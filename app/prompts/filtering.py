"""Ordered, category-aware tag filtering."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from app.errors import TagProcessingError
from app.inference.model_loader import TagCategory
from app.prompts.models import FilterResult, RemovalRecord, TagResult
from app.prompts.normalizer import (
    NormalizerSettings,
    TagNormalizer,
    canonical_tag_key,
)
from app.prompts.tag_conflicts import CONFLICT_LOOKUP


@dataclass(frozen=True, slots=True)
class FilterSettings:
    general_threshold: float = 0.35
    character_threshold: float = 0.75
    rating_threshold: float = 0.50
    include_character_tags: bool = True
    include_rating: bool = False
    max_tags: int = 80
    minimum_display_threshold: float = 0.10
    excluded_tags: tuple[str, ...] = ()
    always_include_tags: tuple[str, ...] = ()
    remove_duplicates: bool = True
    underscore_to_space: bool = False
    unescape_parentheses: bool = True
    trim_whitespace: bool = True
    collapse_spaces: bool = True
    # Default policy: drop every censor-related token; only "uncensored" may remain.
    block_censored_tags: bool = True
    # Default policy: forbid antonym/conflict pairs such as short_hair + very_long_hair.
    block_antonym_conflicts: bool = True

    def __post_init__(self) -> None:
        for label, value in (
            ("general_threshold", self.general_threshold),
            ("character_threshold", self.character_threshold),
            ("rating_threshold", self.rating_threshold),
            ("minimum_display_threshold", self.minimum_display_threshold),
        ):
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise TagProcessingError(f"{label} 必须是 0 到 1 的有限数值。")
        if (
            isinstance(self.max_tags, bool)
            or not isinstance(self.max_tags, int)
            or self.max_tags < 0
        ):
            raise TagProcessingError("max_tags 必须是大于等于 0 的整数；0 表示不限制。")

    @property
    def normalizer_settings(self) -> NormalizerSettings:
        return NormalizerSettings(
            underscore_to_space=self.underscore_to_space,
            unescape_parentheses=self.unescape_parentheses,
            trim_whitespace=self.trim_whitespace,
            collapse_spaces=self.collapse_spaces,
        )


def is_censored_tag_name(name: str) -> bool:
    """True for censor-related tags that must not enter positive prompts.

    ``uncensored`` (and phrases that start with it) is the only allowed
    censor-family token.
    """

    key = canonical_tag_key(name)
    if not key:
        return False
    if key == "uncensored" or key.startswith("uncensored "):
        return False
    return "censor" in key


def _threshold_for(tag: TagResult, settings: FilterSettings) -> float:
    if tag.category in (TagCategory.CHARACTER, TagCategory.COPYRIGHT):
        category_threshold = settings.character_threshold
    elif tag.category is TagCategory.RATING:
        category_threshold = settings.rating_threshold
    else:
        category_threshold = settings.general_threshold
    return max(category_threshold, settings.minimum_display_threshold)


class TagFilter:
    """Apply the documented eight filtering steps with stable results."""

    def __init__(self, normalizer: TagNormalizer | None = None) -> None:
        self._normalizer = normalizer or TagNormalizer()

    def filter(
        self,
        tags: Iterable[TagResult],
        settings: FilterSettings,
    ) -> FilterResult:
        original = tuple(tags)

        # Step 1: reject any invalid confidence before considering other rules.
        for tag in original:
            confidence = tag.confidence
            if (
                isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not math.isfinite(float(confidence))
                or not 0.0 <= float(confidence) <= 1.0
            ):
                raise TagProcessingError(
                    f"标签 {tag.name!r} 的置信度无效：{confidence!r}；"
                    "必须是 0 到 1 的有限数值。"
                )

        normalized = tuple(
            self._normalizer.normalize_tag(tag, settings.normalizer_settings)
            for tag in original
        )
        reasons: dict[int, str | None] = {index: None for index in range(len(normalized))}

        # Empty labels are explicit removals, never silent output tokens.
        for index, tag in enumerate(normalized):
            if tag.normalized_name is None:
                reasons[index] = "empty_after_normalization"

        # Step 2: category threshold.
        for index, tag in enumerate(normalized):
            if reasons[index] is not None:
                continue
            if not tag.enabled:
                reasons[index] = "disabled"
            elif tag.confidence < _threshold_for(tag, settings):
                reasons[index] = "below_threshold"

        # Step 3: rating inclusion.
        if not settings.include_character_tags:
            for index, tag in enumerate(normalized):
                if (
                    tag.category is TagCategory.CHARACTER
                    and reasons[index] is None
                ):
                    reasons[index] = "character_disabled"

        if not settings.include_rating:
            for index, tag in enumerate(normalized):
                if tag.category is TagCategory.RATING and reasons[index] is None:
                    reasons[index] = "rating_disabled"

        excluded_keys = {
            canonical_tag_key(name)
            for name in settings.excluded_tags
            if isinstance(name, str) and name.strip()
        }
        always_keys = {
            canonical_tag_key(name)
            for name in settings.always_include_tags
            if isinstance(name, str) and name.strip()
        }

        # Step 4: exclusions.
        for index, tag in enumerate(normalized):
            if (
                reasons[index] is None
                and tag.normalized_name is not None
                and canonical_tag_key(tag.normalized_name) in excluded_keys
            ):
                reasons[index] = "excluded"

        # Step 5: always-include applies only to tags actually supplied. It
        # overrides threshold/rating/exclusion, but never a disabled or empty tag.
        for index, tag in enumerate(normalized):
            if (
                tag.enabled
                and tag.normalized_name is not None
                and canonical_tag_key(tag.normalized_name) in always_keys
            ):
                reasons[index] = None

        # Step 5b: default censor policy wins over always-include. Only
        # "uncensored" may survive among censor-family labels.
        if settings.block_censored_tags:
            for index, tag in enumerate(normalized):
                name = tag.normalized_name
                if name is None:
                    continue
                if is_censored_tag_name(name):
                    reasons[index] = "censored_blocked"

        def ranking(index: int) -> tuple[int, float, int]:
            tag = normalized[index]
            assert tag.normalized_name is not None
            pinned = canonical_tag_key(tag.normalized_name) in always_keys
            return (0 if pinned else 1, -tag.confidence, index)

        active = [index for index, reason in reasons.items() if reason is None]
        active.sort(key=ranking)

        # Step 5c: forbid antonym/conflict pairs (e.g. short_hair + very_long_hair).
        # Higher-ranked tags win; later conflicting members are removed.
        if settings.block_antonym_conflicts:
            consistent: list[int] = []
            kept_keys: set[str] = set()
            for index in active:
                name = normalized[index].normalized_name
                assert name is not None
                key = canonical_tag_key(name)
                group = CONFLICT_LOOKUP.get(key)
                if group is not None and any(
                    member in kept_keys for member in group if member != key
                ):
                    reasons[index] = "antonym_conflict"
                    continue
                kept_keys.add(key)
                consistent.append(index)
            active = consistent

        # Step 6: normalized-name deduplication.
        if settings.remove_duplicates:
            unique: list[int] = []
            seen: set[str] = set()
            for index in active:
                name = normalized[index].normalized_name
                assert name is not None
                key = canonical_tag_key(name)
                if key in seen:
                    reasons[index] = "duplicate"
                    continue
                seen.add(key)
                unique.append(index)
            active = unique

        # Step 7: max_tags is applied only after every prior filter.
        # max_tags == 0 means unlimited.
        if settings.max_tags > 0:
            for index in active[settings.max_tags :]:
                reasons[index] = "max_tags"
            active = active[: settings.max_tags]

        # Step 8: ranking is deterministic; ties retain original input order.
        filtered_tags = tuple(normalized[index] for index in active)
        removed_tags = tuple(
            RemovalRecord(normalized[index], reason)
            for index, reason in reasons.items()
            if reason is not None
        )
        excluded_tags = tuple(
            normalized[index]
            for index, reason in reasons.items()
            if reason == "excluded"
        )
        return FilterResult(
            normalized_tags=normalized,
            filtered_tags=filtered_tags,
            removed_tags=removed_tags,
            excluded_tags=excluded_tags,
        )
