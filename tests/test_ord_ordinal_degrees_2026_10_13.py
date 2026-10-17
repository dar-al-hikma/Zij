"""Ordinal degrees in every degree table the app applies.

The texts number a sign's degrees as ordinals: the nth degree runs from
(n - 1) deg 00' up to, not including, n deg 00' (Gr. Intr. V.5, fn 39 warns of
the confusion with the cardinal degree; Gr. Intr. Fig. 38 prints each
exaltation degree beside its span). The engine converts in one place,
ordinal_degree / ordinal_degree_range / in_ordinal_degrees, and every table
reads through it.

For each table one listed degree is pinned at its edges through the reader a
chart shows (the condition, the row): (N-1) deg 00' 00" in, (N-1) deg 59' 59"
in, N deg 00' 00" out, and the edge below, (N-2) deg 59' 59", out. The seam
(0 Aries, 360, just under 360) and the helper's agreement with the inline
conversions it replaced are pinned too.

The harsher burned path of Gr. Intr. VII.6, 40 ("from 19° Libra up to 3°
Scorpio, because those are the fall of the luminaries") is read in ordinals
too, as the falls are (Gr. Intr. V.5, 11; Gr. Intr. Fig. 38): from the start
of the 19th degree of Libra to the end of the 3rd of Scorpio, through both its
readers (Gr. Intr. VII.6, 40's row and Sahl's condition 110, which borrows
it). The
measured eyesight rows (Gr. Intr. VI.20, 4-9) are read at their face.

The tables' own cells show their degrees as ordinals in the Reference page's
form ("19th", "19th degree of Aries"); a quotation of a figure or of a
sentence keeps the numbers as printed.
"""
import random
import re

import pytest

from corpus_paths import corpus_file
from skip_guard import needs_corpus

GR_INTR = corpus_file("gr_intr/abu_mashar_great_introduction.md")

SEC = 1.0 / 3600.0
SIGNS = ['Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo', 'Libra', 'Scorpio', 'Sagittarius',
         'Capricorn', 'Aquarius', 'Pisces']


def at(sign, deg, minute=0, second=0):
    """A longitude: `deg` deg `minute`' `second`" of `sign`."""
    return SIGNS.index(sign) * 30.0 + deg + minute / 60.0 + second * SEC


def edges(sign, first, last=None):
    """The four edges of ordinal degrees first..last: two in, two out."""
    last = first if last is None else last
    return [(at(sign, first - 1), True), (at(sign, last - 1, 59, 59), True),
            (at(sign, last), False), (at(sign, first - 1) - SEC, False)]


def _pd(**lons):
    return {p: {'longitude': v, 'latitude': 0.0, 'distance': 1.0, 'speed_in_lon': 1.0,
                'speed_in_lat': 0.0, 'speed_in_dist': 0.0} for p, v in lons.items()}


# Every point placed where no table under test has a degree, so a row seen
# belongs to the point moved.
QUIET = dict(Sun=at('Gemini', 20, 30), Moon=at('Leo', 25, 30), Mercury=at('Gemini', 20, 40),
             Venus=at('Taurus', 20, 30), Mars=at('Leo', 25, 40), Jupiter=at('Sagittarius', 20, 30),
             Saturn=at('Pisces', 15, 30))
QUIET_ASC = at('Gemini', 20, 50)


# --- the helper itself ------------------------------------------------------

@pytest.mark.parametrize("lon,degree", [
    (0.0, 1), (at('Aries', 0, 59, 59), 1), (at('Aries', 1), 2), (at('Aries', 29), 30),
    (at('Aries', 29, 59, 59), 30), (30.0, 1), (360.0, 1), (360.0 - SEC, 30), (360.0 - 1e-9, 30),
    (-1e-16, 1), (720.0 + at('Leo', 4, 30), 5)])
def test_ordinal_degree_of_a_longitude(engine, lon, degree):
    assert engine['ordinal_degree'](lon) == degree


@pytest.mark.parametrize("lon,sign", [(0.0, 'Aries'), (360.0, 'Aries'), (-1e-16, 'Aries'),
                                      (360.0 - SEC, 'Pisces'), (360.0 - 1e-9, 'Pisces')])
def test_the_seam_wraps_with_its_sign(engine, lon, sign):
    """0 Aries and 360 are Aries' 1st degree; just under 360 is Pisces' 30th."""
    assert engine['get_zodiac_sign'](lon) == sign
    assert engine['ordinal_degree'](lon) == (1 if sign == 'Aries' else 30)


@pytest.mark.parametrize("first,last,span", [(19, None, (18.0, 19.0)), (1, None, (0.0, 1.0)),
                                             (30, None, (29.0, 30.0)), (1, 3, (0.0, 3.0)),
                                             (12, 14, (11.0, 14.0))])
def test_ordinal_degree_range(engine, first, last, span):
    assert engine['ordinal_degree_range'](first, last) == span


@pytest.mark.parametrize("first,last", [(0, None), (31, None), (5, 4), (0, 3)])
def test_ordinal_degree_range_refuses_what_is_no_degree(engine, first, last):
    with pytest.raises(ValueError):
        engine['ordinal_degree_range'](first, last)


def _sample(seed=20261013, n=60000):
    rng = random.Random(seed)
    out = [0.0, 30.0, 359.0, 360.0 - 1e-9]
    for _ in range(n):
        whole = rng.randrange(360)
        out.append(whole + rng.choice([0.0, SEC, 59 / 60 + 59 * SEC, 1 - 1e-9, rng.random()]))
    return out


def test_the_helper_agrees_with_every_inline_conversion_it_replaced(engine):
    """Over a dense seeded sample of longitudes already on the circle, as every
    reader had them: the wells', Book V's and nobility's int(lon % 30) + 1;
    the bright and dark degrees' start <= int(lon % 30) <= end; the sign's
    last degree, lon % 30 >= 29; the Lot's EXALTATION_DEGREES[light] - 1.0."""
    od, inr, rng_ = engine['ordinal_degree'], engine['in_ordinal_degrees'], engine['ordinal_degree_range']
    runs = sorted({(s, e) for table in engine['BRIGHTNESS_DEGREES'].values() for s, e, _ in table})
    samples = _sample()
    assert len(samples) > 60000
    assert len(runs) > 30
    for lon in samples:
        assert od(lon) == int(lon % 30) + 1, lon
        assert (od(lon) == 30) == (lon % 30.0 >= 29.0), lon
        for s, e in runs:
            assert inr(lon, s + 1, e + 1) == (s <= int(lon % 30) <= e), (lon, s, e)
    for n in range(1, 31):
        assert rng_(n)[0] == n - 1.0


# --- exaltation degrees (Gr. Intr. V.5, Gr. Intr. Fig. 38) -----------------

def test_exaltation_degrees_are_ordinal_ranges(engine):
    """Each standard exaltation degree is the ordinal range Gr. Intr. Fig. 38
    prints:
    the Sun's 19th of Aries is 18 deg 00' up to 19 deg 00'."""
    rng_, inr = engine['ordinal_degree_range'], engine['in_ordinal_degrees']
    for planet, n in engine['EXALTATION_DEGREES'].items():
        sign = engine['EXALTATIONS'][planet][0]
        assert rng_(n) == (n - 1.0, float(n))
        assert [inr(lon, n) for lon, _ in edges(sign, n)] == [True, True, False, False], planet


@pytest.mark.parametrize("sect,light,start", [('Diurnal', 'Sun', at('Aries', 18)),
                                              ('Nocturnal', 'Moon', at('Taurus', 2))])
def test_the_lot_of_exaltation_counts_from_the_first_point_of_the_degree(engine, sect, light, start):
    """The Lot's exaltation end is the start of the ordinal degree, 18 deg 00'
    Aries and 2 deg 00' Taurus, not its end (19 deg 00', 3 deg 00')."""
    data = _pd(**QUIET)
    asc = 0.0
    lot = engine['lot_by_id']('exaltation', data, asc, None, sect)
    assert lot == pytest.approx((asc + start - data[light]['longitude']) % 360.0, abs=1e-9)


# --- wells (Gr. Intr. V.21, Gr. Intr. Fig. 62) ------------------------------

def _special(engine, planet, lon):
    data = _pd(**dict(QUIET, **{planet: lon}))
    return [r['Condition'] for r in engine['evaluate_special_degrees'](data) if r['Planet'] == planet]


@pytest.mark.parametrize("sign,n", [('Aries', 6), ('Libra', 20), ('Gemini', 30)])
def test_a_welled_degree_at_its_edges(engine, sign, n):
    assert n in engine['WELLED_DEGREES'][sign]
    seen = [any('Welled Degree' in c for c in _special(engine, 'Mars', lon)) for lon, _ in edges(sign, n)]
    assert seen == [expect for _, expect in edges(sign, n)], (sign, n)


# --- leaving a sign (Fifty Aphorisms #15, 31-33): the 30th degree -----------

def test_the_last_degree_of_a_sign_at_its_edges(engine):
    seen = [any('On the threshold' in c for c in _special(engine, 'Mars', lon)) for lon, _ in edges('Leo', 30)]
    assert seen == [True, True, False, False]


@pytest.mark.parametrize("lon,threshold,entering", [(360.0, False, True), (360.0 - SEC, True, False),
                                                    (360.0 - 1e-9, True, False), (0.0, False, True)])
def test_the_seam_through_the_sign_boundary_conditions(engine, lon, threshold, entering):
    """A planet at 360 stands at 0 Aries, entering it; just under 360 it is in
    Pisces' 30th degree, on the threshold."""
    conditions = _special(engine, 'Mars', lon)
    assert any('On the threshold' in c for c in conditions) is threshold
    assert any('Not yet established' in c for c in conditions) is entering


# --- Gr. Intr. V.22, Figs. 63-64 ---------------------------------------------

def _book_v(engine, table, **points):
    asc = points.pop('Ascendant', QUIET_ASC)
    fortune = points.pop('Fortune', at('Gemini', 21, 30))
    data = _pd(**dict(QUIET, **points))
    return [(r['Point'], r['Table']) for r in engine['evaluate_book_v_degrees'](data, asc, fortune, 'Diurnal')
            if r['Table'].startswith(table)]


def test_a_degree_increasing_in_good_fortune_at_its_edges(engine):
    assert 15 in engine['GOOD_FORTUNE_DEGREES']['Taurus']
    seen = [bool(_book_v(engine, 'Increasing', Moon=lon)) for lon, _ in edges('Taurus', 15)]
    assert seen == [True, True, False, False]


@pytest.mark.parametrize("sign,first,last", [('Aries', 19, 19), ('Cancer', 1, 3), ('Capricorn', 12, 14)])
def test_a_degree_of_elevation_at_its_edges(engine, sign, first, last):
    """A single degree and two of Gr. Intr. Fig. 64's runs (the 1st to the
    3rd of Cancer from 0 deg 00' up to 3 deg 00'; the edge below is Gemini's
    30th)."""
    assert set(range(first, last + 1)) <= set(engine['ELEVATION_DEGREES'][sign])
    seen = [bool(_book_v(engine, 'Elevation', Ascendant=lon)) for lon, _ in edges(sign, first, last)]
    assert seen == [True, True, False, False], (sign, first, last)


# --- Sahl's degrees of nobility (On Nativities 1.38, 39-41, Sahl I Fig. 57) -

def test_a_degree_of_nobility_at_its_edges(engine):
    assert 19 in engine['NOBILITY_DEGREES']['Aries']
    seen = []
    for lon, _ in edges('Aries', 19):
        rows = engine['evaluate_nobility_degrees'](_pd(**QUIET), lon, 'Diurnal')
        seen.append([r['Degree'] for r in rows if r['Point'] == 'Ascendant'])
    assert seen == [['19th degree of Aries'], ['19th degree of Aries'], [], []]


# --- bright and dark degrees (Gr. Intr. V.20, Gr. Intr. Fig. 61) ------------

@pytest.fixture(scope="module")
def vii6(engine):
    """A real chart whose Saturn is moved, read by Gr. Intr. VII.6's table."""
    lat, lon = 51.5074, -0.1278
    jd = engine['civil_local_to_jd_ut'](2001, 3, 4, 12, lon / 15)
    chart = engine['calculate_traditional_chart_jd'](jd, lat, lon)

    def labels(planet, where):
        data = {p: dict(d) for p, d in chart['planetary_data'].items()}
        data[planet]['longitude'] = where
        sect = chart['sect']
        essential = engine['evaluate_essential_dignities'](data, sect)
        accidental = engine['evaluate_accidental_dignities'](
            data, chart['houses'], sect, chart['julian_day'], armc=chart['armc'],
            obliquity=chart['obliquity'], geo_lat=lat)
        out = engine['evaluate_abu_mashar_condition'](data, chart['houses'], sect, essential, accidental,
                                                      chart['julian_day'], chart['ascendant'])
        return list(out[planet]['Negative Labels'])
    return labels


@pytest.mark.parametrize("sign,first,last", [('Aries', 4, 8), ('Aries', 30, 30), ('Cancer', 19, 20)])
def test_a_run_of_dark_degrees_at_its_edges(engine, vii6, sign, first, last):
    """Gr. Intr. Fig. 61 prints Aries' second run "3°-7°59'", the 4th to the
    8th degree; the stored (3, 7) is read through in_ordinal_degrees as
    3 deg 00' up to 8 deg 00'."""
    runs = [(s + 1, e + 1) for s, e, c in engine['BRIGHTNESS_DEGREES'][sign] if c == 'Dark']
    assert (first, last) in runs
    seen = [('Dark degree (35)' in vii6('Saturn', lon)) for lon, _ in edges(sign, first, last)]
    assert seen == [True, True, False, False], (sign, first, last)


# --- the harsher burned path (Gr. Intr. VII.6, 40): the falls as ordinals --

# 197 deg 59' 59" out; 198 deg 00' 00", 198 deg 59' 59" and 212 deg 59' 59"
# in; 213 deg 00' 00" out (the end, unmoved, still excluded).
HARSH_EDGES = [(at('Libra', 17, 59, 59), False), (at('Libra', 18), True), (at('Libra', 18, 59, 59), True),
               (at('Scorpio', 2, 59, 59), True), (at('Scorpio', 3), False)]


def test_the_harsh_burned_path_band_runs_through_the_falls_ordinal_degrees(vii6):
    """Gr. Intr. VII.6, 40's row: the band from the start of the 19th degree
    of Libra (18 deg 00') to the end of the 3rd of Scorpio; outside it, in
    Libra or Scorpio, the row is the plain burned path."""
    harsh, plain = 'Burned path, harsh band (40)', 'Burned path (40)'
    seen = [(harsh in labels, plain in labels) for labels in (vii6('Saturn', lon) for lon, _ in HARSH_EDGES)]
    assert seen == [(inside, not inside) for _, inside in HARSH_EDGES]


def _condition_110(engine, moon):
    data = _pd(Moon=moon, Venus=155.0, Mercury=335.0, Sun=0.0, **{'North Node': 80.0})
    data['Moon']['speed_in_lon'] = 13.0
    cusps = [30.0 * i for i in range(12)]
    return engine['evaluate_corruption_of_the_moon'](data, cusps, 'Diurnal')['testimonies'][110]


def test_sahls_condition_110_borrows_the_same_band(engine):
    """Sahl's Introduction Ch. 3, 110 gives no degrees and borrows Gr. Intr.
    VII.6, 40's band: it fires at the same edges, and for the Moon at
    18 deg 30' Libra."""
    seen = [_condition_110(engine, lon)['matched'] for lon, _ in HARSH_EDGES]
    assert seen == [inside for _, inside in HARSH_EDGES]
    assert _condition_110(engine, 198.5)['matched'] is True


CLAUSE_110 = ("In the burned path, \"the end of Libra and the beginning of Scorpio\" -- Sahl gives no degrees; "
              "the span from the 19th degree of Libra to the 3rd degree of Scorpio is Gr. Intr. VII.6, 40's "
              "harsher band (fn 120), borrowed. ")


def test_the_condition_110_text_gives_the_band_in_ordinals(engine):
    """The app's own sentence, not a quotation: the band in the Reference
    page's form."""
    clauses = [str(c) for c in _condition_110(engine, 198.5)['clauses']]
    assert clauses
    assert any(c.startswith(CLAUSE_110) for c in clauses), clauses
    assert not any('19 Libra' in c for c in clauses)


def test_the_band_comment_quotes_vii6_40_as_printed(engine):
    """The quotation above HARSH_BURNED_PATH keeps the page's "19°" and "3°"."""
    import inspect
    source = inspect.getsource(inspect.getmodule(engine['ordinal_degree']))
    block = source[:source.index('\nHARSH_BURNED_PATH = ')]
    block = block[block.rindex('\n\n'):]
    quoted = ' '.join(line.lstrip('# ') for line in block.strip().splitlines())
    assert '"from 19° Libra up to 3° Scorpio, because those are the fall of the luminaries"' in quoted


# --- the eyesight places (Sahl, On Nativities 6.2; Gr. Intr. VI.20) ---------

def _eyes(engine, source, sentence, lon):
    rows = engine['evaluate_eyesight_places'](_pd(**dict(QUIET, Moon=lon)), QUIET_ASC)
    return [r for r in rows if r['Point'] == 'Moon' and r['Source'] == f'{source}, {sentence}']


def test_an_ordinal_eyesight_degree_at_its_edges(engine):
    """Rhetorius's twelfth degree of Aquarius (Sahl, On Nativities 6.2, 67)."""
    seen = [bool([r for r in _eyes(engine, 'Sahl, On Nativities 6.2', 67, lon) if 'twelfth' in r['Place']])
            for lon, _ in edges('Aquarius', 12)]
    assert seen == [True, True, False, False]


def test_a_measured_eyesight_span_is_read_at_its_face(engine):
    """The Bizidaj's Libra 27° 36' to 28° (Sahl, On Nativities 6.2, 70):
    both ends are in, a second past either is out."""
    lo, hi = at('Libra', 27, 36), at('Libra', 28)
    seen = [bool(_eyes(engine, 'Sahl, On Nativities 6.2', 70, lon)) for lon in (lo, hi, hi + SEC, lo - SEC)]
    assert seen == [True, True, False, False]


# --- bounds and faces: runs of measured degrees, not ordinals ---------------

def test_bounds_and_faces_are_runs_of_measured_degrees(engine):
    rulers = engine['get_essential_rulers']
    assert rulers(at('Aries', 5, 59, 59))['term'] == 'Jupiter'
    assert rulers(at('Aries', 6))['term'] == 'Venus'
    assert rulers(at('Aries', 9, 59, 59))['face'] == 'Mars'
    assert rulers(at('Aries', 10))['face'] == 'Sun'


# --- the printed spans, from the corpus -------------------------------------

_ONE = re.compile(r"(\d+)\s*<sup>(?:st|nd|rd|th)</sup>\s*[♈-♓]?\s*\|\s*0?(\d+)°-0?(\d+)°59'")
_RUN = re.compile(r"(\d+)\s*<sup>(?:st|nd|rd|th)</sup>\s*[–-]\s*(\d+)\s*<sup>(?:st|nd|rd|th)</sup>\s*\|"
                  r"\s*0?(\d+)°-0?(\d+)°59'")


@needs_corpus(GR_INTR)
def test_every_printed_ordinal_span_is_the_helper_range(engine):
    """Gr. Intr. Figs. 38 and 62-64 print each ordinal beside its span (nine
    exaltations with the Nodes', 64 wells, seven degrees of good fortune,
    Gr. Intr. Fig. 64's 21 single degrees and four runs); every one is
    ordinal_degree_range's (start, end) with the end's 59' made whole."""
    text = GR_INTR.read_text(encoding="utf-8")
    start = text.index("### Chapter V.5: On the reason")
    fig38 = text[start:text.index("**Figure 38 (Gr. Intr.)", start)]
    v21 = text.index("### Chapter V.21")
    figs = text[v21:text.index("**Figure 64 (Gr. Intr.)", v21)]
    runs = [m.groups() for m in _RUN.finditer(figs)]
    singles = [m.groups() for m in _ONE.finditer(fig38 + _RUN.sub("", figs))]
    assert len(singles) == 9 + 64 + 7 + 21
    assert len(runs) == 4
    rng_ = engine['ordinal_degree_range']
    for n, lo, hi in singles:
        assert rng_(int(n)) == (float(lo), float(hi) + 1.0), (n, lo, hi)
    for first, last, lo, hi in runs:
        assert rng_(int(first), int(last)) == (float(lo), float(hi) + 1.0), (first, last)


# --- what the reader sees: the tables' own cells as ordinals ----------------
# The Reference page's form ("19th", "19th degree of Aries"). A quotation of a
# figure keeps the figure's numbers (Sahl I Fig. 57 in the Chart page's note;
# an eyesight row's printed words).

def _app(date, page, depth=None):
    from conftest import assert_no_exception, make_app
    at = make_app(date=date, page=page)
    if depth:
        at.session_state["_reading_depth"] = depth
    at.run()
    assert_no_exception(at, page)
    return at


SAHL_COL, ABU_COL = 'Sahl (On Nativities 1.38, 41)', "Abu Ma'shar (Gr. Intr. V.22, 4)"
REFERENCE_NOBILITY = [
    ('Aries', '19th', '19th'), ('Taurus', '3rd', '3rd'), ('Gemini', '13th', '11th'),
    ('Cancer', '1st, 13th, 14th, 15th', '1st, 2nd, 3rd, 14th, 15th'), ('Leo', '5th, 7th', '5th, 7th, 17th'),
    ('Virgo', '2nd, 13th, 20th', '2nd, 12th, 20th'), ('Libra', '-', '3rd, 5th, 21st'), ('Scorpio', '-', '12th, 20th'),
    ('Sagittarius', '-', '13th, 20th'), ('Capricorn', '12th, 13th, 20th', '12th, 13th, 14th, 20th'),
    ('Aquarius', '12th, 20th', '7th, 16th, 17th, 20th'), ('Pisces', '-', '12th, 20th')]


def test_the_reference_nobility_table_prints_both_columns_as_ordinals():
    """Sahl's column (Sahl I Fig. 57) and, beside it under the supplement,
    Abu Ma'shar's (Gr. Intr. Fig. 64), every cell an ordinal; an empty sign a
    dash."""
    at = _app("1240-05-23", "reference", "Course text and supplement")
    tables = [df.value for df in at.main.dataframe if SAHL_COL in df.value.columns]
    assert len(tables) == 1
    rows = [(r['Sign'], r[SAHL_COL], r[ABU_COL]) for r in tables[0].to_dict('records')]
    assert rows == REFERENCE_NOBILITY


CHART_SUMMARY_BAND = ("Abu Ma'shar's band from the 19th degree of Libra to the 3rd degree of Scorpio is applied in his "
                      "own Planetary Condition table and, borrowed and labelled, in Sahl's condition 110")
FIG57_AS_PRINTED = ("Figure 57 of his volume prints the degrees: Aries 19; Taurus 3; Gemini 13; Cancer 1, 13, 14, 15; "
                    "Leo 5, 7; Virgo 2, 13, 20; Capricorn 12, 13, 20; Aquarius 12, 20 -- none in Libra, Scorpio, "
                    "Sagittarius or Pisces. The figure prints bare degrees; this app reads them as ordinals")


def test_the_chart_page_names_the_degree_as_an_ordinal_and_quotes_the_figure_as_printed():
    """The Degree column of Degrees of nobility and rank (1240-05-25: the
    Moon at 13 deg 29' Cancer, in the 14th degree); the note's report of
    Sahl I Fig. 57 keeps the figure's bare numbers; the Special Degrees
    summary gives Gr. Intr. VII.6, 40's band in ordinals."""
    at = _app("1240-05-25", "chart")
    tables = [df.value for df in at.main.dataframe if list(df.value.columns) == ['Point', 'Position', 'Degree', 'Note']]
    assert len(tables) == 1
    assert [(r['Point'], r['Position'], r['Degree']) for r in tables[0].to_dict('records')] == \
        [('Moon', "13° Can 29'", '14th degree of Cancer')]
    md = [m.value for m in at.main.markdown]
    assert sum(FIG57_AS_PRINTED in m for m in md) == 1
    assert sum(CHART_SUMMARY_BAND in m for m in md) == 1
    assert not [m for m in md if '19 Libra' in m]


BOOK_V_NOTE = ('Ordinal degrees, as in the wells. The 5th degree of Leo and the 20th of Aquarius are in both tables; '
               'the 17th of Aquarius is a degree of elevation and a well.')


def test_the_book_v_note_names_the_degrees_in_both_tables_as_ordinals():
    at = _app("1240-09-18", "configurations", "Course text and supplement")
    md = [m.value for m in at.main.markdown]
    assert '**Ordinal degrees, and the degrees in both tables.**' in md
    assert sum(m == BOOK_V_NOTE for m in md) == 1


def test_an_eyesight_row_keeps_its_printed_words(engine):
    """The row's printed form is the book's ("from 6° to 9°"); the reading
    beside it is the app's."""
    rows = _eyes(engine, 'Sahl, On Nativities 6.2', 51, at('Sagittarius', 7))
    assert [r['Place'] for r in rows] == \
        ["the place of the arrow -- Sagittarius from 6° to 9° (ordinal degrees, 5°00'-9°00')"]
