"""Typed stage 2 business objects shared by CLI, export, and future UI."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.inference.model_loader import TagCategory


class TagSource(str, Enum):
    MODEL = "model"
    USER = "user"
    PRESET = "preset"


class NegativeTagSource(str, Enum):
    PRESET = "preset"
    DETECTED_DEFECT = "detected_defect"
    USER = "user"


class PromptGroup(str, Enum):
    QUALITY = "quality"
    COUNT = "count"
    SUBJECT = "subject"
    CHARACTER = "character"
    HAIR = "hair"
    EYES_FACE = "eyes_face"
    BODY = "body"
    CLOTHING = "clothing"
    ACCESSORIES = "accessories"
    POSE_ACTION = "pose_action"
    EXPRESSION = "expression"
    COMPOSITION = "composition"
    BACKGROUND = "background"
    LIGHTING = "lighting"
    STYLE = "style"
    OTHER = "other"


PROMPT_GROUP_ORDER: tuple[PromptGroup, ...] = tuple(PromptGroup)


@dataclass(frozen=True, slots=True)
class TagResult:
    """One tag while preserving its original model identity and score."""

    name: str
    confidence: float
    category: TagCategory
    enabled: bool = True
    source: TagSource = TagSource.MODEL
    normalized_name: str | None = None
    prompt_group: PromptGroup | None = None
    model_index: int | None = None

    @property
    def output_name(self) -> str:
        return self.normalized_name if self.normalized_name is not None else self.name


@dataclass(frozen=True, slots=True)
class RemovalRecord:
    tag: TagResult
    reason: str


@dataclass(frozen=True, slots=True)
class FilterResult:
    normalized_tags: tuple[TagResult, ...]
    filtered_tags: tuple[TagResult, ...]
    removed_tags: tuple[RemovalRecord, ...]
    excluded_tags: tuple[TagResult, ...]


@dataclass(frozen=True, slots=True)
class NegativeTag:
    name: str
    sources: tuple[NegativeTagSource, ...]
    confidence: float | None = None
    source_tag: str | None = None


@dataclass(frozen=True, slots=True)
class PromptBuildResult:
    """The single handoff object consumed by CLI, export, and future UI."""

    raw_tags: tuple[TagResult, ...]
    filtered_tags: tuple[TagResult, ...]
    positive_tags: tuple[TagResult, ...]
    negative_tags: tuple[NegativeTag, ...]
    positive_prompt: str
    negative_prompt: str
    removed_tags: tuple[RemovalRecord, ...]
    excluded_tags: tuple[TagResult, ...]
    detected_defects: tuple[TagResult, ...]
    profile_name: str
    settings_snapshot: dict[str, Any]

    def __post_init__(self) -> None:
        # Later mutations of a settings object or source mapping cannot change
        # the audit snapshot attached to an already-built result.
        object.__setattr__(
            self,
            "settings_snapshot",
            copy.deepcopy(self.settings_snapshot),
        )
