#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
基于 Qt 的 EPUB 合并图形界面：

功能：
- 选择多个 EPUB 文件
- 列表支持：
  - 鼠标拖拽排序（InternalMove，直觉式拖动）
  - Shift / Command 多选
  - Delete 键删除选中
  - 从 Finder / 文件管理器拖入 .epub 文件添加
- 一键“按文件名自然排序”（2 在 11 前面）
- 选择输出文件路径，调用 merge_epubs 进行合并
"""

import sys
import re
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QLineEdit,
    QFileDialog,
    QMessageBox,
    QAbstractItemView,
)
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtCore import Qt


from merge_epubs import merge_epubs  # 假定 merge_epubs.py 在同目录，且提供 merge_epubs 函数


class FileListWidget(QListWidget):
    """
    自定义列表控件：
    - 支持内部拖动排序（InternalMove）
    - 支持从外部拖入文件（.epub）添加
    """

    def __init__(self, add_files_callback, parent=None):
        super().__init__(parent)
        self.add_files_callback = add_files_callback

        # 内部拖动排序
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        # 如果是外部文件拖入
        if event.mimeData().hasUrls():
            paths = []
            for url in event.mimeData().urls():
                local_path = url.toLocalFile()
                if local_path and local_path.lower().endswith(".epub"):
                    paths.append(local_path)
            if paths:
                self.add_files_callback(paths)
            event.acceptProposedAction()
        else:
            # 内部拖动排序：交给父类默认行为
            super().dropEvent(event)


class EpubMergeWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("EPUB 合并工具")
        self.resize(800, 500)

        # 中心 widget + 总布局
        central = QWidget(self)
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # ===== 文件列表区域 =====
        top_label = QLabel("待合并的 EPUB 文件（可拖动排序）：")
        main_layout.addWidget(top_label)

        list_layout = QHBoxLayout()
        main_layout.addLayout(list_layout)

        # 左侧：文件列表
        self.list_widget = FileListWidget(self.add_files_from_paths)
        list_layout.addWidget(self.list_widget, stretch=1)

        # 右侧：操作按钮
        btn_layout = QVBoxLayout()
        list_layout.addLayout(btn_layout)

        btn_add = QPushButton("添加文件…")
        btn_add.clicked.connect(self.on_add_files)
        btn_layout.addWidget(btn_add)

        btn_remove = QPushButton("删除选中")
        btn_remove.clicked.connect(self.on_remove_selected)
        btn_layout.addWidget(btn_remove)

        btn_clear = QPushButton("清空列表")
        btn_clear.clicked.connect(self.on_clear_list)
        btn_layout.addWidget(btn_clear)

        btn_sort = QPushButton("按文件名自然排序")
        btn_sort.clicked.connect(self.on_sort_naturally)
        btn_layout.addWidget(btn_sort)

        btn_layout.addStretch(1)

        # Delete 快捷键删除选中
        QShortcut(QKeySequence.Delete, self.list_widget, activated=self.on_remove_selected)

        # ===== 输出路径区域 =====
        output_layout = QHBoxLayout()
        main_layout.addLayout(output_layout)

        lbl_output = QLabel("输出文件：")
        output_layout.addWidget(lbl_output)

        self.output_edit = QLineEdit()
        output_layout.addWidget(self.output_edit, stretch=1)

        btn_browse = QPushButton("浏览…")
        btn_browse.clicked.connect(self.on_choose_output)
        output_layout.addWidget(btn_browse)

        # ===== 底部：状态栏 + 合并按钮 =====
        bottom_layout = QHBoxLayout()
        main_layout.addLayout(bottom_layout)

        self.status_label = QLabel("就绪")
        bottom_layout.addWidget(self.status_label, stretch=1)

        self.btn_merge = QPushButton("开始合并")
        self.btn_merge.clicked.connect(self.on_merge)
        bottom_layout.addWidget(self.btn_merge)

    # ---------- 工具方法 ----------

    def _iter_items(self):
        for i in range(self.list_widget.count()):
            yield self.list_widget.item(i)

    def _existing_paths(self) -> set:
        paths = set()
        for item in self._iter_items():
            path = item.data(Qt.UserRole)
            if path:
                paths.add(path)
        return paths

    @staticmethod
    def _natural_key(name: str):
        """
        自然排序 key：把 'xxx 11.epub' 按数字排序到 'xxx 2.epub' 之后。
        """
        parts = re.split(r"(\d+)", name)
        key = []
        for part in parts:
            if part.isdigit():
                key.append(int(part))
            else:
                key.append(part.lower())
        return key

    def _set_status(self, text: str):
        self.status_label.setText(text)
        self.statusBar().showMessage(text)

    # ---------- 文件列表操作 ----------

    def add_files_from_paths(self, paths):
        """
        从给定路径列表中加入文件，去重，然后按文件名自然排序刷新列表。
        """
        existing = self._existing_paths()
        new_paths = []
        for p in paths:
            p_str = str(Path(p).resolve())
            if p_str not in existing:
                new_paths.append(p_str)

        if not new_paths:
            return

        all_paths = list(existing) + new_paths

        # 按文件名自然排序
        all_paths.sort(key=lambda p: self._natural_key(Path(p).name))

        # 重新刷新列表
        self.list_widget.clear()
        for p in all_paths:
            item = QListWidgetItem(Path(p).name)
            item.setData(Qt.UserRole, p)
            self.list_widget.addItem(item)

        self._set_status(f"新添加 {len(new_paths)} 个文件，当前共 {len(all_paths)} 个。")

    def on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择要合并的 EPUB 文件",
            "",
            "EPUB files (*.epub);;All files (*.*)",
        )
        if not files:
            return
        self.add_files_from_paths(files)

    def on_remove_selected(self):
        selected = self.list_widget.selectedItems()
        if not selected:
            return
        for item in selected:
            row = self.list_widget.row(item)
            self.list_widget.takeItem(row)
        self._set_status(f"已删除 {len(selected)} 个条目，剩余 {self.list_widget.count()} 个。")

    def on_clear_list(self):
        if self.list_widget.count() == 0:
            return
        if QMessageBox.question(
            self,
            "确认清空",
            "确定要清空所有待合并文件吗？",
        ) != QMessageBox.Yes:
            return
        self.list_widget.clear()
        self._set_status("已清空列表。")

    def on_sort_naturally(self):
        """
        对当前列表按文件名做自然排序。
        """
        count = self.list_widget.count()
        if count <= 1:
            return

        items = []
        while self.list_widget.count():
            items.append(self.list_widget.takeItem(0))

        items.sort(key=lambda it: self._natural_key(it.text()))

        for it in items:
            self.list_widget.addItem(it)

        self._set_status("已按文件名自然排序。")

    # ---------- 输出路径 & 合并 ----------

    def on_choose_output(self):
        default_name = "merged.epub"
        # 如果有文件，用第一个文件名做默认前缀
        if self.list_widget.count() > 0:
            first_item = self.list_widget.item(0)
            first_name = Path(first_item.data(Qt.UserRole)).stem
            default_name = f"{first_name}_merged.epub"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "选择输出 EPUB 文件",
            default_name,
            "EPUB files (*.epub);;All files (*.*)",
        )
        if not file_path:
            return

        self.output_edit.setText(str(Path(file_path).resolve()))

    def _get_input_paths_in_order(self):
        paths = []
        for item in self._iter_items():
            p = item.data(Qt.UserRole)
            if p:
                paths.append(p)
        return paths

    def on_merge(self):
        input_paths = self._get_input_paths_in_order()
        if not input_paths:
            QMessageBox.warning(self, "提示", "请先添加至少一个 EPUB 文件。")
            return

        output_path = self.output_edit.text().strip()
        if not output_path:
            QMessageBox.warning(self, "提示", "请先指定输出文件路径。")
            return

        out = Path(output_path)
        if out.exists():
            ret = QMessageBox.question(
                self,
                "确认覆盖",
                f"输出文件已存在：\n{out}\n\n是否覆盖？",
            )
            if ret != QMessageBox.Yes:
                return

        # 最后确认
        if QMessageBox.question(
            self,
            "确认合并",
            f"将按当前顺序合并 {len(input_paths)} 个文件，输出到：\n{out}",
        ) != QMessageBox.Yes:
            return

        # 执行合并（同步执行，若卷数很多会阻塞一段时间）
        try:
            self.btn_merge.setEnabled(False)
            self._set_status("正在合并，请稍候……")
            QApplication.processEvents()

            total_items = merge_epubs(str(out), input_paths)

        except Exception as e:
            self.btn_merge.setEnabled(True)
            self._set_status("合并失败。")
            QMessageBox.critical(
                self,
                "合并失败",
                f"发生错误：\n{e}",
            )
            return

        self.btn_merge.setEnabled(True)
        self._set_status("合并完成。")
        QMessageBox.information(
            self,
            "合并完成",
            f"成功合并 {len(input_paths)} 个卷。\n"
            f"输出文件：\n{out}\n\n"
            f"manifest 共 {total_items} 项。",
        )


def main():
    app = QApplication(sys.argv)
    window = EpubMergeWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
