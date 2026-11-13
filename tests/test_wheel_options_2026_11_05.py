"""The wheels' Options box, the heading "The wheel", the plain looks, the wheel's
place on the page, and the expanded wheel's exit button.

The plain wheel is one ink on one ground, read from the house palette: every
fill, stroke and style in the SVG is parsed over invented charts, polar and
withheld ones among them, in every Timing view, and its geometry is the
ordinary drawing's once colour values are normalised.
"""
import ast
import datetime
import hashlib
import json
import re
import types
import xml.etree.ElementTree as ET

import pytest
import streamlit as st
from streamlit.util import calc_hash

import house_style
import wheel
from engine import page_words
from conftest import (APP_PATH, assert_no_exception, component_mounts, make_app, natal_wheel_envelope,
                      sync_engine_to_environment, ui_source)

COLOUR_ATTRIBUTES = ("fill", "stroke", "stop-color", "flood-color", "lighting-color", "color")
OPACITY_ATTRIBUTES = ("opacity", "fill-opacity", "stroke-opacity", "stop-opacity", "flood-opacity")
THEMES = {None: "light", "light": "light", "dark": "dark"}
# Invented charts: (date and time, latitude, longitude). Ordinary, southern,
# crowded and near the pole, and the pole itself, whose division is withheld.
INVENTED = [
    ((1240, 5, 23, 13, 30), 43.77, 11.26), ((1000, 1, 1, 0, 0), 30.05, 31.23), ((1503, 12, 14, 12, 0), 43.93, 4.81),
    ((1610, 3, 3, 3, 3), 52.2, 0.12), ((1700, 7, 21, 22, 15), -33.9, 18.42), ((1755, 2, 28, 6, 40), 19.43, -99.13),
    ((1801, 9, 9, 9, 9), -12.05, -77.04), ((1850, 11, 1, 17, 20), 35.68, 139.69), ((1899, 6, 30, 23, 59), 64.14, -21.9),
    ((1912, 4, 15, 2, 20), 41.73, -49.95), ((1933, 10, 10, 10, 10), -41.29, 174.78), ((1944, 8, 25, 15, 0), 48.85, 2.35),
    ((1962, 2, 5, 12, 0), 22.3, 114.17), ((1969, 7, 20, 20, 17), 28.57, -80.65), ((1977, 8, 16, 8, 8), 1.35, 103.82),
    ((1984, 1, 24, 4, 44), 55.75, 37.62), ((1999, 8, 11, 11, 3), 50.08, 14.44), ((2004, 6, 8, 5, 40), -1.29, 36.82),
    ((2012, 12, 21, 11, 11), 20.68, -88.57), ((2020, 12, 21, 18, 22), 37.98, 23.73),
    ((1975, 3, 14, 18, 0), 75.0, 20.0), ((1975, 6, 21, 12, 0), -78.0, 166.0), ((1975, 3, 14, 18, 0), 90.0, 20.0),
]
# The output for these before the box stood, whole, fonts and all: off is that
# drawing to the byte. A branch that redraws the wheel on purpose takes the new
# digests from a run at its own head and says so.
OFF_SHA256 = {None: "a171ef71ffd20792f2e2c87c64adc6b4bfeb1e4ae4d2dfcfadf8f9e6b4ad8b4f", "dark": "74950d581be2364ad2a56dd252eec0e671be13b96573480899635e4b704a5c03"}


def _moment(when):
    return datetime.datetime(*when)


@pytest.fixture(scope="module")
def charts(engine):
    return [(when, lat, lon, engine["calculate_traditional_chart"](_moment(when), lat, lon)) for when, lat, lon in INVENTED]


def _natal(engine, entry, **kw):
    when, lat, lon, chart = entry
    return engine["generate_hybrid_svg"](chart, "Invented & <b>", "Nowhere", lat, lon, _moment(when), "LMT",
                                         chronocrats={"Hour Lord": "Venus", "Approximate": False}, **kw)


def _rings_of(entry, count):
    chart = entry[3]
    rings = [{"label": "Nativity", "chart": chart, "when": "birth"},
             {"label": "Year", "chart": chart, "when": "year"},
             {"label": "Month", "chart": chart, "when": "month"}]
    return rings[:count]


def _extras(entry):
    longitude = entry[3]["ascendant"]
    return {0: [("Lot", (longitude + 11) % 360, "Lot"), ("ray", (longitude + 40) % 360, "x"), ("twelfth", (longitude + 90) % 360)]}


def _views(entry):
    """The five views as the page asks for them, with everything on."""
    asc = entry[3]["ascendant"]
    year = int(((asc + 90) % 360) // 30)
    month = int(((asc + 150) % 360) // 30)
    arc = {"start": asc, "end": (asc + 47) % 360}
    marks = [("TP", (asc + 100) % 360, 0)]
    badges = {0: {"Sun": "D", "Moon": "P·F", "Saturn": "f·O"}}
    return {"Year": (1, {}),
            "Year over root": (2, dict(shade_sign=year, profection_from=asc, distribution=arc, marks=marks, badges=badges)),
            "Month over year and root": (3, dict(shade_sign=year, outline_sign=month, profection_from=asc,
                                                 distribution=arc, marks=marks, badges=badges)),
            "Month": (1, {}),
            "Profection": (1, dict(shade_sign=year, outline_sign=month, profection_from=asc, marks=marks))}


def _multi(engine, entry, view, **kw):
    count, options = _views(entry)[view]
    return engine["generate_multiwheel_svg"](_rings_of(entry, count), "Invented", bounds=True, extras=_extras(entry),
                                             **options, **kw)


def _painted(svg):
    """Every paint in the picture, by what paints it: {(attribute, value)}. A
    style attribute or a style sheet's rule is parsed as well; the font faces in the style
    sheet are the only rules it may hold, and they paint nothing."""
    root = ET.fromstring(svg)
    painted, opacities = set(), []
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "style":
            rules = re.sub(r"@font-face\s*\{[^{}]*\}", "", element.text or "").strip()
            assert not rules, f"a rule beside the font faces: {rules[:200]}"
            continue
        for name in COLOUR_ATTRIBUTES:
            if element.get(name) is not None:
                painted.add((name, element.get(name)))
        opacities += [(name, element.get(name)) for name in OPACITY_ATTRIBUTES if element.get(name) is not None]
        for declaration in (element.get("style") or "").split(";"):
            name, _sep, value = declaration.partition(":")
            name = name.strip().lower()
            if name in COLOUR_ATTRIBUTES:
                painted.add((name, value.strip()))
            elif name in OPACITY_ATTRIBUTES:
                opacities.append((name, value.strip()))
        assert tag not in ("linearGradient", "radialGradient", "pattern", "filter", "image"), f"a {tag} in a plain wheel"
    assert not opacities, f"an opacity makes a grey: {opacities}"
    return painted


def _assert_one_ink_one_ground(svg, theme):
    palette = house_style.WHEEL_PALETTES[THEMES[theme]]
    ink, ground = palette["ink"], palette.get("face", palette["bg"])
    painted = _painted(svg)
    assert {value for _name, value in painted} <= {ink, ground, "none"}, sorted(painted)
    assert {value for name, value in painted if name != "fill"} <= {ink, ground, "none"}, sorted(painted)
    # The one stroke in the ground is the edge behind a chart wheel's label: its letters
    # in their point's group, and its glyph's copy beneath, which alone is filled with
    # the ground as well. No hub, no line, no Timing wheel carries it. A stroke on a
    # letter in the ink is a label's glyph alone: its weight.
    root = ET.fromstring(svg)
    groups = [] if any(e.get("data-ring") is not None for e in root.iter()) else [
        list(g) for g in root.iter() if g.get("class") == "pt" and not any(k.tag.endswith("rect") for k in g)]
    letters = {id(k) for group in groups for k in group}
    glyphs = {id(group[0]) for group in groups}
    for element in root.iter():
        is_text, is_edge = element.tag.endswith("text"), element.get("class") == "edge" and bool(groups)
        if element.get("stroke") == ground:
            assert is_text and element.get("paint-order") == "stroke" and (is_edge or id(element) in letters), element.attrib
        if is_text and element.get("fill") == ground:
            assert is_edge, element.attrib
        if is_text and element.get("stroke") == ink:
            assert id(element) in glyphs, element.attrib
    assert ("fill", ink) in painted
    # The whole picture stands on the ground, whichever it is.
    first = next(e for e in ET.fromstring(svg).iter() if e.tag.endswith("rect"))
    assert first.get("fill") == ground
    # A surface is never the ink, or a sign, a band or a bound would be a solid
    # block: only a letter and an arrowhead are filled with it.
    surfaces = {e.get("fill") for e in ET.fromstring(svg).iter()
                if e.tag.rsplit("}", 1)[-1] in ("rect", "circle", "path") and e.get("fill") is not None}
    assert surfaces <= {ground, "none"}, sorted(surfaces)


def _normalised(svg):
    """The drawing without its colour values: every paint that is not "none"
    is one word. Everything else, to the byte, stays."""
    return re.sub(r'\b(fill|stroke)="(?!none")[^"]*"', r'\1="C"', svg)


# --- the plain palette --------------------------------------------------------

def test_the_plain_palette_is_read_from_the_house_and_writes_no_colour_of_its_own():
    for theme, name in THEMES.items():
        ordinary = house_style.WHEEL_PALETTES[name]
        plain = wheel._wheel_palette(theme, plain=True)
        assert plain["ink"] == ordinary["ink"]
        assert plain["bg"] == ordinary.get("face", ordinary["bg"])
        assert set(plain) == set(ordinary), "the same names, so that no drawing step finds one missing"
    # The two words of the owner's: the light plain ground is the wheel's own
    # near-white, the dark one the house's own ground with its own ink.
    assert wheel._wheel_palette("light", plain=True)["bg"] == house_style.WHEEL_PALETTES["light"]["face"] == "#FFFDF6"
    assert wheel._wheel_palette("dark", plain=True)["bg"] == house_style.WHEEL_PALETTES["dark"]["bg"]
    source = (APP_PATH.parent / "wheel.py").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9A-Fa-f]{6}\b", source), "wheel.py writes no colour; house_style holds them"


def test_the_ordinary_palettes_are_the_house_s_own():
    for theme, name in THEMES.items():
        assert wheel._wheel_palette(theme) is house_style.WHEEL_PALETTES[name]
        assert wheel._wheel_palette(theme, plain=False) is house_style.WHEEL_PALETTES[name]


# --- one ink, one ground ------------------------------------------------------

@pytest.mark.parametrize("theme", list(THEMES))
def test_a_plain_natal_wheel_is_one_ink_on_one_ground(engine, charts, theme):
    for entry in charts:
        for wide in (False, True):
            for bounds in (False, True):
                _assert_one_ink_one_ground(_natal(engine, entry, wide=wide, bounds=bounds, theme=theme, plain=True), theme)


@pytest.mark.parametrize("theme", list(THEMES))
@pytest.mark.parametrize("view", wheel.WHEEL_VIEW_OPTIONS)
def test_a_plain_timing_wheel_is_one_ink_on_one_ground(engine, charts, theme, view):
    assert set(_views(charts[0])) == set(wheel.WHEEL_VIEW_OPTIONS), "the premise: every view of the page's"
    for entry in charts:
        if entry[3]["ascendant"] is None:
            continue
        for wide in (False, True):
            _assert_one_ink_one_ground(_multi(engine, entry, view, wide=wide, theme=theme, plain=True), theme)


def test_the_charts_reach_a_withheld_status_where_a_wheel_is_drawn(charts):
    """The premise of the two above: the pole's chart withholds its division and its wheel is drawn."""
    statuses = {entry[3]["division_status"] for entry in charts}
    assert "defined" in statuses and statuses - {"defined"}, statuses


def test_a_wheel_refused_without_a_rising_sign_paints_nothing(engine, charts):
    entry = charts[0]
    refused = {**entry[3], "ascendant": None, "division_reason": "No rising sign."}
    svg = engine["generate_hybrid_svg"](refused, "x", "y", 0.0, 0.0, _moment(entry[0]), "UTC", theme="dark", plain=True)
    assert _painted(svg) == set()


# --- the geometry does not move -----------------------------------------------

@pytest.mark.parametrize("theme", list(THEMES))
def test_the_plain_drawing_is_the_ordinary_one_but_for_its_colours(engine, charts, theme):
    for entry in charts:
        for wide in (False, True):
            for bounds in (False, True):
                ordinary = _natal(engine, entry, wide=wide, bounds=bounds, theme=theme)
                plain = _natal(engine, entry, wide=wide, bounds=bounds, theme=theme, plain=True)
                assert ordinary != plain
                assert _normalised(ordinary) == _normalised(plain)
        if entry[3]["ascendant"] is None:
            continue
        for view in wheel.WHEEL_VIEW_OPTIONS:
            for wide in (False, True):
                ordinary = _multi(engine, entry, view, wide=wide, theme=theme)
                plain = _multi(engine, entry, view, wide=wide, theme=theme, plain=True)
                assert ordinary != plain
                assert _normalised(ordinary) == _normalised(plain)


# --- off is what it was -------------------------------------------------------

def _off_digest(engine, charts, theme):
    digest = hashlib.sha256()
    for entry in charts[:4]:
        for wide in (False, True):
            digest.update(_natal(engine, entry, wide=wide, bounds=True, theme=theme).encode("utf-8"))
            for view in wheel.WHEEL_VIEW_OPTIONS:
                digest.update(_multi(engine, entry, view, wide=wide, theme=theme).encode("utf-8"))
    return digest.hexdigest()


@pytest.mark.parametrize("theme", [None, "dark"])
def test_off_is_the_drawing_it_was_to_the_byte(engine, charts, theme):
    assert _off_digest(engine, charts, theme) == OFF_SHA256[theme]


# --- the Wide table's columns stand apart --------------------------------------

WIDE_PANEL_LEFT = wheel.WHEEL_SIZE + 40
WIDE_HEADING_ROW, WIDE_FIRST_ROW = 100.0, 140.0
WIDE_CLEAR_GAP = 20
WIDER_SANS_RATIO = {"bold": 1.33, "normal": 1.21}
_WIDE_TEXT = re.compile(r'<text x="([\d.]+)" y="([\d.]+)"[^>]*font-size="(\d+)" font-weight="(\w+)"[^>]*>([^<]*)</text>')


def _picture_width(text, size, weight, _faces={}):
    """A string's width at its widest: the app's interface face by the ratio Chromium gives
    where a picture falls to the system's wider sans because that face did not load. No
    browser, so that the pin runs wherever the suite does."""
    from fontTools.ttLib import TTFont

    names = ("zij-interface-600" if weight == "bold" else "zij-interface-400", "tae-symbols-400", "tae-symbols2-400", "dejavu-sans-400")
    for name in names:
        if name not in _faces:
            font = TTFont(APP_PATH.parent / "fonts" / f"{name}.ttf")
            _faces[name] = (font.getBestCmap(), font["hmtx"], font["head"].unitsPerEm)
    width = 0.0
    for character in text:
        if character == "\ufe0e":
            continue
        cmap, metrics, em = next(_faces[name] for name in names if ord(character) in _faces[name][0])
        width += metrics[cmap[ord(character)]][0] / em * size
    return width * WIDER_SANS_RATIO[weight]


def _wide_table_columns(svg):
    """{heading's x from the panel's left: (heading, right edge of the column's widest text)},
    from the heading's row to the row above the angles' heading."""
    found = [(float(x) - WIDE_PANEL_LEFT, float(y), int(size), weight, text.replace("&amp;", "&"))
             for x, y, size, weight, text in _WIDE_TEXT.findall(svg) if float(x) >= WIDE_PANEL_LEFT]
    stop = next(y for _, y, _, _, text in found if text.startswith("Angles and cusps"))
    columns = {x: [text, x + _picture_width(text, size, weight)]
               for x, y, size, weight, text in found if y == WIDE_HEADING_ROW}
    for x, y, size, weight, text in found:
        if WIDE_FIRST_ROW <= y < stop:
            column = max(place for place in columns if place <= x)
            columns[column][1] = max(columns[column][1], x + _picture_width(text, size, weight))
    return {x: tuple(entry) for x, entry in sorted(columns.items())}


def _wide_table_gaps(svg):
    columns = list(_wide_table_columns(svg).items())
    return {(left[1][0], right[1][0]): right[0] - left[1][1] for left, right in zip(columns, columns[1:])}


def _wide_natal_of_a_retrograde_chart(engine, charts):
    drawings = [_natal(engine, entry, wide=True, bounds=True) for entry in charts]
    assert any("retrograde" in svg for svg in drawings) and all("Lot of Fortune" in svg for svg in drawings), \
        "the charts carry each column's longest value"
    return drawings


def test_no_column_of_the_wide_table_runs_into_the_next(engine, charts):
    drawings = _wide_natal_of_a_retrograde_chart(engine, charts)
    for svg in drawings:
        gaps = _wide_table_gaps(svg)
        assert list(gaps) == [("Point", "Position"), ("Position", "Whole-sign place"), ("Whole-sign place", "Quadrant"), ("Quadrant", "Motion")]
        assert min(gaps.values()) >= WIDE_CLEAR_GAP, gaps
        assert max(edge for _, edge in _wide_table_columns(svg).values()) <= wheel.WHEEL_WIDE_WIDTH - WIDE_PANEL_LEFT


@pytest.mark.parametrize("old, planted", [
    (290, 330),     # the heading's collision with Quadrant
    (170, 150),     # Lot of Fortune all but touching its Position
])
def test_that_pin_refuses_a_column_set_back(engine, charts, old, planted):
    svg = _natal(engine, charts[0], wide=True, bounds=True)
    moved = svg.replace(f'<text x="{WIDE_PANEL_LEFT + old:.1f}" y="', f'<text x="{WIDE_PANEL_LEFT + planted:.1f}" y="')
    assert moved != svg
    assert min(_wide_table_gaps(svg).values()) >= WIDE_CLEAR_GAP
    assert min(_wide_table_gaps(moved).values()) < WIDE_CLEAR_GAP


def test_the_picture_width_is_chromium_s_in_the_widest_face():
    # Chromium's getBBox on a Wide natal wheel with no interface face: the widest it draws.
    measured = {("Whole-sign place", 15, "bold"): 144.8, ("Quadrant", 15, "bold"): 79.7, ("Lot of Fortune", 16, "normal"): 111.7,
                ("℞\ufe0e retrograde", 15, "normal"): 97.8, ("00° ♈\ufe0e 00′", 16, "normal"): 77.9}
    for (text, size, weight), width in measured.items():
        assert abs(_picture_width(text, size, weight) - width) <= 3, (text, _picture_width(text, size, weight))


def test_the_strips_are_not_wheels_and_take_no_plain_option(engine):
    for name in ("generate_distribution_strip_svg", "generate_hit_strip_svg"):
        assert "plain" not in engine[name].__code__.co_varnames[:engine[name].__code__.co_argcount]


# --- the page: the Options box ------------------------------------------------

def _popovers(node, found=None):
    found = [] if found is None else found
    for child in getattr(node, "children", {}).values():
        proto = getattr(child, "proto", None)
        if type(child).__name__ == "Block" and proto is not None and getattr(proto, "WhichOneof", None) \
                and proto.WhichOneof("type") == "popover":
            found.append(child)
        else:
            _popovers(child, found)
    return found


def _controls(node, found=None):
    """Every widget under a node, in the order drawn: (kind, label or key)."""
    found = [] if found is None else found
    for child in getattr(node, "children", {}).values():
        if hasattr(child, "children") and getattr(child, "children", None):
            _controls(child, found)
        elif type(child).__name__ in ("Radio", "Checkbox", "Selectbox", "Slider", "Toggle", "Button",
                                       "DownloadButton", "SegmentedControl", "Multiselect", "Number", "TextInput"):
            found.append((type(child).__name__, child.label))
        elif getattr(child, "type", None) == "download_button":
            found.append(("DownloadButton", child.proto.label))
    return found


def _fragment_of(at, kind):
    """The fragment's own block: the one holding the wheel or the heading."""
    def walk(node):
        for child in getattr(node, "children", {}).values():
            if not getattr(child, "children", None):
                continue
            kids = list(child.children.values())
            if kind == "chart" and _popovers(child) and component_mounts(child, "natal_wheel"):
                return child
            if kind == "timing" and kids and getattr(kids[0], "value", None) == "The wheel":
                return child
            found = walk(child)
            if found is not None:
                return found
        return None
    block = walk(at.main)
    assert block is not None, f"no {kind} fragment"
    return block


def test_every_control_of_the_natal_wheel_stands_in_the_box_above_the_picture():
    at = make_app(page="chart", timeout=120).run()
    assert_no_exception(at, "chart")
    fragment = _fragment_of(at, "chart")
    boxes = _popovers(fragment)
    assert len(boxes) == 1
    assert boxes[0].proto.popover.label == "Options"
    assert boxes[0].proto.popover.icon == ":material/tune:"
    assert _controls(boxes[0]) == [("Radio", "Wheel layout"), ("Checkbox", "Bounds ring"),
                                   ("DownloadButton", "Download the wheel (SVG)"), ("Radio", "Wheel look")]
    assert _controls(fragment) == _controls(boxes[0]), "no control of the wheel's outside the box"
    kids = list(fragment.children.values())
    assert kids[0] is boxes[0], "the box stands above the picture"
    assert not component_mounts(boxes[0], "natal_wheel")
    # On the page, the same four once and no other "Wheel layout" radio.
    assert [r.key for r in at.main.radio] == ["wheel_layout", "wheel_look"]
    assert [c.key for c in at.main.checkbox][0] == "chart_bounds"


def test_the_timing_box_opens_on_the_layout_and_ends_on_the_look():
    at = make_app(page="timing", timeout=180).run()
    assert_no_exception(at, "timing")
    fragment = _fragment_of(at, "timing")
    boxes = _popovers(fragment)
    assert len(boxes) == 1
    assert boxes[0].proto.popover.label == "Options"
    labels = [label for _kind, label in _controls(boxes[0])]
    assert labels == ["Wheel layout", "Inner wheel", "Bounds ring", "Lots", "Rays", "Twelfth-parts", "Wheel look"]
    outside = [control for control in _controls(fragment) if control[1] not in labels]
    assert outside == [("Selectbox", "View"), ("DownloadButton", "Download this wheel (SVG)")], outside


def test_the_look_is_one_control_in_both_boxes_with_no_help():
    source = ui_source()
    assert source.count('_reading_radio("Wheel look", WHEEL_LOOK_OPTIONS, "wheel_look", "_wheel_look")') == 2
    assert "Plain wheel" not in source and "wheel_plain" not in source


# --- the heading --------------------------------------------------------------

def test_the_heading_is_the_wheel():
    source = ui_source()
    assert "The charts, drawn" not in source
    assert 'st.subheader("The wheel",' in source
    at = make_app(page="timing", timeout=180).run()
    assert_no_exception(at, "timing")
    assert any(h.value == "The wheel" for h in at.main.subheader)
    assert all(h.value != "The charts, drawn" for h in at.main.subheader)


# --- the preference -----------------------------------------------------------

@pytest.fixture
def prefs(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    sync_engine_to_environment()
    path = tmp_path / "Zij" / "preferences.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    yield path
    monkeypatch.undo()
    sync_engine_to_environment()


def test_the_preference_is_listed_and_is_no_true_or_false(engine):
    assert "_wheel_look" in engine["PREFERENCE_KEYS"]
    assert "_wheel_look" not in engine["PREFERENCE_BOOL_KEYS"]
    assert "_wheel_plain" not in engine["PREFERENCE_KEYS"], "the box's first form, never released"


def test_the_box_stores_the_preference_and_a_new_session_reads_it(prefs):
    at = make_app(page="chart", timeout=120).run()
    assert at.radio(key="wheel_look").value == "Follow the page", "the page's by default"
    ordinary = natal_wheel_envelope(at.main)["svg"]
    at.radio(key="wheel_look").set_value("Plain").run()
    assert_no_exception(at, "on")
    assert json.loads(prefs.read_text())["_wheel_look"] == "Plain"
    drawn = natal_wheel_envelope(at.main)["svg"]
    assert drawn != ordinary
    _assert_one_ink_one_ground(drawn, None)

    again = make_app(page="chart", timeout=120).run()
    assert_no_exception(again, "a new session")
    assert again.radio(key="wheel_look").value == "Plain"
    _assert_one_ink_one_ground(natal_wheel_envelope(again.main)["svg"], None)
    # One preference, both pages: the same word opens the Timing wheel plain.
    timing = make_app(page="timing", timeout=180).run()
    assert_no_exception(timing, "timing")
    assert timing.radio(key="wheel_look").value == "Plain"


# A closed box's controls are not in the page: the browser builds each one from
# the element of the latest run when the box is first opened, and reports what it
# built on the next run, which _persist then stores. So every run's element must
# itself say the stored value. An element that said it only on the session's first
# run built at its first option after any later run: the box read false beside the
# picture, and the next click overwrote the file. The sequence itself needs a
# browser; what a browser would build from each run's element does not.
_BOX_OFF_DEFAULT = {
    "chart": {"wheel_layout": ("_wheel_layout", "Wide"), "wheel_look": ("_wheel_look", "Plain"),
              "chart_bounds": ("_chart_bounds", False)},
    "timing": {"wheel_layout": ("_wheel_layout", "Wide"), "wheel_look": ("_wheel_look", "Plain dark"),
               "wheel_order": ("_wheel_order", wheel.WHEEL_ORDER_OPTIONS[1]),
               "timing_bounds": ("_timing_bounds", False), "timing_lots": ("_timing_lots", True),
               "timing_rays": ("_timing_rays", True), "timing_twelfths": ("_timing_twelfths", True)},
}


def _what_a_browser_builds(at, key):
    radios = [r for r in at.radio if r.key == key]
    if radios:
        proto = radios[0].proto
        return proto.raw_value if proto.set_value else proto.options[proto.default]
    proto = at.checkbox(key=key).proto
    return proto.value if proto.set_value else proto.default


@pytest.mark.parametrize("page", sorted(_BOX_OFF_DEFAULT))
def test_every_run_tells_a_closed_box_the_stored_value(prefs, page):
    controls = _BOX_OFF_DEFAULT[page]
    stored = {store: value for store, value in controls.values()}
    prefs.write_text(json.dumps(stored))
    at = make_app(page=page, timeout=180)
    for run in ("first", "second", "third"):
        at.run()
        assert_no_exception(at, run)
        for key, (store, value) in controls.items():
            # A browser is told the option in the page's words; the store keeps the option.
            told = page_words(value) if isinstance(value, str) else value
            assert _what_a_browser_builds(at, key) == told, (run, key)
        kept = json.loads(prefs.read_text())
        assert {store: kept[store] for store in stored} == stored, run


def test_a_look_moved_in_the_box_is_what_the_later_runs_say(prefs):
    at = make_app(page="chart", timeout=120).run()
    at.radio(key="wheel_look").set_value("Plain dark").run()
    at.run()
    assert _what_a_browser_builds(at, "wheel_look") == "Plain dark"
    assert json.loads(prefs.read_text())["_wheel_look"] == "Plain dark"


def test_a_page_move_carries_the_stored_look_and_layout(prefs):
    prefs.write_text(json.dumps({"_wheel_look": "Plain dark", "_wheel_layout": "Wide"}))
    at = make_app(page="chart", timeout=180).run()
    at._page_hash = calc_hash("timing")
    at.run()
    assert_no_exception(at, "the page move")
    assert at.radio(key="wheel_look").value == "Plain dark"
    assert at.radio(key="wheel_layout").value == "Wide"
    assert _what_a_browser_builds(at, "wheel_look") == "Plain dark"
    kept = json.loads(prefs.read_text())
    assert (kept["_wheel_look"], kept["_wheel_layout"]) == ("Plain dark", "Wide")


def test_a_click_on_the_wheel_changes_no_stored_value_and_no_picture(prefs, monkeypatch):
    """Nothing is clicked under AppTest, so the mount answers as a click's run would.
    What this cannot show is the browser's own order of mounting: that is the pin above."""
    stored = {"_wheel_look": "Plain", "_wheel_layout": "Wide", "_chart_bounds": False}
    prefs.write_text(json.dumps(stored))
    pick, drawn, real = {"value": None}, [], st.components.v2.component

    def mount(data=None, **kwargs):
        drawn.append(data["svg"])
        return types.SimpleNamespace(picked=pick["value"])

    monkeypatch.setattr(st.components.v2, "component",
                        lambda name, **kwargs: mount if name == "natal_wheel" else real(name, **kwargs))
    at = make_app(page="chart", timeout=180).run()
    for clicked in ("sign:3", "planet:Sun", "sign:7"):
        pick["value"] = clicked
        at.run()
        assert_no_exception(at, clicked)
        assert drawn[-1] == drawn[0], clicked
        kept = json.loads(prefs.read_text())
        assert {key: kept[key] for key in stored} == stored, clicked
        assert _what_a_browser_builds(at, "wheel_look") == "Plain"
        assert _what_a_browser_builds(at, "wheel_layout") == "Wide"


def test_the_saved_wheel_follows_the_box(monkeypatch):
    handed = {}
    import streamlit as st
    real = st.download_button

    def spy(label, data=None, *args, **kwargs):
        handed[kwargs.get("key")] = data
        return real(label, data, *args, **kwargs)
    monkeypatch.setattr(st, "download_button", spy)
    at = make_app(page="chart", timeout=120).run()
    at.radio(key="wheel_look").set_value("Plain").run()
    assert_no_exception(at, "on")
    shown = natal_wheel_envelope(at.main)["svg"]
    assert handed["dl_chart_wheel"] == wheel.saved_svg(shown)
    _assert_one_ink_one_ground(shown, None)

    timing = make_app(page="timing", timeout=180)
    timing.session_state["_wheel_look"] = "Plain"
    timing.run()
    assert_no_exception(timing, "timing")
    saved = handed["dl_timing_wheel"]
    _assert_one_ink_one_ground(saved.decode() if isinstance(saved, bytes) else saved, None)


@pytest.mark.parametrize("view", wheel.WHEEL_VIEW_OPTIONS)
def test_every_timing_view_of_the_page_follows_the_box(monkeypatch, view):
    handed = {}
    import streamlit as st
    real = st.download_button

    def spy(label, data=None, *args, **kwargs):
        handed[kwargs.get("key")] = data
        return real(label, data, *args, **kwargs)
    monkeypatch.setattr(st, "download_button", spy)
    at = make_app(page="timing", timeout=180)
    at.session_state["_wheel_look"] = "Plain"
    at.session_state["_timing_lots"] = True
    at.session_state["_timing_rays"] = True
    at.session_state["_timing_twelfths"] = True
    at.session_state["_timing_wheel_view"] = view
    at.run()
    assert_no_exception(at, view)
    saved = handed["dl_timing_wheel"]
    _assert_one_ink_one_ground(saved.decode() if isinstance(saved, bytes) else saved, None)


def test_the_report_does_not_move_with_the_box():
    at = make_app(page="chart", timeout=120).run()
    first = at.session_state["_analysis_export"]
    at.radio(key="wheel_look").set_value("Plain").run()
    assert_no_exception(at, "on")
    after = at.session_state["_analysis_export"]
    assert set(after["display"]) == {"chart_bounds", "wheel_layout"}
    assert {k: v for k, v in first.items() if k != "exported"} == {k: v for k, v in after.items() if k != "exported"}
    assert "<svg" not in at.session_state["_analysis_html"].split("<style", 1)[0]


# --- the read-before-draw that fell away ---------------------------------------

def _fragment_body(name):
    source = ui_source()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(source, node)
    raise AssertionError(name)


def test_the_chart_box_draws_before_the_picture_and_reads_its_own_returns():
    body = _fragment_body("_wheel_block")
    assert 'st.session_state.get(\n            "wheel_layout"' not in body
    assert 'st.session_state.get("chart_bounds"' not in body
    assert body.index('st.popover("Options", icon=":material/tune:"') < body.index("generate_hybrid_svg(")
    assert body.count("plain=") == 2
    assert _fragment_body("_timing_wheel_block").count("plain=") == 1


# --- the wheel's place on a wide window, and the expanded wheel ------------------

def _natal_style():
    tree = ast.parse(ui_source())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "NATAL_WHEEL_CSS":
            return node.value.value
    raise AssertionError("no NATAL_WHEEL_CSS")


def test_the_page_says_what_the_window_s_height_shows():
    # The bar, the strip and their gap above and below: a picture this tall stands whole
    # under them, and the measure stands once, in the tokens' generator.
    assert "--zij-wheel-window:calc(100vh - 124px);" in house_style.PAGE_STYLE
    assert ('.st-key-wheel-column [data-testid="stFullScreenFrame"]:not(:has([aria-label="Close fullscreen"])) img{display:block;width:min(100%,var(--zij-wheel-window))!important;margin:0 auto;}') in house_style.PAGE_STYLE
    assert "width: min(100%, var(--zij-wheel-window, 100%));" in _natal_style()
    # Its expand button inside the picture's corner, off the Options button above it.
    assert ('[data-testid="stElementToolbar"]{top:0.35rem;}') in house_style.PAGE_STYLE


def test_the_expanded_wheel_s_padding_stands_inside_the_window():
    """A full width and height with the padding added ran the box a rem past
    the window, and the exit button, placed from its corner, half out of it."""
    rule = re.search(r"\.nw-wrap\.nw-full\s*\{([^{}]*)\}", _natal_style()).group(1)
    assert "box-sizing: border-box;" in rule and "padding: 0.5rem;" in rule


def test_the_timing_square_stands_in_the_page_s_content_width_and_its_row_in_the_reading_column():
    source = ui_source()
    assert 'with st.container(key="wheel-column"):' in source
    at = make_app(page="timing", timeout=180).run()
    assert_no_exception(at, "timing")
    fragment = _fragment_of(at, "timing")
    kids = list(fragment.children.values())
    assert kids[2].proto.width_config.pixel_width == 0, "no column of its own"
    assert kids[2].proto.width_config.use_stretch
    assert kids[1].proto.width_config.pixel_width == 680, "the row of View and Options above it"
    wide = make_app(page="timing", timeout=180)
    wide.session_state["_wheel_layout"] = "Wide"
    wide.run()
    assert_no_exception(wide, "timing, wide")
    assert type(list(_fragment_of(wide, "timing").children.values())[2]).__name__ == "Image"
