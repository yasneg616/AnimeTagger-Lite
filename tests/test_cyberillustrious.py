from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.config.presets import NegativePresetCatalog, PromptProfileCatalog
from app.config.settings import AppSettings
from app.inference.model_loader import TagCategory
from app.prompts.models import TagSource
from app.prompts.pipeline import PromptProcessor
from app.prompts.tag_classifier import TagClassifier
from tests.test_prompt_builders import tag


RESOURCE_DIR = Path(__file__).resolve().parents[1] / "resources"


def processor() -> PromptProcessor:
    return PromptProcessor(
        TagClassifier.from_json(RESOURCE_DIR / "tag_categories.json"),
        PromptProfileCatalog.from_json(RESOURCE_DIR / "prompt_profiles.json"),
        NegativePresetCatalog.from_json(RESOURCE_DIR / "negative_presets.json"),
    )


def cyber(**changes: object) -> AppSettings:
    return replace(
        AppSettings(profile="cyberillustrious_semireal", underscore_to_space=True),
        **changes,
    )


def test_person_composer_reorders_visual_tags_and_adds_contextual_materials() -> None:
    result = processor().build(
        [
            tag("indoors", 0.99),
            tag("white_shirt", 0.80),
            tag("1girl", 0.96),
            tag("solo", 0.95),
            tag("long_hair", 0.91),
            tag("black_hair", 0.92),
            tag("brown_eyes", 0.89),
            tag("looking_at_viewer", 0.87),
            tag("smile", 0.86),
            tag("standing", 0.82),
            tag("upper_body", 0.83),
            tag("score_9", 0.98),
            tag("absurdres", 0.97),
        ],
        cyber(),
    )
    values = [item.output_name for item in result.positive_tags]

    assert result.profile_name == "cyberillustrious_semireal"
    assert values[:2] == ["1girl", "solo"]
    assert values.index("black hair") < values.index("smile")
    assert values.index("smile") < values.index("white shirt")
    assert values.index("white shirt") < values.index("standing")
    assert values.index("standing") < values.index("upper body")
    assert values.index("upper body") < values.index("indoors")
    assert "semi-realistic" in values
    assert "natural skin texture" in values
    assert "detailed eyes" in values
    assert "detailed hair" in values
    assert "detailed fabric texture" in values
    assert "cinematic lighting" in values
    assert "depth of field" in values
    assert "score 9" not in values
    assert "absurdres" not in values
    assert "masterpiece" not in result.positive_prompt
    assert all(
        item.source is TagSource.PRESET
        for item in result.positive_tags
        if item.output_name in {
            "semi-realistic",
            "natural skin texture",
            "detailed eyes",
        }
    )


def test_landscape_composer_does_not_invent_person_or_clothing() -> None:
    result = processor().build(
        [
            tag("mountain", 0.94),
            tag("lake", 0.91),
            tag("sunset", 0.89),
            tag("outdoors", 0.88),
            tag("clouds", 0.85),
        ],
        cyber(),
    )

    assert "semi-realistic" in result.positive_prompt
    for unsupported in (
        "natural skin texture",
        "detailed eyes",
        "detailed hair",
        "detailed fabric texture",
        "depth of field",
    ):
        assert unsupported not in result.positive_prompt


def test_flat_anime_style_wins_over_weaker_photo_tag() -> None:
    result = processor().build(
        [
            tag("1girl", 0.95),
            tag("flat_color", 0.90),
            tag("cel_shading", 0.87),
            tag("realistic_photo", 0.72),
            tag("close-up", 0.83),
        ],
        cyber(),
    )

    assert "flat color" in result.positive_prompt
    assert "cel shading" in result.positive_prompt
    assert "realistic photo" not in result.positive_prompt
    assert "semi-realistic" in result.positive_prompt
    assert "natural skin texture" not in result.positive_prompt
    assert "shallow depth of field" not in result.positive_prompt
    assert any(
        record.reason == "cyber_style_conflict" for record in result.removed_tags
    )


def test_user_selected_flat_style_overrides_conflicting_model_photo_tag() -> None:
    result = processor().build(
        [
            tag("1girl", 0.95),
            tag("flat_color", 0.88, source=TagSource.USER),
            tag("realistic_photo", 0.93),
        ],
        cyber(),
    )

    assert "flat color" in result.positive_prompt
    assert "realistic photo" not in result.positive_prompt


def test_conflicting_shot_sizes_keep_the_more_confident_detected_one() -> None:
    result = processor().build(
        [
            tag("1girl", 0.93),
            tag("full_body", 0.72),
            tag("close-up", 0.86),
            tag("portrait", 0.76),
        ],
        cyber(),
    )

    assert "close-up" in result.positive_prompt
    assert "portrait" in result.positive_prompt
    assert "full body" not in result.positive_prompt
    assert any(
        record.tag.name == "full_body"
        and record.reason == "cyber_composition_conflict"
        for record in result.removed_tags
    )


def test_cyber_negative_none_is_empty() -> None:
    result = processor().build(
        [tag("1girl", 0.9)],
        cyber(negative_mode="none"),
    )

    assert result.negative_prompt == ""
    assert result.negative_tags == ()


def test_cyber_negative_basic_uses_the_dedicated_short_preset() -> None:
    result = processor().build(
        [tag("1girl", 0.9)],
        cyber(negative_mode="basic"),
    )

    assert result.negative_prompt.startswith(
        "worst quality, low quality, blurry, bad anatomy"
    )
    assert "plastic skin" in result.negative_prompt
    assert "waxy skin" in result.negative_prompt
    assert result.settings_snapshot["effective_negative_preset"] == (
        "cyberillustrious_short"
    )


def test_cyber_explicit_alternative_negative_preset_is_respected() -> None:
    result = processor().build(
        [tag("1girl", 0.9)],
        cyber(negative_mode="basic", negative_preset="quality_only"),
    )

    assert result.negative_prompt == "low quality, worst quality, blurry"
    assert result.settings_snapshot["effective_negative_preset"] == "quality_only"


def test_cyber_cleanup_detected_reuses_existing_defect_rules() -> None:
    result = processor().build(
        [
            tag("1girl", 0.95),
            tag("watermark", 0.88),
            tag("signature", 0.20),
        ],
        cyber(negative_mode="cleanup_detected"),
    )

    assert "watermark" in result.negative_prompt
    assert "watermark" not in result.positive_prompt
    assert "signature" not in result.negative_prompt
    assert [item.name for item in result.detected_defects] == ["watermark"]
    assert any(
        record.reason == "detected_defect_conflict"
        for record in result.removed_tags
    )


def test_character_identity_and_detected_adult_tags_remain_faithful() -> None:
    result = processor().build(
        [
            tag("1girl", 0.96),
            tag("alice_(wonderland)", 0.94, TagCategory.CHARACTER),
            tag("nude", 0.86),
            tag("explicit", 0.81, TagCategory.RATING),
        ],
        cyber(include_rating=True),
    )
    values = [item.output_name for item in result.positive_tags]

    assert values.index("alice (wonderland)") < values.index("nude")
    assert "nude" in values
    assert "explicit" in values
    assert "sexual intercourse" not in result.positive_prompt
    assert "1girl" in values


def test_manual_score_tags_are_not_silently_filtered() -> None:
    result = processor().build(
        [
            tag("1girl", 0.95),
            tag("score_9", 0.91, source=TagSource.USER),
            tag("score_8_up", 0.90),
            tag("score_6_up", 0.89),
        ],
        cyber(),
    )

    assert "score 9" in result.positive_prompt
    assert "score 8 up" not in result.positive_prompt
    assert "score 6 up" not in result.positive_prompt


def test_manual_score_duplicate_survives_a_higher_confidence_model_row() -> None:
    result = processor().build(
        [
            tag("score_9", 0.99),
            tag("1girl", 0.95),
            tag("score_9", 0.91, source=TagSource.USER),
        ],
        cyber(),
    )

    scores = [
        item
        for item in result.positive_tags
        if item.output_name == "score 9"
    ]
    assert len(scores) == 1
    assert scores[0].source is TagSource.USER
    assert not any(
        record.tag.source is TagSource.USER
        and record.tag.output_name == "score 9"
        for record in result.removed_tags
    )


def test_cyber_trigger_keeps_existing_first_and_last_positions() -> None:
    source = [tag("1girl", 0.95), tag("long_hair", 0.89)]
    first = processor().build(source, cyber(trigger_word="my_style"))
    last = processor().build(
        source,
        cyber(trigger_word="my_style", trigger_word_position="last"),
    )

    assert first.positive_prompt.startswith("my style, 1girl")
    assert last.positive_prompt.endswith(", my style")


@pytest.mark.parametrize(
    ("profile", "expected"),
    (
        ("raw", "1girl, black hair, smile"),
        (
            "anime",
            "masterpiece, best quality, amazing quality, 1girl, black hair, smile",
        ),
        ("pony", "1girl, black hair, smile"),
        ("lora_caption", "1girl, black hair, smile"),
    ),
)
def test_old_tag_modes_keep_their_exact_previous_output(
    profile: str,
    expected: str,
) -> None:
    result = processor().build(
        [
            tag("1girl", 0.91),
            tag("black_hair", 0.83),
            tag("smile", 0.78),
        ],
        replace(AppSettings(), profile=profile, underscore_to_space=True),
    )

    assert result.positive_prompt == expected
    assert result.negative_prompt == ""


def test_old_profile_and_negative_resources_backfill_cyber_without_migration(
    tmp_path: Path,
) -> None:
    profiles = json.loads(
        (RESOURCE_DIR / "prompt_profiles.json").read_text(encoding="utf-8")
    )
    profiles["profiles"].pop("cyberillustrious_semireal")
    profiles["profiles"]["pony"]["prefix_tags"] = ["custom_score"]
    profile_path = tmp_path / "old-profiles.json"
    profile_path.write_text(json.dumps(profiles), encoding="utf-8")
    loaded_profiles = PromptProfileCatalog.from_json(profile_path)

    negatives = json.loads(
        (RESOURCE_DIR / "negative_presets.json").read_text(encoding="utf-8")
    )
    negatives["presets"].pop("cyberillustrious_short")
    negatives["presets"]["basic"] = ["custom basic"]
    negative_path = tmp_path / "old-negatives.json"
    negative_path.write_text(json.dumps(negatives), encoding="utf-8")
    loaded_negatives = NegativePresetCatalog.from_json(negative_path)

    assert not loaded_profiles.used_fallback
    assert loaded_profiles.get("pony").prefix_tags == ("custom_score",)
    assert loaded_profiles.get("cyberillustrious_semireal").prompt_format == (
        "cyberillustrious_semireal"
    )
    assert not loaded_negatives.used_fallback
    assert loaded_negatives.get_preset("basic") == ("custom basic",)
    assert "plastic skin" in loaded_negatives.get_preset("cyberillustrious_short")
    assert AppSettings.from_mapping({}).profile == "raw"
