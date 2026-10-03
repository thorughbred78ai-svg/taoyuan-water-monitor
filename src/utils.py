from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def save_json(path: Path, data: Any) -> None:
    """Atomic UTF-8 JSON write (avoids half-written files)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
