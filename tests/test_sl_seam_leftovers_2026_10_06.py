"""The seam, what was left of it: lane SL of the hostile pass's wave 5.

KD's check (findings 11 and 12) found readers outside K-16's list that
still read a longitude a hair under 0 Aries raw: -1e-16 is 0 Aries, but
`-1e-16 % 360.0` is 360.0 and `-1e-16 % 30.0` is 30.0, so a reader that
took its degree in the sign, or its start, from the raw value read the
seam as Aries' far edge (or Pisces), and a value printed raw printed a
signed zero. Each reader below must answer at -1e-16 exactly as at 0.0.
Where a value can move, it is pinned by value; where none can today, by a
spy on the sign the reader asks for (as KD pinned its guards).
"""
import copy

import pytest
import swisseph as swe

from conftest import assert_no_exception, make_app, table_nodes

SEAM = -1e-16


def _florence(engine):
    return engine["calculate_traditional_chart_jd"](swe.julday(1240, 5, 23, 13.75, swe.JUL_CAL), 43.7792, 11.2463)


def _placed(chart, **longitudes):
    data = copy.deepcopy(chart["planetary_data"])
    for name, lon in longitudes.items():
        data[name]["longitude"] = lon
    return data


# --- By value -----------------------------------------------------------------

def test_the_small_days_open_at_the_seam_as_at_0_aries(engine):
    """_pn4_distribute took its start `% 360.0`, which makes -1e-16 into
    360.0: the bound window then reached back to the last bound of Pisces
    and the small days opened with Mars by sextile behind the Ascendant,
    where 0 Aries opens with the distributor alone (PN IV IX.7, 30)."""
    data = _florence(engine)["planetary_data"]
    at_zero = engine["pn4_small_days"](data, 0.0)
    assert at_zero[0]["opened_by"] == "at the revolution: the distributor alone"     # premise
    assert engine["pn4_small_days"](data, SEAM) == at_zero
    sign_window = lambda start: engine["_pn4_distribute"](data, start, lambda lon: lon % 360.0, 360.0, "t")
    at_seam = sign_window(SEAM)
    assert at_seam == sign_window(0.0)
    assert at_seam[0]["from_lon"] == 0.0


def test_the_moon_begins_her_ninth_parts_at_the_seam_as_at_0_aries(engine):
    """pn4_ix7_moon_start took her degree in the sign raw: 30.0 at -1e-16,
    so she began at the end of Aries' ninth-parts (30.4375 days)."""
    assert engine["pn4_ix7_moon_start"](0.0) == ("Aries", 0.0)                       # premise
    assert engine["pn4_ix7_moon_start"](SEAM) == ("Aries", 0.0)


def test_prosperity_keeps_its_own_hands_row_at_the_seam(engine):
    """evaluate_prosperity read the first triplicity lord's bound from the
    raw degree in the sign; at -1e-16 (30.0 in Aries) no bound held it, and
    Sahl 2.21, 1's row went. On the default chart the Lot of Fortune's
    first triplicity lord is Saturn; at 0 Aries he is in Jupiter's bound,
    in the seventh, looking at the Lot."""
    chart = _florence(engine)
    at_zero = engine["evaluate_prosperity"](dict(chart, planetary_data=_placed(chart, Saturn=0.0)))
    own_hands = [row for row in at_zero if "2.21, 1" in repr(row)]
    assert own_hands and "in the bound of Jupiter" in repr(own_hands)                # premise
    assert engine["evaluate_prosperity"](dict(chart, planetary_data=_placed(chart, Saturn=SEAM))) == at_zero


def test_the_natural_connections_print_0_aries_at_the_seam(engine):
    """evaluate_abu_natural_connections printed the degree in the sign raw:
    `Moon 30.0° Ari` for a Moon at -1e-16 (Saturn placed in Virgo, so the
    Moon and he stand in one of the enumerated sign pairs)."""
    chart = _florence(engine)
    moon = lambda lon: [row for row in engine["evaluate_abu_natural_connections"](_placed(chart, Moon=lon, Saturn=150.0))
                        if "Moon" in row["Pair"]]
    at_zero = moon(0.0)
    assert at_zero and all(row["Degrees"].startswith("Moon 0.0° Ari") for row in at_zero)  # premise
    assert moon(SEAM) == at_zero


def test_the_semi_arc_terms_print_no_signed_zero(engine):
    """The Timing page's arc and its terms: the significator's declination
    printed `-0.00°` for a degree at -1e-16 (KD's check, finding 12)."""
    chart = _florence(engine)
    rows = lambda lon: engine["pn4_semi_arc_terms_rows"](lon, chart["obliquity"], chart["geo_lat"], chart["armc"], [], None)
    at_zero = rows(0.0)
    assert at_zero and at_zero[0]["Declination"] == "0.00°"                            # premise
    assert rows(SEAM) == at_zero


def _page_tables(engine, monkeypatch, page, moon):
    at = make_app(page=page)
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.session_state["_target_date"] = "2026-09-17"
    original = engine.calculate_traditional_chart_jd

    def patched(*args, **kwargs):
        chart = copy.deepcopy(original(*args, **kwargs))
        chart["planetary_data"]["Moon"]["longitude"] = moon
        return chart
    monkeypatch.setattr(engine, "calculate_traditional_chart_jd", patched)
    at.run(timeout=300)
    monkeypatch.setattr(engine, "calculate_traditional_chart_jd", original)
    assert_no_exception(at, f"the Moon at {moon!r} on {page}")
    tables = {}
    for heading, node in table_nodes(at):
        tables.setdefault(str(heading), []).append(node.value.to_csv())
    return tables


@pytest.mark.parametrize("page", ["chart", "timing", "days"])
def test_every_table_on_the_page_reads_the_moon_at_the_seam_as_at_0_aries(engine, monkeypatch, page):
    """KD's check, finding 12: with every chart's Moon at -1e-16 the Chart
    page's Absolute printed `-0.0000°`, Timing's planets under III.1, 12
    printed a declination `-0.00°`, and the Days page's IX.7, 71 row began
    the Moon's ninth-parts in Leo. Every table must read as at 0.0."""
    import engine as engine_module
    at_zero = _page_tables(engine_module, monkeypatch, page, 0.0)
    assert at_zero                                                                       # premise
    at_seam = _page_tables(engine_module, monkeypatch, page, SEAM)
    assert at_seam.keys() == at_zero.keys()
    assert {h: t for h, t in at_seam.items() if t != at_zero[h]} == {}


# --- By a spy: no value can move today ----------------------------------------

def _eyesight_at_seam(engine, chart):
    rows = [row for row in engine["EYESIGHT_PLACES"]]
    return lambda: [engine["eyesight_place_in_span"](row, SEAM) for row in rows]


def _rhetorius_at_seam(engine, chart):
    data = _placed(chart, Jupiter=SEAM)
    return lambda: engine["evaluate_rhetorius_affliction"](data, chart["ascendant"], chart["sect"])


READERS_THAT_CANNOT_MOVE = {
    # EYESIGHT_PLACES has no Aries row, so -1e-16 and 0.0 alike stand in
    # none; an Aries row from 0 would have read the seam as degree 30.
    "eyesight_place_in_span": _eyesight_at_seam,
    # Its loop takes `% 360.0` first, 360.0 at -1e-16, which every sign and
    # bound test reads as 0 Aries; the value moves nowhere (below).
    "evaluate_rhetorius_affliction": _rhetorius_at_seam,
}


@pytest.mark.parametrize("reader", list(READERS_THAT_CANNOT_MOVE))
def test_a_reader_that_cannot_move_reads_the_seam_through_on_circle(engine, monkeypatch, reader):
    """The sign each asks for is asked of 0.0, never of -1e-16 nor of
    360.0: a value on the circle, as K-16's readers ask."""
    chart = _florence(engine)
    call = READERS_THAT_CANNOT_MOVE[reader](engine, chart)
    seen = []
    original = engine["get_zodiac_sign"]

    def spy(longitude):
        seen.append(longitude)
        return original(longitude)

    monkeypatch.setitem(engine, "get_zodiac_sign", spy)
    call()
    assert 0.0 in seen
    assert [value for value in seen if not 0.0 <= value < 360.0] == []


def test_rhetorius_reads_jupiter_at_the_seam_in_his_own_bound(engine):
    """The guard by value: Jupiter at -1e-16 is in his own (Egyptian) bound
    of Aries, as at 0.0, and the whole reading is the same."""
    chart = _florence(engine)
    reading = lambda lon: engine["evaluate_rhetorius_affliction"](_placed(chart, Jupiter=lon), chart["ascendant"], chart["sect"])
    at_zero = reading(0.0)
    assert any(row["Planet"] == "Jupiter" and row["Condition"].endswith("in its own terms") for row in at_zero)
    assert reading(SEAM) == at_zero
