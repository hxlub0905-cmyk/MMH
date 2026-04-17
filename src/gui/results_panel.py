"""Bottom results panel: per-CMG, per-column Y-CD table."""

from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QHeaderView, QAbstractItemView, QFrame, QHBoxLayout,
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import pyqtSignal, Qt
from ..core.cmg_analyzer import CMGCut

_COLUMNS = ["Image", "CMG", "Col", "Y-CD (px)", "Y-CD (nm)", "Flag", "Status"]

_ROW_COLOURS = {
    "MIN": QColor(80, 20, 20),
    "MAX": QColor(20, 30, 80),
}
_FLAG_TEXT = {
    "MIN": QColor(224, 100, 100),
    "MAX": QColor(100, 150, 240),
}


class ResultsPanel(QWidget):
    row_selected = pyqtSignal(int, int)   # cmg_id, col_id

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── header bar ────────────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("resultsHeader")
        hbox = QHBoxLayout(header)
        hbox.setContentsMargins(12, 0, 12, 0)

        self._status_label = QLabel("No results.")
        self._status_label.setStyleSheet("color:#505878; font-size:11px;")
        hbox.addWidget(self._status_label)
        hbox.addStretch()

        layout.addWidget(header)

        # ── table ─────────────────────────────────────────────────────────────
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self._table)

    # ── public API ────────────────────────────────────────────────────────────

    def show_results(self, image_name: str, cuts: list[CMGCut]) -> None:
        self._table.setRowCount(0)
        total = sum(len(c.measurements) for c in cuts)
        n_cuts = len(cuts)
        self._status_label.setText(
            f"{image_name}  ·  {n_cuts} CMG cut{'s' if n_cuts != 1 else ''}  ·  "
            f"{total} measurement{'s' if total != 1 else ''}"
        )
        for cut in cuts:
            for m in cut.measurements:
                row = self._table.rowCount()
                self._table.insertRow(row)
                values = [
                    image_name,
                    str(m.cmg_id),
                    str(m.col_id),
                    f"{m.y_cd_px:.1f}",
                    f"{m.y_cd_nm:.2f}",
                    m.flag or "—",
                    "OK",
                ]
                bg = _ROW_COLOURS.get(m.flag)
                for col, val in enumerate(values):
                    item = QTableWidgetItem(val)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if bg:
                        item.setBackground(bg)
                    if col == 5 and m.flag in _FLAG_TEXT:
                        item.setForeground(_FLAG_TEXT[m.flag])
                    self._table.setItem(row, col, item)

    def show_fail(self, image_name: str, reason: str = "") -> None:
        self._table.setRowCount(0)
        self._status_label.setText(
            f"{image_name}  ·  FAIL{('  — ' + reason) if reason else ''}"
        )
        self._table.insertRow(0)
        for col, val in enumerate([image_name, "—", "—", "—", "—", "—", f"FAIL"]):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setForeground(QColor(200, 80, 80))
            self._table.setItem(0, col, item)

    def clear(self) -> None:
        self._table.setRowCount(0)
        self._status_label.setText("Select an image and press  ▶ Run Single  to measure.")

    def update_summary(self, n_images: int, n_meas: int, n_fail: int) -> None:
        self._status_label.setText(
            f"Batch complete  ·  {n_images} images  ·  {n_meas} measurements  ·  "
            f"{n_fail} failure{'s' if n_fail != 1 else ''}"
        )

    # ── internal ──────────────────────────────────────────────────────────────

    def _on_selection(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        try:
            cmg_id = int(self._table.item(row, 1).text())
            col_id = int(self._table.item(row, 2).text())
            self.row_selected.emit(cmg_id, col_id)
        except (AttributeError, ValueError):
            pass
