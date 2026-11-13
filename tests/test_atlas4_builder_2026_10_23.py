"""The full atlas's builder, build_atlas.py.

It builds, from GeoNames' full dump kept on disk, one database holding the
view `cities` over the places in the earlier table's nine columns (the
region by its code, GeoNames' zone), the country and region names, and
the search's own tables (every place, its other names, every name in the
search's four kinds of key, and the first twenty places for each short
prefix whose range is broad). Every test here builds
from small GeoNames-format files it writes itself: no network, and no
shipped file is read but the atlas, read-only, for its schema.
"""
import contextlib
import hashlib
import io
import json
import os
import sqlite3
import warnings
import zipfile
from pathlib import Path

import pytest

import build_atlas as builder

ROOT = Path(builder.__file__).resolve().parent
SHIPPED_ATLAS = ROOT / "atlas.db"
ZIP_TIME = (2025, 5, 6, 0, 0, 0)


def place(i, name, country="US", admin1="01", admin2="001", pop=100, code="PPL", cls="P", ascii_name=None,
          lat=10, lon=20, zone="Etc/UTC", stamp="2026-01-02", population=None):
    return "\t".join(map(str, [i, name, builder.normalize(name) if ascii_name is None else ascii_name, "", lat,
                               lon, cls, code, country, "", admin1, admin2, "", "",
                               pop if population is None else population, "", "0", zone, stamp]))


AGUADA = place(3785489, "La Aguada", "VE", admin1="11", lat="11.27667", lon="-67.46444", pop=7261,
               zone="America/Caracas")


def fixture_places():
    data = [place(1, "Florence", "IT", pop=360000, code="PPLA", zone="Europe/Rome"),
            place(2, "Florence", pop=40000, zone="America/New_York"),
            place(3, "Paris", "FR", pop=2100000, code="PPLC", zone="Europe/Paris"), place(4, "Paris", pop=24000),
            place(5, "Springfield", admin2="001"), place(6, "Springfield", admin2="002"),
            place(7, "Springfield", admin2="001"), place(8, "Kaliningrad", "RU"),
            place(9, "Istanbul", "TR", pop=15000000), place(10, "Москва", "RU"), place(11, "القاهرة", "EG"),
            place(12, "Old Town", code="PPLH"), place(13, "Abandoned", code="PPLQ"),
            place(14, "Destroyed", code="PPLW"), place(15, "Section", code="PPLX"),
            place(16, "Hill", cls="T"), place(17, "Same"), place(18, "Same"),
            place(19, "Exact", pop=1), place(20, "Exactly", pop=9999999, code="PPLC"),
            place(21, "Twin", code="PPLH"), place(22, "Twin"),
            place(23, "Marseille", "FR", ascii_name="Marseille"),
            place(24, "Ur", pop=1), place(25, "Uruk", pop=9999999, code="PPLC"),
            place(26, "Urbino", pop=99999), place(27, "Å", "US", pop=1, zone=""),
            place(28, "Århus", pop=500000), place(29, "Nowhere Region", "RU", admin1="99"),
            # a feature of another class may hold anything but its column count
            "\t".join(["30", "Ridge", "Ridge", "", "x", "y", "T", "RDGE", "", "", "", "", "", "", "", "", "", "",
                       ""]),
            AGUADA]
    for i, s in enumerate(["%", "_", "Flor%", '"', "*", "NEAR", "a OR b", "^", "NOT", "AND", "(x)", "-x", ":x",
                           "a" * 300], 100):
        data.append(place(i, s))
    data.extend(place(1000 + i, "Synthetic " + str(i)) for i in range(220))
    return data


ALTERNATES = [(1, 8, "de", "Königsberg", "", "", "", "", "", ""), (2, 9, "en", "Constantinople", "", "", "", "1",
                                                                     "", ""),
              (3, 1, "link", "http-like", "", "", "", "", "", ""),
              (4, 1, "en", "Florence", "1", "", "", "", "", ""),        # the place's own name again
              (5, 16, "en", "Hill Alias", "", "", "", "", "", ""),       # a place not kept
              (6, 23, "en", "Marseilles", "1", "", "", "", "", ""),
              (7, 9, "en", "Byzantion", "", "", "", "1", "", ""), (8, 24, "en", "UR", "", "", "", "1", "", ""),
              (9, 3785489, "es", "Aguada", "", "", "", "", "", ""),      # a dropped place
              (10, 3, "en", "Pa\u200eris", "", "", "", "", "", ""),       # a format character
              (11, 3, "en", "", "", "", "", "", "", ""),                 # an empty name
              (12, 3, "fr", "Lutèce", "", "", "", "1", "", "")]

COUNTRIES = [("US", "United States"), ("IT", "Italy"), ("FR", "France"), ("RU", "Russia"), ("TR", "Türkiye"),
             ("EG", "Egypt"), ("VE", "Venezuela")]
ADMIN1 = "US.01\tState\tState\t900\nIT.01\tToscana\tTuscany\t901\n"


def country_info(countries=COUNTRIES):
    return "#header\n" + "".join("\t".join([cc, cc + "X", "1", "", name] + [""] * 14) + "\n"
                                 for cc, name in countries)


def zipped(path, member, lines):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo(member, date_time=ZIP_TIME)
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, "".join(line + "\n" for line in lines))


def write_manifest(root, paths):
    manifest = root / "MANIFEST.json"
    manifest.write_text(json.dumps({"format": 1, "files": {
        p.name: {"sha256": builder.digest(p), "bytes": p.stat().st_size, "url": builder.BASE_URL + p.name,
                 "last_modified": "Wed, 14 Oct 2026 02:20:00 GMT", "downloaded_utc": "2026-10-14T03:00:00+00:00"}
        for p in paths}}), encoding="utf-8")
    return manifest


def fixture_files(root, places=None, alternates=None, countries=None, admin1=ADMIN1):
    root.mkdir(parents=True, exist_ok=True)
    zipped(root / "allCountries.zip", "allCountries.txt", fixture_places() if places is None else places)
    zipped(root / "alternateNamesV2.zip", "alternateNamesV2.txt",
           ["\t".join(map(str, r)) for r in (ALTERNATES if alternates is None else alternates)])
    (root / "countryInfo.txt").write_text(country_info() if countries is None else countries, encoding="utf-8")
    (root / "admin1CodesASCII.txt").write_text(admin1, encoding="utf-8")
    paths = [root / n for n in builder.FILES]
    return paths, write_manifest(root, paths)


def make(root, output=None, **files):
    paths, manifest = fixture_files(root, **files)
    output = output or root / "atlas.db"
    summary = builder.build(*paths, manifest, output)
    return output, summary


def ro(path):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA trusted_schema = OFF")
    return conn


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("atlas")
    output, summary = make(root / "inputs", root / "atlas.db")
    return output, summary


@pytest.fixture
def db(built):
    with contextlib.closing(ro(built[0])) as conn:
        yield conn


# Thirty places of one name in one region: a qualified complete name lists
# every one of them, past the twenty a prefix lists.
CROWD = [place(2000 + i, "Crowd", pop=i) for i in range(30)]


@pytest.fixture(scope="module")
def cached_built(tmp_path_factory):
    """The fixture atlas with a work budget of nothing, so that every short
    prefix of every global and country range is written to the table of
    first twenties, and thirty places named "Crowd"."""
    root = tmp_path_factory.mktemp("cached")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(builder, "APP_CACHE_THRESHOLD", 0)
        output, summary = make(root / "inputs", root / "atlas.db", places=fixture_places() + CROWD)
    return output, summary


@pytest.fixture
def cached(cached_built, monkeypatch):
    # The search keeps the countries and regions it has read under the
    # shipped atlas's recorded digest: this atlas's own digest stands in
    # for it, so no other atlas's regions answer a qualifier here.
    import time_zones
    monkeypatch.setitem(time_zones.SHIPPED_DATA_SHA256, "atlas.db", builder.digest(cached_built[0]))
    with contextlib.closing(ro(cached_built[0])) as conn:
        yield conn


# --- the search's tables, as the builder's source tested them -------------------

def test_ranking(db):
    assert builder.matches(db, "Florence")[0]["country_code"] == "IT"
    assert builder.matches(db, "Paris")[0]["country_code"] == "FR"
    assert builder.matches(db, "Exact")[0]["name"] == "Exact"
    assert builder.matches(db, "Twin")[0]["geonameid"] == 22


@pytest.mark.parametrize("query, main, historic", [
    ("Königsberg", "Kaliningrad", False), ("Konigsberg", "Kaliningrad", False),
    ("Constantinople", "Istanbul", True), ("Byzantion", "Istanbul", True),
    ("Москва", "Москва", False), ("القاهرة", "القاهرة", False)])
def test_aliases(db, query, main, historic):
    result = builder.matches(db, query)[0]
    assert result["name"] == main
    assert result["historical_name"] is historic
    assert bool(result["matched"]) == (query != main)


def test_konigsberg_is_kaliningrad_and_not_historical_constantinople_is(db):
    """No place is given a historical name GeoNames does not mark so."""
    for search in (builder.matches, builder.matches_full):
        konigsberg = search(db, "Königsberg")
        assert [(r["geonameid"], r["name"], r["historical_name"]) for r in konigsberg] == [(8, "Kaliningrad", False)]
        constantinople = search(db, "Constantinople")
        assert [(r["geonameid"], r["name"], r["historical_name"]) for r in constantinople] == [
            (9, "Istanbul", True)]
    flags = db.execute("SELECT historic_name FROM atlas_keys WHERE matched = 'Königsberg'").fetchall()
    assert flags and set(flags) == {(0,)}
    assert "Kaliningrad" not in Path(builder.__file__).read_text(encoding="utf-8")
    assert "554234" not in Path(builder.__file__).read_text(encoding="utf-8")


@pytest.mark.parametrize("query", ["%", "_", "Flor%", '"', "*", "NEAR", "a OR b", "^", "NOT", "AND", "(x)", "-x",
                                   ":x", "a" * 300])
@pytest.mark.parametrize("search", [builder.matches, builder.matches_full])
def test_literal(db, query, search):
    """Every text is literal; one longer than the app's bound finds nothing."""
    expected = [query] if len(query) <= builder_text_max() else []
    assert [r["name"] for r in search(db, query)] == expected


def builder_text_max():
    import time_zones
    return time_zones.ATLAS_SEARCH_TEXT_MAX


def test_boundaries(db):
    assert builder.matches(db, "") == builder.matches(db, "  ") == []
    assert builder.matches(db, "F")
    assert builder.matches(db, "  Paris  ") == builder.matches(db, "Paris")
    assert builder.matches(db, "Paris", 0) == []
    assert len(builder.matches(db, "S", 1)) == 1
    with pytest.raises(ValueError):
        builder.matches(db, "x", -1)


def test_the_places_kept_and_their_flags(db):
    assert db.execute("SELECT COUNT(*) FROM places WHERE geonameid IN (16, 30)").fetchone()[0] == 0
    assert all(builder.matches(db, n)[0]["historical"] for n in ("Old Town", "Abandoned", "Destroyed"))
    assert not builder.matches(db, "Section")[0]["historical"]
    assert db.execute("SELECT COUNT(*) FROM places").fetchone()[0] == len(fixture_places()) - 3


def test_a_name_of_one_character_is_found_first_by_that_character(db, cached):
    """"Å", whose ASCII spelling is "a", ranks before every longer name,
    Århus and the 300 "a"s among them, from the table of first twenties
    and from the index range."""
    for conn in (db, cached):
        for text in ("Å", "a", "A"):
            short, full = builder.matches(conn, text), builder.matches_full(conn, text)
            assert short == full
            assert short[0]["name"] == "Å" and short[0]["matched"] is None, text
    assert cached.execute("SELECT COUNT(*) FROM atlas_prefix_results WHERE kind = 0 AND scope = '' "
                          "AND prefix = 'a'").fetchone()[0] >= 3


# --- inputs and the manifest -----------------------------------------------------

def test_a_manifest_mismatch_leaves_the_output_as_it_was(tmp_path):
    paths, manifest = fixture_files(tmp_path)
    target = tmp_path / "atlas.db"
    target.write_bytes(b"previous database")
    paths[3].write_text("corrupt", encoding="utf-8")
    with pytest.raises(builder.AtlasBuildError, match="Manifest mismatch: admin1CodesASCII.txt"):
        builder.build(*paths, manifest, target)
    assert target.read_bytes() == b"previous database"


def test_a_wrong_hash_of_the_same_size_is_refused(tmp_path):
    paths, manifest = fixture_files(tmp_path)
    data = json.loads(manifest.read_text())
    data["files"][paths[0].name]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(data))
    with pytest.raises(builder.AtlasBuildError, match="Manifest mismatch"):
        builder.build(*paths, manifest, tmp_path / "atlas.db")
    assert not (tmp_path / "atlas.db").exists()


def test_an_input_the_manifest_does_not_list_is_refused(tmp_path):
    paths, manifest = fixture_files(tmp_path)
    data = json.loads(manifest.read_text())
    del data["files"]["countryInfo.txt"]
    manifest.write_text(json.dumps(data))
    with pytest.raises(builder.AtlasBuildError, match="Manifest mismatch: countryInfo.txt"):
        builder.build(*paths, manifest, tmp_path / "atlas.db")


def test_the_dumps_may_be_given_as_text(tmp_path):
    paths, _manifest = fixture_files(tmp_path)
    for at, member in ((0, "allCountries.txt"), (1, "alternateNamesV2.txt")):
        with zipfile.ZipFile(paths[at]) as z:
            plain = tmp_path / member
            plain.write_bytes(z.read(member))
        paths[at] = plain
    manifest = write_manifest(tmp_path, paths)
    builder.build(*paths, manifest, tmp_path / "atlas.db")
    with contextlib.closing(ro(tmp_path / "atlas.db")) as conn:
        assert builder.matches(conn, "Paris")[0]["country_code"] == "FR"
        assert builder.matches(conn, "Konigsberg")[0]["name"] == "Kaliningrad"


def test_an_archive_without_its_member_is_refused(tmp_path):
    paths, _manifest = fixture_files(tmp_path)
    zipped(paths[0], "cities500.txt", fixture_places())
    manifest = write_manifest(tmp_path, paths)
    with pytest.raises(builder.AtlasBuildError, match="holds no member allCountries.txt"):
        builder.build(*paths, manifest, tmp_path / "atlas.db")


@pytest.mark.parametrize("at", [0, 1])
@pytest.mark.parametrize("damage", ["text", "cut"])
def test_a_file_named_as_an_archive_that_is_none_is_refused(tmp_path, at, damage):
    """A dump named .zip whose bytes are no zip archive (its text under the
    archive's name, or an archive cut short) is refused, never read as
    text; the output is not written."""
    paths, _manifest = fixture_files(tmp_path)
    data = paths[at].read_bytes()
    if damage == "text":
        with zipfile.ZipFile(paths[at]) as z:
            data = z.read(builder.INPUTS[at][1])
    else:
        data = data[:len(data) - 30]
    paths[at].write_bytes(data)
    manifest = write_manifest(tmp_path, paths)
    with pytest.raises(builder.AtlasBuildError, match=f"{paths[at].name} is not a zip archive"):
        builder.build(*paths, manifest, tmp_path / "atlas.db")
    assert not (tmp_path / "atlas.db").exists()


@pytest.mark.parametrize("at", [0, 1])
def test_an_archive_holding_its_member_twice_is_refused(tmp_path, at):
    """A second copy of the member under the same name is refused, whichever
    copy would have been read."""
    paths, _manifest = fixture_files(tmp_path)
    member = builder.INPUTS[at][1]
    with zipfile.ZipFile(paths[at]) as z:
        text = z.read(member)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")     # zipfile warns of the name written twice
        with zipfile.ZipFile(paths[at], "a") as z:
            z.writestr(zipfile.ZipInfo(member, date_time=ZIP_TIME), text)
    with zipfile.ZipFile(paths[at]) as z:
        assert z.namelist().count(member) == 2
    manifest = write_manifest(tmp_path, paths)
    with pytest.raises(builder.AtlasBuildError, match=f"holds the member {member} 2 times"):
        builder.build(*paths, manifest, tmp_path / "atlas.db")
    assert not (tmp_path / "atlas.db").exists()


def test_the_other_names_archive_may_hold_the_language_codes_beside_them(tmp_path):
    """GeoNames' alternateNamesV2.zip holds iso-languagecodes.txt too: the
    names are read from their own member."""
    paths, _manifest = fixture_files(tmp_path)
    with zipfile.ZipFile(paths[1], "a") as z:
        z.writestr(zipfile.ZipInfo("iso-languagecodes.txt", date_time=ZIP_TIME), "ISO 639-3\tName\n")
    manifest = write_manifest(tmp_path, paths)
    builder.build(*paths, manifest, tmp_path / "atlas.db")
    with contextlib.closing(ro(tmp_path / "atlas.db")) as conn:
        assert builder.matches(conn, "Byzantion")[0]["name"] == "Istanbul"


@pytest.mark.parametrize("at", [0, 1, 2, 3, 4])
def test_the_output_is_never_one_of_the_inputs(tmp_path, at):
    paths, manifest = fixture_files(tmp_path)
    target = (paths + [manifest])[at]
    kept = hashlib.sha256(target.read_bytes()).hexdigest()
    with pytest.raises(builder.AtlasBuildError, match="is one of the build's own inputs"):
        builder.build(*paths, manifest, tmp_path / "." / target.name)
    assert builder.digest(target) == kept
    assert not list(tmp_path.glob(".atlas-*"))


def test_an_id_repeated_in_a_later_batch_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "BATCH", 2)
    rows = [place(1, "Florence", "IT"), place(2, "Paris"), place(3, "Rome"), place(4, "Oslo"), place(2, "Again")]
    with pytest.raises(builder.AtlasBuildError, match="line 5 \\(geonameid 2\\): the id is repeated"):
        make(tmp_path, places=rows)
    output, _summary = make(tmp_path / "good", places=rows[:4])
    with contextlib.closing(ro(output)) as conn:
        assert [r[0] for r in conn.execute("SELECT id FROM cities ORDER BY id")] == [1, 2, 3, 4]


def test_a_parse_failure_leaves_the_output_and_no_temporary_file(tmp_path):
    paths, _manifest = fixture_files(tmp_path)
    zipped(paths[0], "allCountries.txt", ["broken\trow"])
    manifest = write_manifest(tmp_path, paths)
    output = tmp_path / "atlas.db"
    output.write_bytes(b"existing")
    with pytest.raises(builder.AtlasBuildError, match="line 1 has 2 columns, not 19"):
        builder.build(*paths, manifest, output)
    assert output.read_bytes() == b"existing"
    assert not list(tmp_path.glob(".atlas-*"))


def test_the_build_reads_no_network(tmp_path, monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("the build reached for the network")
    monkeypatch.setattr(builder.urllib.request, "urlopen", refused)
    output, _summary = make(tmp_path)
    assert output.exists()


def test_every_connection_the_build_opens_is_closed(tmp_path, monkeypatch):
    """A build that succeeds and one refused while the database is being
    written each close the connection they open."""
    import sqlite3
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
    make(tmp_path / "in", tmp_path / "atlas.db")
    built = len(made)
    monkeypatch.setattr(builder, "build_app_search", lambda conn: (_ for _ in ()).throw(builder.AtlasBuildError("x")))
    with pytest.raises(builder.AtlasBuildError):
        make(tmp_path / "in2", tmp_path / "atlas2.db")
    assert built >= 1 and len(made) > built and all(c.closed for c in made)


def test_the_atlas_is_written_beside_the_output_and_moved_into_place(tmp_path, monkeypatch):
    moved = []
    real = builder.os.replace
    monkeypatch.setattr(builder.os, "replace", lambda a, b: (moved.append((a, b)), real(a, b))[1])
    output, summary = make(tmp_path / "in", tmp_path / "out" / "atlas.db")
    assert len(moved) == 1 and Path(moved[0][0]).parent == tmp_path / "out" and Path(moved[0][1]) == output
    assert not Path(moved[0][0]).exists()
    assert output.stat().st_mode & 0o777 == 0o644
    assert summary["content_digest"] == builder.content_digest(output)


# --- the maintainer's download (a stand-in for the network) -----------------------

class _Response:
    def __init__(self, url, final=None, status=200):
        self._body, self._url, self.status = io.BytesIO(("bytes of " + url).encode()), final or url, status
        self.headers = {"Last-Modified": "Wed, 14 Oct 2026 02:20:00 GMT"}

    def geturl(self):
        return self._url

    def read(self, n=-1):
        return self._body.read(n)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_writes_the_four_files_and_their_manifest(monkeypatch, tmp_path):
    import datetime
    calls = []
    monkeypatch.setattr(builder.urllib.request, "urlopen",
                        lambda url, timeout, context: (calls.append((url, context)), _Response(url))[1])
    builder.fetch(tmp_path)
    manifest = json.loads((tmp_path / "MANIFEST.json").read_text())
    assert [url for url, _context in calls] == [builder.BASE_URL + name for name in builder.FILES]
    assert len(calls) == 4
    assert all(c.verify_mode == builder.ssl.CERT_REQUIRED and c.check_hostname for _url, c in calls)
    files = manifest["files"]
    assert len(files) == 4
    assert set(files) == set(builder.FILES)
    for name, entry in files.items():
        assert entry["url"] == builder.BASE_URL + name
        assert entry["sha256"] == builder.digest(tmp_path / name)
        assert entry["bytes"] == (tmp_path / name).stat().st_size
        assert entry["last_modified"] == "Wed, 14 Oct 2026 02:20:00 GMT"
        assert datetime.datetime.fromisoformat(entry["downloaded_utc"]).utcoffset() == datetime.timedelta(0)
    assert builder.BASE_URL.startswith("https://download.geonames.org/")


@pytest.mark.parametrize("final, status, said", [
    ("http://download.geonames.org/export/dump/allCountries.zip", 200, "which is not an https address"),
    (None, 203, "status 203")])
def test_fetch_refuses_a_plain_redirect_and_a_status_not_200(monkeypatch, tmp_path, final, status, said):
    monkeypatch.setattr(builder.urllib.request, "urlopen",
                        lambda url, timeout, context: _Response(url, final, status))
    with pytest.raises(builder.AtlasBuildError, match=said):
        builder.fetch(tmp_path)
    assert not (tmp_path / "MANIFEST.json").exists()


def test_fetch_never_writes_over_a_kept_file(monkeypatch, tmp_path):
    (tmp_path / "allCountries.zip").write_bytes(b"kept")
    monkeypatch.setattr(builder.urllib.request, "urlopen", lambda url, timeout, context: _Response(url))
    with pytest.raises(FileExistsError):
        builder.fetch(tmp_path)
    assert (tmp_path / "allCountries.zip").read_bytes() == b"kept"


# --- the short-prefix table --------------------------------------------------------

def test_every_fixture_prefix_agrees_with_the_full_search(db, cached):
    """Every short prefix of a plain key reads the same places from the
    table of first twenties as from its index range; at the ordinary budget
    the fixture's ranges are all small, so the table holds none of them."""
    prefixes = {key[:length] for (key,) in cached.execute("SELECT key FROM atlas_keys WHERE kinds & 3 <> 0")
                for length in builder.SHORT_PREFIX_LENGTHS if len(key) >= length}
    assert len(prefixes) > 100
    for prefix in sorted(prefixes):
        for limit in (20, 7):
            assert builder.matches(cached, prefix, limit) == builder.matches_full(cached, prefix, limit), (
                prefix, limit)
    stored = {prefix for (prefix,) in cached.execute(
        "SELECT DISTINCT prefix FROM atlas_prefix_results WHERE scope = '' AND kind < 2")}
    assert stored == prefixes
    assert db.execute("SELECT COUNT(*) FROM atlas_prefix_results").fetchone()[0] == 0


def test_the_short_prefix_table_is_the_full_search_at_twenty(cached):
    """Read off the table itself: each kind, scope and prefix's rows, rank by
    rank, are the index range's first twenty places and the keys it found
    them by."""
    stored = {}
    for kind, scope, prefix, rank, key_id, geonameid, matched in cached.execute(
            "SELECT c.kind, c.scope, c.prefix, c.rank, c.key_id, k.geonameid, k.matched "
            "FROM atlas_prefix_results c JOIN atlas_keys k ON k.id = c.key_id "
            "ORDER BY c.kind, c.scope, c.prefix, c.rank"):
        stored.setdefault((kind, scope, prefix), []).append((rank, key_id, geonameid, matched))
    assert len(stored) > 100
    assert {kind for kind, _scope, _prefix in stored} == {0, 1}     # no name here holds a word form
    assert {scope for _kind, scope, _prefix in stored} >= {"", "US", "US\x1f01"}
    for (kind, scope, prefix), rows in stored.items():
        # the stored prefix itself, not a typed text: a typed text is trimmed
        # first, so a prefix ending in a space ("a " of "a OR b") is read so
        full = time_zones_key_query(cached, kind, prefix, scope)
        assert rows == [(rank, r["key_id"], r["geonameid"], r["matched"])
                        for rank, r in enumerate(full, 1)], (kind, scope, prefix)
    assert max(len(rows) for rows in stored.values()) == 20
    assert len(stored[(0, "", "s")]) == 20 and len(stored[(0, "", "syn")]) == 20     # 220 places begin so
    meta = dict(cached.execute("SELECT key, value FROM metadata"))
    assert json.loads(meta["short_prefix_lengths"]) == [1, 2, 3, 4]
    assert meta["short_prefix_limit"] == "20"


def time_zones_key_query(conn, kind, prefix, scope):
    import time_zones
    return time_zones._atlas_key_query(conn.cursor(), kind, prefix, scope)


@pytest.mark.parametrize("prefix", ["М", "الق", "%", "_", '"', "*", "Ur", "Å"])
def test_a_short_prefix_reads_the_table(db, cached, prefix):
    """Where the prefix's range is broad (here, at a budget of nothing) the
    table alone is read; where it is small (the fixture at the ordinary
    budget) the table holds nothing for it and the range is ranked live;
    both give the same places."""
    for conn, table in ((cached, True), (db, False)):
        statements = []
        conn.set_trace_callback(statements.append)
        result = builder.matches(conn, prefix)
        conn.set_trace_callback(None)
        assert any("FROM atlas_prefix_results c" in sql for sql in statements)
        assert any("WITH candidates AS" in sql for sql in statements) is not table
        assert result == builder.matches_full(conn, prefix)
        assert result


def test_a_short_exact_name_ranks_before_a_larger_seat(db):
    result = builder.matches(db, "Ur")
    assert [(r["name"], r["matched"]) for r in result] == [("Ur", None), ("Uruk", None), ("Urbino", None)]


@pytest.mark.parametrize("limit", [21, 50])
def test_a_limit_above_twenty_takes_the_full_search(cached, limit):
    """A prefix lists twenty places whatever the limit; a qualified complete
    name lists every place of that name, cut only by a limit given."""
    result = builder.matches(cached, "S", limit)
    assert result == builder.matches_full(cached, "S", limit)
    assert len(result) == 20
    for text in ("Crowd (US)", "Crowd, 01", "Crowd, State (US)"):
        crowd = builder.matches(cached, text, limit)
        assert crowd == builder.matches_full(cached, text, limit)
        assert len(crowd) == min(limit, 30), text
        assert len(builder.matches(cached, text)) == 30
        assert {r["name"] for r in crowd} == {"Crowd"}
    assert len(builder.matches(cached, "Crowd")) == 20


def test_an_unseen_prefix_finds_nothing(db):
    assert builder.matches(db, "☂") == builder.matches_full(db, "☂") == []


def test_agreement_and_benchmark_run_on_a_built_atlas(built):
    report = builder.agreement(built[0], samples=30)
    assert {length: r["disagreements"] for length, r in report["agreement"].items()} == {
        "1": 0, "2": 0, "3": 0, "4": 0}
    timed = builder.benchmark(built[0], samples=5)
    assert sorted(timed["queries"], key=int) == ["1", "2", "3", "4", "5", "8"]


# --- what the app reads, against the shipped atlas's schema --------------------------

APP_TABLES = ("cities", "geonames_zones", "country_names", "admin1_names", "metadata")


def _columns(conn, table):
    return [(r[1], r[2]) for r in conn.execute(f"PRAGMA table_info({table})")]


def test_the_tables_the_app_reads_have_the_shipped_atlas_columns(db):
    with contextlib.closing(ro(SHIPPED_ATLAS)) as shipped:
        for table in APP_TABLES:
            assert _columns(db, table) == _columns(shipped, table), table
        shipped_keys = {k for (k,) in shipped.execute("SELECT key FROM metadata")}
    assert [name for name, _type in _columns(db, "cities")] == [
        "id", "name", "ascii_name", "admin1", "country", "lat", "lon", "population", "geonames_zone"]
    assert shipped_keys <= {k for (k,) in db.execute("SELECT key FROM metadata")}


def test_cities_is_a_view_whose_indexes_serve_the_lookup(db):
    """`cities` is a view over the places; the search's three key indexes,
    one per scope, each serve the range their scope reads."""
    kinds = dict(db.execute("SELECT name, type FROM sqlite_master WHERE name = 'cities'"))
    assert kinds == {"cities": "view"}
    assert not db.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'places' "
                          "AND sql IS NOT NULL").fetchall()
    indexes = {name: sql for name, sql in db.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'index' AND tbl_name = 'atlas_keys' AND sql IS NOT NULL")}
    assert indexes == {
        "atlas_key_range": "CREATE INDEX atlas_key_range ON atlas_keys(kinds, key)",
        "atlas_country_range": "CREATE INDEX atlas_country_range ON atlas_keys(country, kinds, key)",
        "atlas_region_range": "CREATE INDEX atlas_region_range ON atlas_keys(country, region, kinds, key)"}
    for scope, index in (("", "atlas_key_range"), ("US", "atlas_country_range"),
                         ("US\x1f01", "atlas_region_range")):
        statements = []
        db.set_trace_callback(statements.append)
        assert time_zones_key_query(db, 1, "flor", scope)
        db.set_trace_callback(None)
        plan = " ".join(r[3] for sql in statements for r in db.execute("EXPLAIN QUERY PLAN " + sql))
        assert f"SEARCH k USING INDEX {index} (" in plan, (scope, plan)
        assert "SCAN k" not in plan and "SCAN p" not in plan, (scope, plan)


def test_the_region_is_its_code_and_the_zone_geonames_own(db):
    rows = {r[0]: r for r in db.execute("SELECT * FROM cities")}
    assert rows[1][:8] == (1, "Florence", "florence", "01", "IT", 10.0, 20.0, 360000)
    assert rows[29][3] == "99"
    zones = dict(db.execute("SELECT c.id, z.name FROM cities c LEFT JOIN geonames_zones z ON z.id = c.geonames_zone"))
    assert zones[1] == "Europe/Rome" and zones[2] == "America/New_York" and zones[27] is None
    assert [name for _id, name in db.execute("SELECT id, name FROM geonames_zones ORDER BY id")] == sorted(
        {"Europe/Rome", "America/New_York", "Europe/Paris", "Etc/UTC"})


def test_the_country_and_region_names_with_geonames_ascii_spelling(db):
    assert db.execute("SELECT * FROM country_names ORDER BY country").fetchall() == sorted(
        (c, n) for c, n in COUNTRIES if c != "VE")                     # the dropped place's country is not carried
    regions = db.execute("SELECT * FROM admin1_names ORDER BY country, admin1").fetchall()
    assert ("IT", "01", "Toscana", "Tuscany") in regions             # name and ASCII spelling, as GeoNames gives
    assert ("RU", "99", None, None) in regions                        # a code with no row is kept, with none
    assert ("US", "01", "State", "State") in regions
    assert db.execute("SELECT admin1_name FROM places WHERE geonameid = 29").fetchone() == ("",)


def test_the_app_lookup_reads_the_built_atlas(built, monkeypatch):
    """time_zones.atlas_rows, unchanged, on the built atlas (its digest put
    in the shipped one's place): rows as (name, region code, country, lat,
    lon), the most populous first, the qualifiers read from the name tables."""
    import time_zones
    monkeypatch.setitem(time_zones.SHIPPED_DATA_SHA256, "atlas.db", builder.digest(built[0]))
    monkeypatch.setattr(time_zones, "ATLAS_FOLDED_NAMES", {})
    assert time_zones.atlas_rows(built[0], "Florence") == [
        ("Florence", "01", "IT", 10.0, 20.0), ("Florence", "01", "US", 10.0, 20.0)]
    assert time_zones.atlas_rows(built[0], "Florence, Tuscany") == [("Florence", "01", "IT", 10.0, 20.0)]
    assert time_zones.atlas_rows(built[0], "Florence, US") == [("Florence", "01", "US", 10.0, 20.0)]
    assert time_zones.atlas_rows(built[0], "La Aguada") == []


# --- the row checks and the drop list --------------------------------------------------

BAD_PLACES = [
    pytest.param(place(9001, "X", lat=95), "(geonameid 9001): the latitude 95.0 is outside -90 to 90", id="lat-95"),
    pytest.param(place(9001, "X", lon=400), "the longitude 400.0 is outside -180 to 180", id="lon-400"),
    pytest.param(place(9001, "X").rsplit("\t", 1)[0], "line 2 has 18 columns, not 19", id="short-row"),
    pytest.param(place(9001, "X") + "\textra", "line 2 has 20 columns, not 19", id="long-row"),
    pytest.param(place(9001, "Tab\tName", ascii_name="TabName"), "line 2 has 20 columns, not 19", id="tab-in-name"),
    pytest.param(place("9x", "X"), "line 2: the id '9x' is not a whole number", id="id-not-a-number"),
    pytest.param(place("-5", "X"), "line 2: the id '-5' is not a whole number", id="id-negative"),
    pytest.param(place(0, "X"), "line 2: the id '0' is not a whole number", id="id-zero"),
    pytest.param(place(9001, "X", lat="nan"), "the latitude 'nan' is not a decimal number", id="lat-nan"),
    pytest.param(place(9001, "X", lat="4e1"), "the latitude '4e1' is not a decimal number", id="lat-exponent"),
    pytest.param(place(9001, "X", lat=""), "the latitude '' is not a decimal number", id="lat-empty"),
    pytest.param(place(9001, "X", population="-1"), "the population '-1' is not a whole number",
                 id="population-negative"),
    pytest.param(place(9001, "X", population=""), "the population '' is not a whole number", id="population-empty"),
    pytest.param(place(9001, "X", population="12.5"), "the population '12.5' is not a whole number",
                 id="population-fraction"),
    pytest.param(place(9001, "X", "USA"), "the country 'USA' is not a two-letter code", id="country-three"),
    pytest.param(place(9001, "X", "us"), "the country 'us' is not a two-letter code", id="country-lower"),
    pytest.param(place(9001, "X", ""), "the country '' is not a two-letter code", id="country-empty"),
    pytest.param(place(9001, "X", zone="Europe/Atlantis"), "the zone 'Europe/Atlantis' is not one the pinned tzdata",
                 id="zone-unknown"),
    pytest.param(place(9001, "X", stamp="2024-13-01"), "the modification date '2024-13-01' is not a date",
                 id="date-bad"),
    pytest.param(place(9001, "Bell\x07"), "the name 'Bell\\x07' holds U+0007", id="control-in-name"),
    pytest.param(place(9001, "X", ascii_name="X\u202e"), "the ASCII name 'X\\u202e' holds U+202E",
                 id="format-in-ascii-name"),
    pytest.param(place(9001, "Line\u2028Sep"), "holds U+2028", id="line-separator-in-name"),
    pytest.param(place(9001, "Para\u2029Sep"), "holds U+2029", id="paragraph-separator-in-name"),
    pytest.param(place(9001, "X", admin1="0\x1f1"), "the region code '0\\x1f1' holds U+001F",
                 id="control-in-region-code"),
    pytest.param(place(1, "Again"), "line 2 (geonameid 1): the id is repeated", id="id-repeated"),
    pytest.param(place(9001, "X", "ZZ"), "countryInfo.txt gives no name for ZZ", id="country-unnamed"),
]


@pytest.mark.parametrize("bad, said", BAD_PLACES)
def test_a_failing_place_stops_the_build_and_is_named(tmp_path, bad, said):
    """The bad row is the second of three: nothing is skipped, nothing is
    written, and an atlas already in place is left as it was."""
    target = tmp_path / "atlas.db"
    target.write_bytes(b"the atlas in place")
    paths, manifest = fixture_files(tmp_path / "in", places=[place(1, "Florence", "IT"), bad, place(3, "Paris")])
    with pytest.raises(builder.AtlasBuildError) as raised:
        builder.build(*paths, manifest, target)
    assert said in str(raised.value), str(raised.value)
    assert target.read_bytes() == b"the atlas in place"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["atlas.db", "in"]


def test_a_place_of_another_class_is_left_out_unchecked_but_for_its_columns(tmp_path):
    output, _summary = make(tmp_path, places=[place(1, "Florence", "IT"), place(2, "Peak\x07", "", cls="T",
                                                                                 lat="x", population="")])
    with contextlib.closing(ro(output)) as conn:
        assert [r[0] for r in conn.execute("SELECT id FROM cities")] == [1]
    with pytest.raises(builder.AtlasBuildError, match="line 2 has 18 columns"):
        make(tmp_path / "again", places=[place(1, "Florence", "IT"), place(2, "Peak", cls="T").rsplit("\t", 1)[0]])


def test_the_dropped_place_is_checked_and_left_out_with_its_names(db, tmp_path):
    assert 3785489 in builder.DROPPED and "52 km" in builder.DROPPED[3785489]
    assert AGUADA in fixture_places()
    assert db.execute("SELECT COUNT(*) FROM places WHERE geonameid = 3785489").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM names WHERE geonameid = 3785489").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM atlas_keys WHERE geonameid = 3785489").fetchone()[0] == 0
    assert builder.matches(db, "La Aguada") == builder.matches(db, "Aguada") == []
    assert dict(db.execute("SELECT key, value FROM metadata"))["dropped_ids"] == "3785489 5854945 11695318 12564634 13110512"
    with pytest.raises(builder.AtlasBuildError, match="geonameid 3785489"):
        make(tmp_path, places=[place(1, "Florence", "IT"), place(3785489, "La Aguada", "VE", lat=95)])


def test_the_full_atlas_drops_la_aguada_and_four_more():
    """La Aguada, which the cities500 builder dropped too, with the same
    reason; two populated places (PPL, no seat of government) of population
    0, so GeoNames' cities500 file never carried them, whose names hold a
    control character; and two abandoned places (PPLQ) of population 0 in
    the United States Minor Outlying Islands, at sea, where the zone
    boundaries give only the ocean's band and GeoNames gives no zone."""
    assert set(builder.DROPPED) == {3785489, 5854945, 11695318, 12564634, 13110512}
    assert builder.DROPPED[3785489] == (
        "La Aguada (VE): its coordinates, 11.27667, -67.46444, lie at sea, about 52 km from the nearest point the "
        "zone boundaries give a country's zone, and GeoNames' own record gives the same point, so no source "
        "corrects it.")
    for gid, country, control in ((12564634, "(AR)", "U+0081"), (13110512, "(BR)", "U+0090")):
        reason = builder.DROPPED[gid]
        assert country in reason and control in reason and "no named source corrects it" in reason
        assert reason.isascii() and reason.isprintable()
    assert builder.DROPPED[5854945] == (
        "Millersville - pre-WW2 settlement (UM): its coordinates, -0.37027, -160.00453, lie at sea, where the zone "
        "boundaries give no country's zone, only the ocean's band, and GeoNames gives it no zone, so no clock can "
        "be given.")
    assert builder.DROPPED[11695318] == (
        "Kingman Reef (UM): its coordinates, 6.39948, -162.40015, lie at sea, where the zone boundaries give no "
        "country's zone, only the ocean's band, and GeoNames gives it no zone, so no clock can be given.")


def test_the_two_places_at_sea_are_checked_and_left_out(tmp_path):
    """Each as GeoNames gives it, with no zone: the build takes the row, and
    writes nothing of it."""
    at_sea = [place(5854945, "Millersville - pre-WW2 settlement", "UM", admin1="", pop=0, code="PPLQ",
                    lat="-0.37027", lon="-160.00453", zone=""),
              place(11695318, "Kingman Reef", "UM", admin1="", pop=0, code="PPLQ", lat="6.39948",
                    lon="-162.40015", zone="")]
    output, _summary = make(tmp_path, places=[place(1, "Florence", "IT")] + at_sea,
                            countries=country_info(COUNTRIES + [("UM", "U.S. Minor Outlying Islands")]))
    with contextlib.closing(ro(output)) as conn:
        assert [r[0] for r in conn.execute("SELECT id FROM cities")] == [1]
        assert conn.execute("SELECT COUNT(*) FROM atlas_keys WHERE geonameid IN (5854945, 11695318)").fetchone() == (0,)
        assert [c for (c,) in conn.execute("SELECT country FROM country_names")] == ["IT"]
        assert builder.matches(conn, "Kingman Reef") == builder.matches(conn, "Millersville") == []


WITH_AR_BR = country_info(COUNTRIES + [("AR", "Argentina"), ("BR", "Brazil")])
# GeoNames' two populated places whose names hold a C1 control character,
# each as GeoNames gives it.
BUODO = place(12564634, "Padre \u00c1\x81ngel Buodo", "AR", admin1="11", pop=0, ascii_name="Padre Angel Buodo")
IGARAPE = place(13110512, "Alto Igarap\u00e9\x90 A\u00e7u", "BR", admin1="16", pop=0, ascii_name="Alto Igarape Acu")


def test_a_dropped_place_whose_name_holds_a_control_builds_and_is_left_out(tmp_path, monkeypatch):
    """Its name, ASCII name and region code are not refused for a character
    no page prints; the place, its other names and its search keys are not
    written, and its country is not carried. Built at a work budget of
    nothing, so that every short prefix of a kept name is in the table."""
    monkeypatch.setattr(builder, "APP_CACHE_THRESHOLD", 0)
    buodo_in_full = place(12564634, "Padre \u00c1\x81ngel Buodo", "AR", admin1="1\x901", pop=0,
                          ascii_name="Padre Angel\u200e Buodo")
    output, _summary = make(tmp_path, places=[place(1, "Florence", "IT"), buodo_in_full, IGARAPE, AGUADA],
                            alternates=[(1, 12564634, "es", "Padre \u00c1ngel Buodo", "", "", "", "", "", ""),
                                        (2, 13110512, "pt", "Alto Igarap\u00e9 A\u00e7u", "", "", "", "", "", ""),
                                        (3, 1, "en", "Firenze", "", "", "", "", "", "")],
                            countries=WITH_AR_BR)
    dropped = (12564634, 13110512, 3785489)
    with contextlib.closing(ro(output)) as conn:
        for table, column in (("places", "geonameid"), ("names", "geonameid"), ("atlas_keys", "geonameid"),
                              ("cities", "id")):
            assert conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} IN (?, ?, ?)",
                                dropped).fetchone()[0] == 0, table
        assert conn.execute("SELECT COUNT(*) FROM atlas_prefix_results c JOIN atlas_keys k ON k.id = c.key_id "
                            "WHERE k.geonameid IN (?, ?, ?)", dropped).fetchone()[0] == 0
        assert conn.execute("SELECT 1 FROM atlas_prefix_results WHERE prefix IN ('f', 'fl')").fetchall()
        assert not conn.execute("SELECT 1 FROM atlas_prefix_results WHERE prefix IN ('p', 'pa', 'al', 'alt')"
                                ).fetchall()
        assert [r[0] for r in conn.execute("SELECT id FROM cities")] == [1]
        assert conn.execute("SELECT * FROM names").fetchall() == [(1, "Firenze", "en", 0, 0, 0, 0)]
        assert [c for (c,) in conn.execute("SELECT country FROM country_names")] == ["IT"]
        for text in ("Padre", "Padre \u00c1ngel", "Alto Igarap", "Alto Igarape Acu"):
            assert builder.matches(conn, text) == builder.matches_full(conn, text) == [], text
        assert dict(conn.execute("SELECT key, value FROM metadata"))["dropped_ids"] == "3785489 5854945 11695318 12564634 13110512"


@pytest.mark.parametrize("name, country, said", [
    pytest.param("Padre \u00c1\x81ngel Buodo", "AR",
                 "line 2 (geonameid 9002): the name 'Padre \u00c1\\x81ngel Buodo' holds U+0081, which no page "
                 "prints as itself.", id="u0081"),
    pytest.param("Alto Igarap\u00e9\x90 A\u00e7u", "BR",
                 "line 2 (geonameid 9002): the name 'Alto Igarap\u00e9\\x90 A\u00e7u' holds U+0090, which no page "
                 "prints as itself.", id="u0090"),
    pytest.param("La Aguada\x85", "VE", "line 2 (geonameid 9002): the name 'La Aguada\\x85' holds U+0085",
                 id="u0085"),
])
@pytest.mark.parametrize("listed", [12564634, 13110512, 3785489])
def test_a_control_in_a_name_stops_the_build_unless_its_row_is_dropped(tmp_path, name, country, said, listed):
    """The same row under an id not on the list (9002, or the id after a
    listed one) stops the build with the check's own message; under any id
    on the list it builds, and is left out."""
    for gid in (9002, listed + 1):
        with pytest.raises(builder.AtlasBuildError) as raised:
            make(tmp_path / str(gid), places=[place(1, "Florence", "IT"), place(gid, name, country, pop=0),
                                              place(3, "Paris")], countries=WITH_AR_BR)
        assert said.replace("9002", str(gid)) in str(raised.value), str(raised.value)
        assert not (tmp_path / str(gid) / "atlas.db").exists()
    output, _summary = make(tmp_path / "listed", countries=WITH_AR_BR, places=[
        place(1, "Florence", "IT"), place(listed, name, country, pop=0), place(3, "Paris")])
    with contextlib.closing(ro(output)) as conn:
        assert [r[0] for r in conn.execute("SELECT id FROM cities ORDER BY id")] == [1, 3]


@pytest.mark.parametrize("bad, said", [
    pytest.param(BUODO.replace("\t10\t20\t", "\t95\t20\t"), "(geonameid 12564634): the latitude 95.0 is outside",
                 id="latitude"),
    pytest.param(BUODO.replace("\t10\t20\t", "\t10\t200\t"), "(geonameid 12564634): the longitude 200.0",
                 id="longitude"),
    pytest.param(BUODO.rsplit("\t", 2)[0], "line 2 has 17 columns, not 19", id="two-columns-too-few"),
    pytest.param(BUODO.replace("Padre Angel Buodo", "Padre\tAngel Buodo"), "line 2 has 20 columns, not 19",
                 id="tab-in-ascii-name"),
    pytest.param(BUODO.replace("Padre \u00c1", "Padre\t\u00c1"), "line 2 has 20 columns, not 19", id="tab-in-name"),
    pytest.param(IGARAPE.replace("\tBR\t", "\tbr\t"), "(geonameid 13110512): the country 'br' is not",
                 id="country"),
    pytest.param(IGARAPE.replace("Etc/UTC", "Europe/Atlantis"), "(geonameid 13110512): the zone 'Europe/Atlantis'",
                 id="zone"),
    pytest.param(IGARAPE.replace("2026-01-02", "2026-02-30"), "(geonameid 13110512): the modification date",
                 id="date"),
    pytest.param(IGARAPE.replace("\t0\t\t0\t", "\t-1\t\t0\t"), "(geonameid 13110512): the population '-1'",
                 id="population"),
    pytest.param(IGARAPE.replace("13110512", "13110512x", 1), "the id '13110512x' is not a whole number",
                 id="id"),
])
def test_a_dropped_row_keeps_every_other_check(tmp_path, bad, said):
    """Only the characters of its name, ASCII name and region code are let
    pass; a row on the list that fails any other check stops the build."""
    with pytest.raises(builder.AtlasBuildError) as raised:
        make(tmp_path, places=[place(1, "Florence", "IT"), bad, place(3, "Paris")], countries=WITH_AR_BR)
    assert said in str(raised.value), str(raised.value)


def test_the_dropped_ids_are_recorded_in_order_whatever_the_list_order(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, "DROPPED", dict(reversed(list(builder.DROPPED.items()))))
    assert list(builder.DROPPED) == [11695318, 5854945, 13110512, 12564634, 3785489]
    output, _summary = make(tmp_path, places=[place(1, "Florence", "IT"), BUODO, IGARAPE], countries=WITH_AR_BR)
    with contextlib.closing(ro(output)) as conn:
        assert dict(conn.execute("SELECT key, value FROM metadata"))["dropped_ids"] == "3785489 5854945 11695318 12564634 13110512"
        assert [r[0] for r in conn.execute("SELECT id FROM cities")] == [1]


def test_the_other_names_kept(db):
    names = db.execute("SELECT geonameid, name, lang, is_preferred, is_historic FROM names "
                       "ORDER BY geonameid, name").fetchall()
    assert names == [(3, "Lutèce", "fr", 0, 1), (8, "Königsberg", "de", 0, 0), (9, "Byzantion", "en", 0, 1),
                     (9, "Constantinople", "en", 0, 1), (23, "Marseilles", "en", 1, 0), (24, "UR", "en", 0, 1)]
    # the place's own name again is no other name, and adds no search key:
    # its name and its ASCII spelling, typed and folded, are one key
    assert db.execute("SELECT kinds, key, matched FROM atlas_keys WHERE geonameid = 1").fetchall() == [
        (3, "florence", None)]
    # a name holding a character no page prints, or none, is left out and counted
    assert dict(db.execute("SELECT key, value FROM metadata"))["alternate_names_left_out"] == "2"
    assert not db.execute("SELECT 1 FROM atlas_keys WHERE key LIKE 'pa%ris' AND key <> 'paris'").fetchall()


@pytest.mark.parametrize("which", ["built", "cached_built"])
def test_each_search_key_is_written_once(request, which):
    """A place's name and its ASCII spelling can give one key: it is one
    row, and no scope of the table of first twenties lists a key or a
    place twice."""
    with contextlib.closing(ro(request.getfixturevalue(which)[0])) as conn:
        columns = "geonameid, kinds, key, matched, historic_name, country, region"
        rows = conn.execute(f"SELECT {columns} FROM atlas_keys").fetchall()
        assert rows
        assert len(rows) == len(set(rows))
        scopes = conn.execute("SELECT p.kind, p.scope, p.prefix, p.key_id, k.geonameid FROM atlas_prefix_results p "
                              "JOIN atlas_keys k ON k.id = p.key_id").fetchall()
        assert bool(scopes) == (which == "cached_built")
        assert len({s[:4] for s in scopes}) == len(scopes)
        assert len({s[:3] + s[4:] for s in scopes}) == len(scopes)


@pytest.mark.parametrize("bad, said", [
    pytest.param((20, 1, "en", "Short", "", "", "", ""), "line 1 has 8 columns, not 10", id="short"),
    pytest.param(("x", 1, "en", "Name", "", "", "", "", "", ""), "the id 'x' is not a whole number", id="id"),
    pytest.param((20, "", "en", "Name", "", "", "", "", "", ""), "the geonameid '' is not a whole number",
                 id="geonameid"),
    pytest.param((20, 1, "en", "Name", "", "", "", "2", "", ""), "the flag '2' is not empty, 0 or 1", id="flag"),
])
def test_a_failing_other_name_stops_the_build(tmp_path, bad, said):
    with pytest.raises(builder.AtlasBuildError, match=said):
        make(tmp_path, alternates=[bad])
    assert not (tmp_path / "atlas.db").exists()


def test_a_name_source_the_check_refuses_stops_the_build(tmp_path):
    with pytest.raises(builder.AtlasBuildError, match="row 'IT.01' is repeated"):
        make(tmp_path / "a", admin1=ADMIN1 + "IT.01\tTuscany\tTuscany\t1\n")
    with pytest.raises(builder.AtlasBuildError, match="holds '\"'; it is refused, not quoted"):
        make(tmp_path / "b", admin1=ADMIN1.replace("\tState\t", '\tSt"ate\t'))
    with pytest.raises(builder.AtlasBuildError, match="row 'IT': the name is blank"):
        make(tmp_path / "c", countries=country_info([(c, "" if c == "IT" else n) for c, n in COUNTRIES]))


# --- the record, and the same content from the same inputs ----------------------------

def test_the_metadata_table(built):
    with contextlib.closing(ro(built[0])) as conn:
        meta = dict(conn.execute("SELECT key, value FROM metadata"))
    sources = {f"{prefix}_{field}" for _name, _member, prefix in builder.INPUTS
               for field in ("url", "bytes", "sha256", "last_modified")}
    assert set(meta) == sources | {
        "dump_date", "python_version", "sqlite_version", "tzdata_version", "unicodedata_version", "dropped_ids",
        "rows", "backend", "normalization", "manifest", "short_prefix_lengths", "short_prefix_limit",
        "snapshot_download_dates_utc", "alternate_names_left_out", "app_search_version",
        "app_search_normalization", "app_cache_threshold", "app_cache_policy"}
    assert meta["app_search_version"] == "2"
    assert meta["normalization"] == meta["app_search_normalization"] == builder.NORMALIZATION
    assert meta["app_cache_threshold"] == str(builder.APP_CACHE_THRESHOLD) == "8192"
    assert meta["app_cache_policy"] == "scope-budget-divided-by-region-code-fanout"
    inputs, kinds = built[0].parent / "inputs", builder.INPUTS
    assert len(kinds) == 4
    for name, _member, prefix in kinds:
        assert meta[f"{prefix}_url"] == builder.BASE_URL + name
        assert meta[f"{prefix}_sha256"] == builder.digest(inputs / name)
        assert meta[f"{prefix}_bytes"] == str((inputs / name).stat().st_size)
        assert meta[f"{prefix}_last_modified"] == "Wed, 14 Oct 2026 02:20:00 GMT"
    assert json.loads(meta["manifest"]) == json.loads((inputs / "MANIFEST.json").read_text())
    assert meta["backend"] == "btree"
    assert meta["rows"] == str(len(fixture_places()) - 3)
    assert meta["dump_date"] == "2026-01-02"
    assert meta["python_version"] == builder.sys.version.split()[0]
    assert meta["unicodedata_version"] == builder.unicodedata.unidata_version
    assert meta["tzdata_version"] == builder.importlib.metadata.version("tzdata")
    assert meta["sqlite_version"] == sqlite3.sqlite_version


def test_two_builds_of_one_input_hold_the_same_content(tmp_path):
    first, summary = make(tmp_path / "one")
    second, again = make(tmp_path / "two")
    assert builder.content_digest(first) == builder.content_digest(second) == summary["content_digest"]
    assert summary["content_digest"] == again["content_digest"]
    third, other = make(tmp_path / "three", places=fixture_places()[:-1])
    assert other["content_digest"] != summary["content_digest"]


def test_the_builder_holds_no_full_text_index_no_plain_address_and_no_date():
    text = Path(builder.__file__).read_text(encoding="utf-8")
    assert "http://" not in text
    assert "fts" not in text.lower()
    assert not builder.re.search(r"\b(19|20)[0-9]{2}-[0-9]{2}-[0-9]{2}\b", text)
    assert "Creative Commons Attribution 4.0" in text


def test_the_command_line_builds_and_digests(tmp_path, capsys):
    paths, manifest = fixture_files(tmp_path)
    builder.main(["--build", "--places", str(paths[0]), "--alternates", str(paths[1]), "--countries",
                  str(paths[2]), "--admin1", str(paths[3]), "--manifest", str(manifest), "--output",
                  str(tmp_path / "atlas.db"), "--report", str(tmp_path / "report.json")])
    report = json.loads((tmp_path / "report.json").read_text())
    capsys.readouterr()
    builder.main(["--digest", str(tmp_path / "atlas.db")])
    assert json.loads(capsys.readouterr().out) == {"content_digest": report["content_digest"]}
    with pytest.raises(SystemExit):
        builder.main(["--build", "--places", str(paths[0])])
    assert hashlib.sha256((tmp_path / "atlas.db").read_bytes()).hexdigest() == builder.digest(tmp_path / "atlas.db")
    assert os.access(tmp_path / "atlas.db", os.R_OK)
