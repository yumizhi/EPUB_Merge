# EPUB_Merge

[![License](https://img.shields.io/github/license/yumizhi/EPUB_Merge)](https://github.com/yumizhi/EPUB_Merge/blob/main/LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/yumizhi/EPUB_Merge)](https://github.com/yumizhi/EPUB_Merge/releases/latest)
[![GitHub all releases](https://img.shields.io/github/downloads/yumizhi/EPUB_Merge/total)](https://github.com/yumizhi/EPUB_Merge/releases)
[![GitHub stars](https://img.shields.io/github/stars/yumizhi/EPUB_Merge?style=social)](https://github.com/yumizhi/EPUB_Merge/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/yumizhi/EPUB_Merge?style=social)](https://github.com/yumizhi/EPUB_Merge/network/members)


> 最近在用Apple books看轻小说，但是找到的epub都是分卷的形式，手机阅读起来有点繁琐，所以写了一个小工具把它们合并成一卷。

一个针对轻小说多卷 EPUB 的合并工具，尽量保留插图、章节结构，并重建按卷分组的目录。

## ✨ 特性（Features）

- 支持一次合并多卷 EPUB 文件，生成单一本“合订本”
- 自动复制每卷的全部资源（文本、插图、CSS 等），不丢插图页
- 同时兼容：
  - EPUB 3 的 `nav.xhtml` 目录
  - EPUB 2 的 `toc.ncx` 目录
- 自动重建**全书目录**：
  - 目录按卷分组，例如：
    - 第1卷 xxx
      - 序章
      - 第一章……
    - 第2卷 xxx
      - …
  - 对原来没有 nav / ncx 的 EPUB，会按 spine 顺序生成简单章节列表
- 兼容不同网站导出的 EPUB：
  - 自动处理 `Chapter 1.html` / `Chapter%201.html` 等路径差异
  - 自动适配不同 OPF 路径（`content.opf` 在根目录、`OEBPS/`、`EPUB/` 等）
- 提供两种使用方式：
  - **命令行工具**：适合脚本化批量处理
  - **图形界面**：
    - 简易 Tk 版（零额外依赖）
    - 高级 Qt 版（PySide6，支持拖拽排序、拖文件进窗口等）

---

## 📦 安装（Installation）

本项目是一个简单的 Python 脚本，无需打包安装，直接 clone 后使用即可。

```bash
git clone https://github.com/yumizhi/EPUB_Merge.git
cd EPUB_Merge
```

要求：
Python 3.8+（建议使用 python3 命令）
命令行模式无第三方依赖；
Qt 图形界面需要额外安装 PySide6：
```bash
pip install PySide6
```
> macOS / Linux 上如有多个 Python 版本，请确保 `pip` 与 `python3` 指向同一环境。

---

## 🚀 使用方法（Usage）

本工具支持两种主要使用方式：

1. 命令行工具（`merge_epubs.py`）
2. 图形界面（Tk 版：`epub_merge_gui_tk.py`，Qt 版：`epub_merge_gui.py`）

### 1. 命令行：`merge_epubs.py`

基础用法：

```bash
python3 merge_epubs.py [outputs_name] [inputs_name] ...
```

命令行模式适合：

* 你已经习惯终端操作；
* 希望写脚本做批量合并；
* 不需要可视化拖动排序。

---

### 2. 图形界面（GUI）

仓库中提供两个 GUI 脚本：

* `epub_merge_gui_tk.py`：基于 Tkinter，零额外依赖，功能简单；
* `epub_merge_gui.py`：基于 PySide6（Qt），交互体验更好，推荐使用。

> 需要注意的是，gui文件使用时需要与 merge_epubs.py 处于同一目录

#### 2.1 Tk 版：`epub_merge_gui_tk.py`

适用于不想安装额外 GUI 库、只要一个“能点就行”的界面。

启动：

```bash
python3 epub_merge_gui_tk.py
```

主要功能：

* “添加文件…”：多选 `.epub` 文件加入列表；
* 列表中可以：
  * 上移 / 下移某一条；
  * 选中多条后“删除选中”；
* “选择…”：指定输出 EPUB 文件名和保存位置；
* “开始合并”：按当前顺序调用 `merge_epubs` 进行合并。

#### 2.2 Qt 版（推荐）：`epub_merge_gui.py`

需要先安装：

```bash
pip install PySide6
```

启动：

```bash
python3 epub_merge_gui.py
```

额外特性：

* 列表支持：

  * **直接拖拽排序**（按住某条上下拖动即可调整顺序）
  * Shift / Ctrl / Command 多选
  * Delete 键删除选中
* 支持从 Finder / 文件管理器直接把 `.epub` 拖进窗口自动添加；
* “按文件名自然排序”：

  * 自动把 `xxx 2.epub` 排在 `xxx 11.epub` 前面（数字按数值比较，而不是字符串比较）；
* 输出路径与合并流程与 Tk 版一致。

GUI 模式适合：

* 偶尔合并一套小说，不想记命令行参数；
* 希望用拖动直观调整卷顺序；
* 希望像管理播放列表一样管理待合并文件。

---

## 📚 合并后目录结构说明（TOC）

合并后的 EPUB 会包含一个新的目录文件（基于 EPUB 3 的 `nav.xhtml`），整体结构类似：

```text
第1卷 义妹生活 01
  ├─ 序章
  ├─ 第一章 …
  └─ …
第2卷 义妹生活 02
  ├─ …
第3卷 …
  └─ …
短篇 义妹生活 短篇 - 01
  ├─ …
外传 another days - 01
  └─ …
```

内部实现在每卷上依次尝试：

1. 若存在 `properties="nav"` 的 `nav.xhtml`：

   * 解析原有目录，挂到对应卷标题下；
2. 否则若存在 `toc.ncx`：

   * 解析 NCX 生成卷级目录；
3. 再否则：

   * 按 spine 顺序生成「章节 1 / 章节 2 / …」。

主流阅读器（Apple Books、Calibre、KOReader 等）会直接使用这个新目录。

---

## ⚠️ 已知限制（Limitations）

* 不做复杂排版美化与 CSS 统一，目标是「内容完整 + 目录可用」，而不是“再版级排版”；
* 针对严重不规范或“伪 EPUB”（无 `META-INF/container.xml` / 无 OPF / 结构损坏）的文件，可能无法成功合并；
* 合并后文件较大会导致部分设备加载缓慢（尤其是插图很多的合订本）；
* 当前工具主要针对**普通小说 / 轻小说**这类线性阅读内容，对教材/多栏排版/重度交互类电子书支持有限。
