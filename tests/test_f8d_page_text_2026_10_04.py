"""Lane F8 of the hostile pass of 2026-10-03, part D: the page text after F8.

The items of the full read of the pages after F8 (items A to E and the two
qualification sites Q1 and Q2), each a test written red against the
unchanged tree and turned green by the wording it names. Nothing here pins a
decision of the engine: every assertion is about the words a reader is shown.

A   the enclosure note named a code constant and "this project's own conjecture"
B   "the function takes it as written", "pinned against four independent witnesses"
C   a file name on the Timing page and in the star catalogue's refusal
D   a closing parenthesis with no opening one (Releaser); fn 234 called
    incomplete, with a stray "(" (Findings and two Prosperity rows) -- the
    footnote is whole on Sahl I p. 422
E   doubled spaces before the bracket in two table builders
Q1  "Apogee circle, approximated (23)" never said what was approximated
Q2  al-Qabisi's join "described as approximate by this app", nowhere on the page
"""
from __future__ import annotations

import re

import pytest

from conftest import assert_no_exception, find_table, make_app
from corpus_paths import corpus_file
from skip_guard import skip_without_corpus

DEPTH = "Course text"


def _render(page, depth=DEPTH, date="1240-05-23"):
    at = make_app(date=date, page=page)
    at.session_state["_reading_depth"] = depth
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "2026-10-03"
    at.run(timeout=180)
    assert_no_exception(at, page)
    return at


_PAGES: dict = {}


def _page(page):
    """One render per page for the whole module."""
    if page not in _PAGES:
        _PAGES[page] = _render(page)
    return _PAGES[page]


def _texts(node, out=None):
    """Every string a reader can see under ``node``: bodies, values, labels,
    help strings and every dataframe cell."""
    out = [] if out is None else out
    for attr in ("value", "label", "help", "body", "caption"):
        try:
            v = getattr(node, attr)
        except Exception:
            continue
        if isinstance(v, str) and v:
            out.append(v)
    proto = getattr(node, "proto", None)
    if proto is not None:
        for attr in ("help", "body", "label"):
            v = getattr(proto, attr, None)
            if isinstance(v, str) and v:
                out.append(v)
    if type(node).__name__ == "Dataframe":
        df = node.value
        out.extend(str(c) for c in df.columns)
        for row in df.itertuples(index=False):
            out.extend(str(cell) for cell in row if cell is not None)
    for child in (getattr(node, "children", None) or {}).values():
        _texts(child, out)
    return out


def _page_text(page):
    return _texts(_page(page).main)


def _with(page, needle):
    """The page's texts that contain ``needle`` (at least one)."""
    found = [t for t in _page_text(page) if needle in t]
    assert found, f"{needle!r} not on {page}"
    return found


def _balanced(s):
    return s.count("(") == s.count(")") and s.count("[") == s.count("]")


def _plain(text):
    """Markdown emphasis, footnote marks and entities out; whitespace collapsed."""
    text = re.sub(r"<sup>\d+</sup>", "", text).replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"\s+", " ", text.replace("*", "")).strip()


# --- A: the enclosure note -------------------------------------------------

def test_a_the_enclosure_note_names_no_code_constant_and_no_project():
    (note,) = set(_with("configurations", "Enclosure here is Abu Ma'shar's own"))
    assert "SIGN_ENCLOSURE_BODIES_ONLY" not in note
    assert not re.search(r"\b[A-Z]{2,}(?:_[A-Z0-9]+)+\b", note), note
    assert "this project" not in note and "in the code" not in note
    assert ("Counting bodies only would make it rare (about 2% of placements), but that is not what 58 says, "
            "and this app does not offer it.") in note


# --- B: build-process language ---------------------------------------------

def test_b3_the_rays_by_ascension_note_does_not_speak_of_the_function():
    (note,) = set(_with("configurations", "The nearest/distant flip is in the text"))
    assert "the function" not in note and "can be asked for" not in note
    assert "The nearest/distant flip is in the text and unexplained; this app takes it as written." in note


def test_b4_the_egyptian_bounds_help_says_witnesses_agree_not_pinned():
    (helptext,) = set(_with("reference", "The bounds every distribution on the Prediction pages runs through"))
    assert "pinned" not in helptext
    assert helptext.endswith("The same table this app directs by; four independent witnesses agree with it.")


# --- C: a file name on the page ----------------------------------------------

_FILE_NAME = re.compile(r"\b[\w-]+\.(?:txt|md|tsv|csv|json|db|py|se1|html?|spec)\b")


def test_c_the_fixed_star_note_names_the_catalogue_not_its_file():
    (note,) = set(_with("timing", "Positions from the Swiss Ephemeris star catalogue"))
    assert not _FILE_NAME.search(note) and "ephe/" not in note, note
    assert note.endswith("Positions from the Swiss Ephemeris star catalogue this app ships.")


def test_c_the_refusal_names_what_is_missing_in_words(engine):
    sentence = engine["fixed_star_refusal"]()
    head = sentence.split(" -- ")[0]                    # the reason the search records follows " -- "
    assert head == "no Swiss Ephemeris star catalogue is attached; nothing is computed", sentence
    assert not _FILE_NAME.search(head)


# --- D: unbalanced brackets ------------------------------------------------

def test_d1_the_releasers_readings_note_opens_the_parenthesis_it_closes():
    (note,) = set(_with("releaser", "Readings: \"the degree of burning\""))
    assert _balanced(note), note
    assert ("to the luminaries and the Ascendant alike (not PN IV III.1, 12's third case, the proportional "
            "semi-arcs, which is Abu Ma'shar's assignment and not Sahl's); ") in note


FN234_ON_THE_PAGE = (
    "Fn 234 to On Nativities 2.17, 7, whole: \"Cf. *Carmen* I.28, 32 (which mentions only the eleventh from the Ascendant) "
    "and *Anth.* II.12 and Rhetorius Ch. 54 (p. 36), which discuss the infortunes (and other planets) in the "
    "eleventh from the Lot. However, *BA* adds that they are contrary to the sect (which makes more sense).\" "
    "The two On Nativities 2.17, 7 rows list Mars or Saturn there whatever the sect, as Sahl's sentence has it.")


def test_d2_the_prosperity_note_quotes_fn_234_whole_and_balanced():
    (note,) = set(_with("findings", "The referent of Sahl's other fortune remains open"))
    assert "incomplete" not in note and "available text" not in note and "(which makes;" not in note
    assert _balanced(note), note
    assert note.endswith(FN234_ON_THE_PAGE), note[-400:]


def test_d2_the_quote_is_fn_234_as_the_corpus_holds_it():
    """Sahl I p. 422, fn 234 to On Nativities 2.17, 7: the whole footnote,
    as the photograph of the page reads (the close shot of triage r25g).
    Found and compared in words, as the citation chain compares a quotation
    (markdown emphasis dropped): the corpus sets *Carmen*'s sentence number
    "32" bold, as the paper prints it (the corpus' #189), where the page's
    "I.28, 32" stays the plain locator the citation register reads."""
    path = corpus_file("on_nativities.md")
    skip_without_corpus(path)
    footnotes = [fn for fn in re.findall(r"^<sup>234</sup> (.*)$", path.read_text(encoding="utf-8"), re.M)
                 if _plain(fn).startswith("Cf. Carmen I.28, 32 ")]
    assert len(footnotes) == 1, footnotes
    quoted = re.search(r'whole: "(.*?)" The two', FN234_ON_THE_PAGE).group(1)
    assert _plain(quoted) == _plain(footnotes[0])


def test_d2_the_two_prosperity_rows_no_longer_call_fn_234_incomplete(engine):
    import test_prosperity_2026_09_15 as P
    by_asc = P._chart(engine, 'Nocturnal', 'Scorpio', Moon='Scorpio', Sun='Aries', Mars='Aquarius',
                      Venus='Taurus', Mercury='Pisces', Jupiter='Virgo', Saturn='Virgo')
    by_lot = P._chart(engine, 'Diurnal', 'Leo', lot=True, Sun='Libra', Moon='Leo', Saturn='Aries', Mars='Aries',
                      Jupiter='Cancer', Venus='Virgo', Mercury='Libra')
    grounds = [r['Ground'] for chart in (by_asc, by_lot) for r in engine['evaluate_prosperity'](chart)
               if r['key'] == 'falling' and '2.17, 7' in r['Sahl']]
    assert len(grounds) == 3, grounds
    assert {g.split('; fn 234')[0] for g in grounds} == {
        'Saturn in the eleventh from the Ascendant', 'Mars in the eleventh from the Lot of Fortune',
        'Saturn in the eleventh from the Lot of Fortune'}, grounds
    for g in grounds:
        assert "incomplete" not in g and "available text" not in g and _balanced(g), g
        assert g.endswith('; fn 234: "BA adds that they are contrary to the sect (which makes more sense)", '
                          'which this row does not require'), g


# --- E: doubled spaces in table cells -----------------------------------------

def test_e1_the_lots_formula_cells_have_single_spaces():
    at = _page("lots")
    formulas = [str(v) for node in at.main.dataframe if "Formula" in node.value.columns
                for v in node.value["Formula"]]
    assert any(" [" in f for f in formulas), formulas          # the bracketed qualifications are there
    assert not [f for f in formulas if "  " in f], [f for f in formulas if "  " in f]


def test_e2_the_moons_defects_cell_has_a_single_space_before_its_count():
    """The Moon's row, both builders. The settled list on this chart: 109 is
    not met here (ruling 137), so the cell prints no clause count, and no
    double space. The settled builder's single space before its count is
    held where a count prints (1240-09-18), by
    test_moon_109_falling_2026_10_08's
    test_two_settled_clauses_of_109_print_one_space_before_the_count. Then
    the list with an open defect (the label-merge case, by hand): the cell
    ends with its exact count, one space before it, and no double space."""
    import engine as E
    from test_label_merge_2026_09_25 import _moon_outcome
    at = _page("configurations")
    (row,) = at.session_state["_analysis_export"]["results"]["Configurations"]["Corruption of the Moon"][0]["rows"]
    assert " clauses across " not in row["Defects"], row        # 109 is not met on this chart (ruling 137)
    assert "  " not in row["Defects"], row
    mp = pytest.MonkeyPatch()
    mp.setattr(E, "evaluate_corruption_of_the_moon",
               lambda *_a, **_k: E._connection_merge([_moon_outcome(False), _moon_outcome(True)]))
    try:
        at2 = make_app(date="1240-05-23", page="configurations")
        at2.run(timeout=300)
    finally:
        mp.undo()
    assert_no_exception(at2, "configurations with an open Moon defect")
    (row2,) = at2.session_state["_analysis_export"]["results"]["Configurations"]["Corruption of the Moon"][0]["rows"]
    assert row2["Defects"].endswith(" [3 settled clauses across 2 of the ten testimonies]"), row2
    assert "  " not in row2["Defects"], row2


# --- Q1: what the apogee label approximates -------------------------------------

def test_q1_the_apogee_label_says_what_stands_in_for_the_circle():
    cells = [t for t in _page_text("configurations") if "Apogee circle" in t]
    assert cells, "no planet farther than its middle distance on this chart"
    for c in cells:
        assert "Apogee circle, approximated (23)" not in c, c
    assert any("Apogee circle, approximated by distance from the earth (23)" in c for c in cells)


Q1_NOTE = ("23: \"Or they are rising up in the circle of their apogee.\" Gr. Intr. VII.1, 10 has a planet rising "
           "there when it is at the top of its apogee or less than 90 degrees from it on either side. This app does "
           "not compute the circle of the apogee: it reads 23 for the Sun alone, by distance from the earth, counting "
           "him when he stands farther from the earth than the middle of his range. That distance is a modern "
           "stand-in for the circle of the apogee, and the condition's label says it is approximated.")


def test_q1_the_condition_notes_say_once_what_is_approximated():
    notes = set(t for t in _page_text("configurations") if "circle of their apogee" in t)
    assert len(notes) == 1, notes                       # said once, in Planetary Condition's notes
    assert notes == {Q1_NOTE}, notes
    assert [t for t in _page_text("configurations") if "Rising in the circle of the apogee (23)." in t]


def test_q1_the_sentences_the_note_reads_are_the_corpus_words():
    path = corpus_file("gr_intr/abu_mashar_great_introduction.md")
    skip_without_corpus(path)
    text = path.read_text(encoding="utf-8")
    assert "\n23 Or they are rising up in the circle of their apogee.\n" in text
    ten = re.search(r"\*\*10\*\* So as for the planets' rising in the apogee, (.*?)\*\*11\*\*", text, re.S).group(1)
    assert "is at the top of its apogee, or between it and [the apogee] are less than 90° to the right or left" in ten
    assert "then it is rising in the zone of the circle of its apogee" in ten


# --- Q2: what the join across quarters approximates -------------------------------

def test_q2_the_semi_arc_note_says_what_is_approximate_and_where():
    (note,) = set(_with("timing", "Al-Qabisi's join across quarters"))
    assert "described as approximate by this app" not in note
    assert ("Al-Qabisi's join across quarters (IV.12c, in ITA VIII.2.2), for two points in different quarters: direct to the angle "
            "that comes next, then from that angle to the other point, and add the two arcs. It is not used: "
            "this app's one formula, with the meridian distance signed, gives the arc in every quarter, "
            "and this app treats the join as an approximation of it. Converse directions are not built.") in note


def test_q2_the_join_as_the_note_states_it_is_al_qabisis():
    """al-Qabisi IV.12c (ITA p. 364): to the angle that comes after it, then
    from the angle to the place, the two arcs joined."""
    path = corpus_file("ita/introductions_to_traditional_astrology_PROVISIONAL.md")
    skip_without_corpus(path)
    line = next(ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.startswith("[al-Qabīsī IV.12c]"))
    for words in ("in one quarter, and the place to which you are directing it in another quarter",
                  "direct the significator to the angle which comes after it",
                  "direct from the angle to the place", "join both [of the arcs of the] directions together"):
        assert words in line, words
