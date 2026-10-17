"""Seven pure lookups, pinned against an independently written implementation.

On 2026-09-09 a second implementation of sign, bound lord, face lord,
triplicity lord, dignity scoring, almuten and whole-sign house was written from
a specification by a model that never saw this code, and run over 4,348 inputs.
It agreed with the engine on every one. The fixture here keeps all 348 boundary
probes from that run plus 400 sampled random cases.

The boundary probes are the point. They sit on every Egyptian bound edge
exactly and at +/- 1e-9, on every sign and face edge, and across all 144
ascendant/target sign pairs -- the places a `<` that should be `<=` hides, and
that random longitudes essentially never reach.
"""
import json
import os

import pytest

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "differential_oracle.json")
PLANETS = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"]


def _cases():
    with open(FIXTURE) as fh:
        return json.load(fh)["cases"]


def _production_almuten(engine, lon, sect, asc):
    """The almuten of `lon` as calculate_prenatal_syzygy picks it, the pick
    being inline there: the production function's own code is run with its two
    sky questions answered by the case -- the root search finds the Sun and the
    Moon both at `lon` (so the lunation's degree is `lon`, new or full Moon
    alike), and the Sun is up exactly when the case is Diurnal. The rulers, the
    triplicity lord by sect, the 5/4/3/2/1 points and the tie are all the
    engine's. A tie comes back typed (UnresolvedResult), which the fixture's
    independent side writes as None; here it is the (lord, points) pairs the
    tie names as a sorted list, not a set, so a lord named twice fails,
    compared with _expected_almuten's."""
    import types
    production = engine["calculate_prenatal_syzygy"]
    production = getattr(production, "__wrapped__", production)    # under st.cache_data, the function itself
    namespace = dict(engine)
    namespace["_sun_moon_signed_offset"] = lambda jd, target: (lon, lon, 0.0, 12.19075)
    namespace["_sun_is_up"] = lambda jd, lat, geo_lon: sect == "Diurnal"
    run = types.FunctionType(production.__code__, namespace, production.__name__,
                             production.__defaults__, production.__closure__)
    syzygy = run(2451545.0, 0.0, 0.0, [asc])
    # Premise: the two answers took (a renamed helper would leave the real sky in).
    assert syzygy["syzygy_longitude"] == lon and syzygy["sect_diurnal"] is (sect == "Diurnal"), syzygy
    almuten = syzygy["almuten"]
    if isinstance(almuten, engine["UnresolvedResult"]):
        return sorted(almuten.alternatives)                     # a tie names every tied lord, once each
    return almuten


def _expected_almuten(case):
    """The fixture's almuten, with a tie spelled out. The second implementation
    wrote a tie as None; which lords tie, and at how many points, is in its own
    dignity_scores for the same case, so the expected tie is read from there
    and never from the engine."""
    expect = case["expect"]
    if expect["almuten"] is not None:
        return expect["almuten"]
    top = max(expect["dignity_scores"].values())
    tied = sorted((p, s) for p, s in expect["dignity_scores"].items() if s == top)
    assert len(tied) > 1, f"id={case['id']}: the fixture's None is not a tie of its own scores"
    return tied


def _actual(engine, case):
    """Recompute one case from the live engine, in the fixture's shape. The
    almuten is the production pick (calculate_prenatal_syzygy's, above), not
    arithmetic over the scores here; the fixture stays the expected side."""
    lon, sect, asc = case["longitude"], case["sect"], case["ascendant"]
    rulers = engine["get_essential_rulers"](lon)
    triplicity = rulers["triplicity_day"] if sect == "Diurnal" else rulers["triplicity_night"]
    # The scores come from the production scorer, evaluate_essential_dignities,
    # with all seven planets placed at the longitude. Its 'Essential Score' also
    # carries the debilities and peregrine penalty; the fixture's oracle counts
    # the positive dignities only, so the penalties its own flags name are added
    # back. Nothing here recomputes a lord or a weight in test code.
    placed = {p: {"longitude": float(lon)} for p in PLANETS}
    graded = engine["evaluate_essential_dignities"](placed, sect)
    scores = {}
    for p in PLANETS:
        row = graded[p]
        scores[p] = (row["Essential Score"] + 5 * row["Detriment"] + 4 * row["Fall"]
                     + 5 * row["Peregrine"])
    return {
        "sign": rulers["sign"],
        "bound_lord": rulers["term"],
        "face_lord": rulers["face"],
        "triplicity_lord": triplicity,
        "dignity_scores": scores,
        "almuten": _production_almuten(engine, lon, sect, asc),
        "whole_sign_house": engine["get_wsh_house"](lon, asc),
    }


@pytest.mark.parametrize("field", ["sign", "bound_lord", "face_lord", "triplicity_lord",
                                   "dignity_scores", "almuten", "whole_sign_house"])
def test_differential_oracle_field(engine, field):
    """Every fixture case still agrees with the independent implementation."""
    bad = []
    for case in _cases():
        got = _actual(engine, case)[field]
        expected = _expected_almuten(case) if field == "almuten" else case["expect"][field]
        if got != expected:
            bad.append((case["id"], case["longitude"], case["sect"], case["why"],
                        expected, got))
    assert not bad, "\n".join(
        f"id={i} lon={lon} sect={sect} [{why}]: expected {exp!r}, got {act!r}"
        for i, lon, sect, why, exp, act in bad[:10])


def test_the_boundary_probes_are_still_in_the_fixture():
    """Guards the fixture itself: a regeneration that dropped the boundary
    cases would leave a suite that passes on random longitudes alone."""
    why = [c["why"] for c in _cases()]
    assert sum(1 for w in why if w == "bound edge exact") == 48
    assert sum(1 for w in why if w == "bound edge minus 1e-9") == 48
    assert sum(1 for w in why if w == "bound edge plus 1e-9") == 48
    assert sum(1 for w in why if w == "wsh grid") == 144
    assert sum(1 for w in why if w != "random") == 348
