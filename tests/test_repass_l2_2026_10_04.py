"""Re-pass of lane L2 (Sahl's approaches, Gr. Intr. VII) on the development
repository's main, 428e05e.

The hostile pass of 2026-10-03 found L2-01..L2-09 (and the outside pass HP-03,
HP-18); lanes F6, F6b and F7 fixed them. This file holds what the re-pass found
beside those fixes. Each strict xfail asserts the behaviour the cited sentence
(or the owner's ruling) requires and fails today at the assertion that states
the finding; each carries its premise checks first, so it cannot fail for a
moved chart. Two ordinary tests pin behaviour the fixes got right but whose
own pins could not fail (L2R-05, L2R-06).

Nothing in engine.py or app.py changes here: the fixer is not the verifier.
"""
from __future__ import annotations

import re
from datetime import time

import pytest

from conftest import make_app, assert_no_exception, table_nodes, apply_switches

FLORENCE = (43.7792, 11.2463)
LMT_1430_UT = 14.5 - FLORENCE[1] / 15.0          # the harness's 14:30 LMT at Florence, in UT

SPEED = {'Moon': 13.0, 'Mercury': 1.3, 'Venus': 1.2, 'Sun': 0.9856,
         'Mars': 0.5, 'Jupiter': 0.08, 'Saturn': 0.03, 'North Node': -0.05}
CUSPS = [(0.0 + 30.0 * i) % 360.0 for i in range(12)]


def body(lon, speed, lat=0.0):
    return {'longitude': lon % 360.0, 'latitude': lat, 'distance': 1.0,
            'speed_in_lon': speed, 'speed_in_lat': 0.0, 'speed_in_dist': 0.0}


def chart(**lons):
    return {name: body(lon, SPEED[name]) for name, lon in lons.items()}


def pair_row(engine, pd, a, b):
    return next(r for r in engine['evaluate_ptolemaic_aspects'](pd)
                if {r['Light Planet'], r['Heavy Planet']} == {a, b})


def real_chart(engine, y, m, d, hour_ut):
    jd = engine['civil_to_jd'](y, m, d, hour_ut)
    return jd, engine['calculate_traditional_chart_jd'](jd, *FLORENCE)


def page_text(at):
    return "\n".join([m.value for m in at.main.markdown] + [c.value for c in at.main.caption])


# --------------------------------------------------------------------------
# L2-01 partly: R2's note under Abu Ma'shar's connection rule
# --------------------------------------------------------------------------

def test_l2_01_partly_the_wild_note_names_sahls_set_under_abu_mashars_rule():
    """1240-05-26 14:30 LMT Florence: the Moon 0°38' past Saturn in Cancer.
    Under Sahl's rule the row is "Under a single blanket" and 111 does not
    fire (R2). Under Abu Ma'shar's rule (VII.5, 16, 34: separated at 1') the
    same row reads "Separated", and 111 -- run under Sahl's doctrine, as R2
    and Sahl's list require -- still does not fire. The note must then say
    whose connected set 111 reads, not "the aspects table's"."""
    at = make_app(date="1240-05-26", page="configurations", switches={"connection": "Abu Ma'shar"})
    at.run(timeout=300)
    assert_no_exception(at, "1240-05-26 configurations, Abu Ma'shar's rule")
    conf = at.session_state["_analysis_export"]["results"]["Configurations"]
    rows = [r for t in conf["Aspects, aversions and connections"] for r in t["rows"]]
    moon = [r for r in rows if 'Moon' in (r.get("Light Planet"), r.get("Heavy Planet"))]
    saturn = next(r for r in moon if 'Saturn' in (r["Light Planet"], r["Heavy Planet"]))
    assert saturn["Motion"] == "Separating" and saturn["Connection"] == "Separated"      # premise: his table
    assert moon and all(r["Connection"] in ("Separated", "–") for r in moon), \
        [(r["Heavy Planet"], r["Connection"]) for r in moon]
    defects = conf["Corruption of the Moon"][0]["rows"][0]["Defects"]
    assert "(111)" not in defects, defects                                                  # premise: Sahl's set, R2
    note = next(m.value for m in at.main.markdown if "**Wild (111).**" in m.value)
    sentence = next(s for s in re.split(r"(?<=\.)\s+", note) if "connected set" in s)
    assert "Sahl" in sentence, sentence


# --------------------------------------------------------------------------
# L2R-01: Sahl 57's "empty in course" beside R2
# --------------------------------------------------------------------------

def test_l2r_01_a_moon_still_connected_is_not_empty_in_course_for_57(engine):
    """R2 (owner, 2026-10-03): "a Moon still connected by 9-10, or united in
    one sign, is not empty of course" (63: "not connecting with any of the
    planets, and not uniting with one"); 57 opens "if the Moon was empty in
    course" and Dykes's fn 76 sends it to 63. 1240-05-26 14:30 LMT Florence
    is a fixture chart: the Moon 0°38' past Saturn in Cancer."""
    jd, c = real_chart(engine, 1240, 5, 26, LMT_1430_UT)
    pd, sect = c['planetary_data'], c['sect']
    row = pair_row(engine, pd, 'Moon', 'Saturn')
    assert row['Motion'] == 'Separating' and row['Connection'] == 'Under a single blanket'   # premise: 10
    corruption = engine['evaluate_corruption_of_the_moon'](pd, c['houses'], sect)
    assert corruption['testimonies'][111]['matched'] is False                                  # premise: R2
    sim = engine['_simulate_forward'](pd, jd)
    after_the_sign_change = [r for r in engine['evaluate_reception'](pd, sect, sim)
                             if r['Received'] == 'Moon' and '(57)' in str(r['Direction'])]
    assert after_the_sign_change == [], after_the_sign_change


# --------------------------------------------------------------------------
# L2R-02: the relief's "less than 7°"
# --------------------------------------------------------------------------

def test_l2r_02_relief_is_less_than_seven_as_its_sentences_and_vii6_60_say(engine):
    """Rhetorius Ch. 41 gives the siege "within 7 degrees"; the relief is not
    his sentence but ITA IV.4.2's ("less than 7° between that planet and its
    rays", the Latin Gr. Intr. VII.6; "less than 7° between it and the
    connection", al-Qabisi) and Gr. Intr. VII.6, 60 ("there was less than 7°
    between the planet and those rays"). This contradicts
    test_l2_07_rhetorius_seven_degrees_read_the_same_way_on_both_sides,
    which pins the F6 reading; the owner chooses which stands."""
    # The same sentence (VII.6, 60) in Abu Ma'shar's own table: Fig. 145 with
    # Jupiter's trine exactly 7.0 degrees ahead of the Moon, then 6.99 (Jupiter 79.99).
    for jupiter, dissolver in ((80.0, None), (79.99, 'Jupiter')):
        pd = chart(Moon=193.0, Saturn=18.0, Mars=130.0, Jupiter=jupiter, Sun=300.0, Venus=330.0, Mercury=310.0)
        rows = engine['_pairwise_configurations'](pd)
        assert engine['_abu_mashar_enclosed']('Moon', engine['INFORTUNES'], pd, rows) == \
            (True, 'by degree (57)', dissolver)                                            # premise: VII.6, 60 exclusive
    pd = {'Moon': body(100.0, 13.0), 'Mars': body(93.0, 0.5), 'Saturn': body(107.0, 0.03),
          'Jupiter': body(100.0 + 7.0 - 120.0, 0.08)}
    planets = list(pd)
    assert engine['_rhetorius_besiegers']('Moon', pd, planets, engine['INFORTUNES']) == ('Mars', 7.0, 'Saturn', 7.0)
    assert engine['_rhetorius_loosener']('Moon', pd, planets, {'Jupiter', 'Venus', 'Sun'}, True) is None


# --------------------------------------------------------------------------
# L2R-03: the residue's Connecting planet when the heavier departs
# --------------------------------------------------------------------------

def test_l2r_03_a_heavier_planet_departing_over_a_cusp_is_marked_as_in_one_sign(engine):
    frame = {'Sun': body(200.0, 0.9856), 'Moon': body(250.0, 13.0)}
    in_one_sign = dict(frame, Mercury=body(10.0, 0.2), Venus=body(10.0 + 2.0 / 60.0, 1.2))
    one = pair_row(engine, in_one_sign, 'Mercury', 'Venus')
    assert one['Motion'] == 'Separating' and one['Connecting planet'] == 'Venus → Mercury (its own motion)'  # premise
    over_the_cusp = dict(frame, Mercury=body(29.0 + 59.0 / 60.0, 0.2), Venus=body(30.0 + 1.0 / 60.0, 1.2))
    row = pair_row(engine, over_the_cusp, 'Mercury', 'Venus')
    assert row['Aspect'] == 'Aversion' and row['Motion'] == 'Separating'                    # premise: the residue
    assert row['Connecting planet'].startswith('Venus → Mercury')                            # premise: L2-04's rule
    assert re.fullmatch(r"Venus → Mercury \(.+\)", row['Connecting planet']), row['Connecting planet']


# --------------------------------------------------------------------------
# L2R-04: Weakness 97's receiver against the reception table
# --------------------------------------------------------------------------

def test_l2r_04_weakness_97_counts_the_receiver_the_reception_table_names(engine):
    """Sahl 97: "it is separating from a planet receiving it"; 49-50: reception
    by house or exaltation, "and below this reception is if it is connecting
    with a planet from the triplicity"; R3: Sahl I Figure 4's partner bears
    triplicity in Sahl's reception. The Moon 15 Gemini, 5 degrees past
    Jupiter 10 Gemini (the airy partner), every other body averse."""
    pd = chart(Moon=75.0, Jupiter=70.0, Sun=100.0, Mercury=230.0, Venus=280.0, Mars=40.0, Saturn=235.0)
    pd['North Node'] = body(300.0, SPEED['North Node'])
    sect = 'Diurnal'
    row = pair_row(engine, pd, 'Moon', 'Jupiter')
    assert row['Motion'] == 'Separating' and row['Connection'] == 'Under a single blanket'   # premise: connected (10)
    assert 'Jupiter' in engine['sahl_triplicity_lords'](75.0, sect)                         # premise: R3
    received = [r for r in engine['evaluate_reception'](pd, sect)
                if r['Receiver'] == 'Jupiter' and r['Received'] == 'Moon']
    assert received and received[0]['Via'] == 'triplicity', received                         # premise: the page's table
    essential = engine['evaluate_essential_dignities'](pd, sect)
    accidental = engine['evaluate_accidental_dignities'](pd, CUSPS, sect)
    weakness = next(r for r in engine['evaluate_weakness_of_planets'](pd, essential, accidental, 0.0, sect)
                    if r['Planet'] == 'Moon')
    assert '97' in [t['n'] for t in weakness['Testimonies']], weakness['Labels']


# --------------------------------------------------------------------------
# L2R-05: a behavioural pin for Venus "appearing" (L2-06's own pin cannot fail)
# --------------------------------------------------------------------------

def test_l2r_05_venus_appearing_is_pinned_by_behaviour(engine):
    """Gr. Intr. VII.2, 38-39: Venus at great latitude "is not called 'burned,'
    but rather she is called 'appearing' until her latitude is below 7°";
    38's own case is the 1' one (fn 40: "in the heart"). Abu Ma'shar's
    source only; Mercury and Sahl's source unchanged; the rays unchanged."""
    phase = engine['solar_phase']
    for lat in (7.0, 7.1, -7.1, 8.5):
        assert phase('Venus', 103.0, 100.0, 1.2, latitude=lat)[0] == 'Appearing', lat     # burned by longitude
        assert phase('Venus', 100.2, 100.0, 1.2, latitude=lat)[0] == 'Appearing', lat     # the heart by longitude
    assert phase('Venus', 103.0, 100.0, 1.2, latitude=6.9)[0] == 'Burned'
    assert phase('Venus', 100.2, 100.0, 1.2, latitude=6.9)[0] == 'Cazimi'
    assert phase('Venus', 103.0, 100.0, 1.2)[0] == 'Burned'                               # no latitude given
    assert phase('Venus', 110.0, 100.0, 1.2, latitude=8.5)[0] == 'Under the rays'
    assert phase('Venus', 100.2, 100.0, 1.2, source='Sahl', latitude=8.5)[0] == 'Cazimi'
    assert phase('Mercury', 103.0, 100.0, 1.3, latitude=7.5)[0] == 'Burned'
    jd, c = real_chart(engine, 2017, 3, 25, 12.0 - FLORENCE[1] / 15.0)
    pd = c['planetary_data']
    assert pd['Venus']['latitude'] > 8.0                                                   # premise: the chart
    acc = engine['evaluate_accidental_dignities'](pd, c['houses'], c['sect'], jd, armc=c['armc'],
                                                  obliquity=c['obliquity'], geo_lat=c['geo_lat'])
    assert acc['Venus']['SolarPhase'] == 'Appearing'
    assert not (acc['Venus']['Cazimi'] or acc['Venus']['Combust'] or acc['Venus']['UnderBeams'])


# --------------------------------------------------------------------------
# L2R-06: a pin for Strength 80 at a station (HP-03's own pin cannot fail on it)
# --------------------------------------------------------------------------

def _strength_80(engine, pd, c, jd):
    essential = engine['evaluate_essential_dignities'](pd, c['sect'])
    accidental = engine['evaluate_accidental_dignities'](pd, c['houses'], c['sect'], jd, armc=c['armc'],
                                                         obliquity=c['obliquity'], geo_lat=c['geo_lat'])
    saturn = next(r for r in engine['evaluate_strength_of_planets'](pd, essential, accidental, c['ascendant'],
                                                                    c['sect'], c['houses'])
                  if r['Planet'] == 'Saturn')
    return accidental['Saturn'], any(t['n'] == '80' for t in saturn['Testimonies'])


def test_l2r_06_a_stationary_planet_is_not_direct_in_course(engine):
    """Sahl, The Introduction Ch. 3, 80: "The third is that it is direct in
    course." The one station rule (HP-03; owner, 2026-10-04): within
    STATION_SPEED_TOLERANCE of rest a planet is stationary, neither direct nor
    retrograde. 2026-07-27 12:00 UT Florence: Saturn about -0.0011 a day."""
    jd, c = real_chart(engine, 2026, 7, 27, 12.0)
    pd = c['planetary_data']
    tol = engine['STATION_SPEED_TOLERANCE']
    assert abs(pd['Saturn']['speed_in_lon']) <= tol                                         # premise: the station
    acc, awarded = _strength_80(engine, pd, c, jd)
    assert acc['Stationary'] and not acc['Retrograde']
    assert awarded is False
    # Either side of the tolerance on the same chart: just outside, direct; just inside, still not.
    for speed, expected in ((tol + 0.0001, True), (tol, False), (-tol, False), (-(tol + 0.0001), False)):
        moved = {p: dict(v) for p, v in pd.items()}
        moved['Saturn']['speed_in_lon'] = speed
        assert _strength_80(engine, moved, c, jd)[1] is expected, speed


# --------------------------------------------------------------------------
# L2R-07: the Chart page prints "Appearing" and "Stationary" unqualified
# --------------------------------------------------------------------------

@pytest.mark.parametrize("date, local, planet, column, value, needles", [
    ("2017-03-25", time(12, 0), "Venus", "Solar phase", "Appearing", ("VII.2, 39",)),
    ("2026-07-27", time(14, 30), "Saturn", "Motion", "Stationary", ("0.003",)),
])
def test_l2r_07_the_chart_page_says_what_appearing_and_stationary_rest_on(date, local, planet, column, value, needles):
    at = make_app(date=date, page="chart")
    at.session_state["time_input_key"] = local                         # LMT, Florence
    at.run(timeout=300)
    assert_no_exception(at, f"{date} chart")
    positions = next(n.value for h, n in table_nodes(at) if h == "Planetary Positions")
    cell = positions[positions["Planet"] == planet].iloc[0][column]
    assert str(cell).startswith(value), cell                                                # premise: the value shows
    text = page_text(at)
    assert any(needle in text for needle in needles), [needle for needle in needles]
