import sys
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import List, Tuple, Optional
import xml.etree.ElementTree as ET
from urllib.parse import unquote
import datetime

# --- 配置与常量 ---
OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
NSMAP = {"opf": OPF_NS, "dc": DC_NS}
EPUB_MIMETYPE = "application/epub+zip"

ET.register_namespace("", OPF_NS)
ET.register_namespace("dc", DC_NS)

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

# ==========================================
# 合并逻辑
# ==========================================
def build_base_opf(title, author):
    pkg = ET.Element(f"{{{OPF_NS}}}package", {"version": "3.0", "unique-identifier": "BookId"})
    meta = ET.SubElement(pkg, f"{{{OPF_NS}}}metadata")
    ET.SubElement(meta, f"{{{DC_NS}}}identifier", {"id": "BookId"}).text = str(uuid.uuid4())
    ET.SubElement(meta, f"{{{DC_NS}}}title").text = title
    ET.SubElement(meta, f"{{{DC_NS}}}language").text = "zh"
    if author: ET.SubElement(meta, f"{{{DC_NS}}}creator").text = author
    ET.SubElement(meta, f"{{{OPF_NS}}}meta", {"property": "dcterms:modified"}).text = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    ET.SubElement(pkg, f"{{{OPF_NS}}}manifest")
    ET.SubElement(pkg, f"{{{OPF_NS}}}spine")
    return pkg

def merge_epubs(output_path, input_items, title=None, author=None):
    # input_items: [(path, alias, [renamed_chapters]), ...]
    resolved_out = Path(output_path).expanduser()
    if resolved_out.parent: resolved_out.parent.mkdir(parents=True, exist_ok=True)
    final_title = title if title else resolved_out.stem

    # 1. 基础 OPF
    first_path = Path(input_items[0][0]).expanduser()
    with zipfile.ZipFile(first_path, "r") as z: opf_rel = get_opf_path(z)
    opf_dir = str(PurePosixPath(opf_rel).parent)
    if opf_dir == ".": opf_dir = ""
    
    opf_root = build_base_opf(final_title, author)
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
                a_vol = ET.Element("a", {"href": vol_href})
                a_vol.text = alias if alias else f"Volume {idx+1}"
                vol_li.insert(0, a_vol) # 插在 ol 前面
                
                volume_nodes.append((vol_href, vol_li))

        # 4. 生成总 NAV (书 -> 卷 -> 章)
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
    if len(sys.argv) < 3:
        print("Usage: python3 merge_gemini.py <output_file.epub> <input1.epub> [input2.epub]...")
        sys.exit(1)

    output_path = sys.argv[1]
    input_paths = sys.argv[2:]

    # CLI 模式下，将文件名（不含扩展名）作为卷名，且不进行章节重命名（user_chaps=None）
    input_items = []
    for path in input_paths:
        p = Path(path)
        if not p.exists():
            print(f"Error: Input file not found: {path}", file=sys.stderr)
            sys.exit(1)
        # 结构: (path, alias, user_chaps)
        input_items.append((str(p), p.stem, None))

    try:
        print(f"Starting EPUB merge...")
        print(f"Output: {output_path}")
        print(f"Inputs: {[item[0] for item in input_items]}")
        
        # 标题和作者在 CLI 中不指定，传入 None
        merge_epubs(output_path, input_items, title=None, author=None)
        
        print("\nSuccessfully merged EPUBs.")
        print(f"Output file: {Path(output_path).resolve()}")

    except Exception as e:
        print(f"\nError during merge: {e}", file=sys.stderr)
        sys.exit(1)