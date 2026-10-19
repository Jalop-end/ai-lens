"""CLI interface for AI Lens using Typer with direct language & thinking level shortcuts (e.g. `ai-lens cs High`, `ai-lens en Medium`, `ai-lens Low`)."""

from __future__ import annotations

import json
import sys
from typing import Optional

import typer

from ai_lens.daemon import run_daemon, send_daemon_command
from ai_lens.overlay import (
    DEFAULT_CONFIG_PATH,
    _ensure_utf8_stdio,
    load_config,
    run_overlay_mvp,
    set_language_in_config,
    set_thinking_level_in_config,
)
from ai_lens.vision_engine import (
    SUPPORTED_LANGUAGES,
    THINKING_LEVELS,
    get_language_display,
    get_thinking_level_config,
    get_thinking_level_display,
    is_recognized_language_arg,
    is_recognized_thinking_level,
    normalize_language_code,
    normalize_thinking_level,
)

_ensure_utf8_stdio()


def _normalize_cli_argv() -> None:
    """
    Allows launching AI Lens directly with a language code and/or thinking level
    as positional arguments right after `ai-lens`:
      - `ai-lens cs`
      - `ai-lens en High`
      - `ai-lens High`
      - `ai-lens Medium cs`
    by inserting `"start"` at `sys.argv[1]` before Typer parses commands.
    """
    if len(sys.argv) > 1:
        first = sys.argv[1]
        if is_recognized_language_arg(first) or is_recognized_thinking_level(first):
            sys.argv[1:1] = ["start"]


def _resolve_lang_and_level(
    arg1: Optional[str],
    arg2: Optional[str],
    opt_lang: Optional[str],
    opt_level: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """
    Resolves `(language, thinking_level)` from up to two flexible positional arguments
    (in any order, e.g. `cs High` or `High cs`) combined with `--lang` and `--level` options.
    """
    detected_lang: Optional[str] = opt_lang
    detected_level: Optional[str] = opt_level

    for raw in (arg1, arg2):
        if not raw:
            continue
        if is_recognized_thinking_level(raw) and detected_level is None:
            detected_level = normalize_thinking_level(raw)
        elif is_recognized_language_arg(raw) and detected_lang is None:
            detected_lang = normalize_language_code(raw)
        elif detected_lang is None:
            detected_lang = normalize_language_code(raw)

    return detected_lang, detected_level


_normalize_cli_argv()

app = typer.Typer(
    name="ai-lens",
    help=(
        "AI Lens - 100% offline lokální VLM asistent s okamžitým výřezem obrazovky.\n\n"
        "Rychlé spuštění s volbou jazyka a hloubky myšlení (Low / Medium / High):\n"
        "  `ai-lens cs High`   |   `ai-lens en Medium`   |   `ai-lens Low`"
    ),
    add_completion=False,
    invoke_without_command=True,
)


@app.callback()
def main(
    ctx: typer.Context,
    lang: Optional[str] = typer.Option(
        None,
        "--lang",
        "-l",
        help="Zkratka jazyka (cs, en, sk, de, es, fr, pl, uk, it, pt, ru, nl, zh, ja, ko).",
    ),
    level: Optional[str] = typer.Option(
        None,
        "--level",
        "-q",
        help="Hloubka myšlení a kvalita odpovědi: Low, Medium, nebo High.",
    ),
) -> None:
    """
    Spustí AI Lens z příkazové řádky v pohotovosti (poslouchá na Alt+F8 / F8).
    """
    if ctx.invoked_subcommand is None:
        run_daemon(open_immediately=False, language=lang, thinking_level=level)


@app.command("start")
def start(
    arg1: Optional[str] = typer.Argument(
        None,
        help="Volitelná zkratka jazyka (např. cs, en, de, sk) nebo úroveň myšlení (Low, Medium, High).",
    ),
    arg2: Optional[str] = typer.Argument(
        None,
        help="Volitelný druhý parametr – úroveň myšlení (Low, Medium, High) nebo jazyk (např. `ai-lens cs High`).",
    ),
    lang: Optional[str] = typer.Option(
        None,
        "--lang",
        "-l",
        help="Nastaví jazyk odpovědí i UI (např. cs, en, de, sk).",
    ),
    level: Optional[str] = typer.Option(
        None,
        "--level",
        "-q",
        help="Nastaví hloubku myšlení a počet tokenů: Low, Medium, nebo High.",
    ),
    now: bool = typer.Option(
        False,
        "--now",
        "-n",
        help="Otevře překryvný overlay rovnou při startu a poté zůstane v pohotovosti.",
    ),
) -> None:
    """Spustí aplikaci s volitelnou zkratkou jazyka a hloubkou myšlení (např. `ai-lens cs High` nebo `ai-lens en Low`)."""
    chosen_lang, chosen_level = _resolve_lang_and_level(arg1, arg2, lang, level)
    run_daemon(open_immediately=now, language=chosen_lang, thinking_level=chosen_level)


@app.command("trigger")
def trigger(
    arg1: Optional[str] = typer.Argument(
        None,
        help="Volitelná zkratka jazyka (cs, en, de...) nebo úroveň myšlení (Low, Medium, High).",
    ),
    arg2: Optional[str] = typer.Argument(
        None,
        help="Volitelná úroveň myšlení (Low, Medium, High) nebo jazyk.",
    ),
    lang: Optional[str] = typer.Option(
        None,
        "--lang",
        "-l",
        help="Nastaví jazyk odpovědí i UI.",
    ),
    level: Optional[str] = typer.Option(
        None,
        "--level",
        "-q",
        help="Nastaví hloubku myšlení: Low, Medium, nebo High.",
    ),
) -> None:
    """Okamžitě vyfotí obrazovku do RAM a otevře fullscreen overlay."""
    chosen_lang, chosen_level = _resolve_lang_and_level(arg1, arg2, lang, level)
    if chosen_lang:
        code = set_language_in_config(chosen_lang)
        typer.echo(f"[AI Lens] Jazyk (UI + AI) nastaven na: {get_language_display(code)}")
    if chosen_level:
        lvl = set_thinking_level_in_config(chosen_level)
        cfg_lang = str(load_config().get("language", "cs"))
        typer.echo(
            f"[AI Lens] Hloubka myšlení nastavena na: {get_thinking_level_display(lvl, cfg_lang)}"
        )

    resp = send_daemon_command("TRIGGER")
    if resp == "OK:TRIGGERED":
        typer.echo("[AI Lens] Signál odeslán běžící instanci -> overlay aktivován.")
    else:
        run_overlay_mvp(language=chosen_lang, thinking_level=chosen_level)


@app.command("status")
def status() -> None:
    """Zkontroluje, zda běží AI Lens proces, a vypíše aktivní jazyk i úroveň myšlení."""
    resp = send_daemon_command("STATUS")
    cfg = load_config()
    lang_code = str(cfg.get("language", "cs"))
    lang_disp = get_language_display(lang_code)
    level_code = str(cfg.get("thinking_level", "medium"))
    level_disp = get_thinking_level_display(level_code, lang_code)
    tier_cfg = get_thinking_level_config(level_code)
    if resp == "OK:RUNNING":
        typer.echo(
            f"[AI Lens] Proces BĚŽÍ (zkratka: {cfg.get('hotkey')} / F8, model: {cfg.get('model')}, "
            f"jazyk: {lang_disp}, myšlení: {level_disp} [{tier_cfg['num_predict']} tokenů])."
        )
    else:
        typer.echo(
            f"[AI Lens] Proces momentálně neběží (jazyk: {lang_disp}, myšlení: {level_disp} [{tier_cfg['num_predict']} tokenů]). "
            "Spusť jej např. příkazem: ai-lens cs High"
        )


@app.command("stop")
def stop() -> None:
    """Zastaví běžící AI Lens proces."""
    resp = send_daemon_command("STOP")
    if resp == "OK:STOPPING":
        typer.echo("[AI Lens] Proces byl úspěšně zastaven.")
    else:
        typer.echo("[AI Lens] Žádný běžící proces nebyl nalezen.")


@app.command("languages")
def languages_cmd() -> None:
    """Vypíše seznam podporovaných zkratek jazyků pro spuštění z terminálu."""
    cfg = load_config()
    current = normalize_language_code(str(cfg.get("language", "cs")))
    typer.echo(
        "Podporované zkratky jazyků (použití: `ai-lens <jazyk> [Low|Medium|High]`, např. `ai-lens cs High` nebo `ai-lens en Medium`):"
    )
    for code, (en_name, native_name) in SUPPORTED_LANGUAGES.items():
        marker = "* " if code == current else "  "
        typer.echo(f"{marker}{code:<4} - {native_name} ({en_name})")


@app.command("levels")
def levels_cmd() -> None:
    """Vypíše úrovně hloubky myšlení (Low, Medium, High), jejich počet tokenů a nároky."""
    cfg = load_config()
    current = normalize_thinking_level(str(cfg.get("thinking_level", "medium")))
    typer.echo(
        "Úrovně hloubky myšlení a kvality odpovědi (použití: `ai-lens <jazyk> <Low|Medium|High>`, např. `ai-lens cs High`):"
    )
    for key, info in THINKING_LEVELS.items():
        marker = "* " if key == current else "  "
        typer.echo(
            f"{marker}{info['label']:<7} | max tokenů: {info['num_predict']:<4} | kontext: {info['num_ctx']:<4} "
            f"| rozlišení: {info['max_image_side']}px | {info['desc_cs']}"
        )


@app.command("config")
def config_cmd(
    lang: Optional[str] = typer.Option(
        None,
        "--lang",
        "-l",
        help="Nastaví jazyk odpovědí i UI (cs, en, sk, de, es, fr, pl, uk, it, pt, ru, nl, zh, ja, ko)",
    ),
    level: Optional[str] = typer.Option(
        None,
        "--level",
        "-q",
        help="Nastaví hloubku myšlení: Low, Medium, nebo High",
    ),
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="Nastaví lokální VLM model (např. gemma4:latest, qwen2.5vl:3b)"
    ),
    hotkey: Optional[str] = typer.Option(
        None, "--hotkey", "-k", help="Nastaví globální zkratku (např. <alt>+<f8>)"
    ),
    padding: Optional[int] = typer.Option(
        None, "--padding", "-p", help="Padding Bounding Boxu v pixelech"
    ),
) -> None:
    """Vypíše nebo upraví konfiguraci v config.json."""
    if lang is not None:
        set_language_in_config(lang)
    if level is not None:
        set_thinking_level_in_config(level)

    cfg = load_config()
    updated = False
    if model is not None:
        cfg["model"] = model
        updated = True
    if hotkey is not None:
        cfg["hotkey"] = hotkey
        updated = True
    if padding is not None:
        cfg["padding"] = padding
        updated = True

    if updated:
        with open(DEFAULT_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

    if updated or lang is not None or level is not None:
        typer.echo("[AI Lens] Konfigurace uložena do config.json:")

    typer.echo(json.dumps(cfg, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
