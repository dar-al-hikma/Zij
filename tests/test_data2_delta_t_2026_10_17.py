"""The Delta T reference proved against the library's own table, recorded in
ephemeris.py (_DELTA_T_RECORDED).

Each thread's Delta T table is compared with a reference read once per
process in a thread of its own. Both reads open the folder by its name, so a
directory swapped in at its path for both reads gave the planted table to
the thread and to the reference alike: the thread computed with it, unseen,
and every honest thread after it was refused. The reference is now kept
only where it is the table recorded in the code, so the raced thread is
refused and an honest thread after it is not.

The race is emulated, not run: the engine's code runs unchanged, and the
swap is made at the instants a racing program would aim at -- just before a
thread is pointed at the folder (set_ephe_path), and undone just after its
table is read (_delta_t_table) -- in a fresh interpreter whose temporary
folder is the test's own.
"""
from __future__ import annotations

import struct
import subprocess
import sys
import textwrap

import pytest

from conftest import EXECUTABLE_DIR

TIMEOUT = 300

RACE = textwrap.dedent('''
    import os, sys, threading
    sys.path.insert(0, {root!r})
    import ephemeris as E
    planted = {planted!r}
    folder = E._EPHEMERIS_FOLDER
    raced = set({raced!r})
    swapped = {{}}
    real_set, real_table = E._swisseph.set_ephe_path, E._delta_t_table

    def set_ephe_path(path):
        name = threading.current_thread().name
        if name in raced and name not in swapped:
            os.rename(folder, folder + '-aside')
            os.rename(planted, folder)
            swapped[name] = True
        return real_set(path)

    def table():
        out = real_table()
        if swapped.get(threading.current_thread().name) is True:
            os.rename(folder, planted)
            os.rename(folder + '-aside', folder)
            swapped[threading.current_thread().name] = 'undone'
        return out

    E._swisseph.set_ephe_path, E._delta_t_table = set_ephe_path, table

    def run(name):
        said = []
        def body():
            for _ in range(2):
                try:
                    E.ephemeris_thread_check()
                except E.EphemerisRefused as refusal:
                    said.append('REFUSED')
                else:
                    said.append('%.2f' % (E.swe.deltat_ex(2451544.5, -1) * 86400))
        thread = threading.Thread(target=body, name=name)
        thread.start()
        thread.join()
        return said

    print(run('victim'), run('later'), sorted(os.listdir(folder)), os.path.isdir(planted))
''')


def _planted(tmp_path):
    planted = tmp_path / "planted"
    planted.mkdir(mode=0o700)
    (planted / "swe_deltat.txt").write_text("".join(f"{year} 3600.0\n" for year in range(1620, 2201)))
    return planted


def _race(tmp_path, raced):
    temporary = tmp_path / "t"
    temporary.mkdir()
    script = RACE.format(root=str(EXECUTABLE_DIR), planted=str(_planted(tmp_path)), raced=list(raced))
    env = {**__import__("os").environ, "TMPDIR": str(temporary)}
    done = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, env=env,
                          timeout=TIMEOUT)
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def test_a_planted_table_taken_by_a_thread_and_the_reference_alike_is_refused_and_a_later_thread_is_not(tmp_path):
    assert _race(tmp_path, ["victim", "ephemeris-reference"]) == (
        "['REFUSED', 'REFUSED'] ['63.83', '63.83'] [] True")


def test_a_planted_table_taken_by_the_thread_alone_is_refused_as_before(tmp_path):
    assert _race(tmp_path, ["victim"]) == "['REFUSED', 'REFUSED'] ['63.83', '63.83'] [] True"


def test_with_no_race_every_thread_computes_with_the_library_s_own_table(tmp_path):
    assert _race(tmp_path, []) == "['63.83', '63.83'] ['63.83', '63.83'] [] True"


def test_the_recorded_table_is_the_library_s_own(tmp_path):
    """Read where no Delta T file can be: a thread of a fresh interpreter
    pointed at an empty folder of its own. A new pyswisseph whose table
    moves fails here, and the record moves with it in the same commit."""
    empty = tmp_path / "empty"
    empty.mkdir()
    script = textwrap.dedent(f'''
        import os, sys, threading
        os.environ['SE_EPHE_PATH'] = {str(empty)!r}
        sys.path.insert(0, {str(EXECUTABLE_DIR)!r})
        import swisseph
        out = []
        def read():
            swisseph.set_ephe_path({str(empty)!r})
            out.extend(swisseph.deltat_ex(swisseph.julday(y, 1, 1, 0.0), -1) for y in range(1620, 2131))
        thread = threading.Thread(target=read)
        thread.start()
        thread.join()
        import ast
        tree = ast.parse(open(os.path.join({str(EXECUTABLE_DIR)!r}, 'ephemeris.py'), encoding='utf-8').read())
        node, = [n for n in tree.body if isinstance(n, ast.Assign)
                 and [ast.unparse(t) for t in n.targets] == ['_DELTA_T_RECORDED']]
        recorded = ast.literal_eval(node.value)
        print(len(out), len(recorded), max(abs(v * 86400 - r) for v, r in zip(out, recorded)) < 1e-6,
              swisseph.version)
    ''')
    done = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, timeout=TIMEOUT)
    assert done.stdout.split() == ["511", "511", "True", "2.10.03"], done.stderr


@pytest.fixture(scope="module")
def ephemeris():
    import ephemeris
    return ephemeris


def _packed(seconds):
    return struct.pack(f"!{len(seconds)}d", *(value / 86400.0 for value in seconds))


def test_the_comparison_takes_two_microseconds_and_no_more(ephemeris):
    recorded = list(ephemeris._DELTA_T_RECORDED)
    assert ephemeris._delta_t_as_recorded(_packed(recorded))
    for year in (0, 255, 510):
        for moved, kept in ((1.9e-6, True), (-1.9e-6, True), (2.1e-6, False), (-2.1e-6, False), (3600.0, False)):
            table = list(recorded)
            table[year] += moved
            assert ephemeris._delta_t_as_recorded(_packed(table)) is kept, (year, moved)
    assert not ephemeris._delta_t_as_recorded(_packed(recorded[:-1]))
    assert not ephemeris._delta_t_as_recorded(_packed(recorded + [0.0]))
    assert not ephemeris._delta_t_as_recorded(b"")
