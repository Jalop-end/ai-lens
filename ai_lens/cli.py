"""CLI interface for AI Lens using Typer."""

from __future__ import annotations

import json
from typing import Optional

import typer

from ai_lens.daemon import run_daemon, send_daemon_command
from ai_lens.overlay import DEFAULT_CONFIG_PATH, _ensure_utf8_stdio, load_config, run_overlay_mvp

_ensure_utf8_stdio()

app = typer.Typer(
    name="ai-lens",
    help="AI Lens - 100% offline lokální VLM asistent s okamžitým výřezem obrazovky.",
    add_completion=False,
    invoke_without_command=True,
)


@app.callback()
def main(ctx: typer.Context) -> None:
    """
    Spustí AI Lens z příkazové řádky v pohotovosti a poslouchá na zkratce
    Ctrl+Alt+Shift+G (nebo záložní klávese F8).
    """
    if ctx.invoked_subcommand is None:
        run_daemon(open_immediately=False)


@app.command("start")
def start(
    now: bool = typer.Option(
        False,
        "--now",
        "-n",
        help="Otevře překryvný overlay rovnou při startu a poté zůstane v pohotovosti.",
    ),
) -> None:
    """Spustí aplikaci z CLI (poslouchá na Ctrl+Alt+Shift+G a F8 bez síťových portů)."""
    run_daemon(open_immediately=now)


@app.command("trigger")
def trigger() -> None:
    """Okamžitě vyfotí obrazovku do RAM a otevře fullscreen overlay."""
    resp = send_daemon_command("TRIGGER")
    if resp == "OK:TRIGGERED":
        typer.echo("[AI Lens] Signál odeslán běžící instanci -> overlay aktivován.")
    else:
        run_overlay_mvp()


@app.command("status")
def status() -> None:
    """Zkontroluje, zda běží AI Lens proces."""
    resp = send_daemon_command("STATUS")
    if resp == "OK:RUNNING":
        cfg = load_config()
        typer.echo(
            f"[AI Lens] Proces BĚŽÍ (zkratka: {cfg.get('hotkey')} / F8, model: {cfg.get('model')})."
        )
    else:
        typer.echo("[AI Lens] Proces momentálně neběží. Spusť jej příkazem: .\\ai-lens.bat")


@app.command("stop")
def stop() -> None:
    """Zastaví běžící AI Lens proces."""
    resp = send_daemon_command("STOP")
    if resp == "OK:STOPPING":
        typer.echo("[AI Lens] Proces byl úspěšně zastaven.")
    else:
        typer.echo("[AI Lens] Žádný běžící proces nebyl nalezen.")


@app.command("config")
def config_cmd(
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="Nastaví lokální VLM model (např. gemma4:latest, qwen2.5vl:3b)"
    ),
    hotkey: Optional[str] = typer.Option(
        None, "--hotkey", "-k", help="Nastaví globální zkratku (např. <ctrl>+<alt>+<shift>+g)"
    ),
    padding: Optional[int] = typer.Option(
        None, "--padding", "-p", help="Padding Bounding Boxu v pixelech"
    ),
) -> None:
    """Vypíše nebo upraví konfiguraci v config.json."""
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
        typer.echo("[AI Lens] Konfigurace uložena do config.json:")

    typer.echo(json.dumps(cfg, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
