"""ONNX Runtime CPU/CUDA provider selection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from app.errors import ProviderError

CPU_PROVIDER = "CPUExecutionProvider"
CUDA_PROVIDER = "CUDAExecutionProvider"


class Device(str, Enum):
    AUTO = "auto"
    CUDA = "cuda"
    CPU = "cpu"


@dataclass(frozen=True, slots=True)
class ProviderSelection:
    requested_device: Device
    providers: tuple[str, ...]
    warning: str | None = None

    @property
    def primary_provider(self) -> str:
        return self.providers[0]


def select_execution_providers(
    device: Device,
    available_providers: Iterable[str],
) -> ProviderSelection:
    """Prefer CUDA for auto/cuda requests and always keep a CPU fallback."""

    available = tuple(dict.fromkeys(available_providers))
    has_cpu = CPU_PROVIDER in available
    has_cuda = CUDA_PROVIDER in available

    if device is Device.CPU:
        if not has_cpu:
            raise ProviderError(
                "ONNX Runtime 未提供 CPUExecutionProvider；请重新安装 onnxruntime。"
            )
        return ProviderSelection(device, (CPU_PROVIDER,))

    if has_cuda:
        providers = (CUDA_PROVIDER, CPU_PROVIDER) if has_cpu else (CUDA_PROVIDER,)
        return ProviderSelection(device, providers)

    if has_cpu:
        return ProviderSelection(
            device,
            (CPU_PROVIDER,),
            "CUDAExecutionProvider 不可用，已自动回退到 CPU。"
            "如需 GPU，请安装 onnxruntime-gpu 并确认 NVIDIA 驱动兼容。",
        )

    provider_text = ", ".join(available) if available else "无"
    raise ProviderError(
        "没有可用的 ONNX Runtime CPU/CUDA Provider；"
        f"当前检测到：{provider_text}"
    )

