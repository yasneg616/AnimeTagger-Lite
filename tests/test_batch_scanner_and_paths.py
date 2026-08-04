from __future__ import annotations

import os
from pathlib import Path
import threading

import pytest

from app.batch.models import BatchConfig, OutputMode, ScanOptions
from app.batch.paths import (
    OutputPlanner,
    ensure_safe_relative_path,
    safe_filename,
    safe_join,
    short_path_hash,
)
from app.batch.scanner import BatchScanner, normalized_path_key, path_is_within
from app.errors import BatchConfigurationError, BatchScanError
from tests.batch_helpers import touch_image


def test_non_recursive_scan_only_returns_top_level_images(tmp_path: Path) -> None:
    touch_image(tmp_path / "top.png")
    touch_image(tmp_path / "nested" / "inside.jpg")
    result = BatchScanner().scan(ScanOptions((tmp_path,)))
    assert [item.source_path.name for item in result.items] == ["top.png"]


def test_recursive_scan_preserves_relative_paths(tmp_path: Path) -> None:
    touch_image(tmp_path / "b" / "inside.jpg")
    touch_image(tmp_path / "a.png")
    result = BatchScanner().scan(ScanOptions((tmp_path,), recursive=True))
    assert [item.relative_path.as_posix() for item in result.items] == [
        "a.png",
        "b/inside.jpg",
    ]


def test_multiple_roots_keep_same_name_as_distinct_items(tmp_path: Path) -> None:
    first = touch_image(tmp_path / "one" / "same.png")
    second = touch_image(tmp_path / "two" / "same.png")
    result = BatchScanner().scan(
        ScanOptions((first.parent, second.parent))
    )
    assert {item.source_path for item in result.items} == {
        first.resolve(),
        second.resolve(),
    }
    assert result.items[0].id != result.items[1].id


@pytest.mark.parametrize(
    ("name", "supported"),
    [
        ("a.png", True),
        ("b.JPG", True),
        ("c.webp", True),
        ("d.txt", False),
        ("e.json", False),
        ("f", False),
    ],
)
def test_scanner_reuses_supported_extension_filter(
    tmp_path: Path,
    name: str,
    supported: bool,
) -> None:
    touch_image(tmp_path / name)
    if supported:
        result = BatchScanner().scan(ScanOptions((tmp_path,)))
        assert len(result.items) == 1
    else:
        with pytest.raises(BatchScanError):
            BatchScanner().scan(ScanOptions((tmp_path,)))


def test_hidden_files_and_directories_are_excluded_by_default(
    tmp_path: Path,
) -> None:
    touch_image(tmp_path / ".hidden.png")
    touch_image(tmp_path / ".hidden-dir" / "inside.png")
    touch_image(tmp_path / "visible.png")
    result = BatchScanner().scan(ScanOptions((tmp_path,), recursive=True))
    assert [item.source_path.name for item in result.items] == ["visible.png"]
    assert result.hidden_count == 2


def test_hidden_files_can_be_included(tmp_path: Path) -> None:
    touch_image(tmp_path / ".hidden.png")
    result = BatchScanner().scan(
        ScanOptions((tmp_path,), include_hidden=True)
    )
    assert len(result.items) == 1


def test_symlink_is_skipped_by_default(tmp_path: Path) -> None:
    source = touch_image(tmp_path / "source.png")
    link = tmp_path / "link.png"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("当前 Windows 会话不允许创建符号链接")
    result = BatchScanner().scan(ScanOptions((tmp_path,)))
    assert [item.source_path.name for item in result.items] == ["source.png"]
    assert result.symlink_count == 1


def test_followed_symlink_duplicate_is_deduplicated(tmp_path: Path) -> None:
    source = touch_image(tmp_path / "source.png")
    link = tmp_path / "link.png"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("当前 Windows 会话不允许创建符号链接")
    result = BatchScanner().scan(
        ScanOptions((tmp_path,), follow_symlinks=True)
    )
    assert len(result.items) == 1
    assert result.duplicate_count == 1


def test_overlapping_roots_do_not_duplicate_physical_file(tmp_path: Path) -> None:
    touch_image(tmp_path / "nested" / "one.png")
    result = BatchScanner().scan(
        ScanOptions((tmp_path, tmp_path / "nested"), recursive=True)
    )
    assert len(result.items) == 1
    assert result.duplicate_count == 1


def test_hardlink_duplicate_is_deduplicated(tmp_path: Path) -> None:
    source = touch_image(tmp_path / "source.png")
    alias = tmp_path / "alias.png"
    try:
        os.link(source, alias)
    except OSError:
        pytest.skip("当前文件系统不允许创建硬链接")
    result = BatchScanner().scan(ScanOptions((tmp_path,)))
    assert len(result.items) == 1
    assert result.duplicate_count == 1


def test_scan_cancel_stops_discovery(tmp_path: Path) -> None:
    for index in range(10):
        touch_image(tmp_path / f"{index:02}.png")
    event = threading.Event()
    result = BatchScanner().scan(
        ScanOptions((tmp_path,)),
        cancel_event=event,
        progress=lambda count, _path: event.set() if count == 2 else None,
    )
    assert result.cancelled
    assert len(result.items) == 2


def test_max_files_marks_result_truncated(tmp_path: Path) -> None:
    for index in range(5):
        touch_image(tmp_path / f"{index}.png")
    result = BatchScanner().scan(
        ScanOptions((tmp_path,), max_files=3)
    )
    assert len(result.items) == 3
    assert result.truncated


def test_max_depth_stops_deeper_recursion(tmp_path: Path) -> None:
    touch_image(tmp_path / "one" / "level1.png")
    touch_image(tmp_path / "one" / "two" / "level2.png")
    result = BatchScanner().scan(
        ScanOptions((tmp_path,), recursive=True, max_depth=1)
    )
    assert [item.source_path.name for item in result.items] == ["level1.png"]


def test_output_root_is_never_rescanned(tmp_path: Path) -> None:
    touch_image(tmp_path / "source.png")
    output = tmp_path / "output"
    touch_image(output / "generated-preview.png")
    result = BatchScanner().scan(
        ScanOptions(
            (tmp_path,),
            recursive=True,
            output_root=output,
        )
    )
    assert [item.source_path.name for item in result.items] == ["source.png"]


def test_scanner_accepts_one_image_as_root(tmp_path: Path) -> None:
    source = touch_image(tmp_path / "one.png")
    result = BatchScanner().scan(ScanOptions((source,)))
    assert result.items[0].source_path == source.resolve()
    assert result.items[0].relative_path == Path("one.png")


def test_duplicate_root_is_removed_before_scan(tmp_path: Path) -> None:
    touch_image(tmp_path / "one.png")
    result = BatchScanner().scan(ScanOptions((tmp_path, tmp_path)))
    assert result.roots == (tmp_path.resolve(),)
    assert len(result.items) == 1


def test_missing_root_becomes_warning_without_hiding_valid_root(
    tmp_path: Path,
) -> None:
    valid = tmp_path / "valid"
    touch_image(valid / "one.png")
    result = BatchScanner().scan(
        ScanOptions((tmp_path / "missing", valid))
    )
    assert len(result.items) == 1
    assert "不存在" in result.warnings[0]


def test_scan_does_not_decode_image_bytes(tmp_path: Path) -> None:
    touch_image(tmp_path / "corrupt.png", b"definitely-not-an-image")
    result = BatchScanner().scan(ScanOptions((tmp_path,)))
    assert len(result.items) == 1


def test_beside_output_uses_same_stem(tmp_path: Path) -> None:
    source = touch_image(tmp_path / "picture.png")
    result = BatchScanner().scan(ScanOptions((tmp_path,)))
    items = list(result.items)
    OutputPlanner().plan(items, BatchConfig(write_csv=False))
    assert items[0].caption_path == source.with_suffix(".txt")


def test_mirror_output_preserves_relative_directory(tmp_path: Path) -> None:
    source_root = tmp_path / "dataset"
    touch_image(source_root / "characters" / "a" / "001.png")
    result = BatchScanner().scan(
        ScanOptions((source_root,), recursive=True)
    )
    output = tmp_path / "output"
    items = list(result.items)
    OutputPlanner().plan(
        items,
        BatchConfig(
            output_mode=OutputMode.MIRROR,
            output_root=output,
            write_csv=False,
        ),
    )
    assert items[0].caption_path == output / "characters" / "a" / "001.txt"


def test_mirror_multiple_roots_get_distinct_root_names(tmp_path: Path) -> None:
    one = tmp_path / "one"
    two = tmp_path / "two"
    touch_image(one / "same.png")
    touch_image(two / "same.png")
    result = BatchScanner().scan(ScanOptions((one, two)))
    output = tmp_path / "out"
    items = list(result.items)
    OutputPlanner().plan(
        items,
        BatchConfig(
            output_mode=OutputMode.MIRROR,
            output_root=output,
            write_csv=False,
        ),
    )
    assert {item.caption_path for item in items} == {
        output / "one" / "same.txt",
        output / "two" / "same.txt",
    }


def test_flat_output_collision_uses_stable_hash(tmp_path: Path) -> None:
    touch_image(tmp_path / "a" / "same.png")
    touch_image(tmp_path / "b" / "same.jpg")
    result = BatchScanner().scan(
        ScanOptions((tmp_path,), recursive=True)
    )
    output = tmp_path / "flat"
    items = list(result.items)
    OutputPlanner().plan(
        items,
        BatchConfig(
            output_mode=OutputMode.FLAT,
            output_root=output,
            write_csv=False,
        ),
    )
    names = [item.caption_path.name for item in items if item.caption_path]
    assert len(set(names)) == 2
    assert all(name.startswith("same__") for name in names)


@pytest.mark.parametrize(
    "relative",
    [
        Path("../escape.txt"),
        Path("a/../../escape.txt"),
        Path("."),
    ],
)
def test_path_traversal_is_rejected(relative: Path) -> None:
    with pytest.raises(BatchConfigurationError):
        ensure_safe_relative_path(relative)


def test_safe_join_never_leaves_root(tmp_path: Path) -> None:
    root = tmp_path / "out"
    target = safe_join(root, Path("a/b.txt"))
    assert path_is_within(target, root)


@pytest.mark.parametrize(
    ("unsafe", "expected"),
    [
        ("a:b", "a_b"),
        ("a/b", "a_b"),
        ("a*b?", "a_b_"),
        ("...", "root"),
        ("CON", "_CON"),
        ("lpt9.caption", "_lpt9.caption"),
    ],
)
def test_invalid_filename_characters_are_sanitized(
    unsafe: str,
    expected: str,
) -> None:
    assert safe_filename(unsafe) == expected


def test_short_hash_is_stable_for_same_path(tmp_path: Path) -> None:
    path = tmp_path / "same.png"
    assert short_path_hash(path) == short_path_hash(path)


def test_windows_normalized_path_key_is_case_insensitive() -> None:
    if os.name != "nt":
        pytest.skip("Windows 路径规范化场景")
    assert normalized_path_key(Path("C:/Temp/FILE.PNG")) == normalized_path_key(
        Path("c:/temp/file.png")
    )


def test_output_mode_requires_output_root() -> None:
    with pytest.raises(BatchConfigurationError):
        BatchConfig(output_mode=OutputMode.MIRROR)
