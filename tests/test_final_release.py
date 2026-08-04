from __future__ import annotations

import json
import hashlib
from pathlib import Path
import re

import pytest

from app import __version__
from app.main import build_parser as build_single_parser
from app.runtime_paths import resolve_runtime_paths
from app.ui.application import build_parser as build_gui_parser
from scripts import build_portable


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_uses_app_version_as_the_single_package_source() -> None:
    text = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'dynamic = ["version"]' in text
    assert 'version = {attr = "app.__version__"}' in text
    project_block = text.split("[project]", 1)[1].split(
        "[project.optional-dependencies]", 1
    )[0]
    assert not re.search(r"(?m)^version\s*=", project_block)


def test_python_sources_do_not_duplicate_release_version_literals() -> None:
    matches: list[str] = []
    for root_name in ("app", "scripts"):
        for path in (PROJECT_ROOT / root_name).rglob("*.py"):
            if path == PROJECT_ROOT / "app" / "__init__.py":
                continue
            if re.search(r"\b\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?\b", path.read_text(encoding="utf-8")):
                matches.append(str(path.relative_to(PROJECT_ROOT)))
    assert matches == []


@pytest.mark.parametrize(
    "parser_factory",
    (build_single_parser, build_gui_parser),
)
def test_user_entry_points_report_the_shared_version(
    parser_factory: object,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        parser_factory().parse_args(["--version"])  # type: ignore[operator]
    assert raised.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_portable_flag_selects_data_subdirectories(tmp_path: Path) -> None:
    root = tmp_path / "portable app"
    root.mkdir()
    (root / "portable.flag").write_bytes(b"")

    paths = resolve_runtime_paths(application_root=root)

    assert paths.is_portable
    assert paths.data_root == root / "data"
    assert paths.config_dir == root / "data" / "config"
    assert paths.log_dir == root / "data" / "logs"
    assert paths.batch_jobs_dir == root / "data" / "batch-jobs"
    assert paths.temp_dir == root / "data" / "temp"


@pytest.mark.parametrize(
    ("variant", "cpu", "gpu"),
    (
        ("cpu", False, False),
        ("cpu", True, True),
        ("cuda", False, False),
        ("cuda", True, True),
        ("cuda", True, False),
    ),
)
def test_build_runtime_conflicts_are_rejected(
    variant: str,
    cpu: bool,
    gpu: bool,
) -> None:
    with pytest.raises(RuntimeError):
        build_portable.verify_runtime_selection(
            variant,
            cpu_installed=cpu,
            gpu_installed=gpu,
        )


def test_build_runtime_separation_accepts_only_matching_runtime() -> None:
    build_portable.verify_runtime_selection(
        "cpu", cpu_installed=True, gpu_installed=False
    )
    build_portable.verify_runtime_selection(
        "cuda", cpu_installed=False, gpu_installed=True
    )


def test_pyinstaller_bootloader_license_is_part_of_release_inventory() -> None:
    assert "PyInstaller" in build_portable.EMBEDDED_BUILD_DISTRIBUTIONS


def test_confirmed_qt_license_texts_match_locked_hashes() -> None:
    for path, expected_sha256 in build_portable.CONFIRMED_QT_LICENSE_TEXTS.values():
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256


def test_formal_zip_names_are_stable() -> None:
    assert (
        build_portable.portable_artifact_name("1.0.0", "cpu")
        == "AnimeTaggerLite-1.0.0-win64-cpu-portable"
    )
    assert (
        build_portable.portable_artifact_name("1.0.0", "cuda")
        == "AnimeTaggerLite-1.0.0-win64-cuda-portable"
    )


def test_spec_excludes_models_tests_and_qt_webengine() -> None:
    path = PROJECT_ROOT / "packaging" / "animetagger-lite.spec"
    text = path.read_text(encoding="utf-8")
    lowered = text.casefold()
    assert "d:\\tagger" not in lowered
    assert "d:/tagger" not in lowered
    assert "model.onnx" not in lowered
    assert "selected_tags.csv" not in lowered
    assert '"pytest"' in lowered
    assert '"pyside6.qtwebenginecore"' in lowered
    assert '"pyside6.qtnetwork"' in lowered
    assert '"pyside6.qtqml"' in lowered
    assert "pyside6/plugins/imageformats/qpdf.dll" in lowered
    assert "onnxruntime_providers_tensorrt.dll" in lowered
    assert '"_zh_cn.qm"' in lowered
    assert "console=debug_console" in lowered
    assert "upx=false" in lowered


def test_build_scripts_pin_python311_and_separate_environments() -> None:
    common = (PROJECT_ROOT / "packaging" / "build_common.ps1").read_text(
        encoding="utf-8"
    )
    cpu_lock = (
        PROJECT_ROOT / "packaging" / "requirements-cpu.lock.txt"
    ).read_text(encoding="utf-8")
    cuda_lock = (
        PROJECT_ROOT / "packaging" / "requirements-cuda.lock.txt"
    ).read_text(encoding="utf-8")
    assert ".venv311-cpu" in common
    assert ".venv311-cuda" in common
    assert "sys.version_info[:2] == (3, 11)" in common
    assert "--check-only" in common
    assert "--archive" in common
    assert "onnxruntime==" in cpu_lock
    assert "onnxruntime-gpu" not in cpu_lock
    assert "onnxruntime-gpu" in cuda_lock
    assert not re.search(r"(?m)^onnxruntime==", cuda_lock)


def _minimal_cpu_portable(root: Path) -> None:
    for relative in (
        "_internal",
        "resources",
        "models/wd-vit-tagger-v3",
        "LICENSES",
        "data/config",
        "data/logs",
        "data/batch-jobs",
        "data/temp",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    for relative in (
        "AnimeTaggerLite.exe",
        "AnimeTaggerLiteCLI.exe",
        "_internal/onnxruntime.dll",
        "models/wd-vit-tagger-v3/README.txt",
        "README.txt",
        "QUICK_START.txt",
        "THIRD_PARTY_NOTICES.txt",
        "LICENSE",
        "portable.flag",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"release fixture")


def test_release_audit_rejects_model_files(tmp_path: Path) -> None:
    root = tmp_path / "portable"
    _minimal_cpu_portable(root)
    assert build_portable.audit_distribution(root, "cpu")["files"] > 0
    (root / "models" / "wd-vit-tagger-v3" / "model.onnx").write_bytes(b"x")
    with pytest.raises(RuntimeError, match="Model weights"):
        build_portable.audit_distribution(root, "cpu")


def test_release_audit_rejects_absolute_development_paths(tmp_path: Path) -> None:
    root = tmp_path / "portable"
    _minimal_cpu_portable(root)
    (root / "README.txt").write_text("source D:/tagger/app", encoding="utf-8")
    with pytest.raises(RuntimeError, match="path markers"):
        build_portable.audit_distribution(root, "cpu")


def test_checksum_manifest_records_required_build_metadata(tmp_path: Path) -> None:
    report = {
        "version": "1.0.0",
        "variant": "cpu",
        "archive_name": "AnimeTaggerLite-1.0.0-win64-cpu-portable.zip",
        "archive_sha256": "a" * 64,
        "archive_bytes": 123,
        "portable_bytes": 456,
        "python_version": "3.11.9",
        "pyinstaller_version": "6.21.0",
        "onnx_runtime_distribution": "onnxruntime",
        "onnx_runtime_version": "1.28.0",
        "build_time_utc": "2026-08-03T00:00:00Z",
        "git_commit": "unavailable",
        "preflight": {"provider": "CPUExecutionProvider"},
    }
    (tmp_path / "BUILD-REPORT-cpu.json").write_text(
        json.dumps(report), encoding="utf-8"
    )

    checksum, combined = build_portable.update_release_manifests(
        tmp_path, "1.0.0"
    )

    checksum_text = checksum.read_text(encoding="utf-8")
    assert report["archive_name"] in checksum_text
    assert report["archive_sha256"] in checksum_text
    assert "Python: 3.11.9" in checksum_text
    assert "Git commit: unavailable" in checksum_text
    assert "CPUExecutionProvider" in combined.read_text(encoding="utf-8")
