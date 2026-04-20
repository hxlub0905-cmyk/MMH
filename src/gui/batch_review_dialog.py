"""Rich batch review viewer with export/report actions."""

from __future__ import annotations
from pathlib import Path
import cv2

from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QTextEdit, QSplitter, QTableWidget, QTableWidgetItem,
    QCheckBox, QWidget,
)
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtCore import Qt, pyqtSignal


def _img_to_pixmap(img) -> QPixmap:
    if img.ndim == 2:
        h, w = img.shape
        q = QImage(img.data, w, h, w, QImage.Format.Format_Grayscale8)
    else:
        h, w, _ = img.shape
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        q = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(q.copy())


class BatchReviewDialog(QDialog):
    export_requested = pyqtSignal()
    report_requested = pyqtSignal()
    export_annotated_requested = pyqtSignal(dict)

    def __init__(self, results: list[dict], annotated_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Review Viewer")
        self.resize(1320, 820)
        self._results = results
        self._annotated_dir = annotated_dir

        root = QVBoxLayout(self)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        self._list = QListWidget()
        self._list.setMinimumWidth(260)
        splitter.addWidget(self._list)

        right = QWidget()
        right_l = QVBoxLayout(right)

        self._img = QLabel("No image")
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setMinimumHeight(450)
        right_l.addWidget(self._img, 3)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Structure", "Feature ID", "CD (px)", "CD (nm)", "Flag"])
        right_l.addWidget(self._table, 2)

        self._meta = QTextEdit()
        self._meta.setReadOnly(True)
        self._meta.setMaximumHeight(120)
        right_l.addWidget(self._meta, 1)

        splitter.addWidget(right)
        splitter.setSizes([280, 1040])

        opt_row = QHBoxLayout()
        opt_row.addWidget(QLabel("Overlay:"))
        self._chk_lines = QCheckBox("Lines"); self._chk_lines.setChecked(True)
        self._chk_vals = QCheckBox("Values"); self._chk_vals.setChecked(True)
        self._chk_boxes = QCheckBox("Boxes"); self._chk_boxes.setChecked(False)
        self._chk_legend = QCheckBox("Legend"); self._chk_legend.setChecked(True)
        for c in (self._chk_lines, self._chk_vals, self._chk_boxes, self._chk_legend):
            opt_row.addWidget(c)
        opt_row.addStretch()
        root.addLayout(opt_row)

        row = QHBoxLayout()
        self._btn_export_ann = QPushButton("Export Batch Output")
        self._btn_report = QPushButton("One-click Report")
        self._btn_export = QPushButton("Export Package")
        self._btn_close = QPushButton("Close")
        self._btn_export_ann.clicked.connect(self._emit_export_annotated)
        self._btn_report.clicked.connect(self.report_requested)
        self._btn_export.clicked.connect(self.export_requested)
        self._btn_close.clicked.connect(self.accept)
        row.addStretch()
        row.addWidget(self._btn_export_ann)
        row.addWidget(self._btn_report)
        row.addWidget(self._btn_export)
        row.addWidget(self._btn_close)
        root.addLayout(row)

        for r in self._results:
            p = Path(r.get("path", ""))
            item = QListWidgetItem(p.name or str(p))
            item.setData(Qt.ItemDataRole.UserRole, r)
            self._list.addItem(item)
        self._list.currentItemChanged.connect(self._show_item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def _emit_export_annotated(self) -> None:
        self.export_annotated_requested.emit({
            "show_lines": self._chk_lines.isChecked(),
            "show_labels": self._chk_vals.isChecked(),
            "show_boxes": self._chk_boxes.isChecked(),
            "show_legend": self._chk_legend.isChecked(),
        })

    def _show_item(self, cur: QListWidgetItem | None, _prev: QListWidgetItem | None) -> None:
        if cur is None:
            return
        r = cur.data(Qt.ItemDataRole.UserRole)
        p = Path(r.get("path", ""))
        ann = None
        if self._annotated_dir is not None:
            cand = self._annotated_dir / f"{p.stem}_annotated.png"
            if cand.exists():
                ann = cv2.imread(str(cand), cv2.IMREAD_COLOR)
        if ann is None and p.exists():
            ann = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)

        if ann is None:
            self._img.setText("Image not available")
            self._img.setPixmap(QPixmap())
        else:
            pix = _img_to_pixmap(ann)
            self._img.setPixmap(pix.scaled(self._img.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation))

        self._table.setRowCount(0)
        if r.get("status") != "OK":
            self._meta.setPlainText(f"Status: FAIL\nError: {r.get('error', '')}")
            return

        n_meas = 0
        for cut in r.get("cuts", []):
            for m in cut.get("measurements", []):
                row = self._table.rowCount()
                self._table.insertRow(row)
                vals = [
                    str(cut.get("cmg_id")),
                    str(m.get("col_id")),
                    f"{m.get('y_cd_px', 0):.3f}",
                    f"{m.get('y_cd_nm', 0):.3f}",
                    m.get("flag") or "",
                ]
                for col, v in enumerate(vals):
                    item = QTableWidgetItem(v)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self._table.setItem(row, col, item)
                n_meas += 1
        self._meta.setPlainText(
            f"Status: OK\nFile: {p.name}\nMeasurements: {n_meas}\nCMG cuts: {len(r.get('cuts', []))}"
        )
