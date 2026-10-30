#!/usr/bin/env bash
# AI Lens Universal 'start' Launcher for macOS and Linux
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AI_LENS="${SCRIPT_DIR}/ai-lens"
if [ ! -f "$AI_LENS" ]; then
    AI_LENS="${SCRIPT_DIR}/ai-lens.sh"
fi

first_arg="$(echo "$1" | tr '[:upper:]' '[:lower:]')"
case "$first_arg" in
    status|stop|diag|diagnostika|diagnostics|languages|levels|secret)
        exec "$AI_LENS" "$@"
        ;;
    *)
        exec "$AI_LENS" start "$@"
        ;;
esac

