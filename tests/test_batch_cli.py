from __future__ import annotations

from pathlib import Path

import pytest

from app import __version__
from app import batch_cli
from app.batch.models import BatchJobStatus
from app.errors import BatchConfigurationError
from app.main import main as app_main
from tests.batch_helpers import FakeBatchTaggingService, touch_image


def test_batch_help_parser_exposes_stage4_options() -> None:
    help_text = batch_cli.build_parser().format_help()
    for option in (
        "--recursive",
        "--lora",
        "--trigger-word",
        "--output-mode",
        "--existing-caption",
        "--dry-run",
        "--resume",
        "--retry-failed",
    ):
        assert option in help_text


def test_batch_parser_accepts_krea2_profile() -> None:
    args = batch_cli.build_parser().parse_args(
        ["images", "--model-dir", "models", "--profile", "krea2"]
    )

    assert args.profile == "krea2"


def test_batch_parser_accepts_cyberillustrious_profile() -> None:
    args = batch_cli.build_parser().parse_args(
        [
            "images",
            "--model-dir",
            "models",
            "--profile",
            "cyberillustrious_semireal",
        ]
    )

    assert args.profile == "cyberillustrious_semireal"


def test_batch_cli_exposes_shared_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        batch_cli.build_parser().parse_args(["--version"])
    assert raised.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_dry_run_does_not_load_model_or_write_any_output(
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    fake = FakeBatchTaggingService(loaded=False)
    code = batch_cli.run(
        [str(tmp_path), "--dry-run"],
        tagging_service=fake,  # type: ignore[arg-type]
    )
    assert code == batch_cli.EXIT_OK
    assert fake.load_calls == 0
    assert fake.calls == []
    assert not (tmp_path / "one.txt").exists()
    assert not (tmp_path / ".animetagger").exists()


def test_dry_run_default_is_non_recursive(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    touch_image(tmp_path / "top.png")
    touch_image(tmp_path / "nested" / "inside.png")
    batch_cli.run([str(tmp_path), "--dry-run"])
    assert "发现 1 张" in capsys.readouterr().out


def test_dry_run_recursive_includes_nested_images(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    touch_image(tmp_path / "top.png")
    touch_image(tmp_path / "nested" / "inside.png")
    batch_cli.run([str(tmp_path), "--dry-run", "--recursive"])
    assert "发现 2 张" in capsys.readouterr().out


def test_default_existing_caption_policy_is_skip(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    touch_image(tmp_path / "one.png")
    (tmp_path / "one.txt").write_text("manual", encoding="utf-8")
    batch_cli.run([str(tmp_path), "--dry-run"])
    output = capsys.readouterr().out
    assert "已有 Caption 1 个" in output
    assert "将跳过 1 个" in output


def test_overwrite_without_yes_is_rejected_before_scan(tmp_path: Path) -> None:
    touch_image(tmp_path / "one.png")
    with pytest.raises(BatchConfigurationError):
        batch_cli.run(
            [
                str(tmp_path),
                "--existing-caption",
                "overwrite",
            ],
            tagging_service=FakeBatchTaggingService(),  # type: ignore[arg-type]
        )


def test_overwrite_dry_run_does_not_require_yes(tmp_path: Path) -> None:
    touch_image(tmp_path / "one.png")
    assert (
        batch_cli.run(
            [
                str(tmp_path),
                "--existing-caption",
                "overwrite",
                "--dry-run",
            ]
        )
        == batch_cli.EXIT_OK
    )


def test_multiple_sources_are_combined_in_preview(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    one = tmp_path / "one"
    two = tmp_path / "two"
    touch_image(one / "a.png")
    touch_image(two / "b.png")
    batch_cli.run([str(one), str(two), "--dry-run"])
    assert "发现 2 张" in capsys.readouterr().out


def test_mirror_without_output_root_returns_configuration_code(
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    assert (
        batch_cli.main(
            [str(tmp_path), "--output-mode", "mirror", "--dry-run"]
        )
        == batch_cli.EXIT_CONFIGURATION
    )


def test_missing_model_returns_dedicated_model_code(tmp_path: Path) -> None:
    touch_image(tmp_path / "one.png")
    assert (
        batch_cli.main(
            [
                str(tmp_path),
                "--model-dir",
                str(tmp_path / "missing-model"),
            ]
        )
        == batch_cli.EXIT_MODEL
    )


def test_successful_fake_batch_loads_model_once_and_returns_zero(
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    fake = FakeBatchTaggingService(loaded=False)
    code = batch_cli.run(
        [
            str(tmp_path),
            "--model-dir",
            str(tmp_path / "fake-model"),
            "--export",
            "txt",
        ],
        tagging_service=fake,  # type: ignore[arg-type]
    )
    assert code == batch_cli.EXIT_OK
    assert fake.load_calls == 1
    assert fake.unload_calls == 1
    assert len(fake.calls) == 1


def test_partial_failure_returns_partial_code(tmp_path: Path) -> None:
    touch_image(tmp_path / "bad.png")
    touch_image(tmp_path / "good.png")
    fake = FakeBatchTaggingService(loaded=False)
    fake.fail_names.add("bad.png")
    code = batch_cli.run(
        [
            str(tmp_path),
            "--model-dir",
            str(tmp_path / "fake-model"),
            "--export",
            "txt",
        ],
        tagging_service=fake,  # type: ignore[arg-type]
    )
    assert code == batch_cli.EXIT_PARTIAL
    assert (tmp_path / "good.txt").is_file()


def test_cancelled_job_returns_cancel_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    touch_image(tmp_path / "one.png")
    fake = FakeBatchTaggingService(loaded=False)

    def cancel_run(self, job, **_kwargs):
        job.status = BatchJobStatus.CANCELLED
        return job

    monkeypatch.setattr("app.batch.service.BatchService.run_job", cancel_run)
    code = batch_cli.run(
        [
            str(tmp_path),
            "--model-dir",
            str(tmp_path / "fake-model"),
            "--export",
            "txt",
        ],
        tagging_service=fake,  # type: ignore[arg-type]
    )
    assert code == batch_cli.EXIT_CANCELLED


def test_conflicting_text_exports_are_rejected(tmp_path: Path) -> None:
    touch_image(tmp_path / "one.png")
    with pytest.raises(BatchConfigurationError):
        batch_cli.run(
            [
                str(tmp_path),
                "--dry-run",
                "--export",
                "txt",
                "--export",
                "prompt-txt",
            ]
        )


def test_dry_run_does_not_create_missing_output_root(tmp_path: Path) -> None:
    source = tmp_path / "source"
    touch_image(source / "one.png")
    output = tmp_path / "does-not-exist"
    batch_cli.run(
        [
            str(source),
            "--dry-run",
            "--output-mode",
            "mirror",
            "--output-root",
            str(output),
        ]
    )
    assert not output.exists()


def test_no_source_is_configuration_error() -> None:
    assert batch_cli.main(["--dry-run"]) == batch_cli.EXIT_CONFIGURATION


def test_app_main_dispatches_batch_without_breaking_single_cli(
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / "one.png")
    assert app_main(["batch", str(tmp_path), "--dry-run"]) == 0
