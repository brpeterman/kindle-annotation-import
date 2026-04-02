"""Resolve toc_family_titles for a position within an EPUB.

Parses the EPUB's navigation document to build a table-of-contents tree,
then finds which TOC entry contains a given spine file + character offset.
Returns the breadcrumb trail of TOC titles from root to the matching entry.
"""

import io
import zipfile
from pathlib import PurePosixPath
from lxml import etree

NS_XHTML = "http://www.w3.org/1999/xhtml"
NS_EPUB = "http://www.idpf.org/2007/ops"
NS_OPF = "http://www.idpf.org/2007/opf"
NS_CONTAINER = "urn:oasis:names:tc:opendocument:xmlns:container"


class TocEntry:
    def __init__(self, title, file_path, fragment=None, parent=None):
        self.title = title
        self.file_path = file_path  # resolved full path within the EPUB
        self.fragment = fragment
        self.parent = parent
        self.children = []

    def add(self, title, file_path, fragment=None):
        child = TocEntry(title, file_path, fragment, parent=self)
        self.children.append(child)
        return child

    def family_titles(self):
        """Walk up from this entry to the root, collecting titles."""
        titles = []
        node = self
        while node is not None:
            if node.title:
                titles.append(node.title)
            node = node.parent
        titles.reverse()
        return titles


def resolve_toc_titles(epub_data, spine_file, char_offset=0):
    """Resolve toc_family_titles for a position in the EPUB.

    Args:
        epub_data: path string or bytes of the EPUB file
        spine_file: the spine file path (e.g., 'OEBPS/Text/Chapter_02.xhtml')
        char_offset: character offset within the extracted text of that file

    Returns:
        A list of TOC title strings, e.g., ['Part 1', 'Chapter 3'], or ['Unknown']
    """
    if isinstance(epub_data, (bytes, bytearray)):
        zf = zipfile.ZipFile(io.BytesIO(epub_data))
    else:
        zf = zipfile.ZipFile(epub_data)

    with zf:
        nav_path, nav_dir = _find_nav_path(zf)
        if not nav_path:
            return ["Unknown"]

        root = _parse_toc_tree(zf, nav_path, nav_dir)
        spine_files = _get_spine_order(zf)

    # Flatten the TOC tree into a sorted list of (spine_index, file_path, entry) tuples
    flat = []
    _flatten_toc(root, flat, spine_files)

    # Find the best matching entry for our position
    best = _find_best_match(flat, spine_file, spine_files)
    if best:
        return best.family_titles()
    return ["Unknown"]


def parse_toc_from_zip(zf: zipfile.ZipFile) -> "TocEntry | None":
    """Parse the TOC tree from an already-open EPUB zip.

    Returns the root TocEntry, or None if no nav document is found.
    """
    nav_path, nav_dir = _find_nav_path(zf)
    if not nav_path:
        return None
    return _parse_toc_tree(zf, nav_path, nav_dir)


def resolve_toc_titles_from_doc(epub, spine_file, char_offset=0):
    """Resolve TOC breadcrumbs using a pre-parsed EpubDocument.

    Args:
        epub: an EpubDocument with toc_root and spine_files populated
        spine_file: the spine file path
        char_offset: character offset (currently unused, reserved for future)

    Returns:
        A list of TOC title strings, or ['Unknown'].
    """
    if epub.toc_root is None:
        return ["Unknown"]
    flat = []
    _flatten_toc(epub.toc_root, flat, epub.spine_files)
    best = _find_best_match(flat, spine_file, epub.spine_files)
    if best:
        return best.family_titles()
    return ["Unknown"]


def _find_nav_path(zf):
    """Find the nav document path and its directory."""
    container = etree.fromstring(zf.read("META-INF/container.xml"))
    rootfile = container.find(f".//{{{NS_CONTAINER}}}rootfile")
    opf_path = rootfile.get("full-path")
    opf_dir = str(PurePosixPath(opf_path).parent)
    opf_tree = etree.fromstring(zf.read(opf_path))

    for item in opf_tree.findall(f".//{{{NS_OPF}}}item"):
        props = item.get("properties", "")
        if "nav" in props.split():
            href = item.get("href")
            nav_path = str(PurePosixPath(opf_dir) / href) if opf_dir != "." else href
            nav_dir = str(PurePosixPath(nav_path).parent)
            return nav_path, nav_dir
    return None, None


def _parse_toc_tree(zf, nav_path, nav_dir):
    """Parse the nav document's <nav epub:type='toc'> into a TocEntry tree."""
    nav_tree = etree.fromstring(zf.read(nav_path))
    root = TocEntry(None, None)

    for nav_el in nav_tree.iter(f"{{{NS_XHTML}}}nav"):
        if nav_el.get(f"{{{NS_EPUB}}}type") == "toc":
            _parse_toc_nav(nav_el, root, nav_dir)
            break

    return root


def _parse_toc_nav(element, parent_entry, nav_dir):
    """Recursively parse a <nav>/<ol>/<li> structure into TocEntry nodes."""
    for child in element:
        tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
        if tag == "ol":
            _parse_toc_nav(child, parent_entry, nav_dir)
        elif tag == "li":
            entry = None
            for sub in child:
                sub_tag = sub.tag.split("}")[-1] if "}" in sub.tag else sub.tag
                if sub_tag == "a" and entry is None:
                    href = sub.get("href", "")
                    title = "".join(sub.itertext()).strip()
                    file_part, _, fragment = href.partition("#")
                    full_path = (
                        str(PurePosixPath(nav_dir) / file_part) if file_part else None
                    )
                    entry = parent_entry.add(title, full_path, fragment or None)
                elif sub_tag == "ol" and entry is not None:
                    _parse_toc_nav(sub, entry, nav_dir)


def _get_spine_order(zf):
    """Get the ordered list of spine file paths."""
    container = etree.fromstring(zf.read("META-INF/container.xml"))
    rootfile = container.find(f".//{{{NS_CONTAINER}}}rootfile")
    opf_path = rootfile.get("full-path")
    opf_dir = str(PurePosixPath(opf_path).parent)
    opf_tree = etree.fromstring(zf.read(opf_path))

    manifest = {}
    for item in opf_tree.findall(f".//{{{NS_OPF}}}item"):
        manifest[item.get("id")] = item.get("href")

    spine = []
    for itemref in opf_tree.findall(f".//{{{NS_OPF}}}itemref"):
        href = manifest.get(itemref.get("idref"), "")
        full_path = str(PurePosixPath(opf_dir) / href) if opf_dir != "." else href
        spine.append(full_path)
    return spine


def _flatten_toc(entry, flat, spine_files):
    """Flatten a TocEntry tree into a list of (spine_index, entry) tuples."""
    for child in entry.children:
        if child.file_path and child.file_path in spine_files:
            spine_idx = spine_files.index(child.file_path)
            flat.append((spine_idx, child))
        _flatten_toc(child, flat, spine_files)


def _find_best_match(flat, target_file, spine_files):
    """Find the TOC entry that best matches the target spine file.

    Uses the last TOC entry whose spine file is <= the target file in spine order.
    """
    if not flat or target_file not in spine_files:
        return None

    target_idx = spine_files.index(target_file)
    best = None
    for spine_idx, entry in flat:
        if spine_idx <= target_idx:
            if best is None or spine_idx >= best[0]:
                best = (spine_idx, entry)

    return best[1] if best else None
