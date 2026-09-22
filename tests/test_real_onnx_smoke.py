from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from app.config.presets import NegativePresetCatalog, PromptProfileCatalog
from app.config.settings import AppSettings
from app.image.image_loader import SUPPORTED_IMAGE_EXTENSIONS, preprocess_image
from app.inference.model_loader import TagCategory, load_selected_tags
from app.inference.providers import CPU_PROVIDER, CUDA_PROVIDER, Device
from app.inference.wd14_engine import WD14Engine
from app.main import main
from app.prompts.pipeline import PromptProcessor, tag_results_from_predictions
from app.prompts.tag_classifier import TagClassifier


def _real_model_dir() -> Path:
    configured = os.environ.get("ANIMETAGGER_MODEL_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[1] / "models" / "wd-vit-tagger-v3"


def _real_validation_image() -> Path | None:
    """Resolve an explicitly configured real image without scanning elsewhere."""

    for variable in (
        "ANIMETAGGER_VALIDATION_IMAGE",
        # Kept for compatibility with the Stage 2 smoke-test instructions.
        "ANIMETAGGER_TEST_IMAGE",
    ):
        configured = os.environ.get(variable)
        if configured:
            path = Path(configured)
            if not path.is_file():
                pytest.fail(f"{variable} 指向的验证图片不存在：{path}")
            if path.suffix.casefold() not in SUPPORTED_IMAGE_EXTENSIONS:
                pytest.fail(f"{variable} 指向不支持的图片格式：{path.suffix}")
            return path

    configured_dir = os.environ.get("ANIMETAGGER_VALIDATION_DIR")
    if not configured_dir:
        return None
    directory = Path(configured_dir)
    if not directory.is_dir():
        pytest.fail(
            f"ANIMETAGGER_VALIDATION_DIR 指向的验证目录不存在：{directory}"
        )
    candidates = sorted(
        (
            path
            for path in directory.iterdir()
            if path.is_file()
            and path.suffix.casefold() in SUPPORTED_IMAGE_EXTENSIONS
        ),
        key=lambda path: path.name.casefold(),
    )
    if not candidates:
        pytest.fail(
            "ANIMETAGGER_VALIDATION_DIR 中没有项目支持的验证图片"
        )
    return candidates[0]


@pytest.mark.smoke
def test_real_wd14_onnx_smoke(tmp_path: Path) -> None:
    """Run the real ONNX graph when the user has supplied the two model files."""

    pytest.importorskip("onnxruntime")
    model_dir = _real_model_dir()
    required = (model_dir / "model.onnx", model_dir / "selected_tags.csv")
    if not all(path.is_file() for path in required):
        pytest.skip(
            "未找到本地 WD14 模型；设置 ANIMETAGGER_MODEL_DIR 后可运行真实 smoke test"
        )

    configured_image = _real_validation_image()
    if configured_image is not None:
        image_path = configured_image
    else:
        # This image exercises only the real ONNX graph and tensor plumbing.
        # Semantic acceptance is covered separately and never uses this fixture.
        image_path = tmp_path / "graph-smoke.png"
        Image.new("RGB", (640, 360), (255, 255, 255)).save(image_path)
    engine = WD14Engine(model_dir, device=Device.AUTO)
    try:
        result = engine.predict(image_path)
        tensor = preprocess_image(image_path, result.model_info.input_size)
        assert tensor.shape == (
            1,
            result.model_info.input_size,
            result.model_info.input_size,
            3,
        )
        assert result.model_info.input_name
        assert result.model_info.output_name
        assert result.model_info.output_count == len(result.predictions)
        assert engine.is_loaded
        engine.release()
        assert not engine.is_loaded
        reloaded = engine.predict(image_path)
    finally:
        engine.release()

    assert result.predictions
    assert len(result.predictions) == result.model_info.output_count
    assert len(reloaded.predictions) == len(result.predictions)
    assert result.model_info.active_provider in {CPU_PROVIDER, CUDA_PROVIDER}
    assert all(0.0 <= item.confidence <= 1.0 for item in result.predictions)
    tags = load_selected_tags(model_dir / "selected_tags.csv")
    categories = {tag.category for tag in tags}
    assert {
        TagCategory.RATING,
        TagCategory.GENERAL,
        TagCategory.CHARACTER,
    }.issubset(categories)


@pytest.mark.smoke
def test_real_anime_image_cli_smoke(capsys: object) -> None:
    """Final acceptance requires a user-provided, non-committed anime image."""

    model_dir = _real_model_dir()
    required = (model_dir / "model.onnx", model_dir / "selected_tags.csv")
    if not all(path.is_file() for path in required):
        pytest.skip("未找到本地 WD14 模型，无法执行真实动漫图 CLI 验收")
    configured_image = _real_validation_image()
    if configured_image is None:
        pytest.skip(
            "未设置 ANIMETAGGER_VALIDATION_IMAGE 或 "
            "ANIMETAGGER_VALIDATION_DIR，不能用占位图冒充真实动漫图验收"
        )

    exit_code = main(
        [
            str(configured_image),
            "--model-dir",
            str(model_dir),
            "--show-raw-tags",
        ]
    )

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert exit_code == 0
    assert "Provider:" in captured.out
    assert "Positive:" in captured.out
    assert "Raw model tags:" in captured.out


@pytest.mark.smoke
def test_same_real_anime_image_compares_anime_pony_and_cyber_profiles() -> None:
    """Compare three renderers on one user-supplied image and one real Session."""

    model_dir = _real_model_dir()
    if not all(
        (model_dir / name).is_file()
        for name in ("model.onnx", "selected_tags.csv")
    ):
        pytest.skip("未找到本地 WD14 模型，无法比较真实图片 profile")
    image_path = _real_validation_image()
    if image_path is None:
        pytest.skip("未提供真实动漫图片，不能使用占位图验收语义输出")

    engine = WD14Engine(model_dir, device=Device.CPU)
    try:
        predictions = engine.predict(image_path).predictions
    finally:
        engine.release()
    resources = Path(__file__).resolve().parents[1] / "resources"
    processor = PromptProcessor(
        TagClassifier.from_json(resources / "tag_categories.json"),
        PromptProfileCatalog.from_json(resources / "prompt_profiles.json"),
        NegativePresetCatalog.from_json(resources / "negative_presets.json"),
    )
    raw = tag_results_from_predictions(predictions)
    outputs = {
        mode: processor.build(
            raw,
            replace(AppSettings(), profile=mode, underscore_to_space=True),
        )
        for mode in ("anime", "pony", "cyberillustrious_semireal")
    }

    assert outputs["anime"].raw_tags == outputs["pony"].raw_tags
    assert outputs["pony"].raw_tags == outputs["cyberillustrious_semireal"].raw_tags
    assert outputs["anime"].positive_prompt.startswith("masterpiece")
    assert "semi-realistic" in outputs["cyberillustrious_semireal"].positive_prompt
    assert "masterpiece" not in outputs["cyberillustrious_semireal"].positive_prompt
    assert not any(
        tag.source.value == "preset" and tag.output_name.startswith("score")
        for tag in outputs["cyberillustrious_semireal"].positive_tags
    )
