#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import re
import platform
from typing import Optional, Dict
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QMessageBox,
    QAbstractItemView, QProgressBar, QFrame, QFormLayout, QDialog,
    QDialogButtonBox, QTreeWidget, QTreeWidgetItem, QStyle, QHeaderView,
    QTextEdit, QCheckBox
)
from PySide6.QtCore import Qt, QThread, Signal, QSettings, QUrl
from PySide6.QtGui import QKeySequence, QShortcut, QFont, QDesktopServices

# 尝试导入后端
try:
    from merge_epubs import merge_epubs, extract_toc_as_flat_list, extract_cover_image
except ImportError:
    def merge_epubs(*a): pass
    def extract_toc_as_flat_list(p): return []
    def extract_cover_image(p, d): return None

# ==========================================
# 现代化样式表 (QSS)
# ==========================================
MODERN_STYLESHEET = """
/* 全局设定 */
QMainWindow, QWidget#CentralWidget {
    background-color: #F5F7FA; /* 现代冷灰背景 */
}
QLabel {
    color: #333333;
    font-size: 13px;
    font-weight: 500;
}
/* 卡片容器 */
QFrame.Card {
    background-color: #FFFFFF;
    border: 1px solid #E1E4E8;
    border-radius: 10px;
}

/* 按钮通用 */
QPushButton {
    border: 1px solid #D1D5DA;
    border-radius: 6px;
    background-color: #FFFFFF;
    color: #24292E;
    padding: 6px 12px;
    font-weight: 600;
    font-size: 12px;
}
QPushButton:hover {
    background-color: #F3F4F6;
    border-color: #9CA3AF;
}
QPushButton:pressed {
    background-color: #E5E7EB;
}

/* 强调按钮 (蓝色) */
QPushButton.Primary {
    background-color: #007AFF;
    color: #FFFFFF;
    border: 1px solid #007AFF;
    font-size: 14px;
    padding: 10px 20px;
}
QPushButton.Primary:hover {
    background-color: #0069D9;
    border-color: #0062CC;
}
QPushButton.Primary:pressed {
    background-color: #0056B3;
}

/* 危险/警告按钮 */
QPushButton.Danger:hover {
    color: #CF222E;
    border-color: #CF222E;
    background-color: #FFEBE9;
}

/* 输入框 */
QLineEdit {
    background-color: #FFFFFF;
    border: 1px solid #D1D5DA;
    border-radius: 6px;
    padding: 8px;
    color: #24292E;
    selection-background-color: #007AFF;
}
QLineEdit:focus {
    border: 1px solid #007AFF;
    outline: none;
}
QLineEdit:read-only {
    background-color: #F6F8FA;
    color: #6A737D;
}

/* 树形列表 */
QTreeWidget {
    border: none;
    background-color: transparent;
    font-size: 13px;
    outline: none;
}
QTreeWidget::item {
    height: 36px; /* 增加行高，更易点击 */
    padding: 2px;
    border-bottom: 1px solid #F0F0F0;
    color: #333;
}
QTreeWidget::item:selected {
    background-color: #EBF5FF; /* 浅蓝色背景 */
    color: #007AFF;
    border-radius: 4px;
}
QTreeWidget::item:selected:active {
    background-color: #EBF5FF; 
    color: #007AFF;
}
QTreeWidget::item:hover {
    background-color: #FAFAFA;
}

/* 树形列表头部 */
QHeaderView::section {
    background-color: #FFFFFF;
    color: #6A737D;
    padding: 4px 8px;
    border: none;
    border-bottom: 2px solid #E1E4E8;
    font-weight: bold;
    font-size: 11px;
    text-transform: uppercase;
}

/* 进度条 */
QProgressBar {
    border: none;
    background-color: #E1E4E8;
    border-radius: 2px;
    height: 4px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #007AFF;
    border-radius: 2px;
}

/* 滚动条美化 */
QScrollBar:vertical {
    border: none;
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #C1C1C1;
    min-height: 20px;
    border-radius: 4px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
"""

class StrictTreeWidget(QTreeWidget):
    def __init__(self, add_cb, parent=None):
        super().__init__(parent)
        self.add_cb = add_cb
        self.setHeaderLabels(["目录结构 (卷名 -> 章节)  |  双击重命名", "路径"])
        self.setColumnHidden(1, True)
        self.header().setSectionResizeMode(0, QHeaderView.Stretch) # 自适应宽度
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setAlternatingRowColors(False)
        self.setRootIsDecorated(True) # 显示展开的小三角
        self.setIndentation(20) # 缩进宽度

    def dragEnterEvent(self, e): 
        if e.mimeData().hasUrls(): e.acceptProposedAction()
        else: super().dragEnterEvent(e)
    def dragMoveEvent(self, e):
        if e.mimeData().hasUrls(): e.acceptProposedAction()
        else: super().dragMoveEvent(e)
    def dropEvent(self, e):
        if e.mimeData().hasUrls():
            self.add_cb([u.toLocalFile() for u in e.mimeData().urls()])
            e.acceptProposedAction()
        else: super().dropEvent(e)


class DetailDialog(QDialog):
    def __init__(
        self,
        parent,
        metadata: Dict[str, Optional[str]],
        volume_label_template: Optional[str],
        cover_path: Optional[str],
        replace_cover: bool,
        extract_dest: Optional[str],
        extract_cb,
    ):
        super().__init__(parent)
        self.setWindowTitle("详细信息")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.in_author = QLineEdit(metadata.get("author") or "")
        self.in_language = QLineEdit(metadata.get("language") or "")
        self.in_publisher = QLineEdit(metadata.get("publisher") or "")
        self.in_published = QLineEdit(metadata.get("published") or "")
        self.in_isbn = QLineEdit(metadata.get("isbn") or "")
        self.in_subject = QLineEdit(metadata.get("subject") or "")
        self.in_description = QTextEdit()
        self.in_description.setPlainText(metadata.get("description") or "")
        self.in_volume_label = QLineEdit(volume_label_template or "")

        cover_row = QHBoxLayout()
        self.in_cover = QLineEdit(cover_path or "")
        btn_cover = QPushButton("选择封面")
        btn_cover.clicked.connect(self.choose_cover)
        cover_row.addWidget(self.in_cover)
        cover_row.addWidget(btn_cover)

        self.chk_replace_cover = QCheckBox("强制替换已有封面")
        self.chk_replace_cover.setChecked(replace_cover)

        extract_row = QHBoxLayout()
        self.in_extract_dest = QLineEdit(extract_dest or "")
        btn_extract_browse = QPushButton("选择…")
        btn_extract_browse.clicked.connect(self.choose_extract_path)
        btn_extract = QPushButton("提取首卷封面")
        btn_extract.clicked.connect(lambda: self.extract_cover(extract_cb))
        extract_row.addWidget(self.in_extract_dest)
        extract_row.addWidget(btn_extract_browse)
        extract_row.addWidget(btn_extract)

        form.addRow("作者:", self.in_author)
        form.addRow("语言:", self.in_language)
        form.addRow("出版社:", self.in_publisher)
        form.addRow("出版日期:", self.in_published)
        form.addRow("ISBN:", self.in_isbn)
        form.addRow("主题(// 分隔):", self.in_subject)
        form.addRow("描述/简介:", self.in_description)
        form.addRow("卷标题模板:", self.in_volume_label)
        form.addRow("封面图片:", cover_row)
        form.addRow("封面策略:", self.chk_replace_cover)
        form.addRow("提取封面输出:", extract_row)

        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def choose_cover(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择封面图片", str(Path(self.in_cover.text()).expanduser()), "Images (*.png *.jpg *.jpeg *.webp *.gif)")
        if f:
            self.in_cover.setText(f)

    def choose_extract_path(self):
        f, _ = QFileDialog.getSaveFileName(self, "保存提取封面", self.in_extract_dest.text(), "Images (*.png *.jpg *.jpeg *.webp *.gif)")
        if f:
            self.in_extract_dest.setText(f)

    def extract_cover(self, extract_cb):
        dest = self.in_extract_dest.text().strip()
        if not dest:
            f, _ = QFileDialog.getSaveFileName(self, "保存提取封面", "", "Images (*.png *.jpg *.jpeg *.webp *.gif)")
            if not f:
                return
            dest = f
            self.in_extract_dest.setText(dest)

        ok, msg = extract_cb(Path(dest))
        if ok:
            QMessageBox.information(self, "成功", msg)
        else:
            QMessageBox.warning(self, "提示", msg)

    def get_metadata(self):
        return {
            "author": self.in_author.text().strip() or None,
            "language": self.in_language.text().strip() or None,
            "publisher": self.in_publisher.text().strip() or None,
            "published": self.in_published.text().strip() or None,
            "isbn": self.in_isbn.text().strip() or None,
            "subject": self.in_subject.text().strip() or None,
            "description": self.in_description.toPlainText().strip() or None,
        }

    def get_volume_template(self):
        return self.in_volume_label.text().strip() or None

    def get_cover_path(self):
        text = self.in_cover.text().strip()
        return text or None

    def get_replace_cover(self):
        return self.chk_replace_cover.isChecked()

    def get_extract_dest(self):
        text = self.in_extract_dest.text().strip()
        return text or None

class Worker(QThread):
    fin = Signal(bool, str, str)

    def __init__(
        self,
        out: str,
        data,
        title: Optional[str],
        metadata: Dict[str, Optional[str]],
        volume_label_template: Optional[str],
        cover_path: Optional[Path],
        replace_cover: bool,
    ):
        super().__init__()
        self.out = out
        self.data = data
        self.title = title
        self.metadata = metadata
        self.volume_label_template = volume_label_template
        self.cover_path = cover_path
        self.replace_cover = replace_cover

    def run(self):
        try:
            merge_epubs(
                self.out,
                self.data,
                title=self.title,
                metadata=self.metadata,
                volume_label_template=self.volume_label_template,
                cover=self.cover_path,
                replace_cover=self.replace_cover,
            )
            self.fin.emit(True, "Success", self.out)
        except Exception as e:
            self.fin.emit(False, str(e), "")

class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EPUB Merge")
        self.resize(900, 700)
        self.set = QSettings("MySoft", "EpubMergeModern")

        self.metadata = {
            "author": None,
            "language": None,
            "publisher": None,
            "published": None,
            "isbn": None,
            "subject": None,
            "description": None,
        }
        self.volume_label_template: Optional[str] = None
        self.cover_path: Optional[str] = None
        self.replace_cover = False
        self.extract_dest: Optional[str] = None
        
        # 应用样式
        self.setStyleSheet(MODERN_STYLESHEET)
        
        # 中心部件
        main_widget = QWidget()
        main_widget.setObjectName("CentralWidget")
        self.setCentralWidget(main_widget)
        
        # 主布局：垂直
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(24, 24, 24, 16)
        main_layout.setSpacing(16)

        # ----------------------------------------------------
        # 1. 顶部标题栏 + 工具栏 (Header)
        # ----------------------------------------------------
        header_layout = QHBoxLayout()
        
        title_lbl = QLabel("书籍列表")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #1a1a1a;")
        
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()

        # 工具按钮
        self.btn_add = QPushButton("添加书籍")
        self.btn_add.setIcon(self.style().standardIcon(QStyle.SP_FileIcon))
        
        self.btn_sort = QPushButton(" 自然排序")
        self.btn_sort.setIcon(self.style().standardIcon(QStyle.SP_FileDialogListView))
        
        self.btn_clear = QPushButton(" 清空")
        self.btn_clear.setProperty("class", "Danger") # 使用 Danger 样式
        self.btn_clear.setIcon(self.style().standardIcon(QStyle.SP_DialogDiscardButton))

        header_layout.addWidget(self.btn_add)
        header_layout.addWidget(self.btn_sort)
        header_layout.addWidget(self.btn_clear)
        
        main_layout.addLayout(header_layout)

        # ----------------------------------------------------
        # 2. 列表区域 (Card)
        # ----------------------------------------------------
        tree_card = QFrame()
        tree_card.setProperty("class", "Card")
        tree_layout = QVBoxLayout(tree_card)
        tree_layout.setContentsMargins(12, 12, 12, 12)
        
        self.tree = StrictTreeWidget(self.add_files)
        tree_layout.addWidget(self.tree)
        
        # 删除按钮悬浮在列表下方或集成在右键菜单，这里放在卡片底部
        bottom_tree_layout = QHBoxLayout()
        self.hint_lbl = QLabel("💡 提示: 拖拽调整顺序，双击修改名称。最终结构: 书名 > 卷名 > 章节")
        self.hint_lbl.setStyleSheet("color: #999; font-size: 12px;")
        
        self.btn_del = QPushButton("移除选中")
        self.btn_del.setCursor(Qt.PointingHandCursor)
        self.btn_del.setStyleSheet("border: none; color: #888;")
        self.btn_del.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        
        bottom_tree_layout.addWidget(self.hint_lbl)
        bottom_tree_layout.addStretch()
        bottom_tree_layout.addWidget(self.btn_del)
        
        tree_layout.addLayout(bottom_tree_layout)
        
        main_layout.addWidget(tree_card, stretch=1)

        # ----------------------------------------------------
        # 3. 设置区域 (Card)
        # ----------------------------------------------------
        settings_card = QFrame()
        settings_card.setProperty("class", "Card")
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(20, 16, 20, 16)
        settings_layout.setSpacing(12)

        st_title = QLabel("输出设置")
        st_title.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 2px;")
        settings_layout.addWidget(st_title)

        form_grid = QFormLayout()
        form_grid.setHorizontalSpacing(12)
        form_grid.setVerticalSpacing(10)

        self.in_title = QLineEdit()
        self.in_title.setPlaceholderText("总标题 (例如: 某某合集)")
        form_grid.addRow("书籍标题:", self.in_title)

        out_row = QHBoxLayout()
        self.in_out = QLineEdit()
        self.in_out.setPlaceholderText("输出文件路径")
        btn_browse = QPushButton("浏览")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self.on_browse)
        out_row.addWidget(self.in_out)
        out_row.addWidget(btn_browse)
        form_grid.addRow("输出文件:", out_row)

        detail_row = QHBoxLayout()
        self.detail_status = QLabel("未设置")
        self.detail_status.setStyleSheet("color: #777; font-size: 12px;")
        btn_detail = QPushButton("详细信息…")
        btn_detail.clicked.connect(self.show_detail_dialog)
        detail_row.addWidget(self.detail_status)
        detail_row.addStretch()
        detail_row.addWidget(btn_detail)
        form_grid.addRow("更多选项:", detail_row)

        settings_layout.addLayout(form_grid)

        main_layout.addWidget(settings_card)

        # ----------------------------------------------------
        # 4. 底部操作栏 (Footer)
        # ----------------------------------------------------
        footer_layout = QHBoxLayout()
        
        # 进度条
        self.progress = QProgressBar()
        self.progress.hide()
        self.progress.setFixedWidth(200)
        
        self.btn_run = QPushButton("开始合并")
        self.btn_run.setProperty("class", "Primary") # 应用 Primary 样式
        self.btn_run.setCursor(Qt.PointingHandCursor)
        self.btn_run.setMinimumWidth(150)

        footer_layout.addWidget(self.progress)
        footer_layout.addStretch()
        footer_layout.addWidget(self.btn_run)

        main_layout.addLayout(footer_layout)

        # 绑定事件
        self.btn_add.clicked.connect(self.on_add)
        self.btn_sort.clicked.connect(self.on_sort)
        self.btn_del.clicked.connect(self.on_del)
        self.btn_clear.clicked.connect(self.on_clear)
        self.btn_run.clicked.connect(self.on_run)

        # 快捷键
        QShortcut(QKeySequence.Delete, self.tree, activated=self.on_del)

        self.update_detail_status()

    # -----------------------------------------
    # 逻辑部分 (与之前保持一致)
    # -----------------------------------------
    def add_files(self, paths):
        exist = {self.tree.topLevelItem(i).text(1) for i in range(self.tree.topLevelItemCount())}
        valid = [p for p in paths if p.lower().endswith(".epub") and p not in exist]
        valid.sort(key=lambda x: [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', Path(x).name)])
        
        for p in valid:
            path = Path(p)
            # Level 1 (Volume) - 字体加粗颜色深
            root = QTreeWidgetItem([path.stem, str(path)])
            root.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable | Qt.ItemIsDragEnabled)
            root.setIcon(0, self.style().standardIcon(QStyle.SP_DirIcon))
            self.tree.addTopLevelItem(root)
            
            # Level 2 (Chapters)
            toc = extract_toc_as_flat_list(str(path))
            for item in toc:
                child = QTreeWidgetItem([item['title'], ""])
                child.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
                # 章节用一个小点或者空图标，靠缩进区分
                root.addChild(child)
                
            root.setExpanded(False)
            
        if valid and not self.in_title.text():
            name = self.tree.topLevelItem(0).text(0)
            clean = re.sub(r'^\d+[\.\-_ ]+', '', name)
            self.in_title.setText(clean + " 合集")
            if not self.in_out.text():
                self.in_out.setText(str(Path(valid[0]).parent / f"{clean}_merged.epub"))

    def on_run(self):
        if self.tree.topLevelItemCount() == 0: return
        if not self.in_out.text(): return QMessageBox.warning(self, "提示", "请选择输出路径")

        cover_path = None
        if self.cover_path:
            cover_path = Path(self.cover_path).expanduser()
            if not cover_path.exists():
                return QMessageBox.warning(self, "提示", "封面路径不存在")

        data = []
        root = self.tree.invisibleRootItem()
        for i in range(root.childCount()):
            vol_item = root.child(i)
            chap_names = [vol_item.child(k).text(0) for k in range(vol_item.childCount())]
            data.append((vol_item.text(1), vol_item.text(0), chap_names))

        self.setEnabled(False)
        self.progress.show()
        self.progress.setRange(0, 0) # 忙碌动画
        self.btn_run.setText("正在合并...")

        self.wk = Worker(
            self.in_out.text(),
            data,
            self.in_title.text().strip() or None,
            self.metadata,
            self.volume_label_template,
            cover_path,
            self.replace_cover,
        )
        self.wk.fin.connect(self.on_fin)
        self.wk.start()

    def on_fin(self, ok, msg, p):
        self.setEnabled(True)
        self.progress.hide()
        self.btn_run.setText("开始合并")
        if ok:
            box = QMessageBox(self)
            box.setWindowTitle("成功")
            box.setText("合并完成！")
            box.setIcon(QMessageBox.Information)
            op = box.addButton("打开文件夹", QMessageBox.ActionRole)
            box.addButton("关闭", QMessageBox.AcceptRole)
            box.exec()
            if box.clickedButton() == op:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(p).parent)))
        else:
            QMessageBox.critical(self, "错误", msg)

    def on_add(self):
        d = self.set.value("last", "")
        f, _ = QFileDialog.getOpenFileNames(self, "添加书籍", d, "EPUB Files (*.epub)")
        if f: 
            self.set.setValue("last", str(Path(f[0]).parent))
            self.add_files(f)
            
    def on_sort(self):
        items = [self.tree.takeTopLevelItem(0) for _ in range(self.tree.topLevelItemCount())]
        items.sort(key=lambda x: [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', x.text(0))])
        for i in items: self.tree.addTopLevelItem(i)

    def on_del(self):
        for i in self.tree.selectedItems():
            if i.parent() is None: (i.parent() or self.tree.invisibleRootItem()).removeChild(i)
            
    def on_clear(self): self.tree.clear()

    def on_browse(self):
        f, _ = QFileDialog.getSaveFileName(self, "保存文件", self.in_out.text(), "EPUB Files (*.epub)")
        if f: self.in_out.setText(f)

    def perform_extract(self, dest: Path):
        if self.tree.topLevelItemCount() == 0:
            return False, "请先添加至少一本 EPUB 后再提取封面"

        first_path = Path(self.tree.topLevelItem(0).text(1))
        extracted = extract_cover_image(first_path, dest)
        if extracted:
            self.extract_dest = str(extracted)
            return True, f"封面已提取到: {extracted}"
        return False, "未找到可提取的封面"

    def show_detail_dialog(self):
        dlg = DetailDialog(
            self,
            self.metadata,
            self.volume_label_template,
            self.cover_path,
            self.replace_cover,
            self.extract_dest,
            self.perform_extract,
        )
        if dlg.exec():
            self.metadata = dlg.get_metadata()
            self.volume_label_template = dlg.get_volume_template()
            self.cover_path = dlg.get_cover_path()
            self.replace_cover = dlg.get_replace_cover()
            self.extract_dest = dlg.get_extract_dest()
            self.update_detail_status()

    def update_detail_status(self):
        pieces = []
        if any(self.metadata.values()):
            pieces.append("元数据")
        if self.volume_label_template:
            pieces.append("卷标题")
        if self.cover_path:
            pieces.append("封面")
        if not pieces:
            self.detail_status.setText("未设置")
            self.detail_status.setStyleSheet("color: #777; font-size: 12px;")
        else:
            self.detail_status.setText("，".join(pieces))
            self.detail_status.setStyleSheet("color: #0069D9; font-size: 12px;")

if __name__ == "__main__":
    # 高分屏支持
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)
    
    # 设置全局字体
    font = QFont("Segoe UI", 10)
    if platform.system() == "Darwin":
        font = QFont("SF Pro Text", 13)
    app.setFont(font)
    
    w = App()
    w.show()
    sys.exit(app.exec())