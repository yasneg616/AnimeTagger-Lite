"""Versioned, immutable, offline semantic vocabulary and source-tag mapping."""
from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from types import MappingProxyType

from app.errors import ConfigurationError
from app.prompts.normalizer import canonical_tag_key
from app.prompts.review_metadata import validate_metadata
from app.runtime_paths import RESOURCE_DIR

BACKEND_DIRECTORIES = {"wd_v3": "wd-vit-tagger-v3", "wd_2026_canary": "wd-eva02-tagger-2026-canary", "pixai_v0_9": "pixai-tagger-v0.9"}


@dataclass(frozen=True, slots=True)
class SemanticTerm:
    key: str
    name: str
    category: str
    slot: str
    scope: str
    phrase: str
    themes: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    adult: bool = False
    min_actors: int = 1
    head: str = ""
    status: str = "candidate"
    generatable: bool = True
    features: tuple[tuple[str, str], ...] = ()
    role_phrase: str = ""
    any_dependencies: tuple[tuple[str, ...], ...] = ()
    object_capable: bool = False
    object_counts: tuple[tuple[str, int], ...] = ()
    conditions: tuple[str, ...] = ()
    role_genders: tuple[str, ...] = ()
    required_slots: tuple[tuple[str, ...], ...] = ()
    role_requires: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class CharacterProfile:
    name: str
    gender: str
    identity: tuple[tuple[str, str], ...]
    copyrights: tuple[str, ...] = ()
    age_state: str = "unknown"
    variants: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    kind: str = "humanoid"
    wardrobe: tuple[tuple[str, str], ...] = ()


class SemanticCatalog:
    def __init__(self, directory: Path | None = None, *, data=None):
        self.directory = Path(directory or RESOURCE_DIR / "prompt_semantics")
        try:
            raw = (self.directory / "catalog.json").read_bytes() if data is None else json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            data = json.loads(raw)
            if data["schema_version"] != 1:
                raise ValueError("不支持的语义资源版本")
            self.version = hashlib.sha256(raw).hexdigest()[:16]
            self.records = MappingProxyType(data["entries"])
            self.review_metadata = validate_metadata(data.get('review_metadata', {}), data['entries'])
            self.aliases = MappingProxyType(data["aliases"])
            self.implications = MappingProxyType({name: tuple(values) for name, values in data["implications"].items()})
            terms = {}
            for identity, row in data["entries"].items():
                rule = row.get("rule")
                if not rule or row.get("status") not in {"reviewed", "lexical"}:
                    continue
                terms[identity] = SemanticTerm(identity, row["name"], row["category"], rule["slot"], rule["scope"], rule["phrase"],
                    tuple(rule.get("themes", ())), tuple(rule.get("requires", ())), tuple(rule.get("excludes", ())),
                    tuple(rule.get("provides", ())), rule.get("adult", False), rule.get("min_actors", 1), rule.get("head", ""), row["status"], row["status"] == "reviewed",
                    tuple(sorted(rule.get("features", {}).items())), rule.get("role_phrase", ""),
                    tuple(tuple(items) for items in rule.get("any_dependencies", ())), rule.get("object_capable", False),
                    tuple(sorted(rule.get("object_counts", {}).items())), tuple(rule.get("conditions", ())), tuple(rule.get("role_genders", ())),
                    tuple(tuple(items) for items in rule.get("required_slots", ())), tuple(tuple(items) for items in rule.get("role_requires", ())))
            self.terms = MappingProxyType(terms)
            by_canonical = {}
            for term in terms.values():
                canonical_key = term.category + ':' + self.canonical(term.name)
                prior = by_canonical.get(canonical_key)
                rank = (term.generatable, term.key == canonical_key)
                if prior is None or rank > (prior.generatable, prior.key == canonical_key):
                    by_canonical[canonical_key] = term
            self._terms_by_canonical = by_canonical
            self.characters = MappingProxyType({name: CharacterProfile(name, row["gender"], tuple((slot, tag) for slot, value in row["identity"].items() for tag in (value if isinstance(value, list) else (value,))),
                tuple(row.get("copyrights", ())), row.get("age_state", "unknown"), tuple(row.get("variants", ())), tuple(row.get("sources", ())), row.get("kind", "humanoid"),
                tuple((slot, tag) for slot, value in row.get('wardrobe', {}).items() for tag in (value if isinstance(value, list) else (value,))))
                for name, row in data["characters"].items()})
            self.coverage = data["coverage"]
            self._implication_cache = {}
            self._characters_by_canonical = {self.canonical(name): profile for name, profile in self.characters.items()}
            self._review_by_canonical = {}
            for identity, item in sorted(self.review_metadata.items()):
                canonical = self.canonical(item['canonical'])
                previous = self._review_by_canonical.get(canonical)
                rank = (item['review_state'] == 'verified_identification', identity == 'general:' + canonical)
                if previous is None or rank > (previous['review_state'] == 'verified_identification', previous['key'] == 'general:' + canonical):
                    self._review_by_canonical[canonical] = item
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ConfigurationError(f"语义词库无法加载：{exc}") from exc

    def canonical(self, name):
        current = canonical_tag_key(name)
        seen = set()
        while current in self.aliases:
            if current in seen:
                raise ConfigurationError("语义别名出现循环")
            seen.add(current)
            current = self.aliases[current]
        return current

    def term(self, name, category="general"):
        return self._terms_by_canonical.get(category + ':' + self.canonical(name)) or self.terms.get(category + ':' + canonical_tag_key(name))

    def character(self, name):
        return self._characters_by_canonical.get(self.canonical(name))

    def identification_note(self, name):
        return self._review_by_canonical.get(self.canonical(name))

    def implied(self, name):
        canonical = self.canonical(name)
        if canonical in self._implication_cache:
            return self._implication_cache[canonical]
        pending = [canonical]
        visited = set()
        while pending:
            item = pending.pop()
            for target in self.implications.get(item, ()):
                if target not in visited:
                    visited.add(target)
                    pending.append(target)
        result = frozenset(visited)
        self._implication_cache[canonical] = result
        return result

    def vocabulary(self, root, backends):
        """Read only CSVs; semantic generation does not require model weights."""
        tags = {}
        for backend in sorted(set(backends or tuple(BACKEND_DIRECTORIES))):
            if backend not in BACKEND_DIRECTORIES:
                raise ConfigurationError(f"未知标签库：{backend}")
            directory = BACKEND_DIRECTORIES[backend]
            path = Path(root) / "models" / directory / "selected_tags.csv"
            if not path.is_file():
                raise ConfigurationError(f"标签库不存在：{path}")
            with path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    category = {"0": "general", "4": "character", "3": "copyright"}.get(row["category"])
                    if not category or not row["name"].strip():
                        continue
                    identity = category + ":" + self.canonical(row["name"])
                    weight = max(1, int(float(row.get("count") or 1)))
                    existing = tags.get(identity)
                    # Output a spelling actually present in the selected CSVs.
                    if existing is None or (-weight, row["name"]) < (-existing[1], existing[0]):
                        tags[identity] = (row["name"], weight)
        return MappingProxyType(tags)
