"""The stars harming eyes, at their places, beside the ranges as printed.

Each object Dykes identifies (Gr. Intr. Fig. 88 with VI.20's notes, Sahl I Fig. 59)
has one row. The table is read by the catalogue's designation, cites each volume by
name, tests nothing against the chart, and leaves the ranges as the texts print them.
"""
import inspect
import re
import sys

import pytest

import engine
from conftest import assert_no_exception, make_app
from corpus_paths import corpus_file
from skip_guard import skip_without_corpus

FIRST, SECOND = engine.READING_DEPTH_OPTIONS
JD = 2461120.5
HEADING = "Stars harming eyes"
SENTENCE = "The places come from today's catalogue at this chart's moment; the ranges are as printed."
NO_ROW = {"Melotte 111": "melotte:111", "NGC 6441": "ngc:6441", "τ Cap": "hip:101923", "κ Cap": "hip:107188"}
VOLUMES = ("Gr. Intr. Fig. ", "Gr. Intr. VI.20", "Carmen IV.2, ", "Rhetorius Ch. 62", "Sahl I Fig. 59",
           "Sahl, On Nativities 6.2, ", "Abu Bakr, On Nativities II.7.3")
# Each row's own letter and the catalogue's key for it: a row joined by a name fails here.
LETTERS = {"etTau": "η", "alCom": "α", "beCom": "β", "gaCom": "γ", "be-1Sco": "β", "deSco": "δ", "piSco": "π",
           "laSco": "λ", "upSco": "υ", "gaSgr": "γ", "upCap": "υ", "epCap": "ε", "gaAqr": "γ", "ze-1Aqr": "ζ",
           "etAqr": "η", "piAqr": "π"}


# Each row's label and the key that places it: two stars of one letter swap past LETTERS, not past this.
LABELS = {"etTau": "Pleiades (in Taurus), esp. η (Alcyone)", "M44": "Praesepe (in Cancer): M44 or MCG 2632",
          "alCom": "Coma Berenice (near Tail of Leo): α", "beCom": "Coma Berenice (near Tail of Leo): β",
          "gaCom": "Coma Berenice (near Tail of Leo): γ", "be-1Sco": "Forehead, eyes of Scorpio: β, Acrab/Graffias",
          "deSco": "Forehead, eyes of Scorpio: δ, Dschubba", "piSco": "Forehead, eyes of Scorpio: π Scorpionis",
          "laSco": "Sting of Scorpio: λ, Shaula", "upSco": "Sting of Scorpio: υ, Lesath",
          "HR6630": "Nebula by sting? (Scorpio): G Sco", "gaSgr": "Tip of Archer's arrow: γ², al-Nasl",
          "upCap": "Spines of Capricorn: υ", "epCap": "Spines of Capricorn: or ε", "gaAqr": "Pour of Aquarius: γ",
          "ze-1Aqr": "Pour of Aquarius: ζ", "etAqr": "Pour of Aquarius: η", "piAqr": "Pour of Aquarius: π"}
EYE_CLAUSE = "The places harming the eyesight show all their texts at both settings."


def row_of(result, part):
    found = [row for row in result["rows"] if part in row["Star"]]
    assert len(found) == 1, (part, found)
    return found[0]


@pytest.fixture(scope="module")
def placed():
    stars, _ = engine.fixed_star_places(JD)
    assert stars, "the catalogue must be attached"
    return {star.designation: star for star in stars}


# ---------------------------------------------------------------- the rows


def test_one_row_per_object_eighteen_keyed_four_without():
    assert len(engine.EYESIGHT_STARS) == 22
    keyed = [entry["key"] for entry in engine.EYESIGHT_STARS if entry["key"]]
    assert len(keyed) == len(set(keyed)) == 18
    assert {entry["named"]: entry["listed"] for entry in engine.EYESIGHT_STARS if not entry["key"]} == NO_ROW


def test_each_rows_label_stands_with_its_own_key():
    printed = {row["Catalogue designation"]: row["Star"] for row in engine.evaluate_eyesight_stars(JD)["rows"]}
    assert len(LABELS) == 18
    assert {key: printed[key] for key in LABELS} == LABELS and len(printed) == 22
    assert {entry["key"]: entry["star"] for entry in engine.EYESIGHT_STARS if entry["key"]} == LABELS


def test_every_key_is_one_catalogue_row_of_its_own_letter(placed):
    stars, _ = engine.fixed_star_places(JD)
    for entry in engine.EYESIGHT_STARS:
        if entry["key"]:
            assert sum(star.designation == entry["key"] for star in stars) == 1, entry["key"]
    for key, letter in LETTERS.items():
        assert engine.fixed_star_greek_form(key).startswith(letter), key
        entry = next(e for e in engine.EYESIGHT_STARS if e["key"] == key)
        assert letter in entry["star"], key


def test_the_name_trap_the_key_decides_and_the_list_file_stays(placed):
    """The list file names hip:60742 for the star of another row's name. β Com's row is
    the catalogue's row called Aldafirah, and γ Com's the row called Kissin."""
    assert placed["beCom"].catalogue_name == "Aldafirah" and placed["gaCom"].catalogue_name == "Kissin"
    entry = next(e for e in engine.fixed_star_list_file() if e["id"] == "hip:60742")
    assert (entry["name"], entry["row"]) == ("Al Dafīrah", "Kissin")
    result = engine.evaluate_eyesight_stars(JD)
    beta, gamma = row_of(result, "Tail of Leo): β"), row_of(result, "Tail of Leo): γ")
    assert beta["Catalogue designation"] == "beCom" and gamma["Catalogue designation"] == "gaCom"
    assert beta["Longitude"] == engine.get_degree_string(placed["beCom"].longitude)
    assert gamma["Longitude"] == engine.get_degree_string(placed["gaCom"].longitude)


@pytest.mark.parametrize("key", [*LETTERS, "M44", "HR6630"])
def test_a_place_is_the_catalogues_at_the_moment_given(key):
    other = JD + 36525.0                 # a century on: the place moves with the moment
    now, later = engine.fixed_star_places(JD)[0], engine.fixed_star_places(other)[0]
    star, then = (next(s for s in stars if s.designation == key) for stars in (now, later))
    entry = next(e for e in engine.EYESIGHT_STARS if e["key"] == key)
    row = row_of(engine.evaluate_eyesight_stars(JD), entry["star"])
    assert row["Longitude"] == engine.get_degree_string(star.longitude)
    assert row["Latitude"] == f"{star.latitude:+.2f}°".replace("-", "−")
    assert star.longitude != then.longitude
    assert row_of(engine.evaluate_eyesight_stars(other), entry["star"])["Longitude"] == engine.get_degree_string(then.longitude)


# ---------------------------------------------------------------- objects with no row


def test_the_four_take_their_places_from_the_grown_catalogue_itself():
    """No stub: the file's entries and the real rows, so that a list which fills while
    this table stays empty is seen here."""
    result = engine.evaluate_eyesight_stars(JD)
    stars = {engine.fixed_star_identity(star): star for star in engine.fixed_star_places(JD)[0]}
    entries = {entry["id"]: entry for entry in engine.fixed_star_list_file()}
    for part, listed in (("Melotte 111", "melotte:111"), ("NGC 6441", "ngc:6441"),
                         ("Spines of Capricorn: τ", "hip:101923"), ("Spines of Capricorn: or κ", "hip:107188")):
        row, star = row_of(result, part), stars[entries[listed]["row"]]
        assert row["Catalogue designation"] == star.designation != "no row"
        assert row["Longitude"] == engine.get_degree_string(star.longitude) != "not placed"
        assert row["Latitude"] == f"{star.latitude:+.2f}°".replace("-", "−")
    assert result["refused"] is None
    assert result["missing"] == "" and not [row for row in result["rows"] if "not placed" in row.values()]


def test_the_four_stand_in_the_list_file_with_an_added_row():
    entries = {entry["id"]: entry for entry in engine.fixed_star_list_file()}
    for listed in NO_ROW.values():
        assert (entries[listed]["list"], entries[listed]["match"]) == ("curated", "added") and entries[listed]["row"]


@pytest.mark.parametrize("name, listed, part", [
    ("Melotte 111", "melotte:111", "Melotte 111"), ("NGC 6441", "ngc:6441", "NGC 6441"),
    ("τ Cap", "hip:101923", "Spines of Capricorn: τ"), ("κ Cap", "hip:107188", "Spines of Capricorn: or κ")])
def test_an_object_fills_by_itself_when_its_entry_gets_a_row(monkeypatch, name, listed, part):
    """The file's entry and the catalogue's row are all that change: no table does."""
    stars, _ = engine.fixed_star_places(JD)
    row = engine.FixedStar(name="Stubbed", other_names=(), designation="stubDes", catalogue_name="Stubbed",
                           lookup="Stubbed", longitude=300.5, latitude=-1.25, right_ascension=1.0, declination=2.0)
    grown = tuple(dict(entry, row="Stubbed") if entry["id"] == listed else entry for entry in engine.fixed_star_list_file())
    monkeypatch.setattr(engine, "fixed_star_places", lambda jd: ((*stars, row), {}))
    monkeypatch.setattr(engine, "fixed_star_list_file", lambda: grown)
    result = engine.evaluate_eyesight_stars(JD)
    filled = row_of(result, part)
    assert filled["Catalogue designation"] == "stubDes"
    assert filled["Longitude"] == engine.get_degree_string(300.5)
    assert filled["Latitude"] == "−1.25°"
    assert name not in result["missing"]
    assert sum(r["Catalogue designation"] == "no row" for r in result["rows"]) == 0


def test_a_keyed_star_the_catalogue_cannot_read_keeps_its_key_and_is_said(monkeypatch):
    stars, _ = engine.fixed_star_places(JD)
    kept = tuple(star for star in stars if star.designation != "laSco")
    monkeypatch.setattr(engine, "fixed_star_places", lambda jd: (kept, {"Shaula": "unread"}))
    result = engine.evaluate_eyesight_stars(JD)
    row = row_of(result, "λ, Shaula")
    assert (row["Catalogue designation"], row["Longitude"], row["Latitude"]) == ("laSco", "not placed", "not placed")
    assert "laSco" in result["missing"]


def test_with_no_catalogue_every_object_is_named_and_the_refusal_stands(monkeypatch):
    monkeypatch.setattr(engine, "fixed_star_places", lambda jd: (None, {}))
    result = engine.evaluate_eyesight_stars(JD)
    assert len(result["rows"]) == 22
    assert all(row["Longitude"] == row["Latitude"] == "not placed" for row in result["rows"])
    assert result["refused"] == engine.fixed_star_refusal()
    assert result["missing"] == ""


# ---------------------------------------------------------------- witnesses


def test_every_witness_names_its_own_volume():
    for entry in engine.EYESIGHT_STARS:
        assert entry["witnesses"]
        for locator in entry["witnesses"]:
            assert locator.startswith(VOLUMES), locator


def test_no_course_citation_and_the_chapter_is_sixty_two():
    text = repr(engine.evaluate_eyesight_stars(JD))
    assert not re.search(r"Lesson|[Cc]ourse|Fig\. 8\b|Ch\. 61", text)
    for entry in engine.EYESIGHT_STARS:
        for locator in entry["witnesses"]:
            if locator.startswith("Carmen"):
                assert locator.endswith("(2nd ed.)"), locator


@pytest.mark.parametrize("part, words", [
    ("Sting of Scorpio: λ", "Gr. Intr. Fig. 88 [3] (Shaula & Lesath?)"),
    ("Sting of Scorpio: υ", "Gr. Intr. Fig. 88 [3] (Shaula & Lesath?)"),
    ("G Sco", "Gr. Intr. Fig. 88 [4] (G Sco + Cglo 6441?)"),
    ("NGC 6441", "Gr. Intr. Fig. 88 [4] (G Sco + Cglo 6441?)"),
    ("or ε", "Sahl I Fig. 59 (ε, κ Capricorni?)"),
    ("or κ", "Sahl I Fig. 59 (ε, κ Capricorni?)"),
    ("Pour of Aquarius: ζ", "Sahl I Fig. 59 (ζ Aquarii?)")])
def test_a_query_of_dykess_stays_his(part, words):
    assert words in row_of(engine.evaluate_eyesight_stars(JD), part)["Witnesses"]


def test_holdens_note_is_kept_apart_where_it_names_other_stars():
    result = engine.evaluate_eyesight_stars(JD)
    for part in ("Pour of Aquarius: γ", "Pour of Aquarius: ζ", "Pour of Aquarius: η", "Pour of Aquarius: π", "esp. η"):
        assert "Holden's note names other stars" in row_of(result, part)["Witnesses"], part
    for part in ("Tail of Leo): α", "Tail of Leo): β", "Tail of Leo): γ"):
        assert "Rhetorius Ch. 62 (the Mane of Leo; Holden's note names 7 and 15 Com)" in row_of(result, part)["Witnesses"], part
    assert "Holden's note: Shaula" in row_of(result, "λ, Shaula")["Witnesses"]
    assert "Rhetorius" not in row_of(result, "υ, Lesath")["Witnesses"]


# ---------------------------------------------------------------- the ranges


def test_the_printed_table_is_untouched_and_the_legs_stand_as_printed():
    assert len(engine.EYESIGHT_PLACES) == 54
    legs = [row for row in engine.EYESIGHT_PLACES if row["source"] == "Gr. Intr. VI.20" and row["sentence"] == 6]
    assert [(row["sign"], row["lo"], row["hi"], row["printed"]) for row in legs] == [
        ("Scorpio", 20.0, 21.0, "Scorpio 20°"), ("Scorpio", 21.0, 22.0, "Scorpio 21° 10'")]
    assert all("leg of the Scorpion" in row["place"] for row in legs)


@pytest.mark.parametrize("part", ["λ, Shaula", "υ, Lesath", "G Sco", "NGC 6441"])
def test_the_legs_print_as_printed_and_the_correction_as_dykess(part):
    cell = row_of(engine.evaluate_eyesight_stars(JD), part)["As printed"]
    lines = cell.split("\n")
    assert lines[:2] == ["Gr. Intr.: Scorpio 20°", "Gr. Intr.: Scorpio 21° 10' (both printed for the leg; Dykes's correction, fns 278, 283)"]


def test_every_span_shown_is_a_row_of_the_printed_table():
    for entry in engine.EYESIGHT_STARS:
        assert entry["spans"], entry["star"]
        assert all(any(row is place for place in engine.EYESIGHT_PLACES) for row in entry["spans"]), entry["star"]


def test_the_chronic_illness_lists_stay_out_of_the_stars_rows():
    """Sahl's 61-68 are chronic illness's, overlapping the eye's (fn 80); Taurus's 64 he reads
    as the Hyades (fn 84), and Abu Bakr's Dafira at 18 Leo is Adhafera (fn 1028). Nawbakht
    names no star. They stay in the printed table and out of a star's row."""
    for entry in engine.EYESIGHT_STARS:
        for row in entry["spans"]:
            assert row["sentence"] not in (61, 62, 63, 64, 65, 66, 67, 68, 74), (entry["star"], row["printed"])
            assert row["printed"] != "Leo, the eighteenth", entry["star"]


@pytest.mark.parametrize("part, source, printed", [
    ("esp. η", "Gr. Intr.", "from 13° 36' Taurus to 14° 30'"), ("Praesepe", "Sahl", "Cancer, from 15° to 19°"),
    ("Tail of Leo): α", "Sahl", "Libra, from 27° 36' to 28°"), ("π Scorpionis", "Sahl", "Scorpio, the ninth and tenth"),
    ("λ, Shaula", "Sahl", "Scorpio, in 23"), ("γ², al-Nasl", "Gr. Intr.", "Sagittarius 15° 20'"),
    ("Spines of Capricorn: υ", "Gr. Intr.", "Capricorn 22°"), ("or ε", "Sahl", "Capricorn from 26° to 29°"),
    ("Pour of Aquarius: η", "Gr. Intr.", "from 20° 10' Aquarius to 24° 20'")])
def test_a_rows_range_is_its_own(part, source, printed):
    assert f"{source}: {printed}" in row_of(engine.evaluate_eyesight_stars(JD), part)["As printed"]


def test_the_range_fn_285_rules_out_stands_only_beside_the_neck_stars():
    result = engine.evaluate_eyesight_stars(JD)
    assert "Capricorn 22°" in row_of(result, "Capricorn: τ")["As printed"]
    assert "Capricorn 22°" not in row_of(result, "or ε")["As printed"]
    assert "Capricorn from 26° to 29°" not in row_of(result, "Capricorn: υ")["As printed"]


# ---------------------------------------------------------------- display only


def test_it_takes_a_moment_and_no_chart():
    assert list(inspect.signature(engine.evaluate_eyesight_stars).parameters) == ["jd"]
    columns = set(engine.evaluate_eyesight_stars(JD)["rows"][0])
    assert columns == {"Star", "As printed", "Longitude", "Latitude", "Catalogue designation", "Witnesses"}
    source = inspect.getsource(engine.evaluate_eyesight_stars)
    code = source.split('"""')[2]
    for word in ("Moon", "Sun", "ascendant", "Ascendant", "planetary", "orb", "eyesight_place_in_span"):
        assert word not in code, word


# ---------------------------------------------------------------- Antares


def test_antares_takes_the_form_of_alphecca_and_menkalinan():
    natures = dict(engine.SAHL_FIXED_STARS)
    assert natures["Antares"] == "Jupiter-Mars (Sahl, following al-Andarzaghar, adds it again as Mars-Venus, 2.2, 66, 70, fn 74)"
    for name in ("Alphecca", "Menkalinan", "Antares"):
        assert "(Sahl, following al-Andarzaghar, " in natures[name]


# ---------------------------------------------------------------- on the page


def page(date, depth):
    at = make_app(date=date, page="fixed-stars")
    at.session_state["_reading_depth"] = depth
    at.run()
    assert_no_exception(at, "fixed-stars")
    return at


def under_heading(at):
    """All the page draws from this table's heading to the next heading, tags gone."""
    drawn, inside = [], False
    for node in at.main:
        kind = getattr(node, "type", None)
        if kind == "subheader":
            inside = node.value == HEADING
        if inside and kind in ("subheader", "caption", "markdown", "warning"):
            drawn.append(str(node.value))
        elif inside and kind == "dataframe":
            drawn.append(node.value.to_csv())
    return "\n".join(drawn)


@pytest.mark.parametrize("depth", [FIRST, SECOND])
def test_the_finding_shows_at_both_depths_with_no_word_of_depth(depth):
    at = make_app(date="1240-05-25", page="delineations")
    at.session_state["_reading_depth"] = depth
    at.run()
    assert "Places harming the eyesight" in [node.value for node in at.subheader]
    help_of = next(node.help for node in at.subheader if node.value == "Places harming the eyesight")
    assert "supplement" not in help_of


@pytest.mark.parametrize("depth", [FIRST, SECOND])
def test_the_star_table_stands_under_its_heading_and_one_sentence(depth):
    text = under_heading(page("1240-05-25", depth))
    assert text.startswith(HEADING) and SENTENCE in text
    for piece in ("Catalogue designation", "Witnesses", "As printed", "Longitude", "Latitude", "esp. η (Alcyone)", "etTau", "NGC 6441",
                  "Rhetorius Ch. 62", "Gr. Intr. Fig. 88 [1]", "Sahl I Fig. 59"):
        assert piece in text, piece
    assert "no row" not in text and "so not placed" not in text


def test_with_no_catalogue_the_page_names_every_object_and_says_why(monkeypatch):
    at = make_app(date="1240-05-25", page="fixed-stars")
    at.session_state["_reading_depth"] = FIRST
    monkeypatch.setattr(sys.modules["engine"], "fixed_star_places", lambda jd: (None, {}))
    at.run()
    assert_no_exception(at, "fixed-stars")
    text = under_heading(at)
    assert f"Not computed: {engine.fixed_star_refusal()}." in text
    assert text.count("not placed") == 44
    assert "Not in the catalogue attached" not in text


def test_the_clause_stands_in_the_sources_line_and_the_settings_help_at_the_first_depth():
    at = make_app(date="1240-05-25", page="delineations")
    at.session_state["_reading_depth"] = FIRST
    captions = [node.value for node in at.run().caption]
    assert [line for line in captions if line.startswith("Sources shown:")] == [
        "Sources shown: Sahl's course texts. Abū Ma'shar's supplement is off; "
        f"switch it on under Sources and readings. {EYE_CLAUSE}"]
    at = make_app(date="1240-05-25", page="sources")
    at.session_state["_reading_depth"] = FIRST
    at.run()
    assert_no_exception(at, "sources")
    radio = next(node for node in at.radio if node.label == "Sources shown")
    assert f"On Nativities alone. {EYE_CLAUSE} With Abū Ma'shar's supplement:" in radio.help
    full = [node.value for node in at.markdown if node.value.startswith("**Sources shown** (this page)")]
    assert len(full) == 1 and f"elsewhere. {EYE_CLAUSE} With Abū Ma'shar's supplement:" in full[0]


def test_the_star_table_stands_where_no_point_stands_in_a_span():
    at = make_app(date="1240-05-23", page="delineations").run()
    assert "Places harming the eyesight" not in [node.value for node in at.subheader]          # premise: no span holds a point
    assert HEADING in [node.value for node in page("1240-05-23", FIRST).subheader]


@pytest.mark.parametrize("depth", [FIRST, SECOND])
def test_the_table_on_the_page_carries_no_course_and_no_lesson(depth):
    text = under_heading(page("1240-05-25", depth))
    assert text.startswith(HEADING)
    assert not re.search(r"Lesson|[Cc]ourse|Fig\. 8\b|Ch\. 61", text)


# ---------------------------------------------------------------- against the corpus


def corpus_text(name):
    path = corpus_file(name)
    skip_without_corpus(path)
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("cell", [
    "esp. η (Alcyone)", "M44 or MCG 2632", "Shaula & Lesath?", "G Sco + Cglo 6441?", "al-Nasl", "τ, υ Capricorn", "ε, κ Capricorn",
    "γ, ζ, η, π Aquarius"])
def test_figure_88_says_so(cell):
    assert cell in corpus_text("gr_intr/abu_mashar_great_introduction.md")


@pytest.mark.parametrize("cell", [
    "α-β-γ Coma Berenice", "λ Sco., Shaula", "υ Sco., Lesath", "β Sco., Acrab/Graffias", "δ Sco., Dschubba", "π Scorpionis",
    "γ² Sagitt., al-Nasl", "η Tauri, Alcyone", "M44 or MCG 2632", "ε, κ Capricorni?", "ζ Aquarii?"])
def test_figure_59_says_so(cell):
    assert cell in corpus_text("on_nativities.md")


def test_rhetorius_sixty_two_is_the_eye_degrees():
    text = corpus_text("rhetorius/rhetorius_holden_PROVISIONAL.md")
    sixty_two = re.search(r"### Chapter 62: (.*)", text).group(1)
    sixty_one = re.search(r"### Chapter 61: (.*)", text).group(1)
    assert "Eyes" in sixty_two and "Eyes" not in sixty_one


@pytest.mark.parametrize("sentence, word", [
    (44, "mane"), (45, "sting"), (46, "forehead"), (47, "arrow"), (48, "Pleiades"), (49, "Cancer")])
def test_carmen_second_edition_says_so(sentence, word):
    chapter = corpus_text("carmen/carmen_dykes_2nd_ed_PROVISIONAL.md").split("[Chapter IV.2:")[1]
    assert word in re.search(rf"\*\*{sentence}\*\* (.*)", chapter).group(1)
