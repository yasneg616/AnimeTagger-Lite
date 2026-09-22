"""Editable JSON prompt profiles and negative-prompt presets."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Any

from app.errors import ConfigurationError
from app.prompts.models import PROMPT_GROUP_ORDER, PromptGroup

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PromptProfile:
    name: str
    prefix_tags: tuple[str, ...] = ()
    add_prefix_default: bool = False
    sort_mode: str = "confidence"
    allowed_groups: tuple[PromptGroup, ...] | None = None
    remove_tags: tuple[str, ...] = ()
    prompt_format: str = "tags"


def _builtin_profiles() -> dict[str, PromptProfile]:
    lora_groups = (
        PromptGroup.COUNT,
        PromptGroup.SUBJECT,
        PromptGroup.CHARACTER,
        PromptGroup.HAIR,
        PromptGroup.EYES_FACE,
        PromptGroup.BODY,
        PromptGroup.CLOTHING,
        PromptGroup.ACCESSORIES,
        PromptGroup.POSE_ACTION,
        PromptGroup.EXPRESSION,
        PromptGroup.COMPOSITION,
        PromptGroup.BACKGROUND,
        PromptGroup.LIGHTING,
    )
    return {
        "raw": PromptProfile("raw"),
        "anime": PromptProfile(
            "anime",
            ("masterpiece", "best quality", "amazing quality"),
            True,
            "group",
        ),
        "pony": PromptProfile("pony", (), False, "group"),
        "krea2": PromptProfile(
            name="krea2",
            sort_mode="group",
            remove_tags=("masterpiece", "best quality", "amazing quality"),
            prompt_format="krea2",
        ),
        "cyberillustrious_semireal": PromptProfile(
            name="cyberillustrious_semireal",
            sort_mode="group",
            prompt_format="cyberillustrious_semireal",
        ),
        "lora_caption": PromptProfile(
            "lora_caption",
            (),
            False,
            "group",
            lora_groups,
            ("masterpiece", "best quality", "amazing quality"),
        ),
    }


def _string_list(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} 必须是字符串数组。")
    return tuple(item.strip() for item in value if item.strip())


class PromptProfileCatalog:
    def __init__(
        self,
        profiles: dict[str, PromptProfile] | None = None,
        *,
        used_fallback: bool = False,
    ) -> None:
        self._profiles = profiles or _builtin_profiles()
        self.used_fallback = used_fallback

    @classmethod
    def from_json(cls, path: Path) -> "PromptProfileCatalog":
        profile_path = Path(path)
        try:
            with profile_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict) or not isinstance(
                payload.get("profiles"), dict
            ):
                raise ValueError("根节点必须包含 profiles 对象。")
            parsed: dict[str, PromptProfile] = {}
            for name, raw in payload["profiles"].items():
                if not isinstance(name, str) or not isinstance(raw, dict):
                    raise ValueError("profile 名称和内容格式无效。")
                sort_mode = raw.get("sort_mode", "confidence")
                if sort_mode not in {"confidence", "group"}:
                    raise ValueError(f"profile {name} 的 sort_mode 无效。")
                prompt_format = raw.get("prompt_format", "tags")
                if prompt_format not in {
                    "tags",
                    "krea2",
                    "cyberillustrious_semireal",
                }:
                    raise ValueError(f"profile {name} 的 prompt_format 无效。")
                raw_groups = raw.get("allowed_groups")
                allowed_groups: tuple[PromptGroup, ...] | None
                if raw_groups is None:
                    allowed_groups = None
                else:
                    allowed_groups = tuple(
                        PromptGroup(value)
                        for value in _string_list(
                            raw_groups, f"{name}.allowed_groups"
                        )
                    )
                add_prefix_default = raw.get("add_prefix_default", False)
                if not isinstance(add_prefix_default, bool):
                    raise ValueError(
                        f"profile {name} 的 add_prefix_default 必须是布尔值。"
                    )
                parsed[name] = PromptProfile(
                    name=name,
                    prefix_tags=_string_list(
                        raw.get("prefix_tags"), f"{name}.prefix_tags"
                    ),
                    add_prefix_default=add_prefix_default,
                    sort_mode=sort_mode,
                    allowed_groups=allowed_groups,
                    remove_tags=_string_list(
                        raw.get("remove_tags"), f"{name}.remove_tags"
                    ),
                    prompt_format=prompt_format,
                )
            required = {"raw", "anime", "pony", "lora_caption"}
            if not required.issubset(parsed):
                raise ValueError(
                    f"缺少必要 profile：{', '.join(sorted(required - set(parsed)))}"
                )
            parsed.setdefault("krea2", _builtin_profiles()["krea2"])
            parsed.setdefault(
                "cyberillustrious_semireal",
                _builtin_profiles()["cyberillustrious_semireal"],
            )
            return cls(parsed)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ) as exc:
            logger.warning(
                "提示词 profile %s 无法加载，使用内置默认值：%s",
                profile_path,
                exc,
            )
            return cls(_builtin_profiles(), used_fallback=True)

    def get(self, name: str) -> PromptProfile:
        try:
            return self._profiles[name]
        except KeyError as exc:
            raise ConfigurationError(f"未找到提示词 profile：{name}") from exc


def _builtin_negative_presets() -> tuple[dict[str, tuple[str, ...]], tuple[str, ...]]:
    return (
        {
            "basic": (
                "low quality",
                "worst quality",
                "blurry",
                "jpeg artifacts",
                "watermark",
                "text",
                "logo",
            ),
            "quality_only": ("low quality", "worst quality", "blurry"),
            "krea2_short": (
                "extra limbs",
                "malformed hands",
                "duplicated subjects",
                "text",
                "watermark",
            ),
            "cyberillustrious_short": (
                "worst quality",
                "low quality",
                "blurry",
                "bad anatomy",
                "deformed anatomy",
                "malformed hands",
                "extra fingers",
                "missing fingers",
                "plastic skin",
                "waxy skin",
                "overprocessed skin",
                "oversaturated",
            ),
        },
        (
            "watermark",
            "text",
            "signature",
            "logo",
            "jpeg artifacts",
            "blurry",
            "lowres",
            "mosaic censoring",
            "censored",
            "scan artifacts",
        ),
    )


class NegativePresetCatalog:
    def __init__(
        self,
        presets: dict[str, tuple[str, ...]] | None = None,
        defect_tags: tuple[str, ...] | None = None,
        *,
        used_fallback: bool = False,
    ) -> None:
        builtins, builtin_defects = _builtin_negative_presets()
        self._presets = presets or builtins
        self.defect_tags = defect_tags or builtin_defects
        self.used_fallback = used_fallback

    @classmethod
    def from_json(cls, path: Path) -> "NegativePresetCatalog":
        preset_path = Path(path)
        try:
            with preset_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict) or not isinstance(
                payload.get("presets"), dict
            ):
                raise ValueError("根节点必须包含 presets 对象。")
            presets = {
                name: _string_list(values, f"presets.{name}")
                for name, values in payload["presets"].items()
                if isinstance(name, str)
            }
            if not presets:
                raise ValueError("至少需要一个反向预设。")
            presets.setdefault(
                "cyberillustrious_short",
                _builtin_negative_presets()[0]["cyberillustrious_short"],
            )
            defect_tags = _string_list(payload.get("defect_tags"), "defect_tags")
            if not defect_tags:
                raise ValueError("defect_tags 不能为空。")
            return cls(presets, defect_tags)
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ) as exc:
            logger.warning(
                "反向提示词预设 %s 无法加载，使用内置默认值：%s",
                preset_path,
                exc,
            )
            presets, defects = _builtin_negative_presets()
            return cls(presets, defects, used_fallback=True)

    def get_preset(self, name: str) -> tuple[str, ...]:
        try:
            return self._presets[name]
        except KeyError as exc:
            raise ConfigurationError(f"未找到反向提示词预设：{name}") from exc
