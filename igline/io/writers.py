"""Run output writers: R14 CSV files, event_log.jsonl, summary.json."""
from __future__ import annotations

import csv
import json
import pathlib
from datetime import datetime, timezone

from igline.engine.stats import percentile

CSV_HEADERS = {
    "jumbo_detail.csv": ["glassType", "jumboNo", "orderNo", "glassNo",
                         "width", "height", "area", "t"],
    "jumbo_results.csv": ["glassType", "jumboNo", "count", "area_accum",
                          "fill", "flush_flag"],
    "temp_results.csv": ["glassType", "tempNo", "count", "width_accum",
                         "fill", "flush_flag"],
    "igu_results.csv": ["unitKey", "orderNo", "jumboID", "paneCount",
                        "glass1", "glass2", "glass3", "width", "height", "area",
                        "orderDate", "dueDate", "tKesim", "tIGU", "tDone",
                        "cycle_kesim_igu", "cycle_igu"],
}


class EventLog:
    """Buffered JSONL event log (R14): ts, sim_min, station, event, entity,
    payload."""

    def __init__(self, path: pathlib.Path, enabled: bool = True, flush_every: int = 5000):
        self.enabled = enabled
        self.path = path
        self._buf: list[str] = []
        self._flush_every = flush_every
        self._fh = None
        self.tail: list[dict] = []       # last events kept for the UI panel
        self._tail_max = 200
        if enabled:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(path, "w", buffering=1 << 20)

    def __call__(self, sim_min: float, station: str, event: str,
                 entity: str, payload: dict) -> None:
        if not self.enabled:
            return
        row = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "sim_min": round(sim_min, 3), "station": station,
               "event": event, "entity": entity, "payload": payload}
        self._buf.append(json.dumps(row, separators=(",", ":")))
        self.tail.append(row)
        if len(self.tail) > self._tail_max:
            del self.tail[: len(self.tail) - self._tail_max]
        if len(self._buf) >= self._flush_every:
            self.flush()

    def flush(self) -> None:
        if self._fh and self._buf:
            self._fh.write("\n".join(self._buf) + "\n")
            self._buf.clear()

    def close(self) -> None:
        self.flush()
        if self._fh:
            self._fh.close()
            self._fh = None


def write_csvs(line, out_dir: pathlib.Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = {
        "jumbo_detail.csv": line.rows_jumbo_detail,
        "jumbo_results.csv": line.rows_jumbo_results,
        "temp_results.csv": line.rows_temp_results,
        "igu_results.csv": line.rows_igu_results,
    }
    for name, rows in tables.items():
        with open(out_dir / name, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(CSV_HEADERS[name])
            w.writerows(rows)


def build_summary(line, seed: int, wall_s: float) -> dict:
    """All A.4 metrics + KPI extras, one dict per replication."""
    now = line.T_end
    tj, tjf = line.tally_jumbo_fill, line.tally_jumbo_fill_flush
    tt, ttf = line.tally_temper_fill, line.tally_temper_fill_flush
    orders = list(line.orders.values())
    total_units = sum(o.qty for o in orders)
    done_orders = [o for o in orders if o.done >= o.qty]
    on_time = sum(1 for o in done_orders
                  if (int(o.last_igu_t // line.day_min) + 1) <= o.due_date)

    def tsum(t):
        return t.summary()

    buf_vals = None
    summary = {
        "seed": seed,
        "sim_minutes": now,
        "wall_seconds": round(wall_s, 2),
        "igu_done": line.igu_done_total,
        "orders_created": line.ord_cnt,
        "orders_done": len(done_orders),
        "units_ordered": total_units,
        "otd_pct": round(100.0 * on_time / len(done_orders), 2) if done_orders else None,
        "glass_number_in": line.glass_in,
        "glass_number_out": line.glass_out,
        "jumbos_cut": [m.jumbos_cut for m in line.machines],
        "jumbos_cut_total": sum(m.jumbos_cut for m in line.machines),
        "utilization": {
            **{f"kesim_{m.no}": round(m.meter.utilization(now), 4) for m in line.machines},
            **{f"rodaj_{i+1}": round(mt.utilization(now), 4)
               for i, mt in enumerate(line.rodaj_meter)},
            "furnace_in_1000": round(line.entrance_meter[0].utilization(now), 4),
            "furnace_in_1600": round(line.entrance_meter[1].utilization(now), 4),
            "igu_1": round(line.igu_meter.utilization(now), 4),
        },
        "tallies": {
            "jumbo_fill": tsum(tj),
            "jumbo_fill_flush": tsum(tjf),
            "jumbo_fill_combined_mean": line._combined_fill(tj, tjf),
            "temper_fill": tsum(tt),
            "temper_fill_flush": tsum(ttf),
            "temper_fill_combined_mean": line._combined_fill(tt, ttf),
            "cycle_order_igu_min": tsum(line.tally_cyc_order_igu),
            "cycle_igu_min": tsum(line.tally_cyc_igu),
            "cycle_kesim_igu_min": tsum(line.tally_cyc_kesim_igu),
        },
        "dstats": {
            "order_buffer": line.ds_order_buffer.summary(now),
            "token_wip": line.ds_token_wip.summary(now),
            "hold_glass": line.ds_hold_glass.summary(now),
            "igu_order_q": line.ds_gate_q.summary(now),
            "match_q": line.ds_match_q.summary(now),
        },
        "counters_final": {
            "cur_order": line.cur_order,
            "igu_cur_order": line.igu_cur,
            "tok_wip": line.tok_wip,
            "order_buffer": line.order_buffer_count,
            "hold_glass": line.pool_count,
            "temper_build": line.temper_build_count,
            "igu_gate_q": len(line.gate_heap),
        },
        "throughput_per_h": round(line.igu_done_total / (now / 60.0), 2),
    }
    # cycle-time distribution percentiles for the dashboard
    for key, tally in (("cycle_kesim_igu", line.tally_cyc_kesim_igu),
                       ("cycle_igu", line.tally_cyc_igu),
                       ("cycle_order_igu", line.tally_cyc_order_igu)):
        vals = sorted(tally.values)
        summary["tallies"][key + "_pcts"] = {
            "p50": percentile(vals, 0.5), "p95": percentile(vals, 0.95),
            "p99": percentile(vals, 0.99)}
    return summary


def write_order_table(line, out_dir: pathlib.Path) -> None:
    """Dashboard order table (one row per order)."""
    with open(out_dir / "orders.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["orderNo", "qty", "paneCount", "orderDate", "dueDate",
                    "firstCut_min", "lastIGU_min", "done", "status",
                    "flow_min", "lateness_days"])
        for o in line.orders.values():
            status = ("done" if o.done >= o.qty else
                      "in_progress" if o.done > 0 or o.first_cut_t >= 0 else "waiting")
            flow = (o.last_igu_t - o.t_start) if o.done >= o.qty else ""
            late = ((int(o.last_igu_t // line.day_min) + 1) - o.due_date
                    if o.done >= o.qty else "")
            w.writerow([o.order_no, o.qty, o.pane_count, o.order_date, o.due_date,
                        round(o.first_cut_t, 2) if o.first_cut_t >= 0 else "",
                        round(o.last_igu_t, 2) if o.last_igu_t >= 0 else "",
                        o.done, status,
                        round(flow, 2) if flow != "" else "", late])


def write_series(line, out_dir: pathlib.Path) -> None:
    with open(out_dir / "series.json", "w") as f:
        json.dump(line.series, f)


def write_summary(summary: dict, out_dir: pathlib.Path) -> None:
    with open(out_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)
