"""Default references must be tied to their actual owner and version."""
from copy import deepcopy
import re

import pytest

from app.prompts.normalizer import canonical_tag_key as key
from app.prompts.semantic_rules import primitive
from scripts.fetch_character_references import appearance_references
from scripts.prompt_semantic_characters import reference_profile
from scripts.build_prompt_semantics import character_profile


def test_nested_regular_costumes_select_only_explicit_default():
    body = ('h4. Appearance\nh5. Regular costumes\n'
            '* !post #11: [[example (1st costume)|1st costume]]: Default\n'
            '* !post #12: [[example (casual)|Casual]]\n'
            'h5. Other costumes\n* !post #13: Default\n'
            'h4. See also\n* !post #14: Default')
    refs = appearance_references(body)
    assert [ref['id'] for ref in refs] == [11]
    assert refs[0]['explicit_default']


@pytest.mark.parametrize('heading', ['Default', 'Original', 'Default appearance'])
def test_default_heading_can_bind_an_unlabelled_reference(heading):
    refs = appearance_references(f'h4. Appearance\nh6. {heading}\n!asset #21\nh6. Other\n!asset #22')
    assert [ref['id'] for ref in refs] == [21] and refs[0]['explicit_default']


@pytest.mark.parametrize('caption', ['Alternate default', 'Swimsuit', 'Not default', 'Second ascension', 'Remodel', 'Default form', 'Anniversary costume'])
def test_variant_or_negative_caption_is_not_a_default(caption):
    assert not appearance_references('h4. Appearance\nh5. Regular costumes\n!post #1: ' + caption)


def test_named_form_or_variant_section_never_becomes_base_appearance():
    body = 'h4. Appearance\nh6. [[Example (young)|Young]]\n!post #1: Default\nh6. [[Example (old)|Old]]\n!post #2: Default'
    assert not appearance_references(body)


def test_reference_can_use_a_declared_default_costume_descendant_only():
    rules = {key(name): primitive(name, slot) for name, slot in [('blue_hair', 'hair.color'), ('green_eyes', 'eyes.color')]}
    reference = {'id': 1, 'wiki_line': '!post #1', 'caption': '[[example (default)|Default]]', 'explicit_default': True}
    post = {'id': 1, 'rating': 'g', 'tag_string_meta': 'official_art', 'tag_string_character': 'example example_(default)', 'tag_string_general': '1girl blue_hair green_eyes'}
    records = {'references': {'example': {'references': [reference]}}, 'posts': {'1': post}}
    implied = lambda name: {'example'} if name == 'example (default)' else set()
    profile, reason = reference_profile('example', {'body': ''}, records, rules, key, implied, {})
    assert profile and not reason and profile['age_state'] == 'unknown'
    for mutation in ['caption', 'implication', 'foreign', 'not_default']:
        changed = deepcopy(records)
        relationships = implied
        if mutation == 'caption': changed['references']['example']['references'][0]['caption'] = '[[another|Default]]'
        if mutation == 'implication': relationships = lambda _: set()
        if mutation == 'foreign': changed['posts']['1']['tag_string_character'] += ' stranger'
        if mutation == 'not_default': changed['references']['example']['references'][0]['explicit_default'] = False
        assert reference_profile('example', {'body': ''}, changed, rules, key, relationships, {})[0] is None


@pytest.mark.parametrize('body', [
    'Appearance-wise, she has short blue hair and green eyes.',
    'For her default hairstyle, she has short blue hair and green eyes.',
    'For her default hairstyle with this costume, she has short blue hair and green eyes.',
    'She has short, streaked, blue hair and green eyes.',
    'She has short-length blue hair and green eyes.',
])
def test_default_prose_and_comma_separated_length_keep_own_attribution(body):
    rules = {key(name): primitive(name, slot) for name, slot in [('blue_hair', 'hair.color'), ('green_eyes', 'eyes.color'), ('short_hair', 'hair.length')]}
    profile = character_profile('example', {'body': body}, {}, {}, rules)
    assert profile['identity']['hair.length'] == 'short_hair'
    assert profile['identity']['hair.color'] == 'blue_hair' and profile['age_state'] == 'unknown'
    assert character_profile('example', {'body': re.sub('she has', 'her sister has', body, flags=re.I)}, {}, {}, rules) is None
    if 'default hairstyle' in body:
        assert character_profile('example', {'body': body.replace('default hairstyle', 'alternate hairstyle')}, {}, {}, rules) is None
