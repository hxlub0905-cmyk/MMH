"""Report workspace — statistics, histogram, and export for batch results."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QFormLayout,
    QLabel, QPushButton, QFileDialog, QMessageBox, QSizePolicy,
    QScrollArea, QProgressDialog, QApplication,
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

        # Export buttons
        export_box = QGroupBox("Export")
        ev = QVBoxLayout(export_box)
        btn_csv    = QPushButton("Export CSV")
        btn_excel  = QPushButton("Export Excel")
        btn_json   = QPushButton("Export JSON")
        btn_html   = QPushButton("Generate HTML Report")
        btn_images = QPushButton("Export Images (Raw + Annotated)…")
        btn_csv.clicked.connect(self._export_csv)
        btn_excel.clicked.connect(self._export_excel)
        btn_json.clicked.connect(self._export_json)
        btn_html.clicked.connect(self._export_html)
        btn_images.clicked.connect(self._export_images)
        for btn in (btn_csv, btn_excel, btn_json, btn_html, btn_images):
            ev.addWidget(btn)
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
        for r in results:
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
        rows = [
            ("Count:", str(n)),
            ("Mean (nm):", f"{mean:.3f}"),
            ("Median (nm):", f"{median:.3f}"),
            ("Std Dev (nm):", f"{stdev:.3f}"),
            ("3-Sigma (nm):", f"{stdev * 3:.3f}"),
            ("Min (nm):", f"{min(ok_vals):.3f}"),
            ("Max (nm):", f"{max(ok_vals):.3f}"),
        ]
        for label, value in rows:
            self._stats_layout.addRow(QLabel(label), QLabel(value))

    # ── Export ────────────────────────────────────────────────────────────────

    def _get_out_path(self, suffix: str) -> Path | None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save as", f"measurements_{ts}{suffix}", f"*{suffix}"
        )
        return Path(path) if path else None

    def _export_csv(self) -> None:
        if not self._records:
            QMessageBox.information(self, "No data", "Load a batch run first.")
            return
        p = self._get_out_path(".csv")
        if p is None:
            return
        try:
            from ...output.csv_exporter import export_csv_from_records
            export_csv_from_records(self._records, p, self._image_records)
            self.status_message.emit(f"CSV exported → {p.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _export_excel(self) -> None:
        if not self._records:
            QMessageBox.information(self, "No data", "Load a batch run first.")
            return
        p = self._get_out_path(".xlsx")
        if p is None:
            return
        try:
            from ...output.excel_exporter import export_excel_from_records
            export_excel_from_records(self._records, p, self._image_records)
            self.status_message.emit(f"Excel exported → {p.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _export_json(self) -> None:
        if not self._records:
            QMessageBox.information(self, "No data", "Load a batch run first.")
            return
        p = self._get_out_path(".json")
        if p is None:
            return
        try:
            from ...output.json_exporter import export_json_from_records
            export_json_from_records(self._records, p, self._image_records, self._batch_run)
            self.status_message.emit(f"JSON exported → {p.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _export_html(self) -> None:
        if not self._records:
            QMessageBox.information(self, "No data", "Load a batch run first.")
            return
        p = self._get_out_path(".html")
        if p is None:
            return
        try:
            from ...output.report_generator import generate_report_from_records
            generate_report_from_records(self._records, p, self._image_records, self._batch_run)
            self.status_message.emit(f"HTML report → {p.name}")
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _export_images(self) -> None:
        """Export raw + annotated images for each batch entry into a chosen folder."""
        if not self._batch_run:
            QMessageBox.information(self, "No data", "Load a batch run first.")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "Select output folder")
        if not out_dir:
            return
        out_path = Path(out_dir)

        try:
            import cv2
            from ...core.image_loader import load_grayscale
            from ...core.annotator import draw_overlays
            from ..._compat import records_to_legacy_cuts

            results = self._batch_run.output_manifest.get("results", [])
            total = len(results)

            progress = QProgressDialog("Exporting images…", "Cancel", 0, total, self)
            progress.setWindowTitle("Export Images")
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
                    cv2.imwrite(str(out_path / f"{stem}_raw.png"), raw)
                    records_dicts = entry.get("measurements", [])
                    records = []
                    for m_dict in records_dicts:
                        try:
                            records.append(MeasurementRecord.from_dict(m_dict))
                        except Exception:
                            pass
                    cuts = records_to_legacy_cuts(records)
                    if cuts:
                        annotated = draw_overlays(raw, None, cuts)
                    else:
                        annotated = cv2.cvtColor(raw, cv2.COLOR_GRAY2BGR)
                    cv2.imwrite(str(out_path / f"{stem}_annotated.png"), annotated)
                    exported += 1
                except Exception:
                    errors += 1

            progress.setValue(total)
            msg = f"Exported {exported} image pair(s) to {out_path.name}"
            if errors:
                msg += f"  ({errors} skipped)"
            self.status_message.emit(msg)
            QMessageBox.information(self, "Done", msg)
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))


# ── helpers ───────────────────────────────────────────────────────────────────

def _clear_form(layout) -> None:
    for i in reversed(range(layout.count())):
        item = layout.itemAt(i)
        if item and item.widget():
            item.widget().deleteLater()
