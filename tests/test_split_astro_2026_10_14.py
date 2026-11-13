"""The modules split out of engine.py, and nothing left unreached by a move.

ephemeris.py holds Swiss Ephemeris's private folder and its checks, the
library's one import, the thread guard, the Delta T check, the refusals and
their sentences, `swe`, the Moshier flag, the Streamlit cache clear beside the
flag it reads, and the civil calendar. time_zones.py holds the pinned zone
database's reset, the linked zones, the aliases, the named mean times, the
areas and stretches, NamedZoneRefusal and named_zone_state. user_data.py
holds the data layer: the per-user data folder and its making, the saved
charts' store and its one reader, the recovery copies, the atomic writes, the
locks, the stray temporary files, the old stores and the import mark, and the
preferences' file, read and written. All three are leaves: none imports the
engine or another of them, but for user_data.py's one accessor (_the_engine),
which reaches the engine when it is called, never at import, for what the
preferences mean. engine.py takes them whole, `from ephemeris import *`, `from
time_zones import *` and `from user_data import *` its first statements, and
so re-exports every name they bind but the accessor and those each rebinds as
it runs (split_census.WITHHELD_BY_MODULE: ephemeris.py's _EPHEMERIS_FOLDER and
_DELTA_T_REFERENCE; user_data.py's DATA_DIR_ERROR and its five LAST_*
notices). Through the engine a rebound name would be the value it had at the
engine's import; it is read in its module, and a read through the engine
fails instead.

The previous split's trap (tests/test_engine_split_2026_09_15.py: readings
assigned into a namespace no function read) is a test that replaces a name
in one module while the code that reads it lives in another. So, for each
module split out (NEW):

* the census (tests/split_census.py): every site in the tests, and in every
  script a test hands to a subprocess, that replaces an attribute of the
  engine. A site that replaces a name a new module binds or reads -- the
  standard modules and names it reads among them -- must replace it in that
  module instead, unless that module's ENGINE_OWN lists it with why the
  engine's own binding is the one the test means (app.py, which takes the
  engine whole at every run, calling it). A site whose name is not written in
  it (a variable, a mapping not written out: the census's "<dynamic>") is
  marked too, unless DYNAMIC lists it with the names it takes and no new
  module binds or reads any of them; and so is a site that loads a module the
  census cannot name ("<dynamic module>"), unless DYNAMIC_MODULES lists it
  with the modules it takes;
* no read or write of a withheld name through the engine, in the program,
  the tests or their scripts; and no read through the engine, in a test that
  has replaced a name in a new module, of the name it replaced;
* static: the leaves import neither the engine nor each other (the accessor
  aside), ephemeris.py alone imports swisseph, and engine.py's first
  statements take the three; engine.py and app.py read no withheld name by
  its bare name; engine.py binds no name of a new module again, but by the
  same import; each module's __all__ is every name it binds but the
  withheld, the accessor and a standard module the engine imports itself
  (NOT_EXPORTED); and the moved code is pinned;
* dynamic, in fresh interpreters: each new module imported alone loads
  nothing of the engine (user_data.py making its folder where the
  environment says); the names re-exported, `swe` one object, the star
  import's set; a reload of the engine that keeps the folders and the classes
  and does not empty Streamlit's caches again; a reload and a fresh import of
  ephemeris.py that find the held folder and register no second exit hook;
  the harness's reload (conftest's sync_engine_to_environment), which gives
  the data layer a new folder once the environment has moved, with its
  positive control (the same function with its reload of user_data.py taken
  out keeps the old folder), and a reload of the engine alone, which keeps
  the folder (the accepted difference); and the accessor, which reaches the
  engine's _loadable_preferences as it stands when a load is made;
* no test opens engine.py by name for a name that moved.

markup.py, wheel.py and export_html.py are the pictures and the HTML report,
and are of two kinds. markup.py is a leaf, importing only the standard
library. wheel.py and export_html.py take markup.py's names by import, and
reach whatever they read of the engine's through one accessor when they are
called, never at import; the engine takes the three whole at its end, after
every definition. So beside the rules above: the accessor's rule (it is
called inside a function only, for one attribute of the engine, a name the
module does not bind) and its static form (no bare read of a name engine.py
binds, unless the module binds it itself); and a replacement of a name in
markup.py that wheel.py or export_html.py holds by its import, which reaches
neither of them, is marked unless the same function replaces it where the code
it means reads it. Those three modules' pins (MOVED_CODE) are the move's; the
ones of wheel.py and export_html.py retired when those files took their colours
and faces from the house style.
"""
from __future__ import annotations

import ast
import builtins
import hashlib
import json
import os
import subprocess
import symtable
import sys
from pathlib import Path

import pytest

import split_census
from conftest import EXECUTABLE_DIR, source_files

TESTS = Path(__file__).resolve().parent
NEW = ("ephemeris.py", "time_zones.py", "user_data.py", "markup.py", "wheel.py", "export_html.py")
# The modules that are not leaves: each imports, outside its accessor, the
# standard library and these of the new modules, and no other program module.
TAKES_BY_IMPORT = {"wheel.py": ("markup", "house_style", "saved_faces"), "export_html.py": ("markup", "house_style", "saved_faces")}
# The modules the engine takes last, after every definition, in this order.
TAKEN_LAST = ("markup.py", "wheel.py", "export_html.py")
WITHHELD = split_census.WITHHELD_BY_MODULE
ALL_WITHHELD = split_census.WITHHELD
# A function a new module defines to reach the engine at call time (it imports
# the engine inside it, and is no name the engine takes).
# What a module has gained since its move, which the digest of the moved code leaves out by name.
GAINED_SINCE_THE_MOVE = {"markup.py": ("PAGE_COLUMN_NAMES", "PAGE_CELL_WORDS", "_PAGE_PHRASES", "_PAGE_PHRASE",
                                       "page_words", "page_column", "page_cell")}
ACCESSORS = {"user_data.py": ("_the_engine",), "wheel.py": ("_the_engine",), "export_html.py": ("_the_engine",)}
# A standard module a new module imports and leaves out of its __all__ all
# the same, because engine.py makes the same import itself: errno, which the
# check of the errno names the program reads (test_mac1_platform_names) finds
# only as errno.NAME, never written as a string.
NOT_EXPORTED = {"user_data.py": ("errno",)}
TIMEOUT = 300

# The data layer's names app.py calls through the engine: by the bare name,
# which app.py's `from engine import *` takes from the engine at the top of
# every run of the page, or as engine.X at the moment of the call. A test
# that replaces one of them on the engine and then drives the page reaches
# the page's call; replaced in user_data.py it would not.
_THE_PAGE_CALLS_IT_BY_ITS_STAR_IMPORT = (
    "app.py calls it by its bare name, which its `from engine import *` takes from the engine at every run: the "
    "engine's binding is the one the page the test drives calls (nothing in user_data.py calls it)")
_THE_PAGE_CALLS_IT_THROUGH_THE_ENGINE = (
    "app.py calls engine.remember_preference at the moment of the call: the engine's binding is the one the page "
    "the test drives calls (nothing in user_data.py calls it)")

_THE_PAGE_ASKS_IT_THROUGH_THE_ENGINE = (
    "app.py calls engine.set_aside_notices at every run of the page: the engine's binding is the one the page the "
    "test drives asks (user_data.py's own call, in restore_set_aside, is not reached: the test presses no button)")

_THE_PAGE_PRESSES_IT_THROUGH_THE_ENGINE = (
    "app.py's button calls engine.restore_set_aside at the moment of the press: the engine's binding is the one the "
    "page the test drives calls (nothing in user_data.py calls it)")

# The wheel writers' names, app.py's calls of them: nothing in wheel.py calls
# them, so the engine's binding is the one a page calls.
_THE_PAGE_CALLS_THE_WRITER_BY_ITS_STAR_IMPORT = (
    "app.py calls it by its bare name, which its `from engine import *` takes from the engine at every run: the "
    "engine's binding is the one the page the test drives calls (nothing in wheel.py calls it)")

# Sites that replace, through the engine, a name a new module binds or reads,
# kept as they are, per module: (file, name): why the engine's own binding is
# the one the test means.
ENGINE_OWN = {
    "ephemeris.py": {},
    "time_zones.py": {},
    "user_data.py": {
        ("test_followups_2026_10_05.py", "load_saved_charts"): _THE_PAGE_CALLS_IT_BY_ITS_STAR_IMPORT,
        ("test_followups_2026_10_05.py", "write_saved_charts"): _THE_PAGE_CALLS_IT_BY_ITS_STAR_IMPORT,
        ("test_ks_store_and_preferences_locked_2026_10_06.py", "write_saved_charts"):
            _THE_PAGE_CALLS_IT_BY_ITS_STAR_IMPORT,
        ("test_record_lifecycle_2026_09_16.py", "write_saved_charts"): _THE_PAGE_CALLS_IT_BY_ITS_STAR_IMPORT,
        ("test_sc2_saved_state_2026_10_07.py", "load_saved_charts"): _THE_PAGE_CALLS_IT_BY_ITS_STAR_IMPORT,
        ("test_sc_saved_charts_2026_10_06.py", "remember_preference"): _THE_PAGE_CALLS_IT_THROUGH_THE_ENGINE,
        ("test_set_aside_at_launch_2026_11_11.py", "set_aside_notices"): _THE_PAGE_ASKS_IT_THROUGH_THE_ENGINE,
        ("test_set_aside_at_launch_2026_11_11.py", "restore_set_aside"): _THE_PAGE_PRESSES_IT_THROUGH_THE_ENGINE,
        ("test_wl_wording_2026_10_08.py", "write_saved_charts"): _THE_PAGE_CALLS_IT_BY_ITS_STAR_IMPORT,
    },
    "markup.py": {},
    "wheel.py": {
        ("test_b15_svg_xml_illegal_2026_10_11.py", "generate_hybrid_svg"):
            _THE_PAGE_CALLS_THE_WRITER_BY_ITS_STAR_IMPORT,
        ("test_b15_svg_xml_illegal_2026_10_11.py", "generate_multiwheel_svg"):
            _THE_PAGE_CALLS_THE_WRITER_BY_ITS_STAR_IMPORT,
        ("test_fragment_readings_2026_09_18.py", "generate_hybrid_svg"): _THE_PAGE_CALLS_THE_WRITER_BY_ITS_STAR_IMPORT,
        ("test_h5_wheel_follows_image_2026_10_05.py", "generate_multiwheel_svg"):
            _THE_PAGE_CALLS_THE_WRITER_BY_ITS_STAR_IMPORT,
        ("test_hp03_one_motion_2026_10_03.py", "generate_multiwheel_svg"):
            _THE_PAGE_CALLS_THE_WRITER_BY_ITS_STAR_IMPORT,
        ("test_pw_page_wording_2026_10_06.py", "generate_multiwheel_svg"):
            _THE_PAGE_CALLS_THE_WRITER_BY_ITS_STAR_IMPORT,
    },
    "export_html.py": {},
}

def _accessor_reads(name):
    """Every name a module reads through its accessor, `_the_engine().X`, by
    its source: what the reach test replaces is what the code reads."""
    tree = ast.parse((EXECUTABLE_DIR / name).read_text(encoding="utf-8"))
    return tuple(sorted({n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
                         and isinstance(n.value, ast.Call) and split_census._dotted(n.value.func) == "_the_engine"}))


# Sites on the engine whose name is not written in them ("<dynamic>"), kept:
# (file, the function holding the site, the site's line as written): (every
# name the site is handed, why). Any other such site is marked: nothing tells
# which names it replaces. A listed site is marked as well where a new module
# binds or reads one of its names, unless that module's ENGINE_OWN keeps the
# name for that file, as it does a named site.
DYNAMIC = {
    ("test_b15_svg_xml_illegal_2026_10_11.py", "_page_svgs", "monkeypatch.setattr(module, fn, spy)"):
        (("generate_hybrid_svg", "generate_multiwheel_svg"), "the loop's own two names: the engine's wheel writers"),
    ("test_split_move_2026_11_05.py", "test_each_name_the_accessor_reads_reaches_the_moved_code",
     "monkeypatch.setattr(engine_module, name, seen)"):
        (_accessor_reads("wheel.py") + _accessor_reads("export_html.py"),
         "the reach test's sentinel, handed each name the two modules read through the accessor: replaced on the "
         "engine because that is where the accessor looks"),
}

# Sites that load a module the census cannot name ("<dynamic module>"), kept: (file,
# the function holding the site, the site's line as written): (every module the
# site is handed, why). Any other such site is marked: what it loads may be the
# engine, and nothing tells what is replaced through it.
DYNAMIC_MODULES = {
    ("test_eph1_ephemeris_edges_2026_10_14.py", "<module>", "importlib.import_module(name)"):
        (("ephemeris", "engine"), "the script's fresh import of the two modules, its value dropped: nothing is "
                                  "replaced through it"),
}

# What each new module adds to the text it took from engine.py: its docstring,
# these imports, its accessor (ACCESSORS) and its __all__. The move's commit
# copied the rest byte for byte, but for user_data.py's two calls of the
# engine's _loadable_preferences, which go through the accessor. MOVED_CODE
# pins the rest by ast.dump (comments aside): a later change to moved code
# updates its pin in the same commit and says why.
ADDED_IMPORTS = {"markup.py": {"import html", "import re", "import unicodedata"},
                 "ephemeris.py": {"import streamlit as st", "import math"},
                 "time_zones.py": {"from datetime import datetime, timedelta, timezone", "import json", "import os",
                                   "import zoneinfo", "from zoneinfo import ZoneInfo, ZoneInfoNotFoundError",
                                   "import contextlib", "import sqlite3", "import unicodedata",
                                   "from pathlib import Path"},
                 "user_data.py": {"import errno", "import hashlib", "import json", "import os", "import re",
                                  "import secrets", "import shutil", "import stat", "import sys", "import threading",
                                  "import time as _clock", "from contextlib import contextmanager",
                                  "from dataclasses import dataclass", "from datetime import datetime",
                                  "from pathlib import Path"}}
# ephemeris.py's pin moved when the exit's removal came to find the folder by
# its descriptor where another program moved it (_ephemeris_folder_where),
# and EphemerisRefused's docstring came to name app.py's catch at
# the import; and again when the removal's identity and rmdir came to be made
# through a descriptor on the path's parent (_ephemeris_folder_rmdir).
# time_zones.py's moved when its three outline tables left the
# code for a data file of their own (data/mean_time_outlines.json, read by
# _read_outline_tables, whose own imports json and os are): the names are
# bound from the file now, to the same values. It moved again when the
# pre-1970 windows came in beside LINKED_ZONES (PRE1970_WINDOWS, read by
# _pre1970_state from named_zone_state's linked branch, with timedelta), and
# civil_mean_time_label came to take a window's first moment written out.
# It moved once more when a clipped standard-time window's label came to open
# with its clock, St Thomas's start to follow an order, the AEF note to give
# La Nature's own dates, and four read statuses their reproductions' words.
# And when that label took one form for every such window, "The clock here
# was then {abbreviation}; ...". And when Amsterdam's 1909-1916 window came
# to carry its laws' words, "Amsterdam mean solar time", in place of IANA's
# AMT, in its label, its note and the comment over the labels. And when the
# atlas lookup came in from app.py (_atlas_fold, _like_prefix
# and atlas_rows, the query of _atlas_matches, whose own imports contextlib,
# sqlite3 and unicodedata are), moved as text, app.py keeping the labels and
# the sentences. And when the atlas's rebuild brought the place's zone in
# (place_zone, read with the list data/place_zones.tsv and the area rules,
# with PlaceClockRefusal, its kinds 'clock_choice' and 'unsettled'), and the lookup
# came to open the atlas read-only through a file: URI (pathlib's Path). And
# when the five places no clock record settles were given area rules
# of their own ('golan', 'abu_musa', 'paracels'). And when two more of the
# kind were given theirs ('dhekelia', 'kashmir'). And when the data it reads came
# to be checked against the hashes it
# records (SHIPPED_DATA_SHA256, ZONE_PACKAGES): the two tables at the import
# (_shipped_file_bytes), the atlas at each lookup (_atlas_checked), each zone
# package at its first use (_zone_package_checked, ShippedDataChanged).
# ephemeris.py's moved again when the Delta T reference came to be kept only
# where it is the library's own table, recorded in the code
# (_DELTA_T_RECORDED, _delta_t_as_recorded). And when the folder's name came
# to be judged on Windows in the code page's form the library reads, each
# refusal saying why (_ephemeris_folder_unsafe). time_zones.py's moved again
# when a zone package's data came to be read as importlib.resources gives it,
# through linked folders (zone_package_digest); and when the atlas came to be
# read whole once while its file is unchanged (_ATLAS_SEEN, _atlas_digest);
# and when each zone package came to be imported by its own written name and
# read from its own file's folder, its refusal naming the version the package
# gives, with no submodule of importlib (_zone_package).
# ephemeris.py's moved again when a folder name the code page cannot write
# came to be refused by a class and a sentence of its own
# (EphemerisFolderNameRefused, EPHEMERIS_FOLDER_NAME_REFUSAL); and when that
# sentence came to name an example folder, the whole path and reopening the app.
# user_data.py's is the move's own, moved again when the data
# folder's move from the former name, its folders above, its reads and its
# stray tidy were made as safe as their comments say.
# All three moved again, by their docstrings alone, when the published
# comments and docstrings lost their references to the project's own records
# (the code, docstrings aside, is the same); user_data.py's once more, by its
# docstrings alone, when the last of those references went; and again when
# the store's last versions came to be kept beside it before each write over
# it (_keep_a_version, _new_version, _drop_old_versions); and again when a
# folder under the former name that is another account's came to be neither
# moved, copied nor read (FormerFolderRefused, _read_the_former_folders_store);
# and again when the copy came to publish regular files and folders only
# (_only_files_and_folders, a junction judged as a link); and again when a
# copy that failed in any way came to make no data folder, every copy
# compared whole before it is published (_not_copied_unless_made_since;
# _drop_copies_not_whole gone); and again when a former folder of this
# account's that others could write in came to be carried in only where it
# holds regular files and folders of this account's alone
# (FormerFolderNotCarried, _only_this_accounts_files_and_folders); and again
# when every former folder of this account's came to be judged by its
# entries' owners, whatever its mode (_only_this_accounts_entries); and again
# when a refused one came to get back every mode its narrowing changed; and
# again, by its docstrings alone, when data_folder_state came to name every
# reason a former folder gives; and again when one launch at a time came to
# hold a former folder, by its lock (FormerFolderBusy, _the_former_folder_held);
# and again when one that cannot be read came to say so (FormerFolderUnreadable);
# and again, by a docstring alone, when _the_former_folder_held came to say
# that any account able to read the folder can hold its lock; and again when
# the move came to be bound to the one folder the launch opens, its owner read
# from what was opened, the name looked at again at each step and the copy
# read through descriptors (_move_the_former_folder, _copy_through); and again
# when a copy a killed launch left came to be removed once the folder it
# records it was made from has become the data folder (_record_the_source);
# and again when an earlier version's dead copy came to be judged and removed
# through the descriptor that holds it (_only_a_copy_through); and again when
# the copies came to be compared with the former folder the cleanup judged
# and opened, never its name (_the_former_folder_judged); and again when the
# link at the former name came to be read only while the name led to the link
# found there throughout the read (_read_the_link); and again, by a docstring
# alone, when _remove_through came to say that a folder put at the name after
# its first look is never emptied; and again when that link came to be read
# through a descriptor bound to it, or to the folder above (_read_the_link);
# and again when, on Windows, the owners of the data folder and of the former
# folder came to be read through the system's security calls and the data
# folder given a protected access list (_windows_owner, _ours,
# _windows_close_the_list), a link at the data folder's name came to be
# judged by its own owner, the owner of the former name's link bound came to
# be asked at every look, and an earlier version's dead copy came to be
# compared only where it is this account's and owner-only (_held_copy_is_ours);
# and again when a folder of Administrators' or SYSTEM's whose list grants
# this account nothing, and the folder a copy by name is made in, came to be
# given that list too (_windows_list_names_this_account); and again when that
# dead copy came to be compared where no other account can write in it or in
# anything in it (_none_else_writes); and again when each file in the data
# folder came to be judged by its own owner, at its name and as opened,
# another account's never read, copied or written through (_whose,
# _open_this_accounts_file), and an earlier version's dead copy on macOS came
# to be kept, neither compared nor removed; and again when the Windows copy of
# the former folder came to judge every entry's owner
# (_an_entry_is_not_this_accounts), the former folder's store to be judged by
# its owner on every platform, and the writer to judge again what following the
# name reached; and again when a file the app keeps there that other accounts
# could change came to be replaced with a private copy at each launch
# (_close_what_others_could_write, _replace_if_others_could_write,
# _windows_file_is_writable_by_others, _windows_reset_the_list, the four
# helpers they call moved above the launch), no file the app makes to carry a
# group or other bit, and the first load after to say so ('closed_to_others');
# and again when a cut-short save that other accounts could change came to
# be said so as well, by the load that keeps it aside (_tidy_stray_temp_files,
# _read_the_stray, _others_could_change_the_stray, load_saved_charts), and on
# Windows a copy its folder's list leaves open to others not to be put in
# (_replace_if_others_could_write); and again when such a file came to be set
# aside unread instead, and brought back only by the page's one button
# (_set_aside_what_others_could_write, restore_set_aside), the folder made
# 0700, a link judged by the file it leads to, every copy and one launch
# bounded, and a lock narrowed in place; and again when the folder a junction
# at the data folder's name leads to came to be closed too, one launch's
# bound to hold across the page's retries, a store found in another case to
# be set aside under its own name, a link's two cases to be told apart, a
# clash at the restore to be kept beside the store, a sticky folder to be
# sound, a folder that keeps no modes to be taken as it is, and the writer to
# refuse a link to a file others could change; and again when the data folder
# came to be narrowed and looked at through one descriptor of it, so that a
# folder renamed in at its name between the two is not taken for one that
# keeps no modes; and again when every folder on the way to the data folder
# came to be judged and the folder held for the life of the process, every
# file in it reached through that descriptor, a link at a store's name came
# never to be followed, a refused change of mode (or a list not closed) came
# to refuse the folder, and one press of the restore came to be bounded;
# and again when a folder held that was removed came to be let go, and one
# made at its name again judged and held before it is read; and again when
# the folder under the former name came to be read and moved only through a
# path judged whole, as the data folder's is; and again when a folder its
# group may write came to count as closed only where it carries no access
# list (_carries_an_access_list); and again when a file brought back came to
# take its other set-aside names with it (_its_other_names_removed); and
# again, by a docstring alone, when _read_regular_file's came to say that no
# link at a judged name is followed; and again when the errno names the
# access list's reading needs came to be read with defaults.
# time_zones.py's
# moved again, by its strings and one docstring alone, when the pre-1970
# notes, conflict rows and refusal notes came to say in words what they had
# cited by the numbers of the project's own records. And when a Standard-time
# cast before 1970 away from its zone's named place came to say whose record
# the zone keeps (zone_record_place, with the database's zone1970.tab read
# from the pinned package, _zone1970_places, and _distance_km). And again
# when that sentence came to stay away from a named mean time that was then
# the civil clock, whose own sentence says whose clock it was, and the table
# of named places came to be filled in one step. It moved again, from
# 8f1c9ca171d58d9dad21bf8a91a86ceb98fc3ec5ab23805ed09766fab7d1d56b, when the
# atlas search came to read St., Ste., Ft. and Mt. as their words in any
# form, and a typed region or country after a comma or in brackets
# (ATLAS_WORD_FORMS, ATLAS_COUNTRY_ALIASES, ATLAS_ASCII_LOWER,
# ATLAS_FOLDED_NAMES, _atlas_words, _atlas_begins, _atlas_qualifier,
# _atlas_looks, _atlas_holding, _atlas_prefixes, _atlas_coarse and
# _atlas_looked_up, which atlas_rows hands such a text to; any other text
# is looked up as before). And when the clocks
# particular places kept before 1970 came in from a data file of their own
# (data/place_clocks.tsv, read by _read_place_clocks, each end turned into UT
# by _clock_in_force), with their documents in PRE1970_SOURCES, and
# named_zone_state came to read a reading at such a place in a researched
# year against them alone (_place_clocks_at, _place_clock_state: a disputed
# stretch refused by the place, PlaceClockRefusal 'clock_choice'), and
# zone_record_place to say nothing of the zone's record there; and the fold
# and gap of such a place's own clocks came to carry its name
# (NamedZoneRefusal's place), not the zone's. And when a skipped or repeated
# reading came to state the change it falls in (clock_change, from a place's
# rows, a linked name's windows or the zone's record, and clock_change_words).
# The atlas search's change and the places' clocks were made apart, from the
# same code, and came together in one merge: the pin is of both, from
# 45079174e4542f8a26e5d3b3b74a531a102642f89b379d6427951604b6877786 (the atlas
# search's) and f9e76a6b70c86f47824685054a2e2766f066c4cdfcf09196b31402f955fab180
# (the places' clocks'). It moved again, from
# ddabe152c6130835ba49c93fde66ddd6667fa72f32543c9b4074b9cc1eff82dd, when the
# atlas search came to read short forms of regions and countries: the postal
# abbreviations of Canada's and Australia's regions
# (ATLAS_REGION_ABBREVIATIONS, resolved by _atlas_holding from the atlas's
# own table of regions), initials ("D.C."), "Great Britain" and "Britain"
# among ATLAS_COUNTRY_ALIASES, each of which names its country alone, the
# abbreviation words in a qualifier compared with a name, any trailing
# bracket as one more part unless it is two letters that are a country's
# code (_atlas_qualifier, _atlas_looks), and each look made once, each
# part read as a qualifier once, and the names holding no comma passed over
# where every look still wanted holds one (_atlas_looked_up). It moved
# again, from d676add7189435216071d3f024a5f9c138fe0ef4501b60f4c83138de034ba02f,
# when atlas_rows came to read an atlas whose metadata names search
# version 2 through index ranges over every name a place has and a table
# of the first twenty places for each broad short prefix
# (_atlas_search_matches and the helpers it calls), reading any other atlas
# as before, and when _atlas_holding came to read the country and region
# names in order, skipping any row that names no country. It moved again,
# from ba503679cd35521f84f5ff2194fbf0533d3c7eaa52d670483189feeb3d81bd35, when
# the complete atlas's SHA-256 and the larger zone list's were recorded,
# atlas_rows came to read a file with no metadata table as one naming no
# version and to refuse one naming version 2 without its tables, and
# _atlas_holding came to fold the names once for each file it reads
# (_atlas_file_identity), not once for the recorded hash. It moved again,
# from c94f283af4e3dcc065d9337146e3697278b2de1b92d2b65f8d747502a39adb78, when
# the zone list's SHA-256 was recorded again for its border rows. It moved
# again, from 8e0ece9935dc1e9e55ecb28b30f41bd6d6082f52ec2ca52be73b5dc7f6a4f719,
# when the search came to count only a capital, a seat of government and a
# first-order region's seat as a seat, and the rebuilt atlas's SHA-256 and
# the zone list's were recorded. It moved again, from
# 40067e902d9e25d7773acbfa3f23303240ea154f307f9918239805e62cd7a9c4, when
# atlas_rows came to read the atlas through its indexed search alone,
# refusing a file whose metadata does not name version 2 instead of reading
# it by the earlier lookup, which went with the helpers only it reached
# (_like_prefix, _atlas_coarse, _atlas_prefixes, _atlas_looked_up), and
# _atlas_looks came to say how a text it makes no looks for is searched. It
# moved again, from
# 89fe12f38d05e90df3512b5826d4a51c9d785dca6d37e322ff371593653aef93, when the
# documents of the places with clocks of their own came to be read at import
# from a data file of their own (data/place_clock_sources.tsv, read by
# _read_place_clock_sources into PRE1970_SOURCES, which refuses an id
# written twice or a title in a form PLACE_CLOCK_SOURCE_LOCATOR_FORMS or
# PLACE_CLOCK_SOURCE_BOOKKEEPING_FORMS names), their entries leaving the
# code with nothing in them changed; and when _read_place_clocks came to
# read a file given by its path, to take a place's researched years as the
# years its rows cover, pairing no end, change or stretch's clock across
# years with no rows, to read a disputed row that runs across the end of a
# year, and a disputed stretch's end that meets no row on the first clock
# after it at the place, else the last before it (_stretch_end_clock), each
# cell of the file parsed once; _place_clock_state came to refuse a reading
# between a disputed stretch's local ends, and clock_change to pair only
# rows that meet. It moved again, from
# 7ff850a8950c87d7fc458e2483468fa88219974ccd96d79db13f012652fa0e9f, when
# the two data files came to hold the clocks of every researched place, not
# Minnesota's alone, with their documents: SHIPPED_DATA_SHA256 records the
# two files' new SHA-256, and nothing else in the code changed. It moved
# again, from
# 1c0e6de2993394dd8d7cc4188ba40bcf3b5015a957fc5c66e37b92b2879bfbf1, when
# clock_change came to list no meeting of a place's two clocks with the same
# offset and abbreviation either side as a change, so that a skipped or
# repeated hour whose reach holds a year's rows meeting the next year's on
# one clock is stated as its one change. It moved again, from
# 1c83f789ccfdff69a8ee412e3138696b338d045b16bb7e1b3fe6db9a075249d9, when
# the two data files came to hold the clocks of more researched places,
# with their documents: SHIPPED_DATA_SHA256 records the two files' new
# SHA-256, and nothing else in the code changed.
# ephemeris.py's moved again, from
# f3c0b5a7b56b0f31bc9ba0436a4cec6e77fe8f34c6658342944fbe311a662079, when it
# came to compute the IAU 2006 apparent sidereal time and the true obliquity
# itself, for every date (_sidereal_frame, greenwich_sidereal_time,
# true_obliquity), in place of Swiss Ephemeris's own outside 1850-2050; and
# again, from f1216cbefa8fe8a7d41193e9f20e4ed43e7aea2734e344ecb50e99e1f30a3652,
# when the houses came to be cast from them (chart_houses); and again, from
# a91893b48fe2fbab579ae31aad407e8f94e84f4fe71661d0e596ab90c5633515, when the
# division's status came to stand beside the cusps (division_status and what
# it checks with, WithheldCusps, house_division, the caution's minute); and
# again, from df76fbc0221d7ef842649cc357b7d0b0a9296a040b6fb1463173feebc60029b7,
# when a revolution's moment withheld came to have its own three sentences
# (REVOLUTION_DIVISION_REASONS).
# markup.py's, wheel.py's and export_html.py's are the move's own: the text
# engine.py held, but for the loads of what wheel.py and export_html.py read of
# the engine's, which go through the accessor. wheel.py's and export_html.py's
# retire when those files are rewritten: a pin on code being rewritten proves
# nothing. markup.py's stays.
MOVED_CODE = {"ephemeris.py": "d98ab60bd72219b9d3b4428b5cd1e42c2f2ae3c29129594d6f4a6ee906e179e0",
              "time_zones.py": "f4481911d7fd6f80145230b4ae65576b40e9dfb090b403e62c6f68bd6bdeb85b",
              "user_data.py": "28827c719252d6ab484454de6fda802b37cd0edf68063616da263c76fc0aefd7",
              "markup.py": "c25d3fd531b76ff9d7debd07644cc1f2bc01d35c77baf9febc3c1b44a630026c"}


def _tree(name):
    return ast.parse((EXECUTABLE_DIR / name).read_text(encoding="utf-8"))


def _bound(tree):
    """Every name a module's top level binds, in order, each once (a `del`
    unbinds)."""
    names = []
    for node in tree.body:
        found = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found = [node.name]
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            found = [(a.asname or a.name).split(".")[0] for a in node.names if a.name != "*"]
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.If, ast.Try, ast.With, ast.For)):
            for sub in ast.walk(node):
                targets = sub.targets if isinstance(sub, ast.Assign) else (
                    [sub.target] if isinstance(sub, ast.AnnAssign) else [])
                for target in targets:
                    found += sorted(split_census._targets(target))
        elif isinstance(node, ast.Delete):
            for target in node.targets:
                for n in split_census._targets(target):
                    if n in names:
                        names.remove(n)
        names += [n for n in dict.fromkeys(found) if n not in names]
    return [n for n in names if not n.startswith("__")]


def _reads(name):
    """Every global name a module's code reads (symtable: the module's own
    references and its functions' global ones)."""
    table = symtable.symtable((EXECUTABLE_DIR / name).read_text(encoding="utf-8"), name, "exec")
    out, stack = set(), [table]
    while stack:
        t = stack.pop()
        for sym in t.get_symbols():
            if sym.is_referenced() and (t.get_type() == symtable.SymbolTableType.MODULE or sym.is_global()):
                out.add(sym.get_name())
        stack.extend(t.get_children())
    return out - set(dir(builtins))


def _affected(module=None):
    """The names whose replacement through the engine `module` would not see:
    those it binds or reads (every new module's, when not given)."""
    out = set()
    for name in NEW if module is None else (module,):
        out |= set(_bound(_tree(name))) | _reads(name)
    return out


# The census and this file are not read; nor are the run-time checks' pins, whose strings are planted
# replacements of a stand-in engine, each run in a throwaway copy of the harness, where the tripwire judges it.
CENSUS_UNREAD = ("split_census.py", Path(__file__).name, "test_guard4_runtime_2026_10_20.py")


def _paths():
    return [p for p in sorted(TESTS.rglob("*.py")) if p.name not in CENSUS_UNREAD]


def _census():
    return split_census.census(_paths())


def _dynamic_key(paths, f, line, _texts={}):
    """A "<dynamic>" site's DYNAMIC key: its file, the innermost function
    holding it (or "<module>") and its line as written."""
    path = next(p for p in paths if p.name == f)
    if path not in _texts:
        text = path.read_text(encoding="utf-8")
        _texts[path] = (text.splitlines(), ast.parse(text))
    lines, tree = _texts[path]
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno <= line <= node.end_lineno:
            if best is None or node.lineno > best.lineno:
                best = node
    return f, best.name if best else "<module>", lines[line - 1].strip()


def _marked(sites, paths, affected=None):
    """The census's sites the guard marks: a name a new module binds or reads,
    unless that module's ENGINE_OWN keeps it; a "<dynamic>" one, unless
    DYNAMIC lists it with names no new module binds or reads; a "<dynamic
    module>" one, unless DYNAMIC_MODULES lists it. `affected`, when given,
    stands for every module's names at once, with no ENGINE_OWN."""
    per_module = {"<given>": affected} if affected is not None else {m: _affected(m) for m in NEW}
    out = []
    for row in sites:
        f, line, _where, _form, name = row
        if name == split_census.DYNAMIC_MODULE:
            if _dynamic_key(paths, f, line) not in DYNAMIC_MODULES:
                out.append(row)
        elif name == "<dynamic>":
            listed = DYNAMIC.get(_dynamic_key(paths, f, line))
            if listed is None or any(handed in names and (f, handed) not in ENGINE_OWN.get(module, {})
                                     for module, names in per_module.items() for handed in listed[0]):
                out.append(row)
        elif any(name in names and (f, name) not in ENGINE_OWN.get(module, {})
                 for module, names in per_module.items()):
            out.append(row)
    return out


@pytest.fixture(scope="module")
def census():
    return _census()


# --- the census -------------------------------------------------------------------------------

def test_the_census_finds_the_sites_it_counts(census):
    """The census reaches what it must: replacement sites in test code and in
    scripts, read as Python, as a format template and by grep alike (each
    kind seen at least once), across the suite. (Its floor was 150 sites in
    40 files until the data layer left the engine: the replacements of the
    data layer's names were made in user_data.py from then on, and the census
    counts replacements of the engine only.)"""
    where = {w.split(" ")[0] for _f, _l, w, _form, _n in census["sites"]}
    assert where == {"code", "script"}, where
    assert len(census["sites"]) > 90 and len({f for f, *_ in census["sites"]}) > 35, len(census["sites"])
    methods = {how for per_file in census["methods"].values() for how in per_file}
    assert {"parsed", "formatted", "grepped"} <= methods, methods


def test_no_site_replaces_through_the_engine_a_name_a_new_module_binds_or_reads(census):
    """A test that replaces engine.X, where X is bound in or read by
    ephemeris.py, time_zones.py or user_data.py, no longer reaches the code
    that reads it there: it must replace the module's X (or be in that
    module's ENGINE_OWN, with why)."""
    marked = _marked(census["sites"], _paths())
    assert marked == [], marked


def test_every_site_kept_on_the_engine_is_still_there(census):
    """No stale entry: each ENGINE_OWN site is found, and its name is one its
    module binds or reads (else it needs no entry); each DYNAMIC and
    DYNAMIC_MODULES site is still found as listed."""
    assert set(ENGINE_OWN) == set(NEW), sorted(ENGINE_OWN)
    paths = _paths()
    dynamic = {_dynamic_key(paths, f, line) for f, line, _where, _form, name in census["sites"] if name == "<dynamic>"}
    assert sorted(set(DYNAMIC) - dynamic) == [], sorted(set(DYNAMIC) - dynamic)
    found = {(f, name) for f, _line, _where, _form, name in census["sites"]}
    found |= {(key[0], handed) for key, (names, _why) in DYNAMIC.items() for handed in names}
    stale = [(module, key) for module in NEW for key in ENGINE_OWN[module]
             if key not in found or key[1] not in _affected(module)]
    assert stale == [], stale
    modules = {_dynamic_key(paths, f, line) for f, line, _where, _form, name in census["sites"]
               if name == split_census.DYNAMIC_MODULE}
    assert sorted(set(DYNAMIC_MODULES) - modules) == [], sorted(set(DYNAMIC_MODULES) - modules)


def test_nothing_reads_or_writes_a_withheld_name_through_the_engine(census):
    """In the tests and their scripts (the census), and in the program's own
    modules: no _EPHEMERIS_FOLDER, _DELTA_T_REFERENCE, DATA_DIR_ERROR or LAST_*
    notice through the engine."""
    assert set(WITHHELD) == set(NEW), sorted(WITHHELD)
    assert list(ALL_WITHHELD) == [n for name in NEW for n in WITHHELD[name]], ALL_WITHHELD
    assert census["rebound"] == [], census["rebound"]
    program = [p for p in sorted(EXECUTABLE_DIR.glob("*.py"))]
    hits = [(p.name, row) for p in program for row in split_census.rebound(ast.parse(p.read_text(encoding="utf-8")))]
    assert hits == [], hits


@pytest.mark.parametrize("planted, expected", [
    ("import engine\nengine._EPHEMERIS_FOLDER = '/x'\n", [(2, "store", "_EPHEMERIS_FOLDER")]),
    ("def f(engine):\n    return engine['_DELTA_T_REFERENCE']\n", [(2, "item load", "_DELTA_T_REFERENCE")]),
    ("import importlib\nm = importlib.import_module('engine')\nprint(getattr(m, '_EPHEMERIS_FOLDER', None))\n",
     [(3, "getattr", "_EPHEMERIS_FOLDER")]),
    ("import ephemeris\nprint(ephemeris._EPHEMERIS_FOLDER)\n", []),
    ("engine = object()\nprint(engine._EPHEMERIS_FOLDER)\n", []),
    ("import engine\nassert engine.LAST_STORE_ERROR is None\n", [(2, "load", "LAST_STORE_ERROR")]),
    ("def f(engine):\n    return engine['DATA_DIR_ERROR']\n", [(2, "item load", "DATA_DIR_ERROR")]),
    ("import engine\nprint(getattr(engine, 'LAST_PREFERENCES_BUSY', None))\n",
     [(2, "getattr", "LAST_PREFERENCES_BUSY")]),
    ("import user_data\nprint(user_data.LAST_STORE_UNREADABLE)\n", []),
])
def test_the_rebound_check_reads_each_shape(planted, expected):
    assert split_census.rebound(ast.parse(planted)) == expected


@pytest.mark.parametrize("script, expected", [
    ('code = r"""\nimport engine\nengine._EPHEMERIS_FOLDER = long\n"""\n', "parsed"),
    ('CHILD = """\nimport engine\nsys.path.insert(0, {repo!r})\nengine._EPHEMERIS_FOLDER\n""".format(repo=1)\n',
     "formatted"),
    ('BODY = r"""\n    if mode:\n        return\n    x = engine._EPHEMERIS_FOLDER\n"""\n', "parsed"),
    ('FRAG = "import engine\\nprint([engine._EPHEMERIS_FOLDER,"\n', "grepped"),
])
def test_a_script_handed_to_a_subprocess_is_read_and_its_reads_found(tmp_path, script, expected):
    """Each way of reading a script finds the read it holds."""
    path = tmp_path / "test_planted.py"
    path.write_text(script, encoding="utf-8")
    result = split_census.census([path])
    assert result["methods"] == {"test_planted.py": {expected: 1}}, result["methods"]
    assert [(row[2], row[4]) for row in result["rebound"]] == [(f"script ({expected})", "_EPHEMERIS_FOLDER")], result


@pytest.mark.parametrize("script, expected, name", [
    ('CHILD = """\nimport engine\nprint(engine.LAST_STORE_ERROR)\n"""\n', "parsed", "LAST_STORE_ERROR"),
    ('FRAG = "import engine\\nprint([engine.DATA_DIR_ERROR,"\n', "grepped", "DATA_DIR_ERROR"),
])
def test_a_script_reading_a_data_layer_notice_through_the_engine_is_found(tmp_path, script, expected, name):
    path = tmp_path / "test_planted.py"
    path.write_text(script, encoding="utf-8")
    result = split_census.census([path])
    assert [(row[2], row[4]) for row in result["rebound"]] == [(f"script ({expected})", name)], result


def test_a_replacement_of_a_name_the_zones_read_is_marked():
    """The census's first finding at the move: test_linked_zones replaced the
    engine's ZoneInfo, which named_zone_state no longer reads."""
    planted = ("def test_x(engine, monkeypatch):\n"
               "    monkeypatch.setitem(engine, 'ZoneInfo', None)\n"
               "    import time_zones\n"
               "    monkeypatch.setattr(time_zones, 'ZoneInfo', None)\n")
    found = split_census.sites(ast.parse(planted))
    assert found == [(2, "monkeypatch.setitem", "ZoneInfo")], found
    assert "ZoneInfo" in _affected() and "tempfile" in _affected() and "named_zone_state" in _affected()


@pytest.mark.parametrize("name", ["LOCK_WAIT_SECONDS", "fcntl", "msvcrt", "_LEGACY_SAVED_CHARTS_PATH", "datetime",
                                  "_owner_of", "write_preferences", "load_saved_charts", "secrets", "_clock"])
def test_a_replacement_of_a_data_layer_name_through_the_engine_is_marked(tmp_path, name):
    """The data layer's names, and the standard ones it reads, are marked on
    the engine; the same replacement made on user_data.py is no site at all.
    (load_saved_charts is marked too: only a site ENGINE_OWN lists, in a file
    whose test drives the page, is kept.)"""
    planted = ("import user_data\n"
               "def test_x(engine, monkeypatch):\n"
               f"    monkeypatch.setattr(engine, {name!r}, None)\n"
               f"    monkeypatch.setattr(user_data, {name!r}, None)\n")
    path = tmp_path / "test_planted.py"
    path.write_text(planted, encoding="utf-8")
    sites = split_census.census([path])["sites"]
    assert [(row[1], row[4]) for row in sites] == [(3, name)], sites
    assert [(row[1], row[4]) for row in _marked(sites, [path])] == [(3, name)]
    assert name in _affected("user_data.py")


@pytest.mark.parametrize("planted", [
    "def test_x(engine, monkeypatch):\n    monkeypatch.setattr(engine, '_esc_text', None)\n",
    "from unittest import mock\nimport engine\ndef test_x():\n"
    "    with mock.patch.dict(vars(engine), values={'_esc_text': None}):\n        pass\n",
    "from unittest import mock\nimport engine\ndef test_x():\n"
    "    with mock.patch.multiple(engine, _esc_attr=None):\n        pass\n",
    "def test_x(engine, monkeypatch):\n    monkeypatch.setitem(engine, 'analysis_html', None)\n",
    "def test_x(engine, monkeypatch):\n    monkeypatch.setattr(engine, '_svg_text', None)\n",
])
def test_a_replacement_of_a_moved_name_through_the_engine_is_marked(tmp_path, planted):
    """The pictures' and the report's names, in the forms the census reads:
    replaced on the engine they reach no code in the modules that read them."""
    path = tmp_path / "test_planted.py"
    path.write_text(planted, encoding="utf-8")
    sites = split_census.census([path])["sites"]
    assert sites and _marked(sites, [path]) == sites, sites


def test_a_replacement_of_a_moved_writer_is_kept_for_a_file_that_means_the_pages_call_and_no_other(tmp_path):
    """ENGINE_OWN keeps the wheel writers for the files that drive the page,
    named by the file; the same replacement in any other file is marked."""
    path = tmp_path / "test_planted.py"
    path.write_text("def test_x(engine, monkeypatch):\n    monkeypatch.setattr(engine, 'generate_hybrid_svg', None)\n",
                    encoding="utf-8")
    sites = split_census.census([path])["sites"]
    assert [(row[1], row[4]) for row in _marked(sites, [path])] == [(2, "generate_hybrid_svg")]
    kept = ("test_fragment_readings_2026_09_18.py", "generate_hybrid_svg")
    assert kept in ENGINE_OWN["wheel.py"]
    assert _marked([(kept[0], 2, "code", "monkeypatch.setattr", kept[1])], [path]) == []


def test_a_listed_loop_handed_a_moved_name_its_module_does_not_keep_is_marked(tmp_path, monkeypatch):
    """A DYNAMIC row stands for its names: one of them a moved name that
    ENGINE_OWN does not keep for the file, the listed loop is marked; kept,
    it is not."""
    path = tmp_path / "test_planted.py"
    path.write_text("def run(engine, monkeypatch):\n"
                    "    for fn in ('generate_hybrid_svg', 'generate_multiwheel_svg', 'generate_hit_strip_svg'):\n"
                    "        monkeypatch.setattr(engine, fn, None)\n", encoding="utf-8")
    sites = split_census.census([path])["sites"]
    assert [row[4] for row in sites] == ["<dynamic>"], sites
    key = ("test_planted.py", "run", "monkeypatch.setattr(engine, fn, None)")
    monkeypatch.setitem(DYNAMIC, key, (("generate_hybrid_svg", "generate_multiwheel_svg", "generate_hit_strip_svg"), "plant"))
    assert _marked(sites, [path]) == sites
    own = dict(ENGINE_OWN["wheel.py"])
    own.update({("test_planted.py", n): "plant" for n in DYNAMIC[key][0]})
    monkeypatch.setitem(ENGINE_OWN, "wheel.py", own)
    assert _marked(sites, [path]) == []


# --- a replacement in markup.py, of a name the others hold by their import ---------------------

def _taken_from_markup():
    """{name: the modules that hold it by `from markup import`}."""
    out = {}
    for module in TAKES_BY_IMPORT:
        for node in _tree(module).body:
            if isinstance(node, ast.ImportFrom) and node.module == "markup":
                for alias in node.names:
                    out.setdefault(alias.asname or alias.name, []).append(module)
    return out


def _function_holding(path, line, _trees={}):
    tree = _trees.setdefault(path, ast.parse(Path(path).read_text(encoding="utf-8")))
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.lineno <= line <= node.end_lineno:
            if best is None or node.lineno > best.lineno:
                best = node
    return best.name if best else "<module>"


def _markup_hazards(paths):
    """A replacement of a name in markup.py that wheel.py or export_html.py
    holds by its import reaches neither of them, and neither the census nor
    the tripwire's engine rule sees it: each is returned, unless the same
    function replaces that name where the code it means reads it."""
    by_name = {p.name: p for p in map(Path, paths)}
    taken = _taken_from_markup()
    also = {(row[0], _function_holding(by_name[row[0]], row[1]), row[4])
            for module in TAKES_BY_IMPORT for row in split_census.census_of_module(module[:-len(".py")], paths)}
    return [row for row in split_census.census_of_module("markup", paths)
            if (row[4] in taken or row[4] == "<dynamic>")
            and (row[0], _function_holding(by_name[row[0]], row[1]), row[4]) not in also]


def test_no_test_replaces_in_markup_a_name_the_others_hold_by_their_import():
    assert _markup_hazards(_paths()) == [], _markup_hazards(_paths())


@pytest.mark.parametrize("planted, expected", [
    ("import markup\ndef test_x(monkeypatch):\n    monkeypatch.setattr(markup, '_esc_text', None)\n", [(3, "_esc_text")]),
    ("import markup\ndef test_x():\n    markup._esc_attr = None\n", [(3, "_esc_attr")]),
    ("from unittest import mock\ndef test_x():\n    with mock.patch('markup._isolated', None):\n        pass\n",
     [(3, "_isolated")]),
    ("from unittest import mock\nimport markup\ndef test_x():\n"
     "    with mock.patch.dict(vars(markup), values={'_esc_text': None}):\n        pass\n", [(4, "_esc_text")]),
    ("from unittest import mock\nimport markup\ndef test_x():\n"
     "    with mock.patch.multiple(markup, _esc_attr=None):\n        pass\n", [(4, "_esc_attr")]),
    ("import markup, wheel\ndef test_x(monkeypatch):\n    monkeypatch.setattr(markup, '_esc_text', None)\n"
     "    monkeypatch.setattr(wheel, '_esc_text', None)\n", []),
    ("import markup, wheel\ndef test_x(monkeypatch):\n    monkeypatch.setattr(markup, '_esc_text', None)\n"
     "def test_y(monkeypatch):\n    monkeypatch.setattr(wheel, '_esc_text', None)\n", [(3, "_esc_text")]),
    ("import markup\ndef test_x(monkeypatch):\n    monkeypatch.setattr(markup, '_xml_legal', None)\n", []),
    ("import wheel\ndef test_x(monkeypatch):\n    monkeypatch.setattr(wheel, '_esc_text', None)\n", []),
])
def test_a_replacement_in_markup_is_marked_unless_it_is_also_made_where_the_code_reads_it(tmp_path, planted, expected):
    path = tmp_path / "test_planted.py"
    path.write_text(planted, encoding="utf-8")
    assert [(row[1], row[4]) for row in _markup_hazards([path])] == expected


@pytest.mark.parametrize("planted, expected", [
    ("def test_x(engine, monkeypatch):\n"
     "    for name in ('CivilDate',):\n"
     "        monkeypatch.setattr(engine, name, None)\n", [(3, "monkeypatch.setattr", "<dynamic>")]),
    ("from unittest import mock\n"
     "import engine\n"
     "def test_x():\n"
     "    with mock.patch.dict(engine.__dict__, {'datetime': None}):\n"
     "        pass\n", [(4, "mock.patch.dict", "datetime")]),
    ("from unittest import mock\n"
     "import engine\n"
     "@mock.patch.dict(vars(engine), clear=True)\n"
     "def test_x():\n"
     "    pass\n", [(3, "mock.patch.dict", "<dynamic>")]),
    ("import engine\nvars(engine).update(swe=None)\n", [(2, "update", "swe")]),
    ("import engine\ndef f(saved):\n    engine.__dict__.update(saved)\n", [(3, "update", "<dynamic>")]),
    ("import engine\n"
     "def f(run):\n"
     "    run.__dict__.update({'x': 1})\n"
     "    engine['_RUN'].__dict__.update({'y': 2})\n", []),
])
def test_a_patched_dict_an_updated_namespace_and_a_name_not_written_are_sites_the_guard_marks(tmp_path, planted, expected):
    """mock.patch.dict and .update of the engine's namespace replace every
    name they write; a site whose name is a variable, or a mapping not
    written out, may replace any name, and is marked unless DYNAMIC lists
    it. (An update of something the engine holds is not a site.)"""
    assert split_census.sites(ast.parse(planted)) == expected
    path = tmp_path / "test_planted.py"
    path.write_text(planted, encoding="utf-8")
    marked = _marked(split_census.census([path])["sites"], [path], _affected())
    assert [(row[1], row[4]) for row in marked] == [(line, name) for line, _form, name in expected], marked


def test_the_handle_looks_the_library_s_function_up_at_each_call(monkeypatch):
    """`swe` runs whatever the library module holds at the moment of the call:
    a patch of the library made after a first call through the handle is
    what the next call runs (a handle that kept the function it first found
    would leave every later patch of swisseph dead), and its undo is too."""
    import ephemeris
    assert ephemeris.swe.julday(2000, 1, 1, 12.0) == 2451545.0   # the first call through the handle
    monkeypatch.setattr(ephemeris._swisseph, "julday", lambda *a, **k: ("patched", a))
    assert ephemeris.swe.julday(2000, 1, 1, 12.0) == ("patched", (2000, 1, 1, 12.0))
    monkeypatch.undo()
    assert ephemeris.swe.julday(2000, 1, 1, 12.0) == 2451545.0


def test_the_engine_a_fixture_hands_back_is_the_engine_where_the_test_takes_it():
    """A fixture returning the engine, or a tuple holding it (test_b15's
    `chart`), is the engine in the test that names it."""
    planted = ("import pytest\n"
               "def _made():\n"
               "    import engine as module\n"
               "    return module, 1\n"
               "@pytest.fixture\n"
               "def chart():\n"
               "    return _made()\n"
               "@pytest.fixture\n"
               "def eng_module():\n"
               "    import importlib\n"
               "    return importlib.import_module('engine')\n"
               "def test_x(chart, eng_module, monkeypatch):\n"
               "    module, data = chart\n"
               "    monkeypatch.setattr(module, 'ZoneInfo', None)\n"
               "    monkeypatch.setattr(data, 'x', None)\n"
               "    monkeypatch.setattr(eng_module, 'swe', None)\n")
    assert split_census.sites(ast.parse(planted)) == [(14, "monkeypatch.setattr", "ZoneInfo"),
                                                     (16, "monkeypatch.setattr", "swe")]


def test_a_name_a_function_binds_to_something_else_is_not_the_engine_there():
    planted = ("import sys\n"
               "def a():\n"
               "    module = sys.modules['engine']\n"
               "    module.x = 1\n"
               "def b(spec):\n"
               "    module = make(spec)\n"
               "    module.y = 2\n"
               "    return module\n"
               "def c(monkeypatch):\n"
               "    launcher = b(None)\n"
               "    monkeypatch.setattr(launcher, 'z', 3)\n")
    assert split_census.sites(ast.parse(planted)) == [(4, "assignment", "x")]


# --- a read through the engine after a replacement in a new module -----------------------------

_REPLACERS = ("setattr", "setitem", "delattr", "delitem", "object")


def _new_module_names(tree):
    """The names a file binds to a new module or to its namespace: `import
    user_data [as X]`, `X = sys.modules["user_data"]`, `X =
    importlib.import_module("user_data")`, `X = vars(user_data)`, anywhere in
    the file (a name so bound in one scope counts in every scope, which can
    only find more)."""
    stems = {name[:-len(".py")] for name in NEW}
    out = set()
    for _ in range(3):
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                out |= {a.asname or a.name for a in node.names if a.name in stems}
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                value = node.value
                if isinstance(value, ast.Call) and value.args and (
                        split_census._dotted(value.func).split(".")[-1] == "import_module"
                        and split_census._const(value.args[0]) in stems
                        or split_census._dotted(value.func) == "vars" and isinstance(value.args[0], ast.Name)
                        and value.args[0].id in out):
                    out.add(node.targets[0].id)
                elif isinstance(value, ast.Subscript) and split_census._dotted(value.value) == "sys.modules" \
                        and split_census._const(value.slice) in stems:
                    out.add(node.targets[0].id)
    return out


def _replaced_then_read(tree):
    """(line of the read, name) for each read through the engine, in one
    scope, of a name the same scope replaced earlier in a new module."""
    modules = _new_module_names(tree)
    if not modules:
        return []
    out = []
    for nodes, names, returning in split_census.scopes(tree):
        replaced = {}
        for node in nodes:
            if isinstance(node, ast.Call) and len(node.args) >= 2 and isinstance(node.args[0], ast.Name) \
                    and node.args[0].id in modules \
                    and split_census._dotted(node.func).split(".")[-1] in _REPLACERS \
                    and split_census._const(node.args[1]):
                replaced.setdefault(split_census._const(node.args[1]), node.lineno)
            elif isinstance(node, (ast.Assign, ast.AugAssign)):
                for target in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                    for t in ast.walk(target):
                        if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id in modules:
                            replaced.setdefault(t.attr, t.lineno)
                        elif isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) \
                                and t.value.id in modules and split_census._const(t.slice):
                            replaced.setdefault(split_census._const(t.slice), t.lineno)
        for node in nodes:
            read = None
            if isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load) \
                    and split_census.is_engine(node.value, names, returning):
                read = node.attr
            elif isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) \
                    and split_census.is_engine(node.value, names, returning):
                read = split_census._const(node.slice)
            elif isinstance(node, ast.Call) and len(node.args) >= 2 \
                    and split_census._dotted(node.func).split(".")[-1] == "getattr" \
                    and split_census.is_engine(node.args[0], names, returning):
                read = split_census._const(node.args[1])
            if read in replaced and node.lineno > replaced[read]:
                out.append((node.lineno, read))
    return sorted(set(out))


def test_no_test_reads_through_the_engine_a_name_it_has_replaced_in_a_new_module():
    """After monkeypatch.setattr(user_data, "X", ...), engine.X is the value
    from before the replacement: a test reading it there reads something the
    code under test no longer sees. In test code and in scripts."""
    hits = []
    for path in _paths():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        hits += [(path.name, line, name) for line, name in _replaced_then_read(tree)]
        for start, script in split_census._candidates(tree):
            _how, script_tree = split_census.read_script(script)
            if script_tree is not None:
                hits += [(path.name, start - 1 + line, f"script: {name}")
                         for line, name in _replaced_then_read(script_tree)]
    assert not hits, hits


@pytest.mark.parametrize("planted, expected", [
    ("import user_data\n"
     "def test_x(monkeypatch):\n"
     "    import engine\n"
     "    monkeypatch.setattr(user_data, 'LOCK_WAIT_SECONDS', 0.5)\n"
     "    assert engine.LOCK_WAIT_SECONDS == 0.5\n", [(5, "LOCK_WAIT_SECONDS")]),
    ("import sys\n"
     "def test_x(engine, monkeypatch):\n"
     "    data = sys.modules['user_data']\n"
     "    real = engine['_owner_of']\n"
     "    monkeypatch.setattr(data, '_owner_of', lambda f: 0)\n"
     "    assert engine['_owner_of'] is real\n", [(6, "_owner_of")]),
    ("import engine, user_data\n"
     "def test_x():\n"
     "    user_data.LOCK_WAIT_SECONDS = 0.5\n"
     "    print(getattr(engine, 'LOCK_WAIT_SECONDS'))\n", [(4, "LOCK_WAIT_SECONDS")]),
    ("import user_data\n"
     "def test_x(monkeypatch):\n"
     "    import engine\n"
     "    real = engine._owner_of\n"
     "    monkeypatch.setattr(user_data, '_owner_of', lambda f: 0)\n"
     "    assert user_data._owner_of is not real\n", []),
])
def test_the_read_after_a_replacement_check_reads_each_shape(planted, expected):
    """A read through the engine after the replacement is found; the read made
    before it (the real one kept, to call it) and a read through the module
    are not."""
    assert _replaced_then_read(ast.parse(planted)) == expected


# --- static -----------------------------------------------------------------------------------

def _imported(tree, skip=()):
    """Every module name a tree imports, anywhere in its code, but inside the
    functions named in `skip`."""
    out = set()
    skipped = {id(n) for fn in ast.walk(tree) if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
               and fn.name in skip for n in ast.walk(fn)}
    for node in ast.walk(tree):
        if id(node) in skipped:
            continue
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant) \
                and split_census._dotted(node.func).split(".")[-1] in ("import_module", "__import__"):
            out.add(str(node.args[0].value).split(".")[0])
    return out


def test_the_new_modules_are_leaves_but_for_what_each_takes_by_import():
    """None imports the engine, app.py or another of them, at any level, but
    what TAKES_BY_IMPORT names; the exceptions are the accessors, each a
    function that imports the engine when it is called and nothing else.
    Through user_data.py's alone go that module's two reads of the
    preferences' meaning."""
    stems = {name[:-len(".py")] for name in NEW}
    for name in NEW:
        found = _imported(_tree(name), skip=ACCESSORS.get(name, ()))
        allowed = set(TAKES_BY_IMPORT.get(name, ()))
        assert not found & (({"engine", "app"} | stems - {name[:-len(".py")]}) - allowed), (name, found)
    for name in ("markup.py", *TAKES_BY_IMPORT):
        found = _imported(_tree(name), skip=ACCESSORS.get(name, ()))
        extra = found - set(sys.stdlib_module_names) - set(TAKES_BY_IMPORT.get(name, ()))
        assert not extra, (name, sorted(extra))
    tree = _tree("user_data.py")
    accessors = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ACCESSORS["user_data.py"]]
    assert len(accessors) == 1 and _imported(accessors[0]) == {"engine"}, [ast.unparse(n) for n in accessors]
    through = [n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and isinstance(n.func.value, ast.Call) and split_census._dotted(n.func.value.func) == "_the_engine"]
    assert through == ["_loadable_preferences"] * 3, through          # the load, a write's read, the restore
    assert "_loadable_preferences" not in _bound(tree) and "_loadable_preferences" not in _reads("user_data.py")


@pytest.mark.parametrize("name", sorted(TAKES_BY_IMPORT))
def test_the_accessor_is_called_only_inside_a_function_for_one_name_of_the_engines(name):
    """The accessor's rule. It imports the engine and returns it, and nothing
    else; it is called inside a function, never at the module's import or in
    a default; each call is at once the read of one attribute; and that
    attribute is a name engine.py binds and this module does not, so that the
    object the engine holds then is the one used. The accessor is no name the
    census takes for the engine itself."""
    tree = _tree(name)
    assert not set(ACCESSORS[name]) & split_census.ENGINE_NAMES
    accessor = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_the_engine")
    assert [ast.unparse(s) for s in accessor.body[1:]] == ["import engine", "return engine"]
    assert accessor.args.args == [] and not accessor.decorator_list
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and split_census._dotted(n.func) == "_the_engine"]
    reads = {id(n.value): n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert calls and all(id(call) in reads for call in calls), [ast.unparse(c) for c in calls if id(c) not in reads]
    engine_binds = set(_bound(_tree("engine.py"))) | set(_star_imported_by_the_engine_first())
    own = set(_bound(tree))
    assert sorted(set(reads[id(c)] for c in calls) - engine_binds) == []
    assert sorted(set(reads[id(c)] for c in calls) & own) == []
    inside = {id(sub) for fn in tree.body if isinstance(fn, ast.FunctionDef) and fn.name != "_the_engine"
              for stmt in fn.body for sub in ast.walk(stmt)}
    assert [ast.unparse(c) for c in calls if id(c) not in inside] == []
    # Nothing else names the accessor: it is no value handed about or kept.
    named = [n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "_the_engine"]
    assert len(named) == len(calls), [ast.unparse(n) for n in named]


def _star_imported_by_the_engine_first():
    """The names the engine holds from the modules it takes first."""
    return [n for name in NEW if name not in TAKEN_LAST for n in _bound(_tree(name))]


def test_the_tripwire_watches_the_engine_and_every_new_module():
    """A module left out is one whose replacements nothing sees at run time."""
    import conftest

    assert set(conftest.WATCHED) == {"engine"} | {name[:-len(".py")] for name in NEW}, conftest.WATCHED
    assert set(conftest.TOLD) == {name[:-len(".py")] for name in TAKEN_LAST}, conftest.TOLD


@pytest.mark.parametrize("name", sorted(TAKES_BY_IMPORT))
def test_no_bare_read_of_a_name_the_engine_binds_but_the_module_binds_it_itself(name):
    """The static form of the accessor's rule: a bare name would be a name
    error, or, where it comes by a `from engine import`, the object the
    engine held at the import, which a replacement never reaches."""
    module = set(_bound(_tree(name)))
    engine_binds = set(_bound(_tree("engine.py"))) | set(_star_imported_by_the_engine_first())
    assert sorted((_reads(name) & engine_binds) - module) == []
    # And a read that names nothing at all, on a branch no run reaches.
    assert sorted(_reads(name) - module) == []


def test_the_engine_takes_the_pictures_and_the_report_after_every_definition():
    """The three star imports are the last statements but `__all__`, in the
    list's order, so nothing the engine defines runs before they are taken,
    and `__all__`, read from the namespace, holds what they bring."""
    engine = _tree("engine.py")
    tail = [ast.unparse(n) for n in engine.body[-4:]]
    assert tail[:3] == ["from markup import *", "from wheel import *", "from export_html import *"], tail
    assert tail[3].startswith("__all__ = "), tail
    names = [p.name for p in source_files()]
    assert names[names.index("engine.py"):] == ["engine.py", *TAKEN_LAST, "sky.py", "app.py"], names


def test_the_engine_reads_the_moved_names_only_when_called():
    """What the rest of engine.py reads of the moved names it reads inside a
    function: at the engine's import they are not bound yet."""
    engine = _tree("engine.py")
    moved = {n for name in TAKEN_LAST for n in _bound(_tree(name))
             if n not in {"html", "re", "unicodedata", "math", "json"}}
    at_import = []
    for node in engine.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        at_import += [(sub.lineno, sub.id) for sub in ast.walk(node)
                      if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load) and sub.id in moved]
    assert not at_import, at_import


def test_ephemeris_py_alone_loads_the_library_and_the_engine_takes_the_new_modules_first():
    program = {p.name: ast.parse(p.read_text(encoding="utf-8")) for p in sorted(EXECUTABLE_DIR.glob("*.py"))}
    loaders = sorted(name for name, tree in program.items() if "swisseph" in _imported(tree))
    assert loaders == ["ephemeris.py"], loaders
    engine = program["engine.py"]
    body = engine.body[1:] if ast.get_docstring(engine) else engine.body
    assert [ast.unparse(n) for n in body[:3]] == ["from ephemeris import *", "from time_zones import *",
                                                  "from user_data import *"], [ast.unparse(n) for n in body[:4]]
    listed = [p.name for p in source_files()]
    assert set(NEW) <= set(listed) and listed.index("user_data.py") < listed.index("engine.py"), listed
    assert not {"markup", "wheel", "export_html"} & _imported(ast.Module(body=engine.body[:-4], type_ignores=[])), \
        "the engine takes them at its end, by the star import alone"


def test_the_engine_and_the_app_read_no_withheld_name_by_its_bare_name():
    for name in ("engine.py", "app.py"):
        bare = [(node.lineno, node.id) for node in ast.walk(_tree(name))
                if isinstance(node, ast.Name) and node.id in ALL_WITHHELD]
        bare += [(node.lineno, n) for node in ast.walk(_tree(name)) if isinstance(node, (ast.Global, ast.Nonlocal))
                 for n in node.names if n in ALL_WITHHELD]
        assert bare == [], (name, bare)


def _bindings(tree):
    """{name: what binds it} for a module's top level: an import's dotted
    source ("os", "datetime.datetime", "time" for `import time as _clock`),
    or "<bound here>" for a definition or an assignment."""
    out = {}
    for node in tree.body:
        for sub in ast.walk(node) if isinstance(node, (ast.If, ast.Try)) else [node]:
            if isinstance(sub, ast.Import):
                for a in sub.names:
                    out.setdefault(a.asname or a.name.split(".")[0], a.name if a.asname else a.name.split(".")[0])
            elif isinstance(sub, ast.ImportFrom) and sub.module:
                for a in sub.names:
                    if a.name != "*":
                        out.setdefault(a.asname or a.name, f"{sub.module}.{a.name}")
    for name in _bound(tree):
        out.setdefault(name, "<bound here>")
    return out


@pytest.mark.parametrize("name", NEW)
def test_the_engine_binds_no_name_of_a_new_module_again(name):
    """A name a new module binds and engine.py binds again after its star
    import is the engine's own, not the one the module's code reads: only
    the same import (`import os` in both) is made in both."""
    module, engine = _bindings(_tree(name)), _bindings(_tree("engine.py"))
    again = sorted(n for n in set(module) & set(engine) if module[n] != engine[n] or engine[n] == "<bound here>")
    assert again == [], [(n, module[n], engine[n]) for n in again]


@pytest.mark.parametrize("name", NEW)
def test_each_modules_all_is_every_name_it_binds_but_the_withheld(name):
    tree = _tree(name)
    alls = [n for n in tree.body if isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == ["__all__"]]
    assert len(alls) == 1, alls
    listed = ast.literal_eval(alls[0].value)
    assert isinstance(listed, list) and len(listed) == len(set(listed)), listed
    left_out = set(WITHHELD[name]) | set(ACCESSORS.get(name, ())) | set(NOT_EXPORTED.get(name, ()))
    expected = [n for n in _bound(tree) if n not in left_out]
    assert sorted(listed) == sorted(expected), (sorted(set(expected) - set(listed)), sorted(set(listed) - set(expected)))
    assert not set(listed) & left_out


def test_the_standard_module_left_out_of_an_all_is_one_the_engine_imports_itself():
    """errno, out of user_data.py's __all__, is still the engine's, by the
    same import: the star import loses nothing by it."""
    left = [(name, n, _bindings(_tree(name))[n]) for name, names in NOT_EXPORTED.items() for n in names]
    assert left == [("user_data.py", "errno", "errno")], left
    assert [_bindings(_tree("engine.py")).get(n) for _name, n, _source in left] == ["errno"]


@pytest.mark.parametrize("name", sorted(MOVED_CODE))
def test_the_moved_code_is_the_code_engine_py_held(name):
    """The moved code, by ast.dump (so comments aside): what the move's
    commit took from engine.py byte for byte, less only the module's
    docstring, its own imports, its accessor, its __all__ and what it has gained since."""
    tree = _tree(name)
    body = tree.body[1:] if ast.get_docstring(tree) else tree.body
    own = [ast.unparse(n) for n in body if ast.unparse(n) in ADDED_IMPORTS[name]]
    assert sorted(own) == sorted(ADDED_IMPORTS[name]), own
    moved = [n for n in body if ast.unparse(n) not in ADDED_IMPORTS[name]
             and not (isinstance(n, ast.Assign) and [ast.unparse(t) for t in n.targets] == ["__all__"])
             and not (isinstance(n, ast.FunctionDef) and n.name in ACCESSORS.get(name, ()))
             and not (isinstance(n, ast.FunctionDef) and n.name in GAINED_SINCE_THE_MOVE.get(name, ()))
             and not (isinstance(n, ast.Assign) and {ast.unparse(t) for t in n.targets} & set(GAINED_SINCE_THE_MOVE.get(name, ())))]
    digest = hashlib.sha256("\n".join(ast.dump(n) for n in moved).encode("utf-8")).hexdigest()
    assert digest == MOVED_CODE[name], (name, digest)


def test_no_test_opens_engine_py_by_name_for_a_name_that_moved():
    """A scan of engine.py's text or tree by its name (ENGINE_PATH, a path
    ending "engine.py") for a name that now lives in a new module would read
    nothing, and pass or fail for that alone: such scans read the modules
    source_modules.txt names (conftest's source_files and engine_files)."""
    moved = set()
    for name in NEW:
        tree = _tree(name)
        imported = {n for n, source in _bindings(tree).items() if source != "<bound here>"}
        moved |= {n for n in _bound(tree) if n not in _imported(tree) and n not in imported
                  and n not in {"st", "datetime", "timezone", "ZoneInfo", "ZoneInfoNotFoundError"}}
    assert {"SAVED_CHARTS_PATH", "_write_text_atomically", "_keep_the_data_folder_ours", "named_zone_state"} <= moved
    import re
    rx = re.compile(r"\b(" + "|".join(sorted(map(re.escape, moved), key=len, reverse=True)) + r")\b")

    def opens_engine_by_name(fn):
        for n in ast.walk(fn):
            if isinstance(n, ast.Name) and n.id == "ENGINE_PATH":
                return True
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Div) and isinstance(n.right, ast.Constant) \
                    and n.right.value == "engine.py":
                return True
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "open" \
                    and any(isinstance(a, ast.Constant) and str(a.value).endswith("engine.py") for a in n.args):
                return True
        return False

    def scans():
        for path in sorted(TESTS.glob("test_*.py")):
            for fn in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and opens_engine_by_name(fn):
                    hits = sorted({m.group(1) for n in ast.walk(fn) if isinstance(n, ast.Constant)
                                   and isinstance(n.value, str) for m in rx.finditer(n.value)})
                    if hits:
                        yield path.name, fn.name, hits

    scanning_for_moved_names = list(scans())
    assert not scanning_for_moved_names, scanning_for_moved_names


# --- dynamic ----------------------------------------------------------------------------------

def _run(code, tmp_path, *args, environment=None):
    """`code` in a fresh interpreter, its data folder's variables under
    `tmp_path` (and `environment` over them); the last "OUT " line, read."""
    env = {k: v for k, v in os.environ.items() if k != "SE_EPHE_PATH"}
    env["PYTHONPATH"] = str(EXECUTABLE_DIR)
    env["XDG_DATA_HOME"] = str(tmp_path / "xdg")
    env["APPDATA"] = str(tmp_path / "appdata")
    env.update(environment or {})
    done = subprocess.run([sys.executable, "-c", code, *args], cwd=tmp_path, env=env, capture_output=True, text=True,
                          timeout=TIMEOUT)
    lines = [ln for ln in done.stdout.splitlines() if ln.startswith("OUT ")]
    assert done.returncode == 0 and lines, done.stderr[-3000:]
    return json.loads(lines[-1][len("OUT "):])


_LEAVES = r"""
import json, sys
out = {}
import time_zones
out["time_zones_alone"] = sorted(m for m in ("engine", "ephemeris", "swisseph", "app", "user_data") if m in sys.modules)
import ephemeris
out["ephemeris_then"] = sorted(m for m in ("engine", "app", "user_data") if m in sys.modules)
print("OUT " + json.dumps(out))
"""


def test_each_new_module_imports_alone_and_loads_nothing_of_the_engine(tmp_path):
    out = _run(_LEAVES, tmp_path)
    assert out == {"time_zones_alone": [], "ephemeris_then": []}, out


_FIRST = r"""
import json, sys
name = sys.argv[1]
__import__(name)
alone = sorted(m for m in ("engine", "ephemeris", "time_zones", "user_data", "swisseph", "streamlit", "pandas", "app",
                           "markup", "wheel", "export_html") if m in sys.modules)
import engine
print("OUT " + json.dumps({"alone": alone, "bound": getattr(sys.modules[name], "__all__")[-1] in vars(engine)}))
"""


@pytest.mark.parametrize("name, loads", [("markup", ["markup"]), ("wheel", ["markup", "wheel"]),
                                         ("export_html", ["export_html", "markup"])])
def test_each_picture_module_imported_first_loads_no_engine_and_the_engine_then_takes_it(tmp_path, name, loads):
    assert _run(_FIRST, tmp_path, name) == {"alone": loads, "bound": True}


_DATA_ALONE = r"""
import json, os, stat, sys
import user_data
out = {"loaded": sorted(m for m in ("engine", "ephemeris", "time_zones", "swisseph", "streamlit", "pandas", "app")
                        if m in sys.modules),
       "folder": str(user_data.DATA_DIR), "error": user_data.DATA_DIR_ERROR,
       "mode": oct(stat.S_IMODE(os.stat(user_data.DATA_DIR).st_mode)),
       "paths": [str(user_data.SAVED_CHARTS_PATH), str(user_data.PREFERENCES_PATH)]}
print("OUT " + json.dumps(out))
"""


def test_user_data_imported_alone_loads_nothing_of_the_engine_and_makes_its_folder_where_it_is_told(tmp_path):
    out = _run(_DATA_ALONE, tmp_path)
    folder = tmp_path / "xdg" / "Zij"
    assert out == {"loaded": [], "folder": str(folder), "error": None, "mode": "0o700",
                   "paths": [str(folder / "saved_charts.json"), str(folder / "preferences.json")]}, out


_REEXPORT = r"""
import atexit, importlib, json, sys
registered = []
_register = atexit.register
def watched(fn, *a, **k):
    if getattr(fn, "__name__", "") == "_ephemeris_folder_remove":
        registered.append(a[0])
    return _register(fn, *a, **k)
atexit.register = watched
import ephemeris
import time_zones
import user_data
import engine
import markup
import wheel
import export_html
out = {}
missing = []
for module in (ephemeris, time_zones, user_data, markup, wheel, export_html):
    for name in module.__all__:
        if getattr(engine, name, missing) is not getattr(module, name):
            missing.append(module.__name__ + "." + name)
out["not_re_exported"] = missing
out["withheld_in_engine"] = sorted(n for n in json.loads(sys.argv[1]) if n in vars(engine))
out["accessor_in_engine"] = "_the_engine" in vars(engine)
out["swe_one"] = engine.swe is ephemeris.swe and isinstance(engine.swe, ephemeris._SwissEphemeris)
namespace = {}
exec("from engine import *", namespace)
out["star"] = sorted(n for n in namespace if n != "__builtins__")
folder = ephemeris._EPHEMERIS_FOLDER
data_folder = user_data.DATA_DIR
classes = ("EphemerisRefused", "EphemerisFolderRefused", "NamedZoneRefusal", "CivilDate", "CivilMoment",
           "_SwissEphemeris", "DataFolderRefused", "NotAPlainFile", "DataLockBusy", "DataLockBlocked",
           "DataLockUnavailable", "StoreAsItStands")
before = {name: getattr(engine, name) for name in classes}
own = engine.UnresolvedResult
engine = importlib.reload(engine)
out["engine_reload"] = {"folder": ephemeris._EPHEMERIS_FOLDER == folder,
                        "data_folder": engine.DATA_DIR == data_folder == user_data.DATA_DIR,
                        "classes": [getattr(engine, name) is before[name] for name in classes],
                        "swe": engine.swe is ephemeris.swe,
                        "ran": engine.UnresolvedResult is not own}
held = ephemeris._EPHEMERIS_HELD
ephemeris = importlib.reload(ephemeris)
out["ephemeris_reload"] = {"folder": ephemeris._EPHEMERIS_FOLDER == folder, "held": ephemeris._EPHEMERIS_HELD is held}
del sys.modules["ephemeris"]
import ephemeris
out["ephemeris_fresh"] = {"folder": ephemeris._EPHEMERIS_FOLDER == folder, "held": ephemeris._EPHEMERIS_HELD is held}
out["registered"] = [r == folder for r in registered]
print("OUT " + json.dumps(out))
"""


@pytest.fixture(scope="module")
def reexport(tmp_path_factory):
    return _run(_REEXPORT, tmp_path_factory.mktemp("reexport"), json.dumps(ALL_WITHHELD))


def test_every_name_the_new_modules_export_is_the_engines_and_swe_is_one_object(reexport):
    assert reexport["not_re_exported"] == [] and reexport["swe_one"] is True, reexport
    assert reexport["withheld_in_engine"] == [] and reexport["accessor_in_engine"] is False, reexport


def test_the_star_import_gives_the_engines_own_names_and_the_new_modules_less_the_withheld(reexport):
    """`from engine import *` (app.py's): the names engine.py binds, every
    name the new modules bind but the withheld and the accessor (the standard
    modules only they import, atexit, struct, tempfile, fcntl and msvcrt,
    among them), and the module name `ephemeris` the star reader reads the
    folder through."""
    star = set(reexport["star"])
    engine_own = set(_bound(_tree("engine.py")))
    new = {n for name in NEW for n in _bound(_tree(name))
           if n not in WITHHELD[name] and n not in ACCESSORS.get(name, ())}
    assert star == engine_own | new, (sorted((engine_own | new) - star), sorted(star - engine_own - new))
    assert {"atexit", "struct", "tempfile", "ephemeris", "swe", "named_zone_state", "CivilDate", "fcntl", "msvcrt",
            "_clock", "DATA_DIR", "load_saved_charts", "_user_data_dir", "DataLockBusy"} <= star
    assert not star & (set(ALL_WITHHELD) | {"_the_engine", "time_zones", "user_data", "markup", "wheel", "export_html"})
    assert {"generate_hybrid_svg", "_esc_text", "_isolated", "analysis_html", "_export_cell", "WHEEL_LAYOUT_OPTIONS",
            "_ASPECT_GLYPH", "_wheel_palette"} <= star


def test_a_reload_of_the_engine_keeps_the_folders_and_the_classes(reexport):
    """For the data layer this is an accepted difference:
    a reload of the engine alone (Streamlit's watcher, in development) re-runs
    its star import against the modules already loaded, so the data folder,
    the paths and the classes are the ones the data layer made at its own
    import. A class the engine defines itself is a new one after the
    reload, which shows the reload ran."""
    assert reexport["engine_reload"] == {"folder": True, "data_folder": True, "classes": [True] * 12,
                                         "swe": True, "ran": True}, reexport["engine_reload"]


def test_a_reload_and_a_fresh_import_of_ephemeris_find_the_held_folder_and_register_no_second_hook(reexport):
    assert reexport["ephemeris_reload"] == reexport["ephemeris_fresh"] == {"folder": True, "held": True}, reexport
    assert reexport["registered"] == [True], reexport["registered"]


_CACHES = r"""
import importlib, json, sys, warnings
warnings.simplefilter("ignore")
import swisseph                                   # the library loaded before the folder: the flag is set
import streamlit as st
calls = []
@st.cache_data
def cached(x):
    calls.append(x)
    return x
out = []
cached(1); cached(1); out.append(len(calls))      # 1: cached
import ephemeris                                  # empties the caches, once
cached(1); out.append(len(calls))                 # 2
import engine                                     # does not
cached(1); out.append(len(calls))                 # 2
importlib.reload(engine)                          # nor does its reload
cached(1); out.append(len(calls))                 # 2
print("OUT " + json.dumps([out, ephemeris._EPHEMERIS_LOADED_FIRST]))
"""


def test_the_caches_are_emptied_once_when_ephemeris_loads_and_not_again_by_the_engine(tmp_path):
    """The cache clear moved with the flag it reads: importing ephemeris.py
    after swisseph empties Streamlit's caches once; importing the engine and
    reloading it do not empty them again."""
    counts, flag = _run(_CACHES, tmp_path)
    assert flag is True and counts == [1, 2, 2, 2], counts


# The harness's reload, in a fresh interpreter that is a test's own child (so
# conftest keeps the data folder the child is given): the engine loaded under
# one folder, the environment moved to another, then the reload `how` makes:
# "harness", conftest's sync_engine_to_environment itself; "control", the same
# function with its reload of user_data.py taken out (rebuilt from conftest's
# own text, so that it is what the harness would be without that reload);
# "engine", importlib.reload of the engine alone.
_HARNESS_RELOAD = r"""
import ast, importlib, json, os, sys
how, first, second = sys.argv[1], sys.argv[2], sys.argv[3]
import conftest
assert os.environ["XDG_DATA_HOME"] == first, os.environ["XDG_DATA_HOME"]
import engine, user_data
before = {"engine": str(engine.DATA_DIR), "data": str(user_data.DATA_DIR)}
busy = engine.DataLockBusy
own = engine.UnresolvedResult
engine._harness_environment = tuple(os.environ.get(n) for n in conftest._ENGINE_ENVIRONMENT)
os.environ["XDG_DATA_HOME"] = second
if how == "harness":
    conftest.sync_engine_to_environment()
elif how == "control":
    source = open(conftest.__file__, encoding="utf-8").read()
    fn = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)
              and n.name == "sync_engine_to_environment")
    kept = [s for s in fn.body if "user_data" not in ast.unparse(s)]
    assert len(kept) == len(fn.body) - 1, [ast.unparse(s) for s in fn.body]
    fn.body = kept
    namespace = dict(vars(conftest))
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "control", "exec"), namespace)
    namespace["sync_engine_to_environment"]()
else:
    importlib.reload(engine)
engine = sys.modules["engine"]
out = {"before": before, "engine": str(engine.DATA_DIR), "data": str(user_data.DATA_DIR),
       "made": os.path.isdir(os.path.join(second, "Zij")),
       "classes_new": engine.DataLockBusy is not busy, "classes_one": engine.DataLockBusy is user_data.DataLockBusy,
       "ran": engine.UnresolvedResult is not own,
       "paths": [str(engine.SAVED_CHARTS_PATH), str(user_data.PREFERENCES_PATH)]}
print("OUT " + json.dumps(out))
"""


def _harness_reload(tmp_path, how):
    first, second = tmp_path / "first", tmp_path / "second"
    out = _run(_HARNESS_RELOAD, tmp_path, how, str(first), str(second),
               environment={"XDG_DATA_HOME": str(first), "PYTHONPATH": str(EXECUTABLE_DIR) + os.pathsep + str(TESTS)})
    return first / "Zij", second / "Zij", out


def test_the_harness_reload_gives_the_data_layer_the_folder_the_environment_moved_to(tmp_path):
    """The data layer resolves its folder at its own import,
    so the harness reloads it before the engine; after XDG_DATA_HOME moves,
    the engine and the module hold the new folder, made, and new classes."""
    first, second, out = _harness_reload(tmp_path, "harness")
    assert out["before"] == {"engine": str(first), "data": str(first)}, out
    assert (out["engine"], out["data"], out["made"]) == (str(second), str(second), True), out
    assert out["classes_new"] and out["classes_one"], out
    assert out["paths"] == [str(second / "saved_charts.json"), str(second / "preferences.json")], out


def test_the_harness_reload_without_its_reload_of_user_data_keeps_the_old_folder(tmp_path):
    """The positive control of the test above: conftest's own function, its
    reload of user_data.py taken out, leaves the engine and the module on the
    first environment's folder, makes nothing under the second, and keeps the
    classes; so the test above fails if the harness loses that reload."""
    first, second, out = _harness_reload(tmp_path, "control")
    assert (out["engine"], out["data"], out["made"]) == (str(first), str(first), False), out
    assert not out["classes_new"] and out["classes_one"], out


def test_a_reload_of_the_engine_alone_keeps_the_folder(tmp_path):
    """The accepted difference: a reload of the engine alone
    -- Streamlit's watcher, in development -- re-runs the engine's star import
    against the data layer already loaded, and the folder is not resolved
    again. The served app's environment is fixed for its life, so it never
    needs to be. The engine's own class is a new one after it, which shows
    the reload ran; the data layer's are the ones it had."""
    first, second, out = _harness_reload(tmp_path, "engine")
    assert (out["engine"], out["data"], out["made"]) == (str(first), str(first), False), out
    assert out["ran"] and not out["classes_new"] and out["classes_one"], out


_ACCESSOR = r"""
import json, sys
import engine, user_data
user_data.PREFERENCES_PATH.write_text(json.dumps({"last_chart": "A", "_wheel_dark": True, "junk": 1}))
seen = []
real = engine._loadable_preferences
out = {"real": user_data.load_preferences()}
def replaced(raw):
    seen.append(sorted(raw))
    return {"replaced": True}
engine._loadable_preferences = replaced
out["replaced"] = user_data.load_preferences()
out["stands"] = list(user_data._preferences_as_they_stand())
out["seen"] = seen
out["module_holds_none"] = "_loadable_preferences" not in vars(user_data)
engine._loadable_preferences = real
out["restored"] = user_data.load_preferences()
print("OUT " + json.dumps(out))
"""


def test_the_accessor_reaches_the_engines_loadable_preferences_as_it_stands_at_the_call(tmp_path):
    """The preferences' meaning stays in the engine: the
    data layer's load and its read before a write ask the engine, at each
    call, which entries are kept, so a replacement of the engine's
    _loadable_preferences is the one used, and its undo too."""
    out = _run(_ACCESSOR, tmp_path, environment={"ALMUTEN_NO_PREFERENCES": "0"})
    kept = {"last_chart": "A", "_wheel_dark": True}
    assert out == {"real": kept, "replaced": {"replaced": True}, "stands": [{"replaced": True}, True],
                   "seen": [["_wheel_dark", "junk", "last_chart"]] * 2, "module_holds_none": True,
                   "restored": kept}, out
