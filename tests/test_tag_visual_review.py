from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from pathlib import Path
import threading
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

import pytest

from app.tag_visual_review import MAX_BODY, ReviewCatalogue, ReviewConflict, ReviewServer, ReviewStore
import app.tag_visual_review as review_module


@pytest.fixture(scope="module")
def catalogue():
    return ReviewCatalogue()


@pytest.fixture
def store(tmp_path, catalogue):
    result = ReviewStore(tmp_path, catalogue)
    yield result
    result.close()


@contextmanager
def running_server(catalogue, store):
    server = ReviewServer(0, catalogue, store)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def request(base, path, *, data=None, headers=None, method=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    extra = dict(headers or {})
    if data is not None and not isinstance(data, bytes):
        data = json.dumps(data, ensure_ascii=False).encode("utf-8")
        extra.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(base + path, data=data, headers=extra, method=method)
    try:
        response = opener.open(req, timeout=10)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read()
        return response.status, dict(response.headers), body


def named(catalogue, name):
    return next(item for item in catalogue.items if item["name"] == name)


def test_gallery_contains_every_existing_illustration_and_excludes_characters(catalogue):
    expected = {key for key, visual in catalogue.library.entries.items() if visual.has_icon}
    assert {item["key"] for item in catalogue.items} == expected
    assert len(catalogue.by_id) == len(expected) == catalogue.payload["total"]
    assert all(item["category"] != "character" for item in catalogue.items)
    assert all(item["label_zh"] and item["explanation_zh"] for item in catalogue.items)
    assert sum(group["count"] for group in catalogue.payload["groups"]) == len(expected)
    assert sum(status["count"] for status in catalogue.payload["statuses"]) == len(expected)
    # Stable identities depend on category and name, so sorting/repainting cannot lose feedback.
    assert named(catalogue, "general")["category"] == "rating"
    assert any(item["status"] == "category_only" for item in catalogue.items)


def test_selection_note_and_atomic_snapshot_survive_reopening(tmp_path, catalogue):
    item = named(catalogue, "blue_hair")
    store = ReviewStore(tmp_path, catalogue)
    result = store.update(item["id"], True, 0, "蓝色不够明显，需要重做。")
    store.close()
    reopened = ReviewStore(tmp_path, catalogue)
    try:
        assert reopened.state()["reviews"][item["id"]] == result["review"]
        snapshot = json.loads((tmp_path / "rework.json").read_text(encoding="utf-8"))
        assert snapshot["rework_count"] == 1
        assert snapshot["items"][0]["entry_key"] == "general:blue hair"
        assert snapshot["items"][0]["note"] == "蓝色不够明显，需要重做。"
        assert not list(tmp_path.glob(".rework-*.tmp"))
    finally:
        reopened.close()


def test_uncheck_removes_queue_item_and_preserves_other_choices(store, catalogue):
    first, second = catalogue.items[:2]
    old = store.update(first["id"], True, 0, "第一个问题")
    store.update(second["id"], True, 0, "第二个问题")
    result = store.update(first["id"], False, old["review"]["row_version"])
    assert result["selected_count"] == 1
    assert result["review"]["note"] == "第一个问题"
    assert [item["id"] for item in store.rework()["items"]] == [second["id"]]


def test_cli_export_reads_feedback_without_rewriting_live_snapshot(store, catalogue, monkeypatch, capsys):
    store.update(catalogue.items[0]["id"], True, 0, "已保存的选择")
    before = (store.directory / "rework.json").read_bytes()
    monkeypatch.setattr(review_module, "ReviewCatalogue", lambda: catalogue)
    assert review_module.main(["--data-dir", str(store.directory), "--export"]) == 0
    exported = json.loads(capsys.readouterr().out)
    assert exported["rework_count"] == 1 and exported["items"][0]["note"] == "已保存的选择"
    assert (store.directory / "rework.json").read_bytes() == before


def test_stale_page_cannot_overwrite_newer_selection_or_reason(store, catalogue):
    item = catalogue.items[0]
    result = store.update(item["id"], True, 0, "来自新页面的原因")
    with pytest.raises(ReviewConflict) as error:
        store.update(item["id"], False, 0, "来自旧页面")
    assert error.value.current == result["review"]
    assert store.state()["version"] == result["version"]
    assert store.rework()["items"][0]["note"] == "来自新页面的原因"


def test_parallel_selections_do_not_replace_each_other(store, catalogue):
    items = catalogue.items[:24]
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda item: store.update(item["id"], True, 0, item["name"]), items))
    assert len({result["version"] for result in results}) == 24
    assert store.state()["selected_count"] == 24
    snapshot = json.loads((store.directory / "rework.json").read_text(encoding="utf-8"))
    assert snapshot["rework_count"] == 24 and snapshot["version"] == 24
    assert {item["id"] for item in snapshot["items"]} == {item["id"] for item in items}


def test_changed_or_removed_illustration_keeps_existing_feedback(store, catalogue, monkeypatch):
    item = catalogue.items[0]
    store.update(item["id"], True, 0, "需要复核")
    with monkeypatch.context() as patch:
        patch.setitem(catalogue.by_id, item["id"], {**item, "icon_revision": "new-version"})
        assert store.rework()["items"][0]["icon_changed"]
    with monkeypatch.context() as patch:
        patch.delitem(catalogue.by_id, item["id"])
        assert store.rework()["rework_count"] == 1
        assert store.rework()["items"][0]["current_icon_revision"] is None
    assert store.state()["selected_count"] == 1


def test_revision_tracks_only_the_illustration_that_actually_changed(catalogue, monkeypatch):
    target = named(catalogue, 'blue_hair')
    original_compose = review_module.compose_svg

    def redraw_one(visual, *args, **kwargs):
        result = original_compose(visual, *args, **kwargs)
        return result.replace('#579bd4','#478aca') if visual.key == 'blue hair' and visual.category == 'general' else result

    monkeypatch.setattr(review_module, 'compose_svg', redraw_one)
    revised = ReviewCatalogue()
    changed = {item['id'] for item in revised.items if item['icon_revision'] != catalogue.by_id[item['id']]['icon_revision']}
    assert changed == {target['id']}
    assert revised.revision != catalogue.revision


def test_snapshot_error_reports_warning_but_retains_committed_feedback(store, catalogue, monkeypatch):
    def cannot_write():
        raise PermissionError("test snapshot unavailable")

    monkeypatch.setattr(store, "_write_snapshot", cannot_write)
    result = store.update(catalogue.items[0]["id"], True, 0)
    assert result["warning"] and result["selected_count"] == 1
    assert store.rework()["items"][0]["needs_rework"] is True


def test_http_checkbox_roundtrip_and_readable_feedback(store, catalogue):
    with running_server(catalogue, store) as (server, base):
        assert server.server_address[0] == "127.0.0.1"
        status, headers, html = request(base, "/")
        assert status == 200 and "图示审阅台" in html.decode()
        assert "connect-src 'self'" in headers["Content-Security-Policy"]
        assert "Access-Control-Allow-Origin" not in headers
        token = json.loads(request(base, "/api/bootstrap")[2])["token"]
        auth = {"X-Review-Token": token, "Origin": base}
        item = named(catalogue, "blue_hair")
        payload = {"id": item["id"], "needs_rework": True, "expected_version": 0,
                   "note": '<script>alert("note")</script>蓝色需要更清晰'}
        status, _, result = request(base, "/api/review", data=payload, headers=auth)
        assert status == 200
        saved = json.loads(result)
        assert saved["review"]["needs_rework"] and saved["selected_count"] == 1
        exported = json.loads(request(base, "/api/rework", headers=auth)[2])
        assert exported["items"][0]["note"] == payload["note"]
        assert json.loads(request(base, "/api/state", headers=auth)[2])["selected_count"] == 1
        payload.update(needs_rework=False, expected_version=saved["review"]["row_version"])
        assert request(base, "/api/review", data=payload, headers=auth)[0] == 200
        assert json.loads(request(base, "/api/rework", headers=auth)[2])["rework_count"] == 0


@pytest.mark.parametrize("extra", [
    {"Host": "attacker.example:8766"}, {"Origin": "https://attacker.example"},
    {"Origin": "null"}, {"Sec-Fetch-Site": "cross-site"}, {"X-Review-Token": "wrong-session"},
    {"X-Review-Token": "caf\u00e9"},
])
def test_external_sites_and_invalid_sessions_cannot_read_or_change_feedback(store, catalogue, extra):
    with running_server(catalogue, store) as (server, base):
        headers = {"X-Review-Token": server.token, **extra}
        assert request(base, "/api/state", headers=headers)[0] == 403
        data = {"id": catalogue.items[0]["id"], "needs_rework": True, "expected_version": 0}
        assert request(base, "/api/review", data=data, headers=headers)[0] == 403
        assert store.state()["selected_count"] == 0


def test_unprotected_forms_and_cors_preflights_are_rejected(store, catalogue):
    with running_server(catalogue, store) as (_, base):
        data = {"id": catalogue.items[0]["id"], "needs_rework": True, "expected_version": 0}
        assert request(base, "/api/review", data=data)[0] == 403
        status, headers, _ = request(base, "/api/review", method="OPTIONS", headers={"Origin": "https://example.com"})
        assert status == 403 and "Access-Control-Allow-Origin" not in headers


@pytest.mark.parametrize("path", ["/data/tag-visual-review/rework.json", "/app/tag_visual_review.py", "/../README.md", "/icons/../../config/settings.json.svg"])
def test_only_whitelisted_assets_are_served(store, catalogue, path):
    with running_server(catalogue, store) as (_, base):
        assert request(base, path)[0] == 404


def test_svg_endpoints_keep_semantic_color_and_support_both_sizes_and_themes(store, catalogue):
    with running_server(catalogue, store) as (_, base):
        blue = named(catalogue, "blue_hair")
        black = named(catalogue, "black_hair")
        for theme in ("light", "dark"):
            for variant in ("small", "large"):
                status, headers, svg = request(base, f"/icons/{blue['id']}.svg?theme={theme}&variant={variant}")
                assert status == 200 and headers["Content-Type"].startswith("image/svg+xml")
                assert ET.fromstring(svg).tag.endswith("svg")
                color = catalogue.visuals[blue["id"]].recipe["color"].encode()
                assert color in svg
                assert svg != request(base, f"/icons/{black['id']}.svg?theme={theme}&variant={variant}")[2]
        assert request(base, f"/icons/{blue['id']}.svg?theme=invalid")[0] == 400


@pytest.mark.parametrize("change", [{"needs_rework": "true"}, {"expected_version": True}, {"expected_version": -1}, {"note": None}, {"note": "x" * 2001}, {"id": "unknown"}])
def test_malformed_feedback_never_changes_saved_choices(store, catalogue, change):
    with running_server(catalogue, store) as (server, base):
        data = {"id": catalogue.items[0]["id"], "needs_rework": True, "expected_version": 0, **change}
        assert request(base, "/api/review", data=data, headers={"X-Review-Token": server.token})[0] == 400
        assert store.state()["version"] == 0


def test_oversized_feedback_is_rejected_before_parsing(store, catalogue):
    with running_server(catalogue, store) as (server, base):
        assert request(base, "/api/review", data=b"x" * (MAX_BODY + 1),
                       headers={"X-Review-Token": server.token, "Content-Type": "application/json"})[0] == 413
        assert store.state()["version"] == 0
