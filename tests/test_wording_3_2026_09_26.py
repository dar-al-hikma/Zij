"""Engine wording, third pass (2026-09-26): page text and comments that
credit each figure to the sentence that gives it.

1. The Governor candidates caption: the eastern preference is
   sahl_eastern_1_22's first level -- 6 degrees for Saturn and Jupiter
   (On Nativities 1.22, 1), 15 for Mars (Dykes's fn 174 on 1.22, 3: Sahl
   gives Mars only his easternizing at 18), and 12 degrees and direct for
   Venus and Mercury (1.22, 7) -- not 1.22, 1 alone, and not Sahl's for Mars.
2. Sahl's banishment, the applying near-miss: the lights are Sahl's
   The Introduction Ch. 3, 13-18 ("by the extent of these lights, they are
   connected"), and 19 carries them across signs; the branch also covers a
   pair in one sign, so it cites 13-19, not 19.
3. Gr. Intr. V.18, 1 is quoted as the page prints it, "2 ½ degrees"; the
   two paraphrases of PN IV IX.7, 37 ("2 ½ days for every sign") follow
   their page too.
4. The Planetary Condition label for the Sun's reception of the Moon
   (Gr. Intr. VII.5, 137-138): a reception by nature, not into a dignity,
   so it no longer reads "Receives Moon into its own her glow is from him".
   With his claim where she stands it is 138's two receptions, "by nature
   and by sign"; from the opposition it keeps 137's "detestable".
5. The Planetary Condition reason, when Mercury's sect and a connection are
   both open, says "the heuristic class" once.
6. Where the house-master's direction is refused (above the polar circle),
   the page draws the revolution table the two exports already carry: its
   three rows give the house-master's place in the revolution (1.23, 3) and
   say that 1.23, 4 is not asked because the direction is refused.
7. The testimony-84 comment credits "rise out of the rays" to Dykes's
   chapter comment (Sahl I p. 303) beside fns 172 and 174, and calls the
   glossary's sense (2) the strict sense that 84's floors relax.
8. evaluate_blocking's docstring: the third-party blocking runs 38-43,
   43 being the worked verdict ("he is cutting the aspect").
"""
import ast
from pathlib import Path

import pytest

from corpus_paths import corpus_file, page_marker
from skip_guard import needs_corpus

ENGINE_DIR = Path(__file__).resolve().parent.parent
APP = ENGINE_DIR / "app.py"


def _strings(path):
    return [n.value for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(n, ast.Constant) and isinstance(n.value, str)]


GOVERNOR_CAPTION = (
    "Sahl, On Nativities 1.7, 3-7; the eastern preference reads the allowance by which Sahl's Saturn and "
    "Jupiter are \"considered to be eastern\" (1.22, 1), Dykes's 15\u00b0 for Mars (fn 174 on 1.22, 3), and 1.22, 7 for Venus "
    "and Mercury.")


def test_the_governor_caption_names_each_planets_sentence():
    strings = _strings(APP)
    assert GOVERNOR_CAPTION in strings
    assert not any(s.endswith("\"considered eastern\" allowance (1.22, 1).") for s in strings)


def test_the_eastern_qualification_note_credits_the_same_witnesses():
    notes = [s for s in _strings(APP) if s.startswith("This column applies an interpretation of Sahl's On Nativities 1.22 to 1.7")]
    assert len(notes) == 1
    assert ("This column's measure is the allowance by which Sahl's Saturn and Jupiter in On Nativities are \"considered to be "
            "eastern\" (1.22, 1), Dykes's 15\u00b0 for Mars (fn 174 on 1.22, 3), and 1.22, 7 for Venus and "
            "Mercury, not the figures for \"the power of easternization\" in 1.22, 6") in notes[0]
    assert "(1.22, 1; Dykes's table)" not in notes[0]


def test_the_governor_caption_follows_the_rule_it_describes(engine):
    rule = engine['sahl_eastern_1_22']
    sources = {p: rule(p, 0.0, 30.0, 1.0).level1.source for p in ('Saturn', 'Jupiter', 'Mars', 'Venus', 'Mercury')}
    assert sources['Saturn'] == sources['Jupiter'] == 'Sahl, On Nativities 1.22, 1; fn 172'
    assert sources['Mars'] == 'Sahl, On Nativities 1.22, 3; Dykes fn 174'
    assert sources['Venus'] == sources['Mercury'] == 'Sahl, On Nativities 1.22, 7'


def _pdata(**positions):
    return {name: {"longitude": float(lon), "latitude": 0.0, "distance": 1.0, "speed_in_lon": float(speed),
                   "speed_in_lat": 0.0, "speed_in_dist": 0.0} for name, (lon, speed) in positions.items()}


def test_the_applying_near_miss_cites_the_lights_and_19(engine):
    # Moon 0 Aries applying to Saturn 20 Aries (one sign), and to Mars 29 Leo
    # (across signs): both outside the Moon's light of 12.
    for other, lon, speed, aspect, distance in (("Saturn", 20, 0.03, "conjunction", "20.0"),
                                                ("Mars", 149, 0.7, "trine", "29.0")):
        rows = engine["evaluate_sahl_banishment"](_pdata(Moon=(0, 13.0), **{other: (lon, speed)}))
        moon = next(r for r in rows if r["Planet"] == "Moon")["Closest configured planet"]
        assert moon == (f"{other}: {aspect} by sign, {distance}\u00b0 from exact and applying, "
                        "outside Moon's light of 12\u00b0 (Sahl 13-19)")


def test_the_twelfth_part_quote_is_as_printed(engine):
    doc = engine['_twelfth_part_sign'].__doc__
    assert 'each division is 2 \u00bd degrees" (1)' in ' '.join(doc.split()) and "2 1/2" not in doc
    month = engine['pn4_ix7_month_days'].__doc__
    assert "2 \u00bd days" in month and "2 1/2" not in month


GI = corpus_file("gr_intr/abu_mashar_great_introduction.md")
PN4 = corpus_file("pn4/pn4_complete/persian_nativities_iv.md")


@needs_corpus(GI, PN4)
def test_the_pages_print_the_half():
    assert "so that each division is 2 \u00bd degrees" in GI.read_text(encoding="utf-8")
    assert "a day for every 12\u00b0, and 2 \u00bd days for every sign" in PN4.read_text(encoding="utf-8")


FLORENCE = (43.7792, 11.2463)


def _sun_receives_moon(E, days):
    lat, lon = FLORENCE
    jd = E.civil_local_to_jd_ut(1957, 8, 17, 12, lon / 15) + days
    chart = E.calculate_traditional_chart_jd(jd, lat, lon)
    p, sect = chart["planetary_data"], chart["sect"]
    essential = E.evaluate_essential_dignities(p, sect)
    accidental = E.evaluate_accidental_dignities(p, chart["houses"], sect, chart["julian_day"],
                                                 armc=chart["armc"], obliquity=chart["obliquity"], geo_lat=lat)
    sim = E._simulate_forward(p, chart["julian_day"])
    sun = E.evaluate_abu_mashar_condition(p, chart["houses"], sect, essential, accidental,
                                          chart["julian_day"], chart["ascendant"], sim)["Sun"]
    # The opposition's row is a Negative Label since the owner's ruling of
    # 2026-09-27 (test_reception_137_negative_2026_09_27); its wording is
    # this test's.
    labels = [label for label in list(sun["Positive Labels"]) + list(sun["Negative Labels"])
              if label.startswith("Receives Moon")]
    labels += [u.reason for u in sun["Unresolved Positive Labels"] if u.reason.startswith("Receives Moon")]
    return labels


@pytest.mark.parametrize("days, label", [
    (0, "Receives Moon by nature: her glow is from him"),
    (8, "Receives Moon by nature and by sign: her glow is from him, and he has a claim where she stands"),
    (4, "Receives Moon by nature: her glow is from him (signs in aversion; 137 says from all signs)"),
    (6, "Receives Moon by nature and by sign: her glow is from him, and he has a claim where she stands "
        "(signs in aversion; 137 says from all signs)"),
    (22, "Receives Moon by nature, from the opposition: detestable (137)"),
])
def test_the_suns_reception_of_the_moon_reads_as_a_sentence(days, label):
    import engine as E
    labels = _sun_receives_moon(E, days)
    # The 137-138 row is the one label not into a dignity; a dignity
    # reception of the Moon (day 8: his face) keeps "into its own".
    assert [x for x in labels if not x.startswith("Receives Moon into its own ")] == [label]
    assert all(x.split("into its own ")[1].split(",")[0].strip() in ("domicile", "house", "exaltation", "triplicity",
                                                                     "bound", "face")
               for x in labels if x.startswith("Receives Moon into its own "))


def test_the_condition_reason_names_the_heuristic_class_once():
    """A constructed chart: Florence, 1240-01-14 01:39 UT, with Mercury
    moved onto the Sun (the one case in which his sect is unassigned),
    retrograde, and Venus 2 degrees behind the two of them, equally placed,
    so that her connection is undecided and one outcome's class is itself
    open under Mercury's sect."""
    import engine as E
    lat, lon = FLORENCE
    jd = E.civil_local_to_jd_ut(1240, 1, 1, 12, lon / 15) + 14 * 0.9
    chart = E.calculate_traditional_chart_jd(jd, lat, lon)
    p, sect = chart["planetary_data"], chart["sect"]
    sun = p["Sun"]["longitude"]
    p["Mercury"].update(longitude=sun, speed_in_lon=-0.5)
    p["Venus"].update(longitude=(sun - 2.0) % 360.0, speed_in_lon=1.2)
    essential = E.evaluate_essential_dignities(p, sect)
    accidental = E.evaluate_accidental_dignities(p, chart["houses"], sect, chart["julian_day"],
                                                 armc=chart["armc"], obliquity=chart["obliquity"], geo_lat=lat)
    sim = E._simulate_forward(p, chart["julian_day"])
    condition = E.evaluate_abu_mashar_condition(p, chart["houses"], sect, essential, accidental,
                                                chart["julian_day"], chart["ascendant"], sim)["Mercury"]["Condition"]
    assert E.is_unresolved(condition)
    assert condition.reason == (
        "the heuristic class is evaluated under both Mercury-sect alternatives; and it depends on an unresolved "
        "connection between Sun and Mercury and Venus (equally placed first bodies; no priority is supplied)")
    assert condition.reason.count("the heuristic class") == 1
    assert condition.alternatives == (("permitted outcome 1", "Indeterminate"),
                                      ("permitted outcome 2, if Mercury is diurnal", "Good"),
                                      ("permitted outcome 2, if Mercury is nocturnal", "Indeterminate"))


HIGH = (69.65, 18.96)          # above the polar circle: the direction is refused
REFUSED = "not asked: the direction is refused at this latitude"
REVOLUTION_FACTS = ["Burned at the revolution", "Burned later in the year, in a stake of the Ascendant of the year"]


def _high(page):
    import html
    from conftest import assert_no_exception, make_app
    at = make_app(page=page)
    at.session_state["manual_lat_key"], at.session_state["manual_lon_key"] = HIGH
    at.session_state["_target_date"] = "1273-06-15"
    at.run(timeout=300)
    assert_no_exception(at, f"{page} at {HIGH}")
    return at


def test_a_refused_direction_draws_the_revolution_rows_the_exports_carry():
    at = _high("releaser")
    assert any("as every direction by the oblique ascension is" in w.value for w in at.main.warning)
    tables = [df.value for df in at.main.dataframe
              if "Fact" in df.value.columns and "Burned at the revolution" in list(df.value["Fact"])]
    assert len(tables) == 1
    drawn = tables[0].astype(str).to_dict("records")
    assert [r["Fact"] for r in drawn] == ["Jupiter in the revolution"] + REVOLUTION_FACTS
    assert [r["Reads"] for r in drawn[1:]] == [REFUSED, REFUSED]
    assert [r["Source"] for r in drawn] == ["1.23, 3", "1.23, 4", "1.23, 4; fn 183"]
    assert drawn[0]["Reads"].endswith("(natal 20\u00b0 Ari 52')")
    shown = [m.value for m in at.main.markdown]
    assert ("With the direction refused, 1.23, 4 is not asked in the revolution's year (age 33). "
            "The house-master in the revolution (1.23, 3):") in shown

    import html
    exported = _high("sources")
    results = exported.session_state["_analysis_export"]["results"]
    entries = [entry["rows"] for page in results.values() for heading, found in page.items()
               if heading.startswith("The house-master directed") for entry in found]
    assert [{k: str(v) for k, v in row.items()} for row in drawn] in \
        [[{k: str(v) for k, v in row.items()} for row in rows] for rows in entries]
    md = exported.session_state["_analysis_markdown"]
    page = html.unescape(exported.session_state["_analysis_html"])
    for text in (md, page):
        for row in drawn:
            assert row["Fact"] in text and row["Reads"] in text, row


def _comment_text():
    from conftest import engine_source
    return " ".join(line.strip().lstrip("#").strip()
                    for line in engine_source().splitlines()          # every engine module
                    if line.strip().startswith("#"))


def test_the_testimony_84_comment_names_the_chapter_comment_and_the_strict_sense():
    text = _comment_text()
    assert ("which per 1.22 fns 172 and 174 and the chapter comment, Sahl I p. 303, still lie inside the rays"
            in text)
    assert ('and invisible (western)": the strict sense, which 84\'s "considered eastern" floors relax.' in text)


@needs_corpus(corpus_file('on_nativities.md'))
def test_the_chapter_comment_is_on_p_303():
    text = corpus_file("on_nativities.md").read_text(encoding="utf-8")
    page = text.split(page_marker("Sahl I", 303), 1)[1].split(page_marker("Sahl I", 304), 1)[0]
    assert "after seven days they will rise out of the rays" in page


def test_the_blocking_docstring_includes_the_worked_verdict(engine):
    doc = " ".join(engine["evaluate_blocking"].__doc__.split())
    assert "The third-party blocking of 38-43 and VII.5, 93-94 is conditional" in doc
    assert "38-42" not in doc


@needs_corpus(corpus_file('sahl_introduction_ch3.md'))
def test_43_is_the_worked_verdict():
    text = corpus_file("sahl_introduction_ch3.md").read_text(encoding="utf-8")
    assert "43 Now Mars was greater in degrees than the Moon, and he is cutting the aspect" in text


def test_the_moons_middle_years_are_printed_as_i_8_12_prints_them():
    strings = _strings(APP)
    assert ("The Moon's 4 is a tenth of her middle years, 39 \u00bd (I.8, 12) -- an independent witness for the "
            "luminary construction of the middle years used elsewhere in this app.") in strings
    assert not any("39 1/2 (I.8, 12)" in s for s in strings)


@needs_corpus(PN4)
def test_i_8_12_prints_the_half():
    assert "when her middle years are 39 \u00bd," in PN4.read_text(encoding="utf-8")
