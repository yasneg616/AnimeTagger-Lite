"""Identification reviews retain source provenance without inventing scenes."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from app.errors import ConfigurationError
from app.prompts.review_metadata import validate_metadata
from app.prompts.semantic_catalog import SemanticCatalog
from app.prompts.semantic_prompt import SemanticPromptGenerator, SemanticPromptRequest
from scripts import review_prompt_metadata as review

ROOT = Path(__file__).resolve().parents[1]


def corpus():
    body = 'A sexual theme label for neutral indexing.'
    identity = 'general:review only sample'
    row = dict(name='review_only_sample', canonical='review only sample', category='general',
               status='candidate', source='https://danbooru.donmai.us/wiki_pages/review_only_sample',
               source_updated_at='2026-10-11T00:00:00Z', source_sha256=hashlib.sha256(body.encode()).hexdigest(),
               missing_reason='No generation rule', weight=1, sources=[])
    data = dict(schema_version=1, aliases={}, implications={}, characters={}, coverage=dict(usable_reviewed=0),
                entries={identity: row})
    item = review.candidate(row, identity, 'sexual_theme', ['own_intro'])
    return data, item, body


@pytest.mark.parametrize('name,body', [
    ('cumin', 'An aromatic seed used in cooking.'),
    ('cumulus', 'A type of cloud.'),
    ('cummerbund', 'A broad sash worn around the waist.'),
    ('holding_hands', 'Two characters holding hands.\nh4. See also\n* [[rape]]'),
    ('camera', 'A photographic device. Not to be confused with a sexual theme.'),
    ('nude', 'A character without clothing.'),
])
def test_unrelated_words_anatomy_and_later_sections_do_not_become_activity_labels(name, body):
    assert review.classify(name, body) == (None, [])


@pytest.mark.parametrize('name,body,group', [
    ('rape', 'A non-consensual sexual assault label.', 'nonconsensual_context'),
    ('neutral_index', 'A sexual fetish label.', 'sexual_theme'),
    ('sex', 'A sexual activity label.', 'explicit_activity'),
    ('shota', 'A youth depiction label.', 'age_sensitive_context'),
    ('cervix', 'An anatomical term.', 'anatomical_context'),
    ('hogtie', 'A restraint term.', 'restraint_context'),
])
def test_classification_is_a_neutral_candidate_group(name, body, group):
    assert review.classify(name, body)[0] == group


def test_identification_notes_are_immutable_and_do_not_create_terms():
    data, item, _ = corpus()
    data['aliases'] = {'legacy sample': item['canonical']}
    data['review_metadata'] = {item['key']: item}
    catalog = SemanticCatalog(data=data)
    assert catalog.identification_note('legacy_sample')['review_state'] == 'needs_review'
    assert catalog.term('review_only_sample') is None
    assert catalog.coverage['usable_reviewed'] == 0
    with pytest.raises(TypeError):
        catalog.identification_note('review_only_sample')['review_state'] = 'verified_identification'


@pytest.mark.parametrize('mutation', ['rule', 'age_state', 'source_sha256', 'source_url', 'canonical', 'empty_verified'])
def test_stale_provenance_and_generation_fields_cannot_be_imported(mutation):
    data, item, _ = corpus()
    if mutation in {'rule', 'age_state'}:
        item[mutation] = 'not accepted'
    elif mutation == 'empty_verified':
        item['review_state'] = 'verified_identification'
    else:
        item[mutation] = 'changed'
    with pytest.raises(ValueError):
        validate_metadata({item['key']: item}, data['entries'])


def test_verified_identification_still_has_no_generation_rule():
    data, item, _ = corpus()
    item.update(review_state='verified_identification', meaning_zh='用于中性索引的主题标签。')
    data['review_metadata'] = {item['key']: item}
    catalog = SemanticCatalog(data=data)
    assert catalog.identification_note('review_only_sample')['review_state'] == 'verified_identification'
    assert not catalog.terms and not catalog.characters


def test_weighted_import_preserves_raw_and_english_contains_only_known_facts():
    actual = json.loads((ROOT / 'resources/prompt_semantics/catalog.json').read_bytes())
    data, item, _ = corpus()
    actual['entries'].update(data['entries'])
    actual['review_metadata'] = {item['key']: item}
    generator = SemanticPromptGenerator(ROOT, catalog=SemanticCatalog(data=actual))
    result = generator.import_tags('1girl, (review_only_sample:1.25), blue_hair')
    assert result.scene.opaque_tokens == ('(review_only_sample:1.25)',)
    assert '(review_only_sample:1.25)' in result.tag_prompt
    assert 'blue hair' in result.english_prompt and 'review only' not in result.english_prompt
    assert any('识别资料待核对' in note for note in result.diagnostics)
    assert not result.blocking


def test_metadata_does_not_change_generated_scene_for_the_same_seed():
    original = json.loads((ROOT / 'resources/prompt_semantics/catalog.json').read_bytes())
    data, item, _ = corpus()
    changed = deepcopy(original)
    changed['entries'].update(data['entries'])
    changed['review_metadata'] = {item['key']: item}
    request = SemanticPromptRequest(seed=821, actor_count=2)
    before = SemanticPromptGenerator(ROOT, catalog=SemanticCatalog(data=original)).generate(request)
    after = SemanticPromptGenerator(ROOT, catalog=SemanticCatalog(data=changed)).generate(request)
    assert before.scene == after.scene and before.tag_prompt == after.tag_prompt
    assert before.english_prompt == after.english_prompt


def test_apply_accepts_only_editable_identification_fields_atomically(tmp_path, monkeypatch):
    data, item, body = corpus()
    monkeypatch.setattr(review, 'ROOT', tmp_path)
    cache = tmp_path / 'data/prompt-semantics'
    cache.mkdir(parents=True)
    (cache / 'wiki.json').write_text(json.dumps({'pages': {'review_only_sample': {'body': body}}}), encoding='utf-8')
    catalog_path = tmp_path / 'catalog.json'
    catalog_path.write_text(json.dumps(data), encoding='utf-8')
    input_path = tmp_path / 'input.jsonl'
    destination = tmp_path / 'annotations.json'
    item.update(review_state='verified_identification', meaning_zh='用于中性索引的主题标签。')
    input_path.write_text(json.dumps(item, ensure_ascii=False) + '\n', encoding='utf-8')
    result = review.apply(input_path, catalog_path, destination)
    assert result['registered'] == result['verified_identification'] == 1
    before = destination.read_bytes()
    item['rule'] = {'slot': 'action'}
    input_path.write_text(json.dumps(item, ensure_ascii=False), encoding='utf-8')
    with pytest.raises(ValueError):
        review.apply(input_path, catalog_path, destination)
    assert destination.read_bytes() == before


def test_duplicate_json_fields_are_rejected():
    with pytest.raises(ValueError, match='重复'):
        review.strict_json('{"key":"one","key":"two"}')


def test_suggested_alias_is_not_an_active_normalization_rule():
    data, item, _ = corpus()
    item['suggested_aliases'] = ['unverified_new_alias']
    data['review_metadata'] = {item['key']: item}
    catalog = SemanticCatalog(data=data)
    assert catalog.canonical('unverified_new_alias') == 'unverified new alias'
    assert catalog.identification_note('unverified_new_alias') is None


def test_invalid_metadata_is_an_actionable_configuration_error():
    data, item, _ = corpus()
    item['age_state'] = 'adult'
    data['review_metadata'] = {item['key']: item}
    with pytest.raises(ConfigurationError, match='识别资料字段'):
        SemanticCatalog(data=data)
