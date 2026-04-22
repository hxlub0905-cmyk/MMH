"""WorkspaceHost — QTabWidget that hosts all 6 workspaces and acts as signal bus."""
from __future__ import annotations

from PyQt6.QtWidgets import QTabWidget, QWidget
from PyQt6.QtCore import pyqtSignal

from .workspaces.browse_workspace      import BrowseWorkspace
from .workspaces.recipe_workspace      import RecipeWorkspace
from .workspaces.measure_workspace     import MeasureWorkspace
from .workspaces.review_workspace      import ReviewWorkspace
from .workspaces.batch_workspace       import BatchWorkspace
from .workspaces.report_workspace      import ReportWorkspace
from .workspaces.history_workspace     import HistoryWorkspace
from ..core.recipe_registry    import RecipeRegistry
from ..core.calibration        import CalibrationManager
from ..core.measurement_engine import MeasurementEngine
from ..core.batch_run_store    import BatchRunStore


class WorkspaceHost(QTabWidget):
    """Owns shared services (registry, calibration, engine) and routes signals."""

    status_message = pyqtSignal(str)

    TAB_BROWSE   = 0
    TAB_RECIPE   = 1
    TAB_MEASURE  = 2
    TAB_BATCH    = 3
    TAB_REVIEW   = 4
    TAB_REPORT   = 5
    TAB_HISTORY  = 6

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        # Shared services
        self._registry    = RecipeRegistry()
        self._cal_manager = CalibrationManager()
        self._engine      = MeasurementEngine(self._registry)
        self._run_store   = BatchRunStore()

        # Workspaces
        self._browse    = BrowseWorkspace(self._cal_manager)
        self._recipe    = RecipeWorkspace(self._registry)
        self._measure   = MeasureWorkspace(self._engine, self._registry, self._cal_manager)
        self._review    = ReviewWorkspace()
        self._batch     = BatchWorkspace(self._engine, self._registry, self._cal_manager,
                                         run_store=self._run_store)
        self._report    = ReportWorkspace(run_store=self._run_store)
        self._history   = HistoryWorkspace(self._run_store)

        self.addTab(self._browse,   "Browse")
        self.addTab(self._recipe,   "Recipe")
        self.addTab(self._measure,  "Measure")
        self.addTab(self._batch,    "Batch")
        self.addTab(self._review,   "Review")
        self.addTab(self._report,   "Report")
        self.addTab(self._history,  "History")

        self._connect_signals()

    def _connect_signals(self) -> None:
        # Browse → Measure
        self._browse.image_selected.connect(self._measure.set_image_record)
        self._browse.image_selected.connect(
            lambda _: self.setCurrentIndex(self.TAB_MEASURE)
        )

        # Measure → Review
        self._measure.run_completed.connect(self._review.load_result)
        self._measure.run_completed.connect(
            lambda _: self.setCurrentIndex(self.TAB_REVIEW)
        )

        # Single-batch → Review + Report; navigate to Review
        self._batch.batch_completed.connect(self._review.load_batch_run)
        self._batch.batch_completed.connect(self._report.load_batch_run)
        self._batch.batch_completed.connect(
            lambda _: self.setCurrentIndex(self.TAB_REVIEW)
        )

        # Multi-batch → Review + Report; navigate to Report (comparison view)
        self._batch.multi_batch_completed.connect(self._review.load_multi_batch)
        self._batch.multi_batch_completed.connect(self._report.load_multi_batch)
        self._batch.multi_batch_completed.connect(
            lambda _: self.setCurrentIndex(self.TAB_REPORT)
        )

        # Recipe changes → refresh selectors
        self._recipe.recipe_saved.connect(self._measure.refresh_recipe_selector)
        self._recipe.recipe_saved.connect(self._batch.refresh_recipe_selector)
        self._measure.recipe_saved.connect(self._batch.refresh_recipe_selector)
        self._measure.recipe_saved.connect(lambda _: self._recipe.refresh_from_registry())

        # History → load in Report
        self._history.load_requested.connect(self._report.load_from_file)
        self._history.load_requested.connect(
            lambda _: self.setCurrentIndex(self.TAB_REPORT)
        )

        # Bubble status messages up to MainWindow status bar
        for ws in (self._browse, self._recipe, self._measure,
                   self._review, self._batch, self._report, self._history):
            ws.status_message.connect(self.status_message)

    # ── Public helpers (called by MainWindow menu actions) ────────────────────

    def open_folder(self, path: str) -> None:
        from pathlib import Path
        self._browse.set_root(Path(path))
        self.setCurrentIndex(self.TAB_BROWSE)

    def switch_to_measure(self) -> None:
        self.setCurrentIndex(self.TAB_MEASURE)

    def switch_to_batch(self) -> None:
        self.setCurrentIndex(self.TAB_BATCH)

    def switch_to_report(self) -> None:
        self.setCurrentIndex(self.TAB_REPORT)
