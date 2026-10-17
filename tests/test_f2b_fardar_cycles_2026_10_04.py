"""Hostile pass of 2026-10-03, fix lane F2b: the follow-up to F2 for the
outside pass's HP-17.

HP-17  In the second cycle a fardar sub-period's reported end could equal
       the age asked for: the age was reduced modulo 75 and the remainder
       compared with bare offsets, while the boundaries reported were the
       cycle's base plus those offsets -- two roundings of one number, and
       the expired sub-lord was returned at its own end. The first-cycle
       fix (Astra F12) compared the same numbers it reported and so never
       saw it. `pn4_fardar_at_age` now builds and compares every boundary
       in the unit of the age asked for (the running total of years from
       the birth hour, IV.1, 11 and 18, 22, 25; restarted when "75 years
       are completed", IV.7, 25), and the seventh sub-period ends exactly
       where its period ends.

The sweep below walks every period and sub-period boundary the function
reports in cycles 1-3, for both sects, and asks at each boundary and a hair
below it that the half-open rule holds everywhere.
"""
from __future__ import annotations

import math

import pytest

CYCLE = 75.0


def _boundaries(engine, sect, cycle):
    """Every boundary (period starts, sub-period starts, the cycle's end) of one
    cycle, as the function itself reports them, walked from the cycle's base."""
    at = engine["pn4_fardar_at_age"]
    base = (cycle - 1) * CYCLE
    age, out = base, []
    while age < base + CYCLE:
        r = at(age, sect)
        assert r["cycle"] == cycle, (age, r)
        out.append(age)
        nxt = r["sub_to"] if r["sub_lord"] is not None else r["to"]
        assert nxt > age, (age, r)
        age = nxt
    return out


@pytest.mark.parametrize("sect", ["Diurnal", "Nocturnal"])
@pytest.mark.parametrize("cycle", [1, 2, 3])
def test_hp17_every_fardar_boundary_is_half_open_in_cycles_one_to_three(engine, sect, cycle):
    at = engine["pn4_fardar_at_age"]
    bounds = _boundaries(engine, sect, cycle)
    # Nine periods; seven planets with seven sub-periods each, the two Nodes with none: 51 starts in a cycle.
    assert len(bounds) == 7 * 7 + 2, bounds
    for b in bounds:
        r = at(b, sect)
        assert r["from"] <= b < r["to"], (b, r)
        lo, hi = (r["sub_from"], r["sub_to"]) if r["sub_lord"] is not None else (r["from"], r["to"])
        assert lo == b < hi, (b, r)                      # the boundary belongs to what begins there
        just_under = math.nextafter(b, -math.inf)
        if just_under >= (cycle - 1) * CYCLE:
            r0 = at(just_under, sect)
            lo0, hi0 = (r0["sub_from"], r0["sub_to"]) if r0["sub_lord"] is not None else (r0["from"], r0["to"])
            assert lo0 <= just_under < hi0 == b, (b, r0)   # a hair below, the expiring one, ending exactly at b
            assert (r0["lord"], r0["sub_lord"]) != (r["lord"], r["sub_lord"]), (b, r0, r)
    # The cycle's last boundary is where the next cycle begins, with the light of the sect (IV.7, 25).
    nxt = at(cycle * CYCLE, sect)
    assert (nxt["lord"], nxt["cycle"]) == ("Sun" if sect == "Diurnal" else "Moon", cycle + 1)


@pytest.mark.parametrize("sect", ["Diurnal", "Nocturnal"])
def test_hp17_the_seventh_subperiod_ends_where_its_period_ends(engine, sect):
    at = engine["pn4_fardar_at_age"]
    for cycle in (1, 2, 3):
        bounds = _boundaries(engine, sect, cycle)
        assert len(bounds) == 7 * 7 + 2, bounds
        periods = [at(b, sect) for b in bounds if at(b, sect)["from"] == b and at(b, sect)["sub_lord"] is not None]
        assert len(periods) == 7, periods                              # the seven planetary periods of the cycle
        for r in periods:
            last = at(math.nextafter(r["to"], -math.inf), sect)
            seventh = engine["pn4_fardar_subperiods"](r["lord"], r["years"])[6][0]   # IV.1, 6: the last down the spheres
            assert last["lord"] == r["lord"] and last["sub_lord"] == seventh and last["sub_to"] == r["to"], (r, last)


def test_hp17_the_outside_pass_case_and_its_neighbours(engine):
    at = engine["pn4_fardar_at_age"]
    age = 80.71428571428571                                     # cycle 2, the Sun's fifth seventh begins
    r = at(age, "Diurnal")
    assert r["sub_from"] <= age < r["sub_to"] and (r["lord"], r["sub_lord"], r["cycle"]) == ("Sun", "Saturn", 2), r
    below = at(math.nextafter(age, -math.inf), "Diurnal")
    assert below["sub_lord"] == "Moon" and below["sub_to"] == age, below
