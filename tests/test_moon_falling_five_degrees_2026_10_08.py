"""The third-day Moon's falling takes the five degrees (the owner's ruling 134).

On Nativities 1.29, 3 names falling among the corruptions; 1.30, 33 takes the
third-day Moon's "position relative to the Ascendant". The row counts her
falling with 1.22, 9's allowance, "the planets will not fall from the stakes
except after 5°", as the Planetary Condition and Strength of the Planets
tables count the stakes: quadrant_strength_position on the nativity's
divisions, the five degrees before the four axial degrees, exactly five
included. It no longer counts her whole-sign place.
"""
import re

import pytest
from datetime import datetime

from conftest import assert_no_exception, find_table, make_app
from corpus_paths import corpus_file
from skip_guard import skip_without_corpus

CORPUS = corpus_file("on_nativities.md")
FLORENCE = (43.7792, 11.2463)

# Constructed divisions of a nativity: opposite cusps 180 degrees apart, the
# Ascendant at 10 Cancer, the stake of the earth at 5 Libra, the seventh at
# 10 Capricorn, the Midheaven at 5 Aries (its falling division wraps 0 Aries).
CUSPS = (100.0, 125.0, 152.0, 185.0, 220.0, 251.0, 280.0, 305.0, 332.0, 5.0, 40.0, 71.0)
STAKES = {1: ('12th', 'the Ascendant'), 4: ('3rd', 'the stake of the earth'),
          7: ('6th', 'the seventh'), 10: ('9th', 'the Midheaven')}

NEW_NOTE = ('Falling is counted from the Ascendant of the nativity, which On Nativities 1.30, 33 takes her '
            'position relative to, and by the Alchabitius divisions of the nativity, as the Planetary Condition '
            'and Strength of the Planets tables count the stakes. On Nativities 1.22, 9 gives the allowance, '
            '"the planets will not fall from the stakes except after 5°". So the third-day Moon falls only in the '
            '12th, 3rd, 6th or 9th division, and only when she is more than five degrees before the degree of the '
            'stake that division ends at: the Ascendant, the stake of the earth, the seventh or the Midheaven. '
            'Within those five degrees she is still in the stake. The divisions, the five degrees counted in '
            'longitude, and exactly five degrees counted as within are this app\'s reading. The first row gives '
            'her whole-sign place from the Ascendant of the nativity; the Falling row counts by the divisions '
            'with the five degrees, so their numbers can differ.')
# The lane's first wording: "them" could be read as the stakes, as if any
# Moon past a stake's five degrees fell, the 11th division's included.
LOOSE_NOTE = 'and past them she falls'
FIRST_ROW = 'The Moon on the third day and her whole-sign place'
OLD_NOTE = 'falling is the whole-sign place from the natal Ascendant'


def _sign(lon):
    return int((lon % 360.0) // 30.0)


def _third(moon):
    """The seven planets on the third day, with nothing but the place able to
    corrupt her: Saturn in the second sign from hers and Mars in the sixth
    (both averse), the Sun four signs on (no burning)."""
    base = _sign(moon) * 30.0
    positions = {
        'Moon': (moon, 13.0),
        'Saturn': ((base + 45.0) % 360.0, 0.03),
        'Mars': ((base + 165.0) % 360.0, 0.7),
        'Sun': ((base + 135.0) % 360.0, 1.0),
        'Mercury': ((base + 130.0) % 360.0, 1.2),
        'Venus': ((base + 140.0) % 360.0, 1.1),
        'Jupiter': ((base + 255.0) % 360.0, 0.08),
    }
    data = {name: {'longitude': lon, 'latitude': 0.0, 'distance': 1.0, 'speed_in_lon': speed,
                   'speed_in_lat': 0.0, 'speed_in_dist': 0.0}
            for name, (lon, speed) in positions.items()}
    return {'planetary_data': data, **{name: row['longitude'] for name, row in data.items()}}


def _rows(engine, moon, cusps=CUSPS):
    return engine['moon_third_day_rows'](_third(moon), {'Saturn': 200.0, 'Mars': 250.0}, cusps[0], cusps)


def _row(rows, prefix):
    hits = [r for r in rows if r['Item'].startswith(prefix)]
    assert len(hits) == 1, prefix
    return hits[0]['Value']


@pytest.mark.parametrize('stake', sorted(STAKES))
@pytest.mark.parametrize('before, falls', [(4.5, False), (5.0, False), (5.5, True)])
def test_the_five_degrees_before_each_stake(engine, stake, before, falls):
    """Just inside the five degrees, at exactly five, and just past them, at
    each of the four stakes: only past them does she fall."""
    division, name = STAKES[stake]
    moon = (CUSPS[stake - 1] - before) % 360.0
    rows = _rows(engine, moon)
    where = f"the {division} division of the nativity, {before:.1f}° before the degree of {name}, "
    expected = (f"Yes: {where}past the five degrees: falling from the stakes" if falls
                else f"No: {where}within the five degrees: in the stake")
    assert _row(rows, 'Falling') == expected
    assert _row(rows, 'Third-day Moon: corruption checks') == (
        'Corruption found in these checks: falling' if falls else 'No corruption found in these checks')
    assert _row(rows, '1.29, 11').startswith(
        'Third-day component does not hold' if falls else 'Third-day component holds')


def test_whole_sign_says_falling_and_the_five_degrees_say_not(engine):
    """The Ascendant at 2 Cancer, the third-day Moon at 28 Gemini: the
    twelfth place by whole sign, but four degrees before the Ascendant's
    degree, so in the stake."""
    cusps = (92.0, 120.0, 150.0, 182.0, 212.0, 242.0, 272.0, 300.0, 330.0, 2.0, 32.0, 62.0)
    assert engine['get_wsh_house'](88.0, cusps[0]) == 12      # the old rule: falling
    rows = _rows(engine, 88.0, cusps)
    assert _row(rows, 'The Moon on the third day').startswith('28° Gem 00\', the 12th place from the Ascendant')
    assert _row(rows, 'Falling') == ('No: the 12th division of the nativity, 4.0° before the degree of the '
                                     'Ascendant, within the five degrees: in the stake')
    assert _row(rows, 'Third-day Moon: corruption checks') == 'No corruption found in these checks'


def test_whole_sign_says_not_falling_and_the_five_degrees_say_falling(engine):
    """The Ascendant at 25 Cancer, the third-day Moon at 2 Cancer: the
    first place by whole sign, but 23 degrees before the Ascendant's degree,
    past the five degrees, so falling."""
    cusps = (115.0, 140.0, 168.0, 200.0, 232.0, 262.0, 295.0, 320.0, 348.0, 20.0, 52.0, 82.0)
    assert engine['get_wsh_house'](92.0, cusps[0]) == 1       # the old rule: not falling
    rows = _rows(engine, 92.0, cusps)
    assert _row(rows, 'Falling') == ('Yes: the 12th division of the nativity, 23.0° before the degree of the '
                                     'Ascendant, past the five degrees: falling from the stakes')
    assert _row(rows, 'Third-day Moon: corruption checks') == 'Corruption found in these checks: falling'


def test_the_row_counts_falling_as_the_condition_tables_do(engine):
    """Round the circle on the constructed divisions, the row falls exactly
    where quadrant_strength_position (the Planetary Condition and Strength
    tables' helper) says 'falling', and the whole-sign place disagrees with
    it on both sides somewhere."""
    position = engine['quadrant_strength_position']
    wsh = engine['get_wsh_house']
    says, disagree = {True: 0, False: 0}, {True: 0, False: 0}
    for tenth in range(0, 3600, 5):
        moon = tenth / 10.0
        falls = _row(_rows(engine, moon), 'Falling').startswith('Yes:')
        assert falls is (position(moon, CUSPS)['strength'] == 'falling'), moon
        says[falls] += 1
        if falls is not (wsh(moon, CUSPS[0]) in engine['CADENT_HOUSES']):
            disagree[falls] += 1
    assert says[True] > 0 and says[False] > 0
    assert disagree[True] > 0 and disagree[False] > 0


@pytest.mark.parametrize('day, falling', [
    # 1240-05-23 (UT 13:45, Florence): the Moon 13 Cancer in the ninth
    # division, 1.2 degrees before the Midheaven's degree.
    (23, 'No: the 9th division of the nativity, 1.2° before the degree of the Midheaven, within the five '
         'degrees: in the stake'),
    # 1240-05-27: the twelfth place by whole sign, the eleventh division.
    (27, 'No: the 11th division of the nativity'),
    # 1240-05-29: the first place by whole sign, the twelfth division 7.7
    # degrees before the Ascendant's degree.
    (29, 'Yes: the 12th division of the nativity, 7.7° before the degree of the Ascendant, past the five '
         'degrees: falling from the stakes'),
])
def test_a_nativity_counts_on_its_own_divisions(engine, day, falling):
    chart = engine['calculate_traditional_chart'](datetime(1240, 5, day, 13, 45), *FLORENCE)
    rows = engine['evaluate_moon_third_day'](chart)
    assert _row(rows, 'Falling') == falling
    corruption = _row(rows, 'Third-day Moon: corruption checks')
    assert corruption.endswith('; falling') is falling.startswith('Yes:')


def _rendered(at):
    return '\n'.join(str(node.value) for kind in ('markdown', 'caption', 'info')
                     for node in getattr(at.main, kind))


@pytest.mark.parametrize('depth', ['Course text', 'Course text and supplement'])
@pytest.mark.parametrize('date, place, value', [
    ('1240-05-23', '10th', 'No: the 9th division of the nativity, 1.2° before the degree of the Midheaven, within the five '
                   'degrees: in the stake'),
    # Whole sign and the divisions agree: the 12th place and the 12th division.
    ('1240-05-28', '12th', 'Yes: the 12th division of the nativity, 20.7° before the degree of the Ascendant, past the '
                   'five degrees: falling from the stakes'),
    # They disagree: the 1st place above the 12th division, falling.
    ('1240-05-29', '1st', 'Yes: the 12th division of the nativity, 7.7° before the degree of the Ascendant, past the five '
                   'degrees: falling from the stakes'),
])
def test_the_findings_page_says_the_rule(engine, depth, date, place, value):
    at = make_app(date=date, page='findings')
    at.session_state['_reading_depth'] = depth
    at.run(timeout=300)
    assert_no_exception(at, f'third-day falling {date} {depth}')
    table = find_table(at, 'The Moon on the third day (Sahl)').value
    falling = table.loc[table['Item'] == 'Falling (1.29, 3)']
    assert falling['Value'].tolist() == [value]
    assert table['Item'].tolist()[0] == FIRST_ROW
    assert table['Value'].tolist()[0].split(' (two days')[0].endswith(
        f', the {place} place from the Ascendant of the nativity')
    assert falling['Text'].tolist() == [
        'On Nativities 1.30, 33 asks "how is her position relative to the Ascendant". On Nativities 1.22, 9: '
        '"the planets will not fall from the stakes except after 5°". The divisions of the nativity are this '
        'app\'s reading.']
    text = _rendered(at)
    assert NEW_NOTE in text
    assert OLD_NOTE not in text and 'the place is whole-sign' not in text
    assert LOOSE_NOTE not in text
    assert engine['THIRD_DAY_CORRUPTION_READER'] in text
    assert ('and falling counted by the divisions of the nativity with the five degrees at the stakes'
            in engine['THIRD_DAY_CORRUPTION_READER'])


@pytest.fixture(scope='module')
def corpus():
    skip_without_corpus(CORPUS)
    text = re.sub(r'<sup>\d+</sup>', '', CORPUS.read_text(encoding='utf-8'))
    return text.replace('*', '')


def test_the_quoted_words_are_on_the_page(engine, corpus):
    """Every quotation the row and the note make is in the sentence they cite:
    1.22, 9 (Sahl I p. 306) and 1.30, 33 (pp. 338-339)."""
    lines = corpus.splitlines()
    nine = next(line for line in lines if line.startswith('9 And the planets will not fall'))
    thirty_three = next(line for line in lines if '33 And look at the inclination of the Moon after that' in line)
    text = _rows(engine, 92.0)
    row = next(r for r in text if r['Item'] == 'Falling (1.29, 3)')['Text']
    cited = dict(re.findall(r'On Nativities (1\.22, 9|1\.30, 33)[^"]*"([^"]+)"', row))
    assert cited == {'1.22, 9': 'the planets will not fall from the stakes except after 5°',
                     '1.30, 33': 'how is her position relative to the Ascendant'}
    assert cited['1.22, 9'] in nine and cited['1.30, 33'] in thirty_three
    note = re.findall(r'"([^"]+)"', NEW_NOTE)
    assert note == [cited['1.22, 9']]
