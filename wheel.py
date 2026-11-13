# Zīj. Copyright (C) 2026 Dār al-Ḥikma.
# Licensed under the GNU Affero General Public License, version 3: see LICENSE.
"""The pictures: the chart wheel, the Timing page's multi-ring wheels and the
two direction strips, each a pure function from a chart's data to an SVG
string, with the two palettes they are drawn in. The engine takes this module
whole, so the pages call them by the names they always had. It imports the
standard library, markup.py, and house_style.py and saved_faces.py for its
colours and faces; what it reads of the engine's (the glyphs of the points, the
bounds, the houses and the motion of a point, the words of a direction) it
reaches through _the_engine when it is called, never at import.
"""
import math
import re
import unicodedata

import house_style
import saved_faces
from markup import _esc_attr, _esc_text, _isolated


def _the_engine():
    """The engine, reached when called and never at import (the engine
    imports this module): what this module reads of the engine's is looked up
    there at each call, so that the object the engine holds under the name
    then is the one used."""
    import engine
    return engine


# ---- The chart wheel ---------------------------------------------------
# generate_hybrid_svg() is a pure function -- no Streamlit calls --
# returning an SVG string. Everything here is attributes: an SVG inside an <img>
# has no page CSS, web fonts or scripts, so what the picture draws in travels
# with it (the symbol faces) or is left to the computer until the picture is
# saved (saved_svg). A picture drawn in the page itself takes the page's faces.
#
# Rings, outside in: a rim band with the WHOLE-SIGN place numbers; the sign
# band with the glyphs, shaded by triplicity, and a one-degree scale on its
# inner edge; the planet zone, where each point's label runs radially --
# glyph, degree, sign, minute, and a black retrograde mark -- as the
# reference charts draw it; a narrow ring with the ALCHABITIUS house numbers;
# and the hub, which names the chart. The rising sign's boundary sits at
# 9 o'clock (the app's own convention), so whole-sign places fall on
# the twelve clock positions. Alchabitius cusps stay dashed (the app's
# convention) and run from the quadrant ring to the degree scale.
WHEEL_LAYOUT_OPTIONS = ('Square', 'Wide')
# How a wheel looks, chosen whatever the page's mode: the page's own palette, or
# one of the two palettes, or either of those as one ink on one ground.
WHEEL_LOOK_OPTIONS = ('Follow the page', 'Light', 'Dark', 'Plain', 'Plain dark')
WHEEL_SIZE = 1000                     # viewBox of the square wheel
WHEEL_WIDE_WIDTH = 1760               # the wide variant: wheel plus a positions panel
_R_RIM, _R_WS_IN, _R_SIGN_IN = 492, 462, 402
_RING_IN = 19                         # how far in from the outer ring a point's label stands: its whole stack moves by this
_R_GLYPH, _R_DEG, _R_SIGN, _R_MIN, _R_RX = (r - _RING_IN for r in (344, 306, 272, 242, 214))
_R_Q_OUT, _R_Q_IN = 152, 122
_R_BOUNDS_BAND = 24                   # the Egyptian-bounds ring, inside the degree scale, when drawn
LABEL_MIN_SEP = 10.5                  # degrees between neighbouring label stacks
LABEL_STAGGER = 30                    # px inward for alternate members of a crowded run, on a Timing wheel
_LABEL_EDGE = 5                       # the edge behind a label's text: this width, half of it outside the letter
# Each point's glyph on the chart's wheel, all about as large and as heavy as
# one another: (size, stroke in the ink, the y that levels its ink's middle with
# the others', about 1.7 below the circle). Read off the rendered glyphs; the
# symbol faces travel with the picture.
_GLYPH_PX = 34
_GLYPH_SET = {'Sun': (0.885, 0.85, 1.1), 'Moon': (1.085, 0.7, 0.5), 'Mercury': (0.975, 0.7, 0.3),
              'Venus': (1.155, 0.4, 0.4), 'Mars': (1.285, 0.1, -2.8), 'Jupiter': (1.01, 0.2, 1.1),
              'Saturn': (0.99, 0.3, 1.4), 'North Node': (0.93, 0.45, 1.5), 'South Node': (0.93, 0.45, 1.5),
              'Lot of Fortune': (1.035, 0.0, -0.5)}
# The hub: its ink stays inside this radius, and each line starts at its size
# here and steps down, by its length, to what its chord holds.
_HUB_INK_R = 116
_HUB_FLOOR_PX, _HUB_WRAP_PX = 10, 13
# The two palettes come from tools/house_style/tokens.json, through house_style.py.
# A picture drawn on an opaque ground would show as a rectangle on a page of
# another colour, so the renderers take theme=: None is the light palette, and
# 'dark' is the same picture on the dark page's own ground. One dict per theme,
# read once at the top of a renderer; the geometry does not know which it is
# drawing in.
_PALETTE_LIGHT = house_style.WHEEL_PALETTES['light']
_PALETTE_DARK = house_style.WHEEL_PALETTES['dark']
# One tint per triplicity: fire, earth, air, water; sign i uses i % 4.
TRIPLICITY_TINT = _PALETTE_LIGHT['tints']
_WHEEL_FONT = house_style.PICTURE_STACK
_CUSP_COLOUR = _PALETTE_LIGHT['cusp']
_AXIS_COLOUR = _PALETTE_LIGHT['axis']     # by cusp index: the horizon, the meridian
_VS = '︎'                        # text-presentation selector: never an emoji
SIGN_GLYPHS = ['♈', '♉', '♊', '♋', '♌', '♍',
               '♎', '♏', '♐', '♑', '♒', '♓']


def _spread_labels(bearings, min_sep=LABEL_MIN_SEP):
    """Push neighbouring bearings apart on the circle until every adjacent
    pair is at least min_sep degrees apart. bearings are in ascending order
    around the circle; that circular order is preserved and the result
    comes back in the same order. Input already separated is unchanged.

    The sequence is unwrapped to a monotone one first and the gaps kept
    SIGNED, so a pair pushed apart cannot leapfrog its neighbours (a
    modular gap would read the overshoot as a wide gap and leave the order
    scrambled). A negative gap is a violation like any other and is pushed
    open on the next sweep."""
    n = len(bearings)
    if n < 2:
        return [b % 360.0 for b in bearings]
    min_sep = min(min_sep, 0.9 * 360.0 / n)       # n labels must fit the circle
    pos = [bearings[0] % 360.0]
    for b in bearings[1:]:
        b = b % 360.0
        while b < pos[-1]:
            b += 360.0
        pos.append(b)
    for _ in range(1000):
        moved = False
        for k in range(n):
            j = (k + 1) % n
            gap = (pos[j] + (360.0 if j == 0 else 0.0)) - pos[k]
            if gap < min_sep - 1e-6:
                push = (min_sep - gap) / 2.0
                pos[k] -= push
                pos[j] += push
                moved = True
        if not moved:
            break
    return [p % 360.0 for p in pos]


def _stagger_offsets(true_bearings, shown_bearings, step=LABEL_STAGGER):
    """Within each run of consecutive displaced labels, every other one
    steps inward by `step` px, as Solar Fire does for stellia."""
    displaced = [abs(((s - t + 180.0) % 360.0) - 180.0) > 0.05 for s, t in zip(shown_bearings, true_bearings)]
    offsets = [0] * len(displaced)
    k = 0
    while k < len(displaced):
        if displaced[k]:
            end = k
            while end < len(displaced) and displaced[end]:
                end += 1
            for n, idx in enumerate(range(k, end)):
                offsets[idx] = step if n % 2 else 0
            k = end
        else:
            k += 1
    return offsets


def _wheel_dm(longitude):
    """Degree and minute within the sign, minutes truncated exactly as
    get_degree_string() truncates them (one shared helper), so the wheel and the tables agree."""
    deg_total, minute = _the_engine()._whole_minutes(longitude)
    return deg_total % 30, minute


def _wheel_sign(longitude):
    """The index (0-11) of the sign the wheel prints beside _wheel_dm's
    degree and minute: the sign of the same carried total, as
    get_degree_string prints it. The carry stops at a sign boundary, so
    60 - 1e-10 prints 29° Tau 59' in the table and on the wheel alike.
    Where the point is DRAWN stays the float."""
    return _the_engine()._whole_minutes(longitude)[0] // 30


def _face(pal, cx, cy, r):
    """The wheel's own face, over the picture's ground, where a palette gives
    it one: what shows between the rings is then the face, and only what lies
    outside the rim is the ground."""
    return [f'<circle class="face" cx="{cx}" cy="{cy}" r="{r}" fill="{pal["face"]}"/>'] if 'face' in pal else []


def _hub_em(s, weight):
    """About how wide a line of the hub is, in ems, by the kinds of letter it
    holds, on the side of too wide: the Latin letters as the interface face the
    page and a saved picture carry sets them, the rest as the computer's own
    face may. What stops a line at the circle is the room this leaves."""
    em = 0.0
    for ch in unicodedata.normalize('NFKC', s):       # one code point can be a whole phrase
        if unicodedata.category(ch) in ('Mn', 'Me', 'Cf'):
            continue
        if unicodedata.east_asian_width(ch) in ('W', 'F'):
            em += 1.02
        elif ch in 'mwMWÆŒæœ@':
            em += 0.92
        elif ch in " ijlftrI.,:;'′·|!()[]-/_":
            em += 0.30
        elif ord(ch) > 0x24F:
            em += 0.66
        elif ch.isupper():
            em += 0.66
        else:
            em += 0.54
    return em * (1.08 if weight == 'bold' else 1.0)


def _hub_rows(lines):
    """The hub's lines as drawn: [(words, size, weight, y from the middle, which
    line they came from)]. Each line stands at its own size on the chord it has;
    one too long steps down, takes a second line at _HUB_WRAP_PX, and goes on
    down to _HUB_FLOOR_PX, where what is left is cut as a name over 30 letters is."""
    rows = [dict(s=s, px=px, w=w, may_wrap=wrap, line=k) for k, (s, px, w, wrap) in enumerate(lines)]
    while True:
        ys, y = [], -sum(r['px'] for r in rows) * 0.6
        for r in rows:
            ys.append(y + r['px'] * 0.6)
            y += r['px'] * 1.2
        over = None
        for r, yc in zip(rows, ys):
            reach = abs(yc) + r['px'] * 0.55
            room = 2.0 * math.sqrt(max(_HUB_INK_R ** 2 - reach ** 2, 0.0))
            if _hub_em(r['s'], r['w']) * r['px'] > room:
                over = r
                break
        if over is None:
            return [(r['s'], r['px'], r['w'], yc, r['line']) for r, yc in zip(rows, ys)]
        if over['may_wrap'] and over['px'] <= _HUB_WRAP_PX:
            # In two, at the break nearest its middle: a space, else after a
            # comma, a slash or an underscore, else at the middle itself.
            words = over['s']
            breaks = [k + 1 for k, ch in enumerate(words) if ch in ' ,/_' and 0 < k < len(words) - 1]
            cut = min(breaks, key=lambda k: abs(k - len(words) / 2.0)) if breaks else len(words) // 2
            at = rows.index(over)
            rows[at:at + 1] = [dict(over, s=words[:cut].strip(), px=_HUB_WRAP_PX + 1, may_wrap=False),
                               dict(over, s=words[cut:].strip(), px=_HUB_WRAP_PX + 1, may_wrap=False)]
        elif over['px'] > _HUB_FLOOR_PX:
            over['px'] -= 1
        else:
            over['s'] = over['s'][:-2].rstrip() + '…'


def generate_hybrid_svg(chart_data, chart_name, location_query, lat, lon, dt_local, tz_name,
                        wide=False, chronocrats=None, bounds=False, theme=None, plain=False):
    pal = _wheel_palette(theme, plain)
    size = WHEEL_SIZE
    cx = cy = size / 2.0
    asc = chart_data['ascendant']
    mc = chart_data['mc']
    cusps = chart_data['houses']
    if asc is None:
        # No rising sign to orient the wheel by: no wheel, only the reason.
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} 80"><title>'
                f'{_esc_text(chart_data["division_reason"])}</title></svg>')
    asc_sign = int((asc % 360.0) // 30)
    angles = (asc, mc, (asc + 180.0) % 360.0, (mc + 180.0) % 360.0)

    # The rising sign's boundary at 9 o'clock, zodiac counter-clockwise.
    # The geometry and the two primitives are shared with the multi-ring
    # wheels of the Timing page.
    ang, xy, sector, _arc = _wheel_geometry(asc_sign, cx, cy)
    line, text = _svg_line, _svg_text
    # An Egyptian-bounds ring inside the degree scale: PN IV's
    # nativities carry one (Figures 1, 22 and 25), and the revolution of
    # Figure 26 does; Figure 51, the simplified I.6 wheel, does not. It sits in
    # the leader zone, so the planet stack is not moved.
    r_planet_edge = _R_SIGN_IN - _R_BOUNDS_BAND if bounds else _R_SIGN_IN

    def sign_glyph(longitude):
        return SIGN_GLYPHS[_wheel_sign(longitude)] + _VS

    width = WHEEL_WIDE_WIDTH if wide else size
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {size}" width="{width}" height="{size}" '
           f'style="font-family:{_WHEEL_FONT}">',
           f'<style>{_the_engine().font_face_css()}</style>',
           f'<rect width="{width}" height="{size}" fill="{pal["bg"]}"/>']
    svg += _face(pal, cx, cy, _R_RIM)

    # 1. Sign band shaded by triplicity, sign glyphs, whole-sign place
    #    numbers on the rim, boundary spokes through both bands.
    #
    #    Each sign's own elements stand in a <g class="sign" data-sign="0-11">
    #    and each point's letters in a <g class="pt" data-point data-lon>, the
    #    convention the revolution wheels carry (_draw_ring_points); its tick
    #    and leader go down before any label, as lines each carrying the same
    #    data-point. The groups add a handle and nothing else: strip
    #    the wrappers and the picture is the picture without them, which is
    #    what tests/test_clickable_wheel_2026_09_15.py asserts.
    for i in range(12):
        a0, a1 = ang(i * 30), ang(i * 30 + 30)
        svg.append(f'<g class="sign" data-sign="{_esc_attr(i)}">')
        svg.append(f'<path d="{sector(_R_SIGN_IN, _R_WS_IN, a0, a1)}" fill="{pal["tints"][i % 4]}"/>')
        svg.append(f'<path d="{sector(_R_WS_IN, _R_RIM, a0, a1)}" fill="{pal["panel"]}"/>')
        # An angle box (step 4) sits wherever the Ascendant or MC falls in its
        # sign; a glyph within 7 degrees of one steps 8 degrees aside.
        glyph_lon = i * 30 + 15
        for angle_lon in angles:
            gap = ((angle_lon - glyph_lon + 180.0) % 360.0) - 180.0
            if abs(gap) < 7.0:
                glyph_lon = i * 30 + 15 - (8 if gap > 0 else -8)
        gx, gy = xy((_R_SIGN_IN + _R_WS_IN) / 2, ang(glyph_lon))
        svg.append(text(gx, gy, SIGN_GLYPHS[i] + _VS, 30, fill=pal['ink']))
        hx, hy = xy((_R_WS_IN + _R_RIM) / 2, ang(i * 30 + 15))
        svg.append(text(hx, hy, str((i - asc_sign) % 12 + 1), 17, 'bold', pal['ink']))
        x0, y0 = xy(_R_SIGN_IN, a0); x1, y1 = xy(_R_RIM, a0)
        svg.append(line(x0, y0, x1, y1, pal['rule'], 1.2))
        svg.append('</g>')

    # 2. Degree scale on the inner edge of the sign band: 1, 5 and 10 degrees.
    for d in range(360):
        ln = 14 if d % 10 == 0 else 10 if d % 5 == 0 else 5
        x0, y0 = xy(_R_SIGN_IN, ang(d)); x1, y1 = xy(_R_SIGN_IN + ln, ang(d))
        svg.append(line(x0, y0, x1, y1, pal['rule'], 0.9 if ln > 5 else 0.5))
    if bounds:
        svg.extend(_bounds_ring_svg(ang, xy, sector, r_planet_edge, _R_SIGN_IN, glyph_px=12, pal=pal))
    for r, w in ((_R_RIM, 2.5), (_R_WS_IN, 1.2), (_R_SIGN_IN, 1.6), (_R_Q_OUT, 1.2), (_R_Q_IN, 1.6)):
        svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{pal["rule"]}" stroke-width="{w}"/>')

    # 3. Alchabitius cusps, dashed, reaching the degree scale;
    #    the four stakes solid and coloured. House numbers at mid-house on
    #    the quadrant ring.
    for i, cusp_lon in enumerate(cusps):
        x0, y0 = xy(_R_Q_IN, ang(cusp_lon)); x1, y1 = xy(r_planet_edge, ang(cusp_lon))
        if i in pal['axis']:
            svg.append(line(x0, y0, x1, y1, pal['axis'][i], 2.6))
        else:
            svg.append(line(x0, y0, x1, y1, pal['cusp'], 1.4, '6 4'))
        mid = cusp_lon + ((cusps[(i + 1) % 12] - cusp_lon) % 360.0) / 2.0
        mx, my = xy((_R_Q_OUT + _R_Q_IN) / 2, ang(mid))
        svg.append(text(mx, my, str(i + 1), 14, 'bold', pal['cusp']))

    # 4. Angle boxes on the sign band: degree over minute, in the axis colour.
    #    The four angles carry data-point under the names the Calculated
    #    Points table prints, so a click on a box reaches the same panel a
    #    click on a planet does.
    for angle_lon, colour, angle_name in zip(angles, (pal['horizon'], pal['meridian'], pal['horizon'], pal['meridian']),
                                             ('Ascendant', 'Midheaven', 'Descendant', 'Imum Coeli')):
        d, m = _wheel_dm(angle_lon)
        svg.append(f'<g class="pt" data-point="{_esc_attr(angle_name)}" data-lon="{_the_engine()._lon_attr(angle_lon)}">')
        bx, by = xy((_R_SIGN_IN + _R_WS_IN) / 2, ang(angle_lon))
        svg.append(f'<rect x="{bx - 19:.1f}" y="{by - 17:.1f}" width="38" height="34" rx="3" '
                   f'fill="{pal["panel"]}" stroke="{colour}" stroke-width="1.2"/>')
        svg.append(text(bx, by - 8, f'{d:02d}°', 13, 'bold', colour))
        svg.append(text(bx, by + 8, f"{m:02d}'", 13, 'bold', colour))
        svg.append('</g>')

    # 5. Points. The seven planets and the north node from the ephemeris, the
    #    south node opposite it with the same motion, the Lot of Fortune
    #    with no motion. A retrograde mark goes on any point whose longitude
    #    speed is negative, nodes included: the true node has direct
    #    spells and is shown as it moves.
    p_data = chart_data['planetary_data']
    node = p_data['North Node']
    points = [(name, d['longitude'], d.get('speed_in_lon', 0.0)) for name, d in p_data.items()]
    points.append(('South Node', (node['longitude'] + 180.0) % 360.0, node.get('speed_in_lon', 0.0)))
    points.append(('Lot of Fortune', chart_data['lot_of_fortune'], None))
    points.sort(key=lambda p: ang(p[1]))
    true_bearings = [ang(p[1]) for p in points]
    shown = _spread_labels(true_bearings)
    # Every glyph on one circle: a crowd is met along the circle, by the spread
    # and the leaders. The lines go down first, each with its point's handle, so
    # that none crosses a label; what runs beneath stops at the edge behind its letters.
    for (name, _lon, _speed), a_true, a_shown in zip(points, true_bearings, shown):
        # A tick on the ring at the true degree, a hairline from it to the glyph.
        handle = f'<line data-point="{_esc_attr(name)}" '
        x0, y0 = xy(r_planet_edge, a_true); x1, y1 = xy(r_planet_edge - 10, a_true)
        svg.append(line(x0, y0, x1, y1, pal['rule'], 1.6).replace('<line ', handle, 1))
        x2, y2 = xy(_R_GLYPH + 22, a_shown)
        svg.append(line(x1, y1, x2, y2, pal['leader'], 0.8).replace('<line ', handle + 'class="leader" ', 1))
    ground = pal.get('face', pal['bg'])
    edge = (ground, _LABEL_EDGE)
    glyphs = []
    for (name, _lon, _speed), a_shown in zip(points, shown):
        gx, gy = xy(_R_GLYPH, a_shown)
        factor, weight, nudge = _GLYPH_SET.get(name, (1.0, 0.0, 0.0))
        glyphs.append((gx, gy + nudge, _the_engine().POINT_GLYPHS.get(name, name[:2]) + _VS, round(_GLYPH_PX * factor, 1), weight))
    # A glyph's stroke is its own ink, so its edge is a copy of it, underneath.
    for gx, gy, glyph, glyph_px, weight in glyphs:
        svg.append(text(gx, gy, glyph, glyph_px, fill=ground, cls='edge', outline=(ground, round(weight + _LABEL_EDGE, 2))))
    for (name, lon_val, speed), a_shown, (gx, gy, glyph, glyph_px, weight) in zip(points, shown, glyphs):
        svg.append(f'<g class="pt" data-point="{_esc_attr(name)}" data-lon="{_the_engine()._lon_attr(lon_val)}">')
        d, m = _wheel_dm(lon_val)
        svg.append(text(gx, gy, glyph, glyph_px, fill=pal['ink'], outline=(pal['ink'], weight) if weight else None))
        dx_, dy_ = xy(_R_DEG, a_shown); svg.append(text(dx_, dy_, f'{d:02d}°', 18, 'bold', pal['ink'], outline=edge))
        sx, sy = xy(_R_SIGN, a_shown); svg.append(text(sx, sy, sign_glyph(lon_val), 19, fill=pal['ink'], outline=edge))
        mx, my = xy(_R_MIN, a_shown); svg.append(text(mx, my, f"{m:02d}'", 15, fill=pal['ink'], outline=edge))
        if speed is not None and _the_engine().motion_state(name, speed) == 'retrograde':
            rx, ry = xy(_R_RX, a_shown); svg.append(text(rx, ry, '℞' + _VS, 15, fill=pal['ink'], outline=edge))   # the ink, never red
        svg.append('</g>')

    # 6. Hub: the chart's name first ("Transits" when none was
    #    given), then when, where, and the systems in force. User strings
    #    are escaped: a name or place with & or < would otherwise break the
    #    whole wheel. The name and the place are isolated (_isolated), as the
    #    page sets them, so an override in either ends with it.
    svg.append(f'<circle cx="{cx}" cy="{cy}" r="{_R_Q_IN - 1}" fill="{pal["panel"]}"/>')
    name = str(chart_name)
    if len(name) > 30:
        name = name[:29] + '…'
    lat_s = f"{int(abs(lat))}°{int((abs(lat) % 1) * 60):02d}′{'N' if lat >= 0 else 'S'}"
    lon_s = f"{int(abs(lon))}°{int((abs(lon) % 1) * 60):02d}′{'E' if lon >= 0 else 'W'}"
    # (words, size, weight, whether they are the reader's own and may take a
    # second line): the name and the place are isolated, as the page sets them.
    hub_rows = _hub_rows([
        (name, 24, 'bold', True),
        (f'{dt_local.day} {dt_local:%b} {dt_local.year}  {dt_local:%H:%M}', 19, 'normal', False),
        (str(tz_name), 18, 'normal', True),
        (str(location_query), 19, 'normal', True),
        (f'{lat_s}  {lon_s}', 18, 'normal', False),
        (str(chart_data['sect']), 19, 'bold', False),
        ('Whole sign · Alchabitius', 17, 'normal', False),
        ('Tropical · True node', 17, 'normal', False),
    ])
    for row_text, px, w, y, row_index in hub_rows:
        s = _isolated(row_text) if row_index in (0, 3) else row_text
        svg.append(text(cx, cy + y, _esc_text(s), px, w, pal['ink']))

    # 7. The wide variant: a positions panel beside the wheel, so a full-
    #    window view uses the window's width as well as its height.
    if wide:
        x0 = size + 40
        svg.append(text(x0, 60, 'Positions', 22, 'bold', pal['ink'], anchor='start'))
        for dx, h in ((0, 'Point'), (170, 'Position'), (290, 'Whole-sign place'), (460, 'Quadrant'), (590, 'Motion')):
            svg.append(text(x0 + dx, 100, h, 15, 'bold', pal['label'], anchor='start'))
        svg.append(line(x0, 112, x0 + 680, 112, pal['rule'], 1))
        y = 140
        for name_, lon_val, speed in sorted(points, key=lambda p: list(_the_engine().POINT_GLYPHS).index(p[0]) if p[0] in _the_engine().POINT_GLYPHS else 99):
            d, m = _wheel_dm(lon_val)
            if speed is None:
                motion = '–'
            else:
                motion = _the_engine().motion_state(name_, speed)
                motion = '℞' + _VS + ' retrograde' if motion == 'retrograde' else motion
            svg.append(text(x0, y, _the_engine().POINT_GLYPHS.get(name_, '') + _VS, 22, fill=pal['ink'], anchor='start'))
            svg.append(text(x0 + 34, y, _esc_text(name_), 16, fill=pal['ink'], anchor='start'))
            svg.append(text(x0 + 170, y, f'{d:02d}° {sign_glyph(lon_val)} {m:02d}′', 16, fill=pal['ink'], anchor='start'))
            svg.append(text(x0 + 290, y, str(_the_engine().get_wsh_house(lon_val, asc)), 16, fill=pal['ink'], anchor='start'))
            svg.append(text(x0 + 460, y, str(_the_engine().get_effective_house(lon_val, cusps)) if cusps else '–', 16, fill=pal['ink'], anchor='start'))
            svg.append(text(x0 + 590, y, motion, 15, fill=pal['ink'], anchor='start'))
            y += 36
        y += 20
        svg.append(text(x0, y, 'Angles and cusps (Alchabitius)', 18, 'bold', pal['ink'], anchor='start'))
        y += 34
        for i, cusp_lon in enumerate(cusps):
            d, m = _wheel_dm(cusp_lon)
            label = {0: 'Asc', 3: 'IC', 6: 'Des', 9: 'MC'}.get(i, '')
            col = x0 + (0 if i < 6 else 340)
            yy = y + (i % 6) * 32
            svg.append(text(col, yy, f'{i + 1:2d}', 15, 'bold', pal['cusp'], anchor='start'))
            svg.append(text(col + 40, yy, f'{d:02d}° {sign_glyph(cusp_lon)} {m:02d}′', 15, fill=pal['ink'], anchor='start'))
            if label:
                svg.append(text(col + 190, yy, label, 15, 'bold', pal['axis'][i], anchor='start'))
        y += 6 * 32 + 20
        sect_line = f"Sect: {_esc_text(chart_data['sect'])}"
        if chronocrats:
            sect_line += (f" · Lord of the day: {_esc_text(_the_engine().day_lord_qualified(chronocrats))}"
                          f" · Lord of the hour: {_esc_text(_the_engine().hour_lord_qualified(chronocrats))}")
        svg.append(text(x0, y, sect_line, 15, fill=pal['ink'], anchor='start'))

    svg.append('</svg>')
    return ''.join(svg)


# ---- Multi-ring wheels and direction strips for the Timing page ----
# Built from the book's own figures.
# The revolution over the root is PN IV I.6 (Figure 51, fn 33); the
# month over the year and the root is PN IV IX.3, 4-6 (Figures 39 and 109, fn 58);
# the profection is Figures 3, 15 and 33. What Dykes' wheels carry, read
# from the images: the outer charts in whole signs, the sign of the year
# shaded, the profection as a dashed arc from the natal Ascendant, an
# Egyptian-bounds ring, and "only the seven traditional planets, the Nodes,
# Lot of Fortune, and axial degrees" (p. 12) unless more is asked for. On
# the order: "Abu Ma'shar seems to prefer that the SR be the inner wheel,
# but to me this seem unnatural and I only do it to illustrate his
# instructions in Ch. I.6" (p. 12) -- the caller chooses; the page offers
# both. Pure functions, no Streamlit, SVG strings out; every point carries
# data- attributes so a test can hold the picture to the inventory table.

_M_RIM, _M_SIGN_IN, _M_BOUNDS_IN, _M_HUB_RING, _M_HUB = 478, 430, 408, 150, 118
WHEEL_RING_COLOURS = _PALETTE_LIGHT['rings']               # inner, middle, outer ring text
WHEEL_SHADE = _PALETTE_LIGHT['shade']                      # the sign of the year (fn 33)
WHEEL_BOUND_TINT = _PALETTE_LIGHT['bound_tint']            # the bound the distribution stands in
WHEEL_ORDER_OPTIONS = ("Nativity inside (Dykes)", "Revolution inside (Abu Ma'shar's order, PN IV I.6)")
WHEEL_VIEW_OPTIONS = ("Year", "Year over root", "Month over year and root", "Month", "Profection")
_ASPECT_GLYPH = {'body': '☌', 'sextile': '⚹', 'square': '□', 'trine': '△', 'opposition': '☍'}


def _wheel_geometry(asc_sign, cx=500.0, cy=500.0):
    """ang/xy/sector for a wheel whose rising SIGN's boundary sits at
    9 o'clock, the zodiac running counter-clockwise."""
    def ang(longitude):
        return (longitude - asc_sign * 30 + 180.0) % 360.0

    def xy(r, a):
        t = math.radians(a)
        return cx + r * math.cos(t), cy - r * math.sin(t)

    def sector(r_in, r_out, a0, a1):
        x0o, y0o = xy(r_out, a0); x1o, y1o = xy(r_out, a1)
        x0i, y0i = xy(r_in, a0); x1i, y1i = xy(r_in, a1)
        large = 1 if (a1 - a0) % 360 > 180 else 0
        return (f'M{x0o:.1f},{y0o:.1f} A{r_out},{r_out} 0 {large} 0 {x1o:.1f},{y1o:.1f} '
                f'L{x1i:.1f},{y1i:.1f} A{r_in},{r_in} 0 {large} 1 {x0i:.1f},{y0i:.1f} Z')

    def arc(r, a0, a1):
        """An open arc from bearing a0 to a1 the zodiacal way round."""
        x0, y0 = xy(r, a0); x1, y1 = xy(r, a1)
        large = 1 if (a1 - a0) % 360 > 180 else 0
        return f'M{x0:.1f},{y0:.1f} A{r},{r} 0 {large} 0 {x1:.1f},{y1:.1f}'

    return ang, xy, sector, arc


def _svg_line(x0, y0, x1, y1, stroke, width, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ''
    return f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{stroke}" stroke-width="{width}"{d}/>'


def _svg_text(x, y, s, px, weight='normal', fill=_PALETTE_LIGHT['ink'], anchor='middle', rotate=None, cls=None,
              outline=None):
    """outline, (colour, width), is a stroke behind the letter: a line under the
    text stops short of it when the colour is what lies beneath, and a glyph
    grows heavier when it is the ink's."""
    rot = f' transform="rotate({rotate:.1f} {x:.1f} {y:.1f})"' if rotate is not None else ''
    c = f' class="{cls}"' if cls else ''
    o = f' paint-order="stroke" stroke="{outline[0]}" stroke-width="{outline[1]}" stroke-linejoin="round"' if outline else ''
    return (f'<text{c} x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" dominant-baseline="central" '
            f'font-size="{px}" font-weight="{weight}" fill="{fill}"{o}{rot}>{s}</text>')


def _svg_arrowhead(xy, r, a, colour, size=9, forward=True):
    """A small filled triangle at bearing a on radius r, pointing the
    zodiacal way (forward) along the circle."""
    tip_a = a + (1.2 if forward else -1.2) * (size * 0.5) * 57.2958 / r
    tx, ty = xy(r, tip_a)
    bx1, by1 = xy(r + size * 0.6, a)
    bx2, by2 = xy(r - size * 0.6, a)
    return f'<polygon points="{tx:.1f},{ty:.1f} {bx1:.1f},{by1:.1f} {bx2:.1f},{by2:.1f}" fill="{colour}"/>'


def _bounds_ring_svg(ang, xy, sector, r_in, r_out, highlight=None, glyph_px=12, pal=None):
    """The Egyptian bounds as a ring, a cell per bound with its lord's
    glyph, as every PN IV wheel carries (Figures 1, 22, 25, 26, 109).
    `highlight` is a longitude whose bound is tinted -- the bound the
    distribution stands in. Every cell is class="bound"."""
    pal = pal or _PALETTE_LIGHT
    out = []
    if highlight is not None:
        highlight = _the_engine()._on_circle(highlight)                # -1e-16 tints Aries' first bound
    for i, sign in enumerate(_the_engine().SIGN_ORDER):
        start = 0
        for limit, lord in _the_engine().EGYPTIAN_TERMS[sign]:
            a0, a1 = ang(i * 30 + start), ang(i * 30 + limit)
            tint = pal['panel']
            if highlight is not None and int(highlight // 30) == i and start <= (highlight % 30.0) < limit:
                tint = pal['bound_tint']
            out.append(f'<path class="bound" d="{sector(r_in, r_out, a0, a1)}" fill="{tint}" '
                       f'stroke="{pal["rule"]}" stroke-width="0.6"/>')
            mx, my = xy((r_in + r_out) / 2.0, ang(i * 30 + (start + limit) / 2.0))
            out.append(_svg_text(mx, my, _the_engine().POINT_GLYPHS[lord] + _VS, glyph_px, fill=pal['note'], cls='bound-lord'))
            start = limit
    return out


def _wheel_points(chart_data):
    """The points a wheel draws by default (p. 12): the seven planets, the
    nodes, the Lot of Fortune. (name, longitude, speed-or-None)."""
    p_data = chart_data['planetary_data']
    node = p_data['North Node']
    points = [(name, d['longitude'], d.get('speed_in_lon', 0.0)) for name, d in p_data.items()]
    points.append(('South Node', (node['longitude'] + 180.0) % 360.0, node.get('speed_in_lon', 0.0)))
    points.append(('Lot of Fortune', chart_data['lot_of_fortune'], None))
    return points


def _ring_layout(n, bounds):
    """(r_in, r_out) for n chart rings, inner to outer, between the hub
    ring and the bounds ring (or the degree scale)."""
    top = _M_BOUNDS_IN - 4 if bounds else _M_SIGN_IN - 4
    bottom = _M_HUB_RING
    if n == 1:
        return [(bottom, top)]
    if n == 2:
        split = bottom + (top - bottom) * 0.58
        return [(bottom, split), (split, top)]
    a = bottom + (top - bottom) * 0.40
    b = a + (top - bottom) * 0.30
    return [(bottom, a), (a, b), (b, top)]


def _draw_ring_points(svg, ang, xy, ring_idx, label, chart_data, r_in, r_out, colour, badges=None, pal=None):
    """One chart's default points in its annulus: a tick at the true
    degree on the ring's outer edge, a hairline to a radial stack (glyph,
    degree, sign, minute, retrograde mark, badge letters), spread apart
    as the natal wheel spreads them. Each point is a <g class="pt"> with
    data-ring/data-chart/data-point/data-lon."""
    # The stack -- glyph, degree, sign, minute, retrograde, badge -- fits the
    # annulus: sizes scale with its width (capped at the natal wheel's),
    # the lines are laid out between the ring's edges, and the stagger
    # for crowded runs is used only where the ring is wide enough for it.
    pal = pal or _PALETTE_LIGHT
    width = r_out - r_in
    scale = max(0.42, min(1.0, width / 150.0))
    px_glyph, px_deg, px_sign, px_min, px_rx = (round(34 * scale), round(18 * scale), round(19 * scale),
                                                 round(15 * scale), round(14 * scale))
    r_glyph = r_out - 12 - px_glyph * 0.55
    span = min(r_glyph - (r_in + 8), 118.0 * scale + 12.0)
    step = span / 4.6
    r_deg, r_sign, r_min, r_rx = r_glyph - step, r_glyph - 2.0 * step, r_glyph - 2.9 * step, r_glyph - 3.7 * step
    r_badge = r_glyph - 4.6 * step
    points = sorted(_wheel_points(chart_data), key=lambda p: ang(p[1]))
    true_b = [ang(p[1]) for p in points]
    min_sep = max(4.0, (px_glyph + 6) * 57.2958 / r_glyph)
    shown = _spread_labels(true_b, min_sep)
    stagger = round(min(30.0 * scale, max(0.0, width - span - 22.0)))
    offsets = _stagger_offsets(true_b, shown, step=stagger) if stagger >= 8 else [0] * len(points)
    for (name, lon_val, speed), a_true, a_shown, off in zip(points, true_b, shown, offsets):
        d, m = _wheel_dm(lon_val)
        svg.append(f'<g class="pt" data-ring="{ring_idx}" data-chart="{_esc_attr(label)}" data-point="{_esc_attr(name)}" '
                   f'data-lon="{_the_engine()._lon_attr(lon_val)}">')
        x0, y0 = xy(r_out, a_true); x1, y1 = xy(r_out - 8, a_true)
        svg.append(_svg_line(x0, y0, x1, y1, colour, 1.4))
        x2, y2 = xy(r_glyph - off + px_glyph * 0.6, a_shown)
        svg.append(_svg_line(x1, y1, x2, y2, pal['leader_ring'], 0.7))
        gx, gy = xy(r_glyph - off, a_shown); svg.append(_svg_text(gx, gy, _the_engine().POINT_GLYPHS.get(name, name[:2]) + _VS, px_glyph, fill=colour))
        dx_, dy_ = xy(r_deg - off, a_shown); svg.append(_svg_text(dx_, dy_, f'{d:02d}°', px_deg, 'bold', colour))
        sx, sy = xy(r_sign - off, a_shown); svg.append(_svg_text(sx, sy, SIGN_GLYPHS[_wheel_sign(lon_val)] + _VS, px_sign, fill=colour))
        mx, my = xy(r_min - off, a_shown); svg.append(_svg_text(mx, my, f"{m:02d}'", px_min, fill=colour))
        if speed is not None and _the_engine().motion_state(name, speed) == 'retrograde':
            rx, ry = xy(r_rx - off, a_shown); svg.append(_svg_text(rx, ry, '℞' + _VS, px_rx, fill=colour))
        if badges and badges.get(name):
            bx, by = xy(r_badge - off, a_shown)
            svg.append(_svg_text(bx, by, _esc_text(badges[name]), px_rx, 'bold', pal['badge'], cls='badge'))
        svg.append('</g>')


def _draw_ring_extras(svg, ang, xy, ring_idx, label, extras, r_out, colour, pal=None):
    """Optional points (Lots, rays, twelfth-parts): a short tick at the
    ring's outer edge and a tiny label, spread thinly. <g class="extra">."""
    pal = pal or _PALETTE_LIGHT
    if not extras:
        return
    items = sorted(extras, key=lambda e: ang(e[1]))
    true_b = [ang(e[1]) for e in items]
    shown = _spread_labels(true_b, 2.2)
    for item, a_true, a_shown in zip(items, true_b, shown):
        name, lon_val = item[0], item[1]
        short = item[2] if len(item) > 2 else (name if len(name) <= 6 else name[:6])
        svg.append(f'<g class="extra" data-ring="{ring_idx}" data-chart="{_esc_attr(label)}" '
                   f'data-point="{_esc_attr(name)}" data-lon="{_the_engine()._lon_attr(lon_val)}">')
        x0, y0 = xy(r_out, a_true); x1, y1 = xy(r_out - 5, a_true)
        svg.append(_svg_line(x0, y0, x1, y1, colour, 0.8))
        tx, ty = xy(r_out - 12, a_shown)
        svg.append(_svg_text(tx, ty, _esc_text(short) + _VS, 7, fill=colour, rotate=-(a_shown - 90.0) % 360.0 - 90.0))
        svg.append('</g>')


def generate_multiwheel_svg(rings, chart_name, wide=False, bounds=True, shade_sign=None, shade_label='Sign of year',
                            outline_sign=None, outline_label='Sign of month', profection_from=None,
                            distribution=None, marks=(), badges=None, extras=None, hub_lines=(), theme=None,
                            plain=False):
    """One to three charts on one zodiac. `rings` are dicts inner to outer:
    {'label', 'chart' (a chart_data), 'when' (a short line for the hub)}.
    shade_sign / outline_sign: sign indices 0-11 (the sign of the year,
    the sign of the month). profection_from: a longitude whose sign the
    dashed arc starts from, ending at shade_sign (Figures 3, 33).
    distribution: {'start': lon, 'end': lon} draws the directed
    Ascendant's arc and tints the bound of `end` (Figures 2, 65). marks:
    (label, lon, ring_idx) degrees ticked on a ring's outer edge. badges:
    {ring_idx: {planet: letters}}. extras: {ring_idx: [(name, lon)]}."""
    pal = _wheel_palette(theme, plain)
    rings = list(rings)
    assert 1 <= len(rings) <= 3
    size = WHEEL_SIZE
    cx = cy = size / 2.0
    inner = rings[0]['chart']
    asc_sign = int((inner['ascendant'] % 360.0) // 30)
    ang, xy, sector, arc = _wheel_geometry(asc_sign, cx, cy)
    width = WHEEL_WIDE_WIDTH if wide else size
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {size}" width="{width}" height="{size}" '
           f'style="font-family:{_WHEEL_FONT}">',
           f'<style>{_the_engine().font_face_css()}</style>',
           f'<rect width="{width}" height="{size}" fill="{pal["bg"]}"/>']
    svg += _face(pal, cx, cy, _M_RIM)
    layout = _ring_layout(len(rings), bounds)
    r_top = layout[-1][1]

    # 0. The shaded sign of the year, under everything (fn 33).
    if shade_sign is not None:
        a0, a1 = ang(shade_sign * 30), ang(shade_sign * 30 + 30)
        svg.append(f'<path class="shade" data-sign="{shade_sign}" d="{sector(_M_HUB, _M_RIM, a0, a1)}" fill="{pal["shade"]}"/>')
    # 1. Sign band, degree scale, spokes through every ring (whole signs are
    #    every chart's houses here, as Dykes draws them).
    for i in range(12):
        a0, a1 = ang(i * 30), ang(i * 30 + 30)
        fill = pal['tints'][i % 4] if shade_sign != i else pal['shade']
        svg.append(f'<path d="{sector(_M_SIGN_IN, _M_RIM, a0, a1)}" fill="{fill}"/>')
        gx, gy = xy((_M_SIGN_IN + _M_RIM) / 2.0 + 6, ang(i * 30 + 15))
        svg.append(_svg_text(gx, gy, SIGN_GLYPHS[i] + _VS, 26, fill=pal['ink']))
        x0, y0 = xy(_M_HUB, a0); x1, y1 = xy(_M_RIM, a0)
        svg.append(_svg_line(x0, y0, x1, y1, pal['rule'], 1.0))
    for d in range(360):
        ln = 12 if d % 10 == 0 else 8 if d % 5 == 0 else 4
        x0, y0 = xy(_M_SIGN_IN, ang(d)); x1, y1 = xy(_M_SIGN_IN + ln, ang(d))
        svg.append(_svg_line(x0, y0, x1, y1, pal['rule'], 0.8 if ln > 4 else 0.45))
    if bounds:
        svg.extend(_bounds_ring_svg(ang, xy, sector, _M_BOUNDS_IN, _M_SIGN_IN,
                                    highlight=(distribution or {}).get('end'), pal=pal))
    for r, w in ((_M_RIM, 2.2), (_M_SIGN_IN, 1.4), (_M_HUB_RING, 1.0), (_M_HUB, 1.4)):
        svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{pal["rule"]}" stroke-width="{w}"/>')
    if outline_sign is not None:
        a0, a1 = ang(outline_sign * 30), ang(outline_sign * 30 + 30)
        svg.append(f'<path class="outline" data-sign="{outline_sign}" d="{sector(_M_HUB, _M_RIM, a0, a1)}" '
                   f'fill="none" stroke="{pal["rule"]}" stroke-width="2.2" stroke-dasharray="7 5"/>')

    # 2. The rings, inner to outer: separator, whole-sign numbers of that
    #    chart, its angles across its own annulus, its points.
    for idx, (ring, (r_in, r_out)) in enumerate(zip(rings, layout)):
        chart = ring['chart']
        colour = pal['rings'][idx if len(rings) > 1 else 0]
        if idx > 0:
            svg.append(f'<circle cx="{cx}" cy="{cy}" r="{r_in}" fill="none" stroke="{pal["rule"]}" stroke-width="1.0"/>')
        c_asc_sign = int((chart['ascendant'] % 360.0) // 30)
        num_r = (_M_HUB + _M_HUB_RING) / 2.0 if idx == 0 else r_out - 9
        for i in range(12):
            nx, ny = xy(num_r, ang(i * 30 + 15 if idx > 0 else i * 30 + 15))
            svg.append(_svg_text(nx, ny, str((i - c_asc_sign) % 12 + 1), 15 if idx == 0 else 10,
                                 'bold', colour, cls='house'))
        a_lo = _M_HUB if idx == 0 else r_in
        for lon_val, col, lab in ((chart['ascendant'], pal['horizon'], 'As'), (chart['mc'], pal['meridian'], 'Mc'),
                                  ((chart['ascendant'] + 180.0) % 360.0, pal['horizon'], 'Ds'),
                                  ((chart['mc'] + 180.0) % 360.0, pal['meridian'], 'Ic')):
            x0, y0 = xy(a_lo, ang(lon_val)); x1, y1 = xy(r_out, ang(lon_val))
            svg.append(_svg_line(x0, y0, x1, y1, col, 2.0 if idx == 0 else 1.5))
            lx, ly = xy(r_out - 9, ang(lon_val) + 2.5 * 57.2958 / r_out * 3)
            svg.append(_svg_text(lx, ly, lab, 9, 'bold', col, cls='angle'))
        _draw_ring_points(svg, ang, xy, idx, ring['label'], chart, r_in, r_out, colour,
                          badges=(badges or {}).get(idx), pal=pal)
        _draw_ring_extras(svg, ang, xy, idx, ring['label'], (extras or {}).get(idx), r_out, colour, pal=pal)

    # 3. Marks: named degrees on a ring's outer edge (the terminal point ...).
    for lab, lon_val, ring_idx in marks:
        r_in, r_out = layout[min(ring_idx, len(layout) - 1)]
        a = ang(lon_val)
        x0, y0 = xy(r_out, a); x1, y1 = xy(r_out - 14, a)
        svg.append(f'<g class="mark" data-point="{_esc_attr(lab)}" data-lon="{_the_engine()._lon_attr(lon_val)}">')
        svg.append(_svg_line(x0, y0, x1, y1, pal['badge'], 2.2))
        tx, ty = xy(r_out - 22, a)
        svg.append(_svg_text(tx, ty, _esc_text(lab), 9, 'bold', pal['badge']))
        svg.append('</g>')

    # 4. The profection: a dashed arc outside the rim from the natal
    #    Ascendant's sign to the sign of the year, arrowhead at the end.
    if profection_from is not None and shade_sign is not None:
        s0 = int(_the_engine()._on_circle(profection_from) // 30)
        if s0 != shade_sign:
            a0, a1 = ang(s0 * 30 + 15), ang(shade_sign * 30 + 15)
            svg.append(f'<path class="profection" d="{arc(_M_RIM + 11, a0, a1)}" fill="none" stroke="{pal["rule"]}" '
                       f'stroke-width="2.4" stroke-dasharray="9 6"/>')
            svg.append(_svg_arrowhead(xy, _M_RIM + 11, a1, pal['rule']))
    # Sign labels run along the arc in the sign band's inner margin,
    # upright on either half of the wheel, as Dykes letters "Sign of year".
    def _tangential(r, lon_val, s, cls):
        a = ang(lon_val)
        rot = (90.0 - a) % 360.0
        if 180.0 < a % 360.0 < 360.0:
            rot += 180.0
        x, y = xy(r, a)
        return _svg_text(x, y, _esc_text(s), 10, 'bold', pal['label'], rotate=rot, cls=cls)
    if shade_sign is not None:
        svg.append(_tangential(_M_SIGN_IN + 15, shade_sign * 30 + 15, shade_label, 'shade-label'))
    if outline_sign is not None:
        svg.append(_tangential(_M_SIGN_IN + 15 if outline_sign != shade_sign else _M_SIGN_IN + 26,
                               outline_sign * 30 + 15, outline_label, 'outline-label'))

    # 5. The distribution: the directed Ascendant from its degree to the
    #    degree the caller passes (the revolution's, on the Year over root
    #    view), solid, on the inner edge of the bounds ring.
    if distribution:
        r_arc = r_top + 1
        a0, a1 = ang(distribution['start']), ang(distribution['end'])
        svg.append(f'<path class="distribution" data-start="{distribution["start"] % 360.0:.6f}" '
                   f'data-end="{distribution["end"] % 360.0:.6f}" d="{arc(r_arc, a0, a1)}" fill="none" '
                   f'stroke="{pal["horizon"]}" stroke-width="2.6"/>')
        svg.append(_svg_arrowhead(xy, r_arc, a1, pal['horizon'], size=11))

    # 6. Hub: the name, then one line per ring, inner first.
    svg.append(f'<circle cx="{cx}" cy="{cy}" r="{_M_HUB - 1}" fill="{pal["panel"]}"/>')
    name = str(chart_name)
    if len(name) > 30:
        name = name[:29] + '…'
    lines = [(_esc_text(_isolated(name)), 15 if len(name) <= 18 else 12, 'bold', pal['rings'][0])]
    for idx, ring in enumerate(rings):
        colour = pal['rings'][idx if len(rings) > 1 else 0]
        place = ('Inner', 'Middle', 'Outer')[idx] if len(rings) == 3 else ('Inner', 'Outer')[idx] if len(rings) == 2 else ''
        head = f"{place}: {ring['label']}" if place else ring['label']
        lines.append((_esc_text(head), 11, 'bold', colour))
        if ring.get('when'):
            lines.append((_esc_text(ring['when']), 9, 'normal', colour))
    for s in hub_lines:
        lines.append((_esc_text(s), 9, 'normal', pal['note']))
    y = cy - 6.5 * (len(lines) - 1)
    for s, px, w, col in lines:
        svg.append(_svg_text(cx, y, s, px, w, col))
        y += 13

    # 7. Wide: a positions column per ring.
    if wide:
        col_w = (width - size - 60) / len(rings)
        for idx, ring in enumerate(rings):
            colour = pal['rings'][idx if len(rings) > 1 else 0]
            x0 = size + 40 + idx * col_w
            svg.append(_svg_text(x0, 60, _esc_text(ring['label']), 18, 'bold', colour, anchor='start'))
            if ring.get('when'):
                svg.append(_svg_text(x0, 84, _esc_text(ring['when']), 11, fill=colour, anchor='start'))
            svg.append(_svg_line(x0, 98, x0 + col_w - 30, 98, pal['rule'], 1))
            chart = ring['chart']
            y = 122
            pts = sorted(_wheel_points(chart), key=lambda p: list(_the_engine().POINT_GLYPHS).index(p[0]) if p[0] in _the_engine().POINT_GLYPHS else 99)
            for name_, lon_val, speed in pts:
                d, m = _wheel_dm(lon_val)
                motion = '℞' + _VS if speed is not None and _the_engine().motion_state(name_, speed) == 'retrograde' else ''
                svg.append(_svg_text(x0, y, _the_engine().POINT_GLYPHS.get(name_, '') + _VS, 18, fill=colour, anchor='start'))
                svg.append(_svg_text(x0 + 30, y, f'{d:02d}° {SIGN_GLYPHS[_wheel_sign(lon_val)]}{_VS} {m:02d}′ {motion}',
                                     14, fill=colour, anchor='start'))
                svg.append(_svg_text(x0 + col_w - 50, y, str(_the_engine().get_wsh_house(lon_val, chart['ascendant'])), 13, fill=colour))
                y += 28
            y += 10
            for lon_val, lab in ((chart['ascendant'], 'Asc'), (chart['mc'], 'MC')):
                d, m = _wheel_dm(lon_val)
                svg.append(_svg_text(x0, y, lab, 13, 'bold', colour, anchor='start'))
                svg.append(_svg_text(x0 + 30, y, f'{d:02d}° {SIGN_GLYPHS[_wheel_sign(lon_val)]}{_VS} {m:02d}′',
                                     14, fill=colour, anchor='start'))
                y += 26
            svg.append(_svg_text(x0, y, f"Sect: {_esc_text(chart['sect'])}", 12, fill=colour, anchor='start'))

    svg.append('</svg>')
    return ''.join(svg)


# ---- Direction strips --------------------------------------------------------
# The four distributions as timelines (evaluation B.4): one bar per bound
# tinted by its distributor, the distributor's glyph in it, a full-height
# line where the bound changes and a half tick where only the partner
# does, and the present as a red line. PN IV prints distributions as a
# table with dates (Figure 22) and as an arc on the wheel (Figures 2, 65);
# nothing in the book replaces a timeline, and a student needs one.
# 1200 x 240: the page shows a strip in a
# column about 550 px wide, where a 1600-wide canvas would draw its glyphs at a
# third of their size; the narrower canvas with taller bars puts a
# distributor's glyph at about 12 px on screen instead of 7.
STRIP_WIDTH, STRIP_HEIGHT = 1200, 240
STRIP_TINT = _PALETTE_LIGHT['strip_tint']


# What a palette paints surfaces with: on a plain wheel each of them is the
# ground, and every other name, which draws a line or a letter, is the ink.
_SURFACE_COLOURS = ('bg', 'panel', 'face', 'tints', 'shade', 'bound_tint', 'strip_tint', 'strip_other')


def _plain_palette(palette):
    """A palette's one ink on its one ground, under the same names, so that the
    drawing does not know which it has. The ground is the wheel's own face where
    the palette gives it one, else the picture's ground. No colour is written
    here: both are the palette's."""
    ink, ground = palette['ink'], palette.get('face', palette['bg'])

    def one(colour, value):
        if isinstance(value, dict):
            return {key: colour for key in value}
        return (colour,) * len(value) if isinstance(value, tuple) else colour
    return {name: one(ground if name in _SURFACE_COLOURS else ink, value) for name, value in palette.items()}


def _wheel_palette(theme=None, plain=False):
    """The colours a picture is drawn in. None -- and anything the viewer's
    browser does not report as dark -- is the light palette, the one the app
    uses by default. `plain` is the plain wheel's, which the strips never ask for."""
    palette = _PALETTE_DARK if str(theme).lower() == 'dark' else _PALETTE_LIGHT
    return _plain_palette(palette) if plain else palette


def wheel_look(look, page_theme=None):
    """What a chosen look asks the drawing for: (theme, plain). The page's mode
    is read only by the first; anything else stands on its own ground on any page,
    and a word not among the looks follows the page."""
    return {WHEEL_LOOK_OPTIONS[1]: ('light', False), WHEEL_LOOK_OPTIONS[2]: ('dark', False),
            WHEEL_LOOK_OPTIONS[3]: ('light', True), WHEEL_LOOK_OPTIONS[4]: ('dark', True)}.get(look, (page_theme, False))


def saved_svg(svg):
    """A picture as it leaves the app, with the faces it draws its words in, so
    that it reads the same opened on its own. The page's picture carries only
    the symbol faces; this adds to the renderer's own <style>."""
    return svg.replace('<style>', '<style>' + saved_faces.font_face_css(*saved_faces.PICTURE_FAMILIES), 1)


def generate_distribution_strip_svg(segments, now, unit='years', span=None, title='', theme=None):
    """segments as _pn4_distribute returns them (from/to/distributor/partner/
    partner_aspect); `now` in the strip's unit (completed years, or the day
    of the year) or None; span the bar's full length (120 years, 365 days
    ...). Each bar is <rect class="seg"> with data-from/to/distributor/
    partner; the present is <line class="now">. The segment the present
    falls in is outlined in the present's colour; a bound change is a
    full-height rule, a partner change a tick at the top; a bar too
    narrow for its glyph is left to its tint alone."""
    pal = _wheel_palette(theme)
    if unit not in ('years', 'days'):
        raise ValueError(f"unit must be 'years' or 'days', not {unit!r}")
    segments = list(segments or [])
    if span is None:
        span = max((s['to'] for s in segments), default=1.0)
    span = float(span) or 1.0
    x_left, x_right = 40.0, STRIP_WIDTH - 40.0
    y_top, y_bot = 78.0, 172.0

    def x_of(v):
        return x_left + (x_right - x_left) * max(0.0, min(1.0, v / span))

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {STRIP_WIDTH} {STRIP_HEIGHT}" width="{STRIP_WIDTH}" '
           f'height="{STRIP_HEIGHT}" style="font-family:{_WHEEL_FONT}">',
           f'<style>{_the_engine().font_face_css()}</style>',
           f'<rect width="{STRIP_WIDTH}" height="{STRIP_HEIGHT}" fill="{pal["bg"]}"/>']
    if title:
        svg.append(_svg_text(x_left, 30, _esc_text(title), 22, 'bold', pal['ink'], anchor='start'))
    current = None
    if now is not None:
        current = next((seg for seg in segments if seg['from'] <= now < seg['to']), None)
    rules, prev = [], None
    for seg in segments:
        x0, x1 = x_of(seg['from']), x_of(seg['to'])
        w = max(0.0, x1 - x0)
        tint = pal['strip_tint'].get(seg['distributor'], pal['strip_other'])
        svg.append(f'<rect class="seg" x="{x0:.1f}" y="{y_top}" width="{w:.1f}" height="{y_bot - y_top}" fill="{tint}" '
                   f'data-from="{seg["from"]:.4f}" data-to="{seg["to"]:.4f}" '
                   f'data-distributor="{_esc_attr(seg["distributor"])}" data-partner="{_esc_attr(_the_engine().pn4_result_text(seg["partner"], "none"))}" '
                   f'data-aspect="{_esc_attr(_the_engine().pn4_result_text(seg["partner_aspect"], "none"))}"/>')
        bound_change = prev is None or prev['distributor'] != seg['distributor']
        # The rules go on after the bars so no bar's fill covers a neighbour's edge.
        rules.append(_svg_line(x0, y_top, x0, y_bot if bound_change else y_top + 18,
                               pal['rule'], 1.6 if bound_change else 1.0))
        if w >= 18:
            svg.append(_svg_text((x0 + x1) / 2.0, y_top + 32, _the_engine().POINT_GLYPHS.get(seg['distributor'], '') + _VS, 30,
                                 fill=pal['ink']))
        if w >= 26 and _the_engine().is_unresolved(seg['partner']):
            svg.append(_svg_text((x0 + x1) / 2.0, y_bot - 22, '?', 18, fill=pal['note']))
        elif w >= 26 and seg['partner']:
            # Two or more partners met together (PN IV III.1, 50) are each
            # drawn, aspect and planet, in their order.
            together = isinstance(seg['partner'], _the_engine().PN4Together)
            pairs = zip(seg['partner'], seg['partner_aspect']) if together else ((seg['partner'], seg['partner_aspect']),)
            svg.append(_svg_text((x0 + x1) / 2.0, y_bot - 22,
                                 ''.join(_ASPECT_GLYPH.get(a, '') + _the_engine().POINT_GLYPHS.get(p, '') + _VS for p, a in pairs),
                                 19, fill=pal['note']))
        prev = seg
    svg.extend(rules)
    if current is not None:
        x0, x1 = x_of(current['from']), x_of(current['to'])
        svg.append(f'<rect class="current" x="{x0:.1f}" y="{y_top - 1.5}" width="{max(0.0, x1 - x0):.1f}" '
                   f'height="{y_bot - y_top + 3}" fill="none" stroke="{pal["now"]}" stroke-width="3"/>')
    svg.append(_svg_line(x_left, y_bot, x_right, y_bot, pal['rule'], 1.4))
    tick = 10.0 if unit == 'years' else 30.0
    v = 0.0
    while v <= span + 1e-9:
        x = x_of(v)
        svg.append(_svg_line(x, y_bot, x, y_bot + 8, pal['rule'], 1.0))
        svg.append(_svg_text(x, y_bot + 24, f'{v:g}', 15, fill=pal['ink']))
        v += tick
    svg.append(_svg_text(x_right, y_bot + 50, 'age in completed years' if unit == 'years' else 'day of the year',
                         14, fill=pal['axis_note'], anchor='end'))
    if now is not None and 0.0 <= now <= span:
        x = x_of(now)
        svg.append(f'<line class="now" x1="{x:.1f}" y1="{y_top - 20}" x2="{x:.1f}" y2="{y_bot + 8}" stroke="{pal["now"]}" '
                   f'stroke-width="2.6" data-now="{now:.4f}"/>')
        # The label beside the line, not on it; on whichever side has room.
        # A day prints as the Days page's Now line and its tables print it.
        # Years as the table and the header print them, truncated
        # (pn4_elapsed_text): rounded, "now: age 10.0" would stand in the segment that
        # ends at 10, 9.9999 years elapsed.
        places = _the_engine().pn4_span_places(current, unit)
        label = (f'now: age {_the_engine().pn4_elapsed_text(now, places)}' if unit == 'years'
                 else f'now: day {_the_engine().pn4_day_text(now, places)}')
        at_right = x > (x_left + x_right) / 2.0
        svg.append(_svg_text(x - 8 if at_right else x + 8, y_top - 30, label, 15, 'bold', pal['now'],
                             anchor='end' if at_right else 'start'))
    svg.append('</svg>')
    return ''.join(svg)


def generate_hit_strip_svg(rows, now, span=None, title='', theme=None):
    """The house-master's direction (Sahl, On Nativities 1.23, 2) as a
    strip in the family of generate_distribution_strip_svg: the same
    0-to-span axis in completed years, one tick per target reached
    (<line class="hit"> with data-arc/data-target), labelled with the
    infortune's glyph and the aspect's, alternating above and below the
    axis so neighbours do not collide; the present as <line class="now">.
    `rows` are sahl_house_master_direction's rows (Target, Arc (years))."""
    pal = _wheel_palette(theme)
    rows = list(rows or [])
    if span is None:
        span = max((float(r['Arc (years)']) for r in rows), default=1.0)
    span = float(span) or 1.0
    x_left, x_right = 40.0, STRIP_WIDTH - 40.0
    y_axis = 128.0

    def x_of(v):
        return x_left + (x_right - x_left) * max(0.0, min(1.0, v / span))

    def label_of(target):
        m = re.match(r"(?:the )?(\w+)'s (body|opposition|square|degree)", target)
        if not m:
            return _esc_text(target)
        planet, what = m.group(1), m.group(2)
        glyph = _the_engine().POINT_GLYPHS.get(planet, planet)
        return (glyph + _VS) if what == 'degree' else (_ASPECT_GLYPH.get(what, '') + glyph + _VS)

    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {STRIP_WIDTH} {STRIP_HEIGHT}" width="{STRIP_WIDTH}" '
           f'height="{STRIP_HEIGHT}" style="font-family:{_WHEEL_FONT}">',
           f'<style>{_the_engine().font_face_css()}</style>',
           f'<rect width="{STRIP_WIDTH}" height="{STRIP_HEIGHT}" fill="{pal["bg"]}"/>']
    if title:
        svg.append(_svg_text(x_left, 30, _esc_text(title), 22, 'bold', pal['ink'], anchor='start'))
    svg.append(_svg_line(x_left, y_axis, x_right, y_axis, pal['rule'], 1.4))
    v = 0.0
    while v <= span + 1e-9:
        x = x_of(v)
        svg.append(_svg_line(x, y_axis, x, y_axis + 8, pal['rule'], 1.0))
        svg.append(_svg_text(x, y_axis + 24, f'{v:g}', 15, fill=pal['ink']))
        v += 10.0
    svg.append(_svg_text(x_right, y_axis + 50, 'age in completed years', 14, fill=pal['axis_note'], anchor='end'))
    for i, r in enumerate(sorted(rows, key=lambda r: float(r['Arc (years)']))):
        arc = float(r['Arc (years)'])
        if arc > span:
            continue
        x = x_of(arc)
        above = i % 2 == 0
        y0, y1 = (y_axis - 34, y_axis) if above else (y_axis, y_axis + 34)
        svg.append(f'<line class="hit" x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y1}" stroke="{pal["rule"]}" '
                   f'stroke-width="2" data-arc="{arc:.4f}" data-target="{_esc_attr(r["Target"])}"/>')
        svg.append(f'<circle cx="{x:.1f}" cy="{y_axis}" r="4" fill="{pal["rule"]}"/>')
        svg.append(_svg_text(x, y_axis - 50 if above else y_axis + 54, label_of(str(r['Target'])), 26, fill=pal['ink']))
        # The arc as the direction table prints it, truncated: rounded, "10.0" would stand
        # for the table's 9.99.
        arc_text = (r['Arc (years)'] if isinstance(r['Arc (years)'], str)
                    else f"{math.floor(arc * 100.0) / 100.0:.2f}")
        svg.append(_svg_text(x, y_axis - 74 if above else y_axis + 78, _esc_text(arc_text), 14, fill=pal['note']))
    if now is not None and 0.0 <= now <= span:
        x = x_of(now)
        svg.append(f'<line class="now" x1="{x:.1f}" y1="{y_axis - 86}" x2="{x:.1f}" y2="{y_axis + 8}" stroke="{pal["now"]}" '
                   f'stroke-width="2.6" data-now="{now:.4f}"/>')
        at_right = x > (x_left + x_right) / 2.0
        svg.append(_svg_text(x - 8 if at_right else x + 8, y_axis - 96, f'now: age {_the_engine().pn4_elapsed_text(now)}', 15, 'bold', pal['now'],
                             anchor='end' if at_right else 'start'))
    svg.append('</svg>')
    return ''.join(svg)


__all__ = ['house_style', 'saved_faces', 'math', 're', 'unicodedata', '_esc_attr', '_esc_text', '_isolated', 'WHEEL_LAYOUT_OPTIONS', 'WHEEL_LOOK_OPTIONS', 'wheel_look', 'WHEEL_SIZE',
           'WHEEL_WIDE_WIDTH', '_R_RIM', '_R_WS_IN', '_R_SIGN_IN', '_RING_IN', '_R_GLYPH', '_R_DEG', '_R_SIGN', '_R_MIN', '_R_RX',
           '_R_Q_OUT', '_R_Q_IN', '_R_BOUNDS_BAND', 'LABEL_MIN_SEP', 'LABEL_STAGGER', '_LABEL_EDGE', '_GLYPH_PX', '_GLYPH_SET', '_HUB_INK_R', '_HUB_FLOOR_PX', '_HUB_WRAP_PX', 'TRIPLICITY_TINT',
           '_WHEEL_FONT', '_CUSP_COLOUR', '_AXIS_COLOUR', '_VS', 'SIGN_GLYPHS', '_spread_labels', '_stagger_offsets',
           '_face', '_wheel_dm', '_wheel_sign', '_hub_em', '_hub_rows', 'generate_hybrid_svg', '_M_RIM', '_M_SIGN_IN', '_M_BOUNDS_IN', '_M_HUB_RING',
           '_M_HUB', 'WHEEL_RING_COLOURS', 'WHEEL_SHADE', 'WHEEL_BOUND_TINT', 'WHEEL_ORDER_OPTIONS',
           'WHEEL_VIEW_OPTIONS', '_ASPECT_GLYPH', '_wheel_geometry', '_svg_line', '_svg_text', '_svg_arrowhead',
           '_bounds_ring_svg', '_wheel_points', '_ring_layout', '_draw_ring_points', '_draw_ring_extras',
           'generate_multiwheel_svg', 'STRIP_WIDTH', 'STRIP_HEIGHT', 'STRIP_TINT', '_PALETTE_LIGHT', '_PALETTE_DARK', 'saved_svg',
           '_SURFACE_COLOURS', '_plain_palette', '_wheel_palette', 'generate_distribution_strip_svg', 'generate_hit_strip_svg']
