"""Single-image inference entry point with stage 4 batch dispatch."""

from __future__ import annotations

import argparse
from dataclasses import replace
import logging
from pathlib import Path
import sys
from typing import Callable, Sequence

from app import __version__
from app.config.presets import NegativePresetCatalog, PromptProfileCatalog
from app.inference.backends import BACKENDS, create_backend
from app.config.settings import AppSettings, load_settings, PROJECT_ROOT
from app.errors import AnimeTaggerError, ConfigurationError
from app.export_service import ExportFormat, ExportService
from app.image.image_loader import ImageLoadOptions, parse_background_color
from app.inference.model_loader import TagCategory
from app.inference.providers import Device
from app.inference.wd14_engine import (
    InferenceResult,
    WD14Engine,
    group_predictions,
)
from app.prompts.models import PromptBuildResult
from app.prompts.pipeline import PromptProcessor, tag_results_from_predictions
from app.prompts.tag_classifier import TagClassifier
from app.runtime_paths import APPLICATION_ROOT, RESOURCE_DIR

EngineFactory = Callable[..., WD14Engine]
ExporterFactory = Callable[[], ExportService]
logger = logging.getLogger(__name__)

PROJECT_ROOT = APPLICATION_ROOT
DEFAULT_RESOURCE_DIR = RESOURCE_DIR

CATEGORY_TITLES: dict[TagCategory, str] = {
    TagCategory.RATING: "Rating",
    TagCategory.GENERAL: "General",
    TagCategory.CHARACTER: "Character",
    TagCategory.OTHER: "Other",
    TagCategory.COPYRIGHT: "Copyright",
}


def _probability(value: str) -> float:
    try:
        probability = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("必须是 0 到 1 之间的数字。") from exc
    if not 0.0 <= probability <= 1.0:
        raise argparse.ArgumentTypeError("必须位于 0 到 1。")
    return probability


def _background(value: str) -> str:
    try:
        red, green, blue = parse_background_color(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return f"#{red:02X}{green:02X}{blue:02X}"


def _positive_integer(value: str) -> int:
    try:
        integer = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("必须是大于 0 的整数。") from exc
    if integer <= 0:
        raise argparse.ArgumentTypeError("必须大于 0。")
    return integer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="anime-tagger",
        description=(
            "AnimeTagger Lite：本地 WD14 单图识别、提示词和安全导出。"
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"AnimeTagger Lite {__version__}",
    )
    parser.add_argument("image", type=Path, help="要识别的一张图片路径")
    parser.add_argument(
        "--model-dir",
        type=Path,
        help="所选后端本地模型目录；省略时使用配置路径",
    )
    parser.add_argument(
        "--device",
        choices=[device.value for device in Device],
        default=Device.AUTO.value,
        help="推理设备：auto（默认，CUDA 优先）、cuda 或 cpu",
    )
    parser.add_argument(
        "--general-threshold", "--threshold-general",
        type=_probability,
        default=None,
        help="General/Unknown 标签阈值（默认由配置决定）",
    )
    parser.add_argument(
        "--character-threshold", "--threshold-character",
        type=_probability,
        default=None,
        help="Character 标签阈值（默认由配置决定）",
    )
    parser.add_argument(
        "--rating-threshold", "--threshold-rating",
        type=_probability,
        default=None,
        help="Rating 标签阈值（默认由配置决定）",
    )
    parser.add_argument(
        "--include-rating",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="是否允许 Rating 标签进入过滤结果",
    )
    parser.add_argument(
        "--max-tags",
        type=_positive_integer,
        default=None,
        help="过滤后最大标签数",
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
        default=None,
        help="正向提示词 profile",
    )
    parser.add_argument(
        "--profile-prefix",
        dest="add_profile_prefix",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="启用或关闭 profile 质量前缀",
    )
    parser.add_argument(
        "--negative-mode",
        choices=("none", "basic", "cleanup_detected"),
        default=None,
        help="反向提示词模式（默认 none）",
    )
    parser.add_argument(
        "--negative-preset",
        default=None,
        help="resources/negative_presets.json 中的预设名称",
    )
    parser.add_argument(
        "--trigger-word",
        default=None,
        help="可选触发词，放在正向提示词最前方",
    )
    parser.add_argument(
        "--exclude-tag",
        action="append",
        default=None,
        help="过滤阶段排除标签，可重复使用",
    )
    parser.add_argument(
        "--remove-tag",
        action="append",
        default=None,
        help="profile 输出阶段移除标签，可重复使用",
    )
    parser.add_argument(
        "--underscore-to-space",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="是否将标签下划线转换为空格",
    )
    parser.add_argument(
        "--background",
        type=_background,
        default=None,
        metavar="#RRGGBB",
        help="透明区域和平铺区域的背景色（默认 #FFFFFF）",
    )
    parser.add_argument(
        "--output-format",
        choices=("console", "txt", "prompt-txt", "json"),
        default="console",
        help="输出方式；console 不写文件",
    )
    parser.add_argument("--output", type=Path, help="TXT/JSON 导出路径")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="显式允许原子覆盖已有导出文件",
    )
    parser.add_argument(
        "--show-confidence",
        action="store_true",
        help="在控制台显示最终正向标签置信度",
    )
    parser.add_argument(
        "--show-category",
        action="store_true",
        help="在控制台显示最终正向标签类别和提示词组",
    )
    parser.add_argument(
        "--show-raw-tags",
        action="store_true",
        help="附加阶段 1 的原始分类标签诊断视图",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示 DEBUG 日志；不会记录完整提示词或图片内容",
    )
    parser.add_argument("--tagger-backend", choices=tuple(BACKENDS), help="本地模型后端（默认 wd_2026_canary）")
    parser.add_argument("--top-k", type=_positive_integer, help="过滤后标签上限，与 --max-tags 取较小值")
    return parser


def render_result(
    result: InferenceResult,
    *,
    general_threshold: float,
    character_threshold: float,
) -> str:
    grouped = group_predictions(
        result.predictions,
        general_threshold=general_threshold,
        character_threshold=character_threshold,
    )
    lines = [
        f"图片：{result.image_path}",
        f"模型：{result.model_info.files.model_path}",
        f"Provider：{result.model_info.active_provider}",
        f"模型输入：{result.model_info.input_size}×{result.model_info.input_size} BGR",
        f"推理耗时：{result.inference_seconds:.3f} 秒",
    ]

    for category in (
        TagCategory.RATING,
        TagCategory.GENERAL,
        TagCategory.CHARACTER,
        TagCategory.OTHER,
        TagCategory.COPYRIGHT,
    ):
        values = grouped[category]
        title = CATEGORY_TITLES[category]
        if category is TagCategory.GENERAL or category is TagCategory.OTHER:
            title += f"（阈值 ≥ {general_threshold:.2f}）"
        elif category is TagCategory.CHARACTER:
            title += f"（阈值 ≥ {character_threshold:.2f}）"
        lines.append("")
        lines.append(f"[{title}] {len(values)} 个")
        lines.append("类别         置信度     标签")
        if not values:
            lines.append("(无)")
            continue
        for prediction in values:
            lines.append(
                f"{prediction.tag.category_label:<12} "
                f"{prediction.confidence:>8.6f}  "
                f"{prediction.tag.name}"
            )
    return "\n".join(lines)


def _settings_from_args(settings: AppSettings, args: argparse.Namespace) -> AppSettings:
    overrides: dict[str, object] = {}
    if args.tagger_backend is None and settings.backend == "wd_2026_canary" and args.model_dir is not None and (args.model_dir / "model.onnx").is_file():
        # Existing explicit local ONNX commands retain WD v3 semantics.
        logging.getLogger(__name__).warning("旧 --model-dir ONNX 命令使用 wd_v3；新模型请显式指定 --tagger-backend。")
        settings = replace(settings, backend="wd_v3")

    if args.tagger_backend is not None:
        settings = settings.select_backend(args.tagger_backend)
    if args.model_dir is not None:
        overrides["model_dir"] = str(args.model_dir)
    for field_name in (
        "top_k",
        "general_threshold",
        "character_threshold",
        "rating_threshold",
        "include_rating",
        "max_tags",
        "profile",
        "add_profile_prefix",
        "negative_mode",
        "negative_preset",
        "trigger_word",
        "underscore_to_space",
        "background",
    ):
        value = getattr(args, field_name)
        if value is not None:
            overrides[field_name] = value
    if args.exclude_tag is not None:
        overrides["excluded_tags"] = tuple(args.exclude_tag)
    if args.remove_tag is not None:
        overrides["remove_tags"] = tuple(args.remove_tag)
    return replace(settings, **overrides)


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
    )
    logging.getLogger("app").setLevel(level)


def render_prompt_result(
    prompts: PromptBuildResult,
    inference: InferenceResult,
    *,
    show_confidence: bool,
    show_category: bool,
) -> str:
    lines = [
        f"Model: {inference.model_info.files.directory.name}",
        f"Provider: {inference.model_info.active_provider}",
        f"Inference time: {inference.inference_seconds * 1000.0:.1f} ms",
        "",
        "Positive:",
        prompts.positive_prompt,
    ]
    if prompts.negative_prompt:
        lines.extend(("", "Negative:", prompts.negative_prompt))

    if show_confidence or show_category:
        lines.extend(("", "Selected tags:"))
        for tag in prompts.positive_tags:
            details: list[str] = []
            if show_confidence:
                details.append(f"{tag.confidence:.6f}")
            if show_category:
                details.append(tag.category.value)
                details.append(tag.prompt_group.value if tag.prompt_group else "other")
            suffix = f" [{' | '.join(details)}]" if details else ""
            lines.append(f"- {tag.output_name}{suffix}")
    return "\n".join(lines)


def run(
    argv: Sequence[str] | None = None,
    *,
    engine_factory: EngineFactory = WD14Engine,
    exporter_factory: ExporterFactory = ExportService,
    settings_path: Path | None = None,
    resource_dir: Path | None = None,
) -> int:
    effective_argv = list(argv) if argv is not None else sys.argv[1:]
    if effective_argv and effective_argv[0] == "batch":
        from app.batch_cli import run as run_batch

        return run_batch(
            effective_argv[1:],
            settings_path=settings_path,
        )
    args = build_parser().parse_args(effective_argv)
    _configure_logging(args.verbose)
    settings = _settings_from_args(
        load_settings(user_path=settings_path),
        args,
    )
    resources = Path(resource_dir) if resource_dir is not None else DEFAULT_RESOURCE_DIR
    classifier = TagClassifier.from_json(resources / "tag_categories.json")
    profiles = PromptProfileCatalog.from_json(resources / "prompt_profiles.json")
    negative_presets = NegativePresetCatalog.from_json(
        resources / "negative_presets.json"
    )

    if args.output_format == "console" and args.output is not None:
        raise ConfigurationError("--output 只能与 txt、prompt-txt 或 json 一起使用。")
    if args.output_format != "console" and args.output is None:
        raise ConfigurationError(
            f"--output-format {args.output_format} 需要同时提供 --output。"
        )

    try:
        background = parse_background_color(settings.background)
    except ValueError as exc:
        raise ConfigurationError(f"背景色配置无效：{exc}") from exc

    model_dir = args.model_dir or Path(settings.model_dir)
    if args.model_dir is None and not model_dir.is_absolute():
        model_dir = PROJECT_ROOT / model_dir
    engine = (create_backend(settings.backend, model_dir, device=Device(args.device))
              if engine_factory is WD14Engine
              else engine_factory(model_dir, device=Device(args.device)))
    try:
        result = engine.predict(
            args.image,
            image_options=ImageLoadOptions(background=background),
        )
        if result.model_info.provider_warning:
            print(f"提示：{result.model_info.provider_warning}", file=sys.stderr)

        processor = PromptProcessor(
            classifier,
            profiles,
            negative_presets,
        )
        prompts = processor.build(
            tag_results_from_predictions(result.predictions),
            settings,
        )
        console_text = render_prompt_result(
            prompts,
            result,
            show_confidence=args.show_confidence,
            show_category=args.show_category,
        )
        if args.show_raw_tags:
            console_text += "\n\nRaw model tags:\n" + render_result(
                result,
                general_threshold=settings.general_threshold,
                character_threshold=settings.character_threshold,
            )
        print(console_text)

        if args.output_format != "console":
            export_path = exporter_factory().export(
                ExportFormat(args.output_format),
                args.output,
                prompts,
                result,
                overwrite=args.overwrite,
            )
            print(f"\nExported: {export_path}")
        return 0
    finally:
        engine.release()


def main(
    argv: Sequence[str] | None = None,
    *,
    engine_factory: EngineFactory = WD14Engine,
    exporter_factory: ExporterFactory = ExportService,
    settings_path: Path | None = None,
    resource_dir: Path | None = None,
) -> int:
    effective_argv = list(argv) if argv is not None else sys.argv[1:]
    if effective_argv and effective_argv[0] == "batch":
        from app.batch_cli import main as batch_main

        return batch_main(effective_argv[1:])
    try:
        return run(
            effective_argv,
            engine_factory=engine_factory,
            exporter_factory=exporter_factory,
            settings_path=settings_path,
            resource_dir=resource_dir,
        )
    except AnimeTaggerError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已由用户取消。", file=sys.stderr)
        return 130
    except Exception as exc:
        logger.debug("未预期异常", exc_info=True)
        print(
            f"错误：程序遇到未预期问题（{exc.__class__.__name__}）。"
            "请使用相同命令重试并检查 README 的故障排查部分。",
            file=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
