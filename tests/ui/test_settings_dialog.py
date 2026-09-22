from __future__ import annotations

from pathlib import Path

from app.config.settings import AppSettings
from app.inference.providers import CPU_PROVIDER, Device
from app.services.tagging_service import (
    ModelValidationResult,
    ModelValidationState,
)
from app.ui.settings_dialog import SettingsDialog


def valid_result(path: str, device: Device) -> ModelValidationResult:
    return ModelValidationResult(
        ModelValidationState.VALID,
        "模型目录基础验证通过",
        directory=Path(path),
        tag_count=123,
        requested_device=device,
        expected_provider=CPU_PROVIDER,
    )


def invalid_result(path: str, device: Device) -> ModelValidationResult:
    return ModelValidationResult(
        ModelValidationState.INVALID,
        "缺少 model.onnx",
        directory=Path(path),
        requested_device=device,
    )


def test_settings_dialog_validates_on_creation(qtbot, tmp_path: Path) -> None:
    dialog = SettingsDialog(
        AppSettings(model_dir=str(tmp_path)),
        valid_result,
    )
    qtbot.addWidget(dialog)
    assert dialog.validation_result is not None
    assert dialog.validation_result.valid
    assert "基础验证通过" in dialog.validation_label.text()
    assert dialog.profile_combo.findData("krea2") >= 0
    assert dialog.profile_combo.findData("cyberillustrious_semireal") >= 0


def test_settings_dialog_selects_cpu_device(qtbot, tmp_path: Path) -> None:
    dialog = SettingsDialog(
        AppSettings(model_dir=str(tmp_path), device="cpu"),
        valid_result,
    )
    qtbot.addWidget(dialog)
    assert dialog.selected_device() is Device.CPU


def test_settings_dialog_builds_typed_settings(qtbot, tmp_path: Path) -> None:
    dialog = SettingsDialog(
        AppSettings(model_dir=str(tmp_path)),
        valid_result,
    )
    qtbot.addWidget(dialog)
    dialog.general_spin.setValue(0.42)
    dialog.profile_combo.setCurrentIndex(
        dialog.profile_combo.findData("anime")
    )
    dialog._accept_if_valid()
    assert dialog.result() == SettingsDialog.DialogCode.Accepted
    assert dialog.settings.general_threshold == 0.42
    assert dialog.settings.profile == "anime"


def test_settings_dialog_empty_model_path_is_allowed(qtbot) -> None:
    def unconfigured(path: str, device: Device) -> ModelValidationResult:
        return ModelValidationResult(
            ModelValidationState.UNCONFIGURED,
            "尚未配置模型目录。",
            requested_device=device,
        )

    dialog = SettingsDialog(AppSettings(model_dir=""), unconfigured)
    qtbot.addWidget(dialog)
    dialog._accept_if_valid()
    assert dialog.result() == SettingsDialog.DialogCode.Accepted
    assert dialog.settings.model_dir == ""


def test_settings_dialog_invalid_result_is_explicit(qtbot, tmp_path: Path) -> None:
    dialog = SettingsDialog(
        AppSettings(model_dir=str(tmp_path)),
        invalid_result,
    )
    qtbot.addWidget(dialog)
    assert not dialog.validation_result.valid
    assert "model.onnx" in dialog.validation_label.text()
