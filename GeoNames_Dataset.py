"""Build the offline place atlas, atlas.db, from GeoNames' cities500 dump.

    python -I GeoNames_Dataset.py [--out PATH] [--keep-downloads]

Run it with the interpreter the app runs on: the atlas search folds names
with that interpreter's Unicode tables, and the database records which
interpreter built it.

What it does, in order:

- fetches cities500.zip, countryInfo.txt and admin1CodesASCII.txt from
  https://download.geonames.org/export/dump/ into a fresh temporary folder,
  recording each file's size, SHA-256 and the server's Last-Modified. It
  never reads a file already lying in the working directory;
- reads the archive's one member, cities500.txt, by name, and checks every
  row: 19 columns, a whole-number id, a latitude from -90 to 90, a longitude
  from -180 to 180, a population that is a whole number, a two-letter
  country, a zone that is empty or one the pinned tzdata package holds, and
  a modification date. A row that fails stops the build, named by its line
  and id, and nothing is written;
- leaves out the few rows listed in DROPPED, each with its reason;
- writes the database to a temporary file beside the target and moves it
  into place. It holds the places and their two search indexes; GeoNames'
  own zone for each place, kept as a record of the source (the app derives
  a place's zone from its coordinates); the names of the countries and
  regions its places carry; and a metadata table saying where the data came
  from.

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
import os
import re
import shutil
import sqlite3
import ssl
import sys
import tempfile
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

BASE_URL = "https://download.geonames.org/export/dump/"
URL = BASE_URL + "cities500.zip"
COUNTRY_INFO_URL = BASE_URL + "countryInfo.txt"
ADMIN1_URL = BASE_URL + "admin1CodesASCII.txt"
MEMBER = "cities500.txt"
DEFAULT_OUT = Path(__file__).resolve().parent / "atlas.db"
COLUMNS = 19
COUNTRY_INFO_COLUMNS = 19

_DECIMAL = re.compile(r"-?[0-9]+(\.[0-9]+)?")
_WHOLE = re.compile(r"[0-9]+")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# Rows left out of the atlas, by GeoNames id, each with its reason. A row is
# corrected only from a named source; one that cannot be is dropped here
# (C-17 of the outside pass; rulings 150 and 172).
DROPPED = {
    3785489: ("La Aguada (VE): its coordinates, 11.27667, -67.46444, lie at sea, about 52 km from the "
              "nearest point the zone boundaries give a country's zone, and GeoNames' own record gives the "
              "same point, so no source corrects it."),
}

# A name holding one of these is refused, not quoted: the name tables keep
# GeoNames' text byte for byte, and these would not survive a plain
# tab-separated reading of it.
_REFUSED_IN_NAMES = ("\t", "\n", "\r", '"')


class AtlasBuildError(ValueError):
    """A download, an archive or a row the atlas is not built from."""


def pinned_zone_names():
    """Every zone name the tzdata package holds (the package's own list)."""
    listing = importlib.resources.files("tzdata").joinpath("zones").read_text(encoding="utf-8")
    return frozenset(listing.split())


def fetch(url, folder, name):
    """Download `url` over https into `folder`/`name`, a file that must not
    exist yet: its size, SHA-256 and the server's Last-Modified."""
    if not url.startswith("https://"):
        raise AtlasBuildError(f"{url} is not an https address; the atlas is fetched over https only.")
    path = os.path.join(folder, name)
    digest, size = hashlib.sha256(), 0
    context = ssl.create_default_context()
    with urllib.request.urlopen(url, timeout=120, context=context) as response:
        final = response.geturl()
        if not final.startswith("https://"):
            raise AtlasBuildError(f"{url} was redirected to {final}, which is not an https address.")
        status = getattr(response, "status", None)
        if status != 200:
            raise AtlasBuildError(f"{url} answered with status {status}, not 200.")
        last_modified = response.headers.get("Last-Modified") or ""
        with open(path, "xb") as out:
            for block in iter(lambda: response.read(1 << 20), b""):
                out.write(block)
                digest.update(block)
                size += len(block)
    return {"url": url, "path": path, "sha256": digest.hexdigest(), "bytes": size, "last_modified": last_modified}


def _decimal(text, what, where, low, high):
    if not _DECIMAL.fullmatch(text):
        raise AtlasBuildError(f"{where}: the {what} {text!r} is not a decimal number.")
    value = float(text)
    if not low <= value <= high:
        raise AtlasBuildError(f"{where}: the {what} {value} is outside {low} to {high}.")
    return value


def city_row(number, raw, zones):
    """One line of cities500.txt, checked, as the values the atlas keeps:
    (id, name, ascii_name, admin1, country, lat, lon, population, zone or
    None, modification date)."""
    where = f"{MEMBER} line {number}"
    try:
        line = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise AtlasBuildError(f"{where} is not UTF-8 text.") from None
    if line.endswith("\n"):
        line = line[:-1]
    cols = line.split("\t")
    if len(cols) != COLUMNS:
        raise AtlasBuildError(f"{where} has {len(cols)} columns, not {COLUMNS}.")
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
    return (int(cols[0]), cols[1], cols[2], cols[10], country, lat, lon, int(cols[14]), zone or None, stamp)


def read_cities(zip_path, zones):
    """Every row of the archive's one member, cities500.txt, checked; the
    first that fails stops the build, and so does a repeated id. A row in
    DROPPED is checked too, and then left out."""
    with zipfile.ZipFile(zip_path) as archive:
        members = archive.namelist()
        if members != [MEMBER]:
            raise AtlasBuildError(f"The archive holds {members!r}, not the one member {MEMBER}.")
        rows, seen = [], set()
        with archive.open(MEMBER) as member:
            for number, raw in enumerate(member, 1):
                row = city_row(number, raw, zones)
                if row[0] in seen:
                    raise AtlasBuildError(f"{MEMBER} line {number} (geonameid {row[0]}): the id is repeated.")
                seen.add(row[0])
                if row[0] not in DROPPED:
                    rows.append(row)
    if not rows:
        raise AtlasBuildError(f"{MEMBER} holds no rows.")
    return rows


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


def write_names(conn, countries, regions):
    """The country and region name tables, for every country and every
    (country, admin1) pair the atlas's places carry; a pair GeoNames gives
    no name is kept, with none. Nothing in the app reads them yet."""
    pairs = conn.execute("SELECT country, admin1, COUNT(*) FROM cities GROUP BY country, admin1").fetchall()
    for country, admin1, _count in pairs:
        if not isinstance(country, str) or not isinstance(admin1, str):
            raise AtlasBuildError(f"A place's country or region code is not text: {country!r}, {admin1!r}.")
    wanted = sorted({country for country, _admin1, _count in pairs})
    unnamed = [country for country in wanted if country not in countries]
    if unnamed:
        raise AtlasBuildError(f"countryInfo.txt gives no name for {', '.join(unnamed)}.")
    pairs.sort(key=lambda row: (row[0], row[1]))
    conn.execute("CREATE TABLE country_names (country TEXT PRIMARY KEY, name TEXT NOT NULL)")
    conn.executemany("INSERT INTO country_names VALUES (?, ?)", [(c, countries[c]) for c in wanted])
    conn.execute("CREATE TABLE admin1_names (country TEXT NOT NULL, admin1 TEXT NOT NULL, name TEXT, "
                 "ascii_name TEXT, PRIMARY KEY (country, admin1))")
    conn.executemany("INSERT INTO admin1_names VALUES (?, ?, ?, ?)",
                     [(c, a, *regions.get((c, a), (None, None))) for c, a, _n in pairs])
    return {"countries": len(wanted), "admin1_pairs": len(pairs),
            "unnamed_admin1_pairs": sum(1 for c, a, _n in pairs if (c, a) not in regions),
            "places_without_region_name": sum(n for c, a, n in pairs if (c, a) not in regions)}


def write_database(out_path, cities, countries, regions, metadata):
    """The database, written to a temporary file beside `out_path` and moved
    into place; the connection is closed on every path."""
    out_path = Path(out_path)
    fd, temporary = tempfile.mkstemp(prefix=".atlas-", suffix=".db", dir=out_path.parent)
    os.close(fd)
    try:
        with contextlib.closing(sqlite3.connect(temporary)) as conn:
            zone_ids = {name: number for number, name in enumerate(sorted({c[8] for c in cities if c[8]}), 1)}
            conn.execute("""
                CREATE TABLE cities (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    ascii_name TEXT,
                    admin1 TEXT,
                    country TEXT,
                    lat REAL,
                    lon REAL,
                    population INTEGER,
                    geonames_zone INTEGER
                )
            """)
            conn.executemany("INSERT INTO cities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                             [(*c[:8], zone_ids.get(c[8])) for c in cities])
            # The two indexes the search reads.
            conn.execute("CREATE INDEX idx_name ON cities(name COLLATE NOCASE)")
            conn.execute("CREATE INDEX idx_ascii ON cities(ascii_name COLLATE NOCASE)")
            # GeoNames' own zone for each place, numbered to keep the file
            # small: a record of the source, which the app does not read.
            conn.execute("CREATE TABLE geonames_zones (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
            conn.executemany("INSERT INTO geonames_zones VALUES (?, ?)",
                             sorted((number, name) for name, number in zone_ids.items()))
            counts = write_names(conn, countries, regions)
            conn.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.executemany("INSERT INTO metadata VALUES (?, ?)", sorted(metadata.items()))
            conn.commit()
        # mkstemp makes the file for its owner alone; the atlas is read by
        # whoever runs the app.
        os.chmod(temporary, 0o644)
        os.replace(temporary, out_path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
        raise
    return counts


def build_offline_atlas(out_path=DEFAULT_OUT, keep_downloads=False):
    """Download, check and write the atlas: a summary of what was written."""
    zones = pinned_zone_names()
    folder = tempfile.mkdtemp(prefix="geonames-")
    try:
        cities_file = fetch(URL, folder, "cities500.zip")
        country_file = fetch(COUNTRY_INFO_URL, folder, "countryInfo.txt")
        admin1_file = fetch(ADMIN1_URL, folder, "admin1CodesASCII.txt")
        cities = read_cities(cities_file["path"], zones)
        countries = read_country_names(country_file["path"])
        regions = read_region_names(admin1_file["path"])
        metadata = {"rows": str(len(cities)),
                    "dropped_ids": " ".join(str(gid) for gid in sorted(DROPPED)),
                    "dump_date": max(c[9] for c in cities),
                    "python_version": sys.version.split()[0],
                    "unicodedata_version": unicodedata.unidata_version,
                    "sqlite_version": sqlite3.sqlite_version,
                    "tzdata_version": importlib.metadata.version("tzdata")}
        for prefix, source in (("source", cities_file), ("country_info", country_file),
                               ("admin1_codes", admin1_file)):
            metadata.update({f"{prefix}_url": source["url"], f"{prefix}_last_modified": source["last_modified"],
                             f"{prefix}_sha256": source["sha256"], f"{prefix}_bytes": str(source["bytes"])})
        counts = write_database(out_path, cities, countries, regions, metadata)
    finally:
        if not keep_downloads:
            shutil.rmtree(folder, ignore_errors=True)
    return {"out": str(out_path), "downloads": folder if keep_downloads else "", **counts, **metadata}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the offline place atlas from GeoNames' cities500 dump.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="where to write the database")
    parser.add_argument("--keep-downloads", action="store_true",
                        help="leave the downloaded files in their temporary folder and print its path")
    args = parser.parse_args(argv)
    print("Downloading the GeoNames files over https and checking every row ...")
    summary = build_offline_atlas(args.out, args.keep_downloads)
    for key in sorted(summary):
        print(f"{key}\t{summary[key]}")
    print(f"{summary['out']} is ready.")


if __name__ == "__main__":
    main()
