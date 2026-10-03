"""Folder-oriented batch processing shared by the CLI and desktop UI."""

from app.batch.models import (
    BatchConfig,
    BatchErrorType,
    BatchItem,
    BatchItemStatus,
    BatchJob,
    BatchJobStatus,
    BatchTextFormat,
    CaptionPolicy,
    OutputMode,
    ScanOptions,
    ScanResult,
)
from app.batch.service import BatchRunControl, BatchService

__all__ = [
    "BatchConfig",
    "BatchErrorType",
    "BatchItem",
    "BatchItemStatus",
    "BatchJob",
    "BatchJobStatus",
    "BatchRunControl",
    "BatchService",
    "BatchTextFormat",
    "CaptionPolicy",
    "OutputMode",
    "ScanOptions",
    "ScanResult",
]
