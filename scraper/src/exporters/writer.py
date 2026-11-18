from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable


def prepare_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "csv").mkdir(exist_ok=True)


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            normalized = {}
            for key, value in row.items():
                normalized[key] = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
            writer.writerow(normalized)
