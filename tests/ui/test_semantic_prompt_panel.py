from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QComboBox, QDialog

from app.config.settings import AppSettings
from app.ui.random_prompt_panel import RandomPromptPanel

ROOT = Path(__file__).resolve().parents[2]


def test_semantic_default_modes_copy_format_and_keep_scene(qtbot):
    panel = RandomPromptPanel(AppSettings(), model_root=ROOT)
    qtbot.addWidget(panel)
    panel.resize(1100, 900)
    panel.show()
    assert panel.mode_combo.currentData() == "semantic"
    semantic = panel.semantic_panel
    assert semantic.actor_count.value() == 1
    assert semantic.freedom_combo.currentData() == "natural"
    assert semantic.content_combo.currentData() == "ordinary"
    assert semantic.density_combo.currentData() == "standard"
    semantic.seed_edit.setText("44")
    panel.generate()
    scene = semantic._last_result.scene
    assert semantic.tags_edit.toPlainText() and semantic.english_edit.toPlainText()
    semantic.results_tabs.setCurrentIndex(1)
    panel.copy_prompt()
    assert QApplication.clipboard().text() == semantic.english_edit.toPlainText()
    semantic.results_tabs.setCurrentIndex(0)
    panel.copy_prompt()
    assert QApplication.clipboard().text() == semantic.tags_edit.toPlainText()
    assert semantic._last_result.scene is scene
    panel.mode_combo.setCurrentIndex(1)
    assert panel.tag_list is panel._legacy_tag_list
    panel.mode_combo.setCurrentIndex(0)
    assert panel.tag_list is semantic.tag_list
    assert semantic._last_result.scene is scene


def test_unsatisfied_request_retains_previous_result_and_actor_lock(qtbot):
    panel = RandomPromptPanel(AppSettings(), model_root=ROOT)
    qtbot.addWidget(panel)
    semantic = panel.semantic_panel
    semantic.seed_edit.setText("24")
    semantic.generate()
    before = semantic._last_result
    semantic.actor_tags[0].setText("red_hair, blue_hair")
    semantic.generate()
    assert semantic._last_result is before
    assert "冲突" in semantic.status_label.text()
    semantic.actor_tags[0].clear()
    semantic.actor_locks[0].setChecked(True)
    semantic.seed_edit.setText("25")
    semantic.generate()
    assert semantic._last_result.scene.actors[0] == before.scene.actors[0]


def test_import_preserves_text_and_shows_pending_multi_attributes(qtbot):
    panel = RandomPromptPanel(AppSettings(), model_root=ROOT)
    qtbot.addWidget(panel)
    semantic = panel.semantic_panel
    text = "2girls, (blue_hair:1.25), red_hair, unknown_magic"
    semantic.import_edit.setPlainText(text)
    semantic.import_tags()
    assert semantic.tags_edit.toPlainText() == text
    assert not semantic.english_edit.toPlainText()
    assert semantic.assign_button.isEnabled()
    assert semantic.results_tabs.currentIndex() == 3
    semantic._assignments = {1: 'A1', 2: 'A2'}
    semantic.import_tags()
    assert semantic.english_edit.toPlainText()
    assert semantic.tags_edit.toPlainText() == text


def test_directional_assignment_dialog_preserves_subject_order(qtbot, monkeypatch):
    panel = RandomPromptPanel(AppSettings(), model_root=ROOT)
    qtbot.addWidget(panel)
    semantic = panel.semantic_panel
    semantic.import_edit.setPlainText("2girls, hand_on_another's_head")
    semantic.import_tags()
    assert len(semantic._last_result.unassigned) == 1

    def submit(dialog):
        combo = dialog.findChild(QComboBox)
        assert combo is not None
        option = next(index for index in range(combo.count()) if tuple(combo.itemData(index) or ()) == ('A2', 'A1'))
        assert 'A2' in combo.itemText(option) and 'A1' in combo.itemText(option)
        combo.setCurrentIndex(option)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QDialog, 'exec', submit)
    semantic.assign_tags()
    assert semantic._last_result.scene.interactions[0].participants == ('A2', 'A1')
    assert not semantic._last_result.blocking and semantic.english_edit.toPlainText()
