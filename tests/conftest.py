"""Configure import paths so plugin modules resolve without Calibre installed."""

import sys
import types
from pathlib import Path

# Run this before any test imports happen (conftest.py is loaded first by pytest).

root = Path(__file__).parent.parent
plugin_dir = root / "calibre_plugin"

# --- Stub the Calibre namespace that pdf_notebook_parser imports from ---
calibre_mod = types.ModuleType("calibre")
calibre_mod.__path__ = []
calibre_ebooks = types.ModuleType("calibre.ebooks")
calibre_ebooks.__path__ = []
calibre_pdf = types.ModuleType("calibre.ebooks.pdf")
calibre_pdf.__path__ = []
calibre_pdftohtml = types.ModuleType("calibre.ebooks.pdf.pdftohtml")
calibre_pdftohtml.PDFTOTEXT = "pdftotext"  # stub constant

sys.modules.setdefault("calibre", calibre_mod)
sys.modules.setdefault("calibre.ebooks", calibre_ebooks)
sys.modules.setdefault("calibre.ebooks.pdf", calibre_pdf)
sys.modules.setdefault("calibre.ebooks.pdf.pdftohtml", calibre_pdftohtml)

# --- Make "calibre_plugins.kindle_annotation_import" resolve to calibre_plugin/ ---
calibre_plugins = types.ModuleType("calibre_plugins")
calibre_plugins.__path__ = []
sys.modules.setdefault("calibre_plugins", calibre_plugins)

kai = types.ModuleType("calibre_plugins.kindle_annotation_import")
kai.__path__ = [str(plugin_dir)]
sys.modules.setdefault("calibre_plugins.kindle_annotation_import", kai)
