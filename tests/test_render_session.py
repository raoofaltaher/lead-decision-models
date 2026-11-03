import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from render_session import CUT, render_markdown, sanitize_events

INIT = {
    "type": "system",
    "subtype": "init",
    "model": "claude-opus-5-5",
    "claude_code_version": "2.1.246",
    "permissionMode": "default",
    "mcp_servers": [{"name": "lead-decisions", "status": "connected", "source": "dynamic"}],
    "tools": ["mcp__lead-decisions__decide"],
    "plugins": [{"name": "personal-plugin"}],
    "memory_paths": ["/home/dev/.claude/memory"],
    "apiKeySource": "none",
    "session_id": "abc",
}
RESULT = {
    "type": "result",
    "subtype": "success",
    "duration_ms": 61000,
    "num_turns": 12,
    "is_error": False,
    "result": "Done. No message was sent.",
    "total_cost_usd": 1.23,
    "usage": {"input_tokens": 5},
}


def tool_use(call_id, name, arguments, timestamp, request_id=None):
    return {
        "type": "assistant",
        "timestamp": timestamp,
        "request_id": request_id or f"request-{call_id}",
        "session_id": "abc",
        "wire_tool_inputs": {},
        "message": {"content": [{"type": "thinking", "thinking": "", "signature": "sig"}, {"type": "tool_use", "id": call_id, "name": name, "input": arguments, "caller": {}}]},
    }


def tool_result(call_id, text, timestamp, is_error=False):
    return {
        "type": "user",
        "timestamp": timestamp,
        "tool_use_result": {"raw": text},
        "tool_result_meta": {},
        "message": {"content": [{"type": "tool_result", "tool_use_id": call_id, "content": text, "is_error": is_error}]},
    }


def test_init_keeps_only_the_listed_keys():
    assert sanitize_events([INIT]) == [
        {
            "type": "system",
            "subtype": "init",
            "model": "claude-opus-5-5",
            "claude_code_version": "2.1.246",
            "permissionMode": "default",
            "mcp_servers": INIT["mcp_servers"],
            "tools": INIT["tools"],
        }
    ]


def test_rate_limits_costs_and_usage_never_reach_the_output():
    text = json.dumps(sanitize_events([INIT, {"type": "rate_limit_event", "rate_limit_info": {"used": 3}}, RESULT]))
    for word in ("rate_limit", "total_cost_usd", "usage", "plugins", "memory_paths", "session_id"):
        assert word not in text


def test_firecrawl_results_are_cut_and_thinking_and_raw_copies_dropped():
    events = sanitize_events(
        [
            tool_use("t1", "mcp__firecrawl__firecrawl_scrape", {"url": "https://example.com/about"}, "2026-11-03T13:00:00.000Z"),
            tool_result("t1", "x" * 2000, "2026-11-03T13:00:02.000Z"),
        ]
    )
    use, result = events
    assert [block["type"] for block in use["message"]["content"]] == ["tool_use"]
    content = result["message"]["content"][0]["content"]
    assert content.startswith("x" * CUT)
    assert content.endswith("[1,400 characters cut]")
    assert "tool_use_result" not in result


def test_decide_answers_are_kept_whole():
    answer = json.dumps({"answers": {"fit": {"answer": True, "probabilities": {"true": 0.9, "false": 0.1}}}}) + " " * 2000
    events = sanitize_events([tool_use("t2", "mcp__lead-decisions__decide", {}, "2026-11-03T13:00:00.000Z"), tool_result("t2", answer, "2026-11-03T13:00:01.000Z")])
    assert events[1]["message"]["content"][0]["content"] == answer


def test_markdown_shows_the_not_validated_label():
    events = sanitize_events(
        [
            INIT,
            tool_use("t2", "mcp__lead-decisions__decide", {"state": "s", "questions": {}}, "2026-11-03T13:00:00.000Z"),
            tool_result("t2", '{"answers": {}}', "2026-11-03T13:00:31.500Z"),
            RESULT,
        ]
    )
    text = render_markdown(events, prompt="PROMPT TEXT", queue=[])
    assert "claude-opus-5-5" in text
    assert "PROMPT TEXT" in text
    assert "Result:\n" in text
    assert "> Not validated: trained on synthetic LeadForge data." in text
    assert "12 turns in 61.0 s" in text


def test_stream_timestamps_never_become_call_durations():
    events = sanitize_events(
        [
            tool_use("a", "mcp__reply-decisions__decide", {}, "2026-11-03T13:00:04.600Z", request_id="r1"),
            tool_result("a", "{}", "2026-11-03T13:00:03.900Z"),
        ]
    )
    text = render_markdown(events, prompt="P", queue=[])
    assert " s:" not in text
    assert "outputs/serving-check.json" in text
    assert "request_id" not in json.dumps(events)


def test_markdown_shows_refused_calls_and_the_queue():
    events = sanitize_events([tool_use("t3", "Bash", {"command": "curl example.com"}, "2026-11-03T13:00:00.000Z"), tool_result("t3", "Permission denied", "2026-11-03T13:00:00.200Z", is_error=True)])
    queue = [
        {"kind": "lead", "domain": "example.com", "answers": {"icp_fit": {"answer": "fit", "probabilities": {"fit": 0.91}}}, "action": "human_review_outreach", "result": {"send": False}},
        {"kind": "reply", "reply_text": "Please unsubscribe me.", "answers": {"reply_intent": {"answer": "opt_out", "probabilities": {"opt_out": 0.97}}}, "action": "suppress_marketing", "result": {"send": False}},
    ]
    text = render_markdown(events, prompt="P", queue=queue)
    assert "Refused or failed:\n" in text
    assert "| 1 | lead | example.com | fit (0.91) | human_review_outreach | false |" in text
    assert "| 2 | reply | Please unsubscribe me. | opt_out (0.97) | suppress_marketing | false |" in text
