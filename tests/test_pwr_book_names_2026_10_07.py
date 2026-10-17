"""Lane PWR of the re-pass's wave 5 (2026-10-07): the book named where a
locator is printed.

The owner's ruling 86: where the caption or the sentence already names the
work, a bare locator stays (the house form); elsewhere the work is named.
Three physical volumes number their chapters alike (Gr. Intr. and PN IV both
have a VII.9, 1), so a bare "IX.9, 4" is only a citation where something
the reader is looking at says whose IX.9 it is.

R01 -- the export. The Prediction pages say once, in their opening caption,
that their citations are PN IV's; the export carries no such caption, so a
heading, a caption or a cell the export prints names its work itself, or
stands under a heading or a caption (or, for a cell, a column) that does.

R03 -- a caption that names one work does not cover another work's locator
under it: such a cell names its own work.

Each class was a strict xfail on 87e9231 before its fix; the plan is the
corpus's ``process/hostile_pass_2026-10-03/repass/WAVE5_LANES.md`` (PWR).
"""
from __future__ import annotations

import re

import pytest

from conftest import assert_no_exception, make_app

# A work named: a title, its house abbreviation, or an author of one work in
# this corpus (Firmicus, the Mathesis; Valens; Rhetorius ...). An author of
# several (Sahl, Abu Ma'shar, Masha'allah, Dorotheus quoted inside Sahl)
# names no work.
WORK = re.compile(
    r"Gr\. ?Intr\.|Great Introduction|\bPN ?(?:IV|I{1,3})\b|Persian Nativities|On Nativities|"
    r"\bIntroduction\b|\bIntro\b|\bITA\b|Mathesis|Carmen|Fifty Aphorisms|Judgments of Nativities|"
    r"\bJN\b|\bTBN\b|Book of (?:the )?Nativities|Book of Aristotle|\bBA\b|Anthologies|Valens|"
    r"Rhetorius|Tetrabiblos|Almagest|\bAbbr\.|On Questions|On Choices|On Times|\bChoices\b|"
    r"Abu Bakr|Morin|Astrologia Gallica|Firmicus")

# The outside inventory's locator grammar (chapter-and-sentence, chapter
# alone, sections such as I.57b or I.4.4, decimal chapters with a sentence,
# "Ch. N, M"), so a chapter-only "(VI.2)" is read as well as "VI.2, 4"; a
# decimal chapter has at most two digits a part, so a place's coordinates
# ("43.7792, 11.2463") are not read as one.
LOC = re.compile(
    r"(?<![\w.])(?:[IVX]+\.\d+(?:\.\d+)?[a-c]?(?:\s*,\s*\d+(?:[-–]\d+)?(?:\s*,\s*\d+)*)?"
    r"|\d{1,2}\.\d{1,2}(?:\.\d{1,2})?(?!\d)\s*,\s*\d+(?:[-–]\d+)?|Ch(?:apter)?\.?\s*\d+\s*,\s*\d+)")

_END = re.compile(r"(\S*?)([.!?])([\"'”’)\]*_]*)\s+(?=[\"'“‘(\[*_]*[A-Z0-9])")
_ABBREV = {"gr", "intr", "ch", "fn", "fnn", "p", "pp", "fig", "figs", "cf", "e.g", "i.e", "sect", "abbr",
           "nat", "no", "vol", "st", "trans", "ed", "aph", "viz", "vs", "etc", "al", "n", "nn"}


def sentence_start(text, at):
    """Where the sentence holding offset `at` begins: after the last full
    stop (not an abbreviation's, not a roman numeral's) before it."""
    start = 0
    for m in _END.finditer(text[:at + 2]):
        if m.end() > at:
            break
        tok = m.group(1).lstrip("(\"'“*_[").lower()
        if m.group(2) == "." and (tok in _ABBREV or re.fullmatch(r"[ivxlc]+|[a-z]", tok)):
            continue
        start = m.end()
    return start


_CLOSED_GROUP = re.compile(r"\([^()]*\)")


def _open_part(text, start, at):
    """text[start:at] with every parenthesis closed before `at` blanked out:
    an aside the sentence has left ("2.11, 1-4 (fn 148: Carmen I.24); 2.13,
    39") names nothing for what follows it."""
    part = text[start:at]
    while True:
        blanked = _CLOSED_GROUP.sub(lambda g: " " * len(g.group(0)), part)
        if blanked == part:
            return part
        part = blanked


def named_before(text, at):
    """A work is named earlier in the sentence that holds offset `at`, outside
    any parenthesis closed before it."""
    return WORK.search(_open_part(text, sentence_start(text, at), at)) is not None


_NAMED_RIGHT_AFTER = re.compile(r"\s*(?:\(\s*|,\s+)(?:in\s+)?(?:" + WORK.pattern + ")")


def named_in_an_aside(text, m):
    """The owner's ruling 129 (2026-10-07): where the sentence already names
    the work, a later locator of it stays bare -- also where it was named in
    a parenthesis the sentence has closed ("(PN IV IV.1, 11): ...; (solar
    returns completed, I.2, 1-3)"). So, where nothing is named earlier
    outside one, a work named at a locator inside one names a later locator
    of the form its citations take; a work of another form does not ("2.11,
    1-4 (fn 148: Carmen I.24, 1-8); 2.13, 39")."""
    start = sentence_start(text, m.start())
    if WORK.search(_open_part(text, start, m.start())):
        return False
    takes = next(work for form, work in _FORMS if form.match(m.group(0)))
    for w in WORK.finditer(text, start, m.start()):
        gap = re.match(r"(?:'s)?[\s,*_]*", text[w.end():]).end()
        if takes.search(w.group(0)) and LOC.match(text, w.end() + gap):
            return True
    return False


def names_its_work(text, m):
    """The locator `m` names its work: earlier in its sentence, or at once
    after it, in the parenthesis or clause that hangs on it ("al-Qabisi
    I.57b (ITA I.13)", "al-Qabisi V.14a, in ITA VI.2.45")."""
    return (named_before(text, m.start()) or _NAMED_RIGHT_AFTER.match(text, m.end()) is not None
            or named_in_an_aside(text, m))


def test_the_sentence_reader_reads_the_house_forms():
    assert named_before("as PN IV I.6, 3 writes; I.6, 4 likewise", 30)
    assert named_before("Gr. Intr. VII.2, 44 as printed, not 40's 7", 10)
    assert not named_before("PN IV I.6, 3 writes it. I.6, 4 likewise", 25)
    assert not named_before("Sahl's strength testimony 80; I.7, 7 names it", 30)
    assert named_before("Sahl, The Introduction Ch. 3, 91-100", 23)
    text = "reported by al-Qabisi I.57b (ITA I.13): the lords"
    assert names_its_work(text, LOC.search(text))
    text = "Sahl 8.6, 1 leaves it, Gr. Intr. VIII.4, 226 prescribes it"
    assert not names_its_work(text, LOC.search(text))
    # an aside closed before the locator names nothing for it
    text = "2.11, 1-4 (fn 148: Carmen I.24, 1-8); 2.13, 39"
    assert not named_before(text, text.index("2.13, 39"))
    assert named_before("Sahl, On Nativities 2.11, 1-4 (fn 148: Carmen I.24, 1-8); 2.13, 39", 58)
    # ...unless it named the work at a locator of the later one's form (ruling 129)
    assert not names_its_work(text, LOC.search(text, text.index("2.13, 39")))
    text = "years elapsed (PN IV IV.1, 11): the table; the cycle (solar returns completed, I.2, 1-3): the rest"
    assert names_its_work(text, LOC.search(text, text.index("I.2, 1-3")))


# --- R01: the export ----------------------------------------------------------

TARGET = "2026-10-07"
FLORENCE = (43.7792, 11.2463)
# Six charts whose exports between them reach every table that prints a
# locator in a seeded sweep of fifty (scratch probe, lane PWR): each
# (date, time, latitude, longitude, depth).
EXPORT_CHARTS = {
    "2005-11-17": ("2005-11-17", (22, 51), 59.2133, -10.436, "Course text and supplement"),
    "1240-10-05": ("1240-10-05", (14, 30), *FLORENCE, "Course text"),
    "1604-12-01": ("1604-12-01", (5, 6), 36.041, 118.1591, "Course text"),
    "2017-02-27": ("2017-02-27", (13, 29), -49.9655, 79.5612, "Course text and supplement"),
    "1240-05-23": ("1240-05-23", (14, 30), *FLORENCE, "Course text and supplement"),
    # The Moon in the fifth: Dykes's summary of Rhetorius in the Topical table.
    "1897-10-14": ("1897-10-14", (13, 37), 35.5205, -77.1779, "Course text"),
}

_EXPORTS = {}


def export_of(name, spec=None):
    """The analysis export (the JSON's mapping) for one of EXPORT_CHARTS, or
    for `spec` (date, (hour, minute), latitude, longitude, depth), at a
    fixed target date so the run reads the same years whenever it runs."""
    if name not in _EXPORTS:
        from datetime import time
        date, (hh, mm), lat, lon, depth = spec or EXPORT_CHARTS[name]
        at = make_app(date=date, page="fardar")
        at.session_state["time_input_key"] = time(hh, mm)
        at.session_state["manual_lat_key"] = lat
        at.session_state["manual_lon_key"] = lon
        at.session_state["_reading_depth"] = depth
        at.session_state["_target_mode"] = "Date"
        at.session_state["_target_date"] = TARGET
        at.session_state["_life_lords_ascendant"] = True
        at.run(timeout=300)
        assert_no_exception(at, name)
        _EXPORTS[name] = at.session_state["_analysis_export"]
    return _EXPORTS[name]


def export_texts(analysis, export_cell, header_tables):
    """Every text the Markdown and HTML exports print, with what stands over
    it: (where, text, the heading and caption over it, the column over it).
    Cells read through the exports' own printer."""
    out = []
    for title, rows in header_tables(analysis):
        for row in rows:
            for col, value in row.items():
                out.append((f"{title} / {col}", export_cell(value), title, col))
    for page, headings in analysis["results"].items():
        for heading, entries in headings.items():
            for entry in entries:
                caption = entry.get("citation") or ""
                over = f"{heading}\n{caption}"
                # A heading or a caption that names a work anywhere covers its
                # own locators: "the caption already names the work".
                out.append((f"{page} / heading", heading, over, ""))
                if caption:
                    out.append((f"{page} / {heading} / caption", caption, over, ""))
                if entry.get("label") is not None:
                    out.append((f"{page} / {heading} / label", export_cell(entry["label"]), over, ""))
                for row in entry["rows"]:
                    for col, value in row.items():
                        out.append((f"{page} / {heading} / column", str(col), over, ""))
                        out.append((f"{page} / {heading} / {col}", export_cell(value), over, str(col)))
    return out


# Bare by the owner's ruling 115: the Revolutions count line names the II.3
# table by its chapter ("... governor, II.3, shifts"). The page's opening
# caption names PN IV, and so does the II.3 table's heading the line points
# to; "PN IV " there would take the line from 400 characters to 406, past the
# caption's ceiling (pn4_count_line). The export's target table carries it.
RULED_BARE = {("The target / Value", "II.3"): "ruling 115"}


def bare_locators(texts):
    """(where, locator, the text around it) for every locator that neither
    names its work earlier in its sentence nor stands under a heading,
    caption or column that names one."""
    bare = set()
    for where, text, over, column in texts:
        if WORK.search(over) or WORK.search(column):
            continue
        for m in LOC.finditer(text):
            if (where, m.group(0)) in RULED_BARE:
                continue
            if not names_its_work(text, m):
                lo = max(0, m.start() - 60)
                bare.add((where, m.group(0), " ".join(text[lo:m.end() + 30].split())))
    return sorted(bare)


@pytest.mark.parametrize("name", list(EXPORT_CHARTS))
def test_r01_every_locator_the_export_prints_names_its_work_or_stands_under_one_that_does(engine, name):
    texts = export_texts(export_of(name), engine["_export_cell"], engine["export_header_tables"])
    assert len([t for t in texts if LOC.search(t[1])]) > 50, "premise: the export prints locators"
    bare = bare_locators(texts)
    assert bare == [], f"{len(bare)} bare locator(s) in the export:\n  " + "\n  ".join(
        f"{w} :: {loc!r} :: {ctx}" for w, loc, ctx in bare[:80])


# --- R03: a caption naming one work does not cover another's locator -----------

def assigned_work(text, m, over, column=""):
    """The work a reader assigns to the locator `m`: the one named at once
    after it, else the last one named earlier in its sentence, else the one
    its column, heading or caption names; None where nothing names one."""
    after = _NAMED_RIGHT_AFTER.match(text, m.end())
    if after:
        return WORK.search(after.group(0)).group(0)
    before = list(WORK.finditer(_open_part(text, sentence_start(text, m.start()), m.start())))
    if before:
        return before[-1].group(0)
    named = WORK.search(column) or WORK.search(over)
    return named.group(0) if named else None


# Each locator below was read in the corpus in the work named beside it (the
# lane's report, PWR_BUILD.md, gives the file and line of each): printed in
# the export under a heading, caption or sentence that names another work,
# or none, it names its own.
GI, PN4, NAT, ITA = r"Gr\. ?Intr\.|Great Introduction", r"PN ?IV", r"On Nativities", r"\bITA\b"
R03_WORKS = {
    "VII.6, 52": GI,          # the Weakness table's 99, under Sahl's The Introduction
    "VII.2, 44": GI,          # the solar-phase note, in the II.3 table and the dignity table
    "VI.4, 4-6": GI,          # II.3's fn 37: loving, hating, hostile
    "IX.2, 33": PN4,          # II.3's fn 38: one belt
    "V.20": GI,               # II.3's fn 39, 41: bright and dark degrees
    "VI.2, 4": PN4,           # Dykes's fn 14 to it, beside Sahl's 2.11-2.19 in the life lords
    "2.11, 2": NAT, "2.11, 4": NAT, "2.13, 39": NAT, "2.19, 5": NAT,
    "8.6, 1": NAT, "1.37, 1": NAT, "1.37, 3": NAT, "3.11, 2": NAT, "3.11, 3": NAT, "3.11, 4": NAT,
    "4.14, 1": NAT, "7.1, 141": NAT, "9.5, 3": NAT, "9.5, 73": NAT, "10.2.5, 4-14": NAT, "11.1, 29": NAT,
    "VIII.3, 11": GI, "VIII.3, 14": GI, "VIII.3, 37": GI, "VIII.3, 40": GI, "VIII.4, 23-24": GI,
    "VIII.6, 14": GI, "VIII.6, 69": GI, "VIII.7, 5": GI,
    "I.57b": ITA, "I.16c": ITA,
    "VII.6, 27": GI,          # the eastern rule's label in the readings in force
    "1.30, 71": NAT,          # the releaser's Why, after "Introduction 2, 37-44" (the check of 677910b, 7)
    "III.13": r"Mathesis",    # Dykes's notes summarizing Rhetorius, "III.13 fn 284", after "Rhetorius"
}


# The forms a work's citations take in this app: On Nativities a dotted
# chapter ("1.30, 71"); the roman-numbered works a roman book and chapter;
# Sahl's The Introduction, On Choices, Abu 'Ali's chapters and Rhetorius a
# "Ch." A locator that continues a sentence after a work named before it is
# read as that work's (a list after a named work continues it), so its form
# must be one that work takes: "Introduction 2, 37-44; 1.30, 71" read 1.30,
# 71 as The Introduction's, which has no 1.30 (the check of 677910b,
# finding 7).
_FORMS = (
    (re.compile(r"\d"), re.compile(r"On Nativities")),
    (re.compile(r"[IVX]"), re.compile(
        r"Gr\. ?Intr\.|Great Introduction|\bPN ?(?:IV|I{1,3})\b|Persian Nativities|Mathesis|Firmicus|Carmen|"
        r"\bAbbr\.|Valens|Anthologies|\bBA\b|Book of Aristotle|\bTBN\b|Book of (?:the )?Nativities|\bITA\b|"
        r"Tetrabiblos|Almagest|Abu Bakr|Morin|Astrologia Gallica")),
    (re.compile(r"Ch"), re.compile(
        r"\bIntroduction\b|\bIntro\b|On Nativities|Choices|\bJN\b|Judgments of Nativities|Rhetorius|"
        r"On Questions|On Times")),
)


def form_misfits(texts):
    """(locator, the work named before it, the text around it) for every
    locator that continues a sentence after another work named in it and
    has a form that work's citations never take."""
    out = set()
    for _where, text, _over, _column in texts:
        for m in LOC.finditer(text):
            if _NAMED_RIGHT_AFTER.match(text, m.end()):
                continue
            before = list(WORK.finditer(_open_part(text, sentence_start(text, m.start()), m.start())))
            if not before:
                continue
            takes = next(work for form, work in _FORMS if form.match(m.group(0)))
            if not takes.search(before[-1].group(0)):
                lo = max(0, m.start() - 60)
                out.add((m.group(0), before[-1].group(0), " ".join(text[lo:m.end() + 30].split())))
    return sorted(out)


def misassigned(texts):
    """(locator, the work a reader would assign, the text around it) for every
    R03_WORKS locator the export prints under another work, or none."""
    out = set()
    for _where, text, over, column in texts:
        for m in LOC.finditer(text):
            want = R03_WORKS.get(m.group(0))
            if want is None:
                continue
            got = assigned_work(text, m, over, column)
            if got is None or not re.fullmatch(want, got):
                lo = max(0, m.start() - 60)
                out.add((m.group(0), got, " ".join(text[lo:m.end() + 30].split())))
    return sorted(out, key=str)


def test_r03_a_locator_continuing_another_works_sentence_has_that_works_form(engine):
    texts = [t for name in EXPORT_CHARTS
             for t in export_texts(export_of(name), engine["_export_cell"], engine["export_header_tables"])]
    continuing = [(t, m) for _w, t, _o, _c in texts for m in LOC.finditer(t)
                  if not _NAMED_RIGHT_AFTER.match(t, m.end()) and named_before(t, m.start())]
    assert len(continuing) > 100, "premise: locators continue sentences that name a work"
    misfits = form_misfits(texts)
    assert misfits == [], "\n  ".join(f"{loc!r} after {work!r} :: {ctx}" for loc, work, ctx in misfits[:40])


def test_r03_a_locator_under_another_works_caption_names_its_own_work(engine):
    texts = [t for name in EXPORT_CHARTS
             for t in export_texts(export_of(name), engine["_export_cell"], engine["export_header_tables"])]
    printed = {m.group(0) for _w, text, _o, _c in texts for m in LOC.finditer(text)}
    assert set(R03_WORKS) <= printed, f"premise: the export prints them all: {set(R03_WORKS) - printed}"
    wrong = misassigned(texts)
    assert wrong == [], "\n  ".join(f"{loc!r} read as {got!r} :: {ctx}" for loc, got, ctx in wrong[:60])


# --- The wording items PWN left ---------------------------------------------------

def _export_at(date, hhmm, lat, lon, depth="Course text"):
    spec = (date, hhmm, lat, lon, depth)
    return export_of(spec, spec)


# GV's check, F12: _pn4_looks_at_sign names a planet in the sign "in it", and
# the governor's facts and II.3's lord rows printed it "<planet> by in it".
# 1542-07-09 10:33 LMT, 31.3183 N 22.9819 W: Mars stands in the governor
# Venus's sign at the root, and in the II.3 lord's.
def test_gv_f12_an_infortune_in_the_sign_is_printed_in_it_not_by_in_it(engine):
    texts = [t for _w, t, _o, _c in export_texts(_export_at("1542-07-09", (10, 33), 31.3183, -22.9819),
                                                  engine["_export_cell"], engine["export_header_tables"])]
    assert any("infortunes looking: Mars" in t for t in texts), "premise: the governor's facts print"
    assert not [t for t in texts if "by in it" in t], [t[:200] for t in texts if "by in it" in t][:3]
    assert any("infortunes looking: Mars in it" in t for t in texts)
    assert any(t == "Mars in it" for t in texts), "the II.3 lord's row: the infortune in its sign"


# KT3's check, note 3: the wheel's panel lists the Sun's "Above the earth",
# read by the chart's sect (ruling 88), beside the Sect table's "Above
# horizon", his centre, and nothing on the panel told the two apart. The
# panel's own caption now says which (on ruling 88 and KT3's note 3).
def _florence_day(engine):
    from datetime import datetime, timedelta
    local = datetime(1240, 5, 23, 14, 30)
    chart = engine["calculate_traditional_chart"](local - timedelta(hours=FLORENCE[1] / 15.0), *FLORENCE)
    accidental = engine["evaluate_accidental_dignities"](
        chart["planetary_data"], chart["houses"], chart["sect"], chart["julian_day"],
        armc=chart["armc"], obliquity=chart["obliquity"], geo_lat=FLORENCE[0])
    return chart, accidental


def test_kt3_note_3_the_panel_says_the_suns_above_the_earth_is_the_charts_sect(engine):
    chart, accidental = _florence_day(engine)
    assert chart["sect"] == "Diurnal" and accidental["Sun"]["Above the earth"] is True, "premise: a day chart"
    sun = engine["point_summary"]("Sun", chart, {}, accidental, [], [], [], [])
    assert "Above the earth" in [r["Condition"] for r in sun["accidental"]], "premise: the panel lists it"
    note = sun.get("accidental_note", "")
    assert "the chart's sect" in note and "his visible disk" in note and "centre" in note, note
    above = [p for p in chart["planetary_data"] if p not in ("Sun", "North Node")
             and accidental.get(p, {}).get("Above the earth") is True]
    assert above, "premise: another body above the earth"
    assert engine["point_summary"](above[0], chart, {}, accidental, [], [], [], []).get("accidental_note") == ""
    from conftest import app_source
    assert "summary['accidental_note']" in app_source(), "the panel's caption carries the note"


# PWN's check, finding 7: Sahl's banishment line printed "12.0° from exact"
# for a gap of 12.0001 beside "outside Moon's light of 12°" (12 is inside it).
def test_pwn_check_7_the_banishment_near_miss_prints_past_the_light_it_is_outside(engine):
    import test_pwn_printed_numbers_2026_10_07 as pwn
    # The Moon at 10 Cancer, Saturn 12.0001 degrees on; every other planet
    # in a sign averse to Cancer (Gemini, Leo, Sagittarius, Aquarius).
    far = {"Sun": (80.0, 1.0), "Mercury": (70.0, 1.2), "Venus": (130.0, 1.2), "Mars": (250.0, 0.6),
           "Jupiter": (310.0, 0.1)}
    rows = engine["evaluate_sahl_banishment"](pwn._pdata(Moon=(100.0, 13.0), Saturn=(112.0001, 0.03), **far))
    moon = next(r["Closest configured planet"] for r in rows if r["Planet"] == "Moon")
    assert "outside Moon's light of 12°" in moon, "premise: the near-miss names the Moon's light"
    assert "12.0° from exact" not in moon and "12.01° from exact" in moon, moon


# PWN's check, finding 10: a light Venus or Mercury separating in one sign is
# "under a single blanket" inside her 7 degrees and "Separated" at 7 (Sahl's
# profile); PWN's shared rule prints 6.9999 as 06° 59', never 07° 00' beside
# the blanket. A guard: it passes on 87e9231 and fails on face757.
@pytest.mark.parametrize("light", ["Venus", "Mercury"])
def test_pwn_check_10_a_blanket_a_hair_inside_seven_degrees_prints_inside_them(engine, light):
    import test_pwn_printed_numbers_2026_10_07 as pwn

    def row(gap):
        data = pwn._pdata(Saturn=(10.0, 0.03), **{light: (10.0 + gap, 1.2)})
        return next((r["Exact Orb Dist"], r["Connection"]) for r in engine["evaluate_ptolemaic_aspects"](data)
                    if {r["Light Planet"], r["Heavy Planet"]} == {light, "Saturn"})
    assert row(6.9999) == ("06° 59'", "Under a single blanket")
    assert row(7.0) == ("07° 00'", "Separated")


# --- Ruling 116: Sahl's sentences in the column headed with Judgments of Nativities ---

JN_COLUMN = "Where On Nativities 1.20 is silent or conditional: Abu 'Ali, Judgments of Nativities Ch. 3"
SAHL_SENTENCE = re.compile(r"(?<![\w.])1\.2[01], \d+")


def test_ruling_116_sahls_sentences_under_the_jn_column_name_on_nativities(engine):
    cells = [engine["_export_cell"](row[column])
             for name in ("2005-11-17", "2017-02-27")
             for entry in export_of(name)["results"]["Prediction"]["Planetary years"]
             for row in entry["rows"] for column in row if column.startswith(JN_COLUMN)]
    quoted = [(cell, m) for cell in cells for m in SAHL_SENTENCE.finditer(cell)]
    assert len(quoted) >= 2, "premise: the column quotes Sahl's 1.20 in a lunar alternative"
    bare = [cell[max(0, m.start() - 40):m.end()] for cell, m in quoted
            if not cell[:m.start()].endswith("On Nativities ")]
    assert bare == [], bare
