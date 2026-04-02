"""Tests for calibre_plugin/toc_resolver.py."""

from calibre_plugins.kindle_annotation_import.toc_resolver import (
    TocEntry,
    parse_toc_from_zip,
    resolve_toc_titles_from_doc,
)
from factories import make_epub, make_epub_zip
import io
import zipfile


def test_family_titles():
    root = TocEntry(None, None)
    part = root.add("Part 1", "part1.xhtml")
    chapter = part.add("Chapter 3", "ch3.xhtml")
    assert chapter.family_titles() == ["Part 1", "Chapter 3"]


def test_family_titles_single():
    root = TocEntry(None, None)
    ch = root.add("Chapter 1", "ch1.xhtml")
    assert ch.family_titles() == ["Chapter 1"]


def test_add_creates_child():
    root = TocEntry(None, None)
    child = root.add("Child", "child.xhtml")
    assert child.parent is root
    assert child in root.children
    assert child.title == "Child"


def test_parse_toc_from_zip():
    epub_bytes = make_epub_zip(
        spine_files={"OEBPS/ch1.xhtml": "<p>Content</p>"},
        nav_toc=[
            ("Chapter 1", "ch1.xhtml"),
        ],
    )
    with zipfile.ZipFile(io.BytesIO(epub_bytes)) as zf:
        root = parse_toc_from_zip(zf)
    assert root is not None
    assert len(root.children) == 1
    assert root.children[0].title == "Chapter 1"


def test_parse_toc_no_nav():
    epub_bytes = make_epub_zip(
        spine_files={"OEBPS/ch1.xhtml": "<p>Content</p>"},
    )
    with zipfile.ZipFile(io.BytesIO(epub_bytes)) as zf:
        root = parse_toc_from_zip(zf)
    assert root is None


def test_resolve_toc_titles_from_doc():
    root = TocEntry(None, None)
    root.add("Part 1", "OEBPS/ch1.xhtml")
    root.add("Part 2", "OEBPS/ch2.xhtml")

    epub = make_epub(
        spine_files=["OEBPS/ch1.xhtml", "OEBPS/ch2.xhtml"],
        file_texts={"OEBPS/ch1.xhtml": "text", "OEBPS/ch2.xhtml": "text"},
        file_html={"OEBPS/ch1.xhtml": "", "OEBPS/ch2.xhtml": ""},
        toc_root=root,
    )

    titles = resolve_toc_titles_from_doc(epub, "OEBPS/ch2.xhtml")
    assert titles == ["Part 2"]


def test_resolve_before_first_toc_entry():
    root = TocEntry(None, None)
    root.add("Chapter 2", "OEBPS/ch2.xhtml")

    epub = make_epub(
        spine_files=["OEBPS/ch1.xhtml", "OEBPS/ch2.xhtml"],
        file_texts={"OEBPS/ch1.xhtml": "text", "OEBPS/ch2.xhtml": "text"},
        file_html={"OEBPS/ch1.xhtml": "", "OEBPS/ch2.xhtml": ""},
        toc_root=root,
    )

    titles = resolve_toc_titles_from_doc(epub, "OEBPS/ch1.xhtml")
    assert titles == ["Unknown"]


def test_resolve_no_toc_root():
    epub = make_epub(toc_root=None)
    titles = resolve_toc_titles_from_doc(epub, "OEBPS/chapter1.xhtml")
    assert titles == ["Unknown"]


def test_resolve_file_not_in_spine():
    root = TocEntry(None, None)
    root.add("Chapter 1", "OEBPS/ch1.xhtml")

    epub = make_epub(
        spine_files=["OEBPS/ch1.xhtml"],
        file_texts={"OEBPS/ch1.xhtml": "text"},
        file_html={"OEBPS/ch1.xhtml": ""},
        toc_root=root,
    )

    titles = resolve_toc_titles_from_doc(epub, "OEBPS/not_in_spine.xhtml")
    assert titles == ["Unknown"]
