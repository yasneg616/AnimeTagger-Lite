from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from app.config.presets import (
    NegativePresetCatalog,
    PromptProfile,
    PromptProfileCatalog,
)
from app.config.settings import AppSettings
from app.inference.model_loader import TagCategory
from app.prompts.filtering import TagFilter
from app.prompts.models import (
    NegativeTagSource,
    PromptBuildResult,
    PromptGroup,
    TagResult,
    TagSource,
)
from app.prompts.pipeline import PromptProcessor
from app.prompts.tag_classifier import TagClassifier

RESOURCE_DIR = Path(__file__).resolve().parents[1] / "resources"


def tag(
    name: str,
    confidence: float,
    category: TagCategory = TagCategory.GENERAL,
    *,
    source: TagSource = TagSource.MODEL,
) -> TagResult:
    return TagResult(name, confidence, category, source=source)


def processor(
    *,
    profiles: PromptProfileCatalog | None = None,
    negatives: NegativePresetCatalog | None = None,
) -> PromptProcessor:
    return PromptProcessor(
        TagClassifier.from_json(RESOURCE_DIR / "tag_categories.json"),
        profiles
        or PromptProfileCatalog.from_json(RESOURCE_DIR / "prompt_profiles.json"),
        negatives
        or NegativePresetCatalog.from_json(
            RESOURCE_DIR / "negative_presets.json"
        ),
    )


class CountingTagFilter(TagFilter):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def filter(self, tags, settings):
        self.calls += 1
        return super().filter(tags, settings)


def test_profile_rebuild_reuses_prepared_filtering_and_edit_invalidates() -> None:
    counting_filter = CountingTagFilter()
    prompt_processor = PromptProcessor(
        TagClassifier.from_json(RESOURCE_DIR / "tag_categories.json"),
        PromptProfileCatalog.from_json(RESOURCE_DIR / "prompt_profiles.json"),
        NegativePresetCatalog.from_json(
            RESOURCE_DIR / "negative_presets.json"
        ),
        tag_filter=counting_filter,
    )
    first = prompt_processor.build(
        [tag("1girl", 0.9), tag("long_hair", 0.8)],
        AppSettings(),
    )

    rebuilt = prompt_processor.build(
        first.raw_tags,
        replace(AppSettings(), profile="anime"),
    )

    assert counting_filter.calls == 1
    assert rebuilt.positive_prompt.startswith("masterpiece")

    edited = list(rebuilt.raw_tags)
    edited[0] = replace(
        edited[0],
        name="2girls",
        normalized_name=None,
        prompt_group=None,
    )
    updated = prompt_processor.build(edited, AppSettings())

    assert counting_filter.calls == 2
    assert "2girls" in updated.positive_prompt


def test_raw_profile_uses_filtered_normalized_confidence_order() -> None:
    settings = replace(AppSettings(), underscore_to_space=True)

    result = processor().build(
        [tag("1girl", 0.8), tag("long_hair", 0.9)],
        settings,
    )

    assert result.positive_prompt == "long hair, 1girl"
    assert result.negative_prompt == ""
    assert all(item.source is TagSource.MODEL for item in result.positive_tags)


def test_anime_profile_adds_quality_prefix_and_group_order() -> None:
    settings = replace(AppSettings(), profile="anime")

    result = processor().build(
        [
            tag("simple background", 0.99),
            tag("1girl", 0.6),
            tag("blue_eyes", 0.8),
        ],
        settings,
    )

    assert result.positive_prompt.startswith(
        "masterpiece, best quality, amazing quality, 1girl"
    )
    assert result.positive_prompt.endswith("simple background")


def test_existing_quality_tag_does_not_duplicate_profile_prefix() -> None:
    settings = replace(AppSettings(), profile="anime")

    result = processor().build([tag("masterpiece", 0.9)], settings)

    assert result.positive_prompt.split(", ").count("masterpiece") == 1


def test_anime_prefix_can_be_disabled() -> None:
    settings = replace(
        AppSettings(),
        profile="anime",
        add_profile_prefix=False,
    )

    result = processor().build([tag("1girl", 0.9)], settings)

    assert result.positive_prompt == "1girl"


def test_pony_uses_editable_custom_prefix() -> None:
    custom_profiles = PromptProfileCatalog(
        {
            "pony": PromptProfile(
                "pony",
                ("score_9", "score_8_up"),
                True,
                "group",
            )
        }
    )
    settings = replace(
        AppSettings(),
        profile="pony",
        underscore_to_space=True,
    )

    result = processor(profiles=custom_profiles).build(
        [tag("1girl", 0.9)],
        settings,
    )

    assert result.positive_prompt == "score 9, score 8 up, 1girl"


def test_lora_caption_never_adds_quality_or_negative() -> None:
    settings = replace(
        AppSettings(),
        profile="lora_caption",
        negative_mode="basic",
    )

    result = processor().build(
        [tag("masterpiece", 0.99), tag("1girl", 0.9), tag("long hair", 0.8)],
        settings,
    )

    assert "masterpiece" not in result.positive_prompt
    assert result.positive_prompt == "1girl, long hair"
    assert result.negative_prompt == ""
    assert result.settings_snapshot["effective_negative_mode"] == "none"


def test_krea2_profile_builds_structured_natural_language() -> None:
    settings = replace(
        AppSettings(),
        profile="krea2",
        underscore_to_space=True,
    )

    result = processor().build(
        [
            tag("masterpiece", 0.99),
            tag("1girl", 0.98),
            tag("long_hair", 0.95),
            tag("blue_eyes", 0.94),
            tag("school_uniform", 0.93),
            tag("standing", 0.92),
            tag("smile", 0.91),
            tag("close-up", 0.90),
            tag("city", 0.89),
            tag("night", 0.88),
            tag("rim_light", 0.87),
            tag("digital_art", 0.86),
            tag("black_jacket", 0.85),
        ],
        settings,
    )

    assert result.profile_name == "krea2"
    assert result.positive_prompt.startswith(
        "A close-up anime illustration depicting one female character."
    )
    assert "Their appearance includes long hair and blue eyes." in result.positive_prompt
    assert "Their clothing and accessories include school uniform." in result.positive_prompt
    assert "a standing pose and a gentle smile" in result.positive_prompt
    assert "an urban environment and a nighttime atmosphere" in result.positive_prompt
    assert "a distinct rim light around the subject" in result.positive_prompt
    assert "Rendered as digital illustration." in result.positive_prompt
    assert "black jacket" in result.positive_prompt
    assert "masterpiece" not in result.positive_prompt
    assert "_" not in result.positive_prompt
    assert len(result.positive_prompt.split("\n\n")) >= 8
    assert {item.output_name for item in result.positive_tags} == {
        "1girl",
        "long hair",
        "blue eyes",
        "school uniform",
        "standing",
        "smile",
        "close-up",
        "city",
        "night",
        "rim light",
        "digital art",
        "black jacket",
    }


def test_krea2_profile_uses_short_optional_negative_preset() -> None:
    settings = replace(
        AppSettings(),
        profile="krea2",
        negative_mode="basic",
        negative_preset="krea2_short",
    )

    result = processor().build([tag("1girl", 0.9)], settings)

    assert result.negative_prompt == (
        "extra limbs, malformed hands, duplicated subjects, text, watermark"
    )


def test_krea2_profile_keeps_trigger_position_and_empty_input_semantics() -> None:
    settings = replace(
        AppSettings(),
        profile="krea2",
        trigger_word="my_style",
        trigger_word_position="last",
        underscore_to_space=True,
    )

    result = processor().build([tag("1girl", 0.9)], settings)
    empty = processor().build(
        [tag("masterpiece", 0.9)],
        replace(AppSettings(), profile="krea2"),
    )

    assert result.positive_prompt.endswith("\n\nmy style.")
    assert empty.positive_prompt == ""


def test_trigger_word_is_first() -> None:
    settings = replace(
        AppSettings(),
        profile="lora_caption",
        trigger_word="my_character",
        underscore_to_space=True,
    )

    result = processor().build([tag("1girl", 0.9)], settings)

    assert result.positive_prompt == "my character, 1girl"
    assert result.positive_tags[0].source is TagSource.USER


def test_lora_remove_tag_removes_fixed_generic_tag() -> None:
    settings = replace(
        AppSettings(),
        profile="lora_caption",
        remove_tags=("solo",),
    )

    result = processor().build(
        [tag("solo", 0.9), tag("1girl", 0.8)],
        settings,
    )

    assert result.positive_prompt == "1girl"
    assert any(
        record.tag.name == "solo" and record.reason == "profile_removed"
        for record in result.removed_tags
    )


def test_negative_none_returns_empty() -> None:
    result = processor().build(
        [tag("1girl", 0.9)],
        AppSettings(),
    )

    assert result.negative_tags == ()
    assert result.negative_prompt == ""


def test_negative_basic_reads_preset() -> None:
    settings = replace(AppSettings(), negative_mode="basic")

    result = processor().build([tag("1girl", 0.9)], settings)

    assert result.negative_prompt.startswith("low quality, worst quality, blurry")
    assert all(
        NegativeTagSource.PRESET in item.sources for item in result.negative_tags
    )


def test_cleanup_detected_uses_only_actual_high_confidence_defects() -> None:
    settings = replace(
        AppSettings(),
        negative_mode="cleanup_detected",
        negative_preset="quality_only",
        defect_threshold=0.35,
    )

    result = processor().build(
        [
            tag("watermark", 0.8),
            tag("signature", 0.2),
            tag("1girl", 0.9),
        ],
        settings,
    )

    assert [item.name for item in result.detected_defects] == ["watermark"]
    assert "watermark" in result.negative_prompt
    assert "signature" not in result.negative_prompt
    assert "logo" not in result.negative_prompt


def test_low_confidence_tags_are_never_inverted() -> None:
    settings = replace(
        AppSettings(),
        negative_mode="cleanup_detected",
        negative_preset="quality_only",
        defect_threshold=0.5,
    )

    result = processor().build(
        [tag("censored", 0.49), tag("extra fingers", 0.01)],
        settings,
    )

    assert "censored" not in result.negative_prompt
    assert "extra fingers" not in result.negative_prompt


def test_detected_defect_is_removed_from_positive_but_raw_is_preserved() -> None:
    original = (
        tag("watermark", 0.9),
        tag("1girl", 0.8),
    )
    settings = replace(
        AppSettings(),
        negative_mode="cleanup_detected",
        negative_preset="quality_only",
    )

    result = processor().build(original, settings)

    assert "watermark" not in result.positive_prompt
    assert "watermark" in result.negative_prompt
    assert [item.name for item in result.raw_tags] == ["watermark", "1girl"]
    assert original[0].normalized_name is None
    assert any(
        record.reason == "detected_defect_conflict"
        for record in result.removed_tags
    )


def test_duplicate_negative_term_merges_stable_sources() -> None:
    settings = replace(
        AppSettings(),
        negative_mode="cleanup_detected",
        negative_preset="basic",
    )

    result = processor().build([tag("watermark", 0.9)], settings)
    watermark = next(item for item in result.negative_tags if item.name == "watermark")

    assert watermark.sources == (
        NegativeTagSource.PRESET,
        NegativeTagSource.DETECTED_DEFECT,
    )
    assert result.negative_prompt.split(", ").count("watermark") == 1


def test_duplicate_detected_defect_is_recorded_once() -> None:
    settings = replace(
        AppSettings(),
        negative_mode="cleanup_detected",
        negative_preset="quality_only",
    )

    result = processor().build(
        [tag("watermark", 0.9), tag("watermark", 0.8)],
        settings,
    )

    assert [item.name for item in result.detected_defects] == ["watermark"]


def test_user_negative_terms_are_stably_deduplicated() -> None:
    settings = replace(
        AppSettings(),
        negative_mode="basic",
        user_negative_tags=("custom issue", "blurry"),
    )

    result = processor().build([tag("1girl", 0.9)], settings)

    assert result.negative_prompt.endswith("custom issue")
    blurry = next(item for item in result.negative_tags if item.name == "blurry")
    assert blurry.sources == (
        NegativeTagSource.PRESET,
        NegativeTagSource.USER,
    )


def test_prompt_groups_are_attached_to_exportable_tags() -> None:
    result = processor().build(
        [tag("1girl", 0.9), tag("blue eyes", 0.8)],
        AppSettings(),
    )

    assert [item.prompt_group for item in result.filtered_tags] == [
        PromptGroup.COUNT,
        PromptGroup.EYES_FACE,
    ]


def test_settings_snapshot_is_independent_of_source_mapping() -> None:
    source = {"nested": {"value": 1}}
    result = PromptBuildResult(
        raw_tags=(),
        filtered_tags=(),
        positive_tags=(),
        negative_tags=(),
        positive_prompt="",
        negative_prompt="",
        removed_tags=(),
        excluded_tags=(),
        detected_defects=(),
        profile_name="raw",
        settings_snapshot=source,
    )

    source["nested"]["value"] = 2

    assert result.settings_snapshot["nested"]["value"] == 1


def test_prompt_build_result_fields_are_consistent() -> None:
    result = processor().build(
        [tag("solo", 0.9), tag("1girl", 0.8)],
        AppSettings(),
    )

    assert result.positive_prompt == ", ".join(
        item.output_name for item in result.positive_tags
    )
    assert result.negative_prompt == ", ".join(
        item.name for item in result.negative_tags
    )
    assert result.profile_name == "raw"
