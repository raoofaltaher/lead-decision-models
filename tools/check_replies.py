import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd

INTENTS = [
    "interested",
    "meeting_requested",
    "more_information",
    "referral",
    "not_now",
    "objection",
    "wrong_person",
    "out_of_office",
    "not_interested",
    "opt_out",
    "ambiguous",
]
COLUMNS = ("reply_id", "scenario_group", "outreach_context", "reply_text", "reply_intent", "is_synthetic")
MIN_ROWS = 500
MIN_PER_INTENT = 45
MIN_GROUPS_PER_INTENT = 10


def normalize_text(text: str) -> str:
    lowered = str(text).casefold()
    without_punctuation = re.sub(r"[^\w\s]", " ", lowered)
    words = " ".join(without_punctuation.split())
    return words or lowered.strip()


def as_bool(value) -> bool:
    return str(value).strip().lower() == "true"


def run_checks(df: pd.DataFrame) -> list[str]:
    problems = []
    missing_columns = [column for column in COLUMNS if column not in df.columns]
    if missing_columns:
        return [f"missing columns: {missing_columns}"]

    blank = df[list(COLUMNS[:5])].astype(str).apply(lambda column: column.str.strip().eq("")).any(axis=1)
    if df[list(COLUMNS[:5])].isna().any(axis=1).any() or blank.any():
        problems.append("blank or null values in required columns")

    if df["reply_id"].duplicated().any():
        problems.append(f"duplicate reply_id values: {sorted(df.loc[df['reply_id'].duplicated(), 'reply_id'])[:5]}")

    unknown = sorted(set(df["reply_intent"]) - set(INTENTS))
    if unknown:
        problems.append(f"unknown intent values: {unknown}")

    if not df["is_synthetic"].map(as_bool).all():
        problems.append("is_synthetic is not true on every row")

    normalized = df["reply_text"].map(normalize_text)
    duplicated = normalized[normalized.duplicated(keep=False)]
    if not duplicated.empty:
        problems.append(f"duplicate or near-duplicate reply_text: {sorted(set(duplicated))[:5]}")

    intents_per_group = df.groupby("scenario_group")["reply_intent"].nunique()
    mixed = sorted(intents_per_group[intents_per_group > 1].index)
    if mixed:
        problems.append(f"scenario groups with more than one intent: {mixed[:5]}")

    if len(df) < MIN_ROWS:
        problems.append(f"only {len(df)} rows; at least {MIN_ROWS} required")

    rows_per_intent = df["reply_intent"].value_counts()
    groups_per_intent = df.groupby("reply_intent")["scenario_group"].nunique()
    for intent in INTENTS:
        rows = int(rows_per_intent.get(intent, 0))
        groups = int(groups_per_intent.get(intent, 0))
        if rows < MIN_PER_INTENT:
            problems.append(f"{intent} has {rows} rows; at least {MIN_PER_INTENT} required")
        if groups < MIN_GROUPS_PER_INTENT:
            problems.append(f"{intent} has {groups} scenario groups; at least {MIN_GROUPS_PER_INTENT} required")
    return problems


def merge_relabels(candidates: pd.DataFrame, relabels: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    merged = candidates.merge(relabels[["reply_id", "relabel_intent"]], on="reply_id", how="left", validate="one_to_one")
    agree = merged["relabel_intent"].eq(merged["reply_intent"])
    kept = merged.loc[agree, list(candidates.columns)].reset_index(drop=True)
    dropped = merged.loc[~agree].reset_index(drop=True)
    return kept, dropped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the synthetic reply dataset and apply the blind relabel.")
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--relabels", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    candidates = pd.read_csv(args.candidates, dtype=str, keep_default_na=False)
    relabels = pd.read_csv(args.relabels, dtype=str, keep_default_na=False)
    kept, dropped = merge_relabels(candidates, relabels)
    kept = kept.loc[:, list(COLUMNS)]
    problems = run_checks(kept)

    args.out.mkdir(parents=True, exist_ok=True)
    dataset = args.out / "reply_examples.csv"
    kept.to_csv(dataset, index=False, lineterminator="\n")
    digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
    (args.out / "reply_examples.sha256").write_text(f"{digest}  reply_examples.csv\n", encoding="utf-8")

    report = {
        "rows_in": int(len(candidates)),
        "rows_kept": int(len(kept)),
        "agreement_rate": round(float(len(kept)) / float(len(candidates)), 4) if len(candidates) else 0.0,
        "per_intent_rows": {intent: int((kept["reply_intent"] == intent).sum()) for intent in INTENTS},
        "per_intent_groups": {
            intent: int(kept.loc[kept["reply_intent"] == intent, "scenario_group"].nunique()) for intent in INTENTS
        },
        "dropped": [
            {"reply_id": row.reply_id, "intended": row.reply_intent, "relabel": row.relabel_intent}
            for row in dropped.itertuples()
        ],
        "problems": problems,
    }
    (args.out / "checks_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "dropped"}, indent=2))
    print(f"dropped rows: {len(dropped)}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
