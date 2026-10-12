"""Inspect uncovered positive definitions while developing semantic adapters."""
import json
import re
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prompt_semantic_families import plain, definition


def main():
    data = json.loads((ROOT / 'resources/prompt_semantics/catalog.json').read_text(encoding='utf-8'))
    pages = json.loads((ROOT / 'data/prompt-semantics/wiki.json').read_text(encoding='utf-8'))['pages']
    rows = [r for r in data['entries'].values() if r['category'] == 'general' and r['status'] != 'reviewed']
    rows.sort(key=lambda r: (-r['weight'], r['name']))
    if len(sys.argv) > 2:
        pattern = re.compile(sys.argv[2])
        rows = [r for r in rows if pattern.search(r['canonical'])]
    if len(sys.argv) > 3:
        rows = sorted(rows, key=lambda r: r['canonical'])[int(sys.argv[3]):]
    print('Reasons:', Counter(r['missing_reason'].split('(')[-1].strip(')') for r in rows))
    print('Suffixes:', Counter(r['canonical'].split()[-1] for r in rows).most_common(75))
    for row in rows[:int(sys.argv[1]) if len(sys.argv) > 1 else 180]:
        page = pages.get(row['canonical'].replace(' ', '_')) or pages.get(row['name'].replace(' ', '_'))
        text = plain(definition(page['body'])) if page else ''
        print(row['canonical'], ':', re.sub(r'\s+', ' ', text)[:350])


if __name__ == '__main__':
    main()
