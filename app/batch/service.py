"""Shared batch orchestration for CLI and GUI."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace
import logging
from pathlib import Path
import threading
import time
from typing import Callable

from app.batch.exporter import BatchOutputWriter
from app.batch.manifest import ManifestStore
from app.batch.models import (
    BatchConfig,
    BatchErrorType,
    BatchItem,
    BatchItemStatus,
    BatchJob,
    BatchJobStatus,
    ScanOptions,
    ScanResult,
    utc_now,
)
from app.batch.paths import OutputPlanner
from app.batch.scanner import BatchScanner
from app.config.settings import AppSettings
from app.errors import (
    BatchConfigurationError,
    ExportError,
    ImageLoadError,
    InferenceError,
    ModelLoadError,
)
from app.services.tagging_service import AnalysisResult, TaggingService

logger = logging.getLogger(__name__)
MAX_RETRY_CACHE_ITEMS = 8

ItemCallback = Callable[[BatchItem, int, int], None]
JobCallback = Callable[[BatchJob], None]


class BatchRunControl:
    """Thread-safe pause/resume/cancel state checked between images."""

    def __init__(self) -> None:
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()
        self._condition = threading.Condition()

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    @property
    def paused(self) -> bool:
        return self.pause_event.is_set()

    def cancel(self) -> None:
        self.cancel_event.set()
        with self._condition:
            self._condition.notify_all()

    def pause(self) -> None:
        self.pause_event.set()

    def resume(self) -> None:
        self.pause_event.clear()
        with self._condition:
            self._condition.notify_all()

    def reset(self) -> None:
        self.cancel_event.clear()
        self.pause_event.clear()

    def wait_if_paused(
        self,
        *,
        paused_callback: Callable[[], None] | None = None,
    ) -> None:
        notified = False
        with self._condition:
            while self.pause_event.is_set() and not self.cancel_event.is_set():
                if not notified and paused_callback is not None:
                    paused_callback()
                    notified = True
                self._condition.wait(timeout=0.25)


class BatchService:
    """Own scanner, path planning, persistence, and serial inference policy."""

    def __init__(
        self,
        tagging_service: TaggingService,
        *,
        scanner: BatchScanner | None = None,
        planner: OutputPlanner | None = None,
        writer: BatchOutputWriter | None = None,
        manifests: ManifestStore | None = None,
    ) -> None:
        self.tagging_service = tagging_service
        self.scanner = scanner or BatchScanner()
        self.planner = planner or OutputPlanner()
        self.writer = writer or BatchOutputWriter()
        self.manifests = manifests or ManifestStore()
        self._analysis_cache: OrderedDict[str, AnalysisResult] = OrderedDict()
        self._active_lock = threading.Lock()
        self._active_job_id: str | None = None

    @property
    def active_job_id(self) -> str | None:
        with self._active_lock:
            return self._active_job_id

    def scan(
        self,
        options: ScanOptions,
        *,
        cancel_event: object | None = None,
        progress: Callable[[int, Path], None] | None = None,
    ) -> ScanResult:
        return self.scanner.scan(
            options,
            cancel_event=cancel_event,  # type: ignore[arg-type]
            progress=progress,
        )

    def create_job(
        self,
        scan_options: ScanOptions,
        config: BatchConfig,
        settings: AppSettings,
        *,
        scan_result: ScanResult | None = None,
    ) -> BatchJob:
        if settings.trigger_word and "," in settings.trigger_word:
            raise BatchConfigurationError(
                "Trigger word 不能包含逗号；请将它作为一个完整触发词。"
            )
        effective_scan = scan_options
        if (
            config.output_root is not None
            and scan_options.output_root != config.output_root
        ):
            effective_scan = replace(
                scan_options,
                output_root=config.output_root,
            )
        result = scan_result or self.scan(effective_scan)
        normalized_scan = replace(effective_scan, roots=result.roots)
        items = list(result.items)
        self.planner.plan(items, config)
        for item in items:
            item.mark(BatchItemStatus.PENDING)
        job = BatchJob(
            scan_options=normalized_scan,
            config=config,
            settings=AppSettings.from_mapping(settings.snapshot()),
            items=items,
            status=(
                BatchJobStatus.CANCELLED
                if result.cancelled
                else BatchJobStatus.READY
            ),
            warnings=list(result.warnings),
        )
        if result.truncated:
            job.warnings.append(
                f"扫描达到文件数上限 {effective_scan.max_files}，结果已截断。"
            )
        if result.duplicate_count:
            job.warnings.append(f"忽略重复图片 {result.duplicate_count} 张。")
        if result.permission_error_count:
            job.warnings.append(
                f"有 {result.permission_error_count} 个目录因权限不足被跳过。"
            )
        self.manifests.assign_paths(job)
        return job

    def preview(self, job: BatchJob) -> dict[str, int]:
        existing = 0
        skipped = 0
        backups = 0
        captions = 0
        json_files = 0
        for item in job.items:
            if item.caption_path is not None:
                captions += 1
                if item.caption_path.exists():
                    existing += 1
                    if job.config.caption_policy.value == "skip":
                        skipped += 1
                    if job.config.caption_policy.value == "backup_and_overwrite":
                        backups += 1
            if item.json_path is not None:
                json_files += 1
        return {
            "images": len(job.items),
            "captions": captions,
            "json_files": json_files,
            "existing_captions": existing,
            "would_skip": skipped,
            "would_backup": backups,
        }

    def run_job(
        self,
        job: BatchJob,
        *,
        control: BatchRunControl | None = None,
        on_item: ItemCallback | None = None,
        on_job: JobCallback | None = None,
    ) -> BatchJob:
        run_control = control or BatchRunControl()
        if job.config.dry_run:
            job.status = BatchJobStatus.COMPLETED
            job.started_at = job.started_at or utc_now()
            job.finished_at = utc_now()
            if on_job is not None:
                on_job(job)
            return job
        if not self.tagging_service.is_model_loaded:
            raise ModelLoadError("批处理开始前必须先加载有效的本地模型。")
        self._claim_job(job)
        processed_since_save = 0
        job.started_at = job.started_at or utc_now()
        job.finished_at = None
        job.status = BatchJobStatus.RUNNING
        try:
            self.manifests.save(job)
            self._emit_job(job, on_job)
            runnable = [
                item
                for item in job.items
                if item.status is BatchItemStatus.PENDING and item.selected
            ]
            for item in job.items:
                if item.status is BatchItemStatus.PENDING and not item.selected:
                    item.output_action = "deselected"
                    item.mark(BatchItemStatus.SKIPPED)
                    item.completed_at = utc_now()
                    self._emit_item(item, 0, len(runnable), on_item)
            total = len(runnable)
            for position, item in enumerate(runnable, start=1):
                if run_control.cancelled:
                    break
                run_control.wait_if_paused(
                    paused_callback=lambda: self._mark_paused(job, on_job)
                )
                if run_control.cancelled:
                    break
                if job.status is BatchJobStatus.PAUSED:
                    job.status = BatchJobStatus.RUNNING
                    self.manifests.save(job)
                    self._emit_job(job, on_job)

                self._run_item(job, item, position, total, on_item)
                processed_since_save += 1
                if processed_since_save >= job.config.manifest_every:
                    self.manifests.save(job)
                    processed_since_save = 0

            if run_control.cancelled:
                job.status = BatchJobStatus.CANCELLING
                self._emit_job(job, on_job)
                for item in job.items:
                    if item.status is BatchItemStatus.PENDING:
                        item.mark(
                            BatchItemStatus.CANCELLED,
                            error_type=BatchErrorType.CANCELLED,
                            error_message="用户在上一张图片完成后取消了批处理。",
                        )
                        item.completed_at = utc_now()
                        if on_item is not None:
                            on_item(item, 0, len(job.items))
                job.status = BatchJobStatus.CANCELLED
            else:
                has_errors = any(
                    item.status
                    in {BatchItemStatus.FAILED, BatchItemStatus.MISSING}
                    for item in job.items
                )
                job.status = (
                    BatchJobStatus.COMPLETED_WITH_ERRORS
                    if has_errors
                    else BatchJobStatus.COMPLETED
                )
            job.finished_at = utc_now()
            report_ok = self._write_reports(job)
            if not report_ok and job.status is BatchJobStatus.COMPLETED:
                job.status = BatchJobStatus.COMPLETED_WITH_ERRORS
            self.manifests.save(job)
            self._emit_job(job, on_job)
            return job
        except Exception:
            if not job.status.terminal:
                job.status = BatchJobStatus.FAILED
                job.finished_at = utc_now()
                try:
                    self.manifests.save(job)
                except Exception:
                    logger.exception("批处理失败后无法更新 Manifest")
            self._emit_job(job, on_job)
            raise
        finally:
            self._release_job(job)

    def retry_failed(self, job: BatchJob) -> int:
        if self.active_job_id is not None:
            raise BatchConfigurationError("批处理运行期间不能重置失败条目。")
        count = 0
        for item in job.items:
            if item.status in {
                BatchItemStatus.FAILED,
                BatchItemStatus.MISSING,
                BatchItemStatus.CANCELLED,
            }:
                if item.retry_count >= job.config.max_retries:
                    continue
                item.retry_count += 1
                item.mark(BatchItemStatus.PENDING)
                item.completed_at = None
                count += 1
        if count:
            job.config = replace(job.config, overwrite_reports=True)
            job.status = BatchJobStatus.READY
            job.finished_at = None
            if not job.config.dry_run:
                self.manifests.save(job)
        return count

    def _run_item(
        self,
        job: BatchJob,
        item: BatchItem,
        position: int,
        total: int,
        on_item: ItemCallback | None,
    ) -> None:
        started = time.perf_counter()
        item.started_at = utc_now()
        if not item.source_path.is_file():
            item.mark(
                BatchItemStatus.MISSING,
                error_type=BatchErrorType.MISSING_SOURCE,
                error_message=f"源图片不存在或已不是普通文件：{item.source_path}",
            )
            self._finish_item(item, started, position, total, on_item)
            return
        try:
            if self.writer.can_complete_without_inference(
                item,
                job.config,
                job.settings,
            ):
                completed = self.writer.write_existing_only(
                    item,
                    job.config,
                    job.settings,
                )
                item.mark(
                    BatchItemStatus.COMPLETED
                    if completed
                    else BatchItemStatus.SKIPPED
                )
                self._finish_item(item, started, position, total, on_item)
                return

            analysis = self._analysis_cache.get(item.id)
            if analysis is None:
                item.mark(BatchItemStatus.ANALYZING)
                item.attempt_count += 1
                self._emit_item(item, position, total, on_item)
                analysis = self.tagging_service.analyze_image(
                    item.source_path,
                    job.settings,
                )
                self._analysis_cache[item.id] = analysis
                self._analysis_cache.move_to_end(item.id)
                while len(self._analysis_cache) > MAX_RETRY_CACHE_ITEMS:
                    self._analysis_cache.popitem(last=False)
            item.mark(BatchItemStatus.EXPORTING)
            self._emit_item(item, position, total, on_item)
            self.writer.write_analysis(item, job, analysis)
            # Successful items no longer need the retry-only analysis cache.
            # Keep failed exports cached so retry_failed() can avoid inference.
            self._analysis_cache.pop(item.id, None)
            item.mark(BatchItemStatus.COMPLETED)
        except Exception as exc:
            logger.exception("批处理条目失败：%s", item.source_path)
            item.mark(
                BatchItemStatus.FAILED,
                error_type=self._classify_error(exc),
                error_message=str(exc),
            )
        self._finish_item(item, started, position, total, on_item)

    @staticmethod
    def _classify_error(exc: Exception) -> BatchErrorType:
        if isinstance(exc, ImageLoadError):
            text = str(exc)
            if "过大" in text or "像素过多" in text or "超过上限" in text:
                return BatchErrorType.IMAGE_TOO_LARGE
            if "不支持图片格式" in text:
                return BatchErrorType.UNSUPPORTED_FORMAT
            if "解码" in text or "损坏" in text:
                return BatchErrorType.DECODE_ERROR
            return BatchErrorType.IMAGE_LOAD
        if isinstance(exc, ModelLoadError):
            return BatchErrorType.MODEL
        if isinstance(exc, InferenceError):
            return BatchErrorType.INFERENCE
        if isinstance(exc, PermissionError):
            return BatchErrorType.OUTPUT_PERMISSION
        if isinstance(exc, ExportError):
            text = str(exc).casefold()
            if "已存在" in text:
                return BatchErrorType.OUTPUT_EXISTS
            if "permission" in text or "权限" in text:
                return BatchErrorType.OUTPUT_PERMISSION
            if ".json" in text:
                return BatchErrorType.JSON_WRITE
            return BatchErrorType.CAPTION_WRITE
        if isinstance(exc, (OSError, UnicodeError)):
            return BatchErrorType.CAPTION_WRITE
        return BatchErrorType.UNKNOWN

    @staticmethod
    def _emit_item(
        item: BatchItem,
        position: int,
        total: int,
        callback: ItemCallback | None,
    ) -> None:
        if callback is not None:
            callback(item, position, total)

    @classmethod
    def _finish_item(
        cls,
        item: BatchItem,
        started: float,
        position: int,
        total: int,
        callback: ItemCallback | None,
    ) -> None:
        item.elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        if item.status in {
            BatchItemStatus.COMPLETED,
            BatchItemStatus.SKIPPED,
            BatchItemStatus.FAILED,
            BatchItemStatus.MISSING,
            BatchItemStatus.CANCELLED,
        }:
            item.completed_at = utc_now()
        cls._emit_item(item, position, total, callback)

    def _mark_paused(
        self,
        job: BatchJob,
        callback: JobCallback | None,
    ) -> None:
        if job.status is BatchJobStatus.PAUSED:
            return
        job.status = BatchJobStatus.PAUSED
        self.manifests.save(job)
        self._emit_job(job, callback)

    @staticmethod
    def _emit_job(job: BatchJob, callback: JobCallback | None) -> None:
        if callback is not None:
            callback(job)

    def _write_reports(self, job: BatchJob) -> bool:
        success = True
        if job.config.write_csv:
            assert job.summary_csv_path is not None
            try:
                self.writer.write_csv(job, job.summary_csv_path)
            except Exception as exc:
                logger.exception("批处理 CSV 汇总导出失败")
                job.warnings.append(f"CSV 汇总导出失败：{exc}")
                success = False
        if job.config.write_summary_json:
            assert job.summary_json_path is not None
            try:
                self.writer.write_summary_json(job, job.summary_json_path)
            except Exception as exc:
                logger.exception("批处理汇总 JSON 导出失败")
                job.warnings.append(f"汇总 JSON 导出失败：{exc}")
                success = False
        return success

    def _claim_job(self, job: BatchJob) -> None:
        with self._active_lock:
            if self._active_job_id is not None:
                raise BatchConfigurationError(
                    f"已有批处理正在运行：{self._active_job_id}"
                )
            self._active_job_id = job.id

    def _release_job(self, job: BatchJob) -> None:
        with self._active_lock:
            if self._active_job_id == job.id:
                self._active_job_id = None
