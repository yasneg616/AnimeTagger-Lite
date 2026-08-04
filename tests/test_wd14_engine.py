from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from app.errors import ModelLoadError
from app.inference.model_loader import TagCategory
from app.inference.providers import CPU_PROVIDER, CUDA_PROVIDER, Device
from app.inference.wd14_engine import WD14Engine, group_predictions


@dataclass
class FakeNode:
    name: str
    shape: list[Any]
    type: str = "tensor(float)"


class FakeSession:
    def __init__(
        self,
        providers: list[str],
        output: np.ndarray,
        *,
        declared_output_count: int | None = None,
    ) -> None:
        self._providers = providers
        self._output = output
        self._declared_output_count = (
            declared_output_count
            if declared_output_count is not None
            else int(output.shape[1])
        )
        self.run_calls = 0

    def get_inputs(self) -> list[FakeNode]:
        return [FakeNode("input", ["N", 4, 4, 3])]

    def get_outputs(self) -> list[FakeNode]:
        return [FakeNode("output", ["N", self._declared_output_count])]

    def get_providers(self) -> list[str]:
        return self._providers

    def run(
        self,
        output_names: list[str],
        feeds: dict[str, np.ndarray],
    ) -> list[np.ndarray]:
        assert output_names == ["output"]
        assert feeds["input"].shape == (1, 4, 4, 3)
        self.run_calls += 1
        return [self._output]


class FakeRuntime:
    def __init__(
        self,
        available: list[str],
        output: np.ndarray,
        *,
        fail_cuda: bool = False,
        silent_cuda_fallback: bool = False,
        declared_output_count: int | None = None,
    ) -> None:
        self.available = available
        self.output = output
        self.fail_cuda = fail_cuda
        self.silent_cuda_fallback = silent_cuda_fallback
        self.declared_output_count = declared_output_count
        self.preload_calls: list[dict[str, object]] = []
        self.session_calls: list[tuple[str, ...]] = []
        self.sessions: list[FakeSession] = []

    def get_available_providers(self) -> list[str]:
        return self.available

    def preload_dlls(
        self,
        *,
        cuda: bool = True,
        cudnn: bool = True,
        msvc: bool = True,
        directory: str | None = None,
    ) -> None:
        self.preload_calls.append(
            {
                "cuda": cuda,
                "cudnn": cudnn,
                "msvc": msvc,
                "directory": directory,
            }
        )

    def InferenceSession(
        self,
        model_path: str,
        *,
        providers: list[str],
    ) -> FakeSession:
        assert model_path.endswith("model.onnx")
        self.session_calls.append(tuple(providers))
        if providers[0] == CUDA_PROVIDER and self.fail_cuda:
            raise RuntimeError("CUDA DLL missing")
        session = FakeSession(
            (
                [CPU_PROVIDER]
                if providers[0] == CUDA_PROVIDER
                and self.silent_cuda_fallback
                else providers
            ),
            self.output,
            declared_output_count=self.declared_output_count,
        )
        self.sessions.append(session)
        return session


def _create_model_dir(tmp_path: Path) -> Path:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "model.onnx").write_bytes(b"mock ONNX for interface test")
    (model_dir / "selected_tags.csv").write_text(
        "tag_id,name,category,count\n"
        "1,safe,9,100\n"
        "2,1girl,0,100\n"
        "3,alice,4,100\n",
        encoding="utf-8",
    )
    return model_dir


def _create_image(tmp_path: Path) -> Path:
    image_path = tmp_path / "image.png"
    Image.new("RGB", (4, 4), (10, 20, 30)).save(image_path)
    return image_path


def test_engine_is_lazy_and_reuses_one_session(tmp_path: Path) -> None:
    runtime = FakeRuntime(
        [CPU_PROVIDER],
        np.array([[0.9, 0.8, 0.7]], dtype=np.float32),
    )
    engine = WD14Engine(
        _create_model_dir(tmp_path),
        device=Device.AUTO,
        runtime=runtime,
    )
    image_path = _create_image(tmp_path)

    assert not engine.is_loaded
    first = engine.predict(image_path)
    second = engine.predict(image_path)

    assert engine.is_loaded
    assert len(runtime.session_calls) == 1
    assert runtime.sessions[0].run_calls == 2
    assert [item.tag.name for item in first.predictions] == [
        "safe",
        "1girl",
        "alice",
    ]
    assert second.model_info is first.model_info

    engine.release()
    assert not engine.is_loaded


def test_category_specific_thresholds_are_applied(tmp_path: Path) -> None:
    runtime = FakeRuntime(
        [CPU_PROVIDER],
        np.array([[0.2, 0.5, 0.7]], dtype=np.float32),
    )
    engine = WD14Engine(_create_model_dir(tmp_path), runtime=runtime)
    result = engine.predict(_create_image(tmp_path))

    grouped = group_predictions(
        result.predictions,
        general_threshold=0.35,
        character_threshold=0.75,
    )

    assert [item.tag.name for item in grouped[TagCategory.RATING]] == ["safe"]
    assert [item.tag.name for item in grouped[TagCategory.GENERAL]] == ["1girl"]
    assert grouped[TagCategory.CHARACTER] == ()


def test_cuda_session_failure_retries_with_cpu(tmp_path: Path) -> None:
    runtime = FakeRuntime(
        [CUDA_PROVIDER, CPU_PROVIDER],
        np.array([[0.9, 0.8, 0.7]], dtype=np.float32),
        fail_cuda=True,
    )
    engine = WD14Engine(
        _create_model_dir(tmp_path),
        device=Device.AUTO,
        runtime=runtime,
    )

    result = engine.predict(_create_image(tmp_path))

    assert runtime.session_calls == [
        (CUDA_PROVIDER, CPU_PROVIDER),
        (CPU_PROVIDER,),
    ]
    assert result.model_info.active_provider == CPU_PROVIDER
    assert result.model_info.provider_warning is not None
    assert "CUDA Provider 初始化失败" in result.model_info.provider_warning


def test_cuda_runtime_dlls_are_preloaded_from_site_packages(
    tmp_path: Path,
) -> None:
    runtime = FakeRuntime(
        [CUDA_PROVIDER, CPU_PROVIDER],
        np.array([[0.9, 0.8, 0.7]], dtype=np.float32),
    )
    engine = WD14Engine(
        _create_model_dir(tmp_path),
        device=Device.CUDA,
        runtime=runtime,
    )

    result = engine.predict(_create_image(tmp_path))

    assert runtime.preload_calls == [
        {
            "cuda": True,
            "cudnn": True,
            "msvc": True,
            "directory": "",
        }
    ]
    assert result.model_info.active_provider == CUDA_PROVIDER
    assert result.model_info.provider_warning is None


def test_bundled_cuda_and_cudnn_directories_are_preloaded_separately(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cuda_directory = tmp_path / "cuda"
    cudnn_directory = tmp_path / "cudnn"
    cuda_directory.mkdir()
    cudnn_directory.mkdir()
    monkeypatch.setattr(
        "app.inference.wd14_engine.bundled_nvidia_dll_directories",
        lambda: (cuda_directory, cudnn_directory),
    )
    runtime = FakeRuntime(
        [CUDA_PROVIDER, CPU_PROVIDER],
        np.array([[0.9, 0.8, 0.7]], dtype=np.float32),
    )
    engine = WD14Engine(
        _create_model_dir(tmp_path),
        device=Device.CUDA,
        runtime=runtime,
    )

    result = engine.predict(_create_image(tmp_path))

    assert runtime.preload_calls == [
        {
            "cuda": True,
            "cudnn": False,
            "msvc": True,
            "directory": str(cuda_directory),
        },
        {
            "cuda": False,
            "cudnn": True,
            "msvc": False,
            "directory": str(cudnn_directory),
        },
    ]
    assert result.model_info.active_provider == CUDA_PROVIDER


def test_silent_cuda_session_fallback_is_reported(tmp_path: Path) -> None:
    runtime = FakeRuntime(
        [CUDA_PROVIDER, CPU_PROVIDER],
        np.array([[0.9, 0.8, 0.7]], dtype=np.float32),
        silent_cuda_fallback=True,
    )
    engine = WD14Engine(
        _create_model_dir(tmp_path),
        device=Device.CUDA,
        runtime=runtime,
    )

    result = engine.predict(_create_image(tmp_path))

    assert result.model_info.active_provider == CPU_PROVIDER
    assert result.model_info.provider_warning is not None
    assert "未在实际 ONNX Session 中启用" in result.model_info.provider_warning
    assert "回退到 CPU" in result.model_info.provider_warning


def test_static_model_output_must_match_csv_count(tmp_path: Path) -> None:
    runtime = FakeRuntime(
        [CPU_PROVIDER],
        np.array([[0.9, 0.8, 0.7]], dtype=np.float32),
        declared_output_count=4,
    )
    engine = WD14Engine(_create_model_dir(tmp_path), runtime=runtime)

    with pytest.raises(ModelLoadError, match="标签数量和模型输出数量不一致"):
        engine.load()
