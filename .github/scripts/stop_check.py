#!/usr/bin/env python3
"""Start, reach and stop a built download from outside, as a reader does.

The desktop build runs this after packaging and before any upload. For the
download built on this runner it checks three launches:

1. The ordinary stop. The download is started from its own zip, unpacked
   afresh, with a fresh data folder, and reached: its server answers on its
   own local address and its window is open. Its server must then refuse
   (403) a WebSocket opening of the session's route under a name rebound to
   this computer, and one under its own address sent from another site's
   Origin, and open one (101) under the window's own address: a page whose
   own name is made to point here, or a page of another site, gets no
   session. Once reached, its
   launcher must have made its window log, a file and not a link, in the
   fresh data folder: only the engine gives the launcher that folder, so the
   log shows that the download loaded its engine. And its window must be
   seen to show the app, not the sentence a session without the key is
   told: within the bound for a run, the server's own metrics must show
   files the app's page hands its window, which only a session the server
   lets in is given (one refused is told one sentence and stops), and this
   check opens no session that runs the app in this launch. The window is
   then closed as a reader closes it (Windows: a close message to the
   window; macOS: Quit).
   Within the launcher's own bound for stopping its server plus a margin, no
   process of that launch may remain and its port may no longer answer. On
   Windows the unpacked folder must then be removable, which shows that no
   file in it is still held open.
2. The launcher alone ended abruptly. A second launch is reached (its
   server's door, its window log and its window's admission as the
   first's), and only
   its launcher process is ended (Windows: process termination; macOS:
   SIGKILL). Within the server's own bound for ending without its launcher
   plus the margin, no process of that launch may remain.
3. A place typed in the city search. The download's own server entry is
   started as the launcher starts its child (the executable with the
   sentinel and a free port; no STREAMLIT_* variable; a key this check
   makes, in the environment alone; its input a pipe only this check
   holds, and its output and errors a pipe the check reads as it comes),
   from the zip unpacked afresh, with a fresh data folder. Once it has
   said it listens, holds its port and answers, a session is opened as the
   window opens one (its own Host and Origin, the cookie and token of its
   server's XSRF protection), the first run is asked with the key in the
   address, and a place is typed in the city search -- the text box read
   from that run by the app's key for it -- spelt so that only the
   search's second, folded look finds it. The server's door must hold as
   in the first launch. The run with the place typed must offer that
   place's label among the choices of place: the download found its place
   atlas and read it. The first run must have drawn the example chart the
   app opens on with Jupiter where the engine computes it on the system the
   suite runs on: the download's own build of Swiss Ephemeris computed it.
   The
   sentence a session without the key is told fails the check here. Then,
   while that session is still open, two more sessions are opened as the
   window opens one, one with no key in the address and one with a key one
   letter off the launch's: the first run of each must show that sentence
   and nothing else. A run that does not end within its bound is reported
   by how far it got. The server is then stopped as the launcher stops it,
   by the end of its input, and within its bound for that plus the margin
   no process of that launch may remain.

The processes of a launch are found by the launch itself -- the launcher,
every process descended from it while the launch ran, and every process
whose executable lies inside the unpacked download -- never by a process
name. Each step prints one line. Nothing printed names a folder outside the
download; nothing reads the key of a launch the launcher started, and the
key the check makes for the third is printed nowhere.

A failure is followed by what the outside can see of why: every process of
the launch seen, with its parent; whether the launcher ended alone or handed
off to a process it started that runs on; its exit status where this check
started it; whether the app made its data folder, and its window log; the
last lines the launcher wrote on its standard output and error (macOS, where
Launch Services opens the bundle with them in the launch's fresh folder, and
a command on Linux); and on macOS the header of any crash report the system
wrote for the bundle's executable after the launch began. Each line is
bounded and has every home folder and the launch's key written over.

A window this runner cannot open fails the check: a check that skips is not
a check. Exit status 0 when every step held, 1 otherwise. Standard library
only.

    python .github/scripts/stop_check.py      # on the build runner

On Linux, where the suite tests this script, a launch is a command and its
window a stand-in that the command shows by a file; the build runners never
take that path:

    python .github/scripts/stop_check.py --stand-in-windows DIR [--folder DIR] --command ARGV...
"""
import argparse
import base64
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile

# The launcher's own bounds (desktop_launcher.py). Its stop waits
# STOP_WAIT_SECONDS for its server to end and KILL_WAIT_SECONDS more after
# killing it; a server whose launcher is gone ends within ORPHAN_WAIT_SECONDS.
STOP_SECONDS = 10.0 + 5.0
ORPHAN_SECONDS = 10.0
# Added to either bound before a launch still running counts as a failure:
# the window's own teardown, and the process's exit after its server's.
MARGIN_SECONDS = 10.0
# From the start to the server answering and the window open. The launcher
# itself waits up to 25 s for its server; a first start of a packaged build
# on a fresh runner also unpacks and scans every file it loads.
REACH_SECONDS = 120.0

POLL_SECONDS = 0.5
# The name a WebSocket opening is sent under once the server answers, as a
# page whose own name points at this computer sends it, and how long each
# opening may take to be answered.
REBOUND_HOST = "evil.example"
# The Origin a page of another site sends with its opening: refused (403)
# under the server's own Host too.
FOREIGN_ORIGIN = "http://evil.example"
PROBE_SECONDS = 10.0
# What a failure may print of a text the launch wrote: its last lines, each
# cut to a width, read from at most the file's last bytes.
TAIL_LINES = 40
LINE_CHARS = 300
TAIL_BYTES = 65536
APP_DIR_NAME = "Zij"
# The window log the launcher makes in the folder the engine gives it.
WINDOW_LOG_NAME = "webview_debug.log"
# The server's own metrics: the memory its media files hold, the files the
# app's page hands its window (a session refused for want of the key is told
# one sentence and stops, and is handed none), and the results of the
# engine's cached calculations, which a refused session never reaches either.
METRICS_PATH = "/_stcore/metrics"
_MEDIA = re.compile(r'(?m)^cache_memory_bytes\{cache_type="st_memory_media_file_storage",cache="[^"]*"\} (\d+)$')
_ENGINE_RESULT = re.compile(r'(?m)^cache_memory_bytes\{cache_type="st_cache_data",cache="engine\.(\w+)"\} \d')
ZIPS = {"win32": "Zij-windows.zip", "darwin": "Zij-macos.zip"}

# The third launch: the download's own server entry, started as the
# launcher starts its child (desktop_launcher.py: the sentinel and the port
# after the executable, the launch's key in the environment under its name,
# the mark the child writes once it listens), and a place typed in the
# app's city search (app.py: the search box's key, the label of the choice
# of place under it, the sentence a session without the key is told).
SERVER_SENTINEL = "--run-streamlit-server"
LISTENING_MARK = "zij-server-listening"
LAUNCH_KEY_VARIABLE = "ZIJ_LAUNCH_KEY"
LAUNCH_KEY_PARAMETER = "launch"
LAUNCH_KEY_REFUSAL = ("This app can be used only in the window it opens when it starts; "
                      "use that window, or start the app again.")
CITY_SEARCH_KEY = "location_input_key"
PLACE_CHOICE_LABEL = "Select specific location:"
# Typed in the other case from the atlas's name, with a letter outside
# ASCII: as typed it finds no place, so only the search's second, folded
# look finds it. The label is the atlas's most populous place of the name,
# and the only option with that label.
PLACE_TYPED = "\u00e9vora"
PLACE_FOUND = "\u00c9vora, 08 (PT)"
# A known value of the example chart the app opens on (Florence, as the
# atlas places it, 1240-05-23, 14:30 local mean time): where its wheel puts
# Jupiter, to the six places the wheel gives, as the app computes it on the
# system the suite runs on -- in 20 Aries 52, the degree and minute the
# engine's own tests pin -- and how far the download's may stand from it.
# Each build machine compiles its own Swiss Ephemeris; a value further off
# was computed by a build of it that differs.
WHEEL_COMPONENT = "natal_wheel"
KNOWN_POINT = "Jupiter"
KNOWN_LONGITUDE = 20.876328
KNOWN_TOLERANCE = 1e-05
# Each run, from the request that starts it to its end. The first run loads
# the engine; on a packaged build's first start, from a folder just unpacked,
# that is as slow as the start itself, which REACH_SECONDS bounds.
RUN_SECONDS = 120.0
# Once the server is gone, how long the step waits for the reader of its
# output to reach the end of that pipe; it never waits longer, and the
# reader never keeps the check from ending.
DRAIN_SECONDS = 2.0
# What the step reads of a message, and prints of a run.
MESSAGE_BYTES = 64 * 1024 * 1024
SAID_SHOWN = 8
OPTIONS_SHOWN = 8
OPTION_CHARS = 80


class CheckFailed(Exception):
    pass


# Folders a printed line may not name: each is written as its stand-in.
_WITHHELD = []


def withhold(path, stand_in):
    if path and len(path.strip(os.sep + "/")) > 2:     # never a root
        for form in {path, os.path.realpath(path)}:
            _WITHHELD.append((form, stand_in))
        _WITHHELD.sort(key=lambda pair: -len(pair[0]))


# The launch's key wherever a line could carry it (the window's address,
# the server's environment), and a token of the forge's own shape.
_KEYS = re.compile(r"(?i)(\blaunch=|\bzij_launch_key['\"]?\s*[=:]\s*['\"]?)[^\s&'\"<>]+")
_TOKENS = re.compile(r"\bgh[opsur]_[A-Za-z0-9]{20,}")
_CONTROL = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|[\x00-\x08\x0b-\x1f\x7f]")
# A log line's leading date and time: the line is printed without it.
_STAMP = re.compile(r"^\s*\[?\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:?\d\d)?\]?\s*")


def scrub(text):
    for path, stand_in in _WITHHELD:
        text = text.replace(path, stand_in)
    return _TOKENS.sub("<withheld>", _KEYS.sub(r"\1<withheld>", text))


def say(text):
    print(scrub(text), flush=True)


def _one_line(text, width=LINE_CHARS):
    """`text` as a failure's details print it: scrubbed whole, on one line
    (each control character, and each run of white space, one space), and
    only then cut to `width`, so that a cut never leaves part of what is
    withheld."""
    return " ".join(scrub(_CONTROL.sub(" ", text)).split())[:width]


def _tail(path, count=TAIL_LINES):
    """The last `count` lines of the file at `path` that hold anything, each
    without control characters or a leading date and time, and cut to
    LINE_CHARS; None if it cannot be read or is not a regular file. A link
    at `path` is not followed, and the file is opened without waiting, so
    that a FIFO or a device there is neither read nor waited on."""
    try:
        if os.name == "posix":
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
        elif os.path.islink(path):
            return None
        else:
            flags = os.O_RDONLY | os.O_BINARY
        with open(os.open(path, flags), "rb") as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                return None
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - TAIL_BYTES))
            data = f.read()
    except OSError:
        return None
    lines = [scrub(_STAMP.sub("", _CONTROL.sub("", line))).rstrip()
             for line in data.decode("utf-8", "replace").splitlines()]
    return [line[:LINE_CHARS] for line in lines if line.strip()][-count:]


# --------------------------------------------------------------------------
# Processes: a snapshot of every process, as {pid: Proc}.

class Proc:
    """One process: its id, its parent's id, its executable's path (None
    where it cannot be read) and a start stamp that tells a process from a
    later one given the same id (None where it cannot be read)."""

    __slots__ = ("pid", "ppid", "exe", "stamp")

    def __init__(self, pid, ppid, exe, stamp):
        self.pid, self.ppid, self.exe, self.stamp = pid, ppid, exe, stamp

    def same(self, other):
        return other is not None and other.pid == self.pid and other.stamp == self.stamp


class LinuxProcesses:
    def snapshot(self):
        table = {}
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                with open(f"/proc/{name}/stat", "rb") as f:
                    fields = f.read().rsplit(b")", 1)[1].split()
            except (OSError, IndexError):
                continue
            if fields[0] in (b"Z", b"X"):
                continue                            # a dead process not yet reaped
            try:
                exe = os.readlink(f"/proc/{name}/exe")
            except OSError:
                exe = None
            table[int(name)] = Proc(int(name), int(fields[1]), exe, int(fields[19]))
        return table

    def listening(self, pids):
        """{port: pid} for every TCP socket listening that one of `pids` holds."""
        inodes = {}
        for pid in pids:
            try:
                names = os.listdir(f"/proc/{pid}/fd")
            except OSError:
                continue
            for fd in names:
                try:
                    target = os.readlink(f"/proc/{pid}/fd/{fd}")
                except OSError:
                    continue
                if target.startswith("socket:["):
                    inodes[target[8:-1]] = pid
        ports = {}
        for table in ("/proc/net/tcp", "/proc/net/tcp6"):
            try:
                with open(table) as f:
                    rows = f.read().splitlines()[1:]
            except OSError:
                continue
            for row in rows:
                cols = row.split()
                if len(cols) > 9 and cols[3] == "0A" and cols[9] in inodes:
                    ports[int(cols[1].rsplit(":", 1)[1], 16)] = inodes[cols[9]]
        return ports

    def kill(self, proc):
        _signal_if_same(self, proc, signal.SIGKILL)


def _signal_if_same(processes, proc, number):
    """Signal `proc` only if a fresh look still finds it by its id and start
    stamp; whether the signal was sent."""
    if proc.same(processes.snapshot().get(proc.pid)):
        try:
            os.kill(proc.pid, number)
            return True
        except OSError:
            pass
    return False


class MacProcesses:
    def __init__(self):
        import ctypes

        self._libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
        self._buffer = ctypes.create_string_buffer(4096)

    def _path(self, pid):
        n = self._libc.proc_pidpath(pid, self._buffer, len(self._buffer))
        return self._buffer.raw[:n].decode("utf-8", "surrogateescape") if n > 0 else None

    def snapshot(self):
        out = subprocess.run(["/bin/ps", "-axo", "pid=,ppid=,stat=,lstart="], capture_output=True,
                             text=True, env=dict(os.environ, LC_ALL="C"), check=True).stdout
        table = {}
        for line in out.splitlines():
            parts = line.split(None, 3)
            if len(parts) < 4 or not parts[0].isdigit() or parts[2].startswith("Z"):
                continue
            pid = int(parts[0])
            try:
                stamp = time.mktime(time.strptime(parts[3].strip(), "%a %b %d %H:%M:%S %Y"))
            except ValueError:
                stamp = parts[3].strip()
            table[pid] = Proc(pid, int(parts[1]), self._path(pid), stamp)
        return table

    def listening(self, pids):
        if not pids:
            return {}
        out = subprocess.run(["/usr/sbin/lsof", "-nP", "-a", "-p", ",".join(map(str, sorted(pids))),
                              "-iTCP", "-sTCP:LISTEN", "-Fpn"], capture_output=True, text=True).stdout
        ports, pid = {}, None
        for line in out.splitlines():
            if line.startswith("p") and line[1:].isdigit():
                pid = int(line[1:])
            elif line.startswith("n") and pid is not None:
                tail = line.rsplit(":", 1)[-1]
                if tail.isdigit():
                    ports[int(tail)] = pid
        return ports

    def kill(self, proc):
        _signal_if_same(self, proc, signal.SIGKILL)


class WindowsProcesses:
    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self.ctypes, self.wintypes = ctypes, wintypes
        k32 = self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.iphlpapi = ctypes.WinDLL("iphlpapi")

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                        ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

        self.PROCESSENTRY32W = PROCESSENTRY32W
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                   ctypes.POINTER(wintypes.DWORD)]
        k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(ctypes.c_ulonglong)] * 4
        k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k32.WaitForSingleObject.restype = wintypes.DWORD
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]

    QUERY, SYNCHRONIZE, TERMINATE = 0x1000, 0x00100000, 0x0001

    def _open(self, pid, access):
        return self.k32.OpenProcess(access, False, pid) or None

    def _identity(self, handle):
        ctypes, wintypes = self.ctypes, self.wintypes
        created, rest = ctypes.c_ulonglong(), [ctypes.c_ulonglong() for _ in range(3)]
        stamp = created.value if self.k32.GetProcessTimes(handle, ctypes.byref(created),
                                                          *map(ctypes.byref, rest)) else None
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        exe = buffer.value if self.k32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)) else None
        return exe, stamp

    def snapshot(self):
        ctypes = self.ctypes
        snap = self.k32.CreateToolhelp32Snapshot(0x2, 0)            # TH32CS_SNAPPROCESS
        if not snap or snap == ctypes.c_void_p(-1).value:
            raise OSError(ctypes.get_last_error(), "no process snapshot")
        entries = []
        try:
            entry = self.PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(entry)
            more = self.k32.Process32FirstW(snap, ctypes.byref(entry))
            while more:
                entries.append((entry.th32ProcessID, entry.th32ParentProcessID))
                more = self.k32.Process32NextW(snap, ctypes.byref(entry))
        finally:
            self.k32.CloseHandle(snap)
        table = {}
        for pid, ppid in entries:
            exe = stamp = None
            handle = self._open(pid, self.QUERY) if pid else None
            if handle:
                try:
                    exe, stamp = self._identity(handle)
                finally:
                    self.k32.CloseHandle(handle)
            table[pid] = Proc(pid, ppid, exe, stamp)
        return table

    def alive(self, proc):
        """Whether `proc` has not ended, asked of the process itself: an
        ended process's object can outlive it while a handle to it is open."""
        handle = self._open(proc.pid, self.QUERY | self.SYNCHRONIZE)
        if not handle:
            return False
        try:
            if self._identity(handle)[1] != proc.stamp:
                return False
            return self.k32.WaitForSingleObject(handle, 0) == 0x102   # WAIT_TIMEOUT: still running
        finally:
            self.k32.CloseHandle(handle)

    def listening(self, pids):
        ctypes, wintypes = self.ctypes, self.wintypes

        class ROW(ctypes.Structure):
            _fields_ = [(name, wintypes.DWORD) for name in
                        ("state", "local_addr", "local_port", "remote_addr", "remote_port", "pid")]

        get = self.iphlpapi.GetExtendedTcpTable
        get.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL, wintypes.ULONG,
                        ctypes.c_int, wintypes.ULONG]
        size = wintypes.DWORD(0)
        for _ in range(5):
            buffer = ctypes.create_string_buffer(max(size.value, 4))
            # AF_INET, TCP_TABLE_OWNER_PID_LISTENER
            result = get(buffer, ctypes.byref(size), False, socket.AF_INET, 3, 0)
            if result == 0:
                break
            if result != 122:                                       # ERROR_INSUFFICIENT_BUFFER
                raise OSError(result, "no TCP table")
        else:
            raise OSError(122, "no TCP table")
        count = wintypes.DWORD.from_buffer(buffer).value
        rows = (ROW * count).from_buffer(buffer, ctypes.sizeof(wintypes.DWORD))
        wanted = set(pids)
        return {socket.ntohs(row.local_port & 0xFFFF): row.pid for row in rows if row.pid in wanted}

    def kill(self, proc):
        handle = self._open(proc.pid, self.QUERY | self.TERMINATE)
        if handle:
            try:
                if self._identity(handle)[1] == proc.stamp:
                    self.k32.TerminateProcess(handle, 1)
            finally:
                self.k32.CloseHandle(handle)


# --------------------------------------------------------------------------
# Windows: the window a launch shows, and the way a reader closes it.

class WindowsDesktop:
    closing = "a close message (WM_CLOSE) to the window"

    def __init__(self):
        import ctypes
        from ctypes import wintypes

        self.ctypes, self.wintypes = ctypes, wintypes
        u32 = self.u32 = ctypes.WinDLL("user32", use_last_error=True)
        self.WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        u32.EnumWindows.argtypes = [self.WNDENUMPROC, wintypes.LPARAM]
        u32.GetWindowThreadProcessId.restype = wintypes.DWORD
        u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u32.IsWindowVisible.argtypes = [wintypes.HWND]
        u32.GetWindow.restype = wintypes.HWND
        u32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

    def find(self, launcher):
        """The launcher's own visible top-level window, as (handle, its
        description), or None."""
        ctypes, wintypes, u32 = self.ctypes, self.wintypes, self.u32
        found = []

        def each(hwnd, _):
            owner = wintypes.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value == launcher.pid and u32.IsWindowVisible(hwnd) and not u32.GetWindow(hwnd, 4):
                rect = wintypes.RECT()
                if u32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    width, height = rect.right - rect.left, rect.bottom - rect.top
                    if width > 0 and height > 0:
                        found.append((width * height, hwnd, f"{width}x{height}"))
            return True

        u32.EnumWindows(self.WNDENUMPROC(each), 0)
        if not found:
            return None
        _, hwnd, size = max(found)
        return hwnd, f"a visible top-level window of the launcher, {size}"

    def close(self, launcher, window):
        if not self.u32.PostMessageW(window[0], 0x0010, 0, 0):          # WM_CLOSE
            raise CheckFailed(f"the close message could not be sent (error {self.ctypes.get_last_error()})")


# --------------------------------------------------------------------------
# macOS: the window a launch shows, and Quit.

class MacDesktop:
    closing = "Quit (the quit event, sent to the launcher's application)"

    def __init__(self):
        import ctypes

        c = self.ctypes = ctypes
        self.cf = c.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self.cg = c.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        self.cg.CGWindowListCopyWindowInfo.restype = c.c_void_p
        self.cg.CGWindowListCopyWindowInfo.argtypes = [c.c_uint32, c.c_uint32]
        self.cf.CFArrayGetCount.restype = c.c_long
        self.cf.CFArrayGetCount.argtypes = [c.c_void_p]
        self.cf.CFArrayGetValueAtIndex.restype = c.c_void_p
        self.cf.CFArrayGetValueAtIndex.argtypes = [c.c_void_p, c.c_long]
        self.cf.CFDictionaryGetValue.restype = c.c_void_p
        self.cf.CFDictionaryGetValue.argtypes = [c.c_void_p, c.c_void_p]
        self.cf.CFNumberGetValue.restype = c.c_bool
        self.cf.CFNumberGetValue.argtypes = [c.c_void_p, c.c_int, c.c_void_p]
        self.cf.CFRelease.argtypes = [c.c_void_p]
        self.owner_key = c.c_void_p.in_dll(self.cg, "kCGWindowOwnerPID").value
        self.layer_key = c.c_void_p.in_dll(self.cg, "kCGWindowLayer").value

        self.objc = c.CDLL("/usr/lib/libobjc.A.dylib")
        c.CDLL("/System/Library/Frameworks/AppKit.framework/AppKit")
        self.objc.objc_getClass.restype = c.c_void_p
        self.objc.objc_getClass.argtypes = [c.c_char_p]
        self.objc.sel_registerName.restype = c.c_void_p
        self.objc.sel_registerName.argtypes = [c.c_char_p]
        send = c.cast(self.objc.objc_msgSend, c.c_void_p).value
        self.send_int = c.CFUNCTYPE(c.c_void_p, c.c_void_p, c.c_void_p, c.c_int32)(send)
        self.send_bool = c.CFUNCTYPE(c.c_byte, c.c_void_p, c.c_void_p)(send)

    def _number(self, dictionary, key):
        value = self.cf.CFDictionaryGetValue(dictionary, key)
        out = self.ctypes.c_int64()
        if value and self.cf.CFNumberGetValue(value, 4, self.ctypes.byref(out)):   # kCFNumberSInt64Type
            return out.value
        return None

    def find(self, launcher):
        # kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
        windows = self.cg.CGWindowListCopyWindowInfo(1 | 16, 0)
        if not windows:
            return None
        try:
            count = sum(1 for i in range(self.cf.CFArrayGetCount(windows))
                        for info in [self.cf.CFArrayGetValueAtIndex(windows, i)]
                        if self._number(info, self.owner_key) == launcher.pid
                        and self._number(info, self.layer_key) == 0)
        finally:
            self.cf.CFRelease(windows)
        return (count, f"{count} on-screen window(s) of the launcher") if count else None

    def close(self, launcher, window):
        objc = self.objc
        app = self.send_int(objc.objc_getClass(b"NSRunningApplication"),
                            objc.sel_registerName(b"runningApplicationWithProcessIdentifier:"), launcher.pid)
        if not app:
            raise CheckFailed("the launcher is not a running application to which Quit can be sent")
        if not self.send_bool(app, objc.sel_registerName(b"terminate")):
            raise CheckFailed("Quit could not be sent to the launcher")


# --------------------------------------------------------------------------
# Linux, for the suite only: a window stands in as a file.

class StandInDesktop:
    """The launched command shows its window by making `<pid>.open` in the
    folder named by STAND_IN_WINDOWS in its environment, and closes it when
    `<pid>.close` appears there."""

    closing = "the stand-in window's close"

    def __init__(self, folder):
        self.folder = os.path.abspath(folder)

    def find(self, launcher):
        if os.path.exists(os.path.join(self.folder, f"{launcher.pid}.open")):
            return launcher.pid, "the stand-in window of the launcher"
        return None

    def close(self, launcher, window):
        with open(os.path.join(self.folder, f"{launcher.pid}.close"), "w"):
            pass


# --------------------------------------------------------------------------
# One launch.

def _answers_health(port):
    """Whether the server on `port` answers as Streamlit's health check
    answers, reached straight, never through a proxy."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/_stcore/health", timeout=2) as answer:
            return answer.status == 200 and answer.read(16).strip() == b"ok"
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _opening_status(port, host, origin=None):
    """The status the server on `port` answers a WebSocket opening of the
    session's route with, sent under the Host header `host` (and the Origin
    header `origin`, when given) and reached straight; None where it
    answers none."""
    request = (f"GET /_stcore/stream HTTP/1.1\r\nHost: {host}\r\n" + (f"Origin: {origin}\r\n" if origin else "")
               + "Upgrade: websocket\r\nConnection: Upgrade\r\n"
               "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n"
               "Sec-WebSocket-Protocol: streamlit\r\n\r\n")
    answer = b""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=PROBE_SECONDS) as sock:
            sock.sendall(request.encode("ascii"))
            while b"\n" not in answer and len(answer) < 256:
                received = sock.recv(256)
                if not received:
                    break
                answer += received
    except OSError:
        return None
    status = answer.split(b"\n", 1)[0].split()
    if len(status) >= 2 and status[0].startswith(b"HTTP/") and status[1].isdigit():
        return int(status[1])
    return None


def _sessions_seen(port):
    """What the server on `port` shows of its sessions by its own metrics,
    reached straight: the bytes of media files it holds, the names of the
    engine's calculations whose results it holds, and its sessions, as a
    clause."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}{METRICS_PATH}", timeout=PROBE_SECONDS) as answer:
            text = answer.read(1 << 20).decode("utf-8", "replace") if answer.status == 200 else ""
    except (urllib.error.URLError, OSError, ValueError):
        return 0, [], "its metrics did not answer"
    media = sum(int(value) for value in _MEDIA.findall(text))
    found = sorted({match[1] for match in _ENGINE_RESULT.finditer(text)})
    counts = dict(re.findall(r'(?m)^(active_sessions|session_events_total)(?:\{type="connect"\})? (\d+)$', text))
    return media, found, (f"{counts.get('active_sessions', '?')} session(s) open, "
                          f"{counts.get('session_events_total', '?')} opened in all")


def _accepts(port):
    """Whether anything still accepts a connection on the port."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def _inside(path, folder):
    if not path or not folder:
        return False
    path, folder = (os.path.normcase(os.path.realpath(p)) for p in (path, folder))
    return path.startswith(folder.rstrip(os.sep) + os.sep)


class Sighting:
    """One process of a launch as this check saw it: its latest sight, its
    parent when first seen (before any adoption by another), and when it was
    first seen and first missed, in seconds after the launch's start."""

    __slots__ = ("proc", "parent", "first", "ended")

    def __init__(self, proc, first):
        self.proc, self.parent, self.first, self.ended = proc, proc.ppid, first, None


class Launch:
    """The processes of one launch, as it runs: the launcher, every process
    descended from one of them while it was seen, and every process whose
    executable lies inside `folder`. All of them count against the stop.

    Apart from that count, `tree` holds only the launcher this check started
    itself and the processes found by walking parent links down from it.
    Those alone may ever be ended by the check. `sightings` only records:
    nothing is ever ended by it."""

    def __init__(self, processes, folder, number):
        self.processes, self.folder, self.number = processes, folder, number
        self.launcher, self.popen, self.port, self.server = None, None, None, None
        self.seen = {}
        self.tree = {}
        self.sightings = {}
        self.started, self.wall_started = time.monotonic(), time.time()
        self.made = None
        self.streams = []
        # What heads the launch (the process this check started, or the
        # bundle's first), as printed; and what a failure says of it besides.
        self.role = "the launcher"
        self.notes = []
        # The thread that reads the server's output pipe (the third launch).
        self.drain = None

    def elapsed(self):
        return time.monotonic() - self.started

    def note(self, procs):
        """Record `procs` as seen running now."""
        now = self.elapsed()
        for proc in procs:
            sighting = self.sightings.get((proc.pid, proc.stamp))
            if sighting is None:
                self.sightings[(proc.pid, proc.stamp)] = Sighting(proc, now)
            else:
                sighting.proc, sighting.ended = proc, None

    def adopt(self, launcher):
        """`launcher` is this launch's; it heads the tree only if this check
        started it (Windows, and a command on Linux)."""
        self.launcher = launcher
        self.seen[launcher.pid] = launcher
        self.note([launcher])
        if self.popen is not None and launcher.pid == self.popen.pid:
            self.tree[launcher.pid] = launcher

    def _alive(self, proc, table):
        if hasattr(self.processes, "alive"):
            return self.processes.alive(proc)
        return proc.same(table.get(proc.pid))

    def live(self):
        """The processes of this launch still running, the record of those
        seen brought up to date first."""
        if self.popen is not None:
            self.popen.poll()                              # a child of ours that ended is reaped
        table = self.processes.snapshot()
        live = {pid: proc for pid, proc in self.seen.items() if self._alive(proc, table)}
        for proc in table.values():
            if _inside(proc.exe, self.folder) and proc.pid not in live:
                live[proc.pid] = proc
        _walk_down(live, table)
        if self.tree:
            tree = {pid: proc for pid, proc in self.tree.items() if self._alive(proc, table)}
            for pid, proc in _walk_down(tree, table).items():
                self.tree.setdefault(pid, proc)
        if hasattr(self.processes, "alive"):
            # Windows: an ended process can stay listed while a handle to it
            # is open (this check holds its launcher's); each is asked.
            live = {pid: proc for pid, proc in live.items() if self.processes.alive(proc)}
        for pid, proc in live.items():
            self.seen[pid] = proc                          # the latest sight: the same process, its path now read
        self.note(live.values())
        now = self.elapsed()
        for key, sighting in self.sightings.items():
            if sighting.ended is None and not sighting.proc.same(live.get(key[0])):
                sighting.ended = now
        return live

    def sighting(self, proc):
        return self.sightings.get((proc.pid, proc.stamp)) if proc is not None else None

    def started_by_launcher(self, proc):
        """Whether `proc` was first seen below the launcher, by the parents
        recorded at first sight."""
        if self.launcher is None:
            return False
        parents = {key[0]: s.parent for key, s in self.sightings.items()}
        pid, steps = proc.pid, 0
        while pid in parents and steps < len(parents):
            pid, steps = parents[pid], steps + 1
            if pid == self.launcher.pid:
                return True
        return False

    def history(self, limit=20):
        """Every process of this launch seen, each with its parent at first
        sight and when it was seen, as printed."""
        own = {key[0] for key in self.sightings}
        rows = []
        for sighting in sorted(self.sightings.values(), key=lambda s: (s.first, s.proc.pid))[:limit]:
            if self.launcher is not None and sighting.proc.same(self.launcher):
                role = f"{self.role}; "
            else:
                role = ""
            if self.launcher is not None and sighting.parent == self.launcher.pid:
                parent = f"parent {sighting.parent}, {self.role}"
            elif sighting.parent in own:
                parent = f"parent {sighting.parent}, of this launch"
            else:
                parent = f"parent {sighting.parent}, outside this launch"
            until = f"gone by {sighting.ended:.1f} s" if sighting.ended is not None else "running"
            rows.append(f"{self.name(sighting.proc)} [{role}{parent}; seen from {sighting.first:.1f} s, {until}]")
        more = len(self.sightings) - limit
        return "; ".join(rows) + (f"; and {more} more" if more > 0 else "") if rows else "none"

    def where(self, exe):
        """An executable as printed: its path within the download, or its
        file name alone where it lies outside."""
        if _inside(exe, self.folder):
            where = os.path.relpath(os.path.realpath(exe), os.path.realpath(self.folder))
        else:
            where = os.path.basename(exe) if exe else "?"
        return where.replace(os.sep, "/")

    def name(self, proc):
        return f"{self.where(proc.exe)} ({proc.pid})"

    def names(self, procs):
        return ", ".join(self.name(p) for p in sorted(procs, key=lambda p: p.pid)) or "none"

    def end_everything(self):
        """After a failure: end what still runs of the tree -- the launcher
        this check started and the processes found below it by their parent
        links -- each by its own id and start stamp, never this check or a
        process it runs under. Nothing else is ended, whatever the launch is
        counted to hold: not a process found by its executable's path, nor
        any process on macOS, where Launch Services starts the launcher (the
        runner is discarded with the job)."""
        if self.popen is None:
            return
        if self.launcher is not None:
            self.live()                                    # the tree walked once more while it hangs together
        if self.popen.poll() is None:
            self.popen.kill()
        table = self.processes.snapshot()
        spared, pid = set(), os.getpid()
        while pid not in spared:
            spared.add(pid)
            if pid not in table:
                break
            pid = table[pid].ppid
        for _ in range(3):
            self.popen.poll()
            if self.launcher is not None:
                self.live()
            table = self.processes.snapshot()
            left = [proc for proc in self.tree.values() if proc.pid not in spared and self._alive(proc, table)]
            if not left:
                return
            for proc in left:
                self.processes.kill(proc)
            time.sleep(1)


def _walk_down(found, table):
    """`found` grown, in place, by every process of `table` whose parent is
    in it: parent links walked down. A process older than its parent is not
    taken, its parent's id being a later process's; nor is one where either
    start stamp cannot be read, its age untold."""
    grew = True
    while grew:
        grew = False
        for proc in table.values():
            parent = found.get(proc.ppid)
            if proc.pid in found or parent is None or proc.pid == parent.pid:
                continue
            if parent.stamp is None or proc.stamp is None:
                continue
            if type(parent.stamp) is type(proc.stamp) and proc.stamp < parent.stamp:
                continue
            found[proc.pid] = proc
            grew = True
    return found


def _exit_code(popen):
    """A launcher of ours that has ended, reaped: a process whose threads are
    still being torn down is already gone but cannot yet be reaped."""
    try:
        return popen.wait(POLL_SECONDS * 4)
    except subprocess.TimeoutExpired:
        return "not yet reaped"


def _run(argv, what):
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CheckFailed(f"{what} failed: {error}")
    if done.returncode:
        said = " ".join((done.stderr or done.stdout).split())
        raise CheckFailed(f"{what} failed (exit {done.returncode}): {said}")


# --------------------------------------------------------------------------
# The session a window opens on its server: a WebSocket on the session's
# route carrying Streamlit's protocol buffers, written and read here by
# their wire format. The field numbers are Streamlit's own (BackMsg,
# ClientState, WidgetStates, WidgetState; ForwardMsg, Delta, Element,
# TextInput, Selectbox, Alert, Exception); the suite compares what is
# written and read here with Streamlit's own classes.

def _varint(number):
    out = bytearray()
    while True:
        low, number = number & 0x7F, number >> 7
        out.append(low | 0x80 if number else low)
        if not number:
            return bytes(out)


def _field(number, payload):
    """A length-delimited field: a string or a message."""
    return _varint(number << 3 | 2) + _varint(len(payload)) + payload


def rerun_message(query_string, widgets=()):
    """A BackMsg asking for a run, as the window sends one: its address's
    query string and the widget values it holds, each (widget id, text)."""
    states = b"".join(_field(1, _field(1, wid.encode("utf-8")) + _field(6, text.encode("utf-8")))
                      for wid, text in widgets)
    client = (_field(1, query_string.encode("utf-8")) if query_string else b"") + _field(2, states)
    return _field(11, client)                                    # BackMsg.rerun_script


def _read_varint(data, i):
    """The varint at `i` in `data`, and where the next field begins."""
    number, shift = 0, 0
    while True:
        if i >= len(data) or shift > 63:
            raise ValueError("a varint runs past its message")
        byte = data[i]
        i += 1
        number |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return number, i


def _fields(data):
    """A message's fields as (number, value): an integer for a varint, the
    bytes for a length-delimited field; fixed-width fields are skipped."""
    out, i = [], 0
    while i < len(data):
        key, i = _read_varint(data, i)
        wire = key & 7
        if wire == 0:
            value, i = _read_varint(data, i)
        elif wire == 2:
            size, i = _read_varint(data, i)
            if i + size > len(data):
                raise ValueError("a field runs past its message")
            value, i = data[i:i + size], i + size
        elif wire in (1, 5):
            i += 8 if wire == 1 else 4
            continue
        else:
            raise ValueError(f"wire type {wire}")
        out.append((key >> 3, value))
    return out


def _text(value):
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else ""


def _element(data):
    """What this check reads of an Element: ("text_input", id, label),
    ("selectbox", id, label, options), ("alert", format, body),
    ("exception", type, message) or ("component", name, its data as JSON
    text); None for any other."""
    for number, value in _fields(data):
        if number == 24 and isinstance(value, bytes):            # text_input
            got = {n: v for n, v in _fields(value) if n in (1, 2)}
            return ("text_input", _text(got.get(1)), _text(got.get(2)))
        if number == 25 and isinstance(value, bytes):            # selectbox
            got = _fields(value)
            first = {n: v for n, v in got if n in (1, 2)}
            return ("selectbox", _text(first.get(1)), _text(first.get(2)),
                    [_text(v) for n, v in got if n == 4])
        if number == 30 and isinstance(value, bytes):            # alert
            got = {n: v for n, v in _fields(value) if n in (1, 2)}
            return ("alert", got.get(2, 0) if isinstance(got.get(2, 0), int) else 0, _text(got.get(1)))
        if number == 8 and isinstance(value, bytes):             # exception
            got = {n: v for n, v in _fields(value) if n in (1, 2)}
            return ("exception", _text(got.get(1)), _text(got.get(2)))
        if number == 59 and isinstance(value, bytes):            # bidi_component
            got = {n: v for n, v in _fields(value) if n in (2, 10)}
            return ("component", _text(got.get(2)), _text(got.get(10)))
    return None


def message_kind(data):
    """What a failure says of one ForwardMsg the server sent after a run's
    request: (kind, description), the kind "start" for the session's start
    (a run begins), "end" for a run's end, "element" for a new element, and
    "other" for any other message."""
    for number, value in _fields(data):
        if number == 4:                                          # new_session
            return "start", "the session's start"
        if number == 6 and isinstance(value, int):               # script_finished
            return "end", f"a run's end (status {value})"
        if number == 5 and isinstance(value, bytes):             # delta
            for inner, element in _fields(value):
                if inner == 3 and isinstance(element, bytes):    # Delta.new_element
                    found = _element(element)
                    if found is None:
                        numbers = sorted({n for n, _ in _fields(element)})
                        return "element", f"an element of another kind (field {', '.join(map(str, numbers))})"
                    if found[0] == "text_input":
                        return "element", f"a text box {found[2]!r}"
                    if found[0] == "selectbox":
                        return "element", f"a choice {found[2]!r} of {len(found[3])} option(s)"
                    if found[0] == "alert":
                        return "element", f"{_ALERT_KINDS.get(found[1], 'an')} alert"
                    if found[0] == "component":
                        return "element", f"a component {found[1]!r}"
                    return "element", f"an exception {found[1]}"
            numbers = sorted({n for n, _ in _fields(value)})
            return "other", f"a delta with no new element (field {', '.join(map(str, numbers)) or 'none'})"
    numbers = sorted({n for n, _ in _fields(data)} - {1, 2})      # beside its hash and metadata
    return "other", f"another message (field {', '.join(map(str, numbers)) or 'none'})"


def read_forward(data):
    """What this check reads of a ForwardMsg: ("new_session",) at a run's
    start, ("finished", status) at its end, ("element", element) for a new
    element, or None."""
    for number, value in _fields(data):
        if number == 4:                                          # new_session
            return ("new_session",)
        if number == 6 and isinstance(value, int):               # script_finished
            return ("finished", value)
        if number == 5 and isinstance(value, bytes):             # delta
            for inner, element in _fields(value):
                if inner == 3 and isinstance(element, bytes):    # Delta.new_element
                    found = _element(element)
                    return ("element", found) if found else None
    return None


# ForwardMsg.ScriptFinishedStatus: a run ended, or ended at a compile error;
# a run cut short for a rerun is followed by that rerun.
FINISHED = 0
FINISHED_WITH_COMPILE_ERROR = 1
# Alert.Format
_ALERT_KINDS = {1: "error", 2: "warning", 3: "info", 4: "success"}


class Session:
    """One session on the server at 127.0.0.1:`port`, opened as the window
    opens it: under its own Host and Origin, with the cookie and token its
    server's XSRF protection gives at its health check."""

    def __init__(self, port):
        self.port, self.sock, self.buffer = port, None, b""
        self.origin = f"http://127.0.0.1:{port}"
        # What the server sent after the last run's request (a Heard).
        self.heard = None
        # Bytes read from the socket, and taken off the buffer, in all; and
        # taken by the time the last whole message was read.
        self.received = self.taken = self.whole = 0

    def open(self):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request = urllib.request.Request(f"{self.origin}/_stcore/health", headers={"Origin": self.origin})
        with opener.open(request, timeout=PROBE_SECONDS) as answer:
            cookies = answer.headers.get_all("Set-Cookie") or []
        xsrf = next((c.split(";", 1)[0].split("=", 1)[1] for c in cookies
                     if c.split("=", 1)[0].strip() == "_streamlit_xsrf"), None)
        nonce = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (f"GET /_stcore/stream HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\nOrigin: {self.origin}\r\n"
                   f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {nonce}\r\n"
                   f"Sec-WebSocket-Version: 13\r\n"
                   f"Sec-WebSocket-Protocol: streamlit{', ' + xsrf if xsrf else ''}\r\n"
                   + (f"Cookie: _streamlit_xsrf={xsrf}\r\n" if xsrf else "") + "\r\n")
        self.sock = socket.create_connection(("127.0.0.1", self.port), timeout=PROBE_SECONDS)
        self.sock.sendall(request.encode("ascii"))
        while b"\r\n\r\n" not in self.buffer:
            if len(self.buffer) > 16384:
                raise CheckFailed("the session's opening was answered with more than headers")
            self._fill()
        head, self.buffer = self.buffer.split(b"\r\n\r\n", 1)
        lines = head.decode("latin-1").split("\r\n")
        status = lines[0].split()
        if len(status) < 2 or status[1] != "101":
            raise CheckFailed(f"the session's opening was answered {lines[0][:80]!r}, not opened with 101")
        accept = base64.b64encode(hashlib.sha1((nonce + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                                               .encode("ascii")).digest()).decode("ascii")
        headers = {name.strip().lower(): value.strip() for name, _, value in
                   (line.partition(":") for line in lines[1:])}
        if headers.get("sec-websocket-accept") != accept:
            raise CheckFailed("the session's opening was answered without this opening's own accept key")
        return bool(xsrf)

    def _fill(self, deadline=None):
        if deadline is not None:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError
            self.sock.settimeout(left)
        received = self.sock.recv(65536)
        if not received:
            raise CheckFailed("the server closed the session")
        self.received += len(received)
        self.buffer += received

    def _take(self, count, deadline):
        while len(self.buffer) < count:
            self._fill(deadline)
        taken, self.buffer = self.buffer[:count], self.buffer[count:]
        self.taken += count
        return taken

    def _frame(self, opcode, payload):
        mask = os.urandom(4)
        size = len(payload)
        if size < 126:
            length = bytes([0x80 | size])
        elif size < 65536:
            length = bytes([0x80 | 126]) + size.to_bytes(2, "big")
        else:
            length = bytes([0x80 | 127]) + size.to_bytes(8, "big")
        self.sock.sendall(bytes([0x80 | opcode]) + length + mask
                          + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def send(self, message):
        self._frame(2, message)

    def receive(self, deadline):
        """The next whole message the server sends, by `deadline`
        (TimeoutError after it)."""
        message = b""
        while True:
            first, second = self._take(2, deadline)
            opcode, size = first & 0x0F, second & 0x7F
            if size == 126:
                size = int.from_bytes(self._take(2, deadline), "big")
            elif size == 127:
                size = int.from_bytes(self._take(8, deadline), "big")
            if size + len(message) > MESSAGE_BYTES:
                raise CheckFailed(f"the server sent a message of more than {MESSAGE_BYTES} bytes")
            mask = self._take(4, deadline) if second & 0x80 else None
            payload = self._take(size, deadline)
            if mask:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            if opcode == 8:
                code = int.from_bytes(payload[:2], "big") if len(payload) >= 2 else None
                raise CheckFailed(f"the server closed the session (code {code})")
            if opcode == 9:
                self._frame(10, payload)
                continue
            if opcode in (0, 1, 2):
                message += payload
                if first & 0x80:
                    self.whole = self.taken
                    return message

    def run(self, message, seconds):
        """Send `message` (a rerun) and read the run it starts to its end:
        (its finishing status, its elements in order, its time in seconds).
        RunUnfinished if it has not ended within `seconds`, with what the
        server sent after the request."""
        began = time.monotonic()
        deadline = began + seconds
        heard = self.heard = Heard(self, began, seconds)
        self.send(message)
        elements = []
        try:
            while True:
                data = self.receive(deadline)
                heard.add(data)
                event = read_forward(data)
                if event is None:
                    continue
                if event[0] == "new_session":
                    elements = []
                elif event[0] == "element":
                    elements.append(event[1])
                elif event[1] in (FINISHED, FINISHED_WITH_COMPILE_ERROR):
                    return event[1], elements, time.monotonic() - began
        except TimeoutError:
            heard.bound_passed()
            raise RunUnfinished(elements, heard)

    def close(self):
        if self.sock is not None:
            try:
                self._frame(8, (1000).to_bytes(2, "big"))
            except OSError:
                pass
            self.sock.close()
            self.sock = None


class RunUnfinished(Exception):
    """A run not ended by its bound; its arguments, the elements it had
    sent and what the server sent after its request (a Heard)."""


class Heard:
    """What the server sent on a session after a run's request, for a run
    that does not end: its whole messages counted by kind (the session's
    start, elements, a run's end, any other), their bytes, when the session's
    start and the last message came, and the last of them; told from a run
    that never started (no message, or none the session's start) and one
    that started and stalled."""

    KINDS = ("start", "element", "end", "other")
    LAST_SHOWN = 6

    def __init__(self, session, began, seconds):
        self.session, self.began, self.seconds = session, began, seconds
        self.counts = dict.fromkeys(self.KINDS, 0)
        self.bytes, self.started, self.last = 0, None, None
        self.recent, self.elements = [], []
        self.received, self.partial = session.received, 0

    def add(self, data):
        kind, description = message_kind(data)
        now = time.monotonic() - self.began
        self.counts[kind] += 1
        self.bytes += len(data)
        self.last = now
        if kind == "start" and self.started is None:
            self.started = now
        if kind == "element":
            self.elements = (self.elements + [description])[-self.LAST_SHOWN:]
        self.recent = (self.recent + [description])[-self.LAST_SHOWN:]

    def bound_passed(self):
        session = self.session
        self.received = session.received - self.received
        self.partial = session.taken - session.whole + len(session.buffer)

    def messages(self):
        return sum(self.counts.values())

    def verdict(self):
        """How far the run got, in a clause."""
        if not self.messages():
            return "it never started: no message came after the request"
        if self.started is None:
            return (f"it never started: {self.messages()} message(s) came after the request, none the "
                    f"session's start")
        return (f"it started (the session's start {self.started:.1f} s after the request) and stalled after "
                f"{self.counts['element']} element(s)")

    def notes(self):
        """What a failure says of it, as lines."""
        counts = ", ".join(f"{self.counts[kind]} {name}" for kind, name in
                           zip(self.KINDS, ("session's start", "element(s)", "run's end", "other")))
        since = (f"the last {self.seconds - self.last:.1f} s before the bound" if self.last is not None
                 else f"none in the {self.seconds:g} s after the request")
        lines = [f"the run: {self.verdict()}",
                 f"the server's messages after the request: {self.messages()} ({counts}), {self.bytes} byte(s); "
                 f"{since}; {self.received} byte(s) read from the session in all"
                 + (f", {self.partial} of them a message not yet whole" if self.partial else "")]
        if self.elements:
            lines.append(f"the last element(s): {'; '.join(self.elements)}")
        if self.recent:
            lines.append(f"the last message(s), in order: {'; '.join(self.recent)}")
        return [_one_line(line) for line in lines]


def _run_notes(elements):
    """What a failure says of a run: its sentences and its choice of place."""
    said = sentences(elements)
    return ([f"what the run said ({len(said)}):"] + [f"  | {line}" for line in said] if said
            else ["the run said nothing in an alert or an exception"]) + [
        f"the run's choice of place: {options_text(options_offered(elements))}"]


def sentences(elements):
    """The run's alerts and exceptions as printed: each on one line,
    scrubbed whole, then cut."""
    said = []
    for element in elements:
        if element[0] == "alert":
            said.append(f"{_ALERT_KINDS.get(element[1], 'alert')}: {element[2]}")
        elif element[0] == "exception":
            said.append(f"exception {element[1]}: {element[2]}")
    return [_one_line(line) for line in said[:SAID_SHOWN]] + (
        [f"and {len(said) - SAID_SHOWN} more"] if len(said) > SAID_SHOWN else [])


def options_offered(elements):
    """The options of the run's last "Select specific location:", or None
    where the run showed none."""
    found = [element[3] for element in elements if element[0] == "selectbox" and element[2] == PLACE_CHOICE_LABEL]
    return found[-1] if found else None


def options_text(options):
    if options is None:
        return "no choice of place"
    shown = [repr(scrub(option)[:OPTION_CHARS]) for option in options[:OPTIONS_SHOWN]]
    more = f" and {len(options) - OPTIONS_SHOWN} more" if len(options) > OPTIONS_SHOWN else ""
    return f"{len(options)} option(s): " + ", ".join(shown) + more


def _free_port():
    """An unused port of 127.0.0.1, asked of the system as the launcher asks."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _server_environment(environment, key):
    """The server's environment as the launcher gives its child one: no
    STREAMLIT_* variable, and the launch's key."""
    out = {name: value for name, value in environment.items() if not name.upper().startswith("STREAMLIT_")}
    out[LAUNCH_KEY_VARIABLE] = key
    return out


def _drain(pipe, path):
    """Copy what the server writes on its output and errors into the file
    at `path` as it comes, as the launcher's thread reads its child's pipe,
    so that the server never waits on a pipe left full. Ends when the pipe
    does: once no process holds its writing end. Nothing else reads the
    pipe or closes it, and the thread is a daemon: it never keeps the check
    from ending."""
    try:
        with pipe, open(path, "ab") as out:
            while True:
                data = os.read(pipe.fileno(), 65536)
                if not data:
                    return
                out.write(data)
                out.flush()
    except (OSError, ValueError):
        pass


class Check:
    def __init__(self, args):
        self.args = args
        self.work = None
        self.platform = sys.platform
        if (args.stand_in_windows or args.folder) and not args.command:
            raise CheckFailed("a stand-in window is for a command on Linux only")
        if args.command:
            if self.platform in ZIPS:
                raise CheckFailed("a command stands in for the download only on Linux")
            if not args.stand_in_windows:
                raise CheckFailed("a command's window must be a stand-in (--stand-in-windows)")
            self.processes = LinuxProcesses()
            self.desktop = StandInDesktop(args.stand_in_windows)
        elif self.platform == "win32":
            self.processes, self.desktop = WindowsProcesses(), WindowsDesktop()
        elif self.platform == "darwin":
            self.processes, self.desktop = MacProcesses(), MacDesktop()
        else:
            raise CheckFailed("this system's windows cannot be seen, so the stop cannot be checked here: "
                              "a check that skips is not a check")

    # -- starting --------------------------------------------------------

    def _fresh(self, name):
        path = os.path.join(self.work, name)
        os.makedirs(path)
        return path

    def _unpack(self, number):
        folder = self._fresh(f"download-{number}")
        if self.platform == "win32":
            with zipfile.ZipFile(self.args.zip) as archive:
                archive.extractall(folder)
        else:
            # ditto, as the Finder unpacks: the bundle's links and modes kept.
            _run(["/usr/bin/ditto", "-x", "-k", self.args.zip, folder], "unpacking the zip")
        return folder

    def start(self, number):
        """Start launch `number` with a fresh data folder; returns the
        Launch, its launcher found, and the data folder the app must make."""
        data = self._fresh(f"data-{number}")
        withhold(data, "<fresh>")
        # Where the launcher's standard output and error go, when this check
        # can give them a place (macOS, a command on Linux): in the fresh folder.
        streams = [("standard output", os.path.join(data, "launcher-stdout.txt")),
                   ("standard error", os.path.join(data, "launcher-stderr.txt"))]
        if self.args.command:
            folder = os.path.abspath(self.args.folder) if self.args.folder else None
            launch = Launch(self.processes, folder, number)
            self.current = launch
            launch.made = made = os.path.join(data, APP_DIR_NAME)
            launch.streams = streams
            environment = dict(os.environ, HOME=data, XDG_DATA_HOME=data,
                               STAND_IN_WINDOWS=self.desktop.folder)
            with open(streams[0][1], "wb") as out, open(streams[1][1], "wb") as err:
                launch.popen = subprocess.Popen(self.args.command, env=environment, stdin=subprocess.DEVNULL,
                                                stdout=out, stderr=err)
            how = "the command run with a fresh home and data folder"
        elif self.platform == "win32":
            folder = self._unpack(number)
            launch = Launch(self.processes, folder, number)
            self.current = launch
            roaming, local = os.path.join(data, "Roaming"), os.path.join(data, "Local")
            os.makedirs(roaming)
            os.makedirs(local)
            launch.made = made = os.path.join(roaming, APP_DIR_NAME)
            environment = dict(os.environ, APPDATA=roaming, LOCALAPPDATA=local)
            # As Explorer starts it: the executable at the top of the unpacked
            # folder, that folder its working folder, no console and no
            # standard streams.
            launch.popen = subprocess.Popen([os.path.join(folder, "Zij.exe")], cwd=folder, env=environment,
                                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL)
            how = "Zij.exe started from the unpacked zip, APPDATA and LOCALAPPDATA in a fresh folder"
        else:
            folder = self._unpack(number)
            launch = Launch(self.processes, folder, number)
            self.current = launch
            bundle = os.path.join(folder, "Zij.app")
            launch.made = made = os.path.join(data, "Library", "Application Support", APP_DIR_NAME)
            launch.streams = streams
            for _, path in streams:
                open(path, "wb").close()
            # As the Finder opens it: by Launch Services, a new instance of the
            # bundle, with HOME (and so the data folder under it) fresh. Its
            # standard output and error, which the Finder sends nowhere, go to
            # files in the fresh folder, so that a failure can say what the
            # app said.
            _run(["/usr/bin/open", "-n", "--stdout", streams[0][1], "--stderr", streams[1][1],
                  "--env", f"HOME={data}", bundle], "opening the bundle")
            how = ("Zij.app opened as a bundle (open -n) from the unpacked zip, HOME in a fresh folder, its "
                   "standard output and error kept there")
        launch.started = time.monotonic()
        self._find_launcher(launch)
        say(f"launch {number}: started: {how}; launcher {launch.name(launch.launcher)}")
        return launch, made

    def _find_launcher(self, launch):
        deadline = time.monotonic() + self.args.reach_seconds
        while True:
            table = self.processes.snapshot()
            if launch.popen is not None:
                proc = table.get(launch.popen.pid)
                if proc is not None:
                    launch.adopt(proc)
                    return proc
                if launch.popen.poll() is not None:
                    raise CheckFailed(f"launch {launch.number}: the launcher ended at once "
                                      f"(exit {launch.popen.returncode})")
            else:
                # Opened by Launch Services: the launcher is the bundle's
                # process whose parent is not itself one of the bundle's.
                ours = {p.pid: p for p in table.values() if _inside(p.exe, launch.folder)}
                launch.note(ours.values())
                roots = [p for p in ours.values() if p.ppid not in ours]
                if len(roots) > 1:
                    raise CheckFailed(f"launch {launch.number}: more than one launcher started: "
                                      f"{launch.names(roots)}")
                if roots:
                    launch.adopt(roots[0])
                    return roots[0]
            if time.monotonic() > deadline:
                raise CheckFailed(f"launch {launch.number}: no launcher process appeared within "
                                  f"{self.args.reach_seconds:g} s")
            time.sleep(POLL_SECONDS)

    # -- reaching --------------------------------------------------------

    def reach(self, launch, made):
        deadline = launch.started + self.args.reach_seconds
        answered = window = None
        while True:
            live = launch.live()
            if launch.launcher.pid not in live:
                exit_code = "" if launch.popen is None else f" (exit {_exit_code(launch.popen)})"
                raise CheckFailed(f"launch {launch.number}: the launcher ended{exit_code} "
                                  f"{time.monotonic() - launch.started:.1f} s after its start, before it "
                                  f"was reached")
            if answered is None:
                for port, pid in sorted(launch.processes.listening(list(live)).items()):
                    if _answers_health(port):
                        answered = port, live[pid]
                        break
            window = self.desktop.find(launch.launcher)
            if answered and window:
                break
            if time.monotonic() > deadline:
                if not answered:
                    raise CheckFailed(f"launch {launch.number}: the server did not answer on its own local "
                                      f"address within {self.args.reach_seconds:g} s; processes: "
                                      f"{launch.names(live.values())}")
                raise CheckFailed(f"launch {launch.number}: the server answered on port {answered[0]} but no "
                                  f"window opened within {self.args.reach_seconds:g} s: this runner did not "
                                  f"show the window, and a check that skips is not a check")
            time.sleep(POLL_SECONDS)
        launch.port, server = answered
        launch.server = server
        if not os.path.isdir(made):
            raise CheckFailed(f"launch {launch.number}: the app did not make its data folder in the fresh "
                              f"folder it was given")
        whose = "the launcher" if server.pid == launch.launcher.pid else (
            "the launcher's child" if server.ppid == launch.launcher.pid else "a process of this launch")
        say(f"launch {launch.number}: reached after {time.monotonic() - launch.started:.1f} s "
            f"(bound {self.args.reach_seconds:g} s): the server answered on 127.0.0.1:{launch.port} "
            f"({whose}, {launch.name(server)}); {window[1]}; data folder made in the fresh folder; "
            f"processes of this launch: {launch.names(launch.live().values())}")
        self.door(launch)
        # The window log: named, never read here (it may hold paths).
        log = os.path.join(made, WINDOW_LOG_NAME)
        if os.path.islink(log) or not os.path.isfile(log):
            held = " (a link stands at its name)" if os.path.islink(log) else ""
            raise CheckFailed(f"launch {launch.number}: the launcher made no window log in the app's data "
                              f"folder{held}, so the download could not be shown to load its engine")
        say(f"launch {launch.number}: window log found in the app's data folder: the download loaded its engine")
        self.admitted(launch)
        return window

    def admitted(self, launch):
        """The window's own session was let in and ran the app: within the
        bound for a run, the server's metrics show files the app's page
        hands its window. A session refused for want of the key is told one
        sentence and stops, and is handed none, and this check opens no
        session that runs the app in this launch, so only the window's could
        have been."""
        deadline = time.monotonic() + self.args.run_seconds
        while True:
            media, found, sessions = _sessions_seen(launch.port)
            if media:
                break
            if time.monotonic() > deadline:
                raise CheckFailed(f"launch {launch.number}: the window's own session never ran the app within "
                                  f"{self.args.run_seconds:g} s: the server holds no file the app's page hands its "
                                  f"window, which a session it lets in is given on its first run ({sessions}): the "
                                  f"window shows the refusal, or never loaded the page")
            time.sleep(POLL_SECONDS)
        results = (f"{len(found)} result(s) of the engine's ({', '.join(found)})" if found
                   else "no result of the engine's yet")
        say(f"launch {launch.number}: the window's own session ran the app: the server holds {media} byte(s) of "
            f"files the app's page hands its window, which only a session it lets in is given, and {results}; "
            f"this check opened no session that ran the app")

    def door(self, launch):
        """The reached server refuses a session's opening under a rebound
        Host, and one under its own address sent from another site's
        Origin, and opens one under the window's own address. (Whether a
        session without the launch's key is let in is asked of the third
        launch, the one whose key this check knows.)"""
        rebound = _opening_status(launch.port, f"{REBOUND_HOST}:{launch.port}")
        if rebound != 403:
            raise CheckFailed(f"launch {launch.number}: a WebSocket opening under the rebound Host "
                              f"{REBOUND_HOST}:{launch.port} was answered {rebound or 'with no status'}, not "
                              f"refused with 403: a page whose own name points at this computer could open a "
                              f"session")
        foreign = _opening_status(launch.port, f"127.0.0.1:{launch.port}", FOREIGN_ORIGIN)
        if foreign != 403:
            raise CheckFailed(f"launch {launch.number}: a WebSocket opening under the window's own address from "
                              f"the Origin {FOREIGN_ORIGIN} was answered {foreign or 'with no status'}, not refused "
                              f"with 403: a page of another site could open a session")
        own = _opening_status(launch.port, f"127.0.0.1:{launch.port}")
        if own != 101:
            raise CheckFailed(f"launch {launch.number}: a WebSocket opening under the window's own address "
                              f"127.0.0.1:{launch.port} was answered {own or 'with no status'}, not opened with 101")
        say(f"launch {launch.number}: a WebSocket opening under a rebound Host was refused (403), one under the "
            f"window's own address from another site's Origin was refused (403), and one under the window's own "
            f"address opened (101)")

    # -- stopping --------------------------------------------------------

    def gone_within(self, launch, began, bound, what):
        """Wait until no process of `launch` runs and its port no longer
        answers, at most `bound` plus the margin after `began`."""
        deadline = began + bound + self.args.margin_seconds
        while True:
            live = launch.live()
            accepts = _accepts(launch.port)
            if not live and not accepts:
                elapsed = time.monotonic() - began
                exit_code = "" if launch.popen is None else \
                    f"; {launch.role.removeprefix('the ')} exit {_exit_code(launch.popen)}"
                return (f"after {elapsed:.1f} s no process of this launch remains ({len(launch.seen)} seen: "
                        f"{launch.names(launch.seen.values())}) and port {launch.port} no longer answers "
                        f"(bound {bound:g} s + {self.args.margin_seconds:g} s margin){exit_code}")
            if time.monotonic() > deadline:
                still = [f"still running: {launch.names(live.values())}"] if live else []
                if accepts:
                    still.append(f"port {launch.port} still answers")
                raise CheckFailed(f"launch {launch.number}: {bound:g} s + {self.args.margin_seconds:g} s "
                                  f"after {what}, {'; '.join(still)}")
            time.sleep(POLL_SECONDS)

    def remove(self, launch):
        """Windows: the unpacked download can be removed -- no file in it is
        held open."""
        began = time.monotonic()
        deadline = began + self.args.margin_seconds
        tries = 0
        while True:
            tries += 1
            try:
                shutil.rmtree(launch.folder)
                say(f"launch {launch.number}: removed the unpacked download after "
                    f"{time.monotonic() - began:.1f} s ({tries} {'try' if tries == 1 else 'tries'}): "
                    f"no file in it was held open")
                return
            except OSError as error:
                if time.monotonic() > deadline:
                    held = os.path.relpath(error.filename, launch.folder) if error.filename else "a file"
                    raise CheckFailed(f"launch {launch.number}: the unpacked download could not be removed "
                                      f"{self.args.margin_seconds:g} s after the stop: {held} "
                                      f"({error.strerror})")
            time.sleep(POLL_SECONDS)

    def ordinary_stop(self):
        launch, made = self.start(1)
        window = self.reach(launch, made)
        began = time.monotonic()
        self.desktop.close(launch.launcher, window)
        result = self.gone_within(launch, began, self.args.stop_seconds, "the window was closed")
        say(f"launch 1: closed by {self.desktop.closing}; {result}")
        if self.platform == "win32" and not self.args.command:
            self.remove(launch)

    def launcher_alone_ended(self):
        launch, made = self.start(2)
        self.reach(launch, made)
        server = launch.server
        if server.pid == launch.launcher.pid:
            raise CheckFailed("launch 2: the server is the launcher itself; no child of it is left to outlive it")
        began = time.monotonic()
        if launch.popen is not None:
            launch.popen.kill()            # Windows: TerminateProcess of the launcher alone; else SIGKILL
            how = "process termination" if self.platform == "win32" else "SIGKILL"
        else:
            # macOS: SIGKILL to the launcher alone, which a fresh look must
            # still find by its id and start stamp just before the signal.
            if not _signal_if_same(self.processes, launch.launcher, signal.SIGKILL):
                raise CheckFailed(f"launch 2: the launcher {launch.name(launch.launcher)} was not signalled: "
                                  f"its id and start stamp no longer matched the process found")
            how = "SIGKILL"
        result = self.gone_within(launch, began, self.args.orphan_seconds, "the launcher alone was ended")
        say(f"launch 2: ended the launcher {launch.name(launch.launcher)} alone by {how}; its server "
            f"{launch.name(server)} went too: {result}")
        if self.platform == "win32" and not self.args.command:
            self.remove(launch)

    def typed_place(self):
        """Launch 3: the download's own server entry is started as the
        launcher starts its child -- the executable with the sentinel and a
        free port of 127.0.0.1, the launcher's environment less every
        STREAMLIT_* variable, a key of this check's own -- with a fresh
        data folder. Once it has said it listens, holds the port and
        answers, a session is opened as the window opens one, its first run
        asked with the key in its address, and a place typed in the city
        search; the run must offer that place's label. The server is then
        stopped as the launcher stops it, by the end of its input, and no
        process of this launch may remain within its bound and the margin.
        On the way: the server's door holds as in the first launch; once
        the place is offered, the first run must be seen to have drawn the
        example chart's Jupiter where the engine puts it; and, the keyed
        session still open, a session with no key and one with a key one
        letter off the launch's are told the one sentence and shown nothing
        else."""
        number = 3
        data = self._fresh(f"data-{number}")
        withhold(data, "<fresh>")
        output = os.path.join(data, "server-output.txt")
        port = _free_port()
        key = secrets.token_urlsafe(32)
        _WITHHELD.insert(0, (key, "<withheld>"))
        if self.args.command:
            folder = os.path.abspath(self.args.folder) if self.args.folder else None
            command, cwd = [*self.args.command, SERVER_SENTINEL, str(port)], None
            environment = dict(os.environ, HOME=data, XDG_DATA_HOME=data)
            made = os.path.join(data, APP_DIR_NAME)
            how = "the command's server entry run with a fresh home and data folder"
        elif self.platform == "win32":
            folder = self._unpack(number)
            roaming, local = os.path.join(data, "Roaming"), os.path.join(data, "Local")
            os.makedirs(roaming)
            os.makedirs(local)
            command, cwd = [os.path.join(folder, "Zij.exe"), SERVER_SENTINEL, str(port)], folder
            environment = dict(os.environ, APPDATA=roaming, LOCALAPPDATA=local)
            made = os.path.join(roaming, APP_DIR_NAME)
            how = "Zij.exe's server entry started from the unpacked zip, APPDATA and LOCALAPPDATA in a fresh folder"
        else:
            folder = self._unpack(number)
            command = [os.path.join(folder, "Zij.app", "Contents", "MacOS", "Zij"), SERVER_SENTINEL, str(port)]
            cwd = folder
            environment = dict(os.environ, HOME=data)
            made = os.path.join(data, "Library", "Application Support", APP_DIR_NAME)
            how = "the bundle's executable's server entry started from the unpacked zip, HOME in a fresh folder"
        launch = Launch(self.processes, folder, number)
        self.current = launch
        launch.role, launch.made, launch.streams = "the server", made, [("output", output)]
        # Its input a pipe only this check holds, as the launcher holds its
        # child's; its output and errors a pipe that a thread of this check
        # reads as it comes into a file in the fresh folder, as the
        # launcher's thread reads its child's. The thread never keeps the
        # check from ending.
        with open(output, "wb"):
            pass
        launch.popen = subprocess.Popen(command, cwd=cwd, env=_server_environment(environment, key),
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        launch.drain = threading.Thread(target=_drain, args=(launch.popen.stdout, output), daemon=True)
        launch.drain.start()
        launch.started = time.monotonic()
        self._find_launcher(launch)
        say(f"launch {number}: started: {how}, on 127.0.0.1:{port} with a key of this check's own, its input "
            f"a pipe only this check holds and its output a pipe it reads as it comes, as the launcher gives "
            f"them; server {launch.name(launch.launcher)}")
        self._reach_the_server(launch, port, output)
        self.door(launch)
        session = Session(port)
        try:
            xsrf = self._open(launch, session)
            elements, took = self._one_run(launch, session, rerun_message(f"{LAUNCH_KEY_PARAMETER}={key}"),
                                           "the first run")
            boxes = sorted({element[1] for element in elements
                            if element[0] == "text_input" and element[1].endswith("-" + CITY_SEARCH_KEY)})
            if len(boxes) != 1:
                raise CheckFailed(f"launch {number}: the first run showed {len(boxes) or 'no'} city search(es) "
                                  f"(a text box keyed {CITY_SEARCH_KEY}), not one")
            say(f"launch {number}: a session opened as the window opens one (its own Host and Origin"
                f"{', the XSRF cookie and token' if xsrf else ''}); the first run, its key in the address, ended "
                f"after {took:.1f} s (bound {self.args.run_seconds:g} s); the city search, holding the example's "
                f"city, offered {options_text(options_offered(elements))}")
            first = elements
            elements, took = self._one_run(launch, session, rerun_message("", [(boxes[0], PLACE_TYPED)]),
                                           f"the run with {PLACE_TYPED!r} typed in the city search")
            options = options_offered(elements)
            if options is None or options.count(PLACE_FOUND) != 1:
                raise CheckFailed(f"launch {number}: with {PLACE_TYPED!r} typed in the city search, the run "
                                  f"offered {options_text(options)}, not {PLACE_FOUND!r} once among them")
            say(f"launch {number}: with {PLACE_TYPED!r} typed in the city search, the run ended after {took:.1f} s "
                f"(bound {self.args.run_seconds:g} s) and offered {PLACE_FOUND!r} among its "
                f"{options_text(options)}")
            say(f"launch {number}: {self._known_value(launch, first)}")
            # One letter off the key: a check of the whole key, not of its
            # length or a part of it.
            wrong = key[:-1] + ("A" if key[-1] != "A" else "B")
            for who, query in (("with no key in its address", ""),
                               ("with a key one letter off the launch's", f"{LAUNCH_KEY_PARAMETER}={wrong}")):
                other = Session(port)
                try:
                    self._open(launch, other)
                    self._one_run(launch, other, rerun_message(query), f"the first run of a session {who}",
                                  refused=True)
                finally:
                    other.close()
            say(f"launch {number}: while that session was open, one opened as the window opens one but with no key "
                f"in its address, and one with a key one letter off the launch's, were each told only "
                f"{LAUNCH_KEY_REFUSAL!r}: the first run of each showed that sentence and nothing else")
        finally:
            session.close()
        launch.notes = []
        began = time.monotonic()
        launch.popen.stdin.close()
        result = self.gone_within(launch, began, self.args.orphan_seconds, "its input was closed")
        launch.drain.join(DRAIN_SECONDS)
        say(f"launch {number}: stopped as the launcher stops it, by the end of its input; {result}")
        if self.platform == "win32" and not self.args.command:
            self.remove(launch)

    def _reach_the_server(self, launch, port, output):
        """The server has said on its output that it listens on `port`, a
        process of this launch holds that port, and it answers."""
        deadline = launch.started + self.args.reach_seconds
        mark = f"{LISTENING_MARK} {port}"
        while True:
            live = launch.live()
            if launch.launcher.pid not in live:
                raise CheckFailed(f"launch {launch.number}: the server ended (exit {_exit_code(launch.popen)}) "
                                  f"{time.monotonic() - launch.started:.1f} s after its start, before it answered")
            said = mark in (_tail(output, count=1 << 20) or [])
            holder = launch.processes.listening(list(live)).get(port) if said else None
            if holder is not None and _answers_health(port):
                break
            if time.monotonic() > deadline:
                why = ("it never said it was listening" if not said else
                       f"no process of this launch holds port {port}" if holder is None else "it did not answer")
                raise CheckFailed(f"launch {launch.number}: the server was not reached on 127.0.0.1:{port} within "
                                  f"{self.args.reach_seconds:g} s: {why}")
            time.sleep(POLL_SECONDS)
        launch.port, launch.server = port, live[holder]
        say(f"launch {launch.number}: reached after {time.monotonic() - launch.started:.1f} s (bound "
            f"{self.args.reach_seconds:g} s): the server said it was listening, holds 127.0.0.1:{port} "
            f"({launch.name(launch.server)}) and answered")

    def _open(self, launch, session):
        """Open `session` as the window opens one; whether its server's
        XSRF protection gave a cookie and token."""
        try:
            return session.open()
        except (OSError, ValueError) as error:
            raise CheckFailed(f"launch {launch.number}: no session could be opened as the window opens one: "
                              f"{type(error).__name__}: {error}")
        except CheckFailed as failure:
            raise CheckFailed(f"launch {launch.number}: {failure}")

    def _known_value(self, launch, elements):
        """Where the first run's wheel puts KNOWN_POINT, held to
        KNOWN_LONGITUDE: a clause saying so, or a failure."""
        wheels = [element[2] for element in elements if element[0] == "component" and element[1] == WHEEL_COMPONENT]
        if len(wheels) != 1:
            raise CheckFailed(f"launch {launch.number}: the first run drew {len(wheels) or 'no'} chart wheel(s), "
                              f"not one, so the example chart's {KNOWN_POINT} could not be read")
        try:
            svg = json.loads(wheels[0])["svg"]
        except (ValueError, TypeError, KeyError):
            raise CheckFailed(f"launch {launch.number}: the first run's chart wheel holds no drawing that can be "
                              f"read")
        found = re.findall(rf'data-point="{KNOWN_POINT}" data-lon="([^"]*)"', svg if isinstance(svg, str) else "")
        try:
            values = [float(value) for value in found]
        except ValueError:
            values = []
        if len(values) != 1:
            raise CheckFailed(f"launch {launch.number}: the first run's chart wheel places {KNOWN_POINT} "
                              f"{len(found)} time(s) in a form that can be read, not once")
        off = abs(values[0] - KNOWN_LONGITUDE)
        if not off <= KNOWN_TOLERANCE:
            raise CheckFailed(f"launch {launch.number}: the example chart's wheel puts {KNOWN_POINT} at "
                              f"{found[0]}, not {KNOWN_LONGITUDE:.6f} (within {KNOWN_TOLERANCE:g} of a degree), "
                              f"where the app draws it on the system the suite runs on: this build's Swiss "
                              f"Ephemeris computes otherwise")
        return (f"the example chart's wheel puts {KNOWN_POINT} at {found[0]}, {off:.1e} of a degree from "
                f"{KNOWN_LONGITUDE:.6f}, where the engine puts it on the system the suite runs on (bound "
                f"{KNOWN_TOLERANCE:g})")

    def _one_run(self, launch, session, message, what, refused=False):
        """One run, read to its end: its elements and time. What it said
        and offered is kept for a failure's report. A run that is to be
        `refused` must show the sentence a session without the key is told
        and nothing else, not one element more; any other run must not
        show it."""
        try:
            status, elements, took = session.run(message, self.args.run_seconds)
        except RunUnfinished as unfinished:
            elements, heard = unfinished.args
            answers = "still answered" if _answers_health(session.port) else "no longer answered"
            launch.notes = heard.notes() + [f"the server {answers} its health check after the bound"] \
                + _run_notes(elements)
            raise CheckFailed(f"launch {launch.number}: {what} did not end within {self.args.run_seconds:g} s: "
                              f"{heard.verdict()}")
        except CheckFailed as failure:
            raise CheckFailed(f"launch {launch.number}: {what}: {failure}")
        except (OSError, ValueError) as error:
            raise CheckFailed(f"launch {launch.number}: {what} could not be read: {type(error).__name__}: {error}")
        launch.notes = _run_notes(elements)
        told = any(element[0] == "alert" and element[2] == LAUNCH_KEY_REFUSAL for element in elements)
        if refused and not told:
            raise CheckFailed(f"launch {launch.number}: {what} was not refused: the server never told it that the "
                              f"app can be used only in its own window, and showed it "
                              f"{session.heard.counts['element']} element(s)")
        if refused and (len(elements) != 1 or session.heard.counts["element"] != 1):
            raise CheckFailed(f"launch {launch.number}: {what} was told that the app can be used only in its own "
                              f"window, but shown {session.heard.counts['element']} element(s), not that sentence "
                              f"alone")
        if told and not refused:
            raise CheckFailed(f"launch {launch.number}: {what} was refused: the server told the session that the "
                              f"app can be used only in its own window, so the key this check gave it was not "
                              f"accepted; the check failed, it did not pass")
        if status == FINISHED_WITH_COMPILE_ERROR:
            raise CheckFailed(f"launch {launch.number}: {what} ended at an error in compiling the app")
        return elements, took

    # -- saying why ------------------------------------------------------

    def explain(self, launch):
        """After a failure of `launch`: what the outside can see of why, as
        lines. When the launcher ended before the launch was reached, waits
        at most the orphan bound and the margin for what it started to end,
        and tells an end from a hand-off; on macOS waits at most the margin
        again for a crash report. Ends nothing."""
        lines = []
        launcher = launch.launcher
        live = launch.live()
        ended = launcher is None or launcher.pid not in live
        if launch.popen is not None:
            code = launch.popen.poll()
            lines.append(f"{launch.role}'s exit status: {'still running' if code is None else code}")
        if launcher is not None and ended and launch.port is None:
            gone = launch.sighting(launcher)
            at = gone.ended if gone is not None and gone.ended is not None else launch.elapsed()
            deadline = time.monotonic() + self.args.orphan_seconds + self.args.margin_seconds
            while live and time.monotonic() < deadline:
                time.sleep(POLL_SECONDS)
                live = launch.live()
            waited = launch.elapsed() - at
            successors = [proc for proc in live.values() if launch.started_by_launcher(proc)]
            others = [proc for proc in live.values() if proc not in successors]
            if successors:
                lines.append(f"a hand-off: {launch.role} started {launch.names(successors)} and ended by "
                             f"{at:.1f} s after the start; {waited:.1f} s after its end that still runs")
            else:
                lines.append(f"{launch.role} ended by {at:.1f} s after the start, and nothing it started "
                             f"was still running {waited:.1f} s after its end: it ended, it did not hand off")
            if others:
                lines.append(f"still running, not started by {launch.role}: {launch.names(others)}")
        lines.append(f"processes of this launch seen (parent at first sight; seconds after the start): "
                     f"{launch.history()}")
        if launch.made is not None:
            made = os.path.isdir(launch.made)
            lines.append(f"the app's data folder in the fresh folder: {'made' if made else 'not made'}")
            at = os.path.join(launch.made, WINDOW_LOG_NAME)
            log = _tail(at) if made else None
            if log:
                lines.append(f"the window log, last {len(log)} line(s):")
                lines.extend(f"  | {line}" for line in log)
            elif log is None and made and (os.path.islink(at) or os.path.exists(at)):
                lines.append("the window log could not be read: only a regular file, not a link, is read")
        lines.extend(launch.notes)
        for what, path in launch.streams:
            text = _tail(path)
            if text is None:
                lines.append(f"{launch.role}'s {what}: not readable")
            elif not text:
                lines.append(f"{launch.role}'s {what}: empty")
            else:
                lines.append(f"{launch.role}'s {what}, last {len(text)} line(s):")
                lines.extend(f"  | {line}" for line in text)
        if self.platform == "darwin" and not self.args.command and launch.folder is not None:
            reports = []
            deadline = time.monotonic() + (self.args.margin_seconds if ended else 0)
            while True:
                reports = _crash_reports(launch)
                if reports or time.monotonic() >= deadline:
                    break
                time.sleep(POLL_SECONDS)
            if not reports:
                lines.append("no crash report for the bundle's executable since the launch began")
            for header in reports:
                lines.append("a crash report for the bundle's executable:")
                lines.extend(f"  | {line}" for line in header)
        return lines

    def run(self):
        self.work = tempfile.mkdtemp(prefix="stop-check-", dir=self.args.work or os.environ.get("RUNNER_TEMP"))
        withhold(self.work, "<work>")
        self.current = None
        self.details = []
        try:
            self.ordinary_stop()
            self.current = None
            self.launcher_alone_ended()
            self.current = None
            self.typed_place()
            self.current = None
        except Exception:
            if self.current is not None:
                try:
                    self.details = self.explain(self.current)
                except Exception as error:      # the failure is still said; its explanation is short
                    self.details = [f"what the outside can see could not be read: {type(error).__name__}"]
            raise
        finally:
            if self.current is not None:
                self.current.end_everything()
            shutil.rmtree(self.work, ignore_errors=True)


# --------------------------------------------------------------------------
# macOS: the crash reports the system writes.

_REPORT_FIELDS = ("Process", "Path", "Identifier", "Parent Process", "Exception Type", "Exception Codes",
                  "Exception Note", "Termination Reason", "Termination Signal", "Crashed Thread")


def _crash_reports(launch, folders=None):
    """The header of each crash report written since `launch` began for an
    executable inside its download, as lines: from a report of today's form
    (.ips: a JSON header line, then a JSON body), its process, exception,
    termination and application-specific note; from one of the older text
    form, its header lines. Each line cut to LINE_CHARS, at most three
    reports."""
    if folders is None:
        folders = [os.path.join(os.path.expanduser("~"), "Library", "Logs", "DiagnosticReports"),
                   "/Library/Logs/DiagnosticReports"]
    found = []
    for folder in folders:
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            path = os.path.join(folder, name)
            try:
                if not name.endswith((".ips", ".crash")) or os.path.getmtime(path) < launch.wall_started - 2:
                    continue
                with open(path, "rb") as f:
                    text = f.read(4 * 1024 * 1024).decode("utf-8", "replace")
            except OSError:
                continue
            header = _report_header(text, launch)
            if header:
                found.append((os.path.getmtime(path), header))
    return [header for _, header in sorted(found)[:3]]


def _report_header(text, launch):
    first, _, rest = text.partition("\n")
    try:
        meta, body = json.loads(first), json.loads(rest)
    except ValueError:
        meta = body = None
    if isinstance(meta, dict) and isinstance(body, dict):
        path = body.get("procPath")
        if not _inside(path, launch.folder):
            return None
        exc, term = body.get("exception") or {}, body.get("termination") or {}
        lines = [f"process {launch.where(path)} ({body.get('pid')}), parent "
                 f"{body.get('parentPid')} ({body.get('parentProc')})",
                 "exception: " + ", ".join(f"{k} {exc[k]}" for k in ("type", "signal", "subtype", "codes")
                                           if exc.get(k)),
                 "termination: " + ", ".join(f"{k} {term[k]}" for k in ("namespace", "indicator", "code",
                                                                       "byProc", "reasons", "details")
                                             if term.get(k) not in (None, "", []))]
        asi = body.get("asi")
        if isinstance(asi, dict):
            notes = [f"{k}: {v}" for k, values in asi.items() for v in (values if isinstance(values, list)
                                                                        else [values])]
            lines += [f"application note: {note}" for note in notes[:3]]
        if body.get("faultingThread") is not None:
            lines.append(f"faulting thread {body.get('faultingThread')}")
        return [scrub(_CONTROL.sub("", line))[:LINE_CHARS] for line in lines]
    lines = [line.strip() for line in text.splitlines()[:80]]
    if not any(line.startswith("Path:") and _inside(line[5:].strip(), launch.folder) for line in lines):
        return None
    kept = [f"Path: {launch.where(line[5:].strip())}" if line.startswith("Path:") else line
            for line in lines if line.split(":", 1)[0] in _REPORT_FIELDS]
    return [scrub(_CONTROL.sub("", line))[:LINE_CHARS] for line in kept[:12]]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Start, reach and stop a built download.")
    parser.add_argument("--zip", help="the download's zip (default: this system's, in the working folder)")
    parser.add_argument("--work", help="where to unpack and keep the fresh data folders")
    parser.add_argument("--reach-seconds", type=float, default=REACH_SECONDS)
    parser.add_argument("--stop-seconds", type=float, default=STOP_SECONDS)
    parser.add_argument("--orphan-seconds", type=float, default=ORPHAN_SECONDS)
    parser.add_argument("--margin-seconds", type=float, default=MARGIN_SECONDS)
    parser.add_argument("--run-seconds", type=float, default=RUN_SECONDS)
    parser.add_argument("--stand-in-windows", help=argparse.SUPPRESS)
    parser.add_argument("--folder", help=argparse.SUPPRESS)
    parser.add_argument("--command", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.command and args.zip is None:
        args.zip = ZIPS.get(sys.platform)
    return args


def main(argv=None):
    try:
        # UTF-8 on every system: Windows would write a pipe in its ANSI code
        # page, and the log would lose the accented letters of a place.
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except AttributeError:
        pass
    args = parse_args(argv)
    withhold(os.path.expanduser("~"), "<home>")
    withhold(os.getcwd(), "<checkout>")
    check = None
    try:
        check = Check(args)
        if not args.command and not os.path.isfile(args.zip or ""):
            raise CheckFailed(f"no {args.zip} to check")
        check.run()
    except CheckFailed as failure:
        say(f"stop check FAILED: {failure}")
        _say_details(check)
        return 1
    except Exception as error:          # the check itself broke: a failure, said without a traceback's paths
        say(f"stop check FAILED: the check itself failed: {type(error).__name__}: {error}")
        _say_details(check)
        return 1
    say("stop check passed: the download started, was reached, and stopped leaving no process behind, "
        "by its window's close and by its launcher's end alone; its window's own session ran the app; its server "
        "refused a rebound Host, another site's Origin, and a session without its key or with a wrong one; its "
        "wheel put the example chart's Jupiter where the app draws it here; and its server, started on its own, "
        "offered the place typed in its city search")
    return 0


def _say_details(check):
    for line in getattr(check, "details", None) or []:
        say(f"  {line}")


if __name__ == "__main__":
    sys.exit(main())
