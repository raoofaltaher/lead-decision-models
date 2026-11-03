import gc
import json
import sys
import traceback
from pathlib import Path

sys.path.insert(0, "tools")

import torch
from transformers import TrainingArguments
from unsloth import DecisionTrainer, FastDecisionModel, is_bfloat16_supported

from smoke_test import QUESTIONS, make_rows

MODEL = "LiquidAI/LFM3-1.7B"
REVISION = "ac2586a34f1a1c03329dbdcdefabd8b6478ddaa7"
TICKET = "Hi, I was charged twice for invoice #4411. Please refund the duplicate today."
REPORT = {"model": MODEL, "revision": REVISION, "steps": {}}
STATE = {}


def step(name, action):
    try:
        REPORT["steps"][name] = {"ok": True, "result": action()}
    except Exception as error:
        REPORT["steps"][name] = {"ok": False, "error": f"{type(error).__name__}: {error}", "trace": traceback.format_exc().splitlines()[-5:]}
    print(name, "OK" if REPORT["steps"][name]["ok"] else REPORT["steps"][name]["error"], flush=True)
    return REPORT["steps"][name]["ok"]


def load():
    model, tokenizer = FastDecisionModel.from_pretrained(MODEL, revision=REVISION, trust_remote_code=True, max_seq_length=2048, load_in_4bit=True)
    STATE["model"] = FastDecisionModel.get_peft_model(model, r=16, lora_alpha=16, lora_dropout=0, random_state=3407)
    STATE["tokenizer"] = tokenizer
    return "loaded 4-bit with LoRA r=16"


def build():
    STATE["train"], report = FastDecisionModel.build_dataset(make_rows(64), STATE["tokenizer"], STATE["model"])
    STATE["holdout"], _ = FastDecisionModel.build_dataset(make_rows(40), STATE["tokenizer"], STATE["model"])
    return report


def train():
    trainer = DecisionTrainer(
        model=STATE["model"],
        processing_class=STATE["tokenizer"],
        train_dataset=STATE["train"],
        args=TrainingArguments(
            per_device_train_batch_size=8,
            gradient_accumulation_steps=1,
            max_steps=20,
            learning_rate=2e-4,
            logging_steps=5,
            bf16=is_bfloat16_supported(),
            fp16=not is_bfloat16_supported(),
            output_dir="outputs/checkpoints/e2e-lfm3",
            report_to="none",
            seed=3407,
        ),
    )
    trainer.train()
    return [entry["loss"] for entry in trainer.state.log_history if "loss" in entry]


def predict(model, tokenizer):
    FastDecisionModel.for_inference(model)
    answers = FastDecisionModel.predict(model, tokenizer, TICKET, QUESTIONS)
    return {name: answer["answer"] for name, answer in answers.items()}


def reload(path):
    model, tokenizer = FastDecisionModel.from_pretrained(path, trust_remote_code=True, max_seq_length=2048, load_in_4bit=True)
    result = predict(model, tokenizer)
    del model, tokenizer
    gc.collect()
    torch.cuda.empty_cache()
    return result


if step("load", load) and step("build_dataset", build) and step("train", train):
    step("calibrate", lambda: FastDecisionModel.calibrate(STATE["model"], STATE["tokenizer"], STATE["holdout"]))
    step("evaluate", lambda: FastDecisionModel.evaluate(STATE["model"], STATE["tokenizer"], STATE["holdout"]))
    step("predict", lambda: predict(STATE["model"], STATE["tokenizer"]))
    step("save_adapter", lambda: STATE["model"].save_pretrained("outputs/e2e-lfm3-adapter") or "saved")
    step("save_merged", lambda: STATE["model"].save_pretrained_merged("outputs/e2e-lfm3-merged", STATE["tokenizer"]) or "saved")
    REPORT["peak_vram_gb"] = round(torch.cuda.max_memory_allocated() / 1024**3, 2)
    del STATE["model"]
    gc.collect()
    torch.cuda.empty_cache()
    step("reload_adapter_predict", lambda: reload("outputs/e2e-lfm3-adapter"))
    step("reload_merged_predict", lambda: reload("outputs/e2e-lfm3-merged"))

Path("outputs/lfm3-e2e-check.json").write_text(json.dumps(REPORT, indent=2, default=str), encoding="utf-8")
print(json.dumps(REPORT, indent=2, default=str))
