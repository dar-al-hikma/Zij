"""The program's source modules, as source_modules.txt names them.

source_modules.txt, at the repository's root, names every source file of the
program: one file name per line, ``#`` starts a comment, blank lines are
skipped, and the line order is the order the files are read in, app.py last.
A tree without the file (every commit before it existed) is the pair
engine.py, app.py. A listed file that does not exist is an error, never a
skip, and so is a name with a directory in it or one name twice.

Everything that reads the program's source as a whole -- the suite's source
scans and the maintainer tools -- reads it through here, so that a module
split out of engine.py is read without another edit. build.spec reads the
list by the same rules on its own (the build imports nothing from tests/),
and the suite checks that it bundles what this reads. Standard library
only; nothing here imports the program.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

LIST_NAME = "source_modules.txt"
PAIR = ("engine.py", "app.py")


def parse(text: str, where: str = LIST_NAME) -> list[str]:
    """The file names a list names, in order. ValueError for a list naming
    nothing, a name with a directory in it, or one name twice."""
    names = []
    for n, raw in enumerate(text.splitlines(), 1):
        name = raw.split("#", 1)[0].strip()
        if not name:
            continue
        if "/" in name or "\\" in name or name in (".", ".."):
            raise ValueError(f"{where}:{n}: {name!r} is not a file name in the tree")
        names.append(name)
    if not names:
        raise ValueError(f"{where} names no file")
    twice = sorted({x for x in names if names.count(x) > 1})
    if twice:
        raise ValueError(f"{where} names {', '.join(twice)} twice")
    return names


def names(root: Path) -> list[str]:
    """The file names tree `root` is made of: its list, else the pair."""
    path = Path(root) / LIST_NAME
    if not path.is_file():
        return list(PAIR)
    return parse(path.read_text(encoding="utf-8"), str(path))


def files(root: Path) -> list[Path]:
    """The source files of tree `root`, in order. FileNotFoundError names a
    listed file the tree does not hold."""
    out = [Path(root) / name for name in names(root)]
    missing = [p.name for p in out if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"{LIST_NAME} names {', '.join(missing)}, which {Path(root)} does not hold")
    return out


def names_at(repo: Path, rev: str) -> list[str]:
    """The file names the list names at git revision `rev` of `repo`, else
    the pair when that revision has no list. CalledProcessError when `rev` is
    not a revision of `repo`."""
    listed = subprocess.run(["git", "-C", str(repo), "ls-tree", "--name-only", rev, "--", LIST_NAME],
                            check=True, capture_output=True, text=True).stdout.strip()
    if not listed:
        return list(PAIR)
    text = subprocess.run(["git", "-C", str(repo), "show", f"{rev}:{LIST_NAME}"],
                          check=True, capture_output=True, text=True).stdout
    return parse(text, f"{rev}:{LIST_NAME}")
