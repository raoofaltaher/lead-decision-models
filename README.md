# lead-decision-models

Fine-tuned [Unsloth](https://unsloth.ai/docs/basics/train-your-own-decision-model-with-unsloth) decision models for two decisions in a B2B lead engine:

- **Lead qualification**: does an account fit the example Ideal Customer Profile, and did the lead convert within 90 days in LeadForge's synthetic CRM data?
- **Reply routing**: which of 11 intents does a prospect's reply express, and does it call for a next step?

The models never send a message. Deterministic policy code decides what is allowed, and a person approves every outreach.

This repository is the companion to a three-part tutorial on [raoofaltaher.com](https://raoofaltaher.com/tutorials).

## Contents

| Path | What it holds |
|---|---|
| `notebooks/` | The executed notebooks the tutorial quotes |
| `data/replies/` | The synthetic reply dataset, its card, checksum and check report |
| `integration/` | The policy gate and the serving setup for Claude Code |
| `outputs/` | Metrics, manifests and the recorded case-study session |
| `tools/` | Checks that keep the code, the data and the tutorial consistent |

## Run it

Setup, hardware, versions and timings are added after the recorded run.

## License

MIT. The base model, Qwen3.5-4B, is Apache-2.0. LeadForge data is MIT and is downloaded at run time, not redistributed.
