# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""Swiss Ephemeris as the engine uses it: the private folder the library
reads from, its checks, the library's one import, the handle every
calculation goes through (`swe`), the Delta T check, the refusals and their
sentences, the Moshier flag every body is read with, and the civil calendar
a date's digits are read in. engine.py takes it by `from ephemeris import *`
before anything else, so that nothing loads the library before the folder is
made.

Two names are this module's alone: _EPHEMERIS_FOLDER and _DELTA_T_REFERENCE
are rebound here as the program runs, so they are read here
(`ephemeris._EPHEMERIS_FOLDER`), never through the engine, which would hold
the value they had when it was imported.

The library's per-angle results are read here: code that judges what Swiss
Ephemeris returns for each house cusp and angle (at a polar latitude, where
it cannot place them all) belongs in this module, beside the handle, not in
engine.py.
"""
# ==========================================
# SWISS EPHEMERIS'S FILES
# ==========================================
# Swiss Ephemeris opens files by name from the folders on its ephemeris
# path: a Delta T table (swe_deltat.txt, then sedeltat.txt), read once per
# thread and kept for the thread's life, behind every value asked at a
# moment of Universal Time -- the bodies, the houses, sidereal time, sunrise
# and sunset, eclipses, the stars; planetary and lunar files (*.se1), which
# its path setter opens even though every body here is read from Moshier;
# the star catalogue (sefstars.txt, then the older fixstars.cat); and leap
# seconds, fictitious bodies' elements and asteroid names (seleapsec.txt,
# seorbel.txt, seasnam.txt), which no call here asks for but which a
# thread's path can still reach (the Earth-orientation files are read only
# after a JPL ephemeris opens, which nothing here asks for). The path is
# kept per thread. A thread's first call starts it at the library's
# compiled default, the working directory first; importing the module sets
# the importing thread's; a path setter takes $SE_EPHE_PATH, when set, over
# the folder its caller names. A Delta T file left in any of those places
# moved every value, and a catalogue there replaced the stars.
#
# So, before the library is loaded, the engine makes a folder of its own
# and sets $SE_EPHE_PATH to it; the folder will hold nothing but a copy of
# the star catalogue the app ships, checked against its recorded SHA-256
# (FIXED_STAR_CATALOGUE_SHA256, in engine.py, where the catalogue is read). Every
# call into the library goes through `swe` (_SwissEphemeris, below), which
# points the calling thread at the folder before the thread's first
# calculation, so no thread's path holds any other folder and no file
# elsewhere is opened. The folder is made by tempfile.mkdtemp: new (the
# call fails rather than reuse a folder that exists), under a name no other
# program can know in advance, and readable and writable by this user
# alone -- its mode is set to 0700 once it is made, and the copy's to 0600
# as it is written, since the process's umask cuts the mode either is asked
# for (under 0o444 the folder came out 0o300, which this user could not
# list). Its name must be one the library takes whole, counted in the bytes
# the library is handed (_ephemeris_folder_is_safe), or the engine refuses.
# Nothing in the app writes there but the catalogue's copy, and it is
# removed at a normal exit (an atexit hook: a killed process leaves it
# behind), known then (on POSIX) by a descriptor held on it since it was
# made, not by its name or its inode number alone; on Windows by its
# (st_dev, st_ino), as _ephemeris_folder_hold says why. Moved aside by
# another program, it is found at exit by that descriptor where it went,
# and emptied and removed there (on Linux and macOS, which give the path of
# a descriptor; elsewhere it is emptied and the empty directory left;
# _ephemeris_folder_remove); on Windows, where no
# descriptor is held, a folder moved aside is left behind. At its own path
# and at the one the system gives, it is known and removed through a
# descriptor on that path's parent, so the one directory a race can put in
# its place is an empty one swapped in at its very name in that parent
# (_ephemeris_folder_rmdir). Where it has gone --
# a temporary-files cleaner, or one that moves it aside -- whatever stands at
# its path is not removed at exit (on POSIX, whatever number its filesystem
# gave it), and is not used: a new folder is made unless what stands at the
# path is the very folder the engine made, known by the same identity, and
# still this user's with mode 0700 (_ephemeris_folder_is_held). A directory made
# or moved into its place is not that
# folder, however like it it looks. At each check -- every call into the
# library through `swe`, a thread's first call, the star reader's search,
# the Delta T reference, the import -- the engine accepts the folder only by
# that identity, and where anything else stands at the path it makes a new
# folder and points the calling thread there; and on POSIX it writes into
# the folder only through the descriptor it holds on it, not through its
# name (on Windows, where none is held, by its name). What no check covers
# is the library's own reading: Swiss Ephemeris opens the files in its
# folder by name, so a directory swapped in between a check and the
# library's next read can be read by that read; the engine sees the swap at
# its next check and moves to a new folder. A thread's Delta T table is
# compared with a reference table read once per process, also by name
# (_delta_t_reference), and taken as the reference only where it is the
# library's own table as this module records it (_DELTA_T_RECORDED, to the
# microsecond): a thread that took a table from a swapped-in directory is
# refused for its life, whether or not the reference's read was raced too. A
# raced reference is refused, not kept: the next check reads it again, so a
# thread after it that read the library's own table is accepted. A program
# running as the same user could likewise write into the folder itself after
# looking for it; each thread's first call checks that the folder holds no
# other file. None of these checks is a lock.
import os
import sys
import atexit
import shutil
import stat
import struct
import tempfile
import threading

_EPHEMERIS_PREFIX = 'zij-ephemeris-'
_EPHEMERIS_CATALOGUE = 'sefstars.txt'


class EphemerisRefused(RuntimeError):
    """The engine refuses to compute in this thread (_ephemeris_thread_ready):
    its folder holds a file the app did not put there, or the thread read a
    Delta T table from a file (before it was pointed at the folder, or from
    a directory swapped in at the folder's path). Its words are for
    whoever reads the state; the page says EPHEMERIS_REFUSAL and stops.
    Raised by `import engine` itself (an import made again, after the
    engine was dropped from sys.modules, in a thread its first calculation
    points at a folder holding such a file), it is caught where app.py
    imports the engine, which says the same sentence."""


class EphemerisFolderRefused(EphemerisRefused):
    """No private folder of the engine's own can be had: none can be made
    (the temporary directory has gone, the disk is full), none can be made
    this user's 0700 one (a filesystem that keeps no modes), its name cannot
    be given to Swiss Ephemeris whole (its bytes, not its
    characters), it cannot be held open to be known again at
    exit (no descriptor left), or the folder went
    before it could be listed. Nothing is computed. The page says
    EPHEMERIS_FOLDER_REFUSAL and stops; raised at
    import, by `import engine` itself, it is caught where app.py imports the
    engine, which says the same sentence."""


class EphemerisFolderNameRefused(EphemerisFolderRefused):
    """The folder's name holds a letter the system's code page cannot write
    (on Windows, where Swiss Ephemeris reads the name in that form:
    _ephemeris_folder_unsafe). Refused as every folder refusal is; the page
    says EPHEMERIS_FOLDER_NAME_REFUSAL, which names the remedy, in place of
    EPHEMERIS_FOLDER_REFUSAL, and app.py holds it too, for the import."""


_EPHEMERIS_FOLDER_BYTES = 200
_CODE_PAGE_CLAUSE = "it holds a letter the system's code page"


def _ephemeris_folder_is_safe(folder):
    """True for a folder Swiss Ephemeris takes whole as its path
    (_ephemeris_folder_unsafe gives no reason against it). Never raises."""
    return _ephemeris_folder_unsafe(folder) is None


def _ephemeris_folder_unsafe(folder):
    """Why Swiss Ephemeris cannot take `folder` whole as its path, in one
    plain clause, or None where it can: absolute, with no ';' (nor, outside
    Windows, ':'), where it splits a path into folders, and not too long.
    The library is handed bytes, not characters: the name's UTF-8 form
    through its path setter, and through $SE_EPHE_PATH, which wins over the
    setter, the form the C library's getenv gives -- the filesystem's form
    on Linux and macOS, the system's ANSI code page's on Windows, where a
    character outside the code page comes out as another (often "?") and the
    path is not the folder. A path of more than 242 bytes (measured on the
    pinned wheel, on both routes, for characters of one to four bytes) is
    dropped for the compiled default, the working directory first, however
    few its characters: 200 bytes leaves room in either form. A name with no
    UTF-8 form (a byte the filesystem's encoding
    could not decode: the path setter cannot take it), whose two forms differ
    on Linux and macOS (the setter would be handed a name that is not the
    folder's), that the code page cannot write on Windows, or holding a NUL
    (neither route carries one) is refused too. Never raises."""
    if not isinstance(folder, str) or not folder or not os.path.isabs(folder):
        return "it is not an absolute path"
    rest = folder[2:] if os.name == 'nt' and folder[1:2] == ':' else folder
    if ';' in folder or ':' in rest:
        return "it holds ';' or ':', where Swiss Ephemeris splits a path in two"
    if '\0' in folder:
        return "it holds a NUL"
    try:
        handed = folder.encode('utf-8')
    except UnicodeError:
        return "it holds a byte the system could not read as a letter"
    if os.name == 'nt':
        import locale
        code_page = locale.getencoding()
        try:
            named = folder.encode(code_page)
            written = named.decode(code_page) == folder
        except (UnicodeError, LookupError):
            written = False
        if not written:
            return f"{_CODE_PAGE_CLAUSE} ({code_page}) cannot write"
    else:
        try:
            named = os.fsencode(folder)
        except (UnicodeError, ValueError):
            return "it holds a byte the system could not read as a letter"
        if handed != named:
            return "the system would hand Swiss Ephemeris another name than the folder's"
    if max(len(handed), len(named)) > _EPHEMERIS_FOLDER_BYTES:
        return f"it is longer than {_EPHEMERIS_FOLDER_BYTES} bytes"
    return None


def _ephemeris_folder_as_made(folder):
    """os.lstat of `folder` where it is a real directory (not a link, and on
    Windows not a junction) and, where the system has owners and modes, this
    user's with mode 0700 -- as tempfile.mkdtemp made it; else None."""
    try:
        st = os.lstat(folder)
    except (OSError, TypeError, ValueError):
        return None
    if not stat.S_ISDIR(st.st_mode):
        return None
    if os.name == 'nt':
        isjunction = getattr(os.path, 'isjunction', None)
        return None if isjunction and isjunction(folder) else st
    return st if st.st_uid == os.getuid() and stat.S_IMODE(st.st_mode) == 0o700 else None


def _ephemeris_folder_is_ours(folder):
    """True where `folder` looks as the engine makes its folder
    (_ephemeris_folder_as_made): the test a folder just made must pass. It
    says nothing of which directory it is; a folder in use is accepted at
    its path only by _ephemeris_folder_is_held."""
    return _ephemeris_folder_as_made(folder) is not None


def _ephemeris_folder_is_held(folder):
    """True only where what stands at `folder`'s path is the very folder the
    engine made there (by the identity taken when it was made),
    still as it was made (_ephemeris_folder_as_made). On POSIX the path's
    (st_dev, st_ino) is that of the descriptor held on the folder since its
    making (_ephemeris_folder_hold), and the held folder has not been
    removed (its link count is above 0): a directory made at the path, or
    moved into it, is another inode while the held one lives, and a removed
    folder is not taken back whatever number stands at its path. On Windows
    the path's (st_dev, st_ino) is the one recorded at the making. False for
    anything else, for nothing at the path, and for a folder this process
    holds no identity for. Never raises."""
    held = _EPHEMERIS_HELD.get(folder) if isinstance(folder, str) else None
    if held is None:
        return False
    st = _ephemeris_folder_as_made(folder)
    if st is None:
        return False
    if not isinstance(held, int):                     # Windows: the identity recorded at the making
        return (st.st_dev, st.st_ino) == held
    try:
        mine = os.fstat(held)
    except OSError:
        return False
    return mine.st_nlink > 0 and (st.st_dev, st.st_ino) == (mine.st_dev, mine.st_ino)


def _ephemeris_folder_hold(folder):
    """What identifies the folder at exit, taken as it is made, and kept for
    the process's life. On POSIX, a descriptor
    opened on the folder itself (no link followed) and never closed before
    exit: while it is open the folder's inode cannot be freed, so no other
    directory can be given its number, and its link count shows the
    folder's removal however the filesystem numbers what comes after. It is
    a descriptor, not a file: nothing is put in the folder. On Windows,
    os.open cannot open a directory (a handle on one needs CreateFile with
    FILE_FLAG_BACKUP_SEMANTICS, which the standard library does not
    offer), so there the identity is the folder's (st_dev, st_ino) as
    before: NTFS's file ID carries a sequence number that changes when its
    record is reused (documented, not run here). None where no descriptor
    can be had (no descriptors left): the engine then refuses."""
    try:
        st = os.lstat(folder)
    except OSError:
        return None
    if os.name == 'nt':
        return (st.st_dev, st.st_ino)
    flags = (os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
             | getattr(os, 'O_CLOEXEC', 0))
    try:
        held = os.open(folder, flags)
    except OSError:
        return None
    mine = os.fstat(held)
    if (mine.st_dev, mine.st_ino) != (st.st_dev, st.st_ino) or not stat.S_ISDIR(mine.st_mode):
        os.close(held)
        return None
    return held


def _ephemeris_folder_where(held):
    """The path the system gives for the folder the descriptor `held` is
    open on, wherever that folder now stands (renamed aside by another
    program, it is not at the path it was made at): on Linux the link
    /proc/self/fd/<n> names it, on macOS fcntl(F_GETPATH) does. None on any
    other system, on a Linux with no /proc mounted, and wherever no absolute
    path is given. It is only where the folder stood when it was asked: the
    caller judges what stands there by its identity. Never raises."""
    try:
        if sys.platform.startswith('linux'):
            where = os.readlink(f'/proc/self/fd/{held}')
        elif sys.platform == 'darwin':
            import fcntl
            where = os.fsdecode(fcntl.fcntl(held, fcntl.F_GETPATH, bytes(1024)).split(b'\0', 1)[0])
        else:
            return None
    except (OSError, ValueError, TypeError, AttributeError, ImportError):
        return None
    return where if isinstance(where, str) and os.path.isabs(where) else None


def _ephemeris_folder_rmdir(where, mine):
    """Removes the directory at the path `where` only where it is the very
    folder `mine` describes (os.fstat of the descriptor held on it: a real
    directory with its (st_dev, st_ino) and a link count above 0), and says
    whether it did. The path's parent is opened as a directory with no link
    followed at its own name (O_DIRECTORY, O_NOFOLLOW; O_PATH where the
    system has it, which asks only to pass through the parent, as rmdir by
    a path does, not to read it), and the identity (os.stat at the name, no
    link followed) and the removal (os.rmdir at the name) are both made
    through that one descriptor, closed in every case: a parent swapped for
    a link between the two cannot carry the removal anywhere else. Links
    earlier in the parent's path are followed as
    by any path (macOS's /var, before /var/folders/.../T); a parent whose
    own name is a link (macOS's /tmp) is not opened, and the folder is
    found by the resolved path the system gives for its descriptor. The
    race left is the final name's alone: an empty directory swapped in at
    that name in that very parent, between the identity and the removal, is
    removed in the folder's place (rmdir keeps any directory with something
    in it; POSIX has no removal of a directory by a descriptor on it). A
    system with no dir_fd for these calls (not in os.supports_dir_fd:
    Python raises NotImplementedError) removes nothing here: a removal by
    the whole path is what reached through a swapped parent, and an empty
    folder left behind is the safer loss. False, too, for no path, a path
    with no last name, and a parent that cannot be opened (without O_PATH,
    one this user cannot read). An OSError of the removal itself is raised
    to the caller."""
    if not isinstance(where, str) or not os.path.isabs(where):
        return False
    parent, name = os.path.split(where)
    if name in ('', '.', '..'):
        return False
    flags = (getattr(os, 'O_PATH', os.O_RDONLY) | getattr(os, 'O_DIRECTORY', 0) | getattr(os, 'O_NOFOLLOW', 0)
             | getattr(os, 'O_CLOEXEC', 0))
    try:
        at = os.open(parent, flags)
    except (OSError, ValueError):
        return False
    try:
        try:
            st = os.stat(name, dir_fd=at, follow_symlinks=False)
        except (OSError, NotImplementedError):
            return False
        if (not stat.S_ISDIR(st.st_mode) or (st.st_dev, st.st_ino) != (mine.st_dev, mine.st_ino)
                or st.st_nlink == 0):
            return False
        try:
            os.rmdir(name, dir_fd=at)
        except NotImplementedError:
            return False
        return True
    finally:
        os.close(at)


def _ephemeris_folder_remove(folder, owner, held):
    """At a normal exit, in the process that made the folder (a forked child
    that shares it leaves it alone), and only the very directory it made:
    whatever stands at the path after a cleaner is not this process's,
    whatever number its filesystem gave it. On
    POSIX `held` is the descriptor held on the folder since it was made
    (_ephemeris_folder_hold): a folder whose link count has fallen to 0 was
    removed, and nothing is touched; one still linked is emptied through
    the descriptor -- its own entries -- wherever it now stands, and only
    then removed by a path: its own, where it still stands there, or else
    the path the system gives for the descriptor (_ephemeris_folder_where:
    the folder moved aside by another program is found where it went), each
    used only where what stands there is a real
    directory with the held (st_dev, st_ino) and a link count above 0, both
    judged and removed through a descriptor on that path's parent
    (_ephemeris_folder_rmdir). So the one race left
    is an empty directory swapped in at the folder's own name in that
    parent, between the identity and the rmdir: it would be removed in the
    folder's place, and the engine's own, then elsewhere, left. Where the
    system gives no path (a POSIX system other than Linux and macOS, a Linux
    with no /proc), the folder moved aside is emptied and the empty
    directory left; on a system with no dir_fd, which cannot empty it
    through its descriptor either, nothing is removed. On Windows `held` is
    the folder's (st_dev, st_ino), compared as before, and the folder is
    then removed with its contents by name, only at its own path (no
    descriptor is held there), so a directory swapped in between that
    comparison and the removal would be removed instead."""
    if os.getpid() != owner:
        return
    if not isinstance(held, int):
        try:
            st = os.lstat(folder)
        except OSError:
            return
        if stat.S_ISDIR(st.st_mode) and (st.st_dev, st.st_ino) == held:
            shutil.rmtree(folder, ignore_errors=True)
        return
    try:
        mine = os.fstat(held)
        if mine.st_nlink == 0:
            return
        for name in os.listdir(held):
            try:
                if stat.S_ISDIR(os.stat(name, dir_fd=held, follow_symlinks=False).st_mode):
                    shutil.rmtree(name, dir_fd=held, ignore_errors=True)
                else:
                    os.unlink(name, dir_fd=held)
            except OSError:
                pass
        if not _ephemeris_folder_rmdir(folder, mine):
            _ephemeris_folder_rmdir(_ephemeris_folder_where(held), mine)
    except (OSError, NotImplementedError):            # NotImplementedError: a system with no dir_fd
        pass
    finally:
        try:
            os.close(held)
        except OSError:
            pass


def _ephemeris_folder_make():
    """A new folder, this user's, mode 0700. tempfile.mkdtemp asks for 0700,
    but the process's umask cuts what it asks (0o300 under 0o444, 0o000
    under 0o777), so the mode is set after it is made: os.chmod is not cut
    by the umask. Where the folder still is not this user's 0700 directory
    -- a filesystem that keeps no modes -- it is removed and the engine
    refuses (EphemerisFolderRefused), rather than use or keep one folder
    after another (each later call makes one more and removes it at once).
    Where no folder can be made at all -- the temporary directory has gone
    with it, or the disk is full -- the engine refuses the same way. So it
    does, removing the folder, where the folder's name is not one Swiss
    Ephemeris takes whole (_ephemeris_folder_is_safe), and where it cannot be
    held open to be known again at exit
    (_ephemeris_folder_hold). The exit hook is
    registered here, once per folder made."""
    try:
        folder = os.path.abspath(tempfile.mkdtemp(prefix=_EPHEMERIS_PREFIX))
    except OSError:
        raise EphemerisFolderRefused("no temporary folder could be made for Swiss Ephemeris; nothing is computed") from None
    if not _ephemeris_folder_is_safe(folder):
        os.rmdir(folder)
        why = _ephemeris_folder_unsafe(folder)
        refusal = EphemerisFolderNameRefused if why.startswith(_CODE_PAGE_CLAUSE) else EphemerisFolderRefused
        raise refusal(f"the temporary folder's name cannot be given to Swiss Ephemeris whole ({why}); point "
                      "TMPDIR, TEMP or TMP at a plain folder")
    if os.name != 'nt':
        # By name, before the folder is held: a descriptor cannot be opened on
        # a folder the umask left unreadable (0o300 under 0o444), so the mode
        # is set first. The name is new and unforeseeable, and what stands
        # there is judged after (_ephemeris_folder_is_ours, then the hold).
        try:
            os.chmod(folder, 0o700)
        except OSError:
            pass                                      # judged below, as a filesystem that keeps no modes
    if not _ephemeris_folder_is_ours(folder):
        try:
            os.rmdir(folder)
        except OSError:
            pass
        raise EphemerisFolderRefused("the temporary folder made for Swiss Ephemeris could not be made this user's "
                                     "alone (mode 0700); nothing is computed")
    held = _ephemeris_folder_hold(folder)
    if held is None:
        try:
            os.rmdir(folder)
        except OSError:
            pass
        raise EphemerisFolderRefused("the temporary folder made for Swiss Ephemeris could not be held open to "
                                     "know it again at exit; nothing is computed")
    _EPHEMERIS_HELD[folder] = held
    atexit.register(_ephemeris_folder_remove, folder, os.getpid(), held)
    return folder


# One folder per process. A reload of this module keeps it (the module's
# globals survive importlib.reload), and a reload of the engine alone does
# not run this code (the next call into the library checks the folder); a
# fresh import after the module was dropped from sys.modules (Streamlit's
# watcher does that) finds it on the library module, which stays loaded.
# What each folder made was held by
# (_EPHEMERIS_HELD, folder -> _ephemeris_folder_hold's identity) is found
# again the same way: a folder is used again only where what stands at its
# path is the folder that identity holds (_ephemeris_folder_is_held: not a
# directory made or moved into its place since), and
# only where its name is still one the library takes whole
# (_ephemeris_folder_is_safe:
# every name handed to Swiss Ephemeris, at import and when made again, has
# passed it). The exit hook was registered once, when the folder was made,
# and is not registered again. Swiss Ephemeris loaded by anything
# before the first of these imports may have read a file already: a thread
# that read a Delta T table then is refused (_ephemeris_thread_ready), and
# the Streamlit caches are emptied below, once this module has imported
# Streamlit.
_swisseph_loaded = sys.modules.get('swisseph')
_EPHEMERIS_HELD = globals().get('_EPHEMERIS_HELD')
if _EPHEMERIS_HELD is None:
    _EPHEMERIS_HELD = getattr(_swisseph_loaded, '_zij_ephemeris_held', None)
if _EPHEMERIS_HELD is None:
    _EPHEMERIS_HELD = {}
_EPHEMERIS_FOLDER = globals().get('_EPHEMERIS_FOLDER') or getattr(_swisseph_loaded, '_zij_ephemeris_folder', None)
_EPHEMERIS_LOADED_FIRST = _swisseph_loaded is not None and _EPHEMERIS_FOLDER is None
if not _ephemeris_folder_is_safe(_EPHEMERIS_FOLDER) or not _ephemeris_folder_is_held(_EPHEMERIS_FOLDER):
    _EPHEMERIS_FOLDER = _ephemeris_folder_make()
os.environ['SE_EPHE_PATH'] = _EPHEMERIS_FOLDER
del _swisseph_loaded

import swisseph as _swisseph
_swisseph._zij_ephemeris_folder = _EPHEMERIS_FOLDER
_swisseph._zij_ephemeris_held = _EPHEMERIS_HELD

# Threads pointed at the folder, and the Delta T table a thread pointed at
# it first holds (carried over a reload, like the folder).
_EPHEMERIS_THREADS = globals().get('_EPHEMERIS_THREADS') or threading.local()
_EPHEMERIS_LOCK = globals().get('_EPHEMERIS_LOCK') or threading.Lock()
_EPHEMERIS_FOLDER_LOCK = globals().get('_EPHEMERIS_FOLDER_LOCK') or threading.Lock()
_DELTA_T_REFERENCE = globals().get('_DELTA_T_REFERENCE')


def _ephemeris_folder_here():
    """The folder, made again if it has gone -- a temporary-files cleaner can
    remove it under an app left running for days, or move it aside -- or if
    what stands at its path is not the folder the engine made there, as it
    made it (_ephemeris_folder_is_held: a link, a directory others may write
    into, another user's, or one of this user's own 0700 directories made or
    moved into its place): its name was
    visible, and anyone may put a link or a directory there. Every thread is
    pointed at the new one at its next call (its recorded folder no longer
    matches), and the catalogue is copied there at the next star read. Where
    no new folder can be made, or none this user's 0700 one, EphemerisRefused
    (_ephemeris_folder_make); the next call tries again."""
    global _EPHEMERIS_FOLDER
    with _EPHEMERIS_FOLDER_LOCK:
        if not _ephemeris_folder_is_safe(_EPHEMERIS_FOLDER) or not _ephemeris_folder_is_held(_EPHEMERIS_FOLDER):
            _EPHEMERIS_FOLDER = _ephemeris_folder_make()
            _swisseph._zij_ephemeris_folder = _EPHEMERIS_FOLDER
            os.environ['SE_EPHE_PATH'] = _EPHEMERIS_FOLDER
        return _EPHEMERIS_FOLDER


def _delta_t_table():
    """Delta T on the first of January of every year its table can hold
    (from 1620; a file may extend it), at the library's default tidal term,
    as packed bits."""
    values = [_swisseph.deltat_ex(_swisseph.julday(year, 1, 1, 0.0), -1) for year in range(1620, 2131)]
    return struct.pack(f'!{len(values)}d', *values)


# The table _delta_t_table reads where no Delta T file is on the thread's
# path: the library's own, built into the pinned pyswisseph (Swiss Ephemeris
# 2.10.03), in seconds, for each year from 1620 to 2130, rounded to the
# microsecond. The reference is kept only where it is this table
# (_delta_t_reference), so its proof is in the code, not in any folder. A
# pyswisseph whose own table moves fails the test that reads it
# (test_the_recorded_table_is_the_library_s_own), and this moves with it.
_DELTA_T_RECORDED = (
    66.553595, 65.632164, 64.727945, 63.837897, 62.961517, 62.095956, 61.245439, 60.407080, 59.580377,
    58.762607, 57.957736, 57.163011, 56.377929, 55.599874, 54.832594, 54.073447, 53.321931, 52.575512,
    51.837767, 51.106143, 50.380137, 49.657278, 48.941012, 48.228854, 47.520303, 46.812926, 46.110084,
    45.409338, 44.710186, 44.010212, 43.312739, 42.615425, 41.918470, 41.220244, 40.524839, 39.830622,
    39.137871, 38.444969, 37.755980, 37.069284, 36.385158, 35.702016, 35.023866, 34.349114, 33.678037,
    33.009089, 32.346201, 31.687817, 31.034212, 30.383892, 29.740690, 29.103095, 28.471385, 27.844130,
    27.225035, 26.612654, 26.007262, 25.407507, 24.816942, 24.234197, 23.659546, 23.091725, 22.534115,
    21.985428, 21.445941, 20.914490, 20.394257, 19.884052, 19.384152, 18.893506, 18.415073, 17.947773,
    17.491882, 17.046477, 16.614266, 16.194294, 15.786836, 15.391106, 15.009541, 14.641320, 14.286718,
    13.946012, 13.619477, 13.307389, 13.010026, 12.726909, 12.459863, 12.208369, 11.972704, 11.752565,
    11.549431, 11.362954, 11.193411, 11.040684, 10.905884, 10.788847, 10.689849, 10.608969, 10.546928,
    10.503753, 10.478723, 10.473977, 10.488067, 10.520335, 10.570161, 10.637131, 10.720260, 10.819087,
    10.932994, 11.061733, 11.203978, 11.359445, 11.527512, 11.708071, 11.899514, 12.101699, 12.314007,
    12.536438, 12.767158, 13.006140, 13.252768, 13.507124, 13.767199, 14.033059, 14.304085, 14.580419,
    14.859929, 15.142746, 15.428250, 15.716613, 16.005638, 16.295491, 16.585553, 16.875998, 17.164617,
    17.451585, 17.736285, 18.018863, 18.297155, 18.571319, 18.840735, 19.105499, 19.363544, 19.614983,
    19.859194, 20.096197, 20.324075, 20.542867, 20.751954, 20.951247, 21.139036, 21.315262, 21.479304,
    21.630940, 21.768720, 21.892458, 22.001535, 22.095566, 22.173417, 22.234747, 22.278937, 22.305415,
    22.313416, 22.302418, 22.271801, 22.220779, 22.149009, 22.055762, 21.940417, 21.801947, 21.640486,
    21.455069, 21.245077, 21.009210, 20.748138, 20.460631, 20.146070, 19.802859, 19.432254, 19.032737,
    18.604686, 18.148065, 17.676305, 17.204423, 16.747437, 16.319249, 15.937251, 15.615241, 15.368238,
    15.210965, 15.159335, 15.220674, 15.374354, 15.593278, 15.848428, 16.112568, 16.357939, 16.557238,
    16.681556, 16.703754, 16.596073, 16.338477, 15.946650, 15.442830, 14.849757, 14.188289, 13.484833,
    12.760398, 12.037723, 11.337687, 10.686905, 10.101942, 9.584748, 9.131851, 8.743394, 8.415729,
    8.146530, 7.932965, 7.773872, 7.666266, 7.607824, 7.596300, 7.629656, 7.705774, 7.822631,
    7.978683, 8.171048, 8.398077, 8.657749, 8.948874, 9.266836, 9.605226, 9.925476, 10.183500,
    10.333125, 10.330499, 10.151391, 9.851015, 9.507672, 9.197151, 8.996935, 8.948827, 8.966845,
    8.931193, 8.722409, 8.219146, 7.345720, 6.190234, 4.883466, 3.552647, 2.336126, 1.331635,
    0.524431, -0.131147, -0.675657, -1.155120, -1.606291, -2.039306, -2.453575, -2.852080, -3.236594,
    -3.604639, -3.932403, -4.194035, -4.362646, -4.410294, -4.327399, -4.166305, -3.995922, -3.885004,
    -3.903223, -4.092655, -4.390106, -4.706773, -4.951109, -5.033380, -4.882524, -4.490641, -3.871015,
    -3.034017, -1.990764, -0.760321, 0.605102, 2.045268, 3.499941, 4.911624, 6.229575, 7.475817,
    8.684853, 9.894518, 11.132785, 12.425111, 13.744300, 15.054343, 16.308456, 17.471719, 18.511518,
    19.434940, 20.249521, 20.970498, 21.611425, 22.182443, 22.683853, 23.117689, 23.484335, 23.784905,
    24.019438, 24.193640, 24.313599, 24.385535, 24.415156, 24.408967, 24.373693, 24.315957, 24.242894,
    24.162180, 24.083331, 24.036301, 24.055065, 24.173077, 24.424976, 24.829471, 25.346512, 25.924085,
    26.509278, 27.049545, 27.504836, 27.891089, 28.237728, 28.575111, 28.931886, 29.321420, 29.698357,
    30.180458, 30.623004, 31.070207, 31.350000, 31.680898, 32.180701, 32.680333, 33.150000, 33.590844,
    34.000593, 34.470345, 35.030000, 35.731554, 36.541195, 37.430593, 38.290000, 39.201965, 40.181339,
    41.170696, 42.230000, 43.372366, 44.485527, 45.476757, 46.456700, 47.523502, 48.535839, 49.586893,
    50.538700, 51.382450, 52.167848, 52.957097, 53.788200, 54.343819, 54.871941, 55.322531, 55.819700,
    56.301018, 56.856191, 57.565797, 58.309200, 59.123569, 59.985609, 60.785990, 61.628700, 62.296519,
    62.966708, 63.467591, 63.828500, 64.091270, 64.300074, 64.473486, 64.573600, 64.687831, 64.845539,
    65.146613, 65.457400, 65.777441, 66.070262, 66.324782, 66.603000, 66.907629, 67.281481, 67.644181,
    68.102400, 68.593604, 68.968026, 69.220340, 69.361200, 69.359225, 69.294359, 69.183237, 69.100000,
    68.999802, 68.899835, 68.800000, 68.800000, 69.037369, 69.276391, 69.517736, 69.761427, 70.008168,
    70.256633, 70.507517, 70.760845, 71.017345, 71.275640, 71.536451, 71.799802, 72.066450, 72.334962,
    72.606086, 72.879847, 73.157031, 73.436146, 73.717971, 74.002529, 74.290636, 74.580742, 74.873654,
    75.169397, 75.468816, 75.770299, 76.074685, 76.381999, 76.693117, 77.006365, 77.322613, 77.641884,
    77.965090, 78.290489, 78.618985, 78.950601, 79.286283, 79.624220, 79.965351, 80.309699, 80.658244,
    81.009107, 81.363260, 81.720726, 82.082523, 82.446699, 82.814260, 83.185232, 83.560669, 83.938543,
    84.319901, 84.704765, 85.094229, 85.486190, 85.881730, 86.280874, 86.684754, 87.091188, 87.501298,
    87.915108, 88.333792, 88.755085, 89.180152, 89.609015, 90.042891, 90.479431, 90.919841, 91.364145,
    91.813600, 92.265775, 92.721915, 93.182046, 93.646192, 94.114376, 94.586623, 95.062957, 95.544724,
    96.029315, 96.518066, 97.011001, 97.509511, 98.010897, 98.516539, 99.026462, 99.542103, 100.060671,
    100.583591, 101.110888, 101.644049, 102.180184, 102.720769, 103.265828, 103.816896, 104.370987, 104.929624,
    105.492831, 106.062195, 106.634628, 107.211703, 107.793446, 108.373714, 108.957098,
)


def _delta_t_as_recorded(table):
    """True where `table` (_delta_t_table's) is _DELTA_T_RECORDED's, each
    year's value within two microseconds (the recorded value's rounding, and
    room for the last bits a platform's build may compute otherwise)."""
    values = struct.unpack(f'!{len(table) // 8}d', table)
    return len(values) == len(_DELTA_T_RECORDED) and all(
        abs(value * 86400.0 - recorded) <= 2e-6 for value, recorded in zip(values, _DELTA_T_RECORDED))


def _delta_t_reference():
    """The table as a thread holds it when its first call points it at the
    folder: read once per process, in a thread of its own, pointed at the
    folder as _ephemeris_folder_here has just accepted it, by its held
    identity, or made it. The library then reads the folder by its name: a
    directory swapped in at the path between that check and the read would
    be read (the check is not a lock). So the table read is kept only where
    it is the library's own, as recorded here (_delta_t_as_recorded); a table
    read from such a directory is refused (EphemerisRefused) and not kept,
    and the next call reads again."""
    global _DELTA_T_REFERENCE
    with _EPHEMERIS_LOCK:
        if _DELTA_T_REFERENCE is None:
            box = []
            folder = _ephemeris_folder_here()

            def first_call():
                _swisseph.set_ephe_path(folder)
                box.append(_delta_t_table())
            reader = threading.Thread(target=first_call, name='ephemeris-reference', daemon=True)
            reader.start()
            reader.join(60)
            if not box:
                raise RuntimeError("Swiss Ephemeris did not answer in a thread of its own within 60 s")
            if not _delta_t_as_recorded(box[0]):
                raise EphemerisRefused("Swiss Ephemeris read a Delta T table that is not its own (it is not the "
                                       "one recorded); nothing is computed in this thread")
            _DELTA_T_REFERENCE = box[0]
        return _DELTA_T_REFERENCE


# The page's sentences: no folder, no file's name, no exception text (as
# the stars' refusal has none); its own words for each refusal.
# EPHEMERIS_REFUSAL is for the two EphemerisRefused describes;
# closing and opening the app clears both (a new process makes a new
# folder, and its threads are new). EPHEMERIS_FOLDER_REFUSAL is for every
# case where no private folder can be had (EphemerisFolderRefused) but one:
# EPHEMERIS_FOLDER_NAME_REFUSAL is for
# a temporary folder whose name the system's code page cannot write
# (EphemerisFolderNameRefused, Windows), and says what the reader can change.
# app.py holds all three in the same words, for a refusal at the engine's
# import, when the engine never loaded.
EPHEMERIS_REFUSAL = ("Nothing is calculated: Swiss Ephemeris found a file this app does not supply. "
                     "Close the app and open it again.")
EPHEMERIS_FOLDER_REFUSAL = ("Nothing is calculated: this app could not make a private folder for its ephemeris "
                            "in the computer's temporary folder.")
EPHEMERIS_FOLDER_NAME_REFUSAL = ("Nothing is calculated: the computer's temporary folder has a name this app's "
                                 "ephemeris cannot read; set TEMP to a folder such as C:\\Temp, whose whole path "
                                 "has only English letters and digits, and open the app again.")


def _ephemeris_thread_ready():
    """Point this thread's Swiss Ephemeris at the folder (once per thread,
    before its first calculation, and again where the folder was made again
    or another directory stands at its path: _ephemeris_thread_pointed). Refuses -- raises EphemerisRefused --
    where no folder of the engine's own can be had or listed (a cleaner
    removed it after the check; a filesystem that keeps no modes), where
    the folder holds a file the app did not put there (each call in
    this thread is refused while it is there; threads already pointed at
    the folder go on), or where this thread already holds a Delta T table
    read from a file: neither the path setter nor swe.close gives a thread
    its own table back, so a thread that read one before it was pointed here
    keeps it for its life; or where the reference table cannot be had
    (_delta_t_reference: a table read is not the library's own). (Swiss
    Ephemeris built without per-thread state, as some platforms build it,
    shares one table among all threads; there the reference table is that
    one, and a file read before the folder was set is seen as the reference
    is checked against the recorded table.)"""
    folder = _ephemeris_folder_here()
    try:
        strays = sorted(set(os.listdir(folder)) - {_EPHEMERIS_CATALOGUE})
    except OSError:
        raise EphemerisFolderRefused("Swiss Ephemeris's folder cannot be read; nothing is computed in this thread "
                                     "while it cannot") from None
    if strays:
        raise EphemerisRefused("Swiss Ephemeris's folder holds a file this app did not put there; "
                               "nothing is computed in this thread while it is there")
    if os.environ.get('SE_EPHE_PATH') != folder:          # changed since the import: set it back
        os.environ['SE_EPHE_PATH'] = folder
    _swisseph.set_ephe_path(folder)
    if _delta_t_table() != _delta_t_reference():
        raise EphemerisRefused("Swiss Ephemeris in this thread holds a Delta T table read from a file before "
                               "the app pointed it at its own folder; nothing is computed in this thread")
    _EPHEMERIS_THREADS.folder = folder


def _ephemeris_thread_pointed():
    """True where this thread may call the library as it is: its first call
    pointed it at the folder now in use (_ephemeris_thread_ready), and what
    stands at the folder's path is still that folder
    (_ephemeris_folder_is_held), or nothing at all -- a folder that has gone
    leaves nothing there to be read, and a thread already pointed goes on
    until a folder is made again, as before. Where anything else stands at
    the path -- a directory made or moved into its place -- the thread is not
    pointed: its next call makes a new folder and points it there, so from its
    next call a thread already pointed at
    the path reads nothing from what stands there now (the library reads by
    name between checks: the module's opening comment). Checked before every
    call (the wrapper below): one lstat and one fstat."""
    folder = _EPHEMERIS_FOLDER
    if getattr(_EPHEMERIS_THREADS, 'folder', None) != folder:
        return False
    return _ephemeris_folder_is_held(folder) or not os.path.lexists(folder)


def ephemeris_thread_check():
    """Point the calling thread at the folder now, if its first call has not,
    or if what stands at the folder's path is no longer the folder it was
    pointed at (_ephemeris_thread_pointed); the page does this first, so that
    a refusal is said in one sentence before anything is drawn. Raises
    EphemerisRefused as the guard does."""
    if not _ephemeris_thread_pointed():
        _ephemeris_thread_ready()


class _SwissEphemeris:
    """The swisseph module, with each thread pointed at the engine's folder
    before its first call (_ephemeris_thread_ready), and again before any
    call made while another directory stands at the folder's path
    (_ephemeris_thread_pointed). Its functions are
    looked up on the module at each call, so whatever the module holds at
    that moment is what runs; its constants and its Error class are the
    module's own."""

    def __init__(self, module):
        self.__dict__['_module'] = module

    def __getattr__(self, name):
        value = getattr(self._module, name)
        if not callable(value) or isinstance(value, type):
            self.__dict__[name] = value
            return value
        module = self._module

        def call(*args, **kwargs):
            if not _ephemeris_thread_pointed():
                _ephemeris_thread_ready()
            return getattr(module, name)(*args, **kwargs)
        call.__name__ = call.__qualname__ = name
        call.__doc__ = value.__doc__
        self.__dict__[name] = call
        return call


swe = _SwissEphemeris(_swisseph)
import streamlit as st
if _EPHEMERIS_LOADED_FIRST:
    st.cache_data.clear()
import math


# Which ephemeris the bodies are read from: Swiss Ephemeris's built-in
# Moshier ephemeris, the one the exports name. At the library's default
# (FLG_SWIEPH) Swiss Ephemeris first looks for planetary files of its own on
# the thread's ephemeris path, reads any it finds, and falls back to Moshier
# only where it finds none: a file there would move the planets, or,
# damaged, stop the chart. (The path is the engine's own folder, above, which
# holds no such file; these flags do not rest on that.) Asked for Moshier, it
# takes nothing that reaches a value from such a file. Every swe.calc_ut that
# reads a body passes these flags, and so does swe.nod_aps_ut (FLG_SPEED is their
# default's other half: the speeds are read); swe.rise_trans,
# swe.lun_eclipse_when and swe.fixstar2_ut pass FLG_MOSEPH alone, as their
# default has no speed. The fixed stars keep their catalogue; the Earth they
# are seen from is Moshier's. Delta T then follows the Moshier ephemeris in
# every one of those calls, as the bodies' already did. The sidereal time
# and the obliquity of the moment (_sidereal_frame, below) keep the
# library's default delta T, asked so that no ephemeris file can reach them:
# swe.calc(jd + swe.deltat_ex(jd, -1), swe.ECL_NUT, swe.FLG_MOSEPH) -- delta
# T at -1 is the library's default tidal term, whatever file a thread has
# open, and ECL_NUT is obliquity and nutation from formulae at that
# instant. (swe.calc_ut(jd, swe.ECL_NUT) gave the same value only while no
# Moon file was readable, or after a Moshier read earlier in the thread.) A
# delta T file (sedeltat.txt) would still reach them, and every other
# value with them; it is not an ephemeris file, and is kept out by the
# engine's folder (SWISS EPHEMERIS'S FILES, above), not by these flags.
MOSHIER_FLAGS = swe.FLG_MOSEPH | swe.FLG_SPEED


# --- The sidereal time and the obliquity of the moment --------------------
# Swiss Ephemeris turns the sky by the IAU 2006 sidereal time only from 1850
# to 2050, and by a long-term construction of its own outside those years,
# with no argument or setting that reaches the choice. The houses depend on
# the instant only through the right ascension of the meridian (ARMC) and the
# true obliquity, so this file computes both itself, by one route for every
# date, and hands them to swe.houses_armc.
#
# The route is the equinox-based one of the IERS Conventions (2010), ch. 5:
# the Earth rotation angle from universal time (eq. 5.15); the IAU 2006
# Greenwich mean sidereal time, the angle plus a polynomial in Julian
# centuries of TT from J2000 (eq. 5.32); and the equation of the equinoxes,
# the nutation in longitude times the cosine of the IAU 2006 mean obliquity
# (eq. 5.40) plus the complementary terms (Table 5.2e, with the fundamental
# arguments of eqs. 5.43 and 5.44). The nutation in longitude and in
# obliquity are Swiss Ephemeris's own (ECL_NUT), and TT is UT plus the
# library's default delta T at -1, as the comment above sets out. A JD in UT
# is taken as the Earth's own rotation time, as Swiss Ephemeris takes it.
# The true obliquity is the IAU 2006 mean obliquity plus that nutation in
# obliquity, so the ARMC and the obliquity handed on belong to one frame.
_ARCSEC = math.pi / 648000.0
_TURN_ARCSEC = 1296000.0

# Table 5.2e: the complementary terms, by multiples of the arguments l, l',
# F, D, Omega, L_Venus, L_Earth, p_A, with the sine and cosine coefficients
# in microarcseconds; the last is the one term of order t.
_EE_COMPLEMENTARY = (
    ((0, 0, 0, 0, 1, 0, 0, 0), 2640.96, -0.39),
    ((0, 0, 0, 0, 2, 0, 0, 0), 63.52, -0.02),
    ((0, 0, 2, -2, 3, 0, 0, 0), 11.75, 0.01),
    ((0, 0, 2, -2, 1, 0, 0, 0), 11.21, 0.01),
    ((0, 0, 2, -2, 2, 0, 0, 0), -4.55, 0.00),
    ((0, 0, 2, 0, 3, 0, 0, 0), 2.02, 0.00),
    ((0, 0, 2, 0, 1, 0, 0, 0), 1.98, 0.00),
    ((0, 0, 0, 0, 3, 0, 0, 0), -1.72, 0.00),
    ((0, 1, 0, 0, 1, 0, 0, 0), -1.41, -0.01),
    ((0, 1, 0, 0, -1, 0, 0, 0), -1.26, -0.01),
    ((1, 0, 0, 0, -1, 0, 0, 0), -0.63, 0.00),
    ((1, 0, 0, 0, 1, 0, 0, 0), -0.63, 0.00),
    ((0, 1, 2, -2, 3, 0, 0, 0), 0.46, 0.00),
    ((0, 1, 2, -2, 1, 0, 0, 0), 0.45, 0.00),
    ((0, 0, 4, -4, 4, 0, 0, 0), 0.36, 0.00),
    ((0, 0, 1, -1, 1, -8, 12, 0), -0.24, -0.12),
    ((0, 0, 2, 0, 0, 0, 0, 0), 0.32, 0.00),
    ((0, 0, 2, 0, 2, 0, 0, 0), 0.28, 0.00),
    ((1, 0, 2, 0, 3, 0, 0, 0), 0.27, 0.00),
    ((1, 0, 2, 0, 1, 0, 0, 0), 0.26, 0.00),
    ((0, 0, 2, -2, 0, 0, 0, 0), -0.21, 0.00),
    ((0, 1, -2, 2, -3, 0, 0, 0), 0.19, 0.00),
    ((0, 1, -2, 2, -1, 0, 0, 0), 0.18, 0.00),
    ((0, 0, 0, 0, 0, 8, -13, -1), -0.10, 0.05),
    ((0, 0, 0, 2, 0, 0, 0, 0), 0.15, 0.00),
    ((2, 0, -2, 0, -1, 0, 0, 0), -0.14, 0.00),
    ((1, 0, 0, -2, 1, 0, 0, 0), 0.14, 0.00),
    ((0, 1, 2, -2, 2, 0, 0, 0), -0.14, 0.00),
    ((1, 0, 0, -2, -1, 0, 0, 0), 0.14, 0.00),
    ((0, 0, 4, -2, 4, 0, 0, 0), 0.13, 0.00),
    ((0, 0, 2, -2, 4, 0, 0, 0), -0.11, 0.00),
    ((1, 0, -2, 0, -3, 0, 0, 0), 0.11, 0.00),
    ((1, 0, -2, 0, -1, 0, 0, 0), 0.11, 0.00),
)
_EE_COMPLEMENTARY_T = (((0, 0, 0, 0, 1, 0, 0, 0), -0.87, 0.00),)


def _fundamental_arguments(t):
    """The eight arguments of the complementary terms, in radians, at t
    Julian centuries of TT from J2000: the Delaunay arguments l, l', F, D
    and Omega (IERS Conventions 2010, eq. 5.43), the mean longitudes of
    Venus and the Earth, and the general precession in longitude p_A
    (eq. 5.44)."""
    def delaunay(c0, c1, c2, c3, c4):
        return math.fmod(c0 + t * (c1 + t * (c2 + t * (c3 + t * c4))), _TURN_ARCSEC) * _ARCSEC
    return (delaunay(485868.249036, 1717915923.2178, 31.8792, 0.051635, -0.00024470),
            delaunay(1287104.793048, 129596581.0481, -0.5532, 0.000136, -0.00001149),
            delaunay(335779.526232, 1739527262.8478, -12.7512, -0.001037, 0.00000417),
            delaunay(1072260.703692, 1602961601.2090, -6.3706, 0.006593, -0.00003169),
            delaunay(450160.398036, -6962890.5431, 7.4722, 0.007702, -0.00005939),
            math.fmod(3.176146697 + 1021.3285546211 * t, 2.0 * math.pi),
            math.fmod(1.753470314 + 628.3075849991 * t, 2.0 * math.pi),
            (0.024381750 + 0.00000538691 * t) * t)


def _ee_complementary_arcsec(t):
    """The complementary terms of the equation of the equinoxes, in
    arcseconds (IERS Conventions 2010, Table 5.2e)."""
    args = _fundamental_arguments(t)

    def series(terms):
        total = 0.0
        for mult, s, c in reversed(terms):
            a = sum(m * x for m, x in zip(mult, args))
            total += s * math.sin(a) + c * math.cos(a)
        return total
    return (series(_EE_COMPLEMENTARY) + series(_EE_COMPLEMENTARY_T) * t) * 1e-6


def _sidereal_frame(jd_ut):
    """(Greenwich apparent sidereal time, true obliquity), both in degrees,
    at a Julian Day in UT (taken as the Earth's rotation time, as Swiss
    Ephemeris takes it), by the route set out above."""
    nutation = swe.calc(jd_ut + swe.deltat_ex(jd_ut, -1), swe.ECL_NUT, swe.FLG_MOSEPH)[0]
    jd_tt = jd_ut + swe.deltat_ex(jd_ut, -1)
    dpsi_arcsec, deps_arcsec = nutation[2] * 3600.0, nutation[3] * 3600.0
    t = (jd_tt - 2451545.0) / 36525.0
    # The Earth rotation angle, in turns (eq. 5.15).
    era_turns = math.fmod(math.fmod(jd_ut, 1.0) + 0.7790572732640
                          + 0.00273781191135448 * (jd_ut - 2451545.0), 1.0)
    # The IAU 2006 mean obliquity (eq. 5.40), in arcseconds.
    eps_mean = 84381.406 + t * (-46.836769 + t * (-0.0001831 + t * (0.00200340
                                + t * (-0.000000576 + t * -0.0000000434))))
    # The IAU 2006 GMST less the rotation angle (eq. 5.32), in arcseconds.
    gmst_poly = 0.014506 + t * (4612.156534 + t * (1.3915817 + t * (-0.00000044
                                + t * (-0.000029956 + t * -0.0000000368))))
    equation_of_equinoxes = dpsi_arcsec * math.cos(eps_mean * _ARCSEC) + _ee_complementary_arcsec(t)
    gast = (era_turns * 360.0 + (gmst_poly + equation_of_equinoxes) / 3600.0) % 360.0
    return gast, (eps_mean + deps_arcsec) / 3600.0


def greenwich_sidereal_time(jd_ut):
    """The Greenwich apparent sidereal time, in degrees, at a Julian Day in
    UT: IAU 2006, by the IERS Conventions' equinox-based route, for every
    date (_sidereal_frame)."""
    return _sidereal_frame(jd_ut)[0]


def true_obliquity(jd_ut):
    """The true obliquity of the ecliptic, in degrees, at a Julian Day in UT:
    the IAU 2006 mean obliquity plus Swiss Ephemeris's nutation in
    obliquity, the obliquity that goes with greenwich_sidereal_time."""
    return _sidereal_frame(jd_ut)[1]


def chart_houses(jd_ut, lat, lon):
    """What swe.houses(jd_ut, lat, lon, b'B') returns, the twelve Alcabitius
    cusps and the angles (ascmc: [0] the Ascendant, [1] the MC, [2] the
    ARMC), with the ARMC from greenwich_sidereal_time plus the east
    longitude and the obliquity from true_obliquity, through
    swe.houses_armc."""
    gast, obliquity = _sidereal_frame(jd_ut)
    return swe.houses_armc((gast + lon) % 360.0, lat, obliquity, b'B')


# --- The quadrant division's status ---------------------------------------
# Swiss Ephemeris is the source of every cusp shown; the evaluation below only
# checks its set. Two planes fix the Ascendant: the ecliptic, whose pole is
# K = (0, -sin e, cos e) in the equatorial frame, and the horizon, whose pole
# is the zenith Z = (cos p cos T, cos p sin T, sin p), T the ARMC. They meet at
# the antipodes +-(K x Z). |K x Z| vanishes where the two planes coincide, once
# a sidereal day on the polar circle. g = (K x Z) . E, E the east point, says
# which antipode rises; it vanishes where the ecliptic only touches the
# horizon, twice a sidereal day above the polar circle, and across each such
# instant the rising degree turns to its opposite.
DIVISION_DEFINED = 'defined'
DIVISION_POLE = 'pole'
DIVISION_COINCIDENCE = 'coincidence'
DIVISION_TANGENCY = 'tangency'
DIVISION_UNRESOLVED = 'unresolved'
# The statuses at which no degree may be called the Ascendant. The pole is not
# among them: its Ascendant and Midheaven are shown, as the point where the
# ecliptic meets the horizon and the meridian, and only the division is refused.
ASCENDANT_WITHHELD = frozenset({DIVISION_COINCIDENCE, DIVISION_TANGENCY, DIVISION_UNRESOLVED})
POLE_BAND = 1e-6                # |latitude| within this of 90 counts as the pole
COINCIDENCE_BAND = 1e-9         # |K x Z| below this: the planes coincide
TANGENCY_BAND = 1e-12           # |g| below this: the ecliptic touches the horizon
CUSP_CHECK_TOLERANCE = 1e-6     # degrees, between Swiss Ephemeris's set and the check
CAUTION_MINUTE_DAYS = 60.0 / 86400.0
DIVISION_REASONS = {
    DIVISION_POLE: ("At the pole no ecliptic degree rises or sets, so the Ascendant has no semi-arc "
                    "and the quadrant divisions are undefined at this latitude."),
    DIVISION_TANGENCY: ("At this moment the ecliptic only touches the horizon here, so no degree is rising and the "
                        "quadrant divisions are undefined for this birth time."),
    DIVISION_COINCIDENCE: ("At this moment the ecliptic lies along the horizon here, so no degree is rising and the "
                           "quadrant divisions are undefined for this birth time."),
    DIVISION_UNRESOLVED: ("The quadrant divisions cannot be computed reliably for this birth time at this latitude, "
                          "so they are not shown."),
}
# The same three where the birth time stands and a revolution's moment does not.
REVOLUTION_DIVISION_REASONS = {
    DIVISION_TANGENCY: ("At this moment the ecliptic only touches the horizon here, so no degree is rising and the "
                        "quadrant divisions are undefined for this revolution."),
    DIVISION_COINCIDENCE: ("At this moment the ecliptic lies along the horizon here, so no degree is rising and the "
                           "quadrant divisions are undefined for this revolution."),
    DIVISION_UNRESOLVED: ("The quadrant divisions cannot be computed reliably for this revolution at this latitude, "
                          "so they are not shown."),
}
ASCENDANT_LEAP_CAUTION = ("Above the polar circle the rising degree can leap across the zodiac within minutes; here a "
                          "minute's difference in the birth time would turn the Ascendant to its opposite.")


class DivisionWithheld(ValueError):
    """Something tried to count from a cusp or an Ascendant the chart withholds."""


class WithheldCusps(tuple):
    """What a chart holds in place of its twelve cusps when the status is not
    defined: no cusps at all, the status and its reason. Empty, so a loop over
    it draws nothing and a test of it reads false; `ascendant` is the pole's
    point, the one value a reader of the first cusp may still ask for, and None
    at the other three statuses."""

    def __new__(cls, status, ascendant=None):
        self = super().__new__(cls)
        self.status, self.ascendant = status, ascendant
        return self

    def __getnewargs__(self):
        return self.status, self.ascendant

    @property
    def reason(self):
        return DIVISION_REASONS[self.status]


def division_refusal(cusps):
    """The sentence a reader of these cusps refuses with, or None when they
    are the chart's twelve."""
    return cusps.reason if isinstance(cusps, WithheldCusps) else None


def first_cusp(cusps):
    """The Ascendant's degree as a reader of the first cusp asks for it: the
    pole's point stands behind withheld cusps. Raises where none does."""
    if not isinstance(cusps, WithheldCusps):
        return cusps[0]
    if cusps.ascendant is None:
        raise DivisionWithheld(cusps.reason)
    return cusps.ascendant


def _horizon_terms(lat, armc, obliquity):
    """(A, B, g): K x Z in the ecliptic's own axes is (-B, A), so
    |K x Z| = hypot(A, B); g is the rising side's east component."""
    p, t, e = math.radians(lat), math.radians(armc), math.radians(obliquity)
    a = math.cos(p) * math.cos(t)
    b = math.cos(p) * math.sin(t) * math.cos(e) + math.sin(p) * math.sin(e)
    g = math.cos(p) * math.cos(e) + math.sin(p) * math.sin(e) * math.sin(t)
    return a, b, g


def alchabitius_check(lat, armc, obliquity):
    """The twelve Alchabitius cusps evaluated from the definition, with no
    library call: the rising root of the two planes, its semi-arc by the
    stable form, the semi-arcs trisected in right ascension and each projected
    on the ecliptic. It checks Swiss Ephemeris's set and is never shown.
    None where the construction has no value (coincidence, tangency, the pole)."""
    if abs(lat) >= 90.0 - POLE_BAND:
        return None
    a, b, g = _horizon_terms(lat, armc, obliquity)
    if math.hypot(a, b) < COINCIDENCE_BAND or abs(g) < TANGENCY_BAND:
        return None
    p, t, e = math.radians(lat), math.radians(armc), math.radians(obliquity)
    ascendant = (math.degrees(math.atan2(a, -b)) + (180.0 if g < 0.0 else 0.0)) % 360.0
    day = math.degrees(math.atan2(abs(g), -math.copysign(1.0, g) * math.sin(p) * math.sin(e) * math.cos(t)))
    night = 180.0 - day

    def on_ecliptic(right_ascension):
        r = math.radians(right_ascension)
        return math.degrees(math.atan2(math.sin(r), math.cos(e) * math.cos(r))) % 360.0

    cusps = [0.0] * 12
    cusps[0], cusps[9] = ascendant, on_ecliptic(armc)
    for i, ra in ((10, armc + day / 3.0), (11, armc + 2.0 * day / 3.0),
                  (1, armc + day + night / 3.0), (2, armc + day + 2.0 * night / 3.0)):
        cusps[i] = on_ecliptic(ra)
    for i, opposite in ((3, 9), (4, 10), (5, 11), (6, 0), (7, 1), (8, 2)):
        cusps[i] = (cusps[opposite] + 180.0) % 360.0
    return tuple(cusps)


def _set_is_in_order(cusps):
    """Each step forward positive, and once round the zodiac. In floats a
    reversed step reads as nearly 360 degrees, and the sum shows it."""
    steps = [(cusps[(i + 1) % 12] - cusps[i]) % 360.0 for i in range(12)]
    return all(step > 0.0 for step in steps) and abs(sum(steps) - 360.0) < 1.0


def _is_rising(longitude, armc, obliquity):
    """Whether a degree on the horizon lies on its eastern side."""
    l, t, e = math.radians(longitude), math.radians(armc), math.radians(obliquity)
    return -math.sin(t) * math.cos(l) + math.cos(t) * math.cos(e) * math.sin(l) > 0.0


def division_status(lat, armc, obliquity, cusps):
    """One of defined, pole, coincidence, tangency or unresolved, for Swiss
    Ephemeris's set `cusps` at this latitude, ARMC and true obliquity."""
    if abs(lat) >= 90.0 - POLE_BAND:
        return DIVISION_POLE
    a, b, g = _horizon_terms(lat, armc, obliquity)
    if math.hypot(a, b) < COINCIDENCE_BAND:
        return DIVISION_COINCIDENCE
    if abs(g) < TANGENCY_BAND:
        return DIVISION_TANGENCY
    if not _set_is_in_order(cusps) or not _is_rising(cusps[0], armc, obliquity):
        return DIVISION_UNRESOLVED
    check = alchabitius_check(lat, armc, obliquity)
    if any(abs((c - k + 180.0) % 360.0 - 180.0) > CUSP_CHECK_TOLERANCE for c, k in zip(cusps, check)):
        return DIVISION_UNRESOLVED
    return DIVISION_DEFINED


def judged_division(cusps, ascmc, lat, armc, obliquity):
    """(cusps, ascmc, status) for what chart_houses returned at this ARMC and
    obliquity: Swiss Ephemeris's twelve cusps when the status is defined, and
    WithheldCusps when it is not. ascmc is Swiss's as it stands, for the
    Midheaven and the ARMC; only the pole's first value is a point a chart may
    name, and a caller reads the Ascendant from there only where the status
    lets it."""
    status = division_status(lat, armc % 360.0, obliquity, cusps)
    if status == DIVISION_DEFINED:
        return cusps, ascmc, status
    return WithheldCusps(status, ascmc[0] if status == DIVISION_POLE else None), ascmc, status


def house_division(jd_ut, lat, lon):
    """chart_houses with the status beside it: (cusps, ascmc, status)."""
    gast, obliquity = _sidereal_frame(jd_ut)
    cusps, ascmc = chart_houses(jd_ut, lat, lon)
    return judged_division(cusps, ascmc, lat, (gast + lon) % 360.0, obliquity)


def ascendant_turns_within_a_minute(jd_ut, lat, lon):
    """Whether a defined chart's Ascendant is a minute of birth time from its
    opposite: a tangent instant lies between this moment and the moment one
    minute before or after it, which g's sign changing across the interval
    says. Only above the polar circle can g change sign."""
    gast, obliquity = _sidereal_frame(jd_ut)
    if abs(lat) + obliquity < 90.0:
        return False
    here = _horizon_terms(lat, (gast + lon) % 360.0, obliquity)[2]
    for minute in (-CAUTION_MINUTE_DAYS, CAUTION_MINUTE_DAYS):
        gast_there, obliquity_there = _sidereal_frame(jd_ut + minute)
        if here * _horizon_terms(lat, (gast_there + lon) % 360.0, obliquity_there)[2] < 0.0:
            return True
    return False


# --- The civil calendar ---------------------------------------------------
# ONE policy, in one place. The digits of a civil date are a JULIAN-calendar
# date before 1582-10-15 and a Gregorian one from that day on, as Solar Fire
# and astro.com read them; the Swiss Ephemeris manual (s. 9.1) keeps the two
# flags apart for exactly this reason. Using the wrong flag mis-dates a
# historical chart by days (seven in the 1200s), which the Moon turns into
# tens of degrees.
#
# Python's datetime is proleptic Gregorian and CANNOT HOLD a Julian-only day:
# 1300-02-29 exists in the Julian calendar and not in the Gregorian. So the
# carrier of a civil date in this file is CivilDate / CivilMoment below, and a
# shift by a UTC offset is done on the Julian Day, never by datetime
# arithmetic. The earlier adapter subtracted the offset with datetime,
# producing Gregorian components, and then read those digits back as Julian:
# local Julian 1300-03-01 00:30 at +02:00 came out a full day wrong. Rounding a moment to the second is done on the JD
# too, so that a carry across midnight is a date carry, not a clamp.
PN4_GREGORIAN_REFORM_JD = 2299160.5     # 1582-10-15 00:00 UT, the first Gregorian day
_MONTH_ABBR = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')
_MONTH_NAME = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August',
               'September', 'October', 'November', 'December')

def civil_calendar(year, month, day):
    """swe.JUL_CAL or swe.GREG_CAL for a civil date's digits, by the policy above."""
    return swe.GREG_CAL if (int(year), int(month), int(day)) >= (1582, 10, 15) else swe.JUL_CAL

def civil_is_valid(year, month, day):
    """Whether the digits name a day in the calendar the policy assigns them:
    1300-02-29 is valid (Julian), 1900-02-29 is not (Gregorian)."""
    year, month, day = int(year), int(month), int(day)
    if not (1 <= year <= 9999 and 1 <= month <= 12 and 1 <= day <= 31):
        return False
    cal = civil_calendar(year, month, day)
    y, m, d, _h = swe.revjul(swe.julday(year, month, day, 0.0, cal), cal)
    return (int(y), int(m), int(d)) == (year, month, day)

def civil_to_jd(year, month, day, hour=0.0):
    """The Julian Day of a civil moment (UT hour, decimal), calendar by policy."""
    return swe.julday(int(year), int(month), int(day), float(hour), civil_calendar(year, month, day))

def civil_local_to_jd_ut(year, month, day, hour_local, utc_offset_hours):
    """A LOCAL civil moment to UT as a Julian Day: the calendar is decided by
    the local digits, the offset (east positive, hours) is subtracted on the
    JD. This is the sidebar's adapter for LMT and manual offsets."""
    return civil_to_jd(year, month, day, hour_local) - float(utc_offset_hours) / 24.0

def _format_civil(c, spec):
    """strftime's common directives for CivilDate / CivilMoment: %Y %m %d %b
    %B %H %M %S %%. Anything else is left in place."""
    if not spec:
        return c.isoformat()
    out, i = [], 0
    while i < len(spec):
        ch = spec[i]
        if ch == '%' and i + 1 < len(spec):
            d = spec[i + 1]
            rep = {'Y': f"{c.year:04d}", 'm': f"{c.month:02d}", 'd': f"{c.day:02d}",
                   'b': _MONTH_ABBR[c.month - 1], 'B': _MONTH_NAME[c.month - 1],
                   'H': f"{getattr(c, 'hour', 0):02d}", 'M': f"{getattr(c, 'minute', 0):02d}",
                   'S': f"{getattr(c, 'second', 0):02d}", '%': '%'}.get(d)
            if rep is not None:
                out.append(rep)
                i += 2
                continue
        out.append(ch)
        i += 1
    return ''.join(out)

class CivilDate:
    """A civil date as digits, read in the calendar civil_calendar() assigns
    them. Carries a birth or target date where datetime.date used to, and
    unlike it can hold a Julian-only day. Compares equal to anything with
    the same year, month and day (a datetime.date included)."""
    __slots__ = ('year', 'month', 'day')

    def __init__(self, year, month, day):
        self.year, self.month, self.day = int(year), int(month), int(day)

    @classmethod
    def of(cls, d):
        return d if isinstance(d, cls) else cls(d.year, d.month, d.day)

    @classmethod
    def from_jd(cls, jd):
        cal = swe.GREG_CAL if jd >= PN4_GREGORIAN_REFORM_JD else swe.JUL_CAL
        y, m, d, _h = swe.revjul(jd, cal)
        return cls(y, m, d)

    def tuple(self):
        return (self.year, self.month, self.day)

    def __eq__(self, other):
        try:
            return self.tuple() == (int(other.year), int(other.month), int(other.day))
        except (AttributeError, TypeError, ValueError):
            return NotImplemented

    def __lt__(self, other):
        return self.jd() < CivilDate.of(other).jd()

    def __hash__(self):
        return hash(self.tuple())

    def __sub__(self, other):
        # a timedelta (days) back, or the number of days between two dates
        if hasattr(other, 'days') and not hasattr(other, 'year'):
            return CivilDate.from_jd(self.jd() - other.days)
        return self.jd() - CivilDate.of(other).jd()

    def __add__(self, other):
        return CivilDate.from_jd(self.jd() + other.days)

    def jd(self, hour=0.0):
        return civil_to_jd(self.year, self.month, self.day, hour)

    def replace(self, **kw):
        return CivilDate(kw.get('year', self.year), kw.get('month', self.month), kw.get('day', self.day))

    def calendar_name(self):
        return 'Julian' if civil_calendar(self.year, self.month, self.day) == swe.JUL_CAL else 'Gregorian'

    def isoformat(self):
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"

    def __format__(self, spec):
        return _format_civil(self, spec)

    def __str__(self):
        return self.isoformat()

    def __repr__(self):
        return f"CivilDate({self.year}, {self.month}, {self.day})"

class CivilMoment(CivilDate):
    """A CivilDate with a time of day (whole seconds), UT or local as the
    caller says. from_jd rounds the JD to the second FIRST, so a moment a
    fraction of a second before midnight carries into the next day."""
    __slots__ = ('hour', 'minute', 'second')

    def __init__(self, year, month, day, hour=0, minute=0, second=0):
        super().__init__(year, month, day)
        self.hour, self.minute, self.second = int(hour), int(minute), int(second)

    @classmethod
    def from_jd(cls, jd, calendar=None):
        """`calendar` (swe.JUL_CAL / swe.GREG_CAL) writes the moment in that
        calendar instead of the epoch's own: the sidebar writes a UT in the
        birth date's calendar, so a Julian birth whose UT falls after the
        reform's JD is not printed as a Gregorian date under the "Julian
        calendar" label."""
        jd = round(float(jd) * 86400.0) / 86400.0
        cal = calendar if calendar is not None else (swe.GREG_CAL if jd >= PN4_GREGORIAN_REFORM_JD else swe.JUL_CAL)
        y, m, d, hour = swe.revjul(jd, cal)
        total = min(int(round(hour * 3600.0)), 24 * 3600 - 1)
        return cls(y, m, d, total // 3600, (total % 3600) // 60, total % 60)

    def hour_decimal(self):
        return self.hour + self.minute / 60.0 + self.second / 3600.0

    def jd(self, hour=None):
        return civil_to_jd(self.year, self.month, self.day, self.hour_decimal() if hour is None else hour)

    def isoformat(self):
        return f"{super().isoformat()} {self.hour:02d}:{self.minute:02d}:{self.second:02d}"

    def __repr__(self):
        return f"CivilMoment({self.year}, {self.month}, {self.day}, {self.hour}, {self.minute}, {self.second})"


def _calendar_date_is_valid(year, month, day, calendar):
    if not (1 <= int(year) <= 9999 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31):
        return False
    y, m, d, _hour = swe.revjul(swe.julday(int(year), int(month), int(day), 0.0, calendar), calendar)
    return (int(y), int(m), int(d)) == (int(year), int(month), int(day))


def _moment_from_jd_in_calendar(jd, calendar):
    # Round the clock to a whole second relative to civil midnight. A value
    # that rounds to 24:00 belongs to the next date; clamping it to 23:59:59
    # silently changes the represented instant.
    day_start = math.floor(float(jd) + 0.5) - 0.5
    seconds = int(round((float(jd) - day_start) * 86400.0))
    if seconds >= 86400:
        day_start += 1.0
        seconds -= 86400
    elif seconds < 0:
        day_start -= 1.0
        seconds += 86400
    year, month, day, _hour = swe.revjul(day_start, calendar)
    return CivilMoment(year, month, day, seconds // 3600, (seconds % 3600) // 60, seconds % 60)


def pn4_datetime_from_jd(jd, calendar=None):
    """The UT civil moment of a Julian Day, as a CivilMoment (not a datetime,
    which cannot hold a Julian-only day such as 1300-02-29): the calendar
    is the one this file uses for that epoch, so feeding it back to
    calculate_traditional_chart -- which reads the digits by the same
    policy -- round-trips. The name is kept for its callers; it formats
    with the same %Y-%m-%d %H:%M:%S directives a datetime does. `calendar`
    writes the moment in a named calendar (the sidebar's UT in the birth
    date's)."""
    return CivilMoment.from_jd(jd, calendar)

def _civil_canonical(d):
    """The digits a civil day is written in by its own epoch: Julian before
    the reform's JD, Gregorian from it. The parser reads the digits of the
    reform gap (1582-10-05 to 1582-10-14) as Julian, so each of them is the
    Julian Day of a Gregorian day ten days on (1582-10-10 is 1582-10-20);
    every other valid spelling is its own canonical form."""
    return CivilDate.from_jd(CivilDate(d.year, d.month, d.day).jd())


# What `from ephemeris import *` gives the engine: every name this module
# binds, the standard modules among them, but the two it rebinds as it runs
# (the module docstring says why).
__all__ = [
    '_ARCSEC',
    'chart_houses',
    'DIVISION_DEFINED',
    'DIVISION_POLE',
    'DIVISION_COINCIDENCE',
    'DIVISION_TANGENCY',
    'DIVISION_UNRESOLVED',
    'ASCENDANT_WITHHELD',
    'POLE_BAND',
    'COINCIDENCE_BAND',
    'TANGENCY_BAND',
    'CUSP_CHECK_TOLERANCE',
    'CAUTION_MINUTE_DAYS',
    'DIVISION_REASONS',
    'REVOLUTION_DIVISION_REASONS',
    'ASCENDANT_LEAP_CAUTION',
    'DivisionWithheld',
    'WithheldCusps',
    'division_refusal',
    'first_cusp',
    '_horizon_terms',
    'alchabitius_check',
    '_set_is_in_order',
    '_is_rising',
    'division_status',
    'judged_division',
    'house_division',
    'ascendant_turns_within_a_minute',
    '_TURN_ARCSEC',
    '_EE_COMPLEMENTARY',
    '_EE_COMPLEMENTARY_T',
    '_fundamental_arguments',
    '_ee_complementary_arcsec',
    '_sidereal_frame',
    'greenwich_sidereal_time',
    'true_obliquity',
    'EPHEMERIS_FOLDER_NAME_REFUSAL',
    '_CODE_PAGE_CLAUSE',
    'EphemerisFolderNameRefused',
    'atexit',
    '_calendar_date_is_valid',
    'civil_calendar',
    '_civil_canonical',
    'civil_is_valid',
    'civil_local_to_jd_ut',
    'civil_to_jd',
    'CivilDate',
    'CivilMoment',
    '_delta_t_as_recorded',
    '_delta_t_reference',
    '_DELTA_T_RECORDED',
    '_delta_t_table',
    '_EPHEMERIS_CATALOGUE',
    '_ephemeris_folder_as_made',
    '_EPHEMERIS_FOLDER_BYTES',
    '_ephemeris_folder_here',
    '_ephemeris_folder_hold',
    '_ephemeris_folder_is_held',
    '_ephemeris_folder_is_ours',
    '_ephemeris_folder_is_safe',
    '_ephemeris_folder_unsafe',
    '_EPHEMERIS_FOLDER_LOCK',
    '_ephemeris_folder_make',
    'EPHEMERIS_FOLDER_REFUSAL',
    '_ephemeris_folder_remove',
    '_ephemeris_folder_rmdir',
    '_ephemeris_folder_where',
    '_EPHEMERIS_HELD',
    '_EPHEMERIS_LOADED_FIRST',
    '_EPHEMERIS_LOCK',
    '_EPHEMERIS_PREFIX',
    'EPHEMERIS_REFUSAL',
    'ephemeris_thread_check',
    '_ephemeris_thread_pointed',
    '_ephemeris_thread_ready',
    '_EPHEMERIS_THREADS',
    'EphemerisFolderRefused',
    'EphemerisRefused',
    '_format_civil',
    'math',
    '_moment_from_jd_in_calendar',
    '_MONTH_ABBR',
    '_MONTH_NAME',
    'MOSHIER_FLAGS',
    'os',
    'pn4_datetime_from_jd',
    'PN4_GREGORIAN_REFORM_JD',
    'shutil',
    'st',
    'stat',
    'struct',
    'swe',
    '_swisseph',
    '_SwissEphemeris',
    'sys',
    'tempfile',
    'threading',
]
