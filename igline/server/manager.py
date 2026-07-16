"""Run manager: engine in a worker thread with live speed control.

Speeds are sim-minutes per wall-minute multipliers: 1, 10, 60, 300 or "max"
(as fast as possible, frame-skipping). The engine advances in small chunks;
after each chunk the latest snapshot is published for websocket broadcast.
"""
from __future__ import annotations

import pathlib
import threading
import time
from collections import deque
from typing import Any

from igline.engine.model import Line
from igline.io import writers
from igline.io.params import ROOT, freeze_params
from igline.io.rundb import index_run
from igline.runner import aggregate_replications, make_run_id

ALARM_EVENTS = {"FLUSH", "STARVE", "STARVE_END", "THRESHOLD"}


class RunManager:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._pause = threading.Event()      # set -> paused
        self._stop = threading.Event()
        self._step = threading.Event()
        self.speed: float | str = 60
        self.state = "idle"                  # idle|running|paused|finished|error
        self.error: str | None = None
        self.run_id: str | None = None
        self.run_dir: pathlib.Path | None = None
        self.mode = "live"
        self.snapshot: dict | None = None
        self.snapshot_seq = 0
        self.events_tail: deque = deque(maxlen=400)
        self.alarms: deque = deque(maxlen=200)
        self.summary: dict | None = None
        self.replication_info: dict = {}
        self._line: Line | None = None

    # ------------------------------------------------------------- control
    def start(self, params: dict, mode: str = "live",
              speed: float | str = 60) -> str:
        with self._lock:
            if self.state in ("running", "paused"):
                raise RuntimeError("a run is already active")
            self._stop.clear()
            self._pause.clear()
            self._step.clear()
            self.mode = mode
            self.speed = "max" if mode == "headless" else speed
            self.state = "running"
            self.error = None
            self.summary = None
            self.events_tail.clear()
            self.alarms.clear()
            self.run_id = make_run_id("ui")
            self.run_dir = ROOT / "runs" / self.run_id
            self._thread = threading.Thread(
                target=self._work, args=(params,), daemon=True)
            self._thread.start()
            return self.run_id

    def pause(self):
        if self.state == "running":
            self._pause.set()
            self.state = "paused"

    def resume(self):
        if self.state == "paused":
            self._pause.clear()
            self.state = "running"

    def step(self):
        if self.state == "paused":
            self._step.set()

    def set_speed(self, speed: float | str):
        self.speed = speed

    def stop(self):
        self._stop.set()
        self._pause.clear()

    def status(self) -> dict:
        return {
            "state": self.state, "run_id": self.run_id, "mode": self.mode,
            "speed": self.speed, "error": self.error,
            "replication": self.replication_info,
            "has_summary": self.summary is not None,
        }

    # -------------------------------------------------------------- worker
    def _work(self, params: dict) -> None:
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            freeze_params(params, self.run_dir / "params.yaml")
            n_rep = int(params["run"].get("replications", 1) or 1)
            if self.mode == "live":
                n_rep = 1
            base_seed = int(params["run"].get("seed", 42))
            summaries = []
            for rep in range(n_rep):
                if self._stop.is_set():
                    break
                self.replication_info = {"current": rep + 1, "total": n_rep}
                rep_dir = self.run_dir if n_rep == 1 else self.run_dir / f"rep{rep+1:02d}"
                s = self._run_one(params, base_seed + rep, rep_dir)
                if s is not None:
                    summaries.append(s)
            if summaries:
                agg = aggregate_replications(summaries) if len(summaries) > 1 else None
                self.summary = {"aggregate": agg, "replications": summaries} \
                    if agg else summaries[0]
                if len(summaries) > 1:
                    writers.write_summary(self.summary, self.run_dir)
                index_run(self.run_id, params, summaries,
                          agg or {}, str(self.run_dir))
            self.state = "finished" if not self._stop.is_set() else "idle"
            if self._stop.is_set() and summaries:
                self.state = "finished"
        except Exception as exc:  # pragma: no cover - surfaced to the UI
            import traceback
            traceback.print_exc()
            self.error = f"{type(exc).__name__}: {exc}"
            self.state = "error"

    def _run_one(self, params: dict, seed: int, out_dir: pathlib.Path):
        out_dir.mkdir(parents=True, exist_ok=True)
        elog = writers.EventLog(out_dir / "event_log.jsonl",
                                enabled=params["run"].get("event_log", True))

        def log(sim_min, station, event, entity, payload):
            elog(sim_min, station, event, entity, payload)
            row = {"sim_min": round(sim_min, 2), "station": station,
                   "event": event, "entity": entity, "payload": payload}
            self.events_tail.append(row)
            if event in ALARM_EVENTS:
                self.alarms.append(row)

        t0 = time.perf_counter()
        line = Line(params, seed=seed, event_log=log)
        self._line = line
        T = line.T_end
        last_pub = 0.0
        while line.env.now < T:
            if self._stop.is_set():
                break
            if self._pause.is_set():
                self._publish(line)
                if self._step.is_set():
                    self._step.clear()
                    self._advance(line, min(line.env.now + 0.5, T))
                else:
                    time.sleep(0.05)
                    continue
            else:
                speed = self.speed
                if speed == "max":
                    chunk = 2.0
                    self._advance(line, min(line.env.now + chunk, T))
                else:
                    wall_frame = 0.25                      # s per UI frame
                    chunk = max(float(speed) * wall_frame / 60.0, 0.002)
                    t_frame = time.perf_counter()
                    self._advance(line, min(line.env.now + chunk, T))
                    elapsed = time.perf_counter() - t_frame
                    if elapsed < wall_frame:
                        time.sleep(wall_frame - elapsed)
            now_wall = time.perf_counter()
            if now_wall - last_pub >= 0.1:
                self._publish(line)
                last_pub = now_wall
        wall = time.perf_counter() - t0
        self._publish(line, final=True)
        if self._stop.is_set() and line.env.now < T:
            elog.close()
            return None
        summary = writers.build_summary(line, seed, wall)
        writers.write_csvs(line, out_dir)
        writers.write_order_table(line, out_dir)
        writers.write_series(line, out_dir)
        writers.write_summary(summary, out_dir)
        import json
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
        elog.close()
        return summary

    @staticmethod
    def _advance(line: Line, until: float) -> None:
        if until > line.env.now:
            line.run(until=until)

    def _publish(self, line: Line, final: bool = False) -> None:
        snap = line.snapshot()
        snap["events_tail"] = list(self.events_tail)[-60:]
        snap["alarms"] = list(self.alarms)[-40:]
        snap["run"] = self.status()
        snap["final"] = final
        self.snapshot = snap
        self.snapshot_seq += 1


manager = RunManager()
