"""Stage 4 folder batch command using the same service as the desktop UI."""

from __future__ import annotations

import argparse
from dataclasses import replace
import logging
from pathlib import Path
import sys
from typing import Sequence

from app import __version__
from app.batch.models import (
    BatchConfig,
    BatchJobStatus,
    BatchTextFormat,
    CaptionPolicy,
    OutputMode,
    ScanOptions,
)
from app.batch.service import BatchRunControl, BatchService
from app.inference.backends import BACKENDS
from app.config.settings import AppSettings, load_settings
from app.errors import (
    AnimeTaggerError,
    BatchConfigurationError,
    BatchManifestError,
    ModelDirectoryError,
    ModelLoadError,
    ProviderError,
    TagCsvError,
)
from app.inference.providers import Device
from app.services.tagging_service import TaggingService

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_CONFIGURATION = 2
EXIT_MODEL = 3
EXIT_CANCELLED = 4
EXIT_INTERNAL = 5


def _probability(value: str) -> float:
    try:
        result = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("必须是 0 到 1 的数值。") from exc
    if not 0.0 <= result <= 1.0:
        raise argparse.ArgumentTypeError("必须位于 0 到 1。")
    return result


def _positive_integer(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("必须是大于 0 的整数。") from exc
    if result <= 0:
        raise argparse.ArgumentTypeError("必须大于 0。")
    return result


def _non_negative_integer(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("必须是非负整数。") from exc
    if result < 0:
        raise argparse.ArgumentTypeError("不能小于 0。")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-tagger batch",
        description=(
            "安全扫描文件夹并串行生成 WD14/LoRA Caption、JSON、CSV 和 Manifest。"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"AnimeTagger Lite {__version__}",
    )
    parser.add_argument(
        "source",
        nargs="*",
        type=Path,
        help="一个或多个图片/文件夹；默认不递归",
    )
    parser.add_argument("--recursive", action="store_true", help="递归扫描子目录")
    parser.add_argument("--include-hidden", action="store_true")
    parser.add_argument("--follow-symlinks", action="store_true")
    parser.add_argument("--max-files", type=_positive_integer, default=100_000)
    parser.add_argument("--max-depth", type=_non_negative_integer, default=64)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument(
        "--device",
        choices=[device.value for device in Device],
        default=None,
    )
    parser.add_argument(
        "--profile",
        choices=(
            "raw",
            "anime",
            "pony",
            "krea2",
            "cyberillustrious_semireal",
            "lora_caption",
        ),
    )
    parser.add_argument(
        "--lora",
        action="store_true",
        help="启用 lora_caption：无质量前缀、无反向提示词、Rating 默认关闭",
    )
    parser.add_argument("--trigger-word")
    parser.add_argument(
        "--trigger-word-position",
        choices=("first", "last"),
        default=None,
    )
    parser.add_argument("--general-threshold", "--threshold-general", type=_probability)
    parser.add_argument("--character-threshold", "--threshold-character", type=_probability)
    parser.add_argument("--rating-threshold", "--threshold-rating", type=_probability)
    parser.add_argument("--max-tags", type=_positive_integer)
    parser.add_argument("--exclude-tag", action="append")
    parser.add_argument("--remove-tag", action="append")
    parser.add_argument("--always-include-tag", action="append")
    parser.add_argument(
        "--include-character-tags",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument(
        "--include-rating",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument(
        "--underscore-to-space",
        action=argparse.BooleanOptionalAction,
        default=None,
    )
    parser.add_argument(
        "--output-mode",
        choices=[mode.value for mode in OutputMode],
        default=OutputMode.BESIDE.value,
    )
    parser.add_argument("--output-root", type=Path)
    parser.add_argument(
        "--existing-caption",
        choices=[policy.value for policy in CaptionPolicy],
        default=CaptionPolicy.SKIP.value,
    )
    parser.add_argument(
        "--export",
        choices=("txt", "prompt-txt", "json", "csv"),
        action="append",
        dest="exports",
        help="可重复；默认 txt 和 csv",
    )
    parser.add_argument("--summary-json", action="store_true")
    parser.add_argument("--csv-bom", action="store_true")
    parser.add_argument("--csv-success-only", action="store_true")
    parser.add_argument(
        "--overwrite-reports",
        action="store_true",
        help="允许原子替换已存在的 CSV/汇总 JSON",
    )
    parser.add_argument("--csv-path", type=Path)
    parser.add_argument("--manifest-path", type=Path)
    parser.add_argument(
        "--resume",
        type=Path,
        metavar="MANIFEST",
        help="恢复一个未完成的 Manifest",
    )
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="显式确认修改已有 Caption 的危险策略",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--tagger-backend", choices=tuple(BACKENDS), help="本地模型后端（默认 wd_2026_canary）")
    parser.add_argument("--top-k", type=_positive_integer, help="过滤后标签上限，与 --max-tags 取较小值")
    return parser


def _settings_from_args(base: AppSettings, args: argparse.Namespace) -> AppSettings:
    overrides: dict[str, object] = {}
    if args.tagger_backend is None and base.backend == "wd_2026_canary" and args.model_dir is not None and (args.model_dir / "model.onnx").is_file():
        # Existing explicit local ONNX commands retain WD v3 semantics.
        logging.getLogger(__name__).warning("旧 --model-dir ONNX 命令使用 wd_v3；新模型请显式指定 --tagger-backend。")
        base = replace(base, backend="wd_v3")

    if args.tagger_backend is not None:
        base = base.select_backend(args.tagger_backend)
    if args.model_dir is not None:
        overrides["model_dir"] = str(args.model_dir)
    for field_name in (
        "top_k",
        "profile",
        "trigger_word",
        "trigger_word_position",
        "general_threshold",
        "character_threshold",
        "rating_threshold",
        "max_tags",
        "include_character_tags",
        "include_rating",
        "underscore_to_space",
    ):
        value = getattr(args, field_name)
        if value is not None:
            overrides[field_name] = value
    if args.exclude_tag is not None:
        overrides["excluded_tags"] = tuple(args.exclude_tag)
    if args.remove_tag is not None:
        overrides["remove_tags"] = tuple(args.remove_tag)
    if args.always_include_tag is not None:
        overrides["always_include_tags"] = tuple(args.always_include_tag)
    if args.lora:
        overrides.update(
            profile="lora_caption",
            add_profile_prefix=False,
            negative_mode="none",
        )
        if args.include_rating is None:
            overrides["include_rating"] = False
    return replace(base, **overrides)


def _config_from_args(args: argparse.Namespace) -> BatchConfig:
    exports = tuple(args.exports or ("txt", "csv"))
    if "txt" in exports and "prompt-txt" in exports:
        raise BatchConfigurationError(
            "--export txt 与 --export prompt-txt 不能同时使用同一个 .txt 目标。"
        )
    text_format = (
        BatchTextFormat.PROMPT_TXT
        if "prompt-txt" in exports
        else BatchTextFormat.TXT
    )
    write_captions = "txt" in exports or "prompt-txt" in exports
    config = BatchConfig(
        output_mode=OutputMode(args.output_mode),
        output_root=args.output_root,
        caption_policy=CaptionPolicy(args.existing_caption),
        text_format=text_format,
        write_captions=write_captions,
        write_json="json" in exports,
        write_csv="csv" in exports,
        write_summary_json=args.summary_json,
        dry_run=args.dry_run,
        csv_bom=args.csv_bom,
        csv_success_only=args.csv_success_only,
        overwrite_reports=args.overwrite_reports,
    )
    if (
        not args.dry_run
        and (
            config.caption_policy is not CaptionPolicy.SKIP
            or config.overwrite_reports
        )
        and not args.yes
    ):
        raise BatchConfigurationError(
            "修改已有 Caption 需要显式 --yes；请先使用 --dry-run 查看范围。"
        )
    return config


def _print_preview(service: BatchService, job: object) -> None:
    preview = service.preview(job)  # type: ignore[arg-type]
    print(
        "Dry run 预览："
        f"发现 {preview['images']} 张，"
        f"预计 Caption {preview['captions']} 个，"
        f"逐图 JSON {preview['json_files']} 个，"
        f"已有 Caption {preview['existing_captions']} 个，"
        f"将跳过 {preview['would_skip']} 个。"
    )
    batch_job = job  # type: ignore[assignment]
    for item in batch_job.items[:20]:
        outputs = [
            str(path)
            for path in (item.caption_path, item.json_path)
            if path is not None
        ]
        print(f"- {item.source_path} -> {', '.join(outputs) or '(无逐图输出)'}")
    if len(batch_job.items) > 20:
        print(f"... 其余 {len(batch_job.items) - 20} 张未逐行显示。")
    for warning in batch_job.warnings:
        print(f"警告：{warning}", file=sys.stderr)


def run(
    argv: Sequence[str] | None = None,
    *,
    tagging_service: TaggingService | None = None,
    settings_path: Path | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    service_owner = tagging_service or TaggingService()
    batch = BatchService(service_owner)

    if args.resume is not None:
        if args.source:
            raise BatchConfigurationError("--resume 不能同时提供新的 source。")
        job = batch.manifests.load(args.resume)
        batch.manifests.warn_if_settings_changed(
            job,
            load_settings(user_path=settings_path),
        )
        if (
            not args.dry_run
            and job.config.caption_policy is not CaptionPolicy.SKIP
            and not args.yes
        ):
            raise BatchConfigurationError(
                "恢复会修改已有 Caption；需要显式 --yes。"
            )
        if args.dry_run:
            job.config = replace(job.config, dry_run=True)
        if args.retry_failed:
            batch.retry_failed(job)
    else:
        if not args.source:
            raise BatchConfigurationError("请提供至少一个 source 或使用 --resume。")
        settings = _settings_from_args(
            load_settings(user_path=settings_path),
            args,
        )
        config = _config_from_args(args)
        scan_options = ScanOptions(
            roots=tuple(args.source),
            recursive=args.recursive,
            include_hidden=args.include_hidden,
            follow_symlinks=args.follow_symlinks,
            max_files=args.max_files,
            max_depth=args.max_depth,
            output_root=config.output_root,
        )
        job = batch.create_job(scan_options, config, settings)

    if args.manifest_path is not None:
        if (
            args.resume is None
            and args.manifest_path.exists()
            and not args.yes
        ):
            raise BatchConfigurationError(
                f"Manifest 已存在；需要显式 --yes：{args.manifest_path}"
            )
        job.manifest_path = args.manifest_path.resolve(strict=False)
    if args.csv_path is not None:
        job.summary_csv_path = args.csv_path.resolve(strict=False)

    if job.config.dry_run:
        _print_preview(batch, job)
        return EXIT_OK

    model_dir = args.model_dir or (
        Path(job.settings.model_dir) if job.settings.model_dir else None
    )
    if model_dir is None:
        raise ModelLoadError("实际批处理需要 --model-dir 或有效的保存模型目录。")
    device = Device(args.device or job.settings.device)
    try:
        info = service_owner.load_model(model_dir, device, backend=job.settings.backend)
        print(
            f"模型已加载：{info.files.directory.name}；"
            f"Provider={info.active_provider}；输入={info.input_size}"
        )
        control = BatchRunControl()
        batch.run_job(
            job,
            control=control,
            on_item=lambda item, position, total: print(
                f"[{position}/{total}] {item.status.value}: {item.source_path}"
            )
            if item.status.value
            in {"completed", "failed", "skipped", "missing"}
            else None,
        )
    finally:
        service_owner.unload_model()

    counts = job.counts()
    print(
        f"批处理结束：status={job.status.value}，"
        f"completed={counts['completed']}，skipped={counts['skipped']}，"
        f"failed={counts['failed'] + counts['missing']}。"
    )
    if job.manifest_path is not None:
        print(f"Manifest: {job.manifest_path}")
    if job.summary_csv_path is not None and job.config.write_csv:
        print(f"CSV: {job.summary_csv_path}")
    if job.status is BatchJobStatus.CANCELLED:
        return EXIT_CANCELLED
    if job.status in {
        BatchJobStatus.COMPLETED_WITH_ERRORS,
        BatchJobStatus.FAILED,
    }:
        return EXIT_PARTIAL
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run(argv)
    except (ModelDirectoryError, ModelLoadError, ProviderError, TagCsvError) as exc:
        print(f"模型错误：{exc}", file=sys.stderr)
        return EXIT_MODEL
    except (BatchConfigurationError, BatchManifestError) as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return EXIT_CONFIGURATION
    except AnimeTaggerError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return EXIT_CONFIGURATION
    except KeyboardInterrupt:
        print("批处理已由用户取消。", file=sys.stderr)
        return EXIT_CANCELLED
    except Exception as exc:
        logger.exception("批处理 CLI 遇到未预期错误")
        print(f"内部错误：{exc.__class__.__name__}", file=sys.stderr)
        return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
