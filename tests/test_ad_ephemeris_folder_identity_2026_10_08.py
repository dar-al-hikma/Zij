"""The folder accepted at its path is the one the engine made (lane AD; the
owner's rulings 139 and 141).

The engine accepted whatever stood at its ephemeris folder's path while it
ran if it looked like its folder: a real directory of this user's, mode
0700. Ruling 139 gave the folder an identity a replacement cannot carry (on
POSIX a descriptor held on it from its making), but consulted it only at
exit. So a directory renamed into place -- the folder moved aside and one of
this user's own 0700 directories made at its path -- was adopted by every
route: the per-call check (_ephemeris_folder_here), a new thread's first
call, the reader thread's star search, the folder found again at a fresh
import and at a reload; and threads already pointed at the path were never
checked again, since only the folder's name was compared. The engine wrote
its catalogue into the adopted directory, or overwrote a catalogue there; a
stray file there refused every new thread, and a fresh import raised.

Now the folder is accepted at its path only by ruling 139's identity: on
POSIX the path's (st_dev, st_ino) is the held descriptor's and the held
folder has not been removed (its link count is above 0). Anything else is
not used, and a new folder is made, as for a folder that has gone; a thread
already pointed at the path is pointed at the new folder at its next call.

Each case runs in a fresh process (FM3's harness): the folder is moved aside
and a 0700 directory of this user's made at its path holding (a) nothing,
(b) a copy of the shipped catalogue, (c) a stray file, (d) an altered
catalogue named as the shipped one (Algol an hour later), or (e) a Delta T
file. Then one route runs first, because the first route to see the swap
makes the new folder and the rest follow by its name: the per-call check
itself; a new thread; a thread already pointed (a chart, the page's thread
check, a star asked of the library directly); the reader thread, after the
stars were read and before they ever were; the Delta T reference, read
again; a fresh import; a reload. After it every route is asked again. Each
case asks that the route made a new folder, that no name but the new
folder's was handed to the library after the swap (by its path setter or
$SE_EPHE_PATH), that no value differs from a clean launch's, that no thread
was refused, that nothing in the replacement
was written or changed (its listing, each file's bytes, inode, mode and
time, the directory's own inode, mode and time), that the process holds
nothing open in it, and that at a normal exit the new folder is removed and
the replacement kept as it stood. Four more cases force the removed folder's
identity onto the replacement after a cleaner removed the folder, so that
only the link count tells them apart.

All 54 failed at main (811ed22): the folder never moved; a new thread was
refused in (c) and (e); a fresh import raised in (c) and (e); the reader
wrote its catalogue into the replacement, or overwrote the altered one there,
when it searched after the swap (before the first star read, after a fresh
import, after a reload); a thread already pointed read the altered catalogue
from the replacement; the Delta T reference read again took the replacement's
Delta T file.

Fix round 1, after the blind check. The catalogue's copy was written by the
folder's name after the folder was accepted, so a directory swapped in
between was written into; it is now read and written through the descriptor
held on the folder (four cases: an empty replacement and one holding an
altered catalogue, the engine's folder moved aside or removed; all four
failed at 4726c68, the replacement written into or its catalogue
overwritten). And the engine's own folder, still held, whose mode is no
longer 0700 or which is reported as another user's, is not accepted (four
cases; they passed at 4726c68 too, which checked the same, and fail where
that check is dropped from _ephemeris_folder_is_held).
"""
from __future__ import annotations

import os
import shutil

import pytest

from ephemeris_check_count import CHECK_COUNT, indented
from test_fm3_ephemeris_folder_umask_2026_10_07 import _child, short_root  # noqa: F401 (a fixture)

CASES = ["a-empty", "b-catalogue-copy", "c-stray-file", "d-altered-catalogue", "e-delta-t-file"]
LIVE = ["here", "new-thread", "pointed-chart", "pointed-check", "pointed-star", "reader", "reader-first-read",
        "reference"]
IMPORTS = ["fresh-import", "reload"]

# What stands at a path: the directory's inode, mode and modification time,
# and each file's bytes (SHA-256), inode, mode and modification time. The
# child and this module both use it, so the replacement is compared as the
# child left it and as it stands after the child's exit.
_STANDING = r"""
def standing(path, lstat=os.lstat):
    import hashlib, stat
    st = lstat(path)
    files = {}
    for name in sorted(os.listdir(path)):
        fst = lstat(os.path.join(path, name))
        with open(os.path.join(path, name), "rb") as fh:
            files[name] = [hashlib.sha256(fh.read()).hexdigest(), fst.st_ino, stat.S_IMODE(fst.st_mode),
                           fst.st_mtime_ns]
    return {"dir": [st.st_ino, stat.S_IMODE(st.st_mode), st.st_mtime_ns], "files": files}
"""
_NS: dict = {"os": os}
exec(_STANDING, _NS)
standing = _NS["standing"]

# Every descriptor the process holds, as (st_dev, st_ino, its name): listed
# from /proc/self/fd on Linux, /dev/fd where there is no /proc (macOS, the
# BSDs); each read by fstat (bound here, before any case forces os.fstat);
# named by its link (Linux) or by fcntl's F_GETPATH (macOS), else by its
# number. The child and this module both use it, and
# test_the_descriptor_listing_sees_what_this_process_holds holds it to a
# file and a directory this process opens, so a listing that sees nothing
# cannot make "nothing held open" pass.
_HELD = r"""
def descriptors_held(fstat=os.fstat):
    import fcntl
    where = "/proc/self/fd" if os.path.isdir("/proc/self/fd") else "/dev/fd"
    seen = []
    for fd in os.listdir(where):
        try:
            st = fstat(int(fd))
        except (OSError, ValueError):
            continue                                  # the listing's own descriptor, closed since
        try:
            name = os.readlink(where + "/" + fd)
        except OSError:
            try:
                name = os.fsdecode(fcntl.fcntl(int(fd), fcntl.F_GETPATH, bytes(1024)).split(b"\0", 1)[0])
            except (AttributeError, OSError):
                name = "descriptor " + fd
        seen.append((st.st_dev, st.st_ino, name))
    return seen
"""
exec(_HELD, _NS)
descriptors_held = _NS["descriptors_held"]

_SWAP = r"""
def body():
    global engine, ephemeris
    import hashlib, importlib, pathlib
""" + "\n".join("    " + ln for ln in (_STANDING + _HELD).strip().splitlines()) + r"""
    def open_in(place, lstat=os.lstat):
        # Every descriptor the process holds on the directory at `place` or a
        # file in it, by inode (a removed file still open keeps its old name).
        ours = {(lstat(place).st_dev, lstat(place).st_ino)}
        ours |= {(lstat(os.path.join(place, n)).st_dev, lstat(os.path.join(place, n)).st_ino) for n in os.listdir(place)}
        return sorted(name for dev, ino, name in descriptors_held() if (dev, ino) in ours)
    def algol():
        return engine.swe.fixstar2_ut("Algol", JD, engine.swe.FLG_MOSEPH)[0][0]
    def delta_t():
        return hashlib.sha256(engine._delta_t_reference()).hexdigest()
    def pointed_record():
        return getattr(ephemeris._EPHEMERIS_THREADS, "folder", None)
    def caught(fn):
        try:
            return bits(fn())
        except BaseException as exc:
            return said(exc)
    def afterwards():
        return {"main": caught(moon), "thread": in_a_thread(moon),
                "check": in_a_thread(lambda: (engine.ephemeris_thread_check(), pointed_record())[1]),
                "stars": caught(stars), "algol_thread": in_a_thread(algol), "delta_t": caught(delta_t)}

    case, route, forcing = ARGS[0], ARGS[1], ARGS[2]
    first = ephemeris._EPHEMERIS_FOLDER
    out["first"] = first
    if case == "clean":
        out["after"] = afterwards()
        out["folder_after"] = ephemeris._EPHEMERIS_FOLDER
        return
    out["before"] = {"main": bits(moon()), "thread": in_a_thread(moon)}   # the importing thread is pointed
    if route != "reader-first-read":
        out["before"]["stars"] = bits(stars())        # the catalogue copied in, read by the reader
    old = os.lstat(first)
    if forcing == "forced":                           # a cleaner removes the folder
        shutil.rmtree(first)
    else:                                             # one that moves it aside
        moved = first + "-moved"
        os.rename(first, moved)
        out["moved"] = moved
    os.mkdir(first)                                   # and a directory of this user's made at its path
    PLANTED.append(first)
    os.chmod(first, 0o700)
    if case == "b-catalogue-copy":
        shutil.copyfile(os.path.join(os.path.dirname(engine.__file__), "ephe", "sefstars.txt"),
                        os.path.join(first, "sefstars.txt"))
        os.chmod(os.path.join(first, "sefstars.txt"), 0o600)
    elif case == "c-stray-file":
        with open(os.path.join(first, "stray.txt"), "w") as fh:
            fh.write("not the app's\n")
    elif case == "d-altered-catalogue":
        from test_fm2_swiss_files_2026_10_07 import _fabricate
        _fabricate(pathlib.Path(first), "sefstars.txt")
    elif case == "e-delta-t-file":
        from test_fm2_swiss_files_2026_10_07 import _fabricate
        _fabricate(pathlib.Path(first), "swe_deltat.txt")
    new = os.lstat(first)
    out["swapped"] = standing(first)
    held = ephemeris._EPHEMERIS_HELD[first]
    out["held_nlink"] = os.fstat(held).st_nlink
    out["same_inode"] = (new.st_dev, new.st_ino) == (old.st_dev, old.st_ino)
    if forcing == "forced":
        # CONSTRUCTED: the replacement carries the removed folder's identity
        # in every view of it, as on a filesystem that gave it the freed
        # number: only the held folder's link count tells them apart.
        real = {"lstat": os.lstat, "stat": os.stat, "fstat": os.fstat}
        def forced(st):
            if (st.st_dev, st.st_ino) != (new.st_dev, new.st_ino):
                return st
            fields = list(st)
            fields[1], fields[2] = old.st_ino, old.st_dev
            return os.stat_result(fields)
        os.lstat = lambda *a, **k: forced(real["lstat"](*a, **k))
        os.stat = lambda *a, **k: forced(real["stat"](*a, **k))
        os.fstat = lambda *a, **k: forced(real["fstat"](*a, **k))
        seen = os.lstat(first)
        out["forced"] = (seen.st_dev, seen.st_ino) == (old.st_dev, old.st_ino)
    # Every name handed to the library from here on, by either route: the
    # path setter's argument, and $SE_EPHE_PATH as it is put into the
    # environment (the os.putenv audit event).
    handed = []
    def audit(event, args):
        if event == "os.putenv" and os.fsdecode(args[0]) == "SE_EPHE_PATH":
            handed.append(os.fsdecode(args[1]))
    sys.addaudithook(audit)
    import swisseph
    setter = swisseph.set_ephe_path
    def set_path(*a, **k):
        handed.append(a[0] if a else k.get("path"))
        return setter(*a, **k)
    swisseph.set_ephe_path = set_path
    out["handed"] = handed
""" + indented(CHECK_COUNT) + r"""
    def ephemeris_step(step):
        # An import route's own step, counted alone, before the engine's: the
        # engine's import makes a library call, whose guard checks the folder
        # too and would leave the swap without the route.
        before = counted()
        module = step()
        out["ephemeris_step"] = {"checked": {k: v - before[k] for k, v in counted().items()},
                                 "folder": module._EPHEMERIS_FOLDER}
        return module
    if route == "fresh-import":
        # Streamlit's watcher drops the modules from sys.modules: the folder's
        # module is imported afresh, and the engine after it.
        del sys.modules["engine"], sys.modules["ephemeris"]
        try:
            ephemeris = ephemeris_step(lambda: importlib.import_module("ephemeris"))
            engine = importlib.import_module("engine")
        except BaseException as exc:
            out["reimport"] = said(exc)
            sys.modules["engine"], sys.modules["ephemeris"] = engine, ephemeris
    elif route == "reload":
        try:
            ephemeris = ephemeris_step(lambda: importlib.reload(ephemeris))
            engine = importlib.reload(engine)
        except BaseException as exc:
            out["reimport"] = said(exc)
    elif route == "engine-reload":
        # The engine alone reloaded (Streamlit's watcher, after an edit to
        # engine.py): the folder's import-time check is ephemeris.py's and does
        # not run again; the check runs at the next library call, through the
        # handle's guard. Each call of the guard's re-pointing step is counted.
        ready, readied = ephemeris._ephemeris_thread_ready, []
        def counted(*a, **k):
            readied.append(ephemeris._EPHEMERIS_FOLDER)
            return ready(*a, **k)
        ephemeris._ephemeris_thread_ready = counted
        module_code = id(ephemeris.EphemerisRefused)
        engine = importlib.reload(engine)
        out["ephemeris_ran_again"] = id(ephemeris.EphemerisRefused) != module_code
        out["readied_by_the_reload"] = len(readied)
        grab("route", moon)                           # the next library call
        out["readied"] = len(readied)
        ephemeris._ephemeris_thread_ready = ready
    elif route == "here":
        grab("route", engine._ephemeris_folder_here)
    elif route == "new-thread":
        out["route"] = in_a_thread(moon)
    elif route == "pointed-chart":
        grab("route", moon)
    elif route == "pointed-check":
        grab("route", engine.ephemeris_thread_check)
    elif route == "pointed-star":
        grab("route", algol)
    elif route in ("reader", "reader-first-read"):
        grab("route", stars)
    elif route == "reference":
        # CONSTRUCTED: the reference is read once per process, at the first
        # thread's first call; it is asked for again here, as a fresh import
        # asks for it, so that its own route is the first to see the swap.
        ephemeris._DELTA_T_REFERENCE = None
        grab("route", delta_t)
    out["folder_after_route"] = ephemeris._EPHEMERIS_FOLDER
    out["pointed_after_route"] = pointed_record()
    out["after"] = afterwards()
    second = ephemeris._EPHEMERIS_FOLDER
    out["second"] = second
    out["variable"] = os.environ.get("SE_EPHE_PATH")
    grab("second_listing", lambda: sorted(os.listdir(second)))
    out["held_second"] = second in ephemeris._EPHEMERIS_HELD
    out["at_path"] = standing(first)                  # its lstat is the real one, bound before any forcing
    out["open_in_replacement"] = open_in(first)
"""


@pytest.fixture(scope="module")
def clean(tmp_path_factory):
    """A clean launch's values: the same reads, with no swap."""
    out, left = _child(tmp_path_factory, 0o022, _SWAP, "clean", "none", "none")
    assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
    after = out["after"]
    assert after["stars"][0] is True and len(after["stars"][1]) == 28, after["stars"]
    assert isinstance(after["main"], str) and after["thread"] == after["main"], after
    assert after["check"] == out["first"] == out["folder_after"] and isinstance(after["algol_thread"], str), out
    assert left == [], left
    return after


def _first_route_result(route, out, clean):
    """What the route that first saw the swap returned, against a clean
    launch."""
    got = out.get("route")
    if route == "here":
        return got == out["folder_after_route"]
    if route in ("new-thread", "pointed-chart", "engine-reload"):
        return got == clean["main"]
    if route == "pointed-check":
        return got is None
    if route == "pointed-star":                       # the new folder holds no catalogue until the reader copies it
        return isinstance(got, dict) and got.get("error") == "Error" and "algol" in got.get("text", "").lower()
    if route in ("reader", "reader-first-read"):
        return got == clean["stars"]
    if route == "reference":
        return got == clean["delta_t"]
    return "reimport" not in out and got is None      # an import: the import itself was the route


def _swapped(tmp_path_factory, clean, case, route, forcing="moved"):
    out, left = _child(tmp_path_factory, 0o022, _SWAP, case, route, forcing)
    first, moved = out.get("first"), out.get("moved")
    try:
        assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
        assert "reimport" not in out, out["reimport"]
        assert out["same_inode"] is False, out
        assert (out["held_nlink"] == 0) if forcing == "forced" else (out["held_nlink"] > 0), out
        assert out.get("forced", forcing != "forced") is True, out
        # The route that first saw the replacement left it and made a new folder.
        assert out["folder_after_route"] != first, ("the replacement was adopted", route, out["folder_after_route"])
        assert _first_route_result(route, out, clean), (route, out.get("route"))
        pointed = route.startswith("pointed-")
        assert not pointed or out["pointed_after_route"] == out["folder_after_route"], out["pointed_after_route"]
        if route in IMPORTS:
            # The route's own `ephemeris` step checked the folder (its name, then
            # its identity) and left the replacement, before the engine's step.
            assert out.get("ephemeris_step", {}).get("checked") == {"safe": 2, "held": 1}, out.get("ephemeris_step")
            assert out["ephemeris_step"]["folder"] == out["folder_after_route"], out["ephemeris_step"]
        if route == "engine-reload":
            # The engine's reload did not run the folder's module again, and the
            # guard re-pointed through the handle by the end of the next call.
            assert out["ephemeris_ran_again"] is False, out
            assert out["readied"] >= 1, ("the guard never re-pointed a thread", out["readied"])
        # One new folder, the engine's own, used by every route after.
        second = out["second"]
        assert second == out["folder_after_route"] and out["made"] == [first, second], out["made"]
        assert out["variable"] == second and out["held_second"] is True, out
        assert out["handed"] and set(out["handed"]) == {second}, ("handed to the library", out["handed"])
        assert out["second_listing"] == ["sefstars.txt"], out["second_listing"]
        assert out["after"] == {**clean, "check": second}, (out["after"], clean)
        # Nothing in the replacement written or changed, and nothing of it held open.
        assert out["at_path"] == out["swapped"], (out["swapped"], out["at_path"])
        assert out["open_in_replacement"] == [], out["open_in_replacement"]
        # At a normal exit the new folder is removed and the replacement kept as it stood.
        assert left == [] and not os.path.lexists(second), "the folder the engine made was not removed at exit"
        assert standing(first) == out["swapped"], "the replacement was changed or removed at exit"
    finally:
        for place in (first, moved):
            if place and os.path.isdir(place) and not os.path.islink(place):
                shutil.rmtree(place, ignore_errors=True)


@pytest.mark.parametrize("route", LIVE)
@pytest.mark.parametrize("case", CASES)
def test_a_directory_renamed_into_place_is_left_by_the_first_route_live(tmp_path_factory, clean, case, route):
    """The folder moved aside and a 0700 directory of this user's made at its
    path, while the engine runs; then `route` runs first. It makes a new
    folder and no route uses the replacement; values equal a clean launch's
    and no thread is refused; nothing in the replacement is written or
    changed, and a normal exit keeps it."""
    _swapped(tmp_path_factory, clean, case, route)


@pytest.mark.parametrize("route", IMPORTS)
@pytest.mark.parametrize("case", CASES)
def test_a_directory_renamed_into_place_is_left_at_a_fresh_import_and_a_reload(tmp_path_factory, clean, case,
                                                                               route):
    """As above, with the swap seen first by a fresh import of the folder's
    module and the engine after it (Streamlit's watcher) or by
    importlib.reload of both: the folder found again is not the one the
    engine made, so a new one is made; the import does not raise for what
    stands in the replacement. The route's own `ephemeris` step is seen to
    check the folder and make the new one, counted before the engine's step
    (whose import-time library call reaches the guard, which would do the
    same), so the test fails where that step does not happen."""
    _swapped(tmp_path_factory, clean, case, route)


@pytest.mark.parametrize("case", CASES)
def test_after_the_engine_alone_is_reloaded_the_next_library_call_re_checks_the_folder(tmp_path_factory, clean,
                                                                                      case):
    """The folder's check at import is ephemeris.py's, so a reload of the
    engine alone (Streamlit's watcher, after an edit to engine.py) does not
    run it again: the accepted difference of the move. The
    next library call does: the swap is left as at every other route, a new
    folder is made, the value is a clean launch's, and the guard's
    re-pointing step ran (the engine's own import-time calls into the library,
    such as the horizon's refraction, are such calls)."""
    _swapped(tmp_path_factory, clean, case, "engine-reload")


@pytest.mark.parametrize("route", ["here", "pointed-chart", "fresh-import", "reload"])
def test_a_replacement_carrying_a_removed_folder_s_identity_is_not_adopted(tmp_path_factory, clean, route):
    """A cleaner removed the folder and a 0700 directory of this user's,
    holding an altered catalogue, was made at its path; its identity is
    forced to the removed folder's in every view of it. The held folder's
    link count (0) is all that tells them apart: it is not adopted."""
    _swapped(tmp_path_factory, clean, "d-altered-catalogue", route, forcing="forced")


# ---------------------------------------------------------------------------
# Fix round 1 (the blind check's items 2 and X3).
#
# Item 2: a swap between the reader's acceptance of the folder and its copy
# of the catalogue. CONSTRUCTED timing, the check's own construction: the
# install step is wrapped so that the swap happens after
# _fixed_star_catalogue_search accepted the folder (through
# _ephemeris_folder_here, by its identity) and before the copy is written.
# The copy was written by the folder's name, so it was created in the
# replacement (a) or overwrote the replacement's own catalogue and made it
# 0600 (d). It is now written through the descriptor held on the folder: into
# the engine's own folder where it was moved aside, nowhere where it was
# removed.

_IN_FLIGHT = r"""
def body():
    import hashlib, pathlib
""" + "\n".join("    " + ln for ln in _STANDING.strip().splitlines()) + r"""
    def caught(fn):
        try:
            return bits(fn())
        except BaseException as exc:
            return said(exc)
    case, cleaner = ARGS[0], ARGS[1]
    first = ephemeris._EPHEMERIS_FOLDER
    out["first"] = first
    out["main"] = bits(moon())                        # charts read; no star read yet
    moved = first + "-moved"
    def swap():
        if cleaner == "moved":                        # a cleaner that moves the folder aside
            os.rename(first, moved)
            out["moved"] = moved
        else:                                         # one that removes it
            shutil.rmtree(first)
        os.mkdir(first)                               # and a directory of this user's made at its path
        PLANTED.append(first)
        os.chmod(first, 0o700)
        if case == "d-altered-catalogue":
            from test_fm2_swiss_files_2026_10_07 import _fabricate
            _fabricate(pathlib.Path(first), "sefstars.txt")
        out["swapped"] = standing(first)
    real_install = engine._fixed_star_catalogue_install
    def install(*a, **k):
        if "swapped" not in out:
            swap()
        return real_install(*a, **k)
    engine._fixed_star_catalogue_install = install
    out["in_flight"] = caught(stars)                  # the first star read: the swap inside its copy
    engine._fixed_star_catalogue_install = real_install
    out["at_path"] = standing(first)
    out["moved_after"] = standing(moved) if cleaner == "moved" else None
    out["stars_after"] = caught(stars)
    out["chart_after"] = in_a_thread(moon)
    second = ephemeris._EPHEMERIS_FOLDER
    out["second"] = second
    grab("second_listing", lambda: sorted(os.listdir(second)))
    out["at_path_end"] = standing(first)
"""


@pytest.mark.parametrize("cleaner", ["moved", "removed"])
@pytest.mark.parametrize("case", ["a-empty", "d-altered-catalogue"])
def test_a_swap_inside_the_catalogue_s_copy_writes_nothing_into_the_replacement(tmp_path_factory, clean, case,
                                                                               cleaner):
    """The folder moved aside (or removed) and a 0700 directory of this
    user's made at its path, empty or holding an altered catalogue, after
    the reader accepted the folder and before it copied the catalogue: the
    replacement is left exactly as it stood, through the read and after
    exit; the copy is in the engine's own folder (moved aside) or nowhere
    (removed); no star read gives another value than a clean launch's, the
    next read gives the clean one, from a new folder of the engine's."""
    from test_fm2_swiss_files_2026_10_07 import SHIPPED
    import hashlib
    shipped = hashlib.sha256(SHIPPED.read_bytes()).hexdigest()
    out, left = _child(tmp_path_factory, 0o022, _IN_FLIGHT, case, cleaner)
    first, moved = out.get("first"), out.get("moved")
    try:
        assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
        assert "swapped" in out, "the install step was never reached"
        assert out["at_path"] == out["swapped"] == out["at_path_end"], (out["swapped"], out["at_path"])
        if cleaner == "moved":                        # the engine's own folder, moved aside: its copy or nothing
            landed = {name: row[0] for name, row in out["moved_after"]["files"].items()}
            assert landed in ({}, {"sefstars.txt": shipped}), out["moved_after"]
        else:                                         # nowhere: the folder it would go into was removed
            assert out["moved_after"] is None and not os.path.lexists(first + "-moved"), out
        assert out["in_flight"][1] in (None, clean["stars"][1]), out["in_flight"]
        assert out["stars_after"] == clean["stars"] and out["chart_after"] == clean["main"], out
        second = out["second"]
        assert second != first and out["second_listing"] == ["sefstars.txt"], (second, out["second_listing"])
        assert left == [] and not os.path.lexists(second), "the folder the engine made was not removed at exit"
        assert standing(first) == out["swapped"], "the replacement was changed or removed at exit"
    finally:
        for place in (first, moved):
            if place and os.path.isdir(place) and not os.path.islink(place):
                shutil.rmtree(place, ignore_errors=True)


# Note X3: the engine's own folder, still held and at its path, but no
# longer this user's 0700 directory -- its mode opened, or (CONSTRUCTED, as
# FM2's "other-owner" case: os.lstat reports another owner for it) another
# user's -- is not accepted: the next call, in a thread already pointed and
# in a new one, makes a new folder, and exit removes both.

_NOT_AS_MADE = r"""
def body():
    how = ARGS[0]
    first = ephemeris._EPHEMERIS_FOLDER
    out["first"] = first
    out["clean"] = bits(moon())
    grab("stars_before", stars)
    real_lstat = os.lstat
    if how == "other-owner":
        me = os.getuid()
        def lstat(path, *a, **k):
            st = real_lstat(path, *a, **k)
            if isinstance(path, (str, bytes, os.PathLike)) and os.path.abspath(os.fsdecode(path)) == first:
                fields = list(st)
                fields[4] = me + 1
                return os.stat_result(fields)
            return st
        os.lstat = lstat
    else:
        os.chmod(first, int(how, 8))
    try:
        grab("pointed", moon)                         # the importing thread, already pointed
        out["after_pointed"] = ephemeris._EPHEMERIS_FOLDER
        out["thread"] = in_a_thread(moon)
        grab("stars_after", stars)
    finally:
        os.lstat = real_lstat
    second = ephemeris._EPHEMERIS_FOLDER
    out["second"] = second
    out["second_lstat"] = described(second)
    grab("second_listing", lambda: sorted(os.listdir(second)))
"""


@pytest.mark.parametrize("how", ["0777", "0755", "0750", "other-owner"])
def test_the_engine_s_own_folder_no_longer_as_made_is_not_accepted(tmp_path_factory, how):
    """The folder the engine made, still held and standing at its path, with
    its mode changed from 0700 (0777, 0755, 0750) or reported as another
    user's: the next call of a thread already pointed makes a new folder,
    this user's 0700 one with the catalogue's copy; values do not move; a
    normal exit removes both folders."""
    out, left = _child(tmp_path_factory, 0o022, _NOT_AS_MADE, how)
    assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
    first, second = out["first"], out["second"]
    assert out["after_pointed"] != first and second == out["after_pointed"], (first, out["after_pointed"], second)
    assert out["made"] == [first, second], out["made"]
    assert out["pointed"] == out["thread"] == out["clean"], out
    assert out["stars_after"] == out["stars_before"] and out["stars_before"][0] is True, out
    assert out["second_lstat"] == {"dir": True, "file": False, "mode": 0o700, "mine": True}, out["second_lstat"]
    assert out["second_listing"] == ["sefstars.txt"], out["second_listing"]
    assert left == [], left


def test_the_descriptor_listing_sees_what_this_process_holds(tmp_path):
    """The listing the pins above read "nothing held open" from: it sees a
    file and a directory this process opens, by inode and by name, and not
    once they are closed."""
    path = tmp_path / "held.txt"
    path.write_text("held\n")
    st, dst = os.lstat(path), os.lstat(tmp_path)
    fh = open(path, "rb")
    fd = os.open(tmp_path, os.O_RDONLY)
    try:
        listed = descriptors_held()
        files = [name for dev, ino, name in listed if (dev, ino) == (st.st_dev, st.st_ino)]
        dirs = [name for dev, ino, name in listed if (dev, ino) == (dst.st_dev, dst.st_ino)]
        assert len(files) == 1 and files[0].endswith("held.txt"), (files, listed)
        assert len(dirs) == 1 and dirs[0].endswith(tmp_path.name), (dirs, listed)
    finally:
        fh.close()
        os.close(fd)
    assert not [n for dev, ino, n in descriptors_held() if (dev, ino) in {(st.st_dev, st.st_ino), (dst.st_dev, dst.st_ino)}]


# ---------------------------------------------------------------------------
# The re-check's F5 note: the catalogue's copy is read back through the
# descriptor held on the folder. Read back by its name, a directory swapped
# in at the folder's path between the copy and its read-back is read
# instead, and a FIFO named sefstars.txt there blocks the read-back's open
# until a writer comes: the reader thread hangs, and every star read with
# it. CONSTRUCTED timing, as above (the swap inside the install step). The
# first star read runs in a thread the child waits on for FIFO_BOUND seconds
# only; past it the child opens the FIFO for writing, which lets the blocked
# open through to an end of file, so the child and the suite go on; the
# harness's own timeout (lowered here) stands behind that. The engine's
# folders are made in a short temporary directory of the test's own
# (short_root), so a child killed by that timeout leaves nothing outside it,
# and the folder stays short whatever the runner's TMPDIR.

FIFO_BOUND = 30

_FIFO = r"""
def body():
    import time
    bound = float(ARGS[0])
    def caught(fn):
        try:
            return bits(fn())
        except BaseException as exc:
            return said(exc)
    def described_fifo(path):
        st = os.lstat(path)
        return [stat.S_ISFIFO(st.st_mode), st.st_ino, stat.S_IMODE(st.st_mode), st.st_mtime_ns]
    first = ephemeris._EPHEMERIS_FOLDER
    out["first"] = first
    out["main"] = bits(moon())                        # charts read; no star read yet
    moved = first + "-moved"
    fifo = os.path.join(first, "sefstars.txt")
    def swap():
        os.rename(first, moved)                       # the folder moved aside
        out["moved"] = moved
        os.mkdir(first)                               # a directory of this user's at its path
        PLANTED.append(first)
        os.chmod(first, 0o700)
        os.mkfifo(fifo, 0o600)                        # holding a FIFO under the catalogue's name
        out["swapped"] = described_fifo(fifo)
    real_install = engine._fixed_star_catalogue_install
    def install(*a, **k):
        if "swapped" not in out:
            swap()
        return real_install(*a, **k)
    engine._fixed_star_catalogue_install = install
    box = []
    def first_read():
        box.append(caught(stars))
    reader = threading.Thread(target=first_read, daemon=True)
    began = time.monotonic()
    reader.start()
    reader.join(bound)
    out["returned"] = not reader.is_alive()
    out["seconds"] = round(time.monotonic() - began, 1)
    if reader.is_alive():
        # Release it: a writer's open lets the blocked open through, and
        # the read finds the end of the file at once.
        deadline = time.monotonic() + 30
        while reader.is_alive() and time.monotonic() < deadline:
            try:
                os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
            except OSError:
                pass
            reader.join(0.2)
        out["released"] = not reader.is_alive()
        engine._fixed_star_catalogue_install = real_install
        return
    engine._fixed_star_catalogue_install = real_install
    out["in_flight"] = box[0]
    out["at_path"] = [sorted(os.listdir(first)), described_fifo(fifo)]
    out["moved_after"] = {name: hashlib.sha256(open(os.path.join(moved, name), "rb").read()).hexdigest()
                          for name in sorted(os.listdir(moved))}
    out["stars_after"] = caught(stars)
    out["chart_after"] = in_a_thread(moon)
    second = ephemeris._EPHEMERIS_FOLDER
    out["second"] = second
    grab("second_listing", lambda: sorted(os.listdir(second)))
    out["at_path_end"] = [sorted(os.listdir(first)), described_fifo(fifo)]
"""


def test_a_fifo_swapped_in_under_the_catalogue_s_name_does_not_hang_the_reader(tmp_path_factory, clean,
                                                                              monkeypatch, short_root):
    """The folder moved aside, after the reader accepted it and before it
    copied the catalogue, and a 0700 directory of this user's made at its
    path holding a FIFO named sefstars.txt: the first star read returns
    within FIFO_BOUND seconds (the copy is read back through the held
    descriptor, from the engine's own folder, and the FIFO is never
    opened); its value is none or a clean launch's; the next read is a
    clean launch's, from a new folder of the engine's; the FIFO stands as
    it stood; the moved folder holds the shipped copy or nothing; a normal
    exit removes the engine's folders."""
    import test_fm3_ephemeris_folder_umask_2026_10_07 as fm3
    from test_fm2_swiss_files_2026_10_07 import SHIPPED
    import hashlib
    shipped = hashlib.sha256(SHIPPED.read_bytes()).hexdigest()
    monkeypatch.setattr(fm3, "TIMEOUT", FIFO_BOUND + 90)  # behind the child's own bound and release
    out, left = _child(tmp_path_factory, 0o022, _FIFO, str(FIFO_BOUND), tmpdir=short_root)
    first, moved = out.get("first"), out.get("moved")
    try:
        assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
        assert out.get("swapped", [False])[0] is True, "the install step was never reached, or no FIFO was made"
        assert out["returned"] is True, (
            f"the first star read did not return within {FIFO_BOUND} s: it opened the FIFO swapped in at the folder's"
            f" path (released afterwards: {out.get('released')})")
        assert out["at_path"] == out["at_path_end"] == [["sefstars.txt"], out["swapped"]], (out["swapped"], out)
        assert out["moved_after"] in ({}, {"sefstars.txt": shipped}), out["moved_after"]
        assert out["in_flight"][1] in (None, clean["stars"][1]), out["in_flight"]
        assert out["stars_after"] == clean["stars"] and out["chart_after"] == clean["main"], out
        second = out["second"]
        assert second != first and out["second_listing"] == ["sefstars.txt"], (second, out["second_listing"])
        assert left == [] and not os.path.lexists(second), "the folder the engine made was not removed at exit"
    finally:
        for place in (first, moved):
            if place and os.path.isdir(place) and not os.path.islink(place):
                shutil.rmtree(place, ignore_errors=True)
