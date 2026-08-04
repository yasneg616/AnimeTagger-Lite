from __future__ import annotations

from pathlib import Path
import threading

from PySide6.QtCore import QThread
from PySide6.QtTest import QSignalSpy

from app.config.settings import AppSettings
from app.inference.providers import Device
from app.services.tagging_service import AnalysisResult
from app.ui.workers.inference_worker import InferenceController, QueueEntry
from tests.ui.helpers import build_completed_payload


class FakeWorkerService:
    def __init__(self) -> None:
        self.loaded = False
        self.calls: list[str] = []
        self.thread_objects: list[QThread] = []
        self.fail_names: set[str] = set()
        self.fail_unload = False
        self.started_event: threading.Event | None = None
        self.release_event: threading.Event | None = None
        self.info = build_completed_payload(Path("image.png"))[0].model_info

    @property
    def is_model_loaded(self) -> bool:
        return self.loaded

    def load_model(self, _path: Path, device: Device):
        del device
        self.thread_objects.append(QThread.currentThread())
        self.loaded = True
        return self.info

    def unload_model(self) -> None:
        if self.fail_unload:
            raise RuntimeError("release failed")
        self.loaded = False

    def analyze_image(
        self,
        path: Path,
        _settings: AppSettings,
    ) -> AnalysisResult:
        self.thread_objects.append(QThread.currentThread())
        self.calls.append(path.name)
        if self.started_event is not None:
            self.started_event.set()
        if self.release_event is not None:
            assert self.release_event.wait(3)
        if path.name in self.fail_names:
            raise RuntimeError(f"failed {path.name}")
        inference, raw, prompts = build_completed_payload(path)
        return AnalysisResult(inference, raw, prompts)


def stop_controller(controller: InferenceController, qtbot) -> None:
    controller.shutdown()
    qtbot.waitUntil(lambda: not controller.is_running, timeout=4000)


def test_model_loading_runs_outside_gui_thread(qtbot, tmp_path: Path) -> None:
    service = FakeWorkerService()
    controller = InferenceController(service)  # type: ignore[arg-type]
    spy = QSignalSpy(controller.model_loaded)
    assert controller.load_model(tmp_path, Device.CPU)
    qtbot.waitUntil(lambda: spy.count() == 1, timeout=3000)
    assert service.thread_objects[0] is not QThread.currentThread()
    stop_controller(controller, qtbot)


def test_cancel_is_not_offered_for_model_lifecycle_operation(
    qtbot,
    tmp_path: Path,
) -> None:
    service = FakeWorkerService()
    controller = InferenceController(service)  # type: ignore[arg-type]
    loaded = QSignalSpy(controller.model_loaded)
    assert controller.load_model(tmp_path, Device.CPU)
    assert not controller.cancel()
    qtbot.waitUntil(lambda: loaded.count() == 1, timeout=3000)
    stop_controller(controller, qtbot)


def test_single_image_success_emits_typed_result(qtbot, tmp_path: Path) -> None:
    service = FakeWorkerService()
    service.loaded = True
    controller = InferenceController(service)  # type: ignore[arg-type]
    spy = QSignalSpy(controller.image_completed)
    done = QSignalSpy(controller.queue_completed)
    assert controller.start_queue(
        (QueueEntry("one", tmp_path / "one.png", AppSettings()),)
    )
    qtbot.waitUntil(lambda: done.count() == 1, timeout=3000)
    assert spy.count() == 1
    assert isinstance(spy.at(0)[1], AnalysisResult)
    stop_controller(controller, qtbot)


def test_multiple_images_are_processed_in_order(qtbot, tmp_path: Path) -> None:
    service = FakeWorkerService()
    service.loaded = True
    controller = InferenceController(service)  # type: ignore[arg-type]
    done = QSignalSpy(controller.queue_completed)
    entries = tuple(
        QueueEntry(str(index), tmp_path / f"{index}.png", AppSettings())
        for index in range(3)
    )
    assert controller.start_queue(entries)
    qtbot.waitUntil(lambda: done.count() == 1, timeout=3000)
    assert service.calls == ["0.png", "1.png", "2.png"]
    assert done.at(0) == [3, 0, 0, 3]
    stop_controller(controller, qtbot)


def test_one_image_failure_does_not_abort_queue(qtbot, tmp_path: Path) -> None:
    service = FakeWorkerService()
    service.loaded = True
    service.fail_names.add("bad.png")
    controller = InferenceController(service)  # type: ignore[arg-type]
    failed = QSignalSpy(controller.image_failed)
    done = QSignalSpy(controller.queue_completed)
    entries = (
        QueueEntry("bad", tmp_path / "bad.png", AppSettings()),
        QueueEntry("good", tmp_path / "good.png", AppSettings()),
    )
    assert controller.start_queue(entries)
    qtbot.waitUntil(lambda: done.count() == 1, timeout=3000)
    assert failed.count() == 1
    assert service.calls == ["bad.png", "good.png"]
    assert done.at(0) == [1, 1, 0, 2]
    stop_controller(controller, qtbot)


def test_repeated_start_does_not_create_parallel_queue(
    qtbot,
    tmp_path: Path,
) -> None:
    service = FakeWorkerService()
    service.loaded = True
    service.started_event = threading.Event()
    service.release_event = threading.Event()
    controller = InferenceController(service)  # type: ignore[arg-type]
    entry = (QueueEntry("one", tmp_path / "one.png", AppSettings()),)
    assert controller.start_queue(entry)
    assert service.started_event.wait(2)
    assert not controller.start_queue(entry)
    service.release_event.set()
    qtbot.waitUntil(lambda: not controller.is_busy, timeout=3000)
    stop_controller(controller, qtbot)


def test_cancel_stops_before_next_image(qtbot, tmp_path: Path) -> None:
    service = FakeWorkerService()
    service.loaded = True
    service.started_event = threading.Event()
    service.release_event = threading.Event()
    controller = InferenceController(service)  # type: ignore[arg-type]
    cancelled = QSignalSpy(controller.image_cancelled)
    done = QSignalSpy(controller.queue_completed)
    entries = (
        QueueEntry("first", tmp_path / "first.png", AppSettings()),
        QueueEntry("second", tmp_path / "second.png", AppSettings()),
    )
    assert controller.start_queue(entries)
    assert service.started_event.wait(2)
    assert controller.cancel()
    service.release_event.set()
    qtbot.waitUntil(lambda: done.count() == 1, timeout=3000)
    assert service.calls == ["first.png"]
    assert cancelled.count() == 1
    assert cancelled.at(0)[0] == "second"
    stop_controller(controller, qtbot)


def test_immediate_cancel_is_not_erased_when_worker_starts(
    qtbot,
    tmp_path: Path,
) -> None:
    service = FakeWorkerService()
    service.loaded = True
    service.started_event = threading.Event()
    service.release_event = threading.Event()
    controller = InferenceController(service)  # type: ignore[arg-type]
    done = QSignalSpy(controller.queue_completed)
    entries = (
        QueueEntry("first", tmp_path / "first.png", AppSettings()),
        QueueEntry("second", tmp_path / "second.png", AppSettings()),
    )
    assert controller.start_queue(entries)
    assert controller.cancel()
    service.release_event.set()
    qtbot.waitUntil(lambda: done.count() == 1, timeout=3000)
    assert "second.png" not in service.calls
    stop_controller(controller, qtbot)


def test_unload_failure_clears_busy_and_shutdown_still_stops_thread(
    qtbot,
    tmp_path: Path,
) -> None:
    service = FakeWorkerService()
    controller = InferenceController(service)  # type: ignore[arg-type]
    loaded = QSignalSpy(controller.model_loaded)
    assert controller.load_model(tmp_path, Device.CPU)
    qtbot.waitUntil(lambda: loaded.count() == 1, timeout=3000)

    service.fail_unload = True
    failed = QSignalSpy(controller.fatal_error)
    assert controller.unload_model()
    qtbot.waitUntil(lambda: failed.count() == 1, timeout=3000)
    assert "释放模型失败" in failed.at(0)[0]
    assert not controller.is_busy

    controller.shutdown()
    qtbot.waitUntil(lambda: not controller.is_running, timeout=4000)


def test_shutdown_cancels_queue_without_thread_terminate(
    qtbot,
    tmp_path: Path,
) -> None:
    service = FakeWorkerService()
    service.loaded = True
    service.started_event = threading.Event()
    service.release_event = threading.Event()
    controller = InferenceController(service)  # type: ignore[arg-type]
    controller.start_queue(
        (
            QueueEntry("first", tmp_path / "first.png", AppSettings()),
            QueueEntry("second", tmp_path / "second.png", AppSettings()),
        )
    )
    assert service.started_event.wait(2)
    assert not controller.shutdown(wait_ms=10)
    service.release_event.set()
    qtbot.waitUntil(lambda: not controller.is_running, timeout=4000)
    assert not service.loaded


def test_immediate_shutdown_does_not_lose_queue_cancellation(
    qtbot,
    tmp_path: Path,
) -> None:
    service = FakeWorkerService()
    service.loaded = True
    service.started_event = threading.Event()
    service.release_event = threading.Event()
    controller = InferenceController(service)  # type: ignore[arg-type]
    entries = (
        QueueEntry("first", tmp_path / "first.png", AppSettings()),
        QueueEntry("second", tmp_path / "second.png", AppSettings()),
    )
    assert controller.start_queue(entries)
    assert not controller.shutdown(wait_ms=0)
    service.release_event.set()
    qtbot.waitUntil(lambda: not controller.is_running, timeout=4000)
    assert "second.png" not in service.calls
    assert not service.loaded


def test_worker_module_never_imports_qwidget() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "ui"
        / "workers"
        / "inference_worker.py"
    )
    text = path.read_text(encoding="utf-8")
    assert "QWidget" not in text
    assert ".terminate(" not in text
