"""Editable tag table model backed by typed :class:`TagResult` values."""

from __future__ import annotations

from dataclasses import replace
from enum import IntEnum
import re

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal

from app.inference.model_loader import TagCategory
from app.prompts.models import PromptGroup, TagResult, TagSource
from app.ui.tag_visual_widgets import TagVisualProvider, VISUAL_ROLE


class TagColumn(IntEnum):
    ENABLED = 0
    TAG = 1
    CATEGORY = 2
    GROUP = 3
    CONFIDENCE = 4
    SOURCE = 5


class TagRole(IntEnum):
    TAG = int(Qt.ItemDataRole.UserRole) + 1
    CATEGORY = int(Qt.ItemDataRole.UserRole) + 2
    GROUP = int(Qt.ItemDataRole.UserRole) + 3
    CONFIDENCE = int(Qt.ItemDataRole.UserRole) + 4
    SOURCE = int(Qt.ItemDataRole.UserRole) + 5
    VISUAL = VISUAL_ROLE


HEADERS = ("启用", "标签", "类别", "提示词分组", "置信度", "来源")
CATEGORY_LABELS = {
    TagCategory.RATING: "Rating",
    TagCategory.GENERAL: "General",
    TagCategory.CHARACTER: "Character",
    TagCategory.COPYRIGHT: "Copyright",
    TagCategory.OTHER: "Other",
}
SOURCE_LABELS = {
    TagSource.MODEL: "模型",
    TagSource.USER: "手动",
    TagSource.PRESET: "预设",
}


def sanitize_tag_name(value: str) -> str:
    # A table row represents exactly one prompt token. Commas therefore become
    # spaces instead of accidentally injecting additional prompt tokens.
    return re.sub(r"\s+", " ", value.replace(",", " ").replace("，", " ")).strip()


class TagTableModel(QAbstractTableModel):
    tags_changed = Signal()

    def __init__(
        self,
        tags: tuple[TagResult, ...] | list[TagResult] = (),
        parent: object | None = None,
        *,
        visual_provider: TagVisualProvider | None = None,
    ) -> None:
        super().__init__(parent)
        self._tags = list(tags)
        self.visual_provider = visual_provider if visual_provider is not None else TagVisualProvider(self)
        self.visual_provider.changed.connect(self._refresh_visuals)

    def _refresh_visuals(self) -> None:
        if self._tags:
            self.dataChanged.emit(self.index(0, TagColumn.TAG), self.index(len(self._tags)-1, TagColumn.TAG),
                                  [int(Qt.ItemDataRole.DecorationRole), int(TagRole.VISUAL)])

    def visual_at(self, row: int):
        tag = self.tag_at(row)
        return self.visual_provider.visual_for(tag.output_name, tag.category) if tag is not None else None

    @property
    def tags(self) -> tuple[TagResult, ...]:
        return tuple(self._tags)

    def tag_at(self, row: int) -> TagResult | None:
        if 0 <= row < len(self._tags):
            return self._tags[row]
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._tags)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(TagColumn)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if (
            orientation is Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(HEADERS)
        ):
            return HEADERS[section]
        return super().headerData(section, orientation, role)

    def data(
        self,
        index: QModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if not index.isValid() or not 0 <= index.row() < len(self._tags):
            return None
        tag = self._tags[index.row()]
        column = TagColumn(index.column())

        if role == Qt.ItemDataRole.DecorationRole and column is TagColumn.TAG:
            return self.visual_provider.icon_for(tag.output_name, tag.category)
        if role == TagRole.VISUAL and column is TagColumn.TAG:
            return self.visual_at(index.row())

        if role == Qt.ItemDataRole.CheckStateRole and column is TagColumn.ENABLED:
            return (
                Qt.CheckState.Checked
                if tag.enabled
                else Qt.CheckState.Unchecked
            )
        if role in {Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole}:
            if column is TagColumn.ENABLED:
                return ""
            if column is TagColumn.TAG:
                return tag.output_name
            if column is TagColumn.CATEGORY:
                return CATEGORY_LABELS.get(tag.category, tag.category.value)
            if column is TagColumn.GROUP:
                return tag.prompt_group.value if tag.prompt_group else "other"
            if column is TagColumn.CONFIDENCE:
                if tag.source is TagSource.USER:
                    return "手动"
                return f"{tag.confidence:.4f}"
            if column is TagColumn.SOURCE:
                return SOURCE_LABELS.get(tag.source, tag.source.value)
        if role == TagRole.TAG:
            return tag.output_name
        if role == TagRole.CATEGORY:
            return tag.category.value
        if role == TagRole.GROUP:
            return tag.prompt_group.value if tag.prompt_group else "other"
        if role == TagRole.CONFIDENCE:
            return tag.confidence
        if role == TagRole.SOURCE:
            return tag.source.value
        if role == Qt.ItemDataRole.ToolTipRole:
            if tag.source is TagSource.USER:
                return "手动标签按 1.0 参与阈值计算，界面显示为“手动”。"
            return f"原始置信度：{tag.confidence:.8f}"
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if column in {
                TagColumn.ENABLED,
                TagColumn.CONFIDENCE,
                TagColumn.SOURCE,
            }:
                return int(Qt.AlignmentFlag.AlignCenter)
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.ItemIsEnabled
        flags = (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )
        column = TagColumn(index.column())
        if column is TagColumn.ENABLED:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        elif column is TagColumn.TAG:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(self, index: QModelIndex, value: object, role: int) -> bool:
        if not index.isValid() or not 0 <= index.row() < len(self._tags):
            return False
        row = index.row()
        tag = self._tags[row]
        column = TagColumn(index.column())

        if column is TagColumn.ENABLED and role == Qt.ItemDataRole.CheckStateRole:
            enabled = value == Qt.CheckState.Checked or value == 2
            if enabled == tag.enabled:
                return False
            self._tags[row] = replace(tag, enabled=enabled)
        elif column is TagColumn.TAG and role == Qt.ItemDataRole.EditRole:
            name = sanitize_tag_name(str(value))
            if not name or name == tag.output_name:
                return False
            self._tags[row] = replace(
                tag,
                name=name,
                # Once the model label identity is changed by the user, its
                # original WD14 category must not force future classification
                # (for example, a renamed character tag staying "character").
                category=TagCategory.GENERAL,
                normalized_name=None,
                prompt_group=None,
                source=TagSource.USER,
            )
        else:
            return False

        self.dataChanged.emit(
            self.index(row, 0),
            self.index(row, self.columnCount() - 1),
        )
        self.tags_changed.emit()
        return True

    def set_tags(
        self,
        tags: tuple[TagResult, ...] | list[TagResult],
        *,
        notify: bool = False,
    ) -> None:
        values = list(tags)
        if len(values) == len(self._tags) and all(
            current is replacement
            for current, replacement in zip(self._tags, values)
        ):
            return
        self.beginResetModel()
        self._tags = values
        self.endResetModel()
        if notify:
            self.tags_changed.emit()

    def add_manual_tag(self, name: str) -> bool:
        cleaned = sanitize_tag_name(name)
        if not cleaned:
            return False
        row = len(self._tags)
        self.beginInsertRows(QModelIndex(), row, row)
        self._tags.append(
            TagResult(
                name=cleaned,
                confidence=1.0,
                category=TagCategory.GENERAL,
                enabled=True,
                source=TagSource.USER,
            )
        )
        self.endInsertRows()
        self.tags_changed.emit()
        return True

    def remove_source_rows(self, rows: list[int] | tuple[int, ...]) -> int:
        valid_rows = sorted(
            {row for row in rows if 0 <= row < len(self._tags)},
            reverse=True,
        )
        for row in valid_rows:
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._tags[row]
            self.endRemoveRows()
        if valid_rows:
            self.tags_changed.emit()
        return len(valid_rows)
