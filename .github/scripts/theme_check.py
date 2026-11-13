#!/usr/bin/env python3
"""Read a built bundle's theme file, at the place its server reads it.

The frozen server looks for .streamlit/config.toml in one folder only, the one
holding app.py under PyInstaller's sys._MEIPASS (server_limits.py), and passes
over a file that is not there without a word: the program then runs in
Streamlit's own colours and faces. So this fails unless the file stands there
beside app.py and holds the checkout's primary colour for both palettes.

    python .github/scripts/theme_check.py dist/Zij        # Windows
    python .github/scripts/theme_check.py dist/Zij.app    # macOS
    python .github/scripts/theme_check.py Zij-windows.zip # the Windows zip

Given a zip, it reads the theme file from the zip's own bytes, where the Windows
download unpacks it: _internal/.streamlit/config.toml beside _internal/app.py.
Entry names are read with each \\ taken as /, since PowerShell's archive writer
has written either.

It reads files and starts nothing. It exits 0 when the theme is there and 1,
naming each fault, when it is not. Standard library only.
"""
from __future__ import annotations

import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PALETTES = ("light", "dark")


def server_folder(bundle: Path) -> Path:
    """Where the frozen program's sys._MEIPASS is: on macOS a link there leads to
    what the bundle keeps in Resources, as it does at the program's own read."""
    if (bundle / "_internal").is_dir():
        return bundle / "_internal"
    return bundle / "Contents" / "Frameworks"


def _primaries_of(text: str) -> dict[str, object]:
    theme = tomllib.loads(text).get("theme", {})
    return {palette: theme.get(palette, {}).get("primaryColor") for palette in PALETTES}


def _primaries(path: Path) -> dict[str, object]:
    return _primaries_of(path.read_text(encoding="utf-8"))


def _compared(held_text, shipped: str, source: Path) -> list[str]:
    try:
        held = _primaries_of(held_text())
        wanted = _primaries(source)
    except (OSError, UnicodeError, tomllib.TOMLDecodeError, AttributeError, zipfile.BadZipFile) as error:
        return [f"the theme could not be read: {error}"]
    found = []
    for palette in PALETTES:
        if not wanted[palette]:
            found.append(f"{source} names no primary colour for the {palette} palette")
        elif held[palette] != wanted[palette]:
            found.append(f"{shipped} gives the {palette} palette's primary colour as {held[palette]!r}, not {wanted[palette]!r}")
    return found


def faults(bundle: Path, source: Path = ROOT / ".streamlit" / "config.toml") -> list[str]:
    """What is wrong with the bundle's theme; nothing, when it is the checkout's."""
    folder = server_folder(bundle)
    shipped = folder / ".streamlit" / "config.toml"
    if not shipped.is_file():
        return [f"{shipped} is not there"]
    if not (folder / "app.py").is_file():
        return [f"{folder} holds no app.py, so the server does not read this file"]
    return _compared(lambda: shipped.read_text(encoding="utf-8"), str(shipped), source)


ZIPPED = "_internal/.streamlit/config.toml"
ZIPPED_APP = "_internal/app.py"


def is_zip_given(path: Path) -> bool:
    """A path names the zip, not the folder, when it ends in .zip or is a file."""
    return path.suffix.lower() == ".zip" or path.is_file()


def zip_faults(archive: Path, source: Path = ROOT / ".streamlit" / "config.toml") -> list[str]:
    """What is wrong with the theme in the Windows zip; nothing, when it is the checkout's."""
    if not archive.is_file():
        return [f"{archive} is not there"]
    if not zipfile.is_zipfile(archive):
        return [f"{archive} is not a zip"]
    try:
        with zipfile.ZipFile(archive) as held:
            members = {info.filename.replace("\\", "/"): info for info in held.infolist() if not info.is_dir()}
            if ZIPPED not in members:
                return [f"{archive} holds no {ZIPPED}"]
            if ZIPPED_APP not in members:
                return [f"{archive} holds no {ZIPPED_APP}, so the server does not read its theme file"]
            data = held.read(members[ZIPPED])
    except (OSError, zipfile.BadZipFile) as error:
        return [f"{archive} could not be read: {error}"]
    return _compared(lambda: data.decode("utf-8"), f"{archive}'s {ZIPPED}", source)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    given = Path(argv[1])
    zipped = is_zip_given(given)
    found = zip_faults(given) if zipped else faults(given)
    for fault in found:
        print(f"theme_check: {fault}", file=sys.stderr)
    if not found:
        place = f"{given} at {ZIPPED}" if zipped else server_folder(given)
        print(f"theme_check: the theme file stands in {place} with both primary colours")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
