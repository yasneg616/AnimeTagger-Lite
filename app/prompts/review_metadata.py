"""Source-bound identification notes, separate from generatable scene rules."""
from __future__ import annotations

from types import MappingProxyType

GROUPS = {
    'explicit_activity': '露骨性行为词条',
    'nonconsensual_context': '非自愿或性暴力语境词条',
    'explicit_fluid_context': '性相关体液或露骨情境词条',
    'anatomical_context': '性器官或裸露细节待核对词条',
    'restraint_context': '束缚器具或情境待核对词条',
    'sexual_theme': '性主题或性癖语境待核对词条',
    'age_sensitive_context': '涉及年龄的敏感语境待核对词条',
    'other_sensitive_context': '其他敏感性语境待核对词条',
}
STATES = {'needs_review', 'verified_identification'}
FIELDS = {'key', 'name', 'canonical', 'review_group', 'review_state', 'label_zh', 'meaning_zh',
          'notes', 'suggested_aliases', 'source_url', 'source_updated_at', 'source_sha256', 'evidence_basis'}
EDITABLE = frozenset({'review_state', 'label_zh', 'meaning_zh', 'notes', 'suggested_aliases'})


def validate_metadata(data, entries):
    """Reject stale provenance and any attempt to supply generation controls."""
    if not isinstance(data, dict):
        raise ValueError('识别资料必须为对象')
    checked = {}
    for identity, item in data.items():
        if not isinstance(item, dict) or set(item) != FIELDS:
            raise ValueError(f'识别资料字段不正确：{identity}；只能填写指定资料字段')
        row = entries.get(identity)
        if not row or row.get('category') != 'general' or item['key'] != identity:
            raise ValueError(f'识别资料词条不在一般词清单中：{identity}')
        for field, source_field in (('name', 'name'), ('canonical', 'canonical'), ('source_url', 'source'),
                                    ('source_updated_at', 'source_updated_at'), ('source_sha256', 'source_sha256')):
            if item[field] != row.get(source_field):
                raise ValueError(f'识别资料来源或名称已变更：{identity}/{field}；请重新导出')
        if item['review_group'] not in GROUPS or item['review_state'] not in STATES:
            raise ValueError(f'无效的识别资料分组或状态：{identity}')
        for field, maximum in (('label_zh', 100), ('meaning_zh', 240), ('notes', 500)):
            value = item[field]
            if not isinstance(value, str) or len(value) > maximum or any(ord(char) < 32 for char in value):
                raise ValueError(f'识别资料文本过长或含控制字符：{identity}/{field}')
        if not item['label_zh'].strip():
            raise ValueError(f'识别资料名称不能为空：{identity}')
        if item['review_state'] == 'verified_identification' and (not item['meaning_zh'].strip() or not item['source_sha256']):
            raise ValueError(f'核对后必须填写中性释义并有对应来源：{identity}')
        for field in ('suggested_aliases', 'evidence_basis'):
            values = item[field]
            if not isinstance(values, list) or len(values) > 30 or any(not isinstance(value, str) or not value.strip()
                or len(value) > 150 or any(ord(char) < 32 for char in value) for value in values):
                raise ValueError(f'识别资料列表不正确：{identity}/{field}')
        if not set(item['evidence_basis']) <= {'tag_name', 'own_intro'} or not item['evidence_basis']:
            raise ValueError(f'识别资料缺少分类依据：{identity}')
        copied = dict(item)
        copied['suggested_aliases'] = tuple(item['suggested_aliases'])
        copied['evidence_basis'] = tuple(item['evidence_basis'])
        checked[identity] = MappingProxyType(copied)
    return MappingProxyType(checked)
