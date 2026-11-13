"""The wheels and the strips are drawn in the page's mode, with no control of
their own: light on a light page, dark on a dark page, whatever a preferences
file still holds of the old setting. The saved wheel is the wheel shown, with
the faces a file carries for itself. A fragment rerun draws a wheel in the mode this window's page has then: a change
of the computer's colours reaches it at once, another window's press only at
this window's next full run, as it reaches this window's page.

A preferences file that holds the old setting keeps it: it is ignored, not
erased, and a file that does not hold it never gains it.
"""
import json
from pathlib import Path

import pytest

import wheel
from conftest import APP_PATH, assert_no_exception, make_app, natal_wheel_envelope, sync_engine_to_environment
from test_fragment_readings_2026_09_18 import _fragment_rerun, shared_fragments  # noqa: F401 (a fixture)
from test_page_colours_2026_11_04 import _Reporting

STORED = "_wheel_dark"
SECTIONS = ("theme.light", "theme.dark", "theme.light.sidebar", "theme.dark.sidebar")
DOWNLOAD = {"chart": "dl_chart_wheel", "timing": "dl_timing_wheel"}
GROUND = {"Dark": wheel._PALETTE_DARK["bg"], "Light": wheel._PALETTE_LIGHT["bg"]}
THEME = {"Dark": "dark", "Light": "light"}
STRIP_PAGES = ("timing", "releaser", "days")
# The two wheels' fragments, at each layout.
WHEELS = [("chart", "Square"), ("chart", "Wide"), ("timing", "Square"), ("timing", "Wide")]


@pytest.fixture(autouse=True)
def the_options_stand_as_they_were():
    import page_colours
    from streamlit import config

    assert page_colours.showing() is None
    before = {section: config.get_options_for_section(section) for section in SECTIONS}
    yield
    page_colours._parsed, page_colours._showing = None, None
    for section, options in before.items():
        for name, value in options.items():
            config.set_option(f"{section}.{name}", value)


@pytest.fixture
def prefs(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    sync_engine_to_environment()
    path = tmp_path / "Zij" / "preferences.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    yield path
    monkeypatch.undo()
    sync_engine_to_environment()


@pytest.fixture
def handed(monkeypatch):
    """What each download button is handed at its latest drawing, by its key:
    the harness cannot read a button's bytes."""
    import streamlit

    held, real = {}, streamlit.download_button

    def capturing(label, data, *args, **kwargs):
        held[kwargs["key"]] = data
        return real(label, data, *args, **kwargs)

    monkeypatch.setattr(streamlit, "download_button", capturing)
    return held


def _choose(at, word):
    """Press the page's own button until the page is showing `word`."""
    import page_colours

    for _ in range(2):
        if page_colours.showing() == word:
            return
        at.button(key="page_theme").click().run(timeout=300)
        assert_no_exception(at, word)
    assert page_colours.showing() == word


def _ground(svg):
    """The picture's own ground: the first rectangle it draws."""
    return svg[svg.index("<rect "):].split(">", 1)[0].split('fill="')[1].split('"')[0]


def _boxes(at):
    return [c for c in at.main.checkbox if c.label == "Dark wheel" or c.key == "wheel_dark"]


@pytest.mark.parametrize("page", ["chart", "timing"])
@pytest.mark.parametrize("stored", [True, False, None], ids=["held-on", "held-off", "not-held"])
def test_the_wheel_follows_the_page_whatever_the_file_holds(page, stored, prefs, handed):
    """Each choice draws its own mode at that choice, in both directions, from
    a file holding the old setting either way or not at all; and no box."""
    prefs.write_text(json.dumps({"_launches": 3} if stored is None else {"_launches": 3, STORED: stored}))
    at = make_app(page=page, timeout=300).run()
    assert_no_exception(at, page)
    assert not _boxes(at), "the box is back"
    for word in ("Dark", "Light", "Dark"):
        _choose(at, word)
        assert _ground(handed[DOWNLOAD[page]]) == GROUND[word], f"{page}, {word}, the file holding {stored}"
        assert not _boxes(at), "the box is back"
    assert GROUND["Dark"] != GROUND["Light"], "the premise: the two grounds can be told apart"


@pytest.mark.parametrize("layout", ["Square", "Wide"])
def test_the_saved_wheel_is_the_wheel_shown(layout, prefs, handed):
    at = make_app(page="chart", timeout=300)
    at.session_state["_wheel_layout"] = layout
    at.run()
    for word in ("Dark", "Light"):
        _choose(at, word)
        envelope = natal_wheel_envelope(at.main)
        assert envelope["width"] == ("stretch" if layout == "Wide" else "column"), "the premise: this layout's wheel"
        shown = envelope["svg"]
        assert _ground(shown) == GROUND[word]
        assert wheel.saved_svg(shown) == handed[DOWNLOAD["chart"]]


@pytest.fixture
def images(monkeypatch):
    """Every st.image drawn: the harness cannot read a picture's bytes."""
    import streamlit

    drawn, real = [], streamlit.image

    def capturing(image, *args, **kwargs):
        drawn.append(image)
        return real(image, *args, **kwargs)

    monkeypatch.setattr(streamlit, "image", capturing)
    return drawn


def _full_run(page, layout):
    at = make_app(page=page, timeout=300)
    at.session_state["_wheel_layout"] = layout
    at.run()
    assert_no_exception(at, page)
    return at


def _rerun_the_wheel(at, page, fragments, images, handed):
    """The wheel's fragment rerun alone. The ground of what it shows and of
    what it hands the download button."""
    assert len(fragments._fragments) == 1, "the premise: one fragment on the page"
    images.clear()
    tree = _fragment_rerun(at, list(fragments._fragments), timeout=300)
    shown = natal_wheel_envelope(tree)["svg"] if page == "chart" else images[-1]
    assert wheel.saved_svg(shown) == handed[DOWNLOAD[page]], "the saved wheel is the wheel shown, with its faces"
    return _ground(shown)


@pytest.mark.parametrize("page, layout", WHEELS)
def test_a_fragment_rerun_draws_the_computer_s_present_colours(page, layout, prefs, handed, images, shared_fragments,
                                                               monkeypatch):
    """At Automatic the computer's colours change with a chart drawn: the rerun
    draws and saves the new ground, in both directions. The report is stubbed,
    since AppTest has no browser to change."""
    import streamlit

    browser = _Reporting(streamlit.context, "light")
    monkeypatch.setattr(streamlit, "context", browser)
    at = _full_run(page, layout)
    assert _ground(handed[DOWNLOAD[page]]) == GROUND["Light"]
    for kind, word in (("dark", "Dark"), ("light", "Light")):
        browser.theme.type = kind
        assert _rerun_the_wheel(at, page, shared_fragments, images, handed) == GROUND[word], (page, layout, word)


@pytest.mark.parametrize("page, layout", WHEELS)
@pytest.mark.parametrize("held, reported", [(None, "dark"), ("Dark", "light")], ids=["automatic", "chosen"])
def test_another_window_s_press_waits_for_this_window_s_full_run(page, layout, held, reported, prefs, handed, images,
                                                                 shared_fragments, monkeypatch):
    """The options belong to the server, so a press elsewhere is in force at
    once and reaches this window's page at its next full run. Until then a
    fragment rerun here keeps to the page this window is showing."""
    import streamlit

    import page_colours

    monkeypatch.setattr(streamlit, "context", _Reporting(streamlit.context, reported))
    page_colours.show(held)
    at = _full_run(page, layout)
    assert _ground(handed[DOWNLOAD[page]]) == GROUND["Dark"]
    page_colours.show("Light")
    assert _rerun_the_wheel(at, page, shared_fragments, images, handed) == GROUND["Dark"], (page, layout, held)
    _full_run(page, layout)
    assert _ground(handed[DOWNLOAD[page]]) == GROUND["Light"], "a full run takes it"


@pytest.mark.parametrize("page, layout", WHEELS)
def test_a_press_elsewhere_reaches_this_window_at_its_own_full_run(page, layout, prefs, handed, monkeypatch):
    """The same session, not a new one: this window's page crosses at its own
    next full run, so its wheel must cross with it, not keep the choice it had."""
    import streamlit

    import page_colours

    monkeypatch.setattr(streamlit, "context", _Reporting(streamlit.context, "dark"))
    at = _full_run(page, layout)
    assert _ground(handed[DOWNLOAD[page]]) == GROUND["Dark"]
    page_colours.show("Light")
    at.run()
    assert_no_exception(at, page)
    assert _ground(handed[DOWNLOAD[page]]) == GROUND["Light"], (page, layout)


def test_every_picture_shown_on_the_strips_pages_takes_the_page_s_mode(prefs, images):
    drawn = images
    at = make_app(page="timing", timeout=300).run()
    for word in ("Dark", "Light"):
        _choose(at, word)
        for page in STRIP_PAGES:
            drawn.clear()
            at = make_app(page=page, timeout=300).run()
            assert_no_exception(at, page)
            pictures = [image for image in drawn if isinstance(image, str) and "<svg" in image]
            assert {_ground(picture) for picture in pictures} == {GROUND[word]}, (word, page)


@pytest.mark.parametrize("stored", [True, False], ids=["held-on", "held-off"])
def test_a_file_holding_the_old_setting_keeps_it_through_every_kind_of_save(stored, prefs):
    prefs.write_text(json.dumps({"_launches": 3, STORED: stored}))
    at = make_app(page="chart", timeout=300).run()
    assert json.loads(prefs.read_text())[STORED] is stored, "the launch"
    assert "wheel_dark" not in at.session_state, "a control still restates it"
    at.checkbox(key="chart_bounds").uncheck().run()
    held = json.loads(prefs.read_text())
    assert held[STORED] is stored and held["_chart_bounds"] is False, f"a control's save: {held}"
    _choose(at, "Dark")
    _choose(at, "Light")
    held = json.loads(prefs.read_text())
    assert held[STORED] is stored and held["_page_colours"] == "Light", f"a choice's save: {held}"


def test_a_file_that_does_not_hold_the_old_setting_never_gains_it(prefs):
    at = make_app(page="chart", timeout=300).run()
    at.checkbox(key="chart_bounds").uncheck().run()
    _choose(at, "Dark")
    assert STORED not in json.loads(prefs.read_text())


@pytest.mark.parametrize("stored", [True, False], ids=["held-on", "held-off"])
def test_the_record_of_settings_names_no_such_setting(stored, prefs):
    prefs.write_text(json.dumps({STORED: stored}))
    at = make_app(page="chart", timeout=300).run()
    assert_no_exception(at, "chart")
    assert set(at.session_state["_analysis_export"]["display"]) == {"chart_bounds", "wheel_layout"}
    for report in ("_analysis_html", "_analysis_markdown"):
        assert "Bounds ring" in at.session_state[report], "the premise: the report lists what is drawn"
        assert "Dark wheel" not in at.session_state[report], report


@pytest.mark.parametrize("name", ["app.py", "export_html.py"])
def test_the_words_of_the_old_control_are_gone(name):
    source = (Path(APP_PATH).parent / name).read_text(encoding="utf-8")
    for word in ("Dark wheel", "WHEEL_DARK", '"wheel_dark"', "_timing_dark"):
        assert word not in source, f"{name}: {word}"
