"""Create a verified portable archive without model weights or private state.

The input directories are read only. Large programs belong in GitHub Releases;
the JSON sidecar records their hashes for verification after downloading.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
from typing import BinaryIO
import zipfile


PRIVATE_ROOTS = {"data", "config", "logs", "temp", "tmp", "backups"}
WEIGHT_SUFFIXES = {".onnx", ".safetensors", ".ckpt", ".pt", ".pth", ".msgpack"}
EMPTY_DATA_DIRS = ("data/config", "data/logs", "data/batch-jobs", "data/temp")
ASSET_LIMIT = 2 * 1024**3


def is_model_weight(relative: PurePosixPath) -> bool:
    suffix = relative.suffix.casefold()
    return (
        suffix in WEIGHT_SUFFIXES
        or relative.name.casefold().endswith((".onnx.data", ".onnx_data"))
        or (suffix == ".bin" and (
            "models" in {p.casefold() for p in relative.parts}
            or relative.name.casefold().startswith(("model", "pytorch_model"))
        ))
    )


def omitted_reason(relative: PurePosixPath) -> str | None:
    if relative.parts[0].casefold() in PRIVATE_ROOTS:
        return "private_state"
    if {p.casefold() for p in relative.parts} & {"__pycache__", ".pytest_cache", ".git"}:
        return "cache"
    if is_model_weight(relative):
        return "model_weight"
    return None


def safe_files(root: Path) -> dict[str, Path]:
    found = {}
    for current, directories, names in os.walk(root, followlinks=False):
        for name in directories + names:
            path = Path(current) / name
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError(f"Refusing a symlink or reparse point: {path}")
        for name in names:
            path = Path(current) / name
            found[path.relative_to(root).as_posix()] = path
    return found


def write_stream(source: BinaryIO, destination: BinaryIO) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
        destination.write(chunk)
        digest.update(chunk)
        size += len(chunk)
    return size, digest.hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def zip_info(name: str, *, binary: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    # Onefile EXEs already contain compressed runtime libraries. Keeping these
    # entries uncompressed avoids recompressing gigabytes without benefit.
    info.compress_type = zipfile.ZIP_STORED if binary else zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def create_archive(
    package: Path, output: Path, *, version: str, tag: str,
    source_commit: str | None = None, source_status: str = "portable-only",
    supplemental: Path | None = None,
) -> dict:
    package = package.resolve()
    output = output.resolve()
    if output.is_relative_to(package):
        raise ValueError("The output must be outside the read-only package")
    if output.suffix.casefold() != ".zip" or output.exists():
        raise ValueError("The output must be a new .zip file")
    if not package.is_dir() or not (package / "AnimeTaggerLite.exe").is_file():
        raise ValueError("The input is not an AnimeTagger portable directory")
    files = safe_files(package)
    supplemental_count = 0
    if supplemental and supplemental.is_dir():
        for relative, path in safe_files(supplemental).items():
            if relative not in files:
                files[relative] = path
                supplemental_count += 1
    excluded = {"model_weight": [], "private_state": 0, "cache": 0}
    included = {}
    for relative, path in sorted(files.items()):
        reason = omitted_reason(PurePosixPath(relative))
        if reason == "model_weight":
            excluded[reason].append({"path": relative, "bytes": path.stat().st_size})
        elif reason:
            excluded[reason] += 1
        else:
            included[relative] = path
    required = {
        "AnimeTaggerLite.exe", "BUILD-MANIFEST.json", "LICENSE", "README.txt",
        "QUICK_START.txt", "THIRD_PARTY_NOTICES.txt", "portable.flag",
        "resources/default_settings.json", "resources/tag_categories.json",
        "models/wd-vit-tagger-v3/README.txt",
    }
    missing = required - included.keys()
    if missing:
        raise ValueError(f"Incomplete package: {sorted(missing)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    sidecar = output.with_suffix(".manifest.json")
    if sidecar.exists():
        raise FileExistsError(sidecar)
    root_name = output.stem
    records = []
    weight_paths = "\n".join(f"- {entry['path']}" for entry in excluded["model_weight"])
    model_note = (
        f"AnimeTagger Lite {version} - 模型准备说明\n\n"
        "本存档不包含模型权重。程序、运行库、模型配置和词表均已保留。\n"
        "请将已有的对应模型权重放回以下相对路径，或在软件设置中选择模型目录：\n"
        f"{weight_paths}\n\n"
        "WD v3：SmilingWolf/wd-vit-tagger-v3\n"
        "Canary：ashen-sensored/wd-eva02-tagger-2026-canary\n"
        "PixAI：deepghs/pixai-tagger-v0.9-onnx\n"
        "如有不同的上游 revision，请以随包模型配置、项目后端说明和你保存的原始模型为准。\n"
        "程序不自动下载模型。私人配置、日志、图片和审阅记录未随存档分发。\n"
        "完整程序在同一私有仓库的 Releases 中；ARCHIVE-MANIFEST.json 记录文件校验值。\n"
    ).encode("utf-8")
    prefix = (
        "【本次存档分发说明】此包已移除模型权重和个人运行数据。\n"
        "首次使用请先阅读 MODEL-SETUP.txt，补齐模型或选择已有模型目录。\n"
        "下面保留原版说明，原版关于内置模型的描述不适用于此无模型存档。\n\n"
    ).encode("utf-8")
    with zipfile.ZipFile(output, "x", allowZip64=True) as archive:
        for relative, path in included.items():
            before = path.stat()
            original_sha = None
            transformed = None
            if relative == "BUILD-MANIFEST.json":
                original = path.read_bytes()
                original_sha = hashlib.sha256(original).hexdigest()
                build = json.loads(original)
                build["model_included"] = False
                build["model_sha256"] = {}
                build["archive_tag"] = tag
                build["model_weights_excluded"] = [entry["path"] for entry in excluded["model_weight"]]
                transformed = (json.dumps(build, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            elif relative in {"README.txt", "QUICK_START.txt"}:
                original = path.read_bytes()
                original_sha = hashlib.sha256(original).hexdigest()
                transformed = prefix + original
            info = zip_info(f"{root_name}/{relative}", binary=relative.endswith(".exe") and before.st_size > 100 * 1024**2)
            if transformed is None:
                with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
                    size, digest = write_stream(source, target)
            else:
                archive.writestr(info, transformed)
                size, digest = len(transformed), hashlib.sha256(transformed).hexdigest()
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RuntimeError(f"Input changed while archiving: {relative}")
            record = {"path": relative, "bytes": size, "sha256": digest}
            if original_sha:
                record["original_sha256"] = original_sha
            records.append(record)
        archive.writestr(zip_info(f"{root_name}/MODEL-SETUP.txt"), model_note)
        records.append({"path": "MODEL-SETUP.txt", "bytes": len(model_note), "sha256": hashlib.sha256(model_note).hexdigest()})
        for relative in EMPTY_DATA_DIRS:
            archive.writestr(f"{root_name}/{relative}/", b"")
        manifest = {
            "schema": 1, "application": "AnimeTagger Lite", "version": version,
            "tag": tag, "variant": "cuda", "model_weights_included": False,
            "source_commit": source_commit, "source_status": source_status,
            "omitted_model_weights": excluded["model_weight"],
            "omitted_private_files": excluded["private_state"],
            "omitted_cache_files": excluded["cache"],
            "supplemental_files_restored_from_git": supplemental_count,
            "files": records,
        }
        archive.writestr(zip_info(f"{root_name}/ARCHIVE-MANIFEST.json"), json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
    if output.stat().st_size >= ASSET_LIMIT:
        raise ValueError("Archive exceeds the GitHub Releases 2 GiB asset limit")
    # The outer hash covers the complete ZIP, including its internal manifest.
    manifest["archive"] = {"name": output.name, "bytes": output.stat().st_size, "sha256": file_digest(output)}
    sidecar.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--source-commit")
    parser.add_argument("--source-status", default="portable-only")
    parser.add_argument("--supplemental", type=Path)
    args = parser.parse_args()
    manifest = create_archive(args.package, args.output, version=args.version, tag=args.tag, source_commit=args.source_commit, source_status=args.source_status, supplemental=args.supplemental)
    print(json.dumps({"tag": manifest["tag"], "archive": manifest["archive"], "files": len(manifest["files"]), "omitted_private_files": manifest["omitted_private_files"]}, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
