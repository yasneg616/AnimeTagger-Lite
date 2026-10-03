"""Atomic batch manifests and recovery of interrupted work."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from app.batch.atomic import atomic_write_text
from app.batch.models import (
    BatchErrorType,
    BatchItemStatus,
    BatchJob,
    BatchJobStatus,
)
from app.errors import BatchManifestError, BatchConfigurationError
from app.config.settings import AppSettings
from app.runtime_paths import BATCH_JOBS_DIR, IS_PORTABLE


class ManifestStore:
    FILE_SUFFIX = ".manifest.json"

    def metadata_directory(self, job: BatchJob) -> Path:
        if job.config.metadata_dir is not None:
            return job.config.metadata_dir.resolve(strict=False)
        if IS_PORTABLE:
            return BATCH_JOBS_DIR.resolve(strict=False)
        if job.config.output_root is not None:
            return (job.config.output_root / ".animetagger").resolve(strict=False)
        first = job.scan_options.roots[0].resolve(strict=False)
        parent = first if first.is_dir() else first.parent
        return (parent / ".animetagger").resolve(strict=False)

    def assign_paths(self, job: BatchJob) -> None:
        directory = self.metadata_directory(job)
        stem = f"batch-{job.id}"
        job.manifest_path = directory / f"{stem}{self.FILE_SUFFIX}"
        job.summary_csv_path = directory / f"{stem}.csv"
        job.summary_json_path = directory / f"{stem}.summary.json"

    def save(self, job: BatchJob) -> Path:
        if job.manifest_path is None:
            self.assign_paths(job)
        assert job.manifest_path is not None
        try:
            payload = json.dumps(job.to_dict(), ensure_ascii=False, indent=2) + "\n"
        except (TypeError, ValueError) as exc:
            raise BatchManifestError(f"无法序列化批处理 Manifest：{exc}") from exc
        try:
            return atomic_write_text(job.manifest_path, payload)
        except Exception as exc:
            raise BatchManifestError(
                f"无法保存批处理 Manifest：{job.manifest_path}（{exc}）"
            ) from exc

    def load(self, path: Path, *, recover: bool = True) -> BatchJob:
        source = Path(path)
        try:
            with source.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise BatchManifestError(
                f"批处理 Manifest 无法读取或已损坏：{source}（{exc}）"
            ) from exc
        if not isinstance(payload, dict):
            raise BatchManifestError("批处理 Manifest 根节点必须是 JSON 对象。")
        try:
            job = BatchJob.from_dict(payload)
        except BatchConfigurationError as exc:
            raise BatchManifestError(f"批处理 Manifest 无效：{exc}") from exc
        job.manifest_path = source.resolve(strict=False)
        # A cancelled job is terminal for discovery/reporting, but an explicit
        # user request to load it with recovery must requeue the cancelled
        # items. Completed/failed terminal jobs remain historical records.
        if recover and (
            not job.status.terminal
            or job.status is BatchJobStatus.CANCELLED
        ):
            self.prepare_resume(job)
        return job

    def prepare_resume(self, job: BatchJob) -> None:
        for item in job.items:
            if not item.source_path.is_file():
                item.mark(
                    BatchItemStatus.MISSING,
                    error_type=BatchErrorType.MISSING_SOURCE,
                    error_message=f"恢复时源图片已不存在：{item.source_path}",
                )
                continue
            required_outputs = [
                path
                for path in (item.caption_path, item.json_path)
                if path is not None
            ]
            if (
                item.status is BatchItemStatus.COMPLETED
                and required_outputs
                and any(not path.is_file() for path in required_outputs)
            ):
                item.mark(BatchItemStatus.PENDING)
                item.completed_at = None
            if item.status in {
                BatchItemStatus.ANALYZING,
                BatchItemStatus.EXPORTING,
                BatchItemStatus.CANCELLED,
            }:
                item.mark(BatchItemStatus.PENDING)
        if any(
            item.status
            in {
                BatchItemStatus.PENDING,
                BatchItemStatus.FAILED,
                BatchItemStatus.MISSING,
            }
            for item in job.items
        ):
            job.status = BatchJobStatus.READY
        job.resumed_from_manifest = True
        job.finished_at = None

    def warn_if_settings_changed(
        self,
        job: BatchJob,
        current: AppSettings,
    ) -> tuple[str, ...]:
        warnings: list[str] = []
        if (
            current.model_dir != job.settings.model_dir
            or current.device != job.settings.device
        ):
            warnings.append(
                "当前模型目录或设备设置与 Manifest 快照不同；"
                "恢复前请确认要使用的模型。"
            )
        if (
            current.profile != job.settings.profile
            or current.general_threshold != job.settings.general_threshold
            or current.character_threshold
            != job.settings.character_threshold
        ):
            warnings.append(
                "当前 Profile 或阈值与 Manifest 快照不同；"
                "任务仍将使用保存时的不可变设置。"
            )
        for warning in warnings:
            if warning not in job.warnings:
                job.warnings.append(warning)
        return tuple(warnings)

    def discover_incomplete(self, directories: Iterable[Path]) -> tuple[Path, ...]:
        found: list[Path] = []
        seen: set[Path] = set()
        for raw_directory in directories:
            directory = Path(raw_directory)
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob(f"*{self.FILE_SUFFIX}")):
                resolved = path.resolve(strict=False)
                if resolved in seen:
                    continue
                try:
                    job = self.load(resolved, recover=False)
                except BatchManifestError:
                    continue
                if not job.status.terminal:
                    found.append(resolved)
                    seen.add(resolved)
        return tuple(found)
