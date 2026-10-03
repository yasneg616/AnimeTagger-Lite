from __future__ import annotations

from types import ModuleType
import sys

from app import portable_entry


def _entry_module(name: str, result: int, calls: list[list[str]]) -> ModuleType:
    module = ModuleType(name)

    def main(argv: list[str]) -> int:
        calls.append(argv)
        return result

    module.main = main  # type: ignore[attr-defined]
    return module


def test_portable_entry_dispatches_cli_by_executable_name(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(sys, "executable", r"D:\portable\AnimeTaggerLiteCLI.exe")
    monkeypatch.setitem(
        sys.modules,
        "app.main",
        _entry_module("app.main", 17, calls),
    )

    assert portable_entry.main(["--version"]) == 17
    assert calls == [["--version"]]


def test_portable_entry_defaults_to_gui(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(sys, "executable", r"D:\portable\AnimeTaggerLite.exe")
    monkeypatch.setitem(
        sys.modules,
        "app.ui.application",
        _entry_module("app.ui.application", 23, calls),
    )

    assert portable_entry.main(["--smoke-test"]) == 23
    assert calls == [["--smoke-test"]]


def test_portable_entry_dispatches_private_review_without_gui(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(sys, "executable", r"D:\portable\AnimeTaggerLite.exe")
    monkeypatch.setitem(sys.modules, "app.tag_visual_review",
                        _entry_module("app.tag_visual_review", 19, calls))
    assert portable_entry.main(["--review-icons", "--port", "8766"]) == 19
    assert calls == [["--port", "8766"]]
