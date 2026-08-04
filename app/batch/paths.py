"""Collision-safe output planning and path-containment checks."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePath
import re

from app.batch.models import BatchConfig, BatchItem, OutputMode
from app.errors import BatchConfigurationError
from app.image.image_loader import SUPPORTED_IMAGE_EXTENSIONS

_UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def ensure_safe_relative_path(relative: Path) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or candidate.drive:
        raise BatchConfigurationError(f"输出相对路径不能是绝对路径：{relative}")
    parts = PurePath(candidate).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise BatchConfigurationError(f"输出相对路径包含非法片段：{relative}")
    return candidate


def safe_join(directory: Path, relative: Path) -> Path:
    root = Path(directory).resolve(strict=False)
    clean = ensure_safe_relative_path(relative)
    target = (root / clean).resolve(strict=False)
    try:
        common = os.path.commonpath((str(root), str(target)))
    except ValueError as exc:
        raise BatchConfigurationError("输出路径与输出目录不在同一卷。") from exc
    if common != str(root):
        raise BatchConfigurationError(f"输出路径越过了输出目录：{relative}")
    return target


def safe_filename(value: str, fallback: str = "root") -> str:
    cleaned = _UNSAFE_FILENAME.sub("_", value).strip(" .")
    if not cleaned:
        return fallback
    if cleaned.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
        cleaned = f"_{cleaned}"
    return cleaned


def short_path_hash(path: Path, length: int = 8) -> str:
    normalized = str(Path(path).resolve(strict=False)).replace("\\", "/").casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:length]


class OutputPlanner:
    """Assign deterministic caption/JSON paths without touching the filesystem."""

    def plan(
        self,
        items: list[BatchItem] | tuple[BatchItem, ...],
        config: BatchConfig,
    ) -> None:
        roots = self._root_labels(items)
        flat_counts: dict[str, int] = {}
        if config.output_mode is OutputMode.FLAT:
            for item in items:
                key = item.relative_path.stem.casefold()
                flat_counts[key] = flat_counts.get(key, 0) + 1

        reserved: set[str] = set()
        for item in items:
            if item.source_path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
                raise BatchConfigurationError(
                    f"批处理条目不是支持的图片：{item.source_path}"
                )
            if config.output_mode is OutputMode.BESIDE:
                base = item.source_path.with_suffix("")
            elif config.output_mode is OutputMode.MIRROR:
                assert config.output_root is not None
                relative = ensure_safe_relative_path(item.relative_path)
                if len(roots) > 1:
                    relative = Path(roots[item.source_root]) / relative
                base = safe_join(config.output_root, relative).with_suffix("")
            else:
                assert config.output_root is not None
                stem = safe_filename(item.relative_path.stem, "image")
                if flat_counts.get(item.relative_path.stem.casefold(), 0) > 1:
                    stem = f"{stem}__{short_path_hash(item.source_path)}"
                base = safe_join(config.output_root, Path(stem))

            caption = base.with_suffix(".txt")
            json_path = base.with_suffix(".json")
            key = os.path.normcase(str(caption.resolve(strict=False)))
            if key in reserved:
                suffix = short_path_hash(item.source_path)
                caption = caption.with_name(f"{caption.stem}__{suffix}.txt")
                json_path = json_path.with_name(f"{json_path.stem}__{suffix}.json")
                key = os.path.normcase(str(caption.resolve(strict=False)))
            if key in reserved:
                raise BatchConfigurationError(
                    f"无法为输出生成唯一文件名：{item.source_path}"
                )
            reserved.add(key)
            if caption.resolve(strict=False) == item.source_path.resolve(strict=False):
                raise BatchConfigurationError("caption 输出不能覆盖原图。")
            if json_path.resolve(strict=False) == item.source_path.resolve(strict=False):
                raise BatchConfigurationError("JSON 输出不能覆盖原图。")
            item.caption_path = caption if config.write_captions else None
            item.json_path = json_path if config.write_json else None

    @staticmethod
    def _root_labels(
        items: list[BatchItem] | tuple[BatchItem, ...],
    ) -> dict[Path, str]:
        unique: list[Path] = []
        for item in items:
            root = item.source_root
            if root not in unique:
                unique.append(root)
        labels: dict[Path, str] = {}
        used: set[str] = set()
        for root in unique:
            base = safe_filename(root.name, "root")
            label = base
            if label.casefold() in used:
                label = f"{base}__{short_path_hash(root, 6)}"
            used.add(label.casefold())
            labels[root] = label
        return labels
