"""Species-feature traits defined by a positive "girl/boy with X features" passage.

A tag such as ``bat_girl`` is usable only when its own Wiki introduction states
that the subject *has traits of* a species: a bat girl is a girl with bat
features, not a bat. That construction establishes a bodily trait owned by the
subject, which maps to ``body.species`` with no object dependency and no age
claim. Pages that state the subject *is* the creature ("A female ghost"), or
that only relate the tag to another tag, deliberately stay in the work queue.

The species word must also be a species this catalog can already express, so a
loose prose match cannot invent a new trait. Nothing here relaxes an age,
identity or content constraint.
"""
from __future__ import annotations

import re

from app.prompts.normalizer import canonical_tag_key as key
from app.prompts.semantic_rules import primitive
from scripts.prompt_semantic_families import ADULT, UNRESOLVED, definition, plain

# Species already represented by a reviewed trait or object rule. A definition
# naming anything outside this set is left unmodelled rather than guessed at.
# Multi-word species are listed separately because the single-word block is
# whitespace-split and would break them into unrelated words.
KNOWN_SPECIES = frozenset(
    """
    ant ape arachnid arthropod badger bat bear bee beetle bird boar bovine bug
    bull butterfly camel canine capybara caracal cat caterpillar cattle centipede
    centaur chameleon cheetah chicken chipmunk cobra cockroach condor coral cougar
    cow coyote crab crane cricket crocodile crow crustacean cuttlefish deer
    dinosaur dog dolphin donkey dove dragon dragonfly duck eagle eel elephant
    elk falcon ferret finch fish flamingo fly fox frog gazelle gecko gerbil
    gibbon giraffe goat goldfish goose gorilla grasshopper griffin gryphon guinea
    pig hamster hare harpy hawk hedgehog heron hippopotamus horse hound hummingbird
    hyena iguana insect insectoid invertebrate jackal jaguar jellyfish kangaroo
    killifish kingfisher kite kitten koala komainu koi ladybug ladybird lamb
    lamprey lemur leopard leviathan lion lizard llama lobster locust loris lynx
    macaque macaw magpie mammal mammoth mandrill mantis marmot marsupial mink
    minotaur mite mockingbird mole mongoose monkey moose moth mouse mule mussel
    mustelid narwhal newt ocelot octopus opossum orangutan orca ostrich otter owl
    oyster panda pangolin panther papillon parakeet parrot peacock pegasus pelican
    penguin pheasant pig pigeon piranha platypus pony porcupine porpoise possum
    prawn primate pteranodon pterodactyl pterosaur puffin puma python quail rabbit
    raccoon ram raven ray reindeer reptile rhinoceros robin rodent rooster
    salamander salmon saurian scallop scorpion seagull seahorse seal serpent shark
    sheep shrew shrimp skunk sloth slug snail snake spaniel sparrow spider sponge
    squid squirrel stag starfish stoat stork swallow swan swift swordfish tapir
    termite tiger toad tortoise toucan trout tuna turkey turtle unicorn urchin
    velociraptor vulture walrus warbler wasp weasel whale wolf wolverine wombat
    woodpecker worm wren yak zebra
    """.split()
)

# Multi-word species are named as whole units; the single-word block above is
# whitespace-split, so these cannot live in it.
MULTIWORD_SPECIES = (
    "snow leopard",
    "red panda",
    "sea lion",
    "guinea pig",
    "polar bear",
    "saber-toothed tiger",
    "humpback whale",
    "killer whale",
    "great white shark",
    "hammerhead shark",
    "flying squirrel",
    "tasmanian devil",
    "bald eagle",
    "barn owl",
    "snowy owl",
    "peregrine falcon",
)
KNOWN_SPECIES |= frozenset(MULTIWORD_SPECIES)

# A broad taxonomic tag may use a more specific example in its own definition.
# A different, unrelated species cannot establish the tag's bodily trait.
SOURCE_TAXA = {
    'reptile': {'lizard', 'snake', 'crocodile', 'turtle', 'tortoise'},
    'bird': {'crow', 'raven', 'owl', 'eagle', 'hawk', 'sparrow'},
    'insect': {'bee', 'butterfly', 'moth', 'beetle', 'ant', 'mantis'},
    'rodent': {'mouse', 'rat', 'hamster', 'squirrel'},
    'canine': {'dog', 'wolf', 'fox'}, 'feline': {'cat', 'lion', 'tiger', 'leopard'},
    'arthropod': {'spider', 'scorpion', 'insect', 'crab', 'shrimp', 'centipede'},
}
KNOWN_SPECIES |= frozenset(SOURCE_TAXA)

SUBJECT = r"(?:girl|boy|woman|man|female|male|lady|guy|person|character|individual)"

FEATURE = (
    r"(?:features|traits|characteristics|characteristcs|qualities|attributes|"
    r"appearance|physique|biology|anatomy|body parts|parts|limbs|appendages)"
)

# The subject of a positive species-trait definition, optionally qualified by
# "human/monster/birdlike". The leading qualifier is not what the subject is:
# "a fish-like monster girl" is still a girl.
SUBJECT_PHRASE = (
    r"(?:(?:male|female|young|adult|teenage|elderly|old|human|monster|birdlike|"
    r"bipedal|fish-?like|animal|beast|demi[- ]?human|insectoid|humanoid)\s+)*"
    r"(?P<subject>" + SUBJECT + r")s?"
)

# What the subject stands in relation to a species: it is stated to own a
# bodily trait of that species, not to be that species.
POSSESS = r"(?:with|possessing|having|featuring|displaying|bearing|that\s+(?:has|have)|who\s+(?:has|have|possesses?)|,\s*possessing)"

QUALIFIER = r"(?:the|some|a|an|real|intrinsic|distinct|prominent|strong|minor|slight|several|various|numerous)"

SPECIES = r"[a-z][a-z '-]{1,24}?"

# A species may be named with its colour, as in "black panther-like features".
# Only a colour this catalog already knows can precede the species word.
COLOR_WORD = (
    r"(?:aqua|black|blue|brown|green|grey|gray|orange|pink|purple|red|white|"
    r"yellow|blonde|silver|gold|golden|beige|cream|tan|cyan|teal|magenta|maroon|"
    r"navy|violet|lavender|indigo|turquoise|platinum|dark|light)\s+"
)
COLORED_SPECIES = r"(?:(?:" + COLOR_WORD + r")?" + SPECIES + r")"

# "A girl with bat features", "A boy possessing hyena traits",
# "A male who has some features of a dragon", "Girls with intrinsic mouse features".
PATTERN = re.compile(
    r"^(?:an?|the|some|numerous|various)?\s*" + SUBJECT_PHRASE + r"\s*"
    r"(?:" + POSSESS + r")\s+(?:" + QUALIFIER + r"\s+)*"
    r"(?:(?P<species1>" + COLORED_SPECIES + r")(?:['\u2019]s)?(?:-like|-esque|-ish)?\s+" + FEATURE +
    r"|" + FEATURE + r"\s+of\s+(?:an?\s+|the\s+)?(?P<species2>" + SPECIES + r"))"
    r"(?:\s+of\s+(?:an?\s+|the\s+)?(?P<species3>" + SPECIES + r"))?"
    r"(?=$|[\s,.;:!?()\u2019'])",
    re.I,
)

# "A spider-themed monster girl" is a girl whose theme is the species.
THEMED = re.compile(
    r"^(?:an?|the|some)?\s*(?:" + SUBJECT_PHRASE + r"\s+)?(?P<species1>" + SPECIES + r")-themed\s+"
    r"(?:(?:monster|human|animal|birdlike)\s+)*(?P<theme_subject>" + SUBJECT + r")s?\b",
    re.I,
)

FEMALE_MARKERS = frozenset("girl woman female lady sister daughter mother queen princess empress goddess widow niece aunt".split())
MALE_MARKERS = frozenset("boy man male guy brother son father king prince emperor god widower nephew uncle".split())

COLOR_WORDS = frozenset(
    "aqua black blue brown green grey gray orange pink purple red white yellow "
    "blonde silver gold golden beige cream tan cyan teal magenta maroon navy "
    "violet lavender indigo turquoise platinum dark light".split()
)

# Species whose lower body replaces the human legs, so leg-dependent facts and
# footwear are not expressible for them.
NO_LEGS = frozenset("mermaid merman merfolk lamia arachne centaur taur harpy".split())


def _species_of(name: str) -> str:
    """Species word from a '<species> girl/boy' key, or "" for any other tag.

    ``canonical_tag_key`` stores underscores as spaces, so both forms are tested.
    """
    for suffix in ("_girl", "_boy", "_female", "_male", " girl", " boy", " female", " male"):
        if name.endswith(suffix):
            return name[: -len(suffix)].replace("_", " ").strip()
    return ""


def _clean(text: str) -> str:
    """Drop parentheticals and See-Also lines without weakening the definition."""
    text = re.split(r"(?i)\bsee also\b|\n", text, maxsplit=1)[0]
    text = re.sub(r"\([^)]*\)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _gender_condition(phrase_text: str) -> str:
    words = set(re.findall(r"[a-z]+", phrase_text.lower()))
    female = bool(words & FEMALE_MARKERS)
    male = bool(words & MALE_MARKERS)
    if female and not male:
        return "gender:female"
    if male and not female:
        return "gender:male"
    return ""


def species_feature_rule(name, page):
    """Return a body.species rule backed by a positive species-trait passage."""
    normalized = key(name)
    species_of_tag = _species_of(normalized)
    if not species_of_tag:
        return None, None
    raw = definition(page.get("body", ""))
    text = plain(raw)
    if not text or UNRESOLVED.search(text) or UNRESOLVED.search(normalized):
        return None, None
    passage = _clean(text)
    match = PATTERN.match(passage)
    themed = False
    if not match:
        match = THEMED.match(passage)
        themed = bool(match)
    if not match:
        return None, None
    groups = match.groupdict()
    # The trait may be named before ("bat features") or after ("features of a
    # dragon") the species; the themed construction only names it once.
    species = ""
    for field in ("species1", "species2", "species3"):
        value = (groups.get(field) or "").strip().lower()
        if value:
            species = value
            break
    if not species:
        return None, None
    # A leading colour qualifies the species ("black panther"). It is dropped
    # only when the full form is not itself a species and the remainder is, so a
    # multi-word species such as "red panda" is never reduced to another animal.
    words = species.split()
    if species not in KNOWN_SPECIES:
        while len(words) > 1 and words[0] in COLOR_WORDS and " ".join(words[1:]) in KNOWN_SPECIES:
            words.pop(0)
    species = " ".join(words)
    # The passage must describe a real bodily trait of the subject, and the
    # species it names must already be expressible by this catalog.
    singular = species.rstrip("s") if species.endswith("s") and species[:-1] in KNOWN_SPECIES else species
    if species not in KNOWN_SPECIES and singular not in KNOWN_SPECIES:
        return None, None
    # The tag's own word names the trait, so the controlled phrase never drifts
    # to a species the definition happened to mention instead ("lizard" for a
    # reptile girl); the passage above is what makes the rule usable. The same
    # guarded colour trim applies, so "red panda" never becomes "panda".
    words = species_of_tag.split()
    if species_of_tag not in KNOWN_SPECIES:
        while len(words) > 1 and words[0] in COLOR_WORDS and " ".join(words[1:]) in KNOWN_SPECIES:
            words.pop(0)
    trait = " ".join(words)
    if trait not in KNOWN_SPECIES or species not in {trait, *SOURCE_TAXA.get(trait, ())}:
        return None, None
    rule = primitive(
        name,
        "body.species",
        phrase="having traits of " + trait if trait[:1] not in "aeiou" else "having traits of an " + trait,
        adult=bool(ADULT.search(normalized)),
    )
    rule["conditions"] = ["original_only"]
    gender = _gender_condition(groups.get("subject") or groups.get("theme_subject") or "")
    if gender:
        rule["conditions"].append(gender)
    rule["features"] = {"body.species": species_of_tag}
    if species_of_tag in NO_LEGS:
        rule["excludes"] = ["slot:footwear", "slot:legwear", "action:walking", "action:running"]
    evidence = {
        "family": "species_feature_trait",
        "definition": text[:600],
        "passage": raw[:900],
        "matched_construction": "themed_subject" if themed else "subject_with_species_features",
        "species": species,
    }
    return rule, evidence
