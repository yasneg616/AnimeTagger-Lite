"""New evidence must preserve ownership, identity and semantic constraints."""
from dataclasses import replace
from pathlib import Path

import pytest

from app.prompts.normalizer import canonical_tag_key as key
from app.prompts.semantic_catalog import SemanticCatalog
from app.prompts.semantic_prompt import SemanticPromptGenerator, SemanticPromptRequest
from app.prompts.semantic_rules import primitive
from app.prompts.semantic_scene import SceneActor, SceneFact, ScenePlan, render_tags, validate_scene
from scripts.prompt_semantic_concepts import concept_rule
from scripts.prompt_semantic_dependencies import enrich_rule
from scripts.prompt_semantic_families import infer_definition
from scripts.prompt_semantic_negation import needs_identity_baseline, negation_rule
from scripts.prompt_semantic_species import species_feature_rule

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def generator():
    return SemanticPromptGenerator(ROOT)


@pytest.mark.parametrize('name,body,slot', (
    ('ice_cube', 'A small piece of ice shaped like a square.', 'object'),
    ('earbuds', 'A small type of earphones that fits outside the ear canal.', 'object'),
    ('chain_headband', 'A chain worn as a headband.', 'accessory'),
    ('hand_wraps', 'A strip of cloth wrapped around the hands.', 'handwear'),
    ('bindi', 'A forehead mark consisting of a colored dot.', 'body.detail'),
    ('sidelighting', 'When the source of lighting comes from the side.', 'lighting'),
    ('2022', "Either the image has the year '2022' written on it, or references that year.", 'text'),
))
def test_positive_own_definition_establishes_the_concept(name, body, slot):
    rule, evidence = concept_rule(name, {'body': body})
    assert rule['slot'] == slot and evidence['matched_passage']


@pytest.mark.parametrize('body', (
    'An unspecified item. An example contains an ice cube.',
    'An unspecified item.\nh4. See also\n* [[ice cube]]',
    'Deprecated. Use another item instead.', '',
))
def test_names_examples_and_deprecated_definitions_do_not_enable_a_concept(body):
    assert concept_rule('ice_cube', {'body': body}) == (None, None)


def test_year_is_visible_text_and_not_a_fabricated_scene_date():
    rule, _ = concept_rule('2022', {'body': "Either the image has the year '2022' written on it, or references the year."})
    assert rule['slot'] == 'text' and 'written' in rule['phrase']
    assert concept_rule('2022', {'body': 'The year this artwork was created.'}) == (None, None)


@pytest.mark.parametrize('name,body', (
    ('no_cape', 'A character who usually wears a cape is not wearing it.'),
    ('no_mole', 'A character who normally has a mole is depicted without one.'),
    ('missing_tail', 'A character is depicted without its usual tail.'),
))
def test_relative_absence_does_not_invent_an_identity_baseline(name, body):
    assert needs_identity_baseline(name, {'body': body})
    assert negation_rule(name, {'body': body}, lambda _: primitive('cape', 'outerwear')) == (None, None)


def toy_catalog(rules):
    return SemanticCatalog(data={
        'schema_version': 1, 'characters': {}, 'aliases': {}, 'implications': {}, 'coverage': {},
        'entries': {'general:' + key(name): {'name': name, 'category': 'general', 'status': 'reviewed',
            'rule': rule} for name, rule in rules.items()},
    })


def test_literal_absence_forbids_its_item_and_allows_unrelated_same_slot_items():
    base = {'cape': primitive('cape', 'outerwear'), 'coat': primitive('coat', 'outerwear'),
            'mole': primitive('mole', 'body.detail'), 'freckles': primitive('freckles', 'body.detail'),
            'dress': primitive('dress', 'outfit')}
    for name, body in (('without_cape', 'Not wearing a cape.'), ('without_mole', 'A face lacking a mole.')):
        rule, _ = negation_rule(name, {'body': body}, base.get)
        catalog = toy_catalog(base | {name: enrich_rule(name, rule)})
        facts = lambda *names: tuple(SceneFact(catalog.term(n).key) for n in names)
        compatible = 'coat' if name.endswith('cape') else 'freckles'
        forbidden = 'cape' if name.endswith('cape') else 'mole'
        scene = ScenePlan('daily', (SceneActor('A1', facts=facts(name, compatible, 'dress')),))
        assert not validate_scene(scene, catalog)
        bad = replace(scene, actors=(replace(scene.actors[0], facts=facts(name, forbidden, 'dress')),))
        assert validate_scene(bad, catalog)


def test_negation_must_refer_to_the_named_item_and_mean_absent():
    lookup = lambda _: primitive('cape', 'outerwear')
    assert negation_rule('without_cape', {'body': 'Wearing a cape without a hood.'}, lookup) == (None, None)
    assert negation_rule('without_cape', {'body': 'The cape is not removed.'}, lookup) == (None, None)


@pytest.mark.parametrize('name,body', (
    ('quux_girl', 'A girl with wolf-like features.'),
    ('cat_girl', 'A girl with wolf-like features.'),
))
def test_species_name_and_own_definition_must_agree(name, body):
    assert species_feature_rule(name, {'body': body}) == (None, None)


def test_small_type_of_keeps_a_physical_noun_without_reading_other_sentences():
    rule, _, reason = infer_definition('small_camera', {'body': 'A small type of camera used to take photographs. A different item is a hat.'})
    assert not reason and rule['slot'] == 'object'
    rule, _, _ = infer_definition('bad_unknown', {'body': 'A small type of unspecified thing. A related item is a camera.'})
    assert rule is None


def test_hood_state_requires_an_attached_hood_and_is_subject_scoped(generator):
    assert generator.import_tags('1girl, hood_up').blocking
    assert not generator.import_tags('1girl, hood_down, hooded_coat').blocking
    assert generator.import_tags('1girl, hood_up, hood_down, hoodie').blocking
    assert generator.import_tags('1girl, hood_down, hooded_coat, hood').blocking
    result = generator.import_tags('2girls, hood_up, hoodie, hood_down, hooded_coat',
        assignments={1: 'A1', 2: 'A1', 3: 'A2', 4: 'A2'})
    assert not result.blocking and not result.unassigned and result.english_prompt


@pytest.mark.parametrize('tag', ('straddling', 'mouth_hold'))
def test_action_needs_a_real_owned_prop_and_generator_materializes_it(generator, tag):
    assert generator.import_tags('1girl, ' + tag).blocking
    result = generator.generate(SemanticPromptRequest(seed=322, actor_tags=((tag,),)))
    assert any(item.owner == 'A1' for item in result.scene.objects)
    assert not validate_scene(result.scene, generator.catalog)


def test_emoticon_prerequisites_reject_an_opposite_mouth_shape(generator):
    valid = generator.import_tags('1girl, :<, closed_mouth, frown')
    assert not valid.blocking and valid.english_prompt
    invalid = generator.import_tags('1girl, :<, open_mouth, frown')
    assert invalid.blocking


def test_head_facing_rule_keeps_its_explicit_closed_eye_subcase(generator):
    imported = generator.import_tags('1girl, facing_to_the_side, closed_eyes')
    assert not imported.blocking and imported.english_prompt
    generated = generator.generate(SemanticPromptRequest(seed=8000, actor_tags=(('facing_to_the_side',),)))
    assert not validate_scene(generated.scene, generator.catalog)
    assert generator.import_tags('1girl, facing_to_the_side, open_eyes').blocking
    assert generator.import_tags('1girl, looking_at_viewer, closed_eyes').blocking


def test_unknown_gender_counts_preserve_weights_ownership_and_no_age_claim(generator):
    result = generator.import_tags('1girl, 2others, (blue_hair:1.2)', assignments={2: 'A2'})
    assert not result.blocking and not result.unassigned
    assert [a.gender for a in result.scene.actors] == ['female', 'unknown', 'unknown']
    assert all(a.age_state == 'unknown' for a in result.scene.actors)
    assert '(blue_hair:1.2)' in result.tag_prompt and 'Character 2' in result.english_prompt


def test_inconsistent_unknown_gender_counts_are_reported(generator):
    assert generator.import_tags('1other, 2others').blocking
    assert generator.import_tags('2others', actor_count=3).blocking
    assert not generator.import_tags('2others').blocking


def test_count_validation_is_exact_and_excludes_creatures(generator):
    f = SceneFact(generator.catalog.term('1other').key)
    one = ScenePlan('daily', (SceneActor('A1', 'unknown'),), facts=(f,))
    assert not validate_scene(one, generator.catalog)
    two = replace(one, actors=one.actors + (SceneActor('A2', 'unknown'),))
    assert validate_scene(two, generator.catalog)
    creature = replace(one, actors=(replace(one.actors[0], kind='creature'),))
    assert validate_scene(creature, generator.catalog)


def test_unknown_gender_count_is_exported_from_the_same_scene(generator):
    scene = ScenePlan('daily', (SceneActor('A1', 'unknown'), SceneActor('A2', 'unknown')))
    assert '2others' in render_tags(scene, generator.catalog, generator.vocabulary(()))


def test_multiple_sourced_fur_colors_do_not_assert_a_uniform_coat(generator):
    facts = tuple(SceneFact(generator.catalog.term(n).key) for n in ('white_fur', 'red_fur'))
    scene = ScenePlan('fantasy', (SceneActor('A1', facts=facts),))
    assert not validate_scene(scene, generator.catalog)
    assert generator.catalog.character('flareon') is not None


def test_additive_fur_colors_cannot_extend_a_known_identity_palette(generator):
    profile = generator.catalog.character('flareon')
    facts = tuple(SceneFact(generator.catalog.term(n).key) for _, n in (*profile.identity, *profile.wardrobe))
    actor = SceneActor('A1', profile.gender, profile.age_state, profile.name, facts, profile.kind)
    scene = ScenePlan('daily', (actor,))
    assert not validate_scene(scene, generator.catalog)
    changed = replace(scene, actors=(replace(actor, facts=facts + (SceneFact(generator.catalog.term('white_fur').key),)),))
    assert any('配色' in error for error in validate_scene(changed, generator.catalog))


def test_upper_body_coverage_keeps_gender_clothing_and_all_participant_age_guards(generator):
    text = '2girls, topless_female, skirt'
    assignments = {1: 'A1', 2: 'A1'}
    unknown = generator.import_tags(text, assignments=assignments, adult_actors=('A1',))
    assert unknown.blocking
    resolved = generator.import_tags(text, assignments=assignments, adult_actors=('A1', 'A2'))
    assert not resolved.blocking and resolved.english_prompt
    assert generator.import_tags('1boy, topless_female, pants', adult_actors=('A1',)).blocking
    assert generator.import_tags('1girl, topless_female, shirt, skirt', adult_actors=('A1',)).blocking


def test_dressing_action_does_not_invent_a_garment(generator):
    assert generator.import_tags('1girl, dressing').blocking
    assert not generator.import_tags('1girl, dressing, dress').blocking
    assert generator.import_tags('1girl, dressing, undressing, dress', adult_actors=('A1',)).blocking


def test_social_roles_are_ordered_and_do_not_invent_age_or_known_genealogy(generator):
    imported = generator.import_tags('2girls, mother_and_child', assignments={1: ('A1', 'A2')})
    assert not imported.blocking and 'Character 1 is the mother of Character 2' in imported.english_prompt
    assert all(a.age_state == 'unknown' for a in imported.scene.actors)
    assert generator.import_tags('1boy, 1girl, mother_and_child', assignments={2: ('A2', 'A1')}).blocking
    assert generator.import_tags('2girls, mother_and_child, nude', assignments={1: ('A1', 'A2'), 2: 'A1'}, adult_actors=('A1', 'A2')).blocking
    known = next(iter(generator.catalog.characters))
    assert generator.import_tags(known + ', mother_and_child', actor_count=2, assignments={1: ('A1', 'A2')}).blocking
    assert generator.import_tags('2girls, mother_and_child, loli', assignments={1: ('A1', 'A2')}, adult_actors=('A1', 'A2')).blocking


def test_garment_displacement_keeps_the_garment_and_its_owner(generator):
    assert generator.import_tags('1girl, clothes_lift', adult_actors=('A1',)).blocking
    imported = generator.import_tags('1girl, clothes_lift, shirt', adult_actors=('A1',))
    assert not imported.blocking
    assert generator.import_tags('1girl, clothes_lift, clothes_pull, shirt', adult_actors=('A1',)).blocking
