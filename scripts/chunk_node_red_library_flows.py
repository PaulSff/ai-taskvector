#!/usr/bin/env python3
"""
Chunk node-red-library-flows-refined.json into one file per flow.

Top-level structure: array of objects, each with _id, url, created_at, updated_at, flow.
Writes each object to mydata/node-red/workflows/node-red-library-flows-refined/<_id>.json
"""
from pathlib import Path

import json

SRC = Path(__file__).resolve().parents[1] / "mydata/node-red/workflows/node-red-library-flows-refined.json"
OUT_DIR = Path(__file__).resolve().parents[1] / "mydata/node-red/workflows/node-red-library-flows-refined"


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"Source not found: {SRC}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Loading {SRC}...")
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise SystemExit("Expected top-level array")
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        fid = item.get("_id") or str(i)
        # sanitize for filename
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(fid))[:64]
        path = OUT_DIR / f"{safe}.json"
        with open(path, "w", encoding="utf-8") as out:
            json.dump(item, out, indent=2, ensure_ascii=False)
        if (i + 1) % 500 == 0:
            print(f"  wrote {i + 1}/{len(data)}")
    print(f"Wrote {len(data)} flows to {OUT_DIR}")


if __name__ == "__main__":
    main()
