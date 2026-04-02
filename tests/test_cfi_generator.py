"""Tests for calibre_plugin/cfi_generator.py."""

from calibre_plugins.kindle_annotation_import.cfi_generator import generate_cfi


def _xhtml(body: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml">'
        "<head/>"
        f"<body>{body}</body>"
        "</html>"
    ).encode("utf-8")


def test_simple_paragraph_offset_zero():
    xhtml = _xhtml("<p>Hello world</p>")
    cfi = generate_cfi(xhtml, 0)
    assert cfi is not None
    assert ":0" in cfi


def test_mid_text_offset():
    xhtml = _xhtml("<p>Hello world</p>")
    cfi = generate_cfi(xhtml, 5)
    assert cfi is not None
    assert ":5" in cfi


def test_second_paragraph():
    xhtml = _xhtml("<p>First</p><p>Second</p>")
    # "First" = 5 chars, so offset 5 = start of "Second"
    cfi = generate_cfi(xhtml, 5)
    assert cfi is not None
    assert ":0" in cfi


def test_tail_text():
    # <p><b>bold</b> tail</p>
    # Text extraction: "bold" (b.text, 4 chars), " tail" (b.tail, 5 chars)
    xhtml = _xhtml("<p><b>bold</b> tail</p>")
    cfi = generate_cfi(xhtml, 4)
    assert cfi is not None
    # Tail text: text node after the <b> element, offset 0 into " tail"
    assert ":0" in cfi


def test_nested_elements():
    xhtml = _xhtml("<div><p><span>deep text</span></p></div>")
    cfi = generate_cfi(xhtml, 0)
    assert cfi is not None
    steps = cfi.split("/")
    assert len(steps) >= 5


def test_element_with_unique_id():
    # Use offset inside <body> directly to ensure the id'd element is in the path
    xhtml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<html xmlns="http://www.w3.org/1999/xhtml">'
        '<body><p id="para1">Hello</p></body>'
        "</html>"
    ).encode("utf-8")
    cfi = generate_cfi(xhtml, 0)
    assert cfi is not None
    assert "[para1]" in cfi


def test_non_unique_id():
    xhtml = _xhtml('<p id="dup">First</p><p id="dup">Second</p>')
    cfi = generate_cfi(xhtml, 0)
    assert cfi is not None
    assert "[dup]" not in cfi


def test_out_of_range_offset():
    xhtml = _xhtml("<p>Short</p>")
    cfi = generate_cfi(xhtml, 999)
    assert cfi is None


def test_offset_at_exact_end():
    # With <head/>, total text is just "Hello" (5 chars). Offset 5 = past end.
    xhtml = _xhtml("<p>Hello</p>")
    cfi = generate_cfi(xhtml, 5)
    assert cfi is None


def test_multiple_siblings():
    xhtml = _xhtml("<p>AAA</p><p>BBB</p><p>CCC</p>")
    # AAA=3, BBB=3, CCC=3. Offset 6 = start of CCC
    cfi = generate_cfi(xhtml, 6)
    assert cfi is not None
    assert ":0" in cfi
