"""Control processes (Arena "Packer"-style logic entities, R3-R7, R10).

All of them are event-driven: they block on :class:`~igline.engine.model.Signal`
wake-ups or fixed scan periods - no busy waiting.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from igline.engine import nesting
from igline.engine.rng import expo

if TYPE_CHECKING:
    from igline.engine.model import Line

S = 1.0 / 60.0


# --------------------------------------------------------------------- R3/R4
def nesting_packer(line: "Line"):
    """R3: pull glasses from the Hold Glass pool and build jumbos.

    Runs only while the pool is non-empty and token WIP < vMaxTok; each
    iteration consumes exactly one glass, so the zero-time loop is bounded.
    """
    env = line.env
    while True:
        if not line.pool or line.tok_wip >= line.max_tok:
            yield line.sig_packer.wait()
            continue
        glass = _select_glass(line)
        _place_with_close(line, glass)


def _select_glass(line: "Line"):
    """R3 steps 1-3: search-fit current strip, search-fit new strip (both with
    the due-window filter), else unconditionally pull the pool head."""
    due_limit = line.v_day + line.dd_win
    min_due = line.pool_min_due()
    if min_due is not None and min_due <= due_limit:
        # step 1: fits current strip of its own type's open jumbo
        for i, grp in enumerate(line.pool):
            if grp.due_date > due_limit:
                continue
            st = line.jumbo_state[grp.glass_type - 1]
            if nesting.fit_strip(st, grp.width, grp.height, line.jumbo_w,
                                 line.jumbo_h, line.kerf, line.rot_ok):
                return line.pool_pop(i)
        # step 2: fits by opening a new strip
        for i, grp in enumerate(line.pool):
            if grp.due_date > due_limit:
                continue
            st = line.jumbo_state[grp.glass_type - 1]
            if nesting.fit_new_strip(st, grp.width, grp.height, line.jumbo_w,
                                     line.jumbo_h, line.kerf, line.rot_ok):
                return line.pool_pop(i)
    # step 3: unconditional pull of the pool head (Remove 1)
    return line.pool_pop_head()


def _place_with_close(line: "Line", glass) -> None:
    """R3 'Decide Fit' on the pulled glass: strip -> new strip -> close jumbo
    and restart on a fresh one."""
    st = line.jumbo_state[glass.glass_type - 1]
    placed = nesting.fit_strip(st, glass.width, glass.height, line.jumbo_w,
                               line.jumbo_h, line.kerf, line.rot_ok)
    if placed:
        line.place_glass(glass, *placed)
        return
    placed = nesting.fit_new_strip(st, glass.width, glass.height, line.jumbo_w,
                                   line.jumbo_h, line.kerf, line.rot_ok)
    if placed:
        nesting.start_new_strip(st)
        line.place_glass(glass, *placed)
        return
    # does not fit at all -> close jumbo, glass restarts on the fresh jumbo
    if st.cnt > 0:
        line.close_jumbo(glass.glass_type, flush=False)
        st = line.jumbo_state[glass.glass_type - 1]
    placed = (nesting.fit_strip(st, glass.width, glass.height, line.jumbo_w,
                                line.jumbo_h, line.kerf, line.rot_ok)
              or nesting.fit_new_strip(st, glass.width, glass.height, line.jumbo_w,
                                       line.jumbo_h, line.kerf, line.rot_ok))
    assert placed, (f"glass {glass.width}x{glass.height} cannot fit an empty "
                    f"jumbo {line.jumbo_w}x{line.jumbo_h}")
    line.place_glass(glass, *placed)


# ----------------------------------------------------------------------- R4
def jumbo_flush_controller(line: "Line"):
    """Jumbo Flush: every flush_period minutes plus on every FJ signal; closes
    aged / full-enough jumbos while the sequencer starves."""
    env = line.env
    while True:
        yield env.any_of([env.timeout(line.flush_period), line.sig_fj.wait()])
        while True:
            line.fj_pend = 0
            for gt in range(1, 13):
                st = line.jumbo_state[gt - 1]
                if st.cnt == 0 or st.accum <= 0:
                    continue
                if (line.starve == 1 and st.j_min <= line.cur_order
                        and (env.now - st.open_t >= line.flush_grace
                             or st.accum >= line.flush_fill * line.jumbo_area)):
                    line.close_jumbo(gt, flush=True)
                    line.log(env.now, "nesting", "FLUSH", f"type{gt}", {})
            if not line.fj_pend:
                break


# ----------------------------------------------------------------------- R10
def temper_flush_controller(line: "Line"):
    """FT flush: wakes on FT signals from per-bed timers; closes beds older
    than vTmax."""
    env = line.env
    while True:
        yield line.sig_ft.wait()
        while True:
            line.ft_pend = 0
            for gt in range(1, 13):
                st = line.bed_state[gt - 1]
                if st is None or st.w_cnt == 0:
                    continue
                if env.now - st.open_t >= line.t_max:
                    line.close_bed(gt, flush=True)
                    line.log(env.now, f"temper_build", "FLUSH", f"type{gt}", {})
            if line.ft_pend < 1:
                break


# ----------------------------------------------------------------------- R7
def sequencer(line: "Line"):
    """Sorting #1: release glasses from the Order Buffer in strict order
    sequence, pane sets together; manages the starve flag."""
    env = line.env
    while True:
        acted = True
        while acted:
            acted = False
            cur = line.cur_order
            order = line.orders.get(cur)
            if order is None:
                break
            need = order.qty
            feed_mult = order.pane_count if line.strict_pane_feed else 2
            # 1) advance condition
            if (line.order_fed[cur] >= feed_mult * need
                    and cur < line.ord_cnt
                    and cur < line.igu_cur + line.igu_window):
                line.cur_order += 1
                line.fj_pend = 1
                line.sig_fj.fire()
                acted = True
                continue
            # 2) feed condition: one full pane set available
            panes = [1, 2] if order.pane_count == 2 else [1, 2, 3]
            if all(line.buf_g[(cur, g)] > line.fed_g[(cur, g)] for g in panes):
                line.starve = 0
                for g in panes:
                    glass = line.buf[(cur, g)].popleft()
                    line.fed_g[(cur, g)] += 1
                    line.order_fed[cur] += 1
                    line.order_buffer_count -= 1
                    assert line.order_buffer_count >= 0
                    line.ds_order_buffer.set(line.order_buffer_count, env.now)
                    env.process(line.glass_flow(glass))
                acted = True
        # 3) nothing possible -> starve and wait
        if line.starve != 1:
            line.starve = 1
            line.sig_dispatch.fire()   # starve unlocks the lookahead rule
            line.sig_fj.fire()
        yield line.sig_seq.wait()


# ----------------------------------------------------------------------- R5
def dispatcher(line: "Line"):
    """Cutting dispatch with the lookahead rule.

    Event-driven on token arrivals / machine releases / starve transitions
    (the Arena Hold scan condition fires as soon as a machine frees, which is
    what sustains the ~1.0 cutter utilization); the periodic scan is kept as
    a liveness fallback for the lookahead re-check.
    """
    env = line.env
    rng = line.rng["dispatch"]
    while True:
        while line.token_buffer:
            m = next((m for m in line.machines
                      if not m.busy and not m.inbox.items), None)
            if m is None:
                break
            head = line.token_buffer[0]
            if head.tok_min <= line.cur_order + line.lookahead or line.starve == 1:
                line.token_buffer.pop(0)
                m.inbox.put(head)
                line.log(env.now, "dispatch", "ASSIGN", f"jumbo{head.jumbo_id}",
                         {"machine": m.no, "tokMin": head.tok_min})
            else:
                break
        yield env.any_of([env.timeout(expo(rng, line.dispatch_period)
                                      if line.dispatch_expo else line.dispatch_period),
                          line.sig_dispatch.wait()])
