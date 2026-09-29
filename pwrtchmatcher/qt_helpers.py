from __future__ import annotations

import inspect
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import (
    QByteArray,
    QObject,
    QPointF,
    QRectF,
    QRunnable,
    QSize,
    QTimer,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QPainter, QPalette, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QFileDialog, QSizePolicy, QWidget


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(int, str)


class Worker(QRunnable):
    def __init__(self, function: Callable, *args, **kwargs) -> None:
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            kwargs = dict(self.kwargs)

            # Only inject the progress callback when the target function
            # actually accepts a parameter named `progress`. This prevents
            # UI worker plumbing from changing the signature of simple
            # functions such as read_csv_header().
            try:
                signature = inspect.signature(self.function)
                accepts_progress = (
                    "progress" in signature.parameters
                    or any(
                        parameter.kind == inspect.Parameter.VAR_KEYWORD
                        for parameter in signature.parameters.values()
                    )
                )
            except (TypeError, ValueError):
                accepts_progress = False

            if accepts_progress:
                kwargs["progress"] = self.signals.progress.emit

            result = self.function(*self.args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.signals.finished.emit(result)


# -----------------------------------------------------------------------------
# SVG
# -----------------------------------------------------------------------------


# File dialogs intentionally use the operating system native UI and icons.


LOGO_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">
  <rect x="1.5" y="1.5" width="45" height="45" rx="12" fill="__PANEL__" fill-opacity="0.12" stroke="__BORDER__"/>
  <path d="M24 36V15M17 36h14" stroke="__ACCENT__" stroke-width="1.9" stroke-linecap="round"/>
  <path d="M18.5 22c3-3.6 8-3.6 11 0M15 18.5c5-5.9 13-5.9 18 0" fill="none" stroke="__ACCENT__" stroke-width="1.5" stroke-linecap="round"/>
  <circle cx="24" cy="13" r="1.8" fill="__ACCENT__"/>
</svg>
"""


FLOW_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" width="540" height="112" viewBox="0 0 540 112">
  <rect x="8" y="21" width="118" height="68" rx="12" fill="__PANEL__" stroke="__BORDER__"/>
  <text x="67" y="49" text-anchor="middle" font-family="Sans" font-size="16" font-weight="600" fill="__WINDOW_TEXT__">PWR</text>
  <text x="67" y="69" text-anchor="middle" font-family="Sans" font-size="11" fill="__MUTED__">time windows</text>

  <path d="M140 55H185" fill="none" stroke="__CONNECTOR__" stroke-width="1.6"/>
  <path d="M178 50l8 5-8 5" fill="none" stroke="__CONNECTOR__" stroke-width="1.6"/>

  <rect x="196" y="15" width="148" height="80" rx="13" fill="__PANEL_STRONG__" stroke="__ACCENT_DARK__"/>
  <circle cx="222" cy="55" r="13" fill="__ACCENT_SURFACE__" stroke="__ACCENT_DARK__"/>
  <path d="M216 55h12M222 49v12" stroke="__ACCENT__" stroke-width="1.6" stroke-linecap="round"/>
  <text x="282" y="50" text-anchor="middle" font-family="Sans" font-size="15" font-weight="600" fill="__WINDOW_TEXT__">MATCH</text>
  <text x="282" y="70" text-anchor="middle" font-family="Sans" font-size="11" fill="__MUTED__">site + fault time</text>

  <path d="M358 55H403" fill="none" stroke="__CONNECTOR__" stroke-width="1.6"/>
  <path d="M396 50l8 5-8 5" fill="none" stroke="__CONNECTOR__" stroke-width="1.6"/>

  <rect x="414" y="21" width="118" height="68" rx="12" fill="__PANEL__" stroke="__BORDER__"/>
  <text x="473" y="49" text-anchor="middle" font-family="Sans" font-size="16" font-weight="600" fill="__WINDOW_TEXT__">TCH</text>
  <text x="473" y="69" text-anchor="middle" font-family="Sans" font-size="11" fill="__MUTED__">result column</text>
</svg>
"""


DONE_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">
  <circle cx="24" cy="24" r="20" fill="none" stroke="__ACCENT_DARK__" stroke-width="1.8"/>
  <path d="M15 24.5l6 6 12-13" fill="none" stroke="__ACCENT__" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""


def _palette_color(role: QPalette.ColorRole, group: QPalette.ColorGroup | None = None) -> str:
    palette = QApplication.instance().palette()
    if group is None:
        return palette.color(role).name(QColor.NameFormat.HexRgb)
    return palette.color(group, role).name(QColor.NameFormat.HexRgb)


def _mix_rgb(first: str, second: str, amount: float) -> str:
    a = QColor(first)
    b = QColor(second)
    amount = max(0.0, min(1.0, amount))
    r = round(a.red() + (b.red() - a.red()) * amount)
    g = round(a.green() + (b.green() - a.green()) * amount)
    bl = round(a.blue() + (b.blue() - a.blue()) * amount)
    return QColor(r, g, bl).name(QColor.NameFormat.HexRgb)


def themed_svg(svg: str) -> str:
    """Apply the current Qt system palette to the internal SVG artwork."""
    palette = QApplication.instance().palette()
    window = palette.color(QPalette.ColorRole.Window).name(QColor.NameFormat.HexRgb)
    base = palette.color(QPalette.ColorRole.Base).name(QColor.NameFormat.HexRgb)
    text = palette.color(QPalette.ColorRole.WindowText).name(QColor.NameFormat.HexRgb)
    muted = palette.color(QPalette.ColorRole.Mid).name(QColor.NameFormat.HexRgb)
    border = palette.color(QPalette.ColorRole.Midlight).name(QColor.NameFormat.HexRgb)
    accent = palette.color(QPalette.ColorRole.Highlight).name(QColor.NameFormat.HexRgb)
    accent_surface = _mix_rgb(base, accent, 0.16)
    accent_dark = _mix_rgb(accent, window, 0.35)
    panel = _mix_rgb(window, base, 0.42)
    panel_strong = _mix_rgb(base, accent, 0.06)
    connector = _mix_rgb(muted, accent, 0.35)

    colors = {
        "__WINDOW__": window,
        "__BASE__": base,
        "__WINDOW_TEXT__": text,
        "__MUTED__": muted,
        "__BORDER__": border,
        "__ACCENT__": accent,
        "__ACCENT_SURFACE__": accent_surface,
        "__ACCENT_DARK__": accent_dark,
        "__PANEL__": panel,
        "__PANEL_STRONG__": panel_strong,
        "__CONNECTOR__": connector,
    }
    for token, value in colors.items():
        svg = svg.replace(token, value)
    return svg


def svg_pixmap(svg: str, size: int) -> QPixmap:
    """Render themed SVG artwork at the requested width, preserving its ratio."""
    renderer = QSvgRenderer(QByteArray(themed_svg(svg).encode("utf-8")))

    source_size = renderer.defaultSize()
    if source_size.width() <= 0 or source_size.height() <= 0:
        width = height = size
    else:
        width = size
        height = max(1, round(size * source_size.height() / source_size.width()))

    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


class AnimatedFlowWidget(QWidget):
    """
    Static flow diagram.

    The SVG itself is rendered exactly as supplied.
    No timer, no travelling signal, no particles, no pulsing ring,
    and no additional painting is performed over the SVG.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.setObjectName("flowDiagram")
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

        self._renderer = QSvgRenderer()
        self._last_svg = ""

        # Load immediately so sizeHint() works correctly.
        self._current_renderer()

    def sizeHint(self) -> QSize:  # noqa: N802
        renderer = self._current_renderer()
        size = renderer.defaultSize()

        if size.isValid() and size.width() > 0 and size.height() > 0:
            return size

        return QSize(540, 112)

    def _current_renderer(self) -> QSvgRenderer:
        svg = themed_svg(FLOW_SVG)

        if svg != self._last_svg:
            self._renderer.load(
                QByteArray(svg.encode("utf-8"))
            )
            self._last_svg = svg
            self.updateGeometry()
            self.update()

        return self._renderer

    def paintEvent(self, event) -> None:  # noqa: N802
        del event

        renderer = self._current_renderer()
        source = renderer.defaultSize()

        if source.width() <= 0 or source.height() <= 0:
            return

        available = self.rect().adjusted(0, 0, -1, -1)

        scale = min(
            available.width() / source.width(),
            available.height() / source.height(),
        )

        width = max(
            1,
            round(source.width() * scale),
        )
        height = max(
            1,
            round(source.height() * scale),
        )

        target = QRectF(
            (self.width() - width) / 2,
            (self.height() - height) / 2,
            width,
            height,
        )

        painter = QPainter(self)
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True,
        )

        # Render ONLY the SVG.
        #
        # IMPORTANT:
        # There is intentionally no additional drawing here.
        # No travelling dot.
        # No halo.
        # No pulse.
        # No moving ring.
        renderer.render(painter, target)

        painter.end()

# -----------------------------------------------------------------------------
# UI widgets
# -----------------------------------------------------------------------------


def _run_native_file_dialog(callback):
    """Run a native file dialog without inheriting the app's stylesheet."""
    app = QApplication.instance()
    old_stylesheet = app.styleSheet() if app is not None else ""

    if app is not None:
        app.setStyleSheet("")

    try:
        return callback()
    finally:
        if app is not None:
            app.setStyleSheet(old_stylesheet)


def open_csv_dialog(parent: QWidget, label: str) -> str:
    """Open the system file picker without the application's visual theme."""
    def _open():
        path, _ = QFileDialog.getOpenFileName(
            parent,
            f"Choose {label} CSV",
            str(Path.home()),
            "CSV files (*.csv *.CSV);;All files (*)",
            options=QFileDialog.Option.DontUseCustomDirectoryIcons,
        )
        return path

    return _run_native_file_dialog(_open)


def save_csv_dialog(parent: QWidget, default_path: Path) -> str:
    """Open the system save dialog without the application's visual theme."""
    def _save():
        path, _ = QFileDialog.getSaveFileName(
            parent,
            "Save matched CSV",
            str(default_path),
            "CSV files (*.csv *.CSV);;All files (*)",
            options=QFileDialog.Option.DontUseCustomDirectoryIcons,
        )
        return path

    path = _run_native_file_dialog(_save)

    if not path:
        return ""

    selected = Path(path)
    if selected.suffix.lower() != ".csv":
        selected = selected.with_suffix(".csv")
    return str(selected)


