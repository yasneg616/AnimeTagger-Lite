"""Deterministic natural-language prompt formatting for Krea 2."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from app.prompts.models import PromptGroup, TagResult, TagSource
from app.prompts.normalizer import canonical_tag_key


_COUNT_SUBJECTS = {
    "1girl": "one female character",
    "1boy": "one male character",
    "2girls": "two female characters",
    "2boys": "two male characters",
    "multiple girls": "multiple female characters",
    "multiple boys": "multiple male characters",
    "solo": "a single character",
}

_SHOT_OPENINGS = {
    "portrait": "A portrait-format anime illustration",
    "upper body": "An upper-body anime illustration",
    "full body": "A full-body anime illustration",
    "cowboy shot": "A cowboy-shot anime illustration",
    "close-up": "A close-up anime illustration",
}

_COMPOSITION_PHRASES = {
    "from above": "a high-angle viewpoint",
    "from below": "a low-angle viewpoint",
    "depth of field": "selective focus and visible depth of field",
}

_BACKGROUND_PHRASES = {
    "simple background": "a simple, uncluttered background",
    "white background": "a clean white background",
    "outdoors": "an outdoor setting",
    "indoors": "an indoor setting",
    "city": "an urban environment",
    "forest": "a forest environment",
    "sky": "an open sky",
    "night": "a nighttime atmosphere",
}

_LIGHTING_PHRASES = {
    "backlighting": "directional backlighting",
    "rim light": "a distinct rim light around the subject",
    "sunlight": "natural sunlight",
    "dramatic lighting": "dramatic directional light with readable shadow shapes",
    "soft lighting": "soft directional light with gentle edge transitions",
}

_ACTION_PHRASES = {
    "standing": "a standing pose",
    "sitting": "a seated pose",
    "lying": "a reclining pose",
    "walking": "walking",
    "running": "running",
    "jumping": "jumping",
    "holding": "a holding gesture",
    "arms up": "raised arms",
    "looking at viewer": "direct eye contact with the viewer",
    "smile": "a gentle smile",
    "open mouth": "an open mouth",
    "closed mouth": "a closed mouth",
    "blush": "a visible blush",
    "crying": "tears",
    "angry": "an angry expression",
    "surprised": "a surprised expression",
}

_STYLE_PHRASES = {
    "anime coloring": "anime-style color handling",
    "digital art": "digital illustration",
    "watercolor": "watercolor painting",
    "sketch": "an expressive sketch treatment",
    "lineart": "line-focused illustration",
    "monochrome": "a controlled monochrome treatment",
}

_COLOR_WORDS = (
    "black",
    "white",
    "red",
    "blue",
    "green",
    "yellow",
    "pink",
    "purple",
    "brown",
    "blonde",
    "orange",
    "grey",
    "gray",
    "teal",
    "cyan",
    "gold",
    "silver",
)


def _humanize(value: str) -> str:
    return " ".join(value.replace("_", " ").split())


def _stable_unique(values: Iterable[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _humanize(value)
        key = canonical_tag_key(cleaned)
        if not cleaned or key in seen:
            continue
        seen.add(key)
        unique.append(cleaned)
    return unique


def _series(values: Iterable[str]) -> str:
    items = _stable_unique(values)
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _indefinite(value: str) -> str:
    lowered = value.casefold()
    if lowered.startswith(("a ", "an ", "the ", "one ", "two ", "multiple ")):
        return value
    article = "an" if value[:1].casefold() in {"a", "e", "i", "o", "u"} else "a"
    return f"{article} {value}"


class Krea2PromptBuilder:
    """Turn classified WD14 tags into dense, editable visual direction.

    The formatter only states detected content in the descriptive sections.
    Its final sentences add explicit Krea-oriented art direction for lighting,
    palette, edge handling, focal hierarchy, texture, and depth.
    """

    def build(
        self,
        tags: Iterable[TagResult],
        *,
        trigger_word: str | None = None,
        trigger_word_position: str = "first",
    ) -> str:
        source = tuple(tags)
        if not source:
            return ""

        trigger_key = canonical_tag_key(trigger_word) if trigger_word else None
        trigger_output: str | None = None
        grouped: dict[PromptGroup, list[str]] = defaultdict(list)
        for tag in source:
            if (
                trigger_key is not None
                and trigger_output is None
                and tag.source is TagSource.USER
                and canonical_tag_key(tag.output_name) == trigger_key
            ):
                trigger_output = _humanize(tag.output_name)
                continue
            if tag.prompt_group is PromptGroup.QUALITY:
                continue
            grouped[tag.prompt_group or PromptGroup.OTHER].append(tag.output_name)

        if not any(grouped.values()):
            return trigger_output or ""

        paragraphs: list[str] = []
        composition = _stable_unique(grouped[PromptGroup.COMPOSITION])
        shot_key = next(
            (
                canonical_tag_key(value)
                for value in composition
                if canonical_tag_key(value) in _SHOT_OPENINGS
            ),
            None,
        )
        opening = (
            _SHOT_OPENINGS[shot_key]
            if shot_key is not None
            else "An anime illustration"
        )
        paragraphs.append(f"{opening} depicting {self._subject(grouped)}.")

        appearance = _stable_unique(
            (
                *grouped[PromptGroup.HAIR],
                *grouped[PromptGroup.EYES_FACE],
                *grouped[PromptGroup.BODY],
            )
        )
        gaze = [
            value
            for value in appearance
            if canonical_tag_key(value).startswith("looking ")
        ]
        appearance = [value for value in appearance if value not in gaze]
        clothing = _stable_unique(
            (
                *grouped[PromptGroup.CLOTHING],
                *grouped[PromptGroup.ACCESSORIES],
            )
        )
        appearance_lines: list[str] = []
        if appearance:
            appearance_lines.append(
                f"Their appearance includes {_series(appearance)}."
            )
        if clothing:
            appearance_lines.append(
                f"Their clothing and accessories include {_series(clothing)}."
            )
        if appearance_lines:
            paragraphs.append(" ".join(appearance_lines))

        action = _stable_unique(
            _ACTION_PHRASES.get(canonical_tag_key(value), _humanize(value))
            for value in (
                *grouped[PromptGroup.POSE_ACTION],
                *gaze,
                *grouped[PromptGroup.EXPRESSION],
            )
        )
        if action:
            paragraphs.append(
                "Their pose, action, and expression convey "
                f"{_series(action)}."
            )

        other = _stable_unique(grouped[PromptGroup.OTHER])
        if other:
            paragraphs.append(f"Additional observed details include {_series(other)}.")

        remaining_composition = [
            value
            for value in composition
            if canonical_tag_key(value) not in _SHOT_OPENINGS
        ]
        composition_text = _series(
            _COMPOSITION_PHRASES.get(canonical_tag_key(value), value)
            for value in remaining_composition
        )
        if composition_text:
            paragraphs.append(f"The composition uses {composition_text}.")
        else:
            paragraphs.append(
                "The composition keeps the main subject clearly framed, with "
                "a readable silhouette and deliberate subject placement."
            )

        background = _series(
            _BACKGROUND_PHRASES.get(canonical_tag_key(value), _humanize(value))
            for value in grouped[PromptGroup.BACKGROUND]
        )
        if background:
            paragraphs.append(f"The environment includes {background}.")

        lighting = _series(
            _LIGHTING_PHRASES.get(canonical_tag_key(value), _humanize(value))
            for value in grouped[PromptGroup.LIGHTING]
        )
        if lighting:
            paragraphs.append(
                f"Lighting is defined by {lighting}. Keep the light direction "
                "clear, with readable shadow shapes and subtle reflected light."
            )
        else:
            paragraphs.append(
                "Use a clear primary light direction, gentle ambient fill, and "
                "readable shadow shapes that preserve the subject's form."
            )

        colors = self._colors(grouped)
        style_keys = {
            canonical_tag_key(value) for value in grouped[PromptGroup.STYLE]
        }
        if "monochrome" in style_keys:
            paragraphs.append(
                "Use controlled monochrome values, clear tonal separation, and "
                "restrained highlights."
            )
        elif colors:
            paragraphs.append(
                f"The palette is anchored by {_series(colors)}, with controlled "
                "saturation and clear separation between subject and background."
            )
        else:
            paragraphs.append(
                "Use a coherent, restrained palette with purposeful accent colors "
                "and clear separation between subject and background."
            )

        style = _series(
            _STYLE_PHRASES.get(canonical_tag_key(value), _humanize(value))
            for value in grouped[PromptGroup.STYLE]
        )
        paragraphs.append(self._style_direction(style, style_keys, grouped))

        rendered = "\n\n".join(paragraphs)
        if trigger_output:
            if trigger_word_position == "last":
                return f"{rendered}\n\n{trigger_output}."
            return f"{trigger_output}.\n\n{rendered}"
        return rendered

    @staticmethod
    def _subject(grouped: dict[PromptGroup, list[str]]) -> str:
        characters = _stable_unique(grouped[PromptGroup.CHARACTER])
        if characters:
            noun = "the character" if len(characters) == 1 else "the characters"
            return f"{noun} {_series(characters)}"

        counts = {
            canonical_tag_key(value) for value in grouped[PromptGroup.COUNT]
        }
        for key in (
            "1girl",
            "1boy",
            "2girls",
            "2boys",
            "multiple girls",
            "multiple boys",
        ):
            if key in counts:
                return _COUNT_SUBJECTS[key]

        subjects = _stable_unique(grouped[PromptGroup.SUBJECT])
        if subjects:
            return _series(_indefinite(value) for value in subjects)
        if "solo" in counts:
            return _COUNT_SUBJECTS["solo"]
        return "the main subject"

    @staticmethod
    def _colors(grouped: dict[PromptGroup, list[str]]) -> list[str]:
        source_groups = (
            PromptGroup.HAIR,
            PromptGroup.EYES_FACE,
            PromptGroup.BODY,
            PromptGroup.CLOTHING,
            PromptGroup.ACCESSORIES,
            PromptGroup.BACKGROUND,
            PromptGroup.STYLE,
            PromptGroup.OTHER,
        )
        text = " ".join(
            _humanize(value).casefold()
            for group in source_groups
            for value in grouped[group]
        )
        words = set(text.split())
        return [color for color in _COLOR_WORDS if color in words]

    @staticmethod
    def _style_direction(
        style: str,
        style_keys: set[str],
        grouped: dict[PromptGroup, list[str]],
    ) -> str:
        prefix = f"Rendered as {style}. " if style else ""
        if "watercolor" in style_keys:
            treatment = (
                "Use translucent layered washes, subtle paper texture, controlled "
                "color bleeding, soft lost edges, and selectively sharpened focal "
                "details."
            )
        elif style_keys.intersection({"sketch", "lineart"}):
            treatment = (
                "Use expressive linework, varied line weight, intentional edge "
                "variation, restrained rendering, and a highly refined focal area."
            )
        elif "monochrome" in style_keys:
            treatment = (
                "Use confident value shapes, visible edge control, subtle surface "
                "texture, and selective detail rather than uniform sharpness."
            )
        else:
            treatment = (
                "Use painterly Japanese and Korean-inspired digital illustration "
                "qualities: expressive layered brushwork, visible but controlled "
                "painted edges, subtle texture in hair and fabric, rich color "
                "variation inside shadows, and restrained highlights."
            )

        has_face = bool(
            grouped[PromptGroup.EYES_FACE]
            or grouped[PromptGroup.HAIR]
            or grouped[PromptGroup.CHARACTER]
            or grouped[PromptGroup.COUNT]
        )
        focal_subject = "the face and eyes" if has_face else "the main subject"
        return (
            f"{prefix}{treatment} Keep {focal_subject} as the most refined focal "
            "area while rendering secondary details more loosely, with natural "
            "depth instead of uniform sharpness across the frame."
        )
