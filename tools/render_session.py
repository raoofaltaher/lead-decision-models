import argparse
import json
from pathlib import Path

INIT_KEYS = ("type", "subtype", "model", "claude_code_version", "permissionMode", "mcp_servers", "tools")
RESULT_KEYS = ("type", "subtype", "duration_ms", "duration_api_ms", "num_turns", "is_error", "result")
CUT = 600
CUT_PREFIX = "mcp__firecrawl__"
NOT_VALIDATED = "> Not validated: trained on synthetic LeadForge data."
ANSWER_KEYS = {"lead": "icp_fit", "reply": "reply_intent"}


def _text(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(block.get("text", "") for block in content or [] if isinstance(block, dict))


def sanitize_events(raw: list[dict]) -> list[dict]:
    names: dict[str, str] = {}
    events = []
    for event in raw:
        kind = event.get("type")
        if kind == "system" and event.get("subtype") == "init":
            events.append({key: event[key] for key in INIT_KEYS if key in event})
        elif kind == "result":
            events.append({key: event[key] for key in RESULT_KEYS if key in event})
        elif kind == "assistant":
            blocks = []
            for block in event["message"]["content"]:
                if block.get("type") == "text":
                    blocks.append({"type": "text", "text": block["text"]})
                elif block.get("type") == "tool_use":
                    names[block["id"]] = block["name"]
                    blocks.append({"type": "tool_use", "id": block["id"], "name": block["name"], "input": block["input"]})
            if blocks:
                events.append({"type": "assistant", "timestamp": event.get("timestamp"), "message": {"content": blocks}})
        elif kind == "user" and isinstance(event.get("message", {}).get("content"), list):
            blocks = []
            for block in event["message"]["content"]:
                if block.get("type") != "tool_result":
                    continue
                text = _text(block.get("content"))
                if names.get(block["tool_use_id"], "").startswith(CUT_PREFIX) and len(text) > CUT:
                    text = f"{text[:CUT]}\n[{len(text) - CUT:,} characters cut]"
                blocks.append({"type": "tool_result", "tool_use_id": block["tool_use_id"], "content": text, "is_error": bool(block.get("is_error"))})
            if blocks:
                events.append({"type": "user", "timestamp": event.get("timestamp"), "message": {"content": blocks}})
    return events


def _cell(text: str) -> str:
    text = " ".join(str(text).split()).replace("|", "\\|")
    return text if len(text) <= 60 else text[:59] + "…"


def _answer(entry: dict) -> str:
    answer = entry.get("answers", {}).get(ANSWER_KEYS.get(entry.get("kind"), ""), {})
    if not isinstance(answer, dict) or "answer" not in answer:
        return "—"
    probability = answer.get("probabilities", {}).get(str(answer["answer"]).lower() if isinstance(answer["answer"], bool) else answer["answer"])
    return f"{answer['answer']} ({probability:.2f})" if isinstance(probability, (int, float)) else str(answer["answer"])


def render_markdown(events: list[dict], *, prompt: str, queue: list[dict]) -> str:
    init = next((event for event in events if event["type"] == "system"), {})
    result = next((event for event in events if event["type"] == "result"), {})
    servers = ", ".join(f"`{server['name']}` ({server['status']})" for server in init.get("mcp_servers", []))
    lines = [
        "# Recorded case study: Tillbrook Procurement",
        "",
        f"Claude Code {init.get('claude_code_version', '?')} with `{init.get('model', '?')}`, permission mode `{init.get('permissionMode', '?')}`. MCP servers: {servers}.",
    ]
    if result:
        lines.append(f"{result.get('num_turns')} turns in {result.get('duration_ms', 0) / 1000:.1f} s.")
    lines += [
        "",
        "## Prompt",
        "",
        "```text",
        prompt.strip(),
        "```",
        "",
        "## Session",
        "",
        "The stream's timestamps can lag a call's start by about a second, too coarse to time a decision, so decision latency is measured directly in `outputs/serving-check.json`.",
        "",
    ]
    calls: dict[str, str] = {}
    step = 0
    for event in events:
        if event["type"] == "assistant":
            for block in event["message"]["content"]:
                if block["type"] == "text":
                    lines += [block["text"].strip(), ""]
                    continue
                step += 1
                calls[block["id"]] = block["name"]
                lines += [f"### {step}. `{block['name']}`", "", "```json", json.dumps(block["input"], indent=2, ensure_ascii=False), "```", ""]
        elif event["type"] == "user":
            for block in event["message"]["content"]:
                name = calls.get(block["tool_use_id"], "")
                label = "Refused or failed:" if block["is_error"] else "Result:"
                lines += [label, "", "```text", block["content"].strip(), "```", ""]
                if name == "mcp__lead-decisions__decide" and not block["is_error"]:
                    lines += [NOT_VALIDATED, ""]
    lines += ["## Approval queue", "", "| # | Kind | Subject | Model answer | Action | Send |", "|---:|---|---|---|---|---|"]
    for number, entry in enumerate(queue, 1):
        subject = entry.get("domain") if entry.get("kind") == "lead" else entry.get("reply_text", "")
        send = str(entry.get("result", {}).get("send")).lower()
        lines.append(f"| {number} | {entry.get('kind')} | {_cell(subject)} | {_answer(entry)} | {entry.get('action')} | {send} |")
    if result:
        lines += ["", "## Final answer", "", str(result.get("result", "")).strip()]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the shareable copies of a recorded Claude Code session.")
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--out-jsonl", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args(argv)

    raw = [json.loads(line) for line in args.raw.read_text(encoding="utf-8").splitlines() if line.strip()]
    events = sanitize_events(raw)
    queue = [json.loads(line) for line in args.queue.read_text(encoding="utf-8").splitlines() if line.strip()]
    args.out_jsonl.write_text("".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events), encoding="utf-8")
    args.out_md.write_text(render_markdown(events, prompt=args.prompt.read_text(encoding="utf-8"), queue=queue), encoding="utf-8")
    print(f"{len(raw)} raw events -> {len(events)} kept; {len(queue)} queue entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
