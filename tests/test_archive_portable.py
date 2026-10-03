from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from scripts.archive_portable import create_archive


def minimal_package(root: Path) -> None:
    files = {
        "AnimeTaggerLite.exe": b"test executable",
        "BUILD-MANIFEST.json": b'{"model_included": true, "model_sha256": {"model.onnx": "old"}}',
        "LICENSE": b"project license",
        "README.txt": b"original description",
        "QUICK_START.txt": b"original instructions",
        "THIRD_PARTY_NOTICES.txt": b"component licenses",
        "portable.flag": b"",
        "resources/default_settings.json": b"{}",
        "resources/tag_categories.json": b"{}",
        "models/wd-vit-tagger-v3/README.txt": b"model setup",
        "models/canary/config.json": b"{}",
        "models/canary/selected_tags.csv": b"id,name,category\n",
        "models/canary/model.safetensors": b"secret weights",
        "models/legacy/pytorch_model.bin": b"other weights",
        "data/temp/clipboard.png": b"private picture",
        "data/config/settings.json": b"private settings",
        "logs/private.log": b"private log",
    }
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def test_archive_excludes_private_state_and_weights_and_verifies_contents(tmp_path: Path) -> None:
    package = tmp_path / "package"
    minimal_package(package)
    before = {p.relative_to(package).as_posix(): p.read_bytes() for p in package.rglob("*") if p.is_file()}
    output = tmp_path / "archive.zip"
    manifest = create_archive(package, output, version="test", tag="test")
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert not any(name.endswith((".onnx", ".safetensors", ".bin", "private.log", "clipboard.png")) for name in names)
        assert "archive/models/canary/config.json" in names
        assert "archive/models/canary/selected_tags.csv" in names
        assert "archive/data/config/" in names
        assert not any(name == "archive/data/config/settings.json" for name in names)
        build = json.loads(archive.read("archive/BUILD-MANIFEST.json"))
        assert build["model_included"] is False and build["model_sha256"] == {}
        for record in manifest["files"]:
            content = archive.read("archive/" + record["path"])
            assert len(content) == record["bytes"]
            assert hashlib.sha256(content).hexdigest() == record["sha256"]
        assert archive.testzip() is None
    assert manifest["omitted_private_files"] == 3
    assert len(manifest["omitted_model_weights"]) == 2
    assert manifest["archive"]["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert "private picture" not in output.with_suffix(".manifest.json").read_text()
    after = {p.relative_to(package).as_posix(): p.read_bytes() for p in package.rglob("*") if p.is_file()}
    assert after == before


def test_archive_recovers_cleaned_templates_without_changing_the_original(tmp_path: Path) -> None:
    package = tmp_path / "package"
    minimal_package(package)
    missing = package / "resources/default_settings.json"
    missing.unlink()
    supplements = tmp_path / "supplements"
    restored = supplements / "resources/default_settings.json"
    restored.parent.mkdir(parents=True)
    restored.write_bytes(b'{"restored": true}')
    output = tmp_path / "archive.zip"
    manifest = create_archive(package, output, version="test", tag="test", supplemental=supplements)
    with zipfile.ZipFile(output) as archive:
        assert archive.read("archive/resources/default_settings.json") == restored.read_bytes()
    assert manifest["supplemental_files_restored_from_git"] == 1
    assert not missing.exists()


def test_archive_refuses_output_inside_the_original_package(tmp_path: Path) -> None:
    package = tmp_path / "package"
    minimal_package(package)
    with pytest.raises(ValueError, match="outside"):
        create_archive(package, package / "archive.zip", version="test", tag="test")
    assert not (package / "archive.zip").exists()
