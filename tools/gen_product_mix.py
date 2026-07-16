"""Generate data/product_mix.csv (66-row DISC product table).

PROVENANCE NOTE
---------------
The original Arena Scenario 3 experiment file (`senaryo3_exp_dosyası.txt`,
block 203$) that holds the authoritative 66-row DISC table was not available
in this repository. This script synthesizes a *calibrated stand-in* table that

  * keeps the one documented row verbatim as row 1: (0.06246, 15125261778),
  * follows the exact product-code encoding decoded by the model:
        code = glass1*1e10 + glass2*1e9 + glass3*1e7 + width*1e4 + height
  * uses glass3 == 12 for every row (double-glazed products). The Arena
    reference run is only consistent with an (almost) all-double mix: the
    sequencer's Arena-faithful "2x" feed threshold strands one third of the
    units of any triple-pane order and would deadlock the strict IGU order
    gate, which the reference results (33k IGUs, 94% IGU utilisation over the
    full run) rule out,
  * targets ~0.74 m^2 mean piece area (so jumbo count and fill match the
    reference band) and pane-type shares of roughly 25% bypass / 43%
    furnace-1050 / 32% furnace-1600 glass instances.

When the real 203$ table becomes available, drop it into
data/product_mix.csv (same two columns: cum_prob, code) or upload it through
the Parameters screen — nothing else needs to change.
"""
from __future__ import annotations

import csv
import pathlib

import numpy as np

OUT = pathlib.Path(__file__).resolve().parents[1] / "data" / "product_mix.csv"
N_ROWS = 66
GLASS3_DOUBLE = 12

# Pane-type pools by furnace routing (vFurnaceOf = [2,0,1,2,0,0,1,1,2,1,2,0])
BYPASS_1 = [2, 5, 6, 12]
F1050_1 = [3, 7, 8, 10]
F1600_1 = [1, 4, 9, 11]
BYPASS_2 = [2, 5, 6]          # glass2 is a single digit (1..9)
F1050_2 = [3, 7, 8]
F1600_2 = [1, 4, 9]
ROUTE_P = [0.25, 0.43, 0.32]  # bypass / furnace-1050 / furnace-1600 instance shares


def encode(g1: int, g2: int, g3: int, w: int, h: int) -> int:
    return g1 * 10**10 + g2 * 10**9 + g3 * 10**7 + w * 10**4 + h


def main() -> None:
    rng = np.random.default_rng(20260716)

    # Row weights: first row fixed at the documented 0.06246.
    rest = rng.gamma(1.2, 1.0, N_ROWS - 1)
    rest = rest / rest.sum() * (1.0 - 0.06246)
    weights = np.concatenate([[0.06246], rest])

    rows: list[tuple[float, int]] = []
    # Documented row 1: glass1=1, glass2=5, glass3=12, 526 x 1778 mm.
    rows.append((0.06246, 15125261778))

    for _ in range(N_ROWS - 1):
        route1 = rng.choice(3, p=ROUTE_P)
        route2 = rng.choice(3, p=ROUTE_P)
        g1 = int(rng.choice([BYPASS_1, F1050_1, F1600_1][route1]))
        g2 = int(rng.choice([BYPASS_2, F1050_2, F1600_2][route2]))
        # Piece area ~ lognormal around 0.72 m^2, clipped to realistic IGU sizes.
        area = float(np.clip(rng.lognormal(np.log(0.82), 0.45), 0.30, 2.2))
        width = int(rng.integers(360, 980))
        height = int(round(area * 1e6 / width))
        height = max(400, min(height, 3100))
        rows.append((0.0, encode(g1, g2, GLASS3_DOUBLE, width, height)))

    cum = np.cumsum(weights)
    cum[-1] = 1.0
    out_rows = [(round(float(c), 5), code) for c, (_, code) in zip(cum, rows)]
    # enforce strict monotonicity after rounding
    for i in range(1, N_ROWS):
        if out_rows[i][0] <= out_rows[i - 1][0]:
            out_rows[i] = (out_rows[i - 1][0] + 0.00001, out_rows[i][1])
    out_rows[-1] = (1.0, out_rows[-1][1])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cum_prob", "code"])
        w.writerows(out_rows)
    print(f"wrote {OUT} ({len(out_rows)} rows)")


if __name__ == "__main__":
    main()
