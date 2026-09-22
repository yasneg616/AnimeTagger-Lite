"""Theme editor with live preview, explicit save, and cancel rollback."""
from dataclasses import replace

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QPushButton, QVBoxLayout,
)

from app.ui.theme import PRESETS, ThemeColors, apply_theme, ink


class PaletteDialog(QDialog):
    def __init__(self, colors: ThemeColors, parent=None):
        super().__init__(parent)
        self.setWindowTitle("调色盘 · 界面配色")
        self.setMinimumWidth(420)
        self.original = colors
        self.colors = colors
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        label = QLabel("让工作台拥有你的颜色")
        label.setProperty("heading", True)
        layout.addWidget(label)
        layout.addWidget(QLabel("实时预览配色，保存后下次启动自动恢复。"))
        form = QFormLayout()
        self.presets = QComboBox()
        self.presets.addItem("自定义")
        self.presets.addItems(PRESETS)
        self.presets.currentTextChanged.connect(self._preset)
        form.addRow("预设主题", self.presets)
        self.swatches = {}
        for key, title in (("accent", "强调色"), ("background", "背景色"), ("surface", "面板色")):
            button = QPushButton()
            button.setObjectName(f"palette_{key}")
            button.clicked.connect(lambda checked=False, k=key: self._choose(k))
            self.swatches[key] = button
            form.addRow(title, button)
        layout.addLayout(form)
        reset = QPushButton("恢复默认配色")
        reset.clicked.connect(lambda: self.set_colors(ThemeColors()))
        layout.addWidget(reset)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存配色")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._refresh()

    def _refresh(self):
        for key, button in self.swatches.items():
            color = getattr(self.colors, key)
            button.setText(color.upper() + "  ·  选择颜色")
            button.setStyleSheet(f"background: {color}; color: {ink(color)}; border: 1px solid #808898;")
        name = next((name for name, colors in PRESETS.items() if colors == self.colors), "自定义")
        self.presets.blockSignals(True)
        self.presets.setCurrentText(name)
        self.presets.blockSignals(False)

    def set_colors(self, colors):
        self.colors = colors
        apply_theme(colors)
        self._refresh()

    def _preset(self, name):
        if name in PRESETS:
            self.set_colors(PRESETS[name])

    def _choose(self, key):
        color = QColorDialog.getColor(QColor(getattr(self.colors, key)), self, "选择颜色")
        if color.isValid():
            self.set_colors(replace(self.colors, **{key: color.name()}))

    def done(self, result):
        if result != QDialog.DialogCode.Accepted:
            apply_theme(self.original)
        super().done(result)
