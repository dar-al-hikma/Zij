"""The OpenStreetMap outline tables as a data file of their own.

The three tables of areas the zone code reads by coordinates -- the
exceptions inside a zone (Sicily, Sardinia, the canton of Geneva), the cities
with dates of their own (Milan, Turin, Bologna, Venice) and the areas outside
the country a zone's notes describe (Alsace-Moselle; Trentino and South Tyrol;
Trieste and Gorizia) -- are an edited OpenStreetMap derivative. They are
published whole as data/mean_time_outlines.json under the Open Database
License, with their notice beside them, apart from the code's licence, and
time_zones.py reads them back at import into exactly the structures the code
held: tuples, each vertex (latitude, longitude), every number the float that
was written.
"""
import ast
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "mean_time_outlines.json"
NOTICE = ROOT / "data" / "NOTICE-ODBL.md"

# A place inside each area and one just outside it (latitude, longitude):
# a vertex written longitude first, or a ring moved to the wrong area, moves
# one of these.
INSIDE = (
    ("MEAN_TIME_EXCEPTIONS", "Europe/Rome", "Sicily", (38.1157, 13.3615), (38.2147, 15.6447)),     # Palermo; Reggio
    ("MEAN_TIME_EXCEPTIONS", "Europe/Rome", "Sardinia", (39.2238, 9.1217), (41.9028, 12.4964)),    # Cagliari; Rome
    ("MEAN_TIME_EXCEPTIONS", "Europe/Zurich", "the canton of Geneva", (46.2044, 6.1432),
     (46.5197, 6.6323)),                                                                           # Geneva; Lausanne
    ("MEAN_TIME_CITY_DATES", "Europe/Rome", "Milan", (45.4642, 9.1900), (45.5845, 9.2744)),       # the Duomo; Monza
    ("MEAN_TIME_CITY_DATES", "Europe/Rome", "Turin", (45.0703, 7.6869), (45.0, 7.5)),
    ("MEAN_TIME_CITY_DATES", "Europe/Rome", "Bologna", (44.4949, 11.3426), (44.40, 11.20)),
    ("MEAN_TIME_CITY_DATES", "Europe/Rome", "Venice", (45.4341, 12.3388), (45.4907, 12.2425)),    # San Marco; Mestre
    ("MEAN_TIME_OUTSIDE", "Europe/Paris", "Alsace-Moselle", (48.5734, 7.7521), (48.6921, 6.1844)),  # Strasbourg; Nancy
    ("MEAN_TIME_OUTSIDE", "Europe/Rome", "Trentino and South Tyrol", (46.0748, 11.1217),
     (45.4384, 10.9916)),                                                                          # Trento; Verona
    ("MEAN_TIME_OUTSIDE", "Europe/Rome", "Trieste and Gorizia", (45.6495, 13.7768),
     (46.0711, 13.2346)),                                                                          # Trieste; Udine
)

# Every vertex of every area lies in this band: Italy, France's east and
# Geneva, latitude first.
LATITUDES, LONGITUDES = (35.0, 50.5), (5.8, 15.8)

# The pre-push hook's page marker of the private texts (tools/git-hooks/pre-push,
# CORPUS_MARKER), in Python's spelling: the data file and its notice carry none.
GAP = r"[\s ]*"
CORPUS_MARKER = re.compile(r"[*_]" + GAP + r"\[([^\]]{0,59}[^\]A-Za-z0-9_])?p\." + GAP
                           + r"([A-Za-z]{1,6}\." + GAP + r")?[0-9ivxlcIVXLC]")


@pytest.fixture(scope="module")
def tz():
    import time_zones
    return time_zones


def _area(tz, table, zone, name):
    hits = [a for a in getattr(tz, table)[zone] if a[0] == name]
    assert len(hits) == 1, (table, zone, name)
    return hits[0]


@pytest.mark.parametrize("table, zone, name, inside, outside", INSIDE, ids=[r[2] for r in INSIDE])
def test_each_area_holds_its_place_and_not_its_neighbour(tz, table, zone, name, inside, outside):
    rings = _area(tz, table, zone, name)[-1]
    assert tz._inside_area(*inside, rings), (name, inside)
    assert not tz._inside_area(*outside, rings), (name, outside)


def test_every_vertex_is_latitude_first_and_a_float(tz):
    count = 0
    for table in ("MEAN_TIME_EXCEPTIONS", "MEAN_TIME_CITY_DATES", "MEAN_TIME_OUTSIDE"):
        zones = getattr(tz, table)
        assert zones, table
        for zone, areas in zones.items():
            assert areas, (table, zone)
            assert isinstance(areas, tuple), (table, zone)
            for area in areas:
                assert isinstance(area, tuple) and len(area) == 3, (table, area[:2])
                rings = area[-1]
                assert rings, (table, area[0])
                assert isinstance(rings, tuple), (table, area[0])
                for ring in rings:
                    assert ring, (table, area[0])
                    assert isinstance(ring, tuple) and len(ring) >= 4, (table, area[0])
                    for vertex in ring:
                        assert isinstance(vertex, tuple) and len(vertex) == 2, (area[0], vertex)
                        lat, lon = vertex
                        assert type(lat) is float and type(lon) is float, (area[0], vertex)
                        assert LATITUDES[0] <= lat <= LATITUDES[1], (area[0], vertex, "latitude")
                        assert LONGITUDES[0] <= lon <= LONGITUDES[1], (area[0], vertex, "longitude")
                        count += 1
    # The tables' vertices: the exceptions 53, the cities 347, the areas outside 826.
    assert count == 53 + 347 + 826, count


def test_the_fields_beside_the_rings_are_the_tables_own(tz):
    assert [(z, a[0], a[1]) for z, areas in tz.MEAN_TIME_EXCEPTIONS.items() for a in areas] == [
        ("Europe/Rome", "Sicily", 1893), ("Europe/Rome", "Sardinia", 1893),
        ("Europe/Zurich", "the canton of Geneva", 1894)]
    assert [(z, a[0], a[1]) for z, areas in tz.MEAN_TIME_CITY_DATES.items() for a in areas] == [
        ("Europe/Rome", "Milan", (1866, 12, 12)), ("Europe/Rome", "Turin", (1867, 1, 1)),
        ("Europe/Rome", "Bologna", (1867, 1, 1)), ("Europe/Rome", "Venice", (1880, 5, 1))]
    assert [(z, a[0], a[1]) for z, areas in tz.MEAN_TIME_OUTSIDE.items() for a in areas] == [
        ("Europe/Paris", "Alsace-Moselle", "France"), ("Europe/Rome", "Trentino and South Tyrol", "Italy"),
        ("Europe/Rome", "Trieste and Gorizia", "Italy")]
    # The ring counts: Geneva's two pieces at Celigny, Turin's detached piece,
    # Trieste and Gorizia's five boxes.
    assert [len(a[-1]) for t in (tz.MEAN_TIME_EXCEPTIONS, tz.MEAN_TIME_CITY_DATES, tz.MEAN_TIME_OUTSIDE)
            for areas in t.values() for a in areas] == [1, 1, 3, 1, 2, 1, 1, 1, 1, 6]


def test_the_module_holds_what_the_file_holds_read_again(tz):
    again = tz._read_outline_tables()
    assert again == {"exceptions": tz.MEAN_TIME_EXCEPTIONS, "cities": tz.MEAN_TIME_CITY_DATES,
                     "outside": tz.MEAN_TIME_OUTSIDE}


def test_every_number_in_the_file_is_written_as_the_float_it_reads_back():
    """Each coordinate is written in its shortest exact form, so the text and
    the float are one value: reading and writing it again changes nothing."""
    numbers = []
    json.loads(DATA.read_text(encoding="utf-8"), parse_float=lambda t: numbers.append(t) or float(t))
    assert len(numbers) == 2 * (53 + 347 + 826), len(numbers)
    assert [t for t in numbers if repr(float(t)) != t] == []


def test_the_loader_reads_the_file_with_the_standard_library_alone():
    tree = ast.parse((ROOT / "time_zones.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module.split(".")[0])
    # contextlib, sqlite3 and unicodedata came with the atlas lookup, moved
    # here from app.py (ruling 175 (7)), and pathlib with its read-only open
    # (SC-07); the outline file's loader still needs json and os alone.
    assert imported == {"contextlib", "datetime", "json", "os", "pathlib", "sqlite3", "unicodedata",
                        "zoneinfo"}, imported
    # No table literal is left in the code: the names are bound from the file.
    bound = {t.id: node.value for node in tree.body if isinstance(node, ast.Assign)
             for t in node.targets if isinstance(t, ast.Name)}
    for name in ("MEAN_TIME_EXCEPTIONS", "MEAN_TIME_CITY_DATES", "MEAN_TIME_OUTSIDE"):
        assert isinstance(bound[name], ast.Subscript), name


def test_the_file_and_its_notice_carry_no_nul_byte_and_no_page_marker():
    for path in (DATA, NOTICE):
        raw = path.read_bytes()
        assert b"\x00" not in raw and b"\r" not in raw, path.name
        assert not CORPUS_MARKER.search(raw.decode("utf-8")), path.name
    # The pattern finds what it is for (the marker built by the helper, never
    # spelled in a published file).
    from corpus_paths import page_marker
    assert CORPUS_MARKER.search(page_marker("Gr. Intr.", 395))


def test_the_notice_names_the_source_the_licence_and_what_the_data_are_not():
    text = NOTICE.read_text(encoding="utf-8")
    for part in ("© OpenStreetMap contributors", "https://www.openstreetmap.org/copyright",
                 "Open Database License (ODbL) 1.0", "https://opendatacommons.org/licenses/odbl/1-0/",
                 "mean_time_outlines.json", "modified for Zīj", "not an authoritative record",
                 "AGPL-3.0"):
        assert part in text, part
    # No date of the extraction or of the work, no code name, no path of ours.
    assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
    assert not re.search(r"MEAN_TIME_|time_zones|process/|/home/|\.py\b", text)
    data = json.loads(DATA.read_text(encoding="utf-8"))
    assert "latitude first" in data["schema"]["rings"]
    assert not re.search(r"\b20\d\d-\d{2}-\d{2}\b", DATA.read_text(encoding="utf-8"))


def test_the_build_ships_the_file_and_its_notice_where_the_module_reads_them():
    spec = (ROOT / "build.spec").read_text(encoding="utf-8")
    assert '("data/mean_time_outlines.json", "data")' in spec
    assert '("data/NOTICE-ODBL.md", "data")' in spec
    source = (ROOT / "time_zones.py").read_text(encoding="utf-8")
    assert "os.path.dirname(os.path.abspath(__file__)), 'data', 'mean_time_outlines.json'" in source


def test_a_windows_checkout_keeps_the_files_bytes():
    lines = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert "data/mean_time_outlines.json -text" in lines


def test_the_readme_and_the_references_name_the_file_in_plain_words():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    row = next(line for line in readme.splitlines() if line.startswith("| `data/` |"))
    assert "OpenStreetMap" in row and "Open Database License" in row and "notice" in row
    refs = (ROOT / "docs" / "REFERENCES.md").read_text(encoding="utf-8")
    row = next(line for line in refs.splitlines() if "data/mean_time_outlines.json" in line)
    assert "© OpenStreetMap contributors" in row and "Open Database License 1.0" in row
    assert "not authoritative borders" in row
    assert not re.search(r"MEAN_TIME_|time_zones|\b\d{4}-\d{2}-\d{2}\b", row)
