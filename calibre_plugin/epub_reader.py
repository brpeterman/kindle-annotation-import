import io
import zipfile
from pathlib import PurePosixPath
from lxml import etree

from calibre_plugins.kindle_annotation_import.models import EpubDocument, PageAnchor
from calibre_plugins.kindle_annotation_import.toc_resolver import parse_toc_from_zip

NS_CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"
NS_OPF = "http://www.idpf.org/2007/opf"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_XHTML = "http://www.w3.org/1999/xhtml"
NS_EPUB = "http://www.idpf.org/2007/ops"

_ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def _roman_to_int(s: str) -> int | None:
    """Convert a Roman numeral string to int, or return None if invalid."""
    s = s.strip().upper()
    if not s or not all(c in _ROMAN_VALUES for c in s):
        return None
    total = 0
    for i, c in enumerate(s):
        if i + 1 < len(s) and _ROMAN_VALUES[c] < _ROMAN_VALUES[s[i + 1]]:
            total -= _ROMAN_VALUES[c]
        else:
            total += _ROMAN_VALUES[c]
    if total > 500:
        return None
    return total


def _parse_page_number(label: str) -> int | None:
    """Parse a page label as an integer, trying decimal then Roman numerals."""
    try:
        return int(label)
    except ValueError:
        return _roman_to_int(label)


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

            nav_labels = page_anchors_from_nav.get(file_path, {})
            nav_ids = set(nav_labels.keys()) if nav_labels else None
            text, anchors = _extract_text_with_anchors(xhtml_bytes, nav_ids)
            file_texts[file_path] = text

            for anchor_id, char_offset in anchors.items():
                # Prefer the nav page-list label (authoritative display text)
                # over the heuristic of stripping "page_" from the element ID.
                if anchor_id in nav_labels:
                    label = nav_labels[anchor_id]
                elif anchor_id.startswith("page_"):
                    label = anchor_id.replace("page_", "")
                else:
                    label = anchor_id
                page_num = _parse_page_number(label)
                page_anchors.append(
                    PageAnchor(
                        page_label=label,
                        page_number=page_num,
                        file_path=file_path,
                        element_id=anchor_id,
                        char_offset=char_offset,
                    )
                )

        toc_root = parse_toc_from_zip(zf)

        return EpubDocument(
            title=title,
            spine_files=spine_files,
            page_anchors=page_anchors,
            file_texts=file_texts,
            file_html=file_html,
            toc_root=toc_root,
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
) -> dict[str, dict[str, str]]:
    """Parse nav page-list. Returns {file_path: {anchor_id: page_label}}."""
    nav_tree = etree.fromstring(zf.read(nav_path))
    result: dict[str, dict[str, str]] = {}
    for nav_el in nav_tree.iter(f"{{{NS_XHTML}}}nav"):
        if nav_el.get(f"{{{NS_EPUB}}}type") == "page-list":
            for a in nav_el.iter(f"{{{NS_XHTML}}}a"):
                href = a.get("href", "")
                page_label = "".join(a.itertext()).strip()
                if "#" in href:
                    file_part, anchor_id = href.rsplit("#", 1)
                    nav_dir = str(PurePosixPath(nav_path).parent)
                    full_path = str(PurePosixPath(nav_dir) / file_part)
                    result.setdefault(full_path, {})[anchor_id] = page_label
    return result


def _extract_text_with_anchors(
    xhtml_bytes: bytes,
    nav_anchor_ids: set[str] | None = None,
) -> tuple[str, dict[str, int]]:
    """Extract plain text and anchor positions from XHTML content.

    Records positions for epub:type="pagebreak" elements and, optionally,
    any elements whose id is in nav_anchor_ids (from the nav page-list).
    """
    tree = etree.fromstring(xhtml_bytes)
    text_parts: list[str] = []
    anchor_positions: dict[str, int] = {}
    current_offset = 0

    for event, element in etree.iterwalk(tree, events=("start", "end")):
        if event == "start":
            epub_type = element.get(f"{{{NS_EPUB}}}type", "")
            element_id = element.get("id", "")
            if "pagebreak" in epub_type and element_id:
                anchor_positions[element_id] = current_offset
            elif nav_anchor_ids and element_id in nav_anchor_ids:
                anchor_positions[element_id] = current_offset
            if element.text:
                text_parts.append(element.text)
                current_offset += len(element.text)
        elif event == "end":
            if element.tail:
                text_parts.append(element.tail)
                current_offset += len(element.tail)

    return "".join(text_parts), anchor_positions
