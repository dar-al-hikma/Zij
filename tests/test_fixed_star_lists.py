# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""The Fixed stars page's four lists: the words, the file behind the two longer
ones, the one control over both tabs and the export, and what no list narrows.
Then the record's frame and its title kept in view, as far as a stylesheet can
be read here: what a browser draws is measured in a browser."""
from __future__ import annotations

from markup import page_cell, page_column
import ast
import hashlib
import json
import math
import re
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

from conftest import EXECUTABLE_DIR, sync_engine_to_environment
from test_fixed_stars_page import axis_lists, choose_population, fixed_stars_app, opener_rows, sahl_rows, tab_named, walk
from test_fixed_stars_record import _export, _title, dialog_of, facts_of, find_star

sys.path.insert(0, str(EXECUTABLE_DIR))
import house_style  # noqa: E402

ROOT = Path(__file__).parent.parent
THE_FILE = ROOT / "data" / "fixed_star_lists.tsv"
WORDS = ["Sahl's 28", "Curated List", "Significant Stars", "Full Catalogue"]
# Of the lists' numbers, one to a line in sorted order; what a change to either list must also change.
CURATED_NUMBERS = "ce0356ae98f896f6b2c471eb60e1940bc811cfdb6d1a6c578c4bf869b50b3cd8"
SIGNIFICANT_NUMBERS = "539ff53490f90db11c1dda1276a20d5662244c886efb0501ed2bd447efb4fdb5"
ON_THE_PAGE = {"Sahl's 28": 28, "Curated List": 177, "Significant Stars": 486, "Full Catalogue": 1852}
CHOSEN_WORDS = re.compile(r"lesson|\bcourse\b|\bplan\b|working note|private|first tier|\bfigure \d|tools/|\b20\d\d-\d\d", re.I)
KINDS = {"Sahl's 28": "sahl", "Curated List": "curated", "Significant Stars": "significant", "Full Catalogue": "full"}


def _read_the_file():
    """Its header, its column line and its entries as (id, name, list, match, row), a - read as empty."""
    text = THE_FILE.read_text(encoding="utf-8")
    header = [line for line in text.splitlines() if line.startswith("#")]
    lines = [line for line in text.splitlines() if not line.startswith("#")]
    return header, lines, [tuple("" if cell == "-" else cell for cell in line.split("\t")) for line in lines[1:]]


@pytest.fixture(scope="module")
def entries():
    return _read_the_file()[2]


@pytest.fixture(scope="module")
def placed(engine):
    jd = engine["civil_local_to_jd_ut"](1240, 5, 23, 14.5, 11.25 / 15.0)
    return engine["fixed_star_places"](jd)[0]


# --- The file ------------------------------------------------------------------------------

def _digest_of(numbers):
    return hashlib.sha256("\n".join(sorted(numbers)).encode("utf-8")).hexdigest()


def test_the_file_stands_as_it_was_written():
    """Its digest over what follows it: a hand's edit moves one or the other."""
    header, lines, rows = _read_the_file()
    assert lines[0] == "id\tname\tlist\tmatch\trow"
    assert all(len(line.split("\t")) == 5 and "" not in line.split("\t") and line == line.strip() for line in lines)
    digest = hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()
    assert header[-1] == f"# rows: {len(rows)}; SHA-256 of what follows: {digest}"
    assert THE_FILE.read_bytes().endswith(b"\n") and b"\r" not in THE_FILE.read_bytes()


def test_the_lists_hold_their_entries_by_number(entries):
    curated = [row[0] for row in entries if row[2] == "curated"]
    every = [row[0] for row in entries]
    assert (len(curated), len(every), len(set(every))) == (177, 486, 486)
    assert {row[2] for row in entries} == {"curated", "significant"}
    assert _digest_of(curated) == CURATED_NUMBERS and _digest_of(every) == SIGNIFICANT_NUMBERS


def test_the_matches_named_by_hand_stand(entries):
    by_number = {row[0]: row for row in entries}
    for number, row in {"ngc:869": "Capulus", "messier:6": "Aculeus", "messier:7": "Acumen",
                        "messier:44": "Praesepe Cluster"}.items():
        assert by_number[number][3:] == ("same object", row)
    for number in ("ngc:6441", "hip:91919", "hip:91971", "hip:43100", "hip:102531", "hip:71681"):
        assert by_number[number][3] == "added", number
    assert {row[3] for row in entries} == {"position", "same object", "added"}
    assert sum(row[3] == "added" for row in entries) == 54
    assert sum(row[3] == "same object" for row in entries) == 4


def test_every_row_is_a_star_of_the_page_and_no_row_is_taken_twice(engine, entries, placed):
    identities = {engine["fixed_star_identity"](star) for star in placed}
    rows = [row[4] for row in entries if row[4]]
    assert len(rows) == len(set(rows)) == 486
    assert set(rows) <= identities
    assert sum(1 for row in entries if row[4] and row[2] == "curated") == 177
    assert all(bool(row[3]) == bool(row[4]) for row in entries)


def test_sahls_stars_all_stand_in_the_curated_list(engine, placed):
    curated = engine["fixed_star_list_members"]("curated")
    sahl = [star for star in placed if star.nature is not None]
    assert len(sahl) == 28
    assert [star.name for star in sahl if engine["fixed_star_identity"](star) not in curated] == []


def test_the_file_says_what_it_is_and_nothing_of_how_it_came(entries):
    """It reaches the public repository. It does not say where its lists came from or how they were
    chosen: the page's two marker lists, and these words."""
    from test_prose_counts import BUILD_PROCESS_MARKERS, COURSE_MARKERS
    header = "\n".join(_read_the_file()[0])
    assert header.count("\n") >= 5
    for text in (header, "\t".join(name for _number, name, *_rest in entries)):
        assert CHOSEN_WORDS.findall(text) == [] and BUILD_PROCESS_MARKERS.findall(text) == [] and COURSE_MARKERS.findall(text) == []


def test_the_file_ships():
    assert '("data/fixed_star_lists.tsv", "data")' in (ROOT / "build.spec").read_text(encoding="utf-8")


# --- The control -----------------------------------------------------------------------------

def test_one_control_above_the_tabs_in_these_words_opening_on_the_curated_list():
    at = fixed_stars_app().run(timeout=120)
    groups = at.main.button_group
    assert [g.options for g in groups] == [WORDS]
    assert groups[0].value == "Curated List" and groups[0].key == "_fixed_stars_population"
    for tab in ("Axes", "Star list"):
        assert len(tab_named(at, tab).button_group) == 0
    # A collapsed label takes its help with it: the reader could never open this one.
    assert groups[0].proto.label_visibility.value == type(groups[0].proto.label_visibility).VISIBLE
    assert groups[0].label == "Stars listed"
    assert groups[0].proto.help == ("Which stars both tabs and the export list, from Sahl's 28 to the whole catalogue "
                                    "with its nonstellar entries; the finder reaches every star.")


@pytest.mark.parametrize("word", WORDS)
def test_each_list_draws_what_the_list_holds(engine, placed, word):
    at = fixed_stars_app().run(timeout=120)
    strip = at.main.caption[0].value
    choose_population(at, word)
    assert at.main.caption[0].value == strip, "the chart stands"
    assert not at.exception
    star_tab = tab_named(at, "Star list")
    assert f"{word} · {ON_THE_PAGE[word]} entries shown" in [c.value for c in star_tab.caption]
    ordered = sorted(engine["fixed_star_listed"](placed, KINDS[word]), key=lambda star: star.longitude)
    assert len(ordered) == ON_THE_PAGE[word]
    if word == "Sahl's 28":
        assert [row["name"] for row in sahl_rows(at)] == [engine["fixed_star_shown_name"](star) for star in ordered]
        assert len(star_tab.dataframe) == 0
        return
    assert not opener_rows(star_tab, "zij-open-sahl-")
    table = star_tab.dataframe[0].value
    assert list(table.columns) == ["Name", "Designation", "Longitude", "Latitude (°)", "Right ascension (h m s)",
                                   "Declination (°)", "V magnitude"]
    assert list(table["Name"]) == [engine["fixed_star_shown_name"](star) for star in ordered]
    assert list(table["Longitude"]) == sorted(table["Longitude"])
    assert list(table["Designation"]) == [engine["fixed_star_designation_form"](star) for star in ordered]


def test_the_page_s_list_is_the_file_s_and_no_entry_is_absent(engine, entries, placed):
    identities = {engine["fixed_star_identity"](star): star for star in placed}
    for word, kind in (("Curated List", "curated"), ("Significant Stars", "significant")):
        wanted = [identities[row[4]] for row in entries if row[4] and (kind == "significant" or row[2] == kind)]
        assert {engine["fixed_star_identity"](star) for star in engine["fixed_star_listed"](placed, kind)} == {
            engine["fixed_star_identity"](star) for star in wanted}
        at = fixed_stars_app().run(timeout=120)
        choose_population(at, word)
        drawn = sorted(tab_named(at, "Star list").dataframe[0].value["Name"])
        assert drawn == sorted(engine["fixed_star_shown_name"](star) for star in wanted)
    assert not [row[1] for row in entries if not row[4]]
    assert {"NGC 884", "Coma Berenices", "NGC 6441"} <= set(drawn)


def test_the_greek_form_stands_on_every_row_and_a_label_prints_it_once(engine, placed):
    at = fixed_stars_app().run(timeout=120)
    choose_population(at, "Full Catalogue")
    table = tab_named(at, "Star list").dataframe[0].value
    assert (table["Designation"].astype(str).str.len() > 0).all()
    nameless = table[table["Name"] == table["Designation"]]
    assert len(nameless) > 100, "a star with no name holds its form in both columns"
    for star in placed:
        parts = engine["fixed_star_label"](star).split(" · ")
        assert len(parts) == len(set(parts)), parts


@pytest.mark.parametrize("word", WORDS)
def test_the_axes_tab_holds_only_the_chosen_list(engine, placed, word):
    at = fixed_stars_app().run(timeout=120)
    choose_population(at, word)
    members = {engine["fixed_star_identity"](star) for star in engine["fixed_star_listed"](placed, KINDS[word])}
    frame_rows = axis_lists(at)
    assert len(frame_rows) == 8
    for rows in frame_rows.values():
        assert {row["identity"] for row in rows} <= members


def test_a_longer_list_never_loses_a_shorter_list_s_row():
    at = fixed_stars_app().run(timeout=120)
    counts = {}
    for word in WORDS:
        choose_population(at, word)
        counts[word] = {(place, row["identity"]) for place, rows in axis_lists(at).items() for row in rows}
    assert counts["Sahl's 28"] <= counts["Curated List"] <= counts["Significant Stars"] <= counts["Full Catalogue"]
    assert len(counts["Curated List"]) < len(counts["Full Catalogue"]), "the premise: the list narrows this chart"


def test_an_axis_with_no_row_under_the_choice_says_so_in_the_page_s_own_words():
    at = fixed_stars_app().run(timeout=120)
    choose_population(at, "Sahl's 28")
    infos = {info.value for info in tab_named(at, "Axes").info}
    empties = [rows for rows in axis_lists(at).values() if not rows]
    assert empties, "the premise: Sahl's stars leave a list of this chart empty"
    assert infos <= {"No crossings within ±4 min.", "No entries within 1° in longitude."} and infos


@pytest.mark.parametrize("word", WORDS)
def test_the_export_follows_the_control_its_eight_lists_too(engine, placed, word):
    at = fixed_stars_app().run(timeout=120)
    choose_population(at, word)
    tables = _export(at)["results"]["Fixed stars"]
    assert list(tables)[-2:] == [f"Star list: {word}", "Stars harming eyes"] and len(tables) == 10
    star_list = tables[f"Star list: {word}"][0]["rows"]
    assert len(star_list) == ON_THE_PAGE[word]
    listed = engine["fixed_star_listed"](placed, KINDS[word])
    assert [row["Name"] for row in star_list] == [engine["fixed_star_shown_name"](star)
                                                  for star in sorted(listed, key=lambda star: star.longitude)]
    shown = axis_lists(at)
    for heading, rows in zip(list(tables)[:8], shown.values()):
        assert [row["Name"] for row in tables[heading][0]["rows"]] == [row["name"] for row in rows], heading
    assert f"List chosen: {word}." in json.dumps(_export(at), ensure_ascii=False)
    assert f"Star list: {word} · {ON_THE_PAGE[word]} entries." in [c.value for c in at.main.caption]


@pytest.mark.parametrize("word", WORDS)
def test_the_finder_and_a_record_reach_every_star_whatever_is_chosen(word):
    at = fixed_stars_app().run(timeout=120)
    choose_population(at, word)
    for query, title in (("Sirius", "Sirius"), ("Great Attractor", "Great Attractor"), ("ZerL2000", "ZerL2000")):
        find_star(at, query)
        assert _title(dialog_of(at)).startswith(title), (word, query)
        assert facts_of(at)["Longitude"], (word, query)
        at.run(timeout=120)
        assert dialog_of(at) is None


def test_a_row_of_each_table_opens_its_own_record_and_a_change_of_list_opens_nothing(monkeypatch):
    sync_engine_to_environment()
    import types
    import streamlit
    real, selected = streamlit.dataframe, {}

    def dataframe(data, **kwargs):
        real(data, **kwargs)
        return types.SimpleNamespace(selection=types.SimpleNamespace(rows=list(selected.get(kwargs.get("key"), ()))))
    monkeypatch.setattr(streamlit, "dataframe", dataframe)
    at = fixed_stars_app().run(timeout=120)
    for word in ("Curated List", "Significant Stars", "Full Catalogue"):
        choose_population(at, word)
        assert dialog_of(at) is None, word
        frame = tab_named(at, "Star list").dataframe[0].value
        selected[f"_fixed_stars_table_{word}"] = [3]
        at.run(timeout=120)
        assert _title(dialog_of(at)).startswith(frame["Name"][3]), word
        at.run(timeout=120)
        assert dialog_of(at) is None, word


def test_the_payload_is_held_across_runs_though_the_list_is_drawn_anew():
    at = fixed_stars_app().run(timeout=120)
    first = _export(at)
    at.run(timeout=120)
    assert _export(at) is first
    choose_population(at, "Significant Stars")
    assert _export(at) is not first


# --- The record's frame -----------------------------------------------------------------------

def test_the_record_s_facts_fill_their_frame_and_its_prose_keeps_its_measure():
    import house_style
    css = house_style.PAGE_STYLE
    tokens = json.loads((ROOT / "tools" / "house_style" / "tokens.json").read_text(encoding="utf-8"))["type"]
    assert "record_measure_px" not in tokens and "min(100%,1000px)" not in css
    group = re.search(r"\.zij-facts-group\{([^}]*)\}", css).group(1)
    nature = re.search(r"\.zij-nature\{([^}]*)\}", css).group(1)
    assert "width" not in group and "width" not in nature
    prose = f"width:min(100%,{tokens['prose_measure_px']}px)"
    assert prose in re.search(r"\.zij-facts-group p\{([^}]*)\}", css).group(1)
    assert prose in re.search(r"\.zij-nature p\{([^}]*)\}", css).group(1)
    assert "repeat(auto-fill,minmax(280px,1fr))" in css, "four columns in the large dialog's 1232 px, and no empty fifth"


def test_the_record_s_title_and_close_control_stand_in_view_by_stable_selectors():
    import house_style
    css = house_style.PAGE_STYLE
    dialog = '[data-testid="stDialog"]'
    assert f'{dialog}>div:has(>[role="dialog"]){{overflow:clip;}}' in css, "a hidden overflow would hold them in place"
    assert re.search(re.escape(f'{dialog} [role="dialog"]>h2[slot="title"]') + r"\{position:sticky;top:-32px;", css)
    assert re.search(re.escape(f'{dialog} [role="dialog"]>button[aria-label="Close"]') + r"\{position:sticky;top:-8px;", css)
    assert "st-emotion-cache" not in css


# --- The table's box -------------------------------------------------------------------------

GRID_RULES = ("_GRID_ROW_MARKER", "_GRID_FRAME", "_GRID_NARROWEST_BOX", "_GRID_NARROWEST_PAGE", "_GRID_SIDEWAYS_BAR", "_GRID_TEXT_PX",
              "_GRID_TEXT_ROOM", "_GRID_CELL_MARGIN", "_GRID_EVERY_ROW_BELOW", "GRID_ROW_HEIGHT", "_GRID_HEADER_HEIGHT", "_CELL_ADVANCE",
              "_NUMBER_CELL", "_is_missing", "_cell_text", "_drawn_width", "_rows_height", "_grid_column", "_page_frame", "_grid")


def _the_installed_grid_s_rule():
    """The selection column's width past each count of rows, read from the grid Streamlit ships:
    a pixel box is built on this figure, so an upgrade that moves it must fail here."""
    import streamlit
    bundles = (Path(streamlit.__file__).parent / "static" / "static" / "js").glob("DataFrame*.js")
    rule = re.compile(r"\?\?\(\w+>(\d+e?\d*)\?(\d+):\w+>(\d+e?\d*)\?(\d+):\w+>(\d+e?\d*)\?(\d+):(\d+)\)")
    found = [match.groups() for bundle in bundles for match in rule.finditer(bundle.read_text(encoding="utf-8"))]
    assert len(found) == 1, "the grid's rule for its selection column is not where it was: read it again"
    numbers = [int(float(number)) for number in found[0]]
    return (*zip(numbers[:6:2], numbers[1:6:2]), (-1, numbers[6]))


def _the_app_s_rule():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    held = [node.value for node in ast.parse(source).body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "_GRID_ROW_MARKER" for target in node.targets)]
    assert len(held) == 1
    return ast.literal_eval(held[0])


def test_the_selection_column_is_counted_at_the_width_the_grid_draws_it():
    assert _the_app_s_rule() == _the_installed_grid_s_rule()


@pytest.fixture(scope="module")
def grid_rule():
    """_grid, out of app.py, with a sink for what it would draw."""
    source, drawn = (ROOT / "app.py").read_text(encoding="utf-8"), []
    found = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in GRID_RULES:
            found[node.name] = ast.get_source_segment(source, node)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in GRID_RULES:
                    found[target.id] = ast.get_source_segment(source, node)
    sink = types.SimpleNamespace(dataframe=lambda data, **kwargs: drawn.append(kwargs))
    held = {"st": sink, "pd": pd, "math": math, "re": re, "house_style": house_style, "page_cell": page_cell, "page_column": page_column}
    exec("\n\n".join(found[name] for name in GRID_RULES), held)
    return held["_grid"], drawn


@pytest.mark.parametrize("rows, marker", [(0, 32), (1, 32), (100, 32), (101, 36), (162, 36), (1000, 36), (1001, 44),
                                          (1107, 44), (10000, 44), (10001, 48)])
def test_a_selectable_grid_s_box_holds_its_columns_at_every_count_of_rows(grid_rule, rows, marker):
    grid, drawn = grid_rule
    frame = pd.DataFrame({"Name": ["Alpha"] * rows, "Value": ["1.00"] * rows})
    grid(frame, selection_mode="single-row", hide_index=True, key="k")
    columns = sum(entry["width"] for entry in drawn[-1]["column_config"].values())
    assert drawn[-1]["width"] == columns + marker + 2
    grid(frame, hide_index=True)
    assert drawn[-1]["width"] == columns + 2, "a grid with no selection draws no such column"


def test_each_list_s_table_is_as_wide_as_its_columns_and_no_wider(monkeypatch):
    """What only a browser can show the whole of (the grid's scroller against its box) stands on
    this: Streamlit sets a pixel width on the grid's box, and the columns are those of the config."""
    sync_engine_to_environment()
    import streamlit
    real, drawn = streamlit.dataframe, {}

    def dataframe(data, **kwargs):
        drawn[kwargs.get("key")] = (len(data.data), kwargs)
        return real(data, **kwargs)
    monkeypatch.setattr(streamlit, "dataframe", dataframe)
    at = fixed_stars_app().run(timeout=120)
    rule = _the_installed_grid_s_rule()
    for word, box in (("Curated List", "pixels"), ("Significant Stars", "content"), ("Full Catalogue", "content")):
        choose_population(at, word)
        assert not at.exception
        rows, kwargs = drawn[f"_fixed_stars_table_{word}"]
        assert rows == ON_THE_PAGE[word]
        if box == "content":
            assert kwargs["width"] == "content", word
            continue
        columns = sum(entry["width"] for entry in kwargs["column_config"].values())
        assert kwargs["width"] == columns + next(width for over, width in rule if rows > over) + 2, word
    choose_population(at, "Sahl's 28")
    assert len(tab_named(at, "Star list").dataframe) == 0
