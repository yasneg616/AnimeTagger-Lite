"""Import clipboard images and local paths without retaining other content."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import tempfile
from uuid import uuid4

from PySide6.QtGui import QClipboard, QImage


@dataclass(frozen=True, slots=True)
class ClipboardImport:
    paths: tuple[Path, ...]
    temporary_paths: tuple[Path, ...] = ()


class ClipboardService:
    def __init__(self, *, temp_parent: Path | None = None) -> None:
        parent = str(temp_parent) if temp_parent is not None else None
        self._session_dir = Path(
            tempfile.mkdtemp(prefix="animetagger-lite-", dir=parent)
        )
        self._created_paths: set[Path] = set()
        self._closed = False

    @property
    def session_dir(self) -> Path:
        return self._session_dir

    @property
    def created_paths(self) -> tuple[Path, ...]:
        return tuple(sorted(self._created_paths))

    def import_from_clipboard(self, clipboard: QClipboard) -> ClipboardImport:
        if self._closed:
            raise RuntimeError("剪贴板临时目录已经清理。")
        mime = clipboard.mimeData()
        paths: list[Path] = []
        temporary: list[Path] = []

        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    paths.append(Path(url.toLocalFile()))

        if mime.hasText() and not paths:
            # Only treat complete local path lines as paths. Other clipboard
            # text is intentionally ignored and never logged.
            for line in mime.text().splitlines():
                candidate = line.strip().strip('"')
                if candidate:
                    path = Path(candidate)
                    if path.exists():
                        paths.append(path)

        if mime.hasImage() and not paths:
            image = clipboard.image()
            if not image.isNull():
                path = self._save_image(image)
                paths.append(path)
                temporary.append(path)

        # Preserve clipboard order while removing repeated local paths.
        unique: list[Path] = []
        seen: set[str] = set()
        for path in paths:
            key = str(path.resolve(strict=False)).casefold()
            if key not in seen:
                seen.add(key)
                unique.append(path)
        return ClipboardImport(tuple(unique), tuple(temporary))

    def _save_image(self, image: QImage) -> Path:
        target = self._session_dir / f"clipboard-{uuid4().hex}.png"
        if not image.save(str(target), "PNG"):
            raise OSError(f"无法保存剪贴板图片：{target}")
        self._created_paths.add(target)
        return target

    def cleanup(self) -> None:
        if self._closed:
            return
        self._closed = True
        # This directory was created by this instance with mkdtemp and is never
        # derived from clipboard or user input.
        shutil.rmtree(self._session_dir, ignore_errors=True)
        self._created_paths.clear()

    def __enter__(self) -> "ClipboardService":
        return self

    def __exit__(self, *_args: object) -> None:
        self.cleanup()

