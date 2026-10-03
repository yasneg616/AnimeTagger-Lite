"""Source and frozen-application paths with an explicit portable mode."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys
import tempfile

from app.errors import ConfigurationError


def _application_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _internal_root(application_root: Path) -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(str(bundled)).resolve()
    return application_root


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    """All source/frozen paths resolved from one application root."""

    application_root: Path
    internal_root: Path
    portable_flag: Path
    is_portable: bool
    resource_dir: Path
    model_root: Path
    data_root: Path
    config_dir: Path
    log_dir: Path
    batch_jobs_dir: Path
    temp_dir: Path
    user_settings_path: Path
    ui_settings_path: Path

    @property
    def writable_directories(self) -> tuple[Path, ...]:
        return (
            self.config_dir,
            self.log_dir,
            self.batch_jobs_dir,
            self.temp_dir,
        )


def resolve_runtime_paths(
    *,
    application_root: Path | None = None,
    internal_root: Path | None = None,
    portable: bool | None = None,
) -> RuntimePaths:
    """Resolve all application paths without consulting the current directory."""

    app_root = (
        Path(application_root).resolve(strict=False)
        if application_root is not None
        else _application_root()
    )
    bundled_root = (
        Path(internal_root).resolve(strict=False)
        if internal_root is not None
        else _internal_root(app_root)
    )
    portable_flag = app_root / "portable.flag"
    is_portable = portable_flag.is_file() if portable is None else portable
    data_root = app_root / "data" if is_portable else app_root
    config_dir = data_root / "config"
    log_dir = data_root / "logs"
    batch_jobs_dir = data_root / "batch-jobs"
    temp_dir = data_root / "temp"
    return RuntimePaths(
        application_root=app_root,
        internal_root=bundled_root,
        portable_flag=portable_flag,
        is_portable=is_portable,
        resource_dir=app_root / "resources",
        model_root=app_root / "models",
        data_root=data_root,
        config_dir=config_dir,
        log_dir=log_dir,
        batch_jobs_dir=batch_jobs_dir,
        temp_dir=temp_dir,
        user_settings_path=config_dir / "settings.json",
        ui_settings_path=config_dir / "ui.ini",
    )


PATHS = resolve_runtime_paths()
APPLICATION_ROOT = PATHS.application_root
INTERNAL_ROOT = PATHS.internal_root
PORTABLE_FLAG = PATHS.portable_flag
IS_PORTABLE = PATHS.is_portable
RESOURCE_DIR = PATHS.resource_dir
MODEL_ROOT = PATHS.model_root
DATA_ROOT = PATHS.data_root
CONFIG_DIR = PATHS.config_dir
LOG_DIR = PATHS.log_dir
BATCH_JOBS_DIR = PATHS.batch_jobs_dir
TEMP_DIR = PATHS.temp_dir
USER_SETTINGS_PATH = PATHS.user_settings_path
UI_SETTINGS_PATH = PATHS.ui_settings_path


def _verify_writable_directory(directory: Path) -> None:
    probe: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=directory,
            prefix=".animetagger-write-test-",
            suffix=".tmp",
            delete=False,
        ) as handle:
            probe = Path(handle.name)
            handle.write(b"ok")
            handle.flush()
        probe.unlink()
        probe = None
    except OSError as exc:
        raise ConfigurationError(
            "便携数据目录不可写："
            f"{directory}。请将整个程序解压到当前用户可写目录，"
            "不要直接从 ZIP、Program Files 或只读介质运行。"
            f"系统错误：{exc}"
        ) from exc
    finally:
        if probe is not None:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass


def ensure_portable_data_directories(
    paths: RuntimePaths | None = None,
    *,
    verify_writable: bool = True,
) -> tuple[Path, ...]:
    """Create and optionally probe the documented portable data directories."""

    resolved = paths or PATHS
    if not resolved.is_portable:
        return ()
    for directory in resolved.writable_directories:
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigurationError(
                "无法创建便携数据目录："
                f"{directory}。请将程序解压到当前用户可写目录。"
                f"系统错误：{exc}"
            ) from exc
        if verify_writable:
            _verify_writable_directory(directory)
    return resolved.writable_directories


def bundled_nvidia_dll_directories() -> tuple[Path | None, Path | None]:
    """Return bundled CUDA and cuDNN DLL directories, if packaged."""

    cuda = INTERNAL_ROOT / "nvidia" / "cu13" / "bin" / "x86_64"
    cudnn = INTERNAL_ROOT / "nvidia" / "cudnn" / "bin"
    return (
        cuda if cuda.is_dir() else None,
        cudnn if cudnn.is_dir() else None,
    )
