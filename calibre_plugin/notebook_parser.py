import html
import re
from pathlib import Path

from calibre_plugins.kindle_annotation_import.models import Clipping, ClippingType

BOOK_TITLE_RE = re.compile(r"<div class='bookTitle'>(.*?)</div>", re.DOTALL)
AUTHORS_RE = re.compile(r"<div class='authors'>\s*(.*?)\s*</div>", re.DOTALL)
NOTE_BLOCK_RE = re.compile(
    r"<h3 class='noteHeading'>(.*?)</div><div class='noteText'>(.*?)</h3>",
    re.DOTALL,
)
HIGHLIGHT_HEADING_RE = re.compile(
    r"Highlight \(<span class='highlight_(\w+)'>\w+</span>\)\s*-\s*Page (\d+)\s*&middot;\s*Location (\d+)"
)
NOTE_HEADING_RE = re.compile(r"Note\s*-\s*Page (\d+)\s*&middot;\s*Location (\d+)")


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def parse_notebook(path: str | Path) -> list[Clipping]:
    text = Path(path).read_text(encoding="utf-8")

    title_match = BOOK_TITLE_RE.search(text)
    book_title = html.unescape(_strip_tags(title_match.group(1))) if title_match else ""

    authors_match = AUTHORS_RE.search(text)
    author = authors_match.group(1).strip() if authors_match else ""

    clippings = []

    for block in NOTE_BLOCK_RE.finditer(text):
        heading_raw = block.group(1)
        note_text = html.unescape(_strip_tags(block.group(2)))
        raw_header = html.unescape(_strip_tags(heading_raw))

        highlight_match = HIGHLIGHT_HEADING_RE.search(heading_raw)
        if highlight_match:
            page = int(highlight_match.group(2))
            location = int(highlight_match.group(3))
            clippings.append(
                Clipping(
                    book_title=book_title,
                    author=author,
                    clipping_type=ClippingType.HIGHLIGHT,
                    page=page,
                    location_start=location,
                    location_end=location,
                    timestamp=None,
                    content=note_text,
                    raw_header=raw_header,
                )
            )
            continue

        note_match = NOTE_HEADING_RE.search(heading_raw)
        if note_match:
            page = int(note_match.group(1))
            location = int(note_match.group(2))
            clippings.append(
                Clipping(
                    book_title=book_title,
                    author=author,
                    clipping_type=ClippingType.NOTE,
                    page=page,
                    location_start=location,
                    location_end=location,
                    timestamp=None,
                    content=note_text,
                    raw_header=raw_header,
                )
            )

    return clippings
