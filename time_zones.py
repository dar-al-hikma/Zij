# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""The time zones: the pinned database every zone is read from, the zones it
keeps only as a link to another place's record, the named mean times and
the areas and stretches where the database is not trusted (the areas' outlines
read from data/mean_time_outlines.json), and the resolution of a zone's local
clock reading to an offset (named_zone_state), with the clocks particular
places kept before 1970 (data/place_clocks.tsv, their documents
data/place_clock_sources.tsv); the zone a place takes
(place_zone, with the list data/place_zones.tsv and the area rules); and the
offline atlas's search (atlas_rows).
engine.py takes it by `from time_zones import *`. It imports nothing of the
engine's or of ephemeris.py.
"""
import contextlib
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import unicodedata
import zoneinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


# Which time-zone database every zone is read from: "the app reads time zones
# only from its pinned tzdata package,
# on every platform, never the computer's own database". zoneinfo looks in
# the directories on its search path first (the system's files on Linux and
# macOS, of whatever release the computer happens to carry) and in the tzdata
# package only where none of them has the zone, so the path is emptied here,
# before this module makes any zone, and zoneinfo's cache is cleared so that
# no zone made earlier from the system's files is handed back. The path is
# the process's, so this holds for every zone made after the import, the
# app's own included. app.py empties it itself before any other import (it
# imports pandas before the engine), and desktop_launcher.py before it loads
# Streamlit; a process that imports the engine alone -- the suite, a tool --
# has it emptied here, after ephemeris.py has imported Streamlit, which makes
# no zone as it is imported. pandas reads the system's UTC through dateutil
# as it is imported, whatever this path says; nothing in the app makes a zone
# that way. Without the package every named zone is refused as unknown, never
# read from the system instead.
def _read_zones_from_the_pinned_package():
    """Point zoneinfo at the tzdata package alone."""
    zoneinfo.reset_tzpath(to=[])
    ZoneInfo.clear_cache()


_read_zones_from_the_pinned_package()


# The data this program ships, each by the SHA-256 of the bytes it was built
# with: the five files read beside this module, and the data files of the two
# zone packages every zone is read from (tzdata, the time-zone database, and
# timezonefinder-data, the zone boundaries; their versions are pinned in
# requirements.txt). The star catalogue's is FIXED_STAR_CATALOGUE_SHA256, in
# engine.py, where the catalogue is read. These are the only record the
# program and its tests read: the test of the shipped data reads these same
# values, and a deliberate change (a rebuilt atlas, a new list, a version
# bump) updates them here in the same commit as the file. (The release's push
# hook keeps its own pin of the atlas, for another purpose.) A file whose
# bytes differ is refused where a missing or malformed one already is: the
# four tables below at this module's import (_shipped_file_bytes), the atlas at
# its first lookup and again whenever its file changes (atlas_rows), each zone
# package at its first use in the process (_zone_package_checked). This
# catches a damaged or swapped data file: a copy cut short, a file left by
# another version of the program, one replaced by mistake. It does not stop
# whoever can write these files from writing this module beside them, the
# recorded values with it; and a file changed outside its check is not seen:
# between the check and the read that follows it, after a zone package's
# first check, and before it -- the zone finder (TimezoneFinder) opens and
# loads its boundary files when it is made, before place_zone first asks it,
# which is when they are checked.
SHIPPED_DATA_SHA256 = {
    'atlas.db': '59f10b1d4fbae40c5094edea73349a52bf755d4e8e96497de6649484e6fc639b',
    'data/mean_time_outlines.json': '7dedf4d6c40ef79ad43b993952231441911d2f8477f154b12af0e32b964a6a72',
    'data/place_zones.tsv': '7ff05ba908a9f550ff64288c2e0249cdd861be0e7782c6134bd450ad0f360f83',
    'data/place_clocks.tsv': '3f7fc3fedc337d827f1ea17b5601085130c10141367c52423c891d30adf5cb76',
    'data/place_clock_sources.tsv': '380d6bf3da1155fa07468f775f8da664be7e2ebd13a3b6ec1fa9579ce0a8bef0',
}
# distribution: (import name, version, number of data files, digest). A
# package's data is hashed as one digest over the sorted list of its files'
# paths and their own hashes (zone_package_digest).
ZONE_PACKAGES = {
    'tzdata': ('tzdata', '2026.5', 605, 'e7705aa8baf0d6a57290c0b54730b2e2813b2d40de18ed5bff69100b9a243e9a'),
    'timezonefinder-data': ('timezonefinder_data', '1.2026.3', 20,
                            'af41d0f1badbb93ae4b4bf46b97e070c9b488e1fec25c77a94ba343c98e34a8a'),
}
_CODE_SUFFIXES = ('.py', '.pyc', '.pyo', '.so', '.pyd', '.dylib', '.dll')


class ShippedDataChanged(RuntimeError):
    """A data file this program ships is not the one it was built with (its
    SHA-256 is not the recorded one), or cannot be read as a file; the text
    names it. Nothing is read from it."""


def _shipped_file_bytes(name):
    """The bytes of a data file read beside this module, `name` as
    SHIPPED_DATA_SHA256 keys it, refused (ShippedDataChanged) where they are
    not the recorded ones. The bytes checked are the bytes then read."""
    import hashlib
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), *name.split('/'))
    with open(path, 'rb') as f:
        data = f.read()
    if hashlib.sha256(data).hexdigest() != SHIPPED_DATA_SHA256[name]:
        raise ShippedDataChanged(f"{name} is not the file this program was built with "
                                 "(its SHA-256 is not the one recorded), so it is not read")
    return data


def _zone_package(import_name):
    """The zone package `import_name` names, imported by its own name written
    out, or None where it is not installed."""
    try:
        if import_name == 'tzdata':
            import tzdata as package
        elif import_name == 'timezonefinder_data':
            import timezonefinder_data as package
        else:
            raise ValueError(f'{import_name} is not a zone package')
    except ModuleNotFoundError:
        return None
    return package


def zone_package_digest(import_name):
    """(number of data files, digest) of an installed zone package: every
    file the package holds as data, where the program reads it -- the folder
    of the package's own file (its __file__), which is the folder
    importlib.resources gives for it, from a source checkout and in a frozen
    build alike, the one zoneinfo reads each zone through and timezonefinder's
    data folder lies in -- but its code (Python modules, compiled or not, and
    __pycache__), which a frozen build moves into its archive; each as (its
    path from the folder above the package, written with "/", its SHA-256),
    sorted, and the digest the SHA-256 of those lines, "path<TAB>hash<LF>"
    each. Folders reached through a link are read (a macOS application bundle
    links its data folders in from elsewhere), each real folder once. The same
    on every platform. None where the package is not installed."""
    import hashlib
    package = _zone_package(import_name)
    if package is None:
        return None
    origin = getattr(package, '__file__', None)
    if not origin:                                   # no file on disk, so no folder to read
        raise FileNotFoundError(f'{import_name} has no folder on disk')
    rows, seen = [], set()

    def read(folder, parts):
        real = os.path.realpath(folder)
        if real in seen:
            return
        seen.add(real)
        for entry in sorted(folder.iterdir(), key=lambda e: e.name):
            if entry.is_dir():
                if entry.name != '__pycache__':
                    read(entry, parts + (entry.name,))
            elif os.path.splitext(entry.name)[1] not in _CODE_SUFFIXES:
                digest = hashlib.sha256(entry.read_bytes()).hexdigest()
                rows.append(('/'.join((import_name, *parts, entry.name)), digest))
    read(Path(origin).parent, ())
    rows.sort()
    return len(rows), hashlib.sha256(''.join(f'{p}\t{h}\n' for p, h in rows).encode('utf-8')).hexdigest()


# distribution -> None (its data as recorded), or the refusal's text.
_ZONE_PACKAGES_SEEN = {}


def _zone_package_checked(distribution):
    """Refuse (ShippedDataChanged) a zone package whose data files are not
    the recorded ones (ZONE_PACKAGES), naming the version the package gives
    (its __version__), or saying it names none. Checked once per process, at
    the package's first use: named_zone_state's before any zone is read,
    place_zone's before the boundaries answer. A package not installed is not
    refused here: no zone can be read without it, as before (every named zone
    refused as unknown; no finder made)."""
    if distribution not in _ZONE_PACKAGES_SEEN:
        import_name, version, count, recorded = ZONE_PACKAGES[distribution]
        try:
            found = zone_package_digest(import_name)
        except OSError:
            found = (None, None)
        if found is None or found == (count, recorded):
            _ZONE_PACKAGES_SEEN[distribution] = None
        else:
            installed = getattr(_zone_package(import_name), '__version__', None)
            if isinstance(installed, str) and installed[:1].isdigit():
                named = f"{distribution} {installed} is installed"
            else:                                    # none, or a word in its place ("unknown")
                named = f"the {distribution} installed does not name its version"
            _ZONE_PACKAGES_SEEN[distribution] = (
                f"the {distribution} package's data files are not those this program was built with "
                f"({named}; {version}'s were recorded), so no zone is read from it")
    if _ZONE_PACKAGES_SEEN[distribution] is not None:
        raise ShippedDataChanged(_ZONE_PACKAGES_SEEN[distribution])


# The named zones the time-zone database keeps only as a link to another
# place's record. The database keeps no history of these places of its own: its
# tzdata.zi carries "L Europe/Berlin Europe/Stockholm", so zoneinfo answers
# Stockholm 1947 with Berlin's record (+03:00, CEMT), Reykjavik 1950 with
# Abidjan's (GMT) and Amsterdam 1930 with Brussels' (WET), each under the
# birthplace's name; what those places' own clocks read then is not in the
# database at all. Each name here is a place of its own, with its own row in
# the database's zone.tab ("an area that is the intersection of a region
# identified by a country code and of a timezone where civil clocks have
# agreed since 1970"; "a row's third column can be a Link from 'backward'
# instead of a Zone"), stored as a link to the place named beside it: the
# database vouches for its clocks only from 1970. A link with no row of its
# own is another name for a zone that has one (Asia/Calcutta for
# Asia/Kolkata, Europe/Kiev for Europe/Kyiv) and is not listed: it is cast as
# its zone. The compiled release does not say which place an old name stands
# for, so an old name for a listed place ("Iceland", linked to Africa/Abidjan)
# is not listed either; timezonefinder, the one source of the app's zone
# names, answers no such name (the test named below reads that).
#
# Shipped here rather than read off the database as the app runs, so that
# the refusal reads the name and the date only and is the same for one chart
# on every machine. The database is the pinned tzdata package on every
# machine (_read_zones_from_the_pinned_package, at the top of this
# file; before it, zoneinfo read the system's files where there were any,
# whose release could differ and which a build with the backzone file could
# give these places' own records). The list is derived from that package
# (requirements.txt's tzdata) by a development-only tool, which also checks
# it; LINKED_ZONES_TZDATA names the package and a development-only test
# holds it to the pin. Every name timezonefinder answers is either a zone
# with a record of its own in the package or one of these
# (tests/test_linked_zones_2026_10_05.py reads the database zoneinfo reads).
#
# Before 1970 some of these places are cast after all, inside windows of
# their own clocks that the sources establish (PRE1970_WINDOWS, below):
# a hand-kept, sourced table, not a backzone compile and not read from the
# package. Inside a window the window gives the offset and the label;
# outside every window the name is refused as before. The 1970 cut stays the
# typed local year: a reading dated
# before 1970 is read against the windows alone, one dated from 1970-01-01
# from the record.
LINKED_ZONES_TZDATA = '2026.5'
LINKED_ZONES_UNTIL_YEAR = 1970
LINKED_ZONES = {
    'Africa/Accra': 'Africa/Abidjan', 'Africa/Addis_Ababa': 'Africa/Nairobi', 'Africa/Asmara': 'Africa/Nairobi',
    'Africa/Bamako': 'Africa/Abidjan', 'Africa/Bangui': 'Africa/Lagos', 'Africa/Banjul': 'Africa/Abidjan',
    'Africa/Blantyre': 'Africa/Maputo', 'Africa/Brazzaville': 'Africa/Lagos', 'Africa/Bujumbura': 'Africa/Maputo',
    'Africa/Conakry': 'Africa/Abidjan', 'Africa/Dakar': 'Africa/Abidjan', 'Africa/Dar_es_Salaam': 'Africa/Nairobi',
    'Africa/Djibouti': 'Africa/Nairobi', 'Africa/Douala': 'Africa/Lagos', 'Africa/Freetown': 'Africa/Abidjan',
    'Africa/Gaborone': 'Africa/Maputo', 'Africa/Harare': 'Africa/Maputo', 'Africa/Kampala': 'Africa/Nairobi',
    'Africa/Kigali': 'Africa/Maputo', 'Africa/Kinshasa': 'Africa/Lagos', 'Africa/Libreville': 'Africa/Lagos',
    'Africa/Lome': 'Africa/Abidjan', 'Africa/Luanda': 'Africa/Lagos', 'Africa/Lubumbashi': 'Africa/Maputo',
    'Africa/Lusaka': 'Africa/Maputo', 'Africa/Malabo': 'Africa/Lagos', 'Africa/Maseru': 'Africa/Johannesburg',
    'Africa/Mbabane': 'Africa/Johannesburg', 'Africa/Mogadishu': 'Africa/Nairobi', 'Africa/Niamey': 'Africa/Lagos',
    'Africa/Nouakchott': 'Africa/Abidjan', 'Africa/Ouagadougou': 'Africa/Abidjan',
    'Africa/Porto-Novo': 'Africa/Lagos', 'America/Anguilla': 'America/Puerto_Rico',
    'America/Antigua': 'America/Puerto_Rico', 'America/Aruba': 'America/Puerto_Rico',
    'America/Atikokan': 'America/Panama', 'America/Blanc-Sablon': 'America/Puerto_Rico',
    'America/Cayman': 'America/Panama', 'America/Creston': 'America/Phoenix',
    'America/Curacao': 'America/Puerto_Rico', 'America/Dominica': 'America/Puerto_Rico',
    'America/Grenada': 'America/Puerto_Rico', 'America/Guadeloupe': 'America/Puerto_Rico',
    'America/Kralendijk': 'America/Puerto_Rico', 'America/Lower_Princes': 'America/Puerto_Rico',
    'America/Marigot': 'America/Puerto_Rico', 'America/Montserrat': 'America/Puerto_Rico',
    'America/Nassau': 'America/Toronto', 'America/Port_of_Spain': 'America/Puerto_Rico',
    'America/St_Barthelemy': 'America/Puerto_Rico', 'America/St_Kitts': 'America/Puerto_Rico',
    'America/St_Lucia': 'America/Puerto_Rico', 'America/St_Thomas': 'America/Puerto_Rico',
    'America/St_Vincent': 'America/Puerto_Rico', 'America/Tortola': 'America/Puerto_Rico',
    'Antarctica/DumontDUrville': 'Pacific/Port_Moresby', 'Antarctica/McMurdo': 'Pacific/Auckland',
    'Antarctica/Syowa': 'Asia/Riyadh', 'Arctic/Longyearbyen': 'Europe/Berlin', 'Asia/Aden': 'Asia/Riyadh',
    'Asia/Bahrain': 'Asia/Qatar', 'Asia/Brunei': 'Asia/Kuching', 'Asia/Kuala_Lumpur': 'Asia/Singapore',
    'Asia/Kuwait': 'Asia/Riyadh', 'Asia/Muscat': 'Asia/Dubai', 'Asia/Phnom_Penh': 'Asia/Bangkok',
    'Asia/Vientiane': 'Asia/Bangkok', 'Atlantic/Reykjavik': 'Africa/Abidjan',
    'Atlantic/St_Helena': 'Africa/Abidjan', 'Europe/Amsterdam': 'Europe/Brussels',
    'Europe/Bratislava': 'Europe/Prague', 'Europe/Busingen': 'Europe/Zurich', 'Europe/Copenhagen': 'Europe/Berlin',
    'Europe/Guernsey': 'Europe/London', 'Europe/Isle_of_Man': 'Europe/London', 'Europe/Jersey': 'Europe/London',
    'Europe/Ljubljana': 'Europe/Belgrade', 'Europe/Luxembourg': 'Europe/Brussels',
    'Europe/Mariehamn': 'Europe/Helsinki', 'Europe/Monaco': 'Europe/Paris', 'Europe/Oslo': 'Europe/Berlin',
    'Europe/Podgorica': 'Europe/Belgrade', 'Europe/San_Marino': 'Europe/Rome', 'Europe/Sarajevo': 'Europe/Belgrade',
    'Europe/Skopje': 'Europe/Belgrade', 'Europe/Stockholm': 'Europe/Berlin', 'Europe/Vaduz': 'Europe/Zurich',
    'Europe/Vatican': 'Europe/Rome', 'Europe/Zagreb': 'Europe/Belgrade', 'Indian/Antananarivo': 'Africa/Nairobi',
    'Indian/Christmas': 'Asia/Bangkok', 'Indian/Cocos': 'Asia/Yangon', 'Indian/Comoro': 'Africa/Nairobi',
    'Indian/Kerguelen': 'Indian/Maldives', 'Indian/Mahe': 'Asia/Dubai', 'Indian/Mayotte': 'Africa/Nairobi',
    'Indian/Reunion': 'Asia/Dubai', 'Pacific/Chuuk': 'Pacific/Port_Moresby', 'Pacific/Funafuti': 'Pacific/Tarawa',
    'Pacific/Majuro': 'Pacific/Tarawa', 'Pacific/Midway': 'Pacific/Pago_Pago',
    'Pacific/Pohnpei': 'Pacific/Guadalcanal', 'Pacific/Saipan': 'Pacific/Guam', 'Pacific/Wake': 'Pacific/Tarawa',
    'Pacific/Wallis': 'Pacific/Tarawa',
}


# The pre-1970 windows. Researchers read the laws and gazettes of the linked
# places, and each window was checked again against the documents, by a
# second reader, before it was adopted. The rows are taken from the checked
# tables as corrected, and Stockholm's Swedish-time row from the decision
# that adopted it, which no table holds.
#
# A hand-kept, sourced table, not a backzone compile, and never read from the
# pinned package: inside a window the window gives the state, the offset and
# the label, because the package holds the linked target's record there, not
# the place's own (Chuuk's +10, Pohnpei's +11, Majuro's +12 and Saipan's +10
# in 1941 against the window's +09; Mahe's LMT in 1907; Amsterdam's and
# Luxembourg's WET in 1910; Reykjavik's GMT in 1925 against -01). "Cast under
# their pinned 2026e records" is the 2026e release's own
# record for each place, the one the researchers compiled and checked, not
# the package's.
#
# Each window is a UT instant pair, half-open [from, to), with its offset in
# whole seconds and its label. A bound is a clip, a moment inside what
# the sources establish chosen to keep clear of an undated change, unless the
# ruling ties it to a dated change of the clock; where a window's start is a
# clip, its cast says the date it is cast from is this app's choice, and why,
# as CHOSEN_STARTS do ('chosen'). The starts that are a dated
# change: Stockholm's CET of 1900 (the statute's start of 1900), its summer
# time of 1916 (the statute's 15 May beginning an hour early) and its CET
# after the refused hour (where both readings agree); Bratislava's four
# (orders 84, 181 and 213 of 1946, the corrected day continuing the summer
# time); Luxembourg's correction of 1937 (the decree's 01:00 summer time) and
# the WET window continuing it. Every other start is a clip.
#
# Labels are the return rows', except two the sources call invented: IANA's
# "SET" for Swedish time (the check's words: "an extra-special
# abbreviation style") and its "GMT" for Czechoslovakia's winter time of
# 1946-47 (europe 1035-1036). Those two carry the decision's plain
# words, as Amsterdam's 1909-1916 window carries its laws' (AMT is IANA's
# abbreviation). A named mean time -- Swedish time, Amsterdam
# mean solar time, Monaco's Paris mean time -- is cast as CIVIL_MEAN_TIMES'
# are, with civil_mean_time_label's sentence. A standard time carries a
# label only where its start is a clip, in one form: "The
# clock here was then {label}; the date it is cast from here, ...", since the
# page prints it as the civil clock then;
# a standard time with a dated start carries none, as a named-zone cast does.
# (The anniversary's description takes it mid-sentence, as "the clock ...".)
#
# The seam with the 1970 cut (the typed local year): a reading whose typed year
# is before 1970 is read against the
# windows alone; from 1970-01-01 local it is read from the record. So
# Blanc-Sablon's local 1969-12-31 20:00:00-23:59:59, after its window's end
# at 1970-01-01 00:00 UT and before the local 1970, is refused 'linked'.
# Moving the cut to UT belongs with the cut's revisit after the release.
#
# Every source a row names is in PRE1970_SOURCES, one id per document
# (duplicates folded: JP1941NOTICE11 is JAPAN1941TIME,
# JP1934NOTICE42 JAPAN1934TIME, LANATURE1951 NATURE1951, NBS1950_66_73
# NBS1950, MILNE1899_R3B MILNE1899), with how the check read it
# -- not the researcher's label (DJ1949 an official
# electronic transcription; SEY1906 and SEY1971 a commercial facsimile). The
# two Swedish documents the check read that the returns give no
# id are SE1899SKR38 and SE1878PROP22. Page
# locators are written "p 522", with no full stop: they are pages of gazettes
# and lists, never of the texts the citation register reads.
PRE1970_READ_STATUSES = (
    'official or library scan, read on the page image',
    "official or library scan, read on the researcher's retained copy",
    'library scan, read in its text layer',
    'original scan, read once and not re-read',
    "commercial facsimile, read on the researcher's retained copy",
    'official electronic transcription',
    'official consolidated text',
    'unofficial mirror of the official text',
    'secondary page',
    'text read in an earlier round and not re-verified',
    'official or library scan, read in its text layer, then checked',
    "official or library scan, read in its text layer on the researcher's retained copy",
    "citation only, through the time-zone database's quotation",
    'search-engine copy only',
    "the time-zone release's own files",
)

PRE1970_SOURCES = {
    # Sweden (the Riksdag's documents read in their open-data text; the
    # statutes and the newspaper not reached).
    'SE1979': ("Sweden, Government Proposition 1978/79:200 (22 March 1979), section 1.1: standard time from 1879, "
               "14 s ahead of the time from 1900; summer time only in 1916; Norway's in 1916, 1940-45 and 1959-65, "
               "Denmark's in 1916 and 1940-48, Iceland's in 1939-67",
               'official electronic transcription'),
    'SE1926': ("Sweden, Motion AK 1926:348 (Lithander, 1 February 1926): the ordinance of 12 May 1916, summer time "
               "15 May to 30 September 1916, the first day beginning an hour early and the last ending an hour "
               "late; no summer time ordered from 1917 to 1926",
               'official electronic transcription'),
    'SE1899': ("Sweden, Andra Kammarens Tillfalliga Utskotts (N:o 4) Utlatande N:o 4 (15 February 1899): the "
               "ordinance of 31 May 1878, from 1879 one time for all places, the mean time of the meridian three "
               "degrees west of Stockholm observatory, 14 s from European mean time (the watchmakers: 14.8 s)",
               'official electronic transcription'),
    'SE1899SKR38': ("Sweden, Riksdagens Skrifvelse N:o 38 (5 April 1899): the 1878 ordinance's wording; asks for "
                    "European mean time",
                    'official electronic transcription'),
    'SE1878PROP22': ("Sweden, Kongl. Maj:ts Nad. Proposition No 22 (1878): from 1879, in law and in civil use, one "
                     "time for all places, the mean time of the meridian three degrees (twelve time-minutes) west "
                     "of Stockholm observatory",
                     'official electronic transcription'),
    'SE1878LAW': ("Svensk forfattningssamling 1878 no 14 (law of 31 May 1878): Swedish time from the beginning of "
                  "1879", "citation only, through the time-zone database's quotation"),
    'SE1899LAW': ("Svensk forfattningssamling 1899 no 44 (16 June 1899): Central European time from the beginning "
                  "of 1900", "citation only, through the time-zone database's quotation"),
    'SE1916LAW': ("Svensk forfattningssamling 1916 no 124 (12 May 1916): 15 May begins an hour early and 30 "
                  "September ends an hour late", "citation only, through the time-zone database's quotation"),
    'SEDN1916': ("Dagens Nyheter, 1 October 1916, p 7: the clocks set back at 01:00 summer time to 00:00",
                 "citation only, through the time-zone database's quotation"),
    'NBS1935': ("R. E. Gould, Standard Time Throughout the World, NBS Circular 406 (20 March 1935): Table 1, p 3, "
                "lists Sweden under 1879 among the zone system's adopters; Table 4, p 18, gives the Marianas 150 "
                "degrees E, 10 h fast", 'library scan, read in its text layer'),
    # The second batch of documents.
    'NO1894': ("Norway, law of 29 June 1894 on standard time: the mean time of 15 degrees E the legal time from 1 "
               "January 1895", 'original scan, read once and not re-read'),
    'NO2018': ("Norway, government note on ending seasonal clock changes (2018): summer time in 1943-45",
               'text read in an earlier round and not re-verified'),
    'DK1893': ("Denmark, law no 83 of 29 March 1893: the mean time of 15 degrees E for all the country but the "
               "Faroes, in force 1 January 1894", 'unofficial mirror of the official text'),
    'DK2023': ("Denmark, government bill L19 (25 January 2023) on the time normally applicable",
               'text read in an earlier round and not re-verified'),
    'NL1908': ("Netherlands, Staatsblad 1908 no 236 (law of 23 July 1908): the legal time is the mean solar time of "
               "Amsterdam, with no figure", 'official or library scan, read on the page image'),
    'NL1908START': ("Netherlands, Staatsblad 1908 no 336 (decree of 7 November 1908): in force on 1 May 1909, with "
                    "the day that begins after midnight of 30 April", 'official or library scan, read on the page image'),
    'NLOBS1909': ("The Observatory 32 (July 1909), p 301: the Amsterdam time adopted in Holland is Greenwich time "
                  "plus 19 m 32.13 s", 'official or library scan, read on the page image'),
    'NL1916': ("Netherlands, Staatsblad 1916 no 172 (law of 27 April 1916): midnight Amsterdam mean time between 30 "
               "April and 1 May 1916 counts as 01:00 on 1 May", 'official or library scan, read on the page image'),
    'NL1958': ("Netherlands, Staatsblad 1958 no 352 (law of 16 July 1958, issued 1 August): the legal time is "
               "Central European time, in force the second day after issue",
               'original scan, read once and not re-read'),
    'NLGENT': ("R. H. van Gent, De wettelijke tijd in Nederland (web page): the 1908 law named no meridian; a "
               "rounded 20 minutes was usually applied", 'secondary page'),
    'CS54': ("Czechoslovakia, law 54/1946 (8 March 1946): the government may set a summer time by order, departing "
             "from Central European time", 'official or library scan, read on the page image'),
    'CS84': ("Czechoslovakia, government order 84/1946: summer time from 6 May 1946 at 02:00 Central European time",
             'official or library scan, read on the page image'),
    'CS181': ("Czechoslovakia, government order 181/1946 of 1 October 1946, Sbirka part 77 (4 October 1946), p "
              "1152: summer time ends on 7 October 1946 at 03:00 summer time; no territorial clause",
              'official or library scan, read on the page image'),
    'CS213': ("Czechoslovakia, government order 213/1946: winter time from 1 December 1946, the clocks put from "
              "03:00 Central European time to 02:00, to 23 February 1947, from 02:00 winter time to 03:00",
              'official or library scan, read on the page image'),
    'LU1904': ("Luxembourg, law of 10 May 1904, Memorial A no 29: the legal time is the mean time of 15 degrees E, "
               "in force 1 June 1904", 'original scan, read once and not re-read'),
    'LU1929': ("Luxembourg, decree of 13 April 1929, Memorial A no 18, p 257: the legal time again the mean time of "
               "15 degrees E, from the night of 20 to 21 April at 23:00", 'official or library scan, read on the page image'),
    'LU1937': ("Luxembourg, grand-ducal decree of 30 September 1937, Memorial A no 67: the legal time again "
               "Greenwich's; in the night of 2 to 3 October 1937, at 01:00, the clocks put back 60 minutes",
               'official or library scan, read on the page image'),
    'IS1968': ("Iceland, law 6/1968: Greenwich mean time all year, in force on 7 April 1968 at 01:00",
               'official consolidated text'),
    'IS1968BILL': ("Iceland, government bill, parliamentary document 255 of the 88th session: the summer-time "
                   "authority of 1917 used in 1917-18 and again without a break from 1939; law 35 of 1907 set the "
                   "time one hour behind Greenwich's", 'official or library scan, read on the page image'),
    'ISALMANAC': ("University of Iceland almanac, its clock history (web page): summer time in 1917, 1918, 1919 and "
                  "1921, then from 1939; none in 1920", 'secondary page'),
    'MC1892': ("Journal de Monaco no 1764 (24 May 1892): by the ordinance of 13 May, the legal time from 1 June 1892 "
               "kept, as in France, on the meridian of Paris", 'original scan, read once and not re-read'),
    'MC1911': ("Journal de Monaco no 2757 (28 March 1911), ordinance of 16 March 1911: the legal time, from its "
               "promulgation, France's as the French law of 9 March 1911 fixes it; the clocks put back 9 min 21 s",
               'official or library scan, read on the page image'),
    'VAT1966': ("Vatican City, Ordinanza XXVI (16 May 1966): the summer time of 1966",
                'original scan, read once and not re-read'),
    # The third batch of documents, each with how the check read it.
    'AEF1949MARCH': ("Journal officiel de l'Afrique Equatoriale Francaise, 1 May 1949, p 522: the arrete of 8 March "
                     "1949, promulgated by arrete no 1000 of 6 April: the legal time in A.E.F., all year, Greenwich "
                     "mean time advanced one hour", 'official or library scan, read on the page image'),
    'NBS1950': ("R. E. Gould, Standard Time Throughout the World, NBS Circular 496 (1 August 1950), Table 1: French "
                "Equatorial Africa, Gabon and Ubangi Shari 1 h fast; Somaliland 3 h fast; the Seychelles 4 h fast; "
                "the Marianas 9 h fast", 'official or library scan, read on the page image'),
    'NATURE1951': ("Le temps legal dans l'Union francaise, La Nature no 3189 (January 1951), p 14: A.E.F. one hour "
                   "ahead of universal time, the Cote des Somalis three; it names decrees of 18 July 1948 and 27 "
                   "January 1949", 'official or library scan, read on the page image'),
    # The last batch of documents, each with how it was read.
    'JAPAN1941TIME': ("Kanpo no 4330 (16 June 1941), p 486: South Seas Government Notice 11 of 10 March 1941: the "
                      "standard time of the South Sea Islands is that of the meridian of 135 degrees E, from 1 April "
                      "1941", 'official or library scan, read on the page image'),
    'JAPAN1922SCOPE': ("Kanpo (16 October 1922), p 393: South Seas Bureau Order 4 of 1 April 1922, the branch "
                       "offices' areas: Saipan the Marianas; Truk the Eastern Carolines west of 154 degrees E; "
                       "Ponape those east of it and the Marshalls west of 164 degrees E; Jaluit the Marshalls east "
                       "of it", 'official or library scan, read on the page image'),
    'JAPAN_PILOT_TIME': ("Nanyo Gunto pilot, Hydrographic Department (July 1940, a corrected copy), p 25: South Sea "
                         "Islands standard time, the meridian of 135 degrees E, 9 h ahead of Greenwich (the 1941 "
                         "correction 323)", 'official or library scan, read on the page image'),
    'JAPAN1934TIME': ("Kanpo no 2125 (3 February 1934), p 70: South Seas Government Notice 42 of 28 December 1933: "
                      "from 1934, 135 degrees E for Palau and Yap, 150 degrees E for Saipan and Truk, 165 degrees E "
                      "for Ponape and Jaluit", 'official or library scan, read on the page image'),
    'US1966TIME': ("United States, Uniform Time Act of 1966, Public Law 89-387, 80 Stat 107-109: Atlantic standard "
                   "time on the meridian of 60 degrees W; advanced time from April to October unless a State or "
                   "possession exempts itself", 'official or library scan, read in its text layer, then checked'),
    'FR1967ATLANTIC': ("Federal Register 32 no 228 (25 November 1967), p 16162: the Atlantic standard time zone "
                       "includes Puerto Rico and the Virgin Islands, effective 23 December 1967",
                       'official or library scan, read on the page image'),
    'DJ1949': ("Cote francaise des Somalis, arrete no 228, Journal officiel no 2 (28 February 1949): the legal time "
               "invariable through the year, Greenwich mean time plus three hours",
               'official electronic transcription'),
    'SEY1906': ("The Laws of Seychelles Revised (1907), p 1689: Ordinance 9 of 1906, the mean time of 60 degrees E "
                "standard time throughout the colony; brought into force on 1 January 1907",
                "commercial facsimile, read on the researcher's retained copy"),
    'SEY1971': ("Laws of Seychelles 1971, volume VI, chapter 237, p 571: the same rule, from 1 January 1907; no "
                "subsidiary legislation", "commercial facsimile, read on the researcher's retained copy"),
    'QC1966ACT': ("Quebec 1966, chapter 3, Official Time Act (assented 15 March 1966): Atlantic standard time east "
                  "of 68 degrees W; in force on its sanction; its summer clause for the western part only",
                  "official or library scan, read on the researcher's retained copy"),
    'QC1969ACT': ("Quebec 1969, chapter 10 (assented 23 October 1969): the line moved to 63 degrees W",
                  "official or library scan, read on the researcher's retained copy"),
    'QC1978T6': ("Quebec, Lois refondues 1977, chapter T-6 (November 1978): its two sections amended in 1969 only",
                 "official or library scan, read in its text layer on the researcher's retained copy"),
    'AMIGOE1964DEC29': ("Amigoe di Curacao (29 December 1964), p 1, \"Klokken halfuur vooruit\"",
                        'official or library scan, read on the page image'),
    'MILNE1899': ("John Milne, Civil Time, The Geographical Journal 13 (1899), p 178",
                  "official or library scan, read on the researcher's retained copy"),
    'WALLIS1948LEAD': ("A 1948 order fixing the legal time of Wallis and Futuna, known through a search-engine copy "
                       "of an official index page", 'search-engine copy only'),
    'TZ2026E': ("IANA's tzdata 2026e, its source files: the release the pinned package is built from",
                "the time-zone release's own files"),
}

# The documents of the places with clocks of their own (PLACE_CLOCKS, read
# from data/place_clocks.tsv, below) come into this table at import from
# data/place_clock_sources.tsv: generated from the same research register
# as the places' table and never edited by hand, one row per document the
# places' rows name, its title and how it was read, but the documents this
# table holds above for its other records (US1966TIME and TZ2026E), which
# the file leaves out. A malformed or changed file stops the import, as the
# places' table does.
PLACE_CLOCK_SOURCE_COLUMNS = ('id', 'title', 'status')
# The forms a title may not take, the forms the tests read every title of
# this table for, as they read them: a page or a chapter and verse written
# as the texts the citation register reads write theirs (a page's "p" with
# a full stop, where a title here writes "p 522"), read as written; and,
# read without regard to case, the forms of the project's own bookkeeping:
# a decision's number, a round of checking, a finding's id, a report's
# section beside the report, the term for a chosen bound with its
# qualifier, the name of a working group, a date of the work.
PLACE_CLOCK_SOURCE_LOCATOR_FORMS = (r"\bpp?\.\s*\d", r"\d{1,2}\.\d{1,2}\s*,\s*\d")
PLACE_CLOCK_SOURCE_BOOKKEEPING_FORMS = (
    r"\brulings?\s+\d", r"\bround\s+\d", r"\bN-\d", r"\bN-?\d+[a-z]", r"\bEN-?\d", r"\bR\d+b?\.\d",
    r"\bfinding\s+\d", r"\bdecision\s+\d", r"reproduction", r"\(\d\.\d\)", r"\breview[\s-]+clip",
    r"\blane\s+(?-i:[A-Z])", r"\b202[4-9]-\d\d-\d\d")


def _read_place_clock_sources(path=None, held=None):
    """{id: (title, status)} from data/place_clock_sources.tsv, or from the
    file at `path` where one is given (read in its place, not checked by its
    hash); `held` the documents the program holds already (PRE1970_SOURCES
    as this module writes it), none of which a row may name again.

    A malformed file stops the import, as the places' table does: a header
    that is not PLACE_CLOCK_SOURCE_COLUMNS; a row of another length; an id
    not written as the file writes one (a capital letter, then capitals and
    digits, twenty at most), or one written twice, in the file or in `held`;
    a status outside PRE1970_READ_STATUSES; a title that is empty, begins or
    ends with a space, or takes one of PLACE_CLOCK_SOURCE_LOCATOR_FORMS or
    PLACE_CLOCK_SOURCE_BOOKKEEPING_FORMS. (A title may end in the stop of
    an abbreviation, "D.C.", and so a final stop is not refused here.)"""
    import re
    name = 'data/place_clock_sources.tsv'
    if path is None:
        data = _shipped_file_bytes(name)
    else:
        with open(path, 'rb') as f:
            data = f.read()
    lines = [line for line in data.decode('utf-8').split('\n') if line and not line.startswith('#')]
    if not lines or tuple(lines[0].split('\t')) != PLACE_CLOCK_SOURCE_COLUMNS:
        raise ValueError(f"{name}: its header is not the columns this program reads")
    held = PRE1970_SOURCES if held is None else held
    forms = ([re.compile(form) for form in PLACE_CLOCK_SOURCE_LOCATOR_FORMS]
             + [re.compile(form, re.IGNORECASE) for form in PLACE_CLOCK_SOURCE_BOOKKEEPING_FORMS])
    sources = {}
    for line in lines[1:]:
        cells = line.split('\t')
        if len(cells) != len(PLACE_CLOCK_SOURCE_COLUMNS):
            raise ValueError(f"{name}: {line!r} has {len(cells)} columns, not {len(PLACE_CLOCK_SOURCE_COLUMNS)}")
        sid, title, status = cells
        if not (2 <= len(sid) <= 20 and sid.isascii() and sid.isalnum() and sid[0].isalpha() and sid == sid.upper()):
            raise ValueError(f"{name}: {line!r}: an id not written as this file writes one")
        if sid in sources or sid in held:
            raise ValueError(f"{name}: {line!r}: a document the program holds already")
        if status not in PRE1970_READ_STATUSES:
            raise ValueError(f"{name}: {line!r}: a status outside the program's list")
        if not title or title != title.strip() or any(form.search(title) for form in forms):
            raise ValueError(f"{name}: {line!r}: a title in a form this table's titles do not take")
        sources[sid] = (title, status)
    return sources


PRE1970_SOURCES.update(_read_place_clock_sources())

# Why a window's start is this app's choice (as CHOSEN_STARTS do): the page
# reads these, so they name no document.
_AFTER_LAW = "the day after its law took effect"
_AFTER_GAZETTE = "the day after the official gazette printed its rule"
_YEAR_WITHOUT_SUMMER = "the first day of a year the sources show without summer time"
_AFTER_ORDER = "the day after its order took effect"


def _ut(*parts):
    """A UT instant."""
    return datetime(*parts, tzinfo=timezone.utc)


def _pre1970_window(start, end, offset_seconds, abbreviation, sources, note, *, chosen=None, mean_time=False,
                    turned_back_from=None, note_sources=()):
    """One window: [start, end) in UT at offset_seconds, under abbreviation,
    on `sources` (the row's, as its return table or ruling gives them), with
    `note` and the further documents it draws on (`note_sources`). `chosen`
    is why its start is this app's choice (None: a dated change);
    `turned_back_from` the offset the clocks were put back from at its start,
    where the hour before is no window of its own."""
    return {'from': start, 'to': end, 'offset_seconds': offset_seconds, 'abbreviation': abbreviation,
            'chosen': chosen, 'mean_time': mean_time, 'turned_back_from': turned_back_from,
            'sources': sources, 'note': note, 'note_sources': note_sources}


_STOCKHOLM_LAW = ('SE1979', 'SE1926', 'SE1899', 'SE1899SKR38', 'SE1878PROP22')
_PACIFIC_NOTE = ("Both bounds are clips. The notice was in force from 1 April 1941; the window "
                 "starts the day after its printing and ends at the year's end, before the war years. Continuity "
                 "to the end rests on the notice's open-ended text and one official secondary witness, the "
                 "corrected pilot (JAPAN_PILOT_TIME). The release's own record for the place gives "
                 "+09 throughout; the package's, the linked target's, gives {}.")
_AEF_NOTE = ("Both bounds are clips, built as returned. The start clip: the gazette prints the order in summary "
             "and gives no date of entry into force, so whether it was in force at Bangui and Libreville at that "
             "instant is not shown, and the +01:00 before it rests on secondary lists only. One witness: the "
             "gazette scan stands only on the Congo government's site. La Nature agrees on the hour, and names "
             "decrees of 18 July 1948 and 27 January 1949 as what fixed it; neither was read. The first is perhaps "
             "decree 48-1136 of 16 July 1948, which was read in the A.E.F. gazette: it leaves the hour to a "
             "ministerial order on each territory's proposal, and that 18 July was its national publication is "
             "not confirmed.")

PRE1970_WINDOWS = {
    'Europe/Stockholm': (
        _pre1970_window(
            _ut(1879, 1, 2), _ut(1899, 12, 31, 22, 59, 46), 3614, 'Swedish time', _STOCKHOLM_LAW,
            "A window no return table holds, built from the decision that adopted it, which gives the date "
            "1879-01-02 and no instant; the window starts at 00:00 UT, "
            "the narrower reading, 1 h 0 min 14 s after local midnight in Swedish time. The law (SE1878LAW, known "
            "through the database's quotation) set the time from the start of 1879; the offset to the second is "
            "only likely (the watchmakers give 14.8 s, SE1899). The database's label for it, SET, is its own "
            "invention, so the plain name is given. NBS1935 lists Sweden under 1879 among the zone system's "
            "adopters: a weak conflicting secondary.",
            chosen=_AFTER_LAW, mean_time=True, note_sources=('SE1878LAW', 'NBS1935')),
        _pre1970_window(
            _ut(1899, 12, 31, 22, 59, 46), _ut(1916, 5, 14, 22), 3600, 'CET',
            ('SE1979', 'SE1926', 'SE1899LAW', 'SE1916LAW'),
            "From the start of 1900 in Swedish time (SE1899LAW, through the database's quotation; restated by "
            "SE1979 and SE1926) to the start of 15 May 1916 in Central European time, the day beginning an hour "
            "early. The change from Swedish time shows the local 1899-12-31 23:59:46 to 23:59:59 twice."),
        _pre1970_window(
            _ut(1916, 5, 14, 22), _ut(1916, 9, 30, 22), 7200, 'CEST', ('SE1926', 'SE1916LAW', 'SEDN1916'),
            "Summer time, to where the statute's wording ends it (30 September ending an hour late: 22:00 UT); "
            "the next hour is refused (PRE1970_DISPUTED). The change to it skips the local 1916-05-14 23:00 to "
            "23:59:59."),
        _pre1970_window(
            _ut(1916, 9, 30, 23), _ut(1970, 1, 1), 3600, 'CET', ('SE1979', 'SE1926', 'SE1916LAW', 'SEDN1916'),
            "From where both readings of the autumn change agree (the newspaper's 23:00 UT), to 1970: no summer "
            "time was ordered after 1916 (SE1926 to 1926; SE1979: every later motion for one rejected)."),
    ),
    'Europe/Oslo': (
        _pre1970_window(
            _ut(1895, 1, 2), _ut(1916, 1, 1), 3600, 'CET', ('NO1894', 'SE1979'),
            "The 1894 law made the mean time of 15 degrees E the legal time from 1 January 1895; the window "
            "starts a day later, after every place's local midnight, and ends before the 1916 summer time. The "
            "years without summer time rest on a 1979 retrospective, not on each year's orders.",
            chosen=_AFTER_LAW),
        _pre1970_window(
            _ut(1917, 1, 1), _ut(1940, 1, 1), 3600, 'CET', ('NO1894', 'SE1979'),
            "The 1894 law stands; SE1979 gives Norway's summer times as 1916, 1940-45 and 1959-65 only.",
            chosen=_YEAR_WITHOUT_SUMMER),
        _pre1970_window(
            _ut(1946, 1, 1), _ut(1959, 1, 1), 3600, 'CET', ('NO1894', 'SE1979'),
            "After the war years, which stay refused: NO2018 gives summer time in 1943-45, SE1979 in 1940-45 "
            "(PRE1970_CONFLICTS).", chosen=_YEAR_WITHOUT_SUMMER, note_sources=('NO2018',)),
        _pre1970_window(
            _ut(1966, 1, 1), _ut(1970, 1, 1), 3600, 'CET', ('NO1894', 'SE1979'),
            "After the summer times of 1959-65, which SE1979 says ended with 1965.", chosen=_YEAR_WITHOUT_SUMMER),
    ),
    'Europe/Copenhagen': (
        _pre1970_window(
            _ut(1894, 1, 2), _ut(1916, 1, 1), 3600, 'CET', ('DK1893', 'DK2023', 'SE1979'),
            "The 1893 law made the mean time of 15 degrees E the time of all the country but the Faroes from 1 "
            "January 1894; the window starts a day later. DK2023 was not reached by the check and no window "
            "needs it.", chosen=_AFTER_LAW),
        _pre1970_window(
            _ut(1917, 1, 1), _ut(1940, 1, 1), 3600, 'CET', ('DK1893', 'DK2023', 'SE1979'),
            "SE1979: Denmark kept summer time in 1916 and again in 1940-48.", chosen=_YEAR_WITHOUT_SUMMER),
        _pre1970_window(
            _ut(1949, 1, 1), _ut(1970, 1, 1), 3600, 'CET', ('DK1893', 'DK2023', 'SE1979'),
            "SE1979: summer time to the end of 1948, and none brought back by 1979.", chosen=_YEAR_WITHOUT_SUMMER),
    ),
    'Europe/Amsterdam': (
        _pre1970_window(
            _ut(1909, 5, 2), _ut(1916, 4, 30, 23, 40, 28), 1172, 'Amsterdam mean solar time',
            ('NL1908', 'NL1908START', 'NLOBS1909', 'NL1916'),
            "Amsterdam mean solar time, the laws' words, \"de middelbare zonnetijd van Amsterdam\" (NL1908, "
            "NL1916). The law names it with no figure; +00:19:32 is the 1909 report's 19 m 32.13 s "
            "to the second, as IANA has it, not the rounded 20 minutes van Gent says was usually applied (NLGENT). "
            "The start is the cautious gate, a day after the law's 1909-04-30T23:40:28Z; the end is "
            "the 1916 law's midnight converted at +00:19:32 (0.13 s inside summer time at the report's figure). "
            "AMT, the abbreviation the return and the decision give, is IANA's, which its notes call their own "
            "(backzone 1261-1262); the label is the laws' words instead.", chosen=_AFTER_LAW,
            mean_time=True, note_sources=('NLGENT', 'TZ2026E')),
        _pre1970_window(
            _ut(1958, 8, 4), _ut(1970, 1, 1), 3600, 'CET', ('NL1958',),
            "The 1958 law, issued 1 August, made Central European time the legal time from the second day after "
            "issue (1958-08-03); the window starts the day after.", chosen=_AFTER_LAW),
    ),
    'Europe/Luxembourg': (
        _pre1970_window(
            _ut(1904, 6, 2), _ut(1916, 1, 1), 3600, 'CET', ('LU1904',),
            "The 1904 law made the mean time of 15 degrees E the legal time from 1 June; the window starts the day "
            "after and ends before the 1916 summer time.", chosen=_AFTER_LAW),
        _pre1970_window(
            _ut(1937, 10, 3), _ut(1937, 10, 3, 2), 0, 'WET', ('LU1937',),
            "A correction: the decree put the clocks back 60 minutes at 01:00 summer time in the "
            "night of 2 to 3 October 1937, 00:00 UT; the record has 02:00 UT, wrong for these two hours. The "
            "local hour before 01:00 on 3 October was shown twice, the first time in summer time, which is no "
            "window: it is refused as ambiguous ('turned_back_from').", turned_back_from=3600,
            note_sources=('TZ2026E',)),
        _pre1970_window(
            _ut(1937, 10, 3, 2), _ut(1938, 1, 1), 0, 'WET', ('LU1937',),
            "Greenwich time again under the decree, continuing the corrected hours, to the year's end, before the "
            "unreviewed change of 1938."),
    ),
    'Atlantic/Reykjavik': (
        _pre1970_window(
            _ut(1920, 1, 1), _ut(1921, 1, 1), -3600, '-01', ('IS1968BILL', 'ISALMANAC'),
            "Neither chronology has summer time in 1920, and both put the clock an hour behind Greenwich (law 35 "
            "of 1907). 1919 and 1921 stay refused: the bill has summer time in 1917-18 and again from 1939, the "
            "almanac and the database have summers in 1919 and 1921 (PRE1970_CONFLICTS).",
            chosen=_YEAR_WITHOUT_SUMMER, note_sources=('TZ2026E',)),
        _pre1970_window(
            _ut(1922, 1, 1), _ut(1939, 1, 1), -3600, '-01', ('IS1968BILL', 'ISALMANAC'),
            "Both chronologies agree there was no summer time after 1921 before 1939; the window ends at 1939's "
            "start, before that year's unverified first hour of summer time.", chosen=_YEAR_WITHOUT_SUMMER),
        _pre1970_window(
            _ut(1968, 4, 8), _ut(1970, 1, 1), 0, 'GMT', ('IS1968', 'IS1968BILL'),
            "The 1968 law put Iceland on Greenwich mean time all year from 7 April 1968 at 01:00 (02:00 UT); the "
            "window starts the day after.", chosen=_AFTER_LAW),
    ),
    'Europe/Monaco': (
        _pre1970_window(
            _ut(1892, 6, 2), _ut(1911, 3, 15), 561, 'PMT', ('MC1892', 'MC1911'),
            "Paris mean time, the legal time by the ordinance of 13 May 1892 from 1 June 1892, 'as in France, on "
            "the meridian of Paris'; the 1911 ordinance, signed 16 March and printed 28 March, ended it on its "
            "promulgation, so the window ends before the signing day. Monaco's own LMT would be 20 min 11 s off "
            "here. Monaco was refused before 1970 though its mean time was known; this window answers that, and the "
            "Vatican stays refused (PRE1970_REFUSAL_NOTES).",
            chosen=_AFTER_LAW, mean_time=True),
        _pre1970_window(
            _ut(1911, 4, 1), _ut(1916, 1, 1), 0, 'WET', ('MC1911',),
            "The 1911 ordinance ties Monaco to France's legal time as the law of 9 March 1911 fixes it, which "
            "does not carry the later French summer-time laws; the window starts after the month of its "
            "promulgation and ends before 1916.",
            chosen="the first day after the month its ordinance took effect in"),
    ),
    'Europe/Bratislava': (
        _pre1970_window(
            _ut(1946, 5, 6, 1), _ut(1946, 10, 6, 1), 7200, 'CEST', ('CS54', 'CS84', 'CS181'),
            "Summer time from 6 May 1946 at 02:00 Central European time (order 84/1946, under law 54/1946). "
            "Order 181/1946 has no territorial clause: it reaches Slovakia by inference, the order before it on "
            "the same page naming the Czech lands alone."),
        _pre1970_window(
            _ut(1946, 10, 6, 1), _ut(1946, 10, 7, 1), 7200, 'CEST', ('CS84', 'CS181'),
            "A correction: order 181/1946, read on the Gazette scan, ends summer time on 7 October "
            "at 03:00 summer time, 01:00 UT; the record ends it a day early.", note_sources=('TZ2026E',)),
        _pre1970_window(
            _ut(1946, 10, 7, 1), _ut(1946, 12, 1, 2), 3600, 'CET', ('CS54', 'CS181', 'CS213'),
            "Central European time between the summer and the winter time; the change back shows the local "
            "1946-10-07 02:00 to 02:59:59 twice."),
        _pre1970_window(
            _ut(1946, 12, 1, 2), _ut(1947, 2, 23, 2), 0, 'winter time', ('CS213',),
            "Winter time, +00:00, from 1 December 1946 03:00 Central European time to 23 February 1947 02:00 "
            "winter time (order 213/1946). The database's label for it, GMT, is its own (europe 1035-1036), and "
            "neither it nor its is_dst is copied: the label is the decision's plain words. The change shows the "
            "local 1946-12-01 02:00 to 02:59:59 twice.", note_sources=('TZ2026E',)),
    ),
    **{zone: (_pre1970_window(_ut(1949, 5, 2), _ut(1950, 1, 1), 3600, 'WAT', ('AEF1949MARCH', 'NBS1950'),
                              _AEF_NOTE, chosen=_AFTER_GAZETTE, note_sources=('NATURE1951',)),)
       for zone in ('Africa/Brazzaville', 'Africa/Bangui', 'Africa/Libreville')},
    'Pacific/Chuuk': (_pre1970_window(_ut(1941, 6, 17), _ut(1942, 1, 1), 32400, '+09',
                                      ('JAPAN1941TIME', 'JAPAN1922SCOPE'), _PACIFIC_NOTE.format('+10'),
                                      chosen=_AFTER_GAZETTE, note_sources=('JAPAN_PILOT_TIME',)),),
    'Pacific/Pohnpei': (_pre1970_window(_ut(1941, 6, 17), _ut(1942, 1, 1), 32400, '+09',
                                        ('JAPAN1922SCOPE', 'JAPAN1941TIME', 'JAPAN_PILOT_TIME'),
                                        _PACIFIC_NOTE.format('+11'), chosen=_AFTER_GAZETTE),),
    'Pacific/Majuro': (_pre1970_window(_ut(1941, 6, 17), _ut(1942, 1, 1), 32400, '+09',
                                       ('JAPAN1922SCOPE', 'JAPAN1941TIME', 'JAPAN_PILOT_TIME'),
                                       _PACIFIC_NOTE.format('+12'), chosen=_AFTER_GAZETTE),),
    'Pacific/Saipan': (_pre1970_window(_ut(1941, 6, 17), _ut(1942, 1, 1), 32400, '+09',
                                       ('JAPAN1922SCOPE', 'JAPAN1941TIME'),
                                       _PACIFIC_NOTE.format('+10') + " The 1934 notice put the Saipan branch on "
                                       "150 degrees E, +10, against the record's +09 from 1934 on "
                                       "(PRE1970_CONFLICTS).", chosen=_AFTER_GAZETTE,
                                       note_sources=('JAPAN_PILOT_TIME', 'JAPAN1934TIME')),),
    'America/St_Thomas': (
        _pre1970_window(
            _ut(1967, 12, 24, 4), _ut(1968, 1, 1), -14400, 'AST', ('US1966TIME', 'FR1967ATLANTIC'),
            "Both bounds are clips. The order took effect on 23 December 1967; the window "
            "starts at 00:00 Atlantic standard time the next day. The only seasonal rule ran from April to "
            "October, so none touches these days.", chosen=_AFTER_ORDER),
    ),
    'Africa/Djibouti': (
        _pre1970_window(
            _ut(1949, 3, 1), _ut(1950, 1, 1), 10800, 'EAT', ('DJ1949', 'NBS1950'),
            "Both bounds are clips. The arrete's text was read in an official electronic "
            "transcription; no page image of the gazette was found. NBS1950 and La Nature "
            "(NATURE1951) agree on +3. EAT is the database's label, not the act's.", chosen=_AFTER_GAZETTE,
            note_sources=('NATURE1951',)),
    ),
    'Indian/Mahe': (
        _pre1970_window(
            _ut(1907, 1, 2), _ut(1908, 1, 1), 14400, '+04', ('SEY1906',),
            "Both bounds are clips. The ordinance was brought into force on 1 January 1907 by "
            "both compilations' statement; the Governor's proclamation itself was not read. Both were read on the "
            "researcher's retained scans; the 1971 laws (SEY1971) carry the rule unchanged.",
            chosen=_AFTER_LAW, note_sources=('SEY1971',)),
    ),
    'America/Blanc-Sablon': (
        _pre1970_window(
            _ut(1966, 3, 16, 4), _ut(1970, 1, 1), -14400, 'AST', ('QC1966ACT', 'QC1969ACT', 'QC1978T6'),
            "Both bounds are clips. The 1966 act, in force on its sanction on 15 March 1966, "
            "put the province east of 68 degrees W on Atlantic standard time, the 1969 act east of 63 degrees W: "
            "the whole Lower North Shore either way, with no summer clause for it. Read on the researcher's "
            "retained scans. The claim of Shanks & Pottenger, which the database's notes "
            "report, that the region kept AST and ADT is unsourced and against the law (PRE1970_CONFLICTS). "
            "The window ends at 1970-01-01 00:00 UT, four hours before the local 1970: the local 1969-12-31 "
            "20:00 to 23:59:59 is refused.", chosen=_AFTER_LAW, note_sources=('TZ2026E',)),
    ),
}

# The stretch where the sources disagree: each with the offsets
# its conflicting readings give. A reading either offset puts inside it is
# refused ('disputed'), whatever window would hold it.
PRE1970_DISPUTED = {
    'Europe/Stockholm': (
        {'from': _ut(1916, 9, 30, 22), 'to': _ut(1916, 9, 30, 23), 'offsets': (3600, 7200),
         'sources': ('SE1916LAW', 'SE1926', 'SEDN1916'),
         'note': ("The statute's wording, 30 September ending an hour late (SE1916LAW, restated by SE1926), puts "
                  "the change at 22:00 UT, Central European time from then (+01:00); the newspaper the database "
                  "follows (SEDN1916) puts it at 23:00 UT, summer time to then (+02:00).")},
    ),
}

# The conflicts the checks recorded on these names, and how each is
# built (the notes go into the window notes and conflict rows).
PRE1970_CONFLICTS = (
    {'zone': 'Europe/Stockholm', 'when': '1916-09-30 22:00-23:00 UT',
     'conflict': "The statute's wording against the newspaper practice on the hour of the autumn change.",
     'sources': ('SE1916LAW', 'SE1926', 'SEDN1916'), 'built': 'Refused: PRE1970_DISPUTED.'},
    {'zone': 'Europe/Stockholm', 'when': '1879',
     'conflict': ("NBS1935's Table 1 lists Sweden under 1879 among the zone system's adopters, against the 1878 "
                  "law's mean time of three degrees west of Stockholm, 14 s from Central European time."),
     'sources': ('NBS1935', 'SE1979', 'SE1899'),
     'built': "Discounted as a weak secondary: Swedish time is cast."},
    {'zone': 'Europe/Oslo', 'when': '1940-1945',
     'conflict': "NO2018 gives summer time in 1943-45, SE1979 in 1940-45.",
     'sources': ('NO2018', 'SE1979'), 'built': 'No window: 1940 to 1946 stays refused.'},
    {'zone': 'Europe/Amsterdam', 'when': '1909-1916',
     'conflict': ("The 1909 report's Greenwich time plus 19 m 32.13 s, and the 1916 law's midnight at +00:19:32, "
                  "against van Gent's rounded 20 minutes usually applied."),
     'sources': ('NLOBS1909', 'NL1916', 'NLGENT'), 'built': '+00:19:32, as the decision rules and IANA has it.'},
    {'zone': 'Europe/Luxembourg', 'when': '1929-04-20 23:00 UT on',
     'conflict': ("The 1929 decree makes Central European time the legal time again, where the database labels "
                  "the stretch WEST, a summer time."),
     'sources': ('LU1929', 'TZ2026E'), 'built': 'No window rests on it: the label only, the offset agrees.'},
    {'zone': 'Europe/Luxembourg', 'when': '1937-10-03 00:00-02:00 UT',
     'conflict': "The decree's change at 01:00 summer time against the record's 02:00 UT.",
     'sources': ('LU1937', 'TZ2026E'), 'built': 'Corrected: a WET window from 00:00 UT.'},
    {'zone': 'Europe/Bratislava', 'when': '1946-10-06 01:00 UT to 1946-10-07 01:00 UT',
     'conflict': "Order 181/1946 ends summer time on 7 October; the record ends it on 6 October.",
     'sources': ('CS181', 'TZ2026E'), 'built': 'Corrected: a CEST window for the day.'},
    {'zone': 'Atlantic/Reykjavik', 'when': '1919 and 1921',
     'conflict': ("The 1968 bill has summer time in 1917-18 and again from 1939; the almanac and the database "
                  "have summers from 20 February to 16 November 1919 and from 20 March to 23 June 1921."),
     'sources': ('IS1968BILL', 'ISALMANAC', 'TZ2026E'), 'built': 'No window in 1919 or 1921.'},
    {'zone': 'Pacific/Saipan', 'when': '1934 on',
     'conflict': ("The 1934 notice puts the Saipan branch on 150 degrees E, +10, and NBS1935 gives the Marianas "
                  "+10, against the record's +09 from 1901 to 1944; NBS1950 gives the Marianas +09."),
     'sources': ('JAPAN1934TIME', 'NBS1935', 'NBS1950', 'TZ2026E'),
     'built': 'Outside the window, which rests on the 1941 notice alone.'},
    {'zone': 'America/Blanc-Sablon', 'when': '1966-1969',
     'conflict': ("Shanks & Pottenger, as the database's notes report, have this region keeping AST and ADT; "
                  "the 1966 and 1969 acts put it on Atlantic standard time with no summer clause."),
     'sources': ('TZ2026E', 'QC1966ACT', 'QC1969ACT'),
     'built': "The law is followed: AST all year in the window."},
)

# Notes on linked names with no window, kept with the name.
PRE1970_REFUSAL_NOTES = {
    'America/Curacao': (
        "The Amigoe of 29 December 1964 reports that the clocks of the Leeward islands would go forward half an "
        "hour at the new year, under a decree the paper had not seen; nothing covers 1965-69. Cited for Aruba "
        "but bearing on Curacao: a refusal, no window.", ('AMIGOE1964DEC29',)),
    'Pacific/Wallis': (
        "The 1948 order is a lead only, known through a search-engine copy, and its identity is unconfirmed (a "
        "ministerial arrete of 26 November 1948 by its title, a decree of 6 December 1948 by its link): no "
        "window.", ('WALLIS1948LEAD',)),
    'Asia/Phnom_Penh': (
        "Milne's 1899 Saigon time, 'used in Lower Laos, Cambodia, Annam', is an 1899 snapshot with no bounds; "
        "the researcher read it as +7:16:35, the check reads 7 h 16 m 56 s fast on the scan: no window.",
        ('MILNE1899',)),
    'Europe/Vatican': (
        "Nothing read covers 1929-1970 but the 1966 summer time, and the state did not exist before 1929: it "
        "stays refused.", ('VAT1966',)),
}

del _STOCKHOLM_LAW, _PACIFIC_NOTE, _AEF_NOTE, _AFTER_LAW, _AFTER_GAZETTE, _YEAR_WITHOUT_SUMMER, _AFTER_ORDER
del _pre1970_window, _ut

# The other links of the same release that name a zone the tables below key
# on: another name for that zone, with no row of its own in zone.tab
# (Asia/Calcutta for Asia/Kolkata, Europe/Kiev for Europe/Kyiv), read as that
# zone -- "cast as its zone", above -- by named_zone_state, whose tables are
# keyed on the zone's own name (else Asia/Calcutta 1880 was cast at MMT,
# unlabelled, where Asia/Kolkata is refused). Derived from
# the same pinned package as LINKED_ZONES: a test holds it to the release's
# tzdata.zi. Timezonefinder answers none of these names; a caller may.
ZONE_ALIASES = {
    'America/Argentina/ComodRivadavia': 'America/Argentina/Catamarca',
    'America/Buenos_Aires': 'America/Argentina/Buenos_Aires', 'America/Catamarca': 'America/Argentina/Catamarca',
    'America/Coral_Harbour': 'America/Panama', 'America/Cordoba': 'America/Argentina/Cordoba',
    'America/Jujuy': 'America/Argentina/Jujuy', 'America/Mendoza': 'America/Argentina/Mendoza',
    'America/Rosario': 'America/Argentina/Cordoba', 'Antarctica/South_Pole': 'Pacific/Auckland',
    'Asia/Calcutta': 'Asia/Kolkata', 'Asia/Dacca': 'Asia/Dhaka', 'Asia/Istanbul': 'Europe/Istanbul',
    'Asia/Rangoon': 'Asia/Yangon', 'Asia/Saigon': 'Asia/Ho_Chi_Minh', 'Asia/Tel_Aviv': 'Asia/Jerusalem',
    'Asia/Ujung_Pandang': 'Asia/Makassar', 'CET': 'Europe/Brussels', 'Canada/Newfoundland': 'America/St_Johns',
    'Chile/Continental': 'America/Santiago', 'Chile/EasterIsland': 'Pacific/Easter', 'Cuba': 'America/Havana',
    'EET': 'Europe/Athens', 'EST': 'America/Panama', 'Eire': 'Europe/Dublin', 'Europe/Kiev': 'Europe/Kyiv',
    'Europe/Tiraspol': 'Europe/Chisinau', 'Europe/Uzhgorod': 'Europe/Kyiv', 'Europe/Zaporozhye': 'Europe/Kyiv',
    'Iran': 'Asia/Tehran', 'Israel': 'Asia/Jerusalem', 'Jamaica': 'America/Jamaica', 'MET': 'Europe/Brussels',
    'NZ': 'Pacific/Auckland', 'Pacific/Truk': 'Pacific/Port_Moresby', 'Pacific/Yap': 'Pacific/Port_Moresby',
    'Poland': 'Europe/Warsaw', 'Singapore': 'Asia/Singapore', 'Turkey': 'Europe/Istanbul', 'W-SU': 'Europe/Moscow'
}


# The first-record rule's reach: the named mean times. After a zone's first
# record (its reference city's LMT, which that rule refuses) many zones hold a
# city's named mean time -- PMT, RMT, MMT -- before
# any standard time. Such a time is CAST, with a label, only where it was the
# area's civil clock (CIVIL_MEAN_TIMES, keyed on the name the place lookup
# returns and on the period); everywhere else it is REFUSED as LMT is,
# since it puts one city's meridian under every birthplace of the zone. The
# lists below are the research's, in one place (79 zones, their named
# states, their groups and sources), read against the compiled zones zoneinfo
# reads. The database's own scope statement is the reason for the default:
# a zone's pre-1970 entries "are often accurate for only a small subset of
# that region" (theory.html:690-692).
#
# The test is applied strictly: a named mean time is cast only for the
# stretches the
# database's own notes establish as the area's civil clock, and the rest is
# refused as uncertain. The notes are read in the source of the IANA release
# the pinned tzdata package is built from (2026e); every
# file:line in these comments is that release's.
#
# NAMED_MEAN_TIMES: each zone whose record holds a named mean time after its
# first record, with the states (abbreviation, offset) of that stretch,
# including the summer forms the database names with them (Dublin's IST,
# Riga's LST, Moscow's MST and MDST, Bermuda's and La Paz's BST), each written
# with the mean time it is kept on, which its label names. A reading is
# matched on its own state, so a stretch of standard time between two named
# stretches (Chile 1910-1916, Tallinn 1918-1919) is not touched. A linked
# name is looked up through its target; before 1970 it is refused first,
# or its windows read it (PRE1970_WINDOWS) and this table is not reached.
# The database's NST of 1884-1935 is St John's mean time, -3:30:52, under a
# standard time's name ("Zone America/St_Johns -3:30:52 - LMT 1884" then
# "-3:30:52 StJohns N%sT ... 1935 Mar 30", northamerica:1464-1467; Goose Bay
# casts Labrador at it, northamerica:1477-1480): it is classed by
# the same test, so it is listed here with its summer form, NDT.
def _mean_time_states(table):
    """{zone: {(abbreviation, offset seconds): the mean time a summer form is
    kept on, or None for a mean time itself}} from 'ABBR +H:MM:SS[ ON]'."""
    def seconds(text):
        sign = -1 if text.startswith('-') else 1
        h, m, s = (int(part) for part in text.lstrip('+-').split(':'))
        return sign * (h * 3600 + m * 60 + s)
    out = {}
    for zone, states in table.items():
        out[zone] = {}
        for state in states.split(', '):
            abbr, offset, *kept_on = state.split()
            out[zone][(abbr, seconds(offset))] = kept_on[0] if kept_on else None
    return out


NAMED_MEAN_TIMES = _mean_time_states({
    'Africa/Algiers': 'PMT +0:09:21', 'Africa/Monrovia': 'MMT -0:43:08, MMT -0:44:30',
    'Africa/Tunis': 'PMT +0:09:21',
    **{f'America/Argentina/{city}': 'CMT -4:16:48' for city in (
        'Buenos_Aires', 'Catamarca', 'Cordoba', 'Jujuy', 'La_Rioja', 'Mendoza', 'Rio_Gallegos', 'Salta',
        'San_Juan', 'San_Luis', 'Tucuman', 'Ushuaia')},
    'America/Asuncion': 'AMT -3:50:40', 'America/Bogota': 'BMT -4:56:16', 'America/Caracas': 'CMT -4:27:40',
    'America/Costa_Rica': 'SJMT -5:36:13', 'America/Coyhaique': 'SMT -4:42:45',
    'America/Grand_Turk': 'KMT -5:07:10', 'America/Guayaquil': 'QMT -5:14:00', 'America/Havana': 'HMT -5:29:36',
    'America/Jamaica': 'KMT -5:07:10', 'America/La_Paz': 'CMT -4:32:36, BST -3:32:36 CMT',
    'America/Managua': 'MMT -5:45:12', 'America/Martinique': 'FFMT -4:04:20',
    'America/Montevideo': 'MMT -3:44:51', 'America/Panama': 'CMT -5:19:36',
    'America/Paramaribo': 'PMT -3:40:52, PMT -3:40:36', 'America/Port-au-Prince': 'PPMT -4:49:00',
    'America/Punta_Arenas': 'SMT -4:42:45', 'America/Santiago': 'SMT -4:42:45',
    'America/Santo_Domingo': 'SDMT -4:40:00',
    'America/St_Johns': 'NST -3:30:52, NDT -2:30:52 NST', 'America/Goose_Bay': 'NST -3:30:52, NDT -2:30:52 NST',
    'Asia/Baghdad': 'BMT +2:57:36', 'Asia/Bangkok': 'BMT +6:42:04', 'Asia/Colombo': 'MMT +5:19:32',
    'Asia/Dhaka': 'HMT +5:53:20', 'Asia/Ho_Chi_Minh': 'PLMT +7:06:30', 'Asia/Irkutsk': 'IMT +6:57:05',
    'Asia/Jakarta': 'BMT +7:07:12', 'Asia/Jerusalem': 'JMT +2:20:40',
    'Asia/Kolkata': 'HMT +5:53:20, MMT +5:21:10', 'Asia/Makassar': 'MMT +7:57:36',
    'Asia/Pontianak': 'PMT +7:17:20', 'Asia/Singapore': 'SMT +6:55:25', 'Asia/Tbilisi': 'TBMT +2:59:11',
    'Asia/Tehran': 'TMT +3:25:44', 'Asia/Yangon': 'RMT +6:24:47', 'Asia/Yekaterinburg': 'PMT +3:45:05',
    'Atlantic/Azores': 'HMT -1:54:32', 'Atlantic/Bermuda': 'BMT -4:19:18, BST -3:19:18 BMT',
    'Atlantic/Madeira': 'FMT -1:07:36', 'Atlantic/Stanley': 'SMT -3:51:24',
    'Europe/Athens': 'AMT +1:34:52', 'Europe/Brussels': 'BMT +0:17:30', 'Europe/Bucharest': 'BMT +1:44:24',
    'Europe/Chisinau': 'CMT +1:55:00, BMT +1:44:24', 'Europe/Dublin': 'DMT -0:25:21, IST +0:34:39 DMT',
    'Europe/Helsinki': 'HMT +1:39:49', 'Europe/Istanbul': 'IMT +1:56:56', 'Europe/Kyiv': 'KMT +2:02:04',
    'Europe/Minsk': 'MMT +1:50:00',
    'Europe/Moscow': 'MMT +2:30:17, MMT +2:31:19, MST +3:31:19 MMT, MDST +4:31:19 MMT',
    'Europe/Paris': 'PMT +0:09:21', 'Europe/Prague': 'PMT +0:57:44', 'Europe/Riga': 'RMT +1:36:34, LST +2:36:34 RMT',
    'Europe/Rome': 'RMT +0:49:56', 'Europe/Simferopol': 'SMT +2:16:00', 'Europe/Sofia': 'IMT +1:56:56',
    'Europe/Tallinn': 'TMT +1:39:00', 'Europe/Vilnius': 'WMT +1:24:00, KMT +1:35:36',
    'Europe/Warsaw': 'WMT +1:24:00', 'Europe/Zurich': 'BMT +0:29:46',
    'Indian/Maldives': 'MMT +4:54:00', 'Pacific/Auckland': 'NZMT +11:30:00', 'Pacific/Bougainville': 'PMMT +9:48:32',
    'Pacific/Easter': 'EMT -7:17:28', 'Pacific/Port_Moresby': 'PMMT +9:48:32',
})

# CIVIL_MEAN_TIMES: where a named mean time was the area's civil clock, keyed
# on the name the place lookup returns; the value is the first local date of
# the period it is cast in (None: the whole stretch). Of the research's
# group (a), the civil clocks, it keeps only what the database's notes
# establish, each stretch beginning where its evidence does: a law's or an
# official table's own date, or, where the source is dated only by its month
# or its year, the first day after that month or year (before it, the source
# vouches for nothing yet). Cast:
#   Europe/Paris, PMT from its start: the law "was published on 1891-03-15, so
#     it could only take force on 1891-03-16" (europe:1364-1365); legal time
#     outside railway stations until 1911 (europe:1394-1400).
#   Europe/Dublin, DMT (and its summer IST) from its start, "the legal
#     transition time" of 1880-08-02 (europe:146-151).
#   America/Santiago, Punta_Arenas, Coyhaique, SMT from 1916-07-01: "Chile's
#     official time from 1916 to 1919" and the official table of changes since
#     1900 (southamerica:1104-1110, 1127-1131); for 1890-1910 the notes only
#     "guess that in practice this was the same offset as in 1916-1919"
#     (southamerica:1099-1101), refused.
#   America/Montevideo, MMT from its start: "Ley No. 3920 of 1908-06-10 placed
#     the determination of legal time" under a national institute
#     (southamerica:1855-1863).
#   America/Jamaica, KMT from 1899-03-01: Milne records it "from an unspecified
#     official document, and says 'This time is used throughout the island'"
#     (northamerica:3783-3786), in a paper of February 1899
#     (northamerica:1259); 1890 is only the record's boundary, refused.
#   Atlantic/Bermuda, BMT (and its summer BST) from 1917-04-02: the clock
#     tower's offset "agrees with standard offset given in the Daylight Saving
#     Act, 1917", of 1917-04-02 (northamerica:3254-3256, 3270); "It is not
#     known when this time became standard for Bermuda; guess 1890"
#     (northamerica:3257), refused before the Act.
#   Asia/Ho_Chi_Minh, PLMT from its start: "The 1906 transition was effective
#     July 1 and standardized Indochina" (asia:4177-4178).
#   The twelve America/Argentina zones, CMT from its start: "standard time in
#     Argentina from 1894-10-31 to 1920-05-01 was -4:16:48.25"
#     (southamerica:207-213).
#   Africa/Monrovia, -0:44:30 from 1970-01-01: "The Nautical Almanac for the
#     Year 1970, p 264, is the source for -0:44:30" (africa:428), and "In 1972
#     Liberia was the last country to switch from a UT offset that was not a
#     multiple of 15 or 20 minutes" (africa:430-431). The record's "1919 Mar"
#     is only a boundary, its line "approximately MMT" (africa:443), and the
#     earlier -0:43:08 is unsourced: refused before 1970.
#   Europe/Rome, RMT from 1887-01-01: in force from 1866-12-12 "in the
#     railways, the post office and the telegraph, not only for the internal
#     service but also for the public" (europe:1729-1734) -- service time, as
#     Zurich's postal and telegraph time is -- the public clocks following
#     city by city, "and the last city was Cagliari in 1886"
#     (europe:1734-1737). So the mainland is cast from the first day after
#     that year; Milan, Turin, Bologna and Venice from their
#     own dates by coordinates (MEAN_TIME_CITY_DATES); Sicily and Sardinia
#     refused (MEAN_TIME_EXCEPTIONS); Trentino, South Tyrol, Trieste and
#     Gorizia refused (MEAN_TIME_OUTSIDE).
#   Pacific/Auckland, NZMT from its start: "the introduction of standard time
#     in New Zealand" at +11:30 (australasia:983, 1697-1698).
#   Pacific/Easter, EMT from 1891-01-01: Shanks & Pottenger say "Pacific/Easter
#     standardized on 109W22 in 1890" (southamerica:1101-1102), the island's
#     standard time on one secondary source, as Argentina's is on one; the year
#     only, so from the first day after it (Easter weighed by the same
#     threshold).
# Refused, though the research put them in group (a):
#   Europe/Riga, RMT (and its summer LST) 1880-1926, and Asia/Tbilisi, TBMT
#     1880-1924: "Byalokoz 1919 says Latvia was 1:36:34" (europe:1896-1898),
#     "Byalokoz 1919 says Georgia was 2:59:11" (asia:1194-1196). Byalokoz's
#     book gives the clocks Russia's decree of 1919-07-01 replaced
#     (europe:47-55): a country-wide value at some time before mid-1919, with
#     neither a start nor an end, so no stretch is established (as
#     Zurich).
#   Europe/Zurich, BMT 1853-1894: the record's 1853-07-16 models "postal and
#     telegraph time", "legal civil time probably changed at still some other
#     transition date", and "the Swiss did not agree about civil time during
#     the transition" (europe:3797-3814); no note dates the civil clock.
#   Africa/Algiers, PMT 1891-1911: the notes say only "See Europe/Paris for
#     PMT-related transitions" (africa:91) and "There are similar problems in
#     Algiers, Monaco and Tunis" (europe:1409-1410), not that the zone's area
#     kept Paris's time.
# The rest of NAMED_MEAN_TIMES -- group (b), the reference city's clock only
# (Asia/Kolkata, Europe/Moscow, Asia/Tehran), group (c), the zones the notes
# leave unclear, and St John's NST (the Newfoundland notes,
# northamerica:1404-1436, date only summer-time rules, and their one Labrador
# statement is of 2017) -- is refused. Europe/Monaco's Paris mean time of
# 1892-1911, which the research also counts in group (a), is cast in its own
# window, not here (PRE1970_WINDOWS); Europe/Vatican, counted
# there too, is a linked name still refused before 1970.
CIVIL_MEAN_TIMES = {
    'Europe/Paris': None, 'Europe/Dublin': None,
    'America/Santiago': (1916, 7, 1), 'America/Punta_Arenas': (1916, 7, 1), 'America/Coyhaique': (1916, 7, 1),
    'America/Montevideo': None, 'America/Jamaica': (1899, 3, 1), 'Atlantic/Bermuda': (1917, 4, 2),
    'Asia/Ho_Chi_Minh': None,
    **{f'America/Argentina/{city}': None for city in (
        'Buenos_Aires', 'Catamarca', 'Cordoba', 'Jujuy', 'La_Rioja', 'Mendoza', 'Rio_Gallegos', 'Salta',
        'San_Juan', 'San_Luis', 'Tucuman', 'Ushuaia')},
    'Africa/Monrovia': (1970, 1, 1),
    'Europe/Rome': (1887, 1, 1),
    'Pacific/Auckland': None, 'Pacific/Easter': (1891, 1, 1),
}

# The cross-check's rule (an attestation date "can be a
# conservative ... policy choice, but must be labeled as such"): where a
# stretch's first day is this app's choice -- the first day after a source
# dated only by its month or year -- the label says so, with the date it
# chose and why. Not where the notes give the day (Paris, Dublin, Chile,
# Montevideo, Bermuda's Act, Indochina, Argentina, Monrovia's Almanac year,
# Auckland, the four Italian cities).
CHOSEN_STARTS = {
    'America/Jamaica': "the first day after February 1899, the month the database gives for its source",
    'Pacific/Easter': "the first day after 1890, the only date the database's source gives",
    'Europe/Rome': "the first day after 1886, the year the database's notes give for the last city's public clocks",
}

# The three outline tables below -- MEAN_TIME_EXCEPTIONS, MEAN_TIME_CITY_DATES
# and MEAN_TIME_OUTSIDE -- are data, not code: an edited OpenStreetMap
# derivative, published whole as data/mean_time_outlines.json under the Open
# Database License with its notice beside it (data/NOTICE-ODBL.md), apart
# from the code's AGPL. The file's own "schema" says
# what each field holds; how each outline was drawn, and the OpenStreetMap
# objects it was taken from where the records name them, are in the file
# with it. The file is read once, here, with the standard library only, and
# turned back into exactly the structures the tables always were: for each
# zone a tuple of areas, (name, the year or the date or the country, rings),
# each ring a tuple of (latitude, longitude) pairs. The file writes each
# vertex [latitude, longitude], latitude first -- the reverse of GeoJSON's
# order -- and every number is a float read back exactly as it was written.
# A frozen build carries the file in a data folder beside this module
# (build.spec).
def _read_outline_tables():
    """{'exceptions': ..., 'cities': ..., 'outside': ...} from the data file."""
    tables = json.loads(_shipped_file_bytes('data/mean_time_outlines.json').decode('utf-8'))['tables']

    def rings(area):
        return tuple(tuple((lat, lon) for lat, lon in ring) for ring in area['rings'])

    def zones(name, second):
        return {zone: tuple((area['area'], second(area), rings(area)) for area in areas)
                for zone, areas in tables[name]['zones'].items()}

    return {'exceptions': zones('exceptions', lambda area: area['until']),
            'cities': zones('cities', lambda area: tuple(area['since'])),
            'outside': zones('outside', lambda area: area['country'])}


_OUTLINE_TABLES = _read_outline_tables()

# Rome's and Zurich's exceptions inside group (a), refused by coordinates:
# "Sicily and Sardinia each had their own time zones from 1866 to 1893"
# (europe:1718-1719), and "Between 1848 and 1894 Geneva did not follow Bern
# Mean Time but kept its own local mean time" (europe:3777-3778). The notes
# say "Sicily"; the polygon is Sicily and its islands -- the Region's
# Aeolians, Ustica, Egadi, Pantelleria and Pelagie (Lampedusa) -- this app's
# reading, which errs, where it errs, toward refusal; "Sardinia" is Sardinia
# with its islands. Each area is a
# set of rings of (latitude, longitude) vertices, drawn wide over the sea and over
# the neighbouring countries (whose points are in another zone, so the test
# never reaches them) and close only where the area meets the rest of its own
# zone: the Strait of Messina's middle, and the canton's border with Vaud,
# with the canton's two pieces at Celigny. The vertices are this app's
# drawing: the dozen along the border with Vaud are rounded from the cantons'
# boundaries as OpenStreetMap draws them ((c) OpenStreetMap contributors,
# ODbL), against which the polygons were also checked. The year is the last of the
# exception, for the page. An exception is read before the zone's own period
# (CIVIL_MEAN_TIMES), so the canton of Geneva keeps its own sentence now that
# Bern mean time is refused throughout.
MEAN_TIME_EXCEPTIONS = _OUTLINE_TABLES['exceptions']

# Rome by city adoption dates: Rome's time reached the public clocks city by
# city -- "Milano set
# the public watches on the Rome time on the same day (12th December 1866),
# Torino and Bologna on the 1st January 1867, Venezia the 1st May 1880"
# (europe:1734-1736) -- so inside each of these cities, found by the
# coordinates, RMT is cast from the city's own date, earlier than the rest of
# the mainland's 1887-01-01 (CIVIL_MEAN_TIMES), and a reading before that
# date is refused ('mean_time_city'). What each kept before is not said, so
# the page says only when its public clocks took Rome's time. Each area is a
# set of rings of (latitude, longitude) vertices, today's, not the cities' of
# 1866-1880 (redrawing them as they were is later work): Milan, Turin and
# Bologna, each
# municipality's boundary as OpenStreetMap draws it ((c) OpenStreetMap
# contributors, ODbL), simplified to within about 130 m (Turin with the small
# detached piece of its territory); Venice, the lagoon city with its islands
# from Murano and the Vignole to the Lido and Malamocco, drawn over the
# lagoon, kept off the mainland (Mestre, Marghera, Fusina, Punta Sabbioni),
# off Pellestrina, and round Sant'Erasmo and the Lazzaretto Nuovo, so that no
# island is cut.
MEAN_TIME_CITY_DATES = _OUTLINE_TABLES['cities']

# Places a zone covers today that were not then part of the
# country whose clocks its notes describe. The notes speak of France's law and
# Italy's decree and say nothing of Alsace, Lorraine's Moselle, Trentino,
# South Tyrol, Trieste or Gorizia (no such name in the europe file); so a
# reading there under Paris's or Rome's mean time is refused
# ('mean_time_outside'), by coordinates, inside today's borders (redrawing
# them as they were is later work). Each area is today's departments (Bas-Rhin,
# Haut-Rhin, Moselle) or provinces (Trento and Bolzano; Trieste and Gorizia)
# as OpenStreetMap draws them ((c) OpenStreetMap contributors, ODbL), joined:
# the border with the rest of the country simplified to within about 300 m,
# and the border with another country replaced by a line drawn wide through
# that country, whose points are in another zone and never reach this test;
# five islets of the Grado lagoon and Trieste's harbour are small boxes.
MEAN_TIME_OUTSIDE = _OUTLINE_TABLES['outside']

# After the mean time, Paris's
# and Rome's records cast France's and Italy's clocks on the places of
# MEAN_TIME_OUTSIDE, which then belonged to neither country or whose clocks
# the sources do not establish. Those stretches are REFUSED there too
# ('outside_clock'), by coordinates; the cast elsewhere is unchanged. The
# bounds are UT instants, half-open:
#   Alsace-Moselle: from Paris's switch to WET -- the record's "0:09:21 - PMT
#     1911 Mar 11" (europe:1493), 1911-03-10 23:50:39 UT, where D1R2's
#     refusal of PMT there ends -- to 1921-01-01, through the French years
#     1919-1920, which the sources make only likely for the area.
#   Trentino, South Tyrol, Trieste and Gorizia: from the end of Rome mean
#     time -- the record's "0:49:56 - RMT 1893 Oct 31 23:00u" (europe:1829),
#     1893-10-31 23:00 UT, where D1R2's refusal of RMT there ends -- to
#     1921-01-01, whole, not only where Rome's summer dates differ from
#     Vienna's.
# Each start is the record's own instant, so the refusal joins the mean-time
# refusal before it with no gap (the test
# tests/test_d1r3_annexed_wrong_casts_2026_10_06.py reads both starts from the
# pinned record again). The end, 1921-01-01 00:00 UT, is a conservative bound
# of this app's choosing (the research's guard), not a dated change of clock.
# Replacing the bounds and the borders when sources date them is later work;
# formerly Austrian places outside today's four provinces wait for it too.
OUTSIDE_STRETCHES = {
    'Europe/Paris': {'Alsace-Moselle': ((datetime(1911, 3, 10, 23, 50, 39, tzinfo=timezone.utc),
                                         datetime(1921, 1, 1, tzinfo=timezone.utc)),)},
    'Europe/Rome': {
        'Trentino and South Tyrol': ((datetime(1893, 10, 31, 23, 0, tzinfo=timezone.utc),
                                      datetime(1921, 1, 1, tzinfo=timezone.utc)),),
        'Trieste and Gorizia': ((datetime(1893, 10, 31, 23, 0, tzinfo=timezone.utc),
                                 datetime(1921, 1, 1, tzinfo=timezone.utc)),),
    },
}


# The one zone whose record, after keeping another time, returns to exactly
# its first state: Lagos's own LMT again from 1908-07-01, after GMT from 1905
# (research section 1b; africa:1145-1147). A reading there is a later line of
# local mean time, not one before the zone kept any time of its own, and is
# refused with that line's sentence. (Lisbon's record repeats its first state
# from 1884 without keeping anything else between: that is its first record.)
LMT_RETURNS = {'Africa/Lagos': (1908, 7, 1)}


def _inside_area(latitude, longitude, rings):
    """Whether a point lies inside any of the area's rings (crossing count)."""
    for ring in rings:
        inside = False
        for (lat_a, lon_a), (lat_b, lon_b) in zip(ring, ring[1:] + ring[:1]):
            if (lat_a > latitude) != (lat_b > latitude):
                cross = lon_a + (latitude - lat_a) * (lon_b - lon_a) / (lat_b - lat_a)
                if longitude < cross:
                    inside = not inside
        if inside:
            return True
    return False


def civil_mean_time_label(abbreviation, kept_on=None, chosen=None):
    """What a cast at a named mean time kept as a civil clock says of itself.
    A summer form (Dublin's IST, Bermuda's BST) is not itself a mean time: it
    names the mean time it was kept on. `chosen` is (first day, why) where
    that day is this app's choice (CHOSEN_STARTS); a
    pre-1970 window gives its first moment written out, in UT."""
    if kept_on:
        label = (f"{abbreviation}, summer time kept on {kept_on} (a named mean time), was then the civil clock "
                 "across this area")
    else:
        label = f"{abbreviation}, a named mean time, was then the civil clock across this area"
    if chosen:
        start, why = chosen
        when = start if isinstance(start, str) else '%04d-%02d-%02d' % start
        label += f"; the date it is cast from here, {when}, is this app's choice: {why}"
    return label


def mean_time_held(abbreviation, kept_on=None):
    """What a refusal says the record holds: the named mean time itself, or a
    summer form with the mean time it was kept on (Riga's LST on RMT, St
    John's NDT on NST), which is not itself a mean time."""
    return f"{abbreviation}, summer time kept on {kept_on}" if kept_on else abbreviation


# A named mean time the database writes under a standard time's name: its
# NST of 1884-1935 is St John's mean time, -3:30:52 ("Zone America/St_Johns
# -3:30:52 - LMT 1884" then "-3:30:52 StJohns N%sT ... 1935 Mar 30",
# northamerica:1464-1467). A reader who knows NST as a
# standard time is told whose meridian it is.
MEAN_TIMES_UNDER_STANDARD_NAMES = {'NST': "St John's"}


def mean_time_whose(abbreviation, kept_on=None):
    """What follows "a mean time taken from one place's meridian" in a
    refusal, where the mean time goes by a standard time's name: the place,
    and that the name is a standard time's. Empty elsewhere."""
    place = MEAN_TIMES_UNDER_STANDARD_NAMES.get(kept_on or abbreviation)
    return f" ({place}, under the name of a standard time)" if place else ""


class NamedZoneRefusal(Exception):
    """A named zone cannot place a local clock reading; `kind` says why.

    The kinds: 'unknown' (the zone's name is not in the time-zone database
    this installation carries), 'sea' (a nautical Etc/GMT zone or the like, which is a
    band of ocean and not a place), 'linked' (a reading before 1970 in a zone
    the database keeps only as a link to another place's record:
    LINKED_ZONES), 'julian' (a Julian-only day, which a
    datetime cannot carry), 'before_rules' (the zone's records have not yet
    begun to keep any standard time at that moment), 'later_lmt' (the
    record holds a later line of local mean time: LMT_RETURNS), 'mean_time' (a named mean time that was not the area's
    civil clock then: NAMED_MEAN_TIMES outside CIVIL_MEAN_TIMES),
    'mean_time_exception' (a named mean time that was the area's clock, but
    not in the part of it the coordinates fall in: MEAN_TIME_EXCEPTIONS),
    'mean_time_city' (a named mean time that was the area's clock, inside a
    city whose public clocks took it later: MEAN_TIME_CITY_DATES),
    'mean_time_outside' (a named mean time read in a part of the zone the
    notes on its country never speak of: MEAN_TIME_OUTSIDE),
    'outside_clock' (that part, in a stretch where the record casts the
    country's clock and the sources do not show which clock the place kept:
    OUTSIDE_STRETCHES), 'ambiguous' (the repeated hour of a fall-back) and 'nonexistent' (the
    skipped hour of a spring-forward), and 'disputed' (a reading in a
    stretch where the sources disagree on when the clocks were turned back:
    PRE1970_DISPUTED). The mean-time kinds carry the
    `abbreviation` and, for a summer form, the mean time it was `kept_on`;
    the exception its `area` and the last year `until`; the city its `area`
    and the first day it is cast, `since`; the part outside the country its
    `area` and the `country`, and so does 'outside_clock'. 'before_rules' carries the
    `abbreviation` of the record's first state: where that is '-00', the
    database's mark for a place while uninhabited (theory.html:584-588) --
    at a record's start, or where Davis, Macquarie and Vostok return to it --
    the record holds no time there, and the refusal says so rather than "before ... kept any standard time".
    An 'ambiguous' or 'nonexistent' reading at a place with clocks of its
    own (PLACE_CLOCKS) is the place's fold or gap, not the zone's: it carries
    the `place`'s name, whose clocks were set back or jumped; any other
    refusal carries None, the class's own, and holds no more than it did."""

    place = None

    def __init__(self, kind, *, abbreviation=None, area=None, until=None, since=None, kept_on=None, country=None,
                 place=None):
        super().__init__(kind)
        self.kind = kind
        self.abbreviation = abbreviation
        self.area = area
        self.until = until
        self.since = since
        self.kept_on = kept_on
        self.country = country
        if place is not None:
            self.place = place


class PlaceClockRefusal(NamedZoneRefusal):
    """A Standard-time cast refused by the place rather than the zone
    (place_zone, below): 'clock_choice' (a place where the sources leave the
    clock to the record: the `area` rule's two `clocks` differ at that
    moment, or the moment is in an `interval` the sources leave unsettled,
    or in a stretch a place's own clocks leave disputed, PLACE_CLOCKS, which
    names no `clocks`) and 'unsettled' (a listed place no source settles:
    the `clocks` the sources give it). `clocks` is ((zone, offset in seconds
    or None), (zone, offset or None)), each clock read at the moment, or
    empty; `interval` is (start, end), local readings, the start (1, 1, 1,
    0, 0, 0) for "before"."""

    def __init__(self, kind, *, area=None, clocks=(), interval=None):
        super().__init__(kind, area=area)
        self.clocks = clocks
        self.interval = interval


def _pre1970_cast(window):
    """The state a pre-1970 window gives: its offset and its label, with a
    named mean time's sentence (civil_mean_time_label), or, for a standard
    time whose start is a clip, a sentence that opens with the clock and
    says its first day is this app's choice."""
    start = window['from']
    since = (f"{start.year:04d}-{start.month:02d}-{start.day:02d} "
             f"{start.hour:02d}:{start.minute:02d} UT")
    chosen = (since, window['chosen']) if window['chosen'] else None
    state = {'offset_seconds': window['offset_seconds'], 'abbreviation': window['abbreviation']}
    if window['mean_time']:
        state['civil_mean_time'] = True
        state['label'] = civil_mean_time_label(window['abbreviation'], None, chosen)
    elif chosen:
        state['label'] = (f"The clock here was then {window['abbreviation']}; the date it is cast from here, "
                          f"{since}, is this app's choice: {window['chosen']}")
    return state


def _pre1970_state(zone_name, year, month, day, hour, minute, second):
    """A linked name's reading before 1970, read against its windows alone
    (PRE1970_WINDOWS; named_zone_state's docstring gives the rule)."""
    try:
        reading = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    except ValueError:
        raise NamedZoneRefusal('julian')
    earliest, latest = datetime.min.replace(tzinfo=timezone.utc), datetime.max.replace(tzinfo=timezone.utc)

    def inside(start, end, offset):
        """Whether the reading, read at `offset`, names an instant in
        [start, end); a reading at the calendar's ends that the offset
        carries past them names none."""
        try:
            instant = reading - timedelta(seconds=offset)
        except OverflowError:
            return False
        return start <= instant < end

    for stretch in PRE1970_DISPUTED.get(zone_name, ()):
        if any(inside(stretch['from'], stretch['to'], offset) for offset in stretch['offsets']):
            raise NamedZoneRefusal('disputed')
    windows = PRE1970_WINDOWS[zone_name]
    holding = [w for w in windows if inside(w['from'], w['to'], w['offset_seconds'])]
    if len(holding) > 1:
        raise NamedZoneRefusal('ambiguous')
    if holding:
        window = holding[0]
        before = window['turned_back_from']
        if before is not None and inside(earliest, window['from'], before):
            raise NamedZoneRefusal('ambiguous')
        return _pre1970_cast(window)
    for earlier, later in zip(windows, windows[1:]):
        if (earlier['to'] == later['from'] and inside(earlier['to'], latest, earlier['offset_seconds'])
                and inside(earliest, later['from'], later['offset_seconds'])):
            raise NamedZoneRefusal('nonexistent')
    raise NamedZoneRefusal('linked')


def named_zone_state(zone_name, year, month, day, hour, minute, second, *, latitude=None, longitude=None):
    """The offset (whole seconds, east positive) and abbreviation a named
    zone gives a local clock reading, or NamedZoneRefusal.

    This reads the zone through `zoneinfo`, which keeps the whole of a
    zone's history; the library it replaced read only the part of each
    zone's file that begins in 1901, so every earlier birth was cast at the
    zone's rounded mean time although standard time had been kept since the
    1880s in several of them. Ambiguity is read from the clock's two folds:
    when they carry different offsets the reading is either repeated or
    skipped, and a round trip through UT says which.

    The first-record rule: a reading earlier than the zone's first
    rule is REFUSED, not cast. The zone's database begins with the local
    mean time of the zone's reference city (Calcutta for Delhi, Rome for
    Florence), which is not the birthplace's own meridian, and naming it
    after the zone would put another city's longitude under the
    birthplace's name. "The zone's first rule" is the moment the database's
    first offset ends: the state in force at the beginning of the record
    (what a `ZoneInfo` gives the year 1) holds until the zone's first
    transition, so a reading that carries exactly that offset and
    abbreviation is a reading before the first rule. (An anniversary was
    once exempt from this; no longer, below.)

    Linked names: a reading dated
    before 1970 in a zone the database keeps only as a link to another
    place's record (LINKED_ZONES) is REFUSED, as is all the app
    cannot vouch for: the state the database holds then is the other
    place's. This holds for an anniversary too, since the anniversary
    would be cast at the other place's clocks under the birthplace's name
    just as the birth would. The test
    reads the name and the date only, never the machine's database, so it
    is the same on every machine; a plain alias (Asia/Calcutta) is not on
    the list and is read as its zone.

    The pre-1970 windows: before 1970 a linked
    name with windows of its own clocks (PRE1970_WINDOWS) is read against
    them alone, never against the package's record, which is the linked
    target's. For each window the local reading less the window's offset is
    a UT instant, and the window holds the reading when that instant falls
    inside it. Exactly one window holding it casts the window's state: its
    offset and label, with a named mean time's sentence, or the sentence
    that its first day is this app's choice where the window starts at a
    clip. Two windows holding it is a fold ('ambiguous'), and so is
    the hour before a window whose start put the clocks back from a time
    that is no window of its own ('turned_back_from'); none holding it,
    between two windows that abut with a change of offset, is a gap
    ('nonexistent'); none holding it otherwise is 'linked', as before. A
    reading that either of a disputed stretch's offsets puts inside it
    (PRE1970_DISPUTED: Stockholm's 1916-09-30 22:00-23:00 UT, +01:00 by the
    statute's wording and +02:00 by the newspaper) is refused first
    ('disputed'). An impossible date is 'julian'. The 1970 cut stays the
    typed local year: a reading dated before 1970 is read
    against the windows alone, one dated from 1970-01-01 from the record. So
    Blanc-Sablon's local 1969-12-31 20:00:00-23:59:59, after its window's
    end at 1970-01-01 00:00 UT and before the local 1970, is refused
    'linked'; moving the cut to UT belongs with the cut's revisit after the
    release.

    A place's own clocks: a reading at coordinates that are exactly a
    place's of PLACE_CLOCKS, in the zone it is cast in and in a local year
    it was researched in, is read against that place's intervals alone
    (_place_clock_state: its clock, a fold, a gap, or a disputed stretch
    refused by the place, 'clock_choice'), never against the zone's record,
    which is another place's; any other pair, or another year, reads the
    record.

    The first-record rule's reach: its test is "the
    abbreviation is LMT" as well as "the record's first state", so a later
    line of local mean time at another offset (Alaska and the Pacific
    islands across the date line, Lima, Sao Tome, Rarotonga) and Lagos's
    return to its first state are refused as the first record is
    ('later_lmt', whose sentence claims neither "before any standard time"
    nor "its reference city"). A named mean time (NAMED_MEAN_TIMES) is cast only where it
    was the area's civil clock (CIVIL_MEAN_TIMES: the name and the period),
    and then the state says so ('civil_mean_time': True, and its 'label',
    civil_mean_time_label's sentence); elsewhere it is REFUSED ('mean_time'),
    and inside Rome's and Zurich's exceptions, when the birthplace's
    `latitude` and `longitude` are given, it is REFUSED ('mean_time_exception').
    These hold for an anniversary as for a birth, and so does the first
    record: an anniversary before a zone's first rule, or in
    a refused period, unavailable.

    The test applied strictly: a named
    mean time cast only for the stretches the database's notes establish
    (CIVIL_MEAN_TIMES' dates); inside a city whose public
    clocks the notes date later, REFUSED until that date
    ('mean_time_city'); St John's mean time under the
    name NST classed by the same test. The exceptions and the cities are
    read before the zone's own period.

    Monrovia from 1970; Rome's mainland
    from 1887-01-01 and Milan, Turin, Bologna and Venice from their own dates,
    each a cast area by coordinates; Riga and Tbilisi refused throughout;
    Alsace-Moselle under Paris's mean time and Trentino, South Tyrol, Trieste
    and Gorizia under Rome's REFUSED by coordinates ('mean_time_outside').
    Where the first day cast is this app's choice, the label says so
    (CHOSEN_STARTS).

    Inside those parts, Paris's
    WET from 1911-03-11 and Rome's CET from the end of Rome mean time (1893),
    each to 1921-01-01, are REFUSED by coordinates ('outside_clock')."""
    _zone_package_checked('tzdata')
    if zone_name.startswith('Etc/'):
        raise NamedZoneRefusal('sea')
    if zone_name in LINKED_ZONES and int(year) < LINKED_ZONES_UNTIL_YEAR:
        if zone_name in PRE1970_WINDOWS:
            return _pre1970_state(zone_name, year, month, day, hour, minute, second)
        raise NamedZoneRefusal('linked')
    # A place with clocks of its own (PLACE_CLOCKS: these coordinates
    # exactly, the zone it is cast in, a reading in one of its researched
    # local years) is read against them alone, never against the zone's
    # record. A caller that gives no coordinates (_clock_states here, and in
    # app.py the Here & Now page's clock and
    # _before_the_link_keeps_standard_time) reads the record as before.
    place = _place_clocks_at(zone_name, year, latitude, longitude)
    if place is not None:
        return _place_clock_state(place, year, month, day, hour, minute, second)
    # An alias is read as the zone it names: the tables below are
    # keyed on that zone's name.
    record = ZONE_ALIASES.get(zone_name, zone_name)
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise NamedZoneRefusal('unknown')
    try:
        naive = datetime(year, month, day, hour, minute, second)
    except ValueError:
        raise NamedZoneRefusal('julian')
    first, second_fold = naive.replace(tzinfo=zone, fold=0), naive.replace(tzinfo=zone, fold=1)
    if first.utcoffset() != second_fold.utcoffset():
        round_trip = first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
        raise NamedZoneRefusal('nonexistent' if round_trip != naive else 'ambiguous')
    beginning = datetime(1, 1, 1, tzinfo=zone)
    abbreviation = first.tzname()
    first_record = first.utcoffset() == beginning.utcoffset() and abbreviation == beginning.tzname()
    if abbreviation == 'LMT' and (not first_record or (int(year), int(month), int(day))
                                  >= LMT_RETURNS.get(record, (10000, 1, 1))):
        raise NamedZoneRefusal('later_lmt')
    if first_record:
        raise NamedZoneRefusal('before_rules', abbreviation=abbreviation)
    state = {'offset_seconds': int(round(first.utcoffset().total_seconds())),
             'abbreviation': abbreviation}
    if latitude is not None and longitude is not None and record in OUTSIDE_STRETCHES:
        # The country's clock cast on a place whose clock
        # the sources do not establish then (OUTSIDE_STRETCHES, read by the
        # reading's UT instant).
        instant = first.astimezone(timezone.utc)
        for area, country, rings in MEAN_TIME_OUTSIDE.get(record, ()):
            stretches = OUTSIDE_STRETCHES[record].get(area, ())
            if (any(lo <= instant < hi for lo, hi in stretches)
                    and _inside_area(float(latitude), float(longitude), rings)):
                raise NamedZoneRefusal('outside_clock', abbreviation=abbreviation, area=area, country=country)
    named = NAMED_MEAN_TIMES.get(LINKED_ZONES.get(record, record), {})
    if (abbreviation, state['offset_seconds']) in named:
        kept_on = named[(abbreviation, state['offset_seconds'])]
        local_date = (int(year), int(month), int(day))
        start = CIVIL_MEAN_TIMES.get(record, False)
        city = None
        if latitude is not None and longitude is not None:
            point = (float(latitude), float(longitude))
            for area, until, rings in MEAN_TIME_EXCEPTIONS.get(record, ()):
                if _inside_area(*point, rings):
                    raise NamedZoneRefusal('mean_time_exception', abbreviation=abbreviation, area=area,
                                           until=until, kept_on=kept_on)
            for area, country, rings in MEAN_TIME_OUTSIDE.get(record, ()):
                if _inside_area(*point, rings):
                    raise NamedZoneRefusal('mean_time_outside', abbreviation=abbreviation, area=area,
                                           country=country, kept_on=kept_on)
            for area, since, rings in MEAN_TIME_CITY_DATES.get(record, ()):
                if _inside_area(*point, rings):
                    if local_date < since:
                        raise NamedZoneRefusal('mean_time_city', abbreviation=abbreviation, area=area,
                                               since=since, kept_on=kept_on)
                    city = area
                    break
        if city is None and (start is False or (start is not None and local_date < start)):
            raise NamedZoneRefusal('mean_time', abbreviation=abbreviation, kept_on=kept_on)
        chosen = (start, CHOSEN_STARTS[record]) if city is None and record in CHOSEN_STARTS else None
        state['civil_mean_time'] = True
        state['label'] = civil_mean_time_label(abbreviation, kept_on, chosen)
    return state


# The zone a place takes. A place takes the zone
# the zone boundaries give its coordinates (the derived zone), except where
# the hand-kept list, data/place_zones.tsv, or an area rule says otherwise,
# each with its source. The list is keyed on the place's coordinates exactly
# as the atlas gives them, never on the atlas choice, so a chart saved from
# the atlas and restored by its coordinates is cast as its pick was. Its
# rules: 'geonames' (GeoNames' own zone, where the derived zone
# is another country's and GeoNames' is the place's own, and Liberpolis,
# which the boundaries leave in no country), 'kept' (the derived
# zone, a listed exception to the rule that would change it), 'unsettled' (no
# source settles the clock: a Standard-time cast is refused) and 'area:NAME'.
def _read_place_zones():
    """{(lat, lon): row} from data/place_zones.tsv, each row a dict of its
    columns; a malformed file stops the import, as the outlines' does, and
    so does a changed one (_shipped_file_bytes)."""
    text = _shipped_file_bytes('data/place_zones.tsv').decode('utf-8')
    lines = [line for line in text.split('\n') if line and not line.startswith('#')]
    header, rows = lines[0].split('\t'), {}
    for line in lines[1:]:
        cells = line.split('\t')
        if len(cells) != len(header):
            raise ValueError(f"data/place_zones.tsv: {line!r} has {len(cells)} columns, not {len(header)}")
        row = dict(zip(header, cells))
        key = (float(row['lat']), float(row['lon']))
        if key in rows:
            raise ValueError(f"data/place_zones.tsv: two rows at {key}")
        rows[key] = row
    return rows


PLACE_ZONES = _read_place_zones()

# The civil clocks kept at particular places before 1970, where the research
# gives a place clocks of its own: data/place_clocks.tsv, generated from a
# research register and never edited by hand. For each researched year of a
# place it holds the intervals that cover the year whole, each a clock (its
# offset and abbreviation) or a stretch whose clock the sources do not settle
# ('disputed'), with the documents of the place's year (PRE1970_SOURCES).
# Disputed stretches that meet are one row, which may run across the end of
# a year. A place's researched years need not follow one another: a year the
# research has not settled has no rows, and a reading in it is cast as at a
# place with no clocks of its own, by the zone's record; nothing is paired
# across it. Like the list above it is keyed on the place's coordinates
# exactly as the atlas gives them, never on the atlas choice: a pair typed
# equal to them is the same place (and so is another atlas place at exactly
# that pair), and a pair that differs in any digit is not. The file writes
# each end as a local date and time read on the clock then in force; each is
# turned into UT once, here (_clock_in_force, _stretch_end_clock), and
# named_zone_state reads a reading at the place, in one of its researched
# years, against its intervals alone (_place_clock_state). A malformed file
# stops the import, and so does a changed one.
PLACE_CLOCK_COLUMNS = ('lat', 'lon', 'geonameid', 'name', 'zone', 'from', 'to', 'offset', 'abbreviation', 'kind',
                       'source_ids')
PLACE_CLOCK_KINDS = ('clock', 'disputed')


def _clock_in_force(ending, beginning):
    """The offset, in seconds, the end between two of a place's intervals is
    read on, as data/place_clocks.tsv writes it: the clock of the interval
    that ends there (a change to summer time is at its hour of standard
    time, a return at its hour of summer time); where that one is a
    disputed stretch, or there is none (the place's first end), the clock of
    the one that begins there. ValueError where neither is a clock."""
    for interval in (ending, beginning):
        if interval is not None and interval['kind'] == 'clock':
            return interval['offset_seconds']
    raise ValueError("data/place_clocks.tsv: an end with no clock on either side to read it on")


def _stretch_end_clock(intervals, i):
    """The offset, in seconds, an end of the disputed stretch intervals[i]
    is read on where no row of the place meets it on that side (the place's
    first or last end, or the edge of a year with no rows), as
    data/place_clocks.tsv writes it: the first clock after the stretch at
    the place, or, where none follows, the last clock before it. ValueError
    where the place has no clock."""
    for interval in intervals[i + 1:]:
        if interval['kind'] == 'clock':
            return interval['offset_seconds']
    for interval in reversed(intervals[:i]):
        if interval['kind'] == 'clock':
            return interval['offset_seconds']
    raise ValueError("data/place_clocks.tsv: an end with no clock on either side to read it on")


def _read_place_clocks(path=None, sources=None):
    """{(lat, lon): place} from data/place_clocks.tsv, or from the file at
    `path` where one is given (read in its place, not checked by its hash),
    its rows naming documents of `sources` (PRE1970_SOURCES where none is
    given). A place is a dict of its 'geonameid' and 'name' (a record of it,
    not its key), its 'zone' (the zone it is cast in), its researched local
    'years' (the years its rows cover) and its 'intervals' in order, each a
    dict of its 'kind', a clock's 'offset_seconds' and 'abbreviation', a
    disputed stretch's 'offsets' (the clocks of the rows that meet it, on
    either side: one where no row meets it on the other side), its
    'sources', and its ends as the file writes them ('from_local',
    'to_local': readings (year, month, day, hour, minute, second)) and in
    UT ('from', 'to').

    Each end is read as the file's header says: where two rows meet, on the
    clock of the one that ends there, else of the one that begins there
    (_clock_in_force); where a row meets no row on that side (the place's
    first or last end, or the edge of a year with no rows), a clock's on
    its own clock and a disputed stretch's on the first clock after it at
    the place, else the last before it (_stretch_end_clock).

    A malformed file stops the import, as the list's does: a header that is
    not PLACE_CLOCK_COLUMNS; a row of another length; coordinates not
    written as the atlas writes them, or no place's; a kind outside
    PLACE_CLOCK_KINDS; a clock without an offset written +HH:MM or an
    abbreviation, or a disputed stretch with either; a source the documents
    do not hold; a place whose rows name two records or zones, or a zone
    the database keeps only as a link or as another name (whose readings
    the tables above already take); a place's rows that do not abut (each
    `from` the text of the `to` before it) but where whole years lie between
    them, that run backwards, or a clock's past the end of its year, or
    whose first `from` or last `to` is not 1 January 00:00, so that each
    researched year is covered whole; two disputed stretches that meet, or
    one at a place with no clock (an end with no clock to read it on); an
    interval empty once its ends are in UT."""
    name = 'data/place_clocks.tsv'
    if path is None:
        data = _shipped_file_bytes(name)
    else:
        with open(path, 'rb') as f:
            data = f.read()
    lines = [line for line in data.decode('utf-8').split('\n') if line and not line.startswith('#')]
    if not lines or tuple(lines[0].split('\t')) != PLACE_CLOCK_COLUMNS:
        raise ValueError(f"{name}: its header is not the columns this program reads")
    held = frozenset(PRE1970_SOURCES if sources is None else sources)
    # Each cell read once: a file repeats its dates, offsets, pairs and
    # lists of documents on row after row.
    moments, offsets, keys, documents = {}, {}, {}, {}

    def local(cell, line):
        moment = moments.get(cell)
        if moment is None:
            digits = cell[:4] + cell[5:7] + cell[8:10] + cell[11:13] + cell[14:]
            if (len(cell) == 16 and cell[4] == cell[7] == '-' and cell[10] == ' ' and cell[13] == ':'
                    and digits.isascii() and digits.isdigit()):
                try:
                    moment = datetime(int(cell[:4]), int(cell[5:7]), int(cell[8:10]), int(cell[11:13]),
                                      int(cell[14:]))
                except ValueError:
                    pass
            if moment is None:
                raise ValueError(f"{name}: {line!r}: {cell!r} is not a local date and time")
            moments[cell] = moment
        return moment

    def offset_seconds(cell, line):
        seconds = offsets.get(cell)
        if seconds is None:
            hours, _, minutes = cell[1:].partition(':')
            if (len(cell) != 6 or cell[0] not in '+-' or not (hours + minutes).isdigit() or int(minutes) >= 60
                    or int(hours) > 14):
                raise ValueError(f"{name}: {line!r}: {cell!r} is not an offset written +HH:MM")
            seconds = offsets[cell] = (-1 if cell[0] == '-' else 1) * (int(hours) * 3600 + int(minutes) * 60)
        return seconds

    places = {}
    for line in lines[1:]:
        cells = line.split('\t')
        if len(cells) != len(PLACE_CLOCK_COLUMNS):
            raise ValueError(f"{name}: {line!r} has {len(cells)} columns, not {len(PLACE_CLOCK_COLUMNS)}")
        lat, lon, geonameid, place_name, zone, start_text, end_text, offset_text, abbreviation, kind, ids = cells
        key = keys.get((lat, lon))
        if key is None:
            key = (float(lat), float(lon))
            if (repr(key[0]), repr(key[1])) != (lat, lon) or not (abs(key[0]) <= 90 and abs(key[1]) <= 180):
                raise ValueError(f"{name}: {line!r}: its coordinates are not written as the atlas writes a place's")
            keys[(lat, lon)] = key
        if kind == 'clock' and abbreviation and abbreviation.strip() == abbreviation:
            offset = offset_seconds(offset_text, line)
        elif kind == 'disputed' and not offset_text and not abbreviation:
            offset = None
        else:
            raise ValueError(f"{name}: {line!r}: a kind, offset and abbreviation this program does not read")
        named = documents.get(ids)
        if named is None:
            named = tuple(ids.split(';'))
            if not all(named) or len(set(named)) != len(named) or not held.issuperset(named):
                raise ValueError(f"{name}: {line!r}: a source the program does not hold")
            documents[ids] = named
        place = places.get(key)
        if place is None:
            place = places[key] = {'geonameid': geonameid, 'name': place_name, 'zone': zone, 'intervals': []}
        if ((geonameid, place_name, zone) != (place['geonameid'], place['name'], place['zone'])
                or not geonameid.isdigit() or not place_name or not zone or zone in LINKED_ZONES
                or zone in ZONE_ALIASES or zone.startswith('Etc/')):
            raise ValueError(f"{name}: {line!r}: a place's record or zone this program does not read")
        start, end = local(start_text, line), local(end_text, line)
        intervals = place['intervals']
        if intervals and intervals[-1]['to_local'] != start:
            # Only whole years with no rows may lie between two rows that
            # do not meet: the year before them ends whole, the one after
            # begins whole.
            before = intervals[-1]['to_local']
            if not (before < start and before == datetime(before.year, 1, 1) and start == datetime(start.year, 1, 1)):
                raise ValueError(f"{name}: {line!r}: its interval does not follow the place's last one in its year")
        if not start < end or (kind == 'clock' and end > datetime(start.year + 1, 1, 1)):
            raise ValueError(f"{name}: {line!r}: its interval does not follow the place's last one in its year")
        intervals.append({'kind': kind, 'offset_seconds': offset, 'abbreviation': abbreviation,
                          'sources': named, 'from_local': start, 'to_local': end})
    for key, place in places.items():
        intervals = place['intervals']
        first, last = intervals[0]['from_local'], intervals[-1]['to_local']
        if first != datetime(first.year, 1, 1) or last != datetime(last.year, 1, 1):
            raise ValueError(f"{name}: the place at {key}: a researched year not covered whole")
        # Where two rows meet, the one end they share and the clock it is
        # read on; None where years with no rows lie between them.
        shared = [_clock_in_force(a, b) if a['to_local'] == b['from_local'] else None
                  for a, b in zip(intervals, intervals[1:])]
        years = set()
        for i, interval in enumerate(intervals):
            before = intervals[i - 1] if i and shared[i - 1] is not None else None
            after = intervals[i + 1] if i < len(shared) and shared[i] is not None else None
            own = interval['offset_seconds'] if interval['kind'] == 'clock' else None
            start_on = shared[i - 1] if before is not None else own
            end_on = shared[i] if after is not None else own
            if start_on is None:
                start_on = _stretch_end_clock(intervals, i)
            if end_on is None:
                end_on = _stretch_end_clock(intervals, i)
            start, end = interval['from_local'], interval['to_local']
            interval['from'] = (start - timedelta(seconds=start_on)).replace(tzinfo=timezone.utc)
            interval['to'] = (end - timedelta(seconds=end_on)).replace(tzinfo=timezone.utc)
            if not interval['from'] < interval['to']:
                raise ValueError(f"{name}: the place at {key}: an interval empty once its ends are in UT")
            if interval['kind'] == 'disputed':
                interval['offsets'] = tuple(sorted({beside['offset_seconds'] for beside in (before, after)
                                                    if beside is not None and beside['kind'] == 'clock'}))
            years.update(range(start.year, end.year if end == datetime(end.year, 1, 1) else end.year + 1))
            interval['from_local'] = (start.year, start.month, start.day, start.hour, start.minute, 0)
            interval['to_local'] = (end.year, end.month, end.day, end.hour, end.minute, 0)
        place['years'] = frozenset(years)
        place['intervals'] = tuple(intervals)
    return places


PLACE_CLOCKS = _read_place_clocks()


def _place_clocks_at(zone_name, year, latitude, longitude):
    """The place of PLACE_CLOCKS a reading in `zone_name` in the local `year`
    at these coordinates is read at, or None: the coordinates the place's,
    exactly, the zone the one it is cast in, the year one it was researched
    in (one its rows cover). Anything else (no coordinates, another pair,
    another zone, a year outside its research or one between its researched
    years that the research has not settled) reads the zone's record as
    before."""
    if latitude is None or longitude is None:
        return None
    try:
        place = PLACE_CLOCKS.get((float(latitude), float(longitude)))
        year = int(year)
    except (TypeError, ValueError, OverflowError):
        return None
    if place is None or place['zone'] != zone_name or year not in place['years']:
        return None
    return place


def _place_clock_state(place, year, month, day, hour, minute, second):
    """A reading at a place with clocks of its own, in a researched year,
    read against its intervals alone, as a linked name's is against its
    windows (_pre1970_state): the reading less a clock's offset is a UT
    instant, and the interval holds the reading when the instant falls inside
    it. Exactly one clock holding it casts its offset and abbreviation, with
    'place_clock' True (the clock is the place's, not the zone's record:
    zone_record_place); two holding it is a fold ('ambiguous'); none, the
    gap of a change ('nonexistent'), each the place's own and so carrying
    its name (`place`), not the zone's. A reading between a disputed
    stretch's local ends, or one that either clock beside it puts inside it,
    as Stockholm's hour is, is refused first, by the place:
    PlaceClockRefusal('clock_choice'), its `interval` the stretch's local
    ends as the file writes them, naming no clocks. An impossible date is
    'julian'."""
    try:
        reading = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    except ValueError:
        raise NamedZoneRefusal('julian')

    def inside(interval, offset):
        return interval['from'] <= reading - timedelta(seconds=offset) < interval['to']

    # A stretch's end at the edge of a year with no rows may be read on a
    # clock that is not beside it (_stretch_end_clock), and a stretch may
    # have no clock beside it at all: between its local ends it is refused
    # whatever its clocks say.
    local = (reading.year, reading.month, reading.day, reading.hour, reading.minute, reading.second)
    for interval in place['intervals']:
        if interval['kind'] == 'disputed' and (interval['from_local'] <= local < interval['to_local'] or any(
                inside(interval, offset) for offset in interval['offsets'])):
            raise PlaceClockRefusal('clock_choice', interval=(interval['from_local'], interval['to_local']))
    holding = [interval for interval in place['intervals']
               if interval['kind'] == 'clock' and inside(interval, interval['offset_seconds'])]
    if len(holding) > 1:
        raise NamedZoneRefusal('ambiguous', place=place['name'])
    if not holding:
        raise NamedZoneRefusal('nonexistent', place=place['name'])
    return {'offset_seconds': holding[0]['offset_seconds'], 'abbreviation': holding[0]['abbreviation'],
            'place_clock': True}


def _one_change(reading, kind, changes):
    """The one change of `changes` (each (instant, (offset, abbreviation)
    before, (offset, abbreviation) after), the instant in UT, the offsets in
    seconds; None and None either side of an end with no one clock) whose skipped ('nonexistent') or repeated ('ambiguous') local
    stretch holds `reading` (a naive local datetime), or None: where no
    change's stretch holds it, or more than one does, or the one that does
    went the other way, or another change falls inside the stretch, the
    stretch is not one change and nothing is said of it."""
    local = reading.replace(tzinfo=timezone.utc)
    holding = []
    for instant, before, after in changes:
        if before is None:
            continue
        low, high = sorted((before[0], after[0]))
        if instant + timedelta(seconds=low) <= local < instant + timedelta(seconds=high):
            holding.append((instant, before, after))
    if len(holding) != 1:
        return None
    instant, before, after = holding[0]
    if (after[0] > before[0]) != (kind == 'nonexistent'):
        return None
    reach = timedelta(seconds=abs(after[0] - before[0]))
    if any(other != instant and abs(other - instant) < reach for other, _before, _after in changes):
        return None
    return instant, before, after


def _zone_change_near(zone, reading):
    """The change of `zone`'s own record a skipped or repeated local
    `reading` falls in, as _one_change reads one, from the record alone: the
    offset before the change is the reading's first fold's, the one after its
    second's, and the instant is found between them to the second. The
    record is then read every minute for the change's own length either
    side, and any other change of offset or abbreviation there leaves the
    stretch not one change (an empty list)."""
    def state(moment):
        local = moment.replace(tzinfo=timezone.utc).astimezone(zone)
        return int(round(local.utcoffset().total_seconds())), local.tzname()

    first, second = reading.replace(tzinfo=zone, fold=0), reading.replace(tzinfo=zone, fold=1)
    before = int(round(first.utcoffset().total_seconds()))
    after = int(round(second.utcoffset().total_seconds()))
    if before == after:
        return []
    low, high = reading - timedelta(seconds=max(before, after)), reading - timedelta(seconds=min(before, after))
    if state(low)[0] != before or state(high)[0] != after:
        return []
    while high - low > timedelta(seconds=1):
        middle = low + timedelta(seconds=(high - low).total_seconds() // 2)
        if state(middle)[0] == after:
            high = middle
        else:
            low = middle
    instant, then, now = high, state(low), state(high)
    reach = abs(after - before)
    for step in range(0, reach + 60, 60):
        step = min(step, reach)
        if state(instant - timedelta(seconds=step) - timedelta(seconds=1)) != then or (
                state(instant + timedelta(seconds=step)) != now):
            return []
    return [(instant.replace(tzinfo=timezone.utc), then, now)]


def clock_change(kind, zone_name, year, month, day, hour, minute, second, *, latitude=None, longitude=None):
    """The change of the clocks a reading refused 'nonexistent' or
    'ambiguous' falls in, read where named_zone_state read it: a place's own
    rows (PLACE_CLOCKS), a linked name's windows before 1970
    (PRE1970_WINDOWS, the hour a window's start turned back from its
    'turned_back_from' included), or the zone's own record. A dict of the
    'place' (the place's name where the change is its own, else None), the
    'zone', the local reading 'at' which it took effect on the clock in
    force before it (year, month, day, hour, minute, second), and the clock
    'before' and 'after' it, each (offset in seconds, abbreviation or
    None); or None, where the reading's stretch is not one change
    (_one_change) or the reading is not refused so."""
    if kind not in ('nonexistent', 'ambiguous') or zone_name.startswith('Etc/'):
        return None
    try:
        reading = datetime(year, month, day, hour, minute, second)
    except (TypeError, ValueError):
        return None
    place = None
    if zone_name in LINKED_ZONES and int(year) < LINKED_ZONES_UNTIL_YEAR:
        windows = PRE1970_WINDOWS.get(zone_name, ())
        changes = [(earlier['to'], (earlier['offset_seconds'], earlier['abbreviation']),
                    (later['offset_seconds'], later['abbreviation']))
                   for earlier, later in zip(windows, windows[1:]) if earlier['to'] == later['from']]
        changes += [(window['from'], (window['turned_back_from'], None),
                     (window['offset_seconds'], window['abbreviation']))
                    for window in windows if window['turned_back_from'] is not None]
    elif (place := _place_clocks_at(zone_name, year, latitude, longitude)) is not None:
        # A disputed stretch's ends have no one clock on their other side:
        # they are changes no reading is placed in, but they still fall
        # inside a stretch or not. Two rows with years between them that
        # have no rows do not meet, and make no change; nor do two clocks
        # that meet with the same offset and abbreviation (a year's rows
        # meeting the next year's on one clock).
        changes = [(earlier['to'], (earlier['offset_seconds'], earlier['abbreviation']),
                    (later['offset_seconds'], later['abbreviation']))
                   if earlier['kind'] == 'clock' and later['kind'] == 'clock' else (earlier['to'], None, None)
                   for earlier, later in zip(place['intervals'], place['intervals'][1:])
                   if earlier['to_local'] == later['from_local'] and not (
                       earlier['kind'] == later['kind'] == 'clock'
                       and (earlier['offset_seconds'], earlier['abbreviation'])
                       == (later['offset_seconds'], later['abbreviation']))]
    else:
        try:
            changes = _zone_change_near(ZoneInfo(zone_name), reading)
        except (ZoneInfoNotFoundError, ValueError, OSError, OverflowError):
            return None
    try:
        found = _one_change(reading, kind, changes)
    except OverflowError:
        return None
    if found is None:
        return None
    instant, before, after = found
    at = instant.replace(tzinfo=None) + timedelta(seconds=before[0])
    return {'place': place['name'] if place is not None else None, 'zone': zone_name,
            'at': (at.year, at.month, at.day, at.hour, at.minute, at.second),
            'before': before, 'after': after}


def _utc_offset_words(seconds):
    """An offset as the time-standard box writes one: UTC, signed, hours and
    minutes, and the seconds where it has any."""
    total = abs(int(seconds))
    text = f"UTC{'-' if seconds < 0 else '+'}{total // 3600:02d}:{(total % 3600) // 60:02d}"
    return text + (f":{total % 60:02d}" if total % 60 else "")


def _clock_words(clock):
    """A clock (offset in seconds, abbreviation or None) by its abbreviation,
    with its offset in brackets; local mean time by name; the offset alone
    where it has no abbreviation, or only the database's numeric one
    ("-03")."""
    offset, abbreviation = clock
    if abbreviation == 'LMT':
        return f"local mean time ({_utc_offset_words(offset)})"
    if not abbreviation or (abbreviation[0] in '+-' and abbreviation[1:].isdigit()):
        return _utc_offset_words(offset)
    return f"{abbreviation} ({_utc_offset_words(offset)})"


def _amount_words(seconds):
    """A length of time in words, its parts that are not zero: "one hour",
    "two hours", "30 minutes", "3 minutes 58 seconds"."""
    seconds = abs(int(seconds))
    parts = []
    for count, unit in ((seconds // 3600, 'hour'), ((seconds % 3600) // 60, 'minute'), (seconds % 60, 'second')):
        if count:
            number = {1: 'one', 2: 'two'}.get(count, str(count))
            parts.append(f"{number} {unit}{'' if count == 1 else 's'}")
    return " ".join(parts)


def _reading_words(reading, day=None):
    """A local reading (year, month, day, hour, minute, second) as the
    sentences print it: the time, with its seconds where it has any, and
    before it the date unless that is `day`."""
    clock = f"{reading[3]:02d}:{reading[4]:02d}" + (f":{reading[5]:02d}" if reading[5] else "")
    date = f"{reading[0]:04d}-{reading[1]:02d}-{reading[2]:02d}"
    return clock if date == day else f"{date} {clock}"


def clock_change_words(change, reading):
    """The parts of a sentence that states a change of the clocks
    (clock_change) and a `reading` it skipped or repeated: 'where' (the
    place, or "the {zone} time zone"), the 'time' and 'date' it took effect
    on the clock before it, the 'amount' in words, the clock 'before' and
    'after', each by name and offset, the 'before_offset' and
    'after_offset' alone, and the 'reading', its date given only where it is
    not the change's."""
    at = change['at']
    date = f"{at[0]:04d}-{at[1]:02d}-{at[2]:02d}"
    before, after = change['before'], change['after']
    return {'where': change['place'] or f"the {change['zone']} time zone",
            'time': _reading_words(at, date), 'date': date,
            'amount': _amount_words(after[0] - before[0]),
            'before': _clock_words(before), 'after': _clock_words(after),
            'before_offset': _utc_offset_words(before[0]), 'after_offset': _utc_offset_words(after[0]),
            'reading': _reading_words(tuple(reading), date)}


# The areas where the research leaves the clock to the person, or settles it
# by a date. Each reaches the places its register names, through the list's
# rows 'area:NAME'; an area with a 'boundary' also reaches every point the zone
# boundaries give that zone (zone.tab names Asia/Hebron "West Bank" and
# Asia/Urumqi "Xinjiang Time"). There a Standard-time cast is refused,
# naming both clocks, unless both clocks give the same offset at that moment
# outside an 'unsettled' interval (the research's uncertain intervals: the
# West Bank before 1967 and around 1995-96; all of Saskatchewan's 520
# records before 1972-04-30). Sokhumi follows GeoNames' Europe/Moscow from
# 2010 (the research: "likely from at least 2010"), and is refused before it
# and in the
# hours of 2014-10-26 whose turning back the sources leave unsettled. The
# intervals are local readings, half open. The West Bank's rule reaches every
# West Bank row GeoNames codes PS (its list rows), the
# places both sources put in Asia/Jerusalem included. The five border places
# whose clock no record in hand settles (the Golan's
# three rows coded SY, Abu Musa's coded AE, one Paracels row coded VN; the
# research's finding their only source) are refused as these areas are,
# naming the zone their coordinates give and their coded country's: 'golan',
# 'abu_musa' and 'paracels', the first clock the derived one. So are the four
# kept on the same finding with GeoNames' record giving the
# derived zone too (a data record, not a clock record), the second clock the
# zone zone.tab gives their coded country: Dhekelia's coded GB ('dhekelia'),
# two Kashmir rows coded IN ('kashmir'), the second Paracels row ('paracels').
_BEFORE = (1, 1, 1, 0, 0, 0)
PLACE_ZONE_AREAS = {
    'west_bank': {'clocks': ('Asia/Hebron', 'Asia/Jerusalem'), 'boundary': 'Asia/Hebron',
                  'unsettled': ((_BEFORE, (1967, 6, 5, 0, 0, 0)), ((1995, 1, 1, 0, 0, 0), (1997, 1, 1, 0, 0, 0)))},
    'xinjiang': {'clocks': ('Asia/Shanghai', 'Asia/Urumqi'), 'boundary': 'Asia/Urumqi', 'unsettled': ()},
    'cyprus_boundary': {'clocks': ('Asia/Nicosia', 'Asia/Famagusta'), 'unsettled': ()},
    'saskatchewan': {'clocks': ('America/Regina', 'America/Swift_Current'),
                     'unsettled': ((_BEFORE, (1972, 4, 30, 0, 0, 0)),)},
    'sokhumi': {'clocks': ('Europe/Moscow', 'Asia/Tbilisi'), 'cast': 'Europe/Moscow',
                'unsettled': ((_BEFORE, (2010, 1, 1, 0, 0, 0)), ((2014, 10, 26, 1, 0, 0), (2014, 10, 26, 3, 0, 0)))},
    'golan': {'clocks': ('Asia/Jerusalem', 'Asia/Damascus'), 'unsettled': ()},
    'abu_musa': {'clocks': ('Asia/Tehran', 'Asia/Dubai'), 'unsettled': ()},
    'paracels': {'clocks': ('Asia/Shanghai', 'Asia/Ho_Chi_Minh'), 'unsettled': ()},
    'dhekelia': {'clocks': ('Asia/Nicosia', 'Europe/London'), 'unsettled': ()},
    'kashmir': {'clocks': ('Asia/Karachi', 'Asia/Kolkata'), 'unsettled': ()},
}
PLACE_ZONE_RULES = ('geonames', 'kept', 'unsettled') + tuple(f'area:{name}' for name in PLACE_ZONE_AREAS)


def _clock_states(zones, reading):
    """Each zone with the offset (seconds) it gives the local reading, or None
    where it refuses the reading."""
    states = []
    for zone in zones:
        try:
            states.append((zone, named_zone_state(zone, *reading)['offset_seconds']))
        except (NamedZoneRefusal, TypeError, ValueError, OverflowError):
            states.append((zone, None))
    return tuple(states)


def place_zone(latitude, longitude, finder, moment=None, *, zone=None):
    """The zone a Standard-time (named-zone) cast at these coordinates is made
    in, or PlaceClockRefusal ('clock_choice', 'unsettled') where the sources
    leave the clock open; None where the boundaries give the point no zone.

    `finder` is the run's TimezoneFinder (app.py makes one each run): this is
    the one place its timezone_at is asked. A caller that already holds the
    zone a chart was cast in (an anniversary of that chart) passes finder
    None and that `zone`. `moment` is the local reading (year, month, day,
    hour, minute, second) the cast is for; without one an area rule gives
    the zone it casts in when it casts, and an unsettled place is refused.
    The answer depends on the coordinates and the moment alone. In order: an
    area rule (the list's, then a boundary's); the list's row; the derived
    zone."""
    if finder is not None:
        _zone_package_checked('timezonefinder-data')
    derived = finder.timezone_at(lng=longitude, lat=latitude) if finder is not None else zone
    row = None
    if latitude is not None and longitude is not None:
        row = PLACE_ZONES.get((float(latitude), float(longitude)))
    rule = row['rule'] if row else None
    area = rule[len('area:'):] if rule and rule.startswith('area:') else None
    if area is None:
        area = next((name for name, a in PLACE_ZONE_AREAS.items() if a.get('boundary') == derived), None)
    if area is not None:
        return _area_zone(area, derived, moment)
    if rule == 'unsettled':
        clocks = row['zone'].split()
        raise PlaceClockRefusal('unsettled', clocks=_clock_states(clocks, moment) if moment is not None
                               else tuple((c, None) for c in clocks))
    if row is not None:
        return row['zone']
    return derived


def _area_zone(name, derived, moment):
    """An area rule's answer at the moment (place_zone)."""
    area = PLACE_ZONE_AREAS[name]
    cast = area.get('cast', derived)
    if moment is None:
        return cast
    reading = tuple(int(part) for part in moment)
    states = _clock_states(area['clocks'], reading)
    if all(offset is None for _zone, offset in states):
        # Neither clock can place the reading (before either kept standard
        # time, a Julian-only day): the derived zone's own refusal says why.
        return derived
    for start, end in area['unsettled']:
        if start <= reading < end:
            raise PlaceClockRefusal('clock_choice', area=name, clocks=states, interval=(start, end))
    if 'cast' in area or (None not in [o for _z, o in states] and states[0][1] == states[1][1]):
        return cast
    raise PlaceClockRefusal('clock_choice', area=name, clocks=states)


# Whose record a full zone keeps before 1970. The database records a zone's
# history before 1970 for the place it is named after (America/Chicago:
# Chicago), and a place inside the zone's boundary that kept another clock
# then (summer time on other dates, under a state's own law) is cast at the
# named place's, with nothing said. Where a place has clocks of its own
# (PLACE_CLOCKS) a reading in its researched years is cast from them; else
# the cast says whose record it is (zone_record_place). The named place is the zone's row in the pinned
# tzdata package's zone1970.tab, its coordinates read as the zones are read,
# from that package alone. The bound is the typed local year, as the linked
# zones' is; the distance a great-circle distance on the mean Earth radius.
ZONE_RECORD_PLACE_KM = 25
_EARTH_RADIUS_KM = 6371.0088
_ZONE1970_PLACES = {}


def _iso6709_degrees(text, degree_digits):
    """One coordinate of zone1970.tab's ISO 6709 form ("+4151", "-08739",
    "+415100", "-0873900"), in decimal degrees."""
    sign, digits = (-1 if text[0] == '-' else 1), text[1:]
    whole, rest = int(digits[:degree_digits]), digits[degree_digits:]
    minutes, seconds = int(rest[:2]), int(rest[2:4] or 0)
    return sign * (whole + minutes / 60 + seconds / 3600)


def _zone1970_places():
    """{zone: (latitude, longitude)} from the pinned tzdata package's
    zone1970.tab, read once, after the package's check
    (_zone_package_checked); empty where the package is not installed."""
    if not _ZONE1970_PLACES:
        _zone_package_checked('tzdata')
        package = _zone_package('tzdata')
        if package is None:
            return {}
        path = Path(package.__file__).parent / 'zoneinfo' / 'zone1970.tab'
        places = {}
        for line in path.read_text(encoding='utf-8').splitlines():
            if not line or line.startswith('#'):
                continue
            cells = line.split('\t')
            coordinates, zone = cells[1], cells[2]
            split = max(coordinates.rfind('+'), coordinates.rfind('-'))
            places[zone] = (_iso6709_degrees(coordinates[:split], 2),
                            _iso6709_degrees(coordinates[split:], 3))
        # Filled in one step, so a thread that finds it filled never
        # reads a part of the table.
        _ZONE1970_PLACES.update(places)
    return _ZONE1970_PLACES


def _distance_km(latitude_1, longitude_1, latitude_2, longitude_2):
    """The great-circle distance between two points (haversine)."""
    import math
    p1, p2 = math.radians(latitude_1), math.radians(latitude_2)
    dp, dl = p2 - p1, math.radians(longitude_2 - longitude_1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def zone_record_place(latitude, longitude, zone_name, moment):
    """The place whose record a Standard-time cast takes, where that is
    another place's, or None.

    It is the zone's last part, underscores as spaces ("Chicago", "New
    York"), for a named-zone cast at a local reading `moment` (year, month,
    day, hour, minute, second) dated before 1970 at coordinates farther than
    ZONE_RECORD_PLACE_KM from the zone's row in zone1970.tab; for a zone with
    no row there, wherever the cast is made. None for anything that is not a
    named zone ("LMT", a manual offset's "UTC+02:00"), a nautical Etc/ zone,
    a reading from 1970, and a cast that is not made or that the pre-1970
    windows and refusals already speak for: a linked zone before 1970
    (LINKED_ZONES: its windows or its refusal, a disputed stretch among
    them), a place the list or an area rule refuses (place_zone), a
    reading named_zone_state refuses, one it casts at a named mean time
    that was then the civil clock ('civil_mean_time'), whose sentence
    already says whose clock it was, and one it casts from a place's own
    clocks ('place_clock', PLACE_CLOCKS), which are not the zone's record. It
    depends on its arguments alone."""
    if not isinstance(zone_name, str) or latitude is None or longitude is None or zone_name.startswith('Etc/'):
        return None
    try:
        reading = tuple(int(part) for part in moment)
        latitude, longitude = float(latitude), float(longitude)
    except (TypeError, ValueError):
        return None
    if not (abs(latitude) <= 90 and abs(longitude) <= 180):    # NaN too: no place
        return None
    if len(reading) != 6 or reading[0] >= LINKED_ZONES_UNTIL_YEAR or zone_name in LINKED_ZONES:
        return None
    try:
        ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None
    try:
        place_zone(latitude, longitude, None, reading, zone=zone_name)
        state = named_zone_state(zone_name, *reading, latitude=latitude, longitude=longitude)
    except NamedZoneRefusal:
        return None
    if state.get('civil_mean_time') or state.get('place_clock'):
        return None
    named = _zone1970_places().get(zone_name)
    if named is not None and _distance_km(latitude, longitude, *named) <= ZONE_RECORD_PLACE_KM:
        return None
    return zone_name.rsplit('/', 1)[-1].replace('_', ' ')


# The atlas lookup (moved from app.py). app.py keeps the sentences and the
# labels, which are written with the engine's degrees_text; the fold, the
# reading of a typed text and the search are here.


def _atlas_fold(text):
    """A name or a typed text as the atlas search compares it: composed
    (NFC, so an accent typed as a separate mark is the accented letter)
    and then case-folded (casefold, not lower: "GROSSRÄSCHEN" is
    "Großräschen"). casefold follows no locale, so the Turkish capital İ
    is mapped to i first and a dot above left after an i is dropped; the
    dotless ı is mapped to i too, since the capital I that stands for it
    ("YUKARI BEĞDEŞ") casefolds to i."""
    folded = unicodedata.normalize("NFC", text or "").replace("\u0130", "i").casefold()
    return folded.replace("\u0131", "i").replace("i\u0307", "i")


# The words the atlas search takes as one: the forms of each group stand
# for one another wherever they are a whole word of the typed text and of a
# name ("St. Paul", "St Paul", "St-Paul" and "Sankt Paul" all find "Saint
# Paul" and "Saint-Paul").
ATLAS_WORD_FORMS = (('saint', 'sankt', 'st'), ('sainte', 'ste'), ('fort', 'ft'), ('mount', 'mt'))
# Country qualifiers that are no code and begin no name in the atlas, as
# they are compared (folded, a final period dropped). Each names its
# country alone: "UK" is not the start of Ukraine, nor "Britain" of British
# Columbia.
ATLAS_COUNTRY_ALIASES = {'usa': 'US', 'u.s': 'US', 'uk': 'GB', 'u.k': 'GB', 'great britain': 'GB', 'britain': 'GB'}
# The postal abbreviations of the regions of Canada and Australia, which the
# atlas codes by number, each with its region's name as the atlas spells it.
# A qualifier equal to one (as qualifiers are compared) holds for that
# region, whose code is read from the atlas's own table of regions, besides
# wherever it holds already ("NL" is still the Netherlands, "WA" Washington).
ATLAS_REGION_ABBREVIATIONS = (
    ('ab', 'CA', 'Alberta'), ('bc', 'CA', 'British Columbia'), ('mb', 'CA', 'Manitoba'),
    ('nb', 'CA', 'New Brunswick'), ('nl', 'CA', 'Newfoundland and Labrador'), ('ns', 'CA', 'Nova Scotia'),
    ('nt', 'CA', 'Northwest Territories'), ('nu', 'CA', 'Nunavut'), ('on', 'CA', 'Ontario'),
    ('pe', 'CA', 'Prince Edward Island'), ('qc', 'CA', 'Quebec'), ('sk', 'CA', 'Saskatchewan'),
    ('yt', 'CA', 'Yukon'),
    ('act', 'AU', 'Australian Capital Territory'), ('nsw', 'AU', 'New South Wales'),
    ('nt', 'AU', 'Northern Territory'), ('qld', 'AU', 'Queensland'), ('sa', 'AU', 'South Australia'),
    ('tas', 'AU', 'Tasmania'), ('vic', 'AU', 'Victoria'), ('wa', 'AU', 'Western Australia'))
# The capitals of ASCII to its small letters and nothing else: the case the
# search's keys as typed set aside.
ATLAS_ASCII_LOWER = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')


def _atlas_words(text):
    """A typed text as the atlas search reads it: its pieces as typed
    (str), and for each whole word of ATLAS_WORD_FORMS its group's index
    (int), the period and the spaces or hyphens after it taken with it. A
    word begins the text or follows a space, a hyphen or a comma, and is
    whole when it is written with its period, or is followed by spaces or a
    hyphen and then more of its comma's part: a text ending in a bare "St"
    is still being typed ("Stuttgart"), and so is a part that ends in one
    ("Foo St, MN")."""
    low = text.translate(ATLAS_ASCII_LOWER)
    forms = sorted(((form, group) for group, written in enumerate(ATLAS_WORD_FORMS) for form in written),
                   key=lambda pair: -len(pair[0]))
    words, start, at = [], 0, 0
    while at < len(low):
        if at == 0 or low[at - 1] in ' -,':
            for form, group in forms:
                if not low.startswith(form, at):
                    continue
                end = at + len(form)
                dotted = low[end:end + 1] == '.'
                rest = end + dotted
                while low[rest:rest + 1] in (' ', '-'):
                    rest += 1
                if dotted or (rest > end and low[rest:rest + 1] not in ('', ',')):
                    if start < at:
                        words.append(text[start:at])
                    words.append(group)
                    start = at = rest
                    break
            else:
                at += 1
            continue
        at += 1
    if start < len(text):
        words.append(text[start:])
    return words


def _atlas_begins(low, words):
    """Whether a name, in ASCII small letters (ATLAS_ASCII_LOWER), begins
    with the typed `words` (_atlas_words, each piece in small letters as
    the look compares it): each piece as it is, and each word in any form
    of its group, whole in the name (with its period, or followed by
    spaces or a hyphen, or ending the name), with the period and the spaces
    or hyphens it has."""
    at = 0
    for word in words:
        if isinstance(word, str):
            if not low.startswith(word, at):
                return False
            at += len(word)
            continue
        for form in ATLAS_WORD_FORMS[word]:
            if low.startswith(form, at):
                end = at + len(form)
                dotted = low[end:end + 1] == '.'
                rest = end + dotted
                while low[rest:rest + 1] in (' ', '-'):
                    rest += 1
                if dotted or rest > end or rest == len(low):
                    at = rest
                    break
        else:
            return False
    return True


def _atlas_qualifier(text):
    """A typed qualifier as it is compared: folded (_atlas_fold), its
    surrounding spaces and a final period dropped ("Minn." is "minn").
    One of ATLAS_COUNTRY_ALIASES so read ("U.S." is "u.s") is that; one
    made only of single letters each followed by a period is its letters
    ("D.C." is "dc", "U.S.A." is "usa"); and a final period that is a
    whole word's of ATLAS_WORD_FORMS is kept ("St." is "st."), so that the
    word stands for its group when the qualifier is compared with a name
    (_atlas_holding)."""
    folded = _atlas_fold(text).strip()
    typed = folded[:-1].rstrip() if folded.endswith('.') else folded
    if typed in ATLAS_COUNTRY_ALIASES:
        return typed
    if len(folded) >= 2 and len(folded) % 2 == 0 and set(folded[1::2]) == {'.'} and all(
            letter.isalpha() for letter in folded[0::2]):
        return folded[0::2]
    words = _atlas_words(folded)
    return folded if folded.endswith('.') and isinstance(words[-1], int) else typed


def _atlas_looks(text):
    """The looks a typed text (already trimmed) makes, as (words,
    qualifiers), or None for a text that holds no whole word of
    ATLAS_WORD_FORMS, no comma and no trailing bracket: that text is
    searched as one look, itself (_atlas_search_looks). The first look is
    the whole text's, with no qualifier, so that a name holding a comma
    ("Misato, Saitama") or a bracket ("Frankfurt (Oder)") is still found
    by it. Then, for each comma,
    the text before it, each part after it one qualifier (str, compared as
    _atlas_qualifier gives it). A trailing bracket after more text is one
    more part: two ASCII letters in it, as the app's own labels end ("(US)"),
    are a qualifier that is the country's alone where they are a country's
    code (a 1-tuple, which _atlas_holding reads), and any other text in it
    is one more qualifier as a comma's part is ("(USA)", "(BC)"). Each look
    is made once: its qualifiers are only those that narrow (an empty one
    holds everywhere, one typed twice holds where it holds once), a cut's
    text is taken without the commas and spaces that end it (what an empty
    part after it would have added), and a look whose text and narrowing
    qualifiers are an earlier look's, or whose text is empty, is not made."""
    bracket = before = None
    if text.endswith(')'):
        opened = text.rfind('(')
        before = text[:opened].rstrip() if opened > 0 else ''
        if before and ')' not in text[opened + 1:-1]:
            inside = text[opened + 1:-1]
            if len(inside) == 2 and inside.isascii() and inside.isalpha():
                bracket = (_atlas_qualifier(inside),)
            else:
                bracket = _atlas_qualifier(inside)
    if bracket is None:
        before = text
    words = _atlas_words(before)
    if bracket is None and ',' not in text and all(isinstance(word, str) for word in words):
        return None
    if bracket is not None:
        if words and isinstance(words[-1], str):
            words = words[:-1] + [words[-1] + text[len(before):]]
        else:
            words = words + [text[len(before):]]
    looks, made = [], set()

    def look(words, qualifiers):
        narrowing = tuple(dict.fromkeys(qualifier for qualifier in qualifiers
                                        if (qualifier if isinstance(qualifier, str) else qualifier[0])))
        key = (tuple(words), frozenset(narrowing))
        if words and key not in made:
            made.add(key)
            looks.append((words, narrowing))
    look(words, ())
    parts = before.split(',')
    qualifiers = [_atlas_qualifier(part) for part in parts] + ([bracket] if bracket is not None else [])
    for cut in range(1, len(parts) + (bracket is not None)):
        head = ','.join(parts[:cut]).rstrip()
        while head.endswith(','):
            head = head[:-1].rstrip()
        look(_atlas_words(head), qualifiers[cut:])
    return looks


# The atlas's tables of countries and regions as qualifiers are compared
# with them, folded once in a process for each file read: (the file's path
# and identity as the connection's file gives them, the fold) -> (countries,
# regions by code, regions by the first letter of a spelling). A file read
# again unchanged is answered from here; another file, or the same one
# changed, is read afresh.
ATLAS_FOLDED_NAMES = {}


def _atlas_file_identity(cursor):
    """The file the cursor's connection reads, as (path, device, inode,
    size, modification and change times); for a database held in memory,
    the connection itself."""
    path = next((file for _seq, name, file in cursor.execute("PRAGMA database_list").fetchall()
                 if name == 'main'), '')
    if not path:
        return ('', id(cursor.connection))
    st = os.stat(path)
    return (os.path.abspath(path), st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _atlas_holding(cursor, qualifiers):
    """For each qualifier, the countries and the (country, region code)
    pairs it holds for: one of ATLAS_COUNTRY_ALIASES holds for its country
    alone; a country's own qualifier (a 1-tuple that is a country's code)
    where it equals the country's code or begins its name; and any other
    where it equals the country's or the region's code, or begins the
    country's name or either spelling of the region's, or is the region's
    abbreviation (ATLAS_REGION_ABBREVIATIONS). Compared with a name, a
    whole word of ATLAS_WORD_FORMS in it stands for every form of its group
    (_atlas_words, _atlas_begins: "St. Kitts" is Saint Kitts); compared
    with a code, it is read as typed, a word's final period dropped. Codes
    and names are compared as _atlas_fold gives them, from the atlas's own
    tables of them, which hold every place's country and region. An empty
    qualifier is left out: it holds everywhere."""
    wanted = [qualifier for qualifier in qualifiers if (qualifier if isinstance(qualifier, str) else qualifier[0])]
    if not wanted:
        return {}
    key = (_atlas_file_identity(cursor), _atlas_fold)
    if key not in ATLAS_FOLDED_NAMES:
        countries = [(code, _atlas_fold(code), _atlas_fold(name))
                     for code, name in cursor.execute(
                         "SELECT country, name FROM country_names WHERE country > '' ORDER BY country").fetchall()]
        written = {(country, _atlas_fold(name)): abbreviation
                   for abbreviation, country, name in ATLAS_REGION_ABBREVIATIONS}
        by_code, by_initial, abbreviated = {}, {}, {}
        for code, admin1, name, ascii_name in cursor.execute(
                "SELECT country, admin1, name, ascii_name FROM admin1_names "
                "WHERE country > '' ORDER BY country, admin1").fetchall():
            by_code.setdefault(_atlas_fold(admin1), []).append((code, admin1))
            for spelling in {_atlas_fold(name), _atlas_fold(ascii_name)} - {''}:
                by_initial.setdefault(spelling[0], []).append((spelling, code, admin1))
                if (code, spelling) in written:
                    abbreviated.setdefault(written[code, spelling], set()).add((code, admin1))
        ATLAS_FOLDED_NAMES[key] = (countries, by_code, by_initial, abbreviated)
    countries, by_code, by_initial, abbreviated = ATLAS_FOLDED_NAMES[key]
    holding = {}
    for qualifier in wanted:
        typed = qualifier if isinstance(qualifier, str) else qualifier[0]
        if typed in ATLAS_COUNTRY_ALIASES:
            holding[qualifier] = ({ATLAS_COUNTRY_ALIASES[typed]}, set())
            continue
        if not isinstance(qualifier, str) and any(folded == typed for _code, folded, _name in countries):
            holding[qualifier] = ({code for code, folded, name in countries
                                   if folded == typed or name.startswith(typed)}, set())
            continue
        words = _atlas_words(typed)
        coded = typed[:-1] if isinstance(words[-1], int) and typed.endswith('.') else typed
        initial = words[0][0] if isinstance(words[0], str) else ATLAS_WORD_FORMS[words[0]][0][0]
        by_country = {code for code, folded, name in countries if folded == coded or _atlas_begins(name, words)}
        by_region = set(by_code.get(coded, ())) | abbreviated.get(coded, set()) | {
            (code, admin1) for spelling, code, admin1 in by_initial.get(initial, ()) if _atlas_begins(spelling, words)}
        holding[qualifier] = (by_country, by_region)
    return holding


ATLAS_SEARCH_TEXT_MAX = 200
ATLAS_SEARCH_CACHE_SQL = """
SELECT k.id AS key_id, k.geonameid, k.matched, k.historic_name,
       (k.key = ?1) AS exact,
       p.feature_code IN ('PPLC', 'PPLG', 'PPLA') AS seat,
       p.population, p.historical, p.name, p.admin1_code AS admin1,
       p.country_code AS country, p.lat, p.lon
FROM atlas_prefix_results c CROSS JOIN atlas_keys k CROSS JOIN places p
WHERE c.kind = ?2 AND c.scope = ?3 AND c.prefix = ?1
  AND k.id = c.key_id AND p.geonameid = k.geonameid
ORDER BY c.rank
"""
ATLAS_SEARCH_RANGE_SQL = """
WITH candidates AS (
  SELECT k.id AS key_id, k.geonameid, k.matched, k.historic_name,
         (k.key = ?1) AS exact,
         p.feature_code IN ('PPLC', 'PPLG', 'PPLA') AS seat,
         p.population, p.historical, p.name, p.admin1_code AS admin1,
         p.country_code AS country, p.lat, p.lon,
         ROW_NUMBER() OVER (PARTITION BY k.geonameid ORDER BY
           (k.key = ?1) DESC, k.historic_name, (k.matched IS NOT NULL),
           COALESCE(k.matched, ''), k.id) AS choice
  FROM atlas_keys k INDEXED BY atlas_key_range CROSS JOIN places p
  WHERE k.kinds IN (1 << ?2, CASE WHEN ?2 < 2 THEN 3 ELSE 12 END) AND k.key >= ?3 AND k.key < ?4
    AND p.geonameid = k.geonameid
    AND (?5 = '' OR (k.country = ?6 AND (?7 IS NULL OR k.region = ?7)))
)
SELECT * FROM candidates WHERE choice = 1
ORDER BY exact DESC, seat DESC, population DESC, historical, historic_name, geonameid
LIMIT 20
"""


def _atlas_search_scopes(holding, qualifiers):
    """Intersect the qualifiers into disjoint countries and regions.

    The empty scope is the whole atlas; a country code is that country;
    a country, separator and region code is that region. Prefixes need
    at most twenty from each; qualified equality ranges retain every row.
    """
    if not qualifiers:
        return ['']
    countries, regions = holding[qualifiers[0]]
    countries, regions = set(countries), set(regions)
    for qualifier in qualifiers[1:]:
        other_countries, other_regions = holding[qualifier]
        regions = {pair for pair in regions | other_regions
                   if (pair[0] in countries or pair in regions)
                   and (pair[0] in other_countries or pair in other_regions)}
        countries &= other_countries
    return sorted(countries) + [country + '\x1f' + region for country, region in sorted(regions)
                                if country not in countries]


def _atlas_search_rank(row):
    """The order of places, independent of how their matching key was read.

    A seat is a country's capital, its seat of government where that is
    elsewhere, or a first-order region's seat (GeoNames' PPLC, PPLG and
    PPLA); the seat of a lower region is not counted as one."""
    return (-row['exact'], -row['seat'], -row['population'], row['historical'],
            row['historic_name'], row['geonameid'])


def _atlas_key_upper(key):
    """The exclusive upper bound of a nonempty literal Unicode prefix."""
    for at in range(len(key) - 1, -1, -1):
        if ord(key[at]) < 0x10ffff:
            codepoint = ord(key[at]) + 1
            return key[:at] + chr(0xe000 if 0xd800 <= codepoint <= 0xdfff else codepoint)
    return None


def _atlas_key_query(cursor, kind, key, scope, exact=False, sql=None, scopes=None):
    """Read a bound equality or prefix range from its smallest scope index."""
    country, separator, region = scope.partition('\x1f')
    sql = sql or ATLAS_SEARCH_RANGE_SQL
    predicate = "(?5 = '' OR (k.country = ?6 AND (?7 IS NULL OR k.region = ?7)))"
    index = 'atlas_key_range'
    if scope:
        index = 'atlas_region_range' if separator else 'atlas_country_range'
        sql = sql.replace(predicate, 'k.country = ?6 AND k.region = ?7' if separator else 'k.country = ?6')
    sql = sql.replace('INDEXED BY atlas_key_range', 'INDEXED BY ' + index)
    if exact:
        sql = sql.replace('k.key >= ?3 AND k.key < ?4', 'k.key = ?3').replace('LIMIT 20', '')
    elif _atlas_key_upper(key) is None:
        sql = sql.replace(' AND k.key < ?4', '')
    values = (key, kind, key, _atlas_key_upper(key), scope, country, region if separator else None)
    for at in range(1, 8):
        sql = sql.replace(f'?{at}', f':p{at}')
    bindings = {'p' + str(at): value for at, value in enumerate(values, 1)}
    if scopes is not None:
        bindings['scopes'] = json.dumps(scopes)
    cursor.execute(sql, bindings)
    columns = [column[0] for column in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    for row in rows:
        row.pop('choice', None)
    return rows


def _atlas_key_matches(cursor, kind, key, scope='', use_short=True, exact=False):
    """Use a broad-prefix cache, or rank a small scoped index range live."""
    if use_short and not exact and 1 <= len(key) <= 4:
        cursor.execute(ATLAS_SEARCH_CACHE_SQL, (key, kind, scope))
        columns = [column[0] for column in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        if rows:
            return rows
    return _atlas_key_query(cursor, kind, key, scope, exact)


def _atlas_scoped_range_matches(cursor, kind, key, scopes, exact=False):
    """Combine disjoint indexed scope ranges without dropping exact names."""
    if exact and len(scopes) > 1:
        sql = ATLAS_SEARCH_RANGE_SQL.replace(
            "(?5 = '' OR (k.country = ?6 AND (?7 IS NULL OR k.region = ?7)))",
            "(k.country IN (SELECT value FROM json_each(:scopes)) OR "
            "k.country || char(31) || k.region IN (SELECT value FROM json_each(:scopes)) OR "
            "k.country || char(31) || k.region || char(31) || p.admin2_code "
            "IN (SELECT value FROM json_each(:scopes)))")
        return _atlas_key_query(cursor, kind, key, '', True, sql, scopes)
    combined = {}
    for scope in scopes:
        for row in _atlas_key_matches(cursor, kind, key, scope, False, exact):
            gid = row['geonameid']
            if gid not in combined or _atlas_search_rank(row) < _atlas_search_rank(combined[gid]):
                combined[gid] = row
    rows = sorted(combined.values(), key=_atlas_search_rank)
    return rows if exact else rows[:20]


def _atlas_scoped_prefix_matches(cursor, kind, key, scopes, use_short=True):
    """Read cached scopes together and rank only uncached index ranges."""
    rows, cached = [], set()
    if use_short and len(scopes) > 1 and 1 <= len(key) <= 4:
        sql = ATLAS_SEARCH_CACHE_SQL.replace('SELECT k.id', 'SELECT c.scope AS cache_scope, k.id', 1).replace(
            'c.scope = ?3', 'c.scope IN (SELECT value FROM json_each(?3))')
        cursor.execute(sql, (key, kind, json.dumps(scopes)))
        columns = [column[0] for column in cursor.description]
        for values in cursor.fetchall():
            row = dict(zip(columns, values))
            cached.add(row.pop('cache_scope'))
            rows.append(row)
    for scope in scopes:
        if scope not in cached:
            rows.extend(_atlas_key_matches(cursor, kind, key, scope, use_short if len(scopes) == 1 else False))
    return rows


def _atlas_literal_word_matches(cursor, words, scopes, exact=False, folded=True):
    """Keep literal pieces beside recognized abbreviation words.

    A bare word before a comma stays literal in a typed text. Folding a
    long s can also introduce a word form that was typed literally. The
    raw or folded spelling index supplies candidates for these rare cases.
    """
    def match(name):
        at = 0
        for word in words:
            if isinstance(word, str):
                if not name.startswith(word, at):
                    return 0
                at += len(word)
            else:
                for form in ATLAS_WORD_FORMS[word]:
                    if not name.startswith(form, at):
                        continue
                    end = at + len(form)
                    dotted = name[end:end + 1] == '.'
                    rest = end + dotted
                    while name[rest:rest + 1] in (' ', '-'):
                        rest += 1
                    if dotted or rest > end or rest == len(name):
                        at = rest
                        break
                else:
                    return 0
        return 2 if at == len(name) else 1
    cursor.connection.create_function('atlas_word_match', 1, match, deterministic=True)
    prefixes = [words[0]] if isinstance(words[0], str) else ATLAS_WORD_FORMS[words[0]]
    sql = ATLAS_SEARCH_RANGE_SQL.replace('(k.key = ?1)', '(atlas_word_match(k.key) = 2)').replace(
        'AND p.geonameid = k.geonameid',
        'AND atlas_word_match(k.key) > 0 AND p.geonameid = k.geonameid')
    if exact:
        sql = sql.replace('atlas_word_match(k.key) > 0', 'atlas_word_match(k.key) = 2').replace('LIMIT 20', '')
    combined = {}
    for scope in scopes:
        for prefix in prefixes:
            for row in _atlas_key_query(cursor, int(folded), prefix, scope, sql=sql):
                gid = row['geonameid']
                if gid not in combined or _atlas_search_rank(row) < _atlas_search_rank(combined[gid]):
                    combined[gid] = row
    rows = sorted(combined.values(), key=_atlas_search_rank)
    return rows if exact else rows[:20]


def _atlas_search_looks(text):
    """Keep literal commas in a name or region beside a country bracket."""
    looks = _atlas_looks(text) or [([text], ())]
    before, country = text, None
    if text.endswith(')'):
        opened = text.rfind('(')
        inside = text[opened + 1:-1]
        if opened > 0 and len(inside) == 2 and inside.isascii() and inside.isalpha():
            before, country = text[:opened].rstrip(), (_atlas_qualifier(inside),)
            literal = (_atlas_words(before), (country,))
            if before and literal not in looks:
                looks.append(literal)
    for at, char in enumerate(before):
        if char != ',':
            continue
        head, tail = before[:at].rstrip(), _atlas_qualifier(before[at + 1:])
        qualifiers = tuple(q for q in (tail, country) if q)
        look = (_atlas_words(head), qualifiers)
        if head and qualifiers and look not in looks:
            looks.append(look)
    return looks


def _atlas_search_matches(cursor, text, use_short=True):
    """Search every look as typed, folding only a look that finds nothing.

    Qualified exact names keep every match. Other looks keep twenty.
    Raw keys preserve ASCII-only case equivalence. Word keys replace whole
    abbreviation words and their separators with a reserved marker. Neither
    kind interprets punctuation as a pattern. Match details retain the
    alternate spelling and GeoNames' historical flag; atlas_rows keeps the
    established five-column contract for the app's labels.
    """
    text = text.strip()
    if not text or len(text) > ATLAS_SEARCH_TEXT_MAX or any(
            unicodedata.category(ch) in {'Cc', 'Cf', 'Zl', 'Zp', 'Cs'} for ch in text):
        return []
    looks = _atlas_search_looks(text)
    holding = _atlas_holding(cursor, {q for _words, qualifiers in looks for q in qualifiers})
    combined, qualified_exact = {}, {}
    for words, qualifiers in looks:
        scopes = _atlas_search_scopes(holding, qualifiers)
        word_key = any(isinstance(word, int) for word in words)
        for folded in (False, True):
            pieces = [(_atlas_fold(word) if folded else word.translate(ATLAS_ASCII_LOWER))
                      if isinstance(word, str) else word for word in words]
            key = ''.join('\x1f' + str(word) + '\x1f' if isinstance(word, int) else
                          word for word in pieces)
            kind = 2 * word_key + folded
            literal_words = word_key and any(
                isinstance(piece, str) and any(isinstance(part, int) for part in
                    _atlas_words(piece.replace(',', 'x,') + 'x'))
                for piece in pieces[:-1])
            exact_rows = []
            if qualifiers:
                exact_rows = (_atlas_literal_word_matches(cursor, pieces, scopes, True, folded) if literal_words else
                              _atlas_scoped_range_matches(cursor, kind, key, scopes, True))
            if exact_rows:
                rows = exact_rows
            elif literal_words:
                rows = _atlas_literal_word_matches(cursor, pieces, scopes, folded=folded)
            else:
                rows = _atlas_scoped_prefix_matches(cursor, kind, key, scopes, use_short)
            for row in exact_rows:
                gid = row['geonameid']
                if gid not in qualified_exact or _atlas_search_rank(row) < _atlas_search_rank(qualified_exact[gid]):
                    qualified_exact[gid] = row
            for row in rows:
                gid = row['geonameid']
                if gid not in combined or _atlas_search_rank(row) < _atlas_search_rank(combined[gid]):
                    combined[gid] = row
            if rows:
                break
    if qualified_exact:
        # A literal complete name can also have a qualified reading.
        return sorted((r for r in combined.values() if r['exact']), key=_atlas_search_rank)
    return sorted(combined.values(), key=_atlas_search_rank)[:20]


# The atlas's checks so far: (path, device, inode, size, modification and
# change times, as the open file gives them) -> True where its bytes were the
# recorded ones.
_ATLAS_SEEN = {}


def _atlas_digest(f):
    """The SHA-256 of the open file `f`, read whole in blocks: the one read
    of the atlas's bytes the check makes."""
    import hashlib
    digest = hashlib.sha256()
    for block in iter(lambda: f.read(1 << 20), b''):
        digest.update(block)
    return digest.hexdigest()


def _atlas_checked(db_path):
    """Refuse (ShippedDataChanged) an atlas whose bytes are not the recorded
    atlas.db's (SHIPPED_DATA_SHA256), or that cannot be read as a file (a
    folder in its place). The file is opened at each lookup and its identity
    taken from the open file (device, inode, size, modification and change
    times); it is read whole only where that identity has not been checked
    in this process: once for an unchanged file, again whenever any of them
    moves. SQLite then opens the file by its name, so a file swapped in
    between the two is read unseen, and so is a file rewritten in place with
    its size and its times all kept."""
    try:
        with open(db_path, 'rb') as f:
            st = os.fstat(f.fileno())
            key = (os.path.abspath(db_path), st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
            if key not in _ATLAS_SEEN:
                _ATLAS_SEEN[key] = _atlas_digest(f) == SHIPPED_DATA_SHA256['atlas.db']
    except OSError as exc:
        raise ShippedDataChanged(f"atlas.db cannot be read as a file ({exc.strerror}), so it is not read") from None
    if not _ATLAS_SEEN[key]:
        raise ShippedDataChanged("atlas.db is not the file this program was built with "
                                 "(its SHA-256 is not the one recorded), so it is not read")


def atlas_rows(db_path, city_search):
    """The offline atlas's rows for a city text, as (name, admin1,
    country, lat, lon), read through the atlas's indexed search.
    Qualified exact names return every match; other texts return at most
    twenty. An exact name is ranked first, then a seat of government (a
    country's capital, its seat of government where that is elsewhere, or
    a first-order region's seat; not the seat of a lower region),
    population, a living place, a living name and the GeoNames id. app.py's
    _atlas_matches makes the labels and sentences.
    Whole abbreviation words, comma qualifiers and trailing brackets keep
    their established reading. Each look is searched as typed first and
    folded only if it finds nothing.
    An atlas that is not the one shipped is refused first (_atlas_checked;
    read whole once while the file is unchanged); so is a file whose
    metadata does not name the indexed search's version 2, and one that
    names it without the search's tables."""
    # Read-only: the atlas is opened as a
    # file: URI with mode=ro, made from the absolute path by as_uri, which
    # percent-encodes a space, "#", "%", "?" and a letter outside ASCII, so
    # a frozen app in such a folder still finds it; nothing can write
    # through the connection. trusted_schema is turned off: the search's
    # queries call the one function it registers themselves, never through
    # the schema, so nothing else changes.
    # Closed on every path, an error's too: a connection's own `with`
    # commits or rolls back and leaves it open.
    _atlas_checked(db_path)
    with contextlib.closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.execute("PRAGMA trusted_schema = OFF")
        cursor = conn.cursor()
        # An atlas whose metadata names the indexed search's version 2 holds
        # that search's tables and is read through them; any other file is
        # refused, never read.
        # A file without a metadata table names no version. One that names
        # version 2 without the search's tables is refused, never half read.
        tables = {name for (name,) in cursor.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if 'metadata' in tables and cursor.execute(
                "SELECT value FROM metadata WHERE key = 'app_search_version'").fetchone() == ('2',):
            if not {'atlas_keys', 'atlas_prefix_results', 'places'} <= tables:
                raise ShippedDataChanged("atlas.db names the indexed search but does not hold its tables, "
                                         "so it is not read")
            return [(r['name'], r['admin1'], r['country'], r['lat'], r['lon'])
                    for r in _atlas_search_matches(cursor, city_search)]
        raise ShippedDataChanged("atlas.db does not name the indexed search, so it is not read")


# What `from time_zones import *` gives the engine: every name this module
# binds, the standard ones among them.
__all__ = [
    'ATLAS_SEARCH_TEXT_MAX',
    'ATLAS_SEARCH_CACHE_SQL',
    'ATLAS_SEARCH_RANGE_SQL',
    '_atlas_search_scopes',
    '_atlas_search_rank',
    '_atlas_key_matches',
    '_atlas_key_upper',
    '_atlas_key_query',
    '_atlas_scoped_range_matches',
    '_atlas_scoped_prefix_matches',
    '_atlas_literal_word_matches',
    '_atlas_search_matches',
    '_atlas_search_looks',
    '_atlas_checked',
    '_atlas_fold',
    '_atlas_digest',
    'ATLAS_ASCII_LOWER',
    '_atlas_begins',
    'ATLAS_COUNTRY_ALIASES',
    'ATLAS_REGION_ABBREVIATIONS',
    '_atlas_holding',
    '_atlas_file_identity',
    '_atlas_looks',
    '_atlas_qualifier',
    '_atlas_words',
    'ATLAS_WORD_FORMS',
    'atlas_rows',
    '_ATLAS_SEEN',
    'ATLAS_FOLDED_NAMES',
    'CHOSEN_STARTS',
    '_BEFORE',
    'civil_mean_time_label',
    '_clock_states',
    'CIVIL_MEAN_TIMES',
    '_CODE_SUFFIXES',
    'contextlib',
    'datetime',
    '_inside_area',
    'LINKED_ZONES',
    'LINKED_ZONES_TZDATA',
    'LINKED_ZONES_UNTIL_YEAR',
    'LMT_RETURNS',
    'json',
    'MEAN_TIME_CITY_DATES',
    'MEAN_TIME_EXCEPTIONS',
    'mean_time_held',
    'MEAN_TIME_OUTSIDE',
    '_mean_time_states',
    'mean_time_whose',
    'MEAN_TIMES_UNDER_STANDARD_NAMES',
    'NAMED_MEAN_TIMES',
    'named_zone_state',
    'NamedZoneRefusal',
    'os',
    '_OUTLINE_TABLES',
    'Path',
    'OUTSIDE_STRETCHES',
    '_area_zone',
    'place_zone',
    'PlaceClockRefusal',
    '_clock_in_force',
    'PLACE_CLOCK_COLUMNS',
    'PLACE_CLOCK_KINDS',
    '_place_clock_state',
    '_one_change',
    '_zone_change_near',
    'clock_change',
    '_utc_offset_words',
    '_clock_words',
    '_amount_words',
    '_reading_words',
    'clock_change_words',
    '_place_clocks_at',
    'PLACE_CLOCKS',
    '_read_place_clocks',
    '_stretch_end_clock',
    'PLACE_CLOCK_SOURCE_COLUMNS',
    'PLACE_CLOCK_SOURCE_LOCATOR_FORMS',
    'PLACE_CLOCK_SOURCE_BOOKKEEPING_FORMS',
    '_read_place_clock_sources',
    'PLACE_ZONE_AREAS',
    'PLACE_ZONE_RULES',
    'PLACE_ZONES',
    '_pre1970_cast',
    'PRE1970_CONFLICTS',
    'PRE1970_DISPUTED',
    'PRE1970_READ_STATUSES',
    'PRE1970_REFUSAL_NOTES',
    'PRE1970_SOURCES',
    '_pre1970_state',
    'PRE1970_WINDOWS',
    '_read_outline_tables',
    '_read_place_zones',
    '_read_zones_from_the_pinned_package',
    'ShippedDataChanged',
    'SHIPPED_DATA_SHA256',
    '_shipped_file_bytes',
    'sqlite3',
    'timedelta',
    'timezone',
    'unicodedata',
    'ZONE_ALIASES',
    'ZoneInfo',
    'zoneinfo',
    'ZoneInfoNotFoundError',
    'ZONE_PACKAGES',
    '_ZONE_PACKAGES_SEEN',
    '_zone_package',
    '_zone_package_checked',
    'zone_package_digest',
    '_distance_km',
    '_EARTH_RADIUS_KM',
    '_iso6709_degrees',
    'ZONE_RECORD_PLACE_KM',
    'zone_record_place',
    '_ZONE1970_PLACES',
    '_zone1970_places',
]
