"""[SUPERSEDED] Synthetic product-mix generator - kept for history only.

The authoritative 66-row DISC table is now shipped verbatim in
data/product_mix.csv, extracted from the real Arena mod file (203$ block,
see docs/arena/senaryo3_mod_dosyasi.txt). Do NOT run this script unless you
deliberately want to overwrite the real table with a synthetic one; restore
the real table afterwards with tools/extract_product_mix.py.

Original synthesis notes: this script produced a calibrated stand-in that

  * keeps the one documented row verbatim as row 1: (0.06246, 15125261778),
  * follows the exact product-code encoding decoded by the model:
        code = glass1*1e10 + glass2*1e9 + glass3*1e7 + width*1e4 + height
  * uses glass3 == 12 for every row (double-glazed products). The Arena
    reference run is only consistent with an (almost) all-double mix: the
    sequencer's Arena-faithful "2x" feed threshold strands one third of the
    units of any triple-pane order and would deadlock the strict IGU order
    gate, which the reference results (33k IGUs, 94% IGU utilisation over the
    full run) rule out,
  * balances the *probability-weighted* pane-type route shares (bypass /
    furnace-1050 / furnace-1600) and the weighted mean piece area
    deterministically, so the Arena reference metrics (jumbo count, furnace
    entry utilizations, fills) are reproduced by construction rather than by
    sampling luck.

When the real 203$ table becomes available, drop it into
data/product_mix.csv (same two columns: cum_prob, code) or upload it through
the Parameters screen - nothing else needs to change.
"""
from __future__ import annotations

import csv
import pathlib

import numpy as np

OUT = pathlib.Path(__file__).resolve().parents[1] / "data" / "product_mix.csv"
N_ROWS = 66
GLASS3_DOUBLE = 12

# Pane-type pools by furnace routing (vFurnaceOf = [2,0,1,2,0,0,1,1,2,1,2,0]).
BYPASS_1 = [2, 5, 6, 12]
F1050_1 = [3, 7, 8, 10]
F1600_1 = [1, 4, 9, 11]
BYPASS_2 = [2, 5, 6]          # glass2 is a single digit (1..9)
F1050_2 = [3, 7, 8]
F1600_2 = [1, 4, 9]
# Weighted pane-instance route shares to hit the furnace entry utilizations.
ROUTE_TARGET = np.array([0.27, 0.44, 0.29])   # bypass / f1050 / f1600
# Concentrated type popularity: real lines run a few dominant glass types,
# which also lets consecutive orders share jumbo streams (low order buffer).
POOL_P4 = [0.66, 0.18, 0.10, 0.06]
POOL_P3 = [0.68, 0.20, 0.12]
SYM_P = 0.55                  # share of symmetric products (glass1 == glass2)
AREA_TARGET = 0.75            # weighted mean piece area (m^2)
WIDTH_RANGE = (400, 900)


def encode(g1: int, g2: int, g3: int, w: int, h: int) -> int:
    return g1 * 10**10 + g2 * 10**9 + g3 * 10**7 + w * 10**4 + h


def main() -> None:
    rng = np.random.default_rng(20260716)

    # Row weights: first row fixed at the documented 0.06246.
    rest = rng.gamma(1.2, 1.0, N_ROWS - 1)
    rest = rest / rest.sum() * (1.0 - 0.06246)
    weights = np.concatenate([[0.06246], rest])

    # Documented row 1: glass1=1 (f1600), glass2=5 (bypass), 526 x 1778 mm.
    types: list[tuple[int, int]] = [(1, 5)]
    share = np.zeros(3)
    share[2] += weights[0] / 2    # glass1=1 -> f1600
    share[0] += weights[0] / 2    # glass2=5 -> bypass

    def route_of_deficit() -> int:
        placed = share.sum()
        target_now = ROUTE_TARGET * (placed + 1e-12) / ROUTE_TARGET.sum()
        return int(np.argmax(ROUTE_TARGET * placed - share))

    for i in range(1, N_ROWS):
        w = weights[i]
        # pane 1: pick the route with the largest weighted deficit
        r1 = route_of_deficit()
        g1 = int(rng.choice([BYPASS_1, F1050_1, F1600_1][r1], p=POOL_P4))
        share[r1] += w / 2
        # pane 2: symmetric with probability SYM_P (needs single-digit type)
        if rng.random() < SYM_P and g1 <= 9:
            g2, r2 = g1, r1
        else:
            r2 = route_of_deficit()
            g2 = int(rng.choice([BYPASS_2, F1050_2, F1600_2][r2], p=POOL_P3))
        share[r2] += w / 2
        types.append((g1, g2))

    # Sizes: draw raw areas, then scale heights so the weighted mean area
    # hits AREA_TARGET exactly (row 1 stays fixed).
    widths = [526] + [int(rng.integers(*WIDTH_RANGE)) for _ in range(N_ROWS - 1)]
    raw_area = np.array([0.935228] +
                        list(np.clip(rng.lognormal(np.log(0.72), 0.40,
                                                   N_ROWS - 1), 0.30, 2.0)))
    w1a = weights[0] * raw_area[0]
    rest_target = AREA_TARGET - w1a
    rest_now = float((weights[1:] * raw_area[1:]).sum())
    raw_area[1:] *= rest_target / rest_now

    rows: list[tuple[float, int]] = [(0.06246, 15125261778)]
    for i in range(1, N_ROWS):
        g1, g2 = types[i]
        width = widths[i]
        height = int(round(raw_area[i] * 1e6 / width))
        height = max(400, min(height, 3100))
        rows.append((0.0, encode(g1, g2, GLASS3_DOUBLE, width, height)))

    cum = np.cumsum(weights)
    cum[-1] = 1.0
    out_rows = [(round(float(c), 5), code) for c, (_, code) in zip(cum, rows)]
    for i in range(1, N_ROWS):
        if out_rows[i][0] <= out_rows[i - 1][0]:
            out_rows[i] = (out_rows[i - 1][0] + 0.00001, out_rows[i][1])
    out_rows[-1] = (1.0, out_rows[-1][1])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["cum_prob", "code"])
        w.writerows(out_rows)

    # calibration echo
    areas = np.array([r[1] % 10**7 % 10**4 * ((r[1] % 10**7) // 10**4) / 1e6
                      for r in out_rows])
    print(f"wrote {OUT} ({len(out_rows)} rows)")
    print(f"weighted route shares (bypass/f1050/f1600): "
          f"{np.round(share / share.sum(), 3)}")
    print(f"weighted mean area: {(weights * areas).sum():.3f} m^2")


if __name__ == "__main__":
    main()
