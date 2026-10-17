"""The spherical-astronomy layer: three defects found by an external audit
on 2026-09-08 and reproduced here before fixing, each pinned by the input
that failed.

A1  _lon_with_oblique_ascension returned a degree six degrees off above the
    polar circle (its scan-and-bisect assumed a sign change it never
    bracketed). Now closed-form within |lat| + obliquity < 90 and None
    outside, where the inverse is not unique.
A2  _hours_from_stake raised ZeroDivisionError: a remainder that rounds to
    exactly 360.0, and day/night semi-arcs from two different ascensional
    differences that did not close to 180. Now one difference, exact
    closure, and a zero semi-arc handled as a stated degenerate case.
B3  calculate_traditional_chart read sect from the Sun's ecliptic degree
    against the Ascendant, which can invert near the poles and exactly on
    the horizon. Now from the Sun's altitude.

Every failing input is built here, none pasted from a report (the one
literal-free construction, nextafter, is required to be built in the test).
Mathematics only: no doctrine, no corpus, no table.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

import pytest
import swisseph as swe

EPS = 23.4392911
OBLIQUITIES = (0.0, EPS, 24.5)


def _lat_grid(limit=65.0, step=0.5):
    n = int(round(2 * limit / step))
    return [-limit + k * step for k in range(n + 1)]


def _signed(a, b):
    return ((a - b + 180.0) % 360.0) - 180.0


def _sun_sin_altitude(chart, lat):
    """The altitude test, computed independently of the app from the values
    the chart carries: geocentric, no refraction."""
    sun = chart["planetary_data"]["Sun"]
    ra, dec, _r = swe.cotrans((sun["longitude"], sun["latitude"], sun["distance"]), -chart["obliquity"])
    p, d, h = map(math.radians, (lat, dec, chart["armc"] - ra))
    return math.sin(p) * math.sin(d) + math.cos(p) * math.cos(d) * math.cos(h)


# --- A2: _hours_from_stake must never divide by zero ------------------------

A2_INPUTS = [
    (60.5, 58.339603018574614, EPS, -70.0),
    (240.5, 238.33960301857465, EPS, 70.0),
    (60.0, 57.81874126060251, EPS, -69.8496311285815),
]


@pytest.mark.parametrize("lon,armc,obliquity,lat", A2_INPUTS)
def test_a2_reported_inputs_return_finite_hours(engine, lon, armc, obliquity, lat):
    quadrant, stake, hours = engine["_hours_from_stake"](lon, armc, obliquity, lat)
    assert math.isfinite(hours) and 0.0 <= hours <= 6.0 + 1e-9, (quadrant, stake, hours)


def test_a2_armc_one_ulp_above_the_planets_ra(engine):
    # No decimal literal: the Midheaven's right ascension is the planet's
    # own, moved by one floating-point step. The remainder (ra - armc) is a
    # tiny negative number, and -1e-16 % 360.0 is exactly 360.0.
    assert -1e-16 % 360.0 == 360.0
    ra, _decl = engine["_ra_decl"](60.5, EPS)
    armc = math.nextafter(ra, math.inf)
    for lat in (-70.0, 70.0, -66.6, 66.6, 43.7792, 0.0):
        quadrant, stake, hours = engine["_hours_from_stake"](60.5, armc, EPS, lat)
        assert math.isfinite(hours) and 0.0 <= hours <= 6.0 + 1e-9, (lat, quadrant, stake, hours)


def test_a2_semiarcs_close_to_180_exactly(engine):
    # Both semi-arcs from one ascensional difference: 6*h_day + 6*h_night is
    # 180 exactly, not to a tolerance, across the whole grid (the old code's
    # two differences left 6*h_day + 6*h_night = 179.99999914 at 70S).
    for obliquity in OBLIQUITIES:
        for lat in _lat_grid():
            for lon in range(0, 360, 3):
                arc_day, arc_night = engine["_semiarcs"](float(lon), obliquity, lat)
                h_day, h_night = arc_day / 6.0, arc_night / 6.0        # as _hours_from_stake divides
                assert arc_day + arc_night == 180.0, (obliquity, lat, lon)
                assert 6.0 * h_day + 6.0 * h_night == 180.0, (obliquity, lat, lon)


def test_a2_a_polar_degree_that_never_rises_has_a_zero_day_arc_and_still_gives_hours(engine):
    # At 70S the degree 60.5 (declination about +20) never rises: its day
    # semi-arc is exactly 0 and its night semi-arc exactly 180. Every
    # Midheaven distance still classifies and gives finite hours.
    arc_day, arc_night = engine["_semiarcs"](60.5, EPS, -70.0)
    assert (arc_day, arc_night) == (0.0, 180.0)
    ra, _decl = engine["_ra_decl"](60.5, EPS)
    for step in range(0, 3600):
        armc = (ra - step / 10.0) % 360.0
        _q, _s, hours = engine["_hours_from_stake"](60.5, armc, EPS, -70.0)
        assert math.isfinite(hours) and 0.0 <= hours <= 6.0 + 1e-9, (step, hours)


def test_a2_ordinary_latitude_hours_are_unchanged_in_kind(engine):
    # Regression guard for the D-1 tests' latitude: the quadrant boundaries
    # are the semi-arcs, and hours run 0..6 within each.
    for lon in range(0, 360, 5):
        q, stake, hours = engine["_hours_from_stake"](float(lon), 100.0, 23.44, 43.7792)
        assert 0.0 <= hours <= 6.0 + 1e-9, (lon, q, hours)


# --- A1: the oblique-ascension inverse -------------------------------------

def test_a1_round_trip_max_residual_over_the_grid(engine):
    inv, oa_of = engine["_lon_with_oblique_ascension"], engine["_oblique_ascension"]
    worst, where, n = 0.0, None, 0
    for obliquity in OBLIQUITIES:
        for lat in _lat_grid():
            for oa in range(0, 360, 3):
                lon = inv(float(oa), obliquity, lat)
                assert lon is not None, (obliquity, lat, oa)
                r = abs(_signed(oa_of(lon, obliquity, lat), float(oa)))
                n += 1
                if r > worst:
                    worst, where = r, (obliquity, lat, oa)
    assert n == 93960
    assert worst < 1e-9, (worst, where)


A1_CASES = [
    # (target OA, obliquity, latitude, the correct longitude, what the old code returned)
    (35.0, EPS, 70.0, 120.7562210318, 301.0),
    (185.0, EPS, -66.6, 273.4262029081, 94.0),
]


@pytest.mark.parametrize("oa,obliquity,lat,correct,wrong", A1_CASES)
def test_a1_reported_cases_refuse_rather_than_return_the_wrong_degree(engine, oa, obliquity, lat, correct, wrong):
    # Both cases lie outside |lat| + obliquity < 90, so the decision taken
    # (refuse outside the domain) gives the explicit no-solution signal.
    # The cited correct longitude is checked to be a genuine solution, and
    # the old answer to be a wrong one, so this test would also catch a
    # future closed-form-everywhere implementation returning the wrong root.
    assert abs(lat) + obliquity >= 90.0
    oa_of = engine["_oblique_ascension"]
    assert abs(_signed(oa_of(correct, obliquity, lat), oa)) < 1e-6
    assert abs(_signed(oa_of(wrong, obliquity, lat), oa)) > 1.0
    assert engine["_lon_with_oblique_ascension"](oa, obliquity, lat) is None


def test_a1_first_case_is_not_a_circumpolar_rise(engine):
    # The 35/70N case is inside the admissible interval for its own degree
    # (tan(lat) tan(decl) = 0.99937 < 1): the old scan simply missed the
    # branch. The refusal is about the latitude, not this degree.
    _ra, decl = engine["_ra_decl"](120.7562210318, EPS)
    x = math.tan(math.radians(70.0)) * math.tan(math.radians(decl))
    assert 0.999 < x < 1.0


def test_a1_domain_boundary(engine):
    inv = engine["_lon_with_oblique_ascension"]
    assert inv(35.0, EPS, 66.0) is not None          # 89.44 < 90
    assert inv(35.0, EPS, -66.0) is not None
    assert inv(35.0, EPS, 66.6) is None              # 90.04
    assert inv(35.0, EPS, -66.6) is None
    assert inv(35.0, EPS, 90.0 - EPS) is None        # the critical latitude itself: a flat interval
    assert inv(35.0, 0.0, 89.0) is not None          # no obliquity, every degree rises below the pole
    assert engine["_ascensional_method_applies"](EPS, 43.7792)
    assert not engine["_ascensional_method_applies"](EPS, 70.0)


def test_a1_rays_within_the_domain_are_all_given(engine):
    for lat in (0.0, 43.7792, -55.0, 66.0):
        for lon in range(0, 360, 30):
            cast = engine["cast_rays_by_ascension"](float(lon), 100.0, EPS, lat)
            for name, _arc in engine["RAY_ASPECTS"]:
                r = cast[name]
                assert r["ascensional"] is not None and r["from the city's ascensions (15)"] is not None, (lat, lon, name)


def test_a1_rays_outside_the_domain_are_refused_not_fabricated(engine):
    for lat in (70.0, -66.6, 90.0 - EPS):
        cast = engine["cast_rays_by_ascension"](120.0, 100.0, EPS, lat)
        for name, _arc in engine["RAY_ASPECTS"]:
            r = cast[name]
            assert r["ascensional"] is None and r["from the city's ascensions (15)"] is None, (lat, name)
            assert r["from right ascensions (14)"] is not None          # 14 needs no latitude
            assert math.isfinite(r["hours"])
        assert cast["Opposition"]["ascensional"] == 300.0               # 22: exempt at every latitude


def test_a1_the_rays_table_says_the_method_does_not_apply(engine):
    p = {"Sun": {"longitude": 120.0}, "Moon": {"longitude": 10.0}, "North Node": {"longitude": 0.0}}
    rows = engine["evaluate_rays_by_ascension"](p, 100.0, EPS, 70.0)
    assert len(rows) == 14
    for r in rows:
        if r["Ray"] == "Opposition":
            assert r["Ascensional ray (VII.7)"] == engine["get_degree_string"](r["Planet"] == "Sun" and 300.0 or 190.0)
            assert r["Apart"] == "0.00°"
        else:
            assert r["Ascensional ray (VII.7)"] == engine["RAYS_OUT_OF_DOMAIN"]
            assert r["Ascensional ray (VII.7)"].startswith("[Uncertain -- ")
            assert r["Apart"] == "--"
    rows = engine["evaluate_rays_by_ascension"](p, 100.0, EPS, 43.7792)
    assert all(not r["Ascensional ray (VII.7)"].startswith("[") for r in rows)


# --- B3: sect from the Sun's altitude ----------------------------------------

B3_CHARTS = [
    (datetime(2026, 1, 1, 0, 0), -70.0, 0.0),                    # polar summer, Sun three degrees up
    (datetime(2000, 1, 1, 12, 0), 45.0, -64.01866714634343),     # Sun a fifth of an arcsecond up
]


@pytest.mark.parametrize("dt,lat,lon", B3_CHARTS)
def test_b3_reported_charts_are_diurnal(engine, dt, lat, lon):
    chart = engine["calculate_traditional_chart"](dt, lat, lon)
    assert _sun_sin_altitude(chart, lat) > 0.0
    assert chart["sect"] == "Diurnal"
    # And the old ecliptic proxy really did say the opposite here.
    assert not ((chart["planetary_data"]["Sun"]["longitude"] - chart["ascendant"]) % 360.0 > 180.0)


# The horizon sect turns on: the Sun's visible disk, not his centre (one
# horizon with the planetary hours, Gr. Intr. VI.33, 4 and 17; hostile pass
# 2026-10-03, L1-04). The engine takes the instant from swe.rise_trans, and
# the centre's geometric altitude at that instant is engine.sun_up_altitude
# (rise_trans's own horizon refraction and the Sun's semi-diameter at his
# distance, less his parallax: about -52.3' in June, -52.9' in December --
# not the flat -50' of convention, which sits 2.3' above it; F5 re-check,
# R1). rise_trans's iteration lands within arcseconds of it, so the guard
# leaves a thin band either side alone.
SUN_UP_BAND = math.sin(math.radians(0.005))


def test_b3_sect_agrees_with_the_altitude_test_at_ordinary_latitudes(engine):
    # Regression guard: random charts at |lat| <= 60 must classify exactly
    # as the altitude test does, with the visible-disk horizon, away from
    # the arcseconds either side of it. The old proxy also passed the
    # geometric form of this sweep, which is why the fixtures (none polar)
    # were predicted, and found, unchanged.
    rng = random.Random(20260908)
    start = datetime(1200, 1, 1)
    span = (datetime(2100, 1, 1) - start).total_seconds()
    disagreements = []
    for _ in range(1500):
        dt = start + timedelta(seconds=rng.uniform(0.0, span))
        dt = dt.replace(microsecond=0)
        lat, lon = rng.uniform(-60.0, 60.0), rng.uniform(-180.0, 180.0)
        chart = engine["calculate_traditional_chart"](dt, lat, lon)
        sin_alt = _sun_sin_altitude(chart, lat)
        horizon = engine["sun_up_sin_altitude"](chart["planetary_data"]["Sun"]["distance"])
        if abs(sin_alt - horizon) < SUN_UP_BAND:
            continue
        expect = "Diurnal" if sin_alt > horizon else "Nocturnal"
        if chart["sect"] != expect:
            disagreements.append((dt, lat, lon, chart["sect"], expect))
    assert disagreements == []


def test_b3_the_chart_still_reports_the_obliquity_it_used(engine):
    chart = engine["calculate_traditional_chart"](datetime(1240, 5, 23, 13, 45), 43.7792, 11.2463)
    assert abs(chart["obliquity"] - swe.calc_ut(chart["julian_day"], swe.ECL_NUT)[0][0]) < 1e-12


# --- B3 continued: the prenatal syzygy's "above the horizon" ----------------
# The same ecliptic proxy decided which luminary was up at a Preventional
# syzygy and the syzygy chart's own sect. For the Moon the proxy is wrong
# at ORDINARY latitudes too, since its ecliptic latitude reaches five
# degrees: within a few degrees of the horizon the proxy and the altitude
# disagree (46 of 3,000 random charts at |lat| <= 60; 16 Preventional
# syzygy degrees moved). The Sun never disagreed in that sweep.

def _syzygy_flags(jd, lat, lon):
    """Independent altitude test for both luminaries at the syzygy moment."""
    _, ascmc = swe.houses(jd, lat, lon, b"B")
    obliquity = swe.calc_ut(jd, swe.ECL_NUT)[0][0]
    out = {}
    for name, body in (("Sun", swe.SUN), ("Moon", swe.MOON)):
        r = swe.calc_ut(jd, body)[0]
        ra, dec, _d = swe.cotrans((r[0], r[1], r[2]), -obliquity)
        p, d, h = map(math.radians, (lat, dec, ascmc[2] - ra))
        out[name] = (math.sin(p) * math.sin(d) + math.cos(p) * math.cos(d) * math.cos(h) > 0.0, r[0])
    return out


def _old_proxy_pick(jd, lat, lon):
    _, ascmc = swe.houses(jd, lat, lon, b"B")
    sun, moon = swe.calc_ut(jd, swe.SUN)[0][0], swe.calc_ut(jd, swe.MOON)[0][0]
    sun_up, moon_up = (sun - ascmc[0]) % 360.0 > 180.0, (moon - ascmc[0]) % 360.0 > 180.0
    return sun if (sun_up and not moon_up) else moon


SYZYGY_FLIPS = [
    # (birth UT, lat, lon, luminary the altitude rule picks): Preventional
    # births whose syzygy degree the old proxy got wrong.
    # Polar: the Sun up and the Moon down by altitude; the proxy read the
    # Moon up and defaulted to it.
    (datetime(1375, 10, 15, 20, 20, 57), -74.96408391086848, -0.08166520555499801, "Sun"),
    # Ordinary latitude: BOTH luminaries a hair above the horizon (the Moon
    # by its own ecliptic latitude), so the rule defaults to the Moon; the
    # proxy read the Moon down and chose the Sun.
    (datetime(1740, 12, 15, 3, 17, 20), -58.744603212943986, -71.45233155269433, "Moon"),
]


@pytest.mark.parametrize("dt,lat,lon,picked", SYZYGY_FLIPS)
def test_b3_preventional_syzygy_takes_the_luminary_that_is_really_up(engine, dt, lat, lon, picked):
    chart = engine["calculate_traditional_chart"](dt, lat, lon)
    s = engine["calculate_prenatal_syzygy"](chart["julian_day"], lat, lon, chart["houses"])
    assert s["event_type"] == "Preventional"
    flags = _syzygy_flags(s["jd_syzygy"], lat, lon)
    expect = "Sun" if (flags["Sun"][0] and not flags["Moon"][0]) else "Moon"
    assert expect == picked
    assert abs(s["syzygy_longitude"] - flags[picked][1]) < 1e-9
    assert s["sect_diurnal"] == flags["Sun"][0]
    old = _old_proxy_pick(s["jd_syzygy"], lat, lon)
    assert abs(((old - s["syzygy_longitude"] + 180.0) % 360.0) - 180.0) > 1.0   # the old code chose the other luminary


def _sun_up_by_events(jd, lat, lon):
    """Independent one-horizon test for the syzygy's sect: is the last of
    swe.rise_trans's apparent risings and settings of the Sun's upper limb
    before jd a rising? Each kind is collected forward from two days back,
    every search starting just past the event before it, so no event is
    looked for in the quarter-hour after a search's start. At |lat| <= 60
    the Sun rises and sets every day, so a missing event is a failure, not
    a fallback."""
    last = None
    for rsmi, kind in ((swe.CALC_RISE, "rise"), (swe.CALC_SET, "set")):
        t = jd - 2.0
        while True:
            res, tret = swe.rise_trans(t, swe.SUN, rsmi, (lon, lat, 0.0))
            assert res == 0, (jd, lat, lon, kind, res)
            if tret[0] >= jd:
                break
            if last is None or tret[0] > last[0]:
                last = (tret[0], kind)
            t = tret[0] + 1e-4
    assert last is not None, (jd, lat, lon)
    return last[1] == "rise"


def test_b3_syzygy_flags_agree_with_the_altitude_test_at_ordinary_latitudes(engine):
    """600 seeded random lunations at |lat| <= 60, every one asserted: the
    sect against an independent test of the app's one horizon, and a
    Preventional syzygy's luminary against the altitude test.

    The sect's oracle follows the owner's ruling of 2026-10-04 on the one
    horizon (Q8): the lunation's sect is divided as every other sect in the
    app is, at the Sun's visible rising and setting (Gr. Intr. VI.33, 4 and
    17 with Dykes's fn 357), so it is asked of swe.rise_trans's events
    (_sun_up_by_events), not of the Sun's centre against the true horizon,
    which this test asserted until then. Same charts, same number of them,
    no band left out. Five of the 600 lunations fall between the two
    horizons and read Diurnal now (1399-12-08 5.73N 140.31W, 1733-04-08
    38.36N 116.79E, 1806-01-28 43.37S 6.63W, 2020-01-29 55.13N 80.81W,
    1273-10-16 54.95S 108.82W, by the birth). The luminary "above the earth"
    stays the centre's altitude (_syzygy_flags), as the engine keeps it."""
    rng = random.Random(20260908)
    start = datetime(1200, 1, 1)
    span = (datetime(2100, 1, 1) - start).total_seconds()
    for _ in range(600):
        dt = (start + timedelta(seconds=rng.uniform(0.0, span))).replace(microsecond=0)
        lat, lon = rng.uniform(-60.0, 60.0), rng.uniform(-180.0, 180.0)
        chart = engine["calculate_traditional_chart"](dt, lat, lon)
        s = engine["calculate_prenatal_syzygy"](chart["julian_day"], lat, lon, chart["houses"])
        flags = _syzygy_flags(s["jd_syzygy"], lat, lon)
        assert s["sect_diurnal"] is _sun_up_by_events(s["jd_syzygy"], lat, lon), (dt, lat, lon)
        if s["event_type"] == "Preventional":
            expect = flags["Sun"][1] if (flags["Sun"][0] and not flags["Moon"][0]) else flags["Moon"][1]
            assert abs(s["syzygy_longitude"] - expect) < 1e-9, (dt, lat, lon)
