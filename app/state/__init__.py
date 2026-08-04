"""Per-image and project state used by the desktop application."""

from app.state.image_item import ImageItem, ImageStatus
from app.state.project_state import AddPathsResult, ProjectState

__all__ = ["AddPathsResult", "ImageItem", "ImageStatus", "ProjectState"]
