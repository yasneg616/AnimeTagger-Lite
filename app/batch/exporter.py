"""Caption policies plus atomic batch report output."""

from __future__ import annotations

import csv
from io import StringIO
import json
from pathlib import Path
import re

from app.batch.atomic import atomic_write_bytes, atomic_write_text
from app.batch.models import (
    BatchConfig,
    BatchItem,
    BatchJob,
    BatchTextFormat,
    CaptionPolicy,
)
from app.config.settings import AppSettings
from app.errors import ExportError
from app.export_service import ExportService
from app.inference.model_loader import TagCategory
from app.services.tagging_service import AnalysisResult

_COMMA_SPLIT = re.compile(r"\s*,\s*")


def caption_terms(text: str) -> tuple[str, ...]:
    return tuple(term.strip() for term in _COMMA_SPLIT.split(text) if term.strip())


def merge_caption_terms(*values: str | None) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        for term in caption_terms(value):
            key = re.sub(r"[\s_]+", " ", term).strip().casefold()
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(term)
    return ", ".join(merged)


def read_caption(path: Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8-sig").strip()
    except (OSError, UnicodeError) as exc:
        raise ExportError(f"无法读取已有 caption：{path}（{exc}）") from exc


def next_backup_path(path: Path) -> Path:
    target = Path(path)
    first = target.with_name(f"{target.name}.bak")
    if not first.exists():
        return first
    index = 1
    while True:
        candidate = target.with_name(f"{target.name}.bak.{index}")
        if not candidate.exists():
            return candidate
        index += 1


class BatchOutputWriter:
    def __init__(self, export_service: ExportService | None = None) -> None:
        self._export_service = export_service or ExportService()

    def can_complete_without_inference(
        self,
        item: BatchItem,
        config: BatchConfig,
        settings: AppSettings,
    ) -> bool:
        del settings
        existing_caption = (
            item.caption_path is not None and item.caption_path.exists()
        )
        existing_json = item.json_path is not None and item.json_path.exists()
        if config.caption_policy is CaptionPolicy.SKIP and (
            existing_caption or existing_json
        ):
            return True
        return (
            config.caption_policy is CaptionPolicy.APPEND_TRIGGER
            and existing_caption
            and not config.write_json
        )

    def write_existing_only(
        self,
        item: BatchItem,
        config: BatchConfig,
        settings: AppSettings,
    ) -> bool:
        """Apply a policy that needs no model; return False for a skip."""

        if config.caption_policy is CaptionPolicy.SKIP:
            item.output_action = "skipped_existing"
            return False
        caption_path = item.caption_path
        if caption_path is None or not caption_path.exists():
            raise ExportError("已有 caption 策略缺少目标 caption。")
        if config.caption_policy is not CaptionPolicy.APPEND_TRIGGER:
            raise ExportError("当前 caption 策略仍需要推理结果。")
        current = read_caption(caption_path)
        updated = merge_caption_terms(settings.trigger_word, current)
        if updated and updated != current:
            atomic_write_text(caption_path, f"{updated}\n")
        item.positive_prompt = updated or current
        item.output_action = "append_trigger"
        return True

    def write_analysis(
        self,
        item: BatchItem,
        job: BatchJob,
        analysis: AnalysisResult,
    ) -> None:
        config = job.config
        prompts = analysis.prompts
        final_positive = prompts.positive_prompt
        if item.caption_path is not None:
            final_positive = self._write_caption(
                item,
                config,
                job.settings,
                prompts.positive_prompt,
                prompts.negative_prompt,
            )
        if item.json_path is not None:
            document = self._export_service.build_json_document(
                prompts,
                analysis.inference,
                final_positive_prompt=final_positive,
                final_negative_prompt=prompts.negative_prompt,
                model_raw_tags=analysis.raw_tags,
                working_tags=analysis.raw_tags,
            )
            document["batch"] = {
                "job_id": job.id,
                "item_id": item.id,
                "caption_policy": config.caption_policy.value,
                "source_root": str(item.source_root),
                "relative_path": item.relative_path.as_posix(),
            }
            atomic_write_text(
                item.json_path,
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            )
        item.positive_prompt = final_positive
        item.negative_prompt = prompts.negative_prompt
        item.provider = analysis.inference.model_info.active_provider
        item.model_name = analysis.inference.model_info.files.directory.name
        item.inference_time_ms = round(
            analysis.inference.inference_seconds * 1000.0,
            3,
        )
        item.tag_count = len(prompts.positive_tags)
        item.character_tags = ", ".join(
            tag.output_name
            for tag in prompts.positive_tags
            if tag.category is TagCategory.CHARACTER
        )
        item.rating_tags = ", ".join(
            tag.output_name
            for tag in prompts.positive_tags
            if tag.category is TagCategory.RATING
        )

    def _write_caption(
        self,
        item: BatchItem,
        config: BatchConfig,
        settings: AppSettings,
        generated: str,
        negative: str,
    ) -> str:
        assert item.caption_path is not None
        target = item.caption_path
        exists = target.exists()
        policy = config.caption_policy
        if exists and policy is CaptionPolicy.SKIP:
            raise ExportError(f"caption 已存在且策略为 skip：{target}")

        final = generated
        if exists and policy is CaptionPolicy.APPEND_TRIGGER:
            final = merge_caption_terms(settings.trigger_word, read_caption(target))
        elif exists and policy is CaptionPolicy.MERGE:
            final = merge_caption_terms(
                settings.trigger_word,
                read_caption(target),
                generated,
            )
        if not final.strip():
            raise ExportError(
                f"生成的 Caption 为空，已拒绝创建空文件：{target}"
            )
        if exists and policy is CaptionPolicy.BACKUP_AND_OVERWRITE:
            backup = next_backup_path(target)
            try:
                original = target.read_bytes()
            except OSError as exc:
                raise ExportError(f"无法读取待备份 caption：{target}（{exc}）") from exc
            atomic_write_bytes(backup, original)
            item.backup_path = backup

        if config.text_format is BatchTextFormat.PROMPT_TXT:
            content = (
                f"Positive:\n{final}\n\n"
                f"Negative:\n{negative}\n"
            )
        else:
            content = f"{final}\n"
        atomic_write_text(target, content)
        item.output_action = (
            policy.value if exists else "created"
        )
        return final

    def write_csv(self, job: BatchJob, path: Path) -> Path:
        if Path(path).exists() and not job.config.overwrite_reports:
            raise ExportError(
                f"CSV 已存在；需要明确允许覆盖报告：{path}"
            )
        buffer = StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(
            (
                "source_path",
                "relative_path",
                "status",
                "error_type",
                "error_message",
                "model_name",
                "execution_provider",
                "inference_time_ms",
                "profile",
                "positive_prompt",
                "negative_prompt",
                "tag_count",
                "character_tags",
                "rating_tags",
                "output_txt",
                "output_json",
                "completed_at",
                "item_id",
                "attempt_count",
                "retry_count",
                "elapsed_ms",
                "output_action",
            )
        )
        for item in job.items:
            if (
                job.config.csv_success_only
                and item.status.value not in {"completed", "skipped"}
            ):
                continue
            writer.writerow(
                (
                    str(item.source_path),
                    item.relative_path.as_posix(),
                    item.status.value,
                    item.error_type.value,
                    item.error_message,
                    item.model_name,
                    item.provider,
                    "" if item.inference_time_ms is None else item.inference_time_ms,
                    job.settings.profile,
                    item.positive_prompt,
                    item.negative_prompt,
                    item.tag_count,
                    item.character_tags,
                    item.rating_tags,
                    str(item.caption_path or ""),
                    str(item.json_path or ""),
                    item.completed_at or "",
                    item.id,
                    item.attempt_count,
                    item.retry_count,
                    "" if item.elapsed_ms is None else item.elapsed_ms,
                    item.output_action,
                )
            )
        encoding = "utf-8-sig" if job.config.csv_bom else "utf-8"
        return atomic_write_bytes(path, buffer.getvalue().encode(encoding))

    def write_summary_json(self, job: BatchJob, path: Path) -> Path:
        if Path(path).exists() and not job.config.overwrite_reports:
            raise ExportError(
                f"汇总 JSON 已存在；需要明确允许覆盖报告：{path}"
            )
        document = {
            "schema_version": 1,
            "job_id": job.id,
            "status": job.status.value,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "counts": job.counts(),
            "warnings": list(job.warnings),
            "config": job.to_dict()["config"],
            "settings": job.settings.snapshot(),
            "items": [
                {
                    "item_id": item.id,
                    "source_path": str(item.source_path),
                    "relative_path": item.relative_path.as_posix(),
                    "status": item.status.value,
                    "caption_path": str(item.caption_path or ""),
                    "json_path": str(item.json_path or ""),
                    "error_type": item.error_type.value,
                    "error_message": item.error_message,
                    "retry_count": item.retry_count,
                    "provider": item.provider,
                    "inference_time_ms": item.inference_time_ms,
                    "elapsed_ms": item.elapsed_ms,
                }
                for item in job.items
            ],
        }
        return atomic_write_text(
            path,
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        )
