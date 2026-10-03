"""Incremental table model for large batch jobs."""

from __future__ import annotations

from enum import IntEnum

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from app.batch.models import BatchItem, BatchJob


class BatchColumn(IntEnum):
    PROCESS = 0
    FILE = 1
    RELATIVE = 2
    FORMAT = 3
    SIZE = 4
    EXISTING = 5
    OUTPUT = 6
    STATUS = 7
    PROGRESS = 8
    ERROR = 9


_HEADERS = {
    BatchColumn.PROCESS: "处理",
    BatchColumn.FILE: "文件",
    BatchColumn.RELATIVE: "相对路径",
    BatchColumn.FORMAT: "格式",
    BatchColumn.SIZE: "大小",
    BatchColumn.EXISTING: "已有 TXT",
    BatchColumn.OUTPUT: "预计输出",
    BatchColumn.STATUS: "状态",
    BatchColumn.PROGRESS: "进度",
    BatchColumn.ERROR: "错误",
}


class BatchTableModel(QAbstractTableModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[BatchItem] = []
        self._rows: dict[str, int] = {}
        self._progress: dict[str, str] = {}

    def set_job(self, job: BatchJob | None) -> None:
        self.beginResetModel()
        self._items = list(job.items) if job is not None else []
        self._rows = {item.id: row for row, item in enumerate(self._items)}
        self._progress.clear()
        self.endResetModel()

    def update_item(
        self,
        item: BatchItem,
        position: int = 0,
        total: int = 0,
    ) -> None:
        row = self._rows.get(item.id)
        if row is None:
            return
        self._items[row] = item
        if position > 0 and total > 0:
            self._progress[item.id] = f"{position}/{total}"
        self.dataChanged.emit(
            self.index(row, 0),
            self.index(row, self.columnCount() - 1),
            [
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.ToolTipRole,
            ],
        )

    def item_at(self, row: int) -> BatchItem | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def set_all_selected(self, selected: bool) -> None:
        if not self._items:
            return
        for item in self._items:
            item.selected = selected
        self.dataChanged.emit(
            self.index(0, BatchColumn.PROCESS),
            self.index(len(self._items) - 1, BatchColumn.PROCESS),
            [Qt.ItemDataRole.CheckStateRole],
        )

    def invert_selected(self) -> None:
        if not self._items:
            return
        for item in self._items:
            item.selected = not item.selected
        self.dataChanged.emit(
            self.index(0, BatchColumn.PROCESS),
            self.index(len(self._items) - 1, BatchColumn.PROCESS),
            [Qt.ItemDataRole.CheckStateRole],
        )

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        flags = super().flags(index)
        if index.isValid() and index.column() == BatchColumn.PROCESS:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def setData(
        self,
        index: QModelIndex,
        value,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        if (
            index.isValid()
            and index.column() == BatchColumn.PROCESS
            and role == Qt.ItemDataRole.CheckStateRole
        ):
            item = self.item_at(index.row())
            if item is None:
                return False
            item.selected = value in (
                Qt.CheckState.Checked,
                Qt.CheckState.Checked.value,
            )
            self.dataChanged.emit(index, index, [role])
            return True
        return False

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(BatchColumn)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if (
            orientation is Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            try:
                return _HEADERS[BatchColumn(section)]
            except (ValueError, KeyError):
                return None
        return super().headerData(section, orientation, role)

    def data(
        self,
        index: QModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        try:
            column = BatchColumn(index.column())
        except ValueError:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            if column is BatchColumn.PROCESS:
                return ""
            if column is BatchColumn.FILE:
                return item.source_path.name
            if column is BatchColumn.RELATIVE:
                return item.relative_path.as_posix()
            if column is BatchColumn.FORMAT:
                return item.image_format
            if column is BatchColumn.SIZE:
                return (
                    ""
                    if item.file_size is None
                    else _human_size(item.file_size)
                )
            if column is BatchColumn.EXISTING:
                return (
                    "是"
                    if item.caption_path is not None
                    and item.caption_path.exists()
                    else "否"
                )
            if column is BatchColumn.OUTPUT:
                return str(item.caption_path or item.json_path or "")
            if column is BatchColumn.STATUS:
                return item.status.value
            if column is BatchColumn.PROGRESS:
                return self._progress.get(item.id, "")
            if column is BatchColumn.ERROR:
                return item.error_message
        if role == Qt.ItemDataRole.ToolTipRole:
            if column is BatchColumn.FILE:
                return str(item.source_path)
            if column is BatchColumn.OUTPUT:
                return str(item.caption_path or item.json_path or "")
            if column is BatchColumn.ERROR and item.error_message:
                return f"{item.error_type.value}: {item.error_message}"
        if role == Qt.ItemDataRole.UserRole:
            return item.id
        if (
            role == Qt.ItemDataRole.CheckStateRole
            and column is BatchColumn.PROCESS
        ):
            return (
                Qt.CheckState.Checked
                if item.selected
                else Qt.CheckState.Unchecked
            )
        return None


def _human_size(value: int) -> str:
    size = float(value)
    for suffix in ("B", "KiB", "MiB", "GiB"):
        if size < 1024.0 or suffix == "GiB":
            return f"{size:.0f} {suffix}" if suffix == "B" else f"{size:.1f} {suffix}"
        size /= 1024.0
    return f"{value} B"
