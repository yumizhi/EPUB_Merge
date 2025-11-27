# Lightweight Epub Merge Tool
[![License](https://img.shields.io/github/license/yumizhi/lightweight_epub_merge_tool)](./LICENSE)
[![GitHub release](https://img.shields.io/github/v/release/yumizhi/lightweight_epub_merge_tool)](https://github.com/yumizhi/lightweight_epub_merge_tool/releases/latest)
[![GitHub All Releases](https://img.shields.io/github/downloads/yumizhi/lightweight_epub_merge_tool/total)](https://github.com/yumizhi/lightweight_epub_merge_tool/releases)
[![GitHub stars](https://img.shields.io/github/stars/yumizhi/lightweight_epub_merge_tool)](https://github.com/yumizhi/lightweight_epub_merge_tool/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/yumizhi/lightweight_epub_merge_tool)](https://github.com/yumizhi/lightweight_epub_merge_tool/network/members)


A lightweight EPUB merge tool and GUI for multi-volume light novels.

一个针对轻小说/多卷 EPUB 的轻量合并工具：尽量保留插图与章节结构，并重建按卷分组的目录（TOC）。

![Lightweight EPUB Merge Tool Screenshot](./assets/merge_epubs_tool_gui.png)

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
- Two usage modes / 两种使用方式：
  - Command line / 命令行：适合脚本化批处理
  - GUI / 图形界面（Qt / PySide6）：拖拽排序、拖文件进窗口、自然排序等
- Metadata & cover / 元数据 & 封面：
  - 支持设置作者、语言、出版社、出版日期、ISBN、主题、简介等信息
  - 支持添加/替换/提取封面图片

---

## 🚀 Download & Run (No Python required) / 打包版直接运行（无需 Python）

你可以直接在仓库 **Releases** 页面下载已打包的可执行版本，解压后即可运行（不需要安装 Python / 依赖）。

使用步骤（通用）：
1. 打开仓库的 **Releases** 页面
2. 下载与你系统对应的打包文件（通常是 `.zip` / `.tar.gz`）
3. 解压到任意目录
4. 运行其中的程序（macOS 一般是 `.app` 或可执行文件；Windows 一般是 `.exe`）

### macOS 安全提示（未签名/未公证的常见情况）
如果你看到类似提示：
> Apple 无法验证“LightweightEPUBMergeGUI”是否包含可能危害 Mac 安全或泄漏隐私的恶意软件

可按以下方式处理（任选其一）：

**方式 A（推荐）：系统设置允许一次打开**
1. 打开 **System Settings / 系统设置**
2. **Privacy & Security / 隐私与安全性**
3. 在“已阻止打开某应用”的提示附近，点击 **Open Anyway / 仍要打开**

**方式 B：移除隔离属性（quarantine）**
在终端进入解压目录后执行（把路径替换成你的实际程序路径）：
```bash
xattr -dr com.apple.quarantine "/path/to/LightweightEPUBMergeGUI.app"
````

然后再双击打开。

> 说明：这是 macOS Gatekeeper 对“非签名/非公证”应用的正常拦截机制；我不是开发者，无法进行代码签名与公证。

---

## 🧰 Run from Source / 源码运行（适合开发者）

### Requirements / 环境要求

* Python 3.8+
* CLI：仅标准库，无第三方依赖
* GUI（Qt）：需要 `PySide6`

### Install / 安装

```bash
git clone https://github.com/yumizhi/lightweight_epub_merge_tool.git
cd lightweight_epub_merge_tool
```

如需运行 GUI：

```bash
pip install PySide6
```

> 在 macOS / Linux 上，如果你有多个 Python 版本，请确保 `pip` 与运行 `python3` 的环境一致。

---

## 📌 Usage / 使用方法

仓库包含两个核心入口：

* `merge_epubs.py` — 核心合并逻辑 / 命令行工具
* `merge_epubs_gui.py` — GUI（PySide6 / Qt）

> 注意：GUI 脚本需要与 `merge_epubs.py` 位于同一目录。

---

### 1) GUI (Recommended) / 图形界面（推荐）：`merge_epubs_gui.py`

启动：

```bash
python3 merge_epubs_gui.py
```

主要能力：

* 文件列表管理

  * 支持拖拽排序（上下拖动即可调整卷顺序）
  * 支持 Shift / Ctrl / Command 多选
  * 支持 Delete 键删除选中项
* 支持从 Finder / 文件管理器直接把 `.epub` 拖进窗口自动添加
* “按文件名自然排序”

  * 自动将 `xxx 2.epub` 排在 `xxx 11.epub` 之前
* 元数据 & 封面（GUI 中可直接填写/选择）

  * 作者、语言、出版社、出版日期、ISBN、主题、简介
  * 卷标题模板（可自定义）
  * 封面：仅新增 / 强制替换 / 一键提取首卷封面

适用场景：

* 偶尔合并一整套轻小说，不想记命令行参数
* 希望直观地拖动调整卷顺序
* 像管理播放列表一样管理待合并文件

---

### 2) Command-line / 命令行：`merge_epubs.py`

基础用法：

```bash
python3 merge_epubs.py OUTPUT.epub VOL1.epub VOL2.epub VOL3.epub ...
```

常用参数（示例与含义）：

* 基础元数据（覆盖或写入）
  `--title` / `--author` / `--language` / `--publisher` / `--published` / `--isbn` / `--subject` / `--description`

  > 作者与主题支持用 `//` 分隔多个值
* 卷标题模板（自定义“第 n 卷”显示方式）
  `--volume-label-template "Vol.{n} {name}"`

  > 未指定时会根据语言自动选择常见格式（中/日/韩/英）
* 封面相关

  * `-c/--cover FILE`：若合并产物缺失封面则添加
  * `-C/--replace-cover FILE`：无论是否已有封面都强制替换
  * `-S/--extract-cover PATH`：从第一本输入 EPUB 中提取封面到指定路径（自动补齐扩展名）

注意：

* 命令行方式无法在执行后再调整卷顺序，合并顺序完全取决于命令行参数顺序
* 需要自动排序/拖拽调序，建议使用 GUI

---

## 🧾 TOC & Internal Structure / 合并后目录结构说明

合并后的 EPUB 会包含一个新的基于 `nav.xhtml` 的全书目录，大致结构如下：

```
第1卷 Gamers 01
  ├─ 序章
  ├─ 第一章 …
  └─ …
第2卷 Gamers 02
  ├─ …
第3卷 …
  └─ …
Gamers DLC - 01
  └─ …
```

每一卷的目录解析逻辑：

1. 若存在带 `properties="nav"` 的 `nav.xhtml`：解析原目录并挂载到对应卷标题之下
2. 否则若存在 `toc.ncx`：解析 NCX 生成卷级目录
3. 否则：按 spine 顺序生成「章节 1 / 章节 2 / …」的简单目录

主流阅读器（如 Apple Books、Calibre、KOReader 等）会直接使用这个新目录进行展示。

---

## ⚠️ Limitations / 已知限制

* 不进行复杂排版美化或 CSS 统一
  工具目标是“内容完整 + 目录可用”，而不是“重排版发行级样式”
* 对于结构严重不规范或“伪 EPUB”（缺失 `META-INF/container.xml`、缺 OPF、结构损坏等），可能无法成功合并
* 合并后的合订本如果插图很多，体积可能较大，在部分设备上加载会偏慢
* 主要针对普通小说 / 轻小说等线性阅读内容设计
  对教材、多栏排版、重交互类电子书支持有限
* 不处理 DRM / 加密电子书
