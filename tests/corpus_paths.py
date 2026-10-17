"""The one root every corpus-reading test resolves.

The corpus is private and never ships, so nothing here names where it lives.
A machine that has it says so once, in the global Git configuration, which
every clone and worktree reads (a repository's own configuration does not
travel with a clone, and a repository's own key overrides the global one):

    git config --global zij.corpusDir /path/to/the/corpus/checkout

The CORPUS_DIR environment variable, when set, overrides the key (a run
pointed at another checkout; set but empty, the corpus is absent). With
neither -- no key, no Git, or the folder not a Git checkout -- the corpus is
absent, as on CI, and every corpus test skips there."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

# A path that can never exist (beneath the null device), for "absent".
ABSENT = Path(os.devnull) / "zij-corpus-not-configured"


def _configured() -> tuple[Path, str]:
    """(the corpus root, where it was found: 'CORPUS_DIR', 'git config' or 'absent')."""
    if "CORPUS_DIR" in os.environ:          # set but empty: absent, not the working folder
        return (Path(os.environ["CORPUS_DIR"]) if os.environ["CORPUS_DIR"] else ABSENT), "CORPUS_DIR"
    try:
        out = subprocess.run(["git", "-C", str(Path(__file__).resolve().parent), "config", "--get",
                              "zij.corpusDir"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ABSENT, "absent"
    value = out.stdout.strip() if out.returncode == 0 else ""
    return (Path(value).expanduser(), "git config") if value else (ABSENT, "absent")


CORPUS_DIR, CORPUS_SOURCE = _configured()


def corpus_file(rel: str) -> Path:
    """CORPUS_DIR / rel, for a corpus-relative path such as
    'gr_intr/abu_mashar_great_introduction.md'."""
    return CORPUS_DIR / rel


# The corpus marks each printed page with its volume and number between an
# opening star-and-bracket and a closing bracket-and-star. A test that finds a
# page by its marker builds the key here, so that no published file spells a
# marker itself: the drop's hook refuses any file that does.
_MARKER_OPEN, _MARKER_CLOSE = "*" + "[", "]" + "*"


def page_marker(volume: str, page: int) -> str:
    """The corpus' marker for `page` of `volume` ('Sahl I', 'PN IV', 'ITA' ...)."""
    return f"{_MARKER_OPEN}{volume} p. {page}{_MARKER_CLOSE}"
