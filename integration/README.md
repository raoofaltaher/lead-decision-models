# Integration: Claude Code and the decision models

Part 3 of the tutorial. Claude Code researches prospects with Firecrawl and hands two bounded decisions to the fine-tuned models, served by a small MCP server in this repository. A deterministic gate turns every decision into a queue entry for a person to approve. Nothing here can send a message.

## 1. Why not Unsloth Studio's Decision API

Unsloth Studio 2026.10.11 serves decision models through its Decision API and an MCP endpoint, but it cannot load LFM3. Its runtime loads a model without `trust_remote_code`, and its own environment pins transformers 5.5.0, below the 5.22.1 that LFM3's code needs. The fix, [unslothai/unsloth#16096](https://github.com/unslothai/unsloth/pull/16096), is merged on `main` and waits for a release ([#15588](https://github.com/unslothai/unsloth/issues/15588)). Until then, `integration/decision_server.py` exposes the same `decide` tool with the same request shape and the same limits.

## 2. The decision server

Both notebooks must have run, so that `outputs/lead-decision-merged/` and `outputs/reply-decision-merged/` exist. `decision_server.py` serves one merged folder over stdio:

- It loads the model on the first `decide` call, with `trust_remote_code=True` in 4-bit, the same call the notebooks use to reload it. On the test machine the first call takes about half a minute.
- It serves only a local folder that holds a `config.json`. The LFM3 code in that folder is the code of the pinned revision that the notebooks downloaded.
- It refuses every request that Studio's Decision API refuses, with Studio's messages, before the model runs.
- Unsloth's console output goes to stderr, so it cannot break the MCP stream.

Claude Code starts one server process per model. Nothing listens on a network port.

## 3. Connect Claude Code

`.mcp.json` in the repository root registers three servers:

| Server | Transport | What it runs |
|---|---|---|
| `lead-decisions` | stdio | `decision_server.py` on `outputs/lead-decision-merged` |
| `reply-decisions` | stdio | `decision_server.py` on `outputs/reply-decision-merged` |
| `firecrawl` | HTTP with OAuth | Firecrawl's hosted MCP server |

Start `claude` in the repository folder. Approve the three project servers when Claude Code asks, then run `/mcp` and sign in to Firecrawl in the browser. Check the result:

```bash
claude mcp list
```

## 4. The gate

`integration/gate.py` is the only path from a model answer to an action:

| Command | What it does |
|---|---|
| `lead-request --features f.json` | Validates a lead record against the categories the model was trained on and prints the exact `decide` request. Exit code 2 means a field is missing or a value is outside those categories: research the lead instead of calling the model. |
| `reply-request --reply-text "..."` | Prints the exact `decide` request for a reply. |
| `lead --domain d --answers a.json ...` | Applies the outreach policy (suppression, persona fit, eligibility, ICP fit) and appends one queue entry per domain. |
| `reply --reply-text "..." --answers a.json ...` | Applies the routing policy. An explicit opt-out phrase in the text always suppresses marketing, whatever the model answered. |

Every result carries `"send": false`. A person reviews `outputs/approval-queue.jsonl`.

## 5. The recorded case study

`case_study_prompt.md` is the prompt of the recorded session. `record_case_study.sh` runs it headless and renders the result:

```bash
./integration/record_case_study.sh
```

The script loads only the three servers of `.mcp.json` (`--strict-mcp-config`) and no user settings (`--setting-sources project`), and it allows only the Firecrawl search and scrape tools, the two `decide` tools, the gate command, writes under `outputs/case-study/` and reads of the case-study files. In its default permission mode Claude Code also runs read-only commands and file reads inside the repository without a rule; both recordings show `ls`, `cat`, `grep` and a `Read` of `integration/gate.py`. It refuses every other write and command, and the transcript shows each refusal. The raw stream stays in `outputs/logs/`; `tools/render_session.py` writes `outputs/case-study-session.jsonl` and `.md`, which keep only known-safe fields and cut scraped page text to 600 characters. `tools/serving_check.py` then times both servers over MCP stdio and checks their answers against the session (`outputs/serving-check.json`).

The first recording, in `outputs/case-study-first-run/`, found that the lead model answered `fit` for companies with missing fields. The gate now refuses such records, and `outputs/case-study-session.md` is the recording after that fix.

The lead model learned from synthetic LeadForge records. Its answers about real companies demonstrate the integration; they are not validated predictions.
