"""The wording lane after the repair (2026-10-08): wording and locators only.

Ruling 133 accepted triage r1007's F16 (the Lot's 2.16, 2 line) and sent the
two blind checkers' wording notes to this lane; the re-pass's wave-5 list
named five more ("Citation ranges and wording"), and the page-text read of
2026-10-08 the exports' "Sahl N". Each test below asserts what a page, an
export or the code says now, and failed on the base for that item's reason.
No computed value moves: where a sentence describes what the app does, the
test also holds the premise it describes.
"""
from __future__ import annotations

import json
import re
from datetime import time
from pathlib import Path

import pytest

from conftest import assert_no_exception, make_app
from test_two_partners_together_2026_10_05 import _c2_bundle

DEPTHS = ("Course text", "Course text and supplement")
# Two charts: the harness's own (Florence, 1240-05-23 14:30 LMT) and another.
CHARTS = ("1240-05-23", "1983-11-19")
_RENDERED = {}


def _texts(node, out=None):
    """Every string a reader can see under ``node``: values, labels, help."""
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
        for attr in ("help", "body", "label", "caption"):
            v = getattr(proto, attr, None)
            if isinstance(v, str) and v:
                out.append(v)
    for child in (getattr(node, "children", None) or {}).values():
        _texts(child, out)
    return out


def _page(page, date, depth, **state):
    key = (page, date, depth, tuple(sorted(state.items())))
    if key not in _RENDERED:
        at = make_app(date=date, page=page, timeout=300)
        at.session_state["_reading_depth"] = depth
        for k, v in state.items():
            at.session_state[k] = v
        at.run(timeout=300)
        assert_no_exception(at, f"{page} {date} {depth}")
        _RENDERED[key] = at
    return _RENDERED[key]


def _page_text(page, date, depth, **state):
    return "\n".join(_texts(_page(page, date, depth, **state).main))


# Both charts at both depths.
EVERYWHERE = pytest.mark.parametrize("date,depth", [(date, depth) for date in CHARTS for depth in DEPTHS])


# --- A1. F16, ruling 133: 2.16, 2's "and it is eastern" ----------------------------------------------------------

F16_NEW = ("On Nativities 2.16, 2's \"and it is eastern\" can be read of the fortune or of the lord of the Lot; the "
           "sentence does not say which, so this app reads it both ways and shows each, with the one outcome, \"in "
           "the middle\".")
F16_OLD = "shows fortune-eastern and lord-eastern readings separately and preserves their conditional outcomes"


@EVERYWHERE
def test_f16_the_lot_note_says_the_sentence_leaves_open_which_is_eastern(date, depth, engine):
    text = _page_text("findings", date, depth)
    assert F16_NEW in text, (date, depth)
    assert F16_OLD not in text, (date, depth)
    # The premise the sentence states: the app reads it both ways, and the one outcome is "in the middle".
    natal = engine["calculate_traditional_chart_jd"](2451545.0, 43.7792, 11.2463)
    a16 = engine["_prosperity_lot_assessments"](natal["planetary_data"], natal["ascendant"],
                                                natal["lot_of_fortune"])["2.16, 2"]
    assert [name for name, _ in a16.readings] == ["fortune eastern", "lord eastern"]
    assert "will be in the middle" in engine["PROSPERITY_SAHL"]["2.16, 2"]


# --- A2. The labels on F6, F7, F8 (The releaser) and F10 (Findings) --------------------------------------------------

@EVERYWHERE
def test_also_2_the_releaser_notes_label_the_apps_reading(date, depth):
    text = _page_text("releaser", date, depth)
    # F6 and F7: whose "eastern" is read how, and where Dykes's 15 degrees is
    assert ("The same word is read otherwise where other sentences use it: in 1.20, 7-34 (the house-master's "
            "years) it is read by the side of the Sun, and in 1.7, 3's preference with Dykes's 15° for Mars (fn "
            "174 on 1.22, 3).") in text, (date, depth)
    assert "1.20, 7-34's years by the side of the Sun" not in text
    # F8: the turning is the text's, the direction Dykes's reading
    assert ("On Nativities 1.23, 13-14's turning from the house-master to the lord of the Ascendant when the "
            "house-master is unsuitable, directed as the house-master was (Dykes's reading, fnn 191 and 194), is "
            "**applied** below") in text, (date, depth)
    assert "redirection to the lord of the Ascendant" not in text


@EVERYWHERE
def test_also_2_the_third_day_moon_summary_labels_the_apps_profile(date, depth):
    text = _page_text("findings", date, depth)
    # F10: the possessive takes the looks alone; the profile is the app's, read from 1.29, 3
    assert ("her sign and place, On Nativities 1.26, 7's intersign looks; the corruption profile this app reads "
            "from 1.29, 3 (co-presence, enclosure, burning, falling); and the limited third-day component of "
            "1.29, 11-12.") in text, (date, depth)
    assert "1.26, 7's intersign looks, co-presence" not in text


# --- A3. 1.20, 6's bearing on the releaser, labelled a reading ----------------------------------------------------

OPEN_CHART = dict(time_input_key=time(8, 0), time_standard_key="Manual UTC offset", utc_offset_key=0.0,
                  _target_mode="Date", _target_date="1960-06-01")   # Florence, 1900-04-27: the election is open


@pytest.mark.parametrize("page", ["timing", "releaser"])
@pytest.mark.parametrize("depth", DEPTHS)
def test_also_3_the_open_releasers_sentences_call_1_20_6_a_reading(page, depth):
    at = _page(page, "1900-04-27", depth, **OPEN_CHART)
    text = "\n".join(_texts(at.main))
    assert ("The releaser is unresolved: its election turns on the Moon's easternness (On Nativities 1.20, 6, as "
            "this app reads it), which the texts do not define (On Nativities 1.22, 1-8)") in text
    assert "easternness (On Nativities 1.20, 6), which" not in text
    reason = ("the releaser's election is open on the Moon's easternness (Sahl, On Nativities 1.20, 6, as this app "
              "reads it; 1.22, 1-8), testimony #3 is read on each arm, and the arms differ here")
    assert reason in json.dumps(at.session_state["_analysis_export"], ensure_ascii=False)
    for export in ("_analysis_markdown", "_analysis_html"):
        assert "Sahl, On Nativities 1.20, 6, as this app reads it; 1.22, 1-8" in at.session_state[export], export
        assert "Sahl, On Nativities 1.20, 6; 1.22, 1-8), testimony" not in at.session_state[export], export


def test_also_3_the_governors_summary_on_both_arms_calls_1_20_6_a_reading(engine):
    rows = [{"#": 1, "Planet": "Jupiter"}]
    arms = (("if the Moon is eastern", (rows, {"text": "Jupiter is primary with 3", "primary": ["Jupiter"]})),
            ("if the Moon is not eastern", (rows, {"text": "Jupiter is primary with 2", "primary": ["Jupiter"]})))
    _rows, summary = engine["pn4_governor_on_each_arm"](arms)
    assert summary["text"].startswith(
        "Jupiter is primary on both arms of the releaser's election, which is open on the Moon's easternness (Sahl, "
        "On Nativities 1.20, 6, as this app reads it; 1.22, 1-8); testimony #3 is read on each arm"), summary["text"]


# --- A4. 2.13, 39 and fn 181 ---------------------------------------------------------------------------------------

@EVERYWHERE
def test_also_4_the_first_lords_time_gives_fn_181s_doubt_and_the_apps_step(date, depth):
    text = _page_text("findings", date, depth)
    assert ("the first lord's time being the beginning of life. That rests on On Nativities 2.13, 39, which says "
            "it of the parents' lords (\"the first lord of the triplicity indicates the end of the father's life, "
            "and the beginning of the native's life\"); Dykes calls the sentence \"rather unclear\" and thinks the "
            "second lord should indicate the beginning (fn 181), and applying the parents' lords to the native's "
            "own is this app's step.") in text, (date, depth)
    assert "the first lord's time being the beginning of life (2.13, 39). The infortunes" not in text


# --- A5. The condition at the end of seven sections, and 5.1, 91 -------------------------------------------------------

@EVERYWHERE
def test_also_5_the_count_and_the_list_agree_and_5_1_91_is_said_apart(date, depth, engine):
    text = _page_text("dignities", date, depth)
    assert "stated at the end of seven of the twelve lord-of-the-Nth sections" in text, (date, depth)
    assert "eight of the twelve" not in text
    assert ("(On Nativities 3.10, 14; likewise 4.11, 24; 6.3.4, 24; 7.1, 217; 9.4, 35; 10.2.4, 13; 12.1, 47)"
            in text)
    assert ("On Nativities 5.1, 91 has nearly the same words after the fifth's list, \"if the lord of the fifth "
            "and the fifth are both free of the infortunes, and the fortunes do not witness the Lot of children in "
            "the houses of the circle, then look at the Lot of children\", but there they lead to the Lot of "
            "children, not to the list; Dykes is not sure whether the sentence is Masha'allah's or Sahl's (fn 49) "
            "and reads its \"witness\" tentatively (fn 50). It is not counted here.") in text, (date, depth)
    # The premise: the seven listed are the houses whose condition the column assesses with the eleventh's,
    # and the fifth is the engine's unstated one, turning to the Lot of children.
    assert sorted(engine["MASHAALLAH_CONDITION_SOURCES"]) == [3, 4, 6, 7, 9, 10, 11, 12]
    assert "5.1, 91 conditionally turns to the Lot of children" in engine["MASHAALLAH_UNSTATED"][5]


# --- A6. "not an emendation", both depths (the default depth is test_readability_b's) --------------------------------

@EVERYWHERE
def test_also_6_the_lot_of_death_says_sahls_printed_sentence_is_emended(date, depth):
    text = _page_text("lots", date, depth)
    assert ("A stated rule with a manuscript variant: the rule is not an emendation, but Sahl's printed sentence "
            "is one, Dykes reading Saturn with Masha'allah's manuscripts for the \"Ascendant\" of Sahl's (fn 89).") \
        in text, (date, depth)
    assert "A stated rule with a manuscript variant, not an emendation." not in text


# --- A7. #4 credits each partner: the app's reading --------------------------------------------------------------------

def test_part_b_also_2_the_partner_tally_says_crediting_each_is_this_apps_reading(engine):
    _rows, summary = _c2_bundle(engine)["governor"]
    assert summary["tally"] == {"Venus": 2, "Jupiter": 3, "Mars": 2, "Saturn": 2}, "the premise: #4 credits each"
    assert ("The partner testimony, #4, counts for each of Mars and Saturn, partners together (this app's reading of "
            "PN IV III.1, 50 and IX.9, 5: each partner is credited), so the counts by planet add up to more than the "
            "testimonies counted.") in summary["text"], summary["text"]
    doc = " ".join(engine["_pn4_governor_alternatives"].__doc__.split())
    assert ("IX.9, 5's \"the partner to them both\" is read as crediting each (this app's reading of III.1, 50 and "
            "IX.9, 5; the owner's ruling 33)") in doc
    assert "\"the partner to them both\" credits each" not in doc


# --- A9. IX.9, 12's testimony is read as a dignity -------------------------------------------------------------------

@EVERYWHERE
def test_part_b_also_4_ix_9_12s_testimony_is_read_as_a_dignity(date, depth):
    text = _page_text("timing", date, depth)
    assert "PN IV IX.9, 12's testimony is read as a dignity of the planet's own at its degree" in text, \
        (date, depth)
    assert "12's testimony is a dignity" not in text


# --- A10. Three states of motion among other changes ------------------------------------------------------------------

def test_part_b_also_5_iii_1_9_names_three_states_of_motion_among_other_changes(engine):
    doc = " ".join(engine["_inferior_gone_direct"].__doc__.split())
    assert ("among the planets' changes \"from condition to condition\" Gr. Intr. III.1, 9 names three states of "
            "motion, \"direct motion, stationing, and retrogradation\" (Gr. Intr. p. 151)") in doc
    assert "the states are three" not in doc


# --- B11. The Great Introduction's table rests on V.14, 6-9 -----------------------------------------------------------

@pytest.mark.parametrize("depth", DEPTHS)
def test_b11_the_great_introductions_triplicity_table_cites_v14_6_9(depth):
    at = _page("victors", "1240-09-01", depth)          # a Virgo prenatal lunation
    exports = (json.dumps(at.session_state["_analysis_export"], ensure_ascii=False),
               at.session_state["_analysis_markdown"], at.session_state["_analysis_html"])
    page = "\n".join(_texts(at.main)) + "\n" + "\n".join(d.value.to_string() for d in at.main.dataframe)
    places = (page,) + exports
    assert len(places) == 4
    assert all(places), "the premise: the page and its three exports"
    for where in places:
        assert "V.14, 7, Figure 53" not in where
    if depth == DEPTHS[1]:          # the supplement shows the Great Introduction's table
        for where in places:
            assert "Gr. Intr. V.14, 6-9, Figure 53, fn 100" in where


# --- B12. Fardar's prose restatement names its work -------------------------------------------------------------------

@EVERYWHERE
def test_b12_fardars_prose_restatement_names_the_great_introduction(date, depth):
    text = _page_text("fardar", date, depth)
    assert ("**Figure 146 (Gr. Intr. VII.8, p. 487)**, verified against the prose restatement at Gr. Intr. "
            "VII.8, 3-8 and the fardar total") in text, (date, depth)
    assert "the prose restatement at VII.8, 3-8" not in text


# --- C16. "Sahl N" in the exports names its work ----------------------------------------------------------------------

@pytest.mark.parametrize("rule", ["Sahl", "Abu Ma'shar"])
def test_c16_the_aspects_table_carries_its_pages_caption_into_the_export(rule):
    at = _page("configurations", "1982-11-19", DEPTHS[0], _connection_rule=rule)
    caption = f"Sahl, The Introduction Ch. 2, 50-60 and Ch. 3, 6-21 — {rule} rule in force"
    assert caption in [c.value for c in at.main.caption], "the premise: the page's caption"
    entries = at.session_state["_analysis_export"]["results"]["Configurations"]["Aspects, aversions and connections"]
    assert [e.get("citation") for e in entries] == [caption]
    for export in ("_analysis_markdown", "_analysis_html"):
        assert "Sahl, The Introduction Ch. 2, 50-60 and Ch. 3, 6-21" in at.session_state[export], export
        assert "Connection test in force" not in at.session_state[export], export


# Petoskey, 1982-11-19 05:18 in the named zone: its revolution has a body connection in the checklist
PETOSKEY = dict(time_input_key=time(5, 18), manual_lat_key=45.3733, manual_lon_key=-84.9553,
                _target_mode="Date", _target_date="2026-10-03")


def test_c16_the_checklists_body_connection_names_the_introduction(engine):
    standard = engine["TIME_STANDARD_OPTIONS"][1]
    at = _page("timing", "1982-11-19", DEPTHS[0], **dict(PETOSKEY, time_standard_key=standard))
    cells = "\n".join(d.value.to_string() for d in at.main.dataframe)
    exports = (json.dumps(at.session_state["_analysis_export"], ensure_ascii=False),
               at.session_state["_analysis_markdown"], at.session_state["_analysis_html"])
    places = (cells,) + exports
    assert len(places) == 4
    assert all(places), "the premise: the page's tables and its three exports"
    for where in places:
        assert "body connection (Sahl, The Introduction Ch. 3, 20–21)" in where
        assert "(Sahl 20–21)" not in where


# --- Fix round 1. B14 and ruling 135: the store's copy is told, naming no file ------------------------------------
#
# Ruling 100's form, "a copy of it was kept beside the saved charts", for each notice that told the copy of an
# unreadable store or preferences file by its file name. Each case below is the one that shows that notice; in each,
# nothing the sidebar says names a file in the data folder, the copy's name, or its date-stamp.


COPY_KEPT = "a copy of it was kept beside the saved charts"
STORE_UNREADABLE_AT_LOAD = "Saved charts could not be read. A copy of the file was kept beside the saved charts."
PREFS_UNREADABLE = "Preferences could not be read. A copy of the file was kept beside the saved charts."
REFUSED_OVER_UNREADABLE = ("The saved charts file could not be written to disk. It could not be read either, and was "
                           "left as it is; " + COPY_KEPT + ".")
KEPT_AND_WRITTEN = ("Saved charts could not be read: the file had been changed since this window read it. A copy of "
                    "the file was kept beside the saved charts, and this window's saved charts were written in its "
                    "place.")


def _folder(tmp_path):
    return Path(tmp_path) / "Zij"


def _sidebar_said(at):
    return [e.value for e in (*at.sidebar.error, *at.sidebar.warning)]


def _names_no_file(said, folder):
    """Nothing said names a file in the data folder, a copy, or a copy's stamp."""
    names = {p.name for p in folder.iterdir()} | {"saved_charts.json", "preferences.json"}
    bad = [t for t in said if any(n in t for n in names) or ".json" in t or "unreadable-" in t
           or re.search(r"\d{8}-\d{6}", t)]
    assert bad == [], bad


def _save(at, name):
    [t for t in at.sidebar.text_input if t.label.startswith("Chart name")][0].set_value(name).run()
    [b for b in at.sidebar.button if "Save" in b.label][0].click().run()


def test_ruling_135_an_unreadable_store_at_the_load_is_told_naming_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    _folder(tmp_path).mkdir()
    (_folder(tmp_path) / "saved_charts.json").write_text("{not json")
    at = make_app(date="1983-11-19", page="chart").run()
    assert_no_exception(at, "an unreadable store at the load")
    assert len(list(_folder(tmp_path).glob("saved_charts.json.unreadable-*"))) == 1, "premise: the copy was kept"
    said = _sidebar_said(at)
    assert said.count(STORE_UNREADABLE_AT_LOAD) == 1, said
    _names_no_file(said, _folder(tmp_path))


def test_ruling_135_an_unreadable_preferences_file_is_told_naming_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    _folder(tmp_path).mkdir()
    (_folder(tmp_path) / "preferences.json").write_text("{not json")
    at = make_app(date="1983-11-19", page="chart").run()
    assert_no_exception(at, "an unreadable preferences file at the load")
    assert len(list(_folder(tmp_path).glob("preferences.json.unreadable-*"))) == 1, "premise: the copy was kept"
    said = _sidebar_said(at)
    assert said.count(PREFS_UNREADABLE) == 1, said
    _names_no_file(said, _folder(tmp_path))


def test_b14_a_refused_save_over_an_unreadable_store_names_no_file(tmp_path, monkeypatch):
    """WL_CHECK's reproduction: the store unreadable after the first run, the write refused."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date="1983-11-19", page="chart").run()
    _folder(tmp_path).mkdir(exist_ok=True)
    (_folder(tmp_path) / "saved_charts.json").write_text("{not json")
    import engine as engine_module
    monkeypatch.setattr(engine_module, "write_saved_charts", lambda charts: False)
    _save(at, "Never written")
    assert_no_exception(at, "a refused save over an unreadable store")
    assert len(list(_folder(tmp_path).glob("saved_charts.json.unreadable-*"))) == 1, "premise: the copy was kept"
    said = _sidebar_said(at)
    assert said.count(REFUSED_OVER_UNREADABLE) == 1, said
    _names_no_file(said, _folder(tmp_path))


def test_ruling_135_a_save_over_a_store_broken_since_the_read_is_told_naming_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    at = make_app(date="1983-11-19", page="chart").run()
    _save(at, "First")
    store = _folder(tmp_path) / "saved_charts.json"
    store.write_text(store.read_text().rstrip().rstrip("}") + ",}")
    _save(at, "Second")
    assert_no_exception(at, "a save over a store broken since the read")
    assert len(list(_folder(tmp_path).glob("saved_charts.json.unreadable-*"))) == 1, "premise: the copy was kept"
    assert set(json.loads(store.read_text())) == {"First", "Second"}, "premise: the save was written"
    said = _sidebar_said(at)
    assert said.count(KEPT_AND_WRITTEN) == 1, said
    _names_no_file(said, _folder(tmp_path))


# --- Fix round 1. The prosperity synthesis row's 2.13, 39 clause, as A4's note ------------------------------------

SYNTHESIS_2_13_39 = ("the first lord's time being the beginning of life (2.13, 39 says it of the parents' lords, and "
                     "Dykes calls the sentence \"rather unclear\", thinking the second lord should indicate the "
                     "beginning, fn 181; applying the parents' lords to the native's own is this app's step)")


@pytest.mark.parametrize("date,depth", [(date, depth) for date in ("1982-11-19", "1240-04-01") for depth in DEPTHS])
def test_fix_the_synthesis_rows_first_lords_time_gives_fn_181s_doubt_and_the_apps_step(date, depth):
    """Two charts whose two lords read class 2 or 5, so the row's Ground carries the timing clause."""
    at = _page("findings", date, depth)
    grounds = [g for d in at.main.dataframe if "Ground" in d.value.columns for g in d.value["Ground"]]
    timed = [g for g in grounds if "the first lord's time being the beginning of life" in g]
    assert timed, f"premise: the synthesis row carries the timing clause ({date}, {depth})"
    for g in timed:
        assert SYNTHESIS_2_13_39 in g, g
        assert "beginning of life (2.13, 39)" not in g


# --- Fix round 1. VIRGO_PARTNER_NOTE in the house form, at the sentence its claim rests on ------------------------

VIRGO_NOTE_CITATION = "Abū Maʿshar's Great Introduction favors Mercury (Gr. Intr. V.14, 7, with Figure 53 and fn 100)."


@pytest.mark.parametrize("depth", DEPTHS)
def test_fix_the_virgo_partner_note_cites_gr_intr_v14_7_in_the_house_form(depth):
    from engine import VIRGO_PARTNER_NOTE
    assert VIRGO_PARTNER_NOTE.endswith(VIRGO_NOTE_CITATION)
    at = _page("victors", "1240-09-01", depth)          # a Virgo prenatal lunation (B11's chart)
    exports = (json.dumps(at.session_state["_analysis_export"], ensure_ascii=False),
               at.session_state["_analysis_markdown"], at.session_state["_analysis_html"])
    page = "\n".join(_texts(at.main)) + "\n" + "\n".join(d.value.to_string(max_colwidth=None) for d in at.main.dataframe)
    places = (page,) + exports
    assert len(places) == 4
    assert all(places), "the premise: the page and its three exports"
    for where in places:
        assert "V.14.7" not in where
        assert VIRGO_NOTE_CITATION in where.replace("&#x27;", "'")


# --- Fix round 1. Figure 71 names its volume: Sahl I's, "Three versions of Masha'allah's Lot of enemies" ---------

FIGURE_71_SOURCES = ("Sahl, On Nativities Ch. 12.1, 48 (Sahl I Figure 71)",
                     "Sahl, On Nativities Ch. 12.1, 49 (Sahl I Figure 71)",
                     "Vat. Pal. lat. 1892, f. 103r (Sahl I Figure 71)")


@EVERYWHERE
def test_fix_the_lot_of_enemies_sources_name_sahl_is_figure_71(date, depth):
    at = _page("lots", date, depth)
    exports = (json.dumps(at.session_state["_analysis_export"], ensure_ascii=False),
               at.session_state["_analysis_markdown"], at.session_state["_analysis_html"])
    frames = [*(d.value for d in at.main.dataframe), *(t.value for t in at.main.table)]
    sources = [s for f in frames if "Source" in f.columns for s in f["Source"]]
    assert sources, "the premise: the provenance table's Source column"
    assert len(exports) == 3
    for source in FIGURE_71_SOURCES:
        assert sources.count(source) == 1, (source, date, depth)
        for where in exports:
            assert where.count(source) == 1, (source, date, depth)
    for where in (*map(str, sources), *exports):
        assert "Fig. 71" not in where


# --- Fix round 1. The Planetary years table's ladder column names On Nativities at its 1.20 ----------------------

JN_COLUMN_HEAD = ("Where On Nativities 1.20 is silent or conditional: Abu 'Ali, Judgments of Nativities Ch. 3 "
                  "(with 'Umar, TBN I.4.3); the supplement")


@EVERYWHERE
def test_fix_the_planetary_years_ladder_column_names_on_nativities(date, depth):
    """The column stands at the supplement depth only, on Fardar and ages and in the export."""
    at = _page("fardar", date, depth)
    columns = [c for d in at.main.dataframe for c in d.value.columns]
    assert "On Nativities 1.20 grants (as house-master)" in columns, "the premise: the Planetary years table"
    entry, = [e for e in at.session_state["_analysis_export"]["results"]["Prediction"]["Planetary years"]]
    heads = {c for row in entry["rows"] for c in row}
    exports = (at.session_state["_analysis_markdown"], at.session_state["_analysis_html"].replace("&#x27;", "'"))
    assert len(exports) == 2
    shown = depth == DEPTHS[1]
    assert (JN_COLUMN_HEAD in columns, JN_COLUMN_HEAD in heads) == (shown, shown)
    assert all((JN_COLUMN_HEAD in e) == shown for e in exports)
    assert not [c for c in (*columns, *heads) if c.startswith("Where 1.20")]
