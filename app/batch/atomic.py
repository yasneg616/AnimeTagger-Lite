"""Small atomic UTF-8 output primitives used by all batch artifacts."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import tempfile

from app.errors import ExportError

logger = logging.getLogger(__name__)


def atomic_write_bytes(path: Path, content: bytes) -> Path:
    target = Path(path)
    temporary: Path | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".animetagger.tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            temporary = Path(handle.name)
        os.replace(temporary, target)
        temporary = None
        return target
    except OSError as exc:
        raise ExportError(f"无法原子写入批处理输出：{target}（{exc}）") from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                logger.warning("无法清理批处理临时文件：%s", temporary)


def atomic_write_text(path: Path, content: str) -> Path:
    return atomic_write_bytes(Path(path), content.encode("utf-8"))
