"""The pictures and the HTML report wear the house style.

Colours come from tools/house_style/tokens.json through the generator and are
written nowhere else; only colours and faces moved, so nothing here holds a
wheel's places. What leaves the app carries the faces it draws in, as data
URIs from a fixed set; the page's own picture carries only the symbol faces,
and the page already serves the rest.
"""
import ast
import base64
import html
import io
import json
import re
import tomllib
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

import pytest

from conftest import assert_no_exception, fetches_nothing, make_app

ROOT = Path(__file__).resolve().parent.parent
TOKENS = json.loads((ROOT / "tools" / "house_style" / "tokens.json").read_text(encoding="utf-8"))
CHARACTERS = json.loads((ROOT / "tools" / "house_style" / "characters.json").read_text(encoding="utf-8"))
PLACE = (34.5, 69.2)
BIRTH = datetime(1963, 8, 14, 9, 45)
COLOUR = re.compile(r'(?:fill|stroke)="(#[0-9a-fA-F]{3,8})"')
FACE = re.compile(r"@font-face\{(.*?)\}", re.S)


@pytest.fixture(scope="module")
def chart(engine):
    return engine["calculate_traditional_chart"](BIRTH, *PLACE)


@pytest.fixture(scope="module")
def bundle(engine, chart):
    return engine["pn4_timing_bundle"](chart, PLACE[0], PLACE[1], BIRTH.date(), date(2026, 9, 10),
                                       engine["PN4_MONTHLY_TURN_OPTIONS"][0],
                                       {"Hour Lord": "Venus", "Approximate": False})


def pictures(engine, chart, bundle, theme=None):
    rings = [{"label": "Nativity", "chart": chart, "when": "birth"},
             {"label": f"Year, age {bundle['age']}", "chart": bundle["sr"], "when": "year"},
             {"label": "Month", "chart": bundle["sr"], "when": "month"}]
    return {
        "natal": engine["generate_hybrid_svg"](chart, "Invented", "Kabul", PLACE[0], PLACE[1], BIRTH, "LMT", bounds=True,
                                               chronocrats={"Day Lord": "Sun", "Hour Lord": "Moon"}, theme=theme),
        "rings": engine["generate_multiwheel_svg"](rings, "Invented", shade_sign=3, outline_sign=5, bounds=True,
                                                   profection_from=chart["ascendant"], marks=[("TP", 123.4, 0)],
                                                   badges={0: {"Sun": "D"}}, theme=theme,
                                                   distribution={"start": chart["ascendant"],
                                                                 "end": (chart["ascendant"] + 47.0) % 360.0}),
        "strip": engine["generate_distribution_strip_svg"](bundle["segments"], bundle["elapsed_years"], "years",
                                                           engine["PN4_DISTRIBUTION_SPAN_YEARS"], "Strip", theme=theme),
        "hits": engine["generate_hit_strip_svg"](bundle["hm_direction"], bundle["elapsed_years"],
                                                 engine["PN4_DISTRIBUTION_SPAN_YEARS"], "Hits", theme=theme),
    }


@pytest.fixture(scope="module")
def exported():
    at = make_app(page="sources")
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.run(timeout=300)
    assert_no_exception(at, "the Sources page")
    return at.session_state["_analysis_html"]


def _style(page):
    return re.search(r"<style>(.*?)</style>", page, re.S).group(1)


def _without_faces(css):
    return FACE.sub("", css)


def _stack(text):
    return [part.strip().strip("\"'") for part in text.split(",")]


def _cmap(payload):
    from fontTools.ttLib import TTFont
    return set(TTFont(io.BytesIO(base64.b64decode(payload))).getBestCmap())


def _faces(css):
    """Each @font-face rule as (family, weight, the code points it answers for)."""
    faces = []
    for rule in FACE.findall(css):
        points = _cmap(re.search(r"base64,([A-Za-z0-9+/=]+)", rule).group(1))
        declared = re.search(r"unicode-range:([^;]+);", rule)
        if declared:
            answered = set()
            for part in declared.group(1).split(","):
                first, _, last = part.strip()[2:].partition("-")
                answered |= set(range(int(first, 16), int(last or first, 16) + 1))
            points &= answered
        faces.append((re.search(r"font-family:'([^']+)'", rule).group(1),
                      int(re.search(r"font-weight:(\d+|normal)", rule).group(1).replace("normal", "400")), points))
    return faces


# --- One source -------------------------------------------------------------------

@pytest.mark.parametrize("name", ["wheel.py", "export_html.py"])
def test_no_colour_is_written_in_the_modules_that_draw(name):
    tree = ast.parse((ROOT / name).read_text(encoding="utf-8"))
    literal = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\b(?:fill|stroke|color)\s*[=:]\s*[\"']?"
                         r"(?!none\b|var\(|currentColor\b|transparent\b|inherit\b)[a-zA-Z]")
    found = [node.value[:60] for node in ast.walk(tree)
             if isinstance(node, ast.Constant) and isinstance(node.value, str) and literal.search(node.value)]
    assert found == []


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_pictures_palettes_read_the_tokens(engine, mode):
    t = TOKENS["modes"][mode]
    palette = engine["_wheel_palette"](None if mode == "light" else "dark")
    muted, steel, green, red = t["wheel_muted"], t["steel"], t["wheel_verdigris"], t["wheel_madder"]
    assert palette == {
        "bg": t["wheel_ground"], "panel": t["panel"], "ink": t["ink"], "rule": muted, "leader": muted,
        "leader_ring": muted, "label": muted, "note": muted, "axis_note": muted, "tints": tuple(t["sign_tints"]),
        "shade": t["wheel_shade"], "bound_tint": t["wheel_bound_tint"], "axis": {0: steel, 6: steel, 9: green, 3: green},
        "horizon": steel, "meridian": green, "cusp": red, "badge": t["wheel_badge"], "rings": (t["ink"], steel, red),
        "now": red, "strip_tint": t["strip_tints"], "strip_other": t["strip_other"],
        **({"face": t["wheel_face"]} if mode == "light" else {})}


def test_the_older_names_read_the_light_palette(engine):
    light = engine["_PALETTE_LIGHT"]
    assert engine["TRIPLICITY_TINT"] is light["tints"] and engine["STRIP_TINT"] is light["strip_tint"]
    assert engine["_AXIS_COLOUR"] is light["axis"] and engine["WHEEL_RING_COLOURS"] is light["rings"]
    assert engine["_CUSP_COLOUR"] == light["cusp"] and engine["WHEEL_SHADE"] == light["shade"]
    assert engine["WHEEL_BOUND_TINT"] == light["bound_tint"]


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_each_picture_draws_in_the_tokens_and_in_each_it_should(engine, chart, bundle, mode):
    t = TOKENS["modes"][mode]
    drawn = {name: {c.upper() for c in COLOUR.findall(svg)}
             for name, svg in pictures(engine, chart, bundle, None if mode == "light" else "dark").items()}
    tokens = {value.upper() for value in t.values() if isinstance(value, str)}
    tokens |= {value.upper() for value in t["sign_tints"]} | {value.upper() for value in t["strip_tints"].values()}
    assert drawn and tokens
    for name, colours in drawn.items():
        assert colours <= tokens, (name, sorted(colours - tokens))
    wants = {"natal": {t["wheel_ground"], t["panel"], t["ink"], t["wheel_muted"], t["steel"], t["wheel_verdigris"],
                       t["wheel_madder"], *t["sign_tints"]},
             "rings": {t["wheel_ground"], t["panel"], t["ink"], t["wheel_muted"], t["steel"], t["wheel_verdigris"],
                       t["wheel_madder"], t["wheel_badge"], t["wheel_shade"], t["wheel_bound_tint"]},
             "strip": {t["wheel_ground"], t["ink"], t["wheel_muted"], t["wheel_madder"]},
             "hits": {t["wheel_ground"], t["ink"], t["wheel_muted"], t["wheel_madder"]}}
    assert wants
    for name, colours in wants.items():
        assert {c.upper() for c in colours} <= drawn[name], (name, sorted({c.upper() for c in colours} - drawn[name]))
    assert drawn["strip"] & {value.upper() for value in t["strip_tints"].values()}


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_sign_of_the_year_draws_in_its_own_token(engine, chart, bundle, mode):
    """Its token and the fourth triplicity's are one colour, so a colour's being
    drawn somewhere says nothing: Aries' tint is another, and the shade has to
    arrive on it."""
    t = TOKENS["modes"][mode]
    assert t["wheel_shade"] != t["sign_tints"][0]
    rings = [{"label": "Nativity", "chart": chart, "when": "birth"}]

    def drawn(shade_sign):
        return engine["generate_multiwheel_svg"](rings, "Invented", shade_sign=shade_sign,
                                                 theme=None if mode == "light" else "dark").count(f'"{t["wheel_shade"]}"')
    assert drawn(0) - drawn(None) == 2, "the sector under everything and the sign's own band"


def test_the_report_s_colours_are_the_tokens(exported):
    css = _without_faces(_style(exported))

    def variables(block):
        return dict(re.findall(r"--(\w+):(#[0-9A-Fa-f]{6})", block))

    def expected(t):
        return {"ink": t["ink"], "dim": t["muted"], "rule": t["line"], "head": t["panel2"], "bg": t["background"],
                "band": t["panel"]}
    light = css.split("@media", 1)[0]
    dark = re.search(r"@media \(prefers-color-scheme: dark\) \{(.*?)\n\}", css, re.S).group(1)
    paper = re.search(r"@media print \{(.*?)\n\}", css, re.S).group(1)
    assert variables(light) == expected(TOKENS["modes"]["light"])
    assert variables(dark) == expected(TOKENS["modes"]["dark"])
    assert variables(paper) == expected(TOKENS["print"])
    assert TOKENS["print"]["background"].upper() == "#FFFFFF", "on paper, a white sheet"
    assert css.index("prefers-color-scheme") < css.index("@media print"), "paper wins over a dark computer"


def test_no_colour_is_written_in_the_report_outside_its_variables(exported):
    css = _without_faces(_style(exported))
    rules = re.sub(r":root \{[^}]*\}", "", css)
    assert re.findall(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|\b(?:fill|stroke|color)\s*:\s*"
                      r"(?!none\b|var\(|currentColor\b|transparent\b|inherit\b)[a-zA-Z]", rules) == []


@pytest.mark.parametrize("name", ["natal", "rings", "strip", "hits"])
def test_on_a_dark_page_a_picture_s_ground_is_the_page_s(engine, chart, bundle, name):
    """No rectangle behind the picture: its ground and the page's are one colour."""
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    root = ET.fromstring(pictures(engine, chart, bundle, "dark")[name])
    ground = root.find("{http://www.w3.org/2000/svg}rect")
    assert ground.get("width") == root.get("width") and ground.get("height") == root.get("height")
    assert ground.get("fill") == config["theme"]["dark"]["backgroundColor"]


# --- Stacks and faces -------------------------------------------------------------

def test_the_symbol_faces_come_first_in_every_stack_the_app_emits(engine, chart, bundle, exported):
    config = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))["theme"]
    import house_style
    page_style = house_style.PAGE_STYLE
    stacks = {"theme " + key: config[key] for key in ("font", "headingFont", "codeFont")}
    for n, text in enumerate(re.findall(r"font-family:([^;}]+)[;}]", _without_faces(page_style))):
        stacks[f"page rule {n}"] = text
    report = _without_faces(_style(exported))
    for n, text in enumerate(re.findall(r"font-family:([^;}]+)[;}]", report)):
        stacks[f"report rule {n}"] = text
    stacks["report body"] = re.search(r"font:16px/1\.55 ([^;]+);", report).group(1)
    drawn = pictures(engine, chart, bundle)
    assert drawn
    for name, svg in drawn.items():
        text = re.search(r'<svg [^>]*style="font-family:([^"]+)"', svg).group(1)
        stacks[name] = text
        assert _stack(text)[-1] == "sans-serif", name
    assert len(stacks) >= 12
    for where, text in stacks.items():
        families = _stack(text)
        if families[0] in ("inherit", "var(--zij-reading)"):
            continue
        assert families[:2] == ["TAE Symbols", "TAE Symbols Sun"] or families[0] == "TAE Symbols", (where, families)


def test_the_report_carries_each_face_its_stacks_name(exported):
    css = _style(exported)
    faces = _faces(css)
    carried = {family for family, _, _ in faces}
    named = set()
    rules = _without_faces(css)
    for text in re.findall(r"font-family:([^;}]+)[;}]", rules) + re.findall(r"font:16px/1\.55 ([^;]+);", rules):
        named |= set(_stack(text))
    named -= {"serif", "sans-serif", "TAE Symbols Sun"}
    assert named and named <= carried, sorted(named - carried)
    weights = {(family, weight) for family, weight, _ in faces}
    assert {("EB Garamond", 400), ("EB Garamond", 600), ("Zij Interface", 400)} <= weights
    assert 0x2609 in {p for family, _, points in faces if family == "TAE Symbols" for p in points}, "the Sun, under the one family"


def test_the_report_asks_for_no_face_it_does_not_carry(exported):
    rules = _without_faces(_style(exported))
    assert "italic" not in rules, "no italic face travels with the report"
    assert "oblique" not in rules
    assert set(re.findall(r"font-weight:(\w+)", rules)) == {"400", "600"}
    assert re.search(r"<(i|em|b|strong)[ >]", exported.split("</style>", 1)[1]) is None


def test_the_fixed_set_is_compressed_and_three_faces_with_two_supplements():
    import saved_faces
    held = [(family, weight, payload) for family, weight, _, payload in saved_faces._FACES]
    assert held and [(family, weight) for family, weight, _ in held] == [
        ("EB Garamond", 400), ("EB Garamond", 600), ("Zij Interface", 400), ("Zij Interface Marks", 400), ("DejaVu Sans", 400)]
    for family, _, payload in held:
        assert base64.b64decode(payload)[:4] == b"wOF2", family


def test_nothing_at_run_time_needs_a_font_tool():
    allowed = {"json", "math", "re", "house_style", "saved_faces", "markup", "engine"}
    # The wheel's hub reckons a line's width by the kinds of its letters: no face is read.
    own = {"wheel.py": {"unicodedata"}}
    for name in ("wheel.py", "export_html.py", "saved_faces.py", "house_style.py"):
        heads = set()
        for node in ast.walk(ast.parse((ROOT / name).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                heads |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                heads.add((node.module or "").split(".")[0])
        permitted = allowed | own.get(name, set())
        assert heads <= permitted, (name, sorted(heads - permitted))
    for name in ("requirements.txt", "requirements-desktop.txt", "requirements-build.txt"):
        text = (ROOT / name).read_text(encoding="utf-8").lower()
        assert "fonttools" not in text and "brotli" not in text, name


def _walk(faces, stack_, weight, point):
    for family in stack_:
        own = [face for face in faces if face[0] == family]
        if not own:
            continue
        nearest = min({face[1] for face in own}, key=lambda w: abs(w - weight))
        if any(point in face[2] for face in own if face[1] == nearest):
            return family
    return None


def test_every_character_on_the_list_reaches_a_face_the_report_carries(exported):
    """Place names in other scripts are not on the list: they fall to the
    computer's own fonts, as ruled."""
    css = _style(exported)
    faces, rules = _faces(css), _without_faces(css)
    reading = _stack(re.search(r"font:16px/1\.55 ([^;]+);", rules).group(1))
    interface = _stack(re.search(r"table \{[^}]*font-family:([^;]+);", rules).group(1))
    required = CHARACTERS["required"]
    assert len(required) > 500
    for role, stack_, weight in (("prose", reading, 400), ("heading", reading, 600), ("table", interface, 400)):
        missing = [chr(p) for p in required if _walk(faces, stack_, weight, p) is None]
        assert missing == [], role


def test_every_character_a_report_prints_reaches_a_face_it_carries(exported):
    css = _style(exported)
    faces, rules = _faces(css), _without_faces(css)
    interface = _stack(re.search(r"table \{[^}]*font-family:([^;]+);", rules).group(1))
    text = re.sub(r"<[^>]+>", "", exported.split("</style>", 1)[1])
    printed = {c for c in text if not c.isspace() and unicodedata.category(c) not in ("Cf", "Cc")}
    assert len(printed) > 60
    missing = sorted(c for c in printed if _walk(faces, interface, 400, ord(c)) is None)
    assert missing == []


# --- Live and saved ---------------------------------------------------------------

def test_the_page_s_picture_carries_only_the_symbol_faces_and_a_saved_one_the_words_faces_too(engine, chart, bundle):
    import glyph_font
    drawn = pictures(engine, chart, bundle)
    assert drawn
    for name, svg in drawn.items():
        families = re.findall(r"@font-face\{font-family:'([^']+)'", svg)
        assert set(families) == {glyph_font.FAMILY}, name
        saved = engine["saved_svg"](svg)
        assert set(re.findall(r"@font-face\{font-family:'([^']+)'", saved)) == {
            glyph_font.FAMILY, "Zij Interface", "Zij Interface Marks", "DejaVu Sans"}, name
        assert re.sub(r"@font-face\{font-family:'(Zij Interface|Zij Interface Marks|DejaVu Sans)'.*?\}", "", saved) == svg, name
        ET.fromstring(saved)
        fetches_nothing(saved)
        fetches_nothing(svg)


def test_a_saved_picture_reaches_a_face_for_every_character_it_can_draw(engine, chart, bundle):
    saved = engine["saved_svg"](pictures(engine, chart, bundle)["natal"])
    faces = _faces(saved)
    stack_ = _stack(re.search(r'<svg [^>]*style="font-family:([^"]+)"', saved).group(1))
    drawn = {ord(c) for element in ET.fromstring(saved).iter() if element.tag.endswith("}text") for c in (element.text or "")}
    drawn |= set(CHARACTERS["required"])
    drawn = {p for p in drawn if unicodedata.category(chr(p)) not in ("Cf", "Cc") and p != 0xFE0E}
    missing = sorted(chr(p) for p in drawn if _walk(faces, stack_, 400, p) is None)
    assert missing == []


def _download_calls():
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute) and node.func.attr == "download_button"
            and any(k.arg == "mime" and getattr(k.value, "value", "") == "image/svg+xml" for k in node.keywords)]


def test_every_saved_picture_goes_through_the_one_helper_and_nothing_else_does():
    calls = _download_calls()
    assert len(calls) == 8
    for call in calls:
        data = call.args[1]
        assert isinstance(data, ast.Call) and getattr(data.func, "id", "") == "saved_svg", ast.dump(data)[:80]
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    uses = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "saved_svg"]
    assert len(uses) == 8, "the page's own picture carries no saved faces"


def test_the_report_s_own_words_stand(exported):
    """The frame the report's tables stand in: its colours and faces moved, and none
    of these words."""
    body = exported.split("</style>", 1)[1]
    assert re.search(r"<h1>Analysis: [^<]*</h1><p class='sub'>Exported [^<]* by this app\.</p><p class='scope'>", body)
    assert re.search(r"<title>Analysis: [^<]*</title>", exported)
    assert "<h2>Results</h2>" in body
    assert re.search(r"<details><summary>[^<]* &mdash; \d+ tables?</summary>", body)
    assert "<footer>" in body and body.rstrip().endswith("</footer></main></body></html>")


def test_the_report_s_title_for_the_annual_profection_says_so(exported):
    assert "<h3>Annual profection</h3>" in exported
    assert "<h3>Chronocrator Matrix</h3>" not in exported


def test_the_lot_of_fortune_s_glyph_is_a_symbol_face_s_wherever_it_can_be_drawn(engine, chart, bundle, exported):
    """In a picture, the report and the pages, the symbol family answers for it
    first, so it reaches neither DejaVu Sans's own file nor the computer."""
    import house_style
    fortune = 0x2297
    assert chr(fortune) in engine["POINT_GLYPHS"].values()
    for where, css in (("picture", pictures(engine, chart, bundle)["natal"]), ("report", _style(exported)),
                       ("page", house_style.PAGE_STYLE)):
        holders = [family for family, _, points in _faces(css) if fortune in points]
        assert holders and holders[0] == "TAE Symbols", where


def test_the_glyph_s_face_is_named_for_itself_and_keeps_its_source_s_copyright():
    from fontTools.ttLib import TTFont
    import glyph_font
    font = TTFont(io.BytesIO(base64.b64decode(glyph_font._FORTUNE_WOFF2_B64)))
    names = {record.nameID: str(record) for record in font["name"].names if record.platformID == 3}
    assert names[1] == names[4] == "TAE Symbols Fortune"
    assert "Bitstream" in names[0] and "Tavmjong Bah" in names[0], "the source's notice stays"
    for record in (names[1], names[3], names[4], names[6]):
        assert not {"Bitstream", "Vera", "Tavmjong", "Arev", "DejaVu"} & set(re.split(r"[ -]", record)), record
    assert font["head"].created == font["head"].modified == 2082844800, "no date of the cut's own"


@pytest.mark.parametrize("plant", [
    r"<STYLE>body{background:u\72l(ht\74p:\2f\2f 127.0.0.1:1/a)}</STYLE>",
    r"<style media=all>body{background:u\72l(ht\74p:\2f\2f 127.0.0.1:1/a)}</style>",
    r"<style media=all>@\69mport 'a.css';</style>",
    r"<style>body{background:u\72l(a.png)}",
    r"""<p style="background:u\72l(a.png)">x</p>""",
    """<p style="background:u&#114;l(&#104;ttp://127.0.0.1:1/a)">x</p>""",
    """<svg><rect style="fill:u&#114;l(a.png)"/></svg>""",
    """<embed src="a">""",
    """<object data="a"></object>""",
    """<video src="a"></video>""",
    """<audio src="a"></audio>""",
    "<link\trel=stylesheet href=a>",
    """<meta http-equiv="refresh" content="0;url=a">""",
])
def test_the_guard_refuses_what_a_browser_would_fetch(plant):
    with pytest.raises(AssertionError):
        fetches_nothing(plant)


@pytest.mark.parametrize("fine", [
    '<meta charset="utf-8">',
    "<p>&lt;script&gt; as typed in a name</p>",
    '<p style="color:var(--ink)">x</p>',
    '<style media="print">p{color:var(--ink)}</style>',
])
def test_the_guard_passes_what_fetches_nothing(fine):
    assert fetches_nothing(fine) is None


# Each of these a real browser fetched or ran, from a page served or a file opened off
# disk; no output of the program holds one.
A_BROWSER_FETCHED = {
    'imageset-attr-rel': '<p style="background:image-set(\'a.png\' 1x);width:9px;height:9px">x</p>',
    'imageset-attr-webkit': '<p style="background:-webkit-image-set(\'a.png\' 1x);width:9px;height:9px">x</p>',
    'imageset-attr-noquote': "<p style=background:image-set('a.png'1x)>x</p>",
    'imageset-attr-tab': '<p style="background:image-set(\'ht&Tab;tp:/127.0.0.1:1/a\' 1x)">x</p>',
    'imageset-sheet-rel': '<style>body{background:image-set("a.png" 1x)}</style>',
    'imageset-sheet-oneslash': '<style>body{background:image-set("http:/127.0.0.1:1/a" 1x)}</style>',
    'imageset-sheet-protorel': '<style>body{background:image-set("//127.0.0.1:1/a" 1x)}</style>',
    'decoy-title-hides-style': '<p title=\'style="x\' style="background:u\\72l(ht\\74p:\\2f\\2f 127.0.0.1:1/a)">x</p>',
    'decoy-datastyle-hides': '<p data-style="a" title=\'style="\' style="background:u\\72l(ht\\74p:\\2f\\2f 127.0.0.1:1/a)">x</p>',
    'svgstyle-entity': '<svg><style>rect{} body{background:&#117;rl(&#104;ttp://127.0.0.1:1/a)}</style></svg>',
    'svgstyle-bsol': '<svg><style>body{background:u&bsol;72l(ht&bsol;74p:&bsol;2f&bsol;2f 127.0.0.1:1/a)}</style></svg>',
    'svgstyle-import': "<svg><style>&#64;import '&#104;ttp://127.0.0.1:1/a';</style></svg>",
    'link-slash': '<link/rel=stylesheet href=&#104;ttp://127.0.0.1:1/a>',
    'input-image': '<input type=image src=&#104;ttp://127.0.0.1:1/a>',
    'body-background': '<body background=&#104;ttp://127.0.0.1:1/a>',
    'table-background': '<table background=&#104;ttp://127.0.0.1:1/a><tr><td>x</td></tr></table>',
    'td-background': '<table><tr><td background=&#104;ttp://127.0.0.1:1/a>x</td></tr></table>',
    'feimage': '<svg width=9 height=9><filter id=f><feImage href="&#104;ttp://127.0.0.1:1/a"/></filter><rect width=9 height=9 filter="u&#114;l(#f)"/></svg>',
    'pres-filter': '<svg width=9 height=9><rect width=9 height=9 filter="u&#114;l(&#104;ttp://127.0.0.1:1/a#a)"/></svg>',
    'pres-fill': '<svg width=9 height=9><rect width=9 height=9 fill="u&#114;l(&#104;ttp://127.0.0.1:1/a#a)"/></svg>',
    'pres-mask': '<svg width=9 height=9><rect width=9 height=9 mask="u&#114;l(&#104;ttp://127.0.0.1:1/a#a)"/></svg>',
    'pres-clip': '<svg width=9 height=9><rect width=9 height=9 clip-path="u&#114;l(&#104;ttp://127.0.0.1:1/a#a)"/></svg>',
    'pres-marker': '<svg width=9 height=9><path d="M0 0L9 9" marker-end="u&#114;l(&#104;ttp://127.0.0.1:1/a#a)"/></svg>',
    'pres-cursor': '<svg width=9 height=9><rect width=9 height=9 cursor="u&#114;l(&#104;ttp://127.0.0.1:1/a),auto"/></svg>',
    'set-filter': '<svg width=9 height=9><rect width=9 height=9><set attributeName=filter to="u&#114;l(&#104;ttp://127.0.0.1:1/a#a)"/></rect></svg>',
    'run-svg-onload': '<svg onload="fetch(\'//127.0.0.1:1/a\'.replace(/^/,\'ht\'+\'tp:\'))"></svg>',
    'run-body-onload': '<body onload="fetch(\'ht\'+\'tp:/\'+\'/127.0.0.1:1/a\')">',
    'run-details': '<details open ontoggle="fetch(\'ht\'+\'tp:/\'+\'/127.0.0.1:1/a\')">x</details>',
    'xml-pi': '<?xml-stylesheet type="text/css" href="http:/127.0.0.1:1/a"?><svg xmlns="http://www.w3.org/2000/svg"><rect width="9" height="9"/></svg>',
    'xml-style-entity': '<svg xmlns="http://www.w3.org/2000/svg"><style>rect{fill:u&#114;l(&#104;ttp://127.0.0.1:1/a#a)} svg{background:&#117;rl(&#104;ttp://127.0.0.1:1/a)}</style><rect width="9" height="9"/></svg>',
    'xml-svg-image2': '<s:svg xmlns:s="&#104;ttp://www.w3.org/2000/svg" xmlns:xl="&#104;ttp://www.w3.org/1999/xlink"><s:image xl:href="&#104;ttp://127.0.0.1:1/a" width="9" height="9"/></s:svg>',
    'xml-svg-use2': '<s:svg xmlns:s="&#104;ttp://www.w3.org/2000/svg" xmlns:xl="&#104;ttp://www.w3.org/1999/xlink"><s:use xl:href="&#104;ttp://127.0.0.1:1/a#a"/></s:svg>',
    'xml-svg-script2': '<s:svg xmlns:s="&#104;ttp://www.w3.org/2000/svg"><s:script>fetch("ht"+"tp:/"+"/127.0.0.1:1/a")</s:script></s:svg>',
    'xml-pres-filter': '<svg xmlns="http://www.w3.org/2000/svg"><rect width="9" height="9" filter="u&#114;l(&#104;ttp://127.0.0.1:1/a#a)"/></svg>',
    'xml-feimage': '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xl="&#104;ttp://www.w3.org/1999/xlink" width="9" height="9"><filter id="f"><feImage xl:href="&#104;ttp://127.0.0.1:1/a"/></filter><rect width="9" height="9" filter="u&#114;l(#f)"/></svg>',
    'xml-onload': '<svg xmlns="http://www.w3.org/2000/svg" onload="fetch(&quot;&#104;ttp://127.0.0.1:1/a&quot;)"><rect width="9" height="9"/></svg>',
    'title-class-img': '<title><p class="</title><img src=http:/127.0.0.1:1/a>">x</p></title>',
    'title-data-import': '<title><p data-chart="</title><style>@import \'http:/127.0.0.1:1/a\';</style>">x</p></title>',
    'title-svg-onload': '<title><p class="</title><svg onload=fetch(\'ht\'+\'tp:/\'+\'/127.0.0.1:1/a\')>">x</p></title>',
    'title-endtag-img': '<title></p class="</title><img src=http:/127.0.0.1:1/a>"></title>',
    'title-whole-head': '<head><meta charset=\'utf-8\'><title><g class="</title><link rel=stylesheet href=http:/127.0.0.1:1/a>"></g></title></head>',
    'charset-start-tag': '<meta charset="iso-2022-jp"></head><body><p class=\x1b$B class=" \x1b(B><img src=http:/127.0.0.1:1/a>">x</p>',
    'charset-end-tag': '<meta charset="iso-2022-jp"></head><body><p>x</p class=\x1b$B class=" \x1b(B><img src=http:/127.0.0.1:1/a>">',
}
assert len(A_BROWSER_FETCHED) == 43


@pytest.mark.parametrize("plant", A_BROWSER_FETCHED.values(), ids=A_BROWSER_FETCHED.keys())
def test_the_guard_refuses_each_form_a_browser_fetched(plant):
    with pytest.raises(AssertionError):
        fetches_nothing(plant)


# Where a browser and the guard's parser could part: each read the browser's way.
@pytest.mark.parametrize("plant", [
    "<svg><style><image href='http:/a'/></style></svg>",
    "<svg><title><img src=a></title></svg>",
    "<style/></p>{}body{background:url(a)}</style>",
    r'''<svg><rect fill="u\72l(http:/a)"/></svg>''',
    "<!--><img src=a>-->",
    "<svg><![CDATA[<img src=a>]]></svg>",
    '<!DOCTYPE svg [<!ENTITY e "x">]><svg></svg>',
    "<style>",
    "<base href=a>",
])
def test_the_guard_refuses_where_a_parser_and_a_browser_could_part(plant):
    with pytest.raises(AssertionError):
        fetches_nothing(plant)


@pytest.mark.parametrize("plant, named", [
    ("<marquee>x</marquee>", "<marquee>"), ('<p onclick="a">x</p>', "onclick"),
    ("<style>p{width:calc(1px)}</style>", "calc"), ("<style>@layer a;</style>", "@layer"),
])
def test_what_the_program_does_not_write_is_refused_by_name(plant, named):
    with pytest.raises(AssertionError, match=named):
        fetches_nothing(plant)


HOSTILE_NAMES = [
    "<script>fetch('x')</script>",
    "<img src=x onerror=fetch('y')>",
    '"><svg onload=fetch(1)>',
    '<link rel=stylesheet href=a>',
    '<embed src=a>',
    'Ann & Bo <3',
    'http://example.invalid/',
    'url(a.png)',
    '@import',
    'srcset',
    '<p style="background:url(a.png)">',
    "</style><style>@import 'a.css'</style>",
    '<meta http-equiv=refresh>',
    'style=//x',
    'style=a\\b',
]
assert len(HOSTILE_NAMES) == 15


@pytest.fixture(scope="module")
def analysis():
    at = make_app(page="sources")
    at.run(timeout=300)
    assert_no_exception(at, "the Sources page")
    return at.session_state["_analysis_export"]


@pytest.mark.parametrize("name", HOSTILE_NAMES)
def test_an_escaped_hostile_name_is_text_and_the_guard_passes_it(engine, chart, analysis, name):
    page = engine["analysis_html"]({**analysis, "chart": name})
    live = engine["generate_hybrid_svg"](chart, name, name, PLACE[0], PLACE[1], BIRTH, "LMT")
    saved = engine["saved_svg"](live)
    for output in (page, live, saved):
        assert html.escape(name) in output, "premise: the name is in the output, escaped"
        fetches_nothing(output)


@pytest.mark.parametrize("theme", [None, "dark"])
def test_the_guard_passes_real_pictures_at_the_pole_and_with_the_division_withheld(engine, chart, bundle, theme, monkeypatch):
    import ephemeris
    drawn = list(pictures(engine, chart, bundle, theme).values())
    at_the_pole = engine["calculate_traditional_chart"](BIRTH, 90.0, PLACE[1])
    drawn.append(engine["generate_hybrid_svg"](at_the_pole, "Invented", "Pole", 90.0, PLACE[1], BIRTH, "LMT", theme=theme))
    monkeypatch.setattr(ephemeris, "division_status", lambda *_: "tangency")
    withheld = engine["calculate_traditional_chart"](BIRTH, 70.0, PLACE[1])
    drawn.append(engine["generate_hybrid_svg"](withheld, "Invented", "North", 70.0, PLACE[1], BIRTH, "LMT", theme=theme))
    assert ephemeris.DIVISION_REASONS["tangency"] in drawn[-1]
    for svg in drawn:
        fetches_nothing(svg)
        fetches_nothing(engine["saved_svg"](svg))
