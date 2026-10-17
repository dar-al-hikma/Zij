"""No file that ships names a URL under the Pantheosis account.

The project moved to the dar-al-hikma organisation. The Pantheosis account
holds no repositories, so its old URLs resolve only by GitHub's redirect -- and
the account is the owner's own: create anything named Zij there and every
shipped link to it silently points at the new thing. The public download link
once did exactly that. The test reads every tracked file, the development-only
ones too: none of them needs such a URL, and a test that named them could not
run in the public tree, where they are absent. A test that must spell one
builds it from two parts, so no line of source carries it whole.

Where the tree has no Git index (an unpacked archive of the source), the
files are listed the way ``git add -A`` would take them from the tree: every
file the ``.gitignore`` files do not exclude. Where Git is present, that scan
must list every tracked file and nothing Git would leave out, so a scan that
drifts from Git's choice fails here first.
"""
import fnmatch
import os
import re
import subprocess
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
# The account under any GitHub host -- github.com, raw.githubusercontent.com,
# api.github.com/repos/, gist., codeload. -- or as a Pages site.
DEAD = re.compile(r"[\w.-]*github[\w.-]*\.(?:com|io)(?:/repos)?[/:]+pantheosis\b|pantheosis\.github\.io",
                  re.IGNORECASE)


def _git_files(*options):
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", *options], check=True,
                         capture_output=True, text=True).stdout.split("\0")
    return [t for t in out if t]


def _ignore_rules(directory, rel):
    """The patterns of `directory`'s .gitignore, each as (anchored, parts,
    directories only, the directory it was read in). Only the forms these
    files use are read; any other form stops the scan rather than guess."""
    path = directory / ".gitignore"
    if not path.is_file():
        return []
    rules = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        assert not line.startswith(("!", "\\")) and "**" not in line, (
            f"{path}: {line!r} is a .gitignore form the scan does not read")
        only_dirs = line.endswith("/")
        line = line.rstrip("/")
        anchored = "/" in line
        rules.append((anchored, line.lstrip("/").split("/"), only_dirs, rel))
    return rules


def _ignored(rel_parts, is_dir, rules):
    for anchored, parts, only_dirs, base in rules:
        if only_dirs and not is_dir:
            continue
        here = rel_parts[len(base):]
        if anchored:
            if len(here) == len(parts) and all(fnmatch.fnmatchcase(h, p) for h, p in zip(here, parts)):
                return True
        elif fnmatch.fnmatchcase(here[-1], parts[0]):
            return True
    return False


def scanned_files():
    """Every file under ROOT that ``git add -A`` would take: the tree less
    what its .gitignore files exclude, and less Git's own directory."""
    files = []

    def walk(directory, rel, rules):
        rules = rules + _ignore_rules(directory, rel)
        for entry in sorted(os.scandir(directory), key=lambda e: e.name):
            parts = rel + (entry.name,)
            is_dir = entry.is_dir(follow_symlinks=False)
            if entry.name == ".git" or _ignored(parts, is_dir, rules):
                continue
            if is_dir:
                walk(Path(entry.path), parts, rules)
            else:
                files.append("/".join(parts))

    walk(ROOT, (), [])
    return files


def tracked_files():
    """The tracked files; where the tree has no Git index, the files the
    release drop would take from it."""
    if not (ROOT / ".git").exists():
        return scanned_files()
    return _git_files()


def test_the_tree_is_listed():
    files = tracked_files()
    assert "README.md" in files and "engine.py" in files and "docs/RELEASING.md" in files
    assert "tests/test_shipped_urls_2026_09_23.py" in files   # this file is read too
    # one shipped file from each directory the drop carries, the hidden ones too
    for shipped in (".github/workflows/build.yml", ".streamlit/config.toml", "tools/git-hooks/pre-push",
                    "ephe/README.md", "fonts/OFL.txt", "tests/fixtures/label_merge_ordinary_2026_09_25.json"):
        assert shipped in files, shipped


def test_without_a_git_index_the_scan_takes_what_git_would():
    """The scan lists every tracked file, and nothing that Git leaves out
    (what it ignores); where there is no Git index there is nothing to hold it
    to, and the scan is what tracked_files() returns."""
    scanned = set(scanned_files())
    if (ROOT / ".git").exists():
        tracked = set(_git_files())
        listed = set(_git_files("--cached", "--others", "--exclude-standard"))
    else:
        tracked = listed = set(tracked_files())
    missed = tracked - scanned
    assert not missed, f"the scan misses tracked files: {sorted(missed)[:20]}"
    extra = {rel for rel in scanned - listed if (ROOT / rel).exists()}   # not one another test made and removed
    assert not extra, f"the scan takes files Git ignores: {sorted(extra)[:20]}"


# Every directory that directly holds a file of the public tree. Where Git is
# present the list is held to Git's, so a directory added to the tree is added
# here; where it is not, the scan must take a file in each, so that a scan
# skipping a directory no anchor above names still fails. The development
# tree holds three directories more, every file of which stays in development
# and is removed by the release drop: "tools" itself (only its git-hooks
# ship), the citation register's copy, which a test that ships may not name,
# and the tests' own tools folder. So they are counted, not listed: none in
# the public tree, three in the development tree, one of them "tools".
SHIPPED_DIRECTORIES = frozenset({
    ".github/scripts", ".github/workflows", ".streamlit", "data", "docs", "ephe", "fonts", "tests", "tests/fixtures",
    "tests/fixtures/stop_check", "tests/fixtures/stop_check/stand_in", "tools/git-hooks"})
DEVELOPMENT_ONLY_DIRECTORIES = 3


def _directories(files):
    return {rel.rsplit("/", 1)[0] for rel in files if "/" in rel}


def test_the_scan_takes_a_file_in_every_shipped_directory():
    """With a Git index, the pinned directories are Git's, less the
    development tree's two; with or without one, the scan takes a file in
    every directory pinned."""
    git = (ROOT / ".git").exists()
    # Without Git there is nothing to hold the pin to, and it stands as written.
    held_to = _directories(_git_files()) if git else SHIPPED_DIRECTORIES
    gone, more = SHIPPED_DIRECTORIES - held_to, held_to - SHIPPED_DIRECTORIES
    assert not gone, f"pinned directories that hold no tracked file: {sorted(gone)}"
    assert not more or (len(more) == DEVELOPMENT_ONLY_DIRECTORIES and "tools" in more), (
        f"directories holding tracked files that SHIPPED_DIRECTORIES lacks: {sorted(more)}")
    missing = SHIPPED_DIRECTORIES - _directories(scanned_files())
    assert not missing, f"the scan takes no file in these shipped directories: {sorted(missing)}"


def _resolved(line):
    """`line` as a browser or Git would read the URLs in it: percent-escapes
    decoded (twice, for an escaped escape), a port after a GitHub host
    dropped, and dot segments and doubled slashes folded."""
    for _ in range(2):
        line = urllib.parse.unquote(line)
    line = re.sub(r"(github[\w.-]*\.(?:com|io)):\d+", r"\1", line, flags=re.IGNORECASE)
    line = re.sub(r"(?<=[^:/])/{2,}", "/", line)
    previous = None
    while previous != line:
        previous = line
        line = re.sub(r"/\.(?=/)", "", line)
        line = re.sub(r"/(?!\.\./)[^/\s]+/\.\.(?=/)", "", line)
    return line


def _texts(data):
    """The readings of a file's bytes a URL can hide in: UTF-8 (with
    replacement: a URL in an image's metadata or a database is still a URL),
    and, where the bytes hold NULs, the same with them taken out, which reads
    UTF-16 text (a Windows shortcut saved as UTF-16LE) in either byte order."""
    texts = [data.decode("utf-8", "replace")]
    if b"\x00" in data:
        texts.append(data.replace(b"\x00", b"").decode("utf-8", "replace"))
    return texts


def _dead_urls(files, root=ROOT):
    hits = []
    for rel in files:
        path = root / rel
        if not path.is_file():
            continue
        found = set()
        for text in _texts(path.read_bytes()):
            for n, ln in enumerate(text.splitlines(), 1):
                if (DEAD.search(ln) or DEAD.search(_resolved(ln))) and ln.strip()[:100] not in found:
                    found.add(ln.strip()[:100])
                    hits.append(f"{rel}:{n}: {ln.strip()[:100]}")
    return hits


def test_no_shipped_file_names_a_pantheosis_url():
    hits = _dead_urls(tracked_files())
    assert not hits, "a tracked file names a Pantheosis URL (use dar-al-hikma):\n" + "\n".join(hits)


def test_the_pattern_catches_the_forms_that_bit():
    # each built from two parts, so that this file does not trip its own test
    for head, tail in (("https://github.com/", "Pantheosis/Zij/releases"),
                       ("git@github.com:", "pantheosis/zij.git"),
                       ("https://pantheosis.", "github.io/"),
                       ("HTTPS://GITHUB.COM/", "PANTHEOSIS/ZIJ"),
                       ("https://raw.githubusercontent.com/", "Pantheosis/Zij/main/README.md"),
                       ("https://api.github.com/repos/", "Pantheosis/Zij/releases/latest"),
                       ("https://codeload.github.com/", "pantheosis/zij/zip/refs/heads/main"),
                       ("https://gist.github.com/", "Pantheosis/0123")):
        assert DEAD.search(head + tail), head + tail
    for url in ("https://github.com/dar-al-hikma/Zij/releases", "*/pantheosis/zij",
                "https://raw.githubusercontent.com/dar-al-hikma/Zij/main/README.md"):
        assert not DEAD.search(url), url


@pytest.mark.parametrize("head, tail", [
    ("https://github.com:443/", "Pantheosis/Zij"),                     # a port
    ("ssh://git@github.com:22/", "pantheosis/zij.git"),
    ("https://github.com/./", "Pantheosis/Zij"),                       # a dot segment
    ("https://github.com/x/../", "Pantheosis/Zij"),
    ("https://github.com//", "Pantheosis/Zij"),
    ("https://github.com/%50", "antheosis/Zij"),                       # percent-encoding
    ("https://github.com/pantheosi", "%73/zij"),
    ("https://github.com/%2550", "antheosis/Zij"),
    ("https://github.com%2F", "Pantheosis/Zij"),
])
def test_a_url_a_browser_or_git_resolves_to_the_account_is_found(tmp_path, head, tail):
    (tmp_path / "notes.txt").write_text(f"see {head}{tail} for the download\n", encoding="utf-8")
    assert _dead_urls(["notes.txt"], root=tmp_path), head + tail


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-le", "utf-16-be"])
def test_a_url_in_utf16_text_is_found(tmp_path, encoding):
    """A Windows shortcut saved as UTF-16LE, with or without its byte-order mark."""
    url = "https://github.com/" + "Pantheosis/Zij/releases"
    (tmp_path / "Zij.url").write_bytes(f"[InternetShortcut]\r\nURL={url}\r\n".encode(encoding))
    assert _dead_urls(["Zij.url"], root=tmp_path)


@pytest.mark.parametrize("honest", ["https://github.com:443/dar-al-hikma/Zij", "https://github.com/./dar-al-hikma/Zij",
                                    "https://github.com/%64ar-al-hikma/Zij", "see 50% of the pantheon, ./x/../y"])
def test_the_resolved_forms_of_another_url_pass(tmp_path, honest):
    (tmp_path / "ok.txt").write_bytes(honest.encode("utf-16"))
    (tmp_path / "ok8.txt").write_text(honest, encoding="utf-8")
    assert _dead_urls(["ok.txt", "ok8.txt"], root=tmp_path) == []


def test_a_url_in_a_file_that_is_not_utf8_is_found(tmp_path):
    """Images and databases were skipped whole; their bytes are read now."""
    (tmp_path / "icon.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe source: https://raw.githubusercontent.com/"
                                        + b"Pantheosis" + b"/Zij/main/icon.png\n\x00\xff")
    (tmp_path / "clean.db").write_bytes(b"\xff\xfe\x00 https://github.com/dar-al-hikma/Zij \x00")
    hits = _dead_urls(["icon.png", "clean.db"], root=tmp_path)
    assert len(hits) == 1 and hits[0].startswith("icon.png:"), hits
