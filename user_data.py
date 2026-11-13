# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""The data layer: where the app keeps what the reader saves. The per-user
data folder (made owner-only, the folder kept under the app's former name
moved in once), the saved charts' store and the preferences' file, each read
through one reader and written whole or not at all, and every file in the
folder read or written through only where it is this account's and no
other account could change it (one that could is set aside at the launch,
unread, and brought back only at the user's word), the recovery copies of
what cannot be read, the last versions of the store kept before each write
over it, the locks that let one window at a time write, the
temporary files a killed write left behind, and the stores older versions
kept elsewhere.

engine.py takes it whole, `from user_data import *` after the ephemeris and
the time zones, so every name here is the engine's too but the accessor
below and six: the names the code rebinds as it runs (DATA_DIR_ERROR,
LAST_STORE_ERROR, LAST_STORE_UNREADABLE, LAST_PREFERENCES_ERROR,
LAST_PREFERENCES_UNREADABLE, LAST_PREFERENCES_BUSY) are read here
(`user_data.LAST_STORE_ERROR`), never through the engine, which would hold
the values they had at its import.

What the preferences mean -- their keys, the renamed values and the values
each widget can hold -- is the engine's: a load asks the engine's
_loadable_preferences, when it is made, which entries it keeps
(_the_engine). Nothing else here reads the engine. Importing this module
finds the folder from the environment, makes it and names the paths under
it; no store or preferences file is read then.
"""
import errno
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import sys
import threading
import time as _clock
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path
# The saved charts' and the preferences' file locks:
# flock where the system has it, msvcrt's byte lock on Windows, and the
# thread lock alone where neither is to be had.
try:
    import fcntl
except ImportError:
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None


def _the_engine():
    """The engine, reached when called and never at import (the engine
    imports this module): the preferences' meaning is the engine's, and is
    looked up there at each call, so that the object the engine holds under
    the name then is the one used."""
    import engine
    return engine


# Charts are saved as {name: {date_string, time_string, location_query}} in a
# small JSON file. Only the raw natal inputs are stored -- the full chart is
# cheaply recomputed on load rather than serialized.
#
# This lives in the OS's per-user data directory, NOT next to app.py: a
# packaged build's own folder (_internal) gets replaced whole by every new
# download, which used to silently wipe saved charts on every update unless
# the file was manually copied out and back in first.
APP_DIR_NAME = "Zij"
# What the folder was called while the app was the Traditional Astrology
# Engine. A chart saved then is not left behind: the
# first run under the new name moves the whole folder across, once, and
# only when the new one does not exist yet.
_LEGACY_APP_DIR_NAME = "TraditionalAstrologyEngine"

def _user_data_path() -> Path:
    """Where the per-user folder is, whether or not it exists or can be made.

    An empty or relative APPDATA or
    XDG_DATA_HOME was taken as given, so the folder was made under whatever
    directory the app was launched from. Either counts as unset, as the XDG
    specification says of its own variable (_absolute_environment_folder)."""
    if sys.platform == "win32":
        base = _absolute_environment_folder("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = _absolute_environment_folder("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_DIR_NAME


def _absolute_environment_folder(name):
    """The environment's `name` where it names a folder by an absolute path;
    None where it is unset, empty or relative."""
    value = os.environ.get(name, "")
    return value if value and os.path.isabs(value) else None

def _user_data_dir() -> Path:
    """The per-user folder, made if need be; raises OSError when it cannot
    be made."""
    return _make_user_data_dir(_user_data_path())

class DataFolderRefused(PermissionError):
    """The data folder stands and
    belongs to another account. Nothing is read from it or written in it."""


# What the data folder's refusal gives as its reason, in the place of the
# system's words (data_folder_state).
DATA_FOLDER_NOT_OURS = "it belongs to another account"


class DataFolderOpenToOthers(DataFolderRefused):
    """A folder on the way to the data folder -- one its path passes
    through, the folder a link on it stands in, or one a link leads through
    -- is not this account's or the system's, or other accounts may write in
    it; or a link met on the way is not this account's or the system's
    (_held_by_its_whole_path). Another account could put another of the
    user's folders in the data folder's place, whose files the launch would
    read as the user's and the saves write over. Nothing is read from the
    data folder or written in it."""


# What that gives as its reason (data_folder_state).
DATA_FOLDER_PATH_OPEN = "other accounts could change a folder on the way to it"


class DataFolderNotClosed(DataFolderRefused):
    """The launch could not close the data folder to other accounts: the
    change of its mode was refused (POSIX), or its access list could not be
    closed (Windows). Nothing is read from it or written in it."""


# What that gives as its reason (data_folder_state).
DATA_FOLDER_NOT_CLOSED = "it could not be closed to other accounts"


class FormerFolderNotCopied(OSError):
    """The folder under the app's former name could not be moved in, and
    its copy could not be made, or made whole, or held something that is
    neither a regular file nor a folder: no data folder is made, and the
    move is tried again at the next launch (_copy_the_former_folder)."""


# What that gives as its reason (data_folder_state, which takes an error's
# own words where it has no system ones).
FORMER_FOLDER_NOT_COPIED = "the folder an older version kept them in could not be copied whole"


class FormerFolderRefused(PermissionError):
    """What stands under the app's former name belongs to another account
    -- when the launch first looks there, or at any step after: the folder
    it opened there, or what the name leads to at a later look -- and no
    data folder stands yet: it is neither moved nor copied, nothing is read
    from it, no data folder is made, and the next launch (or the next look
    at the folder, data_folder_state) asks again (_make_user_data_dir)."""


# What that gives as its reason (data_folder_state).
FORMER_FOLDER_NOT_OURS = "the folder an older version kept them in belongs to another account"


class FormerFolderNotCarried(OSError):
    """The folder under the app's former name is this account's, but holds
    an entry of another account's, or was open to other accounts' writes
    before it was narrowed and holds a link or something that is neither a
    regular file nor a folder: it is neither moved nor copied, no data
    folder is made, and the next launch asks again
    (_only_this_accounts_entries)."""


# What that gives as its reason (data_folder_state).
FORMER_FOLDER_NOT_CARRIED = ("the folder an older version kept them in was open to other accounts and holds "
                             "something that is not carried in")


class FormerFolderUnreadable(FormerFolderNotCarried):
    """The folder under the app's former name is this account's, but it,
    or a folder in it, cannot be listed by this account, so what it holds
    cannot be judged: it is neither moved nor copied, no data folder is
    made, and the next launch asks again (_only_this_accounts_entries).
    Whatever its mode, so that its reason does not say it was open to other
    accounts."""


# What that gives as its reason (data_folder_state).
FORMER_FOLDER_UNREADABLE = "the folder an older version kept them in, or a folder in it, cannot be read"


class FormerFolderBusy(OSError):
    """The folder under the app's former name is this account's, but its
    lock (_the_former_folder_held) was held elsewhere past the wait -- by
    another launch moving, copying or looking at it, or by another program
    -- and nothing in it is narrowed or looked at; or the name came to
    lead, at a step after the launch first looked, to another folder or
    link of this account's, or to nothing (_still_the_former_folder): it is
    neither moved nor copied by this launch, no data folder is made, and
    the next launch (or the next look at the folder, data_folder_state)
    asks again."""


# What that gives as its reason (data_folder_state).
FORMER_FOLDER_BUSY = "the folder an older version kept them in is in use elsewhere"

# How long a launch waits for the former folder's lock: as long as a save
# waits for the store's (LOCK_WAIT_SECONDS). A later look at the data
# folder (data_folder_state) asks once, without waiting.
_FORMER_FOLDER_LOCK_WAIT = 10.0


def _make_user_data_dir(path, lock_wait=None) -> Path:
    """Make the per-user folder `path` as a launch makes it -- the folder
    kept under the app's former name moved across first, once -- and return
    it; raises OSError when it cannot be made.

    The folder took its mode from the
    umask alone (0777 under umask 000), so other accounts could read the
    saved charts and plant files in it. A folder made here is made 0700 --
    asked of mkdir and set after it, since the umask cuts what mkdir is
    asked (0o300 under 0o444) and os.chmod is not cut -- and one of this
    account's that is wider is narrowed (_keep_the_data_folder_ours); one
    that belongs to another account is refused (DataFolderRefused). On
    Windows, where a mode says nothing of other accounts, the folder made
    here is given a protected access list (_windows_close_the_list): this
    account, SYSTEM and Administrators, full control, inherited by all that
    is made in it, nothing inherited from the folder above -- which, where
    APPDATA is a folder such as a drive's root, passes Modify down to every
    account that can log on. One that is wider is narrowed so at each
    launch (_keep_the_data_folder_ours), as is one of Administrators' or
    SYSTEM's that grants this account nothing, in a run as administrator.
    The narrowing reaches the folder, not what another account put in it
    while it was wider: each file the app reads or writes there is judged
    by its own owner (_whose), on every platform, and another account's is
    never read, copied or written through. Nor did it reach a file of the
    user's own that another account could still change: one an older
    version left writable by its group or others (0666 under umask 000),
    which kept that mode, or on Windows one whose own access list gives
    another account a right to write, which a folder's closed list does not
    take away; that account could write it through a descriptor or a hard
    link it held, and the load read what it wrote as the user's, and said
    nothing. Each such file the app reads there is now set aside at each
    launch, unread, under a recovery name, and the page offers to restore
    it (_set_aside_what_others_could_write); a lock file others could
    write is narrowed in place.

    A folder of this account's under the former name is never published at
    `path` wider than its owner's: it is narrowed before it is moved (a link
    at its name followed, as at `path`), and a copy of it is narrowed before
    it takes the name (_copy_the_former_folder). The files in it keep their
    own modes where it is moved, and the owner's part of them where it is
    copied. One the app reads that others could write is set aside where it
    is moved (_set_aside_what_others_could_write), and keeps the copy from
    being made where it is copied (_copy_a_file), as a file past the bounds
    one launch copies does. A narrowing the filesystem refuses is
    passed over, as
    _keep_the_data_folder_ours passes it over, and nothing is said: the
    move or the copy goes ahead, and the folder stands as that filesystem
    keeps it.

    The folders above `path` that are missing are made 0700 too, as the XDG
    base directory specification asks of a missing destination; folders
    already there are left as they are.

    A folder under the former name that belongs to another account (where
    the folder above `path` is one other accounts may write in, as a shared
    one may be) was copied when its move was refused, and the copy published
    as this account's data folder, holding whatever that account had put in
    it. It is now neither moved nor copied, and nothing is read from it:
    FormerFolderRefused is raised, no folder is made at `path`, and the next
    launch asks again. That holds at every step, not at the first look
    alone: where another account owns the folder above, it may put a folder
    of its own at the former name at any moment, so what stands there is
    identified once and every later step is tied to it -- the folder opened
    without following a link, its owner read from what was opened, the lock
    and the look taken on it, the name looked at again before the move,
    after a refused move and before a copy is published, and the copy read
    through the folder opened, never its name (_move_the_former_folder).
    Another account's at any of those steps is refused so; another folder
    or link of this account's there, or nothing, is FormerFolderBusy.

    On Windows the former folder and the data folder were judged by their
    names alone, no owner read: a folder another account put at either name
    (where APPDATA is a folder it may write in) was moved in, copied into or
    used as the data folder, its store read as the user's and the saves
    written into it. Their owners are now read through the system's
    security calls (_owner_of), and only this account, Administrators and
    SYSTEM are taken for this account's (_ours); an owner the system refuses
    this account the reading of is another's. The former folder is judged
    before it is moved (_former_folder_not_this_accounts), what the move put
    at `path` after it, and the former folder again before a copy of it is
    published: another account's is FormerFolderRefused, and no data folder
    is made. Python holds no descriptor of a folder on Windows, so each step
    still goes by the name: an account that may rename or delete in the
    folder above can put a folder of its own at either name between a look
    and the step after it, and only the next look refuses it.

    A former folder of this account's that other accounts could write in,
    now or once, may hold what they put there: a link, which the move
    carried into the data folder and the saves then followed out of it.
    Every former folder of this account's, whatever its mode, is moved (or
    copied) only where every entry in it, at every depth, is this
    account's, judged without following a link; one that was writable by
    its group or by others when this launch found it must hold nothing but
    regular files and folders besides (_only_this_accounts_entries). Else
    FormerFolderNotCarried is raised (FormerFolderUnreadable where it or a
    folder in it cannot be listed), the folder stays where it is, each
    folder in it given back the mode it had, and no data folder is made:
    each launch asks again. The mode alone cannot say whether others put
    something there: a launch narrows the folder before it looks, so a
    second launch during that look, the one after a launch killed in it,
    or an owner who has since closed the folder would find it owner-only.
    A former folder of this account's entries alone that was not open to
    others is moved as before, links and all: those are the account's own.
    On Windows, where modes say nothing of other accounts, no such look is
    made: the former folder is judged by its own owner, and given the data
    folder's protected access list before it is moved where its list gives
    anyone else anything (_narrow_to_its_owner). What another account put in
    it is moved in with it, its owner kept, and is never read or written
    through in the data folder (_whose). A copy keeps no owner, so the copy
    made where the move is refused makes that look first, by name, and raises
    FormerFolderNotCarried as well (_copy_the_former_folder_by_name).

    One launch at a time reads a former folder's mode, looks at it and
    moves, copies or refuses it: each holds the folder's lock from before
    the first until after the last (_the_former_folder_held), waiting
    `lock_wait` seconds for it (_FORMER_FOLDER_LOCK_WAIT when not given;
    data_folder_state does not wait). A launch that cannot have it raises
    FormerFolderBusy, and no data folder is made."""
    legacy = path.parent / _LEGACY_APP_DIR_NAME
    _remove_dead_copies(path, legacy)
    if not path.exists() and legacy.is_dir():
        _judge_the_former_folders_path(legacy)
        if lock_wait is None:
            lock_wait = _FORMER_FOLDER_LOCK_WAIT
        if hasattr(os, "getuid"):
            _move_the_former_folder(legacy, path, lock_wait)
        else:
            # Windows: no descriptor of a folder and no flock. The folder is
            # judged by its owner, narrowed, then moved, or copied by name
            # where the move is refused; what the move put at `path` is
            # judged again.
            if _former_folder_not_this_accounts(legacy):
                raise FormerFolderRefused(errno.EPERM, FORMER_FOLDER_NOT_OURS, str(legacy))
            _narrow_to_its_owner(legacy)
            try:
                legacy.rename(path)
            except OSError:
                _copy_the_former_folder_by_name(legacy, path)
            else:
                if _not_this_accounts(path):
                    raise FormerFolderRefused(errno.EPERM, FORMER_FOLDER_NOT_OURS, str(path))
    _make_missing_folders(path.parent)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        if not path.is_dir():
            raise
    else:
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass                        # a filesystem that keeps no modes
        if not hasattr(os, "getuid"):
            try:
                _windows_close_the_list(path)
            except OSError:
                pass                    # a volume that keeps no lists
    _MODELESS.clear()
    try:
        held = _keep_the_data_folder_ours(path)
    except DataFolderRefused as exc:
        _REFUSED[os.fspath(path)] = exc.strerror or DATA_FOLDER_NOT_OURS
        raise
    _REFUSED.pop(os.fspath(path), None)
    posix = hasattr(os, "getuid")
    try:
        _note_whether_it_keeps_modes(path, held if posix else None)
    finally:
        _hold_for_the_launch(held, path, posix)
    try:
        _set_aside_what_others_could_write(path)
    except OSError:
        pass        # a folder that cannot be listed: nothing is read from it (_folder_not_to_be_used)
    return path


def _make_missing_folders(folder):
    """Make `folder` and each folder above it that is missing, from the top
    down, each 0700 -- asked of mkdir and set after it, as the data folder
    is -- and leave every folder already there as it is. One another launch
    makes in the meantime is left as that launch made it."""
    missing = []
    while not os.path.lexists(folder) and folder.parent != folder:
        missing.append(folder)
        folder = folder.parent
    for each in reversed(missing):
        try:
            os.mkdir(each, 0o700)
        except FileExistsError:
            continue
        try:
            os.chmod(each, 0o700)
        except OSError:
            pass                        # a filesystem that keeps no modes


def _not_this_accounts(folder):
    """Whether `folder` stands and belongs to another account, judged at the
    name and then at what it leads to: a link there (on Windows a link or a
    junction) by its own owner, not followed, and then the folder it names.
    True as well where Windows refuses this account the reading of either
    owner (_OwnerDenied: the owner of a folder may set its list so). False
    where `folder` cannot be looked at (that is the folder's own case,
    data_folder_state's), and where its volume keeps no owners (_ours).

    A link at the name was followed whoever made it: the owner of the folder
    above could rename the user's folder aside and put a link of its own
    there, to a folder of the user's or to one it could later point
    elsewhere, and the app used it. Another account's link is now refused,
    with the folder; a link of this account's is followed as before, and
    the folder it leads to judged."""
    try:
        return not (_ours(_owner_of_the_name(folder)) and _ours(_owner_of(folder)))
    except _OwnerDenied:
        return True
    except (OSError, ValueError):
        return False


def _owner_of(folder):
    """The account `folder` belongs to, a link followed: its id; on
    Windows its SID, as text (_windows_owner)."""
    if not hasattr(os, "getuid"):
        return _windows_owner(folder, follow_links=True)
    return _stat(folder).st_uid


def _owner_of_the_name(path):
    """The account the name `path` itself belongs to, a link there not
    followed: the link's own owner (on Windows, a link's or a junction's,
    opened itself)."""
    if not hasattr(os, "getuid"):
        return _windows_owner(path, follow_links=False)
    return _lstat(path).st_uid


def _ours(owner):
    """Whether an owner _owner_of or _owner_of_the_name read is taken for
    this account's: this account's id; on Windows this account's SID, read
    from the process's token, Administrators' or SYSTEM's -- those two can
    do anything already, and a folder made by a run as administrator belongs
    to Administrators (its list repaired by such a run, _narrow_to_its_owner)
    -- or none, on a volume that keeps no owners (FAT,
    exFAT), which is left as it is, as a filesystem that keeps no modes is.
    The system's own choice of a Windows branch is no getuid, as everywhere
    in this module."""
    if hasattr(os, "getuid"):
        return owner == os.getuid()
    return owner is None or owner in (_windows_this_account(), _ADMINISTRATORS_SID, _SYSTEM_SID)


def _owner_of_the_open(fd):
    """The account the file open at the descriptor `fd` belongs to, read
    from what was opened, not from its name: its id (os.fstat); on Windows
    its SID, through the file's own handle (_windows_owner_of_the_open)."""
    if not hasattr(os, "getuid"):
        return _windows_owner_of_the_open(fd)
    return os.fstat(fd).st_uid


class _NotThisAccounts(PermissionError):
    """A file in the data folder that is another account's -- at its name,
    at the file a link of this account's there leads to, or as opened -- and
    is not read, copied, followed or written through."""


# What stands at a name in the data folder, judged by its owner (_whose).
_NOTHING = "nothing"
_OURS = "ours"
_OUR_LINK = "our link"
_ANOTHERS = "another's"
_LEADS_TO_ANOTHERS = "leads to another's"


def _whose(path):
    """Whose what stands at the name `path` in the data folder is: _NOTHING
    where nothing stands there, or the name cannot be looked at; _ANOTHERS
    where the name itself belongs to another account -- a file, a link or
    anything else, judged at the name, a link not followed; _OUR_LINK for a
    link of this account's to a file of this account's, or to nothing;
    _LEADS_TO_ANOTHERS for a link of this account's to another account's
    file; else _OURS. An owner Windows refuses this account the reading of
    is another's; one that cannot be read for any other reason is not, as
    the data folder's is not (_not_this_accounts).

    The files in the data folder were taken for this account's because the
    folder was: where an older version left the folder open to others,
    another account's store put in it was loaded as the user's, and its link
    at the store's name was followed by every load and every save after, the
    user's records written into that account's file. Each file is now judged
    by its own owner, and only this account's is read or written through."""
    try:
        if not _ours(_owner_of_the_name(path)):
            return _ANOTHERS
    except _OwnerDenied:
        return _ANOTHERS
    except FileNotFoundError:
        return _NOTHING
    except (OSError, ValueError):
        pass
    if not _islink(path):
        return _NOTHING if not _lexists(path) else _OURS
    try:
        return _OUR_LINK if _ours(_owner_of(path)) else _LEADS_TO_ANOTHERS
    except _OwnerDenied:
        return _LEADS_TO_ANOTHERS
    except (OSError, ValueError):
        return _OUR_LINK                # it leads nowhere, or not to be looked at: its own


def _opened_is_ours(fd):
    """Whether the file open at `fd` is this account's, judged by what was
    opened (_owner_of_the_open); another's where Windows refuses this account
    the reading of its owner, and not where it cannot be read for any other
    reason, as at the name (_whose)."""
    try:
        return _ours(_owner_of_the_open(fd))
    except _OwnerDenied:
        return False
    except (OSError, ValueError):
        return True


# Windows: whose a file or folder is, and its access list, read and set
# through the system's security calls. ctypes and the two libraries are
# loaded at the first call, never at import. Each function below is the one
# place its call is made, so that the suite can stand each in on POSIX.
_ADMINISTRATORS_SID = "S-1-5-32-544"
_SYSTEM_SID = "S-1-5-18"
# CREATOR OWNER and OWNER RIGHTS: entries that give a file's owner, never
# another account, what they name.
_OWNER_ENTRY_SIDS = ("S-1-3-0", "S-1-3-4")
_WINDOWS_CALLS = {}
_WINDOWS_ACCOUNT = []


class _OwnerDenied(PermissionError):
    """Windows refused this account the reading of an owner: the owner of
    a file or folder may set its list to deny that while granting the rest."""


def _windows_calls():
    """The kernel32 and advapi32 calls the functions below make, typed."""
    if not _WINDOWS_CALLS:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        p, out, dword, flag = ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), wintypes.DWORD, wintypes.BOOL

        def typed(call, result, *args):
            call.restype, call.argtypes = result, list(args)
            return call
        _WINDOWS_CALLS.update(
            ctypes=ctypes, wintypes=wintypes, invalid=ctypes.c_void_p(-1).value,
            CreateFileW=typed(kernel32.CreateFileW, p, wintypes.LPCWSTR, dword, dword, p, dword, dword, p),
            CloseHandle=typed(kernel32.CloseHandle, flag, p),
            LocalFree=typed(kernel32.LocalFree, p, p),
            GetCurrentProcess=typed(kernel32.GetCurrentProcess, p),
            GetVolumeInformationByHandleW=typed(kernel32.GetVolumeInformationByHandleW, flag, p, p, dword, p, p,
                                                ctypes.POINTER(dword), p, dword),
            GetSecurityInfo=typed(advapi32.GetSecurityInfo, dword, p, ctypes.c_int, dword, out, out, out, out, out),
            ConvertSidToStringSidW=typed(advapi32.ConvertSidToStringSidW, flag, p, out),
            OpenProcessToken=typed(advapi32.OpenProcessToken, flag, p, dword, out),
            GetTokenInformation=typed(advapi32.GetTokenInformation, flag, p, ctypes.c_int, p, dword,
                                      ctypes.POINTER(dword)),
            ConvertStringSecurityDescriptorToSecurityDescriptorW=typed(
                advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW, flag, wintypes.LPCWSTR, dword, out, p),
            GetSecurityDescriptorDacl=typed(advapi32.GetSecurityDescriptorDacl, flag, p, ctypes.POINTER(flag), out,
                                            ctypes.POINTER(flag)),
            SetNamedSecurityInfoW=typed(advapi32.SetNamedSecurityInfoW, dword, wintypes.LPCWSTR, ctypes.c_int, dword,
                                        p, p, p, p),
            GetAce=typed(advapi32.GetAce, flag, p, dword, out),
        )
    return _WINDOWS_CALLS


def _windows_failed(win, code=None):
    """The OSError for a failed call: its own code, or the last error."""
    return win["ctypes"].WinError(win["ctypes"].get_last_error() if code is None else code)


def _windows_sid_text(win, sid):
    """The SID at the address `sid`, as text, as Windows writes it."""
    text = win["ctypes"].c_void_p()
    if not win["ConvertSidToStringSidW"](sid, win["ctypes"].byref(text)):
        raise _windows_failed(win)
    try:
        return win["ctypes"].wstring_at(text.value)
    finally:
        win["LocalFree"](text)


def _windows_opened(win, path, follow_links):
    """A handle of `path`, a folder or a file, open to read its security
    and attributes (a link or junction there opened itself unless
    `follow_links`). _OwnerDenied where the system refuses it that."""
    flags = 0x02000000 | (0 if follow_links else 0x00200000)   # backup semantics; the reparse point itself
    handle = win["CreateFileW"](str(path), 0x00020000 | 0x0080, 0x7, None, 3, flags, None)
    if handle is None or handle == win["invalid"]:
        code = win["ctypes"].get_last_error()
        if code == 5:                                           # ERROR_ACCESS_DENIED
            raise _OwnerDenied(errno.EACCES, os.strerror(errno.EACCES), str(path))
        raise _windows_failed(win, code)
    return handle


def _windows_keeps_lists(win, handle):
    """Whether the volume the handle is on keeps access lists, owners
    with them (FILE_PERSISTENT_ACLS): FAT and exFAT keep none, and the
    system then answers any reading of an owner with an invented one."""
    flags = win["wintypes"].DWORD(0)
    if not win["GetVolumeInformationByHandleW"](handle, None, 0, None, None, win["ctypes"].byref(flags), None, 0):
        raise _windows_failed(win)
    return bool(flags.value & 0x8)


def _windows_owner(path, follow_links=True):
    """The owner of `path` as Windows reads it: its SID's text; None on a
    volume that keeps no access lists; "" for a security descriptor that
    names no owner. Raises _OwnerDenied where the system refuses this
    account the reading of it, OSError where nothing can be looked at."""
    win = _windows_calls()
    handle = _windows_opened(win, path, follow_links)
    try:
        return _windows_owner_through(win, handle, path)
    finally:
        win["CloseHandle"](handle)


def _windows_owner_of_the_open(fd):
    """The owner of the file open at the descriptor `fd`, read through that
    file's own handle (msvcrt's), so of what was opened, whatever its name
    leads to now: as _windows_owner reads it. A descriptor open for reading
    or for writing holds the right to read its owner."""
    win = _windows_calls()
    return _windows_owner_through(win, msvcrt.get_osfhandle(fd), f"descriptor {fd}")


def _windows_owner_through(win, handle, name):
    """The owner of what `handle` is open on, as _windows_owner reads it;
    `name` is what an error names."""
    ctypes = win["ctypes"]
    if not _windows_keeps_lists(win, handle):
        return None
    owner, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
    code = win["GetSecurityInfo"](handle, 1, 0x1, ctypes.byref(owner), None, None, None, ctypes.byref(descriptor))
    if code == 5:
        raise _OwnerDenied(errno.EACCES, os.strerror(errno.EACCES), str(name))
    if code:
        raise _windows_failed(win, code)
    try:
        return _windows_sid_text(win, owner) if owner.value else ""
    finally:
        win["LocalFree"](descriptor)


def _windows_list_is_wider(path):
    """Whether the access list of the folder `path` (a link followed)
    gives anything to an account but this one, SYSTEM and Administrators:
    an allowance to any other SID, an allowance of a form not read here, or
    no list at all (everyone may do anything). Entries for a file's own
    owner (CREATOR OWNER, OWNER RIGHTS) and denials give no one else
    anything. False on a volume that keeps no lists."""
    win = _windows_calls()
    ctypes = win["ctypes"]
    handle = _windows_opened(win, path, True)
    try:
        if not _windows_keeps_lists(win, handle):
            return False
        dacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
        code = win["GetSecurityInfo"](handle, 1, 0x4, None, None, ctypes.byref(dacl), None, ctypes.byref(descriptor))
        if code:
            raise _windows_failed(win, code)
        try:
            if not dacl.value:
                return True
            kept = {_windows_this_account(), _ADMINISTRATORS_SID, _SYSTEM_SID, *_OWNER_ENTRY_SIDS}
            for index in range(ctypes.c_ushort.from_address(dacl.value + 4).value):    # the list's AceCount
                ace = ctypes.c_void_p()
                if not win["GetAce"](dacl, index, ctypes.byref(ace)):
                    raise _windows_failed(win)
                kind = ctypes.c_ubyte.from_address(ace.value).value
                if kind in (1, 6, 10, 12):                  # a denial, of any form
                    continue
                if kind != 0:                               # an allowance of another form
                    return True
                if (ctypes.c_uint32.from_address(ace.value + 4).value
                        and _windows_sid_text(win, ace.value + 8) not in kept):
                    return True
            return False
        finally:
            win["LocalFree"](descriptor)
    finally:
        win["CloseHandle"](handle)


def _windows_list_names_this_account(path):
    """Whether the access list of the folder `path` (a link followed) holds
    an allowance naming this account's own SID that applies to the folder
    itself: a group this account is in does not count, since a run that is
    not elevated holds Administrators for denials alone. True where there is
    no list at all (everyone may do anything) and on a volume that keeps no
    lists."""
    win = _windows_calls()
    ctypes = win["ctypes"]
    handle = _windows_opened(win, path, True)
    try:
        if not _windows_keeps_lists(win, handle):
            return True
        dacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
        code = win["GetSecurityInfo"](handle, 1, 0x4, None, None, ctypes.byref(dacl), None, ctypes.byref(descriptor))
        if code:
            raise _windows_failed(win, code)
        try:
            if not dacl.value:
                return True
            for index in range(ctypes.c_ushort.from_address(dacl.value + 4).value):    # the list's AceCount
                ace = ctypes.c_void_p()
                if not win["GetAce"](dacl, index, ctypes.byref(ace)):
                    raise _windows_failed(win)
                if (ctypes.c_ubyte.from_address(ace.value).value == 0                  # a plain allowance
                        and not ctypes.c_ubyte.from_address(ace.value + 1).value & 0x08  # not for what is in it alone
                        and ctypes.c_uint32.from_address(ace.value + 4).value
                        and _windows_sid_text(win, ace.value + 8) == _windows_this_account()):
                    return True
            return False
        finally:
            win["LocalFree"](descriptor)
    finally:
        win["CloseHandle"](handle)


def _windows_close_the_list(path):
    """Give the folder `path` (a link followed) the protected access list:
    this account, SYSTEM and Administrators, full control, inherited by every
    folder and file in it; none inherited from the folder above. The system
    carries the change to the entries everything in it inherited. OSError
    where it is refused."""
    win = _windows_calls()
    ctypes = win["ctypes"]
    text = f"D:P(A;OICI;FA;;;{_windows_this_account()})(A;OICI;FA;;;SY)(A;OICI;FA;;;BA)"
    descriptor = ctypes.c_void_p()
    if not win["ConvertStringSecurityDescriptorToSecurityDescriptorW"](text, 1, ctypes.byref(descriptor), None):
        raise _windows_failed(win)
    try:
        present, defaulted, dacl = win["wintypes"].BOOL(), win["wintypes"].BOOL(), ctypes.c_void_p()
        if not win["GetSecurityDescriptorDacl"](descriptor, ctypes.byref(present), ctypes.byref(dacl),
                                                ctypes.byref(defaulted)):
            raise _windows_failed(win)
        code = win["SetNamedSecurityInfoW"](str(path), 1, 0x4 | 0x80000000, None, None, dacl, None)
        if code:                                    # DACL and PROTECTED_DACL_SECURITY_INFORMATION
            raise _windows_failed(win, code)
    finally:
        win["LocalFree"](descriptor)


# The rights that let an account change a file: write and append to it,
# change its list or its owner, delete it (FILE_WRITE_DATA, FILE_APPEND_DATA,
# WRITE_DAC, WRITE_OWNER, DELETE), and the generic forms that hold them
# (GENERIC_WRITE, GENERIC_ALL). Reading it, or its attributes, is not one.
_WINDOWS_RIGHTS_TO_CHANGE = 0x2 | 0x4 | 0x40000 | 0x80000 | 0x10000 | 0x40000000 | 0x10000000


def _windows_file_is_writable_by_others(path, follow_links=False):
    """Whether the access list of the file `path` (itself, a link not
    followed unless `follow_links`: then the file it leads to) allows a right to change it (_WINDOWS_RIGHTS_TO_CHANGE) to an
    account but this one, SYSTEM and Administrators: an allowance of such a
    right to any other SID, an allowance of a form not read here, or no list
    at all (everyone may do anything). Entries for the file's own owner
    (CREATOR OWNER, OWNER RIGHTS), entries only for what a folder holds, and
    denials allow no one else anything; nor does an allowance to read.
    False on a volume that keeps no lists."""
    return _windows_entries_allow_others(path, follow_links, _WINDOWS_RIGHTS_TO_CHANGE)


def _windows_folder_is_open_to_others(path):
    """Whether the access list of the folder `path` (itself, a link or
    junction there not followed) allows an account but this one, SYSTEM and
    Administrators a right to rename or replace it or what is in it
    (_WINDOWS_RIGHTS_OVER_A_FOLDER), read as _windows_file_is_writable_by_others
    reads a file's; False on a volume that keeps no lists."""
    return _windows_entries_allow_others(path, False, _WINDOWS_RIGHTS_OVER_A_FOLDER)


def _windows_hold_the_folder(path):
    """A handle on the folder `path` (a link or junction there followed),
    open to list it and sharing reading and writing but not deleting, so
    that neither it nor a folder above it can be renamed or removed while it
    is held; as a descriptor (msvcrt's), which the launch holds for the life
    of the process (_hold_for_the_launch). OSError where it cannot be had."""
    win = _windows_calls()
    handle = win["CreateFileW"](str(path), 0x0001 | 0x0080, 0x1 | 0x2, None, 3, 0x02000000, None)
    if handle is None or handle == win["invalid"]:
        raise _windows_failed(win)
    return msvcrt.open_osfhandle(handle, os.O_RDONLY)


def _windows_entries_allow_others(path, follow_links, rights):
    """Whether the access list of `path` allows any of `rights` to an
    account but this one, SYSTEM and Administrators, as
    _windows_file_is_writable_by_others reads it."""
    win = _windows_calls()
    ctypes = win["ctypes"]
    handle = _windows_opened(win, path, follow_links)
    try:
        if not _windows_keeps_lists(win, handle):
            return False
        dacl, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
        code = win["GetSecurityInfo"](handle, 1, 0x4, None, None, ctypes.byref(dacl), None, ctypes.byref(descriptor))
        if code:
            raise _windows_failed(win, code)
        try:
            if not dacl.value:
                return True
            kept = {_windows_this_account(), _ADMINISTRATORS_SID, _SYSTEM_SID, *_OWNER_ENTRY_SIDS}
            for index in range(ctypes.c_ushort.from_address(dacl.value + 4).value):    # the list's AceCount
                ace = ctypes.c_void_p()
                if not win["GetAce"](dacl, index, ctypes.byref(ace)):
                    raise _windows_failed(win)
                kind = ctypes.c_ubyte.from_address(ace.value).value
                if ctypes.c_ubyte.from_address(ace.value + 1).value & 0x08:
                    continue                                # INHERIT_ONLY: for what a folder holds
                if kind in (1, 6, 10, 12):                  # a denial, of any form
                    continue
                if kind != 0:                               # an allowance of another form
                    return True
                if (ctypes.c_uint32.from_address(ace.value + 4).value & rights
                        and _windows_sid_text(win, ace.value + 8) not in kept):
                    return True
            return False
        finally:
            win["LocalFree"](descriptor)
    finally:
        win["CloseHandle"](handle)


def _windows_reset_the_list(path):
    """Take the file `path`'s own entries from its access list, so that it
    holds only what it inherits from its folder: the protected list, where
    the data folder has it (_windows_close_the_list). OSError where it is
    refused."""
    win = _windows_calls()
    ctypes = win["ctypes"]
    descriptor = ctypes.c_void_p()
    if not win["ConvertStringSecurityDescriptorToSecurityDescriptorW"]("D:", 1, ctypes.byref(descriptor), None):
        raise _windows_failed(win)
    try:
        present, defaulted, dacl = win["wintypes"].BOOL(), win["wintypes"].BOOL(), ctypes.c_void_p()
        if not win["GetSecurityDescriptorDacl"](descriptor, ctypes.byref(present), ctypes.byref(dacl),
                                                ctypes.byref(defaulted)):
            raise _windows_failed(win)
        code = win["SetNamedSecurityInfoW"](str(path), 1, 0x4 | 0x20000000, None, None, dacl, None)
        if code:                                    # DACL and UNPROTECTED_DACL_SECURITY_INFORMATION
            raise _windows_failed(win, code)
    finally:
        win["LocalFree"](descriptor)


def _windows_this_account():
    """This account's SID, as text, read once from the process's token."""
    if not _WINDOWS_ACCOUNT:
        win = _windows_calls()
        ctypes = win["ctypes"]
        token = ctypes.c_void_p()
        if not win["OpenProcessToken"](win["GetCurrentProcess"](), 0x0008, ctypes.byref(token)):    # TOKEN_QUERY
            raise _windows_failed(win)
        try:
            size = win["wintypes"].DWORD(0)
            win["GetTokenInformation"](token, 1, None, 0, ctypes.byref(size))                       # TokenUser
            held = ctypes.create_string_buffer(size.value)
            if not win["GetTokenInformation"](token, 1, ctypes.cast(held, ctypes.c_void_p), size,
                                              ctypes.byref(size)):
                raise _windows_failed(win)
            _WINDOWS_ACCOUNT.append(_windows_sid_text(win, ctypes.c_void_p.from_buffer(held).value))
        finally:
            win["CloseHandle"](token)
    return _WINDOWS_ACCOUNT[0]


def _former_folder_not_this_accounts(legacy):
    """Whether what stands at the former folder's name `legacy` belongs to
    another account, judged at the name itself: a link there is judged as
    the link, by its own owner, and is not followed. A link of this
    account's at that name is carried as a link (_copy_the_former_folder),
    never read, and the folder it leads to is then judged as the data
    folder is (_keep_the_data_folder_ours); one another account made there
    is that account's choice of where the data folder would lead, and is
    refused with the folder. False where nothing can be looked at there.
    On Windows, which reads and copies the former folder by its name, both
    the name and the folder it leads to are judged, as the data folder is
    (_not_this_accounts)."""
    if not hasattr(os, "getuid"):
        return _not_this_accounts(legacy)
    try:
        return not _ours(_owner_of_the_name(legacy))
    except (OSError, ValueError):
        return False


def _keep_the_data_folder_ours(path):
    """Refuse the data folder `path` where it belongs to
    another account; else make it 0700 (0755, 0777 and 0333 become 0700).
    The owner's own bits were left as they were, so an older version's 0333
    folder became 0300, which its owner cannot list: the launch's look at
    its files gave up, and a store others could write in it was loaded
    unseen. It now lets its owner read, write and search it as
    well; where it still cannot be listed, nothing is read from it
    (_folder_not_to_be_used). A link in the folder's place is judged by its
    own owner (another account's is refused), then followed, so the folder
    it names is judged and narrowed too. On Windows, where the mode calls
    change nothing that matters, a folder whose access list gives anyone
    but this account, SYSTEM and Administrators anything, or one of
    Administrators' or SYSTEM's that grants this account nothing, is given
    the protected list instead (_narrow_to_its_owner).

    Only the folder's own owner and the final folder a link at its name led
    to were judged, never the folders between: where the path ran through a
    folder another account may write in, that account could put another of
    the user's folders in the data folder's place, once, before a launch,
    whose files the launch read as the user's and the saves wrote over. The
    whole path is now judged (_held_by_its_whole_path; on Windows
    _windows_judge_the_whole_path), and one another account could change is
    refused (DataFolderOpenToOthers), as a folder of another account's is.

    A change of mode the system refused was taken for a filesystem that
    keeps no modes, and every look at the files others could change in the
    folder was dropped. It now refuses the folder (DataFolderNotClosed), as
    an access list that cannot be closed does on Windows; a filesystem is
    taken as keeping no modes only where the change was taken and did not
    hold (_note_whether_it_keeps_modes). A folder already 0700 needs no
    change, and none is asked.

    The descriptor of the folder judged is returned (on Windows, of a handle
    that shares no deleting: _windows_hold_the_folder), for the launch to
    hold for the life of the process (_hold_for_the_launch); the caller
    closes it where the launch goes no further."""
    if _not_this_accounts(path):
        raise DataFolderRefused(errno.EPERM, DATA_FOLDER_NOT_OURS, str(path))
    if not hasattr(os, "getuid"):
        _windows_judge_the_whole_path(path)
        _narrow_to_its_owner(path, whole=True, refuse=True)
        fd = _windows_hold_the_folder(path)
        try:
            if not os.path.samestat(os.fstat(fd), os.stat(path)):
                raise DataFolderOpenToOthers(errno.EPERM, DATA_FOLDER_PATH_OPEN, str(path))
        except BaseException:
            os.close(fd)
            raise
        return fd
    fd = _held_by_its_whole_path(path)
    try:
        if not _ours(os.fstat(fd).st_uid):
            raise DataFolderRefused(errno.EPERM, DATA_FOLDER_NOT_OURS, str(path))
        _narrow_to_its_owner(fd, whole=True, refuse=True)
    except BaseException:
        os.close(fd)
        raise
    return fd


def _judge_the_former_folders_path(legacy):
    """Judge the path to the folder under the app's former name `legacy` as
    the data folder's is judged (a link at its name judged by its own owner
    and followed), before it is moved or copied: one another account could
    change is left where it is, unmoved and unread, and the move's failure
    is said (FormerFolderNotCopied). What its own owner is, and what it
    holds, are the move's to judge, as before; another account's folder or
    link at the name is refused as such first (FormerFolderRefused), so
    that the page says whose it is."""
    if _former_folder_not_this_accounts(legacy):
        raise FormerFolderRefused(errno.EPERM, FORMER_FOLDER_NOT_OURS, str(legacy))
    try:
        if hasattr(os, "getuid"):
            _held_by_its_whole_path(legacy, opened=False)
        else:
            _windows_judge_the_whole_path(legacy)
    except DataFolderRefused:
        raise FormerFolderNotCopied(errno.EPERM, FORMER_FOLDER_NOT_COPIED, str(legacy)) from None
    except (OSError, ValueError):
        pass                            # nothing to judge there: the move's own looks say what it is


# The data folder this launch judged and holds (_hold_for_the_launch), or
# None; and each data folder a launch refused (DataFolderRefused), by the
# name it was asked at, with its reason. Both are set again whenever the
# module is loaded again, and the folder held before is let go.
_HELD = [None]
_REFUSED = {}
# The names whose folder held was removed while the app ran (_held_now),
# until a folder made there again is judged and held (_hold_again).
_LET_GO = set()


class _HeldFolder:
    """A descriptor held on the data folder for the life of the process, and
    the name it was judged at. On POSIX (`relative`) every file in the
    folder is reached through it (_in_the_held_folder), never by the
    folder's name again, so a folder on the way renamed or replaced after
    the launch moves nothing. On Windows, which reaches no file through a
    folder's handle, it is a handle that shares no deleting
    (_windows_hold_the_folder), so that the folder cannot be renamed while
    it is held, and the files are reached by their names."""

    _close = staticmethod(os.close)     # still bound when the interpreter ends

    def __init__(self, fd, name, relative):
        self.fd, self.name, self.relative = fd, name, relative

    def close(self):
        fd, self.fd = self.fd, None
        if fd is not None:
            try:
                self._close(fd)
            except OSError:
                pass

    def __del__(self):
        self.close()


def _hold_for_the_launch(fd, path, relative):
    """Hold the descriptor `fd` of the data folder judged at `path` for the
    life of the process, in the place of any held before (closed)."""
    old, _HELD[0] = _HELD[0], _HeldFolder(fd, os.fspath(path), relative)
    if old is not None:
        old.close()


def _held_now():
    """The folder held (_HELD[0]), or None. On POSIX one that has been
    removed while the app ran (no name left for it: st_nlink 0) is let go
    first and its name noted (_LET_GO), so that the folder is said gone, by
    its name, as before; a folder made at that name again is judged and held
    as a launch holds one before anything is read from it (_hold_again). A
    folder renamed aside keeps its name elsewhere, and stays held: a folder
    on the way changed after the launch moves nothing."""
    held = _HELD[0]
    if held is None or held.fd is None:
        return None
    if held.relative:
        try:
            removed = os.fstat(held.fd).st_nlink == 0
        except OSError:
            removed = True
        if removed:
            _HELD[0] = None
            _LET_GO.add(held.name)
            held.close()
            return None
    return held


def _hold_again(folder):
    """Where the folder held at the name `folder` was removed while the app
    ran (_held_now) and a folder stands there again, judge it and hold it as
    a launch does (_make_user_data_dir), before anything is read from it; a
    refusal is kept as a launch's is (_REFUSED, and DATA_DIR_ERROR for the
    data folder, so that data_folder_state says it)."""
    global DATA_DIR_ERROR
    if isinstance(folder, int) or _the_held(folder) is not None:
        return
    name = os.fspath(folder)
    if name not in _LET_GO or not os.path.isdir(name):
        return
    _LET_GO.discard(name)
    try:
        _make_user_data_dir(Path(name), lock_wait=0)
    except OSError as exc:
        if name == os.fspath(DATA_DIR):
            DATA_DIR_ERROR = exc.strerror or str(exc)


def _the_held(folder):
    """The held folder, where `folder` is the name it was judged at; else None."""
    held = _held_now()
    if held is not None and not isinstance(folder, int) and os.fspath(folder) == held.name:
        return held
    return None


def _in_the_held_folder(path):
    """(descriptor, name): where `path` names a file in the data folder held
    on POSIX, the folder's descriptor and the file's own name, to reach it
    relative to the folder held (dir_fd); (descriptor, ".") where it names
    that folder; else (None, path), reached by its name as before."""
    held = _held_now()
    if held is None or not held.relative or isinstance(path, int):
        return None, path
    text = os.fspath(path)
    if text == held.name:
        return held.fd, "."
    head, name = os.path.split(text)
    if head == held.name and name not in ("", ".", ".."):
        return held.fd, name
    return None, path


# Each call below is the system's own, made on a file in the data folder
# relative to the folder held (dir_fd), and by the name as given anywhere
# else, or where nothing is held.
def _lstat(path):
    fd, name = _in_the_held_folder(path)
    if fd is None:
        return os.lstat(path)
    # The folder held itself is asked through its descriptor: a look up of
    # "." in it needs the right to search it, which a folder shut since the
    # launch no longer gives.
    return os.fstat(fd) if name == "." else os.stat(name, dir_fd=fd, follow_symlinks=False)


def _stat(path):
    fd, name = _in_the_held_folder(path)
    if fd is None:
        return os.stat(path)
    return os.fstat(fd) if name == "." else os.stat(name, dir_fd=fd)


def _lexists(path):
    try:
        _lstat(path)
    except (OSError, ValueError):
        return False
    return True


def _exists(path):
    try:
        _stat(path)
    except (OSError, ValueError):
        return False
    return True


def _islink(path):
    try:
        return stat.S_ISLNK(_lstat(path).st_mode)
    except (OSError, ValueError):
        return False


def _isdir(path):
    try:
        return stat.S_ISDIR(_stat(path).st_mode)
    except (OSError, ValueError):
        return False


def _open(path, flags, mode=0o777):
    fd, name = _in_the_held_folder(path)
    return os.open(path, flags, mode) if fd is None else os.open(name, flags, mode, dir_fd=fd)


def _unlink(path):
    fd, name = _in_the_held_folder(path)
    return os.unlink(path) if fd is None else os.unlink(name, dir_fd=fd)


def _rename(src, dst):
    (one, a), (other, b) = _in_the_held_folder(src), _in_the_held_folder(dst)
    os.rename(a, b, src_dir_fd=one, dst_dir_fd=other)


def _replace(src, dst):
    (one, a), (other, b) = _in_the_held_folder(src), _in_the_held_folder(dst)
    os.replace(a, b, src_dir_fd=one, dst_dir_fd=other)


def _link(src, dst):
    (one, a), (other, b) = _in_the_held_folder(src), _in_the_held_folder(dst)
    os.link(a, b, src_dir_fd=one, dst_dir_fd=other)


def _chmod(path, mode):
    fd, name = _in_the_held_folder(path)
    if fd is None:
        os.chmod(path, mode)
    elif name == ".":
        os.fchmod(fd, mode)
    else:
        os.chmod(name, mode, dir_fd=fd)


def _listdir(folder):
    """The names in `folder`; the folder held is listed through its
    descriptor (_list_through)."""
    fd, name = _in_the_held_folder(folder)
    if fd is None or name != ".":
        return os.listdir(folder)
    return _list_through(fd)


def _list_through(fd):
    """The names in the folder open at the descriptor `fd`, the descriptor
    rewound to its start first, because on some filesystems (Btrfs) a
    folder's descriptor lists no name made since it was opened or last
    rewound: a descriptor kept past one listing, or opened before the
    folder was written into, would list it as it stood then. A rewind
    refused is passed over, and the folder is still listed through the
    descriptor alone, never by a name."""
    try:
        os.lseek(fd, 0, os.SEEK_SET)
    except OSError:
        pass
    return os.listdir(fd)


def _access(path, mode):
    fd, name = _in_the_held_folder(path)
    return os.access(path, mode) if fd is None else os.access(name, mode, dir_fd=fd)


def _statvfs(path):
    fd, name = _in_the_held_folder(path)
    return os.statvfs(path) if fd is None or name != "." else os.statvfs(fd)


# --- The whole path to the data folder ----------------------------------
# How many links one walk follows (the system's own bound is of this size).
_LINKS_ON_THE_WAY = 40
# The error of a link met where none is followed, or of too many links;
# a name not every system's errno module gives, so read with a default.
_ELOOP = getattr(errno, "ELOOP", errno.EINVAL)
# The owner the kernel shows, in a user namespace that maps no id to root's,
# for every file whose owner it does not map (root's among them); None
# where root's is mapped. Read once (_unmapped_owner).
_UNMAPPED = []


def _unmapped_owner():
    """In a user namespace of its own (a sandbox such as Flatpak's or
    bubblewrap's, which maps this account's id and not the system's), the
    overflow id the kernel shows as the owner of every file whose owner the
    namespace does not map, root's among them -- where no id of the
    namespace's own is that id; else None (the system's own namespace,
    which maps every id as itself, and any system without /proc)."""
    if not _UNMAPPED:
        found = None
        try:
            with open("/proc/self/uid_map", encoding="ascii") as rows:
                spans = [tuple(int(n) for n in row.split()) for row in rows if row.strip()]
            with open("/proc/sys/kernel/overflowuid", encoding="ascii") as overflow:
                shown = int(overflow.read().strip())
            if (spans and spans != [(0, 0, 4294967295)]
                    and not any(inside <= shown < inside + count for inside, _outside, count in spans)):
                found = shown
        except (OSError, ValueError, TypeError):
            found = None
        _UNMAPPED.append(found)
    return _UNMAPPED[0]


def _ours_or_the_systems(uid):
    """Whether the owner `uid` of a folder or link on the way to the data
    folder is this account's or the system's: this account's id, root's,
    or the id a user namespace shows for root's (_unmapped_owner)."""
    return uid == os.getuid() or uid == 0 or (uid is not None and uid == _unmapped_owner())


def _a_group_of_one(gid):
    """Whether the group `gid` is this account's own group and no other's:
    its primary group, named as the account, listing no member but this
    account, and the primary group of no other account in the password
    database (read with grp and pwd). On many Linux systems every account
    has such a group and a desktop session's umask is 002, so the folders a
    user makes there are writable by that group."""
    try:
        import grp
        import pwd
        me = pwd.getpwuid(os.getuid())
        if me.pw_gid != gid:
            return False
        group = grp.getgrgid(gid)
        if group.gr_name != me.pw_name or any(member != me.pw_name for member in group.gr_mem):
            return False
        return not any(other.pw_gid == gid and other.pw_uid != me.pw_uid for other in pwd.getpwall())
    except (ImportError, KeyError, OSError, ValueError):
        return False


# The extended attribute that holds a folder's POSIX access list on Linux,
# and the errors that say a folder carries none: no such attribute, or a
# filesystem (or system) that keeps no such lists; names not every system's
# errno module gives, so read with defaults.
_ACCESS_LIST_ATTRIBUTE = "system.posix_acl_access"
_NO_ACCESS_LIST = {getattr(errno, "ENODATA", errno.ENOENT), getattr(errno, "ENOTSUP", errno.ENOENT),
                   getattr(errno, "EOPNOTSUPP", errno.ENOENT)}
# The error of an O_PATH descriptor, which reads no attribute itself.
_EBADF = getattr(errno, "EBADF", None)


def _carries_an_access_list(fd):
    """Whether the folder open at `fd` carries an extended POSIX access
    list (on Linux, the attribute _ACCESS_LIST_ATTRIBUTE; read through
    /proc where `fd` is an O_PATH descriptor, which reads no attribute
    itself). False where it carries none, or where the filesystem or the
    system keeps no such lists (no os.getxattr: not Linux); True where it
    does, and where the reading fails in any other way: such a folder fails
    closed, as one open to others."""
    getxattr = getattr(os, "getxattr", None)
    if getxattr is None:
        return False
    try:
        try:
            getxattr(fd, _ACCESS_LIST_ATTRIBUTE)
        except OSError as exc:
            if exc.errno != _EBADF:
                raise
            getxattr(f"/proc/self/fd/{fd}", _ACCESS_LIST_ATTRIBUTE)
    except OSError as exc:
        return exc.errno not in _NO_ACCESS_LIST
    return True


def _closed_to_others(seen, fd):
    """Whether no account but this one may write in the folder `seen` (its
    stat; `fd`, a descriptor of it): neither its group nor others may, or
    only its group, where that is this account's group of one
    (_a_group_of_one) and the folder carries no extended access list
    (_carries_an_access_list). On Linux a list's mask is the mode's group
    bits, so a list that gives another account write shows as group write:
    the group alone cannot then say who may write, and the folder is open.
    A list whose mask gives no write leaves the group bits without it, and
    is closed by them alone."""
    mode = stat.S_IMODE(seen.st_mode)
    if mode & 0o002:
        return False
    return not mode & 0o020 or (_a_group_of_one(seen.st_gid) and not _carries_an_access_list(fd))


def _held_by_its_whole_path(path, opened=True, mend=True):
    """POSIX: the folder `path` reached by walking its path from the root,
    each folder opened relative to the one above it (O_DIRECTORY |
    O_NOFOLLOW; O_PATH where the system has it), each link met read where it
    stands and the path it gives walked the same way, from the root where it
    is absolute; a descriptor of the folder it ends at, opened for reading
    and checked to be the folder the walk reached (None where not
    `opened`). Every folder an entry is looked up in on the way must be this
    account's or the system's (_ours_or_the_systems) and closed to other
    accounts (_closed_to_others) -- a sticky folder (S_ISVTX, as /tmp is)
    counts as closed where the entry looked up in it is this account's or
    the system's, since no other account may then rename or remove it --
    and every link met must be this account's or the system's: else
    DataFolderOpenToOthers. The folder the walk ends at is judged by its own
    owner, and narrowed, by the caller. A folder its owner may not read (an
    older version's 0333, left 0300) is given 0700 through the folder above
    it, and opened then; where that change is refused, DataFolderNotClosed
    (not where `mend` is false: the folder an older version used is left as
    it stands, and the PermissionError raised). OSError as the system raises
    it otherwise: nothing there, something that is not a folder, a loop of
    links."""
    walk = (os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_PATH", os.O_RDONLY))
    text = os.fspath(path)
    if not os.path.isabs(text):
        text = os.path.join(os.getcwd(), text)
    refused = DataFolderOpenToOthers(errno.EPERM, DATA_FOLDER_PATH_OPEN, text)
    pending = list(reversed(text.split("/")))
    root = os.open("/", walk)
    stack = [(root, os.fstat(root))]
    last = None
    links = 0
    try:
        while pending:
            name = pending.pop()
            if name in ("", "."):
                continue
            if name == "..":
                if len(stack) > 1:
                    os.close(stack.pop()[0])
                continue
            fd, folder = stack[-1]
            if not _ours_or_the_systems(folder.st_uid):
                raise refused
            entry = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if not _closed_to_others(folder, fd) and not (folder.st_mode & stat.S_ISVTX
                                                      and _ours_or_the_systems(entry.st_uid)):
                raise refused
            if stat.S_ISLNK(entry.st_mode):
                links += 1
                if links > _LINKS_ON_THE_WAY:
                    raise OSError(_ELOOP, os.strerror(_ELOOP), text)
                if not _ours_or_the_systems(entry.st_uid):
                    raise refused
                target = os.readlink(name, dir_fd=fd)
                if not os.path.samestat(entry, os.stat(name, dir_fd=fd, follow_symlinks=False)):
                    raise refused       # the link changed while it was read
                if target.startswith("/"):
                    while len(stack) > 1:
                        os.close(stack.pop()[0])
                pending.extend(reversed(target.split("/")))
                continue
            child = os.open(name, walk, dir_fd=fd)
            stack.append((child, os.fstat(child)))
            last = name
            if not os.path.samestat(stack[-1][1], entry):
                raise refused           # the folder changed while it was opened
        if not opened:
            return None
        if last is None or len(stack) < 2:
            raise OSError(errno.EINVAL, os.strerror(errno.EINVAL), text)
        (above, _seen), (_fd, reached) = stack[-2], stack[-1]
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        try:
            held = os.open(last, flags, dir_fd=above)
        except PermissionError:
            if not mend:
                raise
            try:
                os.chmod(last, 0o700, dir_fd=above)
            except OSError:
                raise DataFolderNotClosed(errno.EPERM, DATA_FOLDER_NOT_CLOSED, text) from None
            held = os.open(last, flags, dir_fd=above)
        if not os.path.samestat(os.fstat(held), reached):
            os.close(held)
            raise refused
        return held
    finally:
        for fd, _seen in stack:
            os.close(fd)


# The rights over a folder that let another account rename or replace it,
# or what is in it, or take the folder for its own: delete it, delete
# what is in it, change its list or its owner, and the generic form that
# holds them all (DELETE, FILE_DELETE_CHILD, WRITE_DAC, WRITE_OWNER,
# GENERIC_ALL). Making a new file or folder in it is not one: that replaces
# nothing on the way.
_WINDOWS_RIGHTS_OVER_A_FOLDER = 0x10000 | 0x40 | 0x40000 | 0x80000 | 0x10000000
# TrustedInstaller, the system's own service, which owns the system drive's root.
_TRUSTED_INSTALLER_SID = "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"
# The reparse tags of a symbolic link and of a junction.
_WINDOWS_LINK_TAGS = (0xA000000C, 0xA0000003)


def _windows_judge_the_whole_path(path, hops=0):
    """Windows: judge every folder on the way to `path` as
    _held_by_its_whole_path does on POSIX, by name, Python holding no
    descriptor of a folder there: each folder an entry is looked up in must
    be this account's or the system's (_ours: this account, Administrators,
    SYSTEM; and TrustedInstaller) and give no other account a right to
    rename or replace what is in it (_windows_folder_is_open_to_others);
    each symbolic link or junction met must be this account's or the
    system's itself, and the path it gives is judged the same way, from its
    root. DataFolderOpenToOthers else, and where an owner or a list cannot
    be read. The folder is then held so that nothing on the way can be
    renamed (_windows_hold_the_folder)."""
    text = os.path.abspath(os.fspath(path))
    refused = DataFolderOpenToOthers(errno.EPERM, DATA_FOLDER_PATH_OPEN, text)
    parts = Path(text).parts
    here = Path(parts[0])
    for index, part in enumerate(parts[1:], 1):
        try:
            owner = _windows_owner(here, follow_links=False)
            if not (_ours(owner) or owner == _TRUSTED_INSTALLER_SID) or _windows_folder_is_open_to_others(here):
                raise refused
        except OSError as exc:
            if exc is refused:
                raise
            raise refused from None
        here = here / part
        seen = os.lstat(here)
        if not (stat.S_ISLNK(seen.st_mode) or getattr(seen, "st_reparse_tag", 0) in _WINDOWS_LINK_TAGS):
            continue
        if hops >= _LINKS_ON_THE_WAY:
            raise OSError(_ELOOP, os.strerror(_ELOOP), text)
        try:
            owner = _windows_owner(here, follow_links=False)
        except OSError:
            raise refused from None
        if not (_ours(owner) or owner == _TRUSTED_INSTALLER_SID):
            raise refused
        target = os.readlink(here)
        if target.startswith("\\\\?\\"):
            target = target[4:]
        if not os.path.isabs(target):
            target = os.path.join(os.path.dirname(here), target)
        return _windows_judge_the_whole_path(Path(target, *parts[index + 1:]), hops + 1)
    return None


def _owner_only(fd):
    """Give the file just made on `fd` mode 0600 exactly.
    Its open asked for 0600, which the umask can only cut (to 0o200 under
    0o444, a copy its owner could not read back); os.fchmod is not cut. No
    fchmod on Windows, where the copy takes the folder's access list."""
    if os.name != "nt" and hasattr(os, "fchmod"):
        try:
            os.fchmod(fd, 0o600)
        except OSError:
            pass


def _sync_folder(folder):
    """Sync `folder` itself to the disk, so that a replace made in it is
    kept; on Linux and macOS only (Windows opens no folder for this). A
    folder that cannot be opened or synced (a filesystem that refuses it)
    is passed over: the file's own bytes were synced before the replace."""
    if os.name == "nt":
        return
    try:
        fd = _open(folder, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _new_temp_file(target, mode=0o600):
    """A temp file of this write's own beside `target`, made new at `mode`
    (the target's own, or 0600 for a first-ever file) --
    the umask may cut it narrower, never wider -- and its descriptor open
    for writing: `<name>.<random>.tmp`, so that what looks for a stray temp
    file (`*.tmp`) still finds one. A name already taken is passed over for
    another; any other refusal (a folder this account cannot write in) is
    raised, as the plain write raised it."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    for _attempt in range(64):
        tmp = target.with_name(f"{target.name}.{secrets.token_hex(8)}.tmp")
        try:
            return tmp, _open(tmp, flags, mode & 0o777)
        except FileExistsError:
            continue
    raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(target.parent))


def _remove(path):
    """Remove the file at `path`, made writable first where it is not (a
    read-only file cannot be removed on every system); one that cannot be
    removed is left."""
    try:
        _unlink(path)
    except FileNotFoundError:
        pass
    except OSError:
        try:
            _chmod(path, stat.S_IREAD | stat.S_IWRITE)
            _unlink(path)
        except OSError:
            pass


# The files in the data folder the app reads, judged at each launch: the
# store and the preferences, the store's versions and the recovery copies of
# an unreadable store or preferences file (each read to be compared). Matched
# whatever the case, as Windows and macOS match a name. A write's temporary
# file is the load's to judge (_tidy_stray_temp_files); a file set aside, a
# save cut short kept aside and the mark of a store brought in are never
# read, and are left as they are.
_READ_NAME = re.compile(r"(?:saved_charts|preferences)\.json(?:\.(?:previous|unreadable)-.*)?",
                        re.IGNORECASE | re.DOTALL)
# The two locks' files. Neither is ever read, copied, moved or replaced: a
# window may hold the lock on the file under the name, and a new file there
# would let a second window take "the" lock while the first holds it.
_LOCK_NAME = re.compile(r"(?:saved_charts|preferences)\.lock", re.IGNORECASE)
# A file set aside is renamed to its own name, this, and the time
# (_set_aside_if_others_could_write); the store's and the preferences' are
# read only by the restore the page offers (restore_set_aside).
_SET_ASIDE = ".set-aside-"
# The store's name and the preferences': a file set aside from either is
# set aside under it, whatever the case of the name it was found at
# (_its_own_name), so that the restore finds it.
_RESTORED_NAMES = ("saved_charts.json", "preferences.json")

STORE_TEXT_LIMIT = 64 * 1024 * 1024
# The most bytes a store, an old store, a recovery copy of one or a stray of
# a write of one is read to (one more tells it is past): the text the writer
# makes is ASCII -- json.dumps escapes every other character -- so a store
# this app wrote is never more bytes than characters. A file past it is not
# read, as a pipe at its name is not: it is no store this app could have
# written, nor one it would write back.
STORE_BYTE_LIMIT = STORE_TEXT_LIMIT


def _recovery_stamp():
    return f"{datetime.now():%Y%m%d-%H%M%S}"


# How much one launch handles at most: the files it judges in the data folder
# and copies with the former folder, and the bytes it copies. No real data
# folder comes near them -- it holds a store and a preferences file of a few
# kilobytes, ten versions of the store and a recovery copy or two, and no
# store is ever more than STORE_BYTE_LIMIT -- so a folder past them is one
# filled by another hand: a copy past them is not made (the former folder
# stays where it is, as one that cannot be copied whole), and the files past
# the count are left for the loads, which read none another account could
# change (_open_this_accounts_file).
_LAUNCH_FILE_LIMIT = 4096
_LAUNCH_BYTE_LIMIT = 1024 * 1024 * 1024
# What this launch has handled so far: files, bytes. Set to nothing once,
# when the module is loaded: one process is one launch. It was set to
# nothing at each making of the folder, which data_folder_state() asks
# again at every run of the page while the making fails, so a former folder
# whose copy kept failing was copied again at each run, past the bound.
_LAUNCH_TALLY = [0, 0]


class _Exposed(PermissionError):
    """A file of this account's that another account could change -- its
    group or others may write it (POSIX), or its own access list lets an
    account but this one, SYSTEM and Administrators change it (Windows), or
    that cannot be judged -- or a link of this account's that leads further
    than one regular file of this account's in a folder no other account may
    write in. Nothing of it is read, and nothing is written through it."""


def _wide(seen):
    """Whether the mode in the stat result `seen` lets the group or others write."""
    return bool(stat.S_IMODE(seen.st_mode) & 0o022)


# The data folder (its device and inode) where this launch found its
# filesystem keeps no modes; empty where it keeps them, and on Windows.
_MODELESS = []


def _note_whether_it_keeps_modes(path, held=None):
    """Note whether the data folder `path`, made 0700 by this launch
    through the descriptor `held` (_keep_the_data_folder_ours), reads back
    through that same descriptor with a group or other bit: a filesystem
    that keeps no modes (a memory stick's FAT or exFAT, some network
    folders) shows every file and folder as open to all, whatever is set.
    Its files were all set aside as files others could change, every save
    at the next load, so nothing could be kept there. Such a folder is
    taken as it is: its files read, nothing set aside, nothing said
    (_taken_as_it_is). Told from what the launch itself set on the folder,
    never from a file's mode alone: a file others may write on a disk that
    keeps modes is still set aside. Windows judges lists, not modes: a
    volume that keeps no lists is its own case (_windows_keeps_lists).

    Only where the change was taken: a change refused refuses the folder
    (DataFolderNotClosed) before this look. Only the folder the descriptor
    holds is noted, and only where the name still leads to it after the
    look (os.path.samestat with a stat of `path`): a look by name
    after a narrowing by name noted whatever folder had been renamed in at
    the name between the two -- an ordinary folder others may write, its
    files then read as the user's. Nothing is noted without a descriptor
    (None: a folder that could not be opened)."""
    _MODELESS.clear()
    if not hasattr(os, "getuid") or held is None:
        return
    try:
        seen = os.fstat(held)
        if not stat.S_IMODE(seen.st_mode) & 0o077:
            return
        if not os.path.samestat(seen, os.stat(path)):
            return
    except (OSError, ValueError):
        return
    _MODELESS.append((seen.st_dev, seen.st_ino))


def _taken_as_it_is(seen, path):
    """Whether the file at `path`, as `seen` (lstat, stat or fstat of it),
    is in the data folder this launch found keeps no modes, on that
    folder's own filesystem: its mode says nothing of who may change it."""
    if not _MODELESS:
        return False
    try:
        folder = _stat(os.path.dirname(os.path.abspath(path)))
    except (OSError, ValueError):
        return False
    return (folder.st_dev, folder.st_ino) in _MODELESS and seen.st_dev == folder.st_dev


def _wide_here(seen, path):
    """_wide, but False for a file in a data folder that keeps no modes
    (_taken_as_it_is)."""
    return _wide(seen) and not _taken_as_it_is(seen, path)


def _windows_wide(path, follow_links=False):
    """Windows: whether the file at `path` (a link followed where
    `follow_links`) has a list that lets another account change it
    (_windows_file_is_writable_by_others); True where the list cannot be
    read: a file that cannot be judged is not read."""
    try:
        return _windows_file_is_writable_by_others(path, follow_links=follow_links)
    except OSError:
        return True


def _exposed_at_the_name(path):
    """Whether what stands at the name `path` -- a regular file of this
    account's, judged at the name, a link not followed -- is one another
    account could change (POSIX: lstat; Windows: its own list). False for
    anything else, or nothing."""
    try:
        seen = _lstat(path)
    except OSError:
        return False
    if not stat.S_ISREG(seen.st_mode):
        return False
    return _wide_here(seen, path) if hasattr(os, "getuid") else _windows_wide(path)


def _exposed_as_opened(fd, path, follow_links=False):
    """Whether the file open at `fd` (opened at `path`) is one another
    account could change: on POSIX its mode as opened (fstat); on Windows its
    list, read at the name while `fd` holds it open -- a file opened here
    shares no deleting, so no other file can take its name meanwhile."""
    if hasattr(os, "getuid"):
        return _wide_here(os.fstat(fd), path)
    return _windows_wide(path, follow_links)


def _list_the_data_folder(folder):
    """The names in the data folder `folder` (through the descriptor the
    launch holds, where it is that folder); OSError where it cannot be
    listed."""
    return _listdir(folder)


def _set_aside_what_others_could_write(folder):
    """Set aside each file the app reads in the data folder `folder` that
    another account could change (_set_aside_if_others_could_write), and
    narrow each lock file others could write in place
    (_narrow_a_lock_in_place); at most _LAUNCH_FILE_LIMIT names this launch.
    OSError where the folder cannot be listed: the caller leaves the folder
    refused (_folder_not_to_be_used), and nothing is read from it. A file
    that cannot be looked at, opened or moved is left as it is: a load reads
    none another account could change (_open_this_accounts_file)."""
    names = sorted(_list_the_data_folder(folder))
    for name in names:
        lock = _LOCK_NAME.fullmatch(name)
        if not lock and (not _READ_NAME.fullmatch(name) or _SET_ASIDE in name.lower()):
            continue
        if _LAUNCH_TALLY[0] >= _LAUNCH_FILE_LIMIT:
            return
        _LAUNCH_TALLY[0] += 1
        try:
            if lock:
                _narrow_a_lock_in_place(Path(folder) / name)
            else:
                _set_aside_if_others_could_write(Path(folder) / name, _its_own_name(folder, name))
        except OSError:
            continue


def _its_own_name(folder, name):
    """The name a file found at `name` in `folder` is set aside under: the
    store's or the preferences' own (_RESTORED_NAMES) where `name` is that
    name in another case and is the same file as that name (a volume that
    matches names whatever their case: Windows', and macOS' by default);
    else `name`. The restore looks for the store's own name's form alone, so
    a store found as SAVED_CHARTS.JSON and set aside under that name was
    awaited by nothing: no notice, no button, the charts gone from the app.
    Matching the restore's form without regard to case instead would also
    offer, on a volume that tells the cases apart, a file the app never
    read as its store; and either way the restore writes the store's own
    name."""
    for own in _RESTORED_NAMES:
        if name != own and name.lower() == own:
            try:
                if os.path.samestat(_lstat(os.path.join(folder, name)), _lstat(os.path.join(folder, own))):
                    return own
            except OSError:
                pass
    return name


def _set_aside_if_others_could_write(path, aside_as=None):
    """Move the file at `path`, a regular file of this account's that
    another account could change, aside under a recovery name of its own
    beside it, and make it private there; nothing of it is read. On POSIX it
    could be where its group or others may write it (st_mode & 0o022),
    judged at the name (lstat) and again from what was opened (fstat); on
    Windows where its own access list allows anyone but this account, SYSTEM
    and Administrators a right to change it
    (_windows_file_is_writable_by_others), or cannot be read.

    'aside' where it was moved; 'held' where it could not be (on Windows,
    another account holding it open without sharing deleting refuses the
    rename): it then stays at its name as it is, and is not read, the load
    judging it again; None where it is not such a file. A link, or another
    account's file, at the name is not moved: a link is judged by the file it
    leads to, as a load opens it (_open_this_accounts_file).

    An older version under umask 000 left the store and the preferences
    0666; another account could write them through a descriptor or a hard
    link it held, or by name, and the next load read what it wrote as the
    user's. A private copy of the bytes put over the name kept the handles
    off the copy but still took what had already been written for the
    user's own. The file is now moved aside by a rename in the same folder
    (never a copy: no byte of it is read), to `<name>.set-aside-<time>`,
    which no load reads and no later look moves again; it is then made
    private -- on POSIX given 0600 through a descriptor opened without
    following a link, and only where that is the file judged; on Windows its
    own entries taken from its list, so that it keeps the folder's -- and
    the app opens without it. Only the user's one button brings it back,
    read then within its limit and written as a new file
    (restore_set_aside). The recovery name is made from `aside_as` where it
    is given (the store's own name, for one found at it in another case:
    _its_own_name), else from the name's own."""
    if _whose(path) != _OURS:
        return None
    seen = _lstat(path)
    if not stat.S_ISREG(seen.st_mode):
        return None
    posix = hasattr(os, "getuid")
    wide = _wide_here(seen, path) if posix else _windows_wide(path)
    if not wide and not posix:
        return None                     # no mode to read as opened: the list is the whole look
    fd = _open_regular_file(path, follow_links=False)
    try:
        opened = os.fstat(fd)
        if not (wide or _wide_here(opened, path)):
            return None
    finally:
        os.close(fd)                    # before the rename: Windows refuses one of a file held open
    aside = _move_aside(path, opened, aside_as)
    if aside is None:
        return 'held'
    _make_it_private(aside, opened)
    return 'aside'


def _move_aside(path, judged, aside_as=None):
    """Rename the file at `path` to the first free `<name>.set-aside-<time>`
    beside it (`<aside_as>.set-aside-<time>` where it is given), where the
    name still holds the file `judged`; the new path, or
    None where the rename is refused or the name holds another file now. A
    name already there is never written over: it is looked at first, in a
    folder no other account may write in, and on Windows the rename itself
    refuses one."""
    stem = f"{aside_as or path.name}{_SET_ASIDE}{_recovery_stamp()}"
    for n in range(1, 1000):
        aside = path.with_name(stem if n == 1 else f"{stem}-{n}")
        if _lexists(aside):
            continue
        try:
            if not os.path.samestat(_lstat(path), judged):
                return None
            _rename(path, aside)
        except FileExistsError:
            continue
        except OSError:
            return None
        return aside
    return None


def _make_it_private(path, judged):
    """Make the file at `path` -- the one `judged`, moved there -- private:
    on POSIX mode 0600 (os.fchmod), through a descriptor opened without
    following a link, only where what was opened is that file; on Windows its
    own entries taken from its list, so that it holds the folder's alone. A
    change refused is passed over: the file is read only by the restore,
    which judges nothing by it."""
    if not hasattr(os, "getuid"):
        try:
            _windows_reset_the_list(path)
        except OSError:
            pass
        return
    try:
        fd = _open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                     | getattr(os, "O_CLOEXEC", 0))
    except OSError:
        return
    try:
        if os.path.samestat(os.fstat(fd), judged):
            os.fchmod(fd, 0o600)
    except OSError:
        pass
    finally:
        os.close(fd)


def _narrow_a_lock_in_place(path):
    """Narrow the lock file at `path`, a regular file of this account's that
    another account could write, in place: on POSIX mode 0600 through a
    descriptor opened without following a link, where what was opened is
    this account's (os.fchmod acts on what was opened); on Windows its own
    entries taken from its list. Its inode (on Windows, its file id) is
    kept, so a window holding the lock on it keeps holding it. A lock was
    replaced like a store, and a second window then took an exclusive lock on
    the new file while the first held it on the old. A lock holds no data:
    nothing of it is read or copied."""
    if _whose(path) != _OURS:
        return
    if not hasattr(os, "getuid"):
        if _exposed_at_the_name(path):
            try:
                _windows_reset_the_list(path)
            except OSError:
                pass
        return
    fd = _open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                 | getattr(os, "O_CLOEXEC", 0))
    try:
        opened = os.fstat(fd)
        if stat.S_ISREG(opened.st_mode) and _wide_here(opened, path) and _opened_is_ours(fd):
            os.fchmod(fd, 0o600)
    finally:
        os.close(fd)


def _within_the_launch(size):
    """Count one file of `size` bytes, about to be copied, against what one
    launch handles; NotAPlainFile (EFBIG) where it is past a store's own
    limit (STORE_BYTE_LIMIT) or would take the launch past its bounds."""
    _LAUNCH_TALLY[0] += 1
    if (size > STORE_BYTE_LIMIT or _LAUNCH_TALLY[0] > _LAUNCH_FILE_LIMIT
            or _LAUNCH_TALLY[1] + size > _LAUNCH_BYTE_LIMIT):
        raise NotAPlainFile(errno.EFBIG, os.strerror(errno.EFBIG), "past what one launch copies")


def _copy_within_bounds(one, out, size):
    """Copy the file open at `one`, whose size its fstat gave as `size`, to
    the file open at `out`, never past `size` bytes: a file that grows while
    it is copied is NotAPlainFile (EFBIG), and the copy is not made. Each
    byte counted against the launch's bound as it is copied."""
    copied = 0
    while True:
        chunk = os.read(one, min(1 << 20, size + 1 - copied))
        if not chunk:
            return
        copied += len(chunk)
        _LAUNCH_TALLY[1] += len(chunk)
        if copied > size or _LAUNCH_TALLY[1] > _LAUNCH_BYTE_LIMIT:
            raise NotAPlainFile(errno.EFBIG, os.strerror(errno.EFBIG), "grew while it was copied")
        view = memoryview(chunk)
        while view:
            view = view[os.write(out, view):]


@contextmanager
def _the_former_folder_held(legacy, wait):
    """The former folder found at the name `legacy`, opened and locked (a
    _FormerFolder), for as long as the `with` lasts; None where there is
    nothing to move -- nothing stands there, or the launch that held the
    lock before has moved it. `wait` seconds at most to have the lock.

    What stands at the name is identified once, at the first look, by its
    device and inode (os.lstat: the name's own, a link there not followed),
    and refused where it is another account's (FormerFolderRefused). A
    folder is then opened without following a link, and its owner and
    identity are read from what was opened (os.fstat): another account's is
    refused so too; another folder of this account's than the one first
    found is FormerFolderBusy; one that cannot be opened is
    FormerFolderUnreadable, as the look would find it. A link of this
    account's is carried as a link (_copy_the_former_folder): the folder it
    leads to is opened, and locked and looked at where it is this
    account's; where it is another's, nothing is read through the link,
    which is refused as the data folder once moved.

    Two launches looked at one former folder at once: the second read the
    mode the first had narrowed, took the folder for one never open to
    others, and moved it, while another account, writing in it again once
    the first had given its mode back, put a link in it. Every launch now
    holds this lock from before it reads the folder's mode until the folder
    is moved, copied and published, or refused and given its modes back:
    each reads the mode the one before it left.

    The folder opened is locked without blocking, asked again after a pause
    that grows to a tenth of a second (_lock_the_former_folder). Held
    elsewhere past `wait`: FormerFolderBusy, and nothing in it is narrowed,
    looked at, moved or copied. Once the lock is had the name is looked at
    again: where it is empty, the launch before has moved the folder; where
    it leads to anything but the object first found -- or a link there no
    longer leads to the folder opened -- the move ends
    (_still_the_former_folder). Any account that can read the folder -- one
    0755, the mode an older version made it with under the usual umask, as
    much as one wide -- can open it and hold the lock, and so stop the
    move: each launch then waits about ten seconds
    (_FORMER_FOLDER_LOCK_WAIT) before it raises FormerFolderBusy, and makes
    no data folder. Nothing of that account's is carried in by it, and the
    folder stays as it was.

    No lock is taken where the system has no flock (Windows, which makes no
    look either and moves by name: _make_user_data_dir), where a link of
    this account's at the name leads to another account's folder, or where
    the filesystem refuses flock for a reason other than a holder's
    (EOPNOTSUPP, ENOLCK): there two launches at once over one folder are as
    they were, and every other step is still tied to what was first
    found."""
    former = _the_former_folder_opened(legacy)
    fd = former.fd if former is not None else None
    try:
        if former is not None:
            if fd is not None and fcntl is not None:
                _lock_the_former_folder(fd, wait)
            if os.path.lexists(legacy):
                _still_the_former_folder(former)
            else:
                former = None                   # moved by the launch before
        yield former
    finally:
        if fd is not None:
            os.close(fd)                        # the lock goes with its descriptor


@dataclass
class _FormerFolder:
    """What a launch found at the former folder's name and holds through
    the move: the name `legacy`; `seen`, what os.lstat gave at the first
    look (its device and inode are the object's identity -- a link's its
    own); `link`, whether that is a link; and `fd`, a descriptor of the
    folder opened -- the folder itself, opened without following a link, or
    the folder a link of this account's leads to -- or None for a link
    leading to another account's folder, through which nothing is read."""
    legacy: Path
    seen: object
    link: bool
    fd: object = None


def _the_former_folder_opened(legacy):
    """What stands at the former folder's name `legacy`, identified and
    opened (_FormerFolder; _the_former_folder_held), or None where nothing
    there is to be moved: nothing stands there, or something that is
    neither a folder nor a link, or the folder is gone by the time it is
    opened (moved by the launch before). Raises FormerFolderRefused where
    it is another account's, at the name or as opened; FormerFolderBusy
    where the folder opened is another of this account's;
    FormerFolderUnreadable where a folder of this account's there cannot be
    opened; and FormerFolderNotCopied where its path is one other accounts
    could change (_the_former_folder_walked).

    The folder was opened by its path, a link at its name followed, after
    the path was judged: where a folder on the way was one another account
    could write in, it could put another of the user's folders there after
    the judgment, which the move then read as the former folder. The folder
    opened is now checked to be the one the walk that judges the path
    reaches (_the_former_folder_walked), so that the folder read is the
    folder judged."""
    uid = os.getuid()
    try:
        seen = os.lstat(legacy)
    except OSError:
        return None
    if seen.st_uid != uid:
        raise FormerFolderRefused(errno.EPERM, FORMER_FOLDER_NOT_OURS, str(legacy))
    link = stat.S_ISLNK(seen.st_mode)
    if not link and not stat.S_ISDIR(seen.st_mode):
        return None
    try:
        if link:
            fd = os.open(legacy, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0))
        else:
            fd = _open_a_folder(legacy)
    except OSError:
        if link:
            if _not_this_accounts(legacy):
                return _FormerFolder(legacy, seen, True)
        elif not os.path.lexists(legacy):
            return None
        else:
            _still_the_former_folder(_FormerFolder(legacy, seen, False))
        raise FormerFolderUnreadable(FORMER_FOLDER_UNREADABLE)
    try:
        _the_former_folder_walked(legacy, fd)
        opened = os.fstat(fd)
        if opened.st_uid != uid:
            if link:
                os.close(fd)
                return _FormerFolder(legacy, seen, True)
            raise FormerFolderRefused(errno.EPERM, FORMER_FOLDER_NOT_OURS, str(legacy))
        if not link and not os.path.samestat(opened, seen):
            raise FormerFolderBusy(FORMER_FOLDER_BUSY)
    except BaseException:
        os.close(fd)
        raise
    return _FormerFolder(legacy, seen, link, fd)


def _the_former_folder_walked(legacy, opened=None):
    """POSIX: a descriptor of the folder under the app's former name
    `legacy` (a link at its name followed), opened by the walk that judges
    its whole path as the data folder's is judged (_held_by_its_whole_path),
    so that whatever is read from it is read from the folder judged; the
    folder is left as it stands (no change of its mode). Where other
    accounts could change the path, FormerFolderNotCopied, as the move
    says it (_judge_the_former_folders_path), and nothing is opened; OSError
    as the walk raises it otherwise. Where `opened` is given (a descriptor
    of the folder opened at the name), the walk's own is only compared with
    it and closed: another folder than the one opened (_moved_on) fails
    closed, and None is returned."""
    try:
        walked = _held_by_its_whole_path(legacy, mend=False)
    except DataFolderRefused:
        raise FormerFolderNotCopied(errno.EPERM, FORMER_FOLDER_NOT_COPIED, str(legacy)) from None
    if opened is None:
        return walked
    try:
        same = os.path.samestat(os.fstat(walked), os.fstat(opened))
    finally:
        os.close(walked)
    if not same:
        raise _moved_on(legacy)
    return None


def _lock_the_former_folder(fd, wait):
    """An exclusive flock on the folder open at `fd`, asked without
    blocking and again after a pause that grows to a tenth of a second,
    `wait` seconds at most: FormerFolderBusy where it is held elsewhere past
    that; no lock, and nothing said, where the filesystem refuses flock for
    a reason other than a holder's."""
    deadline = _clock.monotonic() + max(0.0, wait)
    pause = 0.005
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            pass
        except OSError:
            return                      # a filesystem that refuses flock: no lock
        left = deadline - _clock.monotonic()
        if left <= 0:
            raise FormerFolderBusy(FORMER_FOLDER_BUSY)
        _clock.sleep(min(pause, left))
        pause = min(pause * 2, 0.1)


def _still_the_former_folder(former):
    """Nothing where the former name still leads to the object the launch
    first found there (`former.seen`: the same device and inode, a link
    not followed) and, for a link whose folder was opened, the link still
    to that folder; else raise (_moved_on)."""
    try:
        same = os.path.samestat(os.lstat(former.legacy), former.seen)
        if same and former.link and former.fd is not None:
            same = os.path.samestat(os.stat(former.legacy), os.fstat(former.fd))
    except OSError:
        same = False
    if not same:
        raise _moved_on(former.legacy)


def _moved_on(name):
    """The refusal for a name that no longer leads to the object the launch
    first found there: FormerFolderRefused where what stands there now is
    another account's (os.lstat, a link not followed), FormerFolderBusy for
    anything else -- another folder or link of this account's, or
    nothing."""
    try:
        theirs = os.lstat(name).st_uid != os.getuid()
    except OSError:
        theirs = False
    if theirs:
        return FormerFolderRefused(errno.EPERM, FORMER_FOLDER_NOT_OURS, str(name))
    return FormerFolderBusy(FORMER_FOLDER_BUSY)


def _move_the_former_folder(legacy, path, wait):
    """Move the former folder `legacy` to `path`, or copy it there where
    the move is refused, bound to the one object the name led to at the
    first look and holding its lock throughout (_the_former_folder_held).

    The owner was judged at the name before the folder was opened; the lock
    and its check were passed over where what was opened was another
    account's; the look was skipped where the name then led to another
    account's folder; and the move and the copy went by the name again.
    Where another account owns the folder above (a sticky folder of its
    own: it may rename or replace anything in it), it could put a folder of
    its own at the name at any of those moments; the sticky folder refused
    the move of that folder, and the copy published what it held as this
    account's data folder. Now the look reads the folder opened
    (_only_this_accounts_entries); the name is looked at again before the
    move, after a refused move, and before a copy is published
    (_still_the_former_folder); and the copy reads the folder opened, never
    its name (_copy_the_former_folder), so that a folder put at the name
    meanwhile is never read. Another account's at the name at any of those
    steps ends the move with FormerFolderRefused, and anything else there
    with FormerFolderBusy: no data folder is made, and the next launch asks
    again.

    The move is still one rename by name, atomic. Once made, the data
    folder is checked to be the object first found. Where it is not --
    something put at the name between the last look and the rename, which
    the rename then carried -- the launch raises as above and uses nothing
    of it. What was carried stands at `path`, where the next look judges it
    as the data folder (_keep_the_data_folder_ours): another account's is
    refused, and a folder of this account's there is one the account
    owning the folder above could as well have put at `path` itself. A
    sticky folder refuses the move of another account's folder, so that
    one goes no further than the check before the copy."""
    with _the_former_folder_held(legacy, wait) as former:
        # Asked again under the lock: a launch that held it before may have
        # moved the folder or published its copy.
        if former is None or path.exists():
            return
        if former.fd is not None:
            refusal = _only_this_accounts_entries(former.fd)
            if refusal is not None:
                raise refusal
        _still_the_former_folder(former)
        # One move, atomic on the one filesystem these two share; a copy only
        # if the move is refused, and then the old folder stays put rather
        # than leaving the charts in neither place.
        try:
            legacy.rename(path)
        except OSError:
            _still_the_former_folder(former)
            _copy_the_former_folder(legacy, path, former)
            return
        try:
            moved = os.path.samestat(os.lstat(path), former.seen)
        except OSError:
            moved = False
        if not moved:
            raise _moved_on(path)


def _open_a_folder(name, dir_fd=None):
    """A descriptor of the folder `name` -- relative to the folder open at
    `dir_fd`, where given -- opened without following a link: OSError for a
    link, or for anything else that is not a folder."""
    return os.open(name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
                   | getattr(os, "O_CLOEXEC", 0), dir_fd=dir_fd)


def _give_back_its_mode(folder, mode):
    """Put the mode `mode` back on the folder `folder` (a name, a link
    there followed, or a descriptor),
    as it stood before it was narrowed; a change the filesystem refuses
    leaves it as it is. A former folder that is not carried in stays as it
    was -- else, narrowed, it would read at the next launch as one never
    open to others, and be moved holding the links or other kinds of file
    the look refused in it."""
    try:
        os.chmod(folder, mode)
    except OSError:
        pass


def _only_this_accounts_entries(top):
    """None where every entry in the former folder open at the descriptor
    `top`, at every depth, is this account's, judged by what its name in
    its folder is (os.stat relative to the folder's descriptor: a link is
    never followed to look, it is judged by its own owner, the account
    that made it), and, where the folder was writable by its group or by
    others when it was found, each a regular file or a folder as well.

    The folder and each folder in it are narrowed to their owner before
    they are listed, whatever the mode of the folder above them (the folder
    itself made 0700, so that its owner can list it): a write
    another account could make in one after the look -- through the
    folder's name, or a descriptor of it opened before -- is then refused
    by the folder's own mode, so what the look found is what the move
    carries. Each is read through a descriptor: the folder through the one
    the launch opened and holds (_the_former_folder_held), never by its
    name, which another account may have pointed elsewhere since; each
    folder in it opened relative to the one above it without following a
    link, and judged by what was opened.

    Else the refusal to raise: FormerFolderUnreadable where the folder or a
    folder in it cannot be listed, FormerFolderNotCarried for anything else
    that stands there; each folder whose mode the narrowing changed is then
    given back exactly the mode it had, its setuid, setgid and sticky bits
    with it, so that the folder stays as it was (_give_back_its_mode).
    Windows, which holds no descriptor of a folder, makes no such look at a
    move, and makes it by name at a copy (_an_entry_is_not_this_accounts)."""
    uid = os.getuid()
    narrowed = []
    refusal = FormerFolderNotCarried(FORMER_FOLDER_NOT_CARRIED)

    def narrow(fd, whole=False):
        mode = _narrow_to_its_owner(fd, whole)
        if mode is not None:
            narrowed.append((fd, mode))
        return mode

    def look(fd):
        try:
            names = _list_through(fd)
        except OSError:
            return FormerFolderUnreadable(FORMER_FOLDER_UNREADABLE)
        folders = []
        for name in names:
            seen = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if seen.st_uid != uid:
                return refusal
            if stat.S_ISDIR(seen.st_mode):
                folders.append((name, seen))
            elif wide and not stat.S_ISREG(seen.st_mode):
                return refusal
        for name, seen in reversed(folders):
            try:
                inner = _open_a_folder(name, fd)
            except PermissionError:
                return FormerFolderUnreadable(FORMER_FOLDER_UNREADABLE)
            kept = False
            try:
                if not os.path.samestat(os.fstat(inner), seen):
                    return refusal
                kept = narrow(inner) is not None    # held open to be given its mode back
                found = look(inner)
            finally:
                if not kept:
                    os.close(inner)
            if found is not None:
                return found
        return None
    try:
        mode = narrow(top, whole=True)
        wide = mode is not None and bool(mode & 0o022)
        found = look(top)
    except (OSError, RecursionError):
        found = refusal
    if found is not None:
        for fd, mode in reversed(narrowed):
            _give_back_its_mode(fd, mode)
    for fd, _mode in narrowed:
        if fd != top:
            os.close(fd)
    return found


def _narrow_to_its_owner(path, whole=False, refuse=False):
    """Take from the folder `path` (a name, a link there followed, or a
    descriptor) any permission it
    gives the group or others, its owner's own bits left as they are -- or,
    where `whole`, make it 0700 exactly, so that its owner may read, write and
    search it (the data folder, and the former folder before
    it is looked at and moved: one its owner cannot list cannot be judged);
    a change of mode the filesystem refuses leaves it as it is. The mode it
    found, where that was changed; else None.

    On Windows (a name only; None) a folder whose access list gives anyone
    but this account, SYSTEM and Administrators anything
    (_windows_list_is_wider) is given the protected list the data folder is
    made with (_windows_close_the_list): the entries it inherited from above
    are dropped, from it and from everything in it, which then inherits the
    protected list. A file or folder in it that carries an entry of its own
    keeps it, and the folder's list does not shut it as a closed folder does
    on POSIX: Windows lets any account open a file by its path, below
    folders it may not enter, where the file's own list allows. The files
    the app writes are new files made in the folder, which take its list;
    one put there while the folder was wider keeps its own entries and its
    owner, and the app reads and writes through only its own (_whose); one
    of its own whose own entries let another account change it is set
    aside at the launch, unread (_set_aside_what_others_could_write). The
    look is one open and one reading of the list at
    each launch; a narrowing rewrites the inherited entries of everything in
    the folder, once. Where the list cannot be read or set (a volume that
    keeps no lists, a folder of Administrators' this account may not change)
    it is left as it is, and nothing is said, as a refused change of mode
    is -- but for the data folder (`refuse`): a change of its mode refused,
    or a list that could not be closed, refuses it (DataFolderNotClosed),
    and nothing is read from it or written in it. A list that could not be
    closed was only recorded, and a later save's new file took the folder's
    list, which other accounts could change.

    A folder of Administrators' or SYSTEM's whose list grants this account
    itself nothing (_windows_list_names_this_account) -- one a run as
    administrator made, which a run that is not elevated may not use -- is
    given the protected list too. Only a run as administrator can set it,
    so one such run repairs the folder; one that is not is refused the
    folder before, by the reading of its owner. A folder this account owns
    is not changed by this: OWNER RIGHTS grants it to its owner. Each is
    asked only once the folder's owner has been taken for this account's.

    Where the name is a junction or a link of this account's, the list set
    at the name was set on the junction itself, and the folder it leads to
    kept the entries it inherited -- from a drive's root, Modify for every
    account that can log on -- so that every file the app made there was one
    others could change, set aside at the next load: a user whose data folder
    is such a junction kept nothing. The folder it leads to
    (os.path.realpath) is judged and closed as well."""
    if not hasattr(os, "getuid"):
        for name in _the_name_and_the_folder_it_leads_to(path):
            try:
                if _windows_list_is_wider(name) or (
                        _owner_of(name) not in (None, _windows_this_account())
                        and not _windows_list_names_this_account(name)):
                    _windows_close_the_list(name)
            except OSError:
                if refuse:
                    raise DataFolderNotClosed(errno.EPERM, DATA_FOLDER_NOT_CLOSED, str(path)) from None
        return None
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except (OSError, ValueError):
        return None
    wanted = 0o700 if whole else mode & ~0o077
    if mode == wanted:
        return None
    try:
        os.chmod(path, wanted)
    except (OSError, ValueError):
        if refuse:
            raise DataFolderNotClosed(errno.EPERM, DATA_FOLDER_NOT_CLOSED, str(path)) from None
    return mode


def _the_name_and_the_folder_it_leads_to(path):
    """`path`, and the folder a junction or link there leads to where that
    is another (Windows, which sets a list given at a junction's name on the
    junction itself)."""
    names = [path]
    try:
        real = os.path.realpath(path)
        if os.path.normcase(real) != os.path.normcase(os.path.abspath(path)):
            names.append(Path(real))
    except (OSError, ValueError):
        pass
    return names


def _copy_the_former_folder(legacy, path, former):
    """The former folder the launch found and opened (`former`,
    _the_former_folder_held), copied whole to `path` when the move is
    refused, and published only once complete; the copy made as before
    (_copy_the_former_folder_by_name, whose history this keeps), but read
    through the folder opened, never by the name `legacy`.

    The copy read the former folder by its name, after the move by that
    name was refused: another account owning the folder above could put a
    folder of its own there first, and the copy published what it held.
    Now every entry is read through a descriptor: the folder through the
    one the launch opened and locked, each folder in it opened relative to
    the one above it without following a link, each entry's kind and owner
    read from what was opened (_copy_through); and the copy is compared
    with the former folder, whole, through the same descriptors
    (_copy_is_whole_through). A folder put at the name while the copy is
    made is never read, and the name is looked at again before the copy
    is published (_still_the_former_folder): anything but the folder first
    found there ends the move, and the copy is removed.

    The copy publishes regular files and folders of this account's only: a
    link, anything that is neither a regular file nor a folder, or an
    entry of another account's, anywhere in the former folder, keeps it
    from being published (FormerFolderNotCopied), as a copy that is not
    whole is kept: the former folder stays where it is, the copy is
    removed, and no data folder is made but where another launch has made
    one since (_not_copied_unless_made_since). Each file and folder is
    given its mode and times where the filesystem keeps them; a change it
    refuses is passed over, and the copy is still whole.

    The copy is made in a folder of its own beside `path`,
    `.<name>.<16 hex>.incoming`, made owner-only and held by a lock
    (flock, where the system has it) from its making to its end, so that a
    later launch can tell one a launch killed on the way left from one
    still being made (_remove_dead_copies). Beside the copy it holds the
    record of the folder the copy is made from, its device and inode
    (_record_the_source), which the copy does not publish: a copy a killed
    launch left is removed once that folder has become the data folder,
    though the former name is then gone. The copy is the folder `copy`
    in it, narrowed to its owner before it is published by its rename to
    `path` -- a rename from the folder this launch holds, so that what is
    published is the copy made -- only while there is still nothing at
    `path`: a folder another launch has made in the meantime, and anything
    saved into it, is never written over. Then the folder it was made in
    is removed, through its descriptor.

    A link of this account's at the former name is carried as the move
    carries it: a link naming what it names is made at `path`, where the
    folder it leads to is judged and narrowed as the data folder; nothing
    is read through it, and the link read is the one first found
    (_read_the_link)."""
    if former.link:
        target = _read_the_link(former)
        _still_the_former_folder(former)
        if target is not None:
            try:
                os.symlink(target, path, target_is_directory=True)
                return
            except OSError:
                pass                    # a name taken since the look, or no link to be made
        _not_copied_unless_made_since(path)
        return
    for _attempt in range(64):
        holder = path.with_name(f".{path.name}.{secrets.token_hex(8)}.incoming")
        try:
            os.mkdir(holder, 0o700)
        except FileExistsError:
            continue                    # a name already there: another's, never written into
        except OSError:
            break
        held = _hold_a_new_folder(holder)
        if held is _COPY_TAKEN:
            continue                    # taken by a later launch, or not the folder made: not written into
        if held is None:
            break
        try:
            if _make_and_publish_the_copy(former, held, path):
                return
        finally:
            _remove_through(held, holder)
            os.close(held)
        break
    _not_copied_unless_made_since(path)


def _read_the_link(former):
    """What the link the launch found at the former name (`former`, a
    _FormerFolder) names; None where it cannot be read. The link was read
    by its name and then looked at again, so a link swapped in for the read
    and swapped back passed, and what the other link named became the data
    folder's link; looks by the whole path passed too where the folder
    above itself was swapped for the read, the link never touched. Now the
    link is read through a descriptor bound to it. Where the system can
    open a link itself (O_PATH), the link at the name is opened without
    following it, must be the link first found (os.fstat, its device and
    inode), and is read through that descriptor: a link's text never
    changes, so what is read is what the link first found names. Elsewhere
    (macOS) the folder above is opened once, and the link is looked at and
    read by its name relative to that descriptor: before the read it must
    be the link first found; after it, the same device, inode and change
    time (st_ctime_ns), since a link moved away and back sets its change
    time. Anything else raises (_moved_on), and no link is made.

    The link bound was identified by its device and inode alone: where the
    owner of the folder above put a link of its own at the name and the
    filesystem gave it the freed inode of the user's, the read took it.
    The owner of what is bound is now asked at every look as well -- the
    descriptor's, or the link's relative to the folder above, before and
    after the read -- and another account's ends the move with
    FormerFolderRefused."""
    flags = getattr(os, "O_CLOEXEC", 0)
    o_path = getattr(os, "O_PATH", None)
    try:
        if o_path is not None:
            bound = os.open(former.legacy, o_path | getattr(os, "O_NOFOLLOW", 0) | flags)
        else:
            bound = os.open(former.legacy.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | flags)
    except OSError:
        raise _moved_on(former.legacy) from None
    try:
        name, dir_fd = ("", bound) if o_path is not None else (former.legacy.name, bound)
        try:
            before = os.fstat(bound) if o_path is not None else os.lstat(name, dir_fd=dir_fd)
            same = os.path.samestat(before, former.seen)
        except OSError:
            same = False
        if not same:
            raise _moved_on(former.legacy)
        if not _ours(before.st_uid):
            raise FormerFolderRefused(errno.EPERM, FORMER_FOLDER_NOT_OURS, str(former.legacy))
        try:
            target = os.readlink(name, dir_fd=dir_fd)
        except OSError:
            target = None
        if o_path is None:
            try:
                after = os.lstat(name, dir_fd=dir_fd)
                same = ((after.st_dev, after.st_ino, after.st_ctime_ns)
                        == (before.st_dev, before.st_ino, before.st_ctime_ns))
            except OSError:
                same = False
            if not same:
                raise _moved_on(former.legacy)
            if not _ours(after.st_uid):
                raise FormerFolderRefused(errno.EPERM, FORMER_FOLDER_NOT_OURS, str(former.legacy))
        return target
    finally:
        os.close(bound)


def _hold_a_new_folder(holder):
    """A descriptor of the folder `holder` this launch has just made for a
    copy, opened without following a link and locked (flock, where the
    system has it; none where the filesystem refuses it); _COPY_TAKEN where
    a later launch holds it already, or the name no longer leads to an
    empty folder of this account's (one put there since, never written
    into); None where it cannot be opened."""
    try:
        fd = _open_a_folder(holder)
    except FileNotFoundError:
        return _COPY_TAKEN
    except OSError:
        return None
    try:
        if os.fstat(fd).st_uid != os.getuid() or os.listdir(fd):
            os.close(fd)
            return _COPY_TAKEN
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return _COPY_TAKEN
    except OSError:
        pass                            # no lock to be had: the copy is made without one
    return fd


def _make_and_publish_the_copy(former, held, path):
    """Copy the former folder open at `former.fd` into a folder `copy` in
    the folder open at `held`, compare it whole, and rename it to `path`
    while nothing stands there; True where it was published. Raises where
    the former name no longer leads to the folder first found
    (_still_the_former_folder)."""
    _record_the_source(held, former.seen)
    try:
        os.mkdir(_COPY_NAME, 0o700, dir_fd=held)
        copy = _open_a_folder(_COPY_NAME, held)
    except OSError:
        return False
    try:
        try:
            _copy_through(former.fd, copy)
            whole = _copy_is_whole_through(copy, former.fd)
        except (OSError, RecursionError):
            whole = False
        if not whole:
            return False
        try:
            os.chmod(copy, 0o700)
        except OSError:
            pass                        # a filesystem that keeps no modes
        _still_the_former_folder(former)
        try:
            if not os.path.lexists(path):
                # os.rename refuses a folder that holds anything, so a folder
                # made and written in since this look is still not written over.
                os.rename(_COPY_NAME, path, src_dir_fd=held)
                return True
        except OSError:
            pass
        return False
    finally:
        os.close(copy)


# The folder in a copy's own folder (_copy_the_former_folder) that holds the
# copy, and is renamed to the data folder's name to publish it; and the file
# beside it that records the folder the copy is made from.
_COPY_NAME = "copy"
_RECORD_NAME = "source"


def _record_the_source(held, seen):
    """Write, in the copy's own folder open at `held`, the record of the
    folder the copy is made from: its device and inode (`seen`, what the
    launch first found at the former name), one line, `<device> <inode>`.
    A record that cannot be written is passed over: a copy left without one
    is kept, as before (_a_dead_copy_that_goes)."""
    try:
        fd = os.open(_RECORD_NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_CLOEXEC", 0), 0o600, dir_fd=held)
    except OSError:
        return
    try:
        os.write(fd, f"{seen.st_dev} {seen.st_ino}\n".encode("ascii"))
    except OSError:
        pass
    finally:
        os.close(fd)


def _the_recorded_source(held):
    """The device and inode the record in the copy's own folder open at
    `held` names (_record_the_source); None where it cannot be read: no
    record, a link or anything but a regular file of this account's there,
    or not the one line a record holds."""
    try:
        fd = os.open(_RECORD_NAME, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                     | getattr(os, "O_CLOEXEC", 0), dir_fd=held)
    except OSError:
        return None
    try:
        seen = os.fstat(fd)
        if not stat.S_ISREG(seen.st_mode) or seen.st_uid != os.getuid():
            return None
        text = os.read(fd, 64)
    except OSError:
        return None
    finally:
        os.close(fd)
    found = re.fullmatch(rb"([0-9]+) ([0-9]+)\n", text)
    return (int(found[1]), int(found[2])) if found else None


def _copy_the_former_folder_by_name(legacy, path):
    """The folder under the app's former name, copied whole to `path` when
    it cannot be moved there, and published only once complete -- by name,
    as before, where the system holds no descriptor of a folder to read
    through (Windows), the former folder's owner judged before the copy is
    published; elsewhere the copy is read
    through the folder the launch opened (_copy_the_former_folder). What
    follows is this copy's history, which that one keeps.

    The copy was made at
    `path` itself, which existed from its first file on. A second launch
    took the half-made folder for the app's own, saved into it under the
    store's lock, and the copy's next file -- the old store -- went over that
    save. The copy is now made in a folder of its own beside `path`, and
    renamed to `path` whole, only while there is still no folder of the
    app's there: a folder another launch has made in the meantime, and
    anything saved into it, is never written over. A copy not published is
    removed; it is a copy, and the former folder keeps every file it was
    made from.

    A copy some of whose files could not be copied (a file this account may
    not read, a pipe) is not published: the preferences left out of such a
    copy were read from no file after it, and nothing said so. The former
    folder stays where it is, the copy is removed, and FormerFolderNotCopied
    is raised, so that no folder is made at `path` and the next launch (or
    the next look at the folder, data_folder_state) tries the move again. A
    copy that holds every file and folder whole, where what copytree could
    not copy was only a mode or a time (a filesystem that keeps no modes
    refuses them), is the whole copy, and is published (_copy_is_whole).

    The copy publishes regular files and folders only. A link carried into
    the copy as a link was published in the data folder, leading out of
    it, and the saves followed it to wherever it led. Now a link anywhere
    in the former folder, or anything else that is neither a regular file
    nor a folder (a pipe, a device), keeps the copy from being published,
    as a copy that is not whole is kept: the former folder stays where it
    is, the copy is removed, and FormerFolderNotCopied is raised. The former
    folder is looked at before the copy, so that nothing but its regular
    files and folders is copied, and the copy and the former folder again
    after it, so that one put in the former folder while the copy was made
    is found too (_only_files_and_folders); no link is followed to look. A
    link at the former folder's own name is carried as the move carries
    it: a link naming what it names is made at `path`, and the folder it
    leads to is the data folder, judged and narrowed as one; nothing is
    copied. The move of a former folder of this account's is unchanged,
    and carries the links the account keeps in it, as its own.

    Every file a copy makes is the user's, so another account's store copied
    in was read as the user's own, its owner gone. Where any entry in the
    former folder is not this account's (_an_entry_is_not_this_accounts) nothing
    is copied, or published where one came to stand there during the copy:
    FormerFolderNotCarried, and no data folder is made.

    The copy is made owner-only, and narrowed again after copytree, which
    gives it the former folder's mode at its end, before it takes the data
    folder's name. On Windows its folder is given the protected list before
    anything is copied into it, as a data folder made is, so that what is
    copied takes it. The former folder's owner is judged again before then
    (_former_folder_not_this_accounts): a folder another account put at the
    name while the copy was made ends it with FormerFolderRefused, the copy
    removed.

    A file whose copy failed part way was
    published cut short -- the store's, which the load then copied aside
    and named as "the original file" -- and one whose copy failed before
    its first byte was simply missing, the load listing no chart and saying
    nothing. A copy that failed in any other way (copytree's own error, a
    folder for the copy that could not be made, a link at the former name
    that could not be made, a copy that could not take the name) published
    nothing and said nothing, and an empty data folder was then made while the
    former folder held the charts. Every copy is now compared with the
    former folder before it is published, whether or not copytree raised,
    so that a file cut short or missing, or one put in the former folder
    while the copy was made, keeps it from being published
    (_copy_is_whole); and a copy that failed in any way raises
    FormerFolderNotCopied as one not whole does, but where a folder now
    stands at `path` that another launch made in the meantime: that folder
    is the app's own, and is left to be used as it is -- after a copy that
    was not whole as after any other failure (_not_copied_unless_made_since).
    The copy
    is made in a folder this launch holds a lock on (flock, where the
    system has it) from its making to its end, so that a later launch can
    tell a copy left by a launch killed on the way -- which used to stay
    beside the data folder for good -- from one still being made
    (_remove_dead_copies)."""
    if os.path.islink(legacy):
        try:
            os.symlink(os.readlink(legacy), path, target_is_directory=True)
        except OSError:
            _not_copied_unless_made_since(path)     # a name taken since the look, or no link to be made
        return
    if _an_entry_is_not_this_accounts(legacy):
        raise FormerFolderNotCarried(FORMER_FOLDER_NOT_CARRIED)
    if _only_files_and_folders(legacy) is None:
        _not_copied_unless_made_since(path)
        return
    for _attempt in range(64):
        staging = path.with_name(f".{path.name}.{secrets.token_hex(8)}.copying")
        try:
            # Made owner-only; copytree gives it the former folder's mode at
            # its end, and it is narrowed again before it is published.
            os.mkdir(staging, 0o700)
        except FileExistsError:
            continue                    # a name already there: another's, never written into
        except OSError:
            break
        if not hasattr(os, "getuid"):
            try:
                # Given the protected list before anything is copied in,
                # so that what is copied takes it, as in a made data folder.
                _windows_close_the_list(staging)
            except OSError:
                pass                    # a volume that keeps no lists
        held = _hold_a_copy(staging)
        if held is _COPY_TAKEN:
            continue                    # a later launch took it for a dead copy: it is that launch's to remove
        try:
            try:
                shutil.copytree(legacy, staging, symlinks=True, dirs_exist_ok=True,
                                copy_function=_copy_a_file_by_name)
            except OSError:
                pass                    # shutil.Error among them: the copy is judged below, as every copy is
            if _copy_is_whole(staging, legacy):
                try:
                    os.chmod(staging, 0o700)
                except OSError:
                    pass                # a filesystem that keeps no modes
                if _former_folder_not_this_accounts(legacy):
                    # Another account's folder put at the name while the copy
                    # was made: what was copied may be its.
                    shutil.rmtree(staging, ignore_errors=True)
                    raise FormerFolderRefused(errno.EPERM, FORMER_FOLDER_NOT_OURS, str(legacy))
                if _an_entry_is_not_this_accounts(legacy):
                    shutil.rmtree(staging, ignore_errors=True)
                    raise FormerFolderNotCarried(FORMER_FOLDER_NOT_CARRIED)
                try:
                    if not os.path.lexists(path):
                        # os.rename refuses a folder that holds anything (and on
                        # Windows any folder at all), so a folder made and
                        # written in since this look is still not written over.
                        os.rename(staging, path)
                        return
                except OSError:
                    pass
            shutil.rmtree(staging, ignore_errors=True)
            break
        finally:
            if held is not None:
                os.close(held)
    _not_copied_unless_made_since(path)


def _copy_a_file_by_name(src, dst):
    """The copy of one file copytree makes (_copy_the_former_folder_by_name),
    under the bounds the copy through descriptors keeps (_copy_a_file): the
    file at `src` opened without following a link (where the system can
    refuse one) and judged as opened -- a file the app reads that another
    account could change is not copied (_Exposed), nor one past a store's
    limit or the launch's, nor one that grows while it is copied -- then its
    bytes written to a new file at `dst`, and its times and read-only flag
    given it. OSError where it is not copied: copytree gathers it, and the
    copy, not whole, is not published."""
    one = _open_regular_file(src, follow_links=False)
    try:
        opened = os.fstat(one)
        if _READ_NAME.fullmatch(os.path.basename(src)) and _exposed_as_opened(one, src):
            raise _Exposed(errno.EPERM, os.strerror(errno.EPERM), str(src))
        _within_the_launch(opened.st_size)
        out = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        try:
            _copy_within_bounds(one, out, opened.st_size)
        finally:
            os.close(out)
    finally:
        os.close(one)
    try:
        shutil.copystat(src, dst, follow_symlinks=False)
    except OSError:
        pass
    return dst


def _not_copied_unless_made_since(path):
    """After a copy of the former folder that was not published: raise
    FormerFolderNotCopied, so that no data folder is made at `path` while
    the former folder holds the charts -- unless something stands at `path`
    now, which another launch made in the meantime: that folder is the
    app's own, and is left to be used (or judged) as it is. A copy that was
    not whole is no exception: with another launch's folder standing, this
    launch uses it rather than refusing once."""
    if not os.path.lexists(path):
        raise FormerFolderNotCopied(FORMER_FOLDER_NOT_COPIED)


# What _hold_a_copy gives back for a copy's folder another launch holds, or
# that is no longer the folder named.
_COPY_TAKEN = object()


def _hold_a_copy(staging):
    """A descriptor of the copy's folder `staging` with an exclusive flock
    on it, held while the copy is made (or while a dead copy is removed);
    _COPY_TAKEN where another launch holds it or the name no longer leads to
    it; None where no lock can be had (no flock on this system, or a
    filesystem that refuses it on a folder)."""
    if fcntl is None:
        return None
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(staging, flags)
    except FileNotFoundError:
        return _COPY_TAKEN
    except OSError:
        return None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return _COPY_TAKEN
    except OSError:
        os.close(fd)
        return None
    try:
        if os.path.samestat(os.fstat(fd), os.lstat(staging)):
            return fd
    except OSError:
        pass
    os.close(fd)
    return _COPY_TAKEN


class NotAPlainFile(OSError):
    """What stands at a name the
    app reads is not a regular file -- a pipe, a device, a directory -- or
    is a file past the bound its reader sets. It is not read."""


def _open_regular_file(path, follow_links=True):
    """A descriptor, open for reading, of the regular file at `path` (a
    link followed, unless `follow_links` is False, where the system's open
    can refuse one); NotAPlainFile for anything else. The name is opened
    without waiting (O_NONBLOCK) and judged by what was opened."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
    if not follow_links:
        flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = _open(path, flags)
    try:
        regular = stat.S_ISREG(os.fstat(fd).st_mode)
        if not follow_links and not hasattr(os, "O_NOFOLLOW"):
            # Windows opens through a link or junction at the name: one
            # standing there as the file is opened is not read through.
            seen = _lstat(path)
            if stat.S_ISLNK(seen.st_mode) or getattr(seen, "st_reparse_tag", 0) in _WINDOWS_LINK_TAGS:
                raise _Exposed(_ELOOP, os.strerror(_ELOOP), str(path))
    except BaseException:
        os.close(fd)
        raise
    if not regular:
        os.close(fd)
        raise NotAPlainFile(errno.EINVAL, "not a regular file", str(path))
    return fd


def _open_this_accounts_file(path):
    """A descriptor, open for reading, of the regular file at `path` in the
    data folder, where it is this account's: the name judged first, by its
    own owner (_whose, a link there not followed), then what was opened, by
    its owner read through the descriptor (_opened_is_ours). No link at the
    name is followed (below). _NotThisAccounts where either is another
    account's, and nothing is read; NotAPlainFile, as _open_regular_file,
    for anything but a regular file.

    A file of this account's that another account could change was read as
    the user's: one an older version left 0666, the target of the user's own
    link that others may write, one on Windows whose own list lets another
    account write it. What was opened is now judged as well
    (_exposed_as_opened), and such a file is _Exposed, and nothing of it is
    read.

    A link of this account's at the name was followed one hop, to one file
    of the user's in a folder no other account could write in; but the
    folders between were never judged, so another account that could write
    in one of them could put another of the user's files at the end of the
    link, which the load read and the save wrote over. A link at the name,
    whoever made it and wherever it leads, is now never followed: _Exposed
    (the page says the app does not follow it), and nothing is read. The
    name is opened without following a link (O_NOFOLLOW; on Windows a link
    or junction found at the name is refused, _open_regular_file)."""
    whose = _whose(path)
    if whose == _ANOTHERS:
        raise _NotThisAccounts(errno.EPERM, os.strerror(errno.EPERM), str(path))
    if whose in (_OUR_LINK, _LEADS_TO_ANOTHERS):
        raise _Exposed(errno.EPERM, os.strerror(errno.EPERM), str(path))
    fd = _open_regular_file(path, follow_links=False)
    try:
        if not _opened_is_ours(fd):
            raise _NotThisAccounts(errno.EPERM, os.strerror(errno.EPERM), str(path))
        if _exposed_as_opened(fd, path):
            raise _Exposed(errno.EPERM, os.strerror(errno.EPERM), str(path))
    except BaseException:
        os.close(fd)
        raise
    return fd


def _same_bytes(a, b, follow_links=True):
    """Whether `a` and `b` are regular files holding the same bytes; False
    when either is anything else -- a pipe, a device, a folder, and where
    `follow_links` is False a link -- or cannot be read. Each is opened without waiting (O_NONBLOCK: a pipe opens at
    once, with no writer) and judged by what was opened, as the store's
    reader judges (_read_regular_file), so that no comparison waits on a
    pipe for ever."""
    try:
        one = _open_regular_file(a, follow_links)
    except OSError:
        return False
    try:
        other = _open_regular_file(b, follow_links)
    except OSError:
        os.close(one)
        return False
    return _same_open_bytes(one, other)


def _same_open_bytes(one, other):
    """Whether the regular files open at the descriptors `one` and `other`
    hold the same bytes; False where either cannot be read. Both are
    closed."""
    with os.fdopen(one, "rb") as one, os.fdopen(other, "rb") as other:
        try:
            if os.fstat(one.fileno()).st_size != os.fstat(other.fileno()).st_size:
                return False
            while True:
                left, right = one.read(1 << 20), other.read(1 << 20)
                if left != right:
                    return False
                if not left:
                    return True
        except OSError:
            return False


def _same_link(a, b):
    """Whether `a` and `b` are both links, naming the same thing."""
    try:
        return os.path.islink(a) and os.path.islink(b) and os.readlink(a) == os.readlink(b)
    except OSError:
        return False


def _copy_through(src, dst):
    """Copy every entry in the folder open at the descriptor `src`, at
    every depth, into the folder open at `dst`: each judged by what its
    name in its folder is (os.stat relative to the folder's descriptor, a
    link not followed) and by what was opened -- each folder opened
    relative to the one above it without following a link, each file
    likewise (_open_the_file_within) -- and given its mode and times where
    the filesystem keeps them. OSError (NotAPlainFile, PermissionError)
    where anything there is not a regular file or a folder of this
    account's, or is not what its name showed, or where a read or a write
    fails."""
    uid = os.getuid()
    for name in _list_through(src):
        seen = os.stat(name, dir_fd=src, follow_symlinks=False)
        if seen.st_uid != uid:
            raise PermissionError(errno.EPERM, os.strerror(errno.EPERM), name)
        if stat.S_ISREG(seen.st_mode):
            _copy_a_file(src, dst, name, seen)
        elif not stat.S_ISDIR(seen.st_mode):
            raise NotAPlainFile(errno.EINVAL, "not a regular file", name)
        else:
            inner = _open_a_folder(name, src)
            try:
                opened = os.fstat(inner)
                if opened.st_uid != uid or not os.path.samestat(opened, seen):
                    raise NotAPlainFile(errno.EINVAL, "not the folder its name showed", name)
                os.mkdir(name, 0o700, dir_fd=dst)
                outer = _open_a_folder(name, dst)
                try:
                    _copy_through(inner, outer)
                    _give_it_the_same(outer, opened)
                finally:
                    os.close(outer)
            finally:
                os.close(inner)


def _copy_a_file(src, dst, name, seen):
    """Copy the regular file `name` in the folder open at `src` (what its
    name showed: `seen`) to a new file of that name in the folder open at
    `dst`, the owner's part of its mode and its times with it where the
    filesystem keeps them.

    A file the app reads that its group or others could write, at its name
    or as opened, is not copied: its bytes may be another account's, and a
    launch copies none of those (_Exposed). Nor is a file past a store's own
    limit, or past what one launch copies, or one that grows while it is
    copied: the copy read every file to its end, so a sparse file another
    account lengthened cost its full size on the disk at the launch
    (NotAPlainFile, EFBIG). Each refusal leaves the copy not whole: it is not
    published, and the former folder stays where it is, as one that could
    not be copied whole (FormerFolderNotCopied)."""
    one = _open_the_file_within(src, name, seen)
    try:
        opened = os.fstat(one)
        if _READ_NAME.fullmatch(name) and (_wide(seen) or _wide(opened)):
            raise _Exposed(errno.EPERM, os.strerror(errno.EPERM), name)
        _within_the_launch(opened.st_size)
        out = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                      | getattr(os, "O_CLOEXEC", 0), 0o600, dir_fd=dst)
        try:
            _copy_within_bounds(one, out, opened.st_size)
            _give_it_the_same(out, seen)
        finally:
            os.close(out)
    finally:
        os.close(one)


def _open_the_file_within(folder, name, seen):
    """A descriptor, open for reading, of the file `name` in the folder
    open at `folder`, opened without following a link and without waiting;
    NotAPlainFile where what was opened is not a regular file of this
    account's, or not the one its name showed (`seen`)."""
    fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
                 | getattr(os, "O_CLOEXEC", 0), dir_fd=folder)
    try:
        opened = os.fstat(fd)
    except OSError:
        os.close(fd)
        raise
    if not stat.S_ISREG(opened.st_mode) or opened.st_uid != os.getuid() or not os.path.samestat(opened, seen):
        os.close(fd)
        raise NotAPlainFile(errno.EINVAL, "not a regular file", name)
    return fd


def _give_it_the_same(fd, seen):
    """Give the file or folder open at `fd` the owner's part of the mode in
    `seen` (its group's and others' never carried) and the times in `seen`;
    a change the filesystem refuses is passed over."""
    try:
        os.chmod(fd, stat.S_IMODE(seen.st_mode) & 0o700)
    except OSError:
        pass
    try:
        os.utime(fd, ns=(seen.st_atime_ns, seen.st_mtime_ns))
    except OSError:
        pass


def _copy_is_whole_through(copy, top):
    """Whether everything in the former folder open at the descriptor
    `top` is in the copy open at `copy`, at the same place -- each folder a
    folder, each file a regular file with the same bytes -- and the copy
    holds nothing but regular files and folders; False where either holds
    anything else or cannot be looked at. Read through descriptors, as the
    copy was made (_copy_through)."""
    try:
        return _the_same_within(top, copy)
    except (OSError, RecursionError):
        return False


def _the_same_within(there, here):
    """_copy_is_whole_through's comparison, one folder at a time."""
    uid = os.getuid()
    copied = set(_list_through(here))
    for name in copied:
        kind = os.stat(name, dir_fd=here, follow_symlinks=False).st_mode
        if not (stat.S_ISDIR(kind) or stat.S_ISREG(kind)):
            return False
    for name in _list_through(there):
        if name not in copied:
            return False
        one = os.stat(name, dir_fd=there, follow_symlinks=False)
        other = os.stat(name, dir_fd=here, follow_symlinks=False)
        if one.st_uid != uid:
            return False
        if stat.S_ISREG(one.st_mode) and stat.S_ISREG(other.st_mode):
            a = _open_the_file_within(there, name, one)
            try:
                b = _open_the_file_within(here, name, other)
            except OSError:
                os.close(a)
                raise
            if not _same_open_bytes(a, b):
                return False
        elif stat.S_ISDIR(one.st_mode) and stat.S_ISDIR(other.st_mode):
            a = _open_a_folder(name, there)
            try:
                b = _open_a_folder(name, here)
                try:
                    if not (os.path.samestat(os.fstat(a), one) and os.path.samestat(os.fstat(b), other)
                            and _the_same_within(a, b)):
                        return False
                finally:
                    os.close(b)
            finally:
                os.close(a)
        else:
            return False
    return True


def _remove_through(fd, name):
    """Remove the folder open at the descriptor `fd`, only while the name
    `name` still leads to it (os.path.samestat, a link not followed):
    everything in it, each entry relative to its folder's descriptor and
    no link followed (_empty_through), then the folder, where the name
    still leads to it. Where another folder stands at the name -- one the
    account owning the folder above has put there since -- nothing is
    removed; one put there after that first look is never emptied either,
    as the emptying reads `fd` alone, never the name. What cannot be
    removed is left."""
    try:
        if not os.path.samestat(os.fstat(fd), os.lstat(name)):
            return
    except OSError:
        return
    _empty_through(fd)
    try:
        if os.path.samestat(os.fstat(fd), os.lstat(name)):
            os.rmdir(name)
    except OSError:
        pass


def _empty_through(fd):
    """Remove everything in the folder open at `fd`, at every depth, each
    folder in it opened without following a link and given its owner's
    bits so that it can be emptied; what cannot be removed is left."""
    try:
        names = _list_through(fd)
    except OSError:
        return
    for name in names:
        try:
            seen = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(seen.st_mode):
                inner = _open_a_folder(name, fd)
                try:
                    if os.path.samestat(os.fstat(inner), seen):
                        try:
                            os.chmod(inner, stat.S_IMODE(seen.st_mode) | 0o700)
                        except OSError:
                            pass
                        _empty_through(inner)
                finally:
                    os.close(inner)
                os.rmdir(name, dir_fd=fd)
            else:
                os.unlink(name, dir_fd=fd)
        except (OSError, RecursionError):
            pass


def _copy_is_whole(staging, legacy):
    """Whether everything in the former folder `legacy` is in the copy
    `staging`, at the same place -- each folder a folder, each file a
    regular file with the same bytes; False where either holds anything
    else (a link, a pipe, a device), which no copy publishes, or cannot be
    looked at. No link is followed to look."""
    there = _only_files_and_folders(legacy)
    if there is None or _only_files_and_folders(staging) is None:
        return False
    try:
        for name, folder in there.items():
            here = os.path.join(staging, name)
            if folder:
                if not stat.S_ISDIR(os.lstat(here).st_mode):
                    return False
            elif not _same_bytes(os.path.join(legacy, name), here, follow_links=False):
                return False
    except OSError:
        return False
    return True


def _an_entry_is_not_this_accounts(top):
    """Whether anything in the folder `top`, at every depth, is another
    account's, judged by its owner at its name (a link, on Windows a junction
    too, by its own, not followed), or has an owner that cannot be read, as
    _only_this_accounts_entries takes one. A folder in it that cannot be
    listed is not looked into: _only_files_and_folders refuses that copy."""
    try:
        for root, dirs, files in os.walk(top):
            for name in dirs + files:
                if not _ours(_owner_of_the_name(os.path.join(root, name))):
                    return True
    except (OSError, ValueError):
        return True
    return False


def _only_files_and_folders(top):
    """The names in the folder `top`, at every depth, each relative to it,
    mapped to True for a folder and False for a regular file; None where
    anything else stands there -- a link (never followed to look; on
    Windows a junction too), a pipe, a device -- or where a folder in it
    cannot be listed."""
    found = {}
    isjunction = getattr(os.path, "isjunction", None)

    def refuse(exc):
        raise exc
    try:
        for root, dirs, files in os.walk(top, onerror=refuse):
            for name in dirs + files:
                where = os.path.join(root, name)
                mode = os.lstat(where).st_mode
                if stat.S_ISDIR(mode) and isjunction is not None and isjunction(where):
                    return None
                if stat.S_ISDIR(mode) or stat.S_ISREG(mode):
                    found[os.path.relpath(where, top)] = stat.S_ISDIR(mode)
                else:
                    return None
    except OSError:
        return None
    return found


def _only_a_copy_through(held, former, name=None, closed=False):
    """Whether everything in the copy held open at the descriptor `held`
    (or, where `name` is given, in its folder of that name) is in the
    former folder `former` -- the one the cleanup judged and opened
    (_remove_dead_copies) -- at the same place: each file with the same
    bytes (a link there followed: a copy an earlier version made held the
    bytes a link led to), each link naming the same thing; so that
    removing it loses nothing. False for anything else, and where no former
    folder of this account's was opened (`former` None, or a link to
    another account's folder): nothing is then read. The copy is read
    through its descriptor, each entry relative to its folder's and no link
    in it followed, never by its name, which another account owning the
    folder above may have given to another folder since it was held; the
    former folder through the descriptor the cleanup opened, never its
    name. A copy that is the former folder itself -- the folder opened,
    given a dead copy's name since -- is never a copy of it. Where
    `closed`, every folder and file it opens in the copy must be this
    account's and writable by no other (_none_else_writes), read from its
    own descriptor before it is listed or read: else False, and nothing in
    it is read."""
    if former is None or former.fd is None:
        return False
    try:
        here = held if name is None else _open_a_folder(name, held)
        try:
            if os.path.samestat(os.fstat(here), os.fstat(former.fd)):
                return False
            return _only_a_copy_within(here, former.fd, closed)
        finally:
            if here != held:
                os.close(here)
    except (OSError, RecursionError):
        return False


def _only_a_copy_within(here, there, closed=False):
    """_only_a_copy_through's comparison, one folder at a time."""
    for name in os.listdir(here):
        mine = os.stat(name, dir_fd=here, follow_symlinks=False)
        if stat.S_ISLNK(mine.st_mode):
            if os.readlink(name, dir_fd=here) != os.readlink(name, dir_fd=there):
                return False
        elif stat.S_ISDIR(mine.st_mode):
            inner = _open_a_folder(name, here)
            try:
                opened = os.fstat(inner)
                if not os.path.samestat(opened, mine) or (closed and not _none_else_writes(opened)):
                    return False
                other = os.open(name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
                                dir_fd=there)
                try:
                    if not _only_a_copy_within(inner, other, closed):
                        return False
                finally:
                    os.close(other)
            finally:
                os.close(inner)
        elif stat.S_ISREG(mine.st_mode):
            one = _open_the_file_within(here, name, mine)
            try:
                writable_by_none_else = not closed or _none_else_writes(os.fstat(one))
            except OSError:
                os.close(one)
                raise
            if not writable_by_none_else:
                os.close(one)
                return False
            try:
                other = os.open(name, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0),
                                dir_fd=there)
            except OSError:
                os.close(one)
                raise
            if not stat.S_ISREG(os.fstat(other).st_mode):
                os.close(one)
                os.close(other)
                return False
            if not _same_open_bytes(one, other):
                return False
        else:
            return False
    return True


def _remove_dead_copies(path, legacy):
    """A copy of the former folder left
    beside the data folder `path` by a launch killed while making it is
    removed: only one no launch holds any more (_hold_a_copy), and only
    while it is nothing but a copy of what the former folder `legacy`
    still holds -- for a copy in its own folder
    (`.<name>.<16 hex>.incoming`, _copy_the_former_folder) the folder
    `copy` in it, and that folder of this account's and owner-only, as
    made (_a_dead_copy_that_goes); for one an earlier version made
    (`.<name>.<16 hex>.copying`) the folder itself, and that folder of this
    account's, and it and every folder and file the comparison opens in it
    writable by no other account (_held_copy_is_ours, _none_else_writes).
    An earlier version's copy was compared whatever its owner and mode:
    another account owning the folder above could make one open to all, put
    in it a link guessing where a link in the reader's private former
    folder leads, and learn from its removal that the guess was right; and
    in a copy of the reader's that others may enter, a folder in it they
    may write in would do as well. One that is another account's, or that
    holds anything another account could write in, is now left unread and
    kept, as another account's things are; one others may only read (as
    copytree gave it the former folder's mode) is compared, and removed
    where it matches. On macOS, where another account's write through an
    access list does not show in the mode, every such copy is kept, never
    compared or removed. Each is judged and
    removed through the descriptor that holds it (_only_a_copy_through,
    _remove_through), never by its name: where the account owning the
    folder above gives that name to a folder of the reader's between the
    judgement and the removal, nothing of that folder is removed.

    Once another launch had moved the former folder to `path`, the former
    name was gone, nothing could show a copy to be nothing but a copy of
    it, and a copy a launch killed during that move left stayed for good,
    the saved charts in it. A copy in its own folder records the folder it
    was made from (_record_the_source); where the former name is gone and
    that folder is now the data folder (the same device and inode at
    `path`), it is removed. One still being made, one holding anything the
    former folder does not, one whose record cannot be read or names
    another folder, every one an earlier version made once the former name
    is gone, and every one where no lock can tell (Windows, a filesystem
    that refuses it) are left.

    The former folder a copy is compared with is the one judged: once a
    dead copy's name is found, and before any copy is held or looked at,
    what stands at the former name is identified and opened
    (_the_former_folder_judged) -- a folder opened without following a
    link, its owner and identity read from what was opened -- and read
    through that descriptor alone. The cleanup judged the name, then opened
    it again by name for each copy: the account owning the folder above
    could rename the reader's unmoved former folder to a dead copy's name
    and put its own copy of it at the former name in between, and the
    reader's folder, the only place its charts were, was removed as a copy
    of the other. Where the former folder belongs to another account (at
    the name, or as opened) or another object than the one identified was
    opened, nothing is read from it, and every copy is left. Where nothing
    stood at the former name when it was judged, nothing put there later is
    read: no copy goes as a copy of it, and the record decides only once
    the name is empty. A link of this account's at the former name is
    followed, as the move follows it: the folder it leads to is compared
    only where it is this account's (os.fstat of what was opened) and the
    link, looked at again once it was opened, is still the one found and
    still leads to it (_still_the_former_folder); a link leading to another
    account's folder is never read through. So a copy goes only where
    everything in it is in a folder of this account's that the account's
    own link named, and nothing of it is lost."""
    if fcntl is None or not hasattr(os, "getuid"):
        return                          # no lock can tell a dead copy (Windows)
    # An earlier version's copy is compared only where its mode gives no
    # other account write. On Linux an access list's write to another shows
    # in the mode: the list's mask is the mode's group bits. A macOS list
    # does not show in the mode at all, so there such a copy is kept,
    # neither compared nor removed, as another account's things are.
    earlier = re.compile(r"\." + re.escape(path.name) + r"\.[0-9a-f]{16}\.copying")
    if sys.platform == "darwin":
        earlier = re.compile(r"(?!)")
    form = re.compile(r"\." + re.escape(path.name) + r"\.[0-9a-f]{16}\.incoming")
    try:
        names = [name for name in os.listdir(path.parent) if form.fullmatch(name) or earlier.fullmatch(name)]
    except OSError:
        return
    if not names:
        return
    try:
        former = _the_former_folder_judged(legacy)
    except (FormerFolderRefused, FormerFolderBusy, FormerFolderNotCopied):
        return                          # another account's, not the object identified, or its path open
    try:
        for name in names:
            staging = path.parent / name
            held = _hold_a_copy(staging)
            if held is None or held is _COPY_TAKEN:
                continue
            try:
                if form.fullmatch(name):
                    if _a_dead_copy_that_goes(held, staging, path, legacy, former):
                        _remove_through(held, staging)
                elif _held_copy_is_ours(held) and _only_a_copy_through(held, former, closed=True):
                    _remove_through(held, staging)
            finally:
                os.close(held)
    finally:
        if former is not None and former.fd is not None:
            os.close(former.fd)


def _the_former_folder_judged(legacy):
    """What stands at the former name `legacy`, identified and opened as
    the move opens it (_the_former_folder_opened), and looked at again once
    opened (_still_the_former_folder), for the dead-copy cleanup to compare
    copies with; None where nothing there can be compared (nothing stands
    there, something neither a folder nor a link, or a folder of this
    account's that cannot be opened). Raises FormerFolderRefused where it
    is another account's, FormerFolderBusy where what was opened is not
    the object identified, and FormerFolderNotCopied where its path is one
    other accounts could change."""
    try:
        former = _the_former_folder_opened(legacy)
    except (FormerFolderRefused, FormerFolderBusy, FormerFolderNotCopied):
        raise
    except OSError:
        return None
    if former is not None:
        try:
            _still_the_former_folder(former)
        except BaseException:
            if former.fd is not None:
                os.close(former.fd)
            raise
    return former


def _held_copy_is_ours(held, owner_only=False):
    """Whether the copy's folder open at `held` is this account's and no
    other can write in it (_none_else_writes) -- where `owner_only`, open to
    no other at all (no permission for its group or others), as a launch
    makes one: read from the descriptor, before anything in it is listed."""
    try:
        made = os.fstat(held)
    except OSError:
        return False
    if owner_only:
        return _ours(made.st_uid) and not stat.S_IMODE(made.st_mode) & 0o077
    return _none_else_writes(made)


def _none_else_writes(seen):
    """Whether the file or folder whose stat is `seen` is this account's
    and gives no write to its group or others."""
    return _ours(seen.st_uid) and not stat.S_IMODE(seen.st_mode) & 0o022


def _a_dead_copy_that_goes(held, staging, path, legacy, former):
    """Whether the copy's own folder `staging`, open and held at `held`,
    left by a launch killed while making the copy, is removed: where it is
    this account's and owner-only, as made, and holds nothing but the
    folder `copy` and its record -- no copy at all (a copy never begun, or
    one published, its folder left behind); a copy that is nothing but a
    copy of what the former folder `former`, judged and opened at the name
    `legacy`, holds (_only_a_copy_through); or,
    the former name gone, a copy whose record names the folder that now
    stands at the data folder's name `path` (_the_recorded_source)."""
    if not _held_copy_is_ours(held, owner_only=True):
        return False
    try:
        names = set(os.listdir(held))
    except OSError:
        return False
    if not names <= {_COPY_NAME, _RECORD_NAME}:
        return False
    if _COPY_NAME not in names:
        return True
    if os.path.lexists(legacy):
        return _only_a_copy_through(held, former, _COPY_NAME)
    source = _the_recorded_source(held)
    try:
        now = os.lstat(path)
    except OSError:
        return False
    return source is not None and (now.st_dev, now.st_ino) == source


# A folder that cannot be made (a base
# the account cannot write in, a file where the folder should be) used to
# raise here, at this module's import (which the engine's import makes), and
# the app died before any page with a raw traceback. The paths are still
# named, under the folder that could not be made, so that every read of them
# finds nothing and every write fails as a write; the reason is kept for
# data_folder_problem() below. Every name the call reaches is defined above
# it: a launch's import is the module's first run, and finds no other.
try:
    DATA_DIR = _user_data_dir()
    DATA_DIR_ERROR = None
except OSError as _data_dir_exc:
    DATA_DIR = _user_data_path()
    DATA_DIR_ERROR = _data_dir_exc.strerror or str(_data_dir_exc)


def data_folder_state():
    """What the folder holding the saved charts and the preferences cannot
    be, and the system's reason: ('made', reason) for a folder that could
    not be made, ('found', reason) for one gone since it was made,
    ('opened', reason) for one this account cannot enter, ('written in',
    reason) for one it cannot write in; (None, None) when it can be used.

    A folder that could not be made at launch is tried again on each call,
    so that one put right while the app is open is used from then on -- and
    made as the launch makes it: a bare mkdir here
    left the folder under the former name unmoved, after which the move
    could never run (the new folder now existing) and its saved charts
    dropped out of the app without a word.

    A folder that is there but that this
    account cannot enter (mode 000) or write in (mode 555) was taken as
    usable. Nothing was said: the one that cannot be entered opened with a
    picker empty of the charts it holds, and in either "Set as home" showed
    a home for the session that no file kept. Each call now asks the
    system whether this account may enter the folder and write in it (two
    access tests, no file made), so a folder put right while the app is
    open is used from then on, as above.

    A folder gone since the launch
    (removed, or a file or a broken link in its place) was left to the
    writes, which failed each in its own words ("Could not write ...", "the
    preferences file could not be written"), neither naming the folder.
    It is ('found', reason): said, and refused by Save and "Set as home",
    as the others are. It is not made again here -- the launch makes the
    folder; one removed while the app is open may be on its way back.

    A folder that belongs to another
    account, or another account's link at its name, is ('used',
    DATA_FOLDER_NOT_OURS), and nothing is read from it or written in it
    (_not_this_accounts); so is one whose path runs through a folder other
    accounts could change ('used', DATA_FOLDER_PATH_OPEN), and one the
    launch could not close to other accounts ('used',
    DATA_FOLDER_NOT_CLOSED). Where no data folder stands, the
    data folder is not made, and is asked again at each call, where the
    folder under the former name belongs to another account ('made',
    FORMER_FOLDER_NOT_OURS: FormerFolderRefused), where it is this
    account's but could be neither moved in nor copied whole ('made',
    FORMER_FOLDER_NOT_COPIED: FormerFolderNotCopied), a file the app reads
    that others could change or one past the bounds a launch copies among
    what it holds; where it holds
    what is not carried in ('made', FORMER_FOLDER_NOT_CARRIED:
    FormerFolderNotCarried), where it or a folder in it cannot be read
    ('made', FORMER_FOLDER_UNREADABLE: FormerFolderUnreadable), and where
    another launch or program holds it, or the name came to lead to
    another folder of this account's while the launch moved it
    ('made', FORMER_FOLDER_BUSY: FormerFolderBusy). Where the data folder
    stands but holds no store yet, and the folder under the former name
    beside it stands on a path other accounts could change, that folder is
    left unread and said the same way ('used', FORMER_FOLDER_NOT_COPIED:
    _former_folder_left_unread).

    A folder this account may enter and write in but cannot list (an older
    version's 0333, narrowed to 0300 by its owner's bits) was used: a store
    in it that others could change was loaded unseen. The launch makes it
    0700; one that still cannot be listed is ('listed', reason), and nothing
    is read from it or written in it (_folder_not_to_be_used).

    The folder held that is removed while the app runs is said as one not
    found, by its name; one made at that name again is judged and held as a
    launch holds one, or refused as a launch refuses one (_hold_again)."""
    global DATA_DIR_ERROR
    _hold_again(DATA_DIR)
    if DATA_DIR_ERROR is not None:
        try:
            _make_user_data_dir(DATA_DIR, lock_wait=0)
            DATA_DIR_ERROR = None
        except DataFolderRefused as exc:
            DATA_DIR_ERROR = exc.strerror or DATA_FOLDER_NOT_OURS
            return 'used', DATA_DIR_ERROR
        except OSError as exc:
            DATA_DIR_ERROR = exc.strerror or str(exc)
            return 'made', DATA_DIR_ERROR
    if not _isdir(DATA_DIR):
        try:
            _stat(DATA_DIR)
            reason = os.strerror(errno.ENOTDIR)
        except OSError as exc:
            reason = exc.strerror or os.strerror(errno.ENOENT)
        return 'found', reason
    if _not_this_accounts(DATA_DIR):
        return 'used', DATA_FOLDER_NOT_OURS
    if not _access(DATA_DIR, os.X_OK):
        return 'opened', os.strerror(errno.EACCES)
    if not _access(DATA_DIR, os.W_OK):
        return 'written in', _unwritable_folder_reason(DATA_DIR)
    try:
        _list_the_data_folder(DATA_DIR)
    except OSError as exc:
        return 'listed', exc.strerror or os.strerror(errno.EACCES)
    if _former_folder_left_unread(DATA_DIR):
        return 'used', FORMER_FOLDER_NOT_COPIED
    return None, None


def _former_folder_left_unread(folder):
    """Whether the data folder `folder` holds no store yet, and the folder
    under the app's former name beside it -- whose store a load would bring
    in -- stands on a path other accounts could change
    (_judge_the_former_folders_path: FormerFolderNotCopied). That folder is
    then left where it is, unmoved and unread, and said as its failed move
    is said where no data folder stands yet: the data folder is not used
    (data_folder_state: ('used', FORMER_FOLDER_NOT_COPIED);
    _folder_not_to_be_used), and is asked again at each call, so that a
    path put right, or a store saved there before, is used from then on.
    False where the former folder is another account's: that is passed
    over as if it were not there (_the_first_old_store)."""
    if isinstance(folder, int) or os.fspath(folder) != os.fspath(SAVED_CHARTS_PATH.parent):
        return False
    legacy = Path(folder).parent / _LEGACY_APP_DIR_NAME
    if not os.path.lexists(legacy) or _lexists(SAVED_CHARTS_PATH):
        return False
    try:
        _judge_the_former_folders_path(legacy)
    except FormerFolderNotCopied:
        return True
    except OSError:
        return False
    return False


def _folder_not_to_be_used(folder):
    """Whether nothing may be read from, or written in, the data folder
    `folder`: one a launch refused (DataFolderRefused: another account's,
    one whose path other accounts could change, one it could not close to
    them), one of another account's (_not_this_accounts), one whose path
    other accounts could change, judged now where the launch holds no other
    folder of that name (_judged_whole), one holding no store yet beside a
    former folder whose path other accounts could change
    (_former_folder_left_unread), or one this account cannot list.
    The launch makes the data folder 0700; one it still
    cannot list could not be looked at for files another account could
    change, so none of them can be told from the rest
    (_set_aside_what_others_could_write), and the folder fails closed:
    data_folder_state says it is ('listed', reason). A folder that is not
    there is not refused here: there is nothing in it to read. A folder made
    again at the name of one held and removed is judged and held first
    (_hold_again)."""
    _hold_again(folder)
    if not isinstance(folder, int) and os.fspath(folder) in _REFUSED:
        return True
    if _not_this_accounts(folder):          # the folder held is asked too (relative to it)
        return True
    if _former_folder_left_unread(folder):
        return True
    if _the_held(folder) is None:
        try:
            _judged_whole(folder)
        except DataFolderRefused:
            return True
        except (OSError, ValueError):
            pass                        # not there, or no folder: the listing below says
    try:
        _list_the_data_folder(folder)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return True
    return False


def _judged_whole(folder):
    """Judge the path to the folder `folder` as a launch judges the data
    folder's (_held_by_its_whole_path; on Windows
    _windows_judge_the_whole_path), opening nothing to keep:
    DataFolderOpenToOthers where other accounts could change it."""
    if hasattr(os, "getuid"):
        _held_by_its_whole_path(folder, opened=False)
    else:
        _windows_judge_the_whole_path(folder)


def _unwritable_folder_reason(path):
    """The system's words for a folder the account cannot write in: the
    filesystem's own when it is mounted read-only, else no permission."""
    try:
        if _statvfs(path).f_flag & os.ST_RDONLY:
            return os.strerror(errno.EROFS)
    except (OSError, AttributeError):      # no statvfs on Windows
        pass
    return os.strerror(errno.EACCES)


def data_folder_problem():
    """Why the folder holding the saved charts and the preferences cannot be
    used, or None when it can: data_folder_state()'s reason. That
    covers a folder that is there but that this account cannot enter or
    write in, as well as one that could not be made."""
    return data_folder_state()[1]

SAVED_CHARTS_PATH = DATA_DIR / "saved_charts.json"
# Where this file used to live -- checked once so anyone upgrading from
# before this change doesn't have to move it by hand.
_LEGACY_SAVED_CHARTS_PATH = Path(__file__).parent / "saved_charts.json"

def _validate_chart_mapping(charts):
    """The saved-charts file is {chart name: entry dict}. Valid JSON is not
    enough: '[]' parsed fine and then crashed the sidebar at .keys(). Only
    the shape the UI actually indexes is checked -- a mapping of string
    names to mapping entries -- so an older entry missing a field still
    loads.

    The SHAPE only, deliberately: one entry whose fields are the wrong type
    must not condemn the whole file, which is what raising here would do
    (the loader would copy the file aside and open with an empty picker).
    An entry's own fields are checked, one entry at a time and without
    raising, by the engine's chart_record_fault() -- a record that fails it
    stays in the mapping and in the file, and is refused only at the point
    where the sidebar would otherwise hand it to a widget."""
    if not isinstance(charts, dict):
        raise ValueError(f"saved charts root must be a mapping, got {type(charts).__name__}")
    for name, entry in charts.items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            raise ValueError(f"saved chart {name!r} is not a name -> mapping entry")
        # A name holding a lone surrogate -- the JSON
        # escape "\ud800", valid JSON -- is a str no page can carry: the
        # sidebar's picker raised on it before any page was drawn, at every
        # launch. Such a name is as unusable as a name that is not a str,
        # and condemns the store the same way: it is copied aside and named.
        if not _text_encodes(name):
            raise ValueError(f"saved chart {name!r} has a name that is not text a page can show")
    return charts


def _text_encodes(text):
    """Whether `text` encodes as UTF-8, which is what every page element
    needs of it. A str parsed from JSON can still fail: a lone surrogate
    escape ("\\ud800") parses to a str that no element can carry, while a
    surrogate PAIR written as two escapes parses to the one character it
    names and encodes. The browser sends UTF-8, so the app never makes
    such text itself; a hand edit or an import does."""
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True

def _parse_chart_mapping(data):
    """The validated mapping in the store's bytes `data`. Raises ValueError
    or RecursionError when they are not a store; both readers (the load's
    and the write's, saved_charts_as_they_stand) read through this one.

    - The codec utf-8-sig reads what Notepad writes (a leading BOM) and reads
      a BOM-less file unchanged. UnicodeDecodeError and JSONDecodeError
      are ValueErrors, as are the wrong shape and an integer literal past
      Python's digit limit.
    - JSON nested past the
      interpreter's depth raises RecursionError, and is no more a store
      than they are. The load caught only the ValueErrors, so such a file
      stopped the launch with a raw traceback.
    - A chart named twice. The parser keeps the last record under a
      repeated name and drops the first without a word, and the next save
      wrote the store again without it, so a hand edit's first record was
      in no file. A store naming a chart twice is not a store: it is
      copied aside before anything writes over it, as any malformed store
      is, and the copy is named. A field named twice inside one record (or
      anywhere below it) is held to the same: the parser kept its last
      value, the next save wrote the record back with that one, and the
      other was in no file (_without_repeated_keys).
    - The reader goes deeper than
      the writer. A record nested about 50,000 deep was read and listed,
      and the next Save died on a raw "Stack overflow" in json.dumps, the
      store unchanged and every later Save the same. A store this app
      could not write back is no more a store than one it cannot read: its
      text is made here, as write_saved_charts makes it, and the
      RecursionError that making raises is raised, so that the loader
      copies the bytes aside and names the copy, and a save writes in its
      place, as for any malformed store.
    - Making that text is itself the danger
      for a store nested a few hundred deep -- each level's lines carry its
      indentation, so 1.2 MB of JSON is some 700 MB of text, and a 3.2 MB
      stray raised MemoryError out of the load (where memory was bounded;
      elsewhere it took the memory). The text's length is first counted as
      the writer would make it, piece by piece and without making it, and a
      store whose text would pass STORE_TEXT_LIMIT is not a store: this app
      could not write it back."""
    charts = _without_repeated_keys(data, "a saved chart is named twice", "a saved chart gives a field twice")
    _validate_chart_mapping(charts)
    _within_the_store_text_limit(charts)
    _saved_charts_text(charts)
    return charts


def _without_repeated_keys(data, at_the_top, below):
    """The JSON object or value in the bytes `data` (utf-8-sig: a leading
    byte-order mark read and dropped), parsed so that no key is given twice
    in any one object; ValueError `at_the_top` where a key of the outermost
    object is, `below` where one inside it is. JSON lets a key be repeated
    and the parser keeps the last value without a word; the files this app
    reads are its own, which never repeat one, so a repeat is a hand edit's
    or another program's, and which value was meant cannot be told."""
    repeated = []

    def _pairs(pairs):
        mapping = dict(pairs)
        if len(mapping) != len(pairs):
            repeated.append(mapping)
        return mapping

    parsed = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_pairs)
    if any(mapping is parsed for mapping in repeated):
        raise ValueError(at_the_top)
    if repeated:
        raise ValueError(below)
    return parsed


# The most text a store may come to as the
# writer makes it (characters). A chart's record as written is some 225
# characters, so this is a store of some three hundred thousand charts (a
# test wrote 298,261 before passing it) -- far past any reader's -- and text
# this app can still make and write. The writer refuses a store past it as
# the reader does (finding 10 of that check), so that the app never writes
# what it will not read back.


def _within_the_store_text_limit(charts):
    """Count the text write_saved_charts would make of `charts` (the same
    encoder, indented, piece by piece, never joined) and raise ValueError
    once it passes STORE_TEXT_LIMIT; RecursionError where the writer's own
    would."""
    length = 0
    for piece in json.JSONEncoder(indent=2).iterencode(charts):
        length += len(piece)
        if length > STORE_TEXT_LIMIT:
            raise ValueError("the saved charts would be more text than this app writes")


def _read_regular_file(path, limit=None, judged=True):
    """The bytes of the regular file at `path`; NotAPlainFile for anything
    else, and for a file of more than `limit` bytes when a limit is given.
    `judged`, as every file in the data folder is read, takes only this
    account's regular file at the name itself (_open_this_accounts_file): no
    link there is followed, whoever made it -- a link of this account's is
    _Exposed, another account's file or link at the name, or a file of
    another's opened there, _NotThisAccounts -- and nothing of it is read.
    The store kept beside the program, outside the data folder, is read
    unjudged, as before, a link at its name followed.

    A pipe at the store's name, the preferences', an
    old store's or a recovery copy's held the load for ever, the page never
    drawn, and a link to an endless device at the preferences' name filled
    the memory. The name is opened without waiting (O_NONBLOCK: a pipe
    opens at once, with no writer) and judged by what was opened, so that
    nothing put in its place between a look and the open is read."""
    fd = _open_this_accounts_file(path) if judged else _open_regular_file(path)
    with os.fdopen(fd, "rb") as handle:
        if limit is None:
            return handle.read()
        data = handle.read(limit + 1)
    if len(data) > limit:
        raise NotAPlainFile(errno.EFBIG, os.strerror(errno.EFBIG), str(path))
    return data


# The name of the recovery copy the last load made, or None. Read by the
# sidebar, which says so once per session (else a malformed store showed an
# empty picker and the next save overwrote the
# only copy of the bytes). A module-level name rather than a second return
# value, because load_saved_charts() is called for its mapping in the app
# and in the tests alike and that signature stays as it is.
LAST_STORE_ERROR = None
# True when the last load found the store unreadable, whether or not a
# recovery copy could be made (a directory in the store's place has
# no bytes to copy, and used to open with an empty picker and no sentence).
LAST_STORE_UNREADABLE = False


def _preserve_unreadable_store(path, data=None, limit=None):
    """Copy an unreadable store beside itself, once per content, as
    ``saved_charts.json.unreadable-<YYYYMMDD-HHMMSS>`` (in a folder that
    cannot be listed, ``...unreadable-<16 hex of its digest>``); the copy's file name,
    or None if the bytes could not be read or written. The same bytes are
    not copied twice: a session that opens the app repeatedly against one
    broken file leaves one recovery copy, not one per launch. `data`, when
    given, is the bytes the caller has already read and judged, so that the
    copy holds exactly what was judged unreadable.

    Only a regular file of this account's is read, of no more than `limit`
    bytes when one is given (_read_regular_file, judged): another account's
    store, or one a link leads to, is not read, and no copy of it is made;
    a pipe, or another account's file, at a copy's name is
    passed over, as any other name already taken is. A copy already made is
    read only as far as the bytes it is compared with, and one that holds
    more is another content's. A copy is made owner-only
    (0600), whatever the umask."""
    if data is None:
        try:
            data = _read_regular_file(path, limit)
        except OSError:
            return None
    # The copies were looked for by a
    # glob, which finds nothing in a folder this account may enter and write
    # in but not list (mode 0300), so each launch copied the same bytes again
    # under a new name. Where the folder cannot be listed, the copy is named
    # by its content instead, and found by that name.
    try:
        names = _listdir(path.parent)
    except OSError:
        names = None
    if names is None:
        stem = f"{path.name}.unreadable-{hashlib.sha256(data).hexdigest()[:16]}"
        try:
            if _read_regular_file(path.with_name(stem), len(data)) == data:
                return stem
        except OSError:
            pass
    else:
        for previous in sorted(n for n in names if n.startswith(path.name + ".unreadable-")):
            try:
                if _read_regular_file(path.with_name(previous), len(data)) == data:
                    return previous
            except OSError:
                continue
        stem = f"{path.name}.unreadable-{datetime.now():%Y%m%d-%H%M%S}"
    # Two different wrecks within one second: the second keeps its own copy
    # rather than writing over the first one's bytes.
    #
    # The name was asked
    # free (exists()) and then written (write_bytes), so two loads holding
    # two different unreadable contents in one second -- the file replaced
    # by an editor between their reads; the loads hold no lock here -- chose
    # one name, and the second's bytes went over the first's while both
    # named the copy as kept. Each copy is now made new or not at all
    # (O_CREAT|O_EXCL, as _keep_stray_aside makes its copies): a name
    # already there is never opened or written over. One that already holds
    # these very bytes (another load of the same content, a moment before)
    # is that content's copy, and is named; any other is passed over for
    # the next free -2, -3, ...
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    for n in range(1, 1000):
        name = stem if n == 1 else f"{stem}-{n}"
        copy = path.with_name(name)
        try:
            fd = _open(copy, flags, 0o600)
        except FileExistsError:
            try:
                if _read_regular_file(copy, len(data)) == data:
                    return name
            except OSError:
                pass
            continue
        except OSError:
            return None
        try:
            with os.fdopen(fd, "wb") as handle:
                _owner_only(handle.fileno())
                handle.write(data)
        except OSError:
            try:
                _unlink(copy)             # this copy's own, made just now: no other's is ever named
            except OSError:
                pass
            return None
        return name
    return None

def _write_text_atomically(path, text):
    """Write to a sibling temp file and os.replace() it over the target, so
    a crash or full disk mid-write leaves the previous file intact rather
    than a truncated one that loses every saved chart.

    The temp file's bytes are flushed and synced (os.fsync) before it
    replaces the target, so a crash of the system after the replace finds
    the new bytes or the previous file, never an empty one; a failed sync
    fails the write. On Linux and macOS the folder is synced after the
    replace as well, so the replace itself is kept when this returns; a
    folder whose sync is refused is passed over, and the write stands. On
    Windows the folder is not synced: a crash soon after the write can
    still bring back the previous file, whole. On macOS fsync does not
    empty the drive's own cache, so a power cut can still lose what it
    holds there.

    The bytes written are `text` encoded as UTF-8 and nothing else (no
    newline translation), so that a caller knows them without reading the
    file back: write_saved_charts' digest.

    A file kept as a symbolic link was followed, the temp file made beside
    the file it named, and that file replaced. A link at the name is now
    never written through, whoever made it and wherever it leads: another
    account that could write in a folder on the way to the file it names
    could put another of the user's files there, which the save then wrote
    over, or change a folder on that way between the save's look and its
    replace. _Exposed (or _NotThisAccounts, for a link of this account's to
    another's file), and nothing is written; the page says the app does not
    follow it. Another account's file or link at the name is never written
    through either: the new file is made beside the name, at 0600, and
    replaces what stands there. Every call is made relative to the data
    folder the launch holds (_in_the_held_folder), never by its path again.

    A file made read-only (0444) came back writable (0644), because
    os.replace needs only the folder's permission and the temp file had the
    account's default mode. The owner's part of the file's mode is carried
    onto the temp file before the replace (0444 becomes 0400); its group's
    and others' are not, so that a file an older version left writable by
    others (0666) is never made so again.

    The temp file was made 0o666, cut by the umask, and held the bytes
    at that mode until the carry -- 0666 under umask 000, beside a store of
    0600. It is now made at the owner's part of the target's mode
    (_new_temp_file), so it is never wider than its target at any moment, and
    a first-ever file is made owner-only, 0600, whatever the umask.

    Every write of one file
    went through one temp name, `<file>.tmp`. Two writes in flight at once
    (two windows, or two launches of the app on one folder) shared it: the
    second truncated and refilled the first's temp file, the first's replace
    installed the second's bytes and reported success, and the second's
    replace found no temp file and reported a failure. Each write now makes
    a temp file of its own, made new or not at all (O_CREAT|O_EXCL: a name
    already there is never opened, so never another writer's)."""
    whose = _whose(path)
    if whose == _LEADS_TO_ANOTHERS:
        raise _NotThisAccounts(errno.EPERM, os.strerror(errno.EPERM), str(path))
    if whose == _OUR_LINK:
        raise _Exposed(errno.EPERM, os.strerror(errno.EPERM), str(path))
    target = Path(path)
    mode = None
    if whose == _OURS:
        try:
            mode = stat.S_IMODE(_lstat(target).st_mode) & 0o700
        except OSError:
            pass
    data = text.encode("utf-8")
    tmp, fd = _new_temp_file(target, 0o600 if mode is None else mode)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # The umask may have cut the mode asked of the open (0o200 under
        # 0o444); os.chmod is not cut, and gives the file its mode exactly.
        _chmod(tmp, 0o600 if mode is None else mode)
        _replace(tmp, target)
    except OSError:
        # A failed replace (a directory in the store's place) leaves
        # no stray temp file behind -- made writable first, since a
        # read-only file cannot be removed on every system. Only this
        # write's own temp file is removed: no other writer's is ever named.
        try:
            _chmod(tmp, stat.S_IREAD | stat.S_IWRITE)
        except OSError:
            pass
        try:
            _unlink(tmp)
        except OSError:
            pass
        raise
    _sync_folder(target.parent)


# --- The store's lock and the preferences' lock -----
# A save read the store, put
# its record into what it read and wrote the whole file back, and
# remember_preference / forget_preference did the same with one key of the
# preferences; nothing was held across the three steps. Another window's
# write landing between this window's read and its write was written over,
# and both windows said it was done. Each read-change-write is now made
# under a lock, the store's and the preferences' each its own:
#
# - a thread lock, for the windows of one server (Streamlit runs each
#   window's script in a thread of its own);
# - and a lock on a file in the data folder, for two launches of the app on
#   one folder: fcntl.flock where the system has it (a second descriptor of
#   the file is refused while the first holds it, in the same process as in
#   another), msvcrt's lock on the file's first byte on Windows, and the
#   thread lock alone where neither is to be had (no lock module, or a lock
#   call that answers ENOSYS, not provided by this system) or the file
#   cannot be made (a folder this account cannot write in: the write then
#   fails as a write, and the sidebar's sentence about the folder stands as
#   before).
#
# The lock file is not the store itself, which os.replace swaps for a new
# file at every write (a lock on the old one would lock nothing). It is in
# the data folder; where the store is a link to a file in another folder, a
# write takes one beside that file as well (_lock_files), since that is the
# file every launch linked to it writes. It lives only while it is held: the
# holder removes it before it lets go, and a writer that was waiting on a
# file so removed finds, once it
# has it, that the name no longer leads to it, and takes the lock on the
# file now there instead. So no lock file is left in the folder.
#
# The two locks are separate because a save, holding the store's lock,
# then remembers its chart as the last one opened; one lock taken twice
# would wait on itself. Where both are held the store's is taken first.
#
# Each lock is waited on for a bounded
# time, LOCK_WAIT_SECONDS in all -- the thread lock's wait and the file
# lock's, however many hand-overs are lost on the way. Past it DataLockBusy
# is raised and nothing is written; the page says another window of the app
# is holding the data and to try again. A second launch stopped or hung while
# it held a lock used to leave every Save of every window waiting without
# end. The file lock is asked for without blocking and asked again after a
# short pause (flock and msvcrt's lock take no time limit).
#
# A writer that loses a hand-over (the file it waited on removed
# by its holder, and another writer already holding the file now under the
# name) waits on the new file in its turn; it never goes ahead on the thread
# lock alone while a file lock is to be had (a cap of sixteen such losses
# let it, and writes were lost).
#
# The fallback is narrowed to the thread lock
# alone where no file lock can be had at all -- no lock call on this system,
# a folder this account cannot write in. A
# directory, a link (dangling, or to a file elsewhere) or a file this account
# can open in no way standing under the lock file's name used to end the
# lock between launches silently and for good; a write meeting one is now
# refused (DataLockBlocked), nothing is written, and the obstruction is left
# as it is. A lock file this account can open only for reading, or only for
# writing, is no obstruction: flock takes a descriptor opened either way.
# Under a umask that takes away the owner's write, a launch's own lock file
# is made read-only (0o666 masked), and every other launch went in on the
# thread lock alone while it was held; a
# launch killed while holding it left it so for good.
#
# A lock call that fails for any reason but another holder's, on a system
# that has the call -- a network folder with no lock service, a filesystem
# that does not support locks -- refuses the write (DataLockUnavailable):
# nothing is written, and the page says so (for the saved charts, that their
# folder could not be locked; for a preference, as for any write the file
# did not take). Going on with the thread lock alone there let two launches on
# one folder each report a save while one of the two was lost. The lock file
# made for the attempt is left where it is, and the next write opens it as
# it stands.

LOCK_WAIT_SECONDS = 10.0


class DataLockBusy(Exception):
    """The saved charts' or the preferences' lock was held elsewhere past
    LOCK_WAIT_SECONDS: by another window of the app, or another launch of it
    on the same folder. Nothing has been written."""


class DataLockBlocked(DataLockBusy):
    """Something stands under a lock file's name that is no lock
    file this app can use -- a directory, a link, a file this account can
    open in no way -- on a system that offers file locks. Nothing has been
    written, and what stands there is left as it is. `folder` is the folder
    it stands in: the data folder, or the folder of the file a linked store
    or preferences file names. A DataLockBusy, so that whatever gives up on
    a busy lock gives up here too and writes nothing."""

    def __init__(self, folder):
        super().__init__(str(folder))
        self.folder = str(folder)


class DataLockUnavailable(DataLockBusy):
    """The lock call itself failed on a lock file in `folder`, for a reason
    other than another holder's (a network folder with no lock service, a
    filesystem that does not support locks), on a system that has the call.
    Nothing has been written: without the lock, a write from another launch
    of the app on the same folder could be lost unseen. A DataLockBusy, so
    that whatever gives up on a busy lock gives up here too."""

    def __init__(self, folder):
        super().__init__(str(folder))
        self.folder = str(folder)

_STORE_THREAD_LOCK = threading.Lock()
_PREFERENCES_THREAD_LOCK = threading.Lock()


def saved_charts_lock(wait=None):
    """The store's lock, held with `with` across a read of the store, the
    change made to it and its write. `wait`, when given, bounds the wait for
    the lock in place of LOCK_WAIT_SECONDS (a tidying that can as well be
    left to the next launch waits a moment for the lock); it bounds nothing
    done once the lock is held."""
    return _data_lock(_STORE_THREAD_LOCK, _lock_files(SAVED_CHARTS_PATH, "saved_charts.lock"), wait)


def preferences_lock(wait=None):
    """The preferences' lock, held across a read of the preferences file,
    the change made to it and its write; `wait` as in saved_charts_lock."""
    return _data_lock(_PREFERENCES_THREAD_LOCK, _lock_files(PREFERENCES_PATH, "preferences.lock"), wait)


def _lock_files(path, name):
    """The lock files a write of `path` holds: `name` in the data folder.
    Where `path` was a link to a file in another folder, a lock beside that
    file was held as well; no link at the store's name is followed now
    (_write_text_atomically), so the data folder's lock is the only one."""
    return [path.parent / name]


@contextmanager
def _data_lock(thread_lock, lock_paths, wait=None):
    """Hold `thread_lock` and the file lock of each of `lock_paths`, in
    order, all within one LOCK_WAIT_SECONDS (or `wait`); DataLockBusy, with
    none held, past it."""
    if wait is None:
        wait = LOCK_WAIT_SECONDS
    deadline = _clock.monotonic() + wait
    if not thread_lock.acquire(timeout=max(0.0, wait)):
        raise DataLockBusy()
    held = []
    try:
        for lock_path in lock_paths:
            fd = _take_file_lock(lock_path, deadline)
            if fd is not None:
                held.append((fd, lock_path))
        yield
    finally:
        try:
            for fd, lock_path in reversed(held):
                _give_file_lock(fd, lock_path)
        finally:
            thread_lock.release()


def _take_file_lock(lock_path, deadline=None):
    """The descriptor of `lock_path`, made if need be and locked, or None
    where no file lock can be had (no lock call on this system: no lock
    module, or a call that answers ENOSYS; a folder this account cannot
    write in). A lock call that fails for any other reason than another
    holder's (a network folder with no lock service, ENOLCK; a filesystem
    that does not support locks, EOPNOTSUPP) refuses the write:
    DataLockUnavailable, naming the folder, the file lock not held.

    A link under the name is not followed (O_NOFOLLOW, where the system has
    it: a dangling link made its target, outside the
    data folder), and a directory cannot be opened for writing. A link, a
    directory, or a file this account can open in no way, under
    the name, refuses the write (DataLockBlocked, naming the folder), and
    is left as it stands; the fallback, the thread lock alone, is
    for where no file lock can be had at all.

    A lock file this
    account may only read (the app's own, made under a umask that takes the
    owner's write, or left by a launch killed while it held one) or only
    write is opened as it allows -- flock takes a descriptor opened for
    reading or for writing alike -- and locked as it stands, not refused.
    One it may only read is no holder's to remove (_give_file_lock).

    Windows' Python has no O_NOFOLLOW, so a link
    under the name was opened through, the file opened never was the name,
    and the writer reopened it without end, holding the thread lock: every
    Save hung. So the name is looked at, not followed, before the open --
    anything there but a regular file and nothing is opened -- and again
    after it, which closes the moment between the two.

    A lock file is judged by its owner, at the name and as opened, as every
    file in the data folder is: another account's under the name, one
    another account put there while an older version left the folder open,
    was opened for reading and writing and locked as the app's own. It is
    now no lock file (_lock_name_kind: 'other'): never opened, it refuses
    the write (DataLockBlocked), and is left as it stands.

    A writer whose file was removed by its holder, another
    writer already holding the file now under the name, takes its turn on
    that one; all within `deadline` (LOCK_WAIT_SECONDS from now
    when not given), past which DataLockBusy, the file lock not held."""
    if fcntl is None and msvcrt is None:
        return None
    if deadline is None:
        deadline = _clock.monotonic() + LOCK_WAIT_SECONDS
    while True:
        if _clock.monotonic() >= deadline:
            raise DataLockBusy()
        if _lock_name_kind(lock_path) == 'other':
            raise DataLockBlocked(lock_path.parent)
        fd = _open_lock_file(lock_path)
        if fd is _LOCK_NAME_EMPTIED:
            continue                    # its holder removed it between the looks: the name again
        if fd is None:
            return None
        try:
            opened_regular = stat.S_ISREG(os.fstat(fd).st_mode) and _opened_is_ours(fd)
        except OSError:
            opened_regular = False
        if not opened_regular or _lock_name_kind(lock_path) == 'other':
            os.close(fd)
            raise DataLockBlocked(lock_path.parent)
        try:
            _wait_for_file_lock(fd, deadline)
        except DataLockBusy:
            os.close(fd)
            raise
        except OSError as exc:
            os.close(fd)
            # No lock call on this system: the thread lock alone. (Read
            # guarded: a system without the name never matches, and refuses.)
            if exc.errno == getattr(errno, "ENOSYS", None):
                return None
            raise DataLockUnavailable(lock_path.parent) from exc
        if _still_named(fd, lock_path):
            return fd
        # The holder this write waited on removed the file before letting
        # go: the lock to take is on the one now under the name.
        os.close(fd)


# The errors a lock asked for without blocking is refused with while
# another holds it: flock's EWOULDBLOCK, msvcrt's EACCES (EDEADLK, Windows'
# EDEADLOCK, is msvcrt's only for a blocking LK_LOCK or LK_RLCK after its
# retries, never for this LK_NBLCK; macOS has no EDEADLOCK).
_LOCK_REFUSALS = frozenset({errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES, errno.EDEADLK})


def _wait_for_file_lock(fd, deadline):
    """Lock `fd` (flock, or msvcrt's lock on the file's first byte), asking
    without blocking and again after a pause that grows to a tenth of a
    second while another holds it; DataLockBusy at `deadline`. Any other
    refusal is raised as the OSError it is."""
    pause = 0.005
    while True:
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return
        except OSError as exc:
            if exc.errno not in _LOCK_REFUSALS:
                raise
        left = deadline - _clock.monotonic()
        if left <= 0:
            raise DataLockBusy()
        _clock.sleep(min(pause, left))
        pause = min(pause * 2, 0.1)


# What _open_lock_file gives back when the file under the name went between
# the open that was refused and the look after it: the name is taken again.
_LOCK_NAME_EMPTIED = object()


def _open_lock_file(lock_path):
    """A descriptor of the lock file `lock_path`, made if need be; None
    where none can be had (the fallback: a folder this account
    cannot write in, a folder gone, a filesystem that cannot be written);
    _LOCK_NAME_EMPTIED where the file went in the meantime; DataLockBlocked
    for something under the name that is no lock file this app can use.

    The file is made exclusively (O_CREAT|O_EXCL), and anything already
    under the name is opened as it stands: read and write where the account
    may; otherwise read only, or write only, as the file allows (the app's own
    lock file under a umask that takes the
    owner's write is read-only). Those opens do not create, follow no link
    and do not wait (O_NONBLOCK: a pipe put under the name in between is
    opened at once, and found no regular file by the caller's look after
    the open).

    The make used to be one read-write open with
    O_CREAT, which a folder this account cannot write in and a read-only
    file standing under the name refuse alike. A look after the refusal told
    them apart, and a file let go by its holder in between (removed at its
    release) looked like the folder's refusal: the write went in on the
    thread lock alone while a third launch made and locked a new file, and
    saves were lost. An exclusive make meets anything under the name as
    EEXIST, so a refusal of it is the folder's own, with no look between to
    be overtaken; a file gone before it could be opened as it stands is the
    name taken again. O_EXCL follows no link either, so a dangling link put
    under the name is never made into a file outside, O_NOFOLLOW or not."""
    plain = getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        return _open(lock_path, os.O_RDWR | os.O_CREAT | os.O_EXCL | plain, 0o600)   # owner-only
    except FileExistsError:
        kind = _lock_name_kind(lock_path)          # something stands under the name: opened as it stands, below,
        if kind == 'other':                         # unless it is no lock file of this account's
            raise DataLockBlocked(lock_path.parent)
        if kind == 'absent':
            return _LOCK_NAME_EMPTIED
    except OSError:
        # Nothing stood under the name (an exclusive make meets anything
        # there as EEXIST): the folder refused the file's making, or the name
        # cannot be looked at -- no file lock to be had.
        if _lock_name_kind(lock_path) == 'other':
            raise DataLockBlocked(lock_path.parent)
        return None
    for access in (os.O_RDWR, os.O_RDONLY, os.O_WRONLY):
        try:
            return _open(lock_path, access | plain | getattr(os, "O_NONBLOCK", 0))
        except PermissionError:
            continue
        except FileNotFoundError:
            return _LOCK_NAME_EMPTIED   # let go by its holder since the make: the name again
        except OSError:
            # A link (ELOOP under O_NOFOLLOW), a directory (EISDIR) is refused;
            # anything else (a filesystem that cannot be written) is no file lock.
            if _lock_name_kind(lock_path) == 'other':
                raise DataLockBlocked(lock_path.parent)
            return None
    kind = _lock_name_kind(lock_path)
    if kind == 'absent':
        return _LOCK_NAME_EMPTIED
    if kind == 'unseen':
        return None
    raise DataLockBlocked(lock_path.parent)     # a file this account can open in no way, or another thing now


def _opened_for_writing(fd):
    """Whether the descriptor `fd` was opened for writing (read and write,
    or write only)."""
    try:
        return fcntl.fcntl(fd, fcntl.F_GETFL) & getattr(os, "O_ACCMODE", 3) != os.O_RDONLY
    except OSError:
        return True


def _lock_name_kind(lock_path):
    """What stands under the lock name, the name itself looked at (a link
    not followed): 'absent', 'file' (a regular file of this account's,
    _whose), 'other' (anything else, another account's file among them), or
    'unseen' when the name cannot be looked at (a folder this account may
    not search, or one gone): that is the folder's own case, said by the
    folder's sentence, and no obstruction under the name."""
    try:
        mode = _lstat(lock_path).st_mode
    except FileNotFoundError:
        return 'absent'
    except OSError:
        return 'unseen'
    if not stat.S_ISREG(mode):
        return 'other'
    whose = _whose(lock_path)
    if whose == _NOTHING:
        return 'absent'
    return 'file' if whose == _OURS else 'other'


def _still_named(fd, lock_path):
    """Whether `lock_path` still names the file open on `fd` (the name
    itself, a link not followed)."""
    try:
        return os.path.samestat(os.fstat(fd), _lstat(lock_path))
    except OSError:
        return False


def _give_file_lock(fd, lock_path):
    """Remove the lock file and let the lock go. With flock the file is
    removed while still held, so that no one can lock it afresh after; on
    Windows a file open elsewhere cannot be removed at all, so the lock is
    let go first and the removal is tried after, and refused while another
    writer has the file open.

    The name is removed only while it still names this holder's file: if
    something outside the app removed the file while it was held, and a
    newcomer has since made and locked another under the name, that one is
    the newcomer's and is left.

    Nor is a lock file removed that this holder could
    open only for reading. It is no launch's own making that this account may write
    (a launch opens the file it makes for writing), so it is left as it
    stands -- a lock file still, to the next launch as to this one."""
    if fcntl is not None:
        if _still_named(fd, lock_path) and _opened_for_writing(fd):
            try:
                _unlink(lock_path)
            except OSError:
                pass
        os.close(fd)
        return
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    named = _still_named(fd, lock_path)
    os.close(fd)
    if named:
        try:
            _unlink(lock_path)
        except OSError:
            pass

# Since each write makes
# a temporary file of its own, a write whose process was killed
# between that file and its replace left `<file>.<16 hex>.tmp` beside the
# file for good -- no later write took that name again. At each load the
# strays are tidied: only names of that exact form, only regular files,
# only those last written before this launch (no write of this launch can
# own one), and only under the file's own lock, which every write of it
# holds while its temporary file stands. The lock is waited on a moment
# only (_STRAY_TEMP_WAIT): a stray left now is tidied by a later load. That
# moment bounds the wait for the lock and nothing else: the listing under
# the lock, and the reading, judging, copying and removing of the strays
# after it, take what they take.
#
# A stray may hold the reader's last save, complete -- the write
# was killed after its bytes and before its replace. One that reads as the
# file it was written for (a store; for the preferences, an object) is kept
# aside under a recovery name, `<file>.recovered-<YYYYMMDD-HHMMSS>`, and
# only then removed; one that does not read is removed; one whose bytes
# cannot be read at all is left. The same holds for the shared name every
# write of the store once went through, `saved_charts.json.tmp`,
# which no write of this version makes or removes.
_LAUNCHED_AT = _clock.time()
_STRAY_TEMP_WAIT = 0.25


def _keep_stray_aside(target, data):
    """A recovery copy of a stray's bytes `data` beside `target`, made new
    (O_CREAT|O_EXCL): a copy already under the name -- another launch's, or
    one made in the same second -- is never written over, and the next free
    `-2`, `-3`, ... is taken. Its name, or None when none could be made."""
    stem = f"{target.name}.recovered-{_recovery_stamp()}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    for n in range(1, 1000):
        name = stem if n == 1 else f"{stem}-{n}"
        copy = target.with_name(name)
        try:
            fd = _open(copy, flags, 0o600)            # owner-only, as _preserve_unreadable_store's
        except FileExistsError:
            continue
        except OSError:
            return None
        try:
            with os.fdopen(fd, "wb") as handle:
                _owner_only(handle.fileno())
                handle.write(data)
        except OSError:
            try:
                _unlink(copy)
            except OSError:
                pass
            return None
        return name
    return None


def _reads_as_a_store(data):
    try:
        _parse_chart_mapping(data)
    except (ValueError, RecursionError):
        return False
    return True


def _reads_as_preferences(data):
    try:
        return isinstance(_parse_preferences(data), dict)
    except (ValueError, RecursionError):
        return False


def _parse_preferences(data):
    """The object or value in the preferences file's bytes `data`;
    ValueError where they are not JSON, or name a key twice in one object
    (_without_repeated_keys: the parser kept the last value, and the first
    was dropped without a word at the next write), as a store naming a chart
    twice is not a store."""
    return _without_repeated_keys(data, "a preference is given twice", "a preference gives a key twice")


def _tidy_stray_temp_files(path, lock, reads, limit, former_name=False):
    """The strays (above) beside `path`'s real target,
    listed under `lock`; `reads(bytes)` says whether a stray reads as the
    file; `former_name` takes the earlier writer's `<file>.tmp` as well.
    Returns how many strays were kept aside (the load says so). A stray
    of more than `limit` bytes is not read, and is left, as one whose bytes
    cannot be read is.

    Strays are tidied only in `path`'s own folder, the data folder: beside a
    file kept as a link to one in another folder they are left for
    that folder's owner, whose folder it is, not the app's -- the write
    through the link still makes its temporary file there, and a write killed
    before its replace leaves it there, untouched.

    The former name was
    taken as `<the linked file's name>.tmp`, and beside a store kept as a
    link to a file of another name (`shared.json`, in a folder other
    programs write in) that is any program's name for its own temporary
    file: another program's work, older than the launch, was removed, or
    kept aside and removed. The former name is
    `saved_charts.json.tmp`, the one this app's earlier writer used: it is
    taken only beside a file of the store's own name.

    Only this account's strays are read, kept aside or removed, each judged
    by its owner at its name and as opened (_read_the_stray): another
    account's, one put there while an older version left the folder open,
    is left as it stands. Where the file's own name is another account's
    (a file, or a link not followed), the strays are those of that name.

    A stray another account could change (_others_could_change_the_stray),
    at its name or as opened, was read and kept aside as the user's; it is
    now set aside unread, as the launch sets aside a store others could
    change (_move_aside, _make_it_private), and counted with the strays kept
    aside, which the page says. Its bytes are never read or copied."""
    target = Path(path)
    former_name = former_name and target.name == Path(path).name
    form = r"(?:\.[0-9a-f]{16})?\.tmp" if former_name else r"\.[0-9a-f]{16}\.tmp"
    stray_name = re.compile(re.escape(target.name) + form)
    # Each stray was read,
    # parsed and copied while the lock was held -- and the parse of a store
    # makes its whole text again, which for a stray of deep nesting
    # under a megabyte takes seconds -- so another window's Save waited past
    # its bound and was refused. Only the listing is made under the lock:
    # every write holds the lock while its temporary file stands, so a name
    # listed then is no write's in flight, and no later write takes that
    # name again (each makes a new one). The strays are read, judged, kept
    # aside and removed after the lock is let go; each is read and removed
    # only while its name still holds the very file listed.
    found = []
    try:
        with lock(wait=_STRAY_TEMP_WAIT):
            try:
                names = _listdir(target.parent)
            except OSError:
                return 0
            for name in names:
                if not stray_name.fullmatch(name):
                    continue
                stray = target.parent / name
                try:
                    seen = _lstat(stray)
                except OSError:
                    continue
                if (stat.S_ISREG(seen.st_mode) and seen.st_mtime < _LAUNCHED_AT and seen.st_size <= limit
                        and _whose(stray) == _OURS):
                    found.append((stray, seen))
    except DataLockBusy:
        return 0
    kept = 0
    for stray, seen in found:
        modes = []
        data = None
        if not _others_could_change_the_stray(stray, seen, modes):
            data = _read_the_stray(stray, seen, limit, modes)
        if data is None:
            if _others_could_change_the_stray(stray, seen, modes) and _still_the_stray(stray, seen):
                aside = _move_aside(stray, seen)
                if aside is not None:
                    _make_it_private(aside, seen)
                    kept += 1
            continue                            # gone, changed, or not to be read: left
        gone = False
        if reads(data):
            if not _still_the_stray(stray, seen):
                continue                        # another load has kept it aside and removed it
            if _keep_stray_aside(target, data) is None:
                continue                        # not kept aside: not removed either
            kept += 1
            gone = True
        if _still_the_stray(stray, seen):
            try:
                _unlink(stray)
            except OSError:
                pass
            else:
                gone = True
    return kept


def _others_could_change_the_stray(stray, seen, modes):
    """Whether another account could change the stray `stray`: on POSIX
    where its group or others may write it, at its name as listed (`seen`)
    or as opened (`modes`, the opened file's mode, from _read_the_stray); on
    Windows where its own access list lets them
    (_windows_file_is_writable_by_others), or where that cannot be read: a
    stray that cannot be judged is not read."""
    if hasattr(os, "getuid"):
        if _taken_as_it_is(seen, stray):
            return False
        return any(mode & 0o022 for mode in [stat.S_IMODE(seen.st_mode), *modes])
    return _windows_wide(stray)


def _same_file(a, b):
    return (a.st_dev, a.st_ino, a.st_size, a.st_mtime_ns) == (b.st_dev, b.st_ino, b.st_size, b.st_mtime_ns)


def _still_the_stray(stray, seen):
    """Whether the name `stray` still holds the file listed as `seen` (the
    name itself, a link not followed)."""
    try:
        return _same_file(_lstat(stray), seen)
    except OSError:
        return False


def _read_the_stray(stray, seen, limit, modes=None):
    """The bytes of the file listed as `seen`, read through its name only
    while the name still holds it (a link not followed) and what was opened
    is this account's (_opened_is_ours), and only as far as
    `limit` bytes; None when it does not, or the bytes cannot be read, or
    there are more. The opened file's mode is added to `modes`, where given;
    one others could write is not read (None).
    The size fstat gives is the bound before reading (the file listed, of no
    more than `limit` bytes, and the one opened the same), and `limit` + 1
    bytes the bound while reading: a stray that grows is not read."""
    flags = (os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0))          # a pipe put in its place is not waited on
    try:
        fd = _open(stray, flags)
    except OSError:
        return None
    try:
        with os.fdopen(fd, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if not _same_file(opened, seen) or not _opened_is_ours(handle.fileno()):
                return None
            if modes is not None:
                modes.append(stat.S_IMODE(opened.st_mode))
            if hasattr(os, "getuid") and _wide_here(opened, stray):
                return None
            data = handle.read(limit + 1)
            return data if len(data) <= limit else None
    except OSError:
        return None


def _old_stores():
    """Where a store was kept before the per-user folder held it, newest
    first: the folder under the app's former name (its store is there still
    when the folder was copied, not moved), then beside app.py
    (_LEGACY_SAVED_CHARTS_PATH).

    The store beside the program
    was brought in, without a word, whenever the folder held no store -- at
    the first launch, and again after every deletion of the store -- and in
    a packaged build that folder is the bundle's own. It is now brought in
    once (_IMPORTED_BESIDE_THE_PROGRAM marks the data folder when it has
    been, and the load says so), and never inside a packaged build."""
    olds = [_the_former_folders_store()]
    if not _running_from_a_bundle() and not _the_store_beside_the_program_was_imported():
        olds.append(_LEGACY_SAVED_CHARTS_PATH)
    return olds


def _the_former_folders_store():
    """Where the folder under the app's former name keeps its store."""
    return SAVED_CHARTS_PATH.parent.parent / _LEGACY_APP_DIR_NAME / SAVED_CHARTS_PATH.name


def _read_the_former_folders_store(old):
    """The bytes of the store `old` in the folder under the app's former
    name, read only where they are this account's own: the folder (judged
    at its name, and where that is a link of this account's, the folder it
    leads to as well) and the store must be this account's, at its name
    (_whose) and as opened (_opened_is_ours), on every platform, and the store
    a regular file, opened without following a link (a look first, where
    the open cannot refuse one: Windows). A store kept there as a link,
    or as anything but a regular file, is NotAPlainFile; one of another
    account's, or in another account's folder, is a PermissionError; one of
    more than STORE_BYTE_LIMIT bytes is NotAPlainFile (EFBIG). Nothing is
    read in any of these.

    The store there was read whatever stood at its name, a link followed,
    and brought into the data folder: where another account could write in
    the folder above the data folder, it chose what this account's saved
    charts were made of.

    The folder was judged by its owners alone, and the store opened by its
    path: where the former name was a link whose path ran through a folder
    another account could write in, that account could put another of the
    user's folders on the way, and its file was read as the saved charts.
    The path is now judged whole as the data folder's is, at the read
    itself, and the store read relative to the folder the walk opened
    (_the_former_folder_walked); on Windows the path is judged
    (_windows_judge_the_whole_path) just before the store is read by its
    name. Where it fails, FormerFolderNotCopied, and nothing is read."""
    folder = old.parent
    if _former_folder_not_this_accounts(folder) or _not_this_accounts(folder):
        raise PermissionError(errno.EPERM, os.strerror(errno.EPERM), str(old))
    flags = (os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0))
    if hasattr(os, "getuid"):
        held = _the_former_folder_walked(folder)
        try:
            if not _ours(os.fstat(held).st_uid):
                raise PermissionError(errno.EPERM, os.strerror(errno.EPERM), str(old))
            named = os.stat(old.name, dir_fd=held, follow_symlinks=False)
            if stat.S_ISLNK(named.st_mode):
                raise NotAPlainFile(errno.EINVAL, "not a regular file", str(old))
            if not _ours(named.st_uid):
                raise PermissionError(errno.EPERM, os.strerror(errno.EPERM), str(old))
            fd = os.open(old.name, flags, dir_fd=held)
        finally:
            os.close(held)
    else:
        try:
            _windows_judge_the_whole_path(folder)
        except DataFolderRefused:
            raise FormerFolderNotCopied(errno.EPERM, FORMER_FOLDER_NOT_COPIED, str(folder)) from None
        if os.path.islink(old):
            raise NotAPlainFile(errno.EINVAL, "not a regular file", str(old))
        if _whose(old) == _ANOTHERS:
            raise PermissionError(errno.EPERM, os.strerror(errno.EPERM), str(old))
        fd = os.open(old, flags)
    try:
        seen = os.fstat(fd)
    except OSError:
        os.close(fd)
        raise
    if not stat.S_ISREG(seen.st_mode):
        os.close(fd)
        raise NotAPlainFile(errno.EINVAL, "not a regular file", str(old))
    if not _opened_is_ours(fd):
        os.close(fd)
        raise PermissionError(errno.EPERM, os.strerror(errno.EPERM), str(old))
    if _wide(seen) if hasattr(os, "getuid") else _windows_wide(old):
        os.close(fd)                    # one another account could change: not read, left where it is
        raise _Exposed(errno.EPERM, os.strerror(errno.EPERM), str(old))
    with os.fdopen(fd, "rb") as handle:
        data = handle.read(STORE_BYTE_LIMIT + 1)
    if len(data) > STORE_BYTE_LIMIT:
        raise NotAPlainFile(errno.EFBIG, os.strerror(errno.EFBIG), str(old))
    return data


# The mark the data folder carries once the store beside
# the program has been brought into it. Its presence is all it says.
_IMPORTED_BESIDE_THE_PROGRAM = "saved_charts.json.imported-from-beside-the-program"


def _running_from_a_bundle():
    """Whether this is a packaged build (PyInstaller's sys.frozen, or the
    folder it unpacks into, sys._MEIPASS): the folder beside the program is
    then the bundle's own, and no store is brought in from it."""
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def _the_store_beside_the_program_was_imported():
    """Whether the mark stands, and is this account's (_whose): another
    account's file at its name marks nothing."""
    return _whose(SAVED_CHARTS_PATH.parent / _IMPORTED_BESIDE_THE_PROGRAM) in (_OURS, _OUR_LINK)


def _mark_the_store_beside_the_program_imported():
    """Leave the mark, made new (O_EXCL): whatever already stands at its
    name -- the mark, or another account's file -- is never opened. The name
    is opened without waiting (O_NONBLOCK, as the store's other names are)."""
    try:
        os.close(_open(SAVED_CHARTS_PATH.parent / _IMPORTED_BESIDE_THE_PROGRAM,
                         os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                         | getattr(os, "O_NONBLOCK", 0), 0o600))
    except OSError:
        pass


def _the_first_old_store():
    """(place, charts, not_a_file) for the first store kept in an old place
    (_old_stores) that is there: its charts as the loader reads a store, or
    None where it does not read (it is then left where it is); `not_a_file`
    True where what stands there is no regular file -- a pipe, a device, a
    directory -- which is not read. A file of more than
    STORE_BYTE_LIMIT bytes is not read either, and is a store that does not
    read. (None, None, False) where there is none.

    The store in the folder under the app's former name is read only where
    it is a regular file of this account's in a folder of this account's
    (_read_the_former_folders_store): one kept there as a link is no
    regular file, and is not read; a folder of another account's is no
    place this account kept a store, and is passed over as if it were not
    there; a store of another account's in it does not read."""
    former = _the_former_folders_store()
    for old in _old_stores():
        if old == former and (_former_folder_not_this_accounts(old.parent) or _not_this_accounts(old.parent)):
            continue
        if not old.exists():
            continue
        try:
            data = (_read_the_former_folders_store(old) if old == former
                    else _read_regular_file(old, STORE_BYTE_LIMIT, judged=False))   # beside the program
        except (FileNotFoundError, NotADirectoryError):
            continue                    # nothing there (looked at through the folder judged)
        except NotAPlainFile as exc:
            return old, None, exc.errno != errno.EFBIG      # one too large is a store that does not read
        except OSError:
            return old, None, False
        try:
            return old, _parse_chart_mapping(data), False
        except (ValueError, RecursionError):
            return old, None, False
    return None, None, False


def _the_old_store():
    """The charts of the first store kept in an old place (_old_stores)
    that is there, read as the loader reads a store; None where there is
    none, or it does not read (it is then left where it is)."""
    return _the_first_old_store()[1]


def bring_in_the_old_store():
    """With the store's lock held by the caller: where there is no store
    yet, write the first store kept in an old place (_the_old_store) into
    it, once. True when it was written. A store there that does not read is
    left where it is, and nothing is written. The store beside the program,
    once brought in, is marked so and not brought in again, and
    this thread's store_notices() says it was."""
    if _folder_not_to_be_used(SAVED_CHARTS_PATH.parent) or _lexists(SAVED_CHARTS_PATH):
        return False
    place, legacy, _not_a_file = _the_first_old_store()
    if legacy is None:
        return False
    try:
        _write_the_store(json.dumps(legacy, indent=2))
    except OSError:
        return False
    if place == _LEGACY_SAVED_CHARTS_PATH:
        _mark_the_store_beside_the_program_imported()
        _STORE_LOADED.imported = True
    return True


def _move_the_old_store():
    """The store kept in an old place (_old_stores), written into the
    per-user folder once, while the store there does not exist yet. None
    when that is done, or was not to be done; the DataLockBusy (or a
    DataLockBlocked, or a DataLockUnavailable) when the store's lock
    could not be had, and nothing was written.

    The move asked whether
    the store existed and then wrote it, holding nothing, so a save made in
    between (another window, another launch) was written over by the old
    file's charts, though it had said "Saved". The question and the write
    are now made under the store's lock, the question asked again inside it;
    with the lock held elsewhere past its bound nothing is written, and a
    later load makes the move.

    Such a load listed nothing and said
    nothing, and a save made before the next load wrote the store, after
    which the move was never made. The load now says so (store_notices'
    'unmoved'), and that window's save makes the move under its own lock
    (bring_in_the_old_store) before it adds its record. Only an old store
    that reads is moved, or waited for: else the load was found
    telling the reader to reload for charts that a reload would not list
    (an old store that does not read is left as it is, said or not, as it
    always was)."""
    try:
        with saved_charts_lock():
            bring_in_the_old_store()
    except DataLockBusy as exc:
        return exc
    return None


def load_saved_charts():
    global LAST_STORE_ERROR, LAST_STORE_UNREADABLE
    LAST_STORE_ERROR = None
    LAST_STORE_UNREADABLE = False
    _STORE_LOADED.digest = None
    _STORE_LOADED.copy, _STORE_LOADED.unreadable = None, False         # store_notices()
    _STORE_LOADED.unmoved = None
    _STORE_LOADED.recovered = 0
    _STORE_LOADED.imported = _STORE_LOADED.old_not_a_file = False
    if _folder_not_to_be_used(SAVED_CHARTS_PATH.parent):
        return {}                                       # another account's folder, or one that cannot be listed
    _STORE_LOADED.recovered = _tidy_stray_temp_files(SAVED_CHARTS_PATH, saved_charts_lock, _reads_as_a_store,
                                                     STORE_BYTE_LIMIT, former_name=True)
    # A store of the user's that another account could change, found since
    # the launch (or one the launch could not move), is set aside now; where
    # it cannot be, it is not read (set_aside_notices says which).
    try:
        if _set_aside_if_others_could_write(SAVED_CHARTS_PATH) == 'held':
            return {}
    except OSError:
        pass
    if _whose(SAVED_CHARTS_PATH) == _ANOTHERS:
        # Another account's file or link at the store's name: a store that
        # cannot be read, and of which no copy is made. Nothing of it is
        # read or followed. A link of this account's is not followed either
        # (_open_this_accounts_file: _Exposed), and the page says so.
        LAST_STORE_UNREADABLE = True
        _STORE_LOADED.unreadable = True
        return {}
    if not _lexists(SAVED_CHARTS_PATH):
        _place, old_charts, _STORE_LOADED.old_not_a_file = _the_first_old_store()
        if old_charts:                                          # one holding a chart
            _STORE_LOADED.unmoved = _move_the_old_store()
    if _lexists(SAVED_CHARTS_PATH):
        # Read once: the mapping, the digest this load leaves and the
        # recovery copy are all of the same bytes. Only a regular file is
        # read: anything else is a store that cannot be read.
        try:
            data = _read_regular_file(SAVED_CHARTS_PATH, STORE_BYTE_LIMIT)
        except _Exposed:
            return {}               # others could change it, or a link at its name: not read, and no copy made
        except OSError:
            data = None
        charts = None
        if data is not None:
            _STORE_LOADED.digest = hashlib.sha256(data).hexdigest()
            try:
                charts = _parse_chart_mapping(data)
            except (ValueError, RecursionError):
                charts = None
        if charts is None:
            # Malformed JSON, or valid JSON of the wrong shape. The bytes are
            # kept beside the file before anything is allowed to write over
            # them, and the name of the copy is left where the sidebar can
            # name it.
            LAST_STORE_ERROR = _preserve_unreadable_store(SAVED_CHARTS_PATH, data, STORE_BYTE_LIMIT)
            LAST_STORE_UNREADABLE = True
            _STORE_LOADED.copy, _STORE_LOADED.unreadable = LAST_STORE_ERROR, True
            return {}
        return charts
    return {}


# The digest of the bytes the
# last load_saved_charts() in this thread parsed. A session used to take its
# digest by reading the file a second time, just after its load (and just
# after its own write), so another window's write landing in between was
# taken as this window's own, and its next save wrote over that record under
# a bare "Saved". A Streamlit session runs its script in a thread of its own,
# so the digest is kept per thread: one window's load cannot hand another
# its digest.
_STORE_LOADED = threading.local()


def loaded_saved_charts_digest():
    """The digest of the bytes the last load_saved_charts() in this thread
    parsed -- malformed ones included, which it copied aside -- or None when
    it found no file or could not read it."""
    return getattr(_STORE_LOADED, "digest", None)


# What a load found for the sidebar to say -- the unreadable store's copy, or
# that no copy could be made -- was left only in LAST_STORE_ERROR and
# LAST_STORE_UNREADABLE, which every window of one server shares. Another
# window's load landing between this window's load and its read of them
# cleared this window's notice, or handed it the other's copy. They are kept
# per thread as well, as the digest is and the preferences' notices
# are, and the app reads them through store_notices(). The module's
# names are still set, as the last load in any window left them.
#
# A load that kept a cut-short save aside says so,
# once and naming no file; how many it kept is kept here too.

def store_notices():
    """What this thread's -- this window's -- last load_saved_charts()
    found, as a dict: 'copy', the name of the copy an unreadable store was
    kept as (LAST_STORE_ERROR's); 'unreadable', whether the store could not
    be read (LAST_STORE_UNREADABLE's); 'recovered', how many saves cut short
    it found and kept aside beside the saved charts; 'unmoved',
    whether a store kept in an old place, one that reads, could not be moved
    in for the store's lock; 'blocked', the folder named when that
    was something standing under the lock's name, or None;
    'unlocked', whether that was the folder refusing the lock call itself
    (DataLockUnavailable);
    'imported', whether it brought in the store kept beside the program;
    'old_not_a_file', whether what stands where an
    older version kept its store is no regular file, and was not read.
    What was set aside, or could not be, is asked at each run, not kept
    from a load (set_aside_notices)."""
    unmoved = getattr(_STORE_LOADED, "unmoved", None)
    return {"copy": getattr(_STORE_LOADED, "copy", None),
            "unreadable": getattr(_STORE_LOADED, "unreadable", False),
            "recovered": getattr(_STORE_LOADED, "recovered", 0),
            "unmoved": unmoved is not None,
            "blocked": unmoved.folder if isinstance(unmoved, DataLockBlocked) else None,
            "unlocked": isinstance(unmoved, DataLockUnavailable),
            "imported": getattr(_STORE_LOADED, "imported", False),
            "old_not_a_file": getattr(_STORE_LOADED, "old_not_a_file", False)}


def saved_charts_digest(charts):
    """The digest of the bytes write_saved_charts(charts) writes. A session
    keeps the digest of what it last read or wrote, and refuses to write
    over a file whose digest has moved; that is the
    digest of its own bytes, never of a second read of the file."""
    return hashlib.sha256(_saved_charts_text(charts).encode("utf-8")).hexdigest()


def _saved_charts_text(charts):
    """The store's text for `charts`, as write_saved_charts writes it."""
    return json.dumps(charts, indent=2)


@dataclass(frozen=True)
class StoreAsItStands:
    """What a write finds in the store's place, read once, just before it
    writes. `state` is one of:

    - 'absent': no file, or another account's file or link at the store's
      name, which is never read and which a write replaces at the name with
      a store of this account's (_write_text_atomically); `charts` is {},
      `digest` None;
    - 'readable': a store; `charts` is its mapping, `digest` its bytes';
    - 'malformed': bytes that are not a store (a hand edit's trailing comma,
      the wrong shape); `charts` None, `digest` its bytes';
    - 'unreadable': bytes that cannot be read at all (a file the account may
      not read, a directory in its place, a link of this account's to another
      account's file, which is neither read nor written through); `charts`
      and `digest` None.

    `copy` is the name of the recovery copy of a malformed store's bytes,
    when one was asked for and could be made; else None."""
    state: str
    charts: dict = None
    digest: str = None
    copy: str = None


def saved_charts_as_they_stand(keep_aside=False):
    """The store as a write is about to find it. The digest a session compared
    before writing could not tell
    a missing file from one it could not read -- both were None -- so a store
    announced as unreadable was taken as unchanged and written over by the
    next save, and every saved chart with it.

    A write may replace an absent or a readable store, or a malformed one
    whose bytes are kept beside it first: with `keep_aside` the malformed
    bytes are copied (once per content, as the loader copies them) and the
    copy's name is returned. An unreadable store has no bytes to copy and
    must not be replaced at all; nor may a malformed one whose copy could not
    be made (`copy` None)."""
    path = SAVED_CHARTS_PATH
    if _folder_not_to_be_used(path.parent):
        return StoreAsItStands('unreadable', None, None, None)      # another account's folder, or one not listed
    whose = _whose(path)
    if whose == _ANOTHERS:
        return StoreAsItStands('absent', {}, None, None)            # replaced at the name, never read
    if whose == _LEADS_TO_ANOTHERS:
        return StoreAsItStands('unreadable', None, None, None)
    present = _lexists(path)
    if not present:
        return StoreAsItStands('absent', {}, None, None)
    try:
        data = _read_regular_file(path, STORE_BYTE_LIMIT)
    except OSError:
        return StoreAsItStands('unreadable', None, None, None)
    digest = hashlib.sha256(data).hexdigest()
    try:
        # The loader's reading, the one parser (_parse_chart_mapping):
        # utf-8-sig, then JSON, then the shape. UnicodeDecodeError and
        # JSONDecodeError are ValueErrors, as are the wrong shape, an integer
        # literal past Python's digit limit and a chart named twice;
        # JSON nested past the interpreter's depth raises RecursionError,
        # and is no more a store than they are.
        charts = _parse_chart_mapping(data)
    except (ValueError, RecursionError):
        copy = _preserve_unreadable_store(path, data) if keep_aside else None
        return StoreAsItStands('malformed', None, digest, copy)
    return StoreAsItStands('readable', charts, digest, None)


def write_saved_charts(charts):
    """Write `charts` over the store; True when the disk took it. The bytes
    written are those saved_charts_digest(charts) digests. False, and
    nothing written, where a link stands at the store's name, which the app
    never follows (_write_text_atomically).

    A mapping nested past what json.dumps can write raises
    RecursionError ("Stack overflow"), which reached the page raw. The
    parser refuses such a store before a write is asked of it; a mapping
    that still cannot be written is a write that failed, as any other.

    A store whose text passes STORE_TEXT_LIMIT,
    which the reader refuses, was written, and the next load listed nothing
    and copied it aside. It is now a write that failed, and nothing is
    written."""
    return _write_saved_charts(charts)


def _write_saved_charts(charts):
    """write_saved_charts."""
    if _folder_not_to_be_used(SAVED_CHARTS_PATH.parent):
        return False                                    # another account's folder, or one not listed
    try:
        _validate_chart_mapping(charts)
        _within_the_store_text_limit(charts)
        _write_the_store(_saved_charts_text(charts))
        return True
    except (OSError, ValueError, RecursionError):
        return False


def _write_the_store(text):
    """Write `text` over the store, keeping its present bytes as a version
    first (_keep_a_version). Every write of the store comes here, and every
    caller holds the store's lock (saved_charts_lock)."""
    _keep_a_version(SAVED_CHARTS_PATH)
    _write_text_atomically(SAVED_CHARTS_PATH, text)


# Before each write over the store, the bytes it holds are kept beside it, in
# the data folder, as `saved_charts.json.previous-<YYYYMMDD-HHMMSS>-<nnn>`
# (the time in UTC, then a count within that second), and only the newest
# VERSIONS_KEPT of them are kept. A write that leaves the store a valid but
# empty or wrong one can then be undone by hand: the charts it wrote over
# are in the newest version, byte for byte.
#
# A version is kept only when the store's bytes differ from the newest
# version's, so a run of writes that change nothing keeps one, and writes of
# one bad store over and over never push the good versions out. The names
# sort by age: a version is never named older than the newest one there (a
# clock set back keeps the newest's time and counts on from it), and the
# count is padded to three digits; where a second holds more, the age is
# read from the name's numbers, not its letters. Only names of exactly that
# form, and only regular files, are versions: a name that merely starts
# alike is neither read nor removed.
#
# A version that cannot be kept -- a full disk, a folder this account may
# write in but not list, a name it cannot make -- is passed over and the
# write goes ahead, as the recovery copies are passed over when they cannot
# be made; the page says nothing of it.
VERSIONS_KEPT = 10

_VERSION_FORM = re.compile(r"\.previous-([0-9]{8}-[0-9]{6})-([0-9]{3,})")


def _version_key(store_name, name):
    """(stamp, count) for a version of the store named `store_name`, from
    its file name; None for any other name."""
    if not name.startswith(store_name):
        return None
    found = _VERSION_FORM.fullmatch(name, len(store_name))
    return None if found is None else (found.group(1), int(found.group(2)))


def _versions(folder, store_name):
    """The versions in `folder` -- regular files of this account's (_whose),
    the name of exactly the form -- oldest first, as (key, path). OSError
    where the folder cannot be listed. Another account's file under a
    version's name is no version: it is neither read, counted nor removed,
    so that none put there can push the user's own versions out."""
    found = []
    for name in _listdir(folder):
        key = _version_key(store_name, name)
        if key is None:
            continue
        try:
            if not stat.S_ISREG(_lstat(folder / name).st_mode) or _whose(folder / name) != _OURS:
                continue
        except OSError:
            continue
        found.append((key, folder / name))
    return sorted(found)


def _keep_a_version(path):
    """Keep the bytes of the store at `path` as its newest version, unless
    there is no store, or they are the newest version's already; then
    remove the oldest beyond VERSIONS_KEPT. The version's name, or None
    when none was made. Never raises: a version not kept costs no write.

    The version is written to a temporary file of its own, synced, and
    only then given its name, which is never one already there (a hard
    link, or on Windows a rename, refuses a name that is taken); so a
    version under its name is always whole, and it is on the disk before
    the store is replaced. It takes the owner's part of the store's mode,
    as the store's temporary file does (_new_version), so it is never wider
    than the store, and never open to its group or others. A store that
    is not this account's (_read_regular_file, judged) is never read, and no
    version of it is kept."""
    try:
        try:
            data = _read_regular_file(path, STORE_BYTE_LIMIT)
        except FileNotFoundError:
            return None                                 # no store yet: nothing to keep
        folder = path.parent
        versions = _versions(folder, path.name)
        if versions:
            try:
                if _read_regular_file(versions[-1][1], len(data)) == data:
                    return None
            except OSError:
                pass
        stamp = _version_stamp()
        count = 1
        if versions:
            newest = versions[-1][0]
            if newest[0] >= stamp:
                stamp, count = newest[0], newest[1] + 1
        mode = stat.S_IMODE(_stat(path).st_mode)
        name = _new_version(folder, path.name, data, stamp, count, mode)
    except (OSError, ValueError):
        return None
    try:
        _drop_old_versions(folder, path.name)
    except OSError:
        pass
    return name


def _version_stamp():
    """The time now, in UTC, as a version's name gives it."""
    return f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"


def _new_version(folder, store_name, data, stamp, count, mode):
    """Write `data` at the owner's part of `mode` (its group's and others'
    never carried) under the first free version name from (stamp, count)
    on; its name. OSError where it cannot be written."""
    mode &= 0o700
    tmp, fd = _new_temp_file(folder / f"{store_name}.previous", mode)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _chmod(tmp, mode)                         # the umask may have cut it
        for n in range(count, count + 1000):
            name = f"{store_name}.previous-{stamp}-{n:03d}"
            try:
                if os.name == "nt":
                    _rename(tmp, folder / name)       # refuses a name that is taken
                else:
                    _link(tmp, folder / name)         # refuses a name that is taken
            except FileExistsError:
                continue
            except OSError:
                # A filesystem with no hard links (FAT, exFAT): the name is
                # asked free and the file renamed to it, under the store's
                # lock, which every maker of a version holds.
                if _lexists(folder / name):
                    continue
                _replace(tmp, folder / name)
            _sync_folder(folder)
            return name
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(folder))
    finally:
        _remove(tmp)


def _drop_old_versions(folder, store_name):
    """Remove the oldest versions beyond VERSIONS_KEPT, and the temporary
    file of a version whose write was killed before it was named
    (`<store>.previous.<16 hex>.tmp`, a regular file of this account's
    last written before this launch, as the strays of a write are judged);
    one that cannot be removed is left, and so is another account's."""
    for _key, old in _versions(folder, store_name)[:-VERSIONS_KEPT]:
        _remove(old)
    left = re.compile(re.escape(store_name) + r"\.previous\.[0-9a-f]{16}\.tmp")
    for name in _listdir(folder):
        if not left.fullmatch(name):
            continue
        try:
            seen = _lstat(folder / name)
            if stat.S_ISREG(seen.st_mode) and seen.st_mtime < _LAUNCHED_AT and _whose(folder / name) == _OURS:
                _remove(folder / name)
        except OSError:
            pass

# --- Preferences -------------------------------------------
# The readings and display choices, kept across runs in the same per-user
# directory as the saved charts. Streamlit's
# own persist_state lives only as long as the session, so a restart needs
# a file. Only the store keys the engine lists (PREFERENCE_KEYS, with what
# the preferences mean) are kept, plus the name of the last chart loaded,
# which the app opens on. Missing or unknown keys are ignored on read, as
# the saved-charts loader ignores them. The harness sets
# ALMUTEN_NO_PREFERENCES=1 so a test can neither read a real file nor leak a
# reading into the next test.
PREFERENCES_PATH = DATA_DIR / "preferences.json"


def preferences_enabled():
    return os.environ.get("ALMUTEN_NO_PREFERENCES") != "1"


# The most bytes a preferences file
# may hold, as the store has its STORE_TEXT_LIMIT. A file of every key with
# a long home place's name is a few kilobytes; one past this is not read
# (nor copied aside), and the writer refuses to write one, so that the app
# never writes what it will not read back.
PREFERENCES_BYTE_LIMIT = 1024 * 1024

# The name of the copy the last read of an unreadable preferences file made,
# or None; and whether that read found the file unreadable at all, whether
# or not a copy could be made. The same pair the saved charts' loader keeps
# (LAST_STORE_ERROR, LAST_STORE_UNREADABLE), read by the sidebar.
LAST_PREFERENCES_ERROR = None
LAST_PREFERENCES_UNREADABLE = False
# Whether the last remember_preference / forget_preference gave up
# because another window or launch held the preferences' lock past
# LOCK_WAIT_SECONDS (nothing was written), read by the sidebar.
LAST_PREFERENCES_BUSY = False

# The three names above
# are the module's, and every window of one server shares them. A second
# window's read or write landing between one window's call and that
# window's reading of them reset them or set them, so a window's own notice
# could be lost, or another window's shown to it. Each window now reads its
# own: what its last read or write of the preferences found is kept per
# thread as well (a window's script runs in a thread of its own; the
# store's digest is kept so for the same reason), and read through
# preferences_notices(). The module's names are still set, as the last call
# in any window left them.
_PREFERENCES_NOTICES = threading.local()
_PREFERENCES_NOTICE_DEFAULTS = (("copy", None), ("unreadable", False), ("busy", False), ("blocked", None))


def _reset_preferences_notices():
    for name, default in _PREFERENCES_NOTICE_DEFAULTS:
        setattr(_PREFERENCES_NOTICES, name, default)


def preferences_notices():
    """What this thread's -- this window's -- last read or write of the
    preferences found, as a dict: 'copy', the name of the copy an unreadable
    file was kept as (LAST_PREFERENCES_ERROR's); 'unreadable', whether the
    file could not be read (LAST_PREFERENCES_UNREADABLE's); 'busy', whether
    the lock was held elsewhere past the bound (LAST_PREFERENCES_BUSY's);
    'blocked', the folder in which something stands under the lock's name,
    or None; 'off', whether preferences are switched off for
    this launch (ALMUTEN_NO_PREFERENCES), which holds for
    every read and write alike."""
    notices = {name: getattr(_PREFERENCES_NOTICES, name, default) for name, default in _PREFERENCES_NOTICE_DEFAULTS}
    notices["off"] = not preferences_enabled()
    return notices



def _read_preferences_file(exposed=None):
    """The preferences file's object exactly as written -- every key, valid
    or not -- or {} when there is no file, or None when there is one that
    cannot be read as an object (bad bytes, bad JSON, the wrong shape, a
    key given twice in one object, JSON nested past the interpreter's
    depth, no permission, a folder in its place; a pipe
    or a device in its place, or more than PREFERENCES_BYTE_LIMIT bytes;
    another account's file or link at its name, which is neither read nor
    followed: no copy of it can be made, so it is left as it is and not
    written over; and a file another account could change, or a link of
    this account's at its name, which is never followed, _Exposed, where
    True is added to `exposed`, when given)."""
    if _whose(PREFERENCES_PATH) == _ANOTHERS:
        return None
    if not _lexists(PREFERENCES_PATH):
        return {}
    try:
        # utf-8-sig reads a leading byte-order mark (what Notepad writes) and
        # a file without one unchanged, as the saved charts' reader does.
        raw = _parse_preferences(_read_regular_file(PREFERENCES_PATH, PREFERENCES_BYTE_LIMIT))
    except _Exposed:
        if exposed is not None:
            exposed.append(True)
        return None
    except (ValueError, RecursionError, OSError):
        # Undecodable bytes and bad JSON are both ValueError. JSON nested past
        # the interpreter's depth
        # (200,000 open brackets) raises RecursionError, which escaped this
        # reader and killed the launch with a raw traceback; it is no more a
        # preferences file than bad JSON is, so it is unreadable, copied
        # aside and named as any unreadable file is (the store's write
        # path reads it so already).
        return None
    return raw if isinstance(raw, dict) else None


def _keep_unreadable_preferences():
    """Copy an unreadable preferences file beside itself (once per content,
    by the saved charts' own copier, which names the copy after the file it
    is given) and note the copy, or that none could be made. True when the
    bytes are kept and the file may be written over."""
    global LAST_PREFERENCES_ERROR, LAST_PREFERENCES_UNREADABLE
    LAST_PREFERENCES_ERROR = _preserve_unreadable_store(PREFERENCES_PATH, limit=PREFERENCES_BYTE_LIMIT)
    LAST_PREFERENCES_UNREADABLE = True
    _PREFERENCES_NOTICES.copy, _PREFERENCES_NOTICES.unreadable = LAST_PREFERENCES_ERROR, True
    return LAST_PREFERENCES_ERROR is not None


def load_preferences():
    """The stored preferences as a dict, keys limited to PREFERENCE_KEYS and
    'last_chart', values limited to what the widget behind each key can
    hold; an empty dict when there is no file, or it is unreadable, or the
    harness has switched preferences off.

    An entry whose value is the wrong type or not one of its options is
    dropped, so the reading falls to its default -- the app opens, and the
    file is left as it is until the next reading is set.

    A file that cannot be read at all is copied beside itself first, as the
    saved charts' loader does (else a file
    beginning with a byte-order mark was read as empty, and the same launch
    wrote over it -- home place, last chart and readings gone, with no copy
    and no sentence). The copy's name, or that none could be made, is left
    in LAST_PREFERENCES_ERROR / LAST_PREFERENCES_UNREADABLE for the sidebar,
    and in this window's preferences_notices()."""
    global LAST_PREFERENCES_ERROR, LAST_PREFERENCES_UNREADABLE
    LAST_PREFERENCES_ERROR = None
    LAST_PREFERENCES_UNREADABLE = False
    _reset_preferences_notices()
    if not preferences_enabled() or _not_this_accounts(PREFERENCES_PATH.parent):
        return {}
    if _folder_not_to_be_used(PREFERENCES_PATH.parent):
        return {}                       # a folder that cannot be listed: nothing read from it
    _tidy_stray_temp_files(PREFERENCES_PATH, preferences_lock, _reads_as_preferences,
                           PREFERENCES_BYTE_LIMIT)
    # A file others could change, set aside now where the launch did not, or
    # not read where it cannot be (set_aside_notices says which); no copy of
    # it is made.
    try:
        if _set_aside_if_others_could_write(PREFERENCES_PATH) == 'held':
            return {}
    except OSError:
        pass
    exposed = []
    raw = _read_preferences_file(exposed)
    if exposed:
        return {}
    if raw is None:
        _keep_unreadable_preferences()
        return {}
    return _the_engine()._loadable_preferences(raw)


def write_preferences(prefs):
    """Write `prefs` over the preferences file; True when the disk took it.
    False, and nothing written, where a link stands at its name, as for the
    store (write_saved_charts)."""
    return _write_preferences(prefs)


def _write_preferences(prefs):
    """write_preferences."""
    if not preferences_enabled() or _folder_not_to_be_used(PREFERENCES_PATH.parent):
        return False
    try:
        text = json.dumps(prefs, indent=2, sort_keys=True)
        if len(text.encode("utf-8")) > PREFERENCES_BYTE_LIMIT:
            return False                # never written past what the reader reads back
        _write_text_atomically(PREFERENCES_PATH, text)
        return True
    except (OSError, ValueError):       # ValueError: json.dumps past the integer string limit
        return False

# Each session wrote its own copy of
# the whole preferences file, read once at its launch, so a window opened
# before another set a home place or saved a chart erased both from the
# file the moment any of its own readings moved. The two functions below
# read the file again at the write, as a load reads it, and change one key
# in that: every other key stands as whichever window wrote it left it. An
# entry no load would keep (an unknown key, a value no widget can hold) is
# dropped by the write, as the whole-file write always dropped it.
#
# A file that cannot be read is written over only once its bytes are kept
# beside it; when no copy can be made it is left as it is and
# nothing is written. LAST_PREFERENCES_ERROR / LAST_PREFERENCES_UNREADABLE
# say which, as after a load.

def _preferences_as_they_stand(fallback=None):
    """The file's entries, as a load keeps them, to change one key in, and
    True; when the file is unreadable, a copy of `fallback` (the session's
    own preferences) once the file's bytes are kept beside it, and False;
    (None, False) when no copy of them could be made, or the file is one
    another account could change, which is neither read nor written over."""
    global LAST_PREFERENCES_ERROR, LAST_PREFERENCES_UNREADABLE
    LAST_PREFERENCES_ERROR = None
    LAST_PREFERENCES_UNREADABLE = False
    _PREFERENCES_NOTICES.copy, _PREFERENCES_NOTICES.unreadable = None, False
    exposed = []
    raw = _read_preferences_file(exposed)
    if exposed:
        return None, False          # a file others could change: not read, and not written over
    if raw is None:
        return (dict(fallback or {}) if _keep_unreadable_preferences() else None), False
    return _the_engine()._loadable_preferences(raw), True


def remember_preference(key, value, fallback=None):
    """Set `key` to `value` in the preferences file as it stands now, and
    change no other entry a load keeps. True when the file holds the change.
    `fallback` is what the file is rebuilt from if it has become unreadable
    since it was loaded.

    Whether the value is a change is judged here, against the file as it
    stands, and not against any window's copy of it: window A opened X, window
    B then opened Y, and A opening X
    again wrote nothing, because A's own copy already said X, so the file
    kept B's earlier choice over A's later one. A file that already holds
    the value is not written at all.

    False, with LAST_PREFERENCES_BUSY set and nothing written,
    when the lock is held elsewhere past LOCK_WAIT_SECONDS.
    False, with preferences_notices()['blocked'] naming the folder and
    nothing written, when something stands under the lock's name. False,
    with neither set and nothing written, when the folder refuses the lock
    call itself (DataLockUnavailable): the page says the file was not
    written, as for any write it did not take."""
    global LAST_PREFERENCES_BUSY
    LAST_PREFERENCES_BUSY = False
    _reset_preferences_notices()
    if not preferences_enabled() or _folder_not_to_be_used(PREFERENCES_PATH.parent):
        return False
    # The read, the change and the write under the preferences'
    # lock, so that another window's key set in between is not lost.
    try:
        with preferences_lock():
            prefs, from_file = _preferences_as_they_stand(fallback)
            if prefs is None:
                return False
            if from_file and key in prefs and prefs[key] == value:
                return True
            prefs[key] = value
            return write_preferences(prefs)
    except DataLockBlocked as exc:
        _PREFERENCES_NOTICES.blocked = exc.folder
        return False
    except DataLockUnavailable:
        return False                    # the folder refuses the lock call: refused as a write the file did not take
    except DataLockBusy:
        LAST_PREFERENCES_BUSY = True
        _PREFERENCES_NOTICES.busy = True
        return False


_ANY_VALUE = object()

def forget_preference(key, only_if=_ANY_VALUE, fallback=None):
    """Remove `key` from the preferences file as it stands now, and change
    no other entry a load keeps; with `only_if`, only while the file holds that
    value under `key`, so that a value another window has written since is
    left. True when the file no longer holds what was to be forgotten.
    `fallback`, the bounded wait, the obstruction,
    a lock call refused, and the notices as in remember_preference."""
    global LAST_PREFERENCES_BUSY
    LAST_PREFERENCES_BUSY = False
    _reset_preferences_notices()
    if not preferences_enabled() or _folder_not_to_be_used(PREFERENCES_PATH.parent):
        return False
    try:
        with preferences_lock():        # as in remember_preference
            prefs, _from_file = _preferences_as_they_stand(fallback)
            if prefs is None:
                return False
            if key not in prefs:
                return True                 # nothing to remove: the file is not touched
            if only_if is not _ANY_VALUE and prefs[key] != only_if:
                return True                 # another value now: not this one to forget
            del prefs[key]
            return write_preferences(prefs)
    except DataLockBlocked as exc:
        _PREFERENCES_NOTICES.blocked = exc.folder
        return False
    except DataLockUnavailable:
        return False                    # the folder refuses the lock call: refused as a write the file did not take
    except DataLockBusy:
        LAST_PREFERENCES_BUSY = True
        _PREFERENCES_NOTICES.busy = True
        return False


# --- What was set aside, and its restore ------------------------------------
# A file of the saved charts or the preferences that another account could
# change is set aside at the launch, unread (_set_aside_if_others_could_write),
# and a link of the user's at either name that leads to one is not read
# (_open_this_accounts_file). The page says so while either awaits, in every
# window, and offers one button, which brings them in (restore_set_aside).

def _set_aside_names(path, names):
    """The files in `names` set aside from `path`'s name, oldest first:
    `<name>.set-aside-<time>`, regular files of this account's."""
    form = re.compile(re.escape(path.name + _SET_ASIDE) + r"[0-9]{8}-[0-9]{6}(?:-[0-9]+)?")
    found = []
    for name in sorted(names):
        if not form.fullmatch(name):
            continue
        aside = path.with_name(name)
        try:
            if _whose(aside) == _OURS and stat.S_ISREG(_lstat(aside).st_mode):
                found.append(aside)
        except OSError:
            continue
    return found


def _what_stands_exposed(path):
    """'held' where the name `path` holds a regular file of this account's
    that another account could change (one that could not be set aside);
    'unfollowed' where it is a link of this account's, which the app never
    follows, wherever it leads; else None. The page says each in its own
    words, with no button: nothing is set aside behind a link, and behind a
    link no other account need be able to change anything."""
    whose = _whose(path)
    if whose == _OURS:
        return 'held' if _exposed_at_the_name(path) else None
    if whose in (_OUR_LINK, _LEADS_TO_ANOTHERS):
        return 'unfollowed'
    return None


def _set_aside_kinds():
    """The store's name and the preferences', each with its limit, its lock
    and how its bytes are read and written back; the preferences' only
    while preferences are on."""
    kinds = [(SAVED_CHARTS_PATH, STORE_BYTE_LIMIT, saved_charts_lock, _restore_a_store)]
    if preferences_enabled():
        kinds.append((PREFERENCES_PATH, PREFERENCES_BYTE_LIMIT, preferences_lock, _restore_preferences))
    return kinds


def set_aside_notices():
    """What the page says of what was set aside, asked at each run of every
    window, as a dict: 'awaiting', whether a file of the saved charts or the
    preferences set aside awaits the restore (restore_set_aside);
    'unfollowed', whether a link of the user's stands at either name, which
    is never followed (the restore does not read it); 'held', whether such a file stands at its own name unread, because
    it could not be set aside (on Windows, another account holding it open
    without sharing deleting refuses the rename). All False where the folder
    is not to be used: its own sentence stands."""
    found = {"awaiting": False, "unfollowed": False, "held": False}
    folder = SAVED_CHARTS_PATH.parent
    if _folder_not_to_be_used(folder):
        return found
    try:
        names = _list_the_data_folder(folder)
    except OSError:
        return found
    for path, _limit, _lock, _restore in _set_aside_kinds():
        if _set_aside_names(path, names):
            found["awaiting"] = True
        standing = _what_stands_exposed(path)
        if standing is not None:
            found[standing] = True
    return found


def _read_what_was_set_aside(path, limit, tally=None):
    """The bytes of the file set aside at `path` -- a regular file of this
    account's, opened without following a link -- and its fstat. Its size is
    read from what was opened before a byte is read, and one past `limit` is
    refused; the read stops at `limit` + 1 bytes, so one that grows past it
    while it is read is refused as well (NotAPlainFile, EFBIG). The bytes
    read are added to `tally`'s second place, where given."""
    if _whose(path) != _OURS:
        raise _NotThisAccounts(errno.EPERM, os.strerror(errno.EPERM), str(path))
    fd = _open_regular_file(path, follow_links=False)
    if not _opened_is_ours(fd):
        os.close(fd)
        raise _NotThisAccounts(errno.EPERM, os.strerror(errno.EPERM), str(path))
    with os.fdopen(fd, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if opened.st_size > limit:
            raise NotAPlainFile(errno.EFBIG, os.strerror(errno.EFBIG), str(path))
        data = handle.read(limit + 1)
    if tally is not None:
        tally[1] += len(data)
    if len(data) > limit:
        raise NotAPlainFile(errno.EFBIG, os.strerror(errno.EFBIG), str(path))
    return data, opened


def _merged(current, restored):
    """`current` with each entry of `restored` whose name it does not hold
    added; and whether an entry of `restored` was left out for a name
    `current` holds with another value (the current one is kept)."""
    merged = dict(current)
    left_out = False
    for name, value in restored.items():
        if name not in merged:
            merged[name] = value
        elif merged[name] != value:
            left_out = True
    return merged, left_out


def _restore_a_store(data):
    """Bring the records of the store bytes `data` into the store, under its
    lock (the caller's), through the ordinary writer: those whose names the
    store does not hold added, the store's own kept on a clash. Whether every
    record is in it after (False where a clash left one out); OSError or
    ValueError where nothing could be written."""
    restored = _parse_chart_mapping(data)
    now = saved_charts_as_they_stand()
    if now.state not in ('absent', 'readable'):
        raise ValueError("the saved charts cannot be read to add to")
    merged, left_out = _merged(now.charts or {}, restored)
    if (now.state == 'absent' or merged != now.charts) and not write_saved_charts(merged):
        raise ValueError("the saved charts could not be written")
    return not left_out


def _loadable_restored(raw):
    """The entries of the preferences object `raw` a load keeps, as the
    engine says when called (its _loadable_preferences)."""
    return _the_engine()._loadable_preferences(raw)


def _restore_preferences(data):
    """Bring the entries of the preferences bytes `data` into the
    preferences, as _restore_a_store brings in a store's records, as a load
    keeps them (the engine's _loadable_preferences)."""
    raw = _parse_preferences(data)
    if not isinstance(raw, dict):
        raise ValueError("not preferences")
    restored = _loadable_restored(raw)
    exposed = []
    now = _read_preferences_file(exposed)
    if now is None or exposed:
        raise ValueError("the preferences cannot be read to add to")
    current = _loadable_restored(now) if now else {}
    merged, left_out = _merged(current, restored)
    if (not now or merged != current) and not write_preferences(merged):
        raise ValueError("the preferences could not be written")
    return not left_out


# A file set aside whose charts the restore could not all bring in -- a
# chart of the same name saved since, with other contents -- is kept beside
# the saved charts under this form (`<name>.kept-<time>`), which nothing
# reads: neither a load, nor the restore, nor the launch's look.
_KEPT = ".kept-"


def _keep_beside(aside, opened):
    """Rename the file set aside at `aside` (the one `opened`) to the first
    free `<name>.kept-<time>` beside it, its name before the set-aside; True
    where it was, False where the rename was refused or the name holds
    another file now."""
    name = aside.name.split(_SET_ASIDE, 1)[0]
    stem = f"{name}{_KEPT}{_recovery_stamp()}"
    for n in range(1, 1000):
        kept = aside.with_name(stem if n == 1 else f"{stem}-{n}")
        if _lexists(kept):
            continue
        try:
            if not os.path.samestat(_lstat(aside), opened):
                return False
            _rename(aside, kept)
        except FileExistsError:
            continue
        except OSError:
            return False
        return True
    return False


# Each file set aside that a restore could not bring back in this process,
# known by what it was (its device and inode, its size and the time it was
# last changed): not read again by a later press while it stays so. Set to
# nothing whenever the module is loaded.
_RESTORE_FAILED = set()


def _restore_key(seen):
    """What a file set aside is known by among those a restore could not
    bring back (_RESTORE_FAILED)."""
    return seen.st_dev, seen.st_ino, seen.st_size, seen.st_mtime_ns


def _its_other_names_removed(aside, asides, opened):
    """Remove, unread, each name in `asides` but `aside` that is the file
    brought back from `aside` (the same device and inode as `opened`, what
    its read opened; looked at without following a link, through the
    folder held), and return those removed. A name that is another file, or
    that cannot be looked at or removed, is left for the press to take as
    it comes."""
    removed = set()
    for other in asides:
        if other == aside:
            continue
        try:
            if os.path.samestat(_lstat(other), opened):
                _unlink(other)
                removed.add(other)
        except OSError:
            pass
    return removed


def restore_set_aside(kept=None):
    """The page's one button: bring back what was set aside. True where
    nothing awaits after it (set_aside_notices: nothing set aside; a link at
    either name and a file that could not be set aside are not the
    restore's); False where something could not be brought back, or was
    left for a later press, and stays as it is, under its recovery name.

    Each file set aside from the store's name (and the preferences', while
    they are on), oldest first, is opened without following a link, as a
    regular file of this account's; its size is read from what was opened
    and one past its own limit (STORE_BYTE_LIMIT, PREFERENCES_BYTE_LIMIT)
    refused, and the read stops at the limit, so one that grows while it is
    read is refused too (_read_what_was_set_aside). Its bytes are read as a
    load reads the file, and written under its lock through the ordinary
    writer, which makes a new file: a descriptor or a hard link another
    account held on the file set aside reaches nothing the app reads after.
    A store or preferences saved since the file was set aside keeps its own
    entries: those of the file set aside whose names it does not hold are
    added (_merged); the file set aside is then removed, or, where a clash
    left an entry of it out, kept beside the store under a name nothing reads
    (_keep_beside: `<name>.kept-<time>`), and 'charts' (or 'preferences')
    added to the list `kept` where one is given, so that the page says it
    once. A file that is refused -- past its limit, not of this account's,
    not a store or not preferences, a store or preferences that cannot be
    read to add to, a write refused -- stays where it is.

    One press read every file set aside, with no bound on how many or on
    their bytes, and read again, at every press, each it could not bring
    back: files another account put there under the recovery names, or
    hard links to one large file, made one press read gigabytes. One press
    now reads at most _LAUNCH_FILE_LIMIT files and _LAUNCH_BYTE_LIMIT bytes,
    the launch's own bounds, counted afresh at each press; what is past them
    stays set aside, untouched, for a later press. A file is known by its
    device and inode, so one reached by several names is read once in a
    press; and one that could not be brought back is not read again, by
    this press or a later one, while it stays as it was (_RESTORE_FAILED).
    Once a file is brought back, its other names among those set aside --
    each looked at through the folder held and checked to be the same file
    as the one read (_its_other_names_removed) -- are removed in the same
    press, unread: one press clears a file kept under several names, which
    took one press a name."""
    done = True
    folder = SAVED_CHARTS_PATH.parent
    if _folder_not_to_be_used(folder):
        return False
    tally = [0, 0]
    tried = set()
    for path, limit, lock, restore in _set_aside_kinds():
        try:
            names = _list_the_data_folder(folder)
            with lock():
                asides = list(_set_aside_names(path, names))
                gone = set()
                for aside in asides:
                    if aside in gone:
                        continue                # another name of a file brought back: removed
                    try:
                        seen = _lstat(aside)
                    except OSError:
                        done = False
                        continue
                    if (seen.st_dev, seen.st_ino) in tried or _restore_key(seen) in _RESTORE_FAILED:
                        done = False
                        continue
                    budget = _LAUNCH_BYTE_LIMIT - tally[1]
                    if tally[0] >= _LAUNCH_FILE_LIMIT or seen.st_size > budget:
                        done = False
                        continue                # past this press's bounds: left for a later one
                    tried.add((seen.st_dev, seen.st_ino))
                    tally[0] += 1
                    try:
                        data, opened = _read_what_was_set_aside(aside, min(limit, budget), tally)
                        whole = restore(data)
                    except NotAPlainFile as exc:
                        done = False
                        if not (exc.errno == errno.EFBIG and budget < limit):
                            _RESTORE_FAILED.add(_restore_key(seen))
                        continue
                    except (OSError, ValueError, RecursionError):
                        _RESTORE_FAILED.add(_restore_key(seen))
                        done = False
                        continue
                    if not whole:
                        if not _keep_beside(aside, opened):
                            done = False
                            continue
                        if kept is not None:
                            kept.append('charts' if path == SAVED_CHARTS_PATH else 'preferences')
                        gone |= _its_other_names_removed(aside, asides, opened)
                        continue
                    try:
                        if os.path.samestat(_lstat(aside), opened):
                            _unlink(aside)
                    except OSError:
                        done = False
                    gone |= _its_other_names_removed(aside, asides, opened)
        except (OSError, DataLockBusy):
            done = False
    after = set_aside_notices()
    return done and not after["awaiting"]


# What `from user_data import *` gives the engine: every name this module
# binds, the standard modules among them, but the six it rebinds as it runs
# and the accessor (the module docstring says why), and errno, which
# engine.py imports itself, so that no module names it but as errno.NAME
# (the platform check of the errno names the program reads).
__all__ = [
    '_absolute_environment_folder',
    '_ADMINISTRATORS_SID',
    '_ANY_VALUE',
    'APP_DIR_NAME',
    'bring_in_the_old_store',
    '_clock',
    '_set_aside_what_others_could_write',
    '_set_aside_if_others_could_write',
    '_move_aside',
    '_make_it_private',
    '_narrow_a_lock_in_place',
    '_within_the_launch',
    '_copy_within_bounds',
    '_copy_a_file_by_name',
    '_LAUNCH_FILE_LIMIT',
    '_LAUNCH_BYTE_LIMIT',
    '_LAUNCH_TALLY',
    '_Exposed',
    '_wide',
    '_windows_wide',
    '_exposed_at_the_name',
    '_exposed_as_opened',
    '_list_the_data_folder',
    '_former_folder_left_unread',
    '_folder_not_to_be_used',
    '_set_aside_names',
    '_what_stands_exposed',
    '_set_aside_kinds',
    'set_aside_notices',
    '_read_what_was_set_aside',
    '_merged',
    '_restore_a_store',
    '_restore_preferences',
    '_loadable_restored',
    '_its_other_names_removed',
    'restore_set_aside',
    'contextmanager',
    '_copy_is_whole',
    '_COPY_TAKEN',
    '_copy_the_former_folder',
    '_READ_NAME',
    '_LOCK_NAME',
    '_SET_ASIDE',
    '_write_saved_charts',
    '_write_preferences',
    '_MODELESS',
    '_note_whether_it_keeps_modes',
    '_taken_as_it_is',
    '_wide_here',
    '_KEPT',
    '_keep_beside',
    '_RESTORED_NAMES',
    '_its_own_name',
    '_FormerFolder',
    '_held_copy_is_ours',
    '_ours',
    '_OWNER_ENTRY_SIDS',
    '_others_could_change_the_stray',
    '_OwnerDenied',
    '_SYSTEM_SID',
    '_the_former_folder_opened',
    '_the_former_folder_walked',
    '_lock_the_former_folder',
    '_still_the_former_folder',
    '_moved_on',
    '_move_the_former_folder',
    '_open_a_folder',
    '_hold_a_new_folder',
    '_make_and_publish_the_copy',
    '_COPY_NAME',
    '_RECORD_NAME',
    '_record_the_source',
    '_the_recorded_source',
    '_copy_the_former_folder_by_name',
    '_same_open_bytes',
    '_copy_through',
    '_copy_a_file',
    '_open_the_file_within',
    '_give_it_the_same',
    '_copy_is_whole_through',
    '_the_same_within',
    '_remove_through',
    '_empty_through',
    '_a_dead_copy_that_goes',
    '_the_former_folder_judged',
    '_read_the_link',
    'DATA_DIR',
    'DATA_FOLDER_NOT_OURS',
    'data_folder_problem',
    'data_folder_state',
    '_data_lock',
    'dataclass',
    'DataFolderRefused',
    'DataFolderOpenToOthers',
    'DATA_FOLDER_PATH_OPEN',
    'DataFolderNotClosed',
    'DATA_FOLDER_NOT_CLOSED',
    'DataLockBlocked',
    'DataLockBusy',
    'DataLockUnavailable',
    'datetime',
    '_drop_old_versions',
    'fcntl',
    'forget_preference',
    'FORMER_FOLDER_NOT_CARRIED',
    'FORMER_FOLDER_NOT_COPIED',
    'FORMER_FOLDER_BUSY',
    'FORMER_FOLDER_NOT_OURS',
    'FORMER_FOLDER_UNREADABLE',
    '_former_folder_not_this_accounts',
    'FormerFolderNotCarried',
    'FormerFolderNotCopied',
    'FormerFolderBusy',
    'FormerFolderRefused',
    'FormerFolderUnreadable',
    '_FORMER_FOLDER_LOCK_WAIT',
    '_the_former_folder_held',
    '_the_name_and_the_folder_it_leads_to',
    '_give_back_its_mode',
    '_give_file_lock',
    'hashlib',
    '_hold_a_copy',
    '_IMPORTED_BESIDE_THE_PROGRAM',
    'json',
    '_keep_a_version',
    '_keep_stray_aside',
    '_keep_the_data_folder_ours',
    '_judge_the_former_folders_path',
    '_HELD',
    '_REFUSED',
    '_LET_GO',
    '_HeldFolder',
    '_hold_for_the_launch',
    '_held_now',
    '_hold_again',
    '_the_held',
    '_in_the_held_folder',
    '_lstat',
    '_stat',
    '_lexists',
    '_exists',
    '_islink',
    '_isdir',
    '_open',
    '_unlink',
    '_rename',
    '_replace',
    '_link',
    '_chmod',
    '_listdir',
    '_list_through',
    '_access',
    '_statvfs',
    '_LINKS_ON_THE_WAY',
    '_ELOOP',
    '_UNMAPPED',
    '_unmapped_owner',
    '_ours_or_the_systems',
    '_a_group_of_one',
    '_closed_to_others',
    '_carries_an_access_list',
    '_ACCESS_LIST_ATTRIBUTE',
    '_NO_ACCESS_LIST',
    '_EBADF',
    '_held_by_its_whole_path',
    '_WINDOWS_RIGHTS_OVER_A_FOLDER',
    '_TRUSTED_INSTALLER_SID',
    '_WINDOWS_LINK_TAGS',
    '_windows_judge_the_whole_path',
    '_windows_entries_allow_others',
    '_windows_folder_is_open_to_others',
    '_windows_hold_the_folder',
    '_judged_whole',
    '_RESTORE_FAILED',
    '_restore_key',
    '_keep_unreadable_preferences',
    '_LAUNCHED_AT',
    '_LEGACY_APP_DIR_NAME',
    '_LEGACY_SAVED_CHARTS_PATH',
    'load_preferences',
    'load_saved_charts',
    'loaded_saved_charts_digest',
    '_lock_files',
    '_LOCK_NAME_EMPTIED',
    '_lock_name_kind',
    '_LOCK_REFUSALS',
    'LOCK_WAIT_SECONDS',
    '_make_missing_folders',
    '_make_user_data_dir',
    '_mark_the_store_beside_the_program_imported',
    '_move_the_old_store',
    'msvcrt',
    '_narrow_to_its_owner',
    '_new_temp_file',
    '_new_version',
    '_none_else_writes',
    '_not_copied_unless_made_since',
    '_not_this_accounts',
    'NotAPlainFile',
    '_old_stores',
    '_only_a_copy_through',
    '_only_a_copy_within',
    '_an_entry_is_not_this_accounts',
    '_only_files_and_folders',
    '_only_this_accounts_entries',
    '_open_lock_file',
    '_open_regular_file',
    '_opened_for_writing',
    'os',
    '_owner_of',
    '_owner_of_the_open',
    '_whose',
    '_opened_is_ours',
    '_open_this_accounts_file',
    '_NotThisAccounts',
    '_NOTHING',
    '_OURS',
    '_OUR_LINK',
    '_ANOTHERS',
    '_LEADS_TO_ANOTHERS',
    '_owner_of_the_name',
    '_owner_only',
    '_parse_chart_mapping',
    '_parse_preferences',
    'Path',
    '_preferences_as_they_stand',
    'PREFERENCES_BYTE_LIMIT',
    'preferences_enabled',
    'preferences_lock',
    '_PREFERENCES_NOTICE_DEFAULTS',
    '_PREFERENCES_NOTICES',
    'preferences_notices',
    'PREFERENCES_PATH',
    '_PREFERENCES_THREAD_LOCK',
    '_preserve_unreadable_store',
    're',
    '_read_preferences_file',
    '_read_regular_file',
    '_read_the_former_folders_store',
    '_read_the_stray',
    '_reads_as_a_store',
    '_reads_as_preferences',
    '_recovery_stamp',
    'remember_preference',
    '_remove',
    '_remove_dead_copies',
    '_reset_preferences_notices',
    '_running_from_a_bundle',
    '_same_bytes',
    '_same_file',
    '_same_link',
    'saved_charts_as_they_stand',
    'saved_charts_digest',
    'saved_charts_lock',
    'SAVED_CHARTS_PATH',
    '_saved_charts_text',
    'secrets',
    'shutil',
    'stat',
    '_still_named',
    '_still_the_stray',
    'STORE_BYTE_LIMIT',
    '_STORE_LOADED',
    'store_notices',
    'STORE_TEXT_LIMIT',
    '_STORE_THREAD_LOCK',
    'StoreAsItStands',
    '_STRAY_TEMP_WAIT',
    '_sync_folder',
    'sys',
    '_take_file_lock',
    '_text_encodes',
    '_the_first_old_store',
    '_the_former_folders_store',
    '_the_old_store',
    '_the_store_beside_the_program_was_imported',
    'threading',
    '_tidy_stray_temp_files',
    'timezone',
    '_unwritable_folder_reason',
    '_user_data_dir',
    '_user_data_path',
    '_validate_chart_mapping',
    '_VERSION_FORM',
    '_version_key',
    '_version_stamp',
    '_versions',
    'VERSIONS_KEPT',
    '_wait_for_file_lock',
    '_WINDOWS_ACCOUNT',
    '_windows_calls',
    '_WINDOWS_CALLS',
    '_windows_close_the_list',
    '_windows_failed',
    '_windows_file_is_writable_by_others',
    '_windows_keeps_lists',
    '_windows_list_is_wider',
    '_windows_list_names_this_account',
    '_windows_opened',
    '_windows_owner',
    '_windows_owner_of_the_open',
    '_windows_owner_through',
    '_windows_reset_the_list',
    '_WINDOWS_RIGHTS_TO_CHANGE',
    '_windows_sid_text',
    '_windows_this_account',
    '_within_the_store_text_limit',
    '_without_repeated_keys',
    'write_preferences',
    'write_saved_charts',
    '_write_text_atomically',
    '_write_the_store',
]
