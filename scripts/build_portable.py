"""Build and audit the explicit CPU/CUDA Windows portable distributions."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Iterable, Sequence
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SPEC_PATH = PROJECT_ROOT / "packaging" / "animetagger-lite.spec"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "release"
PORTABLE_NAME = "AnimeTaggerLite"
MODEL_DIR = PROJECT_ROOT / "models" / "wd-vit-tagger-v3"
VALIDATION_DIR = PROJECT_ROOT / "validation-images"
EXPECTED_MODEL_SHA256 = (
    "35f23693620b668f4d53fd3c62bf65e40af739bc52c7eb0fbc49258b58d065b6"
)

RUNTIME_DISTRIBUTIONS = {
    "cpu": (
        "numpy",
        "Pillow",
        "pillow-heif",
        "PySide6",
        "PySide6-Essentials",
        "shiboken6",
        "onnxruntime",
    ),
    "cuda": (
        "numpy",
        "Pillow",
        "pillow-heif",
        "PySide6",
        "PySide6-Essentials",
        "shiboken6",
        "onnxruntime-gpu",
        "nvidia-cublas",
        "nvidia-cuda-nvrtc",
        "nvidia-cuda-runtime",
        "nvidia-cudnn-cu13",
        "nvidia-cufft",
        "nvidia-curand",
        "nvidia-nvjitlink",
    ),
}

# PyInstaller itself is not importable at application runtime, but its compiled
# bootloader is embedded in both executables.  Its bootloader exception and
# license therefore belong in the portable package's license inventory.
EMBEDDED_BUILD_DISTRIBUTIONS = ("PyInstaller",)

TAGGER_DISTRIBUTIONS = (
    "torch", "torchvision", "timm", "safetensors", "huggingface-hub",
    "filelock", "fsspec", "sympy", "mpmath", "networkx", "jinja2",
    "MarkupSafe", "PyYAML", "packaging", "typing-extensions", "tqdm",
    "httpx", "httpcore", "h11", "anyio", "certifi", "idna", "click",
)

CONFIRMED_QT_LICENSE_TEXTS = {
    "GPL-3.0.txt": (
        PROJECT_ROOT / "packaging" / "license-texts" / "GPL-3.0.txt",
        "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986",
    ),
    "LGPL-3.0.txt": (
        PROJECT_ROOT / "packaging" / "license-texts" / "LGPL-3.0.txt",
        "e3a994d82e644b03a792a930f574002658412f62407f5fee083f2555c5f23118",
    ),
}

FORBIDDEN_PARTS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "build",
    "pytest",
    "pytest_qt",
    "tensorflow",
    "tests",
    "validation-images",
}


def _contains_stream_marker(path: Path, markers: tuple[bytes, ...]) -> bytes | None:
    with path.open("rb") as handle:
        return _stream_marker(handle, markers)


def _stream_marker(handle, markers: tuple[bytes, ...]) -> bytes | None:
    if not markers:
        return None
    overlap = max(len(marker) for marker in markers) - 1
    previous = b""
    while True:
        chunk = handle.read(4 * 1024 * 1024)
        if not chunk:
            return None
        haystack = (previous + chunk).lower()
        for marker in markers:
            if marker in haystack:
                return marker
        previous = haystack[-overlap:] if overlap > 0 else b""


def _sensitive_build_markers() -> tuple[bytes, ...]:
    root_texts = {
        str(PROJECT_ROOT),
        str(PROJECT_ROOT).replace("\\", "/"),
        "D:\\tagger",
        "D:/tagger",
        "validation-images",
        ".final-release-smoke",
        "AnimeTaggerLite-release-smoke",
    }
    user_name = Path.home().name.strip()
    if user_name:
        root_texts.add(user_name)
    encoded: set[bytes] = set()
    for text in root_texts:
        encoded.add(text.casefold().encode("utf-8"))
        encoded.add(text.casefold().encode("utf-16le"))
    return tuple(sorted(encoded, key=len, reverse=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build one audited AnimeTagger Lite onedir portable variant."
    )
    parser.add_argument("--variant", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--onefile", action="store_true", help="Bundle the runtime into one EXE; models and editable resources stay beside it.")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--include-models", action="store_true",
                        help="Include the three existing local tagger models with SHA-256 verification.")
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Create the final ZIP after staging and audit.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Ask PyInstaller to discard its cache for this build.",
    )
    parser.add_argument(
        "--debug-console",
        action="store_true",
        help="Keep a console on the GUI executable for local diagnostics.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Verify the Python/runtime environment without building.",
    )
    return parser


def _distribution(name: str) -> metadata.Distribution | None:
    try:
        return metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return None


def verify_runtime_selection(
    variant: str,
    *,
    cpu_installed: bool,
    gpu_installed: bool,
) -> None:
    if variant == "cpu":
        if not cpu_installed or gpu_installed:
            raise RuntimeError(
                "CPU build environment must contain onnxruntime and must not "
                "contain onnxruntime-gpu."
            )
        return
    if variant == "cuda":
        if not gpu_installed or cpu_installed:
            raise RuntimeError(
                "CUDA build environment must contain onnxruntime-gpu and must "
                "not contain onnxruntime."
            )
        return
    raise RuntimeError(f"Unknown build variant: {variant!r}")


def verify_environment(variant: str) -> dict[str, str]:
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError(
            "Formal Windows builds require Python 3.11; current interpreter is "
            f"{platform.python_version()}."
        )
    if sys.maxsize <= 2**32:
        raise RuntimeError("Formal Windows builds require 64-bit Python.")
    if _distribution("PyInstaller") is None:
        raise RuntimeError("PyInstaller is missing from the build environment.")

    cpu = _distribution("onnxruntime")
    gpu = _distribution("onnxruntime-gpu")
    verify_runtime_selection(
        variant,
        cpu_installed=cpu is not None,
        gpu_installed=gpu is not None,
    )

    versions: dict[str, str] = {}
    for name in ("torch", "torchvision", "timm", "safetensors"):
        if _distribution(name) is None:
            raise RuntimeError(f"Multi-backend build requires {name}; install requirements-tagger-torch.txt.")
    for name in (*RUNTIME_DISTRIBUTIONS[variant], *TAGGER_DISTRIBUTIONS):
        distribution = _distribution(name)
        if distribution is not None:
            versions[name] = distribution.version
    for name in EMBEDDED_BUILD_DISTRIBUTIONS:
        distribution = _distribution(name)
        if distribution is not None:
            versions[name] = distribution.version
    return versions


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_preflight_command(
    label: str,
    command: Sequence[str],
    *,
    environment: dict[str, str],
) -> str:
    print(f"[preflight] {label} ...", flush=True)
    completed = subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = completed.stdout.strip()
    if output:
        print(output, flush=True)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Preflight step {label!r} failed with exit code "
            f"{completed.returncode}."
        )
    return output


def run_preflight(variant: str) -> dict[str, object]:
    """Run the non-optional formal-build gates in the active environment."""

    from app.image.image_loader import SUPPORTED_IMAGE_EXTENSIONS
    from app.inference.providers import CPU_PROVIDER, CUDA_PROVIDER, Device
    from app.inference.wd14_engine import WD14Engine

    model_path = MODEL_DIR / "model.onnx"
    tags_path = MODEL_DIR / "selected_tags.csv"
    if not model_path.is_file() or not tags_path.is_file():
        raise RuntimeError(
            "Formal build preflight requires model.onnx and selected_tags.csv "
            f"in {MODEL_DIR}."
        )
    actual_model_hash = sha256_file(model_path)
    if actual_model_hash != EXPECTED_MODEL_SHA256:
        raise RuntimeError(
            "model.onnx SHA-256 mismatch: "
            f"expected {EXPECTED_MODEL_SHA256}, got {actual_model_hash}."
        )
    if not VALIDATION_DIR.is_dir():
        raise RuntimeError(
            f"Formal build preflight requires {VALIDATION_DIR}."
        )
    images = tuple(
        sorted(
            (
                path
                for path in VALIDATION_DIR.iterdir()
                if path.is_file()
                and path.suffix.casefold() in SUPPORTED_IMAGE_EXTENSIONS
            ),
            key=lambda path: path.name.casefold(),
        )
    )
    if not 5 <= len(images) <= 20:
        raise RuntimeError(
            "Formal build preflight requires 5 to 20 user-provided validation "
            f"images; found {len(images)} in {VALIDATION_DIR}."
        )
    initial_image_hashes = {path.name: sha256_file(path) for path in images}

    environment = os.environ.copy()
    environment.update(
        {
            "ANIMETAGGER_MODEL_DIR": str(MODEL_DIR),
            "ANIMETAGGER_VALIDATION_DIR": str(VALIDATION_DIR),
            "PYTHONUTF8": "1",
            "QT_QPA_PLATFORM": "offscreen",
        }
    )
    pip_output = _run_preflight_command(
        "pip check",
        (sys.executable, "-m", "pip", "check"),
        environment=environment,
    )
    _run_preflight_command(
        "compileall",
        (
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "app",
            "tests",
            "scripts",
        ),
        environment=environment,
    )
    pytest_output = _run_preflight_command(
        "full pytest",
        (sys.executable, "-m", "pytest", "-q"),
        environment=environment,
    )
    if " skipped" in pytest_output.casefold():
        raise RuntimeError(
            "Formal build preflight does not allow skipped tests."
        )
    _run_preflight_command(
        "single-image CLI help",
        (sys.executable, "-m", "app.main", "--help"),
        environment=environment,
    )
    _run_preflight_command(
        "batch CLI help",
        (sys.executable, "-m", "app.main", "batch", "--help"),
        environment=environment,
    )
    _run_preflight_command(
        "GUI offscreen startup",
        (sys.executable, "-m", "app.ui", "--smoke-test"),
        environment=environment,
    )

    requested_device = Device.CPU if variant == "cpu" else Device.CUDA
    required_provider = CPU_PROVIDER if variant == "cpu" else CUDA_PROVIDER
    engine = WD14Engine(MODEL_DIR, device=requested_device)
    try:
        prediction = engine.predict(images[0])
    finally:
        engine.release()
    if prediction.model_info.active_provider != required_provider:
        raise RuntimeError(
            f"{variant.upper()} preflight required {required_provider}, got "
            f"{prediction.model_info.active_provider}. Silent fallback is not "
            "allowed."
        )
    final_image_hashes = {path.name: sha256_file(path) for path in images}
    if final_image_hashes != initial_image_hashes:
        raise RuntimeError("Validation image hashes changed during preflight.")

    pytest_summary = pytest_output.splitlines()[-1] if pytest_output else "passed"
    return {
        "pip_check": pip_output or "No broken requirements found.",
        "compileall": "passed",
        "pytest": pytest_summary,
        "cli_help": "passed",
        "batch_cli_help": "passed",
        "gui_offscreen": "passed",
        "provider": prediction.model_info.active_provider,
        "inference_time_ms": round(prediction.inference_seconds * 1000.0, 3),
        "output_count": prediction.model_info.output_count,
        "validation_images": len(images),
        "validation_image_hashes_unchanged": True,
        "model_sha256": actual_model_hash,
    }


def run_pyinstaller(
    variant: str,
    output_root: Path,
    clean: bool,
    *,
    debug_console: bool,
    onefile: bool = False,
) -> Path:
    work_root = output_root / "_build" / variant
    dist_root = output_root / "_pyinstaller" / variant
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--distpath",
        str(dist_root),
        "--workpath",
        str(work_root),
    ]
    if clean:
        command.append("--clean")
    command.append(str(SPEC_PATH))
    environment = os.environ.copy()
    environment["ANIMETAGGER_BUILD_VARIANT"] = variant
    environment["ANIMETAGGER_DEBUG_CONSOLE"] = "1" if debug_console else "0"
    environment["ANIMETAGGER_ONEFILE"] = "1" if onefile else "0"
    subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        check=True,
    )
    built = dist_root / PORTABLE_NAME
    if onefile:
        executable = dist_root / f"{PORTABLE_NAME}.exe"
        if not executable.is_file():
            raise RuntimeError(f"PyInstaller did not create {executable}.")
        built.mkdir(parents=True, exist_ok=True)
        shutil.copy2(executable, built / executable.name)
    if not built.is_dir():
        raise RuntimeError(f"PyInstaller did not create {built}.")
    return built


def _copy_tree_contents(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _remove_tree_within(path: Path, allowed_root: Path) -> None:
    target = Path(path).resolve(strict=False)
    root = Path(allowed_root).resolve(strict=False)
    if target == root or root not in target.parents:
        raise RuntimeError(
            f"Refusing to remove a build path outside its output root: {target}"
        )
    if target.exists():
        shutil.rmtree(target)


def _license_candidates(
    distribution: metadata.Distribution,
) -> Iterable[Path]:
    files = distribution.files or ()
    for relative in files:
        name = Path(str(relative)).name.casefold()
        parts = {part.casefold() for part in Path(str(relative)).parts}
        if name.endswith((".pyc", ".pyo")):
            continue
        if (
            name.startswith(("license", "copying", "notice", "authors"))
            or "licenses" in parts
        ):
            path = Path(distribution.locate_file(relative))
            if path.is_file():
                yield path


def stage_licenses(
    destination: Path,
    versions: dict[str, str],
) -> list[str]:
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        PROJECT_ROOT / "packaging" / "LICENSES_README.txt",
        destination / "README.txt",
    )
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if not python_license.is_file():
        raise RuntimeError(
            f"The CPython license file is missing from {sys.base_prefix}."
        )
    python_component = destination / f"CPython-{sys.version.split()[0]}"
    python_component.mkdir()
    shutil.copy2(python_license, python_component / "LICENSE.txt")
    included: list[str] = [f"CPython=={sys.version.split()[0]}"]
    for name in sorted(versions, key=str.casefold):
        distribution = metadata.distribution(name)
        component = destination / f"{name}-{distribution.version}"
        candidates = list(dict.fromkeys(_license_candidates(distribution)))
        component.mkdir(parents=True, exist_ok=True)
        used_names: set[str] = set()
        for index, source in enumerate(candidates, start=1):
            target_name = source.name
            if target_name.casefold() in used_names:
                target_name = f"{index:02d}-{target_name}"
            used_names.add(target_name.casefold())
            shutil.copy2(source, component / target_name)
        metadata_text = component / "METADATA.txt"
        metadata_text.write_text(
            "\n".join(
                (
                    f"Name: {distribution.metadata.get('Name', name)}",
                    f"Version: {distribution.version}",
                    "License-Expression: "
                    f"{distribution.metadata.get('License-Expression', '')}",
                    f"License: {distribution.metadata.get('License', '')}",
                    f"Home-page: {distribution.metadata.get('Home-page', '')}",
                )
            ).rstrip()
            + "\n",
            encoding="utf-8",
        )
        included.append(f"{name}=={distribution.version}")

    qt_distributions = {
        name: version
        for name, version in versions.items()
        if name.casefold() in {"pyside6", "pyside6-essentials", "shiboken6"}
    }
    if qt_distributions:
        qt_versions = set(qt_distributions.values())
        if len(qt_versions) != 1:
            raise RuntimeError(
                "PySide6, PySide6-Essentials and shiboken6 must use one version: "
                f"{qt_distributions!r}."
            )
        qt_version = next(iter(qt_versions))
        qt_component = destination / f"Qt-for-Python-{qt_version}"
        qt_component.mkdir(parents=True, exist_ok=True)
        for target_name, (source, expected_sha256) in (
            CONFIRMED_QT_LICENSE_TEXTS.items()
        ):
            if not source.is_file():
                raise RuntimeError(f"Confirmed Qt license text is missing: {source}.")
            actual_sha256 = sha256_file(source)
            if actual_sha256 != expected_sha256:
                raise RuntimeError(
                    f"Qt license text hash mismatch for {source}: "
                    f"expected {expected_sha256}, got {actual_sha256}."
                )
            shutil.copy2(source, qt_component / target_name)
        (qt_component / "APPLICABLE-LICENSE.txt").write_text(
            "This portable build uses the LGPL-3.0-only option declared by "
            "the installed PySide6, PySide6-Essentials and shiboken6 package "
            "metadata. LGPL-3.0 incorporates GPL-3.0 terms, so both exact "
            "standard texts are included here. The upstream wheel also "
            "contains LicenseRef-Qt-Commercial.txt; this project does not "
            "assert a Qt commercial license.\n",
            encoding="utf-8",
        )
    return included


def stage_distribution(
    built: Path,
    output_root: Path,
    variant: str,
    version: str,
    versions: dict[str, str],
    *,
    include_models: bool = False,
) -> Path:
    project_license = PROJECT_ROOT / "LICENSE"
    if not project_license.is_file():
        raise RuntimeError(
            "Project LICENSE is missing. Do not build a release until the "
            "project owner confirms the license text."
        )
    destination = (
        output_root
        / "portable"
        / portable_artifact_name(version, variant)
    )
    _remove_tree_within(destination, output_root)
    shutil.copytree(built, destination)

    # PyInstaller may collect vendor test packages (e.g. torch.fx.passes.tests).
    # Audit forbids any path segment named "tests", so strip them after copy.
    internal = destination / "_internal"
    if internal.is_dir():
        for package in ("torch", "timm", "torchvision"):
            for tests_dir in (internal / package).rglob("tests"):
                if tests_dir.is_dir():
                    shutil.rmtree(tests_dir, ignore_errors=True)

    _copy_tree_contents(PROJECT_ROOT / "resources", destination / "resources")
    shutil.copy2(PROJECT_ROOT / "打开图示审阅网站.cmd", destination / "打开图示审阅网站.cmd")
    (destination / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT_ROOT / "scripts" / "start_tag_visual_review.ps1",
                 destination / "scripts" / "start_tag_visual_review.ps1")
    model_destination = destination / "models" / "wd-vit-tagger-v3"
    model_destination.mkdir(parents=True)
    shutil.copy2(
        PROJECT_ROOT / "packaging" / "MODEL_README.txt",
        model_destination / "README.txt",
    )
    from app.inference.backends import BACKENDS, DEFAULT_BACKEND, resolve_backend_files
    model_hashes = {}
    for backend, spec in BACKENDS.items():
        target = destination / spec.directory
        target.mkdir(parents=True, exist_ok=True)
        if include_models:
            source = PROJECT_ROOT / spec.directory
            files = resolve_backend_files(source, backend)
            names = [files.model_path.name, files.tags_path.name]
            if backend == DEFAULT_BACKEND:
                names.append("config.json")
            elif backend == "pixai_v0_9":
                names.append("preprocess.json")
            for name in names:
                shutil.copy2(source / name, target / name)
                relative = (target / name).relative_to(destination).as_posix()
                model_hashes[relative] = sha256_file(source / name)
    shutil.copy2(
        PROJECT_ROOT / "packaging" / "README.portable.txt",
        destination / "README.txt",
    )
    shutil.copy2(
        PROJECT_ROOT / "THIRD_PARTY_NOTICES.md",
        destination / "THIRD_PARTY_NOTICES.txt",
    )
    shutil.copy2(
        PROJECT_ROOT / "QUICK_START.txt",
        destination / "QUICK_START.txt",
    )
    shutil.copy2(project_license, destination / "LICENSE")
    (destination / "portable.flag").write_bytes(b"")
    for relative in (
        "data/config",
        "data/logs",
        "data/batch-jobs",
        "data/temp",
    ):
        (destination / relative).mkdir(parents=True)

    license_components = stage_licenses(
        destination / "LICENSES",
        versions,
    )
    manifest = {
        "application": "AnimeTagger Lite",
        "version": version,
        "variant": variant,
        "python": sys.version.split()[0],
        "runtime_distributions": license_components,
        "model_included": include_models,
        "model_sha256": model_hashes,
        "tagger_backends": list(BACKENDS),
        "canary_torch_version": versions.get("torch"),
        "portable": True,
        "program_layout": "onedir" if (destination / "_internal").is_dir() else "onefile",
    }
    (destination / "BUILD-MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def portable_artifact_name(version: str, variant: str) -> str:
    if variant not in {"cpu", "cuda"}:
        raise ValueError(f"Unknown portable variant: {variant!r}")
    return f"AnimeTaggerLite-{version}-win64-{variant}-portable"


def audit_distribution(root: Path, variant: str, *, model_hashes: dict[str, str] | None = None, onefile: bool = False) -> dict[str, int]:
    required = (
        "AnimeTaggerLite.exe",
        "resources",
        "models/wd-vit-tagger-v3/README.txt",
        "README.txt",
        "QUICK_START.txt",
        "THIRD_PARTY_NOTICES.txt",
        "LICENSE",
        "LICENSES",
        "portable.flag",
        "打开图示审阅网站.cmd",
        "scripts/start_tag_visual_review.ps1",
        "data/config",
        "data/logs",
        "data/batch-jobs",
        "data/temp",
    )
    if not onefile:
        required += ("AnimeTaggerLiteCLI.exe", "_internal")
    missing = [relative for relative in required if not (root / relative).exists()]
    if missing:
        raise RuntimeError(f"Portable directory is missing: {missing!r}")

    forbidden: list[str] = []
    model_files: list[str] = []
    cpu_runtime: list[str] = []
    gpu_runtime: list[str] = []
    qt_webengine: list[str] = []
    foreign_icu: list[str] = []
    user_data_files: list[str] = []
    sensitive_content: list[str] = []
    markers = _sensitive_build_markers()
    files = 0
    size = 0
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        lowered_parts = {part.casefold() for part in relative.parts}
        if lowered_parts & FORBIDDEN_PARTS:
            forbidden.append(str(relative))
        if path.is_file():
            files += 1
            size += path.stat().st_size
            lower_name = path.name.casefold()
            if lower_name.endswith((".onnx", ".safetensors", ".msgpack")) or (
                lower_name == "selected_tags.csv"
            ):
                model_files.append(str(relative))
            if "qtwebengine" in lower_name:
                qt_webengine.append(str(relative))
            if lower_name == "icuuc.dll" or (
                lower_name.startswith("icudt") and lower_name.endswith(".dll")
            ):
                foreign_icu.append(str(relative))
            if relative.parts and relative.parts[0].casefold() == "data":
                user_data_files.append(str(relative))
            if lower_name == "onnxruntime_providers_cuda.dll":
                gpu_runtime.append(str(relative))
            if (
                lower_name.startswith("onnxruntime")
                and "providers_cuda" not in lower_name
            ):
                cpu_runtime.append(str(relative))
            # Compressed bytes can coincidentally spell a short username.
            # The onefile payload is audited after decompression below.
            if not (onefile and relative.as_posix() == "AnimeTaggerLite.exe") and _contains_stream_marker(path, markers) is not None:
                sensitive_content.append(str(relative))
    if forbidden:
        raise RuntimeError(f"Forbidden paths found: {forbidden[:10]!r}")
    approved_models = model_hashes or {}
    unexpected_models = [name for name in model_files if Path(name).as_posix() not in approved_models]
    if unexpected_models:
        raise RuntimeError(f"Model weights found in release: {model_files!r}")
    for relative, expected_hash in approved_models.items():
        path = (root / relative).resolve()
        if not path.is_relative_to((root / "models").resolve()):
            raise RuntimeError(f"Model path is outside models/: {relative}")
        if not path.is_file() or sha256_file(path) != expected_hash:
            raise RuntimeError(f"Bundled model SHA-256 mismatch: {relative}")
    if qt_webengine:
        raise RuntimeError(f"QtWebEngine files found in release: {qt_webengine[:10]!r}")
    if foreign_icu:
        raise RuntimeError(
            "Foreign ICU DLLs found in release: "
            f"{foreign_icu[:10]!r}"
        )
    if user_data_files:
        raise RuntimeError(
            f"Portable data directories are not empty: {user_data_files[:10]!r}"
        )
    if sensitive_content:
        raise RuntimeError(
            "Development/user path markers found in release files: "
            f"{sensitive_content[:10]!r}"
        )
    if onefile:
        from PyInstaller.archive.readers import CArchiveReader
        executable = root / "AnimeTaggerLite.exe"
        reader = CArchiveReader(str(executable))
        entries = [name.replace("\\", "/").casefold() for name in reader.toc]
        with executable.open("rb") as handle:
            prefix = handle.read(reader._start_offset)
            handle.seek(reader._end_offset)
            suffix = handle.read()
        if _stream_marker(io.BytesIO(prefix + suffix), markers):
            raise RuntimeError("Development/user path markers in EXE wrapper.")
        for name in reader.toc:
            payload = reader.extract(name)
            if payload is not None and _stream_marker(io.BytesIO(payload), markers):
                raise RuntimeError(f"Development/user path markers in embedded file: {name}")
        banned = [name for name in entries if set(name.split("/")) & FORBIDDEN_PARTS or "qtwebengine" in name]
        if banned:
            raise RuntimeError(f"Forbidden embedded entries: {banned[:10]}")
        gpu_runtime = [name for name in entries if name.endswith("onnxruntime_providers_cuda.dll")]
        cpu_runtime = [name for name in entries if "onnxruntime" in name and name.endswith((".pyd", ".dll"))]
        has_nvidia = any(name.startswith("nvidia/") for name in entries)
        if variant == "cuda" and not has_nvidia:
            raise RuntimeError("Onefile CUDA build is missing NVIDIA libraries.")
        if variant == "cpu" and has_nvidia:
            raise RuntimeError("Onefile CPU build contains NVIDIA libraries.")
    if variant == "cpu" and gpu_runtime:
        raise RuntimeError("CPU package contains a CUDA provider DLL.")
    if variant == "cpu" and (root / "_internal" / "nvidia").exists():
        raise RuntimeError("CPU package contains NVIDIA runtime files.")
    if variant == "cuda" and not gpu_runtime:
        raise RuntimeError("CUDA package does not contain its CUDA provider DLL.")
    if variant == "cuda" and not onefile and not (root / "_internal" / "nvidia").is_dir():
        raise RuntimeError("CUDA package does not contain NVIDIA runtime files.")
    if not cpu_runtime:
        raise RuntimeError("ONNX Runtime binaries were not found.")
    return {"files": files, "bytes": size}


def create_archive(root: Path, output_root: Path) -> tuple[Path, str]:
    archive = output_root / f"{root.name}.zip"
    temporary = archive.with_suffix(".zip.part")
    temporary.unlink(missing_ok=True)
    archive.unlink(missing_ok=True)
    with zipfile.ZipFile(
        temporary,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as handle:
        for directory in sorted(
            (path for path in root.rglob("*") if path.is_dir()),
            key=lambda item: str(item).casefold(),
        ):
            relative = directory.relative_to(root).as_posix().rstrip("/") + "/"
            handle.writestr(f"{root.name}/{relative}", b"")
        for path in sorted(
            (path for path in root.rglob("*") if path.is_file()),
            key=lambda item: str(item).casefold(),
        ):
            relative = path.relative_to(root).as_posix()
            handle.write(path, f"{root.name}/{relative}")
    os.replace(temporary, archive)
    digest = hashlib.sha256()
    with archive.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return archive, digest.hexdigest()


def _git_commit() -> str:
    if not (PROJECT_ROOT / ".git").exists():
        return "unavailable"
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"
    return completed.stdout.strip() or "unavailable"


def write_build_report(
    output_root: Path,
    *,
    version: str,
    variant: str,
    versions: dict[str, str],
    preflight: dict[str, object],
    portable: Path,
    audit: dict[str, int],
    archive: Path,
    archive_sha256: str,
) -> Path:
    runtime_name = "onnxruntime" if variant == "cpu" else "onnxruntime-gpu"
    report = {
        "application": "AnimeTagger Lite",
        "version": version,
        "variant": variant,
        "build_time_utc": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "python_version": platform.python_version(),
        "python_architecture": platform.architecture()[0],
        "pyinstaller_version": metadata.version("PyInstaller"),
        "onnx_runtime_distribution": runtime_name,
        "onnx_runtime_version": versions[runtime_name],
        "git_commit": _git_commit(),
        "portable_directory_name": portable.name,
        "portable_files": audit["files"],
        "portable_bytes": audit["bytes"],
        "archive_name": archive.name,
        "archive_bytes": archive.stat().st_size,
        "archive_sha256": archive_sha256,
        "runtime_distributions": versions,
        "preflight": preflight,
    }
    path = output_root / f"BUILD-REPORT-{variant}.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def update_release_manifests(output_root: Path, version: str) -> tuple[Path, Path]:
    reports: list[dict[str, object]] = []
    for path in sorted(output_root.glob("BUILD-REPORT-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if payload.get("version") == version:
            reports.append(payload)
    if not reports:
        raise RuntimeError("No build reports are available for checksum output.")

    generated = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    checksum_lines = [
        "AnimeTagger Lite release checksums",
        f"Version: {version}",
        f"Generated: {generated}",
        "",
    ]
    table_lines = [
        f"# AnimeTagger Lite {version} build report",
        "",
        f"Generated: {generated}",
        "",
        "| Variant | ZIP | Directory bytes | ZIP bytes | SHA-256 | Provider |",
        "|---|---|---:|---:|---|---|",
    ]
    for report in sorted(reports, key=lambda item: str(item["variant"])):
        variant = str(report["variant"])
        checksum_lines.extend(
            (
                f"[{variant.upper()}]",
                f"File: {report['archive_name']}",
                f"SHA-256: {report['archive_sha256']}",
                f"Build type: {variant}",
                f"Python: {report['python_version']}",
                f"PyInstaller: {report['pyinstaller_version']}",
                "ONNX Runtime: "
                f"{report['onnx_runtime_distribution']} "
                f"{report['onnx_runtime_version']}",
                f"Build time: {report['build_time_utc']}",
                f"Git commit: {report['git_commit']}",
                "",
            )
        )
        preflight = report.get("preflight", {})
        provider = (
            str(preflight.get("provider", "unavailable"))
            if isinstance(preflight, dict)
            else "unavailable"
        )
        table_lines.append(
            f"| {variant.upper()} | `{report['archive_name']}` | "
            f"{report['portable_bytes']} | {report['archive_bytes']} | "
            f"`{report['archive_sha256']}` | `{provider}` |"
        )

    checksum_path = output_root / "SHA256SUMS.txt"
    checksum_path.write_text("\n".join(checksum_lines), encoding="utf-8")
    report_path = output_root / "BUILD_REPORT.md"
    report_path.write_text("\n".join(table_lines) + "\n", encoding="utf-8")
    return checksum_path, report_path


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    from app import __version__

    version = __version__
    output_root = args.output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    versions = verify_environment(args.variant)
    if args.check_only:
        print(
            json.dumps(
                {
                    "variant": args.variant,
                    "python": platform.python_version(),
                    "architecture": platform.architecture()[0],
                    "distributions": versions,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    required_release_files = (
        PROJECT_ROOT / "LICENSE",
        PROJECT_ROOT / "QUICK_START.txt",
        PROJECT_ROOT / "THIRD_PARTY_NOTICES.md",
        SPEC_PATH,
    )
    missing_release_files = [
        str(path.relative_to(PROJECT_ROOT))
        for path in required_release_files
        if not path.is_file()
    ]
    if missing_release_files:
        raise RuntimeError(
            "Formal release inputs are missing: "
            f"{missing_release_files!r}. Do not invent a project license."
        )

    preflight = run_preflight(args.variant)
    built = run_pyinstaller(
        args.variant,
        output_root,
        args.clean,
        debug_console=args.debug_console,
        onefile=args.onefile,
    )
    portable = stage_distribution(
        built,
        output_root,
        args.variant,
        version,
        versions,
        include_models=args.include_models,
    )
    model_hashes = json.loads((portable / "BUILD-MANIFEST.json").read_text(encoding="utf-8"))["model_sha256"]
    audit = audit_distribution(portable, args.variant, model_hashes=model_hashes, onefile=args.onefile)
    print(
        f"Portable: {portable}\n"
        f"Files: {audit['files']}\n"
        f"Bytes: {audit['bytes']}"
    )
    if args.archive:
        archive, digest = create_archive(portable, output_root)
        report_path = write_build_report(
            output_root,
            version=version,
            variant=args.variant,
            versions=versions,
            preflight=preflight,
            portable=portable,
            audit=audit,
            archive=archive,
            archive_sha256=digest,
        )
        checksum_path, combined_report = update_release_manifests(
            output_root,
            version,
        )
        print(
            f"Archive: {archive}\n"
            f"Archive bytes: {archive.stat().st_size}\n"
            f"SHA-256: {digest}\n"
            f"Build report: {report_path}\n"
            f"Checksums: {checksum_path}\n"
            f"Combined report: {combined_report}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
