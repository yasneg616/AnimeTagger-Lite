"""Positive prompt profiles without inference or UI dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.config.presets import PromptProfile
from app.inference.model_loader import TagCategory
from app.prompts.models import (
    PromptGroup,
    RemovalRecord,
    TagResult,
    TagSource,
)
from app.prompts.normalizer import (
    NormalizerSettings,
    TagNormalizer,
    canonical_tag_key,
)
from app.prompts.tag_classifier import TagClassifier


@dataclass(frozen=True, slots=True)
class PositiveBuild:
    tags: tuple[TagResult, ...]
    prompt: str
    removed_tags: tuple[RemovalRecord, ...]


class PositivePromptBuilder:
    def __init__(
        self,
        classifier: TagClassifier,
        normalizer: TagNormalizer | None = None,
    ) -> None:
        self._classifier = classifier
        self._normalizer = normalizer or TagNormalizer()

    def _synthetic_tag(
        self,
        name: str,
        *,
        source: TagSource,
        group: PromptGroup,
        normalizer_settings: NormalizerSettings,
    ) -> TagResult | None:
        normalized = self._normalizer.normalize_name(name, normalizer_settings)
        if normalized is None:
            return None
        return TagResult(
            name=name,
            confidence=1.0,
            category=TagCategory.GENERAL,
            enabled=True,
            source=source,
            normalized_name=normalized,
            prompt_group=group,
        )

    def build(
        self,
        tags: Iterable[TagResult],
        *,
        profile: PromptProfile,
        add_profile_prefix: bool,
        trigger_word: str | None,
        trigger_word_position: str = "first",
        remove_tags: Iterable[str],
        normalizer_settings: NormalizerSettings,
    ) -> PositiveBuild:
        source_tags = tuple(tags)
        remove_keys = {
            canonical_tag_key(name)
            for name in (*profile.remove_tags, *tuple(remove_tags))
            if name.strip()
        }

        candidates: list[TagResult] = []
        removed: list[RemovalRecord] = []
        allowed = set(profile.allowed_groups) if profile.allowed_groups is not None else None
        for tag in source_tags:
            if tag.normalized_name is None:
                removed.append(RemovalRecord(tag, "empty_after_normalization"))
                continue
            key = canonical_tag_key(tag.normalized_name)
            if key in remove_keys:
                removed.append(RemovalRecord(tag, "profile_removed"))
                continue
            if allowed is not None and tag.prompt_group not in allowed:
                removed.append(RemovalRecord(tag, "profile_group_filtered"))
                continue
            candidates.append(tag)

        indexed = tuple(enumerate(candidates))
        if profile.sort_mode == "group":
            ordered = list(self._classifier.sort_tags(candidates))
        else:
            ordered = [
                tag
                for _, tag in sorted(
                    indexed,
                    key=lambda item: (-item[1].confidence, item[0]),
                )
            ]

        output: list[TagResult] = []
        trigger: TagResult | None = None
        if trigger_word:
            trigger = self._synthetic_tag(
                trigger_word,
                source=TagSource.USER,
                group=PromptGroup.OTHER,
                normalizer_settings=normalizer_settings,
            )
            if trigger is not None and trigger_word_position == "first":
                output.append(trigger)

        if profile.name != "lora_caption" and add_profile_prefix:
            for prefix in profile.prefix_tags:
                synthetic = self._synthetic_tag(
                    prefix,
                    source=TagSource.PRESET,
                    group=PromptGroup.QUALITY,
                    normalizer_settings=normalizer_settings,
                )
                if synthetic is not None:
                    output.append(synthetic)

        output.extend(ordered)
        if trigger is not None and trigger_word_position == "last":
            output.append(trigger)

        # Prompt output is always clean and stable even if filtering was
        # explicitly configured to keep duplicate model rows.
        unique: list[TagResult] = []
        seen: set[str] = set()
        for tag in output:
            name = tag.output_name
            if not name:
                continue
            key = canonical_tag_key(name)
            if key in seen:
                continue
            seen.add(key)
            unique.append(tag)

        final_tags = tuple(unique)
        return PositiveBuild(
            tags=final_tags,
            prompt=", ".join(tag.output_name for tag in final_tags),
            removed_tags=tuple(removed),
        )
