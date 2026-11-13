"""Recorded SHA-256 hashes for the data the app ships and reads.

Six files the repository carries -- the place atlas, the fixed-star
catalogue, the star lists, the sky's source ids, the outlines of the areas the
zone code reads by coordinates and the list of the places whose zone is settled
by a named source rather than by the boundaries alone --
and the data files of the two pinned zone packages: the IANA
time-zone database (tzdata) and the zone boundaries timezonefinder answers
from (timezonefinder-data). Their versions are pinned in requirements.txt;
these hashes catch a changed file under an unchanged name or version.

A package's data is hashed as one digest over the sorted list of its files'
relative paths and their own hashes: every file the distribution installs
except its metadata folder and its code. Both packages are pure wheels
(py3-none-any), one wheel for every platform, installed byte for byte, so the
digest is the same on Linux, Windows and macOS.

The recorded hashes are the program's own, the ones it checks as it runs
(time_zones.py's SHIPPED_DATA_SHA256 and ZONE_PACKAGES, engine.py's
FIXED_STAR_CATALOGUE_SHA256 and FIXED_STAR_LISTS_SHA256, sky.py's PINS): this module reads them and holds no copy, and
each is written once in the program. A deliberate change -- a rebuilt atlas,
a new catalogue, a version bump -- updates its pin there in the same commit,
and says why.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import re
from pathlib import Path, PurePosixPath

import pytest

import time_zones

ROOT = Path(__file__).resolve().parents[1]


def _program_constant(program, name):
    """A constant a program file assigns, read from its text (the engine is not imported here)."""
    tree = ast.parse((ROOT / program).read_text(encoding="utf-8"))
    node, = [n for n in tree.body if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == [name]]
    return ast.literal_eval(node.value)


# Where each pin last moved (the values are the program's, above):
# - atlas.db: the atlas rebuilt from GeoNames' dump: the builder fetches over
# https, checks every row and
#   records its sources; the database also keeps GeoNames' own zones and the
#   country and region names. Its row count, schema, dump and coordinates are
#   pinned in test_atlas1_rebuilt_atlas_2026_10_14.py. (v1.0.0's atlas, built
#   by the unchecked builder, was 30d962ca...53bdb2.)
# - data/mean_time_outlines.json: the outlines the zone code reads by
#   coordinates, published whole under the ODbL (moved out of the code as
#   data, with nothing in them changed).
# - data/place_zones.tsv: the hand-kept list of the places whose zone is
#   settled by a named source rather than by the boundaries alone, read by
#   time_zones.place_zone.
#   Moved again when the five places no clock record settles
#   and the West Bank rows no rule reached are refused as the areas are;
#   two rows' reasons say what their source says.
#   Moved again when the four kept with only GeoNames' record
#   agreeing are refused as those five are.
# - data/place_clocks.tsv: the clocks particular places kept before 1970,
#   year by year, where research gives a place clocks of its own, read by
#   time_zones.named_zone_state; generated from the research, never edited
#   by hand (first pinned with Minnesota's thirteen places). Moved again
#   when it came to hold every researched place's clocks.
# - data/place_clock_sources.tsv: the documents that table's years name, each
#   with its title and how it was read, read into time_zones.PRE1970_SOURCES
#   at import; generated with the table, never edited by hand (first pinned
#   with Minnesota's documents, moved out of the code with nothing in them
#   changed). Moved again when it came to hold the documents of every
#   researched place.
# - data/fixed_star_lists.tsv and data/sky_source_ids.tsv: the Fixed stars page's
#   two longer lists and the sky's numbers for its rows, both generated, never
#   edited by hand; each read and checked as test_star_tables_pinned.py holds.
FILES = {**time_zones.SHIPPED_DATA_SHA256, "ephe/sefstars.txt": _program_constant("engine.py", "FIXED_STAR_CATALOGUE_SHA256"),
         "data/fixed_star_lists.tsv": _program_constant("engine.py", "FIXED_STAR_LISTS_SHA256"),
         "data/sky_source_ids.tsv": _program_constant("sky.py", "PINS")["sky_source_ids.tsv"]}

# distribution: (import name, version, number of data files, digest of the sorted path/hash list)
PACKAGES = time_zones.ZONE_PACKAGES

CODE = {".py", ".pyc", ".pyo", ".so", ".pyd", ".dylib", ".dll"}
UPDATE = ("If the change is deliberate, update this pin in the same commit "
          "(time_zones.py's SHIPPED_DATA_SHA256 or ZONE_PACKAGES, engine.py's FIXED_STAR_CATALOGUE_SHA256 "
          "or FIXED_STAR_LISTS_SHA256, or sky.py's PINS) "
          "and say why in the commit message.")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def package_data(dist) -> list[tuple[str, str]]:
    """[(relative path, sha256), ...] for a distribution's data files, sorted by path."""
    rows = []
    for f in dist.files or ():
        parts = f.parts
        if parts[0] == ".." or parts[0].endswith(".dist-info") or "__pycache__" in parts or f.suffix in CODE:
            continue
        rows.append((PurePosixPath(*parts).as_posix(), sha256(Path(dist.locate_file(f)).read_bytes())))
    return sorted(rows)


def digest(rows: list[tuple[str, str]]) -> str:
    return sha256("".join(f"{path}\t{h}\n" for path, h in rows).encode("utf-8"))


@pytest.mark.parametrize("rel", sorted(FILES))
def test_a_shipped_data_file_has_its_recorded_hash(rel, request):
    if rel == "atlas.db":           # read once in this test process (conftest's shipped_atlas)
        shipped = request.getfixturevalue("shipped_atlas")
        assert shipped.path == ROOT / rel
        got = shipped.sha256
    else:
        got = sha256((ROOT / rel).read_bytes())
    assert got == FILES[rel], f"{rel} has changed: sha256 {got}, recorded {FILES[rel]}. {UPDATE}"


@pytest.mark.parametrize("name", sorted(PACKAGES))
def test_a_pinned_zone_package_has_its_recorded_data(name):
    """By the files its metadata lists, and by the files in its folder as the
    program reads them as it runs (time_zones.zone_package_digest): both give
    the recorded digest."""
    import_name, version, count, recorded = PACKAGES[name]
    dist = importlib.metadata.distribution(name)
    assert dist.version == version, (
        f"{name} {dist.version} is installed; its data is recorded for {version}. {UPDATE}")
    rows = package_data(dist)
    got = digest(rows)
    assert (len(rows), got) == (count, recorded), (
        f"{name} {version}'s data files have changed under the same version: {len(rows)} files, "
        f"digest {got}; recorded {count} files, {recorded}. {UPDATE}")
    assert time_zones.zone_package_digest(import_name) == (count, recorded)


def test_the_package_digest_reads_a_flipped_byte(tmp_path):
    """The digest moves when one byte of one data file moves."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"TZif2\x00\x01")
    b.write_bytes(b"TZif2\x00\x00")
    assert digest([("zoneinfo/X", sha256(a.read_bytes()))]) != digest([("zoneinfo/X", sha256(b.read_bytes()))])
    assert digest([("zoneinfo/X", "0")]) != digest([("zoneinfo/Y", "0")])


def test_each_recorded_hash_is_written_once_in_the_program_and_nowhere_in_the_tests():
    """One record, read by the program as it runs and by this module: a second
    copy (in a test, or a second table in the program) would be free to drift."""
    recorded = set(FILES.values()) | {entry[3] for entry in PACKAGES.values()}
    assert len(recorded) == len(FILES) + len(PACKAGES)
    places = {}
    for path in sorted(ROOT.glob("*.py")) + sorted((ROOT / "tests").rglob("*.py")):
        for found in re.findall(r"[0-9a-f]{64}", path.read_text(encoding="utf-8")):
            if found in recorded:
                places.setdefault(found, []).append(path.relative_to(ROOT).as_posix())
    expected = {h: ["time_zones.py"] for h in time_zones.SHIPPED_DATA_SHA256.values()}
    expected |= {entry[3]: ["time_zones.py"] for entry in PACKAGES.values()}
    expected[FILES["ephe/sefstars.txt"]] = ["engine.py"]
    expected[FILES["data/fixed_star_lists.tsv"]] = ["engine.py"]
    expected[FILES["data/sky_source_ids.tsv"]] = ["sky.py"]
    assert places == expected
