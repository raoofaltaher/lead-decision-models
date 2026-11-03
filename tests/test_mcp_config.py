import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVERS = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]


def test_decision_servers_run_the_stdio_server_on_the_merged_models():
    folders = {"lead-decisions": "outputs/lead-decision-merged", "reply-decisions": "outputs/reply-decision-merged"}
    for name, folder in folders.items():
        server = SERVERS[name]
        assert server["type"] == "stdio"
        assert server["command"] == "unsloth_env/bin/python"
        assert server["args"] == ["integration/decision_server.py", "--model", folder]
        assert (ROOT / server["args"][0]).is_file()


def test_firecrawl_stays_the_hosted_oauth_server():
    assert SERVERS["firecrawl"] == {"type": "http", "url": "https://mcp.firecrawl.dev/v2/mcp-oauth"}


def test_no_other_servers_are_registered():
    assert sorted(SERVERS) == ["firecrawl", "lead-decisions", "reply-decisions"]
