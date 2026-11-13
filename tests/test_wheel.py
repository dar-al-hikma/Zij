"""The chart wheel.

The renderer is a pure function in the engine half, so it is exercised
directly on every harness chart plus the reference nativity, in
both layouts: the SVG must be well-formed XML (an unescaped & in a place
name once broke the whole wheel), carry every point's glyph, the twelve
whole-sign and twelve quadrant numbers, the chart's name, and a retrograde
mark exactly when some point moves backwards. The label-spreading helpers
get unit tests of their own, since a wheel that renders but piles four
glyphs on one bearing is the failure this redesign was for.
"""
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import pytest

from conftest import CHARTS, FLORENCE, LOCAL_TIME, ui_source

# The reference chart, invented: Escanaba MI, 1977-12-16 10:08 EST.
ESCANABA = (45.74525, -87.06458)
REFERENCE_UTC = datetime(1977, 12, 16, 15, 8)


def _chart(engine, date=None):
    if date is None:
        return engine["calculate_traditional_chart"](REFERENCE_UTC, *ESCANABA), ESCANABA
    local = datetime.combine(datetime.strptime(date, "%Y-%m-%d").date(), LOCAL_TIME)
    dt_utc = local - timedelta(hours=FLORENCE[1] / 15.0)      # LMT, as the harness casts them
    return engine["calculate_traditional_chart"](dt_utc, *FLORENCE), FLORENCE


def _svg(engine, chart, latlon, name="Test Chart 1240", wide=False):
    return engine["generate_hybrid_svg"](chart, name, "Florence, 16 (IT)", latlon[0], latlon[1],
                                         datetime(1240, 5, 23, 14, 30), "LMT", wide=wide,
                                         chronocrats={"Day Lord": "Sun", "Hour Lord": "Moon"})


def _texts(svg):
    root = ET.fromstring(svg)
    return [t.text or "" for t in root.iter("{http://www.w3.org/2000/svg}text")]


@pytest.mark.parametrize("date", [None] + list(CHARTS), ids=["1977-escanaba"] + list(CHARTS))
@pytest.mark.parametrize("wide", [False, True], ids=["square", "wide"])
def test_wheel_is_well_formed_and_complete(engine, date, wide):
    chart, latlon = _chart(engine, date)
    svg = _svg(engine, chart, latlon, wide=wide)
    root = ET.fromstring(svg)                                  # well-formed, or this raises
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    width = engine["WHEEL_WIDE_WIDTH"] if wide else engine["WHEEL_SIZE"]
    assert root.get("viewBox") == f"0 0 {width} {engine['WHEEL_SIZE']}"

    texts = _texts(svg)
    stripped = [t.rstrip("︎") for t in texts]
    for glyph in engine["POINT_GLYPHS"].values():
        assert glyph in stripped, f"point glyph {glyph!r} missing"
    for glyph in engine["SIGN_GLYPHS"]:
        assert glyph in stripped, f"sign glyph {glyph!r} missing"
    # Twelve whole-sign numbers on the rim and twelve quadrant numbers on
    # the inner ring: every number 1..12 appears at least twice.
    for n in range(1, 13):
        assert texts.count(str(n)) >= 2, f"house number {n} appears {texts.count(str(n))}x"
    assert "Test Chart 1240" in texts
    assert "Whole-Sign Hybrid Chart" not in svg
    assert "True node" in " ".join(texts)

    # A retrograde mark exactly when something moves backwards. The Lot has
    # no motion; the south node shares the north node's.
    moving_back = any(d.get("speed_in_lon", 0.0) < 0 for d in chart["planetary_data"].values())
    assert ("℞" in "".join(texts)) == moving_back

    if wide:
        assert "Positions" in texts and "Angles and cusps (Alchabitius)" in texts
        assert any("Lord of the hour: Moon" in t for t in texts)


def test_user_strings_are_escaped(engine):
    chart, latlon = _chart(engine)
    svg = engine["generate_hybrid_svg"](chart, "Smith & Jones <test>", "Ampersand & Co", latlon[0], latlon[1],
                                        datetime(1977, 12, 16, 10, 8), "EST <x>")
    ET.fromstring(svg)
    assert "Smith &amp; Jones &lt;test&gt;" in svg and "Ampersand &amp; Co" in svg and "EST &lt;x&gt;" in svg


def test_reference_chart_positions(engine):
    """The invented chart's angles at the engine as it stands, minutes
    truncated the way get_degree_string() truncates. Also pins the true
    node: the mean node sits at 11 Libra."""
    chart, _ = _chart(engine)
    dm = engine["_wheel_dm"]
    assert (engine["get_zodiac_sign"](chart["ascendant"]), dm(chart["ascendant"])) == ("Capricorn", (18, 52))
    assert (engine["get_zodiac_sign"](chart["mc"]), dm(chart["mc"])) == ("Scorpio", (17, 32))
    node = chart["planetary_data"]["North Node"]["longitude"]
    assert (engine["get_zodiac_sign"](node), dm(node)[0]) == ("Libra", 12)


def test_reference_chart_agrees_with_janus(engine):
    """An outside witness: the table was read off Janus, at the invented chart's moment and place (geocentric,
    tropical, Alchabitius semi-arc, true node). Each value stands within 5 seconds of arc of the engine."""
    signs = ("Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
             "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces")

    def longitude(sign, degrees, minutes, seconds):
        return signs.index(sign) * 30 + degrees + minutes / 60 + seconds / 3600

    bodies = {
        "Sun": ("Sagittarius", 24, 33, 36),
        "Moon": ("Pisces", 14, 42, 30),
        "Mercury": ("Capricorn", 5, 31, 14),
        "Venus": ("Sagittarius", 15, 47, 30),
        "Mars": ("Leo", 11, 27, 44),
        "Jupiter": ("Cancer", 1, 56, 16),
        "Saturn": ("Virgo", 0, 31, 26),
        "North Node": ("Libra", 12, 16, 12),
    }
    cusps = (
        ("Capricorn", 18, 52, 20),
        ("Aquarius", 26, 24, 54),
        ("Aries", 7, 28, 28),
        ("Taurus", 17, 32, 33),
        ("Gemini", 8, 35, 37),
        ("Gemini", 28, 45, 38),
    )
    chart, _ = _chart(engine)
    planets = chart["planetary_data"]
    read = {name: (planets[name]["longitude"], value) for name, value in bodies.items()}
    read["Part of Fortune"] = (chart["lot_of_fortune"], ("Aries", 9, 1, 14))
    read["Ascendant"] = (chart["ascendant"], ("Capricorn", 18, 52, 20))
    read["Midheaven"] = (chart["mc"], ("Scorpio", 17, 32, 33))
    for number, value in enumerate(cusps):
        read[f"Cusp {number + 1}"] = (chart["houses"][number], value)
    assert len(read) == 17
    for name, (ours, value) in read.items():
        gap = abs((ours - longitude(*value) + 180) % 360 - 180) * 3600
        assert gap <= 5, f"{name}: {gap:.2f} seconds of arc from Janus"
    for name in ("Mercury", "Mars", "Jupiter", "Saturn", "North Node"):
        assert planets[name]["speed_in_lon"] < 0, name
    for name in ("Sun", "Moon", "Venus"):
        assert planets[name]["speed_in_lon"] > 0, name


# --- Label spreading -------------------------------------------------------

def test_spread_leaves_separated_bearings_alone(engine):
    bearings = [10.0, 40.0, 95.0, 200.0, 300.0]
    assert engine["_spread_labels"](bearings, 10.5) == bearings


def test_spread_separates_a_stellium_and_keeps_its_order(engine):
    spread = engine["_spread_labels"]
    bearings = [100.0, 100.5, 101.0, 103.0, 250.0]
    out = spread(bearings, 10.0)
    assert len(out) == 5 and out[4] == 250.0
    # Adjacent pairs at least the minimum apart, in the same circular order.
    for k in range(5):
        gap = (out[(k + 1) % 5] - out[k]) % 360
        assert gap >= 10.0 - 1e-6, f"pair {k} only {gap:.2f} apart"
    # Circular order preserved: consecutive gaps go round exactly once.
    assert abs(sum((out[(k + 1) % 5] - out[k]) % 360 for k in range(5)) - 360.0) < 1e-6
    # The cluster spreads around its own centre, not off to one side.
    assert 84 < out[0] < 90 and 112 < out[3] < 120     # 4 x 10 deg centred near 101


def test_spread_handles_the_wrap_at_zero(engine):
    out = engine["_spread_labels"]([1.0, 359.5], 10.0)
    assert (out[0] - out[1]) % 360 >= 10.0 - 1e-6


def test_stagger_alternates_within_a_displaced_run(engine):
    stagger = engine["_stagger_offsets"]
    true = [10.0, 11.0, 12.0, 13.0, 200.0]
    shown = [-5.0 % 360, 5.5, 16.0, 26.5, 200.0]
    assert stagger(true, shown, 30) == [0, 30, 0, 30, 0]
    assert stagger(true, true, 30) == [0, 0, 0, 0, 0]


# --- The Chart page's use of it ---------------------------------------------

def test_chart_page_names_the_wheel_and_offers_both_layouts():
    src = ui_source()
    # One name for an unnamed chart everywhere: the strip's "Unsaved chart"
    # ("Transits" superseded).
    assert 'chart_name = _picked_name if _picked_loaded else (EXAMPLE_CHART_NAME if _chart_is_example else UNSAVED_CHART_NAME)' in src, "an unnamed chart is named as the strip names it"
    assert 'st.session_state.get("chart_picker")' in src
    # The square wheel is centred in the reading column; the wide one runs the page's
    # full width. Both are the same component mount, the layout deciding
    # which SVG and which width go into its envelope.
    assert '"svg": svg_wide if _picked_wide else svg_code,' in src
    assert '"width": "stretch" if _picked_wide else "column",' in src
    assert "st.iframe(" not in src, "the iframe had no fullscreen control; the component carries its own"
    assert '"Wheel layout", WHEEL_LAYOUT_OPTIONS, "wheel_layout", "_wheel_layout"' in src
    # The controls stand above the wheel, so the layout is the radio's own return.
    assert 'wheel_layout = _reading_radio("Wheel layout", WHEEL_LAYOUT_OPTIONS, "wheel_layout", "_wheel_layout")' in src
