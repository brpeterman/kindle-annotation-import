import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from calibre_plugins.kindle_annotation_import.models import (
    Clipping,
    ClippingType,
    ParseResult,
)

SEPARATOR = "=========="

# English-only regex — fast path for the most common locale.
METADATA_RE = re.compile(
    r"- Your (Highlight|Note|Bookmark) on "
    r"(?:page (\d+) \| )?"
    r"Location (\d+)(?:-(\d+))? \| "
    r"Added on (.+)"
)

# Location range pattern: one or two numbers separated by a dash.
_LOCATION_RE = re.compile(r"(\d+)(?:\s*-\s*(\d+))?")

# Multilingual type keywords → ClippingType.
# Covers English, German, Spanish, French, Italian, Portuguese, Dutch,
# Swedish, Norwegian, Danish, Turkish, Polish, Japanese, Chinese, Korean.
_TYPE_KEYWORDS: dict[str, ClippingType] = {
    # English
    "highlight": ClippingType.HIGHLIGHT,
    "note": ClippingType.NOTE,
    "bookmark": ClippingType.BOOKMARK,
    # German
    "markierung": ClippingType.HIGHLIGHT,
    "notiz": ClippingType.NOTE,
    "lesezeichen": ClippingType.BOOKMARK,
    # Spanish
    "subrayado": ClippingType.HIGHLIGHT,
    "nota": ClippingType.NOTE,
    "marcador": ClippingType.BOOKMARK,
    # French
    "surlignement": ClippingType.HIGHLIGHT,
    "signet": ClippingType.BOOKMARK,
    # Italian
    "evidenziazione": ClippingType.HIGHLIGHT,
    "segnalibro": ClippingType.BOOKMARK,
    # Portuguese
    "destaque": ClippingType.HIGHLIGHT,
    "marcador de página": ClippingType.BOOKMARK,
    # Dutch
    "markering": ClippingType.HIGHLIGHT,
    "bladwijzer": ClippingType.BOOKMARK,
    "notitie": ClippingType.NOTE,
    # Swedish
    "markering": ClippingType.HIGHLIGHT,
    "bokmärke": ClippingType.BOOKMARK,
    "anteckning": ClippingType.NOTE,
    # Turkish
    "vurgulama": ClippingType.HIGHLIGHT,
    "yer imi": ClippingType.BOOKMARK,
    # Polish
    "zaznaczenie": ClippingType.HIGHLIGHT,
    "notatka": ClippingType.NOTE,
    "zakładka": ClippingType.BOOKMARK,
    # Japanese
    "ハイライト": ClippingType.HIGHLIGHT,
    "メモ": ClippingType.NOTE,
    "ブックマーク": ClippingType.BOOKMARK,
    # Chinese (Simplified)
    "标注": ClippingType.HIGHLIGHT,
    "笔记": ClippingType.NOTE,
    "书签": ClippingType.BOOKMARK,
    # Chinese (Traditional)
    "標註": ClippingType.HIGHLIGHT,
    "筆記": ClippingType.NOTE,
    "書籤": ClippingType.BOOKMARK,
    # Korean
    "하이라이트": ClippingType.HIGHLIGHT,
    "메모": ClippingType.NOTE,
    "북마크": ClippingType.BOOKMARK,
}

_TIMESTAMP_FORMATS = [
    "%A, %B %d, %Y %I:%M:%S %p",  # English US
    "%A, %B %d, %Y %H:%M:%S",  # English 24h variant
    "%A, %d %B %Y %H:%M:%S",  # day-before-month (many European)
    "%A %d %B %Y %H:%M:%S",  # without comma
    "%A, %d. %B %Y %H:%M:%S",  # German (period after day)
    "%A, %d de %B de %Y %H:%M:%S",  # Spanish/Portuguese
    "%Y年%m月%d日%A %H:%M:%S",  # Japanese
    "%Y年%m月%d日 %H:%M:%S",  # Chinese
]

_MAX_SKIPPED_SAMPLES = 5


def _try_parse_timestamp(text: str) -> Optional[datetime]:
    """Try multiple strptime formats. Returns None if none match."""
    text = text.strip()
    for fmt in _TIMESTAMP_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _infer_type_from_words(text: str) -> Optional[ClippingType]:
    """Check for known annotation-type keywords in any language."""
    lower = text.lower()
    for keyword, ctype in _TYPE_KEYWORDS.items():
        if keyword in lower:
            return ctype
    return None


def _parse_metadata_structural(
    meta_line: str, has_content: bool
) -> Optional[tuple[ClippingType, Optional[int], int, int, Optional[datetime]]]:
    """Fallback parser using structural invariants (pipe separators, digits).

    Returns (clipping_type, page, location_start, location_end, timestamp)
    or None if the line is not recognisable as a metadata line.
    """
    if not meta_line.startswith("- "):
        return None

    segments = meta_line.split(" | ")
    if len(segments) < 2:
        return None

    # Last segment is the timestamp (everything after the last pipe).
    timestamp = _try_parse_timestamp(segments[-1])

    # Remaining segments contain type, page, and location info.
    info_segments = segments[:-1]
    info_text = " | ".join(info_segments)

    # Find all digit sequences in the info segments.
    numbers = re.findall(r"\d+", info_text)
    if not numbers:
        return None

    # Find a location range pattern (e.g., "1024-1031" or just "1024").
    loc_match = _LOCATION_RE.search(info_text)
    if not loc_match:
        return None

    location_start = int(loc_match.group(1))
    location_end = int(loc_match.group(2)) if loc_match.group(2) else location_start

    # The page number, if present, appears as a standalone number in the first
    # segment, distinct from the location.  We look for a number in the first
    # segment that is NOT the location number.
    page = None
    first_segment_numbers = re.findall(r"\d+", info_segments[0])
    loc_str = loc_match.group(0)
    for n in first_segment_numbers:
        if n not in loc_str:
            page = int(n)
            break

    # If the location appeared in a second segment (common format:
    # "... page 42 | Location 1024-1031 | Added on ..."), and the first
    # segment has numbers, one might be the page.
    if page is None and len(info_segments) >= 2:
        # Location was likely in the second segment; first-segment numbers
        # could be the page.
        for n in first_segment_numbers:
            page = int(n)
            break

    # Determine annotation type from keywords.
    clipping_type = _infer_type_from_words(info_segments[0])
    if clipping_type is None:
        # Content-based inference: empty content = Bookmark, else Highlight.
        clipping_type = (
            ClippingType.BOOKMARK if not has_content else ClippingType.HIGHLIGHT
        )

    return (clipping_type, page, location_start, location_end, timestamp)


def _record_skip(skipped_samples: list[str], text: str) -> None:
    if len(skipped_samples) < _MAX_SKIPPED_SAMPLES:
        skipped_samples.append(text[:200])


def parse_title_author(line: str) -> tuple[str, str]:
    line = line.strip().lstrip("\ufeff")
    match = re.match(r"^(.+)\(([^)]+)\)\s*$", line)
    if match:
        title = match.group(1).strip()
        author = match.group(2).strip()
        return title, author
    return line, ""


def parse_clippings(path: str | Path) -> ParseResult:
    text = Path(path).read_text(encoding="utf-8-sig")
    entries = text.split(SEPARATOR)
    clippings = []
    total = 0
    skipped_samples: list[str] = []

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue
        total += 1

        lines = entry.split("\n")
        if len(lines) < 2:
            _record_skip(skipped_samples, entry)
            continue

        title_line = lines[0]
        meta_line = lines[1].strip()
        content = "\n".join(lines[3:]).strip() if len(lines) > 3 else ""
        book_title, author = parse_title_author(title_line)

        # Fast path: English regex.
        match = METADATA_RE.match(meta_line)
        if match:
            clipping_type = ClippingType(match.group(1))
            page = int(match.group(2)) if match.group(2) else None
            location_start = int(match.group(3))
            location_end = int(match.group(4)) if match.group(4) else location_start
            timestamp = _try_parse_timestamp(match.group(5).strip())
        else:
            # Structural fallback for non-English locales.
            parsed = _parse_metadata_structural(meta_line, bool(content))
            if not parsed:
                _record_skip(skipped_samples, entry)
                continue
            clipping_type, page, location_start, location_end, timestamp = parsed

        clippings.append(
            Clipping(
                book_title=book_title,
                author=author,
                clipping_type=clipping_type,
                page=page,
                location_start=location_start,
                location_end=location_end,
                timestamp=timestamp,
                content=content,
                raw_header=meta_line,
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


def filter_by_book(clippings: list[Clipping], book_query: str) -> list[Clipping]:
    query = book_query.lower()
    return [c for c in clippings if query in c.book_title.lower()]
