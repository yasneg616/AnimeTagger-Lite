from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
import pytest

from app.config.settings import AppSettings
from app.prompts.random_buckets import RandomBucket
from app.prompts.random_prompt import RandomPromptGenerator
from app.ui.main_window import MainWindow
from app.ui.random_prompt_panel import RandomPromptPanel


def _write_csv(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["tag_id,name,category,count"]
    lines.extend(",".join(row) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def model_root(tmp_path: Path) -> Path:
    wd = tmp_path / "models" / "wd-vit-tagger-v3"
    _write_csv(
        wd / "selected_tags.csv",
        [
            ("9999999", "general", "9", "1"),
            ("1", "1girl", "0", "100"),
            ("2", "solo", "0", "90"),
            ("3", "blue_hair", "0", "50"),
            ("4", "censored", "0", "80"),
            ("5", "uncensored", "0", "40"),
            ("6", "alice", "4", "70"),
            ("7", "wonderland", "3", "60"),
            ("8", "dress", "0", "75"),
            ("9", "hat", "0", "40"),
            ("10", "outdoors", "0", "55"),
        ],
    )
    (wd / "model.onnx").write_bytes(b"x")
    return tmp_path


def test_main_window_has_random_prompt_tab(qtbot, tmp_path: Path) -> None:
    widget = MainWindow(
        settings=AppSettings(model_dir=str(tmp_path / "missing-model")),
        settings_path=tmp_path / "settings.json",
        ui_settings=QSettings(str(tmp_path / "ui.ini"), QSettings.Format.IniFormat),
    )
    qtbot.addWidget(widget)
    titles = [widget.pages.tabText(i) for i in range(widget.pages.count())]
    assert "随机 Prompt" in titles
    assert isinstance(widget.random_prompt_panel, RandomPromptPanel)
    widget.close()
    qtbot.waitUntil(lambda: not widget.controller.is_running, timeout=5000)


def test_random_prompt_panel_bucket_controls_and_generate(
    qtbot,
    model_root: Path,
) -> None:
    panel = RandomPromptPanel(
        AppSettings(),
        model_root=model_root,
        generator=RandomPromptGenerator(model_root),
    )
    qtbot.addWidget(panel)

    # Fine-grained buckets exist and allow large counts.
    assert panel.spin_for(RandomBucket.CLOTHING).maximum() >= 10_000
    assert panel.spin_for(RandomBucket.NSFW).maximum() >= 10_000
    assert panel.pool_spin.minimum() == 0

    panel.backend_combo.setCurrentIndex(panel.backend_combo.findData("wd_v3"))
    for bucket in RandomBucket:
        panel.spin_for(bucket).setValue(0)
    panel.spin_for(RandomBucket.CHARACTER).setValue(1)
    panel.spin_for(RandomBucket.CLOTHING).setValue(1)
    panel.spin_for(RandomBucket.ITEMS).setValue(1)
    panel.spin_for(RandomBucket.BACKGROUND).setValue(1)
    panel.pool_spin.setValue(0)
    panel.seed_edit.setText("7")
    panel.generate()

    text = panel.prompt_edit.toPlainText()
    assert text
    assert "alice" in text
    assert "dress" in text
    assert "hat" in text
    assert "outdoors" in text
    assert "种子 7" in panel.status_label.text()
    assert "服饰" in panel.status_label.text() or "抽中" in panel.status_label.text()

    panel.copy_prompt()
    assert QApplication.clipboard().text() == text.strip()
