#!/usr/bin/env python3
"""Build script: packages calibre_plugin/ into a Calibre plugin zip file."""

import zipfile
from pathlib import Path

PLUGIN_DIR = Path(__file__).parent / "calibre_plugin"
OUTPUT_FILE = Path(__file__).parent / "Kindle_Annotation_Import.zip"


def build():
    files = [f for f in PLUGIN_DIR.iterdir() if f.is_file()]

    with zipfile.ZipFile(OUTPUT_FILE, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(files):
            zf.write(f, f.name)
            print(f"  added: {f.name}")

    print(f"\nBuilt: {OUTPUT_FILE.name} ({OUTPUT_FILE.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
