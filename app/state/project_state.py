"""Ordered, duplicate-safe state for manually added images."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Iterable

from app.image.image_loader import SUPPORTED_IMAGE_EXTENSIONS
from app.state.image_item import ImageItem


def normalized_path_key(path: Path) -> str:
    """Create a Windows-safe path identity without requiring the file to exist."""

    resolved = Path(path).expanduser().resolve(strict=False)
    return os.path.normcase(os.path.normpath(str(resolved)))


@dataclass(frozen=True, slots=True)
class AddPathsResult:
    added: tuple[ImageItem, ...]
    duplicates: tuple[Path, ...] = ()
    unsupported: tuple[Path, ...] = ()
    directories: tuple[Path, ...] = ()
    missing: tuple[Path, ...] = ()


class ProjectState:
    def __init__(self) -> None:
        self._items: list[ImageItem] = []
        self._by_id: dict[str, ImageItem] = {}
        self._path_keys: dict[str, str] = {}
        self.current_id: str | None = None

    @property
    def items(self) -> tuple[ImageItem, ...]:
        return tuple(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def get(self, image_id: str | None) -> ImageItem | None:
        if image_id is None:
            return None
        return self._by_id.get(image_id)

    def add_paths(
        self,
        paths: Iterable[Path],
        *,
        temporary_paths: Iterable[Path] = (),
    ) -> AddPathsResult:
        temporary_keys = {
            normalized_path_key(Path(path)) for path in temporary_paths
        }
        added: list[ImageItem] = []
        duplicates: list[Path] = []
        unsupported: list[Path] = []
        directories: list[Path] = []
        missing: list[Path] = []

        for supplied in paths:
            path = Path(supplied)
            if path.is_dir():
                directories.append(path)
                continue
            if not path.exists() or not path.is_file():
                missing.append(path)
                continue
            if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                unsupported.append(path)
                continue
            key = normalized_path_key(path)
            if key in self._path_keys:
                duplicates.append(path)
                continue
            item = ImageItem(
                source_path=path.resolve(strict=False),
                is_temporary=key in temporary_keys,
            )
            self._items.append(item)
            self._by_id[item.id] = item
            self._path_keys[key] = item.id
            added.append(item)

        if self.current_id is None and added:
            self.current_id = added[0].id
        return AddPathsResult(
            added=tuple(added),
            duplicates=tuple(duplicates),
            unsupported=tuple(unsupported),
            directories=tuple(directories),
            missing=tuple(missing),
        )

    def remove(self, image_ids: Iterable[str]) -> tuple[ImageItem, ...]:
        wanted = set(image_ids)
        removed = tuple(item for item in self._items if item.id in wanted)
        if not removed:
            return ()
        self._items = [item for item in self._items if item.id not in wanted]
        for item in removed:
            self._by_id.pop(item.id, None)
            self._path_keys.pop(normalized_path_key(item.source_path), None)
        if self.current_id in wanted:
            self.current_id = self._items[0].id if self._items else None
        return removed

    def clear(self) -> tuple[ImageItem, ...]:
        removed = tuple(self._items)
        self._items.clear()
        self._by_id.clear()
        self._path_keys.clear()
        self.current_id = None
        return removed

