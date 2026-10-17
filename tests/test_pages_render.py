"""Every page renders without exception on every chart, and renders exactly
the tables the fixture says it does -- as a multiset of (heading, columns),
not a count. Counting st.dataframe calls is what passed commit 3dbf4af,
which lost two tables and duplicated two others.

An entry may carry a third element, values the rendered table must show:
cells read off a printed page and verified there (the entry names its
witness), never the engine's own output copied back, which would only pin
the engine to itself. They are checked on every run; an update run checks
them too and keeps them as they are, never taking them from the render.

To accept a deliberate change to the set of tables:

    UPDATE_TABLE_FIXTURE=1 .venv/bin/python -m pytest tests/test_pages_render.py

then read the diff of tests/fixtures/tables.json before committing it. Serially: the
writer is per session, so under xdist each worker would write only its own slots, and
conftest refuses an update run that has -n. The file is written whole or not at all:
only when every chart's every page was rendered and recorded and no test of the run
failed. A failure anywhere (a value pin among them), or a run narrowed with -k, leaves
tables.json as it was.
"""
import json
import os

import pytest

from conftest import (CHARTS, TABLES_FIXTURE, assert_no_exception, describe_table_diff, dump_fixture,
                      load_table_fixture, make_app, page_slots, slot_name, table_inventory, table_nodes)

_REWRITE_SWITCH = "UPDATE_TABLE_FIXTURE"
UPDATE = os.environ.get(_REWRITE_SWITCH) == "1"
_collected = {}


def _render(date, page, view):
    at = make_app(date=date, page=page, view=view)
    # Pin the target to the day the fixture was regenerated on (an ISO
    # date string, the key app.py reads through _reading("target_date",
    # "_target_date", ...)) so a page whose table set is target-dependent
    # -- the Timing page's "image of the revolution" tables, which drop a
    # row set when the birthday target rolls the revolution in force to a
    # new year -- does not drift off the fixture on the day this suite runs.
    at.session_state["_target_date"] = "2026-09-17"
    at.run()
    assert_no_exception(at, f"{date} {slot_name(page, view)}")
    return at


def _assert_pinned_values(at, date, slot, entries):
    """Each entry's third element, if any: {"key": column, "cells": {key value:
    {column: value}}, "witness": where the values were read}. The rendered
    table under that heading and columns shows exactly those values."""
    rendered = table_nodes(at)
    for entry in entries:
        if len(entry) < 3:
            continue
        heading, columns, pins = entry
        nodes = [node for h, node in rendered if h == heading and list(node.value.columns) == list(columns)]
        assert nodes, f"{date} {slot}: no {heading!r} table rendered to read its pinned values from"
        df = nodes[0].value
        assert pins["cells"], f"{date} {slot}: {heading!r} pins no cell"
        for row_value, cells in pins["cells"].items():
            rows = df[df[pins["key"]] == row_value]
            assert len(rows) == 1, f"{date} {slot}: {heading!r} has {len(rows)} rows {pins['key']} = {row_value!r}"
            for column, value in cells.items():
                got = rows.iloc[0][column]
                assert got == value, (f"{date} {slot}: {heading!r}, {row_value} / {column}: rendered {got!r}, "
                                      f"the page prints {value!r} ({pins['witness']})")


def _keep_pins(before, rows, date, slot):
    """An update run: each value pin of the fixture as it was goes onto the
    table it pins in the new rows; one whose table is gone fails the update
    instead of vanishing from the fixture (a failed update run writes nothing:
    _write_fixture_at_end)."""
    for heading, columns, pins in (e for e in before if len(e) > 2):
        target = next((r for r in rows if len(r) == 2 and r[0] == heading and r[1] == columns), None)
        assert target is not None, f"{date} {slot}: the table {heading!r} that carries value pins is gone"
        target.append(pins)
    return rows


@pytest.mark.parametrize("date", list(CHARTS))
@pytest.mark.parametrize("page,view", page_slots(), ids=[slot_name(p, v) for p, v in page_slots()])
def test_page_renders_expected_tables(date, page, view):
    at = _render(date, page, view)
    slot = slot_name(page, view)
    actual = table_inventory(at)

    # The page header is the one element every page must have; a page that
    # rendered nothing at all would otherwise pass with an empty inventory.
    assert len(at.main.header) >= 1, f"{date} {slot}: no st.header rendered"
    # Structure, not values: _finding() suppresses empty findings and the
    # fixed tables are never empty, so a rendered table with no rows is a
    # table that lost its data.
    for (heading, _cols), df in zip(actual, at.main.dataframe):
        assert len(df.value) > 0, f"{date} {slot}: {heading!r} rendered with no rows"

    if UPDATE:
        # The value pins are read off a page, not the engine: checked, then
        # kept on the table they pin (_keep_pins).
        before = (load_table_fixture() if TABLES_FIXTURE.exists() else {}).get(date, {}).get(slot, [])
        _assert_pinned_values(at, date, slot, before)
        _collected.setdefault(date, {})[slot] = _keep_pins(before, [[h, c] for h, c in actual], date, slot)
        return

    fixture = load_table_fixture()
    expected = [(e[0], e[1]) for e in fixture.get(date, {}).get(slot, [])]
    assert fixture.get(date, {}).get(slot) is not None, (
        f"no fixture entry for {date} {slot}; regenerate with UPDATE_TABLE_FIXTURE=1")
    diff = describe_table_diff(expected, actual)
    assert not diff, (
        f"{date} {slot}: the tables rendered do not match tests/fixtures/tables.json\n{diff}\n"
        f"  ({len(expected)} expected, {len(actual)} rendered)")
    _assert_pinned_values(at, date, slot, fixture[date][slot])


def test_the_fixture_pins_values_read_off_a_page():
    """The value pins exist, and each is its witness's literal, not a copy of
    the engine: Sahl's Figure 57 (Sahl I p. 378), as test_table_pins_2026_09_23
    holds it read off the page photograph."""
    import re
    from test_table_pins_2026_09_23 import SAHL_I_FIG57, SIGN
    fixture = load_table_fixture()
    pinned = [(d, s, e) for d, slots in fixture.items() for s, entries in slots.items() for e in entries if len(e) > 2]
    assert pinned, "tests/fixtures/tables.json pins no rendered value: every entry is [heading, columns]"
    figure_57 = {SIGN[glyph]: degrees for glyph, degrees in SAHL_I_FIG57.items()}
    for date, slot, (heading, columns, pins) in pinned:
        assert pins.get("witness"), (date, slot, heading)
        assert heading == "Degrees of nobility and rank", f"{heading!r}: name its literal here"
        assert "Sahl I p. 378" in pins["witness"]
        for sign, cells in pins["cells"].items():
            for value in cells.values():
                assert tuple(int(n) for n in re.findall(r"\d+", value)) == figure_57[sign], (sign, value)


def test_a_pin_failing_in_an_updating_run_leaves_the_fixture_as_it_was(tmp_path):
    """The blind check's case (G14, note 13): the nobility cells rendered a
    degree low, then an update run over that page and one other. The pinned
    slot fails at its pin while the other is recorded; tables.json must be left
    byte for byte as it was, pins and all. The writer used to write what it had
    recorded, so the failed slot, and its pins with it, left the file. Run in a
    copy of the tree, in a process of its own (an update run refuses xdist)."""
    import shutil
    import subprocess
    import sys

    from conftest import EXECUTABLE_DIR
    tree = tmp_path / "tree"
    tree.mkdir()
    for path in EXECUTABLE_DIR.iterdir():
        if path.name in (".git", "__pycache__", "tests"):
            continue
        if path.suffix == ".py" or path.name == "pytest.ini":
            shutil.copy2(path, tree / path.name)
        else:
            (tree / path.name).symlink_to(path)
    shutil.copytree(EXECUTABLE_DIR / "tests", tree / "tests",
                    ignore=shutil.ignore_patterns("__pycache__", ".xdg-scratch"))
    app = tree / "app.py"
    source = app.read_text(encoding="utf-8")
    cell = "', '.join(pn4_ordinal(d) for d in NOBILITY_DEGREES.get(sg, []))"
    assert source.count(cell) == 1, "premise: the nobility cell's one line"
    app.write_text(source.replace(cell, cell.replace("pn4_ordinal(d)", "pn4_ordinal(d - 1)")), encoding="utf-8")
    original = EXECUTABLE_DIR / "tests" / "fixtures" / "tables.json"
    assert b'"witness"' in original.read_bytes(), "premise: the fixture carries a value pin"

    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTEST_")}
    env.update({_REWRITE_SWITCH: "1", "XDG_DATA_HOME": str(tmp_path / "xdg"), "PYTHONDONTWRITEBYTECODE": "1"})
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_pages_render.py", "-q", "-p", "no:cacheprovider",
         "-k", "test_page_renders_expected_tables and 1240-05-23 and (reference or sources)"],
        cwd=tree, env=env, capture_output=True, text=True, timeout=600)
    out = run.stdout + run.stderr
    assert "1 failed, 1 passed" in out, out[-3000:]                 # one slot recorded, the pinned one failed
    assert "the page prints '19th'" in out, out[-3000:]               # ... at its pin
    assert (tree / "tests" / "fixtures" / "tables.json").read_bytes() == original.read_bytes(), (
        "the update run rewrote tables.json after a pinned value failed")
    assert "tables.json not written" in out, out[-3000:]


def _say(request, line):
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    (reporter.write_line if reporter else print)(line)


@pytest.fixture(scope="session", autouse=True)
def _write_fixture_at_end(request):
    """An update run writes the fixture whole or not at all. A slot whose test
    failed is missing from _collected, so writing what was recorded would drop
    it, value pins and all; a run narrowed with -k would write only the slots
    it rendered. So: only when every chart's every page was recorded and no
    test of the run failed."""
    yield
    if UPDATE:
        wanted = {(date, slot_name(page, view)) for date in CHARTS for page, view in page_slots()}
        recorded = {(date, slot) for date, slots in _collected.items() for slot in slots}
        failed = request.session.testsfailed
        if failed or recorded != wanted:
            _say(request, f"\n{TABLES_FIXTURE.name} not written: {failed} test(s) failed, "
                          f"{len(wanted - recorded)} of {len(wanted)} slots not recorded. It is written only by a "
                          "clean run of the whole file.")
            return
        TABLES_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        ordered = {d: dict(sorted(v.items())) for d, v in sorted(_collected.items())}
        TABLES_FIXTURE.write_text(dump_fixture(ordered))
        print(f"\nwrote {TABLES_FIXTURE}")


# --- The Days and months page's own reading (PN IV, IX.1, 26-34) ---------
# This switch is NOT in conftest.SWITCHES: it is read only by page_days
# (the Days & Months tab of page_timing until 2026-09-17),
# so putting it in the registry would double the Configurations
# cross-product (2**8 states x 6 charts) to prove nothing. It is covered
# instead by the doctrine fixtures, which pin the rule itself, and by
# these two renders, which prove both settings draw the page.

@pytest.mark.parametrize("date", list(CHARTS))
@pytest.mark.parametrize("turn", ["Dykes: always forward", "PN IV IX.1, 26-34"])
def test_days_page_renders_under_both_monthly_turn_readings(date, turn):
    at = make_app(date=date, page="days")
    at.session_state["_pn4_monthly_turn"] = turn
    at.run()
    assert_no_exception(at, f"{date} days, monthly turn = {turn}")
    assert len(at.main.dataframe) > 0


def test_abu_mashars_turn_actually_reverses_a_convertible_indicator():
    """Not just "it renders": under Abu Ma'shar's rule at least one of the
    seven monthly indicators must be turned backwards on some chart, or
    the switch is inert. The default must leave every one forward."""
    def directions(turn):
        at = make_app(date="1240-05-23", page="days")
        at.session_state["_pn4_monthly_turn"] = turn
        at.run()
        assert_no_exception(at, f"timing {turn}")
        for df in at.main.dataframe:
            if "Turned" in df.value.columns:
                return list(df.value["Turned"])
        pytest.fail("the monthly indicators table did not render")

    default = directions("Dykes: always forward")
    assert not any(d.startswith("backwards") for d in default), default
    assert any(d.startswith("backwards") for d in directions("PN IV IX.1, 26-34"))
