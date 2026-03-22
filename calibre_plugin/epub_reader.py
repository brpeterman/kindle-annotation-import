import io
import zipfile
from pathlib import PurePosixPath
from lxml import etree

from calibre_plugins.kindle_annotation_import.models import EpubDocument, PageAnchor

NS_CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"
NS_OPF = "http://www.idpf.org/2007/opf"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_XHTML = "http://www.w3.org/1999/xhtml"
NS_EPUB = "http://www.idpf.org/2007/ops"


def read_epub(path_or_bytes) -> EpubDocument:
    if isinstance(path_or_bytes, (bytes, bytearray)):
        zf = zipfile.ZipFile(io.BytesIO(path_or_bytes))
    else:
        zf = zipfile.ZipFile(path_or_bytes)

    with zf:
        opf_path = _find_opf(zf)
        opf_dir = str(PurePosixPath(opf_path).parent)

        opf_tree = etree.fromstring(zf.read(opf_path))
        title = _get_title(opf_tree)
        spine_files = _get_spine(opf_tree, opf_dir)

        nav_path = _find_nav(opf_tree, opf_dir)
        page_anchors_from_nav = {}
        if nav_path:
            page_anchors_from_nav = _parse_page_list(zf, nav_path, opf_dir)

        file_texts = {}
        file_html = {}
        page_anchors = []

        for file_path in spine_files:
            xhtml_bytes = zf.read(file_path)
            file_html[file_path] = xhtml_bytes.decode("utf-8")
            text, anchors = _extract_text_with_anchors(xhtml_bytes)
            file_texts[file_path] = text
            for anchor_id, char_offset in anchors.items():
                label = (
                    anchor_id.replace("page_", "")
                    if anchor_id.startswith("page_")
                    else anchor_id
                )
                try:
                    page_num = int(label)
                except ValueError:
                    page_num = None
                page_anchors.append(
                    PageAnchor(
                        page_label=label,
                        page_number=page_num,
                        file_path=file_path,
                        element_id=anchor_id,
                        char_offset=char_offset,
                    )
                )

        return EpubDocument(
            title=title,
            spine_files=spine_files,
            page_anchors=page_anchors,
            file_texts=file_texts,
            file_html=file_html,
        )


def _find_opf(zf: zipfile.ZipFile) -> str:
    container = etree.fromstring(zf.read("META-INF/container.xml"))
    rootfile = container.find(f".//{{{NS_CONTAINER}}}rootfile")
    return rootfile.get("full-path")


def _get_title(opf_tree: etree._Element) -> str:
    title_el = opf_tree.find(f".//{{{NS_DC}}}title")
    return title_el.text if title_el is not None and title_el.text else "Unknown"


def _get_spine(opf_tree: etree._Element, opf_dir: str) -> list[str]:
    manifest = {}
    for item in opf_tree.findall(f".//{{{NS_OPF}}}item"):
        manifest[item.get("id")] = item.get("href")

    spine = []
    for itemref in opf_tree.findall(f".//{{{NS_OPF}}}itemref"):
        idref = itemref.get("idref")
        href = manifest.get(idref, "")
        full_path = str(PurePosixPath(opf_dir) / href) if opf_dir != "." else href
        spine.append(full_path)
    return spine


def _find_nav(opf_tree: etree._Element, opf_dir: str) -> str | None:
    for item in opf_tree.findall(f".//{{{NS_OPF}}}item"):
        props = item.get("properties", "")
        if "nav" in props.split():
            href = item.get("href")
            return str(PurePosixPath(opf_dir) / href) if opf_dir != "." else href
    return None


def _parse_page_list(
    zf: zipfile.ZipFile, nav_path: str, opf_dir: str
) -> dict[str, str]:
    nav_tree = etree.fromstring(zf.read(nav_path))
    result = {}
    for nav_el in nav_tree.iter(f"{{{NS_XHTML}}}nav"):
        if nav_el.get(f"{{{NS_EPUB}}}type") == "page-list":
            for a in nav_el.iter(f"{{{NS_XHTML}}}a"):
                href = a.get("href", "")
                if "#" in href:
                    file_part, anchor_id = href.rsplit("#", 1)
                    nav_dir = str(PurePosixPath(nav_path).parent)
                    full_path = str(PurePosixPath(nav_dir) / file_part)
                    result[anchor_id] = full_path
    return result


def _extract_text_with_anchors(xhtml_bytes: bytes) -> tuple[str, dict[str, int]]:
    """Extract plain text and pagebreak anchor positions from XHTML content."""
    tree = etree.fromstring(xhtml_bytes)
    text_parts: list[str] = []
    anchor_positions: dict[str, int] = {}
    current_offset = 0

    for event, element in etree.iterwalk(tree, events=("start", "end")):
        if event == "start":
            epub_type = element.get(f"{{{NS_EPUB}}}type", "")
            if "pagebreak" in epub_type:
                anchor_id = element.get("id", "")
                if anchor_id:
                    anchor_positions[anchor_id] = current_offset
            if element.text:
                text_parts.append(element.text)
                current_offset += len(element.text)
        elif event == "end":
            if element.tail:
                text_parts.append(element.tail)
                current_offset += len(element.tail)

    return "".join(text_parts), anchor_positions
