"""The independent review's naming and status findings (F07, F09, F10, F11, F15).

F10 renames two columns of the aspects table and turns the third from a
Yes/No into a named state. The states are the ones the two connection tests
actually decide and no others: the tests themselves are untouched, and
``Rules differ`` still compares their booleans, which is pinned here so a
display change cannot quietly become a doctrine change.

F07 separates the end of a bounded search from an absence, F09 carries the
circumpolar approximation with the hour lord onto every page, F15 reconciles
three pieces of help with what the app does, and F11 gives the four
classical Lots the provenance rows their own note promises.
"""
from __future__ import annotations

import datetime
import json
import pathlib

import pytest

from conftest import (CHARTS, EXECUTABLE_DIR, FLORENCE, LOCAL_TIME,
                      assert_no_exception, find_table, make_app, ui_source)

# The Moon-Sun row of the default chart is the review's E11: the three
# columns that appeared to contradict each other, now each naming its own
# fact. Under Sahl the pair is past exact and still inside his window.
DEFAULT = "1240-05-23"
POLAR = {"date": "2025-06-21", "lat": 69.6492, "lon": 18.9553}


# --- The engine's own states ---------------------------------------------

def _aspects(engine, day, profile="Sahl"):
    y, m, d = (int(part) for part in day.split("-"))
    hour = LOCAL_TIME.hour + LOCAL_TIME.minute / 60.0
    jd = engine["civil_local_to_jd_ut"](y, m, d, hour, FLORENCE[1] / 15.0)
    chart = engine["calculate_traditional_chart_jd"](jd, *FLORENCE)
    engine["set_readings"](CONNECTION_PROFILE=profile)
    try:
        return engine["evaluate_ptolemaic_aspects"](chart["planetary_data"])
    finally:
        engine["set_readings"](CONNECTION_PROFILE="Sahl")


def _row(rows, a, b):
    hit = [r for r in rows if {r["Light Planet"], r["Heavy Planet"]} == {a, b}]
    assert len(hit) == 1, hit
    return hit[0]


def test_the_columns_are_named_as_the_ruling_names_them(engine):
    row = _aspects(engine, DEFAULT)[0]
    assert "Connecting planet" in row and "Connection" in row
    assert "Applying Planet" not in row and "Connected" not in row


def test_the_moon_sun_row_of_the_default_chart(engine):
    """Astra's E11, read again: the arrow, the motion and the state, each
    saying its own thing instead of appearing to contradict the others."""
    row = _row(_aspects(engine, DEFAULT), "Moon", "Sun")
    assert (row["Connecting planet"], row["Motion"]) == ("Moon → Sun", "Separating")
    assert row["Connection"] == "Under a single blanket"
    assert row["Rules differ"] == "Yes"


def test_the_same_row_under_abu_mashar(engine):
    """One minute past exact has already separated for him (VII.5, 16), so
    the same pair is Separated under his rule and the arrow does not move."""
    row = _row(_aspects(engine, DEFAULT, "Abu Ma'shar"), "Moon", "Sun")
    assert (row["Connecting planet"], row["Motion"], row["Connection"]) == \
        ("Moon → Sun", "Separating", "Separated"), row


@pytest.mark.parametrize("state", ["Applying", "Not yet", "–"])
def test_every_state_sahl_can_produce_appears_in_the_fixture_charts(engine, state):
    seen = {r["Connection"] for day in CHARTS for r in _aspects(engine, day)}
    assert state in seen, repr(seen)


def test_sahl_snapshot_does_not_invent_a_completed_history(engine):
    seen = [r["Connection"] for day in CHARTS for r in _aspects(engine, day)]
    assert any(engine["is_unresolved"](state) for state in seen)
    assert 'Under a single blanket' in seen
    assert {state for state in seen if isinstance(state, str)} <= {'Applying', 'Not yet', '–', 'Under a single blanket', 'Separated'}


def test_abu_mashar_has_no_window_after_exactness(engine):
    """His profile runs Not yet, Applying, Separated and the dash: there is
    no post-exact window in his test, so no row can be under the blanket."""
    seen = {r["Connection"] for day in CHARTS for r in _aspects(engine, day, "Abu Ma'shar")}
    assert seen == {"Applying", "Not yet", "Separated", "–"}


def test_an_aversion_row_shows_a_dash_and_not_a_verdict(engine):
    rows = [r for r in _aspects(engine, DEFAULT) if r["Aspect"] == "Aversion"]
    assert rows
    # Sahl's out-of-sign body connection (20-21) is the one aversion row
    # that can be connected; every other one is not configured at all.
    for row in rows:
        if "Body connection" in row["Strength"]:
            assert row["Connection"] in ("Applying", "Under a single blanket"), row
        elif "Completed bodily encounter" in row["Strength"]:
            assert row["Connection"] in ("Under a single blanket", "Separated"), row
        else:
            assert row["Connection"] == "–", row


def test_the_state_is_the_connection_test_and_nothing_else(engine):
    """The display changed; the boolean did not. Every row's state agrees
    with _is_connected() under the profile in force, on all six charts."""
    connected_states = {"Applying", "Under a single blanket", "Exact — connection completed"}
    for profile in ("Sahl", "Abu Ma'shar"):
        for day in CHARTS:
            y, m, d = (int(part) for part in day.split("-"))
            hour = LOCAL_TIME.hour + LOCAL_TIME.minute / 60.0
            jd = engine["civil_local_to_jd_ut"](y, m, d, hour, FLORENCE[1] / 15.0)
            chart = engine["calculate_traditional_chart_jd"](jd, *FLORENCE)
            engine["set_readings"](CONNECTION_PROFILE=profile)
            try:
                pairs = engine["_pairwise_configurations"](chart["planetary_data"])
                shown = engine["evaluate_ptolemaic_aspects"](chart["planetary_data"])
                for raw, row in zip(pairs, shown):
                    result = engine["_is_connected"](raw)
                    if engine["is_unresolved"](row["Connection"]):
                        assert engine["is_unresolved"](result) or result is False
                    else:
                        assert (row["Connection"] in connected_states) == result, (profile, day, row)
            finally:
                engine["set_readings"](CONNECTION_PROFILE="Sahl")


def test_exact_completion_is_decided_without_rounding(engine):
    p = {'Moon': {'longitude': 10., 'speed_in_lon': 13.},
         'Saturn': {'longitude': 10., 'speed_in_lon': .1}}
    assert engine['evaluate_ptolemaic_aspects'](p)[0]['Connection'] == 'Exact — connection completed'
    p['Moon']['longitude'] -= 1e-10
    assert engine['evaluate_ptolemaic_aspects'](p)[0]['Connection'] == 'Applying'


# --- The table as the page renders it ------------------------------------

@pytest.fixture(scope="module")
def configurations():
    at = make_app(page="configurations")
    at.run()
    assert_no_exception(at, "configurations")
    return at


def test_the_rendered_table_carries_the_two_new_headings(configurations):
    node = find_table(configurations, "Aspects, aversions and connections")
    frame = node.value
    assert "Connecting planet" in frame.columns and "Connection" in frame.columns
    assert "Applying Planet" not in frame.columns and "Connected" not in frame.columns


@pytest.mark.parametrize("column, phrase", [
    ("Connecting planet", "connects with"),
    ("Motion", "going straightaway to"),
    ("Connection", "Under a single blanket"),
    ("Orientation", "Dexter, Dykes's right"),
])
def test_the_four_columns_define_themselves_on_the_heading(configurations, column, phrase):
    config = json.loads(find_table(configurations, "Aspects, aversions and connections").proto.columns)
    assert phrase in config[column]["help"], config[column]["help"]


def test_one_sentence_under_the_table_says_why_the_three_can_differ(configurations):
    captions = [c.value for c in configurations.main.caption]
    assert any("Under this app's reading of Sahl, the Sun's 15° counts" in c for c in captions), captions


# --- F07: a bounded search is not an absence -----------------------------

# 1240-09-18 finds no revoking, resistance or escape inside the horizon.
NO_FORWARD = "1240-09-18"


@pytest.fixture(scope="module")
def no_forward_events():
    at = make_app(date=NO_FORWARD, page="configurations", view="Course text and supplement")
    at.run()
    assert_no_exception(at, "configurations, no forward events")
    return at


def test_the_forward_finding_keeps_its_heading_when_it_has_no_rows(no_forward_events):
    assert any(h.value == "Forward-Looking Conditions" for h in no_forward_events.main.subheader)


def test_the_empty_forward_finding_names_the_horizon_it_searched(no_forward_events):
    captions = [c.value for c in no_forward_events.main.caption]
    assert "No qualifying event found within 200 days of the chart; later events were not evaluated." \
        in captions, captions


def test_the_bounded_search_is_not_listed_as_absent(no_forward_events):
    absent = [c.value for c in no_forward_events.main.caption if c.value.startswith("Not present in this chart")]
    assert not any("Forward-Looking Conditions" in line for line in absent), absent


def test_the_horizon_printed_is_the_simulation_s_own(engine):
    """The sentence is not a number retyped on the page: it is the
    horizon _simulate_forward() actually ran to."""
    hour = LOCAL_TIME.hour + LOCAL_TIME.minute / 60.0
    jd = engine["civil_local_to_jd_ut"](1240, 9, 18, hour, FLORENCE[1] / 15.0)
    chart = engine["calculate_traditional_chart_jd"](jd, *FLORENCE)
    sim = engine["_simulate_forward"](chart["planetary_data"], chart["julian_day"])
    assert int(sim["horizon_days"]) == 200


def test_findings_whose_emptiness_is_instantaneous_still_join_the_absent_line():
    """Only a table whose rows can come from a forward search is bounded.
    Favor & Recompense tests the chart moment (its forward leg is a column
    on rows found at the chart), so an empty one IS an absence and is named
    as one. Prevented connections was counted with it until the hostile pass
    of 2026-10-03 (L5-07): two of its kinds, Abu Ma'shar's further cuttings,
    are rows the 200-day search finds or does not, so an empty table is the
    end of that search and says so, as Forward-Looking Conditions does."""
    import ast
    tree = ast.parse(ui_source())
    with_absent = [node for node in ast.walk(tree)
                   if isinstance(node, ast.Call)
                   and getattr(node.func, "id", None) == "_finding"
                   and any(kw.arg == "absent" for kw in node.keywords)]
    assert sorted(node.args[1].value for node in with_absent) == ["Forward-Looking Conditions", "Prevented connections"], \
        [ast.unparse(node)[:120] for node in with_absent]


# --- F09: the approximation travels with the value -----------------------

def _polar(page):
    at = make_app(date=POLAR["date"], page=page)
    at.session_state["manual_lat_key"] = POLAR["lat"]
    at.session_state["manual_lon_key"] = POLAR["lon"]
    at.session_state["time_input_key"] = datetime.time(12, 0)
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = 0.0
    at.run()
    assert_no_exception(at, f"polar {page}")
    return at


@pytest.mark.parametrize("page", ["chart", "configurations", "timing"])
def test_the_hour_lord_is_qualified_on_every_page(page):
    """Astra's E10: no sunrise or sunset at this date and latitude, so the
    hour is not a temporal hour, and the strip says so wherever it prints."""
    at = _polar(page)
    strip = [c.value for c in at.main.caption if "Hour lord" in c.value]
    assert len(strip) == 1, strip
    assert "(equal-hour approximation)" in strip[0], strip[0]


def test_the_default_chart_s_hour_lord_is_not_qualified(configurations):
    strip = [c.value for c in configurations.main.caption if "Hour lord" in c.value]
    assert len(strip) == 1 and "approximation" not in strip[0], strip


def test_the_chart_page_keeps_its_fuller_warning():
    at = _polar("chart")
    assert any("not a temporal hour" in c.value for c in at.main.caption)


# --- F15: one heading, and help that describes what the app does ---------

def test_topical_planets_in_houses_is_headed_once():
    at = make_app(page="dignities")
    at.run()
    assert_no_exception(at, "dignities")
    headings = [h for h in at.main.subheader if h.value == "Topical Planets in Houses"]
    assert len(headings) == 1, [h.value for h in at.main.subheader]
    # The surviving sentences are the ones that are true: the PN IV halves
    # are Book II's own sentences, the Rhetorius halves Ch. 57's and
    # Mathesis III's. They stand in the block's notes expander since the
    # tooltip became one sentence (readability branch A, 2026-09-17).
    notes = "\n".join(m.value for node in at.main if getattr(node, "type", None) == "status"
                      and node.label == "Sources and editorial notes" for m in node.markdown)
    assert "this app's paraphrases of Rhetorius, Astrological Compendium Ch. 57" in notes
    assert "this app's paraphrases of Abu Ma'shar's PN IV Book II" in notes
    assert "still print" not in notes and "still print" not in headings[0].help
    assert "not in hand" not in notes and "not in hand" not in headings[0].help


def test_the_condition_caption_says_what_the_dignities_page_does(configurations):
    # The qualification stands above the table as body text since
    # readability branch A (2026-09-17); the sentences are the caption's.
    caption = [m.value for m in configurations.main.markdown
               if "Net and Verdict are this app's heuristic" in m.value]
    assert len(caption) == 1, caption
    text = caption[0]
    assert "chooses neither" in text and "Indeterminate on both" in text
    assert "have to pick one of two readings" not in text
    # The doctrine sentences around it are untouched.
    assert "he nowhere adds them up, and Gr. Intr. VII.6 gives no weighting and no tie rule" in text


def test_the_small_days_note_describes_the_control_that_exists():
    at = make_app(page="days")
    at.run()
    assert_no_exception(at, "days")
    # Re-pinned on branch C: the small days' caption is a notes expander
    # ("How the small days are read"); its sentences are read from there.
    notes = [n for n in at.main if getattr(n, "type", None) == "status" and n.label == "How the small days are read"]
    assert len(notes) == 1
    note = " ".join(m.value for m in notes[0].markdown)
    assert "59' 08\"" in note
    assert "Only the revolution's Ascendant is directed" not in note
    assert "the selector above carries it out" in note


def test_the_alternate_point_control_is_on_the_page():
    at = make_app(page="days")
    at.run()
    labels = [s.label for s in at.main.selectbox]
    assert any(label.startswith("Also direct, for the small days") for label in labels), labels


# --- F11: the classical Lots' provenance ---------------------------------

def test_the_four_classical_lots_have_provenance_rows():
    at = make_app(page="lots")
    at.run()
    assert_no_exception(at, "lots")
    provenance = None
    for node in at.main:
        if getattr(node, "type", None) == "table" and "Editor\u2019s note" in list(node.value.columns):
            provenance = node.value
    assert provenance is not None, "the provenance panel is on the page"
    lots = list(provenance["Lot"])
    for name in ("Lot of Fortune", "Lot of Spirit", "Lot of Exaltation", "Lot of Basis"):
        assert name in lots, lots[:8]


def test_their_provenance_is_the_definition_s_own_fields(engine):
    """No text is written for them here: source, standing and note come off
    the same LOT_DEFINITIONS rows every other Lot's does."""
    definitions = {d["name"]: d for d in engine["LOT_DEFINITIONS"]}
    for name in ("Lot of Fortune", "Lot of Spirit", "Lot of Exaltation", "Lot of Basis"):
        assert definitions[name]["source"] and definitions[name]["confidence"]


def test_the_classical_note_points_where_the_rows_are():
    at = make_app(page="lots")
    at.run()
    notes = [m.value for m in at.main.markdown if "All four carry their provenance" in m.value]
    assert len(notes) == 1, notes
    assert "Provenance and standing per Lot" in notes[0]


# --- The retired differential --------------------------------------------

def test_the_dead_differential_is_gone():
    source = (EXECUTABLE_DIR / "tests" / "test_engine_split_2026_09_15.py").read_text(encoding="utf-8")
    assert "_main_engine_namespace" not in source
    assert "test_every_reading_and_chart_evaluates_as_main_did" not in source
    assert "process/tae_docs/ENGINE_SPLIT_2026-09-15.md" in source


def test_no_test_compares_this_checkout_against_a_branch():
    """No suite file may read a file out of a git ref to compare the working
    tree with it.

    Such a proof answers a question only while its own branch is open: once
    the branch merges, the ref it reads IS the working tree and the
    comparison is with itself. The nine of 2026-09-16 were retired for
    failing on main after every merge; four helpers outlived them, uncalled,
    until 2026-09-22 -- by which time the repository's history began at one
    commit and the comparison could never have said anything at all. A
    branch-time proof belongs in that branch's own notes, or its expected
    value belongs in a committed fixture.
    """
    offenders = []
    for path in sorted((EXECUTABLE_DIR / "tests").glob("test_*.py")):
        source = path.read_text(encoding="utf-8")
        if path.name == pathlib.Path(__file__).name:
            continue
        for ref in ('"git", "show"', "'git', 'show'", "git show "):
            if ref in source:
                offenders.append(f"{path.name}: {ref}")
        if "_main_engine_namespace" in source or "_from_main" in source:
            offenders.append(f"{path.name}: a namespace-from-main helper")
    assert offenders == [], offenders
