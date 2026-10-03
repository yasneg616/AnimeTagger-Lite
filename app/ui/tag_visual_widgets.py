"""Shared SVG cache, passive hover cards and read-only random-tag list."""

from __future__ import annotations

from collections import OrderedDict
import logging

from PySide6.QtCore import (QAbstractListModel, QByteArray, QEvent, QModelIndex, QObject,
                           QPoint, QPersistentModelIndex, QRectF, QSize, Qt, Signal)
from PySide6.QtGui import QIcon, QImage, QKeyEvent, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QHBoxLayout, QLabel,
                               QListView, QStyledItemDelegate, QToolTip, QVBoxLayout, QWidget)

from app.prompts.models import TagResult
from app.tag_visuals import GROUP_LABELS, TagVisual, TagVisualLibrary, default_library
from app.tag_visual_svg import compose_svg
from app.ui.theme import ink

logger = logging.getLogger(__name__)
VISUAL_ROLE = int(Qt.ItemDataRole.UserRole) + 6
NAME_ROLE = int(Qt.ItemDataRole.UserRole) + 1


class TagVisualProvider(QObject):
    changed = Signal()

    def __init__(self, parent: QObject | None = None, *, library: TagVisualLibrary | None = None,
                 enabled: bool = True, surface: str = '#20242c') -> None:
        super().__init__(parent)
        self.library = library if library is not None else default_library()
        self.enabled = enabled
        self.surface = surface
        self._cache: OrderedDict[tuple, QPixmap] = OrderedDict()
        self._errors: set[str] = set()

    def set_enabled(self, enabled: bool) -> None:
        if enabled != self.enabled:
            self.enabled = enabled
            self.changed.emit()

    def set_surface(self, surface: str) -> None:
        if surface != self.surface:
            self.surface = surface
            self._cache.clear()
            self.changed.emit()

    def visual_for(self, name: str, category: object) -> TagVisual:
        return self.library.lookup(name, category)

    def pixmap(self, visual: TagVisual, size: int = 24, dpr: float = 2) -> QPixmap | None:
        if not self.enabled or not visual.has_icon or QApplication.instance() is None:
            return None
        key = (visual.key, visual.category, self.surface, size, round(dpr,2))
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        try:
            foreground = ink(self.surface)
            paper = '#f5f6fa' if foreground == '#19202b' else '#26303e'
            svg = compose_svg(visual, self.library.directory, ink=foreground, paper=paper, preview=size>24)
            renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
            if not renderer.isValid():
                raise ValueError('SVG cannot be parsed')
            pixels = max(1, round(size*dpr))
            bitmap = QImage(pixels,pixels,QImage.Format.Format_ARGB32_Premultiplied)
            bitmap.fill(Qt.GlobalColor.transparent)
            painter=QPainter(bitmap)
            try:
                renderer.render(painter,QRectF(0,0,pixels,pixels))
            finally:
                painter.end()
            bitmap.setDevicePixelRatio(dpr)
            result=QPixmap.fromImage(bitmap)
            self._cache[key]=result
            # Bounded memory, including enlarged high-DPI previews.
            limit=544
            while len(self._cache)>limit:
                self._cache.popitem(last=False)
            large=[k for k in self._cache if k[3]>24]
            while len(large)>32:
                self._cache.pop(large.pop(0))
            small=[k for k in self._cache if k[3]<=24]
            while len(small)>512:
                self._cache.pop(small.pop(0))
            return result
        except (OSError, UnicodeError, ValueError, TypeError, KeyError) as exc:
            if visual.key not in self._errors:
                self._errors.add(visual.key)
                logger.warning('标签图示无法渲染，保留英文 %s：%s',visual.key,exc)
            return None

    def icon_for(self, name: str, category: object) -> QIcon | None:
        bitmap=self.pixmap(self.visual_for(name,category))
        return QIcon(bitmap) if bitmap is not None else None


class TagHoverCard(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent,Qt.WindowType.ToolTip)
        self.setObjectName('tagHoverCard')
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.image=QLabel()
        self.image.setFixedSize(160,160)
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title=QLabel();self.label=QLabel();self.explanation=QLabel();self.status=QLabel()
        for label in (self.title,self.label,self.explanation,self.status):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setFixedWidth(260)
        self.title.setStyleSheet('font-weight: 600;')
        text=QVBoxLayout()
        for label in (self.title,self.label,self.explanation,self.status): text.addWidget(label)
        text.addStretch(1)
        layout=QHBoxLayout(self)
        layout.setContentsMargins(12,12,12,12)
        layout.addWidget(self.image)
        layout.addLayout(text)
        self.current_visual: TagVisual | None=None

    def show_visual(self, visual: TagVisual, english: str, detail: str,
                    provider: TagVisualProvider, position: QPoint) -> None:
        self.current_visual=visual
        self.title.setText(english)
        self.label.setText(visual.label_zh or '图示与释义待补')
        self.explanation.setText(visual.explanation_zh or visual.reason)
        status={'direct':'具体图示','composed':'组合图示','schematic':'辅助示意','category_only':'类别提示（含义见文字说明）','pending':'待补图示'}[visual.status]
        self.status.setText(f'{GROUP_LABELS.get(visual.group,"其他")} · {status}\n{detail}')
        bitmap=provider.pixmap(visual,160,self.devicePixelRatioF())
        self.image.setVisible(bitmap is not None)
        self.image.setPixmap(bitmap if bitmap is not None else QPixmap())
        self.setStyleSheet(f'QWidget#tagHoverCard {{ background: {provider.surface}; border: 1px solid #8190a3; border-radius: 8px; color: {ink(provider.surface)}; }}')
        self.layout().activate()
        self.adjustSize()
        screen=QApplication.screenAt(position) or QApplication.primaryScreen()
        if screen is not None:
            available=screen.availableGeometry()
            position.setX(max(available.left(),min(position.x()+16,available.right()-self.width()+1)))
            position.setY(max(available.top(),min(position.y()+12,available.bottom()-self.height()+1)))
        self.move(position)
        self.show()


class TagVisualDelegate(QStyledItemDelegate):
    def __init__(self, view: QAbstractItemView, provider: TagVisualProvider) -> None:
        super().__init__(view)
        self.view=view;self.provider=provider
        self.card=TagHoverCard(view)
        self._index=QPersistentModelIndex()
        view.viewport().setMouseTracking(True)
        view.viewport().installEventFilter(self)
        view.installEventFilter(self)
        view.verticalScrollBar().valueChanged.connect(self.hide_card)
        view.horizontalScrollBar().valueChanged.connect(self.hide_card)
        provider.changed.connect(self.hide_card)
        model=view.model()
        if model is not None:
            for signal in (model.modelAboutToBeReset,model.dataChanged,model.rowsAboutToBeRemoved,model.layoutAboutToBeChanged):
                signal.connect(self.hide_card)

    def hide_card(self, *_args) -> None:
        self.card.hide()
        self._index=QPersistentModelIndex()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind=event.type()
        if kind in {QEvent.Type.Leave,QEvent.Type.Hide,QEvent.Type.FocusOut,QEvent.Type.MouseButtonPress,
                    QEvent.Type.KeyPress,QEvent.Type.Wheel,QEvent.Type.Resize}:
            self.hide_card()
        elif kind==QEvent.Type.MouseMove and self.card.isVisible() and watched is self.view.viewport():
            if self.view.indexAt(event.position().toPoint()) != self._index:
                self.hide_card()
        return super().eventFilter(watched,event)

    def helpEvent(self,event,view,option,index) -> bool:
        if not self.provider.enabled or not index.isValid():
            return super().helpEvent(event,view,option,index)
        visual=index.data(VISUAL_ROLE)
        if not isinstance(visual,TagVisual) or visual.status=='excluded_character':
            return super().helpEvent(event,view,option,index)
        QToolTip.hideText()
        self._index=QPersistentModelIndex(index)
        self.card.show_visual(visual,str(index.data(NAME_ROLE) or index.data()),str(index.data(Qt.ItemDataRole.ToolTipRole) or ''),
                              self.provider,event.globalPos())
        return True


class TagListModel(QAbstractListModel):
    def __init__(self, provider: TagVisualProvider, parent: QObject | None=None) -> None:
        super().__init__(parent)
        self.provider=provider
        self.tags: tuple[TagResult,...]=()
        provider.changed.connect(self.refresh_visuals)

    def set_tags(self,tags) -> None:
        self.beginResetModel();self.tags=tuple(tags);self.endResetModel()

    def refresh_visuals(self) -> None:
        if self.tags:
            self.dataChanged.emit(self.index(0),self.index(len(self.tags)-1),[int(Qt.ItemDataRole.DecorationRole),VISUAL_ROLE])

    def rowCount(self,parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.tags)

    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0<=index.row()<len(self.tags): return None
        tag=self.tags[index.row()]
        if role==Qt.ItemDataRole.DisplayRole: return f'[{tag.category.value}] {tag.output_name}'
        if role==NAME_ROLE: return tag.output_name
        if role==Qt.ItemDataRole.DecorationRole: return self.provider.icon_for(tag.output_name,tag.category)
        if role==VISUAL_ROLE: return self.provider.visual_for(tag.output_name,tag.category)
        if role==Qt.ItemDataRole.ToolTipRole: return f'来源：{tag.source.value}'
        if role==Qt.ItemDataRole.SizeHintRole: return QSize(200,34)
        return None


class TagListView(QListView):
    def __init__(self, provider: TagVisualProvider, parent: QWidget | None=None) -> None:
        super().__init__(parent)
        self.setObjectName('randomTagList')
        self.tag_model=TagListModel(provider,self)
        self.setModel(self.tag_model)
        self.setIconSize(QSize(24,24))
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setUniformItemSizes(True)
        self.visual_delegate=TagVisualDelegate(self,provider)
        self.setItemDelegate(self.visual_delegate)
        self._placeholder=QLabel('本次抽中的标签及类别',self.viewport())
        self._placeholder.setMargin(10)

    def set_tags(self,tags) -> None:
        self.tag_model.set_tags(tags)
        self._placeholder.setVisible(not self.tag_model.tags)

    def toPlainText(self) -> str:
        return '\n'.join(str(self.tag_model.index(i).data()) for i in range(self.tag_model.rowCount()))

    def keyPressEvent(self,event: QKeyEvent) -> None:
        if event.key()==Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            text='\n'.join(str(index.data()) for index in sorted(self.selectedIndexes(),key=lambda i:i.row()))
            if text: QApplication.clipboard().setText(text)
            event.accept();return
        super().keyPressEvent(event)
