"""Random-variate helpers matching Arena's distribution semantics.

All samplers take a ``numpy.random.Generator`` so each model flow can own an
independent spawned stream (deterministic replications, parameter changes in
one flow do not disturb the sampling of another).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


def tria(rng: np.random.Generator, a: float, m: float, b: float) -> float:
    """Arena TRIA(min, mode, max)."""
    return float(rng.triangular(a, m, b))


def logn_arena(rng: np.random.Generator, mean: float, sd: float) -> float:
    """Arena LOGN(LogMean, LogStd): parameters are the *arithmetic* mean and
    std dev of the lognormal variate itself; convert to log-space mu/sigma."""
    m2 = mean * mean
    s2 = sd * sd
    mu = math.log(m2 / math.sqrt(m2 + s2))
    sigma = math.sqrt(math.log(1.0 + s2 / m2))
    return float(rng.lognormal(mu, sigma))


def gamma_arena(rng: np.random.Generator, scale: float, shape: float) -> float:
    """Arena GAMM(beta, alpha) = Gamma(shape=alpha, scale=beta)."""
    return float(rng.gamma(shape, scale))


def expo(rng: np.random.Generator, mean: float) -> float:
    return float(rng.exponential(mean))


@dataclass
class Disc:
    """Arena DISC empirical discrete distribution.

    ``cum_probs`` must be non-decreasing and end at 1.0; ``values`` are the
    outcomes returned for each cumulative bucket.
    """

    cum_probs: list[float]
    values: list[int]

    def __post_init__(self) -> None:
        if len(self.cum_probs) != len(self.values):
            raise ValueError("cum_probs and values length mismatch")
        if any(b < a for a, b in zip(self.cum_probs, self.cum_probs[1:])):
            raise ValueError("cum_probs must be non-decreasing")
        if abs(self.cum_probs[-1] - 1.0) > 1e-9:
            raise ValueError("cum_probs must end at 1.0")
        self._cum = np.asarray(self.cum_probs)

    def sample(self, rng: np.random.Generator) -> int:
        u = rng.random()
        idx = int(np.searchsorted(self._cum, u, side="left"))
        return self.values[min(idx, len(self.values) - 1)]


def spawn_streams(seed: int, names: list[str]) -> dict[str, np.random.Generator]:
    """One independent child stream per named flow, all derived from ``seed``."""
    ss = np.random.SeedSequence(seed)
    children = ss.spawn(len(names))
    return {n: np.random.Generator(np.random.PCG64(c)) for n, c in zip(names, children)}
