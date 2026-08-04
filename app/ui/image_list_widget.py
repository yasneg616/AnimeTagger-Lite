"""Image queue list with stable IDs, status text, icons, and file drops."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QIcon, QImage, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from app.state.image_item import ImageItem, ImageStatus


STATUS_LABELS = {
    ImageStatus.PENDING: "等待",
    ImageStatus.LOADING: "加载中",
    ImageStatus.ANALYZING: "识别中",
    ImageStatus.COMPLETED: "完成",
    ImageStatus.FAILED: "失败",
    ImageStatus.CANCELLED: "已取消",
}
STATUS_COLORS = {
    ImageStatus.PENDING: QColor("#aeb6c2"),
    ImageStatus.LOADING: QColor("#66b3ff"),
    ImageStatus.ANALYZING: QColor("#66b3ff"),
    ImageStatus.COMPLETED: QColor("#64d98b"),
    ImageStatus.FAILED: QColor("#ff7373"),
    ImageStatus.CANCELLED: QColor("#d0a85c"),
}


class ImageListWidget(QListWidget):
    paths_dropped = Signal(object)

    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("imageList")
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setIconSize(QSize(80, 80))
        self.setSpacing(4)
        self.setAlternatingRowColors(True)

    def add_image_item(self, image: ImageItem) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, image.id)
        item.setSizeHint(QSize(210, 88))
        self.addItem(item)
        self.update_image_item(image)

    def update_image_item(self, image: ImageItem) -> None:
        item = self.find_by_id(image.id)
        if item is None:
            return
        label = STATUS_LABELS[image.status]
        item.setText(f"{image.display_name}\n{label}")
        item.setForeground(STATUS_COLORS[image.status])
        tooltip = str(image.source_path)
        if image.error_message:
            tooltip += f"\n{image.error_message}"
        item.setToolTip(tooltip)

    def set_thumbnail(self, image_id: str, image: QImage) -> None:
        item = self.find_by_id(image_id)
        if item is not None and not image.isNull():
            item.setIcon(QIcon(QPixmap.fromImage(image)))

    def set_thumbnail_placeholder(self, image_id: str) -> None:
        item = self.find_by_id(image_id)
        if item is not None:
            placeholder = QPixmap(self.iconSize())
            placeholder.fill(QColor("#30343b"))
            item.setIcon(QIcon(placeholder))

    def find_by_id(self, image_id: str) -> QListWidgetItem | None:
        for row in range(self.count()):
            item = self.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == image_id:
                return item
        return None

    def current_image_id(self) -> str | None:
        item = self.currentItem()
        if item is None:
            return None
        return str(item.data(Qt.ItemDataRole.UserRole))

    def selected_image_ids(self) -> tuple[str, ...]:
        return tuple(
            str(item.data(Qt.ItemDataRole.UserRole))
            for item in self.selectedItems()
        )

    def remove_image_ids(self, image_ids: tuple[str, ...] | list[str]) -> None:
        wanted = set(image_ids)
        for row in range(self.count() - 1, -1, -1):
            item = self.item(row)
            if str(item.data(Qt.ItemDataRole.UserRole)) in wanted:
                self.takeItem(row)

    def select_image_id(self, image_id: str) -> bool:
        item = self.find_by_id(image_id)
        if item is None:
            return False
        self.setCurrentItem(item)
        return True

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: object) -> None:
        mime = event.mimeData()  # type: ignore[attr-defined]
        if mime.hasUrls():
            event.acceptProposedAction()  # type: ignore[attr-defined]
        else:
            event.ignore()  # type: ignore[attr-defined]

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        if paths:
            self.paths_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

