"""Typed application service joining inference, prompts, and export."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import threading
from typing import Callable

from app.config.presets import NegativePresetCatalog, PromptProfileCatalog
from app.config.settings import AppSettings, PROJECT_ROOT
from app.errors import AnimeTaggerError, ModelLoadError
from app.export_service import ExportFormat, ExportService
from app.image.image_loader import ImageLoadOptions, parse_background_color
from app.inference.model_loader import (
    ModelFiles,
    load_selected_tags,
    resolve_model_files,
)
from app.inference.providers import Device, select_execution_providers
from app.inference.backends import create_backend, resolve_backend_files, load_backend_tags, DEFAULT_BACKEND
from app.inference.wd14_engine import InferenceResult, ModelInfo, WD14Engine
from app.prompts.models import PromptBuildResult, TagResult
from app.prompts.pipeline import PromptProcessor, tag_results_from_predictions
from app.prompts.tag_classifier import TagClassifier

EngineFactory = Callable[..., WD14Engine]


class ModelValidationState(str, Enum):
    UNCONFIGURED = "unconfigured"
    INVALID = "invalid"
    VALID = "valid"


@dataclass(frozen=True, slots=True)
class ModelValidationResult:
    state: ModelValidationState
    message: str
    directory: Path | None = None
    files: ModelFiles | None = None
    tag_count: int | None = None
    requested_device: Device = Device.AUTO
    expected_provider: str | None = None
    provider_warning: str | None = None

    @property
    def valid(self) -> bool:
        return self.state is ModelValidationState.VALID


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    inference: InferenceResult
    raw_tags: tuple[TagResult, ...]
    prompts: PromptBuildResult


def resolve_model_directory(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve(strict=False)


class TaggingService:
    """Own one replaceable model session and the shared prompt pipeline."""

    def __init__(
        self,
        *,
        resource_dir: Path | None = None,
        engine_factory: EngineFactory = WD14Engine,
        exporter: ExportService | None = None,
    ) -> None:
        resources = (
            Path(resource_dir)
            if resource_dir is not None
            else PROJECT_ROOT / "resources"
        )
        self._processor = PromptProcessor(
            TagClassifier.from_json(resources / "tag_categories.json"),
            PromptProfileCatalog.from_json(resources / "prompt_profiles.json"),
            NegativePresetCatalog.from_json(resources / "negative_presets.json"),
        )
        self._engine_factory = engine_factory
        self._exporter = exporter or ExportService()
        self._engine: WD14Engine | None = None
        self._model_dir: Path | None = None
        self._device: Device | None = None
        self._backend: str | None = None
        self._engine_lock = threading.RLock()

    @property
    def is_model_loaded(self) -> bool:
        with self._engine_lock:
            return self._engine is not None and self._engine.is_loaded

    @property
    def loaded_backend(self) -> str | None:
        with self._engine_lock:
            return self._backend

    @property
    def model_info(self) -> ModelInfo | None:
        with self._engine_lock:
            return self._engine.model_info if self._engine is not None else None

    def validate_model_directory(
        self,
        model_dir: str | Path,
        device: Device = Device.AUTO,
        backend: str = "wd_v3",
    ) -> ModelValidationResult:
        """Perform a lightweight validation without constructing a session.

        ONNX readability, tensor shape, and output/CSV alignment are verified by
        :meth:`load_model`, because those checks require opening the full model.
        """

        if not str(model_dir).strip():
            return ModelValidationResult(
                ModelValidationState.UNCONFIGURED,
                "尚未配置模型目录。",
                requested_device=device,
            )
        directory = resolve_model_directory(model_dir)
        try:
            files = resolve_backend_files(directory, backend)
            tags = load_backend_tags(files.tags_path, backend)
            if backend == DEFAULT_BACKEND:
                import importlib.util
                if any(importlib.util.find_spec(name) is None for name in ("torch", "timm", "safetensors")):
                    raise ModelLoadError("Canary 缺少可选依赖，请安装 requirements-tagger-torch.txt。")
                return ModelValidationResult(ModelValidationState.VALID,
                    "Canary 文件验证通过；权重和 PyTorch 设备将在加载时完整验证。",
                    directory=directory, files=files, tag_count=len(tags), requested_device=device)
            try:
                import onnxruntime
            except ImportError as exc:
                raise ModelLoadError(
                    "未安装 ONNX Runtime，无法加载模型。"
                ) from exc
            selection = select_execution_providers(
                device,
                onnxruntime.get_available_providers(),
            )
        except AnimeTaggerError as exc:
            return ModelValidationResult(
                ModelValidationState.INVALID,
                str(exc),
                directory=directory,
                requested_device=device,
            )
        return ModelValidationResult(
            ModelValidationState.VALID,
            "模型目录基础验证通过；ONNX 结构将在加载时完整验证。",
            directory=directory,
            files=files,
            tag_count=len(tags),
            requested_device=device,
            expected_provider=selection.primary_provider,
            provider_warning=selection.warning,
        )

    def load_model(
        self,
        model_dir: str | Path,
        device: Device = Device.AUTO,
        backend: str = "wd_v3",
    ) -> ModelInfo:
        """Fully validate a candidate, then atomically replace the old engine."""

        directory = resolve_model_directory(model_dir)
        candidate = (create_backend(backend, directory, device=device)
                     if self._engine_factory is WD14Engine
                     else self._engine_factory(directory, device=device))
        try:
            info = candidate.load()
        except Exception:
            candidate.release()
            raise

        with self._engine_lock:
            previous = self._engine
            self._engine = candidate
            self._model_dir = directory
            self._device = device
            self._backend = backend
        if previous is not None and previous is not candidate:
            previous.release()
        return info

    def unload_model(self) -> None:
        with self._engine_lock:
            engine = self._engine
            self._engine = None
            self._model_dir = None
            self._device = None
            self._backend = None
        if engine is not None:
            engine.release()

    def analyze_image(
        self,
        image_path: Path,
        settings: AppSettings,
    ) -> AnalysisResult:
        try:
            background = parse_background_color(settings.background)
        except ValueError as exc:
            raise ModelLoadError(f"背景色配置无效：{exc}") from exc
        with self._engine_lock:
            if self._engine is None or not self._engine.is_loaded:
                raise ModelLoadError("模型尚未加载，请先在设置中验证并加载模型。")
            if self._engine_factory is WD14Engine and settings.backend != self._backend:
                raise ModelLoadError("所选后端与当前加载模型不同，请点击“加载模型”完成切换后再识别。")
            inference = self._engine.predict(
                Path(image_path),
                image_options=ImageLoadOptions(background=background),
            )
        raw_tags = tag_results_from_predictions(inference.predictions)
        prompts = self.rebuild_prompts(raw_tags, settings)
        return AnalysisResult(inference, raw_tags, prompts)

    def rebuild_prompts(
        self,
        tags: tuple[TagResult, ...] | list[TagResult],
        settings: AppSettings,
    ) -> PromptBuildResult:
        return self._processor.build(tuple(tags), settings)

    def export_result(
        self,
        output_format: ExportFormat,
        output_path: Path,
        prompts: PromptBuildResult,
        inference: InferenceResult,
        *,
        overwrite: bool = False,
        final_positive_prompt: str | None = None,
        final_negative_prompt: str | None = None,
        prompt_was_edited: bool | None = None,
        model_raw_tags: tuple[TagResult, ...] | None = None,
        working_tags: tuple[TagResult, ...] | list[TagResult] | None = None,
    ) -> Path:
        return self._exporter.export(
            output_format,
            output_path,
            prompts,
            inference,
            overwrite=overwrite,
            final_positive_prompt=final_positive_prompt,
            final_negative_prompt=final_negative_prompt,
            prompt_was_edited=prompt_was_edited,
            model_raw_tags=model_raw_tags,
            working_tags=working_tags,
        )
