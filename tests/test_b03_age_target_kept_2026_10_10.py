"""An Age target kept when a birth-date edit lowers the Age box's bound stays
kept (ruling 145, B-03 of the third outside pass).

The reproduction's case: born 1240-05-23, Target by Age, age 1760 (the
birthday 3000-05-23, inside the ephemeris); then the birth date is set to
2026-05-23, whose bound is 974, so 1760 is out of reach and the page says
"keeping 3000-05-23" -- age 974 from the new birth. The box came back as 0
(its own 1760 above the new maximum) and _persist wrote that 0 into the
store: from the next rerun of any kind the target was the birth itself, the
export said age 0 and a Save wrote target_age 0. The box is now seeded with
the kept age before it is drawn, on all four Prediction pages.

Every app run here uses its own XDG directory (tmp_path).
"""
import json
import os
from pathlib import Path

import pytest
from streamlit.util import calc_hash

from conftest import assert_no_exception, make_app

PREDICTION_PAGES = ("timing", "releaser", "days", "fardar")
KEPT = ("3000-05-23", 974)
KEEPING = "The target is beyond this app's ephemeris (3000-09-20); keeping 3000-05-23."


def _age_box(at):
    hits = [n for n in at.main.number_input if n.label.startswith("Age")]
    assert len(hits) == 1, [n.label for n in at.main.number_input]
    return hits[0]


def _target(at):
    t = at.session_state["_analysis_export"]["target"]
    return t["date"], t["age"]


def _errors(at):
    return [e.value for e in at.main.error]


def _goto(at, page):
    at._page_hash = calc_hash(page)
    return at.run()


def _aged(page, age, born="1240-05-23"):
    at = make_app(date=born, page=page).run()
    at.main.radio(key="target_mode").set_value("Age").run()
    _age_box(at).set_value(age).run()
    assert_no_exception(at, "the age")
    return at


def _born(at, date):
    at.sidebar.text_input(key="date_input_key").set_value(date).run()
    assert_no_exception(at, "the birth-date edit")
    return at


def _store_path():
    return Path(os.environ["XDG_DATA_HOME"]) / "Zij" / "saved_charts.json"


@pytest.mark.parametrize("page", PREDICTION_PAGES)
def test_b03_the_kept_age_stays_kept(tmp_path, monkeypatch, page):
    """On the edit's run, after a plain rerun, and after a visit to another
    Prediction page and back, the target is the kept one and the box shows
    it. At e7f10f1 the box showed 0 on the edit's run and the target fell to
    ('2026-05-23', 0) from the rerun on."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _aged(page, 1760)
    assert _target(at) == ("3000-05-23", 1760)
    _born(at, "2026-05-23")
    assert KEEPING in _errors(at)
    assert _target(at) == KEPT
    assert _age_box(at).value == 974
    assert at.session_state["_target_age"] == 974
    at.run()
    assert_no_exception(at, "the plain rerun")
    assert _target(at) == KEPT
    assert _age_box(at).value == 974
    assert at.session_state["_target_age"] == 974
    other = PREDICTION_PAGES[(PREDICTION_PAGES.index(page) + 1) % len(PREDICTION_PAGES)]
    _goto(at, other)
    assert_no_exception(at, f"the visit to {other}")
    assert _target(at) == KEPT
    assert _age_box(at).value == 974
    _goto(at, page)
    assert_no_exception(at, f"the return to {page}")
    assert _target(at) == KEPT
    assert _age_box(at).value == 974


def test_b03_a_save_after_the_rerun_writes_the_kept_age(tmp_path, monkeypatch):
    """At e7f10f1 the record held target_age 0 and the birth as the target."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _born(_aged("timing", 1760), "2026-05-23")
    at.run()
    [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value("Kept age").run()
    [b for b in at.sidebar.button if "Save" in b.label][0].click().run()
    assert_no_exception(at, "the save")
    record = json.loads(_store_path().read_text())["Kept age"]
    assert record["date_string"] == "2026-05-23"
    assert (record["target_mode"], record["target_date"], record["target_age"]) == ("Age",) + KEPT


def test_b03_a_new_age_typed_afterwards_is_taken(tmp_path, monkeypatch):
    """The seeding is for an age above the bound only: an age the reader
    types afterwards stands, on its run and the next."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _born(_aged("releaser", 1760), "2026-05-23")
    at.run()
    _age_box(at).set_value(900).run()
    assert_no_exception(at, "the new age")
    assert _target(at) == ("2926-05-23", 900)
    assert _age_box(at).value == 900
    at.run()
    assert _target(at) == ("2926-05-23", 900)
    assert at.session_state["_target_age"] == 900
    assert [e for e in _errors(at) if "keeping" in e] == []


def test_b03_an_edit_inside_the_bound_changes_nothing(tmp_path, monkeypatch):
    """An age the new birth's bound still holds is the reader's, unchanged:
    the target is that birthday of the new birth, and nothing is kept."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _born(_aged("days", 50), "2026-05-23")
    assert _target(at) == ("2076-05-23", 50)
    assert _age_box(at).value == 50
    assert [e for e in _errors(at) if "keeping" in e] == []
    at.run()
    assert _target(at) == ("2076-05-23", 50)
    assert at.session_state["_target_age"] == 50


def test_b03_a_bound_lowered_then_raised_keeps_the_kept_age(tmp_path, monkeypatch):
    """The self-break's case: the birth moved to 2026 and back to 1240. The
    kept age, 974, is the box's own after the first edit, so the second
    edit reads age 974 from the old birth. At e7f10f1 the box held 0 and the
    target fell to the birth itself, 1240-05-23."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _born(_aged("fardar", 1760), "2026-05-23")
    at.run()
    _born(at, "1240-05-23")
    assert _target(at) == ("2214-05-23", 974)
    assert _age_box(at).value == 974
    at.run()
    assert _target(at) == ("2214-05-23", 974)


def test_b03_a_loaded_record_whose_age_is_out_of_reach(tmp_path, monkeypatch):
    """A record whose age its birth cannot reach keeps its own date and
    shows that date's age, on the load and after. (This passed at e7f10f1
    too: the load drops the widget key and _carry seeds the kept age.)"""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _aged("timing", 50, born="2026-05-23")
    [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value("Far").run()
    [b for b in at.sidebar.button if "Save" in b.label][0].click().run()
    store = json.loads(_store_path().read_text())
    store["Far"].update(target_age=1760, target_date="3000-05-23")
    _store_path().write_text(json.dumps(store))
    fresh = make_app(date="1240-05-23", page="days").run()
    fresh.sidebar.selectbox(key="chart_picker").select("Far").run()
    assert_no_exception(fresh, "the load")
    assert KEEPING in _errors(fresh)
    assert _target(fresh) == KEPT
    assert _age_box(fresh).value == 974
    fresh.run()
    assert _target(fresh) == KEPT
    assert _age_box(fresh).value == 974


def test_b03_a_kept_age_below_the_bound_is_the_kept_one(tmp_path, monkeypatch):
    """The checker's road B: born 2850-05-23, age 100 (2950-05-23), then the
    birth set to 2920-05-23, whose bound is 80. The kept date 2950-05-23 is
    age 30 of the new birth, below the bound: the box is seeded with 30, not
    with the bound."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = _born(_aged("releaser", 100, born="2850-05-23"), "2920-05-23")
    assert "The target is beyond this app's ephemeris (3000-09-20); keeping 2950-05-23." in _errors(at)
    assert _target(at) == ("2950-05-23", 30)
    assert _age_box(at).value == 30
    at.run()
    assert _target(at) == ("2950-05-23", 30)
    assert _age_box(at).value == 30
    _goto(at, "fardar")
    assert _target(at) == ("2950-05-23", 30)
    assert at.session_state["_target_age"] == 30


def _save(at, name):
    [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value(name).run()
    [b for b in at.sidebar.button if "Save" in b.label][0].click().run()
    assert_no_exception(at, "the save")


def _typed_age_survives_the_chart_page(at, record):
    """On Revolutions, type 300; visit the Chart page; come back: 300 stands,
    and a Save writes it."""
    _goto(at, "timing")
    _age_box(at).set_value(300).run()
    assert _age_box(at).value == 300
    _goto(at, "chart")
    assert_no_exception(at, "the visit to Chart")
    assert _target(at) == (f"{record + 300:04d}-05-23", 300)
    _goto(at, "timing")
    assert _age_box(at).value == 300
    assert _target(at) == (f"{record + 300:04d}-05-23", 300)
    _save(at, "Typed")
    saved = json.loads(_store_path().read_text())["Typed"]
    assert (saved["target_date"], saved["target_age"]) == (f"{record + 300:04d}-05-23", 300)


def test_b03_a_typed_age_survives_a_birth_edit_made_on_the_chart_page(tmp_path, monkeypatch):
    """The checker's road J: a record born 1240-05-23 with Age 1760, loaded on
    the Chart page, its birth set to 2026-05-23 there. The age typed on
    Revolutions afterwards stands through a visit to Chart. With the kept age
    written into the box's key at the top level, the box went back to 974
    and a Save wrote 974."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _save(_aged("timing", 1760), "Old")
    at = make_app(date="1240-05-23", page="chart").run()
    at.sidebar.selectbox(key="chart_picker").select("Old").run()
    assert_no_exception(at, "the load")
    _born(at, "2026-05-23")
    at.run()
    assert _target(at) == KEPT
    _goto(at, "timing")
    assert _age_box(at).value == 974
    _typed_age_survives_the_chart_page(at, 2026)


def test_b03_a_typed_age_survives_a_record_loaded_on_the_chart_page(tmp_path, monkeypatch):
    """The checker's road I: a record whose age is out of reach, loaded on the
    Chart page, no birth edit at all. This passed at e7f10f1; the top-level
    write broke it."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _save(_aged("timing", 50, born="2026-05-23"), "Far")
    store = json.loads(_store_path().read_text())
    store["Far"].update(target_age=1760, target_date="3000-05-23")
    _store_path().write_text(json.dumps(store))
    at = make_app(date="1240-05-23", page="chart").run()
    at.sidebar.selectbox(key="chart_picker").select("Far").run()
    assert_no_exception(at, "the load")
    assert _target(at) == KEPT
    _typed_age_survives_the_chart_page(at, 2026)
