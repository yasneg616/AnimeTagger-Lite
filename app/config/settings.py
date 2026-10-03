"""Validated defaults plus optional user JSON overrides."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import json
import logging
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping

from app.errors import ConfigurationError
from app.inference.backends import BACKENDS, DEFAULT_BACKEND, backend_spec
from app.prompts.filtering import FilterSettings
from app.runtime_paths import (
    APPLICATION_ROOT,
    RESOURCE_DIR,
    USER_SETTINGS_PATH,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = APPLICATION_ROOT
DEFAULT_SETTINGS_PATH = RESOURCE_DIR / "default_settings.json"

_BUILTIN_DEFAULTS: dict[str, Any] = {
    "general_threshold": 0.35,
    "character_threshold": 0.75,
    "rating_threshold": 0.50,
    "include_character_tags": True,
    "include_rating": False,
    "max_tags": 80,
    "minimum_display_threshold": 0.10,
    "excluded_tags": [],
    "always_include_tags": [],
    "remove_duplicates": True,
    "underscore_to_space": False,
    "unescape_parentheses": True,
    "trim_whitespace": True,
    "collapse_spaces": True,
    "block_censored_tags": True,
    "block_antonym_conflicts": True,
    "profile": "raw",
    "add_profile_prefix": True,
    "negative_mode": "none",
    "negative_preset": "basic",
    "defect_threshold": 0.35,
    "trigger_word": None,
    "trigger_word_position": "first",
    "remove_tags": [],
    "user_negative_tags": [],
    "background": "#FFFFFF",
    "backend": DEFAULT_BACKEND,
    "backend_options": {},
    "top_k": None,
    "model_dir": BACKENDS[DEFAULT_BACKEND].directory,
    "device": "auto",
    "default_export_format": "txt",
    "default_export_dir": "",
    "recent_open_dir": "",
    "recent_export_dir": "",
    "show_low_confidence": False,
}


def _finite_probability(mapping: Mapping[str, Any], key: str) -> float:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"配置字段 {key} 必须是数字。")
    number = float(value)
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ConfigurationError(f"配置字段 {key} 必须是 0 到 1 的有限数值。")
    return number


def _boolean(mapping: Mapping[str, Any], key: str) -> bool:
    value = mapping[key]
    if not isinstance(value, bool):
        raise ConfigurationError(f"配置字段 {key} 必须是布尔值。")
    return value


def _positive_integer(mapping: Mapping[str, Any], key: str) -> int:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigurationError(f"配置字段 {key} 必须是大于 0 的整数。")
    return value


def _non_negative_integer(mapping: Mapping[str, Any], key: str) -> int:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigurationError(f"配置字段 {key} 必须是大于等于 0 的整数。")
    return value


def _string_tuple(mapping: Mapping[str, Any], key: str) -> tuple[str, ...]:
    value = mapping[key]
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, str) for item in value
    ):
        raise ConfigurationError(f"配置字段 {key} 必须是字符串数组。")
    return tuple(item for item in value if item.strip())


def _string(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping[key]
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"配置字段 {key} 必须是非空字符串。")
    return value.strip()


def _optional_string(mapping: Mapping[str, Any], key: str) -> str | None:
    value = mapping[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigurationError(f"配置字段 {key} 必须是字符串或 null。")
    stripped = value.strip()
    return stripped or None


def _possibly_empty_string(mapping: Mapping[str, Any], key: str) -> str:
    value = mapping[key]
    if not isinstance(value, str):
        raise ConfigurationError(f"配置字段 {key} 必须是字符串。")
    return value.strip()


@dataclass(frozen=True, slots=True)
class AppSettings:
    general_threshold: float = 0.35
    character_threshold: float = 0.75
    rating_threshold: float = 0.50
    include_character_tags: bool = True
    include_rating: bool = False
    max_tags: int = 80
    minimum_display_threshold: float = 0.10
    excluded_tags: tuple[str, ...] = ()
    always_include_tags: tuple[str, ...] = ()
    remove_duplicates: bool = True
    underscore_to_space: bool = False
    unescape_parentheses: bool = True
    trim_whitespace: bool = True
    collapse_spaces: bool = True
    block_censored_tags: bool = True
    block_antonym_conflicts: bool = True
    profile: str = "raw"
    add_profile_prefix: bool = True
    negative_mode: str = "none"
    negative_preset: str = "basic"
    defect_threshold: float = 0.35
    trigger_word: str | None = None
    trigger_word_position: str = "first"
    remove_tags: tuple[str, ...] = ()
    user_negative_tags: tuple[str, ...] = ()
    background: str = "#FFFFFF"
    backend: str = DEFAULT_BACKEND
    backend_options: dict[str, dict[str, Any]] = field(default_factory=dict)
    top_k: int | None = None
    model_dir: str = BACKENDS[DEFAULT_BACKEND].directory
    device: str = "auto"
    default_export_format: str = "txt"
    default_export_dir: str = ""
    recent_open_dir: str = ""
    recent_export_dir: str = ""
    show_low_confidence: bool = False

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "AppSettings":
        merged = dict(_BUILTIN_DEFAULTS)
        backend = mapping.get("backend", DEFAULT_BACKEND)
        spec = backend_spec(backend)
        merged.update(model_dir=spec.directory, general_threshold=spec.general_threshold,
                      character_threshold=spec.character_threshold, rating_threshold=spec.rating_threshold,
                      top_k=spec.top_k)
        merged.update(mapping)
        top_k = merged["top_k"]
        if top_k is not None:
            _positive_integer(merged, "top_k")
        options = merged["backend_options"]
        if not isinstance(options, dict):
            raise ConfigurationError("backend_options 必须是对象。")
        for key, value in options.items():
            backend_spec(key)
            if not isinstance(value, dict):
                raise ConfigurationError("backend_options 的值必须是对象。")
            allowed = {"model_dir", "general_threshold", "character_threshold", "rating_threshold", "top_k"}
            if set(value) - allowed:
                raise ConfigurationError("backend_options 包含不支持的字段。")
            cls.from_mapping({"backend": key, **value})
        profile = _string(merged, "profile")
        if profile not in {
            "raw",
            "anime",
            "pony",
            "krea2",
            "cyberillustrious_semireal",
            "lora_caption",
        }:
            raise ConfigurationError(f"未知 profile：{profile}")
        negative_mode = _string(merged, "negative_mode")
        if negative_mode not in {"none", "basic", "cleanup_detected"}:
            raise ConfigurationError(f"未知 negative_mode：{negative_mode}")
        trigger_word_position = _string(merged, "trigger_word_position")
        if trigger_word_position not in {"first", "last"}:
            raise ConfigurationError(
                f"未知 trigger_word_position：{trigger_word_position}"
            )
        device = _string(merged, "device")
        if device not in {"auto", "cpu", "cuda"}:
            raise ConfigurationError(f"未知 device：{device}")
        default_export_format = _string(merged, "default_export_format")
        if default_export_format not in {"txt", "prompt-txt", "json"}:
            raise ConfigurationError(
                f"未知 default_export_format：{default_export_format}"
            )
        return cls(
            backend=backend, backend_options=options, top_k=top_k,
            general_threshold=_finite_probability(merged, "general_threshold"),
            character_threshold=_finite_probability(merged, "character_threshold"),
            rating_threshold=_finite_probability(merged, "rating_threshold"),
            include_character_tags=_boolean(merged, "include_character_tags"),
            include_rating=_boolean(merged, "include_rating"),
            max_tags=_non_negative_integer(merged, "max_tags"),
            minimum_display_threshold=_finite_probability(
                merged, "minimum_display_threshold"
            ),
            excluded_tags=_string_tuple(merged, "excluded_tags"),
            always_include_tags=_string_tuple(merged, "always_include_tags"),
            remove_duplicates=_boolean(merged, "remove_duplicates"),
            underscore_to_space=_boolean(merged, "underscore_to_space"),
            unescape_parentheses=_boolean(merged, "unescape_parentheses"),
            trim_whitespace=_boolean(merged, "trim_whitespace"),
            collapse_spaces=_boolean(merged, "collapse_spaces"),
            block_censored_tags=_boolean(merged, "block_censored_tags"),
            block_antonym_conflicts=_boolean(merged, "block_antonym_conflicts"),
            profile=profile,
            add_profile_prefix=_boolean(merged, "add_profile_prefix"),
            negative_mode=negative_mode,
            negative_preset=_string(merged, "negative_preset"),
            defect_threshold=_finite_probability(merged, "defect_threshold"),
            trigger_word=_optional_string(merged, "trigger_word"),
            trigger_word_position=trigger_word_position,
            remove_tags=_string_tuple(merged, "remove_tags"),
            user_negative_tags=_string_tuple(merged, "user_negative_tags"),
            background=_string(merged, "background"),
            model_dir=_possibly_empty_string(merged, "model_dir"),
            device=device,
            default_export_format=default_export_format,
            default_export_dir=_possibly_empty_string(
                merged, "default_export_dir"
            ),
            recent_open_dir=_possibly_empty_string(merged, "recent_open_dir"),
            recent_export_dir=_possibly_empty_string(
                merged, "recent_export_dir"
            ),
            show_low_confidence=_boolean(merged, "show_low_confidence"),
        )

    def to_filter_settings(self) -> FilterSettings:
        return FilterSettings(
            general_threshold=self.general_threshold,
            character_threshold=self.character_threshold,
            rating_threshold=self.rating_threshold,
            include_character_tags=self.include_character_tags,
            include_rating=self.include_rating,
            max_tags=(
                0
                if self.max_tags == 0
                else (
                    min(self.max_tags, self.top_k) if self.top_k else self.max_tags
                )
            ),
            minimum_display_threshold=self.minimum_display_threshold,
            excluded_tags=self.excluded_tags,
            always_include_tags=self.always_include_tags,
            remove_duplicates=self.remove_duplicates,
            underscore_to_space=self.underscore_to_space,
            unescape_parentheses=self.unescape_parentheses,
            trim_whitespace=self.trim_whitespace,
            collapse_spaces=self.collapse_spaces,
            block_censored_tags=self.block_censored_tags,
            block_antonym_conflicts=self.block_antonym_conflicts,
        )

    def select_backend(self, backend: str) -> "AppSettings":
        spec = backend_spec(backend)
        if backend == self.backend:
            return self
        fields = ("model_dir", "general_threshold", "character_threshold", "rating_threshold", "top_k")
        options = {key: dict(value) for key, value in self.backend_options.items()}
        options[self.backend] = {key: getattr(self, key) for key in fields}
        values = dict(model_dir=spec.directory, general_threshold=spec.general_threshold,
                      character_threshold=spec.character_threshold, rating_threshold=spec.rating_threshold,
                      top_k=spec.top_k)
        values.update(options.get(backend, {}))
        return replace(self, backend=backend, backend_options=options, **values)

    def snapshot(self) -> dict[str, Any]:
        return asdict(self)


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"{label}无法读取：{path}（{exc}）") from exc
    if not isinstance(payload, dict):
        raise ConfigurationError(f"{label}根节点必须是 JSON 对象：{path}")
    return payload


def load_settings(
    *,
    default_path: Path | None = None,
    user_path: Path | None = None,
    warning_sink: Callable[[str], None] | None = None,
) -> AppSettings:
    """Load defaults, overlay known user fields, and safely fall back on errors."""

    defaults_file = Path(default_path) if default_path is not None else DEFAULT_SETTINGS_PATH
    user_file = Path(user_path) if user_path is not None else USER_SETTINGS_PATH

    defaults = {}
    if defaults_file.is_file():
        try:
            defaults.update(_read_json_object(defaults_file, "默认配置"))
            base = AppSettings.from_mapping(defaults)
        except ConfigurationError as exc:
            logger.warning("默认配置无效，使用内置默认值：%s", exc)
            if warning_sink is not None:
                warning_sink(f"默认配置无效，已使用内置默认值：{exc}")
            base = AppSettings.from_mapping(_BUILTIN_DEFAULTS)
    else:
        logger.warning("默认配置不存在，使用内置默认值：%s", defaults_file)
        if warning_sink is not None:
            warning_sink(f"默认配置不存在，已使用内置默认值：{defaults_file}")
        base = AppSettings.from_mapping(_BUILTIN_DEFAULTS)

    if not user_file.is_file():
        return base

    try:
        user_values = _read_json_object(user_file, "用户配置")
        merged = base.snapshot()
        if "backend" in user_values and user_values["backend"] != base.backend:
            merged = base.select_backend(user_values["backend"]).snapshot()
        merged.update(user_values)
        return AppSettings.from_mapping(merged)
    except ConfigurationError as exc:
        # The corrupt file is left untouched for manual recovery. No settings
        # are written implicitly during CLI startup.
        logger.warning("用户配置无效，保留原文件并回退默认值：%s", exc)
        if warning_sink is not None:
            warning_sink(f"用户配置无效，已保留原文件并回退默认值：{exc}")
        return base


def save_settings(
    settings: AppSettings,
    *,
    user_path: Path | None = None,
) -> Path:
    """Atomically persist business settings as UTF-8 JSON.

    Window geometry, splitter positions, and table column widths are UI-only
    state and intentionally remain in ``QSettings``.
    """

    target = Path(user_path) if user_path is not None else USER_SETTINGS_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigurationError(
            f"无法创建配置目录：{target.parent}（{exc}）"
        ) from exc

    document = settings.snapshot()
    document["schema_version"] = 2
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary_path = Path(handle.name)
        os.replace(temporary_path, target)
        temporary_path = None
        return target
    except (OSError, TypeError, ValueError) as exc:
        raise ConfigurationError(f"无法安全保存配置：{target}（{exc}）") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                logger.warning("无法清理配置临时文件：%s", temporary_path)
