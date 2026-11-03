import asyncio
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integration"))

from decision_server import (
    MAX_QUESTIONS,
    MAX_STATE_CHARS,
    DecisionRequestError,
    DecisionService,
    main,
    validate_request,
)
from policy import LEAD_QUESTIONS, REPLY_QUESTIONS

NOISY_SERVER = Path(__file__).resolve().parent / "noisy_decision_server.py"


def fake_answers(questions):
    return {name: {"answer": True, "probabilities": {"true": 0.9, "false": 0.1}} for name in questions}


class CountingLoader:
    def __init__(self):
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        return lambda state, questions: fake_answers(questions)


def test_tutorial_question_sets_are_valid_requests():
    validate_request("Company: Example Co.", LEAD_QUESTIONS)
    validate_request("Thanks, send me the pricing.", REPLY_QUESTIONS)


@pytest.mark.parametrize(
    ("state", "questions", "message"),
    [
        ("s", {}, "At least one question is required"),
        ("x" * (MAX_STATE_CHARS + 1), {"q": {"type": "noul"}}, f"State is longer than {MAX_STATE_CHARS} characters"),
        ("s", {f"q{i}": {"type": "noul"} for i in range(MAX_QUESTIONS + 1)}, f"At most {MAX_QUESTIONS} questions per request"),
        ("s", {"q": {"type": "maybe"}}, 'Question "q" has unknown type "maybe"'),
        ("s", {"q": {"type": "noul", "criteria": {"yes": "y"}}}, 'Noul "q" criteria may only have "true" and "false"'),
        ("s", {"q": {"type": "choice"}}, 'Choice "q" needs criteria naming its options'),
        ("s", {"q": {"type": "score", "criteria": [str(i) for i in range(11)]}}, 'Score "q" needs 1 to 10 criteria levels'),
        ("s", {"q": {"type": "choice", "criteria": {"a": 1}}}, "Question \"q\" criteria['a'] must be text, an object, an array or null"),
    ],
)
def test_invalid_requests_are_refused_with_studio_messages(state, questions, message):
    with pytest.raises(DecisionRequestError) as error:
        validate_request(state, questions)
    assert str(error.value) == message


def test_model_loads_on_first_call_only():
    loader = CountingLoader()
    service = DecisionService("/models/lead", loader)
    assert loader.calls == []
    first = service.decide("s", {"fit": {"type": "noul"}})
    service.decide("s", {"fit": {"type": "noul"}})
    assert loader.calls == ["/models/lead"]
    assert first == {"answers": fake_answers({"fit": None})}


def test_invalid_request_does_not_load_the_model():
    loader = CountingLoader()
    service = DecisionService("/models/lead", loader)
    with pytest.raises(DecisionRequestError):
        service.decide("s", {"q": {"type": "maybe"}})
    assert loader.calls == []


def test_concurrent_first_calls_load_once():
    loader = CountingLoader()
    service = DecisionService("/models/lead", loader)
    threads = [threading.Thread(target=service.decide, args=("s", {"fit": {"type": "noul"}})) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert loader.calls == ["/models/lead"]


def test_missing_model_folder_stops_at_startup(tmp_path, capsys):
    loader = CountingLoader()
    with pytest.raises(SystemExit) as stop:
        main(["--model", str(tmp_path / "missing")], loader=loader)
    assert stop.value.code == 2
    assert "config.json" in capsys.readouterr().err
    assert loader.calls == []


def test_stdio_round_trip_survives_stdout_noise(tmp_path):
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters

    model = tmp_path / "merged"
    model.mkdir()
    (model / "config.json").write_text("{}", encoding="utf-8")
    params = StdioServerParameters(command=sys.executable, args=[str(NOISY_SERVER), "--model", str(model)])

    async def session():
        async with Client(params) as client:
            tools = await client.list_tools()
            good = await client.call_tool("decide", {"state": "s", "questions": {"fit": {"type": "noul"}}})
            bad = await client.call_tool("decide", {"state": "s", "questions": {"q": {"type": "maybe"}}})
            return tools, good, bad

    tools, good, bad = asyncio.run(asyncio.wait_for(session(), timeout=60))
    assert [tool.name for tool in tools.tools] == ["decide"]
    assert good.is_error is False
    assert good.structured_content == {"answers": fake_answers({"fit": None})}
    assert bad.is_error is True
    assert 'Question "q" has unknown type "maybe"' in bad.content[0].text


def test_every_stdout_line_is_json_rpc_through_shutdown(tmp_path):
    from mcp_types import LATEST_PROTOCOL_VERSION

    model = tmp_path / "merged"
    model.mkdir()
    (model / "config.json").write_text("{}", encoding="utf-8")
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": LATEST_PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "decide", "arguments": {"state": "s", "questions": {"fit": {"type": "noul"}}}},
        },
    ]
    process = subprocess.Popen(
        [sys.executable, str(NOISY_SERVER), "--model", str(model)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    watchdog = threading.Timer(60, process.kill)
    watchdog.start()
    try:
        process.stdin.write("".join(json.dumps(message) + "\n" for message in messages))
        process.stdin.flush()
        lines = []
        while not any(json.loads(line).get("id") == 2 for line in lines):
            line = process.stdout.readline()
            assert line, "the server closed stdout before it answered the tool call"
            lines.append(line)
        process.stdin.close()
        lines.extend(process.stdout.read().splitlines())
        process.wait(timeout=30)
    finally:
        watchdog.cancel()
    stray = [line for line in lines if line.strip() and "jsonrpc" not in json.loads(line)]
    assert stray == []
