"""Atomic single-image TXT and JSON prompt exports."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any

from app import __version__
from app.errors import ExportError
from app.inference.model_loader import TagCategory
from app.inference.wd14_engine import InferenceResult
from app.prompts.models import NegativeTag, PromptBuildResult, RemovalRecord, TagResult

logger = logging.getLogger(__name__)


class ExportFormat(str, Enum):
    TXT = "txt"
    PROMPT_TXT = "prompt-txt"
    JSON = "json"


def _category_value(category: TagCategory) -> str:
    return "unknown" if category is TagCategory.OTHER else category.value


def _tag_to_dict(tag: TagResult) -> dict[str, Any]:
    return {
        "name": tag.name,
        "normalized_name": tag.normalized_name,
        "confidence": tag.confidence,
        "category": _category_value(tag.category),
        "prompt_group": tag.prompt_group.value if tag.prompt_group else None,
        "source": tag.source.value,
        "enabled": tag.enabled,
        "model_index": tag.model_index,
    }


def _negative_tag_to_dict(tag: NegativeTag) -> dict[str, Any]:
    return {
        "name": tag.name,
        "normalized_name": tag.name,
        "category": None,
        "prompt_group": None,
        "source": tag.sources[0].value if tag.sources else None,
        "sources": [source.value for source in tag.sources],
        "confidence": tag.confidence,
        "source_tag": tag.source_tag,
    }


def _removal_to_dict(record: RemovalRecord) -> dict[str, Any]:
    return {
        "reason": record.reason,
        "tag": _tag_to_dict(record.tag),
    }


class ExportService:
    SCHEMA_VERSION = 2

    def _atomic_write_text(
        self,
        output_path: Path,
        content: str,
        *,
        overwrite: bool,
    ) -> Path:
        target = Path(output_path)
        parent = target.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ExportError(f"无法创建导出目录：{parent}（{exc}）") from exc

        if target.exists() and not overwrite:
            raise ExportError(f"导出文件已存在；如需覆盖请使用 --overwrite：{target}")

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                dir=parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_path = Path(handle.name)

            if overwrite:
                os.replace(temporary_path, target)
                temporary_path = None
            else:
                # A hard-link commit is atomic and fails if another writer won
                # the same filename race. Both paths are on the same volume.
                try:
                    os.link(temporary_path, target)
                except FileExistsError as exc:
                    raise ExportError(
                        f"导出文件已存在；如需覆盖请使用 --overwrite：{target}"
                    ) from exc
                try:
                    temporary_path.unlink()
                    temporary_path = None
                except OSError as cleanup_error:
                    logger.warning(
                        "导出已完成，但暂时无法清理临时硬链接 %s：%s",
                        temporary_path,
                        cleanup_error,
                    )
            return target
        except ExportError:
            raise
        except OSError as exc:
            logger.debug("导出文件失败：%s", target, exc_info=True)
            logger.error("导出文件失败：%s（%s）", target, exc)
            raise ExportError(f"无法安全写入导出文件：{target}（{exc}）") from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("无法清理导出临时文件：%s", temporary_path)

    def build_json_document(
        self,
        prompts: PromptBuildResult,
        inference: InferenceResult,
        *,
        final_positive_prompt: str | None = None,
        final_negative_prompt: str | None = None,
        prompt_was_edited: bool | None = None,
        model_raw_tags: tuple[TagResult, ...] | None = None,
        working_tags: tuple[TagResult, ...] | list[TagResult] | None = None,
    ) -> dict[str, Any]:
        final_positive = (
            prompts.positive_prompt
            if final_positive_prompt is None
            else final_positive_prompt
        )
        final_negative = (
            prompts.negative_prompt
            if final_negative_prompt is None
            else final_negative_prompt
        )
        was_edited = (
            final_positive != prompts.positive_prompt
            or final_negative != prompts.negative_prompt
            if prompt_was_edited is None
            else prompt_was_edited
        )
        settings = prompts.settings_snapshot
        thresholds = {
            key: settings.get(key)
            for key in (
                "general_threshold",
                "character_threshold",
                "rating_threshold",
                "defect_threshold",
                "minimum_display_threshold",
            )
        }
        exported_raw_tags = (
            prompts.raw_tags if model_raw_tags is None else tuple(model_raw_tags)
        )
        exported_working_tags = (
            prompts.raw_tags if working_tags is None else tuple(working_tags)
        )
        return {
            "schema_version": self.SCHEMA_VERSION,
            "app_version": __version__,
            # Kept for compatibility with schema-2 consumers released during
            # the RC cycle. New integrations should use ``app_version``.
            "application_version": __version__,
            "source_image": str(inference.image_path),
            "model_name": inference.model_info.files.directory.name,
            "backend": inference.model_info.backend,
            "model_path": str(inference.model_info.files.model_path),
            "execution_provider": inference.model_info.active_provider,
            "inference_time_ms": round(inference.inference_seconds * 1000.0, 3),
            "generated_at": datetime.now(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z"),
            "thresholds": thresholds,
            "prompt_profile": prompts.profile_name,
            "raw_tags": [_tag_to_dict(tag) for tag in exported_raw_tags],
            "working_tags": [
                _tag_to_dict(tag) for tag in exported_working_tags
            ],
            "filtered_tags": [_tag_to_dict(tag) for tag in prompts.filtered_tags],
            "positive_tags": [_tag_to_dict(tag) for tag in prompts.positive_tags],
            "negative_tags": [
                _negative_tag_to_dict(tag) for tag in prompts.negative_tags
            ],
            "removed_tags": [
                _removal_to_dict(record) for record in prompts.removed_tags
            ],
            "excluded_tags": [
                _tag_to_dict(tag) for tag in prompts.excluded_tags
            ],
            "detected_defects": [
                _tag_to_dict(tag) for tag in prompts.detected_defects
            ],
            # Legacy field names remain available and now represent the text
            # actually exported by the user.
            "positive_prompt": final_positive,
            "negative_prompt": final_negative,
            "generated_positive_prompt": prompts.positive_prompt,
            "generated_negative_prompt": prompts.negative_prompt,
            "final_positive_prompt": final_positive,
            "final_negative_prompt": final_negative,
            "prompt_was_edited": was_edited,
            "settings_snapshot": settings,
        }

    def export(
        self,
        output_format: ExportFormat,
        output_path: Path,
        prompts: PromptBuildResult,
        inference: InferenceResult,
        *,
        overwrite: bool = False,
        final_positive_prompt: str | None = None,
        final_negative_prompt: str | None = None,
        prompt_was_edited: bool | None = None,
        model_raw_tags: tuple[TagResult, ...] | None = None,
        working_tags: tuple[TagResult, ...] | list[TagResult] | None = None,
    ) -> Path:
        final_positive = (
            prompts.positive_prompt
            if final_positive_prompt is None
            else final_positive_prompt
        )
        final_negative = (
            prompts.negative_prompt
            if final_negative_prompt is None
            else final_negative_prompt
        )
        if output_format is ExportFormat.TXT:
            content = f"{final_positive}\n"
        elif output_format is ExportFormat.PROMPT_TXT:
            content = (
                f"Positive:\n{final_positive}\n\n"
                f"Negative:\n{final_negative}\n"
            )
        elif output_format is ExportFormat.JSON:
            content = (
                json.dumps(
                    self.build_json_document(
                        prompts,
                        inference,
                        final_positive_prompt=final_positive,
                        final_negative_prompt=final_negative,
                        prompt_was_edited=prompt_was_edited,
                        model_raw_tags=model_raw_tags,
                        working_tags=working_tags,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
        else:
            raise ExportError(f"不支持的导出格式：{output_format}")
        return self._atomic_write_text(
            Path(output_path),
            content,
            overwrite=overwrite,
        )
