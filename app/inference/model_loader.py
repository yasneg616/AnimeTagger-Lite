"""Resolve the local WD14 model files and parse selected_tags.csv."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.errors import ModelDirectoryError, TagCsvError

MODEL_FILENAME = "model.onnx"
TAG_FILENAME = "selected_tags.csv"


class TagCategory(str, Enum):
    RATING = "rating"
    GENERAL = "general"
    CHARACTER = "character"
    COPYRIGHT = "copyright"
    OTHER = "other"


CATEGORY_BY_ID: dict[int, TagCategory] = {
    9: TagCategory.RATING,
    0: TagCategory.GENERAL,
    4: TagCategory.CHARACTER,
    3: TagCategory.COPYRIGHT,
}


@dataclass(frozen=True, slots=True)
class ModelFiles:
    directory: Path
    model_path: Path
    tags_path: Path


@dataclass(frozen=True, slots=True)
class TagMetadata:
    index: int
    tag_id: int
    name: str
    category_id: int
    category: TagCategory

    @property
    def category_label(self) -> str:
        if self.category is TagCategory.OTHER:
            return f"other({self.category_id})"
        return self.category.value


def resolve_model_files(model_dir: Path) -> ModelFiles:
    """Require the two inference files from the official model repository."""

    directory = Path(model_dir)
    if not directory.exists():
        raise ModelDirectoryError(
            "模型目录不存在，且缺少必要文件："
            f"{MODEL_FILENAME}, {TAG_FILENAME}；目录：{directory}"
        )
    if not directory.is_dir():
        raise ModelDirectoryError(f"模型路径不是目录：{directory}")

    model_path = directory / MODEL_FILENAME
    tags_path = directory / TAG_FILENAME
    missing: list[str] = []
    if not model_path.is_file():
        missing.append(MODEL_FILENAME)
    if not tags_path.is_file():
        missing.append(TAG_FILENAME)
    if missing:
        raise ModelDirectoryError(
            f"模型目录缺少必要文件：{', '.join(missing)}；目录：{directory}"
        )

    try:
        if model_path.stat().st_size == 0:
            raise ModelDirectoryError(f"{MODEL_FILENAME} 是空文件：{model_path}")
        if tags_path.stat().st_size == 0:
            raise ModelDirectoryError(f"{TAG_FILENAME} 是空文件：{tags_path}")
    except OSError as exc:
        raise ModelDirectoryError(f"无法读取模型目录中的文件：{directory}") from exc

    return ModelFiles(
        directory=directory,
        model_path=model_path,
        tags_path=tags_path,
    )


def load_selected_tags(csv_path: Path, *, allow_empty_names: bool = False) -> tuple[TagMetadata, ...]:
    """Parse model labels in exact CSV row order (the ONNX output order)."""

    path = Path(csv_path)
    if not path.is_file():
        raise TagCsvError(f"标签文件不存在：{path}")

    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise TagCsvError(f"标签 CSV 没有表头：{path}")

            normalized_fields = {
                field.strip(): field for field in reader.fieldnames if field is not None
            }
            missing_columns = [
                column for column in ("name", "category") if column not in normalized_fields
            ]
            if missing_columns:
                raise TagCsvError(
                    f"标签 CSV 缺少列：{', '.join(missing_columns)}；文件：{path}"
                )

            name_field = normalized_fields["name"]
            category_field = normalized_fields["category"]
            tag_id_field = normalized_fields.get("tag_id")
            tags: list[TagMetadata] = []

            for index, row in enumerate(reader):
                row_number = index + 2
                name = (row.get(name_field) or "").strip()
                if not name and not allow_empty_names:
                    raise TagCsvError(
                        f"标签 CSV 第 {row_number} 行的 name 为空：{path}"
                    )

                category_text = (row.get(category_field) or "").strip()
                try:
                    category_id = int(category_text)
                except ValueError as exc:
                    raise TagCsvError(
                        f"标签 CSV 第 {row_number} 行的 category "
                        f"不是整数：{category_text!r}"
                    ) from exc

                tag_id_text = (
                    (row.get(tag_id_field) or "").strip() if tag_id_field else ""
                )
                try:
                    tag_id = int(tag_id_text) if tag_id_text else index
                except ValueError as exc:
                    raise TagCsvError(
                        f"标签 CSV 第 {row_number} 行的 tag_id "
                        f"不是整数：{tag_id_text!r}"
                    ) from exc

                tags.append(
                    TagMetadata(
                        index=index,
                        tag_id=tag_id,
                        name=name,
                        category_id=category_id,
                        category=CATEGORY_BY_ID.get(category_id, TagCategory.OTHER),
                    )
                )
    except TagCsvError:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise TagCsvError(f"无法读取标签 CSV：{path}") from exc

    if not tags:
        raise TagCsvError(f"标签 CSV 没有数据行：{path}")
    return tuple(tags)
