from __future__ import annotations

from pathlib import Path

import pytest

from app.errors import ModelDirectoryError, TagCsvError
from app.inference.model_loader import (
    TagCategory,
    load_selected_tags,
    resolve_model_files,
)


def test_selected_tags_csv_preserves_order_and_categories(tmp_path: Path) -> None:
    csv_path = tmp_path / "selected_tags.csv"
    csv_path.write_text(
        "tag_id,name,category,count\n"
        "10,safe,9,100\n"
        "20,1girl,0,200\n"
        "30,some_character,4,300\n"
        "40,unknown_kind,7,10\n",
        encoding="utf-8",
    )

    tags = load_selected_tags(csv_path)

    assert [tag.name for tag in tags] == [
        "safe",
        "1girl",
        "some_character",
        "unknown_kind",
    ]
    assert [tag.category for tag in tags] == [
        TagCategory.RATING,
        TagCategory.GENERAL,
        TagCategory.CHARACTER,
        TagCategory.OTHER,
    ]
    assert tags[3].category_label == "other(7)"


def test_selected_tags_requires_expected_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "selected_tags.csv"
    csv_path.write_text("name\n1girl\n", encoding="utf-8")

    with pytest.raises(TagCsvError, match="缺少列：category"):
        load_selected_tags(csv_path)


def test_selected_tags_rejects_invalid_category(tmp_path: Path) -> None:
    csv_path = tmp_path / "selected_tags.csv"
    csv_path.write_text(
        "name,category\n1girl,not-a-number\n",
        encoding="utf-8",
    )

    with pytest.raises(TagCsvError, match="category 不是整数"):
        load_selected_tags(csv_path)


def test_model_directory_reports_both_missing_files(tmp_path: Path) -> None:
    with pytest.raises(ModelDirectoryError) as error:
        resolve_model_files(tmp_path)

    message = str(error.value)
    assert "model.onnx" in message
    assert "selected_tags.csv" in message


def test_missing_model_directory_reports_required_files(tmp_path: Path) -> None:
    with pytest.raises(ModelDirectoryError) as error:
        resolve_model_files(tmp_path / "missing-model")

    message = str(error.value)
    assert "目录不存在" in message
    assert "model.onnx" in message
    assert "selected_tags.csv" in message


def test_model_directory_resolves_required_files(tmp_path: Path) -> None:
    (tmp_path / "model.onnx").write_bytes(b"onnx")
    (tmp_path / "selected_tags.csv").write_text(
        "name,category\nsafe,9\n",
        encoding="utf-8",
    )

    files = resolve_model_files(tmp_path)

    assert files.model_path == tmp_path / "model.onnx"
    assert files.tags_path == tmp_path / "selected_tags.csv"
