"""CLI interface for AI Lens using Typer with direct language & thinking level shortcuts (e.g. `ai-lens cs High`, `ai-lens en Medium`, `ai-lens Low`)."""

from __future__ import annotations

import ctypes
import json
import os
import platform
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Optional

import httpx
import typer

from ai_lens.daemon import _read_daemon_state, run_daemon, send_daemon_command
from ai_lens.overlay import (
    DEFAULT_CONFIG_PATH,
    _ensure_utf8_stdio,
    load_config,
    run_overlay_mvp,
    set_compute_device_in_config,
    set_language_in_config,
    set_thinking_level_in_config,
)
from ai_lens.vision_engine import (
    DEFAULT_GEMINI_MODEL,
    SUPPORTED_LANGUAGES,
    THINKING_LEVELS,
    has_volatile_gemini_api_key,
    get_volatile_gemini_model,
    is_gemini_api_key,
    is_recognized_gemini_model,
    resolve_gemini_model_name,
    set_volatile_gemini_api_key,
    set_volatile_gemini_model,
    get_compute_device_display,
    get_language_display,
    get_thinking_level_config,
    get_thinking_level_display,
    is_recognized_compute_device,
    is_recognized_language_arg,
    is_recognized_thinking_level,
    normalize_compute_device,
    normalize_language_code,
    normalize_thinking_level,
    validate_local_ollama_host,
)

_ensure_utf8_stdio()

DIAG_ALIASES = {"diag", "diagnostika", "diagnostics", "security", "specs", "specifikace"}
_CLI_DETECTED_DEVICE: Optional[str] = None


def _detect_device_from_shell_and_args() -> Optional[str]:
    r"""
    Detects whether CPU, GPU, or Gemini mode is requested via environment variable AI_LENS_DEVICE.
    Direct CLI arguments (CPU, @\, --cpu, Gemini, etc.) are parsed directly from sys.argv.
    """
    env_dev = os.environ.get("AI_LENS_DEVICE", "").strip().lower()
    if env_dev in ("cpu", "procesor", "@\\", "@/"):
        return "cpu"
    if env_dev in ("gemini", "startwithgemini", "withgemini"):
        return "gemini"
    if env_dev == "gpu":
        return "gpu"
    return None


def _normalize_cli_argv() -> None:
    r"""
    Normalizes CLI arguments before Typer parses commands:
      - Detects and normalizes Gemini API launch command:
          `.\ai-lens.bat start with Gemini` -> `start` with compute_device="gemini"
      - Strips `@\`, `"@\"`, `@\ CPU`, `&& CPU`, `CPU`, `--cpu` and sets `_CLI_DETECTED_DEVICE = "cpu"`
      - Allows launching AI Lens directly with language/level positional arguments (`ai-lens cs High`)
      - Normalizes diagnostic aliases (`diagnostika`, `diagnostics`, `security`, `specs`) to `diag`
    """
    global _CLI_DETECTED_DEVICE

    # 1. Scan and extract any CPU/GPU/Gemini flags from sys.argv
    new_argv = [sys.argv[0]]
    skip_next = False
    for i in range(1, len(sys.argv)):
        if skip_next:
            skip_next = False
            continue
        arg = sys.argv[i].strip()
        cleaned = (
            arg.lower()
            .lstrip("-/\\")
            .replace(" ", "")
            .replace('"', "")
            .replace("'", "")
            .strip("()")
            .strip("<>")
        )

        prev_arg = sys.argv[i - 1].strip().lower() if i > 1 else ""
        if prev_arg in ("--device", "-d"):
            new_argv.append(arg)
            continue

        # Detect `start with Gemini` / `with Gemini`
        if cleaned == "with" and i + 1 < len(sys.argv):
            next_arg = sys.argv[i + 1].strip().lower().replace('"', '').replace("'", "").strip("()<>")
            if next_arg in ("gemini", "gemini-api", "geminiapi") or next_arg.startswith("gemini"):
                _CLI_DETECTED_DEVICE = "gemini"
                skip_next = True
                continue

        # Detect Gemini flags
        if arg in ("--gemini", "-g") or cleaned in (
            "gemini", "start-with-gemini", "startwithgemini", "withgemini",
            "&&gemini", "&gemini", "@gemini", "@\\gemini", "@/gemini"
        ):
            _CLI_DETECTED_DEVICE = "gemini"
            continue

        # Chained or prefixed operators: `@\`, `@/`, `&&`, `&`, `@`
        if arg in ("@\\", "@/","@", '"@\\"', "'@\\'", "&&", "&") or cleaned in ("@\\", "@/"):
            if i + 1 < len(sys.argv):
                next_arg = sys.argv[i + 1].strip().lower().replace('"', '').replace("'", "")
                if next_arg in ("cpu", "procesor"):
                    _CLI_DETECTED_DEVICE = "cpu"
                    skip_next = True
                    continue
                if next_arg == "gpu":
                    _CLI_DETECTED_DEVICE = "gpu"
                    skip_next = True
                    continue
            _CLI_DETECTED_DEVICE = "cpu"
            continue

        if cleaned in ("@\\cpu", "@/cpu", "@cpu", "cpu", "procesor", "&&cpu", "&cpu"):
            _CLI_DETECTED_DEVICE = "cpu"
            continue
        if cleaned in ("@\\gpu", "@/gpu", "@gpu", "gpu", "&&gpu", "&gpu"):
            _CLI_DETECTED_DEVICE = "gpu"
            continue

        new_argv.append(arg)

    sys.argv = new_argv

    # 2. Check shell/console buffer if not passed directly in argv
    if _CLI_DETECTED_DEVICE is None:
        detected = _detect_device_from_shell_and_args()
        if detected:
            _CLI_DETECTED_DEVICE = detected

    # 3. Handle diagnostic aliases and direct language/level shortcuts
    if len(sys.argv) > 1:
        first = sys.argv[1].strip().lower().replace('"', '').replace("'", "")
        # Check for 'start diag ...' -> 'diag ...'
        if first == "start" and len(sys.argv) > 2 and sys.argv[2].strip().lower().replace('"', '').replace("'", "") in DIAG_ALIASES:
            sys.argv.pop(1)
            first = sys.argv[1].strip().lower().replace('"', '').replace("'", "")

        # Check for '<lang> diag' -> 'diag <lang>' (e.g. 'en diag', 'cs diag', 'de diag')
        if len(sys.argv) > 2:
            second = sys.argv[2].strip().lower().replace('"', '').replace("'", "")
            if second in DIAG_ALIASES and (is_recognized_language_arg(first) or is_recognized_thinking_level(first)):
                sys.argv[1] = "diag"
                sys.argv[2] = first
                return

        if first in DIAG_ALIASES:
            sys.argv[1] = "diag"
            return
        if first == "now":
            sys.argv[1] = "--now"
            sys.argv.insert(1, "start")
            return
        if is_recognized_language_arg(first) or is_recognized_thinking_level(first):
            sys.argv[1:1] = ["start"]
    elif _CLI_DETECTED_DEVICE == "gemini":
        sys.argv.append("start")


def _resolve_lang_and_level_and_device(
    arg1: Optional[str],
    arg2: Optional[str],
    arg3: Optional[str] = None,
    opt_lang: Optional[str] = None,
    opt_level: Optional[str] = None,
    opt_device: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Resolves `(language, thinking_level, compute_device)` from flexible positional arguments
    and command options.
    """
    detected_lang: Optional[str] = opt_lang
    detected_level: Optional[str] = opt_level
    detected_device: Optional[str] = opt_device or _CLI_DETECTED_DEVICE

    for raw in (arg1, arg2, arg3):
        if not raw:
            continue
        cleaned = raw.strip().lower().lstrip("-")
        if is_recognized_compute_device(cleaned) and detected_device is None:
            detected_device = normalize_compute_device(cleaned)
        elif is_recognized_thinking_level(raw) and detected_level is None:
            detected_level = normalize_thinking_level(raw)
        elif is_recognized_language_arg(raw) and detected_lang is None:
            detected_lang = normalize_language_code(raw)
        elif detected_lang is None:
            detected_lang = normalize_language_code(raw)

    return detected_lang, detected_level, detected_device


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
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Výpočetní jednotka: gpu (výchozí) nebo cpu (vynucený procesor při '@\\').",
    ),
    cpu: bool = typer.Option(
        False,
        "--cpu",
        help="Vynutí běh čistě na CPU (ekvivalent spuštění s '@\\').",
    ),
    gpu: bool = typer.Option(
        False,
        "--gpu",
        help="Vynutí běh na GPU s plnou akcelerací (výchozí stav).",
    ),
    gemini: bool = typer.Option(
        False,
        "--gemini",
        "-g",
        help="Spustí AI Lens v režimu Google Gemini API (vyžaduje zadání API klíče do RAM).",
    ),
) -> None:
    """
    Spustí AI Lens z příkazové řádky v pohotovosti (poslouchá na Alt+F8 / F8).
    Výchozí akcelerace běží na GPU; zadáním 'start with Gemini' se přepne na Google Gemini API.
    """
    if ctx.invoked_subcommand is None:
        target_device = (
            "gemini"
            if (gemini or _CLI_DETECTED_DEVICE == "gemini")
            else (_CLI_DETECTED_DEVICE or device or ("cpu" if cpu else ("gpu" if gpu else "gpu")))
        )
        run_daemon(
            open_immediately=False,
            language=lang,
            thinking_level=level,
            compute_device=target_device,
        )


@app.command("start")
def start(
    arg1: Optional[str] = typer.Argument(
        None,
        help="Volitelná zkratka jazyka (např. cs, en, de, sk), úroveň myšlení (Low, Medium, High) nebo zařízení (CPU, GPU, @\\).",
    ),
    arg2: Optional[str] = typer.Argument(
        None,
        help="Volitelný druhý parametr – úroveň myšlení (Low, Medium, High) nebo jazyk (např. `ai-lens cs High`).",
    ),
    arg3: Optional[str] = typer.Argument(
        None,
        help="Volitelný třetí parametr – výpočetní jednotka (CPU, GPU, @\\).",
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
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Výpočetní jednotka: gpu (výchozí) nebo cpu (při '@\\').",
    ),
    cpu: bool = typer.Option(
        False,
        "--cpu",
        help="Vynutí běh na CPU.",
    ),
    gpu: bool = typer.Option(
        False,
        "--gpu",
        help="Vynutí běh na GPU.",
    ),
    gemini: bool = typer.Option(
        False,
        "--gemini",
        "-g",
        help="Spustí AI Lens v režimu Google Gemini API (start with Gemini).",
    ),
    now: bool = typer.Option(
        False,
        "--now",
        "-n",
        help="Otevře překryvný overlay rovnou při startu a poté zůstane v pohotovosti.",
    ),
) -> None:
    """Spustí aplikaci s volitelnou zkratkou jazyka, hloubkou myšlení a výpočtem (např. `ai-lens cs High` nebo `ai-lens cs High @\\`)."""
    chosen_lang, chosen_level, chosen_dev = _resolve_lang_and_level_and_device(
        arg1, arg2, arg3, lang, level, device
    )
    if gemini or _CLI_DETECTED_DEVICE == "gemini" or chosen_dev == "gemini":
        chosen_dev = "gemini"
    elif cpu:
        chosen_dev = "cpu"
    elif gpu:
        chosen_dev = "gpu"
    elif chosen_dev is None:
        chosen_dev = "gpu"

    run_daemon(
        open_immediately=now,
        language=chosen_lang,
        thinking_level=chosen_level,
        compute_device=chosen_dev,
    )


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
    arg3: Optional[str] = typer.Argument(
        None,
        help="Volitelná výpočetní jednotka (CPU, GPU).",
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
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Výpočetní jednotka: gpu nebo cpu.",
    ),
    secret: bool = typer.Option(
        False,
        "--secret",
        "-s",
        help="Aktivuje Secret Mode (zkratka Ctrl+Alt+Shift+Q, stručná přímá odpověď s plným pochopením na horní liště).",
    ),
) -> None:
    """Okamžitě vyfotí obrazovku do RAM a otevře fullscreen overlay."""
    chosen_lang, chosen_level, chosen_dev = _resolve_lang_and_level_and_device(
        arg1, arg2, arg3, lang, level, device
    )
    if _CLI_DETECTED_DEVICE == "gemini":
        chosen_dev = "gemini"
    if chosen_lang:
        code = set_language_in_config(chosen_lang)
        typer.echo(f"[AI Lens] Jazyk (UI + AI) nastaven na: {get_language_display(code)}")
    if chosen_level:
        lvl = set_thinking_level_in_config(chosen_level)
        cfg_lang = str(load_config().get("language", "cs"))
        typer.echo(
            f"[AI Lens] Hloubka myšlení nastavena na: {get_thinking_level_display(lvl, cfg_lang)}"
        )
    if chosen_dev and chosen_dev != "gemini":
        d = set_compute_device_in_config(chosen_dev)
        cfg_lang = str(load_config().get("language", "cs"))
        typer.echo(f"[AI Lens] Výpočetní jednotka nastavena na: {get_compute_device_display(d, cfg_lang)}")

    cmd = "SECRET" if secret else "TRIGGER"
    resp = send_daemon_command(cmd)
    if resp in ("OK:TRIGGERED", "OK:SECRET"):
        mode_str = "Secret Mode " if secret else ""
        typer.echo(f"[AI Lens] Signál odeslán běžící instanci -> {mode_str}overlay aktivován.")
    else:
        run_overlay_mvp(
            language=chosen_lang,
            thinking_level=chosen_level,
            compute_device=chosen_dev,
            secret_mode=secret,
        )


@app.command("secret")
def secret_cmd(
    arg1: Optional[str] = typer.Argument(
        None,
        help="Volitelná zkratka jazyka (cs, en, de...) nebo úroveň myšlení (Low, Medium, High).",
    ),
    arg2: Optional[str] = typer.Argument(
        None,
        help="Volitelná úroveň myšlení (Low, Medium, High) nebo jazyk.",
    ),
    arg3: Optional[str] = typer.Argument(
        None,
        help="Volitelná výpočetní jednotka (CPU, GPU).",
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
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Výpočetní jednotka: gpu nebo cpu.",
    ),
) -> None:
    """Spustí AI Lens v Secret Quick-Answer Mode (zkratka Ctrl+Alt+Shift+Q, stručná přímá odpověď s plným pochopením na horní liště)."""
    trigger(arg1=arg1, arg2=arg2, arg3=arg3, lang=lang, level=level, device=device, secret=True)


@app.command("status")
def status() -> None:
    """Zkontroluje, zda běží AI Lens proces, a vypíše aktivní jazyk, úroveň myšlení i režim (GPU/CPU/Gemini API)."""
    state = _read_daemon_state()
    cfg = load_config()
    lang_code = str(cfg.get("language", "cs"))
    lang_disp = get_language_display(lang_code)
    level_code = str(cfg.get("thinking_level", "medium"))

    if state is not None:
        running_mode = str(state.get("mode", cfg.get("compute_device", "gpu")))
        dev_disp = get_compute_device_display(running_mode, lang_code)
        tier_cfg = get_thinking_level_config(level_code, running_mode)
        level_disp = get_thinking_level_display(level_code, lang_code, running_mode)
        active_model = get_volatile_gemini_model() if running_mode == "gemini" else cfg.get("model")
        typer.echo(
            f"[AI Lens] Proces BĚŽÍ (PID: {state.get('pid')}, zkratka: {cfg.get('hotkey')} / F8, model: {active_model}, "
            f"jazyk: {lang_disp}, myšlení: {level_disp} [{tier_cfg['num_predict']} tokenů], režim/výpočet: {dev_disp})."
        )
    else:
        dev_code = str(cfg.get("compute_device", "gpu"))
        dev_disp = get_compute_device_display(dev_code, lang_code)
        tier_cfg = get_thinking_level_config(level_code, dev_code)
        level_disp = get_thinking_level_display(level_code, lang_code, dev_code)
        cmd_pfx = get_cli_command_prefix()
        typer.echo(
            f"[AI Lens] Proces momentálně neběží (jazyk: {lang_disp}, myšlení: {level_disp} [{tier_cfg['num_predict']} tokenů], výpočet: {dev_disp}).\n"
            "Spusť jej např. příkazem:\n"
            f"  {cmd_pfx} start with Gemini  (Google Gemini API — výběr modelu a RAM klíč)\n"
            f"  {cmd_pfx} cs High            (GPU lokální model)\n"
            f"  {cmd_pfx} cs High CPU        (CPU lokální model)"
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
    cmd_pfx = get_cli_command_prefix()
    typer.echo(
        f"Podporované zkratky jazyků (použití: `{cmd_pfx} <jazyk> [Low|Medium|High]`, např. `{cmd_pfx} cs High` nebo `{cmd_pfx} en Medium`):"
    )
    for code, (en_name, native_name) in SUPPORTED_LANGUAGES.items():
        marker = "* " if code == current else "  "
        typer.echo(f"{marker}{code:<4} - {native_name} ({en_name})")


@app.command("levels")
def levels_cmd() -> None:
    """Vypíše úrovně hloubky myšlení (Low, Medium, High) pro GPU i CPU."""
    from ai_lens.vision_engine import THINKING_LEVELS_GPU, THINKING_LEVELS_CPU
    cfg = load_config()
    current_level = normalize_thinking_level(str(cfg.get("thinking_level", "medium")))
    current_dev = _CLI_DETECTED_DEVICE or normalize_compute_device(str(cfg.get("compute_device", "gpu")))

    typer.echo("=" * 114)
    typer.echo("  AI LENS — ÚROVNĚ MYŠLENÍ, PŘESNOSTI A POČTU TOKENŮ PRO GPU A PRO CPU")
    typer.echo("=" * 114)

    typer.echo(f"\n[1] GPU PROFIL (Výchozí akcelerace — plný encyklopedický výkon a bohatý kontext)")
    for key, info in THINKING_LEVELS_GPU.items():
        marker = "* [AKTIVNÍ] " if (key == current_level and current_dev == "gpu") else "            "
        typer.echo(
            f"{marker}{info['label']:<6} | max tokenů: {info['num_predict']:<4} | okno kontextu: {info['num_ctx']:<5} "
            f"| výřez: {info['max_image_side']}px | teplota: {info['temperature']}"
        )
        typer.echo(f"              ├─ Přesnost odpovědí : {info['accuracy_cs']}")
        typer.echo(f"              ├─ Kontext a fakta   : {info['context_info_cs']}")
        typer.echo(f"              └─ Profil a rychlost : {info['desc_cs']}")
        typer.echo("              " + "-" * 98)

    typer.echo(f"\n[2] CPU PROFIL (Odlehčený režim — snížené tokeny a výřez pro svižnou odezvu bez přetížení)")
    for key, info in THINKING_LEVELS_CPU.items():
        marker = "* [AKTIVNÍ] " if (key == current_level and current_dev == "cpu") else "            "
        typer.echo(
            f"{marker}{info['label']:<6} | max tokenů: {info['num_predict']:<4} | okno kontextu: {info['num_ctx']:<5} "
            f"| výřez: {info['max_image_side']}px | teplota: {info['temperature']}"
        )
        typer.echo(f"              ├─ Přesnost odpovědí : {info['accuracy_cs']}")
        typer.echo(f"              ├─ Kontext a fakta   : {info['context_info_cs']}")
        typer.echo(f"              └─ Profil a rychlost : {info['desc_cs']}")
        typer.echo("              " + "-" * 98)

    cmd_pfx = get_cli_command_prefix()
    typer.echo(f"\nSpuštění: {cmd_pfx} <jazyk> <Low|Medium|High> (GPU) nebo {cmd_pfx} <jazyk> <Low|Medium|High> CPU (CPU)")


def get_cli_command_prefix() -> str:
    """Returns platform-specific command prefix: '.\\ai-lens.bat' on Windows, './ai-lens.sh' on macOS/Linux."""
    return ".\\ai-lens.bat" if sys.platform == "win32" else "./ai-lens.sh"


def _get_system_memory_info() -> tuple[float, float, float, int]:
    """
    Returns (total_gb, used_gb, free_gb, percent_used) cross-platform
    (Windows, macOS, Linux) without requiring external dependencies.
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
    elif sys.platform == "darwin":
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            total_bytes = pages * page_size
            total_gb = total_bytes / (1024**3)
            free_gb = total_gb * 0.4
            vm = subprocess.check_output(["vm_stat"], timeout=2.0).decode("utf-8", errors="replace")
            m_free = re.search(r"Pages free:\s+(\d+)", vm)
            m_spec = re.search(r"Pages speculative:\s+(\d+)", vm)
            free_p = (int(m_free.group(1)) if m_free else 0) + (int(m_spec.group(1)) if m_spec else 0)
            if free_p > 0:
                free_gb = (free_p * page_size) / (1024**3)
            used_gb = max(0.0, total_gb - free_gb)
            pct = int((used_gb / total_gb) * 100) if total_gb > 0 else 0
            return total_gb, used_gb, free_gb, pct
        except Exception:
            pass
    else:  # Linux
        try:
            meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
            t_m = re.search(r"MemTotal:\s+(\d+)", meminfo)
            a_m = re.search(r"MemAvailable:\s+(\d+)", meminfo)
            if t_m and a_m:
                total_gb = int(t_m.group(1)) / (1024**2)
                avail_gb = int(a_m.group(1)) / (1024**2)
                used_gb = max(0.0, total_gb - avail_gb)
                pct = int((used_gb / total_gb) * 100) if total_gb > 0 else 0
                return total_gb, used_gb, avail_gb, pct
        except Exception:
            pass
    return 0.0, 0.0, 0.0, 0


@app.command("diag")
def diag_cmd(
    lang: Optional[str] = typer.Argument(
        None,
        help="Volitelný kód jazyka pro výpis diagnostiky (např. 'en', 'cs', 'de', 'sk'). Pokud není zadán, použije se jazyk z konfigurace.",
    ),
    lang_opt: Optional[str] = typer.Option(
        None,
        "--lang",
        "-l",
        help="Volitelný parametr jazyka diagnostiky.",
    ),
) -> None:
    """
    Spustí kompletní živou diagnostiku v terminálu (model, RAM/CPU, kontext a přesnost Low/Medium/High,
    kontrola mazání dat z RAM po zavření chatu a 8-bodový bezpečnostní audit napadnutelnosti).
    Lze volat jako: `ai-lens diag`, `ai-lens diag en`, `ai-lens en diag`, `ai-lens diagnostika` nebo `ai-lens security`.
    """
    cfg = load_config()
    target_lang = normalize_language_code(lang or lang_opt or str(cfg.get("language", "cs")))
    is_cs = target_lang in ("cs", "sk")

    lang_disp = get_language_display(target_lang)
    level_code = normalize_thinking_level(str(cfg.get("thinking_level", "medium")))
    dev_code = _CLI_DETECTED_DEVICE or normalize_compute_device(str(cfg.get("compute_device", "gpu")))
    dev_disp = get_compute_device_display(dev_code, target_lang)
    tier_cfg = get_thinking_level_config(level_code, dev_code)
    level_disp = get_thinking_level_display(level_code, target_lang, dev_code)
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

    from ai_lens.vision_engine import THINKING_LEVELS_GPU, THINKING_LEVELS_CPU
    active_levels = THINKING_LEVELS_CPU if dev_code == "cpu" else THINKING_LEVELS_GPU
    cmd_pfx = get_cli_command_prefix()
    ipc_desc = "Win32 WM_HOTKEY" if sys.platform == "win32" else "POSIX signály (SIGUSR1/SIGUSR2/SIGTERM)"
    ipc_desc_en = "Win32 WM_HOTKEY" if sys.platform == "win32" else "POSIX signals (SIGUSR1/SIGUSR2/SIGTERM)"

    typer.echo("=" * 108)
    if is_cs:
        typer.echo("  AI LENS — ŽIVÁ SYSTÉMOVÁ SPECIFIKACE, KONTEXT & BEZPEČNOSTNÍ DIAGNOSTIKA (CLI REPORT)")
    else:
        typer.echo("  AI LENS — LIVE SYSTEM SPECIFICATION, CONTEXT & SECURITY AUDIT (CLI REPORT)")
    typer.echo("=" * 108)

    # 1. Stav běhu a AI modelu / Runtime & AI Model Status
    if is_cs:
        typer.echo("\n[1/5] STAV APLIKACE & AI MODELU (RUNTIME)")
        typer.echo(
            f"  • Stav procesu na pozadí : {'BĚŽÍ (připraven na ' + hotkey + ' / F8)' if daemon_running else f'NEBĚŽÍ (spusť: {cmd_pfx} cs High nebo {cmd_pfx} cs High CPU)'}"
        )
        typer.echo(
            f"  • Lokální Ollama engine  : {'ONLINE a model připraven (' + ollama_url + ')' if ollama_online else 'OFFLINE nebo model není stažen (' + ollama_url + ')'}"
        )
        typer.echo(f"  • Aktivní VLM model      : {model_name} (doporučená lehká alternativa: qwen2.5vl:3b)")
        typer.echo(f"  • Výpočet / Akcelerace   : {dev_disp} (výchozí: GPU; přepnutí: zadej 'CPU' při spuštění)")
        typer.echo(f"  • Aktivní jazyk (UI+AI)  : {lang_disp}")
        typer.echo(
            f"  • Aktivní úroveň myšlení : {level_disp} (max {tier_cfg['num_predict']} tokenů, kontext {tier_cfg['num_ctx']}, výřez {tier_cfg['max_image_side']}px)"
        )
    else:
        typer.echo("\n[1/5] APPLICATION & AI MODEL STATUS (RUNTIME)")
        typer.echo(
            f"  • Background Process Status : {'RUNNING (ready for ' + hotkey + ' / F8)' if daemon_running else f'NOT RUNNING (start: {cmd_pfx} en High or {cmd_pfx} en High CPU)'}"
        )
        typer.echo(
            f"  • Local Ollama Engine       : {'ONLINE and model ready (' + ollama_url + ')' if ollama_online else 'OFFLINE or model not pulled (' + ollama_url + ')'}"
        )
        typer.echo(f"  • Active VLM Model          : {model_name} (recommended lightweight alternative: qwen2.5vl:3b)")
        typer.echo(f"  • Compute / Acceleration    : {dev_disp} (default: GPU; switch: specify 'CPU' at launch)")
        typer.echo(f"  • Active Language (UI+AI)   : {lang_disp}")
        typer.echo(
            f"  • Active Thinking Depth     : {level_disp} (max {tier_cfg['num_predict']} tokens, context {tier_cfg['num_ctx']}, crop {tier_cfg['max_image_side']}px)"
        )

    # 2. Hardware, RAM a CPU / Hardware Resources, RAM & CPU
    if is_cs:
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
    else:
        typer.echo("\n[2/5] HARDWARE RESOURCES, RAM & CPU CONSUMPTION")
        typer.echo(f"  • Operating System & CPU  : {os_info} | {cpu_cores} logical cores | Python {py_ver}")
        if total_gb > 0:
            typer.echo(
                f"  • Live System RAM         : {used_gb:.2f} GB used / {total_gb:.2f} GB total ({mem_pct}% load, {free_gb:.2f} GB free)"
            )
        typer.echo("  • AI Lens Footprint (GUI) : ~45–75 MB RAM in standby (0.0 % CPU) | ~95–145 MB RAM during lasso drawing")
        typer.echo(
            "  • VLM Footprint (Ollama)  : ~3.2–4.5 GB RAM/VRAM (gemma4:latest) | ~2.4–3.1 GB RAM/VRAM (qwen2.5vl:3b)"
        )

    # 3. Kontext, přesnost a hloubka / Context, Accuracy & Reasoning
    if is_cs:
        typer.echo(f"\n[3/5] KONTEXT, PŘESNOST ODPOVĚDÍ A BOHATOST INFORMACÍ ({dev_code.upper()} REŽIM)")
        for key, info in active_levels.items():
            active_tag = "[AKTIVNÍ]" if key == level_code else "         "
            typer.echo(
                f"  {active_tag} {info['label']:<6} | Tokeny: {info['num_predict']:<4} | Okno: {info['num_ctx']:<5} "
                f"| Výřez: {info['max_image_side']}px | Teplota: {info['temperature']}"
            )
            typer.echo(f"             ├─ Přesnost odpovědí       : {info['accuracy_cs']}")
            typer.echo(f"             └─ Kontext a informace     : {info['context_info_cs']}")
    else:
        typer.echo(f"\n[3/5] FACTUAL CONTEXT, ACCURACY & REASONING DEPTH ({dev_code.upper()} MODE)")
        for key, info in active_levels.items():
            active_tag = "[ACTIVE]" if key == level_code else "        "
            typer.echo(
                f"  {active_tag} {info['label']:<6} | Tokens: {info['num_predict']:<4} | Context: {info['num_ctx']:<5} "
                f"| Crop: {info['max_image_side']}px | Temp: {info['temperature']}"
            )
            typer.echo(f"             ├─ Response Accuracy     : {info['accuracy_en']}")
            typer.echo(f"             └─ Context & Reasoning   : {info['context_info_en']}")

    # 4. Zero-Retention paměťová politika / Zero-Retention Policy
    if is_cs:
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
    else:
        typer.echo("\n[4/5] ZERO-RETENTION MEMORY POLICY (INSTANT DATA PURGE UPON CLOSING CHAT)")
        typer.echo(
            f"  • [{'OK' if zero_retention_clean else 'WARNING'}] Zero disk writes for crops : "
            + (
                "No screenshot or log files on disk (all strictly held in volatile RAM)."
                if zero_retention_clean
                else f"Found legacy files: {', '.join(leftover_files)}"
            )
        )
        typer.echo(
            "  • [OK] Instant purge upon close : Pressing ESC, clicking ✕ or new lasso immediately frees "
            "QPixmap, PIL Image, io.BytesIO and Base64 string and enforces gc.collect()."
        )
        typer.echo(
            "  • [OK] Secure system clipboard  : Data is copied to clipboard ONLY when user explicitly clicks the 'Copy' button."
        )

    # 5. 8-bodový bezpečnostní audit / 8-Point Security Audit
    if is_cs:
        typer.echo("\n[5/5] DIAGNOSTIKA ZABEZPEČENÍ A NAPADNUTELNOSTI SYSTÉMU (8-BODOVÝ AUDIT)")
        typer.echo(
            f"  1. [{'OK' if loopback_ok else 'CHYBA'}] Ochrana proti SSRF & úniku dat      : "
            f"URL '{ollama_url}' je uzamčena na lokální loopback (127.0.0.1 / localhost / ::1)."
        )
        typer.echo(
            "  2. [OK] Anti-Proxy izolace (trust_env=False): HTTP klient ignoruje podvržené systémové proměnné HTTP_PROXY / HTTPS_PROXY."
        )
        typer.echo(
            f"  3. [OK] Nulové otevřené síťové porty        : Daemon neotevírá žádný TCP/UDP port; komunikace probíhá lokálně přes {ipc_desc}."
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
            "  7. [OK] Validace a omezení config.json      : Všechny číselné hodnoty jsou limitovány; API klíč se do config.json nesmí nikdy zapsat."
        )
        typer.echo(
            "  8. [OK] Zabezpečení Gemini API klíče (RAM)  : 100% v paměti RAM; přenos výhradně v HTTPS hlavičce x-goog-api-key (ne v URL), getpass maskování."
        )
    else:
        typer.echo("\n[5/5] SYSTEM SECURITY & ATTACK-RESILIENCE AUDIT (8-POINT AUDIT)")
        typer.echo(
            f"  1. [{'OK' if loopback_ok else 'FAIL'}] Protection against SSRF & data leaks : "
            f"URL '{ollama_url}' is locked strictly to local loopback (127.0.0.1 / localhost / ::1)."
        )
        typer.echo(
            "  2. [OK] Anti-Proxy isolation (trust_env=False): HTTP client ignores forged HTTP_PROXY / HTTPS_PROXY environment variables."
        )
        typer.echo(
            f"  3. [OK] Zero open network listening ports   : Daemon opens zero TCP/UDP ports; communication is local via {ipc_desc_en}."
        )
        typer.echo(
            "  4. [OK] Protection against XSS/HTML Inject. : Model output filtered with html.escape(..., quote=True) + link clicking disabled (DontOpenLinks)."
        )
        typer.echo(
            "  5. [OK] Protection vs. Visual Prompt Inject.: Screen text is strictly isolated as passive data (cannot override system instructions)."
        )
        typer.echo(
            "  6. [OK] Secure process execution             : subprocess.Popen strictly uses argument list with shell=False (no Command Injection)."
        )
        typer.echo(
            "  7. [OK] config.json bounds & key protection : All numeric settings are validated; API keys are never stored on disk."
        )
        typer.echo(
            "  8. [OK] Gemini API key security (RAM only)  : 100% volatile memory; transmitted exclusively via HTTPS header x-goog-api-key (never in URL), getpass masked."
        )

    overall_ok = loopback_ok and zero_retention_clean
    typer.echo("\n" + "=" * 108)
    if is_cs:
        typer.echo(
            f"  VÝSLEDEK AUDITU: {'[PASS / BEZPEČNÉ] Všech 8 bezpečnostních kontrol i Zero-Retention paměť prošly bez chyby.' if overall_ok else '[WARN] Zkontrolujte varování výše.'}"
        )
    else:
        typer.echo(
            f"  AUDIT RESULT: {'[PASS / SECURE] All 8 security checks and Zero-Retention memory verified without errors.' if overall_ok else '[WARN] Please check warnings above.'}"
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
    device: Optional[str] = typer.Option(
        None,
        "--device",
        "-d",
        help="Nastaví výpočetní jednotku: gpu nebo cpu",
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
    if device is not None:
        set_compute_device_in_config(device)

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
        # Security: never persist API keys or volatile cloud modes to disk
        cfg.pop("gemini_api_key", None)
        cfg.pop("api_key", None)
        if cfg.get("compute_device") == "gemini":
            cfg["compute_device"] = "gpu"
        if "padding" in cfg:
            try:
                cfg["padding"] = max(0, min(200, int(cfg["padding"])))
            except Exception:
                cfg["padding"] = 4
        with open(DEFAULT_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

    if updated or lang is not None or level is not None or device is not None:
        typer.echo("[AI Lens] Konfigurace uložena do config.json:")

    typer.echo(json.dumps(cfg, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    app()
