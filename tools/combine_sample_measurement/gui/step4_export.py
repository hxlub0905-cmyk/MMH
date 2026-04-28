"""Step 4 — Export Panel.

Shows coordinate map table + image preview (ORIG/NEW crosshairs with CD label).
Exports KLARF, Excel, and Overlay images via background worker.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pandas as pd
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QGroupBox,
    QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QPushButton, QSizePolicy, QSplitter,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QHeaderView, QLineEdit,
)

_HERE = Path(__file__).parent
_PROJECT_ROOT = _HERE.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.combine_sample_measurement.core.exporter import (
    export_klarf, export_excel, export_overlay,
    draw_overlay_on_image, bgr_to_pixmap, _is_valid,
)


# ── Background worker ─────────────────────────────────────────────────────────

class _ExportWorker(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def __init__(
        self,
        df: pd.DataFrame,
        template_parsed: dict[str, Any],
        ds_klafs: dict[str, dict[str, Any]],
        out_dir: Path,
        prefix: str,
        do_klarf: bool,
        do_excel: bool,
        do_overlay: bool,
    ):
        super().__init__()
        self._df             = df
        self._template       = template_parsed
        self._ds_klafs       = ds_klafs
        self._out_dir        = out_dir
        self._prefix         = prefix
        self._do_klarf       = do_klarf
        self._do_excel       = do_excel
        self._do_overlay     = do_overlay

    def run(self) -> None:
        try:
            results: dict = {}
            step = 0
            total = sum([self._do_klarf, self._do_excel, self._do_overlay])

            if self._do_klarf:
                self.progress.emit(step, total, "輸出 KLARF…")
                out = self._out_dir / f"{self._prefix}.klarf"
                n   = export_klarf(self._df, self._template, self._ds_klafs, out)
                results["klarf_path"]  = str(out)
                results["klarf_count"] = n
                step += 1

            if self._do_excel:
                self.progress.emit(step, total, "輸出 Excel…")
                out = self._out_dir / f"{self._prefix}.xlsx"
                export_excel(self._df, out)
                results["excel_path"] = str(out)
                step += 1

            if self._do_overlay:
                self.progress.emit(step, total, "輸出 Overlay 影像…")
                out_dir = self._out_dir / "overlay"

                def _cb(i, t):
                    self.progress.emit(step, total, f"Overlay {i}/{t}…")

                saved = export_overlay(self._df, out_dir, _cb)
                results["overlay_dir"]   = str(out_dir)
                results["overlay_count"] = len(saved)
                step += 1

            self.progress.emit(total, total, "完成")
            self.finished.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Step 4 Widget ─────────────────────────────────────────────────────────────

class Step4ExportWidget(QWidget):
    """Export panel: coordinate preview + KLARF/Excel/Overlay output."""

    _COL_NEW_DID  = 0
    _COL_DS       = 1
    _COL_FILE     = 2
    _COL_CD       = 3
    _COL_XREL_OLD = 4
    _COL_XREL_NEW = 5
    _COL_YREL_OLD = 6
    _COL_YREL_NEW = 7

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._df: pd.DataFrame | None = None
        self._template_parsed: dict[str, Any] = {}
        self._ds_klafs: dict[str, dict[str, Any]] = {}
        self._worker: _ExportWorker | None = None
        self._build_ui()

    def set_data(
        self,
        df: pd.DataFrame,
        template_parsed: dict[str, Any],
        ds_klafs: dict[str, dict[str, Any]],
    ) -> None:
        self._df             = df.copy()
        self._template_parsed = template_parsed
        self._ds_klafs       = ds_klafs
        self._fill_table()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── Left: controls ────────────────────────────────────────────────
        left = QWidget()
        left.setFixedWidth(280)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(12, 12, 12, 12)
        lv.setSpacing(10)

        out_grp = QGroupBox("輸出設定")
        og = QVBoxLayout(out_grp)
        og.setSpacing(6)

        og.addWidget(QLabel("輸出資料夾："))
        dir_row = QHBoxLayout()
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("選擇資料夾…")
        dir_btn = QPushButton("瀏覽")
        dir_btn.setFixedWidth(56)
        dir_btn.clicked.connect(self._browse_dir)
        dir_row.addWidget(self._dir_edit)
        dir_row.addWidget(dir_btn)
        og.addLayout(dir_row)

        og.addWidget(QLabel("檔名前綴："))
        self._prefix_edit = QLineEdit("combined_sample")
        og.addWidget(self._prefix_edit)
        lv.addWidget(out_grp)

        fmt_grp = QGroupBox("輸出格式")
        fg = QVBoxLayout(fmt_grp)
        fg.setSpacing(4)
        self._chk_klarf   = QCheckBox("KLARF")
        self._chk_excel   = QCheckBox("Excel（含全部欄位）")
        self._chk_overlay = QCheckBox("Overlay 影像（每張 SEM 圖）")
        self._chk_klarf.setChecked(True)
        self._chk_excel.setChecked(True)
        self._chk_overlay.setChecked(True)
        fg.addWidget(self._chk_klarf)
        fg.addWidget(self._chk_excel)
        fg.addWidget(self._chk_overlay)
        lv.addWidget(fmt_grp)

        # Note
        note = QLabel(
            "座標換算：\n"
            "new_XREL = orig_XREL + Δx_nm\n"
            "new_YREL = orig_YREL − Δy_nm\n"
            "（影像 Y↓ vs KLARF Y↑，故 Y 用減號）"
        )
        note.setWordWrap(True)
        note.setStyleSheet("color:#9a8a7a; font-size:10px;")
        lv.addWidget(note)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet("color:#a05020; font-size:11px;")
        lv.addWidget(self._status_lbl)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.hide()
        lv.addWidget(self._progress)

        lv.addStretch()

        self._exec_btn = QPushButton("執行輸出")
        self._exec_btn.setObjectName("primaryBtn")
        self._exec_btn.setFixedHeight(38)
        self._exec_btn.clicked.connect(self._run_export)
        lv.addWidget(self._exec_btn)

        splitter.addWidget(left)

        # ── Right: coordinate table + image preview ────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        right_split = QSplitter(Qt.Orientation.Vertical)
        right_split.setChildrenCollapsible(False)

        # Coordinate map table
        tbl_w = QWidget()
        tv = QVBoxLayout(tbl_w)
        tv.setContentsMargins(8, 8, 8, 4)

        tv.addWidget(QLabel("新舊座標對應表（點選列查看影像預覽）："))
        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels([
            "新 DID", "Dataset", "圖片檔名", "CD (nm)",
            "XREL 原始", "XREL 新", "YREL 原始", "YREL 新",
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setSortingEnabled(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.currentCellChanged.connect(self._on_row_changed)
        tv.addWidget(self._table)
        right_split.addWidget(tbl_w)

        # Image preview
        img_w = QWidget()
        iw = QVBoxLayout(img_w)
        iw.setContentsMargins(8, 4, 8, 8)

        img_hdr = QHBoxLayout()
        img_title = QLabel("影像預覽")
        img_title.setStyleSheet("color:#9a8a7a; font-size:10px; font-weight:600;")
        legend_orig = QLabel("● 原始座標 (ORIG)")
        legend_orig.setStyleSheet("color:#3c50ff; font-size:10px;")
        legend_new = QLabel("● 新座標 (NEW) + CD 值")
        legend_new.setStyleSheet("color:#e07820; font-size:10px;")
        img_hdr.addWidget(img_title)
        img_hdr.addStretch()
        img_hdr.addWidget(legend_orig)
        img_hdr.addWidget(legend_new)
        iw.addLayout(img_hdr)

        self._img_lbl = QLabel("點選列以查看影像")
        self._img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._img_lbl.setMinimumHeight(180)
        self._img_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._img_lbl.setStyleSheet(
            "background:#f5f1eb; border-radius:6px; color:#b0a090; font-size:11px;"
        )
        iw.addWidget(self._img_lbl, stretch=1)

        self._coord_status = QLabel("")
        self._coord_status.setStyleSheet("color:#9a8a7a; font-size:10px;")
        iw.addWidget(self._coord_status)

        right_split.addWidget(img_w)
        right_split.setSizes([400, 260])
        rv.addWidget(right_split)

        splitter.addWidget(right)
        splitter.setSizes([280, 720])
        root.addWidget(splitter)

    def _browse_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "選擇輸出資料夾")
        if d:
            self._dir_edit.setText(d)

    # ── Fill table ────────────────────────────────────────────────────────────

    def _fill_table(self) -> None:
        if self._df is None:
            return
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)

        amber = QColor("#FFF3CD")

        for _, row in self._df.iterrows():
            r = self._table.rowCount()
            self._table.insertRow(r)

            new_did  = row.get("new_did", "")
            cd       = float(row.get("cd_nm", 0) or 0)
            is_first = (int(new_did) == 1) if str(new_did).isdigit() else False

            vals = [
                str(new_did),
                str(row.get("source_dataset", "")),
                str(row.get("image_file", "")),
                f"{cd:.2f}",
                _fmt(row.get("orig_xrel")),
                _fmt(row.get("new_xrel")),
                _fmt(row.get("orig_yrel")),
                _fmt(row.get("new_yrel")),
            ]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row.to_dict())
                if is_first:
                    item.setBackground(amber)
                self._table.setItem(r, c, item)

        self._table.setSortingEnabled(True)
        self._table.resizeColumnsToContents()

    # ── Image preview ─────────────────────────────────────────────────────────

    @pyqtSlot(int, int, int, int)
    def _on_row_changed(self, cur_row: int, *_) -> None:
        if cur_row < 0:
            return
        id_item = self._table.item(cur_row, 0)
        if id_item is None:
            return
        row = id_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(row, dict):
            return

        image_path = str(row.get("image_path", ""))
        nm_px      = float(row.get("nm_per_pixel", 0) or 0)
        orig_xrel  = row.get("orig_xrel")
        orig_yrel  = row.get("orig_yrel")
        new_xrel   = row.get("new_xrel")
        new_yrel   = row.get("new_yrel")
        cd_nm      = float(row.get("cd_nm", 0) or 0)
        new_did    = row.get("new_did", "")

        if not image_path:
            self._img_lbl.setText("無影像路徑")
            return

        if nm_px <= 0 or not _is_valid(orig_xrel) or not _is_valid(new_xrel):
            self._img_lbl.setText("⚠ 無法計算座標 overlay\n(nm/px 或原始座標缺失)")
            return

        try:
            img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
            if img is None:
                self._img_lbl.setText(f"無法載入：{image_path}")
                return

            annotated = draw_overlay_on_image(
                img, nm_px,
                float(orig_xrel), float(orig_yrel),
                float(new_xrel),  float(new_yrel),
                cd_nm=cd_nm, new_did=new_did,
            )

            dx_px = (float(new_xrel) - float(orig_xrel)) / nm_px
            dy_px = (float(orig_yrel) - float(new_yrel)) / nm_px
            dist  = (dx_px ** 2 + dy_px ** 2) ** 0.5 * nm_px
            self._coord_status.setText(
                f"補正：Δ=({dx_px:+.1f}, {dy_px:+.1f}) px ≈ {dist:.0f} nm"
            )

            pix = bgr_to_pixmap(annotated)
            lw  = max(self._img_lbl.width(),  100)
            lh  = max(self._img_lbl.height(), 100)
            self._img_lbl.setPixmap(
                pix.scaled(lw, lh,
                           Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            )
        except Exception as exc:
            self._img_lbl.setText(f"影像載入失敗：{exc}")

    # ── Export ────────────────────────────────────────────────────────────────

    def _run_export(self) -> None:
        if self._df is None or self._df.empty:
            QMessageBox.warning(self, "無資料", "請先完成 Step 3 採樣。")
            return

        out_dir = self._dir_edit.text().strip()
        if not out_dir:
            QMessageBox.warning(self, "未設定輸出資料夾", "請選擇輸出資料夾。")
            return

        do_klarf   = self._chk_klarf.isChecked()
        do_excel   = self._chk_excel.isChecked()
        do_overlay = self._chk_overlay.isChecked()

        if not any([do_klarf, do_excel, do_overlay]):
            QMessageBox.warning(self, "無輸出選項", "請至少勾選一種輸出格式。")
            return

        if not self._template_parsed:
            QMessageBox.warning(self, "缺少模板", "KLARF 模板未載入，請重新執行 Step 1。")
            return

        if self._worker and self._worker.isRunning():
            return

        prefix = self._prefix_edit.text().strip() or "combined_sample"
        total  = sum([do_klarf, do_excel, do_overlay])

        self._exec_btn.setEnabled(False)
        self._progress.setRange(0, total)
        self._progress.setValue(0)
        self._progress.show()
        self._status_lbl.setText("輸出中…")

        self._worker = _ExportWorker(
            df=self._df,
            template_parsed=self._template_parsed,
            ds_klafs=self._ds_klafs,
            out_dir=Path(out_dir),
            prefix=prefix,
            do_klarf=do_klarf,
            do_excel=do_excel,
            do_overlay=do_overlay,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    @pyqtSlot(int, int, str)
    def _on_progress(self, cur: int, total: int, msg: str) -> None:
        self._progress.setMaximum(max(total, 1))
        self._progress.setValue(cur)
        self._status_lbl.setText(msg)

    @pyqtSlot(dict)
    def _on_done(self, results: dict) -> None:
        self._progress.hide()
        self._exec_btn.setEnabled(True)

        lines = ["輸出完成！\n"]
        if "klarf_path" in results:
            lines.append(f"KLARF：{results['klarf_count']} 筆\n→ {results['klarf_path']}")
        if "excel_path" in results:
            lines.append(f"Excel：{results['excel_path']}")
        if "overlay_dir" in results:
            lines.append(
                f"Overlay：{results['overlay_count']} 張\n→ {results['overlay_dir']}"
            )
        self._status_lbl.setText("輸出完成")
        QMessageBox.information(self, "輸出完成", "\n".join(lines))

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        self._progress.hide()
        self._exec_btn.setEnabled(True)
        self._status_lbl.setText("")
        QMessageBox.critical(self, "輸出失敗", msg)


def _fmt(v) -> str:
    try:
        if v is None or pd.isna(float(v)):
            return "—"
        return f"{float(v):.0f}"
    except (TypeError, ValueError):
        return str(v) if v is not None else "—"
