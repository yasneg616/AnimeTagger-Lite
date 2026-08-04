from __future__ import annotations

from PySide6.QtCore import Qt

from app.inference.model_loader import TagCategory
from app.prompts.models import PromptGroup, TagResult, TagSource
from app.ui.tag_filter_proxy import TagFilterProxyModel
from app.ui.tag_table_model import TagColumn, TagTableModel


def build_proxy() -> tuple[TagTableModel, TagFilterProxyModel]:
    model = TagTableModel(
        [
            TagResult(
                "1girl",
                0.95,
                TagCategory.GENERAL,
                prompt_group=PromptGroup.COUNT,
            ),
            TagResult(
                "alice",
                0.80,
                TagCategory.CHARACTER,
                prompt_group=PromptGroup.CHARACTER,
            ),
            TagResult(
                "low_score",
                0.05,
                TagCategory.GENERAL,
                prompt_group=PromptGroup.OTHER,
            ),
            TagResult(
                "manual",
                1.0,
                TagCategory.GENERAL,
                source=TagSource.USER,
            ),
        ]
    )
    proxy = TagFilterProxyModel()
    proxy.setSourceModel(model)
    return model, proxy


def proxy_names(proxy: TagFilterProxyModel) -> list[str]:
    return [
        str(proxy.data(proxy.index(row, TagColumn.TAG)))
        for row in range(proxy.rowCount())
    ]


def test_proxy_searches_case_insensitively() -> None:
    _model, proxy = build_proxy()
    proxy.set_search_text("GIRL")
    assert proxy_names(proxy) == ["1girl"]


def test_proxy_filters_category() -> None:
    _model, proxy = build_proxy()
    proxy.set_category_filter("character")
    assert proxy_names(proxy) == ["alice"]


def test_proxy_filters_prompt_group() -> None:
    _model, proxy = build_proxy()
    proxy.set_group_filter("count")
    assert proxy_names(proxy) == ["1girl"]


def test_proxy_hides_low_confidence_by_default() -> None:
    _model, proxy = build_proxy()
    proxy.set_minimum_confidence(0.10)
    assert "low_score" not in proxy_names(proxy)


def test_proxy_can_show_low_confidence() -> None:
    _model, proxy = build_proxy()
    proxy.set_show_low_confidence(True)
    assert "low_score" in proxy_names(proxy)


def test_proxy_always_shows_manual_tag() -> None:
    _model, proxy = build_proxy()
    proxy.set_minimum_confidence(1.0)
    assert "manual" in proxy_names(proxy)


def test_proxy_sorts_confidence() -> None:
    _model, proxy = build_proxy()
    proxy.set_show_low_confidence(True)
    proxy.sort(TagColumn.CONFIDENCE, Qt.SortOrder.DescendingOrder)
    assert proxy_names(proxy)[0] == "manual"


def test_proxy_mapping_supports_safe_source_deletion() -> None:
    model, proxy = build_proxy()
    proxy.set_search_text("alice")
    source_row = proxy.mapToSource(proxy.index(0, 0)).row()
    model.remove_source_rows([source_row])
    assert "alice" not in [tag.name for tag in model.tags]
