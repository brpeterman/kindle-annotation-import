"""Shared factory functions for creating test data with sensible defaults."""

import io
import zipfile

from calibre_plugins.kindle_annotation_import.models import (
    Clipping,
    ClippingType,
    EpubDocument,
    PageAnchor,
)


def make_clipping(**overrides) -> Clipping:
    defaults = dict(
        book_title="Test Book",
        author="Test Author",
        clipping_type=ClippingType.HIGHLIGHT,
        page=42,
        location_start=100,
        location_end=150,
        timestamp=None,
        content="some highlighted text",
        raw_header="- Your Highlight on page 42 | Location 100-150 | Added on Monday, January 1, 2024 12:00:00 AM",
    )
    defaults.update(overrides)
    return Clipping(**defaults)


def make_epub(**overrides) -> EpubDocument:
    defaults = dict(
        title="Test Book",
        spine_files=["OEBPS/chapter1.xhtml"],
        page_anchors=[],
        file_texts={"OEBPS/chapter1.xhtml": "The full plain text of chapter one."},
        file_html={
            "OEBPS/chapter1.xhtml": "<html><body><p>The full plain text of chapter one.</p></body></html>"
        },
        toc_root=None,
    )
    defaults.update(overrides)
    return EpubDocument(**defaults)


def make_epub_zip(
    spine_files: dict[str, str],
    title: str = "Test Book",
    nav_toc: list[tuple[str, str]] | None = None,
    page_list: list[tuple[str, str, str]] | None = None,
    page_break_ids: dict[str, list[str]] | None = None,
) -> bytes:
    """Create a valid in-memory EPUB zip.

    Args:
        spine_files: {file_path: xhtml_body_content} — the body content for each spine file.
            File paths should be like "OEBPS/chapter1.xhtml".
        title: Book title for the OPF metadata.
        nav_toc: List of (title, href) for TOC entries, e.g. [("Chapter 1", "chapter1.xhtml")].
        page_list: List of (page_label, file_path, anchor_id) for nav page-list entries.
        page_break_ids: Dict of {file_path: [anchor_ids]} to inject epub:type="pagebreak" spans.

    Returns:
        bytes of a valid EPUB zip file.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # mimetype
        zf.writestr("mimetype", "application/epub+zip")

        # container.xml
        zf.writestr(
            "META-INF/container.xml",
            (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
                "<rootfiles>"
                '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                "</rootfiles>"
                "</container>"
            ),
        )

        # Build manifest items
        manifest_items = []
        spine_refs = []
        for i, file_path in enumerate(spine_files):
            item_id = f"ch{i}"
            # href is relative to OPF dir (OEBPS/)
            href = (
                file_path.replace("OEBPS/", "")
                if file_path.startswith("OEBPS/")
                else file_path
            )
            manifest_items.append(
                f'<item id="{item_id}" href="{href}" media-type="application/xhtml+xml"/>'
            )
            spine_refs.append(f'<itemref idref="{item_id}"/>')

        nav_manifest = ""
        if nav_toc is not None or page_list is not None:
            nav_manifest = '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'

        # content.opf
        opf = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f"<dc:title>{title}</dc:title>"
            "</metadata>"
            "<manifest>" + "".join(manifest_items) + nav_manifest + "</manifest>"
            "<spine>" + "".join(spine_refs) + "</spine>"
            "</package>"
        )
        zf.writestr("OEBPS/content.opf", opf)

        # Spine XHTML files
        for file_path, body_content in spine_files.items():
            pagebreak_html = ""
            if page_break_ids and file_path in page_break_ids:
                for aid in page_break_ids[file_path]:
                    pagebreak_html += f'<span id="{aid}" epub:type="pagebreak"></span>'

            xhtml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
                "<head><title>Test</title></head>"
                f"<body>{pagebreak_html}{body_content}</body>"
                "</html>"
            )
            zf.writestr(file_path, xhtml)

        # Nav document
        if nav_toc is not None or page_list is not None:
            toc_html = ""
            if nav_toc:
                toc_items = "".join(
                    f'<li><a href="{href}">{t}</a></li>' for t, href in nav_toc
                )
                toc_html = f'<nav epub:type="toc"><ol>{toc_items}</ol></nav>'

            page_list_html = ""
            if page_list:
                pl_items = []
                for label, fpath, anchor_id in page_list:
                    href = (
                        fpath.replace("OEBPS/", "")
                        if fpath.startswith("OEBPS/")
                        else fpath
                    )
                    pl_items.append(
                        f'<li><a href="{href}#{anchor_id}">{label}</a></li>'
                    )
                page_list_html = (
                    f'<nav epub:type="page-list"><ol>{"".join(pl_items)}</ol></nav>'
                )

            nav_xhtml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">'
                "<head><title>Nav</title></head>"
                f"<body>{toc_html}{page_list_html}</body>"
                "</html>"
            )
            zf.writestr("OEBPS/nav.xhtml", nav_xhtml)

    return buf.getvalue()
