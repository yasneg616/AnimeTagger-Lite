"""Export measured coverage, remaining gaps and source-backed sample scenes."""
from __future__ import annotations
import argparse
from collections import Counter
from dataclasses import asdict
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.prompts.semantic_prompt import SemanticPromptGenerator, SemanticPromptRequest


def report(output, baseline=None):
    raw = (ROOT / 'resources/prompt_semantics/catalog.json').read_bytes()
    data = json.loads(raw)
    coverage = data['coverage']
    output.mkdir(parents=True, exist_ok=True)
    gaps = [(identity, row) for identity, row in data['entries'].items() if row['status'] != 'reviewed']
    fields = ('key', 'name', 'category', 'status', 'missing_reason', 'source', 'source_updated_at', 'source_sha256')
    with (output / '未完成词条.tsv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter='\t')
        writer.writeheader()
        for identity, row in sorted(gaps):
            writer.writerow({field: identity if field == 'key' else row.get(field, '') for field in fields})
    reasons = Counter(row['missing_reason'] for _, row in gaps)
    summary = {'catalog_sha256': hashlib.sha256(raw).hexdigest(), 'coverage': coverage,
               'remaining': len(gaps), 'gap_reasons': dict(reasons.most_common()), 'human_reviewed': False}
    if baseline:
        previous = json.loads(baseline.read_bytes())
        before = {key for key, row in previous['entries'].items() if row['status'] == 'reviewed'}
        after = {key for key, row in data['entries'].items() if row['status'] == 'reviewed'}
        summary['change'] = {'previous_usable': len(before), 'newly_usable': len(after - before),
                             'withdrawn': len(before - after), 'net_added': len(after) - len(before)}
    generator = SemanticPromptGenerator(ROOT)
    pools = {}
    for backend in ('wd_v3', 'wd_2026_canary', 'pixai_v0_9', 'all'):
        vocabulary = generator.vocabulary(()) if backend == 'all' else generator.vocabulary((backend,))
        pools[backend] = {}
        for content in ('ordinary', 'adult'):
            pools[backend][content] = sum('character:' + generator.catalog.canonical(profile.name) in vocabulary
                and all((term := generator.catalog.term(tag)) and term.generatable and term.slot == slot
                        and 'general:' + generator.catalog.canonical(tag) in vocabulary
                        for slot, tag in (*profile.identity, *(profile.wardrobe if content == 'ordinary' else ())))
                and (content != 'adult' or profile.age_state == 'adult' and profile.kind == 'humanoid' and len(profile.identity) >= 2)
                for profile in generator.catalog.characters.values())
    summary['character_pools'] = pools
    (output / '词库覆盖.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    text = [f"可用词条 {coverage['usable_reviewed']} / {coverage['total']} ({coverage['usable_reviewed'] / coverage['total']:.2%})",
            f"最低要求 {coverage['minimum_required']}；尚未完成 {len(gaps)} 条。", '']
    for category, total in (('general', 12029), ('character', 5013)):
        count = coverage['by_category'][category]['reviewed']
        text.append(f"{'一般词' if category == 'general' else '角色条目'}：{count} / {total} ({count / total:.2%})")
    text.extend([f"高频一般词前 1000：{coverage['high_frequency_top_1000']['reviewed']} / 1000",
                 f"角色身份档案：{coverage['character_profiles']} 份。", '',
                 '每条规则使用明确属性、归属、依赖和受控英文表达；公开正文和只有旧释义的条目不直接计为可用。',
                 '角色属性没有充分依据时保持未知。默认服装无法一致表达时保留为待核对，不牵连已确认的身体外观。',
                 '编译和结构校验不代替人工语义审阅。代表画面仍需人工确认。', '', '缺口原因（前 20 项）：'])
    text.extend(f'{count} 条：{reason}' for reason, count in reasons.most_common(20))
    (output / '词库覆盖与缺口.txt').write_text('\n'.join(text), encoding='utf-8')
    # Ordinary scenes plus nonsexual figure studies exercise the content-level
    # constraints without adding speculative relationships or intimate actions.
    samples = []
    for index in range(27):
        count = 1 + index % 4
        content = 'ordinary' if index < 18 else 'adult'
        request = SemanticPromptRequest(seed=26000 + index, actor_count=count, content=content,
            freedom=('natural', 'balanced', 'bold')[index % 3], density=('concise', 'standard', 'rich')[(index // 3) % 3] if content == 'ordinary' else 'concise',
            character_mode='known' if index in (4, 8, 12, 16) else 'original',
            action='standing' if content == 'adult' else 'auto',
            actor_tags=tuple(('nude', 'smile') for _ in range(count)) if content == 'adult' else ())
        result = generator.generate(request)
        samples.append({'request': asdict(request), 'scene': asdict(result.scene), 'tags': result.tag_prompt,
                        'english': result.english_prompt, 'summary': result.summary, 'diagnostics': result.diagnostics})
    (output / '代表画面.json').write_text(json.dumps({'human_reviewed': False, 'catalog_sha256': summary['catalog_sha256'], 'samples': samples}, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / '代表画面.txt').write_text('\n\n'.join(f"画面 {index + 1}\n{row['summary']}\n\nTags: {row['tags']}\n\nEnglish: {row['english']}" for index, row in enumerate(samples)), encoding='utf-8')
    print(json.dumps({key: summary[key] for key in ('remaining', 'character_pools', 'change') if key in summary}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'validation/semantic-expansion')
    parser.add_argument('--baseline', type=Path)
    args = parser.parse_args()
    report(args.output, args.baseline)


if __name__ == '__main__':
    main()
