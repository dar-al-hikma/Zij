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
# moved every value, and a catalogue there replaced the stars (the owner's
# ruling 103, from an outside audit of the library's file reads).
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
# _ephemeris_folder_remove, the owner's ruling 183); on Windows, where no
# descriptor is held, a folder moved aside is left behind. At its own path
# and at the one the system gives, it is known and removed through a
# descriptor on that path's parent, so the one directory a race can put in
# its place is an empty one swapped in at its very name in that parent
# (_ephemeris_folder_rmdir, the owner's ruling 188). Where it has gone --
# a temporary-files cleaner, or one that moves it aside -- whatever stands at
# its path is not removed at exit (on POSIX, whatever number its filesystem
# gave it), and is not used: a new folder is made unless what stands at the
# path is the very folder the engine made, known by the same identity, and
# still this user's with mode 0700 (_ephemeris_folder_is_held; the owner's
# rulings 139 and 141). A directory made or moved into its place is not that
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
# (_delta_t_reference): a thread that took a table from a swapped-in
# directory is refused for its life, unless the reference was read from one
# too; then a thread that read the same table is accepted, and every thread
# that read the library's own is refused. A program running as the
# same user could likewise write into the folder itself after looking for
# it; each thread's first call checks that the folder holds no other file.
# None of these checks is a lock.
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
    Delta T table before it was pointed at the folder. Its words are for
    whoever reads the state; the page says EPHEMERIS_REFUSAL and stops.
    Raised by `import engine` itself (an import made again, after the
    engine was dropped from sys.modules, in a thread its first calculation
    points at a folder holding such a file), it is caught where app.py
    imports the engine, which says the same sentence."""


class EphemerisFolderRefused(EphemerisRefused):
    """No private folder of the engine's own can be had: none can be made
    (the temporary directory has gone, the disk is full), none can be made
    this user's 0700 one (a filesystem that keeps no modes), its name cannot
    be given to Swiss Ephemeris whole (the owner's rulings 122 and 138: its
    bytes, not its characters), it cannot be held open to be known again at
    exit (no descriptor left; the owner's ruling 139), or the folder went
    before it could be listed. Nothing is computed (the owner's ruling
    120). The page says EPHEMERIS_FOLDER_REFUSAL and stops; raised at
    import, by `import engine` itself, it is caught where app.py imports the
    engine, which says the same sentence."""


_EPHEMERIS_FOLDER_BYTES = 200


def _ephemeris_folder_is_safe(folder):
    """True for a folder Swiss Ephemeris takes whole as its path: absolute,
    with no ';' (nor, outside Windows, ':'), where it splits a path into
    folders, and not too long. The library is handed bytes, not characters:
    the name's UTF-8 form through its path setter, the filesystem's form
    through $SE_EPHE_PATH. A path of more than 242 bytes (measured on the
    pinned wheel, on both routes, for characters of one to four bytes) is
    dropped for the compiled default, the working directory first, however
    few its characters: 200 bytes leaves room (the owner's ruling 138).
    A name with no UTF-8 form (a byte the filesystem's encoding could not
    decode: the path setter cannot take it), whose two forms differ (the
    setter would be handed a name that is not the folder's), or holding a
    NUL (neither route carries one) is refused too. Never raises."""
    if not isinstance(folder, str) or not folder or not os.path.isabs(folder):
        return False
    rest = folder[2:] if os.name == 'nt' and folder[1:2] == ':' else folder
    if ';' in folder or ':' in rest or '\0' in folder:
        return False
    try:
        handed = folder.encode('utf-8')
        named = os.fsencode(folder)
    except (UnicodeError, ValueError):
        return False
    return handed == named and len(handed) <= _EPHEMERIS_FOLDER_BYTES


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
    engine made there (the owner's ruling 141, by ruling 139's identity),
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
    the process's life (the owner's ruling 139). On POSIX, a descriptor
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
    a link between the two cannot carry the removal anywhere else (the
    owner's ruling 188). Links earlier in the parent's path are followed as
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
    whatever number its filesystem gave it (the owner's ruling 139). On
    POSIX `held` is the descriptor held on the folder since it was made
    (_ephemeris_folder_hold): a folder whose link count has fallen to 0 was
    removed, and nothing is touched; one still linked is emptied through
    the descriptor -- its own entries -- wherever it now stands, and only
    then removed by a path: its own, where it still stands there, or else
    the path the system gives for the descriptor (_ephemeris_folder_where:
    the folder moved aside by another program is found where it went; the
    owner's ruling 183), each used only where what stands there is a real
    directory with the held (st_dev, st_ino) and a link count above 0, both
    judged and removed through a descriptor on that path's parent
    (_ephemeris_folder_rmdir, the owner's ruling 188). So the one race left
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
    Ephemeris takes whole (_ephemeris_folder_is_safe; the owner's rulings
    122 and 138), and where it cannot be held open to be known again at exit
    (_ephemeris_folder_hold; the owner's ruling 139). The exit hook is
    registered here, once per folder made."""
    try:
        folder = os.path.abspath(tempfile.mkdtemp(prefix=_EPHEMERIS_PREFIX))
    except OSError:
        raise EphemerisFolderRefused("no temporary folder could be made for Swiss Ephemeris; nothing is computed") from None
    if not _ephemeris_folder_is_safe(folder):
        os.rmdir(folder)
        raise EphemerisFolderRefused("the temporary folder's name cannot be given to Swiss Ephemeris whole "
                                     "(it holds ';' or ':', is too long in bytes, or cannot be handed to it as it "
                                     "is named); point TMPDIR, TEMP or TMP at a plain folder")
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
# directory made or moved into its place since; the owner's ruling 141), and
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
    moved into its place; the owner's rulings 139 and 141): its name was
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


def _delta_t_reference():
    """The table as a thread holds it when its first call points it at the
    folder: read once per process, in a thread of its own, pointed at the
    folder as _ephemeris_folder_here has just accepted it, by its held
    identity, or made it. The library then reads the folder by its name: a
    directory swapped in at the path between that check and the read would
    be read (the check is not a lock), and the reference taken from it."""
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
            _DELTA_T_REFERENCE = box[0]
        return _DELTA_T_REFERENCE


# The page's sentences: no folder, no file's name, no exception text (as
# ruling 58 (c) keeps the stars' refusal); the owner's words, each for its
# own refusal. EPHEMERIS_REFUSAL is for the two EphemerisRefused describes;
# closing and opening the app clears both (a new process makes a new
# folder, and its threads are new). EPHEMERIS_FOLDER_REFUSAL is for every
# case where no private folder can be had (EphemerisFolderRefused; the
# owner's rulings 120 and 121). app.py holds both in the same words, for a
# refusal at the engine's import, when the engine never loaded.
EPHEMERIS_REFUSAL = ("Nothing is calculated: Swiss Ephemeris found a file this app does not supply. "
                     "Close the app and open it again.")
EPHEMERIS_FOLDER_REFUSAL = ("Nothing is calculated: this app could not make a private folder for its ephemeris "
                            "in the computer's temporary folder.")


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
    keeps it for its life. (Swiss Ephemeris built without per-thread state,
    as some platforms build it, shares one table among all threads; there
    the reference table is that one, and this check cannot see a file read
    before the folder was set.)"""
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
    pointed: its next call makes a new folder and points it there (the
    owner's ruling 141), so from its next call a thread already pointed at
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
# every one of those calls, as the bodies' already did. swe.houses and
# swe.sidtime take no flag and keep the library's default delta T whatever
# ephemeris file is on disk. The obliquity of the moment (true obliquity,
# ECL_NUT) keeps that default too, asked so that no ephemeris file can reach
# it either: swe.calc(jd + swe.deltat_ex(jd, -1), swe.ECL_NUT, swe.FLG_MOSEPH)
# -- delta T at -1 is the library's default tidal term, whatever file a thread
# has open, and ECL_NUT is obliquity and nutation from formulae at that
# instant. (swe.calc_ut(jd, swe.ECL_NUT) gave the same value only while no
# Moon file was readable, or after a Moshier read earlier in the thread.) A
# delta T file (sedeltat.txt) would still reach all three, and every other
# value with them; it is not an ephemeris file, and is kept out by the
# engine's folder (SWISS EPHEMERIS'S FILES, above), not by these flags.
MOSHIER_FLAGS = swe.FLG_MOSEPH | swe.FLG_SPEED


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
# local Julian 1300-03-01 00:30 at +02:00 came out a full day wrong (Astra
# audit 2026-09-11, F01). Rounding a moment to the second is done on the JD
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
        calendar" label (the hostile pass of 2026-09-22, M4)."""
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
    'atexit',
    '_calendar_date_is_valid',
    'civil_calendar',
    '_civil_canonical',
    'civil_is_valid',
    'civil_local_to_jd_ut',
    'civil_to_jd',
    'CivilDate',
    'CivilMoment',
    '_delta_t_reference',
    '_delta_t_table',
    '_EPHEMERIS_CATALOGUE',
    '_ephemeris_folder_as_made',
    '_EPHEMERIS_FOLDER_BYTES',
    '_ephemeris_folder_here',
    '_ephemeris_folder_hold',
    '_ephemeris_folder_is_held',
    '_ephemeris_folder_is_ours',
    '_ephemeris_folder_is_safe',
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
