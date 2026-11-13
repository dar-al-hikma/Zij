# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""The colours the page is shown in, once the reader has chosen them.

Streamlit sends both palettes, from its theme options, at the start of every
run, and the page takes the one the computer asks for. One palette written into
both shows it whatever the computer says, with no script on the page. Until a
choice is saved the page opens Light, whatever the computer says; once made, a
choice holds, Light or Dark.

The options belong to the server, not to a session, as the preferences file
does: a choice made in one tab reaches another at that tab's next full run, and
its button and its colours follow together.

A launch shows the saved choice from its first message: hold_the_server
(server_limits.py) calls show_the_saved_choice each time the configuration is
parsed. The word in the file decides nothing but which of the two palettes is
written.
"""
import logging

from streamlit import config

PREFERENCE = "_page_colours"
LIGHT, DARK = "Light", "Dark"
CHOICES = (LIGHT, DARK)
# What each choice is to a picture, as st.context.theme.type would say it.
THEME_TYPE = {LIGHT: "light", DARK: "dark"}

_PALETTES = ("light", "dark")
_PARTS = ("", ".sidebar")
_parsed = None      # each palette's options as the configuration gave them
_showing = None     # the choice in force; None only before the first parse


def showing():
    return _showing


def offered(shown):
    """Where a press goes from colours `shown` (a theme's type, or None when
    the browser has not said): the other of the two."""
    return LIGHT if shown == THEME_TYPE[DARK] else DARK


def show(choice):
    """Write `choice`'s palette into both sections. Anything but Light or Dark
    writes nothing."""
    global _parsed, _showing
    if choice not in CHOICES or choice == _showing:
        return
    if _parsed is None:
        _parsed = {(palette, part): config.get_options_for_section(f"theme.{palette}{part}")
                   for palette in _PALETTES for part in _PARTS}
    for palette in _PALETTES:
        for part in _PARTS:
            for name, value in _parsed[THEME_TYPE[choice], part].items():
                config.set_option(f"theme.{palette}{part}.{name}", value)
    _showing = choice


def _saved_choice():
    """The word the preferences file holds, or None, past the checks a load
    of the file makes first. It reads that one entry, writes nothing itself and
    does not load the engine: an unreadable file is the first run's to deal
    with. Importing the data layer does what the app's first session would do a
    moment later: the data folder is made and a former one moved across, waiting
    on that folder's lock if another program holds it."""
    import user_data

    if not user_data.preferences_enabled() or user_data._not_this_accounts(user_data.PREFERENCES_PATH.parent):
        return None
    saved = user_data._read_preferences_file()
    return saved.get(PREFERENCE) if saved else None


def show_the_saved_choice():
    """The options were just parsed, so they hold the configuration's palettes
    again. With no choice saved the page opens Light. A file that cannot be
    read opens it Light too, and one line says so: the failure's kind alone, no
    path and no value."""
    global _parsed, _showing
    _parsed, _showing = None, None
    try:
        choice = _saved_choice()
    except Exception as error:
        try:
            logging.getLogger(__name__).warning("The saved colours were not read (%s).", type(error).__name__)
        except Exception:
            pass
        choice = None
    show(choice if choice in CHOICES else LIGHT)
