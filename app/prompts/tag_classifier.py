"""Lightweight JSON-driven tag grouping and stable prompt ordering."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from app.inference.model_loader import TagCategory
from app.prompts.models import PROMPT_GROUP_ORDER, PromptGroup, TagResult
from app.prompts.normalizer import canonical_tag_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GroupRule:
    exact: frozenset[str] = frozenset()
    prefixes: tuple[str, ...] = ()
    suffixes: tuple[str, ...] = ()


def _canonical_rule(value: str) -> str:
    return canonical_tag_key(value)


def _minimal_rules() -> dict[PromptGroup, GroupRule]:
    return {
        PromptGroup.QUALITY: GroupRule(
            exact=frozenset(
                _canonical_rule(value)
                for value in ("masterpiece", "best quality", "amazing quality")
            )
        ),
        PromptGroup.COUNT: GroupRule(
            exact=frozenset(
                _canonical_rule(value)
                for value in ("solo", "1girl", "1boy", "2girls", "2boys")
            )
        ),
        PromptGroup.HAIR: GroupRule(
            suffixes=(_canonical_rule("hair"), _canonical_rule("haircut")),
        ),
        PromptGroup.EYES_FACE: GroupRule(
            suffixes=(_canonical_rule("eyes"),),
        ),
        PromptGroup.BACKGROUND: GroupRule(
            suffixes=(_canonical_rule("background"),),
        ),
    }


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} 必须是字符串数组。")
    return tuple(_canonical_rule(item) for item in value if item.strip())


class TagClassifier:
    def __init__(
        self,
        rules: dict[PromptGroup, GroupRule] | None = None,
        group_order: tuple[PromptGroup, ...] = PROMPT_GROUP_ORDER,
        *,
        used_fallback: bool = False,
    ) -> None:
        self._rules = rules or _minimal_rules()
        self.group_order = group_order
        self.used_fallback = used_fallback
        self._order_index = {
            group: index for index, group in enumerate(self.group_order)
        }

    @classmethod
    def from_json(cls, path: Path) -> "TagClassifier":
        rule_path = Path(path)
        try:
            with rule_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                raise ValueError("根节点必须是对象。")
            raw_order = payload.get("group_order")
            if not isinstance(raw_order, list):
                raise ValueError("group_order 必须是数组。")
            group_order = tuple(PromptGroup(value) for value in raw_order)
            if len(group_order) != len(PROMPT_GROUP_ORDER) or set(group_order) != set(
                PROMPT_GROUP_ORDER
            ):
                raise ValueError("group_order 必须恰好包含全部 16 个提示词组。")

            raw_groups = payload.get("groups")
            if not isinstance(raw_groups, dict):
                raise ValueError("groups 必须是对象。")
            rules: dict[PromptGroup, GroupRule] = {}
            for group in PROMPT_GROUP_ORDER:
                raw_rule = raw_groups.get(group.value, {})
                if not isinstance(raw_rule, dict):
                    raise ValueError(f"组 {group.value} 的规则必须是对象。")
                rules[group] = GroupRule(
                    exact=frozenset(
                        _string_tuple(raw_rule.get("exact"), f"{group.value}.exact")
                    ),
                    prefixes=_string_tuple(
                        raw_rule.get("prefixes"), f"{group.value}.prefixes"
                    ),
                    suffixes=_string_tuple(
                        raw_rule.get("suffixes"), f"{group.value}.suffixes"
                    ),
                )
            return cls(rules, group_order)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.warning(
                "标签分类规则 %s 无法加载，使用最小内置规则：%s",
                rule_path,
                exc,
            )
            return cls(_minimal_rules(), used_fallback=True)

    def classify(self, tag: TagResult) -> PromptGroup:
        if tag.category is TagCategory.CHARACTER:
            return PromptGroup.CHARACTER
        name = tag.output_name
        if not name:
            return PromptGroup.OTHER
        key = canonical_tag_key(name)
        for group in self.group_order:
            if group is PromptGroup.CHARACTER or group is PromptGroup.OTHER:
                continue
            rule = self._rules.get(group)
            if rule is None:
                continue
            if key in rule.exact:
                return group
            if any(
                key == prefix or key.startswith(f"{prefix} ")
                for prefix in rule.prefixes
            ):
                return group
            if any(
                key == suffix or key.endswith(f" {suffix}")
                for suffix in rule.suffixes
            ):
                return group
        return PromptGroup.OTHER

    def assign_groups(self, tags: Iterable[TagResult]) -> tuple[TagResult, ...]:
        return tuple(replace(tag, prompt_group=self.classify(tag)) for tag in tags)

    def sort_tags(self, tags: Iterable[TagResult]) -> tuple[TagResult, ...]:
        indexed = tuple(enumerate(tags))
        return tuple(
            tag
            for _, tag in sorted(
                indexed,
                key=lambda item: (
                    self._order_index.get(
                        item[1].prompt_group or PromptGroup.OTHER,
                        len(self._order_index),
                    ),
                    -item[1].confidence,
                    item[0],
                ),
            )
        )
