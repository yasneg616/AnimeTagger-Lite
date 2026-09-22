from __future__ import annotations

from pathlib import Path

import pytest

from app.errors import ConfigurationError
from app.inference.model_loader import TagCategory
from app.prompts.filtering import is_censored_tag_name
from app.prompts.random_buckets import RandomBucket, classify_random_bucket
from app.prompts.random_prompt import (
    RandomPromptGenerator,
    RandomPromptRequest,
    build_bucket_pools,
    load_tag_libraries,
)


def _write_csv(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["tag_id,name,category,count"]
    lines.extend(",".join(row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def model_root(tmp_path: Path) -> Path:
    wd = tmp_path / "models" / "wd-vit-tagger-v3"
    _write_csv(
        wd / "selected_tags.csv",
        [
            ("9999999", "general", "9", "1"),
            ("1", "1girl", "0", "100"),
            ("2", "solo", "0", "90"),
            ("3", "blue_hair", "0", "50"),
            ("4", "censored", "0", "80"),
            ("5", "uncensored", "0", "40"),
            ("6", "alice", "4", "70"),
            ("7", "wonderland", "3", "60"),
            ("8", "dress", "0", "75"),
            ("9", "school_uniform", "0", "70"),
            ("10", "hat", "0", "40"),
            ("11", "outdoors", "0", "55"),
            ("12", "smile", "0", "65"),
            ("13", "nude", "0", "50"),
            ("14", "large_breasts", "0", "45"),
        ],
    )
    (wd / "model.onnx").write_bytes(b"x")
    canary = tmp_path / "models" / "wd-eva02-tagger-2026-canary"
    _write_csv(
        canary / "selected_tags.csv",
        [
            ("0", "general", "9", "1"),
            ("1", "1girl", "0", "200"),
            ("2", "long_hair", "0", "55"),
            ("3", "censored", "0", "99"),
            ("4", "bob", "4", "30"),
        ],
    )
    (canary / "model.safetensors").write_bytes(b"x")
    (canary / "config.json").write_text("{}", encoding="utf-8")
    return tmp_path


def test_classify_random_bucket_examples() -> None:
    assert classify_random_bucket("alice", TagCategory.CHARACTER) is RandomBucket.CHARACTER
    assert classify_random_bucket("wonderland", TagCategory.COPYRIGHT) is RandomBucket.COPYRIGHT
    assert classify_random_bucket("dress", TagCategory.GENERAL) is RandomBucket.CLOTHING
    assert classify_random_bucket("school_uniform", TagCategory.GENERAL) is RandomBucket.CLOTHING
    assert classify_random_bucket("hat", TagCategory.GENERAL) is RandomBucket.ITEMS
    assert classify_random_bucket("outdoors", TagCategory.GENERAL) is RandomBucket.BACKGROUND
    assert classify_random_bucket("nude", TagCategory.GENERAL) is RandomBucket.NSFW
    assert classify_random_bucket("blue_hair", TagCategory.GENERAL) is RandomBucket.HAIR
    assert classify_random_bucket("large_breasts", TagCategory.GENERAL) is RandomBucket.BODY
    assert classify_random_bucket("smile", TagCategory.GENERAL) is RandomBucket.POSE
    assert classify_random_bucket("1girl", TagCategory.GENERAL) in {
        RandomBucket.POSE,
        RandomBucket.OTHER,
        RandomBucket.BODY,
    }


def test_build_bucket_pools_separates_general(model_root: Path) -> None:
    library = load_tag_libraries(model_root, ("wd_v3",))
    pools = build_bucket_pools(library, top_n=0, allow_censored=False)
    clothing_names = {e.name for e in pools[RandomBucket.CLOTHING]}
    item_names = {e.name for e in pools[RandomBucket.ITEMS]}
    bg_names = {e.name for e in pools[RandomBucket.BACKGROUND]}
    nsfw_names = {e.name for e in pools[RandomBucket.NSFW]}
    assert {"dress", "school_uniform"} <= clothing_names
    assert "hat" in item_names
    assert "outdoors" in bg_names
    # censored blocked; uncensored classified as nsfw and allowed when not censored-filtered
    assert "censored" not in nsfw_names
    assert any(is_censored_tag_name(e.name) is False for e in library)


def test_random_generate_respects_bucket_counts(model_root: Path) -> None:
    generator = RandomPromptGenerator(model_root)
    result = generator.generate(
        RandomPromptRequest(
            backends=("wd_v3",),
            character_count=1,
            copyright_count=1,
            hair_count=0,
            body_count=0,
            clothing_count=2,
            item_count=1,
            pose_count=0,
            background_count=1,
            nsfw_count=0,
            other_count=0,
            pool_top_n=0,
            seed=5,
            allow_censored=False,
            prefer_popular=False,
        )
    )
    names = {tag.output_name for tag in result.tags}
    assert "alice" in names
    assert "wonderland" in names
    assert "censored" not in names
    assert "nude" not in names
    # clothing items from fixture
    assert names & {"dress", "school_uniform"}
    assert "hat" in names
    assert "outdoors" in names
    assert result.buckets.get("character", 0) >= 1
    assert result.buckets.get("clothing", 0) >= 1
    assert result.buckets.get("nsfw", 0) == 0


def test_random_generate_reproducible(model_root: Path) -> None:
    generator = RandomPromptGenerator(model_root)
    request = RandomPromptRequest(
        backends=("wd_v3",),
        character_count=1,
        clothing_count=1,
        seed=42,
        pool_top_n=0,
        allow_censored=False,
    )
    assert generator.generate(request).prompt == generator.generate(request).prompt


def test_random_generate_rejects_unknown_backend(model_root: Path) -> None:
    generator = RandomPromptGenerator(model_root)
    with pytest.raises(ConfigurationError):
        generator.generate(RandomPromptRequest(backends=("nope",), seed=1))


def test_tag_conflicts_module_filters_hair_length() -> None:
    from app.prompts.tag_conflicts import filter_conflicting_names

    kept, dropped = filter_conflicting_names(
        ["short_hair", "very_long_hair", "1girl", "long_hair"]
    )
    assert kept == ("short_hair", "1girl")
    assert set(dropped) == {"very_long_hair", "long_hair"}


def test_random_generate_large_count_uses_full_pool(model_root: Path) -> None:
    generator = RandomPromptGenerator(model_root)
    result = generator.generate(
        RandomPromptRequest(
            backends=("wd_v3",),
            character_count=0,
            copyright_count=0,
            hair_count=0,
            body_count=0,
            clothing_count=0,
            item_count=0,
            pose_count=0,
            background_count=0,
            nsfw_count=0,
            other_count=10_000,
            pool_top_n=0,
            seed=11,
            allow_censored=False,
            prefer_popular=False,
        )
    )
    names = {tag.output_name for tag in result.tags}
    assert "censored" not in names
    assert len(result.tags) >= 1
