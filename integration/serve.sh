#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source unsloth_env/bin/activate
mkdir -p outputs/logs

UNSLOTH_STUDIO_HOME="$HOME/.studio-lead" \
UNSLOTH_SYSTEMONE_MODEL="$PWD/outputs/lead-decision-merged" \
  nohup unsloth studio -p 8888 > outputs/logs/studio-lead.log 2>&1 &
echo $! > outputs/logs/studio-lead.pid

UNSLOTH_STUDIO_HOME="$HOME/.studio-reply" \
UNSLOTH_SYSTEMONE_MODEL="$PWD/outputs/reply-decision-merged" \
  nohup unsloth studio -p 8889 > outputs/logs/studio-reply.log 2>&1 &
echo $! > outputs/logs/studio-reply.pid

echo "Lead model:  http://127.0.0.1:8888  Decision API /v1/systemone, MCP /mcp/decisions/"
echo "Reply model: http://127.0.0.1:8889  Decision API /v1/systemone, MCP /mcp/decisions/"
