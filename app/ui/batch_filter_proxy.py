"""Search and status filters for the batch preview table."""

from __future__ import annotations

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel

from app.batch.models import CaptionPolicy
from app.ui.batch_table_model import BatchTableModel


class BatchFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._search = ""
        self._status = ""
        self._existing_only = False
        self._skip_only = False
        self._policy = CaptionPolicy.SKIP

    def set_search(self, text: str) -> None:
        self._search = text.strip().casefold()
        self._invalidate_rows()

    def set_status(self, status: str) -> None:
        self._status = status
        self._invalidate_rows()

    def set_existing_only(self, enabled: bool) -> None:
        self._existing_only = enabled
        self._invalidate_rows()

    def set_skip_only(self, enabled: bool) -> None:
        self._skip_only = enabled
        self._invalidate_rows()

    def set_caption_policy(self, policy: CaptionPolicy) -> None:
        self._policy = policy
        self._invalidate_rows()

    def _invalidate_rows(self) -> None:
        self.beginFilterChange()
        self.endFilterChange(QSortFilterProxyModel.Direction.Rows)

    def filterAcceptsRow(
        self,
        source_row: int,
        source_parent: QModelIndex,
    ) -> bool:
        source = self.sourceModel()
        if not isinstance(source, BatchTableModel):
            return True
        item = source.item_at(source_row)
        if item is None:
            return False
        if self._search:
            haystack = (
                f"{item.source_path} {item.relative_path.as_posix()} "
                f"{item.image_format}"
            ).casefold()
            if self._search not in haystack:
                return False
        if self._status and item.status.value != self._status:
            return False
        existing = item.caption_path is not None and item.caption_path.exists()
        if self._existing_only and not existing:
            return False
        if self._skip_only and not (
            existing and self._policy is CaptionPolicy.SKIP
        ):
            return False
        return True
