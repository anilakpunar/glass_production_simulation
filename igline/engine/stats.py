"""Statistics collectors: Arena Tally / DStat equivalents plus KPI helpers."""
from __future__ import annotations

import math
from dataclasses import dataclass, field


class Tally:
    """Observation-based statistic (Arena TALLIES). Optionally keeps raw
    values for histograms."""

    __slots__ = ("name", "n", "total", "sq", "vmin", "vmax", "keep", "values")

    def __init__(self, name: str, keep_values: bool = False):
        self.name = name
        self.n = 0
        self.total = 0.0
        self.sq = 0.0
        self.vmin = math.inf
        self.vmax = -math.inf
        self.keep = keep_values
        self.values: list[float] = []

    def record(self, v: float) -> None:
        self.n += 1
        self.total += v
        self.sq += v * v
        if v < self.vmin:
            self.vmin = v
        if v > self.vmax:
            self.vmax = v
        if self.keep:
            self.values.append(v)

    @property
    def mean(self) -> float:
        return self.total / self.n if self.n else 0.0

    @property
    def std(self) -> float:
        if self.n < 2:
            return 0.0
        var = (self.sq - self.total * self.total / self.n) / (self.n - 1)
        return math.sqrt(max(var, 0.0))

    def summary(self) -> dict:
        return {"n": self.n, "mean": self.mean, "std": self.std,
                "min": self.vmin if self.n else 0.0,
                "max": self.vmax if self.n else 0.0}


class DStat:
    """Time-weighted statistic (Arena DSTATS) for queue lengths / levels."""

    __slots__ = ("name", "value", "last_t", "integral", "vmax", "start_t")

    def __init__(self, name: str, t0: float = 0.0, v0: float = 0.0):
        self.name = name
        self.value = v0
        self.last_t = t0
        self.start_t = t0
        self.integral = 0.0
        self.vmax = v0

    def set(self, v: float, now: float) -> None:
        self.integral += self.value * (now - self.last_t)
        self.value = v
        self.last_t = now
        if v > self.vmax:
            self.vmax = v

    def add(self, dv: float, now: float) -> None:
        self.set(self.value + dv, now)

    def mean(self, now: float) -> float:
        span = now - self.start_t
        if span <= 0:
            return self.value
        return (self.integral + self.value * (now - self.last_t)) / span

    def summary(self, now: float) -> dict:
        return {"mean": self.mean(now), "max": self.vmax, "final": self.value}


class BusyMeter:
    """Utilization accounting for a resource with a fixed capacity.

    Processes call ``grant()`` when a unit starts being held and ``release()``
    with the returned hold id when it is freed. Open holds at the end of the
    run are included in the utilization figure.
    """

    __slots__ = ("name", "capacity", "busy_time", "open", "_next")

    def __init__(self, name: str, capacity: int):
        self.name = name
        self.capacity = capacity
        self.busy_time = 0.0
        self.open: dict[int, float] = {}
        self._next = 0

    @property
    def held(self) -> int:
        return len(self.open)

    def grant(self, now: float) -> int:
        hid = self._next
        self._next += 1
        self.open[hid] = now
        return hid

    def release(self, hid: int, now: float) -> None:
        self.busy_time += now - self.open.pop(hid)

    def utilization(self, now: float) -> float:
        if now <= 0:
            return 0.0
        open_extra = sum(now - t for t in self.open.values())
        return (self.busy_time + open_extra) / (now * self.capacity)


@dataclass
class TimePoint:
    """One dashboard time-series sample."""
    sim_min: float
    data: dict = field(default_factory=dict)


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    k = (len(sorted_vals) - 1) * p
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return sorted_vals[lo]
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)
