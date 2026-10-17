"""Sahl, On Nativities 1.18, 7: "unless it receives it" is tested, and a
stationary partner is open (ruling 146 (1), A-03 of the third outside pass).

1.18, 7: "And the connection of the lord of the Ascendant with a <retrograde>
planet, or one in its first slowness, inverts it (unless it receives it): and
it is equivalent." The exception is read in 1.32, 35's direction only: a
partner that receives the lord of the Ascendant (evaluate_reception under
Sahl) is excepted; the lord receiving the partner is not. "Or one in its
first slowness" (fn 393: its first station) is not read, since a station is
not told first from second: a stationary partner not receiving the lord
leaves row 7 open, not "no". Row 7 is not counted (fn 126, 129), so the
count and 8-10's sentence do not move.

The reproduction's chart is REPRO_HIGH_A's A-03 scan hit: 2000-01-03 22:00
UT, 43.7792 N, 11.2463 E (Virgo rising; Mercury in Capricorn connecting with
Saturn retrograde in Taurus, who receives him by house). The other charts
were found by a scan of the engine itself (every day from 1950-01-01 12:00
UT, each day with a planet stationary and every seventh day otherwise, at
two-hourly times at five places), each kept only with its Ascendant, the
lord and every retrograde or stationary partner at least a degree from a
sign's edge, a stationary partner within half the station tolerance of rest
and a retrograde one at more than twice it, and no connection left
undecided -- not by editing a chart. The three charts with two partners, and
the chart whose stationary partner's own connection is undecided, are the
blind check's, found by its own scan of real charts and confirmed here
against the ruling before they were pinned.

Every app run here uses its own XDG directory (tmp_path).
"""
import html
from datetime import datetime, time

from conftest import assert_no_exception, make_app

# Saturn retrograde receives the lord (Mercury, in Saturn's Capricorn): no.
REPRO = ((2000, 1, 3, 22, 0), 43.7792, 11.2463)
# The Moon (Cancer rising) conjoins Saturn retrograde in Virgo, who has no
# dignity of his where she is: yes.
RETRO_NOT_RECEIVING = ((1950, 1, 8, 16, 0), 51.5, -0.12)
# Jupiter (Pisces rising) opposes Saturn stationary in Virgo, who does not
# receive him: open.
STATION_NOT_RECEIVING = ((1950, 5, 15, 0, 0), 30.0, 31.2)
# The Sun (Leo rising) in Cancer trines Jupiter stationary in Pisces, who
# receives him by exaltation: no.
STATION_RECEIVING = ((1950, 6, 27, 0, 0), -33.87, 151.21)
# Jupiter (Sagittarius rising) in Aquarius; Venus retrograde in Aquarius
# applies to him and he receives her (triplicity with bound); she does not
# receive him: yes.
LORD_RECEIVES_PARTNER = ((1950, 1, 22, 4, 0), 51.5, -0.12)
# Two partners. Mercury (Gemini rising) in Pisces: Saturn retrograde in Virgo
# does not receive him, Jupiter retrograde in Cancer does (house): the one
# not receiving settles yes.
TWO_RETRO_ONE_RECEIVING = ((2038, 2, 23, 4, 10), -41.013, 164.764)
# The Moon (Cancer rising) in Scorpio: Mars retrograde in Taurus receives her
# (house), Jupiter stationary in Aquarius does not: open on Jupiter alone.
RETRO_RECEIVING_STATION_NOT = ((1973, 9, 28, 17, 52), 17.048, 101.639)
# Mercury (Gemini rising) in Pisces: Saturn stationary in Gemini and Mars
# retrograde in Cancer, neither receiving: the retrograde partner settles yes
# before the stationary one can open the row.
STATION_AND_RETRO_NEITHER_RECEIVING = ((1914, 2, 12, 3, 18), 3.462, 145.649)
# Saturn (Capricorn rising) with Jupiter stationary in Capricorn, not
# receiving him, the conjunction's connection itself undecided: row 7 is open
# on the connection, one outcome being 7's own open result.
STATION_CONNECTION_UNDECIDED = ((1961, 9, 23, 9, 38), 45.254, 73.047)

S0 = 'no testimony of a short upbringing (1.18, 1-4)'
S1 = ('"the releaser will be weak and not fit, except through the reception of that releaser, '
      '[which indicates] fitness" (1.18, 8)')
S2 = ('"if ... there were two testimonies of what I mentioned, and the native did not have a releaser, '
      'one will not know his lifespan except by revolving [his] years" (1.18, 9; fn 130)')
OPEN_REASON = ('met if Saturn is in its first slowness, not met otherwise ("first slowness" is not read; '
               'Saturn is stationary and does not receive Jupiter)')


def _chart(engine, case):
    when, lat, lon = case
    return engine["calculate_traditional_chart"](datetime(*when), lat, lon)


def _short_life(engine, case):
    chart = _chart(engine, case)
    return engine["sahl_short_life_testimonies"](chart, chart["lot_of_fortune"])


def _sahl_receptions(engine, case):
    chart = _chart(engine, case)
    with engine["doctrine"](engine["SAHL"]):
        rows = engine["evaluate_reception"](chart["planetary_data"], chart["sect"])
    return {(r["Receiver"], r["Received"]) for r in rows}


def _row7(out):
    row = out["rows"][6]
    assert row["Source"] == "1.18, 7" and row["Counted"] == 'no -- "equivalent" (fn 129)', row
    return row


def _count_and_sentence_are(out, count, sentence):
    """The count and 8-10's sentence, exactly as before the change: row 7 is
    not counted."""
    assert type(out["count"]) is int and out["count"] == count, out["count"]
    assert out["sentence"] == sentence, out["sentence"]


# --- the engine -----------------------------------------------------------

def test_reproduction_partner_receiving_the_lord_is_no_and_named(engine):
    assert ("Saturn", "Mercury") in _sahl_receptions(engine, REPRO)
    out = _short_life(engine, REPRO)
    row = _row7(out)
    assert row["Met"] == "no", row
    assert row["Fact"] == "Saturn: retrograde, receiving Mercury", row["Fact"]
    _count_and_sentence_are(out, 0, S0)


def test_a_retrograde_partner_not_receiving_the_lord_is_yes(engine):
    receptions = _sahl_receptions(engine, RETRO_NOT_RECEIVING)
    assert ("Saturn", "Moon") not in receptions, receptions
    out = _short_life(engine, RETRO_NOT_RECEIVING)
    row = _row7(out)
    assert row["Met"] == "yes", row
    assert row["Fact"] == "Saturn: retrograde, not receiving Moon", row["Fact"]
    _count_and_sentence_are(out, 0, S0)


def test_a_stationary_partner_not_receiving_the_lord_is_open(engine):
    chart = _chart(engine, STATION_NOT_RECEIVING)
    saturn = chart["planetary_data"]["Saturn"]
    assert engine["motion_state"]("Saturn", saturn["speed_in_lon"]) == "stationary"
    assert ("Saturn", "Jupiter") not in _sahl_receptions(engine, STATION_NOT_RECEIVING)
    out = _short_life(engine, STATION_NOT_RECEIVING)
    row = _row7(out)
    met = row["Met"]
    assert engine["is_unresolved"](met), met
    assert met.reason == OPEN_REASON, met.reason
    assert met.source == "1.18, 7"
    assert [v for _name, v in met.alternatives] == ["yes", "no"]
    assert row["Fact"] == "Saturn: stationary, not receiving Jupiter", row["Fact"]
    _count_and_sentence_are(out, 1, S1)


def test_a_stationary_partner_receiving_the_lord_is_no(engine):
    chart = _chart(engine, STATION_RECEIVING)
    jupiter = chart["planetary_data"]["Jupiter"]
    assert engine["motion_state"]("Jupiter", jupiter["speed_in_lon"]) == "stationary"
    assert ("Jupiter", "Sun") in _sahl_receptions(engine, STATION_RECEIVING)
    out = _short_life(engine, STATION_RECEIVING)
    row = _row7(out)
    assert row["Met"] == "no", row
    assert row["Fact"] == "Jupiter: stationary, receiving Sun", row["Fact"]
    _count_and_sentence_are(out, 0, S0)


def test_the_lord_receiving_the_partner_does_not_except_it(engine):
    receptions = _sahl_receptions(engine, LORD_RECEIVES_PARTNER)
    assert ("Jupiter", "Venus") in receptions and ("Venus", "Jupiter") not in receptions, receptions
    out = _short_life(engine, LORD_RECEIVES_PARTNER)
    row = _row7(out)
    assert row["Met"] == "yes", row
    assert row["Fact"] == "Venus: retrograde, not receiving Jupiter", row["Fact"]
    _count_and_sentence_are(out, 2, S2)


# --- two partners, and an undecided connection ----------------------------

def test_one_retrograde_partner_not_receiving_is_yes_beside_one_that_receives(engine):
    receptions = _sahl_receptions(engine, TWO_RETRO_ONE_RECEIVING)
    assert ("Jupiter", "Mercury") in receptions and ("Saturn", "Mercury") not in receptions, receptions
    out = _short_life(engine, TWO_RETRO_ONE_RECEIVING)
    row = _row7(out)
    assert row["Met"] == "yes", row
    assert row["Fact"] == "Saturn: retrograde, not receiving Mercury; Jupiter: retrograde, receiving Mercury", row["Fact"]
    _count_and_sentence_are(out, 1, S1)


def test_a_receiving_retrograde_partner_leaves_a_stationary_one_open(engine):
    receptions = _sahl_receptions(engine, RETRO_RECEIVING_STATION_NOT)
    assert ("Mars", "Moon") in receptions and ("Jupiter", "Moon") not in receptions, receptions
    out = _short_life(engine, RETRO_RECEIVING_STATION_NOT)
    row = _row7(out)
    met = row["Met"]
    assert engine["is_unresolved"](met), met
    assert met.reason == ('met if Jupiter is in its first slowness, not met otherwise ("first slowness" is not read; '
                          'Jupiter is stationary and does not receive Moon)'), met.reason
    assert [v for _name, v in met.alternatives] == ["yes", "no"]
    assert row["Fact"] == "Jupiter: stationary, not receiving Moon; Mars: retrograde, receiving Moon", row["Fact"]
    _count_and_sentence_are(out, 0, S0)


def test_a_retrograde_partner_not_receiving_settles_yes_before_a_stationary_one(engine):
    receptions = _sahl_receptions(engine, STATION_AND_RETRO_NEITHER_RECEIVING)
    assert ("Saturn", "Mercury") not in receptions and ("Mars", "Mercury") not in receptions, receptions
    out = _short_life(engine, STATION_AND_RETRO_NEITHER_RECEIVING)
    row = _row7(out)
    assert row["Met"] == "yes", row
    assert row["Fact"] == "Saturn: stationary, not receiving Mercury; Mars: retrograde, not receiving Mercury", row["Fact"]
    _count_and_sentence_are(out, 0, S0)


def test_a_stationary_partner_whose_connection_is_undecided_is_open_on_the_connection(engine):
    """As it is shown today: the connection-uncertainty idiom's open result,
    one outcome 7's own open result and the other "no", the Fact open the
    same way."""
    out = _short_life(engine, STATION_CONNECTION_UNDECIDED)
    row = _row7(out)
    met = row["Met"]
    assert engine["is_unresolved"](met) and met.reason == "the result depends on an unresolved connection", met
    (name1, inner), (name2, other) = met.alternatives
    assert (name1, name2, other) == ("permitted outcome 1", "permitted outcome 2", "no"), met.alternatives
    assert engine["is_unresolved"](inner) and inner.source == "1.18, 7", inner
    assert inner.reason == ('met if Jupiter is in its first slowness, not met otherwise ("first slowness" is not '
                            'read; Jupiter is stationary and does not receive Saturn)'), inner.reason
    assert [v for _name, v in inner.alternatives] == ["yes", "no"]
    fact = row["Fact"]
    assert engine["is_unresolved"](fact), fact
    assert [v for _name, v in fact.alternatives] == ["Jupiter: stationary, not receiving Saturn",
                                                     "none retrograde or stationary"], fact.alternatives
    _count_and_sentence_are(out, 1, S1)


# --- the page and the reports ---------------------------------------------

def _releaser_page(case, xdg, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg))
    (y, mo, d, *hms), lat, lon = case
    at = make_app(page="releaser", timeout=300)
    at.session_state["manual_lat_key"] = lat
    at.session_state["manual_lon_key"] = lon
    at.session_state["date_input_key"] = f"{y:04d}-{mo:02d}-{d:02d}"
    at.session_state["time_input_key"] = time(*hms)
    at.session_state["time_standard_key"] = "Manual UTC offset"
    at.session_state["utc_offset_key"] = 0.0
    at.run()
    assert_no_exception(at, "the releaser page")
    return at


OPEN_TEXT = "Unresolved — " + OPEN_REASON
HEAD = "The short-life testimonies (1.18, 1-10, Masha'allah, fn 125): "
TAIL = 'Shown beside the releaser; they do not disqualify it here. 5-7 are "equivalent" and not counted (fn 126, 129).'
SETTLED_1 = HEAD + "1 of the four counted -- " + S1 + ". " + TAIL


def test_page_and_reports_show_a_stationary_partner_open(tmp_path, monkeypatch):
    """The page's row table and the JSON, Markdown and HTML reports carry
    row 7 open, as they carry an open row 4; the headline and the reports'
    line over the table keep the settled count of 1 exactly."""
    at = _releaser_page(STATION_NOT_RECEIVING, tmp_path, monkeypatch)
    frames = [df.value for df in at.main.dataframe if "Testimony" in df.value.columns]
    assert len(frames) == 1
    rows = frames[0][frames[0]["Testimony"].str.startswith("7.")]
    assert len(rows) == 1 and rows.iloc[0]["Met"] == OPEN_TEXT, rows.iloc[0]["Met"]
    assert rows.iloc[0]["Fact"] == "Saturn: stationary, not receiving Jupiter"
    heads = [m.value for m in at.main.markdown if m.value.startswith("**The short-life testimonies")]
    assert heads == [f"**{HEAD}1 of the four counted** -- {S1}. {TAIL}"], heads
    found = [r for page in at.session_state["_analysis_export"]["results"].values()
             for entries in page.values() for e in entries for r in e["rows"]
             if isinstance(r, dict) and str(r.get("Testimony", "")).startswith("7. The lord of the Ascendant")]
    assert len(found) == 1, found
    met = found[0]["Met"]
    assert met["result_type"] == "UnresolvedResult" and met["display"] == OPEN_TEXT, met
    md = at.session_state["_analysis_markdown"].splitlines()
    md7 = [line for line in md if line.startswith("| 7. The lord of the Ascendant")]
    assert len(md7) == 1 and f"| {OPEN_TEXT}" in md7[0], md7
    assert f"**{SETTLED_1}**" in md
    page_html = at.session_state["_analysis_html"]
    assert f"<td>{html.escape(OPEN_TEXT)}</td>" in page_html
    assert f"<p class='label'>{html.escape(SETTLED_1)}</p>" in page_html


def test_page_shows_the_reproduction_no_with_its_count(tmp_path, monkeypatch):
    at = _releaser_page(REPRO, tmp_path, monkeypatch)
    frames = [df.value for df in at.main.dataframe if "Testimony" in df.value.columns]
    rows = frames[0][frames[0]["Testimony"].str.startswith("7.")]
    assert rows.iloc[0]["Met"] == "no" and rows.iloc[0]["Fact"] == "Saturn: retrograde, receiving Mercury"
    heads = [m.value for m in at.main.markdown if m.value.startswith("**The short-life testimonies")]
    assert heads == [f"**{HEAD}0 of the four counted** -- {S0}. {TAIL}"], heads


def test_page_shows_an_undecided_connection_open(tmp_path, monkeypatch):
    """The nested open result prints as the connection idiom prints it (its
    alternatives hidden, one not being a plain value); the Fact gives both
    outcomes."""
    at = _releaser_page(STATION_CONNECTION_UNDECIDED, tmp_path, monkeypatch)
    frames = [df.value for df in at.main.dataframe if "Testimony" in df.value.columns]
    rows = frames[0][frames[0]["Testimony"].str.startswith("7.")]
    assert len(rows) == 1
    assert rows.iloc[0]["Met"] == "Unresolved — the result depends on an unresolved connection", rows.iloc[0]["Met"]
    assert rows.iloc[0]["Fact"] == ("Unresolved — the result depends on an unresolved connection (permitted outcome 1: "
                                    "Jupiter: stationary, not receiving Saturn; permitted outcome 2: none retrograde "
                                    "or stationary)"), rows.iloc[0]["Fact"]
