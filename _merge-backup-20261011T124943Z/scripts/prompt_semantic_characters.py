"""Validate character appearance evidence from Wiki-selected official records."""
from __future__ import annotations
import hashlib
import json
import re
from app.prompts.normalizer import canonical_tag_key as key
from scripts.prompt_semantic_families import plain

TRAITS = {'hair.color', 'hair.length', 'hair.style', 'hair.texture', 'eyes.color', 'skin.color', 'body.ears', 'body.horns', 'body.wings', 'body.tail', 'body.detail', 'body.halo'}
REJECT = {'alternate costume', 'official alternate costume', 'alternate hairstyle', 'official alternate hairstyle', 'alternate hair color', 'alternate eye color', 'alternate hair length', 'alternate skin color', 'genderswap', 'aged up', 'aged down', 'multiple persona', 'dual persona', 'cosplay', 'character cosplay', 'character parody', 'fusion', 'transformation', 'implied rape', 'loli', 'shota'}
NONAPPEARANCE = {'wet', 'sweat', 'sweatdrop', 'blush', 'makeup', 'lipstick', 'nail polish', 'bandages', 'bandaid', 'scar', 'bruise', 'injury', 'veins', 'nosebleed', 'blood', 'saliva', 'drool', 'nose blush', 'heavy breathing', 'small sweatdrop', 'body blush', 'steam', 'shiny skin', 'oiled skin', 'burn', 'wound'}


def age_evidence(name, body):
    title = re.sub(r'\s*\([^)]*\)', '', name.replace('_', ' ')).strip()
    text = plain(body.replace('\r', '\n'))
    pattern = r"(?i)\b(?:age\s*[:：]\s*|(?:she|he|they|" + re.escape(title) + r")\s+(?:is|are)\s+(?:an?\s+)?)(\d{1,3})(?:\s*years?\s*old|[- ]year[- ]old|(?=\s*(?:\n|$)))"
    matches = list(re.finditer(pattern, text))
    ages = [int(match[1]) for match in matches]
    state = 'adult' if ages and all(age >= 18 for age in ages) else 'minor' if ages and all(age < 18 for age in ages) else 'unknown'
    if state == 'adult' and re.search(r'\b(?:child-like|childlike|prepubescent|preadolescent|young child|toddler)\b', text, re.I):
        state = 'unknown'
    return state, [match[0] for match in matches]


def reference_profile(name, page, records, rules, canonical, implied, ips):
    entry = records.get('references', {}).get(name)
    if not entry:
        return None, 'no_default_appearance_reference'
    valid = []
    rejected = []
    owner = canonical(name)
    ancestors = frozenset(implied(owner))
    for reference in entry['references']:
        post = records.get('assets', {}).get(str(reference['id']), {}).get('post') if reference.get('kind') == 'asset' else records.get('posts', {}).get(str(reference['id']))
        if not post:
            rejected.append('reference_record_unavailable')
            continue
        meta = set(post.get('tag_string_meta', '').split())
        tags = {canonical(tag) for tag in post.get('tag_string_general', '').split()}
        people = {canonical(tag) for tag in post.get('tag_string_character', '').split()}
        if post.get('rating') not in {'g', 's'} or any(post.get(flag) for flag in ('is_deleted', 'is_flagged', 'is_pending')):
            rejected.append('reference_not_available_for_review')
            continue
        if 'official_art' not in meta:
            rejected.append('reference_not_official_art')
            continue
        if owner not in people or people - {owner} - ancestors:
            rejected.append('reference_character_ownership_ambiguous')
            continue
        if tags & REJECT or any(re.search(r'\b(?:alternate|cosplay|genderswap|aged up|aged down)\b', tag) for tag in tags):
            rejected.append('reference_contains_variant_or_transformation')
            continue
        counts = [tag for tag in tags if re.fullmatch(r'\d+(?:girls?|boys?|others?)', tag)]
        if any(not tag.startswith('1') or tag.startswith('10') for tag in counts) or len(counts) > 1:
            rejected.append('reference_contains_multiple_people')
            continue
        gender = 'female' if '1girl' in tags else 'male' if '1boy' in tags else 'unknown'
        creature = 'no humans' in tags
        values = {}
        for tag in sorted(tags):
            rule = rules.get(tag)
            if rule and rule['slot'] in TRAITS and not rule.get('adult') and not rule.get('requires') and not rule.get('required_slots') and not rule.get('conditions') and tag not in NONAPPEARANCE:
                values.setdefault(rule['slot'], set()).add(tag)
        # Preserve the most specific sourced facts, rather than contradictory
        # synonyms or an ancestor and a child both occupying a single slot.
        for slot, choices in values.items():
            parents = {parent for tag in choices for parent in implied(tag)}
            choices.difference_update(parents)
        for broad, specific in (('long hair', 'very long hair'), ('long hair', 'absurdly long hair'), ('very long hair', 'absurdly long hair')):
            if broad in values.get('hair.length', ()) and specific in values['hair.length']:
                values['hair.length'].discard(broad)
        valid.append((gender, creature, values, reference, post))
    if not valid:
        return None, ';'.join(sorted(set(rejected))) or 'no_usable_reference'
    genders = {item[0] for item in valid}
    forms = {item[1] for item in valid}
    if len(genders) != 1 or len(forms) != 1:
        return None, 'reference_gender_or_form_disagreement'
    from app.prompts.semantic_rules import SINGLE_SLOTS
    stable, uncertain = {}, {}
    for slot in sorted({slot for _, _, values, _, _ in valid for slot in values}):
        # Missing attributes remain unknown. Multiple official default records
        # must agree on an attribute before it is locked.
        sets = [values.get(slot, set()) for _, _, values, _, _ in valid]
        if any(not values for values in sets) or any(values != sets[0] for values in sets[1:]):
            uncertain[slot] = sorted(set().union(*sets))
            continue
        choices = sets[0]
        multicolor = slot in {'hair.color', 'eyes.color'} and any(rules[tag].get('provides') for tag in choices)
        if slot in SINGLE_SLOTS and len(choices) > 1 and not multicolor:
            uncertain[slot] = sorted(choices)
        elif choices:
            stable[slot] = sorted(choices) if len(choices) > 1 else next(iter(choices))
    if len(stable) < 2 or not {'hair.color', 'eyes.color'} & stable.keys() and len(stable) < 3:
        return None, 'reference_insufficient_stable_traits'
    age_state, ages = age_evidence(name, page['body'])
    evidence = []
    for _, _, _, reference, post in valid:
        evidence.append({'post_id': post['id'], 'wiki_line': reference['wiki_line'], 'official_art': True,
            'characters': post['tag_string_character'], 'post_updated_at': post.get('updated_at'),
            'post_source': post.get('source', ''), 'source': 'https://danbooru.donmai.us/posts/' + str(post['id']),
            'record_sha256': hashlib.sha256(json.dumps(post, sort_keys=True).encode()).hexdigest()})
    return {'gender': next(iter(genders)), 'kind': 'creature' if next(iter(forms)) else 'humanoid',
        'identity': {slot: [tag.replace(' ', '_') for tag in value] if isinstance(value, list) else value.replace(' ', '_') for slot, value in stable.items()},
        'copyrights': ips.get(name, []), 'age_state': age_state, 'age_evidence': ages, 'variants': [],
        'uncertain_slots': uncertain, 'appearance_evidence': evidence,
        'sources': ['https://danbooru.donmai.us/wiki_pages/' + name, *[value['source'] for value in evidence]],
        'review_method': 'wiki_selected_official_reference_v1'}, ''
