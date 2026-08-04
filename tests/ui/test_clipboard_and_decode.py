from __future__ import annotations

from pathlib import Path
import threading
import time

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QImage
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from app.services.clipboard_service import ClipboardService
from app.ui.workers.thumbnail_worker import ImageDecodeCoordinator
from tests.ui.helpers import make_image


def test_clipboard_image_is_saved_to_tracked_temp_file(
    qtbot,
    tmp_path: Path,
) -> None:
    clipboard = QApplication.clipboard()
    image = QImage(12, 8, QImage.Format.Format_RGB32)
    image.fill(0xFF336699)
    clipboard.setImage(image)
    service = ClipboardService(temp_parent=tmp_path)
    imported = service.import_from_clipboard(clipboard)
    assert len(imported.paths) == 1
    assert imported.paths[0].is_file()
    assert imported.temporary_paths == imported.paths
    service.cleanup()
    clipboard.clear()


def test_clipboard_local_file_urls_are_imported_without_copy(
    qtbot,
    tmp_path: Path,
) -> None:
    path = make_image(tmp_path / "source.png")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    clipboard = QApplication.clipboard()
    clipboard.setMimeData(mime)
    service = ClipboardService(temp_parent=tmp_path)
    imported = service.import_from_clipboard(clipboard)
    assert imported.paths == (path,)
    assert not imported.temporary_paths
    service.cleanup()
    clipboard.clear()


def test_clipboard_text_path_is_supported(qtbot, tmp_path: Path) -> None:
    path = make_image(tmp_path / "source.jpg")
    clipboard = QApplication.clipboard()
    clipboard.setText(f'"{path}"')
    service = ClipboardService(temp_parent=tmp_path)
    imported = service.import_from_clipboard(clipboard)
    assert imported.paths == (path,)
    service.cleanup()
    clipboard.clear()


def test_clipboard_cleanup_removes_only_session_directory(
    qtbot,
    tmp_path: Path,
) -> None:
    unrelated = tmp_path / "keep.txt"
    unrelated.write_text("keep", encoding="utf-8")
    service = ClipboardService(temp_parent=tmp_path)
    session = service.session_dir
    service.cleanup()
    assert not session.exists()
    assert unrelated.read_text(encoding="utf-8") == "keep"


def test_thumbnail_decode_is_asynchronous(qtbot, tmp_path: Path) -> None:
    path = make_image(tmp_path / "thumb.png")
    coordinator = ImageDecodeCoordinator()
    spy = QSignalSpy(coordinator.thumbnail_ready)
    started = time.perf_counter()
    coordinator.request_thumbnail("id", path)
    elapsed = time.perf_counter() - started
    assert elapsed < 0.1
    qtbot.waitUntil(lambda: spy.count() == 1, timeout=3000)
    assert spy.at(0)[0] == "id"
    assert coordinator.shutdown()


def test_duplicate_thumbnail_requests_decode_once(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import app.ui.workers.thumbnail_worker as module

    path = make_image(tmp_path / "thumb.png")
    original = module.load_rgb_image
    calls: list[Path] = []

    def counted(image_path: Path, **kwargs):
        calls.append(Path(image_path))
        return original(image_path, **kwargs)

    monkeypatch.setattr(module, "load_rgb_image", counted)
    coordinator = ImageDecodeCoordinator()
    spy = QSignalSpy(coordinator.thumbnail_ready)
    coordinator.request_thumbnail("first", path)
    coordinator.request_thumbnail("second", path)
    qtbot.waitUntil(lambda: spy.count() == 2, timeout=3000)
    assert len(calls) == 1
    assert coordinator.shutdown()


def test_stale_preview_result_never_overwrites_new_selection(
    qtbot,
    tmp_path: Path,
    monkeypatch,
) -> None:
    import app.ui.workers.thumbnail_worker as module

    slow = make_image(tmp_path / "slow.png", "red")
    fast = make_image(tmp_path / "fast.png", "blue")
    original = module.load_rgb_image

    def delayed(image_path: Path, **kwargs):
        if Path(image_path).name == "slow.png":
            time.sleep(0.15)
        return original(image_path, **kwargs)

    monkeypatch.setattr(module, "load_rgb_image", delayed)
    coordinator = ImageDecodeCoordinator()
    spy = QSignalSpy(coordinator.preview_ready)
    coordinator.request_preview("slow", slow)
    coordinator.request_preview("fast", fast)
    qtbot.waitUntil(lambda: spy.count() == 1, timeout=3000)
    assert spy.at(0)[0] == "fast"
    qtbot.wait(250)
    assert all(spy.at(index)[0] == "fast" for index in range(spy.count()))
    assert coordinator.shutdown()


def test_decode_failure_emits_placeholder_signal(qtbot, tmp_path: Path) -> None:
    path = tmp_path / "broken.png"
    path.write_bytes(b"broken")
    coordinator = ImageDecodeCoordinator()
    spy = QSignalSpy(coordinator.thumbnail_failed)
    coordinator.request_thumbnail("broken", path)
    qtbot.waitUntil(lambda: spy.count() == 1, timeout=3000)
    assert spy.at(0)[0] == "broken"
    assert coordinator.shutdown()


def test_shutdown_rechecks_pool_after_initial_timeout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import app.ui.workers.thumbnail_worker as module

    path = make_image(tmp_path / "slow-shutdown.png")
    original = module.load_rgb_image
    started = threading.Event()
    release = threading.Event()

    def slow_decode(*args, **kwargs):
        started.set()
        assert release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "load_rgb_image", slow_decode)
    coordinator = ImageDecodeCoordinator()
    coordinator.request_thumbnail("slow", path)
    assert started.wait(2)
    assert not coordinator.shutdown(wait_ms=1)
    release.set()
    assert coordinator.shutdown(wait_ms=3000)
