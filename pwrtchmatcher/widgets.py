from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .qt_helpers import LOGO_SVG, open_csv_dialog, svg_pixmap

class DropZone(QFrame):
    selected = Signal(str)

    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label
        self.setObjectName("dropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(164)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(5)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon = QLabel()
        icon.setPixmap(svg_pixmap(LOGO_SVG, 34))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel(f"Drop {label} CSV here")
        title.setObjectName("dropTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hint = QLabel("or click to choose")
        hint.setObjectName("muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(icon)
        layout.addSpacing(4)
        layout.addWidget(title)
        layout.addWidget(hint)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.choose()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if any(url.isLocalFile() and Path(url.toLocalFile()).is_file() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = Path(url.toLocalFile()).expanduser().resolve()
                if path.is_file():
                    self.selected.emit(str(path))
                    event.acceptProposedAction()
                    return
        event.ignore()

    def choose(self) -> None:
        path = open_csv_dialog(self, self.label)
        if path:
            self.selected.emit(path)


class MappingRow(QWidget):
    changed = Signal()

    def __init__(self, label: str) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.label = QLabel(label)
        self.label.setObjectName("fieldLabel")
        self.label.setFixedWidth(100)

        self.combo = QComboBox()
        self.combo.setMinimumHeight(34)
        self.combo.currentIndexChanged.connect(self._changed)

        self.state = QLabel()
        self.state.setObjectName("mappingState")
        self.state.setFixedWidth(36)
        self.state.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.label)
        layout.addWidget(self.combo, 1)
        layout.addWidget(self.state)

    def set_columns(self, columns: list[str], guess: str | None = None) -> None:
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem("Select column…", None)
        for column in columns:
            self.combo.addItem(column, column)

        if guess:
            index = self.combo.findData(guess)
            if index >= 0:
                self.combo.setCurrentIndex(index)
        self.combo.blockSignals(False)
        self.refresh(guess)

    def refresh(self, guess: str | None) -> None:
        value = self.combo.currentData()
        if not value:
            self.state.clear()
        elif guess and value == guess:
            self.state.setText("auto")
        else:
            self.state.setText("edited")

    def _changed(self) -> None:
        self.refresh(None)
        self.changed.emit()

    def value(self) -> str | None:
        return self.combo.currentData()


