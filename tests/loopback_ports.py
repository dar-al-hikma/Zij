"""Loopback ports for the tests that start a server on one.

A test takes its port from a small fixed pool below the range the system
hands out for outgoing connections, so that no connection of any program is
given it by the system, and holds a claim on that port for the whole machine
while it runs (`claim`), so that no other run of these tests -- another
worker, another checkout, another user's -- starts a server on it at the
same time. What is left is a program outside these tests binding the port
between the test's check and the server's bind; `port_taken` says so by
name when a server could not come up.
"""
import socket
import sys
import time


def bindable(port):
    """Whether `port` on the loopback address can be bound now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def claim(number, fallback_root):
    """A hold on port `number` among every run of these tests on the
    machine, or None where another holds it. On Linux it is an abstract
    Unix socket named for the port: one namespace for the whole machine,
    with no file and so no owner or mode to stop another user's run from
    claiming it in turn, and given up by the kernel when its holder ends,
    however it ends. Elsewhere it is a lock file in this run's own folder,
    which holds only among this run's workers."""
    if sys.platform.startswith("linux"):
        held = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            held.bind(f"\0zij-tests-loopback-port-{number}")
        except OSError:
            held.close()
            return None
        return held
    import fcntl

    held = open(fallback_root / f"{number}.lock", "w")
    try:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        held.close()
        return None
    return held


def claimed_port(ports, fallback_root, wait=600):
    """A generator for a fixture: yields a port of `ports`, claimed by the
    caller alone among the runs on the machine (`claim`) and free when
    yielded, and gives the claim up when resumed. Waits at most `wait`
    seconds for one to come free."""
    fallback_root.mkdir(exist_ok=True)
    deadline = time.monotonic() + wait
    held_elsewhere = []
    while True:
        held_elsewhere.clear()
        for number in ports:
            held = claim(number, fallback_root)
            if held is None:
                continue
            if bindable(number):
                try:
                    yield number
                finally:
                    held.close()
                return
            held.close()
            held_elsewhere.append(number)
        assert time.monotonic() < deadline, (
            f"no port of {list(ports)} came free in {wait} seconds: claimed by other runs of these tests on the "
            f"machine, or, for {held_elsewhere}, bound by a program outside them")
        time.sleep(0.5)


def port_taken(port, said=""):
    """Why a server may not have come up on `port`: another process has it.
    Empty where nothing says so."""
    if f"Port {port} is not available" in said or not bindable(port):
        return (f"\nport {port} was taken by another process between the test's check and the child's bind: a "
                f"program outside these tests (or a copy of them too old to claim its port: every run of these keeps "
                f"off a claimed one)")
    return ""
