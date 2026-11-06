"""PyQt6 fullscreen frameless overlay with unmistakable visual HUD, 2px+ white border, freehand lasso, Bounding Box crop, Popover UI, and QThread VLM streaming."""

from __future__ import annotations

import ctypes
import gc
import json
import math
import sys
from pathlib import Path
from typing import Any, Optional

from PIL import Image
from PyQt6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QApplication, QWidget

from ai_lens.capture import (
    ScreenCaptureResult,
    capture_screen,
    compute_bounding_box,
    crop_from_capture,
)
from ai_lens.popover import PopoverCard, SecretTopBar
from ai_lens.vision_engine import (
    DEFAULT_GEMINI_MODEL,
    DEFAULT_PROMPTS_BY_LANG,
    THINKING_LEVELS,
    VisionInferenceWorker,
    build_secret_system_prompt,
    choose_gemini_model_interactive,
    clear_volatile_gemini_api_key,
    encode_pil_to_base64,
    get_volatile_gemini_model,
    get_compute_device_display,
    get_default_prompt,
    get_language_display,
    get_secret_prompt,
    get_thinking_level_config,
    get_thinking_level_display,
    get_ui_strings,
    has_volatile_gemini_api_key,
    normalize_compute_device,
    normalize_language_code,
    normalize_thinking_level,
    prompt_for_gemini_api_key,
    validate_local_ollama_host,
)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
_LEGACY_CROP_PATH = Path(__file__).resolve().parent.parent / "last_crop.png"


def _purge_legacy_disk_traces() -> None:
    """Ensures any legacy debug crop file from older versions is permanently deleted from disk."""
    try:
        if _LEGACY_CROP_PATH.exists():
            _LEGACY_CROP_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _ensure_utf8_stdio() -> None:
    """Prevents UnicodeEncodeError on Windows cp1250/cp852 terminals."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load configuration from config.json with strict security validation and bounds clamping."""
    _purge_legacy_disk_traces()
    defaults: dict[str, Any] = {
        "hotkey": "<alt>+<f8>",
        "border_width": 3,
        "border_color": "#FFFFFF",
        "padding": 4,
        "ollama_host": "http://127.0.0.1:11434",
        "model": "gemma4:latest",
        "language": "cs",
        "thinking_level": "medium",
        "compute_device": "gpu",
        "think": True,
        "enable_code_execution": False,
        "temperature": 0.12,
        "default_prompt": get_default_prompt("cs"),
    }
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                # Never load any persisted API key from disk; API keys are strictly RAM-only
                data.pop("gemini_api_key", None)
                data.pop("api_key", None)
                defaults.update(data)
        except Exception:
            pass
    defaults["language"] = normalize_language_code(str(defaults.get("language", "cs")))
    defaults["enable_code_execution"] = defaults.get("enable_code_execution") is True
    defaults["thinking_level"] = normalize_thinking_level(
        str(defaults.get("thinking_level", "medium"))
    )
    raw_dev = normalize_compute_device(str(defaults.get("compute_device", "gpu")))
    if has_volatile_gemini_api_key():
        defaults["compute_device"] = "gemini"
    else:
        defaults["compute_device"] = "cpu" if raw_dev == "cpu" else "gpu"
    defaults["ollama_host"] = validate_local_ollama_host(str(defaults.get("ollama_host", "")))
    try:
        defaults["padding"] = max(0, min(200, int(defaults.get("padding", 4))))
    except Exception:
        defaults["padding"] = 4
    try:
        defaults["border_width"] = max(1, min(20, int(defaults.get("border_width", 3))))
    except Exception:
        defaults["border_width"] = 3
    try:
        defaults["temperature"] = max(0.0, min(2.0, float(defaults.get("temperature", 0.12))))
    except Exception:
        defaults["temperature"] = 0.12
    return defaults


def set_language_in_config(lang: str, config_path: Path = DEFAULT_CONFIG_PATH) -> str:
    """Updates the active response language (and localized default prompt) in config.json."""
    cfg = load_config(config_path)
    code = normalize_language_code(lang)
    cfg["language"] = code
    cfg["default_prompt"] = get_default_prompt(code)
    disk_cfg = dict(cfg)
    if disk_cfg.get("compute_device") == "gemini":
        disk_cfg["compute_device"] = "gpu"
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(disk_cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return code


def set_thinking_level_in_config(level: str, config_path: Path = DEFAULT_CONFIG_PATH) -> str:
    """Updates the active thinking level ('low', 'medium', 'high') and corresponding parameters in config.json."""
    cfg = load_config(config_path)
    norm = normalize_thinking_level(level)
    tier = get_thinking_level_config(norm)
    cfg["thinking_level"] = norm
    cfg["think"] = bool(tier["think"])
    cfg["temperature"] = float(tier["temperature"])
    disk_cfg = dict(cfg)
    if disk_cfg.get("compute_device") == "gemini":
        disk_cfg["compute_device"] = "gpu"
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(disk_cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return norm


def set_compute_device_in_config(device: str, config_path: Path = DEFAULT_CONFIG_PATH) -> str:
    """
    Updates the active compute device ('gpu' or 'cpu') in config.json.
    Note: 'gemini' mode is strictly short-term RAM-only and is never persisted to config.json.
    """
    cfg = load_config(config_path)
    norm = normalize_compute_device(device)
    if norm == "gemini":
        return "gemini"
    cfg["compute_device"] = norm
    cfg.pop("gemini_api_key", None)
    cfg.pop("api_key", None)
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return norm



class OverlayWindow(QWidget):
    """
    Frameless fullscreen overlay window that:
      1. Freezes the screen with a visible white perimeter frame and top HUD pill.
      2. Lets the user draw a freehand lasso with the mouse (QPainterPath).
      3. Computes the padded Bounding Box [xmin - p, ymin - p, xmax + p, ymax + p].
      4. Crops the clean original screenshot and displays the floating PopoverCard next to it.
      5. Streams the local VLM response in real time via a background QThread.
    """

    regionSelected = pyqtSignal(object, QRect, str)  # (PIL.Image, QRect, prompt)
    overlayDismissed = pyqtSignal()

    def __init__(self, config: Optional[dict[str, Any]] = None, daemon_mode: bool = False) -> None:
        super().__init__()
        self.config = config or load_config()
        self.daemon_mode = daemon_mode
        self.capture_result: Optional[ScreenCaptureResult] = None

        # Lasso, text selection & crop state
        self._is_drawing: bool = False
        self._is_secret_mode: bool = False
        self._drag_start_pos: Optional[QPointF] = None
        self._drag_current_pos: Optional[QPointF] = None
        self._lasso_points: list[QPointF] = []
        self._lasso_path = QPainterPath()
        self._selected_bbox: QRect = QRect()
        self._last_cropped_image: Optional[Image.Image] = None

        # Local VLM streaming state
        self._worker: Optional[VisionInferenceWorker] = None
        self._chat_history: list[dict[str, Any]] = []
        self._current_reply_buffer: str = ""

        self.setWindowTitle("AI Lens Overlay")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, not daemon_mode)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)

        # Floating Popover Card (standard mode)
        self.popover = PopoverCard(self)
        self.popover.hide()
        self.popover.closeRequested.connect(self.dismiss_overlay)
        self.popover.promptSubmitted.connect(self._on_followup_prompt)

        # Secret Quick-Answer Top Bar (secret mode)
        self.secret_top_bar = SecretTopBar(self)
        self.secret_top_bar.hide()
        self.secret_top_bar.closeRequested.connect(self.dismiss_overlay)

        # Bounding Box reasoning pulse animation
        self._is_inferring: bool = False
        self._bbox_pulse_phase: float = 0.0
        self._bbox_pulse_timer = QTimer(self)
        self._bbox_pulse_timer.setInterval(35)  # ~28 FPS
        self._bbox_pulse_timer.timeout.connect(self._on_bbox_pulse_tick)

        # Hard 40-second inference watchdog ("pojistka 40 s")
        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setSingleShot(True)
        self._watchdog_timer.timeout.connect(self._on_inference_watchdog_timeout)

    def _on_bbox_pulse_tick(self) -> None:
        if not self._is_inferring:
            self._bbox_pulse_timer.stop()
            return
        self._bbox_pulse_phase += 0.08
        if self._bbox_pulse_phase > 2.0 * math.pi:
            self._bbox_pulse_phase -= 2.0 * math.pi
        self.update()

    def _on_inference_watchdog_timeout(self) -> None:
        """Use the worker's total budget; tool activity never adds 60 extra seconds."""
        if not self._is_inferring and self._worker is None:
            return
        limit = self._worker.inference_limit if self._worker is not None else 40.0
        if self._worker is not None and self._worker._remaining_budget() > 0:
            self._watchdog_timer.start(max(1, int(self._worker._remaining_budget() * 1000)))
            return
        self._stop_active_worker()
        self.update()
        lang_code = normalize_language_code(str(self.config.get("language", "cs")))
        is_cz_sk = lang_code in ("cs", "sk")

        if self._is_secret_mode or self.secret_top_bar.isVisible():
            if not self._current_reply_buffer.strip():
                msg = (
                    f"Vypršel limit {limit:.0f} s; dotaz byl automaticky ukončen."
                    if is_cz_sk
                    else f"{limit:.0f} s limit reached; query automatically stopped."
                )
                self.secret_top_bar.set_content(msg)
            else:
                self.secret_top_bar.set_content(
                    self._current_reply_buffer + (
                        "\n\nOdpověď je neúplná (časový limit)." if is_cz_sk else
                        "\n\nResponse incomplete (time limit)."))
            return

        if self._current_reply_buffer.strip():
            badge = f"Nedokončeno · limit {limit:.0f} s" if is_cz_sk else f"Incomplete · {limit:.0f} s limit"
            self.popover.stop_loading(badge)
        else:
            badge = f"Ukončeno (limit {limit:.0f} s)" if is_cz_sk else f"Stopped ({limit:.0f} s limit)"
            msg = (
                f"**Časový limit {limit:.0f} s vypršel**\n\n"
                "Dotaz byl ukončen. Zkus menší nebo čitelnější výřez; High zůstává zachováno."
                if is_cz_sk
                else f"**{limit:.0f} s Time Limit Reached**\n\n"
                     "The request was stopped. High remains unchanged."
            )
            self.popover.stop_loading(badge)
            self.popover.set_markdown_content(msg)

    def _on_execution_status(self, worker: VisionInferenceWorker, text: str) -> None:
        if self._worker is not worker or not self._is_inferring:
            return
        remaining = worker._remaining_budget()
        if remaining <= 0:
            self._on_inference_watchdog_timeout()
            return
        self._watchdog_timer.start(max(1, int(remaining * 1000)))
        target = self.secret_top_bar if self._is_secret_mode else self.popover
        target.on_execution_status(text)

    def _on_answer_reset(self, worker: VisionInferenceWorker) -> None:
        """Retract a provisional tool answer if the model retries or is interrupted."""
        if self._worker is not worker or not self._is_inferring:
            return
        self._current_reply_buffer = ""
        if self._is_secret_mode:
            self.secret_top_bar.set_content("")
        else:
            self.popover.set_markdown_content("")

    def _force_win32_foreground(self) -> None:
        """
        Forces Windows 10/11 to place the overlay on top of all windows and grant focus,
        using SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW so High-DPI 4K geometry is preserved.
        """
        if sys.platform != "win32":
            return
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            fg_hwnd = user32.GetForegroundWindow()
            fg_tid = user32.GetWindowThreadProcessId(ctypes.c_void_p(fg_hwnd), None) if fg_hwnd else 0
            cur_tid = kernel32.GetCurrentThreadId()

            attached = False
            if fg_tid and fg_tid != cur_tid:
                attached = bool(user32.AttachThreadInput(fg_tid, cur_tid, True))

            # SWP_NOSIZE (0x0001) | SWP_NOMOVE (0x0002) | SWP_SHOWWINDOW (0x0040) = 0x0043
            SWP_FLAGS = 0x0001 | 0x0002 | 0x0040
            user32.SetWindowPos(
                ctypes.c_void_p(hwnd),
                ctypes.c_void_p(-1),  # HWND_TOPMOST
                0,
                0,
                0,
                0,
                SWP_FLAGS,
            )
            user32.BringWindowToTop(ctypes.c_void_p(hwnd))
            user32.SetForegroundWindow(ctypes.c_void_p(hwnd))
            user32.SetFocus(ctypes.c_void_p(hwnd))

            if attached:
                user32.AttachThreadInput(fg_tid, cur_tid, False)
        except Exception:
            pass

    def _stop_active_worker(self) -> None:
        """Cancels any running QThread inference worker, breaks open sockets, and scrubs its RAM buffers."""
        self._is_inferring = False
        if hasattr(self, "_watchdog_timer") and self._watchdog_timer.isActive():
            self._watchdog_timer.stop()
        if hasattr(self, "_bbox_pulse_timer") and self._bbox_pulse_timer.isActive():
            self._bbox_pulse_timer.stop()
        if self._worker is not None:
            worker = self._worker
            self._worker = None
            try:
                worker.cancel()
                worker.clear_memory()
                worker.tokenReceived.disconnect()
                worker.thinkingProgress.disconnect()
                worker.executionStatus.disconnect()
                worker.answerReset.disconnect()
                worker.finishedInference.disconnect()
                worker.errorOccurred.disconnect()
            except Exception:
                pass
            if worker.isRunning():
                worker.wait(350)

    def reset_selection(self) -> None:
        """
        Immediately erases the current lasso/rectangle path, cropped image, base64 history,
        and Popover/Secret chat text from RAM as soon as the selection/chat is closed.
        """
        self._stop_active_worker()
        self._is_drawing = False
        self._drag_start_pos = None
        self._drag_current_pos = None
        self._lasso_points.clear()
        self._lasso_path = QPainterPath()
        self._selected_bbox = QRect()

        if self._last_cropped_image is not None:
            try:
                self._last_cropped_image.close()
            except Exception:
                pass
            self._last_cropped_image = None

        for entry in self._chat_history:
            if isinstance(entry, dict):
                entry.clear()
        self._chat_history.clear()
        self._current_reply_buffer = ""

        self.popover.clear_sensitive_data()
        self.popover.hide()
        self.secret_top_bar.clear_sensitive_data()
        self.secret_top_bar.hide()
        gc.collect()
        self.update()

    def activate_overlay(self, secret_mode: bool = False) -> float:
        """
        Captures the current screen into RAM BEFORE showing the window,
        then immediately displays the fullscreen frozen overlay on top of everything.

        Args:
            secret_mode: If True, activates Secret Quick-Answer Mode (drag text selection, concise direct answer).

        Returns:
            Capture time in milliseconds.
        """
        self.config = load_config()
        self._is_secret_mode = secret_mode
        lang_code = normalize_language_code(str(self.config.get("language", "cs")))
        thinking_level = normalize_thinking_level(str(self.config.get("thinking_level", "medium")))
        self.popover.set_locale(lang_code, thinking_level)
        self.reset_selection()

        if secret_mode:
            self.setCursor(Qt.CursorShape.IBeamCursor)
        else:
            self.setCursor(Qt.CursorShape.CrossCursor)

        if self.isVisible():
            self.hide()
            QApplication.processEvents()

        screen = QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio() if screen else 1.0

        # Step 1: Capture screen before showing any window
        self.capture_result = capture_screen(monitor_index=1, device_pixel_ratio=dpr)

        # Position overlay across the primary screen's logical geometry
        if screen is not None:
            geom = screen.geometry()
            self.setGeometry(geom)
        else:
            mon = self.capture_result.monitor_rect
            self.setGeometry(mon["left"], mon["top"], mon["width"], mon["height"])

        self.show()
        self.raise_()
        self.activateWindow()
        self._force_win32_foreground()
        self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)
        self.update()

        return self.capture_result.capture_ms

    def dismiss_overlay(self) -> None:
        """
        Hides the overlay in daemon mode or exits in standalone mode, immediately
        purging both the cropped selection, chat history, AND the fullscreen screenshot from RAM.
        In standalone mode, also wipes the Gemini API key from short-term memory.
        """
        self.reset_selection()
        self.capture_result = None
        gc.collect()
        if self.daemon_mode:
            self.hide()
            self.overlayDismissed.emit()
            print(
                "[AI Lens] Chat and cropped selection cleared from RAM. Overlay hidden to standby (Alt+F8 for next selection).",
                flush=True,
            )
        else:
            if clear_volatile_gemini_api_key():
                print(
                    "[AI Lens] Gemini API key was securely wiped from short-term memory (RAM).",
                    flush=True,
                )
            self.close()
            app = QApplication.instance()
            if app is not None:
                app.quit()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Handles mouse press: click-away dismissal if result is showing, or starts selection."""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()

            # 1. If PopoverCard is visible:
            if self.popover.isVisible():
                if self.popover.geometry().contains(pos.toPoint()):
                    super().mousePressEvent(event)
                    return
                # Clicked outside popover -> dismiss overlay immediately
                self.dismiss_overlay()
                return

            # 2. If SecretTopBar is visible:
            if self.secret_top_bar.isVisible():
                if self.secret_top_bar.geometry().contains(pos.toPoint()):
                    super().mousePressEvent(event)
                    return
                # Clicked outside secret bar -> dismiss overlay immediately
                self.dismiss_overlay()
                return

            # 3. If a selection was already completed and user clicks elsewhere:
            if not self._selected_bbox.isNull():
                self.dismiss_overlay()
                return

            # 4. Fresh selection:
            self.reset_selection()
            self._is_drawing = True
            self._drag_start_pos = pos
            self._drag_current_pos = pos
            self._lasso_points = [pos]
            self._lasso_path = QPainterPath(pos)
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self.dismiss_overlay()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Appends cursor coordinates and updates the selection path."""
        if self._is_drawing:
            pos = event.position()
            self._drag_current_pos = pos
            self._lasso_points.append(pos)
            self._lasso_path.lineTo(pos)
            self.update()
        else:
            super().mouseMoveEvent(event)

    def _compute_secret_selection_rect(self, include_padding: bool = False) -> QRect:
        """
        Computes the full bounding box across all swept/drawn points in Secret Mode:
          - Supports diagonal rectangle drag, multi-line text sweep (never cutting off the right half
            of earlier lines), AND freehand circling identically to Standard Lasso Mode.
          - Automatically expands horizontal single-line I-beam drags vertically (>= 34 px) so tall
            capitals, diacritics (háčky/čárky), exponents, and descenders are never sliced off.
          - Adds protective padding (`pad_x >= 10`, `pad_y >= 16`) when cropping (`include_padding=True`)
            so edge glyphs sit cleanly inside ViT vision patches.
        """
        if not self._lasso_points:
            return QRect()
        xs = [p.x() for p in self._lasso_points]
        ys = [p.y() for p in self._lasso_points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        raw_w = max_x - min_x
        raw_h = max_y - min_y

        if raw_w < 8 and raw_h < 8:
            return QRect()

        # Single-line horizontal I-beam text drag: expand vertically around center so full glyph height is covered
        if raw_w >= 12 and raw_h < 38:
            cy = (min_y + max_y) / 2.0
            min_y = cy - 19.0
            max_y = cy + 19.0

        if include_padding:
            cfg_pad = int(self.config.get("padding", 4))
            pad_x = float(max(18, cfg_pad))
            pad_y = float(max(18, cfg_pad))
            min_x -= pad_x
            max_x += pad_x
            min_y -= pad_y
            max_y += pad_y

        rect = QRectF(QPointF(min_x, min_y), QPointF(max_x, max_y)).normalized().toRect()
        return rect.intersected(self.rect())

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """
        Computes the Bounding Box with tight padding, crops screenshot in RAM only,
        displays PopoverCard or SecretTopBar, and launches QThread VLM inference.
        """
        if event.button() == Qt.MouseButton.LeftButton and self._is_drawing:
            self._is_drawing = False
            pos = event.position()
            self._drag_current_pos = pos
            self._lasso_points.append(pos)
            self._lasso_path.lineTo(pos)

            if self._is_secret_mode:
                bbox = self._compute_secret_selection_rect(include_padding=True)
                if bbox.isNull() or (bbox.width() < 12 and bbox.height() < 12):
                    self.reset_selection()
                    return

                if self.capture_result is not None:
                    cropped = crop_from_capture(self.capture_result, bbox)
                    self._last_cropped_image = cropped

                # Discard marking/selection highlight immediately so it disappears upon mouse release
                self._is_drawing = False
                self._drag_start_pos = None
                self._drag_current_pos = None
                self._selected_bbox = QRect()
                self._lasso_points.clear()
                self._lasso_path = QPainterPath()

                bar_w = min(880, max(560, int(self.width() * 0.52)))
                self.secret_top_bar.setFixedWidth(bar_w)
                bar_x = (self.width() - bar_w) // 2
                bar_y = 14
                self.secret_top_bar.move(bar_x, bar_y)
                lang_code = normalize_language_code(str(self.config.get("language", "cs")))
                self.secret_top_bar.set_locale(lang_code)
                load_msg = (
                    "Řeším…"
                    if lang_code in ("cs", "sk")
                    else "Solving…"
                )
                self.secret_top_bar.start_loading(load_msg)
                self.secret_top_bar.show()
                self.secret_top_bar.raise_()
                if self._last_cropped_image is not None:
                    self._start_secret_inference(self._last_cropped_image)

                self.update()
                return
            else:
                padding = max(18, int(self.config.get("padding", 18)))
                bbox = compute_bounding_box(
                    points=self._lasso_points,
                    screen_width=self.width(),
                    screen_height=self.height(),
                    padding=padding,
                )
                if bbox.isNull() or (bbox.width() < 12 and bbox.height() < 12):
                    self.reset_selection()
                    return

            self._selected_bbox = bbox

            if self.capture_result is not None:
                cropped = crop_from_capture(self.capture_result, bbox)
                self._last_cropped_image = cropped
                self.popover.place_near_bbox(bbox, self.rect())
                lang_code = normalize_language_code(str(self.config.get("language", "cs")))
                custom_prompt = str(self.config.get("custom_prompt", "")).strip()
                default_prompt = custom_prompt if custom_prompt else get_default_prompt(lang_code)
                self.regionSelected.emit(cropped, bbox, default_prompt)
                self._start_inference(cropped, default_prompt, is_followup=False)

            self.update()
        else:
            super().mouseReleaseEvent(event)

    def _start_secret_inference(self, cropped_image: Image.Image) -> None:
        """
        Spawns VisionInferenceWorker in Secret Mode using the EXACT same thinking level,
        internal reasoning (`think`), and comprehension pipeline as Standard Lasso Mode,
        differing only in concise output length (<= 25 words, zero visible thoughts).
        """
        self._stop_active_worker()
        self._current_reply_buffer = ""
        self._is_inferring = True
        self._bbox_pulse_phase = 0.0
        self._bbox_pulse_timer.start()
        self._watchdog_timer.start(40000)

        raw_model_name = str(self.config.get("model", "gemma4:latest"))
        ollama_host = str(self.config.get("ollama_host", "http://127.0.0.1:11434"))
        lang_code = normalize_language_code(str(self.config.get("language", "cs")))
        thinking_level = normalize_thinking_level(str(self.config.get("thinking_level", "medium")))
        compute_device = normalize_compute_device(str(self.config.get("compute_device", "gpu")))
        if has_volatile_gemini_api_key():
            compute_device = "gemini"

        display_model = (
            get_volatile_gemini_model()
            if compute_device == "gemini"
            else raw_model_name
        )

        secret_sys_prompt = build_secret_system_prompt(
            lang=lang_code,
            thinking_level=thinking_level,
            compute_device=compute_device,
            model=display_model,
        )
        secret_user_prompt = get_secret_prompt(lang_code)

        worker = VisionInferenceWorker(
            image=cropped_image,
            prompt=secret_user_prompt,
            ollama_host=ollama_host,
            model=display_model,
            language=lang_code,
            thinking_level=thinking_level,
            compute_device=compute_device,
            system_prompt=secret_sys_prompt,
            history=None,
            is_secret_mode=True,
            enable_code_execution=self.config.get("enable_code_execution") is True,
            parent=self,
        )
        worker.tokenReceived.connect(self._on_secret_worker_token)
        worker.thinkingProgress.connect(self.secret_top_bar.on_thinking_progress)
        worker.executionStatus.connect(lambda text, w=worker: self._on_execution_status(w, text))
        worker.answerReset.connect(lambda w=worker: self._on_answer_reset(w))
        worker.finishedInference.connect(self._on_secret_worker_finished)
        worker.errorOccurred.connect(self._on_secret_worker_error)
        self._worker = worker
        worker.start()

    def _on_secret_worker_token(self, token: str) -> None:
        """Receives a single streamed token in Secret Mode and updates SecretTopBar."""
        self._current_reply_buffer += token
        self.secret_top_bar.append_token(token)

    def _on_secret_worker_finished(self, _elapsed: float) -> None:
        """Ensures Secret Mode stops loading even if the stream ended with zero visible tokens."""
        self._is_inferring = False
        self._watchdog_timer.stop()
        self._bbox_pulse_timer.stop()
        self.update()
        if not self._current_reply_buffer.strip():
            lang_code = normalize_language_code(str(self.config.get("language", "cs")))
            msg = (
                "Model nevrátil žádnou odpověď — zkus výřez označit znovu."
                if lang_code in ("cs", "sk")
                else "Model returned no visible answer — please try selecting again."
            )
            self.secret_top_bar.set_content(msg)
        else:
            self.secret_top_bar.stop_loading()

    def _on_secret_worker_error(self, err: str) -> None:
        """Handles errors in Secret Mode and stops the watchdog timer."""
        self._is_inferring = False
        self._watchdog_timer.stop()
        self._bbox_pulse_timer.stop()
        self.update()
        self.secret_top_bar.set_content(err)

    def _start_inference(
        self,
        cropped_image: Image.Image,
        prompt: str,
        is_followup: bool = False,
    ) -> None:
        """Spawns VisionInferenceWorker in a separate QThread and wires streaming signals."""
        self._stop_active_worker()
        self._current_reply_buffer = ""
        self._is_inferring = True
        self._bbox_pulse_phase = 0.0
        self._bbox_pulse_timer.start()
        self._watchdog_timer.start(40000)

        raw_model_name = str(self.config.get("model", "gemma4:latest"))
        ollama_host = str(self.config.get("ollama_host", "http://127.0.0.1:11434"))
        lang_code = normalize_language_code(str(self.config.get("language", "cs")))
        thinking_level = normalize_thinking_level(str(self.config.get("thinking_level", "medium")))
        compute_device = normalize_compute_device(str(self.config.get("compute_device", "gpu")))
        if has_volatile_gemini_api_key():
            compute_device = "gemini"

        display_model = (
            get_volatile_gemini_model()
            if compute_device == "gemini"
            else raw_model_name
        )
        tier_cfg = get_thinking_level_config(thinking_level, compute_device)
        ui = get_ui_strings(lang_code)

        self.popover.set_locale(lang_code, thinking_level)
        level_short = str(tier_cfg["label"])
        level_disp = get_thinking_level_display(thinking_level, lang_code, compute_device)
        system_prompt = self.config.get("system_prompt")
        dev_badge = "GEMINI API" if compute_device == "gemini" else compute_device.upper()
        self.popover.title_label.setText(
            f"AI Lens · {display_model} [{lang_code.upper()} · {level_short} · {dev_badge}]"
        )

        if not is_followup:
            self._chat_history.clear()
            self.popover.start_loading(
                ui["loading_init"].format(
                    model=display_model,
                    lang=get_language_display(lang_code),
                    level=f"{level_disp} · {dev_badge}",
                )
            )
        else:
            self.popover.start_followup_loading(prompt)

        worker = VisionInferenceWorker(
            image=cropped_image,
            prompt=prompt,
            ollama_host=ollama_host,
            model=display_model,
            language=lang_code,
            thinking_level=thinking_level,
            compute_device=compute_device,
            system_prompt=str(system_prompt) if system_prompt else None,
            history=self._chat_history if is_followup else None,
            enable_code_execution=self.config.get("enable_code_execution") is True,
            parent=self,
        )
        worker.tokenReceived.connect(self._on_worker_token)
        worker.thinkingProgress.connect(self.popover.on_thinking_progress)
        worker.executionStatus.connect(lambda text, w=worker: self._on_execution_status(w, text))
        worker.answerReset.connect(lambda w=worker: self._on_answer_reset(w))
        worker.finishedInference.connect(
            lambda elapsed, p=prompt, f=is_followup: self._on_worker_finished(elapsed, p, f)
        )
        worker.errorOccurred.connect(self._on_worker_error)
        self._worker = worker
        worker.start()

    def _on_worker_token(self, token: str) -> None:
        """Receives a single streamed token from QThread and appends it to PopoverCard."""
        if not self._current_reply_buffer and not self._chat_history:
            self.popover.set_markdown_content("")
        self._current_reply_buffer += token
        self.popover.append_token(token)

    def _on_worker_finished(self, elapsed: float, prompt: str, is_followup: bool) -> None:
        """Updates localized status badge (including generation time) and stores conversation turn."""
        self._is_inferring = False
        self._watchdog_timer.stop()
        self._bbox_pulse_timer.stop()
        self.update()
        lang_code = normalize_language_code(str(self.config.get("language", "cs")))
        thinking_level = normalize_thinking_level(str(self.config.get("thinking_level", "medium")))
        tier_cfg = get_thinking_level_config(thinking_level)
        ui = get_ui_strings(lang_code)
        self.popover.stop_loading(ui["done_time"].format(elapsed=elapsed))
        if not self._current_reply_buffer.strip():
            empty_msg = (
                "**Model nevrátil žádnou viditelnou odpověď**\n\n"
                "Zkus prosím dotaz zopakovat nebo přepnout úroveň přemýšlení."
                if lang_code in ("cs", "sk")
                else "**Model returned no visible answer**\n\nPlease try again or switch the thinking level."
            )
            self.popover.set_markdown_content(empty_msg)
            return
        if self._last_cropped_image is not None:
            if not is_followup:
                b64_img = encode_pil_to_base64(
                    self._last_cropped_image,
                    fmt="JPEG",
                    max_side=int(tier_cfg.get("max_image_side", 1408)),
                )
                self._chat_history.append(
                    {"role": "user", "content": prompt, "images": [b64_img]}
                )
            else:
                self._chat_history.append({"role": "user", "content": prompt})
            self._chat_history.append(
                {"role": "assistant", "content": self._current_reply_buffer}
            )

    def _on_worker_error(self, error_msg: str) -> None:
        """Displays any VLM connection/inference error inside PopoverCard in the selected language."""
        self._is_inferring = False
        self._watchdog_timer.stop()
        self._bbox_pulse_timer.stop()
        self.update()
        lang_code = normalize_language_code(str(self.config.get("language", "cs")))
        ui = get_ui_strings(lang_code)
        err_header = (
            ("Chyba Gemini API" if lang_code in ("cs", "sk") else "Gemini API Error")
            if has_volatile_gemini_api_key()
            else ui["err_title"]
        )
        self.popover.stop_loading(ui["conn_error"])
        self.popover.set_markdown_content(f"**{err_header}**\n\n{error_msg}")

    def _on_followup_prompt(self, prompt_text: str) -> None:
        """Handles follow-up question typed in the bottom QLineEdit of the PopoverCard."""
        if self._last_cropped_image is not None and not self._selected_bbox.isNull():
            self.regionSelected.emit(self._last_cropped_image, self._selected_bbox, prompt_text)
            self._start_inference(self._last_cropped_image, prompt_text, is_followup=True)

    def paintEvent(self, event) -> None:  # noqa: N802
        """Paints the frozen screen, unmistakable active border + localized top HUD pill, lasso trail, and Bounding Box."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1. Draw the frozen screenshot background
        if self.capture_result is not None:
            painter.drawPixmap(0, 0, self.capture_result.qpixmap)

        # 2. Dimming overlay & selection rendering
        if self._is_secret_mode:
            # Secret Mode: clean selection highlight covering all swept text/area while actively dragging.
            # Upon release, the highlight vanishes immediately so the screen is completely unmarked.
            if self._is_drawing and self._drag_start_pos and self._drag_current_pos:
                preview_rect = self._compute_secret_selection_rect(include_padding=False)
                rect = (
                    QRectF(preview_rect)
                    if not preview_rect.isNull()
                    else QRectF(self._drag_start_pos, self._drag_current_pos).normalized()
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 120, 215, 120))
                painter.drawRect(rect)
        else:
            # Standard Mode: subtle screen dimming with cutout hole & framed bounding box
            if not self._selected_bbox.isNull() and not self._is_drawing:
                outer_path = QPainterPath()
                outer_path.addRect(
                    float(self.rect().x()),
                    float(self.rect().y()),
                    float(self.width()),
                    float(self.height()),
                )
                inner_path = QPainterPath()
                inner_path.addRoundedRect(
                    float(self._selected_bbox.x()),
                    float(self._selected_bbox.y()),
                    float(self._selected_bbox.width()),
                    float(self._selected_bbox.height()),
                    4.0,
                    4.0,
                )
                dim_path = outer_path.subtracted(inner_path)
                painter.fillPath(dim_path, QColor(0, 0, 0, 105))

                if self._is_inferring:
                    pulse_alpha = int(180 + 70 * math.sin(self._bbox_pulse_phase))
                    bbox_pen = QPen(QColor(56, 189, 248, pulse_alpha))
                    bbox_pen.setWidth(2)
                    painter.setPen(bbox_pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(self._selected_bbox, 4.0, 4.0)

                    # Futuristic glowing corner brackets ┌ ┐ └ ┘
                    corner_pen = QPen(QColor(192, 132, 252, pulse_alpha))
                    corner_pen.setWidth(3)
                    painter.setPen(corner_pen)
                    bx = self._selected_bbox.x()
                    by = self._selected_bbox.y()
                    bw = self._selected_bbox.width()
                    bh = self._selected_bbox.height()
                    c_len = min(18, max(6, min(bw, bh) // 4))
                    painter.drawLine(bx, by, bx + c_len, by)
                    painter.drawLine(bx, by, bx, by + c_len)
                    painter.drawLine(bx + bw, by, bx + bw - c_len, by)
                    painter.drawLine(bx + bw, by, bx + bw, by + c_len)
                    painter.drawLine(bx, by + bh, bx + c_len, by + bh)
                    painter.drawLine(bx, by + bh, bx, by + bh - c_len)
                    painter.drawLine(bx + bw, by + bh, bx + bw - c_len, by + bh)
                    painter.drawLine(bx + bw, by + bh, bx + bw, by + bh - c_len)
                else:
                    bbox_pen = QPen(QColor("#38BDF8"))
                    bbox_pen.setWidth(2)
                    painter.setPen(bbox_pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(self._selected_bbox, 4.0, 4.0)
            else:
                painter.fillRect(self.rect(), QColor(10, 15, 28, 45))

        # 3. Draw the active freehand lasso trail only in standard mode
        if not self._is_secret_mode and not self._lasso_path.isEmpty():
            glow_pen = QPen(QColor(96, 165, 250, 130 if self._is_drawing else 55))
            glow_pen.setWidth(8)
            glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(glow_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._lasso_path)

            core_pen = QPen(QColor(255, 255, 255, 245 if self._is_drawing else 120))
            core_pen.setWidth(2)
            core_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            core_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(core_pen)
            painter.drawPath(self._lasso_path)

        # 4. Draw unmistakable inner glow + crisp white perimeter border (standard mode only)
        if not self._is_secret_mode:
            glow_border = QPen(QColor(56, 189, 248, 140))
            glow_border.setWidth(6)
            glow_border.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            painter.setPen(glow_border)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(3, 3, -3, -3))

            border_width = max(2, int(self.config.get("border_width", 3)))
            border_color = QColor(self.config.get("border_color", "#FFFFFF"))
            pen = QPen(border_color)
            pen.setWidth(border_width)
            pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            painter.setPen(pen)
            half = border_width // 2
            painter.drawRect(self.rect().adjusted(half, half, -half, -half))

        # 5. Draw localized top-center HUD pill (hidden in secret mode or if top bar is active)
        if self._is_secret_mode or self.secret_top_bar.isVisible():
            return

        lang_code = normalize_language_code(str(self.config.get("language", "cs")))
        thinking_level = normalize_thinking_level(str(self.config.get("thinking_level", "medium")))
        compute_device = (
            "gemini"
            if has_volatile_gemini_api_key()
            else normalize_compute_device(str(self.config.get("compute_device", "gpu")))
        )
        tier_cfg = get_thinking_level_config(thinking_level, compute_device)
        ui = get_ui_strings(lang_code)

        if self._is_secret_mode:
            hud_text = (
                "AI Lens [SECRET REŽIM] — Označ text myší jako při kopírování   |   [Esc] Zavřít"
                if lang_code in ("cs", "sk")
                else "AI Lens [SECRET MODE] — Drag to select text like copying   |   [Esc] Close"
            )
        else:
            hud_text = ui["hud_banner"].format(
                lang=lang_code.upper(),
                level=f"{tier_cfg['label']} · {compute_device.upper()}",
            )

        pill_w, pill_h = 590, 38
        pill_x = (self.width() - pill_w) // 2
        pill_y = 18
        pill_rect = QRectF(float(pill_x), float(pill_y), float(pill_w), float(pill_h))

        painter.setPen(QPen(QColor(255, 255, 255, 90), 1.2))
        painter.setBrush(QColor(15, 18, 26, 225))
        painter.drawRoundedRect(pill_rect, 19.0, 19.0)

        painter.setPen(QColor("#F9FAFB"))
        font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.drawText(
            pill_rect,
            Qt.AlignmentFlag.AlignCenter,
            hud_text,
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Pressing Esc immediately closes/hides the overlay."""
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss_overlay()
        else:
            super().keyPressEvent(event)


def run_overlay_mvp(
    language: Optional[str] = None,
    thinking_level: Optional[str] = None,
    compute_device: Optional[str] = None,
    secret_mode: bool = False,
) -> None:
    """Standalone launcher for immediate screen capture + overlay."""
    _ensure_utf8_stdio()
    if language:
        set_language_in_config(language)
    if thinking_level:
        set_thinking_level_in_config(thinking_level)
    if compute_device:
        norm_dev = normalize_compute_device(compute_device)
        if norm_dev == "gemini" and not has_volatile_gemini_api_key():
            eff_lang = language or str(load_config().get("language", "cs"))
            chosen_m = choose_gemini_model_interactive(eff_lang)
            prompt_for_gemini_api_key(eff_lang, chosen_model=chosen_m)
        elif norm_dev != "gemini":
            set_compute_device_in_config(compute_device)
    app = QApplication.instance() or QApplication(sys.argv)
    overlay = OverlayWindow(daemon_mode=False)
    capture_ms = overlay.activate_overlay(secret_mode=secret_mode)
    lang_code = str(overlay.config.get("language", "cs"))
    lang_disp = get_language_display(lang_code)
    dev_code = "gemini" if has_volatile_gemini_api_key() else str(overlay.config.get("compute_device", "gpu"))
    level_disp = get_thinking_level_display(str(overlay.config.get("thinking_level", "medium")), lang_code, dev_code)
    dev_disp = get_compute_device_display(dev_code, lang_code)
    active_model = get_volatile_gemini_model() if dev_code == "gemini" else overlay.config.get("model")
    print(f"[AI Lens] Screen captured into RAM in {capture_ms:.2f} ms.")
    print(
        f"[AI Lens] VLM ({active_model}, language: {lang_disp}, "
        f"thinking depth: {level_disp}, mode: {dev_disp}) ready. "
        "Draw a selection to stream response in real time. [Esc] to close."
    )
    try:
        exit_code = app.exec()
    finally:
        if clear_volatile_gemini_api_key():
            print(
                "[AI Lens] Gemini API key was securely wiped from short-term memory (RAM).",
                flush=True,
            )
    sys.exit(exit_code)


if __name__ == "__main__":
    run_overlay_mvp()
