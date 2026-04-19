"""Main application window — workspace-based UI (Phase A)."""
from __future__ import annotations

from PyQt6.QtWidgets import QMainWindow, QStatusBar, QFileDialog
from PyQt6.QtGui import QAction

from .workspace_host import WorkspaceHost
from .styles import STYLE


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SEM MM — Massive Measurement")
        self.resize(1400, 860)
        self.setMinimumSize(900, 600)
        self.setStyleSheet(STYLE)

        self._host = WorkspaceHost()
        self.setCentralWidget(self._host)

        sb = QStatusBar()
        self.setStatusBar(sb)
        sb.showMessage("Ready — open a folder in Browse to begin.")
        self._host.status_message.connect(sb.showMessage)

        self._build_menubar()

    def _build_menubar(self) -> None:
        mb = self.menuBar()

        fm = mb.addMenu("&File")
        act_open = QAction("Open Folder…  Ctrl+O", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._open_folder)
        fm.addAction(act_open)
        fm.addSeparator()
        fm.addAction(QAction("Quit  Ctrl+Q", self, shortcut="Ctrl+Q", triggered=self.close))

        rm = mb.addMenu("&Run")
        act_measure = QAction("Go to Measure  F5", self)
        act_measure.setShortcut("F5")
        act_measure.triggered.connect(self._host.switch_to_measure)
        rm.addAction(act_measure)
        act_batch = QAction("Go to Batch  F6", self)
        act_batch.setShortcut("F6")
        act_batch.triggered.connect(self._host.switch_to_batch)
        rm.addAction(act_batch)

        vm = mb.addMenu("&View")
        act_fs = QAction("Toggle Full Screen  F11", self)
        act_fs.setShortcut("F11")
        act_fs.triggered.connect(self._toggle_fullscreen)
        vm.addAction(act_fs)

    def _open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select SEM Image Folder")
        if folder:
            self._host.open_folder(folder)

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
