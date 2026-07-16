"""Entity dataclasses for the IGU line model (R2-R13)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Order:
    order_no: int
    code: int
    glass1: int
    glass2: int
    glass3: int
    width: int
    height: int
    area: float
    qty: int
    order_date: int          # vDay at creation
    due_date: int            # order_date + Gamma days
    t_start: float           # sim minute of creation
    pane_count: int          # 2 if glass3 == 12 else 3
    # progress / result fields
    first_cut_t: float = -1.0
    last_igu_t: float = -1.0
    done: int = 0            # completed IGU units


@dataclass(slots=True)
class Glass:
    order_no: int
    glass_no: int            # pane index 1..3
    glass_type: int          # 1..12 (glassN code)
    seq: int                 # orderNo*100000 + pieceCounter*10 + 1
    width: int
    height: int
    area: float
    due_date: int
    my_line: int = 0         # cutting machine that produced it (1/2)
    t_kesim: float = -1.0
    jumbo_id: int = 0
    t_igu: float = -1.0      # set on arrival at match (Sorting #2)


@dataclass(slots=True)
class Token:
    """Cutting token produced when a jumbo closes (R4)."""
    jumbo_id: int
    glass_type: int
    tok_n: int
    tok_min: int
    tok_max: int


@dataclass(slots=True)
class Bed:
    """Temper bed (width-filling batch, R9)."""
    temp_id: int
    glass_type: int
    furn_target: int         # 1 (1050 mm) or 2 (1600 mm)
    glasses: list[Glass] = field(default_factory=list)
    w_accum: float = 0.0
    open_t: float = 0.0


@dataclass(slots=True)
class IGUUnit:
    order_no: int
    glasses: tuple[Glass, ...]
    t_match: float           # when the set was matched (tIGU)
