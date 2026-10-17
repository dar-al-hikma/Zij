"""The Sun's reception of the Moon from the opposition scores negative
(Gr. Intr. VII.5, 137; the owner's ruling, 2026-09-27).

137: the Sun receives the Moon "from all signs, since her glow is from him",
except that his reception of her from the opposition is detestable. The
Planetary Condition used to file that row's labels -- the Sun's "Receives
Moon by nature, from the opposition: detestable (137)" and the Moon's
"Received by Sun (detestable (137), via from the opposition)" -- among the
Positive Labels, under Good Fortune, where they counted toward Net. They are
now Negative Labels, under Weakness beside 43's "not received", with their
wording and locator unchanged. Only the opposition: the plain, doubled
(138) and aversion rows stay positive. The row is still a reception, so the
Moon is not also "not received" (43).

What moves, for each of the two planets on such a chart: Good Fortune and
Positive Score down one, Weakness and Negative Score up one; Net down one
where another reception row still gives the planet its one reception vote,
down two where the detestable row was its only reception. Condition and the
ranking follow Net; the Topical readings' Net and Lean follow it too.
"""
import pytest

LONDON = (51.5074, -0.1278)
FLORENCE = (43.7792, 11.2463)

COUNTS = ("Good Fortune", "Strength", "Weakness", "Misfortune", "Moon Defects",
          "Positive Score", "Negative Score", "Net", "Condition")


def _condition(E, y, m, d, place, days=0):
    lat, lon = place
    jd = E.civil_local_to_jd_ut(y, m, d, 12, lon / 15) + days
    chart = E.calculate_traditional_chart_jd(jd, lat, lon)
    p, sect = chart["planetary_data"], chart["sect"]
    essential = E.evaluate_essential_dignities(p, sect)
    accidental = E.evaluate_accidental_dignities(p, chart["houses"], sect, chart["julian_day"],
                                                 armc=chart["armc"], obliquity=chart["obliquity"], geo_lat=lat)
    sim = E._simulate_forward(p, chart["julian_day"])
    elongation = (p["Moon"]["longitude"] - p["Sun"]["longitude"]) % 360.0
    return elongation, E.evaluate_abu_mashar_condition(p, chart["houses"], sect, essential, accidental,
                                                       chart["julian_day"], chart["ascendant"], sim)


SUN_LABEL = "Receives Moon by nature, from the opposition: detestable (137)"
MOON_LABEL = "Received by Sun (detestable (137), via from the opposition)"

# (chart, planet, main's counts, this ruling's counts). Main's are kept so
# the move is read off the table: every row differs from main by exactly
# the ruling's amount. The Sun's counts on both sides are read under the
# owner's rulings 17 and 18 (2026-10-05; carried here by ruling 41): in
# these charts, January to March, he is swift and nearer than the middle of
# his range, so increasing in light, and 9 adds one to his Good Fortune,
# Positive Score and Net, before the ruling and after it alike.
MOVES = [
    # London 2000-01-21, noon LMT: the Moon in Leo, about 185 degrees from
    # the Sun. Both keep another reception row, so Net moves by one; the
    # Sun's Net goes from 3 to 2, Good either way.
    ((2000, 1, 21, LONDON), "Sun",
     dict(zip(COUNTS, (12, 3, 4, 3, 0, 16, 6, 3, "Good"))),
     dict(zip(COUNTS, (11, 3, 5, 3, 0, 15, 7, 2, "Good")))),
    ((2000, 1, 21, LONDON), "Moon",
     dict(zip(COUNTS, (9, 2, 3, 4, 3, 12, 9, 0, "Indeterminate"))),
     dict(zip(COUNTS, (8, 2, 4, 4, 3, 11, 10, -1, "Indeterminate")))),
    # London 2003-01-18: the Sun in Capricorn, the Moon in Cancer. The
    # detestable row is each one's only reception, so Net moves by two.
    ((2003, 1, 18, LONDON), "Sun",
     dict(zip(COUNTS, (7, 3, 2, 2, 0, 10, 4, 6, "Good"))),
     dict(zip(COUNTS, (6, 3, 3, 2, 0, 9, 5, 4, "Good")))),
    ((2003, 1, 18, LONDON), "Moon",
     dict(zip(COUNTS, (7, 2, 2, 3, 2, 10, 6, 5, "Good"))),
     dict(zip(COUNTS, (6, 2, 3, 3, 2, 9, 7, 3, "Good")))),
    # London 2000-03-20: the Moon in Libra, her only reception the Sun's
    # detestable one; Good (2) becomes Indeterminate (0). The Sun keeps his
    # other receptions, and his Net moves by one.
    ((2000, 3, 20, LONDON), "Sun",
     dict(zip(COUNTS, (10, 3, 0, 1, 0, 13, 1, 9, "Good"))),
     dict(zip(COUNTS, (9, 3, 1, 1, 0, 12, 2, 8, "Good")))),
    ((2000, 3, 20, LONDON), "Moon",
     dict(zip(COUNTS, (5, 2, 2, 2, 4, 7, 8, 2, "Good"))),
     dict(zip(COUNTS, (4, 2, 3, 2, 4, 6, 9, 0, "Indeterminate")))),
    # London 1995-02-15, noon LMT: the Sun at 26 Aquarius, the Moon at 26
    # Leo, about 180 degrees from him. The Sun keeps another reception row,
    # so his Net moves by one, and his Good (2) becomes Indeterminate (1).
    ((1995, 2, 15, LONDON), "Sun",
     dict(zip(COUNTS, (11, 2, 4, 2, 0, 13, 6, 2, "Good"))),
     dict(zip(COUNTS, (10, 2, 5, 2, 0, 12, 7, 1, "Indeterminate")))),
]


@pytest.mark.parametrize("chart, planet, main, now", MOVES,
                         ids=[f"{c[0]}-{c[1]:02d}-{c[2]:02d}-{p}" for c, p, _m, _n in MOVES])
def test_the_opposition_reception_is_a_negative_label_and_moves_each_count(chart, planet, main, now):
    import engine as E
    y, m, d, place = chart
    elongation, condition = _condition(E, y, m, d, place)
    assert 170.0 < elongation < 190.0
    row = condition[planet]
    label = SUN_LABEL if planet == "Sun" else MOON_LABEL
    assert label in row["Negative Labels"] and label not in row["Positive Labels"]
    # Filed under Weakness, beside 43.
    assert ("Weakness", label) in E._abu_mashar_condition_sections(row)
    assert {field: row[field] for field in COUNTS} == now
    # The move is the ruling's and nothing else's.
    only = not any(l.startswith(("Received", "Receives", "Mutual reception")) for l in row["Positive Labels"])
    assert now["Good Fortune"] == main["Good Fortune"] - 1
    assert now["Positive Score"] == main["Positive Score"] - 1
    assert now["Weakness"] == main["Weakness"] + 1
    assert now["Negative Score"] == main["Negative Score"] + 1
    assert now["Net"] == main["Net"] - (2 if only else 1)
    assert {f: now[f] for f in ("Strength", "Misfortune", "Moon Defects")} == \
        {f: main[f] for f in ("Strength", "Misfortune", "Moon Defects")}
    assert row["Known Net"] == row["Net"] and row["Known Weakness"] == row["Weakness"]


def test_the_detestably_received_moon_is_still_received():
    """137 calls it a reception; 43's "not received" does not fire on it."""
    import engine as E
    _elongation, condition = _condition(E, 2000, 3, 20, LONDON)
    moon = condition["Moon"]
    assert MOON_LABEL in moon["Negative Labels"]
    assert "Not received (43)" not in moon["Negative Labels"]


@pytest.mark.parametrize("days", [0, 4, 6, 8])
def test_the_other_variants_stay_positive(days):
    """Florence 1957-08-17 plus 0, 4, 6 and 8 days: the plain row, the two
    aversion rows and the doubled row (138) are Good Fortune, as before."""
    import engine as E
    _elongation, condition = _condition(E, 1957, 8, 17, FLORENCE, days)
    sun, moon = condition["Sun"], condition["Moon"]
    by_nature = [l for l in sun["Positive Labels"] if l.startswith("Receives Moon by nature")]
    assert len(by_nature) == 1 and "detestable" not in by_nature[0]
    assert not any("detestable" in l for l in sun["Negative Labels"] + moon["Negative Labels"])
    assert any(l.startswith("Received by Sun (strong (137)") for l in moon["Positive Labels"])


def test_florence_twenty_two_days_on_is_the_opposition():
    import engine as E
    elongation, condition = _condition(E, 1957, 8, 17, FLORENCE, 22)
    assert 170.0 < elongation < 190.0
    assert SUN_LABEL in condition["Sun"]["Negative Labels"]
    assert MOON_LABEL in condition["Moon"]["Negative Labels"]
    assert not any("detestable" in l for l in condition["Sun"]["Positive Labels"] + condition["Moon"]["Positive Labels"])


PAGE_SENTENCE = ("multiple reception rows for one planet likewise count once; the Sun's reception of the "
                 "Moon from the opposition, which Abu Ma'shar calls detestable, counts once against each of "
                 "them, under Weakness.")


def test_the_count_note_says_the_detestable_reception_counts_against():
    """The Planetary Condition's note on how the count is formed says so,
    in the page's own spelling of the author, and the engine does what it
    says: one Weakness entry on each side, the other reception rows one
    vote."""
    from conftest import ui_source
    import engine as E
    assert PAGE_SENTENCE in ui_source()
    _elongation, condition = _condition(E, 2000, 1, 21, LONDON)
    for planet, label in (("Sun", SUN_LABEL), ("Moon", MOON_LABEL)):
        sections = E._abu_mashar_condition_sections(condition[planet])
        assert sections.count(("Weakness", label)) == 1
        positive, negative = E._abu_mashar_condition_votes(condition[planet])
        assert negative.count(label) == 1 and positive.count("reception") == 1


def test_the_page_and_the_three_exports_carry_it_under_weakness():
    """London 2000-01-21, 14:30 LMT: the Planetary Condition table on the
    page, the export rows, and the Markdown and HTML reports all put the
    label in "Weakness / Misfortune", and the Topical readings' Net is the
    condition's."""
    from conftest import assert_no_exception, make_app
    at = make_app(date="2000-01-21", page="configurations")
    at.session_state["manual_lat_key"], at.session_state["manual_lon_key"] = LONDON
    at.run(timeout=300)
    assert_no_exception(at, "configurations 2000-01-21 London")
    assert any(PAGE_SENTENCE in node.value for node in at.main.markdown), "the count note is not on the page"

    frames = [df.value for df in at.main.dataframe
              if "Weakness / Misfortune" in df.value.columns and "Verdict" in df.value.columns]
    assert len(frames) == 1
    page = frames[0].set_index("Planet")
    for planet, label in (("Sun", SUN_LABEL), ("Moon", MOON_LABEL)):
        assert label in page.loc[planet, "Weakness / Misfortune"]
        assert label not in page.loc[planet, "Good Fortune / Strength"]

    export = at.session_state["_analysis_export"]["results"]
    rows = {r["Planet"]: r for r in export["Configurations"]["Planetary Condition"][0]["rows"]}
    for planet, label in (("Sun", SUN_LABEL), ("Moon", MOON_LABEL)):
        assert label in rows[planet]["Weakness / Misfortune"]
        assert label not in rows[planet]["Good Fortune / Strength"]
        assert rows[planet]["Net"] == page.loc[planet, "Net"]

    topical = {r["Planet"]: r for r in export["Dignities and places"]["Topical Planets in Houses"][0]["rows"]}
    for planet in ("Sun", "Moon"):
        assert topical[planet]["Net"] == rows[planet]["Net"]

    # The Markdown report: the table under "#### Planetary Condition", read
    # cell by cell for both rows.
    markdown = at.session_state["_analysis_markdown"].splitlines()
    at_heading = markdown.index("#### Planetary Condition")
    table = []
    for line in markdown[at_heading + 1:]:
        if line.startswith("#"):
            break
        if line.startswith("|") and not line.startswith("|---"):
            table.append([c.strip() for c in line.strip().strip("|").split(" | ")])
    header, body = table[0], {row[0]: dict(zip(table[0], row)) for row in table[1:]}
    assert "Weakness / Misfortune" in header and "Good Fortune / Strength" in header
    for planet, label in (("Sun", SUN_LABEL), ("Moon", MOON_LABEL)):
        assert label in body[planet]["Weakness / Misfortune"]
        assert label not in body[planet]["Good Fortune / Strength"]

    # The HTML report: the table after <h3>Planetary Condition</h3>, parsed.
    tables = _html_tables_after(at.session_state["_analysis_html"], "Planetary Condition")
    assert tables, "no Planetary Condition table in the HTML export"
    header, *cells = tables[0]
    body = {row[0]: dict(zip(header, row)) for row in cells}
    for planet, label in (("Sun", SUN_LABEL), ("Moon", MOON_LABEL)):
        assert label in body[planet]["Weakness / Misfortune"]
        assert label not in body[planet]["Good Fortune / Strength"]


def _html_tables_after(document, heading):
    """Each table (header row, then body rows, as cell text) that follows an
    <h3> whose text is `heading`, up to the next heading."""
    from html.parser import HTMLParser

    class Tables(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.tables, self.in_h3, self.h3, self.armed = [], False, "", False
            self.row, self.cell = None, None

        def handle_starttag(self, tag, attrs):
            if tag in ("h2", "h3"):
                self.in_h3, self.h3, self.armed = tag == "h3", "", False
            elif tag == "table" and self.armed:
                self.tables.append([])
            elif tag == "tr" and self.armed and self.tables:
                self.row = []
            elif tag in ("td", "th") and self.row is not None:
                self.cell = ""
            elif tag == "br" and self.cell is not None:
                self.cell += "\n"

        def handle_endtag(self, tag):
            if tag == "h3" and self.in_h3:
                self.in_h3, self.armed = False, self.h3.strip() == heading
            elif tag in ("td", "th") and self.cell is not None:
                self.row.append(self.cell)
                self.cell = None
            elif tag == "tr" and self.row is not None:
                self.tables[-1].append(self.row)
                self.row = None

        def handle_data(self, data):
            if self.in_h3:
                self.h3 += data
            elif self.cell is not None:
                self.cell += data

    parser = Tables()
    parser.feed(document)
    return parser.tables
