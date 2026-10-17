"""The atlas builder, GeoNames_Dataset.py (ATLAS1's rebuild: C-02 = D-03 =
SC-03 of the outside pass and the security sweep, rulings 150 and 172; the
name tables by ruling 179 S-04 (a), on the conditions of the atlas-names
check, process/ui_review_sol_2026-10-13/ATLAS_NAMES_CHECK.md, section 10).

The builder fetched cities500.zip over plain http, built from any
cities500.zip or cities500.txt it found in the working directory (a planted
text won over a real download), checked no row and recorded nothing. Now it
fetches over https into a fresh temporary folder, reads the archive's one
member by name, checks every row (a failing row stops the build and is
named), writes the database to a temporary file and moves it into place,
and records its sources in a metadata table.

No test here touches the network: urllib.request.urlopen is replaced by a
server of synthetic files.
"""
import contextlib
import hashlib
import io
import os
import sqlite3
import zipfile
from pathlib import Path

import pytest

import GeoNames_Dataset as builder

LAST_MODIFIED = "Wed, 14 Oct 2026 02:20:00 GMT"


def row(gid="3176959", name="Florence", ascii_name="Florence", lat="43.77925", lon="11.24626", country="IT",
        admin1="16", population="367150", zone="Europe/Rome", stamp="2024-01-01", columns=19):
    cols = [gid, name, ascii_name, "", lat, lon, "P", "PPLA", country, "", admin1, "FI", "048017", "",
            population, "", "50", zone, stamp]
    return "\t".join(cols[:columns])


GOOD_ROWS = [
    row(),
    row("2643743", "London", "London", "51.50853", "-0.12574", "GB", "ENG", "8961989", "Europe/London",
        "2025-05-06"),
    row("5128581", "New York City", "New York City", "40.71427", "-74.00597", "US", "NY", "8804190",
        "America/New_York", "2024-02-02"),
    row("1001", "Plain", "Plain", "1.5", "2.5", "AW", "", "0", "", "2023-03-03"),
    row("1002", "Zero", "Zero", "1.6", "2.6", "AW", "00", "13", "America/Aruba", "2023-03-04"),
    row("1003", "Bonaire", "Bonaire", "12.1", "-68.2", "BQ", "", "0", "America/Kralendijk", "2023-03-05"),
]

COUNTRY_INFO = "\n".join([
    "# GeoNames country info (a comment line)",
    "#ISO\tISO3\tISO-Numeric\tfips\tCountry\tCapital\tArea\tPopulation\tContinent\ttld\tCurrencyCode\t"
    "CurrencyName\tPhone\tPostal\tRegex\tLanguages\tgeonameid\tneighbours\tEquivalentFipsCode",
    *["\t".join([code, code + "X", "1", code, name, "", "1", "1", "EU", "." + code.lower(), "EUR", "Euro", "",
                 "", "", "", "1", "", ""])
      for code, name in (("IT", "Italy"), ("GB", "United Kingdom"), ("US", "United States"), ("AW", "Aruba"),
                         ("BQ", "Bonaire, Saint Eustatius and Saba "))],
]) + "\n"

ADMIN1 = "\n".join([
    "IT.16\tTuscany\tTuscany\t3165361",
    "GB.ENG\tEngland\tEngland\t6269131",
    "US.NY\tNew York\tNew York\t5128638",
    "AW.00\tAruba (general)\tAruba (general)\t1",
]) + "\n"


# Each member's timestamp is fixed: a member named by a string takes the clock's
# time, at two seconds' resolution, so an archive built for the served download
# and the one a test builds again to compare its hash differed whenever the clock
# ticked over between the two.
ZIP_TIME = (2025, 5, 6, 0, 0, 0)


def cities_zip(rows, member=builder.MEMBER, extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, body in [(member, "".join(r + "\n" for r in rows))] + ([(extra, "x")] if extra else []):
            info = zipfile.ZipInfo(name, date_time=ZIP_TIME)
            info.external_attr = 0o600 << 16
            archive.writestr(info, body)
    return buffer.getvalue()


def test_the_archive_a_test_builds_is_the_same_whenever_it_is_built(monkeypatch):
    """The clock forced past a two-second tick between two builds: the bytes agree."""
    import time
    start = time.time()
    first = cities_zip(GOOD_ROWS, extra="other.txt")
    monkeypatch.setattr(time, "time", lambda: start + 7.0)
    monkeypatch.setattr(time, "localtime", lambda secs=None: time.gmtime(start + 7.0 if secs is None else secs))
    assert time.time() - start >= 2, "premise: the clock has moved past a two-second tick"
    rebuilt = cities_zip(GOOD_ROWS, extra="other.txt")
    assert hashlib.sha256(rebuilt).hexdigest() == hashlib.sha256(first).hexdigest()


class _Response:
    def __init__(self, url, body, final=None, status=200, headers=None):
        self._body, self._url, self.status = io.BytesIO(body), final or url, status
        self.headers = {"Last-Modified": LAST_MODIFIED} if headers is None else headers

    def geturl(self):
        return self._url

    def read(self, n=-1):
        return self._body.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Server:
    """urlopen's stand-in: the three files by address, and every call kept."""
    def __init__(self, rows=GOOD_ROWS, zip_bytes=None, country_info=COUNTRY_INFO, admin1=ADMIN1, final=None,
                 status=200, headers=None):
        self.files = {builder.URL: zip_bytes if zip_bytes is not None else cities_zip(rows),
                      builder.COUNTRY_INFO_URL: country_info.encode("utf-8"),
                      builder.ADMIN1_URL: admin1.encode("utf-8")}
        self.final, self.status, self.headers, self.calls = final, status, headers, []

    def __call__(self, url, timeout=None, context=None):
        self.calls.append((url, context))
        return _Response(url, self.files[url], self.final, self.status, self.headers)


@pytest.fixture
def served(monkeypatch, tmp_path):
    """Build in an empty working directory with the network replaced; the
    temporary folders go under tmp_path/tmp."""
    (tmp_path / "work").mkdir()
    (tmp_path / "tmp").mkdir()
    monkeypatch.chdir(tmp_path / "work")
    monkeypatch.setattr(builder.tempfile, "tempdir", str(tmp_path / "tmp"))

    def serve(**kwargs):
        server = Server(**kwargs)
        monkeypatch.setattr(builder.urllib.request, "urlopen", server)
        return server
    return serve


def _rows(db):
    with contextlib.closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        return {r[0]: r for r in conn.execute("SELECT * FROM cities")}


def _metadata(db):
    with contextlib.closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        return dict(conn.execute("SELECT key, value FROM metadata"))


# --- where the files come from ----------------------------------------------

def test_every_address_is_geonames_over_https():
    for url in (builder.URL, builder.COUNTRY_INFO_URL, builder.ADMIN1_URL):
        assert url.startswith("https://download.geonames.org/export/dump/"), url
    assert builder.URL.endswith("/cities500.zip")


def test_the_three_files_are_fetched_over_https_with_certificates_checked(served, tmp_path):
    server = served()
    builder.build_offline_atlas(tmp_path / "atlas.db")
    calls = server.calls
    assert [url for url, _context in calls] == [builder.URL, builder.COUNTRY_INFO_URL, builder.ADMIN1_URL]
    assert len(calls) == 3
    for _url, context in calls:
        assert context.verify_mode == builder.ssl.CERT_REQUIRED and context.check_hostname


def test_an_address_that_is_not_https_is_refused(tmp_path):
    with pytest.raises(builder.AtlasBuildError, match="not an https address"):
        builder.fetch("http://download.geonames.org/export/dump/cities500.zip", str(tmp_path), "x.zip")
    assert not (tmp_path / "x.zip").exists()


def test_a_redirect_to_plain_http_is_refused(served, tmp_path):
    served(final="http://download.geonames.org/export/dump/cities500.zip")
    with pytest.raises(builder.AtlasBuildError, match="redirected to http://"):
        builder.build_offline_atlas(tmp_path / "atlas.db")
    assert not (tmp_path / "atlas.db").exists()


def test_a_status_other_than_200_is_refused(served, tmp_path):
    served(status=203)
    with pytest.raises(builder.AtlasBuildError, match="status 203"):
        builder.build_offline_atlas(tmp_path / "atlas.db")


def test_files_planted_in_the_working_directory_are_not_read(served, tmp_path):
    """C-02's two plants: a cities500.zip and a cities500.txt in the folder the
    builder is run from, each putting Florence at 0, 0. The build reads the
    download, and leaves the planted files as they were."""
    planted = [row(lat="0.0", lon="0.0")]
    work = tmp_path / "work"
    (work / "cities500.zip").write_bytes(cities_zip(planted))
    (work / "cities500.txt").write_text(planted[0] + "\n", encoding="utf-8")
    served()
    builder.build_offline_atlas(tmp_path / "atlas.db")
    florence = _rows(tmp_path / "atlas.db")[3176959]
    assert (florence[5], florence[6]) == (43.77925, 11.24626)
    assert {p.name: p.read_bytes() for p in work.iterdir()} == {
        "cities500.zip": cities_zip(planted), "cities500.txt": (planted[0] + "\n").encode("utf-8")}


def test_the_download_goes_to_a_fresh_temporary_folder_removed_after(served, tmp_path, monkeypatch):
    made = []
    real = builder.tempfile.mkdtemp

    def mkdtemp(*args, **kwargs):
        made.append(real(*args, **kwargs))
        return made[-1]
    monkeypatch.setattr(builder.tempfile, "mkdtemp", mkdtemp)
    served()
    builder.build_offline_atlas(tmp_path / "atlas.db")
    assert len(made) == 1 and Path(made[0]).parent == tmp_path / "tmp"
    assert not Path(made[0]).exists()
    summary = builder.build_offline_atlas(tmp_path / "atlas2.db", keep_downloads=True)
    kept = Path(summary["downloads"])
    assert sorted(p.name for p in kept.iterdir()) == ["admin1CodesASCII.txt", "cities500.zip", "countryInfo.txt"]


# --- the archive and its rows -------------------------------------------------

def test_the_archive_is_read_by_its_one_member(served, tmp_path):
    served(zip_bytes=cities_zip(GOOD_ROWS, extra="other.txt"))
    with pytest.raises(builder.AtlasBuildError, match="not the one member cities500.txt"):
        builder.build_offline_atlas(tmp_path / "atlas.db")
    served(zip_bytes=cities_zip(GOOD_ROWS, member="cities1000.txt"))
    with pytest.raises(builder.AtlasBuildError, match="not the one member cities500.txt"):
        builder.build_offline_atlas(tmp_path / "atlas.db")
    assert not (tmp_path / "atlas.db").exists()


BAD_ROWS = [
    pytest.param(row(lat="95"), "line 2 (geonameid 3176959): the latitude 95.0 is outside -90 to 90", id="lat-95"),
    pytest.param(row(lon="400"), "line 2 (geonameid 3176959): the longitude 400.0 is outside -180 to 180",
                 id="lon-400"),
    pytest.param(row(columns=18), "line 2 has 18 columns, not 19", id="short-row"),
    pytest.param(row() + "\textra", "line 2 has 20 columns, not 19", id="long-row"),
    pytest.param(row(gid="31x"), "line 2: the id '31x' is not a whole number", id="id-not-a-number"),
    pytest.param(row(gid="-5"), "line 2: the id '-5' is not a whole number", id="id-negative"),
    pytest.param(row(lat="nan"), "the latitude 'nan' is not a decimal number", id="lat-nan"),
    pytest.param(row(lat="4e1"), "the latitude '4e1' is not a decimal number", id="lat-exponent"),
    pytest.param(row(lat=""), "the latitude '' is not a decimal number", id="lat-empty"),
    pytest.param(row(population="-1"), "the population '-1' is not a whole number", id="population-negative"),
    pytest.param(row(population=""), "the population '' is not a whole number", id="population-empty"),
    pytest.param(row(population="12.5"), "the population '12.5' is not a whole number", id="population-fraction"),
    pytest.param(row(country="ITA"), "the country 'ITA' is not a two-letter code", id="country-three"),
    pytest.param(row(country="it"), "the country 'it' is not a two-letter code", id="country-lower"),
    pytest.param(row(zone="Europe/Atlantis"), "the zone 'Europe/Atlantis' is not one the pinned tzdata",
                 id="zone-unknown"),
    pytest.param(row(stamp="2024-13-01"), "the modification date '2024-13-01' is not a date", id="date-bad"),
    pytest.param(row(gid="2643743"), "line 2 (geonameid 2643743): the id is repeated", id="id-repeated"),
]


@pytest.mark.parametrize("bad, said", BAD_ROWS)
def test_a_failing_row_stops_the_build_and_is_named(served, tmp_path, bad, said):
    """The bad row is the second of three: nothing is skipped, nothing is
    written, and an atlas already in place is left as it was."""
    target = tmp_path / "atlas.db"
    target.write_bytes(b"the atlas in place")
    served(rows=[GOOD_ROWS[1], bad, GOOD_ROWS[2]])
    with pytest.raises(builder.AtlasBuildError) as raised:
        builder.build_offline_atlas(target)
    assert said in str(raised.value), str(raised.value)
    assert target.read_bytes() == b"the atlas in place"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["atlas.db", "tmp", "work"]


def test_the_good_rows_are_built_as_given(served, tmp_path):
    served()
    builder.build_offline_atlas(tmp_path / "atlas.db")
    rows = _rows(tmp_path / "atlas.db")
    assert len(rows) == len(GOOD_ROWS)
    assert rows[2643743][:8] == (2643743, "London", "London", "ENG", "GB", 51.50853, -0.12574, 8961989)
    with contextlib.closing(sqlite3.connect(f"file:{tmp_path / 'atlas.db'}?mode=ro", uri=True)) as conn:
        zones = dict(conn.execute("SELECT c.id, z.name FROM cities c LEFT JOIN geonames_zones z "
                                  "ON z.id = c.geonames_zone"))
        indexes = sorted(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index' "
                                                    "AND sql IS NOT NULL"))
    assert zones[2643743] == "Europe/London" and zones[1001] is None and zones[1002] == "America/Aruba"
    assert indexes == ["idx_ascii", "idx_name"]


def test_the_metadata_table_is_written(served, tmp_path):
    served()
    builder.build_offline_atlas(tmp_path / "atlas.db")
    meta = _metadata(tmp_path / "atlas.db")
    archive = cities_zip(GOOD_ROWS)
    assert meta["source_url"] == builder.URL
    assert meta["source_last_modified"] == LAST_MODIFIED
    assert meta["source_sha256"] == hashlib.sha256(archive).hexdigest()
    assert meta["source_bytes"] == str(len(archive))
    assert meta["rows"] == str(len(GOOD_ROWS))
    assert meta["dropped_ids"] == " ".join(str(gid) for gid in sorted(builder.DROPPED))
    assert meta["dump_date"] == "2025-05-06"          # the newest modification date among the rows
    assert meta["python_version"] == builder.sys.version.split()[0]
    assert meta["unicodedata_version"] == builder.unicodedata.unidata_version
    assert meta["tzdata_version"] == builder.importlib.metadata.version("tzdata")
    for prefix, url, body in (("country_info", builder.COUNTRY_INFO_URL, COUNTRY_INFO),
                              ("admin1_codes", builder.ADMIN1_URL, ADMIN1)):
        assert meta[f"{prefix}_url"] == url
        assert meta[f"{prefix}_last_modified"] == LAST_MODIFIED
        assert meta[f"{prefix}_sha256"] == hashlib.sha256(body.encode("utf-8")).hexdigest()
        assert meta[f"{prefix}_bytes"] == str(len(body.encode("utf-8")))


def test_the_database_is_written_beside_the_target_and_moved_into_place(served, tmp_path, monkeypatch):
    moved = []
    real = builder.os.replace
    monkeypatch.setattr(builder.os, "replace", lambda a, b: (moved.append((a, b)), real(a, b))[1])
    served()
    builder.build_offline_atlas(tmp_path / "atlas.db")
    assert len(moved) == 1 and Path(moved[0][0]).parent == tmp_path and Path(moved[0][1]) == tmp_path / "atlas.db"
    assert not Path(moved[0][0]).exists()
    assert (tmp_path / "atlas.db").stat().st_mode & 0o777 == 0o644


def test_every_connection_the_build_opens_is_closed(served, tmp_path, monkeypatch):
    made = []
    real = sqlite3.connect

    class _Connection(sqlite3.Connection):
        closed = False

        def close(self):
            self.closed = True
            super().close()

    def connect(*args, **kwargs):
        made.append(real(*args, factory=_Connection, **kwargs))
        return made[-1]
    monkeypatch.setattr(builder.sqlite3, "connect", connect)
    served()
    builder.build_offline_atlas(tmp_path / "atlas.db")
    # an atlas country countryInfo.txt does not name: refused inside the
    # database's writing, with the connection open
    served(country_info="\n".join(line for line in COUNTRY_INFO.splitlines() if not line.startswith("BQ")) + "\n")
    with pytest.raises(builder.AtlasBuildError):
        builder.build_offline_atlas(tmp_path / "atlas2.db")
    assert len(made) == 2 and all(c.closed for c in made)


# --- the country and region names (the atlas-names check's conditions) --------

def test_the_name_tables_hold_every_country_and_pair_with_geonames_text(served, tmp_path):
    served()
    summary = builder.build_offline_atlas(tmp_path / "atlas.db")
    with contextlib.closing(sqlite3.connect(f"file:{tmp_path / 'atlas.db'}?mode=ro", uri=True)) as conn:
        countries = conn.execute("SELECT * FROM country_names ORDER BY country").fetchall()
        regions = conn.execute("SELECT * FROM admin1_names ORDER BY country, admin1").fetchall()
    assert countries == [("AW", "Aruba"), ("BQ", "Bonaire, Saint Eustatius and Saba "), ("GB", "United Kingdom"),
                         ("IT", "Italy"), ("US", "United States")]       # BQ's trailing space kept
    # a blank region code and "00" are two pairs; a pair GeoNames lists no
    # name for is kept, with none
    assert regions == [("AW", "", None, None), ("AW", "00", "Aruba (general)", "Aruba (general)"),
                       ("BQ", "", None, None), ("GB", "ENG", "England", "England"),
                       ("IT", "16", "Tuscany", "Tuscany"), ("US", "NY", "New York", "New York")]
    assert (summary["countries"], summary["admin1_pairs"], summary["unnamed_admin1_pairs"],
            summary["places_without_region_name"]) == (5, 6, 2, 2)


NAME_REFUSALS = [
    pytest.param({"country_info": COUNTRY_INFO + COUNTRY_INFO.splitlines()[2] + "\n"}, "row 'IT' is repeated",
                 id="country-repeated"),
    pytest.param({"admin1": ADMIN1 + "IT.16\tToscana\tToscana\t1\n"}, "row 'IT.16' is repeated",
                 id="region-repeated"),
    pytest.param({"country_info": COUNTRY_INFO.replace("\tItaly\t", "\t\t")}, "row 'IT': the name is blank",
                 id="country-blank"),
    pytest.param({"admin1": ADMIN1.replace("\tTuscany\tTuscany", "\t\tTuscany")}, "row 'IT.16': the name is blank",
                 id="region-blank"),
    pytest.param({"country_info": COUNTRY_INFO.replace("\tUnited States\t", "\tUnited\tStates\t")},
                 "row 'US' has 20 columns", id="country-name-with-a-tab"),
    pytest.param({"admin1": ADMIN1.replace("\tNew York\tNew", "\tNew\tYork\tNew")},
                 "row 'US.NY' is not a code, a name", id="region-name-with-a-tab"),
    pytest.param({"country_info": COUNTRY_INFO.replace("\tUnited States\t", "\tUnited\nStates\t")},
                 "has 5 columns", id="country-name-with-a-line-break"),
    pytest.param({"admin1": ADMIN1.replace("\tNew York\tNew", "\tNew\nYork\tNew")},
                 "row 'US.NY' is not a code, a name", id="region-name-with-a-line-break"),
    pytest.param({"country_info": COUNTRY_INFO.replace("\tUnited States\t", '\t"United States"\t')},
                 "holds '\"'; it is refused, not quoted", id="country-name-with-a-quote"),
    pytest.param({"admin1": ADMIN1.replace("\tTuscany\tTuscany", '\tTus"cany\tTuscany')},
                 "holds '\"'; it is refused, not quoted", id="region-name-with-a-quote"),
    pytest.param({"country_info": "\n".join(line for line in COUNTRY_INFO.splitlines()
                                            if not line.startswith("BQ")) + "\n"},
                 "countryInfo.txt gives no name for BQ", id="atlas-country-unnamed"),
]


@pytest.mark.parametrize("files, said", NAME_REFUSALS)
def test_a_name_source_the_check_refuses_stops_the_build(served, tmp_path, files, said):
    served(**files)
    with pytest.raises(builder.AtlasBuildError) as raised:
        builder.build_offline_atlas(tmp_path / "atlas.db")
    assert said in str(raised.value), str(raised.value)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["tmp", "work"]


@pytest.mark.parametrize("mark", ["\t", "\n", "\r", '"'])
def test_a_name_holding_a_tab_a_line_break_or_a_quote_is_refused(mark):
    with pytest.raises(builder.AtlasBuildError, match="refused, not quoted"):
        builder._checked_name(f"Bad{mark}name", "here")


@pytest.mark.parametrize("country, admin1", [(None, "01"), ("IT", None), ("IT", 16), (b"IT", "16")])
def test_a_null_or_non_text_code_is_refused(country, admin1):
    with contextlib.closing(sqlite3.connect(":memory:")) as conn:
        conn.execute("CREATE TABLE cities (id INTEGER PRIMARY KEY, country, admin1)")
        conn.execute("INSERT INTO cities VALUES (1, ?, ?)", (country, admin1))
        with pytest.raises(builder.AtlasBuildError, match="is not text"):
            builder.write_names(conn, {"IT": "Italy"}, {})


def test_the_builder_names_no_plain_http_address_and_no_date():
    """The builder ships publicly: no address in it is plain http, and its
    text carries no date (the private-paths test reads it for the rest)."""
    text = Path(builder.__file__).read_text(encoding="utf-8")
    assert "http://" not in text
    assert not builder.re.search(r"\b(19|20)[0-9]{2}-[0-9]{2}-[0-9]{2}\b", text)


def test_a_dropped_row_is_checked_and_left_out(served, tmp_path, monkeypatch):
    """C-17: La Aguada's point lies at sea and no source corrects it, so the
    builder leaves it out; a dropped row is still checked, so a bad one
    stops the build as any other would."""
    assert 3785489 in builder.DROPPED and "52 km" in builder.DROPPED[3785489]
    aguada = row("3785489", "La Aguada", "La Aguada", "11.27667", "-67.46444", "VE", "11", "7261",
                 "America/Caracas", "2024-01-01")
    served(rows=GOOD_ROWS + [aguada])
    builder.build_offline_atlas(tmp_path / "atlas.db")
    assert 3785489 not in _rows(tmp_path / "atlas.db") and len(_rows(tmp_path / "atlas.db")) == len(GOOD_ROWS)
    served(rows=GOOD_ROWS + [row("3785489", lat="95")])
    with pytest.raises(builder.AtlasBuildError, match="geonameid 3785489"):
        builder.build_offline_atlas(tmp_path / "atlas2.db")
