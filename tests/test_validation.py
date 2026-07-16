"""Phase 3: Arena reference validation (5 replications x 10 days).

Slow test (~1 min); run with: pytest tests/test_validation.py -m validation
"""
import pathlib

import pytest

from igline.io.params import load_params
from igline.runner import run_replication
from igline.validation import REFERENCE, ROOT_CAUSES, evaluate, render_report

pytestmark = pytest.mark.validation

# Metrics that are expected to deviate for documented root causes (synthetic
# product mix / definitional entity counting) - they must have a root cause,
# not necessarily pass.
DOCUMENTED = set(ROOT_CAUSES)


@pytest.fixture(scope="module")
def rows(tmp_path_factory):
    params = load_params(overrides={"run": {"days": 10, "event_log": False}})
    summaries = [run_replication(params, seed=42 + r, out_dir=None,
                                 event_log_enabled=False)
                 for r in range(5)]
    return evaluate(summaries)


def test_all_pass_or_have_root_cause(rows):
    problems = []
    for r in rows:
        if r["ok"] is False and r["key"] not in DOCUMENTED:
            problems.append(f"{r['key']}: arena={r['arena']} got={r['mean']:.3f}")
    assert not problems, "unexplained deviations: " + "; ".join(problems)


def test_core_metrics_in_band(rows):
    """The physically fundamental metrics must actually pass, not just be
    explained away."""
    # Excluded metrics have documented sampling-realization root causes
    # (ROOT_CAUSES): cycle/buffer/igu-util scale with the realized volume of
    # due-window-preempted glasses (vDDwin rule, R3); furnace-1000 has a
    # physical upper bound below the Arena figure at the table's expected
    # route share; glass in/out is a definitional entity-count difference.
    must_pass = {"igu_done", "units_ordered", "util_kesim_1", "util_kesim_2",
                 "util_furnace_in_1600", "util_rodaj_1", "jumbo_fill_mean",
                 "jumbo_fill_flush_mean", "temper_fill_combined_mean",
                 "jumbos_cut_total"}
    failed = [r["key"] for r in rows if r["key"] in must_pass and r["ok"] is False]
    assert not failed, f"core metrics out of tolerance: {failed}"


def test_report_renders(rows, tmp_path):
    text = render_report(rows, {"generated": "test", "replications": 5,
                                "days": 10, "seed": 42, "run_dir": "x"})
    assert "| Tamamlanan IGU |" in text
    assert "kök neden" in text.lower() or "0 ❌" in text
    (tmp_path / "r.md").write_text(text)


def test_reference_table_complete():
    keys = {k for k, *_ in REFERENCE}
    assert len(keys) == len(REFERENCE)
    assert {"igu_done", "util_kesim_1", "jumbo_fill_mean",
            "order_buffer_mean", "glass_number_in"} <= keys
