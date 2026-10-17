"""Two partners at a shift and at the opening: lane KP (R2-03, R2-04), after the owner's rulings 14, 19 and 33.

PN IV III.1, 50 (PN IV p. 293): "But if one of them was in the management of
two planets or more, then the work in it is in accordance with their natures"
(n. 39: the Arabic's dual read as a plural; n. 40: "we ought to combine
them"). Ruling 14: two partners met at once count together; ruling 19 (2):
at the opening as well (III.1, 23-25, 24 read with 50); ruling 33: where the
text expects one partner -- the twenty-four shifts (III.2, 55-101) among
them -- each is read by its own nature, a pair of one nature giving one
shift, the page labelling it as this app's reading of III.1, 50.

R2-03. III.2, 68-76 (PN IV pp. 307-308) number the eight bound shifts by the
manager in the bound shifted into: #9 "if the distribution shifts from the
bound of a fortune to the bound of a fortune, in the management of a
fortune" (69). A partner that stays across a shift of bound manages in the
new bound as one that comes does, so each partner after the shift is read --
where the shift of management took only the partners that came.

R2-04. The running distribution counts two contacts within one tolerance as
met at one position; the opening chose its partner by exact equality, so a
body and a ray at one degree opened as one partner, and a ray a hair ahead of
a body on the starting degree replaced it for the whole distribution.
"""
from __future__ import annotations

import ast

from conftest import APP_PATH

# The reproduction's layout (R2_REPRODUCTION.md, section 2): Venus at 10.1
# Aries, Mars at 70.1 so that his left sextile, 70.1 - 60.0, falls at
# 10.099999999999994; the other five parked in Libra and Scorpio, whose
# rays first reach Aries at 20 (the Sun's opposition).
PARKED = {"Sun": 200.0, "Moon": 205.0, "Mercury": 215.0, "Jupiter": 225.0, "Saturn": 235.0}


def _planets(**longitudes):
    return {name: {"longitude": lon} for name, lon in {**PARKED, **longitudes}.items()}


def _identity(lon):
    return lon


def _distribute(engine, planets, start, measure=_identity, span=30.0):
    return engine["_pn4_distribute"](planets, start, measure, span, "the Ascendant")


def _segment_at(segments, arc):
    (segment,) = [s for s in segments if s["from"] <= arc < s["to"]]
    return segment


# --- R2-03: a bound shift reads every partner after it --------------------------------

def _rows(engine, before, after):
    together = engine["PN4Together"]
    as_partner = lambda p: together(p) if isinstance(p, tuple) else p
    return engine["pn4_classify_shift"]({"distributor": before[0], "partner": as_partner(before[1])},
                                        {"distributor": after[0], "partner": as_partner(after[1])})


def _bound(rows):
    return {tuple(row["numbers"]): row for row in rows if row["kind"] == "bound"}


def test_r2_03_a_partner_that_stays_is_read_for_the_bound_shift(engine):
    """The reproduction's case A: Venus's bound with Jupiter, then Saturn's
    bound with Jupiter and Mars together -- Jupiter stays, Mars comes. In
    the management of Jupiter, a fortune, the shift from a fortune's bound to
    an infortune's is #11 (III.2, 71); of Mars, #12 (72). Both are in force,
    each saying which partner it is read for, each labelled as this app's
    reading of III.1, 50."""
    rows = _rows(engine, ("Venus", "Jupiter"), ("Saturn", ("Jupiter", "Mars")))
    bound = _bound(rows)
    assert set(bound) == {(2, 11), (2, 12)}, rows
    assert bound[(2, 11)]["label"].endswith("; read for Jupiter"), bound[(2, 11)]
    assert bound[(2, 12)]["label"].endswith("; read for Mars"), bound[(2, 12)]
    reading = engine["PN4_TOGETHER_READING"]
    assert [reading in row["cite"] for row in bound.values()] == [True, True], rows
    assert "III.2, 97" in bound[(2, 11)]["indication"] and "III.2, 98" in bound[(2, 12)]["indication"], rows
    # The management still shifts only from the partner that leaves -- here
    # none leaves, so from Jupiter, who stays -- to the one that comes (#6,
    # #20, III.2, 65 and 81).
    management = [row for row in rows if row["kind"] == "management"]
    assert [row["numbers"] for row in management] == [[6, 20]], rows
    assert management[0]["label"] == "the management shifts from Jupiter to Jupiter and Mars together", management


def test_r2_03_a_partner_that_stays_is_read_when_both_sides_are_pairs(engine):
    """The reproduction's case D: Venus's bound with Jupiter and Mars, then
    Mars's bound with Jupiter and Saturn -- Jupiter stays, Mars leaves,
    Saturn comes. The bound shift reads Jupiter (#11) and Saturn (#12); the
    management shifts from Mars to Saturn (#8, #24)."""
    rows = _rows(engine, ("Venus", ("Jupiter", "Mars")), ("Mars", ("Jupiter", "Saturn")))
    bound = _bound(rows)
    assert set(bound) == {(2, 11), (2, 12)}, rows
    assert bound[(2, 11)]["label"].endswith("; read for Jupiter"), bound[(2, 11)]
    assert bound[(2, 12)]["label"].endswith("; read for Saturn"), bound[(2, 12)]
    assert [row["numbers"] for row in rows if row["kind"] == "management"] == [[8, 24]], rows


def test_r2_03_the_reviewer_s_distribution_reads_mars_who_stays(engine):
    """The outside reviewer's case: Mars at 7 Aries, Venus at 7 Gemini,
    Jupiter at 7 Cancer, directed from 0 Aries. At 97 the bound shifts from
    Mars's to Venus's while the partners go from Mars and Venus (Mars's
    sextile, Venus's body) to Jupiter and Mars (Jupiter's body, Mars's
    square): Mars stays. In the management of Jupiter the shift from an
    infortune's bound to a fortune's is #13 (III.2, 73, read at 95); in the
    management of Mars, #14 (74, read at 96)."""
    planets = {"Mars": {"longitude": 7.0}, "Venus": {"longitude": 67.0}, "Jupiter": {"longitude": 97.0}}
    segments = engine["_pn4_distribute"](planets, 0.0, _identity, 110.0, "test point")
    before, after = _segment_at(segments, 96.5), _segment_at(segments, 97.5)
    assert (before["distributor"], tuple(before["partner"])) == ("Mars", ("Mars", "Venus")), before
    assert (after["distributor"], tuple(after["partner"])) == ("Venus", ("Jupiter", "Mars")), after
    rows = engine["pn4_year_transitions"](segments, 96.5, 97.5)
    bound = {row["Transition"]: row for row in rows if row["Shift"].startswith("the distribution shifts")}
    assert sorted(bound) == ["#3, #13", "#3, #14"], rows
    assert bound["#3, #13"]["Shift"].endswith("; read for Jupiter") and "III.2, 95" in bound["#3, #13"]["Indication"], rows
    assert bound["#3, #14"]["Shift"].endswith("; read for Mars") and "III.2, 96" in bound["#3, #14"]["Indication"], rows
    management = [row for row in rows if row["Shift"].startswith("the management shifts")]
    assert [row["Transition"] for row in management] == ["#5, #17"], rows


def test_r2_03_a_partner_that_stays_is_a_bound_shift_with_the_same_partner(engine):
    """III.2, 93: "if in addition to the shift of the distribution from a
    fortune to a fortune, the management of its manager also shifts from a
    fortune to a fortune ... if the four of them were fortunes". Jupiter's
    bound with Venus, then Venus's bound with Jupiter, Mars and Venus -- not
    a pair of one nature. Jupiter comes, and read for him the management
    shifts from Venus to Jupiter, so the four are fortunes and 93 is added;
    Mars comes (#10, III.2, 70 and 94); Venus stays, and read for her the
    bound shifts with the same partner (#9, III.2, 69 and 92) and her
    management does not shift, so 93 is not added."""
    rows = _rows(engine, ("Jupiter", "Venus"), ("Venus", ("Jupiter", "Mars", "Venus")))
    bound = {row["label"].rsplit("; read for ", 1)[-1]: row for row in rows if row["kind"] == "bound"}
    assert {name: row["numbers"] for name, row in bound.items()} == \
        {"Jupiter": [1, 9], "Mars": [1, 10], "Venus": [1, 9]}, rows
    assert "(III.2, 93)" in bound["Jupiter"]["indication"], bound["Jupiter"]
    assert "(III.2, 93)" not in bound["Venus"]["indication"], bound["Venus"]
    assert [row["numbers"] for row in rows if row["kind"] == "management"] == [[5, 17], [6, 19]], rows


def test_a_pair_of_one_nature_gives_one_shift_of_bound_with_the_four_of_them_where_they_hold(engine):
    """Ruling 33: "a same-nature pair collapses to one type and one shift".
    Jupiter's bound with Venus, then Venus's bound with Jupiter and Venus:
    the distribution shifts from a fortune to a fortune and the management
    from Venus to Jupiter, a fortune to a fortune, and every indicator is a
    fortune, so 93's condition holds for the shift whichever partner is
    read -- one #1, #9 row, with 93 (III.2, 93: "if in addition to the shift
    of the distribution from a fortune to a fortune, the management of its
    manager also shifts from a fortune to a fortune ... if the four of them
    were fortunes"). The mirror, Mars's bound with Saturn, then Saturn's
    with Mars and Saturn: one #4, #16 row with 101 ("if the four of them
    were infortunes"). Where the management comes in from the other nature
    (Mars, to Jupiter and Venus) the pair's one row has neither."""
    cases = {
        "fortunes": (("Jupiter", "Venus"), ("Venus", ("Jupiter", "Venus"))),
        "infortunes": (("Mars", "Saturn"), ("Saturn", ("Mars", "Saturn"))),
        "in from the other nature": (("Jupiter", "Mars"), ("Venus", ("Jupiter", "Venus"))),
    }
    reading = engine["PN4_TOGETHER_READING"]
    got = {name: [(row["numbers"], "; read for " in row["label"],
                   "(III.2, 93)" in row["indication"] or "(III.2, 101)" in row["indication"], reading in row["cite"])
                  for row in _rows(engine, before, after) if row["kind"] == "bound"]
           for name, (before, after) in cases.items()}
    assert got == {
        "fortunes": [([1, 9], False, True, True)],
        "infortunes": [([4, 16], False, True, True)],
        "in from the other nature": [([1, 9], False, False, True)],
    }, got


def test_r2_03_the_page_says_a_shift_of_bound_reads_every_partner_after_it():
    """The Timing page's note on the classifications states the rule the
    shift table follows, with the sentence it rests on."""
    notes = [node.elts[1].value for node in ast.walk(ast.parse(APP_PATH.read_text(encoding="utf-8")))
             if isinstance(node, ast.Tuple) and len(node.elts) == 2
             and all(isinstance(e, ast.Constant) for e in node.elts)
             and node.elts[0].value == "Classifications, and the three planets of neither nature."]
    assert len(notes) == 1, notes
    (note,) = notes
    assert ("A shift of bound is read for every partner after it, one that stays as well as one that comes, "
            "for it is numbered by who manages in the bound shifted into (\"in the management of a fortune\", "
            "PN IV III.2, 69)") in note, note
    assert ("\"the four of them\" of PN IV III.2, 93 and 101 are counted only for a partner the management shifts to, "
            "save that a pair of one nature gives its one shift, with them where they "
            "hold. This is this app's reading of III.1, 50.") in note, note


# --- R2-04: one position at the opening as later -------------------------------------

def test_r2_04_a_body_and_a_ray_behind_the_degree_open_together(engine):
    """Started at 15 Aries, the direction stands in the management of Venus's
    body and Mars's sextile at 10 Aries 06' (III.1, 24), the two at one
    position -- as the same two are one position when a direction started at
    5 Aries meets them at an arc of 5.1."""
    planets = _planets(Venus=10.1, Mars=70.1)
    opening = _distribute(engine, planets, 15.0)[0]
    assert opening["partner"] == engine["PN4Together"](("Mars", "Venus")), opening
    assert tuple(opening["partner_aspect"]) == ("sextile", "body"), opening
    assert "Mars by sextile and Venus by body" in opening["partner_from"], opening
    assert opening["partner_from"].endswith("behind the Ascendant, together (PN IV III.1, 50)"), opening
    running = _segment_at(_distribute(engine, planets, 5.0), 5.5)
    assert running["partner"] == opening["partner"] and running["partner_aspect"] == opening["partner_aspect"], running


def test_r2_04_a_body_on_the_degree_and_a_ray_at_it_open_together(engine):
    planets = _planets(Venus=10.1, Mars=70.1)
    opening = _distribute(engine, planets, 10.1)[0]
    assert opening["partner"] == engine["PN4Together"](("Mars", "Venus")), opening
    assert "at the starting degree, together" in opening["partner_from"], opening


def test_r2_04_a_ray_a_hair_ahead_keeps_the_body_on_the_degree(engine):
    """Mars at 70.10000000000002: his sextile falls 2e-14 ahead of Venus on
    the starting degree. The two are one position; Venus is not replaced at
    an arc of 2e-14 and lost from the whole distribution."""
    segments = _distribute(engine, _planets(Venus=10.1, Mars=70.10000000000002), 10.1)
    assert segments[0]["from"] == 0.0, segments[0]
    assert segments[0]["partner"] == engine["PN4Together"](("Mars", "Venus")), segments[0]
    assert "at the starting degree, together" in segments[0]["partner_from"], segments[0]
    # Until the Sun's opposition at 20 Aries, nothing else is met.
    held = [s for s in segments if s["to"] <= 9.9 + 1e-9]
    assert len(held) == 2, segments  # the bounds of Venus and Mercury
    assert all(s["partner"] == segments[0]["partner"] for s in held), held


def test_r2_04_a_contact_within_the_tolerance_behind_is_at_the_starting_degree(engine):
    opening = _distribute(engine, _planets(Venus=10.1 - 4e-10), 10.1)[0]
    assert opening["partner"] == "Venus", opening
    assert opening["partner_from"].endswith(", at the starting degree"), opening


# Separations of the second contact from the first: within the running
# path's one-position tolerance (1e-9 degree of the measure) and beyond it.
WITHIN = (0.0, 2e-14, 4e-10, 8e-10)
BEYOND = (3e-9, 1e-6)


def _what_is_met(engine, planets, first, second, measure=_identity):
    """The partner once both contacts are behind the direction, by four
    routes: met while running (from 5 degrees before the first), at the
    opening with both behind (from 4 degrees past the second), on the second
    as the starting degree, and on the first as the starting degree with the
    second ahead. Each is the partner holding a quarter of a year past the
    second contact, or past the start where the start is not behind it."""
    out = {}
    for name, start in (("running", first - 5.0), ("behind", second + 4.0), ("on the second", second),
                        ("on the first", first)):
        segments = _distribute(engine, planets, start, measure)
        past = max(measure(second) - measure(start), 0.0) + 0.25
        out[name] = _segment_at(segments, past)["partner"]
    return out


def test_r2_04_the_opening_and_the_running_path_agree_on_every_tie(engine):
    """Two bodies a separation apart, Venus first and Mars second or the
    other way round: within the tolerance both are partners together by
    every route; beyond it the later alone. The same with the oblique
    ascensions of 43.78 N, where the tolerance is in degrees of ascension."""
    together = engine["PN4Together"]
    oblique = lambda lon: engine["_oblique_ascension"](lon, 23.44, 43.78)
    cases, disagreements = [], []
    for measure, separations in ((_identity, WITHIN + BEYOND), (oblique, (2e-14, 1e-6))):
        for separation in separations:
            for first_name, second_name in (("Venus", "Mars"), ("Mars", "Venus")):
                first, second = 10.1, 10.1 + separation
                planets = _planets(**{first_name: first, second_name: second})
                tie = abs(measure(second) - measure(first)) <= 1e-9
                expected = together(("Mars", "Venus")) if tie else second_name
                got = _what_is_met(engine, planets, first, second, measure)
                cases.append((separation, first_name))
                if set(got.values()) != {expected}:
                    disagreements.append((measure is _identity, separation, first_name, got))
    assert len(cases) == 16, cases
    assert disagreements == [], disagreements
