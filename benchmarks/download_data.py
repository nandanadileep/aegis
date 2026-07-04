#!/usr/bin/env python3
"""Download LongMemEval-S cleaned dataset."""
from __future__ import annotations

import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "benchmarks" / "data"
URL = "https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json"
OUT = DATA_DIR / "longmemeval_s_cleaned.json"


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        print(f"Already exists: {OUT}")
        return
    print(f"Downloading {URL} ...")
    resp = requests.get(URL, timeout=120)
    resp.raise_for_status()
    OUT.write_bytes(resp.content)
    print(f"Saved {OUT} ({len(resp.content) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
