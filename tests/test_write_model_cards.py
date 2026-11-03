import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from write_model_cards import card

METRICS = {
    "test": {"accuracy": 0.8312, "ece": 0.0421, "loss": 0.512, "record_accuracy": 0.7011, "roc_auc": 0.8644},
    "splits": {"optimizer_training": 2400, "calibration": 598, "validation": 1000, "test": 1002},
    "peak_vram_gb": 9.87,
}


def make_card(**overrides):
    arguments = {
        "repo_id": "raoofaltaher/lead-decision-models-lead-qualifier",
        "base_model": "unsloth/Qwen3.5-4B",
        "base_revision": "3764fa359b90",
        "task": "lead",
        "license_id": "apache-2.0",
        "tutorial_url": "https://raoofaltaher.com/tutorials/fine-tune-decision-models-lead-qualification",
    }
    arguments.update(overrides)
    return card(METRICS, **arguments)


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


def test_lfm3_card_carries_license_threshold_note():
    text = make_card(
        repo_id="raoofaltaher/lead-decision-models-lfm3-lead-qualifier",
        base_model="LiquidAI/LFM3-1.7B",
        license_id="other",
    )
    assert "license_name: lfm1.0" in text
    assert "revenue threshold" in text
