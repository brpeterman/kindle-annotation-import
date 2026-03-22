from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class ClippingType(Enum):
    HIGHLIGHT = "Highlight"
    NOTE = "Note"
    BOOKMARK = "Bookmark"


@dataclass
class Clipping:
    book_title: str
    author: str
    clipping_type: ClippingType
    page: Optional[int]
    location_start: int
    location_end: int
    timestamp: Optional[datetime]
    content: str
    raw_header: str


@dataclass
class PageAnchor:
    page_label: str
    page_number: Optional[int]
    file_path: str
    element_id: str
    char_offset: int


@dataclass
class EpubDocument:
    title: str
    spine_files: list[str]
    page_anchors: list[PageAnchor]
    file_texts: dict[str, str]
    file_html: dict[str, str]


@dataclass
class MappingResult:
    clipping: Clipping
    matched: bool
    file_path: Optional[str] = None
    char_offset_start: Optional[int] = None
    char_offset_end: Optional[int] = None
    match_method: Optional[str] = None
    confidence: float = 0.0
    context: str = ""
