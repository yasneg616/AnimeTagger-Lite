"""Download and verify the two official WD ViT Tagger v3 inference files.

This is an explicit, developer/user-invoked utility.  AnimeTagger Lite never
imports or runs it during GUI/CLI startup or model loading.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import gc
import hashlib
import http.client
import os
from pathlib import Path
import socket
import sys
import time
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import __version__


REPOSITORY = "SmilingWolf/wd-vit-tagger-v3"
REVISION = "7f6b584d0bd3f55c4531f14ba3d4761b2bccdc0f"
MODEL_SHA256 = "35f23693620b668f4d53fd3c62bf65e40af739bc52c7eb0fbc49258b58d065b6"
OFFICIAL_RESOLVE_BASE = f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}"
DEFAULT_OUTPUT_DIR = (
    PROJECT_ROOT / "models" / "wd-vit-tagger-v3"
)

MODEL_MIN_BYTES = 350_000_000
MODEL_MAX_BYTES = 430_000_000
CSV_MIN_BYTES = 10_000
CSV_MAX_BYTES = 2_000_000
READ_CHUNK_BYTES = 4 * 1024 * 1024
MAX_DOWNLOAD_ATTEMPTS = 3
NETWORK_TIMEOUT_SECONDS = 60

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_NETWORK = 3
EXIT_VERIFY = 4
EXIT_FILESYSTEM = 5


class DownloadError(RuntimeError):
    """The official download could not complete."""


class VerificationError(RuntimeError):
    """A downloaded or existing file failed integrity validation."""


class FileOperationError(RuntimeError):
    """A local filesystem operation failed."""


@dataclass(frozen=True, slots=True)
class ModelValidation:
    size: int
    sha256: str
    input_name: str
    input_shape: tuple[object, ...]
    output_name: str
    output_shape: tuple[object, ...]
    output_count: int
    providers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CsvValidation:
    size: int
    sha256: str
    tag_count: int
    category_ids: tuple[int, ...]
    fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FileOutcome:
    path: Path
    size: int
    sha256: str
    retries: int
    skipped: bool


def official_url(filename: str) -> str:
    if filename not in {"model.onnx", "selected_tags.csv"}:
        raise ValueError(f"不允许下载未授权文件：{filename}")
    return f"{OFFICIAL_RESOLVE_BASE}/{filename}?download=true"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as handle:
            while chunk := handle.read(READ_CHUNK_BYTES):
                digest.update(chunk)
    except OSError as exc:
        raise FileOperationError(f"无法读取文件并计算 SHA-256：{path}（{exc}）") from exc
    return digest.hexdigest()


def _payload_problem(path: Path) -> str | None:
    """Identify common error pages and pointer payloads without parsing binaries."""

    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            prefix = handle.read(8192)
    except OSError as exc:
        raise FileOperationError(f"无法检查文件内容：{path}（{exc}）") from exc
    # Error pages can carry an UTF-8 BOM before their first visible byte.
    stripped = prefix.lstrip(b"\xef\xbb\xbf \t\r\n")
    lowered = stripped.lower()
    if lowered.startswith((b"<!doctype html", b"<html", b"<head", b"<body")):
        return "HTML 错误页面"
    if b"version https://git-lfs.github.com/spec/v1" in lowered:
        return "Git LFS 指针"
    if size < 64 * 1024 and (
        b"xet://" in lowered
        or (
            b"xet" in lowered
            and (b"pointer" in lowered or b"version https://" in lowered)
        )
    ):
        return "Xet 指针文本"
    if lowered.startswith((b"{", b"[")):
        return "JSON 错误响应"
    return None


def _static_output_count(shape: Sequence[object]) -> int:
    if len(shape) != 2:
        raise VerificationError(f"ONNX 输出应为二维张量，实际形状：{tuple(shape)!r}")
    value = shape[1]
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise VerificationError(f"ONNX 输出标签数不是固定正整数：{value!r}")
    return value


def verify_model_file(path: Path) -> ModelValidation:
    source = Path(path)
    problem = _payload_problem(source)
    if problem:
        raise VerificationError(f"model.onnx 实际是{problem}：{source}")
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise FileOperationError(f"无法读取 model.onnx 大小：{source}（{exc}）") from exc
    actual_hash = sha256_file(source)
    if actual_hash != MODEL_SHA256:
        raise VerificationError(
            "model.onnx SHA-256 不匹配；"
            f"实际 SHA-256={actual_hash}；实际大小={size} bytes；文件={source}"
        )
    if not MODEL_MIN_BYTES <= size <= MODEL_MAX_BYTES:
        raise VerificationError(
            "model.onnx 大小超出约 379 MB 的合理范围；"
            f"实际大小={size} bytes；SHA-256={actual_hash}"
        )

    try:
        import onnxruntime
    except ImportError as exc:
        raise VerificationError(
            "缺少 onnxruntime，无法验证 ONNX 图和创建真实 Session。"
        ) from exc

    options = onnxruntime.SessionOptions()
    options.log_severity_level = 3
    session = None
    try:
        session = onnxruntime.InferenceSession(
            str(source),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        inputs = session.get_inputs()
        outputs = session.get_outputs()
        if len(inputs) != 1 or len(outputs) != 1:
            raise VerificationError(
                "WD14 ONNX 应各有一个输入和输出；"
                f"实际输入={len(inputs)}，输出={len(outputs)}"
            )
        input_node = inputs[0]
        output_node = outputs[0]
        if input_node.type != "tensor(float)" or output_node.type != "tensor(float)":
            raise VerificationError(
                "WD14 ONNX 输入/输出类型应为 tensor(float)；"
                f"实际输入={input_node.type!r}，输出={output_node.type!r}"
            )
        input_shape = tuple(input_node.shape)
        if (
            len(input_shape) != 4
            or input_shape[1] != input_shape[2]
            or input_shape[3] != 3
        ):
            raise VerificationError(
                f"WD14 ONNX 输入应为 NHWC [N,S,S,3]，实际={input_shape!r}"
            )
        output_shape = tuple(output_node.shape)
        output_count = _static_output_count(output_shape)
        providers = tuple(session.get_providers())
        return ModelValidation(
            size=size,
            sha256=actual_hash,
            input_name=input_node.name,
            input_shape=input_shape,
            output_name=output_node.name,
            output_shape=output_shape,
            output_count=output_count,
            providers=providers,
        )
    except VerificationError:
        raise
    except Exception as exc:
        text = " ".join(str(exc).split())[:500]
        raise VerificationError(
            f"ONNX Runtime 无法创建真实 Session 或解析模型图：{text}"
        ) from exc
    finally:
        if session is not None:
            del session
        gc.collect()


def verify_csv_file(path: Path) -> CsvValidation:
    source = Path(path)
    problem = _payload_problem(source)
    if problem:
        raise VerificationError(f"selected_tags.csv 实际是{problem}：{source}")
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise FileOperationError(
            f"无法读取 selected_tags.csv 大小：{source}（{exc}）"
        ) from exc
    if not CSV_MIN_BYTES <= size <= CSV_MAX_BYTES:
        raise VerificationError(
            "selected_tags.csv 大小异常，可能为空或明显截断；"
            f"实际大小={size} bytes"
        )
    try:
        text = source.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise VerificationError(
            f"selected_tags.csv 不能按 UTF-8 读取：{source}（{exc}）"
        ) from exc
    lines = text.splitlines()
    if not lines or any(not line.strip() for line in lines):
        raise VerificationError("selected_tags.csv 包含整体空行或没有内容。")

    try:
        with source.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = tuple(
                field.strip() for field in (reader.fieldnames or ()) if field
            )
            missing = {"name", "category"} - set(fields)
            if missing:
                raise VerificationError(
                    "selected_tags.csv 缺少项目预期字段："
                    + ", ".join(sorted(missing))
                )
            tags = 0
            categories: set[int] = set()
            for row_number, row in enumerate(reader, start=2):
                if None in row:
                    raise VerificationError(
                        f"selected_tags.csv 第 {row_number} 行列数异常。"
                    )
                name = (row.get("name") or "").strip()
                category_text = (row.get("category") or "").strip()
                if not name:
                    raise VerificationError(
                        f"selected_tags.csv 第 {row_number} 行标签名称为空。"
                    )
                try:
                    categories.add(int(category_text))
                except ValueError as exc:
                    raise VerificationError(
                        f"selected_tags.csv 第 {row_number} 行 category 非整数："
                        f"{category_text!r}"
                    ) from exc
                if "tag_id" in fields:
                    try:
                        int((row.get("tag_id") or "").strip())
                    except ValueError as exc:
                        raise VerificationError(
                            f"selected_tags.csv 第 {row_number} 行 tag_id 非整数。"
                        ) from exc
                tags += 1
    except VerificationError:
        raise
    except (OSError, csv.Error) as exc:
        raise VerificationError(f"selected_tags.csv 解析失败：{exc}") from exc

    if tags < 1_000:
        raise VerificationError(
            f"selected_tags.csv 只有 {tags} 条标签，疑似明显截断。"
        )
    required_categories = {0, 4, 9}
    if not required_categories.issubset(categories):
        raise VerificationError(
            "selected_tags.csv 无法区分 general、character、rating；"
            f"检测到 category={sorted(categories)}"
        )
    return CsvValidation(
        size=size,
        sha256=sha256_file(source),
        tag_count=tags,
        category_ids=tuple(sorted(categories)),
        fields=fields,
    )


def verify_pair(
    model: ModelValidation,
    tags: CsvValidation,
) -> None:
    if model.output_count != tags.tag_count:
        raise VerificationError(
            "模型输出标签数量与 selected_tags.csv 不一致；"
            f"模型={model.output_count}，CSV={tags.tag_count}。"
            "不会裁剪数组或忽略标签。"
        )


def next_invalid_path(target: Path) -> Path:
    first = target.with_name(f"{target.name}.invalid")
    if not first.exists():
        return first
    index = 1
    while True:
        candidate = target.with_name(f"{target.name}.invalid.{index}")
        if not candidate.exists():
            return candidate
        index += 1


def _preserve_invalid(path: Path, target: Path) -> Path:
    diagnostic = next_invalid_path(target)
    try:
        path.replace(diagnostic)
    except OSError as exc:
        raise FileOperationError(
            f"无法保留异常文件：{path} -> {diagnostic}（{exc}）"
        ) from exc
    return diagnostic


def _download_attempt(url: str, part: Path, filename: str) -> None:
    try:
        offset = part.stat().st_size if part.exists() else 0
    except OSError as exc:
        raise FileOperationError(f"无法检查临时文件：{part}（{exc}）") from exc
    headers = {
        "User-Agent": f"AnimeTagger-Lite-model-preparation/{__version__}",
        "Accept-Encoding": "identity",
    }
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = Request(url, headers=headers, method="GET")
    try:
        response = urlopen(request, timeout=NETWORK_TIMEOUT_SECONDS)
    except HTTPError as exc:
        if exc.code == 416 and part.exists():
            try:
                part.unlink()
            except OSError as cleanup_error:
                raise FileOperationError(
                    f"Range 被拒绝且无法清理临时文件：{part}（{cleanup_error}）"
                ) from cleanup_error
        raise DownloadError(f"HTTP {exc.code}：{exc.reason}") from exc
    except URLError as exc:
        raise DownloadError(f"网络连接失败：{exc.reason}") from exc
    except (TimeoutError, socket.timeout) as exc:
        raise DownloadError(
            f"网络连接超时（{NETWORK_TIMEOUT_SECONDS} 秒）"
        ) from exc

    with response:
        status = getattr(response, "status", response.getcode())
        if status not in {200, 206}:
            raise DownloadError(f"官方服务器返回未预期 HTTP 状态：{status}")
        if offset and status == 206:
            content_range = response.headers.get("Content-Range", "")
            if not content_range.startswith(f"bytes {offset}-"):
                raise DownloadError(
                    "断点续传响应范围不匹配："
                    f"请求起点={offset}，Content-Range={content_range!r}"
                )
            mode = "ab"
        else:
            offset = 0
            mode = "wb"
        length_text = response.headers.get("Content-Length")
        try:
            remaining = int(length_text) if length_text else None
        except ValueError:
            remaining = None
        total = offset + remaining if remaining is not None else None
        downloaded = offset
        last_update = 0.0
        try:
            with part.open(mode) as handle:
                while True:
                    try:
                        chunk = response.read(READ_CHUNK_BYTES)
                    except (
                        OSError,
                        http.client.HTTPException,
                        TimeoutError,
                        socket.timeout,
                    ) as exc:
                        raise DownloadError(f"下载流中断：{exc}") from exc
                    if not chunk:
                        break
                    try:
                        handle.write(chunk)
                    except OSError as exc:
                        raise FileOperationError(
                            f"无法写入临时文件：{part}（{exc}）"
                        ) from exc
                    downloaded += len(chunk)
                    now = time.monotonic()
                    if now - last_update >= 0.5:
                        if total:
                            percent = downloaded * 100.0 / total
                            progress = (
                                f"\r{filename}: {downloaded:,}/{total:,} bytes "
                                f"({percent:5.1f}%)"
                            )
                        else:
                            progress = f"\r{filename}: {downloaded:,} bytes"
                        print(progress, end="", flush=True)
                        last_update = now
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            print()
        if total is not None and downloaded != total:
            raise DownloadError(
                f"下载长度不完整：收到 {downloaded} bytes，预期 {total} bytes"
            )


def _download_with_retries(url: str, part: Path, filename: str) -> int:
    if part.exists():
        problem = _payload_problem(part)
        if problem:
            try:
                part.unlink()
            except OSError as exc:
                raise FileOperationError(
                    f"无法清理无效临时文件：{part}（{exc}）"
                ) from exc
    last_error: DownloadError | None = None
    for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        if attempt > 1:
            print(f"{filename}: 开始第 {attempt} 次下载尝试（继续已有 .part）。")
        try:
            _download_attempt(url, part, filename)
            return attempt - 1
        except DownloadError as exc:
            last_error = exc
            print(
                f"{filename}: 第 {attempt} 次下载失败：{exc}",
                file=sys.stderr,
            )
            if attempt < MAX_DOWNLOAD_ATTEMPTS:
                time.sleep(attempt)
    try:
        part.unlink(missing_ok=True)
    except OSError as exc:
        raise FileOperationError(
            f"下载最终失败，且无法清理临时文件：{part}（{exc}）"
        ) from exc
    assert last_error is not None
    raise DownloadError(
        f"{filename} 在 {MAX_DOWNLOAD_ATTEMPTS} 次尝试后仍失败：{last_error}"
    )


def _verify_target(
    filename: str,
    path: Path,
) -> ModelValidation | CsvValidation:
    if filename == "model.onnx":
        print(f"{filename}: 校验 SHA-256、大小并创建真实 CPU Session…")
        return verify_model_file(path)
    print(f"{filename}: 校验 UTF-8、CSV 结构、标签和 category…")
    return verify_csv_file(path)


def prepare_file(
    filename: str,
    output_dir: Path,
    *,
    force: bool,
) -> tuple[FileOutcome, ModelValidation | CsvValidation]:
    target = output_dir / filename
    part = target.with_name(f"{target.name}.part")
    if target.exists():
        try:
            validation = _verify_target(filename, target)
        except (VerificationError, FileOperationError) as exc:
            diagnostic = _preserve_invalid(target, target)
            print(
                f"{filename}: 已有文件校验失败并保留为 {diagnostic.name}：{exc}",
                file=sys.stderr,
            )
        else:
            if not force:
                try:
                    part.unlink(missing_ok=True)
                except OSError as exc:
                    raise FileOperationError(
                        f"无法清理残留临时文件：{part}（{exc}）"
                    ) from exc
                print(f"{filename}: 已有文件校验通过，跳过下载。")
                return (
                    FileOutcome(
                        target,
                        validation.size,
                        validation.sha256,
                        0,
                        True,
                    ),
                    validation,
                )
            print(
                f"{filename}: --force 已启用，将重新下载；"
                "现有有效文件会保留到新文件完成校验。"
            )

    retries = _download_with_retries(official_url(filename), part, filename)
    try:
        validation = _verify_target(filename, part)
    except (VerificationError, FileOperationError):
        diagnostic = _preserve_invalid(part, target)
        print(
            f"{filename}: 下载内容校验失败，异常文件保留为 {diagnostic}",
            file=sys.stderr,
        )
        raise
    try:
        os.replace(part, target)
    except OSError as exc:
        raise FileOperationError(
            f"校验通过但无法原子提交：{part} -> {target}（{exc}）"
        ) from exc
    print(f"{filename}: 已原子保存到 {target}")
    return (
        FileOutcome(
            target,
            validation.size,
            validation.sha256,
            retries,
            False,
        ),
        validation,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "从官方 SmilingWolf/wd-vit-tagger-v3 固定 revision 下载并验证"
            " model.onnx 与 selected_tags.csv。"
        )
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"输出目录（默认：{DEFAULT_OUTPUT_DIR}）",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="只校验现有两个文件，不访问网络或修改文件",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="即使已有文件有效也重新下载；新文件校验前保留旧文件",
    )
    return parser


def _print_summary(
    model_outcome: FileOutcome,
    model: ModelValidation,
    csv_outcome: FileOutcome,
    tags: CsvValidation,
) -> None:
    print()
    print(f"官方仓库：{REPOSITORY}")
    print(f"固定 revision：{REVISION}")
    print(
        f"model.onnx：{model_outcome.size} bytes；SHA-256={model_outcome.sha256}"
    )
    print(
        "selected_tags.csv："
        f"{csv_outcome.size} bytes；SHA-256={csv_outcome.sha256}；"
        f"标签={tags.tag_count}"
    )
    print(
        f"ONNX：input={model.input_name} {model.input_shape}；"
        f"output={model.output_name} {model.output_shape}；"
        f"Provider={model.providers}"
    )
    print(
        "下载重试："
        f"model.onnx={model_outcome.retries}，"
        f"selected_tags.csv={csv_outcome.retries}"
    )
    print("模型输出标签数与 CSV 标签数一致。")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.verify_only and args.force:
        parser.error("--verify-only 与 --force 不能同时使用")
    output_dir = args.output_dir.expanduser().resolve(strict=False)
    try:
        if args.verify_only:
            model_path = output_dir / "model.onnx"
            csv_path = output_dir / "selected_tags.csv"
            if not model_path.is_file() or not csv_path.is_file():
                raise VerificationError(
                    f"校验目录缺少 model.onnx 或 selected_tags.csv：{output_dir}"
                )
            model = verify_model_file(model_path)
            tags = verify_csv_file(csv_path)
            verify_pair(model, tags)
            _print_summary(
                FileOutcome(model_path, model.size, model.sha256, 0, True),
                model,
                FileOutcome(csv_path, tags.size, tags.sha256, 0, True),
                tags,
            )
            return EXIT_OK

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise FileOperationError(
                f"无法创建模型目录：{output_dir}（{exc}）"
            ) from exc
        if args.force:
            print(
                "警告：--force 会从固定官方 revision 重新下载两个文件；"
                "旧的有效文件在新文件校验通过前不会被覆盖。"
            )
        model_outcome, model_validation = prepare_file(
            "model.onnx",
            output_dir,
            force=args.force,
        )
        csv_outcome, csv_validation = prepare_file(
            "selected_tags.csv",
            output_dir,
            force=args.force,
        )
        assert isinstance(model_validation, ModelValidation)
        assert isinstance(csv_validation, CsvValidation)
        verify_pair(model_validation, csv_validation)
        _print_summary(
            model_outcome,
            model_validation,
            csv_outcome,
            csv_validation,
        )
        return EXIT_OK
    except DownloadError as exc:
        print(f"下载错误：{exc}", file=sys.stderr)
        return EXIT_NETWORK
    except VerificationError as exc:
        print(f"校验错误：{exc}", file=sys.stderr)
        return EXIT_VERIFY
    except FileOperationError as exc:
        print(f"文件错误：{exc}", file=sys.stderr)
        return EXIT_FILESYSTEM


if __name__ == "__main__":
    raise SystemExit(main())
