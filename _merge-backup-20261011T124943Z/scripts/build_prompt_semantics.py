"""Compile source-backed vocabulary; source acquisition is not semantic review."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
from functools import lru_cache
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.prompts.normalizer import canonical_tag_key as key
from app.prompts.semantic_rules import infer_composition, is_adult_term, primitive, REVIEWED, SINGLE_SLOTS
from scripts.fetch_prompt_semantics import inventory, write_json
from scripts.prompt_semantic_families import infer_definition, plain, definition
from scripts.prompt_semantic_explicit import explicit_rule, relational_rule
from scripts.prompt_semantic_dependencies import dependent_rule, enrich_rule
from scripts.prompt_semantic_attributes import attribute_rule
from scripts.prompt_semantic_supplement import supplemental_rule
from scripts.prompt_semantic_species import species_feature_rule
from scripts.prompt_semantic_negation import negation_rule, needs_identity_baseline
from scripts.prompt_semantic_concepts import concept_rule
from scripts.prompt_semantic_characters import reference_profile


def wiki_title(name):
    return name.replace(" ", "_").casefold()


def introduction(body):
    body = body.replace("\r", "\n")
    return re.split(r"(?im)^h[1-6]\.\s*(?:variants|alternate|skins|costumes|gallery|see also|external|voice|spoiler)", body, maxsplit=1)[0]


@lru_cache(maxsize=4)
def attribute_pattern(tags):
    return re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(tag) for tag in sorted(tags, key=lambda tag: (-len(tag), tag))) + r")(?![\w-])", re.I)


def character_profile(name, page, ips, aliases, rules=None, implications=None):
    rules = rules or REVIEWED
    body = introduction(page["body"])
    # Only a character's own declarative appearance passages qualify. Lists of
    # alternate costumes or other characters must not establish fixed traits.
    title = re.sub(r"\s*\([^)]*\)", "", name.replace("_", " ")).strip()
    # A literal title subject and an introductory appearance sentence have the
    # same attribution as "She has ...". Do not match a surname substring, a
    # relative's appearance, or a different named character on the same page.
    names = {title} if title else set()
    names.update(plain(alias).replace('_', ' ').strip() for alias in page.get('other_names', ()) if len(alias) > 2 and '(' not in alias)
    if len(title.split()) == 2 and re.match(r'^[a-z]+ [a-z]+$', title, re.I):
        # The final given name is used as the actual sentence subject in many
        # Japanese-character pages. Relatives and another named subject remain
        # excluded by the attribution checks below.
        names.update(title.split())
    named = '(?:' + '|'.join(re.escape(value) for value in sorted(names, key=len, reverse=True)) + ')' if names else r'(?!)'
    subject = rf"(?:she|he|her|his|they|their|this character|the character|{named}|(?:an?\s+)(?:young\s+|adult\s+|teenage\s+)?(?:girl|boy|woman|man))"
    passages = []
    for line in body.splitlines():
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            clean = plain(sentence)
            clean = re.sub(r"(?i)^(?:in (?:her|his|their|the|canon) (?:default |original |usual |canon )?(?:appearance|design|form)|in canon appearance),?\s*", "", clean)
            if re.match(rf"(?i)^{subject}\b", clean):
                passages.append((sentence, clean))
    physical_modifier = r'(?:short|medium|long|very|absurdly|straight|curly|wavy|messy|aqua|black|blue|brown|green|grey|orange|pink|purple|red|white|yellow|blonde|silver|gold|two-tone|multicolored)'
    own_start = rf"(?i)^(?:(?:she|he|they|{named})\s+(?:also\s+)?(?:has|have|is|are|wears|sports|features|appears|can\s+be|looks\s+(?:very\s+)?similar)|(?:her|his|their|{named}'s)\s+(?:default\s+|original\s+|usual\s+)?(?:{physical_modifier}\s+){{0,4}}(?:hair\b|eyes?\b|skin\b|appearance\b|hairstyle\b|design\b|model\b)|an?\s+(?:young\s+|adult\s+|teenage\s+)?(?:girl|boy|woman|man)\s+with\b)"
    relatives = r"(?i)\b(?:her|his|their)\s+(?:sister|brother|mother|father|friend|daughter|son|wife|husband|companion)\b"
    appearances = [(raw, text) for raw, text in passages if re.match(own_start, text)
                   and not re.search(relatives, text)
                   and re.search(r"\b(hair|eyes|recognizable|appearance|hairstyle)\b", text, re.I)]
    # An omitted subject in an introductory/default appearance definition refers
    # to the page's character. Other sections and variant descriptions do not.
    default_section = True
    for raw in body.replace('\r', '\n').splitlines():
        if heading := re.match(r'h[1-6](?:#[\w-]+)?\.\s*(.+)', raw.strip(), re.I):
            default_section = heading[1].strip().lower() in {'appearance', 'default appearance', 'original appearance', 'description', 'character design'}
            continue
        text = plain(raw)
        if default_section and re.match(r'(?i)^has\s+', text) and re.search(r'\b(?:hair|eyes|fur|tail|wings|ears)\b', text) and not re.search(r'(?i)\b(?:sometimes|alternate|variant|depending|another|other character)\b', text):
            appearances.append((raw, text))
        if default_section and re.match(r'(?i)^an?\s+(?:[\w-]+\s+){0,5}(?:girl|boy|woman|man|male|female|teenager|person)\s+with\b', text) and re.search(r'\b(?:hair|eyes)\b', text):
            appearances.append((raw, text))
    creature = any(key(label.split('|', 1)[0]) in {'pokemon (creature)', 'digimon (creature)'} for label in re.findall(r'\[\[([^\]]+)\]\]', body))
    if creature:
        for raw in body.replace('\r', '\n').splitlines():
            text = plain(raw)
            if re.match(r"(?i)^(?:an?\s+.{0,120}\b(?:creature|pokémon|pokemon|digimon|monster)\b|(?:it|its)\s+(?:is|has|body|fur|eyes|skin|head|tail|wings)\b)", text) and not re.search(r'\b(?:evolve|evolves|evolution|mega|other|another|trainer|sometimes|varies|depending)\b', text, re.I):
                appearances.append((raw, text))
    gender_words = {"female" if re.match(r"(?i)(she|her)\b", text) else "male" for _, text in appearances if re.match(r"(?i)(she|her|he|his)\b", text)}
    for _, text in appearances:
        if re.match(r"(?i)an?\s+(?:young\s+|adult\s+|teenage\s+)?(?:girl|woman)\b", text):
            gender_words.add("female")
        elif re.match(r"(?i)an?\s+(?:young\s+|adult\s+|teenage\s+)?(?:boy|man)\b", text):
            gender_words.add("male")
    if not gender_words and appearances:
        gender_words = {"female" if re.match(r"(?i)she\b", text) else "male" for _, text in passages
                        if re.match(r"(?i)(she|he)\s+(has|is|wears)\b", text) and not re.search(relatives, text)}
    clothing_start = rf"(?i)^(?:(?:she|he|they|{named})\s+(?:wears|wear|dons|sports)\b|(?:her|his|their|{named}'s)\s+(?:default\s+|original\s+)?(?:outfit|uniform|costume|clothing|attire)\s+(?:is|consists|includes)\b)"
    clothing = [(raw, text) for raw, text in passages if re.match(clothing_start, text) and not re.search(relatives, text)
                and not re.search(r"\b(?:or|sometimes|often|usually|occasionally|may|can|alternate|varies|depending|when|if)\b", text, re.I)]
    if not gender_words:
        gender_words = {"female" if re.match(r"(?i)(she|her)\b", text) else "male" for _, text in clothing if re.match(r"(?i)(she|her|he|his)\b", text)}
    if len(gender_words) > 1 and not creature:
        return None
    linked = [key(match.split("|", 1)[0]) for text, _ in appearances for match in re.findall(r"\[\[([^\]]+)\]\]", text)]
    # Ordinary prose is evidence too, e.g. "She has short purple hair and green
    # eyes". Match complete registered attributes; bare color words do not count.
    color_attributes = {tag: rule for tag, rule in rules.items() if rule["slot"] in {"hair.color", "eyes.color", "hair.length", "hair.texture", "skin.color"}}
    accessory_suffix = r"(?i)^\s+(?:bow|ribbon|tie|clip|ornament|band|scrunchie|bracelet|pin|beads|bobbles|flower|tube)s?\b"
    for _, text in appearances:
        linked.extend(key(match.group(0)) for match in attribute_pattern(tuple(sorted(color_attributes))).finditer(text)
                      if not ("hair" in match.group(0) and re.match(accessory_suffix, text[match.end():])))
        # Length and color can share a noun without repeating "hair".
        for length in ("short", "medium", "long", "very long", "absurdly long"):
            if (match := re.search(r"(?<![\w-])" + re.escape(length) + r"\s+(?:[\w-]+\s+){0,2}hair\b", text, re.I)) and not re.match(accessory_suffix, text[match.end():]):
                linked.append(key(length + " hair"))
        # Attributed reverse order: "Her eyes are green" defines eye color,
        # whereas an unrelated green accessory in that sentence does not.
        for noun, suffix in (('hair', 'hair'), ('eyes', 'eyes'), ('skin', 'skin')):
            if match := re.match(rf"(?i)^(?:her|his|their|{named}'s)\s+{noun}\s+(?:is|are)\s+(?:an?\s+)?(?:[\w-]+\s+){{0,2}}(aqua|black|blue|brown|green|grey|orange|pink|purple|red|white|yellow|blonde|silver)\b", text):
                tag = key(match[1] + ' ' + suffix)
                if tag in rules:
                    linked.append(tag)
    values = {}
    for tag in linked:
        tag = aliases.get(tag, tag)
        rule = rules.get(tag)
        allowed_traits = {"hair.color", "hair.length", "eyes.color", "hair.style", "hair.texture", "skin.color", "body.ears", "body.tail", "body.horns", "body.wings", "body.halo", "body.detail", "body.shape", "eyes.detail"}
        if rule and rule['slot'] in allowed_traits and not rule.get('adult') and not rule.get('requires') and not rule.get('required_slots'):
            values.setdefault(rule["slot"], set()).add(tag)
    wear_slots = {"outfit", "top", "bottom", "outerwear", "footwear", "legwear", "handwear", "headwear", "accessory"}
    for raw, _ in clothing:
        for label in re.findall(r"\[\[([^\]]+)\]\]", raw):
            tag = aliases.get(key(label.split("|", 1)[0]), key(label.split("|", 1)[0]))
            rule = rules.get(tag)
            if rule and rule["slot"] in wear_slots and not rule.get("adult"):
                values.setdefault(rule["slot"], set()).add(tag)
    # A generic hair length is not a second version of a more specific length.
    lengths = values.get("hair.length", set())
    for broad, specific in (("long hair", "very long hair"), ("long hair", "absurdly long hair"), ("very long hair", "absurdly long hair")):
        if broad in lengths and specific in lengths:
            lengths.discard(broad)
    for slot, items in values.items():
        ancestors = set()
        for tag in items:
            pending, seen = [tag], set()
            while pending:
                current = pending.pop()
                for parent in (implications or {}).get(current, ()):
                    if parent not in seen:
                        seen.add(parent)
                        pending.append(parent)
            ancestors.update(seen)
            if slot == "hair.color":
                ancestors.update(other for other in items if tag.startswith(("light " + other, "dark " + other, "platinum " + other)))
        items.difference_update(ancestors)
    uncertain = {slot: sorted(items) for slot, items in values.items() if len(items) > 1 and slot in SINGLE_SLOTS}
    stable = {slot: next(iter(items)) if len(items) == 1 else sorted(items) for slot, items in values.items() if len(items) == 1 or slot not in SINGLE_SLOTS}
    # Unknown stable slots are omitted; generation will not invent new hair/eye
    # colors for a known identity. A single generic trait is insufficient.
    if len(stable) < 2 or not ({"hair.color", "eyes.color"} & stable.keys()) and len(stable) < 3:
        return None
    age_pattern = r"(?i)\b(?:age\s*[:：]\s*|(?:she|he|they|" + named + r")\s+(?:is|are)\s+(?:an?\s+)?)(\d{1,3})(?:\s*years?\s*old|[- ]year[- ]old|(?=\s*(?:\n|$)))"
    age_matches = list(re.finditer(age_pattern, plain(body)))
    ages = [int(match[1]) for match in age_matches]
    age_state = "unknown"
    if ages and all(age >= 18 for age in ages):
        age_state = "adult"
    elif ages and all(age < 18 for age in ages):
        age_state = "minor"
    if age_state == 'adult' and any(re.search(r'\b(?:child-like|childlike|prepubescent|preadolescent|young child|toddler)\b', text, re.I) for _, text in appearances):
        age_state = 'unknown'
    variants = tuple(sorted({wiki_title(item.split("|", 1)[0]) for item in re.findall(r"\[\[([^\]]+)\]\]", page["body"]) if name.split("_(", 1)[0] in wiki_title(item)} - {name}))
    wardrobe = {slot: value for slot, value in stable.items() if slot in wear_slots}
    stable = {slot: value for slot, value in stable.items() if slot not in wear_slots}
    return {"gender": next(iter(gender_words)) if len(gender_words) == 1 else 'unknown',
            "kind": 'creature' if creature else 'humanoid',
            "identity": {slot: [tag.replace(' ', '_') for tag in value] if isinstance(value, list) else value.replace(' ', '_') for slot, value in stable.items()},
            "wardrobe": {slot: [tag.replace(' ', '_') for tag in value] if isinstance(value, list) else value.replace(' ', '_') for slot, value in wardrobe.items()},
            "copyrights": ips.get(name, []), "age_state": age_state, "variants": variants,
            "sources": ["https://danbooru.donmai.us/wiki_pages/" + name],
            "appearance_evidence": [raw for raw, _ in (*appearances, *clothing)], "uncertain_slots": uncertain,
            "age_evidence": [match[0] for match in age_matches], "review_method": "unique_own_appearance_prose_v5"}


def build(cache, destination):
    data = inventory()
    wiki = json.loads((cache / "wiki.json").read_text(encoding="utf-8"))
    raw_aliases = json.loads((cache / "tag_aliases.json").read_text(encoding="utf-8"))["rows"]
    raw_implications = json.loads((cache / "tag_implications.json").read_text(encoding="utf-8"))["rows"]
    aliases = {key(row["antecedent_name"]): key(row["consequent_name"]) for row in raw_aliases if row["status"] == "active"}
    def canonical(name):
        current, seen = key(name), set()
        while current in aliases:
            if current in seen:
                raise ValueError("Upstream alias cycle")
            seen.add(current)
            current = aliases[current]
        return current
    local_names = {canonical(row["name"]) for row in data["entries"].values()}
    relevant_aliases = {name: canonical(name) for name in aliases if canonical(name) in local_names or name in local_names}
    implications = {}
    for row in raw_implications:
        if row["status"] == "active":
            source, target = canonical(row["antecedent_name"]), canonical(row["consequent_name"])
            implications.setdefault(source, set()).add(target)
    # Keep the complete ancestor closure of local roots; no unrelated global data.
    retained_implications = {}
    pending, visited = list(local_names), set()
    while pending:
        name = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        targets = implications.get(name, set())
        if targets:
            retained_implications[name] = sorted(targets)
            pending.extend(targets)
    visual = json.loads((ROOT / "resources/tag_visuals/catalog.json").read_text(encoding="utf-8"))["entries"]
    entries, characters, ledger = {}, {}, []
    for identity, original in sorted(data["entries"].items()):
        row = dict(original)
        name = row["name"]
        canonical_name = canonical(name)
        page = wiki["pages"].get(wiki_title(canonical_name)) or wiki["pages"].get(wiki_title(name))
        existing = visual.get(identity, {})
        row.update({"canonical": canonical_name, "status": "candidate" if page else "missing", "rule": None,
                    "label_zh": existing.get("label_zh", ""), "explanation_zh": existing.get("explanation_zh", ""),
                    "source": "https://danbooru.donmai.us/wiki_pages/" + wiki_title(canonical_name),
                    "source_available": bool(page), "source_updated_at": page.get("updated_at") if page else None,
                    "source_sha256": hashlib.sha256(page["body"].encode()).hexdigest() if page else None,
                    "review_method": "unreviewed", "missing_reason": "尚未核对生成规则" if page else "没有取得对应 Wiki"})
        if row["category"] == "general":
            rule, method = infer_composition(canonical_name)
            evidence, reason = None, ""
            if not rule and page:
                rule, evidence = explicit_rule(canonical_name, page)
                if not rule:
                    rule, evidence = relational_rule(canonical_name, page)
                if not rule:
                    rule, evidence = attribute_rule(canonical_name, page)
                if not rule:
                    rule, evidence = concept_rule(canonical_name, page)
                if not rule:
                    rule, evidence, reason = infer_definition(canonical_name, page)
                if not rule:
                    # A "girl/boy with <species> features" passage establishes a
                    # bodily trait of the subject, which no noun family above
                    # expresses. It runs last because the noun families are more
                    # specific when they apply.
                    rule, evidence = species_feature_rule(canonical_name, page)
                if rule:
                    method = "verified_definition_family:" + evidence["family"]
            if rule:
                rule = enrich_rule(canonical_name, rule)
                row.update(status="reviewed", rule=rule, review_method=method, missing_reason="")
                if evidence:
                    row["rule_evidence"] = evidence
                row["meaning_en"] = (evidence["definition"] if evidence else plain(definition(page["body"]))[:600] if page else rule["phrase"])
            elif existing.get("status") in {"direct", "composed", "schematic"} and existing.get("explanation_zh"):
                group = existing["group"]
                slot = {"hair": "hair.detail", "eyes": "body.detail", "face": "body.detail", "body": "body.detail", "clothing": "clothing.detail", "pose": "action", "interaction": "interaction", "object": "object", "scene": "scene.detail", "composition": "scene.detail", "lighting": "scene.detail", "style": "style", "symbol": "scene.detail"}.get(group)
                if slot:
                    row.update(status="lexical", rule=primitive(name, slot, adult=is_adult_term(name), actors=2 if group == "interaction" else 1),
                               review_method="existing_reviewed_meaning_only", missing_reason="词义已有核对；生成依赖和冲突尚待核对")
            if reason and row["status"] != "reviewed":
                row["missing_reason"] += " (" + reason + ")"
        entries[identity] = row
        ledger.append({"key": identity, "name": name, "category": row["category"], "status": row["status"], "source_available": bool(page),
                       "source": row["source"], "source_updated_at": row["source_updated_at"], "source_sha256": row["source_sha256"], "review_method": row["review_method"], "missing_reason": row["missing_reason"]})
    general_rules = {row["canonical"]: row["rule"] for row in entries.values() if row["category"] == "general" and row["status"] == "reviewed"}
    for row in entries.values():
        if row['category'] != 'general' or row['status'] == 'reviewed':
            continue
        page = wiki['pages'].get(wiki_title(row['canonical'])) or wiki['pages'].get(wiki_title(row['name']))
        if page and (result := supplemental_rule(row['canonical'], page, lambda name: general_rules.get(canonical(name))))[0]:
            rule, evidence = result
            row.update(status='reviewed', rule=enrich_rule(row['canonical'], rule),
                review_method='verified_definition_family:' + evidence['family'], missing_reason='', rule_evidence=evidence, meaning_en=evidence['definition'])
            general_rules[row['canonical']] = row['rule']
    for row in entries.values():
        if row["category"] != "general" or row["status"] == "reviewed":
            continue
        page = wiki["pages"].get(wiki_title(row["canonical"])) or wiki["pages"].get(wiki_title(row["name"]))
        if page and needs_identity_baseline(row['canonical'], page):
            row['missing_reason'] = '缺失属性需要核对原有身份及版本参照 (identity_baseline_required)'
            continue
        if page and (result := negation_rule(row["canonical"], page, lambda name: general_rules.get(canonical(name))))[0]:
            rule, evidence = result
            row.update(status="reviewed", rule=enrich_rule(row["canonical"], rule),
                       review_method="verified_definition_family:" + evidence["family"], missing_reason="", rule_evidence=evidence, meaning_en=evidence["definition"])
            general_rules[row["canonical"]] = row["rule"]
    for row in entries.values():
        if row["category"] != "general" or row["status"] == "reviewed":
            continue
        page = wiki["pages"].get(wiki_title(row["canonical"])) or wiki["pages"].get(wiki_title(row["name"]))
        if page and (result := dependent_rule(row["canonical"], page, lambda name: general_rules.get(canonical(name))))[0]:
            rule, evidence = result
            row.update(status="reviewed", rule=enrich_rule(row["canonical"], rule),
                       review_method="verified_definition_family:" + evidence["family"], missing_reason="", rule_evidence=evidence, meaning_en=evidence["definition"])
            general_rules[row["canonical"]] = row["rule"]
    from scripts.prompt_semantic_dependencies import hand_holdable
    holdable = ["object:" + name for name, rule in sorted(general_rules.items())
                if (rule['scope'] == 'object' or rule.get('object_capable')) and hand_holdable(name, rule)]
    if "holding" in general_rules:
        general_rules["holding"]["any_dependencies"] = [holdable]
    for name in ("selfie",):
        if name in general_rules:
            general_rules[name]["requires"] = []
            general_rules[name]["any_dependencies"] = [["object:smartphone", "object:camera"]]
    # Dependency completeness is part of usable coverage, not only a runtime
    # failure. Remove rules whose required entities still lack a reviewed rule.
    changed = True
    while changed:
        changed = False
        for row in entries.values():
            if row["category"] != "general" or row["status"] != "reviewed":
                continue
            rule = row["rule"]
            references = [*rule.get('requires', ()), *[reference for group in rule.get('role_requires', ()) for reference in group]]
            missing = [reference for reference in references if canonical(reference.split(":", 1)[1]) not in general_rules]
            missing.extend(reference + ' (实体归属不匹配)' for reference in references if reference.startswith('object:')
                           and (parent := general_rules.get(canonical(reference.split(':', 1)[1])))
                           and parent['scope'] != 'object' and not parent.get('object_capable'))
            missing.extend('any:' + '|'.join(group) for group in rule.get('any_dependencies', ()) if not any(canonical(reference.split(':', 1)[1]) in general_rules for reference in group))
            missing.extend('slots:' + '|'.join(group) for group in rule.get('required_slots', ()) if not any(candidate['slot'] in group for candidate in general_rules.values()))
            if missing:
                row.update(status="candidate", missing_reason="依赖尚无可用规则：" + ", ".join(missing))
                general_rules.pop(row["canonical"], None)
                changed = True
    for rule in general_rules.values():
        if rule.get('any_dependencies'):
            rule['any_dependencies'] = [[reference for reference in group if canonical(reference.split(':', 1)[1]) in general_rules]
                                        for group in rule['any_dependencies']]
    reference_path = cache / 'character_references.json'
    references = json.loads(reference_path.read_text(encoding='utf-8')) if reference_path.is_file() else {}
    @lru_cache(maxsize=None)
    def implied(name):
        result, pending = set(), [name]
        while pending:
            current = pending.pop()
            for parent in retained_implications.get(current, ()):
                if parent not in result:
                    result.add(parent)
                    pending.append(parent)
        return frozenset(result)
    for row in entries.values():
        if row["category"] != "character":
            continue
        page = wiki["pages"].get(wiki_title(row["canonical"])) or wiki["pages"].get(wiki_title(row["name"]))
        if page and (profile := character_profile(wiki_title(row["canonical"]), page, data["ips"], relevant_aliases, general_rules, retained_implications)):
            characters[wiki_title(row["canonical"])] = profile
            row.update(status="reviewed", review_method=profile["review_method"], missing_reason="")
        elif page:
            profile, reason = reference_profile(wiki_title(row['canonical']), page, references, general_rules, canonical, implied, data['ips'])
            if profile:
                characters[wiki_title(row['canonical'])] = profile
                row.update(status='reviewed', review_method=profile['review_method'], missing_reason='')
            else:
                row['missing_reason'] = '角色身份资料不足：' + reason
    override_path = destination / "character_overrides.json"
    if override_path.is_file():
        overrides = json.loads(override_path.read_text(encoding="utf-8"))
        for name, profile in overrides.items():
            if "character:" + key(name) not in entries:
                raise ValueError("Character override absent from local vocabulary: " + name)
            if any(key(tag) not in REVIEWED for tag in profile["identity"].values()):
                raise ValueError("Character override uses unreviewed identity: " + name)
            characters[name] = profile
            row = entries["character:" + key(name)]
            row.update(status="reviewed", review_method="explicit_project_review", missing_reason="")
            for item in ledger:
                if item["key"] == "character:" + key(name):
                    item.update(status="reviewed", review_method="explicit_project_review", missing_reason="")
    # A sourced profile is usable only if its complete locked appearance passes
    # the same structural rules as a runtime scene. Invalid profiles stay in
    # the gap ledger rather than increasing coverage and failing at generation.
    from app.prompts.semantic_catalog import SemanticCatalog
    from app.prompts.semantic_scene import SceneActor, SceneFact, ScenePlan, validate_scene
    audit = SemanticCatalog(destination, data={'schema_version': 1, 'entries': entries, 'characters': characters,
        'aliases': relevant_aliases, 'implications': retained_implications, 'coverage': {}})
    invalid_profiles = {}
    for name, profile in audit.characters.items():
        facts = tuple(SceneFact(audit.term(tag).key) for _, tag in (*profile.identity, *profile.wardrobe))
        errors = validate_scene(ScenePlan('daily', (SceneActor('A1', profile.gender, profile.age_state, name, facts, profile.kind),)), audit)
        if errors and profile.wardrobe and len(profile.identity) >= 2:
            physical = tuple(SceneFact(audit.term(tag).key) for _, tag in profile.identity)
            if not validate_scene(ScenePlan('daily', (SceneActor('A1', profile.gender, profile.age_state, name, physical, profile.kind),)), audit):
                characters[name]['uncertain_wardrobe'] = characters[name].get('wardrobe', {})
                characters[name]['wardrobe_diagnostics'] = list(errors)
                characters[name]['wardrobe'] = {}
                errors = ()
        if errors:
            invalid_profiles[name] = errors
    for name, errors in invalid_profiles.items():
        characters.pop(name)
        for row in entries.values():
            if row['category'] == 'character' and canonical(row['name']) == canonical(name):
                row.update(status='candidate', missing_reason='角色固定属性未通过结构校验：' + '；'.join(errors))
    # Character rules are evaluated after general rules. Rebuild the ledger so
    # every exported state reflects the final result of both passes.
    ledger = [{field: row.get(field) for field in ("name", "category", "status", "source_available", "source", "source_updated_at", "source_sha256", "review_method", "missing_reason")} | {"key": identity}
              for identity, row in sorted(entries.items())]
    counts = Counter(row["status"] for row in entries.values())
    by_category = {category: dict(Counter(row["status"] for row in entries.values() if row["category"] == category)) for category in ("general", "character")}
    top = sorted((row for row in entries.values() if row["category"] == "general"), key=lambda row: (-row["weight"], row["name"]))[:1000]
    coverage = {"total": len(entries), "statuses": dict(counts), "by_category": by_category,
                "source_available": sum(row["source_available"] for row in entries.values()), "usable_reviewed": counts["reviewed"],
                "minimum_required": 11362, "minimum_met": counts["reviewed"] >= 11362,
                "high_frequency_top_1000": dict(Counter(row["status"] for row in top)), "character_profiles": len(characters),
                "adult_character_profiles": sum(profile["age_state"] == "adult" for profile in characters.values()),
                "character_review_methods": dict(Counter(profile['review_method'] if 'review_method' in profile else 'explicit_project_review' for profile in characters.values())),
                "rejected_character_profiles": len(invalid_profiles),
                "reference_records": len(references.get('posts', {})),
                "aliases": len(relevant_aliases), "implication_edges": sum(map(len, retained_implications.values())),
                "source_files": data["sources"], "review_policy": "Acquired Wiki pages and lexical-only descriptions are not counted as reviewed generation rules."}
    bundle = {"schema_version": 1, "entries": entries, "characters": characters, "aliases": relevant_aliases, "implications": retained_implications, "coverage": coverage}
    write_json(destination / "catalog.json", bundle)
    write_json(destination / "coverage.json", coverage)
    with (destination / "coverage.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=tuple(ledger[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(ledger)
    print(json.dumps(coverage, ensure_ascii=False, indent=2))
    return coverage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "data/prompt-semantics")
    parser.add_argument("--output", type=Path, default=ROOT / "resources/prompt_semantics")
    parser.add_argument("--require-coverage", action="store_true")
    args = parser.parse_args()
    coverage = build(args.cache, args.output)
    return 0 if not args.require_coverage or coverage["minimum_met"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
