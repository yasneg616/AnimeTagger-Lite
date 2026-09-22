"""Mutually exclusive / antonym tag groups for prompt consistency."""

from __future__ import annotations

from typing import Iterable, Sequence

from app.prompts.models import RemovalRecord, TagResult
from app.prompts.normalizer import canonical_tag_key

# Each frozenset is a clique: at most one member may appear in one prompt.
CONFLICT_GROUPS: tuple[tuple[str, ...], ...] = (
    # Hair length / cut
    (
        "short_hair",
        "medium_hair",
        "long_hair",
        "very_long_hair",
        "absurdly_long_hair",
        "bob_cut",
        "pixie_cut",
        "buzz_cut",
        "crew_cut",
        "undercut",
        "bowl_cut",
        "flipped_hair",
    ),
    # Person count (solo vs multi-girl / multi-boy phrasing)
    (
        "solo",
        "2girls",
        "3girls",
        "4girls",
        "5girls",
        "6+girls",
        "multiple_girls",
        "2boys",
        "3boys",
        "multiple_boys",
        "multiple_persona",
        "group",
    ),
    (
        "1girl",
        "2girls",
        "3girls",
        "4girls",
        "5girls",
        "6+girls",
        "multiple_girls",
    ),
    (
        "1boy",
        "2boys",
        "3boys",
        "multiple_boys",
    ),
    # Clothing coverage
    (
        "clothed",
        "clothes",
        "nude",
        "naked",
        "topless",
        "bottomless",
        "no_clothes",
        "undressing",
        "nudity",
    ),
    # Mouth
    (
        "open_mouth",
        "closed_mouth",
        "mouth_closed",
        "pursed_lips",
    ),
    # Eyes / gaze
    (
        "looking_at_viewer",
        "looking_away",
        "looking_back",
        "looking_up",
        "looking_down",
        "looking_to_the_side",
        "eyes_closed",
        "one_eye_closed",
        "wink",
    ),
    # Smile family vs explicit opposite expression
    (
        "smile",
        "frown",
        "sad",
        "crying",
        "angry",
    ),
    # Single-tone hair colors (multi-tone handled separately)
    (
        "blonde_hair",
        "brown_hair",
        "black_hair",
        "blue_hair",
        "red_hair",
        "white_hair",
        "silver_hair",
        "grey_hair",
        "pink_hair",
        "purple_hair",
        "green_hair",
        "orange_hair",
        "aqua_hair",
        "lavender_hair",
        "multicolored_hair",
        "two-tone_hair",
        "gradient_hair",
    ),
    # Single-tone eye colors
    (
        "blue_eyes",
        "red_eyes",
        "green_eyes",
        "brown_eyes",
        "black_eyes",
        "yellow_eyes",
        "purple_eyes",
        "pink_eyes",
        "orange_eyes",
        "aqua_eyes",
        "grey_eyes",
        "white_eyes",
        "multicolored_eyes",
        "heterochromia",
    ),
    # Background vs scene clutter
    (
        "simple_background",
        "white_background",
        "grey_background",
        "black_background",
        "scenery",
        "detailed_background",
        "no_humans",
    ),
    # Sex / nsfw polarity helpers (kept broad but still exclusive)
    (
        "safe",
        "sensitive",
        "questionable",
        "explicit",
    ),
)


def _build_lookup(groups: Sequence[Sequence[str]]) -> dict[str, frozenset[str]]:
    lookup: dict[str, frozenset[str]] = {}
    for group in groups:
        keys = frozenset(canonical_tag_key(item) for item in group if item.strip())
        if len(keys) < 2:
            continue
        for key in keys:
            existing = lookup.get(key)
            lookup[key] = keys if existing is None else (existing | keys)
    return lookup


CONFLICT_LOOKUP = _build_lookup(CONFLICT_GROUPS)


def conflict_group_for(name: str) -> frozenset[str]:
    return CONFLICT_LOOKUP.get(canonical_tag_key(name), frozenset())


def filter_conflicting_names(names: Iterable[str]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Keep first-seen members of each clique; return (kept, dropped)."""

    kept: list[str] = []
    dropped: list[str] = []
    kept_keys: set[str] = set()
    for name in names:
        key = canonical_tag_key(name)
        group = CONFLICT_LOOKUP.get(key)
        if group is not None and any(
            member in kept_keys for member in group if member != key
        ):
            dropped.append(name)
            continue
        kept_keys.add(key)
        kept.append(name)
    return tuple(kept), tuple(dropped)


def resolve_tag_conflicts(
    tags: Sequence[TagResult],
) -> tuple[tuple[TagResult, ...], tuple[RemovalRecord, ...]]:
    """Drop later tags that collide with an already-kept antonym/conflict member."""

    kept: list[TagResult] = []
    removed: list[RemovalRecord] = []
    kept_keys: set[str] = set()
    for tag in tags:
        name = tag.normalized_name or tag.output_name
        key = canonical_tag_key(name) if name else ""
        group = CONFLICT_LOOKUP.get(key)
        if group is not None and any(
            member in kept_keys for member in group if member != key
        ):
            removed.append(RemovalRecord(tag, "antonym_conflict"))
            continue
        if key:
            kept_keys.add(key)
        kept.append(tag)
    return tuple(kept), tuple(removed)
