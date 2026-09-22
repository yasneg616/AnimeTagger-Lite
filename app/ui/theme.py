"""Modern desktop palette, with validated persistent user colors."""
from __future__ import annotations

from dataclasses import dataclass
import re

from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication


@dataclass(frozen=True)
class ThemeColors:
    accent: str = "#a997ff"
    background: str = "#15171c"
    surface: str = "#20242c"

    @classmethod
    def load(cls, settings: QSettings) -> "ThemeColors":
        defaults = cls()
        return cls(**{
            key: value if re.fullmatch(r"#[0-9a-fA-F]{6}", value) else getattr(defaults, key)
            for key in ("accent", "background", "surface")
            for value in [str(settings.value(f"appearance/{key}", getattr(defaults, key))) ]
        })

    def save(self, settings: QSettings) -> None:
        for key in ("accent", "background", "surface"):
            settings.setValue(f"appearance/{key}", getattr(self, key))
        settings.sync()


PRESETS = {
    "暮紫": ThemeColors(),
    "海蓝": ThemeColors("#70b8ff", "#131a23", "#202d3b"),
    "青松": ThemeColors("#73d6b0", "#131c1b", "#21302d"),
    "暖砂": ThemeColors("#e9bc86", "#211c19", "#302a25"),
    "晴昼": ThemeColors("#7355cf", "#eff1f6", "#ffffff"),
}


def ink(color: str) -> str:
    c = QColor(color)
    return "#19202b" if 0.2126*c.redF() + 0.7152*c.greenF() + 0.0722*c.blueF() > .57 else "#eef1f8"


def stylesheet(colors: ThemeColors) -> str:
    bg, surface, accent = colors.background, colors.surface, colors.accent
    text, on_accent = ink(surface), ink(accent)
    light = text == "#19202b"
    muted = "#626b7b" if light else "#a4aebe"
    border = QColor(surface).darker(118).name() if light else QColor(surface).lighter(145).name()
    hover = QColor(surface).darker(108).name() if light else QColor(surface).lighter(125).name()
    return f"""
QWidget {{ color: {text}; font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: 10pt; }}
QMainWindow, QDialog, QTabWidget::pane {{ background: {bg}; }}
QWidget#workspace, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {bg}; }}
QWidget[card="true"], QGroupBox {{ background: {surface}; border: 1px solid {border}; border-radius: 10px; }}
QLabel {{ background: transparent; border: none; }}
QLabel[heading="true"] {{ font-size: 12pt; font-weight: 600; }}
QLabel[muted="true"] {{ color: {muted}; }}
QLabel#brand {{ font-size: 14pt; font-weight: 600; padding: 4px 12px; }}
QToolBar {{ background: {bg}; border: none; spacing: 8px; padding: 8px; }}
QPushButton, QToolButton {{ background: {surface}; border: 1px solid {border}; border-radius: 7px; padding: 6px 12px; }}
QPushButton:hover, QToolButton:hover {{ background: {hover}; border-color: {accent}; }}
QPushButton[primary="true"], QToolButton[primary="true"] {{ background: {accent}; color: {on_accent}; border-color: {accent}; font-weight: 600; }}
QPushButton:disabled, QToolButton:disabled {{ color: {muted}; background: {surface}; border-color: {border}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background: {surface}; border: 1px solid {border}; border-radius: 6px; padding: 5px 8px; min-height: 20px; selection-background-color: {accent}; selection-color: {on_accent}; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border-color: {accent}; }}
QComboBox QAbstractItemView, QMenu {{ background: {surface}; color: {text}; selection-background-color: {accent}; selection-color: {on_accent}; border: 1px solid {border}; padding: 5px; }}
QMenu::item {{ padding: 7px 18px; }}
QMenu::item:selected {{ background: {accent}; color: {on_accent}; }}
QPlainTextEdit {{ background: {bg}; color: {ink(bg)}; border: 1px solid {border}; border-radius: 6px; padding: 8px; selection-background-color: {accent}; selection-color: {on_accent}; font-family: Consolas, 'Microsoft YaHei UI'; }}
QTableView, QListWidget {{ background: {surface}; alternate-background-color: {hover}; border: none; outline: none; selection-background-color: {accent}; selection-color: {on_accent}; }}
QListWidget::item {{ padding: 6px; border: 1px solid transparent; border-radius: 7px; }}
QListWidget::item:selected {{ background: {hover}; color: {text}; border: 1px solid {accent}; }}
QListWidget::item:hover {{ background: {hover}; }}
QTableView::item {{ padding: 5px; border: none; }}
QHeaderView::section {{ background: {surface}; color: {muted}; padding: 7px 4px; border: none; border-bottom: 1px solid {border}; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: {bg}; color: {muted}; padding: 11px 24px; border-bottom: 3px solid transparent; }}
QTabBar::tab:selected {{ color: {text}; background: {surface}; border-bottom-color: {accent}; }}
QGroupBox {{ margin-top: 14px; padding: 10px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 5px; font-weight: 600; }}
QSplitter::handle {{ background: {bg}; width: 8px; height: 8px; }}
QScrollBar:vertical {{ width: 9px; background: {surface}; margin: 0; }}
QScrollBar:horizontal {{ height: 9px; background: {surface}; margin: 0; }}
QScrollBar::handle {{ background: {border}; border-radius: 4px; min-height: 24px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QCheckBox {{ spacing: 6px; background: transparent; }}
QCheckBox::indicator {{ width: 15px; height: 15px; }}
QCheckBox::indicator:checked {{ background: {accent}; border: 1px solid {accent}; border-radius: 3px; }}
QProgressBar {{ background: {surface}; border: none; border-radius: 4px; text-align: center; max-height: 16px; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}
QStatusBar {{ background: {bg}; color: {muted}; border-top: 1px solid {border}; padding: 4px; }}
QStatusBar::item {{ border: none; }}
QToolTip {{ background: {surface}; color: {text}; border: 1px solid {border}; padding: 6px; }}
"""


def apply_theme(colors: ThemeColors) -> None:
    app = QApplication.instance()
    if app is None:
        return
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, colors.background),
        (QPalette.ColorRole.WindowText, ink(colors.background)),
        (QPalette.ColorRole.Base, colors.surface),
        (QPalette.ColorRole.AlternateBase, colors.background),
        (QPalette.ColorRole.Text, ink(colors.surface)),
        (QPalette.ColorRole.Button, colors.surface),
        (QPalette.ColorRole.ButtonText, ink(colors.surface)),
        (QPalette.ColorRole.Highlight, colors.accent),
        (QPalette.ColorRole.HighlightedText, ink(colors.accent)),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(colors))
