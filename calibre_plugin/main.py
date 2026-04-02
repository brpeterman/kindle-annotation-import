"""Main dialog for the Kindle Annotation Import plugin."""

import json
import uuid as uuid_mod
from datetime import datetime, timezone

from qt.core import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QTextEdit,
    QAbstractItemView,
    QDialogButtonBox,
    QLineEdit,
    QSplitter,
    Qt,
)

from calibre.gui2 import choose_files, error_dialog
from calibre.gui2.viewer.highlights import (
    HighlightColorCombo,
    style_definition_for_name,
)

from calibre_plugins.kindle_annotation_import.clippings_parser import parse_clippings
from calibre_plugins.kindle_annotation_import.notebook_parser import parse_notebook
from calibre_plugins.kindle_annotation_import.epub_reader import read_epub
from calibre_plugins.kindle_annotation_import.mapper import map_clippings
from calibre_plugins.kindle_annotation_import.cfi_generator import generate_cfi
from calibre_plugins.kindle_annotation_import.toc_resolver import (
    resolve_toc_titles_from_doc,
)
from calibre_plugins.kindle_annotation_import.models import ClippingType


class ImportDialog(QDialog):
    def __init__(self, gui):
        super().__init__(gui)
        self.gui = gui
        self.db = gui.current_db.new_api
        self.clippings = []
        self.display_entries = []  # list of (highlight_clip, paired_note_or_None)
        self._all_books = []  # list of (book_id, title, authors_str)
        self._pending_annot = None
        self._pending_book_id = None

        self.setWindowTitle("Kindle Annotation Import")
        self.resize(900, 750)
        self._build_ui()
        self._load_books()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # --- File selection ---
        file_row = QHBoxLayout()
        self.btn_select_file = QPushButton("Select Annotations File...")
        self.btn_select_file.clicked.connect(self._on_select_file)
        self.lbl_file_path = QLabel("No file selected")
        file_row.addWidget(self.btn_select_file)
        file_row.addWidget(self.lbl_file_path, 1)
        layout.addLayout(file_row)

        # --- Splitter: annotations (top) + book selection (bottom) ---
        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, 1)

        # Annotations table
        annot_widget = QDialog(self)  # plain container widget
        annot_widget.setWindowFlags(Qt.WindowType.Widget)
        annot_layout = QVBoxLayout(annot_widget)
        annot_layout.setContentsMargins(0, 0, 0, 0)
        annot_layout.addWidget(QLabel("Annotations:"))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Book", "Type", "Page", "Content", "Note"]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(1, 70)
        self.table.setColumnWidth(2, 50)
        annot_layout.addWidget(self.table)
        splitter.addWidget(annot_widget)

        # Book selection
        book_widget = QDialog(self)
        book_widget.setWindowFlags(Qt.WindowType.Widget)
        book_layout = QVBoxLayout(book_widget)
        book_layout.setContentsMargins(0, 0, 0, 0)
        book_layout.addWidget(QLabel("Library Book (EPUB):"))
        self.book_search = QLineEdit()
        self.book_search.setPlaceholderText("Filter books...")
        self.book_search.textChanged.connect(self._filter_books)
        book_layout.addWidget(self.book_search)
        self.book_table = QTableWidget(0, 2)
        self.book_table.setHorizontalHeaderLabels(["Title", "Authors"])
        self.book_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.book_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.book_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.book_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.book_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.book_table.horizontalScrollBar().setEnabled(False)
        self.book_table.setMinimumHeight(150)
        book_layout.addWidget(self.book_table)

        # Find button
        self.btn_find = QPushButton("&Find annotation")
        self.btn_find.clicked.connect(self._on_map)
        book_layout.addWidget(self.btn_find)

        splitter.addWidget(book_widget)

        splitter.setSizes([450, 200])

        # --- Output area ---
        layout.addWidget(QLabel("Output:"))
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumHeight(200)
        layout.addWidget(self.output)

        # --- Style picker + Save row ---
        action_row = QHBoxLayout()
        self.style_combo = HighlightColorCombo(self)
        self.btn_save = QPushButton("&Save to Calibre")
        self.btn_save.clicked.connect(self._on_save)
        self.btn_save.setEnabled(False)
        action_row.addWidget(self.style_combo)
        action_row.addWidget(self.btn_save, 1)
        layout.addLayout(action_row)

        # --- Close button ---
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _load_books(self):
        for book_id in sorted(self.db.all_book_ids()):
            fmts = self.db.formats(book_id)
            if fmts and "EPUB" in fmts:
                title = self.db.field_for("title", book_id)
                authors = self.db.field_for("authors", book_id)
                author_str = ", ".join(authors) if authors else ""
                self._all_books.append((book_id, title, author_str))
        self._filter_books("")

    def _filter_books(self, query):
        self.book_table.setRowCount(0)
        q = query.lower()
        for book_id, title, authors in self._all_books:
            if not q or q in title.lower() or q in authors.lower():
                row = self.book_table.rowCount()
                self.book_table.insertRow(row)
                title_item = QTableWidgetItem(title)
                authors_item = QTableWidgetItem(authors)
                title_item.setData(Qt.ItemDataRole.UserRole, book_id)
                self.book_table.setItem(row, 0, title_item)
                self.book_table.setItem(row, 1, authors_item)

    def _on_select_file(self):
        paths = choose_files(
            self,
            "kindle-annotations-file",
            "Select Kindle Annotations File",
            filters=[("Kindle Annotations", ["txt", "html"])],
            select_only_single_file=True,
        )
        if not paths:
            return

        path = paths[0]
        self.lbl_file_path.setText(path)

        try:
            if path.lower().endswith(".html"):
                result = parse_notebook(path)
            else:
                result = parse_clippings(path)
        except Exception as e:
            error_dialog(
                self, "Parse Error", f"Failed to parse annotations: {e}", show=True
            )
            return

        self.clippings = result.clippings
        self._populate_table()

        if result.skipped_entries > 0:
            self.output.clear()
            self.output.append(
                f"Parsed {result.parsed_entries} of {result.total_entries} entries. "
                f"{result.skipped_entries} could not be parsed."
            )
            if result.skipped_samples:
                self.output.append("\nSample skipped entries:")
                for sample in result.skipped_samples:
                    self.output.append(f"  {sample[:120]}")

    def _populate_table(self):
        # Build a map from (book_title, location_start) -> note for pairing
        notes_by_loc = {}
        for c in self.clippings:
            if c.clipping_type == ClippingType.NOTE:
                notes_by_loc[(c.book_title, c.location_start)] = c

        # Build display entries: highlights and bookmarks (notes paired in)
        self.display_entries = []
        paired_note_keys = set()
        for c in self.clippings:
            if c.clipping_type == ClippingType.HIGHLIGHT:
                key = (c.book_title, c.location_end)
                paired_note = notes_by_loc.get(key)
                self.display_entries.append((c, paired_note))
                if paired_note:
                    paired_note_keys.add(key)
            elif c.clipping_type == ClippingType.BOOKMARK:
                self.display_entries.append((c, None))

        # Surface unpaired standalone notes at the end of the table
        for c in self.clippings:
            if c.clipping_type == ClippingType.NOTE:
                key = (c.book_title, c.location_start)
                if key not in paired_note_keys:
                    self.display_entries.append((c, None))

        self.table.setRowCount(len(self.display_entries))
        for i, (clip, note) in enumerate(self.display_entries):
            self.table.setItem(i, 0, QTableWidgetItem(clip.book_title))
            self.table.setItem(i, 1, QTableWidgetItem(clip.clipping_type.value))
            self.table.setItem(
                i, 2, QTableWidgetItem(str(clip.page) if clip.page else "")
            )
            content = (
                clip.content[:100] + "..." if len(clip.content) > 100 else clip.content
            )
            self.table.setItem(i, 3, QTableWidgetItem(content))
            note_text = ""
            if note:
                note_text = (
                    note.content[:100] + "..."
                    if len(note.content) > 100
                    else note.content
                )
            self.table.setItem(i, 4, QTableWidgetItem(note_text))

    def _on_map(self):
        # Validate annotation selection
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            error_dialog(
                self,
                "No Selection",
                "Please select an annotation from the table.",
                show=True,
            )
            return

        # Validate book selection
        book_rows = self.book_table.selectionModel().selectedRows()
        if not book_rows:
            error_dialog(
                self,
                "No Book",
                "Please select a library book from the table.",
                show=True,
            )
            return

        row_idx = rows[0].row()
        clip, paired_note = self.display_entries[row_idx]
        book_row = book_rows[0].row()
        selected_book_id = self.book_table.item(book_row, 0).data(
            Qt.ItemDataRole.UserRole
        )

        # Check the book has EPUB format
        fmts = self.db.formats(selected_book_id)
        if not fmts or "EPUB" not in fmts:
            error_dialog(
                self,
                "No EPUB",
                "The selected book does not have an EPUB format.",
                show=True,
            )
            return

        self.output.clear()
        self._pending_annot = None
        self._pending_book_id = None
        self.btn_save.setEnabled(False)
        self.output.append(f"Mapping: {clip.clipping_type.value} on page {clip.page}")
        self.output.append(f"Content: {clip.content[:80]}...")

        try:
            epub_bytes = self.db.format(selected_book_id, "EPUB")
            if not epub_bytes:
                error_dialog(
                    self, "Read Error", "Could not read EPUB from library.", show=True
                )
                return

            epub = read_epub(epub_bytes)

            # Map the highlight against the EPUB
            results = map_clippings([clip], epub)
            result = results[0]

            if not result.matched:
                self.output.append("\nFailed to map annotation to EPUB position.")
                self.output.append("The highlighted text was not found in the book.")
                return

            self.output.append(f"\nMatched in: {result.file_path}")
            self.output.append(
                f"Method: {result.match_method} (confidence {result.confidence})"
            )

            # Find the text offset in the original (non-normalized) text for CFI generation
            orig_start = result.char_offset_start
            orig_end = result.char_offset_end

            xhtml = epub.file_html[result.file_path].encode("utf-8")
            start_cfi = generate_cfi(xhtml, orig_start)
            end_cfi = generate_cfi(xhtml, orig_end)

            if not start_cfi or not end_cfi:
                self.output.append(
                    "\nError: Could not generate CFI for the matched position."
                )
                return

            spine_index = epub.spine_files.index(result.file_path)
            toc_titles = resolve_toc_titles_from_doc(
                epub, result.file_path, result.char_offset_start or 0
            )
            book_title = self.db.field_for("title", selected_book_id)

            # Build annotation JSON (for console output)
            is_standalone_note = (
                clip.clipping_type == ClippingType.NOTE and paired_note is None
            )
            # Use punctuation-corrected text when the Kindle export had bad spacing
            highlight_text = result.corrected_text or clip.content
            annot = {
                "type": "highlight",
                "uuid": uuid_mod.uuid4().hex[:22],
                "highlighted_text": "" if is_standalone_note else highlight_text,
                "start_cfi": start_cfi,
                "end_cfi": end_cfi,
                "spine_index": spine_index,
                "spine_name": result.file_path,
                "style": {"kind": "color", "type": "builtin", "which": "yellow"},
                "timestamp": (clip.timestamp or datetime.now(timezone.utc))
                .replace(tzinfo=timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "toc_family_titles": toc_titles,
            }

            if is_standalone_note:
                annot["notes"] = clip.content
            elif paired_note:
                annot["notes"] = paired_note.content

            # Print JSON to console
            json_str = json.dumps(annot, indent=2, ensure_ascii=False)
            print(json_str)

            # Store for Save to Calibre
            self._pending_annot = annot
            self._pending_book_id = selected_book_id
            self.btn_save.setEnabled(True)

            # Check for existing duplicate annotation
            existing_annots = self.db.annotations_map_for_book(
                selected_book_id, "EPUB", user_type="local", user="viewer"
            )
            duplicate_found = False
            if "highlight" in existing_annots:
                for existing in existing_annots["highlight"]:
                    if (
                        existing.get("start_cfi") == start_cfi
                        and existing.get("end_cfi") == end_cfi
                    ):
                        duplicate_found = True
                        break

            # Display human-readable summary in output area
            self.output.clear()
            self.output.append(f"✓ Annotation found in: {book_title}\n")

            # Warn if duplicate
            if duplicate_found:
                self.output.append(
                    "⚠ Duplicate found: This annotation already exists in your library.\n"
                )

            # Highlight preview
            preview = (
                clip.content[:120] + "..." if len(clip.content) > 120 else clip.content
            )
            self.output.append(f"Highlight: {preview}\n")

            # Location info
            if clip.page:
                self.output.append(f"Original Kindle page: {clip.page}")
            if toc_titles:
                self.output.append(f"Location: {' > '.join(toc_titles)}")
            else:
                self.output.append("Location: (no TOC entry)")

            # Timestamp
            if clip.timestamp:
                self.output.append(f"\nHighlighted on: {clip.timestamp}")

            # Note if present
            if paired_note:
                note_preview = (
                    paired_note.content[:100] + "..."
                    if len(paired_note.content) > 100
                    else paired_note.content
                )
                self.output.append(f"\nNote: {note_preview}")

        except Exception as e:
            import traceback

            self.output.append(f"\nError: {e}")
            self.output.append(traceback.format_exc())

    def _on_save(self):
        annot = dict(self._pending_annot)
        annot["style"] = style_definition_for_name(
            self.style_combo.highlight_style_name
        )

        try:
            self.db.merge_annotations_for_book(self._pending_book_id, "EPUB", [annot])
            self.output.append("\n✓ Saved to Calibre library.")
            self._pending_annot = None
            self._pending_book_id = None
            self.btn_save.setEnabled(False)
        except Exception as e:
            import traceback

            self.output.append(f"\nError saving: {e}")
            self.output.append(traceback.format_exc())
