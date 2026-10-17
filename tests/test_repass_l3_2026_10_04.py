"""Re-pass of lane L3 (2026-10-04), at the development repository's main,
428e05e: the nativity -- sect and domain, Rhetorius, the syzygy, the Lots, the victor.

Strict xfails assert the RIGHT behaviour for defects found beside the
repairs (F3, F7, F8 part A); they fail today and turn green the day the
defect is fixed. Ordinary passing tests pin attacks that held where no
lasting test covered them. Corpus-reading tests import corpus_file /
CORPUS_DIR from tests/corpus_paths.py and skip only when the corpus is
absent.
"""
from __future__ import annotations

import copy

import pytest
import swisseph as swe

from conftest import FLORENCE
from corpus_paths import CORPUS_DIR, corpus_file
from skip_guard import needs_corpus

_corpus = needs_corpus()


def _jd(y, m, d, local_hours):
    """Florence local mean time -> UT Julian day in the PROLEPTIC GREGORIAN
    calendar (swe.julday's default). The app reads a date before 1582-10-15
    as Julian, so these engine-level charts are seven days from the page
    chart of the same label in the thirteenth century: (1240, 5, 23, 23.5) is
    JD UT 2174104.447927, Julian 1240-05-16. The page tests below name
    Julian dates."""
    return swe.julday(y, m, d, local_hours - FLORENCE[1] / 15.0)


def _chart(engine, jd):
    return engine['calculate_traditional_chart_jd'](jd, *FLORENCE)


def _accidental(engine, chart, planetary_data, jd, rule):
    """evaluate_accidental_dignities under one domain rule, pinned on this
    thread's _RUN and restored after; returns the result or the exception."""
    _none = object()
    prior = getattr(engine['_RUN'], 'DOMAIN_RULE', _none)
    engine['set_readings'](DOMAIN_RULE=rule)
    try:
        return engine['evaluate_accidental_dignities'](
            planetary_data, chart['houses'], chart['sect'], jd=jd, armc=chart['armc'],
            obliquity=chart['obliquity'], geo_lat=FLORENCE[0])
    except Exception as exc:          # returned, so the test fails at its own assertion
        return exc
    finally:
        if prior is _none:
            delattr(engine['_RUN'], 'DOMAIN_RULE')
        else:
            engine['set_readings'](DOMAIN_RULE=prior)


def _mercury_on_the_sun(chart):
    data = copy.deepcopy(chart['planetary_data'])
    data['Mercury']['longitude'] = data['Sun']['longitude']
    return data


def _above(engine, chart, data, planet):
    d = data[planet]
    return engine['_sin_altitude'](d['longitude'], d['latitude'], d['distance'], chart['obliquity'],
                                   chart['armc'], FLORENCE[0]) > 0.0


# --- L3-R1: Masha'allah's rule, Mercury at the exact conjunction, raises ------------
#
# On Nativities 1.23, 17 names male and feminine planets; the page reads Mercury
# by his phase, which is unassigned at the Sun's own degree (mercury_phase_sect).
# The engine evaluates both readings and keeps what they share. Under this rule
# (since F7's repair of L3-02) the two can agree on Hayz (False) and differ on the
# contrary -- the male reading "neither", the feminine one "contrary" -- and the
# evaluator then takes the truth value of the unresolved contrary
# (`elif contrary_domain:`) and raises TypeError. Before F7 it returned values.

CONJUNCTION_CASES = [
    # (date, Florence LMT hours, chart sect, the Sun's sign): by night in a male sign,
    # by day in a female sign -- the two cells where the readings share Hayz only.
    ((1240, 5, 23), 23.5, 'Nocturnal', 'Gemini'),      # JD UT 2174104.447927
    ((1240, 8, 23), 14.5, 'Diurnal', 'Virgo'),         # JD UT 2174196.072927
]


@pytest.mark.parametrize("ymd,hours,sect,sign", CONJUNCTION_CASES)
def test_l3_r1_mercury_at_the_exact_conjunction_under_mashaallah_is_unresolved_not_an_exception(
        engine, ymd, hours, sect, sign):
    jd = _jd(*ymd, hours)
    chart = _chart(engine, jd)
    data = _mercury_on_the_sun(chart)
    assert chart['sect'] == sect and engine['get_zodiac_sign'](data['Sun']['longitude']) == sign
    assert engine['is_unresolved'](engine['mercury_phase_sect'](data['Mercury']['longitude'],
                                                                data['Sun']['longitude']))
    acc = _accidental(engine, chart, data, jd, engine['DOMAIN_RULE_OPTIONS'][1])
    # The finding: the evaluator must return, not raise.
    assert not isinstance(acc, Exception), f"evaluate_accidental_dignities raised {acc!r}"
    mercury = acc['Mercury']
    assert mercury['Hayz'] is False                       # both readings agree: not in its domain
    assert engine['is_unresolved'](mercury['ContraryDomain'])
    description = engine['domain_description'](mercury)
    assert engine['is_unresolved'](description)
    assert dict(description.alternatives) == {
        'if Mercury is diurnal': 'neither in nor contrary to its domain',
        'if Mercury is nocturnal': 'contrary to its domain',
    }


@pytest.mark.parametrize("ymd,hours,sect,sign", CONJUNCTION_CASES)
def test_l3_r1_background_abu_mashars_rule_returns_on_the_same_inputs(engine, ymd, hours, sect, sign):
    """Held: under Abu Ma'shar's rule the two readings are complementary, so
    whenever they share Hayz they share the contrary as well."""
    jd = _jd(*ymd, hours)
    chart = _chart(engine, jd)
    acc = _accidental(engine, chart, _mercury_on_the_sun(chart), jd, engine['DOMAIN_RULE_OPTIONS'][0])
    assert not isinstance(acc, Exception), acc
    mercury = acc['Mercury']
    # complementary readings: the two cells are open together or settled together
    assert engine['is_unresolved'](mercury['Hayz']) == engine['is_unresolved'](mercury['ContraryDomain'])


# --- L3-R2: the unresolved cell names Abu Ma'shar's locators under Masha'allah's rule ---

def test_l3_r2_mercurys_unresolved_domain_under_mashaallah_cites_the_rule_in_force(engine):
    jd = _jd(1240, 5, 23, 14.5)                  # JD UT 2174104.072927; diurnal, the Sun in Gemini: the readings differ on Hayz
    chart = _chart(engine, jd)
    acc = _accidental(engine, chart, _mercury_on_the_sun(chart), jd, engine['DOMAIN_RULE_OPTIONS'][1])
    assert not isinstance(acc, Exception), acc
    mercury = acc['Mercury']
    sources = [mercury['Hayz'].source, mercury['ContraryDomain'].source,
               engine['domain_description'](mercury).source]
    assert len(sources) == 3, sources
    for source in sources:
        assert '1.23, 17' in source and 'VII.1, 37' not in source, source


# --- L3-02: the four cells of Masha'allah's feminine arm (passing coverage) ---------
#
# F7 check finding 7: no lasting test pinned a feminine planet above the earth by
# night, or the day arm. An oracle from the sentence alone, over a fixed set of
# Florence charts, with every cell reached.

def _mashaallah_oracle(engine, chart, data, planet, day):
    sun = data['Sun']['longitude']
    if planet == 'Mercury':
        male = engine['mercury_phase_sect'](data['Mercury']['longitude'], sun)
        if engine['is_unresolved'](male):
            return None
    else:
        male = planet in ('Sun', 'Jupiter', 'Saturn', 'Mars')
    above = day if planet == "Sun" else _above(engine, chart, data, planet)
    if male:
        sign = engine['get_zodiac_sign'](data[planet]['longitude'])
        hem = above if day else not above
        gen = (sign in engine['MASCULINE_SIGNS']) if day else (sign in engine['FEMININE_SIGNS'])
        return (hem and gen, (not hem) and (not gen)), above
    hem = (not above) if day else above          # 1.23, 17: "by night ... above the earth and by day under the earth"
    return (hem, not hem), above


def test_l3_02_mashaallah_domain_matches_the_sentence_in_every_cell(engine):
    seen = set()
    for day_of_year in range(1, 361, 5):
        for hours in (5.0, 19.5):           # twilight hours reach Mercury and Venus on both sides
            jd = swe.julday(1240, 1, 1, hours - FLORENCE[1] / 15.0) + (day_of_year - 1)
            chart = _chart(engine, jd)
            data = chart['planetary_data']
            acc = _accidental(engine, chart, data, jd, engine['DOMAIN_RULE_OPTIONS'][1])
            assert not isinstance(acc, Exception), acc
            day = chart['sect'] == 'Diurnal'
            for planet in ('Sun', 'Moon', 'Mercury', 'Venus', 'Mars', 'Jupiter', 'Saturn'):
                oracle = _mashaallah_oracle(engine, chart, data, planet, day)
                if oracle is None:
                    continue
                want, above = oracle
                assert (acc[planet]['Hayz'], acc[planet]['ContraryDomain']) == want, (jd, planet)
                if planet in ('Moon', 'Venus', 'Mercury'):
                    seen.add((planet, day, above))
    assert seen == {(p, d, a) for p in ('Moon', 'Venus', 'Mercury') for d in (True, False) for a in (True, False)}, seen


@_corpus
def test_mercurys_gender_by_phase_is_sahls_own_sentence():
    """Held, and the closer witness for the F7-8 note: Sahl, On Questions Ch. 5, 26."""
    text = corpus_file('sahl_on_questions.md').read_text()
    assert ('if Mercury<sup>51</sup> was eastern (that is, arising before the Sun), it will be male; and if he was '
            'western (that is, arising after the Sun), it will be female.') in text


# --- L3-R4: 2.5, 3 graded without 2.5, 2's "casting rays", undeclared -------------
#
# On Nativities 2.5, 2: "If you found one of the two planets in square or sextile
# to its companion, and they were both in their exaltations or their houses ...,
# and each one of the two was casting rays upon its companion, then that is a
# strong right-sidedness. 3 And if they were not in their houses nor
# exaltations, but they were both of the sect of the day or the sect of the
# night, then that is also called right-sidedness (though it is below [the first
# version])." 3 replaces 2's dignity clause; whether the rest of 2 (the square or
# sextile, the rays) carries over the sentence leaves to the reader. The engine
# carries the square or sextile over and drops the rays, and the page states 3
# as "not in their houses or exaltations but both of one sect" -- the reading
# is nowhere said. Either the grade needs the rays, or the page says it does not.
# Ruled (owner, 2026-10-05, ruling 15 on the re-pass): 2.5, 3 requires 2.5, 2's
# configuration whole, the rays read by the same connection rule as 2's; the
# test asserts the ruled grade (the ruling lets it change that far): absent.

def test_l3_r4_a_by_sect_grade_without_rays_is_absent():
    from conftest import assert_no_exception, make_app, table_nodes
    at = make_app(date="1239-12-25", page="configurations")       # Julian; JD UT 2173961.072926944
    at.run(timeout=300)
    assert_no_exception(at)
    rows = []
    for heading, node in table_nodes(at):
        if heading.startswith('Right-sidedness'):
            rows.extend(node.value.to_dict('records'))
    mars_moon = next(r for r in rows if r['Pair'] == 'Mars and Moon')
    assert mars_moon['Aspect (whole sign)'] == 'sextile' and mars_moon['One sect'] == 'yes'
    without_rays = [r['Pair'] for r in rows
                    if str(r['Grade']).startswith('right-sidedness by sect') and r['Casting rays on each other'] == 'no']
    # Ruling 15: a pair of one sect that does not cast rays is not right-sided by 2.5, 3.
    assert mars_moon['Casting rays on each other'] == 'no' and mars_moon['Grade'] == '-', mars_moon
    assert without_rays == [], without_rays


# --- L3-R5: the L3-04 pin cannot fail for its Hermes half (passing pin) -------------
#
# test_l3_04_siblings_rows_carry_dykes_notes_120_and_121 asserts 'revers' in the
# Hermes row's note; the note's own "-- no reversal" (there since before the
# repair) satisfies it, so the strict xfail failed on its Valens half alone, and
# removing fn 120's sentence today leaves it green. This pins the sentence.

@_corpus
def test_l3_r5_the_hermes_siblings_row_quotes_dykes_note_120(engine):
    fn120 = 'I would recommend reversing it by night, as Valens does.'
    assert fn120 in corpus_file('on_nativities.md').read_text()          # the page's words (Sahl I p. 451)
    hermes = {d['id']: d for d in engine['LOT_DEFINITIONS']}['siblings_hermes']
    assert fn120 in hermes['note'], hermes['note']
    assert hermes['reverse_at_night'] is False and 'keeps the order Sahl states' in hermes['note']


def test_l3_r5_the_pass_l3_04_pin_fails_when_note_120_leaves_the_hermes_row(engine):
    import test_hostile_l3_2026_10_03 as pass_l3
    fn120 = 'I would recommend reversing it by night, as Valens does.'
    mutated = dict(engine)
    definitions = copy.deepcopy(engine['LOT_DEFINITIONS'])
    hermes = next(d for d in definitions if d['id'] == 'siblings_hermes')
    assert fn120 in hermes['note']
    hermes['note'] = hermes['note'].replace(f'"{fn120}"', '').replace(fn120, '')
    mutated['LOT_DEFINITIONS'] = definitions
    # The finding: with fn 120 gone the pass's pin must go red.
    with pytest.raises(AssertionError):
        pass_l3.test_l3_04_siblings_rows_carry_dykes_notes_120_and_121(mutated)


# --- L3-R3 and L3-R6: two comments that say the opposite of what holds -------------

def _source(name):
    from pathlib import Path
    root = Path(__file__).resolve().parent
    return (root.parent / name if name.endswith('engine.py') else root / name).read_text()


def test_l3_r3_the_domain_block_does_not_claim_the_chart_sect_must_match():
    from conftest import engine_source
    src = engine_source()                             # every engine module
    assert "All three must hold: the planet's own sect matches the chart's" not in src


def test_l3_r6_the_pass_l3_jd_helper_says_which_calendar_it_builds():
    src = _source('test_hostile_l3_2026_10_03.py')
    helper = src[src.index('def _jd('):src.index('def _chart(')]
    assert 'JUL_CAL' in helper or 'Gregorian' in helper, helper
