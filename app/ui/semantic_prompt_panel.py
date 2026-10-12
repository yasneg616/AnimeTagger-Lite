"""Semantic scene controls; source acquisition is deliberately absent from UI."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QPushButton, QScrollArea, QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

from app.errors import AnimeTaggerError
from app.inference.backends import BACKENDS
from app.prompts.semantic_prompt import SemanticPromptGenerator, SemanticPromptRequest
from app.prompts.semantic_rules import THEMES
from app.ui.tag_visual_widgets import TagListView


class SemanticPromptPanel(QWidget):
    def __init__(self, settings, root: Path, visual_provider, parent=None, *, generator=None):
        super().__init__(parent)
        self.root = Path(root)
        self._generator = generator
        self._last_result = None
        self._import_text = ""
        self._assignments = {}
        self._build_ui(visual_provider)
        self.set_settings(settings)

    def generator(self):
        if self._generator is None:
            self._generator = SemanticPromptGenerator(self.root)
        return self._generator

    def _combo(self, choices):
        result = QComboBox()
        for label, value in choices:
            result.addItem(label, value)
        return result

    def _build_ui(self, provider):
        self.backend_combo = self._combo([("全部本地标签库", ""), *((spec.label, backend) for backend, spec in BACKENDS.items())])
        self.backend_combo.setObjectName("semanticBackendCombo")
        self.seed_edit = QLineEdit()
        self.seed_edit.setPlaceholderText("留空则自动随机")
        self.actor_count = QSpinBox()
        self.actor_count.setRange(1, 4)
        self.actor_count.setValue(1)
        self.actor_count.setObjectName("semanticActorCount")
        self.character_mode = self._combo([("原创人物", "original"), ("已有角色", "known")])
        self.theme_combo = self._combo([("自动主题", "auto"), *((label, theme) for theme, label in THEMES.items())])
        self.location_combo = self._combo([("自动场景", "auto")])
        self.action_combo = self._combo([("自动动作", "auto")])
        self.content_combo = self._combo([("普通内容", "ordinary"), ("成人内容", "adult")])
        self.freedom_combo = self._combo([("自然", "natural"), ("均衡", "balanced"), ("大胆", "bold")])
        self.density_combo = self._combo([("简洁", "concise"), ("标准", "standard"), ("丰富", "rich")])
        self.density_combo.setCurrentIndex(1)
        self.prefer_popular = QCheckBox("偏向高频标签")
        self.prefer_popular.setChecked(True)
        self.underscore_check = QCheckBox("下划线转空格")
        grid = QGridLayout()
        fields = (("标签库", self.backend_combo), ("种子", self.seed_edit), ("主体数量", self.actor_count), ("主体方式", self.character_mode),
                  ("主题", self.theme_combo), ("场景", self.location_combo), ("动作／互动", self.action_combo), ("内容等级", self.content_combo),
                  ("自由度", self.freedom_combo), ("细节密度", self.density_combo))
        for index, (label, widget) in enumerate(fields):
            row, col = divmod(index, 2)
            grid.addWidget(QLabel(label), row, col * 2)
            grid.addWidget(widget, row, col * 2 + 1)
        grid.addWidget(self.prefer_popular, 5, 0, 1, 2)
        grid.addWidget(self.underscore_check, 5, 2, 1, 2)
        self.character_combos, self.actor_tags, self.actor_locks, self.actor_rows = [], [], [], []
        actor_box = QGroupBox("主体属性：填写 tags 可固定属性，锁定可保留上次主体")
        actor_grid = QGridLayout(actor_box)
        for index in range(4):
            label = QLabel(f"A{index+1}")
            combo = self._combo([("随机已有角色", "")])
            combo.setEditable(True)
            combo.setMinimumWidth(160)
            tags = QLineEdit()
            tags.setPlaceholderText("固定属性，例如 blue_hair, long_hair")
            lock = QCheckBox("锁定")
            self.character_combos.append(combo)
            self.actor_tags.append(tags)
            self.actor_locks.append(lock)
            self.actor_rows.append((label, combo, tags, lock))
            for col, widget in enumerate((label, combo, tags, lock)):
                actor_grid.addWidget(widget, index, col)
        self.scene_lock = QCheckBox("锁定上次场景、时间、构图和光照")
        self.coverage_label = QLabel("本地语义词库按需加载。")
        self.coverage_label.setWordWrap(True)
        controls = QWidget()
        control_layout = QVBoxLayout(controls)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.addLayout(grid)
        control_layout.addWidget(actor_box)
        control_layout.addWidget(self.scene_lock)
        control_layout.addWidget(self.coverage_label)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(controls)
        scroll.setMinimumHeight(200)
        scroll.setMaximumHeight(360)
        self.generate_button = QPushButton("生成语义 Prompt")
        self.generate_button.setObjectName("semanticGenerateButton")
        self.copy_button = QPushButton("复制当前格式")
        self.generate_button.clicked.connect(self.generate)
        self.copy_button.clicked.connect(self.copy_prompt)
        buttons = QHBoxLayout()
        buttons.addWidget(self.generate_button)
        buttons.addWidget(self.copy_button)
        buttons.addStretch(1)
        self.status_label = QLabel("主体属性、动作条件和角色身份会在生成过程中校验。")
        self.status_label.setWordWrap(True)
        self.results_tabs = QTabWidget()
        self.tags_edit = QPlainTextEdit()
        self.tags_edit.setObjectName("semanticTagsEdit")
        self.english_edit = QPlainTextEdit()
        self.english_edit.setObjectName("semanticEnglishEdit")
        self.summary_edit = QPlainTextEdit()
        self.summary_edit.setReadOnly(True)
        self.diagnostics_edit = QPlainTextEdit()
        self.diagnostics_edit.setReadOnly(True)
        for title, widget in (("Tags", self.tags_edit), ("English", self.english_edit), ("画面与主体", self.summary_edit), ("待处理问题", self.diagnostics_edit)):
            self.results_tabs.addTab(widget, title)
        self.tag_list = TagListView(provider)
        self.tag_list.setMinimumHeight(90)
        self.tag_list.setMaximumHeight(180)
        import_box = QGroupBox("导入外部 Tags → 英文描述")
        import_layout = QHBoxLayout(import_box)
        self.import_edit = QPlainTextEdit()
        self.import_edit.setMaximumHeight(65)
        self.import_edit.setPlaceholderText("粘贴 tags；权重、未知词和原文会保留。")
        import_layout.addWidget(self.import_edit, 1)
        import_actions = QVBoxLayout()
        self.import_adult = QCheckBox("原创主体已确定成年")
        self.import_adult.setToolTip("只用于原创主体；已有角色沿用档案年龄状态。")
        self.import_button = QPushButton("导入／转换")
        self.assign_button = QPushButton("分配多人属性")
        self.assign_button.setEnabled(False)
        self.import_button.clicked.connect(self.import_tags)
        self.assign_button.clicked.connect(self.assign_tags)
        import_actions.addWidget(self.import_adult)
        self.import_count = QSpinBox()
        self.import_count.setRange(0, 4)
        self.import_count.setSpecialValueText("自动识别导入人数")
        self.import_count.setPrefix("导入人数 ")
        import_actions.addWidget(self.import_count)
        import_actions.addWidget(self.import_button)
        import_actions.addWidget(self.assign_button)
        import_layout.addLayout(import_actions)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)
        layout.addLayout(buttons)
        layout.addWidget(self.status_label)
        layout.addWidget(self.results_tabs, 2)
        layout.addWidget(self.tag_list, 1)
        layout.addWidget(import_box)
        self.actor_count.valueChanged.connect(self._sync_actor_controls)
        self.character_mode.currentIndexChanged.connect(self._sync_actor_controls)
        self.backend_combo.currentIndexChanged.connect(self.refresh_choices)
        self.content_combo.currentIndexChanged.connect(self.refresh_choices)
        self._sync_actor_controls()

    def _sync_actor_controls(self):
        for index, widgets in enumerate(self.actor_rows):
            for widget in widgets:
                widget.setVisible(index < self.actor_count.value())
            self.character_combos[index].setEnabled(self.character_mode.currentData() == "known")

    def set_settings(self, settings):
        index = self.backend_combo.findData(settings.backend)
        self.backend_combo.setCurrentIndex(max(0, index))

    def backends(self):
        value = self.backend_combo.currentData()
        return (value,) if value else tuple(BACKENDS)

    def refresh_choices(self, *_):
        try:
            generator = self.generator()
            vocabulary = generator.vocabulary(self.backends())
            slots = generator.slots(vocabulary)
            for combo, terms in ((self.location_combo, slots.get("location", ())), (self.action_combo, [*slots.get("action", ()), *slots.get("posture", ()), *slots.get("interaction", ())])):
                previous = combo.currentData()
                combo.blockSignals(True)
                while combo.count() > 1:
                    combo.removeItem(1)
                for term in terms:
                    combo.addItem(term.name, term.name)
                combo.setCurrentIndex(max(0, combo.findData(previous)))
                combo.blockSignals(False)
            characters = [name for name, profile in generator.catalog.characters.items()
                          if "character:" + generator.catalog.canonical(name) in vocabulary
                          and all(generator.catalog.term(tag) and generator.catalog.term(tag).generatable
                                  and generator.catalog.term(tag).slot == slot and "general:" + generator.catalog.canonical(tag) in vocabulary for slot, tag in profile.identity)
                          and (self.content_combo.currentData() != "adult" or profile.age_state == "adult")]
            for combo in self.character_combos:
                previous = combo.currentText() if combo.currentIndex() else ""
                combo.blockSignals(True)
                while combo.count() > 1:
                    combo.removeItem(1)
                for name in sorted(characters):
                    combo.addItem(name, name)
                if previous:
                    combo.setEditText(previous)
                combo.blockSignals(False)
            coverage = generator.catalog.coverage
            self.coverage_label.setText(f"已核对生成资料 {coverage['usable_reviewed']:,}/{coverage['total']:,} · 来源已获取 {coverage['source_available']:,} · 当前可选角色 {len(characters)}\n"
                                       + ("覆盖门槛已达到。" if coverage['minimum_met'] else f"覆盖门槛尚未达到 {coverage['minimum_required']:,} 条；候选资料继续保留待核对。"))
        except (AnimeTaggerError, OSError, ValueError) as exc:
            self.coverage_label.setText(str(exc))

    def _request(self):
        seed_text = self.seed_edit.text().strip()
        try:
            seed = int(seed_text) if seed_text else None
        except ValueError as exc:
            raise AnimeTaggerError("种子必须是整数，或留空。") from exc
        from app.prompts.injection import parse_injections
        count = self.actor_count.value()
        previous = self._last_result.scene if self._last_result else None
        characters = tuple(combo.currentData() or (combo.currentText().strip() if combo.currentIndex() != 0 else None) for combo in self.character_combos[:count])
        return SemanticPromptRequest(backends=self.backends(), actor_count=count, character_mode=self.character_mode.currentData(),
            characters=characters if self.character_mode.currentData() == "known" else (), theme=self.theme_combo.currentData(),
            location=self.location_combo.currentData(), action=self.action_combo.currentData(), content=self.content_combo.currentData(),
            freedom=self.freedom_combo.currentData(), density=self.density_combo.currentData(), seed=seed,
            prefer_popular=self.prefer_popular.isChecked(), underscore_to_space=self.underscore_check.isChecked(),
            actor_tags=tuple(parse_injections(edit.text()) for edit in self.actor_tags[:count]), previous_scene=previous,
            locked_actors=tuple(f"A{index+1}" for index, lock in enumerate(self.actor_locks[:count]) if lock.isChecked()),
            locked_scene_slots=tuple(self.generator().catalog.terms[fact.term_key].slot for fact in previous.facts) if previous and self.scene_lock.isChecked() else ())

    def _error(self, exc):
        self.status_label.setText(str(exc))
        self.status_label.setStyleSheet("color: #e27b77;")

    def show_result(self, result):
        self._last_result = result
        self.tags_edit.setPlainText(result.tag_prompt)
        self.english_edit.setPlainText(result.english_prompt)
        self.summary_edit.setPlainText(result.summary)
        issues = (*result.blocking, *result.diagnostics)
        self.diagnostics_edit.setPlainText("\n".join(issues) or "已通过已知语义规则校验。")
        self.tag_list.set_tags(result.tags)
        self.assign_button.setEnabled(bool(result.unassigned))
        self.status_label.setText(f"种子 {result.seed} · 词库 {result.corpus_version} · 候选扩展 {result.expansions}"
                                  + (f" · 待分配 {len(result.unassigned)} 项" if result.unassigned else "")
                                  + (f" · 冲突 {len(result.blocking)} 项" if result.blocking else ""))
        self.status_label.setStyleSheet("color: #e27b77;" if result.blocking else "")
        if result.blocking or result.unassigned:
            self.results_tabs.setCurrentIndex(3)

    def generate(self):
        try:
            result = self.generator().generate(self._request())
        except (AnimeTaggerError, ValueError, OSError) as exc:
            self._error(exc)
            return
        self._import_text = ""
        self.show_result(result)

    def import_tags(self):
        text = self.import_edit.toPlainText()
        if text != self._import_text:
            self._assignments = {}
        try:
            result = self.generator().import_tags(text, backends=self.backends(), assignments=self._assignments,
                actor_count=self.import_count.value() or None,
                adult_actors=tuple(f"A{index+1}" for index in range(4)) if self.import_adult.isChecked() else ())
        except (AnimeTaggerError, ValueError, OSError) as exc:
            self._error(exc)
            return
        self._import_text = text
        self.show_result(result)

    def assign_tags(self):
        if not self._last_result or not self._last_result.unassigned:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("为属性指定主体")
        layout = QVBoxLayout(dialog)
        body = QWidget()
        form = QFormLayout(body)
        selections = {}
        for item in self._last_result.unassigned:
            if item.kind == "relation":
                term = self.generator().catalog.terms.get(item.term_key)
                if term and term.role_phrase:
                    from itertools import permutations
                    choices = [("尚未分配", "")]
                    for actors in permutations(self._last_result.scene.actors, term.min_actors):
                        if term.role_genders and any(gender != "any" and actor.gender != gender for actor, gender in zip(actors, term.role_genders)):
                            continue
                        ids = tuple(actor.actor_id for actor in actors)
                        choices.append((term.role_phrase.format(*ids), ids))
                    combo = self._combo(choices)
                    form.addRow(item.raw + "（互动方向）", combo)
                    selections[item.index] = combo
                    continue
                row = QWidget()
                line = QHBoxLayout(row)
                choices = []
                for actor in self._last_result.scene.actors:
                    check = QCheckBox(actor.actor_id)
                    line.addWidget(check)
                    choices.append(check)
                selections[item.index] = choices
                form.addRow(item.raw + "（互动参与者）", row)
            else:
                combo = self._combo([("尚未分配", ""), *((actor.actor_id, actor.actor_id) for actor in self._last_result.scene.actors)])
                form.addRow(item.raw + ("（持有者）" if item.kind == "object" else ""), combo)
                selections[item.index] = combo
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        layout.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.resize(500, 400)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            for index, choice in selections.items():
                value = tuple(check.text() for check in choice if check.isChecked()) if isinstance(choice, list) else choice.currentData()
                if value:
                    self._assignments[index] = value
            self.import_tags()

    def copy_prompt(self):
        editor = self.english_edit if self.results_tabs.currentIndex() == 1 else self.tags_edit
        text = editor.toPlainText().strip()
        if text:
            QApplication.clipboard().setText(text)
            self.status_label.setText("已复制当前格式。")
        else:
            self.status_label.setText("当前格式尚无可复制文本；请先处理冲突或未分配属性。")
