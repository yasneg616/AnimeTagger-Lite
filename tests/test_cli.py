from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.errors import ModelDirectoryError
from app.inference.model_loader import (
    ModelFiles,
    TagCategory,
    TagMetadata,
)
from app.inference.providers import CPU_PROVIDER
from app.inference.wd14_engine import (
    InferenceResult,
    ModelInfo,
    TagPrediction,
)
from app.main import build_parser, main


@pytest.fixture(autouse=True)
def isolated_cli_user_settings(monkeypatch, tmp_path):
    # CLI defaults must not depend on the developer's saved GUI profile.
    monkeypatch.setattr("app.config.settings.USER_SETTINGS_PATH", tmp_path / "user-settings.json")


class SuccessfulEngine:
    released = False

    def __init__(self, model_dir: Path, *, device: object) -> None:
        self.model_dir = model_dir
        self.device = device

    def predict(self, image_path: Path, *, image_options: object) -> InferenceResult:
        files = ModelFiles(
            directory=self.model_dir,
            model_path=self.model_dir / "model.onnx",
            tags_path=self.model_dir / "selected_tags.csv",
        )
        info = ModelInfo(
            files=files,
            input_name="input",
            output_name="output",
            input_size=448,
            output_count=3,
            active_provider=CPU_PROVIDER,
            provider_warning="CUDAExecutionProvider 不可用，已自动回退到 CPU。",
        )
        tags = (
            TagMetadata(0, 1, "safe", 9, TagCategory.RATING),
            TagMetadata(1, 2, "1girl", 0, TagCategory.GENERAL),
            TagMetadata(2, 3, "alice", 4, TagCategory.CHARACTER),
        )
        return InferenceResult(
            image_path=image_path,
            model_info=info,
            predictions=tuple(
                TagPrediction(tag, score)
                for tag, score in zip(tags, (0.9, 0.8, 0.9))
            ),
            inference_seconds=0.123,
        )

    def release(self) -> None:
        SuccessfulEngine.released = True


class FailingEngine:
    def __init__(self, model_dir: Path, *, device: object) -> None:
        pass

    def predict(self, image_path: Path, *, image_options: object) -> InferenceResult:
        raise ModelDirectoryError("模型目录缺少必要文件：model.onnx")

    def release(self) -> None:
        pass


def test_cli_parser_accepts_krea2_profile() -> None:
    args = build_parser().parse_args(
        ["image.png", "--model-dir", "models", "--profile", "krea2"]
    )

    assert args.profile == "krea2"


def test_cli_can_select_cyberillustrious_and_its_negative_mode(
    capsys: object,
    tmp_path: Path,
) -> None:
    exit_code = main(
        [
            str(tmp_path / "image.png"),
            "--model-dir",
            str(tmp_path / "model"),
            "--profile",
            "cyberillustrious_semireal",
            "--negative-mode",
            "basic",
        ],
        engine_factory=SuccessfulEngine,  # type: ignore[arg-type]
    )

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert exit_code == 0
    assert "Positive:\n1girl, alice, semi-realistic" in captured.out
    assert "natural skin texture" in captured.out
    assert "Negative:\nworst quality, low quality, blurry" in captured.out


def test_cli_outputs_separate_categories_and_provider(
    capsys: object,
    tmp_path: Path,
) -> None:
    SuccessfulEngine.released = False

    exit_code = main(
        [
            str(tmp_path / "image.png"),
            "--model-dir",
            str(tmp_path / "model"),
            "--show-raw-tags",
        ],
        engine_factory=SuccessfulEngine,  # type: ignore[arg-type]
    )

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert exit_code == 0
    assert "[Rating]" in captured.out
    assert "[General（阈值 ≥ 0.35）]" in captured.out
    assert "[Character（阈值 ≥ 0.75）]" in captured.out
    assert "1girl" in captured.out
    assert "alice" in captured.out
    assert "CPUExecutionProvider" in captured.out
    assert "回退到 CPU" in captured.err
    assert SuccessfulEngine.released


def test_cli_expected_error_has_no_traceback(capsys: object, tmp_path: Path) -> None:
    exit_code = main(
        [
            str(tmp_path / "image.png"),
            "--model-dir",
            str(tmp_path / "model"),
        ],
        engine_factory=FailingEngine,  # type: ignore[arg-type]
    )

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert exit_code == 2
    assert "错误：模型目录缺少必要文件：model.onnx" in captured.err
    assert "Traceback" not in captured.err


def test_cli_default_outputs_prompt_not_raw_debug(
    capsys: object,
    tmp_path: Path,
) -> None:
    exit_code = main(
        [
            str(tmp_path / "image.png"),
            "--model-dir",
            str(tmp_path / "model"),
        ],
        engine_factory=SuccessfulEngine,  # type: ignore[arg-type]
    )

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert exit_code == 0
    assert "Positive:\nalice, 1girl" in captured.out
    assert "[Rating]" not in captured.out
    assert "Negative:" not in captured.out
    assert "safe" not in captured.out


def test_cli_parameters_override_user_config(
    capsys: object,
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "general_threshold": 0.95,
                "character_threshold": 0.95,
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            str(tmp_path / "image.png"),
            "--model-dir",
            str(tmp_path / "model"),
            "--general-threshold",
            "0.35",
            "--character-threshold",
            "0.75",
        ],
        engine_factory=SuccessfulEngine,  # type: ignore[arg-type]
        settings_path=settings_path,
    )

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert exit_code == 0
    assert "Positive:\nalice, 1girl" in captured.out


def test_cli_can_select_anime_profile(capsys: object, tmp_path: Path) -> None:
    exit_code = main(
        [
            str(tmp_path / "image.png"),
            "--model-dir",
            str(tmp_path / "model"),
            "--profile",
            "anime",
        ],
        engine_factory=SuccessfulEngine,  # type: ignore[arg-type]
    )

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert exit_code == 0
    assert "Positive:\nmasterpiece, best quality, amazing quality" in captured.out


def test_cli_json_export(tmp_path: Path, capsys: object) -> None:
    output = tmp_path / "result.json"

    exit_code = main(
        [
            str(tmp_path / "image.png"),
            "--model-dir",
            str(tmp_path / "model"),
            "--output-format",
            "json",
            "--output",
            str(output),
        ],
        engine_factory=SuccessfulEngine,  # type: ignore[arg-type]
    )

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert exit_code == 0
    assert output.is_file()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["positive_prompt"] == "alice, 1girl"
    assert f"Exported: {output}" in captured.out


def test_cli_file_format_requires_output(capsys: object, tmp_path: Path) -> None:
    exit_code = main(
        [
            str(tmp_path / "image.png"),
            "--model-dir",
            str(tmp_path / "model"),
            "--output-format",
            "txt",
        ],
        engine_factory=SuccessfulEngine,  # type: ignore[arg-type]
    )

    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert exit_code == 2
    assert "需要同时提供 --output" in captured.err


def test_cli_invalid_threshold_returns_argparse_error() -> None:
    with pytest.raises(SystemExit) as error:
        main(
            [
                "image.png",
                "--model-dir",
                "model",
                "--general-threshold",
                "nan",
            ],
            engine_factory=SuccessfulEngine,  # type: ignore[arg-type]
        )

    assert error.value.code == 2
