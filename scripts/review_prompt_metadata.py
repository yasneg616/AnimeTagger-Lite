"""Export and apply neutral identification reviews without generation rules."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.prompts.normalizer import canonical_tag_key as key
from app.prompts.review_metadata import EDITABLE, GROUPS, validate_metadata
from scripts.fetch_prompt_semantics import write_json
from scripts.prompt_semantic_families import definition, plain

PATTERNS = (
    ('nonconsensual_context', re.compile(r'\b(?:rape|raped|raping|molestation|sexual assault|non[- ]?consensual|forced sex|forced sexual)\b', re.I)),
    ('other_sensitive_context', re.compile(r'\b(?:incest|bestiality|zoophilia|necrophilia)\b', re.I)),
    ('explicit_activity', re.compile(r'\b(?:sex(?:ual)? (?:act|activity|activities|position|intercourse|penetration)|intercourse|masturbat\w*|orgasm\w*|fellatio|cunnilingus|blowjob|handjob|footjob|paizuri|tribadism|frottage|irrumatio|deepthroat|bukkake|defloration|anilingus|anal sex|oral sex|vaginal sex|penis[- ]in[- ]|gangbang|threesome|foursome|pussyjob|buttjob|glansjob|boobjob|titjob|titsjob|pegging|humping)\b', re.I)),
    ('explicit_fluid_context', re.compile(r'\b(?:cum(?:shot|shots|drip|dripping|ming|mings|swap|swapping|dump|dumping|pool|pools|play|flation|flated)?|precum|semen|ejaculat\w*)\b', re.I)),
    ('sexual_theme', re.compile(r'\b(?:bdsm|sexual\w*|sex fetish|sexual slavery|sexual torture|sex slave|sex toys?|dildos?|vibrators?|strap-on|ahegao|femdom|maledom|erotic|fetish(?:ism)?|perverted)\b', re.I)),
    ('anatomical_context', re.compile(r'\b(?:penis|penises|pussy|vulva|vagina|vaginal|anus|testicles?|genitals?|genitalia|clitoris|clitoral|scrotum|labia|cervix|mons pubis|urethra|urethral|nipples?|areolae?|smegma|phimosis)\b', re.I)),
    ('restraint_context', re.compile(r'\b(?:bondage|shibari|hogtie|frogtie|armbinder|gagged|ring gag|box tie|chastity cage)\b', re.I)),
)
NAME_ONLY_ACTIVITY = re.compile(r'\b(?:sex|anal|penetration|fingering|clitoral stimulation|double penetration|imminent penetration)\b', re.I)
AGE = re.compile(r'\b(?:loli|shota|underage|prepubescent|pedophil\w*)\b', re.I)


def classify(name, body):
    """Candidate triage only: tag names and the page's own introductory prose."""
    normalized = key(name)
    intro = plain(definition(body))
    # Exclude comparisons, related lists, examples and unrelated later prose.
    intro = re.split(r'\b(?:not to be confused|do not confuse|unlike|see also|for example|examples include)\b', intro, maxsplit=1, flags=re.I)[0]
    intro = re.split(r'\n|\.(?:\s|$)', intro, maxsplit=1)[0][:600]
    matches = []
    for group, pattern in PATTERNS:
        basis = [field for field, value in (('tag_name', normalized), ('own_intro', intro)) if pattern.search(value)]
        if basis:
            matches.append((group, basis))
    if NAME_ONLY_ACTIVITY.search(normalized):
        matches.append(('explicit_activity', ['tag_name']))
    if AGE.search(normalized) or matches and AGE.search(intro):
        return 'age_sensitive_context', ['tag_name'] if AGE.search(normalized) else ['own_intro']
    order = {group: index for index, (group, _) in enumerate(PATTERNS)}
    return min(matches, key=lambda item: order[item[0]]) if matches else (None, [])


def strict_json(text):
    def pairs(values):
        result = {}
        for name, value in values:
            if name in result:
                raise ValueError('重复的 JSON 字段：' + name)
            result[name] = value
        return result
    return json.loads(text, object_pairs_hook=pairs)


def candidate(row, identity, group, basis):
    return dict(key=identity, name=row['name'], canonical=row['canonical'], review_group=group,
                review_state='needs_review', label_zh=GROUPS[group], meaning_zh='', notes='',
                suggested_aliases=[], source_url=row['source'], source_updated_at=row['source_updated_at'],
                source_sha256=row['source_sha256'], evidence_basis=basis)


def export(catalog_path, wiki_path, output):
    raw = catalog_path.read_bytes()
    catalog = json.loads(raw)
    pages = json.loads(wiki_path.read_bytes())['pages']
    selected, entire = {}, []
    aliases = {}
    for alias, target in catalog['aliases'].items():
        aliases.setdefault(target, []).append(alias.replace(' ', '_'))
    for identity, row in sorted(catalog['entries'].items()):
        if row['category'] != 'general':
            continue
        page = pages.get(row['canonical'].replace(' ', '_')) or pages.get(row['name'].replace(' ', '_').casefold())
        body = page.get('body', '') if page else ''
        group, basis = classify(row['canonical'], body)
        if not group:
            continue
        digest = hashlib.sha256(body.encode()).hexdigest() if page else None
        if digest != row['source_sha256']:
            raise ValueError('缓存来源与词库不一致：' + identity)
        record = candidate(row, identity, group, basis)
        display = dict(key=identity, name=row['name'], canonical=row['canonical'],
                       group_zh=GROUPS[group], catalog_status=row['status'],
                       selected_from_remaining=row['status'] != 'reviewed',
                       active_aliases=' | '.join(sorted(aliases.get(row['canonical'], []))),
                       implied_names=' | '.join(catalog['implications'].get(row['canonical'], [])),
                       source_url=row['source'], source_updated_at=row['source_updated_at'],
                       source_sha256=digest, evidence_basis=' | '.join(basis), missing_reason=row['missing_reason'])
        entire.append(display)
        if row['status'] != 'reviewed':
            selected[identity] = record
    validate_metadata(selected, catalog['entries'])
    output.mkdir(parents=True, exist_ok=True)
    for name, rows in (('相关词条_全词库扫描.tsv', entire),
                       ('相关词条_剩余项.tsv', [row for row in entire if row['selected_from_remaining']])):
        with (output / name).open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=('key', 'name', 'canonical', 'group_zh', 'catalog_status',
                'selected_from_remaining', 'active_aliases', 'implied_names', 'source_url', 'source_updated_at',
                'source_sha256', 'evidence_basis', 'missing_reason'), delimiter='\t')
            writer.writeheader()
            writer.writerows(rows)
    with (output / '识别资料_填写模板.jsonl').open('w', encoding='utf-8', newline='\n') as handle:
        for record in selected.values():
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
    write_json(output / '识别资料_初始登记.json', {'schema_version': 1, 'entries': selected})
    summary = dict(catalog_sha256=hashlib.sha256(raw).hexdigest(), vocabulary_total=len(catalog['entries']),
                   entire_vocabulary_candidates=len(entire), remaining_candidates=len(selected),
                   remaining_by_group=dict(Counter(GROUPS[item['review_group']] for item in selected.values())),
                   automatic_triage=True, classification_requires_review=True, generation_rules_added=0,
                   usable_generation_coverage=catalog['coverage']['usable_reviewed'],
                   policy='Neutral metadata only. No action, scene dependency, age override or generation template is accepted.')
    write_json(output / '扫描统计.json', summary)
    return summary


def apply(input_path, catalog_path, destination, wiki_path=None):
    catalog = json.loads(catalog_path.read_bytes())
    if input_path.suffix.casefold() == '.jsonl':
        records = {}
        for number, line in enumerate(input_path.read_text(encoding='utf-8-sig').splitlines(), 1):
            if not line.strip():
                continue
            item = strict_json(line)
            identity = item.get('key') if isinstance(item, dict) else None
            if not identity or identity in records:
                raise ValueError(f'填写模板第 {number} 行无 key 或 key 重复')
            records[identity] = item
    else:
        bundle = strict_json(input_path.read_text(encoding='utf-8-sig'))
        if not isinstance(bundle, dict) or set(bundle) != {'schema_version', 'entries'} or bundle['schema_version'] != 1:
            raise ValueError('识别资料文件版本或字段不正确')
        records = bundle['entries']
    initial = export_records(catalog_path, wiki_path)
    for identity, record in records.items():
        original = initial.get(identity)
        if original is None:
            raise ValueError('词条不在当前自动登记范围内：' + identity)
        for field in set(original) - EDITABLE:
            if record.get(field) != original[field]:
                raise ValueError(f'只可编辑识别资料字段：{identity}/{field}')
    if destination.exists():
        previous = strict_json(destination.read_text(encoding='utf-8'))
        if set(previous) != {'schema_version', 'entries'} or previous['schema_version'] != 1:
            raise ValueError('既有识别资料文件格式不正确')
        merged = dict(previous['entries'])
    else:
        merged = {}
    merged.update(records)
    validate_metadata(merged, catalog['entries'])
    write_json(destination, {'schema_version': 1, 'entries': merged})
    return dict(registered=len(merged), verified_identification=sum(item['review_state'] == 'verified_identification'
                  for item in merged.values()), generation_rules_added=0, destination=str(destination))


def export_records(catalog_path, wiki_path=None):
    catalog = json.loads(catalog_path.read_bytes())
    pages = json.loads((wiki_path or ROOT / 'data/prompt-semantics/wiki.json').read_bytes())['pages']
    result = {}
    for identity, row in catalog['entries'].items():
        if row['category'] != 'general' or row['status'] == 'reviewed':
            continue
        page = pages.get(row['canonical'].replace(' ', '_')) or pages.get(row['name'].replace(' ', '_').casefold())
        body = page.get('body', '') if page else ''
        if (hashlib.sha256(body.encode()).hexdigest() if page else None) != row['source_sha256']:
            raise ValueError('缓存来源与词库不一致：' + identity)
        group, basis = classify(row['canonical'], body)
        if group:
            result[identity] = candidate(row, identity, group, basis)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('export', 'apply', 'verify'))
    parser.add_argument('--catalog', type=Path, default=ROOT / 'resources/prompt_semantics/catalog.json')
    parser.add_argument('--wiki', type=Path, default=ROOT / 'data/prompt-semantics/wiki.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'validation/semantic-completion-final/相关词条整理')
    parser.add_argument('--input', type=Path)
    parser.add_argument('--destination', type=Path, default=ROOT / 'resources/prompt_semantics/review_annotations.json')
    args = parser.parse_args()
    if args.command == 'export':
        result = export(args.catalog, args.wiki, args.output)
    elif args.command == 'apply':
        if not args.input:
            parser.error('apply requires --input')
        result = apply(args.input, args.catalog, args.destination, args.wiki)
    else:
        data = strict_json(args.destination.read_text(encoding='utf-8-sig'))
        if set(data) != {'schema_version', 'entries'} or data['schema_version'] != 1:
            raise ValueError('识别资料文件版本或字段不正确')
        entries = json.loads(args.catalog.read_bytes())['entries']
        validate_metadata(data['entries'], entries)
        result = dict(registered=len(data['entries']), generation_rules_added=0)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
