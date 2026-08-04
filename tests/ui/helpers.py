from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.config.settings import AppSettings
from app.inference.model_loader import ModelFiles, TagCategory
from app.inference.providers import CPU_PROVIDER
from app.inference.wd14_engine import InferenceResult, ModelInfo
from app.prompts.models import TagResult
from app.services.tagging_service import TaggingService


def make_image(path: Path, color: str = "red") -> Path:
    Image.new("RGB", (32, 24), color).save(path)
    return path


def build_completed_payload(source: Path):
    model_dir = source.parent / "model"
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
        output_count=2,
        active_provider=CPU_PROVIDER,
        provider_warning=None,
    )
    inference = InferenceResult(source, info, (), 0.012)
    raw = (
        TagResult("1girl", 0.95, TagCategory.GENERAL),
        TagResult("long_hair", 0.82, TagCategory.GENERAL),
    )
    prompts = TaggingService().rebuild_prompts(raw, AppSettings())
    return inference, raw, prompts

