"""Desktop application entry point and GUI logging configuration."""

from __future__ import annotations

import argparse
from logging.handlers import RotatingFileHandler
import logging
from pathlib import Path
import sys
from typing import Sequence

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from app import __version__
from app.errors import AnimeTaggerError, ConfigurationError
from app.runtime_paths import (
    LOG_DIR,
    ensure_portable_data_directories,
)

logger = logging.getLogger(__name__)

from app.ui.theme import ThemeColors, apply_theme, stylesheet

DARK_STYLESHEET = stylesheet(ThemeColors())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.ui",
        description=f"AnimeTagger Lite {__version__} PySide6 桌面界面。",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"AnimeTagger Lite {__version__}",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="启动窗口后自动关闭，用于无模型 GUI 启动检查",
    )
    return parser


def configure_gui_logging(log_dir: Path | None = None) -> Path:
    ensure_portable_data_directories()
    directory = Path(log_dir) if log_dir is not None else LOG_DIR
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigurationError(
            f"无法创建日志目录：{directory}（{exc}）"
        ) from exc
    log_path = directory / "animetagger-lite.log"
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    if any(
        isinstance(existing, RotatingFileHandler)
        and Path(existing.baseFilename) == log_path.resolve()
        for existing in app_logger.handlers
    ):
        return log_path

    try:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=3 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
    except OSError as exc:
        raise ConfigurationError(
            f"日志目录不可写：{directory}（{exc}）"
        ) from exc
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
    )
    app_logger.addHandler(handler)
    return log_path


def create_application(argv: Sequence[str] | None = None) -> QApplication:
    existing = QApplication.instance()
    if existing is not None:
        return existing
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(list(argv) if argv is not None else [])
    app.setApplicationName("AnimeTagger Lite")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("AnimeTaggerLite")
    app.setStyle("Fusion")
    apply_theme(ThemeColors())
    return app


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = create_application(argv)
    try:
        log_path = configure_gui_logging()
    except AnimeTaggerError as exc:
        QMessageBox.critical(
            None,
            "AnimeTagger Lite 无法启动",
            str(exc),
        )
        return 2

    def handle_exception(
        exception_type: type[BaseException],
        exception: BaseException,
        traceback: object,
    ) -> None:
        logger.critical(
            "GUI 未捕获异常",
            exc_info=(exception_type, exception, traceback),
        )
        QMessageBox.critical(
            None,
            "AnimeTagger Lite",
            f"程序遇到内部错误。详细信息已写入：\n{log_path}",
        )

    sys.excepthook = handle_exception

    from app.ui.main_window import MainWindow

    window = MainWindow()
    window.show()
    if args.smoke_test:
        QTimer.singleShot(350, window.close)
    return app.exec()
