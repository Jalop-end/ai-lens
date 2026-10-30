#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PATH="${SCRIPT_DIR}:${SCRIPT_DIR}/scripts/mac:${PATH}"
alias ai-lens="'${SCRIPT_DIR}/ai-lens.sh'"
alias start="'${SCRIPT_DIR}/start.sh'"
alias gemini="'${SCRIPT_DIR}/ai-lens.sh' start with Gemini"

