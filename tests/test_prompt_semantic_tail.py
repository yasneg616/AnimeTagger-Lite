"""Long-tail rules are source-bound and their targets belong to each actor."""
from dataclasses import replace
from pathlib import Path

import pytest

from app.errors import ConfigurationError
from app.prompts.semantic_prompt import SemanticPromptGenerator, SemanticPromptRequest
from app.prompts.semantic_scene import SceneActor, SceneFact, ScenePlan, validate_scene
from app.prompts.semantic_catalog import SemanticCatalog
from app.prompts.semantic_rules import primitive
from scripts.prompt_semantic_tail import tail_rule
from scripts.prompt_semantic_attributes import attribute_rule
from scripts.prompt_semantic_families import infer_definition

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def generator():
    return SemanticPromptGenerator(ROOT)


@pytest.mark.parametrize('name,body,slot', [
    ('sticker', 'A piece of paper or plastic, sticky on one side.', 'object'),
    ('headphones_around_neck', 'Wearing a set of headphones around the neck like a collar.', 'placement'),
    ('shirt_tucked_in', 'A shirt that is completely tucked in beneath a skirt.', 'clothing.detail'),
    ('carrying', "Supporting something or someone, usually with one's arms.", 'action'),
    ('morning', 'The part of the day that starts with sunrise.', 'time'),
])
def test_exact_concepts_need_positive_own_definitions(name, body, slot):
    rule, evidence = tail_rule(name, {'body': body})
    assert rule['slot'] == slot and evidence['matched_passage']
    assert tail_rule(name, {'body': 'An unrelated idea.\nh4. See also\n' + body}) == (None, None)
    assert tail_rule(name, {'body': 'Not ' + body}) == (None, None)
    assert tail_rule('unrecognized_' + name, {'body': body}) == (None, None)


@pytest.mark.parametrize('name', ['carrying', 'hugging_object', 'weapon_over_shoulder', 'biting', 'between_fingers', 'riding', 'holding_animal', 'holding_fan', 'drawing_(action)', 'shirt_tucked_in', 'shirt_partially_tucked_in', 'pantyhose_under_shorts', 'thighhighs_under_boots', 'adjusting_clothes', 'on_desk', 'jacket_on_shoulders', 'headphones_around_neck', 'towel_around_neck', 'unworn_helmet', 'juban', 'gusset', 'visor_(armor)', 'shoelaces', 'exposed_pocket', 'uvula', 'ballet', 'high_kick', 'text_messaging', 'sidesaddle'])
def test_new_dependencies_produce_an_owned_valid_scene(generator, name):
    term = generator.catalog.term(name)
    assert term and term.generatable
    result = generator.generate(SemanticPromptRequest(seed=42, actor_tags=((name,),)))
    assert not validate_scene(result.scene, generator.catalog)
    facts = {generator.catalog.canonical(generator.catalog.terms[f.term_key].name) for f in result.scene.actors[0].facts}
    assert generator.catalog.canonical(name) in facts
    assert result.english_prompt and not result.blocking


def test_fully_and_partially_tucked_shirts_conflict(generator):
    cat = generator.catalog
    facts = tuple(SceneFact(cat.term(name).key) for name in ['shirt', 'skirt', 'shirt_tucked_in', 'shirt_partially_tucked_in'])
    assert any('clothing.shirt.tuck' in error for error in validate_scene(ScenePlan('daily', (SceneActor('A1', facts=facts),)), cat))


def test_worn_clothes_in_another_actor_do_not_satisfy_adjusting(generator):
    cat = generator.catalog
    actors = (SceneActor('A1', facts=(SceneFact(cat.term('adjusting_clothes').key),)),
              SceneActor('A2', facts=(SceneFact(cat.term('dress').key),)))
    assert validate_scene(ScenePlan('daily', actors), cat)


@pytest.mark.parametrize('dependent,parent', [('juban', 'kimono'), ('visor_(armor)', 'helmet'), ('uvula', 'open_mouth'), ('text_messaging', 'cellphone'), ('exposed_pocket', 'denim_shorts')])
def test_concrete_dependency_cannot_be_borrowed_from_another_actor(generator, dependent, parent):
    pending = generator.import_tags('2girls, ' + dependent + ', ' + parent,
                                    assignments={1: 'A1', 2: 'A2'})
    assert pending.blocking and not pending.english_prompt


def test_comforting_assigns_the_required_expression_to_the_recipient(generator):
    result = generator.generate(SemanticPromptRequest(seed=42, actor_count=2, scene_tags=('comforting',)))
    relation = next(item for item in result.scene.interactions if generator.catalog.terms[item.fact.term_key].name == 'comforting')
    recipient = next(actor for actor in result.scene.actors if actor.actor_id == relation.participants[1])
    assert any(generator.catalog.canonical(generator.catalog.terms[fact.term_key].name) == 'sad' for fact in recipient.facts)
    assert not validate_scene(result.scene, generator.catalog)
    broken = replace(result.scene, actors=tuple(replace(actor, facts=tuple(fact for fact in actor.facts if generator.catalog.canonical(generator.catalog.terms[fact.term_key].name) != 'sad')) for actor in result.scene.actors))
    assert validate_scene(broken, generator.catalog)


def test_held_garment_is_distinct_from_a_worn_outer_garment(generator):
    result = generator.import_tags('1girl, jacket_on_shoulders, jacket, shirt, skirt')
    assert not result.blocking and not result.unassigned
    assert any(generator.catalog.canonical(generator.catalog.terms[o.fact.term_key].name) == 'jacket' and o.owner == 'A1' for o in result.scene.objects)
    assert not any(generator.catalog.canonical(generator.catalog.terms[f.term_key].name) == 'jacket' for f in result.scene.actors[0].facts)


def test_unique_alternative_wearable_is_imported_as_a_prop(generator):
    result = generator.import_tags('1girl, holding, hat')
    assert not result.blocking and result.english_prompt
    assert any(generator.catalog.canonical(generator.catalog.terms[o.fact.term_key].name) == 'hat' for o in result.scene.objects)
    ambiguous = generator.import_tags('1girl, holding, hat, shirt')
    # Two possible garments do not establish which one is held.
    assert ambiguous.blocking and not ambiguous.english_prompt


def test_alternative_object_owner_remains_explicit_for_multiple_actors(generator):
    pending = generator.import_tags('2girls, holding, hat')
    assert pending.unassigned and not pending.english_prompt
    assigned = generator.import_tags('2girls, holding, hat', assignments={1: 'A2', 2: 'A2'})
    assert not assigned.blocking and not assigned.unassigned
    assert all(obj.owner == 'A2' for obj in assigned.scene.objects)
    wrong = generator.import_tags('2girls, holding, hat', assignments={1: 'A1', 2: 'A2'})
    assert wrong.blocking and not wrong.english_prompt


def test_new_family_relations_preserve_role_and_content_conditions(generator):
    result = generator.generate(SemanticPromptRequest(seed=60, actor_count=2, scene_tags=('mother_and_daughter',)))
    relation = result.scene.interactions[0]
    assert generator.catalog.terms[relation.fact.term_key].role_genders == ('female', 'female')
    assert 'is the mother of' in result.english_prompt
    adult = generator.import_tags('2girls, mother_and_daughter, nude', assignments={1: ('A1', 'A2'), 2: 'A1'}, adult_actors=('A1', 'A2'))
    assert adult.blocking and not adult.english_prompt


@pytest.mark.parametrize('seed', range(12))
def test_pinned_relation_plans_an_eligible_original_cast(generator, seed):
    result = generator.generate(SemanticPromptRequest(seed=seed, actor_count=2, scene_tags=('mother_and_daughter',)))
    assert all(actor.gender == 'female' for actor in result.scene.actors)
    assert not validate_scene(result.scene, generator.catalog)
    assert result == generator.generate(SemanticPromptRequest(seed=seed, actor_count=2, scene_tags=('mother_and_daughter',)))


def test_pinned_gender_cannot_change_a_locked_actor(generator):
    previous = ScenePlan('daily', (SceneActor('A1', 'male'), SceneActor('A2', 'female')))
    with pytest.raises(ConfigurationError, match='主体性别或人数'):
        generator.generate(SemanticPromptRequest(seed=1, actor_count=2, scene_tags=('mother_and_daughter',), previous_scene=previous, locked_actors=('A1',)))


def test_pinned_indeterminate_count_can_construct_an_original_cast(generator):
    result = generator.generate(SemanticPromptRequest(seed=1, actor_count=2, scene_tags=('2others',)))
    assert all(actor.gender == 'unknown' for actor in result.scene.actors)
    assert not validate_scene(result.scene, generator.catalog)


def test_multiple_others_needs_two_indeterminate_actors(generator):
    result = generator.generate(SemanticPromptRequest(seed=42, actor_count=2, scene_tags=('multiple_others',)))
    assert all(actor.gender == 'unknown' for actor in result.scene.actors)
    assert not validate_scene(result.scene, generator.catalog)
    assert generator.import_tags('multiple_others').blocking


def test_male_maid_preplans_gender_without_changing_a_named_identity(generator):
    result = generator.generate(SemanticPromptRequest(seed=42, actor_tags=(('male_maid',),)))
    assert result.scene.actors[0].gender == 'male'
    assert not validate_scene(result.scene, generator.catalog)
    named = generator.import_tags('1girl, hatsune_miku, male_maid, maid')
    assert named.blocking and not named.english_prompt


@pytest.mark.parametrize('name,body', [('unworn_clothes', 'When an article of clothing is present in the image but it is not being worn by any character.'), ('unworn_shirt', 'A shirt that is not being worn.'), ('unworn_headwear', 'Any piece of headwear (a hat, a helmet, etc.) is present in the image, but nobody is wearing it.')])
def test_unworn_garment_proof_establishes_a_prop_not_a_worn_layer(name, body):
    rule, evidence = attribute_rule(name, {'body': body})
    assert rule['scope'] == 'object' and rule['slot'] == 'object'
    assert evidence['family'] == 'defined_unworn_garment_prop'
    unrelated = 'A hat is not being worn, while a shirt is worn.'
    assert attribute_rule('unworn_shirt', {'body': unrelated}) == (None, None)
    assert attribute_rule(name, {'body': 'Not ' + body}) == (None, None)
    assert infer_definition(name, {'body': body})[0] is None


@pytest.mark.parametrize('name', ['unworn_clothes', 'unworn_shirt', 'unworn_dress', 'unworn_shoes', 'unworn_headwear'])
def test_generated_unworn_garments_are_owned_props(generator, name):
    result = generator.generate(SemanticPromptRequest(seed=8000, actor_tags=((name,),), density='concise'))
    term = generator.catalog.term(name)
    assert any(obj.fact.term_key == term.key and obj.owner == 'A1' for obj in result.scene.objects)
    assert not any(fact.term_key == term.key for actor in result.scene.actors for fact in actor.facts)
    assert not validate_scene(result.scene, generator.catalog)
    assert 'wears unworn' not in result.english_prompt


def test_unworn_clothes_cannot_supply_adjusting_worn_clothes(generator):
    result = generator.import_tags('1girl, adjusting_clothes, unworn_clothes')
    assert result.blocking and not result.english_prompt


def test_unworn_headphones_do_not_supply_headphones_worn_around_the_neck(generator):
    result = generator.import_tags('1girl, headphones_around_neck, headphones_removed')
    assert result.blocking and not result.english_prompt


def test_identity_dependent_removed_garment_stays_pending(generator):
    row = generator.catalog.records['general:unworn eyepatch']
    assert row['status'] != 'reviewed'
    assert 'unworn_garment_context_required' in row['missing_reason']


def test_identity_guard_accepts_only_the_character_profile_sourced_trait():
    antenna = primitive('antennae', 'body.detail')
    antenna['conditions'] = ['original_only']
    rows = {'general:antennae': {'name': 'antennae', 'category': 'general', 'status': 'reviewed', 'rule': antenna}}
    profiles = {name: {'gender': 'female', 'identity': identity, 'age_state': 'unknown'} for name, identity in [('sourced', {'body.detail': 'antennae'}), ('other', {})]}
    cat = SemanticCatalog(data={'schema_version': 1, 'entries': rows, 'characters': profiles, 'aliases': {}, 'implications': {}, 'coverage': {}})
    fact = SceneFact('general:antennae')
    sourced = ScenePlan('daily', (SceneActor('A1', 'female', 'unknown', 'sourced', (fact,)),))
    assert not validate_scene(sourced, cat)
    assert validate_scene(replace(sourced, actors=(replace(sourced.actors[0], character='other'),)), cat)
