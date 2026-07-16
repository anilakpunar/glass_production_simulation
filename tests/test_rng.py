import numpy as np
import pytest

from igline.engine.rng import Disc, expo, gamma_arena, logn_arena, spawn_streams, tria

N = 200_000


@pytest.fixture
def rng():
    return np.random.default_rng(123)


def test_tria_moments(rng):
    xs = np.array([tria(rng, 30, 35, 45) for _ in range(N // 10)])
    assert abs(xs.mean() - (30 + 35 + 45) / 3) < 0.15
    assert xs.min() >= 30 and xs.max() <= 45


def test_logn_arena_matches_arithmetic_params(rng):
    xs = np.array([logn_arena(rng, 340, 650) for _ in range(N)])
    assert xs.mean() == pytest.approx(340, rel=0.03)
    assert xs.std() == pytest.approx(650, rel=0.08)
    assert (xs > 0).all()


def test_gamma_arena_moments(rng):
    xs = np.array([gamma_arena(rng, 30.3, 1.81) for _ in range(N)])
    assert xs.mean() == pytest.approx(1.81 * 30.3, rel=0.02)
    assert xs.var() == pytest.approx(1.81 * 30.3**2, rel=0.05)


def test_expo(rng):
    xs = np.array([expo(rng, 0.5) for _ in range(N // 4)])
    assert xs.mean() == pytest.approx(0.5, rel=0.05)


def test_disc_frequencies(rng):
    d = Disc([0.2, 0.5, 1.0], [10, 20, 30])
    xs = np.array([d.sample(rng) for _ in range(N // 4)])
    freq = {v: (xs == v).mean() for v in (10, 20, 30)}
    assert freq[10] == pytest.approx(0.2, abs=0.01)
    assert freq[20] == pytest.approx(0.3, abs=0.01)
    assert freq[30] == pytest.approx(0.5, abs=0.01)


def test_disc_validation():
    with pytest.raises(ValueError):
        Disc([0.5, 0.4, 1.0], [1, 2, 3])
    with pytest.raises(ValueError):
        Disc([0.5, 0.9], [1, 2])


def test_spawn_streams_independent_and_deterministic():
    a = spawn_streams(42, ["orders", "cutting"])
    b = spawn_streams(42, ["orders", "cutting"])
    assert a["orders"].random() == b["orders"].random()
    # different names -> different sequences
    c = spawn_streams(42, ["orders", "cutting"])
    assert c["orders"].random() != c["cutting"].random()
