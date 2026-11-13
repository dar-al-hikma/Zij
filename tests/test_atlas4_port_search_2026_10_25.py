"""The app's indexed search over atlases built from small GeoNames files."""
import ast
import contextlib
import hashlib
import sqlite3
import shutil
import random
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

import build_atlas as builder
import time_zones as zones
from test_atlas4_builder_2026_10_23 import make, place


@pytest.fixture(scope='module')
def atlas(tmp_path_factory):
    root = tmp_path_factory.mktemp('search')
    places = [
        place(1, 'Saint Paul', admin1='MN', pop=300000, code='PPLA'),
        place(2, 'Saint-Paul', country='FR', admin1='01'),
        place(3, 'St. Louis', admin1='MO'), place(4, 'Sankt Gallen', country='CH', admin1='SG'),
        place(5, 'Fort Worth', admin1='TX'), place(6, 'Mount Vernon', admin1='NY'),
        place(7, 'Sault Ste. Marie', country='CA', admin1='08'),
        place(8, 'Kaliningrad', country='RU', admin1='23'),
        place(9, 'Istanbul', country='TR', admin1='34', pop=1000000),
        place(10, 'Großklein', country='DE', admin1='01', ascii_name='Grossklein'),
        place(11, 'Grossevil', country='DE', admin1='01', pop=999999),
        place(12, 'Évòra', country='PT', admin1='08', ascii_name='OtherSpelling'),
        place(13, 'İnanöz', country='TR', admin1='01', ascii_name='Different'),
        place(14, 'Yukarı Beğdeş', country='TR', admin1='01', ascii_name='Unrelated'),
        place(15, 'Vancouver', country='CA', admin1='02'),
        place(16, 'Sydney', country='AU', admin1='02'),
        place(17, 'London', country='GB', admin1='ENG'),
        place(18, 'Washington', admin1='DC'),
        place(19, 'Basseterre', country='KN', admin1='03'),
        place(20, 'Frankfurt (Oder)', country='DE', admin1='11'),
        place(21, 'Misato, Saitama', country='JP', admin1='34'),
        place(22, 'Ham', admin1='MN', pop=1),
        place(23, 'Saint Paul St.', admin1='MN'),
        place(24, 'Saintes', country='FR', admin1='01'),
        place(25, 'Stuttgart', country='DE', admin1='01'),
        place(26, 'Mountain View', admin1='CA'),
        place(27, 'St. Saint Fort Mount End', admin1='MN'),
        place(28, 'Ruin', code='PPLH'), place(29, 'Ruin'),
        place(30, 'Tie'), place(31, 'Tie'),
        place(32, 'Seatown', pop=1, code='PPLA'),
        place(33, 'Seatop', pop=1000000),
        place(34, 'Common', country='CA', admin1='02', pop=1),
        place(35, 'Å', country='SE', admin1='01', ascii_name='A'),
        place(36, 'Kharkhorin', country='MN', admin1='01'),
        place(37, 'Saint Saint Vale', admin1='MN'),
        place(38, 'St. Saint Vale', admin1='MN'),
        place(39, 'Singapore', country='SG', admin1=''),
        place(40, 'Écho', country='PT', admin1='08', ascii_name='Unrelated Echo'),
        place(41, 'Empty Region', country='SG', admin1=''),
        place(42, '12', admin1='01'),
        place(43, 'Close Twins', admin1='MN', lat=10.000011, lon=20.000011, pop=300),
        place(44, 'Close Twins', admin1='MN', lat=10.000022, lon=20.000022, pop=200),
        place(45, 'Close Twins', admin1='MN', lat=10.000033, lon=20.000033, pop=100),
        place(46, 'Same Point', admin1='MN', pop=300),
        place(47, 'Same Point', admin1='MN', pop=200),
        place(48, 'Same Point', admin1='MN', pop=100),
        place(49, 'Close Twins', admin1='MN', lat=10.000034, lon=20.000034, pop=50),
        place(50, 'Misato', country='JP', admin1='34', pop=1000),
        place(51, 'Saint , St. Vale', admin1='MN'),
        place(52, 'St. , St. Vale', admin1='MN'),
        place(53, chr(0xd7ff) + 'Edge'),
        place(54, 'Trailing,', admin1='MN'), place(55, 'Trailing', admin1='MN', pop=1000),
    ]
    places += [place(100 + i, 'Hampton ' + str(i), pop=1000000, code='PPLA') for i in range(25)]
    places += [place(200 + i, 'Common', admin1='TX', pop=10000 + i, lat=30 + i / 10, lon=-100)
               for i in range(25)]
    places += [place(300 + i, name, lat=i, lon=i + 1) for i, name in enumerate(
        ['%', '_', 'Flor%', 'Flor_', '\\', 'Quote\'s', '"', 'a OR b', 'القاهرة', 'Москва'])]
    alternates = [
        (1, 8, 'de', 'Königsberg', '', '', '', '', '', ''),
        (3, 9, 'en', 'Constantinople', '', '', '', '1', '', ''),
        (4, 8, 'en', 'Old Port', '', '', '', '1', '', ''),
        (5, 8, 'de', 'Old Port', '', '', '', '', '', ''),
        (6, 8, 'de', 'Former Capital', '', '', '', '1', '', ''),
        (7, 8, 'en', 'Alias St. End', '', '', '', '1', '', ''),
        (8, 30, 'en', 'Shared Alias', '', '', '', '1', '', ''),
        (9, 31, 'en', 'Shared Alias', '', '', '', '', '', ''),
    ]
    alternates += [(100 + i, 100 + i, 'en', 'écho, 08', '', '', '', '', '', '') for i in range(25)]
    alternates += [(200 + i, 100 + i, 'en', 'Empty Region,', '', '', '', '', '', '') for i in range(25)]
    countries = [('US', 'United States'), ('FR', 'France'), ('CH', 'Switzerland'), ('CA', 'Canada'),
                 ('RU', 'Russia'), ('TR', 'Türkiye'), ('DE', 'Germany'), ('PT', 'Portugal'),
                 ('AU', 'Australia'), ('GB', 'United Kingdom'), ('KN', 'Saint Kitts and Nevis'),
                 ('JP', 'Japan'), ('SE', 'Sweden'), ('MN', 'Mongolia'), ('SG', 'Singapore')]
    country_text = ''.join('\t'.join([cc, cc + 'X', '1', '', name] + [''] * 14) + '\n'
                           for cc, name in countries)
    region_text = ('US.MN\tMinnesota\tMinnesota\t1\nUS.TX\tTexas\tTexas\t2\n'
                   'US.DC\tDistrict of Columbia\tDistrict of Columbia\t3\n'
                   'CA.02\tBritish Columbia\tBritish Columbia\t4\n'
                   'CA.08\tOntario\tOntario\t5\nAU.02\tNew South Wales\tNew South Wales\t6\n'
                   'GB.ENG\tEngland\tEngland\t7\nJP.34\tSaitama\tSaitama\t8\n')
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(builder, 'APP_CACHE_THRESHOLD', 5)
        path, _summary = make(root, places=places, alternates=alternates,
                              countries=country_text, admin1=region_text)
    return path


@pytest.fixture
def conn(atlas, monkeypatch):
    monkeypatch.setitem(zones.SHIPPED_DATA_SHA256, 'atlas.db', builder.digest(atlas))
    with contextlib.closing(sqlite3.connect(atlas.resolve().as_uri() + '?mode=ro', uri=True)) as connection:
        connection.execute('PRAGMA trusted_schema = OFF')
        yield connection


def details(conn, text, use_short=True):
    return zones._atlas_search_matches(conn.cursor(), text, use_short)


def ids(conn, text, use_short=True):
    return [r['geonameid'] for r in details(conn, text, use_short)]


@pytest.mark.parametrize('text,gid', [
    ('St. Paul', 1), ('St Paul', 1), ('Sankt Paul', 1), ('Saint-Paul', 1),
    ('Saint Louis', 3), ('St Gallen', 4), ('Ft. Worth', 5), ('Mt Vernon', 6),
    ('Sault Sainte Marie', 7), ('St.Paul St', 23), ('Saint Saint Ft. Mt. End', 27),
    ('Alias Saint End', 8), ('Misato, Saitama', 21), ('Frankfurt (Oder)', 20),
    ('Frankfurt (Oder), DE', 20), ('Frankfurt (Oder) (DE)', 20),
    ('Washington, D.C.', 18), ('Vancouver, B.C.', 15), ('Vancouver (BC)', 15),
    ('Sydney, NSW', 16), ('London, UK', 17), ('London, Britain', 17),
    ('London, Great Britain', 17), ('Basseterre, St. Kitts', 19),
    ('Saint Paul, Minnesota', 1), ('St. Paul, Minn.', 1), ('Saint Paul, MN (US)', 1),
    ('Saint Paul, USA', 1), ('Saint Paul (U.S.A.)', 1),
])
def test_words_and_qualifiers_reach_their_places(conn, text, gid):
    assert gid in ids(conn, text)


def test_every_qualifier_holds_and_a_country_bracket_is_only_a_country(conn):
    assert ids(conn, 'Saint Paul, MN, FR') == []
    assert ids(conn, 'Saint Paul (MN)') == []
    assert 1 not in ids(conn, 'Saint Paul (CA)')
    assert ids(conn, 'Saint Paul, MN') == ids(conn, 'Saint Paul, MN, , MN')
    assert ids(conn, 'Saint Paul,') == ids(conn, 'Saint Paul')


def test_incomplete_words_and_complete_words_stay_distinct(conn):
    assert 25 in ids(conn, 'St')
    assert 25 not in ids(conn, 'St.') and 24 not in ids(conn, 'St.')
    assert 26 not in ids(conn, 'Mt.')


def test_as_typed_takes_precedence_over_the_fold(conn):
    assert ids(conn, 'Groß') == [10]
    assert 11 not in ids(conn, 'groß')
    assert ids(conn, 'GROSSKLEIN') == [10]


def test_folding_a_literal_piece_does_not_turn_it_into_a_word_form(conn):
    assert 37 in ids(conn, 'ſaint St. Vale')
    assert 38 not in ids(conn, 'ſaint St. Vale')
    assert 37 in ids(conn, 'St. ſaint')


@pytest.mark.parametrize('text,gid', [
    ('évòra', 12), (unicodedata.normalize('NFD', 'évòra'), 12),
    ('İNANÖZ', 13), ('inanöz', 13), ('YUKARI BEĞDEŞ', 14),
])
def test_nfc_and_turkish_folding_reach_their_names(conn, text, gid):
    assert ids(conn, text) == [gid]


def test_the_builder_uses_the_app_fold_and_word_groups(conn):
    assert builder.APP_WORD_FORMS == zones.ATLAS_WORD_FORMS
    keys = [key for key, in conn.execute('SELECT key FROM atlas_keys WHERE (kinds & 1) <> 0')]
    assert keys
    for key in keys:
        assert builder.app_fold(key) == zones._atlas_fold(key)


@pytest.mark.parametrize('text,gid,historical', [
    ('Königsberg', 8, False), ('Konigsberg', 8, False), ('Constantinople', 9, True),
    ('Former Capital', 8, True), ('Old Port', 8, False),
])
def test_alternate_names_keep_only_geonames_historical_flags(conn, text, gid, historical):
    row, = details(conn, text)
    assert row['geonameid'] == gid
    assert bool(row['historic_name']) is historical
    assert row['matched'] == ('Königsberg' if text == 'Konigsberg' else text)


def test_exact_seats_population_living_places_and_ids_decide_the_order(conn):
    assert ids(conn, 'Ham')[0] == 22
    assert ids(conn, 'Seat') == [32, 33]
    assert ids(conn, 'Ruin') == [29, 28]
    assert ids(conn, 'Tie') == [30, 31]
    assert ids(conn, 'Shared Alias') == [31, 30]
    assert len(ids(conn, 'H')) == 20


def test_a_crowded_exact_name_is_reached_by_each_qualifier(conn):
    assert 34 not in ids(conn, 'Common')
    for text in ['Common, 02', 'Common, British Columbia', 'Common (CA)', 'Common, BC']:
        assert ids(conn, text) == [34]


def test_all_short_key_prefixes_equal_the_full_range_search(conn):
    prefixes = {(kind, key[:length]) for mask, key in conn.execute('SELECT kinds, key FROM atlas_keys')
                for kind in range(4) if mask & (1 << kind)
                for length in range(1, min(4, len(key)) + 1)}
    scopes = [r[0] for r in conn.execute('SELECT DISTINCT scope FROM atlas_prefix_results')]
    assert prefixes
    assert scopes
    for kind, prefix in sorted(prefixes):
        for scope in scopes:
            assert zones._atlas_key_matches(conn.cursor(), kind, prefix, scope) == \
                zones._atlas_key_matches(conn.cursor(), kind, prefix, scope, False), (kind, prefix, scope)


def test_all_typed_short_prefixes_keep_results_order_and_labels(conn, atlas, monkeypatch):
    from measure_atlas_search import labels
    monkeypatch.setitem(zones.SHIPPED_DATA_SHA256, 'atlas.db', hashlib.sha256(atlas.read_bytes()).hexdigest())
    spellings = [r[0] for r in conn.execute('SELECT name FROM places UNION SELECT name FROM names')]
    assert spellings
    for spelling in spellings:
        for length in range(1, min(4, len(spelling)) + 1):
            text = spelling[:length]
            for suffix in ['', ', US', ' (CA)', ', 02']:
                cached, full = details(conn, text + suffix), details(conn, text + suffix, False)
                assert cached == full
                assert labels(cached) == labels(full)
    assert len(zones.atlas_rows(atlas, 'H')) == 20


@pytest.mark.parametrize('text', ['%', '_', 'Flor%', 'Flor_', '\\', "Quote's", '"', 'a OR b'])
def test_punctuation_is_literal(conn, text):
    assert [r['name'] for r in details(conn, text)] == [text]


@pytest.mark.parametrize('text', ['', '   ', 'x' * 201, 'Saint\x00Paul', 'Saint\x1f0\x1f', '\ud800'])
def test_blank_excessive_and_unprinted_text_is_refused(conn, text):
    assert details(conn, text) == []


def test_a_short_text_reads_the_precomputed_table(conn):
    statements = []
    conn.set_trace_callback(statements.append)
    assert details(conn, 'H')
    conn.set_trace_callback(None)
    assert statements
    assert any('FROM atlas_prefix_results c' in sql for sql in statements)
    assert not any('WITH candidates AS' in sql for sql in statements)


def test_the_new_search_reads_only_keys_and_indexed_ranges(conn):
    calls = []
    conn.set_trace_callback(calls.append)
    for text in ['St.', 'H, Texas', 'Königsberg', 'évòra', 'Common (CA)']:
        details(conn, text)
    conn.set_trace_callback(None)
    assert calls
    for sql in dict.fromkeys(calls):
        plan = [r[3] for r in conn.execute('EXPLAIN QUERY PLAN ' + sql)]
        assert not [step for step in plan if step.startswith('SCAN ') and any(
            step.split()[1] == name for name in ['k', 'p', 'c', 'country_names', 'admin1_names'])], plan


def test_the_hash_check_is_unchanged_and_the_file_is_read_only_and_closed(atlas, monkeypatch):
    monkeypatch.setitem(zones.SHIPPED_DATA_SHA256, 'atlas.db', hashlib.sha256(atlas.read_bytes()).hexdigest())
    real = sqlite3.connect
    connections = []

    def connect(path, **kwargs):
        assert path == atlas.resolve().as_uri() + '?mode=ro' and kwargs == {'uri': True}
        c = real(path, **kwargs)
        with pytest.raises(sqlite3.OperationalError, match='readonly'):
            c.execute('CREATE TABLE forbidden (x)')
        connections.append(c)
        return c
    monkeypatch.setattr(zones.sqlite3, 'connect', connect)
    assert zones.atlas_rows(atlas, 'St. Paul')
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        connections[-1].execute('SELECT 1')


def test_the_connection_has_trusted_schema_off_and_closes_after_a_query_error(atlas, tmp_path, monkeypatch):
    path = tmp_path / 'broken.db'
    shutil.copyfile(atlas, path)
    with sqlite3.connect(path) as c:
        c.execute('DROP TABLE atlas_keys')
    monkeypatch.setitem(zones.SHIPPED_DATA_SHA256, 'atlas.db', builder.digest(path))
    states, connections = [], []
    real = sqlite3.connect

    class Connection(sqlite3.Connection):
        def cursor(self, *args, **kwargs):
            states.append(self.execute('PRAGMA trusted_schema').fetchone()[0])
            return super().cursor(*args, **kwargs)

    def connect(*args, **kwargs):
        connection = real(*args, factory=Connection, **kwargs)
        connections.append(connection)
        return connection
    monkeypatch.setattr(zones.sqlite3, 'connect', connect)
    # refused with the changed atlas's sentence once the file is open (an
    # SQLite error at the missing table before that was refused)
    with pytest.raises(zones.ShippedDataChanged, match='indexed search'):
        zones.atlas_rows(path, 'Ham')
    assert states == [0]
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        connections[0].execute('SELECT 1')


def test_the_actual_app_labels_and_first_option_keep_their_contract(conn, atlas, monkeypatch):
    from engine import degrees_text
    source = (Path(builder.__file__).parent / 'app.py').read_text()
    tree = ast.parse(source)
    namespace = {'Path': Path, '__file__': str(atlas.parent / 'app.py'), 'atlas_rows': zones.atlas_rows,
                 'degrees_text': degrees_text, 'ShippedDataChanged': zones.ShippedDataChanged}
    nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name == '_atlas_matches') or
             (isinstance(n, ast.Assign) and any(getattr(t, 'id', '').startswith('ATLAS_') for t in n.targets))]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<fixture>', 'exec'), namespace)
    options, why = namespace['_atlas_matches']('Common')
    assert why is None and len(options) == 20
    first = details(conn, 'Common')[0]
    assert next(iter(options.values())) == (first['lat'], first['lon'])
    assert list(options)[0] == 'Common, TX (US)'
    assert options
    assert all(label.startswith('Common, TX (US) [') for label in list(options)[1:])
    qualified, why = namespace['_atlas_matches']('Common, TX (US)')
    assert why is None and len(qualified) == 25
    assert set(qualified.values()) == {(r['lat'], r['lon']) for r in details(conn, 'Common, TX (US)')}
    assert list(namespace['_atlas_matches']('Singapore')[0]) == ['Singapore (SG)']
    close, _why = namespace['_atlas_matches']('Close Twins')
    assert len(close) == 4
    assert set(close.values()) == {(r['lat'], r['lon']) for r in details(conn, 'Close Twins')}
    assert list(close)[1].endswith('[10.0000, 20.0000]')
    assert list(close)[2].endswith('[10.00003, 20.00003]')
    assert list(close)[3].endswith('[10.000034, 20.000034]')


def test_the_reachability_measurement_equals_exhaustive_fixture_lookups(conn):
    from measure_atlas_search import reachability
    from engine import parse_lat_lon
    measured = reachability(conn)
    lost = [0] * 6
    rows = conn.execute('SELECT p.geonameid, p.name, p.admin1_code, a.name, p.country_code FROM places p '
                        'JOIN admin1_names a ON a.country = p.country_code AND a.admin1 = p.admin1_code').fetchall()
    for gid, name, region, region_name, country in rows:
        forms = [name, name + ', ' + region, name + ', ' + region_name if region_name else None,
                 name + ' (' + country + ')', name + ', ' + region + ' (' + country + ')',
                 name + ', ' + region_name + ' (' + country + ')' if region_name else None]
        for column, text in enumerate(forms):
            lost[column] += (text is None or len(text) > 200 or parse_lat_lon(text) is not None
                             or gid not in ids(conn, text))
    assert list(measured['unreachable'].values()) == lost


def test_the_latency_sample_really_misses_as_typed_and_matches_folded(conn):
    from measure_atlas_search import folded_samples
    for length in [1, 2, 3, 4, 5, 8]:
        texts, _attempts = folded_samples(conn, length, 5, random.Random(1))
        assert len(texts) == 5
        for text in texts:
            assert len(text) == length
            assert not zones._atlas_key_matches(conn.cursor(), 0, text.translate(zones.ATLAS_ASCII_LOWER))
            assert details(conn, text)


def test_the_measurement_counts_record_overwrites_and_distinct_point_losses(conn):
    from measure_atlas_search import presentation_losses, presented
    assert {r['geonameid'] for r in presented(details(conn, 'Close Twins')).values()} == {43, 44, 45, 49}
    report = presentation_losses(conn)
    assert list(report['additional_record_id_losses'].values()) == [1, 1, 1, 1]
    assert list(report['additional_distinct_point_losses'].values()) == [0, 0, 0, 0]


def test_the_coordinate_box_still_reads_a_pair_before_searching():
    source = (Path(builder.__file__).parent / 'app.py').read_text()
    tree = ast.parse(source)
    helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_place_the_box_holds')
    namespace = {'PLACE_TEXT_MAX_CHARS': 200, 'parse_lat_lon': lambda t: (44.9537, -93.09),
                 '_atlas_matches': lambda t: pytest.fail('A coordinate pair reached the atlas.')}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), '<fixture>', 'exec'), namespace)
    assert namespace['_place_the_box_holds']('44.9537, -93.09') == (44.9537, -93.09)


def test_qualified_complete_names_return_every_exact_match(conn):
    expected = set(range(200, 225))
    for text in ['Common, TX', 'Common, Texas', 'Common, TX (US)', 'Common, Texas (US)']:
        result = details(conn, text)
        assert {r['geonameid'] for r in result} == expected
        assert result
        assert all(r['exact'] for r in result)
        assert result == details(conn, text, False)
    assert len(ids(conn, 'Common')) == 20
    assert len(ids(conn, 'Comm, TX (US)')) == 20


def test_country_and_region_together_resolve_a_shared_code(conn):
    assert 34 in ids(conn, 'Common, 02 (CA)')
    assert 34 not in ids(conn, 'Common, 02 (US)')
    assert 1 in ids(conn, 'Saint Paul, Minnesota (US)')
    assert 1 not in ids(conn, 'Saint Paul, Minnesota (CA)')


def test_dropped_rows_skip_only_the_unprinted_checks():
    raw = place(12564634, 'Invalid\x81 Name').encode()
    zones_available = builder.pinned_zone_names()
    with pytest.raises(builder.AtlasBuildError, match=r'U\+0081'):
        builder.place_row(1, raw, zones_available)
    assert builder.place_row(1, raw, zones_available, dropped=builder.DROPPED)[0] == 12564634
    for column, value in [(4, '91'), (8, 'ZZZ'), (14, '-1'), (17, 'Missing/Zone'), (18, 'bad')]:
        columns = raw.decode().split('\t')
        columns[column] = value
        with pytest.raises(builder.AtlasBuildError):
            builder.place_row(1, '\t'.join(columns).encode(), zones_available, dropped=builder.DROPPED)


def test_only_the_app_search_is_built_and_small_ranges_are_live(conn):
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert not tables & {'search_keys', 'short_prefix_results'}
    assert conn.execute('SELECT COUNT(*) FROM atlas_prefix_results').fetchone()[0] > 0
    statements = []
    conn.set_trace_callback(statements.append)
    assert ids(conn, 'Ti')
    conn.set_trace_callback(None)
    assert any('INDEXED BY atlas_key_range' in sql for sql in statements)


def test_the_last_unicode_codepoint_is_a_literal_prefix():
    assert zones._atlas_key_upper(chr(0x10ffff)) is None
    assert zones._atlas_key_upper('a' + chr(0x10ffff)) == 'b'
    assert zones._atlas_key_upper(chr(0xd7ff)) == chr(0xe000)


def test_equal_typed_and_folded_keys_share_storage(conn):
    mask, = conn.execute("SELECT kinds FROM atlas_keys WHERE geonameid = 1 AND key = 'saint paul' AND matched IS NULL").fetchone()
    assert mask & 1 and mask & 2
    assert ids(conn, 'Saint Paul') == ids(conn, 'SAINT PAUL')


def test_builder_checks_use_the_app_search(conn, atlas):
    assert builder.matches(conn, 'Common, TX (US)') == builder.matches_full(conn, 'Common, TX (US)')
    assert len(builder.matches(conn, 'Common, TX (US)')) == 25
    agreed = builder.agreement(atlas, samples=5)['agreement']
    assert agreed
    assert all(r['disagreements'] == 0 for r in agreed.values())
    timed = builder.benchmark(atlas, samples=5)['queries']
    assert timed
    assert all(r['samples'] == 5 for r in timed.values())


def test_shared_region_equalities_match_separate_scope_ranges(conn):
    scopes = ['CA\x1f02', 'AU\x1f02', 'US\x1fMN', 'US\x1fTX']
    keys = [(kind, key) for mask, key in conn.execute('SELECT kinds, key FROM atlas_keys')
            for kind in range(4) if mask & (1 << kind)]
    assert keys
    for kind, key in set(keys):
        separate = [row for scope in scopes for row in zones._atlas_key_matches(
            conn.cursor(), kind, key, scope, False, True)]
        separate.sort(key=zones._atlas_search_rank)
        assert zones._atlas_scoped_range_matches(conn.cursor(), kind, key, scopes, True) == separate


def test_a_dropped_country_code_still_needs_a_country_name(tmp_path):
    with pytest.raises(builder.AtlasBuildError, match='countryInfo.txt gives no name for ZZ'):
        make(tmp_path, places=[place(1, 'Valid'), place(12564634, 'Invalid\x81', country='ZZ')], alternates=[])


def test_a_typed_miss_seeks_only_its_own_kind_ranges(conn):
    statements = []
    conn.set_trace_callback(statements.append)
    assert ids(conn, 'évòra') == [12]
    conn.set_trace_callback(None)
    plans = [r[3] for sql in statements if 'WITH candidates AS' in sql
             for r in conn.execute('EXPLAIN QUERY PLAN ' + sql)]
    assert any('atlas_key_range (kinds=? AND key>?' in p for p in plans)


def test_a_literal_complete_name_keeps_its_exact_hit_beside_a_qualified_reading(conn):
    assert set(ids(conn, 'Misato, Saitama')) == {21, 50}
    rows = details(conn, 'Misato, Saitama')
    assert rows
    assert all(r['exact'] for r in rows)


def test_a_bare_word_before_a_comma_stays_literal_beside_a_whole_word(conn):
    for suffix in ['', ', MN', ' (US)', ', MN (US)']:
        assert ids(conn, 'Saint , Saint Vale' + suffix) == [51]
    assert ids(conn, chr(0xd7ff)) == [53]


def test_a_country_qualifier_preserves_a_literal_trailing_comma(conn):
    assert set(ids(conn, 'Trailing, (US)')) == {54, 55}
    assert 54 in ids(conn, 'Trailing,, MN (US)')


@pytest.mark.parametrize('action', ['--benchmark', '--agreement'])
def test_isolated_builder_commands_load_the_app_search(atlas, action):
    result = subprocess.run([sys.executable, '-I', builder.__file__, action, str(atlas)],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('version,new', [
    ('20', False), ('2.0', False), (' 2', False), ('2 ', False), ('3', False), (None, False),
    ('2', True), (2, True)])
def test_only_the_exact_search_version_two_takes_the_new_search(atlas, tmp_path, monkeypatch, version, new):
    """The stored text must be exactly '2'; a number written into the
    builder's text column is stored as that text, so it is '2' too. Any
    other file is refused with its sentence and never searched."""
    path = tmp_path / 'atlas.db'
    shutil.copyfile(atlas, path)
    with contextlib.closing(sqlite3.connect(path)) as c, c:
        c.execute("DELETE FROM metadata WHERE key = 'app_search_version'")
        if version is not None:
            c.execute("INSERT INTO metadata VALUES ('app_search_version', ?)", (version,))
    with contextlib.closing(sqlite3.connect(path)) as c:
        stored = c.execute("SELECT value, typeof(value) FROM metadata WHERE key = 'app_search_version'").fetchall()
    assert stored == ([] if version is None else [(str(version), 'text')])
    monkeypatch.setitem(zones.SHIPPED_DATA_SHA256, 'atlas.db', builder.digest(path))
    calls = []
    real = zones._atlas_search_matches

    def spy(*args, **kwargs):
        calls.append(args[1])
        return real(*args, **kwargs)
    monkeypatch.setattr(zones, '_atlas_search_matches', spy)
    if new:
        assert zones.atlas_rows(path, 'Saint Paul')
    else:
        with pytest.raises(zones.ShippedDataChanged) as refused:
            zones.atlas_rows(path, 'Saint Paul')
        assert str(refused.value) == 'atlas.db does not name the indexed search, so it is not read'
    assert calls == (['Saint Paul'] if new else [])


def test_an_untyped_integer_two_is_not_the_search_version(atlas, tmp_path, monkeypatch):
    """A metadata column without the text type keeps a number as a number,
    and the number 2 is not the stored text '2': such a file is refused
    with its sentence, and the indexed search never reads it."""
    path = tmp_path / 'atlas.db'
    shutil.copyfile(atlas, path)
    with contextlib.closing(sqlite3.connect(path)) as c, c:
        kept = c.execute("SELECT key, value FROM metadata WHERE key <> 'app_search_version'").fetchall()
        c.execute('DROP TABLE metadata')
        c.execute('CREATE TABLE metadata (key TEXT PRIMARY KEY, value)')
        c.executemany('INSERT INTO metadata VALUES (?, ?)', kept + [('app_search_version', 2)])
    with contextlib.closing(sqlite3.connect(path)) as c:
        assert c.execute("SELECT value, typeof(value) FROM metadata "
                         "WHERE key = 'app_search_version'").fetchall() == [(2, 'integer')]
    monkeypatch.setitem(zones.SHIPPED_DATA_SHA256, 'atlas.db', builder.digest(path))

    def refuse(*args, **kwargs):
        raise AssertionError('the indexed search read a file that is not version 2')
    monkeypatch.setattr(zones, '_atlas_search_matches', refuse)
    with pytest.raises(zones.ShippedDataChanged) as refused:
        zones.atlas_rows(path, 'Saint Paul')
    assert str(refused.value) == 'atlas.db does not name the indexed search, so it is not read'
