import argparse
import copy
import json
import statistics
from pathlib import Path

import nbformat

TEST_METRICS = ("accuracy", "ece", "record_accuracy", "roc_auc", "average_precision", "brier", "precision_at_100")
TARGETS = (
    ("FastDecisionModel.get_peft_model(", "random_state=3407,", "random_state={seed},"),
    ("DecisionTrainer(", "seed=3407,", "seed={seed},"),
    ("PUBLISH = ", "PUBLISH = True", "PUBLISH = False"),
)


def seeded_notebook(notebook, seed: int):
    book = copy.deepcopy(notebook)
    for marker, old, new in TARGETS:
        cells = [cell for cell in book.cells if cell.cell_type == "code" and marker in cell.source]
        if len(cells) != 1 or cells[0].source.count(old) != 1:
            raise ValueError(f"expected one cell with {marker!r} and one {old!r} in it")
        cells[0].source = cells[0].source.replace(old, new.format(seed=seed))
    for cell in book.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
    return book


def summarize(runs: dict[str, dict]) -> dict:
    baseline = next(iter(runs.values()))["logistic"]["test"]
    if any(run["logistic"]["test"] != baseline for run in runs.values()):
        raise ValueError("the logistic regression baseline differs between runs, so the split differs")
    per_run = {label: {name: run["test"][name] for name in TEST_METRICS} for label, run in runs.items()}
    summary = {
        name: {
            "mean": round(statistics.fmean(values[name] for values in per_run.values()), 4),
            "min": min(values[name] for values in per_run.values()),
            "max": max(values[name] for values in per_run.values()),
        }
        for name in TEST_METRICS
    }
    return {"runs": per_run, "summary": summary, "logistic_test": baseline}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrain the lead model with other training seeds on the recorded split.")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--notebook", type=Path, required=True)
    prepare.add_argument("--seeds", type=int, nargs="+", required=True)
    prepare.add_argument("--out-root", type=Path, required=True)
    report = commands.add_parser("summarize")
    report.add_argument("--recorded", type=Path, required=True)
    report.add_argument("--seed-root", type=Path, required=True)
    report.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "prepare":
        source = nbformat.read(args.notebook, as_version=4)
        for seed in args.seeds:
            target = args.out_root / f"seed-{seed}" / "notebooks" / args.notebook.name
            target.parent.mkdir(parents=True, exist_ok=True)
            nbformat.write(seeded_notebook(source, seed), target)
            print(target)
        return 0

    runs = {"3407 (recorded)": json.loads(args.recorded.read_text(encoding="utf-8"))}
    for folder in sorted(args.seed_root.glob("seed-*")):
        runs[folder.name.removeprefix("seed-")] = json.loads((folder / "outputs" / "lead-metrics.json").read_text(encoding="utf-8"))
    result = summarize(runs)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
