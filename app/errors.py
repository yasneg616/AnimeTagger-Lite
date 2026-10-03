"""User-facing application exceptions.

The CLI displays these messages without a traceback. Unexpected exceptions are
kept separate so future logging can retain their full diagnostic details.
"""


class AnimeTaggerError(Exception):
    """Base class for expected, user-actionable failures."""


class ImageLoadError(AnimeTaggerError):
    """An image could not be safely decoded or prepared."""


class ModelDirectoryError(AnimeTaggerError):
    """The selected model directory is missing or malformed."""


class TagCsvError(AnimeTaggerError):
    """The model tag CSV is missing or invalid."""


class ProviderError(AnimeTaggerError):
    """No usable ONNX Runtime execution provider is available."""


class ModelLoadError(AnimeTaggerError):
    """The ONNX model could not be loaded or validated."""


class InferenceError(AnimeTaggerError):
    """The ONNX session failed while processing an image."""


class TagProcessingError(AnimeTaggerError):
    """A tag, prompt rule, or prompt profile contains invalid data."""


class ConfigurationError(AnimeTaggerError):
    """A required configuration or preset cannot be used."""


class ExportError(AnimeTaggerError):
    """A prompt export could not be completed safely."""


class BatchConfigurationError(AnimeTaggerError):
    """A batch job contains unsafe or inconsistent settings."""


class BatchScanError(AnimeTaggerError):
    """One or more batch roots could not be scanned safely."""


class BatchManifestError(AnimeTaggerError):
    """A persisted batch manifest is missing, corrupt, or incompatible."""
