"""Offline stratified seed distribution and independent scene acceptance audit."""
from __future__ import annotations

import argparse
from contextlib import redirect_stdout
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.errors import ConfigurationError
from app.prompts.semantic_prompt import SemanticPromptGenerator, SemanticPromptRequest
from app.prompts.semantic_scene import all_facts, validate_scene


def run(root, output, seeds):
    generator = SemanticPromptGenerator(root)
    outcomes, terms, repeats = Counter(), Counter(), Counter()
    failed, violations, samples, versions = [], [], [], {}
    start = time.monotonic()
    for seed in range(seeds):
        # Coprime strata avoid accidentally correlating all adult requests with
        # even actor counts, as a seed%2/seed%4 grid would do.
        count = 1 + seed % 4
        freedom = ("natural", "balanced", "bold")[(seed // 4) % 3]
        content = ("ordinary", "adult")[(seed // 12) % 2]
        density = ("concise", "standard", "rich")[(seed // 24) % 3]
        backend = ("wd_v3", "wd_2026_canary", "pixai_v0_9")[(seed // 72) % 3]
        character_mode = "known" if seed % 17 == 0 else "original"
        request = SemanticPromptRequest(seed=seed, backends=(backend,), actor_count=count, freedom=freedom,
                                        content=content, density=density, character_mode=character_mode)
        label = f"{count}/{freedom}/{content}/{density}/{backend}/{character_mode}"
        try:
            result = generator.generate(request)
        except ConfigurationError as exc:
            failed.append({"seed": seed, "stratum": label, "error": str(exc)})
            print(f"failure seed={seed}: {ascii(str(exc))}", flush=True)
            outcomes[label + "/failed"] += 1
            continue
        errors = list(validate_scene(result.scene, generator.catalog))
        if len(result.scene.actors) != count:
            errors.append("Subject count mismatch")
        if any(value.term_key not in generator.catalog.terms or not generator.catalog.terms[value.term_key].generatable for value in all_facts(result.scene)):
            errors.append("Unreviewed fact generated")
        if content == "ordinary" and any(generator.catalog.terms[value.term_key].adult for value in all_facts(result.scene)):
            errors.append("Adult fact in ordinary scene")
        if not result.tag_prompt or not result.english_prompt:
            errors.append("Missing view")
        if result.expansions > 2000:
            errors.append("Search bound exceeded")
        if errors:
            violations.append({"seed": seed, "errors": errors})
            print(f"violation seed={seed}: {ascii(errors)}", flush=True)
        # Ignore seed/version when measuring duplicate scenes.
        versions[backend] = result.corpus_version
        digest = hashlib.sha256(json.dumps(asdict(result.scene), sort_keys=True).encode()).hexdigest()
        repeats[digest] += 1
        terms.update(value.term_key for value in all_facts(result.scene))
        outcomes[label + "/success"] += 1
        if seed < 24 or seed in (217, 997, 2026, 4095, 9999):
            samples.append({"seed": seed, "request": asdict(request), "scene": asdict(result.scene), "tags": result.tag_prompt,
                            "english": result.english_prompt, "expansions": result.expansions})
        if seed % 200 == 0:
            print(f"seeds={seed}/{seeds} failures={len(failed)} violations={len(violations)}", flush=True)
    report = {"seeds": seeds, "seconds": round(time.monotonic() - start, 3), "successes": seeds - len(failed),
              "failure_rate": len(failed) / seeds, "failures": failed, "rule_violations": violations,
              "unique_scenes": len(repeats), "duplicate_results": sum(value - 1 for value in repeats.values()),
              "max_duplicate_count": max(repeats.values(), default=0), "unique_fact_tags": len(terms),
              "term_frequency": dict(terms.most_common()), "strata": dict(sorted(outcomes.items())), "coverage": generator.catalog.coverage,
              "samples": samples, "catalog_sha256_prefix": generator.catalog.version, "corpus_versions": versions,
              "audit_limit": "Zero detected rule violations does not prove the absence of unmodeled semantic problems."}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("seeds", "seconds", "successes", "failure_rate", "unique_scenes", "duplicate_results", "unique_fact_tags")}, indent=2))
    return 0 if not violations and not failed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "validation/semantic-distribution.json")
    parser.add_argument("--seeds", type=int, default=10000)
    parser.add_argument('--progress-log', type=Path)
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("seeds must be positive")
    if args.progress_log:
        args.progress_log.parent.mkdir(parents=True, exist_ok=True)
        with args.progress_log.open('w', encoding='utf-8', buffering=1) as handle, redirect_stdout(handle):
            return run(args.root, args.output, args.seeds)
    return run(args.root, args.output, args.seeds)


if __name__ == "__main__":
    raise SystemExit(main())
