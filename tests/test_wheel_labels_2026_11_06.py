"""The chart wheel's labels: one circle, even and heavier glyphs, a line stopped
short of a label by an edge in the ground beneath it, and a larger hub.

Nothing here needs a browser. What a reader sees where a line meets a letter was
counted by rendered ink when the drawing was made; these hold what that count
stands on: every glyph on one circle, every line beneath every label, an edge on
every letter in the colour of the surface under it, and the rest of the picture
where it stood. Widths and ink come from the faces themselves, by fontTools.
All charts are invented.
"""
import datetime
import hashlib
import math
import random
import re
import unicodedata
import xml.etree.ElementTree as ET

import pytest

import wheel
from conftest import APP_PATH, fetches_nothing, ui_source

SVG = "{http://www.w3.org/2000/svg}"
FONTS = APP_PATH.parent / "fonts"
# The looks, as the renderer takes them: "Follow the page", "Light" and "Dark"
# draw as one of the first two, and "Plain" and "Plain dark" as the others.
LOOKS = [dict(theme=None), dict(theme="dark"), dict(theme=None, plain=True), dict(theme="dark", plain=True)]
LOOK_IDS = ["light", "dark", "plain", "plain-dark"]
POINTS = {"Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "North Node", "South Node", "Lot of Fortune"}
ANGLES = {"Ascendant", "Midheaven", "Descendant", "Imum Coeli"}
# From the rim inward: glyph, degree, sign, minute, retrograde mark.
STACK_RADII = (325, 287, 253, 223, 195)
INNER_CIRCLE = 152
MARGIN_TO_INNER_CIRCLE = 30                 # the innermost ink's least room, measured 34.7 when it was set
HUB_CIRCLE = 122
HUB_MARGIN = 6                              # by the face's advances, which run wider than its ink
LABEL_EDGE = 5
# (date and time, latitude, longitude): a seeded spread, and some crowded by hand.
CROWDED = [((1962, 2, 5, 12, 0), 22.3, 114.17), ((2020, 12, 21, 18, 22), 37.98, 23.73), ((1984, 11, 24, 4, 44), 55.75, 37.62),
           ((1503, 12, 14, 12, 0), 43.93, 4.81), ((1821, 5, 2, 6, 0), -33.9, 18.42), ((1975, 6, 21, 12, 0), 75.0, 20.0)]
_seeded = random.Random(917331)
INVENTED = CROWDED + [((_seeded.randint(1000, 2100), _seeded.randint(1, 12), _seeded.randint(1, 28), _seeded.randint(0, 23),
                        _seeded.randint(0, 59)), round(_seeded.uniform(-60, 60), 2), round(_seeded.uniform(-180, 180), 2))
                      for _ in range(54)]
# The picture with a point's letters, its glyph's edge, a leader's inner end and
# the hub taken out, before these labels were touched: every look, bounds on and
# off, square and wide, on INVENTED's first eight. Taken from the tree before them.
# A branch that redraws the rest of the wheel on purpose retakes them.
SKELETON_SHA256 = "98a086bebfc496984a5ab7b27a1269c7c8bc1fb588a700dd2c68182f7b9ae924"
# The Timing wheels, fonts aside, before these labels were touched: nothing here reaches them.
TIMING_SHA256 = "2561fcca03d888cec0abfb45e22561a3aea0893e7ede6128e44eaf7d311f8643"


@pytest.fixture(scope="module")
def charts(engine):
    return [(when, lat, lon, engine["calculate_traditional_chart"](datetime.datetime(*when), lat, lon))
            for when, lat, lon in INVENTED]


def _natal(engine, entry, name="Invented", place="Nowhere", zone="UTC", **kw):
    when, lat, lon, chart = entry
    return engine["generate_hybrid_svg"](chart, name, place, lat, lon, datetime.datetime(*when), zone, **kw)


def _xy(element):
    return float(element.get("x")), float(element.get("y"))


def _radius(x, y):
    return math.hypot(x - 500, y - 500)


def _bearing(x, y):
    return math.degrees(math.atan2(500 - y, x - 500)) % 360


def _gap(a, b):
    return abs((a - b + 180) % 360 - 180)


def _labels(root):
    """{point: its <g class="pt"> of letters}; an angle's box is on the sign band and no label."""
    return {g.get("data-point"): g for g in root.iter(SVG + "g") if g.get("class") == "pt" and g.get("data-point") in POINTS}


def _true_bearing(chart, longitude):
    """Where a longitude stands, from the rising sign's boundary at 9 o'clock, counter-clockwise."""
    return (longitude - (chart["ascendant"] % 360 // 30) * 30 + 180) % 360


def _longitudes(chart):
    data = chart["planetary_data"]
    out = {name: row["longitude"] % 360 for name, row in data.items()}
    out["South Node"] = (data["North Node"]["longitude"] + 180) % 360
    out["Lot of Fortune"] = chart["lot_of_fortune"] % 360
    return out


def _hub(root):
    return [t for t in root.iter(SVG + "text") if float(t.get("x")) <= 1000 and _radius(*_xy(t)) < HUB_CIRCLE]


# --- the faces, read from the files ----------------------------------------------

_FACES = {}


def _face(name):
    from fontTools.ttLib import TTFont
    if name not in _FACES:
        font = TTFont(FONTS / f"{name}.ttf")
        _FACES[name] = (font, font.getBestCmap(), font["hmtx"], font["head"].unitsPerEm, font.getGlyphSet())
    return _FACES[name]


def _width(words, px, weight):
    """Its advance in the face the page and the saved picture draw it in, with the wheel's own fallbacks."""
    names = ("zij-interface-600" if weight == "bold" else "zij-interface-400", "tae-symbols-400", "tae-symbols2-400",
             "dejavu-sans-400")
    total = 0.0
    for character in words:
        if character in "\ufe0e\ufe0f\u2066\u2067\u2068\u2069":
            continue
        for name in names:
            _font, cmap, hmtx, upem, _glyphs = _face(name)
            if ord(character) in cmap:
                total += hmtx[cmap[ord(character)]][0] / upem * px
                break
        else:
            raise AssertionError(f"no face holds {character!r}")
    return total


def _hub_width(words, px, weight):
    """_width, going round a letter none of these faces holds, which the computer's
    own face sets: its expansion if it has one, else 1 em where it is full width and
    0.6 elsewhere, a plain figure from outside the wheel's own table."""
    total = 0.0
    for character in words:
        try:
            total += _width(character, px, weight)
        except AssertionError:
            expansion = unicodedata.normalize("NFKC", character)
            if expansion != character:
                total += _hub_width(expansion, px, weight)
            else:
                total += px * (1.0 if unicodedata.east_asian_width(character) in ("W", "F") else 0.6)
    return total


def _ink_bounds(character):
    """(x0, y0, x1, y1) of a symbol's ink, in ems above its baseline."""
    from fontTools.pens.boundsPen import BoundsPen
    for name in ("tae-symbols-400", "tae-symbols2-400", "dejavu-sans-400"):
        _font, cmap, _hmtx, upem, glyphs = _face(name)
        if ord(character) in cmap:
            pen = BoundsPen(glyphs)
            glyphs[cmap[ord(character)]].draw(pen)
            return tuple(value / upem for value in pen.bounds)
    raise AssertionError(f"no symbol face holds {character!r}")


def _ink(character, px):
    """(width, height) of a symbol's ink, at this size."""
    x0, y0, x1, y1 = _ink_bounds(character)
    return (x1 - x0) * px, (y1 - y0) * px


# --- nothing moved ------------------------------------------------------------------

def _skeleton(svg):
    """The picture without what these labels may touch, as text: a point's letters,
    a glyph's edge, a leader's inner end and the hub go; wrappers and handles go,
    since ticks and leaders left their groups; ticks and leaders are sorted, since
    they went down first. Everything else stays, in order, to the byte."""
    root = ET.fromstring(svg)
    ordered, lines = [], []

    def canon(element):
        drop = {"data-point", "class"} if element.tag == SVG + "line" else set()
        attributes = sorted((k, v) for k, v in element.attrib.items() if k not in drop)
        return f"{element.tag.rsplit('}', 1)[-1]} {attributes} {element.text or ''}"

    def walk(element):
        for child in element:
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "style" or child.get("class") == "edge":
                continue
            if tag == "g" and child.get("data-point") in POINTS:
                walk_point(child)
                continue
            if tag == "line" and child.get("data-point") in POINTS:
                seen.setdefault(child.get("data-point"), []).append(child)
                continue
            if tag == "text" and float(child.get("x")) <= 1000 and _radius(*_xy(child)) < HUB_CIRCLE:
                continue
            ordered.append(canon(child))
            walk(child)

    def walk_point(group):
        for child in group:
            if child.tag == SVG + "line":
                seen.setdefault(group.get("data-point"), []).append(child)

    seen = {}
    walk(root)
    for pair in seen.values():
        assert len(pair) == 2
        tick, leader = pair
        lines.append(canon(tick))
        lines.append(f"leader {leader.get('x1')} {leader.get('y1')} {leader.get('stroke')} {leader.get('stroke-width')}")
    return "\n".join(ordered + sorted(lines))


def _skeleton_digest(engine, charts):
    digest = hashlib.sha256()
    for entry in charts[:8]:
        for look in LOOKS:
            for bounds in (False, True):
                for wide in (False, True):
                    digest.update(_skeleton(_natal(engine, entry, bounds=bounds, wide=wide, **look)).encode("utf-8"))
    return digest.hexdigest()


def _timing_digest(engine, charts):
    digest = hashlib.sha256()
    for entry in charts[:8]:
        chart = entry[3]
        rings = [{"label": "Nativity", "chart": chart, "when": "birth"}, {"label": "Year", "chart": chart, "when": "year"}]
        for look in LOOKS:
            for count in (1, 2):
                svg = engine["generate_multiwheel_svg"](rings[:count], "Invented", bounds=True, **look)
                digest.update(re.sub(r"<style>.*?</style>", "", svg, flags=re.S).encode("utf-8"))
    return digest.hexdigest()


def test_the_rest_of_the_picture_stands_where_it_stood(engine, charts):
    assert _skeleton_digest(engine, charts) == SKELETON_SHA256


def test_the_timing_wheels_are_the_drawing_they_were(engine, charts):
    assert _timing_digest(engine, charts) == TIMING_SHA256


def test_a_timing_wheel_keeps_its_stagger_and_its_even_sized_glyphs(engine, charts):
    """One circle and the glyph table are the chart wheel's alone: a lone ring still
    steps a crowd inward, and draws every glyph at the ring's one size, with no weight."""
    stepped = 0
    for entry in charts[:6]:
        root = ET.fromstring(engine["generate_multiwheel_svg"]([{"label": "Nativity", "chart": entry[3], "when": "birth"}], "Invented"))
        glyphs = [next(g.iter(SVG + "text")) for g in root.iter(SVG + "g")
                  if g.get("class") == "pt" and g.get("data-ring") is not None and g.get("data-point") in POINTS]
        assert len(glyphs) == len(POINTS)
        assert len({g.get("font-size") for g in glyphs}) == 1
        assert all(g.get("stroke") is None for g in glyphs)
        stepped += len({round(_radius(*_xy(g))) for g in glyphs}) > 1
    assert stepped, "the crowded charts reach the stagger"


@pytest.mark.parametrize("bounds", [False, True], ids=["plain-ring", "bounds"])
def test_each_tick_stands_at_its_true_degree_and_its_leader_starts_there(engine, charts, bounds):
    edge = 402 - (24 if bounds else 0)
    palette = wheel._wheel_palette(None)
    for entry in charts:
        chart = entry[3]
        root = ET.fromstring(_natal(engine, entry, bounds=bounds))
        lines = {}
        for element in root.iter(SVG + "line"):
            if element.get("data-point"):
                lines.setdefault(element.get("data-point"), []).append(element)
        assert set(lines) == POINTS, "every point has its lines, each with a handle"
        for name, longitude in _longitudes(chart).items():
            assert len(lines[name]) == 2, name
            tick, leader = lines[name]
            bearing = _true_bearing(chart, longitude)
            t = math.radians(bearing)
            outer = (500 + edge * math.cos(t), 500 - edge * math.sin(t))
            inner = (500 + (edge - 10) * math.cos(t), 500 - (edge - 10) * math.sin(t))
            assert (float(tick.get("x1")), float(tick.get("y1"))) == pytest.approx(outer, abs=0.06), name
            assert (float(tick.get("x2")), float(tick.get("y2"))) == pytest.approx(inner, abs=0.06), name
            assert tick.get("stroke") == palette["rule"] and tick.get("stroke-width") == "1.6" and tick.get("class") is None
            assert leader.get("stroke") == palette["leader"] and leader.get("class") == "leader" and leader.get("stroke-width") == "0.8"
            assert (leader.get("x1"), leader.get("y1")) == (tick.get("x2"), tick.get("y2")), name
            # Its other end comes to the glyph it names, just outside it.
            label = _labels(root)[name]
            glyph_bearing = _bearing(*_xy(next(iter(label))))
            end = (float(leader.get("x2")), float(leader.get("y2")))
            assert _radius(*end) == pytest.approx(STACK_RADII[0] + 22, abs=0.1), name
            assert _gap(_bearing(*end), glyph_bearing) < 0.5, name


def test_every_cusp_stands_at_its_true_degree(engine, charts):
    for entry in charts:
        chart = entry[3]
        spokes = [e for e in ET.fromstring(_natal(engine, entry)).iter(SVG + "line")
                  if not e.get("data-point") and _radius(float(e.get("x1")), float(e.get("y1"))) == pytest.approx(HUB_CIRCLE, abs=0.1)]
        assert len(spokes) == 12
        for spoke, cusp in zip(spokes, chart["houses"]):
            assert _radius(float(spoke.get("x2")), float(spoke.get("y2"))) == pytest.approx(402, abs=0.1)
            for x, y in (("x1", "y1"), ("x2", "y2")):
                assert _gap(_bearing(float(spoke.get(x)), float(spoke.get(y))), _true_bearing(chart, cusp)) < 0.1


@pytest.mark.parametrize("ring", [0, 19, 38])
def test_the_ring_moves_a_stack_and_a_leader_s_inner_end_and_nothing_else(engine, charts, monkeypatch, ring):
    """Move every stack radius by a number no drawing uses, and all else stays to the byte."""
    settled = [_skeleton(_natal(engine, entry, bounds=True)) for entry in charts[:6]]
    glyphs = [{n: _xy(next(iter(g))) for n, g in _labels(ET.fromstring(_natal(engine, entry, bounds=True))).items()}
              for entry in charts[:6]]
    for name, radius in zip(("_R_GLYPH", "_R_DEG", "_R_SIGN", "_R_MIN", "_R_RX"), STACK_RADII):
        monkeypatch.setattr(wheel, name, radius + 19 - ring + 3)
    moved = [_skeleton(_natal(engine, entry, bounds=True)) for entry in charts[:6]]
    assert moved == settled
    after = [{n: _xy(next(iter(g))) for n, g in _labels(ET.fromstring(_natal(engine, entry, bounds=True))).items()}
             for entry in charts[:6]]
    assert after != glyphs, "the premise: the stacks do read these radii"


# --- one circle ----------------------------------------------------------------------

def test_every_stack_stands_on_its_one_radius_along_one_bearing(engine, charts):
    """No stagger: the same five radii on every chart, and a crowd met along the circle."""
    for entry in charts:
        chart = entry[3]
        for bounds in (False, True):
            labels = _labels(ET.fromstring(_natal(engine, entry, bounds=bounds)))
            assert set(labels) == POINTS
            true = sorted(_true_bearing(chart, longitude) for longitude in _longitudes(chart).values())
            shown = sorted(_bearing(*_xy(next(iter(group)))) for group in labels.values())
            # the glyph's y carries its own nudge, under 3: a tenth of a degree or so at this radius.
            spread = sorted(a % 360 for a in wheel._spread_labels(true))
            assert all(_gap(a, b) < 0.6 for a, b in zip(shown, spread)), (shown, spread)
            for name, group in labels.items():
                letters = list(group)
                assert len(letters) in (4, 5), name
                bearing = _bearing(*_xy(letters[1]))
                for element, radius in zip(letters[1:], STACK_RADII[1:]):
                    assert _radius(*_xy(element)) == pytest.approx(radius, abs=0.1), (name, element.text)
                    assert _gap(_bearing(*_xy(element)), bearing) < 0.05, (name, element.text)
                glyph_at = _xy(letters[0])
                factor, _weight, nudge = wheel._GLYPH_SET[name]
                assert _radius(glyph_at[0], glyph_at[1] - nudge) == pytest.approx(STACK_RADII[0], abs=0.1), name


def test_the_innermost_ink_clears_the_inner_circle(engine, charts):
    width, height = _ink("℞", 15)
    reach = math.hypot(width, height) / 2
    assert wheel._R_RX - reach - (wheel._R_Q_OUT + 0.6) >= MARGIN_TO_INNER_CIRCLE
    assert any("℞\ufe0f" in "".join(t.text or "" for t in g) or "℞" in "".join(t.text or "" for t in g)
               for entry in charts for g in _labels(ET.fromstring(_natal(engine, entry))).values()), \
        "the premise: these charts reach a retrograde mark"
    # And the mark stands there on the drawing, not only in this file's table.
    marks = [_radius(*_xy(t)) for entry in charts for g in _labels(ET.fromstring(_natal(engine, entry))).values()
             for t in g if (t.text or "").startswith("℞")]
    assert marks and max(marks) == pytest.approx(STACK_RADII[4], abs=0.1) and min(marks) == pytest.approx(STACK_RADII[4], abs=0.1)


def test_no_stack_reaches_its_neighbour_s(engine, charts):
    """Text on text, by the face's widths: at each radius the wider of two neighbours'
    letters, edge and all, fits the chord between them. The count that stood on rendered
    ink was 0 at every threshold; this fails first if the ring or the spread closes up."""
    assert wheel.LABEL_MIN_SEP >= 10.5
    for entry in charts:
        labels = _labels(ET.fromstring(_natal(engine, entry)))
        bearings = sorted((_bearing(*_xy(list(g)[1])), n) for n, g in labels.items())
        for (a, first), (b, second) in zip(bearings, bearings[1:] + bearings[:1]):
            gap = _gap(a, b)
            assert gap >= wheel.LABEL_MIN_SEP - 0.05, (first, second, gap)
            for row, radius in zip(range(1, 5), STACK_RADII[1:]):
                chord = 2 * radius * math.sin(math.radians(gap) / 2)
                wide = []
                for name in (first, second):
                    letters = list(labels[name])
                    if row < len(letters):
                        element = letters[row]
                        wide.append(_width(element.text, float(element.get("font-size")), element.get("font-weight")))
                if len(wide) == 2:
                    assert sum(wide) / 2 + LABEL_EDGE < chord, (first, second, row, wide, chord)


# --- the label's own text -------------------------------------------------------------

def test_a_label_says_and_sizes_what_it_did(engine, charts):
    """Degrees, sign, minutes and mark: their words, sizes, weight and ink are as they were. Only the edge is added."""
    for entry in charts:
        chart = entry[3]
        labels = _labels(ET.fromstring(_natal(engine, entry)))
        for name, longitude in _longitudes(chart).items():
            letters = list(labels[name])
            degree, minute = wheel._wheel_dm(longitude)
            assert letters[1].text == f"{degree:02d}°" and letters[1].get("font-size") == "18" and letters[1].get("font-weight") == "bold"
            assert letters[2].text == wheel.SIGN_GLYPHS[wheel._wheel_sign(longitude)] + wheel._VS and letters[2].get("font-size") == "19"
            assert letters[3].text == f"{minute:02d}'" and letters[3].get("font-size") == "15"
            data = chart["planetary_data"]
            speed = {"South Node": data["North Node"].get("speed_in_lon")}.get(name, data.get(name, {}).get("speed_in_lon"))
            retrograde = speed is not None and name != "Lot of Fortune" and engine["motion_state"](name, speed) == "retrograde"
            assert (len(letters) == 5) == retrograde, name
            if retrograde:
                assert letters[4].text == "℞" + wheel._VS and letters[4].get("font-size") == "15"
            for element in letters[2:]:
                assert element.get("font-weight") == "normal"


def test_everything_off_the_labels_and_hub_carries_no_stroke_of_theirs(engine, charts):
    """The words of the picture that are no label's or hub's have no edge, no weight added."""
    for entry in charts[:8]:
        for look in LOOKS:
            root = ET.fromstring(_natal(engine, entry, bounds=True, wide=True, **look))
            labelled = {id(t) for g in _labels(root).values() for t in g}
            for element in root.iter(SVG + "text"):
                if id(element) in labelled or element.get("class") == "edge":
                    continue
                assert element.get("stroke") is None and element.get("paint-order") is None, element.attrib


def test_the_two_new_attributes_stand_on_a_natal_label_alone(engine, charts):
    """What the attribute list let in: paint-order only as "stroke", the join only as
    "round", each only on a <text>, and neither anywhere on a Timing wheel of one, two
    or three rings, or on either strip."""
    segments = [{"from": 0.0, "to": 50.0, "distributor": "Mars", "partner": "Venus", "partner_aspect": "trine"},
                {"from": 50.0, "to": 120.0, "distributor": "Sun", "partner": "Jupiter", "partner_aspect": None}]
    hits = [{"Target": "Saturn's body", "Arc (years)": 10.5}, {"Target": "Mars's square", "Arc (years)": "33.00"}]
    for entry in charts[:8]:
        for look in LOOKS:
            root = ET.fromstring(_natal(engine, entry, **look))
            carried = 0
            for element in root.iter():
                if element.get("paint-order") is not None or element.get("stroke-linejoin") is not None:
                    carried += 1
                    assert element.tag == SVG + "text", element.tag
                    assert element.get("paint-order") == "stroke" and element.get("stroke-linejoin") == "round", element.attrib
            assert carried > 40
            rings = [{"label": label, "chart": entry[3], "when": "then"} for label in ("Nativity", "Year", "Month")]
            for count in (1, 2, 3):
                multi = engine["generate_multiwheel_svg"](rings[:count], "Invented", **look)
                assert "paint-order" not in multi and "stroke-linejoin" not in multi and 'class="edge"' not in multi, count
            theme = look.get("theme")
            for strip in (engine["generate_distribution_strip_svg"](segments, 10.0, "years", 120.0, "A strip", theme=theme),
                          engine["generate_hit_strip_svg"](hits, 10.0, 120.0, "A strip", theme=theme)):
                assert "data-" in strip, "the premise: a strip was drawn"
                assert "paint-order" not in strip and "stroke-linejoin" not in strip and 'class="edge"' not in strip


# --- the glyphs ----------------------------------------------------------------------

def test_a_table_entry_for_every_glyph_and_none_left_over(engine):
    assert set(wheel._GLYPH_SET) == POINTS, "a point with no entry would draw at the old size with no weight"
    assert set(engine["POINT_GLYPHS"]) >= POINTS


def test_the_glyphs_are_about_one_size(engine):
    """Each one's ink, by its own face, within a few units of the others'. Without the
    table they run from Mars's 18 to Mercury's 27.5."""
    sizes = {}
    for name in POINTS:
        factor = wheel._GLYPH_SET[name][0]
        sizes[name] = _ink(engine["POINT_GLYPHS"][name], wheel._GLYPH_PX * factor)
    tall = {name: max(size) for name, size in sizes.items()}
    assert all(22.5 <= side <= 28 for side in tall.values()), tall
    assert max(tall.values()) - min(tall.values()) <= 4.5, tall
    bare = {name: max(_ink(engine["POINT_GLYPHS"][name], 34)) for name in POINTS}
    assert max(bare.values()) - min(bare.values()) > max(tall.values()) - min(tall.values()), "the premise: the table evens them"


def test_no_glyph_s_stroke_runs_past_about_one():
    """Heavier, not swollen: a stroke of the table's is at most 1, whatever the table says of itself."""
    for name, (_factor, stroke, _nudge) in wheel._GLYPH_SET.items():
        assert 0 <= stroke <= 1, name


def test_each_glyph_s_ink_stands_at_the_circle_by_its_own_face(engine):
    """Where the ink's middle falls, from the faces and not from the table. The text is
    set on the central line of the stack's first face to hold a space, the interface
    face (the symbol faces hold only their symbols), so its middle stands that line
    less its own middle below the y, plus the nudge. A browser's rendering read the
    same to within 0.25.

    2.5 and 1.5, in the picture's units: at most a tenth of a glyph's ink, some 25 tall,
    from the circle, and closer than that to one another, since an even row is what
    the nudges are for. They stand 1.0 to 2.3 below it; without the nudges they run
    nearly 5 apart."""
    _font = _face("zij-interface-400")[0]
    central = (_font["hhea"].ascent + _font["hhea"].descent) / 2 / _font["head"].unitsPerEm
    below, bare = {}, {}
    for name, (factor, _stroke, nudge) in wheel._GLYPH_SET.items():
        _x0, y0, _x1, y1 = _ink_bounds(engine["POINT_GLYPHS"][name])
        px = round(wheel._GLYPH_PX * factor, 1)
        bare[name] = (central - (y0 + y1) / 2) * px
        below[name] = bare[name] + nudge
    assert all(abs(distance) <= 2.5 for distance in below.values()), below
    assert max(below.values()) - min(below.values()) <= 1.5, below
    assert max(bare.values()) - min(bare.values()) > 4, "the premise: the nudges bring them together"


@pytest.mark.parametrize("look", LOOKS, ids=LOOK_IDS)
def test_a_glyph_is_drawn_at_its_size_with_a_stroke_in_its_own_ink(engine, charts, look):
    palette = wheel._wheel_palette(look.get("theme"), look.get("plain", False))
    for entry in charts[:12]:
        labels = _labels(ET.fromstring(_natal(engine, entry, **look)))
        for name, group in labels.items():
            glyph = next(iter(group))
            factor, weight, _nudge = wheel._GLYPH_SET[name]
            assert glyph.text == engine["POINT_GLYPHS"][name] + wheel._VS
            assert float(glyph.get("font-size")) == pytest.approx(round(34 * factor, 1))
            assert glyph.get("fill") == palette["ink"]
            if weight:
                assert glyph.get("stroke") == palette["ink"] and float(glyph.get("stroke-width")) == pytest.approx(weight)
            else:
                assert glyph.get("stroke") is None


# --- the edge -------------------------------------------------------------------------

def _beneath(root, x, y):
    """The fill of the last surface drawn under this spot, before the first edge. A
    sector is taken as its whole annulus, so that it errs towards finding a tint."""
    top = None
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if element.get("class") == "edge":
            break
        fill = element.get("fill")
        if tag not in ("rect", "circle", "path") or fill in (None, "none"):
            continue
        if tag == "rect":
            left, up = float(element.get("x", 0)), float(element.get("y", 0))
            inside = left <= x <= left + float(element.get("width")) and up <= y <= up + float(element.get("height"))
        elif tag == "circle":
            inside = _radius(x, y) <= float(element.get("r"))
        else:
            numbers = [float(n) for n in re.findall(r"-?\d+\.?\d*", re.sub(r"A[\d.]+,[\d.]+ \d+ \d+ \d+ ", "L", element.get("d")))]
            radii = [_radius(a, b) for a, b in zip(numbers[::2], numbers[1::2])]
            inside = min(radii) - 1 <= _radius(x, y) <= max(radii) + 1
        if inside:
            top = fill
    return top


@pytest.mark.parametrize("look", LOOKS, ids=LOOK_IDS)
@pytest.mark.parametrize("bounds", [False, True], ids=["plain-ring", "bounds"])
def test_each_letter_has_an_edge_in_the_colour_beneath_it(engine, charts, look, bounds):
    """A label takes the surface it stands on: found by walking what is drawn under it, never from the palette."""
    for entry in charts[:12]:
        root = ET.fromstring(_natal(engine, entry, bounds=bounds, **look))
        edges = [t for t in root.iter(SVG + "text") if t.get("class") == "edge"]
        labels = _labels(root)
        assert len(edges) == len(POINTS)
        by_place = {_xy(e): e for e in edges}
        for name, group in labels.items():
            letters = list(group)
            glyph = letters[0]
            edge = by_place[_xy(glyph)]
            beneath = _beneath(root, *_xy(glyph))
            assert beneath is not None
            assert edge.get("stroke") == beneath and edge.get("fill") == beneath, name
            assert (edge.text, edge.get("font-size")) == (glyph.text, glyph.get("font-size")), name
            assert edge.get("paint-order") == "stroke"
            assert float(edge.get("stroke-width")) == pytest.approx(wheel._GLYPH_SET[name][1] + LABEL_EDGE), name
            for element in letters[1:]:
                assert element.get("stroke") == _beneath(root, *_xy(element)), (name, element.text)
                assert element.get("paint-order") == "stroke", (name, element.text)
                assert float(element.get("stroke-width")) == LABEL_EDGE, (name, element.text)
                assert element.get("fill") != element.get("stroke"), "an edge in the ink would be a heavier letter"


@pytest.mark.parametrize("bounds", [False, True], ids=["plain-ring", "bounds"])
def test_no_line_is_drawn_over_a_label(engine, charts, bounds):
    """Every line, spoke, tick and leader goes down first, then the glyphs' edges,
    then the letters: a line can only meet a label under its edge."""
    for entry in charts:
        root = ET.fromstring(_natal(engine, entry, bounds=bounds, wide=True))
        order = [e for e in root.iter()]
        first_edge = next(k for k, e in enumerate(order) if e.get("class") == "edge")
        last_edge = max(k for k, e in enumerate(order) if e.get("class") == "edge")
        letters = {id(t) for g in _labels(root).values() for t in g}
        first_letter = next(k for k, e in enumerate(order) if id(e) in letters)
        assert last_edge < first_letter, "a glyph's edge over another's letters eats them"
        for element in order[first_edge:]:
            tag = element.tag.rsplit("}", 1)[-1]
            if tag == "circle" and float(element.get("r")) < INNER_CIRCLE:
                continue                                   # the hub's own disc, well inside every label
            if tag in ("line", "path", "polygon", "circle"):
                x = float(element.get("x1", element.get("cx", 1001)))
                assert x > 1000, f"a {tag} over the labels: {element.attrib}"
            assert not (tag == "g" and element.get("class") == "pt" and element.get("data-point") in ANGLES)


# --- the handles ----------------------------------------------------------------------

def test_a_tick_and_a_leader_are_handles_to_their_point(engine, charts):
    """They left their groups, so each carries the point's own name; a click on
    either reaches the listener on every [data-point], which is what the page mounts."""
    source = ui_source()
    assert 'holder.querySelectorAll("[data-point]")' in source
    assert ".nw-svg [data-point], .nw-svg [data-sign] { cursor: pointer; }" in source
    for entry in charts[:12]:
        root = ET.fromstring(_natal(engine, entry))
        names = [e.get("data-point") for e in root.iter(SVG + "line") if e.get("data-point")]
        assert sorted(names) == sorted(list(POINTS) * 2)
        groups = [g.get("data-point") for g in root.iter(SVG + "g") if g.get("class") == "pt"]
        assert sorted(groups) == sorted(POINTS | ANGLES), "one group a point, its letters"
        assert all(e.get("data-point") is None for e in root.iter(SVG + "text") if e.get("class") == "edge")


# --- the hub -----------------------------------------------------------------------------

LONG_NAMES = ["Wolfeschlegelsteinhausenbergerdorff the Younger", "Anastasia Konstantinovna Rimskaya-Korsakova", "WWWWWWWWWWWWWWWWWWWWWWWWWWWWWW",
              "Ō", "Maria da Conceição de Sá e Silva"]
LONG_PLACES = ["Llanfairpwllgwyngyllgogerychwyrndrobwllllantysiliogogogoch, Wales, United Kingdom",
               "Taumatawhakatangihangakoauauotamateaturipukakapikimaungahoronukupokaiwhenuakitanatahu, New Zealand",
               "San José de las Lajas, Mayabeque, Cuba", "A", "Saint-Rémy-de-Provence, Bouches-du-Rhône, Provence-Alpes-Côte d'Azur, France"]
LONG_ZONES = ["America/Argentina/ComodRivadavia", "America/North_Dakota/New_Salem", "UTC", "LMT", "America/Indiana/Tell_City / Etc/GMT+10 by the local clock"]
# Letters none of the faces here holds: full width, Arabic, and one code point that is a whole phrase.
NON_LATIN_NAMES = ["東" * 40, "東京 " * 14, "سلام " * 12, "\ufdfa" * 6]
NON_LATIN_PLACES = ["東" * 80, "سلام " * 20, "\ufdfa" * 8]
HUB_CASES = ([(name, place, zone) for name in LONG_NAMES for place in LONG_PLACES for zone in LONG_ZONES]
             + [(name, place, zone) for name in NON_LATIN_NAMES for place in NON_LATIN_PLACES for zone in ("UTC", LONG_ZONES[-1])])


def _reach(element):
    x, y = _xy(element)
    half = _hub_width(element.text, float(element.get("font-size")), element.get("font-weight")) / 2
    return math.hypot(half, abs(y - 500) + float(element.get("font-size")) * 0.55)


def test_an_ordinary_hub_stands_at_the_sizes_reached(engine, charts):
    root = ET.fromstring(_natal(engine, charts[6], name="Ana Silva", place="Invented place", zone="Europe/Paris"))
    rows = _hub(root)
    assert len(rows) == 8, "eight lines and no more"
    assert [t.get("font-size") for t in rows[:6]] == ["24", "19", "18", "19", "18", "19"]
    # The two systems lines start at 17 and step down on the chord left to them at the foot.
    assert all(t.get("font-size") in ("16", "17") for t in rows[6:])
    assert [t.get("font-weight") for t in rows] == ["bold", "normal", "normal", "normal", "normal", "bold", "normal", "normal"]
    ys = [_xy(t)[1] for t in rows]
    # No two lines touch: each stands at least its own size below the last, and the pitch was 14.
    assert all(b - a >= max(14, float(t.get("font-size"))) for a, b, t in zip(ys, ys[1:], rows[1:]))


def test_the_hub_keeps_its_words_and_their_order(engine, charts):
    entry = charts[6]
    when = datetime.datetime(*entry[0])
    rows = [t.text for t in _hub(ET.fromstring(_natal(engine, entry, name="Ana", place="Fes", zone="Africa/Casablanca")))]
    assert rows[0] == "Ana" and rows[2] == "Africa/Casablanca" and rows[3] == "Fes"
    assert rows[1] == f"{when.day} {when:%b} {when.year}  {when:%H:%M}"
    assert re.fullmatch(r"\d+°\d\d′[NS]  \d+°\d\d′[EW]", rows[4])
    assert rows[5] == entry[3]["sect"]
    assert rows[6:] == ["Whole sign · Alchabitius", "Tropical · True node"]
    # The circle's own place: the two rings are as they were.
    circles = [float(c.get("r")) for c in ET.fromstring(_natal(engine, entry)).iter(SVG + "circle") if c.get("fill") == "none"]
    assert INNER_CIRCLE in circles and HUB_CIRCLE in circles


@pytest.mark.parametrize("name, place, zone", HUB_CASES)
def test_every_line_stays_inside_the_circle(engine, charts, name, place, zone):
    for entry in (charts[0], charts[5]):
        rows = _hub(ET.fromstring(_natal(engine, entry, name=name, place=place, zone=zone)))
        for row in rows:
            assert _reach(row) <= HUB_CIRCLE - HUB_MARGIN, (row.text, row.get("font-size"), _reach(row))
            assert float(row.get("font-size")) >= 10
        # However long the reader's own lines, the program's are whole.
        assert [row.text for row in rows[-2:]] == ["Whole sign · Alchabitius", "Tropical · True node"]
        assert rows[-3].text == entry[3]["sect"]


@pytest.mark.parametrize("weight", ["normal", "bold"])
def test_the_rough_width_of_letters_no_face_here_holds(weight):
    """By their kinds: a full-width letter a whole em, any other letter past the Latin
    ones 0.66, and a code point that is a whole phrase by what it expands to."""
    assert wheel._hub_em("東" * 10, weight) >= 10
    arabic = "سلام" * 3
    assert wheel._hub_em(arabic, weight) >= 0.66 * len(arabic)
    letters = unicodedata.normalize("NFKC", "\ufdfa").replace(" ", "")
    assert len(letters) == 15, "the premise: it expands"
    assert wheel._hub_em("\ufdfa", weight) >= 0.66 * len(letters)


def test_the_rough_width_is_never_below_the_face_s():
    """What stops a line at the circle is _hub_em: it runs over the page's face, for any letters here."""
    words = LONG_NAMES + LONG_PLACES + LONG_ZONES + ["The quick brown fox jumps over the lazy dog", "0123456789°′·", "ÀÉÎÕÜçñßøå"]
    for line in words:
        for weight in ("normal", "bold"):
            assert wheel._hub_em(line, weight) * 100 >= _width(line, 100, weight), (line, weight)


def test_a_short_line_keeps_every_letter_and_only_a_long_one_is_cut(engine, charts):
    lines = lambda name, place, zone: [(name, 24, "bold", True), ("1 Jan 2000  12:00", 19, "normal", False), (zone, 18, "normal", True),
                                       (place, 19, "normal", True), ("40°00′N  3°00′W", 18, "normal", False), ("Diurnal", 19, "bold", False),
                                       ("Whole sign · Alchabitius", 17, "normal", False), ("Tropical · True node", 17, "normal", False)]
    rows = wheel._hub_rows(lines("Ana Silva", "Fes, Morocco", "Africa/Casablanca"))
    assert [r[0] for r in rows] == [line[0] for line in lines("Ana Silva", "Fes, Morocco", "Africa/Casablanca")]
    # A long place steps down, then takes two lines, broken at a space or a comma, none of its letters lost.
    middling = "San José de las Lajas, Mayabeque, Cuba"
    rows = wheel._hub_rows(lines("Ana Silva", middling, "Africa/Casablanca"))
    placed = [r for r in rows if r[4] == 3]
    assert " ".join(r[0] for r in placed).replace(",  ", ", ") == middling
    assert not any("…" in r[0] for r in rows)
    assert [r[1] for r in placed] == [14, 14], "the size a wrapped line takes"
    # Every line of a long one stays at or over the floor, and a cut is marked as a cut.
    huge = "Taumatawhakatangihangakoauauotamateaturipukakapikimaungahoronukupokaiwhenuakitanatahu, New Zealand"
    rows = wheel._hub_rows(lines("Ana Silva", huge, "Africa/Casablanca"))
    placed = [r for r in rows if r[4] == 3]
    assert len(placed) == 2 and all(r[1] >= wheel._HUB_FLOOR_PX for r in placed)
    assert any(r[0].endswith("…") for r in placed), "the premise: this one is cut"
    # The lines that are not the reader's own are never cut or split.
    assert [r[0] for r in rows if r[4] in (1, 4, 5, 6, 7)] == ["1 Jan 2000  12:00", "40°00′N  3°00′W", "Diurnal", "Whole sign · Alchabitius", "Tropical · True node"]
    # A name keeps 30 letters; one more and it is cut to 29 and the mark.
    named = {}
    for letters in (30, 31):
        drawn = [t.text.strip("\u2066\u2067\u2068\u2069") for t in _hub(ET.fromstring(_natal(engine, charts[6], name="x" * letters, place="Fes")))]
        named[letters] = "".join(t for t in drawn if set(t) <= {"x", "…"})
    assert named == {30: "x" * 30, 31: "x" * 29 + "…"}


# --- it reaches what leaves the app ---------------------------------------------------------

def test_the_saved_picture_keeps_the_edges_and_fetches_nothing(engine, charts):
    drawn = _natal(engine, charts[0], name="Invented", bounds=True)
    saved = wheel.saved_svg(drawn)
    fetches_nothing(saved)
    root = ET.fromstring(saved)
    assert sum(1 for t in root.iter(SVG + "text") if t.get("class") == "edge") == len(POINTS)
    assert sum(1 for t in root.iter(SVG + "text") if t.get("paint-order") == "stroke") == sum(1 for t in ET.fromstring(drawn).iter(SVG + "text") if t.get("paint-order") == "stroke")
