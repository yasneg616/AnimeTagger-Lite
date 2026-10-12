"""Read-only gap triage for the semantic prompt catalog.

Joins the unfinished-entry report against the cached Wiki evidence, re-runs the
existing definition classifier, and groups the still-unmodelled names by their
defining head noun so a compiler change can be aimed at real clusters. This
script never writes the catalog and never marks anything reviewed.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.prompts.normalizer import canonical_tag_key as key  # noqa: E402
from scripts.prompt_semantic_families import (  # noqa: E402
    ADULT, FAMILIES, HEAD_PATTERNS, UNRESOLVED, _defining_phrase, definition,
    infer_definition, plain,
)

STOP = frozenset(
    "a an the of with and or for to in on at by is are as from that which who "
    "whose its it their this these those".split()
)


def wiki_body(wiki: dict, name: str):
    """Return the cached Wiki record for a tag name, following alias keys."""
    for candidate in (name, key(name)):
        record = wiki.get(candidate)
        if isinstance(record, dict) and record.get("body"):
            return record
    return None


def head_noun(name: str, text: str) -> str:
    """Best-effort last content word of the defining noun phrase."""
    phrase = _defining_phrase(text)
    tokens = [t for t in re.split(r"[^a-z0-9-]+", phrase.lower()) if t and t not in STOP]
    if tokens:
        return tokens[-1]
    tokens = [t for t in re.split(r"[^a-z0-9-]+", name.lower()) if t and t not in STOP]
    return tokens[-1] if tokens else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--unfinished",
        default=str(ROOT / "validation" / "semantic-expansion" / "未完成词条.tsv"),
    )
    parser.add_argument(
        "--wiki", default=str(ROOT / "data" / "prompt-semantics" / "wiki.json")
    )
    parser.add_argument("--output", default="")
    parser.add_argument("--reason", default="definition_family_not_implemented")
    parser.add_argument("--top", type=int, default=80)
    parser.add_argument("--samples", type=int, default=6)
    args = parser.parse_args()

    with open(args.wiki, encoding="utf-8") as handle:
        wiki = json.load(handle)
    if isinstance(wiki, dict) and "pages" in wiki:
        wiki = wiki["pages"]

    rows = []
    with open(args.unfinished, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row.get("category") != "general":
                continue
            if args.reason not in (row.get("missing_reason") or ""):
                continue
            rows.append(row)

    buckets: dict[str, list] = collections.defaultdict(list)
    no_wiki = []
    still_blocked = collections.Counter()
    adult_blocked = 0

    for row in rows:
        name = row["name"]
        page = wiki_body(wiki, name)
        if not page:
            no_wiki.append(name)
            continue
        rule, evidence, reason = infer_definition(name, page)
        if rule is not None:
            still_blocked["_NOW_MODELLED"] += 1
            buckets["*MODELLED*"].append((name, "compiles now"))
            continue
        if reason != args.reason:
            still_blocked[reason] += 1
            continue
        text = plain(definition(page.get("body", "")))
        if ADULT.search(text[:350]) or ADULT.search(key(name)):
            adult_blocked += 1
        buckets[head_noun(name, text)].append((name, text[:130]))

    print(f"requested reason : {args.reason}")
    print(f"general entries  : {len(rows)}")
    print(f"no cached wiki   : {len(no_wiki)}")
    print(f"now modelled     : {still_blocked.get('_NOW_MODELLED', 0)}")
    print(f"adult-adjacent   : {adult_blocked}")
    print(f"distinct heads   : {len(buckets)}")
    other = {k: v for k, v in still_blocked.items() if k != "_NOW_MODELLED"}
    if other:
        ranked = sorted(other.items(), key=lambda kv: -kv[1])
        print("reclassified to  : " + ", ".join(f"{k}={v}" for k, v in ranked))
    print()

    print("=== largest head clusters ===")
    for head, items in sorted(buckets.items(), key=lambda kv: -len(kv[1]))[: args.top]:
        print(f"{len(items):5}  {head}")
    print()

    print("=== samples per large cluster ===")
    for head, items in sorted(buckets.items(), key=lambda kv: -len(kv[1]))[:24]:
        if len(items) < 4 or head == "*MODELLED*":
            continue
        print(f"--- {head} ({len(items)}) ---")
        for name, snippet in items[: args.samples]:
            print(f"    {name}  ::  {snippet}")

    if args.output:
        payload = {
            "reason": args.reason,
            "counts": {
                "entries": len(rows),
                "no_cached_wiki": len(no_wiki),
                "now_modelled": still_blocked.get("_NOW_MODELLED", 0),
                "adult_adjacent": adult_blocked,
                "heads": len(buckets),
                "reclassified": dict(other),
            },
            "clusters": {
                head: [n for n, _ in items] for head, items in sorted(
                    buckets.items(), key=lambda kv: -len(kv[1])
                )
            },
            "no_cached_wiki": no_wiki,
        }
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
