"""Shelf (strip) nesting for jumbo plates - pure functions, unit-testable.

Scenario 3 places pieces on horizontal strips of an open jumbo per glass
type. Coordinates follow the Arena variables:

  sh_x   : occupied width of the current strip (vShX)
  sh_h   : height of the current strip (vShH, includes kerf of tallest piece)
  used_y : total height of closed strips (vUsedY)

A piece of w x h (+kerf on each dimension) fits
  - the current strip if  sh_x + w + kerf <= JW  and  used_y + max(sh_h, h + kerf) <= JH
  - a new strip     if  w + kerf <= JW          and  used_y + sh_h + h + kerf <= JH
Rotation (swap w/h) is allowed when rot_ok.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class JumboState:
    """Open-jumbo state for one glass type (vShX, vShH, vUsedY, vAccum, vCnt,
    vJMin, vJMax, vJOpenT, vJumboNo)."""
    glass_type: int
    jumbo_no: int = 0            # Arena vJumboNo starts at 0
    sh_x: float = 0.0
    sh_h: float = 0.0
    used_y: float = 0.0
    accum: float = 0.0       # accumulated glass area (m^2)
    cnt: int = 0
    j_min: int = 0
    j_max: int = 0
    open_t: float = 0.0
    piece_seqs: list[int] = field(default_factory=list)

    @property
    def jumbo_id(self) -> int:
        return self.glass_type * 10000 + self.jumbo_no


# ---------------------------------------------------------------- fit tests

def fit_strip(st: JumboState, w: float, h: float, jw: float, jh: float,
              kerf: float, rot_ok: bool) -> tuple[float, float] | None:
    """Placement (pW, pH) on the current strip, or None. Tries normal
    orientation first, then rotated (Arena decision order)."""
    if st.sh_x + w + kerf <= jw and st.used_y + max(st.sh_h, h + kerf) <= jh:
        return (w, h)
    if rot_ok and st.sh_x + h + kerf <= jw and st.used_y + max(st.sh_h, w + kerf) <= jh:
        return (h, w)
    return None


def fit_new_strip(st: JumboState, w: float, h: float, jw: float, jh: float,
                  kerf: float, rot_ok: bool) -> tuple[float, float] | None:
    """Placement (pW, pH) opening a new strip, or None."""
    if w + kerf <= jw and st.used_y + st.sh_h + h + kerf <= jh:
        return (w, h)
    if rot_ok and h + kerf <= jw and st.used_y + st.sh_h + w + kerf <= jh:
        return (h, w)
    return None


# ---------------------------------------------------------------- mutation

def start_new_strip(st: JumboState) -> None:
    st.used_y += st.sh_h
    st.sh_h = 0.0
    st.sh_x = 0.0


def add_open(st: JumboState, pw: float, ph: float, area: float, order_no: int,
             seq: int, kerf: float, now: float) -> int:
    """Place a piece (already oriented) on the current strip; returns jumbo_id."""
    if st.cnt == 0:
        st.open_t = now
        st.j_min = order_no
        st.j_max = order_no
    st.sh_h = max(st.sh_h, ph + kerf)
    st.sh_x += pw + kerf
    st.accum += area
    st.cnt += 1
    st.j_min = min(st.j_min, order_no)
    st.j_max = order_no           # Arena overwrites with the latest order
    st.piece_seqs.append(seq)
    return st.jumbo_id


def reset_after_close(st: JumboState) -> None:
    st.jumbo_no += 1
    st.sh_x = 0.0
    st.sh_h = 0.0
    st.used_y = 0.0
    st.accum = 0.0
    st.cnt = 0
    st.j_min = 0
    st.j_max = 0
    st.open_t = 0.0
    st.piece_seqs = []
