from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.ui.palette_dialog import PaletteDialog
from app.ui.theme import PRESETS, ThemeColors, apply_theme


def test_theme_roundtrip_and_invalid_saved_color(tmp_path):
    settings = QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat)
    colors = PRESETS["晴昼"]
    colors.save(settings)
    assert ThemeColors.load(settings) == colors
    settings.setValue("appearance/accent", "red; bad-qss")
    assert ThemeColors.load(settings).accent == ThemeColors().accent


def test_palette_cancel_restores_live_preview(qtbot):
    original = ThemeColors()
    apply_theme(original)
    initial = QApplication.instance().styleSheet()
    dialog = PaletteDialog(original)
    qtbot.addWidget(dialog)
    dialog.set_colors(PRESETS["晴昼"])
    assert QApplication.instance().styleSheet() != initial
    dialog.reject()
    assert QApplication.instance().styleSheet() == initial


def test_palette_accept_keeps_colors_and_reset(qtbot):
    dialog = PaletteDialog(ThemeColors())
    qtbot.addWidget(dialog)
    dialog.presets.setCurrentText("青松")
    assert dialog.colors == PRESETS["青松"]
    dialog.accept()
    assert PRESETS["青松"].accent in QApplication.instance().styleSheet()
    apply_theme(ThemeColors())
