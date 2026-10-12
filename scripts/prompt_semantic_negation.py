"""Literal absence with evidence about the named item, not its whole slot.

Removing a usually-present identity trait needs a baseline/variant model that
this adapter does not provide. Such pages stay in the work queue.
"""
from __future__ import annotations

import re

from app.prompts.normalizer import canonical_tag_key as key
from app.prompts.semantic_rules import REVIEWED, SLOT_SCOPE, primitive
from scripts.prompt_semantic_families import UNRESOLVED, definition, plain

# Items whose absence is about underwear rather than an outfit layer. The
# compiled item rule places them on the generic outfit slot, but the catalog
# already models their absence against the underwear slots.
SLOT_OVERRIDE = {
    "bra": "underwear.top",
    "brassiere": "underwear.top",
    "panties": "underwear.bottom",
    "panty": "underwear.bottom",
    "underwear": "underwear",
    "underpants": "underwear.bottom",
    "briefs": "underwear.bottom",
    "boxers": "underwear.bottom",
}

# Items that name a category rather than a single modelled tag.
CATEGORY_SLOTS = {
    "eyewear": "accessory",
    "jewelry": "accessory",
    "jewellery": "accessory",
    "headwear": "headwear",
    "headgear": "headwear",
    "footwear": "footwear",
    "legwear": "legwear",
    "handwear": "handwear",
    "outerwear": "outerwear",
    "undergarment": "underwear",
    "undergarments": "underwear",
}

# A definition must say the item is not there. "No pantsu" alone is a name, not
# evidence, so the passage has to carry an absence word.
ABSENCE = re.compile(
    r"\b(?:not|no|without|lack(?:s|ing)?|absent|missing|removed|removal|none|"
    r"unworn|does\s+not|do\s+not|isn't|aren't)\b",
    re.I,
)

# The tag name is a claim about absence, and a page can define the item instead
# because the tag simply names it.
NAME_FORM = re.compile(r"^(?:no|without|missing)\s+(?P<item>[a-z][a-z '-]*)$", re.I)

# A body feature may be named directly rather than through another tag. These
# are the slots the catalog already marks as present for the matching feature.
BODY_FEATURE_SLOTS = {
    "tail": "body.tail",
    "tails": "body.tail",
    "wing": "body.wings",
    "wings": "body.wings",
    "halo": "body.halo",
    "horn": "body.horns",
    "horns": "body.horns",
    "ear": "body.ears",
    "ears": "body.ears",
}

# Absence tags whose semantics are already written by hand in
# prompt_semantic_supplement. They carry a deliberate content level and
# prerequisite that this general grammar must not replace. The set is derived
# from that module so the two cannot drift apart.
from scripts.prompt_semantic_supplement import RULES as _SUPPLEMENT_RULES  # noqa: E402

HAND_WRITTEN = frozenset(
    name for name in _SUPPLEMENT_RULES if NAME_FORM.match(name)
)

# Slots whose absence is a statement about the body rather than about worn
# clothing. Those do not need another garment to be present.
BODY_PREFIX = "body."


def needs_identity_baseline(name, page):
    normalized = key(name)
    if normalized in REVIEWED or normalized in HAND_WRITTEN or not NAME_FORM.match(normalized):
        return False
    first = re.split(r'\n|\.(?:\s|$)', plain(definition(page.get('body', ''))), maxsplit=1)[0]
    return normalized.startswith('missing ') or bool(re.search(
        r'\b(?:normally|usually|typically|canonically|regularly|in canon|by default)\b', first, re.I))


def _target_slot(item: str, lookup):
    """The slot the named item occupies, taken from its reviewed rule."""
    if item in SLOT_OVERRIDE:
        return SLOT_OVERRIDE[item], None
    if item in CATEGORY_SLOTS:
        # Eyewear and jewelry are subsets of the accessory slot. Excluding that
        # entire slot would incorrectly forbid necklaces or hair ribbons too.
        if CATEGORY_SLOTS[item] == 'accessory':
            return None, None
        return CATEGORY_SLOTS[item], None
    if item in BODY_FEATURE_SLOTS:
        return BODY_FEATURE_SLOTS[item], None
    rule = lookup(item)
    if not rule:
        return None, None
    slot = rule.get("slot")
    if not slot or slot not in SLOT_SCOPE or rule.get("scope") == "scene":
        return None, None
    return slot, rule


def negation_rule(name, page, lookup):
    """Return an absence rule for "no <item>", or (None, None)."""
    normalized = key(name)
    # A hand-written primitive is more specific than this general grammar and is
    # never replaced by it.
    if normalized in REVIEWED or normalized in HAND_WRITTEN:
        return None, None
    match = NAME_FORM.match(normalized)
    if not match:
        return None, None
    item = match.group("item").strip()
    raw = definition(page.get("body", ""))
    text = plain(raw)
    if not text or UNRESOLVED.search(text) or UNRESOLVED.search(normalized):
        return None, None
    if needs_identity_baseline(name, page):
        return None, None
    first = re.split(r'\n|\.(?:\s|$)', text, maxsplit=1)[0]
    if not ABSENCE.search(first):
        return None, None
    item_pattern = re.escape(item)
    absent_item = re.search(r'\b(?:not|no|without|lack(?:s|ing)?|absent|missing|removed|removal)\s+(?:[\w-]+\s+){0,4}' + item_pattern + r'\b', first, re.I)
    absent_item = absent_item or re.search(r'\b' + item_pattern + r'\b.{0,35}\b(?:removed|missing|absent|unworn|not worn)\b', first, re.I)
    if not absent_item or re.search(r'\b(?:not|never)\s+(?:removed|missing|absent)\b', first, re.I):
        return None, None
    slot, item_rule = _target_slot(item, lookup)
    if not slot:
        return None, None
    rule = primitive(
        name,
        "body.detail" if slot.startswith(BODY_PREFIX) else "clothing.detail",
        phrase=("no " + item) if normalized.startswith("no ") else ("without " + item if normalized.startswith("without ") else "missing " + item),
        adult=bool(item_rule and item_rule.get("adult")),
    )
    rule["excludes"] = ['attribute:' + item] if item_rule else ['slot:' + slot]
    rule["features"] = {'absent.item.' + item: 'yes'} if item_rule else {'absent.' + slot: 'yes'}
    # A worn item only reads as absent when something else is worn, which is the
    # same condition the catalog already uses for its other absence tags.
    if not slot.startswith(BODY_PREFIX):
        rule["required_slots"] = [["outfit", "top", "bottom", "outerwear", "underwear", "underwear.top", "underwear.bottom"]]
    evidence = {
        "family": "absent_attribute",
        "definition": text[:600],
        "passage": raw[:900],
        "absent_slot": slot,
        "item": item,
    }
    return rule, evidence

