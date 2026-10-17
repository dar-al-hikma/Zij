"""The Releaser page's form (the follow-ups of 2026-10-05, lane KG: K-26, K-28).

K-28's pin (in ``test_followups_2026_10_05.py``) asks that each arm of an
election open on the Moon's easternness be drawn directed. These hold the rest
of the fix: each arm's table is drawn under a line naming its arm, the export
files the same tables under the same labels with the same rows, and a settled
election draws and exports no arm at all. K-26's pin asks that the line on
Mercury's +20 come after Abu 'Ali's heading; the last test holds it inside his
block, under his table, before the next heading.
"""
from datetime import time

from conftest import assert_no_exception, make_app, table_nodes

MANUAL = "Manual UTC offset"
RELEASER = "The releaser and the house-master (Sahl, *On Nativities* 1.15-1.16, 1.20)"
ARMS = ("PN IV testimony #3, if the Moon is eastern", "PN IV testimony #3, if the Moon is not eastern")


def _render(date, **state):
    at = make_app(date=date, page="releaser")
    for key, value in state.items():
        at.session_state[key] = value
    at.run(timeout=300)
    assert_no_exception(at, f"releaser {date}")
    return at


def _open_chart():
    # 1900-04-27 08:00 UT, Florence: the election is open on the Moon's
    # easternness (the Sun on one arm, the meeting on the other).
    return _render("1900-04-27", time_input_key=time(8, 0), time_standard_key=MANUAL, utc_offset_key=0.0,
                   _target_mode="Date", _target_date="1960-06-01")


def _arm_exports(at):
    entries = at.session_state["_analysis_export"]["results"]["Prediction"].get(RELEASER, [])
    return {e["label"]: e for e in entries if isinstance(e.get("label"), str) and e["label"].startswith(ARMS[0][:20])}


def test_each_arm_is_drawn_under_its_label_and_exported_as_drawn():
    at = _open_chart()
    nodes = list(at.main)
    exported = _arm_exports(at)
    assert sorted(exported) == sorted(ARMS), sorted(exported)
    for label in ARMS:
        line = [i for i, n in enumerate(nodes)
                if getattr(n, "type", None) == "markdown" and str(n.value).startswith(f"**{label}:**")]
        assert len(line) == 1, (label, line)
        table = nodes[line[0] + 1]
        assert getattr(table, "type", None) == "dataframe", (label, getattr(table, "type", None))
        drawn = table.value
        assert "Distributor" in drawn.columns
        entry = exported[label]
        assert sorted(entry["columns"]) == sorted(map(str, drawn.columns)), (label, entry["columns"])
        assert len(entry["rows"]) == len(drawn) > 0, (label, len(entry["rows"]), len(drawn))
        assert [str(r["Distributor"]) for r in entry["rows"]] == [str(v) for v in drawn["Distributor"]], label


def test_the_arm_lines_name_each_arms_releaser_and_choose_neither():
    at = _open_chart()
    bodies = [str(m.value) for m in at.main.markdown]
    eastern = next(b for b in bodies if b.startswith(f"**{ARMS[0]}:**"))
    western = next(b for b in bodies if b.startswith(f"**{ARMS[1]}:**"))
    assert eastern.startswith(f"**{ARMS[0]}:** the Sun, by "), eastern[:120]
    assert western.startswith(f"**{ARMS[1]}:** the meeting (the last New Moon), by "), western[:120]
    assert "neither arm is chosen" in " ".join(bodies)


def test_a_settled_election_draws_and_exports_no_arm():
    at = _render("1240-05-23", _target_mode="Age", _target_age=30)
    bodies = " ".join(str(m.value) for m in at.main.markdown)
    assert "PN IV testimony #3:" in bodies, "the premise: the settled releaser's line is drawn"
    assert "PN IV testimony #3, if the Moon" not in bodies
    assert not _arm_exports(at)
    directed = [h for h, n in table_nodes(at) if h == RELEASER and "Distributor" in n.value.columns]
    assert len(directed) == 2, directed     # the releaser's distribution and PN IV's table, as before


def test_the_mercury_line_stands_in_abu_alis_block_under_its_table():
    at = _render("1240-05-23", _reading_depth="Course text and supplement", _target_mode="Age", _target_age=30)
    nodes = list(at.main)
    kinds = [getattr(n, "type", None) for n in nodes]
    heads = [i for i, k in enumerate(kinds) if k == "subheader"]
    start = next(i for i in heads if "(Abu 'Ali)" in nodes[i].value)
    end = next((i for i in heads if i > start), len(nodes))
    lines = [i for i in range(len(nodes)) if kinds[i] == "markdown"
             and str(nodes[i].value).startswith("Under the adopted reading of ‘which add,’ Mercury’s +20")]
    assert len(lines) == 1, lines
    table = next(i for i in range(start, end) if kinds[i] == "dataframe")
    assert table < lines[0] < end, (start, table, lines[0], end)
