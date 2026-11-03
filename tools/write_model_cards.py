import argparse
import json
from pathlib import Path

TASKS = {
    "lead": {
        "title": "lead qualifier",
        "tag": "lead-qualification",
        "use": "Scores a B2B lead record against an example Ideal Customer Profile (fit, not_fit, insufficient_evidence) and classifies LeadForge's 90-day conversion label.",
        "data": "The intermediate tier of the LeadForge synthetic CRM release v0.1.0-alpha (MIT), split by account so no company appears in two partitions.",
        "scope": "`accuracy`, `ece`, `loss` and `record_accuracy` cover both questions; `roc_auc`, `average_precision`, `brier` and `precision_at_100` score the 90-day conversion question only.",
    },
    "reply": {
        "title": "reply router",
        "tag": "reply-routing",
        "use": "Classifies a prospect's reply to a first-touch sales email into one of 11 intents and predicts whether a next step is called for.",
        "data": "617 LLM-generated synthetic replies, checked automatically with a blind relabel and not reviewed by a person (see data/replies/DATASET_CARD.md in the companion repository).",
        "scope": "`accuracy`, `ece`, `loss` and `record_accuracy` cover both questions; `macro_f1` scores the 11-intent question only.",
    },
}
LFM_NOTE = (
    "LFM3-1.7B is released under the LFM Open License v1.0. Commercial use of the model and of derivatives "
    "such as this one is licensed only below the revenue threshold that license defines; read it before any commercial use."
)


def _baseline(metrics: dict) -> tuple[str | None, dict]:
    if "logistic" in metrics:
        return "Logistic regression", metrics["logistic"].get("test", {})
    if "tfidf" in metrics:
        return "TF-IDF + logistic regression", {"macro_f1": metrics["tfidf"]["test_macro_f1"]}
    return None, {}


def card(
    metrics: dict,
    *,
    repo_id: str,
    base_model: str,
    base_revision: str,
    task: str,
    license_id: str,
    tutorial_url: str,
    trust_remote_code: bool = False,
    repository_url: str | None = None,
    sibling_repo_id: str | None = None,
    sibling_kind: str | None = None,
    tutorial_title: str | None = None,
    tutorial_cover_url: str | None = None,
    article_title: str | None = None,
    article_url: str | None = None,
    article_cover_url: str | None = None,
) -> str:
    info = TASKS[task]
    showcase = ""
    if tutorial_title and tutorial_cover_url and article_title and article_url and article_cover_url:
        showcase = (
            "## Read the tutorial\n\n"
            "<p>\n"
            f'<a href="{tutorial_url}"><img src="{tutorial_cover_url}" alt="{tutorial_title}" width="49%"></a>\n'
            f'<a href="{article_url}"><img src="{article_cover_url}" alt="{article_title}" width="49%"></a>\n'
            "</p>\n\n"
            f"The tutorial [{tutorial_title}]({tutorial_url}) trains and uses this model step by step, "
            f"and the article [{article_title}]({article_url}) explains decision models. Both are on raoofaltaher.com.\n\n"
        )
    links = []
    if repository_url:
        links.append(f"- Companion repository with the notebook, the data, the plots and the tests: {repository_url}")
    if sibling_repo_id:
        links.append(f"- The {sibling_kind} of the same run: [{sibling_repo_id}](https://huggingface.co/{sibling_repo_id})")
    links.append(f"- The tutorial that trains and uses it: {tutorial_url}")
    link_section = "## Links\n\n" + "\n".join(links) + "\n"
    load_arguments = f'"{repo_id}", trust_remote_code=True, load_in_4bit=True' if trust_remote_code else f'"{repo_id}", load_in_4bit=True'
    remote_code_note = (
        f"\n`{base_model}` ships custom modeling code, so loading needs `trust_remote_code=True`. "
        f"Read the Python files of `{base_model}` at revision `{base_revision}` before you run it; "
        "the merged repository carries copies of them.\n"
        if trust_remote_code
        else ""
    )
    license_lines = f"license: {license_id}\n"
    if license_id == "other":
        license_lines += f"license_name: lfm1.0\nlicense_link: https://huggingface.co/{base_model}/blob/{base_revision}/LICENSE\n"
    baseline_name, baseline = _baseline(metrics)
    model_metrics = {name: value for name, value in metrics.get("test", {}).items() if isinstance(value, (int, float))}
    if baseline_name:
        metric_table = f"| Metric | This model | {baseline_name} |\n|---|---:|---:|\n" + "\n".join(
            f"| {name} | {value:.4f} | {baseline[name]:.4f} |" if name in baseline else f"| {name} | {value:.4f} | — |"
            for name, value in model_metrics.items()
        )
    else:
        metric_table = "| Metric | Value |\n|---|---:|\n" + "\n".join(f"| {name} | {value:.4f} |" for name, value in model_metrics.items())
    split_rows = "\n".join(f"| {name} | {value} |" for name, value in metrics.get("splits", {}).items())
    note = f"\n{LFM_NOTE}\n" if license_id == "other" else ""
    return f"""---
{license_lines}base_model: {base_model}
library_name: unsloth
tags:
- decision-model
- unsloth
- clef
- {info['tag']}
---

# {repo_id.split('/')[-1]}

A decision model ({info['title']}) fine-tuned from `{base_model}` (revision `{base_revision}`) with Unsloth's `FastDecisionModel` and a Clef decision head. It scores the options it is given and returns probabilities; it never generates text and never sends a message.

{showcase}## Intended use

{info['use']} It is a teaching model from the tutorial at {tutorial_url}. Deterministic policy code and a person must decide every outreach action; a model probability is not permission to contact anyone.

## Training data

{info['data']}

| Partition | Rows |
|---|---:|
{split_rows}

## Test metrics from the recorded run

{metric_table}

{info['scope']} Lower is better for `ece`, `loss` and `brier`; higher is better for the others. The baseline column comes from the same run, the same split and the same features.

Peak training VRAM: {metrics.get('peak_vram_gb')} GB.

{link_section}
## How to load

```python
from unsloth import FastDecisionModel

model, tokenizer = FastDecisionModel.from_pretrained({load_arguments})
FastDecisionModel.for_inference(model)
```
{remote_code_note}
## Limitations

The training data is synthetic. These metrics show that the pipeline works; they do not show performance on real CRM records or real sales replies. Probabilities and calibration can shift when the market, the data source or the process changes.
{note}"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Write a Hugging Face model card from a metrics file.")
    parser.add_argument("--metrics", required=True, type=Path)
    parser.add_argument("--repo-id", required=True)
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--base-revision", required=True)
    parser.add_argument("--task", choices=sorted(TASKS), required=True)
    parser.add_argument("--license", dest="license_id", default="apache-2.0")
    parser.add_argument("--tutorial-url", required=True)
    parser.add_argument("--trust-remote-code", action="store_true")
    parser.add_argument("--repository-url")
    parser.add_argument("--sibling-repo-id")
    parser.add_argument("--sibling-kind")
    parser.add_argument("--tutorial-title")
    parser.add_argument("--tutorial-cover-url")
    parser.add_argument("--article-title")
    parser.add_argument("--article-url")
    parser.add_argument("--article-cover-url")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    metrics = json.loads(args.metrics.read_text(encoding="utf-8"))
    args.out.write_text(
        card(
            metrics,
            repo_id=args.repo_id,
            base_model=args.base_model,
            base_revision=args.base_revision,
            task=args.task,
            license_id=args.license_id,
            tutorial_url=args.tutorial_url,
            trust_remote_code=args.trust_remote_code,
            repository_url=args.repository_url,
            sibling_repo_id=args.sibling_repo_id,
            sibling_kind=args.sibling_kind,
            tutorial_title=args.tutorial_title,
            tutorial_cover_url=args.tutorial_cover_url,
            article_title=args.article_title,
            article_url=args.article_url,
            article_cover_url=args.article_cover_url,
        ),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
