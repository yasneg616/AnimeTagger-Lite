"""Search, category, group, confidence filtering and stable tag sorting."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel

from app.prompts.models import TagSource
from app.ui.tag_table_model import TagColumn, TagRole, TagTableModel


class TagFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent: object | None = None) -> None:
        super().__init__(parent)
        self._search = ""
        self._category = ""
        self._group = ""
        self._show_low_confidence = False
        self._minimum_confidence = 0.10
        self.setDynamicSortFilter(True)

    def _invalidate_rows(self) -> None:
        """Refresh row filtering across the supported PySide6 range."""

        begin_change = getattr(self, "beginFilterChange", None)
        end_change = getattr(self, "endFilterChange", None)
        direction = getattr(QSortFilterProxyModel, "Direction", None)
        if (
            callable(begin_change)
            and callable(end_change)
            and direction is not None
        ):
            begin_change()
            end_change(direction.Rows)
        else:
            # PySide6 6.7/6.8 do not expose the replacement API.
            self.invalidateFilter()

    def set_search_text(self, text: str) -> None:
        value = text.strip().casefold()
        if value != self._search:
            self._search = value
            self._invalidate_rows()

    def set_category_filter(self, category: str) -> None:
        value = "" if category in {"", "all"} else category
        if value != self._category:
            self._category = value
            self._invalidate_rows()

    def set_group_filter(self, group: str) -> None:
        value = "" if group in {"", "all"} else group
        if value != self._group:
            self._group = value
            self._invalidate_rows()

    def set_show_low_confidence(self, show: bool) -> None:
        if show != self._show_low_confidence:
            self._show_low_confidence = show
            self._invalidate_rows()

    def set_minimum_confidence(self, value: float) -> None:
        if value != self._minimum_confidence:
            self._minimum_confidence = value
            self._invalidate_rows()

    @property
    def show_low_confidence(self) -> bool:
        return self._show_low_confidence

    def filterAcceptsRow(
        self,
        source_row: int,
        source_parent: QModelIndex,
    ) -> bool:
        model = self.sourceModel()
        if model is None:
            return False
        if isinstance(model, TagTableModel):
            result = model.tag_at(source_row)
            if result is None:
                return False
            tag = result.output_name
            category = result.category.value
            group = result.prompt_group.value if result.prompt_group else "other"
            confidence = result.confidence
            source = result.source.value
        else:
            tag_index = model.index(source_row, TagColumn.TAG, source_parent)
            category_index = model.index(
                source_row, TagColumn.CATEGORY, source_parent
            )
            group_index = model.index(source_row, TagColumn.GROUP, source_parent)
            confidence_index = model.index(
                source_row, TagColumn.CONFIDENCE, source_parent
            )
            source_index = model.index(source_row, TagColumn.SOURCE, source_parent)
            tag = str(model.data(tag_index, TagRole.TAG) or "")
            category = str(model.data(category_index, TagRole.CATEGORY) or "")
            group = str(model.data(group_index, TagRole.GROUP) or "")
            confidence = float(
                model.data(confidence_index, TagRole.CONFIDENCE) or 0.0
            )
            source = str(model.data(source_index, TagRole.SOURCE) or "")
        if self._search and self._search not in tag.casefold():
            visual = model.visual_at(source_row) if isinstance(model, TagTableModel) else None
            if visual is None or self._search not in visual.search_text:
                return False
        if self._category and category != self._category:
            return False
        if self._group and group != self._group:
            return False
        if (
            not self._show_low_confidence
            and source != TagSource.USER.value
            and confidence < self._minimum_confidence
        ):
            return False
        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        column = TagColumn(left.column())
        model = self.sourceModel()
        if model is None:
            return super().lessThan(left, right)
        if isinstance(model, TagTableModel):
            left_tag = model.tag_at(left.row())
            right_tag = model.tag_at(right.row())
            if left_tag is None or right_tag is None:
                return super().lessThan(left, right)
            if column is TagColumn.CONFIDENCE:
                return left_tag.confidence < right_tag.confidence
            if column is TagColumn.TAG:
                return (
                    left_tag.output_name.casefold()
                    < right_tag.output_name.casefold()
                )
        if column is TagColumn.CONFIDENCE:
            left_value = float(model.data(left, TagRole.CONFIDENCE) or 0.0)
            right_value = float(model.data(right, TagRole.CONFIDENCE) or 0.0)
            return left_value < right_value
        if column is TagColumn.TAG:
            left_value = str(model.data(left, TagRole.TAG) or "").casefold()
            right_value = str(model.data(right, TagRole.TAG) or "").casefold()
            return left_value < right_value
        return super().lessThan(left, right)
