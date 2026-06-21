from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


class CsvAdapter:
    def read(self, path: Path) -> list[dict[str, Any]]:
        with path.open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))

    def write(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = sorted({key for row in rows for key in row})
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)


class JsonAdapter:
    def read(self, path: Path) -> list[dict[str, Any]]:
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".jsonl":
            return [json.loads(line) for line in text.splitlines() if line.strip()]
        payload = json.loads(text)
        if isinstance(payload, list):
            return payload
        return [payload]

    def write(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".jsonl":
            path.write_text(
                "\n".join(json.dumps(row, sort_keys=True, ensure_ascii=False) for row in rows)
                + "\n",
                encoding="utf-8",
            )
            return
        path.write_text(
            json.dumps(rows, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )


class ParquetAdapter:
    """Parquet-shaped adapter with a deterministic JSON fallback for offline foundation tests."""

    def read(self, path: Path) -> list[dict[str, Any]]:
        payload = json.loads(path.read_bytes().decode("utf-8"))
        if payload.get("format") != "stage5-parquet-fallback-v1":
            raise ValueError("unsupported parquet fallback payload")
        return list(payload["rows"])

    def write(self, path: Path, rows: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"format": "stage5-parquet-fallback-v1", "rows": rows}
        path.write_bytes(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8"))
