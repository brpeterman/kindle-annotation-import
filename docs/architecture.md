# Annotation Import Pipeline

This document describes how the plugin extracts Kindle annotations, maps them
to positions in an EPUB, and stores them in Calibre's annotation database.

Sections marked with **ASSUMPTION** or **DEVIATION** call out places where the
code makes a simplifying assumption or departs from standard/expected behaviour.

---

## 1. Extracting annotations

The plugin accepts two Kindle export formats. Both produce a `ParseResult`
containing a list of `Clipping` objects and statistics about skipped entries.

### 1a. My Clippings.txt (`clippings_parser.py`)

The Kindle appends every highlight, note, and bookmark to a single
`My Clippings.txt` file on the device. The parser splits on the
`==========` separator and extracts fields.

```
Title (Author)
- Your Highlight on page 42 | Location 1024-1031 | Added on Wednesday, January 15, 2025 10:30:45 AM

The highlighted text goes here.
==========
```

**Two-tier parsing strategy:**

1. **English fast path** — An English-only regex (`METADATA_RE`) is tried
   first. This handles the most common case with full field extraction.

2. **Structural fallback** — When the English regex fails (non-English
   Kindles translate the entire metadata line), a structural parser takes
   over. It uses language-agnostic invariants: the `- ` prefix, pipe `|`
   separators, and digit patterns to extract page numbers and location
   ranges. Annotation type is determined by checking words against a
   multilingual keyword table (`_TYPE_KEYWORDS`, covering 15+ languages),
   falling back to content-based inference (empty content = Bookmark,
   non-empty = Highlight).

- **ASSUMPTION — Pipe `|` separators are universal.** The structural
  fallback relies on `|` separating metadata segments. If a Kindle
  locale uses a different delimiter, the fallback will fail and the entry
  will be skipped (but reported in `ParseResult.skipped_samples`).

- **ASSUMPTION — Timestamps may be lost for non-English locales.**
  Python's `strptime` with `%A`/`%B` only matches the system locale's
  day/month names. Without `dateutil` (not bundled with Calibre),
  non-English timestamps will typically fall back to `None`. The
  annotation save code substitutes `datetime.now(UTC)`.

- **ASSUMPTION — Author is in the last parenthesised group.** The regex
  `^(.+)\(([^)]+)\)\s*$` treats the final `(…)` on the title line as the
  author, and everything before it as the title. Books whose titles
  contain parentheses (e.g. "Gödel, Escher, Bach (20th Anniversary
  Edition)") will be misparsed—the edition string becomes the "author."

- **DEVIATION — No deduplication.** The Kindle appends a new entry every
  time a highlight is deleted and re-created, so `My Clippings.txt`
  commonly contains duplicates. The parser does no deduplication; the user
  sees every duplicate in the annotation table.

- **ASSUMPTION — UTF-8 with BOM.** The file is opened as `utf-8-sig` and
  a leading `\ufeff` BOM character is explicitly stripped from the first
  title line. Other encodings will produce garbage or errors.

### 1b. Kindle Notebook HTML (`notebook_parser.py`)

Amazon's "Export Notebook" feature produces an HTML file per book. The
file contains highlights and notes but no timestamps or location ranges.

**Structural parsing:** The parser uses CSS class names (`noteHeading`,
`noteText`, `highlight_COLOR`) rather than English keywords to identify
annotation blocks and types. The presence of a
`<span class='highlight_...'>` tag distinguishes highlights from notes.
Page and location numbers are extracted as digit groups separated by
`&middot;`.

- **DEVIATION — Regex parsing of intentionally malformed HTML.** The
  exported HTML uses mismatched tags (`<h3 class='noteHeading'>…</div>
  <div class='noteText'>…</h3>`). A standards-compliant HTML parser like
  BeautifulSoup would recover this in unpredictable ways, so the parser
  deliberately uses regex.

- **DEVIATION — Page number may be absent.** If the heading contains only
  one number (no middot separator), it is treated as the location with
  `page=None`. The entry is still parsed, but page-guided matching in the
  mapper will be unavailable.

- **DEVIATION — No location range.** The notebook format provides a single
  location, so `location_end` is always set equal to `location_start`.
  This means note-to-highlight pairing (which matches on `location_end`)
  only works when the note's location exactly equals the highlight's
  single location value.

- **DEVIATION — No timestamps.** `Clipping.timestamp` is always `None`.
  The saved Calibre annotation will use `datetime.now(UTC)` as a
  fallback.

### Parse feedback

Both parsers return a `ParseResult` that includes `total_entries`,
`parsed_entries`, `skipped_entries`, and up to 5 `skipped_samples` (raw
text of entries that failed to parse). The UI displays a warning when
entries are skipped, making previously-silent failures visible to the user.

---

## 2. Reading the EPUB

`epub_reader.py` opens the EPUB zip, parses the OPF package document, and
builds an `EpubDocument` containing:

- **spine_files** — the reading-order list of XHTML content files.
- **file_texts** — plain text extracted from each spine file by walking
  the DOM with `lxml.etree.iterwalk`, concatenating `.text` and `.tail`.
- **file_html** — the raw XHTML string for each spine file (used later
  for CFI generation).
- **page_anchors** — page-break markers from two sources (see below).
- **toc_root** — the pre-parsed TOC tree (a `TocEntry` from
  `toc_resolver.py`), used for breadcrumb resolution without re-opening
  the EPUB.

### Page anchor discovery

Page anchors are gathered from two complementary sources:

1. **Inline pagebreak elements** — Elements with `epub:type="pagebreak"`
   found during the DOM walk of each XHTML spine file.

2. **Nav page-list** — The EPUB3 `<nav epub:type="page-list">` document.
   Anchor IDs from the nav page-list are passed to the text extractor so
   their character offsets are recorded during the same DOM walk.

When both sources reference the same element, the nav page-list's display
label (e.g., "42", "iv") is preferred over the heuristic of stripping
`page_` from the element ID.

**Roman numeral support:** Page labels that fail `int()` conversion are
tried as Roman numerals via `_roman_to_int()` (capped at 500 to avoid
false positives). This allows front-matter pages like "iv" → 4 to match
Kindle's integer page numbers.

- **ASSUMPTION — EPUB3 required for page-list.** There is no NCX (EPUB2)
  `<pageList>` fallback. EPUB2-only books with no inline pagebreak
  elements will produce zero page anchors, and page-guided matching will
  fall through to global search.

- **ASSUMPTION — Spine files are valid XHTML parseable by lxml.** Malformed
  content files will raise an exception (no graceful fallback).

- **ASSUMPTION — UTF-8 encoding.** Every spine file is decoded with
  `xhtml_bytes.decode("utf-8")`. XHTML files declaring a different
  encoding in their XML prolog will be decoded incorrectly.

---

## 3. Mapping annotations to EPUB positions

`mapper.py` takes one or more `Clipping` objects and the `EpubDocument` and
attempts to locate each clipping's highlighted text in the EPUB.

### Ordering: highlights first, then notes

All highlights are mapped first, building a lookup table keyed by
`(location_start, location_end)`. Notes and bookmarks are mapped
afterward because they can pair with a previously-matched highlight.

### 3a. Highlight mapping

The mapper normalises the clipping's content text and the EPUB text, then
searches for an exact substring match.

**Text normalisation (`normalize_text`):**

- Replace `\xa0` (non-breaking space) with regular space
- Collapse all whitespace runs to a single space
- Strip leading/trailing whitespace

**Search strategy (in order):**

1. **Page-guided search** — If the clipping has a page number and the EPUB
   has a matching page anchor, search a window around that anchor:
   500 characters before, and either 500 characters past the next page's
   anchor or 5000 characters after the current anchor. Uses `str.find()`
   on the normalised text. Confidence: **1.0**.

2. **Global search** — Iterate every spine file in order and return the
   first normalised `str.find()` match. Confidence: **0.9** if the
   clipping had a page number (meaning page-guided failed), **0.8**
   otherwise.

3. **Punctuation-fix retry** — If both above fail, apply
   `fix_spaced_punctuation` to the needle (removes spaces before
   punctuation, around smart quotes, and around apostrophes—compensating
   for a Kindle extraction quirk) and rerun steps 1–2.

If all three fail, the clipping is unmatched.

- **ASSUMPTION — Exact substring match only.** There is no fuzzy matching,
  edit distance, or longest-common-subsequence fallback. A single
  character difference between the Kindle's extracted text and the EPUB's
  text will cause a miss.

- **ASSUMPTION — First match wins.** Global search returns the first
  occurrence in spine order. If the same passage appears multiple times in
  the book (e.g., an epigraph repeated later), the mapper may match the
  wrong one. No disambiguation is attempted.

- **ASSUMPTION — Page-guided search window is sufficient.** The 500-char
  look-behind and 5000-char lookahead are heuristics. A page break that
  falls mid-sentence could push the highlight just outside the window.

- **DEVIATION — Kindle locations are mostly unused.** The `location_start`
  / `location_end` from the clipping are not used to locate text in the
  EPUB (Kindle locations are a proprietary offset scheme that doesn't map
  to EPUB positions). They are only used for pairing notes to highlights.

### 3b. Note and bookmark mapping

Notes and bookmarks have no highlighted text to search for. The mapper
uses two strategies:

1. **Pair with a highlight** — Find a highlight result whose
   `location_end` equals the note's `location_start` or `location_end`.
   Place the note at the highlight's end position. Confidence: **1.0**.

2. **Page anchor only** — If the note has a page number and a matching
   page anchor exists, place the note at that anchor's character offset.
   Confidence: **0.5**.

- **ASSUMPTION — Note location matches highlight location_end.** This
  pairing heuristic works when the Kindle records the note's location at
  the end of the associated highlight. If the two location values don't
  align exactly, the note falls through to page-anchor-only placement.

### 3c. Offset translation

The mapper works in "normalised text space" (whitespace collapsed) but
needs to produce character offsets in the original XHTML-extracted text
(for CFI generation). Two helper functions handle this:

- `_find_normalized_offset(original_text, original_offset)` — Normalises
  the prefix `original_text[:offset]` and returns its length.

- `_norm_to_original_offset(original_text, norm_offset)` — Walks the
  original text character by character, simulating the normalisation, to
  find the original offset corresponding to a normalised offset.

- **ASSUMPTION — Prefix normalisation is exact.** Normalising a prefix in
  isolation doesn't always produce the same offset as finding the
  corresponding position in the full normalised text, particularly at
  boundaries where leading/trailing whitespace interacts with the prefix
  cut point. This can produce off-by-a-few-characters errors.

---

## 4. Generating EPUB CFIs

`cfi_generator.py` converts a character offset in the extracted plain text
of an XHTML file to an EPUB Canonical Fragment Identifier (CFI).

A CFI is a path like `/4/2/56/1:591` that identifies a precise character
position in the DOM:

- Even steps (`/4`, `/2`, `/56`) navigate to element children.
- Odd steps (`/1`) address text-node slots between/around elements.
- `:591` is the character offset within the text node.
- `[id]` after a step is an ID assertion for robustness.

### Algorithm

1. **Locate the DOM position** (`_find_text_location`) — Walk the DOM with
   the same `iterwalk("start", "end")` traversal used by the EPUB reader's
   text extractor. Count `.text` and `.tail` characters until the
   cumulative offset crosses the target. This identifies: the element, whether
   the target is in its `.text` or `.tail`, and the local character offset
   within that text segment.

2. **Build the CFI path** (`_build_cfi_path`):
   - If the target is in `element.text`: the reference parent is that
     element itself; the text-node step is `/1` (the first child slot,
     before any child elements).
   - If the target is in `element.tail`: the reference parent is the
     element's parent; the text-node step follows the element's CFI index.
   - Walk from root to the reference parent, computing even-numbered child
     indices for each element along the ancestry chain.
   - Append `[id]` assertions where the ID is unique in the document.

3. **The spine prefix is not included.** Calibre stores `spine_index`
   separately in its annotation JSON, so the CFI produced here is the
   within-file path only.

- **ASSUMPTION — The iterwalk traversal in the CFI generator exactly
  matches the epub_reader's text extraction.** Any divergence would map to
  the wrong DOM node. Both use the same `("start", "end")` event pattern
  and the same `.text`/`.tail` concatenation logic. This coupling is
  implicit rather than enforced by shared code.

- **ASSUMPTION — The text offset is in original (un-normalised) text
  space.** The mapper's `_norm_to_original_offset` is responsible for
  converting from normalised offsets back to original ones before CFI
  generation. Any error in that conversion propagates to an incorrect CFI.

---

## 5. Resolving TOC breadcrumbs

`toc_resolver.py` maps a spine file path to a breadcrumb trail of
table-of-contents titles (e.g., `["Part 1", "Chapter 3"]`).

The TOC tree is parsed once during `read_epub` (via `parse_toc_from_zip`)
and stored on `EpubDocument.toc_root`. The resolver then works from this
pre-parsed tree without re-opening the EPUB.

1. Flatten the `TocEntry` tree into `(spine_index, entry)` tuples.
2. Find the last TOC entry whose `spine_index` is <= the target file's
   spine index.
3. Walk up the tree from that entry to the root, collecting titles.

- **ASSUMPTION — EPUB3 nav document exists.** There is no NCX (EPUB2)
  fallback. EPUB2 books return `["Unknown"]`.

- **DEVIATION — File-level granularity only.** The `char_offset` parameter
  is accepted but not yet used in matching. If a single XHTML file
  contains multiple chapters (each with its own TOC entry via fragment
  identifiers), the resolver picks the last TOC entry referencing that
  file, which may not be the correct chapter.

---

## 6. Storing annotations in Calibre

`main.py` orchestrates the full pipeline and stores the result using
Calibre's annotation API.

### Annotation JSON structure

```json
{
  "type": "highlight",
  "uuid": "<first 22 hex chars of a UUID4>",
  "highlighted_text": "<original clipping text>",
  "start_cfi": "/4/2/56/1:591",
  "end_cfi": "/4/2/56/1:623",
  "spine_index": 5,
  "spine_name": "OEBPS/Text/chapter03.xhtml",
  "style": { "kind": "color", "type": "builtin", "which": "yellow" },
  "timestamp": "2025-01-15T10:30:45.000Z",
  "toc_family_titles": ["Part 1", "Chapter 3"],
  "notes": "Optional note content"
}
```

- **`highlighted_text`** preserves the original text from the Kindle
  clipping. For standalone notes (no associated highlight), this is an
  empty string and the note text is stored in `notes` instead.

- **`timestamp`** uses the clipping's parsed timestamp, or falls back to
  `datetime.now(UTC)` for Notebook-format clippings or non-English
  clippings where the timestamp could not be parsed.

- **`style`** is initially set to yellow, then replaced with the user's
  chosen colour from the `HighlightColorCombo` at save time via
  `style_definition_for_name()`.

- **`notes`** is populated from paired notes or standalone note content.

### Note handling

Notes are paired with highlights by matching
`(book_title, highlight.location_end) == (book_title, note.location_start)`.
Paired notes appear in the "Note" column of the highlight's row.

Unpaired (standalone) notes that don't match any highlight are shown as
their own rows at the bottom of the annotation table. When saved, they
are stored as zero-length highlights (`start_cfi == end_cfi`) with the
note text in the `notes` field. Calibre's viewer renders these as
position markers.

### Saving to the database

The annotation dict is passed to `db.merge_annotations_for_book()`, which
is Calibre's built-in method for upserting viewer annotations. The
annotation is stored with `user_type="local"` and `user="viewer"`, making
it indistinguishable from one created by Calibre's built-in EPUB viewer.

- **DEVIATION — One annotation at a time.** There is no batch import. The
  user must select an annotation, click "Find annotation" to map it, then
  click "Save to Calibre." This must be repeated for every annotation.

- **DEVIATION — EPUB target format only.** Only books with an EPUB format
  in the Calibre library are shown. AZW3, MOBI, KFX, and other formats
  are unsupported as mapping targets.

- Duplicate detection compares `start_cfi` and `end_cfi` against existing
  annotations. If a duplicate is found, the user is warned but not
  prevented from saving.

---

## End-to-end data flow

```
My Clippings.txt ───┐
                    ├──> ParseResult  ──> [Clipping] ──┐
Notebook HTML ──────┘     (+ skip stats)               │
                                                       │  map_clippings()
EPUB file ──> EpubDocument ────────────────────────────┤
              (+ toc_root, page_anchors from           │
               inline pagebreaks + nav page-list)      │
                                                       ▼
                                                MappingResult
                                          (file_path, char_offsets)
                                                       │
                                        ┌──────────────┼──────────────┐
                                        │              │              │
                                  generate_cfi   resolve_toc    build annotation
                                  (start, end)   (from toc_root)     JSON
                                        │              │              │
                                        └──────────────┴──────────────┘
                                                       │
                                                       ▼
                                         db.merge_annotations_for_book()
```
