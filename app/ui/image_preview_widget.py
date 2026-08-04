"""Read-only image preview with fit and deterministic zoom controls."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class ImagePreviewWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("imagePreview")
        self._pixmap = QPixmap()
        self._scale = 1.0
        self._fit_mode = True

        self._label = QLabel("请选择图片")
        self._label.setObjectName("previewLabel")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setMinimumSize(160, 160)

        self._scroll = QScrollArea()
        self._scroll.setWidget(self._label)
        self._scroll.setWidgetResizable(True)
        self._scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        controls = QHBoxLayout()
        for text, tooltip, handler in (
            ("适应", "缩放以适应预览区域", self.fit_to_window),
            ("1:1", "按预览像素原始大小显示", self.actual_size),
            ("＋", "放大", self.zoom_in),
            ("－", "缩小", self.zoom_out),
            ("复位", "恢复适应窗口", self.fit_to_window),
        ):
            button = QPushButton(text)
            button.setToolTip(tooltip)
            button.clicked.connect(handler)
            controls.addWidget(button)
        controls.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addWidget(self._scroll, 1)

    @property
    def has_image(self) -> bool:
        return not self._pixmap.isNull()

    @property
    def scale_factor(self) -> float:
        return self._scale

    def set_loading(self) -> None:
        self._pixmap = QPixmap()
        self._label.clear()
        self._label.setText("正在加载预览…")

    def set_error(self, message: str) -> None:
        self._pixmap = QPixmap()
        self._label.clear()
        self._label.setText(f"无法显示预览\n{message}")

    def clear(self) -> None:
        self._pixmap = QPixmap()
        self._label.clear()
        self._label.setText("请选择图片")

    def set_image(self, image: QImage) -> None:
        self._pixmap = QPixmap.fromImage(image)
        self._scale = 1.0
        self._fit_mode = True
        self._render()

    def fit_to_window(self) -> None:
        self._fit_mode = True
        self._render()

    def actual_size(self) -> None:
        self._fit_mode = False
        self._scale = 1.0
        self._render()

    def zoom_in(self) -> None:
        self._fit_mode = False
        self._scale = min(8.0, self._scale * 1.25)
        self._render()

    def zoom_out(self) -> None:
        self._fit_mode = False
        self._scale = max(0.1, self._scale / 1.25)
        self._render()

    def _render(self) -> None:
        if self._pixmap.isNull():
            return
        if self._fit_mode:
            viewport = self._scroll.viewport().size()
            target = QSize(
                max(1, viewport.width() - 4),
                max(1, viewport.height() - 4),
            )
            rendered = self._pixmap.scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._label.setPixmap(rendered)
            self._label.resize(rendered.size())
            return
        size = self._pixmap.size() * self._scale
        rendered = self._pixmap.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._label.setPixmap(rendered)
        self._label.resize(rendered.size())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._fit_mode:
            self._render()
