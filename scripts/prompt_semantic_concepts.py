"""Source-backed adapters for specific props, visible details and small actions.

The exact-name tables describe independently checked concepts. A cached page
must still contain its positive defining evidence; names, examples and groups
alone never enable a rule. Ambiguous identity changes remain unreviewed.
"""
from __future__ import annotations

from copy import deepcopy
import re

from app.prompts.normalizer import canonical_tag_key as key
from app.prompts.semantic_rules import primitive
from scripts.prompt_semantic_attributes import APPAREL, COLORS
from scripts.prompt_semantic_families import UNRESOLVED, definition, plain


CONCEPTS = {}


def add(name, slot, proof, *, phrase=None, features=None, conditions=(), **kwargs):
    rule = primitive(name, slot, phrase=phrase, **kwargs)
    if features:
        rule['features'] = features
    if conditions:
        rule['conditions'] = list(conditions)
    CONCEPTS[key(name)] = (rule, re.compile(proof, re.I))


# These are concrete objects, not a property of some unspecified other object.
for name, proof in (
    ('earbuds', r'\bearphones\b'), ('beans', r'\blegume\b'),
    ('cheese', r'\bdairy\b'), ('ice_cube', r'\bice\b'),
    ('mat', r'\bfabric\b'), ('beach_mat', r'\bfabric\b'),
    ('sticky_note', r'\bpaper\b'), ('chest_of_drawers', r'\bfurniture\b'),
    ('ladder', r'\b(?:bars|steps)\b'), ('crutch', r'\b(?:stick|support|walking)\b'),
    ('cue_stick', r'\b(?:stick|billiards|pool)\b'),
    ('toothpick', r'\b(?:stick|teeth)\b'), ('popsicle_stick', r'\bstick\b'),
    ('selfie_stick', r'\bstick\b'), ('pacifier', r'\b(?:rubber|silicone|teat|infant)\b'),
    ('instrument_case', r'\bcase\b'), ('guitar_case', r'\bcase\b'),
    ('pencil_case', r'\bcase\b'), ('weapon_case', r'\bcase\b'), ('cd_case', r'\bcase\b'),
    ('tanzaku', r'\bpaper\b'), ('rug', r'\b(?:floor|covering)\b'),
    ('carpet', r'\b(?:floor|covering)\b'), ('eraser', r'\b(?:eras|rubber)\w*\b'),
    ('mannequin', r'\b(?:human|body|representation)\b'),
    ('mousepad_(object)', r'\bpad\b'), ('inkwell', r'\bink\b'),
    ('screw', r'\b(?:fastener|thread)\w*\b'), ('bolt_(hardware)', r'\b(?:fastener|thread)\w*\b'),
    ('weights', r'\b(?:objects|weight|exercise)\b'), ('sail', r'\bfabric\b'),
    ('magnet', r'\bmagnetic\b'), ('gauze', r'\bfabric\b'),
    ('candy_wrapper', r'\b(?:covering|candy|wrapper)\b'),
    ('chandelier', r'\b(?:fixture|light|lights)\b'),
    ('lampshade', r'\b(?:lamp|fixture|cover)\b'),
    ('industrial_pipe', r'\b(?:tube|pipe)\b'), ('snorkel', r'\btube\b'),
    ('diploma_tube', r'\btube\b'), ('windsock', r'\btube\b'),
    ('banknote', r'\b(?:currency|money|paper)\b'), ('paint', r'\b(?:mixture|pigment)\b'),
    ('seed', r'\b(?:plant|form|embryo)\b'), ('origami', r'\bpaper\b'),
    ('iphone', r'\bsmartphone\b'), ('faucet', r'\b(?:fixture|water|tap)\b'),
    ('candelabra', r'\b(?:candle|candles|holder)\b'),
    ('tambourine', r'\b(?:instrument|percussion)\b'), ('lyre', r'\b(?:instrument|harp)\b'),
    ('shards', r'\bpieces\b'), ('glass_shards', r'\b(?:glass|pieces)\b'),
    ('sprinkles', r'\b(?:pieces|confectionery|sugar)\b'),
    ('chickpeas', r'\b(?:legume|beans)\b'), ('seaweed', r'\b(?:algae|plant)\b'),
    ('muffin', r'\b(?:cake|bread|baked)\b'), ('snack', r'\b(?:food|meal)\b'),
    ('hamburger_steak', r'\b(?:meat|beef|steak)\b'),
    ('hotpot', r'\b(?:food|cooking|dish)\b'), ('turkey_(food)', r'\b(?:meat|bird|food)\b'),
    ('egg_(food)', r'\b(?:egg|food)\b'), ('blake_bloom_(wuthering_waves)', r'\bflower\b'),
    ('morning_glory', r'\b(?:flower|plant)\b'), ('bellflower', r'\b(?:flower|plant)\b'),
    ('lavender_(flower)', r'\b(?:flower|plant)\b'), ('orchid', r'\b(?:flower|plant)\b'),
    ('peony_(flower)', r'\b(?:flower|plant)\b'),
    ('jade_(gemstone)', r'\b(?:mineral|stone|gem)\w*\b'),
    ('diamond_(gemstone)', r'\b(?:carbon|gem|mineral)\w*\b'),
):
    add(name, 'object', proof)

# Garment pieces are worn facts. A piece of fabric is not automatically held.
for name, slot, proof in (
    ('chain_headband', 'accessory', r'\bheadband\b'),
    ('cross_tie', 'accessory', r'\b(?:neck|neckwear)\b'),
    ('han\'eri', 'accessory', r'\b(?:neckline|kimono)\b'),
    ('arm_wrap', 'handwear', r'\barm\b'), ('wrist_wrap', 'handwear', r'\bwrists?\b'),
    ('hand_wraps', 'handwear', r'\bhands\b'), ('leg_wrap', 'legwear', r'\bleg\b'),
    ('shin_guards', 'legwear', r'\b(?:shin|knee|ankle)\b'),
    ('poleyn', 'legwear', r'\bknees\b'), ('cuisses', 'legwear', r'\bthigh\b'),
    ('knee_guards', 'legwear', r'\bknees\b'),
    ('shoulder_guard', 'accessory', r'\bshoulder\b'),
    ('shoulder_plates', 'accessory', r'\bshoulders\b'),
    ('flak_jacket', 'outerwear', r'\bbody armor\b'),
    ('swimsuit_cover-up', 'outerwear', r'\b(?:garment|swimsuit)\b'),
    ('kesa', 'outerwear', r'\bgarment\b'), ('smock', 'outerwear', r'\bgarment\b'),
    ('swim_cap', 'headwear', r'\bscalp\b'), ('wataboushi', 'headwear', r'\b(?:hood|veil|head)\b'),
    ('sophist\'s_robe_(ff14)', 'outfit', r'\brobe\b'), ('tangzhuang', 'outfit', r'\b(?:clothing|jacket|dress)\b'),
    ('changpao', 'outfit', r'\b(?:gown|robe|dress)\b'), ('hanbok', 'outfit', r'\bclothing\b'),
    ('toga', 'outfit', r'\b(?:clothing|garment)\b'), ('unitard', 'outfit', r'\bgarment\b'),
    ('guimpe', 'top', r'\b(?:blouse|chemise|clothing)\b'),
    ('chest_guard', 'accessory', r'\b(?:covering|chest)\b'),
    ('cuff_links', 'accessory', r'\b(?:fastener|cuff)\w*\b'),
    ('chinese_knot', 'accessory', r'\b(?:knot|decorative)\b'),
):
    add(name, slot, proof)

for name, slot, proof, phrase in (
    ('sidelighting', 'lighting', r'\blighting\b', 'lighting from the side'),
    ('neon_lights', 'lighting', r'\b(?:neon|lights)\b', 'neon lighting'),
    ('scanlines', 'effect', r'\beffect\b', 'CRT-style scanlines'),
    ('double_exposure', 'effect', r'\b(?:superimpos|images)\w*\b', 'a double-exposure effect'),
    ('dotted_line', 'symbol', r'\bline\b', 'a line made of dots or dashes'),
    ('sun_symbol', 'symbol', r'\b(?:symbol|representation)\b', 'a sun symbol'),
    ('chemical_structure', 'symbol', r'\b(?:chemical|representation|molecule)\b', 'a chemical structure diagram'),
    ('roman_numeral', 'text', r'\b(?:numeral|number|roman)\w*\b', 'Roman numerals'),
    ('paw_print_pattern', 'symbol', r'\bpaw.prints?\b', 'a pattern of paw prints'),
    ('bindi', 'body.detail', r'\bforehead\b', 'a colored bindi on the forehead'),
    ('multiple_moles', 'body.detail', r'\bmultiple moles\b', 'multiple moles'),
    ('bikini_tan', 'body.detail', r'\btanlines\b', 'bikini-shaped tan lines'),
    ('one-piece_tan', 'body.detail', r'\btanlines\b', 'one-piece swimsuit-shaped tan lines'),
    ('pear-shaped_figure', 'body.shape', r'\bhips wider than\b', 'a pear-shaped figure with hips wider than the bust'),
    ('hot', 'expression', r'\bhot temperatures\b', 'feeling overheated'),
    ('cold', 'expression', r'\bcold temperatures\b', 'feeling cold'),
    ('obliques', 'body.detail', r'\bmuscles\b', 'visible oblique muscles'),
    ('back_muscles', 'body.detail', r'\bmuscles\b', 'visible back muscles'),
    ('deltoids', 'body.detail', r'\bmuscles\b', 'visible deltoid muscles'),
    ('arch', 'scene.detail', r'\bstructure\b', 'an arch'),
    ('truss', 'scene.detail', r'\bstructure\b', 'a structural truss'),
    ('railroad_tracks', 'scene.detail', r'\b(?:pathway|trains)\b', 'railroad tracks'),
    ('chimney', 'scene.detail', r'\b(?:structure|smoke|building)\b', 'a chimney'),
    ('flight_deck', 'scene.detail', r'\b(?:surface|aircraft)\b', 'a flight deck'),
    ('windowsill', 'scene.detail', r'\b(?:window|surface)\b', 'a windowsill'),
    ('bulletin_board', 'object', r'\b(?:surface|board|post)\b', 'a bulletin board'),
):
    add(name, slot, proof, phrase=phrase)

for name, word in (
    ('deviantart_username', 'DeviantArt'), ('tumblr_username', 'Tumblr'),
    ('facebook_username', 'Facebook'), ('email_address', 'email'),
    ('happy_halloween', 'Happy Halloween'), ('happy_anniversary', 'Happy Anniversary'),
):
    add(name, 'text', re.escape(word), phrase=word + (' address written in the image' if word == 'email' else ' username written in the image' if name.endswith('_username') else ' written in the image'))

HOODED = ['clothing:' + name for name in ('hoodie', 'hooded jacket', 'hooded coat', 'hooded cloak', 'hooded cape')]
for name, position in (('hood_up', 'up'), ('hood_down', 'down')):
    add(name, 'clothing.detail', r'\bhood\b', phrase='a hood ' + ('worn over the head' if position == 'up' else 'resting behind the head'), features={'clothing.hood.position': position}, excludes=('headwear:hood',) if position == 'down' else ())
    CONCEPTS[key(name)][0]['any_dependencies'] = [HOODED]

for name in ('contrast_lapels', 'plaid_lapels'):
    add(name, 'clothing.collar', r'\blapels\b')
    CONCEPTS[key(name)][0]['any_dependencies'] = [['clothing:' + word for word in ('jacket', 'coat', 'blazer', 'suit', 'tuxedo')]]
add('ribbon_as_bra', 'underwear.top', r'\b(?:bra|breasts)\b', phrase='a ribbon used as a bra', adult=True)
add('virgin_killer_sweater', 'top', r'\b(?:sweater|turtleneck)\b', adult=True)

add('mouth_hold', 'action', r'\bholding.+mouth\b', phrase='holding an object in the mouth', excludes=('face:tongue_out',))
CONCEPTS['mouth hold'][0]['any_dependencies'] = [['object:' + name for name in ('pen', 'pencil', 'card', 'flower', 'cloth', 'ribbon', 'knife')]]
add('straddling', 'action', r'\bboth legs.+either side\b', phrase='straddling an associated object', requires=('posture:sitting',), excludes=('body:one_legged',))
CONCEPTS['straddling'][0]['any_dependencies'] = [['object:' + name for name in ('chair', 'bench', 'bicycle', 'motorcycle', 'horse')]]
add('the_pose', 'action', r'\blies flat on.+stomach\b', phrase='lying on the stomach with feet raised', requires=('posture:on_stomach',), adult=True)
add('facing_to_the_side', 'gaze', r'\bclosed or covered eyes\b', phrase='turning the head to the side', features={'eyes.state': 'closed'}, requires=('eyes.state:closed_eyes',))
add('heart_hands_duo', 'interaction', r'\btwo characters.+heart hands\b', phrase='forming one heart shape together with their hands', actors=2)
for name, proof, phrase, genders in (
    ('friends', r'\bmutual affection\b', '{0} and {1} show their friendship', ()),
    ('parent_and_child', r'\bparent and their own child\b', '{0} is a parent of {1}', ()),
    ('mother_and_child', r'\bmother and her own child\b', '{0} is the mother of {1}', ('female', 'any')),
    ('father_and_child', r'\bfather and his own child\b', '{0} is the father of {1}', ('male', 'any')),
    ('adoptive_parent_and_adoptive_child', r'\bby adoption\b', '{0} is an adoptive parent of {1}', ()),
    ('half-siblings', r'\bshare a single parent\b', '{0} and {1} share exactly one parent', ()),
):
    # These are relationship facts, not declarations of the descendant's age.
    # Known identities need sourced genealogy; do not invent it for profiles.
    add(name, 'interaction', proof, actors=2, conditions=('ordinary_only', 'original_only'))
    CONCEPTS[key(name)][0]['role_phrase'] = phrase
    if genders:
        CONCEPTS[key(name)][0]['role_genders'] = list(genders)
    if name in {'friends', 'half-siblings'}:
        CONCEPTS[key(name)][0].pop('role_phrase')
        CONCEPTS[key(name)][0]['phrase'] = 'showing mutual affection as friends' if name == 'friends' else 'half-siblings sharing exactly one parent'

add('grabbing', 'action', r'^grabbing\b', phrase='grabbing an associated object')
CONCEPTS['grabbing'][0]['any_dependencies'] = [['object:' + item for item in ('book', 'pen', 'flower', 'bottle', 'sword', 'cup', 'bag')]]
for name, proof, phrase in (
    ('clothes_lift', r'\bclothing.+lifted up\b', 'lifted clothing'),
    ('clothes_pull', r'\bclothing.+pulled down\b', 'clothing pulled down'),
):
    add(name, 'clothing.exposure', proof, phrase=phrase, adult=True)
    CONCEPTS[key(name)][0]['required_slots'] = [['outfit', 'top', 'bottom', 'outerwear']]
    CONCEPTS[key(name)][0]['features'] = {'clothing.displacement': 'lifted' if name.endswith('lift') else 'pulled_down'}
add('lifting_own_clothes', 'action', r'\blifts up their own clothing\b', phrase='lifting their own clothing', adult=True, requires=('clothing:clothes_lift',))
for name, gender in (('topless_female', 'female'), ('topless_male', 'male')):
    add(name, 'coverage', r'\bnude from the waist up\b', phrase='bare-chested with lower-body clothing', adult=True,
        conditions=('gender:' + gender,), excludes=tuple('slot:' + slot for slot in ('outfit', 'top', 'outerwear', 'underwear', 'underwear.top')))
    CONCEPTS[key(name)][0]['required_slots'] = [['bottom']]
for name, proof, phrase, adult in (
    ('dressing', r'\bputting on clothes\b', 'putting on clothing', False),
    ('undressing', r'\btaking off.+clothes\b', 'taking off clothing', True),
):
    add(name, 'action', proof, phrase=phrase, adult=adult, excludes=('action:' + ('undressing' if name == 'dressing' else 'dressing'),))
    CONCEPTS[name][0]['required_slots'] = [['outfit', 'top', 'bottom', 'outerwear']]
add('multicolored_nails', 'body.nails', r'\bnails.+variety of colors\b', phrase='multicolored nails',
    provides=tuple('multicolor:body.' + part for part in ('nails', 'fingernails', 'toenails', 'claws')))

for name, proof, phrase in (
    ('ok_sign', r'\bindex finger and thumb\b', 'an OK sign'),
    ('gyaru_v', r'\bupside-down V\b', 'an upside-down V sign with the palm facing out'),
    ('inward_v', r'\bpalm facing inwards\b', 'a V sign with the palm facing inward'),
    ('two-finger_salute', r'\b(?:gesture|saluting)\b', 'a two-finger salute'),
    (r'\m/', r'\bthumb, index, and pinkie\b', 'an I-love-you hand sign'),
    (r'\n/', r'\bindex and pinkie\b', 'a sign-of-the-horns gesture'),
    (r'\||/', r'\bmiddle and ring fingers\b', 'a gesture with paired middle and ring fingers and spread outer fingers'),
):
    add(name, 'hands.pose', proof, phrase=phrase, features={'hands.gesture': key(name)})

for name, proof, phrase, dependencies in (
    ('._.', r'\bpair of dots\b', 'dot-shaped eyes', ()),
    ('|_|', r'\bvertical slits\b', 'eyes drawn as long vertical slits', ()),
    (':/', r'\bmouth.+closed\b', 'a closed mouth with one lowered corner', ('mouth:closed_mouth',)),
    (':|', r'\bmouth.+closed\b', 'a closed mouth drawn as a horizontal line', ('mouth:closed_mouth',)),
    (':<', r'\bfrown\b', 'a closed-mouth inverted V-shaped frown', ('mouth:closed_mouth', 'expression:frown')),
    (';(', r'\bone eye closed\b', 'a frown with one eye closed', ('mouth:closed_mouth', 'eyes:one_eye_closed', 'expression:frown')),
    (';<', r'\bone eye closed\b', 'a V-shaped frown with one eye closed', ('mouth:closed_mouth', 'eyes:one_eye_closed', 'expression:frown')),
    (';3', r'\bwinking\b', 'a cat-like smile with one eye closed', ('eyes:one_eye_closed', 'mouth:closed_mouth')),
    (';q', r'\bwinking\b', 'one eye closed with the tongue pointing upward', ('eyes:one_eye_closed', 'face:tongue_out')),
    ('>:(', r'\bv-shaped eyebrows\b', 'a frown with V-shaped eyebrows', ('expression:frown', 'face:v-shaped_eyebrows', 'mouth:closed_mouth')),
    ('>:)', r'\bv-shaped eyebrows\b', 'a smile with V-shaped eyebrows', ('expression:smile', 'face:v-shaped_eyebrows', 'mouth:closed_mouth')),
    ('<|>_<|>', r'\bvertical pupils\b', 'almond-shaped eyes with slit vertical pupils', ('eyes:slit_pupils',)),
):
    add(name, 'eyes.detail' if name in {'._.', '|_|', '<|>_<|>'} else 'face.detail', proof, phrase=phrase, requires=dependencies)
    if name in {'._.', '|_|', '<|>_<|>'}:
        CONCEPTS[key(name)][0]['features'] = {'eyes.state': 'open'}

for name, proof, phrase in (
    ('...', r'\b(?:dots|ellipsis)\b', 'an ellipsis'),
    ('...!', r'\bellipsis\b', 'an ellipsis followed by an exclamation mark'),
    ('...?', r'\bexpression.+combines\b', 'an ellipsis followed by a question mark'),
    ('??', r'\btwo or more question marks\b', 'two or more question marks'),
):
    add(name, 'symbol', proof, phrase=phrase)


def concept_rule(name, page):
    normalized = key(name)
    raw = definition(page.get('body', ''))
    text = plain(raw)
    if not text or UNRESOLVED.search(text) or UNRESOLVED.search(normalized):
        return None, None
    # Only the introductory positive passage establishes the concept. Related
    # examples never repair a mismatching introduction.
    first = re.split(r'\n|\.(?:\s|$)', text, maxsplit=1)[0]
    family = 'specific_verified_concept'
    if normalized in CONCEPTS:
        spec, proof = CONCEPTS[normalized]
        if not proof.search(first):
            return None, None
        rule = deepcopy(spec)
    elif match := re.fullmatch(r'([1-4])others?', normalized):
        if not re.search(r'\b(?:ambiguous|indeterminate|genderless|unknown gender|gender is not|gender.+not known)\b', text[:600], re.I):
            return None, None
        count = int(match[1])
        rule = primitive(name, 'count', phrase=str(count) + ' subjects of indeterminate gender', actors=count)
        rule['conditions'] = ['unknown:' + str(count)]
        family = 'indeterminate_gender_count'
    elif re.fullmatch(r'\d{4}', normalized) and re.search(r'\bimage.+year.+written\b', first, re.I):
        # The source explicitly permits text or a year reference. Choose the
        # written-text subcase, not an inferred creation date or a time setting.
        rule = primitive(name, 'text', phrase='the year "' + normalized + '" written in the image')
        family = 'written_year_text'
    elif match := re.fullmatch(r'(' + COLORS + r') (scales|fur|sclera|nails|fingernails|toenails|claws)', normalized):
        color, part = match.groups()
        escaped = re.escape(part)
        evidence_pattern = r'\b(?:' + re.escape(color) + r'\s+' + escaped + r'|' + escaped + r'.{0,50}\b' + re.escape(color) + r')\b'
        positive = re.search(evidence_pattern, first, re.I)
        if part == 'sclera':
            positive = positive or re.search(r'\bwhite part of the eyes\b.{0,50}\b' + re.escape(color) + r'\b', first, re.I)
        if not positive:
            return None, None
        slot = 'eyes.detail' if part == 'sclera' else 'body.nails' if part in {'nails', 'fingernails', 'toenails', 'claws'} else 'body.detail'
        rule = primitive(name, slot)
        color = color.replace('gray', 'grey')
        # Fur/scales can cover distinct regions. A visible colored patch does
        # not claim that every patch is that color. Keep these additive rather
        # than inventing a uniform-color restriction on sourced identities.
        feature = 'body.' + part + '.color' + ('.' + color if part in {'fur', 'scales'} else '')
        rule['features'] = {feature: 'yes' if part in {'fur', 'scales'} else color}
        family = 'positive_body_component_color'
    else:
        return None, None
    if rule['slot'].startswith('clothing.') and 'any_dependencies' not in rule:
        rule['required_slots'] = [list(APPAREL)]
    return rule, {'family': family, 'definition': text[:600], 'passage': raw[:900], 'matched_passage': first}
