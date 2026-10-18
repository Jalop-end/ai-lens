"""PyQt6 fullscreen frameless overlay with unmistakable visual HUD, 2px+ white border, freehand lasso, Bounding Box crop, Popover UI, and QThread VLM streaming."""

from __future__ import annotations

import ctypes
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
from ai_lens.vision_engine import VisionInferenceWorker, encode_pil_to_base64

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"
DEFAULT_TEST_CROP_PATH = Path(__file__).resolve().parent.parent / "last_crop.png"


def _ensure_utf8_stdio() -> None:
    """Prevents UnicodeEncodeError on Windows cp1250/cp852 terminals."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Load configuration from config.json with safe defaults."""
    defaults = {
        "hotkey": "<alt>+<f8>",
        "border_width": 3,
        "border_color": "#FFFFFF",
        "padding": 20,
        "ollama_host": "http://127.0.0.1:11434",
        "model": "gemma4:latest",
        "think": True,
        "temperature": 0.2,
        "default_prompt": (
            "Podívej se na tento zakroužkovaný výřez obrazovky. "
            "Popiš přesně, co na něm vidíš, a odpověz přirozeně jako klasický AI model v češtině."
        ),
    }
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            defaults.update(data)
        except Exception:
            pass
    return defaults


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
        """Cancels any running QThread inference worker without blocking the UI."""
        if self._worker is not None:
            try:
                self._worker.cancel()
                self._worker.tokenReceived.disconnect()
                self._worker.thinkingProgress.disconnect()
                self._worker.finishedInference.disconnect()
                self._worker.errorOccurred.disconnect()
            except Exception:
                pass
            self._worker = None

    def reset_selection(self) -> None:
        """Clears the current lasso path, bounding box, active worker, and hides the popover."""
        self._stop_active_worker()
        self._is_drawing = False
        self._lasso_points.clear()
        self._lasso_path = QPainterPath()
        self._selected_bbox = QRect()
        self._last_cropped_image = None
        self._chat_history.clear()
        self._current_reply_buffer = ""
        self.popover.hide()
        self.update()

    def activate_overlay(self) -> float:
        """
        Captures the current screen into RAM BEFORE showing the window,
        then immediately displays the fullscreen frozen overlay on top of everything.

        Returns:
            Capture time in milliseconds.
        """
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
        """Hides the overlay in daemon mode (0 ms re-activation) or closes & exits in standalone mode."""
        self.reset_selection()
        if self.daemon_mode:
            self.hide()
            self.overlayDismissed.emit()
            print("[AI Lens] Overlay skryt do pohotovosti. Stiskni Alt+F8 (nebo klikni na plovoucí tlačítko) pro další výběr.", flush=True)
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

            self._stop_active_worker()
            self.popover.hide()
            self._selected_bbox = QRect()
            self._chat_history.clear()
            self._current_reply_buffer = ""
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
        Computes the Bounding Box with adaptive padding, crops the clean screenshot,
        displays the PopoverCard right next to the selection, and launches QThread VLM inference.
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
                try:
                    cropped.save(DEFAULT_TEST_CROP_PATH)
                except Exception:
                    pass

                self.popover.place_near_bbox(bbox, self.rect())
                default_prompt = str(
                    self.config.get(
                        "default_prompt",
                        "Podívej se na tento zakroužkovaný výřez obrazovky. Popiš přesně, co na něm vidíš, a odpověz přirozeně jako klasický AI model v češtině.",
                    )
                )
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
        think_enabled = bool(self.config.get("think", True))
        temperature = float(self.config.get("temperature", 0.2))
        system_prompt = self.config.get("system_prompt")
        self.popover.title_label.setText(f"AI Lens · {model_name}")

        if not is_followup:
            self._chat_history.clear()
            self.popover.start_loading(f"Lokální model `{model_name}` zkoumá zakroužkovaný výřez…")
        else:
            self.popover.append_token(f"\n\n---\n**Dotaz:** {prompt}\n\n")
            self.popover.status_label.setText("Přemýšlím…")

        worker = VisionInferenceWorker(
            image=cropped_image,
            prompt=prompt,
            ollama_host=ollama_host,
            model=model_name,
            system_prompt=str(system_prompt) if system_prompt else None,
            think=think_enabled,
            temperature=temperature,
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
        """Updates status badge and stores conversation turn for follow-up queries."""
        self.popover.stop_loading(f"Hotovo ({elapsed:.1f} s)")
        if self._last_cropped_image is not None:
            if not is_followup:
                b64_img = encode_pil_to_base64(self._last_cropped_image, fmt="JPEG")
                self._chat_history.append(
                    {"role": "user", "content": prompt, "images": [b64_img]}
                )
            else:
                self._chat_history.append({"role": "user", "content": prompt})
            self._chat_history.append(
                {"role": "assistant", "content": self._current_reply_buffer}
            )

    def _on_worker_error(self, error_msg: str) -> None:
        """Displays any local VLM connection/inference error inside PopoverCard."""
        self.popover.stop_loading("Chyba spojení")
        self.popover.set_markdown_content(f"**Chyba lokálního AI enginu**\n\n{error_msg}")

    def _on_followup_prompt(self, prompt_text: str) -> None:
        """Handles follow-up question typed in the bottom QLineEdit of the PopoverCard."""
        if self._last_cropped_image is not None and not self._selected_bbox.isNull():
            self.regionSelected.emit(self._last_cropped_image, self._selected_bbox, prompt_text)
            self._start_inference(self._last_cropped_image, prompt_text, is_followup=True)

    def paintEvent(self, event) -> None:  # noqa: N802
        """Paints the frozen screen, unmistakable active border + top HUD pill, lasso trail, and Bounding Box."""
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

        # 5. Draw top-center HUD pill so the user immediately sees AI Lens is active
        pill_w, pill_h = 520, 38
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
            "AI Lens aktivní — Zakroužkuj oblast myší   |   [Esc] Zavřít",
        )

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Pressing Esc immediately closes/hides the overlay."""
        if event.key() == Qt.Key.Key_Escape:
            self.dismiss_overlay()
        else:
            super().keyPressEvent(event)


def run_overlay_mvp() -> None:
    """Standalone launcher for immediate screen capture + overlay."""
    _ensure_utf8_stdio()
    app = QApplication.instance() or QApplication(sys.argv)
    overlay = OverlayWindow(daemon_mode=False)
    capture_ms = overlay.activate_overlay()
    print(f"[AI Lens] Obrazovka zachycena do RAM za {capture_ms:.2f} ms.")
    print(
        f"[AI Lens] Lokální VLM ({overlay.config.get('model')}) připraven. "
        "Zakroužkuj oblast myší, odpověď se bude streamovat v reálném čase. [Esc] pro zavření."
    )
    sys.exit(app.exec())


if __name__ == "__main__":
    run_overlay_mvp()
