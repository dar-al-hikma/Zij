"""Build the offline place atlas from GeoNames' full dump, from files kept on disk.

    python -I build_atlas.py --build --places allCountries.zip --alternates alternateNamesV2.zip \\
        --countries countryInfo.txt --admin1 admin1CodesASCII.txt --manifest MANIFEST.json --output PATH
    python -I build_atlas.py --fetch FOLDER          (the maintainer's download step)
    python -I build_atlas.py --digest PATH           (a built atlas's content digest)
    python -I build_atlas.py --agreement PATH        (the table of first twenties against the index ranges)
    python -I build_atlas.py --benchmark PATH        (the search's speed)

Run it with the interpreter the app runs on: names are folded with that
interpreter's Unicode tables, and the database records which interpreter
built it.

The inputs are four files passed by path, each checked first against the
manifest (its size and SHA-256), which --fetch writes beside the files it
downloads: the places (allCountries.zip, or its text), their other names
(alternateNamesV2.zip, or its text), the countries (countryInfo.txt) and the
regions (admin1CodesASCII.txt). Nothing else is read, and nothing but --fetch
touches the network. GeoNames' files are daily snapshots: downloading again
does not give the same bytes, so keep the files and the manifest a build
was made from.

What the build does, in order:

- checks every populated place (feature class P) as the cities500 builder
  does: 19 columns, a whole-number id, a latitude from -90 to 90, a
  longitude from -180 to 180, a population that is a whole number, a
  two-letter country that countryInfo.txt names, a zone that is empty or
  one the pinned tzdata package holds, a modification date, and a name,
  ASCII name and region code holding no control, format character, line or
  paragraph separator, or lone surrogate. A row of any other class is
  checked for its 19 columns only, and left out. A row that fails stops the
  build, named by its line and id, and nothing is written;
- leaves out the rows listed in DROPPED, each with its reason. A row on the
  list is checked as every other is, except that its name, ASCII name and
  region code may hold a character no page prints: it is not written;
- keeps each place's other names, except the kinds in DROP_LANGS (links,
  codes and abbreviations), a name equal to the place's own, and a name
  holding a character no page prints (counted in the metadata); a name is
  marked historical only where GeoNames marks it so;
- writes, to a temporary file beside the output moved into place at the end:
  the places, with GeoNames' own zone for each kept as a record of the
  source (the app derives a place's zone from its coordinates); the view
  `cities` over the places, the region by its code; the names of the
  countries and regions the places carry; every name as the search folds it;
  four kinds of key sharing identical rows; for each broad scoped prefix
  of one to four characters, the first twenty places; and a metadata table
  saying where the data came from.

The data are GeoNames' (https://www.geonames.org/), licensed under the
Creative Commons Attribution 4.0 International licence
(https://creativecommons.org/licenses/by/4.0/). GeoNames provides the data
as is, with no warranty of accuracy, timeliness or completeness.
"""
import argparse
import contextlib
import csv
import datetime
import hashlib
import importlib.metadata
import importlib.resources
import json
import os
import random
import re
import sqlite3
import ssl
import statistics
import sys
import tempfile
import time
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

BASE_URL = "https://download.geonames.org/export/dump/"
# Each input: its file name, the text member its archive holds, and the
# prefix of its keys in the metadata table.
PLACES = ("allCountries.zip", "allCountries.txt", "source")
ALTERNATES = ("alternateNamesV2.zip", "alternateNamesV2.txt", "alternate_names")
COUNTRIES = ("countryInfo.txt", None, "country_info")
ADMIN1 = ("admin1CodesASCII.txt", None, "admin1_codes")
INPUTS = (PLACES, ALTERNATES, COUNTRIES, ADMIN1)
FILES = tuple(name for name, _member, _prefix in INPUTS)

COLUMNS = 19
ALTERNATE_COLUMNS = 10
COUNTRY_INFO_COLUMNS = 19
# The kinds of other name left out: links, postal, airport and other codes,
# abbreviations, and the French revolutionary names.
DROP_LANGS = frozenset({"link", "post", "iata", "icao", "faac", "fr_1793", "abbr", "wkdt", "unlc"})
# The feature codes of a place that is no longer one (historical, abandoned,
# destroyed).
HISTORICAL = frozenset({"PPLH", "PPLQ", "PPLW"})
SHORT_PREFIX_LENGTHS = (1, 2, 3, 4)
SHORT_PREFIX_LIMIT = 20
BACKEND = "btree"
NORMALIZATION = "NFC-casefold-Turkish-I-as-typed-first"
BATCH = 5000
SAMPLE_SEED = 1

_DECIMAL = re.compile(r"-?[0-9]+(\.[0-9]+)?")
_WHOLE = re.compile(r"[0-9]+")
_FLAG = re.compile(r"[01]?")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# Rows left out of the atlas, by GeoNames id, each with its reason. A row is
# corrected only from a named source; one that cannot be is dropped here.
DROPPED = {
    3785489: ("La Aguada (VE): its coordinates, 11.27667, -67.46444, lie at sea, about 52 km from the "
              "nearest point the zone boundaries give a country's zone, and GeoNames' own record gives the "
              "same point, so no source corrects it."),
    12564634: ("Padre Angel Buodo (AR): the name GeoNames gives it holds the control character U+0081, an "
               "encoding fault in the source, and no named source corrects it."),
    13110512: ("Alto Igarape Acu (BR): the name GeoNames gives it holds the control character U+0090, an "
               "encoding fault in the source, and no named source corrects it."),
    5854945: ("Millersville - pre-WW2 settlement (UM): its coordinates, -0.37027, -160.00453, lie at sea, "
              "where the zone boundaries give no country's zone, only the ocean's band, and GeoNames gives it "
              "no zone, so no clock can be given."),
    11695318: ("Kingman Reef (UM): its coordinates, 6.39948, -162.40015, lie at sea, where the zone boundaries "
               "give no country's zone, only the ocean's band, and GeoNames gives it no zone, so no clock can "
               "be given."),
}
# A country or region name holding one of these is refused, not quoted.
_REFUSED_IN_NAMES = ("\t", "\n", "\r", '"')
# What a place's name, ASCII name and region code may not hold: a control, a
# format character (the directional controls among them), a line or
# paragraph separator, or a lone surrogate. No page draws one as itself.
_UNPRINTED_CATEGORIES = frozenset(("Cc", "Cf", "Zl", "Zp", "Cs"))


class AtlasBuildError(ValueError):
    """An input, a manifest or a row the atlas is not built from."""


# --- deriving an ASCII alternate spelling ---------------------------------------

def normalize(text):
    """Derive an ASCII alias where NFKD can supply one, keeping punctuation.

    App comparisons use app_fold; this helper only derives alias keys.
    """
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold())
                   if not unicodedata.category(c).startswith("M"))


# --- the maintainer's download -------------------------------------------------

def digest(path):
    """The SHA-256 of a file, read in blocks."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(folder):
    """Download the four inputs over https into `folder`, none of whose files
    may exist yet, and write its MANIFEST.json: each file's address, size,
    SHA-256, the server's Last-Modified and the time it was downloaded."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    context = ssl.create_default_context()
    manifest = {"format": 1, "files": {}}
    for name in FILES:
        url = BASE_URL + name
        target = folder / name
        h, size = hashlib.sha256(), 0
        with urllib.request.urlopen(url, timeout=120, context=context) as response:
            final = response.geturl()
            if not final.startswith("https://"):
                raise AtlasBuildError(f"{url} was redirected to {final}, which is not an https address.")
            status = getattr(response, "status", None)
            if status != 200:
                raise AtlasBuildError(f"{url} answered with status {status}, not 200.")
            last_modified = response.headers.get("Last-Modified") or ""
            with open(target, "xb") as out:
                for block in iter(lambda: response.read(1 << 20), b""):
                    out.write(block)
                    h.update(block)
                    size += len(block)
        manifest["files"][name] = {
            "url": url, "bytes": size, "sha256": h.hexdigest(), "last_modified": last_modified,
            "downloaded_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        print("Downloaded", name, flush=True)
    with open(folder / "MANIFEST.json", "x", encoding="utf-8") as out:
        out.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


# --- reading and checking the inputs --------------------------------------------

def pinned_zone_names():
    """Every zone name the tzdata package holds (the package's own list)."""
    listing = importlib.resources.files("tzdata").joinpath("zones").read_text(encoding="utf-8")
    return frozenset(listing.split())


def checked_manifest(paths, manifest_path):
    """The manifest, after every input's size and SHA-256 are found equal to
    its entry for that file's name."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, dict):
        raise AtlasBuildError(f"{manifest_path} lists no files.")
    for path in paths:
        entry = files.get(Path(path).name)
        if (not isinstance(entry, dict) or Path(path).stat().st_size != entry.get("bytes")
                or digest(path) != entry.get("sha256")):
            raise AtlasBuildError(f"Manifest mismatch: {Path(path).name}")
    return manifest


@contextlib.contextmanager
def _lines(path, member):
    """The raw lines of an input: an archive's member read by its name, or
    the text file itself. A file named as a zip archive must be one, so a
    damaged archive is never read as text, and its member must be held
    exactly once, so no second copy of it is read in its place."""
    with contextlib.ExitStack() as stack:
        archived = zipfile.is_zipfile(path)
        if Path(path).name.lower().endswith(".zip") and not archived:
            raise AtlasBuildError(f"{Path(path).name} is not a zip archive.")
        if member is not None and archived:
            archive = stack.enter_context(zipfile.ZipFile(path))
            held = archive.namelist().count(member)
            if not held:
                raise AtlasBuildError(f"{Path(path).name} holds no member {member}.")
            if held != 1:
                raise AtlasBuildError(f"{Path(path).name} holds the member {member} {held} times.")
            yield stack.enter_context(archive.open(member))
        else:
            yield stack.enter_context(open(path, "rb"))


def _columns(raw, count, where):
    try:
        line = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise AtlasBuildError(f"{where} is not UTF-8 text.") from None
    if line.endswith("\n"):
        line = line[:-1]
    cols = line.split("\t")
    if len(cols) != count:
        raise AtlasBuildError(f"{where} has {len(cols)} columns, not {count}.")
    return cols


def _decimal(text, what, where, low, high):
    if not _DECIMAL.fullmatch(text):
        raise AtlasBuildError(f"{where}: the {what} {text!r} is not a decimal number.")
    value = float(text)
    if not low <= value <= high:
        raise AtlasBuildError(f"{where}: the {what} {value} is outside {low} to {high}.")
    return value


def _unprinted(text):
    return next((ch for ch in text if unicodedata.category(ch) in _UNPRINTED_CATEGORIES), None)


def _refuse_unprinted(text, what, where):
    ch = _unprinted(text)
    if ch is not None:
        raise AtlasBuildError(f"{where}: the {what} {text!r} holds U+{ord(ch):04X}, "
                              f"which no page prints as itself.")


def place_row(number, raw, zones, member=PLACES[1], dropped=()):
    """One line of the places' dump, checked: None for a row that is not a
    populated place (feature class P), else (id, name, ascii_name,
    feature_code, country, admin1, admin2, lat, lon, population, zone or
    None, modification date). A row whose id is in `dropped` is one the
    caller leaves out: every check holds for it but that of the characters
    of its name, ASCII name and region code, which are never written."""
    where = f"{member} line {number}"
    cols = _columns(raw, COLUMNS, where)
    if cols[6] != "P":
        return None
    if not _WHOLE.fullmatch(cols[0]) or int(cols[0]) == 0:
        raise AtlasBuildError(f"{where}: the id {cols[0]!r} is not a whole number.")
    where = f"{where} (geonameid {cols[0]})"
    lat = _decimal(cols[4], "latitude", where, -90, 90)
    lon = _decimal(cols[5], "longitude", where, -180, 180)
    if not _WHOLE.fullmatch(cols[14]):
        raise AtlasBuildError(f"{where}: the population {cols[14]!r} is not a whole number.")
    country = cols[8]
    if not (len(country) == 2 and country.isascii() and country.isalpha() and country.isupper()):
        raise AtlasBuildError(f"{where}: the country {country!r} is not a two-letter code.")
    zone = cols[17]
    if zone and zone not in zones:
        raise AtlasBuildError(f"{where}: the zone {zone!r} is not one the pinned tzdata package holds.")
    stamp = cols[18]
    try:
        if not _DATE.fullmatch(stamp):
            raise ValueError(stamp)
        datetime.date.fromisoformat(stamp)
    except ValueError:
        raise AtlasBuildError(f"{where}: the modification date {stamp!r} is not a date.") from None
    if int(cols[0]) not in dropped:
        for column, what in ((1, "name"), (2, "ASCII name"), (10, "region code")):
            _refuse_unprinted(cols[column], what, where)
    return (int(cols[0]), cols[1], cols[2], cols[7], country, cols[10], cols[11], lat, lon, int(cols[14]),
            zone or None, stamp)


def alternate_row(number, raw, member=ALTERNATES[1]):
    """One line of the other names' dump, checked: (geonameid, name, lang,
    preferred, short, colloquial, historic), or None for a kind in
    DROP_LANGS; a name that is empty or holds a character no page prints is
    "left out" in place of the tuple."""
    where = f"{member} line {number}"
    cols = _columns(raw, ALTERNATE_COLUMNS, where)
    for column, what in ((0, "id"), (1, "geonameid")):
        if not _WHOLE.fullmatch(cols[column]):
            raise AtlasBuildError(f"{where}: the {what} {cols[column]!r} is not a whole number.")
    for column in range(4, 8):
        if not _FLAG.fullmatch(cols[column]):
            raise AtlasBuildError(f"{where}: the flag {cols[column]!r} is not empty, 0 or 1.")
    if cols[2] in DROP_LANGS:
        return None
    if not cols[3] or _unprinted(cols[3]) is not None:
        return "left out"
    return (int(cols[1]), cols[3], cols[2], *(int(v or 0) for v in cols[4:8]))


def _source_rows(path):
    """GeoNames' tab-separated rows, comment and blank lines aside, read as
    plain text with no quoting."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if row and row[0] and not row[0].startswith("#"):
                yield row


def _checked_name(name, where):
    if not name:
        raise AtlasBuildError(f"{where}: the name is blank.")
    marks = [repr(mark) for mark in _REFUSED_IN_NAMES if mark in name]
    if marks:
        raise AtlasBuildError(f"{where}: the name {name!r} holds {', '.join(marks)}; it is refused, not quoted.")
    return name


def read_country_names(path):
    """{country code: name} from countryInfo.txt, its fifth column."""
    countries = {}
    for row in _source_rows(path):
        where = f"countryInfo.txt row {row[0]!r}"
        if len(row) != COUNTRY_INFO_COLUMNS:
            raise AtlasBuildError(f"{where} has {len(row)} columns, not {COUNTRY_INFO_COLUMNS}.")
        if row[0] in countries:
            raise AtlasBuildError(f"{where} is repeated.")
        countries[row[0]] = _checked_name(row[4], where)
    return countries


def read_region_names(path):
    """{(country code, admin1 code): (name, ascii name)} from
    admin1CodesASCII.txt. The codes are kept as text: a blank code and "00"
    are different keys."""
    regions = {}
    for row in _source_rows(path):
        where = f"admin1CodesASCII.txt row {row[0]!r}"
        if len(row) != 4 or "." not in row[0]:
            raise AtlasBuildError(f"{where} is not a code, a name, an ASCII name and an id.")
        key = tuple(row[0].split(".", 1))
        if key in regions:
            raise AtlasBuildError(f"{where} is repeated.")
        if row[2]:
            _checked_name(row[2], where)
        regions[key] = (_checked_name(row[1], where), row[2])
    return regions


# --- the database --------------------------------------------------------------

SCHEMA = """
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE places (geonameid INTEGER PRIMARY KEY, name TEXT NOT NULL, ascii_name TEXT,
  feature_code TEXT, country_code TEXT, country_name TEXT, admin1_code TEXT, admin1_name TEXT,
  admin2_code TEXT, lat REAL, lon REAL, population INTEGER,
  historical INTEGER CHECK (historical IN (0, 1)), geonames_zone INTEGER);
CREATE TABLE names (geonameid INTEGER, name TEXT, lang TEXT,
  is_preferred INTEGER, is_short INTEGER, is_colloquial INTEGER, is_historic INTEGER);
"""

# The places in the nine columns of the atlas's earlier table: the region
# by its code and GeoNames' zone by its number in geonames_zones. The app
# reads the places through the indexed search, not this view; a view keeps
# these columns without copying the places.
CITIES_VIEW = """
CREATE VIEW cities AS SELECT geonameid AS id, name, ascii_name, admin1_code AS admin1,
  country_code AS country, lat, lon, population, geonames_zone FROM places;
"""


def _load_places(conn, path, zones, countries, regions):
    """The places, checked, into `places` (the zone as its name for now);
    the newest modification date among them."""
    newest, batch, unnamed = "", [], set()

    def flush():
        ids = [row[0] for row, _number in batch]
        seen = {gid for (gid,) in conn.execute(
            f"SELECT geonameid FROM places WHERE geonameid IN ({','.join('?' * len(ids))})", ids)} if ids else set()
        for row, number in batch:
            if row[0] in seen:
                raise AtlasBuildError(f"{PLACES[1]} line {number} (geonameid {row[0]}): the id is repeated.")
            seen.add(row[0])
        conn.executemany("INSERT INTO places VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            (gid, name, ascii_name, feature, country, countries.get(country, ""), admin1,
             regions.get((country, admin1), ("", ""))[0], admin2, lat, lon, population,
             int(feature in HISTORICAL), zone)
            for (gid, name, ascii_name, feature, country, admin1, admin2, lat, lon, population, zone, _stamp),
            _number in batch])
        batch.clear()

    with _lines(path, PLACES[1]) as source:
        for number, raw in enumerate(source, 1):
            # The drop list is read inside place_row, once the id is known
            # to be a whole number, so a dropped row keeps every other check.
            row = place_row(number, raw, zones, dropped=DROPPED)
            if row is None:
                continue
            if row[4] not in countries:
                unnamed.add(row[4])
            if row[0] in DROPPED:
                continue
            newest = max(newest, row[11])
            batch.append((row, number))
            if len(batch) >= BATCH:
                flush()
    flush()
    if unnamed:
        raise AtlasBuildError(f"countryInfo.txt gives no name for {', '.join(sorted(unnamed))}.")
    if not newest:
        raise AtlasBuildError(f"{PLACES[1]} holds no populated place.")
    return newest


def _number_zones(conn):
    """GeoNames' zones, numbered in the order of their names, and each
    place's zone replaced by its number."""
    conn.execute("CREATE TABLE geonames_zones (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
    conn.execute("""INSERT INTO geonames_zones (id, name)
                    SELECT ROW_NUMBER() OVER (ORDER BY zone), zone
                    FROM (SELECT DISTINCT geonames_zone AS zone FROM places WHERE geonames_zone IS NOT NULL)""")
    conn.execute("""UPDATE places SET geonames_zone = (SELECT id FROM geonames_zones z
                                                       WHERE z.name = places.geonames_zone)
                    WHERE geonames_zone IS NOT NULL""")


def _load_names(conn, path):
    """The other names of the places kept, into `names`: the number left out
    for holding a character no page prints, or for being empty."""
    conn.execute("CREATE TABLE staging (geonameid INTEGER, name TEXT, lang TEXT, "
                 "p INTEGER, s INTEGER, c INTEGER, h INTEGER)")
    left_out = 0

    def rows(source):
        nonlocal left_out
        for number, raw in enumerate(source, 1):
            row = alternate_row(number, raw)
            if row == "left out":
                left_out += 1
            elif row is not None:
                yield row
    with _lines(path, ALTERNATES[1]) as source:
        conn.executemany("INSERT INTO staging VALUES (?,?,?,?,?,?,?)", rows(source))
    # A name equal to the place's own is not another name.
    conn.execute("""INSERT INTO names SELECT DISTINCT s.* FROM staging s
                    JOIN places p ON p.geonameid = s.geonameid WHERE s.name <> p.name
                    ORDER BY s.geonameid, s.name, s.lang, s.p, s.s, s.c, s.h""")
    conn.execute("DROP TABLE staging")
    conn.execute("CREATE INDEX names_place ON names(geonameid)")
    return left_out


def app_fold(text):
    """The app's NFC casefold, including dotted and dotless Turkish I."""
    folded = unicodedata.normalize('NFC', text or '').replace('\u0130', 'i').casefold()
    return folded.replace('\u0131', 'i').replace('i\u0307', 'i')


APP_WORD_FORMS = (('saint', 'sankt', 'st'), ('sainte', 'ste'), ('fort', 'ft'), ('mount', 'mt'))
APP_ASCII_LOWER = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')
APP_WORD_PATTERN = re.compile(r'(?<![^ ,\-])(' + '|'.join(
    sorted((form for forms in APP_WORD_FORMS for form in forms), key=lambda form: -len(form)))
    + r')(?:\.[ \-]*|[ \-]+|$)')
APP_WORD_GROUP = {form: group for group, forms in enumerate(APP_WORD_FORMS) for form in forms}


def app_keys(spelling):
    """Raw and folded prefixes, with whole abbreviation words recognized.

    A name has a key after each successive whole word is replaced. Leaving
    the remaining suffix literal also lets a final, incomplete word be
    typed: a bare St still begins Stuttgart, or St. at the end of a name.
    Reserved separators cannot occur in a source spelling or a typed text.
    """
    for kind, key in ((0, spelling.translate(APP_ASCII_LOWER)), (1, app_fold(spelling))):
        yield kind, key
        head, at = '', 0
        seen = set()
        for match in APP_WORD_PATTERN.finditer(key):
            head += key[at:match.start()] + '\x1f' + str(APP_WORD_GROUP[match[1]]) + '\x1f'
            at = match.end()
            variant = head + key[at:]
            if variant not in seen:
                seen.add(variant)
                yield kind + 2, variant


APP_CACHE_THRESHOLD = 8192


def build_app_search(conn):
    """Index four key kinds and cache only broad short-prefix ranges.

    A country and a region each have their own key range. Identical keys
    share a kind bit mask. Small ranges are ranked live; only ranges
    exceeding the scoped work budget have a materialized first twenty.
    Exact qualified names use equality ranges directly and are never
    limited by this table.
    """
    started = time.perf_counter()
    conn.executescript("""
      CREATE TABLE atlas_keys (id INTEGER PRIMARY KEY, geonameid INTEGER NOT NULL,
        kinds INTEGER NOT NULL, key TEXT NOT NULL, matched TEXT, historic_name INTEGER NOT NULL,
        country TEXT NOT NULL, region TEXT NOT NULL);
      CREATE TABLE atlas_prefix_results (
        kind INTEGER NOT NULL, scope TEXT NOT NULL, prefix TEXT NOT NULL,
        rank INTEGER NOT NULL CHECK (rank BETWEEN 1 AND 20), key_id INTEGER NOT NULL,
        PRIMARY KEY (kind, scope, prefix, rank)) WITHOUT ROWID;
    """)
    # A place's name and its ASCII spelling can give the same key: the
    # rows are gathered first and each is written once, in the order it
    # first came. Grouping, not a unique index: a unique index holds rows
    # that match no other name as all distinct, and those are the rows
    # that repeat.
    conn.execute('CREATE TEMP TABLE key_rows (geonameid, kinds, key, matched, historic_name, country, region)')
    source = conn.execute("""
      SELECT geonameid, name, NULL, 0, country_code, admin1_code FROM places
      UNION ALL SELECT geonameid, ascii_name, NULL, 0, country_code, admin1_code FROM places
        WHERE ascii_name <> '' AND ascii_name <> name
      UNION ALL SELECT n.geonameid, n.name, n.name, MIN(n.is_historic), p.country_code, p.admin1_code
        FROM names n JOIN places p ON p.geonameid = n.geonameid
        GROUP BY n.geonameid, n.name
    """)

    def rows():
        for gid, spelling, matched, historic, country, region in source:
            spellings = [spelling]
            ascii_key = normalize(spelling)
            if matched is not None and ascii_key.isascii() and ascii_key != app_fold(spelling):
                spellings.append(ascii_key)
            kinds = {}
            for written in spellings:
                for kind, key in app_keys(written):
                    kinds[key] = kinds.get(key, 0) | (1 << kind)
            for key, mask in kinds.items():
                yield gid, mask, key, matched, historic, country, region
    conn.executemany('INSERT INTO key_rows VALUES (?, ?, ?, ?, ?, ?, ?)', rows())
    conn.execute('INSERT INTO atlas_keys (geonameid, kinds, key, matched, historic_name, country, region) '
                 'SELECT geonameid, kinds, key, matched, historic_name, country, region FROM key_rows '
                 'GROUP BY geonameid, kinds, key, matched, historic_name, country, region ORDER BY MIN(rowid)')
    conn.execute('DROP TABLE key_rows')
    conn.execute('CREATE INDEX atlas_key_range ON atlas_keys(kinds, key)')
    conn.execute('CREATE INDEX atlas_country_range ON atlas_keys(country, kinds, key)')
    conn.execute('CREATE INDEX atlas_region_range ON atlas_keys(country, region, kinds, key)')
    build_app_prefixes(conn)
    return time.perf_counter() - started


def build_app_prefixes(conn, regions_only=False):
    """Budget live work across regions that share a qualifier code.

    Global and country ranges use APP_CACHE_THRESHOLD key rows. Regions
    divide that budget by their code's country count: a code such as 01
    must search those regions together. Cache broader ranges, and rank
    smaller ones live. An empty region code has no qualifier fanout.
    """
    started = time.perf_counter()
    conn.execute("CREATE TEMP TABLE region_fanout AS SELECT region, "
                 "CASE WHEN region = '' THEN 1 ELSE COUNT(*) END AS n FROM "
                 "(SELECT DISTINCT country_code AS country, admin1_code AS region FROM places) GROUP BY region")
    conn.execute('CREATE UNIQUE INDEX region_fanout_key ON region_fanout(region)')
    for kind in range(4):
        for length in SHORT_PREFIX_LENGTHS:
            print(f"Ranking broad app comparison {kind}, prefix length {length}", flush=True)
            scope_options = ["k.country || char(31) || k.region"] if regions_only else [
                "''", "k.country", "k.country || char(31) || k.region"]
            for scope in scope_options:
                threshold = ('max(1, ?3 / (SELECT n FROM region_fanout WHERE region = k.region))'
                             if 'char(31)' in scope else '?3')
                conn.execute('CREATE TEMP TABLE broad_prefixes AS SELECT ' + scope + " AS scope, "
                    'substr(k.key, 1, ?2) AS prefix FROM atlas_keys k '
                    'WHERE k.kinds IN (1 << ?1, CASE WHEN ?1 < 2 THEN 3 ELSE 12 END) AND length(k.key) >= ?2 GROUP BY scope, prefix HAVING COUNT(*) > ' + threshold,
                    (kind, length, APP_CACHE_THRESHOLD))
                conn.execute('CREATE UNIQUE INDEX broad_prefixes_key ON broad_prefixes(scope, prefix)')
                conn.execute("""
                  INSERT OR IGNORE INTO atlas_prefix_results (kind, scope, prefix, rank, key_id)
                  WITH candidates AS (
                    SELECT b.scope, b.prefix, k.id AS key_id, k.geonameid,
                           (k.key = b.prefix) AS exact, k.historic_name,
                           ROW_NUMBER() OVER (
                             PARTITION BY b.scope, b.prefix, k.geonameid
                             ORDER BY (k.key = b.prefix) DESC, k.historic_name,
                               (k.matched IS NOT NULL), COALESCE(k.matched, ''), k.id) AS choice
                    FROM atlas_keys k JOIN broad_prefixes b
                      ON b.scope = """ + scope + """ AND b.prefix = substr(k.key, 1, ?2)
                    WHERE k.kinds IN (1 << ?1, CASE WHEN ?1 < 2 THEN 3 ELSE 12 END) AND length(k.key) >= ?2
                  ), ordered AS (
                    SELECT c.scope, c.prefix, c.key_id, ROW_NUMBER() OVER (
                      PARTITION BY c.scope, c.prefix
                      ORDER BY c.exact DESC, p.feature_code IN ('PPLC', 'PPLG', 'PPLA') DESC,
                        p.population DESC, p.historical, c.historic_name, c.geonameid) AS position
                    FROM candidates c JOIN places p ON p.geonameid = c.geonameid WHERE c.choice = 1
                  ) SELECT ?1, scope, prefix, position, key_id FROM ordered WHERE position <= 20
                """, (kind, length))
                conn.execute('DROP TABLE broad_prefixes')
    conn.execute('DROP TABLE region_fanout')
    return time.perf_counter() - started


def _write_names(conn, countries, regions):
    """The country and region name tables the app's lookup reads, for every
    country and every (country, admin1) pair the places carry; a pair
    GeoNames gives no name is kept, with none."""
    pairs = conn.execute("SELECT country_code, admin1_code, COUNT(*) FROM places "
                         "GROUP BY country_code, admin1_code ORDER BY country_code, admin1_code").fetchall()
    wanted = sorted({country for country, _admin1, _count in pairs})
    conn.execute("CREATE TABLE country_names (country TEXT PRIMARY KEY, name TEXT NOT NULL)")
    conn.executemany("INSERT INTO country_names VALUES (?, ?)", [(c, countries[c]) for c in wanted])
    conn.execute("CREATE TABLE admin1_names (country TEXT NOT NULL, admin1 TEXT NOT NULL, name TEXT, "
                 "ascii_name TEXT, PRIMARY KEY (country, admin1))")
    conn.executemany("INSERT INTO admin1_names VALUES (?, ?, ?, ?)",
                     [(c, a, *regions.get((c, a), (None, None))) for c, a, _n in pairs])
    return {"countries": len(wanted), "admin1_pairs": len(pairs),
            "unnamed_admin1_pairs": sum(1 for c, a, _n in pairs if (c, a) not in regions),
            "places_without_region_name": sum(n for c, a, n in pairs if (c, a) not in regions)}


def build(places, alternates, countries_path, admin1_path, manifest_path, output):
    """Check the inputs against the manifest, then every row, and write the
    atlas to `output` (a temporary file beside it, moved into place at the
    end; an atlas already there is left as it was on any failure). A summary
    of what was written."""
    started = time.perf_counter()
    paths = [Path(places), Path(alternates), Path(countries_path), Path(admin1_path)]
    output = Path(output)
    if output.resolve() in {Path(p).resolve() for p in (*paths, manifest_path)}:
        raise AtlasBuildError(f"{output} is one of the build's own inputs; the atlas is written elsewhere.")
    manifest = checked_manifest(paths, manifest_path)
    zones = pinned_zone_names()
    countries = read_country_names(paths[2])
    regions = read_region_names(paths[3])
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".atlas-", suffix=".building", dir=output.parent)
    os.close(fd)
    conn = None
    try:
        conn = sqlite3.connect(temporary)
        conn.execute("PRAGMA cache_size = -32768")
        conn.execute("PRAGMA temp_store = FILE")
        conn.executescript(SCHEMA)
        print("Loading places", flush=True)
        newest = _load_places(conn, paths[0], zones, countries, regions)
        _number_zones(conn)
        print("Loading other names", flush=True)
        left_out = _load_names(conn, paths[1])
        print("Indexing the app's search", flush=True)
        app_search_seconds = build_app_search(conn)
        conn.executescript(CITIES_VIEW)
        counts = _write_names(conn, countries, regions)
        rows = conn.execute("SELECT COUNT(*) FROM places").fetchone()[0]
        metadata = {
            "rows": str(rows),
            "dropped_ids": " ".join(str(gid) for gid in sorted(DROPPED)),
            "dump_date": newest,
            "python_version": sys.version.split()[0],
            "unicodedata_version": unicodedata.unidata_version,
            "sqlite_version": sqlite3.sqlite_version,
            "tzdata_version": importlib.metadata.version("tzdata"),
            "backend": BACKEND,
            "normalization": NORMALIZATION,
            "manifest": json.dumps(manifest, sort_keys=True),
            "short_prefix_lengths": json.dumps(list(SHORT_PREFIX_LENGTHS)),
            "short_prefix_limit": str(SHORT_PREFIX_LIMIT),
            "snapshot_download_dates_utc": json.dumps(
                {name: entry.get("downloaded_utc") for name, entry in manifest["files"].items()}, sort_keys=True),
            "alternate_names_left_out": str(left_out),
            "app_search_version": "2",
            "app_search_normalization": "NFC-casefold-Turkish-I-as-typed-first",
            "app_cache_threshold": str(APP_CACHE_THRESHOLD),
            "app_cache_policy": "scope-budget-divided-by-region-code-fanout",
        }
        for path, (_name, _member, prefix) in zip(paths, INPUTS):
            entry = manifest["files"][path.name]
            metadata.update({f"{prefix}_url": str(entry.get("url") or ""),
                             f"{prefix}_last_modified": str(entry.get("last_modified") or ""),
                             f"{prefix}_sha256": entry["sha256"], f"{prefix}_bytes": str(entry["bytes"])})
        conn.executemany("INSERT INTO metadata VALUES (?, ?)", sorted(metadata.items()))
        conn.commit()
        conn.execute("VACUUM")
        conn.execute("ANALYZE")
        conn.commit()
        tables = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("places", "names", "geonames_zones",
                            "country_names", "admin1_names", "metadata", "atlas_keys", "atlas_prefix_results")}
        conn.close()
        conn = None
        # mkstemp makes the file for its owner alone; the atlas is read by
        # whoever runs the app.
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    finally:
        if conn is not None:
            conn.close()
        Path(temporary).unlink(missing_ok=True)
    return {"output": str(output), "bytes": output.stat().st_size, "rows": tables, **counts,
            "content_digest": content_digest(output), "build_seconds": round(time.perf_counter() - started, 3),
            "app_search_seconds": round(app_search_seconds, 3), "runtime": runtime_info()}


def content_digest(path):
    """The SHA-256 of a built atlas's content: every object's definition and
    every table's rows in a fixed order. Two builds of the same inputs with
    the same interpreter give the same digest, whatever their pages hold."""
    h = hashlib.sha256()
    with contextlib.closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        objects = conn.execute("SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' "
                               "ORDER BY type, name").fetchall()
        for kind, name, sql in objects:
            h.update(repr((kind, name, sql)).encode("utf-8"))
            if kind != "table":
                continue
            width = len(conn.execute(f'SELECT * FROM "{name}" LIMIT 0').description)
            order = ", ".join(str(i) for i in range(1, width + 1))
            for row in conn.execute(f'SELECT * FROM "{name}" ORDER BY {order}'):
                h.update(repr(row).encode("utf-8"))
    return h.hexdigest()


# --- the app search exposed to build checks -------------------------------------

def _app_matches(conn, text, limit, use_short):
    """Use the app's search and keep the builder's place detail fields."""
    from time_zones import _atlas_search_matches
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("limit must be a nonnegative integer")
    if not limit:
        return []
    details = _atlas_search_matches(conn.cursor(), text, use_short)
    if limit != SHORT_PREFIX_LIMIT:
        details = details[:limit]
    rows = []
    for detail in details:
        cursor = conn.execute('SELECT * FROM places WHERE geonameid = ?', (detail['geonameid'],))
        row = dict(zip([c[0] for c in cursor.description], cursor.fetchone()))
        row.update(matched=detail['matched'], historical_name=bool(detail['historic_name']))
        row['historical'] = bool(row['historical'])
        rows.append(row)
    return rows


def matches(conn, text, limit=SHORT_PREFIX_LIMIT):
    """The app search, with its broad-prefix cache where available."""
    return _app_matches(conn, text, limit, True)


def matches_full(conn, text, limit=SHORT_PREFIX_LIMIT):
    """The same app search, with every prefix ranked from its index range."""
    return _app_matches(conn, text, limit, False)


# --- measurements on a built atlas ----------------------------------------------

def _sampled_prefixes(conn, rng, length, count):
    top = conn.execute("SELECT MAX(id) FROM atlas_keys").fetchone()[0]
    if not top:
        raise AtlasBuildError("The atlas holds no names.")
    if not conn.execute("SELECT 1 FROM atlas_keys WHERE (kinds & 1) <> 0 AND length(key) >= ? LIMIT 1", (length,)).fetchone():
        raise AtlasBuildError(f"No name is {length} characters long.")
    while count:
        row = conn.execute("SELECT key FROM atlas_keys WHERE id = ? AND (kinds & 1) <> 0", (rng.randint(1, top),)).fetchone()
        if row and len(row[0]) >= length and row[0][:length].strip() == row[0][:length]:
            count -= 1
            yield row[0][:length]


def benchmark(path, samples=1000):
    """The search's time at prefixes of 1, 2, 3, 4, 5 and 8 characters:
    median and 95th percentile, in milliseconds."""
    rng, report = random.Random(SAMPLE_SEED), {}
    with contextlib.closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        for length in (1, 2, 3, 4, 5, 8):
            timings = []
            for prefix in _sampled_prefixes(conn, rng, length, samples):
                start = time.perf_counter()
                matches(conn, prefix)
                timings.append((time.perf_counter() - start) * 1000)
            timings.sort()
            report[str(length)] = {"samples": samples, "p50_ms": statistics.median(timings),
                                   "p95_ms": timings[int(.95 * (samples - 1))]}
            print(length, report[str(length)], flush=True)
    return {"runtime": runtime_info(), "queries": report}


def agreement(path, samples=1000):
    """The search's answer read with its table of first twenties against
    its answer ranked from the index ranges alone, for sampled prefixes of
    each stored length: the number that differ."""
    rng, report = random.Random(SAMPLE_SEED), {}
    with contextlib.closing(sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        for length in SHORT_PREFIX_LENGTHS:
            references, disagreements = {}, 0
            for prefix in _sampled_prefixes(conn, rng, length, samples):
                if prefix not in references:
                    references[prefix] = matches_full(conn, prefix)
                disagreements += matches(conn, prefix) != references[prefix]
            report[str(length)] = {"samples": samples, "unique_reference_queries": len(references),
                                   "disagreements": disagreements}
            print(length, report[str(length)], flush=True)
    return {"runtime": runtime_info(), "agreement": report}


def runtime_info():
    return {"python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
            "unicode": unicodedata.unidata_version}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the offline place atlas from GeoNames' full dump.")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--fetch", metavar="FOLDER", help="download the four inputs and their manifest")
    actions.add_argument("--build", action="store_true", help="build the atlas from the four inputs")
    actions.add_argument("--digest", metavar="DB", help="print a built atlas's content digest")
    actions.add_argument("--agreement", metavar="DB", help="compare the table of first twenties with the index ranges")
    actions.add_argument("--benchmark", metavar="DB", help="time the search")
    parser.add_argument("--places", help="allCountries.zip or allCountries.txt")
    parser.add_argument("--alternates", help="alternateNamesV2.zip or alternateNamesV2.txt")
    parser.add_argument("--countries", help="countryInfo.txt")
    parser.add_argument("--admin1", help="admin1CodesASCII.txt")
    parser.add_argument("--manifest", help="the manifest --fetch wrote")
    parser.add_argument("--output", help="where to write the atlas")
    parser.add_argument("--report", help="also write the summary to this file, as JSON")
    args = parser.parse_args(argv)
    if args.fetch:
        result = fetch(args.fetch)
    elif args.digest:
        result = {"content_digest": content_digest(args.digest)}
    elif args.agreement:
        result = agreement(args.agreement)
    elif args.benchmark:
        result = benchmark(args.benchmark)
    else:
        needed = (args.places, args.alternates, args.countries, args.admin1, args.manifest, args.output)
        if not all(needed):
            parser.error("--build needs --places, --alternates, --countries, --admin1, --manifest and --output")
        result = build(*needed)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.report:
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
