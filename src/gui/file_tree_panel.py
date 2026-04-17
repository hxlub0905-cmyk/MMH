"""Left-panel file tree filtered to supported SEM image extensions."""

from __future__ import annotations
from pathlib import Path
from PyQt6.QtWidgets import QTreeView, QFileSystemModel, QAbstractItemView
from PyQt6.QtCore import Qt, QSortFilterProxyModel, QModelIndex, pyqtSignal
from ..core.image_loader import SUPPORTED_EXTENSIONS


class _ImageFilter(QSortFilterProxyModel):
    """Show only directories and supported image files."""

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        idx = model.index(source_row, 0, source_parent)
        if model.isDir(idx):
            return True
        name = model.fileName(idx)
        return Path(name).suffix.lower() in SUPPORTED_EXTENSIONS


class FileTreePanel(QTreeView):
    file_selected = pyqtSignal(Path)   # emitted when user clicks an image file

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fs_model = QFileSystemModel()
        self._fs_model.setRootPath("")

        self._proxy = _ImageFilter(self)
        self._proxy.setSourceModel(self._fs_model)

        self.setModel(self._proxy)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAnimated(False)
        self.setSortingEnabled(True)
        self.sortByColumn(0, Qt.SortOrder.AscendingOrder)

        # hide size / type / date columns
        for col in (1, 2, 3):
            self.setColumnHidden(col, True)

        self.selectionModel().currentChanged.connect(self._on_selection)

    def set_root(self, folder: str | Path) -> None:
        src_idx = self._fs_model.setRootPath(str(folder))
        proxy_idx = self._proxy.mapFromSource(src_idx)
        self.setRootIndex(proxy_idx)
        self.expand(proxy_idx)

    def _on_selection(self, proxy_idx: QModelIndex, _prev: QModelIndex) -> None:
        src_idx = self._proxy.mapToSource(proxy_idx)
        if not self._fs_model.isDir(src_idx):
            path = Path(self._fs_model.filePath(src_idx))
            self.file_selected.emit(path)
