"""Main window for Combine Sample Measurement Tool.

Four-step workflow via QTabWidget:
  Step 1 — Load datasets (Excel + image folder + KLARF per dataset)
  Step 2 — Quality filter (Laplacian re-check, auto/manual remove)
  Step 3 — Sampling (Top-N by Min/Max CD, new DID assignment)
  Step 4 — Export (KLARF + Excel + Overlay with old/new coordinate preview)

State held by main window and passed forward on each step transition.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import (
    QLabel, QMainWindow, QMessageBox,
    QTabWidget, QVBoxLayout, QWidget, QStatusBar,
)

_HERE = Path(__file__).parent
_PROJECT_ROOT = _HERE.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tools.combine_sample_measurement.gui.step1_load   import Step1LoadWidget
from tools.combine_sample_measurement.gui.step2_filter import Step2FilterWidget
from tools.combine_sample_measurement.gui.step3_sample import Step3SampleWidget
from tools.combine_sample_measurement.gui.step4_export import Step4ExportWidget


_STYLESHEET = """
QMainWindow, QDialog {
    background: #faf6f1;
}
QTabWidget::pane {
    border: none;
    background: #faf6f1;
}
QTabBar::tab {
    background: #ede8e2;
    color: #7a6a5a;
    padding: 8px 22px;
    border-radius: 0px;
    font-size: 12px;
}
QTabBar::tab:selected {
    background: #faf6f1;
    color: #3f3428;
    font-weight: 600;
    border-bottom: 2px solid #c08040;
}
QTabBar::tab:disabled {
    color: #c0b0a0;
}
QPushButton {
    background: #ede8e2;
    color: #3f3428;
    border: none;
    border-radius: 5px;
    padding: 4px 12px;
    font-size: 12px;
}
QPushButton:hover { background: #e0d8d0; }
QPushButton:pressed { background: #d0c8c0; }
QPushButton#primaryBtn {
    background: #c08040;
    color: #fff;
    font-weight: 600;
}
QPushButton#primaryBtn:hover { background: #b07030; }
QPushButton#primaryBtn:disabled { background: #d0c0a0; color: #fff8f0; }
QGroupBox {
    border: 1px solid #ddd6cc;
    border-radius: 6px;
    margin-top: 8px;
    font-size: 12px;
    color: #5a4a3a;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QTableWidget {
    background: #ffffff;
    gridline-color: #e8e0d8;
    selection-background-color: #fde8c8;
    selection-color: #3f3428;
    alternate-background-color: #faf6f1;
    font-size: 12px;
}
QTableWidget::item { padding: 2px 4px; }
QHeaderView::section {
    background: #f0ebe4;
    color: #5a4a3a;
    font-weight: 600;
    font-size: 11px;
    padding: 4px 6px;
    border: none;
    border-right: 1px solid #ddd6cc;
    border-bottom: 1px solid #ddd6cc;
}
QProgressBar {
    background: #ede8e2;
    border-radius: 3px;
}
QProgressBar::chunk {
    background: #c08040;
    border-radius: 3px;
}
QLabel { color: #3f3428; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #ffffff;
    border: 1px solid #ccc4bc;
    border-radius: 4px;
    padding: 3px 6px;
    font-size: 12px;
    color: #3f3428;
}
QCheckBox { font-size: 12px; color: #3f3428; }
QRadioButton { font-size: 12px; color: #3f3428; }
QSplitter::handle { background: #ddd6cc; }
"""


class CombineSampleWindow(QMainWindow):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Combine Sample Measurement Tool")
        self.setMinimumSize(1100, 700)

        # ── Shared state ──────────────────────────────────────────────────
        self._combined_df:    pd.DataFrame | None     = None
        self._filtered_df:    pd.DataFrame | None     = None
        self._sampled_df:     pd.DataFrame | None     = None
        self._template_parsed: dict[str, Any]         = {}
        self._ds_klafs:        dict[str, dict[str, Any]] = {}

        self.setStyleSheet(_STYLESHEET)
        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        cv = QVBoxLayout(central)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.TabPosition.North)

        self._step1 = Step1LoadWidget()
        self._step2 = Step2FilterWidget()
        self._step3 = Step3SampleWidget()
        self._step4 = Step4ExportWidget()

        self._tabs.addTab(self._step1, "Step 1  載入 Dataset")
        self._tabs.addTab(self._step2, "Step 2  品質篩選")
        self._tabs.addTab(self._step3, "Step 3  採樣設定")
        self._tabs.addTab(self._step4, "Step 4  輸出")

        # Steps 2-4 disabled until data flows in
        for i in (1, 2, 3):
            self._tabs.setTabEnabled(i, False)

        cv.addWidget(self._tabs)

        # ── Status bar ────────────────────────────────────────────────────
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage(
            "歡迎使用 Combine Sample Measurement Tool  —  請從 Step 1 開始載入 Dataset"
        )

        # ── Connect signals ───────────────────────────────────────────────
        self._step1.loaded.connect(self._on_step1_loaded)
        self._step2.filtered.connect(self._on_step2_filtered)
        self._step3.sampled.connect(self._on_step3_sampled)

    # ── Step transitions ──────────────────────────────────────────────────────

    @pyqtSlot(object, dict, dict)
    def _on_step1_loaded(
        self,
        df: pd.DataFrame,
        ds_klafs: dict[str, dict[str, Any]],
        template_parsed: dict[str, Any],
    ) -> None:
        self._combined_df    = df
        self._ds_klafs       = ds_klafs
        self._template_parsed = template_parsed

        self._tabs.setTabEnabled(1, True)
        self._step2.set_dataframe(df)
        self._tabs.setCurrentIndex(1)

        n    = len(df)
        nd   = len(ds_klafs)
        miss = int(df["orig_xrel"].isna().sum())
        msg  = (
            f"已載入 {nd} 個 Dataset，共 {n} 筆量測資料"
            + (f"  |  ⚠ {miss} 筆無法配對 KLARF" if miss else "")
        )
        self._statusbar.showMessage(msg)

    @pyqtSlot(object)
    def _on_step2_filtered(self, filtered_df: pd.DataFrame) -> None:
        self._filtered_df = filtered_df

        self._tabs.setTabEnabled(2, True)
        self._step3.set_dataframe(filtered_df)
        self._tabs.setCurrentIndex(2)

        n_total = len(self._combined_df) if self._combined_df is not None else 0
        n_keep  = len(filtered_df)
        self._statusbar.showMessage(
            f"品質篩選後保留 {n_keep} / {n_total} 筆  →  請在 Step 3 設定採樣條件"
        )

    @pyqtSlot(object)
    def _on_step3_sampled(self, sampled_df: pd.DataFrame) -> None:
        self._sampled_df = sampled_df

        self._tabs.setTabEnabled(3, True)
        self._step4.set_data(sampled_df, self._template_parsed, self._ds_klafs)
        self._tabs.setCurrentIndex(3)

        n = len(sampled_df)
        self._statusbar.showMessage(
            f"採樣完成，共 {n} 筆（DID 1–{n}）  →  Step 4 可執行輸出"
        )
