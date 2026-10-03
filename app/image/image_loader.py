"""Safe, local image decoding and WD14-compatible preprocessing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import warnings

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.errors import ImageLoadError

SUPPORTED_IMAGE_EXTENSIONS = frozenset(
    {
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
)

RGBColor = tuple[int, int, int]


def _register_heif_plugins() -> bool:
    """Register optional HEIF/AVIF Pillow decoders without any network access."""

    try:
        from pillow_heif import register_heif_opener
    except ImportError:
        return False

    register_heif_opener()
    # pillow-heif 1.5 removed its AVIF registration API because Pillow 11.3+
    # ships a native AVIF plugin. Older pillow-heif releases may still expose
    # it, so register it when present without making HEIF depend on that name.
    try:
        from pillow_heif import register_avif_opener
    except ImportError:
        register_avif_opener = None
    if register_avif_opener is not None:
        register_avif_opener()
    return True


_HEIF_PLUGIN_AVAILABLE = _register_heif_plugins()


@dataclass(frozen=True, slots=True)
class ImageLoadOptions:
    """Resource limits and compositing options for one image."""

    background: RGBColor = (255, 255, 255)
    max_file_bytes: int = 128 * 1024 * 1024
    max_pixels: int = 50_000_000
    max_frames: int = 1_000

    def __post_init__(self) -> None:
        if len(self.background) != 3 or any(
            channel < 0 or channel > 255 for channel in self.background
        ):
            raise ValueError("背景色必须包含三个 0 到 255 的整数。")
        if self.max_file_bytes <= 0:
            raise ValueError("最大文件大小必须大于 0。")
        if self.max_pixels <= 0:
            raise ValueError("最大像素数必须大于 0。")
        if self.max_frames <= 0:
            raise ValueError("最大帧数必须大于 0。")


def parse_background_color(value: str) -> RGBColor:
    """Parse a CLI color in #RRGGBB or R,G,B form."""

    text = value.strip()
    if text.startswith("#"):
        hex_value = text[1:]
        if len(hex_value) != 6:
            raise ValueError("背景色十六进制格式应为 #RRGGBB。")
        try:
            return tuple(
                int(hex_value[index : index + 2], 16) for index in (0, 2, 4)
            )  # type: ignore[return-value]
        except ValueError as exc:
            raise ValueError("背景色包含无效的十六进制字符。") from exc

    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 3:
        raise ValueError("背景色格式应为 #RRGGBB 或 R,G,B。")
    try:
        color = tuple(int(part) for part in parts)
    except ValueError as exc:
        raise ValueError("背景色的 RGB 分量必须是整数。") from exc
    if any(channel < 0 or channel > 255 for channel in color):
        raise ValueError("背景色的 RGB 分量必须位于 0 到 255。")
    return color  # type: ignore[return-value]


def _validate_image_path(path: Path, options: ImageLoadOptions) -> None:
    if not path.exists():
        raise ImageLoadError(f"图片文件不存在：{path}")
    if not path.is_file():
        raise ImageLoadError(f"图片路径不是文件：{path}")
    if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_IMAGE_EXTENSIONS))
        raise ImageLoadError(
            f"不支持图片格式“{path.suffix or '(无扩展名)'}”；支持：{supported}"
        )
    try:
        file_size = path.stat().st_size
    except OSError as exc:
        raise ImageLoadError(f"无法读取图片文件信息：{path}") from exc
    if file_size > options.max_file_bytes:
        limit_mb = options.max_file_bytes / (1024 * 1024)
        raise ImageLoadError(
            f"图片文件过大（{file_size / (1024 * 1024):.1f} MiB），"
            f"当前上限为 {limit_mb:.1f} MiB：{path}"
        )


def _has_transparency(image: Image.Image) -> bool:
    return "A" in image.getbands() or "transparency" in image.info


def load_rgb_image(
    image_path: Path,
    *,
    options: ImageLoadOptions | None = None,
    decode_target_size: int | None = None,
) -> Image.Image:
    """Decode only the first frame/page, apply EXIF orientation, and return RGB.

    JPEG decoders receive a draft target when possible. Other formats are
    downscaled immediately after decoding and are never retained by the engine.
    """

    path = Path(image_path)
    settings = options or ImageLoadOptions()
    _validate_image_path(path, settings)

    if decode_target_size is not None and decode_target_size <= 0:
        raise ValueError("解码目标尺寸必须大于 0。")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as source:
                width, height = source.size
                if width <= 0 or height <= 0:
                    raise ImageLoadError(f"图片尺寸无效：{width}×{height}，文件：{path}")
                pixel_count = width * height
                if pixel_count > settings.max_pixels:
                    raise ImageLoadError(
                        f"图片像素过多（{pixel_count:,}），"
                        f"当前上限为 {settings.max_pixels:,}：{path}"
                    )

                frame_count = int(getattr(source, "n_frames", 1))
                if frame_count > settings.max_frames:
                    raise ImageLoadError(
                        f"动态图或多页图片包含 {frame_count} 帧/页，"
                        f"超过上限 {settings.max_frames}：{path}"
                    )

                # Stage 1 intentionally processes only the first frame/page.
                source.seek(0)
                if decode_target_size is not None and source.format in {"JPEG", "MPO"}:
                    source.draft("RGB", (decode_target_size, decode_target_size))

                oriented = ImageOps.exif_transpose(source)
                oriented.load()

                if _has_transparency(oriented):
                    rgba = oriented.convert("RGBA")
                    background = Image.new(
                        "RGBA", rgba.size, (*settings.background, 255)
                    )
                    rgb = Image.alpha_composite(background, rgba).convert("RGB")
                else:
                    rgb = oriented.convert("RGB")

                if (
                    decode_target_size is not None
                    and max(rgb.size) > decode_target_size
                ):
                    rgb.thumbnail(
                        (decode_target_size, decode_target_size),
                        Image.Resampling.LANCZOS,
                    )
                return rgb.copy()
    except ImageLoadError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        heif_hint = ""
        if path.suffix.lower() in {".heic", ".heif", ".avif"} and not _HEIF_PLUGIN_AVAILABLE:
            heif_hint = "；请确认已安装 pillow-heif"
        raise ImageLoadError(
            f"无法解码图片，文件可能损坏或格式不受支持{heif_hint}：{path}"
        ) from exc


def preprocess_image(
    image_path: Path,
    target_size: int,
    *,
    options: ImageLoadOptions | None = None,
) -> np.ndarray:
    """Produce WD14's NHWC float32 BGR tensor in the 0..255 range."""

    if target_size <= 0:
        raise ValueError("模型输入尺寸必须大于 0。")

    settings = options or ImageLoadOptions()
    image = load_rgb_image(
        Path(image_path),
        options=settings,
        decode_target_size=target_size,
    )

    width, height = image.size
    square_size = max(width, height)
    pad_left = (square_size - width) // 2
    pad_top = (square_size - height) // 2
    square = Image.new("RGB", (square_size, square_size), settings.background)
    square.paste(image, (pad_left, pad_top))

    if square_size != target_size:
        square = square.resize(
            (target_size, target_size),
            Image.Resampling.BICUBIC,
        )

    rgb_array = np.asarray(square, dtype=np.float32)
    bgr_array = np.ascontiguousarray(rgb_array[:, :, ::-1], dtype=np.float32)
    return np.expand_dims(bgr_array, axis=0)
