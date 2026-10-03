import json
from pathlib import Path
import shutil

from PySide6.QtCore import QByteArray, QEvent, QSettings, Qt
from PySide6.QtGui import QHelpEvent
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication
import pytest

from app.config.settings import AppSettings
from app.export_service import ExportService, ExportFormat
from app.inference.model_loader import TagCategory
from app.prompts.models import TagResult
from app.services.tagging_service import TaggingService
from app.tag_visuals import TagVisualLibrary
from app.tag_visual_svg import compose_svg
from app.ui.main_window import MainWindow
from app.ui.tag_table_model import TagColumn, TagTableModel
from app.ui.tag_visual_widgets import TagListView, TagVisualProvider
from app.ui.theme import PRESETS, ink
from tests.ui.helpers import build_completed_payload


def make_window(qtbot, tmp_path):
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    window = MainWindow(settings=AppSettings(model_dir=str(tmp_path / "missing")),
                        settings_path=tmp_path / "settings.json", ui_settings=settings)
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()
    return window


def hover(view, delegate, index):
    view.scrollTo(index)
    QApplication.processEvents()
    point = view.visualRect(index).center()
    QApplication.sendEvent(view.viewport(), QHelpEvent(QEvent.Type.ToolTip, point, view.viewport().mapToGlobal(point)))
    assert delegate.card.isVisible()
    return delegate.card


def test_table_retains_english_columns_and_updates_after_edit(qapp):
    model = TagTableModel([TagResult("blue_hair", .9, TagCategory.GENERAL)])
    index = model.index(0, TagColumn.TAG)
    assert model.columnCount() == 6
    assert index.data(Qt.ItemDataRole.DisplayRole) == index.data(Qt.ItemDataRole.EditRole) == "blue_hair"
    assert not index.data(Qt.ItemDataRole.DecorationRole).isNull()
    model.setData(index, "red_hair", Qt.ItemDataRole.EditRole)
    assert model.visual_at(0).label_zh == "红色头发"
    assert index.data(Qt.ItemDataRole.EditRole) == "red_hair"


def test_toggle_does_not_change_prompt_or_export_bytes(qapp, tmp_path):
    inference, tags, _ = build_completed_payload(tmp_path / "input.png")
    model = TagTableModel(tags)
    spy = QSignalSpy(model.tags_changed)
    service = TaggingService()
    exporter = ExportService()
    settings = AppSettings()
    before = service.rebuild_prompts(model.tags, settings)
    before_json = exporter.build_json_document(before, inference, working_tags=model.tags)
    for enabled in (False, True):
        model.visual_provider.set_enabled(enabled)
        after = service.rebuild_prompts(model.tags, settings)
        assert after == before
        assert exporter.build_json_document(after, inference, working_tags=model.tags) == before_json
        assert spy.count() == 0
        assert model.tags == tags
        name = "on" if enabled else "off"
        for suffix, export_format in (("txt", ExportFormat.TXT), ("json", ExportFormat.JSON)):
            exporter.export(export_format, tmp_path / (name+"."+suffix), after, inference, working_tags=model.tags)
    assert (tmp_path / "on.txt").read_bytes() == (tmp_path / "off.txt").read_bytes()
    assert (tmp_path / "on.json").read_bytes() == (tmp_path / "off.json").read_bytes()


def test_both_views_share_persistent_toggle(qtbot, tmp_path):
    window = make_window(qtbot, tmp_path)
    tag = TagResult("white_shirt", .9, TagCategory.GENERAL)
    window.tag_model.set_tags([tag])
    view = window.random_prompt_panel.tag_list
    view.set_tags([tag])
    assert view.tag_model.provider is window.tag_visual_provider
    window.tag_visuals_check.setChecked(False)
    assert window.tag_model.index(0, TagColumn.TAG).data(Qt.ItemDataRole.DecorationRole) is None
    assert view.tag_model.index(0).data(Qt.ItemDataRole.DecorationRole) is None
    window.close()
    qtbot.waitUntil(lambda: not window.isVisible(), timeout=5000)
    reopened = make_window(qtbot, tmp_path)
    assert not reopened.tag_visuals_check.isChecked()
    reopened.close()


def test_hover_is_plain_text_and_closes_on_edit_scroll_page_and_toggle(qtbot, tmp_path):
    window = make_window(qtbot, tmp_path)
    tags = [TagResult("blue_hair", .9-i*.001, TagCategory.GENERAL) for i in range(75)]
    window.tag_model.set_tags(tags)
    delegate = window.tag_visual_delegate
    card = hover(window.tag_table, delegate, window.tag_proxy.index(0, TagColumn.TAG))
    assert card.title.text() == "blue_hair"
    assert card.label.text() == "蓝色头发"
    assert card.image.size().width() == 160 and card.title.textFormat() == Qt.TextFormat.PlainText
    assert card.width() >= 440
    window.tag_model.setData(window.tag_model.index(0, TagColumn.TAG), "green_eyes", Qt.ItemDataRole.EditRole)
    assert not card.isVisible()
    for action in (lambda: window.tag_table.verticalScrollBar().setValue(10),
                   lambda: window.tag_visuals_check.setChecked(False),
                   lambda: window.pages.setCurrentIndex(2)):
        window.pages.setCurrentIndex(0)
        window.tag_visuals_check.setChecked(True)
        hover(window.tag_table, delegate, window.tag_proxy.index(0, TagColumn.TAG))
        action()
        QApplication.processEvents()
        assert not card.isVisible()
    window.close()


def test_random_list_is_read_only_and_copies_original_english(qtbot):
    view = TagListView(TagVisualProvider())
    qtbot.addWidget(view)
    view.set_tags([TagResult("white_shirt", .9, TagCategory.GENERAL), TagResult("alice", .9, TagCategory.CHARACTER)])
    view.show()
    view.selectAll()
    qtbot.keyClick(view, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == "[general] white_shirt\n[character] alice"
    assert not view.tag_model.flags(view.tag_model.index(0)) & Qt.ItemFlag.ItemIsEditable
    assert view.tag_model.index(1).data(Qt.ItemDataRole.DecorationRole) is None


def test_model_reset_closes_random_hover(qtbot):
    view = TagListView(TagVisualProvider())
    qtbot.addWidget(view)
    view.set_tags([TagResult("blue_hair", .9, TagCategory.GENERAL)])
    view.show()
    card = hover(view, view.visual_delegate, view.tag_model.index(0))
    view.set_tags([TagResult("black_shirt", .9, TagCategory.GENERAL)])
    assert not card.isVisible()
    hover(view, view.visual_delegate, view.tag_model.index(0))
    assert card.label.text() == "黑色衬衫"


def test_unknown_pending_hover_and_chinese_search(qtbot, tmp_path):
    window = make_window(qtbot, tmp_path)
    window.tag_model.set_tags([TagResult("green_eyes", .9, TagCategory.GENERAL), TagResult("new_unknown_tag", .8, TagCategory.GENERAL)])
    window.tag_search.setText("绿色眼睛")
    assert window.tag_proxy.rowCount() == 1
    window.tag_search.setText("new_unknown")
    index = window.tag_proxy.index(0, TagColumn.TAG)
    assert index.data(Qt.ItemDataRole.DecorationRole) is None
    card = hover(window.tag_table, window.tag_visual_delegate, index)
    assert not card.image.isVisible() and "待补" in card.label.text()
    window.close()


def test_corrupt_svg_is_logged_and_text_survives(qapp, tmp_path, caplog):
    source = TagVisualLibrary()
    directory = tmp_path / "broken"
    shutil.copytree(source.directory, directory)
    path = directory / "primitives.json"
    assets = json.loads(path.read_text(encoding="utf-8"))
    assets["shapes"]["shirt"] = "<broken"
    path.write_text(json.dumps(assets), encoding="utf-8")
    provider = TagVisualProvider(library=TagVisualLibrary(directory))
    model = TagTableModel([TagResult("shirt", .9, TagCategory.GENERAL)], visual_provider=provider)
    index = model.index(0, TagColumn.TAG)
    assert index.data(Qt.ItemDataRole.DecorationRole) is None
    assert index.data() == "shirt" and "无法渲染" in caplog.text


@pytest.mark.parametrize("dpr", [1, 1.5, 2])
def test_24_and_160_pixel_icons_use_requested_dpi(qapp, dpr):
    provider = TagVisualProvider()
    visual = provider.visual_for("white_shirt", "general")
    for size in (24,160):
        bitmap = provider.pixmap(visual, size, dpr)
        assert bitmap.width() == round(size*dpr)
        assert bitmap.devicePixelRatio() == dpr
        assert not bitmap.isNull()


def test_semantic_eye_colors_survive_light_and_dark_themes(qapp):
    for surface in ("#20242c", "#ffffff"):
        provider = TagVisualProvider(surface=surface)
        for name, x, expected in (("white_pupils",33,"#ffffff"), ("blue_eyes",44,"#579bd4"),
                                  ("green_eyes",44,"#6aa780")):
            bitmap = provider.pixmap(provider.visual_for(name,"general"),128,1)
            assert bitmap.toImage().pixelColor(x,63).name() == expected


def test_cache_is_bounded_after_many_labels_and_previews(qapp):
    provider = TagVisualProvider()
    visuals = [v for v in provider.library.entries.values() if v.semantic][:600]
    for visual in visuals:
        assert provider.pixmap(visual) is not None
    for visual in visuals[:48]:
        assert provider.pixmap(visual,160,2) is not None
    assert sum(key[3]<=24 for key in provider._cache) <= 512
    assert sum(key[3]>24 for key in provider._cache) <= 32
    provider.set_surface("#ffffff")
    assert not provider._cache


def test_entire_supported_catalog_and_five_themes_are_valid_svg(qapp):
    library = TagVisualLibrary()
    for visual in library.entries.values():
        if visual.has_icon:
            assert QSvgRenderer(QByteArray(compose_svg(visual,library.directory,preview=True).encode())).isValid(), visual.key
    for colors in PRESETS.values():
        for name in ("white_hair","black_hair","blue_eyes","green_eyes","white_shirt","black_shirt"):
            visual = library.lookup(name)
            svg = compose_svg(visual,library.directory,ink=ink(colors.surface))
            assert visual.recipe["color"] in svg
            assert QSvgRenderer(QByteArray(svg.encode())).isValid()


@pytest.mark.parametrize('name', ['striped_tail','multicolored_tail','two-tone_tail'])
def test_refined_tail_patterns_stay_inside_the_shape_in_qt(qapp, name):
    provider = TagVisualProvider(surface='#ffffff')
    plain = provider.pixmap(provider.visual_for('tail','general'),128,1).toImage()
    patterned = provider.pixmap(provider.visual_for(name,'general'),128,1).toImage()
    for y in range(128):
        for x in range(128):
            if plain.pixelColor(x,y).alpha() == 0:
                # Re-stroking the trimmed edge can add subpixel antialiasing;
                # a visible stripe outside the silhouette must still fail.
                assert patterned.pixelColor(x,y).alpha() <= 4, (name,x,y)


@pytest.mark.parametrize('dpr',[1,1.5,2])
def test_all_refinements_render_in_the_five_app_themes(qapp,dpr):
    library = TagVisualLibrary()
    visuals = [v for v in library.entries.values() if (v.recipe or {}).get('refinement') == 'r1']
    for colors in PRESETS.values():
        provider = TagVisualProvider(library=library,surface=colors.surface)
        for visual in visuals:
            for size in (24,160):
                pixmap = provider.pixmap(visual,size,dpr)
                assert pixmap is not None and not pixmap.isNull(),visual.key
                assert pixmap.width() == round(size*dpr)
                assert pixmap.devicePixelRatio() == dpr
