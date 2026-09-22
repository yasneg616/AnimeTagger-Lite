from __future__ import annotations

from dataclasses import replace
import math

import pytest

from app.errors import TagProcessingError
from app.inference.model_loader import TagCategory
from app.prompts.filtering import (
    FilterSettings,
    TagFilter,
    is_censored_tag_name,
)
from app.prompts.models import TagResult


def tag(
    name: str,
    confidence: float,
    category: TagCategory = TagCategory.GENERAL,
    *,
    enabled: bool = True,
) -> TagResult:
    return TagResult(name, confidence, category, enabled=enabled)


def names(result: object) -> list[str]:
    return [
        item.output_name
        for item in result.filtered_tags  # type: ignore[attr-defined]
    ]


def test_general_threshold_filters_general_only() -> None:
    result = TagFilter().filter(
        [
            tag("keep", 0.5),
            tag("drop", 0.3),
            tag("character", 0.7, TagCategory.CHARACTER),
        ],
        FilterSettings(general_threshold=0.35, character_threshold=0.65),
    )

    assert names(result) == ["character", "keep"]


def test_character_threshold_is_independent_from_general() -> None:
    result = TagFilter().filter(
        [
            tag("general", 0.5),
            tag("character", 0.5, TagCategory.CHARACTER),
        ],
        FilterSettings(general_threshold=0.35, character_threshold=0.75),
    )

    assert names(result) == ["general"]
    assert any(
        record.tag.name == "character" and record.reason == "below_threshold"
        for record in result.removed_tags
    )


def test_rating_is_excluded_by_default() -> None:
    result = TagFilter().filter(
        [tag("safe", 0.99, TagCategory.RATING), tag("solo", 0.8)],
        FilterSettings(),
    )

    assert names(result) == ["solo"]
    assert result.removed_tags[0].reason == "rating_disabled"


def test_censored_tags_blocked_by_default_uncensored_allowed() -> None:
    result = TagFilter().filter(
        [
            tag("1girl", 0.9),
            tag("censored", 0.9),
            tag("mosaic_censoring", 0.9),
            tag("bar_censor", 0.95),
            tag("uncensored", 0.8),
            tag("uncensored_version", 0.8),
        ],
        FilterSettings(),
    )

    assert names(result) == ["1girl", "uncensored", "uncensored_version"]
    blocked = {
        record.tag.name
        for record in result.removed_tags
        if record.reason == "censored_blocked"
    }
    assert blocked == {"censored", "mosaic_censoring", "bar_censor"}


def test_censored_block_overrides_always_include() -> None:
    result = TagFilter().filter(
        [tag("censored", 0.9), tag("solo", 0.8)],
        FilterSettings(always_include_tags=("censored",)),
    )

    assert names(result) == ["solo"]
    assert any(
        record.tag.name == "censored" and record.reason == "censored_blocked"
        for record in result.removed_tags
    )


def test_antonym_conflicts_are_blocked_by_default() -> None:
    result = TagFilter().filter(
        [
            tag("short_hair", 0.9),
            tag("very_long_hair", 0.8),
            tag("1girl", 0.95),
            tag("2girls", 0.7),
        ],
        FilterSettings(),
    )

    assert names(result) == ["1girl", "short_hair"]
    reasons = {
        record.tag.name: record.reason
        for record in result.removed_tags
        if record.reason == "antonym_conflict"
    }
    assert "very_long_hair" in reasons
    assert "2girls" in reasons


def test_antonym_conflicts_can_be_disabled() -> None:
    result = TagFilter().filter(
        [
            tag("short_hair", 0.9),
            tag("very_long_hair", 0.8),
        ],
        FilterSettings(block_antonym_conflicts=False),
    )
    assert "short_hair" in names(result)
    assert "very_long_hair" in names(result)


def test_block_censored_tags_can_be_disabled() -> None:
    result = TagFilter().filter(
        [tag("censored", 0.9), tag("uncensored", 0.8)],
        FilterSettings(block_censored_tags=False),
    )

    assert names(result) == ["censored", "uncensored"]


def test_is_censored_tag_name_classification() -> None:
    assert is_censored_tag_name("censored")
    assert is_censored_tag_name("Mosaic_Censoring")
    assert is_censored_tag_name("bar censor")
    assert not is_censored_tag_name("uncensored")
    assert not is_censored_tag_name("uncensored focus")
    assert not is_censored_tag_name("1girl")


def test_include_rating_keeps_rating_above_its_own_threshold() -> None:
    result = TagFilter().filter(
        [
            tag("safe", 0.6, TagCategory.RATING),
            tag("questionable", 0.4, TagCategory.RATING),
        ],
        FilterSettings(include_rating=True, rating_threshold=0.5),
    )

    assert names(result) == ["safe"]


def test_max_tags_runs_after_threshold_filtering() -> None:
    result = TagFilter().filter(
        [tag("low", 0.2), tag("high", 0.9), tag("middle", 0.8)],
        FilterSettings(general_threshold=0.35, max_tags=1),
    )

    assert names(result) == ["high"]
    reasons = {record.tag.name: record.reason for record in result.removed_tags}
    assert reasons == {"low": "below_threshold", "middle": "max_tags"}


def test_max_tags_zero_means_unlimited() -> None:
    tags = [tag(f"t{i}", 0.9 - i * 0.001) for i in range(200)]
    result = TagFilter().filter(tags, FilterSettings(max_tags=0))
    assert len(names(result)) == 200
    assert not any(r.reason == "max_tags" for r in result.removed_tags)


def test_underscore_normalization_and_deduplication() -> None:
    result = TagFilter().filter(
        [tag("long_hair", 0.9), tag("long hair", 0.8)],
        FilterSettings(underscore_to_space=True),
    )

    assert names(result) == ["long hair"]
    assert any(record.reason == "duplicate" for record in result.removed_tags)


def test_empty_tag_is_explicitly_removed() -> None:
    result = TagFilter().filter(
        [tag("   ", 0.9), tag("solo", 0.8)],
        FilterSettings(),
    )

    assert names(result) == ["solo"]
    assert result.removed_tags[0].reason == "empty_after_normalization"


def test_excluded_tag_is_recorded() -> None:
    result = TagFilter().filter(
        [tag("solo", 0.9), tag("1girl", 0.8)],
        FilterSettings(excluded_tags=("solo",)),
    )

    assert names(result) == ["1girl"]
    assert [item.output_name for item in result.excluded_tags] == ["solo"]


def test_always_include_overrides_threshold_rating_and_exclusion() -> None:
    result = TagFilter().filter(
        [
            tag("low_tag", 0.05),
            tag("safe", 0.2, TagCategory.RATING),
        ],
        FilterSettings(
            excluded_tags=("low tag",),
            always_include_tags=("low_tag", "safe"),
            underscore_to_space=True,
        ),
    )

    assert names(result) == ["safe", "low tag"]
    assert result.excluded_tags == ()


def test_disabled_tag_is_not_revived_by_always_include() -> None:
    result = TagFilter().filter(
        [tag("solo", 0.9, enabled=False)],
        FilterSettings(always_include_tags=("solo",)),
    )

    assert names(result) == []
    assert result.removed_tags[0].reason == "disabled"


def test_minimum_display_threshold_is_a_lower_bound() -> None:
    result = TagFilter().filter(
        [tag("tiny", 0.08), tag("visible", 0.12)],
        FilterSettings(general_threshold=0.0, minimum_display_threshold=0.1),
    )

    assert names(result) == ["visible"]


def test_equal_scores_keep_input_order() -> None:
    result = TagFilter().filter(
        [tag("first", 0.8), tag("second", 0.8), tag("third", 0.8)],
        FilterSettings(),
    )

    assert names(result) == ["first", "second", "third"]


def test_remove_duplicates_can_be_disabled() -> None:
    result = TagFilter().filter(
        [tag("solo", 0.9), tag("solo", 0.8)],
        FilterSettings(remove_duplicates=False),
    )

    assert names(result) == ["solo", "solo"]


@pytest.mark.parametrize(
    "confidence",
    [math.nan, math.inf, -math.inf, -0.01, 1.01],
)
def test_invalid_confidence_raises(confidence: float) -> None:
    with pytest.raises(TagProcessingError, match="置信度无效"):
        TagFilter().filter([tag("bad", confidence)], FilterSettings())


@pytest.mark.parametrize(
    "changes",
    [
        {"general_threshold": math.nan},
        {"character_threshold": 1.1},
        {"rating_threshold": -0.1},
        {"minimum_display_threshold": math.inf},
        {"max_tags": -1},
        {"max_tags": 1.5},
    ],
)
def test_invalid_filter_settings_raise(changes: dict[str, object]) -> None:
    with pytest.raises(TagProcessingError):
        replace(FilterSettings(), **changes)
