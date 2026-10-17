"""The astronomical core's outputs, pinned: a dozen cases from the move's proof.

The ephemeris and the time zones moved out of engine.py byte for byte
(tests/test_split_astro_2026_10_14.py holds the move). Before the move the
outputs of every function that moved, and of the chart and the app around
them, were hashed over some fifty thousand cases, and the same hashes came out
after it. Twelve of those cases are pinned here, hashed the same way: every
float by float.hex, every container walked, an object by its slots or fields
and its repr, an exception by its type, arguments and attributes. A change
that moves any of these values -- in the moved code or in what calls it --
fails here, and says which case moved.

The hashes are of this machine's Swiss Ephemeris wheel and this Python (the
suite's pins); the chart cases read the library itself, so a new wheel that
moves a value in its last bit moves a hash too.
"""
from __future__ import annotations

import dataclasses
import hashlib
from datetime import datetime

import pytest


def _canon(x):
    if x is None or isinstance(x, bool):
        return repr(x)
    if isinstance(x, float):
        return "f:" + x.hex()
    if isinstance(x, int):
        return "i:" + repr(x)
    if isinstance(x, str):
        return "s:" + repr(x)
    if isinstance(x, (bytes, bytearray)):
        return "b:" + bytes(x).hex()
    if isinstance(x, dict):
        return type(x).__name__ + "{" + ",".join(sorted(_canon(k) + ":" + _canon(v) for k, v in x.items())) + "}"
    if isinstance(x, (list, tuple)):
        return type(x).__name__ + "[" + ",".join(_canon(v) for v in x) + "]"
    if isinstance(x, (set, frozenset)):
        return type(x).__name__ + "{" + ",".join(sorted(_canon(v) for v in x)) + "}"
    if isinstance(x, BaseException):
        return "exc:" + type(x).__name__ + _canon(tuple(x.args)) + _canon(dict(vars(x)))
    name = type(x).__name__
    shown = repr(x) if type(x).__repr__ is not object.__repr__ else "<repr>"
    if dataclasses.is_dataclass(x) and not isinstance(x, type):
        return name + _canon({f.name: getattr(x, f.name) for f in dataclasses.fields(x)})
    slots = [s for klass in type(x).__mro__ for s in (getattr(klass, "__slots__", ()) or ())
             if s not in ("__dict__", "__weakref__")]
    if slots:
        return name + _canon({s: getattr(x, s, "<unset>") for s in dict.fromkeys(slots)}) + shown
    if hasattr(x, "__dict__") and not callable(x):
        return name + _canon(dict(vars(x))) + shown
    return name + ":" + shown


def _digest(fn, E):
    try:
        value = fn(E)
    except Exception as exc:              # a refusal is an output
        value = exc
    return hashlib.sha256(_canon(value).encode("utf-8", "surrogatepass")).hexdigest()


def _zone(E, name, local, lat=None, lon=None):
    kwargs = {} if lat is None else {"latitude": lat, "longitude": lon}
    try:
        return E.named_zone_state(name, *local, **kwargs)
    except E.NamedZoneRefusal as refusal:
        return refusal


CASES = {
    "chart: London 1982-11-15 12:00 GMT": lambda E: E.calculate_traditional_chart_jd(
        E.civil_local_to_jd_ut(1982, 11, 15, 12.0, 0.0), 51.50853, -0.12574),
    "chart: the example, Florence 1240-05-23 14:30 LMT": lambda E: E.calculate_traditional_chart_jd(
        E.civil_local_to_jd_ut(1240, 5, 23, 14.5, 11.2556 / 15.0), 43.7698, 11.2556),
    "chart: the north pole": lambda E: E.calculate_traditional_chart_jd(E.civil_to_jd(2000, 3, 20, 12.0), 90.0, 0.0),
    "chart: just short of the south pole, a reform day": lambda E: E.calculate_traditional_chart_jd(
        E.civil_to_jd(1582, 10, 10, 12.0), -(90 - 1e-6), 45.0),
    "chart: the polar circle at midsummer": lambda E: E.calculate_traditional_chart_jd(
        E.civil_to_jd(2000, 6, 21, 23.75), 66.56, -18.0),
    "calendar: the reform's days and 29 February in both calendars": lambda E: [
        (d, E.civil_calendar(*d), E.civil_is_valid(*d), E.civil_to_jd(*d, 6.5), E.CivilDate(*d).calendar_name())
        for d in [(1582, 10, day) for day in range(4, 17)] + [(1300, 2, 29), (1500, 2, 29), (1600, 2, 29),
                                                               (1700, 2, 29), (1900, 2, 29), (2000, 2, 29)]],
    "calendar: moments, round trips and offsets across midnight": lambda E: [
        (E.CivilMoment.from_jd(jd), E.CivilMoment.from_jd(jd, E.swe.JUL_CAL), E.pn4_datetime_from_jd(jd),
         E.CivilMoment.from_jd(jd).jd(), E.civil_local_to_jd_ut(1300, 2, 29, 0.25, 14.0),
         E.civil_local_to_jd_ut(1300, 3, 1, 23.75, -14.0), E._moment_from_jd_in_calendar(jd, E.swe.GREG_CAL))
        for jd in (1721423.5, 2299160.5 - 0.4 / 86400, 2299160.5, 2451545.0 + 0.6 / 86400, 5373483.5 - 1e-7)],
    "calendar: completed years and birthdays": lambda E: [
        (E.pn4_completed_years(E.CivilDate(*b), E.CivilDate(*t)), E.pn4_birthday(E.CivilDate(*b), age))
        for b, t, age in (((1300, 2, 29), (1301, 2, 28), 1), ((2000, 2, 29), (2001, 3, 1), 1),
                          ((1582, 10, 10), (1583, 10, 19), 1), ((1240, 5, 23), (1283, 5, 23), 43))],
    "zones: a label, a link, a fold, a city and an area": lambda E: [
        _zone(E, "Europe/Paris", (1900, 6, 1, 12, 0, 0)),
        _zone(E, "Europe/Dublin", (1916, 7, 1, 12, 0, 0)),
        _zone(E, "America/Jamaica", (1899, 3, 1, 0, 0, 0)),
        # Stockholm 1950 was the link this case refused; since the pre-1970
        # windows (ruling 82) it is cast in Stockholm's own CET, so the case's
        # hash moved, and Accra 1950, a link with no window, keeps the refusal.
        _zone(E, "Europe/Stockholm", (1950, 6, 1, 12, 0, 0)),
        _zone(E, "Africa/Accra", (1950, 6, 1, 12, 0, 0)),
        _zone(E, "Europe/London", (1982, 10, 24, 1, 30, 0)),
        _zone(E, "Europe/London", (1982, 3, 28, 1, 30, 0)),
        _zone(E, "Europe/Rome", (1870, 6, 1, 12, 0, 0), 45.4375, 12.3358),
        _zone(E, "Europe/Rome", (1880, 6, 1, 12, 0, 0), 38.1157, 13.3615),
        _zone(E, "Europe/Paris", (1915, 6, 1, 12, 0, 0), 48.5734, 7.7521),
        _zone(E, "Africa/Lagos", (1910, 6, 1, 12, 0, 0)),
        _zone(E, "Etc/GMT+2", (1990, 6, 1, 12, 0, 0)),
        _zone(E, "Asia/Calcutta", (1950, 6, 1, 12, 0, 0))],
    "anniversaries: the three standards": lambda E: [
        E.anniversary_moment(birth, years, time_standard=standard, zone_name=zone, utc_offset_hours=offset,
                             latitude=lat, longitude=lon)
        for birth, years, zone, lat, lon in ((E.CivilMoment(1900, 2, 28, 23, 30, 0), 16, "Europe/Dublin", 53.35, -6.26),
                                             (E.CivilMoment(1300, 2, 29, 6, 0, 0), 4, "Europe/Rome", 41.9, 12.5),
                                             (datetime(1983, 11, 19, 10, 30), 40, "Europe/Rome", 43.77, 11.25))
        for standard, offset in (("LMT (Local Mean Time)", lon / 15.0), ("Standard time (named zone)", 0.0),
                                 ("Manual UTC offset", 5.5))],
    "the ephemeris guard: Delta T, the flags, the sentences": lambda E: [
        E._delta_t_table(), E.MOSHIER_FLAGS, E.EPHEMERIS_REFUSAL, E.EPHEMERIS_FOLDER_REFUSAL,
        E._ephemeris_folder_is_safe("/" + "x" * 199), E._ephemeris_folder_is_safe("/" + "x" * 200)],
    "the fixed stars, read from the folder's copy": lambda E: [
        E.fixed_star_longitudes(jd) for jd in (E.civil_to_jd(1240, 5, 23, 12.0), E.civil_to_jd(1982, 11, 15, 12.0))],
}

PINNED = {
    "chart: London 1982-11-15 12:00 GMT": "47c49f783adddaf44b1eefef232ca704fffdb88974ab5be353db5adb2eac89db",
    "chart: the example, Florence 1240-05-23 14:30 LMT": "c47ac4c5275c596dfe336099b3dd20d21b6e95fcad26f37ac1acff3974f7f3b0",
    "chart: the north pole": "b220f3c805c72b0d7dd93313dd401e56fc9be59a41ab7502b7135f63aec70615",
    "chart: just short of the south pole, a reform day": "0d19d6a0b934355fd29b6e51f40d2d6d35d159997a21fe1fd487acb370d84f4e",
    "chart: the polar circle at midsummer": "a19e4fea90ac6d2c016b9615f0744330e5a72edde2428edae07fa69e85073db4",
    "calendar: the reform's days and 29 February in both calendars": "08574a934a6aeaabeb44fac3dd36a44fac9110ddd6f70a775f5930f58bf38827",
    "calendar: moments, round trips and offsets across midnight": "b1913b79b9a8ac6b14fee06dbfe06f2d82a3eb8d2a7c9de0e6a5682a32198162",
    "calendar: completed years and birthdays": "e1df497867fd8d7cf32d90302d03f7b38a01efa82991c9ae5f510c6b3483dbd5",
    "zones: a label, a link, a fold, a city and an area": "2261aa254958a2492e169d667a220533f0f52c30577e4c80ba5c27dc108ae05b",
    "anniversaries: the three standards": "695a7756296b95cf088be53d047ce2e8770e9eba77f4593eef0d894c385f634e",
    "the ephemeris guard: Delta T, the flags, the sentences": "501449c568bdbe2757cfa1a75650412db69d273c4731f40142105d67c859238c",
    "the fixed stars, read from the folder's copy": "b93fbdd3ab70d6c9c951d0b911b9d2b1f9ab8f6b55b7242c963477beeb3e4110",
}


def test_the_sample_names_a_dozen_cases():
    assert len(CASES) == 12 and set(CASES) == set(PINNED)


@pytest.mark.parametrize("case", list(CASES))
def test_the_cores_outputs_are_the_ones_the_move_kept(engine, case):
    import types
    E = types.SimpleNamespace(**engine)
    assert _digest(CASES[case], E) == PINNED[case], case
