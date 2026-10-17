"""The time zones: the pinned database every zone is read from, the zones it
keeps only as a link to another place's record, the named mean times and
the areas and stretches where the database is not trusted (the areas' outlines
read from data/mean_time_outlines.json), and the resolution of a zone's local
clock reading to an offset (named_zone_state); the zone a place takes
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


# Which time-zone database every zone is read from (the owner's ruling 71,
# 2026-10-06): "the app reads time zones only from its pinned tzdata package,
# on every platform, never the computer's own database". zoneinfo looks in
# the directories on its search path first (the system's files on Linux and
# macOS, of whatever release the computer happens to carry) and in the tzdata
# package only where none of them has the zone, so the path is emptied here,
# before this module makes any zone, and zoneinfo's cache is cleared so that
# no zone made earlier from the system's files is handed back. The path is
# the process's, so this holds for every zone made after the import, the
# app's own included; app.py and desktop_launcher.py do the same for
# themselves. Without the package every named zone is refused as unknown,
# never read from the system instead.
def _read_zones_from_the_pinned_package():
    """Point zoneinfo at the tzdata package alone (ruling 71)."""
    zoneinfo.reset_tzpath(to=[])
    ZoneInfo.clear_cache()


_read_zones_from_the_pinned_package()


# The named zones the time-zone database keeps only as a link to another
# place's record (L1-N1 of the re-pass; the owner's ruling 1 on its Q1,
# 2026-10-05). The database keeps no history of these places of its own: its
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
# machine (ruling 71: _read_zones_from_the_pinned_package, at the top of this
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
# their own clocks that the sources establish (PRE1970_WINDOWS, below:
# rulings 82, 104-106, 169 and 171, built before the release by ruling 172):
# a hand-kept, sourced table, not a backzone compile and not read from the
# package. Inside a window the window gives the offset and the label;
# outside every window the name is refused as before. The 1970 cut stays the
# typed local year (ruling 76, kept by ruling 180 (1)): a reading dated
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


# The pre-1970 windows (rulings 82, 104, 105, 106, 169 and 171; ruling 172
# brought them before the release; ruling 180 (1) settled the seam). Outside
# researchers read the laws and gazettes of the linked places, and a blind
# reproduction checked each window against the documents before the owner
# adopted it: Stockholm's in process/outside_tasks_sol_2026-10-06/
# PRE1970_REPRODUCTION.md, rounds 2 and 2b in PRE1970_ROUND2_REPRODUCTION.md
# beside it, rounds 3 and 3b in process/outside_tasks_sol_2026-10-13/
# pre1970_round3/ and pre1970_round3b/ (each *_REPRODUCTION.md). The rows are
# taken from the return tables the rulings adopted (round 1 corrected, round 2
# and its supported corrections, round 2b's delta, rounds 3 and 3b), and
# Stockholm's Swedish-time row from ruling 82 itself, which no return table
# holds (round 2's reproduction, finding 12).
#
# A hand-kept, sourced table, not a backzone compile, and never read from the
# pinned package: inside a window the window gives the state, the offset and
# the label, because the package holds the linked target's record there, not
# the place's own (Chuuk's +10, Pohnpei's +11, Majuro's +12 and Saipan's +10
# in 1941 against the window's +09; Mahe's LMT in 1907; Amsterdam's and
# Luxembourg's WET in 1910; Reykjavik's GMT in 1925 against -01). "Cast under
# their pinned 2026e records" (rulings 169, 171) is the 2026e release's own
# record for each place, the one the reproductions compiled and checked, not
# the package's.
#
# Each window is a UT instant pair, half-open [from, to), with its offset in
# whole seconds and its label. A bound is a review clip, a moment inside what
# the sources establish chosen to keep clear of an undated change, unless the
# ruling ties it to a dated change of the clock; where a window's start is a
# clip, its cast says the date it is cast from is this app's choice, and why,
# as ruling 66's CHOSEN_STARTS do ('chosen'). The starts that are a dated
# change: Stockholm's CET of 1900 (the statute's start of 1900), its summer
# time of 1916 (the statute's 15 May beginning an hour early) and its CET
# after the refused hour (where both readings agree); Bratislava's four
# (orders 84, 181 and 213 of 1946, the corrected day continuing the summer
# time); Luxembourg's correction of 1937 (the decree's 01:00 summer time) and
# the WET window continuing it. Every other start is a clip.
#
# Labels are the return rows', except two the sources call invented: IANA's
# "SET" for Swedish time (round 1's reproduction, 2.4: "an extra-special
# abbreviation style") and its "GMT" for Czechoslovakia's winter time of
# 1946-47 (ruling 104; europe 1035-1036). Those two carry the ruling's plain
# words, as Amsterdam's 1909-1916 window carries its laws' (AMT is IANA's
# abbreviation; ruling 187 (4)). A named mean time -- Swedish time, Amsterdam
# mean solar time, Monaco's Paris mean time -- is cast as CIVIL_MEAN_TIMES'
# are, with civil_mean_time_label's sentence. A standard time carries a
# label only where its start is a clip, in one form (ruling 187 (2)): "The
# clock here was then {label}; the date it is cast from here, ...", since the
# page prints it as the civil clock then;
# a standard time with a dated start carries none, as a named-zone cast does.
# (The anniversary's description takes it mid-sentence, as "the clock ...".)
#
# The seam with the 1970 cut (ruling 180 (1), keeping ruling 76's local
# year): a reading whose typed year is before 1970 is read against the
# windows alone; from 1970-01-01 local it is read from the record. So
# Blanc-Sablon's local 1969-12-31 20:00:00-23:59:59, after its window's end
# at 1970-01-01 00:00 UT and before the local 1970, is refused 'linked'.
# Moving the cut to UT belongs with the cut's revisit after the release.
#
# Every source a row names is in PRE1970_SOURCES, one id per document
# (ruling 171 folded round 3b's duplicates: JP1941NOTICE11 is JAPAN1941TIME,
# JP1934NOTICE42 JAPAN1934TIME, LANATURE1951 NATURE1951, NBS1950_66_73
# NBS1950, MILNE1899_R3B MILNE1899), with how the reproduction that checked it
# read it -- not the researcher's label (ruling 171: DJ1949 an official
# electronic transcription; SEY1906 and SEY1971 a commercial facsimile). The
# two Swedish documents round 1's reproduction read that the returns give no
# id (its section 2.3, R4 and R5) are SE1899SKR38 and SE1878PROP22. Page
# locators are written "p 522", with no full stop: they are pages of gazettes
# and lists, never of the texts the citation register reads.
PRE1970_READ_STATUSES = (
    'official or library scan, read on the page image',
    "official or library scan, read on the researcher's retained copy",
    'library scan, read in its text layer',
    'original scan, read in an earlier round and not re-read',
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
    # Sweden (round 1's reproduction, sections 2.3 and 3.3: the Riksdag's
    # documents read in their open-data text; the statutes and the newspaper
    # not reached).
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
    # Rounds 2 and 2b (round 2's reproduction, section 3.3, and its round 2b
    # part, R2b.4).
    'NO1894': ("Norway, law of 29 June 1894 on standard time: the mean time of 15 degrees E the legal time from 1 "
               "January 1895", 'original scan, read in an earlier round and not re-read'),
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
               'original scan, read in an earlier round and not re-read'),
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
               "in force 1 June 1904", 'original scan, read in an earlier round and not re-read'),
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
               "kept, as in France, on the meridian of Paris", 'original scan, read in an earlier round and not re-read'),
    'MC1911': ("Journal de Monaco no 2757 (28 March 1911), ordinance of 16 March 1911: the legal time, from its "
               "promulgation, France's as the French law of 9 March 1911 fixes it; the clocks put back 9 min 21 s",
               'official or library scan, read on the page image'),
    'VAT1966': ("Vatican City, Ordinanza XXVI (16 May 1966): the summer time of 1966",
                'original scan, read in an earlier round and not re-read'),
    # Round 3 (its reproduction, section 5).
    'AEF1949MARCH': ("Journal officiel de l'Afrique Equatoriale Francaise, 1 May 1949, p 522: the arrete of 8 March "
                     "1949, promulgated by arrete no 1000 of 6 April: the legal time in A.E.F., all year, Greenwich "
                     "mean time advanced one hour", 'official or library scan, read on the page image'),
    'NBS1950': ("R. E. Gould, Standard Time Throughout the World, NBS Circular 496 (1 August 1950), Table 1: French "
                "Equatorial Africa, Gabon and Ubangi Shari 1 h fast; Somaliland 3 h fast; the Seychelles 4 h fast; "
                "the Marianas 9 h fast", 'official or library scan, read on the page image'),
    'NATURE1951': ("Le temps legal dans l'Union francaise, La Nature no 3189 (January 1951), p 14: A.E.F. one hour "
                   "ahead of universal time, the Cote des Somalis three; it names decrees of 18 July 1948 and 27 "
                   "January 1949", 'official or library scan, read on the page image'),
    # Round 3b (its reproduction, sections 2 and 5, ruling 171's read status).
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

# Why a window's start is this app's choice (ruling 66's CHOSEN_STARTS
# precedent): the page reads these, so they name no document.
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
_PACIFIC_NOTE = ("Both bounds are review clips (ruling 171). The notice was in force from 1 April 1941; the window "
                 "starts the day after its printing and ends at the year's end, before the war years. Continuity "
                 "to the end rests on the notice's open-ended text and one official secondary witness, the "
                 "corrected pilot (JAPAN_PILOT_TIME; round 3b's N-2a). The release's own record for the place gives "
                 "+09 throughout; the package's, the linked target's, gives {}.")
_AEF_NOTE = ("Both bounds are review clips (ruling 169), built as returned. The start clip: the gazette prints the "
             "order in summary and gives no date of entry into force, so whether it was in force at Bangui and "
             "Libreville at that instant is not shown, and the +01:00 before it rests on secondary lists only "
             "(round 3's N-2a). One witness: the gazette scan stands only on the Congo government's site (N-2b). "
             "La Nature agrees on the hour, and names decrees of 18 July 1948 and 27 January 1949 as what fixed it "
             "(round 3's reproduction, 2.2, which read neither). The first is perhaps decree 48-1136 of 16 July "
             "1948, which round 3b's reproduction read in the A.E.F. gazette (section 6): it leaves the hour to a "
             "ministerial order on each territory's proposal, and that 18 July was its national publication is "
             "not confirmed.")

PRE1970_WINDOWS = {
    'Europe/Stockholm': (
        _pre1970_window(
            _ut(1879, 1, 2), _ut(1899, 12, 31, 22, 59, 46), 3614, 'Swedish time', _STOCKHOLM_LAW,
            "Ruling 82's first window, which no return table holds (round 2's reproduction, finding 12): built "
            "from ruling 82, which gives the date 1879-01-02 and no instant; the window starts at 00:00 UT, "
            "the narrower reading, 1 h 0 min 14 s after local midnight in Swedish time. The law (SE1878LAW, known "
            "through the database's quotation) set the time from the start of 1879; the offset to the second is "
            "only likely (the watchmakers give 14.8 s, SE1899). The database's label for it, SET, is its own "
            "invention, so the plain name is given. NBS1935 lists Sweden under 1879 among the zone system's "
            "adopters: a weak conflicting secondary (round 1's reproduction, finding 15).",
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
            "years without summer time rest on a 1979 retrospective, not on each year's orders (round 2's "
            "reproduction, finding 7).", chosen=_AFTER_LAW),
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
            "to the second, as IANA has it, not the rounded 20 minutes van Gent says was usually applied (NLGENT; "
            "ruling 106). The start is the cautious gate, a day after the law's 1909-04-30T23:40:28Z; the end is "
            "the 1916 law's midnight converted at +00:19:32 (0.13 s inside summer time at the report's figure). "
            "AMT, the abbreviation the return and ruling 106 give, is IANA's, which its notes call their own "
            "(backzone 1261-1262); the label is the laws' words instead (ruling 187 (4)).", chosen=_AFTER_LAW,
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
            "A correction (ruling 104): the decree put the clocks back 60 minutes at 01:00 summer time in the "
            "night of 2 to 3 October 1937, 00:00 UT; the record has 02:00 UT, wrong for these two hours. The "
            "local hour before 01:00 on 3 October was shown twice, the first time in summer time, which is no "
            "window: it is refused as ambiguous ('turned_back_from').", turned_back_from=3600,
            note_sources=('TZ2026E',)),
        _pre1970_window(
            _ut(1937, 10, 3, 2), _ut(1938, 1, 1), 0, 'WET', ('LU1937',),
            "Greenwich time again under the decree, continuing the corrected hours, to the year's end, before the "
            "unreviewed change of 1938 (ruling 106)."),
    ),
    'Atlantic/Reykjavik': (
        _pre1970_window(
            _ut(1920, 1, 1), _ut(1921, 1, 1), -3600, '-01', ('IS1968BILL', 'ISALMANAC'),
            "Neither chronology has summer time in 1920, and both put the clock an hour behind Greenwich (law 35 "
            "of 1907). 1919 and 1921 stay refused: the bill has summer time in 1917-18 and again from 1939, the "
            "almanac and the database have summers in 1919 and 1921 (ruling 106; PRE1970_CONFLICTS).",
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
            "here. This answers EN-08 for Monaco (ruling 104); the Vatican stays refused (PRE1970_REFUSAL_NOTES).",
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
            "the same page naming the Czech lands alone (round 2b's reproduction, R2b.1)."),
        _pre1970_window(
            _ut(1946, 10, 6, 1), _ut(1946, 10, 7, 1), 7200, 'CEST', ('CS84', 'CS181'),
            "A correction (ruling 106): order 181/1946, read on the Gazette scan, ends summer time on 7 October "
            "at 03:00 summer time, 01:00 UT; the record ends it a day early.", note_sources=('TZ2026E',)),
        _pre1970_window(
            _ut(1946, 10, 7, 1), _ut(1946, 12, 1, 2), 3600, 'CET', ('CS54', 'CS181', 'CS213'),
            "Central European time between the summer and the winter time; the change back shows the local "
            "1946-10-07 02:00 to 02:59:59 twice."),
        _pre1970_window(
            _ut(1946, 12, 1, 2), _ut(1947, 2, 23, 2), 0, 'winter time', ('CS213',),
            "Winter time, +00:00, from 1 December 1946 03:00 Central European time to 23 February 1947 02:00 "
            "winter time (order 213/1946). The database's label for it, GMT, is its own (europe 1035-1036), and "
            "neither it nor its is_dst is copied (ruling 104): ruling 104's plain words. The change shows the "
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
                                       "150 degrees E, +10, against the record's +09 from 1934 on (round 3b's N-2b; "
                                       "PRE1970_CONFLICTS).", chosen=_AFTER_GAZETTE,
                                       note_sources=('JAPAN_PILOT_TIME', 'JAPAN1934TIME')),),
    'America/St_Thomas': (
        _pre1970_window(
            _ut(1967, 12, 24, 4), _ut(1968, 1, 1), -14400, 'AST', ('US1966TIME', 'FR1967ATLANTIC'),
            "Both bounds are review clips (ruling 171). The order took effect on 23 December 1967; the window "
            "starts at 00:00 Atlantic standard time the next day. The only seasonal rule ran from April to "
            "October, so none touches these days.", chosen=_AFTER_ORDER),
    ),
    'Africa/Djibouti': (
        _pre1970_window(
            _ut(1949, 3, 1), _ut(1950, 1, 1), 10800, 'EAT', ('DJ1949', 'NBS1950'),
            "Both bounds are review clips (ruling 171). The arrete's text was read in an official electronic "
            "transcription; no page image of the gazette was found (round 3b's N-2c). NBS1950 and La Nature "
            "(NATURE1951) agree on +3. EAT is the database's label, not the act's.", chosen=_AFTER_GAZETTE,
            note_sources=('NATURE1951',)),
    ),
    'Indian/Mahe': (
        _pre1970_window(
            _ut(1907, 1, 2), _ut(1908, 1, 1), 14400, '+04', ('SEY1906',),
            "Both bounds are review clips (ruling 171). The ordinance was brought into force on 1 January 1907 by "
            "both compilations' statement; the Governor's proclamation itself was not read. Both were read on the "
            "researcher's retained scans (round 3b's N-2d); the 1971 laws (SEY1971) carry the rule unchanged.",
            chosen=_AFTER_LAW, note_sources=('SEY1971',)),
    ),
    'America/Blanc-Sablon': (
        _pre1970_window(
            _ut(1966, 3, 16, 4), _ut(1970, 1, 1), -14400, 'AST', ('QC1966ACT', 'QC1969ACT', 'QC1978T6'),
            "Both bounds are review clips (ruling 171). The 1966 act, in force on its sanction on 15 March 1966, "
            "put the province east of 68 degrees W on Atlantic standard time, the 1969 act east of 63 degrees W: "
            "the whole Lower North Shore either way, with no summer clause for it. Read on the researcher's "
            "retained scans (round 3b's N-2d). The claim of Shanks & Pottenger, which the database's notes "
            "report, that the region kept AST and ADT is unsourced and against the law (N-2e; PRE1970_CONFLICTS). "
            "The window ends at 1970-01-01 00:00 UT, four hours before the local 1970: the local 1969-12-31 "
            "20:00 to 23:59:59 is refused (ruling 180 (1)).", chosen=_AFTER_LAW, note_sources=('TZ2026E',)),
    ),
}

# The stretch where the sources disagree (ruling 82): each with the offsets
# its conflicting readings give. A reading either offset puts inside it is
# refused ('disputed'), whatever window would hold it.
PRE1970_DISPUTED = {
    'Europe/Stockholm': (
        {'from': _ut(1916, 9, 30, 22), 'to': _ut(1916, 9, 30, 23), 'offsets': (3600, 7200),
         'sources': ('SE1916LAW', 'SE1926', 'SEDN1916'),
         'note': ("The statute's wording, 30 September ending an hour late (SE1916LAW, restated by SE1926), puts "
                  "the change at 22:00 UT, Central European time from then (+01:00); the newspaper the database "
                  "follows (SEDN1916) puts it at 23:00 UT, summer time to then (+02:00). Round 1's reproduction, "
                  "section 2.5; its record STOCKHOLM1916.")},
    ),
}

# The conflicts the reproductions recorded on these names, and how each is
# built (ruling 171: the notes go into the window notes and conflict rows).
PRE1970_CONFLICTS = (
    {'zone': 'Europe/Stockholm', 'when': '1916-09-30 22:00-23:00 UT',
     'conflict': "The statute's wording against the newspaper practice on the hour of the autumn change.",
     'sources': ('SE1916LAW', 'SE1926', 'SEDN1916'), 'built': 'Refused: PRE1970_DISPUTED.'},
    {'zone': 'Europe/Stockholm', 'when': '1879',
     'conflict': ("NBS1935's Table 1 lists Sweden under 1879 among the zone system's adopters, against the 1878 "
                  "law's mean time of three degrees west of Stockholm, 14 s from Central European time."),
     'sources': ('NBS1935', 'SE1979', 'SE1899'),
     'built': "Discounted as a weak secondary (round 1's reproduction, finding 15): Swedish time is cast."},
    {'zone': 'Europe/Oslo', 'when': '1940-1945',
     'conflict': "NO2018 gives summer time in 1943-45, SE1979 in 1940-45.",
     'sources': ('NO2018', 'SE1979'), 'built': 'No window: 1940 to 1946 stays refused.'},
    {'zone': 'Europe/Amsterdam', 'when': '1909-1916',
     'conflict': ("The 1909 report's Greenwich time plus 19 m 32.13 s, and the 1916 law's midnight at +00:19:32, "
                  "against van Gent's rounded 20 minutes usually applied."),
     'sources': ('NLOBS1909', 'NL1916', 'NLGENT'), 'built': '+00:19:32, as ruling 106 rules and IANA has it.'},
    {'zone': 'Europe/Luxembourg', 'when': '1929-04-20 23:00 UT on',
     'conflict': ("The 1929 decree makes Central European time the legal time again, where the database labels "
                  "the stretch WEST, a summer time (round 2b's reproduction, R2b.3)."),
     'sources': ('LU1929', 'TZ2026E'), 'built': 'No window rests on it: the label only, the offset agrees.'},
    {'zone': 'Europe/Luxembourg', 'when': '1937-10-03 00:00-02:00 UT',
     'conflict': "The decree's change at 01:00 summer time against the record's 02:00 UT.",
     'sources': ('LU1937', 'TZ2026E'), 'built': 'Corrected: a WET window from 00:00 UT (ruling 104).'},
    {'zone': 'Europe/Bratislava', 'when': '1946-10-06 01:00 UT to 1946-10-07 01:00 UT',
     'conflict': "Order 181/1946 ends summer time on 7 October; the record ends it on 6 October.",
     'sources': ('CS181', 'TZ2026E'), 'built': 'Corrected: a CEST window for the day (ruling 106).'},
    {'zone': 'Atlantic/Reykjavik', 'when': '1919 and 1921',
     'conflict': ("The 1968 bill has summer time in 1917-18 and again from 1939; the almanac and the database "
                  "have summers from 20 February to 16 November 1919 and from 20 March to 23 June 1921."),
     'sources': ('IS1968BILL', 'ISALMANAC', 'TZ2026E'), 'built': 'No window in 1919 or 1921 (ruling 106).'},
    {'zone': 'Pacific/Saipan', 'when': '1934 on',
     'conflict': ("The 1934 notice puts the Saipan branch on 150 degrees E, +10, and NBS1935 gives the Marianas "
                  "+10, against the record's +09 from 1901 to 1944; NBS1950 gives the Marianas +09."),
     'sources': ('JAPAN1934TIME', 'NBS1935', 'NBS1950', 'TZ2026E'),
     'built': 'Outside the window, which rests on the 1941 notice alone (round 3b\'s N-2b).'},
    {'zone': 'America/Blanc-Sablon', 'when': '1966-1969',
     'conflict': ("Shanks & Pottenger, as the database's notes report, have this region keeping AST and ADT; "
                  "the 1966 and 1969 acts put it on Atlantic standard time with no summer clause."),
     'sources': ('TZ2026E', 'QC1966ACT', 'QC1969ACT'),
     'built': "The law is followed: AST all year in the window (round 3b's N-2e)."},
)

# Notes on linked names with no window, kept with the name (ruling 171).
PRE1970_REFUSAL_NOTES = {
    'America/Curacao': (
        "The Amigoe of 29 December 1964 reports that the clocks of the Leeward islands would go forward half an "
        "hour at the new year, under a decree the paper had not seen; nothing covers 1965-69. Cited for Aruba "
        "but bearing on Curacao (round 3b's N-4a): a refusal, no window.", ('AMIGOE1964DEC29',)),
    'Pacific/Wallis': (
        "The 1948 order is a lead only, known through a search-engine copy, and its identity is unconfirmed (a "
        "ministerial arrete of 26 November 1948 by its title, a decree of 6 December 1948 by its link; round "
        "3b's N-6b): no window.", ('WALLIS1948LEAD',)),
    'Asia/Phnom_Penh': (
        "Milne's 1899 Saigon time, 'used in Lower Laos, Cambodia, Annam', is an 1899 snapshot with no bounds; "
        "the researcher read it as +7:16:35, the check reads 7 h 16 m 56 s fast on the scan (round 3b's N-6a): "
        "no window.", ('MILNE1899',)),
    'Europe/Vatican': (
        "Nothing read covers 1929-1970 but the 1966 summer time, and the state did not exist before 1929: it "
        "stays refused (round 2's reproduction, finding 14; EN-08).", ('VAT1966',)),
}

del _STOCKHOLM_LAW, _PACIFIC_NOTE, _AEF_NOTE, _AFTER_LAW, _AFTER_GAZETTE, _YEAR_WITHOUT_SUMMER, _AFTER_ORDER
del _pre1970_window, _ut

# The other links of the same release that name a zone the tables below key
# on: another name for that zone, with no row of its own in zone.tab
# (Asia/Calcutta for Asia/Kolkata, Europe/Kiev for Europe/Kyiv), read as that
# zone -- "cast as its zone", above -- by named_zone_state, whose tables are
# keyed on the zone's own name (EN-07 of the notes lanes: Asia/Calcutta 1880
# was cast at MMT, unlabelled, where Asia/Kolkata is refused). Derived from
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


# D1's reach: the named mean times (the owner's ruling 35 on the re-pass,
# 2026-10-05). After a zone's first record (its reference city's LMT, which D1
# refuses) many zones hold a city's named mean time -- PMT, RMT, MMT -- before
# any standard time. Such a time is CAST, with a label, only where it was the
# area's civil clock (CIVIL_MEAN_TIMES, keyed on the name the place lookup
# returns and on the period); everywhere else it is REFUSED as D1 refuses LMT,
# since it puts one city's meridian under every birthplace of the zone. The
# lists below are the research's, in one place: the corpus's
# process/hostile_pass_2026-10-03/repass/readings/D1_REACH_RESEARCH.md
# (section 1's table of the 79 zones and their named states, section 3's
# groups, section 2's sources), read against the compiled zones zoneinfo
# reads. The database's own scope statement is the reason for the default:
# a zone's pre-1970 entries "are often accurate for only a small subset of
# that region" (theory.html:690-692).
#
# Ruling 66 of the owner (2026-10-06, the time-zone cross-check,
# process/hostile_pass_sol_2026-10-06/TZ_CROSSCHECK_RAW.md) applies ruling
# 35's test strictly: a named mean time is cast only for the stretches the
# database's own notes establish as the area's civil clock, and the rest is
# refused as uncertain. The notes are read in the source of the IANA release
# the pinned tzdata package is built from (2026e, ruling 71); every
# file:line in these comments is that release's.
#
# NAMED_MEAN_TIMES: each zone whose record holds a named mean time after its
# first record, with the states (abbreviation, offset) of that stretch,
# including the summer forms the database names with them (Dublin's IST,
# Riga's LST, Moscow's MST and MDST, Bermuda's and La Paz's BST), each written
# with the mean time it is kept on, which its label names. A reading is
# matched on its own state, so a stretch of standard time between two named
# stretches (Chile 1910-1916, Tallinn 1918-1919) is not touched. A linked
# name is looked up through its target; before 1970 ruling 1 refuses it first,
# or its windows read it (PRE1970_WINDOWS) and this table is not reached.
# The database's NST of 1884-1935 is St John's mean time, -3:30:52, under a
# standard time's name ("Zone America/St_Johns -3:30:52 - LMT 1884" then
# "-3:30:52 StJohns N%sT ... 1935 Mar 30", northamerica:1464-1467; Goose Bay
# casts Labrador at it, northamerica:1477-1480): ruling 61 (b) classes it by
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
# the period it is cast in (None: the whole stretch). Ruling 35 took the
# research's group (a); ruling 66 keeps of it only what the database's notes
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
#     earlier -0:43:08 is unsourced: refused before 1970 (ruling 81 (a)).
#   Europe/Rome, RMT from 1887-01-01: in force from 1866-12-12 "in the
#     railways, the post office and the telegraph, not only for the internal
#     service but also for the public" (europe:1729-1734) -- service time, as
#     Zurich's postal and telegraph time is -- the public clocks following
#     city by city, "and the last city was Cagliari in 1886"
#     (europe:1734-1737). So the mainland is cast from the first day after
#     that year (ruling 81 (b)); Milan, Turin, Bologna and Venice from their
#     own dates by coordinates (MEAN_TIME_CITY_DATES); Sicily and Sardinia
#     refused (MEAN_TIME_EXCEPTIONS); Trentino, South Tyrol, Trieste and
#     Gorizia refused (MEAN_TIME_OUTSIDE).
#   Pacific/Auckland, NZMT from its start: "the introduction of standard time
#     in New Zealand" at +11:30 (australasia:983, 1697-1698).
#   Pacific/Easter, EMT from 1891-01-01: Shanks & Pottenger say "Pacific/Easter
#     standardized on 109W22 in 1890" (southamerica:1101-1102), the island's
#     standard time on one secondary source, as Argentina's is on one; the year
#     only, so from the first day after it (ruling 66: "Easter weighed by the
#     same threshold").
# Refused, though the research put them in group (a):
#   Europe/Riga, RMT (and its summer LST) 1880-1926, and Asia/Tbilisi, TBMT
#     1880-1924: "Byalokoz 1919 says Latvia was 1:36:34" (europe:1896-1898),
#     "Byalokoz 1919 says Georgia was 2:59:11" (asia:1194-1196). Byalokoz's
#     book gives the clocks Russia's decree of 1919-07-01 replaced
#     (europe:47-55): a country-wide value at some time before mid-1919, with
#     neither a start nor an end, so no stretch is established (ruling 81 (c),
#     as Zurich).
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
# leave unclear, and St John's NST (ruling 61 (b): the Newfoundland notes,
# northamerica:1404-1436, date only summer-time rules, and their one Labrador
# statement is of 2017) -- is refused. Europe/Monaco's Paris mean time of
# 1892-1911, which the research also counts in group (a), is cast in its own
# window, not here (ruling 104; PRE1970_WINDOWS); Europe/Vatican, counted
# there too, is a linked name ruling 1 still refuses before 1970.
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

# Ruling 66's row 101 (the cross-check: an attestation date "can be a
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
# from the code's AGPL (ruling 98; ruling 179 S-04 (b); the OpenStreetMap
# outlines' licence review, process/outside_tasks_sol_2026-10-06/
# odbl_outlines/return/REPORT.md, section 3). The file's own "schema" says
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
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'mean_time_outlines.json')
    with open(path, encoding='utf-8') as f:
        tables = json.load(f)['tables']

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
# ruling 66 refuses Bern mean time throughout.
MEAN_TIME_EXCEPTIONS = _OUTLINE_TABLES['exceptions']

# Ruling 61 (a), with ruling 66's "Rome by city adoption dates" and ruling
# 81 (b): Rome's time reached the public clocks city by city -- "Milano set
# the public watches on the Rome time on the same day (12th December 1866),
# Torino and Bologna on the 1st January 1867, Venezia the 1st May 1880"
# (europe:1734-1736) -- so inside each of these cities, found by the
# coordinates, RMT is cast from the city's own date, earlier than the rest of
# the mainland's 1887-01-01 (CIVIL_MEAN_TIMES), and a reading before that
# date is refused ('mean_time_city'). What each kept before is not said, so
# the page says only when its public clocks took Rome's time. Each area is a
# set of rings of (latitude, longitude) vertices, today's, not the cities' of
# 1866-1880 (redrawing them as they were is a lane of its own after the
# release, ruling 179 S-02): Milan, Turin and Bologna, each
# municipality's boundary as OpenStreetMap draws it ((c) OpenStreetMap
# contributors, ODbL), simplified to within about 130 m (Turin with the small
# detached piece of its territory); Venice, the lagoon city with its islands
# from Murano and the Vignole to the Lido and Malamocco, drawn over the
# lagoon, kept off the mainland (Mestre, Marghera, Fusina, Punta Sabbioni),
# off Pellestrina, and round Sant'Erasmo and the Lazzaretto Nuovo, so that no
# island is cut.
MEAN_TIME_CITY_DATES = _OUTLINE_TABLES['cities']

# Ruling 81 (e): places a zone covers today that were not then part of the
# country whose clocks its notes describe. The notes speak of France's law and
# Italy's decree and say nothing of Alsace, Lorraine's Moselle, Trentino,
# South Tyrol, Trieste or Gorizia (no such name in the europe file); so a
# reading there under Paris's or Rome's mean time is refused
# ('mean_time_outside'), by coordinates, inside today's borders (redrawing
# them as they were is a lane of its own after the release, ruling 179
# S-02). Each area is today's departments (Bas-Rhin,
# Haut-Rhin, Moselle) or provinces (Trento and Bolzano; Trieste and Gorizia)
# as OpenStreetMap draws them ((c) OpenStreetMap contributors, ODbL), joined:
# the border with the rest of the country simplified to within about 300 m,
# and the border with another country replaced by a line drawn wide through
# that country, whose points are in another zone and never reach this test;
# five islets of the Grado lagoon and Trieste's harbour are small boxes.
MEAN_TIME_OUTSIDE = _OUTLINE_TABLES['outside']

# Rulings 97 and 102 of the owner (2026-10-06): after the mean time, Paris's
# and Rome's records cast France's and Italy's clocks on the places of
# MEAN_TIME_OUTSIDE, which then belonged to neither country or whose clocks
# the sources do not establish (the research of
# process/outside_tasks_sol_2026-10-06/pre1919_annexed/return/REPORT.md, on
# which ruling 102 rests). Those stretches are REFUSED there too
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
# Replacing the bounds and the borders when sources date them is a lane of its
# own after the release (ruling 179 S-02); formerly Austrian places outside
# today's four provinces wait for that lane too.
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
    """What a cast at a group (a) named mean time says of itself (ruling 35).
    A summer form (Dublin's IST, Bermuda's BST) is not itself a mean time: it
    names the mean time it was kept on. `chosen` is (first day, why) where
    that day is this app's choice (CHOSEN_STARTS, ruling 66's row 101); a
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
# northamerica:1464-1467; ruling 61 (b)). A reader who knows NST as a
# standard time is told whose meridian it is (D1R2's check, note 17).
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
    OUTSIDE_STRETCHES; rulings 97 and 102),
    'ambiguous' (the repeated hour of a fall-back) and 'nonexistent' (the
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
    the record holds no time there, and the refusal says so rather than D1's
    "before ... kept any standard time" (ruling 61 (d))."""

    def __init__(self, kind, *, abbreviation=None, area=None, until=None, since=None, kept_on=None, country=None):
        super().__init__(kind)
        self.kind = kind
        self.abbreviation = abbreviation
        self.area = area
        self.until = until
        self.since = since
        self.kept_on = kept_on
        self.country = country


class PlaceClockRefusal(NamedZoneRefusal):
    """A Standard-time cast refused by the place rather than the zone
    (place_zone, below): 'clock_choice' (a place where the sources leave the
    clock to the record: the `area` rule's two `clocks` differ at that
    moment, or the moment is in an `interval` the sources leave unsettled)
    and 'unsettled' (a listed place no source settles: the `clocks` the
    sources give it). `clocks` is ((zone, offset in seconds or None), (zone,
    offset or None)), each clock read at the moment; `interval` is (start,
    end), local readings, the start (1, 1, 1, 0, 0, 0) for "before"."""

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

    D1 of the owner (2026-10-03): a reading earlier than the zone's first
    rule is REFUSED, not cast. The zone's database begins with the local
    mean time of the zone's reference city (Calcutta for Delhi, Rome for
    Florence), which is not the birthplace's own meridian, and naming it
    after the zone would put another city's longitude under the
    birthplace's name. "The zone's first rule" is the moment the database's
    first offset ends: the state in force at the beginning of the record
    (what a `ZoneInfo` gives the year 1) holds until the zone's first
    transition, so a reading that carries exactly that offset and
    abbreviation is a reading before the first rule. (An anniversary was
    once exempt from this; ruling 35 ended that, below.)

    Ruling 1 of the owner on the re-pass (2026-10-05): a reading dated
    before 1970 in a zone the database keeps only as a link to another
    place's record (LINKED_ZONES) is REFUSED, as D1 refuses what the app
    cannot vouch for: the state the database holds then is the other
    place's. This holds for an anniversary too, since the anniversary
    would be cast at the other place's clocks under the birthplace's name
    just as the birth would. The test
    reads the name and the date only, never the machine's database, so it
    is the same on every machine; a plain alias (Asia/Calcutta) is not on
    the list and is read as its zone.

    Rulings 82, 104-106, 169 and 171 of the owner (the pre-1970 windows,
    built by ruling 172; the seam by ruling 180 (1)): before 1970 a linked
    name with windows of its own clocks (PRE1970_WINDOWS) is read against
    them alone, never against the package's record, which is the linked
    target's. For each window the local reading less the window's offset is
    a UT instant, and the window holds the reading when that instant falls
    inside it. Exactly one window holding it casts the window's state: its
    offset and label, with a named mean time's sentence, or the sentence
    that its first day is this app's choice where the window starts at a
    review clip. Two windows holding it is a fold ('ambiguous'), and so is
    the hour before a window whose start put the clocks back from a time
    that is no window of its own ('turned_back_from'); none holding it,
    between two windows that abut with a change of offset, is a gap
    ('nonexistent'); none holding it otherwise is 'linked', as before. A
    reading that either of a disputed stretch's offsets puts inside it
    (PRE1970_DISPUTED: Stockholm's 1916-09-30 22:00-23:00 UT, +01:00 by the
    statute's wording and +02:00 by the newspaper) is refused first
    ('disputed'). An impossible date is 'julian'. The 1970 cut stays the
    typed local year (ruling 76): a reading dated before 1970 is read
    against the windows alone, one dated from 1970-01-01 from the record. So
    Blanc-Sablon's local 1969-12-31 20:00:00-23:59:59, after its window's
    end at 1970-01-01 00:00 UT and before the local 1970, is refused
    'linked'; moving the cut to UT belongs with the cut's revisit after the
    release.

    Ruling 35 of the owner (2026-10-05, D1's reach): D1's test is "the
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
    record: ruling 35 makes an anniversary before a zone's first rule, or in
    a refused period, unavailable.

    Ruling 66 of the owner (2026-10-06): the test applied strictly, a named
    mean time cast only for the stretches the database's notes establish
    (CIVIL_MEAN_TIMES' dates); with ruling 61 (a), inside a city whose public
    clocks the notes date later, REFUSED until that date
    ('mean_time_city'); with ruling 61 (b), St John's mean time under the
    name NST classed by the same test. The exceptions and the cities are
    read before the zone's own period.

    Ruling 81 of the owner (2026-10-06): Monrovia from 1970; Rome's mainland
    from 1887-01-01 and Milan, Turin, Bologna and Venice from their own dates,
    each a cast area by coordinates; Riga and Tbilisi refused throughout;
    Alsace-Moselle under Paris's mean time and Trentino, South Tyrol, Trieste
    and Gorizia under Rome's REFUSED by coordinates ('mean_time_outside').
    Where the first day cast is this app's choice, the label says so
    (CHOSEN_STARTS).

    Rulings 97 and 102 of the owner (2026-10-06): inside those parts, Paris's
    WET from 1911-03-11 and Rome's CET from the end of Rome mean time (1893),
    each to 1921-01-01, are REFUSED by coordinates ('outside_clock')."""
    if zone_name.startswith('Etc/'):
        raise NamedZoneRefusal('sea')
    if zone_name in LINKED_ZONES and int(year) < LINKED_ZONES_UNTIL_YEAR:
        if zone_name in PRE1970_WINDOWS:
            return _pre1970_state(zone_name, year, month, day, hour, minute, second)
        raise NamedZoneRefusal('linked')
    # An alias is read as the zone it names (EN-07): the tables below are
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
        # Rulings 97 and 102: the country's clock cast on a place whose clock
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


# The zone a place takes (ATLAS1's rebuild: rulings 150, 157 (1), 172, 179
# S-03, 180 (2) and (3), 190; C-01 and C-17 of the outside pass,
# process/hostile_pass_sol_2026-10-13/REPRO_C_D.md). A place takes the zone
# the zone boundaries give its coordinates (the derived zone), except where
# the hand-kept list, data/place_zones.tsv, or an area rule says otherwise,
# each with its source. The list is keyed on the place's coordinates exactly
# as the atlas gives them, never on the atlas choice, so a chart saved from
# the atlas and restored by its coordinates is cast as its pick was (179
# S-06). Its rules: 'geonames' (GeoNames' own zone, where the derived zone
# is another country's and GeoNames' is the place's own: C-01, and C-17's
# Liberpolis, which the boundaries leave in no country), 'kept' (the derived
# zone, a listed exception to the rule that would change it), 'unsettled' (no
# source settles the clock: a Standard-time cast is refused) and 'area:NAME'.
# Building the list is described in the build's report
# (process/ui_phase_2026-10/LANE_ATLAS1_REBUILD_BUILD.md).
def _read_place_zones():
    """{(lat, lon): row} from data/place_zones.tsv, each row a dict of its
    columns; a malformed file stops the import, as the outlines' does."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'place_zones.tsv')
    with open(path, encoding='utf-8', newline='') as f:
        lines = [line for line in f.read().split('\n') if line and not line.startswith('#')]
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

# The areas where the outside research (process/outside_tasks_sol_2026-10-06/
# DISPUTED_CLOCKS_RAW.md) leaves the clock to the person, or settles it by a
# date. Each reaches the places its register names, through the list's rows
# 'area:NAME'; an area with a 'boundary' also reaches every point the zone
# boundaries give that zone (zone.tab names Asia/Hebron "West Bank" and
# Asia/Urumqi "Xinjiang Time"). Ruling 180 (2): there a Standard-time cast is
# refused, naming both clocks; ruling 190 (b): it is made when both clocks
# give the same offset at that moment, except in an 'unsettled' interval
# (Sol's uncertain intervals: the West Bank before 1967 and around 1995-96,
# ruling 190 (b); all of Saskatchewan's 520 records before 1972-04-30,
# ruling 190 (a)). Sokhumi follows GeoNames' Europe/Moscow from 2010 (Sol's
# (b), "likely from at least 2010"), and is refused before it and in the
# hours of 2014-10-26 whose turning back the sources leave unsettled. The
# intervals are local readings, half open. Ruling 201 (1): the West Bank's
# rule reaches every West Bank row GeoNames codes PS (its list rows), the
# places both sources put in Asia/Jerusalem included. Ruling 198 (1): the
# five border places whose clock no record in hand settles (the Golan's
# three rows coded SY, Abu Musa's coded AE, one Paracels row coded VN; the
# reproduction's finding their only source) are refused as these areas are,
# naming the zone their coordinates give and their coded country's: 'golan',
# 'abu_musa' and 'paracels', the first clock the derived one. Ruling 202: so
# are the four kept on the same finding with GeoNames' record giving the
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


# The atlas lookup (ruling 175 (7): moved from app.py as a step of its own,
# before ATLAS1's behavioural changes). app.py keeps the sentences and the
# labels, which are written with the engine's degrees_text; the fold, the
# prefix and the query are here.


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


def _like_prefix(text):
    """A typed text as a LIKE prefix: the text itself, never a pattern."""
    return text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


def atlas_rows(db_path, city_search):
    """The offline atlas's rows for a city text, as (name, admin1,
    country, lat, lon) in the atlas's own order, the most populous first,
    at most 20; an empty list when there are none. The lookup of
    app.py's _atlas_matches, which makes the labels and the sentences."""
    # Read-only (SC-07 of the security sweep): the atlas is opened as a
    # file: URI with mode=ro, made from the absolute path by as_uri, which
    # percent-encodes a space, "#", "%", "?" and a letter outside ASCII, so
    # a frozen app in such a folder still finds it; nothing can write
    # through the connection. trusted_schema is turned off: the query calls
    # atlas_fold itself, never through the schema, so nothing else changes.
    # Closed on every path, an error's too: a connection's own `with`
    # commits or rolls back and leaves it open (ruling 140, LS-06).
    with contextlib.closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.execute("PRAGMA trusted_schema = OFF")
        cursor = conn.cursor()
        # The typed text is a prefix, never a pattern: LIKE's own wildcards
        # and the escape are escaped, so "%" alone matches no city and
        # "Flor%" is not Florianopolis (the hostile pass of 2026-09-22, M1).
        # Surrounding spaces are not part of a name (L6).
        #
        # NOCASE and LIKE fold ASCII letters only, so "évora", "ZÜRICH" or
        # an accent typed as a separate mark found nothing. A text that
        # finds nothing as typed is looked up once more, folded: the text
        # and each name are compared as _atlas_fold gives them (the last
        # arm, on only that second look). A text that finds anything as
        # typed keeps exactly the options it had, so "Groß" is not also
        # "Grosseto", as a casefold of both would make it. A name all
        # ASCII is compared in SQLite itself -- its fold is its lower
        # case, which LIKE already ignores -- and only the rest (one name
        # in five) is folded in Python.
        conn.create_function("atlas_fold", 1, _atlas_fold, deterministic=True)
        text = city_search.strip()
        for pattern, folding in ((_like_prefix(text), 0), (_like_prefix(_atlas_fold(text)), 1)):
            cursor.execute("""
                SELECT name, admin1, country, lat, lon
                FROM cities
                WHERE name LIKE ?1 ESCAPE '\\' COLLATE NOCASE OR ascii_name LIKE ?1 ESCAPE '\\' COLLATE NOCASE
                   OR (?2 AND CASE WHEN length(CAST(name AS BLOB)) = length(name) THEN name
                                   ELSE atlas_fold(name) END LIKE ?1 ESCAPE '\\')
                ORDER BY population DESC
                LIMIT 20
            """, (pattern, folding))
            matches = cursor.fetchall()
            if matches:
                break
    return matches


# What `from time_zones import *` gives the engine: every name this module
# binds, the standard ones among them.
__all__ = [
    '_atlas_fold',
    'atlas_rows',
    'CHOSEN_STARTS',
    '_BEFORE',
    'civil_mean_time_label',
    '_clock_states',
    'CIVIL_MEAN_TIMES',
    'contextlib',
    'datetime',
    '_inside_area',
    '_like_prefix',
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
    'sqlite3',
    'timedelta',
    'timezone',
    'unicodedata',
    'ZONE_ALIASES',
    'ZoneInfo',
    'zoneinfo',
    'ZoneInfoNotFoundError',
]
