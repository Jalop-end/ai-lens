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

from PyQt6.QtCore import QObject, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QMouseEvent
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
    set_language_in_config,
    set_thinking_level_in_config,
)
from ai_lens.vision_engine import (
    get_language_display,
    get_thinking_level_config,
    get_thinking_level_display,
    get_ui_strings,
    normalize_language_code,
    normalize_thinking_level,
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
    Sleek, draggable floating mini-dock on the screen edge ('AI Lens [Alt+F8]').
    Can be minimized into a razor-thin unobtrusive 'čárka' (dash) that covers nothing,
    and expanded back on a single click or double-click.
    """

    triggerClicked = pyqtSignal()
    quitClicked = pyqtSignal()

    STYLE_EXPANDED = """
        QFrame#FloatingTriggerBar {
            background-color: rgba(15, 23, 42, 235);
            border: 1.5px solid #38BDF8;
            border-radius: 18px;
        }
        QPushButton#ActionBtn {
            background-color: transparent;
            color: #F8FAFC;
            border: none;
            font-family: "Segoe UI", system-ui, sans-serif;
            font-size: 12px;
            font-weight: 600;
            padding: 6px 12px;
        }
        QPushButton#ActionBtn:hover {
            color: #38BDF8;
        }
        QPushButton#MinBtn {
            background-color: transparent;
            color: #94A3B8;
            border: none;
            font-size: 14px;
            font-weight: bold;
            padding: 4px 6px;
        }
        QPushButton#MinBtn:hover {
            color: #38BDF8;
        }
        QPushButton#QuitBtn {
            background-color: transparent;
            color: #94A3B8;
            border: none;
            font-size: 12px;
            font-weight: bold;
            padding: 4px 8px;
        }
        QPushButton#QuitBtn:hover {
            color: #F87171;
        }
    """

    STYLE_MINIMIZED = """
        QFrame#FloatingTriggerBar {
            background-color: rgba(15, 23, 42, 220);
            border: 1px solid rgba(56, 189, 248, 180);
            border-radius: 5px;
        }
        QFrame#FloatingTriggerBar:hover {
            background-color: rgba(30, 41, 59, 245);
            border: 1.5px solid #38BDF8;
        }
        QFrame#DashLine {
            background-color: #38BDF8;
            border-radius: 1.5px;
        }
        QFrame#FloatingTriggerBar:hover QFrame#DashLine {
            background-color: #7DD3FC;
        }
    """

    def __init__(self, language: str = "cs", thinking_level: str = "medium") -> None:
        super().__init__(None)
        self.setObjectName("FloatingTriggerBar")
        self.setWindowTitle("AI Lens Mini-Dock")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self._drag_offset: Optional[QPoint] = None
        self._drag_start_pos: Optional[QPoint] = None
        self._has_dragged = False
        self._is_minimized = False

        self.lang_code = normalize_language_code(language)
        self.level_norm = normalize_thinking_level(thinking_level)
        self.tier_cfg = get_thinking_level_config(self.level_norm)
        self.ui = get_ui_strings(self.lang_code)

        # Root layout
        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Full Container (Expanded Mode)
        self._full_container = QWidget(self)
        full_layout = QHBoxLayout(self._full_container)
        full_layout.setContentsMargins(6, 2, 6, 2)
        full_layout.setSpacing(2)

        self.trigger_btn = QPushButton(
            f"🔍 AI Lens [{self.lang_code.upper()} · {self.tier_cfg['label']}] (Alt+F8)",
            self._full_container,
        )
        self.trigger_btn.setObjectName("ActionBtn")
        self.trigger_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.trigger_btn.setToolTip(self.ui["dock_tooltip"])
        self.trigger_btn.clicked.connect(self.triggerClicked.emit)

        self.min_btn = QPushButton("—", self._full_container)
        self.min_btn.setObjectName("MinBtn")
        self.min_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.min_btn.setToolTip(
            self.ui.get("dock_minimize_tooltip", "Zmenšit do tenké čárky (aby nic nezakrýval)")
        )
        self.min_btn.clicked.connect(self.collapse)

        self.quit_btn = QPushButton("✕", self._full_container)
        self.quit_btn.setObjectName("QuitBtn")
        self.quit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.quit_btn.setToolTip(self.ui["dock_quit_tooltip"])
        self.quit_btn.clicked.connect(self.quitClicked.emit)

        full_layout.addWidget(self.trigger_btn)
        full_layout.addWidget(self.min_btn)
        full_layout.addWidget(self.quit_btn)

        # 2. Dash Container (Minimized 'Čárka' Mode)
        self._dash_container = QWidget(self)
        dash_layout = QHBoxLayout(self._dash_container)
        dash_layout.setContentsMargins(8, 2, 8, 2)
        dash_layout.setSpacing(0)

        self._dash_line = QFrame(self._dash_container)
        self._dash_line.setObjectName("DashLine")
        self._dash_line.setFixedHeight(3)
        self._dash_line.setFixedWidth(36)
        dash_layout.addWidget(self._dash_line, alignment=Qt.AlignmentFlag.AlignCenter)
        self._dash_container.hide()

        root_layout.addWidget(self._full_container)
        root_layout.addWidget(self._dash_container)

        self.setStyleSheet(self.STYLE_EXPANDED)
        self.adjustSize()

        # Position at top-right of primary screen
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            x = geom.right() - self.width() - 24
            y = geom.top() + 18
            self.move(max(10, x), max(10, y))

    def collapse(self) -> None:
        """Minimizes the floating pill into a sleek, unobtrusive thin dash ('čárka')."""
        if self._is_minimized:
            return
        top_right = self.geometry().topRight()
        self._is_minimized = True
        self._full_container.hide()
        self._dash_container.show()
        self.setStyleSheet(self.STYLE_MINIMIZED)
        self.setFixedSize(54, 9)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self.ui.get("dock_expand_tooltip", "AI Lens (kliknutím rozbalit / Alt+F8)"))

        # Keep anchored to the top-right position
        self.move(max(10, top_right.x() - 54), top_right.y())

    def expand(self) -> None:
        """Expands the thin dash back into the full mini-dock."""
        if not self._is_minimized:
            return
        top_right = self.geometry().topRight()
        self._is_minimized = False
        self._dash_container.hide()
        self._full_container.show()
        self.setStyleSheet(self.STYLE_EXPANDED)
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.adjustSize()
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setToolTip("")

        # Anchor to top-right without overflowing left edge
        target_x = max(10, top_right.x() - self.width())
        self.move(target_x, top_right.y())

    def toggle_minimized(self) -> None:
        """Toggles between full mini-dock and thin dash ('čárka')."""
        if self._is_minimized:
            self.expand()
        else:
            self.collapse()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.globalPosition().toPoint()
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._has_dragged = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            if self._drag_start_pos is not None:
                delta = (event.globalPosition().toPoint() - self._drag_start_pos).manhattanLength()
                if delta > 4:
                    self._has_dragged = True
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            # If user clicked on the minimized dash without dragging -> expand!
            if self._is_minimized and not self._has_dragged:
                self.expand()
            self._drag_offset = None
            self._drag_start_pos = None
            self._has_dragged = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_minimized()
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu(self)
        menu.setStyleSheet(
            """
            QMenu {
                background-color: #0F172A;
                color: #F8FAFC;
                border: 1px solid #38BDF8;
                border-radius: 8px;
                padding: 4px;
                font-family: "Segoe UI", system-ui, sans-serif;
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 14px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #1E293B;
                color: #38BDF8;
            }
            """
        )
        toggle_label = "🔍 Rozbalit panel" if self._is_minimized else "— Zmenšit do čárky"
        toggle_action = menu.addAction(toggle_label)
        toggle_action.triggered.connect(self.toggle_minimized)

        trigger_action = menu.addAction("📷 Spustit výběr (Alt+F8)")
        trigger_action.triggered.connect(self.triggerClicked.emit)

        menu.addSeparator()
        quit_action = menu.addAction("✕ Ukončit AI Lens")
        quit_action.triggered.connect(self.quitClicked.emit)

        menu.exec(event.globalPos())


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


def _read_daemon_state() -> Optional[dict[str, int]]:
    """Reads PID and Win32 Hotkey Thread ID (TID) of a running daemon from .ai_lens_state.json."""
    if not STATE_FILE_PATH.exists():
        return None
    try:
        data = json.loads(STATE_FILE_PATH.read_text(encoding="utf-8"))
        pid = int(data.get("pid", 0))
        tid = int(data.get("tid", 0))
        if _is_pid_alive(pid):
            return {"pid": pid, "tid": tid}
    except Exception:
        pass
    try:
        STATE_FILE_PATH.unlink(missing_ok=True)
    except Exception:
        pass
    return None


def _write_daemon_state(pid: int, tid: int) -> None:
    """Saves the current daemon PID and Win32 Hotkey Thread ID to .ai_lens_state.json."""
    try:
        STATE_FILE_PATH.write_text(
            json.dumps({"pid": pid, "tid": tid}, indent=2),
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
        if cmd == "STOP" and tid:
            ok = bool(user32.PostThreadMessageW(tid, WM_HOTKEY, HOTKEY_ID_STOP, 0))
            return "OK:STOPPING" if ok else None

    return None


class DaemonBridge(QObject):
    """Thread-safe Qt signal bridge from Win32/pynput hotkey threads to Qt GUI thread."""

    triggerRequested = pyqtSignal(str)
    stopRequested = pyqtSignal()


def run_daemon(
    open_immediately: bool = False,
    language: Optional[str] = None,
    thinking_level: Optional[str] = None,
) -> None:
    """
    Starts AI Lens from the Command Line:
      - Zero TCP/IP listening sockets (completely invisible to Windows Firewall).
      - Shows a sleek FloatingTriggerBar ('🔍 AI Lens (Alt+F8)') at top-right of screen
        for 1-click mouse activation AND visual confirmation.
      - Triple-Engine Hotkey Detection for Alt+F8, F8, Ctrl+Shift+G, and Ctrl+Alt+Shift+G:
          1. Win32 RegisterHotKey in a dedicated pure-Python GetMessageW thread.
          2. 15ms GetAsyncKeyState hardware poller in QTimer.
          3. pynput low-level keyboard listener fallback.
    """
    _ensure_utf8_stdio()
    _disable_console_quickedit()

    if language:
        set_language_in_config(language)
    if thinking_level:
        set_thinking_level_in_config(thinking_level)

    existing = _read_daemon_state()
    if existing is not None:
        cfg_now = load_config()
        lang_code_now = str(cfg_now.get("language", "cs"))
        lang_disp = get_language_display(lang_code_now)
        level_disp = get_thinking_level_display(
            str(cfg_now.get("thinking_level", "medium")), lang_code_now
        )
        _log_debug(
            f"[AI Lens] Proces již běží (PID {existing['pid']}, jazyk: {lang_disp}, hloubka myšlení: {level_disp}). Aktivuji překryvné okno…"
        )
        send_daemon_command("TRIGGER")
        return

    config = load_config()
    hotkey_str = str(config.get("hotkey", "<alt>+<f8>"))
    model_name = str(config.get("model", "gemma4:latest"))
    ollama_host = str(config.get("ollama_host", "http://127.0.0.1:11434"))
    lang_code = str(config.get("language", "cs"))
    level_code = str(config.get("thinking_level", "medium"))
    tier_cfg = get_thinking_level_config(level_code)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    overlay = OverlayWindow(config=config, daemon_mode=True)
    floating_bar = FloatingTriggerBar(language=lang_code, thinking_level=level_code)
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

        # Hide floating mini-bar BEFORE capturing screen so it isn't in the screenshot
        if floating_bar.isVisible():
            floating_bar.hide()
            QApplication.processEvents()

        capture_ms = overlay.activate_overlay()
        backend = overlay.capture_result.capture_backend if overlay.capture_result else "unknown"
        _log_debug(
            f"[AI Lens] Aktivace ({source}) -> obrazovka ({backend}) zmrazena za {capture_ms:.1f} ms."
        )

    def _on_stop() -> None:
        _log_debug("[AI Lens] Ukončuji AI Lens…")
        _clear_daemon_state()
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
            if (mods, vk) not in (
                (MOD_ALT | MOD_NOREPEAT, VK_F8),
                (MOD_NOREPEAT, VK_F8),
                (MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, ord("G")),
                (MOD_CONTROL | MOD_ALT | MOD_SHIFT | MOD_NOREPEAT, ord("G")),
            ):
                u32.RegisterHotKey(None, HOTKEY_ID_CUSTOM, mods, vk)

            _log_debug(
                f"[AI Lens] Win32 RegisterHotKey stav: Alt+F8={bool(r_alt_f8)}, "
                f"F8={bool(r_f8)}, Ctrl+Shift+G={bool(r_csg)}, Ctrl+Alt+Shift+G={bool(r_casg)}"
            )

            _write_daemon_state(os.getpid(), hotkey_thread_tid)
            ready_event.set()

            while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    wp = int(msg.wParam)
                    if wp == HOTKEY_ID_STOP:
                        bridge.stopRequested.emit()
                        break
                    bridge.triggerRequested.emit(f"WM_HOTKEY(id={wp})")

            for hid in (
                HOTKEY_ID_ALT_F8,
                HOTKEY_ID_F8,
                HOTKEY_ID_CTRL_SHIFT_G,
                HOTKEY_ID_CTRL_ALT_SHIFT_G,
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

            alt_f8 = alt_down and f8_down
            just_f8 = f8_down
            ctrl_shift_g = ctrl_down and shift_down and g_down
            custom_combo = all(_is_down(k) for k in vk_list)

            triggered = alt_f8 or just_f8 or ctrl_shift_g or custom_combo
            if triggered and not combo_was_down:
                combo_was_down = True
                label = "Alt+F8" if alt_f8 else ("F8" if just_f8 else "Ctrl+Shift+G")
                bridge.triggerRequested.emit(f"GetAsyncKeyState({label})")
            elif not triggered:
                combo_was_down = False

        poll_timer = QTimer()
        poll_timer.setInterval(15)
        poll_timer.timeout.connect(_poll_hardware_keys)
        poll_timer.start()

    # Engine 3: pynput low-level keyboard listener fallback
    pynput_listener = None
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

    # Pre-warm local VLM in background thread
    temperature = float(tier_cfg.get("temperature", 0.15))
    threading.Thread(
        target=warmup_local_model,
        args=(ollama_host, model_name, "30m", temperature),
        name="AILensWarmup",
        daemon=True,
    ).start()

    level_disp = get_thinking_level_display(level_code, lang_code)
    print("=" * 74, flush=True)
    print(" AI Lens BĚŽÍ V POHOTOVOSTI (Plovoucí lišta + Trojitá detekce zkratky)", flush=True)
    print(f" Lokální AI model  : {model_name}", flush=True)
    print(f" Jazyk (UI + AI)   : {get_language_display(lang_code)}", flush=True)
    print(
        f" Hloubka myšlení   : {level_disp} (max {tier_cfg['num_predict']} tokenů, kontext {tier_cfg['num_ctx']})",
        flush=True,
    )
    print(" Zkratky           : [Alt + F8]  |  [F8]  |  [Ctrl + Alt + Shift + G]", flush=True)
    print(" Plovoucí tlačítko : Nahoře vpravo na obrazovce 'AI Lens (Alt+F8)'", flush=True)
    print(" Zavření overlaye  : Klávesa [Esc] nebo pravé tlačítko myši", flush=True)
    print(" Ochrana soukromí  : 100% RAM-only (okamžité vymazání výřezu i chatu po zavření)", flush=True)
    print("=" * 74, flush=True)

    if open_immediately:
        QTimer.singleShot(150, lambda: bridge.triggerRequested.emit("start"))

    try:
        app.exec()
    finally:
        _clear_daemon_state()
        if pynput_listener is not None:
            try:
                pynput_listener.stop()
            except Exception:
                pass
