"""Two page sentences: what a session without the launch key is told, and the
zone-data sentence under the LMT box.

A session that does not carry the launch key is told the refusal sentence,
word for word, and shown nothing else, both in an AppTest run and through the
launcher's own server; the build's stop check holds the same text as the app.

With the zone data refused (a zone package that is not the one this app
supplies), the box cannot follow a date to its zone and stays at LMT: the
sentence the named zone gives for that refusal stands under the LMT box too,
the very text, from the one constant. A Standard pick says it as before, and
with the zone data accepted it is said nowhere.
"""
from __future__ import annotations

import ast
import importlib.util

import pytest
from streamlit.testing.v1 import AppTest

import engine
from conftest import APP_PATH, EXECUTABLE_DIR, assert_no_exception, make_app, sync_engine_to_environment
from test_sec1_server_door_2026_10_13 import _elements, _session, _texts, launched, port  # noqa: F401

LMT, STANDARD, MANUAL = engine.TIME_STANDARD_OPTIONS
# The sentence's words: no change of a letter, a mark or a space.
REFUSAL = ("This page is not the one the app opened; use the window or tab it opened when it started, "
           "or start the app again.")
ZONE_SENTENCE = ("The time-zone data is not the one this app supplies, so no standard-time zone can be read. "
                 f"Choose {LMT} or {MANUAL}.")
ZONE_WORDS = "time-zone data is not the one"
PACKAGES = ["tzdata", "timezonefinder-data"]


def _stop_check():
    """The build's stop check, loaded as a module (it starts nothing)."""
    spec = importlib.util.spec_from_file_location(
        "stop_check_sentence", EXECUTABLE_DIR / ".github" / "scripts" / "stop_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _app_tree():
    return ast.parse(APP_PATH.read_text(encoding="utf-8"))


def _app_constant(name):
    node = next(n for n in _app_tree().body if isinstance(n, ast.Assign)
                and [ast.unparse(t) for t in n.targets] == [name])
    return node.value


# --- The launch key's sentence ---------------------------------------------------

def test_the_apps_sentence_is_the_owners_and_the_stop_checks_is_the_same():
    value = _app_constant("_LAUNCH_KEY_REFUSAL")
    assert isinstance(value, ast.Constant) and value.value == REFUSAL, ast.unparse(value)
    assert _stop_check().LAUNCH_KEY_REFUSAL == REFUSAL


def test_an_apptest_without_the_key_is_told_the_sentence_and_shown_nothing_else(monkeypatch):
    monkeypatch.setenv("ZIJ_LAUNCH_KEY", "sent-secret-" + "q" * 31)
    for query in ({}, {"launch": "sent-secret-" + "q" * 30 + "r"}):
        sync_engine_to_environment()
        at = AppTest.from_file(str(APP_PATH), default_timeout=120)
        at.query_params.update(query)
        at.run()
        assert not at.exception, [e.value for e in at.exception]
        assert [i.value for i in at.info] == [REFUSAL], query
        assert len(at.main.children) == 1 and len(at.sidebar.children) == 0, query
        assert "only in the window it opens" not in _texts(at), query


def test_live_a_client_without_the_key_is_told_the_sentence_alone(launched):  # noqa: F811
    for label, query in (("no key", ""), ("a wrong key", "launch=" + launched.secret[:-1] + "y")):
        elements = _elements(_session(launched.port, query=query))
        assert [(kind, body.get("body"), body.get("format")) for kind, body in elements] == [
            ("alert", REFUSAL, "INFO")], (label, elements[:5])
    window = _elements(_session(launched.port, query="launch=" + launched.secret))
    assert len(window) > 10 and not [b for _k, b in window if isinstance(b, dict) and b.get("body") == REFUSAL]


# --- The zone-data sentence under the LMT box ---------------------------------------

def _refuse(monkeypatch, package):
    """The zone package refused for the process, as _zone_package_checked
    keeps a refusal."""
    import time_zones as tz
    monkeypatch.setitem(tz._ZONE_PACKAGES_SEEN, package, f"the {package} package's data files are not those ...")


def _sidebar_alerts(at):
    """The sidebar's info, warning and error elements, in their order."""
    found = []

    def walk(node):
        kind = getattr(node, "type", None)
        if kind in ("info", "warning", "error") and hasattr(node, "value"):
            found.append((kind, node.value))
        children = getattr(node, "children", None)
        if isinstance(children, dict):
            for child in children.values():
                walk(child)

    walk(at.sidebar)
    return found


def _lmt_box_then(at):
    """The LMT box and what stands under it in the box's own slot: the
    elements of the block that holds the box, from the box on."""
    held = []

    def walk(node):
        children = getattr(node, "children", None)
        if not isinstance(children, dict):
            return
        row = [children[k] for k in sorted(children)]
        for i, child in enumerate(row):
            if getattr(child, "type", None) == "info" and str(child.value).startswith("**Exact LMT**"):
                held.append([(getattr(c, "type", None), getattr(c, "value", None)) for c in row[i:]])
            walk(child)

    walk(at.sidebar)
    assert len(held) == 1, held
    return held[0]


def _pick(at, standard):
    at.sidebar.selectbox(key="time_standard_key").select(standard).run()
    assert_no_exception(at, f"pick {standard}")
    return at


@pytest.mark.parametrize("package", PACKAGES)
def test_with_the_zone_data_refused_an_unpicked_modern_date_says_the_sentence_under_the_lmt_box(
        monkeypatch, package):
    _refuse(monkeypatch, package)
    at = make_app(date="1990-06-15").run()
    assert_no_exception(at, "an unpicked modern date, the zone data refused")
    assert at.session_state["time_standard_key"] == LMT
    assert "_time_standard_picked" not in at.session_state or not at.session_state["_time_standard_picked"]
    under = _lmt_box_then(at)
    assert under[1:] == [("warning", ZONE_SENTENCE)], under
    assert [value for _kind, value in _sidebar_alerts(at)].count(ZONE_SENTENCE) == 1
    assert not at.sidebar.error, [e.value for e in at.sidebar.error]
    lmt_said = under[1][1]
    # The Standard pick: the cast refused with the same sentence, as before,
    # and said once, as the box's error, with no LMT box left to stand under.
    _pick(at, STANDARD)
    assert [e.value for e in at.sidebar.error] == [lmt_said]
    assert [value for _kind, value in _sidebar_alerts(at)].count(lmt_said) == 1
    assert not at.sidebar.warning or lmt_said not in [w.value for w in at.sidebar.warning]
    # LMT picked back by hand: the data is still refused, so it is still said.
    _pick(at, LMT)
    assert _lmt_box_then(at)[1:] == [("warning", lmt_said)]


@pytest.mark.parametrize("package", PACKAGES)
def test_with_the_zone_data_refused_a_fresh_session_says_the_sentence_under_the_lmt_box(monkeypatch, package):
    _refuse(monkeypatch, package)
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=60).run()
    assert_no_exception(at, "fresh, the zone data refused")
    assert at.session_state["time_standard_key"] == LMT
    assert _lmt_box_then(at)[1:] == [("warning", ZONE_SENTENCE)]
    assert not at.sidebar.error, [e.value for e in at.sidebar.error]


def test_with_the_zone_data_accepted_the_sentence_is_said_nowhere():
    sync_engine_to_environment()
    fresh = AppTest.from_file(str(APP_PATH), default_timeout=60).run()
    assert_no_exception(fresh, "fresh")
    modern = make_app(date="1990-06-15").run()
    assert_no_exception(modern, "a modern date")
    lmt = _pick(make_app(date="1990-06-15").run(), LMT)
    for label, at in (("fresh", fresh), ("modern, followed", modern), ("LMT picked", lmt)):
        assert ZONE_WORDS not in _texts(at), label
    assert modern.session_state["time_standard_key"] == STANDARD
    assert fresh.session_state["time_standard_key"] == LMT and _lmt_box_then(fresh)
    assert lmt.session_state["time_standard_key"] == LMT and _lmt_box_then(lmt)


def test_the_zone_data_sentence_is_one_text_in_the_app():
    tree = _app_tree()
    texts = [node for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)
             and any(words in node.value for words in ("time-zone data is not", "supplies, so no standard-time",
                                                       "no standard-time zone can be read"))]
    assert len(texts) == 1, [ast.unparse(t) for t in texts]
    holder = next(n for n in tree.body if isinstance(n, ast.Assign)
                  and [ast.unparse(t) for t in n.targets] == ["ZONE_DATA_CHANGED_MESSAGE"]).value
    assert texts[0] in list(ast.walk(holder))
    # The LMT box shows it by its name; the named zone's refusal by the run's
    # chart error, which is set from that name.
    shown = [node for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and node.func.attr in ("info", "warning", "error", "caption", "markdown", "write")
             and any(isinstance(arg, ast.Name) and arg.id == "ZONE_DATA_CHANGED_MESSAGE" for arg in node.args)]
    assert [call.func.attr for call in shown] == ["warning"], [ast.unparse(c) for c in shown]
    assert "chart_error = ZONE_DATA_CHANGED_MESSAGE" in [ast.unparse(n) for n in ast.walk(tree) if isinstance(n, ast.Assign)]
    space = {"_LMT_OR_MANUAL": f"{LMT} or {MANUAL}"}
    assert eval(compile(ast.Expression(holder), "app.py", "eval"), space) == ZONE_SENTENCE
