"""Rule-only negative prompt generation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Iterable

from app.config.presets import NegativePresetCatalog
from app.errors import TagProcessingError
from app.prompts.models import (
    NegativeTag,
    NegativeTagSource,
    TagResult,
    TagSource,
)
from app.prompts.normalizer import (
    NormalizerSettings,
    TagNormalizer,
    canonical_tag_key,
)

MAX_NEGATIVE_TAGS = 64


class NegativeMode(str, Enum):
    NONE = "none"
    BASIC = "basic"
    CLEANUP_DETECTED = "cleanup_detected"


@dataclass(frozen=True, slots=True)
class NegativeBuild:
    tags: tuple[NegativeTag, ...]
    prompt: str
    detected_defects: tuple[TagResult, ...]


class NegativePromptBuilder:
    def __init__(
        self,
        catalog: NegativePresetCatalog,
        normalizer: TagNormalizer | None = None,
    ) -> None:
        self._catalog = catalog
        self._normalizer = normalizer or TagNormalizer()

    def build(
        self,
        raw_tags: Iterable[TagResult],
        *,
        mode: NegativeMode,
        preset_name: str,
        defect_threshold: float,
        user_terms: Iterable[str],
        normalizer_settings: NormalizerSettings,
    ) -> NegativeBuild:
        if not math.isfinite(defect_threshold) or not 0.0 <= defect_threshold <= 1.0:
            raise TagProcessingError("缺陷标签阈值必须是 0 到 1 的有限数值。")
        if mode is NegativeMode.NONE:
            return NegativeBuild((), "", ())

        terms: list[NegativeTag] = []
        preset_values = self._catalog.get_preset(preset_name)
        for value in preset_values:
            normalized = self._normalizer.normalize_name(value, normalizer_settings)
            if normalized:
                terms.append(
                    NegativeTag(
                        normalized,
                        (NegativeTagSource.PRESET,),
                    )
                )

        detected: tuple[TagResult, ...] = ()
        if mode is NegativeMode.CLEANUP_DETECTED:
            defect_keys = {
                canonical_tag_key(value) for value in self._catalog.defect_tags
            }
            candidates: list[tuple[int, TagResult]] = []
            for index, tag in enumerate(raw_tags):
                if tag.source is not TagSource.MODEL or not tag.enabled:
                    continue
                if (
                    not math.isfinite(tag.confidence)
                    or not 0.0 <= tag.confidence <= 1.0
                ):
                    raise TagProcessingError(
                        f"标签 {tag.name!r} 的置信度无效：{tag.confidence!r}"
                    )
                if (
                    tag.output_name
                    and tag.confidence >= defect_threshold
                    and canonical_tag_key(tag.output_name) in defect_keys
                ):
                    candidates.append((index, tag))
            candidates.sort(key=lambda item: (-item[1].confidence, item[0]))
            unique_detected: list[TagResult] = []
            seen_defects: set[str] = set()
            for _, tag in candidates:
                key = canonical_tag_key(tag.output_name)
                if key in seen_defects:
                    continue
                seen_defects.add(key)
                unique_detected.append(tag)
            detected = tuple(unique_detected)
            for tag in detected:
                terms.append(
                    NegativeTag(
                        tag.output_name,
                        (NegativeTagSource.DETECTED_DEFECT,),
                        confidence=tag.confidence,
                        source_tag=tag.name,
                    )
                )

        for value in user_terms:
            normalized = self._normalizer.normalize_name(value, normalizer_settings)
            if normalized:
                terms.append(
                    NegativeTag(
                        normalized,
                        (NegativeTagSource.USER,),
                    )
                )

        # Stable deduplication merges provenance instead of losing it.
        unique: list[NegativeTag] = []
        positions: dict[str, int] = {}
        for term in terms:
            key = canonical_tag_key(term.name)
            existing_index = positions.get(key)
            if existing_index is None:
                positions[key] = len(unique)
                unique.append(term)
                continue
            existing = unique[existing_index]
            merged_sources = tuple(dict.fromkeys((*existing.sources, *term.sources)))
            confidence_values = tuple(
                value
                for value in (existing.confidence, term.confidence)
                if value is not None
            )
            unique[existing_index] = NegativeTag(
                name=existing.name,
                sources=merged_sources,
                confidence=max(confidence_values) if confidence_values else None,
                source_tag=existing.source_tag or term.source_tag,
            )

        if len(unique) > MAX_NEGATIVE_TAGS:
            raise TagProcessingError(
                f"反向提示词去重后有 {len(unique)} 个标签，"
                f"超过安全上限 {MAX_NEGATIVE_TAGS}。"
            )
        final_tags = tuple(unique)
        return NegativeBuild(
            tags=final_tags,
            prompt=", ".join(tag.name for tag in final_tags),
            detected_defects=detected,
        )
