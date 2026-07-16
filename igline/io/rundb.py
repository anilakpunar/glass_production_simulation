"""Lightweight SQLite run index (runs.db)."""
from __future__ import annotations

import json
import pathlib
import sqlite3
from datetime import datetime

from igline.io.params import ROOT

DB_PATH = ROOT / "runs" / "runs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    created TEXT,
    days INTEGER,
    seed INTEGER,
    replications INTEGER,
    igu_done REAL,
    orders_created REAL,
    units_ordered REAL,
    util_kesim_1 REAL,
    util_igu_1 REAL,
    jumbo_fill REAL,
    temper_fill REAL,
    path TEXT,
    params_json TEXT,
    summary_json TEXT
);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute(SCHEMA)
    return con


def index_run(run_id: str, params: dict, summaries: list[dict],
              aggregate: dict, path: str) -> None:
    s0 = summaries[0]
    n = len(summaries)

    def mean(key_path: str, default=None):
        try:
            vals = []
            for s in summaries:
                v = s
                for k in key_path.split("."):
                    v = v[k]
                vals.append(float(v))
            return sum(vals) / len(vals)
        except (KeyError, TypeError):
            return default

    con = _connect()
    with con:
        con.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, datetime.now().isoformat(timespec="seconds"),
             params["run"]["days"], params["run"].get("seed"), n,
             mean("igu_done"), mean("orders_created"), mean("units_ordered"),
             mean("utilization.kesim_1"), mean("utilization.igu_1"),
             mean("tallies.jumbo_fill.mean"),
             mean("tallies.temper_fill_combined_mean"),
             path, json.dumps(params),
             json.dumps({"aggregate": aggregate, "first": s0})))
    con.close()


def list_runs(limit: int = 100) -> list[dict]:
    if not DB_PATH.exists():
        return []
    con = _connect()
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT run_id, created, days, seed, replications, igu_done, "
        "orders_created, units_ordered, util_kesim_1, util_igu_1, "
        "jumbo_fill, temper_fill, path FROM runs "
        "ORDER BY created DESC LIMIT ?", (limit,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def get_run(run_id: str) -> dict | None:
    if not DB_PATH.exists():
        return None
    con = _connect()
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    con.close()
    if row is None:
        return None
    d = dict(row)
    d["params"] = json.loads(d.pop("params_json"))
    d["summary"] = json.loads(d.pop("summary_json"))
    return d
