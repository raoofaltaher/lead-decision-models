import argparse
import contextlib
import json
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Union

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import BaseModel, ConfigDict

QUESTION_TYPES = ("noul", "choice", "score")
MAX_QUESTIONS = 64
MAX_CHOICES = 255
MAX_SCORE_LEVELS = 10
MAX_STATE_CHARS = 200_000
MAX_QUESTION_CHARS = 20_000

DECIDE_DESCRIPTION = (
    "Ask the fine-tuned decision model typed questions about a state (text or JSON). "
    'questions maps a name you pick to {"type", "instructions", "criteria"}. '
    '"noul" is yes/no and answers a probability; "choice" needs criteria mapping each option name '
    'to a description; "score" needs criteria listing 1 to 10 levels, lowest first.'
)

JSONContent = Union[str, dict[str, Any], list[Any]]
Decider = Callable[[JSONContent, dict[str, dict[str, Any]]], dict[str, Any]]


class Question(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str
    instructions: JSONContent | None = None
    criteria: JSONContent | None = None


class DecisionRequestError(ValueError):
    pass


def validate_request(state: JSONContent, questions: dict[str, dict[str, Any]]) -> None:
    if not questions:
        raise DecisionRequestError("At least one question is required")
    state_chars = len(state) if isinstance(state, str) else len(json.dumps(state, ensure_ascii=False))
    if state_chars > MAX_STATE_CHARS:
        raise DecisionRequestError(f"State is longer than {MAX_STATE_CHARS} characters")
    if len(questions) > MAX_QUESTIONS:
        raise DecisionRequestError(f"At most {MAX_QUESTIONS} questions per request")
    for name, question in questions.items():
        _validate_question(name, question)


def _validate_question(name: str, question: dict[str, Any]) -> None:
    if len(name) + len(json.dumps(question, ensure_ascii=False)) > MAX_QUESTION_CHARS:
        raise DecisionRequestError(f"Question is longer than {MAX_QUESTION_CHARS} characters")
    kind = question.get("type")
    if kind not in QUESTION_TYPES:
        raise DecisionRequestError(f'Question "{name}" has unknown type "{kind}"')
    criteria = question.get("criteria")
    if kind == "noul":
        if criteria is not None and (not isinstance(criteria, dict) or set(criteria) - {"true", "false"}):
            raise DecisionRequestError(f'Noul "{name}" criteria may only have "true" and "false"')
    elif kind == "choice":
        if not isinstance(criteria, dict) or not criteria:
            raise DecisionRequestError(f'Choice "{name}" needs criteria naming its options')
        if len(criteria) > MAX_CHOICES:
            raise DecisionRequestError(f'Choice "{name}" has more than {MAX_CHOICES} options')
    elif not isinstance(criteria, list) or not 1 <= len(criteria) <= MAX_SCORE_LEVELS:
        raise DecisionRequestError(f'Score "{name}" needs 1 to {MAX_SCORE_LEVELS} criteria levels')
    if criteria is not None:
        entries = criteria.items() if isinstance(criteria, dict) else enumerate(criteria)
        for key, value in entries:
            if value is not None and not isinstance(value, (str, dict, list)):
                raise DecisionRequestError(
                    f'Question "{name}" criteria[{key!r}] must be text, an object, an array or null'
                )


def load_merged_model(path: str) -> Decider:
    from unsloth import FastDecisionModel

    model, tokenizer = FastDecisionModel.from_pretrained(
        path,
        trust_remote_code=True,
        max_seq_length=2048,
        load_in_4bit=True,
    )
    FastDecisionModel.for_inference(model)

    def decide(state: JSONContent, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        return FastDecisionModel.predict(model, tokenizer, state, questions)

    return decide


class DecisionService:
    def __init__(self, model_path: str, loader: Callable[[str], Decider]):
        self.model_path = model_path
        self._loader = loader
        self._decider: Decider | None = None
        self._lock = threading.Lock()

    def decide(self, state: JSONContent, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
        validate_request(state, questions)
        with self._lock, contextlib.redirect_stdout(sys.stderr):
            if self._decider is None:
                self._decider = self._loader(self.model_path)
            return {"answers": self._decider(state, questions)}


def build_server(service: DecisionService) -> MCPServer:
    server = MCPServer("Unsloth decision model")

    @server.tool(description=DECIDE_DESCRIPTION)
    def decide(state: JSONContent, questions: dict[str, Question]) -> dict[str, Any]:
        try:
            return service.decide(
                state, {name: question.model_dump(exclude_none=True) for name, question in questions.items()}
            )
        except ValueError as error:
            raise ToolError(str(error)) from None

    return server


def main(argv: list[str] | None = None, loader: Callable[[str], Decider] = load_merged_model) -> None:
    parser = argparse.ArgumentParser(description="Serve one merged decision model as an MCP decide tool over stdio.")
    parser.add_argument("--model", required=True, help="Local folder of a merged decision model")
    args = parser.parse_args(argv)
    if not (Path(args.model) / "config.json").is_file():
        parser.error(f"{args.model} has no config.json; pass a local merged model folder")
    build_server(DecisionService(args.model, loader)).run("stdio")


if __name__ == "__main__":
    main()
