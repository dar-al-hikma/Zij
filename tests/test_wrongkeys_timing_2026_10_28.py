"""The year's target keys, held to the wrong-typed-key pass.

A target date that is not text (a number, a list) took every page that draws
the year's target down inside Streamlit's text box, and an Age that is not a
finite number, or is past any age a saved record can hold (text, None, NaN, a
number from 2**31 up), took it down inside the Age box or where the age was
read. A negative age is not dropped: the page reads it as the birth. Each is
dropped before the page reads it, as the sidebar's keys are, and the target
falls back to the one the store keeps. An empty target date is not dropped:
the page refuses it with its own sentence, as before; nor is an age merely
past the ephemeris, which the page names. A target mode outside its options
is dropped too, which was drawn as Date and written back into its store key.
(The True age did not raise; it is held to the drop rule.)
"""
import pytest

from conftest import assert_no_exception, make_app


def _timing(mode, **state):
    at = make_app(date="1240-05-23", page="timing")
    at.session_state["_target_mode"] = mode
    for key, value in state.items():
        at.session_state[key] = value
    return at.run()


@pytest.mark.parametrize("mode, key, value", [
    ("Date", "target_date", 5), ("Date", "target_date", ["1300-01-01"]), ("Date", "target_date", 13000101.0),
    ("Age", "target_age", "5"), ("Age", "target_age", None), ("Age", "target_age", True),
    ("Age", "target_age", 10 ** 400), ("Age", "target_age", float("nan")),
    ("Age", "target_age", 2 ** 31), ("Age", "target_age", 10 ** 12), ("Age", "target_age", 10 ** 16 - 1),
    ("Age", "target_age", 1e15), ("Age", "_target_age", 2 ** 31), ("Age", "_target_age", 10 ** 16 - 1),
    ("Age", "target_age", -(2 ** 31)), ("Age", "_target_age", -(10 ** 16 - 1)),
])
def test_a_wrong_typed_target_key_does_not_raise(mode, key, value):
    at = _timing(mode, **{key: value})
    assert_no_exception(at, f"{key}={value!r}")


def test_an_age_past_the_ephemeris_is_kept_and_named():
    at = _timing("Age", target_age=9999)
    assert_no_exception(at)
    errors = [e.value for e in at.main.error] + [w.value for w in at.main.warning] + [i.value for i in at.main.info]
    assert any("beyond this app's ephemeris" in v for v in errors), errors


@pytest.mark.parametrize("key", ["target_mode", "_target_mode"])
@pytest.mark.parametrize("value", [None, 5, "Neither"])
def test_a_target_mode_outside_its_options_is_not_kept(key, value):
    at = _timing("Date", **{key: value})
    assert_no_exception(at, f"{key}={value!r}")
    assert at.session_state["_target_mode"] == "Date"


def test_a_dropped_target_date_falls_back_to_the_kept_one():
    at = _timing("Date", _target_date="1300-06-01", target_date=5)
    assert_no_exception(at)
    assert at.session_state["target_date"] == "1300-06-01"


@pytest.mark.parametrize("value", ["5", None, float("nan")])
def test_a_dropped_age_falls_back_to_the_kept_one(value):
    at = _timing("Age", _target_age=30, target_age=value)
    assert_no_exception(at, f"target_age={value!r}")
    assert at.session_state["target_age"] == 30


def test_an_empty_target_date_keeps_its_sentence():
    at = _timing("Date", target_date=None)
    assert_no_exception(at)
    errors = [e.value for e in at.main.error]
    assert any(v.startswith("Not a YYYY-MM-DD date; keeping ") for v in errors), errors
