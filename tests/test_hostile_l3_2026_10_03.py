"""Hostile pass, lane L3 (2026-10-03): the nativity -- dignities, domain
(hayz), Rhetorius's conditions, the prenatal lunation and its almuten, the
Lots, the eyesight degrees, the years ladder, the third-day Moon.

One test per finding, marked strict xfail so it fails the day the finding is
fixed; ordinary passing tests for the attacks that held. Corpus-reading tests
import corpus_file/CORPUS_DIR from tests/corpus_paths.py and skip only when
the corpus is absent.
"""
from __future__ import annotations

import re
from datetime import time

import pytest
import swisseph as swe

from conftest import FLORENCE, assert_no_exception, make_app, table_nodes
from corpus_paths import CORPUS_DIR, corpus_file
from skip_guard import needs_corpus

pytestmark = []

_corpus = needs_corpus()


def _jd(y, m, d, local_hours):
    """Florence local mean time -> UT Julian day in the PROLEPTIC GREGORIAN
    calendar (swe.julday's default). This is not how the harness's make_app or
    the app builds a chart: they read a date before 1582-10-15 as Julian. So an
    engine-level chart here is seven days from the page chart of the same label
    in the thirteenth century: (1240, 4, 1, 14.5) is Julian 1240-03-25 and
    (1240, 5, 23, 23.5) is JD UT 2174104.447927, Julian 1240-05-16. The
    engine-level verdicts below are asserted on these Gregorian days; the
    make_app tests read their dates as Julian."""
    return swe.julday(y, m, d, local_hours - FLORENCE[1] / 15.0)


def _chart(engine, y, m, d, local_hours):
    return engine['calculate_traditional_chart_jd'](_jd(y, m, d, local_hours), *FLORENCE)


def _syzygy(engine, chart, jd):
    return engine['calculate_prenatal_syzygy'](jd, FLORENCE[0], FLORENCE[1], chart['houses'])


def _syzygy_scores(engine, syz):
    r, W = syz['rulers'], engine['ESSENTIAL_DIGNITY_WEIGHTS']
    trip = r['triplicity_day'] if syz['sect_diurnal'] else r['triplicity_night']
    scores = {}
    for lord, pts in ((r['domicile'], W['domicile']), (r['exaltation'], W['exaltation']),
                      (trip, W['triplicity']), (r['term'], W['term']), (r['face'], W['face'])):
        if lord and lord != '-':
            scores[lord] = scores.get(lord, 0) + pts
    return scores


# --- L3-01: the syzygy's 5/4/3/2/1 almuten silently resolves a tie --------

TIE_DATES = {
    # date -> (lunation, degree printed, the tied lords); Florence 14:30 LMT
    "1240-04-01": ('Conjunctional', "11° Ari 50'", {'Mars', 'Sun'}),
    "1240-01-03": ('Conjunctional', "12° Cap 25'", {'Saturn', 'Mars'}),
    "1240-07-13": ('Preventional', "20° Can 19'", {'Moon', 'Jupiter'}),
    "1241-01-06": ('Preventional', "16° Cap 50'", {'Saturn', 'Mars', 'Venus'}),
    "1242-10-17": ('Preventional', "24° Lib 08'", {'Venus', 'Saturn'}),
}


@pytest.mark.parametrize("date", sorted(TIE_DATES))
def test_l3_01_background_these_lunations_really_tie(engine, date):
    """The facts behind L3-01 (passing): at these births the five lords of the
    syzygy degree tie for the top 5/4/3/2/1 score."""
    y, m, d = map(int, date.split('-'))
    jd = _jd(y, m, d, 14.5)
    syz = _syzygy(engine, _chart(engine, y, m, d, 14.5), jd)
    event, degree, tied = TIE_DATES[date]
    assert syz['event_type'] == event
    assert engine['get_degree_string'](syz['syzygy_longitude']) == degree
    scores = _syzygy_scores(engine, syz)
    top = max(scores.values())
    assert {p for p, s in scores.items() if s == top} == tied


def test_l3_01_syzygy_almuten_tie_is_not_a_single_name(engine):
    jd = _jd(1240, 4, 1, 14.5)
    syz = _syzygy(engine, _chart(engine, 1240, 4, 1, 14.5), jd)
    scores = _syzygy_scores(engine, syz)
    assert scores['Mars'] == scores['Sun'] == 5                     # the tie is real
    almuten = syz['almuten']
    # The right behaviour: either an UnresolvedResult, or both names, as the
    # chart victor already does ("Saturn / Jupiter", evaluate_victors).
    assert engine['is_unresolved'](almuten) or ({'Mars', 'Sun'} <= set(re.findall(r"[A-Z][a-z]+", str(almuten))))


def test_l3_01_victors_page_almuten_row_agrees_with_the_governor_row():
    at = make_app(date="1240-04-01", page="victors")
    at.run()
    assert_no_exception(at)
    rows = {}
    for _heading, node in table_nodes(at):
        df = node.value
        if 'Metric' in df.columns:
            for _, row in df.iterrows():
                rows[str(row['Metric'])] = str(row['Value'])
    governor = next(v for k, v in rows.items() if k.startswith('Governor of the syzygy degree'))
    almuten = next(v for k, v in rows.items() if k.startswith('Almuten by 5/4/3/2/1'))
    assert 'unresolved between Mars and Sun' in governor
    # the almuten row must not name one of a tied pair as if it had won
    assert not re.fullmatch(r"(Mars|Sun) \(Score: 5\)", almuten), almuten


def test_l3_01_contrast_the_chart_victor_does_flag_a_tie(engine):
    """Held: evaluate_victors joins tied winners with ' / ' and sets 'tied'."""
    import inspect
    src = inspect.getsource(engine['evaluate_victors'])
    assert "' / '.join(tied)" in src and "'tied': len(tied) > 1" in src


# --- L3-02: Masha'allah's domain rule can never call a feminine planet contrary ---

def _domain_cells(engine, jd, rule):
    chart = engine['calculate_traditional_chart_jd'](jd, *FLORENCE)
    # pin the reading the way the engine reads it: through this thread's _RUN
    _none = object()
    prior = getattr(engine['_RUN'], 'DOMAIN_RULE', _none)
    engine['set_readings'](DOMAIN_RULE=rule)
    try:
        acc = engine['evaluate_accidental_dignities'](chart['planetary_data'], chart['houses'], chart['sect'], jd=jd,
                                                       armc=chart['armc'], obliquity=chart['obliquity'],
                                                       geo_lat=FLORENCE[0])
    finally:
        if prior is _none:
            delattr(engine['_RUN'], 'DOMAIN_RULE')
        else:
            engine['set_readings'](DOMAIN_RULE=prior)
    return chart, acc


def _above(engine, chart, planet):
    d = chart['planetary_data'][planet]
    return engine['_sin_altitude'](d['longitude'], d['latitude'], d['distance'], chart['obliquity'],
                                   chart['armc'], FLORENCE[0]) > 0.0


def test_l3_02_mashaallah_feminine_planet_wrong_hemisphere_is_contrary(engine):
    jd = _jd(1240, 5, 23, 23.5)                       # nocturnal
    chart, acc = _domain_cells(engine, jd, engine['DOMAIN_RULE_OPTIONS'][1])
    assert chart['sect'] == 'Nocturnal'
    # 1.23, 17: "if it was feminine, by night it is above the earth" -- the Moon and Venus are below
    assert not _above(engine, chart, 'Moon') and not _above(engine, chart, 'Venus')
    for planet in ('Moon', 'Venus'):
        assert acc[planet]['Hayz'] is False
        assert acc[planet]['ContraryDomain'] is True, (planet, acc[planet]['ContraryDomain'])


def test_l3_02_background_male_planets_do_get_contrary_under_mashaallah(engine):
    """The same run marks the male planets contrary when hemisphere and sign
    both fail; the feminine planets follow their one condition, the
    hemisphere (1.23, 17), so each is contrary exactly when it is in the
    wrong one. (Until L3-02 was repaired this pinned the asymmetry itself:
    the Moon and Venus never contrary under the rule.)"""
    jd = _jd(1240, 10, 5, 2.0)
    chart, acc = _domain_cells(engine, jd, engine['DOMAIN_RULE_OPTIONS'][1])
    assert chart['sect'] == 'Nocturnal'
    assert acc['Jupiter']['ContraryDomain'] is True and acc['Saturn']['ContraryDomain'] is True
    for planet in ('Moon', 'Venus'):
        above = _above(engine, chart, planet)      # by night a feminine planet belongs above the earth
        assert acc[planet]['Hayz'] is above, (planet, above, acc[planet]['Hayz'])
        assert acc[planet]['ContraryDomain'] is (not above), (planet, above, acc[planet]['ContraryDomain'])


@_corpus
def test_l3_02_the_sentence_states_one_condition_for_a_feminine_planet():
    text = corpus_file('on_nativities.md').read_text()
    assert ('and if it was feminine, by night it is above the earth and by day under the earth), '
            'far from the rays') in text


# --- Abu Ma'shar's domain rule: the attack held -------------------------

@pytest.mark.parametrize("y,m,d,hours", [(1240, 5, 23, 14.5), (1240, 5, 23, 23.5), (1240, 10, 5, 2.0)])
def test_abu_mashar_domain_matches_the_ruling_for_every_planet(engine, y, m, d, hours):
    """VII.1, 37 read with VII.6, 13 (owner's ruling): hemisphere of the
    planet's own sect, sign of its own gender, Mars male and nocturnal."""
    jd = _jd(y, m, d, hours)
    chart, acc = _domain_cells(engine, jd, engine['DOMAIN_RULE_OPTIONS'][0])
    day = chart['sect'] == 'Diurnal'
    sun = chart['planetary_data']['Sun']['longitude']
    for planet in ('Sun', 'Moon', 'Mercury', 'Venus', 'Mars', 'Jupiter', 'Saturn'):
        own = engine['planet_sect_is_diurnal'](planet, chart['planetary_data'][planet]['longitude'], sun)
        if engine['is_unresolved'](own):
            continue
        above = _above(engine, chart, planet)
        sign = engine['get_zodiac_sign'](chart['planetary_data'][planet]['longitude'])
        hem_ok = (above if day else not above) if own else ((not above) if day else above)
        male = planet == 'Mars' or own
        gen_ok = (sign in engine['MASCULINE_SIGNS']) if male else (sign in engine['FEMININE_SIGNS'])
        assert bool(acc[planet]['Hayz']) == (hem_ok and gen_ok), planet
        assert bool(acc[planet]['ContraryDomain']) == ((not hem_ok) and (not gen_ok)), planet


# --- L3-03: the Rhetorius "aspected by malefics" reading text counts signs differently from its neighbours ---

def _pd(**lons):
    return {p: {'longitude': v, 'latitude': 0.0, 'distance': 1.0, 'speed_in_lon': s,
                'speed_in_lat': 0.0, 'speed_in_dist': 0.0} for p, (v, s) in lons.items()}


BASE = dict(Sun=(200.0, 1.0), Moon=(15.0, 13.0), Mercury=(210.0, 1.2), Venus=(230.0, 1.1),
            Jupiter=(300.0, 0.1), Mars=(250.0, 0.5))


def _malefic_rows(engine, saturn_lon):
    data = _pd(**BASE, Saturn=(saturn_lon, 0.03))
    rows = engine['evaluate_rhetorius_affliction'](data, 15.0, 'Diurnal')
    return [r['By'] for r in rows if r['Planet'] == 'Moon' and 'aspected by malefics' in r['Condition']]


def test_l3_03_background_the_code_tests_real_aspects(engine):
    """Held: the code counts 60/90/120/180 (two, three, four, six signs AHEAD)."""
    assert _malefic_rows(engine, 45.0) == ['Mars by whole-sign trine']            # 30 deg: no Saturn row
    assert 'Saturn by whole-sign sextile' in _malefic_rows(engine, 75.0)[0]       # 60 deg
    assert _malefic_rows(engine, 165.0) == ['Mars by whole-sign trine']           # 150 deg: no Saturn row
    assert 'Saturn by whole-sign opposition' in _malefic_rows(engine, 195.0)[0]   # 180 deg


ORDINALS = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'sixth': 6, 'seventh': 7,
            'eighth': 8, 'ninth': 9, 'tenth': 10, 'eleventh': 11, 'twelfth': 12}


def test_l3_03_rhetorius_reading_text_counts_signs_as_its_neighbours_do(engine):
    by_key = {c['key']: c for c in engine['RHETORIUS_AFFLICTION_CONDITIONS']}
    reading = by_key['aspected by malefics']['reading']
    named = {ORDINALS[w] for w in re.findall(r"\b(" + "|".join(ORDINALS) + r")\b", reading.split('from the planet')[0])}
    # the neighbours: "the tenth sign counted from another" is Aries from Cancer, inclusive
    assert 'tenth sign' in by_key['dominated']['reading']
    # inclusive counting of what the code tests: 2,3,4,6 signs ahead = the 3rd, 4th, 5th, 7th sign
    assert named == {3, 4, 5, 7}, named


@_corpus
def test_rhetorius_ch26_example_is_inclusive_counting():
    """Held: Ch. 26's Aries-from-Cancer example is the tenth sign inclusive, which the code's
    `ahead in (8, 9, 10)` reproduces."""
    text = corpus_file('rhetorius/rhetorius_holden_PROVISIONAL.md').read_text()
    assert 'Let Cancer be the ASC: then those [planets] in Aries are superior to one in Cancer' in text
    assert (0 - 3) % 12 == 9                      # Aries is 9 signs ahead of Cancer = the tenth sign counted from it


def test_rhetorius_dominated_row_reproduces_the_chapter_example(engine):
    data = _pd(**BASE, Saturn=(300.0, 0.03))
    data['Moon']['longitude'] = 100.0             # Cancer
    data['Mars']['longitude'] = 10.0              # Aries
    rows = engine['evaluate_rhetorius_affliction'](data, 100.0, 'Diurnal')
    dom = [r['By'] for r in rows if r['Planet'] == 'Moon' and 'dominated' in r['Condition']]
    assert dom and 'Mars in the tenth sign, a square (the first kind)' in dom[0]


# --- L3-04: the siblings Lots' editorial notes omit Dykes's stated position --------

def test_l3_04_siblings_rows_carry_dykes_notes_120_and_121(engine):
    by_id = {d['id']: d for d in engine['LOT_DEFINITIONS']}
    hermes, valens = by_id['siblings_hermes'], by_id['siblings_valens']
    assert 'revers' in (hermes['note'] + hermes['confidence']).lower()            # fn 120: "I would recommend reversing it by night"
    # 'revers' alone is met by the note's own "-- no reversal", so it held with fn 120
    # cut from the row (re-pass L3-R5). The sentence itself, Sahl I p. 451, fn 120:
    assert 'I would recommend reversing it by night, as Valens does.' in hermes['note'], hermes['note']
    assert 'disput' in (valens['note'] + valens['confidence']).lower() or 'Saturn-Jupiter' in valens['note']   # fn 121


@_corpus
def test_l3_04_background_the_footnotes_say_so():
    text = corpus_file('on_nativities.md').read_text()
    assert 'I would recommend reversing it by night, as Valens does.' in text
    assert 'Valens only uses the Saturn-Jupiter Lot' in text


# --- Lots: attacks that held --------------------------------------------

def test_lot_of_exaltation_night_formula_switches_both_ends(engine):
    """4.1, 6: by night from the MOON to HER exaltation, not the day arc reversed."""
    pdata = _pd(Sun=(100.0, 1.0), Moon=(200.0, 13.0), Mercury=(90.0, 1.0), Venus=(80.0, 1.0),
                Mars=(10.0, 0.5), Jupiter=(300.0, 0.1), Saturn=(250.0, 0.03))
    asc = 0.0
    day = engine['lot_by_id']('exaltation', pdata, asc, None, 'Diurnal')
    night = engine['lot_by_id']('exaltation', pdata, asc, None, 'Nocturnal')
    sun_exalt = engine['SIGN_ORDER'].index('Aries') * 30 + engine['EXALTATION_DEGREES']['Sun'] - 1
    moon_exalt = engine['SIGN_ORDER'].index('Taurus') * 30 + engine['EXALTATION_DEGREES']['Moon'] - 1
    assert day == pytest.approx((asc + sun_exalt - 100.0) % 360)
    assert night == pytest.approx((asc + moon_exalt - 200.0) % 360)


@pytest.mark.parametrize("lot_id,start,end,reverse", [
    ('fortune', 'Sun', 'Moon', True), ('spirit', 'Moon', 'Sun', True), ('basis', 'fortune', 'spirit', True),
    ('assets_jupsat', 'Jupiter', 'Saturn', True), ('siblings_hermes', 'Saturn', 'Jupiter', False),
    ('siblings_valens', 'Mercury', 'Jupiter', False), ('father', 'Sun', 'Saturn', True),
    ('mother', 'Venus', 'Moon', True), ('children_theophilus', 'Jupiter', 'Saturn', False),
    ('children_timing', 'Mars', 'Jupiter', False), ('marriage_men', 'Saturn', 'Venus', False),
    ('marriage_women', 'Venus', 'Saturn', False), ('chronic_illness', 'Saturn', 'Mars', True),
    ('slaves', 'Mercury', 'Moon', True), ('killer', 'lord1', 'Moon', True), ('travel', 'lord9', 'cusp9', False),
    ('work_action', 'Mercury', 'Mars', True), ('work_expedition', 'Saturn', 'Moon', False),
    ('friends', 'Moon', 'Mercury', True), ('desire', 'fortune', 'spirit', True), ('necessity', 'spirit', 'fortune', True),
    ('deception_men', 'Sun', 'Venus', False), ('deception_women', 'Moon', 'Mars', False),
    ('jupiter_prosperity', 'spirit', 'Jupiter', True), ('saturn_burdensome', 'Saturn', 'fortune', True),
    ('death', 'Moon', 'cusp8', False),
])
def test_lot_formulas_match_the_cited_sentences(engine, lot_id, start, end, reverse):
    """Each row's three points and its reversal as the corpus sentence states them
    (read 2026-10-03 against on_nativities.md and the Great Introduction)."""
    d = next(x for x in engine['LOT_DEFINITIONS'] if x['id'] == lot_id)
    assert (d['start'], d['end'], d['reverse_at_night']) == (start, end, reverse)


@_corpus
@pytest.mark.parametrize("phrase", [
    'count from the lord of the second to the second place',
    'count from Jupiter to Saturn by day, and by night the reverse of that',
    'taken by night and day from Mercury to Jupiter',
    'calculate by day from the Sun to Saturn and by night from Saturn to the Sun',
    'taken by day from Venus to the Moon (and by night the contrary)',
    'look in the Lot of men\'s deception by day and by night from the Sun to Venus',
    'taken from by day and by night from the Moon to Mars',
    'taken from Saturn to Mars by day, and by night the contrary of that',
    'taken from Mercury to the Moon by day, and by night the reverse of that',
    'taken from the lord of the Ascendant to the Moon by day (and by night the reverse)',
    'taken by night and day from the lord of the ninth to the ninth',
    'The Lot of work is taken from Mercury to Mars by day, and by night the contrary of that',
    'Calculate by day and night from Saturn to the Moon',
    'from the Moon to Mercury&gt; by day, and by night the contrary',
])
def test_lot_sentences_are_on_the_page(phrase):
    plain = re.sub(r"<sup>\d+</sup>", "", corpus_file('on_nativities.md').read_text())
    assert phrase in plain


def test_lot_arithmetic_projects_the_arc_from_the_third_point(engine):
    pdata = _pd(Sun=(100.0, 1.0), Moon=(130.0, 13.0), Mercury=(90.0, 1.0), Venus=(80.0, 1.0),
                Mars=(10.0, 0.5), Jupiter=(300.0, 0.1), Saturn=(250.0, 0.03))
    assert engine['lot_by_id']('fortune', pdata, 200.0, None, 'Diurnal') == pytest.approx(230.0)
    assert engine['lot_by_id']('fortune', pdata, 200.0, None, 'Nocturnal') == pytest.approx(170.0)
    pdata['Moon']['longitude'] = 100.0                      # 0 deg difference: the Lot is the Ascendant
    assert engine['lot_by_id']('fortune', pdata, 200.0, None, 'Diurnal') == pytest.approx(200.0)


def test_classical_and_topical_lots_agree_on_fortune_by_night(engine):
    chart = _chart(engine, 1240, 5, 23, 23.5)
    assert chart['sect'] == 'Nocturnal'
    classical = {r['Lot Name']: r['Position'] for r in engine['calculate_classical_lots'](
        chart['ascendant'], chart['planetary_data']['Sun']['longitude'], chart['planetary_data']['Moon']['longitude'], chart['sect'])}
    assert classical['Lot of Fortune'] == engine['get_degree_string'](chart['lot_of_fortune'])


# --- Prenatal syzygy: boundaries that held -------------------------------

def test_syzygy_type_boundary_just_before_and_after_a_full_moon(engine):
    chart = _chart(engine, 1240, 5, 23, 14.5)
    houses = chart['houses']
    # find the full Moon after 1240-05-23 by stepping
    jd = _jd(1240, 5, 23, 14.5)
    elong = lambda t: (swe.calc_ut(t, swe.MOON)[0][0] - swe.calc_ut(t, swe.SUN)[0][0]) % 360
    k0 = next(k for k in range(0, 40 * 24) if elong(jd + k / 24.0) < 180.0)      # start below the fullness
    hi = next(jd + k / 24.0 for k in range(k0, k0 + 40 * 24) if elong(jd + k / 24.0) >= 180.0)
    lo = hi - 1.0 / 24
    assert elong(lo) < 180.0 <= elong(hi)
    for _ in range(40):                                   # bisect to the exact full Moon
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if elong(mid) < 180.0 else (lo, mid)
    full = hi
    minute = 1.0 / 60 / 24
    before = engine['calculate_prenatal_syzygy'](full - minute, FLORENCE[0], FLORENCE[1], houses)
    after = engine['calculate_prenatal_syzygy'](full + minute, FLORENCE[0], FLORENCE[1], houses)
    assert before['event_type'] == 'Conjunctional' and after['event_type'] == 'Preventional'
    assert 13.0 < full - before['jd_syzygy'] < 16.5          # a minute before the fullness: the New Moon a fortnight back
    assert abs(after['jd_syzygy'] - full) < minute           # a minute after: that fullness


def test_syzygy_newton_search_lands_before_the_birth(engine):
    for date in ("1240-01-04", "1240-05-23", "1240-09-18", "1240-10-05"):
        y, m, d = map(int, date.split('-'))
        jd = _jd(y, m, d, 14.5)
        syz = _syzygy(engine, _chart(engine, y, m, d, 14.5), jd)
        assert syz['jd_syzygy'] <= jd
        assert jd - syz['jd_syzygy'] < 29.6
        s, mo = swe.calc_ut(syz['jd_syzygy'], swe.SUN)[0][0], swe.calc_ut(syz['jd_syzygy'], swe.MOON)[0][0]
        target = 0.0 if syz['event_type'] == 'Conjunctional' else 180.0
        assert abs(((mo - s - target + 180) % 360) - 180) < 1e-4


# --- Eyesight degrees: cell by cell against the page --------------------

@_corpus
def test_eyesight_sahl_rows_quote_the_page(engine):
    text = corpus_file('on_nativities.md').read_text().replace('&lt;', '<').replace('&gt;', '>')
    plain = re.sub(r"\s+", " ", re.sub(r"<sup>\d+</sup>", "", text).replace('*', ''))
    for row in engine['EYESIGHT_PLACES']:
        if row['source'] != engine['_EYE_SAHL']:
            continue
        quote = re.sub(r"\s+", " ", row['quote'].strip('"'))
        assert quote in plain, (row['sentence'], quote)


@_corpus
def test_eyesight_abu_bakr_rows_quote_the_page(engine):
    text = corpus_file('pn2/pn2_photographed.md').read_text()
    plain = re.sub(r"<sup>\d+</sup>", "", text).replace('*', '')
    for row in engine['EYESIGHT_PLACES']:
        if row['source'] != engine['_EYE_ABUBAKR']:
            continue
        assert row['quote'].strip('"') in plain, row['printed']


@_corpus
def test_eyesight_gr_intr_rows_quote_the_page(engine):
    text = corpus_file('gr_intr/abu_mashar_great_introduction.md').read_text()
    plain = re.sub(r"<sup>\d+</sup>", "", text)
    for row in engine['EYESIGHT_PLACES']:
        if row['source'] != engine['_EYE_ABU']:
            continue
        assert row['quote'].strip('"') in plain, row['printed']


def test_eyesight_ordinal_spans_follow_the_declared_convention(engine):
    """An ordinal 'the Nth degree' is (N-1).0 to N.0; a measured span is closed."""
    by_printed = {r['printed']: r for r in engine['EYESIGHT_PLACES']}
    assert (by_printed['Scorpio, the eighth, ninth and tenth degree']['lo'], by_printed['Scorpio, the eighth, ninth and tenth degree']['hi']) == (7.0, 10.0)
    assert (by_printed['Cancer, the ninth degree to the fifteenth']['lo'], by_printed['Cancer, the ninth degree to the fifteenth']['hi']) == (8.0, 15.0)
    assert (by_printed['Taurus from 6° to 10°']['lo'], by_printed['Taurus from 6° to 10°']['hi']) == (5.0, 10.0)
    libra = by_printed["Libra, from 27° 36' to 28°"]
    assert (libra['lo'], libra['hi'], libra['closed']) == (27.6, 28.0, True)
    pl = by_printed["from 13° 36' Taurus to 14° 30'"]
    assert (pl['lo'], pl['hi'], pl['closed']) == (13.6, 14.5, True)


# --- Years ladder: the JN Ch. 4 table cell by cell -----------------------

@_corpus
def test_years_table_matches_jn_ch4_on_the_page(engine):
    text = corpus_file('pn1/pn1_photographed.md').read_text()
    for planet, (greater, middle, lesser) in engine['JN_YEARS_TABLE'].items():
        def cell(v):
            return f"{int(v)} ½" if v != int(v) else str(int(v))
        pattern = r"\|\s*" + planet + r"\s*\|\s*" + re.escape(cell(greater)) + r"\s*\|\s*" + re.escape(cell(middle)) + r"\s*\|\s*" + re.escape(cell(lesser)) + r"\s*\|"
        assert re.search(pattern, text), planet


@_corpus
def test_years_ladder_sentences_are_verbatim(engine):
    text = re.sub(r"<sup>\d+</sup>", "", corpus_file('pn1/pn1_photographed.md').read_text()).replace('*', '')
    ladder = engine['JN_YEARS_LADDER']
    for _place, _cls, sentence in ladder['places']:
        assert sentence in text, sentence[:60]
    for _name, sentence in ladder['demotions']:
        assert sentence in text, sentence[:60]
    assert ladder['preface'] in text


# --- The third-day Moon: Albinus and the civil-day edge ------------------

def test_albinus_third_day_count_matches_the_engine_comment():
    jd = swe.julday(303, 3, 14, 21 + 53 / 60 + 17 / 3600, swe.JUL_CAL)
    moon = [swe.calc_ut(jd + d, swe.MOON)[0][0] for d in range(4)]
    mars_opp = (swe.calc_ut(jd + 2, swe.MARS)[0][0] + 180.0) % 360
    assert 104 < moon[0] < 105.5                 # 14 58' Cancer, Figure 34
    assert 119 < moon[1] < 120                   # 29 Cancer at +1 day
    assert 133 < moon[2] < 134.5 and abs(moon[2] - mars_opp) < 1.5   # 13 Leo on Mars's opposition ray at +2 days
    assert 148 < moon[3] < 149.5                 # 28 Leo at +3 days


def test_third_day_instant_lies_within_the_third_civil_day(engine):
    """Birth day counted as the first: 48 h after 23:59 is 23:59 of day 3; after 00:01, 00:01 of day 3."""
    assert engine['MOON_THIRD_DAY_DAYS'] == 2.0
    for hours in (23 + 59 / 60, 1 / 60):
        jd = _jd(1240, 5, 23, hours)
        third = engine['third_day_positions'](jd)['jd']
        day_of = lambda t: int(t + FLORENCE[1] / 360.0 + 0.5)           # local civil day number
        assert day_of(third) - day_of(jd) == 2


# --- Chronocrats: the day begins at sunrise --------------------------------

def test_day_lord_before_sunrise_is_the_previous_day_s(engine):
    # 1240-05-23 02:00 LMT Florence is Wednesday 23 May 1240 (Julian); before sunrise it belongs to Tuesday
    jd_pre = _jd(1240, 5, 23, 2.0)
    jd_noon = _jd(1240, 5, 23, 12.0)
    pre = engine['calculate_chronocrats'](jd_pre, FLORENCE[0], FLORENCE[1], 2.0, FLORENCE[1] / 15.0)
    noon = engine['calculate_chronocrats'](jd_noon, FLORENCE[0], FLORENCE[1], 12.0, FLORENCE[1] / 15.0)
    order = ['Moon', 'Mars', 'Mercury', 'Jupiter', 'Venus', 'Saturn', 'Sun']    # Monday..Sunday
    assert (order.index(noon['Day Lord']) - order.index(pre['Day Lord'])) % 7 == 1
    assert not pre['Approximate'] and not noon['Approximate']


# --- Mercury's sect by phase: IV.9, 8 -----------------------------------

def test_mercury_phase_sect_eastern_is_diurnal(engine):
    assert engine['mercury_phase_sect'](90.0, 100.0) is True        # rises before the Sun: eastern, diurnal
    assert engine['mercury_phase_sect'](110.0, 100.0) is False      # western, nocturnal
    assert engine['is_unresolved'](engine['mercury_phase_sect'](100.0, 100.0))


@_corpus
def test_iv9_8_sentence_is_on_the_page():
    text = corpus_file('gr_intr/abu_mashar_great_introduction.md').read_text()
    assert 'when he easternizes [the indication] is diurnal; but when he westernizes he is nocturnal' in text
