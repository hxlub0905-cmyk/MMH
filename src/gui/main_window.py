"""Main application window."""

from __future__ import annotations
import os
import shutil
from pathlib import Path
from datetime import datetime
from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QFileDialog, QMessageBox,
    QToolBar, QStatusBar, QWidget, QVBoxLayout, QButtonGroup,
    QPushButton, QHBoxLayout, QLabel,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QAction, QIcon

from .file_tree_panel import FileTreePanel
from .image_viewer import ImageViewer
from .control_panel import ControlPanel
from .results_panel import ResultsPanel
from .batch_dialog import BatchDialog

from ..core.image_loader import load_grayscale, scan_folder
from ..core.preprocessor import preprocess
from ..core.mg_detector import detect_blobs
from ..core.cmg_analyzer import analyze
from ..core.annotator import draw_overlays


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SEM MM — Massive Measurement")
        self.resize(1280, 800)

        self._current_path: Path | None = None
        self._current_raw = None
        self._current_mask = None
        self._current_cuts = []
        self._preview_timer = QTimer()
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._run_preview)

        self._build_ui()
        self._connect_signals()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Menu bar ──────────────────────────────────────────────────────────
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        self._act_open_folder = QAction("Open Folder…", self)
        self._act_open_folder.setShortcut("Ctrl+O")
        file_menu.addAction(self._act_open_folder)
        file_menu.addSeparator()
        act_quit = QAction("Quit", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        run_menu = menubar.addMenu("&Run")
        self._act_run_single = QAction("Run Single Image", self)
        self._act_run_single.setShortcut("F5")
        run_menu.addAction(self._act_run_single)
        self._act_run_batch = QAction("Run Batch…", self)
        self._act_run_batch.setShortcut("F6")
        run_menu.addAction(self._act_run_batch)

        export_menu = menubar.addMenu("&Export")
        self._act_export = QAction("Export Results…", self)
        self._act_export.setShortcut("Ctrl+E")
        export_menu.addAction(self._act_export)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)
        toolbar.addAction(self._act_open_folder)
        toolbar.addSeparator()
        toolbar.addAction(self._act_run_single)
        toolbar.addAction(self._act_run_batch)
        toolbar.addSeparator()
        toolbar.addAction(self._act_export)

        # ── View mode buttons ─────────────────────────────────────────────────
        mode_widget = QWidget()
        mode_layout = QHBoxLayout(mode_widget)
        mode_layout.setContentsMargins(4, 0, 4, 0)
        mode_layout.addWidget(QLabel("View:"))
        self._btn_raw = QPushButton("Raw")
        self._btn_mask = QPushButton("Mask")
        self._btn_ann = QPushButton("Annotated")
        for btn in (self._btn_raw, self._btn_mask, self._btn_ann):
            btn.setCheckable(True)
            mode_layout.addWidget(btn)
        self._btn_raw.setChecked(True)
        self._view_group = QButtonGroup(self)
        self._view_group.setExclusive(True)
        self._view_group.addButton(self._btn_raw)
        self._view_group.addButton(self._btn_mask)
        self._view_group.addButton(self._btn_ann)
        toolbar.addWidget(mode_widget)

        # ── Central splitter ──────────────────────────────────────────────────
        h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.setCentralWidget(h_splitter)

        # Left: file tree
        self._file_tree = FileTreePanel()
        self._file_tree.setMinimumWidth(180)
        h_splitter.addWidget(self._file_tree)

        # Right: vertical splitter  (controls + viewer | results)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # control panel (horizontal strip at top)
        self._ctrl = ControlPanel()
        right_layout.addWidget(self._ctrl)

        v_splitter = QSplitter(Qt.Orientation.Vertical)
        right_layout.addWidget(v_splitter, stretch=1)

        self._viewer = ImageViewer()
        v_splitter.addWidget(self._viewer)

        self._results = ResultsPanel()
        self._results.setMinimumHeight(120)
        v_splitter.addWidget(self._results)

        v_splitter.setSizes([500, 200])
        h_splitter.setSizes([220, 1060])
        h_splitter.addWidget(right)

        # ── Status bar ────────────────────────────────────────────────────────
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("Ready. Open a folder to begin.")

        self._batch_results: list[dict] = []

    def _connect_signals(self) -> None:
        self._act_open_folder.triggered.connect(self._open_folder)
        self._act_run_single.triggered.connect(self._run_single)
        self._act_run_batch.triggered.connect(self._run_batch)
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
            self._statusbar.showMessage(f"Folder: {folder}")

    @pyqtSlot(Path)
    def _on_file_selected(self, path: Path) -> None:
        self._current_path = path
        try:
            self._current_raw = load_grayscale(path)
        except Exception as exc:
            self._statusbar.showMessage(f"Error loading {path.name}: {exc}")
            return
        self._current_mask = None
        self._current_cuts = []
        self._viewer.set_images(self._current_raw)
        self._viewer.fit_in_view()
        self._results.clear()
        self._statusbar.showMessage(str(path))
        self._schedule_preview()

    def _on_params_changed(self, _nm: float, _params) -> None:
        self._schedule_preview()

    def _schedule_preview(self) -> None:
        self._preview_timer.start(150)   # debounce 150ms

    def _run_preview(self) -> None:
        """Quick mask preview for the currently displayed image."""
        if self._current_raw is None:
            return
        params = self._ctrl.get_preprocess_params()
        try:
            mask = preprocess(self._current_raw, params)
        except Exception:
            return
        self._current_mask = mask
        self._viewer.set_images(self._current_raw, mask, self._annotated_image())
        # update viewer mode without changing selection
        self._viewer._refresh()

    def _annotated_image(self):
        if self._current_mask is not None and self._current_cuts:
            return draw_overlays(self._current_raw, self._current_mask, self._current_cuts)
        return None

    @pyqtSlot()
    def _run_single(self) -> None:
        if self._current_raw is None:
            QMessageBox.information(self, "No image", "Please select an image first.")
            return
        params = self._ctrl.get_preprocess_params()
        nm_px = self._ctrl.get_nm_per_pixel()
        min_area = self._ctrl.get_min_area()
        try:
            mask = preprocess(self._current_raw, params)
            blobs = detect_blobs(mask, min_area=min_area)
            cuts = analyze(blobs, nm_px)
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))
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
        self._statusbar.showMessage(
            f"{name} — {len(cuts)} CMG cut(s), "
            f"{sum(len(c.measurements) for c in cuts)} measurement(s)"
        )

    @pyqtSlot()
    def _run_batch(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Input Folder")
        if not folder:
            return
        image_paths = scan_folder(folder)
        if not image_paths:
            QMessageBox.information(self, "No images", "No supported images found in folder.")
            return

        params = self._ctrl.get_preprocess_params()
        nm_px = self._ctrl.get_nm_per_pixel()
        batch_params = {
            "nm_per_pixel": nm_px,
            "threshold": params.threshold,
            "gauss_k": params.gauss_kernel,
            "morph_open_k": params.morph_open_k,
            "morph_close_k": params.morph_close_k,
            "use_clahe": params.use_clahe,
            "min_area": self._ctrl.get_min_area(),
        }

        dlg = BatchDialog(
            image_paths, batch_params, max_workers=max(1, os.cpu_count() - 1), parent=self
        )
        dlg.batch_done.connect(self._on_batch_done)
        dlg.exec()

    @pyqtSlot(list)
    def _on_batch_done(self, results: list[dict]) -> None:
        self._batch_results = results
        n_ok = sum(1 for r in results if r["status"] == "OK")
        n_fail = len(results) - n_ok
        n_cmg = sum(
            sum(len(c["measurements"]) for c in r.get("cuts", []))
            for r in results
        )
        self._results.update_summary(len(results), n_cmg, n_fail)
        self._statusbar.showMessage(
            f"Batch done — {len(results)} images | {n_cmg} measurements | {n_fail} failures"
        )

    @pyqtSlot()
    def _export(self) -> None:
        if not self._batch_results and self._current_cuts is None:
            QMessageBox.information(self, "Nothing to export", "Run single or batch first.")
            return

        out_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if not out_dir:
            return
        out_path = Path(out_dir)

        # decide what to export
        if self._batch_results:
            data = self._batch_results
        else:
            # wrap single-image result
            from .batch_dialog import _serialise_cuts
            name = self._current_path.name if self._current_path else "image"
            data = [{
                "path": str(self._current_path or ""),
                "status": "OK" if self._current_cuts else "FAIL",
                "cuts": _serialise_cuts(self._current_cuts) if self._current_cuts else [],
                "error": "",
            }]

        nm_px = self._ctrl.get_nm_per_pixel()
        self._do_export(data, out_path, nm_px)
        QMessageBox.information(self, "Export complete", f"Results saved to:\n{out_path}")

    def _do_export(self, results: list[dict], out_path: Path, nm_px: float) -> None:
        from ..output.csv_exporter import export_csv
        from ..output.excel_exporter import export_excel
        from ..output.json_exporter import export_json
        from ..output.report_generator import generate_report
        from ..core.annotator import draw_overlays as _draw
        from ..core.image_loader import load_grayscale
        from ..core.preprocessor import preprocess, PreprocessParams
        from ..core.mg_detector import detect_blobs
        from ..core.cmg_analyzer import analyze

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ann_dir = out_path / "annotated"
        ann_dir.mkdir(exist_ok=True)
        fail_dir = out_path / "_failed"

        params = self._ctrl.get_preprocess_params()
        min_area = self._ctrl.get_min_area()

        import cv2

        for r in results:
            img_path = Path(r["path"])
            if r["status"] == "FAIL":
                fail_dir.mkdir(exist_ok=True)
                if img_path.exists():
                    shutil.copy(img_path, fail_dir / img_path.name)
                continue
            # save annotated image
            try:
                raw = load_grayscale(img_path)
                mask = preprocess(raw, params)
                blobs = detect_blobs(mask, min_area=min_area)
                cuts = analyze(blobs, nm_px)
                ann = _draw(raw, mask, cuts)
                cv2.imwrite(str(ann_dir / (img_path.stem + "_annotated.png")), ann)
            except Exception:
                pass

        export_csv(results, out_path / f"{ts}_measurements.csv", nm_px)
        export_excel(results, out_path / f"{ts}_measurements.xlsx", nm_px)
        export_json(results, out_path / f"{ts}_measurements.json", nm_px)
        generate_report(results, out_path / f"{ts}_report.html", nm_px)
