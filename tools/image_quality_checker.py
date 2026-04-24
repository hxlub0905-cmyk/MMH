"""Standalone Image Quality Checker for SEM images.

Measures sharpness/blur metrics to identify low-quality images that would
produce unreliable CD measurements (blurry edges → short CD values).

Run:  python tools/image_quality_checker.py

Metrics
-------
* Laplacian variance  – Most reliable single metric; high = sharp.
* Tenengrad           – Mean squared Sobel gradient; high = sharp.
* FFT HF ratio        – Fraction of energy in outer 30 % of freq. domain;
                        high = sharp, low = over-smoothed / blurry.

Typical PASS thresholds for well-focused SEM images:
  Laplacian var  >  100   (adjust to your magnification / pixel size)
  Tenengrad      > 1000   (optional)
  FFT HF ratio   >  0.05  (optional)
"""
from __future__ import annotations

import csv
import os
import sys
from pathlib import Path

import cv2
import numpy as np

# ── PyQt6 imports ─────────────────────────────────────────────────────────────
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QDoubleSpinBox, QFileDialog, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSizePolicy, QSpinBox,
    QSplitter, QStatusBar, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget, QFrame, QComboBox, QLineEdit,
)

# ── Supported image extensions ─────────────────────────────────────────────────
_EXTS = {".tif", ".tiff", ".png", ".jpg", ".jpeg", ".bmp"}

# ── Quality computation ────────────────────────────────────────────────────────

def _load_gray(path: str) -> np.ndarray | None:
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.ndim == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if img.dtype != np.uint8:
        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    return img


def compute_quality(path: str) -> dict:
    """Return dict with laplacian_var, tenengrad, fft_hf_ratio (all float)."""
    img = _load_gray(path)
    if img is None:
        return {"error": "Cannot load image", "laplacian_var": 0.0,
                "tenengrad": 0.0, "fft_hf_ratio": 0.0}

    # 1. Laplacian variance
    lap = cv2.Laplacian(img.astype(np.float64), cv2.CV_64F)
    laplacian_var = float(lap.var())

    # 2. Tenengrad (Sobel-based)
    gx = cv2.Sobel(img.astype(np.float64), cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(img.astype(np.float64), cv2.CV_64F, 0, 1, ksize=3)
    tenengrad = float(np.mean(gx**2 + gy**2))

    # 3. FFT high-frequency ratio (outer 30 % of spectrum)
    h, w = img.shape
    fft = np.fft.fft2(img.astype(np.float64))
    fft_shift = np.fft.fftshift(fft)
    mag = np.abs(fft_shift)
    cy, cx = h // 2, w // 2
    # inner radius = 35 % of half-diagonal → keeps DC and low-freq
    r_inner = min(cy, cx) * 0.35
    ys, xs = np.ogrid[:h, :w]
    dist = np.sqrt((ys - cy) ** 2 + (xs - cx) ** 2)
    total_energy = float(mag.sum()) + 1e-9
    hf_energy    = float(mag[dist > r_inner].sum())
    fft_hf_ratio = hf_energy / total_energy

    return {
        "laplacian_var": laplacian_var,
        "tenengrad":     tenengrad,
        "fft_hf_ratio":  fft_hf_ratio,
        "error":         "",
    }


# ── Worker thread ──────────────────────────────────────────────────────────────

class _ScanWorker(QThread):
    progress   = pyqtSignal(int, int, str)          # done, total, path
    result_row = pyqtSignal(dict)                   # one result dict
    finished   = pyqtSignal()

    def __init__(self, paths: list[str]):
        super().__init__()
        self._paths = paths
        self._abort = False

    def abort(self) -> None:
        self._abort = True

    def run(self) -> None:
        total = len(self._paths)
        for i, p in enumerate(self._paths):
            if self._abort:
                break
            metrics = compute_quality(p)
            metrics["path"] = p
            metrics["name"] = Path(p).name
            self.result_row.emit(metrics)
            self.progress.emit(i + 1, total, Path(p).name)
        self.finished.emit()


# ── Main window ────────────────────────────────────────────────────────────────

class ImageQualityChecker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SEM Image Quality Checker")
        self.resize(1100, 700)

        self._folders: list[str] = []          # registered source folders
        self._all_paths: list[str] = []        # discovered image paths
        self._worker: _ScanWorker | None = None
        self._rows: list[dict] = []            # scan results

        self._build_ui()
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready — add folders and click Scan.")

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 10)

        # ── Top toolbar ────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()

        # Folder management
        folder_grp = QGroupBox("Source Folders")
        folder_grp.setFixedHeight(80)
        fv = QVBoxLayout(folder_grp)
        fv.setContentsMargins(6, 4, 6, 4)
        fh = QHBoxLayout()
        self._folder_label = QLabel("(none)")
        self._folder_label.setStyleSheet("color:#888; font-size:11px;")
        self._folder_label.setWordWrap(False)
        self._folder_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_add  = QPushButton("+ Add Folder")
        btn_add.setFixedWidth(110)
        btn_clear = QPushButton("Clear All")
        btn_clear.setFixedWidth(80)
        btn_add.clicked.connect(self._add_folder)
        btn_clear.clicked.connect(self._clear_folders)
        fh.addWidget(self._folder_label, 1)
        fh.addWidget(btn_add)
        fh.addWidget(btn_clear)
        fv.addLayout(fh)
        self._recursive_chk = QCheckBox("Recursive (include subfolders)")
        self._recursive_chk.setChecked(True)
        fv.addWidget(self._recursive_chk)
        toolbar.addWidget(folder_grp, 3)

        # Threshold settings
        thresh_grp = QGroupBox("Thresholds")
        thresh_grp.setFixedHeight(80)
        tg = QHBoxLayout(thresh_grp)
        tg.setSpacing(12)

        tg.addWidget(QLabel("Laplacian var ≥"))
        self._thr_lap = QDoubleSpinBox()
        self._thr_lap.setRange(0, 1e7)
        self._thr_lap.setDecimals(1)
        self._thr_lap.setValue(100.0)
        self._thr_lap.setToolTip("Images below this threshold are marked FAIL (blurry)")
        tg.addWidget(self._thr_lap)

        tg.addWidget(QLabel("  Tenengrad ≥"))
        self._thr_ten = QDoubleSpinBox()
        self._thr_ten.setRange(0, 1e9)
        self._thr_ten.setDecimals(0)
        self._thr_ten.setValue(0.0)
        self._thr_ten.setToolTip("0 = disabled. Tenengrad threshold for FAIL detection.")
        tg.addWidget(self._thr_ten)

        tg.addWidget(QLabel("  FFT HF ratio ≥"))
        self._thr_fft = QDoubleSpinBox()
        self._thr_fft.setRange(0, 1.0)
        self._thr_fft.setDecimals(3)
        self._thr_fft.setSingleStep(0.005)
        self._thr_fft.setValue(0.0)
        self._thr_fft.setToolTip("0 = disabled. FFT high-freq ratio threshold for FAIL detection.")
        tg.addWidget(self._thr_fft)

        self._apply_thr_btn = QPushButton("Re-apply")
        self._apply_thr_btn.setFixedWidth(80)
        self._apply_thr_btn.setToolTip("Re-evaluate PASS/FAIL with current thresholds")
        self._apply_thr_btn.clicked.connect(self._reapply_thresholds)
        tg.addWidget(self._apply_thr_btn)
        tg.addStretch()
        toolbar.addWidget(thresh_grp, 4)

        root.addLayout(toolbar)

        # ── Action row ─────────────────────────────────────────────────────────
        action_row = QHBoxLayout()
        self._scan_btn = QPushButton("▶  Scan")
        self._scan_btn.setFixedHeight(34)
        self._scan_btn.setObjectName("primaryBtn")
        self._scan_btn.clicked.connect(self._start_scan)

        self._abort_btn = QPushButton("Stop")
        self._abort_btn.setFixedHeight(34)
        self._abort_btn.setEnabled(False)
        self._abort_btn.clicked.connect(self._abort_scan)

        self._export_btn = QPushButton("Export CSV…")
        self._export_btn.setFixedHeight(34)
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._export_csv)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(18)
        self._progress.setVisible(False)

        action_row.addWidget(self._scan_btn)
        action_row.addWidget(self._abort_btn)
        action_row.addWidget(self._progress, 1)
        action_row.addStretch()
        action_row.addWidget(self._export_btn)
        root.addLayout(action_row)

        # ── Summary bar ────────────────────────────────────────────────────────
        self._summary_label = QLabel("")
        self._summary_label.setStyleSheet("font-size:12px; color:#555; padding:2px 0;")
        root.addWidget(self._summary_label)

        # ── Results table ──────────────────────────────────────────────────────
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "Status", "Filename", "Laplacian Var", "Tenengrad",
            "FFT HF Ratio", "Folder", "Error",
        ])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setColumnWidth(0, 70)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSortingEnabled(True)
        root.addWidget(self._table, 1)

        # ── Style ──────────────────────────────────────────────────────────────
        self.setStyleSheet("""
            QMainWindow { background: #f5f1eb; }
            QGroupBox { font-size: 12px; font-weight: 600; border: 1px solid #d8cbb8;
                        border-radius: 6px; margin-top: 6px; background: #faf8f4; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; top: -1px;
                               color: #6a5a4a; padding: 0 4px; }
            QPushButton { background: #e8ddd0; border: 1px solid #c8b8a8; border-radius: 5px;
                          padding: 4px 12px; font-size: 12px; }
            QPushButton:hover { background: #d8cdc0; }
            QPushButton#primaryBtn { background: #4a90d9; color: white; border: none; font-weight: 600; }
            QPushButton#primaryBtn:hover { background: #3a80c9; }
            QPushButton:disabled { color: #aaa; background: #eee; border-color: #ddd; }
            QTableWidget { border: 1px solid #d0c0b0; gridline-color: #e8ddd0;
                           font-size: 12px; background: white; }
            QTableWidget::item:alternate { background: #f9f6f0; }
            QHeaderView::section { background: #ede6da; padding: 4px 8px;
                                    border: none; border-bottom: 1px solid #c8b8a8;
                                    font-size: 11px; font-weight: 600; color: #5a4a3a; }
        """)

    # ── Folder management ─────────────────────────────────────────────────────

    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select folder with SEM images")
        if folder and folder not in self._folders:
            self._folders.append(folder)
            self._folder_label.setText("  |  ".join(Path(f).name for f in self._folders))

    def _clear_folders(self) -> None:
        self._folders.clear()
        self._folder_label.setText("(none)")

    # ── Scanning ──────────────────────────────────────────────────────────────

    def _collect_paths(self) -> list[str]:
        paths: list[str] = []
        recursive = self._recursive_chk.isChecked()
        for folder in self._folders:
            p = Path(folder)
            pattern = "**/*" if recursive else "*"
            for f in p.glob(pattern):
                if f.is_file() and f.suffix.lower() in _EXTS:
                    paths.append(str(f))
        return sorted(paths)

    def _start_scan(self) -> None:
        if not self._folders:
            QMessageBox.information(self, "No folders", "Add at least one source folder first.")
            return
        self._all_paths = self._collect_paths()
        if not self._all_paths:
            QMessageBox.information(self, "No images found",
                                    "No supported images found in the selected folder(s).")
            return

        self._rows.clear()
        self._table.setRowCount(0)
        self._table.setSortingEnabled(False)
        self._progress.setMaximum(len(self._all_paths))
        self._progress.setValue(0)
        self._progress.setVisible(True)
        self._scan_btn.setEnabled(False)
        self._abort_btn.setEnabled(True)
        self._export_btn.setEnabled(False)
        self._summary_label.setText(f"Scanning {len(self._all_paths)} images…")

        self._worker = _ScanWorker(self._all_paths)
        self._worker.progress.connect(self._on_progress)
        self._worker.result_row.connect(self._on_result_row)
        self._worker.finished.connect(self._on_scan_done)
        self._worker.start()

    def _abort_scan(self) -> None:
        if self._worker:
            self._worker.abort()
        self._abort_btn.setEnabled(False)

    # ── Result handling ───────────────────────────────────────────────────────

    def _is_pass(self, row: dict) -> bool:
        if row.get("error"):
            return False
        if row["laplacian_var"] < self._thr_lap.value():
            return False
        if self._thr_ten.value() > 0 and row["tenengrad"] < self._thr_ten.value():
            return False
        if self._thr_fft.value() > 0 and row["fft_hf_ratio"] < self._thr_fft.value():
            return False
        return True

    def _on_result_row(self, metrics: dict) -> None:
        self._rows.append(metrics)
        self._add_table_row(metrics)

    def _add_table_row(self, metrics: dict) -> None:
        passed = self._is_pass(metrics)
        row_idx = self._table.rowCount()
        self._table.insertRow(row_idx)

        status_item = QTableWidgetItem("PASS" if passed else "FAIL")
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        status_item.setForeground(QColor("#2a7a2a") if passed else QColor("#cc0000"))
        font = QFont(); font.setBold(True); status_item.setFont(font)

        name_item  = QTableWidgetItem(metrics.get("name", ""))
        lap_item   = _num_item(metrics["laplacian_var"], 2)
        ten_item   = _num_item(metrics["tenengrad"], 1)
        fft_item   = _num_item(metrics["fft_hf_ratio"], 4)
        folder_item = QTableWidgetItem(str(Path(metrics["path"]).parent))
        err_item   = QTableWidgetItem(metrics.get("error", ""))

        for col, item in enumerate([status_item, name_item, lap_item, ten_item,
                                     fft_item, folder_item, err_item]):
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if not passed:
                item.setBackground(QColor("#fff0f0"))
            self._table.setItem(row_idx, col, item)

    def _on_progress(self, done: int, total: int, name: str) -> None:
        self._progress.setValue(done)
        self._status.showMessage(f"[{done}/{total}]  {name}")

    def _on_scan_done(self) -> None:
        self._table.setSortingEnabled(True)
        self._progress.setVisible(False)
        self._scan_btn.setEnabled(True)
        self._abort_btn.setEnabled(False)
        self._export_btn.setEnabled(bool(self._rows))
        self._update_summary()
        self._status.showMessage(f"Scan complete — {len(self._rows)} images processed.")

    def _update_summary(self) -> None:
        total = len(self._rows)
        passes = sum(1 for r in self._rows if self._is_pass(r))
        fails  = total - passes
        pct    = 100 * fails / total if total else 0.0
        self._summary_label.setText(
            f"Total: <b>{total}</b>  &nbsp;|&nbsp;  "
            f"<span style='color:#2a7a2a'><b>PASS: {passes}</b></span>  &nbsp;|&nbsp;  "
            f"<span style='color:#cc0000'><b>FAIL: {fails}</b></span>  ({pct:.1f}% rejected)"
        )
        self._summary_label.setTextFormat(Qt.TextFormat.RichText)

    def _reapply_thresholds(self) -> None:
        """Re-evaluate PASS/FAIL for all loaded rows without re-scanning."""
        if not self._rows:
            return
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        for row in self._rows:
            self._add_table_row(row)
        self._table.setSortingEnabled(True)
        self._update_summary()

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_csv(self) -> None:
        if not self._rows:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", "image_quality_results.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["status", "name", "path", "laplacian_var", "tenengrad",
                             "fft_hf_ratio", "error"],
            )
            writer.writeheader()
            for row in self._rows:
                writer.writerow({
                    "status":        "PASS" if self._is_pass(row) else "FAIL",
                    "name":          row.get("name", ""),
                    "path":          row.get("path", ""),
                    "laplacian_var": f"{row['laplacian_var']:.4f}",
                    "tenengrad":     f"{row['tenengrad']:.2f}",
                    "fft_hf_ratio":  f"{row['fft_hf_ratio']:.6f}",
                    "error":         row.get("error", ""),
                })
        self._status.showMessage(f"Exported → {Path(path).name}")
        QMessageBox.information(self, "Done", f"CSV saved:\n{path}")


# ── helpers ───────────────────────────────────────────────────────────────────

class _NumericItem(QTableWidgetItem):
    """QTableWidgetItem that sorts numerically."""
    def __init__(self, value: float, decimals: int):
        super().__init__(f"{value:.{decimals}f}")
        self.setData(Qt.ItemDataRole.UserRole, value)
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setFlags(self.flags() & ~Qt.ItemFlag.ItemIsEditable)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        try:
            return (self.data(Qt.ItemDataRole.UserRole) <
                    other.data(Qt.ItemDataRole.UserRole))
        except Exception:
            return super().__lt__(other)


def _num_item(value: float, decimals: int) -> _NumericItem:
    return _NumericItem(value, decimals)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("SEM Image Quality Checker")
    win = ImageQualityChecker()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
