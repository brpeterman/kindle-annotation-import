# Kindle Annotation Import — User Guide

A Calibre plugin that imports your Kindle highlights and notes into Calibre's native annotation system, where they can be viewed alongside your books.

## Requirements

- Calibre 7.0 or later
- The book you are importing into must have an **EPUB** format in your Calibre library

## Installation

1. Download `Kindle_Annotation_Import.zip`.
2. In Calibre, open **Preferences → Plugins**.
3. Click **Load plugin from file** and select the zip file.
4. Restart Calibre.

A new **Import Kindle Annotations** action will appear in the toolbar (or under the **Plugins** menu).

## Getting Your Annotations Off the Kindle

Two export formats are supported:

### My Clippings.txt

Found on the Kindle device itself. Connect your Kindle via USB and copy the file from:

```
Kindle/documents/My Clippings.txt
```

This file contains all your highlights, notes, and bookmarks across every book, with timestamps.

### Notebook HTML export

Available through the Kindle app or the Share feature on newer Kindle devices. This produces a file named `<Book Title>-Notebook.html`. It contains only highlights and notes for a single book, without timestamps.

## Importing Annotations

1. Click **Import Kindle Annotations** in the Calibre toolbar.
2. Click **Select Annotations File** and choose your `.txt` or `.html` export file.
   - The annotations table will populate with all highlights and notes found in the file.
3. Select the annotation row you want to import.
4. In the book list at the bottom, find and select the matching book in your Calibre library.
   - Use the search box to filter by title or author.
5. Click **Find annotation** to locate the highlight text in the book's EPUB.
   - A summary appears showing the matched chapter and a snippet of the surrounding text.
6. Choose a highlight style from the colour picker.
7. Click **Save to Calibre** to write the annotation.

Repeat steps 3–7 for each annotation you want to import.

## Viewing Imported Annotations

Open the book in Calibre's built-in viewer. Your imported highlights will appear highlighted in the text. Open the viewer's bookmarks/annotations panel to browse them.

## What Gets Imported

| Feature                         | Supported                                          |
| ------------------------------- | -------------------------------------------------- |
| Highlights                      | Yes                                                |
| Notes paired to a highlight     | Yes (stored as the annotation's note)              |
| Standalone notes (no highlight) | No                                                 |
| Bookmarks                       | Partial (saved as a position, no highlighted text) |
| Multiple books in one file      | Yes — filter by book in the annotations table      |

## Troubleshooting

**"Find annotation" reports no match**

The plugin searches for your exact highlight text inside the EPUB. Matches can fail when:

- The book in Calibre is a different edition from the one you read on the Kindle.
- The Kindle truncated a very long highlight.
- The EPUB uses unusual Unicode characters or ligatures that differ from what Kindle captured.

These are limitations of the plugin and can't be worked around. You'll need to manually enter your highlight using Calibre's native features.

**The annotations table is empty after loading a file**

Check that you selected the correct file type. `My Clippings.txt` must be the raw file from the Kindle device (UTF-8 with BOM). The Notebook HTML file must be the `.html` export, not a printed PDF.

**The book does not appear in the book list**

Only books with an EPUB format are shown. In Calibre, select the book, right-click → **Add books → Add empty book** or use **Convert books** to produce an EPUB from another format.
