"""Single-window desktop orchestration for AnimeTagger Lite stage 3."""

from __future__ import annotations

from dataclasses import fields, replace
import logging
from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QByteArray, QSettings, QSignalBlocker, QSize, QTimer, Qt, Slot
from PySide6.QtGui import QAction, QCloseEvent, QImage
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableView,
    QTabWidget,
    QToolBar,
    QToolButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.config.settings import (
    AppSettings,
    USER_SETTINGS_PATH,
    load_settings,
    save_settings,
)
from app.errors import AnimeTaggerError
from app.export_service import ExportFormat
from app.image.image_loader import SUPPORTED_IMAGE_EXTENSIONS
from app.inference.backends import BACKENDS, backend_spec
from app.ui.theme import ThemeColors, apply_theme
from app.ui.palette_dialog import PaletteDialog
from app.ui.collapsible import CollapsibleSection
from app.inference.model_loader import TagCategory
from app.inference.providers import Device
from app.inference.wd14_engine import ModelInfo
from app.prompts.models import PromptGroup
from app.prompts.injection import inject_text, parse_injections, prepare_tags, token_key
from app.services.clipboard_service import ClipboardService
from app.services.tagging_service import (
    AnalysisResult,
    ModelValidationResult,
    TaggingService,
)
from app.state.image_item import ImageItem, ImageStatus
from app.state.project_state import AddPathsResult, ProjectState
from app.ui.image_list_widget import ImageListWidget
from app.ui.batch_panel import BatchPanel
from app.ui.random_prompt_panel import RandomPromptPanel
from app.ui.image_preview_widget import ImagePreviewWidget
from app.ui.model_status_widget import ModelStatusWidget
from app.ui.prompt_panel import PromptPanel
from app.ui.settings_dialog import SettingsDialog
from app.ui.tag_filter_proxy import TagFilterProxyModel
from app.ui.tag_table_model import TagColumn, TagTableModel
from app.ui.tag_visual_widgets import TagVisualDelegate, TagVisualProvider
from app.ui.workers.inference_worker import InferenceController, QueueEntry
from app.ui.workers.thumbnail_worker import ImageDecodeCoordinator
from app.runtime_paths import (
    IS_PORTABLE,
    TEMP_DIR,
    UI_SETTINGS_PATH,
    ensure_portable_data_directories,
)

logger = logging.getLogger(__name__)


def _probability_spin(value: float, tooltip: str) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0.0, 1.0)
    spin.setDecimals(2)
    spin.setSingleStep(0.05)
    spin.setValue(value)
    spin.setToolTip(tooltip)
    return spin


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        settings: AppSettings | None = None,
        settings_path: Path | None = None,
        service: TaggingService | None = None,
        controller: InferenceController | None = None,
        decoder: ImageDecodeCoordinator | None = None,
        clipboard_service: ClipboardService | None = None,
        ui_settings: QSettings | None = None,
    ) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle(f"AnimeTagger Lite {__version__}")
        self.resize(1540, 960)

        self.settings_path = (
            Path(settings_path)
            if settings_path is not None
            else USER_SETTINGS_PATH
        )
        self._startup_warnings: list[str] = []
        self.settings = settings or load_settings(
            user_path=self.settings_path,
            warning_sink=self._startup_warnings.append,
        )
        self.service = service or TaggingService()
        self.project = ProjectState()
        ensure_portable_data_directories()
        self.clipboard_service = clipboard_service or ClipboardService(
            temp_parent=TEMP_DIR if IS_PORTABLE else None
        )
        self.decoder = decoder or ImageDecodeCoordinator(self)
        self.controller = controller or InferenceController(self.service, self)
        if ui_settings is not None:
            self.ui_settings = ui_settings
        elif IS_PORTABLE:
            self.ui_settings = QSettings(
                str(UI_SETTINGS_PATH),
                QSettings.Format.IniFormat,
            )
        else:
            self.ui_settings = QSettings()
        self.theme_colors = ThemeColors.load(self.ui_settings)
        apply_theme(self.theme_colors)
        self.tag_visual_provider = TagVisualProvider(self, surface=self.theme_colors.surface,
            enabled=self.ui_settings.value("tag_visuals/enabled", True, type=bool))
        self._tags_updating = False
        self._injection_undo = None
        self._quick_updating = False
        self._close_pending = False
        self._close_retry_scheduled = False
        self._ui_state_saved_for_close = False
        self._queue_failures: list[tuple[str, str]] = []

        self._build_actions()
        self._build_toolbar()
        self._build_central_ui()
        self._connect_signals()
        self._restore_ui_state()
        self._sync_quick_controls()
        self._validate_configured_model(show_status=False)
        if self._startup_warnings:
            self.statusBar().showMessage(self._startup_warnings[0], 10000)
        self._update_action_states()

    # --- UI construction -------------------------------------------------

    def _build_actions(self) -> None:
        self.add_action = QAction("添加图片", self)
        self.add_action.setObjectName("addImagesAction")
        self.add_action.setToolTip("选择一张或多张图片")
        self.paste_action = QAction("粘贴图片", self)
        self.paste_action.setObjectName("pasteImagesAction")
        self.paste_action.setToolTip("粘贴剪贴板图片或本地图片路径")
        self.remove_action = QAction("删除所选", self)
        self.remove_action.setObjectName("removeImagesAction")
        self.clear_action = QAction("清空列表", self)
        self.clear_action.setObjectName("clearImagesAction")
        self.start_action = QAction("开始识别", self)
        self.start_action.setObjectName("startInferenceAction")
        self.start_action.setToolTip(
            "识别所选图片；可在列表中 Ctrl/Shift 多选，队列默认逐张执行"
        )
        self.cancel_action = QAction("取消", self)
        self.cancel_action.setObjectName("cancelInferenceAction")
        self.cancel_action.setToolTip("完成当前 ONNX 调用后取消剩余队列")
        self.export_action = QAction("导出当前", self)
        self.export_action.setObjectName("exportAction")
        self.copy_combined_action = QAction("复制正负", self)
        self.copy_combined_action.setObjectName("copyCombinedAction")
        self.settings_action = QAction("设置", self)
        self.settings_action.setObjectName("settingsAction")
        self.about_action = QAction("关于 AnimeTagger Lite", self)
        self.about_action.setObjectName("aboutAction")
        self.palette_action = QAction("调色盘", self)
        self.palette_action.triggered.connect(self._open_palette)
        self.add_action.setShortcut("Ctrl+O")
        self.paste_action.setShortcut("Ctrl+V")
        for action in (self.add_action, self.paste_action, self.remove_action,
                       self.clear_action, self.start_action, self.cancel_action,
                       self.export_action, self.copy_combined_action):
            self.addAction(action)

    def _open_palette(self) -> None:
        dialog = PaletteDialog(self.theme_colors, self)
        if dialog.exec() == PaletteDialog.DialogCode.Accepted:
            self.theme_colors = dialog.colors
            self.theme_colors.save(self.ui_settings)
        self.tag_visual_provider.set_surface(self.theme_colors.surface)

    @staticmethod
    def _action_button(action, *, primary=False):
        button = QToolButton()
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setProperty("primary", primary)
        if primary:
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return button

    @staticmethod
    def _heading(text):
        label = QLabel(text)
        label.setProperty("heading", True)
        return label

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("主工具栏")
        toolbar.setObjectName("mainToolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        brand = QLabel("◈  AnimeTagger Lite")
        brand.setObjectName("brand")
        toolbar.addWidget(brand)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)
        self.backend_combo = QComboBox()
        self.backend_combo.setObjectName("quickBackendCombo")
        for key, spec in BACKENDS.items():
            self.backend_combo.addItem(spec.label, key)
        self.backend_combo.setCurrentIndex(self.backend_combo.findData(self.settings.backend))
        self.backend_combo.currentIndexChanged.connect(self._select_backend)
        toolbar.addWidget(self.backend_combo)
        self.quick_load = QPushButton("加载模型")
        self.quick_load.clicked.connect(self._load_model)
        toolbar.addWidget(self.quick_load)
        self.model_badge = QLabel("未加载")
        self.model_badge.setProperty("muted", True)
        toolbar.addWidget(self.model_badge)
        toolbar.addAction(self.palette_action)
        toolbar.addAction(self.settings_action)
        self.addToolBar(toolbar)
        help_menu = QMenu(self)
        help_menu.addAction(self.about_action)
        help_button = QToolButton()
        help_button.setText("帮助")
        help_button.setMenu(help_menu)
        help_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        toolbar.addWidget(help_button)

        self.progress = QProgressBar()
        self.progress.setObjectName("queueProgress")
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setMaximumWidth(220)
        self.statusBar().addPermanentWidget(self.progress)

    def _build_central_ui(self) -> None:
        self.image_list = ImageListWidget()
        left = QWidget()
        left.setProperty("card", True)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.addWidget(self._heading("图片库"))
        library_actions = QHBoxLayout()
        library_actions.addWidget(self._action_button(self.add_action, primary=True))
        library_actions.addWidget(self._action_button(self.paste_action))
        more = QToolButton()
        more.setText("···")
        menu = QMenu(more)
        menu.addAction(self.remove_action)
        menu.addAction(self.clear_action)
        more.setMenu(menu)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        library_actions.addWidget(more)
        left_layout.addLayout(library_actions)
        left_layout.addWidget(self.image_list, 1)
        hint = QLabel("拖放图片到列表\nCtrl / Shift 多选 · Ctrl+V 粘贴")
        hint.setProperty("muted", True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(hint)
        left.setMinimumWidth(245)

        self.preview = ImagePreviewWidget()

        self.model_status = ModelStatusWidget()
        self.tag_model = TagTableModel(visual_provider=self.tag_visual_provider)
        self.tag_proxy = TagFilterProxyModel(self)
        self.tag_proxy.setSourceModel(self.tag_model)
        self.tag_proxy.set_minimum_confidence(
            self.settings.minimum_display_threshold
        )
        self.tag_proxy.set_show_low_confidence(
            self.settings.show_low_confidence
        )

        self.tag_search = QLineEdit()
        self.tag_search.setObjectName("tagSearch")
        self.tag_search.setPlaceholderText("搜索标签")
        self.category_filter = QComboBox()
        self.category_filter.setObjectName("categoryFilter")
        self.category_filter.addItem("全部类别", "")
        for category in TagCategory:
            self.category_filter.addItem(category.value, category.value)
        self.group_filter = QComboBox()
        self.group_filter.setObjectName("groupFilter")
        self.group_filter.addItem("全部分组", "")
        for group in PromptGroup:
            self.group_filter.addItem(group.value, group.value)
        self.show_low_check = QCheckBox("显示低置信度")
        self.show_low_check.setChecked(self.settings.show_low_confidence)

        self.tag_table = QTableView()
        self.tag_table.setObjectName("tagTable")
        self.tag_table.setModel(self.tag_proxy)
        self.tag_table.setSortingEnabled(True)
        self.tag_table.sortByColumn(
            TagColumn.CONFIDENCE,
            Qt.SortOrder.DescendingOrder,
        )
        self.tag_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.tag_table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.tag_table.setAlternatingRowColors(True)
        self.tag_table.setWordWrap(False)
        self.tag_table.setShowGrid(False)
        self.tag_table.setIconSize(QSize(24, 24))
        self.tag_visual_delegate = TagVisualDelegate(self.tag_table, self.tag_visual_provider)
        self.tag_table.setItemDelegateForColumn(TagColumn.TAG, self.tag_visual_delegate)
        self.tag_table.verticalHeader().hide()
        self.tag_table.verticalHeader().setDefaultSectionSize(34)
        self.tag_table.horizontalHeader().setSectionResizeMode(TagColumn.TAG, QHeaderView.ResizeMode.Stretch)
        self.tag_table.setColumnWidth(TagColumn.ENABLED, 46)
        self.tag_table.setColumnWidth(TagColumn.CONFIDENCE, 90)
        self.tag_table.setColumnHidden(TagColumn.GROUP, True)
        self.tag_table.setColumnHidden(TagColumn.SOURCE, True)

        self.add_tag_button = QPushButton("添加标签")
        self.add_tag_button.setObjectName("addTagButton")
        self.delete_tag_button = QPushButton("删除标签")
        self.delete_tag_button.setObjectName("deleteTagButton")
        self.restore_tags_button = QPushButton("恢复原始标签")
        self.restore_tags_button.setObjectName("restoreTagsButton")
        tag_buttons = QHBoxLayout()
        tag_buttons.addWidget(self.add_tag_button)
        tag_buttons.addWidget(self.delete_tag_button)
        tag_buttons.addWidget(self.restore_tags_button)
        tag_buttons.addStretch(1)

        tag_area = QWidget()
        tag_area.setProperty("card", True)
        tag_layout = QVBoxLayout(tag_area)
        tag_layout.setContentsMargins(12, 12, 12, 12)
        tag_layout.addWidget(self._heading("识别标签"))
        search_row = QHBoxLayout()
        search_row.addWidget(self.tag_search, 2)
        search_row.addWidget(self.category_filter, 1)
        tag_layout.addLayout(search_row)
        filter_content = QWidget()
        filter_layout = QHBoxLayout(filter_content)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.addWidget(self.group_filter)
        filter_layout.addWidget(self.show_low_check)
        self.tag_visuals_check = QCheckBox("图示辅助")
        self.tag_visuals_check.setObjectName("tagVisualsCheck")
        self.tag_visuals_check.setChecked(self.tag_visual_provider.enabled)
        self.tag_visuals_check.setToolTip("标签旁显示图示；悬停查看放大示意和中文释义。也应用于随机 Prompt 标签。")
        filter_layout.addWidget(self.tag_visuals_check)
        detail_check = QCheckBox("详细列")
        detail_check.toggled.connect(lambda checked: [self.tag_table.setColumnHidden(c, not checked) for c in (TagColumn.GROUP, TagColumn.SOURCE)])
        filter_layout.addWidget(detail_check)
        tag_layout.addWidget(CollapsibleSection("筛选与显示", filter_content))
        tag_layout.addWidget(self.tag_table, 1)
        tag_layout.addLayout(tag_buttons)

        self.prompt_panel = PromptPanel()
        quick = self._build_quick_settings()
        prompt_area = QWidget()
        prompt_layout = QVBoxLayout(prompt_area)
        prompt_layout.setContentsMargins(0, 0, 0, 0)
        prompt_layout.addWidget(self.prompt_panel, 1)
        prompt_layout.addWidget(quick)

        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.setObjectName("rightSplitter")
        self.right_splitter.addWidget(tag_area)
        prompt_scroll = QScrollArea()
        prompt_scroll.setWidgetResizable(True)
        prompt_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        prompt_scroll.setWidget(prompt_area)
        self.right_splitter.addWidget(prompt_scroll)
        self.right_splitter.setSizes([420, 420])
        self.right_splitter.setChildrenCollapsible(False)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        actions = QHBoxLayout()
        actions.addWidget(self._action_button(self.start_action, primary=True), 1)
        actions.addWidget(self._action_button(self.cancel_action))
        actions.addWidget(self._action_button(self.export_action))
        actions.addWidget(self._action_button(self.copy_combined_action))
        right_layout.addLayout(actions)
        self.model_section = CollapsibleSection("模型管理 · 加载 / 验证 / 释放", self.model_status)
        right_layout.addWidget(self.model_section)
        right_layout.addWidget(self.right_splitter, 1)
        right.setMinimumWidth(520)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setObjectName("mainSplitter")
        self.main_splitter.addWidget(left)
        self.main_splitter.addWidget(self.preview)
        self.main_splitter.addWidget(right)
        self.main_splitter.setSizes([270, 600, 610])
        self.main_splitter.setChildrenCollapsible(False)
        self.batch_panel = BatchPanel(
            self.controller,
            self.settings,
            self,
        )
        self.random_prompt_panel = RandomPromptPanel(self.settings, self, visual_provider=self.tag_visual_provider)
        self.pages = QTabWidget()
        self.pages.setObjectName("mainPages")
        self.pages.addTab(self.main_splitter, "单图")
        self.pages.addTab(self.batch_panel, "批处理")
        self.pages.addTab(self.random_prompt_panel, "随机 Prompt")
        workspace = QWidget()
        workspace.setObjectName("workspace")
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(12, 0, 12, 8)
        workspace_layout.addWidget(self.pages)
        self.setCentralWidget(workspace)

    def _build_quick_settings(self) -> QWidget:
        widget = QWidget()
        self.profile_combo = QComboBox()
        for value in ("raw", "anime", "pony", "krea2", "lora_caption"):
            self.profile_combo.addItem(value, value)
        self.profile_combo.addItem(
            "CyberIllustrious 半写实", "cyberillustrious_semireal"
        )
        self.profile_combo.setToolTip(
            "针对 CyberIllustrious Semi-Realistic 优化：保留 Danbooru 标签，"
            "按主体与视觉信息重排，并按识别结果适量加入材质、光照和镜头描述。"
        )
        self.general_spin = _probability_spin(
            self.settings.general_threshold,
            "立即使用当前 working_tags 重建提示词，不重新运行模型",
        )
        self.character_spin = _probability_spin(
            self.settings.character_threshold,
            "立即使用当前 working_tags 重建提示词，不重新运行模型",
        )
        self.negative_combo = QComboBox()
        for label, value in (
            ("none", "none"),
            ("basic", "basic"),
            ("cleanup_detected", "cleanup_detected"),
        ):
            self.negative_combo.addItem(label, value)
        self.trigger_edit = QLineEdit()
        self.trigger_edit.setPlaceholderText("LoRA trigger word（可选）")

        widget.setProperty("card", True)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.addWidget(self._heading("生成设置"))
        form = QFormLayout()
        form.addRow("Profile", self.profile_combo)
        layout.addLayout(form)
        thresholds = QHBoxLayout()
        thresholds.addWidget(QLabel("通用阈值"))
        thresholds.addWidget(self.general_spin, 1)
        thresholds.addWidget(QLabel("角色阈值"))
        thresholds.addWidget(self.character_spin, 1)
        layout.addLayout(thresholds)
        advanced = QWidget()
        advanced_form = QFormLayout(advanced)
        advanced_form.addRow("反向模式", self.negative_combo)
        advanced_form.addRow("Trigger word", self.trigger_edit)
        self.quick_advanced = CollapsibleSection("高级设置", advanced)
        layout.addWidget(self.quick_advanced)
        return widget

    def _select_backend(self) -> None:
        backend = self.backend_combo.currentData()
        if backend == self.settings.backend or self.controller.is_busy:
            return
        self.settings = self.settings.select_backend(backend)
        self.batch_panel.set_base_settings(self.settings)
        self.random_prompt_panel.set_settings(self.settings)
        self._sync_quick_controls()
        self._save_settings_safely(nonblocking=True)
        self._validate_configured_model(show_status=True)
        self.model_section.toggle.setChecked(True)
        self._load_model()

    def _connect_signals(self) -> None:
        self.add_action.triggered.connect(self._choose_images)
        self.paste_action.triggered.connect(self._paste_images)
        self.remove_action.triggered.connect(self._remove_selected_images)
        self.clear_action.triggered.connect(self._clear_images)
        self.start_action.triggered.connect(self._start_selected_queue)
        self.cancel_action.triggered.connect(self._cancel_queue)
        self.export_action.triggered.connect(self._choose_export)
        self.copy_combined_action.triggered.connect(
            lambda: self._copy_prompt("combined")
        )
        self.settings_action.triggered.connect(self._open_settings)
        self.about_action.triggered.connect(self._show_about)

        self.image_list.paths_dropped.connect(self.add_paths)
        self.image_list.currentItemChanged.connect(
            self._on_current_list_item_changed
        )
        self.decoder.thumbnail_ready.connect(self._on_thumbnail_ready)
        self.decoder.thumbnail_failed.connect(self._on_thumbnail_failed)
        self.decoder.preview_ready.connect(self._on_preview_ready)
        self.decoder.preview_failed.connect(self._on_preview_failed)

        self.tag_search.textChanged.connect(self.tag_proxy.set_search_text)
        self.category_filter.currentIndexChanged.connect(
            lambda _index: self.tag_proxy.set_category_filter(
                str(self.category_filter.currentData())
            )
        )
        self.group_filter.currentIndexChanged.connect(
            lambda _index: self.tag_proxy.set_group_filter(
                str(self.group_filter.currentData())
            )
        )
        self.show_low_check.toggled.connect(self._set_show_low_confidence)
        self.tag_visuals_check.toggled.connect(self._set_tag_visuals_enabled)
        self.tag_model.tags_changed.connect(self._on_tags_changed)
        self.add_tag_button.clicked.connect(self._add_manual_tag)
        self.delete_tag_button.clicked.connect(self._delete_selected_tags)
        self.restore_tags_button.clicked.connect(self._restore_raw_tags)

        self.prompt_panel.prompt_edited.connect(self._on_prompt_edited)
        self.prompt_panel.injection_requested.connect(self._inject_positive_tags)
        self.prompt_panel.undo_injection_requested.connect(self._undo_positive_injection)
        self.prompt_panel.regenerate_requested.connect(
            self._regenerate_prompt
        )
        self.prompt_panel.copy_requested.connect(self._copy_prompt)

        self.profile_combo.currentIndexChanged.connect(
            lambda _index: self._apply_quick_settings()
        )
        self.negative_combo.currentIndexChanged.connect(
            lambda _index: self._apply_quick_settings()
        )
        self.general_spin.editingFinished.connect(self._apply_quick_settings)
        self.character_spin.editingFinished.connect(self._apply_quick_settings)
        self.trigger_edit.editingFinished.connect(self._apply_quick_settings)

        self.model_status.validate_requested.connect(
            lambda: self._validate_configured_model(show_status=True)
        )
        self.model_status.load_requested.connect(self._load_model)
        self.model_status.unload_requested.connect(self._unload_model)

        self.controller.model_loading.connect(self._on_model_loading)
        self.controller.model_loaded.connect(self._on_model_loaded)
        self.controller.model_load_failed.connect(self._on_model_load_failed)
        self.controller.model_unloaded.connect(self._on_model_unloaded)
        self.controller.image_started.connect(self._on_image_started)
        self.controller.image_completed.connect(self._on_image_completed)
        self.controller.image_failed.connect(self._on_image_failed)
        self.controller.image_cancelled.connect(self._on_image_cancelled)
        self.controller.progress_changed.connect(self._on_progress)
        self.controller.queue_completed.connect(self._on_queue_completed)
        self.controller.fatal_error.connect(self._on_fatal_error)
        self.controller.stopped.connect(self._on_controller_stopped)
        self.controller.busy_changed.connect(
            lambda _busy: self._update_action_states()
        )
        self.batch_panel.activity_changed.connect(self._update_action_states)
        self.pages.currentChanged.connect(
            lambda _index: self._update_action_states()
        )

    # --- image import and selection --------------------------------------

    @Slot()
    def _choose_images(self) -> None:
        patterns = " ".join(
            f"*{suffix}" for suffix in sorted(SUPPORTED_IMAGE_EXTENSIONS)
        )
        initial = self.settings.recent_open_dir or str(Path.home())
        paths, _selected_filter = QFileDialog.getOpenFileNames(
            self,
            "添加图片",
            initial,
            f"支持的图片 ({patterns});;所有文件 (*)",
        )
        if paths:
            self.add_paths([Path(path) for path in paths])

    @Slot()
    def _paste_images(self) -> None:
        try:
            imported = self.clipboard_service.import_from_clipboard(
                QApplication.clipboard()
            )
        except Exception as exc:
            logger.exception("剪贴板图片导入失败")
            QMessageBox.warning(self, "无法粘贴", str(exc))
            return
        if not imported.paths:
            self.statusBar().showMessage(
                "剪贴板中没有可用的图片或本地图片路径。",
                4000,
            )
            return
        self.add_paths(
            imported.paths,
            temporary_paths=imported.temporary_paths,
        )

    @Slot(object)
    def add_paths(
        self,
        paths_object: object,
        *,
        temporary_paths: Iterable[Path] = (),
    ) -> AddPathsResult:
        paths = tuple(Path(path) for path in paths_object)  # type: ignore[arg-type]
        result = self.project.add_paths(
            paths,
            temporary_paths=temporary_paths,
        )
        for item in result.added:
            self.image_list.add_image_item(item)
            self.decoder.request_thumbnail(item.id, item.source_path)
        if result.added:
            first_non_temporary = next(
                (item for item in result.added if not item.is_temporary),
                None,
            )
            if first_non_temporary is not None:
                self.settings = replace(
                    self.settings,
                    recent_open_dir=str(first_non_temporary.source_path.parent),
                )
                self._save_settings_safely(nonblocking=True)
            if self.image_list.currentItem() is None:
                self.image_list.select_image_id(result.added[0].id)

        notices: list[str] = []
        if result.added:
            notices.append(f"已添加 {len(result.added)} 张图片")
        if result.duplicates:
            notices.append(f"忽略 {len(result.duplicates)} 个重复路径")
        if result.unsupported:
            notices.append(f"忽略 {len(result.unsupported)} 个不支持文件")
        if result.missing:
            notices.append(f"忽略 {len(result.missing)} 个不存在文件")
        if result.directories:
            notices.append(
                f"忽略 {len(result.directories)} 个文件夹；文件夹批处理将在后续阶段实现"
            )
        self.statusBar().showMessage("；".join(notices) or "没有可添加的图片", 6000)
        self._update_action_states()
        return result

    @Slot()
    def _remove_selected_images(self) -> None:
        ids = self.image_list.selected_image_ids()
        if not ids:
            return
        self.project.remove(ids)
        self.image_list.remove_image_ids(ids)
        if self.project.current_id:
            self.image_list.select_image_id(self.project.current_id)
        else:
            self._show_current(None)
        self._update_action_states()

    @Slot()
    def _clear_images(self) -> None:
        if not len(self.project):
            return
        self.project.clear()
        self.image_list.clear()
        self._show_current(None)
        self._update_action_states()

    @Slot(object, object)
    def _on_current_list_item_changed(
        self,
        current: object,
        _previous: object,
    ) -> None:
        image_id = self.image_list.current_image_id()
        self.project.current_id = image_id
        self._show_current(self.project.get(image_id))

    def _show_current(self, item: ImageItem | None) -> None:
        self._tags_updating = True
        try:
            self.tag_model.set_tags(item.working_tags if item else ())
        finally:
            self._tags_updating = False
        if item is None:
            self.decoder.invalidate_preview()
            self.preview.clear()
            self.prompt_panel.clear()
        else:
            self.preview.set_loading()
            self.decoder.request_preview(item.id, item.source_path)
            self._refresh_prompt_panel(item)
        self._update_action_states()

    @Slot(str, object)
    def _on_thumbnail_ready(self, image_id: str, image_object: object) -> None:
        if isinstance(image_object, QImage):
            self.image_list.set_thumbnail(image_id, image_object)

    @Slot(str, str)
    def _on_thumbnail_failed(self, image_id: str, _message: str) -> None:
        self.image_list.set_thumbnail_placeholder(image_id)

    @Slot(str, int, object)
    def _on_preview_ready(
        self,
        image_id: str,
        _token: int,
        image_object: object,
    ) -> None:
        if image_id != self.project.current_id:
            return
        if isinstance(image_object, QImage):
            self.preview.set_image(image_object)

    @Slot(str, int, str)
    def _on_preview_failed(
        self,
        image_id: str,
        _token: int,
        message: str,
    ) -> None:
        if image_id == self.project.current_id:
            self.preview.set_error(message)

    # --- model lifecycle and inference ----------------------------------

    def _validate_configured_model(
        self,
        *,
        show_status: bool,
    ) -> ModelValidationResult:
        result = self.service.validate_model_directory(
            self.settings.model_dir,
            Device(self.settings.device),
            backend=self.settings.backend,
        )
        if not self.controller.is_model_loaded:
            self.model_status.set_validation(result)
        if show_status:
            self.statusBar().showMessage(result.message, 7000)
        self._update_action_states()
        return result

    @Slot()
    def _load_model(self) -> None:
        validation = self._validate_configured_model(show_status=False)
        if not validation.valid:
            QMessageBox.warning(
                self,
                "无法加载模型",
                f"{validation.message}\n\n请在“设置”中选择包含 "
                "所选后端权重和标签文件的目录。",
            )
            return
        if not self.controller.load_model(
            self.settings.model_dir,
            Device(self.settings.device),
            backend=self.settings.backend,
        ):
            self.statusBar().showMessage("当前任务尚未结束，暂不能加载模型。", 4000)
        self._update_action_states()

    @Slot()
    def _unload_model(self) -> None:
        if not self.controller.unload_model():
            self.statusBar().showMessage("当前任务尚未结束，暂不能释放模型。", 4000)
        self._update_action_states()

    @Slot()
    def _on_model_loading(self) -> None:
        self.model_status.set_loading()
        self.model_badge.setText("加载中…")
        self.statusBar().showMessage("正在后台加载并验证模型…")
        self._update_action_states()

    @Slot(object)
    def _on_model_loaded(self, info_object: object) -> None:
        if isinstance(info_object, ModelInfo):
            self.model_status.set_loaded(info_object)
            self.model_badge.setText("● 已就绪")
            self.model_badge.setToolTip(info_object.active_provider)
            self.model_section.toggle.setChecked(False)
            message = f"模型已加载，当前使用 {info_object.active_provider}"
            if info_object.provider_warning:
                message = f"{info_object.provider_warning} {message}"
            self.statusBar().showMessage(message, 8000)
        self._update_action_states()

    @Slot(str, bool)
    def _on_model_load_failed(self, message: str, still_loaded: bool) -> None:
        self.model_status.set_failed(message, still_loaded=still_loaded)
        self.model_badge.setText("原模型就绪" if still_loaded else "加载失败")
        self.model_section.toggle.setChecked(True)
        QMessageBox.warning(
            self,
            "模型加载失败",
            f"{message}\n\n"
            + (
                "原有模型 Session 仍可继续使用。"
                if still_loaded
                else "请检查模型文件是否同版本且可读取。"
            ),
        )
        self._update_action_states()

    @Slot()
    def _on_model_unloaded(self) -> None:
        self.model_status.set_released()
        self.model_badge.setText("已释放")
        self.statusBar().showMessage("模型 Session 已释放。", 4000)
        self._update_action_states()

    @Slot()
    def _start_selected_queue(self) -> None:
        if not self.controller.is_model_loaded:
            QMessageBox.information(
                self,
                "模型尚未加载",
                "请先验证并加载模型。界面可以在无模型时继续添加和预览图片。",
            )
            return
        loaded_backend = self.service.loaded_backend
        if loaded_backend is not None and loaded_backend != self.settings.backend:
            try:
                loaded_label = backend_spec(loaded_backend).label
                selected_label = backend_spec(self.settings.backend).label
            except Exception:
                loaded_label = loaded_backend
                selected_label = self.settings.backend
            QMessageBox.warning(
                self,
                "后端与模型不一致",
                f"当前已加载后端为「{loaded_label}」，设置中选择了「{selected_label}」。\n"
                "请点击“加载模型”完成切换后再识别。",
            )
            return
        selected = self.image_list.selected_image_ids()
        ids = selected or tuple(item.id for item in self.project.items)
        items = [
            item
            for image_id in ids
            if (item := self.project.get(image_id)) is not None
        ]
        if not items:
            return
        dirty = [item for item in items if item.is_dirty]
        if dirty:
            answer = QMessageBox.question(
                self,
                "重新识别会覆盖编辑",
                f"{len(dirty)} 张图片包含手动标签或提示词编辑。"
                "重新识别会以新结果覆盖这些 working_tags 和最终提示词，是否继续？",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer is not QMessageBox.StandardButton.Yes:
                return

        entries = tuple(
            QueueEntry(item.id, item.source_path, self.settings)
            for item in items
        )
        if not self.controller.start_queue(entries):
            self.statusBar().showMessage("已有任务正在运行，请勿重复开始。", 5000)
            return
        self._queue_failures.clear()
        for item in items:
            item.prepare_for_reanalysis()
            self.image_list.update_image_item(item)
        self.progress.setRange(0, len(entries))
        self.progress.setValue(0)
        self.statusBar().showMessage(f"识别队列已开始，共 {len(entries)} 张。")
        self._update_action_states()

    @Slot()
    def _cancel_queue(self) -> None:
        if self.controller.cancel():
            self.statusBar().showMessage("正在完成当前图片后取消剩余队列…")
        self._update_action_states()

    @Slot(str)
    def _on_image_started(self, image_id: str) -> None:
        item = self.project.get(image_id)
        if item is not None:
            item.set_status(ImageStatus.ANALYZING)
            self.image_list.update_image_item(item)

    @Slot(str, object)
    def _on_image_completed(
        self,
        image_id: str,
        result_object: object,
    ) -> None:
        item = self.project.get(image_id)
        if item is None or not isinstance(result_object, AnalysisResult):
            return
        item.apply_analysis(
            result_object.inference,
            result_object.raw_tags,
            result_object.prompts,
        )
        self.image_list.update_image_item(item)
        if image_id == self.project.current_id:
            self._show_current(item)

    @Slot(str, str)
    def _on_image_failed(self, image_id: str, message: str) -> None:
        item = self.project.get(image_id)
        if item is not None:
            item.set_status(ImageStatus.FAILED, error_message=message)
            self.image_list.update_image_item(item)
            self._queue_failures.append((item.display_name, message))

    @Slot(str)
    def _on_image_cancelled(self, image_id: str) -> None:
        item = self.project.get(image_id)
        if item is not None:
            item.set_status(ImageStatus.CANCELLED)
            self.image_list.update_image_item(item)

    @Slot(int, int)
    def _on_progress(self, value: int, total: int) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(value)

    @Slot(int, int, int, int)
    def _on_queue_completed(
        self,
        completed: int,
        failed: int,
        cancelled: int,
        total: int,
    ) -> None:
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(total)
        summary = (
            f"队列结束：成功 {completed}，失败 {failed}，"
            f"取消 {cancelled}，共 {total}。"
        )
        self.statusBar().showMessage(summary, 10000)
        if failed:
            details = "\n".join(
                f"• {name}：{message}"
                for name, message in self._queue_failures[:8]
            )
            if len(self._queue_failures) > 8:
                details += f"\n…另有 {len(self._queue_failures) - 8} 项"
            QMessageBox.warning(self, "部分图片识别失败", f"{summary}\n\n{details}")
        self._update_action_states()

    @Slot(str)
    def _on_fatal_error(self, message: str) -> None:
        logger.error("GUI 后台任务错误：%s", message)
        QMessageBox.critical(self, "后台任务错误", message)
        self._update_action_states()

    # --- tags and prompts ------------------------------------------------

    @Slot()
    def _on_tags_changed(self) -> None:
        if self._tags_updating:
            return
        item = self.project.get(self.project.current_id)
        if item is None:
            return
        try:
            item.replace_working_tags(self.tag_model.tags, dirty=True)
            prompts = self.service.rebuild_prompts(
                item.working_tags,
                self.settings,
            )
            item.apply_prompt_result(prompts, preserve_manual_prompts=True)
        except AnimeTaggerError as exc:
            QMessageBox.warning(self, "标签处理失败", str(exc))
            return
        self._tags_updating = True
        try:
            self.tag_model.set_tags(item.working_tags)
        finally:
            self._tags_updating = False
        self._refresh_prompt_panel(item)
        self._update_action_states()

    @Slot()
    def _add_manual_tag(self) -> None:
        if self.project.current_id is None:
            return
        name, accepted = QInputDialog.getText(self, "添加标签", "标签名称")
        if accepted and not self.tag_model.add_manual_tag(name):
            self.statusBar().showMessage("空标签不会被添加。", 3000)

    @Slot()
    def _delete_selected_tags(self) -> None:
        proxy_rows = {
            index.row() for index in self.tag_table.selectionModel().selectedRows()
        }
        source_rows = [
            self.tag_proxy.mapToSource(self.tag_proxy.index(row, 0)).row()
            for row in proxy_rows
        ]
        self.tag_model.remove_source_rows(source_rows)

    @Slot(str, bool)
    def _inject_positive_tags(self, text: str, clean_appearance: bool) -> None:
        item = self.project.get(self.project.current_id)
        if item is None or item.prompt_result is None or self.controller.is_busy:
            return
        try:
            names = parse_injections(text)
            if not names:
                self.statusBar().showMessage("请输入要注入的标签。", 3000)
                return
            tags, removed = prepare_tags(item.working_tags, names, clean_appearance=clean_appearance)
            # Build first so a validation failure leaves image state untouched.
            prompts = self.service.rebuild_prompts(tags, self.settings)
        except (ValueError, AnimeTaggerError) as exc:
            QMessageBox.warning(self, "无法注入标签", str(exc))
            return
        before = replace(item, working_tags=list(item.working_tags))
        recognized = {token_key(tag.output_name) for tag in before.prompt_result.positive_tags if tag.source.value == "model"}
        item.positive_injections = tuple({token_key(name): name for name in (*item.positive_injections, *names)}.values())
        item.apply_prompt_result(prompts, preserve_manual_prompts=True)
        if before.positive_prompt_edited:
            item.edit_prompt("positive", inject_text(before.final_positive_prompt, names, removed & recognized))
        item.edit_prompt("negative", before.final_negative_prompt)
        item.is_dirty = True
        self._injection_undo = (item.id, before, item.edit_revision)
        self._tags_updating = True
        try:
            self.tag_model.set_tags(item.working_tags)
        finally:
            self._tags_updating = False
        self._refresh_prompt_panel(item)
        self._update_action_states()
        self.prompt_panel.injection_edit.clear()
        self.statusBar().showMessage(f"已注入 {len(names)} 个标签，从正向移除 {len(removed & recognized)} 个外观标签。", 6000)

    @Slot()
    def _undo_positive_injection(self) -> None:
        item = self.project.get(self.project.current_id)
        record = self._injection_undo
        if item is None or record is None or self.controller.is_busy:
            return
        image_id, before, revision = record
        if item.id != image_id or item.edit_revision != revision:
            return
        for field in fields(ImageItem):
            setattr(item, field.name, getattr(before, field.name))
        item.edit_revision = revision
        item.working_tags = list(before.working_tags)
        item.touch()
        self._injection_undo = None
        self._show_current(item)
        self._update_action_states()
        self.statusBar().showMessage("已恢复注入前的标签和提示词。", 4000)

    @Slot()
    def _restore_raw_tags(self) -> None:
        item = self.project.get(self.project.current_id)
        if item is None or not item.raw_tags:
            return
        if item.is_dirty:
            answer = QMessageBox.question(
                self,
                "恢复原始标签",
                "这会丢弃当前标签编辑，但不会重新运行模型。是否继续？",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer is not QMessageBox.StandardButton.Yes:
                return
        item.restore_working_tags()
        prompts = self.service.rebuild_prompts(item.working_tags, self.settings)
        item.apply_prompt_result(prompts, preserve_manual_prompts=True)
        self._show_current(item)

    @Slot(str, str)
    def _on_prompt_edited(self, kind: str, text: str) -> None:
        item = self.project.get(self.project.current_id)
        if item is None:
            return
        item.edit_prompt(kind, text)
        edited = (
            item.positive_prompt_edited
            if kind == "positive"
            else item.negative_prompt_edited
        )
        self.prompt_panel.set_edit_notice(
            kind,
            edited=edited,
            stale=item.prompt_stale,
        )
        self._update_action_states()

    @Slot(str)
    def _regenerate_prompt(self, kind: str) -> None:
        item = self.project.get(self.project.current_id)
        if item is None:
            return
        edited = (
            item.positive_prompt_edited
            if kind == "positive"
            else item.negative_prompt_edited
        )
        if edited:
            answer = QMessageBox.question(
                self,
                "覆盖手动提示词",
                "重新生成会覆盖当前手动文本，是否继续？",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer is not QMessageBox.StandardButton.Yes:
                return
        item.restore_generated_prompt(kind)
        self._refresh_prompt_panel(item)

    def _refresh_prompt_panel(self, item: ImageItem) -> None:
        self.prompt_panel.set_prompts(
            positive=item.final_positive_prompt,
            negative=item.final_negative_prompt,
            positive_edited=item.positive_prompt_edited,
            negative_edited=item.negative_prompt_edited,
            stale=item.prompt_stale,
            tag_count=(
                len(item.prompt_result.positive_tags)
                if item.prompt_result is not None
                else 0
            ),
        )
        self._update_action_states()

    @Slot(str)
    def _copy_prompt(self, kind: str) -> None:
        item = self.project.get(self.project.current_id)
        if item is None:
            return
        if kind == "positive":
            text = item.final_positive_prompt
        elif kind == "negative":
            text = item.final_negative_prompt
        elif kind == "combined":
            text = f"Positive:\n{item.final_positive_prompt}"
            if item.final_negative_prompt:
                text += f"\n\nNegative:\n{item.final_negative_prompt}"
        else:
            return
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage("提示词已复制。", 2500)

    # --- settings and exports -------------------------------------------

    @Slot()
    def _apply_quick_settings(self) -> None:
        if self._quick_updating:
            return
        profile = str(self.profile_combo.currentData())
        negative_mode = str(self.negative_combo.currentData())
        if profile == "lora_caption":
            negative_mode = "none"
        self.settings = replace(
            self.settings,
            profile=profile,
            general_threshold=self.general_spin.value(),
            character_threshold=self.character_spin.value(),
            negative_mode=negative_mode,
            trigger_word=self.trigger_edit.text().strip() or None,
        )
        self._sync_quick_controls()
        self._save_settings_safely(nonblocking=True)
        item = self.project.get(self.project.current_id)
        if item is not None and item.working_tags:
            try:
                prompts = self.service.rebuild_prompts(
                    item.working_tags,
                    self.settings,
                )
            except AnimeTaggerError as exc:
                QMessageBox.warning(self, "提示词设置无效", str(exc))
                return
            item.apply_prompt_result(prompts, preserve_manual_prompts=True)
            self._tags_updating = True
            try:
                self.tag_model.set_tags(item.working_tags)
            finally:
                self._tags_updating = False
            self._refresh_prompt_panel(item)

    def _sync_quick_controls(self) -> None:
        self._quick_updating = True
        blockers = [
            QSignalBlocker(self.profile_combo),
            QSignalBlocker(self.general_spin),
            QSignalBlocker(self.character_spin),
            QSignalBlocker(self.negative_combo),
            QSignalBlocker(self.trigger_edit),
            QSignalBlocker(self.backend_combo),
        ]
        try:
            self.backend_combo.setCurrentIndex(self.backend_combo.findData(self.settings.backend))
            self.profile_combo.setCurrentIndex(
                self.profile_combo.findData(self.settings.profile)
            )
            self.general_spin.setValue(self.settings.general_threshold)
            self.character_spin.setValue(self.settings.character_threshold)
            effective_negative = (
                "none"
                if self.settings.profile == "lora_caption"
                else self.settings.negative_mode
            )
            self.negative_combo.setCurrentIndex(
                self.negative_combo.findData(effective_negative)
            )
            self.negative_combo.setEnabled(
                self.settings.profile != "lora_caption"
            )
            self.trigger_edit.setText(self.settings.trigger_word or "")
            self.trigger_edit.setVisible(
                self.settings.profile == "lora_caption"
            )
            if self.settings.profile == "lora_caption":
                self.quick_advanced.toggle.setChecked(True)
        finally:
            del blockers
            self._quick_updating = False

    @Slot(bool)
    def _set_show_low_confidence(self, show: bool) -> None:
        self.tag_proxy.set_show_low_confidence(show)
        self.settings = replace(self.settings, show_low_confidence=show)
        self._save_settings_safely(nonblocking=True)

    @Slot()
    def _open_settings(self) -> None:
        dialog = SettingsDialog(
            self.settings,
            self.service.validate_model_directory,
            self,
        )
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return
        old_model = (self.settings.model_dir, self.settings.device, self.settings.backend)
        self.settings = dialog.settings
        self.batch_panel.set_base_settings(self.settings)
        self.random_prompt_panel.set_settings(self.settings)
        self._save_settings_safely(nonblocking=False)
        self.tag_proxy.set_minimum_confidence(
            self.settings.minimum_display_threshold
        )
        self.show_low_check.setChecked(self.settings.show_low_confidence)
        self._sync_quick_controls()
        new_model = (self.settings.model_dir, self.settings.device, self.settings.backend)
        if old_model != new_model and self.controller.is_model_loaded:
            self.model_status.set_failed(
                "配置已更改；原模型仍保持加载，点击“加载模型”后才会切换",
                still_loaded=True,
            )
        else:
            self._validate_configured_model(show_status=True)
        self._apply_quick_settings()

    @Slot()
    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "关于 AnimeTagger Lite",
            f"AnimeTagger Lite {__version__}\n\n"
            "本地、离线的 WD14 动漫图片标签与提示词工具。\n"
            "软件不会上传图片、发送遥测或后台下载模型。",
        )

    def _save_settings_safely(self, *, nonblocking: bool) -> bool:
        try:
            save_settings(self.settings, user_path=self.settings_path)
            return True
        except AnimeTaggerError as exc:
            logger.exception("GUI 设置保存失败")
            if nonblocking:
                self.statusBar().showMessage(str(exc), 6000)
            else:
                QMessageBox.warning(self, "设置保存失败", str(exc))
            return False

    @Slot()
    def _choose_export(self) -> None:
        item = self.project.get(self.project.current_id)
        if item is None or item.prompt_result is None or item.inference_result is None:
            return
        choices = {
            "正向 TXT": ExportFormat.TXT,
            "正负 TXT": ExportFormat.PROMPT_TXT,
            "JSON": ExportFormat.JSON,
        }
        default_format = ExportFormat(self.settings.default_export_format)
        default_label = next(
            label for label, value in choices.items() if value is default_format
        )
        label, accepted = QInputDialog.getItem(
            self,
            "导出当前图片",
            "格式",
            list(choices),
            list(choices).index(default_label),
            False,
        )
        if not accepted:
            return
        output_format = choices[label]
        suffix = ".json" if output_format is ExportFormat.JSON else ".txt"
        postfix = "-prompts" if output_format is ExportFormat.PROMPT_TXT else ""
        directory = (
            self.settings.recent_export_dir
            or self.settings.default_export_dir
            or str(item.source_path.parent)
        )
        suggested = str(
            Path(directory) / f"{item.source_path.stem}{postfix}{suffix}"
        )
        self._choose_export_path(output_format, suggested)

    def _choose_export_path(
        self,
        output_format: ExportFormat,
        suggested: str,
    ) -> None:
        current_suggestion = suggested
        while True:
            path_text, _filter = QFileDialog.getSaveFileName(
                self,
                "导出当前图片",
                current_suggestion,
                "JSON (*.json)" if output_format is ExportFormat.JSON else "文本 (*.txt)",
            )
            if not path_text:
                return
            path = Path(path_text)
            overwrite = False
            if path.exists():
                box = QMessageBox(self)
                box.setWindowTitle("文件已存在")
                box.setText(f"目标文件已存在：\n{path}")
                overwrite_button = box.addButton(
                    "覆盖",
                    QMessageBox.ButtonRole.DestructiveRole,
                )
                rename_button = box.addButton(
                    "更换文件名",
                    QMessageBox.ButtonRole.ActionRole,
                )
                box.addButton(
                    "取消",
                    QMessageBox.ButtonRole.RejectRole,
                )
                box.exec()
                clicked = box.clickedButton()
                if clicked is rename_button:
                    current_suggestion = str(path)
                    continue
                if clicked is not overwrite_button:
                    return
                overwrite = True
            if self.export_current_to(path, output_format, overwrite=overwrite):
                return

    def export_current_to(
        self,
        output_path: Path,
        output_format: ExportFormat,
        *,
        overwrite: bool = False,
    ) -> bool:
        item = self.project.get(self.project.current_id)
        if item is None or item.prompt_result is None or item.inference_result is None:
            return False
        try:
            exported = self.service.export_result(
                output_format,
                Path(output_path),
                item.prompt_result,
                item.inference_result,
                overwrite=overwrite,
                final_positive_prompt=item.final_positive_prompt,
                final_negative_prompt=item.final_negative_prompt,
                prompt_was_edited=item.prompt_was_edited,
                model_raw_tags=item.raw_tags,
                working_tags=item.working_tags,
            )
        except AnimeTaggerError as exc:
            logger.exception("GUI 导出失败")
            QMessageBox.warning(self, "导出失败", str(exc))
            return False
        self.settings = replace(
            self.settings,
            recent_export_dir=str(exported.parent),
        )
        self._save_settings_safely(nonblocking=True)
        self.statusBar().showMessage(f"已导出：{exported}", 8000)
        return True

    # --- state restoration and safe close -------------------------------

    def _update_action_states(self) -> None:
        busy = self.controller.is_busy
        single_page = self.pages.currentWidget() is self.main_splitter
        has_images = len(self.project) > 0
        current = self.project.get(self.project.current_id)
        self.start_action.setEnabled(
            single_page
            and has_images
            and self.controller.is_model_loaded
            and not busy
        )
        self.cancel_action.setEnabled(self.controller.is_queue_active)
        self.model_status.setEnabled(not busy)
        self.add_action.setEnabled(single_page and not busy)
        self.paste_action.setEnabled(single_page and not busy)
        self.remove_action.setEnabled(single_page and has_images and not busy)
        self.clear_action.setEnabled(single_page and has_images and not busy)
        can_export = (
            current is not None
            and current.prompt_result is not None
            and current.inference_result is not None
        )
        self.export_action.setEnabled(single_page and can_export and not busy)
        self.copy_combined_action.setEnabled(
            single_page
            and current is not None
            and bool(
                current.final_positive_prompt or current.final_negative_prompt
            )
        )
        self.settings_action.setEnabled(not busy)
        self.backend_combo.setEnabled(not busy)
        self.quick_load.setEnabled(not busy)
        self.add_tag_button.setEnabled(current is not None and not busy)
        self.delete_tag_button.setEnabled(current is not None and not busy)
        self.tag_table.setEnabled(not busy)
        self.prompt_panel.setEnabled(not busy)
        self.prompt_panel.inject_button.setEnabled(not busy and current is not None and current.prompt_result is not None)
        record = self._injection_undo
        self.prompt_panel.undo_injection.setEnabled(
            not busy and current is not None and record is not None
            and current.id == record[0] and current.edit_revision == record[2]
        )
        self.profile_combo.setEnabled(not busy)
        self.general_spin.setEnabled(not busy)
        self.character_spin.setEnabled(not busy)
        self.negative_combo.setEnabled(
            not busy and self.settings.profile != "lora_caption"
        )
        self.trigger_edit.setEnabled(not busy)
        self.restore_tags_button.setEnabled(
            current is not None and bool(current.raw_tags) and not busy
        )
        self.batch_panel.sync_controller_state()

    def _restore_ui_state(self) -> None:
        geometry = self.ui_settings.value("main/geometry")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        modern = self.ui_settings.value("main/layout_version") == "2"
        main_state = self.ui_settings.value("main/splitter") if modern else None
        if isinstance(main_state, QByteArray):
            self.main_splitter.restoreState(main_state)
        right_state = self.ui_settings.value("main/right_splitter") if modern else None
        if isinstance(right_state, QByteArray):
            self.right_splitter.restoreState(right_state)
        header_state = self.ui_settings.value("main/tag_header") if modern else None
        if isinstance(header_state, QByteArray):
            self.tag_table.horizontalHeader().restoreState(header_state)
        page_index = self.ui_settings.value("main/page", 0)
        try:
            self.pages.setCurrentIndex(int(page_index))
        except (TypeError, ValueError):
            self.pages.setCurrentIndex(0)

    def _set_tag_visuals_enabled(self, enabled: bool) -> None:
        self.tag_visual_provider.set_enabled(enabled)
        self.ui_settings.setValue("tag_visuals/enabled", enabled)
        self.ui_settings.sync()

    def _save_ui_state(self) -> None:
        self.ui_settings.setValue("main/layout_version", "2")
        self.ui_settings.setValue("main/geometry", self.saveGeometry())
        self.ui_settings.setValue(
            "main/splitter",
            self.main_splitter.saveState(),
        )
        self.ui_settings.setValue(
            "main/right_splitter",
            self.right_splitter.saveState(),
        )
        self.ui_settings.setValue(
            "main/tag_header",
            self.tag_table.horizontalHeader().saveState(),
        )
        self.ui_settings.setValue("main/page", self.pages.currentIndex())
        self.ui_settings.sync()

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._ui_state_saved_for_close:
            self._save_ui_state()
            self._ui_state_saved_for_close = True
        decoder_stopped = self.decoder.shutdown(wait_ms=0)
        controller_stopped = self.controller.shutdown(wait_ms=0)
        if not decoder_stopped or not controller_stopped:
            self._close_pending = True
            event.ignore()
            self.statusBar().showMessage(
                "正在安全结束图片解码、当前识别并释放模型，请稍候…"
            )
            self._schedule_close_retry()
            return
        self._close_pending = False
        self.clipboard_service.cleanup()
        event.accept()

    def _schedule_close_retry(self) -> None:
        if self._close_retry_scheduled:
            return
        self._close_retry_scheduled = True
        QTimer.singleShot(50, self._retry_close)

    @Slot()
    def _retry_close(self) -> None:
        self._close_retry_scheduled = False
        if self._close_pending:
            self.close()

    @Slot()
    def _on_controller_stopped(self) -> None:
        if self._close_pending:
            self._schedule_close_retry()
