"""Offline conditional sampling and loss-aware import into a shared ScenePlan."""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from itertools import permutations
from pathlib import Path
import random
import re

from app.errors import ConfigurationError
from app.inference.model_loader import TagCategory
from app.prompts.injection import parse_injections, split_tokens, token_key
from app.prompts.models import TagResult, TagSource
from app.prompts.normalizer import canonical_tag_key
from app.prompts.semantic_catalog import BACKEND_DIRECTORIES, SemanticCatalog
from app.prompts.semantic_rules import THEMES, is_adult_term
from app.prompts.semantic_scene import (
    SceneActor, SceneFact, SceneInteraction, SceneObject, ScenePlan, all_facts,
    compact_facts, render_english, render_tags, scene_summary, validate_scene,
)


@dataclass(frozen=True, slots=True)
class SemanticPromptRequest:
    backends: tuple[str, ...] = ()
    actor_count: int = 1
    character_mode: str = "original"
    characters: tuple[str | None, ...] = ()
    theme: str = "auto"
    location: str = "auto"
    action: str = "auto"
    content: str = "ordinary"
    freedom: str = "natural"
    density: str = "standard"
    seed: int | None = None
    prefer_popular: bool = True
    underscore_to_space: bool = False
    actor_tags: tuple[tuple[str, ...], ...] = ()
    scene_tags: tuple[str, ...] = ()
    previous_scene: ScenePlan | None = None
    locked_actors: tuple[str, ...] = ()
    locked_scene_slots: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class UnassignedTag:
    index: int
    raw: str
    term_key: str
    kind: str = "actor"


@dataclass(frozen=True, slots=True)
class SemanticPromptResult:
    scene: ScenePlan
    tag_prompt: str
    english_prompt: str
    seed: int
    corpus_version: str
    sources: tuple[str, ...]
    diagnostics: tuple[str, ...] = ()
    blocking: tuple[str, ...] = ()
    unassigned: tuple[UnassignedTag, ...] = ()
    expansions: int = 0
    tags: tuple[TagResult, ...] = ()
    summary: str = ""

    @property
    def prompt(self):
        return self.tag_prompt


class SemanticPromptGenerator:
    def __init__(self, model_root: Path, catalog: SemanticCatalog | None = None):
        self.root = Path(model_root)
        self.catalog = catalog or SemanticCatalog()
        self._vocab_cache = {}
        self._slot_cache = {}
        self._version_cache = {}
        self._viability_cache = {}
        self._character_pool_cache = {}

    def vocabulary(self, backends):
        keys = tuple(sorted(set(backends or BACKEND_DIRECTORIES)))
        if any(backend not in BACKEND_DIRECTORIES for backend in keys):
            raise ConfigurationError("未知标签库。")
        fingerprint = []
        for backend in keys:
            path = self.root / "models" / BACKEND_DIRECTORIES[backend] / "selected_tags.csv"
            if not path.is_file():
                raise ConfigurationError(f"标签库不存在：{path}")
            stat = path.stat()
            fingerprint.append((backend, stat.st_mtime_ns, stat.st_size))
        fingerprint = tuple(fingerprint)
        cache_key = keys, fingerprint
        if cache_key not in self._vocab_cache:
            self._vocab_cache[cache_key] = self.catalog.vocabulary(self.root, keys)
        return self._vocab_cache[cache_key]

    def slots(self, vocabulary):
        cache_key = id(vocabulary)
        if cache_key not in self._slot_cache:
            groups = {}
            seen = set()
            for identity, (name, _) in sorted(vocabulary.items()):
                if not identity.startswith("general:"):
                    continue
                term = self.catalog.term(name)
                if term and term.generatable and term.key not in seen and term.slot != "count":
                    seen.add(term.key)
                    groups.setdefault(term.slot, []).append(term)
            self._slot_cache[cache_key] = groups
        return self._slot_cache[cache_key]

    def _result(self, scene, vocabulary, request, seed, *, diagnostics=(), blocking=(), unassigned=(), expansions=0):
        notes = list(diagnostics)
        if len(scene.actors) > 1:
            notes.append("通用 tags 平铺后无法完整保留主体归属；英文描述保留逐主体属性与互动关系。")
        if scene.opaque_tokens:
            notes.append("未知词保留在 tags 中，英文仅描述已确认的事实。")
        if id(vocabulary) not in self._version_cache:
            self._version_cache[id(vocabulary)] = hashlib.sha256((self.catalog.version + repr(sorted(vocabulary.items()))).encode()).hexdigest()[:16]
        digest = self._version_cache[id(vocabulary)]
        tags_text = render_tags(scene, self.catalog, vocabulary, underscore_to_space=request.underscore_to_space)
        preview = []
        for token in parse_injections(tags_text):
            category = TagCategory.CHARACTER if "character:" + self.catalog.canonical(token_key(token)) in vocabulary else TagCategory.GENERAL
            preview.append(TagResult(token, 1.0, category, source=TagSource.PRESET))
        return SemanticPromptResult(scene, tags_text, "" if blocking or unassigned else render_english(scene, self.catalog), seed, digest,
            tuple(sorted(request.backends or BACKEND_DIRECTORIES)), tuple(dict.fromkeys(notes)), tuple(blocking), tuple(unassigned), expansions,
            tuple(preview), scene_summary(scene, self.catalog))

    def generate(self, request: SemanticPromptRequest):
        if not 1 <= request.actor_count <= 4:
            raise ConfigurationError("语义生成的主体数量须为 1–4。")
        for value, allowed, label in ((request.character_mode, {"original", "known"}, "角色方式"), (request.content, {"ordinary", "adult"}, "内容等级"),
                                     (request.freedom, {"natural", "balanced", "bold"}, "自由度"), (request.density, {"concise", "standard", "rich"}, "细节密度")):
            if value not in allowed:
                raise ConfigurationError(f"无效的{label}：{value}")
        if request.theme != "auto" and request.theme not in THEMES:
            raise ConfigurationError("无效的画面主题。")
        vocabulary = self.vocabulary(request.backends)
        raw_pools = self.slots(vocabulary)
        # Static forward pruning eliminates impossible dependencies before any
        # RNG choice. Candidates with unreviewed or absent props cannot enter a
        # branch, and this work is independent of the scene being constructed.
        viability = {}
        def viable(term, trail=frozenset()):
            if term.key in trail:
                return False
            if term.key in viability:
                return viability[term.key]
            valid = term.generatable and (request.content == "adult" or not term.adult) and term.min_actors <= request.actor_count
            if request.content == "adult" and "ordinary_only" in term.conditions:
                valid = False
            for reference in term.requires:
                required = self.catalog.term(reference.split(":", 1)[1])
                if not required or "general:" + self.catalog.canonical(required.name) not in vocabulary or not viable(required, trail | {term.key}):
                    valid = False
                    break
            for alternatives in term.any_dependencies:
                if not any((required := self.catalog.term(reference.split(":", 1)[1])) and
                           "general:" + self.catalog.canonical(required.name) in vocabulary and
                           viable(required, trail | {term.key}) for reference in alternatives):
                    valid = False
            for references in term.role_requires:
                for reference in references:
                    required = self.catalog.term(reference.split(":", 1)[1])
                    if not required or "general:" + self.catalog.canonical(required.name) not in vocabulary or not viable(required, trail | {term.key}):
                        valid = False
            for alternatives in term.required_slots:
                if not any(viable(candidate, trail | {term.key}) for slot in alternatives for candidate in raw_pools.get(slot, ())):
                    valid = False
            viability[term.key] = valid
            return valid
        cache_key = id(vocabulary), request.content, request.actor_count
        if cache_key in self._viability_cache:
            pools, viability = self._viability_cache[cache_key]
        else:
            pools = {slot: tuple(term for term in terms if viable(term)) for slot, terms in raw_pools.items()}
            self._viability_cache[cache_key] = pools, viability
        seed = request.seed if request.seed is not None else random.SystemRandom().randrange(1, 2**31)
        rng = random.Random(seed)
        theme = rng.choice(tuple(THEMES)) if request.theme == "auto" else request.theme
        previous = request.previous_scene
        if (request.locked_actors or request.locked_scene_slots) and previous is None:
            raise ConfigurationError("锁定需要先生成一个画面。")
        if any(int(actor_id[1:]) > request.actor_count for actor_id in request.locked_actors if re.fullmatch(r"A[1-4]", actor_id)):
            raise ConfigurationError("主体数量少于已锁定的主体。")
        if any(not re.fullmatch(r"A[1-4]", actor_id) for actor_id in request.locked_actors):
            raise ConfigurationError("锁定主体 ID 无效。")
        if previous and not set(request.locked_actors) <= {actor.actor_id for actor in previous.actors}:
            raise ConfigurationError("锁定主体不在上一份画面中。")
        if any(slot not in {term.slot for term in self.catalog.terms.values() if term.scope == "scene"} for slot in request.locked_scene_slots):
            raise ConfigurationError("锁定画面属性无效。")
        character_cache_key = id(vocabulary), request.content
        if character_cache_key not in self._character_pool_cache:
            self._character_pool_cache[character_cache_key] = tuple(profile for name, profile in sorted(self.catalog.characters.items())
                                if "character:" + self.catalog.canonical(name) in vocabulary
                                and all(self.catalog.term(tag) and self.catalog.term(tag).generatable
                                        and self.catalog.term(tag).slot == slot and "general:" + self.catalog.canonical(tag) in vocabulary for slot, tag in (*profile.identity, *(profile.wardrobe if request.content == 'ordinary' else ())))
                                and (request.content != "adult" or profile.age_state == "adult" and profile.kind == 'humanoid' and len(profile.identity) >= 2))
        available_characters = self._character_pool_cache[character_cache_key]
        actors = []
        for index in range(request.actor_count):
            actor_id = f"A{index + 1}"
            locked = next((actor for actor in previous.actors if actor.actor_id == actor_id), None) if previous and actor_id in request.locked_actors else None
            if locked:
                actors.append(locked)
                continue
            selected_name = request.characters[index] if index < len(request.characters) else None
            if selected_name or request.character_mode == "known":
                candidates = [profile for profile in available_characters if not selected_name or self.catalog.canonical(profile.name) == self.catalog.canonical(selected_name)]
                if not candidates:
                    raise ConfigurationError(f"{selected_name or '所选词库'} 没有符合身份、年龄及词表条件的角色档案。")
                profile = rng.choice(candidates)
                facts = tuple(SceneFact(self.catalog.term(tag).key) for _, tag in (*profile.identity, *(profile.wardrobe if request.content == 'ordinary' else ())))
                actors.append(SceneActor(actor_id, profile.gender, profile.age_state, profile.name, facts, profile.kind))
            else:
                actors.append(SceneActor(actor_id, rng.choice(("female", "male")), "adult"))
        globals_ = tuple(fact for fact in previous.facts if self.catalog.terms[fact.term_key].slot in request.locked_scene_slots) if previous else ()
        objects = tuple(item for item in previous.objects if item.owner in request.locked_actors) if previous else ()
        interactions = tuple(item for item in previous.interactions if set(item.participants) & set(request.locked_actors)) if previous else ()
        scene = ScenePlan(theme, tuple(actors), globals_, objects, interactions)
        expansions = [0]
        failures = []

        def remember(message):
            if message not in failures and len(failures) < 8:
                failures.append(message)

        def place(current, term, owner=None, fact=None, as_object=False, duplicate=False):
            fact = fact or SceneFact(term.key)
            if as_object or term.scope == "object":
                if term.scope != "object" and not term.object_capable:
                    raise ConfigurationError(f"{term.name} 不能作为实体道具。")
                if not duplicate and any(item.fact.term_key == term.key and item.owner == owner for item in current.objects):
                    return current
                number = 1
                ids = {item.object_id for item in current.objects}
                while f"O{number}" in ids:
                    number += 1
                return replace(current, objects=(*current.objects, SceneObject(f"O{number}", fact, owner)))
            if term.scope == "actor":
                if owner is None:
                    raise ConfigurationError(f"{term.name} 需要指定主体。")
                updated = tuple(replace(actor, facts=compact_facts((*actor.facts, fact), self.catalog)) if actor.actor_id == owner else actor for actor in current.actors)
                return replace(current, actors=updated)
            if term.scope == "relation":
                if len(current.actors) < term.min_actors:
                    raise ConfigurationError(f"{term.name} 至少需要 {term.min_actors} 个主体。")
                options = [people for people in permutations(current.actors, term.min_actors) if all(person.kind == "humanoid" for person in people)
                           and ('original_only' not in term.conditions or not any(person.character for person in people)) and (not term.role_genders or
                           all(gender == "any" or person.gender == gender for person, gender in zip(people, term.role_genders)))]
                if not options:
                    raise ConfigurationError(f"{term.name} 的互动角色条件不满足。")
                participants = tuple(actor.actor_id for actor in rng.choice(options))
                return replace(current, interactions=(*current.interactions, SceneInteraction(fact, participants)))
            return replace(current, facts=compact_facts((*current.facts, fact), self.catalog))

        def dependencies(current, term, owner=None, trail=frozenset()):
            if term.key in trail:
                raise ConfigurationError("生成依赖出现循环。")
            for alternatives in term.required_slots:
                local = next(actor.facts for actor in current.actors if actor.actor_id == owner) if owner else current.facts
                if not any(self.catalog.terms[value.term_key].slot in alternatives for value in local):
                    actor = next((actor for actor in current.actors if actor.actor_id == owner), None)
                    if actor and actor.character:
                        raise ConfigurationError(f'{term.name} 缺少角色已确认的服装属性。')
                    candidates = [value for slot in alternatives for value in pools.get(slot, ()) if value.key not in trail | {term.key}]
                    if not candidates:
                        raise ConfigurationError(f"{term.name} 没有可用的依赖属性槽。")
                    required = rng.choice(candidates)
                    current = dependencies(place(current, required, owner), required, owner, trail | {term.key})
            if term.role_requires:
                relation = next(value for value in reversed(current.interactions) if value.fact.term_key == term.key)
                for actor_id, references in zip(relation.participants, term.role_requires):
                    for reference in references:
                        kind, name = reference.split(":", 1)
                        required = self.catalog.term(name)
                        if not required or not viable(required):
                            raise ConfigurationError(f"{term.name} 缺少互动参与者的依赖 {name}。")
                        current = dependencies(place(current, required, actor_id, as_object=kind == "object"), required, actor_id, trail | {term.key})
            chosen = list(term.requires)
            for alternatives in term.any_dependencies:
                choices = [reference for reference in alternatives
                           if (required := self.catalog.term(reference.split(":", 1)[1])) and
                           "general:" + self.catalog.canonical(required.name) in vocabulary and viable(required)]
                if not choices:
                    raise ConfigurationError(f"{term.name} 没有可用的任选依赖。")
                # Existing facts satisfy an alternative without extra sampling.
                local = next(actor.facts for actor in current.actors if actor.actor_id == owner) if owner else current.facts
                owned = {self.catalog.canonical(self.catalog.terms[item.fact.term_key].name) for item in current.objects if item.owner == owner}
                present = {self.catalog.canonical(self.catalog.terms[value.term_key].name) for value in local} | owned
                chosen.append(next((reference for reference in choices if self.catalog.canonical(reference.split(":", 1)[1]) in present), None) or rng.choice(choices))
            for reference in chosen:
                kind, name = reference.split(":", 1)
                required = self.catalog.term(name)
                if required is None or not required.generatable or "general:" + self.catalog.canonical(required.name) not in vocabulary:
                    raise ConfigurationError(f"{term.name} 的依赖 {name} 不在所选词表。")
                if required.adult and request.content == "ordinary":
                    raise ConfigurationError(f"{term.name} 的依赖 {name} 超出普通内容等级。")
                if kind == "object":
                    present = any((self.catalog.canonical(self.catalog.terms[item.fact.term_key].name) == self.catalog.canonical(name)
                                   or self.catalog.terms[item.fact.term_key].head == self.catalog.canonical(name)) and item.owner == owner for item in current.objects)
                else:
                    candidates = next(actor.facts for actor in current.actors if actor.actor_id == owner) if required.scope == "actor" and owner else current.facts
                    present = any(fact.term_key == required.key or self.catalog.terms[fact.term_key].slot == required.slot
                                  and self.catalog.canonical(name) in self.catalog.implied(self.catalog.terms[fact.term_key].name) for fact in candidates)
                if not present:
                    actor = next((actor for actor in current.actors if actor.actor_id == owner), None)
                    if actor and actor.character and required.scope == 'actor' and required.object_capable and kind != 'object':
                        raise ConfigurationError(f'{term.name} 缺少角色已确认的服装 {name}。')
                    dependency_owner = owner if kind == "object" or required.scope in {"actor", "object"} else None
                    current = dependencies(place(current, required, dependency_owner, as_object=kind == "object"), required, dependency_owner, trail | {term.key})
            for name, quantity in term.object_counts:
                required = self.catalog.term(name)
                if required is None:
                    raise ConfigurationError(f"{term.name} 缺少 {name} 的道具规则。")
                count = sum(item.owner == owner and (self.catalog.canonical(self.catalog.terms[item.fact.term_key].name) == self.catalog.canonical(name)
                            or self.catalog.terms[item.fact.term_key].head == self.catalog.canonical(name)
                            or self.catalog.canonical(name) in self.catalog.implied(self.catalog.terms[item.fact.term_key].name)) for item in current.objects)
                for _ in range(max(0, quantity - count)):
                    current = place(current, required, owner, as_object=True, duplicate=True)
            return current

        def force(current, name, owner=None):
            term = self.catalog.term(token_key(name))
            if not term or not term.generatable or "general:" + self.catalog.canonical(term.name) not in vocabulary:
                raise ConfigurationError(f"{name} 尚无可用语义规则或不在所选词表。")
            if term.adult and request.content == "ordinary":
                raise ConfigurationError(f"普通内容不允许 {name}。")
            match = re.fullmatch(r"\((.+):\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\)", name)
            fact = SceneFact(term.key, name, float(match[2]) if match else None)
            return dependencies(place(current, term, owner, fact), term, owner)

        for index, names in enumerate(request.actor_tags):
            if index >= len(scene.actors):
                raise ConfigurationError("指定属性的主体不存在。")
            for name in names:
                scene = force(scene, name, scene.actors[index].actor_id)
        for name in request.scene_tags:
            scene = force(scene, name)
        if request.location != "auto":
            scene = force(scene, request.location)
        if request.action != "auto":
            term = self.catalog.term(request.action)
            if not term or term.slot not in {"action", "posture", "interaction"}:
                raise ConfigurationError("所选动作没有可用语义规则。")
            scene = force(scene, request.action, scene.actors[0].actor_id if term.scope == "actor" else None)
        errors = validate_scene(scene, self.catalog, complete=False)
        if errors:
            raise ConfigurationError("指定或锁定条件冲突：" + "；".join(errors))
        if request.content == "adult" and any(actor.age_state != "adult" for actor in scene.actors):
            raise ConfigurationError("成人内容的所有主体必须已确定成年；请更换或解锁年龄未知的角色。")
        steps = [("location", None, True), ("time", None, True), ("framing", None, True), ("lighting", None, False)]
        detail = {"concise": 0, "standard": 1, "rich": 3}[request.density]
        for actor in scene.actors:
            if actor.actor_id in request.locked_actors:
                continue
            if actor.kind == "creature":
                continue
            if request.content == "adult":
                # Content level permits mature facts; it does not require every
                # participant to undress when another action requires clothing.
                steps.append(("coverage", actor.actor_id, False))
            steps.extend((slot, actor.actor_id, True) for slot in ("posture", "expression"))
            if not actor.character:
                steps.extend((slot, actor.actor_id, True) for slot in ("hair.color", "hair.length", "eyes.color"))
            if request.content == "ordinary" and not actor.character:
                steps.append(("outfit", actor.actor_id, True))
            if detail:
                steps.extend((slot, actor.actor_id, False) for slot in (("action",) if actor.character else ("hair.style", "action", "accessory")))
            if detail > 1:
                steps.extend((slot, actor.actor_id, False) for slot in (("gaze", "mouth") if actor.character else ("gaze", "mouth", "outerwear", "body.detail", "footwear")))
                # Sample supplementary facets without changing a named
                # character's undocumented physical identity.
                facets = ('hands.pose', 'legs.pose') if actor.character else ('hands.pose', 'legs.pose', 'clothing.trim', 'clothing.pattern', 'clothing.sleeves', 'face.detail')
                steps.extend((slot, actor.actor_id, False) for slot in rng.sample(facets, 2))
                if not actor.character:
                    steps.append(('hair.texture', actor.actor_id, False))
            elif detail and rng.random() < .4:
                steps.append((rng.choice(('hands.pose',) if actor.character else ('hands.pose', 'clothing.trim', 'face.detail')), actor.actor_id, False))
        if len(actors) > 1 and request.action == "auto":
            steps.append(("interaction", None, False))
        if detail > 1:
            steps.extend((("weather", None, False), ("view", None, False), ("style", None, False)))

        def filled(current, slot, owner):
            facts = next(actor.facts for actor in current.actors if actor.actor_id == owner) if owner else current.facts
            if slot == "interaction":
                return bool(current.interactions)
            if slot in {"hair.color", "hair.style", "hair.texture", "hair.detail"} and any(self.catalog.canonical(self.catalog.terms[value.term_key].name) == "bald" for value in facts):
                return True
            return any(self.catalog.terms[fact.term_key].slot == slot for fact in facts)

        # Mandatory steps first; dependent objects/environments are propagated
        # before checking each branch. Subsequent failure unwinds the actual scene.
        def search(current, remaining):
            if expansions[0] >= 2000:
                return None
            pending = [(slot, owner, required) for slot, owner, required in remaining if not filled(current, slot, owner)]
            if not pending:
                errors = validate_scene(current, self.catalog)
                if not errors:
                    return current
                for error in errors:
                    remember(error)
                return None
            step = min(pending, key=lambda item: (item[0] not in {"location", "interaction", "action"}, not item[2], len(pools.get(item[0], ())), item[0], item[1] or ""))
            slot, owner, required = step
            rest = list(pending)
            rest.remove(step)
            candidates = [term for term in pools.get(slot, ()) if (request.content == "adult" or not term.adult) and term.min_actors <= len(actors)]
            while candidates and expansions[0] < 2000:
                weights = []
                for term in candidates:
                    weight = vocabulary["general:" + self.catalog.canonical(term.name)][1] ** 0.5 if request.prefer_popular else 1.0
                    if term.themes:
                        factor = {"natural": 8.0, "balanced": 3.0, "bold": 1.2}[request.freedom]
                        weight *= factor if theme in term.themes else 1 / factor
                    weights.append(weight)
                choice = rng.choices(range(len(candidates)), weights=weights, k=1)[0]
                term = candidates.pop(choice)
                expansions[0] += 1
                try:
                    branch = dependencies(place(current, term, owner), term, owner)
                except ConfigurationError as exc:
                    remember(str(exc))
                    continue
                errors = validate_scene(branch, self.catalog, complete=False)
                if errors:
                    for error in errors:
                        remember(error)
                    continue
                solved = search(branch, rest)
                if solved is not None:
                    return solved
            if not required:
                return search(current, rest)
            remember(f"{owner or '画面'} 的 {slot} 没有满足条件的候选")
            return None
        solved = search(scene, steps)
        if solved is None:
            raise ConfigurationError(f"生成未找到满足条件的画面（候选扩展 {expansions[0]}/2000）：" + "；".join(failures))
        return self._result(solved, vocabulary, request, seed, expansions=expansions[0])

    def import_tags(self, text, *, backends=(), actor_count=None, assignments=None, adult_actors=()):
        parse_injections(text)  # Reuse bracket validation without losing duplicates.
        tokens = split_tokens(text)
        if not tokens:
            raise ConfigurationError("请输入要转换的 tags。")
        vocabulary = self.vocabulary(backends)
        assignments = assignments or {}
        keys = [self.catalog.canonical(token_key(token)) for token in tokens]
        counts = {"female": set(), "male": set(), "unknown": set()}
        errors, diagnostics = [], []
        for name in keys:
            match = re.fullmatch(r"(\d+)(girl|boy|other)s?", name)
            if match:
                counts[{'girl': 'female', 'boy': 'male', 'other': 'unknown'}[match[2]]].add(int(match[1]))
        if any(len(values) > 1 for values in counts.values()):
            errors.append("输入 tags 的人数标签相互冲突。")
        declared = sum(max(values) for values in counts.values() if values)
        named = [self.catalog.character(name) for name in keys]
        total = actor_count if actor_count is not None else (declared or sum(profile is not None for profile in named) or 1)
        if not 1 <= total <= 4:
            raise ConfigurationError("导入主体数量须为 1–4。")
        if declared and declared != total:
            errors.append("指定主体数量与输入人数标签不同。")
        if "solo" in keys and total != 1:
            errors.append("solo 与多人主体数量冲突。")
        profiles = [profile for profile in named if profile is not None]
        known_genders = {gender: sum(profile.gender == gender for profile in profiles) for gender in counts}
        if declared and any(known_genders[gender] > max(values, default=0) for gender, values in counts.items()):
            errors.append("角色性别数量与输入人数标签不同。")
        # Count tags describe the whole image, not the ordering of character
        # names. Assign identities in their source order, then fill unnamed
        # actors from the remaining declared genders.
        genders = [profile.gender for profile in profiles]
        genders.extend(["female"] * max(0, max(counts["female"], default=0) - known_genders["female"]))
        genders.extend(["male"] * max(0, max(counts["male"], default=0) - known_genders["male"]))
        genders.extend(["unknown"] * (total - len(genders)))
        if any(key in {"multiple girls", "multiple boys"} for key in keys) and not declared and actor_count is None:
            errors.append("multiple 标签没有明确主体人数；请指定导入人数。")
        actors = [SceneActor(f"A{index+1}", genders[index], "adult" if f"A{index+1}" in adult_actors else "unknown") for index in range(total)]
        if set(keys) & {"child", "loli", "shota", "toddler", "baby"}:
            actors = [replace(actor, age_state="minor") for actor in actors]
        globals_, objects, relations, opaque, pending = [], [], [], [], []
        held_names = {self.catalog.canonical(reference.split(":", 1)[1]) for name in keys
                      if (term := self.catalog.term(name)) for reference in term.requires if reference.startswith("object:")}
        character_index = 0
        for index, (raw, name) in enumerate(zip(tokens, keys)):
            if re.fullmatch(r"\d+(girl|boy)s?", name) or name in {"solo", "multiple girls", "multiple boys"}:
                continue
            profile = self.catalog.character(name)
            if profile:
                if character_index >= total:
                    errors.append("角色标签数量超过主体数量。")
                    continue
                actor = actors[character_index]
                if actor.gender != "unknown" and actor.gender != profile.gender:
                    errors.append("角色性别与输入人数标签不同。")
                # Identity facts not explicitly present in external tags remain
                # unresolved: import never invents missing appearance attributes.
                actors[character_index] = replace(actor, gender=profile.gender, age_state=profile.age_state, character=profile.name, kind=profile.kind)
                character_index += 1
                continue
            term = self.catalog.term(name)
            if not term or not term.generatable:
                opaque.append(raw)
                diagnostics.append(f"未核对生成规则：{raw}；保留原文，不补写英文事实。")
                if "character:" + name in vocabulary:
                    errors.append(f"{raw} 没有可用身份档案；不能确定角色身份与年龄。")
                continue
            weight_match = re.fullmatch(r"\((.+):\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\)", raw)
            fact = SceneFact(term.key, raw, float(weight_match[2]) if weight_match else None)
            if term.scope == "actor" and not (term.object_capable and name in held_names):
                owner = assignments.get(index) or ("A1" if total == 1 else None)
                if owner is None:
                    pending.append(UnassignedTag(index, raw, term.key))
                elif owner not in {actor.actor_id for actor in actors}:
                    errors.append(f"{raw} 的主体分配无效。")
                else:
                    actors = [replace(actor, facts=compact_facts((*actor.facts, fact), self.catalog)) if actor.actor_id == owner else actor for actor in actors]
            elif term.scope == "object" or term.object_capable and name in held_names:
                owner = assignments.get(index) or ("A1" if total == 1 else None)
                if owner is None and self.catalog.canonical(term.name) in held_names:
                    pending.append(UnassignedTag(index, raw, term.key, "object"))
                objects.append(SceneObject(f"O{len(objects)+1}", fact, owner))
            elif term.scope == "relation":
                if total < term.min_actors:
                    errors.append(f"{raw} 至少需要 {term.min_actors} 个主体。")
                else:
                    participants = assignments.get(index)
                    if participants is None and (total > term.min_actors or term.role_phrase):
                        pending.append(UnassignedTag(index, raw, term.key, "relation"))
                    elif participants is None:
                        participants = tuple(actor.actor_id for actor in actors)
                    if participants is not None:
                        if isinstance(participants, str):
                            errors.append(f"{raw} 需要分配多个互动参与者。")
                        else:
                            relations.append(SceneInteraction(fact, tuple(participants)))
            else:
                globals_.append(fact)
        scene = ScenePlan("imported", tuple(actors), compact_facts(globals_, self.catalog), tuple(objects), tuple(relations), tuple(opaque), tokens)
        errors.extend(validate_scene(scene, self.catalog, complete=not pending))
        def raw_adult_input(name):
            if not is_adult_term(name):
                return False
            term = self.catalog.term(name)
            # In a verified ordinary ancestry relation, "child" means a son or
            # daughter; it makes no claim about appearance or age. Keep every
            # other raw content keyword, and every unreviewed input, guarded.
            words = name.replace('-', ' ').split()
            ancestry = (term and term.generatable and not term.adult and term.scope == 'relation'
                and {'ordinary_only', 'original_only'} <= set(term.conditions))
            return not (ancestry and 'child' in words and not is_adult_term(' '.join(word for word in words if word != 'child')))
        raw_adult = any(raw_adult_input(name) for name in keys)
        if raw_adult and any(actor.age_state != "adult" for actor in actors):
            errors.append("成人内容的所有主体必须已确定成年。")
        if raw_adult and any(self.catalog.terms[fact.term_key].conditions and "ordinary_only" in self.catalog.terms[fact.term_key].conditions for fact in all_facts(scene)):
            errors.append("当前画面风格不能与成人内容组合。")
        if pending:
            diagnostics.append("多人属性尚未分配；为每项选择主体后生成英文描述。")
        request = SemanticPromptRequest(backends=tuple(backends), actor_count=total)
        return self._result(scene, vocabulary, request, 0, diagnostics=diagnostics, blocking=tuple(dict.fromkeys(errors)), unassigned=pending)
