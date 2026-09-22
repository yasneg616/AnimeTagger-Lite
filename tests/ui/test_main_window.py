from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, QSettings, Qt, QMimeData, QUrl
from PySide6.QtGui import QDropEvent, QImage
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QMessageBox

from app import __version__
from app.config.settings import AppSettings
from app.export_service import ExportFormat
from app.inference.model_loader import TagCategory
from app.prompts.models import TagResult
from app.ui.image_list_widget import ImageListWidget
from app.ui.main_window import MainWindow
from app.ui.tag_table_model import TagColumn
from tests.ui.helpers import build_completed_payload, make_image


@pytest.fixture
def window(qtbot, tmp_path: Path):
    ui_settings = QSettings(
        str(tmp_path / "ui.ini"),
        QSettings.Format.IniFormat,
    )
    widget = MainWindow(
        settings=AppSettings(model_dir=str(tmp_path / "missing-model")),
        settings_path=tmp_path / "settings.json",
        ui_settings=ui_settings,
    )
    qtbot.addWidget(widget)
    widget.show()
    yield widget
    widget.close()
    qtbot.waitUntil(lambda: not widget.controller.is_running, timeout=5000)


def complete_item(window: MainWindow, path: Path):
    item = window.project.get(window.project.current_id)
    assert item is not None
    inference, raw, prompts = build_completed_payload(path)
    item.apply_analysis(inference, raw, prompts)
    window.image_list.update_image_item(item)
    window._show_current(item)
    return item


def test_gui_starts_without_model_and_shows_missing_files(window) -> None:
    assert window.isVisible()
    assert "model.safetensors" in window.model_status.status_text
    assert not window.start_action.isEnabled()


def test_about_dialog_uses_shared_version(
    window,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "about",
        lambda _parent, title, text: shown.append((title, text)),
    )

    window.about_action.trigger()

    assert shown == [
        (
            "关于 AnimeTagger Lite",
            f"AnimeTagger Lite {__version__}\n\n"
            "本地、离线的 WD14 动漫图片标签与提示词工具。\n"
            "软件不会上传图片、发送遥测或后台下载模型。",
        )
    ]


def test_main_window_create_and_close_stops_worker(
    qtbot,
    tmp_path: Path,
) -> None:
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
    assert widget.controller.is_running
    widget.close()
    qtbot.waitUntil(lambda: not widget.controller.is_running, timeout=4000)


def test_add_single_image_updates_list(window, tmp_path: Path) -> None:
    result = window.add_paths([make_image(tmp_path / "one.png")])
    assert len(result.added) == 1
    assert window.image_list.count() == 1


def test_add_multiple_images_updates_list(window, tmp_path: Path) -> None:
    result = window.add_paths(
        [
            make_image(tmp_path / "one.png"),
            make_image(tmp_path / "two.jpg"),
        ]
    )
    assert len(result.added) == 2
    assert window.image_list.count() == 2


def test_duplicate_path_not_added_twice(window, tmp_path: Path) -> None:
    path = make_image(tmp_path / "one.png")
    window.add_paths([path])
    result = window.add_paths([path])
    assert result.duplicates == (path,)
    assert window.image_list.count() == 1


def test_unsupported_file_is_rejected_as_summary(window, tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("text", encoding="utf-8")
    result = window.add_paths([path])
    assert result.unsupported == (path,)
    assert "不支持" in window.statusBar().currentMessage()


def test_directory_drop_does_not_scan(window, tmp_path: Path) -> None:
    make_image(tmp_path / "inside.png")
    result = window.add_paths([tmp_path])
    assert result.directories == (tmp_path,)
    assert window.image_list.count() == 0
    assert "后续阶段" in window.statusBar().currentMessage()


def test_image_list_drop_emits_local_paths(qtbot, tmp_path: Path) -> None:
    path = make_image(tmp_path / "drop.png")
    widget = ImageListWidget()
    qtbot.addWidget(widget)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    event = QDropEvent(
        QPointF(4, 4),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    spy = QSignalSpy(widget.paths_dropped)
    widget.dropEvent(event)
    assert spy.count() == 1
    assert spy.at(0)[0] == [path]


def test_image_switch_keeps_independent_tag_state(window, tmp_path: Path) -> None:
    first = make_image(tmp_path / "first.png")
    second = make_image(tmp_path / "second.png")
    added = window.add_paths([first, second]).added
    added[0].working_tags = [
        TagResult("first_tag", 0.9, TagCategory.GENERAL)
    ]
    added[1].working_tags = [
        TagResult("second_tag", 0.9, TagCategory.GENERAL)
    ]
    window.image_list.select_image_id(added[1].id)
    assert window.tag_model.tags[0].name == "second_tag"
    window.image_list.select_image_id(added[0].id)
    assert window.tag_model.tags[0].name == "first_tag"


def test_thumbnail_and_preview_load_asynchronously(
    window,
    qtbot,
    tmp_path: Path,
) -> None:
    path = make_image(tmp_path / "preview.png")
    thumb = QSignalSpy(window.decoder.thumbnail_ready)
    preview = QSignalSpy(window.decoder.preview_ready)
    window.add_paths([path])
    qtbot.waitUntil(lambda: thumb.count() >= 1, timeout=3000)
    qtbot.waitUntil(lambda: preview.count() >= 1, timeout=3000)
    assert window.preview.has_image


def test_edit_tag_rebuilds_prompt_without_changing_raw(
    window,
    tmp_path: Path,
) -> None:
    path = make_image(tmp_path / "one.png")
    window.add_paths([path])
    item = complete_item(window, path)
    raw_name = item.raw_tags[0].name
    assert window.tag_model.setData(
        window.tag_model.index(0, TagColumn.TAG),
        "custom_tag",
        Qt.ItemDataRole.EditRole,
    )
    assert item.raw_tags[0].name == raw_name
    assert "custom_tag" in item.generated_positive_prompt


def test_add_and_delete_manual_tag(window, tmp_path: Path) -> None:
    path = make_image(tmp_path / "one.png")
    window.add_paths([path])
    complete_item(window, path)
    assert window.tag_model.add_manual_tag("manual_tag")
    assert any(tag.name == "manual_tag" for tag in window.tag_model.tags)
    row = next(
        index
        for index, tag in enumerate(window.tag_model.tags)
        if tag.name == "manual_tag"
    )
    window.tag_model.remove_source_rows([row])
    assert all(tag.name != "manual_tag" for tag in window.tag_model.tags)


def test_disabled_tag_updates_generated_prompt(window, tmp_path: Path) -> None:
    path = make_image(tmp_path / "one.png")
    window.add_paths([path])
    item = complete_item(window, path)
    assert "1girl" in item.generated_positive_prompt
    window.tag_model.setData(
        window.tag_model.index(0, TagColumn.ENABLED),
        Qt.CheckState.Unchecked,
        Qt.ItemDataRole.CheckStateRole,
    )
    assert "1girl" not in item.generated_positive_prompt


def test_manual_prompt_is_not_silently_overwritten_by_profile_change(
    window,
    tmp_path: Path,
) -> None:
    path = make_image(tmp_path / "one.png")
    window.add_paths([path])
    item = complete_item(window, path)
    window.prompt_panel._editors["positive"].setPlainText("manual prompt")
    assert item.positive_prompt_edited
    window.profile_combo.setCurrentIndex(
        window.profile_combo.findData("anime")
    )
    assert item.final_positive_prompt == "manual prompt"
    assert item.prompt_stale


def test_lora_profile_forces_negative_none_and_shows_trigger(
    window,
    tmp_path: Path,
) -> None:
    path = make_image(tmp_path / "one.png")
    window.add_paths([path])
    complete_item(window, path)
    window.profile_combo.setCurrentIndex(
        window.profile_combo.findData("lora_caption")
    )
    assert window.settings.negative_mode == "none"
    assert window.trigger_edit.isVisible()


def test_krea2_profile_is_available_and_generates_prose(
    window,
    tmp_path: Path,
) -> None:
    path = make_image(tmp_path / "one.png")
    window.add_paths([path])
    item = complete_item(window, path)
    window.profile_combo.setCurrentIndex(
        window.profile_combo.findData("krea2")
    )

    assert window.settings.profile == "krea2"
    assert item.generated_positive_prompt.startswith("An anime illustration")
    assert "\n\n" in item.generated_positive_prompt


def test_cyberillustrious_profile_is_available_and_rebuilds_without_inference(
    window,
    tmp_path: Path,
) -> None:
    path = make_image(tmp_path / "one.png")
    window.add_paths([path])
    item = complete_item(window, path)
    raw_before = item.raw_tags
    window.profile_combo.setCurrentIndex(
        window.profile_combo.findData("cyberillustrious_semireal")
    )

    assert window.settings.profile == "cyberillustrious_semireal"
    assert "semi-realistic" in item.generated_positive_prompt
    assert item.raw_tags == raw_before


def test_copy_positive_writes_clipboard(window, tmp_path: Path) -> None:
    path = make_image(tmp_path / "one.png")
    window.add_paths([path])
    item = complete_item(window, path)
    window._copy_prompt("positive")
    assert QApplication.clipboard().text() == item.final_positive_prompt


def test_copy_combined_omits_empty_negative_section(
    window,
    tmp_path: Path,
) -> None:
    path = make_image(tmp_path / "one.png")
    window.add_paths([path])
    complete_item(window, path)
    window._copy_prompt("combined")
    text = QApplication.clipboard().text()
    assert text.startswith("Positive:\n")
    assert "Negative:" not in text


def test_export_current_calls_shared_service(
    window,
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = make_image(tmp_path / "one.png")
    window.add_paths([path])
    item = complete_item(window, path)
    item.edit_prompt("positive", "edited final")
    calls: list[dict[str, object]] = []

    def fake_export(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return Path(args[1])

    monkeypatch.setattr(window.service, "export_result", fake_export)
    output = tmp_path / "caption.txt"
    assert window.export_current_to(output, ExportFormat.TXT)
    assert calls[0]["kwargs"]["final_positive_prompt"] == "edited final"
    assert calls[0]["kwargs"]["model_raw_tags"] == item.raw_tags
    assert calls[0]["kwargs"]["working_tags"] == item.working_tags
    assert calls[0]["kwargs"]["overwrite"] is False


def test_export_default_refuses_existing_file(
    window,
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = make_image(tmp_path / "one.png")
    window.add_paths([path])
    complete_item(window, path)
    output = tmp_path / "caption.txt"
    output.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: None)
    assert not window.export_current_to(output, ExportFormat.TXT)
    assert output.read_text(encoding="utf-8") == "keep"


def test_start_queue_blocks_backend_mismatch(
    window,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = make_image(tmp_path / "one.png")
    window.add_paths([path])
    window.controller._model_loaded = True
    window.service._backend = "wd_v3"
    window.settings = replace(window.settings, backend="pixai_v0_9")
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, text: warnings.append((title, text)),
    )
    started: list[object] = []
    monkeypatch.setattr(
        window.controller,
        "start_queue",
        lambda entries: started.append(entries) or True,
    )

    window._start_selected_queue()

    assert started == []
    assert warnings and warnings[0][0] == "后端与模型不一致"
    assert "加载模型" in warnings[0][1]


def test_window_state_is_saved_to_qsettings(window) -> None:
    window.main_splitter.setSizes([200, 400, 600])
    window._save_ui_state()
    assert window.ui_settings.contains("main/geometry")
    assert window.ui_settings.contains("main/splitter")
    assert window.ui_settings.contains("main/tag_header")


def test_busy_state_disables_controls_that_could_be_overwritten(window) -> None:
    window.controller._busy = True
    window.controller._queue_active = True
    window._update_action_states()
    assert window.cancel_action.isEnabled()
    assert not window.model_status.isEnabled()
    assert not window.tag_table.isEnabled()
    assert not window.prompt_panel.isEnabled()
    assert not window.profile_combo.isEnabled()
    assert not window.general_spin.isEnabled()

    window.controller._busy = False
    window.controller._queue_active = False
    window._update_action_states()


def test_clipboard_session_files_are_cleaned_on_window_close(
    qtbot,
    tmp_path: Path,
) -> None:
    widget = MainWindow(
        settings=AppSettings(model_dir=""),
        settings_path=tmp_path / "settings.json",
        ui_settings=QSettings(
            str(tmp_path / "ui.ini"),
            QSettings.Format.IniFormat,
        ),
    )
    qtbot.addWidget(widget)
    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    QApplication.clipboard().setImage(image)
    imported = widget.clipboard_service.import_from_clipboard(
        QApplication.clipboard()
    )
    session = widget.clipboard_service.session_dir
    widget.add_paths(imported.paths, temporary_paths=imported.temporary_paths)
    assert session.exists()
    widget.close()
    qtbot.waitUntil(
        lambda: not widget.controller.is_running and not session.exists(),
        timeout=4000,
    )
