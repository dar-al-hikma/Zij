"""The seam and the carry: lane G8 of the re-pass of 2026-10-04.

* HP-23 (partly) -- a longitude a hair under 360 (-1e-16) normalises to
  360.0, which get_zodiac_sign reads as 0 Aries. The F9b check found
  evaluate_house_lords still taking the Ascendant's sign from
  int(ascendant_lon // 30) = -1 (Pisces), so every place's sign moved by one.
* L5-02 (partly) -- the wheel prints get_degree_string's degree and minute,
  which carry a value within a millionth of a minute of a whole minute; since
  the owner's ruling on Q6 (2026-10-05) the carry stops at a sign's end, so a
  value just under it prints 29° 59' of its own sign. The sign glyph beside
  them must be the sign get_degree_string prints, at every place a wheel
  prints one: the natal wheel's radial stacks and its
  Wide panel (points and cusps), and the Timing wheel's rings and its Wide
  columns (points, Ascendant and Midheaven).
"""
import copy
import re
import xml.etree.ElementTree as ET
from datetime import datetime


SVG_NS = "{http://www.w3.org/2000/svg}"
PETOSKEY = (45.37334, -84.95533)
REFERENCE_UTC = datetime(1982, 11, 19, 16, 44)

# Each value lies within the display tolerance below a sign's end, so
# get_degree_string prints it as the last minute of its own sign, the carry
# stopping there (ruling on Q6); -1e-16 is the seam and prints as 0 Aries.
CARRIED = {
    "Saturn": 60.0 - 1e-10,       # 29° Tau 59'
    "Jupiter": 30.0 - 1e-10,      # 29° Ari 59'
    "Mars": 360.0 - 1e-12,        # 29° Pis 59'
    "Venus": -1e-16,              # 00° Ari 00'
    "Mercury": 120.0 - 1e-10,     # 29° Can 59'
}


def _expected(engine, lon):
    """(degree, sign glyph, minute) as get_degree_string prints them."""
    printed = engine["get_degree_string"](lon)
    d, sign3, m = re.fullmatch(r"(\d{2})° (\w{3}) (\d{2})'", printed).groups()
    index = [s[:3] for s in engine["SIGN_ORDER"]].index(sign3)
    return d, engine["SIGN_GLYPHS"][index], m


def _carried_chart(engine):
    chart = copy.deepcopy(engine["calculate_traditional_chart"](REFERENCE_UTC, *PETOSKEY))
    for planet, lon in CARRIED.items():
        chart["planetary_data"][planet]["longitude"] = lon
    chart["mc"] = 240.0 - 1e-10                            # prints 29° Sco 59'
    houses = list(chart["houses"])
    houses[1] = 300.0 - 1e-10                              # the 2nd cusp prints 29° Cap 59'
    houses[9] = chart["mc"]
    chart["houses"] = type(chart["houses"])(houses)
    return chart


def _texts(element):
    return [(t.text or "").replace("︎", "") for t in element.iter(f"{SVG_NS}text")]


def _stacks(svg):
    """{(ring, point): (degree, sign glyph, minute)} from every radial stack."""
    out = {}
    for g in ET.fromstring(svg).iter(f"{SVG_NS}g"):
        if g.get("class") != "pt":
            continue
        texts = _texts(g)
        if len(texts) < 4:                                  # the angle boxes print no sign
            continue
        out[(g.get("data-ring"), g.get("data-point"))] = (texts[1].rstrip("°"), texts[2], texts[3].rstrip("'"))
    return out


def _panel_lines(svg):
    return [t.strip() for t in _texts(ET.fromstring(svg))
            if re.match(r"\d{2}° . \d{2}′", t.strip())]


def test_house_lords_read_an_ascendant_at_the_seam_as_0_aries(engine):
    planets = {p: {"longitude": lon} for p, lon in
               [("Saturn", 10.0), ("Jupiter", 40.0), ("Mars", 70.0), ("Sun", 100.0),
                ("Venus", 130.0), ("Mercury", 160.0), ("Moon", 190.0)]}
    at_zero = engine["evaluate_house_lords"](planets, 0.0)
    assert at_zero[0]["Cusp Sign"] == "Aries"
    for seam in (-1e-16, -0.0, 360.0, 720.0, -360.0):
        assert engine["get_zodiac_sign"](seam) == "Aries"
        assert engine["evaluate_house_lords"](planets, seam) == at_zero, seam


def test_every_wheel_prints_the_sign_its_carried_minute_is_in(engine):
    chart = _carried_chart(engine)
    hybrid = {wide: engine["generate_hybrid_svg"](chart, "Seam", "Petoskey", *PETOSKEY,
                                                  datetime(1982, 11, 19, 11, 44), "EST", wide=wide)
              for wide in (False, True)}
    multi = engine["generate_multiwheel_svg"]([{"label": "Root", "chart": chart, "when": ""}], "Seam", wide=True)

    # The radial stacks: the natal wheel's (both layouts) and the Timing wheel's ring.
    for svg, ring in ((hybrid[False], None), (hybrid[True], None), (multi, "0")):
        stacks = _stacks(svg)
        for planet, lon in CARRIED.items():
            assert stacks[(ring, planet)] == _expected(engine, lon), (ring, planet, stacks[(ring, planet)])

    # The Wide panels: every carried point, the carried cusp and the carried Midheaven.
    def line(lon):
        d, glyph, m = _expected(engine, lon)
        return f"{d}° {glyph} {m}′"
    natal_panel = _panel_lines(hybrid[True])
    timing_panel = _panel_lines(multi)
    natal_carried = list(CARRIED.values()) + [chart["houses"][1], chart["mc"]]
    timing_carried = list(CARRIED.values()) + [chart["mc"]]
    assert len(natal_carried) == 7
    assert len(timing_carried) == 6
    for lon in natal_carried:
        assert line(lon) in natal_panel, (lon, line(lon), natal_panel)
    for lon in timing_carried:
        assert any(t.startswith(line(lon)) for t in timing_panel), (lon, line(lon), timing_panel)
