"""Tests for calibre_plugin/clippings_parser.py."""

from datetime import datetime

from calibre_plugins.kindle_annotation_import.clippings_parser import (
    parse_clippings,
    parse_title_author,
    filter_by_book,
)
from calibre_plugins.kindle_annotation_import.models import ClippingType


def _write_clippings(tmp_path, text):
    p = tmp_path / "clippings.txt"
    p.write_text(text, encoding="utf-8")
    return str(p)


ENGLISH_HIGHLIGHT = (
    "The Great Gatsby (F. Scott Fitzgerald)\n"
    "- Your Highlight on page 42 | Location 1024-1031 | "
    "Added on Monday, January 1, 2024 12:00:00 AM\n"
    "\n"
    "So we beat on, boats against the current\n"
    "=========="
)


def test_english_highlight(tmp_path):
    result = parse_clippings(_write_clippings(tmp_path, ENGLISH_HIGHLIGHT))
    assert result.parsed_entries == 1
    c = result.clippings[0]
    assert c.clipping_type == ClippingType.HIGHLIGHT
    assert c.book_title == "The Great Gatsby"
    assert c.author == "F. Scott Fitzgerald"
    assert c.page == 42
    assert c.location_start == 1024
    assert c.location_end == 1031
    assert c.content == "So we beat on, boats against the current"


ENGLISH_NOTE = (
    "The Great Gatsby (F. Scott Fitzgerald)\n"
    "- Your Note on page 42 | Location 1024 | "
    "Added on Monday, January 1, 2024 12:00:00 AM\n"
    "\n"
    "This is my note\n"
    "=========="
)


def test_english_note(tmp_path):
    result = parse_clippings(_write_clippings(tmp_path, ENGLISH_NOTE))
    assert result.parsed_entries == 1
    c = result.clippings[0]
    assert c.clipping_type == ClippingType.NOTE
    assert c.content == "This is my note"
    assert c.location_start == 1024
    assert c.location_end == 1024


ENGLISH_BOOKMARK = (
    "The Great Gatsby (F. Scott Fitzgerald)\n"
    "- Your Bookmark on page 10 | Location 500 | "
    "Added on Monday, January 1, 2024 12:00:00 AM\n"
    "\n"
    "\n"
    "=========="
)


def test_english_bookmark(tmp_path):
    result = parse_clippings(_write_clippings(tmp_path, ENGLISH_BOOKMARK))
    assert result.parsed_entries == 1
    assert result.clippings[0].clipping_type == ClippingType.BOOKMARK


def test_multiple_entries(tmp_path):
    text = ENGLISH_HIGHLIGHT + "\n" + ENGLISH_NOTE
    result = parse_clippings(_write_clippings(tmp_path, text))
    assert result.parsed_entries == 2
    assert result.total_entries == 2
    assert result.skipped_entries == 0


def test_title_author_with_parens():
    title, author = parse_title_author("The Great Gatsby (F. Scott Fitzgerald)")
    assert title == "The Great Gatsby"
    assert author == "F. Scott Fitzgerald"


def test_title_no_author():
    title, author = parse_title_author("Unknown Title")
    assert title == "Unknown Title"
    assert author == ""


def test_title_with_bom():
    title, author = parse_title_author("\ufeffThe Great Gatsby (Author)")
    assert title == "The Great Gatsby"
    assert author == "Author"


STRUCTURAL_FALLBACK = (
    "Ein Buch (Autor Name)\n"
    "- Ihre Markierung auf Seite 10 | Position 200-210 | "
    "Hinzugef\u00fcgt am Montag, 1. Januar 2024 00:00:00\n"
    "\n"
    "German highlight text\n"
    "=========="
)


def test_structural_fallback(tmp_path):
    result = parse_clippings(_write_clippings(tmp_path, STRUCTURAL_FALLBACK))
    assert result.parsed_entries == 1
    c = result.clippings[0]
    assert c.clipping_type == ClippingType.HIGHLIGHT
    # Structural fallback finds the first number pattern via _LOCATION_RE.search
    # which matches "10" from "Seite 10" in the info_text.
    # The page is also extracted from first segment numbers.
    assert c.page == 10
    assert c.content == "German highlight text"


def test_timestamp_parsing(tmp_path):
    result = parse_clippings(_write_clippings(tmp_path, ENGLISH_HIGHLIGHT))
    c = result.clippings[0]
    assert c.timestamp is not None
    assert c.timestamp.year == 2024
    assert c.timestamp.month == 1
    assert c.timestamp.day == 1


def test_malformed_entry_skipped(tmp_path):
    text = "Just a single line with no metadata\n=========="
    result = parse_clippings(_write_clippings(tmp_path, text))
    assert result.parsed_entries == 0
    assert result.skipped_entries == 1
    assert len(result.skipped_samples) == 1


def test_skip_statistics(tmp_path):
    text = ENGLISH_HIGHLIGHT + "\nBad entry\n=========="
    result = parse_clippings(_write_clippings(tmp_path, text))
    assert result.total_entries == 2
    assert result.parsed_entries == 1
    assert result.skipped_entries == 1


def test_filter_by_book(tmp_path):
    text = (
        "Book Alpha (Author A)\n"
        "- Your Highlight on page 1 | Location 10-20 | Added on Monday, January 1, 2024 12:00:00 AM\n"
        "\n"
        "alpha content\n"
        "==========\n"
        "Book Beta (Author B)\n"
        "- Your Highlight on page 2 | Location 30-40 | Added on Monday, January 1, 2024 12:00:00 AM\n"
        "\n"
        "beta content\n"
        "=========="
    )
    result = parse_clippings(_write_clippings(tmp_path, text))
    filtered = filter_by_book(result.clippings, "Alpha")
    assert len(filtered) == 1
    assert filtered[0].book_title == "Book Alpha"


def test_empty_file(tmp_path):
    result = parse_clippings(_write_clippings(tmp_path, ""))
    assert result.parsed_entries == 0
    assert result.total_entries == 0
    assert result.skipped_entries == 0
    assert result.clippings == []


def test_no_page_number(tmp_path):
    text = (
        "A Book (Author)\n"
        "- Your Highlight on Location 500-510 | "
        "Added on Monday, January 1, 2024 12:00:00 AM\n"
        "\n"
        "highlighted text\n"
        "=========="
    )
    result = parse_clippings(_write_clippings(tmp_path, text))
    assert result.parsed_entries == 1
    assert result.clippings[0].page is None
    assert result.clippings[0].location_start == 500
