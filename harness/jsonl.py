"""A run's records (ADR-008) as the scripts read and write them: JSON Lines, one record a
line. A file that isn't there holds no records."""

import json
from pathlib import Path
from typing import Any, cast

Records = list[dict[str, Any]]


def read(path: Path) -> Records:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [cast("dict[str, Any]", json.loads(line)) for line in lines if line.strip()]


def write(path: Path, records: Records) -> None:
    text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    path.write_text(text, encoding="utf-8")
