"""The data layer's behaviour, pinned: a dozen cases from the move's proof.

The data layer (the data folder, the saved charts, the preferences' file,
their locks, their recovery copies and the stray temporary files) moved out
of engine.py into user_data.py byte for byte (tests/test_split_astro_2026_10_14.py
holds the move). Before the move some two hundred and thirty cases were run
against the module that held the code, every replacement made on that module,
and each case's results hashed: what each call returned or raised, the
notices, the six names the code rebinds, and every name in the case's own
folder with its kind, its mode and the digest of its bytes. The same hashes
came out after the move. Twelve of those cases are pinned here, run the same
way against user_data.py. A change that moves any of these -- a byte written,
a mode, a recovery copy's name, a notice -- fails here and says which case
moved.

Each case runs in a folder of its own under the test's tmp_path, with the
clock that names the recovery copies stopped and the random names counted, so
that nothing in a result depends on the moment or the machine; paths are
written relative to that folder.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import errno
import hashlib
import json
import os
import pathlib
import random
import re
import shutil
import stat
import threading
from pathlib import Path

import pytest

try:
    import fcntl as _real_fcntl
except ImportError:                       # pragma: no cover
    _real_fcntl = None

EXECUTABLE_DIR = Path(__file__).resolve().parents[1]

# The interpreter's own count of the stack a RecursionError used moves with
# the frames above the call, not with what the code does.
_STACK_USE = re.compile(r"\(used \d+ kB\)")


# --- results, written out the same way at every run ---------------------------------------------

class Roots:
    def __init__(self, *pairs):
        self.pairs = sorted(((str(k), v) for k, v in pairs if k), key=lambda kv: -len(kv[0]))

    def text(self, s):
        for k, v in self.pairs:
            s = s.replace(k, v)
        return s


def sha(data):
    return hashlib.sha256(data).hexdigest()


def norm(x, roots):
    if isinstance(x, BaseException):
        out = {"raised": type(x).__name__, "args": norm(list(x.args), roots)}
        if hasattr(x, "folder"):
            out["folder"] = norm(x.folder, roots)
        if isinstance(x, OSError):
            out["errno"] = x.errno
        return out
    if isinstance(x, pathlib.PurePath):
        return {"path": roots.text(str(x))}
    if isinstance(x, str):
        return _STACK_USE.sub("(used N kB)", roots.text(x))
    if isinstance(x, (bytes, bytearray)):
        return {"bytes": sha(bytes(x)), "len": len(x)}
    if x is None or isinstance(x, (bool, int, float)):
        return x
    if isinstance(x, dict):
        return {json.dumps(norm(k, roots), sort_keys=True): norm(v, roots) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [norm(v, roots) for v in x]
    if isinstance(x, (set, frozenset)):
        return sorted((norm(v, roots) for v in x), key=lambda v: json.dumps(v, sort_keys=True))
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return {"class": type(x).__name__,
                **{f.name: norm(getattr(x, f.name), roots) for f in dataclasses.fields(x)}}
    if isinstance(x, _dt.datetime):
        return {"datetime": x.isoformat()}
    return {"type": type(x).__name__}


def digest(result):
    return sha(json.dumps(result, sort_keys=True, ensure_ascii=True).encode("ascii"))


def listing(top, roots):
    """Every name under `top`, the names themselves looked at (a link not
    followed): its kind, its mode, and a regular file's bytes by digest."""
    out = {}
    top = Path(top)

    def walk(d):
        try:
            names = sorted(os.listdir(d))
        except OSError as exc:
            out[str(Path(d).relative_to(top)) + "/"] = {"unlistable": exc.errno}
            return
        for n in names:
            p = Path(d) / n
            r = roots.text(str(p.relative_to(top)))
            try:
                st = os.lstat(p)
            except OSError as exc:
                out[r] = {"unseen": exc.errno}
                continue
            mode = oct(stat.S_IMODE(st.st_mode))
            if stat.S_ISLNK(st.st_mode):
                out[r] = {"link": roots.text(os.readlink(p))}
            elif stat.S_ISDIR(st.st_mode):
                out[r] = {"dir": mode}
                walk(p)
            elif stat.S_ISREG(st.st_mode):
                try:
                    with open(p, "rb") as handle:
                        data = handle.read()
                    out[r] = {"file": mode, "sha": sha(data), "len": len(data)}
                except OSError as exc:
                    out[r] = {"file": mode, "unreadable": exc.errno}
            elif stat.S_ISFIFO(st.st_mode):
                out[r] = {"fifo": mode}
            else:
                out[r] = {"other": mode}

    if os.path.lexists(top):
        walk(top)
    return out


# --- stand-ins ----------------------------------------------------------------------------------

FROZEN = _dt.datetime(2026, 1, 2, 3, 4, 5)


class FrozenDatetime(_dt.datetime):
    """datetime with its clock stopped (the recovery copies' names)."""

    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return FROZEN
        return FROZEN.replace(tzinfo=_dt.timezone.utc).astimezone(tz)


class CountingSecrets:
    """secrets, its token_hex counting instead of drawing."""

    def __init__(self):
        self.n = 0

    def token_hex(self, nbytes=32):
        self.n += 1
        return f"{self.n:0{2 * nbytes}x}"

    def __getattr__(self, name):
        import secrets
        return getattr(secrets, name)


class RefusingFcntl:
    """fcntl with flock answering `code` every time."""

    def __init__(self, code):
        self.code, self.calls = code, 0

    def flock(self, fd, op):
        self.calls += 1
        raise OSError(self.code, os.strerror(self.code))

    def __getattr__(self, name):
        return getattr(_real_fcntl, name)


class FakeMsvcrt:
    """msvcrt's byte lock, as far as the lock code asks of it: each call kept."""
    LK_UNLCK, LK_LOCK, LK_NBLCK, LK_RLCK, LK_NBRLCK = 0, 1, 2, 3, 4

    def __init__(self, refuse=None):
        self.calls, self.refuse = [], refuse

    def locking(self, fd, mode, nbytes):
        self.calls.append([mode, nbytes])
        if self.refuse is not None and mode == self.LK_NBLCK:
            raise OSError(self.refuse, os.strerror(self.refuse))


# --- a case's folder and its replacements -------------------------------------------------------

class Patches:
    _MISSING = object()

    def __init__(self):
        self.undo = []

    def set(self, obj, name, value):
        old = getattr(obj, name, self._MISSING)
        setattr(obj, name, value)
        self.undo.append(("attr", obj, name, old))

    def setenv(self, name, value):
        old = os.environ.get(name, self._MISSING)
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
        self.undo.append(("env", None, name, old))

    def restore(self):
        for kind, obj, name, old in reversed(self.undo):
            if kind == "attr":
                if old is self._MISSING:
                    try:
                        delattr(obj, name)
                    except AttributeError:
                        pass
                else:
                    setattr(obj, name, old)
            elif old is self._MISSING:
                os.environ.pop(name, None)
            else:
                os.environ[name] = old
        self.undo = []


REBOUND = ("DATA_DIR_ERROR", "LAST_STORE_ERROR", "LAST_STORE_UNREADABLE", "LAST_PREFERENCES_ERROR",
           "LAST_PREFERENCES_UNREADABLE", "LAST_PREFERENCES_BUSY")


class Ctx:
    def __init__(self, M, E, tree, root):
        self.M, self.E, self.tree, self.root = M, E, Path(tree), Path(root)
        self.p = Patches()
        self.xdg = self.root / "xdg"
        self.data = self.xdg / "Zij"
        self.store = self.data / "saved_charts.json"
        self.prefs = self.data / "preferences.json"
        self.legacy = self.xdg / "TraditionalAstrologyEngine"
        self.program = self.root / "program"
        self.elsewhere = self.root / "elsewhere"
        self.roots = Roots((self.root, "<ROOT>"), (self.tree, "<TREE>"))

    def n(self, x):
        return norm(x, self.roots)

    def call(self, fn, *args, **kwargs):
        try:
            return {"returned": self.n(fn(*args, **kwargs))}
        except Exception as exc:          # every raise is a result
            return self.n(exc)

    def listing(self, top=None):
        return listing(self.root if top is None else top, self.roots)

    def rebound(self):
        return {name: self.n(getattr(self.M, name)) for name in REBOUND}

    def obs(self, **more):
        out = {"listing": self.listing(), "rebound": self.rebound(),
               "store_notices": self.call(self.M.store_notices),
               "preferences_notices": self.call(self.M.preferences_notices),
               "digest": self.call(self.M.loaded_saved_charts_digest)}
        out.update(more)
        return out


def standard_setup(ctx):
    """A data folder of the case's own, every path the layer holds pointed
    into it on the module, the clock and the random names fixed, the
    per-thread notices and the rebound names fresh, preferences on."""
    M, p = ctx.M, ctx.p
    ctx.data.mkdir(parents=True, mode=0o700)
    os.chmod(ctx.data, 0o700)
    ctx.program.mkdir()
    ctx.elsewhere.mkdir()
    p.set(M, "DATA_DIR", ctx.data)
    p.set(M, "SAVED_CHARTS_PATH", ctx.store)
    p.set(M, "PREFERENCES_PATH", ctx.prefs)
    p.set(M, "_LEGACY_SAVED_CHARTS_PATH", ctx.program / "saved_charts.json")
    p.set(M, "datetime", FrozenDatetime)
    p.set(M, "secrets", CountingSecrets())
    p.set(M, "_STORE_LOADED", threading.local())
    p.set(M, "_PREFERENCES_NOTICES", threading.local())
    p.set(M, "_LAUNCHED_AT", 1_000_000.0)
    p.set(M, "_CLOSED_AT_LAUNCH", [])          # the launch's one-shot mark: another test's launch may leave it set
    for name, value in (("DATA_DIR_ERROR", None), ("LAST_STORE_ERROR", None), ("LAST_STORE_UNREADABLE", False),
                        ("LAST_PREFERENCES_ERROR", None), ("LAST_PREFERENCES_UNREADABLE", False),
                        ("LAST_PREFERENCES_BUSY", False)):
        p.set(M, name, value)
    p.setenv("ALMUTEN_NO_PREFERENCES", None)


def run_case(case, M, E, tree, root):
    """One case in the folder `root`, against `M`, the module that holds the
    data layer (and `E`, the engine): its results, written out."""
    root.mkdir(parents=True)
    ctx = Ctx(M, E, tree, root)
    umask = os.umask(0o022)
    try:
        standard_setup(ctx)
        return CASES[case](ctx)
    finally:
        os.umask(umask)
        ctx.p.restore()


# --- seeded inputs ------------------------------------------------------------------------------

NAMES = ["Alpha", "beta two", "Ça va", "Ñandú", "中文名", "日本語", "عربى", "emoji \U0001F600", "q\"uote", "back\\slash",
         "tab\tname", "  spaced  ", "Zürich 1900", "x" * 120, "Μαρία", "ẞharp"]


def seeded_mapping(seed, size=None):
    rng = random.Random(seed)
    size = rng.randint(1, 9) if size is None else size
    out = {}
    for _ in range(size):
        name = rng.choice(NAMES) + ("" if rng.random() < 0.5 else f" {rng.randint(1, 999)}")
        out[name] = {
            "date_string": f"{rng.randint(1, 2100):04d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}",
            "time_string": f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00",
            "location_query": rng.choice(NAMES),
            "lat": round(rng.uniform(-89, 89), 6), "lon": round(rng.uniform(-179, 179), 6),
            "utc_offset": rng.choice([None, 0.0, 5.5, -9.0]),
            "readings": {"_connection_rule": rng.choice(["Sahl", "Abu Ma'shar"]), "n": [rng.random(), [1, [2]]]},
        }
    return out


def store_text(charts):
    return json.dumps(charts, indent=2)


def write_bytes(path, data, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)
    os.chmod(path, mode)


# --- the cases (as the proof ran them) ------------------------------------------------------------

def _write_case(ctx, charts, twice=False):
    M = ctx.M
    out = {"digest_of": ctx.call(M.saved_charts_digest, charts),
           "text_of": ctx.call(M._saved_charts_text, charts),
           "write": ctx.call(M.write_saved_charts, charts)}
    if twice:
        out["again"] = ctx.call(M.write_saved_charts, charts)
    out.update(ctx.obs())
    return out


def _limit_mapping(limit, over):
    overhead = len(store_text({"big": {"note": ""}}))
    return {"big": {"note": "x" * (limit - overhead + (1 if over else 0))}}


def write_limit_patched(ctx):
    ctx.p.set(ctx.M, "STORE_TEXT_LIMIT", 1000)
    out = {}
    for over in (False, True):
        charts = _limit_mapping(1000, over)
        out[f"over={over}"] = {"write": ctx.call(ctx.M.write_saved_charts, charts),
                              "stands": ctx.call(ctx.M.saved_charts_as_they_stand)}
    out.update(ctx.obs())
    return out


def _load_case(ctx, data=None, mode=0o600, times=2, between=None):
    M = ctx.M
    if data is not None:
        write_bytes(ctx.store, data, mode)
    out = {}
    for n in range(times):
        out[f"load{n}"] = ctx.call(M.load_saved_charts)
        out[f"rebound{n}"] = ctx.rebound()
        out[f"notices{n}"] = ctx.call(M.store_notices)
        out[f"digest{n}"] = ctx.call(M.loaded_saved_charts_digest)
        if between is not None and n == 0:
            between(ctx)
    out.update(ctx.obs())
    return out


def load_link_bad_elsewhere(ctx):
    target = ctx.elsewhere / "shared.json"
    write_bytes(target, b"{bad")
    os.symlink(target, ctx.store)
    return _load_case(ctx)


def _stands(ctx, keep_aside_too=True):
    out = {"stands": ctx.call(ctx.M.saved_charts_as_they_stand)}
    if keep_aside_too:
        out["kept"] = ctx.call(ctx.M.saved_charts_as_they_stand, keep_aside=True)
        out["kept_again"] = ctx.call(ctx.M.saved_charts_as_they_stand, True)
    out.update(ctx.obs())
    return out


def stand_malformed(ctx):
    write_bytes(ctx.store, b'{"A": {}, "A": {}}')
    return _stands(ctx)


def _old(ctx, extra=None, times=2):
    M = ctx.M
    out = {"olds": ctx.call(M._old_stores), "first": ctx.call(M._the_first_old_store),
           "old": ctx.call(M._the_old_store)}
    if extra:
        extra(ctx)
    for n in range(times):
        out[f"load{n}"] = ctx.call(M.load_saved_charts)
        out[f"notices{n}"] = ctx.call(M.store_notices)
        out[f"listing{n}"] = ctx.listing()
        if n == 0 and times > 1:
            try:
                os.unlink(ctx.store)
            except OSError:
                pass
    out["olds_after"] = ctx.call(M._old_stores)
    out.update(ctx.obs())
    return out


def old_beside_program(ctx):
    write_bytes(ctx.program / "saved_charts.json", store_text(seeded_mapping(21)).encode())
    return _old(ctx, times=3)


def _prefs_load(ctx, data=None, mode=0o600, times=2):
    M = ctx.M
    if data is not None:
        write_bytes(ctx.prefs, data, mode)
    out = {}
    for n in range(times):
        out[f"load{n}"] = ctx.call(M.load_preferences)
        out[f"rebound{n}"] = ctx.rebound()
        out[f"notices{n}"] = ctx.call(M.preferences_notices)
    out["read"] = ctx.call(M._read_preferences_file)
    out.update(ctx.obs())
    return out


def prefs_renames(ctx):
    return _prefs_load(ctx, json.dumps({key: old for key, old, _new in ctx.E.PREFERENCE_RENAMES}).encode())


def prefs_remember_and_forget(ctx):
    M = ctx.M
    out = {}
    steps = [("remember", "last_chart", "A", {}), ("remember", "last_chart", "A", {}),
             ("remember", "_wheel_dark", True, {}), ("remember", "last_chart", "B", {}),
             ("forget", "_wheel_dark", None, {}), ("forget", "_wheel_dark", None, {}),
             ("forget", "last_chart", None, {"only_if": "A"}), ("forget", "last_chart", None, {"only_if": "B"}),
             ("remember", "home_place", {"label": "H", "lat": 1.5, "lon": 2.5}, {}),
             ("remember", "_launches", 3, {"fallback": {"last_chart": "F"}})]
    for n, (what, key, value, kwargs) in enumerate(steps):
        if what == "remember":
            out[f"{n}"] = ctx.call(M.remember_preference, key, value, **kwargs)
        else:
            out[f"{n}"] = ctx.call(M.forget_preference, key, **kwargs)
        out[f"{n}_notices"] = ctx.call(M.preferences_notices)
        out[f"{n}_rebound"] = ctx.rebound()
        out[f"{n}_file"] = ctx.listing(ctx.data)
    out.update(ctx.obs())
    return out


def folder_existing_777(ctx):
    path = ctx.root / "base" / "Zij"
    path.mkdir(parents=True)
    os.chmod(path, 0o777)
    out = {"made": ctx.call(ctx.M._make_user_data_dir, path), "listing": ctx.listing()}
    os.chmod(path, 0o700)
    return out


def _hold(ctx, lock_fn, inside=None, **kwargs):
    out = {}
    try:
        with lock_fn(**kwargs):
            out["inside"] = ctx.listing(ctx.data)
            if inside:
                out["did"] = inside(ctx)
        out["held"] = True
    except Exception as exc:
        out["held"] = ctx.n(exc)
    out["after"] = ctx.listing(ctx.data)
    return out


def _save_inside(ctx):
    return ctx.call(ctx.M.write_saved_charts, seeded_mapping(50))


def lock_msvcrt(ctx):
    M = ctx.M
    fake = FakeMsvcrt()
    ctx.p.set(M, "fcntl", None)
    ctx.p.set(M, "msvcrt", fake)
    out = {"store": _hold(ctx, M.saved_charts_lock, _save_inside),
           "prefs": _hold(ctx, M.preferences_lock), "calls": fake.calls}
    out["remember"] = ctx.call(M.remember_preference, "last_chart", "A")
    out["calls_after"] = fake.calls
    out.update(ctx.obs())
    return out


def lock_refused_ENOLCK(ctx):
    M = ctx.M
    fake = RefusingFcntl(errno.ENOLCK)
    ctx.p.set(M, "fcntl", fake)
    out = {"store": _hold(ctx, M.saved_charts_lock, _save_inside)}
    out["prefs"] = _hold(ctx, M.preferences_lock)
    out["remember"] = ctx.call(M.remember_preference, "last_chart", "A")
    out["notices"] = ctx.call(M.preferences_notices)
    out["calls"] = fake.calls > 0
    out.update(ctx.obs())
    return out


OLD_MTIME = 900_000.0


def _stray(path, data, old=True, mode=0o600):
    write_bytes(path, data, mode)
    if old:
        os.utime(path, (OLD_MTIME, OLD_MTIME), follow_symlinks=False)


def stray_two_valid(ctx):
    _stray(ctx.data / "saved_charts.json.0000000000000001.tmp", b'{"A": {}}')
    _stray(ctx.data / "saved_charts.json.0000000000000002.tmp", b'{"B": {}}')
    M = ctx.M
    out = {"before": ctx.listing()}
    out["load"] = ctx.call(M.load_saved_charts)
    out["notices"] = ctx.call(M.store_notices)
    out.update(ctx.obs())
    return out


CASES = {
    "write_seeded_3": lambda ctx: _write_case(ctx, seeded_mapping(1003), twice=True),
    "write_limit_patched": write_limit_patched,
    "load_name_twice": lambda ctx: _load_case(ctx, b'{"A": {}, "A": {"x": 1}}'),
    "load_link_bad_elsewhere": load_link_bad_elsewhere,
    "stand_malformed": stand_malformed,
    "old_beside_program": old_beside_program,
    "prefs_renames": prefs_renames,
    "prefs_remember_and_forget": prefs_remember_and_forget,
    "folder_existing_777": folder_existing_777,
    "lock_msvcrt": lock_msvcrt,
    "lock_refused_ENOLCK": lock_refused_ENOLCK,
    "stray_two_valid": stray_two_valid,
}

# Eleven of the twelve moved, by one entry of the notices each case records
# alone, when store_notices() came to say whether the launch closed a file
# that other accounts could change ('closed_to_others', false in every case),
# and moved back by that entry alone when it went (what was set aside is
# asked at each run instead: set_aside_notices).
# The link case moved when a link at the store's name came never to be
# followed: the file it names is neither read nor copied aside.
PINNED = {
    "write_seeded_3": "d499b56217ba5302eb814aaa1363a523e12eff7128f8a84e384412b38e322641",
    "write_limit_patched": "a1ec6cae1ed4d8690d338980b7ae508078c1cf893b14bf6e180812ead0a53128",
    "load_name_twice": "395b3595ffeecb380ddc6eda45b2069cde772fea3954e5e151bbd21042a0d3f2",
    "load_link_bad_elsewhere": "91cbcd23055a10dea85843fdf91f61801346346be8132de6ce747d7e65ccff86",
    "stand_malformed": "a242b1dbc41e5501c22dd033732dbd46c6c38eb418a3d2fb962f870849c28719",
    "old_beside_program": "9ca320615537030a3f0f36ba46f23362809f56bd30bf1b0895b45b77d7ba3ec1",
    "prefs_renames": "b01d0ffaa0430045a555f6812b46209ffcd976b258651e05e4d7d9a345630092",
    "prefs_remember_and_forget": "2436cfe1990024397c3ebb14fa73d8836d5fcf826f78d9c1f21eed3bce649e4f",
    "folder_existing_777": "cd6e21b07d2a09b6e4f297b47ffed23842835e4c17645915767094dd3362bf3f",
    "lock_msvcrt": "ba30ba269120465fa24385b269cec95b068a7e800880c959b4283da457c292dd",
    "lock_refused_ENOLCK": "5ef5f85a9fd644e4f0c519d559503b675e6ff92b45866e6f60de6faaba294d44",
    "stray_two_valid": "18312a36fcdf47271daac3341754381e3c9fcc533b850263b5087243d42855b0",
}


def test_the_sample_names_a_dozen_cases():
    assert len(CASES) == 12 and set(CASES) == set(PINNED)


@pytest.mark.parametrize("case", list(CASES))
def test_the_data_layers_behaviour_is_the_one_the_move_kept(engine, tmp_path, case):
    import engine as E
    import user_data
    assert E.write_saved_charts is user_data.write_saved_charts, "the premise: the engine takes the data layer whole"
    result = run_case(case, user_data, E, EXECUTABLE_DIR, tmp_path / case)
    assert digest(result) == PINNED[case], (case, json.dumps(result, sort_keys=True)[:2000])
