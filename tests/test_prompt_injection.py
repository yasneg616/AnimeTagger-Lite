from dataclasses import replace

import pytest

from app.config.settings import AppSettings
from app.inference.model_loader import TagCategory
from app.prompts.injection import inject_text, is_appearance_tag, parse_injections, prepare_tags, overlay_injections
from app.prompts.models import TagResult, TagSource
from app.services.tagging_service import TaggingService


@pytest.mark.parametrize("name", ["long_hair", "black hair", "twintails", "blunt_bangs", "green_eyes", "heterochromia", "thick_eyebrows", "mole_under_eye", "(blue_eyes:1.2)", "symbol-shaped_pupils", "ringed_pupils"])
def test_recognizes_identity_features(name):
    assert is_appearance_tag(name)


@pytest.mark.parametrize("name", ["smile", "closed_eyes", "looking_at_viewer", "hair_ribbon", "hair_ornament", "eyewear", "jacket", "city", "pubic_hair", "1girl", "character_(blue_eyes)", "hand_in_own_hair", "holding_another's_hair", "black_pubic_hair"])
def test_preserves_non_identity_and_accessories(name):
    assert not is_appearance_tag(name)


def test_split_deduplicate_and_preserve_weighted_names():
    assert parse_injections("new_character_(game)，new costume\nnew_costume, (blue_eyes:1.2)") == ("new_character_(game)", "new costume", "(blue_eyes:1.2)")
    with pytest.raises(ValueError):
        parse_injections("(blue_eyes, red_hair:1.2)")
    with pytest.raises(ValueError):
        parse_injections("new_character_(game")


def test_surgical_text_edit_preserves_other_manual_tokens():
    assert inject_text("(BLUE EYES:1.3), smile, custom_lighting, new_character", ("new_character", "red_hair"), {"blue eyes"}) == "smile, custom_lighting, new_character, red_hair"


def test_cleanup_disables_only_model_features_and_injection_can_reintroduce_color():
    tags = [TagResult(name, .95, TagCategory.GENERAL) for name in ("black_hair", "long_hair", "smile")]
    tags.append(TagResult("long_hair", 1, TagCategory.GENERAL, source=TagSource.USER))
    updated, removed = prepare_tags(tags, ("black_hair", "new_character"))
    assert all(tag.enabled for tag in tags)
    assert removed == {"black hair"}
    assert not updated[0].enabled
    assert any(tag.name == "black_hair" and tag.enabled and tag.source is TagSource.USER for tag in updated)


@pytest.mark.parametrize("profile", ["raw", "anime", "pony", "lora_caption", "cyberillustrious_semireal", "krea2"])
def test_explicit_unknown_tag_survives_profile_exclusion_and_budget(profile):
    tags = [TagResult("1girl", 1, TagCategory.GENERAL), TagResult("new_character", 1, TagCategory.GENERAL, source=TagSource.USER)]
    settings = AppSettings(profile=profile, max_tags=1, excluded_tags=("new_character",))
    prompts = TaggingService().rebuild_prompts(tags, settings)
    result = overlay_injections(prompts, ("new_character",))
    assert "new_character" in result.positive_prompt
    assert any(tag.name == "new_character" for tag in result.positive_tags)
    disabled = replace(prompts, raw_tags=tuple(replace(tag, enabled=False) if tag.name == "new_character" else tag for tag in prompts.raw_tags))
    assert overlay_injections(disabled, ("new_character",)) == disabled
