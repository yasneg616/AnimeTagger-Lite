"""Background workers used by the desktop UI."""

from app.ui.workers.inference_worker import (
    InferenceController,
    QueueEntry,
)
from app.ui.workers.thumbnail_worker import ImageDecodeCoordinator

__all__ = ["ImageDecodeCoordinator", "InferenceController", "QueueEntry"]
