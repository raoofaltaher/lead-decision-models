import sys
from pathlib import Path

import nbformat
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from seed_study import seeded_notebook, summarize

SPLIT = "splitter = StratifiedGroupKFold(\n    n_splits=5,\n    shuffle=True,\n    random_state=3407,\n)"
LORA = "model = FastDecisionModel.get_peft_model(\n    model,\n    r=16,\n    random_state=3407,\n)"
TRAINER = "trainer = DecisionTrainer(\n    args=DecisionConfig(\n        seed=3407,\n    ),\n)"
SETUP = 'HF_USERNAME = "raoofaltaher"\nPUBLISH = True\n'


def notebook(*sources):
    book = nbformat.v4.new_notebook()
    book.cells = [nbformat.v4.new_code_cell(source) for source in sources]
    book.cells[0].outputs = [nbformat.v4.new_output("stream", text="old output")]
    book.cells[0].execution_count = 7
    return book


def metrics(roc_auc, brier, logistic_roc_auc=0.8758):
    test = {"accuracy": 0.89, "ece": 0.01, "record_accuracy": 0.79, "roc_auc": roc_auc, "average_precision": 0.5, "brier": brier, "precision_at_100": 0.5}
    return {"test": test, "logistic": {"test": {"roc_auc": logistic_roc_auc, "average_precision": 0.5495, "brier": 0.1105, "precision_at_100": 0.54}}}


def test_seeded_notebook_changes_only_the_training_seeds_and_publish():
    book = seeded_notebook(notebook(SETUP, SPLIT, LORA, TRAINER), 2)
    setup, split, lora, trainer = (cell.source for cell in book.cells)
    assert "PUBLISH = False" in setup
    assert split == SPLIT
    assert "random_state=2," in lora
    assert "seed=2," in trainer
    assert book.cells[0].outputs == []
    assert book.cells[0].execution_count is None


def test_seeded_notebook_refuses_a_notebook_where_a_target_is_not_unique():
    with pytest.raises(ValueError, match="get_peft_model"):
        seeded_notebook(notebook(SETUP, SPLIT, LORA, LORA, TRAINER), 2)


def test_summarize_reports_mean_min_and_max_beside_the_baseline():
    report = summarize({"3407": metrics(0.86, 0.11), "1": metrics(0.88, 0.10), "2": metrics(0.87, 0.12)})
    assert report["runs"]["1"]["roc_auc"] == 0.88
    assert report["summary"]["roc_auc"] == {"mean": 0.87, "min": 0.86, "max": 0.88}
    assert report["summary"]["brier"] == {"mean": 0.11, "min": 0.1, "max": 0.12}
    assert report["logistic_test"]["roc_auc"] == 0.8758


def test_summarize_refuses_runs_whose_baselines_differ():
    with pytest.raises(ValueError, match="baseline"):
        summarize({"3407": metrics(0.86, 0.11), "1": metrics(0.88, 0.10, logistic_roc_auc=0.9)})
