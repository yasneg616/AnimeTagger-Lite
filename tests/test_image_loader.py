from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image, features
from pillow_heif import from_pillow

from app.errors import ImageLoadError
from app.image.image_loader import (
    ImageLoadOptions,
    load_rgb_image,
    parse_background_color,
    preprocess_image,
)


def test_png_preprocess_produces_nhwc_float32_bgr(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.png"
    Image.new("RGB", (4, 4), (10, 20, 30)).save(image_path)

    tensor = preprocess_image(image_path, 4)

    assert tensor.shape == (1, 4, 4, 3)
    assert tensor.dtype == np.float32
    assert tuple(tensor[0, 0, 0]) == (30.0, 20.0, 10.0)
    assert tensor.flags.c_contiguous


def test_jpeg_exif_orientation_is_applied(tmp_path: Path) -> None:
    image_path = tmp_path / "oriented.jpg"
    image = Image.new("RGB", (2, 3), (40, 50, 60))
    exif = Image.Exif()
    exif[274] = 6
    image.save(image_path, exif=exif)

    loaded = load_rgb_image(image_path)

    assert loaded.size == (3, 2)


@pytest.mark.skipif(not features.check("webp"), reason="Pillow build lacks WebP")
def test_webp_image_loads(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.webp"
    Image.new("RGB", (5, 3), (1, 2, 3)).save(image_path, format="WEBP")

    loaded = load_rgb_image(image_path)

    assert loaded.mode == "RGB"
    assert loaded.size == (5, 3)


@pytest.mark.parametrize("extension", (".heic", ".heif"))
def test_heif_family_images_load(extension: str, tmp_path: Path) -> None:
    image_path = tmp_path / f"sample{extension}"
    from_pillow(Image.new("RGB", (5, 3), (4, 5, 6))).save(image_path)

    loaded = load_rgb_image(image_path)

    assert loaded.mode == "RGB"
    assert loaded.size == (5, 3)


def test_avif_image_loads_with_pillow_runtime(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.avif"
    Image.new("RGB", (5, 3), (7, 8, 9)).save(image_path, format="AVIF")

    loaded = load_rgb_image(image_path)

    assert loaded.mode == "RGB"
    assert loaded.size == (5, 3)


def test_transparent_png_is_composited_on_configured_background(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "alpha.png"
    Image.new("RGBA", (2, 2), (255, 0, 0, 128)).save(image_path)
    options = ImageLoadOptions(background=(255, 255, 255))

    tensor = preprocess_image(image_path, 2, options=options)

    assert tuple(tensor[0, 0, 0]) == (127.0, 127.0, 255.0)


def test_non_square_image_is_center_padded(tmp_path: Path) -> None:
    image_path = tmp_path / "wide.png"
    Image.new("RGB", (4, 2), (10, 20, 30)).save(image_path)

    tensor = preprocess_image(image_path, 4)

    assert tuple(tensor[0, 0, 0]) == (255.0, 255.0, 255.0)
    assert tuple(tensor[0, 1, 0]) == (30.0, 20.0, 10.0)


def test_corrupt_image_has_clear_error(tmp_path: Path) -> None:
    image_path = tmp_path / "broken.png"
    image_path.write_bytes(b"this is not an image")

    with pytest.raises(ImageLoadError, match="无法解码图片"):
        load_rgb_image(image_path)


def test_excessive_pixel_count_is_rejected(tmp_path: Path) -> None:
    image_path = tmp_path / "large.png"
    Image.new("RGB", (4, 4)).save(image_path)
    options = ImageLoadOptions(max_pixels=15)

    with pytest.raises(ImageLoadError, match="图片像素过多"):
        load_rgb_image(image_path, options=options)


def test_unsupported_extension_is_rejected(tmp_path: Path) -> None:
    image_path = tmp_path / "sample.txt"
    image_path.write_bytes(b"not relevant")

    with pytest.raises(ImageLoadError, match="不支持图片格式"):
        load_rgb_image(image_path)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("#1020FF", (16, 32, 255)),
        ("16, 32, 255", (16, 32, 255)),
    ],
)
def test_background_color_parser(text: str, expected: tuple[int, int, int]) -> None:
    assert parse_background_color(text) == expected
