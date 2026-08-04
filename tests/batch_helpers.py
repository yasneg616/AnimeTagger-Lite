from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import threading

from app.batch.models import BatchConfig, BatchJob, ScanOptions
from app.batch.service import BatchService
from app.config.settings import AppSettings
from app.inference.model_loader import ModelFiles, TagCategory
from app.inference.providers import CPU_PROVIDER, Device
from app.inference.wd14_engine import InferenceResult, ModelInfo
from app.prompts.models import TagResult
from app.services.tagging_service import AnalysisResult, TaggingService


def touch_image(path: Path, content: bytes = b"not-decoded") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def build_analysis(
    source: Path,
    *,
    settings: AppSettings | None = None,
    tags: tuple[TagResult, ...] | None = None,
) -> AnalysisResult:
    model_dir = source.parent / "fake-model"
    files = ModelFiles(
        model_dir,
        model_dir / "model.onnx",
        model_dir / "selected_tags.csv",
    )
    info = ModelInfo(
        files=files,
        input_name="input",
        output_name="output",
        input_size=448,
        output_count=4,
        active_provider=CPU_PROVIDER,
        provider_warning=None,
    )
    inference = InferenceResult(source, info, (), 0.012)
    raw = (
        tags
        if tags is not None
        else (
            TagResult("1girl", 0.95, TagCategory.GENERAL),
            TagResult("long_hair", 0.88, TagCategory.GENERAL),
            TagResult("alice", 0.90, TagCategory.CHARACTER),
            TagResult("safe", 0.99, TagCategory.RATING),
        )
    )
    effective = settings or AppSettings(
        profile="lora_caption",
        add_profile_prefix=False,
        negative_mode="none",
    )
    prompts = TaggingService().rebuild_prompts(raw, effective)
    return AnalysisResult(inference, raw, prompts)


class FakeBatchTaggingService:
    def __init__(self, *, loaded: bool = True) -> None:
        self.loaded = loaded
        self.calls: list[Path] = []
        self.load_calls = 0
        self.unload_calls = 0
        self.fail_names: set[str] = set()
        self.started_event: threading.Event | None = None
        self.release_event: threading.Event | None = None
        self.settings_seen: list[AppSettings] = []
        self.info = build_analysis(Path("example.png")).inference.model_info

    @property
    def is_model_loaded(self) -> bool:
        return self.loaded

    def load_model(self, _path: Path, _device: Device):
        self.load_calls += 1
        self.loaded = True
        return self.info

    def unload_model(self) -> None:
        self.unload_calls += 1
        self.loaded = False

    def analyze_image(
        self,
        path: Path,
        settings: AppSettings,
    ) -> AnalysisResult:
        self.calls.append(path)
        self.settings_seen.append(settings)
        if self.started_event is not None:
            self.started_event.set()
        if self.release_event is not None:
            assert self.release_event.wait(5)
            self.release_event = None
        if path.name in self.fail_names:
            raise RuntimeError(f"fake inference failed: {path.name}")
        return build_analysis(path, settings=settings)


def create_job(
    root: Path,
    *,
    service: FakeBatchTaggingService | None = None,
    config: BatchConfig | None = None,
    settings: AppSettings | None = None,
    recursive: bool = False,
) -> tuple[BatchService, BatchJob, FakeBatchTaggingService]:
    fake = service or FakeBatchTaggingService()
    batch = BatchService(fake)  # type: ignore[arg-type]
    job = batch.create_job(
        ScanOptions((root,), recursive=recursive),
        config or BatchConfig(write_csv=False),
        settings
        or AppSettings(
            profile="lora_caption",
            add_profile_prefix=False,
            negative_mode="none",
        ),
    )
    return batch, job, fake
