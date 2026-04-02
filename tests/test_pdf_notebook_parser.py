"""Tests for calibre_plugin/pdf_notebook_parser.py."""

from datetime import datetime
from unittest.mock import patch

from calibre_plugins.kindle_annotation_import.pdf_notebook_parser import (
    parse_pdf_notebook,
    _parse_title_author,
    _try_parse_timestamp,
)
from calibre_plugins.kindle_annotation_import.models import ClippingType


def _mock_parse(text):
    """Call parse_pdf_notebook with mocked _extract_text returning the given text."""
    with patch(
        "calibre_plugins.kindle_annotation_import.pdf_notebook_parser._extract_text",
        return_value=text,
    ):
        return parse_pdf_notebook("dummy.pdf")


def test_basic_highlight():
    text = (
        "Test Book by Test Author\n"
        "Free Kindle instant preview: https://example.com\n"
        "Annotations (1) · 1 Highlights\n"
        "\n"
        'Page 68 | Highlight (Yellow) "Has Caladan been found?"\n'
        "Nov 10, 2022\n"
    )
    result = _mock_parse(text)
    assert result.parsed_entries == 1
    c = result.clippings[0]
    assert c.clipping_type == ClippingType.HIGHLIGHT
    assert c.page == 68
    assert '"Has Caladan been found?"' in c.content
    assert c.book_title == "Test Book"
    assert c.author == "Test Author"


def test_highlight_with_timestamp():
    text = (
        "Book by Author\n"
        "\n"
        "Page 10 | Highlight (Blue) Some text here\n"
        "Dec 25, 2023\n"
    )
    result = _mock_parse(text)
    c = result.clippings[0]
    assert c.timestamp is not None
    assert c.timestamp.year == 2023
    assert c.timestamp.month == 12
    assert c.timestamp.day == 25


def test_paired_note():
    text = (
        "Book by Author\n"
        "\n"
        "Page 68 | Highlight (Yellow) Some highlight text\n"
        "Nov 10, 2022\n"
        "Note: This is my note about the highlight\n"
        "Nov 10, 2022\n"
    )
    result = _mock_parse(text)
    assert result.parsed_entries == 2
    highlight = result.clippings[0]
    note = result.clippings[1]
    assert highlight.clipping_type == ClippingType.HIGHLIGHT
    assert note.clipping_type == ClippingType.NOTE
    assert note.content == "This is my note about the highlight"
    # Paired note should share page with preceding highlight
    assert note.location_start == highlight.location_start


def test_standalone_note():
    text = (
        "Book by Author\n"
        "\n"
        "Page 402 | Note I think this is an important observation\n"
        "Dec 7, 2022\n"
    )
    result = _mock_parse(text)
    assert result.parsed_entries == 1
    c = result.clippings[0]
    assert c.clipping_type == ClippingType.NOTE
    assert c.page == 402
    assert "important observation" in c.content


def test_highlight_continued():
    text = (
        "Book by Author\n"
        "\n"
        "Page 104 | Highlight (Yellow) A long highlight that spans pages\n"
        "Nov 12, 2022\n"
        "Page 104 | Highlight Continued\n"
        "Note: Right from the start\n"
        "Nov 12, 2022\n"
    )
    result = _mock_parse(text)
    # Should have 2 clippings: the highlight and the paired note.
    # "Highlight Continued" should NOT create a third clipping.
    assert result.parsed_entries == 2
    highlight = result.clippings[0]
    note = result.clippings[1]
    assert highlight.clipping_type == ClippingType.HIGHLIGHT
    assert note.clipping_type == ClippingType.NOTE
    assert note.content == "Right from the start"
    assert note.location_start == highlight.location_start


def test_multiline_highlight():
    text = (
        "Book by Author\n"
        "\n"
        "Page 50 | Highlight (Yellow) First line of highlight\n"
        "second line of highlight\n"
        "third line of highlight\n"
        "Jan 1, 2023\n"
    )
    result = _mock_parse(text)
    assert result.parsed_entries == 1
    c = result.clippings[0]
    assert "First line of highlight" in c.content
    assert "second line of highlight" in c.content
    assert "third line of highlight" in c.content


def test_page_footer_skipped():
    text = (
        "Book by Author\n"
        "\n"
        "Page 10 | Highlight (Yellow) Some text\n"
        "Jan 1, 2023\n"
        "5\n"
        "Page 20 | Highlight (Yellow) Other text\n"
        "Jan 2, 2023\n"
    )
    result = _mock_parse(text)
    assert result.parsed_entries == 2


def test_section_heading_skipped():
    text = (
        "Book by Author\n"
        "\n"
        "Book One: Pale\n"
        "\n"
        "Page 10 | Highlight (Yellow) Some text\n"
        "Jan 1, 2023\n"
    )
    result = _mock_parse(text)
    assert result.parsed_entries == 1


def test_title_author_parsing():
    assert _parse_title_author("Gardens of the Moon by Steven Erikson") == (
        "Gardens of the Moon",
        "Steven Erikson",
    )


def test_title_author_with_by_in_title():
    assert _parse_title_author("Stand by Me by Stephen King") == (
        "Stand by Me",
        "Stephen King",
    )


def test_title_no_author():
    assert _parse_title_author("Just a Title") == ("Just a Title", "")


def test_try_parse_timestamp():
    ts = _try_parse_timestamp("Nov 10, 2022")
    assert ts is not None
    assert ts == datetime(2022, 11, 10)


def test_try_parse_timestamp_invalid():
    assert _try_parse_timestamp("not a date") is None


def test_empty_input():
    result = _mock_parse("")
    assert result.parsed_entries == 0
    assert result.total_entries == 0
