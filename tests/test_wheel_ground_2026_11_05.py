"""On a light page a picture's ground is the page's own, so no square shows
round a wheel; the wheel itself keeps its near-white face, hub, rim band and
sign tints. Only what lies outside the outer circle moved, and dark not at all.
"""
import hashlib
import re
import tomllib
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

import pytest

import house_style
import wheel

GROUND, FACE = "#F7F3E8", "#FFFDF6"
FLORENCE = (43.7696, 11.2558)
MOMENT = datetime(1240, 5, 23, 13, 30)
SVG = "{http://www.w3.org/2000/svg}"
DARK_PALETTE_SHA256 = "b172df43aa1ba07fb4ccd20afeb6d4dc530f3790a81c55ca5fa5da57d2a81bf9"


@pytest.fixture(scope="module")
def chart(engine):
    return engine["calculate_traditional_chart"](MOMENT, *FLORENCE)


@pytest.fixture(scope="module")
def bundle(engine, chart):
    return engine["pn4_timing_bundle"](chart, FLORENCE[0], FLORENCE[1], MOMENT.date(), date(1270, 5, 23),
                                       engine["PN4_MONTHLY_TURN_OPTIONS"][0],
                                       {"Hour Lord": "Venus", "Approximate": False})


def wheels(engine, chart, bundle, theme=None):
    """Every wheel, Square and Wide, each with the radius of its outer circle."""
    rings = [{"label": "Nativity", "chart": chart, "when": "birth"},
             {"label": "The year", "chart": bundle["sr"], "when": "year"}]
    drawn = {}
    for wide in (False, True):
        drawn["natal", wide] = (engine["generate_hybrid_svg"](
            chart, "Invented", "Florence", FLORENCE[0], FLORENCE[1], MOMENT, "LMT", bounds=True, wide=wide,
            theme=theme), wheel._R_RIM)
        drawn["rings", wide] = (engine["generate_multiwheel_svg"](
            rings, "Invented", wide=wide, shade_sign=3, profection_from=chart["ascendant"], theme=theme), wheel._M_RIM)
    return drawn


def strips(engine, bundle, theme=None):
    span = engine["PN4_DISTRIBUTION_SPAN_YEARS"]
    return [engine["generate_distribution_strip_svg"](bundle["segments"], bundle["elapsed_years"], "years", span, "A",
                                                      theme=theme),
            engine["generate_hit_strip_svg"](bundle["hm_direction"], bundle["elapsed_years"], span, "B", theme=theme)]


def test_the_light_ground_is_the_page_s_and_the_wheel_s_face_is_as_it_was():
    config = tomllib.loads((Path(wheel.__file__).parent / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    light = house_style.WHEEL_PALETTES["light"]
    assert light["bg"] == config["theme"]["light"]["backgroundColor"] == GROUND
    assert light["face"] == light["panel"] == FACE
    assert light["tints"] == (FACE, "#E9E2D3", "#F5F0E5", "#DED8CB")


def test_the_dark_palette_is_as_it_was():
    dark = house_style.WHEEL_PALETTES["dark"]
    assert hashlib.sha256(repr(dark).encode()).hexdigest() == DARK_PALETTE_SHA256


def test_each_light_wheel_stands_on_its_face_and_the_ground_stays_outside_the_rim(engine, chart, bundle):
    for key, (svg, rim) in wheels(engine, chart, bundle).items():
        shapes = [e for e in ET.fromstring(svg) if e.tag != SVG + "style"]
        ground, face = shapes[:2]
        assert (ground.tag, ground.get("fill")) == (SVG + "rect", GROUND), key
        assert (face.tag, face.get("fill"), face.get("r")) == (SVG + "circle", FACE, str(rim)), key
        assert svg.count(f'fill="{GROUND}"') == 1, f"{key}: the ground is drawn once, under the face"
        assert GROUND not in re.sub(r'<rect width="\d+" height="\d+" fill="#F7F3E8"/>', "", svg), key


def test_a_light_strip_stands_on_the_page_s_ground(engine, bundle):
    for svg in strips(engine, bundle):
        assert f'fill="{GROUND}"' in svg and 'class="face"' not in svg and FACE not in svg


def test_a_dark_picture_has_no_face_and_its_old_ground(engine, chart, bundle):
    dark = house_style.WHEEL_PALETTES["dark"]
    for key, (svg, _rim) in wheels(engine, chart, bundle, theme="dark").items():
        assert 'class="face"' not in svg and f'fill="{dark["bg"]}"' in svg, key
        assert GROUND not in svg and FACE not in svg, key
    for svg in strips(engine, bundle, theme="dark"):
        assert GROUND not in svg and FACE not in svg
