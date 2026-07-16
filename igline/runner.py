"""Run orchestration: single/multi replication headless runs + run registry."""
from __future__ import annotations

import json
import math
import pathlib
import time
from datetime import datetime

from igline.engine.model import Line
from igline.io import writers
from igline.io.params import ROOT, freeze_params, load_params
from igline.io.rundb import index_run


def make_run_id(tag: str | None = None) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{tag}" if tag else ts


def run_replication(params: dict, seed: int, out_dir: pathlib.Path | None,
                    event_log_enabled: bool = True) -> dict:
    """Run one replication; write outputs if out_dir given; return summary."""
    elog = None
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        elog = writers.EventLog(out_dir / "event_log.jsonl",
                                enabled=event_log_enabled and params["run"].get("event_log", True))
    t0 = time.perf_counter()
    line = Line(params, seed=seed, event_log=elog)
    line.run()
    wall = time.perf_counter() - t0
    summary = writers.build_summary(line, seed, wall)
    if out_dir is not None:
        writers.write_csvs(line, out_dir)
        writers.write_order_table(line, out_dir)
        writers.write_series(line, out_dir)
        writers.write_summary(summary, out_dir)
        if elog:
            elog.close()
        # histogram raw data for the dashboard
        with open(out_dir / "distributions.json", "w") as f:
            json.dump({
                "jumbo_fill": line.tally_jumbo_fill.values,
                "jumbo_fill_flush": line.tally_jumbo_fill_flush.values,
                "temper_fill": line.tally_temper_fill.values,
                "temper_fill_flush": line.tally_temper_fill_flush.values,
                "cycle_kesim_igu": line.tally_cyc_kesim_igu.values,
                "cycle_igu": line.tally_cyc_igu.values,
                "cycle_order_igu": line.tally_cyc_order_igu.values,
            }, f)
    return summary


def aggregate_replications(summaries: list[dict]) -> dict:
    """Mean +- half-width (95% t-approx) over scalar metrics."""
    import statistics

    def collect(path: str) -> list[float]:
        vals = []
        for s in summaries:
            v = s
            for k in path.split("."):
                v = v[k]
            if v is not None:
                vals.append(float(v))
        return vals

    metrics = {
        "igu_done": "igu_done",
        "orders_created": "orders_created",
        "units_ordered": "units_ordered",
        "util_kesim_1": "utilization.kesim_1",
        "util_kesim_2": "utilization.kesim_2",
        "util_igu_1": "utilization.igu_1",
        "util_furnace_in_1000": "utilization.furnace_in_1000",
        "util_furnace_in_1600": "utilization.furnace_in_1600",
        "util_rodaj_1": "utilization.rodaj_1",
        "jumbo_fill_mean": "tallies.jumbo_fill.mean",
        "jumbo_fill_flush_mean": "tallies.jumbo_fill_flush.mean",
        "temper_fill_combined_mean": "tallies.temper_fill_combined_mean",
        "order_buffer_mean": "dstats.order_buffer.mean",
        "order_buffer_max": "dstats.order_buffer.max",
        "cycle_kesim_igu_mean": "tallies.cycle_kesim_igu_min.mean",
        "cycle_igu_mean": "tallies.cycle_igu_min.mean",
        "jumbos_cut_total": "jumbos_cut_total",
        "glass_number_in": "glass_number_in",
        "glass_number_out": "glass_number_out",
        "throughput_per_h": "throughput_per_h",
    }
    # t multipliers for 95% CI, df = n-1
    T95 = {1: 0.0, 2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571,
           7: 2.447, 8: 2.365, 9: 2.306, 10: 2.262}
    out = {}
    n = len(summaries)
    for name, path in metrics.items():
        vals = collect(path)
        if not vals:
            continue
        mean = statistics.fmean(vals)
        hw = 0.0
        if len(vals) > 1:
            sd = statistics.stdev(vals)
            t = T95.get(len(vals), 2.0)
            hw = t * sd / math.sqrt(len(vals))
        out[name] = {"mean": round(mean, 4), "half_width": round(hw, 4),
                     "n": len(vals), "values": [round(v, 4) for v in vals]}
    return {"replications": n, "metrics": out}


def run_cli(args) -> int:
    overrides: dict = {"run": {}}
    if args.days:
        overrides["run"]["days"] = args.days
    if args.seed is not None:
        overrides["run"]["seed"] = args.seed
    if args.replications:
        overrides["run"]["replications"] = args.replications
    if args.no_event_log:
        overrides["run"]["event_log"] = False
    params = load_params(args.params, overrides)

    run_id = make_run_id(args.tag)
    out_root = pathlib.Path(args.out)
    if not out_root.is_absolute():
        out_root = ROOT / out_root
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    freeze_params(params, run_dir / "params.yaml")

    n_rep = params["run"].get("replications", 1) or 1
    base_seed = params["run"].get("seed", 42)
    summaries = []
    for r in range(n_rep):
        rep_dir = run_dir if n_rep == 1 else run_dir / f"rep{r+1:02d}"
        seed = base_seed + r
        s = run_replication(params, seed, rep_dir,
                            event_log_enabled=params["run"].get("event_log", True))
        summaries.append(s)
        if not args.quiet:
            print(f"rep {r+1}/{n_rep} seed={seed}: IGU={s['igu_done']} "
                  f"orders={s['orders_created']} units={s['units_ordered']} "
                  f"kesim_util={s['utilization']['kesim_1']:.4f}/"
                  f"{s['utilization'].get('kesim_2', 0):.4f} "
                  f"igu_util={s['utilization']['igu_1']:.4f} "
                  f"wall={s['wall_seconds']}s")
    agg = aggregate_replications(summaries)
    writers.write_summary({"aggregate": agg, "replications": summaries},
                          run_dir) if n_rep > 1 else None
    index_run(run_id, params, summaries, agg, str(run_dir))
    if not args.quiet:
        print(f"outputs: {run_dir}")
    return 0
