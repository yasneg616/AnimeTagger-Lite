"""Attribute constructions with evidence, ownership and prerequisite slots.

These adapters describe a property of an existing subject or garment. The
positive Wiki introduction and the tag construction must agree. Related-tag
lists and broad taxonomy groups are not sufficient evidence.
"""
from __future__ import annotations

import re
from app.prompts.normalizer import canonical_tag_key as key
from app.prompts.semantic_rules import primitive
from scripts.prompt_semantic_families import ADULT, UNRESOLVED, definition, plain, _defining_phrase

APPAREL = ('outfit', 'top', 'bottom', 'outerwear', 'headwear', 'legwear', 'footwear', 'handwear', 'accessory', 'underwear', 'underwear.top', 'underwear.bottom')
PARTS = r"head|forehead|face|cheek|cheeks|chin|neck|nape|shoulder|shoulders|arm|arms|armpit|armpits|elbow|hand|hands|finger|fingers|wrist|chest|back|waist|hip|hips|stomach|navel|thigh|thighs|knee|knees|leg|legs|foot|feet|ankle|ankles|hair|breast|breasts|ass|buttocks|penis|pussy|anus|crotch|groin|testicles|ear|ears|nose|mouth|lips"
COLORS = r"(?:light |dark )?(?:aqua|black|blue|brown|green|grey|gray|orange|pink|purple|red|white|yellow|blonde|silver|gold|golden|beige|cream|tan|cyan|teal|magenta|maroon|navy|violet|lavender|indigo|turquoise)|multicolored|two-tone|gradient|rainbow|split-color"
GENDERS = {'girl': 'female', 'boy': 'male', 'female': 'female', 'male': 'male', 'woman': 'female', 'man': 'male'}
SPECIES = set('cat dog fox wolf rabbit horse unicorn pegasus bear panda tiger lion cow goat sheep deer mouse rat raccoon tanuki squirrel otter bat bird crow raven owl eagle hawk duck chicken penguin crane swan parrot shark fish dolphin whale snake lizard crocodile turtle frog dragon wyvern demon devil angel fairy elf dwarf goblin orc ogre oni tengu vampire zombie ghost witch spider bee butterfly moth insect scorpion ant mantis centipede slime robot android cyborg mermaid merman merfolk minotaur centaur arachne lamia sphinx harpy kitsune nekomata inugami kappa monster'.split())
UNWORN_NOUNS = set('backpack|bag|bikini|bikini bottom|bikini top|boots|bowtie|bra|cape|clothes|coat|crown|dress|eyepatch|eyewear|footwear|gloves|goggles|hair ornament|hairband|hat|headphones|headwear|jacket|jewelry|mask|necklace|necktie|panties|pants|sandals|scarf|shirt|shoes|shorts|skirt|slippers|socks|swimsuit|thighhighs'.split('|'))


def attribute_rule(name, page):
    raw = definition(page.get('body', ''))
    text = plain(raw)
    normalized = key(name)
    # Some older model CSVs retain deprecated broad color/garment tags. Their
    # meaning can still be established from the Wiki's explicit replacements;
    # ambiguous words and unsupported deprecated concepts are never accepted.
    if text and re.match(r'(?i)^deprecated|^this tag has been deprecated', text) and (legacy := re.fullmatch(r'(' + COLORS + r') (footwear|headwear|legwear|eyewear)', normalized)):
        color, kind = legacy.groups()
        replacements = [key(label.split('|', 1)[0]) for label in re.findall(r'\[\[([^\]]+)\]\]', page.get('body', ''))]
        if len({tag for tag in replacements if tag.startswith(color + ' ')}) >= 2 or re.search(re.escape(color) + r' (?:hat|hairband|boots|shoes|socks|pantyhose|glasses)', text, re.I):
            slot = 'accessory' if kind == 'eyewear' else kind
            rule = primitive(name, slot)
            rule['head'] = kind
            rule['features'] = {'garment.' + kind + '.color': color}
            return rule, {'family': 'legacy_color_garment_replacements', 'definition': text[:600], 'passage': raw[:900], 'replacement_tags': replacements[:20]}
    if not text or UNRESOLVED.search(text) or UNRESOLVED.search(normalized):
        return None, None
    first = re.split(r'\n|\.(?:\s|$)', text, maxsplit=1)[0]
    if normalized.startswith('unworn ') and (noun := normalized.removeprefix('unworn ')) in UNWORN_NOUNS:
        # A visible garment that is not worn is a prop. It cannot occupy a
        # worn layer, satisfy dressing prerequisites or lock a costume.
        sentence_text = re.sub(r'\([^)]*\)', lambda match: match[0].replace('.', ''), text)
        first = re.split(r'\n|\.(?:\s|$)', sentence_text, maxsplit=1)[0]
        positive = re.search(r"\b(?:not (?:being )?worn|not worn|aren't being worn|isn't being worn|nobody is wearing|unworn|removed from the body)\b", first, re.I)
        target = r'(?:clothes|clothing)' if noun == 'clothes' else re.escape(noun)
        literal = re.match(r'(?i)^(?:when\s+)?(?:(?:an?|the|any|some)(?:\s+(?:piece|pair|article|type))?(?:\s+of)?\s+)?(?:unworn\s+)?' + target + r'\b', first)
        if positive and literal and not re.search(r'\b(?:normally|usually|canonically)\b', first, re.I):
            rule = primitive(name, 'object', adult=bool(ADULT.search(first) or ADULT.search(normalized)))
            return rule, {'family': 'defined_unworn_garment_prop', 'definition': text[:600], 'passage': raw[:900], 'construction': first[:300]}
        return None, None
    rule = None
    family = ''
    # Stable marks have a body location, not an action or a separate held prop.
    if match := re.fullmatch(r'(mole|tattoo|scar|bandage|bandaid|bandaids|mark|piercing|jewelry|paint|cream|sweat|blood|cum) (?:on|around|from) (' + PARTS + r')', normalized):
        mark, part = match.groups()
        if re.search(r'\b' + re.escape(mark) + r'\b', first, re.I) and re.search(r'\b' + re.escape(part) + r'\b', first, re.I):
            rule = primitive(name, 'body.detail', phrase=normalized,
                adult=mark == 'cum' or bool(ADULT.search(part)) or part in {'breast', 'breasts', 'ass', 'buttocks', 'crotch', 'groin'})
            family = 'located_body_mark'
    # Sleeve colors are explicitly a property of the sleeves (and may differ
    # from the shirt). Other colored components get their own context too.
    components = {'sleeves': ('clothing.sleeves', 'sleeves', ('top', 'outfit', 'outerwear')),
        'trim': ('clothing.trim', 'trim', APPAREL), 'straps': ('clothing.detail', 'straps', APPAREL),
        'eyeshadow': ('face.detail', 'eyeshadow', ()), 'eyelashes': ('eyes.detail', 'eyelashes', ()),
        'eyebrows': ('eyes.detail', 'eyebrows', ()), 'pupils': ('eyes.detail', 'pupils', ()),
        'sclera': ('eyes.detail', 'sclera', ()), 'nails': ('body.nails', 'nails', ()),
        'lips': ('face.detail', 'lips', ()), 'lipstick': ('face.detail', 'lipstick', ())}
    if rule is None and (match := re.fullmatch(r'(' + COLORS + r') (sleeves|trim|straps|eyeshadow|eyelashes|eyebrows|pupils|sclera|nails|lips|lipstick)', normalized)):
        color, part = match.groups()
        if re.search(r'\b' + re.escape(part) + r'\b', first, re.I) and re.search(r'\b(?:colou?r|black|white|red|blue|green|pink|purple|brown|yellow|gold|silver|aqua|orange|two|multi|gradient)', first, re.I):
            slot, context, slots = components[part]
            rule = primitive(name, slot)
            if color in {'multicolored', 'two-tone', 'gradient', 'rainbow', 'split-color'}:
                rule['provides'] = ['multicolor:component.' + context]
            else:
                rule['features'] = {'component.' + context + '.color': color.replace('gray', 'grey')}
            if slots:
                rule['required_slots'] = [list(slots)]
            family = 'component_color'
    # Prints and garment construction/condition definitions are different from
    # selecting a complete second outfit. Their appearance requires clothing.
    clothing_subject = re.match(r'(?i)^(?:(?:an?|the|any|one|two|multiple|several)\s+)?(?:(?:[\w-]+)[, ]+){0,6}(?:clothing|clothes|sleeves|shirt sleeves|fabric|garment|garments)\b', first)
    clothing_name = re.search(r'\b(?:clothes|clothing|print|trim|cutout|cutouts|straps|sleeves|fabric)\b', normalized)
    if rule is None and clothing_subject and clothing_name and not re.search(r'\b(?:lift|pull|grab|hold|aside|removed|removing|undressing|dressing|borrowed|alternate|cosplay)\b', normalized):
        historical = bool(re.search(r'\b(?:clothes|clothing)\b$', normalized) and re.search(r'\b(?:people|traditional|era|period|century|culture|nation|region|ancient|worn by)\b', text[:400], re.I))
        slot = 'outfit' if historical else 'clothing.pattern' if normalized.endswith('print') else 'clothing.sleeves' if 'sleeves' in normalized else 'clothing.trim' if 'trim' in normalized else 'clothing.detail'
        rule = primitive(name, slot, adult=bool(ADULT.search(first) or ADULT.search(normalized)))
        if slot != 'outfit':
            rule['required_slots'] = [list(APPAREL if slot != 'clothing.sleeves' else ('top', 'outfit', 'outerwear'))]
        if match := re.fullmatch(r'(' + COLORS + r') (?:clothes|clothing)', normalized):
            color = match[1]
            if color in {'multicolored', 'two-tone', 'gradient', 'rainbow', 'split-color'}:
                rule['provides'] = ['multicolor:clothing']
            else:
                rule['features'] = {'clothing.color': color}
        if normalized in {'baggy clothes', 'tight clothes', 'skin tight', 'skin-tight clothes'}:
            rule['features'] = {'clothing.fit': normalized}
        if normalized in {'uneven sleeves', 'mismatched sleeves'}:
            rule['provides'] = ['layered_sleeves', 'multicolor:component.sleeves']
        family = 'defined_garment_property'
    # A personification is an actor, not a prop. Only explicit humanoid species
    # definitions qualify; decorative costumes do not establish real anatomy.
    if rule is None and (match := re.fullmatch(r'([\w\'-]+) (girl|boy)', normalized)) and match[1] in SPECIES:
        species, gender = match.groups()
        if re.match(r'(?i)^(?:an?\s+)?(?:human\s+|female\s+|male\s+|monster\s+)?(?:girl|boy|woman|man|character|person|humanoid)\b', first) and re.search(r'\b' + re.escape(species) + r'(?:-like)?\b', first, re.I):
            rule = primitive(name, 'body.species', phrase='humanoid ' + species + ' traits')
            rule['conditions'] = ['gender:' + GENDERS[gender], 'original_only']
            rule['features'] = {'body.species': species}
            family = 'defined_humanoid_species'
    if rule is None and normalized in SPECIES and re.search(r'(?i)^(?:an?\s+)?(?:humanoid|human-like|fantasy|mythological|fictional|supernatural|undead|female|male|people|woman|man|race|species)\b', first):
        if re.search(r'\b(?:humanoid|human|people|woman|man|race|person|character)\b', first, re.I):
            rule = primitive(name, 'body.species')
            rule['conditions'] = ['original_only']
            rule['features'] = {'body.species': normalized}
            if normalized in {'mermaid', 'merman', 'merfolk', 'centaur', 'lamia', 'arachne'}:
                rule['excludes'] = ['slot:footwear', 'slot:legwear', 'posture:standing', 'action:walking', 'action:running']
            family = 'defined_humanoid_species'
    # The visual pose/shape/property is the definition subject itself.
    if rule is None:
        targets = [('hair', 'hair.detail'), ('bangs', 'hair.bangs'), ('sidelocks', 'hair.sidelocks'),
            ('sideburns', 'body.detail'), ('eyebrows', 'eyes.detail'), ('eyelashes', 'eyes.detail'),
            ('eyes', 'eyes.detail'), ('pupils', 'eyes.detail'), ('sclera', 'eyes.detail'),
            ('lips', 'face.detail'), ('tongue', 'face.detail'), ('teeth', 'face.detail'),
            ('skin', 'body.detail'), ('body', 'body.shape'), ('breasts', 'body.shape'),
            ('navel', 'body.detail'), ('feathers', 'object')]
        phrase = _defining_phrase(text)
        for noun, slot in targets:
            if re.fullmatch(r'(?i)(?:[\w-]+[, ]+){0,5}' + noun, phrase) and re.search(r'\b' + noun + r'\b', normalized) and not re.search(r'\b(?:another|holding|pull|lift|grab|peek|sex|insertion|from|under|over|between|after|covering)\b', normalized):
                rule = primitive(name, slot, adult=bool(ADULT.search(first) or noun == 'breasts'))
                if noun in {'hair', 'bangs', 'sidelocks'}:
                    rule['excludes'] = ['hair.length:bald']
                family = 'defined_anatomical_property'
                break
    # Certain physical objects are described by function rather than a named
    # type. The definition must explicitly be a device/vessel, not an image of
    # a device or a person operating one.
    if rule is None:
        phrase = _defining_phrase(text)
        if re.search(r'\b(?:device|appliance|apparatus|vessel|stopper|stand|launcher|projectile|munition|ammunition|ammunitions|container|product|peripheral|equipment|component|implement|utensil|invertebrate|vertebrate|mollusks|invertebrates|fruits|flowering plant|herb|shrub|genus|tree|plant|drug)\s*$', phrase, re.I) and not re.search(r'\b(?:another|own|holding|riding|insertion|on|in|over|under|from)\b', normalized):
            rule = primitive(name, 'object', adult=bool(ADULT.search(first) or ADULT.search(normalized)))
            rule['head'] = 'device' if re.search(r'\b(?:device|appliance|apparatus|peripheral)\b', phrase, re.I) else ''
            family = 'defined_physical_entity'
    # Approved descriptive vocabulary; the actual body or wardrobe component
    # must be the subject of the introductory definition as well as the tag.
    descriptors = r'long|short|medium|very long|small|large|big|thin|thick|wide|narrow|round|rounded|square|rectangular|triangular|pointy|pointed|sharp|serrated|curved|curly|wavy|straight|tall|low|high|extra|multiple|single|double|twin|triple|quad|deep|shallow|puffy|fluffy|fuzzy|messy|unkempt|sparse|dense|heavy|light|full|partial|partially|colored|covered|visible|exposed|hairy|smooth|shiny|glowing|translucent|transparent|solid|mechanical|prosthetic|artificial|fake|torn|damaged|broken|bandaged|frilled|pleated|ruffled|striped|horizontal-striped|vertical-striped|diagonal-striped|checkered|plaid|argyle|polka dot|polka-dot|fur-trimmed|lace-trimmed|ribbon-trimmed|asymmetrical|mismatched|uneven|detached|collared|hooded|ribbed|knitted|elastic|tight|loose|baggy|oversized|padded|lowleg|highleg|high-waisted|low-waisted|side-tie|front-tie|back-tie|side-string|string|tied|strapped|strapless|sleeveless|long-sleeved|short-sleeved|three-quarter|two-sided|reversible|stitched|embroidered|ornate|armored|metal|metallic|leather|latex|rubber|silk|satin|velvet|wool|denim|mesh|lace|fishnet|fishnets'
    nouns = {'hair': 'hair.detail', 'bangs': 'hair.bangs', 'sidelocks': 'hair.sidelocks', 'sideburns': 'body.detail',
        'eyebrows': 'eyes.detail', 'eyelashes': 'eyes.detail', 'eyes': 'eyes.detail', 'eye': 'eyes.detail', 'pupils': 'eyes.detail', 'sclera': 'eyes.detail',
        'skin': 'body.detail', 'lips': 'face.detail', 'tongue': 'face.detail', 'nose': 'face.detail', 'teeth': 'face.detail', 'fangs': 'face.detail',
        'mouth': 'face.detail', 'cheeks': 'face.detail', 'ears': 'body.ears', 'tail': 'body.tail', 'tails': 'body.tail', 'horns': 'body.horns', 'wings': 'body.wings',
        'breasts': 'body.shape', 'hips': 'body.shape', 'thighs': 'body.shape', 'arms': 'body.shape', 'hands': 'body.shape', 'feet': 'body.shape', 'legs': 'body.shape',
        'fingers': 'body.shape', 'nails': 'body.nails', 'halo': 'body.halo', 'navel': 'body.detail', 'feathers': 'object',
        'sleeves': 'clothing.sleeves', 'collar': 'clothing.collar', 'cuffs': 'clothing.trim', 'trim': 'clothing.trim', 'straps': 'clothing.detail',
        'buttons': 'clothing.trim', 'laces': 'clothing.detail', 'belt': 'accessory', 'belt buckle': 'clothing.trim', 'bandana': 'headwear',
        'thighhighs': 'legwear', 'kneehighs': 'legwear', 'leg warmers': 'legwear', 'arm warmers': 'handwear', 'eyewear': 'accessory',
        'breast curtain': 'top', 'bikini top': 'top', 'bikini bottom': 'bottom', 'shrug': 'outerwear'}
    if rule is None and (match := re.fullmatch(r'((?:(?:' + COLORS + '|' + descriptors + r') )(?:[\w-]+ ){0,2})(' + '|'.join(re.escape(noun) for noun in sorted(nouns, key=len, reverse=True)) + ')', normalized)):
        modifiers, noun = match.groups()
        # The first sentence must directly describe this noun, not mention it
        # as an example, comparison, purpose, or unrelated character.
        subject = re.match(r'(?i)^(?:(?:when\s+)?(?:(?:an?|the|any|one|two|multiple|several)\s+)?(?:(?:character|person)\'s\s+)?(?:pair of\s+)?)(?:[\w-]+[, ]+){0,5}' + re.escape(noun) + r'\b', first)
        if subject and not re.search(r'(?i)\b(?:instead|unlike|not to|do not|deprecated|ambiguous)\b', first):
            slot = nouns[noun]
            rule = primitive(name, slot, adult=noun == 'breasts' or bool(ADULT.search(first) or ADULT.search(normalized)))
            rule['head'] = noun
            if slot.startswith('clothing.'):
                rule['required_slots'] = [list(APPAREL)]
            if slot in {'hair.detail', 'hair.bangs', 'hair.sidelocks'}:
                rule['excludes'] = ['hair.length:bald']
            family = 'qualified_component_definition'
    if rule:
        return rule, {'family': family, 'definition': text[:600], 'passage': raw[:900], 'construction': first[:300]}
    return None, None
