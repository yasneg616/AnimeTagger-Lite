"""Export and apply sourced age evidence for character profiles.

Why this exists
---------------
Adult content is gated on a profile whose age is *established by a source*.
Publication dates, image ratings, apparent maturity, franchise popularity and
count tags are explicitly not age evidence, and unknown ages are never
bulk-promoted. This tool makes that gate auditable instead of invisible:

* ``export`` writes one row per profile with the exact reason it is withheld and
  blank fields for the reviewer to fill in.
* ``apply`` accepts only rows carrying a dated source excerpt, and refuses
  placeholder or blanket-batch input.

Nothing here creates generation rules, and nothing here changes a profile's
documented appearance. Filling a row cannot by itself make a profile eligible:
the identity gate still has to pass on its own terms.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CATALOG = ROOT / 'resources' / 'prompt_semantics' / 'catalog.json'
DEFAULT_OUTPUT = ROOT / 'validation' / 'semantic-completion-final' / '相关词条整理'

# Fields the reviewer fills in. Everything else is generated and must match.
EVIDENCE_FIELDS = (
    'age_state_proposed', 'stated_age', 'source_url', 'source_excerpt',
    'source_recorded_at', 'identity_hair.color', 'identity_hair.length',
    'identity_hair.style', 'identity_eyes.color', 'identity_skin.color', 'notes',
)
GENERATED_FIELDS = ('key', 'name', 'current_age_state', 'kind', 'gender', 'copyrights',
                    'identity_slots_present', 'wardrobe_slots_present', 'withheld_reason')
TEMPLATE_FIELDS = GENERATED_FIELDS + EVIDENCE_FIELDS

STATES = {'', 'needs_review', 'verified_age_adult', 'verified_age_minor', 'verified_age_unknown'}
ADULT_MIN_IDENTITY = 2
MIN_EXCERPT = 20

# Statements that are not age evidence. Matched case-insensitively against the
# reviewer's excerpt so a reasoned-looking sentence cannot stand in for a source.
NOT_AGE_EVIDENCE = (
    r'published', r'released? in \d{4}', r'first appeared', r'debut',
    r'rating', r'rated', r'explicit', r'nsfw', r'mature', r'adult[- ]looking',
    r'looks? (?:like )?(?:an )?adult', r'appears? to be \d+', r'presumably',
    r'assumed', r'probably', r'likely \d+', r'popular', r'1girl', r'1boy',
    r'everyone', r'all characters', r'blanket', r'bulk', r'batch',
)
CONTROL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
URL = re.compile(r'^https?://[^\s]+$')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def withheld_reason(profile) -> str:
    """The single most specific reason this profile is not adult-eligible."""
    kind = profile.get('kind') or 'humanoid'
    state = profile.get('age_state') or 'unknown'
    identity = profile.get('identity') or {}
    if kind != 'humanoid':
        return 'non_humanoid_kind'
    if state == 'minor':
        return 'source_says_minor'
    if state != 'adult':
        return 'age_not_established'
    if len(identity) < ADULT_MIN_IDENTITY:
        return 'identity_below_minimum'
    return ''


def is_adult_eligible(profile) -> bool:
    return withheld_reason(profile) == ''


def export(catalog_path: Path, output: Path) -> dict:
    data = json.loads(Path(catalog_path).read_bytes())
    characters = data['characters']
    rows, template = [], []
    for name in sorted(characters):
        profile = characters[name]
        identity = profile.get('identity') or {}
        wardrobe = profile.get('wardrobe') or {}
        reason = withheld_reason(profile)
        generated = {
            'key': name,
            'name': name,
            'current_age_state': profile.get('age_state') or 'unknown',
            'kind': profile.get('kind') or 'humanoid',
            'gender': profile.get('gender') or 'unknown',
            'copyrights': ' | '.join(profile.get('copyrights') or ()),
            'identity_slots_present': ' | '.join(sorted(identity)),
            'wardrobe_slots_present': ' | '.join(sorted(wardrobe)),
            'withheld_reason': reason,
        }
        rows.append({**generated, 'adult_eligible': 'no' if reason else 'yes'})
        template.append({**generated, **{field: '' for field in EVIDENCE_FIELDS}})
    output.mkdir(parents=True, exist_ok=True)
    tsv = output / '角色年龄证据_待填.tsv'
    with tsv.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=[*GENERATED_FIELDS, 'adult_eligible', *EVIDENCE_FIELDS], delimiter='\t')
        writer.writeheader()
        writer.writerows(rows)
    template_path = output / '角色年龄证据_填写模板.jsonl'
    with template_path.open('w', encoding='utf-8', newline='\n') as handle:
        for row in template:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    reasons = Counter(row['withheld_reason'] or 'adult_eligible' for row in rows)
    summary = {
        'catalog_sha256': sha(catalog_path),
        'profiles': len(rows),
        'adult_eligible': sum(1 for row in rows if not row['withheld_reason']),
        'withheld_by_reason': dict(reasons),
        'tsv': str(tsv.relative_to(ROOT)),
        'template': str(template_path.relative_to(ROOT)),
        'adult_identity_minimum': ADULT_MIN_IDENTITY,
        'policy': 'Only a dated source excerpt stating an age can change age_state. '
                  'Publication, rating, apparent maturity and count tags are rejected.',
    }
    (output / '角色年龄证据_统计.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    return summary


def _clean(value, label, name, maximum, errors):
    if not isinstance(value, str):
        errors.append(f'{name}/{label} 必须是文本')
        return ''
    if len(value) > maximum or CONTROL.search(value):
        errors.append(f'{name}/{label} 过长或含控制字符')
        return ''
    return value.strip()


def validate_row(item, profile, errors):
    """Return the normalised evidence record or None when the row is unusable."""
    name = item.get('key')
    if not isinstance(item, dict):
        errors.append('模板行必须是对象')
        return None
    for field in GENERATED_FIELDS:
        if field not in item:
            errors.append(f'{name}/{field} 缺少生成字段；请重新导出模板')
            return None
    if item['key'] != item['name']:
        errors.append(f'{name} 的 key 与 name 不一致；不要改动生成字段')
        return None
    state = (item.get('age_state_proposed') or '').strip()
    if state not in STATES:
        errors.append(f'{name}/age_state_proposed 取值无效：{state!r}')
        return None
    if state == '':
        return {'key': name, 'unchanged': True}
    stated = _clean(item.get('stated_age'), 'stated_age', name, 40, errors)
    url = _clean(item.get('source_url'), 'source_url', name, 300, errors)
    excerpt = _clean(item.get('source_excerpt'), 'source_excerpt', name, 600, errors)
    recorded = _clean(item.get('source_recorded_at'), 'source_recorded_at', name, 40, errors)
    notes = _clean(item.get('notes'), 'notes', name, 500, errors)
    if state in {'verified_age_adult', 'verified_age_minor'}:
        if not stated:
            errors.append(f'{name} 必须填写 stated_age（来源中写明的年龄或年龄区间）')
        if not URL.match(url):
            errors.append(f'{name} 必须填写有效的 http(s) 来源链接')
        if len(excerpt) < MIN_EXCERPT:
            errors.append(f'{name} 的 source_excerpt 少于 {MIN_EXCERPT} 字符；不能仅凭结论')
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', recorded):
            errors.append(f'{name}/source_recorded_at 必须是 YYYY-MM-DD')
        else:
            try:
                if date.fromisoformat(recorded) > date.today():
                    errors.append(f'{name}/source_recorded_at 不能是未来日期')
            except ValueError:
                errors.append(f'{name}/source_recorded_at 不是有效日期')
        for pattern in NOT_AGE_EVIDENCE:
            if re.search(pattern, excerpt, re.I) or re.search(pattern, stated, re.I):
                errors.append(f'{name} 的来源文本命中「非年龄证据」规则：{pattern}；请给出明确写明年岁的原文')
                break
    identity = {}
    for slot in ('hair.color', 'hair.length', 'hair.style', 'eyes.color', 'skin.color'):
        value = _clean(item.get(f'identity_{slot}'), f'identity_{slot}', name, 120, errors)
        if value:
            identity[slot] = value
    return {'key': name, 'state': state, 'stated_age': stated, 'url': url, 'excerpt': excerpt,
            'recorded_at': recorded, 'notes': notes, 'identity': identity}


def apply(input_path: Path, catalog_path: Path, *, dry_run=False):
    data = json.loads(Path(catalog_path).read_bytes())
    characters = data['characters']
    records = []
    for number, line in enumerate(Path(input_path).read_text(encoding='utf-8-sig').splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f'第 {number} 行不是有效 JSON：{exc}')
        records.append((number, item))
    errors, accepted, unchanged = [], [], 0
    seen = set()
    for number, item in records:
        name = item.get('key') if isinstance(item, dict) else None
        if not name or name not in characters:
            errors.append(f'第 {number} 行：档案不存在 {name!r}')
            continue
        if name in seen:
            errors.append(f'第 {number} 行：重复 key {name}')
            continue
        seen.add(name)
        record = validate_row(item, characters[name], errors)
        if record is None:
            continue
        if record.get('unchanged'):
            unchanged += 1
            continue
        accepted.append(record)
    if errors:
        return {'applied': 0, 'errors': errors[:80], 'error_count': len(errors)}
    if dry_run:
        return {'applied': 0, 'dry_run': True, 'would_apply': len(accepted),
                'unchanged': unchanged, 'errors': [], 'error_count': 0}

    eligible_before = sum(1 for p in characters.values() if is_adult_eligible(p))
    appended = 0
    for record in accepted:
        profile = characters[record['key']]
        profile['age_state'] = {'verified_age_adult': 'adult', 'verified_age_minor': 'minor',
                                'verified_age_unknown': 'unknown'}[record['state']]
        evidence = [f'stated age: {record["stated_age"]}', f'source: {record["url"]}',
                    f'source excerpt: {record["excerpt"]}', f'recorded at: {record["recorded_at"]}']
        if record['notes']:
            evidence.append('notes: ' + record['notes'])
        profile['age_evidence'] = evidence
        sources = list(profile.get('sources') or ())
        if record['url'] not in sources:
            sources.append(record['url'])
            appended += 1
        profile['sources'] = sources
        if record['identity']:
            identity = dict(profile.get('identity') or {})
            identity.update(record['identity'])
            profile['identity'] = identity
    data['coverage']['character_profiles'] = len(characters)
    data['coverage']['adult_character_profiles'] = sum(1 for p in characters.values() if is_adult_eligible(p))
    Path(catalog_path).write_bytes(json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
    return {'applied': len(accepted), 'unchanged': unchanged, 'sources_appended': appended,
            'adult_eligible_before': eligible_before,
            'adult_eligible_after': data['coverage']['adult_character_profiles'],
            'catalog_sha256': sha(catalog_path), 'errors': [], 'error_count': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('export', 'apply', 'verify'))
    parser.add_argument('--catalog', type=Path, default=CATALOG)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--dry-run', action='store_true', help='只校验，不写入词库')
    args = parser.parse_args()
    if args.command == 'export':
        result = export(args.catalog, args.output)
    elif args.command == 'apply':
        if not args.input:
            parser.error('apply 需要 --input')
        result = apply(args.input, args.catalog, dry_run=args.dry_run)
    else:
        data = json.loads(args.catalog.read_bytes())
        characters = data['characters']
        result = {'profiles': len(characters),
                  'adult_eligible': sum(1 for p in characters.values() if is_adult_eligible(p)),
                  'withheld_by_reason': dict(Counter(withheld_reason(p) or 'adult_eligible'
                                                     for p in characters.values())),
                  'catalog_sha256': sha(args.catalog)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get('errors') else 0


if __name__ == '__main__':
    raise SystemExit(main())
