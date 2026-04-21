"""Report workspace — statistics, histogram, and export for batch results."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QLabel, QPushButton, QFileDialog, QMessageBox, QSizePolicy,
    QScrollArea, QProgressDialog, QApplication,
    QDialog, QDialogButtonBox, QCheckBox,
)
from PyQt6.QtCore import pyqtSignal, Qt

from ...core.models import BatchRunRecord, ImageRecord, MeasurementRecord


class ReportWorkspace(QWidget):
    status_message = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._batch_run: BatchRunRecord | None = None
        self._records:   list[MeasurementRecord] = []
        self._image_records: list[ImageRecord] = []
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        from PyQt6.QtCore import Qt
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setSpacing(8)

        # Summary cards
        self._summary_box = QGroupBox("Batch Summary")
        self._summary_layout = QFormLayout(self._summary_box)
        iv.addWidget(self._summary_box)

        # Statistics (generic — covers both Y-CD and X-CD)
        self._stats_box = QGroupBox("CD Statistics")
        self._stats_layout = QFormLayout(self._stats_box)
        iv.addWidget(self._stats_box)

        # Export button
        export_box = QGroupBox("Export")
        ev = QVBoxLayout(export_box)
        btn_export = QPushButton("Export…")
        btn_export.clicked.connect(self._export_dialog_clicked)
        ev.addWidget(btn_export)
        iv.addWidget(export_box)
        iv.addStretch()

        scroll.setWidget(inner)
        root.addWidget(scroll)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_batch_run(self, batch_run: BatchRunRecord) -> None:
        self._batch_run = batch_run
        results = batch_run.output_manifest.get("results", [])

        # Reconstruct MeasurementRecord and ImageRecord lists
        self._records = []
        self._image_records = []
        seen_img: set[str] = set()
        for i, r in enumerate(results):
            img_id = r.get("image_id", "")
            img_path = r.get("image_path", "")
            if img_id not in seen_img:
                ir = ImageRecord.from_path(img_path)
                ir.image_id = img_id
                self._image_records.append(ir)
                seen_img.add(img_id)
            for m_dict in r.get("measurements", []):
                try:
                    self._records.append(MeasurementRecord.from_dict(m_dict))
                except Exception:
                    pass
            if i % 200 == 0:
                QApplication.processEvents()

        self._refresh_summary()
        self._refresh_stats()
        self.status_message.emit(
            f"Report loaded: {batch_run.success_count} OK, {batch_run.fail_count} failed"
        )

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

    def _refresh_stats(self) -> None:
        _clear_form(self._stats_layout)

        ok_vals = [r.calibrated_nm for r in self._records if r.status not in ("rejected",)]
        if not ok_vals:
            self._stats_layout.addRow(QLabel("No data"), QLabel("—"))
            return

        import statistics
        n = len(ok_vals)
        mean = statistics.mean(ok_vals)
        median = statistics.median(ok_vals)
        stdev = statistics.stdev(ok_vals) if n > 1 else 0.0
        if n >= 2:
            qs = statistics.quantiles(ok_vals, n=4)
            q25, q75 = qs[0], qs[2]
        else:
            q25 = q75 = ok_vals[0]
        rows = [
            ("Count:", str(n)),
            ("Mean (nm):", f"{mean:.3f}"),
            ("Median (nm):", f"{median:.3f}"),
            ("Q25 (nm):", f"{q25:.3f}"),
            ("Q75 (nm):", f"{q75:.3f}"),
            ("Std Dev (nm):", f"{stdev:.3f}"),
            ("3-Sigma (nm):", f"{stdev * 3:.3f}"),
            ("Min (nm):", f"{min(ok_vals):.3f}"),
            ("Max (nm):", f"{max(ok_vals):.3f}"),
        ]
        for label, value in rows:
            self._stats_layout.addRow(QLabel(label), QLabel(value))

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_dialog_clicked(self) -> None:
        if not self._records:
            QMessageBox.information(self, "No data", "Load a batch run first.")
            return
        dlg = _ExportDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        folder = dlg.folder
        if not folder:
            QMessageBox.warning(self, "No folder", "Select an output folder first.")
            return
        out = Path(folder)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        errors: list[str] = []

        if dlg.export_csv:
            try:
                from ...output.csv_exporter import export_csv_from_records
                export_csv_from_records(self._records, out / f"measurements_{ts}.csv",
                                        self._image_records)
            except Exception as exc:
                errors.append(f"CSV: {exc}")

        if dlg.export_excel:
            try:
                from ...output.excel_exporter import export_excel_from_records
                export_excel_from_records(self._records, out / f"measurements_{ts}.xlsx",
                                          self._image_records)
            except Exception as exc:
                errors.append(f"Excel: {exc}")

        if dlg.export_json:
            try:
                from ...output.json_exporter import export_json_from_records
                export_json_from_records(self._records, out / f"measurements_{ts}.json",
                                         self._image_records, self._batch_run)
            except Exception as exc:
                errors.append(f"JSON: {exc}")

        if dlg.export_html:
            try:
                from ...output.report_generator import generate_report_from_records
                generate_report_from_records(self._records, out / f"report_{ts}.html",
                                             self._image_records, self._batch_run)
            except Exception as exc:
                errors.append(f"HTML: {exc}")

        if dlg.export_images and self._batch_run:
            try:
                self._export_overlays_to(out)
            except Exception as exc:
                errors.append(f"Images: {exc}")

        if errors:
            QMessageBox.warning(self, "Export errors", "\n".join(errors))
        else:
            msg = f"Export complete → {out.name}"
            self.status_message.emit(msg)
            QMessageBox.information(self, "Done", msg)

    def _export_overlays_to(self, out_path: Path) -> None:
        """Export annotated overlay images for each batch entry into out_path."""
        import cv2
        from ...core.image_loader import load_grayscale
        from ...core.annotator import draw_overlays
        from ..._compat import records_to_legacy_cuts

        results = self._batch_run.output_manifest.get("results", [])
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

def _clear_form(layout) -> None:
    for i in reversed(range(layout.count())):
        item = layout.itemAt(i)
        if item and item.widget():
            item.widget().deleteLater()


def _check_pandas() -> bool:
    try:
        import pandas  # noqa: F401
        return True
    except ImportError:
        return False


class _ExportDialog(QDialog):
    """Modal dialog that lets the user choose output folder and export formats."""

    def __init__(self, parent=None):
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
        self._chk_csv   = QCheckBox("CSV  (measurements table)")
        self._chk_excel = QCheckBox("Excel  (measurements + statistics sheet)")
        self._chk_json  = QCheckBox("JSON")
        self._chk_html  = QCheckBox("HTML Report")
        self._chk_img   = QCheckBox("Overlay images  (annotated PNG per image)")
        if not pandas_ok:
            _no_pd = "  ⚠ 需安裝 pandas：pip install \"pandas>=2.0\" openpyxl"
            self._chk_csv.setText(self._chk_csv.text() + _no_pd)
            self._chk_excel.setText(self._chk_excel.text() + _no_pd)
            self._chk_csv.setEnabled(False)
            self._chk_excel.setEnabled(False)
        else:
            self._chk_csv.setChecked(True)
            self._chk_excel.setChecked(True)
        self._chk_json.setChecked(True)
        self._chk_html.setChecked(True)
        self._chk_img.setChecked(False)
        for chk in (self._chk_csv, self._chk_excel, self._chk_json,
                    self._chk_html, self._chk_img):
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
        return self._chk_csv.isChecked() and self._chk_csv.isEnabled()

    @property
    def export_excel(self) -> bool:
        return self._chk_excel.isChecked() and self._chk_excel.isEnabled()

    @property
    def export_json(self) -> bool:
        return self._chk_json.isChecked()

    @property
    def export_html(self) -> bool:
        return self._chk_html.isChecked()

    @property
    def export_images(self) -> bool:
        return self._chk_img.isChecked()
