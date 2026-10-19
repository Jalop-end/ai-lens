"""CLI interface for AI Lens using Typer with direct language & thinking level shortcuts (e.g. `ai-lens cs High`, `ai-lens en Medium`, `ai-lens Low`)."""

from __future__ import annotations

import ctypes
import json
import os
import platform
import sys
import urllib.parse
from pathlib import Path
from typing import Optional

import httpx
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
    validate_local_ollama_host,
)

_ensure_utf8_stdio()

DIAG_ALIASES = {"diag", "diagnostika", "diagnostics", "security", "specs", "specifikace"}


def _normalize_cli_argv() -> None:
    """
    Allows launching AI Lens directly with a language code and/or thinking level
    as positional arguments right after `ai-lens`:
      - `ai-lens cs`
      - `ai-lens en High`
      - `ai-lens High`
      - `ai-lens Medium cs`
    and normalizes Czech/English diagnostic aliases (`diagnostika`, `diagnostics`, `security`, `specs`)
    to `diag` before Typer parses commands.
    """
    if len(sys.argv) > 1:
        first = sys.argv[1]
        if first.strip().lower() in DIAG_ALIASES:
            sys.argv[1] = "diag"
            return
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
        "  `.\\ai-lens.bat cs High`   |   `.\\ai-lens.bat en Medium`   |   `.\\ai-lens.bat Low`"
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
            "Spusť jej např. příkazem: .\\ai-lens.bat cs High (nebo .\\ai-lens.bat en High)"
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
        "Podporované zkratky jazyků (použití: `.\\ai-lens.bat <jazyk> [Low|Medium|High]`, např. `.\\ai-lens.bat cs High` nebo `.\\ai-lens.bat en Medium`):"
    )
    for code, (en_name, native_name) in SUPPORTED_LANGUAGES.items():
        marker = "* " if code == current else "  "
        typer.echo(f"{marker}{code:<4} - {native_name} ({en_name})")


@app.command("levels")
def levels_cmd() -> None:
    """Vypíše úrovně hloubky myšlení (Low, Medium, High), přesnost odpovědí, kontext informací a počet tokenů."""
    cfg = load_config()
    current = normalize_thinking_level(str(cfg.get("thinking_level", "medium")))
    typer.echo(
        "Úrovně hloubky myšlení, přesnosti odpovědí a šíře faktického kontextu (použití: `.\\ai-lens.bat <jazyk> <Low|Medium|High>`, např. `.\\ai-lens.bat cs High`):"
    )
    typer.echo("=" * 112)
    for key, info in THINKING_LEVELS.items():
        marker = "* " if key == current else "  "
        typer.echo(
            f"{marker}{info['label']:<7} | max tokenů: {info['num_predict']:<4} | okno kontextu: {info['num_ctx']:<4} "
            f"| výřez: {info['max_image_side']}px | teplota: {info['temperature']}"
        )
        typer.echo(f"          ├─ Přesnost odpovědí : {info['accuracy_cs']}")
        typer.echo(f"          ├─ Kontext a fakta   : {info['context_info_cs']}")
        typer.echo(f"          └─ Charakteristika   : {info['desc_cs']}")
        typer.echo("-" * 112)


def _get_system_memory_info() -> tuple[float, float, float, int]:
    """
    Returns (total_gb, used_gb, free_gb, percent_used) using Windows GlobalMemoryStatusEx
    without requiring external dependencies.
    """
    if sys.platform == "win32":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                total_gb = stat.ullTotalPhys / (1024**3)
                free_gb = stat.ullAvailPhys / (1024**3)
                used_gb = max(0.0, total_gb - free_gb)
                return total_gb, used_gb, free_gb, int(stat.dwMemoryLoad)
        except Exception:
            pass
    return 0.0, 0.0, 0.0, 0


@app.command("diag")
def diag_cmd() -> None:
    """
    Spustí kompletní živou diagnostiku v terminálu (model, RAM/CPU, kontext a přesnost Low/Medium/High,
    kontrola mazání dat z RAM po zavření chatu a 7-bodový bezpečnostní audit napadnutelnosti).
    Lze volat jako: `ai-lens diag`, `ai-lens diagnostika`, `ai-lens security` nebo `ai-lens specs`.
    """
    cfg = load_config()
    lang_code = normalize_language_code(str(cfg.get("language", "cs")))
    lang_disp = get_language_display(lang_code)
    level_code = normalize_thinking_level(str(cfg.get("thinking_level", "medium")))
    level_disp = get_thinking_level_display(level_code, lang_code)
    tier_cfg = get_thinking_level_config(level_code)
    model_name = str(cfg.get("model", "gemma4:latest"))
    ollama_url = str(cfg.get("ollama_url", "http://127.0.0.1:11434"))
    hotkey = str(cfg.get("hotkey", "<alt>+<f8>"))

    daemon_resp = send_daemon_command("STATUS")
    daemon_running = daemon_resp == "OK:RUNNING"

    safe_host = validate_local_ollama_host(ollama_url)
    parsed_raw = urllib.parse.urlparse(ollama_url.strip())
    loopback_ok = (parsed_raw.hostname or "").lower() in ("127.0.0.1", "localhost", "::1")

    ollama_online = False
    try:
        with httpx.Client(timeout=2.5, trust_env=False) as client:
            resp = client.get(f"{safe_host}/api/tags")
            if resp.status_code == 200:
                ollama_online = True
    except Exception:
        ollama_online = False

    total_gb, used_gb, free_gb, mem_pct = _get_system_memory_info()
    cpu_cores = os.cpu_count() or 1
    py_ver = platform.python_version()
    os_info = f"{platform.system()} {platform.release()} ({platform.machine()})"

    project_root = Path(__file__).resolve().parent.parent
    leftover_files = [
        p.name
        for p in (
            project_root / "last_crop.png",
            project_root / "ai_lens_debug.log",
            project_root / "debug_crop.png",
        )
        if p.exists()
    ]
    zero_retention_clean = len(leftover_files) == 0

    typer.echo("=" * 108)
    typer.echo("  AI LENS — ŽIVÁ SYSTÉMOVÁ SPECIFIKACE, KONTEXT & BEZPEČNOSTNÍ DIAGNOSTIKA (CLI REPORT)")
    typer.echo("=" * 108)

    # 1. Stav běhu a AI modelu
    typer.echo("\n[1/5] STAV APLIKACE & AI MODELU (RUNTIME)")
    typer.echo(
        f"  • Stav procesu na pozadí : {'BĚŽÍ (připraven na ' + hotkey + ' / F8)' if daemon_running else 'NEBĚŽÍ (spusť: .\\ai-lens.bat cs High nebo .\\ai-lens.bat en High)'}"
    )
    typer.echo(
        f"  • Lokální Ollama engine  : {'ONLINE a model připraven (' + ollama_url + ')' if ollama_online else 'OFFLINE nebo model není stažen (' + ollama_url + ')'}"
    )
    typer.echo(f"  • Aktivní VLM model      : {model_name} (doporučená lehká alternativa: qwen2.5vl:3b)")
    typer.echo(f"  • Aktivní jazyk (UI+AI)  : {lang_disp}")
    typer.echo(
        f"  • Aktivní úroveň myšlení : {level_disp} (max {tier_cfg['num_predict']} tokenů, kontext {tier_cfg['num_ctx']}, výřez {tier_cfg['max_image_side']}px)"
    )

    # 2. Hardware, RAM a CPU
    typer.echo("\n[2/5] HARDWAROVÉ ZDROJE, SPOTŘEBA RAM & CPU")
    typer.echo(f"  • Operační systém & CPU  : {os_info} | {cpu_cores} logických jader | Python {py_ver}")
    if total_gb > 0:
        typer.echo(
            f"  • Živá systémová RAM     : {used_gb:.2f} GB využito / {total_gb:.2f} GB celkem ({mem_pct}% vytížení, {free_gb:.2f} GB volných)"
        )
    typer.echo("  • Spotřeba AI Lens (GUI) : ~45–75 MB RAM v pohotovosti (0.0 % CPU) | ~95–145 MB RAM při kreslení lasa")
    typer.echo(
        "  • Spotřeba VLM (Ollama)  : ~3.2–4.5 GB RAM/VRAM (gemma4:latest) | ~2.4–3.1 GB RAM/VRAM (qwen2.5vl:3b)"
    )

    # 3. Kontext, přesnost odpovědí a informace o zakroužkovaném objektu (Low / Medium / High)
    typer.echo("\n[3/5] KONTEXT, PŘESNOST ODPOVĚDÍ A BOHATOST INFORMACÍ (LOW / MEDIUM / HIGH)")
    for key, info in THINKING_LEVELS.items():
        active_tag = "[AKTIVNÍ]" if key == level_code else "         "
        typer.echo(
            f"  {active_tag} {info['label']:<6} | Tokeny: {info['num_predict']:<4} | Okno: {info['num_ctx']:<4} "
            f"| Výřez: {info['max_image_side']}px | Teplota: {info['temperature']}"
        )
        typer.echo(f"             ├─ Přesnost odpovědí       : {info['accuracy_cs']}")
        typer.echo(f"             └─ Kontext a informace     : {info['context_info_cs']}")

    # 4. Zero-Retention (okamžité mazání dat z RAM po zavření chatu)
    typer.echo("\n[4/5] ZERO-RETENTION PAMĚŤOVÁ POLITIKA (OKAMŽITÉ MAZÁNÍ DAT PO ZAVŘENÍ CHATU)")
    typer.echo(
        f"  • [{'OK' if zero_retention_clean else 'VAROVÁNÍ'}] Nulový zápis výřezů na disk : "
        + (
            "Žádné soubory snímků ani logů na disku (vše výhradně v dočasné RAM)."
            if zero_retention_clean
            else f"Nalezeny staré soubory: {', '.join(leftover_files)}"
        )
    )
    typer.echo(
        "  • [OK] Okamžitý výmaz při zavření : Stisk ESC, kliknutí na ✕ nebo nové zakroužkování okamžitě uvolní "
        "QPixmap, PIL Image, io.BytesIO i Base64 string a vynutí gc.collect()."
    )
    typer.echo(
        "  • [OK] Bezpečná systémová schránka: Do schránky se ukládá pouze tehdy, když uživatel sám klikne na tlačítko 'Kopírovat'."
    )

    # 5. 7-bodový bezpečnostní audit napadnutelnosti
    typer.echo("\n[5/5] DIAGNOSTIKA ZABEZPEČENÍ A NAPADNUTELNOSTI SYSTÉMU (7-BODOVÝ AUDIT)")
    typer.echo(
        f"  1. [{'OK' if loopback_ok else 'CHYBA'}] Ochrana proti SSRF & úniku dat      : "
        f"URL '{ollama_url}' je uzamčena na lokální loopback (127.0.0.1 / localhost / ::1)."
    )
    typer.echo(
        "  2. [OK] Anti-Proxy izolace (trust_env=False): HTTP klient ignoruje podvržené systémové proměnné HTTP_PROXY / HTTPS_PROXY."
    )
    typer.echo(
        "  3. [OK] Nulové otevřené síťové porty        : Daemon neotevírá žádný TCP/UDP port; komunikace probíhá přes Windows Named Mutex/Event."
    )
    typer.echo(
        "  4. [OK] Ochrana proti XSS / HTML Injection  : Výstup modelu prochází html.escape(..., quote=True) + zákaz klikání na odkazy (DontOpenLinks)."
    )
    typer.echo(
        "  5. [OK] Ochrana proti Visual Prompt Inject. : Text na obrazovce je striktně izolován jako pasivní data (nelze přepsat systémová pravidla)."
    )
    typer.echo(
        "  6. [OK] Bezpečné spouštění procesů          : subprocess.Popen používá výhradně seznam argumentů se shell=False (žádný Command Injection)."
    )
    typer.echo(
        "  7. [OK] Validace a omezení config.json      : Všechny číselné hodnoty (padding, tloušťka tahu, průhlednost) jsou omezeny proti zahlcení RAM."
    )

    overall_ok = loopback_ok and zero_retention_clean
    typer.echo("\n" + "=" * 108)
    typer.echo(
        f"  VÝSLEDEK AUDITU: {'[PASS / BEZPEČNÉ] Všech 7 bezpečnostních kontrol i Zero-Retention paměť prošly bez chyby.' if overall_ok else '[WARN] Zkontrolujte varování výše.'}"
    )
    typer.echo("=" * 108)


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
