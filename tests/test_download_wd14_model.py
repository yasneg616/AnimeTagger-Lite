from __future__ import annotations

import csv
from pathlib import Path

import pytest

import scripts.download_wd14_model as downloader
from scripts.download_wd14_model import (
    DownloadError,
    EXIT_VERIFY,
    MODEL_SHA256,
    ModelValidation,
    REPOSITORY,
    REVISION,
    VerificationError,
    _download_attempt,
    _download_with_retries,
    _payload_problem,
    main,
    next_invalid_path,
    official_url,
    verify_csv_file,
)


def test_download_source_is_fixed_to_authorized_repository_and_revision() -> None:
    assert REPOSITORY == "SmilingWolf/wd-vit-tagger-v3"
    assert REVISION == "7f6b584d0bd3f55c4531f14ba3d4761b2bccdc0f"
    assert MODEL_SHA256 == (
        "35f23693620b668f4d53fd3c62bf65e40af739bc52c7eb0fbc49258b58d065b6"
    )
    assert official_url("model.onnx").startswith(
        f"https://huggingface.co/{REPOSITORY}/resolve/{REVISION}/"
    )
    with pytest.raises(ValueError):
        official_url("model.safetensors")


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"\xef\xbb\xbf<!doctype html><title>error</title>", "HTML"),
        (b"version https://git-lfs.github.com/spec/v1\n", "Git LFS"),
        (b"version https://example.test/xet pointer\n", "Xet"),
        (b'\xef\xbb\xbf{"error":"not found"}', "JSON"),
    ],
)
def test_pointer_and_error_payloads_are_rejected(
    tmp_path: Path,
    content: bytes,
    expected: str,
) -> None:
    path = tmp_path / "download.part"
    path.write_bytes(content)
    assert expected in (_payload_problem(path) or "")


def test_csv_verification_checks_fields_categories_and_count(
    tmp_path: Path,
) -> None:
    path = tmp_path / "selected_tags.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("tag_id", "name", "category", "count"))
        for index in range(1_000):
            category = (9, 0, 4)[index % 3]
            writer.writerow((index, f"tag_{index}", category, 1))
    info = verify_csv_file(path)
    assert info.tag_count == 1_000
    assert set(info.category_ids) == {0, 4, 9}
    assert info.sha256


def test_csv_verification_rejects_truncated_mapping(tmp_path: Path) -> None:
    path = tmp_path / "selected_tags.csv"
    path.write_text(
        "tag_id,name,category\n1,safe,9\n2,1girl,0\n3,alice,4\n",
        encoding="utf-8",
    )
    with pytest.raises(VerificationError, match="大小异常|明显截断"):
        verify_csv_file(path)


def test_invalid_file_names_are_preserved_without_overwrite(
    tmp_path: Path,
) -> None:
    target = tmp_path / "model.onnx"
    first = target.with_name("model.onnx.invalid")
    first.write_bytes(b"diagnostic")
    assert next_invalid_path(target).name == "model.onnx.invalid.1"


def test_verify_only_missing_files_never_downloads_or_creates_directory(
    tmp_path: Path,
) -> None:
    output = tmp_path / "missing"
    assert main(("--output-dir", str(output), "--verify-only")) == EXIT_VERIFY
    assert not output.exists()


def test_download_attempt_resumes_existing_part(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    part = tmp_path / "model.onnx.part"
    part.write_bytes(b"abc")
    request_headers: dict[str, str | None] = {}

    class FakeResponse:
        status = 206
        headers = {
            "Content-Range": "bytes 3-5/6",
            "Content-Length": "3",
        }

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def getcode(self) -> int:
            return self.status

        def read(self, _size: int) -> bytes:
            if getattr(self, "_read", False):
                return b""
            self._read = True
            return b"def"

    def fake_urlopen(request, timeout):
        request_headers["range"] = request.get_header("Range")
        request_headers["timeout"] = str(timeout)
        return FakeResponse()

    monkeypatch.setattr(downloader, "urlopen", fake_urlopen)
    _download_attempt(
        official_url("model.onnx"),
        part,
        "model.onnx",
    )
    assert request_headers["range"] == "bytes=3-"
    assert part.read_bytes() == b"abcdef"


def test_download_final_failure_retries_then_removes_part(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    part = tmp_path / "model.onnx.part"
    part.write_bytes(b"partial")
    calls = 0

    def fail(*_args, **_kwargs) -> None:
        nonlocal calls
        calls += 1
        raise DownloadError("offline")

    monkeypatch.setattr(downloader, "_download_attempt", fail)
    monkeypatch.setattr(downloader.time, "sleep", lambda _seconds: None)
    with pytest.raises(DownloadError, match="3 次尝试"):
        _download_with_retries(
            official_url("model.onnx"),
            part,
            "model.onnx",
        )
    assert calls == 3
    assert not part.exists()


def test_existing_valid_file_is_skipped_without_network(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = tmp_path / "model.onnx"
    target.write_bytes(b"existing")
    validation = ModelValidation(
        size=378_536_310,
        sha256=MODEL_SHA256,
        input_name="input",
        input_shape=("batch_size", 448, 448, 3),
        output_name="output",
        output_shape=("batch_size", 10_861),
        output_count=10_861,
        providers=("CPUExecutionProvider",),
    )
    monkeypatch.setattr(
        downloader,
        "_verify_target",
        lambda _filename, _path: validation,
    )
    monkeypatch.setattr(
        downloader,
        "_download_with_retries",
        lambda *_args, **_kwargs: pytest.fail("不应访问网络"),
    )
    outcome, actual = downloader.prepare_file(
        "model.onnx",
        tmp_path,
        force=False,
    )
    assert outcome.skipped
    assert actual is validation
    assert target.read_bytes() == b"existing"


def test_failed_download_verification_preserves_invalid_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    def fake_download(_url: str, part: Path, _filename: str) -> int:
        part.write_bytes(b"bad download")
        return 0

    monkeypatch.setattr(downloader, "_download_with_retries", fake_download)
    monkeypatch.setattr(
        downloader,
        "_verify_target",
        lambda _filename, _path: (_ for _ in ()).throw(
            VerificationError("hash mismatch")
        ),
    )
    with pytest.raises(VerificationError, match="hash mismatch"):
        downloader.prepare_file("model.onnx", tmp_path, force=False)
    diagnostic = tmp_path / "model.onnx.invalid"
    assert diagnostic.read_bytes() == b"bad download"
    assert not (tmp_path / "model.onnx.part").exists()
