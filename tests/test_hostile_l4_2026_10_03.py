"""Hostile pass, lane L4 (2026-10-03): what is DONE with the prediction numbers
-- counting, ordering, ranking, tie-breaking and the time lords' arithmetic
on the Revolutions, Releaser, Days and months, and Fardar and ages pages.

One xfail(strict=True) test per finding in the lane report (L4-01 .. L4-09),
each asserting the RIGHT behaviour so it fails today and passes when fixed;
then ordinary passing tests for the attacks the app survived, each checked
against the corpus sentence or figure it rests on. The corpus tests read the
PN IV text and the Great Introduction through tests/corpus_paths.py and skip
only when the corpus is absent.

Chart throughout: the harness's default, 1240-05-23 14:30 LMT Florence
(natal Ascendant 12 Libra 16', diurnal, natal hour lord the Moon). The
target 1250-05-23 is the 10th civil birthday; the 10th solar return falls
at 17:43 UT that day, after the noon the pages read, so there `age` is 10
while `cycle` is 9 and `month` is 12.
"""
from __future__ import annotations

import re

import pytest

from conftest import make_app, assert_no_exception, find_table, table_nodes, ui_source
from corpus_paths import corpus_file, CORPUS_DIR
from skip_guard import skip_without_corpus

PN4_TEXT = corpus_file("pn4/pn4_complete/persian_nativities_iv.md")
PN4_AGES_FIXED = corpus_file("pn4/corrected_tables/p169_ages_fixed.md")
GR_INTR_TEXT = corpus_file("gr_intr/abu_mashar_great_introduction.md")
SAHL_NATIVITIES = corpus_file("on_nativities.md")

FLORENCE = (43.7792, 11.2463)
BIRTH = (1240, 5, 23)
TENTH_BIRTHDAY = (1250, 5, 23)


def _corpus(path):
    skip_without_corpus(path)
    return path.read_text()


# --- the bundle, computed as app.py computes it ---------------------------

def _chart(engine, birth=BIRTH, local_hour=14.5, lat=FLORENCE[0], lon=FLORENCE[1]):
    offset = lon / 15.0                                        # LMT, as the sidebar's default standard
    jd = engine["civil_local_to_jd_ut"](*birth, local_hour, offset)
    chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
    chronocrats = engine["calculate_chronocrats"](jd, lat, lon, int(local_hour), offset)
    return jd, chart, chronocrats


def _bundle(engine, target, birth=BIRTH):
    _jd, chart, chronocrats = _chart(engine, birth)
    bundle = engine["pn4_timing_bundle"](
        chart, FLORENCE[0], FLORENCE[1], engine["CivilDate"](*birth), engine["CivilDate"](*target),
        engine["PN4_MONTHLY_TURN_OPTIONS"][0], chronocrats)
    return chart, bundle


def _sign_of(engine, lon):
    return engine["get_zodiac_sign"](lon)


@pytest.fixture(scope="module")
def tenth_birthday(engine):
    """age 10, cycle 9, month 12: the civil birthday has passed, the return has not."""
    chart, bundle = _bundle(engine, TENTH_BIRTHDAY)
    assert (bundle['age'], bundle['cycle'], bundle['month']) == (10, 9, 12), "the fixture's premise moved"
    return chart, bundle


# =========================================================================
# The findings (xfail, strict)
# =========================================================================

def test_l4_01_month_indicators_turn_from_the_revolution_they_are_dated_to(engine, tenth_birthday):
    chart, b = tenth_birthday
    rows = {r['#']: r for r in b['monthly_rows']}
    # The table is dated to the revolution of `cycle` and labelled month `month`
    # (IX.1, 9-14): #1 is that revolution's sign of the year turned month-1 signs.
    expected_sign = _sign_of(engine, engine["pn4_profect"](chart['ascendant'], b['cycle'] + b['month'] - 1))
    assert rows[1]['Sign'] == expected_sign, (rows[1], expected_sign)
    # #2 is the first ninth-part lord of THAT sign (IX.1, 12-14)
    assert rows[2]['Lord'] == engine["pn4_first_ninth_part_lord"](expected_sign)['lord']


def test_l4_02_fardar_active_mark_agrees_with_the_age_columns_at_a_boundary(engine, tenth_birthday):
    # The fardar runs on years elapsed from the birth hour (IV.1, 11: "from
    # the hour he was born up to 10 years he will be in the fardar of the
    # Sun"), and its table's columns are in that unit: on the 10th civil
    # birthday at noon UT 9.9986 years have elapsed, the Sun's period is
    # still running, and the row marked Active is the row the number falls
    # in. (As first written the test compared the columns with the civil
    # age; the count the table keys on is the elapsed years, so that is the
    # number it is held to, and the page says so.)
    _chart, b = tenth_birthday
    active = [r for r in b['fardar_rows'] if r['Active'] == 'yes']
    assert len(active) == 1
    row = active[0]
    assert float(row['From age']) <= b['elapsed_years'] < float(row['To age']), (row, b['age'], b['elapsed_years'])
    assert b['fardar']['lord'] == row['Lord'] and row['Cycle'] == b['fardar']['cycle'] == 1
    # The Revolutions page's indicator #4 is the fardar AS IT STANDS AT THE
    # REVOLUTION'S MOMENT (IX.9, 1: the indicators are looked at "in the
    # revolution"), so it prints the revolution's elapsed years, truncated
    # to three decimals and never rounded onto a row's own boundary, and
    # says where it was read. The Count row prints the target's.
    rev_from = b['revolution_window'][0]
    assert b['year_rows'][3]['Active point'].startswith(
        f"at the revolution's moment, {engine['pn4_elapsed_text'](rev_from)} years elapsed")
    assert b['fardar_sr']['lord'] in b['year_rows'][3]['Ruler']
    assert engine['pn4_elapsed_text'](b['elapsed_years']) in b['revolution_rows'][0]['Value']


def test_l4_03_year_under_examination_help_names_three_counts():
    src = ui_source()
    assert "Every table on the Prediction pages keys on completed civil anniversaries" not in src


def test_l4_04_mighty_days_direct_this_revolutions_terminal_point(engine, tenth_birthday):
    chart, b = tenth_birthday
    start = b['mighty_days'][0]['from_lon']
    this_revolutions_terminal_point = engine["pn4_profect"](chart['ascendant'], b['cycle'])
    assert abs(((start - this_revolutions_terminal_point + 180.0) % 360.0) - 180.0) < 1e-6, (
        engine["get_degree_string"](start), engine["get_degree_string"](this_revolutions_terminal_point))


def test_l4_05_governor_tally_is_one_years(engine):
    _c1, before = _bundle(engine, (1250, 5, 22))
    _c2, on = _bundle(engine, (1250, 5, 23))
    assert before['jd_sr'] == on['jd_sr'], "premise: the same revolution on both days"
    assert before['governor'][1]['tally'] == on['governor'][1]['tally']
    assert before['governor'][1]['primary'] == on['governor'][1]['primary']


def test_l4_06_birth_date_target_has_no_negative_day_clocks(engine):
    _chart, b = _bundle(engine, BIRTH)
    assert b['day_of_year'] >= 0.0, b['day_of_year']
    rows, _month, ninth = b['day_methods']
    method1 = rows[0]
    # IX.7, 2-3: the year opens in the week of the planet named, and 0 days from birth that planet has the day
    assert method1['Opens the year'].startswith(f"{method1['This week']}'s week"), method1
    assert all(not r['Month'].startswith('0:') for r in ninth), ninth


def test_l4_07_tied_primary_is_not_examined_alphabetically(engine):
    chart, b = _bundle(engine, (1250, 5, 22))
    primary = b['governor'][1]['primary']
    assert len(primary) > 1, "premise: a tie (Jupiter, Mars and Moon with two testimonies each)"
    rows = engine["_pn4_primary_condition"](primary, chart, b['sr'])
    assert rows == [] or engine["is_unresolved"](rows), rows


def test_l4_07_a_single_primary_route_under_a_tied_opening_partner_is_labelled_with_its_planet(monkeypatch):
    # The blind check of fix lane F3 (item 17): with Venus moved onto the
    # Sun at 1241-05-22 the opening partner is tied; the Sun route ties the
    # primary (Jupiter/Venus) while the Venus route has Venus alone. The
    # lane's first build labelled that third table with the route's contact
    # only -- "Venus by trine at ..., behind the Ascendant (the opening
    # partner is tied)" -- not with the planet it is built for. Every table
    # names its planet: where a route's primary is not tied the label ends
    # in that planet's name; and the heading does not say the primary is
    # tied where only the opening partner is.
    # The owner's rulings 14 and 19 (2026-10-05, PN IV III.1, 50): the Sun
    # and Venus met at one degree behind the Ascendant are partners
    # together, so no route is drawn for an opening tie; the labels follow
    # the rulings -- none for an opening tie, and the one table's heading
    # names the one primary, Venus.
    import engine as module
    at = make_app(page="timing")
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "1241-05-22"
    original = module.calculate_traditional_chart_jd
    def patched(*args, **kwargs):
        chart = original(*args, **kwargs)
        chart["planetary_data"]["Venus"]["longitude"] = chart["planetary_data"]["Sun"]["longitude"]
        return chart
    monkeypatch.setattr(module, "calculate_traditional_chart_jd", patched)
    at.run(timeout=300)
    assert_no_exception(at, "Venus on the Sun, 1241-05-22")
    # The premise beside the empty list (lane TL, TL-22): the governor's tables
    # are drawn, so no label is the rulings' answer, not an empty page.
    assert [h for h, _node in table_nodes(at) if h.startswith("The governor (PN IV IX.9")], "premise: the governor is drawn"
    labels = [m.value for m in at.markdown if m.value.startswith("**") and "(the opening partner is tied)" in m.value]
    assert labels == [], labels
    heads = [m.value for m in at.markdown if "the condition of the primary planet" in m.value]
    assert len(heads) == 1, heads
    assert "the opening partner" not in heads[0] and "the condition of the primary planet (Venus)" in heads[0], heads[0]
    assert "UnresolvedResult(" not in heads[0]
    # The check of lane F3 (R6): the export takes its labels through a
    # second call site, so the JSON's governor entries carry the same
    # single-primary label, ending in the route's planet -- in the entry's
    # label, not its citation (F3 check 18; F8 part B).
    entries = at.session_state["_analysis_export"]["results"]["Prediction"]["The governor (PN IV IX.9, 1-10; IX.2, 4-7)"]
    cites = [e["label"] for e in entries if isinstance(e.get("label"), str)
             and "(the opening partner is tied)" in e["label"]]
    assert cites == [], cites


def test_l4_08_month_caption_names_the_months_ninth_part():
    at = make_app(page="days")
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "1250-05-23"
    at.run()
    assert_no_exception(at, "days page at the 10th birthday")
    table = find_table(at, "The seven indicators of the month").value
    row2 = table[table['#'] == 2].iloc[0]
    caption = next(c.value for c in at.main.caption if c.value.startswith("Month 12 of 12"))
    assert f"lord {row2['Lord']})" in caption, (caption, row2['Lord'])


def test_l4_09_day_chart_with_sun_and_meeting_falling_takes_the_ascendant(engine):
    _jd, chart, _chron = _chart(engine, birth=(1240, 1, 7), local_hour=8.0)
    jd = engine["civil_local_to_jd_ut"](1240, 1, 7, 8.0, FLORENCE[1] / 15.0)
    syzygies = engine["sahl_prenatal_meeting_and_fullness"](jd, *FLORENCE)
    releaser = engine["sahl_releaser"](chart['planetary_data'], chart['ascendant'], chart['houses'], chart['sect'],
                                       chart['lot_of_fortune'], syzygies['meeting']['longitude'],
                                       syzygies['fullness']['longitude'])
    assert chart['sect'] == 'Diurnal'
    sun, meeting = releaser['candidates'][0], releaser['candidates'][1]
    assert sun['Verdict'].split(' -- ')[-1].startswith('falling'), sun
    assert meeting['Verdict'].split(' -- ')[-1].startswith('falling'), meeting
    assert releaser['releaser'] is None, releaser['verdict']
    assert '1.15, 9' in releaser['verdict'], releaser['verdict']


# --- L4-10, L4-11, L4-12: reported without xfails; added here -------------

def test_l4_10_fardar_table_is_the_cycle_the_native_is_in(engine):
    _chart, b = _bundle(engine, (2026, 5, 23))
    assert b['fardar']['cycle'] == 11, "premise: the default chart is in its eleventh fardar cycle in 2026"
    assert [r['Cycle'] for r in b['fardar_rows']] == [11] * 9, b['fardar_rows'][0]
    active = [r for r in b['fardar_rows'] if r['Active'] == 'yes']
    assert len(active) == 1 and active[0]['Lord'] == b['fardar']['lord']
    # The columns are the cycle's own years, in the unit the mark runs on (years elapsed from the birth hour)
    assert float(active[0]['From age']) <= b['elapsed_years'] < float(active[0]['To age']), (active[0], b['elapsed_years'])
    assert float(b['fardar_rows'][0]['From age']) == 750.0 and float(b['fardar_rows'][-1]['To age']) == 825.0


def test_l4_11_ii3_looking_at_the_ascendant_row_says_its_frame_is_a_reading(engine, tenth_birthday):
    _chart, b = tenth_birthday
    row = next(r for r in b['ii3']['refinement_rows'] if r['Refinement'].startswith('Looking at the Ascendant'))
    reads = row['Reads']
    # II.3, 16-17 name no Ascendant; 16 asks "the two times": both frames, each said, and the choice said as a reading
    assert "from the revolution's Ascendant, house" in reads and "from the natal Ascendant, house" in reads, reads
    assert "reading" in reads and "16-17 do not say" in reads, reads
    assert row['Source'] == 'II.3, 16-18'


def test_l4_12_iii2_window_is_this_revolutions_year_in_the_unit_now_runs_on(engine, tenth_birthday):
    _chart, b = tenth_birthday
    lo, hi = b['revolution_window']
    # The window is the revolution's year in the distribution's own unit, so Now is always inside it
    assert lo <= b['elapsed_years'] < hi, (lo, b['elapsed_years'], hi)
    assert abs(lo - (b['jd_sr'] - _chart['julian_day']) / engine["PN4_DIRECTION_YEAR_DAYS"]) < 1e-9
    assert abs(hi - (b['jd_sr_next'] - _chart['julian_day']) / engine["PN4_DIRECTION_YEAR_DAYS"]) < 1e-9
    # and the rows listed are exactly the shifts whose arc falls in it
    expected = [engine["pn4_elapsed_text"](nxt['from']) for prev, nxt in zip(b['segments'], b['segments'][1:]) if lo <= nxt['from'] < hi
                for _r in engine["pn4_classify_shift"](prev, nxt)]
    assert [r['At age'] for r in b['iii2_transitions']] == expected
    # Across the whole table, every shift is listed under exactly one revolution's year: the 10th birthday's
    # window must not be the civil [10, 11) that left a shift at 9.9995 under a year the page was not examining
    assert hi < 10.0 < hi + 1.0


def test_l4_09_day_chart_sent_by_fifteen_does_not_quote_nine():
    """1.15, 9's premise is both day candidates falling. On a day chart
    whose Sun was in place but unseen (1.15, 7) the chart reaches the
    Ascendant by 15's second arm, and the verdict and the Ascendant row
    must say so rather than quote 9. The check's input."""
    from datetime import time
    at = make_app(date="1240-01-21", page="releaser")
    at.session_state["time_input_key"] = time(17, 0)                    # LMT, Florence
    at.run(timeout=180)
    assert_no_exception(at, "1240-01-21 17:00")
    cands = next(n.value for _h, n in table_nodes(at) if "Candidate" in map(str, n.value.columns))
    sun = cands[cands["Candidate"] == "the Sun"].iloc[0]["Verdict"]
    meeting = cands[cands["Candidate"].str.startswith("the meeting")].iloc[0]["Verdict"]
    asc_row = cands[cands["Candidate"] == "the Ascendant"].iloc[0]
    asc = asc_row["Source"]
    verdict = next(m.value for m in at.main.markdown if "no releaser by Nawbakht" in m.value)
    note = next(m.value for m in at.main.markdown if "the verdict names" in m.value)
    assert not sun.split(" -- ")[-1].startswith("falling"), sun          # house 7, unseen
    assert meeting.split(" -- ")[-1].startswith("falling"), meeting       # house 6: the mixed case
    assert "if the meeting and the Sun were both falling" not in verdict, verdict
    assert "1.15, 9" not in verdict and "1.15, 15" in verdict, verdict
    assert asc == "1.15, 15-16", asc
    # Re-check R-7: the mixed case reaches the Ascendant by both arms of 15
    # (the meeting by the first, the Sun by the second), so both are quoted.
    assert "in the falling [places], or they were not falling but the lord of their bound" in verdict, verdict
    # Re-check R-8: the page's other two statements of the route follow the
    # verdict -- reading (7) and the Ascendant row's Verdict name 15, not 9.
    assert "the verdict names 9 with 16" not in note, note[-120:]
    assert "that sentence is 1.15, 15" in note, note[-160:]
    assert "1.15, 9 names" not in asc_row["Verdict"], asc_row["Verdict"][-170:]
    assert "1.15, 15 sends" in asc_row["Verdict"], asc_row["Verdict"][-170:]


def test_l4_09_ascendant_row_does_not_claim_nine_when_the_sun_is_the_releaser(engine):
    """On a day chart where the Sun qualifies, the Ascendant was never
    reached by 9, and its row's Source must not claim it."""
    _jd, chart, _chron = _chart(engine, birth=(1240, 5, 23), local_hour=12.0)
    jd = engine["civil_local_to_jd_ut"](1240, 5, 23, 12.0, FLORENCE[1] / 15.0)
    syzygies = engine["sahl_prenatal_meeting_and_fullness"](jd, *FLORENCE)
    releaser = engine["sahl_releaser"](chart['planetary_data'], chart['ascendant'], chart['houses'], chart['sect'],
                                       chart['lot_of_fortune'], syzygies['meeting']['longitude'],
                                       syzygies['fullness']['longitude'])
    assert chart['sect'] == 'Diurnal'
    assert releaser['releaser'] == 'the Sun', releaser['verdict']
    asc = next(r for r in releaser['candidates'] if r['Candidate'] == 'the Ascendant')
    assert asc['Source'] == '1.15, 15-16', asc


# =========================================================================
# Attacks that held, pinned against the page
# =========================================================================

def _figure_table(text, anchor, before=True, limit=40):
    """The markdown table rows nearest to `anchor` (a line containing it)."""
    lines = text.splitlines()
    idx = next(i for i, l in enumerate(lines) if anchor in l)
    rows = []
    rng = range(idx - 1, max(idx - limit, 0), -1) if before else range(idx + 1, idx + limit)
    for i in rng:
        if lines[i].startswith('|'):
            rows.append([c.strip() for c in lines[i].strip().strip('|').split('|')])
        elif rows:
            break
    return rows[::-1] if before else rows


def test_fardar_sequence_is_iv_1_3_4_with_the_nodes_last_in_both_sects(engine):
    text = _corpus(PN4_TEXT)
    assert ("from the Sun, where[ever] he was in the celestial sphere: then after that are the years of Venus, "
            "then the years of Mercury, the Moon, and the years of Saturn") in text
    assert "one begins the distribution of the years of the *fardār* with the Moon, then Saturn, Jupiter, [and] Mars" in text
    assert "with the Head, then the Tail, whether the native was diurnal or nocturnal" in text
    day = [p for p, _y in engine["pn4_fardar_sequence"]('Diurnal')]
    night = [p for p, _y in engine["pn4_fardar_sequence"]('Nocturnal')]
    assert day == ['Sun', 'Venus', 'Mercury', 'Moon', 'Saturn', 'Jupiter', 'Mars', 'Head', 'Tail']
    assert night == ['Moon', 'Saturn', 'Jupiter', 'Mars', 'Sun', 'Venus', 'Mercury', 'Head', 'Tail']
    for sect in ('Diurnal', 'Nocturnal'):
        assert sum(y for _p, y in engine["pn4_fardar_sequence"](sect)) == 75.0


def test_fardar_sevenths_match_iv_1_11_and_the_boundaries_are_half_open(engine):
    text = _corpus(PN4_TEXT)
    assert "that is 1 year, 5 months, 4 days, and approximately 6 hours" in text          # IV.1, 11: 10/7 years
    tenth = 10.0 / 7.0 * 365.25
    assert abs(tenth - (365.25 + 5 * 30.44 + 4 + 6 / 24.0)) < 1.5                          # within a day and a half
    f = engine["pn4_fardar_at_age"]
    assert f(10.0, 'Diurnal')['lord'] == 'Venus' and f(10.0 - 1e-9, 'Diurnal')['lord'] == 'Sun'
    assert f(75.0, 'Diurnal')['lord'] == 'Sun' and f(75.0, 'Nocturnal')['lord'] == 'Moon'   # IV.7, 25
    assert f(75.0, 'Diurnal')['cycle'] == 2 and f(0.0, 'Diurnal')['cycle'] == 1
    assert f(70.0, 'Diurnal')['lord'] == 'Head' and f(70.0, 'Diurnal')['sub_lord'] is None     # IV.1, 8
    sun = f(8.6, 'Diurnal')
    assert (sun['lord'], sun['sub_lord']) == ('Sun', 'Mars') and abs(sun['sub_from'] - 60.0 / 7.0) < 1e-9


def test_lord_of_the_orb_matches_figure_89_age_by_age(engine):
    text = _corpus(PN4_TEXT)
    rows = _figure_table(text, "Figure 89 (PN IV)")
    ages, hours = [], []
    for r in rows:
        if r and 'Age' in r[0]:
            ages.extend(int(c) for c in r[1:])
        elif r and r[0] == 'Hour':
            hours.extend(1 if c == 'N' else int(c) for c in r[1:])
    assert len(ages) == len(hours) >= 84
    spheres = engine["PN4_DESCENDING_SPHERES"]
    for natal in spheres:
        for age, hour in zip(ages, hours):
            lord = engine["pn4_lord_of_the_orb"](natal, age)
            assert (spheres.index(lord) - spheres.index(natal)) % 7 == hour - 1, (natal, age, hour, lord)


def test_ages_of_man_match_the_corrected_figure_53(engine):
    text = _corpus(PN4_AGES_FIXED)
    glyph = {'☽': 'Moon', '☿': 'Mercury', '♀': 'Venus', '☉': 'Sun', '♂': 'Mars', '♃': 'Jupiter', '♄': 'Saturn'}
    table = [[c.strip() for c in l.strip().strip('|').split('|')] for l in text.splitlines() if l.startswith('| ')]
    body = [r for r in table if r[0] in glyph]
    assert len(body) == 7
    f = engine["pn4_age_of_man"]
    for planet_glyph, years, ages, _label in body:
        lo, hi = (int(x) for x in ages.split('-'))
        planet = glyph[planet_glyph]
        assert f(lo)['planet'] == planet and f(hi)['planet'] == planet and f(hi + 0.999)['planet'] == planet
        assert f(lo)['nominal_years'] == int(years)
    assert f(4)['planet'] == 'Mercury' and f(3.999)['planet'] == 'Moon'
    assert f(98)['planet'] == 'Saturn' and f(500)['planet'] == 'Saturn' and f(98)['to'] is None    # I.8, 25
    assert "until the end of his lifespan" in _corpus(PN4_TEXT)


def test_planetary_years_match_figure_146_cell_by_cell(engine):
    text = _corpus(GR_INTR_TEXT)
    rows = _figure_table(text, "Figure 146 (Gr. Intr.): Planetary years")
    glyph = {'♄': 'Saturn', '♃': 'Jupiter', '♂': 'Mars', '☉': 'Sun', '♀': 'Venus', '☿': 'Mercury', '☽': 'Moon'}
    num = lambda s: float(s.replace(' ½', '.5').replace('½', '.5'))
    seen = set()
    for r in rows:
        if r and r[0] in glyph:
            p = glyph[r[0]]
            y = engine["PLANETARY_YEARS"][p]
            assert (y['fardar'], y['lesser'], y['middle'], y['greater'], y['mighty']) == tuple(num(c) for c in r[1:6]), (p, r)
            seen.add(p)
        elif r and r[0] == '☊':
            assert engine["NODE_FARDAR_YEARS"]['Head'] == int(r[1])
        elif r and r[0] == '☋':
            assert engine["NODE_FARDAR_YEARS"]['Tail'] == int(r[1])
    assert len(seen) == 7


def test_partner_rank_is_iii_2_103_104(engine):
    text = _corpus(PN4_TEXT)
    assert ("the strongest of the rays is the opposition, and after that the square, than the trine, "
            "and the weakest of them is the sextile") in text
    assert "the one below it in power is the one managing for it by body; but as for the lord of the ray, it is lower" in text
    order = sorted(engine["PN4_PARTNER_RANK"], key=engine["PN4_PARTNER_RANK"].get)
    assert order == ['body', 'opposition', 'square', 'trine', 'sextile']


def test_small_and_mighty_day_constants_are_ix_7_29_and_25(engine):
    text = _corpus(PN4_TEXT)
    assert "a day for every 59' 08\"" in text
    assert "(and that is 1/6 of a day and half a sixth of a tenth of a day)" in text
    assert "comes to 365 ¼ days, approximately the number of days of the year" in text
    assert abs(engine["PN4_SMALL_DAYS_RATE"] - (59 + 8 / 60.0) / 60.0) < 1e-12
    assert abs(engine["PN4_MIGHTY_DAYS_PER_DEGREE"] - 12.175) < 1e-12
    assert abs(30 * engine["PN4_MIGHTY_DAYS_PER_DEGREE"] - 365.25) < 1e-9
    assert abs(360.0 / engine["PN4_SMALL_DAYS_RATE"] - 365.28) < 0.01


def test_method_1_week_lords_follow_figure_136s_remainders(engine):
    text = _corpus(PN4_TEXT)
    rows = _figure_table(text, "Figure 136 (PN IV)", limit=20)
    spheres = engine["PN4_DESCENDING_SPHERES"]
    checked = 0
    for r in rows:
        if r and r[0].isdigit() and 'ASC' in (r[-2] + r[-1]).upper():
            label = r[-2] if 'ASC' in r[-2].upper() else r[-1]           # "Lord of ASC" / "1<sup>st</sup> planet below lord ASC"
            k = 0 if label.startswith('Lord of ASC') else int(re.match(r"(\d)", label).group(1))
            for cell in r[:7]:
                d = int(cell)
                got = engine["pn4_ix7_weeks_from_birth"](float(d), 'Mars')['week']
                assert got == spheres[(spheres.index('Mars') + k) % 7], (d, k, got)
                checked += 1
    assert checked == 49


def test_profection_counts_completed_years_from_the_ascendant(engine):
    text = _corpus(PN4_TEXT)
    assert "the indicator of the year of birth is the sign of the Ascendant, and the indicator of the second year is the second sign from it" in text
    asc = 12.27 + 180.0                                                 # 12 Libra 16'
    year = engine["pn4_sign_of_the_year"]
    assert year(asc, 0)['sign'] == 'Libra' and year(asc, 12)['sign'] == 'Libra' and year(asc, 11)['sign'] == 'Virgo'
    assert year(asc, 1)['sign'] == 'Scorpio' and abs(year(asc, 5)['longitude'] % 30.0 - asc % 30.0) < 1e-9
    assert engine["pn4_completed_years"](engine["CivilDate"](1240, 5, 23), engine["CivilDate"](1250, 5, 22)) == 9
    assert engine["pn4_completed_years"](engine["CivilDate"](1240, 5, 23), engine["CivilDate"](1250, 5, 23)) == 10


def test_governor_testimonies_are_ix_9_2_to_9(engine):
    text = _corpus(PN4_TEXT)
    for n, needle in ((2, "The first is the lord of the year."), (3, "The second is the distributor from the Ascendant."),
                      (4, "The third is the distributor from the [longevity] releaser."),
                      (5, "The fourth is the partner to them both,"), (6, "The fifth is the lord of the *fardār*."),
                      (7, "The sixth is the lord of the orb."),
                      (8, "The seventh is the one accepting the connection of the Moon, or the lord of her house."),
                      (9, "The eighth is the first lord of the Ascendant of the revolution,")):
        assert needle in text, needle
    cites = [c for _n, _label, c in engine["PN4_GOVERNOR_TESTIMONIES"]]
    assert cites == [f"IX.9, {n}" for n in range(2, 10)]


def test_rate_ladder_is_iii_1_13_and_closes_at_25_thirds(engine):
    text = _corpus(PN4_TEXT)
    assert "every 25‴" in text or "25‴" in text
    rows = {r['Arc']: r['Is'] for r in engine["PN4_LADDER_ROWS"]}
    assert rows == {'1°': '1 year', '5′': '1 month', '1′': '6 days', '10″': '1 day', '25‴': '1 hour'}
    t = engine["pn4_arc_to_time"](1.0 + 5 / 60 + 1 / 60 + 10 / 3600 + 25 / 216000.0)
    assert (t['years'], t['months'], t['days']) == (1, 1, 7) and abs(t['hours'] - 1.0) < 1e-6


def test_sahl_releaser_places_are_1_15_6_and_11(engine):
    text = _corpus(SAHL_NATIVITIES)
    assert "the Sun in the Ascendant, the Midheaven, the house of hope, or in the stake of the west, or in the eighth" in text
    assert "if you found the Moon in a stake or what follows a stake" in text
    assert set(engine["SAHL_RELEASER_DAY_PLACES"]) == {1, 10, 11, 7, 8}
    assert set(engine["SAHL_RELEASER_NIGHT_PLACES"]) == {1, 4, 7, 10, 2, 5, 8, 11}
    assert engine["SAHL_DIGNITY_RANK"] == ('bound', 'house', 'exaltation', 'triplicity', 'face')        # 1.20, 2


def test_the_ten_day_run_at_the_boundary_keeps_the_pages_up(tenth_birthday):
    """The whole bundle at the mixed-count target renders without an UnresolvedResult leaking (the
    conftest fixture raises on one) and its three counts are what the report says they are."""
    _chart, b = tenth_birthday
    assert b['revolution_rows'][0]['Value'].startswith(
        "10 completed civil years (the Chronocrator Matrix's profection and the labels); 9 solar returns completed")
    assert abs(b['elapsed_years'] - 9.99864) < 1e-4
