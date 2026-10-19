"""PyQt6 fullscreen frameless overlay with unmistakable visual HUD, 2px+ white border, freehand lasso, Bounding Box crop, Popover UI, and QThread VLM streaming."""

from __future__ import annotations

import ctypes
import gc
import json
import sys
from pathlib import Path
from typing import Any, Optional

from PIL import Image
from PyQt6.QtCore import QPointF, QRect, QRectF, Qt, pyqtSignal
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
from ai_lens.popover import PopoverCard
from ai_lens.vision_engine import (
    DEFAULT_PROMPTS_BY_LANG,
    THINKING_LEVELS,
    VisionInferenceWorker,
    encode_pil_to_base64,
    get_default_prompt,
    get_language_display,
    get_thinking_level_config,
    get_thinking_level_display,
    get_ui_strings,
    normalize_language_code,
    normalize_thinking_level,
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
        "padding": 20,
        "ollama_host": "http://127.0.0.1:11434",
        "model": "gemma4:latest",
        "language": "cs",
        "thinking_level": "medium",
        "think": True,
        "temperature": 0.15,
        "default_prompt": get_default_prompt("cs"),
    }
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                defaults.update(data)
        except Exception:
            pass
    defaults["language"] = normalize_language_code(str(defaults.get("language", "cs")))
    defaults["thinking_level"] = normalize_thinking_level(
        str(defaults.get("thinking_level", "medium"))
    )
    defaults["ollama_host"] = validate_local_ollama_host(str(defaults.get("ollama_host", "")))
    try:
        defaults["padding"] = max(0, min(200, int(defaults.get("padding", 20))))
    except Exception:
        defaults["padding"] = 20
    try:
        defaults["border_width"] = max(1, min(20, int(defaults.get("border_width", 3))))
    except Exception:
        defaults["border_width"] = 3
    try:
        defaults["temperature"] = max(0.0, min(2.0, float(defaults.get("temperature", 0.15))))
    except Exception:
        defaults["temperature"] = 0.15
    return defaults


def set_language_in_config(lang: str, config_path: Path = DEFAULT_CONFIG_PATH) -> str:
    """Updates the active response language (and localized default prompt) in config.json."""
    cfg = load_config(config_path)
    code = normalize_language_code(lang)
    cfg["language"] = code
    cfg["default_prompt"] = get_default_prompt(code)
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
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

        # Lasso & crop state
        self._is_drawing: bool = False
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

        # Floating Popover Card (child widget inside the same overlay)
        self.popover = PopoverCard(self)
        self.popover.hide()
        self.popover.closeRequested.connect(self.dismiss_overlay)
        self.popover.promptSubmitted.connect(self._on_followup_prompt)

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
        """Cancels any running QThread inference worker and scrubs its RAM buffers."""
        if self._worker is not None:
            try:
                self._worker.cancel()
                self._worker.clear_memory()
                self._worker.tokenReceived.disconnect()
                self._worker.thinkingProgress.disconnect()
                self._worker.finishedInference.disconnect()
                self._worker.errorOccurred.disconnect()
            except Exception:
                pass
            self._worker = None

    def reset_selection(self) -> None:
        """
        Immediately erases the current lasso path, cropped image, base64 history,
        and Popover chat text from RAM as soon as the selection/chat is closed.
        """
        self._stop_active_worker()
        self._is_drawing = False
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
        gc.collect()
        self.update()

    def activate_overlay(self) -> float:
        """
        Captures the current screen into RAM BEFORE showing the window,
        then immediately displays the fullscreen frozen overlay on top of everything.

        Returns:
            Capture time in milliseconds.
        """
        self.config = load_config()
        lang_code = normalize_language_code(str(self.config.get("language", "cs")))
        thinking_level = normalize_thinking_level(str(self.config.get("thinking_level", "medium")))
        self.popover.set_locale(lang_code, thinking_level)
        self.reset_selection()
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
        """
        self.reset_selection()
        self.capture_result = None
        gc.collect()
        if self.daemon_mode:
            self.hide()
            self.overlayDismissed.emit()
            print(
                "[AI Lens] Chat a výřez byly vymazány z RAM. Overlay skryt do pohotovosti (Alt+F8 pro další výběr).",
                flush=True,
            )
        else:
            self.close()
            app = QApplication.instance()
            if app is not None:
                app.quit()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Starts recording the freehand lasso trajectory on left mouse button press."""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            if self.popover.isVisible() and self.popover.geometry().contains(pos.toPoint()):
                super().mousePressEvent(event)
                return

            self.reset_selection()
            self._is_drawing = True
            self._lasso_points = [pos]
            self._lasso_path = QPainterPath(pos)
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            if not self._selected_bbox.isNull():
                self.reset_selection()
            else:
                self.dismiss_overlay()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Appends cursor coordinates [x_i, y_i] and extends the smooth lasso path."""
        if self._is_drawing:
            pos = event.position()
            self._lasso_points.append(pos)
            self._lasso_path.lineTo(pos)
            self.update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """
        Computes the Bounding Box with adaptive padding, crops the clean screenshot in RAM only
        (never written to disk), displays the PopoverCard, and launches QThread VLM inference.
        """
        if event.button() == Qt.MouseButton.LeftButton and self._is_drawing:
            self._is_drawing = False
            pos = event.position()
            self._lasso_points.append(pos)
            self._lasso_path.lineTo(pos)

            padding = int(self.config.get("padding", 20))
            bbox = compute_bounding_box(
                points=self._lasso_points,
                screen_width=self.width(),
                screen_height=self.height(),
                padding=padding,
            )

            if bbox.width() < 24 and bbox.height() < 24:
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

    def _start_inference(
        self,
        cropped_image: Image.Image,
        prompt: str,
        is_followup: bool = False,
    ) -> None:
        """Spawns VisionInferenceWorker in a separate QThread and wires streaming signals."""
        self._stop_active_worker()
        self._current_reply_buffer = ""

        model_name = str(self.config.get("model", "gemma4:latest"))
        ollama_host = str(self.config.get("ollama_host", "http://127.0.0.1:11434"))
        lang_code = normalize_language_code(str(self.config.get("language", "cs")))
        thinking_level = normalize_thinking_level(str(self.config.get("thinking_level", "medium")))
        tier_cfg = get_thinking_level_config(thinking_level)
        ui = get_ui_strings(lang_code)

        self.popover.set_locale(lang_code, thinking_level)
        level_short = str(tier_cfg["label"])
        level_disp = get_thinking_level_display(thinking_level, lang_code)
        system_prompt = self.config.get("system_prompt")
        self.popover.title_label.setText(
            f"AI Lens · {model_name} [{lang_code.upper()} · {level_short}]"
        )

        if not is_followup:
            self._chat_history.clear()
            self.popover.start_loading(
                ui["loading_init"].format(
                    model=model_name,
                    lang=get_language_display(lang_code),
                    level=level_disp,
                )
            )
        else:
            self.popover.append_token(f"\n\n---\n**{ui['followup_prefix']}:** {prompt}\n\n")
            self.popover.status_label.setText(f"{ui['thinking']}…")

        worker = VisionInferenceWorker(
            image=cropped_image,
            prompt=prompt,
            ollama_host=ollama_host,
            model=model_name,
            language=lang_code,
            thinking_level=thinking_level,
            system_prompt=str(system_prompt) if system_prompt else None,
            history=self._chat_history if is_followup else None,
            parent=self,
        )
        worker.tokenReceived.connect(self._on_worker_token)
        worker.thinkingProgress.connect(self.popover.on_thinking_progress)
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
        lang_code = normalize_language_code(str(self.config.get("language", "cs")))
        thinking_level = normalize_thinking_level(str(self.config.get("thinking_level", "medium")))
        tier_cfg = get_thinking_level_config(thinking_level)
        ui = get_ui_strings(lang_code)
        self.popover.stop_loading(ui["done_time"].format(elapsed=elapsed))
        if self._last_cropped_image is not None:
            if not is_followup:
                b64_img = encode_pil_to_base64(
                    self._last_cropped_image,
                    fmt="JPEG",
                    max_side=int(tier_cfg.get("max_image_side", 1024)),
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
        """Displays any local VLM connection/inference error inside PopoverCard in the selected language."""
        lang_code = normalize_language_code(str(self.config.get("language", "cs")))
        ui = get_ui_strings(lang_code)
        self.popover.stop_loading(ui["conn_error"])
        self.popover.set_markdown_content(f"**{ui['err_title']}**\n\n{error_msg}")

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

        # 2. Dimming overlay: subtle dim when waiting for lasso, deeper dim outside selected Bounding Box
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
                6.0,
                6.0,
            )
            dim_path = outer_path.subtracted(inner_path)
            painter.fillPath(dim_path, QColor(0, 0, 0, 105))

            bbox_pen = QPen(QColor("#60A5FA"))
            bbox_pen.setWidth(2)
            painter.setPen(bbox_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self._selected_bbox, 6.0, 6.0)
        else:
            # Subtle tint across the frozen screen so user immediately sees the screen is captured
            painter.fillRect(self.rect(), QColor(10, 15, 28, 45))

        # 3. Draw the active freehand lasso trail while dragging (or faintly after release)
        if not self._lasso_path.isEmpty():
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

        # 4. Draw unmistakable inner glow + crisp white perimeter border
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

        # 5. Draw localized top-center HUD pill so the user immediately sees AI Lens is active
        lang_code = normalize_language_code(str(self.config.get("language", "cs")))
        thinking_level = normalize_thinking_level(str(self.config.get("thinking_level", "medium")))
        tier_cfg = get_thinking_level_config(thinking_level)
        ui = get_ui_strings(lang_code)
        hud_text = ui["hud_banner"].format(lang=lang_code.upper(), level=tier_cfg["label"])

        pill_w, pill_h = 560, 38
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
) -> None:
    """Standalone launcher for immediate screen capture + overlay."""
    _ensure_utf8_stdio()
    if language:
        set_language_in_config(language)
    if thinking_level:
        set_thinking_level_in_config(thinking_level)
    app = QApplication.instance() or QApplication(sys.argv)
    overlay = OverlayWindow(daemon_mode=False)
    capture_ms = overlay.activate_overlay()
    lang_code = str(overlay.config.get("language", "cs"))
    lang_disp = get_language_display(lang_code)
    level_disp = get_thinking_level_display(str(overlay.config.get("thinking_level", "medium")), lang_code)
    print(f"[AI Lens] Obrazovka zachycena do RAM za {capture_ms:.2f} ms.")
    print(
        f"[AI Lens] Lokální VLM ({overlay.config.get('model')}, jazyk: {lang_disp}, hloubka myšlení: {level_disp}) připraven. "
        "Zakroužkuj oblast myší, odpověď se bude streamovat v reálném čase. [Esc] pro zavření."
    )
    sys.exit(app.exec())


if __name__ == "__main__":
    run_overlay_mvp()
