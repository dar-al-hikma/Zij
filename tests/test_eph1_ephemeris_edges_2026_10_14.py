"""Three edges of the engine's ephemeris folder, left open after its
identity was made the very folder the engine made (the owner's rulings 139
and 141), and ruled in 179 and 183.

The import refused past the page. An import of the engine made again after
it was dropped from sys.modules (Streamlit's watcher does that when a source
file changes) runs in the page run's own thread, which its first calculation
points at the folder; where the folder held a file the app did not put
there, that import raised EphemerisRefused, which app.py's guard did not
catch (it caught only EphemerisFolderRefused), and the page showed a raw
exception box. The guard now says each refusal's own sentence (rulings 120
and 121), held in app.py in the module's words; anything else still raises.

The folder moved aside was left behind. Another program that renamed the
engine's folder aside left it, with the catalogue's copy, at exit: the hook
found another inode at the folder's path and rightly removed nothing there.
Under ruling 183 the folder is found at exit by the descriptor held on it,
wherever it went, emptied through it and removed by the path the system
gives for it, only where what stands there is that very folder.

The old module's star reader stayed live. After an import made again, the
dropped module's reader thread lived on and its Swiss Ephemeris kept the
catalogue open, so each such import added a thread and an open file. The
reader is now held on the library module, as the folder is, and found again.

At 1a4a74d these failed: the two sentences held in app.py and the guard's
order; the stray-file page where the engine itself was dropped; the folder
moved aside, beside its path or elsewhere, and moved on again; the forked
child's case at its last step (the parent's exit left the folder moved
aside); the path lookup and the stale path's case (no path was asked for);
and the reader counts after the three routes that import the engine again.
Passed there, as
controls: the directory put where the folder had been removed, the error of
another kind, the page where only the ephemeris module was dropped, and the
three reloads, which already found the reader.
"""
from __future__ import annotations

import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile

import pytest

from conftest import APP_PATH, EXECUTABLE_DIR
from test_fm3_ephemeris_folder_umask_2026_10_07 import _assigned, _child, short_root  # noqa: F401 (a fixture)

TIMEOUT = 300

# The owner's words (rulings 120 and 121), written out here, not read from
# the code they test.
EPHEMERIS_REFUSAL = ("Nothing is calculated: Swiss Ephemeris found a file this app does not supply. "
                     "Close the app and open it again.")
EPHEMERIS_FOLDER_REFUSAL = ("Nothing is calculated: this app could not make a private folder for its ephemeris "
                            "in the computer's temporary folder.")


def _env(tmp_path_factory, tmpdir):
    env = {k: v for k, v in os.environ.items() if k != "SE_EPHE_PATH"}
    env["PYTHONPATH"] = os.pathsep.join([str(EXECUTABLE_DIR), str(EXECUTABLE_DIR / "tests")])
    env["XDG_DATA_HOME"] = str(tmp_path_factory.mktemp("xdg"))
    env["TMPDIR"] = str(tmpdir)
    return env


def _run(tmp_path_factory, tmpdir, script, tag, *args):
    """`script` in a fresh process with its own TMPDIR; what it printed
    after `tag`, read as JSON."""
    done = subprocess.run([sys.executable, "-c", script, *map(str, args)], cwd=tmp_path_factory.mktemp("cwd"),
                          env=_env(tmp_path_factory, tmpdir), capture_output=True, text=True, timeout=TIMEOUT)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith(tag + " ")]
    assert done.returncode == 0 and lines, done.stderr[-3000:]
    return json.loads(lines[-1][len(tag) + 1:])


def _empty_tmpdir(short_root):
    tmpdir = os.path.join(short_root, "t")
    os.mkdir(tmpdir)
    return tmpdir


# ---------------------------------------------------------------------------
# The import refused past the page.

def test_app_py_holds_each_refusal_s_sentence_in_the_module_s_words():
    """Each sentence app.py says for a refusal at the engine's import is the
    one the module holds for that refusal, character for character, and is
    the owner's: the folder's for EphemerisFolderRefused, the stray file's
    for any other EphemerisRefused."""
    from conftest import engine_files
    held = {"folder": _assigned(APP_PATH, "_EPHEMERIS_FOLDER_REFUSAL_AT_IMPORT"),
            "stray": _assigned(APP_PATH, "_EPHEMERIS_REFUSAL_AT_IMPORT")}
    module = {"folder": _assigned(engine_files(), "EPHEMERIS_FOLDER_REFUSAL"),
              "stray": _assigned(engine_files(), "EPHEMERIS_REFUSAL")}
    assert held == module == {"folder": EPHEMERIS_FOLDER_REFUSAL, "stray": EPHEMERIS_REFUSAL}, (held, module)


def _import_guard():
    """The handler of the try that imports the engine in app.py."""
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    tries = [node for node in tree.body if isinstance(node, ast.Try)
             and [ast.unparse(s) for s in node.body] == ["import engine"]]
    assert len(tries) == 1, len(tries)
    (handler,) = tries[0].handlers
    return handler


def test_the_import_guard_looks_for_the_subclass_before_its_parent_and_raises_anything_else():
    """By name only (the engine never loaded): EphemerisFolderRefused first,
    with the folder's sentence; then EphemerisRefused, with the stray file's;
    anything else raised again; then the run stops."""
    handler = _import_guard()
    assert ast.unparse(handler.type) == "RuntimeError", ast.unparse(handler.type)
    chain, said = [s for s in handler.body if isinstance(s, ast.If)], []
    assert len(chain) == 1, [ast.unparse(s) for s in handler.body]
    branch = chain[0]
    while isinstance(branch, ast.If):
        names = [n.value for n in ast.walk(branch.test) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        said.append((names, [ast.unparse(s) for s in branch.body]))
        rest = branch.orelse
        branch = rest[0] if len(rest) == 1 and isinstance(rest[0], ast.If) else rest
    assert said == [(["EphemerisFolderRefused"], ["st.error(_EPHEMERIS_FOLDER_REFUSAL_AT_IMPORT)"]),
                    (["EphemerisRefused"], ["st.error(_EPHEMERIS_REFUSAL_AT_IMPORT)"])], said
    assert [ast.unparse(s) for s in branch] == ["raise"], branch
    assert ast.unparse(handler.body[-1]) == "st.stop()", ast.unparse(handler.body[-1])


_STRAY_PAGE = r"""
import json, os, sys
app, drop, plant = sys.argv[1], [n for n in sys.argv[2].split(",") if n], sys.argv[3]
from streamlit.testing.v1 import AppTest
def page():
    at = AppTest.from_file(app, default_timeout=240).run(timeout=240)
    return {"exceptions": [str(e.value)[:400] for e in at.exception], "errors": [e.value for e in at.error]}
pages = [page()]                                      # a clean run: the engine imported, its folder made
import ephemeris
folder = ephemeris._EPHEMERIS_FOLDER
with open(os.path.join(folder, "stray.txt"), "w") as fh:
    fh.write("a file the app did not put there")
if plant == "other":
    # An error of another kind at the engine's import, its class's name
    # holding the refusal's.
    class NotEphemerisRefused(RuntimeError):
        pass
    class Broken:
        def find_spec(self, name, path=None, target=None):
            if name == "engine":
                raise NotEphemerisRefused("an unrelated failure while the engine loads")
            return None
    sys.meta_path.insert(0, Broken())
for name in drop:                                     # as Streamlit's watcher drops a changed module
    sys.modules.pop(name, None)
pages += [page(), page()]                             # each rerun imports the engine again
print("PAGE " + json.dumps({"pages": pages, "engine_loaded": "engine" in sys.modules, "folder": folder}))
"""

CLEAN = {"exceptions": [], "errors": []}


@pytest.mark.parametrize("drop", ["engine", "engine,ephemeris", "ephemeris"])
def test_a_stray_file_at_an_import_made_again_says_the_stray_file_s_sentence(tmp_path_factory, short_root, drop):
    """The app run by AppTest; a file put in the engine's own folder; the
    engine (and its ephemeris module, or that alone) dropped from
    sys.modules; two more runs. Each says the stray file's sentence and
    shows no exception. Where the engine itself was dropped the refusal is
    raised by its import (failed at 1a4a74d: the raw exception); where only
    its ephemeris module was, by the page's own thread check. The folder is
    still removed at exit, the stray file with it."""
    tmpdir = _empty_tmpdir(short_root)
    out = _run(tmp_path_factory, tmpdir, _STRAY_PAGE, "PAGE", APP_PATH, drop, "none")
    assert out["pages"] == [CLEAN] + [{"exceptions": [], "errors": [EPHEMERIS_REFUSAL]}] * 2, out["pages"]
    assert out["engine_loaded"] is (drop == "ephemeris"), out
    assert os.listdir(tmpdir) == [], os.listdir(tmpdir)


def test_an_error_of_another_kind_at_an_import_made_again_still_shows_as_itself(tmp_path_factory, short_root):
    """A RuntimeError of a third class, not an EphemerisRefused, though its
    name holds that one's, raised by the engine's import made again: the
    page shows it as an exception, not as either sentence."""
    tmpdir = _empty_tmpdir(short_root)
    out = _run(tmp_path_factory, tmpdir, _STRAY_PAGE, "PAGE", APP_PATH, "engine", "other")
    assert out["pages"][0] == CLEAN, out["pages"]
    later = out["pages"][1:]
    assert [page["errors"] for page in later] == [[], []], later
    assert [len(page["exceptions"]) for page in later] == [1, 1], later
    assert ["an unrelated failure while the engine loads" in page["exceptions"][0] for page in later] == [True, True], later
    assert out["engine_loaded"] is False, out


# ---------------------------------------------------------------------------
# The folder moved aside (ruling 183).

def test_the_system_gives_a_moved_folder_s_path_by_a_descriptor_on_it(tmp_path):
    """Linux by /proc/self/fd, macOS by fcntl(F_GETPATH): the path where the
    folder now stands, after it was renamed; elsewhere None. A descriptor on
    a removed folder gives no path there is a folder at."""
    import ephemeris
    made = tmp_path / "made"
    made.mkdir()
    held = os.open(made, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        went = tmp_path / "went"
        os.rename(made, went)
        where = ephemeris._ephemeris_folder_where(held)
        if sys.platform.startswith("linux") or sys.platform == "darwin":
            assert where is not None and os.path.realpath(where) == os.path.realpath(went), (where, went)
        else:
            assert where is None, where
        os.rmdir(went)
        gone = ephemeris._ephemeris_folder_where(held)
        assert gone is None or not os.path.lexists(gone), gone
    finally:
        os.close(held)


_MOVED = r"""
def body():
    import atexit
    case = ARGS[0]
    def inode(path):
        st = os.lstat(path)
        return [st.st_dev, st.st_ino]
    def decoy(path):                                  # a directory of this user's, 0700, holding a file
        os.mkdir(path, 0o700)
        os.chmod(path, 0o700)
        with open(os.path.join(path, "theirs.txt"), "w") as fh:
            fh.write("theirs")
        out["decoy"] = [path, inode(path)]
    first = ephemeris._EPHEMERIS_FOLDER
    out["first"] = first
    grab("stars", stars)                              # the catalogue copied in
    out["chart_before"] = in_a_thread(moon)
    if case == "elsewhere":
        out["aside"] = tempfile.mkdtemp(prefix="aside-")
        moved = os.path.join(out["aside"], "kept")
    else:
        moved = first + "-moved"
    os.rename(first, moved)                           # another program moves the folder aside
    out["moved"] = moved
    out["chart"] = in_a_thread(moon)                  # the engine makes its second folder
    grab("stars_after", stars)
    second = ephemeris._EPHEMERIS_FOLDER
    out["second"] = second
    out["listings"] = {"moved": sorted(os.listdir(moved)), "second": sorted(os.listdir(second))}
    if case == "decoy-after-removal":                 # the folder removed where it went, another put there
        shutil.rmtree(moved)
        decoy(moved)
    elif case == "decoy-after-a-second-move":         # the folder moved on, another put where it was
        out["moved_on"] = moved + "-again"
        os.rename(moved, out["moved_on"])
        decoy(moved)
    elif case == "stale-path":
        out["moved_on"] = moved + "-again"
        real = ephemeris._ephemeris_folder_where
        def where(held):
            # CONSTRUCTED timing: once the system has named the folder's
            # path, the folder moves on and an empty directory of this
            # user's is made where it stood.
            path = real(held)
            os.rename(path, out["moved_on"])
            os.mkdir(path, 0o700)
            return path
        ephemeris._ephemeris_folder_where = where
    elif case == "fork":
        sys.stdout.flush()
        child = os.fork()
        if child == 0:                                # a forked child's normal exit: its exit hooks run
            atexit._run_exitfuncs()
            os._exit(0)
        os.waitpid(child, 0)
        out["after_fork"] = {"moved": sorted(os.listdir(moved)), "second": sorted(os.listdir(second))}
"""


def _moved(tmp_path_factory, short_root, case):
    out, left = _child(tmp_path_factory, 0o022, _MOVED, case, tmpdir=short_root)
    assert out["import"] is None and "body" not in out, (out["import"], out.get("body"))
    assert out["second"] != out["first"] and out["chart"] == out["chart_before"], out
    assert out["stars"] == out["stars_after"] and out["stars"][0] is True, out
    assert out["listings"] == {"moved": ["sefstars.txt"], "second": ["sefstars.txt"]}, out["listings"]
    assert left == [], left                           # the folder made after the move, removed at exit as before
    assert not os.path.lexists(out["first"]), out["first"]
    return out


def _gone(*paths):
    for path in paths:
        if path and os.path.lexists(path):
            shutil.rmtree(path, ignore_errors=True)


@pytest.mark.parametrize("where", ["beside", "elsewhere"])
def test_the_folder_moved_aside_is_emptied_and_removed_where_it_went(tmp_path_factory, short_root, where):
    """Another program renames the folder aside (beside its path, or into
    another directory); the engine moves to a new folder; at a normal exit
    the original, found by the descriptor held on it, is emptied and
    removed where it went, and the new folder at its own path. Failed at
    1a4a74d: the original was left with the catalogue's copy in it."""
    out = _moved(tmp_path_factory, short_root, where)
    try:
        assert not os.path.lexists(out["moved"]), (out["moved"], os.listdir(out["moved"]))
        assert ("aside" in out) == (where == "elsewhere"), out
        assert os.listdir(out.get("aside") or short_root) == [], os.listdir(out.get("aside") or short_root)
    finally:
        _gone(out["moved"], out.get("aside"))


@pytest.mark.parametrize("case", ["decoy-after-removal", "decoy-after-a-second-move"])
def test_a_directory_put_where_the_folder_went_is_left_untouched(tmp_path_factory, short_root, case):
    """Where the folder was moved aside and then removed there, or moved on
    again, and a 0700 directory of this user's holding a file was put where
    it had been (another inode): that directory is left as it was, its file
    in it. The folder moved on is removed where it went on to."""
    out = _moved(tmp_path_factory, short_root, case)
    path, inode = out["decoy"]
    try:
        st = os.lstat(path)
        assert [st.st_dev, st.st_ino] == inode and os.listdir(path) == ["theirs.txt"], (path, os.listdir(path))
        with open(os.path.join(path, "theirs.txt"), encoding="utf-8") as fh:
            assert fh.read() == "theirs"
        assert ("moved_on" in out) == (case == "decoy-after-a-second-move"), out
        assert not os.path.lexists(out.get("moved_on") or out["moved"] + "-again"), out
    finally:
        _gone(path, out.get("moved_on"))


def test_an_empty_directory_at_the_path_the_system_gave_is_not_removed_by_that_path(tmp_path_factory, short_root):
    """The identity of what stands at the path the system gave: where, once
    the path was named, the folder moved on and an empty directory of this
    user's was made there, that directory is kept (rmdir would take it), and
    the folder, emptied, is left where it went. The window left is the one
    the comment names, narrowed by ruling 188: an empty directory swapped
    in at the folder's very name, in the parent it is judged and removed
    through, between the two."""
    out = _moved(tmp_path_factory, short_root, "stale-path")
    try:
        assert os.path.isdir(out["moved"]) and os.listdir(out["moved"]) == [], out["moved"]
        assert os.path.isdir(out["moved_on"]) and os.listdir(out["moved_on"]) == [], out["moved_on"]
    finally:
        _gone(out["moved"], out["moved_on"])


def test_a_forked_child_s_exit_leaves_the_folder_moved_aside(tmp_path_factory, short_root):
    """A forked child that shares the descriptor runs the exit hooks at its
    own normal exit and leaves both folders as they were; the parent's exit
    then removes both."""
    out = _moved(tmp_path_factory, short_root, "fork")
    try:
        assert out["after_fork"] == {"moved": ["sefstars.txt"], "second": ["sefstars.txt"]}, out["after_fork"]
        assert not os.path.lexists(out["moved"]), out["moved"]
    finally:
        _gone(out["moved"])


# ---------------------------------------------------------------------------
# The old module's star reader (an import made again, a reload).

_READERS = r"""
import importlib, json, os, sys, threading
route = sys.argv[1]
JD = 2461042.1650830186
hooks = []
_register = threading._register_atexit
def register(fn, *a, **k):
    hooks.append(fn)
    return _register(fn, *a, **k)
threading._register_atexit = register
def counts():
    open_copies = 0
    for n in os.listdir("/proc/self/fd"):
        try:
            open_copies += os.readlink("/proc/self/fd/" + n).endswith("/sefstars.txt")
        except OSError:
            pass
    readers = sum(t.name.startswith("fixed-star-catalogue") for t in threading.enumerate())
    return {"open": open_copies, "readers": readers}
import ephemeris, engine
out = {"stars": [len(engine.fixed_star_longitudes(JD) or {})]}
out["before"] = counts()
def fresh(*names):
    for name in names:
        sys.modules.pop(name)
    for name in ("ephemeris", "engine"):
        importlib.import_module(name)
if route == "fresh-engine":
    fresh("engine")
elif route == "fresh-both":
    fresh("engine", "ephemeris")
elif route == "fresh-engine-twice":
    fresh("engine")
    out["stars"].append(len(sys.modules["engine"].fixed_star_longitudes(JD) or {}))
    fresh("engine")
elif route == "reload-engine":
    importlib.reload(sys.modules["engine"])
elif route == "reload-ephemeris":
    importlib.reload(sys.modules["ephemeris"])
elif route == "reload-both":
    importlib.reload(sys.modules["ephemeris"])
    importlib.reload(sys.modules["engine"])
out["stars"].append(len(sys.modules["engine"].fixed_star_longitudes(JD) or {}))
out["after"] = counts()
closing = [fn for fn in hooks if getattr(fn, "__name__", "") == "_fixed_star_reader_close"]
out["closing_hooks"] = len(closing)
for fn in closing:                                    # what runs at exit, run now
    fn()
out["after_close"] = counts()
print("READERS " + json.dumps(out))
"""


@pytest.mark.parametrize("route", ["fresh-engine", "fresh-both", "fresh-engine-twice", "reload-engine",
                                   "reload-ephemeris", "reload-both"])
def test_an_import_made_again_finds_the_one_reader_and_its_one_open_catalogue(tmp_path_factory, short_root, route):
    """After each route and a star read in the module it leaves, at most one
    copy of the catalogue is open and one reader thread is alive; the hook
    that closes the reader's catalogue at exit is registered once, and run
    closes the catalogue the live reader holds. Failed at 1a4a74d for the
    three fresh routes (two readers and two open copies, three after two
    such imports); the reloads already found the reader."""
    tmpdir = _empty_tmpdir(short_root)
    out = _run(tmp_path_factory, tmpdir, _READERS, "READERS", route)
    assert set(out["stars"]) == {28}, out["stars"]
    assert out["before"] == {"open": 1, "readers": 1}, out["before"]
    assert out["after"]["readers"] == 1 and out["after"]["open"] <= 1, out["after"]
    assert out["closing_hooks"] == 1, out
    assert out["after_close"] == {"open": 0, "readers": 1}, out["after_close"]
    assert os.listdir(tmpdir) == [], os.listdir(tmpdir)
