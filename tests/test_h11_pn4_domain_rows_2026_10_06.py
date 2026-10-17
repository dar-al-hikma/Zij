"""Lane H11: PN IV's I.7 and II.3 domain rows read plain sect (ruling 37, FQ-1).

PN IV I.7, 17 (PN IV p. 164): "And those of them in their own domain or not
in their domain (of the diurnal [planets] and the nocturnal ones)."
PN IV II.3, 5 (PN IV p. 187): "... in its own domain (of the condition of day
or night) ...", with Dykes's fn 46: "This should probably be understood as
"sect," so that it is simply of the sect of the chart"; II.3, 6: "or its
being in the contrary of its domain", fn 48: "Again, this should probably be
understood as "sect.""

The owner's ruling 37 (2026-10-06, on the blind reading FQ1): those two rows
read plain sect -- a planet of the chart's sect is in its own domain, one of
the other sect is in the contrary -- and stop following the app's Domain
switch, whose help says the PN IV rows are not under it. Each chart is read
by its own sect (the root by the root's, the revolution by the
revolution's). Mercury's sect is his sect by phase (Gr. Intr. IV.9, 8), left
open at the Sun's exact degree as everywhere else.

The charts are the reading's own: Chart M (Mars at opposition, at night),
birth 0 of its seeded sample (the Sun lord of the year at night) and Chart S
(sample birth 6: a diurnal chart whose Sun's centre is just below the
horizon).
"""
import ast
import re
from datetime import datetime
from pathlib import Path
import random

import pytest

from conftest import assert_no_exception, make_app

ROOT = Path(__file__).resolve().parents[1]
RULES = ("Abu Ma'shar", "Masha'allah")
IN_SHORT, CONTRARY = 'in its own domain', 'contrary to its domain'
IN_LONG = 'in its own domain (hayz)'


@pytest.fixture(autouse=True)
def isolated_readings(engine):
    run = engine['_RUN']
    saved = dict(run.__dict__)
    run.__dict__.clear()
    yield
    run.__dict__.clear()
    run.__dict__.update(saved)


def _domain_row(ii3):
    rows = [r for r in ii3['lord_rows'] if r['Factor'].startswith('In its own domain')]
    assert len(rows) == 1, [r['Factor'] for r in ii3['lord_rows']]
    return rows[0]


def _cells(engine, rule, root, rev, year, jd_rev):
    """Every PN IV domain cell under one setting of the Domain switch."""
    engine['set_readings'](DOMAIN_RULE=rule)
    i7 = engine['pn4_i7_planets'](root, rev)
    ii3 = engine['pn4_ii3_examination'](root, rev, year, jd_rev)
    out = {(r['Planet'], r['Chart']): r['Domain (17)'] for r in i7}
    row = _domain_row(ii3)
    out[('lord', 'root')] = row['Root']
    out[('lord', 'revolution')] = row['Revolution']
    return out, row


def _plain_sect(engine, chart, planet, long_form=False):
    """The cell plain sect gives, computed here from the planet's own sect
    and the chart's, independently of the builders."""
    data = chart['planetary_data']
    own = engine['planet_sect_is_diurnal'](planet, data[planet]['longitude'], data['Sun']['longitude'])
    if engine['is_unresolved'](own):
        return own
    in_value = IN_LONG if long_form else IN_SHORT
    return in_value if own == (chart['sect'] == 'Diurnal') else CONTRARY


def _chart_m(engine):
    c = engine['calculate_traditional_chart'](datetime(2020, 10, 13, 23, 0), 51.5, -0.13)
    year = engine['pn4_sign_of_the_year'](c['ascendant'], 8)
    assert (c['sect'], year['sign'], year['lord']) == ('Nocturnal', 'Aries', 'Mars')
    return c, c, year, c['julian_day']


def _birth_0(engine):
    lat, lon = -24.4404500128284, -124.38216690606723
    root = engine['calculate_traditional_chart_jd'](2428164.8044099067, lat, lon)
    rev = engine['calculate_traditional_chart_jd'](2454097.046352744, lat, lon)
    year = engine['pn4_sign_of_the_year'](root['ascendant'], 71)
    assert (root['sect'], rev['sect'], year['sign'], year['lord']) == ('Nocturnal', 'Nocturnal', 'Leo', 'Sun')
    return root, rev, year, 2454097.046352744


def _chart_s(engine):
    jd, lat, lon = 2461042.1650830186, -22.705951642146253, 42.053091056617774
    c = engine['calculate_traditional_chart_jd'](jd, lat, lon)
    year = engine['pn4_sign_of_the_year'](c['ascendant'], 0)
    return c, c, year, jd


def test_chart_m_mars_is_in_his_domain_by_sect_under_either_switch_setting(engine):
    # Mars, a nocturnal planet, in a nocturnal chart: of the chart's sect.
    # Before ruling 37 the Masha'allah setting turned both rows to
    # "contrary" (a male planet by night "under the earth in a female sign").
    root, rev, year, jd = _chart_m(engine)
    for rule in RULES:
        cells, _row = _cells(engine, rule, root, rev, year, jd)
        assert cells[('Mars', 'root')] == cells[('Mars', 'revolution')] == IN_SHORT, rule
        assert cells[('lord', 'root')] == cells[('lord', 'revolution')] == IN_LONG, rule


def test_birth_0_sun_lord_at_night_is_in_the_contrary_of_his_domain(engine):
    # II.3, 6's "in the contrary of its domain", fn 48 "sect": the Sun, a
    # diurnal planet, in a nocturnal root and revolution. Gr. Intr. VII.1's
    # three-valued condition read "neither" here, Masha'allah's "in".
    root, rev, year, jd = _birth_0(engine)
    for rule in RULES:
        cells, _row = _cells(engine, rule, root, rev, year, jd)
        assert cells[('lord', 'root')] == cells[('lord', 'revolution')] == CONTRARY, rule
        assert cells[('Sun', 'root')] == CONTRARY, rule
        assert cells[('Moon', 'root')] == IN_SHORT, rule


def test_chart_s_at_sunset_the_chart_sect_governs_the_pn4_rows(engine):
    # The chart is diurnal by the Sun's disk (the chart's sect) while the
    # Sun's centre is below the geometric horizon. Plain sect reads no
    # hemisphere: the Sun is of the diurnal chart's sect, so in his domain.
    root, rev, year, jd = _chart_s(engine)
    sun = root['planetary_data']['Sun']
    centre = engine['_sin_altitude'](sun['longitude'], sun.get('latitude', 0.0), sun.get('distance', 1.0),
                                     root['obliquity'], root['armc'], root['geo_lat'])
    assert root['sect'] == 'Diurnal' and centre < 0.0
    for rule in RULES:
        cells, _row = _cells(engine, rule, root, rev, year, jd)
        assert cells[('Sun', 'root')] == cells[('Sun', 'revolution')] == IN_SHORT, rule
        assert cells[('Venus', 'root')] == CONTRARY, rule


def _sample(engine, n=60, seed=20261005):
    rng = random.Random(seed)
    lo, hi = 2415020.5, 2462502.5   # 1900-01-01 and 2030-01-01, 0h UT
    for _ in range(n):
        jd, lat, lon, age = rng.uniform(lo, hi), rng.uniform(-60, 60), rng.uniform(-180, 180), rng.randint(1, 80)
        root = engine['calculate_traditional_chart_jd'](jd, lat, lon)
        jd_rev = engine['pn4_solar_revolution_jd'](jd, root['planetary_data']['Sun']['longitude'], age)
        rev = engine['calculate_traditional_chart_jd'](jd_rev, lat, lon)
        year = engine['pn4_sign_of_the_year'](root['ascendant'], age)
        yield root, rev, year, jd_rev


def test_every_pn4_domain_cell_is_plain_sect_and_ignores_the_switch(engine):
    seen = set()
    births = list(_sample(engine))
    assert len(births) == 60
    for root, rev, year, jd_rev in births:
        by_rule = {rule: _cells(engine, rule, root, rev, year, jd_rev)[0] for rule in RULES}
        cells = by_rule[RULES[0]]
        # Seven planets in two charts, and the II.3 lord in each.
        assert len(cells) == 16 and cells.keys() == by_rule[RULES[1]].keys()
        for key, value in cells.items():
            other = by_rule[RULES[1]][key]
            planet, label = key
            chart = root if label == 'root' else rev
            expected = _plain_sect(engine, chart, year['lord'] if planet == 'lord' else planet,
                                   long_form=(planet == 'lord'))
            if engine['is_unresolved'](expected):
                assert engine['is_unresolved'](value) and engine['is_unresolved'](other), key
                continue
            assert value == other == expected, (key, value, other, expected)
            seen.add(value)
    # Both values occur, and the third state of Gr. Intr. VII.1, 39 never.
    assert {IN_SHORT, CONTRARY} <= seen and 'neither' not in seen


def _mercury_on_the_sun(engine):
    positions = {'Sun': 180.0, 'Moon': 240.0, 'Mercury': 180.0, 'Venus': 90.0,
                 'Mars': 90.0, 'Jupiter': 300.0, 'Saturn': 0.0}
    data = {p: {'longitude': lon, 'latitude': 0.0, 'distance': 1.0, 'speed_in_lon': 1.0,
                'speed_in_lat': 0.0, 'speed_in_dist': 0.0} for p, lon in positions.items()}
    chart = {'planetary_data': data, 'ascendant': 0.0, 'houses': [float(v) for v in range(0, 360, 30)],
             'sect': 'Diurnal', 'julian_day': 2451545.0}
    return chart, chart, {'sign': 'Gemini', 'longitude': 60.0, 'lord': 'Mercury'}, 2451545.0


def test_mercury_on_the_suns_degree_stays_open_between_the_two_sects(engine):
    # Mercury's sect by phase is unassigned at the Sun's exact degree
    # (Gr. Intr. IV.9, 8); by plain sect the two readings are "in" (a
    # diurnal Mercury in a diurnal chart) and "contrary" (a nocturnal one).
    root, rev, year, jd = _mercury_on_the_sun(engine)
    for rule in RULES:
        cells, _row = _cells(engine, rule, root, rev, year, jd)
        for key in (('Mercury', 'root'), ('Mercury', 'revolution'), ('lord', 'root'), ('lord', 'revolution')):
            cell = cells[key]
            assert engine['is_unresolved'](cell), (rule, key)
            assert [name for name, _v in cell.alternatives] == ['if Mercury is diurnal', 'if Mercury is nocturnal']
            long_form = key[0] == 'lord'
            assert [v for _n, v in cell.alternatives] == [IN_LONG if long_form else IN_SHORT, CONTRARY], (rule, key)
            assert 'fn 46' in cell.source and 'IV.9, 8' in cell.source, cell.source
            assert '1.23, 17' not in cell.source and 'VII.1, 37' not in cell.source, cell.source


def test_the_ii3_row_names_the_definition_it_computes(engine):
    # FQ1's T-label: the Factor and Source name plain sect (fn 46, 48),
    # the same under either setting; neither Gr. Intr. VII.1, 37-39's
    # condition nor Masha'allah's On Nativities 1.23, 17.
    root, rev, year, jd = _chart_m(engine)
    labels = set()
    for rule in RULES:
        _cells_, row = _cells(engine, rule, root, rev, year, jd)
        labels.add((row['Factor'], row['Source']))
    assert len(labels) == 1
    factor, source = labels.pop()
    assert 'sect of the chart' in factor and 'fn 46' in factor
    assert source == 'PN IV II.3, 5-6; fn 46, 48'


def _app_strings():
    """app.py's string literals, each implicit concatenation joined as the
    parser joins it."""
    tree = ast.parse((ROOT / 'app.py').read_text(encoding='utf-8'))
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def test_the_switch_help_says_the_pn4_rows_are_not_under_it():
    strings = _app_strings()
    assert len(strings) > 1000
    # The radio's help beside the Sect table (kept within 300 characters by
    # F7-9's test), and the Sources page's entry for the switch: the PN IV
    # rows are named as not under it.
    help_ = [s for s in strings if s.startswith('Gr. Intr. VII.1, 37 / VII.6, 13: sign by gender')]
    assert len(help_) == 1
    # The list is not the whole of what the switch reaches (Topical Planets
    # in Houses is on the Sources page only), so the help points there.
    assert help_[0].endswith("not the Revolutions page's PN IV rows. More on the Sources page.")
    not_under = 'Not the PN IV I.7 and II.3 domain rows on the Revolutions page, which read plain sect'
    assert sum(not_under in s for s in strings) == 1
    assert not any("Revolutions page's domain cells" in s or 'follow this switch' in s for s in strings)
    # The II.3 notes and the I.7 table say what the rows read, quoting the
    # sentences and the note.
    ii3_note = ("Domain is read as plain sect: a lord of the chart's sect is in its own domain, one of the other "
                "sect in the contrary (PN IV II.3, 5 with fn 46, and PN IV II.3, 6 with fn 48); the Domain switch on the "
                "Dignities page does not reach it.")
    assert sum(ii3_note in s for s in strings) == 1
    assert not any('the row follows the Domain switch' in s for s in strings)
    i7_caption = [s for s in strings if s.startswith('Domain (17): "those of them in their own domain or not in their '
                                                     'domain (of the diurnal [planets] and the nocturnal ones)" '
                                                     '(PN IV I.7, 17), read as plain sect')]
    assert len(i7_caption) == 1
    assert 'simply of the sect of the chart' in i7_caption[0] and 'does not reach it' in i7_caption[0]


# --- Row [7] of II.3: the same domain as the I.7 table (the check's H11-10) --

SEVEN = ('Sun', 'Moon', 'Mercury', 'Venus', 'Mars', 'Jupiter', 'Saturn')
_PLANET_SPLIT = re.compile(r'; (?=(?:' + '|'.join(SEVEN) + r'): root )')


def _row_7_by_planet(reads):
    """II.3's revolution row [7], "Planet: root ... | revolution ...; ...",
    as {(planet, 'root' | 'revolution'): that chart's labels}."""
    out = {}
    for part in _PLANET_SPLIT.split(reads):
        planet, rest = part.split(': root ', 1)
        root, revolution = rest.split(' | revolution ', 1)
        out[(planet, 'root')], out[(planet, 'revolution')] = root, revolution
    return out


def _assert_row_7_reads_the_i7_domain(row_7, i7_cells, tag):
    """Every planet [7] lists carries, in each chart, exactly the I.7
    table's plain-sect domain, and none of the switch-following labels of
    the accidental rows."""
    assert row_7, tag
    for (planet, chart), labels in row_7.items():
        assert 'Hayz/domain' not in labels and 'Contrary to its domain' not in labels, (tag, planet, chart, labels)
        cell = i7_cells[(planet, chart)]
        other = CONTRARY if cell == IN_SHORT else IN_SHORT
        if cell in (IN_SHORT, CONTRARY):
            assert cell in labels and other not in labels, (tag, planet, chart, labels, cell)
        else:
            assert labels.count(IN_SHORT) == labels.count(CONTRARY) == 1, (tag, planet, chart, labels, cell)


@pytest.mark.parametrize('rule', RULES)
def test_row_7_on_chart_m_reads_mars_by_sect_under_either_setting(engine, rule):
    # Mars, lord of the year, in Aries, the sign of the year: [7] lists him.
    # His accidental row is "Hayz/domain (+3)" under "Abu Ma'shar" and
    # "Contrary to its domain" under "Masha'allah"; the lord row and I.7
    # read him in his domain by sect under both.
    root, rev, year, jd = _chart_m(engine)
    engine['set_readings'](DOMAIN_RULE=rule)
    i7 = {(r['Planet'], r['Chart']): r['Domain (17)'] for r in engine['pn4_i7_planets'](root, rev)}
    ii3 = engine['pn4_ii3_examination'](root, rev, year, jd)
    reads = next(r['Reads'] for r in ii3['revolution_rows'] if r['Question'].startswith('[7]'))
    row_7 = _row_7_by_planet(reads)
    assert ('Mars', 'root') in row_7 and ('Mars', 'revolution') in row_7, reads
    assert IN_SHORT in row_7[('Mars', 'root')] and IN_SHORT in row_7[('Mars', 'revolution')], reads
    _assert_row_7_reads_the_i7_domain(row_7, i7, f'Chart M, {rule}')


@pytest.mark.parametrize('rule', RULES)
def test_row_7_on_the_page_agrees_with_the_i7_table(rule):
    # The default chart on the Revolutions page (1983-11-19, Florence): under
    # "Abu Ma'shar" [7] gave Mars "Hayz/domain (+3)" in the root while the
    # I.7 table gave him "contrary to its domain".
    at = make_app(date='1983-11-19', page='timing')
    at.session_state['_domain_rule'] = rule
    at.run()
    assert_no_exception(at, f'Revolutions page, {rule}')
    frames = [n.value for n in at.main if getattr(n, 'type', None) == 'dataframe']
    i7_frame = next(f for f in frames if {'Planet', 'Chart', 'Domain (17)'} <= set(f.columns))
    i7 = {(p, c): str(v) for p, c, v in zip(i7_frame['Planet'], i7_frame['Chart'], i7_frame['Domain (17)'])}
    assert len(i7) == 14
    rev_frame = next(f for f in frames if 'Question' in f.columns
                     and f['Question'].astype(str).str.startswith('[7]').any())
    reads = rev_frame[rev_frame['Question'].astype(str).str.startswith('[7]')].iloc[0]['Reads']
    row_7 = _row_7_by_planet(reads)
    assert ('Mars', 'root') in row_7, reads
    _assert_row_7_reads_the_i7_domain(row_7, i7, f'1983-11-19 Florence, {rule}')


@pytest.mark.parametrize('sect', ('Diurnal', 'Nocturnal'))
def test_row_7_keeps_mercury_on_the_suns_degree_open(engine, sect):
    # Mercury on the Sun's degree in Libra, the sign of the year: [7] lists
    # him, and his domain stays open between the two sects, in words, by the
    # chart's sect. The row is the same under either switch setting and
    # carries none of the accidental row's domain labels, which follow the
    # switch -- "Domain/hayz unassigned (+3 excluded from the known
    # subtotal)" among them (the re-check's R-6; ruling 59).
    root, _rev, _year, jd = _mercury_on_the_sun(engine)
    root = dict(root, sect=sect)
    year = {'sign': 'Libra', 'longitude': 180.0, 'lord': 'Venus'}
    by_rule = {}
    for rule in RULES:
        engine['set_readings'](DOMAIN_RULE=rule)
        ii3 = engine['pn4_ii3_examination'](root, root, year, jd)
        by_rule[rule] = next(r['Reads'] for r in ii3['revolution_rows'] if r['Question'].startswith('[7]'))
    reads = by_rule[RULES[0]]
    assert by_rule[RULES[1]] == reads, by_rule
    for label in ('Domain/hayz', 'Hayz/domain', 'Contrary to its domain'):
        assert label not in reads, (label, reads)
    row_7 = _row_7_by_planet(reads)
    assert ('Mercury', 'root') in row_7 and ('Mercury', 'revolution') in row_7, reads
    day = sect == 'Diurnal'
    readings = (f"if Mercury is diurnal: {IN_SHORT if day else CONTRARY}; "
                f"if Mercury is nocturnal: {CONTRARY if day else IN_SHORT}")
    for chart in ('root', 'revolution'):
        labels = row_7[('Mercury', chart)]
        assert 'Unassigned' in labels and 'UnresolvedResult(' not in labels, labels
        assert readings in labels, (readings, labels)
