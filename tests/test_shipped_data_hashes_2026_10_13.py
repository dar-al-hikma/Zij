"""Recorded SHA-256 hashes for the data the app ships and reads.

Four files the repository carries -- the place atlas, the fixed-star
catalogue, the outlines of the areas the zone code reads by coordinates and
the list of the places whose zone is settled by a named source rather than
by the boundaries alone --
and the data files of the two pinned zone packages: the IANA
time-zone database (tzdata) and the zone boundaries timezonefinder answers
from (timezonefinder-data). Their versions are pinned in requirements.txt;
these hashes catch a changed file under an unchanged name or version.

A package's data is hashed as one digest over the sorted list of its files'
relative paths and their own hashes: every file the distribution installs
except its metadata folder and its code. Both packages are pure wheels
(py3-none-any), one wheel for every platform, installed byte for byte, so the
digest is the same on Linux, Windows and macOS.

A deliberate change -- a rebuilt atlas, a new catalogue, a version bump --
updates its pin here in the same commit, and says why.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
from pathlib import Path, PurePosixPath

import pytest

ROOT = Path(__file__).resolve().parents[1]

FILES = {
    # The atlas rebuilt from GeoNames' checksummed dump (ATLAS1's rebuild,
    # rulings 172 and 179 S-01): the builder now fetches over https, checks
    # every row and records its sources; the database also keeps GeoNames'
    # own zones and the country and region names. Its row count, schema,
    # dump and coordinates are pinned in test_atlas1_rebuilt_atlas_2026_10_14.py.
    # (v1.0.0's atlas, built by the unchecked builder, was 30d962ca...53bdb2.)
    "atlas.db": "61e4a28deba7a12040cfb7a8940bcc10b7992208a8118fff5097664eb4ac132d",
    "ephe/sefstars.txt": "18b0dcafbe5b7240773daba2c038a325f5b3fc4163f61e0a7f4e92abd4f517c6",
    # The outlines the zone code reads by coordinates, published whole under
    # the ODbL (moved out of the code as data, with nothing in them changed).
    "data/mean_time_outlines.json": "7dedf4d6c40ef79ad43b993952231441911d2f8477f154b12af0e32b964a6a72",
    # The hand-kept list of the places whose zone is settled by a named
    # source rather than by the boundaries alone (ATLAS1's rebuild: C-01,
    # C-17, the disputed clocks), read by time_zones.place_zone. Moved by
    # build 2's fix round 1: the five places no clock record settles and the
    # West Bank rows no rule reached are refused as the areas are (rulings
    # 198 (1), 201 (1)); two rows' reasons say what their source says. Moved
    # by its fix round 2: the four kept with only GeoNames' record agreeing
    # are refused as those five are (ruling 202).
    "data/place_zones.tsv": "77a051099e1e609a22f940ac370acb189705f2d145d92eed25d2b2e8b3dd6132",
}

# distribution: (version, number of data files, digest of the sorted path/hash list)
PACKAGES = {
    "tzdata": ("2026.5", 605, "e7705aa8baf0d6a57290c0b54730b2e2813b2d40de18ed5bff69100b9a243e9a"),
    "timezonefinder-data": ("1.2026.3", 20, "af41d0f1badbb93ae4b4bf46b97e070c9b488e1fec25c77a94ba343c98e34a8a"),
}

CODE = {".py", ".pyc", ".pyo", ".so", ".pyd", ".dylib", ".dll"}
UPDATE = ("If the change is deliberate, update this pin in the same commit "
          "(tests/test_shipped_data_hashes_2026_10_13.py) and say why in the commit message.")


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
def test_a_shipped_data_file_has_its_recorded_hash(rel):
    got = sha256((ROOT / rel).read_bytes())
    assert got == FILES[rel], f"{rel} has changed: sha256 {got}, recorded {FILES[rel]}. {UPDATE}"


@pytest.mark.parametrize("name", sorted(PACKAGES))
def test_a_pinned_zone_package_has_its_recorded_data(name):
    version, count, recorded = PACKAGES[name]
    dist = importlib.metadata.distribution(name)
    assert dist.version == version, (
        f"{name} {dist.version} is installed; its data is recorded for {version}. {UPDATE}")
    rows = package_data(dist)
    got = digest(rows)
    assert (len(rows), got) == (count, recorded), (
        f"{name} {version}'s data files have changed under the same version: {len(rows)} files, "
        f"digest {got}; recorded {count} files, {recorded}. {UPDATE}")


def test_the_package_digest_reads_a_flipped_byte(tmp_path):
    """The digest moves when one byte of one data file moves."""
    a, b = tmp_path / "a", tmp_path / "b"
    a.write_bytes(b"TZif2\x00\x01")
    b.write_bytes(b"TZif2\x00\x00")
    assert digest([("zoneinfo/X", sha256(a.read_bytes()))]) != digest([("zoneinfo/X", sha256(b.read_bytes()))])
    assert digest([("zoneinfo/X", "0")]) != digest([("zoneinfo/Y", "0")])
