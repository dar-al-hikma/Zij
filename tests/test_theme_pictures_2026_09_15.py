"""The pictures in the page's own mode.

Each picture is an SVG inside an <img>, where no page CSS reaches it, so
every one of them carried its own opaque ground and would show as a square
on a page of another colour. The four renderers take a theme: None is the
light palette, and "dark" is the same geometry on the dark page's own ground,
with nothing white or black left in it. What reaches a renderer is the page's
mode; that rule is lifted out of the app and evaluated here.
"""
import ast
import io
import re
import tokenize
import xml.etree.ElementTree as ET
from datetime import date, datetime

import pytest

from conftest import assert_no_exception, find_page_widget, make_app, ui_source

ESCANABA = (45.74525, -87.06458)
REFERENCE_UTC = datetime(1977, 12, 16, 15, 8)
COLOUR = re.compile(r'(?:fill|stroke)="(#[0-9a-fA-F]{3,6})"')
LIGHT_FACE = re.compile(r'<circle class="face" [^>]*/>')       # the one element the light wheels add
LIGHT_ONLY = {"#fff", "#ffffff", "#000", "#000000"}


@pytest.fixture(scope="module")
def chart(engine):
    return engine["calculate_traditional_chart"](REFERENCE_UTC, *ESCANABA)


@pytest.fixture(scope="module")
def bundle(engine, chart):
    return engine["pn4_timing_bundle"](chart, ESCANABA[0], ESCANABA[1], REFERENCE_UTC.date(),
                                       date(2026, 9, 10), engine["PN4_MONTHLY_TURN_OPTIONS"][0],
                                       {"Hour Lord": "Venus", "Approximate": False})


def pictures(engine, chart, bundle, **kw):
    """The four, each rendered with whatever theme is passed."""
    rings = [{"label": "Nativity", "chart": chart, "when": "birth"},
             {"label": f"Year, age {bundle['age']}", "chart": bundle["sr"], "when": "year"}]
    return {
        "natal wheel": engine["generate_hybrid_svg"](
            chart, "Test Chart 1240", "Florence, 16 (IT)", ESCANABA[0], ESCANABA[1],
            datetime(1240, 5, 23, 14, 30), "LMT", bounds=True,
            chronocrats={"Day Lord": "Sun", "Hour Lord": "Moon"}, **kw),
        "revolution wheel": engine["generate_multiwheel_svg"](
            rings, "Test Chart 1240", shade_sign=3, outline_sign=5,
            profection_from=chart["ascendant"], marks=[("TP", 123.4, 0)],
            badges={0: {"Sun": "D"}},
            distribution={"start": chart["ascendant"], "end": (chart["ascendant"] + 47.0) % 360.0},
            **kw),
        "distribution strip": engine["generate_distribution_strip_svg"](
            bundle["segments"], bundle["elapsed_years"], "years",
            engine["PN4_DISTRIBUTION_SPAN_YEARS"], "The distributions", **kw),
        "hit strip": engine["generate_hit_strip_svg"](
            bundle["hm_direction"], bundle["elapsed_years"],
            engine["PN4_DISTRIBUTION_SPAN_YEARS"], "The house-master directed", **kw),
    }


# --- 1. No theme is the light palette --------------------------------------

@pytest.mark.parametrize("theme", [None, "light", "", "Light"])
def test_no_theme_and_a_light_one_draw_the_same_light_picture(engine, chart, bundle, theme):
    plain = pictures(engine, chart, bundle)
    themed = pictures(engine, chart, bundle, theme=theme)
    for name, svg in plain.items():
        assert themed[name] == svg, f"{name} changed under theme={theme!r}"
    for svg in plain.values():
        assert '"#F7F3E8"' in svg, "the light ground is the page's own"
    for name in ("natal wheel", "revolution wheel"):
        assert '"#FFFDF6"' in plain[name], "the wheel stands on the house's panel"


# --- 2. The dark palette --------------------------------------------------

def test_the_dark_pictures_carry_no_white_ground_and_no_black_ink(engine, chart, bundle):
    for name, svg in pictures(engine, chart, bundle, theme="dark").items():
        ET.fromstring(svg)
        colours = set(COLOUR.findall(svg))
        assert not (colours & LIGHT_ONLY), f"{name} still carries {colours & LIGHT_ONLY}"
        root = ET.fromstring(svg)
        ground = next(el for el in root.iter() if el.tag.endswith("rect"))
        assert ground.get("fill") == engine["_PALETTE_DARK"]["bg"], f"{name}: ground {ground.get('fill')}"


def test_the_dark_palette_answers_for_every_colour_the_light_one_does(engine):
    light, dark = engine["_PALETTE_LIGHT"], engine["_PALETTE_DARK"]
    assert set(light) - {"face"} == set(dark), "only the light wheel stands on another colour than its ground"
    for key, value in dark.items():
        assert type(value) is type(light[key]), key
        if key in ("tints", "rings"):
            assert len(value) == len(light[key])
        if key in ("axis", "strip_tint"):
            assert set(value) == set(light[key])
    assert dark["bg"] == "#070A12"                     # the dark page's own ground


def test_the_geometry_is_the_same_picture_in_both_palettes(engine, chart, bundle):
    """Same elements, same coordinates: only the colours move."""
    plain = pictures(engine, chart, bundle)
    dark = pictures(engine, chart, bundle, theme="dark")
    for name, svg in plain.items():
        light_shape = COLOUR.sub('fill=""', LIGHT_FACE.sub("", svg))
        dark_shape = COLOUR.sub('fill=""', dark[name])
        assert light_shape == dark_shape, f"{name}: the geometry moved with the palette"


# --- 3. The strips take the full run's value, the wheels read it afresh ----

def test_the_strips_take_the_full_run_s_theme_and_the_wheels_read_it_afresh():
    src = ui_source()
    assert 'getattr(st.context, "theme", None)' in src, "the read must survive a missing attribute"
    assert 'getattr(_context_theme, "type", None)' in src
    assert src.count("VIEWER_THEME = ") == 1, "read at the top level by the one reading"
    assert src.count("WHEEL_THEME = ") == 1, "one value decides every picture a full run alone draws"
    # Nine pictures: the six direction strips, from the full run's value; the
    # Chart page's two wheels and the Timing page's one, read afresh in their fragments.
    assert src.count("theme=WHEEL_THEME") == 6
    assert src.count("theme=_theme") == 3
    assert src.count("wheel_look(_look, _viewer_theme())") == 2, "each wheel's look reads the page afresh"
    assert len(re.findall(r"\btheme=", src)) == 9, "no picture takes a theme by another name"


def wheel_theme_rule():
    """The app's own WHEEL_THEME expression, lifted out of the UI half and
    evaluated -- the rule itself, not a copy of it."""
    src = ui_source()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "WHEEL_THEME" for t in node.targets):
            expression = ast.get_source_segment(src, node.value)
            return lambda viewer: eval(expression, {}, {"VIEWER_THEME": viewer})
    raise AssertionError("the UI half assigns no WHEEL_THEME")


@pytest.mark.parametrize("viewer, palette", [(None, "_PALETTE_LIGHT"), ("light", "_PALETTE_LIGHT"),
                                             ("dark", "_PALETTE_DARK")])
def test_every_picture_is_drawn_in_the_page_s_mode(viewer, palette, engine):
    """Light on a light page, dark on a dark page; no theme reported yet, the
    light palette, not a guess."""
    rule = wheel_theme_rule()
    assert rule(viewer) == viewer
    assert engine["_wheel_palette"](rule(viewer)) is engine[palette]


def test_the_old_setting_is_no_display_preference_and_no_reading(engine):
    """A file holding it keeps it (tests/test_wheel_follows_the_page.py), so it
    stays listed; nothing in the UI half reads it."""
    assert "_wheel_dark" in engine["PREFERENCE_KEYS"], "a file holding it must keep it"
    src = ui_source()
    registry = src[src.index("READINGS_REGISTRY = ("):]
    registry = registry[:registry.index("\n)\n")]
    assert "_wheel_dark" not in registry, "a display preference is not a doctrinal reading"
    code = [token.string for token in tokenize.generate_tokens(io.StringIO(src).readline)
            if token.type != tokenize.COMMENT]
    assert not [word for word in code if "wheel_dark" in word.lower()], "something still reads it"


@pytest.mark.parametrize("page", ["chart", "timing"])
def test_the_pages_with_pictures_render_under_a_theme_the_harness_cannot_report(page):
    """AppTest has no browser, so st.context.theme.type is None there; the
    pages must render on the light palette rather than raise."""
    at = make_app(page=page).run()
    assert_no_exception(at, page)


@pytest.mark.parametrize("page", ["chart", "timing"])
def test_neither_wheel_carries_a_control_for_it(page):
    """No box on either page: the page's mode decides."""
    at = make_app(page=page).run()
    assert_no_exception(at, page)
    assert not [c for c in at.main.checkbox if c.label == "Dark wheel" or c.key == "wheel_dark"]
    assert "_wheel_dark" not in at.session_state, "nothing writes it"
