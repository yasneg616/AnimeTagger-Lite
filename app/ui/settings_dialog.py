"""Business settings editor with lightweight model-directory validation."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import AppSettings
from app.inference.providers import Device
from app.services.tagging_service import ModelValidationResult

ValidationCallback = Callable[[str, Device], ModelValidationResult]


def _probability_spin(value: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0.0, 1.0)
    spin.setDecimals(2)
    spin.setSingleStep(0.05)
    spin.setValue(value)
    return spin


class SettingsDialog(QDialog):
    def __init__(
        self,
        settings: AppSettings,
        validate_model: ValidationCallback,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setModal(True)
        self.resize(620, 620)
        self._original = settings
        self._result_settings = settings
        self._validate_callback = validate_model
        self.validation_result: ModelValidationResult | None = None

        self.model_dir_edit = QLineEdit(settings.model_dir)
        self.model_dir_edit.setObjectName("modelDirEdit")
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_model)
        validate = QPushButton("验证")
        validate.clicked.connect(self.validate_now)
        model_row = QHBoxLayout()
        model_row.addWidget(self.model_dir_edit, 1)
        model_row.addWidget(browse)
        model_row.addWidget(validate)
        model_widget = QWidget()
        model_widget.setLayout(model_row)

        self.validation_label = QLabel("尚未验证")
        self.validation_label.setObjectName("settingsValidationLabel")
        self.validation_label.setWordWrap(True)

        self.device_combo = QComboBox()
        self.device_combo.setObjectName("deviceCombo")
        self.device_combo.addItem("自动（CUDA 优先，允许 CPU 回退）", "auto")
        self.device_combo.addItem("CPU", "cpu")
        self.device_combo.addItem("CUDA（不可用时显示回退）", "cuda")
        self.device_combo.setCurrentIndex(
            max(0, self.device_combo.findData(settings.device))
        )

        self.general_spin = _probability_spin(settings.general_threshold)
        self.character_spin = _probability_spin(settings.character_threshold)
        self.rating_spin = _probability_spin(settings.rating_threshold)
        self.minimum_spin = _probability_spin(settings.minimum_display_threshold)
        self.defect_spin = _probability_spin(settings.defect_threshold)
        self.max_tags_spin = QSpinBox()
        self.max_tags_spin.setRange(1, 10000)
        self.max_tags_spin.setValue(settings.max_tags)
        self.include_rating_check = QCheckBox()
        self.include_rating_check.setChecked(settings.include_rating)
        self.underscore_check = QCheckBox()
        self.underscore_check.setChecked(settings.underscore_to_space)
        self.parentheses_check = QCheckBox()
        self.parentheses_check.setChecked(settings.unescape_parentheses)

        self.profile_combo = QComboBox()
        for value in ("raw", "anime", "pony", "lora_caption"):
            self.profile_combo.addItem(value, value)
        self.profile_combo.setCurrentIndex(
            self.profile_combo.findData(settings.profile)
        )
        self.negative_mode_combo = QComboBox()
        for label, value in (
            ("无", "none"),
            ("基础预设", "basic"),
            ("检测缺陷并清理冲突", "cleanup_detected"),
        ):
            self.negative_mode_combo.addItem(label, value)
        self.negative_mode_combo.setCurrentIndex(
            self.negative_mode_combo.findData(settings.negative_mode)
        )
        self.negative_preset_edit = QLineEdit(settings.negative_preset)
        self.trigger_word_edit = QLineEdit(settings.trigger_word or "")

        self.export_format_combo = QComboBox()
        for label, value in (
            ("正向 TXT", "txt"),
            ("正负 TXT", "prompt-txt"),
            ("JSON", "json"),
        ):
            self.export_format_combo.addItem(label, value)
        self.export_format_combo.setCurrentIndex(
            self.export_format_combo.findData(settings.default_export_format)
        )
        self.export_dir_edit = QLineEdit(settings.default_export_dir)
        export_browse = QPushButton("浏览…")
        export_browse.clicked.connect(self._browse_export_dir)
        export_row = QHBoxLayout()
        export_row.addWidget(self.export_dir_edit, 1)
        export_row.addWidget(export_browse)
        export_widget = QWidget()
        export_widget.setLayout(export_row)

        self.show_low_check = QCheckBox()
        self.show_low_check.setChecked(settings.show_low_confidence)

        form = QFormLayout()
        form.addRow("模型目录", model_widget)
        form.addRow("", self.validation_label)
        form.addRow("设备模式", self.device_combo)
        form.addRow("General 阈值", self.general_spin)
        form.addRow("Character 阈值", self.character_spin)
        form.addRow("Rating 阈值", self.rating_spin)
        form.addRow("包含 Rating", self.include_rating_check)
        form.addRow("最大标签数", self.max_tags_spin)
        form.addRow("最低显示置信度", self.minimum_spin)
        form.addRow("下划线转空格", self.underscore_check)
        form.addRow("反转义括号", self.parentheses_check)
        form.addRow("Profile", self.profile_combo)
        form.addRow("反向模式", self.negative_mode_combo)
        form.addRow("反向预设", self.negative_preset_edit)
        form.addRow("缺陷阈值", self.defect_spin)
        form.addRow("Trigger word", self.trigger_word_edit)
        form.addRow("默认导出格式", self.export_format_combo)
        form.addRow("默认导出目录", export_widget)
        form.addRow("显示低置信度标签", self.show_low_check)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self._validation_timer = QTimer(self)
        self._validation_timer.setSingleShot(True)
        self._validation_timer.setInterval(250)
        self._validation_timer.timeout.connect(self.validate_now)
        self.model_dir_edit.textChanged.connect(
            lambda _text: self._validation_timer.start()
        )
        self.device_combo.currentIndexChanged.connect(
            lambda _index: self._validation_timer.start()
        )
        self.validate_now()

    @property
    def settings(self) -> AppSettings:
        return self._result_settings

    def selected_device(self) -> Device:
        return Device(str(self.device_combo.currentData()))

    def validate_now(self) -> ModelValidationResult:
        self._validation_timer.stop()
        result = self._validate_callback(
            self.model_dir_edit.text().strip(),
            self.selected_device(),
        )
        self.validation_result = result
        color = "#75d694" if result.valid else "#ef8585"
        if not self.model_dir_edit.text().strip():
            color = "#d8b76b"
        text = result.message
        if result.provider_warning:
            text += f"\n{result.provider_warning}"
        self.validation_label.setText(text)
        self.validation_label.setStyleSheet(f"color: {color};")
        return result

    def _browse_model(self) -> None:
        initial = self.model_dir_edit.text() or str(Path.cwd())
        selected = QFileDialog.getExistingDirectory(
            self,
            "选择 WD14 模型目录",
            initial,
        )
        if selected:
            self.model_dir_edit.setText(selected)

    def _browse_export_dir(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "选择默认导出目录",
            self.export_dir_edit.text() or str(Path.cwd()),
        )
        if selected:
            self.export_dir_edit.setText(selected)

    def _accept_if_valid(self) -> None:
        result = self.validate_now()
        model_dir = self.model_dir_edit.text().strip()
        if model_dir and not result.valid:
            QMessageBox.warning(
                self,
                "模型目录无效",
                f"{result.message}\n\n请修正路径或清空模型目录。",
            )
            return
        self._result_settings = replace(
            self._original,
            model_dir=model_dir,
            device=self.selected_device().value,
            general_threshold=self.general_spin.value(),
            character_threshold=self.character_spin.value(),
            rating_threshold=self.rating_spin.value(),
            include_rating=self.include_rating_check.isChecked(),
            max_tags=self.max_tags_spin.value(),
            minimum_display_threshold=self.minimum_spin.value(),
            underscore_to_space=self.underscore_check.isChecked(),
            unescape_parentheses=self.parentheses_check.isChecked(),
            profile=str(self.profile_combo.currentData()),
            negative_mode=str(self.negative_mode_combo.currentData()),
            negative_preset=self.negative_preset_edit.text().strip() or "basic",
            defect_threshold=self.defect_spin.value(),
            trigger_word=self.trigger_word_edit.text().strip() or None,
            default_export_format=str(
                self.export_format_combo.currentData()
            ),
            default_export_dir=self.export_dir_edit.text().strip(),
            show_low_confidence=self.show_low_check.isChecked(),
        )
        self.accept()
