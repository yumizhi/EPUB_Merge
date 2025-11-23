#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
EPUB 合并图形界面（拖动排序 + 全局排序版本）：
- 选择多个 EPUB 文件
- 支持单行拖动排序：按住某一行，上下拖动，松开时一次性重排（可从顶拖到底）
- 保留多选删除（Shift / Command 多选后点“删除选中”）
- 每次添加文件后，对全部文件按“文件名”排序
- 选择输出文件路径，调用 merge_epubs 进行合并
"""

import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
import traceback
import re


# 假定 merge_epubs.py 和本文件在同一目录
from merge_epubs import merge_epubs


class EpubMergeApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("EPUB 合并工具")
        self.geometry("640x480")
        self.minsize(600, 420)

        # 存放所选文件的实际路径（与 Listbox 行一一对应）
        self.input_files: list[str] = []

        # 拖动状态：起始索引、起始 Y、是否真的发生了拖动、拖动的那一项内容
        self._drag_from_index: int | None = None
        self._drag_start_y: int = 0
        self._drag_moved: bool = False
        self._drag_item_path: str | None = None
        self._drag_item_text: str | None = None

        self._build_widgets()

    # ===================== UI 构建 =====================

    def _build_widgets(self):
        # ==== 上方：文件选择区域 ====
        top_frame = tk.Frame(self)
        top_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 左侧：文件列表 + 排序按钮
        list_frame = tk.Frame(top_frame)
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        label = tk.Label(list_frame, text="待合并的 EPUB 文件（按顺序）：")
        label.pack(anchor="w")

        self.listbox = tk.Listbox(
            list_frame,
            selectmode=tk.EXTENDED,   # 支持多选
            activestyle="dotbox"
        )
        self.listbox.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)

        # 滚动条
        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.listbox.yview)

        # 绑定拖动排序事件（按下 / 移动 / 松开）
        self.listbox.bind("<Button-1>", self.on_listbox_button_press)
        self.listbox.bind("<B1-Motion>", self.on_listbox_drag_motion)
        self.listbox.bind("<ButtonRelease-1>", self.on_listbox_button_release)

        # 右侧：操作按钮（添加 / 删除 / 上移 / 下移）
        btn_frame = tk.Frame(top_frame)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

        btn_add = tk.Button(btn_frame, text="添加文件…", command=self.on_add_files)
        btn_add.pack(fill=tk.X, pady=2)

        btn_remove = tk.Button(btn_frame, text="删除选中", command=self.on_remove_selected)
        btn_remove.pack(fill=tk.X, pady=2)

        btn_up = tk.Button(btn_frame, text="上移", command=self.on_move_up)
        btn_up.pack(fill=tk.X, pady=10)

        btn_down = tk.Button(btn_frame, text="下移", command=self.on_move_down)
        btn_down.pack(fill=tk.X, pady=2)

        # ==== 中间：输出文件选择 ====
        output_frame = tk.LabelFrame(self, text="输出设置")
        output_frame.pack(fill=tk.X, padx=10, pady=(0, 10), ipady=4)

        tk.Label(output_frame, text="输出文件：").pack(side=tk.LEFT, padx=(10, 4))

        self.output_var = tk.StringVar()
        entry = tk.Entry(output_frame, textvariable=self.output_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 4))

        btn_output = tk.Button(output_frame, text="选择…", command=self.on_choose_output)
        btn_output.pack(side=tk.LEFT, padx=(4, 10))

        # ==== 下方：状态栏 + 合并按钮 ====
        bottom_frame = tk.Frame(self)
        bottom_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.status_var = tk.StringVar(value="就绪")
        status_label = tk.Label(
            bottom_frame,
            textvariable=self.status_var,
            anchor="w"
        )
        status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_merge = tk.Button(bottom_frame, text="开始合并", command=self.on_merge)
        btn_merge.pack(side=tk.RIGHT)

        self.btn_merge = btn_merge

    # ===================== Listbox 拖动排序 =====================

    def on_listbox_button_press(self, event):
        """
        鼠标左键按下：
        - 记录起始索引、起始坐标以及该行数据
        - 不打断 Listbox 的默认行为（所以 Shift/Command 多选仍然正常）
        """
        self.listbox.focus_set()

        idx = self.listbox.nearest(event.y)
        size = self.listbox.size()
        if idx < 0 or idx >= size:
            self._drag_from_index = None
            self._drag_item_path = None
            self._drag_item_text = None
            self._drag_moved = False
            return

        self._drag_from_index = idx
        self._drag_start_y = event.y
        self._drag_moved = False

        # 记录当前这一项的内容
        self._drag_item_path = self.input_files[idx] if 0 <= idx < len(self.input_files) else None
        self._drag_item_text = self.listbox.get(idx)

        # 不 return "break"，保留 Listbox 默认单击/多选行为

    def on_listbox_drag_motion(self, event):
        """
        拖动过程中：
        - 当鼠标移动距离超过阈值时，认为进入“拖动模式”
        - 用高亮显示目标位置（单行高亮），更明显
        - 真正的重排在 ButtonRelease 时完成
        """
        if self._drag_from_index is None:
            return

        # 如果光标几乎没动，就不认为是拖动（只是单击）
        if abs(event.y - self._drag_start_y) < 3:
            return

        # 标记已经进入拖动状态
        self._drag_moved = True

        size = self.listbox.size()
        if size <= 1:
            return

        # 计算鼠标当前“靠近哪一行”
        new_index = self.listbox.nearest(event.y)
        new_index = max(0, min(size - 1, new_index))

        # 高亮当前目标行（拖动反馈更明显）
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(new_index)
        self.listbox.activate(new_index)

    def on_listbox_button_release(self, event):
        """
        鼠标松开：
        - 如果是拖动导致的释放（而不是纯点击），根据释放位置重排列表
        """
        if self._drag_from_index is None or not self._drag_moved:
            # 要么没记录起点，要么没真正拖动，只是普通点击
            self._drag_from_index = None
            self._drag_item_path = None
            self._drag_item_text = None
            self._drag_moved = False
            return

        size = self.listbox.size()
        if size <= 1:
            self._reset_drag_state()
            return

        # 目标位置
        new_index = self.listbox.nearest(event.y)
        new_index = max(0, min(size - 1, new_index))

        old_index = self._drag_from_index
        if new_index != old_index and self._drag_item_path is not None and self._drag_item_text is not None:
            self._move_item_final(old_index, new_index, self._drag_item_path, self._drag_item_text)

        self._reset_drag_state()

    def _reset_drag_state(self):
        self._drag_from_index = None
        self._drag_item_path = None
        self._drag_item_text = None
        self._drag_moved = False

    def _move_item_final(self, old_index: int, new_index: int, item_path: str, item_text: str):
        """
        在 input_files 和 listbox 中执行一次性重排：
        从 old_index 移动到 new_index。支持跨多行移动。
        """
        # 调整 new_index：删除 old_index 之后，下标会变化
        if new_index > old_index:
            new_index -= 1

        # 调整 input_files
        if 0 <= old_index < len(self.input_files):
            self.input_files.pop(old_index)
        self.input_files.insert(new_index, item_path)

        # 调整 Listbox 显示
        self.listbox.delete(old_index)
        self.listbox.insert(new_index, item_text)

        # 高亮新位置
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(new_index)
        self.listbox.activate(new_index)

    # ===================== 列表操作：添加 / 删除 / 上下移动 =====================

    def _refresh_listbox_from_files(self):
        """根据 self.input_files 完全刷新 Listbox 内容。"""
        self.listbox.delete(0, tk.END)
        for p in self.input_files:
            self.listbox.insert(tk.END, Path(p).name)

    def on_add_files(self):
        filenames = filedialog.askopenfilenames(
            title="选择要合并的 EPUB 文件",
            filetypes=[("EPUB files", "*.epub"), ("All files", "*.*")]
        )
        if not filenames:
            return

        # 新增的文件路径
        new_files: list[str] = []
        for f in filenames:
            f_str = str(Path(f).resolve())
            if f_str not in self.input_files:
                new_files.append(f_str)

        if not new_files:
            return

        # 把新文件加入总列表，然后对“全部文件”按文件名排序
        self.input_files.extend(new_files)
        self.input_files.sort(key=self._natural_key)

        # 按排序结果刷新 Listbox
        self._refresh_listbox_from_files()

    def on_remove_selected(self):
        selection = list(self.listbox.curselection())
        if not selection:
            return
        # 支持多选删除
        for idx in reversed(selection):
            self.listbox.delete(idx)
            if 0 <= idx < len(self.input_files):
                self.input_files.pop(idx)

    def on_move_up(self):
        selection = list(self.listbox.curselection())
        if not selection:
            return
        first = selection[0]
        if first <= 0:
            return
        self._move_item_by_one(first, first - 1)

    def on_move_down(self):
        selection = list(self.listbox.curselection())
        if not selection:
            return
        last = selection[-1]
        if last >= self.listbox.size() - 1:
            return
        self._move_item_by_one(last, last + 1)

    def _move_item_by_one(self, old_index: int, new_index: int):
        """简单一步上移/下移，用于按钮操作。"""
        if old_index == new_index:
            return
        # input_files
        item_path = self.input_files.pop(old_index)
        self.input_files.insert(new_index, item_path)
        # listbox
        item_text = self.listbox.get(old_index)
        self.listbox.delete(old_index)
        self.listbox.insert(new_index, item_text)
        self.listbox.selection_clear(0, tk.END)
        self.listbox.selection_set(new_index)
        self.listbox.activate(new_index)

    # ===================== 输出路径 & 合并 =====================

    def on_choose_output(self):
        default_name = "merged.epub"
        if self.input_files:
            first = Path(self.input_files[0])
            default_name = f"{first.stem}_merged.epub"

        filename = filedialog.asksaveasfilename(
            title="选择输出 EPUB 文件",
            defaultextension=".epub",
            initialfile=default_name,
            filetypes=[("EPUB files", "*.epub"), ("All files", "*.*")]
        )
        if not filename:
            return
        self.output_var.set(str(Path(filename).resolve()))

    def on_merge(self):
        if not self.input_files:
            messagebox.showwarning("提示", "请先添加至少一个 EPUB 文件。")
            return

        output_path = self.output_var.get().strip()
        if not output_path:
            messagebox.showwarning("提示", "请先选择输出文件路径。")
            return

        out_path = Path(output_path)
        if out_path.exists():
            overwrite = messagebox.askyesno(
                "确认覆盖",
                f"输出文件已存在：\n{out_path}\n\n是否覆盖？"
            )
            if not overwrite:
                return

        if not messagebox.askokcancel(
            "确认合并",
            f"将合并 {len(self.input_files)} 个文件为：\n{out_path}"
        ):
            return

        try:
            self._set_busy(True, "正在合并，请稍候…")
            total_items = merge_epubs(str(out_path), self.input_files)
        except Exception as e:
            traceback.print_exc()
            messagebox.showerror(
                "合并失败",
                f"发生错误：\n{e}"
            )
            self._set_busy(False, "合并失败")
            return

        self._set_busy(False, "合并完成")
        messagebox.showinfo(
            "合并完成",
            f"成功合并 {len(self.input_files)} 个卷。\n"
            f"生成文件：\n{out_path}\n\n"
            f"（manifest 共 {total_items} 项）"
        )

    def _set_busy(self, busy: bool, status: str):
        self.status_var.set(status)
        self.update_idletasks()
        if busy:
            self.btn_merge.config(state=tk.DISABLED)
        else:
            self.btn_merge.config(state=tk.NORMAL)
            
    def _natural_key(self, path_str: str):
        """用于自然排序的 key：文件名中的数字按数值比较。"""
        name = Path(path_str).name
        parts = re.split(r'(\d+)', name)  # 用括号保留数字段
        key = []
        for part in parts:
            if part.isdigit():
                key.append(int(part))
            else:
                key.append(part)
        return key



def main():
    app = EpubMergeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
