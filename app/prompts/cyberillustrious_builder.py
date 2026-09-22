"""Tag-first, context-aware prompt composition for CyberIllustrious."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.inference.model_loader import TagCategory
from app.prompts.models import PromptGroup, RemovalRecord, TagResult, TagSource
from app.prompts.normalizer import canonical_tag_key


_AUTO_STYLE_NOISE = frozenset(
    canonical_tag_key(value)
    for value in (
        "score_9",
        "score_8_up",
        "score_7_up",
        "score_9_up",
        "source_anime",
        "masterpiece",
        "best quality",
        "amazing quality",
        "high quality",
        "absurdres",
        "highres",
        "8k",
        "16k",
        "UHD",
        "HDR",
        "ultra detailed",
        "insanely detailed",
    )
)
_SHOT_TYPES = frozenset(
    canonical_tag_key(value)
    for value in ("close-up", "upper body", "cowboy shot", "full body")
)
_PHOTO_STYLES = frozenset(
    canonical_tag_key(value)
    for value in (
        "realistic photo",
        "RAW photo",
        "editorial photography",
        "photorealistic",
    )
)
_FLAT_STYLES = frozenset(
    canonical_tag_key(value)
    for value in (
        "anime screencap",
        "flat color",
        "cel shading",
        "flat anime coloring",
        "2d",
    )
)
_PEOPLE = frozenset(
    canonical_tag_key(value)
    for value in (
        "1girl",
        "1boy",
        "2girls",
        "2boys",
        "multiple girls",
        "multiple boys",
        "solo",
        "girl",
        "boy",
        "woman",
        "man",
    )
)
_HARD_LIGHT = frozenset(
    canonical_tag_key(value)
    for value in ("hard lighting", "dramatic lighting", "backlighting", "rim light")
)
_SOFT_LIGHT = frozenset(
    canonical_tag_key(value)
    for value in ("soft lighting", "diffused lighting", "overcast")
)
_NIGHT = frozenset(
    canonical_tag_key(value) for value in ("night", "nighttime", "at night")
)
_GROUP_RANK = {
    PromptGroup.COUNT: 0,
    PromptGroup.SUBJECT: 0,
    PromptGroup.CHARACTER: 1,
    PromptGroup.HAIR: 2,
    PromptGroup.EYES_FACE: 2,
    PromptGroup.BODY: 2,
    PromptGroup.EXPRESSION: 3,
    PromptGroup.CLOTHING: 4,
    PromptGroup.ACCESSORIES: 4,
    PromptGroup.POSE_ACTION: 5,
    PromptGroup.COMPOSITION: 6,
    PromptGroup.BACKGROUND: 7,
    PromptGroup.LIGHTING: 8,
    PromptGroup.STYLE: 9,
    PromptGroup.OTHER: 10,
    PromptGroup.QUALITY: 11,
}


def _key(tag: TagResult) -> str:
    return canonical_tag_key(tag.output_name)


def _rank(tag: TagResult) -> int:
    key = _key(tag)
    if key == "looking at viewer" or key == "closed eyes":
        return _GROUP_RANK[PromptGroup.EXPRESSION]
    return _GROUP_RANK.get(tag.prompt_group or PromptGroup.OTHER, 10)


@dataclass(frozen=True, slots=True)
class CyberPositiveBuild:
    tags: tuple[TagResult, ...]
    removed_tags: tuple[RemovalRecord, ...]
    prompt: str


class CyberIllustriousPromptBuilder:
    """Reorder detected tags, resolve conflicts, then add restrained materials."""

    def build(
        self,
        tags: Iterable[TagResult],
        *,
        trigger_word: str | None = None,
        trigger_word_position: str = "first",
    ) -> CyberPositiveBuild:
        source = tuple(tags)
        removed: list[RemovalRecord] = []
        candidates: list[TagResult] = []
        for tag in source:
            key = _key(tag)
            if tag.source is not TagSource.USER and (
                key in _AUTO_STYLE_NOISE
                or key.startswith("score ")
                or key == "source pony"
            ):
                removed.append(RemovalRecord(tag, "cyber_style_filtered"))
            else:
                candidates.append(tag)

        # An orientation such as "portrait" can coexist with a shot size;
        # only mutually exclusive shot-size labels compete by confidence.
        shots = [
            tag
            for tag in candidates
            if tag.source is TagSource.MODEL and _key(tag) in _SHOT_TYPES
        ]
        if len(shots) > 1:
            winner = max(shots, key=lambda tag: tag.confidence)
            for tag in shots:
                if tag is not winner:
                    candidates.remove(tag)
                    removed.append(RemovalRecord(tag, "cyber_composition_conflict"))

        photo = [
            tag
            for tag in candidates
            if tag.source is TagSource.MODEL and _key(tag) in _PHOTO_STYLES
        ]
        flat = [
            tag
            for tag in candidates
            if tag.source is TagSource.MODEL and _key(tag) in _FLAT_STYLES
        ]
        manual_photo = any(
            tag.source is TagSource.USER and _key(tag) in _PHOTO_STYLES
            for tag in candidates
        )
        manual_flat = any(
            tag.source is TagSource.USER and _key(tag) in _FLAT_STYLES
            for tag in candidates
        )
        if manual_photo != manual_flat:
            losing_group = flat if manual_photo else photo
        elif photo and flat:
            losing_group = (
                flat
                if max(tag.confidence for tag in photo)
                > max(tag.confidence for tag in flat)
                else photo
            )
        else:
            losing_group = ()
        for tag in losing_group:
            candidates.remove(tag)
            removed.append(RemovalRecord(tag, "cyber_style_conflict"))

        trigger: TagResult | None = None
        if trigger_word:
            trigger_key = canonical_tag_key(trigger_word)
            for tag in candidates:
                if tag.source is TagSource.USER and _key(tag) == trigger_key:
                    trigger = tag
                    candidates.remove(tag)
                    break

        ordered = [
            tag
            for _, tag in sorted(
                enumerate(candidates),
                key=lambda item: (
                    _rank(item[1]),
                    -item[1].confidence,
                    item[0],
                ),
            )
        ]
        keys = {_key(tag) for tag in ordered}
        strong_flat = any(
            _key(tag) in _FLAT_STYLES
            and (tag.source is TagSource.USER or tag.confidence >= 0.65)
            for tag in ordered
        )
        person = any(
            _key(tag) in _PEOPLE
            or tag.prompt_group is PromptGroup.CHARACTER
            or tag.prompt_group is PromptGroup.HAIR
            or (
                tag.prompt_group is PromptGroup.EYES_FACE
                and _key(tag) != "looking at viewer"
            )
            for tag in ordered
        )
        hair = any(tag.prompt_group is PromptGroup.HAIR for tag in ordered)
        eyes = any(
            tag.prompt_group is PromptGroup.EYES_FACE and "eye" in _key(tag)
            for tag in ordered
        )
        clothing = any(tag.prompt_group is PromptGroup.CLOTHING for tag in ordered)
        has_lighting = any(tag.prompt_group is PromptGroup.LIGHTING for tag in ordered)
        has_scene = any(tag.prompt_group is PromptGroup.BACKGROUND for tag in ordered)
        hard_light = bool(keys & _HARD_LIGHT)
        soft_light = bool(keys & _SOFT_LIGHT)
        night = bool(keys & _NIGHT)

        def enhance(name: str, group: PromptGroup) -> None:
            key = canonical_tag_key(name)
            if key in keys:
                return
            ordered.append(
                TagResult(
                    name=name,
                    confidence=1.0,
                    category=TagCategory.GENERAL,
                    source=TagSource.PRESET,
                    normalized_name=name,
                    prompt_group=group,
                )
            )
            keys.add(key)

        if ordered:
            enhance("semi-realistic", PromptGroup.STYLE)
            if person and not strong_flat:
                enhance("natural skin texture", PromptGroup.STYLE)
            if eyes:
                enhance("detailed eyes", PromptGroup.STYLE)
            if hair:
                enhance("detailed hair", PromptGroup.STYLE)
            if clothing:
                enhance("detailed fabric texture", PromptGroup.STYLE)
            if (person or has_scene) and not strong_flat and not has_lighting:
                enhance("cinematic lighting", PromptGroup.LIGHTING)
            if soft_light and not hard_light and not night and not strong_flat:
                enhance("soft shadows", PromptGroup.LIGHTING)
            if not strong_flat:
                if keys & {"close-up", "portrait"}:
                    enhance("shallow depth of field", PromptGroup.COMPOSITION)
                elif keys & {"upper body", "cowboy shot"}:
                    enhance("depth of field", PromptGroup.COMPOSITION)

        if trigger is not None:
            if trigger_word_position == "last":
                ordered.append(trigger)
            else:
                ordered.insert(0, trigger)
        final_tags = tuple(ordered)
        return CyberPositiveBuild(
            tags=final_tags,
            removed_tags=tuple(removed),
            prompt=", ".join(tag.output_name for tag in final_tags),
        )
