"""Fast screen capture module into RAM and high-DPI Bounding Box cropping."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional, Sequence

import mss
from PIL import Image
from PyQt6.QtCore import QPointF, QRect
from PyQt6.QtGui import QGuiApplication, QImage, QPixmap


@dataclass
class ScreenCaptureResult:
    """Holds the raw captured screenshot in RAM along with metadata."""

    qpixmap: QPixmap
    monitor_rect: dict[str, int]
    capture_ms: float
    device_pixel_ratio: float = 1.0
    capture_backend: str = "mss"


def capture_screen(monitor_index: int = 1, device_pixel_ratio: float = 1.0) -> ScreenCaptureResult:
    """
    Captures the specified monitor directly into RAM (<15 ms).
    Uses QImage.Format.Format_RGB32 for mss BGRx buffers because Windows GDI BitBlt
    leaves the 4th byte (Alpha) as 0x00, which would make Format_ARGB32 transparent.
    Falls back to Qt's QScreen.grabWindow(0) if GDI CAPTUREBLT is restricted.
    """
    t0 = time.perf_counter()
    backend = "mss"

    try:
        with mss.MSS() as sct:
            monitors = sct.monitors
            if monitor_index >= len(monitors):
                monitor_index = 1
            mon = dict(monitors[monitor_index])
            raw_shot = sct.grab(mon)

        width, height = raw_shot.size
        # Keep explicit local reference to bytes buffer during QImage construction & copy
        raw_bytes = raw_shot.bgra
        qimage = QImage(
            raw_bytes,
            width,
            height,
            width * 4,
            QImage.Format.Format_RGB32,
        ).copy()

        qpixmap = QPixmap.fromImage(qimage)
        if device_pixel_ratio > 0:
            qpixmap.setDevicePixelRatio(device_pixel_ratio)
    except Exception:
        backend = "qt_grabWindow"
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            raise
        qpixmap = screen.grabWindow(0)
        dpr = qpixmap.devicePixelRatio() or device_pixel_ratio or 1.0
        device_pixel_ratio = dpr
        geom = screen.geometry()
        mon = {
            "left": geom.x(),
            "top": geom.y(),
            "width": qpixmap.width(),
            "height": qpixmap.height(),
        }

    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    return ScreenCaptureResult(
        qpixmap=qpixmap,
        monitor_rect=mon,
        capture_ms=elapsed_ms,
        device_pixel_ratio=device_pixel_ratio if device_pixel_ratio > 0 else 1.0,
        capture_backend=backend,
    )


def compute_bounding_box(
    points: Sequence[QPointF | tuple[float, float]],
    screen_width: int,
    screen_height: int,
    padding: int = 4,
) -> QRect:
    """
    Computes the Bounding Box [xmin - p, ymin - p, xmax + p, ymax + p]
    from a sequence of lasso points in logical screen coordinates, clamped to screen bounds.
    Fits closely around the user's drawn contour with tight padding.
    """
    if not points:
        return QRect()

    xs: list[float] = []
    ys: list[float] = []
    for pt in points:
        if isinstance(pt, QPointF):
            xs.append(pt.x())
            ys.append(pt.y())
        else:
            xs.append(float(pt[0]))
            ys.append(float(pt[1]))

    raw_xmin = min(xs)
    raw_ymin = min(ys)
    raw_xmax = max(xs)
    raw_ymax = max(ys)

    # Tight padding directly around the drawn outline
    pad = max(0, padding)

    x_min = max(0, int(raw_xmin) - pad)
    y_min = max(0, int(raw_ymin) - pad)
    x_max = min(screen_width, int(raw_xmax) + pad)
    y_max = min(screen_height, int(raw_ymax) + pad)

    width = max(1, x_max - x_min)
    height = max(1, y_max - y_min)
    return QRect(x_min, y_min, width, height)


def crop_from_capture(capture: ScreenCaptureResult, logical_bbox: QRect) -> Image.Image:
    """
    Crops only the selected Bounding Box from the clean original screenshot in RAM
    (accounting for High-DPI devicePixelRatio) and converts just that sub-rectangle to PIL.Image.
    """
    dpr = capture.device_pixel_ratio if capture.device_pixel_ratio > 0 else 1.0
    img_w = capture.qpixmap.width()
    img_h = capture.qpixmap.height()

    px_min = max(0, int(round(logical_bbox.left() * dpr)))
    py_min = max(0, int(round(logical_bbox.top() * dpr)))
    px_max = min(img_w, int(round((logical_bbox.left() + logical_bbox.width()) * dpr)))
    py_max = min(img_h, int(round((logical_bbox.top() + logical_bbox.height()) * dpr)))

    crop_w = max(1, px_max - px_min)
    crop_h = max(1, py_max - py_min)

    cropped_qimage = (
        capture.qpixmap.toImage()
        .copy(px_min, py_min, crop_w, crop_h)
        .convertToFormat(QImage.Format.Format_RGBA8888)
    )
    w, h = cropped_qimage.width(), cropped_qimage.height()
    ptr = cropped_qimage.constBits()
    ptr.setsize(h * cropped_qimage.bytesPerLine())
    return Image.frombuffer(
        "RGBA",
        (w, h),
        bytes(ptr),
        "raw",
        "RGBA",
        cropped_qimage.bytesPerLine(),
        1,
    ).convert("RGB")
