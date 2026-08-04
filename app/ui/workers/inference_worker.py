"""One persistent worker thread for model lifecycle and sequential inference."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import threading

from PySide6.QtCore import QObject, QThread, Qt, Signal, Slot

from app.batch.models import BatchConfig, BatchJob, ScanOptions
from app.batch.service import BatchRunControl, BatchService
from app.config.settings import AppSettings
from app.inference.providers import Device
from app.services.tagging_service import AnalysisResult, TaggingService

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class QueueEntry:
    image_id: str
    image_path: Path
    settings: AppSettings


@dataclass(frozen=True, slots=True)
class BatchScanRequest:
    options: ScanOptions
    config: BatchConfig
    settings: AppSettings


class InferenceWorker(QObject):
    model_loading = Signal()
    model_loaded = Signal(object)
    model_load_failed = Signal(str, bool)
    model_unloaded = Signal()
    model_unload_failed = Signal(str)
    image_started = Signal(str)
    image_completed = Signal(str, object)
    image_failed = Signal(str, str)
    image_cancelled = Signal(str)
    progress_changed = Signal(int, int)
    queue_completed = Signal(int, int, int, int)
    batch_scan_progress = Signal(int, str)
    batch_scan_completed = Signal(object)
    batch_item_changed = Signal(object, int, int)
    batch_job_changed = Signal(object)
    batch_completed = Signal(object)
    batch_retry_ready = Signal(object, int)
    batch_failed = Signal(str)
    fatal_error = Signal(str)
    shutdown_ready = Signal()

    def __init__(self, service: TaggingService) -> None:
        super().__init__()
        self._service = service
        self._cancel_event = threading.Event()
        self._batch_control = BatchRunControl()
        self._batch_service = BatchService(service)
        self._busy = False

    def request_cancel(self) -> None:
        """Thread-safe immediate cancellation request.

        This method deliberately only sets ``threading.Event`` and may be
        called directly while the worker's Qt event loop is inside ONNX.
        """

        self._cancel_event.set()
        self._batch_control.cancel()

    def request_pause_batch(self) -> None:
        self._batch_control.pause()

    def request_resume_batch(self) -> None:
        self._batch_control.resume()

    def prepare_queue(self) -> None:
        """Reset cancellation before the controller publishes a new queue.

        Calling this from the GUI thread is safe because ``threading.Event``
        supports concurrent ``set``/``clear``.  Resetting before the queued
        signal is emitted prevents an immediate cancel or close request from
        being erased when the worker eventually begins processing.
        """

        self._cancel_event.clear()

    def prepare_batch(self) -> None:
        self._batch_control.reset()

    @Slot(object, object)
    def load_model(self, model_dir: object, device: object) -> None:
        self.model_loading.emit()
        try:
            info = self._service.load_model(
                Path(str(model_dir)),
                device if isinstance(device, Device) else Device(str(device)),
            )
        except Exception as exc:
            logger.exception("GUI 模型加载失败")
            self.model_load_failed.emit(
                str(exc),
                self._service.is_model_loaded,
            )
            return
        self.model_loaded.emit(info)

    @Slot()
    def unload_model(self) -> None:
        try:
            self._service.unload_model()
        except Exception as exc:
            logger.exception("GUI 模型释放失败")
            self.model_unload_failed.emit(str(exc))
            return
        self.model_unloaded.emit()

    @Slot(object)
    def process_queue(self, entries_object: object) -> None:
        if self._busy:
            self.fatal_error.emit("已有识别队列正在运行。")
            return
        entries = tuple(entries_object)  # type: ignore[arg-type]
        self._busy = True
        completed = 0
        failed = 0
        cancelled = 0
        total = len(entries)
        try:
            for position, entry in enumerate(entries):
                if self._cancel_event.is_set():
                    for remaining in entries[position:]:
                        self.image_cancelled.emit(remaining.image_id)
                        cancelled += 1
                    break
                self.image_started.emit(entry.image_id)
                try:
                    result = self._service.analyze_image(
                        entry.image_path,
                        entry.settings,
                    )
                except Exception as exc:
                    logger.exception(
                        "图片识别失败：image_id=%s path=%s",
                        entry.image_id,
                        entry.image_path,
                    )
                    failed += 1
                    self.image_failed.emit(entry.image_id, str(exc))
                else:
                    completed += 1
                    self.image_completed.emit(entry.image_id, result)
                self.progress_changed.emit(position + 1, total)
        except Exception as exc:
            logger.exception("识别队列发生未预期错误")
            self.fatal_error.emit(f"识别队列内部错误：{exc}")
        finally:
            self._busy = False
            self.queue_completed.emit(completed, failed, cancelled, total)

    @Slot(object)
    def scan_batch(self, request_object: object) -> None:
        if self._busy:
            self.batch_failed.emit("已有模型或队列操作正在运行。")
            return
        request = request_object
        if not isinstance(request, BatchScanRequest):
            self.batch_failed.emit("批处理扫描请求无效。")
            return
        self._busy = True
        try:
            result = self._batch_service.scan(
                request.options,
                cancel_event=self._batch_control.cancel_event,
                progress=lambda count, path: self.batch_scan_progress.emit(
                    count,
                    str(path),
                ),
            )
            job = self._batch_service.create_job(
                request.options,
                request.config,
                request.settings,
                scan_result=result,
            )
            self.batch_scan_completed.emit(job)
        except Exception as exc:
            logger.exception("GUI 批处理扫描失败")
            self.batch_failed.emit(str(exc))
        finally:
            self._busy = False

    @Slot(object)
    def process_batch(self, job_object: object) -> None:
        if self._busy:
            self.batch_failed.emit("已有模型或队列操作正在运行。")
            return
        if not isinstance(job_object, BatchJob):
            self.batch_failed.emit("批处理任务无效。")
            return
        self._busy = True
        try:
            job = self._batch_service.run_job(
                job_object,
                control=self._batch_control,
                on_item=lambda item, position, total: self.batch_item_changed.emit(
                    item,
                    position,
                    total,
                ),
                on_job=lambda changed: self.batch_job_changed.emit(changed),
            )
            self.batch_completed.emit(job)
        except Exception as exc:
            logger.exception("GUI 批处理执行失败")
            self.batch_failed.emit(str(exc))
        finally:
            self._busy = False

    @Slot(object)
    def retry_batch(self, job_object: object) -> None:
        if self._busy:
            self.batch_failed.emit("批处理运行期间不能重置失败条目。")
            return
        if not isinstance(job_object, BatchJob):
            self.batch_failed.emit("批处理任务无效。")
            return
        try:
            count = self._batch_service.retry_failed(job_object)
        except Exception as exc:
            logger.exception("重置批处理失败条目失败")
            self.batch_failed.emit(str(exc))
            return
        self.batch_retry_ready.emit(job_object, count)

    @Slot()
    def shutdown(self) -> None:
        self._cancel_event.set()
        self._batch_control.cancel()
        try:
            self._service.unload_model()
        except Exception as exc:
            logger.exception("GUI 关闭时释放模型失败")
            self.fatal_error.emit(f"关闭时释放模型失败：{exc}")
        finally:
            # Never strand the QThread because a provider failed to release.
            self.shutdown_ready.emit()


class InferenceController(QObject):
    """GUI-thread facade owning one worker and one ``QThread``."""

    model_loading = Signal()
    model_loaded = Signal(object)
    model_load_failed = Signal(str, bool)
    model_unloaded = Signal()
    image_started = Signal(str)
    image_completed = Signal(str, object)
    image_failed = Signal(str, str)
    image_cancelled = Signal(str)
    progress_changed = Signal(int, int)
    queue_completed = Signal(int, int, int, int)
    batch_scan_progress = Signal(int, str)
    batch_scan_completed = Signal(object)
    batch_item_changed = Signal(object, int, int)
    batch_job_changed = Signal(object)
    batch_completed = Signal(object)
    batch_retry_ready = Signal(object, int)
    batch_failed = Signal(str)
    busy_changed = Signal(bool)
    fatal_error = Signal(str)
    stopped = Signal()

    _load_requested = Signal(object, object)
    _unload_requested = Signal()
    _queue_requested = Signal(object)
    _batch_scan_requested = Signal(object)
    _batch_requested = Signal(object)
    _batch_retry_requested = Signal(object)
    _shutdown_requested = Signal()

    def __init__(
        self,
        service: TaggingService,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._thread = QThread()
        self._thread.setObjectName("AnimeTaggerInferenceThread")
        self._worker = InferenceWorker(service)
        self._worker.moveToThread(self._thread)
        self._busy = False
        self._queue_active = False
        self._batch_active = False
        self._batch_running = False
        self._batch_paused = False
        self._model_loaded = False
        self._shutdown_started = False

        self._load_requested.connect(
            self._worker.load_model,
            Qt.ConnectionType.QueuedConnection,
        )
        self._unload_requested.connect(
            self._worker.unload_model,
            Qt.ConnectionType.QueuedConnection,
        )
        self._queue_requested.connect(
            self._worker.process_queue,
            Qt.ConnectionType.QueuedConnection,
        )
        self._batch_scan_requested.connect(
            self._worker.scan_batch,
            Qt.ConnectionType.QueuedConnection,
        )
        self._batch_requested.connect(
            self._worker.process_batch,
            Qt.ConnectionType.QueuedConnection,
        )
        self._batch_retry_requested.connect(
            self._worker.retry_batch,
            Qt.ConnectionType.QueuedConnection,
        )
        self._shutdown_requested.connect(
            self._worker.shutdown,
            Qt.ConnectionType.QueuedConnection,
        )

        self._worker.model_loading.connect(self.model_loading)
        self._worker.model_loaded.connect(self._on_model_loaded)
        self._worker.model_load_failed.connect(self._on_model_load_failed)
        self._worker.model_unloaded.connect(self._on_model_unloaded)
        self._worker.model_unload_failed.connect(self._on_model_unload_failed)
        self._worker.image_started.connect(self.image_started)
        self._worker.image_completed.connect(self.image_completed)
        self._worker.image_failed.connect(self.image_failed)
        self._worker.image_cancelled.connect(self.image_cancelled)
        self._worker.progress_changed.connect(self.progress_changed)
        self._worker.queue_completed.connect(self._on_queue_completed)
        self._worker.batch_scan_progress.connect(self.batch_scan_progress)
        self._worker.batch_scan_completed.connect(
            self._on_batch_scan_completed
        )
        self._worker.batch_item_changed.connect(self.batch_item_changed)
        self._worker.batch_job_changed.connect(self.batch_job_changed)
        self._worker.batch_completed.connect(self._on_batch_completed)
        self._worker.batch_retry_ready.connect(self._on_batch_retry_ready)
        self._worker.batch_failed.connect(self._on_batch_failed)
        self._worker.fatal_error.connect(self.fatal_error)
        self._worker.shutdown_ready.connect(self._worker.deleteLater)
        self._worker.shutdown_ready.connect(self._thread.quit)
        self._thread.finished.connect(self.stopped)
        self._thread.start()

    @property
    def is_busy(self) -> bool:
        return self._busy

    @property
    def is_model_loaded(self) -> bool:
        return self._model_loaded

    @property
    def is_queue_active(self) -> bool:
        return self._queue_active

    @property
    def is_batch_active(self) -> bool:
        return self._batch_active

    @property
    def is_batch_paused(self) -> bool:
        return self._batch_paused

    @property
    def is_batch_running(self) -> bool:
        return self._batch_running

    @property
    def is_running(self) -> bool:
        return self._thread.isRunning()

    def load_model(self, model_dir: str | Path, device: Device) -> bool:
        if self._busy or self._shutdown_started:
            return False
        self._busy = True
        self.busy_changed.emit(True)
        self._load_requested.emit(str(model_dir), device)
        return True

    def unload_model(self) -> bool:
        if self._busy or self._shutdown_started:
            return False
        self._busy = True
        self.busy_changed.emit(True)
        self._unload_requested.emit()
        return True

    def start_queue(self, entries: tuple[QueueEntry, ...]) -> bool:
        if self._busy or self._shutdown_started or not entries:
            return False
        self._worker.prepare_queue()
        self._busy = True
        self._queue_active = True
        self.busy_changed.emit(True)
        self._queue_requested.emit(entries)
        return True

    def cancel(self) -> bool:
        if not self._queue_active and not self._batch_active:
            return False
        self._worker.request_cancel()
        return True

    def start_batch_scan(self, request: BatchScanRequest) -> bool:
        if self._busy or self._shutdown_started:
            return False
        self._worker.prepare_batch()
        self._busy = True
        self._batch_active = True
        self._batch_running = False
        self._batch_paused = False
        self.busy_changed.emit(True)
        self._batch_scan_requested.emit(request)
        return True

    def start_batch(self, job: BatchJob) -> bool:
        if self._busy or self._shutdown_started or not job.items:
            return False
        self._worker.prepare_batch()
        self._busy = True
        self._batch_active = True
        self._batch_running = True
        self._batch_paused = False
        self.busy_changed.emit(True)
        self._batch_requested.emit(job)
        return True

    def pause_batch(self) -> bool:
        if not self._batch_running or self._batch_paused:
            return False
        self._batch_paused = True
        self._worker.request_pause_batch()
        return True

    def resume_batch(self) -> bool:
        if not self._batch_running or not self._batch_paused:
            return False
        self._batch_paused = False
        self._worker.request_resume_batch()
        return True

    def retry_batch(self, job: BatchJob) -> bool:
        if self._busy or self._shutdown_started:
            return False
        self._busy = True
        self.busy_changed.emit(True)
        self._batch_retry_requested.emit(job)
        return True

    def shutdown(self, wait_ms: int = 0) -> bool:
        if not self._thread.isRunning():
            return True
        self._worker.request_cancel()
        if not self._shutdown_started:
            self._shutdown_started = True
            self._shutdown_requested.emit()
        if wait_ms > 0:
            return self._thread.wait(wait_ms)
        return not self._thread.isRunning()

    @Slot(object)
    def _on_model_loaded(self, info: object) -> None:
        self._busy = False
        self.busy_changed.emit(False)
        self._model_loaded = True
        self.model_loaded.emit(info)

    @Slot(str, bool)
    def _on_model_load_failed(self, message: str, still_loaded: bool) -> None:
        self._busy = False
        self.busy_changed.emit(False)
        self._model_loaded = still_loaded
        self.model_load_failed.emit(message, still_loaded)

    @Slot()
    def _on_model_unloaded(self) -> None:
        self._busy = False
        self.busy_changed.emit(False)
        self._model_loaded = False
        self.model_unloaded.emit()

    @Slot(str)
    def _on_model_unload_failed(self, message: str) -> None:
        self._busy = False
        self.busy_changed.emit(False)
        self.fatal_error.emit(f"释放模型失败：{message}")

    @Slot(int, int, int, int)
    def _on_queue_completed(
        self,
        completed: int,
        failed: int,
        cancelled: int,
        total: int,
    ) -> None:
        self._busy = False
        self._queue_active = False
        self.busy_changed.emit(False)
        self.queue_completed.emit(completed, failed, cancelled, total)

    @Slot(object)
    def _on_batch_scan_completed(self, job: object) -> None:
        self._busy = False
        self._batch_active = False
        self._batch_running = False
        self._batch_paused = False
        self.busy_changed.emit(False)
        self.batch_scan_completed.emit(job)

    @Slot(object)
    def _on_batch_completed(self, job: object) -> None:
        self._busy = False
        self._batch_active = False
        self._batch_running = False
        self._batch_paused = False
        self.busy_changed.emit(False)
        self.batch_completed.emit(job)

    @Slot(object, int)
    def _on_batch_retry_ready(self, job: object, count: int) -> None:
        self._busy = False
        self.busy_changed.emit(False)
        self.batch_retry_ready.emit(job, count)

    @Slot(str)
    def _on_batch_failed(self, message: str) -> None:
        self._busy = False
        self._batch_active = False
        self._batch_running = False
        self._batch_paused = False
        self.busy_changed.emit(False)
        self.batch_failed.emit(message)
