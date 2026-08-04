from __future__ import annotations

import pytest

from app.errors import TagProcessingError
from app.inference.model_loader import TagCategory
from app.prompts.models import PromptGroup, TagResult
from app.prompts.normalizer import NormalizerSettings, TagNormalizer


@pytest.mark.parametrize(
    ("raw", "settings", "expected"),
    [
        (
            "  long_hair  ",
            NormalizerSettings(underscore_to_space=True),
            "long hair",
        ),
        (
            "a   tag\twith\nspaces",
            NormalizerSettings(),
            "a tag with spaces",
        ),
        (
            r"artist_name_\(series\)",
            NormalizerSettings(underscore_to_space=True, unescape_parentheses=True),
            "artist name (series)",
        ),
        (
            r"artist_name_\(series\)",
            NormalizerSettings(
                underscore_to_space=False,
                unescape_parentheses=False,
            ),
            r"artist_name_\(series\)",
        ),
        (
            "Hatsune_Miku_(VOCALOID)",
            NormalizerSettings(underscore_to_space=True),
            "Hatsune Miku (VOCALOID)",
        ),
        (
            "キャラクター☆name",
            NormalizerSettings(),
            "キャラクター☆name",
        ),
    ],
)
def test_normalize_name(
    raw: str,
    settings: NormalizerSettings,
    expected: str,
) -> None:
    assert TagNormalizer().normalize_name(raw, settings) == expected


@pytest.mark.parametrize("raw", ["", " ", "\t\n"])
def test_empty_normalized_name_returns_none(raw: str) -> None:
    assert TagNormalizer().normalize_name(raw, NormalizerSettings()) is None


def test_comma_is_rejected_in_single_tag() -> None:
    with pytest.raises(TagProcessingError, match="不能包含英文逗号"):
        TagNormalizer().normalize_name("1girl, solo", NormalizerSettings())


def test_normalize_tag_preserves_original_name_and_score() -> None:
    original = TagResult("long_hair", 0.9, TagCategory.GENERAL)

    normalized = TagNormalizer().normalize_tag(
        original,
        NormalizerSettings(underscore_to_space=True),
    )

    assert normalized.name == "long_hair"
    assert normalized.normalized_name == "long hair"
    assert normalized.confidence == 0.9
    assert original.normalized_name is None


def test_normalize_tag_reuses_prepared_value_and_clears_stale_group() -> None:
    prepared = TagResult(
        "long_hair",
        0.9,
        TagCategory.GENERAL,
        normalized_name="long_hair",
        prompt_group=PromptGroup.HAIR,
    )
    normalizer = TagNormalizer()

    unchanged = normalizer.normalize_tag(prepared, NormalizerSettings())
    changed = normalizer.normalize_tag(
        prepared,
        NormalizerSettings(underscore_to_space=True),
    )

    assert unchanged is prepared
    assert changed.normalized_name == "long hair"
    assert changed.prompt_group is None
