"""KLARF Export Dialog — filter a KLARF to the top-N defects by CD value.

Layout: QSplitter(Horizontal)
  Left  (~300 px) — file picker, batch source, top-N, output path, status
  Right           — summary stat cards + preview table
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QSplitter,
    QLabel, QPushButton, QSpinBox, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox, QFrame, QMessageBox, QWidget, QSizePolicy,
    QComboBox, QProgressBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QColor, QImage, QPixmap


class NumericItem(QTableWidgetItem):
    """Table item that sorts numerically."""
    def __lt__(self, other: QTableWidgetItem) -> bool:
        try:
            return float(self.text()) < float(other.text())
        except (ValueError, TypeError):
            return super().__lt__(other)


# ── Background workers ────────────────────────────────────────────────────────

class _ExportWorker(QThread):
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def __init__(
        self,
        klarf_path: str,
        batch_run: Any,
        top_n: int,
        output_path: str,
        ascending: bool,
        dry_run: bool,
    ):
        super().__init__()
        self._klarf_path  = klarf_path
        self._batch_run   = batch_run
        self._top_n       = top_n
        self._output_path = output_path
        self._ascending   = ascending
        self._dry_run     = dry_run

    def run(self) -> None:
        try:
            from ..core.klarf_exporter import KlarfTopNExporter
            result = KlarfTopNExporter().export(
                klarf_path=self._klarf_path,
                batch_run=self._batch_run,
                top_n=self._top_n,
                output_path=self._output_path,
                ascending=self._ascending,
                dry_run=self._dry_run,
            )
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Dialog ────────────────────────────────────────────────────────────────────

class KlarfExportDialog(QDialog):
    """Dialog for exporting a KLARF filtered to top-N defects by CD value."""

    def __init__(
        self,
        batch_run: Any = None,
        run_store: Any = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Export KLARF — Top-N by CD")
        self.setMinimumSize(1000, 600)

        self._batch_run  = batch_run
        self._run_store  = run_store
        self._klarf_path = ""
        self._output_path = ""
        self._worker: _ExportWorker | None = None

        self._build_ui()
        if batch_run is not None:
            self._update_batch_label()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_batch_run(self, batch_run: Any) -> None:
        self._batch_run = batch_run
        self._update_batch_label()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── Left panel ────────────────────────────────────────────────────────
        left = QFrame()
        left.setObjectName("leftPanel")
        left.setFixedWidth(310)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(12, 12, 12, 12)
        lv.setSpacing(10)

        # KLARF 檔案列
        klarf_grp = QGroupBox("KLARF 檔案")
        kg = QVBoxLayout(klarf_grp)
        kg.setSpacing(4)
        self._klarf_label = QLabel("（未選擇）")
        self._klarf_label.setWordWrap(True)
        self._klarf_label.setStyleSheet("color:#9a8a7a; font-size:11px;")
        klarf_btn = QPushButton("瀏覽…")
        klarf_btn.setFixedHeight(28)
        klarf_btn.clicked.connect(self._browse_klarf)
        kg.addWidget(self._klarf_label)
        kg.addWidget(klarf_btn)
        lv.addWidget(klarf_grp)

        # Batch 結果列
        batch_grp = QGroupBox("Batch 結果")
        bg = QVBoxLayout(batch_grp)
        bg.setSpacing(4)
        batch_row = QHBoxLayout()
        self._batch_dot = QLabel("●")
        self._batch_dot.setStyleSheet("color:#cc7b6c; font-size:12px; background:transparent;")
        self._batch_info_label = QLabel("（未載入）")
        self._batch_info_label.setStyleSheet("color:#9a8a7a; font-size:11px;")
        self._batch_info_label.setWordWrap(True)
        batch_row.addWidget(self._batch_dot)
        batch_row.addWidget(self._batch_info_label, stretch=1)
        bg.addLayout(batch_row)
        hist_btn = QPushButton("從歷史載入…")
        hist_btn.setFixedHeight(28)
        hist_btn.clicked.connect(self._load_from_history)
        bg.addWidget(hist_btn)
        lv.addWidget(batch_grp)

        # Top N + 升/降冪
        topn_grp = QGroupBox("篩選條件")
        tg = QVBoxLayout(topn_grp)
        tg.setSpacing(4)

        topn_row = QHBoxLayout()
        topn_row.addWidget(QLabel("取前 N 顆:"))
        self._topn_spin = QSpinBox()
        self._topn_spin.setRange(1, 9999)
        self._topn_spin.setValue(100)
        self._topn_spin.setFixedWidth(80)
        topn_row.addWidget(self._topn_spin)
        topn_row.addStretch()
        tg.addLayout(topn_row)

        sort_row = QHBoxLayout()
        sort_row.addWidget(QLabel("排序方式:"))
        self._sort_combo = QComboBox()
        self._sort_combo.addItem("最小 CD 優先（升冪）", True)
        self._sort_combo.addItem("最大 CD 優先（降冪）", False)
        sort_row.addWidget(self._sort_combo, stretch=1)
        tg.addLayout(sort_row)

        hint_lbl = QLabel("取前 N 顆最小/最大 Y-CD 位置")
        hint_lbl.setStyleSheet("color:#9a8a7a; font-size:10px;")
        tg.addWidget(hint_lbl)
        lv.addWidget(topn_grp)

        # 輸出路徑
        out_grp = QGroupBox("輸出路徑")
        og = QVBoxLayout(out_grp)
        og.setSpacing(4)
        self._output_label = QLabel("（將隨 KLARF 選擇自動填入）")
        self._output_label.setWordWrap(True)
        self._output_label.setStyleSheet("color:#9a8a7a; font-size:11px;")
        out_btn = QPushButton("變更…")
        out_btn.setFixedHeight(28)
        out_btn.clicked.connect(self._browse_output)
        og.addWidget(self._output_label)
        og.addWidget(out_btn)
        lv.addWidget(out_grp)

        # 狀態標籤
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet("color:#a05020; font-size:11px;")
        lv.addWidget(self._status_label)

        # 進度條（處理中才顯示）
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)   # 不確定進度（脈動樣式）
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.hide()
        lv.addWidget(self._progress_bar)

        lv.addStretch()

        # 底部按鈕
        btn_row = QHBoxLayout()
        self._preview_btn = QPushButton("預覽")
        self._preview_btn.setFixedHeight(32)
        self._preview_btn.clicked.connect(self._run_preview)
        self._export_btn = QPushButton("執行並輸出 KLARF")
        self._export_btn.setObjectName("primaryBtn")
        self._export_btn.setFixedHeight(36)
        self._export_btn.clicked.connect(self._run_export)
        btn_row.addWidget(self._preview_btn)
        btn_row.addWidget(self._export_btn)
        lv.addLayout(btn_row)

        splitter.addWidget(left)

        # ── Right panel ───────────────────────────────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        # 上/下分割：上方為統計卡片+表格，下方為影像預覽
        right_split = QSplitter(Qt.Orientation.Vertical)
        right_split.setChildrenCollapsible(False)

        # ── 上方：stat cards + 表格 + 座標說明 ───────────────────────────────
        top_w = QWidget()
        top_v = QVBoxLayout(top_w)
        top_v.setContentsMargins(12, 12, 12, 4)
        top_v.setSpacing(8)

        # Stat cards
        cards_w = QWidget()
        cards_hl = QHBoxLayout(cards_w)
        cards_hl.setContentsMargins(0, 0, 0, 0)
        cards_hl.setSpacing(8)

        self._stat_selected  = self._make_stat_card("—", "已選取")
        self._stat_min_cd    = self._make_stat_card("—", "最小 Y-CD (nm)")
        self._stat_nth_cd    = self._make_stat_card("—", "第 N 筆 Y-CD (nm)")
        for card in (self._stat_selected, self._stat_min_cd, self._stat_nth_cd):
            cards_hl.addWidget(card[0])
        top_v.addWidget(cards_w)

        # Preview table
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "DefectID", "影像", "Y-CD (nm)",
            "XREL 原始", "XREL 新", "YREL 原始", "YREL 新",
        ])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSortIndicatorShown(True)
        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(self._table.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(self._table.EditTrigger.NoEditTriggers)
        self._table.currentCellChanged.connect(self._on_table_row_changed)
        top_v.addWidget(self._table, stretch=1)

        # Coordinate note
        coord_note = QLabel(
            "座標換算說明：Step1 pixel offset（以影像中心為基準）→ Step2 換算 nm → Step3 更新 KLARF 座標。"
            "影像 Y 軸向下，KLARF Y 軸向上，兩者方向相反，因此 YREL 使用<b>減號</b>（YREL_new = YREL_orig − dy_nm）。"
        )
        coord_note.setWordWrap(True)
        coord_note.setStyleSheet("color:#9a8a7a; font-size:10px;")
        coord_note.setTextFormat(Qt.TextFormat.RichText)
        top_v.addWidget(coord_note)

        right_split.addWidget(top_w)

        # ── 下方：影像預覽（含原始/新座標十字 overlay）────────────────────
        img_w = QWidget()
        img_wl = QVBoxLayout(img_w)
        img_wl.setContentsMargins(12, 4, 12, 12)
        img_wl.setSpacing(4)

        img_hdr = QWidget()
        img_hdr.setStyleSheet("background:transparent;")
        img_hdr_l = QHBoxLayout(img_hdr)
        img_hdr_l.setContentsMargins(0, 0, 0, 0)
        img_title = QLabel("影像預覽")
        img_title.setStyleSheet("color:#9a8a7a; font-size:10px; font-weight:600;")
        legend_orig = QLabel("● 原始座標")
        legend_orig.setStyleSheet("color:#5080d0; font-size:10px;")
        legend_new = QLabel("● 新座標")
        legend_new.setStyleSheet("color:#e08030; font-size:10px;")
        img_hdr_l.addWidget(img_title)
        img_hdr_l.addStretch()
        img_hdr_l.addWidget(legend_orig)
        img_hdr_l.addWidget(legend_new)
        img_wl.addWidget(img_hdr)

        self._image_label = QLabel("選擇列以查看影像")
        self._image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._image_label.setMinimumHeight(200)
        self._image_label.setStyleSheet(
            "background:#f5f1eb; border-radius:6px; color:#b0a090; font-size:11px;"
        )
        img_wl.addWidget(self._image_label, stretch=1)

        right_split.addWidget(img_w)
        right_split.setSizes([400, 260])

        rv.addWidget(right_split)

        splitter.addWidget(right)
        splitter.setSizes([310, 690])
        root.addWidget(splitter)

    def _make_stat_card(self, val: str, label: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setStyleSheet("background:#f5f1eb; border-radius:8px; border:none;")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 10, 12, 10)
        cl.setSpacing(2)
        val_lbl = QLabel(val)
        val_lbl.setStyleSheet("font-size:22px; font-weight:500; color:#3f3428; background:transparent;")
        desc_lbl = QLabel(label)
        desc_lbl.setStyleSheet("font-size:11px; color:#9a8a7a; background:transparent;")
        cl.addWidget(val_lbl)
        cl.addWidget(desc_lbl)
        return card, val_lbl

    # ── File pickers ──────────────────────────────────────────────────────────

    def _browse_klarf(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "選擇 KLARF 檔案", "",
            "KLARF Files (*.klarf *.000 *.001);;All Files (*)"
        )
        if not path:
            return
        self._klarf_path = path
        self._klarf_label.setText(Path(path).name)
        self._klarf_label.setStyleSheet("color:#3f3428; font-size:11px;")
        self._auto_output_path()

    def _browse_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "輸出 KLARF 路徑", self._output_path or "",
            "KLARF Files (*.klarf);;All Files (*)"
        )
        if path:
            self._output_path = path
            self._output_label.setText(Path(path).name)
            self._output_label.setStyleSheet("color:#3f3428; font-size:11px;")

    def _auto_output_path(self) -> None:
        if not self._klarf_path:
            return
        p = Path(self._klarf_path)
        n = self._topn_spin.value()
        out = p.parent / f"{p.stem}_topN{n}.klarf"
        self._output_path = str(out)
        self._output_label.setText(out.name)
        self._output_label.setStyleSheet("color:#3f3428; font-size:11px;")

    def _load_from_history(self) -> None:
        if not self._run_store:
            QMessageBox.information(self, "無歷史記錄", "未設定 run store。")
            return
        from .workspaces.batch_workspace import _HistoryDialog
        dlg = _HistoryDialog(self._run_store, self)
        dlg.run_selected.connect(self._on_history_selected)
        dlg.exec()

    def _on_history_selected(self, file_path: str) -> None:
        if not self._run_store:
            return
        try:
            result = self._run_store.load(file_path)
            self.set_batch_run(result)
        except Exception as exc:
            QMessageBox.critical(self, "載入失敗", str(exc))

    def _update_batch_label(self) -> None:
        if self._batch_run is None:
            self._batch_dot.setStyleSheet("color:#cc7b6c; font-size:12px; background:transparent;")
            self._batch_info_label.setText("（未載入）")
            return
        from ..core.models import MultiDatasetBatchRun
        if isinstance(self._batch_run, MultiDatasetBatchRun):
            n = self._batch_run.total_images
            d = len(self._batch_run.datasets)
            label = f"Multi-batch · {d} datasets · {n} 張影像"
        else:
            n = self._batch_run.total_images
            label = f"Batch · {n} 張影像"
        self._batch_dot.setStyleSheet("color:#3e7f5d; font-size:12px; background:transparent;")
        self._batch_info_label.setText(label)
        self._batch_info_label.setStyleSheet("color:#3f3428; font-size:11px;")

    # ── Preview / Export ──────────────────────────────────────────────────────

    def _validate_inputs(self) -> bool:
        if not self._klarf_path:
            QMessageBox.warning(self, "缺少輸入", "請選擇 KLARF 檔案。")
            return False
        if self._batch_run is None:
            QMessageBox.warning(self, "缺少 Batch 結果", "請載入 Batch 量測結果。")
            return False
        return True

    def _run_preview(self) -> None:
        if not self._validate_inputs():
            return
        self._preview_btn.setEnabled(False)
        self._export_btn.setEnabled(False)
        self._start_worker(dry_run=True)

    def _run_export(self) -> None:
        if not self._validate_inputs():
            return
        if not self._output_path:
            self._auto_output_path()
        self._preview_btn.setEnabled(False)
        self._export_btn.setEnabled(False)
        self._start_worker(dry_run=False)

    def _start_worker(self, dry_run: bool) -> None:
        if self._worker and self._worker.isRunning():
            return
        # 斷開舊 worker 訊號，避免重複觸發（Bug B1）
        if self._worker is not None:
            try:
                self._worker.finished.disconnect()
            except RuntimeError:
                pass
            try:
                self._worker.error.disconnect()
            except RuntimeError:
                pass
        ascending = bool(self._sort_combo.currentData())
        self._worker = _ExportWorker(
            klarf_path=self._klarf_path,
            batch_run=self._batch_run,
            top_n=self._topn_spin.value(),
            output_path=self._output_path or str(Path(self._klarf_path).parent / "output.klarf"),
            ascending=ascending,
            dry_run=dry_run,
        )
        self._worker.finished.connect(lambda r: self._on_done(r, dry_run))
        self._worker.error.connect(self._on_error)
        self._status_label.setText("處理中…")
        self._progress_bar.show()
        self._worker.start()

    @pyqtSlot(dict)
    def _on_done(self, result: dict, dry_run: bool) -> None:
        self._progress_bar.hide()
        self._preview_btn.setEnabled(True)
        self._export_btn.setEnabled(True)

        # Update stat cards
        self._stat_selected[1].setText(str(result.get("exported_count", 0)))
        mn = result.get("min_ycd_nm", 0.0)
        mx = result.get("max_ycd_nm", 0.0)
        self._stat_min_cd[1].setText(f"{mn:.2f}")
        # 升冪時 Nth 值是 max；降冪時 Nth 值是 min（Bug B5）
        ascending = bool(self._sort_combo.currentData())
        nth_val = mx if ascending else mn
        self._stat_nth_cd[1].setText(f"{nth_val:.2f}")

        # Unmatched warning
        uc = result.get("unmatched_count", 0)
        if uc:
            self._status_label.setText(f"⚠ {uc} 筆 defect 找不到對應影像")
        else:
            self._status_label.setText("")

        # Fill table
        self._fill_table(result.get("preview_rows", []), mn)

        if not dry_run:
            QMessageBox.information(
                self, "輸出完成",
                f"已輸出 {result['exported_count']} 筆 defect\n"
                f"最小 Y-CD：{mn:.2f} nm\n"
                f"第 N 筆 Y-CD：{mx:.2f} nm\n"
                f"輸出檔案：{result.get('output_path', '')}",
            )

    @pyqtSlot(str)
    def _on_error(self, msg: str) -> None:
        self._progress_bar.hide()
        self._status_label.setText("")
        self._preview_btn.setEnabled(True)
        self._export_btn.setEnabled(True)
        QMessageBox.critical(self, "錯誤", f"匯出失敗：\n{msg}")

    def _fill_table(self, rows: list[dict], global_min: float) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        amber = QColor("#FFF3CD")

        for row in rows:
            r = self._table.rowCount()
            self._table.insertRow(r)

            def _nitem(v: Any, fmt: str = "") -> QTableWidgetItem:
                txt = f"{v:{fmt}}" if fmt else str(v)
                item = NumericItem(txt)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                return item

            ycd = float(row.get("ycd_nm", 0.0))
            is_min = abs(ycd - global_min) < 1e-9

            id_item = QTableWidgetItem(str(row.get("defect_id", "")))
            id_item.setData(Qt.ItemDataRole.UserRole, row)   # 整列資料供影像預覽使用
            items = [
                id_item,
                QTableWidgetItem(str(row.get("image_stem", ""))),
                _nitem(ycd, ".2f"),
                _nitem(row.get("xrel_orig", 0), ".0f"),
                _nitem(row.get("xrel_new", 0), ".0f"),
                _nitem(row.get("yrel_orig", 0), ".0f"),
                _nitem(row.get("yrel_new", 0), ".0f"),
            ]
            for col, item in enumerate(items):
                if is_min:
                    item.setBackground(amber)
                self._table.setItem(r, col, item)

        self._table.setSortingEnabled(True)
        self._table.resizeColumnsToContents()

    # ── 影像預覽（功能二）────────────────────────────────────────────────────

    @pyqtSlot(int, int, int, int)
    def _on_table_row_changed(self, cur_row: int, _cur_col: int, _prev_row: int, _prev_col: int) -> None:
        """選取表格列時，載入對應影像並繪製原始/新座標十字 overlay。"""
        if cur_row < 0:
            return
        id_item = self._table.item(cur_row, 0)
        if id_item is None:
            return
        row = id_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(row, dict):
            return

        image_path  = row.get("image_path", "")
        nm_px       = float(row.get("nm_per_pixel", 0.0))
        xrel_orig   = float(row.get("xrel_orig", 0.0))
        yrel_orig   = float(row.get("yrel_orig", 0.0))
        xrel_new    = float(row.get("xrel_new",  0.0))
        yrel_new    = float(row.get("yrel_new",  0.0))

        if not image_path:
            self._image_label.setText("無影像路徑資訊")
            self._image_label.setPixmap(QPixmap())
            return

        try:
            import cv2
            import numpy as np
            img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
            if img is None:
                self._image_label.setText(f"無法載入影像：\n{image_path}")
                self._image_label.setPixmap(QPixmap())
                return

            # 步驟 1：將位元深度標準化為 uint8（SEM TIFF 常為 16-bit，
            # 否則 cvtColor 後 0-65535 範圍下，繪製顏色 (200,100,60) 在
            # QImage Format_RGB888 顯示為近黑，十字會看不見）
            if img.dtype != np.uint8:
                img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

            # 步驟 2：轉為 BGR 3 通道（灰階或 BGRA 統一處理）
            if img.ndim == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            elif img.shape[2] == 4:
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

            H, W = img.shape[:2]
            cx, cy = W / 2.0, H / 2.0

            # 若 nm/pixel 無法計算，顯示警告而非繪製假座標（M6）
            if nm_px <= 0:
                self._image_label.setText(
                    f"⚠ 此 defect 的 nm/pixel 無法計算（raw_px=0），\n"
                    f"無法顯示座標 overlay。"
                )
                return

            # KLARF 座標(nm) → 影像像素（Y 軸反向）
            def _klarf_to_px(xrel_nm: float, yrel_nm: float) -> tuple[int, int]:
                px = int(round(cx + xrel_nm / nm_px))
                py = int(round(cy - yrel_nm / nm_px))
                return px, py

            orig_pt = _klarf_to_px(xrel_orig, yrel_orig)
            new_pt  = _klarf_to_px(xrel_new,  yrel_new)

            # 步驟 3：尺寸依影像大小自適應（高解析度上 1px 線條會被縮放成不可見）
            arm       = max(40, min(W, H) // 40)   # 4096 → 102，1024 → 40
            thickness = max(2,  min(W, H) // 600)  # 4096 → 6，1024 → 2
            font      = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = max(0.6, min(W, H) / 1500)
            font_thick = max(1, thickness - 1)

            annotated = img.copy()
            _draw_crosshair(annotated, orig_pt, color=(255, 80, 60),
                            arm=arm, thickness=thickness)
            _draw_crosshair(annotated, new_pt,  color=(40, 160, 240),
                            arm=arm, thickness=thickness)

            # 文字說明（先畫黑色描邊提升對比，再畫彩色文字）
            for label, pt, color in (("Orig", orig_pt, (255, 80, 60)),
                                      ("New",  new_pt,  (40, 160, 240))):
                tx = pt[0] + arm // 2
                ty = pt[1] - arm // 2
                cv2.putText(annotated, label, (tx, ty), font, font_scale,
                            (0, 0, 0), font_thick + 2, cv2.LINE_AA)
                cv2.putText(annotated, label, (tx, ty), font, font_scale,
                            color, font_thick, cv2.LINE_AA)

            pix = _bgr_to_pixmap(annotated)
            # 縮放至 label 大小（保持比例）
            lw = max(self._image_label.width(),  100)
            lh = max(self._image_label.height(), 100)
            self._image_label.setPixmap(
                pix.scaled(lw, lh, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
            )
        except Exception as exc:
            self._image_label.setText(f"影像載入失敗：{exc}")


# ── Module-level helpers ──────────────────────────────────────────────────────

def _draw_crosshair(
    img,
    center: tuple[int, int],
    color: tuple[int, int, int],
    arm: int = 20,
    thickness: int = 1,
) -> None:
    """在 img 上就地繪製十字標記。"""
    try:
        import cv2
        x, y = center
        H, W = img.shape[:2]
        x1 = max(0, x - arm); x2 = min(W - 1, x + arm)
        y1 = max(0, y - arm); y2 = min(H - 1, y + arm)
        cv2.line(img, (x1, y), (x2, y), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x, y1), (x, y2), color, thickness, cv2.LINE_AA)
        # 小圓圈標記圓心
        cv2.circle(img, (x, y), 3, color, 1, cv2.LINE_AA)
    except Exception:
        pass


def _bgr_to_pixmap(img) -> "QPixmap":
    """Convert a BGR numpy array to QPixmap."""
    import numpy as np
    import cv2
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    qi = QImage(rgb.tobytes(), w, h, w * ch, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qi)
