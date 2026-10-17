"""Text the reader types: the place box's parser and its length, and the
direction controls a name or a place carries into the exports.

The parser (D-01). parse_lat_lon read the box with \\s*[, ]\\s* between the
two numbers, and a number, a long run of spaces and a letter made the
pattern try every split of the run: 16,000 spaces took about three seconds,
quadrupling with each doubling, and the box takes text of any length. The
pattern is now possessive throughout, so a failed match never goes back,
and the box and the parser refuse an entry longer than any place. The
language it accepts is the old one exactly: the old parser is kept below,
under a name of this file's own, as the reference every string is read
against.

The isolates (SB-08). A name or place holding RIGHT-TO-LEFT OVERRIDE is set
between FIRST STRONG ISOLATE and POP DIRECTIONAL ISOLATE on the page and in
the Markdown export; the HTML export and the wheel now set it the same way,
so the override turns nothing outside the name.
"""
import json
import random
import re
import time
from datetime import datetime
from pathlib import Path

import pytest

from conftest import assert_no_exception, make_app

FIXTURE = Path(__file__).parent / "fixtures" / "lat_lon_sample_2026_10_13.json"
TOO_LONG = "This entry is too long to be a city or a latitude, longitude pair, so it was not looked up."
CAP = 200


def _reference_lat_lon(text):
    """parse_lat_lon as it stood before, the reference: the same accepted
    language, the same values. Nothing outside this file calls it."""
    m = re.fullmatch(r"\s*([-+]?\d+(?:\.\d+)?)\s*[, ]\s*([-+]?\d+(?:\.\d+)?)\s*", str(text))
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if abs(lat) > 90.0 or abs(lon) > 180.0:
        return None
    return lat, lon


# The pieces a typed coordinate is made of, and the near misses: digits
# (Arabic-Indic and full-width among them, which \d also reads), signs,
# points, commas, every kind of space, degree, minute and second marks,
# hemisphere letters and stray punctuation.
_TOKENS = (list("0123456789") * 4 + list(".-+,, ") * 3
           + ["  ", "\t", "\n", " ", " ", "　", "°", "'", '"', "′", "″", "º",
              "N", "S", "E", "W", "n", "e", "deg", "x", "٤", "５", "١", ";", "/", ".5"])
_SPACES = [" ", ",", "\t", " ", "\n", ", ", " ,", "  ", ""]


def _equivalence_corpus(n, seed):
    """n strings, a third each: random runs of the tokens; two loose
    numbers between loose separators, sometimes with a mark added or a
    separator replaced; and two numbers in or near range between runs of
    spaces and commas of every kind."""
    r = random.Random(seed)
    out = []
    for i in range(n):
        if i % 3 == 1:
            out.append("".join(r.choice(_TOKENS) for _ in range(r.randint(0, 14))))
        elif i % 3 == 2:
            def ws():
                return "".join(r.choice([" ", ",", "\t", " ", "\n", " "]) for _ in range(r.randint(0, 4)))

            def num(limit):
                return (r.choice(["", "-", "+"]) + str(r.randint(0, limit))
                        + r.choice(["", "." + str(r.randint(0, 99999))]))
            out.append(ws() + num(95) + ws() + num(185) + ws())
        else:
            def sep():
                return "".join(r.choice(_SPACES) for _ in range(r.randint(0, 3)))

            def loose():
                return (r.choice(["", "-", "+", "--", "+-"])
                        + "".join(r.choice("0123456789٤５") for _ in range(r.randint(0, 3)))
                        + r.choice(["", ".", "." + str(r.randint(0, 9999)), ".."]))
            s = sep() + loose() + sep() + loose() + sep()
            if r.random() < 0.3:
                s += r.choice(_TOKENS)
            if s and r.random() < 0.2:
                s = r.choice(["°", "N", "'", " "]).join(s.split(r.choice([" ", ",", "."]), 1))
            out.append(s)
    return out


# Every input tests/test_chart_input.py gives the parser, and the pair the
# app itself writes into the box.
EXISTING = ["45.3733, -84.9553", "45.3733 -84.9553", "-33.9, 151.2", "Florence", "91, 0", "0, 181",
            "45.3733", "", None, "45.37334, -84.95533", "43.7792, 11.2463"]
# The shapes at the edges of the old pattern: runs it backtracked over,
# separators it took and refused, digits \d reads, numbers float() would
# read but the pattern never did.
HOSTILE_SHAPES = (["1" + " " * k + "x" for k in (10, 100, 198)]
                  + ["1," + " " * 150 + "2", " " * CAP, "1 " * 99, ", " * 99, "1" + "\t" * 150 + "2",
                     "1 , , 2", "1 ,2", "1\t2", "1\t 2", "1  2", "1 2", "+1 -2", "1. 2", "1 .2",
                     "٤٥, ٨٤", "90 180", "-90, -180", "90.0000001 0", "1e3 2", "1_0 2", "0x1 2", "nan 1",
                     "inf 1", "1,2", "1,,2", "1, 　\n2", " \t1\n,\n2\t "])


# --- The parser reads what it read before ---------------------------------

def test_the_parser_reads_exactly_what_it_read_before(engine):
    """Existing inputs, the hostile shapes and 100,000 generated strings:
    the same pair or both refused. The generated set holds thousands of
    each, so the comparison is not won by refusing everything."""
    parse = engine["parse_lat_lon"]
    corpus = EXISTING + HOSTILE_SHAPES + _equivalence_corpus(100_000, 20261013)
    assert len(corpus) > 100_000
    assert max(len(s) for s in corpus if s is not None) <= CAP
    accepted = 0
    for s in corpus:
        want = _reference_lat_lon(s)
        assert parse(s) == want, repr(s)
        accepted += want is not None
    assert 5_000 < accepted < len(corpus) - 50_000, accepted


def test_a_fixed_sample_reads_as_recorded(engine):
    """2,000 of the generated strings, seeded, with what the old parser
    gave each, held in the fixture rather than recomputed."""
    sample = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(sample) == 2000
    parse = engine["parse_lat_lon"]
    for text, want in sample:
        assert parse(text) == (tuple(want) if want is not None else None), repr(text)
    assert sum(want is not None for _text, want in sample) > 100


# --- A long entry is judged in one pass, or refused unread ---------------

# The bound is 0.2 s. The fixed parser takes well under a millisecond on
# 50,000 characters, so a loaded machine has more than a hundredfold of
# room; the old pattern took from fifteen to forty seconds on each shape
# below, every one of which it read in time quadratic in the run.
BOUND = 0.2
LONG_SHAPES = {
    "spaces": "1" + " " * 50_000 + "x",
    "spaces then a comma": "1" + " " * 50_000 + ",x",
    "spaces and tabs": "1" + " \t" * 25_000 + "x",
    "a signed decimal, spaces and a mark": "-90.5" + " " * 50_000 + "°x",
}


def _timed(fn, text):
    t0 = time.perf_counter()
    got = fn(text)
    return got, time.perf_counter() - t0


@pytest.mark.parametrize("shape", list(LONG_SHAPES))
def test_fifty_thousand_spaces_are_judged_within_the_bound(engine, shape):
    """The parse itself, without the length cap, and the parser as the box
    calls it. A run over the bound is tried once more, in case the machine
    stalled; a run ten times over is backtracking, and fails at once."""
    text = LONG_SHAPES[shape]
    for fn in (engine["_lat_lon_numbers"], engine["parse_lat_lon"]):
        got, took = _timed(fn, text)
        assert took < 10 * BOUND, f"{fn.__name__} took {took:.2f} s on {shape}"
        if took >= BOUND:
            got, took = _timed(fn, text)
        assert took < BOUND, f"{fn.__name__} took {took:.3f} s on {shape}"
        assert got is None


def test_the_cap_refuses_a_pair_one_character_too_long(engine):
    """A pair the parse reads, padded to the cap, is read; one more space
    and it is refused, though the parse alone still reads it."""
    assert engine["PLACE_TEXT_MAX_CHARS"] == CAP
    at_cap = "45.3733, " + " " * (CAP - len("45.3733, -84.9553")) + "-84.9553"
    assert len(at_cap) == CAP
    assert engine["parse_lat_lon"](at_cap) == (45.3733, -84.9553)
    over = at_cap + " "
    assert engine["_lat_lon_numbers"](over) == (45.3733, -84.9553)
    assert engine["parse_lat_lon"](over) is None
    assert engine["parse_lat_lon"]("1" + " " * 50_000 + "2") is None


def _box(text):
    at = make_app(page="chart")
    at.session_state["manual_coords_key"] = False
    at.session_state["location_input_key"] = text
    return at


@pytest.mark.parametrize("text", [
    "45.3733, " + " " * CAP + "-84.9553",                 # a pair the parse alone reads
    "Florence " + "x" * CAP,                              # a city, then more than any place
], ids=["a pair", "a city"])
def test_the_box_refuses_a_long_entry_with_its_sentence(text):
    """Neither parsed nor looked up: the box says why, in the owner's
    sentence, and nothing is cast."""
    at = _box(text).run()
    assert_no_exception(at, "a long entry")
    assert [w.value for w in at.sidebar.warning if w.value == TOO_LONG] == [TOO_LONG]
    assert "Select specific location:" not in [s.label for s in at.sidebar.selectbox], "the atlas was asked"
    assert not [s for s in at.sidebar.success if s.value.startswith("**")], "a place was resolved"


def test_an_entry_at_the_cap_is_still_read():
    at = _box("45.3733, " + " " * (CAP - len("45.3733, -84.9553")) + "-84.9553").run()
    assert_no_exception(at, "a pair at the cap")
    assert TOO_LONG not in [w.value for w in at.sidebar.warning]


# The box has two routes to a place: the search under it, and the start of
# the coordinate fields when they are switched on. The atlas strips a text
# before it looks it up, so a city followed by more spaces than any place
# holds is a text the atlas matches; only the cap at the fields' start
# keeps that route from taking the city the box has just refused.
TOKYO = (35.6895, 139.69171)
PADDED_TOKYO = "Tokyo" + " " * (CAP + 100)


def _switched_on(text):
    """The box holds the text with the fields off; the run is made and the
    fields are switched on: what they start at, and the sidebar's warnings
    on that first run."""
    at = _box(text).run()
    assert_no_exception(at, "the box before the switch")
    warnings = [w.value for w in at.sidebar.warning]
    at.sidebar.toggle(key="manual_coords_key").set_value(True).run()
    assert_no_exception(at, "switching the fields on")
    return (at.session_state["manual_lat_key"], at.session_state["manual_lon_key"]), warnings


def test_switching_the_fields_on_does_not_take_a_city_the_box_refused():
    """A city padded past the cap: the box says the entry is too long, and
    the fields start where they start for a text that resolves to nothing,
    not at the city. The same city unpadded starts them at the city, so the
    atlas has the place and the padding alone is what is refused."""
    assert len(PADDED_TOKYO) > CAP
    unpadded, _ = _switched_on("Tokyo")
    assert unpadded == pytest.approx(TOKYO, abs=1e-4)
    padded, warnings = _switched_on(PADDED_TOKYO)
    assert [w for w in warnings if w == TOO_LONG] == [TOO_LONG]
    nowhere, _ = _switched_on("Qzxqzx")
    assert padded == nowhere
    assert padded != pytest.approx(TOKYO, abs=1)


def _typed_and_switched_on(text):
    """A first run whose box resolves nothing; then the text typed and the
    fields switched on in one run, so the fields' start resolves the text
    itself rather than keeping the box's last resolution: where they
    start, and that run's warnings."""
    at = _box("Qzxqzx").run()
    assert_no_exception(at, "the box before the text")
    assert "_resolved_lat" not in at.session_state
    at.sidebar.text_input(key="location_input_key").set_value(text)
    at.sidebar.toggle(key="manual_coords_key").set_value(True)
    at.run()
    assert_no_exception(at, "the text and the switch in one run")
    return (at.session_state["manual_lat_key"], at.session_state["manual_lon_key"])


def test_switching_the_fields_on_takes_a_city_padded_to_exactly_the_cap(engine):
    """The city padded to exactly the cap is a text the fields' start reads:
    they start at the city. One space more and they start where they start
    for a text that resolves to nothing. Typed in the run that switches
    the fields on, so it is the cap in the fields' own lookup that is
    tried, not the box's."""
    assert engine["PLACE_TEXT_MAX_CHARS"] == CAP
    at_cap = "Tokyo" + " " * (CAP - len("Tokyo"))
    assert len(at_cap) == CAP
    assert _typed_and_switched_on(at_cap) == pytest.approx(TOKYO, abs=1e-4)
    over = _typed_and_switched_on(at_cap + " ")
    assert over == _typed_and_switched_on("Qzxqzx2")
    assert over != pytest.approx(TOKYO, abs=1)


# --- RIGHT-TO-LEFT OVERRIDE ends with the name (SB-08) -------------------

RLO, FSI, PDI = "‮", "⁨", "⁩"
NAME = f"abc{RLO}def"
PLACE = f"Petoskey {RLO}MI"


def bare_overrides(text):
    """How many RIGHT-TO-LEFT OVERRIDEs stand outside every isolate."""
    depth, bare = 0, 0
    for ch in text:
        if ch in "⁦⁧⁨":
            depth += 1
        elif ch == PDI:
            depth = max(0, depth - 1)
        elif ch == RLO and not depth:
            bare += 1
    return bare


def test_the_counter_sees_a_bare_override():
    assert bare_overrides(NAME) == 1
    assert bare_overrides(f"{FSI}{NAME}{PDI} {PLACE}") == 1
    assert bare_overrides(f"{FSI}{NAME}{PDI} {FSI}{PLACE}{PDI}") == 0


@pytest.fixture(scope="module")
def rlo_page(tmp_path_factory):
    import os
    scratch = tmp_path_factory.mktemp("rlo")
    old = os.environ.get("XDG_DATA_HOME")
    os.environ["XDG_DATA_HOME"] = str(scratch)
    try:
        data = scratch / "Zij"
        data.mkdir(parents=True, exist_ok=True)
        (data / "saved_charts.json").write_text(json.dumps({NAME: {
            "date_string": "1982-11-19", "time_string": "11:44:00",
            "time_standard": "Standard time (named zone)", "utc_offset": None,
            "location_query": PLACE, "lat": 45.37334, "lon": -84.95533,
            "target_mode": "Date", "target_date": "2026-09-15", "target_age": 43}}), encoding="utf-8")
        at = make_app(page="sources").run(timeout=300)
        at.sidebar.selectbox(key="chart_picker").select(NAME).run(timeout=300)
        assert_no_exception(at, "a name and a place holding an override")
        return at.session_state["_analysis_html"]
    finally:
        if old is None:
            os.environ.pop("XDG_DATA_HOME", None)
        else:
            os.environ["XDG_DATA_HOME"] = old


def test_the_html_export_carries_no_bare_override(rlo_page):
    """Title, heading and both Place cells hold the override, each inside
    an isolate."""
    assert rlo_page.count(RLO) >= 4, "the name and the place reached the page"
    assert bare_overrides(rlo_page) == 0
    # Flags, not "in" asserts: pytest's report on a failed "in" over a page
    # this long takes minutes to write.
    title = f"<title>Analysis: {FSI}{NAME}{PDI}</title>" in rlo_page
    heading = f"<h1>Analysis: {FSI}{NAME}{PDI}</h1>" in rlo_page
    assert title and heading, (title, heading)
    assert rlo_page.count(f"<td>{FSI}{PLACE}{PDI}</td>") == 2


PETOSKEY = (45.37334, -84.95533)
REFERENCE_UTC = datetime(1982, 11, 19, 16, 44)


@pytest.fixture(scope="module")
def chart(engine):
    return engine["calculate_traditional_chart"](REFERENCE_UTC, *PETOSKEY)


@pytest.mark.parametrize("wide", [False, True])
def test_the_wheel_carries_no_bare_override(engine, chart, wide):
    svg = engine["generate_hybrid_svg"](chart, NAME, PLACE, PETOSKEY[0], PETOSKEY[1],
                                        datetime(1982, 11, 19, 11, 44), "America/Detroit", wide=wide)
    assert svg.count(RLO) == 2, "the name and the place reached the wheel"
    assert bare_overrides(svg) == 0
    assert f">{FSI}{NAME}{PDI}</text>" in svg
    assert f">{FSI}{PLACE}{PDI}</text>" in svg


def test_the_timing_wheel_carries_no_bare_override(engine, chart):
    svg = engine["generate_multiwheel_svg"]([{"label": "Natal", "chart": chart}], NAME)
    assert svg.count(RLO) == 1, "the name reached the wheel"
    assert bare_overrides(svg) == 0
    assert f">{FSI}{NAME}{PDI}</text>" in svg
