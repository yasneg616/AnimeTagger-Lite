"""One prompt-processing pipeline reused by CLI, export, and future UI."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from app.config.presets import NegativePresetCatalog, PromptProfileCatalog
from app.config.settings import AppSettings
from app.inference.wd14_engine import TagPrediction
from app.prompts.filtering import FilterSettings, TagFilter
from app.prompts.models import (
    FilterResult,
    PromptBuildResult,
    RemovalRecord,
    TagResult,
    TagSource,
)
from app.prompts.negative_builder import NegativeMode, NegativePromptBuilder
from app.prompts.normalizer import NormalizerSettings, canonical_tag_key
from app.prompts.positive_builder import PositivePromptBuilder
from app.prompts.tag_classifier import TagClassifier


def tag_results_from_predictions(
    predictions: Iterable[TagPrediction],
) -> tuple[TagResult, ...]:
    return tuple(
        TagResult(
            name=prediction.tag.name,
            confidence=prediction.confidence,
            category=prediction.tag.category,
            enabled=True,
            source=TagSource.MODEL,
            model_index=prediction.tag.index,
        )
        for prediction in predictions
    )


class PromptProcessor:
    def __init__(
        self,
        classifier: TagClassifier,
        profiles: PromptProfileCatalog,
        negative_presets: NegativePresetCatalog,
        tag_filter: TagFilter | None = None,
    ) -> None:
        self._classifier = classifier
        self._profiles = profiles
        self._negative_presets = negative_presets
        self._filter = tag_filter or TagFilter()
        self._positive_builder = PositivePromptBuilder(classifier)
        self._negative_builder = NegativePromptBuilder(negative_presets)
        # GUI quick settings often rebuild the same 10,861 WD14 tags while
        # changing only profile or negative-prompt options. Keep one prepared
        # tag set so those changes do not repeatedly normalize, classify, and
        # allocate removal records for every model output.
        self._prepared_source: tuple[TagResult, ...] | None = None
        self._prepared_settings: FilterSettings | None = None
        self._prepared_filter_result: FilterResult | None = None
        self._prepared_raw_classified: tuple[TagResult, ...] | None = None
        self._prepared_filtered_classified: tuple[TagResult, ...] | None = None

    def _assign_groups_reusing_prepared(
        self,
        tags: Iterable[TagResult],
        prepared_ids: set[int],
    ) -> tuple[TagResult, ...]:
        values = tuple(tags)
        return tuple(
            tag
            if id(tag) in prepared_ids and tag.prompt_group is not None
            else replace(tag, prompt_group=self._classifier.classify(tag))
            for tag in values
        )

    def _prepare_tags(
        self,
        raw_tags: Iterable[TagResult],
        settings: FilterSettings,
    ) -> tuple[
        FilterResult,
        tuple[TagResult, ...],
        tuple[TagResult, ...],
    ]:
        source = tuple(raw_tags)
        if (
            self._prepared_source is not None
            and self._prepared_settings == settings
            and source == self._prepared_source
        ):
            assert self._prepared_filter_result is not None
            assert self._prepared_raw_classified is not None
            assert self._prepared_filtered_classified is not None
            return (
                self._prepared_filter_result,
                self._prepared_raw_classified,
                self._prepared_filtered_classified,
            )

        prepared_ids = {
            id(tag) for tag in (self._prepared_raw_classified or ())
        }
        filter_result = self._filter.filter(source, settings)
        raw_classified = self._assign_groups_reusing_prepared(
            filter_result.normalized_tags,
            prepared_ids,
        )
        filtered_classified = self._assign_groups_reusing_prepared(
            filter_result.filtered_tags,
            prepared_ids,
        )
        # PromptBuildResult.raw_tags becomes ImageItem.working_tags. Cache that
        # exact immutable sequence so subsequent GUI rebuilds are fast.
        self._prepared_source = raw_classified
        self._prepared_settings = settings
        self._prepared_filter_result = filter_result
        self._prepared_raw_classified = raw_classified
        self._prepared_filtered_classified = filtered_classified
        return filter_result, raw_classified, filtered_classified

    def build(
        self,
        raw_tags: Iterable[TagResult],
        settings: AppSettings,
    ) -> PromptBuildResult:
        filter_result, raw_classified, filtered_classified = self._prepare_tags(
            raw_tags,
            settings.to_filter_settings(),
        )
        profile = self._profiles.get(settings.profile)
        normalizer_settings = NormalizerSettings(
            underscore_to_space=settings.underscore_to_space,
            unescape_parentheses=settings.unescape_parentheses,
            trim_whitespace=settings.trim_whitespace,
            collapse_spaces=settings.collapse_spaces,
        )

        positive = self._positive_builder.build(
            filtered_classified,
            profile=profile,
            add_profile_prefix=settings.add_profile_prefix,
            trigger_word=settings.trigger_word,
            trigger_word_position=settings.trigger_word_position,
            remove_tags=settings.remove_tags,
            normalizer_settings=normalizer_settings,
        )

        effective_negative_mode = (
            NegativeMode.NONE
            if profile.name == "lora_caption"
            else NegativeMode(settings.negative_mode)
        )
        negative = self._negative_builder.build(
            raw_classified,
            mode=effective_negative_mode,
            preset_name=settings.negative_preset,
            defect_threshold=settings.defect_threshold,
            user_terms=settings.user_negative_tags,
            normalizer_settings=normalizer_settings,
        )

        positive_tags = positive.tags
        conflict_removals: list[RemovalRecord] = []
        if effective_negative_mode is NegativeMode.CLEANUP_DETECTED:
            defect_keys = {
                canonical_tag_key(tag.output_name)
                for tag in negative.detected_defects
                if tag.output_name
            }
            kept: list[TagResult] = []
            for tag in positive_tags:
                if (
                    tag.source is TagSource.MODEL
                    and tag.output_name
                    and canonical_tag_key(tag.output_name) in defect_keys
                ):
                    conflict_removals.append(
                        RemovalRecord(tag, "detected_defect_conflict")
                    )
                else:
                    kept.append(tag)
            positive_tags = tuple(kept)

        removed_records = tuple(
            (*filter_result.removed_tags, *positive.removed_tags, *conflict_removals)
        )
        excluded_classified = self._classifier.assign_groups(
            filter_result.excluded_tags
        )
        snapshot = settings.snapshot()
        snapshot["effective_negative_mode"] = effective_negative_mode.value
        return PromptBuildResult(
            raw_tags=raw_classified,
            filtered_tags=filtered_classified,
            positive_tags=positive_tags,
            negative_tags=negative.tags,
            positive_prompt=", ".join(tag.output_name for tag in positive_tags),
            negative_prompt=negative.prompt,
            removed_tags=removed_records,
            excluded_tags=excluded_classified,
            detected_defects=negative.detected_defects,
            profile_name=profile.name,
            settings_snapshot=snapshot,
        )
