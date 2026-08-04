from __future__ import annotations

from PySide6.QtCore import Qt

from app.inference.model_loader import TagCategory
from app.prompts.models import PromptGroup, TagResult, TagSource
from app.ui.tag_table_model import (
    TagColumn,
    TagTableModel,
    sanitize_tag_name,
)


def sample_tags() -> list[TagResult]:
    return [
        TagResult(
            "1girl",
            0.95,
            TagCategory.GENERAL,
            prompt_group=PromptGroup.COUNT,
        ),
        TagResult(
            "alice",
            0.82,
            TagCategory.CHARACTER,
            prompt_group=PromptGroup.CHARACTER,
        ),
    ]


def test_table_has_required_six_columns() -> None:
    model = TagTableModel(sample_tags())
    assert model.columnCount() == 6
    assert [
        model.headerData(column, Qt.Orientation.Horizontal)
        for column in range(6)
    ] == ["启用", "标签", "类别", "提示词分组", "置信度", "来源"]


def test_table_displays_tag_data() -> None:
    model = TagTableModel(sample_tags())
    assert model.data(model.index(0, TagColumn.TAG)) == "1girl"
    assert model.data(model.index(1, TagColumn.CATEGORY)) == "Character"
    assert model.data(model.index(0, TagColumn.GROUP)) == "count"


def test_toggle_enabled_emits_change(qtbot) -> None:
    model = TagTableModel(sample_tags())
    with qtbot.waitSignal(model.tags_changed):
        assert model.setData(
            model.index(0, TagColumn.ENABLED),
            Qt.CheckState.Unchecked,
            Qt.ItemDataRole.CheckStateRole,
        )
    assert not model.tags[0].enabled


def test_edit_tag_marks_source_user(qtbot) -> None:
    model = TagTableModel(sample_tags())
    with qtbot.waitSignal(model.tags_changed):
        assert model.setData(
            model.index(0, TagColumn.TAG),
            "custom hair",
            Qt.ItemDataRole.EditRole,
        )
    assert model.tags[0].name == "custom hair"
    assert model.tags[0].source is TagSource.USER


def test_edit_character_tag_resets_model_category_for_reclassification() -> None:
    model = TagTableModel(sample_tags())
    assert model.setData(
        model.index(1, TagColumn.TAG),
        "long_hair",
        Qt.ItemDataRole.EditRole,
    )
    assert model.tags[1].category is TagCategory.GENERAL
    assert model.tags[1].prompt_group is None
    assert model.tags[1].source is TagSource.USER


def test_edit_tag_sanitizes_commas() -> None:
    model = TagTableModel(sample_tags())
    assert model.setData(
        model.index(0, TagColumn.TAG),
        "red,hair， long",
        Qt.ItemDataRole.EditRole,
    )
    assert model.tags[0].name == "red hair long"


def test_edit_empty_tag_is_rejected() -> None:
    model = TagTableModel(sample_tags())
    assert not model.setData(
        model.index(0, TagColumn.TAG),
        "  ",
        Qt.ItemDataRole.EditRole,
    )
    assert model.tags[0].name == "1girl"


def test_add_manual_tag_uses_manual_confidence_display(qtbot) -> None:
    model = TagTableModel()
    with qtbot.waitSignal(model.tags_changed):
        assert model.add_manual_tag("new_tag")
    assert model.tags[0].source is TagSource.USER
    assert model.tags[0].confidence == 1.0
    assert model.data(model.index(0, TagColumn.CONFIDENCE)) == "手动"


def test_add_empty_manual_tag_is_rejected() -> None:
    model = TagTableModel()
    assert not model.add_manual_tag(" , ， ")
    assert model.rowCount() == 0


def test_delete_multiple_rows_avoids_index_shift(qtbot) -> None:
    tags = [
        TagResult(str(index), 0.9, TagCategory.GENERAL)
        for index in range(5)
    ]
    model = TagTableModel(tags)
    with qtbot.waitSignal(model.tags_changed):
        assert model.remove_source_rows([1, 3]) == 2
    assert [tag.name for tag in model.tags] == ["0", "2", "4"]


def test_delete_duplicate_or_invalid_rows_once() -> None:
    model = TagTableModel(sample_tags())
    assert model.remove_source_rows([0, 0, -1, 99]) == 1
    assert [tag.name for tag in model.tags] == ["alice"]


def test_set_tags_copies_input_list() -> None:
    tags = sample_tags()
    model = TagTableModel(tags)
    tags.clear()
    assert model.rowCount() == 2


def test_set_tags_skips_reset_for_identical_immutable_rows() -> None:
    tags = sample_tags()
    model = TagTableModel(tags)
    resets: list[bool] = []
    model.modelReset.connect(lambda: resets.append(True))

    model.set_tags(tags)

    assert resets == []


def test_sanitize_tag_name_collapses_whitespace() -> None:
    assert sanitize_tag_name("  long   hair  ") == "long hair"
