"""Extract the 66-row DISC product table verbatim from the Arena mod file
(block 203$) into data/product_mix.csv."""
from __future__ import annotations

import csv
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
MOD = ROOT / "docs" / "arena" / "senaryo3_mod_dosyasi.txt"
OUT = ROOT / "data" / "product_mix.csv"


def main() -> None:
    src = MOD.read_text()
    m = re.search(r"DISC\((.*?)\):", src, re.S)
    if not m:
        raise SystemExit("DISC block not found in mod file")
    pairs = re.findall(r"([\d.]+)\s*,\s*(\d{10,12})", m.group(1))
    rows = [(float(p), int(c)) for p, c in pairs]
    if len(rows) != 66 or rows[-1][0] != 1.0:
        raise SystemExit(f"unexpected table: {len(rows)} rows, last cum {rows[-1][0]}")
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cum_prob", "code"])
        w.writerows(rows)
    print(f"wrote {OUT} ({len(rows)} rows, verbatim from {MOD.name})")


if __name__ == "__main__":
    main()
