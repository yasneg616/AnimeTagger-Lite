"""Executable dispatcher used by the Windows portable onedir builds."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch by executable name while sharing one frozen dependency tree."""

    executable = Path(sys.executable).stem.casefold()
    arguments = list(argv) if argv is not None else sys.argv[1:]
    if executable.endswith("cli") or (arguments and arguments[0] == "--cli"):
        if arguments and arguments[0] == "--cli":
            arguments.pop(0)
        from app.main import main as cli_main

        return cli_main(arguments)

    from app.ui.application import main as gui_main

    return gui_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
