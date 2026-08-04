from __future__ import annotations

from pathlib import Path

from app.inference.model_loader import TagCategory
from app.prompts.models import PromptGroup, TagResult
from app.prompts.tag_classifier import TagClassifier

RESOURCE_PATH = Path(__file__).resolve().parents[1] / "resources" / "tag_categories.json"


def result(
    name: str,
    confidence: float = 0.8,
    category: TagCategory = TagCategory.GENERAL,
) -> TagResult:
    return TagResult(
        name,
        confidence,
        category,
        normalized_name=name,
    )


def test_category_rules_load_from_json() -> None:
    classifier = TagClassifier.from_json(RESOURCE_PATH)

    assert not classifier.used_fallback
    assert classifier.classify(result("best quality")) is PromptGroup.QUALITY
    assert classifier.classify(result("long hair")) is PromptGroup.HAIR
    assert classifier.classify(result("blue eyes")) is PromptGroup.EYES_FACE


def test_character_model_category_has_priority() -> None:
    classifier = TagClassifier.from_json(RESOURCE_PATH)

    assert (
        classifier.classify(
            result("best quality", category=TagCategory.CHARACTER)
        )
        is PromptGroup.CHARACTER
    )


def test_unknown_tag_enters_other() -> None:
    classifier = TagClassifier.from_json(RESOURCE_PATH)

    assert classifier.classify(result("totally novel tag")) is PromptGroup.OTHER
    assert classifier.classify(result("chair")) is PromptGroup.OTHER


def test_corrupt_json_falls_back_and_logs(
    tmp_path: Path,
    caplog: object,
) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    classifier = TagClassifier.from_json(path)

    assert classifier.used_fallback
    assert classifier.classify(result("masterpiece")) is PromptGroup.QUALITY
    assert "使用最小内置规则" in caplog.text  # type: ignore[attr-defined]


def test_same_group_sorts_by_confidence_with_stable_ties() -> None:
    classifier = TagClassifier.from_json(RESOURCE_PATH)
    assigned = classifier.assign_groups(
        [
            result("long hair", 0.7),
            result("black hair", 0.9),
            result("blue hair", 0.9),
        ]
    )

    ordered = classifier.sort_tags(assigned)

    assert [tag.name for tag in ordered] == [
        "black hair",
        "blue hair",
        "long hair",
    ]


def test_group_order_precedes_confidence() -> None:
    classifier = TagClassifier.from_json(RESOURCE_PATH)
    assigned = classifier.assign_groups(
        [
            result("simple background", 0.99),
            result("1girl", 0.5),
            result("red eyes", 0.8),
        ]
    )

    ordered = classifier.sort_tags(assigned)

    assert [tag.name for tag in ordered] == [
        "1girl",
        "red eyes",
        "simple background",
    ]
