import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from hub_check import check_repo, file_mismatches

REQUEST = {"state": "s", "questions": {"fit": {"type": "noul"}}}


def write_folder(folder: Path, files: dict) -> Path:
    for name, text in files.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return folder


def answers(value):
    return {"fit": {"answer": value, "probabilities": {"true": 0.7, "false": 0.3}}}


def loader_returning(by_source):
    def load(source):
        if isinstance(by_source[source], Exception):
            raise by_source[source]
        return lambda state, questions: by_source[source]

    return load


def test_identical_folders_have_no_mismatch(tmp_path):
    files = {"config.json": "{}", "nested/model.safetensors": "weights"}
    local = write_folder(tmp_path / "local", files)
    hub = write_folder(tmp_path / "hub", files)
    assert file_mismatches(local, hub) == []


def test_missing_and_changed_files_are_reported_but_readme_and_extras_are_not(tmp_path):
    local = write_folder(tmp_path / "local", {"config.json": "{}", "model.safetensors": "weights", "README.md": "peft card"})
    hub = write_folder(tmp_path / "hub", {"config.json": "{changed}", "README.md": "our card", "02-reply-routing.ipynb": "{}"})
    assert file_mismatches(local, hub) == ["changed config.json", "missing model.safetensors"]


def test_matching_repo_reloads_and_predicts_the_same_classes(tmp_path):
    local = write_folder(tmp_path / "local", {"config.json": "{}"})
    hub = write_folder(tmp_path / "hub", {"config.json": "{}"})
    load = loader_returning({"me/model": answers(True), str(local): answers(True)})
    result = check_repo("me/model", local, REQUEST, download=lambda repo_id: hub, loader=load)
    assert result == {"files_match": True, "reloaded": True, "prediction_matches": True, "hub_classes": {"fit": True}}


def test_a_different_class_is_not_a_match(tmp_path):
    local = write_folder(tmp_path / "local", {"config.json": "{}"})
    hub = write_folder(tmp_path / "hub", {"config.json": "{}"})
    load = loader_returning({"me/model": answers(False), str(local): answers(True)})
    result = check_repo("me/model", local, REQUEST, download=lambda repo_id: hub, loader=load)
    assert result["reloaded"] is True
    assert result["prediction_matches"] is False


def test_a_failed_reload_is_recorded_not_raised(tmp_path):
    local = write_folder(tmp_path / "local", {"config.json": "{}"})
    hub = write_folder(tmp_path / "hub", {})
    load = loader_returning({"me/model": RuntimeError("no base model"), str(local): answers(True)})
    result = check_repo("me/model", local, REQUEST, download=lambda repo_id: hub, loader=load)
    assert result["files_match"] is False
    assert result["file_problems"] == ["missing config.json"]
    assert result["reloaded"] is False
    assert result["prediction_matches"] is False
    assert result["error"] == "RuntimeError: no base model"
