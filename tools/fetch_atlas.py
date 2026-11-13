#!/usr/bin/env python3
"""Put the place atlas, atlas.db, at the root of this checkout, as the
program pins it.

The atlas is not kept in the repository. It is published as a release file,
one zip holding atlas.db alone, named by the first twelve hex digits of the
SHA-256 that time_zones.py records for atlas.db (its SHIPPED_DATA_SHA256
entry, the record of the atlas's bytes): the zip Zij-atlas-<12 hex>.zip, on
the release tagged atlas-<12 hex>. Its length in bytes is recorded here
(ATLAS_SIZE), and so are the published zip's own length and SHA-256
(ZIP_SIZE, ZIP_SHA256), read back from the release. A rebuilt atlas moves
that entry, this length and the zip's two in one commit, and the names move
with the entry.

The sources, in turn:

1. atlas.db already at the root, with the recorded SHA-256: it is left as
   it is.
2. A folder given by --from, or else by the Git key zij.atlasDir, that holds
   the zip.
3. The cache folder given by --cache, if it holds the zip.
4. The release of the repository --repo names (OWNER/NAME), downloaded
   through GitHub's REST API with the token in GH_TOKEN or GITHUB_TOKEN when
   one is set (a private repository's release needs one). With --cache the
   zip is kept there once its atlas.db has passed, for the next run: the
   downloaded file itself, the one checked and read, moved there, or copied
   there through its open file where the cache is on another drive.

Whatever the source, what is read as a zip is a temporary file this run makes,
read through the one open file that wrote it and never again by its name: a
zip from a folder or the cache is copied into one beside atlas.db, through the
one open file its length was checked on, no more than that length, and is not
read again; a download is written into one beside atlas.db too, never in the
cache folder. What is written is hashed as it is written, and must be the
recorded zip, of its length and its SHA-256, and its end record must declare
one entry, before anything reads it as a zip; another is refused, and a
zip from a folder or the cache left where it was found. The temporary file is
removed once atlas.db is placed or refused. A copy or a download needs free
disk in the checkout of the zip's length beside atlas.db's own temporary
file; without it, the zip is refused, saying so, and its temporary file
removed. A release that lists another length for it is refused before the
download is asked for, and a download is never written past that length,
whatever the server sends. The zip must hold one file, atlas.db, and nothing
else, declaring the recorded length; another length is refused before a byte is
written. atlas.db is written to a temporary file beside its place, never past
that length, its SHA-256 compared with the recorded one, and only then moved
into place, in one step. A zip that holds anything else, a file that does not
match, a download cut short or refused: each stops the tool with a sentence
saying so, and leaves the checkout as it was, an atlas.db already there
included. First, before it looks at the atlas.db in place, it removes what a
run killed before its end left, even where that atlas.db is the recorded file:
its temporary files beside atlas.db and in the cache folder, regular files of
this account's named as this tool names them that no run still holds, and
nothing else. A run holds each temporary file it makes with an exclusive lock
(flock) from its making until it has moved or removed it, and the lock ends
with the run, however it ends; a file another run holds is left to that run.
On Windows, which has no such lock, a file another run has open cannot be
removed and is left, but one between its writing and its move (a moment) can
be, and that run then stops, saying its file could not be written. Where the
filesystem refuses flock for any reason but another run's lock (NFS without
its lock service, for one), each file is left unheld and a left one removed as
on Windows, but there a file another run is still writing can be removed too:
a run whose atlas.db is taken stops in the same way, one whose zip is taken
reads on through the file it holds, and nothing wrong is placed. On either, a
downloaded zip can be taken after its atlas.db is placed and before its move
to the cache folder: atlas.db stays placed, and the run says its zip could not
be kept there.

Standard library only; the same on Windows, macOS and Linux. time_zones.py
is read as text, never imported. Exit status: 0 when atlas.db is in place,
1 when it could not be put there, 2 for a usage error.
"""
from __future__ import annotations

import argparse
import ast
import errno
import hashlib
import http.client
import ipaddress
import json
import os
import re
import stat
import struct
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from pathlib import Path

try:
    import fcntl
except ImportError:                                     # Windows
    fcntl = None

ROOT = Path(__file__).resolve().parent.parent
MEMBER = "atlas.db"
API = "https://api.github.com"
GIT_KEY = "zij.atlasDir"
BLOCK = 1 << 20
TIMEOUT = 60
# The pinned atlas.db's length in bytes, beside the SHA-256 time_zones.py
# records for it: a rebuilt atlas moves both in one commit, and the tests hold
# this one to the atlas.db in the checkout. A zip whose atlas.db declares
# another length is refused before a byte is written, and no more than this
# is ever written.
ATLAS_SIZE = 2105266176
# The published zip itself, Zij-atlas-<12 hex>.zip: its length in bytes and
# its SHA-256, read back from the release that holds it. A rebuilt atlas moves
# both with ATLAS_SIZE and the SHA-256 time_zones.py records, in one commit.
# Whatever its source, a zip of another length or SHA-256 is refused before
# anything reads it as a zip; a release that lists another length is refused
# before the download is asked for, and no more than this length is ever
# written of a download.
ZIP_SIZE = 770939661
ZIP_SHA256 = "3a76d4f9f7ec4fb9fec0e33a7798b7698420647e7f27609b8edd48dc2cfcc4ae"
_REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_DIGEST = re.compile(r"[0-9a-f]{64}")
# The temporary files this tool makes, as tempfile.mkstemp names them: the
# prefix, eight characters of its alphabet, the suffix.
_ATLAS_PART = re.compile(r"\.atlas\.db\.[a-z0-9_]{8}\.part")
_ZIP_PART = re.compile(r"\.Zij-atlas-[a-z0-9_]{8}\.zip\.part")
# The end of a zip as zipfile reads it: the end record, and the zip64 locator
# and zip64 end record that may stand before it, with their signatures.
_END, _END_SIG = struct.Struct("<4s4H2LH"), b"PK\x05\x06"
_END64_LOCATOR, _END64_LOCATOR_SIG = struct.Struct("<4sLQL"), b"PK\x06\x07"
_END64, _END64_SIG = struct.Struct("<4sQ2H2L4Q"), b"PK\x06\x06"
# The longest entry list one entry named atlas.db can have: an entry's 46
# fixed bytes, the name, and an extra field and a comment each as long as
# its two-byte length allows.
_ONE_ENTRY = 46 + len(MEMBER) + 0xFFFF + 0xFFFF


class Refused(Exception):
    """atlas.db could not be put in place; the text says why."""


class NotTheZip(Refused):
    """The zip is not the recorded zip, by its length or its SHA-256."""


# --------------------------------------------------------------------------- the pin and the names

def pinned_digest(root: Path = ROOT) -> str:
    """The SHA-256 time_zones.py records for atlas.db, read from its text:
    the 'atlas.db' entry of the dictionary assigned to SHIPPED_DATA_SHA256 at
    the module's top level, which must be there exactly once."""
    source = root / "time_zones.py"
    try:
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
    except (OSError, SyntaxError, UnicodeDecodeError) as exc:
        raise Refused(f"cannot read the recorded SHA-256 of atlas.db from {source}: {exc}") from None
    found = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        else:
            continue
        if not any(isinstance(t, ast.Name) and t.id == "SHIPPED_DATA_SHA256" for t in targets):
            continue
        if not isinstance(value, ast.Dict):
            raise Refused(f"SHIPPED_DATA_SHA256 in {source} is not written as a dictionary")
        for key, entry in zip(value.keys, value.values):
            if isinstance(key, ast.Constant) and key.value == MEMBER:
                found.append(entry.value if isinstance(entry, ast.Constant) else None)
    if len(found) != 1 or not isinstance(found[0], str) or not _DIGEST.fullmatch(found[0]):
        raise Refused(f"{source} does not record one SHA-256 for atlas.db in SHIPPED_DATA_SHA256")
    return found[0]


def release_names(digest: str) -> tuple[str, str]:
    """The release tag and the zip's name for the atlas whose SHA-256 is
    `digest`."""
    short = digest[:12]
    return f"atlas-{short}", f"Zij-atlas-{short}.zip"


def matches(path: Path, digest: str) -> bool:
    """Whether `path` is a file whose SHA-256 is `digest`."""
    if not path.is_file():
        return False
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(BLOCK), b""):
            sha.update(block)
    return sha.hexdigest() == digest


class _NotWritten(Exception):
    """A failure writing, syncing or moving the file in its folder, not a
    failure reading the zip."""


def _written(step, *args):
    try:
        return step(*args)
    except OSError as exc:
        raise _NotWritten(exc) from None


def _remove(path) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


# The temporary files this run holds: each one's path, and a second
# descriptor of it that keeps its exclusive lock until _release.
_HELD: dict[str, int] = {}
# What flock, asked not to wait, raises where another run holds the file.
_LOCKED = frozenset({errno.EWOULDBLOCK, errno.EAGAIN})


def _held(prefix: str, suffix: str, folder) -> tuple[int, str]:
    """A new temporary file in `folder`, as tempfile.mkstemp makes it, held
    by this run: where flock exists, locked exclusively through a second
    descriptor until _release(path), so that another run's clean-up leaves
    it. flock without waiting refuses with EWOULDBLOCK (the same number as
    EAGAIN on Linux and on macOS) only where another run holds the file: here,
    another run's clean-up about to remove it. Such a file, and one that
    clean-up took before the lock, is given up for a new one, and a file given
    up is removed while its name is still the file made. Any other refusal of
    flock (ENOLCK on Linux, ENOTSUP or EOPNOTSUPP on macOS, where the
    filesystem keeps no locks, as NFS without its lock service) leaves the
    file unheld, as on Windows."""
    for _ in range(8):
        fd, path = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=folder)
        if fcntl is None:
            return fd, path
        lock = os.dup(fd)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno not in _LOCKED:                # no locks here: unheld, as on Windows
                os.close(lock)
                return fd, path
        else:
            try:
                if os.path.samestat(os.fstat(lock), os.lstat(path)):
                    _HELD[str(Path(path))] = lock
                    return fd, path
            except OSError:
                pass
        try:
            if os.path.samestat(os.fstat(fd), os.lstat(path)):
                os.remove(path)
        except OSError:
            pass
        os.close(lock)
        os.close(fd)
    raise OSError(f"no temporary file in {folder} could be held: another run removed each one made")


def _release(path) -> None:
    """Let go of the temporary file at `path`, once it has been moved or
    removed."""
    lock = _HELD.pop(str(Path(path)), None)
    if lock is not None:
        os.close(lock)


def _remove_left(folder: Path, *names: re.Pattern) -> None:
    """Remove from `folder` the temporary files a run killed before its end
    left: regular files this account owns (on Windows, which has no owner
    here, regular files) whose whole name is one of `names`, and which no run
    holds: where flock exists, each is removed only while this run holds its
    lock, taken without waiting, and a file flock refuses with EWOULDBLOCK or
    EAGAIN (another run holds it) is left. Where flock refuses for any other
    reason (a filesystem that keeps no locks) and on Windows, there is no lock
    to ask, and the file is removed by its name and kind alone: on Windows a
    file another run has open refuses its removal, but on such a filesystem it
    does not. A link, a folder, another account's file, a file swapped in for
    the one found, a file another run holds, any other name, and a file that
    cannot be removed are left alone."""
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return
    for entry in entries:
        if not any(name.fullmatch(entry.name) for name in names):
            continue
        try:
            st = entry.stat(follow_symlinks=False)
            if not stat.S_ISREG(st.st_mode) or (hasattr(os, "getuid") and st.st_uid != os.getuid()):
                continue
            if fcntl is None:
                os.remove(entry.path)
                continue
            fd = os.open(entry.path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
            try:
                if not os.path.samestat(os.fstat(fd), st):
                    continue
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    if exc.errno in _LOCKED:            # held by a run still going
                        continue
                os.remove(entry.path)                   # held now, or no locks here
            finally:
                os.close(fd)
        except OSError:
            pass


# --------------------------------------------------------------------------- from a zip to its place

class _NotCopied(Exception):
    """A failure writing the private copy of a zip, not a failure reading
    the zip it copies."""


def _shut(file) -> None:
    """Close `file`, raising nothing where the close fails: a disk that
    filled can leave bytes in its buffer that the close writes again and is
    refused again, and the failure that stopped the run says why. The file is
    closed all the same."""
    try:
        file.close()
    except OSError:
        pass


def _drop(copy, part) -> None:
    """Close the private copy `copy` (_shut), remove it at `part` and let it
    go (_release), in that order: closed first, because Windows removes no
    open file; let go last, so that it is held until it is gone. It is
    removed and let go whatever the close raises."""
    try:
        _shut(copy)
    finally:
        _remove(part)
        _release(part)


def _not_recorded(sha, label: str) -> None:
    """Refuse, naming the zip by `label`, unless `sha` (the hash of every byte
    of it) is ZIP_SHA256."""
    if sha.hexdigest() != ZIP_SHA256:
        raise NotTheZip(f"{label} is not the recorded zip (its SHA-256 is {sha.hexdigest()}, the recorded zip's "
                        f"is {ZIP_SHA256}); it was not read as a zip")


def _copied(zip_path: Path, label: str, folder):
    """A private copy of the zip at `zip_path`, made in `folder` as a
    temporary file this run holds (_held), returned open and rewound, with
    its path, once it is the recorded zip: the source, opened once, must be a
    regular file of ZIP_SIZE bytes; that many are copied through that one
    open file, hashed as they are copied, and must be all it yields; their
    SHA-256 must be ZIP_SHA256. The source is not read again: a change to it
    after its open is either in the copy, and hashed, or not seen. Anything
    else refuses: the copy is removed and the source closed and left where it
    is. A copy that cannot be written whole (a disk without room for it, for
    one) refuses the same way."""
    try:
        source = open(zip_path, "rb")
    except OSError as exc:
        raise Refused(f"{label} cannot be read ({exc})") from None
    with source:
        try:
            found = os.fstat(source.fileno())
        except OSError as exc:
            raise Refused(f"{label} cannot be read ({exc})") from None
        if not stat.S_ISREG(found.st_mode) or found.st_size != ZIP_SIZE:
            raise NotTheZip(f"{label} is not the recorded zip (it is {found.st_size:,} bytes, the recorded zip has "
                            f"{ZIP_SIZE:,}); it was not read as a zip")
        try:
            fd, part = _held(".Zij-atlas-", ".zip.part", folder)
        except OSError as exc:
            raise Refused(f"{label} could not be copied to {folder} to be read ({exc}); it was not read as a "
                          f"zip") from None
        copy = os.fdopen(fd, "w+b")
        try:
            sha = hashlib.sha256()
            got = 0
            for block in iter(lambda: source.read(min(BLOCK, ZIP_SIZE - got + 1)), b""):
                got += len(block)
                if got > ZIP_SIZE:
                    break
                sha.update(block)
                try:
                    copy.write(block)
                except OSError as exc:
                    raise _NotCopied(exc) from None
            if got != ZIP_SIZE:
                raise NotTheZip(f"{label} is not the recorded zip (it changed while it was read); it was not read "
                                f"as a zip")
            _not_recorded(sha, label)
            try:
                copy.flush()
            except OSError as exc:
                raise _NotCopied(exc) from None
            copy.seek(0)
        except _NotCopied as exc:
            _drop(copy, part)
            raise Refused(f"{label} could not be copied to {folder} to be read ({exc}); it was not read as a "
                          f"zip") from None
        except OSError as exc:
            _drop(copy, part)
            raise Refused(f"{label} cannot be read ({exc})") from None
        except BaseException:
            _drop(copy, part)
            raise
    return copy, part


def _one_entry(copy, label: str) -> None:
    """Refuse the private copy open at `copy` unless the end of the zip, read
    as zipfile finds it, declares one entry, in an entry list no longer than
    one entry named atlas.db can be (_ONE_ENTRY): its end record (the last 22
    bytes, or else the last record signature in them and the 65,535 bytes a
    comment can fill before them) and, where a zip64 locator stands just
    before that, the zip64 end record, which must stand just before the
    locator. Only those records are read; zipfile is given the copy only once
    they pass."""
    length = copy.seek(0, os.SEEK_END)
    base = max(length - _END.size - 0xFFFF, 0)
    copy.seek(base)
    tail = copy.read()
    at = len(tail) - _END.size
    if not (at >= 0 and tail[at:at + 4] == _END_SIG and tail[-2:] == b"\0\0"):
        at = tail.rfind(_END_SIG)
        if at < 0 or len(tail) - at < _END.size:
            raise Refused(f"{label} cannot be read as a zip (it has no end record); its entry list was not read")
    _, _, _, here, total, listed, _, _ = _END.unpack_from(tail, at)
    end = base + at
    if end >= _END64_LOCATOR.size:
        copy.seek(end - _END64_LOCATOR.size)
        locator = copy.read(_END64_LOCATOR.size)
        if locator[:4] == _END64_LOCATOR_SIG:
            record = end - _END64_LOCATOR.size - _END64.size
            copy.seek(max(record, 0))
            found = copy.read(_END64.size)
            if (record < 0 or _END64_LOCATOR.unpack(locator)[2] != record or len(found) != _END64.size
                    or found[:4] != _END64_SIG):
                raise Refused(f"{label} cannot be read as a zip (its zip64 end record is not where its locator "
                              f"stands); its entry list was not read")
            _, _, _, _, _, _, here, total, listed, _ = _END64.unpack(found)
    if here != 1 or total != 1 or listed > _ONE_ENTRY:
        raise Refused(f"{label} must hold atlas.db alone; its end record declares {total:,} entries in an entry list "
                      f"of {listed:,} bytes, and that list was not read")
    copy.seek(0)


def _placed(copy, root: Path, digest: str, label: str, size: int) -> None:
    """atlas.db from the recorded zip open at `copy` (a private copy, _copied
    or download) put at `root`, once its SHA-256 is `digest`: refused before
    zipfile reads it unless its end record declares one entry (_one_entry);
    then refused before anything is written unless it holds atlas.db alone,
    declaring `size` bytes; written to a temporary file in `root`, never past
    `size` bytes, checked, then moved into place. Anything else refuses and
    removes the temporary file. `copy` is read through that one open file,
    never by a name, and is left open."""
    _one_entry(copy, label)
    try:
        archive = zipfile.ZipFile(copy)
    except (OSError, zipfile.BadZipFile) as exc:
        raise Refused(f"{label} cannot be read as a zip ({exc})") from None
    with archive:
        infos = archive.infolist()
        names = [info.orig_filename for info in infos]
        if len(infos) != 1 or infos[0].filename != MEMBER or names != [MEMBER]:
            raise Refused(f"{label} must hold atlas.db alone; it holds {names!r}")
        if infos[0].file_size != size:
            raise Refused(f"the atlas.db in {label} is not the recorded file (it declares {infos[0].file_size:,} "
                          f"bytes, the recorded atlas has {size:,}); none of it was written")
        fd, part = _held(".atlas.db.", ".part", root)
        try:
            sha = hashlib.sha256()
            got = 0
            out = os.fdopen(fd, "wb")
            try:
                with archive.open(infos[0]) as src:
                    for block in iter(lambda: src.read(BLOCK), b""):
                        got += len(block)
                        if got > size:
                            raise Refused(f"the atlas.db in {label} is not the recorded file (it yields more than "
                                          f"the {size:,} bytes it declares); what was written of it was removed")
                        sha.update(block)
                        _written(out.write, block)
                _written(out.flush)
                _written(os.fsync, out.fileno())
            finally:
                _shut(out)                              # closed before it is moved or removed
            if sha.hexdigest() != digest:
                raise Refused(f"the atlas.db in {label} is not the recorded file "
                              f"(its SHA-256 is {sha.hexdigest()}, time_zones.py records {digest})")
            _written(os.chmod, part, 0o644)
            _written(os.replace, part, root / MEMBER)
        except Refused:
            _remove(part)
            raise
        except _NotWritten as exc:
            _remove(part)
            raise Refused(f"the atlas.db in {label} could not be written to {root} ({exc})") from None
        except Exception as exc:
            # a damaged archive or member, an encrypted member, a compression
            # method zipfile cannot read, or one it can whose data is not of
            # that method (an LZMA, Zstandard or bzip2 member)
            _remove(part)
            raise Refused(f"the atlas.db in {label} cannot be read whole ({exc})") from None
        except BaseException:
            _remove(part)
            raise
        finally:
            _release(part)


def place_from_zip(zip_path: Path, root: Path, digest: str, label: str | None = None,
                   size: int | None = None) -> None:
    """atlas.db from the zip at `zip_path` put at `root`, once its SHA-256 is
    `digest`: the zip copied first into a private temporary file in `root`
    (_copied), refused unless that copy is the recorded zip; then only the
    copy is read (_placed), with `size` ATLAS_SIZE unless given. The copy is
    removed once atlas.db is placed or refused, whatever stops the run; the
    zip itself is never removed here. A refusal names the zip by `label`, or
    else by its full path."""
    label = label or str(zip_path)
    size = ATLAS_SIZE if size is None else size
    copy, part = _copied(zip_path, label, root)
    try:
        _placed(copy, root, digest, label, size)
    finally:
        _drop(copy, part)


# --------------------------------------------------------------------------- the download

def _loopback(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


def _safe_url(url: str) -> bool:
    """HTTPS, or plain HTTP to this computer alone."""
    parts = urllib.parse.urlsplit(url)
    return parts.scheme == "https" or (parts.scheme == "http" and _loopback(parts.hostname))


class _Redirects(urllib.request.HTTPRedirectHandler):
    """A redirect is followed only to an address _safe_url allows. The token
    is sent as an unredirected header, so it never follows."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _safe_url(newurl):
            raise Refused("the download was redirected to an address that is not HTTPS; it was not followed")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _request(url: str, accept: str, token: str | None) -> urllib.request.Request:
    req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "zij-fetch-atlas",
                                               "X-GitHub-Api-Version": "2022-11-28"})
    if token:
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    return req


def download(repo: str, digest: str, folder: Path, api: str = API, token: str | None = None):
    """The release zip of `repo` for the atlas `digest`, downloaded into a
    temporary file in `folder` and returned open and rewound, with its path,
    still held (_held), once it is the recorded zip: the caller reads it
    through that open file alone, never by its name, then moves or removes it
    (_drop). A release that lists another length than ZIP_SIZE is refused
    before the download is asked for, no more than one byte past ZIP_SIZE is
    read of what is sent, and nothing past it is written; what is written is
    hashed as it is written, and must be of ZIP_SHA256. Anything else refuses
    and removes the file."""
    if not _REPO.fullmatch(repo):
        raise Refused(f"--repo takes OWNER/NAME, not {repo!r}")
    api = api.rstrip("/")
    if not _safe_url(api):
        raise Refused(f"the API address {api!r} is not HTTPS")
    tag, asset = release_names(digest)
    opener = urllib.request.build_opener(_Redirects)
    where = f"the release {tag} of {repo}"
    try:
        with opener.open(_request(f"{api}/repos/{repo}/releases/tags/{urllib.parse.quote(tag)}",
                                  "application/vnd.github+json", token), timeout=TIMEOUT) as resp:
            release = json.load(resp)
        listed = release.get("assets") if isinstance(release, dict) else None
        found = [a for a in listed or [] if isinstance(a, dict) and a.get("name") == asset]
        if len(found) != 1 or not isinstance(found[0].get("id"), int) or not isinstance(found[0].get("size"), int):
            raise Refused(f"{where} does not hold one file named {asset}")
        size = ZIP_SIZE
        if found[0]["size"] != size:
            raise Refused(f"{where} lists {asset} at {found[0]['size']:,} bytes, not the recorded zip's {size:,}; "
                          f"nothing was downloaded")
        fd, part = _held(".Zij-atlas-", ".zip.part", folder)
        out = os.fdopen(fd, "w+b")
        try:
            sha = hashlib.sha256()
            got = 0
            with opener.open(_request(f"{api}/repos/{repo}/releases/assets/{found[0]['id']}",
                                      "application/octet-stream", token), timeout=TIMEOUT) as resp:
                for block in iter(lambda: resp.read(min(BLOCK, size - got + 1)), b""):
                    got += len(block)
                    if got > size:
                        break
                    sha.update(block)
                    _written(out.write, block)
            if got < size:
                raise Refused(f"the download of {asset} was cut short: {got:,} bytes of the recorded zip's {size:,}")
            if got > size:
                raise Refused(f"the download of {asset} is longer than the recorded zip's {size:,} bytes; no more "
                              f"than those were written, and they were removed")
            _not_recorded(sha, f"{asset} downloaded from {repo}'s release")
            _written(out.flush)
            out.seek(0)
        except BaseException as exc:
            _drop(out, part)
            if isinstance(exc, _NotWritten):
                raise Refused(f"the download of {asset} could not be written to {folder} to be read ({exc}); it was "
                              f"not read as a zip") from None
            if isinstance(exc, (http.client.HTTPException, OSError)) and not isinstance(exc, urllib.error.URLError):
                raise Refused(f"the download of {asset} was cut short ({exc!r})") from None
            raise
        return out, part
    except urllib.error.HTTPError as exc:
        hint = (" (the release may not exist, or, in a private repository, a token is needed in GH_TOKEN)"
                if exc.code in (401, 403, 404) else "")
        raise Refused(f"GitHub answered {exc.code} {exc.reason} for {where}{hint}") from None
    except urllib.error.URLError as exc:
        raise Refused(f"cannot reach GitHub for {where} ({exc.reason})") from None
    except (ValueError, http.client.HTTPException, OSError) as exc:
        raise Refused(f"cannot read {where} ({exc!r})") from None


# --------------------------------------------------------------------------- in turn

def _git_folder(root: Path) -> Path | None:
    try:
        out = subprocess.run(["git", "-C", str(root), "config", "--get", GIT_KEY],
                             capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    value = out.stdout.strip()
    return Path(value).expanduser() if out.returncode == 0 and value else None


# Whether an open file can be moved: not on Windows, where Python opens a
# file without the sharing that lets it be renamed while open.
_MOVES_OPEN = os.name != "nt"


def _kept(copy, part, kept: Path) -> None:
    """The downloaded zip, open at `copy` and checked, put at `kept`, the
    cache's name for it, only while `part` is still that file: moved from
    `part` (on Windows, which moves no open file, closed first), and the file
    then at `kept` must be it. Where the cache is on another drive than
    `part` (another st_dev, on Windows the volume's serial number), or where
    the move is refused across drives (EXDEV) while `copy` is still open, it
    is copied instead through `copy` (_copied_over), and `part` is left for
    its caller to remove. Raises OSError when it is not kept, saying so."""
    checked = os.fstat(copy.fileno())
    here = os.lstat(part)
    if not os.path.samestat(checked, here):
        raise OSError("the file checked is no longer at its temporary name")
    if os.stat(kept.parent).st_dev != here.st_dev:
        return _copied_over(copy, kept)
    if not _MOVES_OPEN:
        copy.close()
    try:
        os.replace(part, kept)
    except OSError as exc:
        if copy.closed or exc.errno != errno.EXDEV:
            raise
        return _copied_over(copy, kept)
    if not os.path.samestat(checked, os.lstat(kept)):
        raise OSError("the file now at its name is not the one checked")


def _copied_over(copy, kept: Path) -> None:
    """The checked zip open at `copy` copied through that open file, no more
    than ZIP_SIZE bytes, into a new temporary file in `kept`'s folder that
    this run holds (_held), then moved to `kept` while that name is still the
    file written; the file then at `kept` must be it. A copy that cannot be
    made whole is removed, and raises OSError saying so."""
    fd, new = _held(".Zij-atlas-", ".zip.part", kept.parent)
    out = os.fdopen(fd, "wb")
    try:
        copy.seek(0)
        got = 0
        for block in iter(lambda: copy.read(min(BLOCK, ZIP_SIZE - got)), b""):
            got += len(block)
            out.write(block)
        if got != ZIP_SIZE:
            raise OSError(f"the file checked yields {got:,} bytes, not the recorded zip's {ZIP_SIZE:,}")
        out.flush()
        os.fsync(out.fileno())
        made = os.fstat(out.fileno())
        out.close()                                     # Windows moves no open file
        if not os.path.samestat(made, os.lstat(new)):
            raise OSError("its copy is no longer at its temporary name")
        os.replace(new, kept)
        if not os.path.samestat(made, os.lstat(kept)):
            raise OSError("the file now at its name is not the one copied")
    except BaseException:
        try:
            _shut(out)
        finally:
            _remove(new)
        raise
    finally:
        _release(new)


def fetch(root: Path = ROOT, folder: Path | None = None, cache: Path | None = None, repo: str | None = None,
          api: str = API, token: str | None = None, use_git_key: bool = True) -> str:
    """atlas.db put at `root` from the first source that holds it (see the
    module's text); returns a sentence saying what was done, or raises
    Refused with one saying why nothing was."""
    digest = pinned_digest(root)
    tag, asset = release_names(digest)
    _remove_left(root, _ATLAS_PART, _ZIP_PART)          # a run killed before its end
    if cache is not None:
        _remove_left(Path(cache), _ZIP_PART)
    if matches(root / MEMBER, digest):
        return "atlas.db is the recorded file already; it was not changed."
    looked = []
    if folder is None and use_git_key:
        folder = _git_folder(root)
    for source in (folder, cache):
        if source is None:
            continue
        candidate = Path(source) / asset
        if candidate.is_file():
            try:
                place_from_zip(candidate, root, digest)
            except NotTheZip as exc:
                raise Refused(f"{exc}, and it was left there: put the zip of the release {tag} in its place, "
                              f"or remove it") from None
            return f"atlas.db placed from {candidate}."
        looked.append(str(candidate))
    if repo:
        if cache is not None:
            Path(cache).mkdir(parents=True, exist_ok=True)
        copy, part = download(repo, digest, root, api, token)
        try:
            _placed(copy, root, digest, f"{asset} downloaded from {repo}'s release", ATLAS_SIZE)
            if cache is not None:
                try:
                    _kept(copy, part, Path(cache) / asset)
                except OSError as exc:
                    return f"atlas.db placed from {repo}'s release; its zip could not be kept in {cache} ({exc})."
                return f"atlas.db placed from {repo}'s release, its zip kept in {cache}."
        finally:
            _drop(copy, part)
        return f"atlas.db placed from {repo}'s release."
    seen = f" (looked for {', '.join(looked)})" if looked else ""
    raise Refused(f"no source holds {asset}{seen}: name a folder that holds it with --from, "
                  f"or the repository whose release holds it with --repo OWNER/NAME")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Put atlas.db at the checkout's root, checked against the SHA-256 time_zones.py records.")
    parser.add_argument("--from", dest="folder", type=Path,
                        help=f"a folder holding the atlas's zip (default: the Git key {GIT_KEY}, if set)")
    parser.add_argument("--cache", type=Path, help="a folder the downloaded zip is kept in, and read from next time")
    parser.add_argument("--repo", help="OWNER/NAME: the repository whose release holds the zip")
    parser.add_argument("--api", default=API, help=argparse.SUPPRESS)
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or None
    try:
        said = fetch(args.root, args.folder, args.cache, args.repo, args.api, token)
    except Refused as exc:
        print(f"fetch_atlas: {exc}. atlas.db was not changed.", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"fetch_atlas: {exc}. atlas.db was not changed.", file=sys.stderr)
        return 1
    print(said)
    return 0


if __name__ == "__main__":
    sys.exit(main())
