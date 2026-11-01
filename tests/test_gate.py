import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integration"))

from gate import (
    build_lead_request,
    build_reply_request,
    explicit_opt_out_in_text,
    gate_lead,
    gate_reply,
    main,
    normalize_domain,
)
from policy import LEAD_QUESTIONS, REPLY_QUESTIONS

FIT_ANSWERS = {
    "icp_fit": {"answer": "fit", "probabilities": {"fit": 0.9, "not_fit": 0.08, "insufficient_evidence": 0.02}},
    "conversion_outcome_90d": {"answer": False, "probabilities": {"true": 0.2, "false": 0.8}},
}

INTERESTED_ANSWERS = {
    "reply_intent": {"answer": "interested", "probabilities": {"interested": 0.9}},
    "follow_up_recommended": {"answer": True, "probabilities": {"true": 0.9, "false": 0.1}},
}


def test_mixed_reply_with_opt_out_phrase_suppresses(tmp_path):
    result = gate_reply(
        "Sounds useful, but please take me off your list.",
        INTERESTED_ANSWERS,
        contact_is_suppressed=False,
        explicit_opt_out_event=False,
        queue=tmp_path / "q.jsonl",
    )
    assert result["action"] == "suppress_marketing"
    assert result["send"] is False


def test_out_of_vocabulary_category_blocks_model_call():
    with pytest.raises(ValueError, match="industry"):
        build_lead_request({"industry": "fintech", "region": "DE", "employee_band": "51-200"})


def test_malformed_answers_fail_closed(tmp_path):
    result = gate_lead(
        "acme.com", {}, suppressed=False, persona_fit=True, eligibility="approved", queue=tmp_path / "q.jsonl"
    )
    assert result["action"] == "human_icp_review"


def test_answer_outside_the_options_fails_closed(tmp_path):
    answers = {"icp_fit": {"answer": "maybe", "probabilities": {"maybe": 1.0}}}
    result = gate_lead(
        "acme.com", answers, suppressed=False, persona_fit=True, eligibility="approved", queue=tmp_path / "q.jsonl"
    )
    assert result["action"] == "human_icp_review"


def test_duplicate_domain_is_not_queued_twice(tmp_path):
    queue = tmp_path / "q.jsonl"
    results = [
        gate_lead(
            normalize_domain(url), FIT_ANSWERS, suppressed=False, persona_fit=True, eligibility="unknown", queue=queue
        )
        for url in ("https://www.acme.com/about", "http://acme.com")
    ]
    assert len(queue.read_text(encoding="utf-8").splitlines()) == 1
    assert results[1]["duplicate"] is True


def test_empty_reply_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        gate_reply("   ", {}, contact_is_suppressed=False, explicit_opt_out_event=False, queue=tmp_path / "q.jsonl")


def test_suppressed_contact_is_blocked_before_answers_are_read(tmp_path):
    result = gate_lead(
        "acme.com", {}, suppressed=True, persona_fit=True, eligibility="approved", queue=tmp_path / "q.jsonl"
    )
    assert result["action"] == "suppress"


def test_fit_with_unknown_eligibility_goes_to_human_review(tmp_path):
    result = gate_lead(
        "acme.com", FIT_ANSWERS, suppressed=False, persona_fit=True, eligibility="unknown", queue=tmp_path / "q.jsonl"
    )
    assert result["action"] == "human_eligibility_review"
    assert result["icp_fit_probability"] == 0.9


def test_every_result_has_send_false(tmp_path):
    queue = tmp_path / "q.jsonl"
    results = [
        gate_lead("a.com", FIT_ANSWERS, suppressed=False, persona_fit=True, eligibility="approved", queue=queue),
        gate_lead("b.com", {}, suppressed=None, persona_fit=None, eligibility="unknown", queue=queue),
        gate_reply("Can we talk on Tuesday?", INTERESTED_ANSWERS, contact_is_suppressed=False, explicit_opt_out_event=False, queue=queue),
        gate_reply("Unsubscribe.", {}, contact_is_suppressed=False, explicit_opt_out_event=False, queue=queue),
    ]
    assert all(result["send"] is False for result in results)


def test_opt_out_phrases_are_detected():
    assert explicit_opt_out_in_text("Please UNSUBSCRIBE me")
    assert explicit_opt_out_in_text("don't contact me again")
    assert not explicit_opt_out_in_text("Can we talk next week?")


def test_normalize_domain_strips_scheme_www_and_path():
    assert normalize_domain("https://www.Acme.com/about?x=1") == "acme.com"
    assert normalize_domain("not a url") is None


def test_build_lead_request_uses_the_training_state_format():
    request = build_lead_request({"industry": "manufacturing", "region": "UK", "employee_band": "500-999"})
    state = json.loads(request["state"])
    assert request["questions"] == LEAD_QUESTIONS
    assert state["task"] == "B2B lead qualification"
    assert state["features"]["industry"] == "manufacturing"
    assert state["features"]["touch_count"] is None


def test_build_reply_request_uses_the_training_state_format():
    request = build_reply_request("Can we talk next week?")
    state = json.loads(request["state"])
    assert request["questions"] == REPLY_QUESTIONS
    assert state == {
        "task": "B2B sales reply assessment",
        "outreach_context": "A first-touch introduction to a fictional B2B procurement service.",
        "recipient_reply": "Can we talk next week?",
    }


def test_build_reply_request_rejects_empty_text():
    with pytest.raises(ValueError):
        build_reply_request("  ")


def test_cli_lead_request_prints_the_request(tmp_path, capsys):
    features = tmp_path / "f.json"
    features.write_text(json.dumps({"industry": "logistics", "region": "US", "employee_band": "200-499"}), encoding="utf-8")

    assert main(["lead-request", "--features", str(features)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["questions"] == LEAD_QUESTIONS
