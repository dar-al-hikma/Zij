"""Findings of an outside hostile pass on cb7390d that the pass of 2026-10-03 missed.

An outside reviewer worked from the published source packet alone, with no texts,
and reported 27 rows: 12 duplicate the pass's own findings, one is a policy
question, and 14 were new. Each of the 14 was re-run on this checkout before it
was kept. One strict xfail per finding, asserting the right behaviour, keyed by
the outside id (HP-NN) so the two reports read together. HP-21 and HP-22 (two
tests of the suite that cannot fail) are recorded in the report with no test
here; HP-09 is established for the harness's submitted None only.

Nothing in engine.py or app.py changes here: the fixer is not the verifier.
"""
from __future__ import annotations

import json
import re

import pytest

from conftest import APP_PATH, assert_no_exception, make_app, sync_engine_to_environment

FLORENCE = (43.7792, 11.2463)


def _chart(engine, y, m, d, hour_ut, lat=FLORENCE[0], lon=FLORENCE[1]):
    jd = engine["civil_to_jd"](y, m, d, hour_ut)
    return jd, engine["calculate_traditional_chart_jd"](jd, lat, lon)


def _pdata(**overrides):
    values = {"Sun": (40.0, 1.0), "Moon": (20.0, 13.0), "Mercury": (80.0, 1.3), "Venus": (250.0, 1.2),
              "Mars": (170.0, 0.5), "Jupiter": (220.0, 0.08), "Saturn": (305.0, 0.03), "North Node": (130.0, -0.05)}
    values.update(overrides)
    return {p: {"longitude": x, "latitude": 0.0, "distance": 1.0, "speed_in_lon": v, "speed_in_lat": 0.0, "speed_in_dist": 0.0}
            for p, (x, v) in values.items()}


CUSPS = [(100.0 + 30.0 * i) % 360.0 for i in range(12)]


# --- one motion, two tables ---------------------------------------------------------

def test_hp03_sahl_strength_and_pn4_motion_agree_on_a_stationary_planet(engine):
    """2026-07-27 12:00 UT Florence: Saturn moves -0.0011 a day. The accidental
    row calls him Stationary and not Retrograde, so strength testimony 80 is
    awarded; the PN IV indicator table (I.7) reads the sign of the speed and
    prints 'retrograde'. One fact, two answers on one chart."""
    jd, c = _chart(engine, 2026, 7, 27, 12.0)
    p = c["planetary_data"]
    assert -0.01 < p["Saturn"]["speed_in_lon"] < 0, "the probe chart has moved; pick another station"
    ess = engine["evaluate_essential_dignities"](p, c["sect"])
    acc = engine["evaluate_accidental_dignities"](p, c["houses"], c["sect"], jd,
                                                  armc=c["armc"], obliquity=c["obliquity"], geo_lat=c["geo_lat"])
    strength = next(r for r in engine["evaluate_strength_of_planets"](p, ess, acc, c["ascendant"], c["sect"], c["houses"])
                    if r["Planet"] == "Saturn")
    direct_awarded = any(t["n"] == "80" for t in strength["Testimonies"])
    pn4 = next(r for r in engine["pn4_i7_planets"](c, c) if r["Planet"] == "Saturn" and r["Chart"] == "root")
    assert not (direct_awarded and pn4["Motion (7)"] == "retrograde"), (acc["Saturn"], pn4["Motion (7)"])


# --- the house-master and the Moon's orientality -------------------------------------

def test_hp04_house_master_does_not_rest_on_an_orientality_the_years_call_unresolved(engine):
    """1900-04-27 08:00 UT Florence: the Sun is the releaser with no lord looking,
    and the Moon is made house-master by 1.20, 6 as 'eastern, with a share in the
    Ascendant'; sahl_house_master_years for the same Moon returns facts['eastern']
    unresolved. A verdict cannot rest on a fact the engine itself leaves open."""
    jd, c = _chart(engine, 1900, 4, 27, 8.0)
    p = c["planetary_data"]
    syz = engine["sahl_prenatal_meeting_and_fullness"](jd, *FLORENCE)
    rel = engine["sahl_releaser"](p, c["ascendant"], c["houses"], c["sect"], c["lot_of_fortune"],
                                  syz["meeting"]["longitude"], syz["fullness"]["longitude"])
    years = engine["sahl_house_master_years"]("Moon", p, c["houses"], c["sect"],
                                              engine["evaluate_essential_dignities"](p, c["sect"]))
    assert engine["is_unresolved"](years["facts"]["eastern"]), "the probe's premise: the Moon's orientality is open in the years"
    by_1_20_6 = rel["ranking"] and "1.20, 6" in rel["ranking"][0]["Rank"]
    assert not (rel["house_master"] == "Moon" and by_1_20_6), rel["verdict"]


# Lane F6b (the owner's ruling R4 of 2026-10-04, reading (A)): 1.22 defines
# easternness for the superiors (1-6) and the inferiors (7-8), never the Moon,
# so 1.20, 6 cannot elect her on it. The election takes the evidence the years
# take and comes back open, with both arms, typed through to the page.

def _hp04_chart(engine):
    jd, c = _chart(engine, 1900, 4, 27, 8.0)
    syz = engine["sahl_prenatal_meeting_and_fullness"](jd, *FLORENCE)
    rel = engine["sahl_releaser"](c["planetary_data"], c["ascendant"], c["houses"], c["sect"], c["lot_of_fortune"],
                                  syz["meeting"]["longitude"], syz["fullness"]["longitude"])
    return c, rel


def test_hp04_an_election_turning_on_the_moons_easternness_is_open_with_both_arms(engine):
    """The 1900 chart: the Sun in the places with no lord looking, the Moon the
    exaltation lord with a share in the Ascendant. Both arms are carried --
    the releaser and the house-master as well, since under Nawbakht's 1.15, 7
    the Sun does not stand without her -- and no arm is a single name."""
    c, rel = _hp04_chart(engine)
    unresolved = engine["is_unresolved"]
    for key in ("releaser", "longitude", "house_master", "verdict"):
        assert unresolved(rel[key]), (key, rel[key])
    arms = dict(rel["house_master"].alternatives)
    assert set(arms) == {"if the Moon is eastern", "if the Moon is not eastern"}
    assert arms["if the Moon is eastern"] == "Moon"
    assert arms["if the Moon is not eastern"] == "Mars", arms
    assert dict(rel["releaser"].alternatives)["if the Moon is not eastern"] == "the meeting (the last New Moon)"
    assert "1.22" in rel["house_master"].reason and "superiors" in rel["house_master"].reason
    # the one verdict row per arm, and the reason stated where the rule is stated
    sun_row = next(r for r in rel["candidates"] if r["Candidate"] == "the Sun")
    assert unresolved(sun_row["Verdict"])
    assert "1.20, 6" in dict(sun_row["Verdict"].alternatives)["if the Moon is eastern"]
    assert {r["If"] for r in rel["ranking"]} == set(arms)
    # the years take the arm's orientality: the Moon graded eastern on the eastern arm
    years = engine["sahl_house_master_years"](rel["house_master"], c["planetary_data"], c["houses"], c["sect"],
                                              engine["evaluate_essential_dignities"](c["planetary_data"], c["sect"]))
    assert unresolved(years["text"])
    texts = dict(years["text"].alternatives)
    assert "(Moon)" in texts["if the Moon is eastern"] and "(Mars)" in texts["if the Moon is not eastern"], texts


def test_hp04_the_moon_is_never_elected_by_1_20_6_on_a_settled_eastern(engine):
    """No chart elects the Moon by 1.20, 6 on a settled "eastern": a superior-style
    settlement cannot exist for her (1.22 gives her none), so the examination of a
    candidate she would rescue is open unless an arm is supplied -- and with the
    arm supplied, the row says which arm it is."""
    unresolved = engine["is_unresolved"]
    c, _rel = _hp04_chart(engine)
    p = c["planetary_data"]
    examine = engine["_sahl_examine_candidate"]
    open_ = examine("the Sun", p["Sun"]["longitude"], p, c["houses"], c["sect"], engine["SAHL_RELEASER_DAY_PLACES"], "Sun")
    assert unresolved(open_["fit"]) and open_["sharer_1_20_6"] == ("exaltation", "Moon") and open_["moon_consulted"]
    assert open_["fit"].reason == "the supplied passages do not define the Moon's orientality"   # the years' evidence
    with pytest.raises(TypeError):
        bool(open_["fit"])
    east = examine("the Sun", p["Sun"]["longitude"], p, c["houses"], c["sect"], engine["SAHL_RELEASER_DAY_PLACES"], "Sun",
                   moon_eastern=True)
    west = examine("the Sun", p["Sun"]["longitude"], p, c["houses"], c["sect"], engine["SAHL_RELEASER_DAY_PLACES"], "Sun",
                   moon_eastern=False)
    assert east["fit"] is True and "taken as eastern on this arm" in east["why"]
    assert west["fit"] is False and "taken as not eastern on this arm" in west["why"] and "1.15, 7" in west["why"]
    # the engine's own notion of her side of the Sun plays no part: she is "eastern" by it here
    assert engine["solar_phase"]("Moon", p["Moon"]["longitude"], p["Sun"]["longitude"], p["Moon"]["speed_in_lon"])[1] == "eastern"


def test_hp04_the_page_and_the_exports_carry_the_open_election_typed():
    """The Releaser page for the 1900 chart (08:45 local, the harness's Florence
    time for 08:00 UT): the verdict is the unresolved form with both arms, the
    releaser is not distributed, no one house-master is directed, and the
    Markdown and JSON exports carry the same typed result -- never one name."""
    import datetime as dt
    at = make_app(date="1900-04-27", page="releaser")
    at.session_state["time_input_key"] = dt.time(8, 45)
    at.run()
    assert_no_exception(at, "releaser")
    page = "\n".join(m.value for m in at.main.markdown)
    verdict = next(m for m in page.splitlines() if m.startswith("**Unresolved"))
    assert "if the Moon is eastern: The releaser is the Sun" in verdict and "if the Moon is not eastern: The releaser is the meeting" in verdict
    assert "1.22 defines it for the superiors (1-6) and the inferiors (7-8)" in verdict
    assert "The releaser distributed" not in page and "The releaser is not distributed" in page
    assert "No one house-master to direct" in page
    assert "under each arm of the Moon's easternness" in page
    assert "**The releaser is the Sun" not in page, "a single name reached the page"
    md = at.session_state["_analysis_markdown"]
    assert "if the Moon is not eastern" in md
    assert "house-master by 1.20, 6: eastern" not in md, "the old single-name Rank reached the Markdown export"
    export = at.session_state["_analysis_export"]["results"]["Prediction"]
    tables = next(v for k, v in export.items() if "house-master (Sahl" in k)
    sun_row = next(r for r in tables[0]["rows"] if r["Candidate"] == "the Sun")
    assert sun_row["Verdict"]["result_type"] == "UnresolvedResult"
    assert [a["name"] for a in sun_row["Verdict"]["alternatives"]] == ["if the Moon is eastern", "if the Moon is not eastern"]
    assert {r["If"] for r in tables[1]["rows"]} == {"if the Moon is eastern", "if the Moon is not eastern"}


def test_hp04_an_election_that_never_needed_the_moons_easternness_is_settled(engine):
    """A chart whose releaser is seen by its lords: one name, as before, and
    the Moon's orientality not consulted."""
    pd = _pdata(Sun=(40.0, 1.0), Moon=(200.0, 13.0), Mars=(40.0, 0.5))
    rel = engine["sahl_releaser"](pd, 100.0, CUSPS, "Diurnal", 250.0, 20.0, 200.0)
    assert not engine["is_unresolved"](rel["releaser"]) and rel["moon_consulted"] is False
    assert isinstance(rel["house_master"], str) and "If" not in rel["ranking"][0]


def test_hp04_an_empty_arm_is_named_not_printed_as_none():
    """The blind check of F6b, finding 5: 1923-02-08 09:06 UT at 43.7792, 151.2, a
    night chart whose eastern arm keeps the Lot of Fortune and whose not-eastern
    arm has no releaser (1.15, 16). The not-distributed line, the house-master
    line and the division printed that arm as a raw "None"; each names it in the
    engine's own words for the empty arm (the arm's verdict says "No releaser by
    Nawbakht's rule", the years line "no house-master")."""
    import datetime as dt
    at = make_app(date="1923-02-08", page="releaser")
    at.session_state["manual_lat_key"], at.session_state["manual_lon_key"] = 43.7792, 151.2
    at.session_state["time_input_key"] = dt.time(9, 6)
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = 0.0
    at.run()
    assert_no_exception(at, "releaser")
    page = "\n".join(str(m.value) for m in at.main.markdown)
    assert "if the Moon is not eastern: None" not in page
    lines = page.splitlines()
    verdict = next(line for line in lines if line.startswith("**Unresolved"))
    assert "if the Moon is not eastern: No releaser by Nawbakht's rule" in verdict, verdict
    not_distributed = next(line for line in lines if line.startswith("**The releaser is not distributed**"))
    assert "if the Moon is not eastern: no releaser by Nawbakht's rule)" in not_distributed, not_distributed
    no_one = next(line for line in lines if line.startswith("No one house-master to direct"))
    assert "if the Moon is not eastern: no house-master)" in no_one, no_one
    division = next(line for line in lines if line.startswith("Placed by division"))
    assert "if the Moon is not eastern: no house-master)" in division, division


def test_hp04_a_row_the_chain_never_reached_takes_no_arm(engine):
    """The blind check of F6b, finding 6: 1900-02-13 19:17:14 UT Florence, a night
    chart whose Moon is the releaser, seen by the Sun and Jupiter. The election
    never needs the Moon's easternness, but the fullness, a row after the chosen
    one, was examined on the eastern arm and read "taken as eastern on this arm,
    house-master by 1.20, 6" on a page with no arms. A row the chain never
    reached takes no arm: it is examined with her easternness open, in the
    engine's words for that. The second chart, 1928-11-09 08:09:22 UT at
    43.7792, -74.0, is the same shape; there the reading before the ruling (her
    side of the Sun) printed "Moon, its exaltation lord, is eastern" on that row.

    The re-check of the second build, R6: on both charts the fullness stands on
    either answer -- the Moon by 1.20, 6 if she is eastern, a later eastern lord
    with a share in the Ascendant if she is not (Mars, its triplicity lord, in
    1900; Mercury, its face lord, in 1928) -- so the row names both house-masters
    and says only the house-master is open, never that its standing is.

    Ruling 43 (owner, 2026-10-06), following ruling 16 (1.20, 6's "eastern" for
    the five planets is 1.22's): on 1900-02-13 Mars is 6.5 degrees earlier in the
    zodiac than the Sun, eastern by his side but not by 1.22, 3's 18, so no
    eastern lord follows the Moon at that fullness and its row takes the
    contrast's shape: its standing is open. 1928-11-09 keeps R6's shape."""
    examine = engine["_sahl_examine_candidate"]
    for ymd, hour, place, later in (((1928, 11, 9), 8 + 9 / 60 + 22 / 3600, (43.7792, -74.0), ("face", "Mercury")),):
        jd, c = _chart(engine, *ymd, hour, *place)
        syz = engine["sahl_prenatal_meeting_and_fullness"](jd, *place)
        rel = engine["sahl_releaser"](c["planetary_data"], c["ascendant"], c["houses"], c["sect"], c["lot_of_fortune"],
                                      syz["meeting"]["longitude"], syz["fullness"]["longitude"])
        assert rel["releaser"] == "the Moon" and rel["moon_consulted"] is False, (ymd, rel["verdict"])
        fullness = next(r for r in rel["candidates"] if r["Candidate"] == "the fullness (the last Full Moon)")["Verdict"]
        assert isinstance(fullness, str), (ymd, fullness)
        assert fullness.startswith("not consulted, an earlier candidate qualified -- "), (ymd, fullness)
        assert "on this arm" not in fullness, (ymd, fullness)
        assert "the texts do not define the Moon's easternness" in fullness, (ymd, fullness)
        assert "standing is open" not in fullness, (ymd, fullness)
        assert fullness.endswith(f"only its house-master is open: Moon if she is eastern, {later[1]} if she is not "
                                 "(\"even if it was in the second from it, not looking at it\"; \"a share\" read as any "
                                 "of the five dignities at the Ascendant's degree)"), (ymd, fullness)
        assert f"{later[1]}, its {later[0]} lord, is eastern with a share in the Ascendant" in fullness, (ymd, fullness)
        # the open examination agrees with the two arms it summarises
        p = c["planetary_data"]
        lon = syz["fullness"]["longitude"]
        arms = [examine("the fullness (the last Full Moon)", lon, p, c["houses"], c["sect"],
                        engine["SAHL_RELEASER_NIGHT_PLACES"], moon_eastern=east) for east in (True, False, None)]
        assert [a["fit"] for a in arms] == [True, True, True], (ymd, [a["fit"] for a in arms])
        assert arms[0]["sharer_1_20_6"][1] == "Moon" and arms[1]["sharer_1_20_6"] == later, (ymd, arms[1]["sharer_1_20_6"])
        assert arms[2]["sharer_1_20_6"][1] == "Moon" and arms[2]["sharer_1_20_6_if_not_eastern"] == later
        # the election itself is untouched
        assert rel["house_master"] == {(1900, 2, 13): "Jupiter", (1928, 11, 9): "Mercury"}[ymd], (ymd, rel["verdict"])
    # 1900-02-13 19:17:14 UT Florence under ruling 43: the election is untouched (the Moon, Jupiter); the
    # fullness's standing is open, as in the contrast below, and the row names Mars as not eastern by 1.22, 3.
    jd, c = _chart(engine, 1900, 2, 13, 19 + 17 / 60 + 14 / 3600, *FLORENCE)
    syz = engine["sahl_prenatal_meeting_and_fullness"](jd, *FLORENCE)
    rel = engine["sahl_releaser"](c["planetary_data"], c["ascendant"], c["houses"], c["sect"], c["lot_of_fortune"],
                                  syz["meeting"]["longitude"], syz["fullness"]["longitude"])
    assert rel["releaser"] == "the Moon" and rel["moon_consulted"] is False and rel["house_master"] == "Jupiter", (
        rel["verdict"])
    fullness = next(r for r in rel["candidates"] if r["Candidate"] == "the fullness (the last Full Moon)")["Verdict"]
    assert fullness.startswith("not consulted, an earlier candidate qualified -- "), fullness
    assert "on this arm" not in fullness, fullness
    assert "the texts do not define the Moon's easternness" in fullness, fullness
    assert fullness.endswith(": this candidate's standing is open, with both arms"), fullness
    assert ("Mars, its triplicity lord, holds a share in the Ascendant but is not eastern (1.22, 3: direct, 6.5° earlier "
            "in the zodiac than the Sun; it asks 18° or more earlier, not retrograde (1.22, 5))") in fullness, fullness
    # the three arms' fits as they come out: the eastern arm stands, the not-eastern arm falls, the open
    # examination carries the years' evidence (an UnresolvedResult)
    arms = [examine("the fullness (the last Full Moon)", syz["fullness"]["longitude"], c["planetary_data"], c["houses"],
                    c["sect"], engine["SAHL_RELEASER_NIGHT_PLACES"], moon_eastern=east) for east in (True, False, None)]
    assert arms[0]["fit"] is True and arms[1]["fit"] is False, ([a["fit"] for a in arms[:2]], arms[1]["why"])
    assert engine["is_unresolved"](arms[2]["fit"]), arms[2]["fit"]
    # The contrast: 1906-11-04 00:01:25.6 UT at 48.2823, -45.7405 is settled too, but no eastern lord
    # follows the Moon at its fullness, so that row's standing does turn on her and says so.
    place = (48.28226213732471, -45.74045880466758)
    jd, c = _chart(engine, 1906, 11, 4, 0.0237650637517417, *place)
    syz = engine["sahl_prenatal_meeting_and_fullness"](jd, *place)
    rel = engine["sahl_releaser"](c["planetary_data"], c["ascendant"], c["houses"], c["sect"], c["lot_of_fortune"],
                                  syz["meeting"]["longitude"], syz["fullness"]["longitude"])
    assert rel["moon_consulted"] is False and not engine["is_unresolved"](rel["releaser"]), rel["verdict"]
    fullness = next(r for r in rel["candidates"] if r["Candidate"] == "the fullness (the last Full Moon)")["Verdict"]
    assert fullness.endswith(": this candidate's standing is open, with both arms"), fullness
    west = examine("the fullness (the last Full Moon)", syz["fullness"]["longitude"], c["planetary_data"], c["houses"],
                   c["sect"], engine["SAHL_RELEASER_NIGHT_PLACES"], moon_eastern=False)
    assert west["fit"] is False, west["why"]
    import datetime as dt
    at = make_app(date="1900-02-13", page="releaser")
    at.session_state["time_input_key"] = dt.time(19, 17, 14)
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = 0.0
    at.run()
    assert_no_exception(at, "releaser")
    cands = next(d.value for d in at.main.dataframe if "Candidate" in d.value.columns)
    shown = cands[cands["Candidate"] == "the fullness (the last Full Moon)"].iloc[0]["Verdict"]
    assert "taken as eastern on this arm" not in str(shown), shown
    assert "taken as eastern on this arm" not in at.session_state["_analysis_markdown"]



def test_hp04_an_unreached_row_that_stands_on_both_arms_is_not_called_open():
    """The re-check of the second build, R6, its reproduction: the fullness on
    1928-11-09 08:09:22 UT at 43.7792, -74.0 stands on both arms of the Moon's
    easternness (the Moon if she is eastern, Mercury if she is not), so its row
    does not call its standing open and names Mercury. (Ruling 43, 2026-10-06:
    the reproduction as first written used 1900-02-13 19:17:14 UT Florence,
    whose Mars is not eastern by 1.22, 3 under ruling 16.)"""
    import datetime as dt
    at = make_app(date="1928-11-09", page="releaser")
    at.session_state["manual_lat_key"], at.session_state["manual_lon_key"] = 43.7792, -74.0
    at.session_state["time_input_key"] = dt.time(8, 9, 22)
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = 0.0
    at.run()
    assert_no_exception(at, "releaser")
    cands = next(d.value for d in at.main.dataframe if "Candidate" in d.value.columns)
    fullness = str(cands[cands["Candidate"] == "the fullness (the last Full Moon)"].iloc[0]["Verdict"])
    # Eastern: the Moon (exaltation lord) keeps the fullness by 1.20, 6; not eastern: Mercury (face
    # lord, eastern, a share in the Ascendant) does. It stands on both arms; only its house-master is open.
    assert "standing is open" not in fullness, fullness
    assert "Mercury" in fullness, fullness
    md = at.session_state["_analysis_markdown"]
    assert "standing is open" not in md and "Moon if she is eastern, Mercury if she is not" in md


def test_hp04_a_forking_page_keeps_each_arms_reading_on_its_unreached_rows(engine):
    """The re-check's note on forking pages: 1931-02-18 2.3137 h UT at 14.3174,
    118.1934 (day) forks -- the Sun if the Moon is eastern, the Ascendant if not.
    On the eastern arm the meeting is a row the chain never reached; it keeps that
    arm's reading ("taken as eastern on this arm") beside its sibling's "taken as
    not eastern on this arm", and no cell of the forked rows reads the open
    examination: the open re-examination is for a settled page only."""
    place = (14.3174, 118.1934)
    jd, c = _chart(engine, 1931, 2, 18, 2.3137, *place)
    syz = engine["sahl_prenatal_meeting_and_fullness"](jd, *place)
    rel = engine["sahl_releaser"](c["planetary_data"], c["ascendant"], c["houses"], c["sect"], c["lot_of_fortune"],
                                  syz["meeting"]["longitude"], syz["fullness"]["longitude"])
    unresolved = engine["is_unresolved"]
    assert unresolved(rel["releaser"]), rel["releaser"]
    assert dict(rel["releaser"].alternatives) == {"if the Moon is eastern": "the Sun",
                                                  "if the Moon is not eastern": "the Ascendant"}
    meeting = next(r for r in rel["candidates"] if r["Candidate"] == "the meeting (the last New Moon)")["Verdict"]
    assert unresolved(meeting), meeting
    cells = dict(meeting.alternatives)
    assert cells["if the Moon is eastern"].startswith("not consulted, an earlier candidate qualified -- "), cells
    assert "taken as eastern on this arm, house-master by 1.20, 6" in cells["if the Moon is eastern"], cells
    assert "taken as not eastern on this arm" in cells["if the Moon is not eastern"], cells
    texts = [(row["Candidate"], text) for row in rel["candidates"]
             for _arm, text in (row["Verdict"].alternatives if unresolved(row["Verdict"]) else ((None, row["Verdict"]),))]
    assert len(texts) == 6, texts   # the Sun, the meeting and the Ascendant, each under both arms
    opened = [(who, text) for who, text in texts if "standing is open" in text or "only its house-master is open" in text]
    assert opened == [], opened


# --- ties after the opening ------------------------------------------------------------

def test_hp05_a_later_tie_of_contacts_is_unresolved_like_an_opening_tie(engine):
    # The owner's rulings 14 and 19 (2026-10-05, PN IV III.1, 50): two met at
    # once are partners together, at the opening as later; the two tie
    # assertions follow them.
    pd = {"Mars": {"longitude": 10.0}, "Venus": {"longitude": 10.0}}
    opening = engine["pn4_distribution_at_age"](engine["_pn4_distribute"](pd, 10.0, lambda x: x, 30.0, "test point"), 0.0)
    assert not engine["is_unresolved"](opening["partner"]) and tuple(opening["partner"]) == ("Mars", "Venus"), \
        "the probe's premise: the opening pair is read together"
    later = engine["pn4_distribution_at_age"](engine["_pn4_distribute"](pd, 0.0, lambda x: x, 30.0, "test point"), 10.0)
    assert not engine["is_unresolved"](later["partner"]) and tuple(later["partner"]) == ("Mars", "Venus"), later["partner"]


# --- the governor's quoted OR, and Mercury's exact conjunction ------------------------

def test_hp13_an_unread_arm_of_an_or_rule_does_not_yield_no(engine):
    root = {"planetary_data": _pdata(Jupiter=(185.0, 0.08)), "ascendant": 100.0, "sect": "Diurnal", "houses": CUSPS}
    rows = engine["pn4_governor_condition"]("Jupiter", root, root)
    row12 = next(r for r in rows if r["Test"].startswith("IX.9, 12"))
    assert "not read" in row12["Criteria"], "the probe's premise: the engine says it did not read the nature arm"
    assert row12["Met"] != "no", row12


def test_hp18_governor_condition_does_not_decide_a_side_the_phase_evaluator_leaves_open(engine):
    root = {"planetary_data": _pdata(Sun=(40.0, 1.0), Mercury=(40.0, 1.3)), "ascendant": 100.0, "sect": "Diurnal", "houses": CUSPS}
    assert engine["is_unresolved"](engine["mercury_phase_sect"](40.0, 40.0)), "the probe's premise"
    row11 = next(r for r in engine["pn4_governor_condition"]("Mercury", root, root) if r["Test"].startswith("IX.9, 11"))
    decided = re.findall(r"of the Sun (?:not )?met \((eastern|western)\)", row11["Criteria"])
    assert not decided, row11["Criteria"]


# --- a fardar boundary in a later cycle ------------------------------------------------

def test_hp17_fardar_sub_periods_are_half_open_in_every_cycle(engine):
    age = 80.71428571428571
    r = engine["pn4_fardar_at_age"](age, "Diurnal")
    assert r["sub_from"] <= age < r["sub_to"], r


# --- the circle's seam -------------------------------------------------------------------

def test_hp23_a_longitude_that_normalises_to_360_is_the_first_degree_of_aries(engine):
    assert engine["get_zodiac_sign"](-1e-16) == "Aries"
    assert engine["get_essential_rulers"](-1e-16) == engine["get_essential_rulers"](0.0)


# --- the store and the shell -------------------------------------------------------------

NULL_TIME = {"date_string": "1983-11-19", "time_string": None, "time_standard": "LMT (Local Mean Time)",
             "lat": 43.7792, "lon": 11.2463, "location_query": "Florence"}


def test_hp10_the_validator_refuses_a_null_time(engine):
    assert engine["chart_record_fault"](dict(NULL_TIME)) is not None


def _launch_over(tmp_path, monkeypatch, files):
    """A fresh launch, preferences live, over a store this test writes."""
    data = tmp_path / "Zij"
    data.mkdir(parents=True)
    for name, content in files.items():
        (data / name).write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("ALMUTEN_NO_PREFERENCES", raising=False)
    sync_engine_to_environment()
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(str(APP_PATH), default_timeout=300).run()


def test_hp10_a_null_time_record_as_last_chart_keeps_the_shell(tmp_path, monkeypatch):
    at = _launch_over(tmp_path, monkeypatch, {"saved_charts.json": json.dumps({"Null time": NULL_TIME}),
                                              "preferences.json": json.dumps({"last_chart": "Null time"})})
    assert_no_exception(at, "launch on a null-time record")


def test_hp12_undecodable_preferences_are_ignored_not_fatal(tmp_path, monkeypatch):
    at = _launch_over(tmp_path, monkeypatch, {"preferences.json": b"\xff\xfeinvalid"})
    assert_no_exception(at, "launch on undecodable preferences")


def test_hp09_a_blank_manual_offset_is_refused_not_clamped_to_minus_fourteen():
    at = make_app(date="1983-11-19", page="chart")
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = -5.0
    at.run()
    at.sidebar.number_input(key="utc_offset_key").set_value(None).run()
    assert_no_exception(at, "blank offset")
    sentence = "The UTC offset box is blank."
    assert any(sentence in n.value for n in at.sidebar.error), [n.value for n in at.sidebar.error]
    text = "\n".join([n.value for n in at.sidebar.info] + [n.value for n in at.sidebar.error])
    assert "UTC-14:00" not in text and "UTC+00:00" not in text, text
    assert at.session_state["utc_offset_key"] is None
    at.run()                                            # the run after: the refusal stands, nothing is cast
    assert_no_exception(at, "blank offset, next run")
    assert at.sidebar.number_input(key="utc_offset_key").value is None
    assert any(sentence in n.value for n in at.sidebar.error), [n.value for n in at.sidebar.error]
    assert at.session_state["utc_offset_key"] is None
    assert "UTC+00:00" not in "\n".join(n.value for n in at.sidebar.info)


def test_hp09_a_blank_offset_from_the_start_casts_no_chart_and_writes_no_export():
    at = make_app(date="1983-11-19", page="chart")
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = None
    at.run()
    assert_no_exception(at, "blank offset seed")
    assert any("The UTC offset box is blank." in n.value for n in at.sidebar.error)
    assert "_analysis_export" not in at.session_state       # chart_ok False: the export is not built
    at.run()
    assert any("The UTC offset box is blank." in n.value for n in at.sidebar.error)
    assert "_analysis_export" not in at.session_state


# --- the exports -----------------------------------------------------------------------------

def test_hp16_the_exports_carry_the_true_sun_qualification_the_page_states():
    at = make_app(page="timing")
    at.run()
    assert_no_exception(at, "timing")
    page = "\n".join(m.value for m in at.main.markdown)
    assert "true-Sun return" in page, "the probe's premise: the page qualifies the return"
    md = at.session_state["_analysis_markdown"]
    assert "true-Sun" in md or "true Sun" in md or "mean Sun" in md


def test_hp27_exports_carry_no_internal_testimony_ids():
    at = make_app(page="dignities")
    at.run()
    assert_no_exception(at, "dignities")
    export = at.session_state["_analysis_export"]["results"]
    rows = export["Dignities and places"]["Topical Planets in Houses"][0]["rows"]
    assert rows, "the probe's premise: the export carries the table's rows"
    leaking = [row for row in rows if "Joint testimony IDs" in row]
    assert not leaking, sorted(leaking[0])
