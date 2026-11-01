import argparse
import importlib.metadata
import json
import math
import platform
from pathlib import Path

MODEL_ID = "unsloth/Qwen3.5-4B"

QUESTIONS = {
    "team": {
        "type": "choice",
        "instructions": "Which team should handle this?",
        "criteria": {
            "billing": "invoices, payments, refunds",
            "technical": "bugs, outages, errors",
            "sales": "pricing, new plans",
        },
    },
    "refund": {
        "type": "noul",
        "instructions": "Does the customer ask for a refund?",
    },
    "urgency": {
        "type": "score",
        "instructions": "How urgent is this?",
        "criteria": ["not urgent", "soon", "today"],
    },
}

TICKETS = [
    ("Hi, I was charged twice for invoice #4411. Please refund the duplicate today.", {"team": "billing", "refund": True, "urgency": 2}),
    ("The dashboard shows an error when I export a report. Please help in the next few days.", {"team": "technical", "refund": False, "urgency": 1}),
    ("Could you send pricing for your business plan? We are researching for next year; no rush.", {"team": "sales", "refund": False, "urgency": 0}),
    ("Our whole team is locked out after the update. Nothing loads.", {"team": "technical", "refund": False, "urgency": 2}),
    ("Please cancel my subscription and return last month's payment.", {"team": "billing", "refund": True, "urgency": 1}),
    ("We want to add forty seats next quarter. What would that cost?", {"team": "sales", "refund": False, "urgency": 0}),
    ("The invoice lists the wrong company address. Can you correct it this week?", {"team": "billing", "refund": False, "urgency": 1}),
    ("Search returns no results since this morning. Customers are waiting.", {"team": "technical", "refund": False, "urgency": 2}),
]


def make_rows(count):
    rows = []
    for index in range(count):
        state, gold = TICKETS[index % len(TICKETS)]
        rows.append({"state": f"{state} (ticket {index + 1})", "questions": QUESTIONS, "gold": gold})
    return rows


def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["4bit", "16bit"], default="4bit")
    parser.add_argument("--out", default="outputs/smoke-test.json")
    args = parser.parse_args(argv)

    import torch
    from transformers import TrainingArguments
    from unsloth import DecisionTrainer, FastDecisionModel, is_bfloat16_supported

    model, tokenizer = FastDecisionModel.from_pretrained(
        model_name=MODEL_ID,
        max_seq_length=2048,
        load_in_4bit=args.mode == "4bit",
    )
    model = FastDecisionModel.get_peft_model(
        model,
        r=16,
        lora_alpha=16,
        lora_dropout=0,
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    items, report = FastDecisionModel.build_dataset(make_rows(32), tokenizer, model)

    trainer = DecisionTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=items,
        args=TrainingArguments(
            per_device_train_batch_size=8,
            gradient_accumulation_steps=1,
            max_steps=5,
            learning_rate=2e-4,
            logging_steps=1,
            bf16=is_bfloat16_supported(),
            fp16=not is_bfloat16_supported(),
            output_dir="outputs/checkpoints/smoke",
            report_to="none",
            seed=3407,
        ),
    )
    trainer.train()

    losses = [entry["loss"] for entry in trainer.state.log_history if "loss" in entry]
    finite = len(losses) >= 2 and all(math.isfinite(loss) for loss in losses)

    result = {
        "mode": args.mode,
        "loss_first": losses[0] if losses else None,
        "loss_last": losses[-1] if losses else None,
        "losses": losses,
        "build_report": report,
        "peak_vram_gb": round(torch.cuda.max_memory_allocated() / 1024**3, 2),
        "gpu": torch.cuda.get_device_name(0),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "unsloth": package_version("unsloth"),
        "unsloth_zoo": package_version("unsloth_zoo"),
        "transformers": package_version("transformers"),
        "bitsandbytes": package_version("bitsandbytes"),
        "passed": finite,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if finite else 1


if __name__ == "__main__":
    raise SystemExit(main())
