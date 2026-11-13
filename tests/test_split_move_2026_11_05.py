"""The pictures and the HTML report, split out of engine.py: what they read reaches them.

wheel.py and export_html.py read what they need of the engine's through one
accessor, when they are called, and take markup.py's names by import. The guard
(tests/test_split_astro_2026_10_14.py) reads that off the source and the tripwire
sees what the suite replaces; neither shows that a replacement made where the
code looks a name up is seen when the code runs, which is the trap of every
split. So here each name is replaced with a sentinel where the code that reads it
looks it up, the entry points that reach it are called, and the sentinel must
be seen from a frame of the moved code. The names come from the source: what
the accessor reads, and what each module's own functions call. Then the
reload, whose new classes the moved code's class checks must meet, and the name
`wheel`, which is also a well-known package's.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

import export_html
import markup
import test_split_astro_2026_10_14 as split
import wheel
from conftest import EXECUTABLE_DIR, assert_no_exception, make_app

MOVED_FILES = {str(EXECUTABLE_DIR / name) for name in split.TAKEN_LAST}
ACCESSOR_READS = tuple(split._accessor_reads("wheel.py")) + tuple(split._accessor_reads("export_html.py"))


class Seen:
    """Stands in for a name: does what the real value does, and notes each use
    from a frame of the moved code (the engine's own uses of its own name do not
    count). Any use: a call, an attribute, an item, an iteration, an isinstance."""

    def __init__(self, real, name):
        self.__dict__.update(_real=real, _name=name, _sightings=[])

    def _note(self):
        caller = sys._getframe(2).f_code
        if caller.co_filename in MOVED_FILES:
            self._sightings.append((Path(caller.co_filename).name, caller.co_name))

    def __call__(self, *a, **k):
        self._note()
        return self._real(*a, **k)

    def __getattr__(self, attr):
        self._note()
        return getattr(self._real, attr)

    def __getitem__(self, key):
        self._note()
        return self._real[key]

    def __iter__(self):
        self._note()
        return iter(self._real)

    def __contains__(self, item):
        self._note()
        return item in self._real

    def __len__(self):
        self._note()
        return len(self._real)

    def __instancecheck__(self, instance):
        self._note()
        return isinstance(instance, self._real)


@pytest.fixture(scope="module")
def inputs():
    """The example's chart, its timing bundle and the page's own export of it."""
    at = make_app(page="sources").run(timeout=300)
    assert_no_exception(at, "the Sources page")
    import engine as E
    lat, lon = 43.7698, 11.2556
    jd = E.civil_to_jd(1240, 5, 23, 14.5)
    chart = E.calculate_traditional_chart_jd(jd, lat, lon)
    chrono = E.calculate_chronocrats(jd, lat, lon, 14, 0.0)
    bundle = E.pn4_timing_bundle(chart, lat, lon, E.CivilDate(1240, 5, 23), E.CivilDate(1273, 8, 1),
                                 E.PN4_MONTHLY_TURN_OPTIONS[0], chrono)
    assert not bundle.get("refused")
    return {"chart": chart, "chrono": chrono, "bundle": bundle, "analysis": at.session_state["_analysis_export"],
            "local": E.CivilMoment(1240, 5, 23, 14, 30, 0), "lat": lat, "lon": lon}


def every_entry_point(inputs, longitude):
    """Each picture and the report, in the forms that reach all they read."""
    chart, bundle = inputs["chart"], inputs["bundle"]
    asc = chart["ascendant"]
    hits = [{"Target": "Saturn's body", "Arc (years)": 10.5}, {"Target": "Mars's square", "Arc (years)": "33.00"}]
    wheel.generate_hybrid_svg(chart, "A Name", "A Place", inputs["lat"], inputs["lon"], inputs["local"], "LMT", wide=True,
                              chronocrats=inputs["chrono"], bounds=True)
    wheel.generate_hybrid_svg(chart, "A Name", "A Place", inputs["lat"], inputs["lon"], inputs["local"], "LMT", plain=True)
    wheel.generate_multiwheel_svg(
        [{"label": "Nativity", "chart": chart, "when": "then"}, {"label": "Year", "chart": bundle["sr"], "when": "then"}],
        "A Name", wide=True, bounds=True, shade_sign=3, outline_sign=5, profection_from=asc,
        distribution={"start": asc, "end": (asc + 10.0) % 360.0}, marks=[("TP", asc, 0)], badges={0: {"Sun": "D"}},
        extras={0: [("A Lot", 10.0, "Lot")]})
    wheel.generate_distribution_strip_svg(bundle["segments"], bundle["elapsed_years"], "years", 120.0, "A strip")
    wheel.generate_distribution_strip_svg(bundle["small_days"], bundle["day_of_year"], "days", None, "A strip")
    wheel.generate_hit_strip_svg(hits, bundle["elapsed_years"], 120.0, "A strip")
    export_html.analysis_html(inputs["analysis"])
    analysis = inputs["analysis"]
    export_html.export_header_tables({**analysis, "status": {**analysis["status"], "a_key_nobody_worded": 1}})
    export_html._export_cell(longitude)


def test_the_names_the_reach_tests_read_are_there():
    assert "POINT_GLYPHS" in ACCESSOR_READS and "export_zone_caution" in ACCESSOR_READS and "font_face_css" in ACCESSOR_READS


@pytest.mark.parametrize("name", ACCESSOR_READS)
def test_each_name_the_accessor_reads_reaches_the_moved_code(inputs, monkeypatch, name):
    """A replacement of engine.X is what the moved code uses, whichever object
    the engine holds at the call: the accessor does not keep it."""
    import engine as engine_module
    longitude = engine_module.CircleLongitude(123.5)
    seen = Seen(getattr(engine_module, name), name)
    monkeypatch.setattr(engine_module, name, seen)
    every_entry_point(inputs, longitude)
    assert seen._sightings, f"{name} was replaced on the engine and the moved code never used the replacement"


def _called(holder):
    """The functions a module's own code reads by a bare name, each where that
    module looks it up: its own and those it holds by import."""
    reads = split._reads(Path(holder.__file__).name)
    return sorted(n for n in reads if n != "_the_engine" and callable(getattr(holder, n, None))
                  and not isinstance(getattr(holder, n), type) and n in holder.__all__)


def test_the_called_names_hold_what_each_module_is_known_to_call():
    assert {"_esc_text", "_esc_attr", "_isolated", "_svg_text", "_svg_line", "_wheel_palette", "_wheel_dm", "_wheel_sign",
            "_spread_labels", "_stagger_offsets", "_wheel_geometry", "_svg_arrowhead", "_bounds_ring_svg", "_wheel_points",
            "_ring_layout", "_draw_ring_points", "_draw_ring_extras"} <= set(_called(wheel))
    assert {"_esc_text", "_isolated", "_export_cell", "_html_table", "_export_words", "export_header_tables"} \
        <= set(_called(export_html))
    assert "_xml_legal" in _called(markup)


@pytest.mark.parametrize("name", _called(wheel))
def test_each_function_the_wheel_calls_is_read_where_the_wheel_looks_it_up(inputs, monkeypatch, name):
    import engine as E
    longitude = E.CircleLongitude(123.5)
    seen = Seen(getattr(wheel, name), name)
    monkeypatch.setattr(wheel, name, seen)
    every_entry_point(inputs, longitude)
    assert seen._sightings, name


@pytest.mark.parametrize("name", _called(export_html))
def test_each_function_the_report_calls_is_read_where_the_report_looks_it_up(inputs, monkeypatch, name):
    import engine as E
    longitude = E.CircleLongitude(123.5)
    seen = Seen(getattr(export_html, name), name)
    monkeypatch.setattr(export_html, name, seen)
    every_entry_point(inputs, longitude)
    assert seen._sightings, name


def test_the_one_function_markup_calls_is_read_where_markup_looks_it_up(inputs, monkeypatch):
    import engine as E
    longitude = E.CircleLongitude(123.5)
    assert _called(markup) == ["_xml_legal", "page_cell", "page_words"]      # the page's own, called within markup alone
    seen = Seen(markup._xml_legal, "_xml_legal")
    monkeypatch.setattr(markup, "_xml_legal", seen)
    every_entry_point(inputs, longitude)
    assert seen._sightings


def test_the_helpers_are_one_object_in_the_three_modules_and_the_engine():
    """Why a replacement in markup.py alone reaches neither of the others: each
    holds the function itself, from its import."""
    import engine as E
    for name in ("_esc_text", "_isolated"):
        assert getattr(wheel, name) is getattr(export_html, name) is getattr(markup, name) is getattr(E, name)
    assert wheel._esc_attr is markup._esc_attr is E._esc_attr
    assert split._taken_from_markup() == {"_esc_attr": ["wheel.py"], "_esc_text": ["wheel.py", "export_html.py"],
                                          "_isolated": ["wheel.py", "export_html.py"]}


_RELOAD = r"""
import importlib, json
import engine, export_html, wheel
def strip(E):
    return wheel.generate_distribution_strip_svg(
        [{"from": 0.0, "to": 50.0, "distributor": "Mars", "partner": E.PN4Together(["Venus", "Jupiter"]),
          "partner_aspect": E.PN4Together(["trine", "square"])},
         {"from": 50.0, "to": 100.0, "distributor": "Sun", "partner": E.UnresolvedResult("why", "where"),
          "partner_aspect": None}], 10.0, "years", 120.0, "A strip")
def cell(E):
    return export_html._export_cell(E.CircleLongitude(359.99999))
before = (strip(engine), cell(engine))
old = (engine.PN4Together, engine.CircleLongitude, engine.UnresolvedResult)
old_longitude = engine.CircleLongitude(359.99999)
old_together = engine.PN4Together(["Venus", "Jupiter"])
engine = importlib.reload(engine)
out = {"new_classes": [engine.PN4Together is not old[0], engine.CircleLongitude is not old[1],
                       engine.UnresolvedResult is not old[2]],
       "same": [strip(engine) == before[0], cell(engine) == before[1]],
       "reads_degrees": before[1] != str(359.99999) and "." in before[1],
       "isolated_one": wheel._isolated is engine._isolated,
       "old_class_is_not_the_new": [export_html._export_cell(old_longitude) == before[1]]}
print("OUT " + json.dumps(out))
"""


def test_after_a_reload_the_moved_codes_class_checks_hold_on_the_new_classes(tmp_path):
    """A reload of the engine (Streamlit's watcher, the harness's) makes new
    classes, and the moved code reads the engine's at the call: a strip and a
    cell drawn from the new classes are what they were, and a longitude of the
    old class is no longer one."""
    out = split._run(_RELOAD, tmp_path)
    assert out == {"new_classes": [True, True, True], "same": [True, True], "reads_degrees": True, "isolated_one": True,
                   "old_class_is_not_the_new": [False]}, out


_WHEEL_FILE = r"""
import json, sys
import wheel
print("OUT " + json.dumps(wheel.__file__))
"""


def test_the_module_called_wheel_is_this_programs(tmp_path):
    """`wheel` is also a well-known package's name. In a fresh interpreter from
    the program's own folder the name is the program's file, and in this one."""
    assert Path(split._run(_WHEEL_FILE, tmp_path)).resolve() == (EXECUTABLE_DIR / "wheel.py").resolve()
    assert Path(wheel.__file__).resolve() == (EXECUTABLE_DIR / "wheel.py").resolve()


def test_no_requirement_of_the_program_is_the_package_called_wheel():
    """A build that installed it could find it first in some order of the path."""
    named = []
    for path in sorted(EXECUTABLE_DIR.glob("requirements*")):
        for line in path.read_text(encoding="utf-8").splitlines():
            name = line.split("#", 1)[0].strip().split("==")[0].split(">=")[0].split("[")[0].strip().lower()
            if name == "wheel":
                named.append(path.name)
    assert not named, named


def test_the_markup_module_holds_no_engine_name_and_reads_only_the_standard_library():
    tree = ast.parse((EXECUTABLE_DIR / "markup.py").read_text(encoding="utf-8"))
    assert split._reads("markup.py") - set(split._bound(tree)) == set()
    assert not [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_the_engine"]
