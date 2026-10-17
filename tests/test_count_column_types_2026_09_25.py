"""The mixed-type Count column (queue item 7b of process/HANDOFF_2026-09-25b.md),
plus the two further mixed-type columns the blind check of this branch found
in scope: the build brief asked for every such column, not only Count's.

A planet's testimony Count was an int on most rows, but on a row with at
least one unresolved testimony (``is_unresolved`` on a Testimonies entry's
``result``) app.py wrote a second sentence into the same cell -- "N resolved;
M unresolved" -- so the column held both ints and strings. pandas keeps such
a column as ``object`` and pyarrow's ``Table.from_pandas`` cannot type it
(reproduced directly below with the exact strings this app once wrote);
Streamlit catches the ``ArrowInvalid``, logs it, and falls back to
stringifying the whole column, which is the display fault this file pins
against: 1240-03-31 (Florence, 14:30 LMT) gives Venus one unresolved
testimony in each of Strength of the Planets (Sahl, Ch. 3, 78-88) and
Weakness of the Planets (Ch. 3, 91-100), on both the tick grid and its
answer key.

The fix (app.py's ``_tick_grid``): Count stays the engine's own int in every
row; a planet's unresolved testimonies go in their own column, Unresolved --
a plain float64 column (None upcast to NaN by pandas, on a grid with at
least one such row), so it types alongside Count as a NumberColumn instead
of sitting in a TextColumn of digits beside it (note 8 of the blind check).

The same fault, found elsewhere by the blind check:

* Favor & Recompense's "Recompense (days)" (Configurations page) held a
  float on a row where the forward search found the payback and a sentence
  ("none within N days...") on a row where it did not (``engine.py``,
  ``evaluate_favor_and_recompense``). Fixed the same way Moon Defects
  already was: the cell is a string throughout, the found day rounded and
  stringified rather than left a float. Pinned with 1239-06-14, which has
  both kinds of row in one table.

* Indicator 15's "relationship details" (Timing page), column "Connected",
  held a plain bool on most rows and the display string of an
  UnresolvedResult on a row whose connection is left to one of the
  permitted completions of an unresolved connection
  (``evaluate_with_connection_uncertainty`` raising ``_ConnectionChoice`` in
  ``_connection_decision``, tried both ways and merged row by row inside
  ``pn4_timing_bundle``, which is ``@_connection_aware``). The per-row bool
  ``pn4_indicator_relationships`` itself returns is never unresolved -- the
  ambiguity is introduced by that merge, after the function returns -- so
  the fix is a single normalisation in app.py, right after
  ``pn4 = pn4_timing_bundle(...)``, turning only the resolved rows' bool
  Connected into the text "Yes"/"No"; the UnresolvedResult itself is left
  in place, so its reason, source and alternatives still reach the export,
  and ``_display_rows`` still turns it to the page's own words at render
  time, exactly as it did before this fix. Pinned with 1700-02-28
  (Venus-Mercury).
"""
import logging

import pandas as pd
import pyarrow as pa
import pytest

from conftest import CHARTS, READING_DEPTHS, assert_no_exception, make_app, table_nodes

FAULT_CHART = "1240-03-31"

# The exact message streamlit.dataframe_util logs when pa.Table.from_pandas
# raises on a column and it falls back to stringifying the whole thing
# (dataframe_util.convert_pandas_df_to_arrow_table, still true of the
# Streamlit pinned here): a page that never hits this never asked pyarrow
# to type a column it could not. AppTest renders for real -- the same
# marshalling a served app would do -- so this fires exactly when a served
# reader would have seen the fallback, and the column is already repaired
# to a uniform string column by the time any dataframe element is read
# back, which is why this suite checks the log rather than the cell.
_ARROW_FALLBACK = "Serialization of dataframe to Arrow table was unsuccessful"


def test_a_count_column_mixing_ints_and_resolved_unresolved_strings_defeats_arrow():
    """Not a regression pin -- a fixed demonstration of the mechanism the
    rest of this file guards against, so the fault this branch was built
    for cannot be mistaken for a different one."""
    df = pd.DataFrame([{"Planet": "Mercury", "Count": 3},
                       {"Planet": "Saturn", "Count": "2 resolved; 1 unresolved"}])
    with pytest.raises(pa.ArrowInvalid):
        pa.Table.from_pandas(df)


# --- The mixed-type column, on the chart and page that showed it -----------

@pytest.mark.parametrize("depth", READING_DEPTHS)
def test_configurations_logs_no_arrow_fallback_on_the_fault_chart(tmp_path, monkeypatch, caplog, depth):
    """The development repository's #49, its own repro chart, at both reading depths (the tabbed and
    the untabbed Strength & Weakness view): pyarrow must type every column
    Configurations draws on its first attempt, not on a caught retry."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date=FAULT_CHART, page="configurations")
    at.session_state["_reading_depth"] = depth
    with caplog.at_level(logging.INFO, logger="streamlit.dataframe_util"):
        at.run(timeout=300)
    assert_no_exception(at, f"configurations {FAULT_CHART} {depth}")
    fallbacks = [r.getMessage() for r in caplog.records if _ARROW_FALLBACK in r.getMessage()]
    assert not fallbacks, fallbacks


@pytest.mark.parametrize("date", sorted(CHARTS) + [FAULT_CHART])
def test_configurations_logs_no_arrow_fallback_on_any_harness_chart(tmp_path, monkeypatch, caplog, date):
    """Coverage, the harness's other six charts included: none of them
    happens to give a planet an unresolved testimony, so this is the net
    that catches the fault reappearing on a chart nobody thought to add."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date=date, page="configurations")
    with caplog.at_level(logging.INFO, logger="streamlit.dataframe_util"):
        at.run(timeout=300)
    assert_no_exception(at, f"configurations {date}")
    fallbacks = [r.getMessage() for r in caplog.records if _ARROW_FALLBACK in r.getMessage()]
    assert not fallbacks, fallbacks


# --- Both counts still shown, for the planet that has both ------------------

def test_a_planet_with_unresolved_testimonies_still_shows_both_counts(tmp_path, monkeypatch):
    """Venus on 1240-03-31: Count (the resolved testimonies) and Unresolved
    (the unresolved ones) are both visible, on the grid and on its answer
    key, and Count stays a genuine integer column throughout -- the reader
    loses nothing that the old single-cell sentence said."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date=FAULT_CHART, page="configurations").run(timeout=300)
    assert_no_exception(at, f"configurations {FAULT_CHART}")
    found = table_nodes(at)
    strength_grid = next(node for heading, node in found if heading == "Strength of the Planets").value
    weakness_grid = next(node for heading, node in found if heading == "Weakness of the Planets").value
    answer_keys = [node.value for heading, node in found if heading == "Answer key: testimonies in words"]
    assert len(answer_keys) == 2, "one answer key per grid"
    strength_answer, weakness_answer = answer_keys

    for grid, answer, expected_count in ((strength_grid, strength_answer, 2), (weakness_grid, weakness_answer, 4)):
        assert pd.api.types.is_integer_dtype(grid["Count"]), grid["Count"].dtype
        assert pd.api.types.is_integer_dtype(answer["Count"]), answer["Count"].dtype
        # Unresolved is a NumberColumn beside Count (note 8 of the blind
        # check), backed by a plain float64 column: None upcasts the whole
        # column to float64 (NaN, not a pandas nullable Int64's pd.NA,
        # which prints as "<NA>" and trips test_rendered_capitals_2026_09_21's
        # guard -- NaN's lower-case "nan" does not).
        assert str(grid["Unresolved"].dtype) == "float64", grid["Unresolved"].dtype
        assert str(answer["Unresolved"].dtype) == "float64", answer["Unresolved"].dtype
        for df in (grid, answer):
            row = df[df["Planet"] == "Venus"].iloc[0]
            assert row["Count"] == expected_count, row["Count"]
            assert row["Unresolved"] == 1, row["Unresolved"]
            others = df[df["Planet"] != "Venus"]
            assert others["Unresolved"].isna().all(), others["Unresolved"].tolist()


# --- Defect 1b-1: Favor & Recompense's "Recompense (days)" -----------------

RECOMPENSE_FAULT_CHART = "1239-06-14"


@pytest.mark.parametrize("depth", READING_DEPTHS)
def test_configurations_logs_no_arrow_fallback_on_the_recompense_fault_chart(tmp_path, monkeypatch, caplog, depth):
    """1239-06-14 gives Favor & Recompense both a found payback (a day
    count) and a search that ran out (the horizon sentence) in the same
    table: pyarrow must type "Recompense (days)" on the first attempt."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date=RECOMPENSE_FAULT_CHART, page="configurations")
    at.session_state["_reading_depth"] = depth
    with caplog.at_level(logging.INFO, logger="streamlit.dataframe_util"):
        at.run(timeout=300)
    assert_no_exception(at, f"configurations {RECOMPENSE_FAULT_CHART} {depth}")
    fallbacks = [r.getMessage() for r in caplog.records if _ARROW_FALLBACK in r.getMessage()]
    assert not fallbacks, fallbacks


def test_recompense_days_stays_readable_and_uniformly_typed(tmp_path, monkeypatch):
    """Both a found day and an unfound search still read in words, and the
    whole column is one Arrow-compatible type (str) throughout. Not a
    regression pin by itself: Streamlit's own fallback already stringifies
    the column before AppTest can read it back, so reverting the engine fix
    still passes this assertion (note 3 of the 2026-09-25 recheck) -- only
    the two log tests above, which read the fallback before it repairs
    anything, actually catch a revert."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date=RECOMPENSE_FAULT_CHART, page="configurations").run(timeout=300)
    assert_no_exception(at, f"configurations {RECOMPENSE_FAULT_CHART}")
    found = table_nodes(at)
    table = next(node for heading, node in found if heading == "Favor & Recompense").value
    values = table["Recompense (days)"].tolist()
    assert all(isinstance(v, str) for v in values), values
    assert any(v.replace(".", "", 1).isdigit() for v in values), values
    assert any("none within" in v and "the search ends there" in v for v in values), values


# --- Defect 1b-2: Indicator 15's "Connected" --------------------------------

CONNECTED_FAULT_CHART = "1700-02-28"


@pytest.mark.parametrize("depth", READING_DEPTHS)
def test_timing_logs_no_arrow_fallback_on_the_connected_fault_chart(tmp_path, monkeypatch, caplog, depth):
    """1700-02-28: Venus-Mercury's Connected is left to one of the permitted
    completions of an unresolved connection, and the two tried disagree --
    pyarrow must still type the whole column on one pass."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date=CONNECTED_FAULT_CHART, page="timing")
    at.session_state["_reading_depth"] = depth
    with caplog.at_level(logging.INFO, logger="streamlit.dataframe_util"):
        at.run(timeout=300)
    assert_no_exception(at, f"timing {CONNECTED_FAULT_CHART} {depth}")
    fallbacks = [r.getMessage() for r in caplog.records if _ARROW_FALLBACK in r.getMessage()]
    assert not fallbacks, fallbacks


def test_indicator_15_connected_is_text_and_the_unresolved_row_keeps_its_reason(tmp_path, monkeypatch):
    """Connected is text throughout -- Yes, No, or (unchanged from before
    this fix) an UnresolvedResult's own reasoned sentence, via
    _display_rows at render time -- and 1700-02-28 actually has all three.
    Only the resolved rows' bool is turned to text; the ambiguous row's
    full reason is not thrown away for the sake of a uniform column
    (defect 5 of the 2026-09-25 recheck)."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date=CONNECTED_FAULT_CHART, page="timing").run(timeout=300)
    assert_no_exception(at, f"timing {CONNECTED_FAULT_CHART}")
    found = table_nodes(at)
    table = next(node for heading, node in found if heading == "Indicator 15: relationship details").value
    values = table["Connected"].tolist()
    assert set(values) & {"Yes", "No"} == {"Yes", "No"}, values
    unresolved = [v for v in values if v not in ("Yes", "No")]
    assert len(unresolved) == 1, values
    assert unresolved[0].startswith("Unresolved") and "depends on an unresolved connection" in unresolved[0], unresolved


def test_the_unresolved_connected_cell_keeps_its_reason_and_source_in_the_export(tmp_path, monkeypatch):
    """The JSON export's one ambiguous row keeps the full UnresolvedResult
    -- reason, source and alternatives -- rather than the bare word
    Unresolved the first version of this fix threw them away for (defect 5
    of the 2026-09-25 recheck); the resolved rows are still plain Yes/No
    text, so the column reads the same on the page and in the export."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date=CONNECTED_FAULT_CHART, page="timing").run(timeout=300)
    assert_no_exception(at, f"timing {CONNECTED_FAULT_CHART}")
    export = at.session_state["_analysis_export"]
    entries = export["results"]["Prediction"]["Indicator 15: relationship details"]
    rows = [row for entry in entries for row in entry["rows"]]
    resolved = [row["Connected"] for row in rows if not isinstance(row["Connected"], dict)]
    assert resolved and set(resolved) <= {"Yes", "No"}, resolved
    unresolved = [row["Connected"] for row in rows if isinstance(row["Connected"], dict)]
    assert len(unresolved) == 1, unresolved
    cell = unresolved[0]
    assert cell["result_type"] == "UnresolvedResult"
    assert "depends on an unresolved connection" in cell["reason"], cell
    assert "Sahl, The Introduction Ch. 3" in cell["source"], cell
    assert {alt["value"] for alt in cell["alternatives"]} == {True, False}, cell
