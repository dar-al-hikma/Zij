"""The seam, the rest of it: lane KD of the follow-ups (K-16).

K-16's own test (``test_followups_2026_10_05.py``) compares each reader at
-1e-16 with the same reader at 0.0. Two things it does not reach are pinned
here: a wheel's ``data-lon`` for a value that rounds up to 360 at six
places, and the door every planetary-data reader now takes, which must hand
an ordinary chart's mapping through untouched.
"""
import copy
import re
from datetime import datetime

import pytest
import swisseph as swe


def _florence(engine):
    return engine["calculate_traditional_chart_jd"](swe.julday(1240, 5, 23, 13.75, swe.JUL_CAL), 43.7792, 11.2463)


def test_data_lon_prints_a_value_on_the_circle(engine):
    """A point a hair under 360 that six places round up prints 0.000000,
    as -1e-16 does, and never 360.000000; a value six places do not round
    keeps its digits."""
    hair = 360.0 - 1e-9
    chart = _florence(engine)
    chart["planetary_data"]["Moon"]["longitude"] = hair
    chart["mc"] = hair
    hybrid = engine["generate_hybrid_svg"](chart, "t", "Florence", 43.7792, 11.2463, datetime(1240, 5, 23, 14, 30), "LMT")
    multi = engine["generate_multiwheel_svg"]([{"label": "Root", "chart": chart, "when": "x"}], "t",
                                              marks=[("Terminal point", hair, 0)], extras={0: [("Lot", hair)]})
    printed = {(which, name): re.findall(rf'data-point="{name}" data-lon="([^"]+)"', svg)
               for which, svg, names in (("natal", hybrid, ("Moon", "Midheaven")),
                                         ("multi", multi, ("Moon", "Terminal point", "Lot")))
               for name in names}
    assert printed == {key: ["0.000000"] for key in printed} and len(printed) == 5
    values = [float(v) for v in re.findall(r'data-lon="([^"]+)"', hybrid + multi)]
    assert len(values) >= 20
    assert [v for v in values if not 0.0 <= v < 360.0] == []
    cases = {-1e-16: "0.000000", 360.0 - 1e-9: "0.000000", 360.0 - 4e-7: "0.000000",
             360.0 - 6e-7: "359.999999", 720.0: "0.000000", 12.5: "12.500000"}
    assert {lon: engine["_lon_attr"](lon) for lon in cases} == cases


def test_the_door_hands_an_ordinary_chart_through_untouched(engine):
    """Every longitude the ephemeris returns is already in [0, 360): the
    door returns that very mapping, so no ordinary chart's reading can
    move. A stray value is mended in a copy; the caller's mapping keeps
    its own value."""
    data = _florence(engine)["planetary_data"]
    assert engine["_planets_on_circle"](data) is data
    stray = copy.deepcopy(data)
    stray["Moon"]["longitude"] = -1e-16
    mended = engine["_planets_on_circle"](stray)
    assert mended["Moon"]["longitude"] == 0.0
    assert stray["Moon"]["longitude"] == -1e-16
    assert {name: entry for name, entry in mended.items() if name != "Moon"} == \
        {name: entry for name, entry in stray.items() if name != "Moon"}
    assert engine["_on_circle"](-1e-16) == 0.0


def _seam_inputs(engine):
    chart = _florence(engine)
    data = copy.deepcopy(chart["planetary_data"])
    data["Moon"]["longitude"] = -1e-16
    sect = chart["sect"]
    essential = engine["evaluate_essential_dignities"](data, sect)
    accidental = engine["evaluate_accidental_dignities"](data, chart["houses"], sect, chart["julian_day"],
                                                         armc=chart["armc"], obliquity=chart["obliquity"],
                                                         geo_lat=chart["geo_lat"])
    return chart, data, essential, accidental, engine["_simulate_forward"](data, chart["julian_day"])


READERS_WITH_A_DOOR = {
    "evaluate_blocking": lambda e, c, d, ess, acc, sim: e["evaluate_blocking"](d),
    "evaluate_cutting_the_light": lambda e, c, d, ess, acc, sim: e["evaluate_cutting_the_light"](d, sim),
    "evaluate_abu_mashar_condition": lambda e, c, d, ess, acc, sim: e["evaluate_abu_mashar_condition"](
        d, c["houses"], c["sect"], ess, acc, c["julian_day"], c["ascendant"], sim),
}


@pytest.mark.parametrize("reader", list(READERS_WITH_A_DOOR))
def test_a_reader_with_a_door_hands_its_own_readers_the_mended_longitude(engine, monkeypatch, reader):
    """These readers also take signs from the raw value in branches the
    default chart does not open by value (cutting the light's Type I, the
    condition's empty-of-course search over the forward simulation); the
    door that mends them is the one their inner aspect table is handed, so
    the table must never see the hair under 0 Aries."""
    chart, data, essential, accidental, sim = _seam_inputs(engine)
    seen = []
    original = engine["_pairwise_configurations"]

    def spy(planetary_data, *args, **kwargs):
        seen.append(planetary_data["Moon"]["longitude"])
        return original(planetary_data, *args, **kwargs)

    monkeypatch.setitem(engine, "_pairwise_configurations", spy)
    READERS_WITH_A_DOOR[reader](engine, chart, data, essential, accidental, sim)
    assert seen
    assert set(seen) == {0.0}


def _recompense_at_seam(engine, chart):
    sim = copy.deepcopy(engine["_simulate_forward"](chart["planetary_data"], chart["julian_day"]))
    sim["series"]["Saturn"]["lon"] = [-1e-16] * len(sim["series"]["Saturn"]["lon"])
    return lambda: engine["_find_recompense_day"](sim, "Saturn", "Moon")


def _favor_at_seam(engine, chart):
    _chart, data, essential, _accidental, sim = _seam_inputs(engine)
    return lambda: engine["evaluate_favor_and_recompense"](data, essential, chart["sect"], sim)


def _book_v_at_seam(engine, chart):
    data = copy.deepcopy(chart["planetary_data"])
    data["Moon"]["longitude"] = -1e-16
    return lambda: engine["evaluate_book_v_degrees"](data, chart["ascendant"], chart["lot_of_fortune"], chart["sect"])


def _nobility_at_seam(engine, chart):
    data = copy.deepcopy(chart["planetary_data"])
    data["Moon"]["longitude"] = -1e-16
    return lambda: engine["evaluate_nobility_degrees"](data, chart["ascendant"], chart["sect"])


def _monthly_turn_at_seam(engine, chart):
    return lambda: engine["pn4_monthly_turn_forward"](-1e-16, engine["PN4_MONTHLY_TURN_OPTIONS"][1])


READERS_OF_A_DEGREE_LIST = {
    "_find_recompense_day": _recompense_at_seam,
    "evaluate_favor_and_recompense": _favor_at_seam,
    "evaluate_book_v_degrees": _book_v_at_seam,
    "evaluate_nobility_degrees": _nobility_at_seam,
    "pn4_monthly_turn_forward": _monthly_turn_at_seam,
}


@pytest.mark.parametrize("reader", list(READERS_OF_A_DEGREE_LIST))
def test_a_reader_reads_the_seam_through_on_circle(engine, monkeypatch, reader):
    """These readers take a sign and a degree in the sign (a well, a
    table's degree, the monthly turn's half) where no Aries list holds the
    first degree, so a hair under 0 Aries cannot move their answers by
    value (the K-16 parameters say why, one by one). What each must do is
    read the value as 0 Aries: the sign they ask for is asked of 0.0,
    never of -1e-16 (which `% 30` takes as Aries' 31st degree) and never
    of nothing (a reader that took the sign itself, as Pisces)."""
    chart = _florence(engine)
    call = READERS_OF_A_DEGREE_LIST[reader](engine, chart)
    seen = []
    original = engine["get_zodiac_sign"]

    def spy(longitude):
        seen.append(longitude)
        return original(longitude)

    monkeypatch.setitem(engine, "get_zodiac_sign", spy)
    call()
    assert 0.0 in seen
    assert [value for value in seen if not 0.0 <= value < 360.0] == []
