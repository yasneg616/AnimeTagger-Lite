"""Compare local backends on real images; never download data or models."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.settings import AppSettings
from app.inference.backends import BACKENDS
from app.inference.providers import Device
from app.inference.wd14_engine import WD14Engine
from app.prompts.pipeline import tag_results_from_predictions
from app.services.tagging_service import TaggingService

MODES = ("raw", "anime", "pony", "lora_caption", "cyberillustrious_semireal")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=tuple(BACKENDS), action="append")
    parser.add_argument("--device", choices=("cpu", "cuda", "auto"), default="cpu")
    args = parser.parse_args()
    images = sorted(p for p in args.images.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})
    if not images:
        parser.error("No real images found")
    report = {"device": args.device, "image_count": len(images), "backends": {}}
    for backend in args.backend or BACKENDS:
        settings = AppSettings.from_mapping({"backend": backend, "device": args.device})
        service = TaggingService()
        record = {"settings": settings.snapshot(), "images": []}
        report["backends"][backend] = record
        try:
            info = service.load_model(settings.model_dir, Device(args.device), backend=backend)
            record.update(provider=info.active_provider, warning=info.provider_warning, output_count=info.output_count)
            legacy = WD14Engine(Path(settings.model_dir), device=Device(args.device)) if backend == "wd_v3" else None
            try:
                for path in images:
                    analysis = service.analyze_image(path, settings)
                    grouped = analysis.inference.grouped
                    counts = {}
                    for group in ("general", "character", "rating", "copyright"):
                        threshold = settings.character_threshold if group in {"character", "copyright"} else getattr(settings, f"{group}_threshold")
                        counts[group] = sum(p.confidence >= threshold for p in grouped[group])
                    prompts = {mode: service.rebuild_prompts(analysis.raw_tags, replace(settings, profile=mode)) for mode in MODES}
                    item = {"image": path.name, "counts_above_threshold": counts,
                            "seconds": analysis.inference.inference_seconds,
                            "characters": [{"name": p.tag.name, "score": p.confidence} for p in grouped["character"] if p.confidence >= settings.character_threshold],
                            "general_top20": [p.tag.name for p in grouped["general"][:20]],
                            "prompt_tag_counts": {mode: len(result.filtered_tags) for mode, result in prompts.items()}}
                    if legacy:
                        old_tags = tag_results_from_predictions(legacy.predict(path).predictions)
                        item["legacy_prompt_equal"] = all(
                            service.rebuild_prompts(old_tags, replace(settings, profile=mode)).positive_prompt == prompts[mode].positive_prompt
                            for mode in MODES)
                        if not item["legacy_prompt_equal"]:
                            raise AssertionError(f"Legacy prompt changed: {path.name}")
                    record["images"].append(item)
                    print(f"{backend}: {path.name}: {counts}", flush=True)
            finally:
                if legacy:
                    legacy.release()
        except Exception as exc:
            record["error"] = str(exc)
            print(f"{backend}: ERROR: {exc}", flush=True)
        finally:
            service.unload_model()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return int(any("error" in record for record in report["backends"].values()))


if __name__ == "__main__":
    raise SystemExit(main())
