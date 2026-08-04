from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path

import pytest

from app.batch.atomic import atomic_write_text
from app.batch.exporter import (
    BatchOutputWriter,
    caption_terms,
    merge_caption_terms,
    next_backup_path,
)
from app.batch.models import (
    BatchConfig,
    BatchItemStatus,
    BatchTextFormat,
    CaptionPolicy,
    OutputMode,
    ScanOptions,
)
from app.batch.service import BatchService
from app.config.settings import AppSettings
from app.errors import BatchConfigurationError, ExportError
from app.inference.model_loader import TagCategory
from app.prompts.models import TagResult
from app.services.tagging_service import AnalysisResult, TaggingService
from tests.batch_helpers import (
    FakeBatchTaggingService,
    build_analysis,
    create_job,
    touch_image,
)


def _one_image(tmp_path: Path) -> Path:
    return touch_image(tmp_path / "one.png")


def test_skip_existing_caption_avoids_inference(tmp_path: Path) -> None:
    _one_image(tmp_path)
    caption = tmp_path / "one.txt"
    caption.write_text("manual tag\n", encoding="utf-8")
    batch, job, fake = create_job(
        tmp_path,
        config=BatchConfig(
            caption_policy=CaptionPolicy.SKIP,
            write_csv=False,
        ),
    )
    batch.run_job(job)
    assert job.items[0].status is BatchItemStatus.SKIPPED
    assert fake.calls == []
    assert caption.read_text(encoding="utf-8") == "manual tag\n"


def test_skip_existing_json_avoids_inference_and_preserves_report(
    tmp_path: Path,
) -> None:
    _one_image(tmp_path)
    report = tmp_path / "one.json"
    original = '{"manual": true}\n'
    report.write_text(original, encoding="utf-8")
    batch, job, fake = create_job(
        tmp_path,
        config=BatchConfig(
            caption_policy=CaptionPolicy.SKIP,
            write_captions=False,
            write_json=True,
            write_csv=False,
        ),
    )
    batch.run_job(job)
    assert job.items[0].status is BatchItemStatus.SKIPPED
    assert fake.calls == []
    assert report.read_text(encoding="utf-8") == original


def test_overwrite_replaces_existing_caption_atomically(tmp_path: Path) -> None:
    _one_image(tmp_path)
    caption = tmp_path / "one.txt"
    caption.write_text("old\n", encoding="utf-8")
    batch, job, _fake = create_job(
        tmp_path,
        config=BatchConfig(
            caption_policy=CaptionPolicy.OVERWRITE,
            write_csv=False,
        ),
    )
    batch.run_job(job)
    assert "1girl" in caption.read_text(encoding="utf-8")
    assert not list(tmp_path.glob("*.animetagger.tmp"))


def test_backup_and_overwrite_keeps_exact_old_bytes(tmp_path: Path) -> None:
    _one_image(tmp_path)
    old = b"manual, old\r\n"
    caption = tmp_path / "one.txt"
    caption.write_bytes(old)
    batch, job, _fake = create_job(
        tmp_path,
        config=BatchConfig(
            caption_policy=CaptionPolicy.BACKUP_AND_OVERWRITE,
            write_csv=False,
        ),
    )
    batch.run_job(job)
    assert (tmp_path / "one.txt.bak").read_bytes() == old
    assert job.items[0].backup_path == tmp_path / "one.txt.bak"


def test_backup_name_increments_without_overwriting(tmp_path: Path) -> None:
    caption = tmp_path / "one.txt"
    caption.write_text("old", encoding="utf-8")
    (tmp_path / "one.txt.bak").write_text("first", encoding="utf-8")
    (tmp_path / "one.txt.bak.1").write_text("second", encoding="utf-8")
    assert next_backup_path(caption).name == "one.txt.bak.2"


def test_append_trigger_preserves_manual_caption_and_skips_model(
    tmp_path: Path,
) -> None:
    _one_image(tmp_path)
    caption = tmp_path / "one.txt"
    caption.write_text("1girl, blue eyes\n", encoding="utf-8")
    batch, job, fake = create_job(
        tmp_path,
        config=BatchConfig(
            caption_policy=CaptionPolicy.APPEND_TRIGGER,
            write_csv=False,
        ),
        settings=AppSettings(
            profile="lora_caption",
            trigger_word="style_token",
        ),
    )
    batch.run_job(job)
    assert caption.read_text(encoding="utf-8") == (
        "style_token, 1girl, blue eyes\n"
    )
    assert fake.calls == []


def test_append_trigger_does_not_duplicate_existing_trigger(
    tmp_path: Path,
) -> None:
    _one_image(tmp_path)
    caption = tmp_path / "one.txt"
    caption.write_text("STYLE_token, 1girl\n", encoding="utf-8")
    batch, job, _fake = create_job(
        tmp_path,
        config=BatchConfig(
            caption_policy=CaptionPolicy.APPEND_TRIGGER,
            write_csv=False,
        ),
        settings=AppSettings(
            profile="lora_caption",
            trigger_word="style token",
        ),
    )
    batch.run_job(job)
    assert caption_terms(caption.read_text(encoding="utf-8")) == (
        "style token",
        "1girl",
    )


def test_append_trigger_exact_duplicate_is_not_repeated(tmp_path: Path) -> None:
    _one_image(tmp_path)
    caption = tmp_path / "one.txt"
    caption.write_text("style_token, 1girl\n", encoding="utf-8")
    batch, job, _fake = create_job(
        tmp_path,
        config=BatchConfig(
            caption_policy=CaptionPolicy.APPEND_TRIGGER,
            write_csv=False,
        ),
        settings=AppSettings(
            profile="lora_caption",
            trigger_word="style_token",
        ),
    )
    batch.run_job(job)
    assert caption.read_text(encoding="utf-8") == "style_token, 1girl\n"


def test_merge_keeps_existing_terms_first_and_stably_deduplicates(
    tmp_path: Path,
) -> None:
    _one_image(tmp_path)
    caption = tmp_path / "one.txt"
    caption.write_text("manual, 1girl\n", encoding="utf-8")
    batch, job, _fake = create_job(
        tmp_path,
        config=BatchConfig(
            caption_policy=CaptionPolicy.MERGE,
            write_csv=False,
        ),
        settings=AppSettings(
            profile="lora_caption",
            trigger_word="style",
        ),
    )
    batch.run_job(job)
    merged = caption.read_text(encoding="utf-8")
    assert merged.startswith("style, manual, 1girl")
    assert "long_hair" in merged


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (("a, b", "b, c"), "a, b, c"),
        (("long_hair", "long hair"), "long_hair"),
        ((None, " a "), "a"),
        (("", ""), ""),
    ],
)
def test_merge_caption_terms(
    values: tuple[str | None, ...],
    expected: str,
) -> None:
    assert merge_caption_terms(*values) == expected


def test_prompt_txt_contains_positive_and_negative_sections(
    tmp_path: Path,
) -> None:
    _one_image(tmp_path)
    settings = AppSettings(profile="raw", negative_mode="basic")
    batch, job, _fake = create_job(
        tmp_path,
        config=BatchConfig(
            text_format=BatchTextFormat.PROMPT_TXT,
            write_csv=False,
        ),
        settings=settings,
    )
    batch.run_job(job)
    text = (tmp_path / "one.txt").read_text(encoding="utf-8")
    assert text.startswith("Positive:\n")
    assert "\n\nNegative:\n" in text


def test_prompt_txt_rejects_merge_policy() -> None:
    with pytest.raises(BatchConfigurationError):
        BatchConfig(
            text_format=BatchTextFormat.PROMPT_TXT,
            caption_policy=CaptionPolicy.MERGE,
        )


def test_json_export_keeps_stage3_schema_and_batch_metadata(
    tmp_path: Path,
) -> None:
    _one_image(tmp_path)
    batch, job, _fake = create_job(
        tmp_path,
        config=BatchConfig(
            write_json=True,
            write_csv=False,
        ),
    )
    batch.run_job(job)
    text = (tmp_path / "one.json").read_text(encoding="utf-8")
    assert '"schema_version": 2' in text
    assert f'"job_id": "{job.id}"' in text


def test_mirror_output_directories_are_created_lazily(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    _one_image(root)
    output = tmp_path / "new" / "nested-output"
    batch, job, _fake = create_job(
        root,
        config=BatchConfig(
            output_mode=OutputMode.MIRROR,
            output_root=output,
            write_csv=False,
        ),
    )
    assert not output.exists()
    batch.run_job(job)
    assert (output / "one.txt").is_file()


def test_atomic_write_failure_preserves_existing_file_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "old.txt"
    target.write_text("old", encoding="utf-8")
    real_replace = os.replace

    def fail_replace(source, destination):
        if Path(destination) == target:
            raise OSError("simulated")
        return real_replace(source, destination)

    monkeypatch.setattr("app.batch.atomic.os.replace", fail_replace)
    with pytest.raises(ExportError):
        atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob("*.animetagger.tmp"))


def test_backup_failure_never_overwrites_original(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _one_image(tmp_path)
    caption = tmp_path / "one.txt"
    caption.write_text("manual\n", encoding="utf-8")
    batch, job, _fake = create_job(
        tmp_path,
        config=BatchConfig(
            caption_policy=CaptionPolicy.BACKUP_AND_OVERWRITE,
            write_csv=False,
        ),
    )

    def fail_backup(_path, _content):
        raise ExportError("backup failed")

    monkeypatch.setattr(
        "app.batch.exporter.atomic_write_bytes",
        fail_backup,
    )
    batch.run_job(job)
    assert caption.read_text(encoding="utf-8") == "manual\n"
    assert job.items[0].status is BatchItemStatus.FAILED


class EmptyPromptService(FakeBatchTaggingService):
    def analyze_image(
        self,
        path: Path,
        settings: AppSettings,
    ) -> AnalysisResult:
        self.calls.append(path)
        return build_analysis(path, settings=settings, tags=())


def test_empty_prompt_never_creates_empty_caption(tmp_path: Path) -> None:
    _one_image(tmp_path)
    fake = EmptyPromptService()
    batch, job, _ = create_job(tmp_path, service=fake)
    batch.run_job(job)
    assert not (tmp_path / "one.txt").exists()
    assert job.items[0].status is BatchItemStatus.FAILED


def test_lora_profile_never_adds_quality_or_negative() -> None:
    raw = (
        TagResult("1girl", 0.9, TagCategory.GENERAL),
        TagResult("blue_eyes", 0.8, TagCategory.GENERAL),
    )
    result = TaggingService().rebuild_prompts(
        raw,
        AppSettings(
            profile="lora_caption",
            add_profile_prefix=True,
            negative_mode="basic",
        ),
    )
    assert "masterpiece" not in result.positive_prompt
    assert "best quality" not in result.positive_prompt
    assert result.negative_prompt == ""


def test_lora_trigger_first_and_last_positions() -> None:
    raw = (TagResult("1girl", 0.9, TagCategory.GENERAL),)
    service = TaggingService()
    first = service.rebuild_prompts(
        raw,
        AppSettings(
            profile="lora_caption",
            trigger_word="style",
            trigger_word_position="first",
        ),
    )
    last = service.rebuild_prompts(
        raw,
        AppSettings(
            profile="lora_caption",
            trigger_word="style",
            trigger_word_position="last",
        ),
    )
    assert first.positive_prompt == "style, 1girl"
    assert last.positive_prompt == "1girl, style"


def test_trigger_is_not_duplicated_when_model_has_same_tag() -> None:
    raw = (TagResult("style", 0.9, TagCategory.GENERAL),)
    result = TaggingService().rebuild_prompts(
        raw,
        AppSettings(profile="lora_caption", trigger_word="style"),
    )
    assert result.positive_prompt == "style"


def test_character_tag_switch_filters_character_category() -> None:
    raw = (
        TagResult("1girl", 0.9, TagCategory.GENERAL),
        TagResult("alice", 0.99, TagCategory.CHARACTER),
    )
    result = TaggingService().rebuild_prompts(
        raw,
        AppSettings(
            profile="lora_caption",
            include_character_tags=False,
        ),
    )
    assert result.positive_prompt == "1girl"


def test_rating_remains_disabled_by_default_in_lora() -> None:
    raw = (
        TagResult("safe", 0.99, TagCategory.RATING),
        TagResult("1girl", 0.9, TagCategory.GENERAL),
    )
    result = TaggingService().rebuild_prompts(
        raw,
        AppSettings(profile="lora_caption"),
    )
    assert "safe" not in result.positive_prompt


def test_lora_remove_exclude_and_always_include_are_independent() -> None:
    raw = (
        TagResult("solo", 0.99, TagCategory.GENERAL),
        TagResult("simple_background", 0.99, TagCategory.GENERAL),
        TagResult("blue_eyes", 0.01, TagCategory.GENERAL),
        TagResult("1girl", 0.8, TagCategory.GENERAL),
    )
    result = TaggingService().rebuild_prompts(
        raw,
        AppSettings(
            profile="lora_caption",
            remove_tags=("solo",),
            excluded_tags=("simple_background",),
            always_include_tags=("blue_eyes",),
        ),
    )
    assert set(result.positive_prompt.split(", ")) == {"blue_eyes", "1girl"}


def test_batch_rejects_trigger_containing_comma(tmp_path: Path) -> None:
    _one_image(tmp_path)
    fake = FakeBatchTaggingService()
    with pytest.raises(BatchConfigurationError):
        BatchService(fake).create_job(  # type: ignore[arg-type]
            ScanOptions((tmp_path,)),
            BatchConfig(write_csv=False),
            AppSettings(
                profile="lora_caption",
                trigger_word="one,two",
            ),
        )


def test_settings_snapshot_is_deep_and_isolated(tmp_path: Path) -> None:
    _one_image(tmp_path)
    base = AppSettings(
        profile="lora_caption",
        remove_tags=("original",),
    )
    _batch, job, _fake = create_job(tmp_path, settings=base)
    changed = replace(base, remove_tags=("changed",))
    assert changed.remove_tags == ("changed",)
    assert job.settings.remove_tags == ("original",)


def test_each_image_receives_its_own_result(tmp_path: Path) -> None:
    touch_image(tmp_path / "one.png")
    touch_image(tmp_path / "two.png")
    batch, job, fake = create_job(tmp_path)
    batch.run_job(job)
    assert [path.name for path in fake.calls] == ["one.png", "two.png"]
    assert job.items[0].id != job.items[1].id
    assert all(item.status is BatchItemStatus.COMPLETED for item in job.items)
