import argparse
import gc
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integration"))

BASE_MODEL = "LiquidAI/LFM3-1.7B"
BASE_REVISION = "ac2586a34f1a1c03329dbdcdefabd8b6478ddaa7"
REPOS = {
    "lead-decision-models-lead-qualifier": ("outputs/lead-decision-adapter", "lead"),
    "lead-decision-models-lead-qualifier-merged": ("outputs/lead-decision-merged", "lead"),
    "lead-decision-models-reply-router": ("outputs/reply-decision-adapter", "reply"),
    "lead-decision-models-reply-router-merged": ("outputs/reply-decision-merged", "reply"),
}
IGNORED_FILES = {"README.md"}


def _digests(folder: Path) -> dict[str, str]:
    return {
        path.relative_to(folder).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def file_mismatches(local: Path, hub: Path) -> list[str]:
    hub_digests = _digests(hub)
    problems = []
    for name, digest in _digests(local).items():
        if name in IGNORED_FILES:
            continue
        if name not in hub_digests:
            problems.append(f"missing {name}")
        elif hub_digests[name] != digest:
            problems.append(f"changed {name}")
    return problems


def _classes(answers: dict) -> dict:
    return {name: answer["answer"] for name, answer in answers.items()}


def check_repo(repo_id: str, local_folder: Path, request: dict, *, download, loader) -> dict:
    problems = file_mismatches(Path(local_folder), Path(download(repo_id)))
    result = {"files_match": not problems, "reloaded": False, "prediction_matches": False}
    if problems:
        result["file_problems"] = problems
    try:
        hub_answers = loader(repo_id)(request["state"], request["questions"])
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        return result
    local_answers = loader(str(local_folder))(request["state"], request["questions"])
    result["reloaded"] = True
    result["prediction_matches"] = _classes(hub_answers) == _classes(local_answers)
    result["hub_classes"] = _classes(hub_answers)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check that each Hub repository holds the local model and predicts the same classes.")
    parser.add_argument("--user", required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs" / "hub-check.json")
    args = parser.parse_args(argv)

    import torch
    from decision_server import load_merged_model
    from gate import build_lead_request, build_reply_request
    from huggingface_hub import HfApi, snapshot_download

    requests = {
        "lead": build_lead_request({"industry": "manufacturing", "region": "UK", "employee_band": "500-999"}),
        "reply": build_reply_request("Thanks, this looks relevant. Can you send pricing for 300 seats?"),
    }
    report = {
        "base_model": BASE_MODEL,
        "base_revision_pinned": BASE_REVISION,
        "base_main_revision": HfApi().model_info(BASE_MODEL).sha,
        "repos": {},
    }
    for name, (folder, task) in REPOS.items():
        repo_id = f"{args.user}/{name}"
        report["repos"][repo_id] = check_repo(
            repo_id, ROOT / folder, requests[task], download=snapshot_download, loader=load_merged_model
        )
        gc.collect()
        torch.cuda.empty_cache()
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if all(repo["files_match"] and repo["prediction_matches"] for repo in report["repos"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
