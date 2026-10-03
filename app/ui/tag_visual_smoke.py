"""Explicit source/frozen GUI probe with isolated preferences and screenshots."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import sys
import time

from PySide6.QtCore import QByteArray, QEvent, QPoint, QRect, QSettings, Qt
from PySide6.QtGui import QColor, QFont, QHelpEvent, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app import __version__
from app.config.settings import AppSettings
from app.inference.model_loader import TagCategory
from app.prompts.models import TagResult
from app.tag_visual_svg import compose_svg
from app.ui.collapsible import CollapsibleSection
from app.ui.main_window import MainWindow
from app.ui.tag_table_model import TagColumn
from app.ui.tag_visual_widgets import VISUAL_ROLE, TagVisualProvider
from app.ui.theme import PRESETS, apply_theme, ink


def _settle(app: QApplication) -> None:
    app.processEvents()
    QTest.qWait(35)


def _require(condition: object, message: str) -> None:
    # Frozen builds use Python optimization; acceptance gates must survive -O.
    if not condition:
        raise RuntimeError(message)


def _hover(view, delegate, index) -> None:
    view.scrollTo(index)
    QApplication.processEvents()
    local = view.visualRect(index).center()
    event = QHelpEvent(QEvent.Type.ToolTip, local, view.viewport().mapToGlobal(local))
    QApplication.sendEvent(view.viewport(), event)
    _require(delegate.card.isVisible(), "hover did not open")
    _require(delegate.card.current_visual.key == index.data(VISUAL_ROLE).key, "hover showed stale descriptor")


def run_visual_smoke(app: QApplication, output: Path) -> int:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {"version": __version__, "frozen": bool(getattr(sys, "frozen", False)), "checks": {}, "screenshots": []}
    window = None
    try:
        settings = QSettings(str(output / "probe-ui.ini"), QSettings.Format.IniFormat)
        settings.clear()
        window = MainWindow(settings=AppSettings(backend="wd_v3", model_dir=str(output / "missing-model")),
                            settings_path=output / "probe-settings.json", ui_settings=settings)
        provider = window.tag_visual_provider
        _require(provider.library.available, "visual resources unavailable")
        samples = json.loads((provider.library.directory / "samples.json").read_text(encoding="utf-8"))
        if isinstance(samples, dict):
            samples = samples["tags"]
        _require(len(samples) == 48, "expected 48 fixed samples")
        tags = tuple(TagResult(name, .99-i*.001, TagCategory.GENERAL) for i, name in enumerate(samples))
        window.tag_model.set_tags(tags)
        window.random_prompt_panel.tag_list.set_tags(tags)
        window.prompt_panel.set_prompts(positive=", ".join(samples), negative="", positive_edited=False,
                                       negative_edited=False, stale=False, tag_count=48)
        window.resize(1540, 960)
        primary = app.primaryScreen()
        if primary is not None:
            window.setScreen(primary)
            window.move(primary.availableGeometry().topLeft()+QPoint(20, 20))
        window.show()
        for section in window.findChildren(CollapsibleSection):
            if section.toggle.text().endswith("筛选与显示"):
                section.toggle.setChecked(True)
        _settle(app)
        report["dpr"] = window.devicePixelRatioF()
        report["screen"] = window.screen().name()
        report["platform"] = app.platformName()

        # Validate every shipped supported descriptor, including long-tail
        # compositions. Parsing alone is complemented by actual row/hover grabs.
        start = time.perf_counter()
        supported = [v for v in provider.library.entries.values() if v.has_icon]
        bad = [v.key for v in supported if not QSvgRenderer(QByteArray(
            compose_svg(v, provider.library.directory, preview=True).encode("utf-8"))).isValid()]
        _require(not bad, f"bad SVGs: {bad[:12]}")
        report["checks"]["all_svg_valid"] = len(supported)
        report["checks"]["all_svg_parse_seconds"] = round(time.perf_counter()-start, 3)
        refinement_path = provider.library.directory / "refinements.json"
        refinement_keys = set(json.loads(refinement_path.read_text(encoding="utf-8"))["entries"]) if refinement_path.is_file() else set()
        refined = [v for v in supported if (v.recipe or {}).get("refinement") == "r1"]
        _require({v.category+":"+v.key for v in refined} == refinement_keys, "refinement catalogue mismatch")
        report["checks"]["refined_samples"] = len(refined)

        extras = json.loads((provider.library.directory / "review_samples.json").read_text(encoding="utf-8"))["tags"]
        review = QImage(6*180, 7*208, QImage.Format.Format_ARGB32_Premultiplied)
        review.fill(QColor("#ffffff"))
        light = TagVisualProvider(library=provider.library, surface="#ffffff")
        painter = QPainter(review)
        try:
            for i, name in enumerate(extras):
                x, y = i%6*180, i//6*208
                visual = light.visual_for(name, "general")
                _require(visual.semantic, f"review sample pending: {name}")
                painter.drawPixmap(x+20, y+2, light.pixmap(visual,140,1))
                painter.setPen(QColor("#19202b"))
                painter.setFont(QFont("Segoe UI", 8))
                painter.drawText(QRect(x+5,y+146,170,36),Qt.TextFlag.TextWordWrap,name)
                painter.setFont(QFont("Microsoft YaHei UI", 9))
                painter.drawText(QRect(x+5,y+185,170,22),visual.label_zh)
        finally:
            painter.end()
        _require(review.save(str(output / "long-tail-review.png")), "failed to save long-tail review")
        report["checks"]["long_tail_samples"] = len(extras)
        report["screenshots"].append({"file":"long-tail-review.png", "theme":"晴昼", "kind":"long-tail examples"})

        for pair in (("short_hair", "long_hair"), ("ponytail", "twintails"), ("braid", "twin_braids"),
                     ("hair_over_one_eye", "closed_eyes"), ("blue_eyes", "green_eyes"),
                     ("arms_up", "outstretched_arms"), ("standing", "sitting"), ("sitting", "kneeling"),
                     ("white_shirt", "black_shirt"), ("long_sleeves", "short_sleeves")):
            svgs = [compose_svg(provider.visual_for(name, "general"), provider.library.directory) for name in pair]
            _require(svgs[0] != svgs[1], f"indistinguishable diagrams: {pair}")
        report["checks"]["distinct_core_pairs"] = 10

        for theme_index, (theme_name, colors) in enumerate(PRESETS.items()):
            apply_theme(colors)
            provider.set_surface(colors.surface)
            window.theme_colors = colors
            window.pages.setCurrentIndex(0)
            window.tag_table.verticalScrollBar().setValue(0)
            _settle(app)
            prefix = f"theme-{theme_index+1}"
            for filename, widget in ((prefix+"-single.png", window),):
                _require(widget.grab().save(str(output / filename)), f"failed to save {filename}")
                report["screenshots"].append({"file": filename, "theme": theme_name, "kind": "single"})
            index = window.tag_proxy.index(0, TagColumn.TAG)
            _hover(window.tag_table, window.tag_visual_delegate, index)
            _settle(app)
            filename = prefix+"-hover.png"
            _require(window.tag_visual_delegate.card.grab().save(str(output / filename)), f"failed to save {filename}")
            report["screenshots"].append({"file": filename, "theme": theme_name, "kind": "hover"})
            window.tag_visual_delegate.hide_card()
            window.pages.setCurrentIndex(2)
            _settle(app)
            filename = prefix+"-random.png"
            _require(window.grab().save(str(output / filename)), f"failed to save {filename}")
            report["screenshots"].append({"file": filename, "theme": theme_name, "kind": "random"})
            view = window.random_prompt_panel.tag_list
            _hover(view, view.visual_delegate, view.tag_model.index(0))
            view.verticalScrollBar().setValue(5)
            _require(not view.visual_delegate.card.isVisible(), "scroll left stale hover")

            # Both the 24px row icon and 160px preview are in this sample sheet.
            sheet = QImage(6*190, 8*260, QImage.Format.Format_ARGB32_Premultiplied)
            sheet.fill(QColor(colors.surface))
            painter = QPainter(sheet)
            try:
                for i, name in enumerate(samples):
                    x, y = (i % 6)*190, (i // 6)*260
                    visual = provider.visual_for(name, "general")
                    _require(visual.semantic, f"sample pending: {name}")
                    for size, px, py in ((160, x+15, y+25), (24, x+157, y+3)):
                        bitmap = provider.pixmap(visual, size, window.devicePixelRatioF())
                        _require(bitmap is not None and not bitmap.isNull(), f"sample did not render: {name}")
                        painter.drawPixmap(px, py, bitmap)
                    painter.setPen(QColor(ink(colors.surface)))
                    painter.setFont(QFont("Segoe UI", 9))
                    painter.drawText(QRect(x+5, y+188, 180, 38), Qt.TextFlag.TextWordWrap, name)
                    painter.setFont(QFont("Microsoft YaHei UI", 10))
                    painter.drawText(QRect(x+5, y+231, 180, 25), visual.label_zh)
            finally:
                painter.end()
            filename = prefix+"-48-samples.png"
            _require(sheet.save(str(output / filename)), f"failed to save {filename}")
            report["screenshots"].append({"file": filename, "theme": theme_name, "kind": "48 samples"})

            if refined:
                refined_sheet = QImage(7*190, ((len(refined)+6)//7)*260, QImage.Format.Format_ARGB32_Premultiplied)
                refined_sheet.fill(QColor(colors.surface))
                painter = QPainter(refined_sheet)
                try:
                    for i, visual in enumerate(refined):
                        x,y = i%7*190, i//7*260
                        for size,px,py in ((160,x+15,y+25),(24,x+157,y+3)):
                            bitmap = provider.pixmap(visual,size,window.devicePixelRatioF())
                            _require(bitmap is not None and not bitmap.isNull(), f"refined sample did not render: {visual.key}")
                            painter.drawPixmap(px,py,bitmap)
                        painter.setPen(QColor(ink(colors.surface)))
                        painter.setFont(QFont("Segoe UI",9))
                        painter.drawText(QRect(x+5,y+188,180,38),Qt.TextFlag.TextWordWrap,visual.key.replace(" ","_"))
                        painter.setFont(QFont("Microsoft YaHei UI",10))
                        painter.drawText(QRect(x+5,y+231,180,25),visual.label_zh)
                finally:
                    painter.end()
                filename = prefix+"-refined-samples.png"
                _require(refined_sheet.save(str(output / filename)), f"failed to save {filename}")
                report["screenshots"].append({"file":filename,"theme":theme_name,"kind":"refined samples"})

        window.pages.setCurrentIndex(0)
        window.tag_model.set_tags(tags)
        _settle(app)
        _hover(window.tag_table, window.tag_visual_delegate, window.tag_proxy.index(0, TagColumn.TAG))
        window.tag_model.setData(window.tag_model.index(0, TagColumn.TAG), "red_hair", Qt.ItemDataRole.EditRole)
        _require(not window.tag_visual_delegate.card.isVisible(), "edit left stale hover")
        _require(window.tag_model.visual_at(0).label_zh == "红色头发", "edit did not refresh descriptor")
        report["checks"]["edit_updates_and_closes_hover"] = True
        before = window.tag_model.tags
        window.tag_visuals_check.setChecked(False)
        _require(window.tag_model.index(0, TagColumn.TAG).data(Qt.ItemDataRole.DecorationRole) is None, "table toggle failed")
        _require(window.random_prompt_panel.tag_list.tag_model.index(0).data(Qt.ItemDataRole.DecorationRole) is None, "random toggle failed")
        _require(window.tag_model.tags == before, "toggle modified business tags")
        _require(settings.value("tag_visuals/enabled", True, type=bool) is False, "toggle was not saved")
        window.tag_visuals_check.setChecked(True)
        report["checks"]["shared_toggle_and_persistence"] = True

        # A real view paints/scrolls thousands of rows with a bounded bitmap cache.
        bulk = tuple(TagResult(v.key, .9, TagCategory.GENERAL) for v in supported if v.category == "general")
        window.tag_model.set_tags(bulk)
        _settle(app)
        scroll = window.tag_table.verticalScrollBar()
        start = time.perf_counter()
        for step in range(61):
            scroll.setValue(round(scroll.maximum()*step/60))
            app.processEvents()
        report["checks"]["scroll"] = {"rows": len(bulk), "positions": 61,
                                              "seconds": round(time.perf_counter()-start, 3), "cache": len(provider._cache)}
        _require(len(provider._cache) <= 544, "unbounded bitmap cache")
        report["checks"]["48_samples"] = 48
        report["passed"] = True
    except Exception as exc:
        logging.getLogger(__name__).exception("Tag visual smoke failed")
        report["passed"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if window is not None:
            window.close()
            for _ in range(20):
                if not window.controller.is_running:
                    break
                _settle(app)
        for item in report["screenshots"]:
            item["sha256"] = hashlib.sha256((output / item["file"]).read_bytes()).hexdigest()
        (output / "visual-smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return 0 if report["passed"] else 1
