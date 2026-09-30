"""Explicit positive-prompt injection, independent of model vocabulary."""
from __future__ import annotations

from dataclasses import replace
import re

from app.inference.model_loader import TagCategory
from app.prompts.models import PromptBuildResult, TagResult, TagSource
from app.prompts.normalizer import canonical_tag_key


_HAIR = set("""ahoge bangs blunt_bangs parted_bangs swept_bangs asymmetrical_bangs
hair_between_eyes hair_over_one_eye hair_over_eyes hair_intakes hair_flaps sidelocks
braid braids single_braid twin_braids french_braid braided_bangs crown_braid
ponytail high_ponytail low_ponytail side_ponytail twintails low_twintails short_twintails
hair_bun double_bun single_hair_bun folded_ponytail half_updo updo topknot
drill_hair twin_drills ringlets hime_cut bob_cut pixie_cut bowl_cut buzz_cut
crew_cut undercut mohawk bald bald_head widow's_peak hair_slicked_back
hair_pulled_back hair_tucked_behind_ear hair_behind_ear hair_over_shoulder
hair_over_breasts hair_spread_out streaked_hair colored_inner_hair
multicolored_hair two-tone_hair gradient_hair split-color_hair
""".split())
_FACE = set("""heterochromia eyelashes long_eyelashes colored_eyelashes thick_eyebrows
thin_eyebrows short_eyebrows eyebrows_visible_through_hair no_eyebrows
beard mustache goatee stubble facial_hair sideburns freckles facial_mark
facial_tattoo face_tattoo scar_on_face scar_across_eye mole_under_eye
mole_under_mouth mole_on_cheek mole_on_face mole_on_nose thick_lips thin_lips
pointy_ears elf_ears sharp_teeth fangs fang slit_pupils horizontal_pupils
no_pupils white_pupils colored_sclera black_sclera red_sclera sanpaku tsurime tareme
""".split())
_COLORS = "aqua black blue brown green grey gray orange pink purple red silver white yellow gold golden amber hazel violet multicolored two-tone rainbow glowing"
_EYES = {f"{color}_eyes" for color in _COLORS.split()}
_HAIR.update(f"{color}_hair" for color in (_COLORS + " blonde lavender").split())
_HAIR.update("""short_hair very_short_hair medium_hair long_hair very_long_hair
absurdly_long_hair low-braided_long_hair low-tied_long_hair asymmetrical_hair
big_hair curly_hair curtained_hair flipped_hair fluffy_hair folded_hair
messy_hair multi-tied_hair parted_hair pointy_hair spiked_hair straight_hair
tall_hair wavy_hair antenna_hair bow-shaped_hair heart-shaped_hair
striped_hair patterned_hair starry_hair hair_between_breasts
""".split())


def token_key(text: str) -> str:
    """Match an entire label, including common (label:weight) syntax."""
    text = text.strip().replace(r"\(", "(").replace(r"\)", ")")
    while len(text) > 1 and (text[0], text[-1]) in {("(", ")"), ("[", "]")}:
        text = text[1:-1].strip()
        text = re.sub(r":\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)\s*$", "", text)
    return canonical_tag_key(text)


def is_appearance_tag(text: str) -> bool:
    key = token_key(text).replace(" ", "_")
    return key in _HAIR | _FACE | _EYES or key.endswith(("_eyebrows", "_eyelashes", "_pupils", "_sclera"))


def split_tokens(text: str) -> tuple[str, ...]:
    """Split top-level comma/newline labels without breaking weighted groups."""
    tokens, buffer, stack = [], [], []
    escaped = False
    for char in text:
        if escaped:
            buffer.append(char)
            escaped = False
            continue
        if char == "\\":
            escaped = True
            buffer.append(char)
            continue
        if char in "([":
            stack.append(char)
        elif char in ")]" and stack and (stack[-1], char) in {("(", ")"), ("[", "]")}:
            stack.pop()
        if char in ",，\n\r" and not stack:
            tokens.append("".join(buffer).strip())
            buffer = []
        else:
            buffer.append(char)
    tokens.append("".join(buffer).strip())
    return tuple(token for token in tokens if token)


def parse_injections(text: str) -> tuple[str, ...]:
    stack = []
    for char in re.sub(r"\\.", "", text):
        if char in "([":
            stack.append(char)
        elif char in ")]":
            if not stack or (stack.pop(), char) not in {("(", ")"), ("[", "]")}:
                raise ValueError("标签中的括号不成对，请检查后再注入。")
    if stack:
        raise ValueError("标签中的括号不成对，请检查后再注入。")
    tokens = split_tokens(text)
    if any("," in token or "，" in token or "\n" in token or "\r" in token for token in tokens):
        raise ValueError("请逐个输入标签，用逗号或换行分隔；括号中不能包含多个标签。")
    result, seen = [], set()
    for token in tokens:
        key = token_key(token)
        if key and key not in seen:
            result.append(token)
            seen.add(key)
    return tuple(result)


def inject_text(text: str, names: tuple[str, ...], removed: set[str] | None = None) -> str:
    removed = removed or set()
    tokens = [token for token in split_tokens(text) if token_key(token) not in removed]
    seen = {token_key(token) for token in tokens}
    for name in names:
        if token_key(name) not in seen:
            tokens.append(name)
            seen.add(token_key(name))
    return ", ".join(tokens)


def prepare_tags(tags, names, *, clean_appearance=True):
    """Disable only model appearance; preserve the original inference and user tags."""
    removed = {
        token_key(tag.output_name) for tag in tags
        if clean_appearance and tag.source is TagSource.MODEL and is_appearance_tag(tag.output_name)
    }
    # Explicit manual overrides with the same label are protected.
    removed -= {token_key(tag.output_name) for tag in tags if tag.source is TagSource.USER and tag.enabled}
    result = [replace(tag, enabled=False) if tag.source is TagSource.MODEL and token_key(tag.output_name) in removed else tag for tag in tags]
    for name in names:
        key = token_key(name)
        result = [tag for tag in result if not (tag.source is TagSource.USER and token_key(tag.output_name) == key)]
        result.append(TagResult(name, 1.0, TagCategory.GENERAL, source=TagSource.USER))
    return result, removed


def overlay_injections(prompts: PromptBuildResult, names: tuple[str, ...]) -> PromptBuildResult:
    """Make explicit injections survive max_tags, exclusions and profile formatting."""
    active = {token_key(tag.name): tag for tag in prompts.raw_tags if tag.enabled and tag.source is TagSource.USER}
    names = tuple(name for name in names if token_key(name) in active)
    if not names:
        return prompts
    positive = list(prompts.positive_tags)
    keys = {token_key(tag.output_name) for tag in positive}
    for name in names:
        if token_key(name) not in keys:
            positive.append(active[token_key(name)])
            keys.add(token_key(name))
    injected_keys = {token_key(name) for name in names}
    filtered = list(prompts.filtered_tags)
    filtered_keys = {token_key(tag.output_name) for tag in filtered}
    filtered.extend(active[token_key(name)] for name in names if token_key(name) not in filtered_keys)
    return replace(
        prompts, positive_prompt=inject_text(prompts.positive_prompt, names),
        positive_tags=tuple(positive), filtered_tags=tuple(filtered),
        excluded_tags=tuple(tag for tag in prompts.excluded_tags if token_key(tag.output_name) not in injected_keys),
        removed_tags=tuple(record for record in prompts.removed_tags if not (record.tag.source is TagSource.USER and token_key(record.tag.output_name) in injected_keys)),
        settings_snapshot={**prompts.settings_snapshot, "positive_injections": list(names)},
    )
