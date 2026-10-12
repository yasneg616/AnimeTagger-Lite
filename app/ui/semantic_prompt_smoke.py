"""Source/frozen acceptance probe with network denied and isolated preferences."""
from dataclasses import asdict
import json
from pathlib import Path
import socket
import sys

from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.config.settings import AppSettings
from app.prompts.random_buckets import RandomBucket
from app.prompts.semantic_scene import validate_scene
from app.ui.main_window import MainWindow


def require(value, message):
    if not value:
        raise RuntimeError(message)


def run_semantic_smoke(app: QApplication, output: Path) -> int:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {"frozen": bool(getattr(sys, "frozen", False)), "platform": app.platformName(), "network": "denied", "checks": {}, "screenshots": []}
    original_connect, original_connection = socket.socket.connect, socket.create_connection
    window = None
    def denied(*args, **kwargs):
        raise RuntimeError("Runtime network access is forbidden in this probe")
    socket.socket.connect = denied
    socket.create_connection = denied
    try:
        preferences = QSettings(str(output / "probe-ui.ini"), QSettings.Format.IniFormat)
        window = MainWindow(settings=AppSettings(), settings_path=output / "probe-settings.json", ui_settings=preferences)
        window.resize(1480, 1100)
        window.pages.setCurrentWidget(window.random_prompt_panel)
        window.show()
        app.processEvents()
        panel = window.random_prompt_panel
        semantic = panel.semantic_panel
        semantic.backend_combo.setCurrentIndex(0)
        semantic.seed_edit.setText("20261010")
        semantic.actor_count.setValue(2)
        semantic.action_combo.setCurrentIndex(semantic.action_combo.findData("holding_hands"))
        semantic.generate()
        require(semantic._last_result is not None, semantic.status_label.text())
        original = semantic._last_result
        require(not validate_scene(original.scene, semantic.generator().catalog), "Invalid generated scene")
        require(original.english_prompt and original.tag_prompt, "Missing format")
        report["checks"]["native_two_subjects"] = asdict(original.scene)
        report["corpus_version"] = original.corpus_version
        report["coverage"] = semantic.generator().catalog.coverage
        for tab, filename in ((0, "semantic-tags.png"), (1, "semantic-english.png"), (2, "semantic-subjects.png")):
            semantic.results_tabs.setCurrentIndex(tab)
            app.processEvents()
            QTest.qWait(40)
            require(window.grab().save(str(output / filename)), "Screenshot failed")
            report["screenshots"].append(filename)
            require(semantic._last_result is original, "Format switch replaced the scene")
        semantic.results_tabs.setCurrentIndex(0)
        semantic.copy_prompt()
        app.processEvents()
        QTest.qWait(100)
        report["checks"]["native_tags_clipboard"] = app.clipboard().text() == original.tag_prompt
        require(report["checks"]["native_tags_clipboard"], "Tags clipboard read-back differs from the displayed prompt")
        semantic.results_tabs.setCurrentIndex(1)
        semantic.copy_prompt()
        app.processEvents()
        # Windows releases clipboard ownership through its event loop. Match
        # separate user clicks instead of racing two immediate setText calls.
        QTest.qWait(100)
        report["checks"]["native_english_clipboard"] = app.clipboard().text() == original.english_prompt
        require(semantic.english_edit.toPlainText() == original.english_prompt, "English editor changed facts")
        require(report["checks"]["native_english_clipboard"], "English clipboard read-back differs from the displayed prompt")
        report["checks"]["same_scene_on_format_switch"] = True
        semantic.actor_locks[0].setChecked(True)
        semantic.scene_lock.setChecked(True)
        semantic.seed_edit.setText("17")
        semantic.generate()
        require(semantic._last_result.scene.actors[0] == original.scene.actors[0], "Actor lock changed facts")
        require(semantic._last_result.scene.facts == original.scene.facts, "Scene lock changed facts")
        report["checks"]["locked_reroll"] = True
        before_error = semantic._last_result
        semantic.actor_tags[0].setText("red_hair, blue_hair")
        semantic.generate()
        require(semantic._last_result is before_error, "Failed generation erased the previous scene")
        report["checks"]["unsolved_retains_result"] = True
        semantic.import_edit.setPlainText("2girls, (blue_hair:1.25), red_hair, unknown_magic")
        semantic.import_tags()
        require(semantic._last_result.unassigned and not semantic.english_edit.toPlainText(), "Import guessed actor ownership")
        semantic._assignments = {1: "A1", 2: "A2"}
        semantic.import_tags()
        require(not semantic._last_result.blocking and not semantic._last_result.unassigned, "Assignment did not resolve import")
        require("(blue_hair:1.25)" in semantic.tags_edit.toPlainText(), "Weighted original lost")
        report["checks"]["weighted_unknown_multi_import"] = True
        app.processEvents()
        require(window.grab().save(str(output / "semantic-import.png")), "Import screenshot failed")
        report["screenshots"].append("semantic-import.png")
        panel.mode_combo.setCurrentIndex(1)
        panel.backend_combo.setCurrentIndex(0)
        for bucket in RandomBucket:
            panel.spin_for(bucket).setValue(0)
        panel.spin_for(RandomBucket.CHARACTER).setValue(1)
        panel.spin_for(RandomBucket.CLOTHING).setValue(2)
        panel.seed_edit.setText("21")
        panel.generate()
        require(panel.prompt_edit.toPlainText(), panel.status_label.text())
        panel.copy_prompt()
        app.processEvents()
        QTest.qWait(100)
        report["checks"]["native_legacy_clipboard"] = app.clipboard().text() == panel.prompt_edit.toPlainText().strip()
        require(report["checks"]["native_legacy_clipboard"], "Legacy clipboard read-back differs from the displayed prompt")
        report["checks"]["legacy_mode_generate"] = True
        app.processEvents()
        require(window.grab().save(str(output / "legacy-mode.png")), "Legacy screenshot failed")
        report["screenshots"].append("legacy-mode.png")
        report["status"] = "passed"
    except Exception as exc:
        report.update(status="failed", error=repr(exc))
    finally:
        socket.socket.connect, socket.create_connection = original_connect, original_connection
        if window:
            window.close()
            for _ in range(100):
                app.processEvents()
                QTest.qWait(30)
                if not window.controller.is_running and window.decoder.shutdown(wait_ms=0):
                    break
        (output / "semantic-smoke.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["status"] == "passed" else 1
