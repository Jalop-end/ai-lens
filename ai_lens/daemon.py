"""Firewall-free CLI daemon with Floating Mini-Dock, Triple-Engine Hotkey Detection (Alt+F8), and Console QuickEdit protection."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import datetime
import json
import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QObject, QPoint, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QMouseEvent, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QWidget,
)

from ai_lens.overlay import (
    OverlayWindow,
    _ensure_utf8_stdio,
    load_config,
    set_compute_device_in_config,
    set_language_in_config,
    set_thinking_level_in_config,
)
from ai_lens.vision_engine import (
    DEFAULT_GEMINI_MODEL,
    choose_gemini_model_interactive,
    clear_volatile_gemini_api_key,
    get_volatile_gemini_model,
    set_volatile_gemini_model,
    get_compute_device_display,
    get_language_display,
    get_thinking_level_config,
    get_thinking_level_display,
    get_ui_strings,
    has_volatile_gemini_api_key,
    normalize_compute_device,
    normalize_language_code,
    normalize_thinking_level,
    prompt_for_gemini_api_key,
    set_volatile_gemini_api_key,
    warmup_local_model,
)

STATE_FILE_PATH = Path(__file__).resolve().parent.parent / ".ai_lens_state.json"
DEBUG_LOG_PATH = Path(__file__).resolve().parent.parent / "ai_lens_debug.log"

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

HOTKEY_ID_ALT_F8 = 1
HOTKEY_ID_F8 = 2
HOTKEY_ID_CTRL_SHIFT_G = 3
HOTKEY_ID_CTRL_ALT_SHIFT_G = 4
HOTKEY_ID_CUSTOM = 5
HOTKEY_ID_SECRET = 6
HOTKEY_ID_STOP = 99

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_LMENU = 0xA4
VK_RMENU = 0xA5
VK_F8 = 0x77

FUNCTION_KEY_VKS = {f"f{i}": 0x70 + (i - 1) for i in range(1, 13)}


def _log_debug(msg: str) -> None:
    """Writes timestamped diagnostic entry to stdout only (zero disk log persistence)."""
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        if DEBUG_LOG_PATH.exists():
            DEBUG_LOG_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _disable_console_quickedit() -> None:
    """
    Disables Windows Console QuickEdit Mode on stdin so that clicking inside the
    PowerShell/CMD window never pauses/freezes the running Python event loop.
    """
    if sys.platform != "win32":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        STD_INPUT_HANDLE = -10
        ENABLE_QUICK_EDIT_MODE = 0x0040
        ENABLE_EXTENDED_FLAGS = 0x0080
        h_stdin = kernel32.GetStdHandle(STD_INPUT_HANDLE)
        if h_stdin and h_stdin != -1:
            mode = ctypes.wintypes.DWORD()
            if kernel32.GetConsoleMode(h_stdin, ctypes.byref(mode)):
                new_mode = (mode.value & ~ENABLE_QUICK_EDIT_MODE) | ENABLE_EXTENDED_FLAGS
                kernel32.SetConsoleMode(h_stdin, new_mode)
    except Exception:
        pass


def _parse_win32_hotkey(hotkey_str: str) -> tuple[int, int, list[int]]:
    """
    Parses a hotkey string like '<alt>+<f8>' or '<ctrl>+<alt>+<shift>+g' into:
      (win32_modifiers, vk_code, list_of_vk_codes_for_GetAsyncKeyState).
    Supports F1..F12 as well as alphanumeric keys.
    """
    mods = MOD_NOREPEAT
    vk = VK_F8
    vk_list: list[int] = []

    parts = [p.strip().lower().strip("<>") for p in hotkey_str.split("+") if p.strip()]
    for part in parts:
        if part in ("ctrl", "control"):
            mods |= MOD_CONTROL
            vk_list.append(VK_CONTROL)
        elif part == "alt":
            mods |= MOD_ALT
            vk_list.append(VK_MENU)
        elif part == "shift":
            mods |= MOD_SHIFT
            vk_list.append(VK_SHIFT)
        elif part in ("win", "cmd", "super"):
            mods |= MOD_WIN
        elif part in FUNCTION_KEY_VKS:
            vk = FUNCTION_KEY_VKS[part]
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
    vk_list.append(vk)
    return mods, vk, vk_list


class FloatingTriggerBar(QFrame):
    """
    Ultra-mini green dot indicator in the top-right corner of the screen.
    Shows that AI Lens is running in the background.
    Clicking this mini dot immediately turns off / shuts down the entire AI Lens process.
    """

    triggerClicked = pyqtSignal()
    quitClicked = pyqtSignal()

    def __init__(
        self,
        language: str = "cs",
        thinking_level: str = "medium",
        compute_device: str = "gpu",
    ) -> None:
        super().__init__(None)
        self.setObjectName("FloatingTriggerBar")
        self.setWindowTitle("AI Lens Dot")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(18, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hovered = False

        self.lang_code = normalize_language_code(language)
        self.setToolTip(
            "AI Lens [Aktivní] — Kliknutím vypnout celou AI"
            if self.lang_code in ("cs", "sk")
            else "AI Lens [Active] — Click to shut down AI"
        )

        # Position right in the top-right corner of primary screen:
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            sgeom = screen.geometry()
            avail = screen.availableGeometry()
            dot_w = self.width()
            max_x = min(sgeom.x() + sgeom.width(), avail.x() + avail.width())
            min_y = max(sgeom.y(), avail.y())
            x = max_x - dot_w - 6
            y = min_y + 6
            self.move(int(x), int(y))

        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(2000)
        self._topmost_timer.timeout.connect(self._force_win32_topmost)
        self._topmost_timer.start()

    def _force_win32_topmost(self) -> None:
        """Forces the green dot to stay in foreground over full-screen and maximized windows."""
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040
            user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
        except Exception:
            pass

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._force_win32_topmost()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Ultra-mini 9x9 px round dot centered inside the 18x18 clickable area
        dot_rect = QRectF(4.5, 4.5, 9.0, 9.0)
        dot_color = QColor("#EF4444") if self._hovered else QColor("#22C55E")
        painter.setBrush(dot_color)
        painter.setPen(QPen(QColor(255, 255, 255, 220), 1.0))
        painter.drawEllipse(dot_rect)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton):
            self.quitClicked.emit()


def _is_pid_alive(pid: int) -> bool:
    """Checks if a Windows process with `pid` is currently alive without any network socket."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.wintypes.DWORD()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        ctypes.windll.kernel32.CloseHandle(handle)
        return bool(ok and exit_code.value == STILL_ACTIVE)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_daemon_state() -> Optional[dict[str, Any]]:
    """Reads PID, Win32 Hotkey Thread ID (TID), and mode of a running daemon from .ai_lens_state.json."""
    if not STATE_FILE_PATH.exists():
        return None
    try:
        data = json.loads(STATE_FILE_PATH.read_text(encoding="utf-8"))
        pid = int(data.get("pid", 0))
        tid = int(data.get("tid", 0))
        if _is_pid_alive(pid):
            return data
    except Exception:
        pass
    try:
        STATE_FILE_PATH.unlink(missing_ok=True)
    except Exception:
        pass
    return None


def _write_daemon_state(pid: int, tid: int, mode: str = "gpu") -> None:
    """Saves the current daemon PID, Win32 Hotkey Thread ID, and mode to .ai_lens_state.json."""
    try:
        STATE_FILE_PATH.write_text(
            json.dumps({"pid": pid, "tid": tid, "mode": mode}, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass


def _clear_daemon_state() -> None:
    try:
        STATE_FILE_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def send_daemon_command(command: str) -> Optional[str]:
    """
    Sends a command ('TRIGGER', 'STATUS', 'STOP') to the running AI Lens process
    using Win32 PostThreadMessageW to the dedicated Win32 GetMessageW thread.
    """
    state = _read_daemon_state()
    if state is None:
        return None

    cmd = command.upper().strip()
    if cmd == "STATUS":
        return "OK:RUNNING"

    if sys.platform == "win32":
        tid = state.get("tid", 0)
        user32 = ctypes.windll.user32
        if cmd == "TRIGGER" and tid:
            ok = bool(user32.PostThreadMessageW(tid, WM_HOTKEY, HOTKEY_ID_ALT_F8, 0))
            return "OK:TRIGGERED" if ok else None
        if cmd == "SECRET" and tid:
            ok = bool(user32.PostThreadMessageW(tid, WM_HOTKEY, HOTKEY_ID_SECRET, 0))
            return "OK:SECRET" if ok else None
        if cmd == "STOP" and tid:
            ok = bool(user32.PostThreadMessageW(tid, WM_HOTKEY, HOTKEY_ID_STOP, 0))
            return "OK:STOPPING" if ok else None
    else:
        pid = int(state.get("pid", 0))
        if pid and _is_pid_alive(pid):
            try:
                if cmd == "TRIGGER":
                    os.kill(pid, signal.SIGUSR1)
                    return "OK:TRIGGERED"
                if cmd == "SECRET":
                    os.kill(pid, signal.SIGUSR2)
                    return "OK:SECRET"
                if cmd == "STOP":
                    os.kill(pid, signal.SIGTERM)
                    return "OK:STOPPING"
            except OSError:
                pass

    return None


class DaemonBridge(QObject):
    """Thread-safe Qt signal bridge from Win32/pynput hotkey threads to Qt GUI thread."""

    triggerRequested = pyqtSignal(str)
    stopRequested = pyqtSignal()


def run_daemon(
    open_immediately: bool = False,
    language: Optional[str] = None,
    thinking_level: Optional[str] = None,
    compute_device: Optional[str] = None,
) -> None:
    """
    Starts AI Lens from the Command Line:
      - Zero TCP/IP listening sockets (completely invisible to Windows Firewall).
      - Shows a sleek FloatingTriggerBar ('🔍 AI Lens [CS · High · GPU] (Alt+F8)') at top-right of screen
        for 1-click mouse activation AND visual confirmation.
      - Default compute device: GPU (fastest). Switches to CPU when launched with `&& CPU`.
      - Triple-Engine Hotkey Detection for Alt+F8, F8, Ctrl+Shift+G, and Ctrl+Alt+Shift+G:
          1. Win32 RegisterHotKey in a dedicated pure-Python GetMessageW thread.
          2. 15ms GetAsyncKeyState hardware poller in QTimer.
          3. pynput low-level keyboard listener fallback.
    """
    _ensure_utf8_stdio()
    _disable_console_quickedit()

    norm_dev = normalize_compute_device(compute_device) if compute_device else None

    # Handle Gemini API mode: always show model selection table first, then prompt for API key
    if norm_dev == "gemini":
        chosen_m = choose_gemini_model_interactive(language or "cs")
        prompt_for_gemini_api_key(language or "cs", chosen_model=chosen_m)

    if language:
        set_language_in_config(language)
    if thinking_level:
        set_thinking_level_in_config(thinking_level)
    if compute_device:
        if norm_dev != "gemini":
            set_compute_device_in_config(compute_device)
    else:
        # Default to GPU when launched normally without && CPU or Gemini
        set_compute_device_in_config("gpu")

    existing = _read_daemon_state()
    if existing is not None:
        if norm_dev == "gemini":
            _log_debug(
                f"[AI Lens] Stopping previous instance (PID {existing['pid']}) to launch with Google Gemini API…"
            )
            send_daemon_command("STOP")
            time.sleep(0.6)
            _clear_daemon_state()
        else:
            cfg_now = load_config()
            lang_code_now = str(cfg_now.get("language", "cs"))
            lang_disp = get_language_display(lang_code_now)
            dev_now = str(cfg_now.get("compute_device", "gpu"))
            dev_disp = get_compute_device_display(dev_now, lang_code_now)
            level_disp = get_thinking_level_display(
                str(cfg_now.get("thinking_level", "medium")), lang_code_now, dev_now
            )
            _log_debug(
                f"[AI Lens] Process already running (PID {existing['pid']}, language: {lang_disp}, thinking depth: {level_disp}, mode: {dev_disp}). Activating overlay…"
            )
            send_daemon_command("TRIGGER")
            return

    config = load_config()
    hotkey_str = str(config.get("hotkey", "<alt>+<f8>"))
    model_name = str(config.get("model", "gemma4:latest"))
    ollama_host = str(config.get("ollama_host", "http://127.0.0.1:11434"))
    lang_code = str(config.get("language", "cs"))
    level_code = str(config.get("thinking_level", "medium"))
    dev_code = "gemini" if has_volatile_gemini_api_key() else str(config.get("compute_device", "gpu"))
    active_model = get_volatile_gemini_model() if dev_code == "gemini" else model_name
    tier_cfg = get_thinking_level_config(level_code, dev_code)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    overlay = OverlayWindow(config=config, daemon_mode=True)
    floating_bar = FloatingTriggerBar(
        language=lang_code,
        thinking_level=level_code,
        compute_device=dev_code,
    )
    floating_bar.show()
    floating_bar.raise_()

    bridge = DaemonBridge()
    last_trigger_time = 0.0
    hotkey_thread_tid = 0
    ready_event = threading.Event()

    def _on_overlay_dismissed() -> None:
        floating_bar.show()
        floating_bar.raise_()

    overlay.overlayDismissed.connect(_on_overlay_dismissed)

    def _on_trigger(source: str = "hotkey") -> None:
        nonlocal last_trigger_time
        now = time.monotonic()
        if now - last_trigger_time < 0.45:
            return
        last_trigger_time = now

        # Hide floating green dot BEFORE capturing screen so it isn't in the screenshot
        if floating_bar.isVisible():
            floating_bar.hide()
            QApplication.processEvents()

        is_secret = "secret" in source.lower()
        capture_ms = overlay.activate_overlay(secret_mode=is_secret)
        backend = overlay.capture_result.capture_backend if overlay.capture_result else "unknown"
        mode_label = "SECRET MODE" if is_secret else "Standard"
        _log_debug(
            f"[AI Lens] Activation ({source} · {mode_label}) -> screen ({backend}) frozen in {capture_ms:.1f} ms."
        )

    def _on_stop() -> None:
        _log_debug("[AI Lens] Terminating AI Lens…")
        _clear_daemon_state()
        if clear_volatile_gemini_api_key():
            print(
                "[AI Lens] Gemini API key was securely wiped from short-term memory (RAM).",
                flush=True,
            )
        if sys.platform == "win32" and hotkey_thread_tid:
            try:
                ctypes.windll.user32.PostThreadMessageW(hotkey_thread_tid, WM_QUIT, 0, 0)
            except Exception:
                pass
        floating_bar.close()
        overlay.close()
        app.quit()

    floating_bar.triggerClicked.connect(lambda: bridge.triggerRequested.emit("Mini-Dock kliknutí"))
    floating_bar.quitClicked.connect(bridge.stopRequested.emit)

    bridge.triggerRequested.connect(_on_trigger, Qt.ConnectionType.QueuedConnection)
    bridge.stopRequested.connect(_on_stop, Qt.ConnectionType.QueuedConnection)

    mods, vk, vk_list = _parse_win32_hotkey(hotkey_str)

    if sys.platform == "win32":
        user32 = ctypes.windll.user32

        # Engine 1: Dedicated Win32 GetMessageW thread (zero PyQt6 nativeEvent callbacks!)
        def _win32_hotkey_loop() -> None:
            nonlocal hotkey_thread_tid
            u32 = ctypes.windll.user32
            k32 = ctypes.windll.kernel32
            hotkey_thread_tid = int(k32.GetCurrentThreadId())

            msg = ctypes.wintypes.MSG()
            u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)

            r_alt_f8 = u32.RegisterHotKey(None, HOTKEY_ID_ALT_F8, MOD_ALT | MOD_NOREPEAT, VK_F8)
            r_f8 = u32.RegisterHotKey(None, HOTKEY_ID_F8, MOD_NOREPEAT, VK_F8)
            r_csg = u32.RegisterHotKey(
                None, HOTKEY_ID_CTRL_SHIFT_G, MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, ord("G")
            )
            r_casg = u32.RegisterHotKey(
                None,
                HOTKEY_ID_CTRL_ALT_SHIFT_G,
                MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_NOREPEAT,
                ord("G"),
            )
            r_secret = u32.RegisterHotKey(
                None,
                HOTKEY_ID_SECRET,
                MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_NOREPEAT,
                ord("Q"),
            )
            if (mods, vk) not in (
                (MOD_ALT | MOD_NOREPEAT, VK_F8),
                (MOD_NOREPEAT, VK_F8),
                (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, ord("G")),
                (MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_NOREPEAT, ord("G")),
            ):
                u32.RegisterHotKey(None, HOTKEY_ID_CUSTOM, mods, vk)

            _log_debug(
                f"[AI Lens] Win32 RegisterHotKey status: Alt+F8={bool(r_alt_f8)}, "
                f"F8={bool(r_f8)}, Ctrl+Shift+G={bool(r_csg)}, Ctrl+Alt+Shift+G={bool(r_casg)}, "
                f"Ctrl+Alt+Shift+Q (Secret)={bool(r_secret)}"
            )

            _write_daemon_state(os.getpid(), hotkey_thread_tid, dev_code)
            ready_event.set()

            while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    wp = int(msg.wParam)
                    if wp == HOTKEY_ID_STOP:
                        bridge.stopRequested.emit()
                        break
                    if wp == HOTKEY_ID_SECRET:
                        bridge.triggerRequested.emit("secret:WM_HOTKEY(Ctrl+Alt+Shift+Q)")
                    else:
                        bridge.triggerRequested.emit(f"WM_HOTKEY(id={wp})")

            for hid in (
                HOTKEY_ID_ALT_F8,
                HOTKEY_ID_F8,
                HOTKEY_ID_CTRL_SHIFT_G,
                HOTKEY_ID_CTRL_ALT_SHIFT_G,
                HOTKEY_ID_SECRET,
                HOTKEY_ID_CUSTOM,
            ):
                u32.UnregisterHotKey(None, hid)

        hk_thread = threading.Thread(target=_win32_hotkey_loop, name="AILensWin32Hotkey", daemon=True)
        hk_thread.start()
        ready_event.wait(timeout=2.0)

        # Engine 2: Hardware key-state poller (GetAsyncKeyState every 15 ms)
        combo_was_down = False

        def _is_down(vkey: int) -> bool:
            return (user32.GetAsyncKeyState(vkey) & 0x8000) != 0

        def _poll_hardware_keys() -> None:
            nonlocal combo_was_down
            if overlay.isVisible():
                combo_was_down = False
                return

            alt_down = _is_down(VK_MENU) or _is_down(VK_LMENU) or _is_down(VK_RMENU)
            ctrl_down = _is_down(VK_CONTROL)
            shift_down = _is_down(VK_SHIFT)
            f8_down = _is_down(VK_F8)
            g_down = _is_down(ord("G"))
            q_down = _is_down(ord("Q"))

            alt_f8 = alt_down and f8_down
            just_f8 = f8_down
            ctrl_shift_g = ctrl_down and shift_down and g_down
            ctrl_alt_shift_q = ctrl_down and alt_down and shift_down and q_down
            custom_combo = all(_is_down(k) for k in vk_list)

            triggered = alt_f8 or just_f8 or ctrl_shift_g or ctrl_alt_shift_q or custom_combo
            if triggered and not combo_was_down:
                combo_was_down = True
                if ctrl_alt_shift_q:
                    bridge.triggerRequested.emit("secret:GetAsyncKeyState(Ctrl+Alt+Shift+Q)")
                else:
                    label = "Alt+F8" if alt_f8 else ("F8" if just_f8 else "Ctrl+Shift+G")
                    bridge.triggerRequested.emit(f"GetAsyncKeyState({label})")
            elif not triggered:
                combo_was_down = False

        poll_timer = QTimer()
        poll_timer.setInterval(15)
        poll_timer.timeout.connect(_poll_hardware_keys)
        poll_timer.start()
    else:
        # Non-Windows (macOS, Linux): register PID state and POSIX signal handlers
        _write_daemon_state(os.getpid(), 0, dev_code)
        try:
            signal.signal(signal.SIGUSR1, lambda *_: bridge.triggerRequested.emit("signal:SIGUSR1"))
            signal.signal(signal.SIGUSR2, lambda *_: bridge.triggerRequested.emit("secret:signal:SIGUSR2"))
            signal.signal(signal.SIGTERM, lambda *_: bridge.stopRequested.emit())
        except Exception:
            pass
        ready_event.set()

    # Engine 3: pynput cross-platform global keyboard listener (Windows, macOS, Linux)
    pynput_listener = None
    try:
        from pynput import keyboard

        def _fire_trigger(src: str) -> None:
            if not overlay.isVisible():
                bridge.triggerRequested.emit(src)

        def _fire_secret(src: str) -> None:
            if not overlay.isVisible():
                bridge.triggerRequested.emit(f"secret:{src}")

        hotkey_bindings = {
            "<f8>": lambda: _fire_trigger("pynput(F8)"),
            "<alt>+<f8>": lambda: _fire_trigger("pynput(Alt+F8)"),
            "<ctrl>+<shift>+g": lambda: _fire_trigger("pynput(Ctrl+Shift+G)"),
            "<cmd>+<shift>+g": lambda: _fire_trigger("pynput(Cmd+Shift+G)"),
            "<ctrl>+<alt>+<shift>+q": lambda: _fire_secret("pynput(Ctrl+Alt+Shift+Q)"),
            "<cmd>+<alt>+<shift>+q": lambda: _fire_secret("pynput(Cmd+Alt+Shift+Q)"),
        }
        pynput_listener = keyboard.GlobalHotKeys(hotkey_bindings)
        pynput_listener.daemon = True
        pynput_listener.start()
    except Exception:
        try:
            from pynput import keyboard

            def _on_pynput_press(key) -> None:
                if overlay.isVisible():
                    return
                if key == keyboard.Key.f8:
                    bridge.triggerRequested.emit("pynput(F8)")

            pynput_listener = keyboard.Listener(on_press=_on_pynput_press)
            pynput_listener.daemon = True
            pynput_listener.start()
        except Exception:
            pass

    # Allow Ctrl+C in terminal to cleanly exit Qt event loop
    signal.signal(signal.SIGINT, lambda *_: bridge.stopRequested.emit())
    sigint_timer = QTimer()
    sigint_timer.start(250)
    sigint_timer.timeout.connect(lambda: None)

    # Pre-warm local VLM in background thread (skipped for Gemini API cloud mode)
    if dev_code != "gemini":
        temperature = float(tier_cfg.get("temperature", 0.12))
        threading.Thread(
            target=warmup_local_model,
            args=(
                ollama_host,
                model_name,
                "30m",
                temperature,
                dev_code,
                int(tier_cfg.get("num_ctx", 10240)),
            ),
            name="AILensWarmup",
            daemon=True,
        ).start()

    level_disp = get_thinking_level_display(level_code, "en", dev_code)
    dev_disp = get_compute_device_display(dev_code, "en")
    is_mac = sys.platform == "darwin"
    shortcuts_str = (
        " [Option + F8]  |  [F8]  |  [Cmd + Shift + G]"
        if is_mac
        else " [Alt + F8]  |  [F8]  |  [Ctrl + Alt + Shift + G]"
    )
    secret_str = (
        " [Cmd + Option + Shift + Q] (text drag, concise direct answer)"
        if is_mac
        else " [Ctrl + Alt + Shift + Q] (text drag, concise direct answer)"
    )
    print("=" * 74, flush=True)
    if dev_code == "gemini":
        print(" AI Lens RUNNING IN STANDBY (Google Gemini API — RAM-only key)", flush=True)
        print(f" Gemini AI Model      : {active_model}", flush=True)
        print(f" Language (UI + AI)   : {get_language_display(lang_code)}", flush=True)
        print(
            f" Thinking Depth       : {level_disp} (max {tier_cfg['num_predict']} tokens)",
            flush=True,
        )
        print(f" Compute / Provider   : {dev_disp}", flush=True)
        print(" Key Security         : 100% RAM-only (key is not stored on disk, cleared on exit)", flush=True)
        print(f" Shortcuts            :{shortcuts_str}", flush=True)
        print(f" Secret Mode (Fast)   :{secret_str}", flush=True)
        print(" Green Status Dot     : Mini dot at top-right corner (click to exit AI Lens immediately)", flush=True)
        print(" Close Overlay        : [Esc] key, click outside card, or right mouse button", flush=True)
        print(" Privacy Protection   : 100% RAM-only (selection and chat cleared from RAM upon closing)", flush=True)
    else:
        print(" AI Lens RUNNING IN STANDBY (Green Dot + Triple Shortcut Detection)", flush=True)
        print(f" Local AI Model       : {model_name}", flush=True)
        print(f" Language (UI + AI)   : {get_language_display(lang_code)}", flush=True)
        print(
            f" Thinking Depth       : {level_disp} (max {tier_cfg['num_predict']} tokens, context {tier_cfg['num_ctx']})",
            flush=True,
        )
        print(f" Compute / Device     : {dev_disp}", flush=True)
        print(f" Shortcuts            :{shortcuts_str}", flush=True)
        print(f" Secret Mode (Fast)   :{secret_str}", flush=True)
        print(" Green Status Dot     : Mini dot at top-right corner (click to exit AI Lens immediately)", flush=True)
        print(" Close Overlay        : [Esc] key, click outside card, or right mouse button", flush=True)
        print(" Privacy Protection   : 100% RAM-only (selection and chat cleared from RAM upon closing)", flush=True)
    print("=" * 74, flush=True)

    if open_immediately:
        QTimer.singleShot(150, lambda: bridge.triggerRequested.emit("start"))

    try:
        app.exec()
    finally:
        _clear_daemon_state()
        if clear_volatile_gemini_api_key():
            print(
                "[AI Lens] Gemini API key was securely wiped from short-term memory (RAM).",
                flush=True,
            )
        if pynput_listener is not None:
            try:
                pynput_listener.stop()
            except Exception:
                pass
