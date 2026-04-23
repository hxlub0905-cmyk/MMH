"""Report workspace — statistics, histogram, and export for batch results."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QLabel, QPushButton, QFileDialog, QMessageBox, QSizePolicy,
    QScrollArea, QProgressDialog, QApplication, QComboBox,
    QDialog, QDialogButtonBox, QCheckBox,
)
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QThread
from PyQt6.QtGui import QPixmap

from ...core.models import BatchRunRecord, ImageRecord, MeasurementRecord, MultiDatasetBatchRun


class ReportWorkspace(QWidget):
    status_message = pyqtSignal(str)

    def __init__(self, run_store=None, parent: QWidget | None = None):
        super().__init__(parent)
        self._batch_run: BatchRunRecord | None = None
        self._multi_batch_run: MultiDatasetBatchRun | None = None
        self._records:   list[MeasurementRecord] = []
        self._image_records: list[ImageRecord] = []
        self._run_store = run_store
        self._load_worker   = None
        self._export_worker = None
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setSpacing(8)

        # Outlier filter row
        filter_box = QGroupBox("Display Filter")
        fh = QHBoxLayout(filter_box)
        fh.addWidget(QLabel("Outlier filter:"))
        self._outlier_combo = QComboBox()
        self._outlier_combo.addItems(["No filter", "IQR (1.5×)", "3σ (mean ± 3σ)"])
        self._outlier_combo.currentIndexChanged.connect(self._on_filter_changed)
        fh.addWidget(self._outlier_combo)
        fh.addStretch()
        iv.addWidget(filter_box)

        # Summary cards
        self._summary_box = QGroupBox("Batch Summary")
        self._summary_layout = QFormLayout(self._summary_box)
        iv.addWidget(self._summary_box)

        # Statistics — QVBoxLayout holds one (single-batch) or many (multi-batch) sections
        self._stats_box = QGroupBox("CD Statistics")
        self._stats_vbox = QVBoxLayout(self._stats_box)
        self._stats_vbox.setSpacing(6)
        iv.addWidget(self._stats_box)

        # Box plot — visible only for multi-batch
        self._boxplot_box = QGroupBox("CD Distribution by Dataset")
        bpl = QVBoxLayout(self._boxplot_box)
        self._boxplot_label = QLabel("Box plot available after multi-dataset batch run.")
        self._boxplot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._boxplot_label.setStyleSheet("color:#888;")
        bpl.addWidget(self._boxplot_label)
        self._boxplot_box.setVisible(False)
        iv.addWidget(self._boxplot_box)

        # Export button
        export_box = QGroupBox("Export")
        ev = QVBoxLayout(export_box)
        btn_row = QHBoxLayout()
        btn_export = QPushButton("Export…")
        btn_export.clicked.connect(self._export_dialog_clicked)
        btn_load_hist = QPushButton("Load from History…")
        btn_load_hist.clicked.connect(self._load_from_history_clicked)
        btn_row.addWidget(btn_export)
        btn_row.addWidget(btn_load_hist)
        btn_row.addStretch()
        ev.addLayout(btn_row)
        iv.addWidget(export_box)
        iv.addStretch()

        scroll.setWidget(inner)
        root.addWidget(scroll)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_batch_run(self, batch_run: BatchRunRecord) -> None:
        self._batch_run = batch_run
        self._multi_batch_run = None
        self._records = []
        self._image_records = []

        # Show summary immediately from metadata (no records needed)
        self._boxplot_box.setVisible(False)
        self._refresh_summary()
        self.status_message.emit(
            f"Report loading… {batch_run.success_count} OK, {batch_run.fail_count} failed"
        )

        results = batch_run.output_manifest.get("results", [])
        self._load_worker = _LoadWorker(results, multi=False)
        self._load_worker.load_done.connect(self._on_batch_load_done)
        self._load_worker.load_error.connect(
            lambda e: self.status_message.emit(f"Load error: {e}")
        )
        self._load_worker.start()

    @pyqtSlot(list, list)
    def _on_batch_load_done(self, records: list, image_records: list) -> None:
        self._records = records
        self._image_records = image_records
        self._refresh_stats()
        br = self._batch_run
        if br:
            self.status_message.emit(
                f"Report loaded: {br.success_count} OK, {br.fail_count} failed"
            )

    def load_multi_batch(self, mbr: MultiDatasetBatchRun) -> None:
        self._multi_batch_run = mbr
        self._batch_run = None
        self._records = []
        self._image_records = []

        # Show summary immediately
        self._boxplot_box.setVisible(True)
        self._refresh_summary_multi()
        self.status_message.emit(
            f"Multi-batch report loading… {mbr.success_count}/{mbr.total_images} OK  "
            f"·  {len(mbr.datasets)} datasets"
        )

        # Collect all results across datasets for background load
        all_results = []
        for ds in mbr.datasets:
            all_results.extend(ds.output_manifest.get("results", []))
        self._load_worker = _LoadWorker(all_results, multi=False)
        self._load_worker.load_done.connect(self._on_multi_load_done)
        self._load_worker.load_error.connect(
            lambda e: self.status_message.emit(f"Load error: {e}")
        )
        self._load_worker.start()

    @pyqtSlot(list, list)
    def _on_multi_load_done(self, records: list, image_records: list) -> None:
        self._records = records
        self._image_records = image_records
        self._refresh_stats()
        self._refresh_boxplot()
        mbr = self._multi_batch_run
        if mbr:
            self.status_message.emit(
                f"Multi-batch report: {mbr.success_count}/{mbr.total_images} OK  "
                f"·  {len(mbr.datasets)} datasets"
            )

    def load_from_file(self, file_path: str) -> None:
        """Load a batch run from a persisted JSON file."""
        if not self._run_store:
            return
        try:
            result = self._run_store.load(file_path)
        except Exception as exc:
            self.status_message.emit(f"Failed to load: {exc}")
            return
        from ...core.models import MultiDatasetBatchRun
        if isinstance(result, MultiDatasetBatchRun):
            self.load_multi_batch(result)
        else:
            self.load_batch_run(result)

    def _load_from_history_clicked(self) -> None:
        if not self._run_store:
            QMessageBox.information(self, "Not available", "No run store configured.")
            return
        from ..workspaces.batch_workspace import _HistoryDialog
        dlg = _HistoryDialog(self._run_store, self)
        dlg.run_selected.connect(self.load_from_file)
        dlg.exec()

    # ── Filter / refresh ──────────────────────────────────────────────────────

    def _on_filter_changed(self) -> None:
        self._refresh_stats()
        if self._multi_batch_run:
            self._refresh_boxplot()

    def _apply_outlier_filter(self, vals: list[float]) -> list[float]:
        method = self._outlier_combo.currentText()
        if not vals or method == "No filter":
            return vals
        import statistics
        if method.startswith("IQR"):
            if len(vals) < 2:
                return vals
            qs = statistics.quantiles(vals, n=4)
            q1, q3 = qs[0], qs[2]
            iqr = q3 - q1
            return [v for v in vals if q1 - 1.5 * iqr <= v <= q3 + 1.5 * iqr]
        if method.startswith("3σ"):
            mean = statistics.mean(vals)
            std  = statistics.stdev(vals) if len(vals) > 1 else 0.0
            return [v for v in vals if abs(v - mean) <= 3 * std]
        return vals

    def _refresh_summary(self) -> None:
        br = self._batch_run
        if br is None:
            return
        _clear_form(self._summary_layout)
        rows = [
            ("Total images:", str(br.total_images)),
            ("OK:", str(br.success_count)),
            ("Failed:", str(br.fail_count)),
            ("Started:", br.start_time[:19].replace("T", " ") if br.start_time else "—"),
            ("Workers:", str(br.worker_count)),
        ]
        for label, value in rows:
            self._summary_layout.addRow(QLabel(label), QLabel(value))

    def _refresh_summary_multi(self) -> None:
        mbr = self._multi_batch_run
        if mbr is None:
            return
        _clear_form(self._summary_layout)
        rows = [
            ("Datasets:", str(len(mbr.datasets))),
            ("Total images:", str(mbr.total_images)),
            ("OK:", str(mbr.success_count)),
            ("Failed:", str(mbr.fail_count)),
            ("Started:", mbr.start_time[:19].replace("T", " ") if mbr.start_time else "—"),
        ]
        for label, value in rows:
            self._summary_layout.addRow(QLabel(label), QLabel(value))

    def _refresh_stats(self) -> None:
        _clear_vbox(self._stats_vbox)

        if self._multi_batch_run:
            for ds in self._multi_batch_run.datasets:
                vals = _collect_vals_from_results(ds.output_manifest.get("results", []))
                vals = self._apply_outlier_filter(vals)
                grp = QGroupBox(ds.dataset_label or "Dataset")
                fl = QFormLayout(grp)
                _fill_stats_form(fl, vals)
                self._stats_vbox.addWidget(grp)
        else:
            ok_vals = [r.calibrated_nm for r in self._records if r.status not in ("rejected",)]
            ok_vals = self._apply_outlier_filter(ok_vals)
            wrapper = QWidget()
            fl = QFormLayout(wrapper)
            fl.setContentsMargins(0, 0, 0, 0)
            _fill_stats_form(fl, ok_vals)
            self._stats_vbox.addWidget(wrapper)

    def _refresh_boxplot(self) -> None:
        if not self._multi_batch_run:
            return
        datasets_data = []
        for ds in self._multi_batch_run.datasets:
            vals = _collect_vals_from_results(ds.output_manifest.get("results", []))
            vals = self._apply_outlier_filter(vals)
            datasets_data.append({"label": ds.dataset_label or "Dataset", "values": vals})

        try:
            from ...output.report_generator import _boxplot_b64
            import base64
            b64 = _boxplot_b64(datasets_data)
            if b64:
                pix = QPixmap()
                pix.loadFromData(base64.b64decode(b64))
                self._boxplot_label.setPixmap(pix)
                self._boxplot_label.setText("")
            else:
                self._boxplot_label.setPixmap(QPixmap())
                self._boxplot_label.setText(
                    "Box plot unavailable (install matplotlib to enable)."
                )
        except Exception as exc:
            self._boxplot_label.setText(f"Box plot error: {exc}")

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_dialog_clicked(self) -> None:
        if not self._records:
            QMessageBox.information(self, "No data", "Load a batch run first.")
            return
        has_multi = self._multi_batch_run is not None
        dlg = _ExportDialog(self, has_multi_batch=has_multi)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        folder = dlg.folder
        if not folder:
            QMessageBox.warning(self, "No folder", "Select an output folder first.")
            return
        out = Path(folder)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        per_dataset = dlg.per_dataset and has_multi

        # Build the list of (label, callable) tasks to run in the background
        tasks: list[tuple[str, object]] = []

        if dlg.export_excel:
            from ...output.excel_exporter import export_excel_from_records
            _meas_mode = dlg.excel_meas_mode
            if per_dataset and self._multi_batch_run:
                for ds in self._multi_batch_run.datasets:
                    ds_label = ds.dataset_label or "Dataset"
                    ds_records, ds_image_records = _extract_ds_records(ds)
                    ds_out = out / ds_label
                    tasks.append((
                        f"Excel [{ds_label}]",
                        lambda r=ds_records, ir=ds_image_records, p=ds_out, lb=ds_label, mm=_meas_mode:
                            (p.mkdir(parents=True, exist_ok=True),
                             export_excel_from_records(r, p / f"measurements_{ts}.xlsx", ir,
                                                       dataset_label=lb, meas_mode=mm)),
                    ))
            elif self._multi_batch_run:
                datasets_for_excel = [
                    {
                        "records":       _extract_ds_records(ds)[0],
                        "image_records": _extract_ds_records(ds)[1],
                        "dataset_label": ds.dataset_label or "Dataset",
                    }
                    for ds in self._multi_batch_run.datasets
                ]
                tasks.append((
                    "Excel",
                    lambda d=datasets_for_excel, mm=_meas_mode:
                        export_excel_from_records([], out / f"measurements_{ts}.xlsx",
                                                  datasets=d, meas_mode=mm),
                ))
            else:
                ds_label = (
                    self._batch_run.dataset_label
                    if self._batch_run and self._batch_run.dataset_label else ""
                )
                tasks.append((
                    "Excel",
                    lambda r=self._records, ir=self._image_records, lb=ds_label, mm=_meas_mode:
                        export_excel_from_records(r, out / f"measurements_{ts}.xlsx",
                                                  ir, dataset_label=lb, meas_mode=mm),
                ))

        if dlg.export_json:
            from ...output.json_exporter import export_json_from_records
            if per_dataset and self._multi_batch_run:
                for ds in self._multi_batch_run.datasets:
                    ds_label = ds.dataset_label or "Dataset"
                    ds_records, ds_image_records = _extract_ds_records(ds)
                    ds_out = out / ds_label
                    tasks.append((
                        f"JSON [{ds_label}]",
                        lambda r=ds_records, ir=ds_image_records, p=ds_out:
                            (p.mkdir(parents=True, exist_ok=True),
                             export_json_from_records(r, p / f"measurements_{ts}.json", ir)),
                    ))
            else:
                tasks.append((
                    "JSON",
                    lambda: export_json_from_records(
                        self._records, out / f"measurements_{ts}.json",
                        self._image_records, self._batch_run),
                ))

        if dlg.export_html:
            if per_dataset and self._multi_batch_run:
                from ...output.report_generator import generate_report_from_records
                for ds in self._multi_batch_run.datasets:
                    ds_label = ds.dataset_label or "Dataset"
                    ds_records, ds_image_records = _extract_ds_records(ds)
                    ds_out = out / ds_label
                    tasks.append((
                        f"HTML [{ds_label}]",
                        lambda r=ds_records, ir=ds_image_records, p=ds_out:
                            (p.mkdir(parents=True, exist_ok=True),
                             generate_report_from_records(r, p / f"report_{ts}.html", ir)),
                    ))
            elif self._multi_batch_run:
                from ...output.report_generator import generate_multi_dataset_report
                datasets_data = []
                for ds in self._multi_batch_run.datasets:
                    vals = _collect_vals_from_results(ds.output_manifest.get("results", []))
                    vals = self._apply_outlier_filter(vals)
                    nm_pp = _infer_nm_per_pixel(ds.output_manifest.get("results", []))
                    datasets_data.append({
                        "label": ds.dataset_label or "Dataset",
                        "values": vals,
                        "total_images": ds.total_images,
                        "fail_count":   ds.fail_count,
                        "nm_per_pixel": nm_pp,
                    })
                tasks.append((
                    "HTML",
                    lambda d=datasets_data:
                        generate_multi_dataset_report(d, out / f"report_{ts}.html"),
                ))
            else:
                from ...output.report_generator import generate_report_from_records
                tasks.append((
                    "HTML",
                    lambda: generate_report_from_records(
                        self._records, out / f"report_{ts}.html",
                        self._image_records, self._batch_run),
                ))

        if dlg.export_images:
            if self._multi_batch_run:
                for ds in self._multi_batch_run.datasets:
                    ds_label = ds.dataset_label or "dataset"
                    results = ds.output_manifest.get("results", [])
                    img_out = out / ds_label
                    tasks.append((
                        f"Images [{ds_label}]",
                        lambda r=results, p=img_out:
                            self._export_overlays_from_results(r, p),
                    ))
            elif self._batch_run:
                results = self._batch_run.output_manifest.get("results", [])
                tasks.append((
                    "Images",
                    lambda r=results: self._export_overlays_from_results(r, out),
                ))

        if dlg.export_boxplot and self._multi_batch_run:
            from ...output.report_generator import _boxplot_b64
            import base64
            datasets_data = []
            for ds in self._multi_batch_run.datasets:
                vals = _collect_vals_from_results(ds.output_manifest.get("results", []))
                vals = self._apply_outlier_filter(vals)
                datasets_data.append({"label": ds.dataset_label or "Dataset", "values": vals})
            tasks.append((
                "Box Plot",
                lambda d=datasets_data, b64=_boxplot_b64, dec=base64.b64decode:
                    (lambda bdata: (out / f"boxplot_{ts}.png").write_bytes(dec(bdata)) if bdata else None)(b64(d)),
            ))

        if not tasks:
            return

        # Run all tasks in background with a progress dialog
        progress_dlg = QProgressDialog("Preparing export…", None, 0, 0, self)
        progress_dlg.setWindowTitle("Exporting…")
        progress_dlg.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dlg.setMinimumDuration(0)
        progress_dlg.show()

        self._export_worker = _ExportWorker(tasks)
        self._export_worker.progress.connect(progress_dlg.setLabelText)
        self._export_worker.finished.connect(progress_dlg.close)
        self._export_worker.finished.connect(
            lambda errors: self._on_export_done(errors, out)
        )
        self._export_worker.start()

    @pyqtSlot(list)
    def _on_export_done(self, errors: list, out: Path) -> None:
        if errors:
            QMessageBox.warning(self, "Export errors", "\n".join(errors))
        else:
            msg = f"Export complete → {out.name}"
            self.status_message.emit(msg)
            QMessageBox.information(self, "Done", msg)

    def _export_overlays_from_results(self, results: list[dict], out_path: Path) -> None:
        import cv2
        from ...core.image_loader import load_grayscale
        from ...core.annotator import draw_overlays
        from ..._compat import records_to_legacy_cuts

        out_path.mkdir(parents=True, exist_ok=True)
        total = len(results)

        progress = QProgressDialog("Exporting overlay images…", "Cancel", 0, total, self)
        progress.setWindowTitle("Export Overlays")
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)

        exported = errors = 0
        for i, entry in enumerate(results):
            progress.setValue(i)
            QApplication.processEvents()
            if progress.wasCanceled():
                break
            image_path = entry.get("image_path", "")
            if not image_path or not Path(image_path).exists():
                errors += 1
                continue
            stem = Path(image_path).stem
            try:
                raw = load_grayscale(image_path)
                recs = []
                for m_dict in entry.get("measurements", []):
                    try:
                        recs.append(MeasurementRecord.from_dict(m_dict))
                    except Exception:
                        pass
                cuts = records_to_legacy_cuts(recs)
                if cuts:
                    annotated = draw_overlays(raw, None, cuts)
                else:
                    annotated = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
                cv2.imwrite(str(out_path / f"{stem}_annotated.png"), annotated)
                exported += 1
            except Exception:
                errors += 1

        progress.setValue(total)
        msg = f"Exported {exported} overlay image(s)"
        if errors:
            msg += f"  ({errors} skipped)"
        self.status_message.emit(msg)


# ── helpers ───────────────────────────────────────────────────────────────────

def _collect_vals_from_results(results: list[dict]) -> list[float]:
    vals = []
    for r in results:
        for m_dict in r.get("measurements", []):
            try:
                rec = MeasurementRecord.from_dict(m_dict)
                if rec.status not in ("rejected",):
                    vals.append(float(rec.calibrated_nm))
            except Exception:
                pass
    return vals


def _fill_stats_form(fl: QFormLayout, vals: list[float]) -> None:
    if not vals:
        fl.addRow(QLabel("No data"), QLabel("—"))
        return
    import statistics
    n = len(vals)
    mean = statistics.mean(vals)
    median = statistics.median(vals)
    stdev = statistics.stdev(vals) if n > 1 else 0.0
    if n >= 2:
        qs = statistics.quantiles(vals, n=4)
        q25, q75 = qs[0], qs[2]
    else:
        q25 = q75 = vals[0]
    rows = [
        ("Count:", str(n)),
        ("Mean (nm):", f"{mean:.3f}"),
        ("Median (nm):", f"{median:.3f}"),
        ("Q25 (nm):", f"{q25:.3f}"),
        ("Q75 (nm):", f"{q75:.3f}"),
        ("Std Dev (nm):", f"{stdev:.3f}"),
        ("3-Sigma (nm):", f"{stdev * 3:.3f}"),
        ("Min (nm):", f"{min(vals):.3f}"),
        ("Max (nm):", f"{max(vals):.3f}"),
    ]
    for label, value in rows:
        fl.addRow(QLabel(label), QLabel(value))


def _clear_form(layout) -> None:
    for i in reversed(range(layout.count())):
        item = layout.itemAt(i)
        if item and item.widget():
            item.widget().deleteLater()


def _clear_vbox(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item and item.widget():
            item.widget().deleteLater()


def _infer_nm_per_pixel(results: list[dict]) -> float:
    """Infer nm/pixel from the first measurement that has both raw_px and calibrated_nm."""
    for r in results:
        for m_dict in r.get("measurements", []):
            raw_px = float(m_dict.get("raw_px", 0.0))
            cal_nm = float(m_dict.get("calibrated_nm", 0.0))
            if raw_px > 0 and cal_nm > 0:
                return cal_nm / raw_px
    return 1.0


def _check_pandas() -> bool:
    try:
        import pandas  # noqa: F401
        return True
    except ImportError:
        return False


class _ExportDialog(QDialog):
    """Modal dialog that lets the user choose output folder and export formats."""

    def __init__(self, parent=None, *, has_multi_batch: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Export")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Output folder row
        folder_box = QGroupBox("Output folder")
        fh = QHBoxLayout(folder_box)
        self._folder_label = QLabel("(not selected)")
        self._folder_label.setWordWrap(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(80)
        browse_btn.clicked.connect(self._browse_folder)
        fh.addWidget(self._folder_label, 1)
        fh.addWidget(browse_btn)
        layout.addWidget(folder_box)

        # Format checkboxes
        pandas_ok = _check_pandas()
        formats_box = QGroupBox("Formats to export")
        fv = QVBoxLayout(formats_box)

        # Comprehensive Excel replaces separate CSV + Excel options
        self._chk_excel = QCheckBox(
            "Comprehensive Excel  (All Measurements + Image Summary + Statistics)\n"
            "  • CD line XY positions per measurement (origin = image top-left)\n"
            "  • MIN/MAX CD locations highlighted in Image Summary sheet"
        )
        self._chk_excel.setStyleSheet("QCheckBox { spacing: 6px; }")

        self._chk_json    = QCheckBox("JSON")
        self._chk_html    = QCheckBox("HTML Report")
        self._chk_img     = QCheckBox("Overlay images  (annotated PNG per image)")
        self._chk_boxplot = QCheckBox("Box Plot (PNG)  — multi-dataset only")
        self._chk_boxplot.setEnabled(has_multi_batch)
        self._chk_per_dataset = QCheckBox(
            "Per-dataset output  (each dataset → its own subfolder)"
        )
        self._chk_per_dataset.setEnabled(has_multi_batch)
        if has_multi_batch:
            self._chk_per_dataset.setChecked(False)

        # Measurement mode selector (only relevant for Excel)
        meas_mode_row = QHBoxLayout()
        meas_mode_row.addSpacing(24)
        meas_mode_row.addWidget(QLabel("All Measurements 輸出模式："))
        self._excel_mode_combo = QComboBox()
        self._excel_mode_combo.addItem("全部測量值 (All)", "all")
        self._excel_mode_combo.addItem("每張圖最小值 (Min per image)", "min_per_image")
        self._excel_mode_combo.addItem("每張圖最大值 (Max per image)", "max_per_image")
        meas_mode_row.addWidget(self._excel_mode_combo, 1)

        if not pandas_ok:
            _no_pd = "  ⚠ 需安裝 pandas：pip install \"pandas>=2.0\" openpyxl"
            self._chk_excel.setText(self._chk_excel.text() + _no_pd)
            self._chk_excel.setEnabled(False)
            self._excel_mode_combo.setEnabled(False)
        else:
            self._chk_excel.setChecked(True)
        self._chk_json.setChecked(True)
        self._chk_html.setChecked(True)
        self._chk_img.setChecked(False)
        if has_multi_batch:
            self._chk_boxplot.setChecked(True)

        # Sync combo enabled state with Excel checkbox
        self._chk_excel.toggled.connect(self._excel_mode_combo.setEnabled)

        for chk in (self._chk_excel,):
            fv.addWidget(chk)
        fv.addLayout(meas_mode_row)
        for chk in (self._chk_json, self._chk_html, self._chk_img,
                    self._chk_boxplot, self._chk_per_dataset):
            fv.addWidget(chk)
        layout.addWidget(formats_box)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._folder = ""

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if folder:
            self._folder = folder
            self._folder_label.setText(folder)

    @property
    def folder(self) -> str:
        return self._folder

    @property
    def export_csv(self) -> bool:
        return False  # CSV merged into Comprehensive Excel

    @property
    def export_excel(self) -> bool:
        return self._chk_excel.isChecked() and self._chk_excel.isEnabled()

    @property
    def excel_meas_mode(self) -> str:
        return self._excel_mode_combo.currentData() or "all"

    @property
    def export_json(self) -> bool:
        return self._chk_json.isChecked()

    @property
    def export_html(self) -> bool:
        return self._chk_html.isChecked()

    @property
    def export_images(self) -> bool:
        return self._chk_img.isChecked()

    @property
    def export_boxplot(self) -> bool:
        return self._chk_boxplot.isChecked() and self._chk_boxplot.isEnabled()

    @property
    def per_dataset(self) -> bool:
        return self._chk_per_dataset.isChecked() and self._chk_per_dataset.isEnabled()


# ── Background workers ────────────────────────────────────────────────────────

class _LoadWorker(QThread):
    """Deserialise batch results into records off the main thread."""
    load_done  = pyqtSignal(list, list)  # records, image_records
    load_error = pyqtSignal(str)

    def __init__(self, results: list, *, multi: bool = False):
        super().__init__()
        self._results = results

    def run(self) -> None:
        try:
            from ...core.models import ImageRecord, MeasurementRecord
            records: list = []
            image_records: list = []
            seen_img: set = set()
            for r in self._results:
                img_id   = r.get("image_id", "")
                img_path = r.get("image_path", "")
                if img_id not in seen_img:
                    ir = ImageRecord.from_path(img_path)
                    ir.image_id = img_id
                    image_records.append(ir)
                    seen_img.add(img_id)
                for m_dict in r.get("measurements", []):
                    try:
                        records.append(MeasurementRecord.from_dict(m_dict))
                    except Exception:
                        pass
            self.load_done.emit(records, image_records)
        except Exception as exc:
            self.load_error.emit(str(exc))


class _ExportWorker(QThread):
    """Run a list of (label, callable) export tasks sequentially off the main thread."""
    progress = pyqtSignal(str)   # status message for progress dialog
    finished = pyqtSignal(list)  # list of error strings (empty = success)

    def __init__(self, tasks: list):
        super().__init__()
        self._tasks = tasks

    def run(self) -> None:
        errors: list[str] = []
        for label, fn in self._tasks:
            self.progress.emit(f"正在輸出 {label}…")
            try:
                fn()
            except Exception as exc:
                errors.append(f"{label}: {exc}")
        self.finished.emit(errors)


# ── Dataset extraction helper ─────────────────────────────────────────────────

def _extract_ds_records(ds) -> tuple:
    """Extract (records, image_records) from a BatchRunRecord dataset."""
    from ...core.models import ImageRecord, MeasurementRecord
    records: list = []
    image_records: list = []
    seen_img: set = set()
    for r in ds.output_manifest.get("results", []):
        img_id   = r.get("image_id", "")
        img_path = r.get("image_path", "")
        if img_id not in seen_img:
            ir = ImageRecord.from_path(img_path)
            ir.image_id = img_id
            image_records.append(ir)
            seen_img.add(img_id)
        for m_dict in r.get("measurements", []):
            try:
                records.append(MeasurementRecord.from_dict(m_dict))
            except Exception:
                pass
    return records, image_records
