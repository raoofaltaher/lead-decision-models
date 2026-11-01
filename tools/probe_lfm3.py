import argparse
import importlib.metadata
import json
import math
import subprocess
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from smoke_test import make_rows

MODEL_ID = "LiquidAI/LFM3-1.7B"
REVISION = "ac2586a34f1a1c03329dbdcdefabd8b6478ddaa7"


def package_version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def try_mode(mode: str) -> dict:
    record = {"loaded": False, "trained": False, "loss_first": None, "loss_last": None, "error": None}
    try:
        from transformers import TrainingArguments
        from unsloth import DecisionTrainer, FastDecisionModel, is_bfloat16_supported

        model, tokenizer = FastDecisionModel.from_pretrained(
            model_name=MODEL_ID,
            revision=REVISION,
            trust_remote_code=True,
            max_seq_length=2048,
            load_in_4bit=mode == "4bit",
        )
        record["loaded"] = True
        model = FastDecisionModel.get_peft_model(model, r=16, lora_alpha=16, lora_dropout=0, random_state=3407)
        items, _ = FastDecisionModel.build_dataset(make_rows(32), tokenizer, model)
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
                output_dir=f"outputs/checkpoints/lfm3-{mode}",
                report_to="none",
                seed=3407,
            ),
        )
        trainer.train()
        losses = [entry["loss"] for entry in trainer.state.log_history if "loss" in entry]
        record.update(loss_first=losses[0] if losses else None, loss_last=losses[-1] if losses else None)
        record["trained"] = (
            len(losses) >= 2 and all(math.isfinite(loss) for loss in losses) and losses[-1] < losses[0]
        )
    except Exception as error:
        record["error"] = f"{type(error).__name__}: {error}"
        record["traceback_tail"] = traceback.format_exc().strip().splitlines()[-6:]
    return record


def run_isolated(mode: str) -> dict:
    completed = subprocess.run(
        [sys.executable, __file__, "--single", mode], capture_output=True, text=True
    )
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith("PROBE_RESULT "):
            return json.loads(line.removeprefix("PROBE_RESULT "))
    return {
        "loaded": False,
        "trained": False,
        "loss_first": None,
        "loss_last": None,
        "error": f"process exited with code {completed.returncode}",
        "traceback_tail": completed.stderr.strip().splitlines()[-6:],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Probe whether Unsloth's decision trainer can train LFM3-1.7B.")
    parser.add_argument("--single", choices=["4bit", "16bit"])
    parser.add_argument("--out", default="outputs/lfm3-probe.json")
    args = parser.parse_args(argv)

    if args.single:
        print("PROBE_RESULT " + json.dumps(try_mode(args.single)))
        return 0

    result = {"model_id": MODEL_ID, "revision": REVISION}
    result["mode_4bit"] = run_isolated("4bit")
    result["mode_16bit"] = run_isolated("16bit")
    result.update(
        unsloth=package_version("unsloth"),
        unsloth_zoo=package_version("unsloth_zoo"),
        transformers=package_version("transformers"),
        huggingface_hub=package_version("huggingface_hub"),
    )
    supported = any(result[key]["loaded"] and result[key]["trained"] for key in ("mode_4bit", "mode_16bit"))
    result["verdict"] = "supported" if supported else "not_supported"

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
