"""The open election's releaser note, its two locators split (2026-10-15).

Where Sahl's election of the longevity releaser is left open on the Moon's
easternness, the luminary proxies' first rows read "unavailable: " and the
releaser note. The note cites On Nativities 1.20, 6 for the condition, as this
app reads it, and On Nativities 1.22, 1-8 for the definition that leaves the
Moon out. Each locator stands in its own parenthesis and names its work, and
the reading label stays with 1.20, 6, as the governor's longer sentence has it.
A wording change: the election, the year's lord and the proxies' rows are as
they were.
"""
from __future__ import annotations

import ast
import json
import re
from datetime import date, datetime, time
from pathlib import Path

import pytest

from conftest import assert_no_exception, make_app

ENGINE_DIR = Path(__file__).resolve().parent.parent

NOTE = ("the releaser is unresolved, since its election turns on the Moon's easternness (On Nativities 1.20, 6, "
        "as this app reads it), which the texts do not define (On Nativities 1.22, 1-8)")
OLD = "the releaser is unresolved on the Moon's easternness (On Nativities 1.20, 6, as this app reads it; 1.22, 1-8)"
# Florence, 1900-04-27 08:00 UT: the election is open. Its profected year is
# the Moon's at 1960-06-01 and the Sun's at 1961-06-01.
FLORENCE = (43.7792, 11.2463)
YEARS = (("1960-06-01", "Moon"), ("1961-06-01", "Sun"))
_LOCATOR = re.compile(r"\d+\.\d+, \d+(?:-\d+)?")


def _bundle(engine, target):
    chart = engine["calculate_traditional_chart"](datetime(1900, 4, 27, 8, 0), *FLORENCE)
    return engine["pn4_timing_bundle"](chart, *FLORENCE, date(1900, 4, 27), date.fromisoformat(target),
                                       engine["PN4_MONTHLY_TURN_OPTIONS"][0], {"Hour Lord": "Venus", "Approximate": False})


def _assert_split(note):
    """Each locator in its own parenthesis, naming its work; the reading
    label in 1.20, 6's and not in 1.22, 1-8's."""
    groups = re.findall(r"\(([^()]*)\)", note)
    assert groups == ["On Nativities 1.20, 6, as this app reads it", "On Nativities 1.22, 1-8"], groups
    found = [(m.group(0), note[max(0, m.start() - len("On Nativities ")):m.start()]) for m in _LOCATOR.finditer(note)]
    assert found == [("1.20, 6", "On Nativities "), ("1.22, 1-8", "On Nativities ")], found
    assert "as this app reads it" in groups[0] and "as this app reads it" not in groups[1]


@pytest.mark.parametrize("target,lord", YEARS)
def test_the_proxies_reads_cells_carry_the_split_note_whole(engine, target, lord):
    b = _bundle(engine, target)
    assert engine["is_unresolved"](b["releaser"]["longitude"]), "premise: the election is open"
    assert b["year"]["lord"] == lord, "premise: a luminary's year, so the proxies table has its releaser rows"
    assert b["releaser_note"] == NOTE
    cells = [row["Reads"] for row in b["proxies"] if "easternness" in row["Reads"]]
    assert cells == ["unavailable: " + NOTE] * 2, cells
    _assert_split(cells[0][len("unavailable: "):])
    assert OLD not in cells[0]


def test_the_note_reaches_the_timing_page_and_the_exports():
    at = make_app(date="1900-04-27", page="timing", timeout=300)
    at.session_state["_reading_depth"] = "Course text"
    for key, value in dict(time_input_key=time(8, 0), time_standard_key="Manual UTC offset", utc_offset_key=0.0,
                           _target_mode="Date", _target_date="1960-06-01").items():
        at.session_state[key] = value
    at.run(timeout=300)
    assert_no_exception(at, "timing 1900-04-27 at 1960-06-01")
    cells = [cell for df in at.dataframe if "Reads" in getattr(df.value, "columns", [])
             for cell in df.value["Reads"] if "easternness" in str(cell)]
    assert cells == ["unavailable: " + NOTE] * 2, cells
    for export in ("_analysis_markdown", "_analysis_html"):
        text = at.session_state[export].replace("&#x27;", "'").replace("&#39;", "'")
        assert text.count("unavailable: " + NOTE) == 2, export
        assert OLD not in text, export
    exported = json.dumps(at.session_state["_analysis_export"], ensure_ascii=False)
    assert exported.count("unavailable: " + NOTE) == 2 and OLD not in exported


def test_only_the_open_branch_of_the_note_changed():
    """The five branches of the releaser note in the profection-year bundle:
    the open election's split, the other four as they were."""
    tree = ast.parse((ENGINE_DIR / "engine.py").read_text(encoding="utf-8"))
    fn, = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "pn4_timing_bundle"]
    values = [ast.unparse(n.value) if not isinstance(n.value, ast.Constant) else n.value.value for n in ast.walk(fn)
              if isinstance(n, ast.Assign) and any(getattr(t, "id", None) == "releaser_note" for t in n.targets)]
    assert values == [NOTE, "no releaser by On Nativities 1.15 (the releaser section)", "refused above the polar circle",
                      "f'age {age} is past the {PN4_DISTRIBUTION_SPAN_YEARS:g}-year table'", None], values
