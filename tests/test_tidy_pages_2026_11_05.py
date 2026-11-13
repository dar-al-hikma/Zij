"""The tidy list: the page's words, tables and places.

A page and the two reports print the page's headings and Dykes's spellings; the
saved-data file keeps its keys and words, but for four sentences that had gone
stale. The Domain choice stands over its table, the stars harming eyes in a tab
of their own, and the scores' last numbers leave the pages and the reports.
"""
from __future__ import annotations

import ast
import collections
import html
import json
import re
from datetime import time
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from conftest import APP_PATH, assert_no_exception, make_app, sync_engine_to_environment, table_nodes
from engine import PAGE_CELL_WORDS, PAGE_COLUMN_NAMES, TIME_STANDARD_OPTIONS, page_words

ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
LMT, MANUAL = TIME_STANDARD_OPTIONS[0], TIME_STANDARD_OPTIONS[2]
EYES = "Stars harming eyes"
DIGNITY = "Planetary Dignity Evaluation (Hellenistic/Rhetorius reconstruction)"
GOVERNOR = "Governor of the syzygy degree: the five lords under On Nativities 1.7, 3-7"
NATURAL = "Natural connections"
CONDITION = "Planetary Condition"
PAGES = ["chart", "dignities", "delineations", "configurations", "lots", "victors", "fixed-stars", "timing",
         "releaser", "days", "fardar"]


def _page(page, date="1240-05-23", **seed):
    at = make_app(date=date, page=page, timeout=240)
    for key, value in seed.items():
        at.session_state[key] = value
    at.run()
    assert_no_exception(at, page)
    return at


def _fresh():
    """The app as it opens: no seed at all, so the example chart."""
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=240)
    at.run()
    assert_no_exception(at, "fresh")
    return at


def _texts(at):
    """What a page says in prose, every kind of block."""
    return [node.value for kind in ("caption", "markdown", "subheader", "warning", "info", "header")
            for node in getattr(at, kind)]


def _tables(at):
    return {heading: node.value for heading, node in table_nodes(at)}


def _results(at):
    return at.session_state["_analysis_export"]["results"]


def _strip(at):
    return at.caption[0].value


# --- The example chart --------------------------------------------------------

def test_the_chart_the_app_opens_on_is_called_an_example_and_says_what_it_is_for():
    at = _fresh()
    assert _strip(at).startswith("Example chart — Florence")
    assert ("These sample birth details let you explore the tables. Enter or open a chart to replace them."
            in [node.value for node in at.caption])
    assert "Example chart — Florence" in at.session_state["_analysis_markdown"]
    assert "Example chart — Florence" in at.session_state["_analysis_html"]


def test_the_saved_data_file_keeps_its_word_for_the_example():
    assert _fresh().session_state["_analysis_export"]["chart"] == "Unsaved chart"


def test_the_mark_clears_as_soon_as_the_chart_changes():
    at = _fresh()
    at.session_state["date_input_key"] = "1240-05-24"
    at.run()
    assert_no_exception(at, "changed")
    assert _strip(at).startswith("Unsaved chart")
    assert not any("sample birth details" in node.value for node in at.caption)


def test_coordinates_typed_in_are_no_example():
    assert _strip(_page("chart")).startswith("Unsaved chart")


# --- Words --------------------------------------------------------------------

@pytest.mark.parametrize("plain, printed", [
    ("Abu Ma'shar's rule", "Abū Ma'shar's rule"),
    ("Masha'allah, On Nativities 1.23", "Māshā'allāh, On Nativities 1.23"),
    ("following al-Qabisi", "following al-Qabīsī"),
    ("Al-Qabisi's bridge", "Al-Qabīsī's bridge"),
    ("the app's fallback", "this app's fallback"),
    ("the Chronocrator Matrix's profection", "the annual profection"),
    ("The releaser directed forward to the fourteen cutting stars", "Each releaser directed forward to the fourteen cutting stars"),
])
def test_the_page_s_words(plain, printed):
    assert page_words(plain) == printed


@pytest.mark.parametrize("stands", [
    "ITA I.18, al-Qabisi\u00a0I.22",                 # a kept table's example: its spaces are unbreaking
    'Dykes: "Abu Ma\'shar seems to prefer"',
    "“Abu Ma'shar”",
    "ITA VIII.1.3, al-Qabisi IV.4",
    "al-Qabisi I.57b",
    "the application",
])
def test_a_quotation_and_a_locator_stand_as_printed(stands):
    assert page_words(stands) == stands


def test_a_second_seconds_mark_opens_no_quotation():
    assert page_words("59' 08\" a day, Abu Ma'shar, 12\" more") == "59' 08\" a day, Abū Ma'shar, 12\" more"


@pytest.mark.parametrize("page", PAGES)
def test_no_table_prints_a_name_the_page_has_renamed(page):
    at = _page(page)
    for heading, frame in _tables(at).items():
        assert not set(frame.columns) & set(PAGE_COLUMN_NAMES) - set(PAGE_COLUMN_NAMES.values()), heading
        for column in frame.columns:
            assert not set(frame[column].map(str)) & set(PAGE_CELL_WORDS), (heading, column)
            assert page_words(column) == column, (heading, column)


def test_the_lots_tables_share_a_heading_for_the_lot():
    tables = _tables(_page("lots"))
    assert "Lot" in tables["Classical Lots"].columns and "Lot Name" not in tables["Classical Lots"].columns


def test_the_annual_profection_is_named_alike_on_its_page_and_in_the_reports():
    at = _page("fardar")
    assert "Annual profection" in [node.value for node in at.subheader]
    frame = _tables(at)["Annual profection"]
    assert {"Active point", "Ruler"} <= set(frame.columns) and frame["Technique"].tolist() == ["Annual profection"]
    report = at.session_state["_analysis_markdown"]
    assert "Annual profection" in report and "Chronocrator" not in report
    assert "| Technique | Active point | Ruler |" in report
    assert not any("Chronocrator" in text for text in _texts(at))


def test_the_saved_data_file_keeps_its_keys_and_words():
    results = _results(_page("chart"))
    lots = results["Lots"]["Classical Lots"][0]["rows"][0]
    assert {"Lot Name", "WS place", "Sign Dispositor"} <= set(lots)
    profection = results["Prediction"]["Annual profection"][0]["rows"][0]
    assert profection["Technique"] == "Annual Profection" and "Active Ruler" in profection and "Active Point" in profection
    assert "Abu Ma'shar" in str(results) and "Abū Ma'shar's" not in str(results["Configurations"][CONDITION][0]["citation"])
    assert "Topical House Lords (Masha'allah)" in results["Dignities and places"]


def test_the_reports_print_the_page_s_headings_and_names():
    at = _page("chart")
    for report in (at.session_state["_analysis_markdown"], at.session_state["_analysis_html"]):
        report = report.replace("&#x27;", "'")
        report = re.sub(r"<style>.*?</style>", "", report, flags=re.S)
        for old in ("WS place", "Sign Dispositor", "Lot Name", "Domicile Lord", "Exaltation Lord", "Active Point"):
            assert old not in report, old
        assert "Whole-sign place" in report and "Domicile lord" in report


# --- Hovers and sentences -----------------------------------------------------

def test_the_fitting_infortune_hover_no_longer_repeats_the_note_under_it():
    at = _page("configurations")
    box = next(node for node in at.checkbox if "Fitting infortune" in node.label)
    assert "Off by default" in box.help and "FITTING" not in box.help
    assert "Choices Ch. 1, 12" in box.help


def test_the_collection_policy_is_read_above_its_table_or_where_the_table_would_stand():
    assert "glance=COLLECTION_POLICY" not in APP_SOURCE
    assert "summary=COLLECTION_POLICY" in APP_SOURCE
    assert 'absent=f"{COLLECTION_POLICY} None in this chart."' in APP_SOURCE


def test_no_page_sentence_says_no_unique_inverse():
    assert "unique inverse" not in re.sub(r"^\s*#.*$", "", APP_SOURCE, flags=re.M)


def test_the_retired_clauses_are_gone():
    for clause in ("no tie rule", "they move nothing", "2.11, 2 shown beside it", "the first lord's time being read"):
        assert clause not in APP_SOURCE, clause


def test_the_condition_detail_does_not_repeat_the_sentence_above_the_table():
    at = _page("configurations", planetary_condition_detail="Venus")
    said = [node.value for node in at.caption] + [node.value for node in at.markdown]
    assert sum("VII.6, 46" in text and text.startswith("This") for text in said) <= 1


def test_the_image_table_says_its_search_finds_a_point():
    at = _page("timing")
    assert "The table's search finds a point; a cell opens in full." in [node.value for node in at.caption]


def test_the_monthly_turn_hover_points_to_its_note():
    at = _page("days")
    radio = next(node for node in at.radio if node.label == "Monthly profections turn")
    assert "complicated, probably wrong" not in radio.help and "in the notes under the table" in radio.help


# --- The Domain choice --------------------------------------------------------

def test_the_domain_choice_stands_over_its_table_in_no_column_beside_it():
    tree = ast.parse(APP_SOURCE)
    page = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "page_dignities")
    assert "domain_col" not in ast.unparse(page)
    calls = [node for node in page.body if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
             and getattr(node.value.func, "id", "") == "_reading_radio"]
    assert any(call.value.args[0].value == "Domain (hayz)" for call in calls), "at the page's top level, not in a column"


# --- No reading in a narrow column ---------------------------------------------

_READING_CALLS = {"_reading_radio", "_reading_checkbox"}
_LONG_READING = 40  # characters of a label, past which a narrow column cuts it


def _column_bindings(tree):
    """Each row of st.columns, by line: (line, name, place in the row or None for all of it, its share of the row)."""
    bound = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
                and getattr(node.value.func, "attr", "") == "columns" and getattr(node.value.func.value, "id", "") == "st"):
            continue
        spec = node.value.args[0]
        widths = ([1] * spec.value if isinstance(spec, ast.Constant) else
                  [item.value for item in spec.elts] if isinstance(spec, ast.List) else None)
        target = node.targets[0]
        if isinstance(target, ast.Tuple):
            bound += [(node.lineno, item.id, place, widths[place] / sum(widths) if widths else 1)
                      for place, item in enumerate(target.elts)]
        elif widths:
            bound += [(node.lineno, f"{target.id}[{place}]", place, width / sum(widths)) for place, width in enumerate(widths)]
    return bound


def _readings_in_narrow_columns(source):
    """(line, label) of a reading in a column it should not stand in. Past a row's first
    column it moves with the window, away from what it changes; in a narrow first column
    it keeps the page's left edge, so only a long label suffers. A popover is its own panel."""
    tree = ast.parse(source)
    bound = _column_bindings(tree)
    refused = []

    def visit(node, column):
        if isinstance(node, ast.With):
            for item in node.items:
                held = item.context_expr
                if getattr(getattr(held, "func", None), "attr", "") == "popover":
                    column = None
                name = ast.unparse(held)
                found = [entry for entry in bound if entry[1] == name and entry[0] < node.lineno]
                if found:
                    column = found[-1]
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") in _READING_CALLS and column:
            label = node.args[0].value if isinstance(node.args[0], ast.Constant) else ast.unparse(node.args[0])
            if column[2] > 0 or (column[3] < 0.5 and len(label) > _LONG_READING):
                refused.append((node.lineno, label))
        for child in ast.iter_child_nodes(node):
            visit(child, column)

    visit(tree, None)
    return refused


def test_no_reading_stands_in_a_narrow_column():
    assert [label for _, label in _readings_in_narrow_columns(APP_SOURCE)] == []


@pytest.mark.parametrize("planted", [
    'v_view, v_layout, v_opts = st.columns([2.2, 1.4, 0.9], vertical_alignment="bottom")\nwith v_layout:\n    _reading_radio("Wheel layout", OPTIONS, "a", "b")\n',
    'left, right = st.columns([3, 1])\nwith right:\n    _reading_radio("House-based Lot construction", OPTIONS, "a", "b")\n',
    'c_one, c_two = st.columns([2.5, 1.2])\nwith c_two:\n    _reading_checkbox("Fitting infortune", "a", "b")\n',
    'row = st.columns([3, 1])\nwith row[1]:\n    _reading_radio("Target by", OPTIONS, "a", "b")\n',
    'c_one, c_two = st.columns([1, 3])\nwith c_one:\n    _reading_checkbox("Fitting infortune: the malefic that rules the Ascendant", "a", "b")\n',
])
def test_that_pin_refuses_a_reading_planted_back_in_a_column(planted):
    assert _readings_in_narrow_columns(planted)


# --- Designation --------------------------------------------------------------

def test_the_star_tables_say_designation():
    at = _page("fixed-stars")
    assert "Greek form" not in APP_SOURCE.replace("in its Greek form", "")
    export = at.session_state["_fixed_stars_export"]["results"]["Fixed stars"]
    rows = next(entry["rows"] for heading, entries in export.items() if heading.startswith("Star list") for entry in entries)
    assert "Designation" in rows[0] and "Greek form" not in rows[0]


# --- Stars harming eyes -------------------------------------------------------

def test_the_stars_harming_eyes_stand_in_a_tab_of_the_fixed_stars_page():
    at = _page("fixed-stars")
    assert [tab.label for tab in at.tabs][:3] == ["Axes", "Star list", EYES]
    frame = _tables(at)[EYES]
    assert list(frame.columns) == ["Star", "As printed", "Longitude", "Latitude", "Catalogue designation", "Witnesses"]
    assert not any("Display only" in text for text in _texts(at))


def test_their_rows_are_the_engine_s_for_the_chart_s_moment():
    at = _page("fixed-stars")
    exported = at.session_state["_fixed_stars_export"]["results"]["Fixed stars"][EYES][0]["rows"]
    frame = _tables(at)[EYES]
    assert frame["Star"].tolist() == [page_words(row["Star"]) for row in exported]
    assert frame["Longitude"].tolist() == [row["Longitude"] for row in exported]
    assert [" ".join(text.split()) for text in frame["Witnesses"]] == [" ".join(page_words(row["Witnesses"]).split()) for row in exported]


def test_delineations_keeps_the_places_with_one_line_to_the_tab():
    at = _page("delineations")
    assert EYES not in _tables(at) and EYES not in [node.value for node in at.subheader]
    assert "The stars harming eyes have their own table on the Fixed stars page." in [node.value for node in at.caption]


def test_the_sources_page_speaks_of_the_places_alone():
    assert "stars harming eyes show" not in APP_SOURCE
    assert APP_SOURCE.count("The places harming the eyesight show all their texts at both settings.") == 3


def test_the_main_report_s_scope_drops_them_and_the_fixed_stars_export_carries_them():
    at = _page("fixed-stars")
    export = at.session_state["_fixed_stars_export"]["results"]["Fixed stars"]
    assert export[EYES][0]["rows"]
    assert EYES in at.session_state["_fixed_stars_markdown"]
    chart = _page("chart")
    assert EYES not in chart.session_state["_analysis_markdown"]
    assert EYES not in chart.session_state["_analysis_html"]


# --- The scores' last numbers -------------------------------------------------

def test_ess_acc_and_their_excuse_leave_the_page_and_the_reports_and_stay_in_the_file():
    at = _page("dignities")
    assert not {"Ess", "Acc", "Ranking score"} & set(_tables(at)[DIGNITY].columns)
    assert {"Essential Dignities", "Accidental Conditions"} <= set(_tables(at)[DIGNITY].columns)
    assert not any("point weights" in text for text in _texts(at))
    for report in (at.session_state["_analysis_markdown"], at.session_state["_analysis_html"]):
        assert "point weights" not in report
    row = _results(at)["Dignities and places"][DIGNITY][0]["rows"][0]
    assert {"Ess", "Acc", "Ranking score"} <= set(row)


def test_the_governor_s_table_keeps_its_sourced_columns_alone():
    at = _page("victors")
    frame = _tables(at)[GOVERNOR]
    assert not {"Model points", "Model"} & set(frame.columns)
    assert {"Planet", "Verdict", "Direct (1.7, 4)", "Stake or own dignity (1.7, 7)"} <= set(frame.columns)
    assert "Model points" not in at.session_state["_analysis_markdown"]
    row = _results(at)["Lunation and victors"][GOVERNOR][0]["rows"][0]
    assert {"Model points", "Model"} <= set(row)


def test_natural_connections_says_its_standing_once_above_the_table():
    at = _page("configurations", date="1975-03-14")
    assert "direct: sign pairs" not in at.session_state["_analysis_markdown"]
    frames = _tables(at)
    if NATURAL in frames:
        assert "Standing" not in frames[NATURAL].columns
        assert any("Every row stands as the text states it" in text for text in _texts(at))
        assert "Every row stands as the text states it" in at.session_state["_analysis_markdown"]
    results = _results(at)["Configurations"]
    if NATURAL in results:
        assert results[NATURAL][0]["rows"][0]["Standing"].startswith("direct:")


def test_the_saved_data_file_s_four_sentences_no_longer_speak_of_the_pages():
    export = _page("chart").session_state["_analysis_export"]
    results = export["results"]
    assert "ranking convenience" not in results["Dignities and places"][DIGNITY][0]["citation"]
    assert "as the page says" not in results["Configurations"][CONDITION][0]["citation"]
    assert "only this file keeps" in export["scope"]
    assert "in the file's own spellings and capitals" in export["scope"]
    assert "but not the Fixed stars page, which has its own export" in export["scope"]
    assert EYES not in export["scope"]


def test_a_report_s_scope_says_the_cells_are_the_pages():
    report = _page("chart").session_state["_analysis_markdown"]
    assert "with their cells as the pages print them." in report and "only this file keeps" not in report


def test_where_the_seven_classes_are_is_named():
    at = _page("delineations")
    assert any("(On Nativities 2.1, 2-9)" in text for text in _texts(at))


# --- Tables ---------------------------------------------------------------------

def test_i7_s_long_readings_go_under_their_rows_all_together():
    source = APP_SOURCE[APP_SOURCE.index("_i7_planet_rows = _display_rows"):][:300]
    assert "under=('Whole sign (10-11)', 'By degree (12-13)', 'Received by (14)', 'Return (19)')" in source


def test_follows_the_stake_keeps_its_row_within_the_narrowest_window():
    assert "under=('To the next stake', 'Aphorism #45 as printed" in APP_SOURCE


def test_the_condition_s_two_lists_are_drawn_alike():
    source = APP_SOURCE[APP_SOURCE.index("df_condition = pd.DataFrame"):][:300]
    assert "under=('Good Fortune / Strength', 'Weakness / Misfortune')" in source


def test_the_columns_forced_under_are_under_whatever_they_hold():
    """Short values, which the rule alone would leave in the row."""
    tree = ast.parse(APP_SOURCE)
    rule = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_columns_under")
    assert [arg.arg for arg in rule.args.args] == ["names", "texts", "room", "forced"]
    namespace = {"_short_limit": lambda *args, **kw: 0, "_longest_piece": lambda text, limit=0: len(text),
                 "_cell_width": len, "_TEXT_CELL_PADDING": 0, "_TEXT_WRAP_ROOM": 1, "_TEXT_LINE_PX": 1,
                 "_TEXT_ROW_PADDING": 0, "_ROW_CAP_PX": 1000, "_TEXT_TABLE_LEAST": 1000, "math": __import__("math")}
    exec(compile(ast.Module([rule], []), "app.py", "exec"), namespace)
    assert namespace["_columns_under"](["a", "b", "c"], [["1"], ["2"], ["3"]], 500, {1}) == {1}
    assert namespace["_columns_under"](["a", "b", "c"], [["1"], ["2"], ["3"]], 500) == set()


def test_the_fitting_infortune_box_stands_in_no_narrow_column():
    assert "rule_col" not in APP_SOURCE and "fit_col" not in APP_SOURCE


def test_a_lord_s_long_place_wraps_where_the_star_table_would_pass_the_page():
    source = APP_SOURCE[APP_SOURCE.index("def _star_grid(rows):"):][:900]
    assert '> _GRID_NARROWEST_PAGE and "Place" in frame' in source and "_STAR_PLACE_LINE" in source


# --- A refused revolution ---------------------------------------------------------

def _strip_links(at):
    return [node.value for node in at.markdown if "(#the-small-days)" in node.value]


def test_days_and_months_draws_no_strip_above_a_refused_revolution():
    at = make_app(date="1975-03-14", page="days", timeout=240)
    state = at.session_state
    state["time_input_key"] = time(18, 0)
    state["time_standard_key"] = MANUAL
    state["utc_offset_key"] = 0.0
    state["manual_lat_key"], state["manual_lon_key"] = 89.99, -35.1854
    at.run()
    assert_no_exception(at, "refused")
    assert at.warning, "this chart is refused, or the pin reads nothing"
    assert not at.subheader
    assert not _strip_links(at)


def test_days_and_months_draws_its_strip_at_a_chart_it_can_read():
    """The pin above reads the strip's own links: here they are."""
    assert _strip_links(_page("days"))


# --- The year's shade ----------------------------------------------------------------

@pytest.mark.parametrize("mode", ["light", "dark"])
def test_a_year_in_any_sign_shades_its_band(mode):
    tokens = __import__("json").loads((ROOT / "tools" / "house_style" / "tokens.json").read_text(encoding="utf-8"))
    colours = tokens["modes"][mode]
    assert colours["wheel_shade"] not in colours["sign_tints"]


# --- Dykes's forms on every string a page draws ----------------------------------

_FORMS = re.compile("Abū|Māshā|Qabīsī")
_PAGE_CALLS = {"markdown", "caption", "info", "warning", "error", "success", "subheader", "expander", "write", "header", "popover"}
_EYE_FIXTURE = ROOT / "tests" / "fixtures" / "stars_harming_eyes_rows_2026_11_05.json"


def _drawn_strings(block):
    """Every word a block draws: bodies, labels, helps, options; a table's headings and cells."""
    for node in block.children.values():
        if hasattr(node, "children"):
            yield from _drawn_strings(node)
        value = getattr(node, "value", None)
        if isinstance(value, pd.DataFrame):
            yield from map(str, value.columns)
            yield from (str(cell) for cell in value.to_numpy().ravel())
        proto = getattr(node, "proto", None)
        for field in ("body", "label", "help", "placeholder"):
            text = getattr(proto, field, None)
            if isinstance(text, str):
                yield text
        yield from map(str, getattr(node, "options", None) or ())


def _still_plain(text):
    text = html.unescape(text)
    return page_words(text) != text


@pytest.mark.parametrize("depth", ["Course text", "Course text and supplement"])
@pytest.mark.parametrize("page", PAGES + ["sources", "reference"])
def test_a_page_prints_dykes_s_forms_outside_quotations_and_locators(page, depth):
    at = make_app(page=page, timeout=240)
    at.session_state["_reading_depth"] = depth
    at.run()
    assert_no_exception(at, page)
    plain = sorted({next(found.group(0) for found in re.finditer(r".{0,70}(?:Abu Ma'shar|Masha'allah|[aA]l-Qabisi|[tT]he app\\b).{0,40}", html.unescape(text))) if re.search(r"Abu Ma'shar|Masha'allah|[aA]l-Qabisi|[tT]he app\\b", html.unescape(text)) else text[:120]
                    for text in _drawn_strings(at.main) if _still_plain(text)})
    assert not plain, plain[:8]


_LINE_THAT_BINDS_PAGE_WORDS = next(node.lineno for node in ast.parse(APP_SOURCE).body
                                   if isinstance(node, ast.ImportFrom) and node.module == "engine")


def test_no_refusal_above_the_engine_s_import_reads_page_words():
    """A run the engine refuses, or that its door refuses, draws its one sentence before that name exists."""
    above = "\n".join(APP_SOURCE.split("\n")[:_LINE_THAT_BINDS_PAGE_WORDS - 1])
    assert "page_words" not in above


def _page_call_sites():
    """The page-text calls of app.py with a computed first argument."""
    for node in ast.walk(ast.parse(APP_SOURCE)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.args):
            continue
        if node.func.attr not in _PAGE_CALLS or isinstance(node.args[0], ast.Constant):
            continue
        if (getattr(node.func.value, "id", "") in ("logging", "warnings", "_time_standard_slot", "time_standard_box", "_here_now_slot", "_home_slot", "_lmt_box")
                or getattr(node.func.value, "attr", "") == "sidebar" or node.lineno < _LINE_THAT_BINDS_PAGE_WORDS):
            continue
        if any(k.arg == "unsafe_allow_html" for k in node.keywords):
            continue
        yield node


def test_every_computed_page_string_goes_through_the_page_s_words():
    """A rare chart's sentence no walk reaches. What a reader typed stands as typed, so it is the one exception."""
    bare = [node.lineno for node in _page_call_sites()
            if getattr(node.args[0].func if isinstance(node.args[0], ast.Call) else None, "id", "") != "page_words"
            and not any(word in ast.get_source_segment(APP_SOURCE, node.args[0]) for word in ("_as_typed", "_chart_label", "strip", "#{anchor}", "_place_line"))]
    assert not bare, bare


def test_a_name_the_reader_typed_stands_as_typed():
    """The strip prints a chart's name as typed, a plain spelling included."""
    assert "slot.caption(strip)" in APP_SOURCE and "page_words(strip)" not in APP_SOURCE
    assert "page_words(_as_typed" not in APP_SOURCE


def test_the_sidebar_s_place_box_prints_a_saved_place_as_typed():
    """The coordinates' half alone takes the page's words."""
    typed = "Masha'allah Springs"
    at = make_app(page="chart", timeout=240)
    state = at.session_state
    state["manual_coords_key"] = True
    state["manual_lat_key"], state["manual_lon_key"] = 33.25, 44.5
    state["loaded_location"] = {"label": typed, "lat": 33.25, "lon": 44.5}
    at.run()
    assert_no_exception(at, "place")
    boxes = [node.value for node in at.sidebar.success]
    assert any(f"**{typed}**" in box for box in boxes), boxes


def test_the_saved_data_file_holds_none_of_the_page_s_forms_it_did_not_hold():
    """A shared sentence respelled at its source would reach the file: its only
    printed forms are these, which it has always carried, inside quotations."""
    export = dict(_page("chart").session_state["_analysis_export"])
    held = collections.Counter(_FORMS.findall(json.dumps(export, ensure_ascii=False)))
    assert held == {"Abū": 2, "Qabīsī": 3}, held


@pytest.mark.parametrize("chart", json.loads(_EYE_FIXTURE.read_text(encoding="utf-8")))
def test_the_stars_harming_eyes_read_as_they_did_under_delineations(chart):
    """Rows of five invented charts, as Delineations printed them before the tab: no cell moves,
    but the Longitude, Latitude and designation of the four objects the grown catalogue places."""
    expected = json.loads(_EYE_FIXTURE.read_text(encoding="utf-8"))[chart]
    moment, hour, minute, lat, lon = chart.split("|")
    at = make_app(page="fixed-stars", timeout=300)
    state = at.session_state
    state["manual_coords_key"] = True
    state["date_input_key"], state["time_input_key"], state["time_standard_key"] = moment, time(int(hour), int(minute)), LMT
    state["manual_lat_key"], state["manual_lon_key"] = float(lat), float(lon)
    at.run()
    assert_no_exception(at, chart)
    frame = _tables(at)[EYES]
    assert frame.to_dict("records") == expected
