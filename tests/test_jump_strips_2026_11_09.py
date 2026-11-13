# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""The strips of section names on The releaser and on Fardar and ages, as on Days and months.

Each strip's names and anchors in order; every anchor a heading the page draws, read
from the page as Streamlit's testing harness draws it; no strip where the page refuses;
a section drawn only sometimes listed only when drawn; the strip standing on the page and
never in a container; the one set of rules naming every strip's key. That a strip stays
stuck and a jump lands clear of it are facts only a browser shows.
"""
from __future__ import annotations

import ast
import importlib.util
import re

import pytest

import engine as E
import ephemeris as M
import house_style
from conftest import APP_PATH, EXECUTABLE_DIR, READING_DEPTHS, make_app, sync_engine_to_environment
from streamlit.testing.v1.element_tree import Block

LINK = re.compile(r"\[([^\]]+)\]\(#([^)]+)\)")
RELEASER = [("Releaser and House-Master", "the-releaser-and-the-house-master"),
            ("Cutting Stars", "the-cutting-stars"),
            ("House-Master Directed", "the-house-master-directed")]
FATHERS_LOT = ("Father's Lot", "the-fathers-lot")
FARDAR = [("Directing", "directing"), ("Sect Light Lords", "the-lords-of-the-sect-light"),
          ("*Fardar*", "the-fardar"),
          ("Fruition", "when-a-natal-indication-comes-out"),
          ("Ages of Man", "the-ages-of-man"), ("Profection", "annual-profection"),
          ("Years", "planetary-years")]
ASCENDANT = ("Rising Lords", "ascendant-triplicity-lords")
KEYS = {"page_releaser": "releaser-sections", "page_fardar": "fardar-sections", "page_days": "days-sections"}
WITHHELD = ("tangency", "coincidence", "unresolved")


@pytest.fixture(autouse=True)
def _engine_in_step():
    """The harness reloads the engine when the environment has moved; before a
    pin patches it, not after."""
    sync_engine_to_environment()


def _with_ascendant(sections):
    return sections[:2] + [ASCENDANT] + sections[2:]


def _build_theme():
    spec = importlib.util.spec_from_file_location("build_theme", EXECUTABLE_DIR / "tools" / "house_style" / "build_theme.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _function(name):
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    return next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)


def _is_call(node, dotted):
    return isinstance(node, ast.Call) and ast.unparse(node.func) == dotted


def _strips(at):
    return [m.value for m in at.main.markdown if len(LINK.findall(m.value)) > 1]


def _strip(at):
    strips = _strips(at)
    assert len(strips) == 1, strips
    return LINK.findall(strips[0])


def _anchors(at):
    return [h.proto.anchor for h in at.main.subheader if h.proto.anchor]


def _run(page, **state):
    at = make_app(page=page, timeout=120)
    for name, value in state.items():
        at.session_state[name] = value
    at.run()
    assert not at.exception
    return at


@pytest.fixture(scope="module")
def releaser():
    return _run("releaser")


@pytest.fixture(scope="module")
def fardar():
    return _run("fardar")


# --- the names and their anchors ---------------------------------------------------

def test_the_releaser_s_names_and_anchors_in_order(releaser):
    assert _strip(releaser) == RELEASER + [FATHERS_LOT], "the example chart draws the father's Lot"
    assert _anchors(releaser) == [anchor for _, anchor in RELEASER + [FATHERS_LOT]]


def test_fardar_and_ages_s_names_and_anchors_in_order(fardar):
    assert _strip(fardar) == FARDAR
    assert _anchors(fardar) == [anchor for _, anchor in FARDAR]


@pytest.mark.parametrize("page", ["releaser", "fardar"])
def test_every_anchor_names_a_heading_the_page_draws(page, releaser, fardar):
    at = {"releaser": releaser, "fardar": fardar}[page]
    drawn = {h.proto.anchor: h.value for h in at.main.subheader if h.proto.anchor}
    for name, anchor in _strip(at):
        assert anchor in drawn, anchor
        # A short name of the owner's or in his spirit, never the heading's citation.
        assert not re.search(r"[\d(),.]|\bPN\b|\bIX\b|Sahl|Nativities", name), name


def test_no_heading_s_words_changed(releaser):
    """Only anchors were added: each heading still reads as the page printed it."""
    assert [h.value for h in releaser.main.subheader if h.proto.anchor] == [
        "The releaser and the house-master (Sahl, *On Nativities* 1.15-1.16, 1.20)",
        "The cutting fixed stars (PN IV IX.8, 32-55)",
        "The house-master directed (Sahl, *On Nativities* 1.23, 1-11)",
        "The father's Lot: its harmers and their direction (Sahl, *On Nativities* 4.20, 31-36)"]
    ticked = _run("fardar", _life_lords_ascendant=True)
    assert [h.value for h in ticked.main.subheader if h.proto.anchor] == [
        "Directing: which ascensions, and what a degree is worth",
        "The lords of the triplicity of the sect light, over the life",
        "Ascendant triplicity lords: life-stage significations",
        "The *fardar* (PN IV IV.1)",
        "When a natal indication comes out (PN IV III.7, 32-42)",
        "The Ages of Man",
        "Annual profection",
        "Planetary years"]


# --- the sections drawn only sometimes ----------------------------------------------

class _Undrawn(dict):
    """A father's Lot the page does not draw: false to the page's test, its rows still
    there for the export, which reads them on every run."""
    def __bool__(self):
        return False


def test_the_father_s_lot_is_listed_only_where_drawn(monkeypatch):
    real = E.pn4_timing_bundle

    def without_the_lot(*args, **kwargs):
        bundle = real(*args, **kwargs)
        return {**bundle, "father_lot": _Undrawn(bundle["father_lot"])} if not bundle.get("refused") else bundle

    monkeypatch.setattr(E, "pn4_timing_bundle", without_the_lot)
    at = _run("releaser")
    assert _strip(at) == RELEASER
    assert _anchors(at) == [anchor for _, anchor in RELEASER]


def test_the_ascendant_s_lords_are_listed_only_where_their_box_is_ticked():
    at = _run("fardar")
    assert _strip(at) == FARDAR
    at.checkbox(key="life_lords_ascendant").check().run()
    assert not at.exception
    assert _strip(at) == _with_ascendant(FARDAR)
    assert _anchors(at) == [anchor for _, anchor in _with_ascendant(FARDAR)]
    at.checkbox(key="life_lords_ascendant").uncheck().run()
    assert _strip(at) == FARDAR and _anchors(at) == [anchor for _, anchor in FARDAR]
    # A box ticked on an earlier visit, its widget since dropped: the store alone draws it.
    stored = _run("fardar", _life_lords_ascendant=True)
    assert _strip(stored) == _with_ascendant(FARDAR)
    assert _anchors(stored) == [anchor for _, anchor in _with_ascendant(FARDAR)]


# --- where the page refuses -------------------------------------------------------

@pytest.mark.parametrize("page", ["releaser", "fardar"])
def test_the_recovery_panel_draws_no_strip(page):
    at = make_app(page=page)
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = "zzzz-no-such-city"
    at.run()
    assert not at.exception
    assert at.main.error and not _strips(at) and not at.main.subheader


@pytest.mark.parametrize("page", ["releaser", "fardar"])
@pytest.mark.parametrize("status", WITHHELD)
def test_no_strip_above_a_withheld_revolution(monkeypatch, page, status):
    monkeypatch.setattr(E, "pn4_timing_bundle", lambda *a, **k: {"refused": M.REVOLUTION_DIVISION_REASONS[status]})
    at = _run(page)
    assert not _strips(at) and not at.main.subheader
    assert [str(w.value) for w in at.main.warning] == [M.REVOLUTION_DIVISION_REASONS[status]]


@pytest.mark.parametrize("name", ["page_releaser", "page_fardar"])
def test_the_strip_stands_on_the_page_under_its_header_behind_the_page_s_own_refusal(name):
    """As on Days and months: past the recovery return, under the header, under a plain
    test reading the same two the refusal after it reads, never in a container."""
    body = _function(name).body
    assert isinstance(body[0], ast.If) and any(isinstance(n, ast.Return) for n in body[0].body)
    assert isinstance(body[1], ast.Expr) and _is_call(body[1].value, "st.header")
    guard = body[2]
    assert isinstance(guard, ast.If) and not guard.orelse and len(guard.body) == 1
    assert ast.unparse(guard.test) == "not (ASCENDANT_REFUSAL or pn4.get('refused'))"
    strip = guard.body[0]
    assert isinstance(strip, ast.Expr) and _is_call(strip.value, "_jump_strip")
    assert ast.literal_eval(strip.value.args[0]) == KEYS[name]
    refusal = body[3]
    assert ast.unparse(refusal.test) == "_chart_strip(counts_from_the_ascendant=True) or _revolution_refused()"
    assert not any(_is_call(n, "_jump_strip") for s in body if s is not guard for n in ast.walk(s))


def test_the_helper_is_not_wrapped_and_every_page_calls_it_on_the_page():
    calls = [n for n in ast.walk(ast.parse(APP_PATH.read_text(encoding="utf-8"))) if _is_call(n, "_jump_strip")]
    assert len(calls) == len(KEYS)
    assert sorted(ast.literal_eval(c.args[0]) for c in calls) == sorted(KEYS.values())
    for name in KEYS:
        assert not any(isinstance(n, ast.With) and any(_is_call(m, "_jump_strip") for m in ast.walk(n))
                       for n in ast.walk(_function(name))), name


# --- no choice moves a heading the strip names ----------------------------------------

def _heading_places(at):
    places = {}

    def walk(block, path):
        for index, child in block.children.items():
            if isinstance(child, Block):
                walk(child, (*path, index))
            elif getattr(child.proto, "anchor", ""):
                places[child.proto.anchor] = (*path, index)

    walk(at.main, ())
    return places


@pytest.mark.parametrize("page", ["releaser", "fardar"])
def test_no_choice_moves_a_heading_the_strip_names(page):
    """Streamlit scrolls a heading newly mounted to the one the address names (see
    Days and months's pin): the depth, and on Fardar and ages the Ascendant's box, leave
    every other named heading where it stood."""
    still = _heading_places(_run(page))
    for depth in READING_DEPTHS:
        moved = _heading_places(_run(page, _reading_depth=depth))
        assert moved == still, depth
    if page == "fardar":
        at = _run(page)
        at.checkbox(key="life_lords_ascendant").check().run()
        ticked = _heading_places(at)
        assert {a: p for a, p in ticked.items() if a != ASCENDANT[1]} == still
        assert ASCENDANT[1] in ticked


# --- the one set of rules ------------------------------------------------------------

def test_the_shared_rules_name_every_strip_s_key():
    strips = _build_theme().JUMP_STRIPS
    assert set(strips) == set(KEYS.values())
    shared = ":is(" + ",".join(f".st-key-{key}" for key in strips) + ")"
    style = house_style.PAGE_STYLE
    for selector in (f":has(>{shared}){{", f"{shared}{{", f'[data-testid="stMain"] {shared} [data-testid="stMarkdown"] p{{',
                     f"{shared} a:is(:link,:visited){{"):
        assert style.count(selector) == 1, selector
    # A heading jumped to on any of them lands clear of the bar and the strip's one line.
    assert style.count(f'[data-testid="stMain"]:has({shared}) :not({shared},{shared} *,[data-testid="stHeader"] *)'
                       "{scroll-margin-top:112px;}") == 1


def test_one_line_by_short_names_and_a_closer_gap_never_smaller_letters():
    """Fardar and ages's eight names fit one line at 1366 px by short names and a gap of
    16 px in place of the bar's 30 (measured in a browser); the letters are the shared
    rule's alone, and no strip's own rule sets a size."""
    strips = _build_theme().JUMP_STRIPS
    assert strips == {"days-sections": None, "releaser-sections": None, "fardar-sections": 16}
    own = re.findall(r'\[data-testid="stMain"\] \.st-key-([\w-]+) \[data-testid="stMarkdown"\] p\{([^}]*)\}',
                     house_style.PAGE_STYLE)
    assert own == [("fardar-sections", "column-gap:16px;")]


def test_a_long_strip_wraps_rather_than_scroll_or_shrink():
    rule = re.search(r'\[data-testid="stMain"\] :is\([^)]*\) \[data-testid="stMarkdown"\] p\{([^}]*)\}',
                     house_style.PAGE_STYLE).group(1)
    assert "flex-wrap:wrap" in rule and "white-space:nowrap" in rule and "max-width:none" in rule
    assert "overflow" not in rule
    assert "column-gap:30px;" in rule and re.search(r"font-size:\d+px;", rule)
