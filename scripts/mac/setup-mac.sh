#!/usr/bin/env bash
# setup-mac.sh
# Konfigurace a podpora příkazů AI Lens pro macOS (Terminal.app, iTerm2, zsh, bash):
#   ai-lens start with Gemini
#   start with Gemini
#   ai-lens cs High
#   ai-lens secret
#   ai-lens diag
#   ai-lens status
#   ai-lens stop

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AI_LENS_BIN="${SCRIPT_DIR}/ai-lens.sh"
START_BIN="${SCRIPT_DIR}/start.sh"

# Nastavení spustitelných práv na kořenové i podsložkové skripty
chmod +x "${SCRIPT_DIR}"/*.sh "${SCRIPT_DIR}/ai-lens" "${SCRIPT_DIR}/start" 2>/dev/null || true
chmod +x "${SCRIPT_DIR}/scripts/mac"/*.sh 2>/dev/null || true

# Dočasné aliasy pro aktuální shell session
alias ai-lens="'${AI_LENS_BIN}'"
alias start="'${START_BIN}'"
alias gemini="'${AI_LENS_BIN}' start with Gemini"

HOOK_TAG="# AI Lens macOS Command Support"
HOOK_BODY="
$HOOK_TAG
export PATH=\"${SCRIPT_DIR}:${SCRIPT_DIR}/scripts/mac:\$PATH\"
alias ai-lens='${AI_LENS_BIN}'
alias start='${START_BIN}'
alias gemini='${AI_LENS_BIN} start with Gemini'
"

# Automatická integrace do profilů macOS uživatele (~/.zshrc je výchozí na macOS od verze 10.15 Catalina)
TARGET_CONFIGS=("${HOME}/.zshrc" "${HOME}/.bash_profile" "${HOME}/.bashrc")

for cfg in "${TARGET_CONFIGS[@]}"; do
    fname="$(basename "$cfg")"
    if [ -f "$cfg" ] || [ "$fname" = ".zshrc" ]; then
        if [ ! -f "$cfg" ]; then
            touch "$cfg"
        fi
        if ! grep -q "$HOOK_TAG" "$cfg" 2>/dev/null; then
            echo "$HOOK_BODY" >> "$cfg"
            echo "[AI Lens] ✓ Příkazy 'ai-lens' a 'start with Gemini' byly automaticky aktivovány v ~/${fname}."
        fi
    fi
done

echo ""
echo "=========================================================================="
echo "  AI LENS — PODPORA PRO MACOS BYLA ÚSPĚŠNĚ NASTAVENA"
echo "=========================================================================="
echo "  Odteď můžete v terminálu macOS používat příkazy přímo odkudkoliv:"
echo "    ./ai-lens.sh start with Gemini   (nebo: ai-lens start with Gemini)"
echo "    ./ai-lens.sh cs High             (nebo: ai-lens cs High)"
echo "    ./ai-lens.sh secret              (nebo: ai-lens secret)"
echo "    ./ai-lens.sh diag                (nebo: ai-lens diag)"
echo "    ./ai-lens.sh status              (nebo: ai-lens status)"
echo "    ./ai-lens.sh stop                (nebo: ai-lens stop)"
echo "=========================================================================="

