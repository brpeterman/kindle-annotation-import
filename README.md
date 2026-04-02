# Kindle Annotation Import — Developer README

A Calibre plugin that imports Kindle highlights and notes into Calibre's native annotation system.

## Repository Layout

```
kindle-annotation-import/
├── build_plugin.py          # Build script — produces the installable zip
├── calibre_plugin/          # All plugin source (installed into Calibre)
│   ├── __init__.py          # Plugin metadata (name, version, min Calibre version)
│   ├── ui.py                # Calibre InterfaceAction entry point
│   ├── main.py              # ImportDialog — the main UI and orchestration logic
│   ├── models.py            # Shared dataclasses (Clipping, EpubDocument, MappingResult, …)
│   ├── clippings_parser.py  # Parser for "My Clippings.txt"
│   ├── notebook_parser.py   # Parser for "*-Notebook.html" Kindle exports
│   ├── epub_reader.py       # EPUB reader — extracts spine text and page anchors
│   ├── mapper.py            # Maps clippings to character offsets in the EPUB
│   ├── cfi_generator.py     # Converts character offsets to EPUB CFI strings
│   ├── toc_resolver.py      # Resolves a spine location to a TOC breadcrumb path
│   └── plugin-import-name-kindle_annotation_import.txt
├── tests                    # Unit tests
```

## Building the Plugin

Run the build script from the project root. It requires only the Python standard library and works on Windows, Linux, and macOS:

```
python build_plugin.py
```

This packages every file in `calibre_plugin/` flat into `Kindle_Annotation_Import.zip` in the project root. That zip is the file you install into Calibre.

## Development Workflow

### Import conventions

| Directory         | Import style                                                    |
| ----------------- | --------------------------------------------------------------- |
| `calibre_plugin/` | `from calibre_plugins.kindle_annotation_import.models import …` |

### Unit tests

1. Create a venv:
   ```sh
   python -m venv .venv
   ```
2. Activate the venv:

   ```sh
   # sh
   source .venv/bin/activate

   # Windows cmd
   .\.venv\Scripts\activate
   ```

3. Install dependencies:
   ```sh
   pip install .
   ```
4. Run tests:
   ```sh
   pytest
   ```

### Testing inside Calibre

#### Ad hoc testing

To install the plugin without packaging and importing it:

```sh
calibre-debug -s; calibre-customize -b ./calibre_plugin
```

Start up Calibre and the latest plugin code should be loaded.

#### Release testing

After editing, rebuild the zip and reinstall:

1. `python build_plugin.py`
2. In Calibre: **Preferences → Plugins → Load plugin from file** → select `Kindle_Annotation_Import.zip`
3. Restart Calibre.

Plugin `print()` output is visible in the Calibre debug console (`calibre-debug -g`).

## Module Overview

| Module                   | Responsibility                                                    |
| ------------------------ | ----------------------------------------------------------------- |
| `clippings_parser.py`    | Parses `My Clippings.txt` into `list[Clipping]`                   |
| `notebook_parser.py`     | Parses `*-Notebook.html` into `list[Clipping]`                    |
| `pdf_notebook_parser.py` | Parses `Notebook - *.pdf` into `list[Clipping]`                   |
| `epub_reader.py`         | Opens an EPUB, builds plain-text per spine file + page anchors    |
| `mapper.py`              | Matches each `Clipping` to a character offset in the EPUB text    |
| `cfi_generator.py`       | Converts a character offset to an EPUB CFI path string            |
| `toc_resolver.py`        | Maps a spine file to a TOC breadcrumb list                        |
| `main.py`                | Dialog UI — wires everything together, writes Calibre annotations |

## Known Limitations

- **One annotation at a time** — there is no batch import mode.
- **EPUB targets only** — the book in Calibre must have an EPUB format.
- **Exact text matching** — the mapper does a substring search. If the Kindle highlight was truncated, or the EPUB is a different edition, the match will fail.
- **English locale timestamps** — `My Clippings.txt` timestamps are parsed with English month/weekday names. Files produced on a non-English Kindle will fail to parse the timestamp.
- **EPUB3 page lists only** — page-guided matching requires an EPUB3 nav page-list or `epub:type="pagebreak"` anchors.
