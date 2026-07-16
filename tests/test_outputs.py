"""Phase 2 acceptance: output files, summary schema, replications, run index."""
import csv
import json

import pytest

from igline.engine.model import Line
from igline.io import writers
from igline.io.params import load_params
from igline.runner import aggregate_replications, run_replication

REQUIRED_SUMMARY_KEYS = {
    "seed", "sim_minutes", "wall_seconds", "igu_done", "orders_created",
    "orders_done", "units_ordered", "otd_pct", "glass_number_in",
    "glass_number_out", "jumbos_cut", "jumbos_cut_total", "utilization",
    "tallies", "dstats", "counters_final", "throughput_per_h",
}
REQUIRED_UTIL_KEYS = {"kesim_1", "kesim_2", "rodaj_1", "rodaj_2",
                      "furnace_in_1000", "furnace_in_1600", "igu_1"}
REQUIRED_TALLY_KEYS = {
    "jumbo_fill", "jumbo_fill_flush", "jumbo_fill_combined_mean",
    "temper_fill", "temper_fill_flush", "temper_fill_combined_mean",
    "cycle_order_igu_min", "cycle_igu_min", "cycle_kesim_igu_min",
}


@pytest.fixture(scope="module")
def short_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("run")
    params = load_params(overrides={"run": {"days": 1}})
    summary = run_replication(params, seed=5, out_dir=out)
    return out, summary


def test_summary_schema(short_run):
    _, s = short_run
    assert REQUIRED_SUMMARY_KEYS <= set(s.keys())
    assert REQUIRED_UTIL_KEYS <= set(s["utilization"].keys())
    assert REQUIRED_TALLY_KEYS <= set(s["tallies"].keys())
    for k in ("order_buffer", "token_wip", "hold_glass", "igu_order_q"):
        assert {"mean", "max", "final"} <= set(s["dstats"][k].keys())


def test_output_files_exist(short_run):
    out, _ = short_run
    for name in ("jumbo_detail.csv", "jumbo_results.csv", "temp_results.csv",
                 "igu_results.csv", "orders.csv", "series.json",
                 "summary.json", "event_log.jsonl", "distributions.json"):
        assert (out / name).exists(), name


def test_csv_headers(short_run):
    out, _ = short_run
    for name, header in writers.CSV_HEADERS.items():
        with open(out / name) as f:
            assert next(csv.reader(f)) == header


def test_event_log_jsonl(short_run):
    out, _ = short_run
    with open(out / "event_log.jsonl") as f:
        for i, ln in enumerate(f):
            row = json.loads(ln)
            assert {"ts", "sim_min", "station", "event", "entity", "payload"} <= set(row)
            if i > 50:
                break


def test_aggregate_replications():
    params = load_params(overrides={"run": {"days": 1}, })
    s1 = run_replication(params, seed=1, out_dir=None)
    s2 = run_replication(params, seed=2, out_dir=None)
    agg = aggregate_replications([s1, s2])
    assert agg["replications"] == 2
    m = agg["metrics"]["igu_done"]
    assert m["n"] == 2 and m["half_width"] >= 0
    assert m["mean"] == pytest.approx(sum(m["values"]) / 2)


def test_determinism_same_seed():
    params = load_params(overrides={"run": {"days": 1}})
    a = run_replication(params, seed=9, out_dir=None)
    b = run_replication(params, seed=9, out_dir=None)
    assert a["igu_done"] == b["igu_done"]
    assert a["tallies"]["jumbo_fill"]["mean"] == b["tallies"]["jumbo_fill"]["mean"]
