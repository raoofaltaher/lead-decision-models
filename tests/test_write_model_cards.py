import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from write_model_cards import card

METRICS = {
    "test": {"accuracy": 0.8312, "ece": 0.0421, "loss": 0.512, "record_accuracy": 0.7011, "roc_auc": 0.8644},
    "splits": {"optimizer_training": 2400, "calibration": 598, "validation": 1000, "test": 1002},
    "peak_vram_gb": 9.87,
}


ARGUMENTS = {
    "repo_id": "raoofaltaher/lead-decision-models-lead-qualifier",
    "base_model": "unsloth/Qwen3.5-4B",
    "base_revision": "3764fa359b90",
    "task": "lead",
    "license_id": "apache-2.0",
    "tutorial_url": "https://raoofaltaher.com/tutorials/fine-tune-lfm3-decision-model-with-unsloth",
}


def make_card(**overrides):
    return card(METRICS, **{**ARGUMENTS, **overrides})


def test_card_has_license_and_base_model():
    text = make_card()
    front_matter = text.split("---")[1]
    assert "license: apache-2.0" in front_matter
    assert "base_model: unsloth/Qwen3.5-4B" in front_matter
    assert "library_name: unsloth" in front_matter


def test_card_metrics_come_from_metrics_json():
    text = make_card()
    assert "| accuracy | 0.8312 |" in text
    assert "| roc_auc | 0.8644 |" in text
    assert "2400" in text


def test_card_shows_how_to_load_the_model():
    text = make_card()
    assert 'FastDecisionModel.from_pretrained("raoofaltaher/lead-decision-models-lead-qualifier"' in text


def test_lead_card_shows_the_logistic_baseline_beside_the_model():
    metrics = {**METRICS, "logistic": {"test": {"roc_auc": 0.8758, "brier": 0.1105}}}
    text = card(metrics, **{**ARGUMENTS})
    assert "| Metric | This model | Logistic regression |" in text
    assert "| roc_auc | 0.8644 | 0.8758 |" in text
    assert "| accuracy | 0.8312 | — |" in text
    assert "`roc_auc`, `average_precision`, `brier` and `precision_at_100` score the 90-day conversion question only" in text


def test_reply_card_shows_the_tfidf_baseline_beside_the_model():
    metrics = {"test": {"macro_f1": 0.7782}, "splits": {}, "tfidf": {"validation_macro_f1": 0.5652, "test_macro_f1": 0.7049}}
    text = card(metrics, **{**ARGUMENTS, "task": "reply"})
    assert "| Metric | This model | TF-IDF + logistic regression |" in text
    assert "| macro_f1 | 0.7782 | 0.7049 |" in text
    assert "`macro_f1` scores the 11-intent question only" in text


def test_card_without_remote_code_loads_plainly():
    text = make_card()
    assert "trust_remote_code" not in text


def test_lfm3_card_loads_with_remote_code_and_says_why():
    text = make_card(base_model="LiquidAI/LFM3-1.7B", license_id="other", trust_remote_code=True)
    assert (
        'FastDecisionModel.from_pretrained("raoofaltaher/lead-decision-models-lead-qualifier", '
        "trust_remote_code=True, load_in_4bit=True)"
    ) in text
    assert "custom modeling code" in text
    assert "Read the Python files of `LiquidAI/LFM3-1.7B` at revision `3764fa359b90`" in text


def test_lfm3_card_carries_license_threshold_note():
    text = make_card(
        repo_id="raoofaltaher/lead-decision-models-lfm3-lead-qualifier",
        base_model="LiquidAI/LFM3-1.7B",
        license_id="other",
    )
    assert "license_name: lfm1.0" in text
    assert "license_link: https://huggingface.co/LiquidAI/LFM3-1.7B/blob/3764fa359b90/LICENSE" in text
    assert "revenue threshold" in text


def test_card_links_the_repository_and_the_sibling_model():
    text = make_card(
        repository_url="https://github.com/raoofaltaher/lead-decision-models",
        sibling_repo_id="raoofaltaher/lead-decision-models-lead-qualifier-merged",
        sibling_kind="merged 16-bit model",
    )
    assert "https://github.com/raoofaltaher/lead-decision-models" in text
    assert "[raoofaltaher/lead-decision-models-lead-qualifier-merged](https://huggingface.co/raoofaltaher/lead-decision-models-lead-qualifier-merged)" in text
    assert "merged 16-bit model" in text
