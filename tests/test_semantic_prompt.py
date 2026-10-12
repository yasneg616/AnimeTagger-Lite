from dataclasses import replace
from pathlib import Path

import pytest

from app.errors import ConfigurationError
from app.prompts.semantic_catalog import SemanticCatalog
from app.prompts.semantic_prompt import SemanticPromptGenerator, SemanticPromptRequest
from app.prompts.semantic_scene import (
    SceneActor, SceneFact, SceneObject, ScenePlan, compact_facts,
    render_english, render_tags, validate_scene,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def generator():
    return SemanticPromptGenerator(ROOT)


def fact(generator, name):
    return SceneFact(generator.catalog.term(name).key)


@pytest.mark.parametrize("count", range(1, 5))
@pytest.mark.parametrize("freedom", ("natural", "balanced", "bold"))
@pytest.mark.parametrize("content", ("ordinary", "adult"))
def test_complete_scenes_reproduce_and_preserve_output_facts(generator, count, freedom, content):
    request = SemanticPromptRequest(seed=196, actor_count=count, freedom=freedom, content=content, density="rich")
    result = generator.generate(request)
    assert result == generator.generate(request)
    assert len(result.scene.actors) == count
    assert not validate_scene(result.scene, generator.catalog)
    assert 0 < result.expansions <= 2000
    assert result.tag_prompt and result.english_prompt
    assert render_english(result.scene, generator.catalog) == result.english_prompt
    assert render_tags(result.scene, generator.catalog, generator.vocabulary(())) == result.tag_prompt
    if content == "adult":
        assert all(actor.age_state == "adult" for actor in result.scene.actors)
    else:
        assert not any(generator.catalog.terms[value.term_key].adult for actor in result.scene.actors for value in actor.facts)


def test_conflicts_are_owned_and_multicolor_is_explicit(generator):
    blue, red, multi = (fact(generator, name) for name in ("blue_hair", "red_hair", "multicolored_hair"))
    scene = ScenePlan("daily", (SceneActor("A1", facts=(blue,)), SceneActor("A2", facts=(red,))))
    assert not validate_scene(scene, generator.catalog)
    conflict = replace(scene, actors=(replace(scene.actors[0], facts=(blue, red)), scene.actors[1]))
    assert any("hair.color" in error for error in validate_scene(conflict, generator.catalog))
    allowed = replace(conflict, actors=(replace(conflict.actors[0], facts=(blue, red, multi)), conflict.actors[1]))
    assert not validate_scene(allowed, generator.catalog)
    assert "blue hair" in render_english(allowed, generator.catalog)
    assert "red hair" in render_english(allowed, generator.catalog)


def test_length_implication_keeps_specific_and_ponytail_can_coexist(generator):
    values = tuple(fact(generator, name) for name in ("long_hair", "very_long_hair", "ponytail"))
    compact = compact_facts(values, generator.catalog)
    assert fact(generator, "long_hair") not in compact
    assert fact(generator, "very_long_hair") in compact
    assert not validate_scene(ScenePlan("daily", (SceneActor("A1", facts=compact),)), generator.catalog)
    bob = (*compact, fact(generator, "bob_cut"))
    assert validate_scene(ScenePlan("daily", (SceneActor("A1", facts=bob),)), generator.catalog)


def test_layered_clothes_are_valid_but_nudity_and_clothes_are_not(generator):
    values = tuple(fact(generator, name) for name in ("shirt", "skirt", "coat"))
    scene = ScenePlan("daily", (SceneActor("A1", facts=values),))
    assert not validate_scene(scene, generator.catalog)
    for extra in ("nude", "dress"):
        assert validate_scene(replace(scene, actors=(replace(scene.actors[0], facts=(*values, fact(generator, extra))),)), generator.catalog)


def test_dependencies_require_the_same_owner(generator):
    scene = ScenePlan("daily", (SceneActor("A1", facts=(fact(generator, "reading"),)), SceneActor("A2")),
                      objects=(SceneObject("O1", fact(generator, "book"), "A2"),))
    assert any("object:book" in error for error in validate_scene(scene, generator.catalog))
    assert not validate_scene(replace(scene, objects=(replace(scene.objects[0], owner="A1"),)), generator.catalog)
    result = generator.generate(SemanticPromptRequest(seed=1, action="reading", actor_count=2))
    assert any(item.owner == "A1" and generator.catalog.terms[item.fact.term_key].name == "book" for item in result.scene.objects)


def test_scope_types_cannot_be_interchanged(generator):
    scene = ScenePlan("daily", (SceneActor("A1", facts=(fact(generator, "night"),)),), facts=(fact(generator, "blue_hair"),))
    assert len(validate_scene(scene, generator.catalog)) >= 2


def test_controlled_english_uses_plural_and_proper_name_grammar(generator):
    scene = ScenePlan("daily", (SceneActor("A1", character="hatsune_miku", age_state="unknown", facts=tuple(fact(generator, tag) for tag in ("twintails", "glasses", "boots", "demon_tail"))),))
    english = render_english(scene, generator.catalog)
    assert "is Hatsune Miku" in english
    assert "a twintails" not in english and "a glasses" not in english and "a boots" not in english
    assert "a demon tail" in english
    scene = ScenePlan("daily", (SceneActor("A1", facts=(fact(generator, "double_bun"), fact(generator, "one-piece_swimsuit"))),))
    english = render_english(scene, generator.catalog)
    assert "two hair buns" in english and "a one-piece swimsuit" in english
    assert "a two hair buns" not in english and "an one-piece" not in english


def test_absence_phrases_are_stated_without_an_article(generator):
    """An absent attribute reads as "no cape", never as "a no cape"."""
    scene = ScenePlan("daily", (SceneActor("A1", facts=(
        fact(generator, "shirt"), fact(generator, "no_cape"), fact(generator, "no_eyewear"))),))
    english = render_english(scene, generator.catalog)
    assert "no cape" in english and "no eyewear" in english
    assert "a no cape" not in english and "a no eyewear" not in english
    # The absence must not sit alongside the thing it says is absent.
    owner = scene.actors[0]
    slots = {generator.catalog.terms[f.term_key].slot for f in owner.facts}
    assert "outerwear" not in slots and "accessory" not in slots
    assert not validate_scene(scene, generator.catalog)


def test_reviewed_absence_keeps_its_specific_prerequisite(generator):
    """No shoes depicts legwear without footwear; no mouth needs no garment."""
    bare = ScenePlan("daily", (SceneActor("A1", facts=(fact(generator, "no_shoes"),)),))
    assert any("no_shoes" in problem for problem in validate_scene(bare, generator.catalog))
    dressed = ScenePlan("daily", (SceneActor("A1", facts=(
        fact(generator, "dress"), fact(generator, "socks"), fact(generator, "no_shoes"))),))
    assert not validate_scene(dressed, generator.catalog)
    # A body-feature absence needs no garment at all.
    feature = ScenePlan("daily", (SceneActor("A1", facts=(fact(generator, "no_mouth"),)),))
    assert not validate_scene(feature, generator.catalog)


def test_native_character_identity_and_age_are_locked(generator):
    request = SemanticPromptRequest(seed=13, characters=("hatsune_miku",))
    result = generator.generate(request)
    actor = result.scene.actors[0]
    assert actor.character == "hatsune_miku" and actor.age_state == "unknown"
    assert {generator.catalog.terms[value.term_key].name for value in actor.facts} >= {"aqua_hair", "aqua_eyes", "twintails", "very_long_hair"}
    with pytest.raises(ConfigurationError, match="档案|成年"):
        generator.generate(replace(request, content="adult"))
    with pytest.raises(ConfigurationError, match="冲突"):
        generator.generate(replace(request, actor_tags=(("red_hair",),)))


def test_adult_known_character_requires_an_explicit_adult_profile(generator):
    result = generator.generate(SemanticPromptRequest(seed=32, characters=("satake_minako",), content="adult"))
    assert result.scene.actors[0].age_state == "adult"
    assert not validate_scene(result.scene, generator.catalog)


def test_locks_preserve_owned_facts_props_and_relations(generator):
    before = generator.generate(SemanticPromptRequest(seed=4, actor_count=2, action="reading"))
    after = generator.generate(SemanticPromptRequest(seed=33, actor_count=2, previous_scene=before.scene, locked_actors=("A1",),
                                                     locked_scene_slots=("location", "environment", "time")))
    assert before.scene.actors[0] == after.scene.actors[0]
    assert {item for item in before.scene.objects if item.owner == "A1"} <= set(after.scene.objects)
    assert {item for item in before.scene.interactions if "A1" in item.participants} <= set(after.scene.interactions)
    for slot in ("location", "environment", "time"):
        assert tuple(value for value in before.scene.facts if generator.catalog.terms[value.term_key].slot == slot) == tuple(value for value in after.scene.facts if generator.catalog.terms[value.term_key].slot == slot)


def test_reroll_with_a_later_locked_actor_keeps_object_ids_unique(generator):
    before = generator.generate(SemanticPromptRequest(seed=11, actor_count=2, actor_tags=(("reading",), ("holding_umbrella",))))
    after = generator.generate(SemanticPromptRequest(seed=12, actor_count=2, action="reading", previous_scene=before.scene, locked_actors=("A2",)))
    assert before.scene.actors[1] == after.scene.actors[1]
    assert len({item.object_id for item in after.scene.objects}) == len(after.scene.objects)
    assert not validate_scene(after.scene, generator.catalog)


def test_conflicting_constraints_report_specific_cause(generator):
    with pytest.raises(ConfigurationError, match="night|sunlight"):
        generator.generate(SemanticPromptRequest(seed=2, scene_tags=("night", "sunlight")))
    with pytest.raises(ConfigurationError, match="至少需要"):
        generator.generate(SemanticPromptRequest(seed=2, action="holding_hands"))
    with pytest.raises(ConfigurationError, match="主体"):
        generator.generate(SemanticPromptRequest(seed=2, locked_actors=("A3",), previous_scene=generator.generate(SemanticPromptRequest(seed=2)).scene))


def test_restricted_vocabulary_unsatisfiable_has_bounded_search(tmp_path):
    csv = tmp_path / "models/wd-vit-tagger-v3/selected_tags.csv"
    csv.parent.mkdir(parents=True)
    csv.write_text("tag_id,name,category,count\n1,1girl,0,100\n2,blue_hair,0,1\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="候选扩展 .*2000.*location"):
        SemanticPromptGenerator(tmp_path).generate(SemanticPromptRequest(backends=("wd_v3",), seed=1))


def test_weighted_input_and_unknown_tags_keep_original_tokens(generator):
    text = "1girl, (blue_hair:1.25), (blue_hair:1.7), long_hair, ponytail, strange_new_word"
    result = generator.import_tags(text)
    assert result.tag_prompt == text
    assert result.scene.imported_tokens[1:3] == ("(blue_hair:1.25)", "(blue_hair:1.7)")
    assert next(value.weight for value in result.scene.actors[0].facts if value.term_key == fact(generator, "blue_hair").term_key) == 1.7
    assert "strange_new_word" not in result.english_prompt
    assert result.scene.opaque_tokens == ("strange_new_word",)
    assert not result.blocking


def test_external_conflicts_do_not_destroy_tags(generator):
    text = "1girl, red_hair, blue_hair"
    result = generator.import_tags(text)
    assert result.blocking and not result.english_prompt
    assert result.tag_prompt == text


def test_multi_subject_import_waits_for_user_ownership(generator):
    text = "2girls, red_hair, blue_hair, hugging, book"
    result = generator.import_tags(text)
    assert len(result.unassigned) == 2
    assert not result.english_prompt
    assigned = generator.import_tags(text, assignments={1: "A1", 2: "A2"})
    assert not assigned.unassigned and not assigned.blocking
    assert "Character 1" in assigned.english_prompt and "Character 2" in assigned.english_prompt


def test_import_interaction_participants_and_object_owners_are_not_guessed(generator):
    text = "3girls, holding_hands, reading, book"
    result = generator.import_tags(text)
    assert {item.kind for item in result.unassigned} == {"relation", "actor", "object"}
    assigned = generator.import_tags(text, assignments={1: ("A1", "A3"), 2: "A2", 3: "A2"})
    assert not assigned.blocking and not assigned.unassigned
    assert assigned.scene.interactions[0].participants == ("A1", "A3")
    assert assigned.scene.objects[0].owner == "A2"


def test_import_counts_brackets_identity_and_age(generator):
    with pytest.raises(ValueError, match="括号"):
        generator.import_tags("1girl, (blue_hair:1.2")
    with pytest.raises(ConfigurationError, match="1–4"):
        generator.import_tags("5girls, blue_hair")
    assert generator.import_tags("solo, 2girls").blocking
    assert generator.import_tags("1girl, nude").blocking
    assert not generator.import_tags("1girl, nude", adult_actors=("A1",)).blocking
    assert generator.import_tags("1girl, child, nude", adult_actors=("A1",)).blocking
    assert generator.import_tags("hatsune_miku, nude", adult_actors=("A1",)).blocking
    assert generator.import_tags("2girls, closed_eyes, eye_contact", assignments={1: "A1"}).blocking


def test_import_gender_counts_do_not_define_named_character_order(generator):
    result = generator.import_tags("1girl, 1boy, andrew_graves, ashley_graves")
    assert [actor.gender for actor in result.scene.actors] == ["male", "female"]
    assert not any("性别" in error for error in result.blocking)
    assert any("性别" in error for error in generator.import_tags("2girls, andrew_graves, ashley_graves").blocking)


def test_formatting_and_weights_do_not_change_native_scene(generator):
    request = SemanticPromptRequest(seed=5, actor_tags=(("(blue_hair:1.2)",),))
    result = generator.generate(request)
    spaced = generator.generate(replace(request, underscore_to_space=True))
    assert result.scene == spaced.scene and result.english_prompt == spaced.english_prompt
    assert "(blue_hair:1.2)" in result.tag_prompt
    assert "(blue hair:1.2)" in spaced.tag_prompt
    assert result.corpus_version == spaced.corpus_version


def test_corpus_distinguishes_source_acquisition_from_review(generator):
    report = generator.catalog.coverage
    assert report["total"] == 17042
    assert report["usable_reviewed"] == sum(row["status"] == "reviewed" for row in generator.catalog.records.values())
    assert report["minimum_met"] == (report["usable_reviewed"] >= 11362)
    assert report["source_available"] > report["usable_reviewed"]


def test_reviewed_nested_garment_modifiers_and_short_cut_constraints(generator):
    from app.prompts.semantic_rules import infer_composition, REVIEWED
    rule, method = infer_composition("transparent_frilled_dress")
    assert rule["adult"] and rule["head"] == "dress" and rule["slot"] == "outfit"
    assert "hair.length:long_hair" in REVIEWED["crew cut"]["excludes"]
    for style in ("bowl_cut", "buzz_cut"):
        scene = ScenePlan("daily", (SceneActor("A1", facts=(fact(generator, "long_hair"), fact(generator, style))),))
        assert validate_scene(scene, generator.catalog)


def test_runtime_has_no_network_dependency(generator, monkeypatch):
    import socket
    def denied(*args, **kwargs):
        raise AssertionError("Runtime attempted a network operation")
    monkeypatch.setattr(socket.socket, "connect", denied)
    result = generator.generate(SemanticPromptRequest(seed=52))
    assert result.english_prompt
    assert generator.import_tags(result.tag_prompt).tag_prompt == result.tag_prompt


@pytest.mark.parametrize("seed,backend,count,content,freedom", (
    (1190, "wd_2026_canary", 3, "adult", "natural"),
    (7735, "pixai_v0_9", 4, "ordinary", "balanced"),
    (1078, "pixai_v0_9", 3, "adult", "bold"),
    (766, "wd_2026_canary", 3, "adult", "bold"),
))
def test_distribution_regressions_do_not_erase_identity_or_add_unreviewed_dependencies(generator, seed, backend, count, content, freedom):
    result = generator.generate(SemanticPromptRequest(seed=seed, backends=(backend,), actor_count=count, content=content,
                                                     freedom=freedom, character_mode="known" if seed in (1190, 7735) else "original"))
    from app.prompts.semantic_scene import all_facts
    assert not validate_scene(result.scene, generator.catalog)
    assert all(generator.catalog.terms[value.term_key].generatable for value in all_facts(result.scene))
    assert result.expansions < 2000
