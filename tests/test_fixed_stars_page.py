"""The Fixed stars page: every star of the catalogue, and the two measures at each axis.

The places and the crossing times are pinned against an independent reproduction
(tests/fixtures/fixed_stars_reference.json; its note says what it was computed from). That
reproduction reads another star catalogue than the one this app ships, so its rows are not this
app's to a hundredth of an arcsecond: each pin below states the bound, by era, that was measured
for Swiss Ephemeris on the shipped catalogue, with the room left above the measurement. Swiss
Ephemeris's default precession is Vondrák et al. 2011, so the places are pinned against that
model's rows, whose ecliptic takes that model's own mean obliquity.

The crossing references are geocentric, without diurnal aberration, as the page computes; a
topocentric culmination would sit up to 0.032 s from them. Pins of either list stay away from its
edge unless the edge is what they test: Spica in the example chart sits 0.98 to 0.99 degrees from
an axis, where the catalogue gap could decide it.
"""
from __future__ import annotations

import dataclasses
import hashlib
import html
import json
import math
import os
import random
import itertools
import re
import statistics
import subprocess
import sys
import textwrap
import types
from pathlib import Path

import pandas as pd
import pytest
import swisseph as raw_swe

from conftest import EXECUTABLE_DIR, FLORENCE, assert_no_exception, make_app, sync_engine_to_environment

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "fixed_stars_reference.json").read_text(encoding="utf-8"))
PLACES = FIXTURE["places"]
EVENTS = FIXTURE["events"]
EVENT_AXIS = {"rise": "Ascendant", "culm": "MC", "set": "Descendant", "anti": "IC"}
AXES = ("Ascendant", "MC", "Descendant", "IC")
NOT_LISTED = ("Test", "AA11_page_B73", "Ensis")
NO_MAGNITUDE = 18
THE_WORD = re.compile(r"\bangles?\b", re.IGNORECASE)
NO_CHART_SENTENCE = "Correct the nativity in the sidebar; the reference tables and the sources stay available."
MINUS = "−"
CROSSING = "Crossing (min:s)"
OFFSET = "Longitude offset (°)"

# Measured: the largest residual in any coordinate, in arcseconds, with the room above it. Most of
# the 28 agree closely; these five carry a larger gap between the two catalogues.
PLACE_BOUND = {500: 0.1, 1000: 0.05, 1500: 0.05, 1800: 0.05, 2000: 0.05, 2026: 0.05, 2200: 0.05}
PLACE_BOUND_STAR = {
    "Procyon": {500: 0.6, 1000: 0.3, 1500: 0.1, 1800: 0.05, 2000: 0.05, 2026: 0.05, 2200: 0.05},
    "Sirius": {500: 0.2, 1000: 0.1, 1500: 0.05, 1800: 0.05, 2000: 0.05, 2026: 0.05, 2200: 0.05},
    "Altair": {500: 0.2, 1000: 0.1, 1500: 0.05, 1800: 0.05, 2000: 0.05, 2026: 0.05, 2200: 0.05},
    "Acamar": {500: 20.0, 1000: 13.0, 1500: 6.0, 1800: 2.0, 2000: 1.0, 2026: 1.2, 2200: 3.5},
    "Toliman": {500: 350.0, 1000: 240.0, 1500: 125.0, 1800: 55.0, 2000: 7.0, 2026: 0.6, 2200: 42.0},
}
# Measured: the largest error in a crossing time, in seconds, offset included, with the room above it.
TIME_BOUND = {1000: 0.02, 1600: 0.01, 2000: 0.01, 2026: 0.01, 2200: 0.01}
TIME_BOUND_TOLIMAN = {1000: 11.5, 1600: 5.0, 2000: 0.4, 2026: 0.05, 2200: 2.0}


def wrapped(a, b):
    return (a - b + 180.0) % 360.0 - 180.0


def star_named(stars, catalogue_name):
    found = [s for s in stars if s.catalogue_name == catalogue_name]
    assert len(found) == 1, catalogue_name
    return found[0]


def frame_at(engine, jd, lat, lon):
    """A chart's frame as chart_houses gives it, for the many moments below where a whole chart
    is not needed (test_the_axes_and_the_armc_are_the_charts holds the two together)."""
    ascmc = engine["chart_houses"](jd, lat, lon)[1]
    return {"axes": {"Ascendant": ascmc[0], "MC": ascmc[1], "Descendant": (ascmc[0] + 180.0) % 360.0,
                     "IC": (ascmc[1] + 180.0) % 360.0}, "armc": ascmc[2], "latitude": lat}


def on_reader(engine, fn):
    return engine["_on_fixed_star_reader"](fn)


def fixed_stars_app(**kwargs):
    """make_app reloads the engine if the environment has moved since it last looked, which would
    drop a patch of the engine's names. A test that patches calls sync_engine_to_environment first."""
    return make_app(page="fixed-stars", **kwargs)


def walk(node):
    """Every rendered element under a node, containers included."""
    yield node
    for child in getattr(node, "children", {}).values():
        yield from walk(child)


def printed(at):
    """Every string the page's own area prints: each element's proto as text, its help included,
    and each table's heads and cells."""
    texts = []
    for node in walk(at.main):
        if getattr(node, "type", None) == "dataframe":
            table = node.value
            texts += [str(c) for c in table.columns] + [str(v) for v in table.to_numpy().ravel()]
            texts.append(str(getattr(node.proto, "columns", "")))
        elif getattr(node, "proto", None) is not None:
            texts.append(str(node.proto))
        for attribute in ("label", "value", "help"):
            value = getattr(node, attribute, None)
            if isinstance(value, str):
                texts.append(value)
    return texts


def assert_the_word_is_absent(at):
    texts = printed(at)
    assert texts, "the premise: the page printed something"
    assert not [t[:200] for t in texts if THE_WORD.search(t)]


def tab_named(at, label):
    return next(t for t in at.main.tabs if t.label == label)


_ROW_VALUE = re.compile(r'<div class="zij-row-label">([^<]*)</div>(<strong class="zij-admits">)?([^<]*)')
_ROW_SECOND = re.compile(r'<div class="zij-row-second">([^<]*)</div>')


def opener_rows(node, prefix):
    """The compact rows under a node whose buttons' keys start with `prefix`, as they are drawn, in
    order: the key, the button's label read back from Markdown, the line under it, each labelled value,
    and which of the values the row is bold and in brass for."""
    rows = []
    for element in walk(node):
        kind = getattr(element, "type", None)
        if kind == "button" and (element.key or "").startswith(prefix):
            rows.append({"key": element.key, "name": re.sub(r"\\\\(.)", r"\\1", element.label), "second": None, "values": {}, "admits": []})
        elif kind == "html" and rows:
            second = _ROW_SECOND.search(element.proto.body)
            if second:
                rows[-1]["second"] = second[1]
            for label, admits, value in _ROW_VALUE.findall(element.proto.body):
                if label in rows[-1]["values"]:
                    continue
                rows[-1]["values"][label] = value
                if admits:
                    rows[-1]["admits"].append(label)
    return rows


def axis_lists(at):
    """The eight lists as the page draws them, by (axis, 'crossing' or 'longitude')."""
    lists = {(axis, kind): [] for axis in AXES for kind in ("crossing", "longitude")}
    for row in opener_rows(tab_named(at, "Axes"), "zij-open-"):
        _zij, _open, axis, kind, row["identity"] = row["key"].split("-", 4)
        lists[axis, kind].append(row)
    return lists


def sahl_rows(at):
    """The Star list's rows under Sahl's 28, with each row's own nature."""
    rows = opener_rows(tab_named(at, "Star list"), "zij-open-sahl-")
    natures = [node.proto.body for node in walk(tab_named(at, "Star list")) if getattr(node, "type", None) == "html"
               and node.proto.body.startswith("<p>")]
    assert len(natures) == len(rows)
    return [{**row, "nature": html.unescape(nature[3:-4])} for row, nature in zip(rows, natures)]


def choose_population(at, name):
    """The page's one control, as a reader moves it."""
    at.main.button_group[0].set_value(name).run(timeout=120)
    return at


def assert_is_the_page(at, context):
    """The page's own body, so a pin of an absence cannot pass on a page that stopped early."""
    assert_no_exception(at, context)
    assert [h.value for h in at.main.header] == ["Fixed stars"], context
    assert [t.label for t in at.main.tabs] == ["Axes", "Star list", "Stars harming eyes"], context


# --- The catalogue ---------------------------------------------------------------------------

def test_the_file_order_number_reaches_every_row_and_the_sorted_one_does_not(engine):
    def counts():
        assert engine["_fixed_star_catalogue_search"]()
        rows = len(engine["_fixed_star_rows_read"]())
        with pytest.raises(engine["swe"].Error):
            engine["swe"].fixstar_ut(str(rows + 1), 2451545.0, raw_swe.FLG_MOSEPH)
        engine["swe"].fixstar2_ut("1888", 2451545.0, raw_swe.FLG_MOSEPH)
        with pytest.raises(engine["swe"].Error):
            engine["swe"].fixstar2_ut("1889", 2451545.0, raw_swe.FLG_MOSEPH)
        return rows
    assert on_reader(engine, counts) == 2107


def _listed_groups(engine):
    """The groups of rows the catalogue lists as stars: every one but those it lists nowhere."""
    def rows_and_groups():
        assert engine["_fixed_star_catalogue_search"]()
        groups = engine["_fixed_star_groups"](engine["_fixed_star_rows_read"]())
        return [group for group in groups if engine["_fixed_star_entry"](group).catalogue_name not in NOT_LISTED
                and not any(engine["_fixed_star_is_old_row"](row) for row in group)]
    return on_reader(engine, rows_and_groups)


def test_each_stars_place_is_its_file_rows_place_at_every_era(engine):
    """A place read through swe.fixstar2_ut's key, by name or designation, is the one
    swe.fixstar_ut's file-order number gives its row: the same star by either call."""
    groups = _listed_groups(engine)
    assert len(groups) == 1852

    def first_rows():
        out = []
        for group in groups:
            entry = engine["_fixed_star_entry"](group)
            out.append(next(row[0] for row in group if (row[1] or row[2]) == entry.catalogue_name
                            and row[2] == entry.designation))
        return out
    numbers = on_reader(engine, first_rows)
    for jd in (1903855.0, 2461000.5, 2816787.5):
        stars, missing = engine["fixed_star_places"](jd)
        assert missing == {} and len(stars) == 1852    # the stars stand in the groups' order

        def legacy(jd=jd):
            return [(engine["swe"].fixstar_ut(str(n), jd, raw_swe.FLG_MOSEPH)[0],
                     engine["swe"].fixstar_ut(str(n), jd, raw_swe.FLG_MOSEPH | raw_swe.FLG_EQUATORIAL)[0])
                    for n in numbers]
        rows = on_reader(engine, legacy)
        assert len(rows) == 1852
        for star, (ecliptic, equatorial) in zip(stars, rows):
            assert abs(wrapped(star.longitude, ecliptic[0])) < 1e-9, star.name
            assert abs(star.latitude - ecliptic[1]) < 1e-9, star.name
            assert abs(wrapped(star.right_ascension, equatorial[0])) < 1e-9, star.name
            assert abs(star.declination - equatorial[1]) < 1e-9, star.name


def test_rows_that_are_one_star_are_one_row_with_their_other_names(engine):
    stars, _ = engine["fixed_star_places"](2451545.0)
    by_name = {}
    for star in stars:
        by_name.setdefault(star.name, []).append(star)
    # One name, one star, each other name beside it; capitals alone are no other name.
    assert by_name["Sirius"][0].designation == "alCMa" and len(by_name["Sirius"]) == 1
    assert by_name["Toliman"][0].other_names == ("Rigil Kentaurus", "Rigel Kentaurus", "Bungula", "Proxima Centauri")
    assert by_name["Mizar"][0].other_names == ("Miz0", "Vasishtha")
    assert by_name["Alcor"][0].other_names == ("Alc0", "Arundhati", "Saidak")
    # A second designation at the one place stands among the other names too.
    assert by_name["Dabih"][0].other_names == ("be-1Cap",) and by_name["Dabih"][0].designation == "beCap"
    # Two stars under one name stay two, each with its designation.
    assert sorted(s.designation for s in stars if s.catalogue_name == "Menkar") == ["alCet", "laCet"]
    assert [s.designation for s in by_name["Menkar"]] == ["alCet"], "the other reads by its designation"
    # The one designation with two places: its old row is left out.
    assert [s.designation for s in by_name["Virgo Cluster"]] == ["VC"]
    # No two stars stand within the bound, and no designation stands twice.
    designations = [s.designation for s in stars]
    assert sorted({d for d in designations if designations.count(d) > 1}) == []
    units = sorted((engine["_fixed_star_unit"](s.longitude, s.latitude) for s in stars), key=lambda u: u[2])
    closest = min(math.dist(a, b) for a, b in zip(units, units[1:]))
    assert math.degrees(closest) * 3600.0 > engine["FIXED_STAR_SAME_STAR_ARCSEC"]


def test_a_star_with_no_name_shows_its_designation_and_nonstellar_entries_stay(engine):
    stars, _ = engine["fixed_star_places"](2451545.0)
    nameless = [s for s in stars if s.name == s.designation]
    assert "deAnd" in [s.name for s in nameless] and len(nameless) > 400
    named = {s.name: s for s in stars}
    assert "Galactic Center" in named and named["Galactic Center"].designation == "SgrA*"
    assert named["Galactic Center"].magnitude is None and named["Sirius"].magnitude == -1.46
    assert named["Great Attractor"].magnitude is None and named["Gal.Pole"].magnitude is None


def test_sahls_28_carry_this_engines_names_and_natures(engine):
    stars, _ = engine["fixed_star_places"](2451545.0)
    sahl = {s.catalogue_name: s for s in stars if s.nature is not None}
    assert {k: s.nature for k, s in sahl.items()} == dict(engine["SAHL_FIXED_STARS"])
    assert sahl["Zuben Eschamali"].name == "Zuben Eschemali"
    # The book's spelling is the name; the catalogue's same name is no other name beside it.
    assert "Zuben Eschamali" not in sahl["Zuben Eschamali"].other_names
    assert len(sahl) == 28
    assert all(s.name == engine["FIXED_STAR_PAGE_NAME"].get(k, k) for k, s in sahl.items())


def test_sahls_places_are_the_readings_own(engine):
    for jd in (1903855.0, 2451545.0, 2816787.5):
        longitudes, _ = engine["_fixed_star_reading"](jd)
        stars, _ = engine["fixed_star_places"](jd)
        assert {s.catalogue_name: s.longitude for s in stars if s.nature is not None} == longitudes


def test_the_catalogue_is_read_once_per_moment(engine, monkeypatch):
    calls = []
    real = engine["_fixed_star_places_read"]
    monkeypatch.setitem(engine, "_fixed_star_places_read", lambda jd: (calls.append(jd), real(jd))[1])
    engine["_fixed_star_places_at"].cache_clear()
    first = engine["fixed_star_places"](2460000.25)
    second = engine["fixed_star_places"](2460000.25)
    assert calls == [2460000.25] and first[0] is second[0]
    engine["fixed_star_places"](2460000.5)
    assert calls == [2460000.25, 2460000.5]
    engine["_fixed_star_places_at"].cache_clear()


def test_a_star_the_catalogue_cannot_place_is_named_by_the_engines_sentence(engine, monkeypatch):
    real = engine["swe"].fixstar2_ut

    def refusing(key, *args):
        if key == "Zuben Eschamali":
            raise engine["swe"].Error("refused")
        return real(key, *args)
    monkeypatch.setattr(engine["swe"], "fixstar2_ut", refusing)
    engine["_fixed_star_places_at"].cache_clear()
    stars, missing = engine["fixed_star_places"](2460000.75)
    engine["_fixed_star_places_at"].cache_clear()
    assert set(missing) == {"Zuben Eschamali"} and len(stars) == 1851
    assert engine["fixed_star_missing_note"](missing) == "Not in the catalogue attached, so not placed: Zuben Eschemali."


def test_without_a_catalogue_nothing_is_kept_and_nothing_is_placed(engine, monkeypatch):
    engine["_fixed_star_places_at"].cache_clear()
    monkeypatch.setitem(engine, "_fixed_star_catalogue_search", lambda: False)
    assert engine["fixed_star_places"](2460001.25) == (None, {})
    monkeypatch.undo()
    stars, _ = engine["fixed_star_places"](2460001.25)
    assert stars is not None and len(stars) == 1852
    engine["_fixed_star_places_at"].cache_clear()


def _groups_with_their_stars(engine):
    """Each group of rows the catalogue holds as one star, its own row's number, and the star as
    the page holds it."""
    groups = _listed_groups(engine)
    stars, _ = engine["fixed_star_places"](2451545.0)
    assert len(stars) == len(groups) == 1852
    out = []
    for group, star in zip(groups, stars):       # the catalogue's stars stand in the order of their groups
        own = [row[0] for row in group if (row[1] or row[2], row[2]) == (star.catalogue_name, star.designation)]
        assert own, group
        out.append((group, own[0], star))
    return out


def test_every_stars_magnitude_is_its_own_rows_read_by_file_number(engine):
    """Read by number: the library's read by name matches on a prefix, so "Ruc" answers Ruchbah's,
    and a star's aliases do not always carry its own magnitude."""
    held = _groups_with_their_stars(engine)
    direct = on_reader(engine, lambda: {number: raw_swe.fixstar_mag(str(number))[0] for _g, number, _s in held})
    assert len(direct) == len(held)
    assert len(held) == 1852
    for _group, number, star in held:
        expected = None if direct[number] in (0.0, 999.99) else direct[number]
        assert star.magnitude == expected, (star.name, number)
    assert sum(star.magnitude is None for _g, _n, star in held) == NO_MAGNITUDE
    assert star_named([s for _g, _n, s in held], "Ruc").magnitude != star_named([s for _g, _n, s in held], "Ruchbah").magnitude


def test_every_name_of_a_stars_rows_stands_on_that_star(engine):
    held = _groups_with_their_stars(engine)
    assert len(held) == 1852
    added = {name.casefold() for names in (engine["FIXED_STAR_OTHER_NAMES"], engine["FIXED_STAR_ALSO_NAMED"], engine["FIXED_STAR_PAGE_NAME"]) for name in names.values()}
    added |= {name.casefold() for name in engine["FIXED_STAR_SHOWN_NAME"].values() if name}
    for group, _number, star in held:
        shown = {star.name.casefold(), star.catalogue_name.casefold(), star.designation.casefold(), *(n.casefold() for n in star.other_names)}
        its_rows = {text.casefold() for row in group for text in row[1:3] if text}
        assert shown - (added - its_rows) == its_rows, star.name
    stars = [s for _g, _n, s in held]
    assert star_named(stars, "Mizar").other_names == ("Miz0", "Vasishtha")
    assert star_named(stars, "Toliman").other_names == ("Rigil Kentaurus", "Rigel Kentaurus", "Bungula", "Proxima Centauri")


# --- The whole catalogue, proved at the attach --------------------------------------------------

# The checked copy changed as it would be between its readback and the library's open, in a fresh
# interpreter whose temporary folder is the test's own. Each change leaves Sahl's stars as recorded,
# but for the one named in NOT_THE_ROWS, which Sahl's own comparison refuses first.
PROOF = textwrap.dedent('''
    import json, sys
    from pathlib import Path
    sys.path.insert(0, ROOT)
    import engine

    def line_of(lines, label):
        name, designation = label.split(',')
        found = [i for i, line in enumerate(lines)
                 if [cell.strip() for cell in line.split(',')[:2]] == [name, designation]]
        return found[0]

    def magnitude_set(lines, label, value):
        at = line_of(lines, label)
        cells = lines[at].split(',')
        cells[13] = value
        lines[at] = ','.join(cells)

    def seconds_of_declination_moved(lines, label, arcseconds):
        at = line_of(lines, label)
        cells = lines[at].split(',')
        cells[8] = '%.4f' % (float(cells[8]) + arcseconds)
        lines[at] = ','.join(cells)

    CHANGE

    real = engine._fixed_star_catalogue_install

    def changed_after_the_check(source):
        checked = real(source)
        path = Path(engine._ephemeris_folder_here()) / 'sefstars.txt'
        lines = path.read_bytes().decode('latin-1').split('\\n')
        change(lines)
        path.write_bytes('\\n'.join(lines).encode('latin-1'))
        return checked

    engine._fixed_star_catalogue_install = changed_after_the_check
    stars, missing = engine.fixed_star_places(2451545.0)
    print(json.dumps({'stars': None if stars is None else len(stars), 'why': engine._FIXED_STAR_STATE['why'],
                      'ready': engine._FIXED_STAR_STATE['ready']}))
''')
ROWS_CHANGED = "its rows are not the shipped file's"
MAGNITUDES_CHANGED = "its magnitudes are not the shipped file's"
# 5 arcseconds at the catalogue's epoch, with the proper motion that brings it back by the first date.
ONLY_LATER = "a row moved everywhere but at the first date"
NOT_THE_ROWS = {
    "a cell of Vega not a number": "places Vega otherwise than the shipped file does",
    "a magnitude changed": MAGNITUDES_CHANGED,
    "a magnitude one step off": MAGNITUDES_CHANGED,
    "a magnitude not a number": MAGNITUDES_CHANGED,
    "a magnitude in words": MAGNITUDES_CHANGED,
    "a magnitude sentinel changed": MAGNITUDES_CHANGED,
}
CHANGES = {
    "two rows three hours off": """
def change(lines):
    for label in ('Arcturus,alBoo', 'Deneb Adige,alCyg'):
        at = line_of(lines, label)
        cells = lines[at].split(',')
        cells[3] = '%02d' % ((int(cells[3]) + 3) % 24)
        lines[at] = ','.join(cells)
""",
    "two rows three hours off, with one cell of the last row not a number": """
def change(lines):
    for label in ('Arcturus,alBoo', 'Deneb Adige,alCyg'):
        at = line_of(lines, label)
        cells = lines[at].split(',')
        cells[3] = '%02d' % ((int(cells[3]) + 3) % 24)
        lines[at] = ','.join(cells)
    at = line_of(lines, 'Gliese 710,HD168442')
    cells = lines[at].split(',')
    cells[8] = 'nan'
    lines[at] = ','.join(cells)
""",
    "a cell of Vega not a number": """
def change(lines):
    at = line_of(lines, 'Vega,alLyr')
    cells = lines[at].split(',')
    cells[8] = 'nan'
    lines[at] = ','.join(cells)
""",
    "the first row not of Sahl's moved 1.2 arcseconds": """
def change(lines):
    seconds_of_declination_moved(lines, 'Rohini,alTau', 1.2)
""",
    "the last row moved 1.2 arcseconds": """
def change(lines):
    seconds_of_declination_moved(lines, 'Gliese 710,HD168442', 1.2)
""",
    "a proper motion that acts only away from the epoch": """
def change(lines):
    at = line_of(lines, 'Arcturus,alBoo')
    cells = lines[at].split(',')
    cells[9] = '%.2f' % (float(cells[9]) * 100.0)
    lines[at] = ','.join(cells)
""",
    ONLY_LATER: """
def change(lines):
    at = line_of(lines, 'Rohini,alTau')
    cells = lines[at].split(',')
    cells[8] = '%.4f' % (float(cells[8]) + 5.0)
    cells[10] = '%.4f' % (float(cells[10]) + 0.986)
    lines[at] = ','.join(cells)
""",
    "two neighbouring rows exchanged whole": """
def change(lines):
    a, b = line_of(lines, 'Acrab,be-1Sco'), line_of(lines, ',be-2Sco')
    lines[a], lines[b] = lines[b], lines[a]
""",
    "two neighbouring rows exchanging their places under their own labels": """
def change(lines):
    a, b = line_of(lines, 'Acrab,be-1Sco'), line_of(lines, ',be-2Sco')
    one, other = lines[a].split(','), lines[b].split(',')
    lines[a], lines[b] = ','.join(one[:2] + other[2:]), ','.join(other[:2] + one[2:])
""",
    "two rows of one label and two places exchanged": """
def change(lines):
    a, b = [i for i, line in enumerate(lines) if line.startswith('Virgo Cluster')]
    lines[a], lines[b] = lines[b], lines[a]
""",
    "two names of one star at one place exchanged": """
def change(lines):
    a, b = line_of(lines, 'Aldebaran,alTau'), line_of(lines, 'Rohini,alTau')
    lines[a], lines[b] = lines[b], lines[a]
""",
    "two names of one star, whose records part only far from the epoch, exchanged": """
def change(lines):
    a, b = line_of(lines, 'Mabsuthat,31Lyn'), line_of(lines, 'Mabsuthat,kaLyn')
    lines[a], lines[b] = lines[b], lines[a]
""",
    "a designation changed": """
def change(lines):
    at = line_of(lines, 'Gliese 710,HD168442')
    lines[at] = lines[at].replace('HD168442', 'HD168443')
""",
    "a magnitude changed": """
def change(lines):
    magnitude_set(lines, 'Sirius,alCMa', '42.42')
""",
    "a magnitude one step off": """
import math
def change(lines):
    at = line_of(lines, 'Aldebaran,alTau')
    magnitude_set(lines, 'Aldebaran,alTau', repr(math.nextafter(float(lines[at].split(',')[13]), math.inf)))
""",
    "a magnitude not a number": """
def change(lines):
    magnitude_set(lines, 'Vega,alLyr', 'nan')
""",
    "a magnitude in words": """
def change(lines):
    magnitude_set(lines, 'Vega,alLyr', 'bright')
""",
    "a magnitude sentinel changed": """
def change(lines):
    magnitude_set(lines, 'Galactic Center,SgrA*', '0.0')
""",
    "a row added after the last": """
def change(lines):
    last = max(i for i, line in enumerate(lines) if line.strip())
    lines.insert(last + 1, lines[line_of(lines, 'Gliese 710,HD168442')].replace('Gliese 710', 'Gliese 711'))
""",
    "the last row gone": """
def change(lines):
    del lines[line_of(lines, 'Gliese 710,HD168442')]
""",
}


def _proof_run(tmp_path, change):
    temporary = tmp_path / "t"
    temporary.mkdir()
    script = PROOF.replace("CHANGE", change).replace("ROOT", repr(str(EXECUTABLE_DIR)))
    done = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True,
                          env={**os.environ, "TMPDIR": str(temporary)}, timeout=300)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_copy_changed_nowhere_passes_the_proof(tmp_path):
    got = _proof_run(tmp_path, "def change(lines):\n    pass\n")
    assert got == {"stars": 1852, "why": None, "ready": True}


@pytest.mark.parametrize("change", sorted(CHANGES))
def test_any_row_changed_after_the_check_refuses_the_catalogue(tmp_path, change):
    got = _proof_run(tmp_path, CHANGES[change])
    assert got["stars"] is None and got["ready"] is False, got
    assert got["why"].endswith(NOT_THE_ROWS.get(change, ROWS_CHANGED)), got["why"]
    assert "sefstars.txt" not in got["why"]


def test_the_change_only_a_later_date_shows_is_not_seen_at_the_first(tmp_path):
    """The premise of that entry: the first date alone passes it, so it is the later dates that refuse it."""
    first_date_alone = (CHANGES[ONLY_LATER] + "\ntotals = engine.FIXED_STAR_ROWS_RECORDED['totals']\n"
                        "engine.FIXED_STAR_ROWS_RECORDED['totals'] = dict(list(totals.items())[:1])\n")
    assert _proof_run(tmp_path, first_date_alone) == {"stars": 1853, "why": None, "ready": True}  # parted from Aldebaran


def test_the_recorded_rows_are_the_shipped_catalogues_read_by_file_number(engine, capsys):
    """Within half the tolerance, on any machine this runs on: each build leg runs this one test, so
    a platform whose arithmetic stands too near the app's own refusal stops its build, with the
    distance measured at each date in the log, printed whether the test passes or not."""
    recorded = engine["FIXED_STAR_ROWS_RECORDED"]
    assert engine["FIXED_STAR_ROWS_TOLERANCE"] == 2e-6
    assert sorted(recorded["totals"]) == sorted(engine["FIXED_STAR_RECORDED"])

    def read():
        searched = engine["_fixed_star_catalogue_search"]()
        rows = {jd: engine["_fixed_star_rows_summed_at"](jd) for jd in recorded["totals"]}
        labels = [raw_swe.fixstar_ut(str(number), 2451545.0, raw_swe.FLG_MOSEPH)[1] for number in range(1, 2108)]
        return rows, labels, searched
    rows, labels, searched = on_reader(engine, read)
    assert len(rows) == 4
    distances = {jd: math.dist(total, recorded["totals"][jd]) for jd, (_digest, total) in rows.items()}
    with capsys.disabled():
        print("\nStar catalogue, distance of the rows' sum from its record, by date:",
              ", ".join(f"{jd}: {distance:.3e}" for jd, distance in distances.items()))
    assert searched
    for jd, (digest, _total) in rows.items():
        assert digest == recorded["labels"] == hashlib.sha256("\n".join(labels).encode("utf-8")).hexdigest(), jd
        assert distances[jd] <= engine["FIXED_STAR_ROWS_TOLERANCE"] / 2.0, jd


def test_the_tolerance_sees_a_single_arcsecond_on_the_first_row(engine):
    assert math.radians(1.0 / 3600.0) > 2.0 * engine["FIXED_STAR_ROWS_TOLERANCE"]


# The shipped file changed, after its one read, as the copy is: a second read of it would find
# the copy's magnitude, so only the bytes read and checked once can refuse it.
SECOND_READ_DIFFERS = """
import shutil, tempfile
shipped = Path(tempfile.mkdtemp())
for name in ('sefstars.txt', 'sefstars_added.txt'):
    shutil.copyfile(Path(ROOT) / 'ephe' / name, shipped / name)
engine._fixed_star_catalogue_source = lambda: shipped / 'sefstars.txt'

def change(lines):
    magnitude_set(lines, 'Sirius,alCMa', '42.42')
    source = shipped / 'sefstars.txt'
    held = source.read_bytes().decode('latin-1').split('\\n')
    magnitude_set(held, 'Sirius,alCMa', '42.42')
    source.write_bytes('\\n'.join(held).encode('latin-1'))
"""


def test_the_magnitudes_are_read_from_the_bytes_checked_not_a_second_read(tmp_path):
    got = _proof_run(tmp_path, SECOND_READ_DIFFERS)
    assert got["stars"] is None and got["ready"] is False, got
    assert got["why"].endswith(MAGNITUDES_CHANGED), got["why"]


# A magnitude changed between the copy's writing and its reading back: the copy's own check
# refuses it, before the library opens it.
CHANGED_AT_THE_READBACK = """
import os
opened = engine._fixed_star_catalogue_open
written = []

def readback_changed(folder, flags, *rest):
    if flags & os.O_WRONLY:
        written.append(folder)
    elif written:
        path = Path(written.pop()) / 'sefstars.txt'
        lines = path.read_bytes().decode('latin-1').split('\\n')
        magnitude_set(lines, 'Sirius,alCMa', '42.42')
        path.write_bytes('\\n'.join(lines).encode('latin-1'))
    return opened(folder, flags, *rest)

engine._fixed_star_catalogue_open = readback_changed

def change(lines):
    pass
"""


def test_a_magnitude_changed_before_the_copy_is_read_back_refuses_it(tmp_path):
    got = _proof_run(tmp_path, CHANGED_AT_THE_READBACK)
    assert got["stars"] is None and got["ready"] is False, got
    assert "does not read back as the catalogue" in got["why"], got["why"]


# Sirius's magnitude rewritten in the copy, in place, once the proof has passed and before the rows
# are read: the library's reads by number search the open file again, and would find it.
AFTER_THE_PROOF = textwrap.dedent('''
    import json, sys
    from pathlib import Path
    sys.path.insert(0, ROOT)
    import engine
    import swisseph

    def sirius_rewritten():
        path = Path(engine._ephemeris_folder_here()) / 'sefstars.txt'
        lines = path.read_bytes().decode('latin-1').split('\\n')
        at = [i for i, line in enumerate(lines) if [c.strip() for c in line.split(',')[:2]] == ['Sirius', 'alCMa']][0]
        cells = lines[at].split(',')
        cells[13] = '42.42'
        lines[at] = ','.join(cells)
        path.write_bytes('\\n'.join(lines).encode('latin-1'))

    real = engine._fixed_star_rows_read
    seen = {}

    def rewritten_before_the_rows():
        seen['proved'] = engine._FIXED_STAR_STATE['ready']
        sirius_rewritten()
        rows = real()
        seen['library'] = swisseph.fixstar_mag('Sirius')[0]
        return rows

    engine._fixed_star_rows_read = rewritten_before_the_rows
    stars, _missing = engine.fixed_star_places(2451545.0)
    sirius = [star for star in stars if star.catalogue_name == 'Sirius'][0]
    print(json.dumps({**seen, 'stars': len(stars), 'shown': engine.fixed_star_magnitude(sirius),
                      'exported': engine.fixed_star_list_rows([sirius], True)[0]['V magnitude']}))
''')


def test_a_magnitude_rewritten_after_the_proof_is_not_shown(tmp_path):
    """The page and the export carry the magnitudes the proof compared, read from the bytes checked,
    not the library's read again after it."""
    temporary = tmp_path / "t"
    temporary.mkdir()
    script = AFTER_THE_PROOF.replace("ROOT", repr(str(EXECUTABLE_DIR)))
    done = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True,
                          env={**os.environ, "TMPDIR": str(temporary)}, timeout=300)
    assert done.returncode == 0, done.stderr
    got = json.loads(done.stdout.strip().splitlines()[-1])
    assert got["proved"] is True and got["library"] == 42.42, got        # the change landed, and the library reads it
    assert got == {"proved": True, "library": 42.42, "stars": 1852, "shown": -1.46, "exported": -1.46}


def _shipped_magnitudes():
    """Field 13 of every row of the two shipped files, in the file's order, read here."""
    data = b"".join((EXECUTABLE_DIR / "ephe" / name).read_bytes() for name in ("sefstars.txt", "sefstars_added.txt"))
    return [float(line.split(",")[13]) for line in data.decode("latin-1").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def _magnitudes_against_the_library(engine, edit):
    """_fixed_star_magnitudes_agree over the shipped bytes, edited, against the catalogue the library holds."""
    def read():
        assert engine["_fixed_star_catalogue_search"]()
        lines = engine["_fixed_star_catalogue_bytes"](engine["_fixed_star_catalogue_source"]()).decode("latin-1").split("\n")
        edit(lines)
        return engine["_fixed_star_magnitudes_agree"]("\n".join(lines).encode("latin-1"))
    return on_reader(engine, read)


def _record_of(lines, label):
    found = [i for i, line in enumerate(lines) if [cell.strip() for cell in line.split(",")[:2]] == label.split(",")]
    return found[0]


def _magnitude_set(lines, label, value):
    at = _record_of(lines, label)
    cells = lines[at].split(",")
    cells[13] = value(cells[13])
    lines[at] = ",".join(cells)


def _last_record(lines):
    return max(i for i, line in enumerate(lines) if line.strip() and not line.lstrip().startswith("#"))


MAGNITUDE_EDITS = {
    "as checked": (lambda lines: None, True),
    "a row the checked bytes lack": (lambda lines: lines.pop(_last_record(lines)), False),
    "a row more in the checked bytes": (lambda lines: lines.insert(_last_record(lines) + 1, lines[_last_record(lines)]), False),
    "Sirius otherwise": (lambda lines: _magnitude_set(lines, "Sirius,alCMa", lambda _cell: "42.42"), False),
    "a magnitude one step off": (lambda lines: _magnitude_set(
        lines, "Aldebaran,alTau", lambda cell: repr(math.nextafter(float(cell), math.inf))), False),
    "a sentinel otherwise": (lambda lines: _magnitude_set(lines, "Galactic Center,SgrA*", lambda _cell: "0.0"), False),
}


@pytest.mark.parametrize("edit", sorted(MAGNITUDE_EDITS))
def test_every_rows_magnitude_and_the_count_of_rows_are_compared(engine, edit):
    change, agrees = MAGNITUDE_EDITS[edit]
    assert _magnitudes_against_the_library(engine, change) is agrees


def test_only_the_librarys_no_such_row_ends_the_rows(engine, monkeypatch):
    """Any other error at the number past the last row is not taken for the rows' end (the engine's
    swe looks its functions up on the library module at each call)."""
    assert _magnitudes_against_the_library(engine, lambda lines: None) is True     # attached first
    real = raw_swe.fixstar_mag
    after = str(len(_shipped_magnitudes()) + 1)

    def other_error(star):
        if star == after:
            raise raw_swe.Error("swisseph.fixstar_mag: the file could not be read")
        return real(star)
    monkeypatch.setattr(raw_swe, "fixstar_mag", other_error)
    assert _magnitudes_against_the_library(engine, lambda lines: None) is False


def test_every_shown_and_exported_magnitude_is_the_shipped_files(engine):
    """The shipped catalogue, accepted: each star's magnitude, on the page and in the export, is its own
    row's in the shipped file, none where that row has none (0.0 or 999.99)."""
    shipped = _shipped_magnitudes()
    assert len(shipped) == 2107
    held = _groups_with_their_stars(engine)
    assert len(held) == 1852
    for _group, number, star in held:
        expected = None if shipped[number - 1] in (0.0, 999.99) else shipped[number - 1]
        assert engine["fixed_star_magnitude"](star) == expected, star.name
        assert engine["fixed_star_list_rows"]([star], True)[0]["V magnitude"] == expected, star.name
    assert sum(engine["fixed_star_magnitude"](star) is None for _g, _n, star in held) == NO_MAGNITUDE


# --- The places against the reproduction ------------------------------------------------------

def test_swiss_ephemeris_defaults_to_the_precession_the_places_are_pinned_against(engine):
    """Swiss Ephemeris 2.10.03's default, long-term and short-term, is Vondrák et al. 2011, and
    the rows say so: at year 500 its places sit nearer that model's rows than the IAU 2006 ones."""
    assert raw_swe.version == "2.10.03"
    assert raw_swe.MOD_PREC_DEFAULT == raw_swe.MOD_PREC_VONDRAK_2011
    assert raw_swe.MOD_PREC_DEFAULT_SHORT == raw_swe.MOD_PREC_VONDRAK_2011
    residual = {"vondrak2011": [], "iau2006": []}
    gapped = set(PLACE_BOUND_STAR)
    stars, _ = engine["fixed_star_places"](1903855.0)
    for row in PLACES:
        if row["year"] == 500 and row["star"] not in gapped:
            star = star_named(stars, row["star"])
            residual[row["model"]].append(abs(wrapped(star.right_ascension, row["ra"])) * 3600.0)
    assert len(residual["vondrak2011"]) == 23 and len(residual["iau2006"]) == 23
    assert statistics.median(residual["vondrak2011"]) < statistics.median(residual["iau2006"]) / 3.0


@pytest.mark.parametrize("year", sorted(PLACE_BOUND))
def test_the_places_are_the_vondrak_rows_within_the_eras_bound(engine, year):
    """Right ascension and declination of date, and the ecliptic longitude and latitude, whose
    obliquity is the Vondrák model's own mean obliquity on both sides (the IAU 2006 mean
    obliquity, obl06, would move those two by up to 0.048 arcseconds at year 500)."""
    rows = [r for r in PLACES if r["model"] == "vondrak2011" and r["year"] == year]
    assert len(rows) == 28
    worst = {}
    for row in rows:
        stars, missing = engine["fixed_star_places"](row["jd_ut"])
        assert missing == {}
        star = star_named(stars, row["star"])
        delta = max(abs(wrapped(star.right_ascension, row["ra"])), abs(star.declination - row["dec"]),
                    abs(wrapped(star.longitude, row["lon"])), abs(star.latitude - row["lat"])) * 3600.0
        worst[row["star"]] = delta
        bound = PLACE_BOUND_STAR.get(row["star"], PLACE_BOUND)[year]
        assert delta <= bound, f"{row['star']} in {year}: {delta:.4f} arcseconds, bound {bound}"
    # Where the two catalogues agree, so do the two star models, far inside the bound.
    assert worst["Spica"] <= 0.02


def test_the_pairs_are_sahls_28_as_hipparcos_numbers(engine):
    assert set(FIXTURE["pairs"]) == {name for name, _nature in engine["SAHL_FIXED_STARS"]}
    assert len(set(FIXTURE["pairs"].values())) == 28
    assert FIXTURE["pairs"]["Sirius"] == 32349 and FIXTURE["pairs"]["Toliman"] == 71683


# --- The crossings against the reproduction ---------------------------------------------------

def test_the_event_cases_are_the_thirty(engine):
    assert len({e["case"] for e in EVENTS}) == 30 and len(EVENTS) == 112
    assert {e["latitude"] for e in EVENTS} == {45.0} and {e["longitude_east"] for e in EVENTS} == {0.0}
    # Toliman has no rising or setting at 45 N in any of its cases; each has its two culminations.
    toliman = [e for e in EVENTS if e["star"] == "Toliman"]
    assert {e["event"] for e in toliman} == {"culm", "anti"} and len({e["case"] for e in toliman}) == 10


def _time_bound(row):
    return (TIME_BOUND_TOLIMAN if row["star"] == "Toliman" else TIME_BOUND)[row["year"]]


@pytest.mark.parametrize("year", sorted(TIME_BOUND))
def test_a_moment_near_each_event_gives_the_signed_time_within_the_eras_bound(engine, year):
    """The moment set at the reference event plus a seeded offset inside the window: the crossing
    is that far away, on the right side, and the star is in that axis's crossing list."""
    rng = random.Random(f"crossings {year}")
    rows = [e for e in EVENTS if e["year"] == year]
    assert rows
    for row in rows:
        room = _time_bound(row) + 0.5
        before = rng.uniform(60.0, 240.0 - room) * rng.choice((1.0, -1.0))   # + : the moment precedes the event
        jd = row["jd_ut"] - before / 86400.0
        stars, _ = engine["fixed_star_places"](jd)
        frame = frame_at(engine, jd, row["latitude"], row["longitude_east"])
        star = star_named(stars, row["star"])
        axis = EVENT_AXIS[row["event"]]
        seconds = engine["fixed_star_crossing_seconds"](star.right_ascension, star.declination, frame["armc"],
                                                        frame["latitude"], axis)
        assert abs(seconds - before) <= _time_bound(row), f"{row}: {seconds} against {before}"
        listed = engine["fixed_star_axis_lists"](stars, frame)[axis]["crossing"]
        assert star.designation in [r["star"].designation for r in listed], row


@pytest.mark.parametrize("year", sorted(TIME_BOUND))
def test_a_moment_outside_the_window_leaves_the_star_off_that_list(engine, year):
    rows = [e for e in EVENTS if e["year"] == year]
    assert rows
    for row in rows:
        before = 240.0 + _time_bound(row) + 5.0
        jd = row["jd_ut"] - before / 86400.0
        stars, _ = engine["fixed_star_places"](jd)
        lists = engine["fixed_star_axis_lists"](stars, frame_at(engine, jd, row["latitude"], row["longitude_east"]))
        star = star_named(stars, row["star"])
        assert star.designation not in [r["star"].designation for r in lists[EVENT_AXIS[row["event"]]]["crossing"]], row


def test_the_east_longitude_moves_the_crossing_by_its_own_time(engine):
    """The references stand on longitude 0. East of it the same event comes that much earlier, so
    a moment moved back by the longitude's time finds it at the same signed time."""
    row = next(e for e in EVENTS if e["year"] == 2026 and e["star"] == "Spica" and e["event"] == "culm")
    rate = engine["FIXED_STAR_SIDEREAL_RATE"]
    for east in (30.0, -75.0):
        jd = row["jd_ut"] - (east / rate + 90.0) / 86400.0
        stars, _ = engine["fixed_star_places"](jd)
        star = star_named(stars, "Spica")
        armc = frame_at(engine, jd, 45.0, east)["armc"]
        seconds = engine["fixed_star_crossing_seconds"](star.right_ascension, star.declination, armc, 45.0, "MC")
        assert abs(seconds - 90.0) <= 0.05, east


def test_the_hour_angle_is_wrapped_and_half_a_turn_goes_after(engine):
    """A crossing nearly a sidereal day away by the raw difference is a near one. The rate is the
    sidereal one: 60 degrees is 14,361 seconds, not the 14,400 of the solar rate."""
    crossing = engine["fixed_star_crossing_seconds"]
    rate = engine["FIXED_STAR_SIDEREAL_RATE"]
    assert crossing(0.1, 10.0, 359.9, 45.0, "MC") == pytest.approx(0.2 / rate)
    assert crossing(359.9, 10.0, 0.1, 45.0, "MC") == pytest.approx(-0.2 / rate)
    assert crossing(180.1, 10.0, 359.9, 45.0, "IC") == pytest.approx(0.2 / rate, abs=1e-6)
    assert crossing(60.0, 10.0, 0.0, 45.0, "MC") == pytest.approx(14360.68, abs=0.01)
    assert crossing(180.0, 10.0, 0.0, 45.0, "MC") > 0.0 and crossing(0.0, 10.0, 0.0, 45.0, "IC") > 0.0
    assert crossing(180.0, 10.0, 0.0, 45.0, "MC") == pytest.approx(180.0 / rate)


def _placed(engine, **fields):
    return engine["FixedStar"](name=fields.pop("name", "A star"), other_names=(), designation=fields.pop("designation", "x"),
                               catalogue_name="x", lookup="x", **fields)


def test_each_edge_is_inclusive_on_the_unrounded_value(engine, monkeypatch):
    frame = {"axes": {axis: 100.0 for axis in AXES}, "armc": 0.0, "latitude": 0.0}
    edge = _placed(engine, name="edge", longitude=101.0, latitude=50.0, right_ascension=0.0, declination=0.0)
    past = _placed(engine, name="past", longitude=101.0 + 1e-9, latitude=50.0, right_ascension=0.0, declination=0.0)
    back = _placed(engine, name="back", longitude=99.0, latitude=-50.0, right_ascension=0.0, declination=0.0)
    lists = engine["fixed_star_axis_lists"]((edge, past, back), frame)
    assert {r["star"].name for r in lists["MC"]["longitude"]} == {"edge", "back"}

    seconds = {"edge": 240.0, "past": 240.0 + 1e-9, "back": -240.0}
    names = iter([edge, past, back] * 4)
    monkeypatch.setitem(engine, "fixed_star_crossing_seconds", lambda *a: seconds[next(names).name])
    lists = engine["fixed_star_axis_lists"]((edge, past, back), frame)
    assert {r["star"].name for r in lists["MC"]["crossing"]} == {"edge", "back"}


def test_each_list_runs_by_its_own_measures_absolute_size(engine):
    frame = {"axes": {axis: 100.0 for axis in AXES}, "armc": 200.0, "latitude": 30.0}
    rate = engine["FIXED_STAR_SIDEREAL_RATE"]

    def star(name, offset, seconds):
        return _placed(engine, name=name, longitude=100.0 + offset, latitude=0.0,
                       right_ascension=200.0 + seconds * rate, declination=0.0)
    stars = (star("a", 0.2, 100.0), star("b", -0.9, 10.0), star("c", 0.5, -50.0))
    lists = engine["fixed_star_axis_lists"](stars, frame)["MC"]
    # Neither is the longitude's order (b, a, c), and neither is the signed measure's.
    assert [r["star"].name for r in lists["crossing"]] == ["b", "c", "a"]
    assert [r["star"].name for r in lists["longitude"]] == ["a", "c", "b"]


# --- The statuses ----------------------------------------------------------------------------

def test_a_never_rising_star_shows_the_status_and_keeps_its_culminations(engine):
    """Toliman never rises at 45 N: its horizon rows show the status, and its two culminations
    are the references', at each era's bound."""
    rows = [e for e in EVENTS if e["star"] == "Toliman"]
    assert rows
    for row in rows:
        stars, _ = engine["fixed_star_places"](row["jd_ut"])
        star = star_named(stars, "Toliman")
        armc = frame_at(engine, row["jd_ut"], 45.0, 0.0)["armc"]
        for axis, word in (("Ascendant", "Never rises"), ("Descendant", "Never sets")):
            assert engine["fixed_star_crossing_seconds"](star.right_ascension, star.declination, armc, 45.0, axis) is None
            assert engine["fixed_star_crossing_text"](None, axis) == word
        assert star.declination < -45.0
        seconds = engine["fixed_star_crossing_seconds"](star.right_ascension, star.declination, armc, 45.0,
                                                        EVENT_AXIS[row["event"]])
        assert abs(seconds) <= TIME_BOUND_TOLIMAN[row["year"]], row


def test_a_circumpolar_star_at_a_high_latitude_has_no_horizon_crossing(engine):
    stars, _ = engine["fixed_star_places"](2461000.5)
    capella = star_named(stars, "Capella")
    assert capella.declination > 45.0
    assert engine["fixed_star_semi_arc"](capella.declination, 60.0) is None
    for axis in ("Ascendant", "Descendant"):
        assert engine["fixed_star_crossing_seconds"](capella.right_ascension, capella.declination, 10.0, 60.0, axis) is None
    for axis in ("MC", "IC"):
        assert engine["fixed_star_crossing_seconds"](capella.right_ascension, capella.declination, 10.0, 60.0, axis) is not None
    # At the same latitude Sirius crosses: the status is the star's, not the latitude's.
    sirius = star_named(stars, "Sirius")
    assert engine["fixed_star_semi_arc"](sirius.declination, 60.0) is not None


def test_on_the_equator_every_star_is_up_for_half_a_turn(engine):
    crossing = engine["fixed_star_crossing_seconds"]
    half = 90.0 / engine["FIXED_STAR_SIDEREAL_RATE"]
    for declination in (-60.0, 0.0, 16.5, 88.0):
        assert engine["fixed_star_semi_arc"](declination, 0.0) == pytest.approx(90.0)
        culmination = crossing(100.0, declination, 90.0, 0.0, "MC")
        assert crossing(100.0, declination, 90.0, 0.0, "Ascendant") == pytest.approx(culmination - half)
        assert crossing(100.0, declination, 90.0, 0.0, "Descendant") == pytest.approx(culmination + half)


def test_in_the_south_a_northern_star_has_the_short_arc_and_the_far_north_does_not_cross(engine):
    assert engine["fixed_star_semi_arc"](20.0, -45.0) == pytest.approx(68.6558, abs=1e-3)
    assert engine["fixed_star_semi_arc"](-20.0, -45.0) == pytest.approx(180.0 - 68.6558, abs=1e-3)
    assert engine["fixed_star_semi_arc"](50.0, -45.0) is None and engine["fixed_star_semi_arc"](-50.0, -45.0) is None
    # Rising comes before the culmination, setting after it, in either hemisphere.
    crossing = engine["fixed_star_crossing_seconds"]
    culmination = crossing(30.0, 20.0, 10.0, -45.0, "MC")
    assert crossing(30.0, 20.0, 10.0, -45.0, "Ascendant") < culmination < crossing(30.0, 20.0, 10.0, -45.0, "Descendant")


def test_a_grazing_star_still_crosses_and_one_just_past_it_does_not(engine):
    assert engine["fixed_star_semi_arc"](40.0 - 1e-6, 50.0) == pytest.approx(180.0, abs=0.1)
    assert engine["fixed_star_semi_arc"](40.0 + 1e-6, 50.0) is None
    assert engine["fixed_star_semi_arc"](-40.0 + 1e-6, 50.0) == pytest.approx(0.0, abs=0.1)
    assert engine["fixed_star_semi_arc"](-40.0 - 1e-6, 50.0) is None


def test_at_the_pole_no_star_crosses_the_horizon_and_nothing_raises(engine):
    for latitude in (90.0, -90.0):
        assert engine["fixed_star_semi_arc"](16.5, latitude) is None
        assert engine["fixed_star_crossing_seconds"](100.0, 16.5, 40.0, latitude, "Ascendant") is None
        assert engine["fixed_star_crossing_seconds"](100.0, 16.5, 40.0, latitude, "MC") is not None


# --- The printed forms ------------------------------------------------------------------------

def test_the_printed_forms(engine):
    text = engine["fixed_star_crossing_text"]
    assert text(0.4, "MC") == "0:00" and text(-0.4, "MC") == "0:00"
    assert text(4715.0, "MC") == "+78:35" and text(-239.6, "MC") == f"{MINUS}4:00"
    assert text(59.5, "IC") == "+1:00"
    offset = engine["fixed_star_offset_text"]
    assert offset(10.8333333) == "+10° 50′" and offset(-0.8833) == f"{MINUS}00° 53′"
    assert offset(0.0) == "+00° 00′" and offset(-0.001) == "+00° 00′"
    assert offset(-179.999) == f"{MINUS}180° 00′"
    ra = engine["fixed_star_right_ascension_text"]
    assert ra(0.0) == "00h 00m 00s" and ra(101.29018) == "06h 45m 10s"
    assert ra(359.9999) == "00h 00m 00s" and ra(359.99) == "23h 59m 58s"


def test_the_signed_offset_keeps_its_sign_across_0_aries(engine):
    """Star minus axis, + in zodiacal order, the shorter way round: a raw difference past half a
    turn is still a small signed one."""
    offset = engine["fixed_star_longitude_offset"]
    assert offset(359.7, 0.3) == pytest.approx(-0.6, abs=1e-9)
    assert offset(0.3, 359.7) == pytest.approx(0.6, abs=1e-9)
    assert engine["fixed_star_offset_text"](offset(359.7, 0.3)) == f"{MINUS}00° 36′"
    assert engine["fixed_star_offset_text"](offset(0.3, 359.7)) == "+00° 36′"


def test_a_row_on_the_page_keeps_its_offset_sign_across_0_aries(engine, monkeypatch):
    """One star just past 0° Aries with the Ascendant just before it, and one just before with the
    MC just past: each row as the page prints it."""
    sync_engine_to_environment()
    real_places, real_frame = engine["fixed_star_places"], engine["fixed_star_frame"]

    def places(jd):
        stars, _ = real_places(jd)
        return ((dataclasses.replace(star_named(stars, "Spica"), longitude=0.3),
                 dataclasses.replace(star_named(stars, "Vega"), longitude=359.7)), {})

    def frame(chart_data):
        return {**real_frame(chart_data), "axes": {"Ascendant": 359.7, "MC": 0.3, "Descendant": 179.7, "IC": 180.3}}
    monkeypatch.setitem(engine, "fixed_star_places", places)
    monkeypatch.setitem(engine, "fixed_star_frame", frame)
    at = fixed_stars_app().run(timeout=120)
    assert_is_the_page(at, "across 0 Aries")
    rows = {(row["name"], row["values"]["Longitude offset"]) for rows in axis_lists(at).values() for row in rows}
    assert ("Spica", "+00° 36′") in rows
    assert ("Vega", f"{MINUS}00° 36′") in rows


# --- The axes are the chart's -----------------------------------------------------------------

def _sample_charts(engine, seed, count):
    rng = random.Random(seed)
    for _ in range(count):
        year = rng.randint(1, 3000)
        jd = engine["civil_to_jd"](year, rng.randint(1, 12), rng.randint(1, 28), rng.uniform(0.0, 24.0))
        yield jd, rng.uniform(-65.0, 65.0), rng.uniform(-180.0, 180.0)


def test_the_axes_and_the_armc_are_the_charts(engine):
    charts = list(_sample_charts(engine, "axes", 24))
    assert len(charts) == 24
    for jd, lat, lon in charts:
        chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
        frame = engine["fixed_star_frame"](chart)
        ascmc = engine["chart_houses"](jd, lat, lon)[1]
        assert frame["armc"] == ascmc[2] == chart["armc"]
        assert frame["latitude"] == lat == chart["geo_lat"]
        assert frame["axes"] == {"Ascendant": ascmc[0], "MC": ascmc[1], "Descendant": chart["descendant"], "IC": chart["ic"]}
        assert frame["axes"]["Ascendant"] == chart["ascendant"] and frame["axes"]["MC"] == chart["mc"]
        assert abs(wrapped(frame["axes"]["Descendant"], ascmc[0] + 180.0)) < 1e-9
        assert abs(wrapped(frame["axes"]["IC"], ascmc[1] + 180.0)) < 1e-9
        # The hour angle is counted from this ARMC, and the east longitude is in it.
        gast = engine["greenwich_sidereal_time"](jd)
        assert abs(wrapped(frame["armc"], gast + lon)) < 1e-9


def test_the_page_prints_the_charts_axes(engine):
    at = fixed_stars_app().run(timeout=120)
    assert_is_the_page(at, "the example chart")
    from datetime import time
    jd = engine["civil_local_to_jd_ut"](1240, 5, 23, time(14, 30).hour + 30 / 60.0, FLORENCE[1] / 15.0)
    chart = engine["calculate_traditional_chart_jd"](jd, *FLORENCE)
    axes_tab = tab_named(at, "Axes")
    captions = [c.value for c in axes_tab.caption if c.value.startswith("Longitude: ")]
    expected = [f"Longitude: {engine['get_degree_string'](chart[key])}" for key in ("ascendant", "mc", "descendant", "ic")]
    assert captions == expected
    assert [s.value for s in axes_tab.subheader] == list(AXES)
    heads = [node.proto.body for node in walk(axes_tab) if getattr(node, "type", None) == "html"
             and "zij-list-head" in node.proto.body]
    assert len(heads) == 8
    assert [re.findall(r'<div class="zij-locator">([^<]*)', head)[0] for head in heads[0::2]] == [
        "Rising", "Upper culmination", "Setting", "Lower culmination"]
    assert [re.findall(r'<div class="zij-locator">([^<]*)', head)[0] for head in heads[1::2]] == ["Latitude is ignored."] * 4


# --- The crossing list on Sahl's 28 is the chart's cells; the longitude list is this page's own ------

def test_the_crossing_list_for_sahls_28_is_what_the_cells_report(engine):
    """The chart's cells at the Ascendant and the Midheaven, and the page's crossing list narrowed
    to Sahl's stars, over a sample of charts: the same stars, and the same time as printed."""
    seen = 0
    charts = list(_sample_charts(engine, "crossing list", 80))
    assert len(charts) == 80
    for jd, lat, lon in charts:
        chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
        stars, _ = engine["fixed_star_places"](jd)
        lists = engine["fixed_star_axis_lists"](stars, engine["fixed_star_frame"](chart))
        rows = engine["pn4_fixed_stars_in_image"](chart, jd)["rows"]
        for axis, place in (("Ascendant", "on the Ascendant"), ("MC", "on the Midheaven")):
            hits = {r["Star"]: r["Crossing"] for r in rows if r["Place"] == place}
            page = {r["star"].name: engine["fixed_star_crossing_text"](r["seconds"], axis)
                    for r in lists[axis]["crossing"] if r["star"].nature is not None}
            assert hits == page, (jd, axis)
            seen += len(hits)
    assert seen >= 10, "a sample with hardly a hit tests nothing"


def test_the_longitude_list_is_this_pages_own_and_no_cell_reads_it(engine):
    """Lesson 6's example, at the moment the engine's Ascendant comes to Denebola's longitude: the
    star tops this page's longitude list, and the chart's cell has not got it, since it rose long
    before. The list states its own test, and states it apart from the crossing's."""
    jd = engine["civil_to_jd"](2019, 6, 30, 16 + 56 / 60 + 29 / 3600)
    chart = engine["calculate_traditional_chart_jd"](jd, 44 + 58 / 60 + 48 / 3600, -(93 + 15 / 60 + 49 / 3600))
    stars, _ = engine["fixed_star_places"](jd)
    lists = engine["fixed_star_axis_lists"](stars, engine["fixed_star_frame"](chart))
    assert "Denebola" in [r["star"].name for r in lists["Ascendant"]["longitude"]]
    assert "Denebola" not in [r["star"].name for r in lists["Ascendant"]["crossing"]]
    assert "Denebola" not in [r["Star"] for r in engine["pn4_fixed_stars_in_image"](chart, jd)["rows"]]


def test_the_reproductions_place_decides_the_longitude_list_away_from_its_edge(engine):
    """An external pin: the frame set from the reproduction's own longitude, 0.5 degrees either
    side (in), and 1.05 degrees (out), well clear of the catalogue gap and of the edge."""
    rows = [r for r in PLACES if r["model"] == "vondrak2011" and r["year"] == 2026 and r["star"] in ("Spica", "Regulus", "Vega")]
    assert len(rows) == 3
    for row in rows:
        stars, _ = engine["fixed_star_places"](row["jd_ut"])
        star = star_named(stars, row["star"])
        for shift, is_in in ((0.5, True), (-0.5, True), (1.05, False), (-1.05, False)):
            axis_longitude = (row["lon"] - shift) % 360.0
            frame = {"axes": {axis: axis_longitude for axis in AXES}, "armc": 0.0, "latitude": 45.0}
            listed = engine["fixed_star_axis_lists"](stars, frame)["Ascendant"]["longitude"]
            found = [r for r in listed if r["star"] == star]
            assert bool(found) is is_in, (row["star"], shift)
            if found:
                assert found[0]["offset"] == pytest.approx(shift, abs=0.001)


def test_every_row_shows_both_measures_and_is_never_merged(engine):
    at = fixed_stars_app().run(timeout=120)
    assert_is_the_page(at, "the example chart")
    lists = axis_lists(at)
    assert len(tab_named(at, "Axes").dataframe) == 0
    assert all(set(row["values"]) == {CROSSING, "Longitude offset"} for rows in lists.values() for row in rows)
    time_form = re.compile(rf"^([+{MINUS}]\d+:\d\d|0:00|Never rises|Never sets)$")
    offset_form = re.compile(rf"^[+{MINUS}]\d\d+° \d\d′$")
    crossing = [row for (_axis, kind), rows in lists.items() if kind == "crossing" for row in rows]
    longitude = [row for (_axis, kind), rows in lists.items() if kind == "longitude" for row in rows]
    assert crossing and longitude
    assert [v for row in crossing + longitude for v in [row["values"][CROSSING]] if not time_form.match(v)] == []
    assert [v for row in crossing + longitude for v in [row["values"]["Longitude offset"]] if not offset_form.match(v)] == []
    # In a crossing list every time is inside the window as printed; in a longitude list every
    # offset is within a degree. The other measure is free: those are two tests.
    assert [row for row in crossing if int(row["values"][CROSSING].lstrip(f"+{MINUS}").split(":")[0]) > 4] == []
    assert [row for row in longitude if row["values"]["Longitude offset"][1:3] not in ("00", "01")] == []
    assert any(int(row["values"]["Longitude offset"][1:].split("°")[0]) > 1 for row in crossing)
    assert any(row["values"][CROSSING].startswith("Never") or int(row["values"][CROSSING].lstrip(f"+{MINUS}").split(":")[0]) > 4
               for row in longitude)


# --- The page ----------------------------------------------------------------------------------

def test_the_page_stands_last_in_the_first_group_and_the_sky_alone_between_the_next_two():
    source = (Path(__file__).parent.parent / "app.py").read_text(encoding="utf-8")
    first_group = source[source.index('"**The Nativity**": ['):source.index('"**Prediction**": [')]
    assert first_group.rstrip().rstrip("],").rstrip().endswith(
        'st.Page(page_fixed_stars, url_path="fixed-stars", title="Fixed stars"),')
    assert "page_sky" not in first_group
    between = source[source.index('"**Prediction**": ['):source.index('"**Reference**": [')]
    assert between[between.index('"": ['):].rstrip().rstrip("],").rstrip().endswith(
        'st.Page(page_sky, url_path="sky", title="The Sky"),')
    assert source.count("st.Page(page_sky,") == 1


def test_with_no_chart_the_page_says_so_as_its_neighbours_do():
    at = fixed_stars_app(date="not a date")
    at.session_state["manual_lat_key"] = 200.0
    at.run(timeout=120)
    assert_no_exception(at, "no chart")
    assert [h.value for h in at.main.header] == ["Fixed stars"]
    assert [c.value for c in at.main.caption] == [NO_CHART_SENTENCE]
    assert len(at.main.error) == 1 and len(at.main.tabs) == 0 and len(at.main.dataframe) == 0
    assert not [t for t in printed(at) if THE_WORD.search(t)]


@pytest.mark.parametrize("viewer_theme", ["light", "dark"])
def test_the_page_renders_alike_in_both_themes_with_nothing_of_the_banned_word(viewer_theme, monkeypatch):
    """The harness has no browser, so the theme is handed to the read at the top of the app. The
    page reads no theme itself, so the two must draw the same page."""
    sync_engine_to_environment()
    import streamlit as st

    class Context:
        theme = types.SimpleNamespace(type=viewer_theme)

        def __getattr__(self, name):
            return getattr(real_context, name)
    real_context = st.context
    monkeypatch.setattr(st, "context", Context())
    at = fixed_stars_app().run(timeout=120)
    assert_is_the_page(at, viewer_theme)
    assert [s.value for s in at.main.subheader] == [*AXES, "Stars harming eyes"]
    assert_the_word_is_absent(at)
    # The strip first, under the one header, as on every chart page.
    assert at.main.caption[0].value.startswith("Unsaved chart · 1240-05-23 14:30:00")
    assert "Two measures at each axis: crossing in time and proximity in longitude." in [m.value for m in at.main.markdown]


def test_the_nature_column_head_is_the_engines_own(engine):
    at = fixed_stars_app().run(timeout=120)
    assert_is_the_page(at, "the example chart")
    places, _ = engine["_fixed_star_sahl_places"](2451545.0)
    hit = engine["_star_hits"](places, [("x", engine["_star_by_longitude"](places["Sirius"].longitude))])[0]
    stars, _ = engine["fixed_star_places"](2451545.0)
    columns = list(engine["fixed_star_list_rows"](stars)[0])
    assert engine["FIXED_STAR_NATURE_HEADING"] in hit and columns[-1] == engine["FIXED_STAR_NATURE_HEADING"]
    assert columns == ["Name", "Designation", "Other names", "Catalogue designation", "Longitude", "Latitude (°)",
                       "Right ascension (h m s)", "Declination (°)", "V magnitude", engine["FIXED_STAR_NATURE_HEADING"]]
    # The natures' source stands in the notes it belongs to, first, and nowhere else on the tab.
    star_tab = tab_named(at, "Star list")
    notes = next(e for e in star_tab.expander if e.label == "Nature notes")
    assert notes.caption[0].value == "Natures: Rhetorius, per Dykes (Sahl I pp. 391–392)."
    assert [c.value for c in star_tab.caption].count(notes.caption[0].value) == 1


def _axes_tables(at):
    return axis_lists(at)


def test_sahls_28_stand_in_longitude_order_and_the_control_shows_all(engine):
    at = fixed_stars_app().run(timeout=120)
    assert_is_the_page(at, "the example chart")
    choose_population(at, "Sahl's 28")
    star_tab = tab_named(at, "Star list")
    rows = sahl_rows(at)
    names = {engine["FIXED_STAR_PAGE_NAME"].get(n, n) for n, _nature in engine["SAHL_FIXED_STARS"]}
    assert {row["name"] for row in rows} == names and len(rows) == 28
    assert len(star_tab.dataframe) == 0
    assert "Sahl's 28 · 28 entries shown" in [c.value for c in star_tab.caption]
    assert next(row["nature"] for row in rows if row["name"] == "Spica") == "Venus-Mercury"
    # In longitude order, on the unrounded longitude.
    jd = engine["civil_local_to_jd_ut"](1240, 5, 23, 14.5, FLORENCE[1] / 15.0)
    stars, _ = engine["fixed_star_places"](jd)
    assert [row["name"] for row in rows] == [s.name for s in sorted((s for s in stars if s.nature), key=lambda s: s.longitude)]
    assert all(re.fullmatch(r"\d\d° [A-Z][a-z]{2} \d\d'", row["values"]["Longitude"]) for row in rows)

    # One control, above the tabs.
    assert [g.options for g in at.main.button_group] == [["Sahl's 28", "Curated List", "Significant Stars", "Full Catalogue"]]
    assert len(star_tab.button_group) == 0
    choose_population(at, "Full Catalogue")
    assert_is_the_page(at, "the full catalogue")
    star_tab = tab_named(at, "Star list")
    table = star_tab.dataframe[0].value
    assert len(table) == 1852
    assert "Full Catalogue · 1852 entries shown" in [c.value for c in star_tab.caption]
    longitude_order = [engine["fixed_star_shown_name"](s) for s in sorted(stars, key=lambda s: s.longitude)]
    assert list(table["Name"]) == longitude_order
    assert list(table.columns) == ["Name", "Designation", "Longitude", "Latitude (°)", "Right ascension (h m s)",
                                   "Declination (°)", "V magnitude"]
    assert table["V magnitude"].isna().sum() == NO_MAGNITUDE
    assert_the_word_is_absent(at)


def test_a_star_with_no_magnitude_prints_the_word_and_stays_null_where_data_is_kept():
    """Streamlit's own mark for a missing value is the word "None"; the column stays numeric under
    the placeholder, and the JSON keeps the null while the two reports print the page's word."""
    at = fixed_stars_app().run(timeout=120)
    choose_population(at, "Full Catalogue")
    assert_is_the_page(at, "the full catalogue")
    table = tab_named(at, "Star list").dataframe[0]
    assert table.proto.placeholder == "Unavailable"
    assert pd.api.types.is_float_dtype(table.value["V magnitude"]) and table.value["V magnitude"].isna().sum() == NO_MAGNITUDE
    rows = _export_tables(at)["Star list: Full Catalogue"][0]["rows"]
    assert sum(r["V magnitude"] is None for r in rows) == NO_MAGNITUDE
    assert "Unavailable" not in json.dumps(rows, ensure_ascii=False)
    report = at.session_state["_fixed_stars_markdown"]
    head = next(line for line in report.splitlines() if line.startswith("| Name | Designation | Other names"))
    assert head.split(" | ")[-2] == "V magnitude"
    star_rows = [line.split(" | ") for line in itertools.takewhile(lambda line: line.startswith("| "),
                                                                    report.splitlines()[report.splitlines().index(head) + 2:])]
    assert len(star_rows) == 1852
    assert next(r for r in star_rows if r[0] == "| Great Attractor")[-2] == "Unavailable"
    assert sum(r[-2] == "Unavailable" for r in star_rows) == NO_MAGNITUDE
    page = at.session_state["_fixed_stars_html"]
    assert page.count("<td>Unavailable</td>") == NO_MAGNITUDE
    assert "<td>None</td>" not in page and "| None |" not in report


def test_the_star_list_of_sahls_28_has_no_missing_magnitude_for_the_word_to_cover():
    at = fixed_stars_app().run(timeout=120)
    assert_is_the_page(at, "the example chart")
    choose_population(at, "Sahl's 28")
    star_list = _export_tables(at)["Star list: Sahl's 28"][0]["rows"]
    assert len(star_list) == 28 and all(row["V magnitude"] is not None for row in star_list)
    assert "Unavailable" not in at.session_state["_fixed_stars_markdown"]
    assert "Unavailable" not in at.session_state["_fixed_stars_html"]


def test_the_star_list_is_drawn_at_a_bounded_height(monkeypatch):
    """Sahl's 28 are rows, with no grid and no scrollbar of their own; a table keeps its
    scrollbar under the tabs, at a height the page asks for and not one that grows with it."""
    sync_engine_to_environment()
    import streamlit
    real = streamlit.dataframe
    asked = []

    def dataframe(data, **kwargs):
        asked.append((len(data.data), kwargs.get("height")))
        return real(data, **kwargs)
    monkeypatch.setattr(streamlit, "dataframe", dataframe)
    at = fixed_stars_app().run(timeout=120)
    assert_is_the_page(at, "the example chart")
    choose_population(at, "Sahl's 28")
    asked.clear()
    at.run(timeout=120)
    assert asked == []
    choose_population(at, "Full Catalogue")
    assert_is_the_page(at, "the full catalogue")
    assert (1852, 615) in asked, "600, and room for its sideways scrollbar"


def test_the_nature_notes_are_the_literal_values(engine):
    at = fixed_stars_app().run(timeout=120)
    assert_is_the_page(at, "the example chart")
    notes = next(e for e in tab_named(at, "Star list").expander if e.label == "Nature notes")
    text = notes.markdown[0].value
    for name, nature in engine["SAHL_FIXED_STARS"]:
        assert f"{engine['FIXED_STAR_PAGE_NAME'].get(name, name)}: {nature}" in text


def test_the_lists_are_drawn_over_the_catalogue_with_sahls_stars_among_them(engine):
    """A star outside Sahl's 28 stands in a list as Sahl's do, under its designation if it has no
    name: in the example chart the MC's crossing list opens on a star with none."""
    at = fixed_stars_app().run(timeout=120)
    assert_is_the_page(at, "the example chart")
    choose_population(at, "Full Catalogue")
    rows = [row for rows in axis_lists(at).values() for row in rows]
    assert any(row["name"] not in {engine["FIXED_STAR_PAGE_NAME"].get(k, k) for k, _ in engine["SAHL_FIXED_STARS"]} for row in rows)
    assert any(row["second"] is None for row in rows), "a star with no name prints its designation once"


def test_an_empty_list_says_so_and_a_missing_star_is_named(engine, monkeypatch):
    """A catalogue holding only one star, far from every axis' list in the example chart but for
    those it happens to meet: the empty lists say they are empty, and the star the catalogue could
    not place is named above the tabs."""
    sync_engine_to_environment()
    real = engine["fixed_star_places"]

    def one_star(jd):
        stars, _ = real(jd)
        return tuple(s for s in stars if s.name == "Sirius"), {"Zuben Eschamali": "refused"}
    monkeypatch.setitem(engine, "fixed_star_places", one_star)
    at = fixed_stars_app().run(timeout=120)
    assert_is_the_page(at, "one star")
    assert engine["fixed_star_places"] is one_star, "the premise: nothing reloaded the engine under the patch"
    assert sys.modules["engine"].__dict__ is engine, "the premise: the app's engine is the one patched"
    assert [w.value for w in at.main.warning] == ["Not in the catalogue attached, so not placed: Zuben Eschemali."]
    infos = [i.value for i in tab_named(at, "Axes").info]
    assert infos.count("No crossings within ±4 min.") >= 3 and infos.count("No entries within 1° in longitude.") >= 3
    assert "Curated List · 1 entries shown" in [c.value for c in tab_named(at, "Star list").caption]
    assert_the_word_is_absent(at)


def test_with_no_star_placed_the_list_says_so(engine, monkeypatch):
    sync_engine_to_environment()
    monkeypatch.setitem(engine, "fixed_star_places", lambda jd: ((), {}))
    at = fixed_stars_app().run(timeout=120)
    assert_no_exception(at, "no star placed")
    assert [h.value for h in at.main.header] == ["Fixed stars"]
    assert [i.value for i in at.main.info] == ["No catalogue entries could be placed."], "it stands alone"
    assert len(at.main.tabs) == 0 and [node.value for node in at.main.subheader] == ["Stars harming eyes"]
    assert_the_word_is_absent(at)


def test_without_a_catalogue_the_page_says_so(engine, monkeypatch):
    sync_engine_to_environment()
    monkeypatch.setitem(engine, "fixed_star_places", lambda jd: (None, {}))
    at = fixed_stars_app().run(timeout=120)
    assert_no_exception(at, "no catalogue")
    assert [h.value for h in at.main.header] == ["Fixed stars"]
    assert [i.value for i in at.main.info] == ["The star catalogue is unavailable; no entries could be placed."]
    assert len(at.main.tabs) == 0 and [node.value for node in at.main.subheader] == ["Stars harming eyes"]
    assert_the_word_is_absent(at)


def test_only_the_seven_help_strings_stand_on_the_page():
    import ast
    tree = ast.parse((Path(__file__).parent.parent / "app.py").read_text(encoding="utf-8"))
    constants = {n.targets[0].id: n.value for n in tree.body
                 if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                 and n.name in ("page_fixed_stars", "_fixed_stars_export_button")]
    assert len(functions) == 2
    helps = []
    for function in functions:
        for node in ast.walk(function):
            for keyword in getattr(node, "keywords", ()):
                if keyword.arg == "help":
                    value = keyword.value.args[0] if getattr(getattr(keyword.value, "func", None), "id", "") == "page_words" else keyword.value
                    value = constants.get(getattr(value, "id", None), value)
                    helps.append("".join(p.value for p in ast.walk(value)
                                         if isinstance(p, ast.Constant) and isinstance(p.value, str)))
    # Three stand on what they explain, and the other four in one disclosure.
    assert sorted(helps) == sorted((
        "Rhetorius's natures, from Dykes's table at Sahl I pp. 391–392; a dash marks other catalogue objects.",
        "Which stars both tabs and the export list, from Sahl's 28 to the whole catalogue with its nonstellar "
        "entries; the finder reaches every star.",
        "Exports all eight axis lists and the selected star list in longitude order; changing tabs does not change "
        "the export.",
    ))
    at = fixed_stars_app().run(timeout=120)
    about = next(e for e in tab_named(at, "Axes").expander if e.label == "About the two measures")
    assert [m.value for m in about.markdown] == [
        "A crossing falls within four minutes before or after the chart. Rising and setting use the star's centre "
        "at altitude 0°, geocentric, without refraction.",
        "The star's longitude lies within 1° of this axis's longitude; latitude is ignored.",
        f"Crossing time: + is after the chart, {MINUS} is before it; 0:00 is at the chart. Minutes and seconds are "
        "time, not arc.",
        "Longitude offset is the signed shortest difference from the axis to the star: + follows zodiacal order, "
        f"{MINUS} runs against it.",
    ]


@pytest.mark.parametrize("date, place", [("0001-03-01", FLORENCE), ("3000-06-15", FLORENCE), ("2026-06-30", (89.5, 10.0)),
                                         ("2026-06-30", (90.0, 0.0)), ("2026-06-30", (-90.0, 0.0)),
                                         ("1990-12-21", (-45.0, -70.0)), ("1990-12-21", (0.0, 30.0))],
                         ids=["year 1", "year 3000", "near the pole", "the north pole", "the south pole", "the south", "the equator"])
def test_the_ends_of_the_range_and_the_poleward_latitudes_render(date, place):
    at = fixed_stars_app(date=date)
    at.session_state["manual_lat_key"], at.session_state["manual_lon_key"] = place
    at.run(timeout=120)
    assert_is_the_page(at, f"{date} at {place}")
    choose_population(at, "Sahl's 28")
    assert len(sahl_rows(at)) == 28
    assert_the_word_is_absent(at)


# --- The export --------------------------------------------------------------------------------

def _export_text(at):
    """The three files as text, the moment of exporting taken out: it is the one date in them."""
    analysis = at.session_state["_fixed_stars_export"]
    stamp = analysis["exported"]
    return [text.replace(stamp, "") for text in (json.dumps(analysis, ensure_ascii=False, default=str),
                                                 at.session_state["_fixed_stars_markdown"],
                                                 at.session_state["_fixed_stars_html"])]


def _export_tables(at):
    return at.session_state["_fixed_stars_export"]["results"]["Fixed stars"]


def test_the_export_holds_all_eight_lists_and_the_star_list_as_the_page_prints_them(engine):
    at = fixed_stars_app().run(timeout=120)
    assert_is_the_page(at, "the example chart")
    choose_population(at, "Sahl's 28")
    tables = _export_tables(at)
    assert list(tables) == [f"{axis}: {title}" for axis in AXES
                            for title in ("Crossing within ±4 min", "Longitude within 1°")] + ["Star list: Sahl's 28", "Stars harming eyes"]
    shown = axis_lists(at)
    headings = list(tables)[:8]
    assert len(headings) == 8
    assert len(shown) == 8
    for heading, rows in zip(headings, shown.values()):
        assert [(r["Name"], r[CROSSING], r[OFFSET]) for r in tables[heading][0]["rows"]] == [
            (row["name"], row["values"][CROSSING], row["values"]["Longitude offset"]) for row in rows], heading
    # Each list carries its axis's longitude, and the crossing list its event.
    assert "· Upper culmination" in tables["MC: Crossing within ±4 min"][0]["label"]
    captions = [c.value for c in tab_named(at, "Axes").caption if c.value.startswith("Longitude: ")]
    assert tables["Ascendant: Longitude within 1°"][0]["label"] == captions[0]
    # The star list, with its natures' source, in longitude order.
    star_list = tables["Star list: Sahl's 28"][0]
    assert star_list["citation"] == "Natures: Rhetorius, per Dykes (Sahl I pp. 391–392)."
    assert [r["Name"] for r in star_list["rows"]] == [row["name"] for row in sahl_rows(at)]
    assert len(star_list["rows"]) == 28


def test_the_export_says_what_it_holds_and_the_signs(engine):
    at = fixed_stars_app().run(timeout=120)
    scope = at.session_state["_fixed_stars_export"]["scope"]
    assert scope.startswith("All eight axis lists, the star list as filtered, and the stars harming eyes.")
    for words in ("+ is after the chart", "+ follows zodiacal order", "latitude is ignored", "without refraction"):
        assert words in scope
    texts = _export_text(at)
    assert len(texts) == 3
    for text in texts:
        assert "All eight axis lists" in text and "Crossing within" in text and "Rhetorius" in text


def test_the_export_follows_the_control_in_longitude_order_whatever_the_tab(engine):
    at = fixed_stars_app().run(timeout=120)
    choose_population(at, "Full Catalogue")
    assert_is_the_page(at, "the full catalogue")
    star_list = _export_tables(at)["Star list: Full Catalogue"][0]
    jd = engine["civil_local_to_jd_ut"](1240, 5, 23, 14.5, FLORENCE[1] / 15.0)
    stars, _ = engine["fixed_star_places"](jd)
    assert [r["Name"] for r in star_list["rows"]] == [engine["fixed_star_shown_name"](s) for s in sorted(stars, key=lambda s: s.longitude)]
    assert len(star_list["rows"]) == 1852
    captions = [c.value for c in at.main.caption]
    assert "Star list: Full Catalogue · 1852 entries." in captions
    assert [r["Name"] for r in star_list["rows"][:3]] == list(tab_named(at, "Star list").dataframe[0].value["Name"])[:3]


def test_the_export_carries_the_build_process_guards_markers_nowhere(engine):
    """The guard in test_prose_counts reads app.py; the export a reader opens is built at run time,
    from the engine's strings too, so its words are scanned here, full catalogue and all."""
    from test_prose_counts import BUILD_PROCESS_MARKERS, COURSE_MARKERS
    at = fixed_stars_app().run(timeout=120)
    choose_population(at, "Full Catalogue")
    texts = _export_text(at)
    assert len(texts) == 3
    for text in texts:
        assert BUILD_PROCESS_MARKERS.findall(text) == []
        assert COURSE_MARKERS.findall(text) == []
        assert not THE_WORD.search(text)
    # The guard's own sieve works on this text: the premise of the scan.
    assert BUILD_PROCESS_MARKERS.search(_export_text(at)[1] + " the owner")


def test_the_export_at_the_pole_says_so_and_stays_clear_of_the_word(engine):
    at = fixed_stars_app(date="2026-06-30")
    at.session_state["manual_lat_key"], at.session_state["manual_lon_key"] = 90.0, 0.0
    at.run(timeout=120)
    assert_is_the_page(at, "the pole")
    # The strip's form on the pages counted from the Ascendant: its sentence at the pole.
    assert [w.value[:39] for w in at.main.warning] == ["At the pole no ecliptic degree rises or"]
    assert "pole" in at.session_state["_fixed_stars_export"]["status"]
    assert not [t for t in _export_text(at) if THE_WORD.search(t)]


def test_an_empty_list_and_a_missing_star_stand_in_the_export(engine, monkeypatch):
    sync_engine_to_environment()
    real = engine["fixed_star_places"]

    def one_star(jd):
        stars, _ = real(jd)
        return tuple(s for s in stars if s.name == "Sirius"), {"Zuben Eschamali": "refused"}
    monkeypatch.setitem(engine, "fixed_star_places", one_star)
    at = fixed_stars_app().run(timeout=120)
    assert_is_the_page(at, "one star")
    tables = _export_tables(at)
    assert tables["Star list: Curated List"][0]["label"] == "Not in the catalogue attached, so not placed: Zuben Eschemali."
    labels = [entries[0]["label"] for heading, entries in tables.items() if not entries[0]["rows"]]
    assert any(label.endswith("No crossings within ±4 min.") for label in labels)
    assert any(label.endswith("No entries within 1° in longitude.") for label in labels)


def test_the_pages_export_is_the_one_buttons_three_formats_and_a_click_reruns_nothing():
    at = fixed_stars_app().run(timeout=120)
    assert_is_the_page(at, "the example chart")
    popovers = [n for n in walk(at.main) if getattr(n, "type", None) == "popover"]
    assert [p.proto.popover.label for p in popovers] == ["Export fixed stars"]
    assert popovers[0].proto.popover.help.startswith("Exports all eight axis lists")
    buttons = [n for n in walk(popovers[0]) if getattr(n, "type", None) == "download_button"]
    assert [b.label for b in buttons] == ["HTML", "JSON", "Markdown"]
    assert [b.label for b in buttons if b.proto.ignore_rerun is not True] == []
    assert "Choose a format" in [m.value for m in walk(popovers[0]) if getattr(m, "type", None) == "markdown"]
    # The chart's own export stands in the sidebar as ever, and carries nothing of this page's.
    assert "Fixed stars" not in at.session_state["_analysis_export"]["results"]
    assert at.session_state["_analysis_export"]["scope"].startswith("The export carries this chart's readings")


def test_a_refused_run_keeps_no_export_of_the_last_chart():
    at = fixed_stars_app().run(timeout=120)
    assert "_fixed_stars_export" in at.session_state, "the premise: the export is in the session"
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = ""
    at.run(timeout=120)
    assert_no_exception(at, "a refused run")
    assert [c.value for c in at.main.caption] == [NO_CHART_SENTENCE]
    assert "_fixed_stars_export" not in at.session_state and "_fixed_stars_html" not in at.session_state
    assert "_fixed_stars_markdown" not in at.session_state


def test_the_chart_export_keeps_its_moment_and_its_blocks_and_this_one_only_what_it_reads():
    at = fixed_stars_app().run(timeout=120)
    chart, stars = at.session_state["_analysis_export"], at.session_state["_fixed_stars_export"]
    assert stars["input"] == chart["input"] and stars["chart"] == chart["chart"]
    assert stars["readings"] == [] and stars["display"] == {} and stars["target"] == {}
    assert not {"readings", "saved_with", "target_date"} & set(stars["entered"])
    report = at.session_state["_fixed_stars_markdown"]
    assert "## The moment and place the chart was cast at" in report and "## The readings in force" not in report
    assert "## The readings in force" in at.session_state["_analysis_markdown"]
