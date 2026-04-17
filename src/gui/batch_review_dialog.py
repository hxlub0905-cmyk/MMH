"""Batch review viewer: browse each image, see measurements, export package."""

from __future__ import annotations
from pathlib import Path
import cv2

from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QPushButton, QTextEdit,
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

    def __init__(self, results: list[dict], annotated_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Batch Review Viewer")
        self.resize(1200, 760)
        self._results = results
        self._annotated_dir = annotated_dir

        root = QHBoxLayout(self)

        self._list = QListWidget()
        self._list.setMinimumWidth(260)
        root.addWidget(self._list, 0)

        right = QVBoxLayout()
        root.addLayout(right, 1)

        self._img = QLabel("No image")
        self._img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img.setMinimumHeight(420)
        right.addWidget(self._img, 3)

        self._meta = QTextEdit()
        self._meta.setReadOnly(True)
        self._meta.setMinimumHeight(180)
        right.addWidget(self._meta, 1)

        row = QHBoxLayout()
        self._btn_export = QPushButton("Export Package")
        self._btn_close = QPushButton("Close")
        self._btn_export.clicked.connect(self.export_requested)
        self._btn_close.clicked.connect(self.accept)
        row.addStretch()
        row.addWidget(self._btn_export)
        row.addWidget(self._btn_close)
        right.addLayout(row)

        for r in self._results:
            p = Path(r.get("path", ""))
            item = QListWidgetItem(p.name or str(p))
            item.setData(Qt.ItemDataRole.UserRole, r)
            self._list.addItem(item)
        self._list.currentItemChanged.connect(self._show_item)
        if self._list.count():
            self._list.setCurrentRow(0)

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
        else:
            pix = _img_to_pixmap(ann)
            self._img.setPixmap(pix.scaled(
                self._img.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))

        if r.get("status") != "OK":
            self._meta.setPlainText(f"Status: FAIL\nError: {r.get('error', '')}")
            return
        lines = [f"Status: OK", f"Path: {p.name}", ""]
        for cut in r.get("cuts", []):
            lines.append(f"CMG {cut.get('cmg_id')}:")
            for m in cut.get("measurements", []):
                lines.append(
                    f"  Col {m.get('col_id')}  {m.get('y_cd_nm', 0):.3f} nm  "
                    f"({m.get('y_cd_px', 0):.3f} px)  {m.get('flag') or ''}".rstrip()
                )
        self._meta.setPlainText("\n".join(lines))
