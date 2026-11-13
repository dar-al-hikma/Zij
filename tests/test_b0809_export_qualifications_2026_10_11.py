"""The exports carry the two sentences the page prints over its tables.

The Dignities page prints the Natal adaptation sentence over Topical
Planets in Houses -- the PN IV halves adapt Book II's annual rules for the
lord of the year to natal places, and the natal lookup does not establish
those annual prerequisites. The JSON, Markdown and HTML exports carried the
table without it.

The Revolutions page prints the fixed stars' reading over the two star
tables -- how a star is read as on an angle or with a planet. The exports
carried both tables under the image's heading with no citation, so a star's
row went out with nothing to say how that was read.

Each sentence is now ONE string for the page and the export (the code's own
practice: SECT_CAPTION; the true-Sun citation). The page prints it as it
did, byte for byte; each export carries it, the emphasis marks dropped and
every word kept, with its table and only there: the Natal adaptation once,
after the Topical table's own citation; the fixed stars' reading twice, once
with the root's star table and once with the revolution's, and not with the
image's table under the same heading. The tables' rows are unchanged.

Input: Target by Date 2026-10-09, the Dignities page on the default chart and
the Revolutions page on a chart with both star tables (1240-05-25, the first
from the default on), the three exports from session_state (what the download
buttons hand over). Every app run uses its own XDG directory.

A narrower case: the chart above has rows in
both star tables, so the pins above cannot see a star table the page does not
draw. Three more Florence charts (make_app's place and clock, the same
target), found by running the Revolutions page day by day from 1240-05-23 and
reading its own "None ..." sentences under each star heading: 1240-05-23, the
first with no hit in either table; 1240-05-27, the first with the
revolution's table only; 1240-06-18, the first with the root's table only.
With no table the exports carry neither the sentence nor a star table; with
one, the sentence once, with that table.
"""
import hashlib
import html as H
import json

import pytest

from conftest import assert_no_exception, make_app

TARGET = "2026-10-09"
BOTH_TABLES = "1240-05-25"

# The page's lines, as the page passed them to st.markdown before and after
# the change (in app.py).
NATAL_PAGE = ("**Natal adaptation.** The Book II entries adapt PN IV's annual rules for planets serving as lord "
              "of the year to natal house positions. The source evaluates the root and revolution together; the "
              "natal lookup does not establish those annual prerequisites. The columns summarize suitable and "
              "adverse conditions, with the qualifications shown in each entry.")
STARS_PAGE = ("**The fixed stars (I.6, 7 in the root; III.8, 9 in the revolution)** -- Sahl's list, *On Nativities* "
              "2.2, in Dykes's identifications (the table at that chapter's end, with Rhetorius Ch. 58's natures); "
              "PN IV names no stars of its own. This app reads a star as on an angle when it crosses that angle within "
              "four minutes of the chart (+ after it, − before). It reads one as with a planet when within one degree across "
              "the sky, latitude counted, and as at the terminal point or the distribution's degree when within one degree of "
              "longitude. The planets \"in the stakes\" go by whole-sign place. Positions from "
              "the Swiss Ephemeris star catalogue this app ships.")

# The same words as the exports carry them: no emphasis marks.
NATAL_TEXT = ("Natal adaptation. The Book II entries adapt PN IV's annual rules for planets serving as lord "
              "of the year to natal house positions. The source evaluates the root and revolution together; the "
              "natal lookup does not establish those annual prerequisites. The columns summarize suitable and "
              "adverse conditions, with the qualifications shown in each entry.")
STARS_TEXT = ("The fixed stars (I.6, 7 in the root; III.8, 9 in the revolution) -- Sahl's list, On Nativities "
              "2.2, in Dykes's identifications (the table at that chapter's end, with Rhetorius Ch. 58's natures); "
              "PN IV names no stars of its own. This app reads a star as on an angle when it crosses that angle within "
              "four minutes of the chart (+ after it, − before). It reads one as with a planet when within one degree across "
              "the sky, latitude counted, and as at the terminal point or the distribution's degree when within one degree of "
              "longitude. The planets \"in the stakes\" go by whole-sign place. Positions from "
              "the Swiss Ephemeris star catalogue this app ships.")

# The Topical table's own export citation, as it stood at base; the Natal
# adaptation follows it.
TOPICAL = "Topical Planets in Houses"
TOPICAL_CITATION = ("Rhetorius Ch. 57 and Firmicus, Mathesis III, as the texts state it, under each author's own "
                    "division; PN IV Book II paraphrased in the two condition columns and shared passages; the Moon "
                    "from VII.8 by her transit in her own table; every entry with its locator. " + NATAL_TEXT)
# The Topical rows at base, as the JSON holds them (sha256 of the rows, keys
# sorted): the change adds a sentence and moves no cell.
TOPICAL_PLANETS = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"]
TOPICAL_ROWS_SHA256 = "71e5eae6f3627073f72aaf00f69bc2364abbe5ef06a39e52feeeb245ac0a0a09"

IMAGE = "The image of the revolution of the year: its points (PN IV I.6, 3-8)"
NATURE = "Nature (Rhetorius, per Dykes)"
STAR_COLUMNS = ["Star", "Longitude", NATURE, "Place", "Crossing", "Separation"]
ROOT_STARS = [
    {"Star": "Spica", "Longitude": "13° Lib 15'", NATURE: "Venus-Mercury",
     "Place": "on the Ascendant", "Crossing": "+1:17", "Separation": "—"},
]
REVOLUTION_STARS = [
    {"Star": "Alpheratz", "Longitude": "14° Ari 40'", NATURE: "Mars-Mercury",
     "Place": "the degree of the terminal point, by longitude", "Crossing": "—", "Separation": "0.89 deg of longitude"},
]


def _run(page, tmp_path, monkeypatch, date="1240-05-23"):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / page))
    at = make_app(date=date, page=page)
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = TARGET
    at.run(timeout=180)
    assert_no_exception(at, page)
    assert at.session_state["_analysis_export"]["target"]["date"] == TARGET
    return at


def _module_run(page, tmp_path_factory, **chart):
    mp = pytest.MonkeyPatch()
    try:
        return _run(page, tmp_path_factory.mktemp(f"b0809_{page}"), mp, **chart)
    finally:
        mp.undo()


@pytest.fixture(scope="module")
def dignities(tmp_path_factory):
    return _module_run("dignities", tmp_path_factory)


@pytest.fixture(scope="module")
def timing(tmp_path_factory):
    return _module_run("timing", tmp_path_factory, date=BOTH_TABLES)


def _exports(at):
    return (at.session_state["_analysis_export"], at.session_state["_analysis_markdown"],
            at.session_state["_analysis_html"])


def _page_line(at, opening):
    lines = [m.value for m in at.main.markdown if m.value.startswith(opening)]
    assert len(lines) == 1, lines
    return lines[0]


def _json_count(value, text):
    """How often `text` stands in the export's strings, keys and values,
    read as the JSON holds them (unescaped)."""
    if isinstance(value, str):
        return value.count(text)
    if isinstance(value, dict):
        return sum(_json_count(k, text) + _json_count(v, text) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return sum(_json_count(v, text) for v in value)
    return 0


def _unmarked(markdown):
    return markdown.replace("**", "").replace("*", "")


def _md_head(columns, first):
    return ("| " + " | ".join(columns) + " |\n|" + "---|" * len(columns) + "\n| " + first + " |")


def _html_head(columns, first):
    return ("<div class='wrap'><table><thead><tr>" + "".join(f"<th>{H.escape(c)}</th>" for c in columns)
            + "</tr></thead><tbody><tr><td>" + H.escape(first) + "</td>")


# --- the page: unchanged -----------------------------------------------------

def test_b08_the_dignities_page_prints_the_natal_adaptation_as_it_did(dignities):
    assert _page_line(dignities, "**Natal adaptation.**") == NATAL_PAGE
    assert sum(NATAL_PAGE in str(m.value) for m in dignities.main.markdown) == 1


def test_b09_the_revolutions_page_prints_the_fixed_stars_reading_as_it_did(timing):
    assert _page_line(timing, "**The fixed stars (") == STARS_PAGE
    assert sum(STARS_PAGE in str(m.value) for m in timing.main.markdown) == 1


# --- the export: the page's words, with their table, once each ---------------

def test_b08_the_export_carries_the_pages_natal_adaptation_word_for_word(dignities):
    """The export's sentence is the page's own line with the emphasis marks
    dropped: one word changed on either side fails here."""
    page = _unmarked(_page_line(dignities, "**Natal adaptation.**"))
    exp, _, _ = _exports(dignities)
    entries = exp["results"]["Dignities and places"][TOPICAL]
    assert len(entries) == 1
    assert entries[0]["citation"].endswith(" " + page), entries[0]["citation"]
    assert page == NATAL_TEXT


def test_b08_the_json_carries_the_natal_adaptation_with_the_topical_table_once(dignities):
    exp, _, _ = _exports(dignities)
    entries = exp["results"]["Dignities and places"][TOPICAL]
    assert [e.get("citation") for e in entries] == [TOPICAL_CITATION]
    assert _json_count(exp, NATAL_TEXT) == 1


def test_b08_the_markdown_carries_the_natal_adaptation_with_the_topical_table_once(dignities):
    _, md, _ = _exports(dignities)
    assert md.count(NATAL_TEXT) == 1
    block = f"#### {TOPICAL}\n\n*{TOPICAL_CITATION}*\n\n| Planet | Whole-sign place | "
    assert md.count(block) == 1
    header = md[md.index(block):].split("\n")[4]
    assert not {"Net", "Lean", "Standing"} & {cell.strip() for cell in header.split("|")}, header


def test_b08_the_html_carries_the_natal_adaptation_with_the_topical_table_once(dignities):
    _, _, doc = _exports(dignities)
    assert doc.count(H.escape(NATAL_TEXT)) == 1
    block = (f"<h3>{H.escape(TOPICAL)}</h3><p class='cite'>{H.escape(TOPICAL_CITATION)}</p>"
             "<div class='wrap'><table><thead><tr><th>Planet</th>")
    assert doc.count(block) == 1


def test_b09_the_export_carries_the_pages_fixed_stars_reading_word_for_word(timing):
    page = _unmarked(_page_line(timing, "**The fixed stars ("))
    exp, _, _ = _exports(timing)
    cited = [e.get("citation") for e in exp["results"]["Prediction"][IMAGE]]
    assert cited.count(page) == 2, cited
    assert page == STARS_TEXT


def test_b09_the_json_carries_the_reading_with_each_star_table_and_only_there(timing):
    exp, _, _ = _exports(timing)
    entries = exp["results"]["Prediction"][IMAGE]
    assert len(entries) == 3
    image, root, revolution = entries
    assert "citation" not in image and "Star" not in image["columns"]
    assert root["citation"] == STARS_TEXT and root["rows"] == ROOT_STARS
    assert revolution["citation"] == STARS_TEXT and revolution["rows"] == REVOLUTION_STARS
    assert _json_count(exp, STARS_TEXT) == 2


def test_b09_the_markdown_carries_the_reading_with_each_star_table_and_only_there(timing):
    _, md, _ = _exports(timing)
    assert md.count(STARS_TEXT) == 2
    for first in ("Spica | 13° Lib 15'", "Alpheratz | 14° Ari 40'"):
        assert md.count(f"*{STARS_TEXT}*\n\n{_md_head(STAR_COLUMNS, first)}") == 1, first


def test_b09_the_html_carries_the_reading_with_each_star_table_and_only_there(timing):
    _, _, doc = _exports(timing)
    assert doc.count(H.escape(STARS_TEXT)) == 2
    for first in ("Spica", "Alpheratz"):
        block = f"<p class='cite'>{H.escape(STARS_TEXT)}</p>{_html_head(STAR_COLUMNS, first)}"
        assert doc.count(block) == 1, first


# --- the rows: unchanged -----------------------------------------------------

def test_b0809_the_tables_rows_are_unchanged(dignities, timing):
    rows = _exports(dignities)[0]["results"]["Dignities and places"][TOPICAL][0]["rows"]
    assert [r["Planet"] for r in rows] == TOPICAL_PLANETS
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    assert digest == TOPICAL_ROWS_SHA256
    _, root, revolution = _exports(timing)[0]["results"]["Prediction"][IMAGE]
    assert (root["rows"], revolution["rows"]) == (ROOT_STARS, REVOLUTION_STARS)
    assert root["columns"] == revolution["columns"] == sorted(STAR_COLUMNS)


def test_b0809_no_emphasis_mark_reaches_the_exports_sentences(dignities, timing):
    """The page renders the marks as bold and italic; the exports carry the
    words. A raw "**" or "*On Nativities*" would be read literally in the
    JSON and the HTML."""
    for at in (dignities, timing):
        exp, md, doc = _exports(at)
        assert "**Natal adaptation.**" not in json.dumps(exp, ensure_ascii=False) + doc
        assert "*On Nativities* 2.2" not in json.dumps(exp, ensure_ascii=False) + md + doc


# --- the polish round: a star table the page does not draw -------------------

NO_HIT = "1240-05-23"
REVOLUTION_ONLY = ("1240-05-27", "None of Sahl's stars crosses", [
    {"Star": "Alpheratz", "Longitude": "14° Ari 40'", NATURE: "Mars-Mercury",
     "Place": "the degree of the terminal point, by longitude", "Crossing": "—", "Separation": "0.62 deg of longitude"},
])
ROOT_ONLY = ("1240-06-18", "None on the year's Ascendant", [
    {"Star": "Alphard", "Longitude": "16° Leo 43'", NATURE: "Saturn-Venus",
     "Place": "on the Midheaven", "Crossing": "+3:48", "Separation": "—"},
])
ROOT_NONE = "None of Sahl's stars crosses"
REVOLUTION_NONE = "None on the year's Ascendant"


def _star_entries(exp):
    return [e for e in exp["results"]["Prediction"].get(IMAGE, []) if "Star" in e["columns"]]


def test_b09_a_chart_with_no_star_hit_exports_neither_the_sentence_nor_a_star_table(tmp_path, monkeypatch):
    at = _run("timing", tmp_path, monkeypatch, date=NO_HIT)
    lines = [str(m.value) for m in at.main.markdown]
    # The page draws no star table: both of its "None ..." sentences stand.
    assert any(m.startswith(ROOT_NONE) for m in lines) and any(m.startswith(REVOLUTION_NONE) for m in lines)
    frames = [df.value for df in at.dataframe]
    assert frames and [f for f in frames if "Star" in f.columns] == []
    exp, md, doc = _exports(at)
    assert _star_entries(exp) == []
    entries = exp["results"]["Prediction"][IMAGE]
    assert len(entries) == 1 and entries[0]["rows"] and "citation" not in entries[0]   # the image's table alone
    assert _json_count(exp, STARS_TEXT) == 0
    assert md.count(STARS_TEXT) == 0 and "| Star | Longitude |" not in md
    assert doc.count(H.escape(STARS_TEXT)) == 0 and "<th>Star</th><th>Longitude</th>" not in doc


@pytest.mark.parametrize("chart", [REVOLUTION_ONLY, ROOT_ONLY], ids=["revolution-only", "root-only"])
def test_b09_a_chart_with_one_star_table_carries_the_sentence_once_with_it(chart, tmp_path, monkeypatch):
    date, absent, rows = chart
    at = _run("timing", tmp_path, monkeypatch, date=date)
    lines = [str(m.value) for m in at.main.markdown]
    assert sum(m.startswith((ROOT_NONE, REVOLUTION_NONE)) for m in lines) == 1
    assert any(m.startswith(absent) for m in lines)
    exp, md, doc = _exports(at)
    entries = exp["results"]["Prediction"][IMAGE]
    assert len(entries) == 2 and "citation" not in entries[0]
    assert entries[1]["citation"] == STARS_TEXT and entries[1]["rows"] == rows
    assert _json_count(exp, STARS_TEXT) == 1
    assert md.count(STARS_TEXT) == 1
    assert md.count(f"*{STARS_TEXT}*\n\n{_md_head(STAR_COLUMNS, rows[0]['Star'])}") == 1
    assert doc.count(H.escape(STARS_TEXT)) == 1
    assert doc.count(f"<p class='cite'>{H.escape(STARS_TEXT)}</p>{_html_head(STAR_COLUMNS, rows[0]['Star'])}") == 1
