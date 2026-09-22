"""Lazy, single-model WD14 ONNX inference engine."""

from __future__ import annotations

from dataclasses import dataclass, replace
import numbers
from pathlib import Path
import time
from typing import Any, Iterable

import numpy as np

from app.errors import InferenceError, ModelLoadError
from app.image.image_loader import ImageLoadOptions, preprocess_image
from app.inference.model_loader import (
    ModelFiles,
    TagCategory,
    TagMetadata,
    load_selected_tags,
    resolve_model_files,
)
from app.inference.providers import (
    CPU_PROVIDER,
    CUDA_PROVIDER,
    Device,
    ProviderSelection,
    select_execution_providers,
)
from app.runtime_paths import bundled_nvidia_dll_directories


@dataclass(frozen=True, slots=True)
class ModelInfo:
    files: ModelFiles
    input_name: str
    output_name: str
    input_size: int
    output_count: int
    active_provider: str
    provider_warning: str | None
    backend: str = "wd_v3"


@dataclass(frozen=True, slots=True)
class TagPrediction:
    tag: TagMetadata
    confidence: float


@dataclass(frozen=True, slots=True)
class InferenceResult:
    image_path: Path
    model_info: ModelInfo
    predictions: tuple[TagPrediction, ...]
    inference_seconds: float

    @property
    def grouped(self) -> dict[str, tuple[TagPrediction, ...]]:
        """Unfiltered structured scores; unsupported groups remain empty."""
        groups = {category.value: tuple(p for p in self.predictions if p.tag.category is category)
                  for category in TagCategory}
        groups["raw"] = self.predictions
        return groups


def _clean_runtime_error(error: BaseException) -> str:
    text = " ".join(str(error).split())
    return text[:400] if text else error.__class__.__name__


def _positive_static_dimension(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise ModelLoadError(f"ONNX 模型的{label}不是固定整数：{value!r}")
    integer = int(value)
    if integer <= 0:
        raise ModelLoadError(f"ONNX 模型的{label}无效：{integer}")
    return integer


def _validate_tensor_type(node: Any, label: str) -> None:
    node_type = getattr(node, "type", None)
    if node_type is not None and node_type != "tensor(float)":
        raise ModelLoadError(
            f"ONNX 模型的{label}类型应为 tensor(float)，实际为 {node_type!r}"
        )


def _inspect_session(
    session: Any,
    tags: tuple[TagMetadata, ...],
) -> tuple[str, str, int, int]:
    inputs = session.get_inputs()
    outputs = session.get_outputs()
    if len(inputs) != 1:
        raise ModelLoadError(
            f"WD14 ONNX 应只有 1 个输入，当前检测到 {len(inputs)} 个。"
        )
    if len(outputs) != 1:
        raise ModelLoadError(
            f"WD14 ONNX 应只有 1 个输出，当前检测到 {len(outputs)} 个。"
        )

    input_node = inputs[0]
    output_node = outputs[0]
    _validate_tensor_type(input_node, "输入")
    _validate_tensor_type(output_node, "输出")

    input_shape = tuple(input_node.shape)
    if len(input_shape) != 4:
        raise ModelLoadError(
            f"WD14 ONNX 输入应为 NHWC 四维张量，实际形状：{input_shape!r}"
        )
    height = _positive_static_dimension(input_shape[1], "输入高度")
    width = _positive_static_dimension(input_shape[2], "输入宽度")
    channels = _positive_static_dimension(input_shape[3], "输入通道数")
    if height != width or channels != 3:
        raise ModelLoadError(
            "WD14 ONNX 输入应为 [N, S, S, 3]，"
            f"实际形状：{input_shape!r}"
        )

    output_shape = tuple(output_node.shape)
    if len(output_shape) != 2:
        raise ModelLoadError(
            f"WD14 ONNX 输出应为二维张量，实际形状：{output_shape!r}"
        )
    output_count = _positive_static_dimension(output_shape[1], "输出标签数")
    if output_count != len(tags):
        raise ModelLoadError(
            "标签数量和模型输出数量不一致："
            f"{len(tags)} 个 CSV 标签，{output_count} 个模型输出。"
        )

    return input_node.name, output_node.name, height, output_count


def group_predictions(
    predictions: Iterable[TagPrediction],
    *,
    general_threshold: float = 0.35,
    character_threshold: float = 0.75,
) -> dict[TagCategory, tuple[TagPrediction, ...]]:
    """Filter display rows by category-specific thresholds, then sort by score."""

    if not 0.0 <= general_threshold <= 1.0:
        raise ValueError("General 阈值必须位于 0 到 1。")
    if not 0.0 <= character_threshold <= 1.0:
        raise ValueError("Character 阈值必须位于 0 到 1。")

    grouped: dict[TagCategory, list[TagPrediction]] = {
        category: [] for category in TagCategory
    }
    for prediction in predictions:
        category = prediction.tag.category
        threshold = (
            character_threshold
            if category is TagCategory.CHARACTER
            else general_threshold
        )
        if category is TagCategory.RATING or prediction.confidence >= threshold:
            grouped[category].append(prediction)

    return {
        category: tuple(
            sorted(
                values,
                key=lambda item: (-item.confidence, item.tag.name.casefold()),
            )
        )
        for category, values in grouped.items()
    }


class WD14Engine:
    """One lazily initialized ONNX session reusable across image predictions."""

    def __init__(
        self,
        model_dir: Path,
        *,
        device: Device = Device.AUTO,
        runtime: Any | None = None,
    ) -> None:
        self._model_dir = Path(model_dir)
        self._device = device
        self._runtime = runtime
        self._session: Any | None = None
        self._tags: tuple[TagMetadata, ...] | None = None
        self._model_info: ModelInfo | None = None

    @property
    def is_loaded(self) -> bool:
        return self._session is not None

    @property
    def model_info(self) -> ModelInfo | None:
        return self._model_info

    def _get_runtime(self) -> Any:
        if self._runtime is not None:
            return self._runtime
        try:
            import onnxruntime
        except ImportError as exc:
            raise ModelLoadError(
                "未安装 ONNX Runtime。CPU 版请安装 requirements.txt；"
                "GPU 版请安装 requirements-gpu.txt。"
            ) from exc
        self._runtime = onnxruntime
        return self._runtime

    @staticmethod
    def _create_session(runtime: Any, model_path: Path, providers: tuple[str, ...]) -> Any:
        return runtime.InferenceSession(
            str(model_path),
            providers=list(providers),
        )

    def load(self) -> ModelInfo:
        """Load once on first use and validate the WD14 model/CSV contract."""

        if self._session is not None and self._model_info is not None:
            return self._model_info

        files = resolve_model_files(self._model_dir)
        tags = self._load_tags(files.tags_path)
        runtime = self._get_runtime()
        available = tuple(runtime.get_available_providers())
        selection = select_execution_providers(self._device, available)
        preload_error: str | None = None
        if selection.primary_provider == CUDA_PROVIDER:
            # ONNX Runtime 1.21+ can load CUDA/cuDNN DLLs installed by the
            # official ``onnxruntime-gpu[cuda,cudnn]`` extras without changing
            # the system PATH or requiring a full CUDA Toolkit installation.
            preload_dlls = getattr(runtime, "preload_dlls", None)
            if callable(preload_dlls):
                cuda_directory, cudnn_directory = (
                    bundled_nvidia_dll_directories()
                )
                try:
                    if cuda_directory is not None:
                        preload_dlls(
                            cuda=True,
                            cudnn=False,
                            directory=str(cuda_directory),
                        )
                    if cudnn_directory is not None:
                        preload_dlls(
                            cuda=False,
                            cudnn=True,
                            msvc=False,
                            directory=str(cudnn_directory),
                        )
                    if cuda_directory is None and cudnn_directory is None:
                        preload_dlls(directory="")
                except Exception as exc:
                    # Session construction remains authoritative: a compatible
                    # system runtime may still be available. If ORT falls back,
                    # the diagnostic is surfaced below instead of being silent.
                    preload_error = _clean_runtime_error(exc)

        try:
            session = self._create_session(
                runtime,
                files.model_path,
                selection.providers,
            )
        except Exception as first_error:
            can_retry_cpu = (
                selection.primary_provider == CUDA_PROVIDER
                and CPU_PROVIDER in tuple(available)
            )
            if not can_retry_cpu:
                raise ModelLoadError(
                    "无法读取 model.onnx；文件可能损坏、不是兼容的 WD14 ONNX，"
                    f"或运行时依赖缺失。详细原因：{_clean_runtime_error(first_error)}"
                ) from first_error

            try:
                session = self._create_session(
                    runtime,
                    files.model_path,
                    (CPU_PROVIDER,),
                )
            except Exception as cpu_error:
                raise ModelLoadError(
                    "CUDA 和 CPU 都无法加载 model.onnx；文件可能损坏或格式不兼容。"
                    f"CUDA：{_clean_runtime_error(first_error)}；"
                    f"CPU：{_clean_runtime_error(cpu_error)}"
                ) from cpu_error
            selection = replace(
                selection,
                providers=(CPU_PROVIDER,),
                warning=(
                    "CUDA Provider 初始化失败，已自动回退到 CPU。"
                    f"原因：{_clean_runtime_error(first_error)}"
                ),
            )

        try:
            input_name, output_name, input_size, output_count = self._inspect_session(
                session,
                tags,
            )
        except Exception:
            del session
            raise

        active_providers = tuple(session.get_providers())
        if (
            selection.primary_provider == CUDA_PROVIDER
            and CUDA_PROVIDER not in active_providers
        ):
            if CPU_PROVIDER not in active_providers:
                del session
                raise ModelLoadError(
                    "CUDA Provider 未在实际 ONNX Session 中启用，"
                    f"Session Providers：{active_providers!r}"
                )
            diagnostic = (
                f"预加载运行库失败：{preload_error}；"
                if preload_error
                else ""
            )
            selection = replace(
                selection,
                providers=active_providers,
                warning=(
                    "CUDA Provider 未在实际 ONNX Session 中启用，"
                    f"{diagnostic}已自动回退到 CPU。"
                ),
            )
        active_provider = (
            active_providers[0] if active_providers else selection.primary_provider
        )
        model_info = ModelInfo(
            files=files,
            input_name=input_name,
            output_name=output_name,
            input_size=input_size,
            output_count=output_count,
            active_provider=active_provider,
            provider_warning=selection.warning,
        )

        # Publish the state only after all validation succeeds.
        self._session = session
        self._tags = tags
        self._model_info = model_info
        return model_info

    def predict(
        self,
        image_path: Path,
        *,
        image_options: ImageLoadOptions | None = None,
    ) -> InferenceResult:
        model_info = self.load()
        assert self._session is not None
        assert self._tags is not None

        tensor = self._preprocess_image(
            Path(image_path),
            model_info.input_size,
            options=image_options,
        )
        started_at = time.perf_counter()
        try:
            outputs = self._session.run(
                [model_info.output_name],
                {model_info.input_name: tensor},
            )
        except Exception as exc:
            raise InferenceError(
                f"模型推理失败：{_clean_runtime_error(exc)}"
            ) from exc
        inference_seconds = time.perf_counter() - started_at

        if len(outputs) != 1:
            raise InferenceError(
                f"模型返回了 {len(outputs)} 个输出，预期为 1 个。"
            )
        probabilities = np.asarray(outputs[0], dtype=np.float32)
        if probabilities.ndim != 2 or probabilities.shape[0] != 1:
            raise InferenceError(
                "模型输出形状不正确，预期 [1, 标签数]，"
                f"实际为 {probabilities.shape!r}。"
            )
        if probabilities.shape[1] != len(self._tags):
            raise InferenceError(
                "标签数量和实际推理输出数量不一致："
                f"{len(self._tags)} 个 CSV 标签，"
                f"{probabilities.shape[1]} 个模型输出。"
            )
        scores = probabilities[0]
        if not np.all(np.isfinite(scores)):
            raise InferenceError("模型输出包含 NaN 或无穷值。")
        if np.any(scores < -1e-6) or np.any(scores > 1.0 + 1e-6):
            raise InferenceError(
                "模型输出不在 0 到 1 的置信度范围；"
                "请确认选择的是 SmilingWolf WD14 v3 ONNX 文件。"
            )

        predictions = tuple(
            TagPrediction(tag=tag, confidence=float(score))
            for tag, score in zip(self._tags, scores)
        )
        return InferenceResult(
            image_path=Path(image_path),
            model_info=model_info,
            predictions=predictions,
            inference_seconds=inference_seconds,
        )

    def release(self) -> None:
        """Drop references so ONNX Runtime can release CPU/GPU memory."""

        self._session = None
        self._tags = None
        self._model_info = None

    _inspect_session = staticmethod(_inspect_session)
    _preprocess_image = staticmethod(preprocess_image)
    _load_tags = staticmethod(load_selected_tags)
