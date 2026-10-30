#!/usr/bin/env bash
# AI Lens - Google Gemini API launcher for macOS and Linux
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI_LENS="${SCRIPT_DIR}/ai-lens"
if [ ! -f "$AI_LENS" ]; then
    AI_LENS="${SCRIPT_DIR}/ai-lens.sh"
fi
exec "$AI_LENS" start with Gemini "$@"

