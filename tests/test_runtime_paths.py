from __future__ import annotations

from pathlib import Path

import pytest

from app.errors import ConfigurationError
from app.runtime_paths import (
    APPLICATION_ROOT,
    BATCH_JOBS_DIR,
    CONFIG_DIR,
    IS_PORTABLE,
    LOG_DIR,
    MODEL_ROOT,
    RESOURCE_DIR,
    TEMP_DIR,
    ensure_portable_data_directories,
    resolve_runtime_paths,
)


def test_source_runtime_paths_stay_inside_project_root() -> None:
    assert not IS_PORTABLE
    assert (APPLICATION_ROOT / "app").is_dir()
    assert RESOURCE_DIR == APPLICATION_ROOT / "resources"
    assert MODEL_ROOT == APPLICATION_ROOT / "models"
    assert CONFIG_DIR == APPLICATION_ROOT / "config"
    assert LOG_DIR == APPLICATION_ROOT / "logs"
    assert BATCH_JOBS_DIR == APPLICATION_ROOT / "batch-jobs"
    assert TEMP_DIR == APPLICATION_ROOT / "temp"
    assert ensure_portable_data_directories() == ()


@pytest.mark.parametrize(
    "folder",
    ("portable app", "便携版", "éditions"),
)
def test_portable_paths_support_spaces_and_non_ascii(
    tmp_path: Path,
    folder: str,
) -> None:
    root = tmp_path / folder
    root.mkdir()
    paths = resolve_runtime_paths(
        application_root=root,
        internal_root=root / "_internal",
        portable=True,
    )

    created = ensure_portable_data_directories(paths)

    assert paths.resource_dir == root / "resources"
    assert paths.model_root == root / "models"
    assert paths.user_settings_path == root / "data" / "config" / "settings.json"
    assert created == paths.writable_directories
    assert all(path.is_dir() for path in created)
    assert not list(root.rglob(".animetagger-write-test-*.tmp"))


def test_portable_directory_creation_reports_actionable_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "portable"
    paths = resolve_runtime_paths(application_root=root, portable=True)

    def deny_mkdir(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("simulated read-only directory")

    monkeypatch.setattr(Path, "mkdir", deny_mkdir)
    with pytest.raises(ConfigurationError, match="解压到当前用户可写目录"):
        ensure_portable_data_directories(paths)
