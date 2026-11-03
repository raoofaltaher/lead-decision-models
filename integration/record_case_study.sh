#!/usr/bin/env bash
set -uo pipefail
export PATH="${HOME}/.local/bin:${PATH}"
command -v claude > /dev/null || { echo "claude is not on PATH"; exit 127; }
cd "$(dirname "$0")/.."
source unsloth_env/bin/activate
mkdir -p outputs/case-study outputs/logs
rm -f outputs/approval-queue.jsonl
start=$(date +%s)
claude -p "$(cat integration/case_study_prompt.md)" \
  --mcp-config .mcp.json \
  --strict-mcp-config \
  --setting-sources project \
  --allowedTools \
    "mcp__firecrawl__firecrawl_search" \
    "mcp__firecrawl__firecrawl_scrape" \
    "mcp__lead-decisions__decide" \
    "mcp__reply-decisions__decide" \
    "Bash(python integration/gate.py *)" \
    "Edit(outputs/case-study/**)" \
    "Read(data/case-study/**)" \
    "Read(outputs/case-study/**)" \
  --output-format stream-json \
  --verbose \
  > outputs/logs/case-study-session.raw.jsonl 2> outputs/logs/case-study.err
status=$?
end=$(date +%s)
echo "claude exit=${status} seconds=$((end - start))"
python tools/render_session.py \
  --raw outputs/logs/case-study-session.raw.jsonl \
  --prompt integration/case_study_prompt.md \
  --queue outputs/approval-queue.jsonl \
  --out-jsonl outputs/case-study-session.jsonl \
  --out-md outputs/case-study-session.md
