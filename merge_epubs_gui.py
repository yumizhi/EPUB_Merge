#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import re
import platform
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QMessageBox, 
    QAbstractItemView, QProgressBar, QFrame, QFormLayout, 
    QTreeWidget, QTreeWidgetItem, QStyle, QHeaderView, QSizePolicy
)
from PySide6.QtCore import Qt, QThread, Signal, QSettings, QUrl, QSize
from PySide6.QtGui import QKeySequence, QShortcut, QFont, QDesktopServices, QIcon, QColor, QPalette

# 尝试导入后端
try:
    from merge_epubs import merge_epubs, extract_toc_as_flat_list
except ImportError:
    def merge_epubs(*a): pass
    def extract_toc_as_flat_list(p): return []

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

class Worker(QThread):
    fin = Signal(bool, str, str)
    def __init__(self, out, data, t, a):
        super().__init__()
        self.args = (out, data, t, a)
    def run(self):
        try:
            merge_epubs(*self.args)
            self.fin.emit(True, "Success", self.args[0])
        except Exception as e:
            self.fin.emit(False, str(e), "")

class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("EPUB Merge")
        self.resize(900, 750)
        self.set = QSettings("MySoft", "EpubMergeModern")
        
        # 应用样式
        self.setStyleSheet(MODERN_STYLESHEET)
        
        # 中心部件
        main_widget = QWidget()
        main_widget.setObjectName("CentralWidget")
        self.setCentralWidget(main_widget)
        
        # 主布局：垂直
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(24, 24, 24, 24)
        main_layout.setSpacing(20)

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
        tree_layout.setContentsMargins(10, 10, 10, 10)
        
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
        settings_layout.setContentsMargins(20, 20, 20, 20)
        settings_layout.setSpacing(15)
        
        # 标题行
        st_title = QLabel("输出设置")
        st_title.setStyleSheet("font-weight: bold; font-size: 14px; margin-bottom: 5px;")
        settings_layout.addWidget(st_title)

        # 表单
        form_grid = QHBoxLayout()
        form_grid.setSpacing(20)

        # 左侧：书名和作者
        meta_layout = QVBoxLayout()
        meta_layout.setSpacing(10)
        
        self.in_title = QLineEdit()
        self.in_title.setPlaceholderText("总标题 (例如: 某某合集)")
        meta_layout.addWidget(QLabel("书籍标题:"))
        meta_layout.addWidget(self.in_title)
        
        self.in_author = QLineEdit()
        self.in_author.setPlaceholderText("作者名 (可选)")
        meta_layout.addWidget(QLabel("作者:"))
        meta_layout.addWidget(self.in_author)
        
        # 右侧：输出路径
        out_layout = QVBoxLayout()
        out_layout.setSpacing(10)
        
        self.in_out = QLineEdit()
        self.in_out.setPlaceholderText("选择保存位置...")
        self.in_out.setReadOnly(False)
        
        btn_browse = QPushButton("浏览...")
        btn_browse.setFixedWidth(80)
        btn_browse.clicked.connect(self.on_browse)
        
        path_row = QHBoxLayout()
        path_row.addWidget(self.in_out)
        path_row.addWidget(btn_browse)
        
        out_layout.addWidget(QLabel("输出文件:"))
        out_layout.addLayout(path_row)
        # 加一个空的 stretch 保持对齐
        out_layout.addStretch()

        form_grid.addLayout(meta_layout, 1)
        form_grid.addLayout(out_layout, 1)
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
        
        self.wk = Worker(self.in_out.text(), data, self.in_title.text(), self.in_author.text())
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