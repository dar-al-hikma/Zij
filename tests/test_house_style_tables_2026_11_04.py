# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""The pages' tables: what the suite can see of how they draw.

A table's rule runs here without a page, on rows written to break it; the
stylesheet and the page's calls are read as text; and the Delineations page runs
on every fixture chart at both reading depths. What only a browser shows (a row's
height, a cell cut at its frame, which face a paragraph takes) has no leg here.
These pins hold what those facts rest on.
"""
from __future__ import annotations

import ast
import html
import json
import math
import re
import sys
import types

import pandas as pd
import pytest

from conftest import APP_PATH, CHARTS, EXECUTABLE_DIR, PAGES, READING_DEPTHS, UNLABELLED_LINE, TextTable, assert_no_exception, \
    make_app, sync_engine_to_environment, table_inventory, table_nodes, text_table_nodes

sys.path.insert(0, str(EXECUTABLE_DIR))
import house_style  # noqa: E402
import markup  # noqa: E402

SAHL = "Sahl: indications of fortune and livelihood"
RULES = ("_is_missing", "_cell_text", "_drawn_width", "_CELL_ADVANCE", "_GRID_TEXT_PX", "_GRID_CELL_MARGIN", "_GRID_TEXT_ROOM",
         "_GRID_NARROWEST_PAGE", "_SHORT_CELL", "_WHOLE_VALUE", "_NUMBER_CELL", "_kept_whole", "_kept_table",
         "_ROW_CAP_PX", "_TEXT_LINE_PX", "_TEXT_ROW_PADDING", "_TEXT_WRAP_ROOM", "_TEXT_TABLE_ROOM", "_TEXT_TABLE_LEAST",
         "_TEXT_CELL_PADDING", "_SHORT_LIMITS", "_ROW_VALUE_CELL", "_ROW_VALUE_PX", "_SILENT_HEADINGS", "_cell_width",
         "_longest_piece", "_short_limit", "_columns_under", "_CLAUSE_LIST_LEAST", "_outside_brackets", "_led_clause",
         "_clause_lines", "_clauses_of", "_LEAD_OF_A_ROW_BENEATH", "_LEAD_OF_ITS_CLAUSES", "_OWN_LINE_LEADS", "_own_lines",
         "_repeats_a_row_beneath", "_leads_to_nothing", "_less_what_stands_beneath", "_text_table", "_page_frame")
LONG = "a sentence long enough to pass any column's width " * 40
APP_SOURCE = APP_PATH.read_text(encoding="utf-8")
APP_TREE = ast.parse(APP_SOURCE)


@pytest.fixture(scope="module")
def rule():
    """The table's rule, out of app.py, with a sink for what it would draw."""
    drawn = []
    held = types.SimpleNamespace(drawn=drawn)
    space = {"re": re, "math": math, "html": html, "pd": pd, "house_style": house_style,
             "page_cell": markup.page_cell, "page_column": markup.page_column, "page_words": markup.page_words,
             "st": types.SimpleNamespace(html=drawn.append)}
    for node in APP_TREE.body:
        if isinstance(node, ast.FunctionDef):
            names = [node.name]
        elif isinstance(node, ast.Assign):
            names = [getattr(target, "id", "") for target in node.targets]
        else:
            continue
        if set(names) & set(RULES):
            exec(compile(ast.Module([node], []), "app.py", "exec"), space)      # noqa: S102
    assert set(RULES) <= set(space), set(RULES) - set(space)
    for name in RULES:
        setattr(held, name, space[name])

    def table(frame, **options):
        drawn.clear()
        space["_text_table"](pd.DataFrame(frame), **options)
        assert len(drawn) == 1
        return TextTable(drawn[0])
    held.table = table
    return held


def _whole_words(text):
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


# --- One shape per table ----------------------------------------------------------

def test_a_lone_long_value_wraps_in_its_column_as_its_neighbours_stand(rule):
    table = rule.table({"Item": ["one", "two", "three"], "Value": ["x", "y", "a lone longer value " * 8], "Text": ["p", "q", "r"]})
    assert table.headings == ["Item", "Value", "Text"]
    assert table.line_labels == []
    assert "<tr class=\"zij-under\"" not in table.body


def test_a_column_goes_under_for_every_row_or_for_none(rule):
    """A column that would pass the row's cap leaves the row whole, its short
    cells with its long one, and the row keeps the same cells in every row."""
    table = rule.table({"Item": ["one", "two", "three"], "Short": ["x", "y", "z"], "Note": ["short", LONG, "also short"]})
    assert table.headings == ["Item", "Short"]
    assert table.line_labels == ["Note"]
    assert len(table.rows) == 3
    for row in table.rows:
        assert len(row["cells"]) == 2
        assert [label for label, _ in row["lines"]] == ["Note"]


def test_the_row_s_cap_is_a_third_of_a_window_and_decides_by_the_wrapped_height(rule):
    assert rule._ROW_CAP_PX == 333
    assert rule._columns_under(["Item", "Note"], [["one"], ["word " * 60]], rule._TEXT_TABLE_ROOM) == set()
    lines_past_the_cap = math.ceil((rule._ROW_CAP_PX - rule._TEXT_ROW_PADDING) / rule._TEXT_LINE_PX) + 1
    assert rule._columns_under(["Item", "Note"], [["one"], ["word " * (lines_past_the_cap * 400)]], rule._TEXT_TABLE_ROOM) == {1}


def test_the_first_column_never_goes_under_since_it_names_the_row(rule):
    assert 0 not in rule._columns_under(["Note", "Other"], [[LONG], ["x"]], rule._TEXT_TABLE_ROOM)
    assert rule.table({"Note": [LONG], "Other": ["x"]}).headings[0] == "Note"


def test_a_table_too_wide_for_the_narrowest_box_gives_up_its_widest_columns(rule):
    wide = {f"Column{at}": ["longwordinthiscolumnthatcannotbreak" + "x" * at] for at in range(1, 8)}
    table = rule.table({"Item": ["one"], **wide})
    assert len(table.headings) < 8
    assert table.line_labels
    assert sum(rule._longest_piece(cell) + rule._TEXT_CELL_PADDING for cell in table.rows[0]["cells"]) <= rule._TEXT_TABLE_LEAST


def test_a_table_in_half_a_page_says_so_and_stands_narrower(rule):
    cells = {f"Column{at}": ["longwordinthiscolumn"] for at in range(1, 5)}
    whole = rule.table({"Item": ["one"], **cells})
    half = rule.table({"Item": ["one"], **cells}, room=rule._TEXT_TABLE_ROOM // 2 - 8)
    assert len(half.headings) < len(whole.headings)
    assert "room=_TEXT_TABLE_ROOM // 2 - 8" in APP_SOURCE, "the unit table beside another stacks or fits its half"


# --- What a table draws ------------------------------------------------------------

def test_the_row_s_own_values_draw_the_eye_over_the_lines_beneath(rule):
    table = rule.table({"Item": ["one", "two"], "Short": ["x", "y"], "Note": [LONG, LONG]})
    assert table.bold_columns == {"Item", "Short"}
    assert 'class="zij-row-value' in table.body or " zij-row-value" in table.body


def test_a_table_with_no_lines_under_its_rows_draws_nothing_bold(rule):
    assert rule.table({"Item": ["one"], "Short": ["x"]}).bold_columns == set()
    assert "zij-row-value" not in rule.table({"Item": ["one"], "Short": ["x"]}).body


def test_a_long_column_wrapped_in_place_stays_regular_though_others_go_under(rule):
    middling = "abcdefghijklmnopqrstuvwxyz " * 3      # past what bold is for, short of the cap
    table = rule.table({"Item": ["one"], "Middling": [middling], "Note": [LONG]})
    assert table.line_labels == ["Note"] and "Middling" in table.headings
    assert table.bold_columns == {"Item"}


def test_where_the_first_column_only_numbers_the_row_the_second_names_it(rule):
    table = rule.table({"#": ["1", "2"], "Name": ["alpha", "beta"], "Note": [LONG, LONG]})
    assert {"#", "Name"} <= table.bold_columns


@pytest.mark.parametrize("silent", ["Text", "Value", "Reads"])
def test_a_line_whose_heading_tells_nothing_draws_without_it(rule, silent):
    table = rule.table({"Item": ["one"], silent: [LONG]})
    assert table.line_labels == [UNLABELLED_LINE]
    assert f">{silent}<" not in table.body
    assert rule._SILENT_HEADINGS == {"Text", "Value", "Reads"}


def test_a_line_whose_heading_tells_the_reader_keeps_it(rule):
    assert rule.table({"Item": ["one"], "Sahl": [LONG]}).line_labels == ["Sahl"]


def test_a_label_stands_beside_one_line_and_above_a_list(rule):
    lists = "first clause: met; second clause: met; third clause: not met"
    table = rule.table({"Item": ["one", "two"], "Ground": ["one line of its own. " * 200, lists + " " + LONG]},
                       clause_lines=("Ground",))
    assert table.line_labels == ["Ground"]
    first, second = re.findall(r'<tr class="zij-under"><td[^>]*>(.*?)</td>', table.body, flags=re.S)
    assert '</span> ' in first and "</span><br>" not in first
    assert "</span><br>" in second


def test_a_double_hyphen_draws_as_a_dash_in_a_cell_a_heading_and_a_line(rule):
    table = rule.table({"Item -- it": ["one -- two"], "Note": ["three -- four " + LONG]})
    assert "--" not in table.body
    assert table.headings[0] == "Item — it"
    assert table.rows[0]["cells"][0] == "one — two"
    assert table.rows[0]["lines"][0][1].startswith("three — four")


def test_a_heading_s_tooltip_is_drawn_on_the_heading(rule):
    table = rule.table({"Date": ["1240-05-23"], "Item": ["one"]}, column_help={"Date": 'The "calendar" & its note'})
    assert table.tips == {"Date": 'The "calendar" & its note'}
    assert "Item" not in table.tips


def test_a_cell_s_markup_is_never_read_as_markup(rule):
    table = rule.table({"Item": ["<b>one</b> & two"], "Note": ["<i>three</i> " + LONG]})
    assert "<b>" not in table.body and "<i>" not in table.body
    assert table.rows[0]["cells"][0] == "<b>one</b> & two"


def test_a_degree_a_time_and_a_locator_are_marked_never_to_break(rule):
    body = rule.table({"Item": ["at 18° Ari 00' on 1240-05-23 12:00 by On Nativities 2.11, 4 and PN IV VI.2, 4-5 " + "word " * 12]}).body
    whole = re.findall(r'<span class="zij-whole">(.*?)</span>', body)
    assert "18° Ari 00'" in whole and "On Nativities 2.11, 4" in whole and "1240-05-23 12:00" in whole


def test_numbers_stand_on_their_right(rule):
    table = rule.table({"Item": ["one", "two"], "Count": ["1", "22"]})
    assert re.search(r'<th class="zij-number[^"]*">Count</th>', table.body)
    assert not re.search(r'<th class="zij-number[^"]*">Item</th>', table.body)


# --- A list of clauses ---------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "one: met; two: met; three: not met",
    "An opening sentence. one: met; two: met; three: not met. A closing sentence.",
    "lead (2.3, 6), its name: first: met; second: met; third: met",
    "a (with; brackets; inside); b; c; d",
    "two clauses; and no more",
    "no clause at all",
    'a quotation "with; three; of them; inside" and nothing else',
])
def test_a_list_s_lines_are_its_text_only_its_spaces_become_line_ends(rule, text):
    assert " ".join(rule._clause_lines(text)) == text


def test_three_clauses_are_a_list_and_two_a_sentence_with_a_pause(rule):
    assert rule._CLAUSE_LIST_LEAST == 3
    assert rule._clause_lines("one; two") == ["one; two"]
    assert rule._clause_lines("one; two; three") == ["one;", "two;", "three"]


def test_a_bracket_s_semicolons_make_no_list(rule):
    assert rule._clause_lines("a (b; c; d; e) f") == ["a (b; c; d; e) f"]


def test_a_clause_that_opens_what_follows_takes_a_line_of_its_own(rule):
    lines = rule._clause_lines("a lead here: first: met; second: met; third: met")
    assert lines == ["a lead here:", "first: met;", "second: met;", "third: met"]
    dashed = rule._clause_lines("a step — its reading: first: met; second: met; third: met")
    assert dashed[0] == "a step — its reading:" and dashed[1] == "first: met;"


def test_text_that_holds_its_line_ends_keeps_them(rule):
    assert rule._clause_lines("one\ntwo; three; four") == ["one", "two; three; four"]


# --- The row that sums up the rows beneath it ----------------------------------------

BENEATH = ["Saturn in a stake: met; Saturn clear of Mars: met; Saturn free of retrogradation: met",
           "The Sun, the sect light, in Gemini; its lords Saturn, Mercury, Jupiter. First: Saturn in Cancer; raw quadrant 10; degree house 10",
           "Venus afflicted: met; fortune eastern: met; lord eastern: met"]


def test_a_clause_that_stands_beneath_leaves_and_one_that_stands_nowhere_stays(rule):
    text = "Opening. Lifelong happiness (2.3, 2): not met -- Saturn in a stake: met; a clause of its own: met; Saturn clear of Mars: met; another of its own: not met"
    lines = rule._less_what_stands_beneath(text, BENEATH).split("\n")
    assert "a clause of its own: met;" in lines and "another of its own: not met" in lines
    assert not any("Saturn in a stake" in line or "Saturn clear of Mars" in line for line in lines)


def test_nothing_is_dropped_when_nothing_stands_beneath(rule):
    text = "first: met; second: met; third: met. Synthesis: two; clauses"
    kept = rule._less_what_stands_beneath(text, [])
    assert " ".join(kept.split("\n")) == text


def test_a_dash_goes_with_the_clause_it_led_to(rule):
    kept = rule._less_what_stands_beneath("Happiness: not met — Venus afflicted: met; fortune eastern: met; lord eastern: met", BENEATH)
    assert kept == "Happiness: not met"
    assert "—" not in kept


def test_a_bracket_goes_only_when_all_it_holds_stands_beneath(rule):
    whole = "one; two; the step (Venus afflicted: met; fortune eastern: met)."
    part = "one; two; the step (Venus afflicted: met; a thing said only here: met)."
    assert "(" not in rule._less_what_stands_beneath(whole, BENEATH)
    assert "(Venus afflicted: met; a thing said only here: met)" in rule._less_what_stands_beneath(part, BENEATH)


def test_the_lords_sentence_leaves_only_when_all_of_it_stands_beneath(rule):
    gone = "Modified by the third; no class step. The lords: the Sun, the sect light, in Gemini; its lords Saturn, Mercury, Jupiter."
    kept = rule._less_what_stands_beneath(gone, BENEATH)
    assert "The lords" not in kept and kept.endswith("no class step.")
    other = gone.replace("in Gemini", "in Libra")
    assert "The lords: the Sun, the sect light, in Libra" in rule._less_what_stands_beneath(other, BENEATH)
    assert "The lords: the Sun" in rule._less_what_stands_beneath(gone, []), "with its row not drawn, it stays"


def test_a_lead_holding_a_clause_of_its_own_does_not_lead_to_nothing(rule):
    below = {"Venus afflicted: met", "fortunate: not met"}
    opens = ["Venus afflicted: met;", "fortunate: not met."]
    assert rule._leads_to_nothing(["Conditional Lot assessments: 2.16, 2 —"] + opens, below)
    assert not rule._leads_to_nothing(["Conditional Lot assessments: 2.16, 2 — a clause alone here;"] + opens, below)


def test_only_the_lords_lead_is_read_past(rule):
    other = "Other lords: the Sun, the sect light, in Gemini; its lords Saturn, Mercury, Jupiter."
    assert "Other lords: the Sun" in rule._less_what_stands_beneath(other, BENEATH)


@pytest.mark.parametrize("lead", ["Synthesis: both stand", "Modified by the third: Jupiter"])
def test_a_synthesis_and_a_modifier_start_their_own_lines(rule, lead):
    text = f"An opening sentence. {lead}. A closing sentence."
    lines = rule._less_what_stands_beneath(text, []).split("\n")
    assert f"{lead}. A closing sentence." in lines and "An opening sentence." in lines
    assert " ".join(lines) == text


CONDITIONAL = ("Opening. Conditional Lot assessments: 2.16, 2 — Venus afflicted: met; fortune eastern: met; lord eastern: met. "
               "Synthesis: unresolved.")


def test_a_lead_that_only_names_its_clauses_leaves_when_all_of_them_have(rule):
    assert rule._less_what_stands_beneath(CONDITIONAL, BENEATH).split("\n") == ["Opening.", "Synthesis: unresolved."]


def test_that_lead_stays_while_one_of_its_clauses_stands(rule):
    kept = rule._less_what_stands_beneath(CONDITIONAL, [BENEATH[2].replace("lord eastern: met", "another: met")]).split("\n")
    assert kept == ["Opening.", "Conditional Lot assessments: 2.16, 2", "lord eastern: met.", "Synthesis: unresolved."]
    assert "Conditional Lot assessments: 2.16, 2 —" in rule._less_what_stands_beneath(CONDITIONAL, []).split("\n")


def test_a_lead_that_gives_a_verdict_stays_though_its_clauses_go(rule):
    kept = rule._less_what_stands_beneath(CONDITIONAL.replace("Conditional Lot assessments: 2.16, 2", "Lifelong happiness (2.3, 2): not met"), BENEATH)
    assert "Lifelong happiness (2.3, 2): not met" in kept.split("\n")


def test_a_clause_of_the_next_sentence_keeps_no_lead_alive(rule):
    """The lead's reach ends with its sentence."""
    text = CONDITIONAL.replace("Synthesis: unresolved.", "A sentence said only here; and more; and the last.")
    assert not any(line.startswith("Conditional") for line in rule._less_what_stands_beneath(text, BENEATH).split("\n"))


def test_a_lead_inside_brackets_starts_no_line(rule):
    text = "An opening (it says. Synthesis: not here) and on."
    assert rule._less_what_stands_beneath(text, []) == text


# --- The Delineations page ------------------------------------------------------------

@pytest.fixture(scope="module", params=[(date, depth) for date in CHARTS for depth in READING_DEPTHS],
                ids=lambda value: f"{value[0]}-{value[1].split()[-1]}")
def sahl_page(request):
    """Sahl's table as the page drew it, and the rows the engine wrote."""
    sync_engine_to_environment()        # it may reload the engine, and a patch must be on the one the page reads
    import engine as engine_module
    date, depth = request.param
    held = {}
    real = engine_module.evaluate_prosperity

    def keep(*args, **kwargs):
        rows = real(*args, **kwargs)
        if not kwargs:
            held["rows"] = rows
        return rows
    engine_module.evaluate_prosperity = keep
    try:
        at = make_app(date=date, page="delineations", timeout=240)
        at.session_state["_reading_depth"] = depth
        at.run()
    finally:
        engine_module.evaluate_prosperity = real
    assert_no_exception(at, f"{date} {depth}")
    table = dict(text_table_nodes(at))[SAHL]
    rows = [row for row in held["rows"] if depth == READING_DEPTHS[1] or not row["Supplement"]]
    return types.SimpleNamespace(at=at, table=table, rows=rows, date=date, depth=depth)


def _row_text(cell):
    return _whole_words(cell.replace("\n", " "))


def _in_this_chart(row):
    return dict(row["lines"])["In this chart"]


def _clause_pattern(piece):
    return r"(?:^|; |\. )" + re.escape(piece) + r"(?:$|;|\.)"


def _pieces(gap):
    """What lies between two kept lines, as whole clauses, written apart from the
    page's rule: cut at semicolons and sentence ends, brackets opened in the gap
    read as plain text."""
    found = []
    for piece in re.split(r"; |\. (?=[A-Z])", gap):
        piece = piece.strip(" ;.—")
        while piece.endswith(")") and piece.count(")") > piece.count("("):
            piece = piece[:-1]
        while piece.startswith("(") and piece.count("(") > piece.count(")"):
            piece = piece[1:]
        if piece:
            found.append(piece)
    return found


CONDITIONAL_LEAD = "Conditional Lot assessments: "
# Where each step of the first row opens, and whose it is. A sentence the row alone says belongs to no row beneath.
SUBJECTS = {"Lifelong happiness (2.3, 2)": "lifelong", "the Lot step (2.3, 6)": "the Lot", CONDITIONAL_LEAD: "the Lot",
            "Synthesis:": "its own", "Modified by ": "its own", "The lords: ": "the lords"}
SUBJECT = re.compile("(" + "|".join(map(re.escape, SUBJECTS)) + ")")


def _gaps(original, lines):
    """What lies between the kept lines, each with where it ends in the engine's words."""
    at, gaps = 0, []
    for line in lines:
        kept = line.rstrip(" .;—")
        found = original.find(kept, at)
        assert found >= 0, f"not the engine's words in the engine's order: {line!r}"
        gaps.append((found, original[at:found]))
        at = found + len(kept)
    return [*gaps, (len(original), original[at:])]


def _piece_without_its_lead(piece):
    """A clause as the row beneath prints it: The lords' sentence but for its lead
    and capital, an assessment's first clause but for the lead naming the assessment."""
    if piece.startswith("The lords: "):
        said = piece[len("The lords: "):]
        return said[0].upper() + said[1:]
    if piece.startswith(CONDITIONAL_LEAD) and " — " in piece:
        return piece.partition(" — ")[2]
    return piece


def _pattern_row(sahl_page):
    return next(row for row in sahl_page.table.rows if row["cells"][0].startswith("The two lords"))


def test_the_engine_s_first_row_is_not_drawn_and_its_row_of_the_pattern_is(sahl_page):
    """Written apart from the page's rule. The engine's first row, its combined
    class, is not drawn; the words of Sahl's own pattern are, word for word, after
    the row of the lords."""
    original = _whole_words(str(sahl_page.rows[0]["Ground"]).replace("--", "—"))
    opening = original[:original.index(". Lifelong happiness (2.3, 2): ")]
    drawn = _row_text(_in_this_chart(_pattern_row(sahl_page)))
    assert drawn.startswith(opening), (opening, drawn)
    assert len(sahl_page.table.rows) == len(sahl_page.rows)
    names = [row["cells"][0] for row in sahl_page.table.rows]
    assert names[names.index("The lords, by place") + 1] == "The two lords' pattern"


def test_a_clause_that_left_stands_under_its_own_subject(sahl_page):
    """Lifelong's evidence stands in Lifelong's row, the partnering lord's in his,
    the lords' sentence as that row's opening."""
    original = _whole_words(str(sahl_page.rows[0]["Ground"]).replace("--", "—"))
    by_key = {row["key"]: _whole_words(str(row["Ground"]).replace("--", "—")) for row in sahl_page.rows[1:]}
    verdict = re.search(r"Lifelong happiness \(2\.3, 2\): (.*?) — (.*?)(?:; the Lot step|\. Synthesis:)", original)
    assert verdict and by_key["lifetime"].startswith(verdict.group(2)[:40]), (verdict and verdict.group(2), by_key["lifetime"])
    modified = re.search(r"Modified by the partnering lord \(2\.11, 4\): (\w+) in .*? — (.*?); no class step", original)
    assert modified and modified.group(2) in by_key["third"], original
    tail = original[original.rindex("The lords: ") + len("The lords: "):]
    assert by_key["lords"].startswith(tail[0].upper() + tail[1:])


def test_no_lead_with_nothing_under_it_stands_in_the_first_row(sahl_page):
    lines = _in_this_chart(sahl_page.table.rows[0]).split("\n")
    assert not [line for line in lines if re.fullmatch(CONDITIONAL_LEAD + r"[\d., ]+—?", line)], lines
    if sahl_page.date == "1240-01-04":
        assert CONDITIONAL_LEAD in str(sahl_page.rows[0]["Ground"]), "this chart has one for the page to take away"
        assert not any(line.startswith(CONDITIONAL_LEAD) for line in lines), lines


SUPPLEMENT_TABLES = ["Mars in his own domicile, by sect (Abu Bakr)", "Mercury's phase against the sect", "Mercury's company and sect",
                     "Morin's rules for aspects into good and bad houses"]


@pytest.mark.parametrize("heading", SUPPLEMENT_TABLES)
def test_the_supplement_s_small_tables_are_plain_tables(heading):
    """A grid of these is cut at its frame in a usual window, and they hold few rows.
    Where one of them draws on some fixture chart, it draws in the page's own markup."""
    drawn = 0
    for date in CHARTS:
        at = make_app(date=date, page="delineations", timeout=240)
        at.session_state["_reading_depth"] = READING_DEPTHS[1]
        at.run()
        assert_no_exception(at, date)
        for title, node in table_nodes(at):
            if title == heading:
                assert isinstance(node, TextTable), (date, title)
                drawn += 1
    assert drawn, "the pin reads nothing if the table is on no fixture chart"


def test_the_row_of_the_pattern_holds_no_class_and_nothing_summed(sahl_page):
    lines = _in_this_chart(_pattern_row(sahl_page)).split("\n")
    assert not any(line.startswith(("Lifelong happiness", "Synthesis:", "Modified by ", "First: ", "Second: ")) for line in lines), lines
    assert not any("The lords:" in line or "Synthesis" in line or re.search(r"\bclass \d", line) for line in lines), lines


def test_the_rows_beneath_the_first_are_drawn_whole(sahl_page):
    """Each as the engine wrote it, but for the words that named the class."""
    drawn = [row for row in sahl_page.table.rows if not row["cells"][0].startswith("The two lords")]
    assert len(sahl_page.rows[1:]) == len(drawn) > 1
    for row, shown in zip(sahl_page.rows[1:], drawn):
        text = _whole_words(str(row["Ground"]).replace("--", "—").replace("; this does not change the two-lord synthesis", "")
                            .replace(", not a class step,", ","))
        assert _row_text(dict(shown["lines"]).get("In this chart", "")) == text


def test_sahl_s_table_says_its_shared_citation_once(sahl_page):
    assert "Triplicity table" not in sahl_page.table.value.columns
    assert "Triplicity table: Sahl, The Introduction Ch. 1, 35-41, Figure 4" in [
        part for caption in sahl_page.at.main.caption for part in caption.value.split(" · ")]


def test_no_heading_or_label_taken_away_is_on_this_page(sahl_page):
    drawn = dict(text_table_nodes(sahl_page.at))
    for heading in ("The fetus's stay (Sahl)", "The Moon on the third day (Sahl)", SAHL):
        assert not set(drawn[heading].value.columns) & {"Ground", "Class", "Item", "Value", "Text"}, heading


def test_the_page_offers_no_selector_on_sahl_s_table_and_no_expander_above_it(sahl_page):
    assert "sahl_indications_of_fortune_and_livelihood_detail" not in [box.key for box in sahl_page.at.main.selectbox]
    assert not any(label.startswith("The prenatal degree") for label in (e.label for e in sahl_page.at.main.expander))
    assert not any("--" in cell for row in sahl_page.table.rows for cell in row["cells"])


def test_the_first_two_tables_read_as_a_reader_reads_them():
    at = make_app(page="delineations", timeout=240).run()
    assert_no_exception(at, "delineations")
    tables = dict(table_inventory(at))
    assert tables["The fetus's stay (Sahl)"] == ["What is read", "In this chart", "What the text says"]
    assert tables["The Moon on the third day (Sahl)"] == ["What is read", "In this chart", "What the text says"]
    assert tables[SAHL] == ["What is read", "In this chart", "Sahl", "Also"]


def test_the_sentence_above_sahl_s_table_says_what_the_chapter_does_not():
    at = make_app(page="delineations", timeout=240).run()
    said = [node.value for node in at.main.markdown if "seven-class outcome" in node.value]
    assert said == ["A single seven-class outcome (On Nativities 2.1, 2-9) is not specified for every combination in Sahl's chapter."]


def test_the_prenatal_degree_s_governor_stands_on_lunation_and_victors_alone():
    at = make_app(page="victors", timeout=240).run()
    assert_no_exception(at, "victors")
    assert "Prenatal Lunation (Syzygy)" in [node.value for node in at.main.subheader]


def _sahl_rows_changed(change):
    """The Delineations page with the engine's rows changed as a chart might."""
    sync_engine_to_environment()
    import engine as engine_module
    real = engine_module.evaluate_prosperity

    def changed(*args, **kwargs):
        return change(real(*args, **kwargs))
    engine_module.evaluate_prosperity = changed
    try:
        at = make_app(page="delineations", timeout=240).run()
    finally:
        engine_module.evaluate_prosperity = real
    assert_no_exception(at, "delineations")
    return at, dict(text_table_nodes(at))[SAHL]


def test_a_citation_the_rows_do_not_share_stays_on_its_row_and_none_is_lost():
    """No chart today gives two values: all come from one constant. The branch
    still has to keep every citation when one does."""
    def two_values(rows):
        rows = [dict(row) for row in rows]
        rows[-1]["Triplicity table"] = "Another table, Figure 9"
        return rows
    at, table = _sahl_rows_changed(two_values)
    assert "Triplicity table" in table.value.columns
    held = set(table.value["Triplicity table"])
    assert {"Another table, Figure 9", "Sahl, The Introduction Ch. 1, 35-41, Figure 4"} <= held
    captions = " ".join(caption.value for caption in at.main.caption)
    assert "Sahl, On Nativities 2.1-2.21" in captions and "Triplicity table:" not in captions


def test_a_source_note_draws_only_on_a_chart_whose_rows_hold_one():
    plain = dict(table_inventory(make_app(page="delineations", timeout=240).run()))[SAHL]
    assert "Virgo source note" not in plain

    def noted(rows):
        rows = [dict(row) for row in rows]
        rows[0]["Virgo source note"] = "A note on Virgo's lords."
        return rows
    _, table = _sahl_rows_changed(noted)
    assert "Virgo source note" in table.value.columns
    assert "A note on Virgo's lords." in list(table.value["Virgo source note"])


def test_a_cell_of_many_short_clauses_is_measured_as_the_sentence_it_is(rule):
    """Only the rule's estimate sees this: a list of short clauses is one long line
    to it, so it goes under its row though each clause would stand in a column."""
    clauses = "; ".join(f"clause number {at}: met" for at in range(90))
    table = rule.table({"Item": ["one"], "In this chart": [clauses]}, clause_lines=("In this chart",))
    assert table.line_labels == ["In this chart"]
    assert table.rows[0]["lines"][0][1].count("\n") == 89


# --- No table hides a column ------------------------------------------------------------

@pytest.mark.parametrize("page", PAGES)
def test_no_grid_on_a_page_hides_a_column(page):
    at = make_app(page=page, timeout=240)
    at.session_state["_reading_depth"] = READING_DEPTHS[1]
    at.run()
    assert_no_exception(at, page)
    hidden = {}
    for heading, node in table_nodes(at):
        if isinstance(node, TextTable):
            continue
        held = json.loads(node.proto.columns or "{}")
        gone = [name for name, config in held.items() if config.get("hidden") and name != "_index"]    # hide_index
        if gone:
            hidden[heading] = gone
    assert not hidden, hidden


# --- A sentence that qualifies a table stands above it ---------------------------------

QUALIFYING = {
    "delineations": ["A single seven-class outcome"],
    "dignities": ["**Natal adaptation.**", "A natal analogy:", "The readings remain visible"],
    "configurations": ["**Under Sahl's rule.** A pair refused", "**Under Sahl's rule.** Kind II", "Abū Ma'shar enumerates these conditions"],
    "timing": ["Facts from this app's own evaluators", "**Facts, not a verdict.**", "**Facts, not judgments:"],
    "days": ["**The day.**"],
    "fardar": ["No numerical age ranges are calculated here."],
}


def _open_passages(node):
    """The Markdown that stands outside every expander, in the page's order."""
    found = []
    for child in getattr(node, "children", {}).values():
        kind = getattr(child, "type", None)
        if kind in ("expander", "status"):
            continue
        if kind == "markdown":
            found.append(child.value)
        found += _open_passages(child)
    return found


@pytest.mark.parametrize("page", sorted(QUALIFYING))
def test_a_sentence_that_qualifies_a_table_stands_open_above_it(page):
    """The long passages fold under their tables; these say what a figure or a
    cell is not, and a reader meets them before the rows."""
    at = make_app(page=page, timeout=240).run()
    assert_no_exception(at, page)
    shown = [text.replace("*", "") for text in _open_passages(at.main)]
    for opening in QUALIFYING[page]:
        assert any(text.startswith(opening.replace("*", "")) for text in shown), opening


# --- The exports keep their own words ---------------------------------------------------

def test_the_markdown_and_html_exports_keep_their_own_headings():
    """The Markdown is what a reader opens, so its own table headings are read, and a
    table the page renamed keeps the export's heading: Sahl's table is in no export,
    "What is read" is the page's name for its neighbours' Item, which is."""
    at = make_app(page="delineations", timeout=240).run()
    report, page = at.session_state["_analysis_markdown"], at.session_state["_analysis_html"]
    headings = {cell.strip() for line in report.splitlines() if line.startswith("| ") for cell in line.strip("| \n").split(" | ")}
    assert headings, "the pin reads nothing if the export holds no table"
    for renamed in ("What is read", "In this chart", "What the text says"):
        assert renamed not in headings and renamed not in report, renamed
        assert f">{renamed}<" not in page, renamed
    export_rows = [entry for section in at.session_state["_analysis_export"]["results"].values() for entries in section.values()
                   for entry in entries if {"Item", "Value"} <= set(entry["columns"])]
    assert export_rows, "the pin reads nothing if no export table holds the old headings"
    assert re.search(r"^\| *Item *\| *Value *\|", report, re.M)


def test_the_export_reads_as_it_did_though_the_page_renamed_its_headings():
    """The renames are the page's. The engine's rows and the exports keep their keys,
    and the page's new name stands once in the export, in the sentence naming what it leaves out."""
    at = make_app(page="delineations", timeout=240).run()
    export = at.session_state["_analysis_export"]
    columns = {column for section in export["results"].values() for entries in section.values()
               for entry in entries for column in entry["columns"]}
    assert columns, "the pin reads nothing if the export holds no table"
    assert not columns & {"What is read", "In this chart", "What the text says", "Delineations"}
    written = json.dumps(export["results"], ensure_ascii=False)
    assert "Delineations" not in written
    assert "In this chart" not in export["scope"] and export["scope"].count("Delineations") == 1
    assert not {"What is read", "What the text says"} & set(re.findall(r'"([^"]+)"', written))


# --- The page's calls, read as text --------------------------------------------------

def _calls():
    return [node for node in ast.walk(APP_TREE) if isinstance(node, ast.Call)]


def test_every_grid_goes_through_the_one_rule():
    drawn = [node for node in _calls() if ast.unparse(node.func) == "st.dataframe"]
    assert len(drawn) == 1, "st.dataframe stands in _grid alone"
    inside = next(node for node in APP_TREE.body if isinstance(node, ast.FunctionDef) and node.name == "_grid")
    assert drawn[0] in list(ast.walk(inside))
    grids = [node for node in _calls() if ast.unparse(node.func) == "_grid"]
    assert grids, "the pin reads nothing if no call is found"


def test_no_markdown_table_call_or_static_table_is_left_to_draw_its_own_way():
    assert not [node for node in _calls() if ast.unparse(node.func) == "st.table"]
    texts = [node for node in _calls() if ast.unparse(node.func) == "_text_table"]
    assert len(texts) >= 40, "the plain tables' count falls only by a decision"


def test_a_grid_of_few_rows_shows_them_all():
    source = ast.get_source_segment(APP_SOURCE, next(n for n in APP_TREE.body if isinstance(n, ast.FunctionDef) and n.name == "_grid"))
    assert "if len(frame) < _GRID_EVERY_ROW_BELOW:" in source
    assert re.search(r"^_GRID_EVERY_ROW_BELOW = 50\b", APP_SOURCE, re.M)


def test_the_date_note_stands_on_every_plain_table_s_date_heading():
    """The grid's heading carried the calendar's note; a plain table's title does."""
    assert len(re.findall(r"column_help=_date_column_tip\(", APP_SOURCE)) == 4


DATE_TABLE_PAGES = ["days", "releaser"]
DATE_TABLE_STATE = {"_target_mode": "Date", "_target_date": "2026-09-17"}


@pytest.mark.parametrize("page", DATE_TABLE_PAGES)
def test_a_plain_table_s_date_heading_draws_the_calendar_s_note(page):
    """What the reader hovers: the heading's own title, as the page draws it."""
    at = make_app(page=page, timeout=240)
    for key, value in DATE_TABLE_STATE.items():
        at.session_state[key] = value
    at.run()
    assert_no_exception(at, page)
    dated = [node for _, node in text_table_nodes(at) if "Date" in node.headings]
    assert dated, "the pin reads nothing if this page draws no plain table with a Date"
    for node in dated:
        assert "calendar" in node.tips.get("Date", ""), node.headings


def test_the_page_address_is_the_page_s_new_name():
    pages = {ast.literal_eval(keyword.value): node for node in _calls() if ast.unparse(node.func) == "st.Page"
             for keyword in node.keywords if keyword.arg == "url_path"}
    assert "delineations" in pages and "findings" not in pages
    titles = {keyword.arg: ast.literal_eval(keyword.value) for keyword in pages["delineations"].keywords}
    assert titles["title"] == "Delineations"


def test_no_page_carries_an_icon_and_no_label_an_emoji():
    pages = [node for node in _calls() if ast.unparse(node.func) == "st.Page"]
    assert len(pages) == 14
    assert all(keyword.arg != "icon" for node in pages for keyword in node.keywords)
    for gone in ("\U0001F4CD", "\U0001F4C2", "\U0001F4BE", "\U0001F5D1", "⚠"):
        assert gone not in APP_SOURCE, gone
    assert ":material/location_on:" in APP_SOURCE and ":material/delete:" in APP_SOURCE
    assert "st.navigation(pages, position=\"top\")" in APP_SOURCE


# --- The stylesheet --------------------------------------------------------------------

def _rule_of(selector):
    css = house_style.PAGE_STYLE
    found = [declarations for chosen, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", css) if chosen == selector]
    assert found, selector
    return found[0]


def test_no_table_sets_a_fixed_layout_so_columns_take_their_widths_from_what_they_hold():
    assert "table-layout" not in house_style.PAGE_STYLE


def test_a_column_holding_a_table_stacks_rather_than_cuts_it():
    assert _rule_of('[data-testid="stColumn"]:has(.zij-table,[data-testid="stDataFrame"])') == "min-width:min-content;"


def test_the_stylesheet_names_each_private_id_it_leans_on():
    for held in ("stMain", "stMarkdown", "stExpander", "stColumn", "stDataFrame", "stCaptionContainer", "stTopNav",
                 "stTopNavSection", "stTopNavDropdownLink", "stTopNavPopoverBody", "stHtml", "stTable",
                 "stMarkdownContainer"):
        assert f'[data-testid="{held}"]' in house_style.PAGE_STYLE, held
