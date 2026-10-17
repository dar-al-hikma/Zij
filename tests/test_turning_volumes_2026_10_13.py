"""Every locator of the turning block names its volume.

The turning of the houses of the root (PN IV VI.2) was cited row by row as a
bare "VI.2, N". The bare form resolves in two books (Persian Nativities IV
and the Mathesis both have a VI.2), and a "(Firmicus)" in the siblings note
sent five of the rows to the Mathesis. "Every locator names its volume": no
string a reader sees in this block may hold a VI.2 locator without "PN IV"
before it. The strings are read where the reader meets them -- the rows the
engine hands the page, for a day chart and a night chart, the string
literals of the page's own section in app.py, and that section as the app
renders it, so that an engine string the section joins into its own text
(the semi-arcs' sources in the notes) is read as it is shown -- not only in
the tables.

Runs without the corpus.
"""
import io
import re
import tokenize
from datetime import time
from pathlib import Path

import pytest

ENGINE_DIR = Path(__file__).resolve().parent.parent

# A VI.2 locator (with or without its sentence) not glued to a word or a
# decimal: "VI.2, 4", "VI.2, 10-11", "VI.2" -- not "VI.20", not "XVI.2".
LOCATOR = re.compile(r"(?<![\w.])VI\.2(?!\d)(?!\.\d)")
VOLUME = "PN IV "


def bare(text):
    """Every VI.2 locator in `text` without "PN IV " directly before it."""
    return [text[max(0, m.start() - 30):m.end() + 12] for m in LOCATOR.finditer(text)
            if text[max(0, m.start() - len(VOLUME)):m.start()] != VOLUME]


def test_the_rule_reads_what_it_must():
    assert bare("the fathers (VI.2, 6)") and bare("'VI.2, 4; fn 12'") and bare("VI.2, 1, whole.")
    assert not bare("(PN IV VI.2, 6)") and not bare("Mathesis VI.20, 3") and not bare("XVI.2, 1")


def _cells(rows):
    return [str(v) for r in rows for v in r.values()]


@pytest.fixture(scope="module")
def charts(engine):
    """Three real charts, by day and by night, each with a quadrant cusp in
    a sign other than its whole-sign house (so the second turning's row is
    drawn too): a nocturnal chart of 1240 and one chart of each sect found
    near 2023."""
    calc = engine["calculate_traditional_chart_jd"]
    root = calc(2250406.625914352, 18.827745849999175, -35.78280106166059)
    found = {}
    for k in range(0, 48):
        c = calc(2460000.0 + k * 0.29, 55.75, 37.62)
        found.setdefault(c["sect"], c)
        if len(found) == 2:
            break
    assert set(found) == {"Diurnal", "Nocturnal"}, "premise: a day chart and a night chart"
    return [root, found["Diurnal"], found["Nocturnal"]]


def test_no_turning_row_holds_a_bare_vi2_locator(engine, charts):
    rows, trip = [], []
    for chart in charts:
        for age in (0, 7, 30):
            rows += engine["pn4_turning_rows"](chart, age)
        trip += engine["pn4_turning_triplicity_lords"](chart, charts[0])
    assert len(rows) > 9 * 7 * 3 and len(trip) == 6 * len(charts), "premise: every chart's rows were drawn"
    assert any("in another sign" in r["Point"] for r in rows), "premise: a displaced cusp's second row was read"
    cells = _cells(rows) + _cells(trip)
    assert sum("PN IV VI.2" in c for c in cells) > 100, "premise: the Source cells were read"
    offenders = [b for c in cells for b in bare(c)]
    assert not offenders, offenders[:10]


def test_no_turning_table_holds_a_bare_vi2_locator(engine):
    """The tables themselves, every field, both sects' planet topics: a row
    the charts above happen not to draw is still read."""
    texts = [s for row in engine["PN4_TURNING_HOUSES"] for s in row if isinstance(s, str)]
    texts += [s for row in engine["PN4_TURNING_LOTS"] for s in row]
    for sect in ("Diurnal", "Nocturnal"):
        texts += list(engine["pn4_turning_planet_topics"](sect).values())
    offenders = [b for t in texts for b in bare(t)]
    assert not offenders, offenders


def _section_strings():
    """The string literals of app.py's turning section: from its subheader
    to the next tab. Comments are not read; strings are, f-strings whole.
    A name the section reads (an engine constant joined into a note) is not
    a literal and is not read here: the rendered test below reads it as
    shown."""
    src = (ENGINE_DIR / "app.py").read_text(encoding="utf-8")
    start = src.index('st.subheader("The turning of the houses of the root (PN IV VI.2)"')
    end = src.index("with tab_dist:", start)
    body = src[start:end]
    return [t.string for t in tokenize.generate_tokens(io.StringIO(body).readline)
            if t.type == tokenize.STRING or t.type == getattr(tokenize, "FSTRING_MIDDLE", -1)]


def test_the_page_section_holds_no_bare_vi2_locator():
    strings = _section_strings()
    assert any("VI.2, 1, whole." in s for s in strings), "premise: the section's notes were read"
    offenders = [b for s in strings for b in bare(s)]
    assert not offenders, offenders


# The section as the app draws it: three charts on the Revolutions page
# (the default chart, and two with a quadrant cusp in another sign, one by
# day with the sect light's or Mars's triplicity in Virgo, one by night), as
# (date, local time, latitude, longitude, target date).
RENDERED_CHARTS = (
    ("1240-05-23", None, None, None, None),
    ("1963-09-08", None, None, None, "1983-10-05"),
    ("1985-02-10", time(6, 0), 59.33, 18.06, "2000-03-01"),
)
TURNING_SUBHEADER = "The turning of the houses of the root (PN IV VI.2)"


def _rendered_section(at):
    """Every text the reader is shown in the turning section: from its
    subheader (with its help) to the next subheader or the end of its tab,
    every markdown, caption and expander label, the notes expander's bodies,
    and every dataframe's columns and cells."""
    def walk(node):
        yield node
        for child in (getattr(node, "children", None) or {}).values():
            yield from walk(child)

    tab = next(t for t in at.tabs if any(type(n).__name__ == "Subheader" and n.value == TURNING_SUBHEADER
                                         for n in walk(t)))
    nodes = list(walk(tab))
    start = next(i for i, n in enumerate(nodes) if type(n).__name__ == "Subheader" and n.value == TURNING_SUBHEADER)
    texts = []
    for k, n in enumerate(nodes[start:]):
        if k and type(n).__name__ == "Subheader":
            break
        for attr in ("value", "label"):
            v = getattr(n, attr, None)
            if isinstance(v, str):
                texts.append(v)
            elif hasattr(v, "columns"):
                texts += [str(c) for c in v.columns] + [str(x) for x in v.astype(str).values.ravel()]
        helptext = getattr(getattr(n, "proto", None), "help", None)
        if isinstance(helptext, str) and helptext:
            texts.append(helptext)
    return texts


def test_the_rendered_section_holds_no_bare_vi2_locator(engine):
    """What the reader sees, read off the rendered page: a string the section
    takes from the engine by name (PN4_SEMIARCS_SOURCES in the notes, the
    Virgo note in the triplicity table) is read where it is shown."""
    from conftest import assert_no_exception, make_app

    sects, displaced, virgo, offenders = set(), 0, 0, []
    for date, local, lat, lon, target in RENDERED_CHARTS:
        at = make_app(date=date, page="timing")
        if local is not None:
            at.session_state["time_input_key"] = local
        if lat is not None:
            at.session_state["manual_lat_key"] = lat
            at.session_state["manual_lon_key"] = lon
        if target is not None:
            at.session_state["_target_mode"] = "Date"
            at.session_state["_target_date"] = target
        at.run(timeout=300)
        assert_no_exception(at, f"timing, {date}")
        texts = _rendered_section(at)
        blob = "\n".join(texts)
        assert "**PN IV VI.2, 1, whole.**" in texts and engine["PN4_SEMIARCS_SOURCES"] in blob, \
            f"premise: the notes expander's bodies were read ({date})"
        assert blob.count("PN IV VI.2") > 60, f"premise: the tables' cells were read ({date})"
        sects.add("Nocturnal" if "what it indicates (PN IV VI.2, 2); the fathers" in blob else "Diurnal")
        displaced += "in another sign)" in blob
        virgo += engine["VIRGO_PARTNER_NOTE"] in blob
        offenders += [(date, b) for t in texts for b in bare(t)]
    assert sects == {"Diurnal", "Nocturnal"} and displaced >= 2 and virgo, \
        "premise: both sects, a displaced cusp's row, and the Virgo note"
    assert not offenders, offenders[:10]


def test_the_siblings_note_names_no_work_beside_the_locators(engine):
    """fn 15's mention of Firmicus is said as fn 15's: a parenthesised work
    name beside the bare rows was what sent them to the Mathesis."""
    note = next(n for lot, _t, _c, n in engine["PN4_TURNING_LOTS"] if lot == "siblings_hermes")
    assert note.startswith("fn 15 reverses it at night, citing Firmicus")
    assert "(Firmicus)" not in note


# The three notes the same amendment corrected, each pinned to what its
# sentence carries.

def _lot(engine, lot_id):
    return next(d for d in engine["LOT_DEFINITIONS"] if d["id"] == lot_id)


def test_the_lot_of_spirit_names_the_notes_that_confirm_its_identity(engine):
    """The identity is in Dykes's note 121, on the heading over On Nativities
    Ch. 9.5, 73, and in his note 9 on Ch. 11, 5; at 73 the name stands in his
    pointed brackets, so 73 cannot witness it."""
    note = _lot(engine, "spirit")["note"]
    assert "note 121, on the heading over On Nativities Ch. 9.5, 73" in note
    assert "his note 9 on Ch. 11, 5" in note and "at 73 the name is his supply" in note
    assert "notes on On Nativities Ch. 9.5, 73" not in note


def test_the_lot_of_enemies_from_mercury_to_the_moon_sources_its_reversal(engine):
    """E's reading prints no night reversal; the row's comes from the Lot of
    slaves, Sahl's 6.10, 20 ("by night the reverse of that"). The flag is
    unchanged."""
    row = _lot(engine, "enemies_slaves")
    assert row["reverse_at_night"] is True and _lot(engine, "slaves")["reverse_at_night"] is True
    assert "Reversed by night as the Lot of slaves is (Sahl, On Nativities Ch. 6.10, 20)." in row["note"]


def test_the_releasers_short_form_carries_the_reading_label():
    """The short form reaches the governor's testimony #3 and the proxies cell;
    it carries "as this app reads it" where the long form does."""
    import ast
    tree = ast.parse((ENGINE_DIR / "engine.py").read_text(encoding="utf-8"))
    forms = [n.value.value for n in ast.walk(tree)
             if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "releaser_note" for t in n.targets)
             and isinstance(n.value, ast.Constant) and "easternness" in str(n.value.value)]
    assert forms, "premise: the short form was found"
    for s in forms:
        assert "(On Nativities 1.20, 6, as this app reads it), which the texts do not define (On Nativities 1.22, 1-8)" in s, s
