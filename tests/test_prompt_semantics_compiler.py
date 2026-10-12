"""Evidence adapters must establish facts, ownership and usable dependencies."""
from dataclasses import replace
from pathlib import Path

import pytest

from app.prompts.normalizer import canonical_tag_key as key
from app.prompts.semantic_catalog import SemanticCatalog
from app.prompts.semantic_prompt import SemanticPromptGenerator, SemanticPromptRequest
from app.prompts.semantic_rules import primitive
from app.prompts.semantic_scene import SceneActor, SceneFact, ScenePlan, validate_scene
from scripts.build_prompt_semantics import character_profile
from scripts.prompt_semantic_characters import age_evidence, reference_profile
from scripts.prompt_semantic_dependencies import dependent_rule, hand_holdable
from scripts.prompt_semantic_families import infer_definition
from scripts.prompt_semantic_negation import HAND_WRITTEN, negation_rule
from scripts.prompt_semantic_species import species_feature_rule

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('name,body,slot', (
    ('custom_camera', 'A compact camera used for photography. An unrelated example is a hat.', 'object'),
    ('chiton', "A Greco-Roman 'tunic' (or 'robe').", 'outfit'),
    ('model_knife', 'The model knife is a small, portable knife with a wooden grip.', 'object'),
))
def test_definition_uses_the_positive_first_sentence(name, body, slot):
    rule, evidence, reason = infer_definition(name, {'body': body})
    assert not reason and rule['slot'] == slot and evidence['definition']


@pytest.mark.parametrize('name,body', (
    ('absolutely_everyone', 'An image depicting every character. The background has a hat.'),
    ('aiming', 'A character aiming a weapon.'),
    ('pubic_hair', 'Hair growing around the genitals.'),
    ('bad_unknown', 'An unspecified concept. A related object is a knife.'),
))
def test_unrelated_or_incomplete_definitions_do_not_establish_a_rule(name, body):
    rule, _, _ = infer_definition(name, {'body': body})
    assert rule is None or rule['slot'] != 'hair.color'
    if name != 'pubic_hair':
        assert rule is None


def appearance_rules():
    return {key(name): primitive(name, slot) for name, slot in (
        ('blue_hair', 'hair.color'), ('short_hair', 'hair.length'), ('green_eyes', 'eyes.color'),
        ('red_hair', 'hair.color'), ('white_shirt', 'top'))}


def test_own_character_prose_separates_wardrobe_and_accessory_colors():
    page = {'body': "Alice has [[short_hair|short]] [[blue_hair]] and [[green_eyes]]. She wears a [[white_shirt]]. Her sister has [[red_hair]]. Alice has a red hair bow.", 'other_names': []}
    profile = character_profile('alice_example', page, {}, {}, appearance_rules())
    assert profile['identity'] == {'hair.color': 'blue_hair', 'hair.length': 'short_hair', 'eyes.color': 'green_eyes'}
    assert profile['wardrobe'] == {'top': 'white_shirt'}
    assert profile['age_state'] == 'unknown'


def test_implicit_subject_is_limited_to_default_appearance_sections():
    page = {'body': 'h4. Appearance\nHas [[blue_hair]] and [[green_eyes]].\nh4. Alternate costume\nHas [[red_hair]].'}
    profile = character_profile('example', page, {}, {}, appearance_rules())
    assert profile['gender'] == 'unknown'
    assert profile['identity']['hair.color'] == 'blue_hair'


def reference_records():
    return {'references': {'example': {'references': [{'id': 1, 'wiki_line': '!post #1'}]}},
            'posts': {'1': {'id': 1, 'rating': 'g', 'tag_string_meta': 'official_art',
                'tag_string_character': 'example', 'tag_string_general': '1girl blue_hair green_eyes short_hair'}}}


@pytest.mark.parametrize('mutation', ('foreign_owner', 'nonofficial', 'variant', 'multi_people'))
def test_reference_must_be_official_single_owner_default(mutation):
    records = reference_records()
    post = records['posts']['1']
    if mutation == 'foreign_owner':
        post['tag_string_character'] += ' another_character'
    elif mutation == 'nonofficial':
        post['tag_string_meta'] = ''
    elif mutation == 'variant':
        post['tag_string_general'] += ' alternate_hair_color'
    else:
        post['tag_string_general'] = post['tag_string_general'].replace('1girl', '2girls')
    profile, reason = reference_profile('example', {'body': ''}, records, appearance_rules(), key, lambda _: (), {})
    assert profile is None and reason


def test_reference_disagreement_does_not_lock_an_unproven_attribute():
    records = reference_records()
    records['references']['example']['references'].append({'id': 2, 'wiki_line': '!post #2'})
    records['posts']['2'] = {**records['posts']['1'], 'id': 2,
                           'tag_string_general': '1girl red_hair green_eyes short_hair'}
    profile, reason = reference_profile('example', {'body': ''}, records, appearance_rules(), key, lambda _: (), {})
    assert profile is not None and not reason
    assert 'hair.color' not in profile['identity'] and profile['uncertain_slots']['hair.color']


def test_age_requires_actual_age_evidence():
    assert age_evidence('example', 'Licensed and published character.')[0] == 'unknown'
    assert age_evidence('example', 'Age: 21\n')[0] == 'adult'
    assert age_evidence('example', 'Age: 16\n')[0] == 'minor'
    assert age_evidence('example', 'Age: 16\nAge: 21\n')[0] == 'unknown'
    assert age_evidence('example', 'She is 500 years old with a child-like appearance.')[0] == 'unknown'


def test_generic_holding_has_only_portable_candidates():
    assert hand_holdable('camera', primitive('camera', 'object'))
    assert hand_holdable('white_shirt', {'object_capable': True})
    for name in ('bed', 'aircraft', 'tank', 'bear', 'building', 'piano'):
        assert not hand_holdable(name, {'head': name})
    catalog = SemanticCatalog()
    holding = catalog.term('holding')
    assert holding.any_dependencies
    assert all(catalog.term(reference.split(':', 1)[1]).name not in {'bed', 'aircraft', 'tank', 'bear', 'piano'}
               for reference in holding.any_dependencies[0])


def test_removed_garment_is_an_owned_unworn_prop():
    shirt = {**primitive('shirt', 'top'), 'object_capable': True}
    rule, evidence = dependent_rule('shirt_removed', {'body': 'A shirt that has been removed.'}, lambda name: shirt if name == 'shirt' else None)
    assert evidence and rule['requires'] == ['object:shirt']
    assert 'top:shirt' in rule['excludes'] and 'unworn' in rule['phrase']


@pytest.fixture(scope='module')
def generator():
    return SemanticPromptGenerator(ROOT)


def test_existing_character_wardrobe_can_change_without_erasing_identity(generator):
    profile = generator.catalog.character('satake_minako')
    result = generator.generate(SemanticPromptRequest(seed=1190, characters=(profile.name,), content='adult', actor_tags=(('nude',),)))
    assert not validate_scene(result.scene, generator.catalog)
    names = {generator.catalog.terms[f.term_key].name for f in result.scene.actors[0].facts}
    assert {generator.catalog.term(name).name for _, name in profile.identity} <= names
    assert not any(generator.catalog.terms[f.term_key].slot in {'outfit', 'top', 'bottom'} for f in result.scene.actors[0].facts)
    assert 'adult' not in result.english_prompt.lower()


def test_partial_identity_never_invents_missing_physical_attributes(generator):
    profile = next(p for p in generator.catalog.characters.values() if p.kind == 'humanoid' and p.identity and not any(slot == 'body.horns' for slot, _ in p.identity))
    facts = tuple(SceneFact(generator.catalog.term(name).key) for _, name in profile.identity)
    actor = SceneActor('A1', profile.gender, profile.age_state, profile.name, facts, profile.kind)
    horns = generator.catalog.term('horns')
    scene = ScenePlan('daily', (replace(actor, facts=(*facts, SceneFact(horns.key))),))
    assert any('身份依据' in error for error in validate_scene(scene, generator.catalog))


def test_component_colors_and_presence_are_scoped(generator):
    def fact(name):
        return SceneFact(generator.catalog.term(name).key)
    base = SceneActor('A1', facts=(fact('white_shirt'), fact('blue_sleeves')))
    scene = ScenePlan('daily', (base, SceneActor('A2', facts=(fact('white_shirt'), fact('red_sleeves')))))
    assert not validate_scene(scene, generator.catalog)
    conflict = replace(scene, actors=(replace(base, facts=(*base.facts, fact('red_sleeves'))), scene.actors[1]))
    assert any('color' in error for error in validate_scene(conflict, generator.catalog))
    missing = ScenePlan('daily', (SceneActor('A1', facts=(fact('no_eyes'), fact('blue_eyes'))),))
    assert validate_scene(missing, generator.catalog)


def test_directional_relations_wait_for_ordered_assignment(generator):
    text = '2girls, hand_on_another\'s_head'
    pending = generator.import_tags(text)
    assert pending.unassigned and not pending.english_prompt
    assigned = generator.import_tags(text, assignments={1: ('A2', 'A1')})
    assert not assigned.blocking and not assigned.unassigned
    assert assigned.scene.interactions[0].participants == ('A2', 'A1')
    assert 'Character 2' in assigned.english_prompt and "Character 1's" in assigned.english_prompt


def test_explicit_layers_allow_two_tops_but_unmarked_overlap_conflicts(generator):
    facts = tuple(SceneFact(generator.catalog.term(name).key) for name in ('white_shirt', 'blue_shirt'))
    scene = ScenePlan('daily', (SceneActor('A1', facts=facts),))
    assert validate_scene(scene, generator.catalog)
    layered = replace(scene, actors=(replace(scene.actors[0], facts=(*facts, SceneFact(generator.catalog.term('layered_clothes').key))),))
    assert not validate_scene(layered, generator.catalog)


def test_original_identity_conditions_are_scoped_to_their_actor(generator):
    result = generator.generate(SemanticPromptRequest(seed=42, actor_count=2, characters=('', 'hatsune_miku'), actor_tags=(('nurse',),)))
    assert result.scene.actors[1].character == 'hatsune_miku'
    assert not validate_scene(result.scene, generator.catalog)


def test_canonical_lookup_can_use_a_reviewed_legacy_alias():
    catalog = SemanticCatalog(data={'schema_version': 1, 'aliases': {'old knife': 'knife'}, 'implications': {},
        'characters': {}, 'coverage': {}, 'entries': {'general:old knife': {
            'name': 'old_knife', 'category': 'general', 'status': 'reviewed', 'rule': primitive('knife', 'object')}}})
    assert catalog.term('knife').generatable
    assert catalog.term('old_knife') is catalog.term('knife')


def test_native_literal_emote_punctuation_survives_tags_and_import(generator):
    from app.prompts.injection import parse_injections, token_key
    result = generator.generate(SemanticPromptRequest(seed=3, actor_tags=((';)',),)))
    assert ';\\)' in result.tag_prompt
    assert any(token_key(token) == ';)' for token in parse_injections(result.tag_prompt))
    imported = generator.import_tags(result.tag_prompt)
    assert ';)' not in {token_key(token) for token in imported.scene.opaque_tokens}
    assert token_key(r'\(literal\)') == '(literal)'


def test_garment_ornaments_require_the_correct_owned_garment(generator):
    for name, slot in (('hat_belt', 'headwear'), ('hat_bow', 'headwear'), ('shoe_bow', 'footwear')):
        term = generator.catalog.term(name)
        scene = ScenePlan('daily', (SceneActor('A1', facts=(SceneFact(term.key),)),))
        assert any(slot in error for error in validate_scene(scene, generator.catalog))
        result = generator.generate(SemanticPromptRequest(seed=4, actor_tags=((name,),)))
        assert any(generator.catalog.terms[f.term_key].slot == slot for f in result.scene.actors[0].facts)
    assert generator.catalog.term('pole').scope == 'object'
    assert generator.catalog.term('recording').slot != 'location'
    assert generator.catalog.term('lamppost').slot != 'location'
    assert generator.catalog.term('translucent_bunnysuit').adult
    assert generator.catalog.term('ribbon_in_mouth').requires == ('object:ribbon',)


def test_place_words_inside_objects_and_image_metadata_are_not_scene_locations(generator):
    expected = {'health_bar': 'symbol', 'chocolate_bar': 'object', "bishamonten's_pagoda": 'object',
                'negative_space': 'framing', 'pool_ladder': 'object', 'sand_castle': 'scene.detail',
                'skyline': 'scene.detail', 'spreader_bar': 'object'}
    for name, slot in expected.items():
        assert generator.catalog.term(name).slot == slot
    assert generator.catalog.term('breaker_gorgon') is None or not generator.catalog.term('breaker_gorgon').generatable
    assert generator.catalog.term('projectile_cum') is None or not generator.catalog.term('projectile_cum').generatable
    assert generator.catalog.term('wrestling_ring').slot == 'location'
    assert generator.catalog.term('picture_frame').scope == 'object'
    assert generator.catalog.term('antennae').scope == 'actor'
    assert generator.catalog.term('mimic_chest').scope == 'object'
    assert generator.catalog.term('deer').scope == 'object'
    assert generator.catalog.term('pompadour').slot == 'hair.style'


def test_raised_arms_do_not_also_reach_into_a_pocket(generator):
    from app.errors import ConfigurationError
    with pytest.raises(ConfigurationError):
        generator.generate(SemanticPromptRequest(seed=8, actor_tags=(('arms_up', 'hand_in_pocket'),)))


def test_lap_resting_requires_two_owned_participant_poses(generator):
    result = generator.generate(SemanticPromptRequest(seed=4, actor_count=2, action='lap_pillow'))
    relation = next(value for value in result.scene.interactions if generator.catalog.terms[value.fact.term_key].name == 'lap_pillow')
    poses = {actor.actor_id: {generator.catalog.terms[fact.term_key].name for fact in actor.facts} for actor in result.scene.actors}
    assert 'lying' in poses[relation.participants[0]]
    assert 'sitting' in poses[relation.participants[1]]
    assert not any(generator.catalog.terms[item.fact.term_key].name == 'lap_pillow' for item in result.scene.objects)


def test_no_outer_bottoms_still_requires_actual_top_and_underwear(generator):
    result = generator.generate(SemanticPromptRequest(seed=4, content='adult', actor_tags=(('no_pants',),)))
    slots = {generator.catalog.terms[f.term_key].slot for f in result.scene.actors[0].facts}
    assert {'top', 'underwear.bottom'} <= slots
    assert 'bottom' not in slots and 'outfit' not in slots


@pytest.mark.parametrize('name', ('standing_on_one_leg', 'tiptoes', 'wading'))
def test_weight_bearing_poses_cannot_be_combined_with_lying(generator, name):
    from app.errors import ConfigurationError
    result = generator.generate(SemanticPromptRequest(seed=16, actor_tags=((name,),)))
    assert any(generator.catalog.canonical(generator.catalog.terms[f.term_key].name) == 'standing'
               or 'standing' in generator.catalog.implied(generator.catalog.terms[f.term_key].name)
               for f in result.scene.actors[0].facts)
    with pytest.raises(ConfigurationError):
        generator.generate(SemanticPromptRequest(seed=16, actor_tags=((name, 'lying'),)))
    assert generator.import_tags('1girl, ' + name + ', lying').blocking


def test_eyewear_property_and_plural_garments_have_meaningful_english(generator):
    result = generator.generate(SemanticPromptRequest(seed=4, actor_tags=(('bespectacled', 'idol_clothes', 'waraji'),)))
    assert 'wears a bespectacled' not in result.english_prompt
    assert 'an idol clothes' not in result.english_prompt
    assert 'straw-rope sandals' in result.english_prompt


def test_known_character_does_not_randomly_acquire_unverified_clothes(generator):
    result = generator.generate(SemanticPromptRequest(seed=7, characters=('hatsune_miku',), density='rich'))
    assert not any(generator.catalog.terms[f.term_key].slot in {'outfit', 'top', 'bottom', 'outerwear', 'footwear'} for f in result.scene.actors[0].facts)


def test_tail_interaction_materializes_the_receivers_tail(generator):
    result = generator.generate(SemanticPromptRequest(seed=23, actor_count=2, action="holding_another's_tail"))
    relation = result.scene.interactions[0]
    recipient = next(actor for actor in result.scene.actors if actor.actor_id == relation.participants[1])
    assert any(generator.catalog.terms[f.term_key].slot == 'body.tail' for f in recipient.facts)
    assert not validate_scene(result.scene, generator.catalog)


def test_every_required_entity_is_representable_as_an_owned_object(generator):
    for term in generator.catalog.terms.values():
        if not term.generatable:
            continue
        for reference in (*term.requires, *(ref for group in term.role_requires for ref in group)):
            if reference.startswith('object:'):
                parent = generator.catalog.term(reference.split(':', 1)[1])
                assert parent and parent.generatable and (parent.scope == 'object' or parent.object_capable), term.name


@pytest.mark.parametrize('name', ('cross', 'mahjong_tile', 'ofuda', 'petal', 'plant', 'torch'))
def test_physical_props_roundtrip_through_a_holding_scene(generator, name):
    text = '1girl, holding_' + name + ', ' + name
    imported = generator.import_tags(text)
    assert not imported.blocking and not imported.unassigned
    assert imported.scene.objects and imported.english_prompt
    generated = generator.generate(SemanticPromptRequest(seed=181, actor_count=2, actor_tags=(('holding_' + name,),)))
    assert any(item.owner == 'A1' and generator.catalog.canonical(generator.catalog.terms[item.fact.term_key].name) == generator.catalog.canonical(name) for item in generated.scene.objects)
    assert not validate_scene(generated.scene, generator.catalog)


def test_multitoken_prop_owner_is_requested_using_its_canonical_name(generator):
    text = '2girls, holding_mahjong_tile, mahjong_tile'
    pending = generator.import_tags(text, assignments={1: 'A1'})
    assert [(row.index, row.kind) for row in pending.unassigned] == [(2, 'object')]
    resolved = generator.import_tags(text, assignments={1: 'A1', 2: 'A1'})
    assert not resolved.blocking and not resolved.unassigned and resolved.english_prompt


@pytest.mark.parametrize('name,body,species,gender', (
    ('bat_girl', 'Girls with intrinsic bat (animal) features, such as bat ears and bat wings.', 'bat', 'gender:female'),
    ('jaguar_girl', 'A girl with jaguar-like features, such as jaguar ears or a jaguar tail.', 'jaguar', 'gender:female'),
    ('snow_leopard_boy', 'A boy with snow leopard traits such as snow leopard ears or a snow leopard tail.', 'snow leopard', 'gender:male'),
    ('dragon_boy', 'A male who has some features of a dragon such as horns, wings and a serpentine tail.', 'dragon', 'gender:male'),
    ('spider_girl', 'A spider-themed monster girl. Spider girls often have extra eyes or extra arms.', 'spider', 'gender:female'),
))
def test_species_features_are_owned_traits_of_the_subject(name, body, species, gender):
    """A "girl with X features" passage is a trait the subject owns."""
    rule, evidence = species_feature_rule(name, {'body': body})
    assert rule['slot'] == 'body.species' and rule['scope'] == 'actor'
    assert rule['features'] == {'body.species': species}
    assert rule['conditions'] == ['original_only', gender]
    assert evidence['family'] == 'species_feature_trait' and evidence['species']
    # A species trait is a bodily fact, never an object the subject holds.
    assert not rule['requires'] and 'role_requires' not in rule


def test_species_trait_is_extracted_from_the_tag_not_a_borrowed_species():
    """A reptile girl is defined by lizard traits but owns the reptile trait."""
    rule, evidence = species_feature_rule(
        'reptile_girl', {'body': 'A girl with lizard characteristics such as lizard tail and scales.'})
    assert rule['features'] == {'body.species': 'reptile'}
    assert evidence['species'] == 'lizard'
    assert rule['phrase'] == 'having traits of reptile'


@pytest.mark.parametrize('name,body', (
    ('ghost_girl', 'A female ghost.'),
    ('fish_girl', 'A fish-like monster girl with human legs, unlike a mermaid.'),
    ('lion_girl', 'A variant of the common cat girl, featuring traits from Panthera leo.'),
    ('shark_girl', 'A mermaid or fish girl with shark-like traits.'),
    ('raccoon_girl', 'Girls with intrinsic raccoon or tanuki (raccoon-dog) features.'),
))
def test_being_the_creature_or_an_ambiguous_species_is_not_a_trait(name, body):
    """Stating the subject *is* the creature asserts no bodily trait to model."""
    rule, _ = species_feature_rule(name, {'body': body})
    assert rule is None


@pytest.mark.parametrize('name,body', (
    ('fictional_girl', 'A girl with feathered dragon-like features.'),
    ('madeup_girl', 'A girl with quux-like features and a quux tail.'),
))
def test_a_species_without_a_reviewed_trait_is_not_invented(name, body):
    """A prose match cannot introduce a species the catalog cannot express."""
    rule, _ = species_feature_rule(name, {'body': body})
    assert rule is None


def test_species_traits_carry_no_age_claim():
    """A species trait never asserts an age, in either direction."""
    rule, _ = species_feature_rule('bat_girl', {'body': 'Girls with intrinsic bat features.'})
    assert 'age:minor' not in rule['conditions']
    assert rule['adult'] is False


@pytest.mark.parametrize('name,body', (
    ('cow_boy', 'A boy who works on a ranch with cattle.'),
    ('teddy_boy', 'A boy holding a teddy bear.'),
))
def test_non_species_compounds_are_not_mistaken_for_species_traits(name, body):
    rule, _ = species_feature_rule(name, {'body': body})
    assert rule is None


def negation_lookup(name):
    """Reviewed rules for the items the absence tags below refer to."""
    return {key(item): primitive(item, slot) for item, slot in (
        ('cape', 'outerwear'), ('coat', 'outerwear'), ('jacket', 'outerwear'),
        ('mask', 'accessory'), ('blindfold', 'accessory'), ('eyepatch', 'accessory'),
        ('mole', 'body.detail'), ('halo', 'body.halo'))}.get(key(name))


@pytest.mark.parametrize('name,body,slot', (
    ('no_cape', 'A character not wearing a cape.', 'outerwear'),
    ('no_jacket', 'A character without a jacket.', 'outerwear'),
    ('no_mask', 'A character whose mask is removed.', 'accessory'),
    ('no_mole', 'A face lacking a mole.', 'body.detail'),
))
def test_absence_excludes_the_slot_of_the_named_item(name, body, slot):
    rule, evidence = negation_rule(name, {'body': body}, negation_lookup)
    item = key(name).split(' ', 1)[1]
    assert rule['excludes'] == ['attribute:' + item]
    assert rule['features'] == {'absent.item.' + item: 'yes'}
    assert evidence['family'] == 'absent_attribute' and evidence['absent_slot'] == slot


def test_absence_of_a_worn_item_keeps_the_worn_garment_prerequisite():
    worn, _ = negation_rule('no_cape', {'body': 'Not wearing a cape.'}, negation_lookup)
    assert worn['required_slots']
    body_part, _ = negation_rule('no_mole', {'body': 'Lacking a mole.'}, negation_lookup)
    assert 'required_slots' not in body_part


@pytest.mark.parametrize('name,body', (
    ('no_cape', 'A cape is a sleeveless outer garment.'),
    ('no_mask', 'A mask is a covering worn over the face.'),
))
def test_naming_the_item_is_not_evidence_that_it_is_absent(name, body):
    """A page that defines the item does not establish the absence tag."""
    rule, _ = negation_rule(name, {'body': body}, negation_lookup)
    assert rule is None


def test_absence_of_an_unmodelled_item_is_not_guessed():
    rule, _ = negation_rule('no_dickey', {'body': 'Missing the dickey.'}, negation_lookup)
    assert rule is None


@pytest.mark.parametrize('name', ('no_shoes', 'no_panties', 'no_shirt'))
def test_hand_written_absence_rules_are_never_replaced(name):
    """A general grammar must not overwrite a deliberate reviewed rule."""
    assert key(name) in HAND_WRITTEN
    rule, _ = negation_rule(name, {'body': 'Not wearing it.'}, negation_lookup)
    assert rule is None


def test_absence_does_not_invent_a_content_level():
    """An absence carries the item's own classification and no age claim."""
    rule, _ = negation_rule('no_mole', {'body': 'Lacking a mole.'}, negation_lookup)
    assert rule['adult'] is False
    assert not any(condition.startswith('age:') for condition in rule.get('conditions', ()))


@pytest.mark.parametrize('name,body,slot', (
    ('missing_tail', 'A character who normally has a tail is depicted without it.', 'body.tail'),
    ('missing_wings', 'When a winged character is depicted without wings.', 'body.wings'),
    ('missing_halo', 'When a character who normally has a halo is depicted without one.', 'body.halo'),
    ('missing_headwear', 'A character who normally wears headwear is shown without it.', 'headwear'),
    ('missing_legwear', 'A character who normally wears pantyhose is shown without their legwear.', 'legwear'),
))
def test_missing_identity_trait_waits_for_a_baseline_model(name, body, slot):
    rule, evidence = negation_rule(name, {'body': body}, negation_lookup)
    assert rule is None and evidence is None


def test_literal_body_feature_absence_needs_no_other_garment():
    """Literal absence and absence relative to a known identity are different."""
    rule, _ = negation_rule('without_tail', {'body': 'Depicted without a tail.'}, negation_lookup)
    assert 'required_slots' not in rule
    worn, _ = negation_rule('without_headwear', {'body': 'Shown without headwear.'}, negation_lookup)
    assert worn['required_slots']


def test_missing_item_without_a_known_slot_is_not_guessed():
    """A missing part the catalog cannot express stays in the work queue."""
    rule, _ = negation_rule('missing_eye', {'body': 'A character with a single missing eye.'}, negation_lookup)
    assert rule is None



