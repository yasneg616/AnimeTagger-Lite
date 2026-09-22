"""Randomly sample a prompt from local model tag libraries."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import random
from typing import Iterable, Sequence

from app.errors import ConfigurationError
from app.inference.backends import BACKENDS, load_backend_tags, resolve_backend_files
from app.inference.model_loader import TagCategory
from app.prompts.filtering import is_censored_tag_name
from app.prompts.models import TagResult, TagSource
from app.prompts.normalizer import canonical_tag_key
from app.prompts.random_buckets import RandomBucket, classify_random_bucket
from app.prompts.tag_classifier import TagClassifier
from app.prompts.tag_conflicts import CONFLICT_LOOKUP, filter_conflicting_names


@dataclass(frozen=True, slots=True)
class TagLibraryEntry:
    name: str
    category: TagCategory
    weight: int


@dataclass(frozen=True, slots=True)
class RandomPromptRequest:
    backends: tuple[str, ...] = ()
    character_count: int = 1
    copyright_count: int = 0
    hair_count: int = 1
    body_count: int = 0
    clothing_count: int = 2
    item_count: int = 1
    pose_count: int = 1
    background_count: int = 1
    nsfw_count: int = 0
    other_count: int = 2
    pool_top_n: int = 2500
    seed: int | None = None
    allow_censored: bool = False
    prefer_popular: bool = True
    underscore_to_space: bool = False

    def bucket_counts(self) -> dict[RandomBucket, int]:
        return {
            RandomBucket.CHARACTER: max(0, int(self.character_count)),
            RandomBucket.COPYRIGHT: max(0, int(self.copyright_count)),
            RandomBucket.HAIR: max(0, int(self.hair_count)),
            RandomBucket.BODY: max(0, int(self.body_count)),
            RandomBucket.CLOTHING: max(0, int(self.clothing_count)),
            RandomBucket.ITEMS: max(0, int(self.item_count)),
            RandomBucket.POSE: max(0, int(self.pose_count)),
            RandomBucket.BACKGROUND: max(0, int(self.background_count)),
            RandomBucket.NSFW: max(0, int(self.nsfw_count)),
            RandomBucket.OTHER: max(0, int(self.other_count)),
        }


@dataclass(frozen=True, slots=True)
class RandomPromptResult:
    tags: tuple[TagResult, ...]
    prompt: str
    sources: tuple[str, ...]
    seed: int
    pools: dict[str, int] = field(default_factory=dict)
    buckets: dict[str, int] = field(default_factory=dict)


def _display_name(name: str, *, underscore_to_space: bool) -> str:
    return name.replace("_", " ") if underscore_to_space else name


def load_tag_libraries(
    model_root: Path,
    backends: Sequence[str],
) -> tuple[TagLibraryEntry, ...]:
    """Merge selected backend CSVs; higher popularity wins on name collisions.

    ``model_root`` is the application root. Backend directories already include
    their ``models/`` prefix (for example ``models/wd-vit-tagger-v3``).
    """

    if not backends:
        raise ConfigurationError("请至少选择一个标签库来源。")
    root = Path(model_root)
    merged: dict[str, TagLibraryEntry] = {}
    for backend in backends:
        if backend not in BACKENDS:
            raise ConfigurationError(f"未知 tagger backend：{backend}")
        directory = Path(BACKENDS[backend].directory)
        candidate = root / directory
        if not candidate.exists() and root.name == "models":
            candidate = root / directory.name
        files = resolve_backend_files(candidate, backend)
        try:
            raw = Path(files.tags_path).read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise ConfigurationError(f"无法读取标签库：{files.tags_path}") from exc
        weights = _parse_count_column(raw)
        for tag in load_backend_tags(files.tags_path, backend):
            name = tag.name.strip()
            if not name:
                continue
            if tag.category is TagCategory.RATING:
                continue
            weight = max(1, weights.get(name, 1))
            key = canonical_tag_key(name)
            existing = merged.get(key)
            if existing is None or weight > existing.weight:
                merged[key] = TagLibraryEntry(name, tag.category, weight)
    if not merged:
        raise ConfigurationError("所选标签库为空，无法生成随机 Prompt。")
    return tuple(merged.values())


def _parse_count_column(csv_text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    lines = csv_text.splitlines()
    if not lines:
        return counts
    header = [cell.strip().casefold() for cell in lines[0].split(",")]
    try:
        name_index = header.index("name")
        count_index = header.index("count")
    except ValueError:
        return counts
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = line.split(",")
        if len(cells) <= max(name_index, count_index):
            continue
        name = cells[name_index].strip()
        try:
            count = int(float(cells[count_index].strip()))
        except ValueError:
            continue
        if name:
            counts[name] = max(counts.get(name, 0), count)
    return counts


def build_bucket_pools(
    library: Sequence[TagLibraryEntry],
    *,
    top_n: int,
    allow_censored: bool,
) -> dict[RandomBucket, list[TagLibraryEntry]]:
    pools: dict[RandomBucket, list[TagLibraryEntry]] = {bucket: [] for bucket in RandomBucket}
    for entry in library:
        if not allow_censored and is_censored_tag_name(entry.name):
            continue
        bucket = classify_random_bucket(entry.name, entry.category)
        pools[bucket].append(entry)
    for bucket, items in pools.items():
        items.sort(key=lambda item: (-item.weight, item.name.casefold()))
        if top_n > 0:
            pools[bucket] = items[:top_n]
    return pools


def _exclude_conflicts(
    pool: Sequence[TagLibraryEntry],
    weights: Sequence[int],
    picked_name: str,
) -> tuple[list[TagLibraryEntry], list[int]]:
    picked_key = canonical_tag_key(picked_name)
    blocked = {
        member
        for member in CONFLICT_LOOKUP.get(picked_key, frozenset())
        if member != picked_key
    }
    if not blocked:
        return list(pool), list(weights)
    kept: list[TagLibraryEntry] = []
    kept_weights: list[int] = []
    for entry, weight in zip(pool, weights):
        if canonical_tag_key(entry.name) in blocked:
            continue
        kept.append(entry)
        kept_weights.append(weight)
    return kept, kept_weights


def _sample(
    pool: Sequence[TagLibraryEntry],
    count: int,
    *,
    rng: random.Random,
    prefer_popular: bool,
) -> list[TagLibraryEntry]:
    if count <= 0 or not pool:
        return []
    if count >= len(pool):
        chosen_all: list[TagLibraryEntry] = []
        kept_keys: set[str] = set()
        for entry in pool:
            key = canonical_tag_key(entry.name)
            group = CONFLICT_LOOKUP.get(key)
            if group is not None and any(
                member in kept_keys for member in group if member != key
            ):
                continue
            kept_keys.add(key)
            chosen_all.append(entry)
            if len(chosen_all) >= count:
                break
        return chosen_all

    available = list(pool)
    if prefer_popular:
        available_weights = [max(1, entry.weight) for entry in available]
        chosen: list[TagLibraryEntry] = []
        for _ in range(count):
            if not available:
                break
            index = rng.choices(range(len(available)), weights=available_weights, k=1)[0]
            entry = available.pop(index)
            available_weights.pop(index)
            chosen.append(entry)
            available, available_weights = _exclude_conflicts(
                available, available_weights, entry.name
            )
        return chosen

    available = list(pool)
    chosen = []
    for _ in range(count):
        if not available:
            break
        index = rng.randrange(len(available))
        entry = available.pop(index)
        chosen.append(entry)
        blocked_key = canonical_tag_key(entry.name)
        blocked = {
            member
            for member in CONFLICT_LOOKUP.get(blocked_key, frozenset())
            if member != blocked_key
        }
        if blocked:
            available = [
                item
                for item in available
                if canonical_tag_key(item.name) not in blocked
            ]
    return chosen


class RandomPromptGenerator:
    def __init__(
        self,
        model_root: Path,
        classifier: TagClassifier | None = None,
    ) -> None:
        self._model_root = Path(model_root)
        self._classifier = classifier or TagClassifier()
        self._cache: dict[tuple[str, ...], tuple[TagLibraryEntry, ...]] = {}

    def library_for(self, backends: Sequence[str]) -> tuple[TagLibraryEntry, ...]:
        key = tuple(backends)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        library = load_tag_libraries(self._model_root, key)
        self._cache[key] = library
        return library

    def generate(self, request: RandomPromptRequest) -> RandomPromptResult:
        backends = request.backends or tuple(BACKENDS)
        library = self.library_for(backends)
        seed = request.seed if request.seed is not None else random.randrange(1, 2**31 - 1)
        rng = random.Random(seed)

        pools = build_bucket_pools(
            library,
            top_n=request.pool_top_n,
            allow_censored=request.allow_censored,
        )
        counts = request.bucket_counts()

        selected: list[TagLibraryEntry] = []
        selected_buckets: dict[str, int] = {}
        # Sample order matters for conflict winners: character → copyright →
        # structured visual buckets → nsfw → other.
        order = (
            RandomBucket.CHARACTER,
            RandomBucket.COPYRIGHT,
            RandomBucket.HAIR,
            RandomBucket.BODY,
            RandomBucket.CLOTHING,
            RandomBucket.ITEMS,
            RandomBucket.POSE,
            RandomBucket.BACKGROUND,
            RandomBucket.NSFW,
            RandomBucket.OTHER,
        )
        for bucket in order:
            picked = _sample(
                pools[bucket],
                counts.get(bucket, 0),
                rng=rng,
                prefer_popular=request.prefer_popular,
            )
            if picked:
                selected_buckets[bucket.value] = len(picked)
            selected.extend(picked)

        kept_names, _dropped = filter_conflicting_names(entry.name for entry in selected)
        kept_keys = {canonical_tag_key(name) for name in kept_names}
        selected = [entry for entry in selected if canonical_tag_key(entry.name) in kept_keys]

        max_weight = max((entry.weight for entry in selected), default=1) or 1
        tags: list[TagResult] = []
        seen: set[str] = set()
        for entry in selected:
            key = canonical_tag_key(entry.name)
            if key in seen:
                continue
            seen.add(key)
            confidence = min(0.99, 0.35 + 0.64 * (entry.weight / max_weight))
            tags.append(
                TagResult(
                    name=_display_name(entry.name, underscore_to_space=request.underscore_to_space),
                    confidence=confidence,
                    category=entry.category,
                    enabled=True,
                    source=TagSource.MODEL,
                    normalized_name=_display_name(
                        entry.name,
                        underscore_to_space=request.underscore_to_space,
                    ),
                )
            )

        classified = self._classifier.assign_groups(tags)
        ordered = self._classifier.sort_tags(classified)
        prompt = ", ".join(tag.output_name for tag in ordered)
        return RandomPromptResult(
            tags=ordered,
            prompt=prompt,
            sources=tuple(backends),
            seed=seed,
            pools={bucket.value: len(items) for bucket, items in pools.items()},
            buckets=selected_buckets,
        )
