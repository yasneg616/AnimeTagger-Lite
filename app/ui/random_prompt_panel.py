"""Random prompt page: sample tags from local model tag libraries."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import AppSettings
from app.errors import AnimeTaggerError
from app.inference.backends import BACKENDS
from app.prompts.random_buckets import BUCKET_LABELS, RandomBucket
from app.prompts.random_prompt import (
    RandomPromptGenerator,
    RandomPromptRequest,
    RandomPromptResult,
)
from app.runtime_paths import APPLICATION_ROOT
from app.ui.tag_visual_widgets import TagListView, TagVisualProvider

# (bucket, default count) — UI label comes from BUCKET_LABELS.
_BUCKET_DEFAULTS: tuple[tuple[RandomBucket, int], ...] = (
    (RandomBucket.CHARACTER, 1),
    (RandomBucket.COPYRIGHT, 0),
    (RandomBucket.HAIR, 1),
    (RandomBucket.BODY, 0),
    (RandomBucket.CLOTHING, 2),
    (RandomBucket.ITEMS, 1),
    (RandomBucket.POSE, 1),
    (RandomBucket.BACKGROUND, 1),
    (RandomBucket.NSFW, 0),
    (RandomBucket.OTHER, 2),
)


class RandomPromptPanel(QWidget):
    def __init__(
        self,
        settings: AppSettings,
        parent: QWidget | None = None,
        *,
        model_root: Path | None = None,
        generator: RandomPromptGenerator | None = None,
        visual_provider: TagVisualProvider | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        # BACKENDS[...].directory is relative to the application root.
        self._model_root = Path(model_root or APPLICATION_ROOT)
        self._generator = generator or RandomPromptGenerator(self._model_root)
        self._last_result: RandomPromptResult | None = None
        self.visual_provider = visual_provider if visual_provider is not None else TagVisualProvider(self)
        self._bucket_spins: dict[RandomBucket, QSpinBox] = {}
        self._build_ui()
        self._sync_backend_default(settings.backend)

    def _make_spin(self, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, 1_000_000)
        spin.setValue(value)
        return spin

    def _build_ui(self) -> None:
        self.backend_combo = QComboBox()
        self.backend_combo.setObjectName("randomBackendCombo")
        self.backend_combo.addItem("全部本地标签库", "")
        for backend, spec in BACKENDS.items():
            self.backend_combo.addItem(spec.label, backend)

        self.pool_spin = QSpinBox()
        self.pool_spin.setObjectName("randomPoolSpin")
        self.pool_spin.setRange(0, 1_000_000)
        self.pool_spin.setSingleStep(50)
        self.pool_spin.setSpecialValueText("全部")
        self.pool_spin.setValue(2500)
        self.seed_edit = QLineEdit()
        self.seed_edit.setObjectName("randomSeedEdit")
        self.seed_edit.setPlaceholderText("留空则自动随机")
        self.prefer_popular = QCheckBox("偏向高频标签")
        self.prefer_popular.setChecked(True)
        self.allow_censored = QCheckBox("允许 censor 类标签")
        self.allow_censored.setChecked(False)
        self.underscore_check = QCheckBox("下划线转空格")
        self.underscore_check.setChecked(False)

        top_form = QFormLayout()
        top_form.addRow("标签库", self.backend_combo)
        top_form.addRow("候选池 Top N（0=全部）", self.pool_spin)
        top_form.addRow("种子", self.seed_edit)
        top_form.addRow("", self.prefer_popular)
        top_form.addRow("", self.allow_censored)
        top_form.addRow("", self.underscore_check)

        count_box = QGroupBox("各类标签数量")
        grid = QGridLayout(count_box)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for index, (bucket, default) in enumerate(_BUCKET_DEFAULTS):
            spin = self._make_spin(default)
            spin.setObjectName(f"randomSpin_{bucket.value}")
            spin.setToolTip(f"{BUCKET_LABELS[bucket]} 标签抽样数量；0 表示不抽")
            self._bucket_spins[bucket] = spin
            row, col = divmod(index, 2)
            grid.addWidget(QLabel(f"{BUCKET_LABELS[bucket]}"), row, col * 2)
            grid.addWidget(spin, row, col * 2 + 1)

        options = QGroupBox("生成参数")
        options_layout = QVBoxLayout(options)
        options_layout.addLayout(top_form)
        options_layout.addWidget(count_box)

        self.generate_button = QPushButton("随机生成 Prompt")
        self.generate_button.setObjectName("randomGenerateButton")
        self.copy_button = QPushButton("复制 Prompt")
        self.copy_button.setObjectName("randomCopyButton")
        self.generate_button.clicked.connect(self.generate)
        self.copy_button.clicked.connect(self.copy_prompt)

        actions = QHBoxLayout()
        actions.addWidget(self.generate_button)
        actions.addWidget(self.copy_button)
        actions.addStretch(1)

        self.status_label = QLabel("从本地模型标签库按类别随机搭配；不会联网。")
        self.status_label.setObjectName("randomStatus")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #9da7b3;")

        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setObjectName("randomPromptEdit")
        self.prompt_edit.setPlaceholderText("点击「随机生成 Prompt」后在此预览")
        self.prompt_edit.setMinimumHeight(100)

        self.tag_list = TagListView(self.visual_provider)
        self.tag_list.setMinimumHeight(100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(QLabel("随机 Prompt"))
        layout.addWidget(options)
        layout.addLayout(actions)
        layout.addWidget(self.status_label)
        layout.addWidget(QLabel("提示词预览"), 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.prompt_edit, 1)
        layout.addWidget(QLabel("抽中标签"), 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.tag_list, 1)

    def _sync_backend_default(self, backend: str) -> None:
        index = self.backend_combo.findData(backend)
        self.backend_combo.setCurrentIndex(index if index >= 0 else 0)

    def set_settings(self, settings: AppSettings) -> None:
        self._settings = settings
        self._sync_backend_default(settings.backend)

    def spin_for(self, bucket: RandomBucket) -> QSpinBox:
        return self._bucket_spins[bucket]

    def _request(self) -> RandomPromptRequest:
        backend = self.backend_combo.currentData()
        backends = (backend,) if backend else tuple(BACKENDS)
        seed_text = self.seed_edit.text().strip()
        seed: int | None
        if not seed_text:
            seed = None
        else:
            try:
                seed = int(seed_text)
            except ValueError as exc:
                raise AnimeTaggerError("种子必须是整数，或留空。") from exc
        counts = {
            bucket: spin.value() for bucket, spin in self._bucket_spins.items()
        }
        return RandomPromptRequest(
            backends=backends,
            character_count=counts[RandomBucket.CHARACTER],
            copyright_count=counts[RandomBucket.COPYRIGHT],
            hair_count=counts[RandomBucket.HAIR],
            body_count=counts[RandomBucket.BODY],
            clothing_count=counts[RandomBucket.CLOTHING],
            item_count=counts[RandomBucket.ITEMS],
            pose_count=counts[RandomBucket.POSE],
            background_count=counts[RandomBucket.BACKGROUND],
            nsfw_count=counts[RandomBucket.NSFW],
            other_count=counts[RandomBucket.OTHER],
            pool_top_n=self.pool_spin.value(),
            seed=seed,
            allow_censored=self.allow_censored.isChecked(),
            prefer_popular=self.prefer_popular.isChecked(),
            underscore_to_space=self.underscore_check.isChecked(),
        )

    def generate(self) -> None:
        try:
            request = self._request()
            result = self._generator.generate(request)
        except AnimeTaggerError as exc:
            self.status_label.setText(str(exc))
            self.status_label.setStyleSheet("color: #ff7373;")
            return
        except Exception as exc:  # pragma: no cover - defensive UI path
            self.status_label.setText(f"生成失败：{exc}")
            self.status_label.setStyleSheet("color: #ff7373;")
            return

        self._last_result = result
        self.prompt_edit.setPlainText(result.prompt)
        self.tag_list.set_tags(result.tags)
        pools = result.pools
        buckets = result.buckets
        pool_bits = " · ".join(
            f"{BUCKET_LABELS[b]}={pools.get(b.value, 0)}"
            for b, _ in _BUCKET_DEFAULTS
            if pools.get(b.value, 0)
        )
        picked_bits = " ".join(
            f"{BUCKET_LABELS[RandomBucket(k)]}×{v}" for k, v in buckets.items()
        )
        self.status_label.setText(
            f"种子 {result.seed} · 来源 {', '.join(result.sources)}\n"
            f"候选池：{pool_bits or '空'}\n"
            f"抽中：{picked_bits or '无'}"
        )
        self.status_label.setStyleSheet("color: #9da7b3;")

    def copy_prompt(self) -> None:
        text = self.prompt_edit.toPlainText().strip()
        if not text:
            self.status_label.setText("尚无可复制的提示词。")
            self.status_label.setStyleSheet("color: #e4b45d;")
            return
        QApplication.clipboard().setText(text)
        self.status_label.setText("已复制到剪贴板。")
        self.status_label.setStyleSheet("color: #64d98b;")
