"""Main application window — 3-panel dark UI."""

from __future__ import annotations
import os
import shutil
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QFileDialog, QMessageBox,
    QToolBar, QStatusBar, QWidget, QVBoxLayout, QHBoxLayout,
    QFrame, QLabel, QPushButton, QButtonGroup, QApplication,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot, QSize
from PyQt6.QtGui import QAction, QFont

from .file_tree_panel import FileTreePanel
from .image_viewer import ImageViewer
from .control_panel import ControlPanel
from .results_panel import ResultsPanel
from .batch_dialog import BatchDialog
from .styles import STYLE

from ..core.image_loader import load_grayscale, scan_folder
from ..core.preprocessor import preprocess
from ..core.mg_detector import detect_blobs
from ..core.cmg_analyzer import analyze
from ..core.annotator import draw_overlays


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SEM MM — Massive Measurement")
        self.resize(1400, 860)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(STYLE)

        self._current_path: Path | None = None
        self._current_raw  = None
        self._current_mask = None
        self._current_cuts: list = []
        self._batch_results: list = []

        self._preview_timer = QTimer()
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._run_preview)

        self._build_ui()
        self._connect_signals()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_menubar()
        self._build_toolbar()

        # ── Root splitter: Left | Center | Right ──────────────────────────────
        root_splitter = QSplitter(Qt.Orientation.Horizontal)
        root_splitter.setChildrenCollapsible(False)
        self.setCentralWidget(root_splitter)

        root_splitter.addWidget(self._make_left_panel())
        root_splitter.addWidget(self._make_center_panel())
        root_splitter.addWidget(self._ctrl)   # right panel IS the control panel

        root_splitter.setSizes([210, 960, 250])
        root_splitter.setStretchFactor(0, 0)
        root_splitter.setStretchFactor(1, 1)
        root_splitter.setStretchFactor(2, 0)

        # ── Status bar ────────────────────────────────────────────────────────
        sb = QStatusBar()
        self.setStatusBar(sb)
        sb.showMessage("Ready — open a folder to begin.")

    def _build_menubar(self) -> None:
        mb = self.menuBar()

        fm = mb.addMenu("&File")
        self._act_open = QAction("Open Folder…  Ctrl+O", self)
        self._act_open.setShortcut("Ctrl+O")
        fm.addAction(self._act_open)
        fm.addSeparator()
        fm.addAction(QAction("Quit  Ctrl+Q", self, shortcut="Ctrl+Q",
                             triggered=self.close))

        rm = mb.addMenu("&Run")
        self._act_single = QAction("Run Single  F5", self)
        self._act_single.setShortcut("F5")
        rm.addAction(self._act_single)
        self._act_batch = QAction("Run Batch…  F6", self)
        self._act_batch.setShortcut("F6")
        rm.addAction(self._act_batch)

        em = mb.addMenu("&Export")
        self._act_export = QAction("Export Results…  Ctrl+E", self)
        self._act_export.setShortcut("Ctrl+E")
        em.addAction(self._act_export)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(14, 14))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(tb)

        tb.addAction(self._act_open)
        tb.addSeparator()
        tb.addAction(self._act_single)
        tb.addAction(self._act_batch)
        tb.addSeparator()
        tb.addAction(self._act_export)

    def _make_left_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("leftPanel")
        panel.setMinimumWidth(160)
        panel.setMaximumWidth(300)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        title = QLabel("FILES")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self._file_tree = FileTreePanel()
        layout.addWidget(self._file_tree)

        return panel

    def _make_center_panel(self) -> QWidget:
        center = QWidget()
        vbox = QVBoxLayout(center)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # ── viewer header ─────────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("viewerHeader")
        hbox = QHBoxLayout(header)
        hbox.setContentsMargins(10, 0, 12, 0)
        hbox.setSpacing(0)

        # Segmented mode buttons
        self._btn_raw  = QPushButton("Raw")
        self._btn_mask = QPushButton("Mask")
        self._btn_ann  = QPushButton("Annotated")
        self._btn_raw.setObjectName("segLeft")
        self._btn_mask.setObjectName("segMid")
        self._btn_ann.setObjectName("segRight")
        for btn in (self._btn_raw, self._btn_mask, self._btn_ann):
            btn.setCheckable(True)
            btn.setFixedHeight(26)
        self._btn_raw.setChecked(True)

        self._view_group = QButtonGroup(self)
        self._view_group.setExclusive(True)
        for btn in (self._btn_raw, self._btn_mask, self._btn_ann):
            self._view_group.addButton(btn)

        hbox.addWidget(self._btn_raw)
        hbox.addWidget(self._btn_mask)
        hbox.addWidget(self._btn_ann)
        hbox.addStretch()

        self._zoom_label = QLabel("Double-click to fit")
        self._zoom_label.setStyleSheet("color: #303458; font-size: 11px;")
        hbox.addWidget(self._zoom_label)

        vbox.addWidget(header)

        # ── vertical splitter: image viewer | results table ───────────────────
        v_split = QSplitter(Qt.Orientation.Vertical)
        v_split.setChildrenCollapsible(False)

        self._viewer = ImageViewer()
        v_split.addWidget(self._viewer)

        self._results = ResultsPanel()
        self._results.setMinimumHeight(100)
        v_split.addWidget(self._results)

        v_split.setSizes([600, 200])
        v_split.setStretchFactor(0, 1)
        v_split.setStretchFactor(1, 0)

        vbox.addWidget(v_split, stretch=1)

        # control panel (right dock) — instantiate here so it exists before
        # _build_ui() needs to reference it
        self._ctrl = ControlPanel()
        self._ctrl.setMinimumWidth(230)
        self._ctrl.setMaximumWidth(310)

        return center

    def _connect_signals(self) -> None:
        self._act_open.triggered.connect(self._open_folder)
        self._act_single.triggered.connect(self._run_single)
        self._act_batch.triggered.connect(self._run_batch)
        self._act_export.triggered.connect(self._export)

        self._file_tree.file_selected.connect(self._on_file_selected)
        self._ctrl.params_changed.connect(self._on_params_changed)
        self._ctrl.run_single.connect(self._run_single)
        self._ctrl.run_batch.connect(self._run_batch)

        self._btn_raw.clicked.connect(lambda: self._viewer.set_mode("raw"))
        self._btn_mask.clicked.connect(lambda: self._viewer.set_mode("mask"))
        self._btn_ann.clicked.connect(lambda: self._viewer.set_mode("annotated"))

    # ── slots ─────────────────────────────────────────────────────────────────

    @pyqtSlot()
    def _open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select SEM Image Folder")
        if folder:
            self._file_tree.set_root(folder)
            self.statusBar().showMessage(f"Folder: {folder}")

    @pyqtSlot(Path)
    def _on_file_selected(self, path: Path) -> None:
        self._current_path = path
        try:
            self._current_raw = load_grayscale(path)
        except Exception as exc:
            self.statusBar().showMessage(f"Load error: {exc}")
            return
        self._current_mask = None
        self._current_cuts = []
        self._viewer.set_images(self._current_raw)
        self._viewer.fit_in_view()
        self._results.clear()
        self.statusBar().showMessage(str(path))
        self._schedule_preview()

    def _on_params_changed(self, _nm: float, _p) -> None:
        self._schedule_preview()

    def _schedule_preview(self) -> None:
        self._preview_timer.start(180)

    def _run_preview(self) -> None:
        if self._current_raw is None:
            return
        try:
            mask = preprocess(self._current_raw, self._ctrl.get_preprocess_params())
        except Exception:
            return
        self._current_mask = mask
        annotated = self._make_annotated()
        self._viewer.set_images(self._current_raw, mask, annotated)

    def _make_annotated(self):
        if self._current_mask is not None and self._current_cuts:
            return draw_overlays(self._current_raw, self._current_mask, self._current_cuts)
        return None

    @pyqtSlot()
    def _run_single(self) -> None:
        if self._current_raw is None:
            QMessageBox.information(self, "No image", "Select an image first.")
            return
        params   = self._ctrl.get_preprocess_params()
        nm_px    = self._ctrl.get_nm_per_pixel()
        min_area = self._ctrl.get_min_area()
        try:
            mask  = preprocess(self._current_raw, params)
            blobs = detect_blobs(mask, min_area=min_area)
            cuts  = analyze(blobs, nm_px)
        except Exception as exc:
            QMessageBox.critical(self, "Processing error", str(exc))
            return

        self._current_mask = mask
        self._current_cuts = cuts
        annotated = draw_overlays(self._current_raw, mask, cuts) if cuts else None
        self._viewer.set_images(self._current_raw, mask, annotated)

        name = self._current_path.name if self._current_path else "image"
        if cuts:
            self._results.show_results(name, cuts)
            self._btn_ann.setChecked(True)
            self._viewer.set_mode("annotated")
        else:
            self._results.show_fail(name, "No CMG cuts detected")

        n_meas = sum(len(c.measurements) for c in cuts)
        self.statusBar().showMessage(
            f"{name}  ·  {len(cuts)} CMG cut(s)  ·  {n_meas} measurement(s)"
        )

    @pyqtSlot()
    def _run_batch(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if not folder:
            return
        paths = scan_folder(folder)
        if not paths:
            QMessageBox.information(self, "No images", "No supported images found.")
            return

        params = self._ctrl.get_preprocess_params()
        batch_params = {
            "nm_per_pixel": self._ctrl.get_nm_per_pixel(),
            "threshold": params.threshold,
            "gauss_k": params.gauss_kernel,
            "morph_open_k": params.morph_open_k,
            "morph_close_k": params.morph_close_k,
            "use_clahe": params.use_clahe,
            "min_area": self._ctrl.get_min_area(),
        }
        workers = max(1, (os.cpu_count() or 2) - 1)
        dlg = BatchDialog(paths, batch_params, workers, parent=self)
        dlg.batch_done.connect(self._on_batch_done)
        dlg.exec()

    @pyqtSlot(list)
    def _on_batch_done(self, results: list) -> None:
        self._batch_results = results
        n_ok   = sum(1 for r in results if r["status"] == "OK")
        n_fail = len(results) - n_ok
        n_meas = sum(
            sum(len(c["measurements"]) for c in r.get("cuts", []))
            for r in results
        )
        self._results.update_summary(len(results), n_meas, n_fail)
        self.statusBar().showMessage(
            f"Batch done  ·  {len(results)} images  ·  {n_meas} measurements  ·  {n_fail} failures"
        )

    @pyqtSlot()
    def _export(self) -> None:
        if not self._batch_results and not self._current_cuts:
            QMessageBox.information(self, "Nothing to export", "Run single or batch first.")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not out_dir:
            return
        nm_px = self._ctrl.get_nm_per_pixel()
        if self._batch_results:
            data = self._batch_results
        else:
            from .batch_dialog import _serialise_cuts
            data = [{
                "path": str(self._current_path or ""),
                "status": "OK" if self._current_cuts else "FAIL",
                "cuts": _serialise_cuts(self._current_cuts),
                "error": "",
            }]
        self._do_export(data, Path(out_dir), nm_px)
        QMessageBox.information(self, "Export complete",
                                f"Results saved to:\n{out_dir}")

    def _do_export(self, results: list, out_path: Path, nm_px: float) -> None:
        import cv2
        from ..output.csv_exporter import export_csv
        from ..output.excel_exporter import export_excel
        from ..output.json_exporter import export_json
        from ..output.report_generator import generate_report

        ts      = datetime.now().strftime("%Y%m%d_%H%M%S")
        ann_dir = out_path / "annotated"
        ann_dir.mkdir(exist_ok=True)
        fail_dir = out_path / "_failed"

        params   = self._ctrl.get_preprocess_params()
        min_area = self._ctrl.get_min_area()

        for r in results:
            img_path = Path(r["path"])
            if r["status"] == "FAIL":
                fail_dir.mkdir(exist_ok=True)
                if img_path.exists():
                    shutil.copy(img_path, fail_dir / img_path.name)
                continue
            try:
                raw   = load_grayscale(img_path)
                mask  = preprocess(raw, params)
                blobs = detect_blobs(mask, min_area=min_area)
                cuts  = analyze(blobs, nm_px)
                ann   = draw_overlays(raw, mask, cuts)
                cv2.imwrite(str(ann_dir / (img_path.stem + "_annotated.png")), ann)
            except Exception:
                pass

        export_csv(results,   out_path / f"{ts}_measurements.csv",  nm_px)
        export_excel(results, out_path / f"{ts}_measurements.xlsx", nm_px)
        export_json(results,  out_path / f"{ts}_measurements.json", nm_px)
        generate_report(results, out_path / f"{ts}_report.html",    nm_px)
