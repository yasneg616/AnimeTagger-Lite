"""Immutable scene facts, subject-scoped validation, and two deterministic views."""
from __future__ import annotations

from dataclasses import dataclass, replace
import re

from app.errors import ConfigurationError
from app.prompts.semantic_rules import SINGLE_SLOTS, LENGTH_LEVELS


@dataclass(frozen=True, slots=True)
class SceneFact:
    term_key: str
    raw: str = ""
    weight: float | None = None


@dataclass(frozen=True, slots=True)
class SceneActor:
    actor_id: str
    gender: str = "female"
    age_state: str = "adult"
    character: str | None = None
    facts: tuple[SceneFact, ...] = ()
    kind: str = "humanoid"


@dataclass(frozen=True, slots=True)
class SceneObject:
    object_id: str
    fact: SceneFact
    owner: str | None = None


@dataclass(frozen=True, slots=True)
class SceneInteraction:
    fact: SceneFact
    participants: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScenePlan:
    theme: str
    actors: tuple[SceneActor, ...]
    facts: tuple[SceneFact, ...] = ()
    objects: tuple[SceneObject, ...] = ()
    interactions: tuple[SceneInteraction, ...] = ()
    opaque_tokens: tuple[str, ...] = ()
    imported_tokens: tuple[str, ...] = ()


def all_facts(scene):
    return (*scene.facts, *(fact for actor in scene.actors for fact in actor.facts),
            *(item.fact for item in scene.objects), *(item.fact for item in scene.interactions))


def compact_facts(facts, catalog):
    """Remove exact aliases and less-specific ancestors within the same owner."""
    unique = {}
    for fact in facts:
        term = catalog.terms[fact.term_key]
        canonical = term.category + ":" + catalog.canonical(term.name)
        current = unique.get(canonical)
        if current is None or (fact.weight or 1.0) > (current.weight or 1.0):
            unique[canonical] = fact
    retained = []
    for fact in unique.values():
        name = catalog.canonical(catalog.terms[fact.term_key].name)
        if any(name in catalog.implied(catalog.terms[other.term_key].name)
               and catalog.terms[other.term_key].slot == catalog.terms[fact.term_key].slot
               and catalog.canonical(catalog.terms[other.term_key].name) not in catalog.implied(name)
               for other in unique.values() if other is not fact):
            continue
        retained.append(fact)
    return tuple(retained)


def multicolor_capability(context, owners):
    """True when ``context`` is declared multi-coloured.

    ``owners`` may be compiled terms or an already-flattened capability set.
    The compiler registers the same capability under two spellings: the
    generated ``multicolor:<context>`` form and the short ``multicolor_<noun>``
    form used by the handwritten hair and eye rules. Both mean the same thing,
    so the slot and feature checks accept either instead of only one.
    """
    provided = {value for owner in owners for value in (owner.provides if hasattr(owner, "provides") else (owner,))}
    if "multicolor:" + context in provided:
        return True
    noun = context.removesuffix(".color").removesuffix("component")
    return noun in {"hair", "eyes"} and "multicolor_" + noun in provided


def validate_scene(scene, catalog, *, complete=True):
    errors = []
    actor_ids = {actor.actor_id for actor in scene.actors}
    if not 1 <= len(scene.actors) <= 4 or len(actor_ids) != len(scene.actors):
        errors.append("主体数量须为 1–4，且主体 ID 唯一。")
    facts = all_facts(scene)
    if any(fact.term_key not in catalog.terms for fact in facts):
        return ("画面含有未核对的生成词。",)
    if any(item.owner is not None and item.owner not in actor_ids for item in scene.objects):
        errors.append("道具的持有者不存在。")
    for relation in scene.interactions:
        term = catalog.terms[relation.fact.term_key]
        if any(actor.kind != "humanoid" for actor in scene.actors if actor.actor_id in relation.participants):
            errors.append(f"互动 {term.name} 需要人形主体。")
        if term.scope != "relation":
            errors.append(f"{term.name} 不能作为互动关系。")
        if len(set(relation.participants)) < term.min_actors or len(set(relation.participants)) != len(relation.participants) or not set(relation.participants) <= actor_ids:
            errors.append(f"互动 {term.name} 的参与者不足或不存在。")
        if term.role_genders and all(item in actor_ids for item in relation.participants):
            people = {actor.actor_id: actor for actor in scene.actors}
            if len(term.role_genders) != len(relation.participants) or any(gender != "any" and people[item].gender != gender for item, gender in zip(relation.participants, term.role_genders)):
                errors.append(f"互动 {term.name} 的角色条件不满足。")
        if catalog.canonical(term.name) == "eye contact":
            for actor in scene.actors:
                if actor.actor_id in relation.participants and any(catalog.canonical(catalog.terms[value.term_key].name) == "closed eyes" for value in actor.facts):
                    errors.append(f"互动 {term.name} 的 {actor.actor_id} 闭着双眼，不能建立目光接触。")
        if catalog.canonical(term.name) == "looking at another" and relation.participants:
            observer = next((actor for actor in scene.actors if actor.actor_id == relation.participants[0]), None)
            if observer and any(dict(catalog.terms[value.term_key].features).get("eyes.state") == "closed" for value in observer.facts):
                errors.append(f"互动 {term.name} 的观察者 {observer.actor_id} 闭着双眼。")
        if "another's hair" in catalog.canonical(term.name) and len(relation.participants) > 1:
            target = next((actor for actor in scene.actors if actor.actor_id == relation.participants[1]), None)
            if target and any(dict(catalog.terms[value.term_key].features).get('hair.present') == 'no' for value in target.facts):
                errors.append(f'互动 {term.name} 的 {target.actor_id} 没有头发。')
        if complete:
            for actor_id, references in zip(relation.participants, term.role_requires):
                actor = next((value for value in scene.actors if value.actor_id == actor_id), None)
                if actor:
                    names = {catalog.canonical(catalog.terms[value.term_key].name) for value in actor.facts}
                    names.update(parent for name in tuple(names) for parent in catalog.implied(name))
                    owned = {catalog.canonical(catalog.terms[value.fact.term_key].name) for value in scene.objects if value.owner == actor_id}
                    for reference in references:
                        kind, name = reference.split(":", 1)
                        if catalog.canonical(name) not in (owned if kind == "object" else names):
                            errors.append(f"互动 {term.name} 的 {actor_id} 缺少 {reference}。")
    if len({item.object_id for item in scene.objects}) != len(scene.objects):
        errors.append("道具 ID 必须唯一。")
    if any(catalog.terms[item.fact.term_key].scope != "object" and not catalog.terms[item.fact.term_key].object_capable for item in scene.objects):
        errors.append("道具包含了其他归属类型的属性。")
    adult = any(catalog.terms[fact.term_key].adult for fact in facts)
    if adult and any(actor.age_state != "adult" for actor in scene.actors):
        errors.append("成人内容的所有主体必须已确定成年。")
    if adult and any(actor.kind != 'humanoid' for actor in scene.actors):
        errors.append('成人内容不支持非人形主体。')
    for fact in facts:
        term = catalog.terms[fact.term_key]
        if len(scene.actors) < term.min_actors:
            errors.append(f"{term.name} 至少需要 {term.min_actors} 个主体。")
        count_tag = re.fullmatch(r'([1-4])(girl|boy|other)s?', catalog.canonical(term.name)) if term.slot == 'count' else None
        if count_tag:
            gender = {'girl': 'female', 'boy': 'male', 'other': 'unknown'}[count_tag[2]]
            if sum(actor.gender == gender and actor.kind == 'humanoid' for actor in scene.actors) != int(count_tag[1]):
                errors.append(f'{term.name} 与实际主体数量不符。')
        for condition in term.conditions:
            if condition == "ordinary_only" and adult:
                errors.append(f"{term.name} 不能与成人内容组合。")
            elif condition == 'creature_only' and any(actor.kind != 'creature' for actor in scene.actors):
                errors.append(f'{term.name} 与人形主体冲突。')
            elif condition == "different_copyrights":
                works = {work for actor in scene.actors if actor.character and (profile := catalog.character(actor.character)) for work in profile.copyrights}
                if len(works) < 2:
                    errors.append(f"{term.name} 需要来自不同作品的角色。")
            elif condition == "known_identity" and not any(actor.character for actor in scene.actors):
                errors.append(f"{term.name} 需要已有角色身份。")
            elif condition == 'original_only' and term.scope != 'actor' and any(actor.character for actor in scene.actors
                    if term.scope != 'relation' or any(actor.actor_id in relation.participants for relation in scene.interactions if relation.fact.term_key == term.key)):
                errors.append(f"{term.name} 不能替已有角色推断未核对的身份关系。")
            elif condition.startswith(("female:", "male:", "unknown:")):
                gender, count = condition.split(":")
                if sum(actor.gender == gender and actor.kind == 'humanoid' for actor in scene.actors) < int(count):
                    errors.append(f"{term.name} 的人物数量条件不满足。")

    def inspect(group, owner):
        scoped = compact_facts(group, catalog)
        by_slot = {}
        for fact in scoped:
            term = catalog.terms[fact.term_key]
            if term.scope != ("actor" if owner else "scene"):
                errors.append(f"{term.name} 的归属对象类型不正确。")
            by_slot.setdefault(term.slot, []).append(term)
            if owner:
                actor = next(value for value in scene.actors if value.actor_id == owner)
                for condition in term.conditions:
                    if condition.startswith("gender:") and actor.gender != condition.split(":", 1)[1]:
                        errors.append(f"{owner} 的 {term.name} 与主体性别不符。")
                    if condition.startswith('age:') and actor.age_state != condition.split(':', 1)[1]:
                        errors.append(f'{owner} 的 {term.name} 与主体年龄状态不符。')
                    if condition == 'original_only' and actor.character:
                        profile = catalog.character(actor.character)
                        identity = profile.identity if profile else ()
                        sourced = any(slot == term.slot and (catalog.canonical(tag) == catalog.canonical(term.name)
                                      or catalog.canonical(term.name) in catalog.implied(tag)) for slot, tag in identity)
                        if not sourced:
                            errors.append(f'{owner} 的 {term.name} 没有对应的角色身份依据。')
        capabilities = {value for terms in by_slot.values() for term in terms for value in term.provides}
        for slot, terms in by_slot.items():
            multicolor = slot in {"hair.color", "eyes.color"} and multicolor_capability(slot, terms)
            layered_garment = slot in {'top', 'bottom', 'outerwear'} and 'layered_outfit' in capabilities
            if slot in SINGLE_SLOTS and len(terms) > 1 and not multicolor and not layered_garment:
                errors.append(f"{owner or '画面'} 的 {slot} 冲突：{', '.join(term.name for term in terms)}")
            if multicolor and any('rainbow' in catalog.canonical(term.name) for term in terms) and any('two-tone' in catalog.canonical(term.name) for term in terms):
                errors.append(f"{owner} 的彩虹配色与仅两色规则冲突。")
        feature_values = {}
        for terms in by_slot.values():
            for term in terms:
                for name, value in term.features:
                    feature_values.setdefault(name, {}).setdefault(value, []).append(term.name)
        for name, values in feature_values.items():
            color_context = name.removesuffix(".color")
            layered = name == "clothing.sleeves.length" and "layered_sleeves" in capabilities
            if len(values) > 1 and not layered and not (name.endswith(".color") and multicolor_capability(name, capabilities)):
                errors.append(f"{owner or '画面'} 的 {name} 冲突：{', '.join(tag for tags in values.values() for tag in tags)}")
        # Clothing ensembles may be described by their components. A one-piece
        # garment occupies upper and lower layers, while outerwear is independent.
        outfit = by_slot.get("outfit", ())
        one_piece = {"dress", "kimono", "yukata", "cheongsam", "bodysuit", "swimsuit", "one-piece swimsuit"}
        if any((term.head or term.name.replace("_", " ")) in one_piece for term in outfit) and ("top" in by_slot or "bottom" in by_slot) and 'layered_outfit' not in capabilities and not ('inner_top_layer' in capabilities and 'bottom' not in by_slot):
            errors.append(f"{owner} 的连体服装与另一套内层服装冲突。")
        styles = by_slot.get("hair.style", ())
        lengths = by_slot.get("hair.length", ())
        if any(catalog.canonical(term.name) in ("pixie cut", "bob cut") for term in styles) and any(LENGTH_LEVELS.get(term.name.replace("_", " "), 0) >= 2 for term in lengths):
            errors.append(f"{owner} 的短发剪裁与长发冲突。")
        local = (*scoped, *scene.facts) if owner else scoped
        term_names = {catalog.canonical(catalog.terms[fact.term_key].name) for fact in local}
        for fact in local:
            term_names.update(catalog.implied(catalog.terms[fact.term_key].name))
        slots = {catalog.terms[fact.term_key].slot for fact in local}
        held_objects = {catalog.canonical(catalog.terms[item.fact.term_key].name) for item in scene.objects if item.owner == owner}
        held_objects.update(catalog.terms[item.fact.term_key].head for item in scene.objects if item.owner == owner)
        def dependency_present(reference):
            prefix, value = reference.split(':', 1)
            if prefix == 'object':
                return catalog.canonical(value) in held_objects
            required = catalog.term(value)
            # An implication in another facet cannot override an explicitly
            # conflicting base attribute (e.g. one-legged standing plus lying).
            if required and required.slot in by_slot:
                return any(catalog.canonical(value) == catalog.canonical(candidate.name)
                           or catalog.canonical(value) in catalog.implied(candidate.name)
                           for candidate in by_slot[required.slot])
            return catalog.canonical(value) in term_names
        for fact in scoped:
            term = catalog.terms[fact.term_key]
            for reference in term.excludes:
                prefix, value = reference.split(":", 1)
                conflicting = value in slots if prefix == "slot" else catalog.canonical(value) in term_names
                required = catalog.term(value)
                if required and prefix == required.slot:
                    # An attached hood belongs to the outer garment. Its
                    # implication is not a second fact saying a hood is worn on
                    # the head; exclusions must respect the requested facet.
                    conflicting = any(candidate.slot == prefix and (catalog.canonical(value) == catalog.canonical(candidate.name)
                        or catalog.canonical(value) in catalog.implied(candidate.name))
                        for candidate in (catalog.terms[item.term_key] for item in local))
                if conflicting:
                    errors.append(f"{owner or '画面'}：{term.name} 与 {reference} 冲突。")
            if complete:
                for reference in term.requires:
                    prefix, value = reference.split(":", 1)
                    present = dependency_present(reference)
                    if not present:
                        errors.append(f"{owner or '画面'}：{term.name} 缺少 {reference}。")
                for alternatives in term.any_dependencies:
                    if not any(dependency_present(reference) for reference in alternatives):
                        errors.append(f"{owner or '画面'}：{term.name} 缺少任选依赖 {' / '.join(alternatives)}。")
                for alternatives in term.required_slots:
                    if not any(slot in by_slot for slot in alternatives):
                        errors.append(f"{owner or '画面'}：{term.name} 缺少属性槽 {' / '.join(alternatives)}。")
                for name, quantity in term.object_counts:
                    count = sum(item.owner == owner and (catalog.canonical(catalog.terms[item.fact.term_key].name) == catalog.canonical(name)
                                or catalog.terms[item.fact.term_key].head == catalog.canonical(name)
                                or catalog.canonical(name) in catalog.implied(catalog.terms[item.fact.term_key].name)) for item in scene.objects)
                    if count < quantity:
                        errors.append(f"{owner or '画面'}：{term.name} 至少需要 {quantity} 个 {name}，当前只有 {count} 个。")
    inspect(scene.facts, None)
    for actor in scene.actors:
        if actor.gender not in {"female", "male", "unknown"} or actor.age_state not in {"adult", "minor", "unknown"}:
            errors.append(f"{actor.actor_id} 的主体属性无效。")
        inspect(actor.facts, actor.actor_id)
        if actor.kind not in {"humanoid", "creature"}:
            errors.append(f"{actor.actor_id} 的主体类型无效。")
        if actor.kind == "creature" and any(catalog.terms[fact.term_key].slot in {"outfit", "top", "bottom", "outerwear", "underwear", "underwear.top", "underwear.bottom", "footwear", "legwear", "handwear", "hands.pose", "legs.pose"} for fact in actor.facts):
            errors.append(f"{actor.actor_id} 的非人形档案不支持人形服装或四肢姿势。")
        if actor.character:
            profile = catalog.character(actor.character)
            if not profile:
                errors.append(f"角色 {actor.character} 尚无可用身份档案。")
            else:
                if actor.gender != profile.gender or actor.age_state != profile.age_state or actor.kind != profile.kind:
                    errors.append(f"角色 {actor.character} 的性别或年龄状态与档案不同。")
                values = {}
                for fact in actor.facts:
                    term = catalog.terms[fact.term_key]
                    values.setdefault(term.slot, set()).add(catalog.canonical(term.name))
                expected = {}
                for slot, name in profile.identity:
                    expected.setdefault(slot, set()).add(catalog.canonical(name))
                protected = {'hair.color', 'hair.length', 'hair.style', 'hair.texture', 'eyes.color', 'skin.color', 'body.ears', 'body.horns', 'body.wings', 'body.tail', 'body.species'}
                for slot in protected & values.keys():
                    declared = expected.get(slot, set())
                    for value in values[slot]:
                        if not any(value == attribute or attribute in catalog.implied(value) or value in catalog.implied(attribute) for attribute in declared):
                            errors.append(f'角色 {actor.character} 的 {slot} 没有对应的身份依据：{value}。')
                # Multiple fur/scale colors can be legitimate patches, but a
                # known identity must keep its sourced palette. Additive color
                # facts must not let a new color bypass the identity lock.
                palettes, palette_terms = {}, {}
                for _, name in profile.identity:
                    reference = catalog.term(name)
                    for feature, value in reference.features if reference else ():
                        match = re.fullmatch(r'body\.(fur|scales)\.color(?:\.(.+))?', feature)
                        if match:
                            palettes.setdefault(match[1], set()).add(match[2] or value)
                            palette_terms.setdefault(match[1], set()).add(catalog.canonical(name))
                for fact in actor.facts:
                    candidate = catalog.terms[fact.term_key]
                    for feature, value in candidate.features:
                        match = re.fullmatch(r'body\.(fur|scales)\.color(?:\.(.+))?', feature)
                        if match and (match[2] or value) not in palettes.get(match[1], ()):
                            canonical = catalog.canonical(candidate.name)
                            if not any(canonical == name or canonical in catalog.implied(name) or name in catalog.implied(canonical)
                                    for name in palette_terms.get(match[1], ())):
                                errors.append(f'角色 {actor.character} 的 {match[1]} 配色没有对应的身份依据：{candidate.name}。')
                for slot, name in profile.identity:
                    actual = values.get(slot, set())
                    required = catalog.canonical(name)
                    satisfied = required in actual or any(required in catalog.implied(value) for value in actual)
                    if complete and not satisfied:
                        errors.append(f"角色 {actor.character} 的固定属性 {slot} 未保留。")
                    elif actual and not satisfied:
                        errors.append(f"角色 {actor.character} 的固定属性 {slot} 冲突。")
                    if slot in {"hair.color", "eyes.color", "hair.length", "skin.color"} and any(value not in expected[slot] and not any(
                           declared in catalog.implied(value) or value in catalog.implied(declared) for declared in expected[slot]) for value in actual):
                        errors.append(f"角色 {actor.character} 的固定属性 {slot} 被其他取值覆盖。")
    return tuple(dict.fromkeys(errors))


def require_valid(scene, catalog):
    errors = validate_scene(scene, catalog)
    if errors:
        raise ConfigurationError("；".join(errors))
    return scene


def series(values):
    values = list(values)
    return ", ".join(values[:-1]) + " and " + values[-1] if len(values) > 1 else (values[0] if values else "")


def article(value):
    if value.startswith(("a ", "an ", "the ", "two ", "three ", "four ", "both ", "multiple ")):
        return value
    # An absence is stated, not counted: "no cape" and "missing wings" are
    # already complete noun phrases and must not gain an article.
    if value.startswith(("no ", "without ", "missing ", "absent ")):
        return value
    if value.split()[-1] in {'gold', 'cream', 'sauce', 'corn', 'trash', 'stubble', 'tanlines', 'facepaint', 'cuffs', 'sunglasses', 'eyewear', 'headwear', 'bobbles', 'tails', 'joints', 'extremities', 'fur'}:
        return value
    if value.split()[-1] in {"twintails", "braids", "ringlets", "bangs", "sidelocks", "ears", "fangs", "horns", "wings", "fingernails", "toenails", "nails", "teeth", "pupils", "eyebrows", "eyelashes", "breasts", "freckles", "hair", "skin", "blush", 'footwear', 'pectorals', 'petals', 'leaves', 'plants', 'flowers', 'antennae'}:
        return value
    if value.split()[-1] in {"earrings", "glasses", "shoes", "boots", "sandals", "sneakers", "heels", "pants", "jeans", "shorts", "gloves", "socks", "thighhighs", "pantyhose", "kneehighs", "leggings", "mittens", "slippers", "loafers", "pumps", "warmers", "overalls", "pajamas", "food", "fruit", "coffee", "tea", "juice", "milk", "rice", "ramen", "sushi", "paper", "grapes", "headphones", "earphones", "chopsticks", "noodles", "curtains", "tubes", "cuffs", "chains", "rings", "skates", "sleeves", "bloomers", "culottes", "sweatpants", "bell-bottoms", "dreadlocks", "cornrows", "clogs", "moccasins", "espadrilles", "cleats", "gauntlets", "jewelry", "clothes", "armor", "armour", "bandages", "drills"}:
        return value
    consonant_sound = value.lower().startswith(("one", "uni", "euro"))
    return ("an " if value[:1].lower() in "aeiou" and not consonant_sound else "a ") + value


def render_english(scene, catalog):
    paragraphs = []
    for actor in scene.actors:
        noun = {"female": "woman", "male": "man", "unknown": "person"}[actor.gender] if actor.age_state == "adult" else {"female": "female character", "male": "male character", "unknown": "character"}[actor.gender]
        identity = actor.character.replace("_", " ").title() if actor.character else noun
        opening = f"Character {actor.actor_id[1:]} is {identity if actor.character else article(identity)}"
        grouped = {}
        for fact in compact_facts(actor.facts, catalog):
            term = catalog.terms[fact.term_key]
            grouped.setdefault(term.slot, []).append(term.phrase)
        appearance = []
        hair_slots = ("hair.color", "hair.length", "hair.texture")
        hair = [phrase for slot in hair_slots for phrase in grouped.get(slot, ())]
        if len(grouped.get("hair.color", ())) == 1 and len(grouped.get("hair.length", ())) == 1 and len(grouped.get("hair.texture", ())) <= 1:
            hair = [" ".join([phrase.removesuffix(" hair") for slot in ("hair.length", "hair.texture", "hair.color") for phrase in grouped.get(slot, ())]) + " hair"]
        styles = [{"one side up": "one-sided updo", "two side up": "two-sided updo"}.get(phrase, phrase)
                  for phrase in grouped.get("hair.style", ())]
        if hair and styles:
            hair[-1] += " styled in " + series(article(phrase) for phrase in styles)
        else:
            hair.extend(article(phrase) for phrase in styles)
        appearance.extend(hair)
        appearance.extend(phrase for slot in ("hair.detail", "eyes.color", "skin.color") for phrase in grouped.get(slot, ()))
        appearance.extend(article(phrase) for slot in ('body.detail', 'body.breast_size', 'body.ears', 'body.wings', 'body.horns', 'body.tail', 'body.halo') for phrase in grouped.get(slot, ()))
        if appearance:
            opening += " with " + series(appearance)
        garments = [phrase for slot in ("outfit", "top", "bottom", "outerwear", "footwear", "legwear", "handwear", "headwear", "accessory") for phrase in grouped.get(slot, ())]
        lines = [opening + "."]
        if garments:
            lines.append("This character wears " + series(article(phrase) for phrase in garments) + ".")
        for slot, lead in (("coverage", "This character is "), ("posture", "Their posture is "), ("action", "This character is "), ("expression", "Their expression is "), ("gaze", "This character is "), ("mouth", "Their mouth is "), ("eyes.state", "Their eyes are "), ("clothing.detail", "Their clothing has ")):
            phrases = grouped.get(slot, ())
            if phrases:
                lines.append(lead + series(phrases) + ".")
        props = [catalog.terms[item.fact.term_key].phrase for item in scene.objects if item.owner == actor.actor_id]
        if props:
            lines.append("Their associated objects include " + series(article(phrase) for phrase in props) + ".")
        handled = {*hair_slots, "hair.style", "hair.detail", "eyes.color", "skin.color", "body.detail", "body.breast_size",
                   "outfit", "top", "bottom", "outerwear", "footwear", "legwear", "handwear", "headwear", "accessory",
                   "coverage", "posture", "action", "expression", "gaze", "mouth", "eyes.state", "clothing.detail",
                   'body.ears', 'body.wings', 'body.horns', 'body.tail', 'body.halo'}
        additional = [phrase for slot, phrases in grouped.items() if slot not in handled for phrase in phrases]
        if additional:
            lines.append("Further details for this character include " + series(additional) + ".")
        paragraphs.append(" ".join(lines))
    for relation in scene.interactions:
        term = catalog.terms[relation.fact.term_key]
        phrase = term.phrase
        if term.role_phrase:
            names = ["Character " + item[1:] for item in relation.participants]
            paragraphs.append(term.role_phrase.format(*names).rstrip(".") + ".")
            continue
        if catalog.canonical(catalog.terms[relation.fact.term_key].name) == "eye contact":
            phrase = "making eye contact"
        elif catalog.canonical(catalog.terms[relation.fact.term_key].name) == "locked arms":
            phrase = "linking arms with each other"
        participants = series("Character " + item[1:] for item in relation.participants)
        paragraphs.append(f"{participants} are {phrase}.")
    global_groups = {}
    for fact in compact_facts(scene.facts, catalog):
        term = catalog.terms[fact.term_key]
        global_groups.setdefault(term.slot, []).append(term.phrase)
    for slots, lead in ((("location", "environment", "time", "weather", "scene.detail"), "The setting includes "), (("framing", "view", "focus"), "The framing uses "), (("lighting",), "The lighting is "), (("style",), "The visual style is "), (("background",), "The background uses "), (("border", "symbol", "text", "effect"), "Visual details include ")):
        values = [phrase for slot in slots for phrase in global_groups.get(slot, ())]
        if values:
            paragraphs.append(lead + series(values) + ".")
    unowned = [catalog.terms[item.fact.term_key].phrase for item in scene.objects if item.owner is None]
    if unowned:
        paragraphs.append("The scene also includes " + series(article(phrase) for phrase in unowned) + ".")
    return "\n\n".join(paragraphs)


def render_tags(scene, catalog, vocabulary, *, underscore_to_space=False):
    if scene.imported_tokens:
        return ", ".join(scene.imported_tokens)
    names = []
    def literal(name):
        # Literal punctuation in emotes and qualified names must not become
        # an emphasis group or an unmatched delimiter in an external prompt.
        return name.replace('\\', '\\\\').replace('(', r'\(').replace(')', r'\)').replace('[', r'\[').replace(']', r'\]')
    genders = {gender: sum(actor.gender == gender and actor.kind == "humanoid" for actor in scene.actors) for gender in ("female", "male", "unknown")}
    for gender, suffix in (("female", "girl"), ("male", "boy"), ("unknown", "other")):
        count = genders[gender]
        if count:
            identity = "general:" + str(count) + suffix + ("s" if count > 1 else "")
            if identity in vocabulary:
                names.append(vocabulary[identity][0])
    if len(scene.actors) == 1 and "general:solo" in vocabulary:
        names.append(vocabulary["general:solo"][0])
    if all(actor.kind == 'creature' for actor in scene.actors) and 'general:no humans' in vocabulary:
        names.append(vocabulary['general:no humans'][0])
    for actor in scene.actors:
        if actor.character:
            spelling = vocabulary.get("character:" + catalog.canonical(actor.character))
            if spelling:
                names.append(literal(spelling[0]))
    for fact in all_facts(scene):
        term = catalog.terms[fact.term_key]
        identity = term.category + ":" + catalog.canonical(term.name)
        if identity not in vocabulary:
            raise ConfigurationError(f"所选词表中没有 {term.name}，无法生成等价 tags。")
        spelling = literal(vocabulary[identity][0])
        names.append(f"({spelling}:{fact.weight:g})" if fact.weight is not None else spelling)
    names.extend(scene.opaque_tokens)
    seen = set()
    result = []
    for name in names:
        from app.prompts.injection import token_key
        canonical = catalog.canonical(token_key(name))
        if canonical not in seen:
            seen.add(canonical)
            result.append(name.replace("_", " ") if underscore_to_space else name)
    return ", ".join(result)


def scene_summary(scene, catalog):
    rows = [f"主体 {len(scene.actors)} 个 · 主题 {scene.theme}"]
    for actor in scene.actors:
        rows.append(f"{actor.actor_id} · {actor.character or ('原创女性' if actor.gender == 'female' else '原创男性' if actor.gender == 'male' else '原创主体')}\n  " + ", ".join(catalog.terms[fact.term_key].name for fact in actor.facts))
    rows.append("画面 · " + ", ".join(catalog.terms[fact.term_key].name for fact in scene.facts))
    if scene.interactions:
        rows.append("互动 · " + "; ".join(f"{'/'.join(item.participants)}: {catalog.terms[item.fact.term_key].name}" for item in scene.interactions))
    return "\n".join(rows)
