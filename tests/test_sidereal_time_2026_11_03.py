"""The sidereal time the angles are cast from: IAU 2006, for every date.

Swiss Ephemeris turns the sky by the IAU 2006 sidereal time only from 1850
to 2050. The engine computes the Greenwich apparent sidereal time and the
true obliquity itself (ephemeris.py's _sidereal_frame) and casts the houses
from them through swe.houses_armc (chart_houses). These pins hold:

* the chart's ARMC (less the east longitude) and obliquity, and its
  Ascendant and MC, to an independent reproduction under the same route
  (fixtures/sidereal_time_iau2006.json, 'rows'): sidereal time 0.002",
  obliquity 0.0015", MC 0.003", Ascendant 0.02" to latitude 60 (the margins
  Swiss Ephemeris's IAU 2000B nutation leaves against IAU 2000A);
* the sidereal time against an integrated IAU 2006 Earth rotation
  ('integrated_rotation'), which the series route leaves by up to 0.06" at
  -500;
* modern charts moving by less than any pin: their angles and cusps against
  swe.houses itself, under 0.01";
* the Ascendant at latitude 60 from an explicit formula, near ARMC 0 and 180
  and where it amplifies an error most, near 270 (the ARMC) and 284 (the
  obliquity);
* the Chart page's sidereal times, and that no house or sidereal-time call
  of Swiss Ephemeris's own is left in the program.
"""
from __future__ import annotations

import ast
import json
import math
import random
from datetime import time

import pytest
import swisseph as swe

from conftest import EXECUTABLE_DIR, assert_no_exception, make_app, source_files
from test_d1r_mean_time_reach_2026_10_06 import _calculation_rows
from test_hostile_l1_2026_10_03 import MANUAL

FIXTURE = json.loads((EXECUTABLE_DIR / "tests" / "fixtures" / "sidereal_time_iau2006.json").read_text(encoding="utf-8"))
ROWS = FIXTURE["rows"]
EARLY = [r for r in ROWS if r["year"] < 1375]
LATE = [r for r in ROWS if r["year"] >= 1375]

GAST_TOL, OBLIQUITY_TOL, MC_TOL, ASC_TOL = 0.002, 0.0015, 0.003, 0.02    # arcseconds


def _arcsec(a, b):
    return abs((a - b + 180.0) % 360.0 - 180.0) * 3600.0


def _chart(engine, row, lat=None, lon=None):
    lat = row.get("latitude", 0.0) if lat is None else lat
    lon = row.get("longitude_east", 0.0) if lon is None else lon
    return engine["calculate_traditional_chart_jd"](row["jd_ut1"], lat, lon), lon


def _check_rows(engine, rows):
    bad = []
    for row in rows:
        # The instant's TT is the reproduction's own (its delta T).
        if abs(swe.deltat_ex(row["jd_ut1"], -1) * 86400.0 - row["delta_t_s"]) > 1e-6:
            bad.append((row["year"], "delta T", swe.deltat_ex(row["jd_ut1"], -1) * 86400.0, row["delta_t_s"]))
        chart, lon = _chart(engine, row)
        checks = [("sidereal time", chart["armc"] - lon, row["gast_deg"], GAST_TOL),
                  ("obliquity", chart["obliquity"], row["true_obliquity_deg"], OBLIQUITY_TOL)]
        if "asc_deg" in row:
            assert abs(row["latitude"]) <= 60.0, row
            checks += [("MC", chart["mc"], row["mc_deg"], MC_TOL), ("Ascendant", chart["ascendant"], row["asc_deg"], ASC_TOL)]
        bad += [(row["year"], what, got, want, _arcsec(got, want)) for what, got, want, tol in checks
                if _arcsec(got, want) > tol]
    return bad


def test_the_fixture_holds_the_rows_it_names():
    assert len(ROWS) == 87 and len(LATE) == 56 and len(EARLY) == 31, (len(ROWS), len(LATE), len(EARLY))
    assert sum("asc_deg" in r for r in ROWS) == 27
    assert sorted(r["year"] for r in FIXTURE["integrated_rotation"]) == [-500, 0, 500, 1000, 1500, 1800, 2000, 2026, 2200]


def test_the_angles_from_1375_on_are_the_reproductions(engine):
    assert _check_rows(engine, LATE) == []


def test_the_angles_before_1375_are_the_reproductions(engine):
    """The same route before 1375: bounded, beside these, by the integrated
    rotation (the next test)."""
    assert _check_rows(engine, EARLY) == []


# The bound on the series route against the integrated IAU 2006 rotation, by
# year (arcseconds).
INTEGRATED_BOUND = {-500: 0.06, 0: 0.02, 500: 0.005}


def test_the_sidereal_time_stays_near_the_integrated_iau_2006_rotation(engine):
    rows = FIXTURE["integrated_rotation"]
    assert len(rows) == 9
    gaps = [(row["year"], _arcsec(engine["calculate_traditional_chart_jd"](row["jd_ut1"], 0.0, 0.0)["armc"],
                                  row["gast_deg"]), INTEGRATED_BOUND.get(row["year"], 0.002)) for row in rows]
    assert [g for g in gaps if g[1] > g[2]] == [], gaps


def test_modern_angles_and_cusps_move_by_less_than_any_pin(engine):
    """1850-2049, a seeded sample at latitudes from -66 to 66: the chart's
    Ascendant, MC and twelve cusps against swe.houses itself, under 0.01".
    (The finest modern angle pin in the suite is a 0.5" window.)"""
    rnd = random.Random(20261103)
    lo, hi = swe.julday(1850, 1, 1, 0.0), swe.julday(2049, 12, 31, 0.0)
    worst = 0.0
    for lat in (-66.0, -45.0, -33.87, 0.0, 23.0, 43.7792, 52.5, 60.0, 66.0):
        for _ in range(8):
            jd, lon = rnd.uniform(lo, hi), rnd.uniform(-180.0, 180.0)
            chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
            cusps, ascmc = swe.houses(jd, lat, lon, b"B")
            pairs = list(zip(chart["houses"], cusps)) + [(chart["ascendant"], ascmc[0]), (chart["mc"], ascmc[1]),
                                                         (chart["armc"], ascmc[2])]
            worst = max([worst] + [_arcsec(a, b) for a, b in pairs])
    assert worst < 0.01, worst


def _ascendant(armc, obliquity, lat):
    """The eastern horizon's ecliptic degree, by the formula."""
    a, e, p = map(math.radians, (armc, obliquity, lat))
    return math.degrees(math.atan2(math.cos(a), -(math.sin(a) * math.cos(e) + math.tan(p) * math.sin(e)))) % 360.0


@pytest.mark.parametrize("target_armc", [0.4, 180.6, 270.4, 284.0])
def test_the_ascendant_at_latitude_60_is_the_formulas(engine, target_armc):
    """The 1500 instant of the fixture, its longitude chosen to put the ARMC
    at target_armc: the chart's Ascendant against the formula fed the
    fixture's sidereal time and obliquity. Near 270 an error in the ARMC
    reaches the Ascendant 4.4 times over; near 284, one in the obliquity 4.8
    times; near 0 and 180, 0.6 and 1.1 times."""
    row = next(r for r in ROWS if r["year"] == 1500)
    lon = (target_armc - row["gast_deg"] + 180.0) % 360.0 - 180.0
    chart = engine["calculate_traditional_chart_jd"](row["jd_ut1"], 60.0, lon)
    armc = (row["gast_deg"] + lon) % 360.0
    assert _arcsec(armc, target_armc) < 1e-6
    expect = _ascendant(armc, row["true_obliquity_deg"], 60.0)
    assert _arcsec(chart["ascendant"], expect) < ASC_TOL, (chart["ascendant"], expect)


def test_the_chart_page_shows_the_sidereal_time_the_angles_were_cast_from(engine):
    """Year 500, noon UT at Florence: the Greenwich and local sidereal times
    the Calculation table prints are the reproduction's, and the chart's
    RAMC is the local one in degrees."""
    lat, lon = 43.7792, 11.2463
    at = make_app(date="0500-06-21", page="chart", timeout=300)
    at.session_state["time_input_key"] = time(12, 0, 0)
    at.session_state["time_standard_key"] = MANUAL
    at.session_state["utc_offset_key"] = 0.0
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.run(timeout=300)
    assert_no_exception(at, "chart 0500-06-21 12:00 UT")
    calc = _calculation_rows(at)
    jd = engine["civil_to_jd"](500, 6, 21, 12.0)
    row = next(r for r in ROWS if r["year"] == 500 and r.get("longitude_east") == 0.0 and r.get("latitude") == 0.0)
    assert row["jd_ut1"] == jd, (row["jd_ut1"], jd)
    gast = row["gast_deg"]

    def hms(hours):
        total = min(int(round((hours % 24.0) * 3600)), 24 * 3600 - 1)
        return f"{total // 3600:02d}h {(total % 3600) // 60:02d}m {total % 60:02d}s"
    assert calc["Greenwich sidereal time at birth"] == hms(gast / 15.0), calc
    assert calc["Local sidereal time"] == hms((gast + lon) / 15.0), calc
    armc = engine["calculate_traditional_chart_jd"](jd, lat, lon)["armc"]
    assert _arcsec(armc, engine["greenwich_sidereal_time"](jd) + lon) < 1e-6
    assert _arcsec(armc, gast + lon) < GAST_TOL


def _swe_calls():
    for path in source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id in ("swe", "_swisseph")):
                yield path.name, node, tree


def test_no_house_or_sidereal_time_call_of_swiss_ephemeris_is_left():
    """Every house and sidereal-time call goes through chart_houses: no
    swe.houses, houses_ex, sidtime or sidtime0 anywhere in the program, and
    swe.houses_armc only inside chart_houses."""
    left = [(f, n.lineno, ast.unparse(n)) for f, n, _t in _swe_calls()
            if n.func.attr in ("houses", "houses_ex", "houses_ex2", "sidtime", "sidtime0")]
    assert left == [], left
    armc_calls = []
    for path in source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if isinstance(fn, ast.FunctionDef):
                armc_calls += [(path.name, fn.name) for n in ast.walk(fn) if isinstance(n, ast.Call)
                               and isinstance(n.func, ast.Attribute) and n.func.attr == "houses_armc"]
    assert armc_calls == [("ephemeris.py", "chart_houses")], armc_calls


def test_each_caller_casts_its_houses_with_the_obliquity_of_the_same_frame(engine):
    """Where the engine pairs an ARMC with an obliquity, the obliquity is
    true_obliquity at the same instant: no ECL_NUT read is left outside
    _sidereal_frame."""
    reads = [(f, n.lineno) for f, n, _t in _swe_calls()
             if n.func.attr in ("calc", "calc_ut") and len(n.args) > 1 and ast.unparse(n.args[1]) == "swe.ECL_NUT"]
    assert len(reads) == 1 and reads[0][0] == "ephemeris.py", reads
    row = next(r for r in ROWS if r["year"] == 500 and "asc_deg" in r)
    chart = engine["calculate_traditional_chart_jd"](row["jd_ut1"], row["latitude"], row["longitude_east"])
    assert chart["obliquity"] == engine["true_obliquity"](row["jd_ut1"])
    assert _arcsec(chart["armc"], engine["greenwich_sidereal_time"](row["jd_ut1"]) + row["longitude_east"]) < 1e-6
