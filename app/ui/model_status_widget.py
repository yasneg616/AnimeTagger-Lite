"""Compact model state and controls shown in the main window."""

from __future__ import annotations

from enum import Enum

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.inference.wd14_engine import ModelInfo
from app.services.tagging_service import ModelValidationResult


class ModelUiState(str, Enum):
    UNCONFIGURED = "unconfigured"
    VALIDATED = "validated"
    LOADING = "loading"
    LOADED = "loaded"
    FAILED = "failed"
    RELEASED = "released"


class ModelStatusWidget(QWidget):
    validate_requested = Signal()
    load_requested = Signal()
    unload_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("modelStatusWidget")
        self.state = ModelUiState.UNCONFIGURED
        self._status = QLabel("模型：尚未配置")
        self._status.setObjectName("modelStatusLabel")
        self._status.setWordWrap(True)
        self._provider = QLabel("Provider：—")
        self._provider.setObjectName("providerStatusLabel")
        self._provider.setWordWrap(True)

        self.validate_button = QPushButton("验证模型")
        self.load_button = QPushButton("加载模型")
        self.unload_button = QPushButton("释放模型")
        self.validate_button.clicked.connect(self.validate_requested)
        self.load_button.clicked.connect(self.load_requested)
        self.unload_button.clicked.connect(self.unload_requested)
        self.load_button.setEnabled(False)
        self.unload_button.setEnabled(False)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.addWidget(self.validate_button)
        buttons.addWidget(self.load_button)
        buttons.addWidget(self.unload_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.addWidget(self._status)
        layout.addWidget(self._provider)
        layout.addLayout(buttons)

    @property
    def status_text(self) -> str:
        return self._status.text()

    @property
    def provider_text(self) -> str:
        return self._provider.text()

    def set_validation(self, result: ModelValidationResult) -> None:
        if result.valid:
            self.state = ModelUiState.VALIDATED
            self._status.setText(
                f"模型：已验证（{result.tag_count or 0} 个标签）"
            )
            provider = result.expected_provider or "未知"
            if result.provider_warning:
                self._provider.setText(
                    f"预计 Provider：{provider}；{result.provider_warning}"
                )
            else:
                self._provider.setText(f"预计 Provider：{provider}")
            self.load_button.setEnabled(True)
        else:
            self.state = ModelUiState.UNCONFIGURED
            self._status.setText(f"模型：{result.message}")
            self._provider.setText("Provider：—")
            self.load_button.setEnabled(False)
        self.unload_button.setEnabled(False)

    def set_loading(self) -> None:
        self.state = ModelUiState.LOADING
        self._status.setText("模型：正在加载并验证…")
        self.load_button.setEnabled(False)
        self.validate_button.setEnabled(False)

    def set_loaded(self, info: ModelInfo) -> None:
        self.state = ModelUiState.LOADED
        self._status.setText(
            f"模型：已加载（输入 {info.input_size}×{info.input_size}，"
            f"{info.output_count} 个标签）"
        )
        provider_text = info.active_provider
        if info.provider_warning:
            provider_text = f"{info.provider_warning} 当前使用 {info.active_provider}"
        self._provider.setText(f"Provider：{provider_text}")
        self.validate_button.setEnabled(True)
        self.load_button.setEnabled(True)
        self.unload_button.setEnabled(True)

    def set_failed(self, message: str, *, still_loaded: bool = False) -> None:
        self.state = ModelUiState.LOADED if still_loaded else ModelUiState.FAILED
        prefix = "新模型加载失败，原模型仍可用" if still_loaded else "加载失败"
        self._status.setText(f"模型：{prefix}（{message}）")
        self.validate_button.setEnabled(True)
        self.load_button.setEnabled(True)
        self.unload_button.setEnabled(still_loaded)

    def set_released(self) -> None:
        self.state = ModelUiState.RELEASED
        self._status.setText("模型：已释放")
        self._provider.setText("Provider：—")
        self.validate_button.setEnabled(True)
        self.load_button.setEnabled(True)
        self.unload_button.setEnabled(False)

