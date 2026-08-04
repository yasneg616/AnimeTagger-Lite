from __future__ import annotations

from logging.handlers import RotatingFileHandler
import logging
from pathlib import Path

import pytest

from app.errors import ConfigurationError
from app.ui import application
from app.ui.application import configure_gui_logging


def test_gui_logging_configuration_is_idempotent(tmp_path: Path) -> None:
    app_logger = logging.getLogger("app")
    original_handlers = tuple(app_logger.handlers)
    try:
        expected = configure_gui_logging(tmp_path)
        assert configure_gui_logging(tmp_path) == expected
        matching = [
            handler
            for handler in app_logger.handlers
            if isinstance(handler, RotatingFileHandler)
            and Path(handler.baseFilename) == expected.resolve()
        ]
        assert len(matching) == 1
        assert matching[0].maxBytes == 3 * 1024 * 1024
        assert matching[0].backupCount == 3
    finally:
        for handler in tuple(app_logger.handlers):
            if handler not in original_handlers:
                app_logger.removeHandler(handler)
                handler.close()


def test_gui_startup_reports_unwritable_portable_data_without_traceback(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    messages: list[tuple[str, str]] = []

    def fail_logging() -> Path:
        raise ConfigurationError(
            "便携数据目录不可写；请将整个程序解压到当前用户可写目录。"
        )

    monkeypatch.setattr(application, "configure_gui_logging", fail_logging)
    monkeypatch.setattr(
        application.QMessageBox,
        "critical",
        lambda _parent, title, message: messages.append((title, message)),
    )

    assert application.main([]) == 2
    assert messages
    assert "无法启动" in messages[0][0]
    assert "可写目录" in messages[0][1]
    assert "Traceback" not in messages[0][1]
