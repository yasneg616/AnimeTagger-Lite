from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app import __version__
from app.config.presets import NegativePresetCatalog, PromptProfileCatalog
from app.config.settings import AppSettings
from app.errors import ExportError
from app.export_service import ExportFormat, ExportService
from app.inference.model_loader import (
    ModelFiles,
    TagCategory,
)
from app.inference.providers import CPU_PROVIDER
from app.inference.wd14_engine import InferenceResult, ModelInfo
from app.prompts.models import TagResult, TagSource
from app.prompts.pipeline import PromptProcessor
from app.prompts.tag_classifier import TagClassifier

RESOURCE_DIR = Path(__file__).resolve().parents[1] / "resources"


def build_results(
    source_image: Path,
    *,
    settings: AppSettings | None = None,
) -> tuple[object, InferenceResult]:
    model_dir = Path(r"C:\models\wd-vit-tagger-v3")
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
    inference = InferenceResult(
        source_image,
        info,
        (),
        0.123456,
    )
    processor = PromptProcessor(
        TagClassifier.from_json(RESOURCE_DIR / "tag_categories.json"),
        PromptProfileCatalog.from_json(RESOURCE_DIR / "prompt_profiles.json"),
        NegativePresetCatalog.from_json(RESOURCE_DIR / "negative_presets.json"),
    )
    prompts = processor.build(
        [
            TagResult("1girl", 0.9, TagCategory.GENERAL),
            TagResult("长发", 0.8, TagCategory.GENERAL),
        ],
        settings or AppSettings(),
    )
    return prompts, inference


def test_positive_txt_export(tmp_path: Path) -> None:
    prompts, inference = build_results(tmp_path / "image.png")
    output = tmp_path / "caption.txt"

    ExportService().export(
        ExportFormat.TXT,
        output,
        prompts,  # type: ignore[arg-type]
        inference,
    )

    assert output.read_text(encoding="utf-8") == "1girl, 长发\n"


def test_positive_negative_txt_export(tmp_path: Path) -> None:
    from dataclasses import replace

    prompts, inference = build_results(
        tmp_path / "image.png",
        settings=replace(AppSettings(), negative_mode="basic"),
    )
    output = tmp_path / "prompts.txt"

    ExportService().export(
        ExportFormat.PROMPT_TXT,
        output,
        prompts,  # type: ignore[arg-type]
        inference,
    )

    text = output.read_text(encoding="utf-8")
    assert text.startswith("Positive:\n1girl, 长发\n\nNegative:\n")
    assert "low quality" in text


def test_json_export_contains_required_fields(tmp_path: Path) -> None:
    source = Path(r"C:\images\角色.png")
    prompts, inference = build_results(source)
    output = tmp_path / "result.json"

    ExportService().export(
        ExportFormat.JSON,
        output,
        prompts,  # type: ignore[arg-type]
        inference,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))

    required = {
        "schema_version",
        "app_version",
        "application_version",
        "source_image",
        "model_name",
        "model_path",
        "execution_provider",
        "inference_time_ms",
        "generated_at",
        "thresholds",
        "prompt_profile",
        "raw_tags",
        "working_tags",
        "filtered_tags",
        "removed_tags",
        "excluded_tags",
        "detected_defects",
        "positive_prompt",
        "negative_prompt",
    }
    assert required.issubset(payload)
    assert payload["app_version"] == __version__
    assert payload["application_version"] == __version__
    assert payload["source_image"] == str(source)
    assert payload["execution_provider"] == CPU_PROVIDER
    assert payload["inference_time_ms"] == 123.456
    assert payload["raw_tags"][0]["source"] == "model"
    assert payload["raw_tags"][0]["prompt_group"] == "count"


def test_json_distinguishes_model_raw_and_edited_working_tags(
    tmp_path: Path,
) -> None:
    prompts, inference = build_results(tmp_path / "image.png")
    model_raw = (
        TagResult("original_model_tag", 0.91, TagCategory.CHARACTER),
    )
    working = (
        TagResult(
            "edited user tag",
            1.0,
            TagCategory.GENERAL,
            source=TagSource.USER,
        ),
    )

    document = ExportService().build_json_document(
        prompts,  # type: ignore[arg-type]
        inference,
        model_raw_tags=model_raw,
        working_tags=working,
    )

    assert document["raw_tags"][0]["name"] == "original_model_tag"
    assert document["raw_tags"][0]["source"] == "model"
    assert document["working_tags"][0]["name"] == "edited user tag"
    assert document["working_tags"][0]["source"] == "user"


def test_negative_json_tags_keep_common_tag_fields(tmp_path: Path) -> None:
    from dataclasses import replace

    prompts, inference = build_results(
        tmp_path / "image.png",
        settings=replace(AppSettings(), negative_mode="basic"),
    )
    document = ExportService().build_json_document(
        prompts,  # type: ignore[arg-type]
        inference,
    )
    negative = document["negative_tags"][0]

    assert {
        "name",
        "normalized_name",
        "confidence",
        "category",
        "prompt_group",
        "source",
    }.issubset(negative)


def test_json_is_utf8_and_not_ascii_escaped(tmp_path: Path) -> None:
    prompts, inference = build_results(Path(r"C:\images\角色.png"))
    output = tmp_path / "result.json"

    ExportService().export(
        ExportFormat.JSON,
        output,
        prompts,  # type: ignore[arg-type]
        inference,
    )

    raw = output.read_bytes()
    assert "角色".encode("utf-8") in raw
    assert "长发".encode("utf-8") in raw
    assert b"\\u89d2\\u8272" not in raw


def test_default_does_not_overwrite_existing_file(tmp_path: Path) -> None:
    prompts, inference = build_results(tmp_path / "image.png")
    output = tmp_path / "caption.txt"
    output.write_text("original", encoding="utf-8")

    with pytest.raises(ExportError, match="已存在"):
        ExportService().export(
            ExportFormat.TXT,
            output,
            prompts,  # type: ignore[arg-type]
            inference,
        )

    assert output.read_text(encoding="utf-8") == "original"


def test_explicit_overwrite_replaces_existing_file(tmp_path: Path) -> None:
    prompts, inference = build_results(tmp_path / "image.png")
    output = tmp_path / "caption.txt"
    output.write_text("original", encoding="utf-8")

    ExportService().export(
        ExportFormat.TXT,
        output,
        prompts,  # type: ignore[arg-type]
        inference,
        overwrite=True,
    )

    assert output.read_text(encoding="utf-8") == "1girl, 长发\n"


def test_failed_atomic_replace_does_not_damage_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompts, inference = build_results(tmp_path / "image.png")
    output = tmp_path / "caption.txt"
    output.write_text("original", encoding="utf-8")

    def fail_replace(source: object, destination: object) -> None:
        raise PermissionError("simulated denial")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(ExportError, match="无法安全写入"):
        ExportService().export(
            ExportFormat.TXT,
            output,
            prompts,  # type: ignore[arg-type]
            inference,
            overwrite=True,
        )

    assert output.read_text(encoding="utf-8") == "original"
    assert not list(tmp_path.glob(".caption.txt.*.tmp"))


def test_json_contains_paths_only_not_binary_content(tmp_path: Path) -> None:
    prompts, inference = build_results(tmp_path / "image.png")
    document = ExportService().build_json_document(
        prompts,  # type: ignore[arg-type]
        inference,
    )

    serialized = json.dumps(document)
    assert "image_binary" not in serialized
    assert "model_binary" not in serialized


def test_schema_two_keeps_legacy_and_explicit_prompt_fields(tmp_path: Path) -> None:
    prompts, inference = build_results(tmp_path / "image.png")
    document = ExportService().build_json_document(
        prompts,  # type: ignore[arg-type]
        inference,
        final_positive_prompt="edited positive",
        final_negative_prompt="edited negative",
        prompt_was_edited=True,
    )

    assert document["schema_version"] == 2
    assert document["generated_positive_prompt"] == "1girl, 长发"
    assert document["final_positive_prompt"] == "edited positive"
    assert document["positive_prompt"] == "edited positive"
    assert document["prompt_was_edited"] is True


def test_txt_export_accepts_final_prompt_without_changing_generated(
    tmp_path: Path,
) -> None:
    prompts, inference = build_results(tmp_path / "image.png")
    output = tmp_path / "caption.txt"
    ExportService().export(
        ExportFormat.TXT,
        output,
        prompts,  # type: ignore[arg-type]
        inference,
        final_positive_prompt="manual final",
    )
    assert output.read_text(encoding="utf-8") == "manual final\n"
    assert prompts.positive_prompt == "1girl, 长发"  # type: ignore[union-attr]
