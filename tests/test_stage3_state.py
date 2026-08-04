from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest
from PIL import Image

from app.config.settings import AppSettings, load_settings, save_settings
from app.inference.model_loader import TagCategory
from app.prompts.models import TagResult, TagSource
from app.services.tagging_service import TaggingService
from app.state.image_item import ImageItem, ImageStatus
from app.state.project_state import ProjectState, normalized_path_key


def make_image(path: Path, color: str = "red") -> Path:
    Image.new("RGB", (24, 18), color).save(path)
    return path


def build_prompts(tags: list[TagResult] | tuple[TagResult, ...]):
    return TaggingService().rebuild_prompts(tags, AppSettings())


def test_image_item_has_stable_uuid_and_display_name(tmp_path: Path) -> None:
    item = ImageItem(tmp_path / "same.png")
    assert item.id
    assert item.display_name == "same.png"
    assert item.status is ImageStatus.PENDING


def test_image_item_does_not_share_mutable_working_tags(tmp_path: Path) -> None:
    shared = [TagResult("1girl", 0.9, TagCategory.GENERAL)]
    first = ImageItem(tmp_path / "a.png", working_tags=shared)
    second = ImageItem(tmp_path / "b.png", working_tags=shared)
    first.working_tags.clear()
    assert len(second.working_tags) == 1
    assert len(shared) == 1


def test_raw_tags_are_not_changed_by_working_tag_edits(tmp_path: Path) -> None:
    raw = (TagResult("1girl", 0.9, TagCategory.GENERAL),)
    item = ImageItem(tmp_path / "a.png", raw_tags=raw, working_tags=list(raw))
    item.working_tags[0] = replace(item.working_tags[0], name="solo")
    assert item.raw_tags[0].name == "1girl"


def test_prompt_edit_is_preserved_when_generated_prompt_changes(
    tmp_path: Path,
) -> None:
    first = build_prompts([TagResult("1girl", 0.9, TagCategory.GENERAL)])
    second = build_prompts([TagResult("solo", 0.9, TagCategory.GENERAL)])
    item = ImageItem(tmp_path / "a.png")
    item.apply_prompt_result(first, preserve_manual_prompts=False)
    item.edit_prompt("positive", "my manual prompt")
    item.apply_prompt_result(second, preserve_manual_prompts=True)
    assert item.final_positive_prompt == "my manual prompt"
    assert item.generated_positive_prompt == "solo"
    assert item.prompt_stale


def test_restore_generated_prompt_clears_edited_flag(tmp_path: Path) -> None:
    prompts = build_prompts([TagResult("1girl", 0.9, TagCategory.GENERAL)])
    item = ImageItem(tmp_path / "a.png")
    item.apply_prompt_result(prompts, preserve_manual_prompts=False)
    item.edit_prompt("positive", "manual")
    item.restore_generated_prompt("positive")
    assert item.final_positive_prompt == prompts.positive_prompt
    assert not item.positive_prompt_edited


def test_restore_working_tags_copies_raw_tuple(tmp_path: Path) -> None:
    raw = (TagResult("1girl", 0.9, TagCategory.GENERAL),)
    item = ImageItem(tmp_path / "a.png", raw_tags=raw)
    item.restore_working_tags()
    item.working_tags.clear()
    assert len(item.raw_tags) == 1


def test_project_adds_one_supported_image(tmp_path: Path) -> None:
    path = make_image(tmp_path / "a.png")
    result = ProjectState().add_paths([path])
    assert len(result.added) == 1
    assert result.added[0].source_path == path.resolve()


def test_project_adds_multiple_images_in_order(tmp_path: Path) -> None:
    first = make_image(tmp_path / "a.png")
    second = make_image(tmp_path / "b.jpg")
    project = ProjectState()
    project.add_paths([first, second])
    assert [item.display_name for item in project.items] == ["a.png", "b.jpg"]


def test_project_rejects_duplicate_normalized_path(tmp_path: Path) -> None:
    path = make_image(tmp_path / "a.png")
    project = ProjectState()
    project.add_paths([path])
    result = project.add_paths([path.parent / "." / path.name])
    assert not result.added
    assert result.duplicates == (path.parent / "." / path.name,)


def test_project_rejects_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("not an image", encoding="utf-8")
    result = ProjectState().add_paths([path])
    assert result.unsupported == (path,)


def test_project_does_not_scan_directory(tmp_path: Path) -> None:
    make_image(tmp_path / "inside.png")
    result = ProjectState().add_paths([tmp_path])
    assert result.directories == (tmp_path,)
    assert not result.added


def test_project_marks_clipboard_path_temporary(tmp_path: Path) -> None:
    path = make_image(tmp_path / "clip.png")
    result = ProjectState().add_paths([path], temporary_paths=[path])
    assert result.added[0].is_temporary


def test_project_remove_releases_path_for_readding(tmp_path: Path) -> None:
    path = make_image(tmp_path / "a.png")
    project = ProjectState()
    item = project.add_paths([path]).added[0]
    project.remove([item.id])
    assert project.add_paths([path]).added


def test_normalized_path_key_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "a.png"
    assert normalized_path_key(path) == normalized_path_key(path.parent / "." / path.name)


def test_settings_stage3_fields_round_trip_atomically(tmp_path: Path) -> None:
    path = tmp_path / "config" / "settings.json"
    expected = replace(
        AppSettings(),
        model_dir=r"D:\models\wd14",
        device="cpu",
        default_export_format="json",
        recent_open_dir=r"D:\images",
        show_low_confidence=True,
    )
    save_settings(expected, user_path=path)
    loaded = load_settings(user_path=path)
    assert loaded == expected
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 2


def test_failed_settings_replace_leaves_no_temp_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.config.settings as settings_module

    path = tmp_path / "settings.json"

    def fail_replace(_source: object, _target: object) -> None:
        raise PermissionError("denied")

    monkeypatch.setattr(settings_module.os, "replace", fail_replace)
    with pytest.raises(Exception, match="无法安全保存配置"):
        save_settings(AppSettings(), user_path=path)
    assert not list(tmp_path.glob(".settings.json.*.tmp"))


def test_manual_tag_uses_user_source_for_prompt_pipeline() -> None:
    tag = TagResult(
        "custom_tag",
        1.0,
        TagCategory.GENERAL,
        source=TagSource.USER,
    )
    result = build_prompts([tag])
    assert result.positive_tags[0].source is TagSource.USER

