"""column_config on the tables.

Widths and help text only. The doctrine fixtures (tests/fixtures/tables.json)
compare a table's own DataFrame -- its values, its column names, its column
order -- and none of that is touched here: every DataFrame is built exactly
as it was, and column_config only says how a column already there is
displayed. These tests read the rendered element's own proto rather than the
source, so a column_config that failed to reach Streamlit's wire format
would be caught here even if the Python call that built it looked right.
"""
import json

import re

import pytest

from conftest import PAGES, READING_DEPTHS, TextTable, assert_no_exception, find_table, make_app


def _column_config(dataframe_element):
    return json.loads(dataframe_element.proto.columns)


# --- Every page still renders, at both reading depths ---------------------

@pytest.mark.parametrize("page", PAGES)
@pytest.mark.parametrize("depth", READING_DEPTHS)
def test_every_page_still_renders_with_column_config_added(page, depth):
    at = make_app(page=page)
    at.session_state["_reading_depth"] = depth
    at.run()
    assert_no_exception(at, f"{page}, {depth}")


# --- The tick grids: the number moves from the header into its tooltip ----

def test_strength_grid_moves_the_sentence_number_into_the_tooltip():
    at = make_app(page="configurations")
    at.run()
    assert_no_exception(at, "configurations")
    body = find_table(at, "Strength of the Planets").proto.body
    assert re.search(r'title="Sahl, The Introduction Ch\. 3, 78"[^>]*>[^<]*(?:<[^>]*>)*excellent place', body)
    assert re.search(r'title="Sahl, The Introduction Ch\. 3, 88"[^>]*>[^<]*(?:<[^>]*>)*gender match', body)
    assert "78 excellent place" not in body and "88 gender match" not in body


def test_weakness_grid_moves_the_sentence_number_into_the_tooltip():
    at = make_app(page="configurations")
    at.run()
    assert_no_exception(at, "configurations")
    body = find_table(at, "Weakness of the Planets").proto.body
    assert re.search(r'title="Sahl, The Introduction Ch\. 3, 91"[^>]*>[^<]*(?:<[^>]*>)*falling, averse ASC', body)
    assert "91 falling, averse ASC" not in body


# --- A long column, from _finding() ----------------------------------------

def test_a_finding_s_long_columns_are_a_text_table_s_and_wrap_where_they_stand():
    at = make_app(page="delineations")
    at.run()
    assert_no_exception(at, "delineations")
    table = find_table(at, "The Moon on the third day (Sahl)")
    assert isinstance(table, TextTable)
    assert table.headings == ["What is read", "In this chart", "What the text says"]


def test_a_direct_table_s_long_cells_stand_in_a_text_table_too():
    """Not every text table comes through _finding(): the Timing page's own
    tables call the helper directly."""
    at = make_app(page="timing")
    at.run()
    assert_no_exception(at, "timing")
    table = find_table(at, "The revolution of the year")
    assert isinstance(table, TextTable)
    assert "Source" in table.value.columns and len(table.value) > 0


# --- A Yes/No column: width only, still text, values untouched ------------

def test_a_yes_no_column_is_narrow_text_not_a_checkbox():
    at = make_app(page="dignities")
    at.run()
    assert_no_exception(at, "dignities")
    node = find_table(at, "Sect")
    config = _column_config(node)
    for col in ("Above horizon", "Domain (hayz)", "Of the chart's sect"):
        assert isinstance(config[col]["width"], int), "a column is as wide as what it holds"
        assert config[col]["type_config"]["type"] == "text"
        assert "CheckboxColumn" not in json.dumps(config[col])
    values = set(node.value["Above horizon"].unique().tolist()) | set(node.value["Of the chart's sect"].unique().tolist())
    assert values <= {"Yes", "No"}, "the ruling: values do not change on this branch"
