"""Reviewed semantic primitives. A broad tag bucket is never a constraint."""
from __future__ import annotations

from app.prompts.normalizer import canonical_tag_key

THEMES = {
    "daily": "日常", "city": "都市", "nature": "自然", "fantasy": "奇幻",
    "science_fiction": "科幻", "beach": "海边", "formal": "正式场合",
}
SLOT_SCOPE = {
    **{slot: "actor" for slot in ("hair.color", "hair.length", "hair.style", "hair.texture", "hair.detail", "eyes.color", "eyes.state", "skin.color", "outfit", "top", "bottom", "outerwear", "footwear", "legwear", "handwear", "headwear", "accessory", "posture", "action", "expression", "gaze", "mouth", "body.detail", "body.breast_size", "clothing.detail", "coverage")},
    **{slot: "scene" for slot in ("location", "environment", "time", "weather", "lighting", "framing", "view", "style", "scene.detail")},
    "object": "object", "interaction": "relation", "count": "scene",
}
SLOT_SCOPE.update({slot: "actor" for slot in (
    "underwear", "underwear.top", "underwear.bottom", "body.ears", "body.wings", "body.tail", "body.horns",
    "body.shape", "eyes.detail", "face.detail", "clothing.pattern", "clothing.sleeves", "clothing.collar",
    "clothing.trim", "clothing.material", "clothing.exposure", "body.visible", "hands.pose", "legs.pose",
    "hair.bangs", "hair.sidelocks", "body.halo", "body.nails", "body.species",
    "placement", "body.role",
)})
SLOT_SCOPE.update({slot: "scene" for slot in ("background", "border", "symbol", "text", "focus", "effect")})
SINGLE_SLOTS = frozenset(SLOT_SCOPE) - {
    "accessory", "body.detail", "clothing.detail", "hair.detail", "object", "scene.detail", "style", "count", "action", "interaction",
    "body.ears", "body.wings", "body.tail", "body.horns", "body.shape", "eyes.detail", "face.detail", "clothing.pattern",
    "clothing.trim", "body.visible", "hands.pose", "legs.pose", "body.halo", "body.nails", "symbol", "text", "effect", "border",
    "background", "clothing.sleeves", "clothing.collar", "clothing.material", "clothing.exposure",
    "placement", "body.role",
}


def key(name):
    return canonical_tag_key(name)


def primitive(name, slot, *, phrase=None, themes=(), requires=(), excludes=(), provides=(), adult=False, actors=1):
    return {"slot": slot, "scope": SLOT_SCOPE[slot], "phrase": phrase or key(name),
            "themes": list(themes), "requires": list(requires), "excludes": list(excludes),
            "provides": list(provides), "adult": adult, "min_actors": actors}


REVIEWED = {}


def add(names, slot, **kwargs):
    for name in names.split("|"):
        REVIEWED[key(name)] = primitive(name, slot, **kwargs)


COLORS = "black white red blue green yellow pink purple brown orange grey silver aqua blonde lavender".split()
for color in COLORS:
    add(color + "_hair", "hair.color")
    if color not in {"blonde", "lavender", "silver"}:
        add(color + "_eyes", "eyes.color")
add("short_hair|medium_hair|long_hair|very_long_hair|absurdly_long_hair", "hair.length")
add("multicolored_hair|two-tone_hair|gradient_hair", "hair.color", provides=("multicolor_hair",))
add("heterochromia", "eyes.color", provides=("multicolor_eyes",))
add("ponytail|twintails|braid|twin_braids|hair_bun|double_bun|bob_cut|pixie_cut", "hair.style")
add("straight_hair|wavy_hair|curly_hair", "hair.texture")
add("pale_skin|dark_skin|tan|dark-skinned_female|dark-skinned_male", "skin.color")
add("smile|grin|frown|surprised|angry|crying|expressionless|pout", "expression")
add("looking_at_viewer|looking_away|looking_up|looking_down|looking_to_the_side|looking_back", "gaze")
add("open_mouth|closed_mouth", "mouth")
add("standing|sitting|lying|kneeling|crouching|squatting", "posture")
add("walking|running", "action", excludes=("posture:sitting", "posture:lying", "posture:kneeling", "posture:crouching", "posture:squatting"))
add("reading", "action", requires=("object:book",), excludes=("action:running",))
add("holding_umbrella", "action", phrase="holding an umbrella", requires=("object:umbrella",))
add("holding_book", "action", phrase="holding a book", requires=("object:book",))
add("holding_sword", "action", phrase="holding a sword", requires=("object:sword",), themes=("fantasy",))
add("waving|arms_up|hand_on_own_hip|arms_behind_back", "action")
add("holding_hands|hug|kissing|talking", "interaction", actors=2)
add("indoors", "environment", provides=("indoor",))
add("outdoors", "environment", provides=("outdoor",))
for name, themes, environment in (
    ("cafe", ("daily", "city"), "indoors"), ("library", ("daily",), "indoors"),
    ("bedroom", ("daily",), "indoors"), ("classroom", ("daily",), "indoors"),
    ("kitchen", ("daily",), "indoors"), ("street", ("city", "daily"), "outdoors"),
    ("city", ("city", "science_fiction"), "outdoors"), ("forest", ("nature", "fantasy"), "outdoors"),
    ("beach", ("beach", "nature"), "outdoors"), ("flower_field", ("nature",), "outdoors"),
    ("castle", ("fantasy", "formal"), "outdoors"), ("ruins", ("fantasy",), "outdoors"),
    ("rooftop", ("city",), "outdoors"),
):
    add(name, "location", themes=themes, requires=("environment:" + environment,))
add("day|night|sunset|sunrise", "time")
add("rain|snow", "weather", requires=("environment:outdoors",))
add("sunlight", "lighting", excludes=("time:night",))
add("moonlight", "lighting", excludes=("time:day", "time:sunrise"))
add("backlighting|soft_lighting|rim_lighting|dramatic_lighting", "lighting")
add("full_body|upper_body|cowboy_shot|close-up", "framing")
add("from_above|from_below|from_side|from_behind", "view")
add("anime_coloring|watercolor|sketch|lineart|monochrome", "style")
add("book|cup|teacup|phone|smartphone|bag|backpack", "object", themes=("daily", "city"))
add("umbrella", "object", themes=("daily", "city"))
add("sword|staff|shield|wand", "object", themes=("fantasy",))
add("flower|basket", "object", themes=("nature",))
add("hat|glasses|earrings|necklace|hair_ribbon|hair_ornament|choker", "accessory")
add("blush|freckles|mole|pointy_ears|fangs", "body.detail")
add("dress|school_uniform|sailor_uniform|maid|maid_uniform|kimono|yukata|cheongsam|bodysuit|armor", "outfit")
add("swimsuit|bikini|one-piece_swimsuit", "outfit", themes=("beach",))
add("shirt|t-shirt|blouse|sweater|tank_top", "top")
add("skirt|pleated_skirt|pants|shorts|jeans", "bottom")
add("jacket|coat|cardigan|cape|cloak", "outerwear")
add("shoes|boots|sandals|sneakers|high_heels", "footwear")
add("nude", "coverage", adult=True, excludes=("slot:outfit", "slot:top", "slot:bottom", "slot:outerwear"))
add("topless", "coverage", adult=True, excludes=("slot:outfit", "slot:top", "slot:outerwear"))
add("bottomless", "coverage", adult=True, excludes=("slot:outfit", "slot:bottom"))
add("1girl|1boy|2girls|2boys|3girls|3boys|4girls|4boys|solo", "count")

# Explicitly reviewed noun and attribute families. Their public Wiki pages are
# retained as evidence by the compiler; membership in a broad group alone never
# enables a tag. Actions require their own dependency rules below.
add("hair_bow|hairclip|hair_flower|hairband|hair_tie|hair_scrunchie|hair_stick|kanzashi|bun_cover|hairpods|headband|bracelet|bangle|ring|brooch|pendant|amulet|anklet|necktie|bowtie|scarf|sash|belt|suspenders|watch|eyepatch", "accessory")
add("beret|baseball_cap|peaked_cap|flat_cap|fedora|bowler_hat|top_hat|witch_hat|sun_hat|straw_hat|bucket_hat|beanie|santa_hat|crown|tiara|helmet|headscarf|veil|hood|maid_headdress|mob_cap", "headwear")
add("socks|thighhighs|pantyhose|kneehighs|over-kneehighs|leggings|leg_warmers|ankle_socks|tabi", "legwear")
add("gloves|elbow_gloves|fingerless_gloves|half_gloves|mittens|under-elbow_gloves", "handwear")
add("blazer|hoodie|vest|sweater_vest|waistcoat|suit_jacket|trench_coat|raincoat|fur_coat|winter_coat|capelet|poncho|leather_jacket|cropped_jacket|long_coat|bomber_jacket", "outerwear")
add("crop_top|camisole|tube_top|halter_top|polo_shirt|dress_shirt|turtleneck|turtleneck_sweater|sleeveless_shirt|collared_shirt|frilled_shirt|sleeveless_turtleneck|ribbed_sweater|off-shoulder_shirt", "top")
add("miniskirt|long_skirt|pencil_skirt|plaid_skirt|suspender_skirt|high-waist_skirt|denim_shorts|short_shorts|bike_shorts|capri_pants|cargo_pants|wide-leg_pants|hakama|sarong|kilt", "bottom")
add("loafers|mary_janes|pumps|slippers|flip-flops|geta|zouri|ankle_boots|knee_boots|thigh_boots|platform_boots|platform_shoes|dress_shoes|lace-up_boots|rubber_boots|high_heel_boots|sandal_boots|ballet_slippers|high_tops", "footwear")
add("suit|business_suit|skirt_suit|pant_suit|tuxedo|wedding_dress|evening_gown|sundress|sweater_dress|jumpsuit|overalls|pajamas|nightgown|robe|hanfu|qipao|miko|nontraditional_miko|serafuku|military_uniform|naval_uniform|nurse|nurse_uniform|police_uniform|gym_uniform|cheerleader|cheerleader_uniform|tracksuit|furisode|uchikake|sailor_dress", "outfit")
add("apron|waist_apron|maid_apron|jewelry|neckerchief|ascot|neck_ribbon|wrist_cuffs|thigh_strap|thighlet|armlet|ankle_ribbon|hair_tubes|single_hair_tube|hair_bell|hair_beads|hair_bracelet|hairpin|head_chain|belly_chain|hand_chains|toe_ring|garter_belt|garter_straps", "accessory")
add("sunglasses|aviator_sunglasses|sports_sunglasses|shutter_shades|tinted_eyewear", "accessory", excludes=("accessory:glasses",))
add("undershirt|henley_shirt|baseball_shirt|hawaiian_shirt|henley|peasant_blouse|sailor_shirt|sailor_blouse", "top")
add("hot_pants|bloomers|culottes|culotte_shorts|harem_pants|sailor_pants|sweatpants|track_pants|yoga_pants|pajama_pants|bell-bottoms", "bottom")
add("shawl|mantle|tabard|haori|hanten|happi|duffel_coat|labcoat|puffer_jacket|varsity_jacket|bolero|windbreaker|sweatshirt|track_jacket", "outerwear")
add("bonnet|tokin_hat|nun_headdress|phrygian_cap|garrison_cap|military_cap|ushanka|tricorn|sailor_hat|paper_hat|party_hat|visor_cap|straw_boater", "headwear")
add("fishnet_pantyhose|fishnet_thighhighs|fishnet_socks|stirrup_legwear|stirrup_pantyhose|toeless_legwear|toeless_pantyhose|footless_pantyhose|bobby_socks", "legwear")
add("surgical_gloves|partially_fingerless_gloves|bridal_gauntlets|gauntlets|opera_gloves", "handwear")
add("tengu-geta|clogs|moccasins|espadrilles|combat_boots|wellington_boots|cowboy_boots|hiking_boots|school_shoes|roller_skates|ice_skates|cleats|ankle_strap_heels", "footwear")
add("bra|panties|lingerie|underwear|leotard|bunnysuit|babydoll", "outfit", adult=True)
add("bikini_top|sports_bra|bra_top", "top", adult=True)
add("bikini_bottom|boyshort_panties|boxers|briefs", "bottom", adult=True)
add("bald|very_short_hair", "hair.length")
REVIEWED[key("bald")]["excludes"] = ["slot:" + value for value in ("hair.color", "hair.style", "hair.texture", "hair.detail")]
REVIEWED[key("pixie_cut")]["excludes"] = ["hair.length:" + value for value in ("long_hair", "very_long_hair", "absurdly_long_hair")]
for name in ("ponytail", "twintails", "braid", "twin_braids", "hair_bun", "double_bun"):
    REVIEWED[key(name)]["excludes"] = ["hair.length:bald", "hair.length:very_short_hair"]
add("high_ponytail|low_ponytail|side_ponytail|short_ponytail|long_ponytail|low_twintails|short_twintails|side_braid|single_braid|french_braid|crown_braid|braided_ponytail|braided_bun|single_hair_bun|updo|half_updo|topknot|drill_hair|twin_drills|hime_cut|bowl_cut|buzz_cut|crew_cut|undercut|mohawk|two_side_up", "hair.style")
add("one_side_up|tri_tails|quad_tails|twin_ponytails|low_twin_braids|single_drill|sidecut|mullet|dreadlocks|cornrows", "hair.style")
add("very_long_braid", "hair.style", requires=("hair.length:very_long_hair",))
add("crossed_bangs|choppy_bangs|short_hair_with_long_locks|asymmetrical_sidelocks|single_sidelock|single_hair_intake|arched_bangs|diagonal_bangs", "hair.detail")
for name, rule in REVIEWED.items():
    if rule["slot"] == "hair.style":
        rule["excludes"] = list(dict.fromkeys([*rule["excludes"], "hair.length:bald"]))
        if name not in {"pixie cut", "buzz cut", "crew cut", "undercut", "sidecut", "mohawk"}:
            rule["excludes"].append("hair.length:very_short_hair")
for name in ("pixie_cut", "bob_cut", "bowl_cut", "buzz_cut", "crew_cut"):
    REVIEWED[key(name)]["excludes"] = list(dict.fromkeys([*REVIEWED[key(name)]["excludes"],
        *("hair.length:" + value for value in ("long_hair", "very_long_hair", "absurdly_long_hair"))]))
REVIEWED[key("short_hair_with_long_locks")]["requires"] = ["hair.length:short_hair"]
add("fluffy_hair|messy_hair|spiked_hair|ringlets|flipped_hair", "hair.texture")
add("bangs|blunt_bangs|parted_bangs|swept_bangs|asymmetrical_bangs|double-parted_bangs|hair_intakes|hair_flaps|sidelocks|ahoge|antenna_hair|cowlick|hair_between_eyes|hair_over_one_eye|hair_behind_ear|hair_over_shoulder|hair_spread_out|loose_hair_strand", "hair.detail")
add("streaked_hair|split-color_hair|colored_inner_hair|rainbow_hair", "hair.color", provides=("multicolor_hair",))
add("closed_eyes", "eyes.state", phrase="closed", excludes=tuple("gaze:" + tag for tag in ("looking_at_viewer", "looking_away", "looking_up", "looking_down", "looking_to_the_side", "looking_back")))
add("one_eye_closed|half-closed_eyes|unusually_open_eyes", "eyes.state")
add("flat_chest|small_breasts|medium_breasts|large_breasts|huge_breasts", "body.breast_size")
add("elf_ears|cat_ears|dog_ears|fox_ears|rabbit_ears|wolf_ears|horse_ears|animal_ears|horns|demon_horns|wings|feathered_wings|demon_wings|tail|cat_tail|fox_tail|demon_tail|long_fingernails|sharp_fingernails|facial_hair|beard|mustache|stubble|mole_under_eye|mole_under_mouth|scar|scar_on_face|facial_mark|eyelashes|long_eyelashes|thick_eyebrows|thin_eyebrows|white_pupils|slit_pupils|red_pupils", "body.detail")
add("happy|sad|embarrassed|nervous|serious|sleepy|scared|excited|smug|confused|bored|annoyed|disgust|laughing|sobbing|tears|wince|evil_smile|gentle_smile", "expression")
add("looking_afar|looking_at_sky|looking_at_ground", "gaze")
add("own_hands_clasped|crossed_arms|arms_at_sides|arm_up|hand_up|hands_up|salute|reaching|shrugging|pointing|pointing_up|pointing_at_viewer|head_tilt|head_down|head_back", "action")
add("on_back|on_side|on_stomach", "posture", requires=("posture:lying",))
add("seiza|wariza|yokozuwari|indian_style|lotus_position|butterfly_sitting|figure_four_sitting", "posture", requires=("posture:sitting",))
add("on_one_knee", "posture", requires=("posture:kneeling",))
add("back-to-back|face-to-face|eye_contact|cheek-to-cheek|forehead-to-forehead|shoulder-to-shoulder|locked_arms", "interaction", actors=2)
add("group_hug", "interaction", phrase="hugging each other as a group", actors=3)
add("park|garden|courtyard|river|lake|mountain|hill|meadow|desert|cliff|canyon|waterfall|cave|bamboo_forest|town|road|alley|bridge|harbor|dock|pier|playground|stadium|field|farm", "location", requires=("environment:outdoors",), themes=("nature", "city"))
add("office|living_room|dining_room|bathroom|hallway|corridor|shop|restaurant|bar|hotel_room|church|shrine|gym|laboratory|dressing_room|locker_room|stage|theater|train_interior|car_interior", "location", requires=("environment:indoors",), themes=("daily", "city"))
add("dusk|dawn", "time")
add("cloudy_sky|fog|wind|snowing|raining", "weather", requires=("environment:outdoors",))
add("ambient_light|diffused_lighting|dappled_sunlight|spotlight|chiaroscuro|lens_flare|bloom", "lighting")
add("portrait|bust|wide_shot", "framing")
add("front_view|side_view|rear_view|bird's-eye_view|dutch_angle", "view")
add("realistic|photorealistic|oil_painting|pencil_drawing|traditional_media|digital_media|ink|pixel_art|cel_shading|flat_color|greyscale|sepia|silhouette|comic|illustration", "style")
add("table|chair|stool|bench|desk|sofa|armchair|bed|pillow|blanket|curtains|mirror|clock|vase|lamp|candle|lantern|flashlight|bottle|glass|wine_glass|mug|plate|bowl|spoon|fork|knife|chopsticks|teapot|tray|lunch_box|water_bottle|thermos|paper|notebook|pen|pencil|paintbrush|palette|paint_bucket|camera|video_camera|microphone|megaphone|headphones|earphones|computer|laptop|tablet_pc|keyboard|computer_mouse|monitor|television|remote_control|game_controller|handheld_game_console|wallet|purse|handbag|suitcase|briefcase|basket|box|sack|shopping_bag|key|envelope|letter|newspaper|magazine|map|scroll|bookmark|toy|teddy_bear|stuffed_toy|doll|ball|soccer_ball|basketball|tennis_racket|baseball_bat|bicycle|skateboard|guitar|violin|flute|piano|drum|trumpet|broom|bucket|watering_can|shovel|rake|comb|hair_brush|hair_dryer|lipstick|compact|handkerchief|tissue|rope|chain|fan|hand_fan|folding_fan|parasol|bell|gift|gift_box|present|ribbon|bow|food|fruit|apple|banana|orange_(fruit)|lemon|strawberry|cherry|grapes|watermelon|peach|cake|cupcake|bread|cookie|chocolate|candy|lollipop|ice_cream|sandwich|burger|pizza|rice|onigiri|bento|noodles|ramen|sushi|drink|coffee|tea|juice|milk|rose|sunflower|tulip|lily|bouquet|leaf|branch|acorn|pinecone|mushroom|shell|seashell|stone|gem|crystal|feather|katana|dagger|rapier|scythe|axe|hammer|spear|lance|halberd|trident|mace|bow_(weapon)|crossbow|gun|pistol|rifle|shotgun|revolver|lightsaber|magic_wand|magic_staff", "object")

MODIFIERS = COLORS + "gold golden beige cream tan violet magenta cyan maroon navy teal dark-blue light-blue dark-green light-green light-brown dark-brown striped vertical-striped horizontal-striped diagonal-striped plaid polka-dot frilled lace-trimmed ribbon-trimmed fur-trimmed checkered floral print sleeveless long-sleeved short-sleeved off-shoulder collared turtleneck leather denim satin silk knitted ribbed hooded cable-knit torn dirty wet transparent see-through open unbuttoned unzipped oversized loose tight highleg lowleg strapless backless halterneck asymmetrical pleated layered two-tone multicolored white-frilled black-frilled short long cropped high-waist low-waist buttoned double-breasted single-breasted pinstriped argyle gingham gingham-check".split()
# A held object and a worn garment are separate facts, even when their nouns
# coincide. Only object primitives are eligible for this action composition.
for name, rule in tuple(REVIEWED.items()):
    if rule["scope"] == "object":
        label = "holding " + name
        mass = {"food", "fruit", "coffee", "tea", "juice", "milk", "rice", "ramen", "sushi", "ribbon", "paper", "rope", "chain", "ice cream"}
        plural = {"curtains", "headphones", "earphones", "chopsticks", "grapes", "noodles"}
        noun = name if name in mass | plural else ("an " if name[:1] in "aeiou" else "a ") + name
        REVIEWED[label] = primitive(label, "action", phrase="holding " + noun,
                                    requires=("object:" + name,), themes=rule["themes"], adult=rule["adult"])

# Controlled English clauses express exactly the fact represented by a tag.
CLAUSES = {
    "smile": "a smile", "grin": "a grin", "frown": "a frown", "pout": "a pout",
    "surprised": "surprised", "angry": "angry", "crying": "tearful", "expressionless": "neutral",
    "open_mouth": "open", "closed_mouth": "closed", "arms_up": "raising both arms",
    "hand_on_own_hip": "resting a hand on their own hip", "arms_behind_back": "keeping their arms behind their back",
    "holding_hands": "holding hands", "hug": "hugging each other", "kissing": "kissing each other", "talking": "talking to each other",
    "looking_at_viewer": "looking at the viewer", "maid": "a maid uniform",
    "ponytail": "a ponytail", "twintails": "twintails", "braid": "a braid", "twin_braids": "twin braids",
    "hair_bun": "a hair bun", "double_bun": "two hair buns", "bob_cut": "a bob haircut", "pixie_cut": "a pixie haircut",
    "on_back": "lying on their back", "on_side": "lying on their side", "on_stomach": "lying on their stomach",
    "on_one_knee": "kneeling on one knee", "seiza": "sitting in seiza", "wariza": "sitting with the legs folded to either side",
    "yokozuwari": "sitting with both legs folded to one side", "indian_style": "sitting cross-legged", "lotus_position": "sitting in the lotus position",
    "butterfly_sitting": "sitting with the soles of the feet together", "figure_four_sitting": "sitting with one ankle over the opposite knee",
    "closed_eyes": "closed", "one_eye_closed": "partly closed, with one eye shut", "half-closed_eyes": "half closed", "unusually_open_eyes": "unusually wide open",
    "bald": "a bald head", "salute": "saluting", "arm_up": "raising one arm", "hand_up": "raising one hand", "hands_up": "raising both hands",
    "head_tilt": "tilting their head", "head_down": "lowering their head", "head_back": "tilting their head back", "own_hands_clasped": "clasping their own hands",
    "crossed_arms": "crossing their arms", "arms_at_sides": "keeping their arms at their sides", "tears": "tearful", "laughing": "amused", "sobbing": "tearful",
    "looking_afar": "looking into the distance", "looking_at_sky": "looking at the sky", "looking_at_ground": "looking at the ground",
    "dutch_angle": "a Dutch angle", "from_above": "a view from above", "from_below": "a view from below", "from_side": "a side view", "from_behind": "a view from behind",
    "evil_smile": "a sinister smile", "gentle_smile": "a gentle smile", "disgust": "disgusted", "wince": "a wince",
}
for name, phrase in CLAUSES.items():
    if key(name) in REVIEWED:
        REVIEWED[key(name)]["phrase"] = phrase
for name in ("miko", "nontraditional_miko", "nurse", "cheerleader"):
    REVIEWED[key(name)]["phrase"] = {"miko": "a shrine maiden outfit", "nontraditional_miko": "a nontraditional shrine maiden outfit", "nurse": "a nurse uniform", "cheerleader": "a cheerleader uniform"}[name]
for name in ("kimono", "yukata", "cheongsam", "armor", "cape", "cloak"):
    REVIEWED[key(name)]["themes"] = ["fantasy", "formal"]
for name in ("school_uniform", "sailor_uniform", "maid", "maid_uniform", "dress", "shirt", "skirt", "pants", "jacket"):
    REVIEWED[key(name)]["themes"] = ["daily", "city"]
for name in ("suit", "business_suit", "skirt_suit", "pant_suit", "tuxedo", "wedding_dress", "evening_gown"):
    REVIEWED[key(name)]["themes"] = ["formal", "city"]
for name in ("pajamas", "nightgown", "robe", "sundress", "jumpsuit", "overalls", "tracksuit"):
    REVIEWED[key(name)]["themes"] = ["daily"]
for name in ("military_uniform", "naval_uniform", "miko", "nontraditional_miko", "hanfu", "qipao", "furisode", "uchikake"):
    REVIEWED[key(name)]["themes"] = ["fantasy", "formal"]
for name in ("park", "garden", "courtyard", "farm", "field", "playground"):
    REVIEWED[key(name)]["themes"] = ["nature", "daily"]
for name in ("river", "lake", "mountain", "hill", "meadow", "desert", "cliff", "canyon", "waterfall", "cave", "bamboo_forest"):
    REVIEWED[key(name)]["themes"] = ["nature", "fantasy"]
for name in ("town", "road", "alley", "bridge", "harbor", "dock", "pier", "stadium"):
    REVIEWED[key(name)]["themes"] = ["city", "daily"]

# These independent attributes have implication-compatible meanings.
LENGTH_LEVELS = {key(name): level for level, name in enumerate(("short_hair", "medium_hair", "long_hair", "very_long_hair", "absurdly_long_hair"))}
NSFW_WORDS = frozenset("nude naked topless bottomless sex intercourse penis pussy vagina nipples areolae cum semen ejaculation orgasm blowjob fellatio cunnilingus masturbation paizuri anal vaginal penetration hentai rape bondage ahegao creampie incest loli shota child toddler baby".split())


def infer_composition(name):
    """Only compose a fully known modifier and a reviewed head, never substrings."""
    normalized = key(name)
    if normalized in REVIEWED:
        return dict(REVIEWED[normalized]), "reviewed_primitive"
    for modifier in MODIFIERS:
        prefix = modifier + " "
        if normalized.startswith(prefix):
            head = normalized[len(prefix):]
            head_rule, _ = infer_composition(head)
            if head_rule and head_rule["slot"] in {"top", "bottom", "outfit", "outerwear", "footwear", "headwear", "handwear", "legwear", "accessory", "object"}:
                result = dict(head_rule)
                result["phrase"] = normalized
                result["head"] = result.get("head", head)
                if modifier in {"transparent", "see-through"} and result["slot"] in {"top", "bottom", "outfit"}:
                    result["adult"] = True
                return result, "reviewed_modifier_composition"
    return None, "unreviewed"


def is_adult_term(name):
    return bool(set(key(name).replace("-", " ").split()) & NSFW_WORDS)
