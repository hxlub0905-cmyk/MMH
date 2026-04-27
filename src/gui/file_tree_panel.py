"""Left-panel file tree filtered to supported SEM image extensions."""

from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QAbstractItemView
from PyQt6.QtCore import Qt, pyqtSignal
from ..core.image_loader import SUPPORTED_EXTENSIONS


class FileTreePanel(QTreeWidget):
    file_selected = pyqtSignal(Path)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._root: Path | None = None
        self.setHeaderLabel("Files")
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAnimated(True)
        self.itemClicked.connect(self._on_click)

    def set_root(self, folder: str | Path) -> None:
        self.clear()
        self._root = Path(folder)
        self._populate(self.invisibleRootItem(), self._root)
        self.expandAll()

    def root_path(self) -> Path | None:
        return self._root

    def _populate(self, parent: QTreeWidgetItem, folder: Path) -> None:
        try:
            entries = sorted(folder.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            return
        for entry in entries:
            if entry.is_dir():
                dir_item = QTreeWidgetItem(parent, [entry.name])
                dir_item.setData(0, Qt.ItemDataRole.UserRole, entry)
                self._populate(dir_item, entry)
            elif entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
                file_item = QTreeWidgetItem(parent, [entry.name])
                file_item.setData(0, Qt.ItemDataRole.UserRole, entry)

    def _on_click(self, item: QTreeWidgetItem, _col: int) -> None:
        path: Path | None = item.data(0, Qt.ItemDataRole.UserRole)
        if path and path.is_file():
            self.file_selected.emit(path)
