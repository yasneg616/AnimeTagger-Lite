"""Bounded asynchronous decoding for thumbnails and the active preview."""

from __future__ import annotations

from collections import OrderedDict
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal, Slot
from PySide6.QtGui import QImage

from app.image.image_loader import load_rgb_image


class _DecodeSignals(QObject):
    finished = Signal(str, str, int, object, str)


class _DecodeTask(QRunnable):
    def __init__(
        self,
        *,
        kind: str,
        key: str,
        token: int,
        path: Path,
        target_size: int,
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        self.signals = _DecodeSignals()
        self._kind = kind
        self._key = key
        self._token = token
        self._path = Path(path)
        self._target_size = target_size
        self._cancel_event = cancel_event
        # The coordinator retains the runnable until its queued result reaches
        # the GUI thread. Auto-deleting here could destroy the signal object
        # before Qt delivers that queued emission.
        self.setAutoDelete(False)

    @Slot()
    def run(self) -> None:
        if self._cancel_event.is_set():
            return
        try:
            image = load_rgb_image(
                self._path,
                decode_target_size=self._target_size,
            )
            try:
                width, height = image.size
                data = image.tobytes("raw", "RGB")
                qimage = QImage(
                    data,
                    width,
                    height,
                    width * 3,
                    QImage.Format.Format_RGB888,
                ).copy()
            finally:
                image.close()
            if self._cancel_event.is_set():
                return
            self.signals.finished.emit(
                self._kind,
                self._key,
                self._token,
                qimage,
                "",
            )
        except Exception as exc:
            if not self._cancel_event.is_set():
                self.signals.finished.emit(
                    self._kind,
                    self._key,
                    self._token,
                    QImage(),
                    str(exc),
                )


class ImageDecodeCoordinator(QObject):
    thumbnail_ready = Signal(str, object)
    thumbnail_failed = Signal(str, str)
    preview_ready = Signal(str, int, object)
    preview_failed = Signal(str, int, str)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        thumbnail_size: int = 96,
        preview_size: int = 2048,
        cache_limit: int = 128,
    ) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._thumbnail_size = thumbnail_size
        self._preview_size = preview_size
        self._cache_limit = cache_limit
        self._thumbnail_cache: OrderedDict[str, QImage] = OrderedDict()
        self._thumbnail_waiters: dict[str, list[str]] = {}
        self._active_tasks: dict[tuple[str, str, int], _DecodeTask] = {}
        self._preview_token = 0
        self._active_preview_id = ""
        self._cancel_event = threading.Event()
        self._closed = False

    @property
    def active_preview_token(self) -> int:
        return self._preview_token

    def request_thumbnail(self, image_id: str, path: Path) -> None:
        if self._closed:
            return
        path_key = str(Path(path).resolve(strict=False)).casefold()
        cached = self._thumbnail_cache.get(path_key)
        if cached is not None:
            self._thumbnail_cache.move_to_end(path_key)
            QTimer.singleShot(
                0,
                lambda: self.thumbnail_ready.emit(image_id, cached.copy()),
            )
            return
        waiters = self._thumbnail_waiters.setdefault(path_key, [])
        waiters.append(image_id)
        if len(waiters) > 1:
            return
        self._start_task("thumbnail", path_key, 0, path, self._thumbnail_size)

    def request_preview(self, image_id: str, path: Path) -> int:
        if self._closed:
            return self._preview_token
        self._preview_token += 1
        self._active_preview_id = image_id
        token = self._preview_token
        self._start_task("preview", image_id, token, path, self._preview_size)
        return token

    def invalidate_preview(self) -> None:
        self._preview_token += 1
        self._active_preview_id = ""

    def _start_task(
        self,
        kind: str,
        key: str,
        token: int,
        path: Path,
        target_size: int,
    ) -> None:
        task = _DecodeTask(
            kind=kind,
            key=key,
            token=token,
            path=path,
            target_size=target_size,
            cancel_event=self._cancel_event,
        )
        task.signals.finished.connect(self._on_finished)
        self._active_tasks[(kind, key, token)] = task
        self._pool.start(task)

    @Slot(str, str, int, object, str)
    def _on_finished(
        self,
        kind: str,
        key: str,
        token: int,
        image_object: object,
        error: str,
    ) -> None:
        self._active_tasks.pop((kind, key, token), None)
        if self._closed:
            return
        image = image_object if isinstance(image_object, QImage) else QImage()
        if kind == "thumbnail":
            waiters = self._thumbnail_waiters.pop(key, [])
            if error or image.isNull():
                for image_id in waiters:
                    self.thumbnail_failed.emit(image_id, error or "图片解码失败")
                return
            self._thumbnail_cache[key] = image.copy()
            self._thumbnail_cache.move_to_end(key)
            while len(self._thumbnail_cache) > self._cache_limit:
                self._thumbnail_cache.popitem(last=False)
            for image_id in waiters:
                self.thumbnail_ready.emit(image_id, image.copy())
            return

        if (
            token != self._preview_token
            or key != self._active_preview_id
        ):
            return
        if error or image.isNull():
            self.preview_failed.emit(key, token, error or "图片解码失败")
        else:
            self.preview_ready.emit(key, token, image)

    def shutdown(self, wait_ms: int = 5000) -> bool:
        if not self._closed:
            self._closed = True
            self._cancel_event.set()
            self._thumbnail_cache.clear()
            self._thumbnail_waiters.clear()
        finished = self._pool.waitForDone(wait_ms)
        if finished:
            self._active_tasks.clear()
        return finished
