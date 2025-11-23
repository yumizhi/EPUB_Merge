import sys
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import List, Sequence, Union, Tuple, Dict, Optional
import xml.etree.ElementTree as ET
from urllib.parse import unquote


OPF_NS = "http://www.idpf.org/2007/opf"
DC_NS = "http://purl.org/dc/elements/1.1/"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
NSMAP = {"opf": OPF_NS, "dc": DC_NS}

EPUB_MIMETYPE = "application/epub+zip"
PathLike = Union[str, Path]

# 默认命名空间用 OPF，DC 单独注册
ET.register_namespace("", OPF_NS)
ET.register_namespace("dc", DC_NS)


def get_opf_path(zf: zipfile.ZipFile) -> str:
    """从 META-INF/container.xml 里找到 OPF 的路径。"""
    data = zf.read("META-INF/container.xml")
    root = ET.fromstring(data)
    rootfile = root.find(f".//{{{CONTAINER_NS}}}rootfile")
    if rootfile is None:
        raise RuntimeError("No <rootfile> in container.xml")
    return rootfile.attrib["full-path"]


def build_base_opf(lang: str = "zh") -> ET.Element:
    """构造一个最小可用的 OPF 3.0 骨架。"""
    pkg = ET.Element(f"{{{OPF_NS}}}package", {
        "version": "3.0",
        "unique-identifier": "BookId",
    })
    metadata = ET.SubElement(pkg, f"{{{OPF_NS}}}metadata")
    identifier = ET.SubElement(metadata, f"{{{DC_NS}}}identifier", {"id": "BookId"})
    identifier.text = "urn:uuid:" + str(uuid.uuid4())
    title = ET.SubElement(metadata, f"{{{DC_NS}}}title")
    title.text = "Merged Book"
    language = ET.SubElement(metadata, f"{{{DC_NS}}}language")
    language.text = lang
    ET.SubElement(pkg, f"{{{OPF_NS}}}manifest")
    ET.SubElement(pkg, f"{{{OPF_NS}}}spine")
    return pkg


def _ensure_input_paths(input_paths: Sequence[PathLike]) -> List[Path]:
    resolved: List[Path] = []
    for raw in input_paths:
        path = Path(raw).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Input EPUB not found: {path}")
        resolved.append(path)
    return resolved


def _copy_manifest_items(
    *,
    book_manifest: ET.Element,
    manifest: ET.Element,
    in_zip: zipfile.ZipFile,
    out_zip: zipfile.ZipFile,
    src_base_dir: str,
    dest_base_dir: str,
    prefix: str,
    id_prefix: str,
    written_files: set,
    suppress_nav: bool,
) -> Tuple[int, Dict[str, str], Dict[str, str], Dict[str, str]]:
    """
    Copy manifest resources from one volume into the merged EPUB.

    - src_base_dir: 该卷 OPF 所在目录，例如 "OEBPS"
    - dest_base_dir: 合并后 OPF 所在目录（所有资源都写在这里下面）
    - prefix: 对于第 2 卷及以后使用 v1/、v2/… 这样的前缀
    - id_prefix: 对应 id 上的前缀，避免 id 冲突
    - suppress_nav: 是否去掉 properties="nav"

    返回:
        total      : 复制的 item 数量
        id_map     : old_id -> new_id
        id_to_href : old_id -> new_href (相对于最终 OPF)
        href_map   : old_href (相对于该卷 OPF) -> new_href
    """
    id_map: Dict[str, str] = {}
    id_to_href: Dict[str, str] = {}
    href_map: Dict[str, str] = {}
    total = 0

    for item in book_manifest.findall("opf:item", NSMAP):
        old_id = item.attrib["id"]
        href = item.attrib["href"]
        media_type = item.attrib.get("media-type", "")

        # 新的 id / href
        new_id = old_id if not id_prefix else f"{id_prefix}{old_id}"
        new_href = href if not prefix else f"{prefix}{href}"

        # 复制属性，并且根据 suppress_nav 处理 properties
        attrs = dict(item.attrib)
        attrs["id"] = new_id
        attrs["href"] = new_href

        if suppress_nav and "properties" in attrs:
            props = attrs["properties"].split()
            props = [p for p in props if p != "nav"]
            if props:
                attrs["properties"] = " ".join(props)
            else:
                attrs.pop("properties", None)

        # 源路径：相对于该卷 OPF 所在目录
        src_rel = href
        src_path = f"{src_base_dir}/{src_rel}" if src_base_dir else src_rel

        # 目标路径：相对于合并后 OPF 所在目录
        dst_rel = new_href
        dst_path = f"{dest_base_dir}/{dst_rel}" if dest_base_dir else dst_rel

        if dst_path not in written_files:
            # 这里做「多方案尝试」：原路径 / URL 解码路径 / 空格转 %20 等
            candidates = [src_path]
            # 1）URL decode 一遍（处理 Chapter%201.html -> Chapter 1.html）
            decoded = unquote(src_path)
            if decoded not in candidates:
                candidates.append(decoded)
            # 2）把空格编码成 %20（处理 Chapter 1.html -> Chapter%201.html）
            if " " in src_path:
                encoded_spaces = src_path.replace(" ", "%20")
                if encoded_spaces not in candidates:
                    candidates.append(encoded_spaces)

            last_err: Optional[KeyError] = None
            data = None
            for cand in candidates:
                try:
                    data = in_zip.read(cand)
                    src_path = cand  # 成功读取的真实路径
                    last_err = None
                    break
                except KeyError as exc:
                    last_err = exc
                    continue

            if last_err is not None or data is None:
                # 所有候选路径都失败，才真正报错
                raise RuntimeError(
                    f"{in_zip.filename}: cannot find resource {src_path} "
                    f"for manifest item {old_id} ({media_type})"
                ) from last_err

            out_zip.writestr(dst_path, data)
            written_files.add(dst_path)

        # 登记到合并 OPF 的 manifest
        ET.SubElement(manifest, f"{{{OPF_NS}}}item", attrs)

        id_map[old_id] = new_id
        id_to_href[old_id] = new_href

        # href_map：为了目录重写，既登记原 href，也登记几种常见变体
        # 原值（相对于该卷 OPF）
        href_map[href] = new_href
        # URL 解码（处理 manifest 用 Text/Chapter%201.html，nav 用 Text/Chapter 1.html）
        decoded_href = unquote(href)
        if decoded_href != href:
            href_map[decoded_href] = new_href
        # 空格编码版本
        if " " in href:
            encoded_spaces_href = href.replace(" ", "%20")
            if encoded_spaces_href != href:
                href_map[encoded_spaces_href] = new_href

        total += 1

    return total, id_map, id_to_href, href_map


def _append_spine_entries(
    *, book_spine: ET.Element, spine: ET.Element, id_map: Dict[str, str]
) -> None:
    """根据 id_map 将每卷的 spine itemref 追加到总 spine 中。"""
    for itemref in book_spine.findall("opf:itemref", NSMAP):
        old_idref = itemref.attrib.get("idref")
        if not old_idref:
            continue
        new_idref = id_map.get(old_idref)
        if not new_idref:
            continue
        spine.append(ET.Element(f"{{{OPF_NS}}}itemref", {"idref": new_idref}))


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _build_volume_nav_from_nav_xhtml(
    *,
    in_zip: zipfile.ZipFile,
    src_base_dir: str,
    nav_href_rel: str,
    href_map: Dict[str, str],
    vol_title: str,
    vol_index: int,
) -> Optional[ET.Element]:
    """优先从 EPUB3 的 nav.xhtml 中构造该卷的 TOC <li>。"""
    nav_src_path = f"{src_base_dir}/{nav_href_rel}" if src_base_dir else nav_href_rel
    try:
        data = in_zip.read(nav_src_path)
    except KeyError:
        return None

    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None

    # 找 <nav epub:type="toc">，忽略标签的命名空间
    toc_nav = None
    for nav in root.iter():
        if _local_name(nav.tag) != "nav":
            continue
        t = (
            nav.attrib.get("epub:type")
            or nav.attrib.get("{http://www.idpf.org/2007/ops}type")
            or nav.attrib.get("type")
        )
        if t and "toc" in t:
            toc_nav = nav
            break
    if toc_nav is None:
        # 退化：取第一个 <nav>
        for nav in root.iter():
            if _local_name(nav.tag) == "nav":
                toc_nav = nav
                break
        if toc_nav is None:
            return None

    # 取 nav 下面第一个 <ol>
    ol = None
    for child in toc_nav:
        if _local_name(child.tag) == "ol":
            ol = child
            break
    if ol is None:
        return None

    import copy

    ol_copy = copy.deepcopy(ol)

    nav_dir_rel = PurePosixPath(nav_href_rel).parent.as_posix()
    nav_dir_rel = "" if nav_dir_rel == "." else nav_dir_rel

    # 重写每个 <a href="...">，使其指向合并后的新路径
    for a in ol_copy.iter():
        if _local_name(a.tag) != "a":
            continue
        href = a.attrib.get("href")
        if not href:
            continue
        path, sep, frag = href.partition("#")
        if path in ("", "#"):
            continue
        if nav_dir_rel:
            full_rel = str(PurePosixPath(nav_dir_rel) / path)
        else:
            full_rel = path
        new_doc_href = href_map.get(full_rel)
        if not new_doc_href:
            continue
        new_href = new_doc_href + (sep + frag if sep else "")
        a.set("href", new_href)

    li_vol = ET.Element("li")
    span = ET.SubElement(li_vol, "span")
    span.text = vol_title or f"第{vol_index + 1}卷"
    li_vol.append(ol_copy)
    return li_vol


def _build_ol_from_ncx(
    *,
    in_zip: zipfile.ZipFile,
    src_base_dir: str,
    ncx_href_rel: str,
    href_map: Dict[str, str],
) -> Optional[ET.Element]:
    """从 EPUB2 的 toc.ncx 中解析出 <ol> 结构。"""
    ncx_src_path = f"{src_base_dir}/{ncx_href_rel}" if src_base_dir else ncx_href_rel
    try:
        data = in_zip.read(ncx_src_path)
    except KeyError:
        return None

    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None

    nav_map = None
    for el in root.iter():
        if _local_name(el.tag) == "navMap":
            nav_map = el
            break
    if nav_map is None:
        return None

    ncx_dir_rel = PurePosixPath(ncx_href_rel).parent.as_posix()
    ncx_dir_rel = "" if ncx_dir_rel == "." else ncx_dir_rel

    def build_li(np: ET.Element) -> ET.Element:
        label_text = ""
        for child in np:
            if _local_name(child.tag) == "navLabel":
                for t in child:
                    if _local_name(t.tag) == "text" and t.text:
                        label_text = t.text.strip()
                        break
            if label_text:
                break

        src_attr = ""
        for child in np:
            if _local_name(child.tag) == "content":
                src_attr = child.attrib.get("src", "")
                break

        path, sep, frag = src_attr.partition("#")
        if ncx_dir_rel and path:
            full_rel = str(PurePosixPath(ncx_dir_rel) / path)
        else:
            full_rel = path
        new_doc_href = href_map.get(full_rel)
        if new_doc_href:
            href = new_doc_href + (sep + frag if sep else "")
        else:
            href = src_attr

        li = ET.Element("li")
        a = ET.SubElement(li, "a")
        a.set("href", href)
        a.text = label_text or href

        children = [c for c in np if _local_name(c.tag) == "navPoint"]
        if children:
            ol_child = ET.SubElement(li, "ol")
            for c in children:
                ol_child.append(build_li(c))
        return li

    ol_root = ET.Element("ol")
    for np in nav_map:
        if _local_name(np.tag) == "navPoint":
            ol_root.append(build_li(np))
    return ol_root


def _build_volume_nav_li_fallback(
    *,
    book_spine: ET.Element,
    id_to_href: Dict[str, str],
    vol_title: str,
    vol_index: int,
) -> ET.Element:
    """如果该卷没有 nav / ncx，则从 spine 顺序构造一个简单 TOC。"""
    li_vol = ET.Element("li")
    span = ET.SubElement(li_vol, "span")
    span.text = vol_title or f"第{vol_index + 1}卷"

    ol = ET.SubElement(li_vol, "ol")
    chapter_idx = 1
    for itemref in book_spine.findall("opf:itemref", NSMAP):
        old_idref = itemref.attrib.get("idref")
        if not old_idref:
            continue
        href = id_to_href.get(old_idref)
        if not href:
            continue
        li = ET.SubElement(ol, "li")
        a = ET.SubElement(li, "a")
        a.set("href", href)
        a.text = f"章节 {chapter_idx}"
        chapter_idx += 1
    return li_vol


def _extract_volume_title(book_root: ET.Element, default_title: str, vol_index: int) -> str:
    """生成形如“第1卷 xxx”的卷标题。"""
    base_label = f"第{vol_index + 1}卷"
    metadata = book_root.find("opf:metadata", NSMAP)
    if metadata is not None:
        title_el = metadata.find("dc:title", NSMAP)
        if title_el is None:
            title_el = metadata.find("title")
        if title_el is not None and title_el.text:
            t = title_el.text.strip()
            if t and t != base_label:
                return f"{base_label} {t}"
    return base_label


def _build_merged_nav_html(volume_lis: Sequence[ET.Element]) -> bytes:
    """构造全书统一的 nav-merged.xhtml。"""
    html = ET.Element("html", {
        "lang": "zh",
        "xmlns:epub": "http://www.idpf.org/2007/ops",
    })
    head = ET.SubElement(html, "head")
    title_el = ET.SubElement(head, "title")
    title_el.text = "目录"
    body = ET.SubElement(html, "body")
    nav = ET.SubElement(body, "nav", {
        "epub:type": "toc",
        "id": "toc",
    })
    h1 = ET.SubElement(nav, "h1")
    h1.text = "目录"
    ol_root = ET.SubElement(nav, "ol")
    for li in volume_lis:
        ol_root.append(li)
    return ET.tostring(html, encoding="utf-8", xml_declaration=True)


def merge_epubs(output_path: PathLike, input_paths: Sequence[PathLike]) -> int:
    """Merge multiple EPUB volumes into one with a consolidated volume-structured TOC."""
    if not input_paths:
        raise SystemExit("No input EPUB files specified.")

    resolved_output = Path(output_path).expanduser()
    resolved_inputs = _ensure_input_paths(input_paths)
    if resolved_output.parent:
        resolved_output.parent.mkdir(parents=True, exist_ok=True)

    # 沿用第 1 卷的 OPF 路径和目录结构
    with zipfile.ZipFile(resolved_inputs[0], "r") as first_zip:
        primary_opf_rel = PurePosixPath(get_opf_path(first_zip))
    opf_dir = primary_opf_rel.parent.as_posix()
    opf_dir = "" if opf_dir == "." else opf_dir

    opf_root = build_base_opf()
    # 用输出文件名（不含扩展名）作为总书名
    metadata = opf_root.find("opf:metadata", NSMAP)
    if metadata is not None:
        title_el = metadata.find("dc:title", NSMAP)
        if title_el is None:
            title_el = metadata.find("title")
        if title_el is not None:
            title_el.text = resolved_output.stem


    manifest = opf_root.find("opf:manifest", NSMAP)
    spine = opf_root.find("opf:spine", NSMAP)
    if manifest is None or spine is None:
        raise RuntimeError("Generated OPF missing manifest or spine.")

    volume_nav_items: List[ET.Element] = []

    with zipfile.ZipFile(resolved_output, "w") as out_zip:
        # mimetype 必须第一个写入，且不压缩
        out_zip.writestr("mimetype", EPUB_MIMETYPE, compress_type=zipfile.ZIP_STORED)

        # container.xml 指向第 1 卷原来的 OPF 路径
        container_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="{primary_opf_rel.as_posix()}"
              media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""
        out_zip.writestr("META-INF/container.xml", container_xml)

        written_files: set = set()
        total_items = 0

        for vol_idx, in_path in enumerate(resolved_inputs):
            # 第 1 卷不加前缀，后续卷用 v1/、v2/… 区分资源
            prefix = "" if vol_idx == 0 else f"v{vol_idx}/"
            id_prefix = "" if vol_idx == 0 else f"v{vol_idx}_"
            suppress_nav = True  # 所有卷都去掉 nav 属性，统一用 nav-merged

            with zipfile.ZipFile(in_path, "r") as in_zip:
                opf_path = get_opf_path(in_zip)
                opf_data = in_zip.read(opf_path)
                book_root = ET.fromstring(opf_data)

                book_manifest = book_root.find("opf:manifest", NSMAP)
                book_spine = book_root.find("opf:spine", NSMAP)
                if book_manifest is None or book_spine is None:
                    raise RuntimeError(f"{in_path}: OPF missing manifest or spine.")

                src_base_dir = PurePosixPath(opf_path).parent.as_posix()
                src_base_dir = "" if src_base_dir == "." else src_base_dir

                nav_href_rel: Optional[str] = None
                ncx_href_rel: Optional[str] = None

                # 先尝试 EPUB3: manifest 中 properties="nav" 的 item
                for item in book_manifest.findall("opf:item", NSMAP):
                    props = item.attrib.get("properties", "")
                    if "nav" in props.split():
                        nav_href_rel = item.attrib.get("href")
                        break

                # 如果没有 nav，再尝试 EPUB2: spine 的 toc="ncx-id"
                if nav_href_rel is None:
                    toc_id = book_spine.attrib.get("toc")
                    if toc_id:
                        for item in book_manifest.findall("opf:item", NSMAP):
                            if item.attrib.get("id") == toc_id:
                                ncx_href_rel = item.attrib.get("href")
                                break

                copied, id_map, id_to_href, href_map = _copy_manifest_items(
                    book_manifest=book_manifest,
                    manifest=manifest,
                    in_zip=in_zip,
                    out_zip=out_zip,
                    src_base_dir=src_base_dir,
                    dest_base_dir=opf_dir,
                    prefix=prefix,
                    id_prefix=id_prefix,
                    written_files=written_files,
                    suppress_nav=suppress_nav,
                )
                total_items += copied

                _append_spine_entries(book_spine=book_spine, spine=spine, id_map=id_map)

                # 构造该卷的卷级 TOC 节点
                default_vol_title = f"第{vol_idx + 1}卷"
                vol_title = _extract_volume_title(book_root, default_vol_title, vol_idx)

                li_vol: Optional[ET.Element] = None
                if nav_href_rel:
                    li_vol = _build_volume_nav_from_nav_xhtml(
                        in_zip=in_zip,
                        src_base_dir=src_base_dir,
                        nav_href_rel=nav_href_rel,
                        href_map=href_map,
                        vol_title=vol_title,
                        vol_index=vol_idx,
                    )
                if li_vol is None and ncx_href_rel:
                    ol_from_ncx = _build_ol_from_ncx(
                        in_zip=in_zip,
                        src_base_dir=src_base_dir,
                        ncx_href_rel=ncx_href_rel,
                        href_map=href_map,
                    )
                    if ol_from_ncx is not None:
                        li_vol = ET.Element("li")
                        span = ET.SubElement(li_vol, "span")
                        span.text = vol_title
                        li_vol.append(ol_from_ncx)
                if li_vol is None:
                    li_vol = _build_volume_nav_li_fallback(
                        book_spine=book_spine,
                        id_to_href=id_to_href,
                        vol_title=vol_title,
                        vol_index=vol_idx,
                    )

                volume_nav_items.append(li_vol)

        # 构造并写入全局 nav-merged.xhtml
        nav_bytes = _build_merged_nav_html(volume_nav_items)
        nav_href = "nav-merged.xhtml"
        nav_item_attrs = {
            "id": "nav",
            "href": nav_href,
            "media-type": "application/xhtml+xml",
            "properties": "nav",
        }
        ET.SubElement(manifest, f"{{{OPF_NS}}}item", nav_item_attrs)

        nav_dst_path = f"{opf_dir}/{nav_href}" if opf_dir else nav_href
        out_zip.writestr(nav_dst_path, nav_bytes)

        # 写出合并后的 OPF（覆盖第 1 卷原来的 OPF）
        opf_bytes = ET.tostring(opf_root, encoding="utf-8", xml_declaration=True)
        out_zip.writestr(primary_opf_rel.as_posix(), opf_bytes)

    return total_items


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) < 2:
        print("Usage: python merge_epub.py output.epub vol01.epub vol02.epub ...")
        raise SystemExit(1)
    output = argv[0]
    inputs = argv[1:]
    total = merge_epubs(output, inputs)
    print(f"Merged {len(inputs)} volumes, {total} manifest items.")


if __name__ == "__main__":
    main()
