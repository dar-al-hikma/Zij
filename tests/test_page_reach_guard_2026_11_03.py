"""The page guard judges the main area alone.

The sidebar, the nativity form, is drawn before the navigation runs the page, so
a run stopped above that call holds a whole sidebar and no page. It fails as a
run that did not reach the page, and so does every pin on that page that asserts
only that some text is absent. The true app passes, and so does a run stopped by
a refusal, whose sentence stands in the main area.
"""
import pytest
from streamlit.testing.v1 import AppTest

import conftest
import test_hostile_l7_2026_10_03 as page_pins
from conftest import APP_PATH, make_app, page_not_reached

# The call stands inside the try whose finally lifts the opening cover (app.py's last lines).
NAVIGATION = '    st.navigation(pages, position="top").run()'
NOT_REACHED = "app.py: the run did not reach the page: "
ONLY_THE_SIDEBAR = "the app rendered nothing but its sidebar"
ABSENCE_ONLY_PINS = ("test_l7_03_past_the_table_age_is_rounded", "test_l7_09_pages_do_not_call_themselves_the_engine",
                     "test_l7_15_reference_page_names_the_volume_of_every_page_number")


@pytest.fixture
def stopped_above_the_page(tmp_path, monkeypatch):
    """The harness's app is a copy that stops just above the navigation."""
    source = APP_PATH.read_text(encoding="utf-8")
    assert source.count(NAVIGATION) == 1, "premise: the one call that runs the page"
    copy = tmp_path / "app.py"
    copy.write_text(source.replace(NAVIGATION, "    st.stop()\n" + NAVIGATION), encoding="utf-8")
    (tmp_path / "atlas.db").symlink_to(APP_PATH.parent / "atlas.db")
    monkeypatch.setattr(conftest, "APP_PATH", copy)


def _script(tmp_path, text):
    path = tmp_path / "app.py"
    path.write_text("import streamlit as st\n" + text, encoding="utf-8")
    return AppTest.from_file(str(path), default_timeout=60)


def test_the_true_app_reaches_the_timing_page():
    at = make_app(page="timing").run(timeout=120)
    assert page_not_reached(at) is None
    assert len(at.main.children) > 0 and len(at.sidebar.children) > 0


def test_a_run_stopped_above_the_navigation_does_not_reach_the_timing_page(stopped_above_the_page):
    at = make_app(page="timing")
    with pytest.raises(pytest.fail.Exception) as failed:
        at.run(timeout=120)
    assert str(failed.value) == NOT_REACHED + ONLY_THE_SIDEBAR
    assert page_not_reached(at) == ONLY_THE_SIDEBAR
    assert len(at.main.children) == 0 and len(at.sidebar.children) > 0, "premise: the sidebar was drawn, the page not"


@pytest.mark.parametrize("pin", ABSENCE_ONLY_PINS)
def test_a_pin_that_asserts_only_absence_fails_on_that_run(stopped_above_the_page, pin):
    with pytest.raises(pytest.fail.Exception) as failed:
        getattr(page_pins, pin)()
    assert str(failed.value) == NOT_REACHED + ONLY_THE_SIDEBAR


def test_a_raise_above_the_page_with_the_sidebar_drawn_does_not_reach_it(tmp_path):
    at = _script(tmp_path, "st.sidebar.write('form')\nraise RuntimeError('early')\n")
    with pytest.raises(pytest.fail.Exception) as failed:
        at.run()
    assert str(failed.value).startswith(NOT_REACHED + "the app raised before it rendered anything but its sidebar\n")
    assert "early" in str(failed.value)


def test_a_refusal_in_the_main_area_stops_the_run_and_passes(tmp_path):
    at = _script(tmp_path, "st.sidebar.write('form')\nst.error('Nothing is calculated.')\nst.stop()\n").run()
    assert page_not_reached(at) is None
    assert [e.value for e in at.main.error] == ["Nothing is calculated."]
