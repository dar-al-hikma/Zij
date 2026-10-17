"""Numbers as printed: lane H3 of the re-pass (the owner's rulings of
2026-10-05, items 4, 9 and 10).

* Ruling 4 (Q6, L5R-03) -- the minute carry stops at a sign boundary: a
  longitude within get_degree_string's tolerance below a sign's end prints
  29° 59' of its own sign, never 00° 00' of the next, so the printed sign
  is the sign get_zodiac_sign reads from the float, on the tables and on
  the wheel alike.
* Ruling 9 (Q12, N-03) -- a row detail's fact keeps "-0.00" for a negative
  value that rounds to zero, with the unrounded value beside it, and prints
  no scientific notation; the unrounded value still reads back exactly.
* Ruling 10 (Q13) -- the III.2 shift table's "At age" prints as the header
  prints the years elapsed (pn4_elapsed_text: three decimals, truncated),
  so a shift prints the same figure as the From cell of the distribution
  row it opens.
"""
import math


# --- Ruling 4: the carry stops at a sign boundary ---------------------------

_HAIRS = (1e-9, 1e-10, 1e-12, 1e-14, 3.5e-15, 1e-15)


def test_every_boundary_prints_the_sign_the_engine_reads(engine):
    """Every one of the twelve boundaries, approached from below by a hair
    inside the tolerance (and by 3.5e-15, where the float's product with 60
    already rounds up to the boundary's minute), on the circle and a turn
    either side: the printed sign is get_zodiac_sign's, the wheel's sign is
    the same, and below a boundary the print is the sign's last minute."""
    values = [30.0 * k - hair + turn for k in range(1, 13) for hair in _HAIRS for turn in (0.0, 360.0, -360.0)
              if 30.0 * k - hair + turn < 30.0 * k + turn]      # a turn can swallow the hair (390.0)
    assert len(values) >= 12 * len(_HAIRS), len(values)
    for lon in values:
        printed = engine["get_degree_string"](lon)
        sign = engine["get_zodiac_sign"](lon)
        assert printed == f"29° {sign[:3]} 59'", (lon, printed, sign)
        assert engine["SIGN_ORDER"][engine["_wheel_sign"](lon)] == sign, (lon, sign)
        assert engine["_wheel_dm"](lon) == (29, 59), (lon, engine["_wheel_dm"](lon))


def test_the_carry_still_works_inside_a_sign_and_at_the_seam(engine):
    """What the ruling leaves alone: a whole minute inside a sign is carried
    (Astra F13), an exact boundary is the next sign's first minute, and the
    seam's -1e-16 (which normalises to 360.0) is 0 Aries."""
    cases = {30 + 1 / 60: "00° Tau 01'", 45.0 - 1e-10: "15° Tau 00'", 30.0: "00° Tau 00'",
             360.0: "00° Ari 00'", -1e-16: "00° Ari 00'", -1 / 60: "29° Pis 59'", 0.0: "00° Ari 00'"}
    assert len(cases) == 7
    for lon, expected in cases.items():
        assert engine["get_degree_string"](lon) == expected, (lon, engine["get_degree_string"](lon))


# --- Ruling 9: "-0.00" stays; no scientific notation ------------------------

_FACT_VALUES = (-4.6968067468587115e-05, 4.6968067468587115e-05, -0.0001, 1e-07, -1e-300, 1.5e16, 1e+22,
                4.589889633317114, 1.0, -0.0, 0.0, math.nextafter(5.0, 0))


def test_a_fact_prints_no_scientific_notation_and_reads_back_exactly(engine):
    for value in _FACT_VALUES:
        text = engine["_fact"]("Latitude", value)
        assert text.startswith(f"Latitude: {value:.2f} (unrounded: "), text
        unrounded = text.split("(unrounded: ")[1][:-1]
        assert "e" not in unrounded.lower(), text
        assert float(unrounded) == value and math.copysign(1.0, float(unrounded)) == math.copysign(1.0, value), text


def test_a_negative_value_that_rounds_to_zero_keeps_its_sign(engine):
    assert engine["_fact"]("Latitude", -4.6968067468587115e-05) == \
        "Latitude: -0.00 (unrounded: -0.000046968067468587115)"


def test_where_repr_is_already_positional_the_unrounded_value_is_repr(engine):
    for value in (4.589889633317114, 1.0, 0.1, -12.5, 359.99999999999):
        assert engine["_fact"]("Speed", value) == f"Speed: {value:.2f} (unrounded: {value!r})"


# --- Ruling 10: III.2's "At age" as the header prints the years elapsed -----

def _segment(distributor, partner, start, end):
    return {"from": start, "to": end, "from_lon": 0.0, "distributor": distributor, "partner": partner,
            "partner_aspect": "body" if partner else None, "partner_from": "", "opened_by": ""}


def test_a_shift_prints_the_from_cell_of_the_row_it_opens(engine):
    segments = [_segment("Venus", None, 0.0, 1.5596), _segment("Saturn", None, 1.5596, 1.9999),
                _segment("Saturn", "Jupiter", 1.9999, 2.3), _segment("Mars", "Jupiter", 2.3, 9.0)]
    rows = engine["pn4_year_transitions"](segments, 1.0, 3.0)
    assert [r["At age"] for r in rows] == ["1.559", "1.999", "2.300"], rows
    table = engine["_pn4_distribution_rows"](segments, None)
    assert len(table) == len(segments)
    froms = [row["From age"] for row in table[1:]]
    assert [r["At age"] for r in rows] == froms
    assert [r["At age"] for r in rows] == [engine["pn4_elapsed_text"](s["from"]) for s in segments[1:]]
