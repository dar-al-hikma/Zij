"""Re-pass of lane L7 (2026-10-04) on the development repository's main, 428e05e.

Every test here is a strict xfail that asserts the RIGHT behaviour and fails
today, one per finding of the re-pass (L7_REPASS.md in the corpus's
process/hostile_pass_2026-10-03/repass/): a finding of the pass that is fixed
for its own input but not for a neighbour (`partly`), one never closed
(`reopens`), or a new defect beside a fix (`N-NN`). Run with --runxfail to see
each fail at the assertion that states it.

No network; corpus reads go through tests/corpus_paths.py and do not skip when
the texts are present.
"""
from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
import textwrap
from datetime import time

import pytest

from conftest import EXECUTABLE_DIR, assert_no_exception, make_app, table_nodes
from corpus_paths import CORPUS_DIR
from skip_guard import needs_corpus

# The tests that run a corpus-reading pin skip where the corpus is absent (CI), as
# every corpus test does; with the corpus present the skip guard forbids it.
_corpus = needs_corpus()


def _render(page, depth="Course text", date="1240-05-23", **state):
    at = make_app(date=date, page=page)
    at.session_state["_reading_depth"] = depth
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "2026-10-03"
    for key, value in state.items():
        at.session_state[key] = value
    at.run(timeout=180)
    assert_no_exception(at, page)
    return at


def _cells(at):
    for heading, node in table_nodes(at):
        df = node.value
        for col in df.columns:
            for i, v in enumerate(df[col]):
                yield heading, col, i, v


# Charts the re-pass added to the page-text sieve (all through the sidebar's own keys).
YOUNG_DAY = dict(date="1990-08-04", time_input_key=time(10, 5), time_standard_key="Manual UTC offset",
                 utc_offset_key=-3.0, manual_coords_key=True, manual_lat_key=-23.55, manual_lon_key=-46.63)
JULIAN_NIGHT = dict(date="1500-12-01", time_input_key=time(3, 15), time_standard_key="LMT (Local Mean Time)",
                    manual_coords_key=True, manual_lat_key=59.33, manual_lon_key=18.07)
ANCIENT = dict(date="0500-03-01", time_input_key=time(6, 0), time_standard_key="LMT (Local Mean Time)",
               manual_coords_key=True, manual_lat_key=31.2, manual_lon_key=29.9)


# --- L7-01, partly: the other Lot ends the table keys by id -----------------

def test_repass_l7_01_no_lot_formula_names_an_end_by_its_table_id():
    at = _render("lots", "Course text and supplement")
    formulas = [str(v) for _h, col, _i, v in _cells(at) if col == "Formula"]
    assert formulas, "premise: the Lots page draws its Formula columns"
    ids = [f for f in formulas if re.search(r"\((?:fortune|spirit) - |- (?:fortune|spirit)\)", f)]
    assert not ids, ids[:4]


# --- L7-05, partly: Python booleans through the UI boundary ----------------

def test_repass_l7_05_no_python_boolean_in_an_unresolved_cell():
    offenders = []
    for page, chart in (("findings", YOUNG_DAY), ("releaser", JULIAN_NIGHT), ("configurations", ANCIENT)):
        state = dict(chart)
        at = _render(page, "Course text", date=state.pop("date"), **state)
        for heading, col, _i, v in _cells(at):
            if re.search(r": (?:True|False)\b", str(v)):
                offenders.append((page, heading, col, str(v)[-90:]))
        for key in ("_analysis_markdown", "_analysis_html"):
            for m in re.finditer(r".{0,60}: (?:True|False)\b\)?", at.session_state[key]):
                offenders.append((page, key, m.group(0)))
    assert not offenders, offenders[:6]


# --- L7-06, partly: NaN cells in the very table L7-06 named ---------------

def test_repass_l7_06_no_nan_status_cells_beside_an_unresolved_row():
    bad = []
    state = dict(ANCIENT)
    timing = _render("timing", "Course text", date=state.pop("date"), **state)
    configurations = _render("configurations", "Course text", date="1240-04-01")
    headings = {h for h, _n in table_nodes(timing)} | {h for h, _n in table_nodes(configurations)}
    assert {"Indicator 15: relationship details", "Handing Over"} <= headings, "premise: the tables are drawn"
    for at in (timing, configurations):
        bad += [(h, i) for h, c, i, v in _cells(at)
                if c == "Status" and ((isinstance(v, float) and math.isnan(v)) or str(v) == "nan")]
    assert not bad, (len(bad), sorted({h for h, _i in bad}))


# --- L7-13, reopens (never closed) -----------------------------------------

def test_repass_l7_13_the_pages_render_fixture_pins_at_least_one_value():
    fixture = json.loads((EXECUTABLE_DIR / "tests" / "fixtures" / "tables.json").read_text(encoding="utf-8"))
    shapes = {len(entry) for chart in fixture.values() for slot in chart.values() for entry in slot}
    assert shapes, "premise: the fixture has entries"
    assert shapes != {2}, f"every entry is [heading, columns] (entry lengths {sorted(shapes)}): identity only"


# --- N-04: the L7-16 pin passes when its sentence is not drawn -------------

def test_repass_l7_16_pin_fails_when_its_sentence_is_absent(monkeypatch):
    import test_hostile_l7_2026_10_03 as L7
    real = L7._render
    # A render on which the Findings page's eyesight note is not drawn.
    monkeypatch.setattr(L7, "_render", lambda page, depth="Course text", date="1240-05-23", **state:
                        real("sources", depth))
    with pytest.raises(AssertionError):
        L7.test_l7_16_findings_page_names_the_volume_of_figure_57()


# --- HP-21, partly: the oracle's almuten field never reaches production ----

def test_repass_hp21_the_oracles_almuten_field_reaches_the_production_pick(engine):
    import test_differential_oracle as O
    read = []

    class Traced(dict):
        def __getitem__(self, key):
            read.append(key)
            return dict.__getitem__(self, key)

    ns = Traced(engine)
    case = O._cases()[0]
    O._actual(ns, case)
    assert read, "premise: the oracle reads the engine"
    assert any("almuten" in k or k == "calculate_prenatal_syzygy" for k in read), (
        f"the oracle's almuten field is computed in the test from {sorted(set(read))}")


# --- N-01: VII.6, 23's "approximated" circle of the apogee is a coin flip --

APOGEE_LABEL = "Apogee circle, approximated by distance from the earth (23)"


def test_repass_vii6_23_counts_a_condition_that_tracks_the_circle_of_the_apogee(engine):
    """Gr. Intr. VII.1, 10 (Gr. Intr. p. 408): a planet is rising in the circle of
    its apogee when 'the corrected planet is at the top of its apogee, or between it
    and [the apogee] are less than 90 degrees to the right or left'. The witness
    gives the engine every benefit: for each planet it takes the apogee longitude
    (0-358, step 2) that agrees best with the engine over the sample. Right
    behaviour: either the condition is not counted for these five (the texts give
    no apogee positions to compute it from), or it tracks the rule (>= 90%)."""
    import random
    E = engine
    rng = random.Random(20261004)
    lat, lon = 43.7792, 11.2463
    planets = ("Saturn", "Jupiter", "Mars", "Venus", "Mercury")
    samples = {p: [] for p in planets}
    for _ in range(240):
        jd = 2415020.5 + rng.random() * 200 * 365.25          # 1900-2100
        chart = E["calculate_traditional_chart_jd"](jd, lat, lon)
        p, sect = chart["planetary_data"], chart["sect"]
        essential = E["evaluate_essential_dignities"](p, sect)
        accidental = E["evaluate_accidental_dignities"](p, chart["houses"], sect, chart["julian_day"],
                                                        armc=chart["armc"], obliquity=chart["obliquity"], geo_lat=lat)
        cond = E["evaluate_abu_mashar_condition"](p, chart["houses"], sect, essential, accidental,
                                                  chart["julian_day"], chart["ascendant"], None)
        for planet in planets:
            samples[planet].append((APOGEE_LABEL in cond[planet]["Positive Labels"], p[planet]["longitude"]))
    counted = sum(c for rows in samples.values() for c, _l in rows)
    if counted == 0:
        return                                                 # not counted: the other right behaviour
    worst = []
    for planet, rows in samples.items():
        best = max(sum(1 for c, lng in rows if c == (abs(((lng - a + 180) % 360) - 180) < 90)) / len(rows)
                   for a in range(0, 360, 2))
        worst.append((round(best, 3), planet))
    assert min(worst)[0] >= 0.9, f"best agreement with any apogee, per planet: {sorted(worst)}"


# --- HP-27, partly: the export still copies an evaluator's raw row ---------

def _markdown_section_columns(md, heading):
    i = md.find(f"#### {heading}\n")
    assert i >= 0, f"premise: the export has a '{heading}' section"
    for line in md[i:].split("\n")[1:12]:
        if line.startswith("| "):
            return [c.strip() for c in line.strip().strip("|").split("|")]
    raise AssertionError(f"premise: no table under '{heading}'")


def test_repass_hp27_the_collection_export_carries_the_pages_columns():
    at = _render("configurations", "Course text and supplement")
    page = [list(map(str, n.value.columns)) for h, n in table_nodes(at) if h == "Collection of Light"]
    assert page, "premise: the Configurations page draws Collection of Light on 1240-05-23"
    exported = _markdown_section_columns(at.session_state["_analysis_markdown"], "Collection of Light")
    extra = [c for c in exported if c not in page[0]]
    assert not extra, (page[0], extra)


# --- N-02: Python reprs of number lists on pages and in the exports --------

def test_repass_no_python_list_repr_of_numbers_on_the_pages():
    offenders = []
    for page in ("reference", "configurations"):
        at = _render(page, "Course text and supplement")
        for heading, col, _i, v in _cells(at):
            if re.search(r"\[\d+(?:, \d+)+\]", str(v)):
                offenders.append((page, heading, col, str(v)[:80]))
    assert not offenders, offenders[:5]


# --- N-03: a negative zero and a float repr in the exports ------------------

# Narrowed by the owner's ruling 9 (2026-10-05): "-0.00" stays (a negative value
# that rounds to zero keeps its sign, its unrounded value beside it); what the
# exports must not print is scientific notation (a float with a negative
# exponent, the form the check found).
def test_repass_exports_print_no_float_with_a_negative_exponent():
    state = dict(YOUNG_DAY)
    at = _render("chart", "Course text", date=state.pop("date"), **state)
    md = at.session_state["_analysis_markdown"]
    bad = re.findall(r".{0,40}(?:\d(?:\.\d+)?e-\d\d).{0,20}", md)
    assert not bad, bad[:3]


# --- L7-23, partly: the same label shape at 60 and 69 is unpinned ----------

@_corpus
def test_repass_l7_23_a_drift_of_the_60_or_69_eyesight_label_fails_a_pin(engine):
    import inspect
    import test_hostile_pins_2026_10_03 as P
    pins = [fn for name, fn in inspect.getmembers(P, inspect.isfunction)
            if name.startswith("test_pin_") and list(inspect.signature(fn).parameters) == ["engine"]]
    assert pins, "premise: the pins file has engine pins"
    drifts = (("_EYE_RULE_60", "60: ", "61: "), ("_EYE_RULE_69", "69: ", "70: "),
              ("_EYE_RULE_69", "corruption of vision", "corruption of sight"))
    assert len(drifts) == 3
    uncaught = []
    for name, old, new in drifts:
        assert old in engine[name], f"premise: {name} carries {old!r}"
        mutated = dict(engine)
        mutated[name] = engine[name].replace(old, new, 1)
        caught = False
        for fn in pins:
            try:
                fn(mutated)
            except AssertionError:
                caught = True
                break
        if not caught:
            uncaught.append((name, old, new))
    assert not uncaught, f"no pin fails on: {uncaught}"


# --- N-05: the chart-name box suggests the suite's own chart ----------------

def test_repass_the_chart_name_placeholder_names_no_test_chart():
    at = _render("chart")
    boxes = [t for t in at.sidebar.text_input if t.label.startswith("Chart name")]
    assert boxes, "premise: the sidebar has the chart-name box"
    placeholder = boxes[0].proto.placeholder
    assert not re.search(r"\btest\b", placeholder, re.I), placeholder


# --- N-06: a typed testimony sentence printed as a Python dict ---------------

def test_repass_exports_print_no_serialised_result_in_a_testimony():
    at = _render("chart", "Course text", date="1240-04-01")
    md, html = at.session_state["_analysis_markdown"], at.session_state["_analysis_html"]
    assert "#### Weakness of the Planets" in md, "premise: the export carries the Weakness table"
    for name, text in (("markdown", md), ("html", html)):
        bad = re.findall(r".{0,60}(?:'result_type'|&#x27;result_type&#x27;|'display_alternatives').{0,40}", text)
        assert not bad, (name, bad[:2])


# --- L7-24, partly: the new pin compares word sets ---------------------------

@_corpus
def test_repass_l7_24_a_word_dropped_from_the_pinned_lords_cell_fails_its_pin(engine):
    import copy
    import test_hostile_pins_2026_10_03 as P
    cell = engine["MASHAALLAH_LORDS"][2][3]
    assert cell["text"].endswith("and they seek him out"), "premise: the cell as pinned"
    lords = copy.deepcopy(engine["MASHAALLAH_LORDS"])
    lords[2][3]["text"] = cell["text"].replace("seek him out", "seek out")
    mutated = dict(engine)
    mutated["MASHAALLAH_LORDS"] = lords
    with pytest.raises(AssertionError):
        P.test_pin_the_lord_of_the_third_in_the_second_keeps_its_wording(mutated)
