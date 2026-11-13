# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""The strip of section names on Days and months: links, place and stylesheet.

That the strip stays stuck, that a jump lands in one step and that a click runs
no script are facts only a browser shows, and no browser is among the suite's
requirements. These pins hold what those facts rest on: the links and headings a
page draws, where the strip stands in the page's code, and the emitted rules.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import re
import tomllib

import pytest

import house_style
from conftest import APP_PATH, EXECUTABLE_DIR, make_app
from streamlit.testing.v1.element_tree import Block

KEY = "days-sections"
# Every strip is held by one set of rules (the strips on The releaser and on Fardar and
# ages: test_jump_strips_2026_11_09.py); Days and months's is the first named in it.
def _strip_keys():
    spec = importlib.util.spec_from_file_location("build_theme", EXECUTABLE_DIR / "tools" / "house_style" / "build_theme.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.JUMP_STRIPS)


STRIP = ":is(" + ",".join(f".st-key-{key}" for key in _strip_keys()) + ")"
SECTIONS = [("The small days", "the-small-days"), ("The mighty days", "the-mighty-days"),
            ("The nine methods", "the-nine-methods"), ("The seven indicators", "the-seven-indicators")]
LINK = re.compile(r"\[([^\]]+)\]\(#([^)]+)\)")
# What a grid's toolbar buttons stand at in the installed Streamlit, as read in a browser.
GRID_TOOLBAR_LAYER = 101


def _function(name):
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)


def _is_call(node, dotted):
    return isinstance(node, ast.Call) and ast.unparse(node.func) == dotted


def _statement_calls(statement, dotted):
    return isinstance(statement, ast.Expr) and _is_call(statement.value, dotted)


def _rule(selector):
    """The declarations of the one rule written for exactly this selector."""
    found = re.findall(r"(?:^|[}>])" + re.escape(selector) + r"\{([^}]*)\}", house_style.PAGE_STYLE)
    assert len(found) == 1, f"{selector}: {len(found)} rules"
    return found[0]


def _theme(mode):
    config = tomllib.loads((EXECUTABLE_DIR / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    return config["theme"][mode]


def _both(token):
    return f"light-dark({_theme('light')[token]},{_theme('dark')[token]})"


def _ratio(a, b):
    def luminance(value):
        channels = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
        return sum(c * w for c, w in zip(linear, (.2126, .7152, .0722)))
    low, high = sorted((luminance(a), luminance(b)))
    return (high + .05) / (low + .05)


@pytest.fixture(scope="module")
def days():
    at = make_app(page="days").run()
    assert not at.exception
    return at


# --- the links --------------------------------------------------------------------

def _strips(at):
    return [m.value for m in at.main.markdown if len(LINK.findall(m.value)) > 1]


def test_each_name_links_to_a_heading_the_page_draws(days):
    strips = _strips(days)
    assert len(strips) == 1
    assert LINK.findall(strips[0]) == SECTIONS
    assert [h.proto.anchor for h in days.main.subheader if h.proto.anchor] == [anchor for _, anchor in SECTIONS]


def test_each_name_is_its_heading_s_own_first_words(days):
    for (name, _), heading in zip(SECTIONS, [h for h in days.main.subheader if h.proto.anchor], strict=True):
        assert heading.value.startswith(name)


def test_a_name_carries_no_citation(days):
    names = [name for name, _ in LINK.findall(_strips(days)[0])]
    assert len(names) == len(SECTIONS)
    for name in names:
        assert not re.search(r"[\d(),.]|\bPN\b|\bIX\b", name), name


def test_the_recovery_panel_draws_no_strip():
    at = make_app(page="days")
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = "zzzz-no-such-city"
    at.run()
    assert not at.exception
    assert at.main.error and not _strips(at) and not at.main.subheader


# --- where it stands in the code --------------------------------------------------

def test_the_strip_stands_on_the_page_under_its_title_and_past_the_recovery_return():
    body = _function("page_days").body
    assert isinstance(body[0], ast.If) and any(isinstance(n, ast.Return) for n in body[0].body)
    assert _statement_calls(body[1], "st.header")
    # Under a plain test and nothing else: inside any container it would have nothing
    # to stick along. The test is that the page draws the headings it links to.
    assert isinstance(body[2], ast.If) and not body[2].orelse and len(body[2].body) == 1
    assert ast.unparse(body[2].test) == "not (ASCENDANT_REFUSAL or pn4.get('refused'))"
    strip = body[2].body[0]
    assert _statement_calls(strip, "_jump_strip")
    assert ast.literal_eval(strip.value.args[0]) == KEY
    assert ast.literal_eval(strip.value.args[1]) == tuple(SECTIONS)


def test_the_helper_holds_its_keyed_container_once():
    """A second container inside it would leave the strip nothing to stick along."""
    helper = _function("_jump_strip")
    containers = [n for n in ast.walk(helper) if _is_call(n, "st.container")]
    assert len(containers) == 1 and [k.arg for k in containers[0].keywords] == ["key"]
    assert not any(isinstance(n, ast.Call) and ast.unparse(n.func).endswith((".container", ".empty"))
                   and n is not containers[0] for n in ast.walk(helper))


def _heading_places(at):
    """Each named heading's place in the main area's tree, as Streamlit addresses it."""
    places = {}

    def walk(block, path):
        for index, child in block.children.items():
            if isinstance(child, Block):
                walk(child, (*path, index))
            elif getattr(child.proto, "anchor", ""):
                places[child.proto.anchor] = (*path, index)

    walk(at.main, ())
    assert list(places) == [anchor for _, anchor in SECTIONS]
    return places


def test_no_choice_on_the_page_moves_a_heading_the_strip_names():
    """Streamlit scrolls a heading newly mounted to the one the address names, so a
    heading that moves in the tree throws a reader who has jumped there and gone
    back up. Every control on the page holds them still. A chart the page refuses
    takes the headings out, so on its return they mount anew and the view arrives
    at the heading the address names; that return is outside this pin."""
    first = make_app(page="days").run()
    assert not first.exception
    still = _heading_places(first)
    choice = first.selectbox(key="pn4_day_point")
    assert len(choice.options) > 20
    for option in choice.options[1:]:
        first.selectbox(key="pn4_day_point").set_value(option).run()
        assert not first.exception and any(m.value.startswith("**Small days from ") for m in first.main.markdown), option
        assert _heading_places(first) == still, option
    first.selectbox(key="pn4_day_point").set_value(choice.options[0]).run()
    assert not first.exception and not any(m.value.startswith("**Small days from ") for m in first.main.markdown)
    assert _heading_places(first) == still

    states = (
        ({"date_input_key": "not-a-date"}, "Results have not updated"),
        ({"manual_lat_key": 90.0}, "Ascendant"),
        ({"_target_mode": "Age"}, None),
        ({"_target_mode": "Date", "target_date": "not-a-date"}, "Not a YYYY-MM-DD date"),
        ({"_target_mode": "Date", "target_date": "9999-01-01"}, "ephemeris"),
        ({"_pn4_monthly_turn": "PN IV IX.1, 26-34"}, None),
        ({"_reading_depth": "Course text and supplement"}, None),
    )
    for state, said in states:
        at = make_app(page="days")
        for name, value in state.items():
            at.session_state[name] = value
        at.run()
        assert not at.exception, state
        assert said is None or said in " ".join(e.value for kind in (at.main.warning, at.main.error) for e in kind), state
        # A store the page's control was drawn from is still what was set, so the state did stand.
        assert all(at.session_state[name] == value for name, value in state.items() if name.startswith("_")), state
        assert _heading_places(at) == still, state


def test_every_section_named_is_drawn_whatever_the_chart():
    """Each heading a top-level statement of the page, so nothing leaves one undrawn but the
    one refusal, whose test holds the strip back too."""
    body = _function("page_days").body
    anchors = [next(k.value.value for k in s.value.keywords if k.arg == "anchor")
               for s in body if _statement_calls(s, "st.subheader")]
    assert anchors == [anchor for _, anchor in SECTIONS]
    refusal = body[3]
    assert ast.unparse(refusal.test) == "_chart_strip(counts_from_the_ascendant=True) or _revolution_refused()"
    assert not any(isinstance(n, (ast.Return, ast.Raise)) for s in body[1:] if s is not refusal for n in ast.walk(s))
    assert not any(_is_call(n, "st.stop") for s in body[1:] for n in ast.walk(s))


def test_days_and_months_has_one_strip():
    calls = [n for n in ast.walk(_function("page_days")) if _is_call(n, "_jump_strip")]
    assert len(calls) == 1


def test_the_strip_adds_no_script_and_nothing_that_reruns():
    helper = _function("_jump_strip")
    called = {ast.unparse(n.func) for n in ast.walk(helper) if isinstance(n, ast.Call)}
    assert called == {"st.container", "st.markdown", "' '.join"}
    assert not any(isinstance(n, ast.keyword) and n.arg and n.arg.startswith("unsafe")
                   for n in ast.walk(helper))
    called_by_the_page = {ast.unparse(n.func) for n in ast.walk(_function("page_days")) if isinstance(n, ast.Call)}
    assert not {name for name in called_by_the_page if re.match(r"st\.(html|iframe|components)", name)}
    assert "<script" not in house_style.PAGE_STYLE.lower()
    source = APP_PATH.read_text(encoding="utf-8")
    assert "unsafe_allow_javascript" not in source
    # The wheel's component goes through `st`; an import, aliased, would pass the names above.
    imported = {alias.name for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {f"{node.module}.{alias.name}" for node in ast.walk(ast.parse(source))
                 if isinstance(node, ast.ImportFrom) and node.module for alias in node.names}
    assert not {name for name in imported if name.startswith("streamlit.components")}


# --- the emitted rules ------------------------------------------------------------

def test_it_is_held_by_its_own_key_on_the_box_streamlit_wraps_it_in():
    declarations = _rule(f":has(>{STRIP})")
    nav_height = re.search(r"height:(\d+)px", _rule('[data-testid="stTopNav"]')).group(1)
    assert "position:sticky" in declarations and f"top:{nav_height}px" in declarations
    assert f"z-index:{GRID_TOOLBAR_LAYER + 1};" in declarations
    # On the keyed box itself sticky has no room, and in a keyed box's flex row a height alone does nothing.
    assert "sticky" not in _rule(STRIP) and "flex:none" in _rule(STRIP)
    assert "st-emotion-cache" not in house_style.PAGE_STYLE


def test_its_ground_is_the_page_s_own_and_opaque():
    declarations = _rule(STRIP)
    assert f"background:{_both('backgroundColor')};" in declarations
    for mode in ("light", "dark"):
        assert re.fullmatch(r"#[0-9A-Fa-f]{6}", _theme(mode)["backgroundColor"])
    assert "opacity" not in declarations and "opacity" not in _rule(f":has(>{STRIP})"), "a ground the page shows through"


def _colours(declarations):
    """The light and the dark colour a rule of the strip's links gives them."""
    light, dark = re.fullmatch(r"color:light-dark\((#[0-9A-Fa-f]{6}),(#[0-9A-Fa-f]{6})\);(?:text-decoration:none;)?",
                               declarations).groups()
    return {"light": light, "dark": dark}


def test_its_links_rest_in_the_theme_s_muted_ink():
    tokens = json.loads((EXECUTABLE_DIR / "tools" / "house_style" / "tokens.json").read_text(encoding="utf-8"))
    assert _colours(_rule(f"{STRIP} a:is(:link,:visited)")) == {
        mode: tokens["modes"][mode]["muted"] for mode in ("light", "dark")}


def test_no_underline_by_another_name_in_the_rules_for_its_links():
    """Only a colour, and a focus ring, on any rule that reaches a link in the strip."""
    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", house_style.PAGE_STYLE)
    of_its_links = [(selector, declarations) for selector, declarations in rules
                    if STRIP in selector and re.search(
                        r"[\s>]\.?a(?![\w-])|[\s>:](?:any-)?link\b|:visited|:hover|:focus|:active", selector)]
    assert len(of_its_links) == 3
    for selector, declarations in of_its_links:
        names = {d.split(":")[0].strip() for d in declarations.split(";") if d.strip()}
        assert names <= {"color", "text-decoration", "outline", "outline-offset"}, selector
    assert ("text-decoration:none" in _rule(f"{STRIP} a:is(:link,:visited)")
            and sum("text-decoration" in declarations for _, declarations in of_its_links) == 1)


def test_its_links_do_not_look_like_the_app_s_other_links():
    at_rest = _colours(_rule(f"{STRIP} a:is(:link,:visited)"))
    told = _colours(_rule(f"{STRIP} a:is(:link,:visited):is(:hover,:focus-visible)"))
    for mode in ("light", "dark"):
        assert at_rest[mode] != _theme(mode)["linkColor"], mode
        assert told[mode] == _theme(mode)["primaryColor"], mode
        assert at_rest[mode] != told[mode], mode
        for colour in (at_rest[mode], told[mode]):
            assert _ratio(colour, _theme(mode)["backgroundColor"]) >= 4.5, (mode, colour)


def test_no_rule_of_ours_takes_a_link_s_underline_off_but_the_strip_s():
    assert _rule(f"{STRIP} a:is(:link,:visited)").endswith("text-decoration:none;")
    written = [selector for selector, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", house_style.PAGE_STYLE)
               if "text-decoration" in declarations]
    assert written == [f"{STRIP} a:is(:link,:visited)"]
    # No rule of ours takes a link's underline off but this one; the theme's stays on.
    config = tomllib.loads((EXECUTABLE_DIR / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["theme"]["linkUnderline"] is True


def test_the_focus_ring_and_the_pointer_stay():
    assert _rule(f"{STRIP} a:focus-visible") == f"outline:2px solid {_both('primaryColor')};outline-offset:2px;"
    style = house_style.PAGE_STYLE
    its_rules = style[style.index(STRIP):style.rindex(STRIP)]
    assert not re.search(r"outline:(?:none|0)|cursor:", its_rules)


def test_its_words_are_set_as_a_running_head_by_the_stylesheet_alone():
    declarations = _rule(f'[data-testid="stMain"] {STRIP} [data-testid="stMarkdown"] p')
    assert '"EB Garamond"' in declarations and '"Zij Interface"' not in declarations
    assert "text-transform:uppercase" in declarations and re.search(r"letter-spacing:0?\.\d+em", declarations)
    small = re.search(r"--zij-small-size:(\d+px)", house_style.PAGE_STYLE).group(1)
    assert f"font-size:{small};" in declarations


def test_one_row_its_names_unbroken():
    """Days and months's names take one row at every usual width, as measured in a
    browser; a longer strip's wrap to a second row, a name never broken."""
    declarations = _rule(f'[data-testid="stMain"] {STRIP} [data-testid="stMarkdown"] p')
    assert "display:flex" in declarations and "white-space:nowrap" in declarations
    # Streamlit pulls a passage up by a negative margin, which would set the row off its strip's centre.
    assert _rule(f'{STRIP} [data-testid="stMarkdownContainer"]') == "margin-bottom:0;"


def test_what_is_scrolled_to_rests_below_the_strip_and_the_strip_itself_moves_nothing():
    nav = int(re.search(r"top:(\d+)px", _rule(f":has(>{STRIP})")).group(1))
    strip = int(re.search(r"min-height:(\d+)px", _rule(STRIP)).group(1))
    selector = f'[data-testid="stMain"]:has({STRIP}) :not({STRIP},{STRIP} *,[data-testid="stHeader"] *)'
    margin = int(re.fullmatch(r"scroll-margin-top:(\d+)px;", _rule(selector)).group(1))
    assert margin > nav + strip
    # A padding on the scroller would take in the strip's own links: Tab onto one would scroll the page.
    assert "scroll-padding" not in house_style.PAGE_STYLE


def test_the_page_does_not_animate_a_jump():
    assert "scroll-behavior" not in house_style.PAGE_STYLE
    assert "scroll-behavior" not in APP_PATH.read_text(encoding="utf-8"), "an inline rule of the page's own"
