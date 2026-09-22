from __future__ import annotations

from pathlib import Path
import threading

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QSignalSpy

from app.batch.models import (
    BatchItemStatus,
    BatchJobStatus,
    OutputMode,
)
from app.config.settings import AppSettings
from app.inference.providers import Device
from app.ui.batch_panel import BatchPanel
from app.ui.main_window import MainWindow
from app.ui.workers.inference_worker import InferenceController
from tests.batch_helpers import FakeBatchTaggingService, touch_image


@pytest.fixture
def batch_window(qtbot, tmp_path: Path):
    widget = MainWindow(
        settings=AppSettings(model_dir=""),
        settings_path=tmp_path / "settings.json",
        ui_settings=QSettings(
            str(tmp_path / "ui.ini"),
            QSettings.Format.IniFormat,
        ),
    )
    qtbot.addWidget(widget)
    widget.show()
    yield widget
    widget.close()
    qtbot.waitUntil(lambda: not widget.controller.is_running, timeout=5000)


@pytest.fixture
def fake_panel(qtbot):
    fake = FakeBatchTaggingService(loaded=True)
    controller = InferenceController(fake)  # type: ignore[arg-type]
    controller._model_loaded = True
    panel = BatchPanel(
        controller,
        AppSettings(profile="lora_caption", model_dir="fake"),
    )
    qtbot.addWidget(panel)
    panel.show()
    yield panel, controller, fake
    controller.shutdown()
    qtbot.waitUntil(lambda: not controller.is_running, timeout=5000)


def _scan(panel: BatchPanel, root: Path, qtbot) -> None:
    panel.add_root(root)
    panel.scan()
    qtbot.waitUntil(lambda: panel.job is not None, timeout=5000)


def test_main_window_has_independent_batch_page(batch_window) -> None:
    assert batch_window.pages.count() == 3
    assert batch_window.pages.tabText(0) == "单图"
    assert batch_window.pages.tabText(1) == "批处理"
    assert batch_window.pages.tabText(2) == "随机 Prompt"
    assert batch_window.batch_panel.objectName() == "batchPanel"
    assert (
        batch_window.batch_panel.options_scroll.widget()
        is batch_window.batch_panel.options_widget
    )


def test_batch_page_starts_without_model_and_can_scan(
    batch_window,
    qtbot,
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    panel = batch_window.batch_panel
    _scan(panel, tmp_path, qtbot)
    assert panel.table_model.rowCount() == 1
    assert panel.job is not None
    assert panel.job.status is BatchJobStatus.READY
    assert not batch_window.controller.is_model_loaded


def test_scan_runs_on_worker_without_blocking_gui_event_loop(
    batch_window,
    qtbot,
    tmp_path: Path,
) -> None:
    for index in range(200):
        touch_image(tmp_path / f"{index:03}.png")
    panel = batch_window.batch_panel
    panel.add_root(tmp_path)
    spy = QSignalSpy(batch_window.controller.batch_scan_completed)
    panel.scan()
    assert batch_window.controller.is_busy
    qtbot.waitUntil(lambda: spy.count() == 1, timeout=5000)
    assert panel.table_model.rowCount() == 200


def test_scan_table_shows_existing_caption_and_output_path(
    batch_window,
    qtbot,
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    (tmp_path / "one.txt").write_text("manual", encoding="utf-8")
    panel = batch_window.batch_panel
    _scan(panel, tmp_path, qtbot)
    item = panel.table_model.item_at(0)
    assert item is not None
    assert item.caption_path == tmp_path / "one.txt"
    assert "已有 Caption 1" in panel.summary_label.text()


def test_semantic_option_change_invalidates_existing_preview(
    batch_window,
    qtbot,
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    panel = batch_window.batch_panel
    _scan(panel, tmp_path, qtbot)
    panel.recursive_check.setChecked(True)
    assert panel.job is None
    assert panel.table_model.rowCount() == 0
    assert "请重新扫描" in panel.summary_label.text()


def test_no_model_prevents_real_batch_start(
    batch_window,
    qtbot,
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    panel = batch_window.batch_panel
    _scan(panel, tmp_path, qtbot)
    panel.start()
    assert "请先在单图页加载有效模型" in panel.summary_label.text()
    assert not (tmp_path / "one.txt").exists()


def test_output_root_controls_follow_output_mode(batch_window) -> None:
    panel = batch_window.batch_panel
    assert not panel.output_root_edit.isEnabled()
    panel.output_mode_combo.setCurrentIndex(
        panel.output_mode_combo.findData(OutputMode.MIRROR.value)
    )
    assert panel.output_root_edit.isEnabled()


def test_lora_controls_build_safe_settings_snapshot(
    batch_window,
    tmp_path: Path,
) -> None:
    panel = batch_window.batch_panel
    panel.add_root(tmp_path)
    panel.trigger_edit.setText("style_token")
    request = panel._build_request()
    assert request.settings.profile == "lora_caption"
    assert request.settings.negative_mode == "none"
    assert not request.settings.include_rating
    assert request.settings.trigger_word == "style_token"


def test_batch_panel_lists_krea2_profile(batch_window) -> None:
    assert batch_window.batch_panel.profile_combo.findData("krea2") >= 0


def test_batch_panel_can_build_cyberillustrious_request(
    batch_window,
    tmp_path: Path,
) -> None:
    panel = batch_window.batch_panel
    panel.add_root(tmp_path)
    panel.lora_check.setChecked(False)
    panel.profile_combo.setCurrentIndex(
        panel.profile_combo.findData("cyberillustrious_semireal")
    )

    assert panel._build_request().settings.profile == "cyberillustrious_semireal"


def test_running_state_locks_semantic_options(fake_panel, qtbot, tmp_path: Path) -> None:
    panel, controller, _fake = fake_panel
    touch_image(tmp_path / "one.png")
    _scan(panel, tmp_path, qtbot)
    controller._busy = True
    panel.sync_controller_state()
    assert not panel.options_widget.isEnabled()
    assert not panel.scan_button.isEnabled()
    controller._busy = False
    panel.sync_controller_state()
    assert panel.options_widget.isEnabled()


def test_pause_resume_cancel_button_states(fake_panel) -> None:
    panel, controller, _fake = fake_panel
    controller._batch_active = True
    controller._batch_running = True
    controller._batch_paused = False
    panel.sync_controller_state()
    assert panel.pause_button.isEnabled()
    assert not panel.resume_button.isEnabled()
    assert panel.cancel_button.isEnabled()
    controller._batch_paused = True
    panel.sync_controller_state()
    assert not panel.pause_button.isEnabled()
    assert panel.resume_button.isEnabled()


def test_fake_batch_runs_and_updates_rows_incrementally(
    fake_panel,
    qtbot,
    tmp_path: Path,
) -> None:
    panel, controller, fake = fake_panel
    touch_image(tmp_path / "one.png")
    touch_image(tmp_path / "two.png")
    _scan(panel, tmp_path, qtbot)
    reset_spy = QSignalSpy(panel.table_model.modelReset)
    done = QSignalSpy(controller.batch_completed)
    panel.start()
    qtbot.waitUntil(lambda: done.count() == 1, timeout=5000)
    assert reset_spy.count() == 0
    assert len(fake.calls) == 2
    assert all(
        panel.table_model.item_at(row).status is BatchItemStatus.COMPLETED
        for row in range(2)
    )


def test_failure_status_filter_only_shows_failed_item(
    fake_panel,
    qtbot,
    tmp_path: Path,
) -> None:
    panel, controller, fake = fake_panel
    touch_image(tmp_path / "bad.png")
    touch_image(tmp_path / "good.png")
    fake.fail_names.add("bad.png")
    _scan(panel, tmp_path, qtbot)
    done = QSignalSpy(controller.batch_completed)
    panel.start()
    qtbot.waitUntil(lambda: done.count() == 1, timeout=5000)
    panel.status_filter.setCurrentIndex(
        panel.status_filter.findData("failed")
    )
    assert panel.table_proxy.rowCount() == 1
    assert panel.table_model.item_at(0).status is BatchItemStatus.FAILED


def test_retry_failed_button_resets_only_failed_items(
    fake_panel,
    qtbot,
    tmp_path: Path,
) -> None:
    panel, controller, fake = fake_panel
    touch_image(tmp_path / "bad.png")
    touch_image(tmp_path / "good.png")
    fake.fail_names.add("bad.png")
    _scan(panel, tmp_path, qtbot)
    done = QSignalSpy(controller.batch_completed)
    panel.start()
    qtbot.waitUntil(lambda: done.count() == 1, timeout=5000)
    ready = QSignalSpy(controller.batch_retry_ready)
    panel.retry_failed()
    qtbot.waitUntil(lambda: ready.count() == 1, timeout=5000)
    assert ready.at(0)[1] == 1
    failed = next(item for item in panel.job.items if item.source_path.name == "bad.png")
    assert failed.status is BatchItemStatus.PENDING


def test_selection_controls_do_not_reset_whole_model(
    batch_window,
    qtbot,
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    touch_image(tmp_path / "two.png")
    panel = batch_window.batch_panel
    _scan(panel, tmp_path, qtbot)
    reset_spy = QSignalSpy(panel.table_model.modelReset)
    panel.table_model.set_all_selected(False)
    assert not any(item.selected for item in panel.job.items)
    panel.table_model.invert_selected()
    assert all(item.selected for item in panel.job.items)
    assert reset_spy.count() == 0


def test_search_and_existing_filters_are_composable(
    batch_window,
    qtbot,
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "cat.png")
    touch_image(tmp_path / "dog.jpg")
    (tmp_path / "cat.txt").write_text("manual", encoding="utf-8")
    panel = batch_window.batch_panel
    _scan(panel, tmp_path, qtbot)
    panel.search_edit.setText("cat")
    assert panel.table_proxy.rowCount() == 1
    panel.existing_only_check.setChecked(True)
    assert panel.table_proxy.rowCount() == 1
    panel.search_edit.setText("dog")
    assert panel.table_proxy.rowCount() == 0


def test_clear_job_does_not_delete_images_or_outputs(
    batch_window,
    qtbot,
    tmp_path: Path,
) -> None:
    source = touch_image(tmp_path / "one.png")
    caption = tmp_path / "one.txt"
    caption.write_text("manual", encoding="utf-8")
    panel = batch_window.batch_panel
    _scan(panel, tmp_path, qtbot)
    panel.clear_job()
    assert panel.job is None
    assert source.is_file()
    assert caption.read_text(encoding="utf-8") == "manual"


def test_batch_shutdown_cancels_pending_work_without_terminate(
    qtbot,
    tmp_path: Path,
) -> None:
    fake = FakeBatchTaggingService(loaded=True)
    fake.started_event = threading.Event()
    fake.release_event = threading.Event()
    controller = InferenceController(fake)  # type: ignore[arg-type]
    controller._model_loaded = True
    panel = BatchPanel(controller, AppSettings(profile="lora_caption"))
    qtbot.addWidget(panel)
    touch_image(tmp_path / "one.png")
    touch_image(tmp_path / "two.png")
    _scan(panel, tmp_path, qtbot)
    panel.start()
    assert fake.started_event.wait(3)
    assert not controller.shutdown(wait_ms=0)
    fake.release_event.set()
    qtbot.waitUntil(lambda: not controller.is_running, timeout=5000)
    worker_text = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "ui"
        / "workers"
        / "inference_worker.py"
    ).read_text(encoding="utf-8")
    assert ".terminate(" not in worker_text
