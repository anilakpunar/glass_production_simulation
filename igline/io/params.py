"""Parameter loading / merging / freezing.

Parameters live in config/default_params.yaml; a run may override any subset
via another YAML file or a dict (e.g. from the UI). The merged set is frozen
to runs/<run_id>/params.yaml so every run is reproducible.
"""
from __future__ import annotations

import copy
import csv
import pathlib
from typing import Any

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_PARAMS_FILE = ROOT / "config" / "default_params.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_params(override_file: str | pathlib.Path | None = None,
                overrides: dict | None = None) -> dict[str, Any]:
    with open(DEFAULT_PARAMS_FILE) as f:
        params = yaml.safe_load(f)
    if override_file:
        with open(override_file) as f:
            file_over = yaml.safe_load(f) or {}
        params = _deep_merge(params, file_over)
    if overrides:
        params = _deep_merge(params, overrides)
    validate_params(params)
    return params


def validate_params(p: dict) -> None:
    t = p["temper"]
    if len(t["furnace_of"]) != 12 or len(t["heat_time_s"]) != 12:
        raise ValueError("temper.furnace_of and temper.heat_time_s must have 12 entries")
    if any(f not in (0, 1, 2) for f in t["furnace_of"]):
        raise ValueError("temper.furnace_of entries must be 0, 1 or 2")
    if len(t["furnace_width_mm"]) != 2:
        raise ValueError("temper.furnace_width_mm must have 2 entries")
    for key in ("trim_tria_s", "break_tria_s"):
        tri = p["cutting"][key]
        if not (tri[0] <= tri[1] <= tri[2]):
            raise ValueError(f"cutting.{key} must satisfy min <= mode <= max")
    if p["orders"]["daily_target"] <= 0:
        raise ValueError("orders.daily_target must be positive")


def freeze_params(params: dict, path: str | pathlib.Path) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.safe_dump(params, f, sort_keys=False, allow_unicode=True)


def load_product_mix(path: str | pathlib.Path) -> tuple[list[float], list[int]]:
    """Read the DISC product table (cum_prob, code). Validates monotonicity."""
    path = pathlib.Path(path)
    if not path.is_absolute():
        path = ROOT / path
    cum_probs: list[float] = []
    codes: list[int] = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            cum_probs.append(float(row["cum_prob"]))
            codes.append(int(row["code"]))
    if not cum_probs:
        raise ValueError(f"empty product mix file: {path}")
    if any(b < a for a, b in zip(cum_probs, cum_probs[1:])):
        raise ValueError("product mix cum_prob column must be non-decreasing")
    if abs(cum_probs[-1] - 1.0) > 1e-6:
        raise ValueError("product mix cum_prob must end at 1.0")
    cum_probs[-1] = 1.0
    return cum_probs, codes


def decode_product(code: int) -> dict[str, Any]:
    """Decode an Arena product code (R2).

    width  = (code mod 1e7) div 1e4 ; height = code mod 1e4
    g      = code div 1e7 ; glass3 = g mod 100 ; glass2 = (g div 100) mod 10 ;
    glass1 = g div 1000. glass3 == 12 -> double glazing (2 panes).
    """
    wh = code % 10**7
    height = wh % 10**4
    width = wh // 10**4
    g = code // 10**7
    glass3 = g % 100
    glass2 = (g // 100) % 10
    glass1 = g // 1000
    area = width * height / 1e6
    pane_count = 2 if glass3 == 12 else 3
    return {
        "code": code, "width": width, "height": height, "area": area,
        "glass1": glass1, "glass2": glass2, "glass3": glass3,
        "pane_count": pane_count,
    }
