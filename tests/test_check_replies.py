import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import check_replies

CONTEXT = "A first-touch introduction to a fictional B2B procurement automation service."


def clean_frame():
    rows = []
    for intent in check_replies.INTENTS:
        for group in range(check_replies.MIN_GROUPS_PER_INTENT):
            for variant in range(5):
                rows.append(
                    {
                        "reply_id": f"{intent}-{group}-{variant}",
                        "scenario_group": f"{intent}-g{group}",
                        "outreach_context": CONTEXT,
                        "reply_text": f"{intent} reply {group} variant {variant}",
                        "reply_intent": intent,
                        "is_synthetic": True,
                    }
                )
    return pd.DataFrame(rows)


def agreeing_relabels(frame):
    return pd.DataFrame(
        {"reply_id": frame["reply_id"], "relabel_intent": frame["reply_intent"]}
    )


def test_clean_dataset_has_no_problems():
    assert check_replies.run_checks(clean_frame()) == []


def test_unknown_intent_is_a_problem():
    frame = clean_frame()
    frame.loc[0, "reply_intent"] = "maybe_later"

    problems = check_replies.run_checks(frame)

    assert any("unknown intent" in problem for problem in problems)


def test_near_duplicate_text_is_a_problem():
    frame = clean_frame()
    frame.loc[0, "reply_text"] = "Please send pricing."
    frame.loc[60, "reply_text"] = "please send pricing"

    problems = check_replies.run_checks(frame)

    assert any("duplicate" in problem for problem in problems)


def test_symbol_only_replies_are_not_duplicates():
    frame = clean_frame()
    frame.loc[0, "reply_text"] = "\U0001f44d"
    frame.loc[60, "reply_text"] = "?"

    assert check_replies.run_checks(frame) == []


def test_group_with_two_intents_is_a_problem():
    frame = clean_frame()
    other_group = frame.loc[frame["reply_intent"] == "referral", "scenario_group"].iloc[0]
    frame.loc[0, "scenario_group"] = other_group

    problems = check_replies.run_checks(frame)

    assert any("more than one intent" in problem for problem in problems)


def test_intent_below_group_minimum_is_a_problem():
    frame = clean_frame()
    wrong_person = frame["reply_intent"] == "wrong_person"
    frame.loc[wrong_person & (frame["scenario_group"] == "wrong_person-g9"), "scenario_group"] = "wrong_person-g8"

    problems = check_replies.run_checks(frame)

    assert any("wrong_person" in problem and "groups" in problem for problem in problems)


def test_non_synthetic_row_is_a_problem():
    frame = clean_frame()
    frame.loc[3, "is_synthetic"] = False

    problems = check_replies.run_checks(frame)

    assert any("is_synthetic" in problem for problem in problems)


def test_disagreeing_relabel_is_dropped():
    frame = clean_frame()
    relabels = agreeing_relabels(frame)
    relabels.loc[0, "relabel_intent"] = "ambiguous"

    kept, dropped = check_replies.merge_relabels(frame, relabels)

    assert frame.loc[0, "reply_id"] not in set(kept["reply_id"])
    assert list(dropped["reply_id"]) == [frame.loc[0, "reply_id"]]
    assert len(kept) == len(frame) - 1


def test_main_writes_dataset_report_and_checksum(tmp_path):
    frame = clean_frame()
    candidates = tmp_path / "candidates.csv"
    relabels = tmp_path / "relabels.csv"
    frame.to_csv(candidates, index=False)
    agreeing_relabels(frame).to_csv(relabels, index=False)
    out = tmp_path / "out"

    code = check_replies.main(
        ["--candidates", str(candidates), "--relabels", str(relabels), "--out", str(out)]
    )

    assert code == 0
    dataset = out / "reply_examples.csv"
    digest = (out / "reply_examples.sha256").read_text(encoding="utf-8").split()[0]
    assert digest == hashlib.sha256(dataset.read_bytes()).hexdigest()
    report = json.loads((out / "checks_report.json").read_text(encoding="utf-8"))
    assert report["rows_in"] == len(frame)
    assert report["rows_kept"] == len(frame)
    assert report["agreement_rate"] == 1.0
    assert report["problems"] == []
    assert list(pd.read_csv(dataset).columns) == list(check_replies.COLUMNS)
