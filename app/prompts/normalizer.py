"""Small, deterministic Danbooru-style tag normalizer."""

from __future__ import annotations

from dataclasses import dataclass, replace
import re

from app.errors import TagProcessingError
from app.prompts.models import TagResult

_REPEATED_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class NormalizerSettings:
    underscore_to_space: bool = False
    unescape_parentheses: bool = True
    trim_whitespace: bool = True
    collapse_spaces: bool = True


class TagNormalizer:
    """Normalize one label without splitting or changing letter case."""

    def normalize_name(
        self,
        name: str,
        settings: NormalizerSettings,
    ) -> str | None:
        if not isinstance(name, str):
            raise TagProcessingError("标签名称必须是字符串。")

        normalized = name
        if settings.underscore_to_space:
            normalized = normalized.replace("_", " ")
        if settings.unescape_parentheses:
            normalized = normalized.replace(r"\(", "(").replace(r"\)", ")")
        if settings.collapse_spaces:
            normalized = _REPEATED_WHITESPACE.sub(" ", normalized)
        if settings.trim_whitespace:
            normalized = normalized.strip()

        if "," in normalized:
            raise TagProcessingError(
                f"单个标签不能包含英文逗号：{name!r}；请将其作为独立标签提供。"
            )
        return normalized if normalized else None

    def normalize_tag(
        self,
        tag: TagResult,
        settings: NormalizerSettings,
    ) -> TagResult:
        normalized_name = self.normalize_name(tag.name, settings)
        if tag.normalized_name == normalized_name:
            return tag
        return replace(
            tag,
            normalized_name=normalized_name,
            # A changed output name may belong to a different prompt group.
            prompt_group=None,
        )


def canonical_tag_key(name: str) -> str:
    """Comparison key used only for matching/deduplication, not display."""

    return " ".join(name.replace("_", " ").split()).casefold()
