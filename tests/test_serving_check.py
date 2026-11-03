import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from serving_check import same_classes, summarize_latency


def test_latency_separates_the_loading_call_from_warm_calls():
    assert summarize_latency([31.234, 0.08, 0.12, 0.1]) == {
        "calls": 4,
        "first_call_s": 31.23,
        "warm_median_ms": 100.0,
        "warm_max_ms": 120.0,
    }


def test_answers_match_when_every_class_is_equal_and_the_saved_file_may_be_wrapped():
    served = {"reply_intent": {"answer": "opt_out", "probabilities": {"opt_out": 0.92}}}
    saved = {"answers": {"reply_intent": {"answer": "opt_out", "probabilities": {"opt_out": 0.91}}}}
    assert same_classes(served, saved) is True
    assert same_classes(served, {"reply_intent": {"answer": "not_interested"}}) is False
