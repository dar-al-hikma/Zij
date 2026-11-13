# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""The pages' house style: what the app emits, and the fonts' route.

What only a browser shows (the faces drawn, the colour after a theme switch, a
canvas's face) has no leg here: no browser is among the suite's requirements.
These pins hold the emitted text those facts rest on.
"""
from __future__ import annotations

import ast
import base64
import hashlib
import importlib.util
import io
import os
import re
import socket
import subprocess
import sys
import threading
import tomllib
import unicodedata

import pytest
from fontTools.ttLib import TTFont

from conftest import APP_PATH, EXECUTABLE_DIR, source_files
from loopback_ports import claimed_port
import shipped_modules

CONFIG_PATH = EXECUTABLE_DIR / ".streamlit" / "config.toml"
FONTS = EXECUTABLE_DIR / "fonts"
LICENSES = EXECUTABLE_DIR / "licenses"
PORTS = range(8597, 8601)

# Everything the config held before it held a theme.
THE_DOOR_S_CONFIG = {
    "runner": {"magicEnabled": False},
    "client": {"toolbarMode": "minimal", "allowedOrigins": []},
    "server": {"address": "127.0.0.1", "allowedHosts": ["127.0.0.1"], "enableCORS": True, "corsAllowedOrigins": [],
               "enableXsrfProtection": True, "xsrfCookieSameSite": "lax", "scriptHealthCheckEnabled": False,
               "enableStaticServing": False, "headless": True, "maxUploadSize": 0},
    "browser": {"serverAddress": "127.0.0.1", "gatherUsageStats": False},
    "global": {"developmentMode": False, "e2eTest": False},
}
# The ten colours of the page the house style was adopted from.
ADOPTED = {"light": {"background": "#F7F3E8", "panel": "#FFFDF6", "panel2": "#EFE8D8", "ink": "#242733",
                     "muted": "#596174", "brass": "#895D16", "steel": "#315D80", "line": "#C8BEA8",
                     "edge": "#8A806E", "madder": "#A53E2B"},
           "dark": {"background": "#070A12", "panel": "#0D1220", "panel2": "#151B2B", "ink": "#EAE3D2",
                    "muted": "#8B91A6", "brass": "#E3AA3E", "steel": "#7FB6E0", "line": "#242E47",
                    "edge": "#606B86", "madder": "#E4674C"}}
# A grid's rules, and a text table's, quieter than the page's own.
QUIET_RULES = {'light': '#E0D8C7', 'dark': '#1A2236'}
GENERICS = {"serif", "sans-serif", "monospace"}
FAMILY_NAME_IDS = {1, 3, 4, 6, 16, 17, 18, 20, 21, 22, 25}
THE_LETTERS_A_LABEL_DRAWS_WHOLE = "Ḥḥṣṭḍẓ"


def _config():
    return tomllib.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _page_style():
    tree = ast.parse((EXECUTABLE_DIR / "house_style.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "PAGE_STYLE":
            return ast.literal_eval(node.value)
    raise AssertionError("house_style.py has no PAGE_STYLE")


def _rules(css):
    """The stylesheet's rules, in order, as (selector, declarations)."""
    body = css.removeprefix("<style>").removesuffix("</style>")
    return [(m[0], m[1]) for m in re.findall(r"([^{}]+)\{([^{}]*)\}", body)]


def _rule_with(css, selector_part):
    found = [r for r in _rules(css) if selector_part in r[0]]
    assert found, selector_part
    return found[0]


def _stacks():
    """Every stack the app emits: the theme's three and each in its stylesheet."""
    theme = _config()["theme"]
    stacks = {key: theme[key] for key in ("font", "headingFont", "codeFont")}
    for selector, declarations in _rules(_page_style()):
        if selector.startswith("@font-face"):
            continue
        for value in re.findall(r"font-family:([^;]+)", declarations):
            stacks[selector[:40]] = value
    return stacks


def _names(stack):
    return [part.strip().strip("\"'") for part in stack.split(",")]


def _marks_faces():
    """{weight: font} of the embedded marks face."""
    faces = {}
    for selector, declarations in _rules(_page_style()):
        if selector == "@font-face" and "'Zij Interface Marks'" in declarations:
            data = base64.b64decode(re.search(r"base64,([A-Za-z0-9+/=]+)", declarations).group(1))
            faces[int(re.search(r"font-weight:(\d+)", declarations).group(1))] = (TTFont(io.BytesIO(data)), declarations)
    return faces


def _font_files():
    return sorted(path.name for path in FONTS.iterdir() if path.name != "OFL.txt")


def _server_limits():
    spec = importlib.util.spec_from_file_location("server_limits_under_test", EXECUTABLE_DIR / "server_limits.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- The config ---------------------------------------------------------------

def test_the_door_s_options_are_what_they_were():
    config = _config()
    assert {key: value for key, value in config.items() if key != "theme"} == THE_DOOR_S_CONFIG


def test_the_theme_follows_the_adopted_page():
    theme = _config()["theme"]
    assert theme["baseFontSize"] == 16, "it would drag the sidebar and the page's padding with it"
    assert theme["headingFontSizes"][:4] == ["44px", "32px", "25px", "22px"]
    assert set(theme["headingFontWeights"]) == {600}
    assert "base" not in theme
    for mode, colours in ADOPTED.items():
        section, sidebar = theme[mode], theme[mode]["sidebar"]
        assert section["backgroundColor"] == colours["background"]
        assert section["secondaryBackgroundColor"] == colours["panel2"]
        assert section["textColor"] == colours["ink"]
        assert section["primaryColor"] == colours["brass"]
        assert section["linkColor"] == colours["steel"]
        assert section["redColor"] == colours["madder"]
        assert section["borderColor"] == colours["edge"]
        assert section["dataframeBorderColor"] == QUIET_RULES[mode]
        assert section["dataframeHeaderTextColor"] == colours["muted"]
        assert sidebar["backgroundColor"] == colours["panel"]


def test_every_font_face_goes_by_the_route_and_each_file_is_registered():
    limits = _server_limits()
    faces = _config()["theme"]["fontFaces"]
    urls = [face["url"] for face in faces]
    assert urls
    assert all(url.startswith(limits.FONT_ROUTE) for url in urls), urls
    assert {url.removeprefix(limits.FONT_ROUTE) for url in urls} == set(limits.FONT_FILES) == set(_font_files())


def test_the_fonts_the_build_carries_are_the_route_s():
    datas = shipped_modules.spec_datas(EXECUTABLE_DIR)
    carried = {source.removeprefix("fonts/") for source, dest in datas if dest == "fonts" and not source.endswith("OFL.txt")}
    assert carried == set(_server_limits().FONT_FILES)
    assert (".streamlit/config.toml", ".streamlit") in datas


def test_the_stop_check_fetches_a_font_on_the_route():
    source = (EXECUTABLE_DIR / ".github/scripts/stop_check.py").read_text(encoding="utf-8")
    path = re.search(r'^FONT_PATH = "([^"]+)"$', source, re.M).group(1)
    limits = _server_limits()
    assert path.removeprefix(limits.FONT_ROUTE) in limits.FONT_FILES
    assert "if not _answers_font(launch.port):" in source


# --- The stacks and names -------------------------------------------------------

def test_the_symbol_faces_come_first_in_every_emitted_stack():
    stacks = _stacks()
    assert len(stacks) >= 5, stacks
    for where, stack in stacks.items():
        assert _names(stack)[:2] == ["TAE Symbols", "TAE Symbols Sun"], where


def test_every_stack_ends_in_a_generic_and_names_only_registered_families():
    registered = {face["family"].strip('"') for face in _config()["theme"]["fontFaces"]}
    registered |= {re.search(r"font-family:'([^']+)'", d).group(1) for s, d in _rules(_page_style()) if s == "@font-face"}
    stacks = list(_stacks().items())
    assert stacks
    for where, stack in stacks:
        names = _names(stack)
        assert names[-1] in GENERICS, where
        assert set(names[:-1]) <= registered, (where, set(names[:-1]) - registered)


def _reserved_names():
    """The names each licence reserves, by its own text."""
    reserved = set()
    for path in LICENSES.glob("*OFL*"):
        reserved.update(re.findall(r'with Reserved Font Name "([^"]+)"', path.read_text(encoding="utf-8")))
    dejavu = (LICENSES / "dejavu-Bitstream-Arev-DejaVu.txt").read_text(encoding="utf-8")
    assert 'not containing either the words "Bitstream" or the word\n"Vera"' in dejavu
    assert 'the words "Tavmjong Bah" or the word "Arev"' in dejavu
    return reserved | {"Bitstream", "Vera", "Tavmjong Bah", "Arev"}


def test_the_licences_reserve_what_this_build_was_named_around():
    assert _reserved_names() == {"Plex", "Bitstream", "Vera", "Tavmjong Bah", "Arev"}
    # EB Garamond's licence reserves no name.
    for name in ("eb-garamond-OFL.txt",):
        assert "with Reserved Font Name" not in (LICENSES / name).read_text(encoding="utf-8")


def test_no_emitted_family_carries_a_reserved_name():
    reserved = [name.lower() for name in _reserved_names()]
    families = {face["family"] for face in _config()["theme"]["fontFaces"]}
    families |= {name for stack in _stacks().values() for name in _names(stack)}
    families |= {re.search(r"font-family:'([^']+)'", d).group(1) for s, d in _rules(_page_style()) if s == "@font-face"}
    assert reserved and families
    urls = [face["url"] for face in _config()["theme"]["fontFaces"]]
    assert urls
    lines = [line for module in source_files()
             for line in module.read_text(encoding="utf-8").splitlines()
             if "font-family" in line or "font_family" in line]
    assert any("TAE Symbols" in line for line in lines) and any("_WHEEL_FONT" in line for line in lines)
    for text in sorted(families) + urls + lines:
        assert [name for name in reserved if name in text.lower()] == [], text[:120]


def test_no_font_is_named_with_a_reserved_name():
    reserved = [name.lower() for name in _reserved_names()]
    fonts = {path.name: TTFont(path) for path in FONTS.glob("*.ttf")}
    fonts.update({f"marks {weight}": font for weight, (font, _) in _marks_faces().items()})
    records = [(where, record.nameID, str(record)) for where, font in fonts.items() for record in font["name"].names
               if record.nameID in FAMILY_NAME_IDS]
    assert reserved and records
    for where, name_id, text in records:
        assert [name for name in reserved if name in text.lower()] == [], (where, name_id, text)


def test_the_figures_of_the_interface_face_are_tabular_by_design():
    """The adopted page sets numbers with tabular-nums; IBM Plex Sans Condensed
    has no such feature to lose, for all its figures share one advance."""
    for weight in (400, 600):
        font = TTFont(FONTS / f"zij-interface-{weight}.ttf")
        cmap, hmtx = font.getBestCmap(), font["hmtx"]
        assert len({hmtx[cmap[0x30 + n]][0] for n in range(10)}) == 1


# --- The marks face ---------------------------------------------------------------

def _mark_offset(font, base, mark):
    for lookup in font["GPOS"].table.LookupList.Lookup:
        for table in lookup.SubTable:
            table = getattr(table, "ExtSubTable", table)
            if table.LookupType == 4 and base in table.BaseCoverage.glyphs and mark in table.MarkCoverage.glyphs:
                record = table.MarkArray.MarkRecord[table.MarkCoverage.glyphs.index(mark)]
                anchor = table.BaseArray.BaseRecord[table.BaseCoverage.glyphs.index(base)].BaseAnchor[record.Class]
                if anchor is not None:
                    return anchor.XCoordinate - record.MarkAnchor.XCoordinate, anchor.YCoordinate - record.MarkAnchor.YCoordinate
    return None


def _outline(font, name):
    coordinates, ends, flags = font["glyf"][name].getCoordinates(font["glyf"])
    return list(coordinates), list(ends), list(flags)


@pytest.mark.parametrize("weight", [400, 600])
def test_each_marked_letter_is_the_interface_face_s_own_letter_and_mark(weight):
    marks = _marks_faces()[weight][0]
    plex = TTFont(FONTS / f"zij-interface-{weight}.ttf")
    plex_cmap = plex.getBestCmap()
    letters = marks.getBestCmap()
    assert letters
    assert set(THE_LETTERS_A_LABEL_DRAWS_WHOLE) <= {chr(point) for point in letters}
    for point, name in letters.items():
        assert point not in plex_cmap, f"U+{point:04X}: the face holds only what the interface face lacks"
        base, mark = unicodedata.normalize("NFD", chr(point))
        base_name, mark_name = plex_cmap[ord(base)], plex_cmap[ord(mark)]
        glyph = marks["glyf"][name]
        assert glyph.isComposite(), chr(point)
        drawn_base, drawn_mark = glyph.components
        assert _outline(marks, drawn_base.glyphName) == _outline(plex, base_name), chr(point)
        assert _outline(marks, drawn_mark.glyphName) == _outline(plex, mark_name), chr(point)
        assert (drawn_base.x, drawn_base.y) == (0, 0), chr(point)
        assert (drawn_mark.x, drawn_mark.y) == _mark_offset(plex, base_name, mark_name), chr(point)
        assert marks["hmtx"][name][0] == plex["hmtx"][base_name][0], chr(point)


def test_the_marks_face_comes_in_every_interface_weight_and_the_same_letters():
    weights = sorted(int(face["weight"]) for face in _config()["theme"]["fontFaces"] if face["family"] == '"Zij Interface"')
    marks = _marks_faces()
    assert sorted(marks) == weights
    letters = {weight: set(font.getBestCmap()) for weight, (font, _) in marks.items()}
    assert marks and letters
    assert all(held == letters[weights[0]] for held in letters.values())
    for font, declarations in marks.values():
        assert "url(data:font/woff2;base64," in declarations, "embedded: no route"
        assert "unicode-range:" in declarations


def test_the_marks_face_is_under_the_notice_that_names_it():
    notice = (FONTS / "OFL.txt").read_text(encoding="utf-8")
    assert "Zij Interface Marks" in notice and 'with Reserved Font Name "Plex"' in notice


def _glyph_font_payloads():
    tree = ast.parse((EXECUTABLE_DIR / "glyph_font.py").read_text(encoding="utf-8"))
    constants = {n.targets[0].id: n.value.value for n in tree.body if isinstance(n, ast.Assign)
                 and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Constant)}
    return {"tae-symbols-400.ttf": base64.b64decode(constants["_SYMBOLS_WOFF2_B64"]),
            "tae-symbols2-400.ttf": base64.b64decode(constants["_SYMBOLS2_WOFF2_B64"])}


def test_the_symbol_faces_are_glyph_font_s_own_tables():
    """The two files the route answers hold what glyph_font.py embeds, table
    for table: only the container differs."""
    payloads = _glyph_font_payloads()
    assert len(payloads) == 2
    for name, payload in payloads.items():
        served, embedded = TTFont(FONTS / name, recalcTimestamp=False), TTFont(io.BytesIO(payload), recalcTimestamp=False)
        tables = sorted(tag for tag in embedded.keys() if tag != "GlyphOrder")
        assert tables and sorted(tag for tag in served.keys() if tag != "GlyphOrder") == tables, name
        for tag in tables:
            kept, held = served.getTableData(tag), embedded.getTableData(tag)
            if tag == "head":   # bytes 8 to 11 are the whole file's checksum, which is the container's
                kept, held = kept[:8] + kept[12:], held[:8] + held[12:]
            assert kept == held, (name, tag)


def test_every_face_the_route_answers_is_uncompressed_truetype():
    """A search can read an uncompressed font's tables, and the release hook
    refuses any other kind (docs/RELEASING.md)."""
    held = _font_files()
    assert len(held) == 9
    for name in held:
        assert name.endswith(".ttf"), name
        assert (FONTS / name).read_bytes()[:4] == b"\x00\x01\x00\x00", name
        assert TTFont(FONTS / name).flavor is None, name
    assert sorted(path.name for path in FONTS.iterdir() if path.suffix in (".woff", ".woff2", ".otf")) == []


def test_the_two_embedded_faces_stay_compressed():
    """Held as data URIs, where a page's size counts; the hook reads them as
    text, as it reads glyph_font.py."""
    payloads = list(_glyph_font_payloads().values())
    payloads += [base64.b64decode(re.search(r"base64,([A-Za-z0-9+/=]+)", declarations).group(1))
                 for selector, declarations in _rules(_page_style()) if selector == "@font-face"]
    assert len(payloads) == 5
    assert all(payload[:4] == b"wOF2" for payload in payloads)


# --- The stylesheet ---------------------------------------------------------------

def test_nothing_sets_a_page_width():
    """A passage has its measure, and a column holding a table its least width;
    nothing else in the stylesheet sets a width, so the page is as wide as the window.
    The page's own box is named once, for the Sky's top padding alone."""
    css = _page_style()
    assert "block-container" not in css
    assert [rule for rule in _rules(css) if "stMainBlockContainer" in rule[0]] == [
        ('[data-testid="stMainBlockContainer"]:has(.st-key-zij-sky-controls)', "padding-top:76px;")]
    passage = ":is(p,li,blockquote)"
    widths = [rule for rule in _rules(css) if "max-width" in rule[1] or "min-width" in rule[1]]
    assert widths
    for selector, declarations in widths:
        # A strip of section names lifts the passage's measure from its own line, setting none.
        if "max-width:none" in declarations and "min-width" not in declarations:
            assert ".st-key-days-sections" in selector and "max-width:none" in declarations, selector
            continue
        if "min-width" in declarations:
            assert selector == '[data-testid="stColumn"]:has(.zij-table,[data-testid="stDataFrame"])', selector
        else:
            assert all(passage in part for part in selector.split(":not(")[0:1]), selector
    assert 'layout="wide"' in APP_PATH.read_text(encoding="utf-8")


READING_RULE = ('[data-testid="stMain"] [data-testid="stMarkdown"] :is(p,li,blockquote):not([data-testid="stCaptionContainer"] *),'
                '[class*="st-key-reading-"] :is(p,li,blockquote):not([data-testid="stCaptionContainer"] *)')
DENSE_RULE = '[data-testid="stExpander"] [data-testid="stMarkdown"] :is(p,li,blockquote):not([data-testid="stCaptionContainer"] *)'


def test_the_prose_size_is_read_by_the_reading_rule_alone():
    css = _page_style()
    assert css.count("var(--zij-prose-size)") == 1 and css.count("var(--zij-prose-line-height)") == 1
    selector, declarations = _rule_with(css, "st-key-reading-")
    assert selector == READING_RULE
    assert "font-size:var(--zij-prose-size)" in declarations
    assert '"EB Garamond"' in declarations
    assert re.match(r":root\{--zij-prose-size:17px;", css.removeprefix("<style>"))
    assert re.search(r"^PROSE_WIDTH = 680$", APP_PATH.read_text(encoding="utf-8"), re.M)


def test_a_passage_inside_an_expander_takes_the_dense_face_after_the_reading_rule():
    """Of one weight, so the later stands: open text in the reading face, an
    expander's in the interface face, wherever the expander opens."""
    rules = _rules(_page_style())
    reading = rules.index(next(rule for rule in rules if rule[0] == READING_RULE))
    dense = rules.index(next(rule for rule in rules if rule[0] == DENSE_RULE))
    assert reading < dense
    assert "font-size:var(--zij-dense-size)" in rules[dense][1] and "Zij Interface" in rules[dense][1]
    assert '"EB Garamond"' not in rules[dense][1]


def test_the_reading_rule_reaches_a_dialog_by_the_key_as_a_page_by_its_place():
    selector = _rule_with(_page_style(), "st-key-reading-")[0]
    for place in ("stSidebar", "stDialog", "stApp", "body"):
        assert place not in selector
    assert selector == READING_RULE


def test_small_text_holds_inside_reading_text_and_inside_a_table():
    css = _page_style()
    rules = _rules(css)
    reading = next(i for i, r in enumerate(rules) if r[0] == READING_RULE)
    small = next(i for i, r in enumerate(rules) if "font-size:var(--zij-small-size)" in r[1])
    table = next(i for i, r in enumerate(rules) if "font-size:var(--zij-table-size)" in r[1])
    assert reading < small and table < small, "of the same weight, so the later rule stands"
    for selector in ('[data-testid="stCaptionContainer"] p', "cite", ".zij-locator", "caption", " dt"):
        assert selector in rules[small][0], selector
    assert re.search(r"--zij-small-size:14px", css)


def test_a_table_s_own_text_size_is_its_own_token():
    css = _page_style()
    selector, declarations = _rule_with(css, ":is(table,td,th)")
    assert "font-size:var(--zij-table-size)" in declarations and "zij-prose" not in declarations
    for drawn in ('[data-testid="stTable"]', '[data-testid="stHtml"]', '[data-testid="stMarkdownContainer"]'):
        assert drawn in selector, drawn
    assert re.search(r"--zij-table-size:14px", css)
    # Text in a cell or a definition takes the cell's size, wherever it stands.
    selector, declarations = _rule_with(css, ":is(td,th,dd,dt,caption) :is(p,li,blockquote)")
    assert '[data-testid="stMain"]' in selector and '[data-testid="stExpander"]' in selector
    assert '[class*="st-key-reading-"]' in selector and declarations == "font:inherit;"
    assert "font-size:var(--zij-definition-size)" in _rule_with(css, " dd")[1]


def test_muted_text_is_resolved_by_the_page_under_either_theme():
    css = _page_style()
    selector, declarations = _rule_with(css, '[data-testid="stCaptionContainer"],cite')
    light, dark = ADOPTED["light"]["muted"], ADOPTED["dark"]["muted"]
    fallback, resolved = declarations.index("color:color-mix("), declarations.index(f"color:light-dark({light},{dark})")
    assert fallback < resolved, "the fallback first, for a browser without light-dark()"
    assert "opacity:1" in declarations
    assert declarations.count("color:") == 2
    assert "color:inherit" in [r for r in _rules(css) if r[0] == '[data-testid="stCaptionContainer"] p'][0][1]


def test_a_dialog_or_a_popover_resolves_colours_under_the_theme_showing():
    """They stand outside the element Streamlit gives the theme's colour scheme,
    so light-dark() there needs one from the page. A launch shows Light until the
    reader presses the sidebar's button (a minimal toolbar has no menu to choose
    another) and a choice has its own rule, after this one; this rule stands for a
    run no launch's server holds, which follows the computer."""
    assert "@media (prefers-color-scheme:dark){body{color-scheme:dark;}}" in _page_style()
    assert _config()["client"]["toolbarMode"] == "minimal"


def test_a_primary_button_s_label_is_written_to_be_read_on_its_ground():
    declarations = _rule_with(_page_style(), '[data-testid="stBaseButton-primary"]')[1]
    assert declarations == "color:light-dark(#FFFDF6,#070A12);"


def test_a_quotation_is_drawn_at_the_ink_s_full_strength():
    assert _rule_with(_page_style(), "blockquote{"[:-1])[1]
    assert '[data-testid="stMarkdownContainer"] blockquote{opacity:1;}' in _page_style()


def test_the_stylesheet_is_one_constant_emitted_past_the_door():
    source = APP_PATH.read_text(encoding="utf-8")
    assert "<style" not in source, "the stylesheet lives in house_style.py"
    tree = ast.parse(source)
    order = {}
    calls = []
    for position, node in enumerate(tree.body):
        text = ast.get_source_segment(source, node) or ""
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            if text.startswith("_admit_only_the_window("):
                order["door"] = position
            elif text.startswith("st.set_page_config("):
                order["config"] = position
            elif text == "st.html(house_style.PAGE_STYLE)":
                order["style"] = position
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "st.html":
            calls.append(ast.unparse(node))
    assert order["door"] < order["config"] < order["style"], order
    assert calls
    assert calls.count("st.html(house_style.PAGE_STYLE)") == 1
    assert not any("VIEWER_THEME" in call for call in calls), "the page resolves its colours, not the script"
    style_module = (EXECUTABLE_DIR / "house_style.py").read_text(encoding="utf-8")
    assert "import" not in [t for line in style_module.splitlines() for t in line.split()[:1]]


# --- The route, live -------------------------------------------------------------

@pytest.fixture(scope="module")
def font_port(tmp_path_factory):
    yield from claimed_port(PORTS, tmp_path_factory.getbasetemp().parent / "house-style-ports")


@pytest.fixture(scope="module")
def font_server(font_port, tmp_path_factory):
    """The source run, its server held by server_limits as a real run's is."""
    from test_srcrun_door_2026_10_15 import _ON_PORT
    folder = tmp_path_factory.mktemp("house-style-home")
    environment = {name: value for name, value in os.environ.items() if not name.upper().startswith("STREAMLIT_")}
    environment.update(HOME=str(folder), USERPROFILE=str(folder), APPDATA=str(folder / "appdata"),
                       LOCALAPPDATA=str(folder / "local"), XDG_DATA_HOME=str(folder / "data"),
                       XDG_CONFIG_HOME=str(folder / "config"))
    process = subprocess.Popen([sys.executable, "-c", _ON_PORT, str(EXECUTABLE_DIR), str(font_port)],
                               cwd=folder, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    ready = threading.Event()
    seen = []

    def read():
        for line in process.stdout:
            seen.append(line)
            if "Open the app at" in line:
                ready.set()

    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        assert ready.wait(120), "".join(seen)[-2000:]
        yield font_port
    finally:
        process.terminate()
        try:
            process.wait(30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        reader.join(10)


def _ask(port, target, method="GET", host=None, extra=()):
    """One request exactly as written, as (status, headers, body)."""
    lines = [f"{method} {target} HTTP/1.1", f"Host: {host or f'127.0.0.1:{port}'}", "Connection: close", *extra, "", ""]
    with socket.create_connection(("127.0.0.1", port), timeout=30) as connection:
        connection.sendall("\r\n".join(lines).encode("latin-1"))
        data = b""
        while chunk := connection.recv(1 << 16):
            data += chunk
    head, _, body = data.partition(b"\r\n\r\n")
    first, *rest = head.decode("latin-1").split("\r\n")
    headers = {}
    for line in rest:
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return int(first.split()[1]), headers, body


def _is_no_font_and_no_file(answer):
    status, headers, body = answer
    assert not (status == 200 and headers.get("content-type", "").startswith("font/")), answer[:2]
    assert not body.startswith(b"wOF2")
    assert b"Licensed under the GNU" not in body and b"enableStaticServing" not in body


def test_the_stop_check_s_probe_tells_a_font_from_anything_else(tmp_path):
    """Its fetch of a font, against a server of each kind: only a real answer passes."""
    source = (EXECUTABLE_DIR / ".github/scripts/stop_check.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    probe = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_answers_font")
    import urllib.error
    import urllib.request
    space = {"urllib": urllib, "OSError": OSError, "ValueError": ValueError, "PROBE_SECONDS": 5, "FONT_PATH": "/f"}
    exec(ast.get_source_segment(source, probe), space)

    def served(status, kind, body):
        listener = socket.create_server(("127.0.0.1", 0))

        def answer():
            connection, _ = listener.accept()
            with connection:
                connection.recv(4096)
                connection.sendall(f"HTTP/1.1 {status} X\r\nContent-Type: {kind}\r\nContent-Length: {len(body)}\r\n"
                                   "Connection: close\r\n\r\n".encode("latin-1") + body)

        thread = threading.Thread(target=answer, daemon=True)
        thread.start()
        try:
            return space["_answers_font"](listener.getsockname()[1])
        finally:
            thread.join(10)
            listener.close()

    truetype = b"\x00\x01\x00\x00"
    assert served(200, "font/ttf", truetype + b"rest") is True
    assert served(404, "font/ttf", truetype) is False
    assert served(200, "text/html", truetype) is False
    assert served(200, "font/ttf", b"<html>") is False
    assert served(200, "font/woff2", b"wOF2rest") is False
    assert served(200, "font/ttf", b"wOF2rest") is False


def test_each_listed_font_is_answered_as_a_font(font_server):
    limits = _server_limits()
    names = sorted(limits.FONT_FILES)
    assert names
    for name in names:
        status, headers, body = _ask(font_server, limits.FONT_ROUTE + name)
        assert status == 200, name
        assert headers["content-type"] == "font/ttf", name
        assert headers["content-length"] == str(len(body)), name
        assert hashlib.sha256(body).digest() == hashlib.sha256((FONTS / name).read_bytes()).digest(), name


@pytest.mark.parametrize("target", [
    "/zij-font/",
    "/zij-font",
    "/zij-font/OFL.txt",
    "/zij-font/no-such-font.ttf",
    "/zij-font/eb-garamond-400.woff2",
    "/zij-font/eb-garamond-400.ttf/",
    "/zij-font/EB-GARAMOND-400.TTF",
    "/zij-font/eb-garamond-400.ttf.txt",
    "/zij-font/../app.py",
    "/zij-font/../../app.py",
    "/zij-font/%2e%2e/app.py",
    "/zij-font/%2e%2e%2fapp.py",
    "/zij-font/..%2fapp.py",
    "/zij-font/..%2f.streamlit%2fconfig.toml",
    "/zij-font/..\\app.py",
    "/fonts/eb-garamond-400.ttf",
    "/app/static/eb-garamond-400.ttf",
    "/app/static/fonts/eb-garamond-400.ttf",
])
def test_no_other_name_or_spelling_is_answered_with_a_file(font_server, target):
    _is_no_font_and_no_file(_ask(font_server, target))


@pytest.mark.parametrize("method", ["HEAD", "POST", "PUT", "DELETE", "OPTIONS"])
def test_only_a_get_is_answered(font_server, method):
    status, _headers, body = _ask(font_server, "/zij-font/eb-garamond-400.ttf", method=method)
    assert status == 404 and body == b""


@pytest.mark.parametrize("host", ["evil.example", "evil.example:80", "localhost"])
def test_the_host_check_comes_before_the_font(font_server, host):
    status, headers, body = _ask(font_server, "/zij-font/eb-garamond-400.ttf", host=host)
    assert status == 403 and body == b"Forbidden", (host, headers)


def test_another_site_is_told_nothing_about_a_font(font_server):
    for extra in (("Origin: http://evil.example",), ("Origin: null",), ()):
        status, headers, _body = _ask(font_server, "/zij-font/eb-garamond-400.ttf", extra=extra)
        assert status == 200
        assert not [name for name in headers if name.startswith("access-control-")], (extra, headers)
        assert headers["x-content-type-options"] == "nosniff"


# --- The sidebar's picker and its delete button -------------------------------------

def test_the_delete_button_stands_level_with_the_saved_charts_field():
    """A selectbox carries its label above its field and a button has none, so
    the row aligns on the bottom edge: at the top, the button stood level with
    the label. The browser is what shows the two boxes meet; the suite has
    none, and this is the call the page rests on."""
    tree = ast.parse((EXECUTABLE_DIR / "app.py").read_text(encoding="utf-8"))
    calls = [node.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
             and isinstance(node.targets[0], ast.Tuple)
             and [getattr(target, "id", None) for target in node.targets[0].elts] == ["load_col", "del_col"]]
    assert len(calls) == 1
    assert ast.unparse(calls[0].func) == "st.sidebar.columns"
    assert {keyword.arg: ast.literal_eval(keyword.value) for keyword in calls[0].keywords} == {"vertical_alignment": "bottom"}
