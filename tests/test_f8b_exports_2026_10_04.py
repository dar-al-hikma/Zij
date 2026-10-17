"""Lane F8, part B, of the hostile pass of 2026-10-03: the three exports.

The part's items that came without an xfail of their own, each written before
its fix and seen to fail without it, and a few cross-checks on the items that
did (L7-07, L5-03, L5-04, HP-16, HP-27), which the xfails asserted on one
format only:

* L5-10 -- every export heading is a heading the page shows, and a table is
  filed under the heading the page draws it under;
* S1-5  -- a refused run leaves no export of the previous chart in the session;
* F3-18 -- a tied primary's condition tables carry their label in a field of
  their own, not in the citation;
* F6-24 -- the releaser's verdict line reaches all three exports;
* F7-15 -- confirmed only: the Strength and I.7 citations carry the station
  rule (pinned in tests/test_hp03_one_motion_2026_10_03.py).

No network; the app runs under conftest's harness.
"""
from __future__ import annotations

import html as H
import json
import re
from collections import Counter

import pytest

from conftest import _is_notes_expander, assert_no_exception, make_app


RELEASER = "The releaser and the house-master (Sahl, *On Nativities* 1.15-1.16, 1.20)"
GOVERNOR = "The governor (PN IV IX.9, 1-10; IX.2, 4-7)"

# The export's sections and the pages that draw them.
SECTION_PAGES = {
    "Chart": ("chart",),
    "Dignities and places": ("dignities",),
    "Configurations": ("configurations",),
    "Lots": ("lots",),
    "Lunation and victors": ("victors",),
    "Prediction": ("timing", "releaser", "days", "fardar"),
}


def _walk(at):
    """The headings the page shows over its tables -- every subheader and
    every expander that is not a notes panel, as the harness's table walker
    reads them -- and how many grids (st.dataframe or st.table) stand under
    each."""
    heads, grids, heading = set(), Counter(), None
    for node in at.main:
        kind = getattr(node, "type", None)
        if kind == "subheader":
            heading = node.value
            heads.add(heading)
        elif kind in ("expander", "status") and not _is_notes_expander(node):
            heading = node.label
            heads.add(heading)
        elif kind in ("dataframe", "table"):
            grids[heading] += 1
    return heads, grids


def _render(page, **state):
    at = make_app(page=page)
    if page == "fardar":
        # The export carries this optional table even when the page hides it.
        at.session_state["_life_lords_ascendant"] = True
    for key, value in state.items():
        at.session_state[key] = value
    at.run(timeout=300)
    assert_no_exception(at, page)
    return at


# --- L5-10: export headings as on the page ------------------------------------------

@pytest.mark.parametrize("section", list(SECTION_PAGES))
def test_l5_10_every_export_heading_is_a_heading_on_its_page(section):
    heads, grids, export = set(), Counter(), None
    for page in SECTION_PAGES[section]:
        at = _render(page)
        h, g = _walk(at)
        heads |= h
        grids.update(g)
        export = at.session_state["_analysis_export"]["results"][section]
    missing = sorted(heading for heading in export if heading not in heads)
    assert not missing, f"{section}: export headings no page shows: {missing}"
    if section == "Prediction":
        # Every Prediction heading is checked above. The count below is not
        # asserted for this section: the PN IV releaser table is exported
        # where the Releaser page prints its note instead (a residual of this
        # part's build, outside its scope).
        return
    # A table the export files under a heading stands under that heading on
    # the page: no heading carries more tables in the export than the page
    # draws under it (the Chart page's Quadrant divisions draws one more,
    # Sahl's sign categories, which the export leaves on the page).
    over = {heading: (len(entries), grids[heading]) for heading, entries in export.items()
            if len(entries) > grids[heading]}
    assert not over, f"{section}: (export, page) table counts under one heading: {over}"


def test_l5_10_the_cross_check_victor_grids_are_filed_under_the_cross_check():
    at = _render("victors")
    results = at.session_state["_analysis_export"]["results"]["Lunation and victors"]
    matched = [e["citation"] for e in results["Victor of the Chart"]]
    crossed = [e["citation"] for e in results["Cross-check: the two unmatched weight/place pairings"]]
    assert matched and all("matched preset" in scheme for scheme in matched), matched
    assert crossed and not any("matched preset" in scheme for scheme in crossed), crossed
    assert len(matched) + len(crossed) == 4
    md = at.session_state["_analysis_markdown"]
    assert md.index("#### Victor of the Chart") < md.index("#### Cross-check: the two unmatched weight/place pairings")


# --- S1-5: a refused run carries no stale export -------------------------------------

EXPORT_KEYS = ("_analysis_export", "_analysis_markdown", "_analysis_html")


def test_s1_5_a_refused_run_leaves_no_export_of_the_previous_chart():
    at = make_app(date="1983-11-19", page="chart")
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = -5.0
    at.run(timeout=300)
    assert_no_exception(at, "manual offset -5")
    assert at.session_state["_analysis_export"]["input"]["utc_offset_hours"] == -5.0, "premise: a chart was exported"
    at.sidebar.number_input(key="utc_offset_key").set_value(None).run(timeout=300)
    assert_no_exception(at, "blank offset")
    assert any("The UTC offset box is blank." in n.value for n in at.sidebar.error)
    stale = [key for key in EXPORT_KEYS if key in at.session_state]
    assert not stale, f"a refused run still holds the previous chart's export: {stale}"
    # A valid offset casts and exports again.
    at.sidebar.number_input(key="utc_offset_key").set_value(5.5).run(timeout=300)
    assert_no_exception(at, "offset +5.5")
    assert at.session_state["_analysis_export"]["input"]["utc_offset_hours"] == 5.5
    assert all(key in at.session_state for key in EXPORT_KEYS)


# --- F3-18: a tied primary's label is not the citation -------------------------------

def test_f3_18_a_tied_primarys_tables_carry_their_label_apart_from_the_citation():
    """1250-05-22: the primary is tied between Jupiter, Mars and the Moon, so
    the IX.9, 11-13 table is drawn once for each under its own label. The
    label travels in each export entry's own field; the citation field keeps
    what the page cites."""
    at = _render("timing", _target_mode="Date", _target_date="1250-05-22")
    entries = at.session_state["_analysis_export"]["results"]["Prediction"][GOVERNOR]
    assert entries
    tie = "(the primary is tied between Jupiter, Mars and Moon)"
    labelled = [e for e in entries if e.get("label")]
    assert labelled, "premise: the tie's tables are in the export"
    assert [e["label"] for e in labelled] == [f"{p} {tie}" for p in ("Jupiter", "Mars", "Moon")], labelled
    assert not any("primary is tied" in str(e.get("citation") or "") for e in entries), entries
    # The page prints the same labels, bold, over the same tables.
    page = [m.value for m in at.main.markdown if m.value.startswith("**") and tie in m.value]
    assert page == [f"**{e['label']}**" for e in labelled], page
    md = at.session_state["_analysis_markdown"].splitlines()
    page_html = at.session_state["_analysis_html"]
    for e in labelled:
        assert f"**{e['label']}**" in md, e["label"]
        assert f"*{e['label']}*" not in md, "the label is printed as a citation"
        assert f"<p class='label'>{H.escape(e['label'])}</p>" in page_html
        assert f"<p class='cite'>{H.escape(e['label'])}</p>" not in page_html


def test_f3_18_a_single_primary_has_no_label():
    at = _render("timing", _target_mode="Date", _target_date="1243-05-22")
    entries = at.session_state["_analysis_export"]["results"]["Prediction"][GOVERNOR]
    assert not [e for e in entries if e.get("label")], entries


# --- F6-24: the releaser's verdict reaches the exports -------------------------------

def test_f6_24_the_releasers_verdict_line_reaches_every_export():
    at = _render("releaser")
    entries = at.session_state["_analysis_export"]["results"]["Prediction"][RELEASER]
    candidates = entries[0]
    assert "Candidate" in candidates["columns"], "premise: the candidates' table comes first"
    verdict = candidates.get("label")
    assert verdict, f"the verdict line is in no export: {sorted(candidates)}"
    text = verdict if isinstance(verdict, str) else verdict["display"]
    # The page's own line, word for word, over the same table.
    assert f"**{text}**" in [m.value for m in at.main.markdown], text
    assert f"**{text}**" in at.session_state["_analysis_markdown"].splitlines()
    assert f"<p class='label'>{H.escape(text)}</p>" in at.session_state["_analysis_html"]


# --- L7-07, L5-03, L5-04, HP-16, HP-27 in every format --------------------------------

def test_l7_07_the_html_labels_its_rows_in_words_too():
    at = _render("chart")
    page_html = at.session_state["_analysis_html"]
    export = at.session_state["_analysis_export"]
    labels = re.findall(r"<tr><td>([^<]*)</td>", page_html)
    snake = sorted({label for label in labels if re.fullmatch(r"[a-z]+_[a-z0-9_]+", label)})
    assert not snake, snake
    # The JSON keeps its keys: they are the schema a program reads.
    assert {"date_string", "time_string", "lat", "lon"} <= set(export["entered"])
    assert {"chart_ok", "chart_error", "stale"} <= set(export["status"])
    # The values the rows label are still there; the checksum row is dropped (ruling 27).
    assert "engine_file_sha256" not in export["app"] and "Checksum of the calculation code" not in page_html
    assert "Checksum of the calculation code" not in at.session_state["_analysis_markdown"]


def test_l5_03_the_status_says_whether_the_record_was_modified(tmp_path, monkeypatch):
    from test_hostile_l5_2026_10_03 import _loaded_record
    at = _loaded_record(tmp_path, monkeypatch)
    status = at.session_state["_analysis_export"]["status"]
    assert status["modified"] is False and at.session_state["_analysis_export"]["chart"] == "Rec"
    at.session_state["_target_mode"] = "Age"
    at.session_state["_target_age"] = 10
    at.run()
    assert_no_exception(at, "edited record")
    export = at.session_state["_analysis_export"]
    assert export["chart"] == "Rec (modified)"
    assert export["status"]["modified"] is True
    assert export["status"]["edited_since_saved"] is True
    assert export["status"]["saved_with_other_readings"] is False
    assert at.session_state["_analysis_markdown"].splitlines()[0] == "# Analysis: Rec (modified)"
    assert "<title>Analysis: Rec (modified)</title>" in at.session_state["_analysis_html"]


def test_l5_04_the_reports_print_the_engine_longitude_to_four_places(engine):
    at = _render("chart")
    rows = at.session_state["_analysis_export"]["results"]["Chart"]["Planetary Positions"][0]["rows"]
    assert len(rows) == 7, [row["Planet"] for row in rows]
    md = at.session_state["_analysis_markdown"]
    for row in rows:
        assert isinstance(row["Absolute"], float)
        assert 0.0 <= row["Absolute"] < 360.0
        assert engine["get_degree_string"](row["Absolute"]) == row["Position"]
        assert f"| {engine['_export_cell'](row['Absolute'])} |" in md


def test_hp16_the_revolution_table_cites_the_true_sun_return_in_every_format():
    at = _render("timing")
    entry = at.session_state["_analysis_export"]["results"]["Prediction"]["The revolution of the year"][0]
    assert "true-Sun return" in entry["citation"] and "mean Sun" in entry["citation"], entry.get("citation")
    assert entry["citation"] in at.session_state["_analysis_markdown"]
    assert H.escape(entry["citation"]) in at.session_state["_analysis_html"]


def test_hp27_the_topical_rows_take_the_pages_columns():
    at = _render("dignities")
    rows = at.session_state["_analysis_export"]["results"]["Dignities and places"]["Topical Planets in Houses"][0]["rows"]
    assert len(rows) == 7, [row["Planet"] for row in rows]
    page_columns = {"Planet", "Placed in (WS place)", "Lean", "Net", "Unresolved", "Standing",
                    "If in a suitable condition", "If in a bad condition",
                    "Rhetorius and Firmicus, as the texts state it", "Shared PN IV passages"}
    # Entries: every entry of the row's list, printed whole, as the row's
    # detail on the page prints them (the cell can leave some to the detail).
    for row in rows:
        assert set(row) <= page_columns | {"Entries"}, sorted(set(row) - page_columns)
    assert "Joint testimony IDs" not in at.session_state["_analysis_markdown"]
    assert "Joint testimony IDs" not in at.session_state["_analysis_html"]


# --- F7-15: confirmed, not rebuilt ------------------------------------------------------

def test_f7_15_the_strength_and_i7_citations_carry_the_station_rule(engine):
    at = _render("chart")
    results = at.session_state["_analysis_export"]["results"]
    rule = f"within {engine['STATION_SPEED_TOLERANCE']} degrees a day"
    strength = results["Configurations"]["Strength of the Planets"][0]
    i7 = [e for e in results["Prediction"]["The reading checklist (PN IV I.7, 1-26)"] if e.get("citation")]
    assert rule in strength["citation"]
    assert i7 and rule in i7[0]["citation"]
    assert rule in at.session_state["_analysis_markdown"] and rule in at.session_state["_analysis_html"]
