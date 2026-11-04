"""Floating Popover QFrame widget next to the lasso selection with monitor collision avoidance."""

from __future__ import annotations

import html
import re


_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_QUOTE_RE = re.compile(r'(?:„([^“"\n]+)[“"]|“([^”\n]+)”|"([^"\n]{2,})"|«([^»\n]+)»)')
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*•]\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\s*(\d+\.)\s+(.*)$")

_CONFIDENCE_TAG_RE = re.compile(
    r"^\[(?:Jistota|Pravděpodobnost|Confidence|Přesnost|Accuracy|Surety)[^0-9%]*(\d{1,3})\s*%\s*\]$",
    re.IGNORECASE,
)
_CONFIDENCE_EXTRACT_RE = re.compile(
    r"(?:\[(?:Jistota|Pravděpodobnost|Confidence|Přesnost|Accuracy|Surety)[^0-9%]*(\d{1,3})\s*%\s*\]"
    r"|(?:\*\*|#|\b)(?:Jistota|Pravděpodobnost|Confidence|Přesnost|Accuracy)[^\n\r\d]*(\d{1,3})\s*%)",
    re.IGNORECASE,
)


def extract_confidence_score(text: str) -> Optional[int]:
    """Extracts the estimated confidence percentage score (1..100) from markdown text."""
    matches = list(_CONFIDENCE_EXTRACT_RE.finditer(text))
    if not matches:
        return None
    val = matches[-1].group(1) or matches[-1].group(2)
    try:
        pct = int(val)
        return max(1, min(100, pct))
    except (ValueError, TypeError):
        return None


def _format_inline_Runs(text: str) -> str:
    """
    Formats inline Markdown & typography:
      - Preserves inline `code`
      - Formats citations/quotes in "..." with an italic serif citation font (Georgia / Times New Roman)
      - Formats **important words / answers** in the same color (#E5E7EB) but larger (16px) and thicker (800)
    """
    code_slots: list[str] = []

    def _stash_code(m: re.Match[str]) -> str:
        idx = len(code_slots)
        escaped_code = html.escape(m.group(1))
        code_slots.append(
            f'<code style="font-family: Consolas, \'Cascadia Mono\', monospace; '
            f'font-size: 12px; color: #E5E7EB;">{escaped_code}</code>'
        )
        return f"\x00CODE{idx}\x00"

    working = _INLINE_CODE_RE.sub(_stash_code, text)
    working = html.escape(working, quote=False)

    # Convert typographic/double quotes into "..." with optimal serif italic citation font
    def _replace_quote(m: re.Match[str]) -> str:
        inner = m.group(1) or m.group(2) or m.group(3) or m.group(4) or ""
        return (
            '<span style="font-family: \'Georgia\', \'Cambria\', \'Palatino Linotype\', '
            '\'Times New Roman\', serif; font-style: italic; font-size: 13.5px; color: #E5E7EB;">'
            f'"{inner}"</span>'
        )

    working = _QUOTE_RE.sub(_replace_quote, working)

    # Highlight **answers and important words**: same color (#E5E7EB), larger (16px), and thicker (bold 800)
    working = _BOLD_RE.sub(
        r'<b style="color: #E5E7EB; font-size: 16px; font-weight: 800;">\1</b>',
        working,
    )

    # Standard *italic*
    working = _ITALIC_RE.sub(r"<i>\1</i>", working)

    # Style checkmark (✓, ✔) in vivid emerald green and cross (✗, ✕, ❌) in vivid crimson red
    working = re.sub(
        r"([✓✔])",
        r'<span style="color: #34D399; font-weight: 800; font-size: 15px;">\1</span>',
        working,
    )
    working = re.sub(
        r"([✗✕❌])",
        r'<span style="color: #F87171; font-weight: 800; font-size: 15px;">\1</span>',
        working,
    )

    for idx, slot_html in enumerate(code_slots):
        working = working.replace(f"\x00CODE{idx}\x00", slot_html)

    return working


def render_styled_markdown_html(markdown_text: str) -> str:
    """
    Converts streamed Markdown into rich HTML for QTextBrowser:
      - Strips internal thoughts and cleans raw LaTeX math to human chat style
      - Base text: #E5E7EB, 13px Segoe UI
      - Highlighted answers & key terms (**...**): #E5E7EB, 16px, bold (800)
      - Citations ("..."): wrapped in "" using italic Georgia / Times New Roman serif font
    """
    if not markdown_text:
        return ""
    markdown_text = clean_chat_math_and_thoughts(markdown_text)

    parts = re.split(r"(```[\s\S]*?```)", markdown_text)
    html_blocks: list[str] = []

    for part in parts:
        if part.startswith("```") and part.endswith("```"):
            inner = part[3:-3]
            first_nl = inner.find("\n")
            if first_nl != -1:
                inner = inner[first_nl + 1 :]
            escaped = html.escape(inner.strip("\n"))
            html_blocks.append(
                '<pre style="background-color: rgba(15, 18, 25, 220); color: #E5E7EB; '
                "padding: 8px; border-radius: 6px; font-family: Consolas, 'Cascadia Mono', monospace; "
                f'font-size: 12px; margin: 6px 0;">{escaped}</pre>'
            )
            continue

        lines = part.splitlines()
        for raw_line in lines:
            stripped = raw_line.strip()
            if not stripped:
                html_blocks.append('<div style="height: 6px;"></div>')
                continue

            if stripped in ("---", "***", "___"):
                html_blocks.append(
                    '<hr style="border: none; border-top: 1px solid rgba(255,255,255,0.16); margin: 8px 0;" />'
                )
                continue

            conf_tag_m = _CONFIDENCE_TAG_RE.match(stripped)
            if conf_tag_m:
                pct = int(conf_tag_m.group(1))
                color = "#34D399" if pct >= 85 else ("#38BDF8" if pct >= 70 else "#FBBF24")
                bg = "rgba(16, 185, 129, 0.16)" if pct >= 85 else ("rgba(56, 189, 248, 0.16)" if pct >= 70 else "rgba(245, 158, 11, 0.16)")
                border = "rgba(52, 211, 153, 0.40)" if pct >= 85 else ("rgba(56, 189, 248, 0.40)" if pct >= 70 else "rgba(251, 191, 36, 0.40)")
                html_blocks.append(
                    f'<div style="margin: 6px 0; display: inline-block; background-color: {bg}; '
                    f'border: 1px solid {border}; border-radius: 6px; padding: 2px 8px; '
                    f'color: {color}; font-size: 11.5px; font-weight: 700;">'
                    f'Odhad jistoty / pravděpodobnost: {pct} %</div>'
                )
                continue

            heading_m = _HEADING_RE.match(stripped)
            if heading_m:
                h_text = _format_inline_Runs(heading_m.group(2))
                html_blocks.append(
                    '<div style="color: #E5E7EB; font-size: 16px; font-weight: 800; '
                    f'margin-top: 8px; margin-bottom: 4px;">{h_text}</div>'
                )
                continue

            if stripped.startswith(">"):
                quote_body = stripped.lstrip(">").strip().strip('"„“”')
                formatted_quote = _format_inline_Runs(quote_body)
                html_blocks.append(
                    '<div style="margin: 6px 0 6px 10px; font-family: \'Georgia\', \'Cambria\', '
                    "'Palatino Linotype', 'Times New Roman', serif; font-style: italic; "
                    f'font-size: 13.5px; color: #E5E7EB;">"{formatted_quote}"</div>'
                )
                continue

            bullet_m = _BULLET_RE.match(raw_line)
            if bullet_m:
                item_html = _format_inline_Runs(bullet_m.group(1))
                html_blocks.append(
                    f'<div style="margin: 3px 0 3px 10px; color: #E5E7EB;">• {item_html}</div>'
                )
                continue

            num_m = _NUMBERED_RE.match(raw_line)
            if num_m:
                num_prefix = html.escape(num_m.group(1))
                item_html = _format_inline_Runs(num_m.group(2))
                html_blocks.append(
                    '<div style="margin: 3px 0 3px 8px; color: #E5E7EB;">'
                    f'<b style="color: #E5E7EB; font-size: 14px; font-weight: 700;">{num_prefix}</b> {item_html}</div>'
                )
                continue

            line_html = _format_inline_Runs(raw_line)
            html_blocks.append(f'<div style="margin: 3px 0; color: #E5E7EB;">{line_html}</div>')

    body = "\n".join(html_blocks)
    return (
        '<div style="font-family: \'Segoe UI\', system-ui, sans-serif; '
        'font-size: 13px; color: #E5E7EB; line-height: 1.45;">'
        f"{body}</div>"
    )

import math
import time
from typing import Optional

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ai_lens.vision_engine import (
    get_thinking_level_display,
    get_ui_strings,
    normalize_language_code,
    normalize_thinking_level,
)


def compute_popover_position(
    bbox: QRect,
    screen_rect: QRect,
    popover_size: QSize,
    gap: int = 12,
) -> QPoint:
    """
    Computes the optimal (x, y) position for the popover card next to `bbox`
    with collision detection against `screen_rect` boundaries.

    Default position: right of selection at (x_max + 12, y_min).
    If x_max + 12 + width > screen_right, flips left to (x_min - width - 12, y_min)
    or below/above the selection if neither side fits.
    """
    w = popover_size.width()
    h = popover_size.height()

    x_min = bbox.left()
    y_min = bbox.top()
    x_max = bbox.left() + bbox.width()
    y_max = bbox.top() + bbox.height()

    screen_left = screen_rect.left()
    screen_top = screen_rect.top()
    screen_right = screen_rect.left() + screen_rect.width()
    screen_bottom = screen_rect.top() + screen_rect.height()

    # 1. Try default position: right of selection (x_max + 12, y_min)
    if x_max + gap + w <= screen_right - gap:
        x = x_max + gap
        y = y_min
    # 2. Flip left: (x_min - width - 12, y_min)
    elif x_min - gap - w >= screen_left + gap:
        x = x_min - w - gap
        y = y_min
    # 3. Place below selection if space allows
    elif y_max + gap + h <= screen_bottom - gap:
        x = max(screen_left + gap, min(x_min, screen_right - w - gap))
        y = y_max + gap
    # 4. Place above selection or clamp inside screen
    elif y_min - gap - h >= screen_top + gap:
        x = max(screen_left + gap, min(x_min, screen_right - w - gap))
        y = y_min - h - gap
    else:
        x = max(screen_left + gap, screen_right - w - gap)
        y = max(screen_top + gap, min(y_min, screen_bottom - h - gap))

    # Clamp vertically so the popover never overflows top or bottom of the monitor
    if y + h > screen_bottom - gap:
        y = max(screen_top + gap, screen_bottom - h - gap)
    if y < screen_top + gap:
        y = screen_top + gap

    return QPoint(x, y)


class NeuralOrbWidget(QWidget):
    """
    Futuristic Lemniscate (Infinity Loop ∞) with flowing celestial light.
    Renders with anti-aliasing:
      - Continuous Bernoulli lemniscate glowing conduit (cyan & indigo neon)
      - Dual focal-core ambient breathing energy in loop centers
      - Central nexus crossing pulse
      - Twin celestial light photons circulating along the infinity path with comet trails
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(96, 54)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._phase: float = 0.0
        self._cached_path: Optional[QPainterPath] = None

    def set_phase(self, phase: float) -> None:
        self._phase = phase
        self.update()

    @staticmethod
    def _lemniscate_point(t: float, a: float = 27.0) -> tuple[float, float]:
        """Calculates (x, y) along the Bernoulli Lemniscate (horizontal infinity loop)."""
        denom = 1.0 + math.sin(t) ** 2
        x = (a * math.sqrt(2) * math.cos(t)) / denom
        y = (a * math.sqrt(2) * math.sin(t) * math.cos(t)) / denom
        return x, y

    def _get_infinity_path(self, cx: float, cy: float, a: float) -> QPainterPath:
        if self._cached_path is None:
            path = QPainterPath()
            steps = 72
            for i in range(steps + 1):
                t = (2.0 * math.pi * i) / steps
                x, y = self._lemniscate_point(t, a)
                pt = QPointF(cx + x, cy + y)
                if i == 0:
                    path.moveTo(pt)
                else:
                    path.lineTo(pt)
            self._cached_path = path
        return self._cached_path

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx = self.width() / 2.0
        cy = self.height() / 2.0
        a = 27.0

        # 1. Subtle breathing ambient energy in left & right loop centers
        pulse = 0.5 + 0.5 * math.sin(self._phase * 1.5)
        for focal_x in (-20.0, 20.0):
            core_grad = QRadialGradient(cx + focal_x, cy, 14.0)
            core_alpha = int(45 + 35 * pulse)
            core_grad.setColorAt(0.0, QColor(56, 189, 248, core_alpha))
            core_grad.setColorAt(0.6, QColor(147, 51, 234, int(core_alpha * 0.45)))
            core_grad.setColorAt(1.0, QColor(15, 23, 42, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(core_grad))
            painter.drawEllipse(QPointF(cx + focal_x, cy), 14.0, 14.0)

        # 2. Draw the cached smooth infinity curve path
        path = self._get_infinity_path(cx, cy, a)

        # Ambient diffuse glow around the infinity loop
        glow_pen = QPen(QColor(56, 189, 248, 48))
        glow_pen.setWidthF(7.0)
        glow_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        glow_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(glow_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        # Crisp electric neon conduit line
        conduit_pen = QPen(QColor(129, 140, 248, 145))
        conduit_pen.setWidthF(2.0)
        conduit_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        conduit_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(conduit_pen)
        painter.drawPath(path)

        # 3. Intersection nexus at (cx, cy)
        nexus_r = 3.0 + 1.2 * math.sin(self._phase * 2.5)
        nexus_grad = QRadialGradient(cx, cy, nexus_r + 2.0)
        nexus_grad.setColorAt(0.0, QColor(255, 255, 255, 230))
        nexus_grad.setColorAt(0.5, QColor(192, 132, 252, 170))
        nexus_grad.setColorAt(1.0, QColor(99, 102, 241, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(nexus_grad))
        painter.drawEllipse(QPointF(cx, cy), nexus_r + 2.0, nexus_r + 2.0)

        # 4. Circulating celestial light photons with glowing comet trails
        for offset in (0.0, math.pi):
            base_t = self._phase * 1.35 + offset

            # Comet tail: 8 trailing light particles diminishing in size and alpha
            for k in range(8, 0, -1):
                tr_t = base_t - k * 0.08
                tx, ty = self._lemniscate_point(tr_t, a)
                frac = 1.0 - (k / 8.0)
                tr_r = 1.0 + frac * 2.3
                tr_alpha = int(35 + frac * 175)
                trail_color = (
                    QColor(192, 132, 252, tr_alpha)
                    if offset == 0.0
                    else QColor(56, 189, 248, tr_alpha)
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(trail_color))
                painter.drawEllipse(QPointF(cx + tx, cy + ty), tr_r, tr_r)

            # Leading bright light sphere (the glowing photon head)
            hx, hy = self._lemniscate_point(base_t, a)
            head_pt = QPointF(cx + hx, cy + hy)
            light_grad = QRadialGradient(head_pt, 9.5)
            light_grad.setColorAt(0.0, QColor(255, 255, 255, 255))
            light_grad.setColorAt(0.28, QColor(224, 242, 254, 235))
            light_grad.setColorAt(0.60, QColor(56, 189, 248, 175))
            light_grad.setColorAt(0.85, QColor(168, 85, 247, 90))
            light_grad.setColorAt(1.0, QColor(147, 51, 234, 0))
            painter.setBrush(QBrush(light_grad))
            painter.drawEllipse(head_pt, 9.5, 9.5)


class ThinkingGlowBar(QFrame):
    """
    Sleek horizontal neon scanning beam that sweeps back and forth
    while the model is processing or reasoning.
    Runs at ~30 FPS with negligible CPU footprint.
    """

    def __init__(self, parent: Optional[QWidget] = None, height: int = 3) -> None:
        super().__init__(parent)
        self.setFixedHeight(height)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._phase: float = 0.0
        self._is_active: bool = False
        self._timer = QTimer(self)
        self._timer.setInterval(30)
        self._timer.timeout.connect(self._on_tick)
        self.setVisible(False)

    def start_animation(self) -> None:
        self._is_active = True
        self._phase = 0.0
        self.setVisible(True)
        if not self._timer.isActive():
            self._timer.start()
        self.update()

    def stop_animation(self) -> None:
        self._is_active = False
        self._timer.stop()
        self.setVisible(False)
        self.update()

    def _on_tick(self) -> None:
        if not self._is_active:
            self._timer.stop()
            return
        self._phase += 0.075
        if self._phase > 2.0 * math.pi:
            self._phase -= 2.0 * math.pi
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if not self._is_active:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w = float(self.width())
        h = float(self.height())
        if w <= 0 or h <= 0:
            return

        center_norm = (math.sin(self._phase) + 1.0) / 2.0
        center_x = center_norm * w
        beam_w = max(60.0, w * 0.35)

        gradient = QLinearGradient(center_x - beam_w, 0, center_x + beam_w, 0)
        gradient.setColorAt(0.0, QColor(56, 189, 248, 0))
        gradient.setColorAt(0.3, QColor(96, 165, 250, 160))
        gradient.setColorAt(0.5, QColor(192, 132, 252, 240))
        gradient.setColorAt(0.7, QColor(56, 189, 248, 160))
        gradient.setColorAt(1.0, QColor(56, 189, 248, 0))

        painter.fillRect(QRectF(0, 0, w, h), gradient)


class ThinkingAnimationCard(QFrame):
    """
    Futuristic, comforting thinking animation card shown in PopoverCard
    while waiting for the first tokens to stream.
    Features:
      - Multi-ring pulsating neural AI orb
      - Live stopwatch in tenths of seconds (proves real-time execution)
      - Psychologically staged status messages (connecting -> synthesis -> deep reasoning)
      - Active reasoning step counter (fires on thinkingProgress)
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("ThinkingAnimationCard")
        self._language = "cs"
        self._thinking_level = "medium"
        self._start_time: float = 0.0
        self._phase: float = 0.0
        self._thinking_steps: int = 0
        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 FPS
        self._timer.timeout.connect(self._on_tick)

        self._setup_style()
        self._setup_ui()

    def _setup_style(self) -> None:
        self.setStyleSheet(
            """
            QFrame#ThinkingAnimationCard {
                background-color: rgba(22, 26, 36, 210);
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
            }
            QLabel#ThinkingHeadline {
                color: #F3F4F6;
                font-family: "Segoe UI", system-ui, sans-serif;
                font-size: 13px;
                font-weight: 600;
                background: transparent;
            }
            QLabel#ThinkingPhase {
                color: #9CA3AF;
                font-family: "Segoe UI", system-ui, sans-serif;
                font-size: 11px;
                font-weight: 400;
                background: transparent;
            }
            """
        )

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 18, 16, 18)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.orb = NeuralOrbWidget(self)

        self.headline_label = QLabel("Příprava & analýza výřezu", self)
        self.headline_label.setObjectName("ThinkingHeadline")
        self.headline_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.phase_label = QLabel("Snímání scény a kódování vizuálního kontextu…", self)
        self.phase_label.setObjectName("ThinkingPhase")
        self.phase_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.phase_label.setWordWrap(True)

        layout.addStretch(1)
        layout.addWidget(self.orb, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(4)
        layout.addWidget(self.headline_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.phase_label, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)

    def start_animation(self, language: str = "cs", thinking_level: str = "medium") -> None:
        self._language = normalize_language_code(language)
        self._thinking_level = normalize_thinking_level(thinking_level)
        self._start_time = time.time()
        self._phase = 0.0
        self._thinking_steps = 0
        self._on_tick()
        if not self._timer.isActive():
            self._timer.start()

    def stop_animation(self) -> None:
        self._timer.stop()

    def on_thinking_step(self, count: int) -> None:
        self._thinking_steps = count

    def _on_tick(self) -> None:
        self._phase += 0.06
        self.orb.set_phase(self._phase)
        elapsed = max(0.0, time.time() - self._start_time)

        is_cs = self._language in ("cs", "sk")
        if self._thinking_steps > 0:
            headline = "Aktivní řetězec myšlenek" if is_cs else "Active Chain of Thought"
            phase = (
                f"Model interně simuluje logiku a ověřuje data… ({self._thinking_steps} kroků)"
                if is_cs
                else f"Model is simulating logic and verifying data… ({self._thinking_steps} steps)"
            )
        elif elapsed < 1.0:
            headline = "Příprava & analýza výřezu" if is_cs else "Preparing Visual Input"
            phase = (
                "Snímání scény a kódování vizuálního kontextu…"
                if is_cs
                else "Encoding image region and multimodal context…"
            )
        elif elapsed < 2.5:
            headline = "Multimodální syntéza" if is_cs else "Multimodal Synthesis"
            phase = (
                "Propojování vizuálních prvků se zadáním…"
                if is_cs
                else "Correlating visual elements with semantics…"
            )
        else:
            headline = "Hluboké uvažování modelu" if is_cs else "Deep Neural Reasoning"
            phase = (
                "Formulace logické argumentace a přesné odpovědi…"
                if is_cs
                else "Formulating comprehensive and exact response…"
            )

        self.headline_label.setText(headline)
        self.phase_label.setText(phase)


class PopoverCard(QFrame):
    """
    Floating QFrame card shown right next to the circled area on the overlay.
    Contains:
      - Header bar with localized status/loading indicator and close button
      - Markdown-capable response view (for streaming tokens)
      - Localized follow-up question input field at the bottom
    """

    promptSubmitted = pyqtSignal(str)
    closeRequested = pyqtSignal()

    DEFAULT_WIDTH = 440
    DEFAULT_HEIGHT = 350

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("PopoverCard")
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        self._language: str = "cs"
        self._thinking_level: str = "medium"
        self._raw_markdown: str = ""
        self._loading_step: int = 0
        self._thinking_tokens: int = 0
        self._loading_timer = QTimer(self)
        self._loading_timer.setInterval(350)
        self._loading_timer.timeout.connect(self._tick_loading)

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(20)
        self._render_timer.timeout.connect(self._flush_pending_render)
        self._last_render_len = 0

        self._setup_style()
        self._setup_ui()

    def _setup_style(self) -> None:
        self.setStyleSheet(
            """
            QFrame#PopoverCard {
                background-color: rgba(18, 20, 26, 245);
                border: 1.5px solid rgba(255, 255, 255, 0.28);
                border-radius: 12px;
            }
            QLabel#HeaderTitle {
                color: #F3F4F6;
                font-family: "Segoe UI", system-ui, sans-serif;
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#StatusBadge {
                color: #60A5FA;
                font-family: "Segoe UI", system-ui, sans-serif;
                font-size: 11px;
                font-weight: 500;
            }
            QLabel#ConfidenceBadge {
                font-family: "Segoe UI", system-ui, sans-serif;
                font-size: 11px;
                font-weight: 700;
                padding: 1px 7px;
                border-radius: 5px;
            }
            QPushButton#CloseButton {
                background-color: transparent;
                color: #9CA3AF;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                padding: 2px 6px;
            }
            QPushButton#CloseButton:hover {
                background-color: rgba(255, 255, 255, 0.12);
                color: #FFFFFF;
            }
            QTextBrowser#ResponseBrowser {
                background-color: rgba(28, 31, 40, 200);
                color: #E5E7EB;
                border: 1px solid rgba(255, 255, 255, 0.10);
                border-radius: 8px;
                padding: 8px;
                font-family: "Segoe UI", system-ui, sans-serif;
                font-size: 13px;
                selection-background-color: #3B82F6;
            }
            QLineEdit#PromptInput {
                background-color: rgba(31, 35, 46, 230);
                color: #F9FAFB;
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 7px;
                padding: 6px 10px;
                font-family: "Segoe UI", system-ui, sans-serif;
                font-size: 12px;
            }
            QLineEdit#PromptInput:focus {
                border: 1px solid #60A5FA;
            }
            """
        )

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(6)

        # Header row
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel("AI Lens")
        self.title_label.setObjectName("HeaderTitle")

        self.confidence_badge = QLabel("", self)
        self.confidence_badge.setObjectName("ConfidenceBadge")
        self.confidence_badge.setVisible(False)

        self.status_label = QLabel("Připraveno")
        self.status_label.setObjectName("StatusBadge")

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("CloseButton")
        self.close_btn.setToolTip("Zavřít (Esc)")
        self.close_btn.clicked.connect(self.closeRequested.emit)

        header_layout.addWidget(self.title_label)
        header_layout.addSpacing(6)
        header_layout.addWidget(self.confidence_badge)
        header_layout.addStretch(1)
        header_layout.addWidget(self.status_label)
        header_layout.addSpacing(6)
        header_layout.addWidget(self.close_btn)

        # Subtle neon scanning beam for live reasoning/query progress
        self.glow_bar = ThinkingGlowBar(self, height=3)

        # Dedicated futuristic thinking card shown while model is computing
        self.thinking_card = ThinkingAnimationCard(self)
        self.thinking_card.setVisible(False)

        # Response area (supports Markdown & code blocks)
        self.response_browser = QTextBrowser(self)
        self.response_browser.setObjectName("ResponseBrowser")
        self.response_browser.setOpenExternalLinks(False)
        self.response_browser.setOpenLinks(False)

        # Follow-up input field at the bottom
        self.prompt_input = QLineEdit(self)
        self.prompt_input.setObjectName("PromptInput")
        self.prompt_input.setPlaceholderText("Doplňující dotaz k výřezu… (Enter pro odeslání)")
        self.prompt_input.returnPressed.connect(self._on_submit_prompt)

        layout.addLayout(header_layout)
        layout.addWidget(self.glow_bar)
        layout.addWidget(self.thinking_card, stretch=1)
        layout.addWidget(self.response_browser, stretch=1)
        layout.addWidget(self.prompt_input)

    def _update_confidence_badge(self) -> None:
        pct = extract_confidence_score(self._raw_markdown)
        if pct is not None:
            if pct >= 85:
                bg = "rgba(16, 185, 129, 0.22)"
                border = "rgba(52, 211, 153, 0.65)"
                color = "#34D399"
            elif pct >= 70:
                bg = "rgba(56, 189, 248, 0.22)"
                border = "rgba(56, 189, 248, 0.65)"
                color = "#38BDF8"
            else:
                bg = "rgba(245, 158, 11, 0.22)"
                border = "rgba(251, 191, 36, 0.65)"
                color = "#FBBF24"

            self.confidence_badge.setStyleSheet(
                f"background-color: {bg}; border: 1px solid {border}; color: {color};"
            )
            self.confidence_badge.setText(f"{pct} %")
            self.confidence_badge.setToolTip(
                f"Odhadovaná pravděpodobnost správnosti / jistota modelu: {pct} %"
            )
            self.confidence_badge.setVisible(True)
        else:
            self.confidence_badge.setVisible(False)

    def clear_sensitive_data(self) -> None:
        """Immediately wipes all conversation text, DOM content, and input buffers from RAM."""
        self._loading_timer.stop()
        self._render_timer.stop()
        self.glow_bar.stop_animation()
        self.thinking_card.stop_animation()
        self.thinking_card.setVisible(False)
        self.response_browser.setVisible(True)
        self._raw_markdown = ""
        self._last_render_len = 0
        self._loading_step = 0
        self._thinking_tokens = 0
        self.confidence_badge.clear()
        self.confidence_badge.setVisible(False)
        self.response_browser.clear()
        self.response_browser.setHtml("")
        self.prompt_input.clear()

    def set_locale(self, language: str, thinking_level: str = "medium") -> None:
        """Updates all PopoverCard labels, tooltips, and placeholders to match `language` and `thinking_level`."""
        self._language = normalize_language_code(language)
        self._thinking_level = normalize_thinking_level(thinking_level)
        ui = get_ui_strings(self._language)
        self.close_btn.setToolTip(ui["close_tooltip"])
        self.prompt_input.setPlaceholderText(ui["followup_placeholder"])
        if not self._loading_timer.isActive() and not self._raw_markdown:
            self.status_label.setText(ui["ready"])

    def _on_submit_prompt(self) -> None:
        text = self.prompt_input.text().strip()
        if text:
            self.prompt_input.clear()
            self.promptSubmitted.emit(text)

    def _tick_loading(self) -> None:
        ui = get_ui_strings(self._language)
        spinner_frames = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
        frame = spinner_frames[self._loading_step % len(spinner_frames)]
        self._loading_step += 1
        elapsed = max(0.0, time.time() - getattr(self, "_start_time", time.time()))
        if self._thinking_tokens > 0:
            self.status_label.setText(f"{frame} {ui['thinking']} ({elapsed:.1f}s)")
        else:
            self.status_label.setText(f"{frame} {ui['analyzing']} ({elapsed:.1f}s)")

    def start_loading(self, message: str = "") -> None:
        """Starts the loading indicator and displays the animated thinking card before first tokens arrive."""
        ui = get_ui_strings(self._language)
        self._raw_markdown = ""
        self._loading_step = 0
        self._thinking_tokens = 0
        self._start_time = time.time()
        self.confidence_badge.clear()
        self.confidence_badge.setVisible(False)
        self.status_label.setText(f"⠋ {ui['analyzing']}…")

        self.glow_bar.start_animation()
        self.response_browser.setVisible(False)
        self.thinking_card.start_animation(self._language, self._thinking_level)
        self.thinking_card.setVisible(True)

        self._loading_timer.start()

    def start_followup_loading(self, prompt: str) -> None:
        """Starts animated thinking indicators for a follow-up question while keeping previous chat visible."""
        ui = get_ui_strings(self._language)
        self.append_token(f"\n\n---\n**{ui['followup_prefix']}:** {prompt}\n\n")
        self._loading_step = 0
        self._thinking_tokens = 0
        self._start_time = time.time()
        self.status_label.setText(f"⠋ {ui['thinking']}…")
        self.glow_bar.start_animation()
        self._loading_timer.start()

    def on_thinking_progress(self) -> None:
        """Updates status when the VLM is actively running visual reasoning tokens."""
        ui = get_ui_strings(self._language)
        self._thinking_tokens += 1
        self.thinking_card.on_thinking_step(self._thinking_tokens)
        if self._thinking_tokens == 1:
            self.status_label.setText(f"🧠 {ui['thinking']}…")

    def stop_loading(self, status_text: str = "") -> None:
        """Stops the loading indicator once streaming completes or pauses."""
        ui = get_ui_strings(self._language)
        self._loading_timer.stop()
        if self.thinking_card.isVisible():
            self.thinking_card.stop_animation()
            self.thinking_card.setVisible(False)
            self.response_browser.setVisible(True)
        self.glow_bar.stop_animation()
        if self._render_timer.isActive() or self._last_render_len != len(self._raw_markdown):
            self._render_timer.stop()
            self._flush_pending_render()
        self.status_label.setText(status_text or ui["ready"])
        self._update_confidence_badge()

    def _flush_pending_render(self) -> None:
        """Renders accumulated Markdown into styled HTML at up to 50 FPS without blocking fast token streams."""
        if not self._raw_markdown:
            return
        self._last_render_len = len(self._raw_markdown)
        self.response_browser.setHtml(render_styled_markdown_html(self._raw_markdown))
        self._update_confidence_badge()
        sb = self.response_browser.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.maximum())

    def set_markdown_content(self, markdown_text: str) -> None:
        """Replaces the displayed Markdown text using styled HTML rendering."""
        self._render_timer.stop()
        if self.thinking_card.isVisible():
            self.thinking_card.stop_animation()
            self.thinking_card.setVisible(False)
            self.response_browser.setVisible(True)
        self.glow_bar.stop_animation()
        self._raw_markdown = markdown_text
        self._flush_pending_render()

    def append_token(self, token: str) -> None:
        """Appends a newly streamed token and schedules a batched 50 FPS DOM render."""
        ui = get_ui_strings(self._language)
        if self._loading_timer.isActive():
            self._loading_timer.stop()
        if self.thinking_card.isVisible():
            self.thinking_card.stop_animation()
            self.thinking_card.setVisible(False)
            self.response_browser.setVisible(True)
        self.glow_bar.stop_animation()
        self.status_label.setText(ui["streaming"])
        was_empty = not self._raw_markdown
        self._raw_markdown += token
        if was_empty:
            self._flush_pending_render()
        elif not self._render_timer.isActive():
            self._render_timer.start()

    def place_near_bbox(self, bbox: QRect, screen_rect: QRect) -> QPoint:
        """Positions the PopoverCard next to `bbox` respecting `screen_rect` borders."""
        pos = compute_popover_position(
            bbox=bbox,
            screen_rect=screen_rect,
            popover_size=self.size(),
            gap=12,
        )
        self.move(pos)
        self.show()
        self.raise_()
        return pos


def clean_chat_math_and_thoughts(text: str, max_words: Optional[int] = None) -> str:
    """
    Cleans internal thoughts, reasoning blocks, analysis monologues, and transforms
    raw LaTeX / KaTeX math expressions into natural human-friendly chat representations.
    If `max_words` is specified, strictly caps output to that number of lexical words (e.g. max 25 words).
    """
    if not text:
        return ""

    # 1. Strip internal thoughts blocks: <thought>...</thought>, <think>...</think>, <|thought|>...<|/thought|>, and unclosed tags
    text = re.sub(
        r'(?is)<\s*\|?\s*(?:thought|think|reasoning|reflection)\s*\|?[^>]*>.*?<\s*\|?\s*/\s*(?:thought|think|reasoning|reflection)\s*\|?\s*>',
        '',
        text,
    )
    text = re.sub(r'(?is)<\s*\|?\s*(?:thought|think|reasoning|reflection)\s*\|?[^>]*>.*', '', text)

    # 2. Extract from explicit final-answer label ONLY if preceded by a thinking monologue (or empty prefix).
    # Never match bare '✓', which appears legitimately on option B/C/D after '✗ A) ...'!
    marker_m = re.search(
        r'(?im)(?:^|\n)\s*(?:\*\*)?(?:final\s+answer|konečná\s+odpověď|správná\s+odpověď|odpověď|výsledek|řešení|answer|solution|result)(?:\*\*)?\s*:\s*(?:\*\*)?',
        text,
    )
    if marker_m:
        prefix = text[:marker_m.start()].strip()
        after = text[marker_m.end():].strip()
        if after and (
            not prefix
            or len(prefix.split()) > 15
            or re.search(
                r'(?i)(?:think(?:ing)?|thoughts?|reasoning|úvah[ay]|analýz[ay]|rozbor|myšlenkov|(?:^|\n)\s*(?:step\s*1|krok\s*1|1\.))',
                prefix,
            )
        ):
            text = after

    # 3. Strip explicit thought/reasoning section headers and meta-thinking lead-ins
    thought_header_pat = (
        r'(?im)^\s*(?:\*\*)?(?:thoughts?|thinking(?:\s+process)?|internal\s+reasoning|reasoning|'
        r'myšlenkový\s+postup|úvaha):\s*(?:\*\*)?.*?(?:\n|$)'
    )
    text = re.sub(thought_header_pat, '', text)
    text = re.sub(
        r'(?im)^\s*(?:let\'s\s+think\s+step\s+by\s+step|here\s+is\s+my\s+reasoning)\b.*?\n',
        '',
        text,
    )

    # 4. In concise Secret Mode (`max_words` set), strip any trailing '[Jistota: XX %]' / '[Confidence: XX %]' tag
    if max_words is not None:
        text = re.sub(r'(?i)\[\s*(?:jistota|confidence|pravděpodobnost)\s*:\s*\d+\s*%\s*\]', '', text)

    # 5. Convert LaTeX text wrappers: \text{...}, \mathrm{...}, \mathbf{...}, \mathit{...}
    text = re.sub(r'\\(?:text|mathrm|mathbf|mathit)\s*\{([^}]*)\}', r'\1', text)

    # 6. Handle LaTeX math escapes and spacing
    text = text.replace(r'\%', '%')
    text = text.replace(r'\{,\}', ',')
    text = text.replace('{,}', ',')
    text = re.sub(r'(\d+)\{,\}(\d+)', r'\1,\2', text)
    text = text.replace(r'\,', ' ').replace(r'\;', ' ').replace(r'\:', ' ').replace(r'\ ', ' ')

    # 7. Math symbols to clean human chat style
    text = re.sub(r'\\times\b', '×', text)
    text = re.sub(r'\\cdot\b', '·', text)
    text = re.sub(r'\\div\b', '/', text)
    text = re.sub(r'\\pm\b', '±', text)
    text = re.sub(r'\\approx\b', '≈', text)
    text = re.sub(r'\\le(?:q)?\b', '<=', text)
    text = re.sub(r'\\ge(?:q)?\b', '>=', text)
    text = re.sub(r'\\ne(?:q)?\b', '!=', text)
    text = re.sub(r'\\rightarrow\b', '->', text)
    text = re.sub(r'\\leftarrow\b', '<-', text)
    text = re.sub(r'\\left\(', '(', text)
    text = re.sub(r'\\right\)', ')', text)
    text = re.sub(r'\\left\[', '[', text)
    text = re.sub(r'\\right\]', ']', text)

    # 8. Fractions: \frac{a}{b} -> a / b
    for _ in range(3):
        text = re.sub(r'\\frac\{([^{}]+)\}\{([^{}]+)\}', r'\1 / \2', text)

    # 9. Square roots: \sqrt{x} -> √(x)
    text = re.sub(r'\\sqrt\{([^{}]+)\}', r'√(\1)', text)

    # 10. Strip single and double dollar signs surrounding inline / block math
    text = re.sub(r'\$\$([^\$]+)\$\$', r'\1', text)
    text = re.sub(r'\$([^\$]+)\$', r'\1', text)
    text = text.replace('$$', '').replace('$', '')

    # 11. Clean redundant horizontal whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{2,}', '\n', text)

    # 12. Strict lexical word count clamp (standalone symbols like '✓', '✗', '=', '×' don't consume the word budget)
    if max_words is not None and max_words > 0:
        word_count = 0
        cut_idx: Optional[int] = None
        for m_tok in re.finditer(r'\S+', text):
            tok = m_tok.group(0)
            if any(ch.isalnum() for ch in tok):
                word_count += 1
                if word_count > max_words:
                    cut_idx = m_tok.start()
                    break
        if cut_idx is not None:
            candidate = text[:cut_idx]
            # Prefer ending at the last complete sentence boundary if available past 60% of the text
            last_sent = max(candidate.rfind('. '), candidate.rfind('! '), candidate.rfind('? '))
            if last_sent >= int(len(candidate) * 0.6):
                text = candidate[: last_sent + 1].strip()
            else:
                text = candidate.rstrip(' ,;:-–—\n')

    return text.strip()


def _format_secret_display(text: str) -> str:
    """Escapes HTML, strips thoughts, cleans math to chat style, caps to <= 45 words, and highlights bold/checkmarks/crosses for SecretTopBar."""
    if not text:
        return ""
    cleaned = clean_chat_math_and_thoughts(text, max_words=45)
    if not cleaned:
        return ""
    escaped = html.escape(cleaned, quote=False)
    escaped = re.sub(r"\*\*(.+?)\*\*", r'<span style="color: #F8FAFC; font-weight: 800;">\1</span>', escaped)
    escaped = escaped.replace("**", "")
    escaped = re.sub(
        r"([✓✔])",
        r'<span style="color: #34D399; font-weight: 800; font-size: 16px;">\1</span>',
        escaped,
    )
    escaped = re.sub(
        r"([✗✕❌])",
        r'<span style="color: #F87171; font-weight: 800; font-size: 16px;">\1</span>',
        escaped,
    )
    escaped = escaped.replace("\n", "<br/>")
    return escaped


class SecretTopBar(QFrame):
    """
    Sleek, unobtrusive horizontal floating bar positioned right below the screen's top bar (horní lišta)
    for Secret Mode. Displays direct, concise answers with deep comprehension, saving tokens and reading time.
    """

    closeRequested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("SecretTopBar")
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self._raw_text = ""
        self._language = "cs"
        self._is_loading: bool = False
        self._start_time: float = 0.0
        self._anim_step: int = 0
        self._thinking_steps: int = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(65)
        self._anim_timer.timeout.connect(self._tick_secret_loading)

        self.setMinimumWidth(540)
        self.setMaximumWidth(920)
        self._setup_style()
        self._setup_effects()
        self._setup_ui()

    def _setup_effects(self) -> None:
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 185))
        shadow.setOffset(0, 3)
        self.setGraphicsEffect(shadow)

    def _setup_style(self) -> None:
        self.setStyleSheet(
            """
            QFrame#SecretTopBar {
                background-color: rgba(12, 20, 36, 135);
                border: 1px solid rgba(56, 189, 248, 0.40);
                border-radius: 12px;
            }
            QLabel#SecretContent {
                color: #FFFFFF;
                font-family: "Segoe UI", system-ui, sans-serif;
                font-size: 15px;
                font-weight: 700;
                line-height: 1.45;
                background: transparent;
            }
            QPushButton#SecretCopyBtn {
                background-color: rgba(255, 255, 255, 0.12);
                color: #F8FAFC;
                border: 1px solid rgba(255, 255, 255, 0.22);
                border-radius: 6px;
                font-family: "Segoe UI", system-ui, sans-serif;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 12px;
            }
            QPushButton#SecretCopyBtn:hover {
                background-color: rgba(56, 189, 248, 0.35);
                color: #FFFFFF;
                border: 1px solid #38BDF8;
            }
            QPushButton#SecretCloseBtn {
                background-color: transparent;
                color: #CBD5E1;
                border: none;
                font-size: 15px;
                font-weight: bold;
                padding: 4px 8px;
            }
            QPushButton#SecretCloseBtn:hover {
                color: #EF4444;
            }
            """
        )

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(16, 10, 14, 10)
        row_layout.setSpacing(12)
        row_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.content_label = QLabel("...", self)
        self.content_label.setObjectName("SecretContent")
        self.content_label.setWordWrap(True)
        self.content_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(6)
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.copy_btn = QPushButton("Kopírovat", self)
        self.copy_btn.setObjectName("SecretCopyBtn")
        self.copy_btn.setToolTip("Kopírovat odpověď do schránky")
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._on_copy)

        self.close_btn = QPushButton("✕", self)
        self.close_btn.setObjectName("SecretCloseBtn")
        self.close_btn.setToolTip("Zavřít (Esc)")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.closeRequested.emit)

        btn_layout.addWidget(self.copy_btn)
        btn_layout.addWidget(self.close_btn)

        row_layout.addWidget(self.content_label, 1)
        row_layout.addLayout(btn_layout)

        self._glow_bar = ThinkingGlowBar(self, height=2)

        main_layout.addLayout(row_layout)
        main_layout.addWidget(self._glow_bar)

    def set_locale(self, language: str) -> None:
        """Updates SecretTopBar button text and tooltips according to language."""
        self._language = normalize_language_code(language)
        if self._language in ("cs", "sk"):
            self.copy_btn.setText("Kopírovat")
            self.copy_btn.setToolTip("Kopírovat odpověď do schránky")
            self.close_btn.setToolTip("Zavřít (Esc)")
        else:
            self.copy_btn.setText("Copy")
            self.copy_btn.setToolTip("Copy answer to clipboard")
            self.close_btn.setToolTip("Close (Esc)")

    def _on_copy(self) -> None:
        from PyQt6.QtWidgets import QApplication
        cb = QApplication.clipboard()
        if cb is not None:
            cleaned = clean_chat_math_and_thoughts(self._raw_text, max_words=45).replace("**", "")
            cb.setText(cleaned)
            copied_text = "Zkopírováno" if self._language in ("cs", "sk") else "Copied"
            reset_text = "Kopírovat" if self._language in ("cs", "sk") else "Copy"
            self.copy_btn.setText(copied_text)
            QTimer.singleShot(1500, lambda: self.copy_btn.setText(reset_text))

    def _recenter_on_screen(self) -> None:
        parent = self.parentWidget()
        if parent is not None and parent.width() > 0:
            new_x = (parent.width() - self.width()) // 2
            self.move(max(10, new_x), 14)

    def _tick_secret_loading(self) -> None:
        if not self._is_loading:
            self._anim_timer.stop()
            return
        spinner_frames = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
        frame = spinner_frames[self._anim_step % len(spinner_frames)]
        self._anim_step += 1
        elapsed = max(0.0, time.time() - self._start_time)
        is_cs = self._language in ("cs", "sk")

        if self._thinking_steps > 0:
            txt = (
                f"{frame} Hluboké uvažování · {self._thinking_steps} kroků ({elapsed:.1f}s)"
                if is_cs
                else f"{frame} Deep reasoning · {self._thinking_steps} steps ({elapsed:.1f}s)"
            )
        elif elapsed < 1.0:
            txt = (
                f"{frame} Snímání & analýza zadání ({elapsed:.1f}s)"
                if is_cs
                else f"{frame} Capturing & analyzing query ({elapsed:.1f}s)"
            )
        elif elapsed < 2.5:
            txt = (
                f"{frame} Multimodální syntéza ({elapsed:.1f}s)"
                if is_cs
                else f"{frame} Multimodal synthesis ({elapsed:.1f}s)"
            )
        else:
            txt = (
                f"{frame} Formulace přesné odpovědi ({elapsed:.1f}s)"
                if is_cs
                else f"{frame} Formulating precise response ({elapsed:.1f}s)"
            )

        self.content_label.setText(txt)
        self.adjustSize()
        self._recenter_on_screen()

    def on_thinking_progress(self) -> None:
        """Called when internal reasoning / thinking tokens are running."""
        self._thinking_steps += 1
        if self._is_loading:
            self._tick_secret_loading()

    def start_loading(self, text: str = "Řeším...") -> None:
        self._raw_text = ""
        self._is_loading = True
        self._start_time = time.time()
        self._anim_step = 0
        self._thinking_steps = 0
        self._glow_bar.start_animation()
        self._tick_secret_loading()
        if not self._anim_timer.isActive():
            self._anim_timer.start(65)
        self.adjustSize()
        self._recenter_on_screen()

    def stop_loading(self) -> None:
        """Stops the loading spinner and neon glow bar once Secret Mode streaming finishes."""
        self._is_loading = False
        self._anim_timer.stop()
        self._glow_bar.stop_animation()
        if self._raw_text.strip():
            cleaned_html = _format_secret_display(self._raw_text)
            if cleaned_html:
                self.content_label.setText(cleaned_html)
        if self.layout() is not None:
            self.layout().activate()
        self.adjustSize()
        self._recenter_on_screen()

    def append_token(self, token: str) -> None:
        if self._is_loading:
            self._is_loading = False
            self._anim_timer.stop()
            self._glow_bar.stop_animation()
            self.content_label.setText("")
        self._raw_text += token
        cleaned_html = _format_secret_display(self._raw_text)
        if not cleaned_html:
            ui = get_ui_strings(self._language)
            self.content_label.setText(f"{ui.get('thinking', 'Přemýšlím')}…")
        else:
            self.content_label.setText(cleaned_html)
        if self.layout() is not None:
            self.layout().activate()
        self.adjustSize()
        self._recenter_on_screen()

    def set_content(self, text: str) -> None:
        self._is_loading = False
        self._anim_timer.stop()
        self._glow_bar.stop_animation()
        self._raw_text = text
        self.content_label.setText(_format_secret_display(text))
        if self.layout() is not None:
            self.layout().activate()
        self.adjustSize()
        self._recenter_on_screen()

    def clear_sensitive_data(self) -> None:
        self._is_loading = False
        self._anim_timer.stop()
        self._glow_bar.stop_animation()
        self._raw_text = ""
        self.content_label.setText("")
        self.hide()
