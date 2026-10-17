"""PN IV II.13, 1 [3]: "the planet to which the Sun hands over the management
(so long as it is in its sign)", read with fn 239 as the planets the Sun
connects with before he leaves his sign, and "hands over" by weight (ruling
147 (3), A-17 of the third outside pass): the Sun hands over only to a planet
heavier than he by WEIGHT_ORDER -- Mars, Jupiter, Saturn. Mercury and Venus
are lighter, and "the light one connects with one which is slower than it"
(Gr. Intr. VII.5, 9, p. 445); at an inferior conjunction the lighter one
connects with him "through its retrogradation" (Gr. Intr. VII.5, 24, p. 448;
VII.5, 118, p. 472), though his signed speed is then the greater. The engine
had kept a perfection when the Sun's signed speed exceeded the planet's, so
counted every such inferior conjunction as a hand-over.

The charts were found by a scan, not made: every inferior conjunction of
Mercury and of Venus 1950-2049 (Moshier; the elongation falling through zero
with the planet retrograde) was listed with the Sun's degree in his sign;
the 2004-06-08 Venus conjunction (Sun 17 53 Gemini) and the 2008-06-07
Mercury one (Sun 17 15 Gemini) were taken, and a native born with the Sun
early in Gemini whose revolutions at 24 and 28 open before them. Born
1980-05-26 10:00 UT at 51.5 N, 0.12 W: Leo rises, so age 24 is a year of the
Sun and the bundle prints the hand-over row. Mercury's retrograde speed there
(-0.56) is smaller in size than the Sun's, so the pin also refuses an
absolute-speed reading.

The Moon's connections (II.22, 1-2) are not touched; their pins hold the
values the engine gave before the change.
"""
import json
from datetime import date, datetime, time

import pytest

from conftest import assert_no_exception, make_app, ui_source

BIRTH, LAT, LON = datetime(1980, 5, 26, 10, 0), 51.5, -0.12

# age: (exit day of the Sun from Gemini, the hand-overs by weight, the lighter
# planet in his body by its retrogradation and its day, the Moon's exit day,
# the Moon's connections)
REVOLUTIONS = {
    24: (25.8224, [("Jupiter", "square", 4.8062)], ("Venus", 13.146),
         0.6106, [("Venus", "sextile", 0.187)]),
    28: (25.8203, [("Mars", "sextile", 9.1782)], ("Mercury", 12.4644),
         1.389, [("Mercury", "trine", 0.7231)]),
}


def _revolution(engine, age):
    cast = engine["calculate_traditional_chart"]
    chart = cast(BIRTH, LAT, LON)
    jd_sr = engine["pn4_solar_revolution_jd"](chart["julian_day"], chart["planetary_data"]["Sun"]["longitude"], age)
    sr = cast(engine["pn4_datetime_from_jd"](jd_sr), LAT, LON)
    return chart, sr, jd_sr


def _the_lighter_one_retrograde_in_his_body(engine, jd_sr, sun, planet, day):
    """The ephemeris, not the engine's filter: on `day` the planet is in the
    Sun's body, retrograde, inside his sign, and his signed speed exceeds
    both its signed and its absolute speed -- so the signed-speed reading,
    and an absolute-speed one, would both have counted it."""
    swe, flags = engine["swe"], engine["MOSHIER_FLAGS"]
    s = swe.calc_ut(jd_sr + day, swe.SUN, flags)[0]
    p = swe.calc_ut(jd_sr + day, engine["PLANET_SWE_IDS"][planet], flags)[0]
    assert abs(engine["_wrap180"](s[0] - p[0])) < 0.05
    assert engine["get_zodiac_sign"](s[0]) == sun["sign"] and 0.0 < day < sun["exit_day"]
    assert p[3] < 0.0 < s[3] and s[3] > abs(p[3])


@pytest.mark.parametrize("age, planet", [(28, "Mercury"), (24, "Venus")])
def test_a17_a_lighter_planet_at_its_inferior_conjunction_is_not_handed_over_to(engine, age, planet):
    """(a) Mercury, 2008; (b) Venus, 2004: each meets the Sun by its
    retrogradation before he leaves Gemini. The engine had listed it as a
    hand-over (the Sun the faster by signed speed); by weight it is the one
    connecting with him, and the list is the heavier planet's alone."""
    _chart, sr, jd_sr = _revolution(engine, age)
    sun = engine["pn4_sun_handover"](sr["planetary_data"], jd_sr)
    exit_day, handed, (light, light_day), _m_exit, _m = REVOLUTIONS[age]
    assert light == planet
    _the_lighter_one_retrograde_in_his_body(engine, jd_sr, sun, planet, light_day)
    assert planet not in [c["planet"] for c in sun["connections"]]
    assert [(c["planet"], c["aspect"]) for c in sun["connections"]] == [(p, a) for p, a, _d in handed]
    assert [c["day"] for c in sun["connections"]] == pytest.approx([d for _p, _a, d in handed], abs=0.01)
    assert sun["exit_day"] == pytest.approx(exit_day, abs=0.01) and sun["sign"] == "Gemini"


@pytest.mark.parametrize("age", sorted(REVOLUTIONS))
def test_a17_c_a_heavier_planet_is_handed_over_to_as_before(engine, age):
    """(c) Jupiter's square (2004) and Mars's sextile (2008) are kept, each
    heavier than the Sun by WEIGHT_ORDER, inside his sign. (Passes on the
    engine before the change too: a scan of every day 1900-2100 found the
    Sun's signed speed above Mars's, Jupiter's and Saturn's by at least
    0.19 degree a day, so the two readings never part for them.)"""
    _chart, sr, jd_sr = _revolution(engine, age)
    sun = engine["pn4_sun_handover"](sr["planetary_data"], jd_sr)
    _exit, handed, _light, _m_exit, _m = REVOLUTIONS[age]
    order = engine["WEIGHT_ORDER"]
    assert len(handed) == 1
    for planet, aspect, day in handed:
        assert order.index(planet) < order.index("Sun")
        found = [c for c in sun["connections"] if c["planet"] == planet and c["aspect"] == aspect]
        assert len(found) == 1 and found[0]["day"] == pytest.approx(day, abs=0.01)
        assert engine["get_zodiac_sign"](found[0]["moon_at"]) == "Gemini"


@pytest.mark.parametrize("age", sorted(REVOLUTIONS))
def test_a17_d_the_moons_connections_are_unchanged(engine, age):
    """(d) II.22, 1-2: the Moon's connections on both revolutions are the
    values the engine gave before the change, each with a planet lighter
    than the Sun, so a weight test borrowed from the Sun would drop them.
    (Passes on the engine before the change too.)"""
    _chart, sr, jd_sr = _revolution(engine, age)
    moon = engine["pn4_moon_connections"](sr["planetary_data"], jd_sr)
    _exit, _handed, _light, m_exit, m_conns = REVOLUTIONS[age]
    assert moon["exit_day"] == pytest.approx(m_exit, abs=0.01)
    assert [(c["planet"], c["aspect"]) for c in moon["connections"]] == [(p, a) for p, a, _d in m_conns]
    assert [c["day"] for c in moon["connections"]] == pytest.approx([d for _p, _a, d in m_conns], abs=0.01)


def test_a17_the_proxy_row_in_a_year_of_the_sun(engine):
    """Through the bundle, age 24 (Leo rising, so the Sun is lord of the
    year): row [3] names Jupiter alone, and says what "hands over" is read
    as. The Revolutions page and its export print this row."""
    chart = engine["calculate_traditional_chart"](BIRTH, LAT, LON)
    rule = engine["PN4_MONTHLY_TURN_OPTIONS"][0]
    b = engine["pn4_timing_bundle"](chart, LAT, LON, BIRTH.date(), date(2004, 8, 1), rule)
    assert b["year"]["lord"] == "Sun"
    row = next(r for r in b["proxies"] if r["Proxy"].startswith("[3] "))
    assert row["Reads"] == ("Jupiter by square on day 4.81 -- the revolution's Sun, applying to a heavier planet "
                            "(fn 239)")
    assert row["Source"] == "II.13, 1; fn 239"


def test_a17_the_page_note_says_the_reading(engine):
    """The Revolutions page's note on the Sun's proxies says "hands over"
    by weight, and no longer by the applying (faster) body."""
    page = ui_source()
    assert ("and \\\"hands over\\\" as the Sun applying to a heavier planet (Mars, Jupiter, Saturn); " in page)
    assert "the Sun being the applying body at the perfection" not in page


def test_a17_an_empty_hand_over_says_no_heavier_planet_not_no_connection():
    """When the Sun hands over to no heavier planet before he leaves his
    sign, the row says so, and not that he leaves "without a connection":
    Mercury or Venus may still connect with him (Gr. Intr. VII.5, 9). The
    checker's page case: Florence, 14:30 local, born 1963-09-08, the
    revolution for 1983-10-05, a year of the Sun; Mercury meets him by its
    retrogradation in Virgo, and no heavier planet perfects with him there.
    Read off the rendered Revolutions page and its export."""
    at = make_app(date="1963-09-08", page="timing")
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "1983-10-05"
    at.run(timeout=300)
    assert_no_exception(at, "timing, 1963-09-08, target 1983-10-05")
    want = ("none: hands over to no heavier planet before he leaves Virgo on day 15.20 -- the revolution's Sun, "
            "applying to a heavier planet (fn 239)")
    rows = [r for el in at.main.dataframe if "Proxy" in getattr(el.value, "columns", [])
            for r in el.value.to_dict("records") if r["Proxy"].startswith("[3] The planet to which the Sun")]
    assert [r["Reads"] for r in rows] == [want]
    exp = at.session_state["_analysis_export"]
    text = json.dumps(exp if isinstance(exp, dict) else json.loads(exp))
    assert json.dumps(want) in text and "without a connection" not in text


def test_a17_the_moons_empty_row_keeps_her_own_words():
    """The Sun's empty row has its own wording; the Moon's is not his. When
    the Moon connects with no planet before she leaves her sign, her row
    says so and names the lord of the house, who stands in (II.22, 4). The
    case: born 1914-03-22 15:40 UT at 44.33 N, 64.38 E, target 1935-06-01,
    so the revolution of 1935-03-22 (age 21 completed), a year of the Moon;
    read off the rendered Revolutions page and its export."""
    at = make_app(date="1914-03-22", page="timing")
    at.session_state["manual_lat_key"] = 44.33
    at.session_state["manual_lon_key"] = 64.38
    at.session_state["time_input_key"] = time(15, 40)
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = 0.0
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "1935-06-01"
    at.run(timeout=300)
    assert_no_exception(at, "timing, 1914-03-22, target 1935-06-01")
    want = ("none: leaves Libra on day 0.04 without a connection; the lord of the house, Venus, stands in "
            "(II.22, 4)")
    rows = [r for el in at.main.dataframe if "Proxy" in getattr(el.value, "columns", [])
            for r in el.value.to_dict("records") if r["Proxy"].startswith("[4] The planet the Moon connects with")]
    assert [r["Reads"] for r in rows] == [want]
    exp = at.session_state["_analysis_export"]
    text = json.dumps(exp if isinstance(exp, dict) else json.loads(exp))
    assert json.dumps(want) in text and "hands over to no heavier planet" not in text
