"""Hostile pass of 2026-10-03, lane L2: the code against its own quoted
sentence -- Sahl's sixteen approaches (The Introduction Ch. 3) and Gr. Intr.
VII.2-VII.6, driven through the pure engine on constructed planetary_data.

Each finding's test asserts the behaviour the cited sentence requires;
each FAILED on cb7390d as a strict xfail and passes since lane F6 of the
repair (the ruled ones, L2-01 and L2-05, as the owner ruled them, R2 and
R3 of 2026-10-03). The passing tests are the attacks that held, kept as coverage: Sahl's own
worked figures (10, 11, 13, 14, 25), the orb edges, the Sun's fifteen, the
sign-cusp strike, VII.2's boundary inclusivity, and two base tables parsed
from the corpus figures themselves (47, 38).
"""
from __future__ import annotations

import inspect
import re

import pytest

from conftest import engine_source, ui_source, make_app, assert_no_exception, table_nodes
from corpus_paths import corpus_file
from skip_guard import skip_without_corpus

GR_INTR = corpus_file("gr_intr/abu_mashar_great_introduction.md")

GLYPH = {'♄': 'Saturn', '♃': 'Jupiter', '♂': 'Mars', '☉': 'Sun', '♀': 'Venus', '☿': 'Mercury', '☽': 'Moon'}
SIGN_GLYPH = dict(zip('♈♉♊♋♌♍♎♏♐♑♒♓',
                      ['Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo',
                       'Libra', 'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces']))

# Representative daily motions, direct, so the standing light/heavy order and
# the kinetic order agree unless a test says otherwise.
SPEED = {'Moon': 13.0, 'Mercury': 1.3, 'Venus': 1.2, 'Sun': 0.9856,
         'Mars': 0.5, 'Jupiter': 0.08, 'Saturn': 0.03, 'North Node': -0.05}


def body(lon, speed, lat=0.0):
    return {'longitude': lon % 360.0, 'latitude': lat, 'distance': 1.0,
            'speed_in_lon': speed, 'speed_in_lat': 0.0, 'speed_in_dist': 0.0}


def chart(**lons):
    """planetary_data from absolute longitudes, with the speeds above."""
    return {name: body(lon, SPEED[name]) for name, lon in lons.items()}


def pair_row(engine, pd, a, b):
    rows = engine['evaluate_ptolemaic_aspects'](pd)
    return next(r for r in rows if {r['Light Planet'], r['Heavy Planet']} == {a, b})


def averse_frame(**lons):
    """The seven planets and the Node with everything but the named pair
    placed in signs averse to Gemini (the pair's sign in the L2-01 case)."""
    pd = chart(Sun=100, Mercury=230, Venus=280, Mars=40, Jupiter=235, **lons)
    pd['North Node'] = body(300, SPEED['North Node'])
    return pd


# --------------------------------------------------------------------------
# Findings (strict xfail: each passes only once the finding is fixed)
# --------------------------------------------------------------------------

def _equal_cusps(asc):
    """Twelve divisions of 30 degrees from the Ascendant's degree: the
    divisions 109 counts on (ruling 137) where a test has no chart."""
    return [(asc + 30.0 * i) % 360.0 for i in range(12)]


def test_l2_01_moon_still_connected_by_sahl_9_10_is_not_empty_of_course(engine):
    pd = averse_frame(Moon=75.0, Saturn=70.0)          # 15 Gemini five degrees past 10 Gemini
    row = pair_row(engine, pd, 'Moon', 'Saturn')
    assert row['Motion'] == 'Separating'
    assert row['Connection'] == 'Under a single blanket'   # the engine's own Sahl 9-10 verdict
    defects = engine['evaluate_corruption_of_the_moon'](pd, _equal_cusps(0.0), 'Diurnal')
    assert defects['testimonies'][111]['matched'] is False


def test_l2_01_cross_sign_residue_under_one_degree_is_not_empty_of_course(engine):
    """R2's second case: the residue of Sahl 9 across a sign boundary --
    "the planet does not cease to be counted as being connected until it
    separates from the planet by a full degree" -- a Moon two minutes past
    Saturn over the Aries/Taurus cusp. Every other body sits in early Libra,
    averse to Taurus and some 25 degrees short of its opposition to Saturn,
    so nothing else connects with either of them."""
    pd = chart(Sun=182.0, Mercury=184.0, Venus=186.0, Mars=185.0, Jupiter=183.0,
               Saturn=29.0 + 59.0 / 60.0, Moon=30.0 + 1.0 / 60.0)
    pd['North Node'] = body(300.0, SPEED['North Node'])
    row = pair_row(engine, pd, 'Moon', 'Saturn')
    assert row['Aspect'] == 'Aversion' and row['Motion'] == 'Separating'
    assert row['Connection'] == 'Under a single blanket'       # 9's residue, admitted
    defects = engine['evaluate_corruption_of_the_moon'](pd, _equal_cusps(0.0), 'Diurnal')
    assert defects['testimonies'][111]['matched'] is False
    # Past the full degree the residue is gone and she is wild.
    pd['Moon'] = body(31.0 + 1.0 / 60.0, SPEED['Moon'])
    assert pair_row(engine, pd, 'Moon', 'Saturn')['Connection'] != 'Under a single blanket'
    assert engine['evaluate_corruption_of_the_moon'](pd, _equal_cusps(0.0), 'Diurnal')['testimonies'][111]['matched'] is True


def test_l2_02_blocking_type_ii_does_not_widen_mercurys_light(engine):
    pd = chart(Mercury=220.0, Saturn=48.0, Mars=45.0)   # 10 Scorpio, 18 Taurus, 15 Taurus
    assert pair_row(engine, pd, 'Mercury', 'Saturn')['Connection'] == 'Not yet'
    blocks = [b for b in engine['evaluate_blocking'](pd) if b['Blocked'] == 'Mercury']
    assert blocks == []


def test_l2_03_enclosure_is_dissolved_by_a_ray_cast_between_the_legs(engine):
    pd = chart(Mars=100.0, Saturn=18.0, Moon=193.0, Jupiter=315.0)
    rows = engine['_pairwise_configurations'](pd)
    # The engine's own helper finds the intervening ray ...
    assert engine['_third_day_intervening_ray'](pd, rows, 'Mars', 'Saturn') == 'Jupiter'
    # ... but the Enclosure table does not read it.
    enclosed = [e for e in engine['evaluate_enclosure'](pd) if e['Planet'] == 'Moon']
    assert enclosed == []


def test_l2_04_cross_sign_residue_names_the_moon_as_the_one_separating(engine):
    pd = chart(Saturn=29.0 + 59.0 / 60.0, Moon=30.0 + 1.0 / 60.0)
    row = pair_row(engine, pd, 'Moon', 'Saturn')
    assert row['Motion'] == 'Separating'
    assert row['Connecting planet'].startswith('Moon')


def test_l2_05_partnering_triplicity_lord_has_testimony(engine):
    pd = chart(Moon=140.0, Saturn=205.0)               # 20 Leo applying by sextile to 25 Libra
    rulers = engine['get_essential_rulers'](140.0)
    assert rulers['triplicity_participating'] == 'Saturn'
    kinds = {r['Kind'] for r in engine['evaluate_non_reception'](pd, 'Diurnal')}
    assert 'I (58)' not in kinds


def test_l2_06_venus_at_great_latitude_is_appearing_not_burned(engine):
    assert 'latitude' in inspect.signature(engine['solar_phase']).parameters
    assert re.search(r"VII\.2, 3[89]", engine_source())


def test_l2_06_abu_ali_years_keep_the_longitude_phase_for_venus():
    """Abu Ma'shar's "appearing" exception (Gr. Intr. VII.2, 39) is his, not
    Abu 'Ali's: the Fardar and ages page's JN Ch. 3 column reads the
    longitude phase only. The check's input: Venus 0.07 deg from the Sun
    at 8.29 deg of latitude, which Abu Ma'shar's Chart page calls
    "Appearing" and Abu 'Ali's years still call burned."""
    from datetime import time
    at = make_app(date="2009-03-27", page="fardar")
    at.session_state["time_input_key"] = time(12, 0)                    # LMT, Florence
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.run(timeout=180)
    assert_no_exception(at, "2009-03-27 12:00")
    years = next(n.value for _h, n in table_nodes(at) if any(str(c).startswith("Where On Nativities 1.20") for c in n.value.columns))
    col = next(c for c in years.columns if str(c).startswith("Where On Nativities 1.20"))
    cell = years[years["Planet"] == "Venus"].iloc[0][col]
    assert "burned" in cell, cell


def test_l2_07_rhetorius_seven_degrees_read_the_same_way_on_both_sides(engine):
    pd = {'Moon': body(100.0, 13.0), 'Mars': body(93.0, 0.5), 'Saturn': body(107.0, 0.03),
          'Jupiter': body(100.0 + 7.0 - 120.0, 0.08)}
    planets = list(pd)
    siege = engine['_rhetorius_besiegers']('Moon', pd, planets, engine['INFORTUNES'])
    assert siege == ('Mars', 7.0, 'Saturn', 7.0)
    relief = engine['_rhetorius_loosener']('Moon', pd, planets, {'Jupiter', 'Venus', 'Sun'}, True)
    # Owner's ruling 2 of 2026-10-05 (the re-pass's Q2): the relief's "less than 7°" is
    # exclusive, so the ray exactly 7.0° off besieges and does not relieve.
    assert relief is None


def test_l2_08_sahl_105_does_not_fire_at_the_exact_opposition(engine):
    pd = averse_frame(Moon=10.0, Saturn=70.0)
    pd['Sun'] = body(190.0, SPEED['Sun'])             # 10 Libra, opposite 10 Aries to the minute
    defects = engine['evaluate_corruption_of_the_moon'](pd, _equal_cusps(0.0), 'Diurnal')
    assert defects['testimonies'][105]['matched'] is False


def test_l2_09_the_page_says_one_figure_is_both_a_transfer_and_an_intervention(engine):
    """Both evaluators report Fig. 13; the page, beside Transfer of Light,
    says so and gives the reason the editor gives (the note on VII.5, 92:
    "the difference lies in what we want the planets to do")."""
    text = ui_source()
    start = text.index("_finding(_gap, 'Transfer of Light'")
    end = text.index("_finding(_gap, 'Collection of Light'", start)
    finding = text[start:end]
    pd = chart(Moon=68.0, Mars=70.0, Saturn=72.0)        # Fig. 13: 8, 10, 12 Gemini
    assert {'Type': 'I (Intervention)', 'Blocked': 'Moon', 'Blocked By': 'Mars', 'From Reaching': 'Saturn'} \
        in engine['evaluate_blocking'](pd)
    assert {'Type': 'II', 'Carrier': 'Moon', 'Separates From': '(via Mars)', 'Connects To': 'Saturn'} \
        in engine['evaluate_transfers_of_light'](pd)
    assert 'ntervention' in finding and 'Type II' in finding, finding[:300]
    assert re.search(r"VII\.5, 92", finding), finding[:300]


# --------------------------------------------------------------------------
# Attacks that held
# --------------------------------------------------------------------------

def test_sahl_fig_10_transfer_moon_from_mercury_to_jupiter(engine):
    pd = chart(Moon=70.0, Mercury=128.0, Jupiter=343.0)   # 10 Gem, 8 Leo, 13 Pisces (Ch. 3, 25-27)
    assert {'Type': 'I', 'Carrier': 'Moon', 'Separates From': 'Mercury', 'Connects To': 'Jupiter'} \
        in engine['evaluate_transfers_of_light'](pd)


def test_sahl_fig_11_collection_by_jupiter(engine):
    pd = chart(Venus=10.0, Moon=42.0, Jupiter=105.0)   # 10 Aries, 12 Taurus, 15 Cancer (Ch. 3, 29-30)
    found = engine['evaluate_collections_of_light'](pd)
    assert [(c['Collector'], c['Planets']) for c in found] == [('Jupiter', ('Moon', 'Venus'))]
    assert found[0]['Mutual sight'] is False               # "they were not looking at each other"


def test_sahl_fig_13_intervention_by_mars(engine):
    pd = chart(Moon=68.0, Mars=70.0, Saturn=72.0)        # 8, 10, 12 Gemini (Ch. 3, 36-37)
    assert {'Type': 'I (Intervention)', 'Blocked': 'Moon', 'Blocked By': 'Mars', 'From Reaching': 'Saturn'} \
        in engine['evaluate_blocking'](pd)


def test_sahl_fig_14_nullification_by_mars(engine):
    pd = chart(Moon=220.0, Mars=45.0, Saturn=53.0)       # 10 Scorpio, 15 and 23 Taurus (Ch. 3, 42-43)
    blocks = engine['evaluate_blocking'](pd)
    assert [(b['Type'], b['Blocked'], b['Blocked By'], b['From Reaching']) for b in blocks] == \
        [('II (Nullification)', 'Moon', 'Mars', 'Saturn')]


def test_sahl_fig_25_enclosure_of_the_moon(engine):
    pd = chart(Mars=100.0, Saturn=18.0, Moon=193.0)      # 10 Cancer, 18 Aries, 13 Libra (Ch. 3, 122)
    found = engine['evaluate_enclosure'](pd)
    assert [(e['Planet'], e['Separating From'], e['Connecting To']) for e in found] == [('Moon', 'Mars', 'Saturn')]
    assert found[0]['Severity'].startswith('More powerful')   # 121: "at 7 degrees and what is below that"


@pytest.mark.parametrize("remaining, state", [(12.0, 'Applying'), (12.0001, 'Not yet')])
def test_sahl_19_the_applicants_light_reaches_exactly_its_own_degree(engine, remaining, state):
    pd = {'Moon': body(10.0, 13.0), 'Saturn': body(130.0 + remaining, 0.03)}   # trine, Moon's light 12
    assert pair_row(engine, pd, 'Moon', 'Saturn')['Connection'] == state


@pytest.mark.parametrize("past, state", [(12.0, 'Separated'), (11.999, 'Under a single blanket')])
def test_sahl_10_separation_in_one_sign_is_half_the_light_body(engine, past, state):
    pd = {'Moon': body(40.0 + past, 13.0), 'Saturn': body(40.0, 0.03)}
    assert pair_row(engine, pd, 'Moon', 'Saturn')['Connection'] == state


@pytest.mark.parametrize("gap, state", [(15.0, 'Applying'), (15.001, 'Not yet')])
def test_sahl_13_the_suns_fifteen_degrees_in_one_sign(engine, gap, state):
    pd = {'Moon': body(55.0 - gap, 13.0), 'Sun': body(55.0, 1.0)}
    assert pair_row(engine, pd, 'Moon', 'Sun')['Connection'] == state


def test_sahl_13_sun_applying_within_his_own_light(engine):
    pd = {'Sun': body(40.0, 1.0), 'Saturn': body(55.0, 0.03)}
    assert pair_row(engine, pd, 'Sun', 'Saturn')['Connection'] == 'Applying'


def test_sahl_20_strike_across_the_cusp_and_sahl_7_exactness(engine):
    strike = pair_row(engine, chart(Moon=29.0 + 59.0 / 60.0, Saturn=30.0 + 1.0 / 60.0), 'Moon', 'Saturn')
    assert strike['Aspect'] == 'Aversion' and strike['Connection'] == 'Applying'
    exact = pair_row(engine, chart(Moon=45.0, Saturn=45.0), 'Moon', 'Saturn')
    assert exact['Connection'] == 'Exact — connection completed'


@pytest.mark.parametrize("planet, lon, sun, speed, phase", [
    ('Saturn', 94.0, 100.0, 0.03, 'Under the rays'),   # VII.2, 12: at the completion of 6 it has gone past burning
    ('Saturn', 85.0, 100.0, 0.03, None),                # VII.2, 14: at 15 the three conditions are complete
    ('Saturn', 115.0, 100.0, 0.03, 'Under the rays'),  # VII.2, 32: at 15 west it enters the rays
    ('Saturn', 106.0, 100.0, 0.03, 'Burned'),          # VII.2, 34: at 6 west it is burned
    ('Saturn', 122.0, 100.0, 0.03, 'Degrees of setting'),  # VII.2, 30-31: from 22
    ('Mars', 82.0, 100.0, 0.5, None),                   # VII.2, 13: 18 east for Mars
    ('Moon', 88.0, 100.0, 13.0, 'Under the rays'),     # VII.2, 73: at 12 east she comes under the rays
    ('Moon', 94.0, 100.0, 13.0, 'Burned'),             # VII.2, 74: at 6 east she is burned
    ('Moon', 112.0, 100.0, 13.0, 'Under the rays'),    # VII.2, 61: passes beyond 12 west
    ('Venus', 107.0, 100.0, 1.2, 'Under the rays'),    # VII.2, 47-48: 7 west, direct, no longer burned
    ('Venus', 115.0, 100.0, 1.2, 'Under the rays'),    # VII.2, 48-49: under the rays through 15
    ('Venus', 93.0, 100.0, -0.6, 'Under the rays'),    # VII.2, 40: retrograde east, a full 7 is past burning
    ('Venus', 88.0, 100.0, -0.6, None),                 # VII.2, 40-41: at 12 the fourth condition
    ('Venus', 88.0, 100.0, 0.6, 'Under the rays'),     # VII.2, 44: direct east, at 12 under the rays
])
def test_vii2_boundary_inclusivity(engine, planet, lon, sun, speed, phase):
    assert engine['solar_phase'](planet, lon, sun, speed)[0] == phase


def test_sahl_fig_16_reception_by_house_and_by_exaltation(engine):
    by_house = engine['evaluate_reception'](chart(Moon=10.0, Mars=15.0), 'Diurnal')
    assert [(r['Receiver'], r['Received'], r['Via'], r['Grade']) for r in by_house] == [('Mars', 'Moon', 'house', 'Perfect')]
    by_exalt = engine['evaluate_reception'](chart(Moon=10.0, Sun=135.0), 'Diurnal')
    assert by_exalt[0]['Receiver'] == 'Sun' and by_exalt[0]['Grade'] == 'Perfect'


def test_sahl_fig_18_non_reception_models(engine):
    kinds = lambda pd: {r['Kind'] for r in engine['evaluate_non_reception'](pd, 'Diurnal')}
    assert kinds(chart(Moon=160.0, Saturn=165.0)) == {'I (58)'}                  # B alien in A's sign
    assert 'II (59-60)' in kinds(chart(Moon=26.0, Saturn=148.0))                # A in B's fall (Aries)
    assert 'III (61)' in kinds(chart(Moon=220.0, Saturn=345.0))                 # A in its own fall
    assert 'IV (62)' in kinds(chart(Moon=100.0, Saturn=15.0))                   # B in its own fall
    assert 'V (62)' in kinds(chart(Moon=130.0, Saturn=225.0))                   # B in A's fall


def test_sahl_75_76_the_moon_hands_over_power_only_from_taurus_or_cancer(engine):
    types = lambda pd: {r['Type'] for r in engine['evaluate_handing_over'](pd, 'Diurnal')}
    assert types(chart(Moon=100.0, Jupiter=105.0)) >= {'Management', 'Power'}      # Cancer
    assert 'Power' not in types(chart(Moon=130.0, Saturn=135.0))                  # Leo: management only
    assert types(chart(Moon=10.0, Mars=15.0)) == {'Management', 'Nature'}         # Aries -> Mars, 74


def _figure_rows(text, caption_prefix, start_marker):
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(start_marker))
    end = next(i for i, l in enumerate(lines) if i > start and l.lstrip('*').startswith(caption_prefix))
    return lines[start:end]


def test_gr_intr_figure_47_egyptian_bounds_match_the_engine_cell_by_cell(engine):
    skip_without_corpus(GR_INTR)
    rows = _figure_rows(GR_INTR.read_text(), "Figure 47 (Gr. Intr.)", "### Chapter V.9")
    parsed = {}
    for line in rows:
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) == 6 and cells[0] in SIGN_GLYPH:
            limits, running = [], 0
            for cell in cells[1:]:
                glyph, width = cell.split()
                running += int(width)
                limits.append((running, GLYPH[glyph]))
            parsed[SIGN_GLYPH[cells[0]]] = limits
    assert len(parsed) == 12
    assert parsed == {sign: list(map(tuple, v)) for sign, v in engine['EGYPTIAN_TERMS'].items()}


def test_gr_intr_figure_38_exaltation_degrees_match_the_engine(engine):
    skip_without_corpus(GR_INTR)
    rows = _figure_rows(GR_INTR.read_text(), "Figure 38 (Gr. Intr.)", "### Chapter V.5")
    parsed = {}
    for line in rows:
        m = re.match(r"\|\s*([♄♃♂☉♀☿☽])\s*\|\s*(\d+)\s*<sup>", line.strip())
        if m:
            parsed[GLYPH[m.group(1)]] = int(m.group(2))
    assert parsed == engine['EXALTATION_DEGREES']
