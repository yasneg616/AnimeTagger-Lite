"""Typed, serializable batch job state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from app.config.settings import AppSettings
from app.errors import BatchConfigurationError


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def stable_item_id(path: Path) -> str:
    normalized = str(Path(path).resolve(strict=False)).replace("\\", "/").casefold()
    return str(uuid5(NAMESPACE_URL, f"animetagger-lite:{normalized}"))


class OutputMode(str, Enum):
    BESIDE = "beside"
    MIRROR = "mirror"
    FLAT = "flat"


class CaptionPolicy(str, Enum):
    SKIP = "skip"
    OVERWRITE = "overwrite"
    BACKUP_AND_OVERWRITE = "backup_and_overwrite"
    APPEND_TRIGGER = "append_trigger"
    MERGE = "merge"


class BatchTextFormat(str, Enum):
    TXT = "txt"
    PROMPT_TXT = "prompt-txt"


class BatchItemStatus(str, Enum):
    DISCOVERED = "discovered"
    PENDING = "pending"
    ANALYZING = "analyzing"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    CANCELLED = "cancelled"
    MISSING = "missing"


class BatchJobStatus(str, Enum):
    CREATED = "created"
    SCANNING = "scanning"
    READY = "ready"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    FAILED = "failed"

    @property
    def terminal(self) -> bool:
        return self in {
            BatchJobStatus.CANCELLED,
            BatchJobStatus.COMPLETED,
            BatchJobStatus.COMPLETED_WITH_ERRORS,
            BatchJobStatus.FAILED,
        }


class BatchErrorType(str, Enum):
    NONE = "none"
    UNSUPPORTED_FORMAT = "unsupported_format"
    DECODE_ERROR = "decode_error"
    IMAGE_TOO_LARGE = "image_too_large"
    MISSING_SOURCE = "missing_source"
    IMAGE_LOAD = "image_load"
    MODEL = "model"
    INFERENCE = "inference"
    OUTPUT_PERMISSION = "output_permission_error"
    OUTPUT_EXISTS = "output_exists"
    PATH = "path_error"
    OUTPUT_PATH = "output_path"
    CAPTION_READ = "caption_read"
    CAPTION_WRITE = "caption_write"
    JSON_WRITE = "json_write"
    MANIFEST_WRITE = "manifest_write"
    PERMISSION = "permission"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ScanOptions:
    roots: tuple[Path, ...]
    recursive: bool = False
    include_hidden: bool = False
    follow_symlinks: bool = False
    max_files: int = 100_000
    max_depth: int = 64
    output_root: Path | None = None

    def __post_init__(self) -> None:
        normalized = tuple(Path(root).expanduser() for root in self.roots)
        object.__setattr__(self, "roots", normalized)
        if not normalized:
            raise BatchConfigurationError("批处理至少需要一个输入文件夹或图片。")
        if self.max_files <= 0:
            raise BatchConfigurationError("扫描文件数上限必须大于 0。")
        if self.max_depth < 0:
            raise BatchConfigurationError("扫描深度上限不能小于 0。")
        if self.output_root is not None:
            object.__setattr__(
                self,
                "output_root",
                Path(self.output_root).expanduser(),
            )


@dataclass(frozen=True, slots=True)
class BatchConfig:
    output_mode: OutputMode = OutputMode.BESIDE
    output_root: Path | None = None
    caption_policy: CaptionPolicy = CaptionPolicy.SKIP
    text_format: BatchTextFormat = BatchTextFormat.TXT
    write_captions: bool = True
    write_json: bool = False
    write_csv: bool = True
    write_summary_json: bool = False
    metadata_dir: Path | None = None
    dry_run: bool = False
    manifest_every: int = 10
    max_retries: int = 1
    csv_bom: bool = False
    csv_success_only: bool = False
    overwrite_reports: bool = False

    def __post_init__(self) -> None:
        if self.output_root is not None:
            object.__setattr__(
                self,
                "output_root",
                Path(self.output_root).expanduser(),
            )
        if self.metadata_dir is not None:
            object.__setattr__(
                self,
                "metadata_dir",
                Path(self.metadata_dir).expanduser(),
            )
        if self.output_mode is not OutputMode.BESIDE and self.output_root is None:
            raise BatchConfigurationError(
                f"输出模式 {self.output_mode.value} 需要指定输出目录。"
            )
        if (
            not self.write_captions
            and not self.write_json
            and not self.write_csv
            and not self.write_summary_json
        ):
            raise BatchConfigurationError("至少需要启用一种批处理输出。")
        if (
            self.text_format is BatchTextFormat.PROMPT_TXT
            and self.caption_policy
            in {CaptionPolicy.APPEND_TRIGGER, CaptionPolicy.MERGE}
        ):
            raise BatchConfigurationError(
                "append_trigger 和 merge 只适用于逗号分隔的 txt Caption。"
            )
        if self.manifest_every <= 0:
            raise BatchConfigurationError("Manifest 保存间隔必须大于 0。")
        if self.max_retries < 0:
            raise BatchConfigurationError("最大重试次数不能小于 0。")


@dataclass(slots=True)
class BatchItem:
    source_path: Path
    source_root: Path
    relative_path: Path
    id: str = ""
    selected: bool = True
    status: BatchItemStatus = BatchItemStatus.DISCOVERED
    file_size: int | None = None
    image_format: str = ""
    caption_path: Path | None = None
    json_path: Path | None = None
    backup_path: Path | None = None
    positive_prompt: str = ""
    negative_prompt: str = ""
    provider: str = ""
    inference_time_ms: float | None = None
    elapsed_ms: float | None = None
    retry_count: int = 0
    attempt_count: int = 0
    model_name: str = ""
    tag_count: int = 0
    character_tags: str = ""
    rating_tags: str = ""
    started_at: str | None = None
    completed_at: str | None = None
    output_action: str = ""
    error_type: BatchErrorType = BatchErrorType.NONE
    error_message: str = ""
    updated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.source_path = Path(self.source_path)
        self.source_root = Path(self.source_root)
        self.relative_path = Path(self.relative_path)
        if not self.id:
            self.id = stable_item_id(self.source_path)

    def mark(
        self,
        status: BatchItemStatus,
        *,
        error_type: BatchErrorType = BatchErrorType.NONE,
        error_message: str = "",
    ) -> None:
        self.status = status
        self.error_type = error_type
        self.error_message = error_message
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "selected": self.selected,
            "source_path": str(self.source_path),
            "source_root": str(self.source_root),
            "relative_path": self.relative_path.as_posix(),
            "status": self.status.value,
            "file_size": self.file_size,
            "image_format": self.image_format,
            "caption_path": str(self.caption_path) if self.caption_path else None,
            "json_path": str(self.json_path) if self.json_path else None,
            "backup_path": str(self.backup_path) if self.backup_path else None,
            "positive_prompt": self.positive_prompt,
            "negative_prompt": self.negative_prompt,
            "provider": self.provider,
            "inference_time_ms": self.inference_time_ms,
            "elapsed_ms": self.elapsed_ms,
            "retry_count": self.retry_count,
            "attempt_count": self.attempt_count,
            "model_name": self.model_name,
            "tag_count": self.tag_count,
            "character_tags": self.character_tags,
            "rating_tags": self.rating_tags,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "output_action": self.output_action,
            "error_type": self.error_type.value,
            "error_message": self.error_message,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BatchItem":
        try:
            item = cls(
                id=str(payload["id"]),
                selected=bool(payload.get("selected", True)),
                source_path=Path(str(payload["source_path"])),
                source_root=Path(str(payload["source_root"])),
                relative_path=Path(str(payload["relative_path"])),
                status=BatchItemStatus(str(payload["status"])),
            )
            for field_name in ("caption_path", "json_path", "backup_path"):
                value = payload.get(field_name)
                setattr(item, field_name, Path(str(value)) if value else None)
            item.positive_prompt = str(payload.get("positive_prompt", ""))
            item.negative_prompt = str(payload.get("negative_prompt", ""))
            item.provider = str(payload.get("provider", ""))
            item.inference_time_ms = _optional_float(
                payload.get("inference_time_ms")
            )
            item.elapsed_ms = _optional_float(payload.get("elapsed_ms"))
            item.retry_count = int(payload.get("retry_count", 0))
            item.attempt_count = int(payload.get("attempt_count", 0))
            item.file_size = (
                None
                if payload.get("file_size") is None
                else int(payload["file_size"])
            )
            item.image_format = str(payload.get("image_format", ""))
            item.model_name = str(payload.get("model_name", ""))
            item.tag_count = int(payload.get("tag_count", 0))
            item.character_tags = str(payload.get("character_tags", ""))
            item.rating_tags = str(payload.get("rating_tags", ""))
            item.started_at = _optional_text(payload.get("started_at"))
            item.completed_at = _optional_text(payload.get("completed_at"))
            item.output_action = str(payload.get("output_action", ""))
            item.error_type = BatchErrorType(
                str(payload.get("error_type", BatchErrorType.NONE.value))
            )
            item.error_message = str(payload.get("error_message", ""))
            item.updated_at = str(payload.get("updated_at", utc_now()))
            return item
        except (KeyError, TypeError, ValueError) as exc:
            raise BatchConfigurationError("Manifest 中包含无效的批处理条目。") from exc


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


@dataclass(frozen=True, slots=True)
class ScanResult:
    items: tuple[BatchItem, ...]
    roots: tuple[Path, ...]
    warnings: tuple[str, ...] = ()
    duplicate_count: int = 0
    unsupported_count: int = 0
    hidden_count: int = 0
    symlink_count: int = 0
    permission_error_count: int = 0
    truncated: bool = False
    cancelled: bool = False


@dataclass(slots=True)
class BatchJob:
    scan_options: ScanOptions
    config: BatchConfig
    settings: AppSettings
    items: list[BatchItem]
    id: str = field(default_factory=lambda: str(uuid4()))
    status: BatchJobStatus = BatchJobStatus.CREATED
    created_at: str = field(default_factory=utc_now)
    started_at: str | None = None
    finished_at: str | None = None
    manifest_path: Path | None = None
    summary_csv_path: Path | None = None
    summary_json_path: Path | None = None
    warnings: list[str] = field(default_factory=list)
    resumed_from_manifest: bool = False

    def counts(self) -> dict[str, int]:
        counts = {status.value: 0 for status in BatchItemStatus}
        for item in self.items:
            counts[item.status.value] += 1
        counts["total"] = len(self.items)
        return counts

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "job_id": self.id,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "scan_options": {
                "roots": [str(root) for root in self.scan_options.roots],
                "recursive": self.scan_options.recursive,
                "include_hidden": self.scan_options.include_hidden,
                "follow_symlinks": self.scan_options.follow_symlinks,
                "max_files": self.scan_options.max_files,
                "max_depth": self.scan_options.max_depth,
                "output_root": (
                    str(self.scan_options.output_root)
                    if self.scan_options.output_root
                    else None
                ),
            },
            "config": {
                "output_mode": self.config.output_mode.value,
                "output_root": (
                    str(self.config.output_root) if self.config.output_root else None
                ),
                "caption_policy": self.config.caption_policy.value,
                "text_format": self.config.text_format.value,
                "write_captions": self.config.write_captions,
                "write_json": self.config.write_json,
                "write_csv": self.config.write_csv,
                "write_summary_json": self.config.write_summary_json,
                "metadata_dir": (
                    str(self.config.metadata_dir) if self.config.metadata_dir else None
                ),
                "dry_run": self.config.dry_run,
                "manifest_every": self.config.manifest_every,
                "max_retries": self.config.max_retries,
                "csv_bom": self.config.csv_bom,
                "csv_success_only": self.config.csv_success_only,
                "overwrite_reports": self.config.overwrite_reports,
            },
            "settings": self.settings.snapshot(),
            "counts": self.counts(),
            "warnings": list(self.warnings),
            "resumed_from_manifest": self.resumed_from_manifest,
            "paths": {
                "manifest": str(self.manifest_path) if self.manifest_path else None,
                "summary_csv": (
                    str(self.summary_csv_path) if self.summary_csv_path else None
                ),
                "summary_json": (
                    str(self.summary_json_path) if self.summary_json_path else None
                ),
            },
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BatchJob":
        try:
            if payload.get("schema_version") != 1:
                raise BatchConfigurationError("不支持的 Manifest schema_version。")
            raw_scan = payload["scan_options"]
            raw_config = payload["config"]
            scan = ScanOptions(
                roots=tuple(Path(str(root)) for root in raw_scan["roots"]),
                recursive=bool(raw_scan["recursive"]),
                include_hidden=bool(raw_scan["include_hidden"]),
                follow_symlinks=bool(raw_scan["follow_symlinks"]),
                max_files=int(raw_scan["max_files"]),
                max_depth=int(raw_scan["max_depth"]),
                output_root=(
                    Path(str(raw_scan["output_root"]))
                    if raw_scan.get("output_root")
                    else None
                ),
            )
            config = BatchConfig(
                output_mode=OutputMode(str(raw_config["output_mode"])),
                output_root=(
                    Path(str(raw_config["output_root"]))
                    if raw_config.get("output_root")
                    else None
                ),
                caption_policy=CaptionPolicy(str(raw_config["caption_policy"])),
                text_format=BatchTextFormat(
                    str(raw_config.get("text_format", BatchTextFormat.TXT.value))
                ),
                write_captions=bool(raw_config["write_captions"]),
                write_json=bool(raw_config["write_json"]),
                write_csv=bool(raw_config["write_csv"]),
                write_summary_json=bool(raw_config["write_summary_json"]),
                metadata_dir=(
                    Path(str(raw_config["metadata_dir"]))
                    if raw_config.get("metadata_dir")
                    else None
                ),
                dry_run=bool(raw_config["dry_run"]),
                manifest_every=int(raw_config["manifest_every"]),
                max_retries=int(raw_config.get("max_retries", 1)),
                csv_bom=bool(raw_config.get("csv_bom", False)),
                csv_success_only=bool(
                    raw_config.get("csv_success_only", False)
                ),
                overwrite_reports=bool(
                    raw_config.get("overwrite_reports", False)
                ),
            )
            job = cls(
                id=str(payload["job_id"]),
                status=BatchJobStatus(str(payload["status"])),
                created_at=str(payload["created_at"]),
                scan_options=scan,
                config=config,
                settings=AppSettings.from_mapping(payload["settings"]),
                items=[
                    BatchItem.from_dict(item)
                    for item in payload.get("items", [])
                ],
            )
            job.started_at = _optional_text(payload.get("started_at"))
            job.finished_at = _optional_text(payload.get("finished_at"))
            job.warnings = [str(item) for item in payload.get("warnings", [])]
            job.resumed_from_manifest = bool(
                payload.get("resumed_from_manifest", False)
            )
            raw_paths = payload.get("paths", {})
            if isinstance(raw_paths, dict):
                job.manifest_path = _optional_path(raw_paths.get("manifest"))
                job.summary_csv_path = _optional_path(raw_paths.get("summary_csv"))
                job.summary_json_path = _optional_path(
                    raw_paths.get("summary_json")
                )
            return job
        except BatchConfigurationError:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise BatchConfigurationError("Manifest 缺少必要的批处理字段。") from exc


def _optional_text(value: object) -> str | None:
    return None if value is None else str(value)


def _optional_path(value: object) -> Path | None:
    return None if value is None else Path(str(value))
