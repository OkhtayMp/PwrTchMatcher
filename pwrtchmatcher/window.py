from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QUrl, Slot
from PySide6.QtGui import QDesktopServices, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .constants import APP_NAME, GITHUB_URL, PWR_ROLES, TCH_ROLES
from .core import safe_unlink, validate_mapping
from .matcher import process_files
from .pages import FilePage, PreviewPage, ProcessingPage, ReviewPage
from .qt_helpers import LOGO_SVG, Worker, save_csv_dialog, svg_pixmap


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(720, 560)
        self.resize(790, 620)

        self.current_worker: Worker | None = None
        self.processing_page: ProcessingPage | None = None
        self.done_page: PreviewPage | None = None
        self.temp_output: Path | None = None
        self.last_output: Path | None = None

        self.pwr_page = FilePage("PWR", PWR_ROLES, with_target=False, allow_back=False)
        self.tch_page = FilePage("TCH", TCH_ROLES, with_target=True, allow_back=True)
        self.review_page = ReviewPage()

        self.stack = QStackedWidget()
        self.stack.addWidget(self.pwr_page)
        self.stack.addWidget(self.tch_page)
        self.stack.addWidget(self.review_page)

        self._build_ui()
        self._connect()
        self._show_step(0)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("appRoot")
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 18, 28, 9)
        root.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(8)

        logo = QLabel()
        logo.setPixmap(svg_pixmap(LOGO_SVG, 26))
        header.addWidget(logo)

        brand = QLabel("PWR / TCH")
        brand.setObjectName("brand")
        header.addWidget(brand)
        header.addStretch(1)

        self.step = QLabel()
        self.step.setObjectName("step")
        header.addWidget(self.step)
        root.addLayout(header)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFixedHeight(1)
        root.addWidget(divider)

        root.addWidget(self.stack, 1)

        footer = QLabel(f'<a href="{GITHUB_URL}">code.py · OkhtayMp · GitHub</a>')
        footer.setObjectName("footer")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setOpenExternalLinks(True)
        root.addWidget(footer)

        central.setStyleSheet(build_style(QApplication.instance()))
        self.setCentralWidget(central)

    def _connect(self) -> None:
        self.pwr_page.continueRequested.connect(self.go_tch)
        self.tch_page.backRequested.connect(self.back_pwr)
        self.tch_page.continueRequested.connect(self.go_review)
        self.review_page.backRequested.connect(self.back_tch)
        self.review_page.confirmRequested.connect(self.start_from_review)

    def _show_step(self, index: int) -> None:
        labels = ("PWR", "TCH", "CHECK", "RUN", "DONE")
        if 0 <= index < len(labels):
            self.step.setText(f"{index + 1} / {len(labels)}   {labels[index]}")

    @Slot()
    def go_tch(self) -> None:
        self.stack.setCurrentWidget(self.tch_page)
        self._show_step(1)

    @Slot()
    def go_review(self) -> None:
        if not self.pwr_page.file_path or not self.tch_page.file_path:
            return
        self.review_page.set_review(
            self.pwr_page.file_path,
            self.pwr_page.mapping(),
            self.tch_page.file_path,
            self.tch_page.mapping(),
        )
        self.stack.setCurrentWidget(self.review_page)
        self._show_step(2)

    @Slot()
    def back_tch(self) -> None:
        self.stack.setCurrentWidget(self.tch_page)
        self._show_step(1)

    @Slot()
    def back_pwr(self) -> None:
        self.stack.setCurrentWidget(self.pwr_page)
        self._show_step(0)

    @Slot()
    def start_from_review(self) -> None:
        if not self.pwr_page.file_path or not self.tch_page.file_path:
            self.review_page.show_error("Choose both CSV files first.")
            return

        pwr_mapping = self.pwr_page.mapping()
        tch_mapping = self.tch_page.mapping()

        error = validate_mapping(pwr_mapping, ("site", "start", "end"))
        if error:
            self.review_page.show_error(f"PWR: {error}")
            return

        error = validate_mapping(tch_mapping, ("site", "fault_time", "ticket"))
        if error:
            self.review_page.show_error(f"TCH: {error}")
            return

        target = tch_mapping.get("target")
        if not target:
            self.review_page.show_error("Choose the TCH result column.")
            return

        self.review_page.start.setEnabled(False)

        try:
            with tempfile.NamedTemporaryFile(
                prefix=f".{self.tch_page.file_path.stem}_matched_",
                suffix=".csv.part",
                dir=self.tch_page.file_path.parent,
                delete=False,
            ) as handle:
                self.temp_output = Path(handle.name)
        except OSError as exc:
            self.review_page.show_error(f"Could not create a temporary output file.\n{exc}")
            self.review_page.start.setEnabled(True)
            return

        safe_unlink(self.temp_output)

        self.start_processing(self.temp_output)

    def start_processing(self, output_path: Path) -> None:
        assert self.pwr_page.file_path and self.tch_page.file_path

        self.last_output = None
        self.processing_page = ProcessingPage()
        self.stack.addWidget(self.processing_page)
        self.stack.setCurrentWidget(self.processing_page)
        self._show_step(3)

        worker = Worker(
            process_files,
            self.pwr_page.file_path,
            self.pwr_page.mapping(),
            self.pwr_page.separator,
            self.tch_page.file_path,
            self.tch_page.mapping(),
            self.tch_page.separator,
            output_path,
        )
        worker.signals.progress.connect(self._processing_progress)
        worker.signals.finished.connect(self.processing_finished)
        worker.signals.failed.connect(self.processing_failed)
        self.current_worker = worker
        self._set_navigation_enabled(False)
        QThreadPool.globalInstance().start(worker)

    @Slot(int, str)
    def _processing_progress(self, value: int, text: str) -> None:
        if self.processing_page is not None:
            self.processing_page.update_progress(value, text)

    @Slot(object)
    def processing_finished(self, result: object) -> None:
        self.current_worker = None
        self._set_navigation_enabled(True)

        result_dict = dict(result)
        if self.processing_page is not None:
            self.stack.removeWidget(self.processing_page)
            self.processing_page.deleteLater()
            self.processing_page = None

        page = PreviewPage()
        page.set_result(result_dict)
        page.saveRequested.connect(self.save_output)
        page.openFile.connect(self.open_output)
        page.startOver.connect(self.restart)
        self.done_page = page
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        self._show_step(4)

    @Slot(str)
    def processing_failed(self, message: str) -> None:
        self.current_worker = None
        self._set_navigation_enabled(True)
        safe_unlink(self.temp_output)
        self.temp_output = None

        if self.processing_page is not None:
            self.stack.removeWidget(self.processing_page)
            self.processing_page.deleteLater()
            self.processing_page = None

        self.stack.setCurrentWidget(self.review_page)
        self._show_step(2)
        self.review_page.show_error("Nothing was saved. " + message)

    def _set_navigation_enabled(self, enabled: bool) -> None:
        self.pwr_page.setEnabled(enabled)
        self.tch_page.setEnabled(enabled)
        self.review_page.setEnabled(enabled)

    @Slot()
    def save_output(self) -> None:
        if self.temp_output is None or not self.temp_output.exists() or self.done_page is None:
            return

        assert self.tch_page.file_path
        default = self.tch_page.file_path.with_name(self.tch_page.file_path.stem + "_matched.csv")
        output = save_csv_dialog(self, default)
        if not output:
            return

        output_path = Path(output).expanduser().resolve()
        source_paths = {
            self.pwr_page.file_path.resolve(),
            self.tch_page.file_path.resolve(),
        }
        if output_path in source_paths:
            QMessageBox.warning(
                self,
                APP_NAME,
                "Choose a new file. Source CSV files are never overwritten.",
            )
            return

        try:
            if output_path.exists():
                answer = QMessageBox.question(
                    self,
                    APP_NAME,
                    f"Replace '{output_path.name}'?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if answer != QMessageBox.StandardButton.Yes:
                    return
                output_path.unlink()

            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(self.temp_output), str(output_path))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, APP_NAME, f"Could not save the CSV.\n{exc}")
            return

        self.last_output = output_path
        self.temp_output = None
        self.done_page.mark_saved(output_path)

    @Slot()
    def open_output(self) -> None:
        path = self.last_output
        if path is None and self.done_page is not None:
            path = self.done_page.output
        if path is None or not path.exists():
            return

        try:
            url = QUrl.fromLocalFile(str(path))
            if not QDesktopServices.openUrl(url):
                raise RuntimeError("The operating system could not open the file.")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, APP_NAME, f"Could not open the CSV.\n{exc}")

    @Slot()
    def restart(self) -> None:
        if self.current_worker is not None:
            return

        safe_unlink(self.temp_output)
        self.temp_output = None
        self.last_output = None
        self.pwr_page.reset()
        self.tch_page.reset()

        if self.done_page is not None:
            self.stack.removeWidget(self.done_page)
            self.done_page.deleteLater()
            self.done_page = None

        self.stack.setCurrentWidget(self.pwr_page)
        self._show_step(0)

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.current_worker is not None:
            QMessageBox.information(
                self,
                APP_NAME,
                "The operation is still running.",
            )
            event.ignore()
            return
        safe_unlink(self.temp_output)
        self.temp_output = None
        event.accept()


def build_style(app: QApplication) -> str:
    """Build a small app-only stylesheet from the current system palette."""
    palette = app.palette()

    def color(role) -> str:
        return palette.color(role).name()

    window = color(palette.ColorRole.Window)
    base = color(palette.ColorRole.Base)
    text = color(palette.ColorRole.Text)
    window_text = color(palette.ColorRole.WindowText)
    button = color(palette.ColorRole.Button)
    button_text = color(palette.ColorRole.ButtonText)
    alternate = color(palette.ColorRole.AlternateBase)
    mid = color(palette.ColorRole.Mid)
    midlight = color(palette.ColorRole.Midlight)
    highlight = color(palette.ColorRole.Highlight)
    highlighted_text = color(palette.ColorRole.HighlightedText)
    disabled_text = palette.color(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text).name()

    # Keep the UI visually close to the desktop/native Qt theme. The app only
    # adds hierarchy, spacing and semantic emphasis; it does not replace the
    # system's overall color scheme.
    return f"""
QWidget#appRoot {{
    background: {window};
    color: {window_text};
    font-family: Inter, Noto Sans, Sans Serif;
    font-size: 13px;
}}

QLabel {{
    background: transparent;
    color: {window_text};
}}

QLabel#brand {{
    color: {window_text};
    font-size: 12px;
    font-weight: 700;
}}

QLabel#step {{
    color: {mid};
    font-size: 9px;
    font-weight: 600;
}}

QLabel#pageTitle {{
    color: {window_text};
    font-size: 21px;
    font-weight: 700;
}}

QLabel#muted, QLabel#reviewText {{
    color: {mid};
    font-size: 11px;
}}

QLabel#tiny {{
    color: {mid};
    font-size: 9px;
}}

QLabel#status {{
    color: {text};
    font-size: 11px;
}}

QLabel#fileName, QLabel#reviewFile {{
    color: {text};
    font-size: 11px;
    font-weight: 600;
}}

QLabel#reviewBadge {{
    background: {alternate};
    border: 1px solid {midlight};
    border-radius: 6px;
    color: {highlight};
    font-size: 9px;
    font-weight: 700;
    padding: 3px 7px;
}}

QLabel#reviewKey, QLabel#fieldLabel {{
    color: {mid};
    font-size: 10px;
    font-weight: 600;
}}

QLabel#reviewValue {{
    background: transparent;
    color: {text};
    font-size: 10px;
    font-weight: 600;
}}

QLabel#reviewValueAccent {{
    background: transparent;
    color: {highlight};
    font-size: 10px;
    font-weight: 700;
}}

QLabel#mappingState {{
    color: {highlight};
    font-size: 8px;
}}

QLabel#dropTitle {{
    color: {window_text};
    font-size: 14px;
    font-weight: 650;
}}

QLabel#cardTitle {{
    color: {window_text};
    font-size: 12px;
    font-weight: 650;
}}

QLabel#rule {{
    color: {mid};
    font-size: 10px;
}}

QLabel#footer, QLabel#footer a {{
    color: {mid};
    font-size: 8px;
    text-decoration: none;
}}

QFrame#divider, QFrame#reviewSeparator {{
    background: {midlight};
    border: 0;
}}

QFrame#dropZone, QFrame#fileBar, QFrame#mappingCard,
QFrame#reviewCard, QFrame#reviewPanel {{
    background: {alternate};
    border: 1px solid {midlight};
    border-radius: 9px;
}}

QFrame#dropZone {{
    min-width: 430px;
    max-width: 590px;
}}

QFrame#dropZone:hover, QFrame#reviewPanel:hover {{
    border-color: {highlight};
}}

QFrame#reviewLine {{
    background: {base};
    border: 1px solid {midlight};
    border-radius: 7px;
}}

QPushButton {{
    background: {button};
    border: 1px solid {mid};
    border-radius: 7px;
    min-height: 34px;
    padding: 0 12px;
    color: {button_text};
    font-size: 11px;
    font-weight: 600;
}}

QPushButton:hover {{
    background: {midlight};
}}

QPushButton:pressed {{
    background: {mid};
}}

QPushButton:disabled {{
    color: {disabled_text};
    background: {alternate};
    border-color: {midlight};
}}

QPushButton#ghostButton {{
    background: transparent;
    border-color: {midlight};
}}

QPushButton#ghostButton:hover {{
    background: {alternate};
}}

QPushButton#smallButton {{
    min-height: 27px;
    padding: 0 9px;
    font-size: 10px;
}}

QPushButton#primaryButton {{
    background: {highlight};
    border-color: {highlight};
    color: {highlighted_text};
    font-weight: 700;
}}

QPushButton#primaryButton:hover {{
    background: {highlight};
}}

QComboBox {{
    background: {base};
    border: 1px solid {mid};
    border-radius: 7px;
    min-height: 34px;
    padding: 0 9px;
    color: {text};
}}

QComboBox:hover, QComboBox:focus {{
    border-color: {highlight};
}}

QComboBox::drop-down {{
    width: 24px;
    border: 0;
    background: transparent;
}}

QComboBox QAbstractItemView {{
    background: {base};
    color: {text};
    border: 1px solid {mid};
    selection-background-color: {highlight};
    selection-color: {highlighted_text};
    outline: 0;
    padding: 3px;
}}

QLineEdit#previewSearch {{
    background: {base};
    border: 1px solid {mid};
    border-radius: 7px;
    min-height: 34px;
    padding: 0 10px;
    color: {text};
    selection-background-color: {highlight};
    selection-color: {highlighted_text};
}}

QLineEdit#previewSearch:focus {{
    border-color: {highlight};
}}

QLabel#previewMeta {{
    color: {mid};
    font-size: 9px;
    font-weight: 600;
}}

QFrame#previewFrame {{
    background: {base};
    border: 1px solid {midlight};
    border-radius: 8px;
}}

QTableView#previewTable {{
    background: {base};
    alternate-background-color: {alternate};
    color: {text};
    border: 0;
    outline: 0;
    gridline-color: {midlight};
    selection-background-color: {highlight};
    selection-color: {highlighted_text};
    font-size: 10px;
}}

QTableView#previewTable::item {{
    padding: 5px 8px;
    border: 0;
}}

QTableView#previewTable QHeaderView::section {{
    background: {alternate};
    color: {mid};
    border: 0;
    border-bottom: 1px solid {midlight};
    padding: 6px 8px;
    font-size: 9px;
    font-weight: 700;
}}

QProgressBar {{
    background: {alternate};
    border: 0;
    border-radius: 3px;
    min-height: 6px;
}}

QProgressBar::chunk {{
    background: {highlight};
    border-radius: 3px;
}}
"""
