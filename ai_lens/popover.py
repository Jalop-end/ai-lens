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

    for idx, slot_html in enumerate(code_slots):
        working = working.replace(f"\x00CODE{idx}\x00", slot_html)

    return working


def render_styled_markdown_html(markdown_text: str) -> str:
    """
    Converts streamed Markdown into rich HTML for QTextBrowser:
      - Base text: #E5E7EB, 13px Segoe UI
      - Highlighted answers & key terms (**...**): #E5E7EB, 16px, bold (800)
      - Citations ("..."): wrapped in "" using italic Georgia / Times New Roman serif font
    """
    if not markdown_text:
        return ""

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

from typing import Optional

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
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


class PopoverCard(QFrame):
    """
    Floating QFrame card shown right next to the circled area on the overlay.
    Contains:
      - Header bar with status/loading indicator and close button
      - Markdown-capable response view (for streaming tokens)
      - Follow-up question input field at the bottom
    """

    promptSubmitted = pyqtSignal(str)
    closeRequested = pyqtSignal()

    DEFAULT_WIDTH = 420
    DEFAULT_HEIGHT = 340

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("PopoverCard")
        self.setFixedSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        self._raw_markdown: str = ""
        self._loading_step: int = 0
        self._thinking_tokens: int = 0
        self._loading_timer = QTimer(self)
        self._loading_timer.setInterval(350)
        self._loading_timer.timeout.connect(self._tick_loading)

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
        layout.setSpacing(8)

        # Header row
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel("AI Lens")
        self.title_label.setObjectName("HeaderTitle")

        self.status_label = QLabel("Připraveno")
        self.status_label.setObjectName("StatusBadge")

        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("CloseButton")
        self.close_btn.setToolTip("Zavřít (Esc)")
        self.close_btn.clicked.connect(self.closeRequested.emit)

        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.status_label)
        header_layout.addSpacing(6)
        header_layout.addWidget(self.close_btn)

        # Response area (supports Markdown & code blocks)
        self.response_browser = QTextBrowser(self)
        self.response_browser.setObjectName("ResponseBrowser")
        self.response_browser.setOpenExternalLinks(False)

        # Follow-up input field at the bottom
        self.prompt_input = QLineEdit(self)
        self.prompt_input.setObjectName("PromptInput")
        self.prompt_input.setPlaceholderText("Doplňující dotaz k výřezu… (Enter pro odeslání)")
        self.prompt_input.returnPressed.connect(self._on_submit_prompt)

        layout.addLayout(header_layout)
        layout.addWidget(self.response_browser, stretch=1)
        layout.addWidget(self.prompt_input)

    def _on_submit_prompt(self) -> None:
        text = self.prompt_input.text().strip()
        if text:
            self.prompt_input.clear()
            self.promptSubmitted.emit(text)

    def _tick_loading(self) -> None:
        dots = "." * ((self._loading_step % 3) + 1)
        self._loading_step += 1
        if self._thinking_tokens > 0:
            self.status_label.setText(f"Zkoumám obraz a přemýšlím{dots}")
        else:
            self.status_label.setText(f"Analyzuji výřez{dots}")

    def start_loading(self, message: str = "Čekání na lokální AI model…") -> None:
        """Starts the loading indicator before first tokens arrive."""
        self._raw_markdown = ""
        self._loading_step = 0
        self._thinking_tokens = 0
        self.status_label.setText("Analyzuji výřez.")
        self.response_browser.setHtml(render_styled_markdown_html(f"*{message}*"))
        self._loading_timer.start()

    def on_thinking_progress(self) -> None:
        """Updates status when the VLM is actively running visual reasoning tokens."""
        self._thinking_tokens += 1
        if self._thinking_tokens == 1:
            self.status_label.setText("Zkoumám obraz a přemýšlím…")
            if not self._raw_markdown:
                self.response_browser.setHtml(
                    render_styled_markdown_html(
                        "*Model pečlivě zkoumá detaily a text ve zakroužkovaném výřezu…*"
                    )
                )

    def stop_loading(self, status_text: str = "Hotovo") -> None:
        """Stops the loading indicator once streaming completes or pauses."""
        self._loading_timer.stop()
        self.status_label.setText(status_text)

    def set_markdown_content(self, markdown_text: str) -> None:
        """Replaces the displayed Markdown text using styled HTML rendering."""
        self._raw_markdown = markdown_text
        self.response_browser.setHtml(render_styled_markdown_html(self._raw_markdown))
        sb = self.response_browser.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.maximum())

    def append_token(self, token: str) -> None:
        """Appends a newly streamed token and re-renders styled HTML in real time."""
        if self._loading_timer.isActive():
            self._loading_timer.stop()
        self.status_label.setText("Streamuji odpověď…")
        self._raw_markdown += token
        self.response_browser.setHtml(render_styled_markdown_html(self._raw_markdown))
        sb = self.response_browser.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.maximum())

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
