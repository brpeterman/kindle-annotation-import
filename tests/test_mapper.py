"""Tests for calibre_plugin/mapper.py."""

from calibre_plugins.kindle_annotation_import.mapper import (
    normalize_text,
    fix_spaced_punctuation,
    map_clippings,
)
from calibre_plugins.kindle_annotation_import.models import ClippingType, PageAnchor
from factories import make_clipping, make_epub


# --- normalize_text ---


def test_normalize_collapses_whitespace():
    assert normalize_text("hello   world") == "hello world"


def test_normalize_replaces_nbsp():
    assert normalize_text("hello\xa0world") == "hello world"


def test_normalize_strips():
    assert normalize_text("  hello  ") == "hello"


def test_normalize_mixed():
    assert normalize_text("  a \xa0 b   c  ") == "a b c"


# --- fix_spaced_punctuation ---


def test_fix_before_comma():
    assert fix_spaced_punctuation("word , word") == "word, word"


def test_fix_before_period():
    assert fix_spaced_punctuation("end .") == "end."


def test_fix_before_ellipsis():
    assert fix_spaced_punctuation("word \u2026") == "word\u2026"


def test_fix_open_quote():
    assert fix_spaced_punctuation("\u201c word") == "\u201cword"


def test_fix_close_quote():
    assert fix_spaced_punctuation("word \u201d") == "word\u201d"


def test_fix_mid_word_apostrophe():
    assert fix_spaced_punctuation("don ' t") == "don't"


def test_fix_mid_word_dash():
    assert fix_spaced_punctuation("well - known") == "well-known"


# --- map_clippings: exact match (global) ---


def test_global_exact_match():
    clip = make_clipping(
        content="boats against the current",
        page=None,
        location_start=100,
        location_end=100,
    )
    epub = make_epub(
        file_texts={
            "OEBPS/ch1.xhtml": "So we beat on, boats against the current, borne back."
        },
        file_html={"OEBPS/ch1.xhtml": ""},
        spine_files=["OEBPS/ch1.xhtml"],
    )
    results = map_clippings([clip], epub)
    assert results[0].matched
    assert results[0].match_method == "text_exact_global"
    assert results[0].confidence == 0.8  # no page


def test_global_match_with_page():
    clip = make_clipping(
        content="boats against the current",
        page=42,
        location_start=100,
        location_end=100,
    )
    epub = make_epub(
        file_texts={
            "OEBPS/ch1.xhtml": "So we beat on, boats against the current, borne back."
        },
        file_html={"OEBPS/ch1.xhtml": ""},
        spine_files=["OEBPS/ch1.xhtml"],
    )
    results = map_clippings([clip], epub)
    assert results[0].matched
    assert results[0].match_method == "text_exact_global"
    assert results[0].confidence == 0.9  # has page but no anchor


# --- map_clippings: page-anchored match ---


def test_page_anchored_match():
    text = "X" * 1000 + "boats against the current" + "Y" * 1000
    clip = make_clipping(
        content="boats against the current",
        page=42,
        location_start=100,
        location_end=100,
    )
    epub = make_epub(
        file_texts={"OEBPS/ch1.xhtml": text},
        file_html={"OEBPS/ch1.xhtml": ""},
        spine_files=["OEBPS/ch1.xhtml"],
        page_anchors=[
            PageAnchor("42", 42, "OEBPS/ch1.xhtml", "page_42", 990),
        ],
    )
    results = map_clippings([clip], epub)
    assert results[0].matched
    assert results[0].match_method == "text_exact_page"
    assert results[0].confidence == 1.0


# --- map_clippings: punctuation fallback ---


def test_punctuation_fallback_sets_corrected_text():
    # The EPUB has correct punctuation, but the Kindle export has spaced punctuation
    clip = make_clipping(
        content="said , hello",
        page=None,
        location_start=100,
        location_end=100,
    )
    epub = make_epub(
        file_texts={"OEBPS/ch1.xhtml": "He said, hello to the crowd."},
        file_html={"OEBPS/ch1.xhtml": ""},
        spine_files=["OEBPS/ch1.xhtml"],
    )
    results = map_clippings([clip], epub)
    assert results[0].matched
    assert results[0].corrected_text == "said, hello"


# --- map_clippings: no match ---


def test_no_match():
    clip = make_clipping(content="text not in the book")
    epub = make_epub(
        file_texts={"OEBPS/ch1.xhtml": "Completely different content here."},
        file_html={"OEBPS/ch1.xhtml": ""},
        spine_files=["OEBPS/ch1.xhtml"],
    )
    results = map_clippings([clip], epub)
    assert not results[0].matched


def test_empty_content():
    clip = make_clipping(content="")
    epub = make_epub()
    results = map_clippings([clip], epub)
    assert not results[0].matched


# --- map_clippings: note pairing ---


def test_note_paired_with_highlight():
    highlight = make_clipping(
        clipping_type=ClippingType.HIGHLIGHT,
        content="boats against the current",
        location_start=100,
        location_end=150,
    )
    note = make_clipping(
        clipping_type=ClippingType.NOTE,
        content="My note",
        location_start=150,
        location_end=150,
    )
    epub = make_epub(
        file_texts={
            "OEBPS/ch1.xhtml": "So we beat on, boats against the current, borne back."
        },
        file_html={"OEBPS/ch1.xhtml": ""},
        spine_files=["OEBPS/ch1.xhtml"],
    )
    results = map_clippings([highlight, note], epub)
    assert results[0].matched  # highlight
    assert results[1].matched  # note paired
    assert results[1].match_method == "paired_with_highlight"
    assert results[1].confidence == 1.0


def test_note_fallback_to_page_anchor():
    note = make_clipping(
        clipping_type=ClippingType.NOTE,
        content="My note",
        page=42,
        location_start=999,
        location_end=999,
    )
    epub = make_epub(
        file_texts={"OEBPS/ch1.xhtml": "Some text here."},
        file_html={"OEBPS/ch1.xhtml": ""},
        spine_files=["OEBPS/ch1.xhtml"],
        page_anchors=[
            PageAnchor("42", 42, "OEBPS/ch1.xhtml", "page_42", 5),
        ],
    )
    results = map_clippings([note], epub)
    assert results[0].matched
    assert results[0].match_method == "page_anchor_only"
    assert results[0].confidence == 0.5
