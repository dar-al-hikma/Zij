"""Lane F8 of the hostile pass of 2026-10-03, part A: what the pages say.

The items of the part that had no xfail of their own, each a test written
red against the unchanged tree and turned green by the wording it names.
Nothing here pins a decision of the engine: every assertion is about the
words a reader is shown, or a developer path, or a label that names a
library the app no longer uses.

Ids are the scope file's: C-02, C-03/C-08, C-04 (the hostile pass's report),
S1-3, S1-4 (lane F1's build and check), F7-8, F7-9, F7-31 (lane F7's check),
F2-wheel, F2-22, F2-35, F2-41/43 (lane F2's checks), F6-T3 (lane F6's third
re-check). F2-36 is the pinned ordinal in test_prediction_pages_2026_09_17.

The part's blind check found two defects, each with a test at the foot of
this file: L7-06 had rounded Indicator 15's Distance, and written "-" for its
empty cells, in the list the export reads too, so the JSON no longer carried
the engine's values its own precision sentence promises (check finding 6);
and L4-08's caption set the first ninth-part's sign beside "this month's
sign" as if it were that sign (check finding 13).
"""
from __future__ import annotations

import base64
import json
import re
from datetime import time
from pathlib import Path

import pytest

from conftest import (APP_PATH, EXECUTABLE_DIR, apply_switches, assert_no_exception, find_table, make_app,
                      sync_engine_to_environment)


def _sidebar_errors(at):
    return "\n".join(e.value for e in at.sidebar.error)


def _main_text(at):
    """Every markdown and caption body on the page, expanders included."""
    out = []
    for node in at.main:
        if getattr(node, "type", "") in ("markdown", "caption"):
            value = getattr(node, "value", None)
            if isinstance(value, str):
                out.append(value)
    return out


def _svgs(at):
    found = []

    def walk(node):
        for child in getattr(node, "children", {}).values():
            if type(child).__name__ == "Image":
                url = child.proto.imgs[0].url
                if url.startswith("data:image/svg+xml;base64,"):
                    found.append(base64.b64decode(url.split(",", 1)[1]).decode("utf-8"))
            else:
                walk(child)
    walk(at.main)
    return found


# --- C-02: an atlas place with no region -------------------------------------

def test_c02_a_place_with_no_region_is_labelled_without_an_empty_one():
    at = make_app(page="chart")
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = "Hong Kong"
    at.run()
    assert_no_exception(at, "Hong Kong")
    box = [s for s in at.sidebar.selectbox if s.label == "Select specific location:"][0]
    assert box.options[0] == "Hong Kong (HK)", box.options[:3]
    assert not [o for o in box.options if re.search(r",\s*\(", o)], box.options
    # A place with a region keeps it.
    at.session_state["location_input_key"] = "Florence"
    at.run()
    box = [s for s in at.sidebar.selectbox if s.label == "Select specific location:"][0]
    assert re.fullmatch(r"Florence, \S.* \(IT\)", box.options[0]), box.options[0]


# --- C-03 / C-08: no developer's home directory in a shipped file -----------

_HOME_PATH = re.compile(r"/(?:home|Users)/[A-Za-z_][A-Za-z0-9_.-]*/|[A-Z]:\\Users\\[A-Za-z]")
_TEXT_SUFFIXES = {".py", ".txt", ".md", ".spec", ".toml", ".yml", ".yaml", ".ini", ".cfg", ".json", ".tsv"}
_SKIP_DIRS = {".git", "__pycache__", ".venv", ".xdg-scratch", "build", "dist"}


def test_c03_c08_no_shipped_file_names_a_developers_home_directory():
    offenders = []
    for path in sorted(EXECUTABLE_DIR.rglob("*")):
        rel = path.relative_to(EXECUTABLE_DIR)
        if set(rel.parts) & _SKIP_DIRS or not path.is_file() or path.suffix not in _TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if _HOME_PATH.search(line):
                offenders.append(f"{rel}:{n}: {line.strip()[:90]}")
    assert not offenders, offenders


# --- C-04: the bundle identifier ---------------------------------------------

def test_c04_the_macos_bundle_identifier_names_the_app_not_its_former_name():
    spec = (EXECUTABLE_DIR / "build.spec").read_text(encoding="utf-8")
    ids = re.findall(r'bundle_identifier\s*=\s*"([^"]+)"', spec)
    assert len(ids) == 1, ids
    ident = ids[0].lower()
    assert "almuten" not in ident and "traditionalastrology" not in ident, ident
    assert ident.split(".")[-1] == "zij", ident
    assert re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", ident), ident


# --- S1-3: a repeated clock time is not always a daylight-saving fall-back ----

def _zone_app(date, hhmm, lat, lon):
    at = make_app(date=date, page="chart")
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.session_state["time_input_key"] = time(*hhmm)
    import engine
    at.session_state["time_standard_key"] = engine.TIME_STANDARD_OPTIONS[1]
    at.run()
    assert_no_exception(at, f"{date} {hhmm}")
    return at


@pytest.mark.parametrize("date, hhmm, lat, lon, zone", [
    ("1883-11-18", (12, 2), 40.7128, -74.006, "America/New_York"),     # standard time adopted: clocks set back
    ("1888-01-01", (0, 0), 35.6762, 139.6503, "Asia/Tokyo"),           # standard time adopted: clocks set back
    ("2024-11-03", (1, 30), 40.7128, -74.006, "America/New_York"),     # a daylight-saving fall-back
])
def test_s1_3_the_repeated_hour_sentence_does_not_say_daylight_saving(date, hhmm, lat, lon, zone):
    at = _zone_app(date, hhmm, lat, lon)
    text = _sidebar_errors(at)
    assert f"happens twice in {zone}" in text, text
    assert "daylight" not in text.lower(), text


def test_s1_3_the_skipped_hour_sentence_does_not_say_daylight_saving_either():
    at = _zone_app("2024-03-10", (2, 30), 40.7128, -74.006)
    text = _sidebar_errors(at)
    assert "does not exist in America/New_York" in text, text
    assert "daylight" not in text.lower(), text


# --- S1-4: the time standard's label, and the records saved under the old one ---

OLD_STANDARD = "Standard time (pytz)"


def test_s1_4_the_standard_time_option_names_no_library(engine):
    options = engine["TIME_STANDARD_OPTIONS"]
    assert len(options) == 3 and options[1].startswith("Standard time"), options
    assert not [o for o in options if "pytz" in o.lower()], options
    assert engine["time_standard_current"](OLD_STANDARD) == options[1]
    assert [engine["time_standard_current"](o) for o in options] == list(options)


def test_s1_4_the_sidebar_offers_no_library_name():
    at = make_app(page="chart").run()
    assert_no_exception(at, "chart")
    box = [s for s in at.sidebar.selectbox if s.label == "Time standard"][0]
    assert not [o for o in box.options if "pytz" in o.lower()], box.options


def test_s1_4_a_session_seeded_with_the_old_label_runs_under_the_new_one():
    import engine
    at = make_app(date="1982-11-19", page="chart")
    at.session_state["manual_lat_key"], at.session_state["manual_lon_key"] = 45.37334, -84.95533
    at.session_state["time_input_key"] = time(11, 44)
    at.session_state["time_standard_key"] = OLD_STANDARD
    at.run()
    assert_no_exception(at, "old label seeded")
    assert at.session_state["time_standard_key"] == engine.TIME_STANDARD_OPTIONS[1]
    assert "UTC offset -05:00 (EST)" in "\n".join(n.value for n in at.sidebar.info)


def test_s1_4_a_record_saved_under_the_old_label_loads_unmodified(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from streamlit.util import calc_hash
    import engine
    record = {"date_string": "1982-11-19", "time_string": "11:44:00", "time_standard": OLD_STANDARD,
              "utc_offset": None, "location_query": "Petoskey, MI (US)", "lat": 45.37334, "lon": -84.95533,
              "target_mode": "Date", "target_date": "2026-09-15", "target_age": 43}
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    (tmp_path / "Zij").mkdir(parents=True)
    (tmp_path / "Zij" / "saved_charts.json").write_text(json.dumps({"Rec": record}))
    sync_engine_to_environment()
    at = AppTest.from_file(str(APP_PATH), default_timeout=300)
    at._page_hash = calc_hash("chart")
    at.run()
    at.sidebar.selectbox(key="chart_picker").select("Rec").run()
    assert_no_exception(at, "the old record")
    assert at.session_state["time_standard_key"] == engine.TIME_STANDARD_OPTIONS[1]
    assert "_loaded_without_standard" not in at.session_state
    strip = [c.value for c in at.main.caption if c.value.startswith("Rec")]
    assert strip and strip[0].startswith("Rec ·"), strip      # not "Rec (modified)"
    assert not [c for c in at.sidebar.caption if "Edited since it was saved" in c.value]
    assert "UTC offset -05:00 (EST)" in "\n".join(n.value for n in at.sidebar.info)


# --- F7-9: the Masha'allah switch names every place it reaches ---------------

def test_f7_9_the_domain_switch_names_the_revolutions_pages_domain_cells():
    at = make_app(page="sources").run()
    assert_no_exception(at, "sources")
    text = "\n".join(_main_text(at))
    affects = [t for t in text.split("\n") if t.startswith("Affects:") and "Sect table" in t]
    assert len(affects) == 1, affects
    assert "Revolutions page" in affects[0] and "I.7" in affects[0] and "II.3" in affects[0], affects[0]
    dignities = make_app(page="dignities").run()
    radio = [r for r in dignities.main.radio if r.label == "Domain (hayz)"][0]
    assert "Revolutions" in radio.help and len(radio.help) <= 300, (len(radio.help), radio.help)


# --- F7-8: an evening Mercury under Masha'allah's rule -----------------------

def test_f7_8_the_dignities_note_says_how_mercury_is_read_under_mashaallah():
    at = make_app(page="dignities", switches={"domain": "Masha'allah"}).run()
    assert_no_exception(at, "dignities, Masha'allah")
    note = [t for t in _main_text(at) if t.startswith("**Domain/hayz** follows the Domain switch")]
    assert len(note) == 1, note
    assert "Mercury" in note[0] and "westernizing" in note[0], note[0]
    # Under Abu Ma'shar's rule the clause is not there: it is the other rule's.
    plain = make_app(page="dignities").run()
    note = [t for t in _main_text(plain) if t.startswith("**Domain/hayz** follows the Domain switch")]
    assert len(note) == 1 and "westernizing" not in note[0], note


# --- F7-31: 31's slowness and the station band -------------------------------

def test_f7_31_the_condition_notes_say_31_excludes_the_station():
    import engine
    at = make_app(page="configurations")
    at.session_state["_reading_depth"] = "Course text and supplement"
    at.run()
    assert_no_exception(at, "configurations")
    texts = _main_text(at)
    heads = [i for i, t in enumerate(texts) if t.startswith("**Slow in course (31)")]
    assert len(heads) == 1, [t[:60] for t in texts if "31" in t][:5]
    body = texts[heads[0] + 1]                     # a notes section: its heading, then its body
    assert f"{engine.STATION_SPEED_TOLERANCE}" in body and "24 or 32" in body and "33" in body, body


# --- F2-wheel: the year ring names the revolution it is ---------------------

def test_f2_wheel_the_year_ring_names_the_revolutions_count():
    at = make_app(page="timing")
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "1250-05-23"           # age 10, the 9th return (17:43 UT, after noon)
    at.run(timeout=180)
    assert_no_exception(at, "timing 1250-05-23")
    wheels = [s for s in _svgs(at) if "Year, " in s]
    assert wheels, "no wheel with a year ring on the page"
    for svg in wheels:
        assert "Year, 9th return" in svg, re.findall(r"Year, [^<]*", svg)
        assert "Year, age" not in svg, re.findall(r"Year, [^<]*", svg)


# --- F2-22: the Days page's count line and the nine methods ------------------

def test_f2_22_the_days_count_line_says_the_methods_open_at_the_return(engine):
    line = engine["pn4_count_line"]("Days and months")
    assert "year opening at this return" in line, line
    assert "1, 4 and 5" in line and "from the birth" in line, line
    assert len(line) <= 400, len(line)


# --- F2-41 / F2-35: testimony #3 on the Releaser page at the table's end -----

def _releaser(date):
    at = make_app(page="releaser")
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = date
    at.run(timeout=300)
    assert_no_exception(at, f"releaser {date}")
    return at


def test_f2_41_the_releaser_page_has_no_unreachable_clause():
    source = APP_PATH.read_text(encoding="utf-8")
    assert "counts nothing here" not in source


@pytest.mark.parametrize("target, inside", [((1240, 5, 24), True), ((1241, 5, 22), True), ((1250, 5, 23), True),
                                            ((1300, 1, 1), True), ((1359, 12, 1), True), ((1360, 5, 24), False)])
def test_f2_41_a_target_inside_the_table_has_its_revolution_inside_it(engine, target, inside):
    """Why the clause could go: the releaser's direction is available at the
    target only if the revolution's moment, which is never later, is inside
    the table too -- so the line's revolution half always has a reading.
    The last target is the span end, past the table with its revolution
    still inside it (F2-35)."""
    lat, lon = 43.7792, 11.2463
    jd = engine["civil_local_to_jd_ut"](1240, 5, 23, 14.5, lon / 15.0)
    chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
    chron = engine["calculate_chronocrats"](jd, lat, lon, 14, lon / 15.0)
    b = engine["pn4_timing_bundle"](chart, lat, lon, engine["CivilDate"](1240, 5, 23), engine["CivilDate"](*target),
                                    engine["PN4_MONTHLY_TURN_OPTIONS"][0], chron)
    assert b["revolution_window"][0] <= b["elapsed_years"]
    assert (b["pn4_releaser"]["status"] == "available") is inside, b["pn4_releaser"]["note"]
    assert b["releaser_sr"] is not None, target


def test_f2_35_at_the_span_end_the_page_says_what_the_governor_counts():
    # 1360-05-24: the revolution opens at 119.9997 years elapsed, the
    # target is 120.005 -- past the table, while the governor counts #3
    # from the releaser's distribution at the revolution's moment.
    at = _releaser("1360-05-24")
    lines = [t for t in _main_text(at) if t.startswith("**PN IV testimony #3:**")]
    assert len(lines) == 1, [t[:80] for t in _main_text(at) if "outside the direction table" in t or "#3" in t]
    assert "at the revolution's moment" in lines[0] and "distributor **Jupiter**" in lines[0], lines[0]
    assert "past the 120-year table" in lines[0], lines[0]


def test_f2_35_past_the_table_at_both_moments_the_note_stands_alone():
    at = _releaser("1361-06-01")
    assert not [t for t in _main_text(at) if t.startswith("**PN IV testimony #3:**")]
    assert [t for t in _main_text(at) if "outside the direction table" in t]


def test_f2_43_no_comment_reads_the_hyphenated_stale_range():
    from conftest import source_files
    files = source_files()                            # every source module, not the pair
    assert len(files) >= 2, files
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"indicators #3-#4", text), path.name


# --- F6-T3: reading (7) where the Ascendant is the releaser -----------------

def test_f6_t3_reading_7_does_not_point_at_a_sentence_the_verdict_does_not_print():
    at = make_app(date="1240-02-07", page="releaser")
    at.session_state["time_input_key"] = time(12, 0)
    at.run(timeout=180)
    assert_no_exception(at, "1240-02-07 12:00")
    verdict = [t for t in _main_text(at) if "The releaser is the Ascendant" in t]
    assert verdict and "1.15, 15" not in verdict[0], verdict      # the verdict names no sentence
    note = next(t for t in _main_text(at) if "the verdict names" in t)
    assert "that sentence is" not in note, note[-160:]
    assert note.endswith("On this chart the Ascendant was reached by 1.15, 15."), note[-160:]


# --- The check's defect 6 (L7-06): the page rounds, the JSON does not --------

def _indicator_15(engine, birth=(1240, 5, 23), target=(2026, 10, 3)):
    """The engine's own Indicator 15 records for the harness chart (14:30
    LMT, Florence), computed as app.py computes the bundle."""
    lat, lon = 43.7792, 11.2463
    jd = engine["civil_local_to_jd_ut"](*birth, 14.5, lon / 15.0)
    chart = engine["calculate_traditional_chart_jd"](jd, lat, lon)
    chron = engine["calculate_chronocrats"](jd, lat, lon, 14, lon / 15.0)
    b = engine["pn4_timing_bundle"](chart, lat, lon, engine["CivilDate"](*birth), engine["CivilDate"](*target),
                                    engine["PN4_MONTHLY_TURN_OPTIONS"][0], chron)
    return b["indicator_relationships"]


def _timing_at(target="2026-10-03"):
    at = make_app(page="timing")
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = target
    at.run(timeout=180)
    assert_no_exception(at, f"timing {target}")
    return at


_EMPTY_WHEN_AVERSE = ("Motion", "Applicant", "Receiver")


def test_l7_06_the_json_carries_indicator_15s_engine_values(engine):
    """The JSON's precision sentence: "Values are the engine's own, at the
    precision it holds them ... where a page or a report rounds, the JSON
    does not." Indicator 15's Distance is the engine's float, and a pair in
    aversion, which has no motion, applicant or receiver, is null there --
    as the Planetary Positions' Absolute is the engine's float (L5-04). The
    reports print the float as they print every bare number."""
    records = _indicator_15(engine)
    averse = [r for r in records if r["Motion"] is None]
    assert records and averse, "the chart has no pair in aversion; pick a target that has one"
    at = _timing_at()
    export = json.loads(json.dumps(at.session_state["_analysis_export"]))
    entries = export["results"]["Prediction"]["Indicator 15: relationship details"]
    assert len(entries) == 1, len(entries)
    rows = entries[0]["rows"]
    assert [(r["Role"], r["Partner"]) for r in rows] == [(r["Role"], r["Partner"]) for r in records]
    markdown = at.session_state["_analysis_markdown"]
    for row, record in zip(rows, records):
        assert isinstance(row["Distance"], float) and row["Distance"] == record["Distance"], (row["Distance"], record)
        assert f"| {engine['_export_cell'](record['Distance'])} |" in markdown, record["Distance"]
        for key in _EMPTY_WHEN_AVERSE:
            if record[key] is None:
                assert row[key] is None, (key, row[key], record["Partner"])
    assert '"Distance": ' + repr(averse[0]["Distance"]) in json.dumps(at.session_state["_analysis_export"])


def test_l7_06_the_page_prints_hundredths_and_the_states_own_dash(engine):
    """The page: the Distance to hundredths, and an aversion's empty Motion,
    Applicant and Receiver the dash its State column already prints for it
    (an en dash), not a hyphen beside it (the check's note 7)."""
    records = _indicator_15(engine)
    assert [r for r in records if r["Motion"] is None], "no pair in aversion"
    at = _timing_at()
    df = find_table(at, "Indicator 15: relationship details").value
    assert len(df) == len(records), (len(df), len(records))
    for (_i, cell), record in zip(df.iterrows(), records):
        assert cell["Distance"] == f"{record['Distance']:.2f}", (cell["Distance"], record["Distance"])
        if record["Motion"] is None:
            assert cell["State"] == "\u2013", cell["State"]
        for key in _EMPTY_WHEN_AVERSE:
            if record[key] is None:
                assert cell[key] == "\u2013", (key, cell[key], record["Partner"])


# --- The check's defect 13 (L4-08): the month's sign, then its ninth-part ----

def test_l4_08_the_caption_names_the_months_sign_as_the_months():
    """At the tenth birthday (month 12 of the 9th revolution) the year's sign
    turned forward is Gemini; the first ninth-part of Gemini is Libra's, whose
    lord is Venus (PN IV III.9, 7; IX.1, 12-16). The caption names Gemini as
    the month's sign and Libra as the ninth-part's, as the table's row #2
    does ("forward (from Gemini)", Libra, Venus)."""
    at = make_app(page="days")
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = "1250-05-23"
    at.run(timeout=180)
    assert_no_exception(at, "days 1250-05-23")
    table = find_table(at, "The seven indicators of the month").value
    row2 = table[table["#"] == 2].iloc[0]
    assert (row2["Sign"], row2["Lord"], row2["Turned"]) == ("Libra", "Venus", "forward (from Gemini)"), dict(row2)
    caption = next(c.value for c in at.main.caption if c.value.startswith("Month 12 of 12"))
    assert ("the first ninth-part of this month's sign (Gemini, the year's sign turned forward; "
            "that ninth-part is in Libra, lord Venus)") in caption, caption
    assert "(Libra" not in caption, caption
