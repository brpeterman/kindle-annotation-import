import html
import re
from pathlib import Path

from calibre_plugins.kindle_annotation_import.models import (
    Clipping,
    ClippingType,
    ParseResult,
)

BOOK_TITLE_RE = re.compile(r"<div class='bookTitle'>(.*?)</div>", re.DOTALL)
AUTHORS_RE = re.compile(r"<div class='authors'>\s*(.*?)\s*</div>", re.DOTALL)
NOTE_BLOCK_RE = re.compile(
    r"<h3 class='noteHeading'>(.*?)</div><div class='noteText'>(.*?)</h3>",
    re.DOTALL,
)

# Structural marker: highlights always have a <span class='highlight_COLOR'> tag.
HIGHLIGHT_SPAN_RE = re.compile(r"<span class='highlight_(\w+)'>")

# Two numbers separated by a middot (page · location), with any translated
# words in between.  Works across all Kindle locales.
HEADING_NUMBERS_RE = re.compile(r"(\d+)\s*(?:&middot;|·)\s*\D*?(\d+)")

# Fallback: single trailing number when there is no middot.
SINGLE_NUMBER_RE = re.compile(r"(\d+)\s*$")

_MAX_SKIPPED_SAMPLES = 5


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _record_skip(skipped_samples: list[str], text: str) -> None:
    if len(skipped_samples) < _MAX_SKIPPED_SAMPLES:
        skipped_samples.append(text[:200])


def parse_notebook(path: str | Path) -> ParseResult:
    text = Path(path).read_text(encoding="utf-8")

    title_match = BOOK_TITLE_RE.search(text)
    book_title = html.unescape(_strip_tags(title_match.group(1))) if title_match else ""

    authors_match = AUTHORS_RE.search(text)
    author = authors_match.group(1).strip() if authors_match else ""

    clippings = []
    total = 0
    skipped_samples: list[str] = []

    for block in NOTE_BLOCK_RE.finditer(text):
        total += 1
        heading_raw = block.group(1)
        note_text = html.unescape(_strip_tags(block.group(2)))
        raw_header = html.unescape(_strip_tags(heading_raw))

        # Determine type: presence of highlight_COLOR span → highlight, else note.
        is_highlight = bool(HIGHLIGHT_SPAN_RE.search(heading_raw))

        # Extract page and location numbers.
        numbers_match = HEADING_NUMBERS_RE.search(heading_raw)
        if numbers_match:
            page = int(numbers_match.group(1))
            location = int(numbers_match.group(2))
        else:
            # Fallback: single number treated as location, no page.
            single_match = SINGLE_NUMBER_RE.search(_strip_tags(heading_raw))
            if single_match:
                page = None
                location = int(single_match.group(1))
            else:
                _record_skip(skipped_samples, raw_header)
                continue

        clipping_type = ClippingType.HIGHLIGHT if is_highlight else ClippingType.NOTE

        clippings.append(
            Clipping(
                book_title=book_title,
                author=author,
                clipping_type=clipping_type,
                page=page,
                location_start=location,
                location_end=location,
                timestamp=None,
                content=note_text,
                raw_header=raw_header,
            )
        )

    skipped = total - len(clippings)
    return ParseResult(
        clippings=clippings,
        total_entries=total,
        parsed_entries=len(clippings),
        skipped_entries=skipped,
        skipped_samples=skipped_samples,
    )
