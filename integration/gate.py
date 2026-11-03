import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

from policy import (
    LEAD_QUESTIONS,
    MODEL_FEATURES,
    REPLY_QUESTIONS,
    evaluate_contact_persona_fit,
    lead_action,
    route_reply,
    to_python_value,
)

TRAINED_VALUES = {
    "industry": {"manufacturing", "logistics", "professional_services", "healthcare_non_clinical"},
    "region": {"US", "UK"},
    "employee_band": {"200-499", "500-999", "1000-1999", "2000+"},
}
OPT_OUT_PHRASES = (
    "unsubscribe",
    "remove me",
    "take me off",
    "stop emailing",
    "opt out",
    "opt me out",
    "do not contact",
    "don't contact",
)
HOSTNAME = re.compile(r"[a-z0-9-]+(\.[a-z0-9-]+)+")
OUTREACH_CONTEXT = "A first-touch introduction to a fictional B2B procurement service."


def normalize_domain(url: str) -> str | None:
    if not isinstance(url, str) or not url.strip():
        return None
    text = url.strip()
    if "://" not in text:
        text = f"http://{text}"
    hostname = urlparse(text).hostname
    if not hostname or not HOSTNAME.fullmatch(hostname):
        return None
    return hostname.removeprefix("www.")


def make_lead_state(features: dict) -> str:
    feature_state = {name: to_python_value(features.get(name)) for name in MODEL_FEATURES}
    state = {
        "task": "B2B lead qualification",
        "snapshot": "Features available through day 30 after lead creation.",
        "features": feature_state,
    }
    return json.dumps(state, sort_keys=True, ensure_ascii=False)


def build_lead_request(features: dict) -> dict:
    unknown_fields = sorted(set(features) - set(MODEL_FEATURES))
    problems = [f"unknown fields {unknown_fields}"] if unknown_fields else []
    for field, allowed in TRAINED_VALUES.items():
        value = features.get(field)
        if value is None:
            problems.append(f"missing ICP evidence: {field}")
        elif value not in allowed:
            problems.append(f"{field}={value!r} is outside the training categories {sorted(allowed)}")
    if problems:
        raise ValueError("; ".join(problems))
    return {"state": make_lead_state(features), "questions": LEAD_QUESTIONS}


def build_reply_request(reply_text: str, outreach_context: str = OUTREACH_CONTEXT) -> dict:
    if not isinstance(reply_text, str) or not reply_text.strip():
        raise ValueError("reply_text is empty")
    state = {
        "task": "B2B sales reply assessment",
        "outreach_context": outreach_context,
        "recipient_reply": reply_text,
    }
    return {"state": json.dumps(state, sort_keys=True, ensure_ascii=False), "questions": REPLY_QUESTIONS}


def explicit_opt_out_in_text(text: str) -> bool:
    lowered = str(text).casefold().replace("’", "'")
    return any(phrase in lowered for phrase in OPT_OUT_PHRASES)


def _options(question: dict) -> list:
    if question["type"] == "noul":
        return [True, False]
    return list(question["criteria"])


def _valid_answer(answers: dict, name: str, questions: dict):
    entry = answers.get(name) if isinstance(answers, dict) else None
    if not isinstance(entry, dict) or not isinstance(entry.get("probabilities"), dict):
        return None
    answer = entry.get("answer")
    if answer not in _options(questions[name]) or (questions[name]["type"] == "noul" and not isinstance(answer, bool)):
        return None
    return entry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_queue(queue: Path) -> list[dict]:
    path = Path(queue)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append(queue: Path, entry: dict) -> None:
    path = Path(queue)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def gate_lead(domain, answers, *, suppressed, persona_fit, eligibility, queue) -> dict:
    for entry in _read_queue(queue):
        if domain and entry.get("kind") == "lead" and entry.get("domain") == domain:
            return {**entry["result"], "duplicate": True}

    fit = _valid_answer(answers, "icp_fit", LEAD_QUESTIONS)
    prediction = {}
    if fit is not None:
        prediction = {"icp_fit": fit["answer"], "icp_fit_probability": float(fit["probabilities"].get("fit", 0.0))}

    result = lead_action(
        prediction,
        suppressed=suppressed,
        contact_persona_fit=persona_fit,
        contact_eligibility=eligibility,
    )
    result["duplicate"] = False
    _append(
        queue,
        {"kind": "lead", "domain": domain, "answers": answers, "action": result["action"], "result": result, "decided_at": _now()},
    )
    return result


def gate_reply(reply_text, answers, *, contact_is_suppressed, explicit_opt_out_event, queue) -> dict:
    if not isinstance(reply_text, str) or not reply_text.strip():
        raise ValueError("reply_text is empty")

    opt_out_event = True if explicit_opt_out_in_text(reply_text) else explicit_opt_out_event
    intent = _valid_answer(answers, "reply_intent", REPLY_QUESTIONS)
    follow_up = _valid_answer(answers, "follow_up_recommended", REPLY_QUESTIONS)

    result = route_reply(
        predicted_intent=intent["answer"] if intent else None,
        model_follow_up_recommended=follow_up["answer"] if follow_up else None,
        contact_is_suppressed=contact_is_suppressed,
        explicit_opt_out_event=opt_out_event,
    )
    _append(
        queue,
        {"kind": "reply", "reply_text": reply_text, "answers": answers, "action": result["action"], "result": result, "decided_at": _now()},
    )
    return result


def _flag(value: str):
    return {"true": True, "false": False, "unknown": None}[value]


def _load_answers(path: Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data.get("answers", data) if isinstance(data, dict) else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate decision-model answers with the deterministic outreach policy.")
    commands = parser.add_subparsers(dest="command", required=True)
    flags = ["true", "false", "unknown"]

    request = commands.add_parser("lead-request")
    request.add_argument("--features", required=True, type=Path)

    reply_request = commands.add_parser("reply-request")
    reply_request.add_argument("--reply-text", required=True)

    lead = commands.add_parser("lead")
    lead.add_argument("--domain", required=True)
    lead.add_argument("--answers", required=True, type=Path)
    lead.add_argument("--suppressed", choices=flags, default="unknown")
    lead.add_argument("--persona-fit", choices=flags, default="unknown")
    lead.add_argument("--buyer-role")
    lead.add_argument("--eligibility", choices=["approved", "ineligible", "unknown"], default="unknown")
    lead.add_argument("--queue", required=True, type=Path)

    reply = commands.add_parser("reply")
    reply.add_argument("--reply-text", required=True)
    reply.add_argument("--answers", required=True, type=Path)
    reply.add_argument("--suppressed", choices=flags, default="unknown")
    reply.add_argument("--opt-out-event", choices=flags, default="unknown")
    reply.add_argument("--queue", required=True, type=Path)

    args = parser.parse_args(argv)

    if args.command == "lead-request":
        features = json.loads(args.features.read_text(encoding="utf-8"))
        try:
            print(json.dumps(build_lead_request(features), ensure_ascii=False))
        except ValueError as error:
            print(json.dumps({"error": str(error), "next_action": "research_missing_account_evidence", "send": False}))
            return 2
        return 0

    if args.command == "reply-request":
        try:
            print(json.dumps(build_reply_request(args.reply_text), ensure_ascii=False))
        except ValueError as error:
            print(json.dumps({"error": str(error), "send": False}))
            return 2
        return 0

    if args.command == "lead":
        persona_fit = _flag(args.persona_fit)
        if args.buyer_role:
            persona_fit = evaluate_contact_persona_fit(args.buyer_role)
        result = gate_lead(
            normalize_domain(args.domain) or args.domain,
            _load_answers(args.answers),
            suppressed=_flag(args.suppressed),
            persona_fit=persona_fit,
            eligibility=args.eligibility,
            queue=args.queue,
        )
    else:
        result = gate_reply(
            args.reply_text,
            _load_answers(args.answers),
            contact_is_suppressed=_flag(args.suppressed),
            explicit_opt_out_event=_flag(args.opt_out_event),
            queue=args.queue,
        )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
