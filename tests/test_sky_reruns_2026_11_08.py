"""The Sky's own presses rerun the sky alone, and Streamlit's fade waits.

A press of Stars listed or View used to rerun the whole script, and on a slow
window that run passed the half second after which Streamlit fades whatever it
has not yet re-sent: the whole sky faded and came back. The sky and its own
controls are one fragment now (`_sky_block`), so a press reruns that body
alone; and the page's own style holds Streamlit's fade back to two seconds.

`AppTest` runs a fragment as part of a full run, so these tests ask the script
runner for a fragment's own run, as the browser does after a press inside one:
the run's request names the fragment, and the runner calls its body without
executing the page. What comes back is the deltas that run sent, so a page
whose main ran again shows its heading, and one that did not shows none.
"""
import ast
import json
import os
import re

import pytest

import house_style
from conftest import component_mounts, make_app, ui_source

LISTS = {"Sahl's 28": 28, "Curated List": 177, "Significant Stars": 486, "Full Catalogue": 1852}
STALE_RULE = '[data-testid="stElementContainer"][data-stale="true"]{transition-delay:2s;}'


def _sky_page():
    at = make_app(page="sky").run()
    assert not at.exception, at.exception
    return at


def _envelope(at):
    mounts = component_mounts(at.main, "fixed_star_sky")
    assert len(mounts) == 1, "the sky, once"
    return json.loads(mounts[0].proto.json)


def _the_skys_fragment(at):
    """The one fragment the Sky page registers: the sky and its controls."""
    ids = list(at._fragment_storage._fragments)
    assert len(ids) == 1, f"one fragment on the Sky page, found {len(ids)}"
    return ids[0]


def _press_inside(monkeypatch, at, fragment_id, press):
    """Run what `press` sets as the browser runs a press inside a fragment: a
    rerun whose request names that fragment."""
    import streamlit.testing.v1.local_script_runner as runner

    real = runner.RerunData
    monkeypatch.setattr(runner, "RerunData", lambda **kw: real(fragment_id_queue=[fragment_id], **kw))
    press(at).run()
    monkeypatch.setattr(runner, "RerunData", real)
    assert not at.exception, at.exception
    return at


def _group(at, key):
    return next(group for group in at.get("button_group") if group.key == key)


# --- 1. The shape: every sky control and the sky stand in one fragment ----------------

def _page_sky_and_block():
    tree = ast.parse(ui_source())
    page = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "page_sky")
    block = next(node for node in ast.walk(page) if isinstance(node, ast.FunctionDef) and node.name == "_sky_block")
    return page, block


def test_the_sky_and_its_own_controls_are_one_fragment():
    src = ui_source()
    page, block = _page_sky_and_block()
    assert [ast.unparse(dec) for dec in block.decorator_list] == ["_pinned_fragment"]
    body = ast.get_source_segment(src, block)
    outside = ast.get_source_segment(src, page).replace(body, "")
    for piece in ("_star_finder(", "key=_SKY_POPULATION", "key=_SKY_VIEW", 'key="zij-sky-controls"',
                  "SKY_VIEW(data=", "_open_star_record(", "_star_record_opening(", "_held_choice("):
        assert piece in body, piece
        assert piece not in outside, f"{piece} stands outside the fragment"
    # The heading and the strip are the page's, drawn once per full run.
    assert 'st.header("The Sky")' in outside and "_chart_strip(" in outside
    assert "_sky_block()" in outside
    # The page's colours are read afresh in the fragment, as the wheel's are.
    assert body.count("_viewer_theme()") == 1 and "VIEWER_THEME" not in body


# --- 2. A press reruns the sky alone, and the sky takes the new value ---------------

@pytest.mark.parametrize("name", ["Sahl's 28", "Full Catalogue"])
def test_a_press_of_stars_listed_reruns_the_sky_and_not_the_page(monkeypatch, name):
    at = _sky_page()
    assert [h.value for h in at.main.header] == ["The Sky"], "a full run draws the heading"
    fragment = _the_skys_fragment(at)
    _press_inside(monkeypatch, at, fragment, lambda at: _group(at, "_sky_population").set_value(name))
    assert [h.value for h in at.main.header] == [], "the page's main ran again"
    data = _envelope(at)
    assert data["population"] == name and len(data["shown"]) == LISTS[name]
    assert _group(at, "_sky_population").value == name
    # The list it holds goes with the page, as a full run's press left it.
    assert at.session_state["_fixed_stars_list"] == name


def test_a_press_of_view_reruns_the_sky_and_not_the_page(monkeypatch):
    import sky

    at = _sky_page()
    before = _envelope(at)["mode"]
    other = next(name for name in sky.VIEWS if sky.VIEWS[name] != before)
    _press_inside(monkeypatch, at, _the_skys_fragment(at), lambda at: _group(at, "_sky_view").set_value(other))
    assert [h.value for h in at.main.header] == []
    assert _envelope(at)["mode"] == sky.VIEWS[other] != before
    assert at.session_state["_sky_view_held"] == other


def test_a_find_turns_the_sky_in_the_skys_own_run(monkeypatch):
    at = _sky_page()
    at.text_input(key="_fixed_stars_query").set_value("Spica")
    _press_inside(monkeypatch, at, _the_skys_fragment(at),
                  lambda at: next(b for b in at.button if b.label == "Find").click())
    assert [h.value for h in at.main.header] == []
    data = _envelope(at)
    assert data["names"][data["turn"]["id"]].startswith("Spica")


def test_a_full_run_after_a_press_keeps_the_choice():
    """A theme press, a page move and a return are full runs: the list chosen inside
    the fragment is the one they draw."""
    at = _sky_page()
    _group(at, "_sky_population").set_value("Sahl's 28").run()
    at.run()
    assert not at.exception
    assert [h.value for h in at.main.header] == ["The Sky"]
    assert len(_envelope(at)["shown"]) == 28


# --- 3. Streamlit's fade waits two seconds -----------------------------------------------

def _bundle():
    import streamlit

    folder = os.path.join(os.path.dirname(streamlit.__file__), "static", "static", "js")
    return "".join(open(os.path.join(folder, name), encoding="utf-8", errors="replace").read()
                   for name in sorted(os.listdir(folder))
                   if name.endswith(".js") and name.startswith(("index", "styled-components")))


def _stale_misses(bundle, css):
    """What the page's wait keys on that the bundle does not write, or the page does not hold."""
    misses = []
    # The element's container carries its staleness as an attribute, beside its test id.
    if not re.search(r'"data-testid":`stElementContainer`,"data-stale":', bundle):
        misses.append("the stale attribute on the element's container")
    # The fade itself: a transition on opacity, whose delay the page's rule replaces.
    if not re.search(r"=`1s ease-in 0\.5s`,\w+=\{opacity:\w+\.stale,transition:`opacity \$\{\w+\}`\}", bundle):
        misses.append("the fade's own transition")
    if css.count(STALE_RULE) != 1 or css.count("data-stale") != 1:
        misses.append("the page's own rule")
    return misses


def test_streamlit_s_own_bundle_still_marks_and_fades_what_the_page_holds_back():
    assert _stale_misses(_bundle(), house_style.PAGE_STYLE) == []


@pytest.mark.parametrize("old, new", [('"data-stale":', '"data-is-stale":'),
                                      ("`1s ease-in 0.5s`", "`1s ease-in 0.2s`"),
                                      ("transition:`opacity ${", "animation:`fade ${")])
def test_a_bundle_that_renames_the_mark_or_the_fade_is_caught(old, new):
    bundle = _bundle()
    assert old in bundle
    assert _stale_misses(bundle.replace(old, new), house_style.PAGE_STYLE) != []


def test_a_page_without_the_rule_is_caught():
    assert _stale_misses(_bundle(), house_style.PAGE_STYLE.replace(STALE_RULE, "")) != []


def test_the_rule_is_the_build_s_and_stands_last_in_the_page_s_style():
    """Written by tools/house_style/build_theme.py, as every rule of the page's style is,
    and later than any rule that could name the same element."""
    import importlib.util

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "house_style", "build_theme.py")
    spec = importlib.util.spec_from_file_location("house_style_build_theme", path)
    build_theme = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_theme)
    assert build_theme.STALE_MARK + "{transition-delay:" + build_theme.STALE_FADE_DELAY + ";}" == STALE_RULE
    assert house_style.PAGE_STYLE.endswith(STALE_RULE + "</style>")
