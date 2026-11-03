import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "integration"))


def summarize_latency(seconds: list[float]) -> dict:
    warm = seconds[1:]
    return {
        "calls": len(seconds),
        "first_call_s": round(seconds[0], 2),
        "warm_median_ms": round(statistics.median(warm) * 1000, 1),
        "warm_max_ms": round(max(warm) * 1000, 1),
    }


def same_classes(served: dict, saved: dict) -> bool:
    saved = saved.get("answers", saved)
    return {name: answer.get("answer") for name, answer in served.items()} == {
        name: answer.get("answer") for name, answer in saved.items()
    }


def _requests(case_folder: Path) -> dict[str, list[tuple[str, dict]]]:
    from gate import build_lead_request, build_reply_request

    leads = []
    for features in sorted(case_folder.glob("*.features.json")):
        try:
            leads.append((features.name.removesuffix(".features.json"), build_lead_request(json.loads(features.read_text(encoding="utf-8")))))
        except ValueError:
            continue
    replies = [
        (item["reply_id"], build_reply_request(item["reply_text"]))
        for item in json.loads((ROOT / "data" / "case-study" / "replies.json").read_text(encoding="utf-8"))
    ]
    return {"lead": leads, "reply": replies}


async def _measure(model_folder: Path, requests: list[tuple[str, dict]], case_folder: Path) -> dict:
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(ROOT / "integration" / "decision_server.py"), "--model", str(model_folder)],
        cwd=str(ROOT),
    )
    seconds, matches = [], {}
    async with Client(params) as client:
        for name, request in requests:
            started = time.perf_counter()
            result = await client.call_tool("decide", request)
            seconds.append(time.perf_counter() - started)
            saved = case_folder / f"{name}.answers.json"
            if saved.exists():
                matches[name] = same_classes(result.structured_content["answers"], json.loads(saved.read_text(encoding="utf-8")))
    return {**summarize_latency(seconds), "matches_session": matches}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Time the decision servers over MCP stdio and compare their answers with a recorded session.")
    parser.add_argument("--case-folder", type=Path, default=ROOT / "outputs" / "case-study")
    parser.add_argument("--out", type=Path, default=ROOT / "outputs" / "serving-check.json")
    args = parser.parse_args(argv)

    requests = _requests(args.case_folder)
    report = {
        task: asyncio.run(_measure(ROOT / "outputs" / f"{task}-decision-merged", requests[task], args.case_folder))
        for task in ("lead", "reply")
        if requests[task]
    }
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if all(all(task["matches_session"].values()) for task in report.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
