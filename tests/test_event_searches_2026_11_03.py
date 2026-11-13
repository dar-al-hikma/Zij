"""The event searches: a contact against its cutoff, the first recompense, and "is connecting".

PN IV II.22, 1-2 (PN IV pp. 264-265) divides a Moon-ruled year among the planets "which the Moon
connects with, so long as she is in her [current] sign". The app reads that as a perfection by degree
before she leaves it, so a contact and her exit are compared. They are found to one precision here.

Gr. Intr. VII.5, 127 (Gr. Intr. p. 475): the first planet "will not cease to have favor for it until" the
helper "falls into its own well or fall, and the other [planet] connects with it". "Until" names the
first such occasion.

Gr. Intr. VII.5, 117 (Gr. Intr. p. 471): "Revoking is if a planet is connecting with a planet, but before it
reaches it, it retrogrades away from it". "Is connecting" is read at the chart moment by the engine's own
connection test, 12 degrees by aspect and 15 by assembly (Gr. Intr. VII.5, 27, Gr. Intr. p. 449;
VII.4, 3, Gr. Intr. p. 425).

Gr. Intr. VII.5, 123 (Gr. Intr. pp. 473-474), Cutting's second type: "if a light planet is connecting with a
planet heavier than itself". The same words, read the same way. Its first type (VII.5, 121, Gr. Intr. p. 473) says
"wants a connection" and asks none at the chart moment.

The expected values come from a bisection over the same positions, written apart from the engine's.
"""
from __future__ import annotations

import random

import pytest

from conftest import assert_no_exception, make_app

def _chart(engine, jd, lat=0.0, lon=0.0):
    return engine["calculate_traditional_chart_jd"](jd, lat, lon)


def _sample(engine, seed, count):
    """Seeded charts, 1900-2100, latitudes to 60 degrees either way."""
    swe = engine["swe"]
    rng = random.Random(seed)
    low, high = swe.julday(1900, 1, 1, 0.0), swe.julday(2100, 1, 1, 0.0)
    return [(rng.uniform(low, high), rng.uniform(-60.0, 60.0), rng.uniform(-180.0, 180.0)) for _ in range(count)]


def _wrap(angle):
    return (angle + 180.0) % 360.0 - 180.0


def _signs_apart(first, second):
    apart = abs(int(first // 30) - int(second // 30))
    return min(apart, 12 - apart)


class Sky:
    """Two planets from one moment on, read from the ephemeris with no search of the engine's."""

    def __init__(self, engine, jd, first, second):
        self.swe, self.flags, self.jd = engine["swe"], engine["MOSHIER_FLAGS"], jd
        self.first, self.second = engine["PLANET_SWE_IDS"][first], engine["PLANET_SWE_IDS"][second]
        self.read = {}

    def lon(self, body, day):
        key = (body, day)
        if key not in self.read:
            self.read[key] = self.swe.calc_ut(self.jd + day, body, self.flags)[0][0]
        return self.read[key]

    def perfections(self, horizon, step=0.1):
        """Every perfection of the pair in (0, horizon), its whole-sign aspect valid at the root."""
        found = []
        for angle, signs in ((0.0, 0), (60.0, 2), (90.0, 3), (120.0, 4), (180.0, 6)):
            for offset in ((angle,) if angle in (0.0, 180.0) else (angle, -angle)):
                def residual(day, _offset=offset):
                    return _wrap(self.lon(self.first, day) - self.lon(self.second, day) - _offset)
                low, at_low = 0.0, residual(0.0)
                while low < horizon:
                    high = min(low + step, horizon)
                    at_high = residual(high)
                    if (at_low < 0.0) != (at_high < 0.0) and abs(at_high - at_low) < 90.0:
                        a, b, at_a = low, high, at_low
                        while b - a > 1e-8:
                            mid = (a + b) / 2.0
                            at_mid = residual(mid)
                            if (at_mid < 0.0) == (at_a < 0.0):
                                a, at_a = mid, at_mid
                            else:
                                b = mid
                        root = (a + b) / 2.0
                        if _signs_apart(self.lon(self.first, root), self.lon(self.second, root)) == signs:
                            found.append((root, angle))
                    low, at_low = high, at_high
        return sorted(found)


def _favor_rows(engine, jd, lat, lon):
    chart = _chart(engine, jd, lat, lon)
    planets, sect = chart["planetary_data"], chart["sect"]
    sim = engine["_simulate_forward"](planets, jd)
    essential = engine["evaluate_essential_dignities"](planets, sect)
    return engine["evaluate_favor_and_recompense"](planets, essential, sect, sim)


def _first_recompense(engine, jd, helper, helped):
    """The first perfection of the pair at which the helper stands in its well or fall."""
    sky = Sky(engine, jd, helped, helper)
    falls = engine["FALLS"].get(helper, [])
    for day, angle in sky.perfections(float(engine["FAVOR_SEARCH_DAYS"])):
        lon = sky.lon(sky.second, day) % 360.0
        sign = engine["get_zodiac_sign"](lon)
        if sign in falls or engine["ordinal_degree"](lon) in engine["WELLED_DEGREES"].get(sign, []):
            return day, angle
    return None


# --- a contact against its cutoff ---------------------------------------------


def test_a_trine_39_seconds_before_the_moons_exit_is_her_second_connection(engine):
    """1942-07-22 16:50 UT: the Moon squares Mars, then trines the Sun 39 s before leaving Scorpio."""
    jd = engine["civil_local_to_jd_ut"](1942, 7, 22, 16 + 50 / 60, 0.0)
    chart = _chart(engine, jd, 0.0, -175.0)
    moon = engine["pn4_moon_connections"](chart["planetary_data"], jd)
    assert [(c["planet"], c["aspect"]) for c in moon["connections"]] == [("Mars", "square"), ("Sun", "trine")]
    assert moon["connections"][1]["day"] < moon["exit_day"]


def test_that_year_is_divided_between_mars_and_the_sun(engine):
    jd = engine["civil_local_to_jd_ut"](1942, 7, 22, 16 + 50 / 60, 0.0)
    chart = _chart(engine, jd, 0.0, -175.0)
    chronocrats = engine["calculate_chronocrats"](jd, 0.0, -175.0, 16, 0.0)
    birth = engine["CivilDate"](1942, 7, 22)
    bundle = engine["pn4_timing_bundle"](chart, 0.0, -175.0, birth, birth,
                                         engine["PN4_MONTHLY_TURN_OPTIONS"][0], chronocrats)
    assert [row["Owned by"] for row in bundle["portion_rows"]] == ["Mars", "Sun"]


def _bisect(test, low, high):
    """The moment a boolean test changes inside (low, high), to a hundred-millionth of a day."""
    at_low = test(low)
    assert test(high) != at_low
    while high - low > 1e-8:
        mid = (low + high) / 2.0
        if test(mid) == at_low:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


ASPECT_NAMES = {0.0: "body", 60.0: "sextile", 90.0: "square", 120.0: "trine", 180.0: "opposition"}

# Moon sign passages with a perfection within a minute of her exit, from a census of her 32,084 exits of
# 1900-2100 by the same independent bisection: a start in the passage, the planet, and how long before her
# exit it perfects (after it, where negative).
NEAR_THE_EXIT = [
    (2437336.9565369124, "Mars", 1.9),
    (2419736.8242931725, "Saturn", 32.7),
    (2416264.408050058, "Mars", 36.5),
    (2446299.888935074, "Sun", -1.2),
    (2434777.2456144136, "Mercury", -2.4),
]


@pytest.mark.parametrize("start, planet, seconds", NEAR_THE_EXIT)
def test_a_contact_near_the_moons_exit_falls_on_its_own_side(engine, start, planet, seconds):
    planets = _chart(engine, start)["planetary_data"]
    moon = Sky(engine, start, "Moon", planet)
    sign = int(moon.lon(moon.first, 0.0) // 30)
    own_exit = _bisect(lambda day: int(moon.swe.calc_ut(start + day, moon.first, moon.flags)[0][0] // 30) == sign,
                       0.0, 1.5)
    own = set()
    for other in ("Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"):
        for _day, angle in Sky(engine, start, "Moon", other).perfections(own_exit):
            own.add((other, ASPECT_NAMES[angle]))
    near = {name for other, name in own if other == planet}
    assert bool(near) == (seconds > 0), (own, planet, seconds)    # the premise: its side of the exit
    found = engine["pn4_moon_connections"](planets, start)
    assert {(c["planet"], c["aspect"]) for c in found["connections"]} == own


def test_a_contact_and_its_cutoffs_hold_one_precision(engine):
    """The contact, the sign exit and the station, each within the stated precision of a finer bisection."""
    jd = engine["civil_local_to_jd_ut"](2000, 1, 22, 12.0, 0.0)
    planets = _chart(engine, jd)["planetary_data"]
    sim = engine["_simulate_forward"](planets, jd)
    sky = Sky(engine, jd, "Moon", "Mercury")
    tolerance = 2 * engine["CONTACT_PRECISION_DAYS"]
    assert tolerance * 86400.0 < 0.2

    exit_day = sim["events"]["Moon"]["sign_exits"][0]
    moon_sign = int(sky.lon(sky.first, 0.0) // 30)
    own_exit = _bisect(lambda day: int(sky.swe.calc_ut(jd + day, sky.first, sky.flags)[0][0] // 30) == moon_sign,
                       0.0, exit_day + 0.1)
    assert exit_day == pytest.approx(own_exit, abs=tolerance)

    station_day, kind = sim["events"]["Mercury"]["stations"][0]
    assert kind == "first"
    own_station = _bisect(lambda day: sky.swe.calc_ut(jd + day, sky.second, sky.flags)[0][3] > 0.0,
                          station_day - 0.5, station_day + 0.5)
    assert station_day == pytest.approx(own_station, abs=tolerance)

    own_day, angle = sky.perfections(30.0)[0]
    assert engine["_perfection_day"](sim, "Moon", "Mercury", angle) == pytest.approx(own_day, abs=tolerance)


# --- the first recompense ----------------------------------------------------


def _row(rows, helped, condition, helper):
    hits = [r for r in rows if (r["Planet"], r["Condition"], r["Favored By"]) == (helped, condition, helper)]
    assert len(hits) == 1, rows
    return hits[0]


def test_a_helper_entering_its_well_between_two_samples_pays_at_that_contact(engine):
    """Jupiter reaches his welled degree and squares the Moon between days 10 and 11."""
    jd = engine["civil_local_to_jd_ut"](2000, 6, 24, 12.0, 0.0)
    row = _row(_favor_rows(engine, jd, 0.0, 0.0), "Moon", "Well", "Jupiter")
    assert row["Recompense (days)"] == "10.7"
    assert _first_recompense(engine, jd, "Jupiter", "Moon")[1] == 90.0


def test_an_aspect_fixed_at_an_earlier_sample_does_not_pass_over_an_earlier_one(engine):
    """Venus in Virgo opposes the Moon at day 8.1, before the trine the day-2 sample had fixed."""
    jd, lat, lon = 2446326.9400688885, 26.94022597, 13.43712423
    row = _row(_favor_rows(engine, jd, lat, lon), "Moon", "Fall", "Venus")
    assert row["Recompense (days)"] == "8.1"
    day, angle = _first_recompense(engine, jd, "Venus", "Moon")
    assert angle == 180.0 and round(day, 1) == 8.1
    venus = engine["swe"].calc_ut(jd + day, engine["PLANET_SWE_IDS"]["Venus"], engine["MOSHIER_FLAGS"])[0][0]
    assert engine["get_zodiac_sign"](venus) == "Virgo"


def test_every_favor_row_in_a_sample_reads_the_first_recompense(engine):
    rows = [(jd, row) for jd, lat, lon in _sample(engine, 20261103, 60) for row in _favor_rows(engine, jd, lat, lon)]
    assert len(rows) > 40, rows
    found = 0
    for jd, row in rows:
        own = _first_recompense(engine, jd, row["Favored By"], row["Planet"])
        found += own is not None
        expected = str(round(own[0], 1)) if own else "none within 200 days (the search ends there)"
        assert row["Recompense (days)"] == expected, (jd, row, own)
    assert 0 < found < len(rows), (found, len(rows))


# --- what "is connecting" reads -----------------------------------------------


def _pair_row(engine, planets, first, second):
    with engine["doctrine"](engine["ABU_MASHAR"]):
        rows = engine["_pairwise_configurations"](planets)
        row = next(r for r in rows if {r["p1"], r["p2"]} == {first, second})
        return row, engine["_is_connected"](row)


def _revoking(engine, jd, lat, lon):
    planets = _chart(engine, jd, lat, lon)["planetary_data"]
    return planets, engine["evaluate_revoking"](planets, engine["_simulate_forward"](planets, jd))


def test_mercury_21_degrees_from_venus_is_not_connecting(engine):
    jd = engine["civil_local_to_jd_ut"](2000, 1, 22, 12.0, 0.0)
    planets, rows = _revoking(engine, jd, 0.0, 0.0)
    assert not [r for r in rows if (r["Planet"], r["Was Connecting To"]) == ("Mercury", "Venus")], rows
    row, connected = _pair_row(engine, planets, "Mercury", "Venus")
    assert row["aspect_name"] == "Sextile" and row["motion"] == "Applying" and abs(row["deviation"]) > 12.0
    assert connected is False


def test_every_revoking_row_in_a_sample_is_connected_at_the_chart_moment(engine):
    rows = []
    for jd, lat, lon in _sample(engine, 20261104, 120):
        planets, returned = _revoking(engine, jd, lat, lon)
        rows += [(jd, planets, row) for row in returned]
    assert len(rows) > 10, rows
    for jd, planets, row in rows:
        pair, connected = _pair_row(engine, planets, row["Planet"], row["Was Connecting To"])
        assert connected, (jd, row, pair["deviation"], pair["dist"])


def test_a_connected_planet_stationing_before_the_perfection_still_revokes(engine):
    """Mercury within orb of Venus at the chart moment turns retrograde at day 35.1, and no perfection of that
    aspect comes first."""
    jd, lat, lon = 2467906.071452093, -3.91000399900134, 7.3003534332588345
    planets, rows = _revoking(engine, jd, lat, lon)
    assert rows == [{"Planet": "Mercury", "Was Connecting To": "Venus", "Stations Retrograde In (days)": 35.1}]
    row, connected = _pair_row(engine, planets, "Mercury", "Venus")
    assert connected is True
    sky = Sky(engine, jd, "Mercury", "Venus")
    speed = lambda day: sky.swe.calc_ut(jd + day, sky.first, sky.flags)[0][3]
    assert speed(35.0) > 0.0 > speed(35.2)
    assert not [day for day, angle in sky.perfections(35.2) if angle == row["target"]]


def test_the_page_says_when_is_connecting_is_read():
    at = make_app(date="1313-03-05", page="configurations", timeout=300)
    at.session_state["manual_lat_key"] = -23.89
    at.session_state["manual_lon_key"] = -71.84
    at.run(timeout=300)
    assert_no_exception(at, "Configurations")
    notes = [m.value for m in at.markdown if m.value.startswith("**Revoking** (117)")]
    assert len(notes) == 1 and (
        '"Is connecting" is read at the chart moment: within 12\u00b0 by aspect (27) or 15\u00b0 by assembly (Gr. Intr. VII.4, 3).' in notes[0]), notes


# --- Cutting's two simulated types: "is connecting" and "wants a connection" ---


def _cutting(engine, jd, lat, lon, rule=None):
    """Cutting's rows under the sidebar's rule, the app's default when none is named."""
    planets = _chart(engine, jd, lat, lon)["planetary_data"]
    sim = engine["_simulate_forward"](planets, jd)
    with engine["doctrine"](rule or engine["reading"]("CONNECTION_PROFILE")):
        return planets, engine["evaluate_cutting_the_light"](planets, sim)


def _of_type(rows, kind):
    return [(r["Planet"], r["Yields To"], r["Other Contact"]) for r in rows if r["Type"] == kind]


def _in_the_connection_orbs(planets, first, second):
    """Apart from the engine's test: 15 degrees in one sign, 12 from the exact aspect of their signs otherwise."""
    one, other = planets[first]["longitude"], planets[second]["longitude"]
    apart, signs = abs(_wrap(one - other)), _signs_apart(one, other)
    if signs == 0:
        return apart <= 15.0
    return abs(apart - signs * 30.0) <= 12.0


CUTTING_CHARTS = {
    # A sextile 14.3 degrees off: inside the 15 of an assembly, but this is an aspect.
    "by_aspect_over_12": (2417939.38439276, 0.93047896713216, -56.46489593623673),
    # One sign, 16.1 degrees apart.
    "by_assembly_over_15": (2450076.3213322256, -16.972911565333774, 166.60690276690957),
    # Venus 19.4 degrees off the sextile with Mars, the Sun 11.7 off it.
    "both_ways": (2447590.6741278283, -40.14216086092378, -74.6998724881146),
    # One sign, 14.9 degrees apart: over the aspect's 12, inside the assembly's 15.
    "by_assembly_within_15": (2446050.4994575433, 58.534053665647576, 125.62797619029732),
    # Mars 22.8 degrees off the trine with Saturn, 26.7 from Jupiter in one sign.
    "type_i_far_off": (2420531.7207857748, 11.310060157572764, -26.447447251541348),
}
BOTH_RULES = ["Sahl", "Abu Ma'shar"]


@pytest.mark.parametrize("rule", BOTH_RULES)
@pytest.mark.parametrize("chart, light, onward, heavy", [
    ("by_aspect_over_12", "Sun", "Saturn", "Mars"),
    ("by_assembly_over_15", "Sun", "Saturn", "Mars"),
    ("both_ways", "Venus", "Jupiter", "Mars"),
])
def test_cuttings_second_type_needs_the_connection_at_the_chart_moment(engine, chart, light, onward, heavy, rule):
    planets, rows = _cutting(engine, *CUTTING_CHARTS[chart], rule=rule)
    assert (light, onward, heavy) not in _of_type(rows, "II"), rows
    row, connected = _pair_row(engine, planets, light, heavy)
    assert row["motion"] == "Applying" and connected is False
    assert not _in_the_connection_orbs(planets, light, heavy)


@pytest.mark.parametrize("rule", BOTH_RULES)
@pytest.mark.parametrize("chart, light, onward, heavy, because", [
    ("both_ways", "Sun", "Jupiter", "Mars", "Mars reaches Jupiter on day 6 and moves on; Sun lands on Jupiter instead on day 17"),
    ("by_assembly_within_15", "Venus", "Saturn", "Mars", "Mars reaches Saturn on day 0 and moves on; Venus lands on Saturn instead on day 14"),
])
def test_cuttings_second_type_stands_for_a_planet_already_connecting(engine, chart, light, onward, heavy, because, rule):
    planets, rows = _cutting(engine, *CUTTING_CHARTS[chart], rule=rule)
    assert [r["Because"] for r in rows if r["Type"] == "II" and (r["Planet"], r["Yields To"], r["Other Contact"]) == (light, onward, heavy)] == [because]
    row, connected = _pair_row(engine, planets, light, heavy)
    assert connected is True and _in_the_connection_orbs(planets, light, heavy)


@pytest.mark.parametrize("rule", BOTH_RULES)
def test_cuttings_first_type_stands_though_not_connected_at_the_chart_moment(engine, rule):
    planets, rows = _cutting(engine, *CUTTING_CHARTS["type_i_far_off"], rule=rule)
    assert sorted(_of_type(rows, "I")) == [("Mars", "Mercury", "Jupiter"), ("Mars", "Mercury", "Saturn")], rows
    for heavy in ("Saturn", "Jupiter"):
        assert _pair_row(engine, planets, "Mars", heavy)[1] is False
        assert not _in_the_connection_orbs(planets, "Mars", heavy)


# Type I's rows on the sample below: the chart's place in it, then the planet, the one that
# conjoins with it and the one it wanted.
TYPE_I_ON_THE_SAMPLE = [
    (116, "Jupiter", "Mercury", "Saturn"), (138, "Sun", "Mercury", "Mars"), (140, "Sun", "Mercury", "Mars"),
    (416, "Venus", "Mercury", "Sun"), (417, "Venus", "Mercury", "Saturn"), (417, "Venus", "Mercury", "Sun"),
    (842, "Mars", "Mercury", "Jupiter"), (842, "Mars", "Mercury", "Saturn"), (853, "Venus", "Mercury", "Sun"),
    (1156, "Sun", "Mercury", "Mars"), (1191, "Venus", "Mercury", "Sun"), (1217, "Sun", "Mercury", "Mars"),
    (1234, "Sun", "Mercury", "Saturn"), (1283, "Mars", "Mercury", "Jupiter"), (1320, "Jupiter", "Mercury", "Saturn"),
    (1475, "Venus", "Mercury", "Sun"), (1486, "Sun", "Venus", "Saturn"),
]


def test_cuttings_two_simulated_types_on_a_sample_of_1500(engine):
    second, first = [], []
    for place, (jd, lat, lon) in enumerate(_sample(engine, 20261104, 1500)):
        planets, rows = _cutting(engine, jd, lat, lon)
        second += [(place, planets, light, heavy) for light, _, heavy in _of_type(rows, "II")]
        first += [(place, *row) for row in _of_type(rows, "I")]
    assert len(second) == 374
    for place, planets, light, heavy in second:
        assert _pair_row(engine, planets, light, heavy)[1] is True, (place, light, heavy)
        assert _in_the_connection_orbs(planets, light, heavy), (place, light, heavy)
    assert sorted(first) == TYPE_I_ON_THE_SAMPLE
