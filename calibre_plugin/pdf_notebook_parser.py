"""Parse Kindle PDF notebook exports into Clipping objects.

The Kindle app can export annotations as a PDF document. This parser
extracts text from the PDF using Calibre's bundled ``pdftotext`` tool,
then walks the resulting lines with a simple state machine.
"""

import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from calibre.ebooks.pdf.pdftohtml import PDFTOTEXT

from calibre_plugins.kindle_annotation_import.models import (
    Clipping,
    ClippingType,
    ParseResult,
)

# --- line-level patterns ---------------------------------------------------

HIGHLIGHT_RE = re.compile(r"^Page (\d+) \| Highlight \((\w+)\)\s*(.*)")
CONTINUED_RE = re.compile(r"^Page (\d+) \| Highlight Continued")
STANDALONE_NOTE_RE = re.compile(r"^Page (\d+) \| Note\s+(.*)")
PAIRED_NOTE_RE = re.compile(r"^Note:\s*(.*)")
TIMESTAMP_RE = re.compile(r"^[A-Z][a-z]{2} \d{1,2}, \d{4}$")
PAGE_FOOTER_RE = re.compile(r"^\d+$")

_MAX_SKIPPED_SAMPLES = 5


def _try_parse_timestamp(text: str) -> Optional[datetime]:
    text = text.strip()
    try:
        return datetime.strptime(text, "%b %d, %Y")
    except ValueError:
        return None


def _record_skip(skipped_samples: list[str], text: str) -> None:
    if len(skipped_samples) < _MAX_SKIPPED_SAMPLES:
        skipped_samples.append(text[:200])


def _extract_text(path: str) -> str:
    """Run Calibre's bundled pdftotext and return the full text."""
    result = subprocess.run(
        [PDFTOTEXT, "-enc", "UTF-8", "-nopgbrk", path, "-"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"pdftotext failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


def _parse_title_author(line: str) -> tuple[str, str]:
    """Parse 'Title by Author' from the first line of the PDF text."""
    # The title line format is "Title by Author"
    # Use the last occurrence of " by " to split, since titles can contain "by"
    idx = line.rfind(" by ")
    if idx > 0:
        return line[:idx].strip(), line[idx + 4 :].strip()
    return line.strip(), ""


def parse_pdf_notebook(path: str | Path) -> ParseResult:
    text = _extract_text(str(path))
    lines = text.splitlines()

    # --- header ---
    book_title = ""
    author = ""
    if lines:
        book_title, author = _parse_title_author(lines[0])

    # Skip the Amazon link and annotation summary lines.
    # Find the first blank line after the header block, then start parsing.
    body_start = 1
    for i in range(1, min(len(lines), 6)):
        if not lines[i].strip():
            body_start = i + 1
            break

    # --- state machine ---
    clippings: list[Clipping] = []
    skipped_samples: list[str] = []
    total = 0

    # Track the last highlight for note pairing and "Highlight Continued".
    current_highlight: Optional[Clipping] = None
    # Accumulate multi-line highlight text across pdftotext line breaks.
    accumulating_text_for: Optional[Clipping] = None

    def _flush_accumulator():
        nonlocal accumulating_text_for
        if accumulating_text_for is not None:
            accumulating_text_for.content = accumulating_text_for.content.strip()
            accumulating_text_for = None

    for line in lines[body_start:]:
        stripped = line.strip()
        if not stripped:
            _flush_accumulator()
            continue

        # PDF page footer (bare number)
        if PAGE_FOOTER_RE.match(stripped):
            _flush_accumulator()
            continue

        # Highlight
        m = HIGHLIGHT_RE.match(stripped)
        if m:
            _flush_accumulator()
            total += 1
            page = int(m.group(1))
            highlight_text = m.group(3)

            clip = Clipping(
                book_title=book_title,
                author=author,
                clipping_type=ClippingType.HIGHLIGHT,
                page=page,
                location_start=page,
                location_end=page,
                timestamp=None,
                content=highlight_text,
                raw_header=stripped,
            )
            clippings.append(clip)
            current_highlight = clip
            accumulating_text_for = clip
            continue

        # Highlight Continued — PDF page-break artifact, no new text
        m = CONTINUED_RE.match(stripped)
        if m:
            _flush_accumulator()
            # Don't create a clipping; keep current_highlight for note pairing.
            continue

        # Standalone note (Page N | Note ...)
        m = STANDALONE_NOTE_RE.match(stripped)
        if m:
            _flush_accumulator()
            total += 1
            page = int(m.group(1))
            note_text = m.group(2)

            clip = Clipping(
                book_title=book_title,
                author=author,
                clipping_type=ClippingType.NOTE,
                page=page,
                location_start=page,
                location_end=page,
                timestamp=None,
                content=note_text,
                raw_header=stripped,
            )
            clippings.append(clip)
            current_highlight = None
            accumulating_text_for = None
            continue

        # Paired note (Note: ...)
        m = PAIRED_NOTE_RE.match(stripped)
        if m:
            _flush_accumulator()
            total += 1
            note_text = m.group(1)
            page = current_highlight.page if current_highlight else None
            loc = current_highlight.location_start if current_highlight else 0

            clip = Clipping(
                book_title=book_title,
                author=author,
                clipping_type=ClippingType.NOTE,
                page=page,
                location_start=loc,
                location_end=loc,
                timestamp=None,
                content=note_text,
                raw_header=stripped,
            )
            clippings.append(clip)
            accumulating_text_for = None
            continue

        # Timestamp
        if TIMESTAMP_RE.match(stripped):
            _flush_accumulator()
            ts = _try_parse_timestamp(stripped)
            # Attach to the most recently created clipping.
            if ts and clippings:
                last = clippings[-1]
                if last.timestamp is None:
                    last.timestamp = ts
            continue

        # If we're accumulating multi-line highlight text, append this line.
        if accumulating_text_for is not None:
            accumulating_text_for.content += " " + stripped
            continue

        # Anything else: section heading or unrecognised line — skip silently.

    _flush_accumulator()

    skipped = total - len(clippings)
    return ParseResult(
        clippings=clippings,
        total_entries=total,
        parsed_entries=len(clippings),
        skipped_entries=skipped,
        skipped_samples=skipped_samples,
    )
