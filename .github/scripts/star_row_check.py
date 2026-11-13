#!/usr/bin/env python3
"""Read the tied star's kept row by its number, from a built bundle's two catalogue files.

The catalogue holds the Virgo Cluster on two rows, under one name and one
designation. Swiss Ephemeris opens a key through a sorted table, and which of two
equal keys it finds is that platform's sort's to say, so the program reads the
row it keeps by the file's number (engine._fixed_star_place_read). This does that
with this platform's library on the bundle's files, joined in a temporary folder
as the engine joins them, and fails unless the number opens that row: the row
alone in a catalogue, where no tie can stand, must read the same at each date.
The library keeps what it last read for a star's name across a change of folder,
so each row alone is read by a Python of its own, this script started again.

It prints both keys' places and both numbers', and a tie either way fails nothing.

    python .github/scripts/star_row_check.py dist/Zij        # Windows
    python .github/scripts/star_row_check.py dist/Zij.app    # macOS

It writes only in its temporary folder and starts only itself, once a row. It
exits 0 when the row reads by its number and 1, naming the fault, when it does not.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import swisseph as swe

# The library takes SE_EPHE_PATH, where it is set, over any folder it is given.
os.environ.pop("SE_EPHE_PATH", None)

NAME, DESIGNATION = "Virgo Cluster", "VC"
OLD_LONGITUDE = 180.930     # at J2000, as engine.FIXED_STAR_OLD_ROW tells the old row
J2000 = 2451545.0
OTHER_DATE = 2437671.5      # 7 January 1962
READS = tuple((jd, flags) for jd in (J2000, OTHER_DATE) for flags in (swe.FLG_MOSEPH, swe.FLG_MOSEPH | swe.FLG_EQUATORIAL))
CATALOGUE = "sefstars.txt"
ADDED = "sefstars_added.txt"
SAME = 1e-9


def catalogue_folder(bundle: Path) -> Path:
    """Where the frozen engine's ephe folder is: under sys._MEIPASS, as in theme_check."""
    if (bundle / "_internal").is_dir():
        return bundle / "_internal" / "ephe"
    return bundle / "Contents" / "Frameworks" / "ephe"


def rows_of(data: bytes) -> list[tuple[int, bytes]]:
    """The tied star's rows by the file's own text, each with its number, counting as the
    library counts: every line but a blank one and a comment."""
    found, number = [], 0
    for line in data.splitlines():
        if not line.strip() or line.startswith(b"#"):
            continue
        number += 1
        parts = [part.strip() for part in line.split(b",")]
        if parts[:2] == [NAME.encode(), DESIGNATION.encode()]:
            found.append((number, line))
    return found


def _open(folder: Path, data: bytes) -> None:
    (folder / CATALOGUE).write_bytes(data)
    swe.set_ephe_path(str(folder))


def _alone(folder: Path, line: bytes) -> list[tuple[float, float]]:
    """The row's places with nothing else in the catalogue, read in a new process."""
    folder.mkdir()
    (folder / CATALOGUE).write_bytes(line + b"\n")
    done = subprocess.run([sys.executable, "-I", str(Path(__file__).resolve()), "--alone", str(folder)],
                          capture_output=True, text=True, timeout=120, check=True)
    return [tuple(place) for place in json.loads(done.stdout)]


def _places(star: str, read) -> list[tuple[float, float]]:
    return [tuple(read(star, jd, flags)[0][:2]) for jd, flags in READS]


def _key_place(key: str) -> str:
    try:
        longitude, latitude = swe.fixstar2_ut(key, J2000, swe.FLG_MOSEPH)[0][:2]
    except swe.Error as error:
        return f"refused ({error})"
    return f"{longitude:.6f} {latitude:+.6f}"


def faults(bundle: Path) -> list[str]:
    """What stops the kept row reading by its number; nothing, when it does."""
    folder = catalogue_folder(bundle)
    try:
        data = (folder / CATALOGUE).read_bytes() + (folder / ADDED).read_bytes()
    except OSError as error:
        return [f"the catalogue's files could not be read in {folder}: {error}"]
    rows = rows_of(data)
    if len(rows) != 2:
        return [f"the catalogue holds {len(rows)} rows of {NAME},{DESIGNATION}, not two"]
    with tempfile.TemporaryDirectory() as temporary:
        try:
            alone = {number: _alone(Path(temporary) / str(number), line) for number, line in rows}
        except (subprocess.SubprocessError, ValueError) as error:
            said = (getattr(error, "stderr", None) or "").strip().splitlines()[-1:]
            return [f"a row alone could not be read: {error} {' '.join(said)}".rstrip()]
        kept = [number for number in alone if abs(alone[number][0][0] - OLD_LONGITUDE) >= 0.01]
        if len(kept) != 1:
            return [f"{len(kept)} rows of {NAME},{DESIGNATION} stand away from the old row's place, not one"]
        _open(Path(temporary), data)
        for key in (NAME, f",{DESIGNATION}"):
            print(f"star_row_check: key {key!r} at J2000: {_key_place(key)}")
        found = []
        for number, line in rows:
            role = "kept" if number == kept[0] else "old"
            try:
                held, label, _flag = swe.fixstar_ut(str(number), J2000, swe.FLG_MOSEPH)
                print(f"star_row_check: number {number} ({role} row) at J2000: {held[0]:.6f} {held[1]:+.6f} {label}")
                places = _places(str(number), swe.fixstar_ut)
            except swe.Error as error:
                if role == "kept":
                    found.append(f"number {number} is refused: {error}")
                continue
            if role != "kept":
                continue
            if label != f"{NAME},{DESIGNATION}":
                found.append(f"number {number} opens {label!r}")
            elif any(abs(a - b) > SAME for place, own in zip(places, alone[number]) for a, b in zip(place, own)):
                found.append(f"number {number} does not read as the kept row alone reads")
        swe.close()
    return found


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[1] == "--alone":
        swe.set_ephe_path(argv[2])
        print(json.dumps(_places(NAME, swe.fixstar2_ut)))
        return 0
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    found = faults(Path(argv[1]))
    for fault in found:
        print(f"star_row_check: {fault}", file=sys.stderr)
    if not found:
        print(f"star_row_check: the kept row of {NAME} reads by its number at each date")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
