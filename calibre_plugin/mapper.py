import re

from calibre_plugins.kindle_annotation_import.models import (
    Clipping,
    ClippingType,
    EpubDocument,
    MappingResult,
    PageAnchor,
)


def normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


_BEFORE_PUNCT = re.compile(r"\s+([,.?!:;\-/])")
_AFTER_OPEN_QUOTE = re.compile(r"([\u201C\u2018])\s+")
_BEFORE_CLOSE_QUOTE = re.compile(r"\s+([\u201D\u2019])")
_APOSTROPHE_SPACES = re.compile(r"(\w)\s*(['\u2019])\s*(\w)")


def fix_spaced_punctuation(text: str) -> str:
    text = _BEFORE_PUNCT.sub(r"\1", text)
    text = _AFTER_OPEN_QUOTE.sub(r"\1", text)
    text = _BEFORE_CLOSE_QUOTE.sub(r"\1", text)
    text = _APOSTROPHE_SPACES.sub(r"\1\2\3", text)
    return text


def map_clippings(clippings: list[Clipping], epub: EpubDocument) -> list[MappingResult]:
    results = []
    highlight_results: dict[tuple[int, int], MappingResult] = {}

    highlights = [c for c in clippings if c.clipping_type == ClippingType.HIGHLIGHT]
    others = [c for c in clippings if c.clipping_type != ClippingType.HIGHLIGHT]

    for clip in highlights:
        result = _map_highlight(clip, epub)
        results.append(result)
        if result.matched:
            highlight_results[(clip.location_start, clip.location_end)] = result

    for clip in others:
        result = _map_note_or_bookmark(clip, epub, highlight_results)
        results.append(result)

    return results


def _map_highlight(clip: Clipping, epub: EpubDocument) -> MappingResult:
    if not clip.content:
        return MappingResult(clipping=clip, matched=False)

    needle = normalize_text(clip.content)
    result = _search_epub(clip, epub, needle)

    if not result.matched:
        fixed_needle = fix_spaced_punctuation(needle)
        if fixed_needle != needle:
            print(f"Trying again with fixed punctuation using string '{fixed_needle}'")
            result = _search_epub(clip, epub, fixed_needle)

    return result


def _search_epub(clip: Clipping, epub: EpubDocument, needle: str) -> MappingResult:
    if clip.page is not None:
        anchor = _find_page_anchor(epub, clip.page)
        if anchor:
            text = epub.file_texts.get(anchor.file_path, "")
            norm_text = normalize_text(text)

            norm_anchor_offset = _find_normalized_offset(text, anchor.char_offset)
            search_start = max(0, norm_anchor_offset - 500)

            next_anchor = _find_page_anchor(epub, clip.page + 1)
            if next_anchor and next_anchor.file_path == anchor.file_path:
                norm_end = _find_normalized_offset(text, next_anchor.char_offset)
                search_end = min(len(norm_text), norm_end + 500)
            else:
                search_end = min(len(norm_text), norm_anchor_offset + 5000)

            region = norm_text[search_start:search_end]
            pos = region.find(needle)
            if pos >= 0:
                abs_offset = search_start + pos
                clip.content = needle
                return _build_result(
                    clip,
                    anchor.file_path,
                    abs_offset,
                    abs_offset + len(needle),
                    text,
                    norm_text,
                    "text_exact_page",
                    1.0,
                )

    for file_path in epub.spine_files:
        text = epub.file_texts.get(file_path, "")
        norm_text = normalize_text(text)
        pos = norm_text.find(needle)
        if pos >= 0:
            confidence = 0.9 if clip.page is not None else 0.8
            return _build_result(
                clip,
                file_path,
                pos,
                pos + len(needle),
                text,
                norm_text,
                "text_exact_global",
                confidence,
            )

    return MappingResult(clipping=clip, matched=False)


def _map_note_or_bookmark(
    clip: Clipping,
    epub: EpubDocument,
    highlight_results: dict[tuple[int, int], MappingResult],
) -> MappingResult:
    for (h_start, h_end), h_result in highlight_results.items():
        if clip.location_start == h_end or clip.location_end == h_end:
            if h_result.matched:
                return MappingResult(
                    clipping=clip,
                    matched=True,
                    file_path=h_result.file_path,
                    char_offset_start=h_result.char_offset_end,
                    char_offset_end=h_result.char_offset_end,
                    match_method="paired_with_highlight",
                    confidence=1.0,
                    context=h_result.context,
                )

    if clip.page is not None:
        anchor = _find_page_anchor(epub, clip.page)
        if anchor:
            return MappingResult(
                clipping=clip,
                matched=True,
                file_path=anchor.file_path,
                char_offset_start=anchor.char_offset,
                char_offset_end=anchor.char_offset,
                match_method="page_anchor_only",
                confidence=0.5,
                context=epub.file_texts.get(anchor.file_path, "")[
                    anchor.char_offset : anchor.char_offset + 100
                ],
            )

    return MappingResult(clipping=clip, matched=False)


def _find_page_anchor(epub: EpubDocument, page_num: int) -> PageAnchor | None:
    for a in epub.page_anchors:
        if a.page_number == page_num:
            return a
    return None


def _find_normalized_offset(original_text: str, original_offset: int) -> int:
    """Map a char offset in original text to the approximate offset in normalized text."""
    prefix = original_text[:original_offset]
    return len(normalize_text(prefix))


def _norm_to_original_offset(original_text: str, norm_offset: int) -> int:
    """Map a char offset in normalize_text(original_text) back to original_text."""
    norm_pos = 0
    prev_was_space = True  # True to simulate strip() of leading whitespace
    for i, ch in enumerate(original_text):
        c = " " if ch == "\xa0" else ch
        if c.isspace():
            if not prev_was_space:
                if norm_pos == norm_offset:
                    return i
                norm_pos += 1
            prev_was_space = True
        else:
            if norm_pos == norm_offset:
                return i
            norm_pos += 1
            prev_was_space = False
    return len(original_text)


def _build_result(
    clip: Clipping,
    file_path: str,
    norm_start: int,
    norm_end: int,
    original_text: str,
    norm_text: str,
    method: str,
    confidence: float,
) -> MappingResult:
    ctx_start = max(0, norm_start - 50)
    ctx_end = min(len(norm_text), norm_end + 50)
    context = norm_text[ctx_start:ctx_end]
    orig_start = _norm_to_original_offset(original_text, norm_start)
    orig_end = _norm_to_original_offset(original_text, norm_end)
    return MappingResult(
        clipping=clip,
        matched=True,
        file_path=file_path,
        char_offset_start=orig_start,
        char_offset_end=orig_end,
        match_method=method,
        confidence=confidence,
        context=context,
    )
