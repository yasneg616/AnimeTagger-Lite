from __future__ import annotations

from pathlib import Path

import pytest

from app.config.settings import AppSettings
from app.export_service import ExportFormat
from app.inference.model_loader import ModelFiles, TagCategory, TagMetadata
from app.inference.providers import CPU_PROVIDER, Device
from app.inference.wd14_engine import (
    InferenceResult,
    ModelInfo,
    TagPrediction,
)
from app.services.tagging_service import (
    ModelValidationState,
    TaggingService,
)


def model_info(path: Path) -> ModelInfo:
    files = ModelFiles(path, path / "model.onnx", path / "selected_tags.csv")
    return ModelInfo(
        files=files,
        input_name="input",
        output_name="output",
        input_size=448,
        output_count=1,
        active_provider=CPU_PROVIDER,
        provider_warning=None,
    )


class FakeEngine:
    def __init__(
        self,
        model_dir: Path,
        *,
        device: Device,
        fail: bool = False,
    ) -> None:
        self.path = Path(model_dir)
        self.device = device
        self.fail = fail
        self._info: ModelInfo | None = None
        self.released = False

    @property
    def is_loaded(self) -> bool:
        return self._info is not None

    @property
    def model_info(self) -> ModelInfo | None:
        return self._info

    def load(self) -> ModelInfo:
        if self.fail:
            raise RuntimeError("bad candidate")
        self._info = model_info(self.path)
        return self._info

    def predict(self, path: Path, **_kwargs: object) -> InferenceResult:
        assert self._info is not None
        metadata = TagMetadata(0, 0, "1girl", 0, TagCategory.GENERAL)
        return InferenceResult(
            Path(path),
            self._info,
            (TagPrediction(metadata, 0.98),),
            0.01,
        )

    def release(self) -> None:
        self.released = True
        self._info = None


def test_validate_unconfigured_model_directory() -> None:
    result = TaggingService().validate_model_directory("")
    assert result.state is ModelValidationState.UNCONFIGURED
    assert "尚未配置" in result.message


def test_validate_missing_model_directory_names_missing_files(
    tmp_path: Path,
) -> None:
    result = TaggingService().validate_model_directory(tmp_path)
    assert result.state is ModelValidationState.INVALID
    assert "model.onnx" in result.message
    assert "selected_tags.csv" in result.message


def test_lightweight_validation_reads_csv_without_loading_onnx(
    tmp_path: Path,
) -> None:
    (tmp_path / "model.onnx").write_bytes(b"placeholder")
    (tmp_path / "selected_tags.csv").write_text(
        "tag_id,name,category\n0,1girl,0\n",
        encoding="utf-8",
    )
    result = TaggingService().validate_model_directory(tmp_path, Device.CPU)
    assert result.valid
    assert result.tag_count == 1
    assert "加载时完整验证" in result.message


def test_service_load_analyze_and_unload_with_fake_engine(
    tmp_path: Path,
) -> None:
    service = TaggingService(
        engine_factory=lambda path, device: FakeEngine(path, device=device)  # type: ignore[arg-type]
    )
    service.load_model(tmp_path, Device.CPU)
    result = service.analyze_image(tmp_path / "image.png", AppSettings())
    assert result.prompts.positive_prompt == "1girl"
    assert result.raw_tags[0].confidence == pytest.approx(0.98)
    service.unload_model()
    assert not service.is_model_loaded


def test_failed_candidate_does_not_destroy_loaded_session(tmp_path: Path) -> None:
    engines: list[FakeEngine] = []

    def factory(path: Path, device: Device) -> FakeEngine:
        engine = FakeEngine(path, device=device, fail=path.name == "bad")
        engines.append(engine)
        return engine

    service = TaggingService(engine_factory=factory)  # type: ignore[arg-type]
    service.load_model(tmp_path / "good", Device.CPU)
    with pytest.raises(RuntimeError, match="bad candidate"):
        service.load_model(tmp_path / "bad", Device.CPU)
    assert service.is_model_loaded
    assert not engines[0].released
    assert engines[1].released


def test_service_export_uses_final_manually_edited_prompt(
    tmp_path: Path,
) -> None:
    engine = FakeEngine(tmp_path / "model", device=Device.CPU)
    service = TaggingService(engine_factory=lambda *_args, **_kwargs: engine)
    service.load_model(tmp_path / "model", Device.CPU)
    analysis = service.analyze_image(tmp_path / "image.png", AppSettings())
    output = tmp_path / "result.json"
    service.export_result(
        ExportFormat.JSON,
        output,
        analysis.prompts,
        analysis.inference,
        final_positive_prompt="manual final",
        final_negative_prompt="manual negative",
        prompt_was_edited=True,
    )
    text = output.read_text(encoding="utf-8")
    assert '"schema_version": 2' in text
    assert '"generated_positive_prompt": "1girl"' in text
    assert '"final_positive_prompt": "manual final"' in text
    assert '"prompt_was_edited": true' in text
