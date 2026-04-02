"""Tests for calibre_plugin/notebook_parser.py."""

from calibre_plugins.kindle_annotation_import.notebook_parser import parse_notebook
from calibre_plugins.kindle_annotation_import.models import ClippingType


def _write_html(tmp_path, body):
    """Write a minimal Kindle notebook HTML file."""
    html = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<html xmlns='http://www.w3.org/TR/1999/REC-html-in-xml'>"
        "<head></head>"
        "<body><div class='bodyContainer'>"
        "<h1>"
        "<div class='bookTitle'>Test Book</div>"
        "<div class='authors'>Test Author</div>"
        "</h1>" + body + "</div></body></html>"
    )
    p = tmp_path / "notebook.html"
    p.write_text(html, encoding="utf-8")
    return str(p)


def test_single_highlight(tmp_path):
    body = (
        "<h3 class='noteHeading'>"
        "Highlight (<span class='highlight_yellow'>yellow</span>) - "
        "Chapter &gt; Page 42 &middot; Location 500"
        "</div><div class='noteText'>"
        "The highlighted text here"
        "</h3>"
    )
    result = parse_notebook(_write_html(tmp_path, body))
    assert result.parsed_entries == 1
    c = result.clippings[0]
    assert c.clipping_type == ClippingType.HIGHLIGHT
    assert c.page == 42
    assert c.location_start == 500
    assert c.content == "The highlighted text here"


def test_single_note(tmp_path):
    body = (
        "<h3 class='noteHeading'>"
        "Note - Chapter &gt; Page 42 &middot; Location 500"
        "</div><div class='noteText'>"
        "My note text"
        "</h3>"
    )
    result = parse_notebook(_write_html(tmp_path, body))
    assert result.parsed_entries == 1
    c = result.clippings[0]
    assert c.clipping_type == ClippingType.NOTE
    assert c.content == "My note text"


def test_highlight_and_paired_note(tmp_path):
    body = (
        "<h3 class='noteHeading'>"
        "Highlight (<span class='highlight_yellow'>yellow</span>) - "
        "Chapter &gt; Page 225 &middot; Location 2277"
        "</div><div class='noteText'>"
        "The highlighted passage"
        "</h3>"
        "<h3 class='noteHeading'>"
        "Note - Chapter &gt; Page 225 &middot; Location 2279"
        "</div><div class='noteText'>"
        "A note about this"
        "</h3>"
    )
    result = parse_notebook(_write_html(tmp_path, body))
    assert result.parsed_entries == 2
    highlight = result.clippings[0]
    note = result.clippings[1]
    assert highlight.clipping_type == ClippingType.HIGHLIGHT
    assert note.clipping_type == ClippingType.NOTE
    # Document-order pairing: note's location_start set to highlight's
    assert note.location_start == highlight.location_start


def test_title_and_author(tmp_path):
    result = parse_notebook(
        _write_html(
            tmp_path,
            (
                "<h3 class='noteHeading'>"
                "Highlight (<span class='highlight_blue'>blue</span>) - Page 1 &middot; Location 10"
                "</div><div class='noteText'>text</h3>"
            ),
        )
    )
    assert result.clippings[0].book_title == "Test Book"
    assert result.clippings[0].author == "Test Author"


def test_html_entity_decoding(tmp_path):
    body = (
        "<h3 class='noteHeading'>"
        "Highlight (<span class='highlight_yellow'>yellow</span>) - "
        "Running &gt; Page 10 &middot; Location 100"
        "</div><div class='noteText'>"
        "He said &quot;hello&quot;"
        "</h3>"
    )
    result = parse_notebook(_write_html(tmp_path, body))
    assert result.clippings[0].content == 'He said "hello"'


def test_location_only_no_page(tmp_path):
    body = (
        "<h3 class='noteHeading'>"
        "Highlight (<span class='highlight_yellow'>yellow</span>) - Location 200"
        "</div><div class='noteText'>text</h3>"
    )
    result = parse_notebook(_write_html(tmp_path, body))
    assert result.parsed_entries == 1
    c = result.clippings[0]
    assert c.page is None
    assert c.location_start == 200


def test_skip_entry_no_numbers(tmp_path):
    body = (
        "<h3 class='noteHeading'>"
        "Highlight (<span class='highlight_yellow'>yellow</span>) - No numbers here"
        "</div><div class='noteText'>text</h3>"
    )
    result = parse_notebook(_write_html(tmp_path, body))
    assert result.parsed_entries == 0
    assert result.skipped_entries == 1


def test_multiple_highlights(tmp_path):
    entries = ""
    for i in range(3):
        entries += (
            f"<h3 class='noteHeading'>"
            f"Highlight (<span class='highlight_yellow'>yellow</span>) - "
            f"Page {i + 1} &middot; Location {(i + 1) * 100}"
            f"</div><div class='noteText'>Text {i + 1}</h3>"
        )
    result = parse_notebook(_write_html(tmp_path, entries))
    assert result.parsed_entries == 3
    assert [c.page for c in result.clippings] == [1, 2, 3]
