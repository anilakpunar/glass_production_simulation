"""Unit tests for the pure shelf-nesting functions (R3)."""
from igline.engine import nesting
from igline.engine.nesting import JumboState

JW, JH, KERF = 6000, 3210, 5


def st(**kw):
    s = JumboState(glass_type=1)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_fit_strip_normal():
    s = st()
    assert nesting.fit_strip(s, 1000, 800, JW, JH, KERF, True) == (1000, 800)


def test_fit_strip_boundary():
    s = st(sh_x=4995)
    # 4995 + 1000 + 5 = 6000 -> fits exactly
    assert nesting.fit_strip(s, 1000, 800, JW, JH, KERF, True) == (1000, 800)
    s = st(sh_x=4996)
    assert nesting.fit_strip(s, 1000, 800, JW, JH, KERF, False) is None


def test_fit_strip_rotation():
    # too wide normally, fits rotated
    s = st(sh_x=5000)
    assert nesting.fit_strip(s, 1500, 900, JW, JH, KERF, True) == (900, 1500)
    assert nesting.fit_strip(s, 1500, 900, JW, JH, KERF, False) is None


def test_fit_strip_height_growth_respects_jumbo():
    # current strip is 500 high, piece of 800 grows the strip; used_y forbids it
    s = st(sh_h=500, used_y=2500)
    # used_y + max(500, 800+5) = 3305 > 3210 -> no
    assert nesting.fit_strip(s, 400, 800, JW, JH, KERF, False) is None
    # shorter piece within existing strip height is fine
    assert nesting.fit_strip(s, 400, 300, JW, JH, KERF, False) == (400, 300)


def test_fit_new_strip():
    s = st(sh_x=5900, sh_h=805, used_y=0)
    # no room on strip, but a new strip fits: 0+805+800+5=1610 <= 3210
    assert nesting.fit_strip(s, 800, 800, JW, JH, KERF, False) is None
    assert nesting.fit_new_strip(s, 800, 800, JW, JH, KERF, False) == (800, 800)


def test_fit_new_strip_rotation_only():
    s = st(sh_h=200, used_y=2400)
    # normal: 2400+200+700+5 = 3305 > 3210; rotated (400 high): 3005 <= 3210
    assert nesting.fit_new_strip(s, 400, 700, JW, JH, KERF, True) == (700, 400)
    assert nesting.fit_new_strip(s, 400, 700, JW, JH, KERF, False) is None


def test_add_open_updates_state_and_id():
    s = st()
    # Arena vJumboNo starts at 0 -> first jumboID = type*10000 + 0
    jid = nesting.add_open(s, 1000, 800, 0.8, order_no=7, seq=700011, kerf=KERF, now=12.5)
    assert jid == 1 * 10000 + 0
    assert s.sh_x == 1005 and s.sh_h == 805 and s.cnt == 1
    assert s.j_min == s.j_max == 7 and s.open_t == 12.5
    nesting.add_open(s, 500, 400, 0.2, order_no=3, seq=300011, kerf=KERF, now=13.0)
    assert s.j_min == 3 and s.j_max == 3     # Arena overwrites vJMax with the latest order
    assert s.sh_x == 1510 and s.sh_h == 805  # strip height keeps the max
    assert s.open_t == 12.5                  # first piece sets open time


def test_start_new_strip_and_reset():
    s = st(sh_x=3000, sh_h=900, used_y=1000)
    nesting.start_new_strip(s)
    assert (s.sh_x, s.sh_h, s.used_y) == (0, 0, 1900)
    s.cnt = 5
    s.jumbo_no = 4
    nesting.reset_after_close(s)
    assert s.jumbo_no == 5 and s.cnt == 0 and s.used_y == 0 and s.accum == 0


def test_real_product_mix_decode():
    """The shipped table is the verbatim Arena 203$ DISC block."""
    from igline.io.params import decode_product, load_product_mix
    cum, codes = load_product_mix("data/product_mix.csv")
    assert len(codes) == 66
    assert cum[0] == 0.06246 and codes[0] == 15125261778
    assert cum[-1] == 1.0 and codes[-1] == 13124740778
    d = decode_product(codes[0])
    assert (d["glass1"], d["glass2"], d["glass3"]) == (1, 5, 12)
    assert (d["width"], d["height"]) == (526, 1778)
    # rows with glass3 != 12 exist (e.g. 75034861612) and are forced to
    # double glazing by the engine (Arena mod 116$)
    d2 = decode_product(75034861612)
    assert d2["glass3"] == 3 and d2["glass1"] == 7 and d2["glass2"] == 5
    assert (d2["width"], d2["height"]) == (486, 1612)
