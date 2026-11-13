"""The data folder on Windows, run for real: a second local account, folders
given to it, the lists read back, and the data layer launched against each
scene in a fresh interpreter, as the app's first import launches it.

Windows only, as an administrator, on a machine that is thrown away after
the run: it makes a local account and leaves it. The suite never collects
this file (its name is not a test's); the Windows test workflow runs it,
and it exits 1 when any scene ends otherwise than it should.

Each scene names what is expected and prints what the launch found, the
owners read and the access lists, as icacls gives them. The other account
acts through its own logon (a network logon, used to make and open files as
it); a process started as it does not run on the hosted runner, which has no
desktop for it. The scenes of the files in the data folder (11-14, 16-19)
are launched by an ordinary account made for them, through a task the system
starts as that account, where the runner allows it; else by the job's own
account, and the check says so.

Every folder on the way to the data folder is judged as well: each must be
this account's or the system's and closed to other accounts. So the scenes'
folder is given a closed list of its own at the start (SYSTEM and
Administrators, full control; Users, reading), and each scene's base is
given to Administrators, so that the system drive's list, which passes
Modify down to every account that can log on, reaches no scene by
inheritance; a scene that wants a folder open to others opens it itself.
Scenes 20-23 are the whole path's: a link at a store's name never followed,
a data folder reached through a folder the other account may change, the
folder held while the app runs, and a folder whose list cannot be closed."""
import json
import os
import re
import secrets
import shutil
import string
import subprocess
import sys
import textwrap
import traceback
from pathlib import Path

if sys.platform != "win32":
    sys.exit("This check runs on Windows only.")

import ctypes
import msvcrt
from ctypes import wintypes

ROOT = Path(__file__).resolve().parent.parent
SCENES = Path(os.environ.get("SystemDrive", "C:") + "\\") / "zij-scenes"
OTHER = "otheraccount"
USER = os.environ["USERNAME"]
ADMINISTRATORS, SYSTEM = "S-1-5-32-544", "S-1-5-18"
REC = {"date_string": "1977-12-16", "time_string": "10:30:00", "time_standard": "LMT (Local Mean Time)",
       "location_query": "Florence", "lat": 43.7792, "lon": 11.2463}
FAILED = []

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
adv = ctypes.WinDLL("advapi32", use_last_error=True)
P, DW = ctypes.c_void_p, wintypes.DWORD


def _typed(fn, res, *args):
    fn.restype, fn.argtypes = res, list(args)
    return fn


CreateFileW = _typed(k32.CreateFileW, P, wintypes.LPCWSTR, DW, DW, P, DW, DW, P)
CloseHandle = _typed(k32.CloseHandle, wintypes.BOOL, P)
LocalFree = _typed(k32.LocalFree, P, P)
GetVolumeInformationByHandleW = _typed(k32.GetVolumeInformationByHandleW, wintypes.BOOL, P, P, DW, P, P,
                                       ctypes.POINTER(DW), P, DW)
GetSecurityInfo = _typed(adv.GetSecurityInfo, DW, P, ctypes.c_int, DW, ctypes.POINTER(P), ctypes.POINTER(P),
                         ctypes.POINTER(P), ctypes.POINTER(P), ctypes.POINTER(P))
ConvertSidToStringSidW = _typed(adv.ConvertSidToStringSidW, wintypes.BOOL, P, ctypes.POINTER(P))
LookupAccountNameW = _typed(adv.LookupAccountNameW, wintypes.BOOL, wintypes.LPCWSTR, wintypes.LPCWSTR, P,
                            ctypes.POINTER(DW), P, ctypes.POINTER(DW), ctypes.POINTER(DW))
LogonUserW = _typed(adv.LogonUserW, wintypes.BOOL, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, DW, DW,
                    ctypes.POINTER(P))
ImpersonateLoggedOnUser = _typed(adv.ImpersonateLoggedOnUser, wintypes.BOOL, P)
RevertToSelf = _typed(adv.RevertToSelf, wintypes.BOOL)
INVALID = ctypes.c_void_p(-1).value


def sid_text(sid):
    text = P()
    if not ConvertSidToStringSidW(sid, ctypes.byref(text)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.wstring_at(text.value)
    finally:
        LocalFree(text)


def sid_of(name):
    size, domain_size, use = DW(0), DW(0), DW(0)
    LookupAccountNameW(None, name, None, ctypes.byref(size), None, ctypes.byref(domain_size), ctypes.byref(use))
    sid, domain = ctypes.create_string_buffer(size.value), ctypes.create_unicode_buffer(domain_size.value)
    if not LookupAccountNameW(None, name, ctypes.cast(sid, P), ctypes.byref(size), ctypes.cast(domain, P),
                              ctypes.byref(domain_size), ctypes.byref(use)):
        raise ctypes.WinError(ctypes.get_last_error())
    return sid_text(ctypes.cast(sid, P))


def owner_read(path, follow=True):
    """What this account reads as the owner of `path` (a link or junction
    there opened itself unless `follow`), and whether its volume keeps
    access lists; the error's number where the read is refused."""
    flags = 0x02000000 | (0 if follow else 0x00200000)
    handle = CreateFileW(str(path), 0x00020000 | 0x80, 7, None, 3, flags, None)
    if handle in (None, INVALID):
        return {"error": ctypes.get_last_error()}
    try:
        volume = DW(0)
        GetVolumeInformationByHandleW(handle, None, 0, None, None, ctypes.byref(volume), None, 0)
        owner, descriptor = P(), P()
        code = GetSecurityInfo(handle, 1, 1, ctypes.byref(owner), None, None, None, ctypes.byref(descriptor))
        if code:
            return {"error": code, "keeps lists": bool(volume.value & 8)}
        try:
            return {"owner": sid_text(owner) if owner.value else None, "keeps lists": bool(volume.value & 8)}
        finally:
            LocalFree(descriptor)
    finally:
        CloseHandle(handle)


def run(*args, check=True, show=True):
    done = subprocess.run(list(args), capture_output=True, text=True, timeout=300)
    if show:
        print("  $", " ".join(args))
        for line in (done.stdout + done.stderr).strip().splitlines():
            print("   ", line)
    if check and done.returncode:
        raise SystemExit(f"{args[0]} failed: {done.returncode}")
    return done


def icacls(path, *more):
    """icacls on `path`: a change must succeed; a list read back is printed
    as given, refused or not."""
    return run("icacls", str(path), *more, check=bool(more))


def give(path, owner, link=False):
    """`path` given to `owner` (an account's name, or *SID), its owner set
    by icacls; a link or junction itself where `link`."""
    icacls(path, "/setowner", owner, *(["/L"] if link else []))


def other_logon(password):
    token = P()
    for kind in (3, 2, 4):          # network, interactive, batch
        if LogonUserW(OTHER, ".", password, kind, 0, ctypes.byref(token)):
            return token, kind
    return None, ctypes.get_last_error()


def as_other(token, path):
    """Whether the other account can read and change the file `path`, each
    tried by opening it as that account."""
    found = {}
    if not ImpersonateLoggedOnUser(token):
        return {"impersonation": ctypes.get_last_error()}
    try:
        for mode, how in (("read", "rb"), ("change", "r+b")):
            try:
                with open(path, how):
                    found[mode] = "allowed"
            except OSError as exc:
                found[mode] = f"refused ({exc.winerror or exc.errno})"
    finally:
        RevertToSelf()
    return found


class LUID(ctypes.Structure):
    _fields_ = [("LowPart", DW), ("HighPart", wintypes.LONG)]


class ONE_PRIVILEGE(ctypes.Structure):
    _fields_ = [("PrivilegeCount", DW), ("Luid", LUID), ("Attributes", DW)]


LookupPrivilegeValueW = _typed(adv.LookupPrivilegeValueW, wintypes.BOOL, wintypes.LPCWSTR, wintypes.LPCWSTR,
                               ctypes.POINTER(LUID))
AdjustTokenPrivileges = _typed(adv.AdjustTokenPrivileges, wintypes.BOOL, P, wintypes.BOOL, P, DW, P, P)


def grant_right(right, account):
    """Give the account named `account` the user right `right` (a logon
    right or a privilege) in the machine's local policy, by secedit: the
    policy exported, the account's SID added to the right's line, the policy
    imported. A logon made after it holds it."""
    inf, db = SCENES / f"{right}.inf", SCENES / f"{right}.sdb"
    run("secedit", "/export", "/cfg", str(inf), "/areas", "USER_RIGHTS", show=False)
    text = inf.read_text(encoding="utf-16")
    line = re.search(r"^" + right + r"\s*=.*$", text, re.M)
    if line:
        text = text.replace(line.group(0), line.group(0).rstrip() + ",*" + sid_of(account))
    else:
        text = text.replace("[Privilege Rights]", "[Privilege Rights]\n" + right + " = *" + sid_of(account))
    inf.write_text(text, encoding="utf-16")
    done = run("secedit", "/configure", "/db", str(db), "/cfg", str(inf), "/areas", "USER_RIGHTS", check=False,
               show=False)
    print(f"  {right} given to {account}:", "yes" if done.returncode == 0 else f"refused ({done.returncode})")


def logon(account, password):
    """A logon of `account` (network, else interactive, else batch), and
    its kind; (None, the error) where every one is refused."""
    token = P()
    for kind in (3, 2, 4):          # network, interactive, batch
        if LogonUserW(account, ".", password, kind, 0, ctypes.byref(token)):
            return token, kind
    return None, ctypes.get_last_error()


def enable_link_privilege(token):
    """Turn on the privilege to make symbolic links in the logon's token,
    where the account holds it; whether that was done."""
    luid = LUID()
    if not LookupPrivilegeValueW(None, "SeCreateSymbolicLinkPrivilege", ctypes.byref(luid)):
        return False
    wanted = ONE_PRIVILEGE(1, luid, 0x2)            # SE_PRIVILEGE_ENABLED
    ok = AdjustTokenPrivileges(token, False, ctypes.byref(wanted), 0, None, None)
    return bool(ok) and ctypes.get_last_error() != 1300     # ERROR_NOT_ALL_ASSIGNED


def made_as(token, account, path, data=None, link_to=None):
    """Make, as the account whose logon is `token`, the file `path` holding
    `data`, or a file symbolic link at `path` to `link_to`; how it was made.
    A link that account may not make (no Developer Mode, no privilege) is
    made by the job and given to it (icacls /setowner /L), and said so."""
    why = None
    if token and ImpersonateLoggedOnUser(token):
        try:
            if link_to is None:
                try:
                    path.write_bytes(data)
                    return f"made by {account} through its own logon"
                except OSError as exc:
                    why = exc.winerror or exc.errno
            else:
                try:
                    os.symlink(link_to, path)
                    return f"made by {account} through its own logon"
                except OSError as exc:
                    why = exc.winerror or exc.errno
        finally:
            RevertToSelf()
    else:
        why = "no logon" if not token else f"impersonation refused ({ctypes.get_last_error()})"
    if link_to is None:
        path.write_bytes(data)
    else:
        os.symlink(link_to, path)
    give(path, account, link=link_to is not None)
    return f"made by the job and given to {account} (its own make: {why})"


def read_as(token, path):
    """The bytes of `path` as the account whose logon is `token` reads them;
    the refusal, as text, where it cannot."""
    if not ImpersonateLoggedOnUser(token):
        return f"impersonation refused ({ctypes.get_last_error()})"
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        return f"refused ({exc.winerror or exc.errno})"
    finally:
        RevertToSelf()


def opened_as(token, path):
    """`path` opened for reading, as the account whose logon is `token`
    (None: the job): while it stays open the folder it is in cannot be
    renamed, which is how an account may refuse the user's launch the move."""
    if token and ImpersonateLoggedOnUser(token):
        try:
            return open(path, "rb")
        finally:
            RevertToSelf()
    return open(path, "rb")


def held_as(token, path, share_delete=True):
    """`path` opened for reading and writing as the account whose logon is
    `token`, sharing reading, writing and, where `share_delete`, deleting (a
    handle that shares no deleting refuses a replace of the name); its
    descriptor, or the refusal, as text."""
    if not token:
        return "no logon"
    if not ImpersonateLoggedOnUser(token):
        return f"impersonation refused ({ctypes.get_last_error()})"
    try:
        handle = CreateFileW(str(path), 0xC0000000, 0x7 if share_delete else 0x3, None, 3, 0x80, None)
        if handle is None or handle == INVALID:
            return f"refused ({ctypes.get_last_error()})"
        return msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
    finally:
        RevertToSelf()


def written_through(fd, data):
    """`data` written over the file open at `fd`, from its start; what came of it."""
    if isinstance(fd, str):
        return f"no handle: {fd}"
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, data)
        os.ftruncate(fd, len(data))
        return "written"
    except OSError as exc:
        return f"refused ({exc.winerror or exc.errno})"


def written_as(token, path, data):
    """`data` written at `path` by its name, as the account whose logon is
    `token`; what came of it."""
    if not token:
        return "no logon"
    if not ImpersonateLoggedOnUser(token):
        return f"impersonation refused ({ctypes.get_last_error()})"
    try:
        Path(path).write_bytes(data)
        return "written"
    except OSError as exc:
        return f"refused ({exc.winerror or exc.errno})"
    finally:
        RevertToSelf()


def own_entries(path):
    """The entries of `path`'s access list that it did not inherit, as
    icacls lists them; None where icacls cannot read the list."""
    done = run("icacls", str(path), check=False)
    if done.returncode:
        return None
    lines = [line.replace(str(path), "", 1).strip() for line in done.stdout.splitlines()]
    return [line for line in lines if ":(" in line and "(I)" not in line]


def closed_list(path):
    """Whether the list of `path`, as icacls reads it, is the protected one
    the data layer gives: no entry inherited, and none for any account but
    this one, SYSTEM and Administrators."""
    done = run("icacls", str(path), check=False, show=False)
    if done.returncode:
        return False
    lines = [line.replace(str(path), "", 1).strip() for line in done.stdout.splitlines()]
    entries = [line for line in lines if ":(" in line]
    kept = {USER.lower(), "system", "administrators"}
    return bool(entries) and all("(I)" not in line and line.split(":(")[0].rsplit("\\", 1)[-1].lower() in kept
                                 for line in entries)


def renamed_as(token, folder):
    """Whether the account whose logon is `token` may rename `folder` now:
    its error; None where it may (the folder is then named back, by the
    job)."""
    if not token:
        return "no logon"
    aside = folder.with_name(folder.name + "-theirs")
    if not ImpersonateLoggedOnUser(token):
        return f"impersonation refused ({ctypes.get_last_error()})"
    try:
        os.rename(folder, aside)
    except OSError as exc:
        return exc.winerror or exc.errno
    finally:
        RevertToSelf()
    os.rename(aside, folder)
    return None


def closed_to(path, *accounts):
    """Give `path` a list of its own: SYSTEM and Administrators, and each of
    `accounts`, full control; nothing inherited."""
    icacls(path, "/inheritance:r", "/grant:r", f"*{SYSTEM}:(OI)(CI)F", f"*{ADMINISTRATORS}:(OI)(CI)F",
           *(f"{a}:(OI)(CI)F" for a in accounts))


def linked_as(token, path, link):
    """A hard link at `link` to the file `path`, made as the account whose
    logon is `token`; what came of it."""
    if not token:
        return "no logon"
    if not ImpersonateLoggedOnUser(token):
        return f"impersonation refused ({ctypes.get_last_error()})"
    try:
        os.link(path, link)
        return "linked"
    except OSError as exc:
        return f"refused ({exc.winerror or exc.errno})"
    finally:
        RevertToSelf()


def moved_as(token, path, to):
    """`path` renamed to `to` as the account whose logon is `token`; what
    came of it."""
    if not token:
        return "no logon"
    if not ImpersonateLoggedOnUser(token):
        return f"impersonation refused ({ctypes.get_last_error()})"
    try:
        os.rename(path, to)
        return "renamed"
    except OSError as exc:
        return f"refused ({exc.winerror or exc.errno})"
    finally:
        RevertToSelf()


def rename_refused(folder):
    """Whether the system refuses the job, now, the renaming of `folder`: its
    error; None where it does not (the folder is then named back)."""
    aside = folder.with_name(folder.name + "-aside")
    try:
        os.rename(folder, aside)
    except OSError as exc:
        return exc.winerror or exc.errno
    os.rename(aside, folder)
    return None


def bytes_of(path):
    """The bytes of `path`, read by the job; the refusal, as text."""
    try:
        return path.read_bytes()
    except OSError as exc:
        return repr(exc)


LAUNCH = textwrap.dedent("""
    import json, os, sys
    import user_data as u
    out = {"data folder": str(u.DATA_DIR), "error": u.DATA_DIR_ERROR,
           "state": list(u.data_folder_state()),
           "not ours": u.DATA_FOLDER_NOT_OURS, "former not ours": u.FORMER_FOLDER_NOT_OURS,
           "former not carried": u.FORMER_FOLDER_NOT_CARRIED,
           "path open": getattr(u, "DATA_FOLDER_PATH_OPEN", "(none here)"),
           "not closed": getattr(u, "DATA_FOLDER_NOT_CLOSED", "(none here)")}
    try:
        with u.saved_charts_lock():
            out["brought in"] = u.bring_in_the_old_store()
    except Exception as exc:
        out["brought in"] = repr(exc)
    out["loaded"] = sorted(u.load_saved_charts() or {})
    out["notices"] = {k: u.store_notices()[k] for k in ("unreadable", "copy")}
    try:
        with u.saved_charts_lock():
            charts = dict(u.saved_charts_as_they_stand().charts or {})
            charts["Mine"] = json.loads(sys.argv[1])
            out["saved"] = u.write_saved_charts(charts)
    except Exception as exc:
        out["saved"] = repr(exc)
    out["preference written"] = u.write_preferences({"last_chart": "Mine"})
    out["set aside"] = getattr(u, "set_aside_notices", lambda: None)()
    # The folders whose list the launch could not close, and why.
    out["lists left open"] = dict(getattr(u, "_WINDOWS_LISTS_LEFT_OPEN", {}))
    print(json.dumps(out))
""")


# A launch that loads and writes nothing: what the launch's repair and the
# loads after it leave, before any save makes a new store.
LOAD = textwrap.dedent("""
    import json, os
    import user_data as u
    out = {"data folder": str(u.DATA_DIR), "error": u.DATA_DIR_ERROR, "state": list(u.data_folder_state())}
    out["loaded"] = sorted(u.load_saved_charts() or {})
    out["closed"] = u.store_notices().get("closed_to_others")
    # What the page is told of a file set aside, or of one that could not be.
    out["set aside"] = getattr(u, "set_aside_notices", lambda: None)()
    try:                    # the file the next load reads, read here (the preferences' own load needs the engine)
        out["last chart"] = json.loads(u.PREFERENCES_PATH.read_text(encoding="utf-8")).get("last_chart")
    except (OSError, ValueError) as exc:
        out["last chart"] = repr(exc)
    out["names"] = sorted(os.listdir(u.DATA_DIR))
    print(json.dumps(out))
""")


# The one button's call: what was set aside brought back, then a load.
RESTORE = textwrap.dedent("""
    import json, os
    import user_data as u
    restore = getattr(u, "restore_set_aside", None)
    out = {"restored": restore() if restore else "no restore here"}
    out["loaded"] = sorted(u.load_saved_charts() or {})
    out["set aside"] = getattr(u, "set_aside_notices", lambda: None)()
    out["names"] = sorted(os.listdir(u.DATA_DIR))
    print(json.dumps(out))
""")


# A launch that holds its data folder while the app runs: it says what it
# found, waits for a line, then saves one chart and says whether it was kept.
HOLD = textwrap.dedent("""
    import json, sys
    import user_data as u
    print(json.dumps({"state": list(u.data_folder_state()),
                      "loaded": sorted(u.load_saved_charts() or {})}), flush=True)
    sys.stdin.readline()
    try:
        with u.saved_charts_lock():
            charts = dict(u.saved_charts_as_they_stand().charts or {})
            charts["Held"] = json.loads(sys.argv[1])
            saved = u.write_saved_charts(charts)
    except Exception as exc:
        saved = repr(exc)
    print(json.dumps({"saved": saved}), flush=True)
""")


# The app's own lock of the store, asked in a process of its own while
# another holds it: the data layer's _take_file_lock, with a short deadline.
SECOND_LOCK = textwrap.dedent("""
    import json
    import user_data as u
    lock = u.SAVED_CHARTS_PATH.parent / "saved_charts.lock"
    try:
        fd = u._take_file_lock(lock, deadline=u._clock.monotonic() + 3)
    except u.DataLockBusy as exc:
        found = "refused" if type(exc) is u.DataLockBusy else f"refused otherwise ({type(exc).__name__})"
    except Exception as exc:
        found = f"failed ({exc!r})"
    else:
        found = "no file lock" if fd is None else "taken"
        if fd is not None:
            u._give_file_lock(fd, lock)
    print(json.dumps({"by": "the app's own _take_file_lock, in a process of its own",
                      "a second exclusive lock": found}))
""")


def launch(base, code=LAUNCH):
    """The data layer launched as the app launches it, APPDATA at `base`
    (None: the account's own); what it found, as a mapping."""
    env = dict(os.environ)
    if base is not None:
        env["APPDATA"] = str(base)
    done = subprocess.run([sys.executable, "-c", code, json.dumps(REC)], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=300)
    if done.returncode:
        print(done.stdout, done.stderr)
        return {"crashed": done.returncode}
    return json.loads(done.stdout.strip().splitlines()[-1])


# The same launch, run by the ordinary account a scheduled task starts:
# its own token, its own profile, no administrator's rights. Its output is
# left in a file the job reads.
AS_ORDINARY = textwrap.dedent("""
    import contextlib, io, json, os, sys, traceback
    base, out = sys.argv[1], sys.argv[2]
    if base != "-":
        os.environ["APPDATA"] = base
    sys.path.insert(0, {code!r})
    os.chdir({code!r})
    held = io.StringIO()
    try:
        with contextlib.redirect_stdout(held):
            sys.argv = ["-c", {rec!r}]
            exec(compile({launch!r}, "launch", "exec"), {{"__name__": "__main__"}})
        text = held.getvalue().strip().splitlines()[-1]
    except BaseException:
        text = json.dumps({{"crashed": traceback.format_exc()}})
    with open(out + ".part", "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(out + ".part", out)
""")
ORDINARY = "zijuser"


def launch_as_ordinary(base, password, wait=120, script="as_ordinary.py"):
    """The data layer launched by the ordinary account, APPDATA at `base`
    (None: the account's own), through a scheduled task that runs once the
    launch in `script`; what it found, as a mapping, or {"not run": why}."""
    import time
    launch_as_ordinary.count = getattr(launch_as_ordinary, "count", 0) + 1
    name = f"zij-launch-{launch_as_ordinary.count}"
    out = SCENES / "out" / f"{name}.json"
    script = SCENES / "code" / script
    command = " ".join(f'"{a}"' if " " in a else a for a in (sys.executable, str(script), str(base or "-"), str(out)))
    # Not through run(): the password is never printed.
    made = subprocess.run(["schtasks", "/create", "/tn", name, "/tr", command, "/sc", "once", "/st", "23:59",
                           "/ru", ORDINARY, "/rp", password, "/rl", "LIMITED", "/f"],
                          capture_output=True, text=True, timeout=300)
    print(f"  $ schtasks /create /tn {name} /tr {command} /ru {ORDINARY} (its password) ->", made.returncode)
    if made.returncode:
        return {"not run": f"the task could not be made ({made.returncode})"}
    run("schtasks", "/run", "/tn", name, check=False)
    deadline = time.monotonic() + wait
    while not out.exists() and time.monotonic() < deadline:
        time.sleep(1)
    if not out.exists():
        done = run("schtasks", "/query", "/tn", name, "/v", "/fo", "list", check=False, show=False)
        last = [line.strip() for line in done.stdout.splitlines() if line.startswith(("Status", "Last Result"))]
        run("schtasks", "/delete", "/tn", name, "/f", check=False, show=False)
        return {"not run": f"no output in {wait} s: {last}"}
    run("schtasks", "/delete", "/tn", name, "/f", check=False, show=False)
    return json.loads(out.read_text(encoding="utf-8"))


def store(folder, *names):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "saved_charts.json").write_text(json.dumps({name: REC for name in names}, indent=2))
    return folder / "saved_charts.json"


def expect(scene, ok, found):
    print(f"[{'as it should be' if ok else 'NOT AS IT SHOULD BE'}] {scene}")
    print("  found:", json.dumps(found))
    if not ok:
        FAILED.append(scene)


def refused(found, reason_key="not ours", state="used"):
    return (found.get("state") == [state, found.get(reason_key)] and found.get("loaded") == []
            and found.get("saved") is False and found.get("preference written") is False)


def accepted(found, *charts):
    return (found.get("state") == [None, None] and found.get("loaded") == sorted(charts)
            and found.get("saved") is True and found.get("preference written") is True)


def fresh(name):
    base = SCENES / name
    base.mkdir(parents=True)
    give(base, f"*{ADMINISTRATORS}")
    return base, base / "Zij", base / "TraditionalAstrologyEngine"


def looked(path):
    """What stands at the store's name after a launch, for the scene's
    line: a link or a file, the name's own owner, and the charts' names
    in it, read by the job."""
    seen = {"link": os.path.islink(path), "owner": owner_read(path, follow=False).get("owner")}
    try:
        seen["charts"] = sorted(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        seen["charts"] = repr(exc)
    return seen


def stored_scenes(token, alphabet):
    """(11)-(19): the files in the data folder, each judged by its own owner,
    after (20)-(23), the whole path to it (whole_path_scenes). The user is an ordinary account made here, its launches run by a task
    that starts as it, where the runner allows; else the job's own account."""
    password = ("Aa1!" + "".join(secrets.choice(alphabet) for _ in range(10)))
    made = subprocess.run(["net", "user", ORDINARY, password, "/add"], capture_output=True, text=True, timeout=300)
    print("  $ net user", ORDINARY, "(a generated password) /add ->", made.returncode)
    (SCENES / "code").mkdir(exist_ok=True)
    (SCENES / "out").mkdir(exist_ok=True)
    if made.returncode == 0:
        icacls(SCENES / "out", "/grant", f"{ORDINARY}:(OI)(CI)F")
    shutil.copy2(ROOT / "user_data.py", SCENES / "code" / "user_data.py")
    (SCENES / "code" / "as_ordinary.py").write_text(
        AS_ORDINARY.format(code=str(SCENES / "code"), rec=json.dumps(REC), launch=LAUNCH), encoding="utf-8")
    (SCENES / "code" / "as_ordinary_load.py").write_text(
        AS_ORDINARY.format(code=str(SCENES / "code"), rec=json.dumps(REC), launch=LOAD), encoding="utf-8")
    (SCENES / "code" / "as_ordinary_restore.py").write_text(
        AS_ORDINARY.format(code=str(SCENES / "code"), rec=json.dumps(REC), launch=RESTORE), encoding="utf-8")
    (SCENES / "code" / "as_ordinary_second_lock.py").write_text(
        AS_ORDINARY.format(code=str(SCENES / "code"), rec=json.dumps(REC), launch=SECOND_LOCK), encoding="utf-8")
    user, user_token, go, go_load = USER, None, launch, (lambda base: launch(base, LOAD))
    go_restore = (lambda base: launch(base, RESTORE))
    go_second_lock = (lambda base: launch(base, SECOND_LOCK))
    if made.returncode == 0:
        grant_right("SeBatchLogonRight", ORDINARY)
        grant_right("SeCreateSymbolicLinkPrivilege", ORDINARY)
        # (14) An ordinary first launch and the launch after it, as the
        # ordinary account, its own APPDATA: the probe of whether its
        # launches run here at all.
        first = launch_as_ordinary(None, password)
        if "not run" not in first:
            user, go = ORDINARY, (lambda base: launch_as_ordinary(base, password))
            go_load = (lambda base: launch_as_ordinary(base, password, script="as_ordinary_load.py"))
            go_restore = (lambda base: launch_as_ordinary(base, password, script="as_ordinary_restore.py"))
            go_second_lock = (lambda base: launch_as_ordinary(base, password, script="as_ordinary_second_lock.py"))
            user_token, _kind = logon(ORDINARY, password)
            expect("14: an ordinary first launch as the ordinary account, its own APPDATA: accepted",
                   accepted(first), first)
            again = go(None)
            expect("14: the launch after it: accepted, the chart it saved loaded", accepted(again, "Mine"), again)
        else:
            print("[note] the ordinary account's launches do not run here:", first["not run"])
    if user == USER:
        print("[note] the launches below run as the job's account", USER)
    print("The scenes' user:", user, sid_of(user))
    if user_token:
        print("  its link privilege on:", enable_link_privilege(user_token))
    if token:
        print("  the other account's link privilege on:", enable_link_privilege(token))
    injected = json.dumps({"Injected": REC}, indent=2).encode()

    def scene_base(name):
        """A scene's base, given to the scenes' user where that is not the
        job: every folder on the way to its data folder is then the user's
        or the system's, and closed to other accounts."""
        base, zij, legacy = fresh(name)
        if user != USER:
            icacls(base, "/grant", f"{user}:(OI)(CI)F")
        return base, zij, legacy

    # (20)-(23) first, each on its own, so that a scene below that fails in its
    # own setup cannot keep them from running.
    whole_path_scenes(token, user, user_token, go, scene_base)

    # (15) The owner of a file as opened, read through its own handle: a file
    # of the other account's opened by its name, and through a link of the
    # job's to it, and a file of the job's.
    where = SCENES / "15-opened"
    where.mkdir()
    theirs = where / "theirs.json"
    print("  their file:", made_as(token, OTHER, theirs, injected))
    os.symlink(theirs, where / "link.json")
    (where / "mine.json").write_bytes(b"{}")
    probe = ("import json, os, sys; sys.path.insert(0, sys.argv[1]); import user_data as u; "
             "print(json.dumps([u._windows_owner_of_the_open(os.open(p, os.O_RDONLY)) for p in sys.argv[2:]]))")
    done = subprocess.run([sys.executable, "-c", probe, str(SCENES / "code"), *(str(where / n) for n in
                           ("theirs.json", "link.json", "mine.json"))], env=dict(os.environ, APPDATA=str(where)),
                          capture_output=True, text=True, timeout=300)
    print("  the owners read through the opened files' handles:", done.stdout.strip(), done.stderr.strip()[-300:])
    try:
        read = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        read = None
    expect("15: the owner of a file as opened, through its handle: the other account's file, by its name and through"
           " a link, and the job's own",
           read == [sid_of(OTHER), sid_of(OTHER), owner_read(where / "mine.json").get("owner")], read)

    for name in ("Zij", "TraditionalAstrologyEngine"):
        # (11) The other account's own store, put in the user's folder while it was open to others.
        base, zij, _legacy = scene_base(f"11-planted-store-{name}")
        folder = base / name
        os.mkdir(folder)                # as an older version made it: the list from above, Modify for all
        give(folder, user)
        icacls(folder, "/grant", "*S-1-5-11:(OI)(CI)M")     # the list a drive's root passes down
        print("  the planted store:", made_as(token, OTHER, folder / "saved_charts.json", injected))
        print("  its owner:", owner_read(folder / "saved_charts.json", follow=False))
        found = go(base)
        after = looked(zij / "saved_charts.json")
        print("  the store's name after the save:", after)
        expect(f"11: another account's store in the user's {name} folder: not loaded, said unreadable with no copy,"
               " the save a new store of the user's at the name",
               found.get("state") == [None, None] and found.get("loaded") == []
               and found.get("notices") == {"unreadable": True, "copy": None} and found.get("saved") is True
               and after == {"link": False, "owner": sid_of(user), "charts": ["Mine"]}, found)

        # (12) The other account's file link at the store's name, to a file it reads.
        base, zij, _legacy = scene_base(f"12-planted-link-{name}")
        folder = base / name
        os.mkdir(folder)
        give(folder, user)
        theirs = SCENES / f"12-theirs-{name}"
        theirs.mkdir()
        give(theirs, OTHER)
        harvest = theirs / "harvest.json"
        print("  its file:", made_as(token, OTHER, harvest, injected))
        print("  the planted link:", made_as(token, OTHER, folder / "saved_charts.json", link_to=harvest))
        print("  the link's own owner:", owner_read(folder / "saved_charts.json", follow=False),
              "| the file it leads to:", owner_read(folder / "saved_charts.json"))
        found = go(base)
        after = looked(zij / "saved_charts.json")
        read = read_as(token, harvest) if token else harvest.read_bytes()
        print("  the store's name after the save:", after)
        print("  the other account's file, read through its logon:",
              read if isinstance(read, str) else sorted(json.loads(read)))
        expect(f"12: another account's link at the store's name in the user's {name} folder: not followed, said"
               " unreadable with no copy, the save a new store of the user's at the name, its file unchanged",
               found.get("state") == [None, None] and found.get("loaded") == []
               and found.get("notices") == {"unreadable": True, "copy": None} and found.get("saved") is True
               and after == {"link": False, "owner": sid_of(user), "charts": ["Mine"]} and read == injected, found)
        found = go(base)
        read = read_as(token, harvest) if token else harvest.read_bytes()
        expect(f"12: the launch after it ({name}): the user's own store loaded, the other account's file unchanged",
               found.get("loaded") == ["Mine"] and found.get("saved") is True and read == injected, found)

        # (13) The user's own link at the store's name, to a store of the user's
        # elsewhere, in a folder given the list a drive's root passes down
        # (every account that can log on may change the files in it) or the
        # protected list: in neither is the link read or written through, and
        # the page is told.
        for kind in ("open", "closed"):
            base, zij, _legacy = scene_base(f"13-own-link-{name}-{kind}")
            folder = base / name
            os.mkdir(folder)
            give(folder, user)
            synced = SCENES / f"13-synced-{name}-{kind}"
            synced.mkdir()
            give(synced, user)
            if kind == "closed":
                icacls(synced, "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F", f"*{SYSTEM}:(OI)(CI)F",
                       f"*{ADMINISTRATORS}:(OI)(CI)F")
            else:
                icacls(synced, "/grant", "*S-1-5-11:(OI)(CI)M")     # the list a drive's root passes down
            kept = synced / "store.json"
            print("  the user's store:", made_as(user_token, user, kept, json.dumps({"Old": REC}, indent=2).encode()))
            print("  the user's link:", made_as(user_token, user, folder / "saved_charts.json", link_to=kept))
            found = go(base)
            after = looked(zij / "saved_charts.json")
            print("  the store's name after the save:", after)
            expect(f"13: the user's own link at the store's name in the user's {name} folder, to a store in a"
                   f" folder {'with the protected list' if kind == 'closed' else 'every account may write in'}:"
                   " neither read nor written through, the page told",
                   found.get("state") == [None, None] and found.get("loaded") == []
                   and found.get("saved") is False and after["link"] is True
                   and (found.get("set aside") or {}).get("unfollowed") is True
                   and sorted(json.loads(kept.read_text(encoding="utf-8"))) == ["Old"], found)

    own = json.dumps({"Old": REC}, indent=2).encode()

    # (16) The user's former folder, its move refused while a file in it is
    # held open, as the other account can hold one of its own there. The copy
    # would make each file the user's: another account's store is not carried.
    base, zij, legacy = scene_base("16-copied-theirs")
    os.mkdir(legacy)
    give(legacy, user)
    planted = legacy / "saved_charts.json"
    print("  the planted store:", made_as(token, OTHER, planted, injected))
    print("  its owner:", owner_read(planted, follow=False))
    held = opened_as(token, planted)
    try:
        refusal = rename_refused(legacy)
        print("  the folder's rename while the other account holds the store open, refused with:", refusal)
        found = go(base)
    finally:
        held.close()
    print("  in the base after the launch:", sorted(p.name for p in base.iterdir()))
    expect("16: another account's store in the user's former folder, the move refused: not copied in, no data folder"
           " made, the reason said",
           refusal is not None and found.get("state") == ["made", found.get("former not carried")]
           and found.get("loaded") == [] and sorted(p.name for p in base.iterdir()) == [legacy.name]
           and bytes_of(planted) == injected, found)

    base, zij, legacy = scene_base("16-copied-own")
    os.mkdir(legacy)
    give(legacy, user)
    mine = legacy / "saved_charts.json"
    print("  the user's store:", made_as(user_token, user, mine, own))
    print("  its owner:", owner_read(mine, follow=False))
    held = opened_as(user_token, mine)
    try:
        refusal = rename_refused(legacy)
        print("  the folder's rename while the user holds the store open, refused with:", refusal)
        found = go(base)
    finally:
        held.close()
    after = looked(zij / "saved_charts.json")
    print("  the store's name after the save:", after)
    expect("16: the user's own former folder, the move refused: copied in, the former folder kept",
           refusal is not None and found.get("state") == [None, None] and found.get("loaded") == ["Old"]
           and found.get("saved") is True and after["charts"] == ["Mine", "Old"] and bytes_of(mine) == own, found)

    # (17) The data folder standing with no store, beside the user's former
    # folder: another account's store there is not brought in as the user's.
    base, zij, legacy = scene_base("17-former-store-theirs")
    os.mkdir(zij)
    give(zij, user)
    os.mkdir(legacy)
    give(legacy, user)
    planted = legacy / "saved_charts.json"
    print("  the planted store:", made_as(token, OTHER, planted, injected))
    print("  its owner:", owner_read(planted, follow=False))
    found = go(base)
    after = looked(zij / "saved_charts.json")
    print("  the store's name after the save:", after)
    expect("17: another account's store in the former folder beside the data folder: not brought in, the save the"
           " user's alone",
           found.get("state") == [None, None] and found.get("brought in") is False and found.get("loaded") == []
           and found.get("saved") is True and after == {"link": False, "owner": sid_of(user), "charts": ["Mine"]}
           and bytes_of(planted) == injected, found)

    # The user's own store there: brought in where the former folder has the
    # protected list; where it is given the list a drive's root passes down,
    # which lets every account change the store, it is not read, and is left
    # where it is.
    for kind in ("closed", "open"):
        base, zij, legacy = scene_base(f"17-former-store-own-{kind}")
        os.mkdir(zij)
        give(zij, user)
        os.mkdir(legacy)
        give(legacy, user)
        if kind == "closed":
            icacls(legacy, "/inheritance:r", "/grant:r", f"{user}:(OI)(CI)F", f"*{SYSTEM}:(OI)(CI)F",
                   f"*{ADMINISTRATORS}:(OI)(CI)F")
        else:
            icacls(legacy, "/grant", "*S-1-5-11:(OI)(CI)M")     # the list a drive's root passes down
        mine = legacy / "saved_charts.json"
        print("  the user's store:", made_as(user_token, user, mine, own))
        found = go(base)
        after = looked(zij / "saved_charts.json")
        print("  the store's name after the save:", after)
        if kind == "closed":
            expect("17: the user's own store in the former folder beside the data folder, the folder's list"
                   " protected: brought in",
                   found.get("state") == [None, None] and found.get("brought in") is True
                   and found.get("loaded") == ["Old"] and found.get("saved") is True
                   and after["charts"] == ["Mine", "Old"], found)
        else:
            expect("17: the user's own store in the former folder beside the data folder, a folder every account"
                   " may write in: not read, left where it is",
                   found.get("state") == [None, None] and found.get("brought in") is False
                   and found.get("loaded") == [] and found.get("saved") is True and after["charts"] == ["Mine"]
                   and bytes_of(mine) == own, found)

    # (18) The user's own store, and then the user's own preferences, made by
    # the user's launch, then given an explicit Modify entry for the other
    # account (by the job, icacls /grant), which survives the folder's list
    # being closed. With no handle of the other account's open on it, or one
    # that shares deleting, the next launch moves the file aside, under a
    # recovery name beside it, with the folder's list alone, and reads
    # nothing of it: the store's name is left empty, nothing is loaded, and
    # the page is told that something awaits restoring. The one button's call
    # then brings the store back as a new file that takes the folder's list
    # alone, and the other account's write through the handle it held from
    # before the launch reaches nothing the next load reads. With a handle
    # that shares no deleting, the move is refused: the file is not read and
    # the page is told that it could not be set aside.
    names = ("saved_charts.json", "preferences.json")
    planted = {"saved_charts.json": injected, "preferences.json": json.dumps({"last_chart": "Injected"}).encode()}
    for hold in (None, "sharing deleting", "sharing no deleting"):
        for name in names:
            base, zij, _legacy = scene_base(f"18-explicit-entry-{name}-{(hold or 'no handle').replace(' ', '-')}")
            os.mkdir(zij)
            give(zij, user)
            first = go(base)
            target = zij / name
            icacls(target, "/grant", f"{OTHER}:M")
            held = held_as(token, target, share_delete=hold == "sharing deleting") if hold else "none held"
            print("  the other account's handle on", name, "->", held if isinstance(held, str) else f"held, {hold}")
            found = go_load(base)
            listed = found.get("names") or []
            aside = [each for each in listed if each.startswith(name + ".set-aside-")]
            told = found.get("set aside") or {}
            # The store's own scene loads nothing; the preferences' loads the store, which stands as it was.
            charts = [] if name == "saved_charts.json" else ["Mine"]
            by_name = written_as(token, target, planted[name])
            seen = {"first": first, "launch": found, "by name": by_name}
            if hold == "sharing no deleting":
                through = written_through(held, planted[name])
                again = go_load(base)
                seen.update({"through the handle": through, "next load": again})
                expect(f"18: an explicit write entry for another account on the user's {name}, its handle held"
                       " sharing no deleting: the move aside refused, the file not read, the page told so",
                       accepted(first) and found.get("loaded") == charts and name in listed and aside == []
                       and told.get("held") is True and again.get("loaded") == charts
                       and (again.get("set aside") or {}).get("held") is True, seen)
                if not isinstance(held, str):
                    os.close(held)
                continue
            entries = own_entries(zij / aside[0]) if len(aside) == 1 else None
            seen.update({"set aside as": aside, "its own entries": entries})
            ok = (accepted(first) and found.get("loaded") == charts and name not in listed and len(aside) == 1
                  and entries == [] and told.get("awaiting") is True and not told.get("held")
                  and by_name.startswith("refused"))
            if name == "saved_charts.json":
                restored = go_restore(base)
                through = written_through(held, planted[name]) if hold else "no handle"
                again = go_load(base)
                after = own_entries(zij / name)
                seen.update({"restore": restored, "through the handle": through, "next load": again,
                             "the store's own entries after": after})
                # (The file set aside is removed; one the other account holds open, sharing deleting, may
                # still be listed until its handle closes, and is then no file of the user's to read.)
                ok = (ok and restored.get("restored") is True and restored.get("loaded") == ["Mine"]
                      and (restored.get("set aside") or {}).get("awaiting") is False
                      and again.get("loaded") == ["Mine"] and after == [])
            else:
                through = written_through(held, planted[name]) if hold else "no handle"
                seen.update({"through the handle": through})
            expect(f"18: an explicit write entry for another account on the user's {name}, {hold or 'no'} handle"
                   " held: moved aside under a recovery name with the folder's list alone, not read, the page told;"
                   + (" the restore brings it back as a new file the handle does not reach"
                      if name == "saved_charts.json" else ""), ok, seen)
            if not isinstance(held, str):
                os.close(held)

    # (19) A lock file of the user's that the other account may write (an
    # explicit Modify entry), held by one window across a launch, through a
    # handle that shares deleting: the launch narrows its list in place and
    # never replaces it, so the window keeps holding the lock on the file
    # under the name, and a second exclusive lock on it is refused: asked by
    # the app's own lock call, in a process of its own, as the user.
    base, zij, _legacy = scene_base("19-wide-lock-held")
    os.mkdir(zij)
    give(zij, user)
    first = go(base)
    lock = zij / "saved_charts.lock"
    print("  the lock file:", made_as(user_token, user, lock, b""))
    icacls(lock, "/grant", f"{OTHER}:M")
    before = os.stat(lock).st_ino
    handle = CreateFileW(str(lock), 0xC0000000, 0x7, None, 3, 0x80, None)
    one = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY) if handle not in (None, INVALID) else None
    try:
        if one is not None:
            msvcrt.locking(one, msvcrt.LK_NBLCK, 1)
        found = go_load(base)
        after = os.stat(lock).st_ino
        entries = own_entries(lock)
        by_the_app = go_second_lock(base)
        print("  the second lock asked by:", by_the_app.get("by"))
        second = by_the_app.get("a second exclusive lock")
    finally:
        if one is not None:
            try:
                os.lseek(one, 0, os.SEEK_SET)
                msvcrt.locking(one, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
            os.close(one)
    seen = {"first": first, "launch": found, "file id before": before, "after": after, "own entries": entries,
            "a second exclusive lock": second, "asked by": by_the_app.get("by"), "its run": by_the_app}
    expect("19: a wide lock file held across a launch: the same file, its list narrowed in place, a second"
           " exclusive lock refused while the first is held",
           accepted(first) and one is not None and after == before and entries == [] and second == "refused", seen)


def whole_path_scenes(token, user, user_token, go, scene_base):
    """(20)-(23): every folder on the way to the data folder judged, the
    folder held while the app runs, a link at a store's name never followed,
    and a folder whose list cannot be closed refused. Each scene runs on its
    own: one that fails in its own setup is said so, and the next still runs."""
    for scene in (store_link_scene, through_shared_scene, held_scene, list_not_closed_scene):
        try:
            scene(token, user, user_token, go, scene_base)
        except Exception:
            print(traceback.format_exc()[-3000:])
            expect(f"{scene.__doc__.split(':')[0]}: the scene ran to its end", False, {"crashed": scene.__name__})


def store_link_scene(token, user, user_token, go, scene_base):
    """(20): a link at a store's name."""
    old = json.dumps({"Old": REC}, indent=2).encode()

    # (20) A link of the user's at the store's name, and at the preferences',
    # to a file of the user's in a folder closed to every other account (and
    # once more through a junction on the way to it): never followed -- not
    # read, nothing written through it -- and the page told.
    for name, kind in (("saved_charts.json", "link"), ("preferences.json", "link"),
                       ("saved_charts.json", "junction")):
        tag = f"{name.split('.')[0]}-{kind}"
        base, zij, _legacy = scene_base(f"20-store-link-{tag}")
        os.mkdir(zij)
        give(zij, user)
        private = SCENES / f"20-private-{tag}"
        private.mkdir()
        give(private, user)
        closed_to(private, user)
        target = private / "kept.json"
        data = old if name == "saved_charts.json" else json.dumps({"last_chart": "Old"}).encode()
        print("  the user's file:", made_as(user_token, user, target, data))
        way = target
        if kind == "junction":
            junction = SCENES / f"20-junction-{tag}"
            run("cmd", "/c", "mklink", "/J", str(junction), str(private))
            give(junction, user, link=True)
            way = junction / "kept.json"
        print("  the user's link:", made_as(user_token, user, zij / name, link_to=way))
        found = go(base)
        after = bytes_of(target)
        seen = {"launch": found, "the file unchanged": after == data, "the link kept": os.path.islink(zij / name)}
        if name == "saved_charts.json":
            ok = found.get("loaded") == [] and found.get("saved") is False
        else:
            ok = found.get("preference written") is False
        expect(f"20: the user's own {kind} at {name}, to a file of the user's in a closed folder: not read,"
               " nothing written through it, the page told",
               ok and found.get("state") == [None, None] and after == data and os.path.islink(zij / name)
               and (found.get("set aside") or {}).get("unfollowed") is True, seen)


def through_shared_scene(token, user, user_token, go, scene_base):
    """(21): the data folder reached through a folder another account may change."""
    # (21) The data folder's name a junction of the user's, to a folder of the
    # user's closed to others but inside a folder the other account may
    # change: refused with the folder sentence, nothing read, nothing written.
    base, zij, _legacy = scene_base("21-through-shared")
    shared = SCENES / "21-shared"
    shared.mkdir()
    icacls(shared, "/grant", f"{OTHER}:(OI)(CI)M")
    private = shared / "private"
    private.mkdir()
    give(private, user)
    closed_to(private, user)
    planted = store(private, "Old")
    give(planted, user)
    before, names_before = planted.read_bytes(), sorted(os.listdir(private))
    run("cmd", "/c", "mklink", "/J", str(zij), str(private))
    give(zij, user, link=True)
    icacls(shared)
    found = go(base)
    seen = {"launch": found, "names after": sorted(os.listdir(private))}
    expect("21: the data folder's name a junction through a folder the other account may change: refused,"
           " nothing read, nothing written",
           refused(found, "path open") and planted.read_bytes() == before
           and sorted(os.listdir(private)) == names_before, seen)


def held_scene(token, user, user_token, go, scene_base):
    """(22): the data folder held while the app runs."""
    # (22) The folder held: a launch on a closed path holds its data folder
    # while the app runs. Neither the other account nor the user's own may
    # rename the data folder or the folder above it while it is held; were
    # the folder above renamed and another folder of the user's put in its
    # place, the save made after must land in the folder held and leave the
    # other folder's store as it was. The other account's renames are
    # refused by the scene folder's own list as well, held or not, so they
    # show nothing of the hold; the job's own renames, which the hold alone
    # refuses, carry the scene.
    base, _zij, _legacy = fresh("22-held")
    above = base / "above"
    above.mkdir()
    zij = above / "Zij"
    env = dict(os.environ, APPDATA=str(above))
    holder = subprocess.Popen([sys.executable, "-c", HOLD, json.dumps(REC)], cwd=ROOT, env=env, text=True,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    seen, victim, moved = {}, None, None

    def said():
        """The holder's next line, as a mapping; what it was where it is none."""
        line = holder.stdout.readline()
        try:
            return json.loads(line or "{}")
        except ValueError:
            return {"not a line of its own": line[-500:]}

    try:
        seen["launch"] = said()
        seen["the other account renames the data folder"] = renamed_as(token, zij)
        seen["the other account renames the folder above it"] = renamed_as(token, above)
        seen["the user renames the data folder"] = rename_refused(zij)
        try:
            os.rename(above, base / "above-aside")
            moved = base / "above-aside"
            seen["the user renames the folder above it"] = None
        except OSError as exc:
            seen["the user renames the folder above it"] = exc.winerror or exc.errno
        if moved is not None:
            victim = store(above / "Zij", "Victim")
        try:
            holder.stdin.write("go\n")
            holder.stdin.flush()
        except OSError as exc:          # the holder ended before it was told to save
            seen["told to save"] = repr(exc)
        seen["save"] = said()
    finally:
        try:
            holder.stdin.close()
        except OSError:
            pass
        try:
            holder.wait(timeout=120)
        except subprocess.TimeoutExpired:
            holder.kill()
            holder.wait()
        seen["its errors"] = holder.stderr.read()[-2000:]
    held = (moved or above) / "Zij" / "saved_charts.json"
    try:
        seen["the held folder's store"] = sorted(json.loads(held.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        seen["the held folder's store"] = repr(exc)
    if victim is not None:
        try:
            seen["the other folder's store"] = sorted(json.loads(victim.read_text(encoding="utf-8")))
        except (OSError, ValueError) as exc:
            seen["the other folder's store"] = repr(exc)
    kept_in_place = (seen["the user renames the data folder"] is not None
                     and seen["the user renames the folder above it"] is not None)
    expect("22: the data folder held while the app runs: no rename of it or of the folder above it by the"
           " job's own account, or the save kept in the folder held and the other folder's store unchanged"
           " (the other account's renames are refused by the scene folder's list too, held or not, and show"
           " nothing of the hold)",
           (seen.get("launch") or {}).get("state") == [None, None]
           and seen["the other account renames the data folder"] is not None
           and seen["the other account renames the folder above it"] is not None
           and (seen.get("save") or {}).get("saved") is True and seen["the held folder's store"] == ["Held"]
           and (kept_in_place or seen.get("the other folder's store") == ["Victim"]), seen)


def list_not_closed_scene(token, user, user_token, go, scene_base):
    """(23): a data folder whose list cannot be closed."""
    old = json.dumps({"Old": REC}, indent=2).encode()
    injected = json.dumps({"Injected": REC}, indent=2).encode()

    # (23) A data folder whose list the launch cannot close: Administrators'
    # folder giving the user and the other account Modify, which a launch that
    # is not elevated may not change. Refused with the folder sentence; and a
    # file of the user's the other account holds a hard link to, renamed back
    # to the store's name through that folder after any launch, is not read.
    if user == USER:
        print("[not run] 23: a folder whose list cannot be closed needs a launch that is not elevated;"
              " the suite's stand-in stands for it")
        return
    base, zij, _legacy = scene_base("23-list-not-closed")
    zij.mkdir()
    give(zij, f"*{ADMINISTRATORS}")
    icacls(zij, "/inheritance:r", "/grant:r", f"*{SYSTEM}:(OI)(CI)F", f"*{ADMINISTRATORS}:(OI)(CI)F",
           f"{user}:(OI)(CI)M", f"{OTHER}:(OI)(CI)M")
    kept = zij / "saved_charts.json"
    print("  the user's store:", made_as(user_token, user, kept, old))
    print("  the other account's hard link to it:", linked_as(token, kept, zij / "held.json"))
    first = go(base)
    aside = sorted(n for n in os.listdir(zij) if n.startswith("saved_charts.json.set-aside-"))
    print("  written through the hard link:", written_as(token, zij / "held.json", injected))
    if aside:
        print("  the file set aside renamed back:", moved_as(token, zij / aside[0], kept))
    second = go(base)
    seen = {"first": first, "set aside": aside, "second": second}
    expect("23: a data folder whose list cannot be closed: refused, and a file renamed back through it not read",
           refused(first, "not closed") and refused(second, "not closed") and second.get("loaded") == [], seen)


def main():
    print("Python", sys.version.split()[0], "| user", USER, "| this account", sid_of(USER))
    print("The system drive's own list, which a folder made under it inherits:")
    icacls(Path(os.environ.get("SystemDrive", "C:") + "\\"))
    alphabet = string.ascii_letters + string.digits
    password = ("Aa1!" + "".join(secrets.choice(alphabet) for _ in range(10)))
    # Not through run(): the password is never printed, whatever run() prints.
    made = subprocess.run(["net", "user", OTHER, password, "/add"], capture_output=True, text=True, timeout=300)
    print("  $ net user", OTHER, "(a generated password) /add ->", made.returncode)
    if made.returncode:
        raise SystemExit("the second account could not be made")
    print("The other account:", OTHER, sid_of(OTHER))
    SCENES.mkdir(exist_ok=True)
    give(SCENES, f"*{ADMINISTRATORS}")
    icacls(SCENES, "/inheritance:r", "/grant:r", f"*{SYSTEM}:(OI)(CI)F", f"*{ADMINISTRATORS}:(OI)(CI)F",
           "*S-1-5-32-545:(OI)(CI)RX")
    print("The folders on the way to this account's own data folder, and to the scenes', their owners and lists:")
    appdata = Path(os.environ["APPDATA"])
    for folder in [*reversed(appdata.parents), appdata, SCENES]:
        print("  ", folder, owner_read(folder, follow=False))
        icacls(folder)
    # So that the other account may make a file link itself: Developer Mode
    # on, and the privilege given to it, before its logon.
    run("reg", "add", r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock", "/v",
        "AllowDevelopmentWithoutDevLicense", "/t", "REG_DWORD", "/d", "1", "/f", check=False)
    grant_right("SeCreateSymbolicLinkPrivilege", OTHER)
    token, kind = other_logon(password)
    print("  its logon:", {3: "network", 2: "interactive", 4: "batch"}.get(kind, f"refused ({kind})")
          if token else f"refused ({kind})")
    SCENES.mkdir(exist_ok=True)

    # (1) The user's Zij renamed aside before a launch, the other's in its place.
    base, zij, _legacy = fresh("1-renamed-aside")
    store(zij, "Mine")
    zij.rename(base / "Zij-aside")
    planted = store(zij, "Injected")
    give(zij, OTHER)
    icacls(zij, "/grant", f"{OTHER}:(OI)(CI)F", f"{USER}:(OI)(CI)M")
    icacls(zij)
    before = planted.read_bytes()
    found = launch(base)
    expect("1: another account's folder at Zij, no race: refused, its store unread, nothing written in it",
           refused(found) and planted.read_bytes() == before, found)

    # (2) A first launch after an upgrade: the other's folder made at Zij
    # beforehand, holding no store; the former folder the user's.
    base, zij, legacy = fresh("2-upgrade")
    store(legacy, "Old")
    zij.mkdir()
    give(zij, OTHER)
    icacls(zij, "/grant", f"{OTHER}:(OI)(CI)F", f"{USER}:(OI)(CI)M")
    found = launch(base)
    expect("2: at an upgrade, another account's empty folder at Zij: refused, the former charts not copied in",
           refused(found) and not (zij / "saved_charts.json").exists()
           and json.loads((legacy / "saved_charts.json").read_text()) == {"Old": REC}, found)

    # (3) A base that passes Modify down, as the system drive does.
    base, zij, _legacy = fresh("3-passed-down")
    icacls(base, "/grant", "*S-1-5-11:(OI)(CI)M")       # every folder below it open to every account
    icacls(base)
    found = launch(base)
    icacls(zij)
    icacls(zij / "saved_charts.json")
    reach = as_other(token, zij / "saved_charts.json") if token else "no logon"
    print("  the other account on the new store:", reach)
    expect("3a: the data folder under a base that passes Modify down: refused, a folder on the way open to"
           " other accounts, nothing written", refused(found, "path open")
           and not (zij / "saved_charts.json").exists() and isinstance(reach, dict)
           and not any(v == "allowed" for v in reach.values()), found)
    base, zij, _legacy = fresh("3-made-before")
    os.mkdir(zij)                   # as an older version made it, under a base that passed Modify down
    icacls(zij, "/grant", "*S-1-5-11:(OI)(CI)M")
    store(zij, "Old")
    outside = SCENES / "3-outside"
    (outside / "kept").mkdir(parents=True)
    run("cmd", "/c", "mklink", "/J", str(zij / "junction"), str(outside))
    give(zij / "junction", OTHER, link=True)
    icacls(zij)
    print("  a folder outside, which a junction the other account made in the data folder leads to:")
    icacls(outside / "kept")
    reach_before = as_other(token, zij / "saved_charts.json") if token else "no logon"
    print("  the other account on the store, before the launch:", reach_before)
    found = launch(base)
    icacls(zij)
    icacls(zij / "saved_charts.json")
    reach = as_other(token, zij / "saved_charts.json") if token else "no logon"
    print("  the other account on the store, after the launch:", reach)
    print("  the folder outside, after the launch:")
    icacls(outside / "kept")
    expect("3b: a data folder of the user's open to others, found at a launch: accepted, then closed to them",
           accepted(found, "Old") and isinstance(reach, dict)
           and not any(v == "allowed" for v in reach.values()), found)

    # (4) An Administrators-owned data folder, and one owned by the user by name.
    for name, owner in (("4-administrators", f"*{ADMINISTRATORS}"), ("4-the-user", USER)):
        base, zij, _legacy = fresh(name)
        store(zij, "Old")
        give(zij, owner)
        found = launch(base)
        print("  owner read back:", owner_read(zij))
        expect(f"4: a data folder owned by {owner}: accepted", accepted(found, "Old"), found)

    # (5) The former folder owned by the other account.
    base, zij, legacy = fresh("5-former-theirs")
    store(legacy, "Injected")
    give(legacy, OTHER)
    icacls(legacy, "/grant", f"{OTHER}:(OI)(CI)F", f"{USER}:(OI)(CI)M")
    found = launch(base)
    expect("5: another account's former folder: refused, no data folder made, nothing copied",
           found.get("state") == ["made", found.get("former not ours")] and not os.path.lexists(zij)
           and sorted(p.name for p in base.iterdir()) == ["TraditionalAstrologyEngine"], found)

    # (6) A link or junction at Zij: the other account's refused, the user's accepted.
    for name, kind, owner, ok in (("6-junction-theirs", "/J", OTHER, False), ("6-link-theirs", "/D", OTHER, False),
                                  ("6-junction-mine", "/J", USER, True)):
        base, zij, _legacy = fresh(name)
        mine = SCENES / (name + "-target")
        planted = store(mine, "Old")
        icacls(mine, "/grant", "*S-1-5-11:(OI)(CI)M")      # the list a drive's root passes down
        before = planted.read_bytes()
        run("cmd", "/c", "mklink", kind, str(zij), str(mine))
        give(zij, owner, link=True)
        print("  the link's own owner, read back:", owner_read(zij, follow=False),
              "| the folder it leads to:", owner_read(zij))
        found = launch(base)
        if ok:
            # The folder the junction leads to takes the system drive's list
            # (Modify for every account that can log on): the launch closes
            # it, not the junction's own list alone, so the store in it, and
            # the save the launch made, are read back.
            print("  after the launch, the folder the junction leads to:")
            icacls(mine)
            print("  the store in it:")
            icacls(planted)
            closed = closed_list(mine)
            again = launch(base, LOAD)
            seen = {"launch": found, "the folder's list closed": closed, "the next load": again}
            expect(f"6: a {'junction' if kind == '/J' else 'link'} at Zij made by the user: accepted, the folder it"
                   " leads to closed, the save kept and read back",
                   accepted(found, "Old") and closed and found.get("lists left open") == {}
                   and again.get("loaded") == ["Mine", "Old"], seen)
        else:
            expect(f"6: a {'junction' if kind == '/J' else 'link'} at Zij made by the other account: refused",
                   refused(found) and planted.read_bytes() == before, found)

    # (7) A volume with no access lists.
    letter = next((c for c in "ZYXWVUTSRQ" if not os.path.exists(f"{c}:\\")), None)
    vhd = SCENES / "fat.vhd"
    steps = SCENES / "fat.txt"
    steps.write_text(f'create vdisk file="{vhd}" maximum=64 type=expandable\nselect vdisk file="{vhd}"\n'
                     f"attach vdisk\nconvert mbr\ncreate partition primary\nformat fs=fat32 quick label=ZFAT\n"
                     f"assign letter={letter}\n")
    done = run("diskpart", "/s", str(steps), check=False)
    if letter and done.returncode == 0 and os.path.exists(f"{letter}:\\"):
        base = Path(f"{letter}:\\base")
        base.mkdir()
        print("  the owner read on that volume:", owner_read(base))
        found = launch(base)
        print("  the owner read of the data folder made there:", owner_read(base / "Zij"))
        expect("7: a data folder on a volume with no access lists: accepted, nothing said", accepted(found), found)
    else:
        print("[not run] 7: no volume without access lists could be made here (diskpart:", done.returncode, ")")

    # (8) An owner the user is denied the reading of.
    base, zij, _legacy = fresh("8-owner-denied")
    planted = store(zij, "Injected")
    give(zij, OTHER)
    icacls(zij, "/grant", f"{OTHER}:(OI)(CI)F", f"{USER}:(OI)(CI)M")
    icacls(zij, "/deny", f"{USER}:(RC)")
    icacls(zij)
    print("  the owner read:", owner_read(zij))
    before = planted.read_bytes()
    found = launch(base)
    expect("8: a data folder whose owner the user may not read: refused",
           refused(found) and planted.read_bytes() == before, found)

    # (9) Ordinary launches with the account's own APPDATA: an upgrade, then a launch after it.
    appdata = Path(os.environ["APPDATA"])
    zij, legacy = appdata / "Zij", appdata / "TraditionalAstrologyEngine"
    shutil.rmtree(zij, ignore_errors=True)
    store(legacy, "Old")
    print("  the account's own APPDATA, and the former folder made in it:")
    icacls(appdata)
    icacls(legacy)
    found = launch(None)
    icacls(zij)
    expect("9: an ordinary upgrade launch, the account's own APPDATA: the charts moved in and kept",
           accepted(found, "Old") and not legacy.exists(), found)
    found = launch(None)
    reach = as_other(token, zij / "saved_charts.json") if token else "no logon"
    print("  the other account on that store:", reach)
    expect("9: the launch after it: accepted", accepted(found, "Mine", "Old"), found)
    shutil.rmtree(zij, ignore_errors=True)
    found = launch(None)
    expect("9: an ordinary first launch: accepted", accepted(found), found)

    # (10) A data folder a run as administrator made on Python 3.13 or later,
    # as os.mkdir(path, 0o700) makes it under this token, then a launch (as
    # administrator here): its list given the account's own entry.
    base, zij, _legacy = fresh("10-made-as-administrator")
    os.mkdir(zij, 0o700)
    store(zij, "Old")
    me = sid_of(USER)
    owner = owner_read(zij)
    made = icacls(zij).stdout
    print("  the owner read, as made:", owner)
    # the account's own entry, by name or SID as icacls prints it, full control on the folder itself
    names_me = re.compile(r"(^|[\\\s])(" + re.escape(USER) + "|" + re.escape(me) + r"):(\((OI|CI|I)\))*\(F\)",
                          re.I | re.M)
    as_made = (owner.get("owner") == ADMINISTRATORS and "OWNER RIGHTS:" in made
               and not names_me.search(made))
    print("  as Python makes it under an administrator's token (Administrators; SYSTEM, Administrators,"
          " OWNER RIGHTS, no entry of the account's own):", as_made)
    found = launch(base)
    after = icacls(zij).stdout
    icacls(zij / "saved_charts.json")
    print("  the owner read, after the launch:", owner_read(zij))
    expect("10: a data folder a run as administrator made: accepted, its list then naming the account, full control",
           as_made and accepted(found, "Old") and bool(names_me.search(after)), found)

    stored_scenes(token, alphabet)

    print()
    print("Scenes not as they should be:", FAILED or "none")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
