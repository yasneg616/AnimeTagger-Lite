"""A compact disclosure section that keeps its editor and signals intact."""
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget
from PySide6.QtCore import Qt


class CollapsibleSection(QWidget):
    def __init__(self, title, content, *, expanded=False, parent=None):
        super().__init__(parent)
        self.setProperty("card", True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.content = content
        self.toggle = QPushButton()
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self._title = title
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        layout.addWidget(self.toggle)
        layout.addWidget(content)
        self.toggle.toggled.connect(self._expand)
        self._expand(expanded)

    def _expand(self, expanded):
        self.toggle.setText(("−  " if expanded else "+  ") + self._title)
        self.content.setVisible(expanded)
