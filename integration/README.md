# Integration: Claude Code and the decision models

Part 3 of the tutorial. Claude Code researches prospects with Firecrawl and hands two bounded decisions to the fine-tuned models, served by Unsloth Studio's Decision API. A deterministic gate turns every decision into a queue entry for a person to approve. Nothing here can send a message.

## 1. Serve the two models

Both notebooks must have run, so that `outputs/lead-decision-merged/` and `outputs/reply-decision-merged/` exist.

```bash
./integration/serve.sh
```

The script starts two Unsloth Studio processes on the loopback address only:

| Model | Address | Studio data folder |
|---|---|---|
| Lead qualification | `http://127.0.0.1:8888` | `~/.studio-lead` |
| Reply routing | `http://127.0.0.1:8889` | `~/.studio-reply` |

`UNSLOTH_SYSTEMONE_MODEL` points each process at its merged folder. Studio loads the model on the first request, which can take a minute.

## 2. Turn on the Decision API (once per process)

Open each address in a browser and:

1. Complete Studio's first-run setup.
2. Open Settings → API → Decision API and turn on **Serve requests**.
3. Turn on **Keyless API access** for localhost, or create an API key under Access tokens.

With a key, add an `Authorization` header to the matching `.mcp.json` entry and keep the key in an environment variable, never in a file:

```json
"headers": { "Authorization": "Bearer ${LEAD_DECISIONS_KEY}" }
```

## 3. Connect Claude Code

`.mcp.json` in the repository root registers three servers: `lead-decisions` and `reply-decisions` (Studio's built-in MCP endpoint, tool `decide`) and `firecrawl` (sign in once in the browser). Start Claude Code in the repository folder, with the virtual environment active, and check:

```bash
claude mcp list
```

## 4. The gate

`integration/gate.py` is the only path from a model answer to an action:

| Command | What it does |
|---|---|
| `lead-request --features f.json` | Validates a lead record against the categories the model was trained on and prints the exact `decide` request. Exit code 2 means a value is outside those categories: research the lead instead of calling the model. |
| `reply-request --reply-text "..."` | Prints the exact `decide` request for a reply. |
| `lead --domain d --answers a.json ...` | Applies the outreach policy (suppression, persona fit, eligibility, ICP fit) and appends one queue entry per domain. |
| `reply --reply-text "..." --answers a.json ...` | Applies the routing policy. An explicit opt-out phrase in the text always suppresses marketing, whatever the model answered. |

Every result carries `"send": false`. A person reviews `outputs/approval-queue.jsonl`.

## 5. The recorded case study

`case_study_prompt.md` is the prompt of the recorded session. It ran headless:

```bash
claude -p "$(cat integration/case_study_prompt.md)" --mcp-config .mcp.json --output-format stream-json --verbose > outputs/case-study-session.jsonl
```

The lead model learned from synthetic LeadForge records. Its answers about real companies demonstrate the integration; they are not validated predictions.
