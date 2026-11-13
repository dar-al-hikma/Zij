"""The attached star catalogue proved by its values (engine.py's
FIXED_STAR_RECORDED and _fixed_star_attach).

The shipped catalogue's copy is hashed as it is written and read back, but
Swiss Ephemeris then opens the copy by its name, so a change made between
the readback and the library's open was read, unseen, for the life of the
process: Regulus moved 13.6 degrees. Now each of Sahl's stars is read at four
dates spanning those the app casts once the catalogue is attached, and
compared with the longitudes recorded from the shipped catalogue; any
difference refuses the catalogue, with the page's own sentence (the rest of
the catalogue's rows are pinned in test_fixed_stars_page.py). J2000 alone
did not see a field that acts only away from the catalogue's epoch: a
proper motion multiplied by a hundred left J2000 as recorded and moved
Regulus 5.1 degrees at 1200.

The race is emulated, not run: the engine runs unchanged in a fresh
interpreter whose temporary folder is the test's own, and the copy is
changed by its path at the instant _fixed_star_attach is entered (after the
readback, before the library's open).
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import textwrap

import pytest

from conftest import EXECUTABLE_DIR

TIMEOUT = 300
REFUSAL = ("no Swiss Ephemeris star catalogue is attached; nothing is computed"
           " -- the fixed-star file could not be read")

RACE = textwrap.dedent('''
    import json, os, sys
    sys.path.insert(0, {root!r})
    import engine, ephemeris
    star, field, value = {star!r}, {field!r}, {value!r}

    def moved_hour(line):
        cells = line.split(',')
        if field is None:
            cells[3] = '%02d' % ((int(cells[3]) + 1) % 24)
        else:
            cells[field] = value
        return ','.join(cells)

    real = engine._fixed_star_attach

    def attach(ephe_dir, source, *checked):
        if star:
            path = os.path.join(ephe_dir, 'sefstars.txt')
            with open(path, encoding='latin-1', newline='') as f:
                lines = f.read().split('\\n')
            hit = [i for i, line in enumerate(lines) if line.split(',')[0].strip() == star]
            assert hit, star
            for i in hit:
                lines[i] = moved_hour(lines[i])
            with open(path, 'w', encoding='latin-1', newline='') as f:
                f.write('\\n'.join(lines))
        return real(ephe_dir, source, *checked)

    engine._fixed_star_attach = attach
    stars = engine.fixed_star_longitudes(2451545.0)
    print(json.dumps({{'stars': stars, 'refusal': engine.fixed_star_refusal() if stars is None else None,
                       'why': engine._FIXED_STAR_STATE['why'], 'ready': engine._FIXED_STAR_STATE['ready'],
                       'later': engine.fixed_star_longitudes(2451545.0 + 365.25),
                       'at1200': engine.fixed_star_longitudes(engine.civil_to_jd(1200, 6, 1, 0.0))}}))
''')


def _run(tmp_path, star, field=None, value=None):
    temporary = tmp_path / "t"
    temporary.mkdir()
    env = {**os.environ, "TMPDIR": str(temporary)}
    done = subprocess.run([sys.executable, "-I", "-c", RACE.format(root=str(EXECUTABLE_DIR), star=star, field=field,
                                                                        value=value)],
                          capture_output=True, text=True, env=env, timeout=TIMEOUT)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


def _recorded():
    tree = ast.parse((EXECUTABLE_DIR / "engine.py").read_text(encoding="utf-8"))
    node, = [n for n in tree.body if isinstance(n, ast.Assign)
             and [ast.unparse(t) for t in n.targets] == ["FIXED_STAR_RECORDED"]]
    return ast.literal_eval(node.value)[2451545.0]


@pytest.mark.parametrize("star", ["Vega", "Regulus", "Aldebaran"])
def test_a_star_changed_between_the_readback_and_the_attach_refuses_the_catalogue(tmp_path, star):
    got = _run(tmp_path, star)
    assert got["stars"] is None and got["later"] is None and got["ready"] is False
    assert got["refusal"] == REFUSAL
    assert got["why"].endswith(f"it places {star} otherwise than the shipped file does"), got["why"]
    assert "sefstars.txt" not in got["why"]


# A record's fields: name, designation, frame, RA h m s, Dec d m s, then
# (9) proper motion in RA, (10) in Dec, (11) radial velocity, (12) parallax.
# Each edit leaves Regulus at J2000 within the bound (so a proof at J2000
# alone passed it) and moves it at the span's ends.
FIELDS = {"proper motion in RA": (9, "-24873.00"), "proper motion in Dec": (10, "5590.00"),
          "radial velocity": (11, "590"), "parallax": (12, "44.0")}


@pytest.mark.parametrize("field", sorted(FIELDS))
def test_a_field_that_acts_away_from_the_epoch_refuses_the_catalogue(tmp_path, field):
    got = _run(tmp_path, "Regulus", *FIELDS[field])
    assert got["stars"] is None and got["at1200"] is None and got["ready"] is False
    assert got["refusal"] == REFUSAL
    assert got["why"].endswith("it places Regulus otherwise than the shipped file does"), got["why"]


def test_the_honest_catalogue_gives_every_star_as_recorded(tmp_path):
    got = _run(tmp_path, "")
    recorded = _recorded()
    assert got["ready"] is True and got["why"] is None
    assert sorted(got["stars"]) == sorted(recorded)
    assert len(recorded) == 28
    for name, value in recorded.items():
        assert abs(got["stars"][name] - value) <= 1e-9, name
        assert abs(got["later"][name] - value) < 0.05 and got["later"][name] != value, name


def test_every_star_the_app_uses_is_recorded_and_the_bound_is_a_millionth(engine):
    names = [name for name, _nature in engine["SAHL_FIXED_STARS"]]
    recorded = engine["FIXED_STAR_RECORDED"]
    assert len(recorded) == 4
    for jd in sorted(recorded):
        assert sorted(recorded[jd]) == sorted(names), jd
    assert engine["FIXED_STAR_PROOF_DEGREES"] == 1e-6


def test_the_dates_span_those_the_app_casts():
    """The first and the last day the app casts (app.py's own bounds), one
    between, and J2000."""
    tree = ast.parse((EXECUTABLE_DIR / "app.py").read_text(encoding="utf-8"))
    bound = {ast.unparse(t): n.value for n in tree.body if isinstance(n, ast.Assign) for t in n.targets}
    first = ast.literal_eval(bound["EPHEMERIS_JD_MIN"])
    last_raw = ast.literal_eval(bound["EPHEMERIS_JD_MAX"]) - ast.literal_eval(bound["EPHEMERIS_SEARCH_DAYS"])
    assert ast.unparse(bound["EPHEMERIS_JD_LAST"]) == ("min(civil_to_jd(3001, 1, 1, 0.0), "
                                                        "EPHEMERIS_JD_MAX - EPHEMERIS_SEARCH_DAYS)")
    import engine
    last = min(engine.civil_to_jd(3001, 1, 1, 0.0), last_raw) - 1.0
    assert sorted(engine.FIXED_STAR_RECORDED) == [first, 2086307.5, 2451545.0, last]


def test_the_recorded_values_are_the_shipped_catalogue_s(engine):
    """Read again from the shipped catalogue through the engine's reader."""
    import swisseph
    assert engine["_fixed_star_catalogue_ready"]() is True
    recorded = engine["FIXED_STAR_RECORDED"]
    assert len(recorded) == 4
    for jd in sorted(recorded):
        got = engine["_on_fixed_star_reader"](lambda: {n: engine["swe"].fixstar2_ut(n, jd, swisseph.FLG_MOSEPH)[0][0]
                                                       for n in recorded[jd]})
        assert len(got) == 28
        for name in sorted(got):
            assert abs(got[name] - recorded[jd][name]) <= 1e-9, (jd, name)
