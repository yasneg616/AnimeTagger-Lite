from __future__ import annotations

import json
from pathlib import Path

from app.config.presets import NegativePresetCatalog, PromptProfileCatalog
from app.config.settings import AppSettings, load_settings

RESOURCE_DIR = Path(__file__).resolve().parents[1] / "resources"


def test_missing_user_fields_use_defaults(tmp_path: Path) -> None:
    user_path = tmp_path / "settings.json"
    user_path.write_text('{"general_threshold": 0.42}', encoding="utf-8")

    settings = load_settings(
        default_path=RESOURCE_DIR / "default_settings.json",
        user_path=user_path,
    )

    assert settings.general_threshold == 0.42
    assert settings.character_threshold == 0.75
    assert settings.negative_mode == "none"


def test_unknown_user_fields_are_ignored(tmp_path: Path) -> None:
    user_path = tmp_path / "settings.json"
    user_path.write_text(
        '{"future_field": {"anything": true}, "max_tags": 12}',
        encoding="utf-8",
    )

    settings = load_settings(
        default_path=RESOURCE_DIR / "default_settings.json",
        user_path=user_path,
    )

    assert settings.max_tags == 12
    assert not hasattr(settings, "future_field")


def test_corrupt_user_config_falls_back_and_preserves_file(
    tmp_path: Path,
    caplog: object,
) -> None:
    user_path = tmp_path / "settings.json"
    original = "{broken json"
    user_path.write_text(original, encoding="utf-8")

    settings = load_settings(
        default_path=RESOURCE_DIR / "default_settings.json",
        user_path=user_path,
    )

    assert settings == AppSettings()
    assert user_path.read_text(encoding="utf-8") == original
    assert "保留原文件并回退默认值" in caplog.text  # type: ignore[attr-defined]


def test_invalid_user_field_falls_back_to_defaults(
    tmp_path: Path,
    caplog: object,
) -> None:
    user_path = tmp_path / "settings.json"
    user_path.write_text('{"general_threshold": "high"}', encoding="utf-8")

    settings = load_settings(
        default_path=RESOURCE_DIR / "default_settings.json",
        user_path=user_path,
    )

    assert settings.general_threshold == 0.35
    assert "配置字段 general_threshold" in caplog.text  # type: ignore[attr-defined]


def test_default_and_user_config_are_layered_separately(tmp_path: Path) -> None:
    default_path = tmp_path / "defaults.json"
    user_path = tmp_path / "settings.json"
    defaults = AppSettings().snapshot()
    defaults["character_threshold"] = 0.66
    default_path.write_text(
        json.dumps(defaults, ensure_ascii=False),
        encoding="utf-8",
    )
    user_path.write_text('{"general_threshold": 0.44}', encoding="utf-8")

    settings = load_settings(default_path=default_path, user_path=user_path)

    assert settings.general_threshold == 0.44
    assert settings.character_threshold == 0.66


def test_prompt_profile_resource_loads_all_required_profiles() -> None:
    catalog = PromptProfileCatalog.from_json(
        RESOURCE_DIR / "prompt_profiles.json"
    )

    assert not catalog.used_fallback
    assert catalog.get("raw").sort_mode == "confidence"
    assert catalog.get("anime").prefix_tags
    assert catalog.get("pony").name == "pony"
    assert catalog.get("lora_caption").allowed_groups


def test_negative_preset_resource_loads_defects() -> None:
    catalog = NegativePresetCatalog.from_json(
        RESOURCE_DIR / "negative_presets.json"
    )

    assert not catalog.used_fallback
    assert "low quality" in catalog.get_preset("basic")
    assert "watermark" in catalog.defect_tags
