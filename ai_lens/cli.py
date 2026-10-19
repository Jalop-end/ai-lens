"""CLI interface for AI Lens using Typer with direct language shortcut support (e.g. `ai-lens cs`, `ai-lens en`)."""

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
)
from ai_lens.vision_engine import (
    SUPPORTED_LANGUAGES,
    get_language_display,
    is_recognized_language_arg,
    normalize_language_code,
)

_ensure_utf8_stdio()


def _normalize_cli_argv() -> None:
    """
    Allows launching AI Lens directly with a language code as the first argument,
    e.g. `ai-lens cs`, `ai-lens en`, `ai-lens de`, `ai-lens sk`, `ai-lens es`, etc.,
    by rewriting `sys.argv[1:2]` to `["start", sys.argv[1]]` before Typer parses args.
    """
    if len(sys.argv) > 1 and is_recognized_language_arg(sys.argv[1]):
        sys.argv[1:2] = ["start", sys.argv[1]]


_normalize_cli_argv()

app = typer.Typer(
    name="ai-lens",
    help=(
        "AI Lens - 100% offline lokální VLM asistent s okamžitým výřezem obrazovky.\n\n"
        "Rychlé spuštění s volbou jazyka: `ai-lens cs` (čeština), `ai-lens en` (angličtina), "
        "`ai-lens de` (němčina), `ai-lens sk` (slovenština), `ai-lens es`, `ai-lens fr`, `ai-lens pl`, `ai-lens uk`…"
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
        help="Zkratka jazyka odpovědí (např. cs, en, sk, de, es, fr, pl, uk, it, pt, ru, nl, zh, ja, ko).",
    ),
) -> None:
    """
    Spustí AI Lens z příkazové řádky v pohotovosti (poslouchá na Alt+F8 / F8).
    """
    if ctx.invoked_subcommand is None:
        run_daemon(open_immediately=False, language=lang)


@app.command("start")
def start(
    language: Optional[str] = typer.Argument(
        None,
        help="Volitelná zkratka jazyka (např. cs, en, sk, de, es, fr, pl, uk, it, pt, ru, nl, zh, ja, ko).",
    ),
    lang: Optional[str] = typer.Option(
        None,
        "--lang",
        "-l",
        help="Nastaví jazyk odpovědí (např. cs, en, de, sk).",
    ),
    now: bool = typer.Option(
        False,
        "--now",
        "-n",
        help="Otevře překryvný overlay rovnou při startu a poté zůstane v pohotovosti.",
    ),
) -> None:
    """Spustí aplikaci z CLI s volitelnou zkratkou jazyka (např. `ai-lens cs` nebo `ai-lens en`)."""
    chosen_lang = lang or language
    run_daemon(open_immediately=now, language=chosen_lang)


@app.command("trigger")
def trigger(
    language: Optional[str] = typer.Argument(
        None,
        help="Volitelná zkratka jazyka (např. cs, en, sk, de, es, fr, pl, uk).",
    ),
    lang: Optional[str] = typer.Option(
        None,
        "--lang",
        "-l",
        help="Nastaví jazyk odpovědí pro tento i další výběry.",
    ),
) -> None:
    """Okamžitě vyfotí obrazovku do RAM a otevře fullscreen overlay."""
    chosen_lang = lang or language
    if chosen_lang:
        code = set_language_in_config(chosen_lang)
        typer.echo(f"[AI Lens] Jazyk odpovědí nastaven na: {get_language_display(code)}")

    resp = send_daemon_command("TRIGGER")
    if resp == "OK:TRIGGERED":
        typer.echo("[AI Lens] Signál odeslán běžící instanci -> overlay aktivován.")
    else:
        run_overlay_mvp(language=chosen_lang)


@app.command("status")
def status() -> None:
    """Zkontroluje, zda běží AI Lens proces."""
    resp = send_daemon_command("STATUS")
    cfg = load_config()
    lang_disp = get_language_display(str(cfg.get("language", "cs")))
    if resp == "OK:RUNNING":
        typer.echo(
            f"[AI Lens] Proces BĚŽÍ (zkratka: {cfg.get('hotkey')} / F8, model: {cfg.get('model')}, jazyk: {lang_disp})."
        )
    else:
        typer.echo(
            f"[AI Lens] Proces momentálně neběží (nastavený jazyk: {lang_disp}). Spusť jej příkazem: ai-lens cs (nebo .\\ai-lens.bat)"
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
    typer.echo("Podporované zkratky jazyků (použití: `ai-lens <zkratka>`, např. `ai-lens cs` nebo `ai-lens en`):")
    for code, (en_name, native_name) in SUPPORTED_LANGUAGES.items():
        marker = "* " if code == current else "  "
        typer.echo(f"{marker}{code:<4} - {native_name} ({en_name})")


@app.command("config")
def config_cmd(
    lang: Optional[str] = typer.Option(
        None,
        "--lang",
        "-l",
        help="Nastaví jazyk odpovědí (cs, en, sk, de, es, fr, pl, uk, it, pt, ru, nl, zh, ja, ko)",
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

    if updated or lang is not None:
        typer.echo("[AI Lens] Konfigurace uložena do config.json:")

    typer.echo(json.dumps(cfg, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
