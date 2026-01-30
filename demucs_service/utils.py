from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path


_INVALID_FILENAME = re.compile(r"[^a-zA-Z0-9._-]+")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_filename(name: str) -> str:
    cleaned = _INVALID_FILENAME.sub("_", name.strip())
    return cleaned or "file"


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=str(path.parent)
    ) as temp_file:
        json.dump(data, temp_file, indent=2, sort_keys=True)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_path = Path(temp_file.name)
    os.replace(temp_path, path)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", delete=False, dir=str(path.parent)) as temp_file:
        temp_file.write(data)
        temp_file.flush()
        os.fsync(temp_file.fileno())
        temp_path = Path(temp_file.name)
    os.replace(temp_path, path)
