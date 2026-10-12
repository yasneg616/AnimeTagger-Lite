"""Resolve gesture grammar into owned props and ordered participants."""
from __future__ import annotations

import re

from app.prompts.normalizer import canonical_tag_key as key
from app.prompts.semantic_rules import primitive
from scripts.prompt_semantic_families import ADULT, UNRESOLVED, definition, plain


# Only positively identified portable things may satisfy a generic hold. A
# concrete place/furniture/vehicle noun is never made portable by its tag group.
HANDHELD_HEADS = frozenset('tool|utensil|weapon|gun|firearm|pistol|handgun|rifle|shotgun|revolver|sword|blade|knife|dagger|katana|rapier|sabre|saber|spear|lance|halberd|scythe|trident|mace|axe|hammer|bat|baseball bat|bow|crossbow|arrow|arrows|shield|staff|wand|book|notebook|magazine|newspaper|map|scroll|paper|card|letter|envelope|ticket|wallet|purse|bag|backpack|pouch|handbag|briefcase|basket|bucket|bowl|plate|cup|mug|glass|goblet|teacup|teapot|kettle|spoon|fork|chopsticks|tray|thermos|pan|frying pan|toy|doll|puppet|plushie|stuffed toy|stuffed animal|teddy bear|ball|racket|racquet|guitar|violin|flute|trumpet|harmonica|recorder|camera|phone|smartphone|cellphone|tablet|game controller|microphone|remote control|flashlight|lantern|candle|torch|pen|pencil|eraser|marker|crayon|chalk|paintbrush|brush|hairbrush|comb|hair brush|hair dryer|toothbrush|scissors|needle|ruler|handkerchief|mirror|umbrella|parasol|hand fan|flag|bouquet|flower|feather|gem|crystal|stone|shell|ofuda|orb|potion|flask|jar|vial|syringe|test tube|cane|walking stick|cigarette|cigar|lighter|pillow|cushion|blanket|towel|balloon|food|snack|candy|fruit|vegetable|pastry|cake|cookie|biscuit|chocolate|bread|sandwich|burger|pizza|onigiri|bento|lollipop|ice cream|popsicle|drink|beverage|coffee|tea|juice|milk|soda|beer|wine|bottle|can|carton'.split('|'))
HANDHELD_NAMES = frozenset('hand fan|folding fan|closed fan|pointer|pendulum|party popper|pregnancy test|riding crop|scepter|sketchbook|skewer|stethoscope|string|table tennis paddle|juice box|water gun|fishing rod|fishing pole|drumsticks|musical bow|mop|broom|notepad|crowbar|paddle|mahjong tile|cloth|lead pipe|hair iron|curling iron|paint tube|cleaning rag'.split('|'))
HANDHELD_NAMES |= frozenset('barcode scanner|beachball|binoculars|bone|butterfly net|candy apple|cat|chainsaw|chess piece|clipboard|club|coin|condom|controller|cooking pot|crepe|cross|dog|drawing (object)|drink carton|dumbbell|duster|egg|fish|flower pot|glowstick|gohei|gourd|grenade|halloween bucket|handcuffs|hose|ladle|leash|lipstick tube|magnifying glass|mallet|maracas|menu|microphone stand|money|paint palette|paper airplane|petal|photograph (object)|plant|pocket watch|pocky|poke ball|pole|polearm|rabbit|reins|sex toy|sheath|shower head|sign|skull|smoking pipe|spatula|sponge|spring onion|stick|stylus|surfboard|swim ring|ticket|whip|nunchaku|handheld electric fan|fan (object)|folding fan|closed umbrella|brush|vegetable'.split('|'))
# Objects whose own holding tag states a hand gesture: a musical instrument, a
# kitchen utensil and a spun-sugar treat are all carried in the hand. Living
# creatures ("animal", "bird", "creature") are deliberately not made portable.
HANDHELD_NAMES |= frozenset('bass guitar|instrument|whistle|whisk|cotton candy|bow (music)|fireworks|paddle|table tennis paddle|toothbrush|crowbar|drumsticks|lighter|mop|notepad'.split('|'))


def hand_holdable(name, rule):
    normalized = key(name)
    return bool(rule.get('object_capable') or rule.get('head') in HANDHELD_HEADS
                or normalized in HANDHELD_HEADS or normalized in HANDHELD_NAMES)


def dependent_rule(name, page, lookup):
    normalized = key(name)
    raw = definition(page.get("body", ""))
    text = plain(raw)
    if not text or UNRESOLVED.search(text) or UNRESOLVED.search(normalized):
        return None, None
    rule = None
    if match := re.fullmatch(r'(holding|grabbing|pulling|stroking|touching|biting|licking) own (.+)', normalized):
        verb, part = match.groups()
        parent = lookup(part)
        if parent and parent['scope'] == 'actor' and parent.get('object_capable'):
            rule = primitive(name, 'action', phrase=verb + ' their own ' + part, requires=(parent['slot'] + ':' + part,), adult=parent.get('adult', False))
        elif part in {'hair', 'head', 'face', 'cheek', 'chin', 'neck', 'shoulder', 'arm', 'arms', 'hand', 'hands', 'finger', 'fingers', 'wrist', 'chest', 'back', 'waist', 'hip', 'stomach', 'thigh', 'knee', 'leg', 'legs', 'foot', 'feet', 'breast', 'breasts', 'ass', 'penis', 'pussy', 'tail', 'ears', 'ear', 'horn', 'horns'}:
            rule = primitive(name, 'action', phrase=verb + ' their own ' + part, adult=bool(ADULT.search(part) or part in {'breast', 'breasts', 'ass'}))
            if part == 'hair':
                rule['excludes'] = ['hair.length:bald']
            if part in {'tail', 'horn', 'horns'}:
                target = 'tail' if part == 'tail' else 'horns'
                if lookup(target):
                    rule['requires'] = ['body:' + target]
                else:
                    rule = None
    match = re.fullmatch(r"(holding|carrying|hugging|biting|mouth holding|mouth hold) (?:unworn |removed )?(.+?)(?: (behind back|over shoulder|above head))?", normalized) if rule is None else None
    if match:
        verb, prop, where = match.groups()
        parent = lookup(prop)
        if not parent:
            # Resolve an explicitly linked disambiguated noun, e.g. "arrow
            # (projectile)" or "photograph (object)", without a lexical guess.
            matches = {key(label.split('|', 1)[0]) for label in re.findall(r'\[\[([^\]]+)\]\]', raw)
                       if key(label.split('|', 1)[0]).split(' (', 1)[0] == prop and lookup(key(label.split('|', 1)[0]))}
            if len(matches) == 1:
                prop = next(iter(matches))
                parent = lookup(prop)
        if prop == 'fan' and not parent and lookup('hand fan'):
            prop, parent = 'hand fan', lookup('hand fan')
        if parent and hand_holdable(prop, parent) and re.search(r"\b(?:hold\w*|carry\w*|carrie\w*|hug\w*|bit\w*|mouth)\b", text[:500], re.I):
            label = prop
            article = "" if label.endswith(("s", "wear")) or label in {"food", "drink", "water", "hair", "paper", "rice", "coffee", "tea", "milk", "juice", "fruit"} else "an " if label[:1] in "aeiou" else "a "
            phrase = ("holding " if verb in {"mouth holding", "mouth hold"} else verb + " ") + article + label
            if verb in {"mouth holding", "mouth hold"}:
                phrase += " in the mouth"
            if where:
                phrase += ' ' + where
            rule = primitive(name, "action", phrase=phrase, requires=("object:" + prop,), adult=parent.get("adult", False))
    if rule is None and (match := re.fullmatch(r"(.+?) (?:in|between) (?:the )?(mouth|teeth)", normalized)):
        prop, where = match.groups()
        parent = lookup(prop)
        if parent and (parent["scope"] == "object" or parent.get("object_capable")) and re.search(r"\b(?:mouth|teeth)\b", text[:400], re.I):
            rule = primitive(name, "placement", phrase=f"{prop} positioned {'in the mouth' if where == 'mouth' else 'between the teeth'}", requires=("object:" + prop,), adult=parent.get("adult", False))
    if rule is None and (match := re.fullmatch(r"(.+?) on (?:the )?(head|shoulder|back|lap|arm|hand|finger|foot|leg|nose)", normalized)):
        prop, part = match.groups()
        parent = lookup(prop)
        if parent and (parent["scope"] == "object" or parent.get("object_capable")) and re.search(r"\b" + re.escape(part) + r"\b", text[:400], re.I):
            rule = primitive(name, "placement", phrase=f"{prop} positioned on their {part}", requires=("object:" + prop,), adult=parent.get("adult", False))
    if rule is None and (match := re.fullmatch(r"(.+?) (lift|pull|grab|hold|aside|removed|partially removed)", normalized)):
        garment, operation = match.groups()
        garment = {'panty': 'panties', 'thighhigh': 'thighhighs', 'glove': 'gloves', 'sock': 'socks', 'boot': 'boots', 'shoe': 'shoes', 'sleeve': 'detached sleeves'}.get(garment, garment)
        parent = lookup(garment)
        if parent and parent["scope"] == "actor" and parent.get("object_capable") and re.search(r"\b(?:lift\w*|pull\w*|grab\w*|hold\w*|remov\w*|aside)\b", text[:400], re.I):
            exposed = parent.get('adult', False) or garment in {'shirt', 'dress', 'skirt', 'pants', 'shorts'}
            if operation == 'removed':
                rule = primitive(name, 'placement', phrase='with ' + garment + ' removed and unworn', requires=('object:' + garment,), adult=exposed,
                                 excludes=(parent['slot'] + ':' + garment,))
            else:
                words = {'lift': 'lifted', 'pull': 'pulled down', 'grab': 'grasped', 'hold': 'held', 'aside': 'moved aside', 'partially removed': 'partially removed'}
                rule = primitive(name, 'clothing.exposure', phrase='with their ' + garment + ' ' + words[operation],
                                 requires=(parent['slot'] + ':' + garment,), adult=exposed)
    if rule is None and (match := re.fullmatch(r"(?:hand|hands) (on|in) own (.+)", normalized)):
        prep, part = match.groups()
        if part in {"head", "face", "cheek", "chin", "neck", "shoulder", "arm", "wrist", "chest", "back", "waist", "hip", "stomach", "thigh", "knee", "leg", "foot", "hair", "breast", "breasts", "ass", "buttocks", "penis", "pussy"}:
            rule = primitive(name, "hands.pose", phrase=f"resting {'both hands' if normalized.startswith('hands') else 'a hand'} {prep} their own {part}", adult=bool(ADULT.search(part) or part in {"breast", "breasts", "ass", "buttocks"}))
    if rule is None and (match := re.fullmatch(r"(holding|grabbing|biting|licking|pulling|stroking|touching) another's (.+)", normalized)):
        verb, part = match.groups()
        if part in {"head", "face", "cheek", "chin", "neck", "shoulder", "arm", "wrist", "hand", "chest", "back", "waist", "hip", "stomach", "thigh", "knee", "leg", "foot", "hair", "breast", "breasts", "ass", "buttocks", "penis", "pussy", "tail", "ears", "ear", "horn", "horns"}:
            finite = {"holding": "holds", "grabbing": "grasps", "biting": "bites", "licking": "licks", "pulling": "pulls", "stroking": "strokes", "touching": "touches"}[verb]
            rule = primitive(name, "interaction", actors=2, adult=bool(ADULT.search(part) or part in {"breast", "breasts", "ass", "buttocks"}))
            rule["role_phrase"] = "{0} " + finite + " {1}'s " + part
            if part in {'tail', 'horn', 'horns', 'wings'}:
                target = {'horn': 'horns'}.get(part, part)
                if not lookup(target):
                    return None, None
                rule['role_requires'] = [[], ['body:' + target]]
    if rule:
        rule["adult"] = rule["adult"] or bool(ADULT.search(normalized))
        return rule, {"family": "resolved_action_dependencies", "definition": text[:600], "passage": raw[:900]}
    return None, None


COLORS = frozenset("aqua black blue brown green grey orange pink purple red white yellow blonde silver gold golden beige cream tan cyan teal magenta maroon navy violet lavender indigo turquoise platinum".split())
WEAR_SLOTS = {"outfit", "top", "bottom", "outerwear", "footwear", "legwear", "handwear", "headwear", "accessory", "underwear", "underwear.top", "underwear.bottom"}


def enrich_rule(name, rule):
    result = {**rule}
    normalized = key(name)
    if normalized == 'deer':
        result.update(slot='object', scope='object', head='deer')
    if normalized == 'pompadour':
        result.update(slot='hair.style', scope='actor', head='hairstyle')
        result['excludes'] = list(dict.fromkeys([*result.get('excludes', ()), 'hair.length:bald']))
    if normalized == 'arms up':
        result['excludes'] = list(dict.fromkeys([*result.get('excludes', ()),
            'hands.pose:hand_in_pocket', 'hands.pose:hands_in_pockets', 'hands.pose:arms_on_table']))
    if normalized == 'pole':
        result.update(slot='object', scope='object', head='pole')
    if normalized in {'recording', 'lamppost'}:
        result.update(slot='scene.detail' if normalized == 'lamppost' else 'style', scope='scene')
    if normalized in {'ofuda', 'mahjong tile', 'torch'}:
        result.update(slot='object', scope='object', head=normalized)
    if normalized in {'cross', 'plant', 'petals', 'leaf', 'leaves', 'flower', 'flowers', 'rock', 'stone', 'branch'}:
        result['object_capable'] = True
    if normalized == 'playboy bunny':
        result['phrase'] = 'a Playboy bunny uniform'
        result['adult'] = True
    if normalized == 'waraji':
        result['phrase'] = 'straw-rope sandals'
    if normalized == 'holding':
        result['phrase'] = 'holding an object'
    if normalized in {'standing on one leg', 'tiptoes', 'wading'}:
        result['requires'] = list(dict.fromkeys([*result.get('requires', ()), 'posture:standing']))
    if normalized == 'legs over head':
        result['any_dependencies'] = [['posture:lying', 'posture:on_back', 'posture:headstand']]
    if normalized == 'blinking':
        result['features'] = {**result.get('features', {}), 'eyes.state': 'closed'}
    if normalized in {'reverse bunnysuit', 'reverse bikini'}:
        result['adult'] = True
    if normalized == 'kindergarten uniform':
        result['conditions'] = list(dict.fromkeys([*result.get('conditions', ()), 'ordinary_only']))
    if result['slot'] in {'outfit', 'top', 'bottom', 'underwear', 'underwear.top', 'underwear.bottom'} and re.search(r'\b(?:translucent|transparent|see-through|impossible|crotchless|breastless)\b', normalized):
        result['adult'] = True
    if normalized == 'single off shoulder':
        result.update(slot='clothing.exposure', scope='actor', phrase='one shoulder exposed by clothing hanging off one arm')
    apparel = ('outfit', 'top', 'bottom', 'outerwear', 'headwear', 'legwear', 'footwear', 'handwear', 'underwear', 'underwear.top', 'underwear.bottom')
    # A "missing halo" absence is about the body, so it must not inherit the
    # worn-garment prerequisite that other clothing details carry.
    absent = any(key_name.startswith('absent.') for key_name in result.get('features', ()))
    explicit_garment = any(reference.split(':', 1)[0] in apparel for reference in result.get('requires', ()))
    explicit_garment = explicit_garment or any(group and all(reference.split(':', 1)[0] in apparel for reference in group)
                                            for group in result.get('any_dependencies', ()))
    if result['slot'].startswith('clothing.') and not normalized.startswith(('detached ', 'no ')) and not absent and not explicit_garment:
        upper = result['slot'] in {'clothing.sleeves', 'clothing.collar'} or normalized in {'off shoulder', 'single off shoulder', 'collarbone cutout', 'chest cutout', 'back cutout'}
        result.setdefault('required_slots', [list(('top', 'outfit', 'outerwear') if upper else apparel)])
    for kind, words in (('headwear', {'hat', 'headwear'}), ('footwear', {'shoe', 'shoes', 'footwear', 'boot', 'boots'})):
        if result['scope'] == 'actor' and result['slot'] in {'headwear', 'footwear', 'accessory', 'clothing.trim', 'clothing.detail'} and normalized.split()[0] in words and normalized.split()[-1] in {'bow', 'ribbon', 'belt', 'ornament', 'flower', 'jewel', 'buckle', 'lace', 'laces', 'wings'}:
            result.update(slot='clothing.trim', object_capable=False)
            result['required_slots'] = [[kind]]
    if result['slot'] == 'accessory' and normalized.startswith('hair '):
        result['excludes'] = list(dict.fromkeys([*result.get('excludes', ()), 'hair.length:bald']))
    if result['slot'] in {'body.detail', 'body.shape'} and (anatomy := re.search(r'\b(ears?|horns?|wings?|tails?)$', normalized)):
        part = anatomy[1]
        part = {'ear': 'ears', 'horn': 'horns', 'wing': 'wings', 'tails': 'tail'}.get(part, part)
        result['slot'] = 'body.' + part
    if normalized in {'child', 'baby', 'toddler', 'young girl', 'young boy'}:
        result['conditions'] = list(dict.fromkeys([*result.get('conditions', ()), 'age:minor', 'ordinary_only']))
    if normalized.endswith((' female', ' male')) and result['scope'] == 'actor':
        result['conditions'] = list(dict.fromkeys([*result.get('conditions', ()), 'gender:' + normalized.rsplit(' ', 1)[1]]))
    if normalized == 'layered clothes':
        result['provides'] = list(dict.fromkeys([*result.get('provides', ()), 'layered_outfit', 'layered_sleeves']))
    if normalized in {'pinafore dress', 'jumper dress', 'dirndl'}:
        result['provides'] = list(dict.fromkeys([*result.get('provides', ()), 'inner_top_layer']))
    if normalized == 'asymmetrical wings':
        result['provides'] = list(dict.fromkeys([*result.get('provides', ()), 'multicolor:body.wings']))
    if result["slot"] in WEAR_SLOTS:
        result["object_capable"] = True
    features = dict(result.get("features", {}))
    words = normalized.split()
    color = words[0] if words and words[0] in COLORS else None
    if len(words) >= 3 and words[0] in {"light", "dark"} and words[1] in COLORS:
        color = words[0] + " " + words[1]
    context = None
    if result["slot"] in {"hair.color", "eyes.color", "skin.color"}:
        context = result["slot"].split(".")[0]
    elif result["scope"] == "actor" and re.search(r"\b(?:tail|horns|wings|ears|halo|nails|pupils|sclera)\b$", normalized):
        context = "body." + words[-1]
    elif result["slot"] == "background":
        context = "background"
    elif result["slot"] == "accessory":
        context = "accessory." + (result.get("head") or " ".join(words[1:] if color else words))
    if context and color:
        features[context + ".color"] = color
    if context and any(word in {"multicolored", "two-tone", "gradient", "rainbow", "split-color"} for word in words):
        result["provides"] = list(dict.fromkeys([*result.get("provides", ()), "multicolor:" + context]))
    if result["slot"] == "hair.color":
        features["hair.present"] = "yes"
    if result['slot'] == 'eyes.color':
        features['body.eyes.present'] = 'yes'
    for noun, slot in (('ears', 'body.ears'), ('wings', 'body.wings'), ('tail', 'body.tail'), ('horns', 'body.horns')):
        if result['slot'] == slot and not normalized.startswith('no '):
            features['body.' + noun + '.present'] = 'yes'
    if result['slot'] == 'eyes.detail':
        for noun in ('pupils', 'sclera'):
            if noun in words and not normalized.startswith('no '):
                features['body.' + noun + '.present'] = 'yes'
    if normalized == "bald":
        features["hair.present"] = "no"
    if normalized in {"no eyes", "no pupils", "no sclera", "no mouth", "no ears", "no tail", "no horns", "no wings"}:
        features["body." + normalized[3:] + ".present"] = "no"
    if normalized in {"closed eyes", "sleeping"}:
        features["eyes.state"] = "closed"
    if result["slot"] == "gaze":
        # A sourced head-facing rule can explicitly choose the closed-eye
        # subcase. Actual looking/contact rules still require open eyes.
        features.setdefault("eyes.state", "open")
    if normalized in {"eye contact", "looking at another"}:
        features["eyes.state"] = "open"
    if normalized == "dual wielding":
        result["object_counts"] = {"weapon": 2}
    if normalized in {"chibi", "super deformed", "deformed", "child's drawing"}:
        result["conditions"] = ["ordinary_only"]
    if normalized in {"male focus", "female focus"}:
        result["conditions"] = [normalized.split()[0] + ":1"]
    if normalized == "solo focus":
        result["min_actors"] = 2
    if normalized in {"small breasts", "medium breasts", "large breasts", "huge breasts", "gigantic breasts", "flat chest"}:
        result["adult"] = True
    # Upper-body layers, rather than colors of unrelated skirts/shoes, establish
    # the context of sleeve-length constraints.
    if result["slot"] in {"top", "outfit", "outerwear"}:
        target = "clothing.sleeves.length" if result["slot"] != "outerwear" else "clothing.outer_sleeves.length"
        for modifier, value in (("long-sleeved", "long"), ("short-sleeved", "short"), ("sleeveless", "none")):
            if modifier in words:
                features[target] = value
    if normalized in {"nude", "completely nude"}:
        result["excludes"] = list(dict.fromkeys([*result.get("excludes", ()), *["slot:" + slot for slot in ("underwear", "underwear.top", "underwear.bottom")]]))
    if normalized == "topless":
        result["excludes"] = list(dict.fromkeys([*result.get("excludes", ()), "slot:underwear", "slot:underwear.top"]))
    if normalized == "bottomless":
        result["excludes"] = list(dict.fromkeys([*result.get("excludes", ()), "slot:underwear", "slot:underwear.bottom"]))
    if features:
        result["features"] = features
    return result
