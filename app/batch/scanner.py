"""Bounded, cancellable folder discovery without image decoding."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from threading import Event
from typing import Callable, Protocol

from app.batch.models import BatchItem, ScanOptions, ScanResult
from app.errors import BatchScanError
from app.image.image_loader import SUPPORTED_IMAGE_EXTENSIONS


class CancellationToken(Protocol):
    def is_set(self) -> bool: ...


ScanProgress = Callable[[int, Path], None]


def normalized_path_key(path: Path) -> str:
    return os.path.normcase(str(Path(path).resolve(strict=False)))


def path_is_within(path: Path, directory: Path) -> bool:
    candidate = Path(path).resolve(strict=False)
    parent = Path(directory).resolve(strict=False)
    try:
        return os.path.commonpath((str(candidate), str(parent))) == str(parent)
    except ValueError:
        return False


def _is_hidden(path: Path, name: str) -> bool:
    if name.startswith("."):
        return True
    try:
        attributes = path.stat(follow_symlinks=False).st_file_attributes
    except (AttributeError, OSError):
        return False
    return bool(attributes & 0x2)


@dataclass(slots=True)
class _ScanCounters:
    duplicates: int = 0
    unsupported: int = 0
    hidden: int = 0
    symlinks: int = 0
    permissions: int = 0


class BatchScanner:
    """Discover supported images while enforcing explicit resource limits."""

    def scan(
        self,
        options: ScanOptions,
        *,
        cancel_event: CancellationToken | None = None,
        progress: ScanProgress | None = None,
    ) -> ScanResult:
        token = cancel_event or Event()
        roots = self._normalize_roots(options.roots)
        output_root = (
            options.output_root.resolve(strict=False)
            if options.output_root is not None
            else None
        )
        items: list[BatchItem] = []
        seen_files: set[object] = set()
        seen_directories: set[tuple[int, int] | str] = set()
        warnings: list[str] = []
        counters = _ScanCounters()
        truncated = False

        for root in roots:
            if token.is_set():
                break
            if not root.exists():
                warnings.append(f"输入路径不存在，已跳过：{root}")
                continue
            if root.is_file():
                if self._consider_file(
                    root,
                    root.parent,
                    root.name,
                    options,
                    output_root,
                    seen_files,
                    items,
                    counters,
                ) and progress is not None:
                    progress(len(items), root)
                if len(items) >= options.max_files:
                    truncated = True
                    break
                continue
            if not root.is_dir():
                warnings.append(f"输入路径不是普通文件或文件夹，已跳过：{root}")
                continue

            stack: list[tuple[Path, int]] = [(root, 0)]
            while stack and not token.is_set():
                directory, depth = stack.pop()
                if output_root is not None and path_is_within(directory, output_root):
                    continue
                if options.follow_symlinks:
                    identity = self._directory_identity(directory)
                    if identity in seen_directories:
                        continue
                    seen_directories.add(identity)
                try:
                    with os.scandir(directory) as iterator:
                        entries = sorted(
                            iterator,
                            key=lambda entry: entry.name.casefold(),
                        )
                except PermissionError:
                    counters.permissions += 1
                    warnings.append(f"无权限读取文件夹，已跳过：{directory}")
                    continue
                except OSError as exc:
                    warnings.append(f"无法读取文件夹，已跳过：{directory}（{exc}）")
                    continue

                child_directories: list[tuple[Path, int]] = []
                for entry in entries:
                    if token.is_set():
                        break
                    path = Path(entry.path)
                    if not options.include_hidden and _is_hidden(path, entry.name):
                        counters.hidden += 1
                        continue
                    try:
                        is_symlink = entry.is_symlink()
                    except OSError:
                        is_symlink = True
                    if is_symlink and not options.follow_symlinks:
                        counters.symlinks += 1
                        continue
                    try:
                        is_dir = entry.is_dir(
                            follow_symlinks=options.follow_symlinks
                        )
                        is_file = entry.is_file(
                            follow_symlinks=options.follow_symlinks
                        )
                    except OSError as exc:
                        warnings.append(f"无法检查路径，已跳过：{path}（{exc}）")
                        continue
                    if is_dir:
                        if options.recursive and depth < options.max_depth:
                            child_directories.append((path, depth + 1))
                        continue
                    if not is_file:
                        continue
                    try:
                        relative = path.relative_to(root)
                    except ValueError:
                        relative = Path(entry.name)
                    if self._consider_file(
                        path,
                        root,
                        relative,
                        options,
                        output_root,
                        seen_files,
                        items,
                        counters,
                    ) and progress is not None:
                        progress(len(items), path)
                    if len(items) >= options.max_files:
                        truncated = True
                        stack.clear()
                        break
                if not truncated:
                    stack.extend(reversed(child_directories))

        if not items and not warnings and not token.is_set():
            raise BatchScanError("所选输入路径中没有可扫描的普通文件。")
        return ScanResult(
            items=tuple(items),
            roots=roots,
            warnings=tuple(warnings),
            duplicate_count=counters.duplicates,
            unsupported_count=counters.unsupported,
            hidden_count=counters.hidden,
            symlink_count=counters.symlinks,
            permission_error_count=counters.permissions,
            truncated=truncated,
            cancelled=token.is_set(),
        )

    @staticmethod
    def _normalize_roots(roots: tuple[Path, ...]) -> tuple[Path, ...]:
        normalized: list[Path] = []
        seen: set[str] = set()
        for raw_root in roots:
            root = Path(raw_root).expanduser().resolve(strict=False)
            key = normalized_path_key(root)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(root)
        return tuple(normalized)

    @staticmethod
    def _directory_identity(path: Path) -> tuple[int, int] | str:
        try:
            stat = path.stat()
            if stat.st_ino:
                return (stat.st_dev, stat.st_ino)
        except OSError:
            pass
        return normalized_path_key(path)

    @staticmethod
    def _consider_file(
        path: Path,
        source_root: Path,
        relative: Path | str,
        options: ScanOptions,
        output_root: Path | None,
        seen_files: set[object],
        items: list[BatchItem],
        counters: _ScanCounters,
    ) -> bool:
        del options
        if output_root is not None and path_is_within(path, output_root):
            return False
        if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            counters.unsupported += 1
            return False
        key = normalized_path_key(path)
        try:
            stat = path.stat()
            physical_key: object = (
                "inode",
                stat.st_dev,
                stat.st_ino,
            ) if stat.st_ino else key
        except OSError:
            physical_key = key
        if key in seen_files or physical_key in seen_files:
            counters.duplicates += 1
            return False
        seen_files.add(key)
        seen_files.add(physical_key)
        try:
            file_size = path.stat().st_size
        except OSError:
            file_size = None
        items.append(
            BatchItem(
                source_path=path.resolve(strict=False),
                source_root=source_root.resolve(strict=False),
                relative_path=Path(relative),
                file_size=file_size,
                image_format=path.suffix.lower().lstrip("."),
            )
        )
        return True
