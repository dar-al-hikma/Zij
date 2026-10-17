"""Lane CAL1 (ruling 168 (1)): the date box's help names the late-reform trap.

The app reads a typed date as Gregorian from 1582-10-15, so a date recorded in
the old calendar in a country that reformed later is cast ten to thirteen days
early unless the reader converts it first. The help says so, in the owner's
words. The text is read from the rendered widget, not from the source.
"""
from conftest import make_app


DATE_HELP = (
    "The civil date of birth. Before 1582-10-15 the digits are read as a "
    "Julian-calendar date, as Solar Fire and astro.com read them; from that "
    "day on, Gregorian; type Old Style dates (Britain to 1752, Russia to "
    "1918) in Gregorian. Years before 1000 are typed with their leading "
    "zeros (0787-08-10).")


def test_date_box_help_names_the_late_reform_trap():
    at = make_app()
    at.run()
    boxes = [w for w in at.sidebar.text_input if w.label == "Date (YYYY-MM-DD)"]
    assert len(boxes) == 1, [w.label for w in at.sidebar.text_input]
    assert boxes[0].help == DATE_HELP
