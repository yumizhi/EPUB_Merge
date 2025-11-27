# lightweight_epub_merge_tool

A lightweight EPUB merge tool and GUI for multi-volume light novels.

> 一个针对轻小说多卷 EPUB 的轻量级合并工具，尽量保留插图与章节结构，并重建按卷分组的目录（TOC）。

---

## ✨ Features / 功能特性

- Merge multiple `.epub` volumes into a single omnibus book
  将多卷 EPUB 合并为一本“合订本”
- Preserve all resources of each volume
  保留每卷的文本、插图、CSS 等资源，不丢插图页
- Support both EPUB 3 `nav.xhtml` and EPUB 2 `toc.ncx`
  自动识别并合并不同目录格式
- Rebuild a global table of contents grouped by volume
  重建按卷分组的总目录，例如：
  - 第 1 卷 xxx
    - 序章
    - 第一章 …
  - 第 2 卷 xxx
    - …
  - 短篇 / 外传等
- If an EPUB has no `nav` / `ncx`, generate a simple chapter list from the spine  
  对无目录文件的 EPUB，按 spine 顺序生成简单章节列表
- Robust handling of messy EPUB layouts  
  适配不同站点导出的 EPUB：
  - 自动处理 `Chapter 1.html` / `Chapter%201.html` 等路径差异
  - 自动查找 `content.opf`（支持根目录、`OEBPS/`、`EPUB/` 等多种结构）
- Two usage modes
  两种使用方式：
  - 命令行工具：适合脚本化批处理
  - 图形界面（GUI）：
    - Tk 版：基于 Tkinter，零额外依赖（仅为legacy中的旧版本代码支持，注意merge_tool版本）
  - Qt 版：基于 PySide6，支持拖拽排序、拖文件进窗口、自然排序等，体验更好
  - 元数据&封面：命令行支持设置作者、语言、出版社、出版日期、ISBN、主题、描述等基础信息，并能添加/替换/提取封面图片

---

## 📦 Installation / 安装

本项目是若干 Python 脚本组成的工具，无需复杂安装流程，clone 后即可使用。

```bash
git clone https://github.com/yumizhi/lightweight_epub_merge_tool.git
cd lightweight_epub_merge_tool
````

* Python：3.8 或更高版本
* 命令行与 Tk GUI：

  * 仅依赖 Python 标准库，无第三方依赖
* Qt GUI（推荐）需要安装 `PySide6`：

```bash
pip install PySide6
```

> 在 macOS / Linux 上，如果你有多个 Python 版本，请确保 `pip` 与运行 `python3` 的环境一致。

也可以直接从本仓库的 “Releases” 页面下载已打包版本，根据需要放到任意目录运行。

---

## 🚀 Usage / 使用方法

仓库中包含一个核心脚本和两个 GUI 前端：

* `merge_epubs.py` — 核心合并逻辑 / 命令行工具
* `merge_epubs_gui_tk.py` — 基于 Tkinter 的简易 GUI
* `merge_epubs_gui.py` — 基于 PySide6 / Qt 的 GUI（推荐）

> 注意：GUI 脚本需要与 `merge_epubs.py` 位于同一目录。

### 1. Command-line / 命令行：`merge_epubs.py`

适合习惯终端操作，或希望写脚本批量合并的场景。

基础用法：

```bash
python3 merge_epubs.py OUTPUT.epub VOL1.epub VOL2.epub VOL3.epub ...
```

* `OUTPUT.epub`：输出的合并后 EPUB 文件路径
* `VOLX.epub`：各卷输入文件，顺序即为合并顺序

常用可选参数：

- `--title` / `--author` / `--language` / `--publisher` / `--published` / `--isbn` / `--subject` / `--description`：批量写入或覆盖基础元数据（作者、语言、出版社、出版时间、ISBN 等，作者与主题支持用 `//` 分隔多个值）。
- `--volume-label-template`：自定义卷标题模板，例如 `"제 {n}권"`、`"Vol.{n} {name}"`。未指定时会根据语言自动选择常见格式（中/日/韩/英）。
- `-c/--cover FILE`：若当前合并产物缺失封面则添加。
- `-C/--replace-cover FILE`：无论是否已有封面都强制替换为指定图片。
- `-S/--extract-cover PATH`：从第一本输入 EPUB 中提取封面到指定路径（自动补齐扩展名）。

示例：

```bash
python3 merge_epubs.py ImoutoLife全集.epub "ImoutoLife 01.epub" "ImoutoLife 02.epub" "ImoutoLife 03.epub"
```

建议提前按卷号重命名文件，或使用 GUI 中的“自然排序”功能。

---

### 2. Tk GUI（简易版）：`merge_epubs_gui_tk.py` (仅支持legacy中对应的merge_epubs.py)

基于标准库 Tkinter，无需额外安装第三方 GUI 库，适合只需要一个“能点就行”的界面。

启动：

```bash
python3 merge_epubs_gui_tk.py
```

主要功能：

* “添加文件…”：多选 `.epub` 文件加入列表
* 列表中可以：

  * 上移 / 下移单条记录
  * 多选后“删除选中”
* “选择…”：指定输出 EPUB 文件名及保存路径
* “开始合并”：按当前列表顺序调用 `merge_epubs.py` 进行合并

---

### 3. Qt GUI：`merge_epubs_gui.py`

基于 PySide6 / Qt，提供更完整的桌面交互体验。

依赖安装：

```bash
pip install PySide6
```

启动：

```bash
python3 merge_epubs_gui.py
```

额外特性：

* 文件列表：

  * 支持拖拽排序（按住某一行上下拖动即可调整卷顺序）
  * 支持 Shift / Ctrl / Command 多选
  * 支持 Delete 键删除选中项
* 支持从 Finder / 文件管理器中直接将 `.epub` 文件拖入窗口自动添加
* “按文件名自然排序”：

  * 自动将 `xxx 2.epub` 排在 `xxx 11.epub` 之前（按数值排序而非纯字符串排序）
* 输出路径选择与合并流程与 Tk 版一致
* 元数据 & 封面：可在界面中直接填写作者、语言、出版社、出版日期、ISBN、主题、简介、卷标题模板，并选择封面图片（支持“仅新增”或“强制替换”），也可一键提取首卷封面到本地

适用场景：

* 偶尔合并一整套轻小说，不想记命令行参数
* 希望直观地拖动调整卷顺序
* 像管理播放列表一样管理待合并文件

---

## 📚 TOC & Internal Structure / 合并后目录结构说明

合并后的 EPUB 会包含一个新的基于 `nav.xhtml` 的全书目录，大致结构如下：

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

对每一卷，内部处理逻辑大致为：

1. 若存在带 `properties="nav"` 的 `nav.xhtml`：

   * 解析原目录，并挂载到对应卷标题之下
2. 否则若存在 `toc.ncx`：

   * 解析 NCX 生成卷级目录
3. 否则：

   * 按 spine 顺序生成「章节 1 / 章节 2 / …」的简单目录

主流阅读器（如 Apple Books、Calibre、KOReader 等）会直接使用这个新目录进行展示。

---

## ⚠️ Limitations / 已知限制

* 不进行复杂排版美化或 CSS 统一
  工具目标是“内容完整 + 目录可用”，而不是“重排版发行级样式”
* 对于结构严重不规范或“伪 EPUB” 文件（缺失 `META-INF/container.xml`、缺 OPF、结构损坏等），可能无法成功合并
* 合并后的合订本如果插图很多，体积可能较大，在部分设备上加载会偏慢
* 主要针对普通小说 / 轻小说等线性阅读内容设计
  对教材、多栏排版、重交互类电子书支持有限
