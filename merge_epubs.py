import argparse
import datetime
import mimetypes
import sys
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional, Tuple
import xml.etree.ElementTree as ET
from urllib.parse import unquote

# --- 配置与常量 ---
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
NSMAP = {"opf": OPF_NS, "dc": DC_NS}
EPUB_MIMETYPE = "application/epub+zip"

ET.register_namespace("", OPF_NS)
ET.register_namespace("dc", DC_NS)

LOCALIZED_VOL_LABELS = {
    "ko": "제 {n}권",
    "ja": "第{n}巻",
    "zh": "第{n}卷",
    "en": "Volume {n}",
}


def _local_name(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag

def get_opf_path(zf: zipfile.ZipFile) -> str:
    try:
        data = zf.read("META-INF/container.xml")
        root = ET.fromstring(data)
        ns = {'n': CONTAINER_NS}
        rootfile = root.find(".//n:rootfile", ns)
        if rootfile is None: rootfile = root.find(".//rootfile") # 宽容模式
        return rootfile.attrib["full-path"]
    except: return ""


def parse_language_from_opf(opf_root: ET.Element) -> Optional[str]:
    lang_node = opf_root.find("dc:language", NSMAP)
    if lang_node is not None and (lang_node.text or "").strip():
        return lang_node.text.strip()
    return None


def detect_language_from_book(path: Path) -> Optional[str]:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            opf_path = get_opf_path(zf)
            if not opf_path:
                return None
            opf_root = ET.fromstring(zf.read(opf_path))
            return parse_language_from_opf(opf_root)
    except Exception:
        return None

# ==========================================
# 核心功能：统一目录解析 (扁平化)
# ==========================================
def extract_toc_as_flat_list(epub_path: str) -> List[dict]:
    """
    提取 EPUB 目录为线性列表，供 GUI 显示和后端合并使用。
    结构: [{'title': '序章', 'href': 'text/c1.xhtml'}, ...]
    策略: 优先 NAV (EPUB3) -> 其次 NCX (EPUB2) -> 最后 Spine (无目录时)
    """
    items = []
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            opf_path = get_opf_path(z)
            if not opf_path: return []
            
            opf_dir = str(PurePosixPath(opf_path).parent)
            if opf_dir == ".": opf_dir = ""
            
            opf_data = z.read(opf_path)
            opf_root = ET.fromstring(opf_data)
            manifest = opf_root.find("opf:manifest", NSMAP)
            spine = opf_root.find("opf:spine", NSMAP)
            
            # 1. 定位目录文件
            nav_href = None
            ncx_href = None
            
            if manifest is not None:
                # 找 NAV
                for item in manifest.findall("opf:item", NSMAP):
                    props = (item.get("properties") or "").split()
                    if "nav" in props:
                        nav_href = item.get("href")
                        break
                # 找 NCX
                toc_id = spine.get("toc") if spine is not None else None
                if toc_id:
                    for item in manifest.findall("opf:item", NSMAP):
                        if item.get("id") == toc_id:
                            ncx_href = item.get("href")
                            break

            # 2. 解析 (NAV 优先)
            if nav_href:
                full = f"{opf_dir}/{nav_href}" if opf_dir else nav_href
                items = _parse_nav(z, full)
            elif ncx_href:
                full = f"{opf_dir}/{ncx_href}" if opf_dir else ncx_href
                items = _parse_ncx(z, full)
            
            # 3. 兜底 Spine
            if not items and spine is not None:
                id_map = {i.get("id"): i.get("href") for i in manifest.findall("opf:item", NSMAP)}
                for idx, ref in enumerate(spine.findall("opf:itemref", NSMAP)):
                    href = id_map.get(ref.get("idref"))
                    if href: items.append({"title": f"Chapter {idx+1}", "href": href})

    except Exception as e:
        print(f"Error parsing TOC: {e}")
    return items

def _parse_nav(zf, path):
    """解析 NAV.xhtml 中的所有链接，拉平"""
    items = []
    try:
        root = ET.fromstring(zf.read(path))
        # 查找 nav[epub:type='toc'] 或 nav
        toc_node = None
        for n in root.iter():
            if "toc" in (n.get("epub:type") or n.get("type") or ""): toc_node = n; break
        if not toc_node:
            for n in root.iter(): 
                if _local_name(n.tag) == "nav": toc_node = n; break
        
        if toc_node is not None:
            # 简单粗暴：按文档顺序提取所有 <a> 标签
            # 这样可以忽略原书复杂的嵌套，强制拉平为“卷下即章节”
            for a in toc_node.iter():
                if _local_name(a.tag) == "a" and a.get("href"):
                    text = "".join(a.itertext()).strip()
                    items.append({"title": text or "Untitled", "href": a.get("href")})
    except: pass
    return items

def _parse_ncx(zf, path):
    """解析 NCX 中的 navPoint，拉平"""
    items = []
    try:
        root = ET.fromstring(zf.read(path))
        for np in root.iter():
            if _local_name(np.tag) == "navPoint":
                label = ""
                for lb in np.iter():
                    if _local_name(lb.tag) == "text": label = lb.text; break
                
                src = ""
                for c in np:
                    if _local_name(c.tag) == "content": src = c.get("src"); break
                
                if src:
                    items.append({"title": label or "Untitled", "href": src})
    except: pass
    return items


def _find_existing_cover_item(manifest: ET.Element) -> Optional[ET.Element]:
    for item in manifest.findall("opf:item", NSMAP):
        props = (item.get("properties") or "").split()
        if "cover-image" in props:
            return item
    return None


def _ensure_cover_metadata(opf_root: ET.Element, cover_id: str):
    metadata_node = opf_root.find("opf:metadata", NSMAP)
    if metadata_node is None:
        return
    for meta in list(metadata_node.findall("opf:meta", NSMAP)):
        if meta.get("name") == "cover":
            metadata_node.remove(meta)
    ET.SubElement(metadata_node, f"{{{OPF_NS}}}meta", {"name": "cover", "content": cover_id})


def apply_cover_image(out_zip: zipfile.ZipFile, opf_root: ET.Element, opf_dir: str, cover_path: Path, replace: bool):
    manifest = opf_root.find("opf:manifest", NSMAP)
    if manifest is None:
        return
    existing = _find_existing_cover_item(manifest)
    if existing is not None and not replace:
        return
    if existing is not None and replace:
        manifest.remove(existing)

    if not cover_path.exists():
        raise FileNotFoundError(f"Cover file not found: {cover_path}")

    mime, _ = mimetypes.guess_type(str(cover_path))
    mime = mime or "image/jpeg"
    ext = cover_path.suffix or ".jpg"
    href = f"cover{ext}"
    dest = f"{opf_dir}/{href}" if opf_dir else href

    out_zip.writestr(dest, cover_path.read_bytes())

    ET.SubElement(manifest, f"{{{OPF_NS}}}item", {
        "id": "cover-image",
        "href": href,
        "media-type": mime,
        "properties": "cover-image",
    })
    _ensure_cover_metadata(opf_root, "cover-image")


def extract_cover_image(epub_path: Path, dest: Path) -> Optional[Path]:
    try:
        with zipfile.ZipFile(epub_path, "r") as zf:
            opf_path = get_opf_path(zf)
            if not opf_path:
                return None
            opf_root = ET.fromstring(zf.read(opf_path))
            manifest = opf_root.find("opf:manifest", NSMAP)
            if manifest is None:
                return None
            cover_item = _find_existing_cover_item(manifest)
            if cover_item is None:
                return None
            href = cover_item.get("href")
            if not href:
                return None
            opf_dir = str(PurePosixPath(opf_path).parent)
            if opf_dir == ".":
                opf_dir = ""
            src_path = f"{opf_dir}/{href}" if opf_dir else href
            data = zf.read(src_path)
            mime = cover_item.get("media-type") or mimetypes.guess_type(href)[0] or "image/jpeg"
            suffix = mimetypes.guess_extension(mime) or Path(href).suffix or ".jpg"
            final_dest = dest.with_suffix(suffix)
            dest.parent.mkdir(parents=True, exist_ok=True)
            final_dest.write_bytes(data)
            return final_dest
    except Exception:
        return None

# ==========================================
# 合并逻辑
# ==========================================
def build_base_opf(title: str, metadata: Dict[str, Optional[str]]) -> ET.Element:
    pkg = ET.Element(f"{{{OPF_NS}}}package", {"version": "3.0", "unique-identifier": "BookId"})
    meta = ET.SubElement(pkg, f"{{{OPF_NS}}}metadata")
    ET.SubElement(meta, f"{{{DC_NS}}}identifier", {"id": "BookId"}).text = str(uuid.uuid4())
    ET.SubElement(meta, f"{{{DC_NS}}}title").text = title

    lang = metadata.get("language") or "zh"
    ET.SubElement(meta, f"{{{DC_NS}}}language").text = lang

    authors = metadata.get("author") or ""
    for creator in [p.strip() for p in authors.split("//") if p.strip()]:
        ET.SubElement(meta, f"{{{DC_NS}}}creator").text = creator

    for subj in [s.strip() for s in (metadata.get("subject") or "").split("//") if s.strip()]:
        ET.SubElement(meta, f"{{{DC_NS}}}subject").text = subj

    if metadata.get("publisher"):
        ET.SubElement(meta, f"{{{DC_NS}}}publisher").text = metadata["publisher"]
    if metadata.get("published"):
        ET.SubElement(meta, f"{{{DC_NS}}}date").text = metadata["published"]
    if metadata.get("isbn"):
        ET.SubElement(meta, f"{{{DC_NS}}}identifier", {"id": "BookISBN", "opf:scheme": "ISBN"}).text = metadata["isbn"]
    if metadata.get("description"):
        ET.SubElement(meta, f"{{{DC_NS}}}description").text = metadata["description"]

    ET.SubElement(meta, f"{{{OPF_NS}}}meta", {"property": "dcterms:modified"}).text = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ET.SubElement(pkg, f"{{{OPF_NS}}}manifest")
    ET.SubElement(pkg, f"{{{OPF_NS}}}spine")
    return pkg

def _format_volume_label(idx: int, alias: str, language: Optional[str], custom_template: Optional[str]) -> str:
    if custom_template:
        return custom_template.format(n=idx + 1, name=alias)
    if language and language in LOCALIZED_VOL_LABELS:
        return LOCALIZED_VOL_LABELS[language].format(n=idx + 1)
    return LOCALIZED_VOL_LABELS.get("en", "Volume {n}").format(n=idx + 1)


def merge_epubs(output_path, input_items, title=None, metadata: Optional[Dict[str, Optional[str]]] = None, volume_label_template: Optional[str] = None, cover: Optional[Path] = None, replace_cover: bool = False):
    # input_items: [(path, alias, [renamed_chapters]), ...]
    resolved_out = Path(output_path).expanduser()
    if resolved_out.parent:
        resolved_out.parent.mkdir(parents=True, exist_ok=True)
    final_title = title if title else resolved_out.stem
    metadata = metadata or {}

    # 1. 基础 OPF
    first_path = Path(input_items[0][0]).expanduser()
    detected_lang = metadata.get("language") or detect_language_from_book(first_path) or "en"
    metadata.setdefault("language", detected_lang)

    with zipfile.ZipFile(first_path, "r") as z:
        opf_rel = get_opf_path(z)
    opf_dir = str(PurePosixPath(opf_rel).parent)
    if opf_dir == ".": opf_dir = ""
    
    opf_root = build_base_opf(final_title, metadata)
    manifest = opf_root.find("opf:manifest", NSMAP)
    spine = opf_root.find("opf:spine", NSMAP)
    
    volume_nodes = [] # 存储 TOC 节点

    with zipfile.ZipFile(resolved_out, "w") as out_zip:
        out_zip.writestr("mimetype", EPUB_MIMETYPE, compress_type=zipfile.ZIP_STORED)
        out_zip.writestr("META-INF/container.xml", 
            f'<?xml version="1.0"?><container version="1.0" xmlns="{CONTAINER_NS}"><rootfiles><rootfile full-path="{opf_rel}" media-type="application/oebps-package+xml"/></rootfiles></container>')

        written = set()

        for idx, item in enumerate(input_items):
            # item 结构: (path, alias, user_chaps)
            path, alias, user_chaps = item
            
            path = Path(path).expanduser()
            prefix, id_pfx = (f"v{idx}/", f"v{idx}_") if idx > 0 else ("", "")
            
            # 关键：先用统一逻辑提取原始目录 (用于获取 href)
            original_toc = extract_toc_as_flat_list(str(path))
            
            with zipfile.ZipFile(path, "r") as zin:
                opf_p = get_opf_path(zin)
                src_dir = str(PurePosixPath(opf_p).parent)
                if src_dir == ".": src_dir = ""
                
                # --- 复制资源 ---
                bk_root = ET.fromstring(zin.read(opf_p))
                bk_man = bk_root.find("opf:manifest", NSMAP)
                href_map = {} # old -> new

                for it in bk_man.findall("opf:item", NSMAP):
                    ohref = it.get("href")
                    if not ohref: continue
                    nhref = f"{prefix}{ohref}" if prefix else ohref
                    nid = f"{id_pfx}{it.get('id')}"
                    
                    # 记录映射
                    href_map[ohref] = nhref
                    href_map[unquote(ohref)] = nhref

                    # 写入文件
                    s_path = f"{src_dir}/{ohref}" if src_dir else ohref
                    d_path = f"{opf_dir}/{nhref}" if opf_dir else nhref
                    
                    if d_path not in written:
                        try:
                            data = None
                            try: data = zin.read(s_path)
                            except: data = zin.read(unquote(s_path))
                            out_zip.writestr(d_path, data)
                            written.add(d_path)
                        except: pass
                    
                    # 注册 Manifest
                    props = it.get("properties", "").replace("nav", "").strip()
                    attrs = {"id": nid, "href": nhref, "media-type": it.get("media-type")}
                    if props: attrs["properties"] = props
                    ET.SubElement(manifest, f"{{{OPF_NS}}}item", attrs)

                # --- 复制 Spine ---
                bk_spi = bk_root.find("opf:spine", NSMAP)
                for sp in bk_spi.findall("opf:itemref", NSMAP):
                    ref = sp.get("idref")
                    ET.SubElement(spine, f"{{{OPF_NS}}}itemref", {"idref": f"{id_pfx}{ref}"})

                # --- 构建卷 TOC 节点 (Level 2) ---
                vol_li = ET.Element("li")
                
                # 确定卷的入口链接 (通常是第一章)
                vol_href = "#"
                chap_list_html = []
                
                if original_toc:
                    # 获取第一章的链接作为卷的链接
                    first_orig = original_toc[0]['href'].split('#')[0]
                    first_new = href_map.get(first_orig) or href_map.get(unquote(first_orig))
                    if first_new: vol_href = first_new

                    # 构建章节列表 (Level 3)
                    if original_toc:
                        vol_ol = ET.SubElement(vol_li, "ol")
                        for i, toc_item in enumerate(original_toc):
                            chap_li = ET.SubElement(vol_ol, "li")
                            
                            # 计算新链接
                            orig_clean = toc_item['href'].split('#')[0]
                            frag = toc_item['href'].split('#')[1] if '#' in toc_item['href'] else ""
                            base_new = href_map.get(orig_clean) or href_map.get(unquote(orig_clean))
                            
                            if base_new:
                                final_href = f"{base_new}#{frag}" if frag else base_new
                                a = ET.SubElement(chap_li, "a", {"href": final_href})
                                # 优先使用用户在 GUI 修改的名字，CLI 模式下 user_chaps 为 None
                                if user_chaps and i < len(user_chaps) and user_chaps[i] is not None:
                                    a.text = user_chaps[i]
                                else:
                                    a.text = toc_item['title']
                
                # 创建卷名链接 (Level 2 Link)
                # 注意：这里我们把卷名放在最前面，且给它加了链接
                volume_label = _format_volume_label(idx, alias or f"Volume {idx+1}", metadata.get("language"), volume_label_template)
                a_vol = ET.Element("a", {"href": vol_href})
                a_vol.text = volume_label
                vol_li.insert(0, a_vol) # 插在 ol 前面
                
                volume_nodes.append((vol_href, vol_li))

        # 4. 封面处理
        if cover is not None:
            apply_cover_image(out_zip, opf_root, opf_dir, cover, replace_cover)

        # 5. 生成总 NAV (书 -> 卷 -> 章)
        # 获取第一卷的链接作为书名的链接
        book_href = volume_nodes[0][0] if volume_nodes else "#"
        nav_html = _build_nav_html(final_title, book_href, [n[1] for n in volume_nodes])
        
        nav_name = "nav-merged.xhtml"
        out_zip.writestr(f"{opf_dir}/{nav_name}" if opf_dir else nav_name, nav_html)
        
        ET.SubElement(manifest, f"{{{OPF_NS}}}item", {
            "id": "nav-merged", "href": nav_name, "media-type": "application/xhtml+xml", "properties": "nav"
        })
        out_zip.writestr(opf_rel, ET.tostring(opf_root, encoding="utf-8", xml_declaration=True))

def _build_nav_html(book_title, book_href, vol_lis):
    """
    构建符合阅读器要求的三级目录：
    <ol>
      <li> <a href="vol1_start">书名</a>
        <ol>
          <li> <a href="vol1_start">卷1</a>
            <ol> ...chapters... </ol>
          </li>
          ...
        </ol>
      </li>
    </ol>
    """
    html = ET.Element("html", {"xmlns": "http://www.w3.org/1999/xhtml", "xmlns:epub": "http://www.idpf.org/2007/ops"})
    head = ET.SubElement(html, "head")
    ET.SubElement(head, "title").text = book_title
    ET.SubElement(ET.SubElement(head, "style"), "text").text = "ol { list-style: none; } a { text-decoration: none; }"
    
    body = ET.SubElement(html, "body")
    nav = ET.SubElement(body, "nav", {"epub:type": "toc", "id": "toc"})
    
    root_ol = ET.SubElement(nav, "ol")
    root_li = ET.SubElement(root_ol, "li")
    
    # Level 1: 书名 (带链接！)
    a_book = ET.SubElement(root_li, "a", {"href": book_href})
    a_book.text = book_title
    
    # Level 2 Container
    vols_ol = ET.SubElement(root_li, "ol")
    for li in vol_lis: vols_ol.append(li)
    
    return ET.tostring(html, encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge multiple EPUB files into a single volume with a unified TOC.")
    parser.add_argument("output", help="输出 EPUB 文件路径")
    parser.add_argument("inputs", nargs="+", help="需要合并的 EPUB 文件路径")
    parser.add_argument("--title", help="合并后电子书标题（默认使用输出文件名）")
    parser.add_argument("--author", help="作者名，多个作者用 // 分隔")
    parser.add_argument("--language", help="语言代码，用于目录本地化与元数据")
    parser.add_argument("--publisher", help="出版社")
    parser.add_argument("--published", help="出版日期 (YYYY-MM-DD)")
    parser.add_argument("--isbn", help="ISBN 号")
    parser.add_argument("--subject", help="主题/标签，多个值用 // 分隔")
    parser.add_argument("--description", help="简介文本")
    parser.add_argument("--volume-label-template", help="卷标题模板，例如 '제 {n}권' 或 'Vol.{n} {name}'")
    parser.add_argument("-c", "--cover", type=Path, help="指定封面图片，如不存在封面则添加")
    parser.add_argument("-C", "--replace-cover", type=Path, help="强制替换封面图片")
    parser.add_argument("-S", "--extract-cover", type=Path, help="从第一本 EPUB 提取封面到指定路径（自动补扩展名）")

    args = parser.parse_args()

    # CLI 模式下，将文件名（不含扩展名）作为卷名，且不进行章节重命名（user_chaps=None）
    input_items = []
    for path in args.inputs:
        p = Path(path)
        if not p.exists():
            print(f"Error: Input file not found: {path}", file=sys.stderr)
            sys.exit(1)
        input_items.append((str(p), p.stem, None))

    metadata = {
        "author": args.author,
        "language": args.language,
        "publisher": args.publisher,
        "published": args.published,
        "isbn": args.isbn,
        "subject": args.subject,
        "description": args.description,
    }

    if args.extract_cover:
        extracted = extract_cover_image(Path(input_items[0][0]), args.extract_cover)
        if extracted:
            print(f"Cover extracted to: {extracted}")
        else:
            print("No cover image found to extract.")

    try:
        print("Starting EPUB merge...")
        print(f"Output: {args.output}")
        print(f"Inputs: {[item[0] for item in input_items]}")

        cover_to_use = args.replace_cover or args.cover
        replace_flag = bool(args.replace_cover)

        merge_epubs(
            args.output,
            input_items,
            title=args.title,
            metadata=metadata,
            volume_label_template=args.volume_label_template,
            cover=cover_to_use,
            replace_cover=replace_flag,
        )

        print("\nSuccessfully merged EPUBs.")
        print(f"Output file: {Path(args.output).resolve()}")

    except Exception as e:
        print(f"\nError during merge: {e}", file=sys.stderr)
        sys.exit(1)