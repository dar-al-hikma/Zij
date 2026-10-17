"""B-15 of the third outside pass (ruling 146): the wheel SVGs stay
well-formed whatever a name holds.

XML 1.0 forbids the C0 controls other than tab, line feed and carriage
return, U+FFFE and U+FFFF, and a lone surrogate, escaped or not. A saved
chart's name or place label holding one made the Chart wheel and the Timing
multi-wheel, and so their downloads, not XML. ``_esc_text`` and ``_esc_attr``
now drop those characters before they escape; ordinary text is escaped as
before, byte for byte.
"""
import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pytest

from conftest import make_app

LMT = "LMT (Local Mean Time)"
REC = {"date_string": "1240-05-23", "time_string": "14:30:00", "time_standard": LMT,
       "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
# (name, place) as the reproduction ran them
ILLEGAL = [("Native\x01Name", "Florence"), ("Native", "Flor\x01ence"), ("A\x0bB", "Florence"),
           ("A￾B", "Florence"), ("A￿B", "Florence")]
ORDINARY = [("Native", "Florence"), ("Firenze — città", "Firenze — città"), ("東京都", "東京都 🌙"),
            ("ʿAlī al-Qabīṣī", "بغداد"), ("Tom & Jerry <b> \"q\" 'a'", "A&B <c>"), ("tab\there", "x\ny\rz")]
IDS = [repr(n) + "/" + repr(p) for n, p in ILLEGAL]
# the Timing multi-wheel draws the name and ring labels, never the place, so a place-only case would pass at base
NAME_CASES = [n for n, _ in ILLEGAL if n != "Native"]
NAME_IDS = [repr(n) for n in NAME_CASES]


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def chart():
    return _default_chart()


def _default_chart():
    """The default chart as the page computes it, through a captured call.
    The app run may re-import the engine, so the module is taken after it
    has been built, and both are returned."""
    at = make_app(page="chart")
    import engine as module
    captured = []
    original = module.generate_hybrid_svg

    def spy(chart_data, *a, **k):
        captured.append(chart_data)
        return original(chart_data, *a, **k)
    module.generate_hybrid_svg = spy
    try:
        at.run(timeout=300)
    finally:
        module.generate_hybrid_svg = original
    assert captured, "the premise: the page draws the wheel"
    return module, captured[0]


def _draw(module, cd, name, place, wide):
    return module.generate_hybrid_svg(cd, name, place, 43.7792, 11.2463, datetime(1240, 5, 23, 14, 30), "LMT", wide=wide)


def _multi(module, cd, name, wide):
    return module.generate_multiwheel_svg([{"label": name, "chart": cd, "when": "x"}], name, wide=wide)


@pytest.mark.parametrize("name, place", ILLEGAL, ids=IDS)
@pytest.mark.parametrize("wide", [False, True])
def test_the_chart_wheel_parses_whatever_the_name_and_place_hold(chart, name, place, wide):
    module, cd = chart
    assert ET.fromstring(_draw(module, cd, name, place, wide)).tag.endswith("svg")


@pytest.mark.parametrize("name", NAME_CASES, ids=NAME_IDS)
@pytest.mark.parametrize("wide", [False, True])
def test_the_timing_multiwheel_parses_whatever_the_name_holds(chart, name, wide):
    module, cd = chart
    assert ET.fromstring(_multi(module, cd, name, wide)).tag.endswith("svg")


def test_a_ring_label_and_a_hub_line_holding_an_illegal_character_parse(chart):
    module, cd = chart
    svg = module.generate_multiwheel_svg([{"label": "R\x01oot", "chart": cd, "when": "w\x0ben"}], "t",
                                         hub_lines=("h\x02ub",), marks=(("M\x03", 10.0, 0),))
    assert ET.fromstring(svg).tag.endswith("svg")


def test_the_helpers_drop_exactly_what_xml_forbids():
    import engine as module
    esc_t, esc_a = module._esc_text, module._esc_attr
    forbidden = [chr(c) for c in list(range(0, 9)) + [0x0B, 0x0C] + list(range(0x0E, 0x20))] + \
                ["\ufffe", "\uffff", "\ud800", "\udfff"]
    assert len(forbidden) == 9 + 2 + 18 + 4
    for ch in forbidden:
        # ascii() so a lone surrogate in a failing value cannot break the report under xdist
        assert (ascii(esc_t("a" + ch + "b")), ascii(esc_a("a" + ch + "b"))) == ("'ab'", "'ab'"), ascii(ch)
    # legal in XML 1.0, so kept: tab/LF/CR, the whole of DEL and C1 (U+007F-U+009F, NEL among them), the line and
    # paragraph separators, the replacement character
    kept = list("\t\n\r") + [chr(c) for c in range(0x7F, 0xA0)] + ["\u2028", "\u2029", "\ufffd"]
    assert len(kept) == 3 + 33 + 3
    for ch in kept:
        assert esc_t("a" + ch + "b") == "a" + ch + "b" and esc_a("a" + ch + "b") == "a" + ch + "b", ascii(ch)
    assert esc_t("&<>\"'") == "&amp;&lt;&gt;&quot;&#x27;" and esc_a("&<>\"'") == "&amp;&lt;&gt;&quot;&#x27;"
    assert esc_t("\U0001F319 é 東 ب") == "\U0001F319 é 東 ب"


def test_ordinary_names_give_the_svg_base_gives(chart, monkeypatch):
    """Base was html.escape itself; the same drawing with that put back is
    the reference, byte for byte."""
    import html
    module, cd = chart
    got = [(n, p, w, _draw(module, cd, n, p, w), _multi(module, cd, n, w)) for n, p in ORDINARY for w in (False, True)]
    assert len(got) == 2 * len(ORDINARY)
    monkeypatch.setattr(module, "_esc_text", lambda s: html.escape(str(s)))
    monkeypatch.setattr(module, "_esc_attr", lambda s: html.escape(str(s), quote=True))
    for n, p, w, hybrid, multi in got:
        assert hybrid == _draw(module, cd, n, p, w), (n, p, w)
        assert multi == _multi(module, cd, n, w), (n, w)
        assert ET.fromstring(hybrid) is not None and ET.fromstring(multi) is not None


# --- the page path, as the reproduction ran it ---------------------------------

def _page_svgs(page, name, place, monkeypatch):
    """A scratch store holding the one record (ASCII-escaped, as json.dumps
    writes it), the picker's select, and the SVGs the page builds."""
    store = Path(os.environ["XDG_DATA_HOME"]) / "Zij"
    store.mkdir(parents=True, exist_ok=True)
    (store / "saved_charts.json").write_bytes(json.dumps({name: dict(REC, location_query=place)}).encode("ascii"))
    at = make_app(page=page, timeout=300)
    import engine as module
    svgs = []
    for fn in ("generate_hybrid_svg", "generate_multiwheel_svg"):
        def spy(*a, _orig=getattr(module, fn), **k):
            out = _orig(*a, **k)
            svgs.append(out)
            return out
        monkeypatch.setattr(module, fn, spy)
    at.run(timeout=300)
    at.sidebar.selectbox(key="chart_picker").select(name).run(timeout=300)
    assert not at.exception, [str(e.value) for e in at.exception]
    return svgs


PAGE_CASES = [("chart", n, p) for n, p in ILLEGAL[:2] + ILLEGAL[3:4]] + \
             [("timing", n, p) for n, p in (ILLEGAL[0], ILLEGAL[3])]  # no place-only case on Timing, as above


@pytest.mark.parametrize("page, name, place", PAGE_CASES, ids=lambda v: repr(v))
def test_the_page_builds_a_well_formed_download(scratch, monkeypatch, page, name, place):
    svgs = _page_svgs(page, name, place, monkeypatch)
    wheels = [s for s in svgs if s.lstrip().startswith("<svg")]
    assert wheels, "the premise: the page drew a wheel"
    for svg in wheels:
        ET.fromstring(svg)
