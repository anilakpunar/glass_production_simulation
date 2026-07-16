"""IGU line model (Arena Scenario 3, rules R1-R13).

The base time unit is the simulated MINUTE; all second-based inputs are
converted with ``S = 1/60``. The simulated clock runs continuously over
``days * hours_per_day * 60`` minutes (Arena "9 Hours Per Day" calendar);
calendar display maps sim minutes onto 9-hour working days.
"""
from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

import simpy

from igline.engine import nesting
from igline.engine.entities import Bed, Glass, IGUUnit, Order, Token
from igline.engine.rng import Disc, expo, gamma_arena, logn_arena, spawn_streams, tria
from igline.engine.stats import BusyMeter, DStat, Tally
from igline.io.params import decode_product, load_product_mix

S = 1.0 / 60.0  # seconds -> minutes
N_TYPES = 12


class Signal:
    """Level-triggered wake-up: ``fire()`` never blocks, a ``yield wait()``
    after a missed fire returns immediately (no lost wake-ups)."""

    __slots__ = ("env", "_ev")

    def __init__(self, env: simpy.Environment):
        self.env = env
        self._ev = env.event()

    def fire(self) -> None:
        if not self._ev.triggered:
            self._ev.succeed()

    def wait(self):
        ev = self._ev
        if ev.triggered:
            self._ev = self.env.event()
        return ev


@dataclass(slots=True)
class PoolGroup:
    """A run of identical uncut glasses (same order + pane) in the Hold Glass
    pool; kept as one group so the nesting search scans O(#orders) instead of
    O(#glasses)."""
    order_no: int
    glass_no: int
    glass_type: int
    width: int
    height: int
    area: float
    due_date: int
    glasses: deque


@dataclass(slots=True)
class BedState:
    """Open temper bed per glass type (vWAccum, vWCnt, vTOpenT, vTempNo)."""
    glass_type: int
    bed_no: int = 1
    w_accum: float = 0.0
    w_cnt: int = 0
    open_t: float = 0.0
    glasses: list = field(default_factory=list)

    @property
    def temp_id(self) -> int:
        return self.glass_type * 100000 + self.bed_no


class Machine:
    """Cutting machine (Kesim_1 / Kesim_2)."""

    def __init__(self, env: simpy.Environment, no: int):
        self.no = no
        self.inbox: simpy.Store = simpy.Store(env)
        self.busy = False
        self.meter = BusyMeter(f"kesim_{no}", 1)
        self.jumbos_cut = 0
        self.current: dict | None = None   # live job info for SCADA


class Line:
    """Complete line state + station processes. Control processes live in
    :mod:`igline.engine.controllers`."""

    def __init__(self, params: dict, seed: int,
                 event_log: Callable[[float, str, str, str, dict], None] | None = None):
        self.p = params
        self.env = simpy.Environment()
        self.log = event_log or (lambda *_a, **_k: None)

        run = params["run"]
        self.day_min = run["hours_per_day"] * 60.0
        self.T_end = run["days"] * self.day_min
        self.start_dt = datetime.strptime(run["start_datetime"], "%Y-%m-%d %H:%M")

        self.rng = spawn_streams(seed, [
            "orders", "cutting", "igu", "dispatch", "mix", "qty", "due"])

        cum, codes = load_product_mix(params["orders"]["product_mix_file"])
        self.product_disc = Disc(cum, codes)

        o = params["orders"]
        self.daily_target = o["daily_target"]
        self.batch_interval = o["batch_interval_s"] * S
        self.first_batch = o["first_batch_s"] * S

        n = params["nesting"]
        self.jumbo_w = n["jumbo_w_mm"]
        self.jumbo_h = n["jumbo_h_mm"]
        self.jumbo_area = self.jumbo_w * self.jumbo_h / 1e6
        self.kerf = n["kerf_mm"]
        self.rot_ok = bool(n["rotation_ok"])
        self.dd_win = n["due_window_days"]
        self.max_tok = n["max_token_wip"]
        self.flush_grace = n["flush_grace_s"] * S
        self.flush_fill = n["flush_fill_threshold"]
        self.flush_period = n["flush_period_min"]

        c = params["cutting"]
        self.trim_tria = c["trim_tria_s"]
        self.break_tria = c["break_tria_s"]
        self.lookahead = c["lookahead_orders"]
        self.dispatch_period = c["dispatch_period_min"]
        self.dispatch_expo = bool(c.get("dispatch_expo", False))

        sq = params["sequencer"]
        self.igu_window = sq["igu_window_orders"]
        self.strict_pane_feed = bool(sq.get("strict_pane_feed", False))

        t = params["temper"]
        self.furnace_of = list(t["furnace_of"])          # index glassType-1 -> 0/1/2
        self.heat_time = list(t["heat_time_s"])
        self.furnace_width = list(t["furnace_width_mm"])
        self.l_heat = list(t["heat_zone_len_mm"])
        self.furn_len = list(t["tunnel_len_mm"])
        self.row_gap = t["row_gap_mm"]
        self.glass_gap = t["glass_gap_mm"]
        self.t_max = t["bed_timeout_s"] * S
        self.div_n = t["divert_threshold"]

        e = params["edging"]
        self.vfeed = e["feed_mm_s"]

        g = params["igu"]
        self.igu_tria = g["process_tria_s"]
        self.igu_setup = g["setup_s"]

        env = self.env

        # ----- orders / pool -----
        self.orders: dict[int, Order] = {}
        self.ord_cnt = 0
        self.v_day = 0
        self.pool: list[PoolGroup] = []
        self.pool_count = 0
        self._pool_min_due: int | None = None
        self.glass_in = 0
        self.glass_out = 0
        self.batches_created = 0

        # ----- nesting / tokens -----
        self.jumbo_state = [nesting.JumboState(gt) for gt in range(1, N_TYPES + 1)]
        self.jumbo_build: dict[int, deque] = {}
        self.token_buffer: list[Token] = []       # kept sorted by tok_min
        self.tok_wip = 0

        # ----- cutting -----
        self.machines = [Machine(env, i + 1) for i in range(c["machines"])]

        # ----- order buffer / sequencer -----
        self.buf: dict[tuple[int, int], deque] = {}
        self.buf_g: dict[tuple[int, int], int] = {}
        self.fed_g: dict[tuple[int, int], int] = {}
        self.order_fed: dict[int, int] = {}
        self.cur_order = 1
        self.starve = 0

        # ----- edging (rodaj) -----
        lines = e["lines"]
        self.rodaj_h = [simpy.Resource(env, 1) for _ in range(lines)]
        self.rodaj_w = [simpy.Resource(env, 1) for _ in range(lines)]
        self.rodaj_meter = [BusyMeter(f"rodaj_{i+1}", 2) for i in range(lines)]

        # ----- temper / furnace -----
        self.bed_state = [BedState(gt) if self.furnace_of[gt - 1] != 0 else None
                          for gt in range(1, N_TYPES + 1)]
        self.entrance = [simpy.Resource(env, 1), simpy.Resource(env, 1)]
        self.entrance_meter = [BusyMeter("furnace_in_1000", 1), BusyMeter("furnace_in_1600", 1)]
        self.tunnel: list[list[dict]] = [[], []]   # live loads per furnace (SCADA)
        self.temper_build_count = 0

        # ----- match / IGU gate -----
        self.match_store: dict[int, list[deque]] = {}
        self.match_q_len = [0, 0, 0]
        self.igu_arr: dict[int, int] = {}
        self.igu_passed: dict[int, int] = {}
        self.gate_heap: list[tuple[int, int, IGUUnit]] = []
        self._gate_seq = 0
        self.igu_cur = 1

        # ----- IGU assembly -----
        self.igu_res = simpy.Resource(env, g["stations"])
        self.igu_meter = BusyMeter("igu_1", g["stations"])
        self.igu_last_order = -1
        self.igu_done_total = 0
        self.orders_done = 0
        self.igu_active: list[int] = []            # orderNos in service (SCADA)

        # ----- signals -----
        self.sig_packer = Signal(env)   # pool changed / token slot freed
        self.sig_dispatch = Signal(env) # token added / machine freed / starve
        self.sig_seq = Signal(env)      # sequencer wake
        self.sig_fj = Signal(env)       # jumbo flush scan request
        self.sig_ft = Signal(env)       # temper flush scan request
        self.sig_gate = Signal(env)     # IGU order gate wake
        self.fj_pend = 0
        self.ft_pend = 0

        # ----- statistics -----
        self.tally_jumbo_fill = Tally("Jumbo Fill", keep_values=True)
        self.tally_jumbo_fill_flush = Tally("Jumbo Fill Flush", keep_values=True)
        self.tally_temper_fill = Tally("Temper Fill", keep_values=True)
        self.tally_temper_fill_flush = Tally("Temper Fill Flush", keep_values=True)
        self.tally_cyc_order_igu = Tally("Cycle Order_IGU", keep_values=True)
        self.tally_cyc_igu = Tally("Cycle IGU", keep_values=True)
        self.tally_cyc_kesim_igu = Tally("Cycle Kesim_IGU", keep_values=True)
        self.ds_order_buffer = DStat("order_buffer")
        self.ds_token_wip = DStat("token_wip")
        self.ds_hold_glass = DStat("hold_glass")
        self.ds_gate_q = DStat("igu_order_q")
        self.ds_match_q = DStat("match_q")
        self.order_buffer_count = 0

        # ----- output rows (R14) -----
        self.rows_jumbo_detail: list[tuple] = []
        self.rows_jumbo_results: list[tuple] = []
        self.rows_temp_results: list[tuple] = []
        self.rows_igu_results: list[tuple] = []

        # ----- dashboard time series -----
        self.series: list[dict] = []
        self._last_igu_total = 0

        # extension hook: broken-glass rework re-entry (not used in Scenario 3)
        self.rework_hook: Callable[[Glass], None] | None = None

        self._start_processes()

    # ------------------------------------------------------------------ time
    def sim_clock(self, sim_min: float) -> str:
        """Map continuous sim minutes to the 9h/day working calendar
        (weekends skipped for display)."""
        day = int(sim_min // self.day_min)
        within = sim_min % self.day_min
        # working days -> calendar days skipping Sat/Sun
        wd = self.start_dt
        full_weeks, rest = divmod(day, 5)
        wd = wd + timedelta(weeks=full_weeks, days=rest)
        if wd.weekday() >= 5:  # landed on weekend via rest overflow
            wd += timedelta(days=7 - wd.weekday())
        return (wd + timedelta(minutes=within)).strftime("%Y-%m-%d %H:%M")

    # -------------------------------------------------------------- processes
    def _start_processes(self) -> None:
        from igline.engine import controllers
        env = self.env
        env.process(self.order_generator())
        env.process(controllers.nesting_packer(self))
        env.process(controllers.jumbo_flush_controller(self))
        env.process(controllers.temper_flush_controller(self))
        env.process(controllers.sequencer(self))
        env.process(controllers.dispatcher(self))
        for m in self.machines:
            env.process(self.cutting_machine(m))
        env.process(self.igu_gate())
        env.process(self.series_sampler())

    # ----------------------------------------------------------------- orders
    def order_generator(self):
        """R2: batch order creation every batch_interval, first at t=60 s."""
        env = self.env
        yield env.timeout(self.first_batch)
        while True:
            self.v_day += 1
            self.batches_created += 1
            gen_acc = 0
            while gen_acc < self.daily_target:
                order = self._create_order()
                gen_acc += order.qty
            self.log(env.now, "orders", "BATCH", f"day{self.v_day}",
                     {"orders": self.ord_cnt, "units": gen_acc})
            self.sig_packer.fire()
            self.sig_seq.fire()
            yield env.timeout(self.batch_interval)

    def _create_order(self) -> Order:
        env = self.env
        code = self.product_disc.sample(self.rng["mix"])
        d = decode_product(code)
        qty = max(1, round(min(float(self.p["orders"]["qty_cap"]),
                               logn_arena(self.rng["qty"],
                                          self.p["orders"]["qty_mean"],
                                          self.p["orders"]["qty_sd"]))))
        due = self.v_day + round(gamma_arena(self.rng["due"],
                                             self.p["orders"]["due_gamma_scale"],
                                             self.p["orders"]["due_gamma_shape"]))
        self.ord_cnt += 1
        no = self.ord_cnt
        order = Order(order_no=no, code=code, glass1=d["glass1"], glass2=d["glass2"],
                      glass3=d["glass3"], width=d["width"], height=d["height"],
                      area=d["area"], qty=qty, order_date=self.v_day, due_date=due,
                      t_start=env.now, pane_count=d["pane_count"])
        self.orders[no] = order
        self.order_fed[no] = 0
        # Explode into glass panes -> Hold Glass pool. Arena SEPARATE runs per
        # unit (G1, G2[, G3], next unit ...), so pane seq numbers interleave;
        # groups keep one deque per pane but respect the interleaved seq.
        panes = [(1, d["glass1"]), (2, d["glass2"])]
        if d["glass3"] != 12:
            panes.append((3, d["glass3"]))
        pc = len(panes)
        for j, (glass_no, gtype) in enumerate(panes):
            glasses = deque()
            for i in range(qty):
                piece = i * pc + j + 1
                seq = no * 100000 + piece * 10 + 1
                glasses.append(Glass(order_no=no, glass_no=glass_no, glass_type=gtype,
                                     seq=seq, width=d["width"], height=d["height"],
                                     area=d["area"], due_date=due))
            self.pool.append(PoolGroup(no, glass_no, gtype, d["width"], d["height"],
                                       d["area"], due, glasses))
            self.buf.setdefault((no, glass_no), deque())
            self.buf_g[(no, glass_no)] = 0
            self.fed_g[(no, glass_no)] = 0
            self.glass_in += qty
        self.pool_count += order.qty * order.pane_count
        if self._pool_min_due is None or due < self._pool_min_due:
            self._pool_min_due = due
        self.ds_hold_glass.set(self.pool_count, env.now)
        return order

    # ------------------------------------------------------------------ pool
    def pool_min_due(self) -> int | None:
        if self._pool_min_due is None and self.pool:
            self._pool_min_due = min(g.due_date for g in self.pool)
        return self._pool_min_due

    def pool_pop(self, idx: int) -> Glass:
        grp = self.pool[idx]
        glass = grp.glasses.popleft()
        if not grp.glasses:
            self.pool.pop(idx)
            if grp.due_date == self._pool_min_due:
                self._pool_min_due = min((g.due_date for g in self.pool), default=None)
        self.pool_count -= 1
        self.ds_hold_glass.set(self.pool_count, self.env.now)
        return glass

    def pool_pop_head(self) -> Glass:
        """Pop the glass with the globally smallest seq. Pane groups of the
        earliest order interleave, so pick the min-head-seq group among the
        leading order's groups."""
        first_o = self.pool[0].order_no
        best = 0
        best_seq = self.pool[0].glasses[0].seq
        for i in range(1, min(3, len(self.pool))):
            grp = self.pool[i]
            if grp.order_no != first_o:
                break
            if grp.glasses[0].seq < best_seq:
                best = i
                best_seq = grp.glasses[0].seq
        return self.pool_pop(best)

    # --------------------------------------------------------------- nesting
    def close_jumbo(self, gtype: int, flush: bool) -> None:
        """R4: close the open jumbo of a type -> emit a cutting token."""
        st = self.jumbo_state[gtype - 1]
        assert st.cnt > 0, "closing an empty jumbo"
        fill = st.accum / self.jumbo_area
        (self.tally_jumbo_fill_flush if flush else self.tally_jumbo_fill).record(fill)
        self.rows_jumbo_results.append(
            (gtype, st.jumbo_no, st.cnt, round(st.accum, 4), round(fill, 4), int(flush)))
        tok = Token(jumbo_id=st.jumbo_id, glass_type=gtype, tok_n=st.cnt,
                    tok_min=st.j_min, tok_max=st.j_max)
        self.log(self.env.now, "nesting", "CLOSE", f"jumbo{st.jumbo_id}",
                 {"type": gtype, "n": st.cnt, "fill": round(fill, 3), "flush": flush})
        nesting.reset_after_close(st)
        self.tok_wip += 1
        self.ds_token_wip.set(self.tok_wip, self.env.now)
        # token buffer kept sorted by tok_min (LVF)
        lo = 0
        while lo < len(self.token_buffer) and self.token_buffer[lo].tok_min <= tok.tok_min:
            lo += 1
        self.token_buffer.insert(lo, tok)
        self.sig_dispatch.fire()

    def place_glass(self, glass: Glass, pw: float, ph: float) -> None:
        """addOpen (R3): put an oriented piece on its type's open jumbo."""
        st = self.jumbo_state[glass.glass_type - 1]
        jid = nesting.add_open(st, pw, ph, glass.area, glass.order_no, glass.seq,
                               self.kerf, self.env.now)
        glass.jumbo_id = jid
        self.jumbo_build.setdefault(jid, deque()).append(glass)
        self.rows_jumbo_detail.append(
            (glass.glass_type, st.jumbo_no, glass.order_no, glass.glass_no,
             glass.width, glass.height, round(glass.area, 4), round(self.env.now, 3)))
        self.fj_pend = 1
        self.sig_fj.fire()

    # --------------------------------------------------------------- cutting
    def cutting_machine(self, m: Machine):
        """R6: trim per jumbo, then break per piece into the Order Buffer."""
        env = self.env
        rng = self.rng["cutting"]
        while True:
            tok: Token = yield m.inbox.get()
            m.busy = True
            hold = m.meter.grant(env.now)
            m.jumbos_cut += 1
            m.current = {"jumboID": tok.jumbo_id, "tokN_left": tok.tok_n,
                         "orderRange": [tok.tok_min, tok.tok_max]}
            self.log(env.now, f"kesim_{m.no}", "SEIZE", f"jumbo{tok.jumbo_id}",
                     {"n": tok.tok_n})
            yield env.timeout(tria(rng, *self.trim_tria) * S)
            build = self.jumbo_build[tok.jumbo_id]
            for _ in range(tok.tok_n):
                yield env.timeout(tria(rng, *self.break_tria) * S)
                glass = build.popleft()
                glass.my_line = m.no
                glass.t_kesim = env.now
                order = self.orders[glass.order_no]
                if order.first_cut_t < 0:
                    order.first_cut_t = env.now
                key = (glass.order_no, glass.glass_no)
                self.buf[key].append(glass)
                self.buf_g[key] += 1
                self.order_buffer_count += 1
                self.ds_order_buffer.set(self.order_buffer_count, env.now)
                m.current["tokN_left"] -= 1
                self.sig_seq.fire()
            del self.jumbo_build[tok.jumbo_id]
            self.tok_wip -= 1
            assert self.tok_wip >= 0
            self.ds_token_wip.set(self.tok_wip, env.now)
            m.meter.release(hold, env.now)
            m.busy = False
            m.current = None
            self.log(env.now, f"kesim_{m.no}", "RELEASE", f"jumbo{tok.jumbo_id}", {})
            self.sig_packer.fire()
            self.sig_dispatch.fire()

    # ---------------------------------------------------------------- edging
    def glass_flow(self, glass: Glass):
        """R8 edging with overlapped H/W seize, then temper decision (R9)."""
        env = self.env
        li = glass.my_line - 1
        meter = self.rodaj_meter[li]
        req_h = self.rodaj_h[li].request()
        yield req_h
        hold_h = meter.grant(env.now)
        yield env.timeout(glass.height / self.vfeed * S)
        req_w = self.rodaj_w[li].request()
        yield req_w
        hold_w = meter.grant(env.now)
        self.rodaj_h[li].release(req_h)
        meter.release(hold_h, env.now)
        yield env.timeout(glass.width / self.vfeed * S)
        self.rodaj_w[li].release(req_w)
        meter.release(hold_w, env.now)

        furn = self.furnace_of[glass.glass_type - 1]
        if furn == 0:
            self.to_match(glass)                      # bypass line
        else:
            self.temper_arrival(glass, furn)

    # ---------------------------------------------------------------- temper
    def temper_arrival(self, glass: Glass, furn: int) -> None:
        """R9 width-filling bed build (zero-time logic on arrival)."""
        st = self.bed_state[glass.glass_type - 1]
        cap = self.furnace_width[furn - 1]
        if not (cap >= st.w_accum + glass.width + st.w_cnt * self.glass_gap):
            self.close_bed(glass.glass_type, flush=False)
        self._bed_add(st, glass, furn)

    def _bed_add(self, st: BedState, glass: Glass, furn: int) -> None:
        if st.w_cnt == 0:
            st.open_t = self.env.now
            self.env.process(self.ft_timer(st.glass_type, st.temp_id))
        st.w_accum += glass.width
        st.w_cnt += 1
        st.glasses.append(glass)
        self.temper_build_count += 1
        self.log(self.env.now, "temper_build", "OPEN" if st.w_cnt == 1 else "ADD",
                 f"bed{st.temp_id}", {"type": st.glass_type, "w": st.w_accum})

    def close_bed(self, gtype: int, flush: bool) -> None:
        """R9 closeOpen: emit the bed batch to the furnace (R11)."""
        st = self.bed_state[gtype - 1]
        assert st is not None and st.w_cnt > 0, "closing an empty bed"
        furn = self.furnace_of[gtype - 1]
        cap = self.furnace_width[furn - 1]
        fill = st.w_accum / cap
        (self.tally_temper_fill_flush if flush else self.tally_temper_fill).record(fill)
        self.rows_temp_results.append(
            (gtype, st.bed_no, st.w_cnt, round(st.w_accum, 1), round(fill, 4), int(flush)))
        bed = Bed(temp_id=st.temp_id, glass_type=gtype, furn_target=furn,
                  glasses=st.glasses, w_accum=st.w_accum, open_t=st.open_t)
        self.temper_build_count -= len(st.glasses)
        self.log(self.env.now, "temper_build", "CLOSE", f"bed{st.temp_id}",
                 {"n": st.w_cnt, "fill": round(fill, 3), "flush": flush})
        st.bed_no += 1
        st.w_accum = 0.0
        st.w_cnt = 0
        st.glasses = []
        st.open_t = 0.0
        self.env.process(self.bed_flow(bed))

    def ft_timer(self, gtype: int, temp_id: int):
        """R10: per-bed timeout entity."""
        yield self.env.timeout(self.t_max + 0.01 * S)
        st = self.bed_state[gtype - 1]
        if st.temp_id == temp_id and st.w_cnt > 0:
            self.ft_pend = 1
            self.sig_ft.fire()

    # --------------------------------------------------------------- furnace
    def bed_flow(self, bed: Bed):
        """R11: furnace selection, entrance pitch, tunnel transit, split."""
        env = self.env
        furn = bed.furn_target
        if furn == 1:
            nq1 = len(self.entrance[0].queue)
            nq2 = len(self.entrance[1].queue)
            if not (nq1 < self.div_n or nq2 > 0):
                furn = 2                              # divert to the 1600 furnace
        heat = self.heat_time[bed.glass_type - 1]
        vspeed = self.l_heat[furn - 1] / heat         # mm/s
        pitch = self.row_gap / vspeed * S             # min
        transit = self.furn_len[furn - 1] / vspeed * S
        with self.entrance[furn - 1].request() as req:
            yield req
            hold = self.entrance_meter[furn - 1].grant(env.now)
            self.log(env.now, f"furnace_{furn}", "SEIZE", f"bed{bed.temp_id}",
                     {"pieces": len(bed.glasses)})
            yield env.timeout(pitch)
            self.entrance_meter[furn - 1].release(hold, env.now)
        load = {"tempID": bed.temp_id, "pieces": len(bed.glasses),
                "enter": env.now, "exit": env.now + transit}
        self.tunnel[furn - 1].append(load)
        yield env.timeout(transit)
        self.tunnel[furn - 1].remove(load)
        self.log(env.now, f"furnace_{furn}", "SPLIT", f"bed{bed.temp_id}", {})
        for glass in bed.glasses:                     # SPLIT -> singles to match
            self.to_match(glass)

    # ----------------------------------------------------------------- match
    def to_match(self, glass: Glass) -> None:
        """R12 Sorting #2: match panes of a unit by orderNo."""
        env = self.env
        glass.t_igu = env.now
        order = self.orders[glass.order_no]
        panes = order.pane_count
        store = self.match_store.setdefault(glass.order_no,
                                            [deque() for _ in range(panes)])
        qi = min(glass.glass_no, panes) - 1
        store[qi].append(glass)
        self.match_q_len[qi] += 1
        while all(store):
            set_glasses = tuple(q.popleft() for q in store)
            for i in range(panes):
                self.match_q_len[i] -= 1
            unit = IGUUnit(order_no=glass.order_no, glasses=set_glasses, t_match=env.now)
            self.igu_arr[glass.order_no] = self.igu_arr.get(glass.order_no, 0) + 1
            self._gate_seq += 1
            heapq.heappush(self.gate_heap, (unit.order_no, self._gate_seq, unit))
            self.ds_gate_q.set(len(self.gate_heap), env.now)
            self.log(env.now, "match", "MATCH", f"o{glass.order_no}",
                     {"unit": self.igu_arr[glass.order_no]})
            self.sig_gate.fire()
        self.ds_match_q.set(sum(self.match_q_len), env.now)

    def igu_gate(self):
        """R12 strict order-sequence gate before IGU assembly."""
        env = self.env
        while True:
            while (self.gate_heap and self.gate_heap[0][0] == self.igu_cur
                   and self.igu_arr.get(self.igu_cur, 0) > self.igu_passed.get(self.igu_cur, 0)):
                _, _, unit = heapq.heappop(self.gate_heap)
                self.igu_passed[unit.order_no] = self.igu_passed.get(unit.order_no, 0) + 1
                self.ds_gate_q.set(len(self.gate_heap), env.now)
                self.log(env.now, "igu_gate", "PASS_GATE", f"o{unit.order_no}", {})
                env.process(self.igu_unit_flow(unit))
            yield self.sig_gate.wait()

    # ------------------------------------------------------------------- IGU
    def igu_unit_flow(self, unit: IGUUnit):
        """R13: 3-station IGU assembly."""
        env = self.env
        rng = self.rng["igu"]
        with self.igu_res.request() as req:
            yield req
            hold = self.igu_meter.grant(env.now)
            self.igu_active.append(unit.order_no)
            setup = self.igu_setup if unit.order_no != self.igu_last_order else 0.0
            self.igu_last_order = unit.order_no
            yield env.timeout((setup + tria(rng, *self.igu_tria)) * S)
            self.igu_meter.release(hold, env.now)
            self.igu_active.remove(unit.order_no)
        self._complete_unit(unit)

    def _complete_unit(self, unit: IGUUnit) -> None:
        env = self.env
        order = self.orders[unit.order_no]
        order.done += 1
        order.last_igu_t = env.now
        self.igu_done_total += 1
        g1 = unit.glasses[0]
        self.glass_out += len(unit.glasses)
        cyc_order = env.now - order.t_start
        cyc_igu = env.now - unit.t_match
        cyc_kesim = env.now - g1.t_kesim
        self.tally_cyc_order_igu.record(cyc_order)
        self.tally_cyc_igu.record(cyc_igu)
        self.tally_cyc_kesim_igu.record(cyc_kesim)
        self.rows_igu_results.append(
            (unit.order_no, unit.order_no, g1.jumbo_id, order.pane_count,
             order.glass1, order.glass2, order.glass3, order.width, order.height,
             round(order.area, 4), order.order_date, order.due_date,
             round(g1.t_kesim, 3), round(unit.t_match, 3), round(env.now, 3),
             round(cyc_kesim, 3), round(cyc_igu, 3)))
        self.log(env.now, "igu_1", "DONE", f"o{unit.order_no}",
                 {"done": order.done, "need": order.qty})
        if order.done >= order.qty:
            self.orders_done += 1
        # R13: advance the strict order gate
        advanced = False
        while True:
            cur = self.orders.get(self.igu_cur)
            if cur is not None and cur.done >= cur.qty > 0:
                self.igu_cur += 1
                advanced = True
            else:
                break
        if advanced:
            self.sig_gate.fire()
            self.sig_seq.fire()

    # ------------------------------------------------------------- dashboards
    def series_sampler(self):
        env = self.env
        period = 5.0
        while True:
            yield env.timeout(period)
            now = env.now
            thr = (self.igu_done_total - self._last_igu_total) * (60.0 / period)
            self._last_igu_total = self.igu_done_total
            self.series.append({
                "sim_min": round(now, 1),
                "order_buffer": self.order_buffer_count,
                "token_wip": self.tok_wip,
                "hold_glass": self.pool_count,
                "match_q": sum(self.match_q_len),
                "igu_gate_q": len(self.gate_heap),
                "igu_done": self.igu_done_total,
                "throughput_h": round(thr, 1),
                "util": {
                    "kesim_1": round(self.machines[0].meter.utilization(now), 4),
                    "kesim_2": round(self.machines[1].meter.utilization(now), 4)
                    if len(self.machines) > 1 else 0.0,
                    "igu_1": round(self.igu_meter.utilization(now), 4),
                    "furnace_1000": round(self.entrance_meter[0].utilization(now), 4),
                    "furnace_1600": round(self.entrance_meter[1].utilization(now), 4),
                },
            })

    # -------------------------------------------------------------- snapshot
    def snapshot(self) -> dict:
        """Live state frame for the SCADA screen (B.2 schema)."""
        now = self.env.now
        machines = {}
        for m in self.machines:
            machines[f"kesim_{m.no}"] = {
                "state": "BUSY" if m.busy else ("STARVED" if self.starve else "IDLE"),
                "job": m.current,
                "util": round(m.meter.utilization(now), 4),
            }
        furnaces = {}
        for fi, name in ((0, "furnace_1000"), (1, "furnace_1600")):
            loads = self.tunnel[fi]
            cur = None
            if loads:
                nxt = min(loads, key=lambda x: x["exit"])
                cur = {"tempID": nxt["tempID"], "pieces": nxt["pieces"],
                       "exit_eta_min": round(nxt["exit"] - now, 2)}
            furnaces[name] = {
                "state": "RUNNING" if (loads or self.entrance_meter[fi].held) else "IDLE",
                "loads_in_tunnel": len(loads),
                "entry_queue": len(self.entrance[fi].queue),
                "current": cur,
                "util": round(self.entrance_meter[fi].utilization(now), 4),
                "loads": [{"tempID": l["tempID"], "pieces": l["pieces"],
                           "pos": min(1.0, max(0.0, (now - l["enter"]) /
                                               max(l["exit"] - l["enter"], 1e-9)))}
                          for l in loads],
            }
        stations = {**machines, **furnaces}
        for i, meter in enumerate(self.rodaj_meter):
            stations[f"rodaj_{i+1}"] = {
                "state": "BUSY" if meter.held else "IDLE",
                "util": round(meter.utilization(now), 4),
            }
        slots = [{"busy": True, "orderNo": o} for o in self.igu_active]
        slots += [{"busy": False, "orderNo": None}] * (self.igu_res.capacity - len(slots))
        stations["igu_1"] = {"state": "BUSY" if self.igu_active else
                             ("STARVED" if not self.gate_heap else "IDLE"),
                             "stations": slots,
                             "util": round(self.igu_meter.utilization(now), 4)}
        elapsed_h = now / 60.0 if now > 0 else 1e-9
        return {
            "sim_min": round(now, 2),
            "sim_clock": self.sim_clock(now),
            "day": self.v_day,
            "progress": round(now / self.T_end, 4),
            "stations": stations,
            "buffers": {
                "hold_glass": self.pool_count,
                "token_buffer": len(self.token_buffer),
                "order_buffer": self.order_buffer_count,
                "temper_build": self.temper_build_count,
                "match_q": list(self.match_q_len),
                "igu_order_q": len(self.gate_heap),
            },
            "counters": {
                "igu_done": self.igu_done_total,
                "orders_done": self.orders_done,
                "orders_created": self.ord_cnt,
                "cur_order": self.cur_order,
                "igu_cur_order": self.igu_cur,
                "starve": self.starve,
                "tok_wip": self.tok_wip,
                "glass_in": self.glass_in,
                "glass_out": self.glass_out,
            },
            "kpis": {
                "jumbo_fill_avg": round(self._combined_fill(
                    self.tally_jumbo_fill, self.tally_jumbo_fill_flush), 4),
                "temper_fill_avg": round(self._combined_fill(
                    self.tally_temper_fill, self.tally_temper_fill_flush), 4),
                "throughput_per_h": round(self.igu_done_total / elapsed_h, 1),
                "otd_pct": self._otd_pct(),
            },
        }

    @staticmethod
    def _combined_fill(a: Tally, b: Tally) -> float:
        n = a.n + b.n
        return (a.total + b.total) / n if n else 0.0

    def _otd_pct(self) -> float:
        done = [o for o in self.orders.values() if o.done >= o.qty]
        if not done:
            return 100.0
        # order completes on working day floor(last_igu_t/day_min)+1
        on_time = sum(1 for o in done
                      if (int(o.last_igu_t // self.day_min) + 1) <= o.due_date)
        return round(100.0 * on_time / len(done), 1)

    # ------------------------------------------------------------------- run
    def run(self, until: float | None = None) -> None:
        self.env.run(until=until if until is not None else self.T_end)
