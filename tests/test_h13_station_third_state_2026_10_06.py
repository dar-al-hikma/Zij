"""H13: a station is a third state (ruling 40).

Abu Ma'shar lists a planet's states as three: "direct motion, stationing,
and retrogradation" (Gr. Intr. III.1, 9, p. 151). Book VII.2 gives the
station a condition of its own wherever it falls: for the inferiors in the
east, "they do not cease to be in their condition until they station. 42
And when they station, they are in the fifth condition. 43 And when they go
direct in the east, they are in the sixth condition, until they speed up
and come near to the Sun" (VII.2, 41-43, Gr. Intr. p. 418); in the west,
"50 And when they station, they come to be in the thirteenth condition"
(p. 419). So VII.2, 44's printed 6 belongs to an inferior that has gone
direct, not to one at its station.

VII.5, 10 (Gr. Intr. p. 445): "the connection by assembly, it is that two
planets are direct in motion, in a single sign". Read by the same Book,
"direct" is the first of the three states and does not take in a station.

Neither case is reached by a real chart 1900-2100 (the nearest inferior
station lies 14.5 degrees from the Sun; no Type I blocking with a planet at
its station was found), so every chart here is constructed.
"""
from __future__ import annotations

import pytest

from conftest import function_source

SUN = 100.0
STATION_SPEEDS = (0.002, -0.002, 0.0)


# --- solar_phase: a stationary inferior is not in VII.2, 43-44's "direct" profile --------------

# (longitude, side): 6.5 E is where 44's printed 6 and 40's 7 disagree; 12.0 E and 7.0 W are the
# two endpoints whose ownership the "direct inferior" profile reverses.
PROFILE_SPLIT = ((93.5, "eastern"), (88.0, "eastern"), (107.0, "western"))


@pytest.mark.parametrize("source", ["Abu Ma'shar", "Sahl"])
@pytest.mark.parametrize("planet", ["Mercury", "Venus"])
@pytest.mark.parametrize("lon, side", PROFILE_SPLIT)
def test_a_stationary_inferior_takes_one_phase_whatever_the_sign_of_its_speed(engine, planet, lon, side, source):
    phases = {v: engine["solar_phase"](planet, lon, SUN, v, source=source) for v in STATION_SPEEDS}
    for v in STATION_SPEEDS:
        assert engine["motion_state"](planet, v) == "stationary"
        assert phases[v][1] == side
    assert len({p[0] for p in phases.values()}) == 1, phases


@pytest.mark.parametrize("planet", ["Mercury", "Venus"])
@pytest.mark.parametrize("speed", STATION_SPEEDS)
def test_the_phase_note_names_the_station_not_a_direction(engine, planet, speed):
    note = engine["solar_phase_note"](planet, "eastern", speed, 6.5)
    assert "44 as printed" not in note, note
    assert "retrograde" not in note, note
    assert "station" in note, note


@pytest.mark.parametrize("planet", ["Mercury", "Venus"])
def test_a_moving_inferior_keeps_its_direction_profile(engine, planet):
    """The guard beside the change: just outside the station tolerance the
    inferior has gone direct (VII.2, 43-44's printed 6) or retrograde
    (37/40's 7), as before."""
    direct, retro = 0.0031, -0.0031
    assert engine["motion_state"](planet, direct) == "direct"
    assert engine["motion_state"](planet, retro) == "retrograde"
    assert engine["solar_phase"](planet, 93.5, SUN, direct)[0] == "Under the rays"
    assert engine["solar_phase"](planet, 93.5, SUN, retro)[0] == "Burned"
    assert engine["solar_phase"](planet, 88.0, SUN, direct)[0] == "Under the rays"
    assert engine["solar_phase"](planet, 107.0, SUN, retro)[0] == "Burned"
    assert "44 as printed" in engine["solar_phase_note"](planet, "eastern", direct, 6.5)
    assert "retrograde" in engine["solar_phase_note"](planet, "eastern", retro, 6.5)


# --- evaluate_blocking: "direct" read as a state ------------------------------------------------

def _pdata(**overrides):
    values = {"Sun": (SUN, 0.9856), "Moon": (245.0, 13.0), "Mercury": (80.0, 1.3), "Venus": (200.0, 1.2),
              "Mars": (248.0, 1.0), "Jupiter": (160.0, 0.08), "Saturn": (256.0, -0.02),
              "North Node": (130.0, -0.05)}
    values.update(overrides)
    return {p: {"longitude": x, "latitude": 0.0, "distance": 1.0, "speed_in_lon": v, "speed_in_lat": 0.0,
                "speed_in_dist": 0.0} for p, (x, v) in values.items()}


def _type_one(engine, data, profile):
    run = engine["_RUN"]
    had = hasattr(run, "CONNECTION_PROFILE")
    previous = getattr(run, "CONNECTION_PROFILE", None)
    try:
        engine["set_readings"](CONNECTION_PROFILE=profile)
        return [(r["Blocked"], r["Blocked By"], r["From Reaching"]) for r in engine["evaluate_blocking"](data)
                if r["Type"].startswith("I ")]
    finally:
        if had:
            engine["set_readings"](CONNECTION_PROFILE=previous)
        else:
            delattr(run, "CONNECTION_PROFILE")


PROFILES = ("Sahl", "Abu Ma'shar")
# Moon 5, Mars 8, Saturn 16 Sagittarius: Mars stands between the Moon and the heavy one.
MARS_BLOCKER = dict(Mars=(248.0, None))
# Mars 10, Venus 12, Saturn 16 Sagittarius, the Moon and the Sun out of the sign.
MARS_BLOCKED = dict(Mars=(250.0, None), Venus=(252.0, 1.2), Moon=(20.0, 13.0), Sun=(270.0, 0.9856))


def _with_mars(case, speed):
    return _pdata(**{k: (x, speed if k == "Mars" else v) for k, (x, v) in case.items()})


@pytest.mark.parametrize("profile", PROFILES)
def test_a_stationary_blocker_does_not_intervene(engine, profile):
    data = _with_mars(MARS_BLOCKER, 0.002)
    assert engine["motion_state"]("Mars", 0.002) == "stationary"
    assert ("Moon", "Mars", "Saturn") not in _type_one(engine, data, profile)


@pytest.mark.parametrize("profile", PROFILES)
def test_a_stationary_planet_is_not_blocked_by_assembly(engine, profile):
    data = _with_mars(MARS_BLOCKED, 0.002)
    assert ("Mars", "Venus", "Saturn") not in _type_one(engine, data, profile)


@pytest.mark.parametrize("profile", PROFILES)
def test_a_direct_planet_still_blocks_and_is_blocked(engine, profile):
    """The guard beside the change: just past the tolerance Mars is direct,
    and both trios stand."""
    assert ("Moon", "Mars", "Saturn") in _type_one(engine, _with_mars(MARS_BLOCKER, 0.0031), profile)
    assert ("Mars", "Venus", "Saturn") in _type_one(engine, _with_mars(MARS_BLOCKED, 0.0031), profile)


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("speed", (-0.002, 0.0, -0.0031))
def test_a_planet_not_moving_forward_is_never_the_applicant_to_a_heavier_one_ahead(engine, profile, speed):
    """Why the `speed <= 0` filter is redundant: a lighter planet below a
    heavier one in its sign that is not itself moving forward is not the
    applicant of their row, so `applying()` refuses it already."""
    data = _with_mars(MARS_BLOCKER, speed)
    rows = engine["_pairwise_configurations"](data)
    row = next(r for r in rows if {r["p1"], r["p2"]} == {"Mars", "Saturn"})
    assert (row["applicant"] or row["light_name"]) != "Mars", row
    assert ("Moon", "Mars", "Saturn") not in _type_one(engine, data, profile)


def test_blocking_reads_direct_through_motion_state():
    body = function_source("evaluate_blocking")
    assert "motion_state(" in body
    assert "speed[blocked] <= 0" not in body


# --- the stationary row's words (after the blind check, its notes 4b and 8) ---------------------

STATIONARY_SUFFIX = (
    " -- stationary (Gr. Intr. VII.2, 42: \"when they station, they are in the fifth condition\"): "
    "the text gives that condition no band; this app's reading uses 37/40's 7 degrees, "
    "not 44's printed 6, which follows 43's \"when they go direct\""
)


@pytest.mark.parametrize("planet", ["Mercury", "Venus"])
@pytest.mark.parametrize("speed", STATION_SPEEDS)
def test_the_stationary_note_says_its_limits_are_this_apps_reading(engine, planet, speed):
    """VII.2 gives the fifth condition no band (Gr. Intr. p. 418), and 55's
    day-limit "of easternization and direct motion" (Gr. Intr. p. 419)
    offers a second candidate in the east; so the 7 the row uses is named
    as this app's reading, not the text's."""
    assert engine["solar_phase_note"](planet, "eastern", speed, 6.5) == STATIONARY_SUFFIX


def test_the_accidental_row_carries_the_stationary_note(engine):
    cusps = [(SUN + 30.0 * i) % 360.0 for i in range(12)]
    row = engine["evaluate_accidental_dignities"](_pdata(Mercury=(93.5, 0.002)), cusps, "Diurnal", None)["Mercury"]
    assert "Burned, eastern (6.5 deg) (-5)" + STATIONARY_SUFFIX in row["Accidental Labels"], row["Accidental Labels"]


def test_the_engine_names_the_station_locators_by_their_volume():
    """PN IV has a Book VII too: the station's sentences are written with
    Gr. Intr. in the note's docstring and in blocking's Type I comment."""
    assert "Gr. Intr. VII.2, 42" in function_source("solar_phase_note")
    assert "Gr. Intr. VII.2, 42 and 50" in function_source("evaluate_blocking")
