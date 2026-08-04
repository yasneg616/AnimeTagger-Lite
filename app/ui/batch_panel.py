"""Independent stage 4 folder batch page."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Signal, Slot
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from app.batch.exporter import BatchOutputWriter
from app.batch.manifest import ManifestStore
from app.batch.models import (
    BatchConfig,
    BatchItem,
    BatchJob,
    BatchJobStatus,
    BatchTextFormat,
    CaptionPolicy,
    OutputMode,
    ScanOptions,
)
from app.config.settings import AppSettings, PROJECT_ROOT
from app.errors import AnimeTaggerError
from app.ui.batch_filter_proxy import BatchFilterProxyModel
from app.ui.batch_table_model import BatchTableModel
from app.ui.workers.inference_worker import (
    BatchScanRequest,
    InferenceController,
)
from app.runtime_paths import BATCH_JOBS_DIR, IS_PORTABLE


class BatchPanel(QWidget):
    activity_changed = Signal()

    def __init__(
        self,
        controller: InferenceController,
        settings: AppSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("batchPanel")
        self.controller = controller
        self.base_settings = settings
        self.job: BatchJob | None = None
        self._build_ui()
        self._connect_signals()
        self._show_recovery_notice()
        self._refresh_buttons()

    def _build_ui(self) -> None:
        self.roots = QListWidget()
        self.roots.setObjectName("batchRoots")
        self.roots.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.add_root_button = QPushButton("添加文件夹")
        self.add_root_button.setObjectName("batchAddRoot")
        self.remove_root_button = QPushButton("移除所选")
        self.clear_roots_button = QPushButton("清空")
        root_buttons = QHBoxLayout()
        root_buttons.addWidget(self.add_root_button)
        root_buttons.addWidget(self.remove_root_button)
        root_buttons.addWidget(self.clear_roots_button)
        roots_box = QGroupBox("输入目录（可添加多个）")
        roots_layout = QVBoxLayout(roots_box)
        roots_layout.addWidget(self.roots)
        roots_layout.addLayout(root_buttons)

        self.recursive_check = QCheckBox("递归子目录")
        self.recursive_check.setObjectName("batchRecursive")
        self.hidden_check = QCheckBox("包含隐藏文件")
        self.symlink_check = QCheckBox("跟随符号链接")
        self.max_files_spin = QSpinBox()
        self.max_files_spin.setRange(1, 1_000_000)
        self.max_files_spin.setValue(100_000)
        self.output_mode_combo = QComboBox()
        self.output_mode_combo.setObjectName("batchOutputMode")
        for label, value in (
            ("原图同目录", OutputMode.BESIDE),
            ("镜像目录", OutputMode.MIRROR),
            ("扁平目录", OutputMode.FLAT),
        ):
            self.output_mode_combo.addItem(label, value.value)
        self.output_root_edit = QLineEdit()
        self.output_root_edit.setObjectName("batchOutputRoot")
        self.output_root_button = QPushButton("选择…")
        output_row = QWidget()
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.addWidget(self.output_root_edit, 1)
        output_layout.addWidget(self.output_root_button)

        scan_form = QFormLayout()
        scan_options = QWidget()
        scan_options.setLayout(scan_form)
        scan_form.addRow("", self.recursive_check)
        scan_form.addRow("", self.hidden_check)
        scan_form.addRow("", self.symlink_check)
        scan_form.addRow("最多图片", self.max_files_spin)
        scan_form.addRow("输出模式", self.output_mode_combo)
        scan_form.addRow("输出目录", output_row)

        self.profile_combo = QComboBox()
        for profile in ("raw", "anime", "pony", "lora_caption"):
            self.profile_combo.addItem(profile, profile)
        self.lora_check = QCheckBox("LoRA Caption 模式")
        self.lora_check.setObjectName("batchLoraMode")
        self.lora_check.setChecked(True)
        self.trigger_edit = QLineEdit()
        self.trigger_edit.setObjectName("batchTriggerWord")
        self.trigger_edit.setPlaceholderText("例如 yaseng_style（可选）")
        self.trigger_position_combo = QComboBox()
        self.trigger_position_combo.addItem("最前", "first")
        self.trigger_position_combo.addItem("最后", "last")
        self.general_spin = QDoubleSpinBox()
        self.general_spin.setRange(0.0, 1.0)
        self.general_spin.setSingleStep(0.05)
        self.general_spin.setValue(settings_value(self.base_settings, "general_threshold"))
        self.character_spin = QDoubleSpinBox()
        self.character_spin.setRange(0.0, 1.0)
        self.character_spin.setSingleStep(0.05)
        self.character_spin.setValue(
            settings_value(self.base_settings, "character_threshold")
        )
        self.max_tags_spin = QSpinBox()
        self.max_tags_spin.setRange(1, 1000)
        self.max_tags_spin.setValue(self.base_settings.max_tags)
        self.character_check = QCheckBox("保留 Character 标签")
        self.character_check.setChecked(self.base_settings.include_character_tags)
        self.rating_check = QCheckBox("保留 Rating 标签")
        self.rating_check.setChecked(False)
        self.exclude_edit = QLineEdit()
        self.exclude_edit.setPlaceholderText("逗号分隔")
        self.remove_edit = QLineEdit()
        self.remove_edit.setPlaceholderText("逗号分隔")
        self.always_edit = QLineEdit()
        self.always_edit.setPlaceholderText("逗号分隔")

        caption_form = QFormLayout()
        caption_options = QWidget()
        caption_options.setLayout(caption_form)
        caption_form.addRow("", self.lora_check)
        caption_form.addRow("Profile", self.profile_combo)
        caption_form.addRow("Trigger word", self.trigger_edit)
        caption_form.addRow("Trigger 位置", self.trigger_position_combo)
        caption_form.addRow("General 阈值", self.general_spin)
        caption_form.addRow("Character 阈值", self.character_spin)
        caption_form.addRow("最大标签数", self.max_tags_spin)
        caption_form.addRow("", self.character_check)
        caption_form.addRow("", self.rating_check)
        caption_form.addRow("排除标签", self.exclude_edit)
        caption_form.addRow("删除标签", self.remove_edit)
        caption_form.addRow("固定保留", self.always_edit)

        self.policy_combo = QComboBox()
        self.policy_combo.setObjectName("batchCaptionPolicy")
        for policy in CaptionPolicy:
            self.policy_combo.addItem(policy.value, policy.value)
        self.text_format_combo = QComboBox()
        self.text_format_combo.addItem("同名 TXT Caption", BatchTextFormat.TXT.value)
        self.text_format_combo.addItem(
            "正负 Prompt TXT",
            BatchTextFormat.PROMPT_TXT.value,
        )
        self.caption_check = QCheckBox("逐图 TXT")
        self.caption_check.setChecked(True)
        self.json_check = QCheckBox("逐图 JSON")
        self.csv_check = QCheckBox("CSV 汇总")
        self.csv_check.setChecked(True)
        self.csv_bom_check = QCheckBox("CSV UTF-8 BOM")
        self.summary_json_check = QCheckBox("单个汇总 JSON")
        export_checks = QWidget()
        export_grid = QGridLayout(export_checks)
        export_grid.setContentsMargins(0, 0, 0, 0)
        export_grid.addWidget(self.caption_check, 0, 0)
        export_grid.addWidget(self.json_check, 0, 1)
        export_grid.addWidget(self.csv_check, 1, 0)
        export_grid.addWidget(self.summary_json_check, 1, 1)
        export_grid.addWidget(self.csv_bom_check, 2, 0)
        export_form = QFormLayout()
        export_options = QWidget()
        export_options.setLayout(export_form)
        export_form.addRow("已有 Caption", self.policy_combo)
        export_form.addRow("TXT 格式", self.text_format_combo)
        export_form.addRow("导出", export_checks)

        options = QWidget()
        options_layout = QVBoxLayout(options)
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.addWidget(roots_box, 1)
        options_layout.addWidget(scan_options)
        options_layout.addWidget(caption_options)
        options_layout.addWidget(export_options)

        self.scan_button = QPushButton("扫描 / Dry-run 预览")
        self.scan_button.setObjectName("batchScan")
        self.open_manifest_button = QPushButton("打开 Manifest")
        self.start_button = QPushButton("开始批处理")
        self.start_button.setObjectName("batchStart")
        self.pause_button = QPushButton("暂停")
        self.resume_button = QPushButton("继续")
        self.cancel_button = QPushButton("取消")
        self.retry_button = QPushButton("重试失败项")
        self.report_button = QPushButton("导出报告")
        self.clear_job_button = QPushButton("清除任务")
        buttons = QHBoxLayout()
        for button in (
            self.scan_button,
            self.open_manifest_button,
            self.start_button,
            self.pause_button,
            self.resume_button,
            self.cancel_button,
            self.retry_button,
            self.report_button,
            self.clear_job_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch(1)

        self.summary_label = QLabel(
            "先扫描以查看预计处理、跳过和覆盖范围；扫描不会加载模型或写文件。"
        )
        self.summary_label.setObjectName("batchSummary")
        self.summary_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setObjectName("batchProgress")
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索文件、相对路径或格式")
        self.status_filter = QComboBox()
        self.status_filter.addItem("全部状态", "")
        for status in (
            "pending",
            "analyzing",
            "exporting",
            "completed",
            "skipped",
            "failed",
            "cancelled",
            "missing",
        ):
            self.status_filter.addItem(status, status)
        self.existing_only_check = QCheckBox("仅已有 Caption")
        self.skip_only_check = QCheckBox("仅将跳过")
        self.select_all_button = QPushButton("全选")
        self.select_none_button = QPushButton("全不选")
        self.invert_button = QPushButton("反选")
        self.remove_items_button = QPushButton("移除所选任务项")
        filters = QHBoxLayout()
        filters.addWidget(self.search_edit, 2)
        filters.addWidget(self.status_filter)
        filters.addWidget(self.existing_only_check)
        filters.addWidget(self.skip_only_check)
        filters.addWidget(self.select_all_button)
        filters.addWidget(self.select_none_button)
        filters.addWidget(self.invert_button)
        filters.addWidget(self.remove_items_button)
        self.table_model = BatchTableModel(self)
        self.table_proxy = BatchFilterProxyModel(self)
        self.table_proxy.setSourceModel(self.table_model)
        self.table = QTableView()
        self.table.setObjectName("batchTable")
        self.table.setModel(self.table_proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.horizontalHeader().setStretchLastSection(True)

        result = QWidget()
        result_layout = QVBoxLayout(result)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.addLayout(buttons)
        result_layout.addWidget(self.summary_label)
        result_layout.addWidget(self.progress)
        result_layout.addLayout(filters)
        result_layout.addWidget(self.table, 1)

        self.options_widget = options
        self.options_scroll = QScrollArea()
        self.options_scroll.setObjectName("batchOptionsScroll")
        self.options_scroll.setWidgetResizable(True)
        self.options_scroll.setWidget(options)
        splitter = QSplitter()
        splitter.addWidget(self.options_scroll)
        splitter.addWidget(result)
        splitter.setSizes([390, 950])
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

    def _connect_signals(self) -> None:
        self.add_root_button.clicked.connect(self._choose_root)
        self.remove_root_button.clicked.connect(self._remove_selected_roots)
        self.clear_roots_button.clicked.connect(self._clear_roots)
        self.output_root_button.clicked.connect(self._choose_output_root)
        self.output_mode_combo.currentIndexChanged.connect(
            self._sync_output_root_state
        )
        self.lora_check.toggled.connect(self._sync_lora_state)
        self.scan_button.clicked.connect(self.scan)
        self.open_manifest_button.clicked.connect(self._choose_manifest)
        self.start_button.clicked.connect(self.start)
        self.pause_button.clicked.connect(self.pause)
        self.resume_button.clicked.connect(self.resume)
        self.cancel_button.clicked.connect(self.cancel)
        self.retry_button.clicked.connect(self.retry_failed)
        self.report_button.clicked.connect(self.export_report)
        self.clear_job_button.clicked.connect(self.clear_job)
        self.search_edit.textChanged.connect(self.table_proxy.set_search)
        self.status_filter.currentIndexChanged.connect(
            lambda _index: self.table_proxy.set_status(
                str(self.status_filter.currentData())
            )
        )
        self.existing_only_check.toggled.connect(
            self.table_proxy.set_existing_only
        )
        self.skip_only_check.toggled.connect(self.table_proxy.set_skip_only)
        self.select_all_button.clicked.connect(
            lambda: self.table_model.set_all_selected(True)
        )
        self.select_none_button.clicked.connect(
            lambda: self.table_model.set_all_selected(False)
        )
        self.invert_button.clicked.connect(self.table_model.invert_selected)
        self.remove_items_button.clicked.connect(self._remove_selected_items)
        for combo in (
            self.output_mode_combo,
            self.profile_combo,
            self.trigger_position_combo,
            self.policy_combo,
            self.text_format_combo,
        ):
            combo.currentIndexChanged.connect(self._invalidate_preview)
        for check in (
            self.recursive_check,
            self.hidden_check,
            self.symlink_check,
            self.lora_check,
            self.character_check,
            self.rating_check,
            self.caption_check,
            self.json_check,
            self.csv_check,
            self.csv_bom_check,
            self.summary_json_check,
        ):
            check.toggled.connect(self._invalidate_preview)
        for spin in (
            self.max_files_spin,
            self.general_spin,
            self.character_spin,
            self.max_tags_spin,
        ):
            spin.valueChanged.connect(self._invalidate_preview)
        for edit in (
            self.output_root_edit,
            self.trigger_edit,
            self.exclude_edit,
            self.remove_edit,
            self.always_edit,
        ):
            edit.textChanged.connect(self._invalidate_preview)

        self.controller.batch_scan_progress.connect(self._on_scan_progress)
        self.controller.batch_scan_completed.connect(self._on_scan_completed)
        self.controller.batch_item_changed.connect(self._on_item_changed)
        self.controller.batch_job_changed.connect(self._on_job_changed)
        self.controller.batch_completed.connect(self._on_batch_completed)
        self.controller.batch_retry_ready.connect(self._on_retry_ready)
        self.controller.batch_failed.connect(self._on_failed)
        self.controller.busy_changed.connect(lambda _busy: self._refresh_buttons())
        self._sync_output_root_state()
        self._sync_lora_state(self.lora_check.isChecked())

    def set_base_settings(self, settings: AppSettings) -> None:
        self.base_settings = settings

    def add_root(self, path: Path) -> bool:
        resolved = Path(path).expanduser().resolve(strict=False)
        existing = {
            self.roots.item(index).text().casefold()
            for index in range(self.roots.count())
        }
        if str(resolved).casefold() in existing:
            return False
        self.roots.addItem(str(resolved))
        self._invalidate_preview()
        self._refresh_buttons()
        return True

    @Slot()
    def _choose_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "添加批处理文件夹",
            self.base_settings.recent_open_dir or str(Path.home()),
        )
        if selected:
            self.add_root(Path(selected))

    @Slot()
    def _remove_selected_roots(self) -> None:
        for item in self.roots.selectedItems():
            self.roots.takeItem(self.roots.row(item))
        self._invalidate_preview()
        self._refresh_buttons()

    @Slot()
    def _clear_roots(self) -> None:
        self.roots.clear()
        self._invalidate_preview()
        self._refresh_buttons()

    @Slot()
    def _invalidate_preview(self, *_args) -> None:
        if self.job is None or self.controller.is_busy:
            return
        self.job = None
        self.table_model.set_job(None)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.summary_label.setText(
            "批处理设置已改变；请重新扫描以确认新的处理与覆盖范围。"
        )
        self._refresh_buttons()

    @Slot()
    def _choose_output_root(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "选择批处理输出目录",
            self.output_root_edit.text()
            or self.base_settings.default_export_dir
            or str(Path.home()),
        )
        if selected:
            self.output_root_edit.setText(selected)

    @Slot()
    def _choose_manifest(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "打开批处理 Manifest",
            self.base_settings.default_export_dir or str(Path.home()),
            "AnimeTagger Manifest (*.manifest.json);;JSON (*.json)",
        )
        if selected:
            self.load_manifest(Path(selected))

    def load_manifest(self, path: Path) -> bool:
        try:
            store = ManifestStore()
            job = store.load(path)
            store.warn_if_settings_changed(job, self.base_settings)
        except AnimeTaggerError as exc:
            self._on_failed(str(exc))
            return False
        self.job = job
        self.table_proxy.set_caption_policy(job.config.caption_policy)
        self.table_model.set_job(job)
        self.progress.setRange(0, max(1, len(job.items)))
        self.progress.setValue(
            sum(
                item.status.value in {"completed", "skipped"}
                for item in job.items
            )
        )
        self._show_job_summary(job, prefix="已恢复")
        self._refresh_buttons()
        return True

    def _build_request(self) -> BatchScanRequest:
        roots = tuple(
            Path(self.roots.item(index).text())
            for index in range(self.roots.count())
        )
        output_root_text = self.output_root_edit.text().strip()
        output_root = Path(output_root_text) if output_root_text else None
        mode = OutputMode(str(self.output_mode_combo.currentData()))
        config = BatchConfig(
            output_mode=mode,
            output_root=output_root,
            caption_policy=CaptionPolicy(str(self.policy_combo.currentData())),
            text_format=BatchTextFormat(
                str(self.text_format_combo.currentData())
            ),
            write_captions=self.caption_check.isChecked(),
            write_json=self.json_check.isChecked(),
            write_csv=self.csv_check.isChecked(),
            write_summary_json=self.summary_json_check.isChecked(),
            csv_bom=self.csv_bom_check.isChecked(),
        )
        settings = replace(
            self.base_settings,
            profile=(
                "lora_caption"
                if self.lora_check.isChecked()
                else str(self.profile_combo.currentData())
            ),
            add_profile_prefix=not self.lora_check.isChecked(),
            negative_mode=(
                "none"
                if self.lora_check.isChecked()
                else self.base_settings.negative_mode
            ),
            trigger_word=self.trigger_edit.text().strip() or None,
            trigger_word_position=str(
                self.trigger_position_combo.currentData()
            ),
            general_threshold=self.general_spin.value(),
            character_threshold=self.character_spin.value(),
            max_tags=self.max_tags_spin.value(),
            include_character_tags=self.character_check.isChecked(),
            include_rating=self.rating_check.isChecked(),
            excluded_tags=_comma_values(self.exclude_edit.text()),
            remove_tags=_comma_values(self.remove_edit.text()),
            always_include_tags=_comma_values(self.always_edit.text()),
        )
        options = ScanOptions(
            roots=roots,
            recursive=self.recursive_check.isChecked(),
            include_hidden=self.hidden_check.isChecked(),
            follow_symlinks=self.symlink_check.isChecked(),
            max_files=self.max_files_spin.value(),
            output_root=output_root,
        )
        return BatchScanRequest(options, config, settings)

    @Slot()
    def scan(self) -> None:
        try:
            request = self._build_request()
        except AnimeTaggerError as exc:
            self._on_failed(str(exc))
            return
        self.job = None
        self.table_model.set_job(None)
        self.progress.setRange(0, 0)
        self.summary_label.setText("正在后台扫描；不会解码图片、加载模型或写入文件…")
        if not self.controller.start_batch_scan(request):
            self._on_failed("当前模型或队列操作尚未结束，暂时不能扫描。")
            return
        self.activity_changed.emit()
        self._refresh_buttons()

    @Slot()
    def start(self) -> None:
        if self.job is None or not self.job.items:
            self._on_failed("请先完成扫描并确认预览。")
            return
        if not self.controller.is_model_loaded:
            self._on_failed("请先在单图页加载有效模型；dry-run 扫描无需模型。")
            return
        preview = _preview_counts(self.job)
        policy = self.job.config.caption_policy
        if policy is not CaptionPolicy.SKIP and preview["existing"] > 0:
            answer = QMessageBox.warning(
                self,
                "确认修改已有 Caption",
                f"策略 {policy.value} 将修改 {preview['existing']} 个已有 Caption。\n"
                "原始图片不会被修改。是否继续？",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        if not self.controller.start_batch(self.job):
            self._on_failed("当前模型或队列操作尚未结束，不能重复启动批处理。")
            return
        self.summary_label.setText(
            f"正在处理 {len(self.job.items)} 张；"
            f"策略={policy.value}；原始图片只读。"
        )
        self.activity_changed.emit()
        self._refresh_buttons()

    @Slot()
    def pause(self) -> None:
        if self.controller.pause_batch():
            self.summary_label.setText("将在当前图片完成后暂停。")
            self._refresh_buttons()

    @Slot()
    def resume(self) -> None:
        if self.controller.resume_batch():
            self.summary_label.setText("批处理已继续。")
            self._refresh_buttons()

    @Slot()
    def cancel(self) -> None:
        if self.controller.cancel():
            self.summary_label.setText("将在当前扫描项或 ONNX 调用完成后安全取消。")
            self._refresh_buttons()

    @Slot()
    def retry_failed(self) -> None:
        if self.job is not None and not self.controller.retry_batch(self.job):
            self._on_failed("当前任务仍在运行，暂时不能重试。")

    @Slot()
    def export_report(self) -> None:
        if self.job is None:
            self._on_failed("当前没有可导出的任务。")
            return
        initial = str(
            self.job.summary_csv_path
            or Path(self.base_settings.default_export_dir or Path.home())
            / f"batch-{self.job.id}.csv"
        )
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "导出批处理 CSV 报告",
            initial,
            "CSV (*.csv)",
        )
        if not selected:
            return
        target = Path(selected)
        overwrite = False
        if target.exists():
            answer = QMessageBox.warning(
                self,
                "确认覆盖报告",
                f"CSV 已存在，将使用原子替换：\n{target}",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            overwrite = True
        previous = self.job.config
        self.job.config = replace(previous, overwrite_reports=overwrite)
        try:
            BatchOutputWriter().write_csv(self.job, target)
        except AnimeTaggerError as exc:
            self._on_failed(str(exc))
            return
        finally:
            self.job.config = previous
        self.job.summary_csv_path = target
        self.summary_label.setText(f"CSV 报告已导出：{target}")

    @Slot()
    def clear_job(self) -> None:
        if self.controller.is_busy:
            return
        self.job = None
        self.table_model.set_job(None)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.summary_label.setText("任务已清除；原始图片和输出文件均未删除。")
        self._refresh_buttons()

    @Slot()
    def _remove_selected_items(self) -> None:
        if self.job is None or self.controller.is_busy:
            return
        rows = {
            self.table_proxy.mapToSource(index).row()
            for index in self.table.selectionModel().selectedRows()
        }
        if not rows:
            return
        self.job.items = [
            item
            for row, item in enumerate(self.job.items)
            if row not in rows
        ]
        self.table_model.set_job(self.job)
        self._show_job_summary(self.job, prefix="预览已更新")
        self._refresh_buttons()

    @Slot(int, str)
    def _on_scan_progress(self, count: int, path: str) -> None:
        self.summary_label.setText(f"正在扫描：已发现 {count} 张；{path}")

    @Slot(object)
    def _on_scan_completed(self, job_object: object) -> None:
        if not isinstance(job_object, BatchJob):
            self._on_failed("扫描返回了无效任务。")
            return
        self.job = job_object
        self.table_proxy.set_caption_policy(job_object.config.caption_policy)
        self.table_model.set_job(self.job)
        self.progress.setRange(0, max(1, len(self.job.items)))
        self.progress.setValue(0)
        self._show_job_summary(self.job, prefix="Dry-run")
        self.activity_changed.emit()
        self._refresh_buttons()

    @Slot(object, int, int)
    def _on_item_changed(
        self,
        item_object: object,
        position: int,
        total: int,
    ) -> None:
        if isinstance(item_object, BatchItem):
            self.table_model.update_item(item_object, position, total)
            if position > 0:
                self.progress.setRange(0, max(1, total))
                self.progress.setValue(position)

    @Slot(object)
    def _on_job_changed(self, job_object: object) -> None:
        if isinstance(job_object, BatchJob):
            self.job = job_object
            self._show_job_summary(job_object)
            self._refresh_buttons()

    @Slot(object)
    def _on_batch_completed(self, job_object: object) -> None:
        if isinstance(job_object, BatchJob):
            self.job = job_object
            self._show_job_summary(job_object, prefix="完成")
            self.progress.setValue(len(job_object.items))
        self.activity_changed.emit()
        self._refresh_buttons()

    @Slot(object, int)
    def _on_retry_ready(self, job_object: object, count: int) -> None:
        if isinstance(job_object, BatchJob):
            self.job = job_object
            self.table_proxy.set_caption_policy(
                job_object.config.caption_policy
            )
            self.table_model.set_job(job_object)
        self.summary_label.setText(f"已重置 {count} 个失败/取消条目，可再次开始。")
        self._refresh_buttons()

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self.summary_label.setText(f"批处理错误：{message}")
        self.progress.setRange(0, 1)
        self.activity_changed.emit()
        self._refresh_buttons()

    def _show_job_summary(
        self,
        job: BatchJob,
        *,
        prefix: str = "",
    ) -> None:
        counts = job.counts()
        preview = _preview_counts(job)
        elapsed = [
            item.inference_time_ms
            for item in job.items
            if item.inference_time_ms is not None
        ]
        average = sum(elapsed) / len(elapsed) if elapsed else 0.0
        providers = sorted({item.provider for item in job.items if item.provider})
        lead = f"{prefix}：" if prefix else ""
        self.summary_label.setText(
            f"{lead}{counts['total']} 张；已有 Caption {preview['existing']}；"
            f"预计跳过 {preview['skipped']}；状态={job.status.value}；"
            f"完成 {counts['completed']}，失败 "
            f"{counts['failed'] + counts['missing']}，取消 {counts['cancelled']}；"
            f"平均推理 {average:.1f} ms；"
            f"Provider={','.join(providers) or '尚未运行'}。"
        )

    @Slot()
    def _sync_output_root_state(self) -> None:
        beside = str(self.output_mode_combo.currentData()) == OutputMode.BESIDE.value
        self.output_root_edit.setEnabled(not beside)
        self.output_root_button.setEnabled(not beside)

    @Slot(bool)
    def _sync_lora_state(self, enabled: bool) -> None:
        self.profile_combo.setEnabled(not enabled)
        if enabled:
            self.profile_combo.setCurrentIndex(
                self.profile_combo.findData("lora_caption")
            )
            self.rating_check.setChecked(False)

    def sync_controller_state(self) -> None:
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        busy = self.controller.is_busy
        active = self.controller.is_batch_running
        cancellable = self.controller.is_batch_active
        paused = self.controller.is_batch_paused
        self.scan_button.setEnabled(not busy and self.roots.count() > 0)
        self.start_button.setEnabled(
            not busy and self.job is not None and bool(self.job.items)
        )
        self.pause_button.setEnabled(active and not paused)
        self.resume_button.setEnabled(active and paused)
        self.cancel_button.setEnabled(cancellable)
        self.retry_button.setEnabled(
            not busy
            and self.job is not None
            and any(
                item.status.value in {"failed", "missing", "cancelled"}
                for item in self.job.items
            )
        )
        self.open_manifest_button.setEnabled(not busy)
        self.report_button.setEnabled(
            not busy and self.job is not None and bool(self.job.items)
        )
        self.clear_job_button.setEnabled(not busy and self.job is not None)
        self.options_widget.setEnabled(not busy)
        self.remove_items_button.setEnabled(not busy and self.job is not None)

    def _show_recovery_notice(self) -> None:
        directories = [
            BATCH_JOBS_DIR if IS_PORTABLE else PROJECT_ROOT / ".animetagger"
        ]
        for value in (
            self.base_settings.recent_open_dir,
            self.base_settings.default_export_dir,
        ):
            if value:
                directories.append(Path(value) / ".animetagger")
        found = ManifestStore().discover_incomplete(directories)
        if found:
            self.summary_label.setText(
                f"检测到 {len(found)} 个未完成批处理；"
                "不会自动继续，请使用“打开 Manifest”查看或恢复。"
            )


def _comma_values(text: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in text.split(",") if value.strip())


def _preview_counts(job: BatchJob) -> dict[str, int]:
    existing = sum(
        item.caption_path is not None and item.caption_path.exists()
        for item in job.items
    )
    skipped = (
        existing
        if job.config.caption_policy is CaptionPolicy.SKIP
        else 0
    )
    return {"existing": existing, "skipped": skipped}


def settings_value(settings: AppSettings, field: str) -> float:
    return float(getattr(settings, field))
