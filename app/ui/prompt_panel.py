"""Editable generated/final positive and negative prompt panels."""

from __future__ import annotations

from PySide6.QtCore import Signal
from app.ui.collapsible import CollapsibleSection
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class PromptPanel(QWidget):
    prompt_edited = Signal(str, str)
    regenerate_requested = Signal(str)
    copy_requested = Signal(str)
    injection_requested = Signal(str, bool)
    undo_injection_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._programmatic = False
        self._tag_count = 0
        self._editors: dict[str, QPlainTextEdit] = {}
        self._counts: dict[str, QLabel] = {}
        self._notices: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._build_section("positive", "正向提示词"))
        self.negative_section = CollapsibleSection("反向提示词", self._build_section("negative", "编辑反向提示词"))
        layout.addWidget(self.negative_section)

    def _build_section(self, kind: str, title: str) -> QGroupBox:
        group = QGroupBox(title)
        editor = QPlainTextEdit()
        editor.setObjectName(f"{kind}PromptEdit")
        editor.setPlaceholderText(f"尚无{title}")
        editor.setMinimumHeight(86)
        count = QLabel("0 字符 · 0 标签")
        notice = QLabel("")
        notice.setObjectName(f"{kind}PromptNotice")
        notice.setProperty("muted", True)
        notice.hide()

        regenerate = QPushButton("重新生成")
        regenerate.setToolTip("使用当前标签和设置恢复自动生成文本")
        copy = QPushButton("复制")
        regenerate.clicked.connect(
            lambda _checked=False, value=kind: self.regenerate_requested.emit(value)
        )
        copy.clicked.connect(
            lambda _checked=False, value=kind: self.copy_requested.emit(value)
        )
        editor.textChanged.connect(
            lambda value=kind: self._on_text_changed(value)
        )

        actions = QHBoxLayout()
        actions.addWidget(count)
        actions.addStretch(1)
        actions.addWidget(regenerate)
        actions.addWidget(copy)

        layout = QVBoxLayout(group)
        layout.addWidget(editor)
        if kind == "positive":
            self.injection_edit = QLineEdit()
            self.injection_edit.setObjectName("positiveInjectionEdit")
            self.injection_edit.setPlaceholderText("输入任意标签，逗号分隔（无需模型支持）")
            self.inject_button = QPushButton("注入正向")
            self.inject_button.setObjectName("injectPositiveButton")
            self.inject_button.setToolTip("加入当前正向 Prompt；不重新运行模型")
            self.clean_appearance = QCheckBox("清理已识别的发型 / 发色 / 面部特征")
            self.clean_appearance.setChecked(True)
            self.clean_appearance.setToolTip("停用模型识别的发型、发色、瞳色、眉毛、睫毛等外观标签；保留表情、视线、服装、背景和手动标签。")
            self.undo_injection = QPushButton("撤销注入")
            self.undo_injection.setEnabled(False)
            self.undo_injection.clicked.connect(self.undo_injection_requested)
            self.inject_button.clicked.connect(self._request_injection)
            self.injection_edit.returnPressed.connect(self._request_injection)
            row = QHBoxLayout()
            row.addWidget(self.injection_edit, 1)
            row.addWidget(self.inject_button)
            layout.addLayout(row)
            options = QHBoxLayout()
            options.addWidget(self.clean_appearance, 1)
            options.addWidget(self.undo_injection)
            layout.addLayout(options)
        layout.addWidget(notice)
        layout.addLayout(actions)
        self._editors[kind] = editor
        self._counts[kind] = count
        self._notices[kind] = notice
        return group

    def _request_injection(self) -> None:
        self.injection_requested.emit(self.injection_edit.text(), self.clean_appearance.isChecked())

    def set_prompts(
        self,
        *,
        positive: str,
        negative: str,
        positive_edited: bool,
        negative_edited: bool,
        stale: bool,
        tag_count: int,
    ) -> None:
        self._programmatic = True
        self._tag_count = tag_count
        try:
            self._editors["positive"].setPlainText(positive)
            self._editors["negative"].setPlainText(negative)
        finally:
            self._programmatic = False
        self._set_notice("positive", positive_edited, stale)
        self._set_notice("negative", negative_edited, stale)
        self._update_count("positive")
        self._update_count("negative")

    def clear(self) -> None:
        self.set_prompts(
            positive="",
            negative="",
            positive_edited=False,
            negative_edited=False,
            stale=False,
            tag_count=0,
        )

    def text(self, kind: str) -> str:
        return self._editors[kind].toPlainText()

    def mark_stale(self) -> None:
        for kind in ("positive", "negative"):
            self._notices[kind].setText("标签或设置已变化，可重新生成。")
            self._notices[kind].show()

    def set_edit_notice(self, kind: str, *, edited: bool, stale: bool) -> None:
        self._set_notice(kind, edited, stale)

    def _set_notice(self, kind: str, edited: bool, stale: bool) -> None:
        if stale and edited:
            text = "保留了手动文本；标签或设置已变化，可重新生成。"
        elif edited:
            text = "当前为手动编辑文本。"
        else:
            text = ""
        self._notices[kind].setText(text)
        self._notices[kind].setVisible(bool(text))

    def _on_text_changed(self, kind: str) -> None:
        self._update_count(kind)
        if not self._programmatic:
            self.prompt_edited.emit(kind, self.text(kind))

    def _update_count(self, kind: str) -> None:
        text = self.text(kind)
        tag_count = (
            self._tag_count
            if kind == "positive"
            else len([part for part in text.split(",") if part.strip()])
        )
        self._counts[kind].setText(f"{len(text)} 字符 · {tag_count} 标签")
