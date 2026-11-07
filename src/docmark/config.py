from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DATA_DIR = Path.cwd() / "data"
DATA_DIR = Path(os.getenv("DOCMARK_DATA_DIR", str(DEFAULT_DATA_DIR))).resolve()
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"

MAX_UPLOAD_MB = max(1, int(os.getenv("DOCMARK_MAX_UPLOAD_MB", "30")))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
ALLOWED_EXTENSIONS = {".docx", ".pdf"}
