"""Printed numbers: lane PWN of the hostile pass's wave 5.

An outside reviewer's inventory of printed-number boundaries (classes N01-N13;
C01, its lower-confidence class, was reproduced and is not a contradiction under
the conventions below, so it has no test here), the owner's rulings 87 (PW-27,
PW-18) and 92 (PW-31's capital), PW's check notes, D1R2's check notes 17 and
19, and the notes items PW-33, PW-34 and EN-07. Each test failed on the base,
face757, for its item's reason before its fix. N04's coordinates (the strip,
the sidebar's box, the manual label, the Home popover) follow the owner's
ruling 107: a coordinate that rounds to zero prints without its sign.

The conventions: a printed degree does not carry past its sign; a signed zero
prints 0; a printed distance agrees with the verdict beside it -- read back, the
printed number gives the verdict the row prints; the sign may stay where the
unrounded value is printed beside it (ruling 9). No calculated value moves:
the JSON keeps each float as the engine holds it.
"""
import copy
import importlib.resources
import json
import re
from datetime import time
from pathlib import Path

import pytest

from conftest import EXECUTABLE_DIR, assert_no_exception, make_app, table_nodes
from test_d1r_mean_time_reach_2026_10_06 import _app as _named_app, _box, _calculation_rows, _refused_on_the_page
from test_pw_page_wording_2026_10_06 import FLORENCE_REC, _open_record, _store, scratch  # noqa: F401

MANUAL = "Manual UTC offset"
FLORENCE = (43.7792, 11.2463)



def _engine_text():
    from conftest import engine_source
    return engine_source()                            # every engine module, joined


def _pdata(**over):
    """Seven planets at rest far from one another; `over` moves some:
    name=(longitude, speed[, latitude])."""
    base = {'Sun': (300.0, 1.0), 'Moon': (130.0, 13.0), 'Mercury': (25.0, 1.2), 'Venus': (55.0, 1.1),
            'Mars': (250.0, 0.7), 'Jupiter': (265.0, 0.08), 'Saturn': (200.0, 0.03)}
    base.update(over)
    return {n: {'longitude': v[0], 'latitude': v[2] if len(v) > 2 else 0.0, 'distance': 1.0,
                'speed_in_lon': v[1], 'speed_in_lat': 0.0, 'speed_in_dist': 0.0} for n, v in base.items()}


def _manual_utc(page, date, hms, lat=FLORENCE[0], lon=FLORENCE[1]):
    """A chart cast in UT (a manual offset of 0) at a given second."""
    at = make_app(date=date, page=page, timeout=300)
    at.session_state["time_input_key"] = time(*hms)
    at.session_state["time_standard_key"] = MANUAL
    at.session_state["utc_offset_key"] = 0.0
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.run(timeout=300)
    assert_no_exception(at, f"{page} {date} {hms} UT")
    return at


def _strip(at):
    return next(c.value for c in at.main.caption if "\n**" in c.value and " · " in c.value)


def _markdown_row(report, heading, first_cell):
    lines = report.splitlines()
    start = lines.index(f"#### {heading}")
    header = next(l for l in lines[start:] if l.startswith("| "))
    row = next(l for l in lines[start:] if l.startswith(f"| {first_cell} |"))
    return dict(zip([c.strip() for c in header.strip("|").split("|")], [c.strip() for c in row.strip("|").split("|")]))


def _number(text):
    return float(re.search(r"-?\d+(?:\.\d+)?", text).group(0))


@pytest.fixture(scope="module")
def chart_2024(engine):
    """A real revolution chart (2024-06-01 12:00 UT, Florence) and a natal one,
    whose positions the constructed cases below move."""
    jd = engine["civil_local_to_jd_ut"](2024, 6, 1, 12.0, 0.0)
    sr = engine["calculate_traditional_chart_jd"](jd, *FLORENCE)
    natal = engine["calculate_traditional_chart_jd"](engine["civil_local_to_jd_ut"](1990, 6, 1, 12.0, 0.0), *FLORENCE)
    return natal, sr, jd


# =============================================================================
# N01: the Absolute does not carry past its sign
# =============================================================================

# A real Moon: 1983-11-06 06:08:46 UT, Florence. Swiss Ephemeris puts her at
# 239.99998784..., 0.0000122 degrees short of Sagittarius: Position 29 Sco 59'.
N01_DATE, N01_TIME = "1983-11-06", (6, 8, 46)


def test_n01_a_real_moon_a_hair_under_scorpios_end_prints_239_9999():
    at = _manual_utc("chart", N01_DATE, N01_TIME)
    rows = [n.value for h, n in table_nodes(at) if h == "Planetary Positions"]
    assert rows, "the premise: the Positions table"
    moon = rows[0].set_index("Planet").loc["Moon"]
    assert moon["Position"] == "29° Sco 59'", "the premise: the Moon a hair under Scorpio's end"
    assert moon["Absolute"] == "239.9999°", moon["Absolute"]
    md = _markdown_row(at.session_state["_analysis_markdown"], "Planetary Positions", "Moon")
    assert md["Absolute"] == "239.9999", md
    html = at.session_state["_analysis_html"]
    moon_row = re.search(r"<tr><td>Moon</td>.*?</tr>", html[html.index("Planetary Positions"):]).group(0)
    assert "<td>239.9999</td>" in moon_row, moon_row
    export_rows = at.session_state["_analysis_export"]["results"]["Chart"]["Planetary Positions"][0]["rows"]
    moon_float = next(r["Absolute"] for r in export_rows if r["Planet"] == "Moon")
    assert isinstance(moon_float, float) and 239.9999 < moon_float < 240.0, "the JSON keeps the calculation's float"


@pytest.mark.parametrize("k", range(1, 12))
def test_n01_the_export_absolute_stops_at_every_interior_sign_end(engine, k):
    """30k - 1e-5 is the last of sign k-1: printed 30k it is the next sign's 0."""
    lon = 30.0 * k - 1e-5
    assert engine["get_degree_string"](lon).startswith("29° "), "the premise"
    assert engine["_export_cell"](engine["CircleLongitude"](lon)) == f"{30.0 * k - 1e-4:.4f}"


def test_n01_a_right_ascension_keeps_its_own_rounding(engine):
    """Not the fix's to change: a right ascension has no signs (only 360
    stops it), and a value a hair under a sign's end on the circle elsewhere
    prints as it rounds."""
    assert engine["degrees_text"](29.99999, 4, circle=True) == "30.0000"
    assert engine["degrees_text"](359.99999, 4, circle=True) == "359.9999"


# =============================================================================
# N02: the sidereal clocks do not reach 24h or 360
# =============================================================================

# 1983-11-06 12:00:00 UT at 43.7792 N 134.8634 E: the Local sidereal time is
# 23.9999943 hours and the RAMC 359.9999147 degrees, both within half a second.
N02_LON = 134.8634


def test_n02_the_calculation_table_stops_lst_and_ramc_below_the_end_of_their_circles(engine):
    jd = engine["civil_local_to_jd_ut"](1983, 11, 6, 12.0, 0.0)
    armc = engine["calculate_traditional_chart_jd"](jd, FLORENCE[0], N02_LON)["armc"]
    assert 360.0 - 0.5 / 3600 < armc < 360.0, ("the premise", armc)
    at = _manual_utc("chart", "1983-11-06", (12, 0, 0), lon=N02_LON)
    calc = _calculation_rows(at)
    assert calc["Local sidereal time"] == "23h 59m 59s", calc
    assert calc["RAMC"] == "359° 59' 59\"", calc


# =============================================================================
# N03: a duration's hours do not reach 24
# =============================================================================

def test_n03_an_arc_a_hair_under_a_year_prints_23_9_hours(engine):
    assert engine["pn4_format_arc_time"]((360.0 - 0.0001) / 360.0) == "0y 11m 29d 23.9h"


def test_n03_a_days_distribution_lasting_a_hair_under_a_day_prints_23_9_hours(engine):
    seg = {'from': 0.0, 'to': 0.9999, 'distributor': 'Mars', 'partner': None, 'partner_aspect': None, 'opened_by': '-'}
    assert engine["_pn4_distribution_rows"]([seg], None, unit='days')[0]['Lasting'] == "0d 23.9h"


# =============================================================================
# N04: a signed zero prints 0
# =============================================================================

def test_n04_beniarbeig_from_the_atlas_prints_its_longitude_as_0_00():
    """The atlas's Beniarbeig (ES) is at 38.82232 N, 0.0021 W: the strip
    printed "-0.00"."""
    at = make_app(page="chart", timeout=300)
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = "Beniarbeig"
    at.run(timeout=300)
    assert_no_exception(at, "Beniarbeig")
    strip = _strip(at)
    assert "Beniarbeig" in strip, "the premise: the atlas's place"
    assert "38.82, 0.00" in strip and "-0.00" not in strip, strip


def test_n04_coordinates_that_round_to_zero_print_without_a_sign():
    at = make_app(page="chart", timeout=300)
    at.session_state["manual_lat_key"] = -0.00001
    at.session_state["manual_lon_key"] = -0.00001
    at.run(timeout=300)
    assert_no_exception(at, "the equator at Greenwich, a hair south and west")
    box = "\n".join(s.value for s in at.sidebar.success)
    assert "Manual [0.0000, 0.0000]" in box and "0.0000, 0.0000" in box and "-0.0000" not in box, box
    assert "0.00, 0.00" in _strip(at) and "-0.00" not in _strip(at), _strip(at)
    assert at.session_state["_analysis_export"]["input"]["place"] == "Manual [0.0000, 0.0000]"


def test_n04_a_record_saved_with_a_signed_zero_keeps_its_place_name_and_is_not_modified(scratch):
    """Ruling 107 changes the labels made from now on. A record on disk keeps
    the place name it was saved with -- the box prints it as saved -- and
    opening it neither changes the store nor calls the chart modified; the
    coordinates beside it print without the sign."""
    record = dict(FLORENCE_REC, location_query="Manual [-0.0000, 11.2463]", lat=-0.00001, lon=11.2463)
    at = _open_record("Old", record)
    strip = _strip(at)
    assert strip.startswith("Old · ") and "(modified)" not in strip, strip
    box = [s.value for s in at.sidebar.success if s.value.startswith("**Manual [")]
    assert len(box) == 1, [s.value for s in at.sidebar.success]
    name, coordinates = box[0].split("  \n", 1)
    assert name == "**Manual [-0.0000, 11.2463]**" and coordinates.startswith("0.0000, 11.2463"), box[0]
    assert "0.00, 11.25" in strip and "-0.00" not in strip, strip
    assert json.loads(_store().read_text(encoding="utf-8")) == {"Old": record}, "the store is unchanged"


def test_n04_a_bare_float_that_rounds_to_zero_prints_0_in_the_reports(engine):
    for value in (-0.000001, -0.00004, -0.0):
        assert engine["_export_cell"](value) == "0", value
    assert engine["_export_cell"](-0.00006) == "-0.0001"


# =============================================================================
# N05: a solar-phase distance reads, printed, the phase beside it
# =============================================================================

CUSPS = [(300.0 + 30.0 * i) % 360.0 for i in range(12)]


@pytest.mark.parametrize("planet, delta, speed, label", [
    ("Venus", 6.9999, 1.1, "Burned, western (6.99 deg) (-5)"),
    ("Moon", 6.0001, 13.0, "Under the rays, western (6.01 deg) (-2)"),
    ("Saturn", 15.0001, 0.03, "In the degrees of setting (15.01 deg)"),
])
def test_n05_the_accidental_label_prints_a_distance_inside_its_phase(engine, planet, delta, speed, label):
    data = _pdata(**{planet: ((300.0 + delta) % 360.0, speed)})
    labels = engine["evaluate_accidental_dignities"](data, CUSPS, "Diurnal", None)[planet]["Accidental Labels"]
    assert label in labels, labels
    printed = _number(label.split("(")[1])
    phase = engine["solar_phase"](planet, 300.0 + printed, 300.0, speed)[0]
    assert label.startswith({"Burned": "Burned", "Under the rays": "Under the rays",
                             "Degrees of setting": "In the degrees of setting"}[phase]), (phase, label)


@pytest.mark.parametrize("planet, delta, reads", [
    ("Venus", 6.9999, "yes: Burned, western, 6.99 from the Sun"),
    ("Moon", 6.0001, "no: Under the rays, western, 6.01 from the Sun"),
    ("Saturn", 1.04, "yes: Burned, western, 1.04 from the Sun"),       # Sahl's heart is 1 degree, inclusive
])
def test_n05_the_house_master_at_the_revolution_prints_a_distance_inside_its_phase(engine, chart_2024, planet,
                                                                                    delta, reads):
    natal, sr, jd = chart_2024
    rev = {p: dict(v) for p, v in sr["planetary_data"].items()}
    rev["Sun"]["longitude"], rev[planet]["longitude"] = 100.0, 100.0 + delta
    if planet == "Venus":
        rev[planet]["speed_in_lon"] = 1.1
    this_year = [{"Target": engine["SAHL_BURNING_TARGET"]}]
    rows = engine["sahl_house_master_in_revolution"](planet, natal, dict(sr, planetary_data=rev), this_year,
                                                     jd_next=jd + 365.2422)
    assert [r["Reads"] for r in rows if r["Fact"] == "Burned at the revolution"] == [reads]


def test_n05_the_third_day_moon_a_hair_past_12_degrees_prints_past_them(engine):
    data = _pdata(Moon=(312.0001, 13.0))
    third = {'planetary_data': data, **{n: v['longitude'] for n, v in data.items()}}
    cusps = tuple((95.0 + 30.0 * i) % 360.0 for i in range(12))   # constructed divisions (ruling 134)
    rows = engine["moon_third_day_rows"](third, {'Saturn': 200.0, 'Mars': 250.0}, 95.0, cusps)
    value = next(r["Value"] for r in rows if r["Item"].startswith("Burning"))
    assert value == "No: 12.01° from the Sun (burned within 12°, The Introduction Ch. 3, 103)", value


# =============================================================================
# N06: an ascensional distance reads, printed, the band beside it
# =============================================================================

def _band(x):
    return next((i for i, edge in enumerate((15.0, 30.0, 45.0)) if x <= edge), 3)


def _lon_at_ascension_past_mc(engine, chart, target):
    """The longitude whose right ascension is `target` degrees past the MC's
    (the Midheaven's measure, VII's RA), by bisection on the engine's own
    _ra_decl."""
    ra = lambda lon: engine["_ra_decl"](lon, chart["obliquity"])[0]
    mc = chart["mc"]
    lo, hi = mc, mc + 60.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if (ra(mid % 360.0) - ra(mc)) % 360.0 < target:
            lo = mid
        else:
            hi = mid
    return ((lo + hi) / 2.0) % 360.0


@pytest.mark.parametrize("target", [15.0001, 30.0001, 45.0001])
def test_n06_the_ascensional_bands_print_a_distance_inside_the_row_band(engine, chart_2024, target):
    natal = chart_2024[0]
    lon = _lon_at_ascension_past_mc(engine, natal, target)
    data = copy.deepcopy(natal["planetary_data"])
    data["Mars"]["longitude"] = lon
    result = engine["evaluate_ascensional_bands"](data, natal["ascendant"], natal["mc"], natal["obliquity"],
                                                  natal["geo_lat"], natal["sect"])
    row = next(r for r in result["rows"] if r["Planet"] == "Mars")
    assert row["Follows the stake"].startswith("Midheaven"), "the premise: Mars follows the MC"
    printed = _number(row["Ascensional distance"])
    grade = row["App grade (generalised from 2.13, 48-51)"]
    labels = [label for _limit, label, _j in engine["SAHL_2_13_BANDS"]]
    assert labels.index(grade) == _band(target), "the premise: the row's band"
    assert _band(printed) == labels.index(grade), (row["Ascensional distance"], grade)


@pytest.mark.parametrize("arc", [15.0001, 30.0001, 45.0001])
def test_n06_the_grade_by_ascensions_prints_an_arc_inside_its_band(engine, monkeypatch, chart_2024, arc):
    natal = chart_2024[0]
    monkeypatch.setitem(engine, "_prosperity_ascension_from_stake", lambda *a, **k: ("the Ascendant", arc))
    import engine as module
    monkeypatch.setattr(module, "_prosperity_ascension_from_stake", lambda *a, **k: ("the Ascendant", arc))
    rows = engine["evaluate_prosperity"](natal)
    text = next(r["Ground"] for r in rows if r.get("Class") == "Grade by ascensions")
    printed = _number(text.split(":", 1)[1])
    assert _band(printed) == _band(arc), text


# =============================================================================
# N07: Abu Ma'shar's natural connections
# =============================================================================

@pytest.mark.parametrize("sun, moon, degrees, from_exact, motion", [
    (29.999, 150.01, "Sun 29.9° Ari ↔ 0.0° Vir; Moon at 0.0° Vir", "0.0°", "Exact"),
    (0.049, 179.999, "Sun 0.0° Ari ↔ 29.9° Vir; Moon at 29.9° Vir", "0.05°", "Separating"),
    (12.0, 167.96, "Sun 12.0° Ari ↔ 18.0° Vir; Moon at 18.0° Vir", "0.04°", "Applying"),
])
def test_n07_a_natural_connection_prints_no_30_in_a_sign_and_no_0_off_exactness(engine, sun, moon, degrees,
                                                                                 from_exact, motion):
    rows = [r for r in engine["evaluate_abu_natural_connections"](_pdata(Sun=(sun, 1.0), Moon=(moon, 13.0)))
            if r["Pair"] == "Sun & Moon"]
    assert [(r["Degrees"], r["From exact"], r["Motion"]) for r in rows] == [(degrees, from_exact, motion)]


def test_n07_an_exact_counterpart_keeps_its_30(engine):
    """0.0 pairs with 30.0, the sign's far edge (57, 62): that 30 is the
    counterpart's own value, not a carry."""
    rows = [r for r in engine["evaluate_abu_natural_connections"](_pdata(Sun=(0.0, 1.0), Moon=(175.0, 13.0)))
            if r["Pair"] == "Sun & Moon"]
    assert rows and rows[0]["Degrees"].startswith("Sun 0.0° Ari ↔ 30.0° Vir;"), rows


# =============================================================================
# N08: an orb or a relationship distance reads the row's verdicts
# =============================================================================

def test_n08_a_conjunction_a_hair_past_venuss_orb_prints_past_it(engine):
    """Venus 10 Aries, the Moon 17.0001 Aries: the Moon is outside Venus's 7
    degrees, so the bodies are not mutual; 07 00' printed is exactly 7."""
    rows = [r for r in engine["evaluate_ptolemaic_aspects"](_pdata(Venus=(10.0, 1.1), Moon=(17.0001, 13.0)))
            if {r["Light Planet"], r["Heavy Planet"]} == {"Venus", "Moon"}]
    assert [(r["Exact Orb Dist"], r["Bodies"]) for r in rows] == [("07° 01'", "Venus in Moon's body")], rows


def test_n08_an_orb_on_a_whole_degree_still_prints_it(engine):
    assert engine["_format_orb"](7.0) == "07° 00'"
    assert engine["_format_orb"](6.5) == "06° 30'"


def _ind15(engine, chart_2024, saturn):
    natal, sr, _jd = chart_2024
    rev = {p: dict(v) for p, v in sr["planetary_data"].items()}
    rev["Moon"].update(longitude=100.0, speed_in_lon=13.0)
    rev["Saturn"].update(longitude=saturn, speed_in_lon=0.03)
    for p, lon in (("Sun", 200.0), ("Mercury", 205.0), ("Venus", 230.0), ("Mars", 260.0), ("Jupiter", 290.0)):
        rev[p]["longitude"] = lon
    recs = engine["pn4_indicator_relationships"](dict(natal, ascendant=95.0), dict(sr, planetary_data=rev, ascendant=95.0),
                                                 95.0)
    return next(r for r in recs if r["Role"] == "Lord of the natal Ascendant" and r["Partner"] == "Saturn")


def test_n08_indicator_15_a_hair_past_the_moons_12_prints_past_them(engine, chart_2024):
    rec = _ind15(engine, chart_2024, 112.0001)
    assert rec["Connected"] is False and rec["Distance"] == pytest.approx(12.0001), "the premise"
    assert rec["Description"] == ("approaching exactness with Saturn by conjunction; 12.01° from exact; "
                                  "outside the adopted connection window"), rec["Description"]


def test_n08_the_revolutions_page_prints_indicator_15s_distance_past_the_window(engine, monkeypatch):
    """The page's Distance cell, at hundredths, beside a row outside the
    window: a record whose Distance is 12.0001 (constructed at the page's
    formatting site; the export keeps the float)."""
    at = make_app(page="timing", timeout=300)
    import engine as module      # after make_app, which may reload the engine
    original = module.pn4_indicator_relationships

    def patched(*args, **kwargs):
        recs = [dict(r) for r in original(*args, **kwargs)]
        if recs:
            recs[0].update(Distance=12.0001, Connected=False)
        return recs
    monkeypatch.setattr(module, "pn4_indicator_relationships", patched)
    at.run(timeout=300)
    monkeypatch.setattr(module, "pn4_indicator_relationships", original)
    assert_no_exception(at, "Revolutions")
    frames = [n.value for h, n in table_nodes(at) if h == "Indicator 15: relationship details"]
    assert frames, "the premise: indicator 15's table"
    cell = frames[0]["Distance"].iloc[0]
    assert float(cell) > 12.0, cell          # outside the window, as the row reads; "12.00" read inside it


# =============================================================================
# N09: the revolution Moon's conditions
# =============================================================================

def _proxy_six(engine, chart_2024, latitude, elongation):
    natal, sr, _jd = chart_2024
    rev = {p: dict(v) for p, v in sr["planetary_data"].items()}
    rev["Sun"]["longitude"] = 100.0
    rev["Moon"].update(latitude=latitude, longitude=(100.0 + elongation) % 360.0)
    rows = engine["pn4_luminary_proxies"]("Moon", natal, dict(sr, planetary_data=rev))
    return next(r["Reads"] for r in rows if r["Proxy"].startswith("[6]"))


def test_n09_a_moon_a_hair_before_the_sun_prints_no_360(engine, chart_2024):
    reads = _proxy_six(engine, chart_2024, 0.3, 359.99999)
    assert "decreasing in glow (359.9° from the Sun)" in reads, reads


def test_n09_a_moon_a_hair_before_the_full_prints_inside_her_increase(engine, chart_2024):
    reads = _proxy_six(engine, chart_2024, 0.3, 179.99999)
    assert "increasing in glow (179.99° from the Sun)" in reads, reads


def test_n09_a_latitude_that_rounds_to_zero_prints_its_unrounded_value_or_no_sign(engine, chart_2024):
    south = _proxy_six(engine, chart_2024, -0.000001, 10.0)
    assert south.startswith("southern in latitude (-0.00, unrounded: -0.000001);"), south
    zero = _proxy_six(engine, chart_2024, -0.0, 10.0)
    assert zero.startswith("northern in latitude (+0.00);"), zero


# =============================================================================
# N10: Rhetorius's ray evidence beside relief
# =============================================================================

def test_n10_a_friendly_ray_a_hair_under_7_prints_under_7_on_the_page(monkeypatch):
    """The Moon at 10 Cancer besieged by Mars's and Saturn's squares 5
    degrees either side; Venus's sextile 6.99999 degrees ahead relieves her
    ("less than 7"). The detail printed "Distance: 7.00°" beside "Relief: yes"."""
    at = make_app(page="findings", view="supplement", timeout=300)
    import engine as module      # after make_app, which may reload the engine
    original = module.calculate_traditional_chart_jd

    def patched(*args, **kwargs):
        chart = copy.deepcopy(original(*args, **kwargs))
        for planet, lon in (("Moon", 100.0), ("Mars", 5.0), ("Saturn", 15.0), ("Venus", 46.99999),
                            ("Sun", 200.0), ("Jupiter", 170.0), ("Mercury", 150.0)):
            chart["planetary_data"][planet]["longitude"] = lon
        return chart
    monkeypatch.setattr(module, "calculate_traditional_chart_jd", patched)
    at.run(timeout=300)
    key = "affliction_and_fortification_after_rhetorius_detail"
    picked = None
    for option in at.selectbox(key=key).options:
        at.selectbox(key=key).set_value(option).run(timeout=300)
        texts = [m.value for m in at.main.markdown if m.value.startswith("**Ray evidence.**")]
        if any("Donor: Venus" in t for t in texts):
            picked = texts
            break
    monkeypatch.setattr(module, "calculate_traditional_chart_jd", original)
    assert_no_exception(at, "Configurations, the besieged Moon")
    assert picked, "the premise: a row whose ray evidence names Venus"
    venus = next(line for t in picked for line in t.splitlines() if "Donor: Venus" in line)
    assert "Aspect: sextile" in venus and "Relief: True" in venus, ("the premise: Venus's sextile relieves", venus)
    assert "Distance: 6.999°" in venus, venus


def test_n10_the_engine_keeps_the_witness_float(engine):
    siege = ('Mars', 5.0, 'Saturn', 5.0)
    data = _pdata(Moon=(100.0, 13.0), Venus=(46.99999, 1.1))
    planets = ['Saturn', 'Jupiter', 'Mars', 'Sun', 'Venus', 'Mercury', 'Moon']
    rays = engine["_rhetorius_siege_evidence"]('Moon', data, planets, siege)['Ray evidence']
    venus = next(r for r in rays if r['Donor'] == 'Venus')
    assert venus['Relief'] is True and venus['Distance'] == pytest.approx(6.99999)


# =============================================================================
# N11: the strips' age labels are the tables'
# =============================================================================

def test_n11_the_distribution_strips_now_is_the_tables_truncated_age(engine):
    segs = [{'from': 0.0, 'to': 10.0, 'distributor': 'Mars', 'partner': None, 'partner_aspect': None},
            {'from': 10.0, 'to': 20.0, 'distributor': 'Sun', 'partner': None, 'partner_aspect': None}]
    svg = engine["generate_distribution_strip_svg"](segs, 9.9999, unit='years', span=20.0)
    assert re.findall(r'now: age [0-9.]+', svg) == ["now: age 9.999"], re.findall(r'now: age [0-9.]+', svg)


def test_n11_the_hit_strip_prints_the_tables_arc_and_the_truncated_age(engine):
    svg = engine["generate_hit_strip_svg"]([{'Target': "Saturn's body", 'Arc (years)': '9.99'}], 9.9999, span=20.0)
    labels = re.findall(r'>([0-9][0-9.]*)</text>', svg)
    assert "9.99" in labels and "10.0" not in labels, labels
    assert re.findall(r'now: age [0-9.]+', svg) == ["now: age 9.999"]


# =============================================================================
# N12: a short interval does not print empty
# =============================================================================

def test_n12_a_short_years_segment_prints_two_different_ends(engine):
    seg = {'from': 0.0001, 'to': 0.0002, 'distributor': 'Mars', 'partner': None, 'partner_aspect': None,
           'opened_by': '-'}
    row = engine["_pn4_distribution_rows"]([seg], seg, unit='years')[0]
    assert row['Now'] == 'yes'
    assert float(row['From age']) < float(row['To age']), row
    assert float(row['From age']) <= 0.0001 < float(row['To age']) or row['From age'] == "0.0001", row


def test_n12_a_short_days_segment_prints_two_different_ends(engine):
    seg = {'from': 0.001, 'to': 0.004, 'distributor': 'Mars', 'partner': None, 'partner_aspect': None,
           'opened_by': '-'}
    row = engine["_pn4_distribution_rows"]([seg], seg, unit='days')[0]
    assert float(row['From day']) < float(row['To day']), row


# =============================================================================
# N13: a strictly nearer contact is not nearer by 0.0
# =============================================================================

def test_n13_a_contact_nearer_by_a_thousandth_is_not_nearer_by_zero(engine):
    """The Moon at 10 Cancer applies to Mars 11 Aries by square, 1.000 off,
    and to Jupiter 11.001 Pisces by trine, 1.001 off: both connections by
    degree, Mars the nearer."""
    rows = engine["evaluate_cutting_the_light"](_pdata(Moon=(100.0, 13.0), Mars=(11.0, 0.7), Jupiter=(341.001, 0.08)),
                                                None)
    because = [r["Because"] for r in rows if r.get("Planet") == "Moon" and r["Because"].startswith("nearer by")]
    assert because, "the premise: the Moon's cut contact"
    assert all(_number(b) > 0 for b in because), because


# =============================================================================
# Ruling 87, PW-27: the stationary inferior's note says "no band"
# =============================================================================

def test_pw27_the_stationary_note_says_the_text_gives_no_band(engine):
    """Gr. Intr. VII.2, 42 (p. 418): "And when they station, they are in the
    fifth condition" -- no degrees given; 55 (p. 419) has its own
    "day-limit", which "no limits" seemed to deny."""
    note = engine["solar_phase_note"]("Mercury", "eastern", 0.002, 6.5)
    assert "the text gives that condition no band;" in note and "no limits" not in note, note


# =============================================================================
# Ruling 87, PW-18: the civil weekday's lord called this app's stand-in
# =============================================================================

def test_pw18_the_notice_calls_the_civil_weekdays_lord_this_apps_stand_in():
    at = make_app(page="chart", timeout=300)
    at.session_state["manual_lat_key"] = 78.2
    at.session_state["manual_lon_key"] = 15.6
    at.run(timeout=300)
    assert_no_exception(at, "chart, circumpolar")
    notice = [c.value for c in at.main.caption if "not a temporal hour" in c.value]
    assert len(notice) == 1 and "The Lord of the Day is the civil weekday's lord, this app's stand-in, since" in notice[0], \
        notice
    assert len(notice[0]) < 400, len(notice[0])


# =============================================================================
# Ruling 92, PW-31: no capital after "; " in Masha'allah's lords cell
# =============================================================================

def test_pw31_the_lords_cell_has_no_capital_after_a_semicolon(engine):
    text = engine["MASHAALLAH_LORDS"][7][2]["text"]
    assert "; if the Ascendant lord aspects the second lord" in text and "; If" not in text, text


# =============================================================================
# PW-33: the strip names the named mean time it was cast at
# =============================================================================

def test_pw33_the_strip_at_lyon_1900_names_pmt():
    at = _named_app("1900-06-01", (12, 0), 45.7640, 4.8357)
    assert "PMT, a named mean time, was then the civil clock across this area." in _box(at), "the premise"
    assert "Europe/Paris +00:09:21 (PMT)" in _strip(at), _strip(at)


def test_pw33_a_zone_cast_at_its_standard_time_keeps_its_strip():
    at = _named_app("1960-06-01", (12, 0), 45.7640, 4.8357)
    assert "Europe/Paris +01:00 ·" in _strip(at) or "Europe/Paris +01:00\n" in _strip(at), _strip(at)
    assert "(CET)" not in _strip(at), _strip(at)


# =============================================================================
# PW-34: the comment over MEAN_TIME_EXCEPTIONS
# =============================================================================

def test_pw34_the_exceptions_comment_says_sicily_and_its_islands_and_names_the_map():
    text = _engine_text()
    # The table is read from its data file since ATLAS1; the comment stands over the name bound from it.
    comment = text[text.index("# Rome's and Zurich's exceptions inside group (a)"):text.index("MEAN_TIME_EXCEPTIONS = ")]
    assert "Sicily and its islands" in comment, comment
    assert "OpenStreetMap" in comment and "ODbL" in comment, comment


# =============================================================================
# EN-07: an alias is read as the zone it names
# =============================================================================

@pytest.mark.parametrize("alias, zone, local", [
    ("Asia/Calcutta", "Asia/Kolkata", (1880, 6, 1, 12, 0, 0)),
    ("Europe/Kiev", "Europe/Kyiv", (1900, 6, 1, 12, 0, 0)),
])
def test_en07_an_alias_is_refused_where_its_zone_is(engine, alias, zone, local):
    def verdict(name):
        try:
            state = engine["named_zone_state"](name, *local)
        except engine["NamedZoneRefusal"] as refusal:
            return ("refused", refusal.kind, refusal.abbreviation)
        return ("cast", state["abbreviation"], state.get("label"))
    assert verdict(zone)[0] == "refused", "the premise"
    assert verdict(alias) == verdict(zone)


def test_en07_an_alias_of_a_zone_cast_at_its_mean_time_is_cast_and_labelled_as_it(engine):
    for alias, zone, local in (("NZ", "Pacific/Auckland", (1900, 6, 1, 12, 0, 0)),
                               ("Eire", "Europe/Dublin", (1900, 6, 1, 12, 0, 0))):
        assert engine["named_zone_state"](alias, *local) == engine["named_zone_state"](zone, *local), alias


def _pinned_links():
    """Every link in the pinned tzdata release: {link name: target}."""
    zi = Path(str(importlib.resources.files("tzdata") / "zoneinfo")) / "tzdata.zi"
    links = {}
    for line in zi.read_text(encoding="utf-8").splitlines():
        if line.startswith("L "):
            _, target, name = line.split()
            links[name] = target
    return links


def test_en07_the_alias_list_is_the_pinned_releases(engine):
    """ZONE_ALIASES holds every link of the pinned release that is not a
    place of its own (LINKED_ZONES) and names a zone whose named mean times,
    periods, refused stretches or later local mean time the engine keys on."""
    keyed = (set(engine["NAMED_MEAN_TIMES"]) | set(engine["CIVIL_MEAN_TIMES"]) | set(engine["LMT_RETURNS"])
             | set(engine["MEAN_TIME_EXCEPTIONS"]) | set(engine["MEAN_TIME_OUTSIDE"]) | set(engine["MEAN_TIME_CITY_DATES"])
             | set(engine["CHOSEN_STARTS"]) | set(engine["OUTSIDE_STRETCHES"]))
    expected = {name: target for name, target in _pinned_links().items()
                if name not in engine["LINKED_ZONES"] and target in keyed}
    assert engine["ZONE_ALIASES"] == expected


# =============================================================================
# D1R2's check, note 17: NST is St John's mean time under a standard time's name
# =============================================================================

def test_d1r2_17_the_st_johns_refusal_says_whose_mean_time_nst_is():
    at = _named_app("1900-06-01", (12, 0), 47.5615, -52.7126)
    sentence = _refused_on_the_page(at, "1900-06-01", ("America/St_Johns", "holds NST, a mean time taken from one "
                                                       "place's meridian"))
    assert "(St John's, under the name of a standard time)" in sentence, sentence


def test_d1r2_17_the_anniversary_reason_says_it_too(engine):
    moment = engine["anniversary_moment"](engine["CivilMoment"](1880, 6, 1, 12, 0, 0), 20, time_standard="named",
                                          zone_name="America/St_Johns", latitude=47.5615, longitude=-52.7126)
    assert engine["is_unresolved"](moment), moment
    assert "(St John's, under the name of a standard time)" in str(moment.reason), moment.reason


# =============================================================================
# D1R2's check, note 19: the Findings' help names the refused periods
# =============================================================================

def test_d1r2_19_the_fetus_finding_says_a_refused_target_is_unavailable():
    """Since ruling 35 a target in a period the birth would be refused in is
    unavailable too, with its reason in the cell; the help said only a date
    or clock time that does not exist or is ambiguous."""
    at = make_app(page="findings", timeout=300).run(timeout=300)
    assert_no_exception(at, "Findings")
    texts = [m.value for m in at.main.markdown]
    qualification = [t for t in texts if t.startswith("**This app's reading of the year.**")]
    note = [t for t in texts if "The numerical convention repeats the local birth month" in t]
    assert len(qualification) == 1 and len(note) == 1, "the premise: the fetus finding's help and its note"
    assert "a period the birth would be refused in" in qualification[0], qualification[0]
    assert "a period the birth would be refused in" in note[0], note[0]
