"""Tests for calibre_plugin/epub_reader.py."""

from calibre_plugins.kindle_annotation_import.epub_reader import (
    read_epub,
    _roman_to_int,
    _parse_page_number,
)
from factories import make_epub_zip


def test_basic_epub_read():
    epub_bytes = make_epub_zip(
        spine_files={"OEBPS/chapter1.xhtml": "<p>Chapter one text.</p>"},
        title="My Test Book",
    )
    doc = read_epub(epub_bytes)
    assert doc.title == "My Test Book"
    assert doc.spine_files == ["OEBPS/chapter1.xhtml"]
    assert "Chapter one text." in doc.file_texts["OEBPS/chapter1.xhtml"]
    assert "<p>Chapter one text.</p>" in doc.file_html["OEBPS/chapter1.xhtml"]


def test_spine_order():
    epub_bytes = make_epub_zip(
        spine_files={
            "OEBPS/ch1.xhtml": "<p>One</p>",
            "OEBPS/ch2.xhtml": "<p>Two</p>",
            "OEBPS/ch3.xhtml": "<p>Three</p>",
        },
    )
    doc = read_epub(epub_bytes)
    assert doc.spine_files == ["OEBPS/ch1.xhtml", "OEBPS/ch2.xhtml", "OEBPS/ch3.xhtml"]


def test_inline_page_anchors():
    epub_bytes = make_epub_zip(
        spine_files={"OEBPS/ch1.xhtml": "<p>Before page break.</p>"},
        page_break_ids={"OEBPS/ch1.xhtml": ["page_42"]},
    )
    doc = read_epub(epub_bytes)
    anchors = [a for a in doc.page_anchors if a.page_number == 42]
    assert len(anchors) == 1
    assert anchors[0].element_id == "page_42"
    assert anchors[0].file_path == "OEBPS/ch1.xhtml"


def test_nav_page_list_anchors():
    epub_bytes = make_epub_zip(
        spine_files={
            "OEBPS/ch1.xhtml": '<p><span id="pg10"></span>Text on page 10.</p>'
        },
        page_list=[("10", "OEBPS/ch1.xhtml", "pg10")],
        nav_toc=[("Chapter 1", "ch1.xhtml")],
    )
    doc = read_epub(epub_bytes)
    anchors = [a for a in doc.page_anchors if a.page_label == "10"]
    assert len(anchors) == 1
    assert anchors[0].page_number == 10


def test_roman_numeral_page():
    assert _roman_to_int("iv") == 4
    assert _roman_to_int("XIV") == 14
    assert _roman_to_int("XLII") == 42
    assert _roman_to_int("") is None
    assert _roman_to_int("not_roman") is None


def test_roman_numeral_cap():
    # Values > 500 are rejected
    assert _roman_to_int("DI") is None  # 501


def test_parse_page_number():
    assert _parse_page_number("42") == 42
    assert _parse_page_number("iv") == 4
    assert _parse_page_number("not_a_num") is None


def test_text_extraction():
    epub_bytes = make_epub_zip(
        spine_files={"OEBPS/ch1.xhtml": "<p>Hello</p><p>World</p>"},
    )
    doc = read_epub(epub_bytes)
    text = doc.file_texts["OEBPS/ch1.xhtml"]
    assert "Hello" in text
    assert "World" in text


def test_toc_parsed():
    epub_bytes = make_epub_zip(
        spine_files={"OEBPS/ch1.xhtml": "<p>Content</p>"},
        nav_toc=[("Chapter 1", "ch1.xhtml")],
    )
    doc = read_epub(epub_bytes)
    assert doc.toc_root is not None
    assert len(doc.toc_root.children) == 1
    assert doc.toc_root.children[0].title == "Chapter 1"


def test_missing_nav():
    epub_bytes = make_epub_zip(
        spine_files={"OEBPS/ch1.xhtml": "<p>Content</p>"},
        # No nav_toc or page_list
    )
    doc = read_epub(epub_bytes)
    assert doc.toc_root is None
