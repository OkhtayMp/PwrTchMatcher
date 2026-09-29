from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QBrush, QColor, QPalette
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from .constants import CREATE_COLUMN
from .core import guess_column, read_csv_header, validate_mapping
from .qt_helpers import LOGO_SVG, AnimatedFlowWidget, Worker, svg_pixmap
from .widgets import DropZone, MappingRow


class FilePage(QWidget):
    continueRequested = Signal()
    backRequested = Signal()

    def __init__(self, kind: str, roles: tuple, *, with_target: bool, allow_back: bool) -> None:
        super().__init__()
        self.kind = kind
        self.roles = roles
        self.with_target = with_target
        self.allow_back = allow_back
        self.file_path: Path | None = None
        self.columns: list[str] = []
        self.separator = ","
        self.mapping_rows: dict[str, MappingRow] = {}
        self.target_row: MappingRow | None = None
        self.header_worker: Worker | None = None
        self._load_id = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        self.title = QLabel(kind)
        self.title.setObjectName("pageTitle")
        root.addWidget(self.title)

        self.subtitle = QLabel("Choose the CSV file.")
        self.subtitle.setObjectName("muted")
        root.addWidget(self.subtitle)

        self.drop = DropZone(kind)
        self.drop.selected.connect(self.load_file)
        root.addWidget(self.drop, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.file_bar = QFrame()
        self.file_bar.setObjectName("fileBar")
        self.file_bar.setMaximumWidth(680)
        file_layout = QHBoxLayout(self.file_bar)
        file_layout.setContentsMargins(12, 7, 12, 7)
        file_layout.setSpacing(10)

        self.file_name = QLabel()
        self.file_name.setObjectName("fileName")
        self.file_name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        change = QPushButton("Change")
        change.setObjectName("smallButton")
        change.clicked.connect(self.drop.choose)

        file_layout.addWidget(self.file_name, 1)
        file_layout.addWidget(change)
        self.file_bar.hide()
        root.addWidget(self.file_bar, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.mapping_card = QFrame()
        self.mapping_card.setObjectName("mappingCard")
        self.mapping_card.setMaximumWidth(680)
        mapping_layout = QVBoxLayout(self.mapping_card)
        mapping_layout.setContentsMargins(16, 13, 16, 13)
        mapping_layout.setSpacing(8)

        heading = QHBoxLayout()
        heading.setSpacing(8)
        self.mapping_title = QLabel("Columns")
        self.mapping_title.setObjectName("cardTitle")
        self.columns_count = QLabel()
        self.columns_count.setObjectName("muted")
        heading.addWidget(self.mapping_title)
        heading.addStretch(1)
        heading.addWidget(self.columns_count)
        mapping_layout.addLayout(heading)

        self.rows_box = QVBoxLayout()
        self.rows_box.setSpacing(8)
        mapping_layout.addLayout(self.rows_box)

        if with_target:
            self.target_row = MappingRow("Result")
            self.target_row.changed.connect(self._mapping_changed)
            mapping_layout.addSpacing(2)
            mapping_layout.addWidget(self.target_row)

        self.mapping_card.hide()
        root.addWidget(self.mapping_card, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.status = QLabel()
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.status)

        nav = QHBoxLayout()
        nav.setSpacing(8)

        self.back_button = QPushButton("Back")
        self.back_button.setObjectName("ghostButton")
        self.back_button.setVisible(allow_back)
        self.back_button.clicked.connect(self.backRequested)
        nav.addWidget(self.back_button)
        nav.addStretch(1)

        self.next_button = QPushButton("Continue")
        self.next_button.setObjectName("primaryButton")
        self.next_button.setMinimumWidth(108)
        self.next_button.setEnabled(False)
        self.next_button.clicked.connect(self.validate_and_continue)
        nav.addWidget(self.next_button)
        root.addLayout(nav)
        root.addStretch(1)

    def reset(self) -> None:
        self._load_id += 1
        self.file_path = None
        self.columns.clear()
        self.mapping_rows.clear()
        self.separator = ","
        self.status.clear()
        self.next_button.setEnabled(False)
        self.drop.show()
        self.file_bar.hide()
        self.mapping_card.hide()

    @Slot(str)
    def load_file(self, path_str: str) -> None:
        path = Path(path_str).expanduser().resolve()
        if not path.is_file():
            self.status.setText("File not found.")
            return

        if path.suffix.lower() != ".csv":
            self.status.setText("Choose a CSV file.")
            return

        self._load_id += 1
        request_id = self._load_id
        self.file_path = path
        self.drop.hide()
        self.file_bar.show()
        self.file_name.setText(path.name)
        self.mapping_card.hide()
        self.next_button.setEnabled(False)
        self.status.setText("Reading columns…")

        worker = Worker(read_csv_header, path)
        self.header_worker = worker
        worker.signals.finished.connect(
            lambda payload, rid=request_id: self._header_ready(payload, rid)
        )
        worker.signals.failed.connect(
            lambda message, rid=request_id: self._read_failed(message, rid)
        )
        QThreadPool.globalInstance().start(worker)

    def _header_ready(self, payload: object, request_id: int) -> None:
        if request_id != self._load_id:
            return
        columns, separator = payload
        self.columns = list(columns)
        self.separator = separator
        self._build_mapping()
        self.mapping_card.show()
        self.next_button.setEnabled(True)
        self.status.clear()

    def _read_failed(self, message: str, request_id: int) -> None:
        if request_id != self._load_id:
            return
        self.mapping_card.hide()
        self.next_button.setEnabled(False)
        self.status.setText(message)

    def _build_mapping(self) -> None:
        while self.rows_box.count():
            item = self.rows_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.mapping_rows.clear()

        for key, label, candidates in self.roles:
            guess = guess_column(self.columns, candidates)
            row = MappingRow(label)
            row.set_columns(self.columns, guess)
            self.mapping_rows[key] = row
            self.rows_box.addWidget(row)

        self.columns_count.setText(f"{len(self.columns)} found")

        if self.target_row is not None:
            choices = ["Create new — power TT", *self.columns]
            existing = guess_column(self.columns, ("power TT", "Power TT", "power_tt"))
            self.target_row.set_columns(choices, existing)

            if not existing:
                create_index = self.target_row.combo.findText("Create new — power TT")
                self.target_row.combo.blockSignals(True)
                self.target_row.combo.setCurrentIndex(create_index)
                self.target_row.combo.blockSignals(False)
                self.target_row.refresh(None)

    def mapping(self) -> dict[str, str | None]:
        result = {key: row.value() for key, row in self.mapping_rows.items()}
        if self.target_row is not None:
            value = self.target_row.value()
            result["target"] = CREATE_COLUMN if value == "Create new — power TT" else value
        return result

    def validate_and_continue(self) -> None:
        mapping = self.mapping()
        required = tuple(key for key, _, _ in self.roles)
        error = validate_mapping(mapping, required)
        if error:
            self.status.setText(error)
            return

        if self.with_target:
            target = mapping.get("target")
            if not target:
                self.status.setText("Choose the result column.")
                return
            input_columns = {
                mapping.get("site"),
                mapping.get("fault_time"),
                mapping.get("ticket"),
            }
            if target != CREATE_COLUMN and target in input_columns:
                self.status.setText("Result column must be different from the input columns.")
                return

        self.continueRequested.emit()

    def _mapping_changed(self) -> None:
        self.status.clear()


class ReviewPage(QWidget):
    backRequested = Signal()
    confirmRequested = Signal()

    def __init__(self) -> None:
        super().__init__()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        title = QLabel("Ready to match")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        intro = QLabel("Check the selected columns, then start.")
        intro.setObjectName("muted")
        root.addWidget(intro)

        diagram = AnimatedFlowWidget()
        root.addWidget(diagram, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.rule = QLabel("Same site  •  Fault time must be inside the PWR time window")
        self.rule.setObjectName("rule")
        self.rule.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.rule)

        panels = QHBoxLayout()
        panels.setContentsMargins(0, 2, 0, 0)
        panels.setSpacing(10)

        self.pwr_panel, self.pwr_fields = self._make_panel("PWR")
        self.tch_panel, self.tch_fields = self._make_panel("TCH")

        panels.addWidget(self.pwr_panel, 1)
        panels.addWidget(self.tch_panel, 1)
        root.addLayout(panels)

        self.error = QLabel()
        self.error.setObjectName("status")
        self.error.setWordWrap(True)
        self.error.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.error.hide()
        root.addWidget(self.error)

        root.addStretch(1)

        nav = QHBoxLayout()
        nav.setSpacing(8)

        back = QPushButton("Back")
        back.setObjectName("ghostButton")
        back.clicked.connect(self.backRequested)
        nav.addWidget(back)
        nav.addStretch(1)

        self.start = QPushButton("Start matching")
        self.start.setObjectName("primaryButton")
        self.start.setMinimumWidth(128)
        self.start.clicked.connect(self.confirmRequested)
        nav.addWidget(self.start)
        root.addLayout(nav)

    @staticmethod
    def _make_panel(prefix: str) -> tuple[QFrame, dict[str, QLabel]]:
        panel = QFrame()
        panel.setObjectName("reviewPanel")

        outer = QVBoxLayout(panel)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(7)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(7)

        badge = QLabel(prefix)
        badge.setObjectName("reviewBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(40, 22)
        header.addWidget(badge)

        file_label = QLabel()
        file_label.setObjectName("reviewFile")
        file_label.setWordWrap(False)
        file_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        header.addWidget(file_label, 1)
        outer.addLayout(header)

        separator = QFrame()
        separator.setObjectName("reviewSeparator")
        separator.setFixedHeight(1)
        outer.addWidget(separator)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(5)
        grid.setColumnMinimumWidth(0, 58)
        grid.setColumnStretch(1, 1)

        fields: dict[str, QLabel] = {"file": file_label}
        if prefix == "PWR":
            rows = (
                ("site", "Site"),
                ("start", "Started"),
                ("end", "Cleared"),
            )
        else:
            rows = (
                ("site", "Site"),
                ("fault", "Fault"),
                ("ticket", "Ticket"),
                ("result", "Result"),
            )

        for row_index, (key, label_text) in enumerate(rows):
            label = QLabel(label_text)
            label.setObjectName("reviewKey")
            label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

            value = QLabel("—")
            value.setObjectName("reviewValueAccent" if key == "result" else "reviewValue")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setMinimumHeight(18)
            value.setToolTip("—")

            grid.addWidget(label, row_index, 0)
            grid.addWidget(value, row_index, 1)
            fields[key] = value

        outer.addLayout(grid)
        return panel, fields

    @staticmethod
    def _set_field(fields: dict[str, QLabel], key: str, value: str) -> None:
        label = fields[key]
        text = value.strip() if value and value.strip() else "—"
        label.setText(text)
        label.setToolTip(text)

    def set_review(
        self,
        pwr_path: Path,
        pwr_mapping: dict[str, str | None],
        tch_path: Path,
        tch_mapping: dict[str, str | None],
    ) -> None:
        self.error.hide()
        self.error.clear()
        self.start.setEnabled(True)

        self._set_field(self.pwr_fields, "file", pwr_path.name)
        self._set_field(self.pwr_fields, "site", str(pwr_mapping.get("site")))
        self._set_field(self.pwr_fields, "start", str(pwr_mapping.get("start")))
        self._set_field(self.pwr_fields, "end", str(pwr_mapping.get("end")))

        target = tch_mapping.get("target")
        target_text = "Create new: power TT" if target == CREATE_COLUMN else str(target)

        self._set_field(self.tch_fields, "file", tch_path.name)
        self._set_field(self.tch_fields, "site", str(tch_mapping.get("site")))
        self._set_field(self.tch_fields, "fault", str(tch_mapping.get("fault_time")))
        self._set_field(self.tch_fields, "ticket", str(tch_mapping.get("ticket")))
        self._set_field(self.tch_fields, "result", target_text)

    def show_error(self, message: str) -> None:
        self.error.setText(message)
        self.error.show()
        self.start.setEnabled(True)


class ProcessingPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 18, 0, 18)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.setSpacing(10)

        icon = QLabel()
        icon.setPixmap(svg_pixmap(LOGO_SVG, 40))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(icon)

        title = QLabel("Matching files")
        title.setObjectName("pageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        self.status = QLabel("Starting…")
        self.status.setObjectName("muted")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.status)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedWidth(360)
        self.bar.setFixedHeight(6)
        root.addWidget(self.bar, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.detail = QLabel("PWR  →  match  →  TCH")
        self.detail.setObjectName("tiny")
        self.detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.detail)

    def update_progress(self, value: int, text: str) -> None:
        self.bar.setValue(max(0, min(100, value)))
        self.status.setText(text)


class PreviewTableModel(QAbstractTableModel):
    """Small table model for a bounded, non-blocking CSV preview."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.headers: list[str] = []
        self.rows: list[list[str]] = []
        self.unmatched: list[bool] = []

    def set_data(self, headers: list[str], rows: list[list[str]], unmatched: list[bool]) -> None:
        self.beginResetModel()
        self.headers = headers
        self.rows = rows
        self.unmatched = unmatched
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        return 0 if parent is not None and parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        return 0 if parent is not None and parent.isValid() else len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row = index.row()
        column = index.column()
        if row >= len(self.rows) or column >= len(self.headers):
            return None

        value = self.rows[row][column]
        if role == Qt.ItemDataRole.DisplayRole:
            return value
        if role == Qt.ItemDataRole.ToolTipRole:
            return value
        if role == Qt.ItemDataRole.ForegroundRole and self.unmatched[row]:
            palette = QApplication.instance().palette()
            base = palette.color(QPalette.ColorRole.Base)
            text = palette.color(QPalette.ColorRole.Text)
            # A readable neutral gray, intentionally not the disabled color.
            gray = QColor(
                round(text.red() * 0.58 + base.red() * 0.42),
                round(text.green() * 0.58 + base.green() * 0.42),
                round(text.blue() * 0.58 + base.blue() * 0.42),
            )
            return QBrush(gray)
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal and 0 <= section < len(self.headers):
            return self.headers[section]
        if orientation == Qt.Orientation.Vertical:
            return str(section + 1)
        return None


def read_csv_preview(
    path: Path,
    separator: str,
    result_column: str,
    *,
    query: str = "",
    limit: int = 260,
) -> tuple[list[str], list[list[str]], list[bool], int, bool]:
    """Read a small bounded preview without loading a large CSV into memory."""
    query = query.strip().casefold()
    limit = max(1, int(limit))
    headers: list[str] = []
    rows: list[list[str]] = []
    unmatched: list[bool] = []
    result_index = -1
    scanned = 0

    with path.open("r", encoding="utf-8-sig", newline="", errors="replace") as handle:
        reader = csv.reader(handle, delimiter=separator)
        header = next(reader, [])
        headers = [str(item).strip() for item in header]
        if not headers:
            raise ValueError("The output CSV has no header row.")

        if result_column in headers:
            result_index = headers.index(result_column)

        for raw_row in reader:
            scanned += 1
            row = [str(value) for value in raw_row]
            if len(row) < len(headers):
                row.extend([""] * (len(headers) - len(row)))
            elif len(row) > len(headers):
                row = row[: len(headers)]

            if query and query not in " ".join(row).casefold():
                continue

            rows.append(row)
            unmatched.append(result_index >= 0 and not row[result_index].strip())
            if len(rows) >= limit:
                return headers, rows, unmatched, scanned, True

    return headers, rows, unmatched, scanned, False


class PreviewPage(QWidget):
    saveRequested = Signal()
    startOver = Signal()
    openFile = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.output: Path | None = None
        self.separator = ","
        self.result_column = "power TT"
        self.matches = 0
        self.total_rows = 0
        self._request_id = 0
        self.preview_worker: Worker | None = None

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(220)
        self._search_timer.timeout.connect(self._run_search)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
        root.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel("Preview")
        title.setObjectName("pageTitle")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.count = QLabel()
        self.count.setObjectName("previewMeta")
        title_row.addWidget(self.count)
        root.addLayout(title_row)

        self.file_name = QLabel()
        self.file_name.setObjectName("reviewFile")
        self.file_name.setToolTip("")
        root.addWidget(self.file_name)

        search_row = QHBoxLayout()
        search_row.setSpacing(7)
        self.search = QLineEdit()
        self.search.setObjectName("previewSearch")
        self.search.setPlaceholderText("Search rows…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._search_changed)
        search_row.addWidget(self.search, 1)
        self.search_state = QLabel("Preview")
        self.search_state.setObjectName("previewMeta")
        search_row.addWidget(self.search_state)
        root.addLayout(search_row)

        frame = QFrame()
        frame.setObjectName("previewFrame")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        self.model = PreviewTableModel(self)
        self.table = QTableView()
        self.table.setObjectName("previewTable")
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(27)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(True)
        frame_layout.addWidget(self.table)
        root.addWidget(frame, 1)

        legend = QHBoxLayout()
        hint = QLabel("Gray rows = no matching result")
        hint.setObjectName("previewMeta")
        legend.addWidget(hint)
        legend.addStretch(1)
        self.scan_state = QLabel()
        self.scan_state.setObjectName("previewMeta")
        legend.addWidget(self.scan_state)
        root.addLayout(legend)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        again = QPushButton("Start again")
        again.setObjectName("ghostButton")
        again.clicked.connect(self.startOver)
        buttons.addWidget(again)
        buttons.addStretch(1)

        self.save_button = QPushButton("Save CSV")
        self.save_button.setObjectName("primaryButton")
        self.save_button.clicked.connect(self.saveRequested)
        buttons.addWidget(self.save_button)

        self.open_button = QPushButton("Open")
        self.open_button.setObjectName("ghostButton")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self.openFile)
        buttons.addWidget(self.open_button)
        root.addLayout(buttons)

    def set_result(self, result: dict[str, object]) -> None:
        self.output = Path(str(result["output"]))
        self.separator = str(result.get("separator", ","))
        self.result_column = str(result.get("result_column", "power TT"))
        self.matches = int(result.get("matches", 0))
        self.total_rows = int(result.get("tch_rows", 0))
        self.file_name.setText(self.output.name)
        self.file_name.setToolTip(str(self.output))
        self.count.setText(f"{self.matches:,} matched / {self.total_rows:,} rows")
        self.save_button.setEnabled(True)
        self.open_button.setEnabled(False)
        self.search.setEnabled(True)
        self.search.clear()
        self._request_preview("")

    def mark_saved(self, path: Path) -> None:
        self.output = path
        self.file_name.setText(path.name)
        self.file_name.setToolTip(str(path))
        self.save_button.setEnabled(False)
        self.open_button.setEnabled(True)

    def _search_changed(self, _text: str) -> None:
        self._search_timer.start()

    def _run_search(self) -> None:
        self._request_preview(self.search.text())

    def _request_preview(self, query: str) -> None:
        if self.output is None or not self.output.exists():
            return

        self._request_id += 1
        request_id = self._request_id
        self.search_state.setText("Searching…" if query.strip() else "Previewing…")
        self.scan_state.clear()

        worker = Worker(
            read_csv_preview,
            self.output,
            self.separator,
            self.result_column,
            query=query,
            limit=260,
        )
        self.preview_worker = worker
        worker.signals.finished.connect(
            lambda payload, rid=request_id: self._preview_ready(payload, rid, bool(query.strip()))
        )
        worker.signals.failed.connect(
            lambda message, rid=request_id: self._preview_failed(message, rid)
        )
        QThreadPool.globalInstance().start(worker)

    def _preview_ready(self, payload: object, request_id: int, searched: bool) -> None:
        if request_id != self._request_id:
            return

        headers, rows, unmatched, scanned, has_more = payload
        self.model.set_data(headers, rows, unmatched)
        shown = len(rows)
        self.search_state.setText(f"{shown:,} shown")
        if searched:
            self.scan_state.setText(
                f"First {shown:,} matches" if has_more else f"Scanned {scanned:,} rows"
            )
        else:
            self.scan_state.setText("First rows")

        self.table.resizeColumnsToContents()
        for index in range(self.model.columnCount()):
            self.table.setColumnWidth(index, min(max(self.table.columnWidth(index), 90), 360))

    def _preview_failed(self, message: str, request_id: int) -> None:
        if request_id != self._request_id:
            return
        self.search_state.setText("Preview unavailable")
        self.scan_state.setText(message)


# -----------------------------------------------------------------------------
# Processing
# -----------------------------------------------------------------------------
