import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from calibre_plugins.kindle_annotation_import.models import Clipping, ClippingType

SEPARATOR = "=========="

METADATA_RE = re.compile(
    r"- Your (Highlight|Note|Bookmark) on "
    r"(?:page (\d+) \| )?"
    r"Location (\d+)(?:-(\d+))? \| "
    r"Added on (.+)"
)


def parse_title_author(line: str) -> tuple[str, str]:
    line = line.strip().lstrip("\ufeff")
    match = re.match(r"^(.+)\(([^)]+)\)\s*$", line)
    if match:
        title = match.group(1).strip()
        author = match.group(2).strip()
        return title, author
    return line, ""


def parse_clippings(path: str | Path) -> list[Clipping]:
    text = Path(path).read_text(encoding="utf-8-sig")
    entries = text.split(SEPARATOR)
    clippings = []

    for entry in entries:
        entry = entry.strip()
        if not entry:
            continue

        lines = entry.split("\n")
        if len(lines) < 2:
            continue

        title_line = lines[0]
        meta_line = lines[1].strip()

        book_title, author = parse_title_author(title_line)

        match = METADATA_RE.match(meta_line)
        if not match:
            continue

        clipping_type = ClippingType(match.group(1))
        page = int(match.group(2)) if match.group(2) else None
        location_start = int(match.group(3))
        location_end = int(match.group(4)) if match.group(4) else location_start
        timestamp = datetime.strptime(
            match.group(5).strip(), "%A, %B %d, %Y %I:%M:%S %p"
        )

        content = "\n".join(lines[3:]).strip() if len(lines) > 3 else ""

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

    return clippings


def filter_by_book(clippings: list[Clipping], book_query: str) -> list[Clipping]:
    query = book_query.lower()
    return [c for c in clippings if query in c.book_title.lower()]
