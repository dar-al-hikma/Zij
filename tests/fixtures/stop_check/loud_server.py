"""A stand-in for the app's server entry that first says much, for the stop
check's own tests.

    loud_server.py --run-streamlit-server PORT

Before anything else it says whether its input and its output are pipes,
and writes LOUD_BYTES on its standard output, well over what a pipe holds
unread; then it becomes the real server entry beside it
(`server_entry.py`: the launcher run from source) with the same arguments
and the same standard streams. A server whose output pipe is not read as it
comes waits in that first write and never says it listens.
"""
import os
import stat
import sys

LOUD_BYTES = 400 * 1024
LINE = b"what the server says before it listens, enough to fill a pipe that nobody reads"
DONE = b"loud: done"


def _kind(fd):
    return b"a pipe" if stat.S_ISFIFO(os.fstat(fd).st_mode) else b"not a pipe"


def main():
    out = sys.stdout.buffer
    out.write(b"loud: input " + _kind(0) + b", output " + _kind(1) + b"\n")
    written = number = 0
    while written < LOUD_BYTES:
        line = b"%06d " % number + LINE + b"\n"
        out.write(line)
        written += len(line)
        number += 1
    out.write(DONE + b"\n")
    out.flush()
    entry = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server_entry.py")
    os.execv(sys.executable, [sys.executable, entry, *sys.argv[1:]])


if __name__ == "__main__":
    main()
