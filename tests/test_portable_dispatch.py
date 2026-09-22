from app import portable_entry


def test_single_exe_cli_flag_dispatches_without_gui(monkeypatch):
    from app import main
    received = []
    monkeypatch.setattr(portable_entry.sys, "executable", "AnimeTaggerLite.exe")
    monkeypatch.setattr(main, "main", lambda args: received.append(args) or 0)
    assert portable_entry.main(["--cli", "image.png", "--device", "cpu"]) == 0
    assert received == [["image.png", "--device", "cpu"]]


def test_legacy_cli_executable_still_dispatches(monkeypatch):
    from app import main
    monkeypatch.setattr(portable_entry.sys, "executable", "AnimeTaggerLiteCLI.exe")
    monkeypatch.setattr(main, "main", lambda args: 7 if args == ["--help"] else 1)
    assert portable_entry.main(["--help"]) == 7
