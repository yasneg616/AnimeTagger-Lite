"""Private, loopback-only review gallery for the shipped tag illustrations.

Run with ``python -m app.tag_visual_review``. No Qt, models, user images,
external services, or extra Python packages are required.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import secrets
import sqlite3
import sys
import threading
from urllib.parse import parse_qs, urlsplit

from app.runtime_paths import APPLICATION_ROOT, RESOURCE_DIR
from app.tag_visual_svg import compose_svg
from app.tag_visuals import GROUP_LABELS, TagVisualLibrary

logger = logging.getLogger(__name__)
DEFAULT_DATA_DIR = APPLICATION_ROOT / "data" / "tag-visual-review"
STATUS_LABELS = {"direct": "具体图示", "composed": "组合图示", "schematic": "场景示意", "category_only": "类别图示"}
CATEGORY_LABELS = {"general": "一般标签", "rating": "内容评级", "copyright": "作品名称"}
APP_ID = "anime-tagger-icon-review"
MAX_BODY = 16_384


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class ReviewCatalogue:
    """A stable category-aware identity for every available illustration."""

    def __init__(self, directory: Path | None = None) -> None:
        self.library = TagVisualLibrary(directory)
        if not self.library.available:
            raise ValueError("图示资源不可用，无法建立审阅目录。")
        self.directory = self.library.directory
        ledger: dict[str, dict[str, str]] = {}
        ledger_path = self.directory / "coverage.tsv"
        if ledger_path.is_file():
            with ledger_path.open(encoding="utf-8", newline="") as handle:
                ledger = {row["key"]: row for row in csv.DictReader(handle, delimiter="\t")}
        self.items: list[dict] = []
        self.visuals = {}
        visuals = dict(self.library.entries)
        for key, visual in self.library.terms.items():
            visuals.setdefault("general:" + key, visual)
        for key, visual in visuals.items():
            if not visual.has_icon or visual.category == "character":
                continue
            item_id = hashlib.sha256(key.encode("utf-8")).hexdigest()
            row = ledger.get(key, {})
            # Revision follows the actual illustration. Editing an unrelated
            # drawing or a source comment must not invalidate reviewed icons.
            rendered = {}
            for theme, ink, paper in (("light", "#263443", "#f5f6fa"),
                                      ("dark", "#e6edf7", "#202b3d")):
                for variant, preview in (("small", False), ("large", True)):
                    svg = compose_svg(visual, self.directory, ink=ink, paper=paper, preview=preview)
                    rendered[theme + "-" + variant] = hashlib.sha256(svg.encode("utf-8")).hexdigest()
            descriptor = {"label": visual.label_zh, "explanation": visual.explanation_zh,
                          "status": visual.status, "rendered": rendered}
            revision = hashlib.sha256(_json_bytes(descriptor)).hexdigest()
            item = {"id": item_id, "key": key, "name": row.get("name", visual.key.replace(" ", "_")),
                    "category": visual.category, "group": visual.group, "status": visual.status,
                    "label_zh": visual.label_zh, "explanation_zh": visual.explanation_zh,
                    "reason": visual.reason, "count": int(row.get("count") or 0),
                    "icon_revision": revision}
            self.items.append(item)
            self.visuals[item_id] = visual
        if not self.items:
            raise ValueError("当前图示库没有可审阅的图标。")
        self.items.sort(key=lambda item: (-item["count"], item["key"]))
        self.by_id = {item["id"]: item for item in self.items}
        self.revision = hashlib.sha256(_json_bytes(self.items)).hexdigest()
        groups = Counter(item["group"] for item in self.items)
        statuses = Counter(item["status"] for item in self.items)
        categories = Counter(item["category"] for item in self.items)
        self.payload = {"revision": self.revision, "total": len(self.items), "items": self.items,
                        "groups": [{"value": key, "label": label, "count": groups[key]}
                                   for key, label in GROUP_LABELS.items() if groups[key]],
                        "statuses": [{"value": key, "label": label, "count": statuses[key]}
                                     for key, label in STATUS_LABELS.items() if statuses[key]],
                        "categories": [{"value": key, "label": label, "count": categories[key]}
                                       for key, label in CATEGORY_LABELS.items() if categories[key]]}

    @lru_cache(maxsize=512)
    def svg(self, item_id: str, theme: str = "light", small: bool = False) -> bytes:
        if theme not in {"light", "dark"}:
            raise ValueError("无效的预览主题。")
        ink, paper = ("#e6edf7", "#202b3d") if theme == "dark" else ("#263443", "#f5f6fa")
        return compose_svg(self.visuals[item_id], self.directory, ink=ink, paper=paper,
                           preview=not small).encode("utf-8")


class ReviewConflict(Exception):
    def __init__(self, current: dict) -> None:
        self.current = current


class ReviewStore:
    """SQLite is authoritative; rework.json is an atomic, readable snapshot."""

    def __init__(self, directory: Path, catalogue: ReviewCatalogue, *, write_snapshot: bool = True) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.catalogue = catalogue
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.directory / "reviews.sqlite3", timeout=10, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value INTEGER NOT NULL)")
        self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('version', 0)")
        self.db.execute("""CREATE TABLE IF NOT EXISTS reviews (
            id TEXT PRIMARY KEY, entry_key TEXT NOT NULL, name TEXT NOT NULL,
            category TEXT NOT NULL, label_zh TEXT NOT NULL, needs_rework INTEGER NOT NULL CHECK(needs_rework IN (0,1)),
            note TEXT NOT NULL, icon_revision TEXT NOT NULL, updated_at TEXT NOT NULL, row_version INTEGER NOT NULL
        )""")
        self.db.commit()
        if write_snapshot:
            with self.lock:
                self._write_snapshot()

    @staticmethod
    def _row(row: sqlite3.Row | None) -> dict:
        if row is None:
            return {"needs_rework": False, "note": "", "row_version": 0}
        result = dict(row)
        result["needs_rework"] = bool(result["needs_rework"])
        return result

    def _version(self) -> int:
        return self.db.execute("SELECT value FROM metadata WHERE key='version'").fetchone()[0]

    def state(self) -> dict:
        with self.lock:
            rows = {row["id"]: self._row(row) for row in self.db.execute("SELECT * FROM reviews")}
            return {"version": self._version(), "reviews": rows,
                    "selected_count": sum(row["needs_rework"] for row in rows.values()),
                    "catalog_revision": self.catalogue.revision}

    def rework(self) -> dict:
        with self.lock:
            rows = [self._row(row) for row in self.db.execute(
                "SELECT * FROM reviews WHERE needs_rework=1 ORDER BY category, name")]
            for row in rows:
                item = self.catalogue.by_id.get(row["id"])
                row["current_icon_revision"] = item["icon_revision"] if item else None
                row["icon_changed"] = item is None or item["icon_revision"] != row["icon_revision"]
                if item:
                    row["explanation_zh"] = item["explanation_zh"]
                    row["group"] = item["group"]
                    row["status"] = item["status"]
            return {"schema_version": 1, "catalog_revision": self.catalogue.revision,
                    "version": self._version(), "updated_at": _now(), "rework_count": len(rows), "items": rows}

    def _write_snapshot(self) -> None:
        payload = self.rework()
        temp = self.directory / (".rework-" + secrets.token_hex(6) + ".tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self.directory / "rework.json")
        finally:
            temp.unlink(missing_ok=True)

    def update(self, item_id: str, needed: bool, expected_version: int, note: str | None = None) -> dict:
        item = self.catalogue.by_id[item_id]
        with self.lock:
            try:
                self.db.execute("BEGIN IMMEDIATE")
                previous = self._row(self.db.execute("SELECT * FROM reviews WHERE id=?", (item_id,)).fetchone())
                if previous["row_version"] != expected_version:
                    raise ReviewConflict(previous)
                note = previous["note"] if note is None else note.strip()
                version = self._version() + 1
                self.db.execute("""INSERT INTO reviews VALUES (?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET entry_key=excluded.entry_key, name=excluded.name,
                    category=excluded.category, label_zh=excluded.label_zh, needs_rework=excluded.needs_rework,
                    note=excluded.note, icon_revision=excluded.icon_revision,
                    updated_at=excluded.updated_at, row_version=excluded.row_version""",
                    (item_id, item["key"], item["name"], item["category"], item["label_zh"],
                     int(needed), note, item["icon_revision"], _now(), version))
                self.db.execute("UPDATE metadata SET value=? WHERE key='version'", (version,))
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
            warning = ""
            try:
                self._write_snapshot()
            except OSError:
                logger.exception("审阅勾选已保存到数据库，但重做清单快照写入失败")
                warning = "勾选已保存，但重做清单快照暂时写入失败。可使用页面上的导出按钮。"
            current = self._row(self.db.execute("SELECT * FROM reviews WHERE id=?", (item_id,)).fetchone())
            selected_count = self.db.execute("SELECT COUNT(*) FROM reviews WHERE needs_rework=1").fetchone()[0]
            return {"review": current, "version": version, "selected_count": selected_count, "warning": warning}

    def close(self) -> None:
        with self.lock:
            self.db.close()


class ReviewServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, catalogue: ReviewCatalogue, store: ReviewStore,
                 asset_dir: Path | None = None) -> None:
        self.catalogue, self.store = catalogue, store
        self.asset_dir = asset_dir or RESOURCE_DIR / "tag_visual_review"
        self.token = secrets.token_urlsafe(32)
        self.instance = secrets.token_hex(12)
        super().__init__(("127.0.0.1", port), ReviewHandler)
        actual_port = self.server_address[1]
        self.allowed_hosts = {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}"}
        self.allowed_origins = {"http://" + host for host in self.allowed_hosts}


class ReviewHandler(BaseHTTPRequestHandler):
    server: ReviewServer

    def log_message(self, format: str, *args: object) -> None:
        # Do not put user notes or query strings into logs.
        return

    def _send(self, status: int, payload: bytes, content_type: str = "application/json; charset=utf-8",
              *, download: bool = False, etag: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "private, max-age=3600" if etag else "no-store")
        if etag:
            self.send_header("ETag", '"' + etag + '"')
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; "
                         "img-src 'self'; font-src 'self'; connect-src 'self'; base-uri 'none'; "
                         "frame-ancestors 'none'; form-action 'none'")
        if download:
            self.send_header("Content-Disposition", 'attachment; filename="tag-icons-rework.json"')
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, payload: object, **kwargs) -> None:
        self._send(status, _json_bytes(payload), **kwargs)

    def _guard(self, private: bool = False) -> bool:
        if self.headers.get("Host", "") not in self.server.allowed_hosts:
            self._json(403, {"error": "仅允许从本机地址访问。"})
            return False
        origin = self.headers.get("Origin")
        if origin is not None and origin not in self.server.allowed_origins:
            self._json(403, {"error": "不允许其他网站访问审阅后台。"})
            return False
        if self.headers.get("Sec-Fetch-Site", "none") not in {"none", "same-origin"}:
            self._json(403, {"error": "不允许跨站访问。"})
            return False
        if private and not hmac.compare_digest(self.headers.get("X-Review-Token", "").encode("utf-8"),
                                               self.server.token.encode("ascii")):
            self._json(403, {"error": "审阅会话已失效，请刷新页面。"})
            return False
        return True

    def do_GET(self) -> None:
        route = urlsplit(self.path)
        private = route.path in {"/api/state", "/api/rework"}
        if not self._guard(private):
            return
        try:
            if route.path == "/api/health":
                self._json(200, {"app": APP_ID, "instance": self.server.instance,
                                 "total": len(self.server.catalogue.items)})
            elif route.path == "/api/bootstrap":
                self._json(200, {"token": self.server.token, "instance": self.server.instance})
            elif route.path == "/api/catalog":
                self._json(200, self.server.catalogue.payload)
            elif route.path == "/api/state":
                self._json(200, self.server.store.state())
            elif route.path == "/api/rework":
                self._json(200, self.server.store.rework(), download="download" in parse_qs(route.query))
            elif route.path.startswith("/icons/") and route.path.endswith(".svg"):
                item_id = route.path[7:-4]
                if item_id not in self.server.catalogue.by_id:
                    self._json(404, {"error": "图示不存在。"})
                    return
                query = parse_qs(route.query)
                theme = query.get("theme", ["light"])[0]
                variant = query.get("variant", ["large"])[0]
                if theme not in {"light", "dark"} or variant not in {"large", "small"}:
                    self._json(400, {"error": "无效的图示预览选项。"})
                    return
                svg = self.server.catalogue.svg(item_id, theme, variant == "small")
                self._send(200, svg, "image/svg+xml; charset=utf-8", etag=hashlib.sha256(svg).hexdigest())
            else:
                assets = {"/": ("index.html", "text/html"), "/index.html": ("index.html", "text/html"),
                          "/assets/app.js": ("app.js", "text/javascript"),
                          "/assets/style.css": ("style.css", "text/css"),
                          "/favicon.svg": ("favicon.svg", "image/svg+xml")}
                if route.path not in assets:
                    self._json(404, {"error": "页面不存在。"})
                    return
                filename, mime = assets[route.path]
                self._send(200, (self.server.asset_dir / filename).read_bytes(), mime + "; charset=utf-8")
        except (OSError, ValueError, KeyError, sqlite3.Error):
            logger.exception("图示审阅读取失败")
            self._json(503, {"error": "本机资源暂时不可用，请重试。"})

    def do_POST(self) -> None:
        if not self._guard(private=True):
            return
        if urlsplit(self.path).path != "/api/review":
            self._json(404, {"error": "接口不存在。"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > MAX_BODY:
                self._json(413, {"error": "提交内容太大或为空。"})
                return
            if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                self._json(415, {"error": "需要 JSON 格式。"})
                return
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict) or set(data) - {"id", "needs_rework", "expected_version", "note"}:
                raise ValueError("无效的提交字段。")
            if not isinstance(data.get("id"), str) or data["id"] not in self.server.catalogue.by_id:
                raise ValueError("图示不存在。")
            if type(data.get("needs_rework")) is not bool:
                raise ValueError("勾选状态必须是布尔值。")
            if type(data.get("expected_version")) is not int or data["expected_version"] < 0:
                raise ValueError("审阅版本无效。")
            if "note" in data and (not isinstance(data["note"], str) or len(data["note"]) > 2000):
                raise ValueError("备注最多 2,000 个字符。")
            self._json(200, self.server.store.update(data["id"], data["needs_rework"],
                                                    data["expected_version"], data.get("note")))
        except ReviewConflict as exc:
            self._json(409, {"error": "该图示的选择已在另一页面更新，已载入最新状态，请重新选择。",
                             "current": exc.current})
        except (ValueError, UnicodeError) as exc:
            self._json(400, {"error": str(exc)})
        except (OSError, sqlite3.Error):
            logger.exception("图示审阅保存失败")
            self._json(503, {"error": "保存失败，之前的选择仍保留。请重试。"})

    def do_OPTIONS(self) -> None:
        self._json(403, {"error": "不允许跨站访问。"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--export", action="store_true", help="输出本机已勾选的重做清单，不启动网站")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not 0 <= args.port <= 65535:
        parser.error("port 必须在 0–65535 之间")
    store = None
    server = None
    instance_path = args.data_dir / "server.json"
    try:
        if sys.stderr is None and not args.export:
            # A windowed portable EXE has no Python stderr. Keep startup and
            # resource errors in the same private directory as its feedback.
            args.data_dir.mkdir(parents=True, exist_ok=True)
            logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                                handlers=[logging.FileHandler(args.data_dir / "server.runtime.log", encoding="utf-8")],
                                force=True)
        catalogue = ReviewCatalogue()
        store = ReviewStore(args.data_dir, catalogue, write_snapshot=not args.export)
        if args.export:
            print(json.dumps(store.rework(), ensure_ascii=False, indent=2))
            return 0
        server = ReviewServer(args.port, catalogue, store)
        url = f"http://127.0.0.1:{server.server_address[1]}"
        instance_path.write_text(json.dumps({"pid": os.getpid(), "url": url, "instance": server.instance}, indent=2),
                                 encoding="utf-8")
        logger.info("图示审阅网站已启动：%s，共 %s 个图示", url, len(catalogue.items))
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        return 0
    except (OSError, ValueError, sqlite3.Error):
        logger.exception("图示审阅网站无法启动")
        return 1
    finally:
        if server is not None:
            server.server_close()
            try:
                current = json.loads(instance_path.read_text(encoding="utf-8"))
                if current.get("instance") == server.instance:
                    instance_path.unlink(missing_ok=True)
            except (OSError, ValueError):
                pass
        if store is not None:
            store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
