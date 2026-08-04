from __future__ import annotations

import pytest

from app.errors import ProviderError
from app.inference.providers import (
    CPU_PROVIDER,
    CUDA_PROVIDER,
    Device,
    select_execution_providers,
)


def test_auto_prefers_cuda_and_keeps_cpu_fallback() -> None:
    selection = select_execution_providers(
        Device.AUTO,
        [CPU_PROVIDER, CUDA_PROVIDER],
    )

    assert selection.providers == (CUDA_PROVIDER, CPU_PROVIDER)
    assert selection.warning is None


@pytest.mark.parametrize("device", [Device.AUTO, Device.CUDA])
def test_cuda_unavailable_falls_back_to_cpu(device: Device) -> None:
    selection = select_execution_providers(device, [CPU_PROVIDER])

    assert selection.providers == (CPU_PROVIDER,)
    assert selection.warning is not None
    assert "回退到 CPU" in selection.warning


def test_explicit_cpu_does_not_request_cuda() -> None:
    selection = select_execution_providers(
        Device.CPU,
        [CUDA_PROVIDER, CPU_PROVIDER],
    )

    assert selection.providers == (CPU_PROVIDER,)
    assert selection.warning is None


def test_no_cpu_or_cuda_provider_is_an_error() -> None:
    with pytest.raises(ProviderError, match="没有可用"):
        select_execution_providers(Device.AUTO, ["AzureExecutionProvider"])

