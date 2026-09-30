"""Independent mutable state for one manually added image."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from uuid import uuid4

from app.inference.wd14_engine import InferenceResult
from app.prompts.models import PromptBuildResult, TagResult
from app.prompts.injection import overlay_injections


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ImageStatus(str, Enum):
    PENDING = "pending"
    LOADING = "loading"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class ImageItem:
    source_path: Path
    display_name: str = ""
    is_temporary: bool = False
    id: str = field(default_factory=lambda: str(uuid4()))
    status: ImageStatus = ImageStatus.PENDING
    error_message: str = ""
    raw_tags: tuple[TagResult, ...] = ()
    working_tags: list[TagResult] = field(default_factory=list)
    prompt_result: PromptBuildResult | None = None
    inference_result: InferenceResult | None = None
    generated_positive_prompt: str = ""
    generated_negative_prompt: str = ""
    final_positive_prompt: str = ""
    final_negative_prompt: str = ""
    positive_prompt_edited: bool = False
    negative_prompt_edited: bool = False
    prompt_stale: bool = False
    positive_injections: tuple[str, ...] = ()
    edit_revision: int = 0
    is_dirty: bool = False
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        self.source_path = Path(self.source_path)
        if not self.display_name:
            self.display_name = self.source_path.name
        # Never retain a mutable sequence supplied by a caller.
        self.working_tags = list(self.working_tags)
        self.raw_tags = tuple(self.raw_tags)

    @property
    def prompt_was_edited(self) -> bool:
        return self.positive_prompt_edited or self.negative_prompt_edited

    def touch(self) -> None:
        self.edit_revision += 1
        self.updated_at = _now()

    def set_status(
        self,
        status: ImageStatus,
        *,
        error_message: str = "",
    ) -> None:
        self.status = status
        self.error_message = error_message
        self.touch()

    def apply_analysis(
        self,
        inference: InferenceResult,
        raw_tags: tuple[TagResult, ...],
        prompts: PromptBuildResult,
    ) -> None:
        """Replace the working copy after an explicit re-analysis."""

        self.inference_result = inference
        self.positive_injections = ()
        self.raw_tags = tuple(raw_tags)
        self.working_tags = list(prompts.raw_tags)
        self.prompt_result = prompts
        self.generated_positive_prompt = prompts.positive_prompt
        self.generated_negative_prompt = prompts.negative_prompt
        self.final_positive_prompt = prompts.positive_prompt
        self.final_negative_prompt = prompts.negative_prompt
        self.positive_prompt_edited = False
        self.negative_prompt_edited = False
        self.prompt_stale = False
        self.is_dirty = False
        self.set_status(ImageStatus.COMPLETED)

    def replace_working_tags(
        self,
        tags: tuple[TagResult, ...] | list[TagResult],
        *,
        dirty: bool = True,
    ) -> None:
        self.working_tags = list(tags)
        self.is_dirty = dirty
        self.touch()

    def apply_prompt_result(
        self,
        prompts: PromptBuildResult,
        *,
        preserve_manual_prompts: bool = True,
    ) -> None:
        prompts = overlay_injections(prompts, self.positive_injections)
        old_generated_positive = self.generated_positive_prompt
        old_generated_negative = self.generated_negative_prompt
        self.prompt_result = prompts
        self.working_tags = list(prompts.raw_tags)
        self.generated_positive_prompt = prompts.positive_prompt
        self.generated_negative_prompt = prompts.negative_prompt

        if not preserve_manual_prompts or not self.positive_prompt_edited:
            self.final_positive_prompt = prompts.positive_prompt
            self.positive_prompt_edited = False
        if not preserve_manual_prompts or not self.negative_prompt_edited:
            self.final_negative_prompt = prompts.negative_prompt
            self.negative_prompt_edited = False

        generated_changed = (
            old_generated_positive != prompts.positive_prompt
            or old_generated_negative != prompts.negative_prompt
        )
        self.prompt_stale = self.prompt_was_edited and (
            self.prompt_stale or generated_changed
        )
        self.touch()

    def edit_prompt(self, kind: str, text: str) -> None:
        if kind == "positive":
            self.final_positive_prompt = text
            self.positive_prompt_edited = text != self.generated_positive_prompt
        elif kind == "negative":
            self.final_negative_prompt = text
            self.negative_prompt_edited = text != self.generated_negative_prompt
        else:
            raise ValueError(f"未知提示词类型：{kind}")
        if not self.prompt_was_edited:
            self.prompt_stale = False
        self.is_dirty = True
        self.touch()

    def restore_generated_prompt(self, kind: str | None = None) -> None:
        if kind in {None, "positive"}:
            self.final_positive_prompt = self.generated_positive_prompt
            self.positive_prompt_edited = False
        if kind in {None, "negative"}:
            self.final_negative_prompt = self.generated_negative_prompt
            self.negative_prompt_edited = False
        if kind not in {None, "positive", "negative"}:
            raise ValueError(f"未知提示词类型：{kind}")
        self.prompt_stale = self.prompt_was_edited
        self.touch()

    def restore_working_tags(self) -> None:
        self.positive_injections = ()
        self.working_tags = list(self.raw_tags)
        self.is_dirty = self.prompt_was_edited
        self.touch()

    def prepare_for_reanalysis(self) -> None:
        """Keep audit data until a new result arrives, but mark the queue state."""

        self.set_status(ImageStatus.PENDING)
        self.error_message = ""
