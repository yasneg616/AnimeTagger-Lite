"""Export source-backed review batches; drafts never enter the runtime pool."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def export(catalog_path: Path, wiki_path: Path, output: Path, batch_size: int = 100):
    if not 1 <= batch_size <= 1000:
        raise ValueError("batch_size must be 1–1000")
    raw_catalog = catalog_path.read_bytes()
    catalog = json.loads(raw_catalog)
    pages = json.loads(wiki_path.read_text(encoding="utf-8"))["pages"]
    pending = sorted(((identity, row) for identity, row in catalog["entries"].items()
                      if row["status"] != "reviewed"),
                     key=lambda item: (item[1]["category"] != "general", -item[1]["weight"], item[0]))
    output.mkdir(parents=True, exist_ok=True)
    index = []
    for start in range(0, len(pending), batch_size):
        filename = f"batch-{start // batch_size + 1:04d}.jsonl"
        with (output / filename).open("w", encoding="utf-8", newline="\n") as handle:
            for identity, row in pending[start:start + batch_size]:
                canonical = row["canonical"].replace(" ", "_")
                page = pages.get(canonical) or pages.get(row["name"].replace(" ", "_").casefold())
                body = page.get("body", "") if page else ""
                digest = hashlib.sha256(body.encode()).hexdigest() if page else None
                if digest != row["source_sha256"]:
                    raise ValueError("Wiki cache differs from compiled evidence: " + identity)
                template = ({"meaning_en": None, "meaning_zh": None, "slot": None, "scope": None,
                             "phrase": None, "requires": [], "excludes": [], "provides": [],
                             "themes": [], "adult": None, "min_actors": None}
                            if row["category"] == "general" else
                            {"copyrights": [], "gender": None, "identity": {}, "age_state": "unknown",
                             "age_evidence": None, "variants": [], "appearance_evidence": None})
                payload = {"key": identity, "name": row["name"], "category": row["category"],
                           "status": row["status"], "weight": row["weight"],
                           "sources": row["sources"], "source_url": row["source"],
                           "source_updated_at": row["source_updated_at"], "source_sha256": digest,
                           "wiki_body_candidate": body, "existing_meaning_zh": row["explanation_zh"],
                           "missing_reason": row["missing_reason"], "draft_only": True,
                           "review_template": template}
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
                index.append({"key": identity, "category": row["category"], "name": row["name"],
                              "status": row["status"], "weight": row["weight"], "batch": filename,
                              "source": row["source"], "missing_reason": row["missing_reason"]})
    with (output / "index.tsv").open("w", encoding="utf-8", newline="") as handle:
        fields = ("key", "category", "name", "status", "weight", "batch", "source", "missing_reason")
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(index)
    summary = {"catalog_sha256": hashlib.sha256(raw_catalog).hexdigest(),
               "pending": len(pending), "batches": (len(pending) + batch_size - 1) // batch_size,
               "batch_size": batch_size, "coverage": catalog["coverage"],
               "policy": "These are review candidates, not accepted rules. Export cannot change runtime coverage."}
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "README.txt").write_text(
        "语义词库待核对资料\n\n"
        "index.tsv 按一般词、角色和频率排序；batch-*.jsonl 每行是一项独立资料。\n"
        "Wiki 正文仅作候选证据。核对时记录准确含义、属性归属、依赖、互斥、搭配和英文句式；"
        "角色还须核对作品、稳定外观、版本差异及年龄证据。\n"
        "review_template 是空白草稿，不能直接导入发布词库。不得以大分类、已取得正文或模型猜测替代规则核对。\n"
        "将核对后的通用规则写入 app/prompts/semantic_rules.py，角色写入 character_overrides.json；"
        "重新编译后运行语义测试和分布检查。未确定年龄保持 unknown。\n"
        "summary.json 绑定本次词库哈希；资料更新后重新导出。此目录不会进入便携包。\n",
        encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "resources/prompt_semantics/catalog.json")
    parser.add_argument("--wiki", type=Path, default=ROOT / "data/prompt-semantics/wiki.json")
    parser.add_argument("--output", type=Path, help="A dedicated output directory; defaults to a catalog-version snapshot.")
    parser.add_argument("--batch-size", type=int, default=100)
    args = parser.parse_args()
    version = hashlib.sha256(args.catalog.read_bytes()).hexdigest()[:16]
    output = args.output or ROOT / "data/prompt-semantics/review" / version
    summary = export(args.catalog, args.wiki, output, args.batch_size)
    print(json.dumps({key: summary[key] for key in ("pending", "batches", "catalog_sha256")}, indent=2))


if __name__ == "__main__":
    main()
