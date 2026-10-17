"""What a page shows must not depend on the interpreter's hash seed.

Python seeds its string hashing afresh at every start (PYTHONHASHSEED), and a
set of planet names is walked in an order that follows it. Three places
walked such a set on the way to a page, so one chart could read differently
after the app was restarted:

* Enclosure's dissolver (Gr. Intr. VII.6, 60-61, ``_abu_mashar_enclosed``):
  with more than one of the Sun, Venus and Jupiter looking, the one named in
  "Enclosure by the infortunes dissolved by ..." was the first the set
  yielded. 60 and 61 do not rank them ("the Sun or one of the fortunes", "the
  fortunes or Sun"), so they are now tried in the order the tables list the
  planets: the Sun, then Venus, then Jupiter.
* Transfer of Light's rows (``evaluate_transfers_of_light``) and, through
  them, Reflection of Light's.
* III.8, 7's facts on the lord of the year and the distributor
  (``pn4_bound_transits``): "a fortune with it: Venus, Jupiter" when both
  stand in the sign.

Each is walked through ``in_planet_order`` now. The first test renders the
Configurations page and builds the export for three charts in two fresh
interpreters under different seeds and compares everything shown.

The fourth item is the Planetary Condition table's column types. With
Mercury exactly on the Sun his sect is unassigned (``mercury_phase_sect``),
his domain and contrary-domain testimonies are open, and the engine's Good
Fortune, Weakness and Net for him are UnresolvedResults: a column mixing them
with the other rows' numbers is one Arrow cannot type, and Streamlit fell back
to stringifying it. As the Sahl grids' Count does, the three columns now hold
the resolved subtotal in every row and a new Unresolved column says how many
testimonies are open; the row's details keep the possible totals.
"""
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from conftest import assert_no_exception, make_app, table_nodes

TESTS_DIR = Path(__file__).resolve().parent
SEEDS = ("1", "2")
# Charts on which the seed changed the page before the fix: the dissolver
# and Transfer of Light on the default chart, Transfer and Reflection of
# Light on the other two.
SEED_CHARTS = ("1240-05-23", "1240-05-26", "1240-10-05")

_CHILD = r"""
import json, os, sys
sys.path.insert(0, os.getcwd())
from conftest import make_app

def walk(node, out):
    kind = getattr(node, "type", None)
    if kind == "dataframe":
        frame = node.value
        out.append([kind, list(map(str, frame.columns)), frame.astype(str).values.tolist()])
    elif kind in ("markdown", "caption", "subheader", "header", "text", "table"):
        out.append([kind, str(node.value)])
    elif kind in ("expander", "status", "selectbox", "radio", "checkbox"):
        out.append([kind, str(getattr(node, "label", ""))])
    for child in getattr(node, "children", {}).values():
        walk(child, out)

shown = {}
for date in json.loads(sys.argv[1]):
    at = make_app(date=date, page="configurations")
    at.session_state["_target_date"] = "2026-09-17"
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.run(timeout=300)
    if len(at.exception):
        raise SystemExit("\n".join(e.value for e in at.exception))
    page = []
    walk(at.main, page)
    export = {k: v for k, v in at.session_state["_analysis_export"].items() if k != "exported"}
    shown[date] = {"page": page, "export": json.loads(json.dumps(export, default=str))}
print(json.dumps(shown, sort_keys=True))
"""


def _run_under_seeds(code, *args, seeds=SEEDS):
    """stdout of `code` run once per seed, each in its own interpreter."""
    procs = {}
    for seed in seeds:
        env = dict(os.environ, PYTHONHASHSEED=seed)
        procs[seed] = subprocess.Popen([sys.executable, "-c", code, *args], cwd=TESTS_DIR, env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    outputs = {}
    for seed, proc in procs.items():
        out, err = proc.communicate(timeout=600)
        assert proc.returncode == 0, f"PYTHONHASHSEED={seed}:\n{err[-3000:]}"
        outputs[seed] = out
    return outputs


def _first_difference(a, b, path=""):
    if type(a) is not type(b):
        return f"{path}: {a!r} != {b!r}"
    if isinstance(a, dict):
        for key in sorted(set(a) | set(b)):
            if a.get(key) != b.get(key):
                return _first_difference(a.get(key), b.get(key), f"{path}/{key}")
    elif isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: {len(a)} items != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                return _first_difference(x, y, f"{path}[{i}]")
    elif a != b:
        return f"{path}: {str(a)[:300]!r} != {str(b)[:300]!r}"
    return None


def test_the_configurations_page_and_the_export_read_the_same_under_any_hash_seed():
    outputs = _run_under_seeds(_CHILD, json.dumps(SEED_CHARTS))
    shown = {seed: json.loads(out) for seed, out in outputs.items()}
    first, second = (shown[seed] for seed in SEEDS)
    assert set(first) == set(SEED_CHARTS)
    for date in SEED_CHARTS:
        assert first[date]["page"], f"{date}: nothing rendered"
        difference = _first_difference(first[date], second[date])
        assert difference is None, (
            f"{date}: PYTHONHASHSEED {SEEDS[0]} and {SEEDS[1]} disagree at {difference}")


# --- The dissolver's order, stated -----------------------------------------

def test_the_dissolver_is_tried_sun_venus_jupiter(engine):
    """60-61 do not rank the dissolvers, so the table order decides."""
    assert engine["in_planet_order"]({"Jupiter", "Venus", "Sun"}) == ["Sun", "Venus", "Jupiter"]
    assert engine["in_planet_order"]({"Lot of Fortune", "Saturn", "Moon", "North Node"}) == [
        "Moon", "Saturn", "North Node", "Lot of Fortune"]


# --- The sweep's other sites, each under several seeds ---------------------

_SWEEP_CHILD = r"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.getcwd()))
os.environ.setdefault("ALMUTEN_NO_PREFERENCES", "1")
os.environ.setdefault("XDG_DATA_HOME", os.path.join(os.getcwd(), ".xdg-scratch"))
import engine as E

out = {}
# _fact of a set of planet names (the generic branch printed the set's own order).
out["fact"] = E._fact("Planets", {"Jupiter", "Venus", "Saturn", "Mars", "Sun"})
# III.8, 7's facts, with Venus and Jupiter both in the lord of the year's sign.
rev = {name: {"longitude": lon, "latitude": 0.0, "distance": 1.0, "speed_in_lon": 0.5}
       for name, lon in (("Sun", 200.0), ("Moon", 100.0), ("Mercury", 210.0), ("Venus", 12.0),
                         ("Mars", 250.0), ("Jupiter", 15.0), ("Saturn", 10.0))}
current = {"from_lon": 280.0, "distributor": "Mars", "partner": None}
rows = E.pn4_bound_transits({}, {"planetary_data": rev}, current, "Saturn")
out["III.8"] = [row["Sentence"] for row in rows]
print(json.dumps(out, sort_keys=True))
"""


def test_the_swept_sites_read_the_same_under_any_hash_seed():
    outputs = _run_under_seeds(_SWEEP_CHILD, seeds=("1", "2", "3", "4", "5", "6"))
    shown = {seed: json.loads(out) for seed, out in outputs.items()}
    first = shown["1"]
    assert "Sun, Venus, Mars, Jupiter, Saturn" in first["fact"], first["fact"]
    assert any("a fortune with it: Venus, Jupiter" in sentence for sentence in first["III.8"]), first["III.8"]
    for seed, value in shown.items():
        assert value == first, f"PYTHONHASHSEED {seed} disagrees with 1: {value} != {first}"


# --- 4. The Planetary Condition table's column types ------------------------

_ARROW_FALLBACK = "Serialization of dataframe to Arrow table was unsuccessful"
TYPED_COLUMNS = ("Good Fortune", "Strength", "Weakness", "Misfortune", "Net")


def _mercury_on_the_sun(monkeypatch, at):
    """The chart with Mercury moved onto the Sun's longitude exactly, the
    only case in which his sect is unassigned. Patched after make_app,
    which reloads the engine."""
    import engine
    original = engine.calculate_traditional_chart_jd

    def patched(*args, **kwargs):
        chart = original(*args, **kwargs)
        chart['planetary_data']['Mercury']['longitude'] = chart['planetary_data']['Sun']['longitude']
        return chart
    monkeypatch.setattr(engine, 'calculate_traditional_chart_jd', patched)
    return engine


@pytest.fixture
def conjunction_page(monkeypatch, caplog):
    """The Configurations page for the default chart with Mercury on the
    Sun, with every Arrow fallback Streamlit logged while drawing it."""
    at = make_app(date="1240-05-23", page="configurations")
    at.session_state["_reading_depth"] = "Course text and supplement"
    engine = _mercury_on_the_sun(monkeypatch, at)
    with caplog.at_level(logging.INFO, logger="streamlit.dataframe_util"):
        at.run(timeout=300)
    return at, engine, list(caplog.records)


def test_the_conjunction_really_leaves_mercury_open(conjunction_page):
    at, engine, _records = conjunction_page
    assert_no_exception(at, "configurations with Mercury on the Sun")
    rows = at.session_state["_analysis_export"]["results"]["Configurations"]["Planetary Condition"][0]["rows"]
    mercury = next(row for row in rows if row["Planet"] == "Mercury")
    assert mercury["Unresolved"] == 2, mercury    # his domain and contrary-domain testimonies


def test_no_arrow_fallback_on_the_planetary_condition_table(conjunction_page):
    _at, _engine, records = conjunction_page
    failed = [str(record.exc_info[1]) for record in records
              if _ARROW_FALLBACK in record.getMessage() and record.exc_info]
    ours = [text for text in failed if any(f"column {name} " in text for name in TYPED_COLUMNS + ("Unresolved",))]
    assert not ours, ours


def test_the_planetary_condition_columns_are_numeric_on_the_page(conjunction_page):
    at, _engine, _records = conjunction_page
    frame = next(node for heading, node in table_nodes(at) if heading == "Planetary Condition").value
    for name in TYPED_COLUMNS:
        assert pd.api.types.is_integer_dtype(frame[name]), (name, frame[name].dtype, frame[name].tolist())
    assert str(frame["Unresolved"].dtype) == "float64", frame["Unresolved"].dtype
    mercury = frame[frame["Planet"] == "Mercury"].iloc[0]
    assert mercury["Unresolved"] == 2
    assert frame[frame["Planet"] != "Mercury"]["Unresolved"].isna().all()
    # Unranked: after every row whose Net is resolved.
    assert frame["Planet"].iloc[-1] == "Mercury", frame["Planet"].tolist()


def test_the_planetary_condition_columns_are_one_type_in_the_export(conjunction_page):
    at, _engine, _records = conjunction_page
    rows = at.session_state["_analysis_export"]["results"]["Configurations"]["Planetary Condition"][0]["rows"]
    for name in TYPED_COLUMNS:
        kinds = {type(row[name]).__name__ for row in rows}
        assert kinds == {"int"}, (name, kinds)
    assert {type(row["Unresolved"]).__name__ for row in rows} == {"int", "NoneType"}
    pa.Table.from_pandas(pd.DataFrame(rows))    # raises on a column it cannot type


def test_the_resolved_subtotals_and_the_possible_totals_agree(conjunction_page):
    """The cells are the engine's own known subtotals, and the details line
    still prints the engine's unresolved totals, alternatives and all."""
    at, engine, _records = conjunction_page
    rows = at.session_state["_analysis_export"]["results"]["Configurations"]["Planetary Condition"][0]["rows"]
    mercury = next(row for row in rows if row["Planet"] == "Mercury")
    box = [node for node in at.main.selectbox if node.key == 'planetary_condition_detail'][0]
    box.select("Mercury")
    at.run(timeout=300)
    assert_no_exception(at, "the Planetary Condition detail for Mercury")
    line = next(node.value for node in at.main.markdown if node.value.startswith('**Mercury.**'))
    assert f"known subtotal {mercury['Net']};" in line, line
    assert f"known subtotal {mercury['Good Fortune']};" in line, line
    assert f"known subtotal {mercury['Weakness']};" in line, line
    assert "if Mercury is diurnal" in line and "if Mercury is nocturnal" in line, line


def test_known_counts_equal_the_counts_whenever_they_are_resolved(engine):
    """On an ordinary chart the new fields are the columns' old values."""
    chart = engine["calculate_traditional_chart_jd"](2174209.0, 43.7792, 11.2463)
    p, sect = chart["planetary_data"], chart["sect"]
    essential = engine["evaluate_essential_dignities"](p, sect)
    accidental = engine["evaluate_accidental_dignities"](p, chart["houses"], sect, chart["julian_day"],
                                                         armc=chart["armc"], obliquity=chart["obliquity"],
                                                         geo_lat=43.7792)
    condition = engine["evaluate_abu_mashar_condition"](p, chart["houses"], sect, essential, accidental,
                                                        chart["julian_day"], chart["ascendant"])
    for planet, row in condition.items():
        assert row["Known Good Fortune"] == row["Good Fortune"], planet
        assert row["Known Weakness"] == row["Weakness"], planet
        assert row["Known Net"] == row["Net"], planet
        assert row["Unresolved Count"] == 0, planet
