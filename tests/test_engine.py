"""Integration tests for the DES engine (Phase 1 acceptance)."""
import time

import pytest

from igline.engine.model import Line
from igline.io.params import load_params


@pytest.fixture(scope="module")
def line10():
    params = load_params(overrides={"run": {"days": 10}})
    t0 = time.perf_counter()
    line = Line(params, seed=42)
    line.run()
    line.wall = time.perf_counter() - t0
    return line


def test_runs_fast_enough(line10):
    assert line10.wall < 60.0


def test_igu_count_band(line10):
    assert 30_000 <= line10.igu_done_total <= 36_000


def test_cutting_utilization(line10):
    for m in line10.machines:
        assert m.meter.utilization(line10.T_end) > 0.97


def test_no_negative_counters(line10):
    assert line10.tok_wip >= 0
    assert line10.order_buffer_count >= 0
    assert line10.pool_count >= 0
    assert line10.temper_build_count >= 0
    assert all(v >= 0 for v in line10.match_q_len)


def test_igu_results_recorded(line10):
    assert len(line10.rows_igu_results) == line10.igu_done_total
    # rows carry sane cycle times
    row = line10.rows_igu_results[100]
    assert row[15] > 0 and row[16] > 0        # cycle_kesim_igu, cycle_igu


def test_strict_order_gate(line10):
    """Units must start assembly in non-decreasing order sequence."""
    seen = [r[0] for r in line10.rows_igu_results[:2000]]
    # tDone ordering equals gate ordering only per station; check orderNo of
    # completions never jumps backwards by more than the 3 parallel stations
    for a, b in zip(seen, seen[1:]):
        assert b >= a - 1


def test_glass_conservation(line10):
    """Every cut glass is somewhere: buffer, in-flight, matched or done."""
    assert line10.glass_out <= line10.glass_in
    fed = sum(line10.order_fed.values())
    cut = sum(line10.buf_g.values())
    assert fed <= cut <= line10.glass_in


def test_order_progress(line10):
    assert line10.igu_cur <= line10.cur_order + 1
    assert line10.orders_done > 0
    o = line10.orders[1]
    assert o.done == o.qty                     # first order must complete


def test_jumbo_accounting(line10):
    closed = len(line10.rows_jumbo_results)
    cut = sum(m.jumbos_cut for m in line10.machines)
    # every cut jumbo was closed first; open/queued tokens may remain
    assert cut <= closed
    assert closed - cut <= line10.max_tok + len(line10.token_buffer) + 2


def test_calendar_mapping():
    params = load_params(overrides={"run": {"days": 2}})
    line = Line(params, seed=1)
    assert line.sim_clock(0) == "2026-01-05 07:00"
    assert line.sim_clock(539) == "2026-01-05 15:59"
    assert line.sim_clock(540) == "2026-01-06 07:00"
    # day 5 (0-based) falls on the next Monday (weekend skipped)
    assert line.sim_clock(5 * 540) == "2026-01-12 07:00"
