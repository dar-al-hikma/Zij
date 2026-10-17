"""Page wording: lane PW of the hostile pass's wave 5.

The notes items the re-pass's checkers left for a later page-wording lane
(the coordinator's compilation, rows PW-01 .. PW-31 and EN-01), the owner's
ruling 75 (EN-02: the III.2 window line prints its bounds as "At age" does)
and the display rounding SL's check found at reachable longitudes (no printed
angle reads 360 or -0). Each test asserts what the page, the export or the
code comment should say, and failed on the base for that item's reason.
"""
import copy
import json
import os
import re
from datetime import time
from pathlib import Path

import pytest
import swisseph as swe

from conftest import EXECUTABLE_DIR, assert_no_exception, make_app, table_nodes, function_source

LMT, MANUAL = "LMT (Local Mean Time)", "Manual UTC offset"
SUPPLEMENT = "Course text and supplement"
FLORENCE_REC = {"date_string": "1983-11-19", "time_string": "10:30:00", "time_standard": LMT,
                "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}


# --- helpers ----------------------------------------------------------------------------------------


def _app_text():
    return (EXECUTABLE_DIR / "app.py").read_text(encoding="utf-8")


def _engine_text():
    from conftest import engine_source
    return engine_source()                            # every engine module, joined


def _render(page, date="1240-05-23", **state):
    at = make_app(date=date, page=page, timeout=300)
    for key, value in state.items():
        at.session_state[key] = value
    at.run(timeout=300)
    assert_no_exception(at, f"{page} {date} {state}")
    return at


def _texts(node, out=None):
    """Every string a reader can see under ``node``."""
    out = [] if out is None else out
    for attr in ("value", "label", "help", "body"):
        try:
            v = getattr(node, attr)
        except Exception:
            continue
        if isinstance(v, str) and v:
            out.append(v)
    proto = getattr(node, "proto", None)
    if proto is not None:
        for attr in ("help", "body", "label"):
            v = getattr(proto, attr, None)
            if isinstance(v, str) and v:
                out.append(v)
    for child in (getattr(node, "children", None) or {}).values():
        _texts(child, out)
    return out


def _captions(at):
    return [c.value for c in at.main.caption]


def _markdowns(at):
    return [m.value for m in at.main.markdown]


def _strip(at):
    return next(c.value for c in at.main.caption if "\n**" in c.value and " · " in c.value)


def _null_cells_drawn_as_none(at, heading=None):
    """(heading, holes) for every grid holding a missing value with no
    placeholder: Streamlit draws a missing value as "None" unless the
    dataframe names a placeholder (the K-17 helper)."""
    out = []
    for found, node in table_nodes(at):
        if heading is not None and found != heading:
            continue
        df = node.value
        holes = {str(c): int(df[c].isna().sum()) for c in df.columns if df[c].isna().any()}
        if not holes:
            continue
        proto = getattr(node, "proto", None)
        placeholder = proto.placeholder if proto is not None and proto.HasField("placeholder") else None
        if placeholder is None or placeholder == "None":
            out.append((found, holes))
    return out


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """A disposable XDG directory; preferences stay off."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    return tmp_path


def _store():
    d = Path(os.environ["XDG_DATA_HOME"]) / "Zij"
    d.mkdir(parents=True, exist_ok=True)
    return d / "saved_charts.json"


def _open_record(name, record):
    _store().write_text(json.dumps({name: record}), encoding="utf-8")
    at = make_app(page="chart", timeout=300).run(timeout=300)
    at.sidebar.selectbox(key="chart_picker").select(name).run(timeout=300)
    assert_no_exception(at, f"the record {name!r}")
    return at


def _manual(page, date, hh, mm, lat, lon, offset, **state):
    return _render(page, date=date, time_input_key=time(hh, mm), manual_lat_key=lat, manual_lon_key=lon,
                   time_standard_key=MANUAL, utc_offset_key=offset, **state)


def _florence(engine):
    return engine["calculate_traditional_chart_jd"](swe.julday(1240, 5, 23, 13.75, swe.JUL_CAL), 43.7792, 11.2463)


# --- PW-01, PW-02: a null cell in a finding's table is drawn empty --------------------------------------

def test_pw01_forward_looking_conditions_draws_no_none():
    """Configurations, 1313-02-22 14:30 LMT at -23.89, -71.84: Forward-Looking
    Conditions holds a Revoking and an Escape row with null cells, and the
    table named no placeholder, so Streamlit drew "None" in each."""
    at = _render("configurations", date="1313-02-22", manual_lat_key=-23.89, manual_lon_key=-71.84)
    nodes = [n for h, n in table_nodes(at) if h == "Forward-Looking Conditions"]
    assert nodes and any(n.value.isna().any().any() for n in nodes), "the premise: null cells in the table"
    drawn = _null_cells_drawn_as_none(at)
    assert not drawn, drawn


def test_pw02_corruption_of_the_moon_draws_no_none_where_unresolved_is_empty(monkeypatch):
    """Two merged outcomes, 104 settled by one clause and another clause
    open: the frame holds {'Count': 1, 'Unresolved': None}, drawn "None"."""
    at = make_app(page="configurations", timeout=300)
    import engine as module

    def outcome(extra):
        t = {n: {"matched": False, "clauses": []} for n in range(103, 113)}
        t[104] = {"matched": True, "clauses": ["In her own fall, Scorpio"]}
        labels = ["In her own fall, Scorpio (104)"]
        if extra:
            t[104]["clauses"].append("Connecting with Saturn, in its own fall")
            labels.append("Connecting with Saturn, in its own fall (104)")
        return {"testimonies": t, "unique_testimony_count": sum(x["matched"] for x in t.values()),
                "matching_instances": len(labels), "labels": labels}

    monkeypatch.setattr(module, "evaluate_corruption_of_the_moon",
                        lambda *a, **k: module._connection_merge([outcome(False), outcome(True)]))
    at.run(timeout=300)
    assert_no_exception(at, "the merged Moon outcome")
    nodes = [n for h, n in table_nodes(at) if h == "Corruption of the Moon"]
    assert nodes and nodes[0].value["Unresolved"].isna().any(), "the premise: an empty Unresolved cell"
    drawn = _null_cells_drawn_as_none(at, "Corruption of the Moon")
    assert not drawn, drawn


# --- PW-03, PW-04, PW-05, PW-18: whose weekday the day lord is ------------------------------------------

def _day_notice(at):
    return [c for c in _captions(at) if "not a temporal hour" in c or "weekday repeats" in c
            or "no sunrise fell on this civil date" in c]


def test_pw03_the_repeated_notice_names_its_rule_this_apps_reading():
    """71.5N 25E LMT 2000-05-10 12:00: the second Tuesday, equal hours. The
    notice says the weekday repeats without calling the rule the app's."""
    at = _render("chart", date="2000-05-10", time_input_key=time(12, 0), manual_lat_key=71.5,
                 manual_lon_key=25.0, time_standard_key=LMT)
    notice = [c for c in _captions(at) if "not a temporal hour" in c]
    assert len(notice) == 1 and "two sunrises fell on one civil date" in notice[0], notice
    assert "this app's reading" in notice[0], notice[0]
    assert len(notice[0]) <= 400, len(notice[0])


def test_pw04_the_repeated_caption_says_the_hours_count_from_him_again():
    """40N 0E at UTC-7, 2000-02-10 00:12: the day opened by the second
    sunrise of the civil 2000-02-09 (a Wednesday) is Mercury's again, and its
    first hour is his: the hour before it was Saturn's (Wednesday's last
    night hour), so the chain of Gr. Intr. VI.33, 6-7 does not run on."""
    at = _manual("chart", "2000-02-10", 0, 12, 40.0, 0.0, -7.0)
    caption = [c for c in _captions(at) if c.startswith("**The Lord of the Day's weekday repeats here:**")]
    assert len(caption) == 1, _captions(at)
    assert "first hour is his again" in caption[0] and "VI.33, 7" in caption[0], caption[0]
    assert len(caption[0]) <= 400, len(caption[0])


def test_pw05_a_civil_date_with_no_sunrise_flags_its_skipped_weekday(engine):
    """40N 0E at UTC-7: sunrises fall a hair before midnight on 2000-11-27
    and a hair after it on 11-29, so the civil Tuesday 11-28 has none, and
    no planetary day is Tuesday's: Monday's Moon rules it."""
    def chron(day):
        jd = swe.julday(2000, 11, day, 12.0 + 7.0)
        return engine["calculate_chronocrats"](jd, 40.0, 0.0, 12, -7.0)
    assert [chron(d)["Day Lord"] for d in (27, 28, 29)] == ["Sun", "Moon", "Mercury"], "the premise"
    assert chron(28).get("Day Lord Skipped") == "Tuesday", chron(28)
    assert not chron(27).get("Day Lord Skipped") and not chron(29).get("Day Lord Skipped")


# PW's blind check, finding 2: the flag was decided by the bracket's sunrise
# ahead, which reaches a day, and on a skipped date the next sunrise falls just
# after the following midnight: from the date's own midnight until that
# sunrise's time past it nothing was flagged, though the planetary day and the
# civil date are those flagged a moment later. 66N 0E at UTC-7: the Sun rises
# 2000-10-15 23:59:49 and 2000-10-17 00:03:10, so the Monday has none and its
# first three minutes went unflagged.
SKIPPED_FROM_MIDNIGHT = [
    (40.0, 0.0, -7.0, (2000, 11, 28), (0, 0, 0), "Tuesday"),
    (40.0, 0.0, -7.0, (2000, 11, 28), (0, 0, 30), "Tuesday"),
    (0.0, 0.0, -6.0, (2000, 1, 2), (0, 0, 5), "Sunday"),
    (66.0, 0.0, -7.0, (2000, 10, 16), (0, 2, 0), "Monday"),
]


@pytest.mark.parametrize("lat, lon, off, ymd, hms, weekday", SKIPPED_FROM_MIDNIGHT)
def test_pw05_a_skipped_date_is_flagged_from_its_first_minute(engine, lat, lon, off, ymd, hms, weekday):
    (y, m, d), (h, mi, s) = ymd, hms
    noon = engine["calculate_chronocrats"](swe.julday(y, m, d, 12.0 - off), lat, lon, 12, off)
    assert noon["Day Lord Skipped"] == weekday, f"the premise: the date has no sunrise: {noon}"
    early = engine["calculate_chronocrats"](swe.julday(y, m, d, h + mi / 60 + s / 3600 - off), lat, lon, h, off)
    assert early["Day Lord"] == noon["Day Lord"] and not early["Approximate"], f"the premise: one planetary day: {early}"
    assert early["Day Lord Skipped"] == weekday, early


@pytest.mark.parametrize("lat, off, date, hh, mm, lord, weekday", [
    (40.0, -7.0, "2000-11-28", 0, 0, "Moon", "Tuesday"),
    (66.0, -7.0, "2000-10-16", 0, 2, "Sun", "Monday"),
])
def test_pw05_the_chart_page_says_so_from_the_skipped_dates_midnight(lat, off, date, hh, mm, lord, weekday):
    at = _manual("chart", date, hh, mm, lat, 0.0, off)
    assert f"Day lord {lord} ({weekday} skipped) · " in _strip(at), _strip(at)
    said = [c for c in _captions(at) if "no sunrise fell on this civil date" in c]
    assert len(said) == 1 and f"No planetary day is {weekday}'s here" in said[0], said
    assert at.session_state["_analysis_export"]["status"]["day_lord"] == f"{lord} ({weekday} skipped)"


def test_pw05_the_chart_page_says_the_weekday_is_skipped():
    at = _manual("chart", "2000-11-28", 12, 0, 40.0, 0.0, -7.0)
    assert "Day lord Moon (Tuesday skipped) · " in _strip(at), _strip(at)
    said = [c for c in _captions(at) if "no sunrise fell on this civil date" in c]
    assert len(said) == 1 and "this app's reading" in said[0] and len(said[0]) <= 400, said


def test_pw18_the_export_status_names_the_civil_day_lord():
    """78.2N 15.6E, 2000-06-21 23:30 at UTC+0: no sunrise within a day
    behind, so the day lord is the civil weekday's; the export's status
    said nothing of it."""
    at = _manual("chart", "2000-06-21", 23, 30, 78.2, 15.6, 0.0)
    assert "(civil weekday)" in _strip(at), "the premise: the strip qualifies him"
    status = at.session_state["_analysis_export"]["status"]
    assert str(status.get("day_lord", "")).endswith("(civil weekday)"), status
    assert "| Lord of the Day | " in at.session_state["_analysis_markdown"]


# --- PW-06: past the table, each arm's line names its releaser ------------------------------------------

def test_pw06_past_the_table_each_arm_names_its_releaser():
    """Releaser, 1943-05-03 08:00 at UTC+0, Florence, target 2068-01-01: the
    lead says "Each arm's releaser, so directed, is shown below", and each
    arm's line printed only "elapsed age 124.668 is outside the direction
    table", naming no releaser, with no full stop."""
    at = _manual("releaser", "1943-05-03", 8, 0, 43.7792, 11.2463, 0.0, _target_mode="Date",
                 _target_date="2068-01-01")
    bodies = _markdowns(at)
    assert any("so directed" in b for b in bodies), "the premise: the lead sentence"
    arms = [b for b in bodies if b.startswith("**PN IV testimony #3, if the Moon")]
    assert len(arms) == 2, arms
    assert all("outside the direction table" in b for b in arms), arms
    for line in arms:
        assert ", by " in line and line.rstrip().endswith("."), line


# --- PW-07, PW-08: the Markdown export's names ----------------------------------------------------------

def test_pw07_the_comment_does_not_say_escaping_at_stops_an_autolink():
    text = _app_text()
    end = text.index("_MARKDOWN_MARKS = re.compile(")
    comment = text[text.rindex("\n\n", 0, end):end]
    assert "What a Markdown reader takes as a mark" in comment, "the premise: the comment over the marks"
    assert 'autolinks ("https:", "@")' not in comment, comment
    assert "stops nothing" in comment, comment


def test_pw08_the_markdown_isolates_a_name_that_can_turn_the_text_around(scratch):
    name = "abc‮def"
    at = _open_record(name, dict(FLORENCE_REC, location_query=name))
    report = at.session_state["_analysis_markdown"]
    assert report.splitlines()[0] == f"# Analysis: ⁨{name}⁩", report.splitlines()[0]
    places = [line for line in report.splitlines() if line.startswith("| Place |")]
    assert places and all(f"⁨{name}⁩" in line for line in places), places


# --- PW-09: a place label with no visible character -----------------------------------------------------

def test_pw09_a_place_label_with_no_visible_character_names_nothing(scratch):
    at = _open_record("Invisible place", dict(FLORENCE_REC, location_query="​"))
    boxes = [m.value for m in at.sidebar.success if "43.7792, 11.2463" in m.value]
    assert boxes, "the premise: the place box is drawn"
    assert boxes[0].startswith("43.7792, 11.2463"), repr(boxes[0])
    strip = _strip(at)
    assert " · 43.78, 11.25" in strip and "​" not in strip, repr(strip)


# --- PW-11: a manual offset of -0.0 -------------------------------------------------------------------

def test_pw11_a_manual_offset_of_minus_zero_prints_no_signed_zero():
    at = _render("chart", time_standard_key=MANUAL, utc_offset_key=-0.0)
    report = at.session_state["_analysis_markdown"]
    assert "| UTC offset (hours, east positive) |" in report, "the premise: the offset rows"
    assert "| -0 |" not in report, [l for l in report.splitlines() if "UTC offset" in l]


# --- PW-12: the Rhetorius relief's gap, printed under its bound -------------------------------------------

def test_pw12_a_gap_under_seven_degrees_does_not_print_as_seven(engine):
    data = {"Moon": {"longitude": 100.0}, "Mars": {"longitude": 106.97}, "Jupiter": {"longitude": 226.97}}
    infortunes = engine["INFORTUNES"]
    body = engine["_rhetorius_loosener"]("Moon", data, ["Moon", "Mars"], infortunes, False)
    trine = engine["_rhetorius_loosener"]("Moon", data, ["Moon", "Jupiter"], {"Jupiter"}, True)
    assert body and trine, "the premise: both rays 6.97 degrees off are read"
    assert "7.0° off" not in body and "7.0° off" not in trine, (body, trine)
    assert "6.97° off" in body and "6.97° off" in trine, (body, trine)


# --- PW-13: the node years against the header's completed age -------------------------------------------

def test_pw13_the_node_years_are_not_called_ages_70_to_75():
    text = _app_text()
    assert "In the 71st to the 75th years of each fardar" in text, "the premise"
    assert "(ages 70 to 75)" not in text
    assert "(from age 70 until 75 is completed)" in text


# --- PW-15: Venus appearing cites 39 with 38 ---------------------------------------------------------

def test_pw15_the_positions_caption_cites_vii2_39_with_38():
    at = _render("chart")
    said = [c for c in _captions(at) if "would put her in the heart or burned" in c]
    assert len(said) == 1, "the premise: the Positions caption"
    assert "(Gr. Intr. VII.2, 39, with 38)" in said[0], said[0]


# --- PW-16: the exports at the pole -------------------------------------------------------------------

def test_pw16_the_exports_at_the_pole_say_the_ascendant_is_not_a_rising_degree():
    at = _manual("lots", "2000-12-21", 12, 0, 90.0, 0.0, 0.0)
    assert any("not a rising degree" in c for c in _texts(at.main)), "the premise: the page says so"
    export = json.dumps(at.session_state["_analysis_export"], ensure_ascii=False)
    for name, text in (("JSON", export), ("Markdown", at.session_state["_analysis_markdown"]),
                       ("HTML", at.session_state["_analysis_html"])):
        assert "an Ascendant cast there is where the ecliptic meets the horizon, not a rising degree" in text, name


# --- PW-19: the wheel's figures name their volume --------------------------------------------------------

def test_pw19_every_figure_the_revolutions_wheel_cites_names_its_volume():
    at = _render("timing")
    notes = [e for e in at.main.status if e.label == "How the wheel is drawn"]
    assert len(notes) == 1, "the premise: the wheel's notes"
    texts = _texts(notes[0]) + [r.help for r in at.main.radio if r.label == "Inner wheel" and r.help]
    found = [(t[max(0, m.start() - 12):m.end()], bool(re.search(r"PN IV $", t[:m.start()])))
             for t in texts for m in re.finditer(r"\bFigures? \d+", t)]
    assert len(found) >= 10, f"the premise: the wheel's figures ({len(found)})"
    bare = [ctx for ctx, named in found if not named]
    assert not bare, bare


# --- PW-20: the precision paragraph names its exceptions --------------------------------------------------

def test_pw20_the_precision_paragraph_names_its_exceptions():
    at = _render("chart")
    precision = at.session_state["_analysis_export"]["precision"]
    assert "Absolute (Planetary Positions)" in precision, "the premise: a named column"
    assert "except in the columns named below" in precision, precision
    assert "a list, an empty cell or an unresolved answer keeps its JSON type" in precision, precision
    assert "a bare number (not a number inside a page's text) to at most four decimal places" in precision


# --- PW-21, PW-28, PW-29: code comments ---------------------------------------------------------------

def test_pw21_the_right_sidedness_comment_counts_mercury_by_his_phase():
    text = _engine_text()
    comment = text[text.index("# Neither enters a score; each table names its source."):
                   text.index("def evaluate_right_sidedness(")]
    assert '"of the sect of the day or ... night"' in comment, "the premise"
    assert "Mercury has none of his own here and is not counted" not in comment, comment
    assert "Mercury by his phase" in comment, comment


def test_pw28_the_day_limit_quotation_closes_where_the_page_closes_it():
    """Gr. Intr. VII.2, 55 (Gr. Intr. p. 419): 'it is called "the
    day-limit" of easternization and direct motion'."""
    doc = function_source("solar_phase")
    assert "day-limit" in doc, "the premise"
    assert '"the day-limit of easternization' not in doc, doc
    assert '"the day-limit" of easternization and direct' in doc


def _module_binding(name):
    """The text of the one engine module whose top level binds `name`,
    wherever the list of source modules puts it (the time zones' module for
    the linked zones), so that a comment above it is read in its own file."""
    import ast
    from conftest import engine_files
    hits = [path for path in engine_files() for node in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(node, ast.Assign) and name in [getattr(t, "id", None) for t in node.targets]]
    assert len(hits) == 1, (name, hits)
    return hits[0].read_text(encoding="utf-8")


def test_pw29_the_linked_zones_comment_names_no_development_path():
    text = _module_binding("LINKED_ZONES_TZDATA")
    end = text.index("LINKED_ZONES_TZDATA = ")
    comment = text[text.rindex("\n\n", 0, end):end]
    assert "derived from that package" in comment, "the premise"
    assert "tools/" not in comment, comment
    assert "a development-only tool" in comment and "a development-only test" in comment, comment


# --- PW-23: the apogee note says the Sun ----------------------------------------------------------------

def test_pw23_the_apogee_note_does_not_count_a_planet_by_distance():
    at = _render("configurations")
    notes = [t for t in _texts(at.main) if "circle of their apogee" in t]
    assert len(set(notes)) == 1, notes
    assert "a planet counting" not in notes[0], notes[0]
    assert "for the Sun alone" in notes[0], notes[0]


# --- PW-25: the domain switch's entry names the wheel's point panel ------------------------------------

def test_pw25_the_domain_entry_names_every_reader_of_the_domain_flags():
    at = _render("sources")
    entry = [t for t in _texts(at.main) if "Affects: the Sect table" in t]
    assert len(set(entry)) == 1, entry
    for reader in ("the Sect table", "Dignity Evaluation", "Topical Planets in Houses", "Planetary Condition",
                   "a planet picked on the Chart page's wheel"):
        assert reader in entry[0], (reader, entry[0])


# --- PW-26: the aspects note on a refusal ----------------------------------------------------------------

def test_pw26_the_aspects_note_promises_a_reason_only_for_a_refused_residue():
    text = _app_text()
    assert "Sahl's 20 admits" in text, "the premise"
    assert "where 20 refuses it, the Strength cell says" not in text
    assert "where 20 refuses what is left of it, the Strength cell says which of its two conditions does" in text


# --- PW-30: no article before a planet's name ------------------------------------------------------------

def test_pw30_the_opening_contact_says_behind_saturn_not_behind_the_saturn(engine):
    data = _florence(engine)["planetary_data"]
    segments = engine["_pn4_distribute"](data, data["Saturn"]["longitude"], lambda lon: lon % 360.0, 360.0,
                                         "Saturn", significator="Saturn")
    opened = str(segments[0].get("partner_from"))
    assert "Venus by square" in opened, f"the premise: {opened!r}"
    assert "behind the Saturn" not in opened and opened.endswith("behind Saturn"), opened
    asc = engine["_pn4_distribute"](data, data["Saturn"]["longitude"], lambda lon: lon % 360.0, 360.0, "Ascendant",
                                    significator="Saturn")
    assert str(asc[0].get("partner_from")).endswith("behind the Ascendant"), asc[0].get("partner_from")


# --- EN-01: the node's fardar letter on the wheel -------------------------------------------------------

@pytest.mark.parametrize("target, node", [("1311-08-01", "North Node"), ("1313-08-01", "South Node")])
def test_en01_the_year_over_root_wheel_badges_the_node_that_holds_the_fardar(monkeypatch, target, node):
    at = make_app(page="timing", timeout=300)
    import engine as module
    svgs = []
    original = module.generate_multiwheel_svg

    def spy(rings, *args, **kwargs):
        svg = original(rings, *args, **kwargs)
        svgs.append((kwargs.get("badges"), svg))
        return svg
    monkeypatch.setattr(module, "generate_multiwheel_svg", spy)
    at.session_state["_target_mode"] = "Date"
    at.session_state["_target_date"] = target
    at.session_state["_timing_wheel_view"] = "Year over root"
    at.run(timeout=300)
    assert_no_exception(at, f"Revolutions, {target}")
    assert svgs, "the premise: the wheel is drawn"
    assert any(badges and "F" in str(badges) for badges, _ in svgs), "the premise: a lord of the fardar is badged"
    badged = {}
    for _, svg in svgs:
        for name, body in re.findall(r'<g class="pt"[^>]*data-point="([^"]+)"[^>]*>(.*?)</g>', svg, re.S):
            badged.setdefault(name, []).extend(re.findall(r'<text class="badge"[^>]*>([^<]*)</text>', body))
    assert node in badged, "the premise: the node is drawn"
    assert "F" in "".join(badged[node]), {k: v for k, v in badged.items() if v}


# --- EN-02 (ruling 75): the III.2 window prints as "At age" does -----------------------------------------

def test_en02_the_iii2_window_line_truncates_its_bounds():
    """The default chart's eleventh year: the revolution falls at 9.9999474
    years elapsed and the next at 10.9999491; truncated as "At age" and the
    header print them (ruling 13), 9.999 to 10.999, where the line printed
    10.000 to 11.000."""
    at = _render("timing", _target_mode="Date", _target_date="1250-08-01")
    lines = [m for m in _markdowns(at) if "this revolution's year," in m and "years elapsed from the birth hour" in m]
    assert len(lines) == 1, "the premise: the III.2 window line"
    assert "9.999 to 10.999 years elapsed" in lines[0], lines[0]


# --- The display rounding (SL's check, finding 8 with finding 4's export cell) -------------------------

def _no_360_or_signed_zero(cell):
    """No printed angle reads 360 or a signed zero: "360", "360.00",
    "-0", "-0.00" as a whole number in the cell."""
    return not re.search(r"(?<![\d.])(?:360(?:\.0+)?|-0(?:\.0+)?)(?![\d.])", str(cell))


@pytest.mark.parametrize("lon", [359.999987004788, 180.005, 359.9999999])
def test_the_semi_arc_rows_print_no_360_and_no_signed_zero(engine, lon):
    chart = _florence(engine)
    rows = engine["pn4_semi_arc_terms_rows"](lon, chart["obliquity"], chart["geo_lat"], chart["armc"], [], None)
    assert rows, "the premise: the significator's row"
    for column in ("Right ascension", "Declination", "Meridian distance", "Semi-arc"):
        assert _no_360_or_signed_zero(rows[0][column]), (lon, column, rows[0][column])


def _with_the_moon_at(monkeypatch, moon, page="chart"):
    at = make_app(page=page, timeout=300)
    import engine as module
    original = module.calculate_traditional_chart_jd

    def patched(*args, **kwargs):
        chart = copy.deepcopy(original(*args, **kwargs))
        chart["planetary_data"]["Moon"]["longitude"] = moon
        return chart
    monkeypatch.setattr(module, "calculate_traditional_chart_jd", patched)
    at.run(timeout=300)
    monkeypatch.setattr(module, "calculate_traditional_chart_jd", original)
    assert_no_exception(at, f"the Moon at {moon!r}")
    return at


def _markdown_positions_moon(report):
    lines = report.splitlines()
    start = lines.index("#### Planetary Positions")
    header = next(l for l in lines[start:] if l.startswith("| Planet"))
    row = next(l for l in lines[start:] if l.startswith("| Moon |"))
    cells = dict(zip([c.strip() for c in header.strip("|").split("|")], [c.strip() for c in row.strip("|").split("|")]))
    return cells


@pytest.mark.parametrize("moon", [359.999987004788, -1e-16])
def test_the_positions_absolute_prints_no_360_and_no_signed_zero(monkeypatch, moon):
    at = _with_the_moon_at(monkeypatch, moon)
    rows = [n.value for h, n in table_nodes(at) if h == "Planetary Positions"]
    assert rows, "the premise: the Positions table"
    page_cell = rows[0].set_index("Planet").loc["Moon", "Absolute"]
    assert _no_360_or_signed_zero(page_cell), page_cell
    md = _markdown_positions_moon(at.session_state["_analysis_markdown"])["Absolute"]
    assert _no_360_or_signed_zero(md), md
    html = at.session_state["_analysis_html"]
    moon_row = re.search(r"<tr><td>Moon</td>.*?</tr>", html[html.index("Planetary Positions"):]).group(0)
    assert _no_360_or_signed_zero(re.sub(r"<[^>]+>", "|", moon_row)), moon_row
    export_rows = at.session_state["_analysis_export"]["results"]["Chart"]["Planetary Positions"][0]["rows"]
    moon_float = next(r["Absolute"] for r in export_rows if r["Planet"] == "Moon")
    assert isinstance(moon_float, float) and moon_float == moon, "the JSON keeps the calculation's float"
