"""The HTML analysis export.

Windows and macOS associate `.html` with a browser and neither renders
Markdown or JSON for someone who has not chosen a tool for them, so this
is the format the app's own reader can actually open: one file, opened by
double-clicking, printable to PDF, with nothing beside it to keep.

What is pinned here is what makes that true and keeps it true: the file is
self-contained (no script, no fetch, no reference to anything outside it),
it carries exactly the tables the JSON carries, and its cells are the same
words the Markdown prints -- all three go through `_export_cell`, so a
reader of any one of them is reading the same analysis.
"""
import html
import json
import os
import re
from pathlib import Path

import pytest

from conftest import assert_no_exception, engine_source, fetches_nothing, make_app


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    at = make_app(page="sources")
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.run(timeout=300)
    assert_no_exception(at, "the Sources page")
    return (at.session_state["_analysis_html"],
            at.session_state["_analysis_export"],
            at.session_state["_analysis_markdown"])


# --- 1. One file, and nothing fetched ------------------------------------

def test_it_is_a_whole_document(exported):
    page, _export, _md = exported
    assert page.startswith("<!doctype html>")
    assert page.rstrip().endswith("</html>")
    assert "<meta charset='utf-8'>" in page
    assert "<title>Analysis:" in page


def test_nothing_is_fetched_and_nothing_is_executed(exported):
    """The reader may be offline, and the app ships no vendored library:
    a script or an external reference would make the file a liar about
    being one file. A font held in the file is the one thing a url() may hold."""
    page, _export, _md = exported
    fetches_nothing(page)
    assert "url(data:font/woff2;base64," in page, "premise: the report carries its faces"


FONT = "url(data:font/woff2;base64,d09GMgABAAAA) format('woff2')"


@pytest.mark.parametrize("planted", [
    "url(https://example.invalid/a.woff2)", "url(http://example.invalid/a.woff2)", "url(//example.invalid/a.woff2)",
    "url(a.woff2)", "url(data:text/html;base64,PHNjcmlwdD4=)", "url(data:image/svg+xml;base64,PHN2Zz4=)",
    "url(data:font/woff;base64,d09GRgAB)", "url(data:font/woff2;charset=utf-8,x)", "URL(data:font/woff2;base64,d09GMgAB)",
    "url( data:font/woff2;base64,d09GMgAB)", "u\\72l(data:font/woff2;base64,d09GMgAB)",
    FONT + " url(https://example.invalid/a.woff2)", "@import 'a.css'", "<script>", "<iframe>", "<link rel=x>", "<img src=x>",
    "srcset", "http://example.invalid", "https://example.invalid",
])
def test_the_guard_takes_a_font_held_in_the_file_and_nothing_else(planted):
    fetches_nothing(f"<style>@font-face{{src:{FONT};}}</style>")
    with pytest.raises(AssertionError):
        fetches_nothing(f"<style>@font-face{{src:{planted};}}</style>")


def test_the_style_travels_inside_the_document(exported):
    page, _export, _md = exported
    assert page.count("<style>") == 1
    assert "prefers-color-scheme: dark" in page, "readable on a dark desktop"
    assert "@media print" in page, "prints to PDF without the summary chrome"


# --- 2. It carries what the JSON carries ---------------------------------

def test_every_table_the_json_carries_is_in_the_page(exported):
    page, export, _md = exported
    for section, headings in export["results"].items():
        assert _escaped(section) in page, section
        for heading in headings:
            assert _escaped(__import__('markup').page_words(heading)) in page, heading


def test_the_table_count_matches_the_json(exported):
    page, export, _md = exported
    in_json = sum(len(entries) for headings in export["results"].values()
                  for entries in headings.values())
    # The header blocks are tables too: seven of them precede the results.
    assert page.count("<table>") == in_json + 7


def test_the_scope_note_and_the_precision_paragraph_are_both_on_the_page(exported):
    page, export, _md = exported
    from markup import page_words
    scope = export["scope"].replace(", in the file's own spellings and capitals, and the fields of this app's own arithmetic that only this file keeps, but not the Fixed stars page, which has its own export", "")
    assert _escaped(page_words(scope.replace("Stars harming eyes; ", ""))) in page
    assert _escaped(page_words(export["precision"])) in page


# --- 3. The same words as the Markdown -----------------------------------

def test_one_cell_printer_serves_every_format():
    """A second printer is a second set of words for one fact. The HTML
    renderer lives in the engine, beside the pictures it also builds with a
    <style> block; app.py may not carry one (the finding contract)."""
    from conftest import ui_source
    source = engine_source() + ui_source()
    assert source.count("def _export_cell(") == 1
    for renderer in ("def _markdown_table(", "def _html_table("):
        body = source[source.index(renderer):]
        body = body[:body.index("\ndef ", 1)]
        assert "_export_cell(" in body, renderer


def test_a_flag_and_an_empty_value_read_as_the_markdown_reads_them(exported):
    page, _export, md = exported
    assert ">yes<" in page or ">no<" in page
    assert "None" not in re.sub(r"[A-Za-z]None|None[A-Za-z]", "", page), \
        "nothing prints as a Python None"


def test_the_results_are_one_collapsed_section_a_page(exported):
    """A hundred tables at once is not a document a reader meets; the
    sections open on print."""
    page, export, _md = exported
    assert page.count("<details>") == len(export["results"])
    assert "<details open>" not in page


# --- 4. Escaping at the point of writing ---------------------------------

HOSTILE = "<script>alert(1)</script> & \"quoted\" <b>"


def test_a_hostile_chart_name_cannot_break_out(tmp_path, monkeypatch):
    """The name comes from a saved record, so it is written by a person and
    reaches the page's title, its heading and its file name."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    data = Path(os.environ["XDG_DATA_HOME"]) / "Zij"
    data.mkdir(parents=True, exist_ok=True)
    (data / "saved_charts.json").write_text(json.dumps({HOSTILE: {
        "date_string": "1977-12-16", "time_string": "10:08:00",
        "time_standard": "Standard time (pytz)", "utc_offset": None,
        "location_query": "Escanaba, MI (US)", "lat": 45.74525, "lon": -87.06458,
        "target_mode": "Date", "target_date": "2026-09-15", "target_age": 48}}))
    at = make_app(page="sources").run(timeout=300)
    at.sidebar.selectbox(key="chart_picker").select(HOSTILE).run(timeout=300)
    assert_no_exception(at, "a hostile chart name")
    page = at.session_state["_analysis_html"]
    # The name really did reach the document -- escaped, and twice (title
    # and heading). A test that asserted only the absence of a script tag
    # would pass on a page the name never reached at all.
    assert page.count("&lt;script&gt;alert(1)&lt;/script&gt;") >= 2, "the name reached the page"
    assert "<script" not in page
    assert "<b>" not in page


def _escaped(text):
    """As the engine's own _esc_text escapes it: html.escape's default, which
    takes the quotes too, so an apostrophe reads &#x27; in the source and an
    apostrophe on screen."""
    return html.escape(str(text))


# --- 5. A typed place, and the table printer itself --------------
# The name above reaches the title and the heading; a place typed into the
# box, or held by a saved record, reaches the table cells, which only
# _html_table's own escape guards. With that escape narrowed to & " ' the
# whole suite once passed while the export carried a live <script> in two
# cells: these two pins fail on that narrowing, the first through the app,
# the second by name.

HOSTILE_PLACE = "Escanaba <script>alert(1)</script> & \"q\" <b>"


def test_a_hostile_place_cannot_break_out_of_the_table_cells(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    data = Path(os.environ["XDG_DATA_HOME"]) / "Zij"
    data.mkdir(parents=True, exist_ok=True)
    (data / "saved_charts.json").write_text(json.dumps({HOSTILE: {
        "date_string": "1977-12-16", "time_string": "10:08:00",
        "time_standard": "Standard time (pytz)", "utc_offset": None,
        "location_query": HOSTILE_PLACE, "lat": 45.74525, "lon": -87.06458,
        "target_mode": "Date", "target_date": "2026-09-15", "target_age": 48}}))
    at = make_app(page="sources").run(timeout=300)
    at.sidebar.selectbox(key="chart_picker").select(HOSTILE).run(timeout=300)
    assert_no_exception(at, "a hostile place")
    page = at.session_state["_analysis_html"]
    # Judged first and asserted as plain flags: pytest's report on a failed
    # "in" over a page this long takes minutes to write.
    live_script, live_bold = "<script" in page, "<b>" in page
    assert not live_script, "a <script> tag is live in the export"
    assert not live_bold, "a <b> tag is live in the export"
    # Both reached the page, escaped whole: the name in the title and the
    # heading, the place in the two Place rows (what was entered, and the
    # place the chart was cast at).
    assert page.count(html.escape(HOSTILE)) >= 2, "the name reached the page"
    assert page.count(f"<td>{html.escape(HOSTILE_PLACE)}</td>") >= 2, "the place reached the cells"


def test_the_table_printer_escapes_a_header_and_a_cell(engine):
    """Every one of < > & " ' in a header and in a cell, escaped, so a
    narrowed escape fails here by name rather than by accident."""
    got = engine["_html_table"]([{"<k> & \"q\" 'a'": "<v> & \"q\" 'a'"}])
    assert got == ("<div class='wrap'><table><thead><tr>"
                   "<th>&lt;k&gt; &amp; &quot;q&quot; &#x27;a&#x27;</th>"
                   "</tr></thead><tbody><tr>"
                   "<td>&lt;v&gt; &amp; &quot;q&quot; &#x27;a&#x27;</td>"
                   "</tr></tbody></table></div>")
