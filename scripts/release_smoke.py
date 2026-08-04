"""Run an isolated, real-model smoke test against one portable release ZIP."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Sequence
import zipfile

from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SMOKE_NAMES = {"AnimeTaggerLite-release-smoke", ".final-release-smoke"}


class SmokeFailure(RuntimeError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--variant", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--validation-dir", type=Path, required=True)
    parser.add_argument(
        "--smoke-root",
        type=Path,
        default=Path(r"D:\AnimeTaggerLite-release-smoke"),
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--keep", action="store_true")
    return parser


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_smoke_root(path: Path) -> Path:
    resolved = Path(path).resolve(strict=False)
    if resolved.name not in ALLOWED_SMOKE_NAMES:
        raise SmokeFailure(
            "Refusing to clean an unrecognized smoke root: " f"{resolved}"
        )
    if resolved == PROJECT_ROOT or PROJECT_ROOT in resolved.parents:
        if resolved != PROJECT_ROOT / ".final-release-smoke":
            raise SmokeFailure(
                f"Refusing an unsafe project-contained smoke root: {resolved}"
            )
    return resolved


def _clean_smoke_root(root: Path) -> None:
    resolved = _validate_smoke_root(root)
    if resolved.exists():
        shutil.rmtree(resolved)


def _decode_output(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _scrubbed_environment(temp_dir: Path) -> dict[str, str]:
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    path_parts = (
        system_root / "System32",
        system_root,
        system_root / "System32" / "Wbem",
    )
    return {
        "COMSPEC": str(system_root / "System32" / "cmd.exe"),
        "PATH": os.pathsep.join(str(path) for path in path_parts),
        "SystemRoot": str(system_root),
        "WINDIR": str(system_root),
        "TEMP": str(temp_dir),
        "TMP": str(temp_dir),
        "QT_QPA_PLATFORM": "offscreen",
        "PYTHONHOME": "",
        "PYTHONPATH": "",
        "VIRTUAL_ENV": "",
    }


def _run(
    label: str,
    command: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout: int = 180,
    expected_code: int = 0,
) -> str:
    print(f"[release-smoke] {label}", flush=True)
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    output = _decode_output(completed.stdout).strip()
    if output:
        print(output, flush=True)
    if completed.returncode != expected_code:
        raise SmokeFailure(
            f"{label} returned {completed.returncode}, expected "
            f"{expected_code}. Output: {output[-1000:]}"
        )
    return output


def _assert_no_processes() -> None:
    completed = subprocess.run(
        ["tasklist.exe", "/FO", "CSV", "/NH"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    output = _decode_output(completed.stdout).casefold()
    for executable in ("animetaggerlite.exe", "animetaggerlitecli.exe"):
        if f'"{executable}"' in output:
            raise SmokeFailure(f"Residual release process detected: {executable}")


def _prepare_images(source: Path, destination: Path) -> tuple[Path, ...]:
    supported = {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
        ".gif",
        ".tif",
        ".tiff",
        ".heic",
        ".heif",
        ".avif",
    }
    originals = tuple(
        sorted(
            (
                path
                for path in source.iterdir()
                if path.is_file() and path.suffix.casefold() in supported
            ),
            key=lambda path: path.name.casefold(),
        )
    )
    if not 5 <= len(originals) <= 20:
        raise SmokeFailure(
            f"Expected 5 to 20 validation images in {source}, got {len(originals)}."
        )
    originals_dir = destination / "原始副本"
    originals_dir.mkdir(parents=True)
    copied: list[Path] = []
    for index, path in enumerate(originals, start=1):
        nested = originals_dir / ("子目录" if index % 2 == 0 else "")
        nested.mkdir(parents=True, exist_ok=True)
        target = nested / f"角色 图像 {index}{path.suffix.casefold()}"
        shutil.copy2(path, target)
        copied.append(target)

    format_dir = destination / "格式 空格 中文"
    format_dir.mkdir(parents=True)
    with Image.open(originals[0]) as opened:
        rgb = opened.convert("RGB")
        rgb.save(format_dir / "动漫样本.jpg", format="JPEG", quality=95)
        rgb.save(format_dir / "动漫样本.webp", format="WEBP", quality=95)
        rgba = rgb.convert("RGBA")
        alpha = Image.new("L", rgba.size, 220)
        rgba.putalpha(alpha)
        rgba.save(format_dir / "透明 动漫样本.png", format="PNG")
        rgb.save(format_dir / "动漫样本.avif", format="AVIF", quality=90)
        try:
            from pillow_heif import from_pillow
        except ImportError as exc:
            raise SmokeFailure(
                "pillow-heif is unavailable for legal HEIC/HEIF derivatives."
            ) from exc
        from_pillow(rgb).save(format_dir / "动漫样本.heic", quality=90)
        from_pillow(rgb).save(format_dir / "动漫样本.heif", quality=90)
    return tuple(copied) + tuple(sorted(format_dir.iterdir()))


def _extract_archive(archive: Path, destination: Path) -> Path:
    if not archive.is_file():
        raise SmokeFailure(f"Release archive does not exist: {archive}")
    with zipfile.ZipFile(archive, "r") as handle:
        names = tuple(handle.namelist())
        if not names:
            raise SmokeFailure("Release ZIP is empty.")
        for name in names:
            normalized = name.replace("\\", "/")
            path = Path(normalized)
            if path.is_absolute() or ".." in path.parts:
                raise SmokeFailure(f"Unsafe ZIP entry: {name}")
        handle.extractall(destination)
    roots = [path for path in destination.iterdir() if path.is_dir()]
    if len(roots) != 1:
        raise SmokeFailure(f"Expected one top-level portable directory, got {roots!r}")
    return roots[0]


def _assert_prompt_json(
    path: Path,
    *,
    version: str,
    expected_provider: str,
) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("app_version") != version:
        raise SmokeFailure(
            f"JSON app_version mismatch: {payload.get('app_version')!r}"
        )
    if payload.get("execution_provider") != expected_provider:
        raise SmokeFailure(
            "Release inference provider mismatch: "
            f"{payload.get('execution_provider')!r}"
        )
    if not str(payload.get("positive_prompt", "")).strip():
        raise SmokeFailure("Release JSON has an empty positive prompt.")
    if not str(payload.get("negative_prompt", "")).strip():
        raise SmokeFailure("Release JSON has an empty negative prompt.")
    if len(payload.get("raw_tags", [])) != 10861:
        raise SmokeFailure("Release JSON raw tag count is not 10,861.")
    return payload


def run_smoke(args: argparse.Namespace) -> dict[str, object]:
    smoke_root = _validate_smoke_root(args.smoke_root)
    _clean_smoke_root(smoke_root)
    smoke_root.mkdir(parents=True)
    work_root = smoke_root / args.variant
    extract_root = work_root / "extracted"
    input_root = work_root / "inputs"
    output_root = work_root / "outputs"
    temp_root = work_root / "temp"
    for path in (extract_root, input_root, output_root, temp_root):
        path.mkdir(parents=True, exist_ok=True)

    validation_dir = args.validation_dir.resolve(strict=True)
    original_hashes = {
        path.name: sha256_file(path)
        for path in validation_dir.iterdir()
        if path.is_file()
    }
    prepared_images = _prepare_images(validation_dir, input_root)
    portable = _extract_archive(args.archive.resolve(strict=True), extract_root)
    gui = portable / "AnimeTaggerLite.exe"
    cli = portable / "AnimeTaggerLiteCLI.exe"
    if not gui.is_file() or not cli.is_file():
        raise SmokeFailure("Portable executables are missing.")

    model_destination = portable / "models" / "wd-vit-tagger-v3"
    if (model_destination / "model.onnx").exists() or (
        model_destination / "selected_tags.csv"
    ).exists():
        raise SmokeFailure("Release ZIP unexpectedly contains model files.")
    environment = _scrubbed_environment(temp_root)
    version_output = _run(
        "CLI version",
        (str(cli), "--version"),
        cwd=work_root,
        environment=environment,
    )
    if args.version not in version_output:
        raise SmokeFailure(f"CLI did not report version {args.version}.")
    batch_version = _run(
        "batch CLI version",
        (str(cli), "batch", "--version"),
        cwd=work_root,
        environment=environment,
    )
    if args.version not in batch_version:
        raise SmokeFailure(f"Batch CLI did not report version {args.version}.")
    _run(
        "CLI help",
        (str(cli), "--help"),
        cwd=work_root,
        environment=environment,
    )
    _run(
        "batch CLI help",
        (str(cli), "batch", "--help"),
        cwd=work_root,
        environment=environment,
    )
    _run(
        "no-model GUI startup",
        (str(gui), "--smoke-test"),
        cwd=work_root,
        environment=environment,
    )
    _assert_no_processes()

    source_model = args.model_dir.resolve(strict=True)
    model_destination.mkdir(parents=True, exist_ok=True)
    for filename in ("model.onnx", "selected_tags.csv"):
        source_file = source_model / filename
        if not source_file.is_file():
            raise SmokeFailure(f"Model input is missing: {source_file}")
        shutil.copy2(source_file, model_destination / filename)

    expected_provider = (
        "CPUExecutionProvider"
        if args.variant == "cpu"
        else "CUDAExecutionProvider"
    )
    device = args.variant
    format_results: dict[str, str] = {}
    for image in prepared_images:
        if image.parent.name != "格式 空格 中文" and image != prepared_images[0]:
            continue
        output = output_root / f"{image.stem}-{image.suffix[1:]}.json"
        _run(
            f"real inference {image.suffix.casefold()}",
            (
                str(cli),
                str(image),
                "--model-dir",
                str(model_destination),
                "--device",
                device,
                "--profile",
                "anime",
                "--negative-mode",
                "basic",
                "--output-format",
                "json",
                "--output",
                str(output),
            ),
            cwd=work_root,
            environment=environment,
            timeout=300,
        )
        payload = _assert_prompt_json(
            output,
            version=args.version,
            expected_provider=expected_provider,
        )
        format_results[image.name] = str(
            payload["execution_provider"]
        )

    prompt_txt = output_root / "正负 提示词.txt"
    _run(
        "positive/negative TXT export",
        (
            str(cli),
            str(prepared_images[0]),
            "--model-dir",
            str(model_destination),
            "--device",
            device,
            "--negative-mode",
            "basic",
            "--output-format",
            "prompt-txt",
            "--output",
            str(prompt_txt),
        ),
        cwd=work_root,
        environment=environment,
        timeout=300,
    )
    prompt_text = prompt_txt.read_text(encoding="utf-8")
    if "Positive:" not in prompt_text or "Negative:" not in prompt_text:
        raise SmokeFailure("Positive/negative TXT headings are missing.")

    batch_source = input_root / "原始副本"
    batch_output = output_root / "批处理 镜像"
    manifest = output_root / "batch.manifest.json"
    csv_path = output_root / "batch.csv"
    _run(
        "real recursive LoRA batch",
        (
            str(cli),
            "batch",
            str(batch_source),
            "--recursive",
            "--model-dir",
            str(model_destination),
            "--device",
            device,
            "--lora",
            "--trigger-word",
            "release_token",
            "--trigger-word-position",
            "first",
            "--output-mode",
            "mirror",
            "--output-root",
            str(batch_output),
            "--export",
            "txt",
            "--export",
            "json",
            "--export",
            "csv",
            "--summary-json",
            "--manifest-path",
            str(manifest),
            "--csv-path",
            str(csv_path),
        ),
        cwd=work_root,
        environment=environment,
        timeout=600,
    )
    captions = tuple(batch_output.rglob("*.txt"))
    json_outputs = tuple(batch_output.rglob("*.json"))
    if len(captions) != len(original_hashes) or len(json_outputs) != len(
        original_hashes
    ):
        raise SmokeFailure(
            "Batch output count mismatch: "
            f"{len(captions)} TXT, {len(json_outputs)} JSON, "
            f"{len(original_hashes)} inputs."
        )
    if not manifest.is_file() or not csv_path.is_file():
        raise SmokeFailure("Batch Manifest or CSV is missing.")
    if any(
        not path.read_text(encoding="utf-8").startswith("release_token")
        for path in captions
    ):
        raise SmokeFailure("LoRA trigger word is not first in every caption.")

    _run(
        "model-configured GUI restart",
        (str(gui), "--smoke-test"),
        cwd=work_root,
        environment=environment,
    )
    _assert_no_processes()
    if not (portable / "data" / "config" / "ui.ini").is_file():
        raise SmokeFailure("Portable UI state was not persisted to data/config/ui.ini.")

    final_hashes = {
        path.name: sha256_file(path)
        for path in validation_dir.iterdir()
        if path.is_file()
    }
    if final_hashes != original_hashes:
        raise SmokeFailure("Original validation image hashes changed.")
    leftovers = tuple(work_root.rglob("*.animetagger.tmp")) + tuple(
        work_root.rglob("*.part")
    )
    if leftovers:
        raise SmokeFailure(f"Temporary output files remain: {leftovers[:10]!r}")

    return {
        "status": "passed",
        "version": args.version,
        "variant": args.variant,
        "archive": args.archive.name,
        "archive_sha256": sha256_file(args.archive),
        "smoke_time_utc": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "cwd_is_source": work_root.resolve() == PROJECT_ROOT,
        "system_python_required": False,
        "source_resources_required": False,
        "no_model_gui": "passed",
        "model_validation_and_inference": "passed",
        "provider": expected_provider,
        "format_providers": format_results,
        "transparent_png": "passed",
        "heic_heif_avif": "passed",
        "positive_negative_txt": "passed",
        "batch_images": len(original_hashes),
        "lora_caption": "passed",
        "csv": "passed",
        "manifest": "passed",
        "settings_persistence": "passed",
        "original_hashes_unchanged": True,
        "temporary_files": 0,
        "residual_processes": 0,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report_path = args.report.resolve(strict=False)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = run_smoke(args)
    except Exception as exc:
        failure = {
            "status": "failed",
            "version": args.version,
            "variant": args.variant,
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }
        report_path.write_text(
            json.dumps(failure, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Release smoke failed: {exc}", file=sys.stderr)
        return 1
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not args.keep:
        _clean_smoke_root(args.smoke_root)
    print(f"Release smoke passed. Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
