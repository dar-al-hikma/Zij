"""The Moon's seventh defect counts falling by the divisions with the five degrees (the owner's ruling 137).

Sahl, The Introduction Ch. 3, 109 (Sahl I p. 70): "The seventh is if she was
falling from the stakes or connecting with a planet falling from the stakes."
The text does not say how falling is counted. Ruling 137: for the Moon and for
the planet she connects with, by the nativity's own divisions with the five
degrees at the four stakes, through quadrant_strength_position, as Strength 83
and the Planetary Condition's 39 count it; the page says it is this app's
reading and cites Dykes's Figure 9 in Sahl I. Which planets count as connected
is not part of the ruling. Weakness 91 keeps whole-sign places.
"""
import re

import pytest

from conftest import assert_no_exception, find_table, make_app
from corpus_paths import corpus_file
from skip_guard import skip_without_corpus

# Chart B of the blind reading: 2000-01-01 14:30 UT, 58 N, 0 E. Its own
# divisions put the Ascendant at 1°48' Cancer, early in its sign, so whole
# sign and the divisions part company near the stakes.
CHART_B = (2451545.104167, 58.0, 0.0)

# Constructed divisions: opposite cusps 180 apart, each stake ten degrees
# into its sign (10 Cancer, 10 Libra, 10 Capricorn, 10 Aries), so the
# five degrees before a stake lie inside one sign and every distance below is
# exact in binary.
CUSPS = (100.0, 128.0, 158.0, 190.0, 222.0, 252.0, 280.0, 308.0, 338.0, 10.0, 42.0, 72.0)
STAKES = {0: ('12th', 'the Ascendant'), 3: ('3rd', 'the stake of the earth'),
          6: ('6th', 'the seventh'), 9: ('9th', 'the Midheaven')}

COUNT = 'by the divisions with the five degrees'
CITE = "(109; this app's reading, which the text does not say, after Sahl I Figure 9)"

NOTE_109 = (
    '**Falling (109).** "The seventh is if she was falling from the stakes or connecting with a planet falling '
    'from the stakes" (109). The text does not say how falling is counted here: in The Introduction Ch. 2, 35 '
    'Sahl names the falling places by sign and defines retreat by the same phrase (Ch. 3, 5), which '
    'Dykes\'s Figure 9 in Sahl I draws "understood dynamically". This app\'s reading counts it by the Alchabitius '
    'divisions of the nativity with the five degrees, as the Strength of the Planets and Planetary Condition '
    'tables count the stakes: "the planets will not fall from the stakes except after 5°" (On Nativities 1.22, 9). '
    'So the Moon, or a planet she connects with, falls only in the 12th, 3rd, 6th or 9th division, and only when '
    'it is more than five degrees before the degree of the stake that division ends at: the Ascendant, the stake '
    'of the earth, the seventh or the Midheaven. Within those five degrees it is still in the stake. The '
    'divisions, the five degrees counted in longitude, and exactly five degrees counted as within are this app\'s '
    'reading.')
LIST_ITEM = 'falling from the stakes or connecting with a planet that is, counted by the divisions with the five degrees'
OLD_LIST_ITEM = 'falling from the stakes or connecting with a planet that is;'


@pytest.fixture(scope='module')
def chart_b(engine):
    return engine['calculate_traditional_chart_jd'](*CHART_B)


def _pd(chart, **lons):
    pd = {name: dict(row) for name, row in chart['planetary_data'].items()}
    for name, lon in lons.items():
        pd[name]['longitude'] = lon % 360.0
    return pd


def _t109(engine, pd, cusps, sect='Diurnal'):
    return engine['evaluate_corruption_of_the_moon'](pd, list(cusps), sect)['testimonies'][109]


def _own(clauses):
    return [c for c in clauses if c.startswith('Falling from the stakes')]


def _via(clauses, planet):
    return [c for c in clauses if c.startswith(f'Connecting with {planet}, ')]


def _own_clause(division, stake):
    return (f'Falling from the stakes {COUNT}: the {division} division of the nativity, more than five degrees '
            f'before the degree of {stake}')


def _via_clause(planet, division, stake):
    return (f'Connecting with {planet}, itself falling from the stakes {COUNT}: the {division} division of the '
            f'nativity, more than five degrees before the degree of {stake}')


# --- 1. The Moon at the five degrees before each stake ---------------------

@pytest.mark.parametrize('index', sorted(STAKES))
@pytest.mark.parametrize('before, falls', [(4.5, False), (5.0, False), (5.5, True)])
def test_the_moon_at_the_five_degrees_before_each_stake(engine, chart_b, index, before, falls):
    """4.5 and exactly 5.0 degrees before a stake's degree she is in the stake;
    5.5 degrees before it she falls, and the clause names the division and the
    stake."""
    moon = CUSPS[index] - before
    clauses = _t109(engine, _pd(chart_b, Moon=moon), CUSPS)['clauses']
    division, stake = STAKES[index]
    assert _own(clauses) == ([_own_clause(division, stake)] if falls else []), clauses


# --- 2. The planet she connects with, the same way ------------------------

def _connected_frame(chart, jupiter):
    """Jupiter at the given longitude and the Moon 63 degrees behind him: a
    sextile by sign and by degree, the Moon applying, 3 degrees short."""
    return _pd(chart, Jupiter=jupiter, Moon=jupiter - 63.0)


@pytest.mark.parametrize('index', sorted(STAKES))
@pytest.mark.parametrize('before, falls', [(4.5, False), (5.0, False), (5.5, True)])
def test_the_connected_planet_at_the_five_degrees_before_each_stake(engine, chart_b, index, before, falls):
    jupiter = CUSPS[index] - before
    pd = _connected_frame(chart_b, jupiter)
    row = next(r for r in engine['_pairwise_configurations'](pd) if {r['p1'], r['p2']} == {'Moon', 'Jupiter'})
    assert row['aspect_name'] == 'Sextile' and engine['_is_connected'](row), row     # the premise
    t = _t109(engine, pd, CUSPS)
    assert _own(t['clauses']) == [], t                                                # she herself is not falling
    division, stake = STAKES[index]
    assert _via(t['clauses'], 'Jupiter') == ([_via_clause('Jupiter', division, stake)] if falls else []), t


# --- 3. Where whole sign and the divisions disagree ------------------------

def test_the_moon_in_the_twelfth_sign_within_five_degrees_of_the_ascendant_is_not_falling(engine, chart_b):
    """Moon 28 Gemini, the twelfth sign from the Ascendant (whole sign: falling),
    3.8 degrees before the Ascendant's degree (the divisions: in the stake)."""
    pd = _pd(chart_b, Moon=88.0)
    assert engine['get_wsh_house'](88.0, chart_b['ascendant']) == 12               # old rule: falling
    assert _own(_t109(engine, pd, chart_b['houses'])['clauses']) == []


def test_the_moon_in_the_eleventh_sign_in_the_twelfth_division_is_falling(engine, chart_b):
    """Moon 25 Taurus, the eleventh sign (whole sign: not falling), in the 12th
    division, far more than five degrees before the Ascendant's degree."""
    pd = _pd(chart_b, Moon=55.0)
    assert engine['get_wsh_house'](55.0, chart_b['ascendant']) == 11               # old rule: not falling
    assert _own(_t109(engine, pd, chart_b['houses'])['clauses']) == [_own_clause('12th', 'the Ascendant')]


OTHERS_AVERSE_TO_CANCER = dict(Sun=250.0, Mercury=255.0, Venus=305.0, Mars=65.0, Saturn=135.0)
OTHERS_AVERSE_TO_LEO = dict(Sun=280.0, Mercury=285.0, Venus=340.0, Mars=100.0, Saturn=170.0)


def test_a_connected_planet_falling_by_division_but_not_by_sign_meets_109(engine, chart_b):
    """Moon 22 Cancer (1st sign, 2nd division) applying by trine to Jupiter 25
    Scorpio, the fifth sign (whole sign: not falling) and the 6th division,
    more than five degrees before the seventh's degree. Every other planet is
    in a sign averse to Cancer."""
    pd = _pd(chart_b, Moon=112.0, Jupiter=235.0, **OTHERS_AVERSE_TO_CANCER)
    assert engine['get_wsh_house'](235.0, chart_b['ascendant']) == 5                # old rule: not falling
    t = _t109(engine, pd, chart_b['houses'])
    assert t['matched'] is True
    assert t['clauses'] == [_via_clause('Jupiter', '6th', 'the seventh')], t


def test_a_connected_planet_falling_by_sign_but_not_by_division_does_not_meet_109(engine, chart_b):
    """Moon 26 Leo (2nd sign, 4th division) applying by sextile to Jupiter 28
    Gemini, the twelfth sign (whole sign: falling), 3.8 degrees before the
    Ascendant's degree (the divisions: in the stake)."""
    pd = _pd(chart_b, Moon=146.0, Jupiter=88.0, **OTHERS_AVERSE_TO_LEO)
    assert engine['get_wsh_house'](88.0, chart_b['ascendant']) == 12                # old rule: falling
    row = next(r for r in engine['_pairwise_configurations'](pd) if {r['p1'], r['p2']} == {'Moon', 'Jupiter'})
    assert engine['_is_connected'](row), row                                        # the premise
    t = _t109(engine, pd, chart_b['houses'])
    assert t['matched'] is False and t['clauses'] == [], t


# --- 4. One count, the condition tables' -----------------------------------

def test_both_clauses_fall_exactly_where_the_condition_tables_say_falling(engine, chart_b):
    """720 longitudes round the circle, on chart B's own divisions: the Moon's
    clause, and the clause for a planet she connects with, appear exactly where
    quadrant_strength_position says 'falling'; and whole sign disagrees with it
    on both sides."""
    cusps = chart_b['houses']
    own_rule, whole_sign, via_checked = [], [], 0
    for step in range(720):
        lon = step * 0.5 + 0.25
        falling = engine['quadrant_strength_position'](lon, cusps)['strength'] == 'falling'
        own = bool(_own(_t109(engine, _pd(chart_b, Moon=lon), cusps)['clauses']))
        assert own is falling, lon
        frame = _connected_frame(chart_b, lon)
        row = next(r for r in engine['_pairwise_configurations'](frame) if {r['p1'], r['p2']} == {'Moon', 'Jupiter'})
        if row['aspect_name'] != 'Aversion' and engine['_is_connected'](row):
            # Only where she connects with him: 63 degrees is a sextile by
            # sign except when he is in his sign's first three degrees.
            via = bool(_via(_t109(engine, frame, cusps)['clauses'], 'Jupiter'))
            assert via is falling, lon
            via_checked += 1
        own_rule.append(falling)
        whole_sign.append(engine['get_wsh_house'](lon, chart_b['ascendant']) in engine['CADENT_HOUSES'])
    assert any(own_rule) and not all(own_rule)
    assert via_checked >= 600, via_checked
    pairs = set(zip(own_rule, whole_sign))
    assert (True, False) in pairs and (False, True) in pairs


def test_weakness_91_still_counts_whole_sign_places(engine, chart_b):
    """Ruling 137 leaves 91 whole sign: Saturn 28 Gemini, the twelfth sign,
    3.8 degrees before the Ascendant's degree, is still falling and averse."""
    pd = _pd(chart_b, Saturn=88.0)
    ess = engine['evaluate_essential_dignities'](pd, chart_b['sect'])
    acc = engine['evaluate_accidental_dignities'](pd, chart_b['houses'], chart_b['sect'])
    rows = engine['evaluate_weakness_of_planets'](pd, ess, acc, chart_b['ascendant'], chart_b['sect'])
    saturn = next(r for r in rows if r['Planet'] == 'Saturn')
    assert 'Falling from the stakes, averse to the Ascendant (91)' in saturn['Labels'], saturn


# --- 5. The page and the export ---------------------------------------------

DEPTHS = ('Course text', 'Course text and supplement')
# Florence, 14:30 local: 1240-09-18 the Moon falls (and Jupiter, whom she
# connects with); 1240-06-18 only Saturn, whom she connects with; 1240-05-23
# neither (under whole sign the Moon and the Sun had fallen there).
CHARTS = {
    '1240-09-18': [_own_clause('9th', 'the Midheaven') + ' ' + CITE,
                   _via_clause('Jupiter', '3rd', 'the stake of the earth') + ' ' + CITE],
    '1240-06-18': [_via_clause('Saturn', '9th', 'the Midheaven') + ' ' + CITE],
    '1240-05-23': [],
}


def _note_texts(at):
    out = []
    for kind in ('markdown', 'caption'):
        out.extend(node.value for node in getattr(at.main, kind))
    return out


@pytest.mark.parametrize('date', sorted(CHARTS))
@pytest.mark.parametrize('depth', DEPTHS)
def test_the_page_and_the_export_say_the_rule(depth, date):
    at = make_app(date=date, page='configurations')
    at.session_state['_reading_depth'] = depth
    at.run(timeout=300)
    assert_no_exception(at, f'configurations {date} {depth}')
    texts = _note_texts(at)
    assert any(NOTE_109 in t for t in texts), 'the 109 note is not on the page'
    assert any(LIST_ITEM in t for t in texts) and not any(OLD_LIST_ITEM in t for t in texts)
    (entry,) = at.session_state['_analysis_export']['results']['Configurations']['Corruption of the Moon']
    defects = entry['rows'][0]['Defects'] if entry['rows'] else ''
    found = re.findall(r'(?:Falling from the stakes|Connecting with \w+, itself falling from the stakes)[^)]*\)',
                       defects)
    assert found == CHARTS[date], defects
    if CHARTS[date]:
        frame = find_table(at, 'Corruption of the Moon').value
        assert frame['Defects'].iloc[0] == defects
    else:
        assert 'falling from the stakes' not in defects.lower()


def test_two_settled_clauses_of_109_print_one_space_before_the_count():
    """The settled list's clause count, on a chart where 109 is met twice
    (1240-09-18: the Moon and Jupiter), as the old pin had it on 1240-05-23.
    Her 18 deg 29' Libra is in the 19th degree of Libra, inside Gr. Intr.
    VII.6, 40's band read in ordinals, so 110 is met as well: three clauses,
    two testimonies."""
    at = make_app(date='1240-09-18', page='configurations')
    at.run(timeout=300)
    assert_no_exception(at, 'configurations 1240-09-18')
    (row,) = at.session_state['_analysis_export']['results']['Configurations']['Corruption of the Moon'][0]['rows']
    assert row['Defects'].endswith(' [3 clauses across 2 of the ten testimonies]'), row
    assert '  ' not in row['Defects'], row


# --- 6. The quoted words are in the sentences cited --------------------------

@pytest.fixture(scope='module')
def corpus():
    paths = {name: corpus_file(name) for name in ('sahl_introduction_ch3.md', 'on_nativities.md')}
    skip_without_corpus(*paths.values())
    return {name: p.read_text(encoding='utf-8') for name, p in paths.items()}


def test_the_notes_quotations_are_in_their_sentences(corpus):
    """The note quotes 109, Figure 9's caption and On Nativities 1.22, 9, and
    nothing else."""
    quoted = re.findall(r'"([^"]+)"', NOTE_109)
    assert quoted == ['The seventh is if she was falling from the stakes or connecting with a planet falling from '
                      'the stakes', 'understood dynamically',
                      'the planets will not fall from the stakes except after 5°']
    ch3 = corpus['sahl_introduction_ch3.md'].splitlines()
    sentence = next(line for line in ch3 if line.startswith('109 '))
    assert re.sub(r'<sup>\d+</sup>', '', sentence) == '109 ' + quoted[0] + '.'
    figure = next(line for line in ch3 if line.startswith('Figure 9 (Sahl I):'))
    assert figure.endswith(quoted[1])
    retreat = next(line for line in ch3 if line.startswith('5 And [2] **retreat**'))
    assert 'falling from the stakes' in retreat
    nine = next(line for line in corpus['on_nativities.md'].splitlines()
                if line.startswith('9 And') and 'will not fall from the stakes' in line)
    assert quoted[2] in nine
