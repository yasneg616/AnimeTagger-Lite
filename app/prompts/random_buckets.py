"""Fine-grained random-prompt buckets for local tag-library sampling."""

from __future__ import annotations

from enum import Enum

from app.inference.model_loader import TagCategory
from app.prompts.normalizer import canonical_tag_key


class RandomBucket(str, Enum):
    CHARACTER = "character"
    COPYRIGHT = "copyright"
    HAIR = "hair"
    BODY = "body"
    CLOTHING = "clothing"
    ITEMS = "items"
    POSE = "pose"
    BACKGROUND = "background"
    NSFW = "nsfw"
    OTHER = "other"


BUCKET_LABELS: dict[RandomBucket, str] = {
    RandomBucket.CHARACTER: "角色",
    RandomBucket.COPYRIGHT: "作品",
    RandomBucket.HAIR: "发型发色",
    RandomBucket.BODY: "身体",
    RandomBucket.CLOTHING: "服饰",
    RandomBucket.ITEMS: "物品",
    RandomBucket.POSE: "姿势表情",
    RandomBucket.BACKGROUND: "背景",
    RandomBucket.NSFW: "NSFW",
    RandomBucket.OTHER: "其他",
}


_NSFW_EXACT = frozenset(
    canonical_tag_key(x)
    for x in (
        "nude",
        "naked",
        "nsfw",
        "sex",
        "intercourse",
        "vaginal",
        "anal",
        "oral",
        "blowjob",
        "handjob",
        "paizuri",
        "cunnilingus",
        "fellatio",
        "masturbation",
        "orgasm",
        "cum",
        "creampie",
        "facial",
        "pussy",
        "vagina",
        "penis",
        "testicles",
        "nipples",
        "erect_nipples",
        "areolae",
        "topless",
        "bottomless",
        "pubic_hair",
        "hairy_pussy",
        "spread_legs",
        "legs_apart",
        "ahegao",
        "bondage",
        "shibari",
        "gag",
        "hanging_breasts",
        "cum_in_pussy",
        "cum_on_body",
        "cum_on_face",
        "uncensored",
    )
)
_NSFW_CONTAINS = (
    "nude",
    "naked",
    "sex",
    "pussy",
    "penis",
    "nipple",
    "cum",
    "orgasm",
    "bondage",
    "ahegao",
    "rape",
    "tentacle",
    "hentai",
    "masturb",
    "ejaculat",
    "semen",
    "vagina",
    "clitoris",
    "areola",
    "areolae",
)

_CLOTHING_EXACT = frozenset(
    canonical_tag_key(x)
    for x in (
        "clothed",
        "clothes",
        "dress",
        "shirt",
        "skirt",
        "school_uniform",
        "jacket",
        "coat",
        "swimsuit",
        "armor",
        "bikini",
        "lingerie",
        "panties",
        "bra",
        "underwear",
        "thighhighs",
        "kneehighs",
        "socks",
        "stockings",
        "gloves",
        "boots",
        "shoes",
        "pants",
        "shorts",
        "hoodie",
        "sweater",
        "cardigan",
        "vest",
        "tie",
        "bowtie",
        "serafuku",
        "sailor_collar",
        "maid_headdress",
        "apron",
        "cape",
        "cloak",
        "kimono",
        "yukata",
        "cheongsam",
        "leotard",
        "bodysuit",
        "miniskirt",
        "pleated_skirt",
        "denim",
        "cargo_pants",
        "sweatpants",
        "overalls",
        "labcoat",
        "tracksuit",
        "gym_uniform",
        "bikini_top",
        "bikini_bottom",
        "micro_bikini",
        "one-piece_swimsuit",
        "school_swimsuit",
        "wet_clothes",
        "off_shoulder",
        "bare_shoulders",
        "detached_sleeves",
        "sleeves_past_wrists",
        "long_skirt",
        "pencil_skirt",
        "compression_shorts",
        "hot_pants",
        "pantyhose",
        "zettai_ryouiki",
        "belt",
        "sash",
        "bandana",
        "headwear",
    )
)
_CLOTHING_SUFFIXES = (
    " dress",
    " shirt",
    " skirt",
    " uniform",
    " swimsuit",
    " jacket",
    " coat",
    " panties",
    " bra",
    " boots",
    " shoes",
    " gloves",
    " socks",
    " stockings",
    " thighhighs",
    " sleeves",
    " collar",
    " hood",
    " hatband",
    " bikini",
    " lingerie",
    " armor",
    " pants",
    " shorts",
    " sweater",
    " hoodie",
    " kimono",
    " costume",
    " outfit",
    " clothes",
    " wear",
    " sleeves",
)

_ITEMS_EXACT = frozenset(
    canonical_tag_key(x)
    for x in (
        "hat",
        "beret",
        "cap",
        "glasses",
        "sunglasses",
        "ribbon",
        "hair_ribbon",
        "hairband",
        "hair_ornament",
        "hairpin",
        "headphones",
        "earrings",
        "necklace",
        "choker",
        "bracelet",
        "watch",
        "ring",
        "bag",
        "backpack",
        "handbag",
        "weapon",
        "sword",
        "katana",
        "gun",
        "rifle",
        "pistol",
        "staff",
        "wand",
        "shield",
        "book",
        "phone",
        "smartphone",
        "umbrella",
        "parasol",
        "flower",
        "rose",
        "crown",
        "tiara",
        "halo",
        "wings",
        "tail",
        "cat_ears",
        "animal_ears",
        "maid_headdress",
        "cane",
        "scythe",
        "bow",
        "arrow",
        "lollipop",
        "candy",
        "food",
        "cake",
        "ice_cream",
        "cup",
        "teacup",
        "chair",
        "table",
        "bed",
        "pillow",
        "blanket",
        "teddy_bear",
        "plush",
        "musical_note",
        "guitar",
        "piano",
        "microphone",
        "lantern",
        "candle",
        "mirror",
        "camera",
        "hat_ornament",
    )
)
_ITEMS_SUFFIXES = (
    " hat",
    " glasses",
    " ribbon",
    " ornament",
    " earrings",
    " necklace",
    " bag",
    " sword",
    " gun",
    " book",
    " flower",
    " wings",
    " ears",
    " weapon",
    " accessory",
    " jewelry",
    " headwear",
)

_BACKGROUND_EXACT = frozenset(
    canonical_tag_key(x)
    for x in (
        "background",
        "simple_background",
        "white_background",
        "grey_background",
        "black_background",
        "blurred_background",
        "scenery",
        "outdoors",
        "indoors",
        "sky",
        "cloudy_sky",
        "starry_sky",
        "night_sky",
        "sunset",
        "sunrise",
        "night",
        "day",
        "beach",
        "ocean",
        "sea",
        "river",
        "lake",
        "mountain",
        "forest",
        "woods",
        "field",
        "flower_field",
        "grass",
        "city",
        "street",
        "rooftop",
        "building",
        "classroom",
        "library",
        "cafe",
        "restaurant",
        "bedroom",
        "bathroom",
        "kitchen",
        "onsen",
        "shrine",
        "temple",
        "castle",
        "ruins",
        "space",
        "underwater",
        "rain",
        "snow",
        "cherry_blossoms",
        "fallen_leaves",
        "window",
        "curtain",
        "indoors",
    )
)
_BACKGROUND_SUFFIXES = (
    " background",
    " scenery",
    " sky",
    " beach",
    " field",
    " room",
    " street",
    " city",
    " forest",
    " indoors",
    " outdoors",
)

_HAIR_EXACT = frozenset(
    canonical_tag_key(x)
    for x in (
        "hair",
        "long_hair",
        "short_hair",
        "medium_hair",
        "very_long_hair",
        "absurdly_long_hair",
        "twintails",
        "ponytail",
        "side_ponytail",
        "braid",
        "braids",
        "twin_braids",
        "bangs",
        "blunt_bangs",
        "swept_bangs",
        "parted_bangs",
        "ahoge",
        "sidelocks",
        "hair_between_eyes",
        "hair_over_one_eye",
        "hair_over_eyes",
        "bob_cut",
        "pixie_cut",
        "drill_hair",
        "flipped_hair",
        "messy_hair",
        "wet_hair",
        "hair_flower",
        "multicolored_hair",
        "two-tone_hair",
        "gradient_hair",
        "streaked_hair",
        "colored_inner_hair",
    )
)
_HAIR_SUFFIXES = (
    " hair",
    " eyes",  # eye color often grouped with hair in prompts; keep under hair/body later
    " twintails",
    " ponytail",
    " braids",
    " bangs",
)

_BODY_EXACT = frozenset(
    canonical_tag_key(x)
    for x in (
        "breasts",
        "small_breasts",
        "medium_breasts",
        "large_breasts",
        "huge_breasts",
        "flat_chest",
        "navel",
        "midriff",
        "abs",
        "muscular",
        "muscles",
        "pale_skin",
        "dark_skin",
        "tan",
        "fair_skin",
        "mole",
        "freckles",
        "pointy_ears",
        "fang",
        "fangs",
        "heterochromia",
        "makeup",
        "lips",
        "teeth",
        "tongue",
        "bare_legs",
        "bare_feet",
        "bare_arms",
        "bare_shoulders",
        "collarbone",
        "armpits",
        "wide_hips",
        "slim",
        "petite",
        "tall",
        "short",
        "child",
        "loli",
        "shota",
        "mature_female",
        "milf",
        "gyaru",
        "tomboy",
        "crossdressing",
    )
)
_BODY_SUFFIXES = (
    " eyes",
    " skin",
    " breasts",
    " hair_length",
)

_POSE_EXACT = frozenset(
    canonical_tag_key(x)
    for x in (
        "standing",
        "sitting",
        "lying",
        "walking",
        "running",
        "jumping",
        "holding",
        "arms_up",
        "arms_behind_back",
        "hand_on_own_hip",
        "hand_up",
        "waving",
        "pointing",
        "covering_face",
        "hand_to_mouth",
        "chin_rest",
        "head_tilt",
        "looking_at_viewer",
        "looking_away",
        "looking_back",
        "looking_up",
        "looking_down",
        "eyes_closed",
        "one_eye_closed",
        "wink",
        "smile",
        "grin",
        "frown",
        "crying",
        "tears",
        "angry",
        "sad",
        "surprised",
        "embarrassed",
        "blush",
        "open_mouth",
        "closed_mouth",
        "pout",
        "sigh",
        "upper_body",
        "lower_body",
        "full_body",
        "cowboy_shot",
        "portrait",
        "close-up",
        "from_above",
        "from_below",
        "from_side",
        "from_behind",
        "pov",
        "depth_of_field",
        "foreshortening",
        "dynamic_angle",
        "profile",
        "contrapposto",
        "arched_back",
        "on_back",
        "on_stomach",
        "on_side",
        "kneeling",
        "crouching",
        "squatting",
        "leaning",
        "against_wall",
        "solo_focus",
    )
)
_POSE_SUFFIXES = (
    " shot",
    " view",
    " angle",
    " pose",
)

# eye colors stay in body via suffix; remove hair eyes suffix conflict
_HAIR_SUFFIXES = tuple(s for s in _HAIR_SUFFIXES if s != " eyes")


def _has_token(key: str, token: str) -> bool:
    return key == token or f" {token}" in key or key.startswith(f"{token} ") or f" {token} " in f" {key} "


def _matches_suffix(key: str, suffixes: tuple[str, ...]) -> bool:
    for suffix in suffixes:
        token = suffix.strip()
        if key == token or key.endswith(f" {token}"):
            return True
    return False


def _contains_any(key: str, needles: tuple[str, ...]) -> bool:
    return any(needle in key for needle in needles)


def classify_random_bucket(name: str, model_category: TagCategory) -> RandomBucket:
    """Map a library tag to a fine-grained random bucket."""

    if model_category is TagCategory.CHARACTER:
        return RandomBucket.CHARACTER
    if model_category is TagCategory.COPYRIGHT:
        return RandomBucket.COPYRIGHT
    if model_category is not TagCategory.GENERAL:
        return RandomBucket.OTHER

    key = canonical_tag_key(name)
    if not key:
        return RandomBucket.OTHER

    if key in _NSFW_EXACT or _contains_any(key, _NSFW_CONTAINS):
        return RandomBucket.NSFW
    if key in _CLOTHING_EXACT or _matches_suffix(key, _CLOTHING_SUFFIXES):
        return RandomBucket.CLOTHING
    if key in _ITEMS_EXACT or _matches_suffix(key, _ITEMS_SUFFIXES):
        return RandomBucket.ITEMS
    if key in _BACKGROUND_EXACT or _matches_suffix(key, _BACKGROUND_SUFFIXES):
        return RandomBucket.BACKGROUND
    if key in _HAIR_EXACT or _matches_suffix(key, _HAIR_SUFFIXES):
        return RandomBucket.HAIR
    if key in _POSE_EXACT or _matches_suffix(key, _POSE_SUFFIXES):
        return RandomBucket.POSE
    if key in _BODY_EXACT or _matches_suffix(key, _BODY_SUFFIXES):
        return RandomBucket.BODY
    return RandomBucket.OTHER
