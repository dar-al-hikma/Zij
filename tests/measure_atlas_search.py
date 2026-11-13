"""Measure the app search without changing the shipped atlas or its digest.

Run with the app's Python interpreter. The database is opened read-only;
only the measurement process uses its digest as the expected digest.
The output identifies the input manifest and the measurement conditions.
"""
import argparse
import ast
import contextlib
import functools
import hashlib
import json
import math
import mmap
import ctypes
import shutil
import subprocess
import tempfile
from array import array
from bisect import bisect_left
import os
from pathlib import Path
import random
import sqlite3
import statistics
import sys
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_atlas as builder
import time_zones as zones


def open_atlas(path):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    conn.execute('PRAGMA trusted_schema = OFF')
    conn.execute('PRAGMA temp_store = FILE')
    return conn


def main_key(text):
    """The key of a main name as typed, without expanding incomplete words."""
    text = text.strip()
    if not builder.APP_WORD_PATTERN.search(text.translate(zones.ATLAS_ASCII_LOWER)):
        return 0, text.translate(zones.ATLAS_ASCII_LOWER)
    words = zones._atlas_words(text)
    return (2 if any(isinstance(w, int) for w in words) else 0,
            ''.join('\x1f' + str(w) + '\x1f' if isinstance(w, int)
                    else w.translate(zones.ATLAS_ASCII_LOWER) for w in words))


class SortedIds:
    """Compact exact membership for the exhaustive query-result cache."""
    __slots__ = ('values',)

    def __init__(self, values=()):
        self.values = array('Q', sorted(values))

    def __len__(self):
        return len(self.values)

    def __contains__(self, value):
        at = bisect_left(self.values, value)
        return at < len(self.values) and self.values[at] == value


def reachability(conn, samples=1000):
    """Count unreachable main names, checking every potentially crowded case.

    An exact main name ranks ahead of all longer names. If at most twenty
    places have that exact key, its place is reachable unless another look
    can contribute a better exact match, the qualifier rejects its own
    region, or its text is refused. Those exceptions are enumerated below;
    each is evaluated by the real search. No candidate cap is used.
    """
    started = time.perf_counter()
    from engine import parse_lat_lon
    crowded = set(conn.execute("""
      SELECT v.kind, k.key FROM atlas_keys k CROSS JOIN (SELECT 0 AS kind UNION ALL SELECT 2) v
      WHERE (k.kinds & (1 << v.kind)) <> 0 GROUP BY v.kind, k.key
      HAVING COUNT(DISTINCT geonameid) > 20
    """))
    literal_heads = set()
    for key, in conn.execute("SELECT key FROM atlas_keys WHERE (kinds & 1) <> 0 "
                             "AND (instr(key, ',') > 0 OR instr(key, ' (') > 0)"):
        for delimiter in [',', ' (']:
            at = key.find(delimiter)
            while at >= 0:
                for kind, head in builder.app_keys(key[:at].strip()):
                    literal_heads.add((kind - kind % 2, head))
                at = key.find(delimiter, at + 1)
    regions = {(c, a): n for c, a, n in conn.execute('SELECT country, admin1, name FROM admin1_names')}
    bad_regions = set()
    for (country, admin1), name in regions.items():
        for qualifier in [admin1, name]:
            if not qualifier:
                continue
            if any(unicodedata.category(ch) in {'Cc', 'Cf', 'Zl', 'Zp', 'Cs'} for ch in qualifier):
                bad_regions.add((country, admin1))
            looks = zones._atlas_looks('Placeholder, ' + qualifier)
            for words, qualifiers in looks:
                if words != ['Placeholder']:
                    continue
                holding = zones._atlas_holding(conn.cursor(), qualifiers)
                scopes = zones._atlas_search_scopes(holding, qualifiers)
                if not any(s == '' or s == country or s == country + '\x1f' + admin1 for s in scopes):
                    bad_regions.add((country, admin1))

    suspects, certified_sample = [], []
    rng, total, certified, missing_region_names = random.Random(1), 0, 0, 0
    missing_region_code = missing_names_with_code = 0
    source = conn.execute('SELECT geonameid, name, admin1_code, country_code FROM places ORDER BY geonameid')
    for gid, name, region, country in source:
        total += 1
        row = (gid, name, region, country)
        missing_region_code += not region
        if not regions[country, region]:
            missing_region_names += 1
            missing_names_with_code += bool(region)
        key = main_key(name)
        longest_suffix = max(5, 7 + len(region), 7 + len(regions[country, region] or ''))
        numeric_name = all(ch.isdecimal() or ch in '+-.,' or ch.isspace() for ch in name)
        unusual = (key in crowded or key in literal_heads or main_key(zones._atlas_fold(name)) in literal_heads
                   or ',' in name or '(' in name or (country, region) in bad_regions
                   or numeric_name or not name or name != name.strip() or len(name) + longest_suffix > 200)
        if unusual:
            suspects.append(row)
        else:
            certified += 1
            if len(certified_sample) < samples:
                certified_sample.append(row)
            else:
                at = rng.randrange(certified)
                if at < samples:
                    certified_sample[at] = row
    print(f'Reachability: {total} places; {len(suspects)} checked by search; {certified} certified.', flush=True)

    @functools.lru_cache(maxsize=200000)
    def found(text):
        if len(text) > 200 or parse_lat_lon(text) is not None:
            return SortedIds()
        return SortedIds(r['geonameid'] for r in zones._atlas_search_matches(conn.cursor(), text))

    def forms(row):
        gid, name, region, country = row
        region_name = regions[country, region]
        return [name, name + ', ' + region,
                name + ', ' + region_name if region_name else None, name + ' (' + country + ')',
                name + ', ' + region + ' (' + country + ')',
                name + ', ' + region_name + ' (' + country + ')' if region_name else None]

    from collections import Counter
    form_names = ['main_name', 'region_code', 'region_name', 'country_bracket',
                  'region_code_country', 'region_name_country']
    lost, examples = [0] * 6, [[] for _ in range(6)]
    reasons, lengths = [Counter() for _ in range(6)], [Counter() for _ in range(6)]
    maxima = [{} for _ in range(6)]

    def observe(row):
        for column, text in enumerate(forms(row)):
            result = found(text) if text is not None else frozenset()
            size = len(result)
            lengths[column][size] += 1
            if size > maxima[column].get('length', -1):
                maxima[column] = {'length': size, 'text': text, 'name': row[1], 'geonameid': row[0],
                                  'country': row[3], 'region': row[2]}
            if row[0] not in result:
                lost[column] += 1
                reason = ('missing_region_name' if text is None else
                          'empty_main_name' if not row[1] else
                          'length_bound' if len(text) > 200 else
                          'coordinate_pair' if parse_lat_lon(text) is not None else
                          'surrounding_whitespace' if row[1] != row[1].strip() else
                          'no_region_code' if column == 1 and not row[2] else
                          'twenty_option_limit' if column == 0 else 'qualifier_interpretation')
                reasons[column][reason] += 1
                if len(examples[column]) < 30:
                    examples[column].append({'geonameid': row[0], 'text': text, 'reason': reason})
    for at, row in enumerate(suspects):
        observe(row)
        if at and at % 10000 == 0:
            print(f'Checked {at} reachability exceptions.', flush=True)
    # Every certified name has at most twenty exact matches globally, and
    # no other look can contribute an exact match. Its list has at most
    # twenty rows in every scope. The upper tail above twenty therefore
    # comes entirely from the exhaustive exception search, not a sample.
    if total < 10000:
        suspect_ids = {r[0] for r in suspects}
        for row in conn.execute('SELECT geonameid, name, admin1_code, country_code FROM places ORDER BY geonameid').fetchall():
            if row[0] not in suspect_ids:
                observe(row)
        unknown_small = 0
    else:
        unknown_small = certified
        lost[2] += missing_region_names - sum(1 for row in suspects if not regions[row[3], row[2]])
        lost[5] += missing_region_names - sum(1 for row in suspects if not regions[row[3], row[2]])
        for column in [2, 5]:
            reasons[column]['missing_region_name'] = missing_region_names
    for row in certified_sample:
        for column, text in enumerate(forms(row)):
            if text is not None and row[0] not in found(text):
                raise AssertionError(f'A certified place was not reached: {row!r}, {text!r}')
    list_report = {}
    for column, name in enumerate(form_names):
        remaining = total - math.ceil(.999 * total) + 1
        percentile = None
        for size, count in sorted(lengths[column].items(), reverse=True):
            if unknown_small and size < 20:
                break
            remaining -= count
            if remaining <= 0:
                percentile = size
                break
        if percentile is None and unknown_small:
            raise AssertionError('The list percentile needs exact counts below twenty; run that tail explicitly.')
        list_report[name] = {'maximum': maxima[column], 'p99_9': percentile,
                             'known_length_histogram': dict(sorted(lengths[column].items())),
                             'unqueried_certified_lengths_at_most_twenty': unknown_small}
    return {'places': total, 'unreachable': dict(zip(form_names, lost)),
            'unreachable_by_kind': dict(zip(form_names, [dict(r) for r in reasons])),
            'missing_region_names': missing_region_names, 'missing_region_codes': missing_region_code,
            'missing_region_names_with_code': missing_names_with_code, 'examples': dict(zip(form_names, examples)),
            'list_lengths': list_report,
            'percentile_population': 'One generated input per place, repeated texts weighted by their places; unavailable forms count zero.',
            'certified_places': certified, 'exceptions_checked_by_search': len(suspects),
            'certified_sample_checked': len(certified_sample), 'crowded_exact_keys': len(crowded),
            'literal_heads': len(literal_heads), 'query_cache': str(found.cache_info()),
            'seconds': time.perf_counter() - started}


def prefix_samples(conn, length, count, rng):
    top = conn.execute('SELECT MAX(id) FROM atlas_keys').fetchone()[0]
    rows = []
    while len(rows) < count:
        row = conn.execute('SELECT s.key, p.admin1_code, p.country_code FROM atlas_keys s '
                           'JOIN places p ON p.geonameid = s.geonameid WHERE s.id = ? AND (s.kinds & 1) <> 0',
                           (rng.randint(1, top),)).fetchone()
        if row and len(row[0]) >= length and row[0][:length].strip() == row[0][:length]:
            rows.append((row[0][:length], row[1], row[2]))
    return rows


def folded_samples(conn, length, count, rng):
    top = conn.execute('SELECT MAX(id) FROM atlas_keys').fetchone()[0]
    rows, attempts = [], 0
    while len(rows) < count:
        attempts += 1
        if attempts > count * 10000:
            raise ValueError('Too few texts that miss as typed and match folded.')
        row = conn.execute('SELECT key FROM atlas_keys WHERE id = ? AND (kinds & 1) <> 0',
                           (rng.randint(1, top),)).fetchone()
        if not row or len(row[0]) < length:
            continue
        text = unicodedata.normalize('NFD', row[0][:length].swapcase())
        if text.strip() != text or text.isascii() or zones._atlas_looks(text) is not None:
            continue
        # Length is the requested number of typed codepoints, after NFD.
        if len(text) != length:
            text = row[0][:length].swapcase()
        if len(text) != length or zones._atlas_looks(text) is not None:
            continue
        key = text.translate(zones.ATLAS_ASCII_LOWER)
        if zones._atlas_key_matches(conn.cursor(), 0, key):
            continue
        if zones._atlas_search_matches(conn.cursor(), text):
            rows.append(text)
    return rows, attempts


def percentiles(timings):
    ordered = sorted(timings)
    return {'samples': len(ordered), 'p50_ms': statistics.median(ordered),
            'p95_ms': ordered[math.ceil(.95 * len(ordered)) - 1], 'max_ms': ordered[-1]}


def benchmark(path, conn, samples):
    rng, report = random.Random(1), {}
    zones.atlas_rows(path, 'Kaliningrad')
    region_names = {(c, a): n for c, a, n in conn.execute('SELECT country, admin1, name FROM admin1_names')}
    for length in [1, 2, 3, 4, 5, 8]:
        keys = prefix_samples(conn, length, samples, rng)
        named = [(t, region_names[c, a]) for t, a, c in keys if region_names[c, a]]
        while len(named) < samples:
            named += [(t, region_names[c, a]) for t, a, c in prefix_samples(conn, length, samples - len(named), rng)
                      if region_names[c, a]]
        folded, attempts = folded_samples(conn, length, samples, rng)
        groups = {'plain': [t for t, a, c in keys],
                  'region_code': [t + ', ' + a for t, a, c in keys],
                  'region_name': [t + ', ' + n for t, n in named],
                  'country_bracket': [t + ' (' + c + ')' for t, a, c in keys],
                  'folded_miss': folded}
        report[str(length)] = {}
        for group, texts in groups.items():
            timings = []
            for text in texts:
                start = time.perf_counter()
                zones.atlas_rows(path, text)
                timings.append(1000 * (time.perf_counter() - start))
            report[str(length)][group] = percentiles(timings)
        report[str(length)]['folded_sampling_attempts'] = attempts
        print('Latency', length, report[str(length)], flush=True)
    return report


def presented(rows):
    """The rows retained by the app's existing label dictionary."""
    from engine import degrees_text
    options = {}
    for r in rows:
        region = (r['admin1'] or '').strip()
        text = (f"{r['name']}, {region} ({r['country']})" if region
                else f"{r['name']} ({r['country']})")
        if text in options:
            base, places = text, 4
            while True:
                text = f"{base} [{degrees_text(r['lat'], places)}, {degrees_text(r['lon'], places)}]"
                if text not in options or (options[text]['lat'], options[text]['lon']) == (r['lat'], r['lon']):
                    break
                places += 1
        options[text] = r
    return options


def labels(rows):
    """The app's labels, the coordinate suffix grown until each is unique."""
    return [(text, (r['lat'], r['lon'])) for text, r in presented(rows).items()]


def presentation_losses(conn):
    """Count additional records and distinct points lost to label collisions.

    A base label ends in its country bracket; a suffixed label ends in a
    coordinate bracket. Overwrites therefore require the same base label
    and the same printed coordinate pair. Candidate buckets cover every
    such collision, and the real search determines which rows are offered.
    """
    from engine import degrees_text, parse_lat_lon
    started = time.perf_counter()

    def base(name, region, country):
        region = (region or '').strip()
        return f'{name}, {region} ({country})' if region else f'{name} ({country})'

    conn.create_function('atlas_label', 3, base, deterministic=True)
    conn.create_function('atlas_degrees', 1, lambda v: degrees_text(v, 4), deterministic=True)
    conn.execute("""CREATE TEMP TABLE label_candidates AS
      SELECT DISTINCT label FROM (
        SELECT atlas_label(name, admin1_code, country_code) AS label,
               atlas_degrees(lat) AS latitude, atlas_degrees(lon) AS longitude
        FROM places GROUP BY label, latitude, longitude HAVING COUNT(*) > 1)
    """)
    conn.execute('CREATE INDEX label_candidates_key ON label_candidates(label)')
    candidates = conn.execute("""SELECT p.geonameid, p.name, p.admin1_code, a.name, p.country_code, p.lat, p.lon
      FROM places p JOIN admin1_names a ON a.country = p.country_code AND a.admin1 = p.admin1_code
      WHERE atlas_label(p.name, p.admin1_code, p.country_code) IN (SELECT label FROM label_candidates)
      ORDER BY p.geonameid""").fetchall()
    print('Presentation candidate places:', len(candidates), flush=True)

    @functools.lru_cache(maxsize=4096)
    def found(text):
        if len(text) > 200 or parse_lat_lon(text) is not None:
            return frozenset(), frozenset(), frozenset()
        rows = zones._atlas_search_matches(conn.cursor(), text)
        retained = list(presented(rows).values())
        return (frozenset(r['geonameid'] for r in rows), frozenset(r['geonameid'] for r in retained),
                frozenset((r['lat'], r['lon']) for r in retained))

    record_losses, point_losses = [0] * 4, [0] * 4
    examples = [[] for _ in range(4)]
    for gid, name, region, region_name, country, lat, lon in candidates:
        forms = [name, name + ', ' + region, name + ', ' + region_name if region_name else None,
                 name + ' (' + country + ')']
        for column, text in enumerate(forms):
            if text is None:
                continue
            rows, retained, points = found(text)
            if gid in rows and gid not in retained:
                record_losses[column] += 1
                point_losses[column] += (lat, lon) not in points
                if len(examples[column]) < 20:
                    examples[column].append({'geonameid': gid, 'text': text,
                                             'distinct_point_lost': (lat, lon) not in points})
    names = ['main_name', 'region_code', 'region_name', 'country_bracket']
    return {'candidate_places': len(candidates), 'additional_record_id_losses': dict(zip(names, record_losses)),
            'additional_distinct_point_losses': dict(zip(names, point_losses)), 'examples': examples,
            'seconds': time.perf_counter() - started}


def agreement(conn, samples):
    rng, result = random.Random(1), {}
    for length in [1, 2, 3, 4]:
        references, disagreements, label_disagreements = {}, 0, 0
        for text, _a, _c in prefix_samples(conn, length, samples, rng):
            if text not in references:
                references[text] = zones._atlas_search_matches(conn.cursor(), text, False)
            cached = zones._atlas_search_matches(conn.cursor(), text)
            disagreements += cached != references[text]
            label_disagreements += labels(cached) != labels(references[text])
        result[str(length)] = {'samples': samples, 'unique_references': len(references),
                               'disagreements': disagreements, 'label_disagreements': label_disagreements}
        print('Agreement', length, result[str(length)], flush=True)
    return result


def actual_app_lookup(path):
    """Load the real label function against a hard link to the measured file."""
    from engine import degrees_text
    folder = path.parent / (path.stem + '_app')
    folder.mkdir(exist_ok=True)
    linked = folder / 'atlas.db'
    if not linked.exists():
        os.link(path, linked)
    if not os.path.samefile(path, linked):
        raise ValueError('The app fixture points at a different atlas.')
    tree = ast.parse((ROOT / 'app.py').read_text())
    nodes = [n for n in tree.body if (isinstance(n, ast.FunctionDef) and n.name == '_atlas_matches') or
             (isinstance(n, ast.Assign) and any(getattr(t, 'id', '').startswith('ATLAS_') for t in n.targets))]
    namespace = {'Path': Path, '__file__': str(folder / 'app.py'), 'atlas_rows': zones.atlas_rows,
                 'degrees_text': degrees_text, 'ShippedDataChanged': zones.ShippedDataChanged}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<measured app>', 'exec'), namespace)
    return namespace['_atlas_matches']


def crowded_exact_lookups(path, conn):
    """Time the thousand broadest qualified equality keys, including output.

    Country and region groups of the two typed key kinds are counted in
    full. Word markers are rendered as whole dotted words so the public
    app path reads them in the same key kind. Duplicate input texts are
    measured once; invalid input texts are listed separately.
    """
    candidates = []
    for scope in ['country', "country || char(31) || region"]:
        candidates += conn.execute('SELECT v.kind, k.key, ' + scope + ' AS scope, '
            'COUNT(DISTINCT k.geonameid) AS places FROM atlas_keys k CROSS JOIN (SELECT 0 AS kind UNION ALL SELECT 2) v WHERE (k.kinds & (1 << v.kind)) <> 0 '
            'GROUP BY scope, v.kind, k.key HAVING places > 20 ORDER BY places DESC, kind, key, scope LIMIT 10000').fetchall()
    candidates.sort(key=lambda r: (-r[3], r[0], r[1], r[2]))
    result, rejected, seen = [], [], set()
    prefix_only_keys = 0
    zones.atlas_rows(path, 'Kaliningrad')
    app_lookup = actual_app_lookup(path)
    app_lookup('Kaliningrad')
    zones.atlas_rows(path, 'Kaliningrad')
    for kind, key, scope, count in candidates:
        text = key
        for group, forms in enumerate(zones.ATLAS_WORD_FORMS):
            text = text.replace('\x1f' + str(group) + '\x1f', min(forms, key=len) + '. ')
        text = text.rstrip()
        if main_key(text) != (kind, key):
            prefix_only_keys += 1
            continue
        country, separator, region = scope.partition('\x1f')
        text += (', ' + region if separator else '') + ' (' + country + ')'
        if text in seen:
            continue
        seen.add(text)
        if len(text) > 200:
            rejected.append({'text': text, 'candidate_places': count, 'reason': 'length_bound'})
            continue
        start = time.perf_counter()
        rows = zones.atlas_rows(path, text)
        elapsed = 1000 * (time.perf_counter() - start)
        start = time.perf_counter()
        options, why = app_lookup(text)
        app_ms = 1000 * (time.perf_counter() - start)
        result.append({'kind': kind, 'key': key, 'scope': scope, 'text': text,
                       'indexed_exact_places': count, 'returned_places': len(rows), 'ms': elapsed,
                       'app_ms_including_labels': app_ms, 'offered_labels': len(options or {}), 'why': why})
        if len(result) == 1000:
            break
    return {'queries': result, 'rejected': rejected, 'prefix_only_keys_omitted': prefix_only_keys,
            'latency': percentiles([r['ms'] for r in result]),
            'app_latency_including_labels': percentiles([r['app_ms_including_labels'] for r in result]),
            'domain': 'The largest country and region equality groups of complete typed app keys, including alternate names; distinct rendered inputs. Prefix-only keys are excluded.'}


def query_plans(conn):
    queries = ["SELECT value FROM metadata WHERE key = 'app_search_version'",
               "SELECT country, name FROM country_names WHERE country > '' ORDER BY country",
               'SELECT country, admin1, name, ascii_name FROM admin1_names '
               "WHERE country > '' ORDER BY country, admin1"]
    statements = []
    conn.set_trace_callback(statements.append)
    for text in ['St.', 's, Minnesota', 'Konigsberg', 'London, 01', 'İnanöz', 'ſaint St. Vale', 'Kaliningrad, 23 (RU)', 'Königsberg (RU)', 'xy, 01',
                 'ſaint St. Vale, MN (US)', 'Saint , St. Vale, MN (US)',
                 chr(0x10ffff), chr(0x10ffff) + ', MN (US)']:
        zones._atlas_search_matches(conn.cursor(), text)
        zones._atlas_search_matches(conn.cursor(), text, False)
    conn.set_trace_callback(None)
    queries += statements
    return [{'sql': sql, 'plan': [r[3] for r in conn.execute('EXPLAIN QUERY PLAN ' + sql)]}
            for sql in dict.fromkeys(queries)]


def io_reads():
    path = Path('/proc/self/io')
    if not path.exists():
        return None
    return int(dict(line.split(':', 1) for line in path.read_text().splitlines())['read_bytes'])


def resident_pages(path):
    """Observe file-cache residency without reading the mapped file."""
    if not sys.platform.startswith('linux'):
        return None
    pages = math.ceil(path.stat().st_size / mmap.PAGESIZE)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        vector = (ctypes.c_ubyte * pages)()
        with path.open('rb') as file, mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_COPY) as mapped:
            view = ctypes.c_char.from_buffer(mapped)
            address = ctypes.addressof(view)
            del view
            result = libc.mincore(ctypes.c_void_p(address), ctypes.c_size_t(len(mapped)), vector)
            if result:
                return None
            return {'resident': sum(value & 1 for value in vector), 'pages': pages}
    except (AttributeError, OSError, ValueError):
        return None


def first_lookups(path):
    """Time the unchanged check on a byte-identical fresh inode, then warm.

    The original file supplies the expected hash. The timed integrity
    check verifies the copy itself. Copy/setup time is excluded. File
    residency and physical reads disclose the actual cache state.
    """
    report = {}
    with tempfile.TemporaryDirectory(prefix='atlas-cache-') as folder:
        copied = Path(folder) / 'atlas.db'
        try:
            result = subprocess.run(['cp', '--reflink=always', '--', str(path), str(copied)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            reflink = result.returncode == 0
        except FileNotFoundError:
            reflink = False
        if not reflink:
            shutil.copyfile(path, copied)
        if copied.stat().st_size != path.stat().st_size:
            raise ValueError('The cache fixture has a different size.')
        for mode in ['cold_hint', 'warm']:
            if mode == 'cold_hint' and hasattr(os, 'posix_fadvise'):
                with copied.open('rb') as file:
                    os.fsync(file.fileno())
                    os.posix_fadvise(file.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)
            residency = resident_pages(copied)
            zones._ATLAS_SEEN.clear()
            before = io_reads()
            start = time.perf_counter()
            rows = zones.atlas_rows(copied, 'Kaliningrad')
            seconds = time.perf_counter() - start
            after = io_reads()
            report[mode] = {'seconds_including_integrity_check': seconds, 'results': len(rows),
                            'storage_read_bytes': after - before if before is not None else None,
                            'residency_before': residency,
                            'copy_method': 'reflink' if reflink else 'copyfile',
                            'byte_identity_verified_by_timed_integrity_check': True}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=1000)
    parser.add_argument('--scope', default='Supplied atlas; see metadata for provenance.')
    parser.add_argument('--only', choices=['latency', 'agreement', 'reachability', 'presentation', 'plans', 'first', 'exact'])
    args = parser.parse_args()
    path = args.database.resolve()
    actual_digest = builder.digest(path)
    zones.SHIPPED_DATA_SHA256['atlas.db'] = actual_digest
    with contextlib.closing(open_atlas(path)) as connection:
        metadata = dict(connection.execute('SELECT key, value FROM metadata'))
    report = {'measurement_scope': args.scope, 'database_bytes': path.stat().st_size,
              'database_sha256': actual_digest, 'runtime': builder.runtime_info(), 'metadata': metadata,
              'source_sha256': {name: builder.digest(ROOT / name) for name in
                                ['time_zones.py', 'build_atlas.py', 'app.py']}}
    # Close the metadata connection before advising the file cache away.
    if args.only is None or args.only == 'first':
        start = time.perf_counter()
        report['first'] = first_lookups(path)
        report['first_seconds'] = time.perf_counter() - start
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if args.only == 'first':
        return
    with contextlib.closing(open_atlas(path)) as conn:
        actions = {'plans': lambda: query_plans(conn),
                   'latency': lambda: benchmark(path, conn, args.samples),
                   'agreement': lambda: agreement(conn, args.samples),
                   'reachability': lambda: reachability(conn, args.samples),
                   'presentation': lambda: presentation_losses(conn),
                   'exact': lambda: crowded_exact_lookups(path, conn),
                   }
        for name, action in actions.items():
            if args.only is None or args.only == name:
                start = time.perf_counter()
                report[name] = action()
                report[name + '_seconds'] = time.perf_counter() - start
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
