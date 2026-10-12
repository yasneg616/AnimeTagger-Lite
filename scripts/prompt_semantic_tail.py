"""Checked long-tail concepts with owned garments, props and plain expressions.

Each exact tag has an independently selected reading and positive introductory
evidence. Generic actions choose bounded, concrete targets; acquisition alone
does not enable them. There is no fallback from an unknown noun to a rule.
"""
from copy import deepcopy
import re

from app.prompts.normalizer import canonical_tag_key as key
from app.prompts.semantic_rules import primitive
from scripts.prompt_semantic_families import UNRESOLVED, definition, plain

SPECS = {}


def add(name, slot, proof, *, phrase=None, features=None, required_slots=(),
        any_dependencies=(), conditions=(), role_phrase='', role_genders=(), **kwargs):
    rule = primitive(name, slot, phrase=phrase, **kwargs)
    if features: rule['features'] = features
    if required_slots: rule['required_slots'] = [list(group) for group in required_slots]
    if any_dependencies: rule['any_dependencies'] = [list(group) for group in any_dependencies]
    if conditions: rule['conditions'] = list(conditions)
    if role_phrase: rule['role_phrase'] = role_phrase
    if role_genders: rule['role_genders'] = list(role_genders)
    SPECS[key(name)] = rule, re.compile(proof, re.I)


for name, proof in (
    ('sticker', r'\b(?:paper|plastic)\b.*\bsticky\b'),
    ('spring_onion', r'\b(?:onion|leek)\b'),
    ('poster_(object)', r'\bprinted picture\b'),
    ('calendar_(object)', r'\bcontains a calendar\b'),
    ('portrait_(object)', r'\bcontains a portrait\b'),
    ('figure', r'\bsmall.scale statue\b'),
    ('shouji', r'\b(?:sliding door|panel)\b'),
    ('cage', r'\bstructure of bars\b'), ('birdcage', r'\bcage\b'),
    ('swing', r'\bhanging seat\b'),
    ('vial', r'\b(?:glass|vessel)\b'),
    ('potion', r'\b(?:vial|flask|bottle|container)\b.*\bliquid\b'),
    ('steering_wheel', r'\bsteering control\b'),
    ('drawer', r'\bboxes\b'), ('tablecloth', r'\bcloth\b.*\btable\b'),
    ('window_blinds', r'\bwindow covering\b'),
    ('poker_chip', r'\b(?:disk.shaped|counter)\b'),
    ('streamers', r'\bstrips of paper\b'),
    ('caution_tape', r'\btape\b'), ('film_strip', r'\bstrip of still images\b'),
    ('string_of_flags', r'\bstring of flag\b'),
    ('cube', r'\bgeometric object\b.*\bsix faces\b'),
    ('tube', r'\bhollow cylinder\b'), ('log', r'\btrunk\b.*\btree\b'),
    ('tree_stump', r'\bbase of tree\b'),
    ('rubble', r'\b(?:rocks|concrete)\b'),
    ('nail_(hardware)', r'\bspikes of metal\b'),
    ('grenade_pin', r'\bpin\b.*\bseparated\b'),
    ('drum_set', r'\bcollection of drums\b'),
    ('gibson_les_paul', r'\belectric guitar\b'),
    ('icing', r'\bsweet glaze\b'), ('toast', r'\bslice of bread\b'),
    ('baguette', r'\bloaf of bread\b'), ('pie', r'\bpastry crust\b'),
    ('dessert', r'\bsweet foods\b'), ('sweets', r'\bfoods\b.*\bsugar\b'),
    ('cucumber', r'\b(?:fruit|cucumis)\b'), ('bud', r'\bsproutings\b'),
    ('four-leaf_clover', r'\bclover\b'),
    ('ceiling_light', r'\blight fixture\b'),
    ('smokestack', r'\bexhaust pipe\b'),
    ('fireplace', r'\bchimney\b'),
):
    add(name, 'object', proof)

for name, proof, phrase in (
    ('balcony', r'\bplatform\b.*\b(?:ceiling|building)\b', 'a balcony'),
    ('train_station_platform', r'\bplatform\b.*\btrain\b', 'a train station platform'),
    ('path', r'\broad or trail\b', 'a footpath'),
    ('canal', r'\bbody of water\b.*\bmankind\b', 'a man-made canal'),
    ('stream', r'\bbody of water\b.*\briver\b', 'a small stream'),
    ('graveyard', r'\blocation\b.*\bburied\b', 'a graveyard'),
    ('grasslands', r'\barea\b.*\bgrasses\b', 'grasslands'),
    ('cockpit', r'\barea\b.*\bvehicle\b', 'a vehicle cockpit'),
    ('shower_(place)', r'\broom or stall\b', 'a shower room'),
):
    add(name, 'location', proof, phrase=phrase)

for name, proof, phrase in (
    ('crosswalk', r'\b(?:pedestrian crossing|marked path)\b', 'a marked pedestrian crossing'),
    ('pavement', r'\bstones\b.*\bsurface\b', 'stone pavement'),
    ('contrail', r'\b(?:vapor|condensation) trail\b.*\bairplane', 'an aircraft condensation trail'),
):
    add(name, 'scene.detail', proof, phrase=phrase)

add('morning', 'time', r'\bpart of the day\b', phrase='morning')
add('evening', 'time', r'\bafternoon\b.*\bsun\b', phrase='evening before nightfall')
add('overcast', 'weather', r'\bsky\b.*\bcompletely covered\b', phrase='a fully overcast sky')

for name, proof, phrase in (
    ('linear_hatching', r'\bshading technique\b', 'shading with parallel hatching lines'),
    ('faux_traditional_media', r'\bdigitally.created\b.*\btraditional media\b', 'digital art mimicking traditional media'),
    ('cyberpunk', r'\bscience fiction genre\b', 'a cyberpunk setting and visual style'),
    ('pale_colors', r'\bcolors\b.*\bpale\b', 'a pale, low-contrast color palette'),
    ('pale_color', r'\bcolors\b.*\bpale\b', 'a pale, low-contrast color palette'),
    ('viewfinder', r'\bcamera frame\b', 'a camera viewfinder frame'),
    ('fake_cover', r'\bmock.up cover\b', 'a fictional cover design'),
    ('fake_magazine_cover', r'\bmock cover\b', 'a fictional magazine cover design'),
):
    add(name, 'style', proof, phrase=phrase)
add('sideways', 'view', r'\bimage oriented on its side\b', phrase='an image rotated 90 degrees sideways')

for name, proof, phrase in (
    ('hexagram', r'\bsix.pointed star\b', 'a six-pointed star symbol'),
    ('inverted_cross', r'\bupside.down\b', 'an inverted cross symbol'),
    ('broken_heart', r'\bdisjoint pieces\b.*\bheart\b', 'a broken-heart symbol'),
    ('insignia', r'\bsymbol\b.*\brank\b', 'an insignia symbol'),
    ('emoji', r'\bicon\b.*\btext\b', 'an emoji embedded in text'),
    ('beamed_sixteenth_notes', r'\bsixteenth notes\b.*\bbeam\b', 'beamed sixteenth-note symbols'),
    ('union_jack', r'\bnational flag\b.*\bUnited Kingdom\b', 'the United Kingdom flag'),
):
    add(name, 'symbol', proof, phrase=phrase)
add('meandros', 'border', r'\bdecorative border\b', phrase='a repeating Greek-key border')
add('simplified_chinese_text', 'text', r'\bSimplified Chinese characters\b', phrase='text written in Simplified Chinese')
add('trick_or_treat', 'text', r'\bphrase\b.*\bTrick or Treat\b', phrase='the words "Trick or Treat"')
add('pixiv_id', 'text', r'\bnumerical pixiv ID\b', phrase='a numeric Pixiv artist ID written in the image')
add('group_name', 'text', r'\bname of a team\b', phrase='a written team or group name')

for name, proof, phrase in (
    ('sunburst', r'\brays of light\b.*\bcentral point\b', 'a sunburst of light rays'),
    ('diffraction_spikes', r'\bspikes of light\b', 'diffraction spikes radiating from a bright light'),
    ('caustics', r'\bpatterns of light\b', 'reflected or refracted caustic light patterns'),
    ('ring_light_reflection', r'\bring.shaped reflection\b', 'ring-shaped light reflections'),
):
    add(name, 'effect', proof, phrase=phrase)

for name, slot, proof, phrase in (
    ('pirate_costume', 'outfit', r'\bdressed as a stereotypical pirate\b', 'a pirate costume'),
    ('pirate', 'outfit', r'\bdressed as a stereotypical pirate\b', 'a pirate costume'),
    ('loungewear', 'outfit', r'\bcomfortable clothes\b', 'comfortable loungewear'),
    ('wrestling_outfit', 'outfit', r'\bclothing\b.*\bwrestling\b', 'a wrestling outfit'),
    ('dalachi_(headdress)', 'headwear', r'\bheaddress', 'a Manchurian dalachi headdress'),
    ('xiao_guan_(headdress)', 'headwear', r'\bheadwear\b', 'a xiao guan headdress'),
    ('bolo_tie', 'accessory', r'\bcord\b.*\bclasp\b', 'a bolo tie'),
    ('crescent_pin', 'accessory', r'\b(?:brooch|lapel pin)\b', 'a crescent-shaped pin'),
    ('carrot_necklace', 'accessory', r'\baccessory\b.*\brabbit girls\b', 'a carrot-shaped necklace'),
    ('lapel_pin', 'accessory', r'\bpin worn on clothing\b', 'a lapel pin'),
    ('linked_piercing', 'accessory', r'\btwo piercings linked together\b', 'two piercings linked together'),
    ('multiple_bracelets', 'accessory', r'\bmultiple bracelets\b.*\bsame wrist\b', 'multiple bracelets on the same wrist'),
    ('multiple_piercings', 'accessory', r'\bmultiple piercings\b.*\bsame piercing site\b', 'multiple piercings at one site'),
    ('ring_hair_extensions', 'accessory', r'\bhair extensions\b.*\bring\b', 'hair extensions fastened with rings'),
):
    add(name, slot, proof, phrase=phrase)

for name, proof, phrase in (
    ('birthmark', r'\birregularity on the skin\b', 'a birthmark'),
    ('head_bump', r'\bswelling on the head\b', 'a cartoon swelling on the head'),
    ("adam's_apple", r'\blump on the neck\b', "a visible Adam's apple"),
    ('goatee_stubble', r'\bshort, coarse hair\b', 'goatee stubble'),
    ('mustache_stubble', r'\bshort, coarse hair\b', 'mustache stubble'),
    ('sideburns_stubble', r'\bshort, coarse hair\b', 'sideburn stubble'),
    ('very_long_fingernails', r'\bfingernails\b.*\bfingertips\b', 'very long fingernails'),
    ('linea_alba', r'\bvertical line\b.*\bnavel\b', 'a visible vertical linea alba above the navel'),
):
    add(name, 'body.detail', proof, phrase=phrase)
add('armpit_crease', 'body.detail', r'\bcrease of skin\b.*\barm is lowered\b',
    phrase='an armpit crease with the arm lowered', requires=('action:arms_at_sides',), excludes=('action:arms_up', 'action:arm_up'))
add('blunt_tresses', 'hair.detail', r'\bhair\b.*\bcut flat\b', phrase='bluntly cut separated tresses', excludes=('hair.length:bald',))
add('single_braided_sidelock', 'hair.detail', r'\bsingle braid\b.*\bear\b', phrase='one braided sidelock in front of the ear', excludes=('hair.length:bald',))

add('palms_together', 'hands.pose', r'\bpalms touching\b', phrase='palms pressed together without interlocking fingers', features={'hands.configuration': 'palms_together'})
add('index_fingers_together', 'hands.pose', r'\bindex fingers together\b', phrase='touching the tips of the index fingers together', features={'hands.configuration': 'index_fingers_together'})
add('finger_to_own_chin', 'hands.pose', r'\bfingers\b.*\bown chin\b', phrase='a finger resting on their own chin')
add('left-handed', 'hands.pose', r'\bleft hand\b.*\bdominant hand\b', phrase='using the left hand as their dominant hand', features={'hands.dominance': 'left'})
add('right-handed', 'hands.pose', r'\bright hand\b.*\bdominant hand\b', phrase='using the right hand as their dominant hand', features={'hands.dominance': 'right'})

for name, proof, phrase in (
    ('jealous', r'\bfeeling\b.*\bpossessive\b', 'jealous'),
    ('false_smile', r'\bsmiling\b.*\banything but happy\b', 'a smile masking unhappiness'),
    ('sigh', r'\bexhalation of air\b', 'sighing'),
    ('flexing', r'\bshows off their muscles\b', 'flexing their muscles'),
):
    add(name, 'expression' if name in {'jealous', 'false_smile'} else 'action', proof, phrase=phrase)

# These relations describe an ordinary original cast, without inventing
# canonical family/teacher facts or deriving ages from a role name.
for name, genders, role, proof in (
    ('mother_and_daughter', ('female', 'female'), '{0} is the mother of {1}', r'\bmother and her daughter\b'),
    ('mother_and_son', ('female', 'male'), '{0} is the mother of {1}', r'\bmother and her son\b'),
    ('father_and_daughter', ('male', 'female'), '{0} is the father of {1}', r'\bfather and his daughter\b'),
    ('father_and_son', ('male', 'male'), '{0} is the father of {1}', r'\bfather and his son\b'),
    ('teacher_and_student', ('any', 'any'), '{0} is the teacher of {1}', r'\bteacher and their student\b'),
    ('family_bonding', ('any', 'any'), '{0} and {1} are family members spending time together', r'\bfamily members\b.*\bquality time\b'),
):
    add(name, 'interaction', proof, actors=2, role_phrase=role, role_genders=genders, conditions=('ordinary_only', 'original_only'))

for name, garment, body_part, proof in (
    ('jacket_on_shoulders', 'jacket', 'shoulders', r'\bjacket draped over the shoulders\b'),
    ('coat_on_shoulders', 'coat', 'shoulders', r'\bcoat draped over the shoulders\b'),
    ('jacket_around_waist', 'jacket', 'waist', r'\bjacket\b.*\baround\b.*\bwaist\b'),
    ('cardigan_around_waist', 'cardigan', 'waist', r'\bcardigan worn around the waist\b'),
    ('headphones_around_neck', 'headphones', 'neck', r'\bheadphones around the neck\b'),
    ('towel_around_neck', 'towel', 'neck', r'\btowel draped around their neck\b'),
):
    # An unworn garment is an owned prop in this placement, rather than a
    # second worn jacket with its sleeves and buttons applied to the actor.
    add(name, 'placement', proof, phrase=f'{garment} draped around their {body_part}',
        requires=('object:' + garment,), excludes=('outerwear:' + garment,) if garment in {'jacket', 'coat', 'cardigan'} else ())

bottoms = ('bottom:skirt', 'bottom:pants', 'bottom:shorts')
for name, state, proof in (
    ('shirt_tucked_in', 'fully', r'\bshirt\b.*\bcompletely tucked in\b'),
    ('shirt_partially_tucked_in', 'partially', r'\bshirt\b.*\bpartially tucked in\b'),
):
    add(name, 'clothing.detail', proof, phrase=f'the shirt {state} tucked into the bottom garment',
        requires=('top:shirt',), any_dependencies=(bottoms,), features={'clothing.shirt.tuck': state})
add('adjusting_clothes', 'action', r'\bfixing any article of clothing\b', phrase='adjusting their worn clothing',
    required_slots=(('outfit', 'top', 'bottom', 'outerwear', 'headwear', 'legwear', 'footwear', 'handwear', 'accessory'),))
add('pantyhose_under_shorts', 'clothing.detail', r'\bpantyhose\b.*\bbeneath\b.*\bshorts\b',
    phrase='pantyhose worn beneath their shorts', requires=('legwear:pantyhose', 'bottom:shorts'))
add('thighhighs_under_boots', 'clothing.detail', r'\bthighhigh stockings worn under boots\b',
    phrase='thighhigh stockings worn under their boots', requires=('legwear:thighhighs', 'footwear:boots'))
add('unworn_helmet', 'placement', r'\bhelmet\b.*\bvisible but not worn\b', phrase='a visible helmet that is not worn',
    requires=('object:helmet',), excludes=('headwear:helmet',))

portable = tuple('object:' + name for name in ('book', 'bag', 'basket', 'box', 'pillow', 'stuffed_animal'))
for name, phrase, proof in (
    ('carrying', 'carrying an associated object', r'\bsupporting something or someone\b'),
    ('hugging_object', 'hugging an associated inanimate object', r'\bhugging an inanimate object\b'),
    ('holding_behind_back', 'holding an associated object behind their back', r'\bholding something behind the back\b'),
):
    add(name, 'action', proof, phrase=phrase, any_dependencies=(portable,))
add('biting', 'action', r'\bteeth\b.*\bpierce or hold an object\b', phrase='biting an associated object',
    any_dependencies=(('object:apple', 'object:carrot', 'object:bread', 'object:pencil'),), excludes=('mouth:tongue_out',))
add('between_fingers', 'placement', r'\bholding something between two fingers\b', phrase='holding a small object between two fingers',
    any_dependencies=(('object:card', 'object:coin', 'object:ofuda', 'object:cigarette'),))
add('weapon_over_shoulder', 'action', r'\bweapon over the shoulder\b', phrase='carrying a weapon over their shoulder',
    any_dependencies=(('object:sword', 'object:rifle', 'object:axe', 'object:scythe'),))
add('holding_animal', 'action', r'\bholding an animal\b', phrase='holding a small associated animal',
    any_dependencies=(('object:cat', 'object:rabbit', 'object:chick'),))
add('animal_hug', 'action', r'\bhugging an animal\b', phrase='hugging a small associated animal',
    any_dependencies=(('object:cat', 'object:rabbit'),))
add('riding', 'action', r'\briding an animal or a vehicle\b', phrase='riding an associated mount or vehicle',
    any_dependencies=(('object:horse', 'object:bicycle', 'object:motorcycle'),), requires=('posture:sitting',), excludes=('posture:standing', 'posture:lying'))
for name, target, proof in (
    ('on_desk', 'desk', r'\bon a desk\b'), ('on_throne', 'throne', r'\bon the throne\b'),
):
    add(name, 'placement', proof, phrase='sitting on an associated ' + target,
        requires=('object:' + target, 'posture:sitting'))
add('two-handed', 'hands.pose', r'\bboth hands\b.*\bsingle weapon\b', phrase='gripping a weapon with both hands',
    any_dependencies=(('object:sword', 'object:rifle', 'object:spear', 'object:axe'),), features={'hands.configuration': 'two_handed_grip'})
add('drawing_(action)', 'action', r'\bcreating a picture\b.*\b(?:pencil|pen)\b', phrase='drawing on associated paper',
    requires=('object:paper',), any_dependencies=(('object:pencil', 'object:pen', 'object:crayon', 'object:marker'),))
add('blowing_bubble_gum', 'action', r'\bchewing gum\b.*\bblow bubbles\b', phrase='blowing a bubble with chewing gum', requires=('object:chewing_gum',))
add('flattop', 'hair.style', r'\btype of haircut\b.*\bstyled upright\b', phrase='a flat-top haircut', excludes=('hair.length:bald',))

# Further concrete items whose introductions describe a material, function or
# brand rather than one of the generic noun-family heads.
for name, proof, phrase in (
    ('ritual_baton', r'\bflat scepter\b', 'a ritual baton'),
    ('pancake_stack', r'\bpancakes piled\b', 'a stack of pancakes'),
    ('shiba_inu', r'\bdistinct purebred dog\b', 'a Shiba Inu dog'),
    ('thread', r'\bstrand\b.*\bfibers\b', 'sewing thread'),
    ('yarn', r'\bstrands of fiber\b', 'yarn'),
    ('hagoita', r'\bwooden paddle\b', 'a decorated hagoita paddle'),
    ('coffin', r'\bfunerary box\b', 'a coffin'),
    ('soup', r'\bliquid food\b', 'soup'),
    ('dowsing_rod', r'\bshaped rod\b', 'a dowsing rod'),
    ('sunscreen', r'\b(?:cream|lotion|oil)\b.*\bsunburn\b', 'sunscreen'),
    ('crumbs', r'\bparticles of crumbly food\b', 'food crumbs'),
    ('bamboo_steamer', r'\bcookware made from bamboo\b', 'a bamboo steamer'),
    ('haniwa_(statue)', r'\bterracotta clay sculptures\b', 'a terracotta haniwa statue'),
    ('napkin', r'\bcloth or paper\b.*\bclean\b', 'a napkin'),
    ('kanabou', r'\bspiked club\b', 'a Japanese spiked kanabou club'),
    ('saddle', r'\bseat placed on the back\b', 'a saddle'),
    ('heart_(organ)', r'\borgan\b.*\bpumps blood\b', 'an anatomical heart'),
    ('board_game', r'\btabletop game\b', 'a board game'),
    ('ammunition', r'\bmanufactured material fired from a gun\b', 'ammunition'),
    ('d-pad', r'\bdirectional control\b', 'a directional control pad'),
    ('character_charm', r'\bcharm\b.*\bdesigned after a character\b', 'a character-shaped charm'),
):
    add(name, 'object', proof, phrase=phrase)
add('sidewalk', 'location', r'\bpaved path\b.*\broad\b', phrase='a sidewalk')
add('island', 'location', r'\bland\b.*\bwatery body\b', phrase='an island')
add('lattice', 'scene.detail', r'\bwooden\b.*\bpanels\b', phrase='decorative wooden lattice panels')

for name, slot, proof, phrase in (
    ('tarot_(medium)', 'style', r'\bentire image drawn\b.*\btarot card\b', 'a tarot-card illustration'),
    ('western_comics_(style)', 'style', r'\bstyle of traditional\b.*\bcomic books\b', 'a traditional Western comic-book style'),
    ('vignetting', 'effect', r'\bbrightness or saturation\b.*\bperiphery\b', 'a peripheral vignette'),
    ('sparkling_aura', 'effect', r'\bsparkles surrounding\b', 'an aura of sparkles'),
    ('very_wide_shot', 'framing', r'\bsubject is fully visible\b.*\bsmall portion\b', 'a very wide shot with the full subject small in the frame'),
    ('doodle_inset', 'style', r'\bdoodle\b.*\bsmaller portion of the image\b', 'a small doodle inset'),
    ('doodle', 'style', r'\b(?:drawing|sketch)\b', 'a doodle style'),
    ('sakuramon', 'symbol', r'\bdepiction of a five.petaled cherry blossom\b', 'a five-petaled sakuramon emblem'),
    ('runes', 'text', r'\bletters\b.*\brunic alphabets\b', 'written runes'),
    ('cursive', 'text', r'\bcursive writing\b', 'cursive handwriting'),
    ('lyrics', 'text', r'\bsong lyrics written\b', 'written song lyrics'),
    ('yes', 'text', r'\bemphasizes the word\b', 'the literal word "yes"'),
    ('akeome', 'text', r'\bnew year.s greeting\b', 'the Japanese greeting "akeome"'),
    ('fortissimo', 'symbol', r'\bdynamic notation\b', 'the musical dynamic marking "ff"'),
    ('furigana', 'text', r'\bjapanese reading aid\b', 'small furigana reading aids alongside Japanese characters'),
):
    add(name, slot, proof, phrase=phrase)

add('crocs', 'footwear', r'\bclog.shaped resin shoes\b', phrase='resin Crocs clogs')
add('pom_pom_beanie', 'headwear', r'\bbeanie\b.*\bpom pom\b', phrase='a beanie with a pom-pom')
add('single_arm_warmer', 'handwear', r'\barm warmers on only one arm\b', phrase='one arm warmer')
add('single_wrist_cuff', 'accessory', r'\bwrist cuff\b.*\bonly one wrist\b', phrase='one wrist cuff')
add('single_shoulder_pad', 'accessory', r'\bshoulder pads\b.*\bonly one side\b', phrase='one shoulder pad')
add('wig', 'headwear', r'\bhairpiece worn\b', phrase='a wig')
add('visor_(armor)', 'clothing.detail', r'\bpart of a helmet\b.*\bface\b', phrase='a helmet visor covering the face', requires=('headwear:helmet',))
add('juban', 'clothing.detail', r'\bgarment worn under the kimono\b', phrase='a juban worn beneath the kimono', requires=('outfit:kimono',), excludes=('outfit:yukata',))
add('gusset', 'clothing.detail', r'\binset piece of material\b.*\bpantyhose or leggings\b', phrase='an inset gusset in their legwear', any_dependencies=(('legwear:pantyhose', 'legwear:leggings'),))
add('shoelaces', 'clothing.detail', r'\bstrings or cords\b.*\bshoe\b', phrase='shoelaces on their shoes', required_slots=(('footwear',),))
add('exposed_pocket', 'clothing.detail', r'\bshorts\b.*\bpockets are visible\b', phrase='pockets visible below the hems of their shorts', requires=('bottom:denim_shorts',))
for name, proof, phrase in (
    ('embroidery', r'\bdecorating clothes\b.*\bstitched designs\b', 'embroidered designs'),
    ('musical_note_print', r'\bmusical notes printed\b', 'a musical-note print'),
    ('single_horizontal_stripe', r'\blone horizontal stripe\b', 'one horizontal stripe'),
    ('single_vertical_stripe', r'\bvertical stripe\b.*\bclothing\b', 'one vertical stripe'),
):
    add(name, 'clothing.pattern', proof, phrase=phrase, required_slots=(('outfit', 'top', 'bottom', 'outerwear', 'headwear', 'legwear', 'handwear', 'accessory'),))

add('sharp_toenails', 'body.nails', r'\bsharp and pointed toenails\b', phrase='sharp pointed toenails')
add('shoulder_blush', 'body.detail', r'\bshoulders\b.*\bblushing\b', phrase='blushing shoulders')
add('cheekbones', 'body.detail', r'\bbone below the eyes\b', phrase='prominent cheekbones')
add('uvula', 'face.detail', r'\bflap of tissue\b.*\bthroat\b', phrase='a visible uvula in the open mouth', requires=('mouth:open_mouth',))
add('squinting', 'eyes.state', r'\bpartly closing the eyes\b', phrase='squinting')
add('sick', 'body.detail', r'\bill health\b', phrase='appearing unwell')
add('ballet', 'action', r'\bperformance dancing\b', phrase='performing a standing ballet dance', requires=('action:dancing', 'posture:standing'))
add('high_kick', 'legs.pose', r'\bkick\b.*\bhigher\b.*\bwaist\b', phrase='a high kick above waist level', requires=('posture:standing',))
add('text_messaging', 'action', r'\btext messages on a cellphone\b', phrase='sending text messages on a cellphone', requires=('object:cellphone',))
add('sidesaddle', 'placement', r'\briding something with both legs on the same side\b', phrase='riding an associated horse with both legs on the same side', requires=('object:horse', 'posture:sitting'))
add('comforting', 'interaction', r'\bease another.s sadness\b', actors=2, role_phrase='{0} comforts {1}')
SPECS[key('comforting')][0]['role_requires'] = [[], ['expression:sad']]

# These placements select one concrete reading of an otherwise broad action.
# Every required prop belongs to the actor performing it.
add('ship', 'object', r'\blarge seagoing vessel\b', phrase='a large seagoing ship')
add('screen', 'object', r'\binformation display\b', phrase='an information display screen')
add('skates', 'footwear', r'\bboots with wheels or blades\b', phrase='a pair of skates')
add('neck_ruff', 'accessory', r'\bfrill or ruffle worn around the neck\b', phrase='a neck ruff')
add('single_detached_sleeve', 'accessory', r'\bsingle detached sleeve\b', phrase='a single detached sleeve')
add('bag_charm', 'placement', r'\btrinket attached to a bag\b', phrase='a charm attached to their bag', requires=('object:bag',))
add('whistle_around_neck', 'placement', r'\bwhistle on a necklace\b', phrase='a whistle hanging on a necklace around their neck', requires=('object:whistle',))
add('over_shoulder', 'placement', r'\bobject over one shoulder\b', phrase='carrying an associated bag over one shoulder', requires=('object:bag',))
add('arm_rest', 'hands.pose', r'\bresting one.s arm\b.*\bsurface\b', phrase='resting their arms on an associated table', requires=('object:table',))
add('reverse_grip', 'action', r'\bknife grip\b.*\bblade pointing down\b', phrase='holding an associated knife with its blade pointing down from the fist', requires=('object:knife',))
add('male_maid', 'clothing.detail', r'\bmale character dressed in a maid outfit\b', phrase='wearing a maid outfit', requires=('outfit:maid',), conditions=('gender:male',))
add('red_eyeliner', 'face.detail', r'\bcolor of eyeliner\b', phrase='red eyeliner', features={'makeup.eyeliner.color': 'red'})
add('bandage_over_one_eye', 'face.detail', r'\bbandage or adhesive bandaid placed over an eye\b', phrase='a bandage covering one eye')
add('height_difference', 'interaction', r'\bconspicuously taller than another character\b', actors=2, role_phrase='{0} is conspicuously taller than {1}')
add('multiple_others', 'count', r'\bmultiple ambiguously or non.gendered characters\b', phrase='multiple characters of indeterminate gender', actors=2, conditions=('unknown:2',))
add('screenshot_inset', 'style', r'\bscreenshot\b.*\bsmaller inset\b', phrase='a screenshot inset within the illustration')
add('magazine_cover', 'style', r'\bcover page for a magazine\b', phrase='a magazine cover layout')
add('fake_phone_screenshot', 'style', r'\bfake screenshot of a cellphone screen\b', phrase='an illustration presented as a mock cellphone screenshot')


def tail_rule(name, page):
    normalized = key(name)
    if normalized not in SPECS: return None, None
    raw = definition(page.get('body', ''))
    text = plain(raw)
    sentence_text = re.sub(r'\([^)]*\)', lambda match: match[0].replace('.', ''), text)
    first = re.split(r'\n|\.(?:\s|$)', sentence_text, maxsplit=1)[0]
    if not first or UNRESOLVED.search(text) or re.match(r'(?i)^(?:not|without|unlike|see\b)', first):
        return None, None
    rule, proof = SPECS[normalized]
    if not proof.search(first): return None, None
    return deepcopy(rule), {'family': 'verified_owned_long_tail', 'definition': text[:600], 'passage': raw[:900], 'matched_passage': first}
