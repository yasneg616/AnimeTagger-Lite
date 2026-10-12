"""Explicit, resumable GET-only Danbooru vocabulary acquisition (never runtime)."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("wd-vit-tagger-v3", "wd-eva02-tagger-2026-canary", "pixai-tagger-v0.9")


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporary.replace(path)


def inventory(root=ROOT):
    entries = {}
    ips = {}
    sources = []
    for backend in SOURCES:
        path = root / "models" / backend / "selected_tags.csv"
        sources.append({"name": backend, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                name = row["name"].strip()
                category = {"0": "general", "4": "character", "3": "copyright"}.get(row["category"])
                if not name or category is None:
                    continue
                key = category + ":" + " ".join(name.replace("_", " ").split()).casefold()
                entry = entries.setdefault(key, {"name": name, "category": category, "weight": 1, "sources": []})
                entry["weight"] = max(entry["weight"], int(float(row.get("count") or 1)))
                if backend not in entry["sources"]:
                    entry["sources"].append(backend)
                if row.get("ips"):
                    values = json.loads(row["ips"])
                    if values:
                        ips[name] = values
    return {"entries": entries, "ips": ips, "sources": sources}


class Client:
    def __init__(self, cache, interval=1.0, base="https://danbooru.donmai.us"):
        self.cache = Path(cache)
        self.interval = max(1.0, interval)
        self.base = base
        self.last_request = 0.0

    def get(self, resource, params):
        url = self.base + "/" + resource + ".json?" + urllib.parse.urlencode(params)
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache / "requests" / (key + ".json")
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))["data"]
        for attempt in range(5):
            time.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "AnimeTaggerLite-Semantics/1.0", "Accept": "application/json"})
                with urllib.request.urlopen(request, timeout=45) as response:
                    data = json.load(response)
                if not isinstance(data, list):
                    raise ValueError("Expected an API record list")
                write_json(path, {"url": url, "fetched_at": datetime.now(timezone.utc).isoformat(), "data": data})
                return data
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                if isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 403, 404):
                    raise
                if attempt == 4:
                    raise
                delay = min(30, 2 ** (attempt + 1))
                if isinstance(exc, urllib.error.HTTPError):
                    try:
                        delay = max(delay, min(60, float(exc.headers.get("Retry-After", delay))))
                    except ValueError:
                        pass
                print(f"retry {resource}: {type(exc).__name__}; wait {delay}s", flush=True)
                time.sleep(delay)

    def relationships(self, resource):
        checkpoint = self.cache / (resource + ".json")
        state = json.loads(checkpoint.read_text(encoding="utf-8")) if checkpoint.exists() else {"rows": [], "cursor": None, "complete": False}
        while not state["complete"]:
            params = {"search[status]": "active", "limit": 1000, "only": "id,antecedent_name,consequent_name,status,updated_at"}
            if state["cursor"] is not None:
                params["page"] = "b" + str(state["cursor"])
            rows = self.get(resource, params)
            if not rows:
                state["complete"] = True
            else:
                cursor = min(row["id"] for row in rows)
                if state["cursor"] is not None and cursor >= state["cursor"]:
                    raise ValueError("API pagination made no progress")
                state["rows"].extend(rows)
                state["cursor"] = cursor
            write_json(checkpoint, state)
            print(f"{resource}: {len(state['rows'])} records; complete={state['complete']}", flush=True)
        return state["rows"]

    def wiki_batch(self, names):
        names = sorted({name.strip().strip("_") for name in names})
        rows = self.get("wiki_pages", {"search[title_comma]": ",".join(names), "search[is_deleted]": "false", "limit": 1000,
                                      "only": "id,title,body,other_names,updated_at,is_deleted"})
        if any(row["title"] not in names for row in rows):
            raise ValueError("API did not honor title_comma; refusing unrelated pages")
        return rows

    def groups(self):
        path = self.cache / "groups.json"
        state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"pages": {}, "checked": []}
        while True:
            pending = {"tag_groups"}
            for page in state["pages"].values():
                for match in re.findall(r"\[\[([^\]]+)\]\]", page["body"]):
                    title = match.split("|", 1)[0].strip().replace(" ", "_").casefold().strip("_")
                    if title.startswith(("tag_group:", "list_of_")):
                        pending.add(title)
            missing = sorted(pending - set(state["checked"]))
            if not missing:
                break
            batch = missing[:60]
            for row in self.wiki_batch(batch):
                state["pages"][row["title"]] = row
            state["checked"] = sorted(set(state["checked"]) | set(batch))
            write_json(path, state)
            print(f"groups: {len(state['pages'])} pages, {len(state['checked'])} checked", flush=True)
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "data" / "prompt-semantics")
    parser.add_argument("--base", choices=("https://danbooru.donmai.us", "https://safebooru.donmai.us"), default="https://danbooru.donmai.us")
    parser.add_argument("--batch-size", type=int, default=60)
    parser.add_argument("--wiki-batches", type=int, default=0, help="0 fetches the full local vocabulary; positive values allow a resumable pilot")
    parser.add_argument("--groups-only", action="store_true", help="Fetch source taxonomies with the same cache and review boundary")
    args = parser.parse_args()
    if not 1 <= args.batch_size <= 100:
        parser.error("batch-size must be 1..100")
    data = inventory()
    write_json(args.cache / "inventory.json", data)
    client = Client(args.cache, base=args.base)
    if args.groups_only:
        client.groups()
        return 0
    aliases = client.relationships("tag_aliases")
    client.relationships("tag_implications")
    alias_map = {row["antecedent_name"]: row["consequent_name"] for row in aliases}
    names = {row["name"].replace(" ", "_").casefold() for row in data["entries"].values()}
    names.update(ip for values in data["ips"].values() for ip in values)
    names.update(alias_map.get(name, name) for name in tuple(names))
    ordered = sorted(names)
    wiki_path = args.cache / "wiki.json"
    state = json.loads(wiki_path.read_text(encoding="utf-8")) if wiki_path.exists() else {"pages": {}, "checked": []}
    checked = set(state["checked"])
    remaining = [name for name in ordered if name not in checked]
    batches = 0
    for start in range(0, len(remaining), args.batch_size):
        batch = remaining[start:start + args.batch_size]
        rows = client.wiki_batch(batch)
        for row in rows:
            state["pages"][row["title"]] = row
        checked.update(batch)
        state["checked"] = sorted(checked)
        write_json(wiki_path, state)
        batches += 1
        print(f"wiki: checked={len(checked)}/{len(ordered)} found={len(state['pages'])}", flush=True)
        if args.wiki_batches and batches >= args.wiki_batches:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
