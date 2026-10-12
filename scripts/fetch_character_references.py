"""Cache text tag records for the default appearance references in local Wiki.

GET requests only; no image files, credentials or runtime network dependency.
Acquired records remain candidate evidence until the compiler checks ownership,
official-art provenance, variants and the referenced attribute rules.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.fetch_prompt_semantics import Client, write_json, inventory
from scripts.prompt_semantic_families import plain


def appearance_references(body):
    rows, root_depth, contexts = [], None, {}
    roots = {'appearance', 'default appearance', 'original appearance', 'character design', 'official art'}
    containers = {'default', 'original', 'default appearance', 'original appearance', 'regular costumes', 'regular outfits', 'regular outfit', 'default costume', 'default outfit', 'official art'}
    for line in body.replace('\r', '\n').splitlines():
        heading = re.match(r'h([1-6])(?:#[\w-]+)?\.\s*(.+)', line.strip(), re.I)
        if heading:
            depth, title = int(heading[1]), plain(heading[2]).strip().casefold()
            if root_depth is not None and depth <= root_depth:
                if rows:
                    break
                root_depth, contexts = None, {}
            if root_depth is None:
                if title in roots:
                    root_depth = depth
                continue
            contexts = {d: value for d, value in contexts.items() if d < depth}
            contexts[depth] = title
            continue
        if root_depth is None or not all(title in containers for title in contexts.values()):
            continue
        match = re.search(r'!(post|asset)\s+#(\d+)(?:\s*:\s*(.*))?', line)
        if not match:
            continue
        label = match[3] or ''
        caption = plain(label)
        explicit = bool(re.search(r'\b(?:original|default|profile|reference|character design)\b', caption, re.I))
        if re.search(r'\b(?:not|non-default|alternate|skin|swimsuit|anniversary|collab|remodel|ascension|form)\b', caption, re.I):
            continue
        if re.search(r'\b(?:costume|outfit)\b', caption, re.I) and not explicit:
            continue
        # A nested list is not itself a default reference. Its selected row
        # needs a literal default label, unless the heading says Default.
        if contexts and not explicit and not any(title in {'default', 'original', 'default appearance', 'original appearance'} for title in contexts.values()):
            continue
        if rows and not explicit:
            continue
        row = {'id': int(match[2]), 'kind': match[1], 'caption': label, 'wiki_line': line.strip(),
               'explicit_default': explicit or any(title in {'default', 'original', 'default appearance', 'original appearance'} for title in contexts.values())}
        if not any((item['kind'], item['id']) == (row['kind'], row['id']) for item in rows):
            rows.append(row)
    return rows[:3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, default=ROOT / 'data/prompt-semantics')
    parser.add_argument('--batches', type=int, default=0)
    parser.add_argument('--batch-size', type=int, default=80)
    parser.add_argument('--select-only', action='store_true', help='Refresh reference selection from local Wiki without any GET requests')
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 100:
        parser.error('batch size must be 1..100')
    pages = json.loads((args.cache / 'wiki.json').read_text(encoding='utf-8'))['pages']
    refs = {}
    for row in inventory()['entries'].values():
        if row['category'] != 'character':
            continue
        title = row['name'].replace(' ', '_').lower()
        page = pages.get(title)
        if page and (references := appearance_references(page['body'])):
            refs[title] = {'wiki_updated_at': page.get('updated_at'), 'references': references}
    path = args.cache / 'character_references.json'
    state = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {'posts': {}, 'checked': [], 'failures': []}
    state['references'] = refs
    state.setdefault('assets', {})
    state.setdefault('assets_checked', [])
    write_json(path, state)
    if args.select_only:
        print(f'Selected {len(refs)} character reference lists from cached Wiki; network requests=0', flush=True)
        return
    asset_checked = set(state['assets_checked'])
    asset_pending = sorted({str(ref['id']) for page in refs.values() for ref in page['references'] if ref.get('kind') == 'asset'} - asset_checked, key=int)
    client = Client(args.cache)
    fields = 'id,rating,tag_string_general,tag_string_character,tag_string_copyright,tag_string_meta,source,is_deleted,is_pending,is_flagged,updated_at'
    for start in range(0, len(asset_pending), args.batch_size):
        batch = asset_pending[start:start + args.batch_size]
        rows = client.get('media_assets', {'search[id]': ','.join(batch), 'limit': 100, 'only': 'id,md5,post[' + fields + ']'})
        if any(str(row['id']) not in batch for row in rows):
            raise ValueError('Media asset API did not honor requested IDs')
        for row in rows:
            state['assets'][str(row['id'])] = row
            if row.get('post'):
                state['posts'][str(row['post']['id'])] = row['post']
        asset_checked.update(batch)
        state['assets_checked'] = sorted(asset_checked, key=int)
        write_json(path, state)
        print(f'assets={len(asset_checked)} records={len(state["assets"])} linked_posts={sum(bool(row.get("post")) for row in state["assets"].values())}', flush=True)
        if args.batches:
            break
    checked = set(state['checked'])
    pending = sorted({str(ref['id']) for page in refs.values() for ref in page['references'] if ref.get('kind') != 'asset'} - checked, key=int)
    batches = 0
    for start in range(0, len(pending), args.batch_size):
        batch = pending[start:start + args.batch_size]
        rows = client.get('posts', {'tags': 'id:' + ','.join(batch), 'limit': 100, 'only': fields})
        if any(str(row['id']) not in batch for row in rows):
            raise ValueError('Post API did not honor the requested IDs')
        for row in rows:
            state['posts'][str(row['id'])] = row
        checked.update(batch)
        state['checked'] = sorted(checked, key=int)
        state['updated_at'] = datetime.now(timezone.utc).isoformat()
        write_json(path, state)
        print(f"references={len(refs)} checked={len(checked)} records={len(state['posts'])} pending={len(pending)-min(start+len(batch),len(pending))}", flush=True)
        batches += 1
        if args.batches and batches >= args.batches:
            break
    print(f"Done: {len(state['posts'])} post tag records; remaining {len(pending) - min(batches*args.batch_size, len(pending))}", flush=True)


if __name__ == '__main__':
    main()
