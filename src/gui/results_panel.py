"""Results table: per-CMG, per-column Y-CD measurements."""

from __future__ import annotations
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QLabel, QHeaderView, QAbstractItemView,
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import pyqtSignal
from ..core.cmg_analyzer import CMGCut

_COLUMNS = ["Image", "CMG ID", "Col ID", "Y-CD (px)", "Y-CD (nm)", "Flag", "Status"]

_FLAG_COLOURS = {
    "MIN": QColor(255, 100, 100),   # red tint
    "MAX": QColor(100, 150, 255),   # blue tint
}


class ResultsPanel(QWidget):
    row_selected = pyqtSignal(int, int)   # cmg_id, col_id

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._status_label = QLabel("No results.")
        layout.addWidget(self._status_label)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.itemSelectionChanged.connect(self._on_selection)
        layout.addWidget(self._table)

    # ── public API ────────────────────────────────────────────────────────────

    def show_results(self, image_name: str, cuts: list[CMGCut]) -> None:
        self._table.setRowCount(0)
        total = sum(len(c.measurements) for c in cuts)
        self._status_label.setText(
            f"{image_name}  |  {len(cuts)} CMG cut(s)  |  {total} measurement(s)"
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
                    m.flag,
                    "OK",
                ]
                for col, val in enumerate(values):
                    item = QTableWidgetItem(val)
                    if m.flag in _FLAG_COLOURS:
                        item.setBackground(_FLAG_COLOURS[m.flag])
                    self._table.setItem(row, col, item)

    def show_fail(self, image_name: str, reason: str = "") -> None:
        self._table.setRowCount(0)
        self._status_label.setText(f"{image_name}  |  FAIL  {reason}")
        self._table.insertRow(0)
        item = QTableWidgetItem(image_name)
        self._table.setItem(0, 0, item)
        fail_item = QTableWidgetItem(f"FAIL: {reason}")
        fail_item.setBackground(QColor(255, 180, 180))
        self._table.setItem(0, 6, fail_item)

    def clear(self) -> None:
        self._table.setRowCount(0)
        self._status_label.setText("No results.")

    def update_summary(self, n_images: int, n_cmg: int, n_fail: int) -> None:
        self._status_label.setText(
            f"Batch complete — {n_images} images | {n_cmg} CMG measurements | {n_fail} failures"
        )

    # ── internal ──────────────────────────────────────────────────────────────

    def _on_selection(self) -> None:
        rows = self._table.selectedItems()
        if not rows:
            return
        row = self._table.currentRow()
        try:
            cmg_id = int(self._table.item(row, 1).text())
            col_id = int(self._table.item(row, 2).text())
            self.row_selected.emit(cmg_id, col_id)
        except (AttributeError, ValueError):
            pass
