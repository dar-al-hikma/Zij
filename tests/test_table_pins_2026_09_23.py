"""Table pins (2026-09-23): every doctrinal table the engine transcribes from
a printed page, compared cell by cell with a literal read off that page.

Before this module only five transcribed tables (the wells, Figures 63 and
64, the planetary years, the JN years) were compared with their source; the
rest were pinned to literals copied into a test and never compared with
anything, or pinned in part, or not at all. The citation checker never sees
a table. So each table below has:

* a literal vendored AS READ OFF THE PAGE PHOTOGRAPH (photographs_by_page/
  beside the corpus checkout; the file is named in the comment above the
  literal) or, for the course's Handy Tables, off the PDF page rendered at
  300 dpi. Literals keep the page's own glyphs and order, so a reader can lay
  each one beside the page and check it cell by cell;
* Test A (runs everywhere): the engine's constant equals the literal over
  the cells the engine carries;
* Test B (texts present): the literal equals the table PARSED from the
  corpus markdown, where the corpus holds the table as text. A figure the
  corpus holds only as an image, and the Handy Tables, have no Test B.

Where engine, page and markdown did not all agree on a cell nothing was
changed at first: the test carrying that cell was a strict xfail whose
reason started with its finding number, T-NN. The findings are written up in
the corpus, process/table_pins_2026-09-23/REPORT.md; the owner's rulings on
T-01..T-05 (RULINGS.md beside it) corrected the engine and the markdown, and
the xfails were removed. A new disagreement follows the same pattern.

Locators always name the volume: Gr. Intr. (Abu Ma'shar's Great
Introduction), PN IV (Persian Nativities IV), Sahl I (the Sahl volume),
Handy (TNAC Handy Tables from Part 1, course PDF).
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from corpus_paths import corpus_file
from skip_guard import needs_corpus

GR_INTR = corpus_file("gr_intr/abu_mashar_great_introduction.md")
PN4 = corpus_file("pn4/pn4_complete/persian_nativities_iv.md")
PN4_FIXED = corpus_file("pn4/corrected_tables")      # the same tables, repaired against the pages during OCR
SAHL_INTRO = corpus_file("sahl_introduction_zodiac_chapters.md")
SAHL_INTRO_CH3 = corpus_file("sahl_introduction_ch3.md")
SAHL_NAT = corpus_file("on_nativities.md")
SAHL_CHOICES = corpus_file("sahl_on_choices.md")
EPHE_STARS = Path(__file__).resolve().parents[1] / "ephe" / "sefstars.txt"

SIGNS = ['Aries', 'Taurus', 'Gemini', 'Cancer', 'Leo', 'Virgo',
         'Libra', 'Scorpio', 'Sagittarius', 'Capricorn', 'Aquarius', 'Pisces']
SIGN = dict(zip('♈♉♊♋♌♍♎♏♐♑♒♓', SIGNS))
PLANET = {'☉': 'Sun', '☽': 'Moon', '☿': 'Mercury', '♀': 'Venus', '♂': 'Mars', '♃': 'Jupiter', '♄': 'Saturn'}
GLYPH = {name: glyph for glyph, name in PLANET.items()}


def _needs(path):
    """Test B marker: skip, naming the corpus, where the text is absent (CI)."""
    return needs_corpus(path, why="the page literal is what Test A uses")


def _opposite(sign):
    return SIGNS[(SIGNS.index(sign) + 6) % 12]


# --- Reading the markdown ------------------------------------------------------
GREEK = {'alpha': 'α', 'beta': 'β', 'gamma': 'γ', 'delta': 'δ', 'epsilon': 'ε', 'theta': 'θ'}


def _norm(cell, footnotes=True):
    """One markdown cell as plain text: LaTeX degrees and Greek letters to
    their characters, <br> to a space, bold marks dropped. Footnote
    superscripts are kept as bare digits (footnotes=True) or dropped."""
    s = re.sub(r'\\(alpha|beta|gamma|delta|epsilon|theta)\b', lambda m: GREEK[m.group(1)], cell)
    s = s.replace('^{\\circ}', '°').replace('^\\circ', '°')
    s = re.sub(r'\^\{([^}]*)\}', r'\1', s)
    s = re.sub(r'\\text\{([^}]*)\}', r'\1', s).replace('$', '')
    s = re.sub(r'<sup>(.*?)</sup>', r'\1' if footnotes else '', s)
    s = s.replace('<br>', ' ').replace('**', '').replace('*', '')
    return ' '.join(s.split())


def _cells(line, footnotes=True):
    return [_norm(c, footnotes) for c in line.strip().strip('|').split('|')]


def _is_rule(line):
    return re.fullmatch(r'\|[\s:|-]+\|?', line.strip()) is not None


def _table_before(text, caption, footnotes=True):
    """The rows (cells) of the markdown table that ends just above the first
    line beginning with `caption` (bold marks ignored), rules dropped."""
    lines = text.splitlines()
    end = next(i for i, l in enumerate(lines) if l.strip().strip('*').startswith(caption))
    i = end - 1
    while not lines[i].strip():
        i -= 1
    block = []
    while i >= 0 and lines[i].startswith('|'):
        block.append(lines[i])
        i -= 1
    return [_cells(l, footnotes) for l in reversed(block) if not _is_rule(l)]


def _all_rows(text, footnotes=True):
    """Every table row of a file that holds one table and nothing else."""
    return [_cells(l, footnotes) for l in text.splitlines() if l.startswith('|') and not _is_rule(l)]


def _pn4_copies(caption, fixed_name):
    """The rows of one PN IV figure as the spliced text has it and as its
    corrected-table copy has it: [(which, rows), ...]."""
    return [('spliced', _table_before(PN4.read_text(encoding="utf-8"), caption)),
            (fixed_name, _all_rows((PN4_FIXED / fixed_name).read_text(encoding="utf-8")))]


def _span(cell):
    """'0° - 5° 59'' -> (0, 5): the first and last whole degree of a span."""
    lo, hi = re.fullmatch(r"(\d+)\s*°\s*-\s*(\d+)\s*°\s*59['’]", cell).groups()
    return int(lo), int(hi)


def _glyphs(cell):
    return tuple(ch for ch in cell if ch in PLANET)


def _chapter(text, start, stop, bold=False):
    """The prose of one chapter, page furniture, footnotes, images and
    captions removed, as a single line. With bold=True (PN IV numbers its
    sentences in bold) each '**N**' becomes the marker '§N§'."""
    lines = text.splitlines()
    a = next(i for i, l in enumerate(lines) if l.startswith(start))
    b = next(i for i, l in enumerate(lines) if i > a and l.startswith(stop))
    keep = []
    for l in lines[a + 1:b]:
        s = l.strip()
        if (not s or s == '---' or s.startswith(('*[', '<sup>', '![', '|', 'Figure', '**Figure', '#'))):
            continue
        if bold:
            s = re.sub(r'\*\*(\d+)\*\*', r'§\1§', s)
        keep.append(_norm(s, footnotes=False))
    return ' '.join(keep)


_SENTENCE_START = r'(?:^|(?<=[\s.”"\')\]]))(\d{1,3}) (?=[A-Z\[(“"])'


def _sentences(prose, numbers, bold=False):
    """{n: text of sentence n} for the wanted numbers. Candidate numbers are
    taken only as a rising run from the chapter's first, each the next
    number or the one after it (a printed heading can hold a number's place,
    as Sahl I Introduction 2, 3 does), so a number inside a sentence is not
    taken for a sentence start."""
    pattern = r'§(\d+)§' if bold else _SENTENCE_START
    chain = []
    for m in re.finditer(pattern, prose):
        n = int(m.group(1))
        if not chain or chain[-1][0] < n <= chain[-1][0] + 2:
            chain.append((n, m.start(), m.end()))
    ends = [a for _n, a, _b in chain[1:]] + [len(prose)]
    return {n: prose[b:end].strip() for (n, _a, b), end in zip(chain, ends) if n in numbers}


def _degrees(sentence):
    return tuple(int(d) for d in re.findall(r'(\d+)\s*°', sentence))


# ================================================================================
# 1. EXALTATION_DEGREES (with EXALTATIONS): Gr. Intr. V.5, Figure 38
# ================================================================================
# Gr. Intr. p. 268, read off GrIntr_p0268.jpg. As printed: planet, ordinal
# degree and sign, cardinal span. The ninth row prints the Head's glyph again
# where V.5, 10 names the Tail; the engine carries no node row.
GR_INTR_FIG38 = (
    ('♄', '21st', '♎', "20°-20°59'"),
    ('♃', '15th', '♋', "14°-14°59'"),
    ('♂', '28th', '♑', "27°-27°59'"),
    ('☉', '19th', '♈', "18°-18°59'"),
    ('♀', '27th', '♓', "26°-26°59'"),
    ('☿', '15th', '♍', "14°-14°59'"),
    ('☽', '3rd', '♉', "2°-2°59'"),
    ('☊', '3rd', '♊', "2°-2°59'"),
    ('☊', '3rd', '♐', "2°-2°59'"),
)
# Handy p. 1, "Standard and Hermes exaltation degrees" (course PDF): planet,
# standard column, Hermes column, as printed.
HANDY_P1_EXALTATION_DEGREES = (
    ('♄', '21° ♎', '20° ♎'), ('♃', '15° ♋', '15° ♋'), ('♂', '28° ♑', '27° ♑'), ('☉', '19° ♈', '18° ♈'),
    ('♀', '27° ♓', '26° ♓'), ('☿', '15° ♍', '15° ♍'), ('☽', '3° ♉', '2° ♉'),
)


def test_fig38_ordinals_and_cardinal_spans_agree_on_the_page():
    for _glyph, ordinal, _sign, span in GR_INTR_FIG38:
        n = int(re.match(r'\d+', ordinal).group())
        assert _span(span) == (n - 1, n - 1), ordinal


@pytest.mark.parametrize("glyph, ordinal, sign, _span_", [r for r in GR_INTR_FIG38 if r[0] in PLANET],
                         ids=[PLANET[r[0]] for r in GR_INTR_FIG38 if r[0] in PLANET])
def test_A_exaltation_degree_and_sign_match_gr_intr_fig38(engine, glyph, ordinal, sign, _span_):
    planet = PLANET[glyph]
    assert engine["EXALTATION_DEGREES"][planet] == int(re.match(r'\d+', ordinal).group())
    assert engine["EXALTATIONS"][planet] == [SIGN[sign]]


@pytest.mark.parametrize("glyph, standard, _hermes", HANDY_P1_EXALTATION_DEGREES,
                         ids=[PLANET[r[0]] for r in HANDY_P1_EXALTATION_DEGREES])
def test_A_exaltation_degree_matches_handy_p1_standard_column(engine, glyph, standard, _hermes):
    degree, sign = standard.split()
    assert engine["EXALTATION_DEGREES"][PLANET[glyph]] == int(degree.rstrip('°'))
    assert engine["EXALTATIONS"][PLANET[glyph]] == [SIGN[sign]]


# T-01, ruled: Gr. Intr. Fig. 38 puts the Sun's 19th degree of Aries at 18°-18°59' and the Moon's 3rd
# of Taurus at 2°-2°59'; the Lot of Exaltation had started from 19°00' Aries and 3°00' Taurus.
def test_A_lot_of_exaltation_endpoints_lie_in_the_fig38_degrees(engine):
    """Not a table constant: the Lot (On Nativities 4.1, 6) takes the sect
    light's "degree of his exaltation", which the engine hard-codes."""
    for sect, glyph in (('Diurnal', '☉'), ('Nocturnal', '☽')):
        _g, _ordinal, sign, span = next(r for r in GR_INTR_FIG38 if r[0] == glyph)
        lo, hi = _span(span)
        start = SIGNS.index(SIGN[sign]) * 30
        point = engine["_lot_point"]("exaltation_degree", {}, 0.0, [], sect, {})
        assert start + lo <= point < start + hi + 1, (sect, point)


@_needs(GR_INTR)
def test_B_fig38_literal_matches_the_markdown():
    rows = _table_before(GR_INTR.read_text(encoding="utf-8"), "Figure 38 (Gr. Intr.)")
    got = []
    for glyph, deg, span in rows:
        n, suffix, sign = re.fullmatch(r'(\d+) ?(st|nd|rd|th) ?(\S)', deg).groups()
        got.append((glyph, n + suffix, sign, span))
    assert tuple(got) == GR_INTR_FIG38


# ================================================================================
# 2. MASCULINE_/FEMININE_QUADRANT_HOUSES, ADVANCING_BY_QUADRANT_FIG90:
#    Gr. Intr. VI.26, 3, Figure 90
# ================================================================================
# Gr. Intr. p. 386, read off GrIntr_p0386.jpg and GrIntr_p0386_alt1.jpg. The
# corpus holds this figure only as an image: no Test B for it. The figure names
# its quadrants by position; its dashed arrows run clockwise (up the left, over
# the top, down the right), i.e. the Ascendant on the left and the Midheaven
# on top. VI.26, 3, printed beside it, names the same quadrants by the angles
# that bound them; VI.26, 2 puts three houses in each quadrant and VI.26, 6
# counts the houses from the one rising in the east.
GR_INTR_FIG90 = {
    'upper left':  ('Advancing', 'Male', 'Eastern', 'On right'),
    'upper right': ('Withdrawing', 'Feminine', 'Western', 'On left'),
    'lower left':  ('Withdrawing', 'Feminine', 'Western', 'On left'),
    'lower right': ('Advancing', 'Male', 'Eastern', 'On right'),
}
FIG90_POSITION_ANGLES = {       # Ascendant left, Midheaven top (the arrows' orientation)
    'upper left': ('Ascendant', 'Midheaven'), 'upper right': ('Midheaven', 'setting'),
    'lower left': ('fourth', 'Ascendant'), 'lower right': ('setting', 'fourth'),
}
# VI.26, 3 (same page): the quadrants "from" one angle "to" another, first the
# two called advancing (male, eastern, on the right), then the two called
# withdrawing (feminine, western, on the left), angles as the sentence words them.
GR_INTR_VI26_3 = {
    'advancing': (('Ascendant', 'Midheaven'), ('setting', 'fourth')),
    'withdrawing': (('tenth', 'setting'), ('fourth', 'Ascendant')),
}
ANGLE_HOUSE = {'Ascendant': 1, 'fourth': 4, 'setting': 7, 'Midheaven': 10, 'tenth': 10}


def _quadrant_houses(a, b):
    """The three whole houses between two adjacent angles, counted from the
    east (VI.26, 2 and 6): between the Ascendant and the Midheaven lie the
    10th-12th, and so on round the circle."""
    x, y = ANGLE_HOUSE[a], ANGLE_HOUSE[b]
    start = x if (x + 2) % 12 + 1 == y else y
    assert (start + 2) % 12 + 1 in (x, y), (a, b)
    return {(start + k - 1) % 12 + 1 for k in range(3)}


def test_fig90_positions_carry_the_labels_vi26_3_gives_their_angles():
    for position, labels in GR_INTR_FIG90.items():
        a, b = FIG90_POSITION_ANGLES[position]
        houses = _quadrant_houses(a, b)
        named = [k for k, pairs in GR_INTR_VI26_3.items() if any(_quadrant_houses(*p) == houses for p in pairs)]
        assert named == [labels[0].lower()], position


def test_A_quadrant_genders_and_advancing_set_match_gr_intr_fig90(engine):
    male = set().union(*(_quadrant_houses(*FIG90_POSITION_ANGLES[p]) for p, l in GR_INTR_FIG90.items() if l[1] == 'Male'))
    female = set().union(*(_quadrant_houses(*FIG90_POSITION_ANGLES[p]) for p, l in GR_INTR_FIG90.items() if l[1] == 'Feminine'))
    advancing = set().union(*(_quadrant_houses(*pair) for pair in GR_INTR_VI26_3['advancing']))
    assert engine["MASCULINE_QUADRANT_HOUSES"] == male == {4, 5, 6, 10, 11, 12}
    assert engine["FEMININE_QUADRANT_HOUSES"] == female == {1, 2, 3, 7, 8, 9}
    assert engine["ADVANCING_BY_QUADRANT_FIG90"] == advancing == male


@_needs(GR_INTR)
def test_B_vi26_3_as_the_markdown_words_it():
    prose = _chapter(GR_INTR.read_text(encoding="utf-8"), "### Chapter VI.26", "### Chapter VI.27")
    s3 = _sentences(prose, {3})[3]
    pairs = re.findall(r'from the (Ascendant|Midheaven|setting|fourth|tenth) to the (Ascendant|Mid- ?heaven|Midheaven|setting|fourth|tenth)', s3)
    pairs = [(a, b.replace('- ', '').replace('-', '')) for a, b in pairs]
    assert s3.index('advancing') < s3.index('withdrawing')
    assert {'advancing': tuple(pairs[:2]), 'withdrawing': tuple(pairs[2:])} == GR_INTR_VI26_3


# ================================================================================
# 3. PN4_II3_FIGURE_55: PN IV II.3, 5-8, Figure 55
# ================================================================================
# PN IV p. 188, read off PN4_p0188.jpg. The comparison column as printed; of
# the "Basic meaning" column only the words that tie each row to its sentence
# are kept (the engine quotes II.3, 5-8 themselves, not the figure; its four
# quotes were read against PN4_p0187.jpg, sentences 5-6, and PN4_p0188.jpg, 7-8).
PN4_FIG55 = (
    ('Good in root, good in SR', ('safety', 'delight')),
    ('Good in root, bad in SR', ('weakness', 'decrease')),
    ('Bad in root, good in SR', ('improve', 'delight')),
    ('Bad in root, bad in SR', ('excess of adversity',)),
)
_FIG55_WORD = {'good': 'good', 'bad': 'bad', 'suitable': 'good', 'excellent': 'good', 'contrary': 'bad'}


def _fig55_states(text):
    """'Good in root, bad in SR' or the engine's 'suitable in the root,
    contrary in the revolution' -> ('good', 'bad')."""
    words = re.findall(r'\b(good|bad|suitable|excellent|contrary)\b', text.lower())
    if 'both' in text.lower():
        words = words * 2
    return tuple(_FIG55_WORD[w] for w in words)


@pytest.mark.parametrize("i", range(4), ids=['good-good', 'good-bad', 'bad-good', 'bad-bad'])
def test_A_figure_55_rows_match_pn4_fig55(engine, i):
    label, cite, quote = engine["PN4_II3_FIGURE_55"][i]
    comparison, words = PN4_FIG55[i]
    assert _fig55_states(label) == _fig55_states(comparison)
    assert cite == f"II.3, {5 + i}"
    assert all(w in quote.lower() for w in words), (quote, words)


@_needs(PN4)
def test_B_fig55_literal_matches_the_markdown():
    rows = _table_before(PN4.read_text(encoding="utf-8"), "Figure 55 (PN IV)")
    body = rows[rows.index(['Comparison', 'Basic meaning']) + 1:]
    assert [r[0] for r in body] == [c for c, _w in PN4_FIG55]
    assert all(all(w in r[1].lower() for w in words) for r, (_c, words) in zip(body, PN4_FIG55))


@_needs(PN4)
def test_B_figure_55_quotes_are_in_their_sentences(engine):
    prose = _chapter(PN4.read_text(encoding="utf-8"), "### Chapter II.3", "### Chapter II.4", bold=True)
    sentences = _sentences(prose, {5, 6, 7, 8}, bold=True)
    for _label, cite, quote in engine["PN4_II3_FIGURE_55"]:
        assert ' '.join(quote.split()) in sentences[int(cite.split(', ')[1])], cite


# ================================================================================
# 4. VICTOR_WEIGHTS, VICTOR_PLACES_VALUES: Handy, Lesson 20 (course PDF only)
# ================================================================================
# Handy p. 33, "Weighted victors" and "House values for ibn Ezra's victor";
# Handy p. 34, "House values for Masha'allah's victor". Read off the PDF pages
# rendered at 300 dpi. No markdown: the course PDF is the only text.
HANDY_P33_WEIGHTED_VICTORS = {
    'Older': {'authors': ('Umar al-Tabari', "Masha'allah"),
              'weights': {'House': 5, 'Exaltation': 4, 'Bound': 3, 'Triplicity': 2, 'Face': 1}},
    'Newer': {'authors': ('Al-Qabisi', "Abu Ma'shar"),
              'weights': {'House': 5, 'Exaltation': 4, 'Triplicity': 3, 'Bound': 2, 'Face': 1}},
}
# inner ring (house) -> outer ring (value)
HANDY_P33_IBN_EZRA_PLACES = {1: 12, 2: 6, 3: 3, 4: 9, 5: 7, 6: 1, 7: 10, 8: 4, 9: 5, 10: 11, 11: 8, 12: 2}
# four wedges print two values, "Masha'allah" n / Dorotheus m, kept as (n, m)
HANDY_P34_MASHAALLAH_PLACES = {1: 12, 2: (3, 4), 3: 5, 4: 7, 5: (8, 9), 6: 1, 7: (9, 8), 8: (4, 3),
                               9: 6, 10: 11, 11: 10, 12: 2}
# Handy p. 33, "Table for ibn Ezra's victor #1 (1485/1537)": columns and rows as printed
HANDY_P33_WORKSHEET_COLUMNS = ('♄', '♃', '♂', '☉', '♀', '☿', '☽')
HANDY_P33_WORKSHEET_ROWS = ('☉:', '☽:', 'ASC:', '⊗:', '☌/☍:', 'Lord day (7)', 'Lord hour (6)', 'Places', 'Totals')
_DIGNITY_KEY = {'House': 'domicile', 'Exaltation': 'exaltation', 'Triplicity': 'triplicity', 'Bound': 'term', 'Face': 'face'}


def _scheme(engine_table, method):
    (key,) = [k for k in engine_table if k.startswith(method)]
    return key


@pytest.mark.parametrize("method", ['Older', 'Newer'])
def test_A_victor_weights_match_handy_p33(engine, method):
    key = _scheme(engine["VICTOR_WEIGHTS"], method)
    page = HANDY_P33_WEIGHTED_VICTORS[method]
    assert engine["VICTOR_WEIGHTS"][key] == {_DIGNITY_KEY[k]: v for k, v in page['weights'].items()}
    # the key names the page's two authors (the engine drops "Umar")
    assert all(a.split()[-1].lower() in key.lower() for a in page['authors']), key


def test_A_victor_places_match_handy_p33_and_p34(engine):
    table = engine["VICTOR_PLACES_VALUES"]
    assert table[_scheme(table, 'Newer')] == HANDY_P33_IBN_EZRA_PLACES
    mashaallah = {h: (v[0] if isinstance(v, tuple) else v) for h, v in HANDY_P34_MASHAALLAH_PLACES.items()}
    assert table[_scheme(table, 'Older')] == mashaallah
    dorotheus = {h: (v[1] if isinstance(v, tuple) else v) for h, v in HANDY_P34_MASHAALLAH_PLACES.items()}
    for wheel in (HANDY_P33_IBN_EZRA_PLACES, mashaallah, dorotheus):
        assert sorted(wheel.values()) == list(range(1, 13))


def test_A_victor_worksheet_rows_and_columns_match_handy_p33(engine):
    # one arbitrary chart; only the sheet's shape and its two fixed rows are read
    lons = {'Saturn': 5.0, 'Jupiter': 40.0, 'Mars': 75.0, 'Sun': 110.0, 'Venus': 145.0, 'Mercury': 180.0, 'Moon': 215.0}
    pdata = {p: {'longitude': lon} for p, lon in lons.items()}
    result = engine["evaluate_victors"](pdata, 250.0, 285.0, 320.0, 'Diurnal',
                                        {'Day Lord': 'Saturn', 'Hour Lord': 'Jupiter'})
    page_rows = {'☉:': 'Sun', '☽:': 'Moon', 'ASC:': 'Ascendant', '⊗:': 'Lot of Fortune',
                 '☌/☍:': 'Prenatal Syzygy', 'Lord day (7)': 'Lord of the Day (7)',
                 'Lord hour (6)': 'Lord of the Hour (6)', 'Places': 'Places', 'Totals': 'Totals'}
    assert engine["WEIGHT_ORDER"] == [PLANET[g] for g in HANDY_P33_WORKSHEET_COLUMNS]
    for scheme in result.values():
        grid = scheme['grid']
        assert [r['Row'] for r in grid] == [page_rows[r] for r in HANDY_P33_WORKSHEET_ROWS]
        day, hour = grid[5], grid[6]
        assert {p: v for p, v in day.items() if p != 'Row' and v} == {'Saturn': '7'}
        assert {p: v for p, v in hour.items() if p != 'Row' and v} == {'Jupiter': '6'}


# ================================================================================
# 5. PN4_III2_TYPES: PN IV III.2, 10-17, Figure 66
# ================================================================================
# PN IV p. 296, read off PN4_p0296.jpg: row, distributor, partner, reading.
# The page's caption says "(III.1, 10-54)"; its own Reading column, the
# chapter heading and the engine all say III.2.
PN4_FIG66 = (
    ('#1', 'F', '--', 'III.2, 11, 18-24'),
    ('#2', 'I', '--', 'III.2, 12, 25-29'),
    ('#3', 'I', 'F', 'III.2, 13, 30-35'),
    ('#4', 'F', 'I', 'III.2, 14, 36-39'),
    ('#5', 'ambiguous mixture', '', 'III.2, 15, 40-43'),
    ('#6', 'I', 'I', 'III.2, 16, 44-48'),
    ('#7', 'F', 'F', 'III.2, 17, 49-54'),
)
_OF_NATURE = {'F': ('Jupiter', 'Venus'), 'I': ('Saturn', 'Mars'), '--': (None,)}


@pytest.mark.parametrize("row", PN4_FIG66, ids=[r[0] for r in PN4_FIG66])
def test_A_static_types_match_pn4_fig66(engine, row):
    tag, distributor, partner, reading = row
    n = int(tag[1:])
    _label, cite = engine["PN4_III2_TYPES"][n]
    assert re.findall(r'[\dIV.]+(?:-\d+)?', cite) == re.findall(r'[\dIV.]+(?:-\d+)?', reading)
    if distributor in _OF_NATURE:
        for d in _OF_NATURE[distributor]:
            for p in _OF_NATURE[partner]:
                if p != d:
                    assert engine["pn4_static_type"](d, p)[0] == n, (d, p)
    else:   # the ambiguous mixture turns on a condition and is never assigned by nature
        assert all(engine["pn4_static_type"](d, p)[0] != n
                   for d in ('Jupiter', 'Venus', 'Saturn', 'Mars') for p in (None, 'Jupiter', 'Venus', 'Saturn', 'Mars'))


@_needs(PN4)
def test_B_fig66_literal_matches_the_markdown():
    rows = _table_before(PN4.read_text(encoding="utf-8"), "Figure 66 (PN IV)")
    body = [tuple(r) for r in rows if r[0].startswith('#')]
    assert tuple(body) == PN4_FIG66


# ================================================================================
# 6. SAHL_FIXED_STARS: Dykes's star table at the end of On Nativities 2.2
# ================================================================================
# Sahl I pp. 391-392, read off SahlI_p0391.jpg and SahlI_p0392.jpg: number,
# scientific name, common name, Rhetorius (Ch. 58), Sahl, nature (Rhetorius).
# Footnote numbers are kept in the two mark columns, dropped from the names.
# Rows 18-19 print Jupiter-MERCURY and rows 20-24 Mars-MERCURY: the second
# glyph carries Mercury's horns, set beside the hornless Venus of rows 1-5, 27-30.
# Sahl's own sentences agree (2.2, 47, Sahl I p. 387: the two are of the
# complexion of Jupiter and Mercury; 2.2, 54, p. 388: the five of Mars and Mercury).
SAHL_I_STAR_TABLE = (
    (1, 'α Virgo', 'Spica', 'X', 'X', ('♀', '☿')),
    (2, 'α Lyra', 'Vega', 'X', 'X', ('♀', '☿')),
    (3, 'α Piscis Austrinus', 'Fomalhaut', 'X', 'X', ('♀', '☿')),
    (4, 'α Cygnus', 'Deneb Adige', 'X72', '', ('♀', '☿')),
    (5, 'α Corona Borealis', 'Alphecca', 'X', '(X)73', ('♀', '☿')),
    (6, 'α Leo', 'Regulus', 'X', 'X', ('♃', '♂')),
    (7, 'α Bootes', 'Arcturus', 'X', '', ('♃', '♂')),
    (8, 'α Aquila', 'Altair', 'X', 'X', ('♃', '♂')),
    (9, 'α Scorpio', 'Antares', 'X', 'X74', ('♃', '♂')),
    (10, 'α Canis Major', 'Sirius', 'X', 'X', ('♃', '♂')),
    (11, 'β Orion', 'Rigel', 'X', 'X', ('♃', '♄')),
    (12, 'ε Orion', 'Alnilam', 'X', 'X', ('♃', '♄')),
    (13, 'β Auriga', 'Menkalinan', 'X', '(X)75', ('♃', '♄')),
    (14, 'α Sagittarius', 'Rukbat', 'X', 'X', ('♃', '♄')),
    (15, 'β Perseus', 'Algol', 'X', 'X', ('♃', '♄')),
    (16, 'α Auriga', 'Capella', 'X', 'X', ('♃', '♄')),
    (17, 'β Gemini', 'Pollux', 'X', 'X', ('♂',)),
    (18, 'β Libra', 'Zuben Eschemali', 'X', 'X', ('♃', '☿')),
    (19, 'α Gemini', 'Castor', 'X', 'X', ('♃', '☿')),
    (20, 'γ Orion', 'Bellatrix', 'X', 'X', ('♂', '☿')),
    (21, 'α Canis Major', 'Procyon', 'X', 'X', ('♂', '☿')),
    (22, 'α Orion', 'Betelgeuse', 'X', 'X', ('♂', '☿')),
    (23, 'α Andromeda', 'Alpheratz', 'X', 'X', ('♂', '☿')),
    (24, 'β Pegasus', 'Scheat', 'X', 'X', ('♂', '☿')),
    (25, 'α Centaurus', 'Toliman', 'X', 'X', ('♀', '♃')),
    (26, 'θ Eridanus', 'Acamar', 'X', 'X', ('♀', '♃')),
    (27, 'β Leo', 'Denebola', 'X', 'X', ('♄', '♀')),
    (28, 'δ Leo', 'Zosma', 'X', 'X', ('♄', '♀')),
    (29, 'α Hydra', 'Alphard', 'X', 'X', ('♄', '♀')),
    (30, 'α Taurus', 'Aldebaran', 'X', 'X', ('♂', '♀')),
)
# T-02, ruled: the page prints Jupiter-Mercury for Zuben Eschemali and Castor (rows 18-19; Sahl 2.2, 47
# agrees); the engine and the markdown carried Jupiter-Venus.
# T-03, ruled: the page prints Mars-Mercury for Bellatrix, Procyon, Betelgeuse, Alpheratz and Scheat
# (rows 20-24; Sahl 2.2, 54 agrees); the engine and the markdown carried Mars-Venus.
# T-04, ruled: the page spells row 18 Zuben Eschemali (so does the markdown); the engine keeps the
# catalogue's Zuben Eschamali as its lookup key and shows the page's spelling.
_STAR_ROWS_IN_SAHL = [r for r in SAHL_I_STAR_TABLE if r[4]]
_ENGINE_NAME = {'Zuben Eschemali': 'Zuben Eschamali'}     # T-04: the engine's spelling, to pair the rows


def test_A_star_table_keeps_the_rows_sahl_carries_in_page_order(engine):
    names = [name for name, _nature in engine["SAHL_FIXED_STARS"]]
    assert names == [_ENGINE_NAME.get(r[2], r[2]) for r in _STAR_ROWS_IN_SAHL]


def _star_param(row):
    return pytest.param(row, id=row[2])


@pytest.mark.parametrize("row", [_star_param(r) for r in _STAR_ROWS_IN_SAHL])
def test_A_star_nature_matches_the_page(engine, row):
    nature = dict(engine["SAHL_FIXED_STARS"])[_ENGINE_NAME.get(row[2], row[2])]
    assert tuple(GLYPH[p] for p in nature.split(' (')[0].split('-')) == row[5]
    # the engine's notes cite the footnotes the Sahl column prints
    for fn in ('73', '74', '75'):
        assert (f'fn {fn}' in nature) == row[4].endswith(fn)


@pytest.mark.parametrize("row", [pytest.param(r, id=r[2]) for r in _STAR_ROWS_IN_SAHL])
def test_A_star_name_is_the_page_spelling(engine, row):
    """The name a reader sees: the lookup key through FIXED_STAR_PAGE_NAME."""
    i = _STAR_ROWS_IN_SAHL.index(row)
    key = engine["SAHL_FIXED_STARS"][i][0]
    assert engine["FIXED_STAR_PAGE_NAME"].get(key, key) == row[2]


_CONSTELLATION = {'Virgo': 'Vir', 'Lyra': 'Lyr', 'Piscis Austrinus': 'PsA', 'Cygnus': 'Cyg', 'Corona Borealis': 'CrB',
                  'Leo': 'Leo', 'Bootes': 'Boo', 'Aquila': 'Aql', 'Scorpio': 'Sco', 'Canis Major': 'CMa',
                  'Orion': 'Ori', 'Auriga': 'Aur', 'Sagittarius': 'Sgr', 'Perseus': 'Per', 'Gemini': 'Gem',
                  'Libra': 'Lib', 'Andromeda': 'And', 'Pegasus': 'Peg', 'Centaurus': 'Cen', 'Eridanus': 'Eri',
                  'Hydra': 'Hya', 'Taurus': 'Tau'}
_LETTER = {'α': 'al', 'β': 'be', 'γ': 'ga', 'δ': 'de', 'ε': 'ep', 'θ': 'th'}


def test_A_each_star_the_engine_looks_up_is_the_star_the_page_identifies(engine):
    """The shipped catalogue resolves each engine name to a Bayer designation;
    it must be the page's scientific name. Fn 77 on the same page warns
    against taking Achernar for Acamar. Row 21 prints 'α Canis Major' for
    Procyon, which is alpha Canis MINORIS (row 10's alpha Canis Major is
    Sirius): the page's slip, recorded in the report; the common name rules."""
    catalogue = {}
    for line in EPHE_STARS.read_text(encoding="utf-8", errors="replace").splitlines():
        if line and not line.startswith('#') and ',' in line:
            name, code = [f.strip() for f in line.split(',')[:2]]
            catalogue.setdefault(name, code)
    for row in _STAR_ROWS_IN_SAHL:
        name = _ENGINE_NAME.get(row[2], row[2])
        letter, constellation = row[1].split(' ', 1)
        expected = _LETTER[letter] + ('CMi' if row[2] == 'Procyon' else _CONSTELLATION[constellation])
        assert re.sub(r'-\d', '', catalogue[name]) == expected, (name, catalogue[name], row[1])


def _star_table_rows(text):
    lines = text.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith('| Scientific name'))
    stop = next(i for i, l in enumerate(lines) if i > start and l.startswith('**Comment by Dykes.**'))
    out = []
    for line in lines[start:stop]:
        m = re.match(r'\|\s*(\d+)\.\s', line)
        if not m:
            continue
        name_cells = _cells(line, footnotes=False)
        mark_cells = _cells(line, footnotes=True)
        number, designation = name_cells[0].split('. ', 1)
        out.append((int(number), designation, name_cells[1], mark_cells[2], mark_cells[3], _glyphs(mark_cells[4])))
    return out


def _star_md_param(row):
    return pytest.param(row, id=f"{row[0]}-{row[2]}")


@_needs(SAHL_NAT)
@pytest.mark.parametrize("row", [_star_md_param(r) for r in SAHL_I_STAR_TABLE])
def test_B_star_table_row_matches_the_markdown(row):
    md = {r[0]: r for r in _star_table_rows(SAHL_NAT.read_text(encoding="utf-8"))}
    assert sorted(md) == list(range(1, 31))
    assert md[row[0]] == row


# ================================================================================
# 7. PN4_AGES_OF_MAN: PN IV I.8, 10-26, Figure 53
# ================================================================================
# PN IV p. 169, read off PN4_p0169.jpg: planet, years, ages, period of life.
PN4_FIG53 = (
    ('☽', 4, '0-3', 'Upbringing'),
    ('☿', 10, '4-13', 'End of childhood'),
    ('♀', 8, '14-21', 'Beginning of youth'),
    ('☉', 19, '22-40', 'End of youth'),
    ('♂', 15, '41-55', 'Beginning of maturity'),
    ('♃', 12, '56-67', 'Maturity, transition to old age'),
    ('♄', 30, '68-97', 'Old age'),
)


def test_A_ages_of_man_match_pn4_fig53(engine):
    assert engine["PN4_AGES_OF_MAN"] == tuple((PLANET[g], y, label) for g, y, _a, label in PN4_FIG53)


@pytest.mark.parametrize("glyph, years, ages, label", PN4_FIG53, ids=[PLANET[r[0]] for r in PN4_FIG53])
def test_A_ages_column_is_where_the_engine_puts_each_age(engine, glyph, years, ages, label):
    lo, hi = map(int, ages.split('-'))
    assert hi - lo + 1 == years
    for age in (lo, hi + 0.99):
        got = engine["pn4_age_of_man"](age)
        assert (got['planet'], got['from'], got['label']) == (PLANET[glyph], lo, label)
    # Saturn's age is open-ended in the engine by I.8, 25 (a reading of the
    # prose, not a cell): the others end where the figure ends them
    if glyph != '♄':
        assert engine["pn4_age_of_man"](lo)['to'] == hi + 1


@_needs(PN4)
@_needs(PN4_FIXED / "p169_ages_fixed.md")
def test_B_fig53_literal_matches_the_markdown():
    for which, rows in _pn4_copies("Figure 53 (PN IV)", "p169_ages_fixed.md"):
        assert tuple((g, int(y), a, l) for g, y, a, l in rows[1:]) == PN4_FIG53, which


# ================================================================================
# 8. EGYPTIAN_TERMS: Handy p. 1; Gr. Intr. V.9, Figure 47; PN IV Figure 23
# ================================================================================
# Handy p. 1, "Table of Egyptian bounds" (course PDF): lord, first and last
# whole degree of each printed span ("♃ 0°-5°59'" -> ('♃', 0, 5)).
HANDY_P1_BOUNDS = {
    '♈': (('♃', 0, 5), ('♀', 6, 11), ('☿', 12, 19), ('♂', 20, 24), ('♄', 25, 29)),
    '♉': (('♀', 0, 7), ('☿', 8, 13), ('♃', 14, 21), ('♄', 22, 26), ('♂', 27, 29)),
    '♊': (('☿', 0, 5), ('♃', 6, 11), ('♀', 12, 16), ('♂', 17, 23), ('♄', 24, 29)),
    '♋': (('♂', 0, 6), ('♀', 7, 12), ('☿', 13, 18), ('♃', 19, 25), ('♄', 26, 29)),
    '♌': (('♃', 0, 5), ('♀', 6, 10), ('♄', 11, 17), ('☿', 18, 23), ('♂', 24, 29)),
    '♍': (('☿', 0, 6), ('♀', 7, 16), ('♃', 17, 20), ('♂', 21, 27), ('♄', 28, 29)),
    '♎': (('♄', 0, 5), ('☿', 6, 13), ('♃', 14, 20), ('♀', 21, 27), ('♂', 28, 29)),
    '♏': (('♂', 0, 6), ('♀', 7, 10), ('☿', 11, 18), ('♃', 19, 23), ('♄', 24, 29)),
    '♐': (('♃', 0, 11), ('♀', 12, 16), ('☿', 17, 20), ('♄', 21, 25), ('♂', 26, 29)),
    '♑': (('☿', 0, 6), ('♃', 7, 13), ('♀', 14, 21), ('♄', 22, 25), ('♂', 26, 29)),
    '♒': (('☿', 0, 6), ('♀', 7, 12), ('♃', 13, 19), ('♂', 20, 24), ('♄', 25, 29)),
    '♓': (('♀', 0, 11), ('♃', 12, 15), ('☿', 16, 18), ('♂', 19, 27), ('♄', 28, 29)),
}
# Gr. Intr. p. 287, read off GrIntr_p0287.jpg: lord and printed width above,
# span below ("♃6 / 0° - 5° 59'" -> ('♃', 6, 0, 5)).
GR_INTR_FIG47 = {
    '♈': (('♃', 6, 0, 5), ('♀', 6, 6, 11), ('☿', 8, 12, 19), ('♂', 5, 20, 24), ('♄', 5, 25, 29)),
    '♉': (('♀', 8, 0, 7), ('☿', 6, 8, 13), ('♃', 8, 14, 21), ('♄', 5, 22, 26), ('♂', 3, 27, 29)),
    '♊': (('☿', 6, 0, 5), ('♃', 6, 6, 11), ('♀', 5, 12, 16), ('♂', 7, 17, 23), ('♄', 6, 24, 29)),
    '♋': (('♂', 7, 0, 6), ('♀', 6, 7, 12), ('☿', 6, 13, 18), ('♃', 7, 19, 25), ('♄', 4, 26, 29)),
    '♌': (('♃', 6, 0, 5), ('♀', 5, 6, 10), ('♄', 7, 11, 17), ('☿', 6, 18, 23), ('♂', 6, 24, 29)),
    '♍': (('☿', 7, 0, 6), ('♀', 10, 7, 16), ('♃', 4, 17, 20), ('♂', 7, 21, 27), ('♄', 2, 28, 29)),
    '♎': (('♄', 6, 0, 5), ('☿', 8, 6, 13), ('♃', 7, 14, 20), ('♀', 7, 21, 27), ('♂', 2, 28, 29)),
    '♏': (('♂', 7, 0, 6), ('♀', 4, 7, 10), ('☿', 8, 11, 18), ('♃', 5, 19, 23), ('♄', 6, 24, 29)),
    '♐': (('♃', 12, 0, 11), ('♀', 5, 12, 16), ('☿', 4, 17, 20), ('♄', 5, 21, 25), ('♂', 4, 26, 29)),
    '♑': (('☿', 7, 0, 6), ('♃', 7, 7, 13), ('♀', 8, 14, 21), ('♄', 4, 22, 25), ('♂', 4, 26, 29)),
    '♒': (('☿', 7, 0, 6), ('♀', 6, 7, 12), ('♃', 7, 13, 19), ('♂', 5, 20, 24), ('♄', 5, 25, 29)),
    '♓': (('♀', 12, 0, 11), ('♃', 4, 12, 15), ('☿', 3, 16, 18), ('♂', 9, 19, 27), ('♄', 2, 28, 29)),
}
# PN IV p. 65, read off PN4_p0065.jpg: printed as Handy p. 1 prints it.
PN4_FIG23 = {
    '♈': (('♃', 0, 5), ('♀', 6, 11), ('☿', 12, 19), ('♂', 20, 24), ('♄', 25, 29)),
    '♉': (('♀', 0, 7), ('☿', 8, 13), ('♃', 14, 21), ('♄', 22, 26), ('♂', 27, 29)),
    '♊': (('☿', 0, 5), ('♃', 6, 11), ('♀', 12, 16), ('♂', 17, 23), ('♄', 24, 29)),
    '♋': (('♂', 0, 6), ('♀', 7, 12), ('☿', 13, 18), ('♃', 19, 25), ('♄', 26, 29)),
    '♌': (('♃', 0, 5), ('♀', 6, 10), ('♄', 11, 17), ('☿', 18, 23), ('♂', 24, 29)),
    '♍': (('☿', 0, 6), ('♀', 7, 16), ('♃', 17, 20), ('♂', 21, 27), ('♄', 28, 29)),
    '♎': (('♄', 0, 5), ('☿', 6, 13), ('♃', 14, 20), ('♀', 21, 27), ('♂', 28, 29)),
    '♏': (('♂', 0, 6), ('♀', 7, 10), ('☿', 11, 18), ('♃', 19, 23), ('♄', 24, 29)),
    '♐': (('♃', 0, 11), ('♀', 12, 16), ('☿', 17, 20), ('♄', 21, 25), ('♂', 26, 29)),
    '♑': (('☿', 0, 6), ('♃', 7, 13), ('♀', 14, 21), ('♄', 22, 25), ('♂', 26, 29)),
    '♒': (('☿', 0, 6), ('♀', 7, 12), ('♃', 13, 19), ('♂', 20, 24), ('♄', 25, 29)),
    '♓': (('♀', 0, 11), ('♃', 12, 15), ('☿', 16, 18), ('♂', 19, 27), ('♄', 28, 29)),
}


def _bounds_as_engine(spans):
    """(lord, first, last) spans -> the engine's [(upper limit, lord), ...]."""
    return [(last + 1, PLANET[lord]) for lord, _first, last in spans]


def test_fig47_widths_and_spans_agree_on_the_page():
    for sign, row in GR_INTR_FIG47.items():
        assert [w for _l, w, _a, _b in row] == [b - a + 1 for _l, _w, a, b in row], sign
        assert row[0][2] == 0 and row[-1][3] == 29 and all(row[i + 1][2] == row[i][3] + 1 for i in range(4)), sign


@pytest.mark.parametrize("witness", ['Handy p. 1', 'Gr. Intr. Fig. 47', 'PN IV Fig. 23'])
@pytest.mark.parametrize("sign", list(SIGN), ids=SIGNS)
def test_A_egyptian_bounds_match_each_printed_table(engine, witness, sign):
    table = {'Handy p. 1': HANDY_P1_BOUNDS, 'PN IV Fig. 23': PN4_FIG23,
             'Gr. Intr. Fig. 47': {s: tuple((l, a, b) for l, _w, a, b in r) for s, r in GR_INTR_FIG47.items()}}[witness]
    assert [tuple(t) for t in engine["EGYPTIAN_TERMS"][SIGN[sign]]] == _bounds_as_engine(table[sign])


@_needs(GR_INTR)
def test_B_fig47_literal_matches_the_markdown():
    rows = _table_before(GR_INTR.read_text(encoding="utf-8"), "Figure 47 (Gr. Intr.)")
    got = {}
    for lords, spans in zip(rows[0::2], rows[1::2]):
        got[lords[0]] = tuple((c[0], int(c[1:].strip()), *_span(s)) for c, s in zip(lords[1:], spans[1:]))
    assert got == GR_INTR_FIG47


@_needs(PN4)
@_needs(PN4_FIXED / "bounds_fixed.md")
def test_B_pn4_fig23_literal_matches_the_markdown():
    for which, rows in _pn4_copies("Figure 23 (PN IV)", "bounds_fixed.md"):
        got = {r[0]: tuple((c[0], *_span(c[1:].strip())) for c in r[1:]) for r in rows if r[0] in SIGN}
        assert got == PN4_FIG23, which


# ================================================================================
# 9. TRIPLICITY, SIGN_ELEMENT: Sahl I Introduction 1, Figure 4;
#    Gr. Intr. V.14, Figure 53; Handy p. 1
# ================================================================================
# Sahl I p. 44, read off SahlI_p0044.jpg: signs, day, night, partner.
SAHL_I_FIG4 = (('♈♌♐', '☉', '♃', '♄'), ('♉♍♑', '♀', '☽', '♂'), ('♊♎♒', '♄', '☿', '♃'), ('♋♏♓', '♀', '♂', '☽'))
# Gr. Intr. p. 295, read off GrIntr_p0295.jpg: signs, diurnal, nocturnal, partner.
GR_INTR_FIG53 = (('♈♌♐', '☉', '♃', '♄'), ('♉♍♑', '♀', '☽', '♂ (and ☿ when in ♍)'),
                 ('♊♎♒', '♄', '☿', '♃'), ('♋♏♓', '♀', '♂', '☽'))
# Handy p. 1, "Dorothean triplicity lords" (course PDF), rows and sign order as printed.
HANDY_P1_TRIPLICITY = (('♈♌♐', '☉', '♃', '♄'), ('♎♒♊', '♄', '☿', '♃'), ('♋♏♓', '♀', '♂', '☽'), ('♑♉♍', '♀', '☽', '♂'))


def _partner(cell, sign):
    """'♂ (and ☿ when in ♍)' -> Mercury in Virgo, Mars elsewhere."""
    m = re.fullmatch(r'(\S) \(and (\S) when in (\S)\)', cell)
    if m:
        return PLANET[m.group(2)] if SIGN[m.group(3)] == sign else PLANET[m.group(1)]
    return PLANET[cell]


@pytest.mark.parametrize("witness", ['Sahl I Fig. 4', 'Gr. Intr. Fig. 53', 'Handy p. 1'])
def test_A_triplicities_match_each_printed_table(engine, witness):
    table, source = {'Sahl I Fig. 4': (SAHL_I_FIG4, 'Sahl'), 'Gr. Intr. Fig. 53': (GR_INTR_FIG53, 'Great Introduction'),
                     'Handy p. 1': (HANDY_P1_TRIPLICITY, 'Sahl')}[witness]
    elements = set()
    for signs, day, night, partner in table:
        row_elements = {engine["SIGN_ELEMENT"][SIGN[g]] for g in signs}
        assert len(row_elements) == 1, signs       # the row is one triplicity
        elements |= row_elements
        for g in signs:
            got = engine["triplicity_rulers"](SIGN[g], table=source)
            assert (got['Day'], got['Night'], got['Participating']) == (PLANET[day], PLANET[night], _partner(partner, SIGN[g]))
    assert len(elements) == 4


def test_A_the_common_triplicity_table_is_sahls_fig4(engine):
    for signs, day, night, partner in SAHL_I_FIG4:
        assert engine["TRIPLICITY"][engine["SIGN_ELEMENT"][SIGN[signs[0]]]] == \
            {'Day': PLANET[day], 'Night': PLANET[night], 'Participating': PLANET[partner]}


def _triplicity_md(rows):
    return tuple((r[0].replace(' ', ''), r[1], r[2], r[3]) for r in rows if r[0][:1] in SIGN)


@_needs(SAHL_INTRO)
def test_B_sahl_fig4_literal_matches_the_markdown():
    assert _triplicity_md(_table_before(SAHL_INTRO.read_text(encoding="utf-8"), "Figure 4 (Sahl I)")) == SAHL_I_FIG4


@_needs(GR_INTR)
def test_B_gr_intr_fig53_literal_matches_the_markdown():
    assert _triplicity_md(_table_before(GR_INTR.read_text(encoding="utf-8"), "Figure 53 (Gr. Intr.)")) == GR_INTR_FIG53


# ================================================================================
# 10. CHALDEAN_ORDER (the faces): Gr. Intr. V.15, Figure 54
# ================================================================================
# Gr. Intr. p. 296, read off GrIntr_p0296.jpg: the three faces of each sign.
GR_INTR_FIG54 = {
    '♈': ('♂', '☉', '♀'), '♉': ('☿', '☽', '♄'), '♊': ('♃', '♂', '☉'), '♋': ('♀', '☿', '☽'),
    '♌': ('♄', '♃', '♂'), '♍': ('☉', '♀', '☿'), '♎': ('☽', '♄', '♃'), '♏': ('♂', '☉', '♀'),
    '♐': ('☿', '☽', '♄'), '♑': ('♃', '♂', '☉'), '♒': ('♀', '☿', '☽'), '♓': ('♄', '♃', '♂'),
}


@pytest.mark.parametrize("sign", list(SIGN), ids=SIGNS)
def test_A_faces_match_gr_intr_fig54(engine, sign):
    i = SIGNS.index(SIGN[sign])
    assert [engine["get_essential_rulers"](i * 30 + 10 * k + 5)['face'] for k in range(3)] == \
        [PLANET[g] for g in GR_INTR_FIG54[sign]]


def test_A_chaldean_order_is_the_first_seven_faces_of_fig54(engine):
    faces = [PLANET[g] for s in SIGN for g in GR_INTR_FIG54[s]]
    assert engine["CHALDEAN_ORDER"] == faces[:7]
    assert faces == faces[:7] * 5 + faces[:1]          # the page repeats the seven, 36 faces


@_needs(GR_INTR)
def test_B_fig54_literal_matches_the_markdown():
    rows = _table_before(GR_INTR.read_text(encoding="utf-8"), "Figure 54 (Gr. Intr.)")
    assert {r[0]: tuple(r[1:]) for r in rows if r[0] in SIGN} == GR_INTR_FIG54


# ================================================================================
# 11. BRIGHTNESS_DEGREES: Gr. Intr. V.20, Figures 60-61
# ================================================================================
# Gr. Intr. p. 305, read off GrIntr_p0305.jpg: code -> (class number, name).
GR_INTR_FIG60 = {'B': (1, 'Bright'), 'K': (2, 'Dusky'), 'E': (3, 'Empty'), 'D': (4, 'Dark')}
# Gr. Intr. p. 306, read off GrIntr_p0306.jpg: printed width and code above,
# span below ("3K / 0°-2°59'" -> ('3K', 0, 2)).
GR_INTR_FIG61 = {
    '♈': (('3K', 0, 2), ('5D', 3, 7), ('8K', 8, 15), ('4B', 16, 19), ('4D', 20, 23), ('5B', 24, 28), ('1D', 29, 29)),
    '♉': (('3K', 0, 2), ('7D', 3, 9), ('2E', 10, 11), ('8B', 12, 19), ('5E', 20, 24), ('3B', 25, 27), ('2K', 28, 29)),
    '♊': (('7B', 0, 6), ('3K', 7, 9), ('5B', 10, 14), ('2E', 15, 16), ('6B', 17, 22), ('7K', 23, 29)),
    '♋': (('7K', 0, 6), ('5B', 7, 11), ('2K', 12, 13), ('4B', 14, 17), ('2D', 18, 19), ('8B', 20, 27), ('2D', 28, 29)),
    '♌': (('7B', 0, 6), ('3K', 7, 9), ('6D', 10, 15), ('5E', 16, 20), ('9B', 21, 29)),
    '♍': (('5K', 0, 4), ('4B', 5, 8), ('2E', 9, 10), ('6B', 11, 16), ('4D', 17, 20), ('7B', 21, 27), ('2E', 28, 29)),
    '♎': (('5B', 0, 4), ('5K', 5, 9), ('8B', 10, 17), ('3K', 18, 20), ('7B', 21, 27), ('2E', 28, 29)),
    '♏': (('3K', 0, 2), ('5B', 3, 7), ('6E', 8, 13), ('6B', 14, 19), ('2D', 20, 21), ('5B', 22, 26), ('3K', 27, 29)),
    '♐': (('9B', 0, 8), ('3K', 9, 11), ('7B', 12, 18), ('4D', 19, 22), ('7K', 23, 29)),
    '♑': (('7K', 0, 6), ('3B', 7, 9), ('5D', 10, 14), ('4B', 15, 18), ('2K', 19, 20), ('4E', 21, 24), ('5B', 25, 29)),
    '♒': (('4D', 0, 3), ('5B', 4, 8), ('4K', 9, 12), ('8B', 13, 20), ('4E', 21, 24), ('5B', 25, 29)),
    '♓': (('6K', 0, 5), ('6B', 6, 11), ('6K', 12, 17), ('4B', 18, 21), ('3E', 22, 24), ('3B', 25, 27), ('2K', 28, 29)),
}


def test_fig61_widths_and_spans_agree_on_the_page():
    for sign, row in GR_INTR_FIG61.items():
        assert all(int(code[:-1]) == b - a + 1 for code, a, b in row), sign
        assert row[0][1] == 0 and row[-1][2] == 29 and all(row[i + 1][1] == row[i][2] + 1 for i in range(len(row) - 1))


@pytest.mark.parametrize("sign", list(SIGN), ids=SIGNS)
def test_A_brightness_matches_gr_intr_figs_60_61(engine, sign):
    assert [tuple(t) for t in engine["BRIGHTNESS_DEGREES"][SIGN[sign]]] == \
        [(a, b, GR_INTR_FIG60[code[-1]][1]) for code, a, b in GR_INTR_FIG61[sign]]


@_needs(GR_INTR)
def test_B_figs_60_61_literals_match_the_markdown():
    text = GR_INTR.read_text(encoding="utf-8")
    fig60 = _table_before(text, "Figure 60 (Gr. Intr.)")
    assert {r[1]: (int(r[0][1]), r[0].split('] ')[1]) for r in fig60} == GR_INTR_FIG60
    rows = _table_before(text, "Figure 61 (Gr. Intr.)")
    got = {}
    for codes, spans in zip(rows[0::2], rows[1::2]):
        got[codes[0].split()[0]] = tuple((c, *_span(s)) for c, s in zip(codes[1:], spans[1:]) if c)
    assert got == GR_INTR_FIG61


# ================================================================================
# 12. NOBILITY_DEGREES: Sahl, On Nativities 1.38, 41, Figure 57
# ================================================================================
# Sahl I p. 378, read off SahlI_p0378.jpg: the degrees as printed ("19°"),
# which the engine reads as ordinals (its comment says why). The page's
# caption prints "Ch. 1.28, 41", the book's misprint for 1.38.
SAHL_I_FIG57 = {'♈': (19,), '♉': (3,), '♊': (13,), '♋': (1, 13, 14, 15), '♌': (5, 7),
                '♍': (2, 13, 20), '♑': (12, 13, 20), '♒': (12, 20)}


def test_A_nobility_degrees_match_sahl_fig57(engine):
    assert engine["NOBILITY_DEGREES"] == {SIGN[s]: list(d) for s, d in SAHL_I_FIG57.items()}


@_needs(SAHL_NAT)
def test_B_fig57_literal_matches_the_markdown():
    rows = _table_before(SAHL_NAT.read_text(encoding="utf-8"), "Figure 57 (Sahl I)")
    assert {r[0]: tuple(int(d) for d in re.findall(r'\d+', r[1])) for r in rows} == SAHL_I_FIG57


# ================================================================================
# 13. PLANETARY_ORBS: Gr. Intr. VII.3, 6-11, Figure 105
# ================================================================================
# Gr. Intr. p. 424, read off GrIntr_p0424.jpg: "Degrees on both sides".
GR_INTR_FIG105 = (('☉', 15), ('☽', 12), ('♄♃', 9), ('♂', 8), ('☿♀', 7))


def test_A_planetary_orbs_match_gr_intr_fig105(engine):
    assert engine["PLANETARY_ORBS"] == {PLANET[g]: float(d) for glyphs, d in GR_INTR_FIG105 for g in glyphs}


@_needs(GR_INTR)
def test_B_fig105_literal_matches_the_markdown():
    rows = _table_before(GR_INTR.read_text(encoding="utf-8"), "Figure 105 (Gr. Intr.)")
    assert tuple((r[0], int(r[1].rstrip('°'))) for r in rows[1:]) == GR_INTR_FIG105


# ================================================================================
# 14. SOLAR_BURNED_ORB, SOLAR_RAYS_ORB, SOLAR_SETTING_DEGREES: Gr. Intr. VII.2
#     prose; Dykes's table at the head of On Nativities 1.22
# ================================================================================
# Gr. Intr. VII.2: the degree figures each sentence prints, in order. Read off
# GrIntr_p0414.jpg (11, 13), GrIntr_p0417.jpg (30, 31, 34), GrIntr_p0418.jpg
# (37, 40, 44), GrIntr_p0419.jpg (47, 48, 51, 52), GrIntr_p0422.jpg (60, 61),
# GrIntr_p0423.jpg (72, 73). Superiors 11-34, inferiors 35-57, Moon 58-74.
GR_INTR_VII2_DEGREES = {
    11: (6, 10),        # Saturn and Jupiter burned within 6, Mars within 10 (east)
    13: (15, 18),       # under the rays until 15 (Saturn, Jupiter), 18 (Mars) (east)
    30: (60, 22, 18),   # westernizing from 60 until 22 (Saturn, Jupiter), 18 (Mars)
    31: (15,),          # "in the degrees of setting" until 15
    34: (6, 10),        # under the rays until 6 (Saturn, Jupiter), 10 (Mars), then burned (west)
    37: (7,),           # inferiors burned up to 7, leaving the Sun into the east
    40: (7, 12),        # past burning at a full 7; under the rays up to 12
    44: (12, 6),        # direct in the east: under the rays from 12 until 6
    47: (7,),           # burned until 7 in the west
    48: (15,),          # under the rays until 15
    51: (15,),          # retrograde in the west, back to 15
    52: (7,),           # under the rays until 7
    60: (6,),           # the Moon burned until 6 (west)
    61: (12,),          # under the rays until 12 in the west
    72: (12,),          # until 12 in the east
    73: (6,),           # under the rays until 6 (east)
}
# Sahl I p. 304, read off SahlI_p0304.jpg: westernizes at, considered
# western, considered eastern, easternizes at.
SAHL_I_NAT_1_22 = (('♄', 15, 22, 6, 15), ('♃', 15, 22, 6, 15), ('♂', 18, 22, 15, 18))


def test_A_solar_orbs_match_gr_intr_vii2(engine):
    s = GR_INTR_VII2_DEGREES
    burned, rays, setting = engine["SOLAR_BURNED_ORB"], engine["SOLAR_RAYS_ORB"], engine["SOLAR_SETTING_DEGREES"]
    for i, planets in enumerate((('Saturn', 'Jupiter'), ('Mars',))):
        for p in planets:
            assert burned[p] == (s[11][i], s[34][i]), p
            assert rays[p] == (s[13][i], s[31][0]), p
            assert setting[p] == s[30][1 + i], p
    for p in ('Venus', 'Mercury'):
        assert s[37][0] == s[40][0] and s[47][0] == s[52][0] and s[40][1] == s[44][0] and s[48][0] == s[51][0]
        assert burned[p] == (s[40][0], s[47][0]) and rays[p] == (s[44][0], s[48][0]), p
    assert engine["INFERIOR_DIRECT_EASTERN_BURNED"] == s[44][1]
    assert burned['Moon'] == (s[73][0], s[60][0]) and rays['Moon'] == (s[72][0], s[61][0])
    assert engine["MOON_RAYS_ORB"] == s[61][0]


class _Reading:
    """Set one of the engine's readings for this thread, then restore it."""

    def __init__(self, engine, name, value):
        self.engine, self.name, self.value = engine, name, value

    def __enter__(self):
        run = self.engine['_RUN']
        self.previous = getattr(run, self.name, _Reading)
        self.engine['set_readings'](**{self.name: self.value})

    def __exit__(self, *exc):
        run = self.engine['_RUN']
        if self.previous is _Reading:
            delattr(run, self.name)
        else:
            setattr(run, self.name, self.previous)


@pytest.mark.parametrize("row", SAHL_I_NAT_1_22, ids=[PLANET[r[0]] for r in SAHL_I_NAT_1_22])
def test_A_on_nativities_1_22_table_is_what_the_engine_reads_for_sahl(engine, row):
    glyph, westernizes, western, eastern, easternizes = row
    planet = PLANET[glyph]
    got = engine["sahl_eastern_1_22"](planet, 100.0, 130.0, 0.1)
    assert (got.level1.threshold, got.level2.threshold) == (eastern, easternizes)
    # The western columns are the engine's Mars-18 reading (decision D-15:
    # the switch carries Dykes's table; the default is Gr. Intr. VII.2, 30-31)
    with _Reading(engine, 'MARS_WEST_RAYS_18', True):
        assert (engine["solar_rays_orb"](planet)[1], engine["solar_setting_degree"](planet)) == (westernizes, western)
    with _Reading(engine, 'MARS_WEST_RAYS_18', False):
        default = (engine["solar_rays_orb"](planet)[1], engine["solar_setting_degree"](planet))
        assert default == ((GR_INTR_VII2_DEGREES[31][0], GR_INTR_VII2_DEGREES[30][2]) if planet == 'Mars'
                           else (westernizes, western))


@_needs(GR_INTR)
def test_B_vii2_degree_figures_match_the_markdown():
    prose = _chapter(GR_INTR.read_text(encoding="utf-8"), "### Chapter VII.2", "### Chapter VII.3")
    sentences = _sentences(prose, set(GR_INTR_VII2_DEGREES))
    assert {n: _degrees(sentences[n]) for n in GR_INTR_VII2_DEGREES} == GR_INTR_VII2_DEGREES


@_needs(SAHL_NAT)
def test_B_on_nativities_1_22_table_matches_the_markdown():
    lines = SAHL_NAT.read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith('| Westernizes'))
    rows = []
    for line in lines[start + 1:]:
        if not line.startswith('|'):
            break
        if not _is_rule(line):
            c = _cells(line)
            rows.append((c[2], *(int(x.rstrip('°')) for x in (c[0], c[1], c[3], c[4]))))
    assert tuple(rows) == SAHL_I_NAT_1_22


# ================================================================================
# 15. GOOD_PLACE_SCHEMES: Sahl I Introduction 2, 31-44, Figures 5-7;
#     Introduction 3, 78; On Choices 9, 12
# ================================================================================
# Sahl I p. 47, read off SahlI_p0047.jpg: Intro 2, 31 (stakes), 33 (what
# follows them), 35 (falling from them), as the sentences name the places.
SAHL_I_INTRO_2_31_35 = {'stakes': (1, 4, 7, 10), 'what follows the stakes': (2, 5, 8, 11),
                        'falling from the stakes': (3, 6, 9, 12)}
# Sahl I p. 48, read off SahlI_p0048.jpg: the grey wedges of Figures 5 and 6
# (images only in the corpus: no Test B).
SAHL_I_FIG5_GREY = frozenset({1, 2, 4, 5, 7, 8, 10, 11})
SAHL_I_FIG6_GREY = frozenset({1, 4, 5, 7, 9, 10, 11})
# Sahl I p. 49, read off SahlI_p0049.jpg: Figure 7, Good / Middle / Bad.
SAHL_I_FIG7 = {'Sahl': ((1, 10, 7, 4, 11, 9, 5), (3, 2), (8, 6, 12)),
               'Carmen I.5': ((1, 10, 11, 5, 7, 4, 9), (3, 2), (8, 6, 12))}
# Sahl I p. 66, read off SahlI_p0066.jpg: Intro 3, 78 with fn 92, "only six
# good places", the seven of Figure 6 less the ninth.
SAHL_I_INTRO_3_78_SIX = SAHL_I_FIG6_GREY - {9}
# Sahl I p. 222, read off SahlI_p0222.jpg: On Choices 9, 12, the Sun's
# excellent places in the order printed.
SAHL_I_CHOICES_9_12 = (1, 11, 10)


def _schemes(engine):
    table = engine["GOOD_PLACE_SCHEMES"]
    pick = lambda prefix: next(v for k, v in table.items() if k.startswith(prefix))
    return pick('Eight places'), pick('Seven praised'), pick('Six excellent'), pick('Excellent places for the Sun')


def test_A_good_place_schemes_match_sahls_figures_and_sentences(engine):
    eight, seven, six, sun = _schemes(engine)
    assert {k: set(v) for k, v in eight.items()} == {k: set(v) for k, v in SAHL_I_INTRO_2_31_35.items()}
    assert set(eight['stakes']) | set(eight['what follows the stakes']) == SAHL_I_FIG5_GREY
    assert tuple(seven) == SAHL_I_FIG7['Sahl'][0] and set(seven) == SAHL_I_FIG6_GREY
    assert set(six) == SAHL_I_INTRO_3_78_SIX == engine["EXCELLENT_PLACES"]
    assert tuple(sun) == SAHL_I_CHOICES_9_12


@_needs(SAHL_INTRO)
def test_B_fig7_literal_matches_the_markdown():
    rows = _table_before(SAHL_INTRO.read_text(encoding="utf-8"), "Figure 7 (Sahl I)")
    header = rows[0]
    cuts = [i for i, c in enumerate(header) if c in ('Good', 'Middle', 'Bad')] + [len(header)]
    got = {r[0]: tuple(tuple(int(x) for x in r[a:b]) for a, b in zip(cuts, cuts[1:])) for r in rows[1:]}
    assert got == SAHL_I_FIG7


_ORDINAL = {'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5, 'sixth': 6, 'seventh': 7, 'eighth': 8,
            'ninth': 9, 'tenth': 10, 'eleventh': 11, 'twelfth': 12}


@_needs(SAHL_INTRO)
def test_B_intro_2_31_35_as_the_markdown_words_them():
    prose = _chapter(SAHL_INTRO.read_text(encoding="utf-8"), "## [Chapter 2:]", "[On aspects")
    sentences = _sentences(prose, {31, 33, 35})
    got = {}
    for n, name in ((31, 'stakes'), (33, 'what follows the stakes'), (35, 'falling from the stakes')):
        places = [_ORDINAL[w] for w in re.findall(r'\b(' + '|'.join(_ORDINAL) + r')\b', sentences[n])]
        if 'sign of the Ascendant' in sentences[n]:
            places.append(1)
        got[name] = tuple(sorted(places))
    assert got == SAHL_I_INTRO_2_31_35


@_needs(SAHL_INTRO_CH3)
def test_B_intro_3_78_fn92_as_the_markdown_words_it():
    note = next(l for l in SAHL_INTRO_CH3.read_text(encoding="utf-8").splitlines() if l.startswith('<sup>92</sup>'))
    count, left_out = re.search(r'only (\w+) good places, by leaving out the (\w+)', note).groups()
    assert SAHL_I_FIG6_GREY - SAHL_I_INTRO_3_78_SIX == {_ORDINAL[left_out]}
    assert (count, len(SAHL_I_INTRO_3_78_SIX)) == ('six', 6)


@_needs(SAHL_CHOICES)
def test_B_choices_9_12_as_the_markdown_words_it():
    text = SAHL_CHOICES.read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if l.startswith('**12** And') and 'travel was to kings' in l)
    clause = _norm(line).split('excellent place, ', 1)[1].split('.')[0]
    words = re.findall(r'\b(Ascendant|' + '|'.join(_ORDINAL) + r')\b', clause)
    assert tuple(1 if w == 'Ascendant' else _ORDINAL[w] for w in words) == SAHL_I_CHOICES_9_12


# ================================================================================
# 16. DOMICILES, EXALTATIONS, DETRIMENTS, FALLS: Handy p. 1
# ================================================================================
# Handy p. 1, "Houses (inner), Exaltations (outer)" (course PDF): sign ->
# (house lord on the inner ring, exaltation lord on the outer ring or None).
HANDY_P1_WHEEL = {
    '♈': ('♂', '☉'), '♉': ('♀', '☽'), '♊': ('☿', None), '♋': ('☽', '♃'),
    '♌': ('☉', None), '♍': ('☿', '☿'), '♎': ('♀', '♄'), '♏': ('♂', None),
    '♐': ('♃', None), '♑': ('♄', '♂'), '♒': ('♄', None), '♓': ('♃', '♀'),
}
# The page prints no detriment or fall. Falls: Gr. Intr. V.5, 11 (p. 268,
# GrIntr_p0268.jpg), the fall is in the sign opposite the exaltation.
# Detriments: Gr. Intr. p. 264, fn 27 (GrIntr_p0264.jpg), the detriment is
# the opposite of the sign a planet rules.


@pytest.mark.parametrize("planet", list(PLANET.values()))
def test_A_dignities_match_handy_p1_wheel(engine, planet):
    houses = {SIGN[s] for s, (lord, _ex) in HANDY_P1_WHEEL.items() if PLANET[lord] == planet}
    exalted = {SIGN[s] for s, (_lord, ex) in HANDY_P1_WHEEL.items() if ex and PLANET[ex] == planet}
    assert set(engine["DOMICILES"][planet]) == houses
    assert set(engine["EXALTATIONS"][planet]) == exalted
    assert set(engine["DETRIMENTS"][planet]) == {_opposite(s) for s in houses}
    assert set(engine["FALLS"][planet]) == {_opposite(s) for s in exalted}


# ================================================================================
# 17. AVERAGE_DAILY_MOTION: Handy p. 2
# ================================================================================
# Handy p. 2, "Planetary periods, years, and average daily speeds" (course
# PDF): degrees, minutes, seconds. Mercury's cell prints a degree sign where
# the seconds mark belongs ("01° 23' 00°").
HANDY_P2_DAILY_SPEEDS = {'♄': (0, 2, 1), '♃': (0, 4, 59), '♂': (0, 31, 27), '☉': (0, 59, 8),
                         '♀': (1, 12, 0), '☿': (1, 23, 0), '☽': (13, 10, 36)}
# T-05, ruled: Handy p. 2 prints the Moon's average daily speed as 13° 10' 36" (13.1767 to four places);
# the engine had carried 13.1764 (13° 10' 35").


@pytest.mark.parametrize("glyph", [pytest.param(g, id=PLANET[g])
                                   for g in HANDY_P2_DAILY_SPEEDS])
def test_A_average_daily_motion_is_handy_p2_rounded_as_the_engine_writes_it(engine, glyph):
    """The engine keeps decimal degrees; the page prints d m s. Each engine
    value must be the page's value rounded to as many decimals as the engine
    itself writes."""
    value = engine["AVERAGE_DAILY_MOTION"][PLANET[glyph]]
    places = len(repr(value).split('.')[1])
    d, m, s = HANDY_P2_DAILY_SPEEDS[glyph]
    assert value == round(d + m / 60 + s / 3600, places)


# ================================================================================
# 18. DAY_LORD_BY_WEEKDAY, CHALDEAN_HOUR_ORDER: Handy pp. 33, 35; PN IV Figure 45
# ================================================================================
# Handy p. 33, "Lords of the days" (course PDF).
HANDY_P33_LORDS_OF_THE_DAYS = (('Sunday', '☉'), ('Monday', '☽'), ('Tuesday', '♂'), ('Wednesday', '☿'),
                               ('Thursday', '♃'), ('Friday', '♀'), ('Saturday', '♄'))
# Handy p. 35, "Planetary hours and days" (course PDF), and PN IV p. 123,
# Figure 45, read off PN4_p0123.jpg: the two print the same 168 cells. Each
# string is one hour's row, Sunday to Saturday.
PLANETARY_HOURS = {
    'diurnal': ('☉☽♂☿♃♀♄', '♀♄☉☽♂☿♃', '☿♃♀♄☉☽♂', '☽♂☿♃♀♄☉', '♄☉☽♂☿♃♀', '♃♀♄☉☽♂☿',
                '♂☿♃♀♄☉☽', '☉☽♂☿♃♀♄', '♀♄☉☽♂☿♃', '☿♃♀♄☉☽♂', '☽♂☿♃♀♄☉', '♄☉☽♂☿♃♀'),
    'nocturnal': ('♃♀♄☉☽♂☿', '♂☿♃♀♄☉☽', '☉☽♂☿♃♀♄', '♀♄☉☽♂☿♃', '☿♃♀♄☉☽♂', '☽♂☿♃♀♄☉',
                  '♄☉☽♂☿♃♀', '♃♀♄☉☽♂☿', '♂☿♃♀♄☉☽', '☉☽♂☿♃♀♄', '♀♄☉☽♂☿♃', '☿♃♀♄☉☽♂'),
}
_WEEKDAY = {'Sunday': 6, 'Monday': 0, 'Tuesday': 1, 'Wednesday': 2, 'Thursday': 3, 'Friday': 4, 'Saturday': 5}


def test_A_day_lords_match_handy_p33_and_the_first_hour_of_p35(engine):
    assert engine["DAY_LORD_BY_WEEKDAY"] == {_WEEKDAY[day]: PLANET[g] for day, g in HANDY_P33_LORDS_OF_THE_DAYS}
    assert PLANETARY_HOURS['diurnal'][0] == ''.join(g for _d, g in HANDY_P33_LORDS_OF_THE_DAYS)


def test_A_chaldean_hour_order_is_saturdays_column_of_p35(engine):
    saturday = [row[6] for row in PLANETARY_HOURS['diurnal'][:7]]
    assert engine["CHALDEAN_HOUR_ORDER"] == [PLANET[g] for g in saturday]


def test_A_the_engine_gives_every_cell_of_the_planetary_hours_table(engine, monkeypatch):
    """calculate_chronocrats itself, driven through all 168 cells: sunrise at
    06:00 and sunset at 18:00 UT every day, so each temporal hour is one
    civil hour, and the moment is the middle of the hour wanted. Nocturnal
    hours 7-12 fall after midnight, in the next calendar day, and must still
    take the previous sunrise's day lord. The function's cache is emptied
    before and after, so no faked result is served to or kept from anyone,
    and the coordinates are ones no other test uses."""
    def sun_event(jd_start, _lat, _lon, want_rise):
        midnight = int(jd_start - 0.5) + 0.5 - 1
        events = [midnight + k + (0.25 if want_rise else 0.75) for k in range(4)]
        return next(e for e in events if e >= jd_start)
    chronocrats = engine["calculate_chronocrats"]
    monkeypatch.setitem(engine, "_find_sun_event", sun_event)
    sunday = 2451545.5               # 2000-01-02 00:00 UT, a Sunday
    assert date(2000, 1, 2).weekday() == _WEEKDAY['Sunday']
    chronocrats.clear()
    try:
        for half, first in (('diurnal', 0.25), ('nocturnal', 0.75)):
            for h, row in enumerate(PLANETARY_HOURS[half], start=1):
                for d, glyph in enumerate(row):
                    jd = sunday + d + first + (h - 0.5) / 24.0
                    got = chronocrats(jd, 1.2345, 6.789, 0.0, 0.0)
                    assert got['Approximate'] is False
                    assert got['Hour Lord'] == PLANET[glyph], (half, h, HANDY_P33_LORDS_OF_THE_DAYS[d][0])
                    assert got['Day Lord'] == PLANET[PLANETARY_HOURS['diurnal'][0][d]]
    finally:
        chronocrats.clear()


@_needs(PN4)
@_needs(PN4_FIXED / "p123_fixed.md")
def test_B_pn4_fig45_matches_the_page_literal():
    for which, rows in _pn4_copies("Figure 45 (PN IV)", "p123_fixed.md"):
        grid, half = {'diurnal': [], 'nocturnal': []}, None
        for r in rows:
            if r[0].startswith('Diurnal'):
                half = 'diurnal'
            elif r[0].startswith('Nocturnal'):
                half = 'nocturnal'
            elif r[0].isdigit():
                assert int(r[0]) == len(grid[half]) + 1, which
                grid[half].append(''.join(r[1:]))
        assert {k: tuple(v) for k, v in grid.items()} == PLANETARY_HOURS, which
