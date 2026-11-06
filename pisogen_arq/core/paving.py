# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alfonso Rodríguez
"""PisoGen ARQ paving core, Python port of core/paving.js (2026.1.0).

Portable metre-based geometry. No host application objects or filesystem
access. Pieces, ids, hashes and error messages match the JavaScript core so
both hosts lay the same floor; tests/test_golden.py checks it against
results produced by the JavaScript file.
"""
import math

SCHEMA = 'archviz.paving/1'
PATTERNS = ('wood', 'brick', 'tile', 'strip', 'pinwheel',
            'hopscotch_1', 'hopscotch_2', 'hopscotch_3', 'hopscotch_4', 'herringbone', 'chevron', 'basketweave',
            'hexagon', 'octagon', 'adopasto', 'adopasto_reja', 'irregular', 'wedge', 'i_block', 'diamonds')
EPS = 1e-10
_MASK = 0xffffffff
_MISSING = object()


def hypot(*values):
    """Math.hypot as V8 computes it (scaled sum with Kahan compensation), so
    lengths match the JavaScript core to the last bit: with a zero joint a
    point sits exactly on a cut line and one ulp decides its side."""
    values = [abs(v) for v in values]
    top = max(values) if values else 0
    if top == 0 or len(values) == 1:
        return top
    total = compensation = 0.0
    for v in values:
        n = v / top
        summand = n * n - compensation
        preliminary = total + summand
        compensation = (preliminary - total) - summand
        total = preliminary
    return math.sqrt(total) * top


class PavingError(ValueError):
    pass


def _is_num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _is_int(value):
    return _is_num(value) and float(value).is_integer()


def _jstr(value):
    """String(value) as JavaScript writes ids and hash keys."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _get(settings, key, default):
    value = settings.get(key, _MISSING)
    return default if value is _MISSING or value is None else value


def _imul(a, b):
    return ((a & _MASK) * (b & _MASK)) & _MASK


def number(value, name, positive):
    if not _is_num(value) or (value <= 0 if positive else value < 0):
        raise PavingError('Invalid ' + name)
    return value


def area(poly):
    total = 0.0
    n = len(poly)
    for i, p in enumerate(poly):
        q = poly[(i + 1) % n]
        total += p[0] * q[1] - q[0] * p[1]
    return total / 2


def cross(a, b, p):
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def polygon(points):
    if not isinstance(points, (list, tuple)) or len(points) < 3:
        raise PavingError('Invalid polygon')
    result = []
    for p in points:
        if not isinstance(p, (list, tuple)) or len(p) != 2 or not all(_is_num(v) for v in p):
            raise PavingError('Invalid point')
        result.append([p[0], p[1]])
    if abs(area(result)) <= EPS:
        raise PavingError('Degenerate polygon')
    return result


def clip_convex(subject, boundary):
    """Sutherland-Hodgman intersection. The clipping boundary must be convex."""
    output = polygon(subject)
    clip = polygon(boundary)
    if area(clip) < 0:
        clip.reverse()
    n = len(clip)
    for i in range(n):
        if cross(clip[i], clip[(i + 1) % n], clip[(i + 2) % n]) < -EPS:
            raise PavingError('Clipping boundary must be convex')
    i = 0
    while i < n and output:
        a, b, source = clip[i], clip[(i + 1) % n], output
        output = []
        previous = source[-1]
        previous_side = cross(a, b, previous)
        for point in source:
            side = cross(a, b, point)
            if (side >= -EPS) != (previous_side >= -EPS):
                t = previous_side / (previous_side - side)
                output.append([previous[0] + t * (point[0] - previous[0]),
                               previous[1] + t * (point[1] - previous[1])])
            if side >= -EPS:
                output.append([point[0], point[1]])
            previous, previous_side = point, side
        count = len(output)
        output = [p for k, p in enumerate(output)
                  if hypot(p[0] - output[(k + count - 1) % count][0], p[1] - output[(k + count - 1) % count][1]) > EPS]
        i += 1
    return output if len(output) >= 3 and abs(area(output)) > EPS else []


def rectangle(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def inset_convex(shape, distance):
    if not distance:
        return shape
    n = len(shape)
    shifted = []
    for i, p in enumerate(shape):
        before, after = shape[(i + n - 1) % n], shape[(i + 1) % n]
        u = [p[0] - before[0], p[1] - before[1]]
        v = [after[0] - p[0], after[1] - p[1]]
        lu, lv = hypot(*u), hypot(*v)
        u = [c / lu for c in u]
        v = [c / lv for c in v]
        a = [p[0] - u[1] * distance, p[1] + u[0] * distance]
        b = [p[0] - v[1] * distance, p[1] + v[0] * distance]
        det = u[0] * v[1] - u[1] * v[0]
        if abs(det) < 1e-12:
            raise PavingError('Invalid pattern corner')
        t = ((b[0] - a[0]) * v[1] - (b[1] - a[1]) * v[0]) / det
        shifted.append([a[0] + u[0] * t, a[1] + u[1] * t])
    bad = area(shifted) <= EPS
    if not bad:
        for i, p in enumerate(shifted):
            q, a, b = shifted[(i + 1) % n], shape[i], shape[(i + 1) % n]
            if (q[0] - p[0]) * (b[0] - a[0]) + (q[1] - p[1]) * (b[1] - a[1]) <= EPS:
                bad = True
                break
    if bad:
        raise PavingError('Joint eliminates a pattern piece')
    return shifted


# Placement (ALFA33): the generators always work in pattern space, rows along
# X from (0, 0). T maps pattern space onto the face: rotate by the reference
# edge plus the user angle, then move to the chosen origin.
ORIGIN_MODES = ('first_vertex', 'centroid', 'corner_bl', 'corner_br', 'corner_tl', 'corner_tr', 'picked')


class _Placement:
    identity = False


def _sign(v):
    return (v > 0) - (v < 0)


def placement(data):
    s = data.get('settings') or {}
    angle = _get(s, 'pattern_angle_deg', 0)
    align = s.get('align_mode') or 'first_edge'
    mode = s.get('origin_mode') or 'first_vertex'
    anchor = s.get('origin_anchor') or 'corner'
    off = [s.get('offset_x_m') or 0, s.get('offset_y_m') or 0]
    if not _is_num(angle) or abs(angle) > 360:
        raise PavingError('Invalid pattern angle')
    if align not in ('first_edge', 'longest_edge'):
        raise PavingError('Invalid align mode')
    if mode not in ORIGIN_MODES:
        raise PavingError('Invalid origin mode')
    if anchor not in ('corner', 'center'):
        raise PavingError('Invalid origin anchor')
    if not all(_is_num(v) and abs(v) <= 100 for v in off):
        raise PavingError('Invalid pattern offset')
    place = _Placement()
    if angle == 0 and align == 'first_edge' and mode == 'first_vertex' and anchor == 'corner' and not off[0] and not off[1]:
        place.identity = True
        return place
    boundary = polygon(data['boundary'])
    base = 0.0
    if align == 'longest_edge':
        best = -1
        for i, p in enumerate(boundary):
            q = boundary[(i + 1) % len(boundary)]
            length = hypot(q[0] - p[0], q[1] - p[1])
            if length > best + 1e-9:
                best = length
                base = math.atan2(q[1] - p[1], q[0] - p[0])
    theta = base + angle * math.pi / 180

    def snap(v):
        if abs(v) < 1e-15:
            return 0
        if abs(abs(v) - 1) < 1e-15:
            return _sign(v)
        return v

    c, sn = snap(math.cos(theta)), snap(math.sin(theta))

    def rot(p):
        return [c * p[0] - sn * p[1], sn * p[0] + c * p[1]]

    def inv(p):
        return [c * p[0] + sn * p[1], -sn * p[0] + c * p[1]]

    origin = [0, 0]
    if mode == 'centroid':
        # Area centroid of the face, holes and L shapes included.
        total = cx = cy = 0.0
        for cell in data.get('domain_triangles_m') or [boundary]:
            a = area(cell)
            sx = sy = 0.0
            for i, p in enumerate(cell):
                q = cell[(i + 1) % len(cell)]
                k = p[0] * q[1] - q[0] * p[1]
                sx += (p[0] + q[0]) * k
                sy += (p[1] + q[1]) * k
            total += a
            cx += sx / 6
            cy += sy / 6
        origin = [cx / total, cy / total]
    elif mode.startswith('corner_'):
        # Corner of the face's bounding rectangle, measured along the pattern axes.
        local = [inv(p) for p in boundary]
        xs, ys = [p[0] for p in local], [p[1] for p in local]
        origin = rot([min(xs) if mode.endswith('l') else max(xs), min(ys) if mode[7] == 'b' else max(ys)])
    elif mode == 'picked':
        point = s.get('origin_point_m')
        if not isinstance(point, (list, tuple)) or len(point) != 2 or not all(_is_num(v) for v in point):
            raise PavingError('Invalid origin point')
        origin = [point[0], point[1]]
    # Centre anchor: the module centre (piece centre for rows) lands on the origin.
    half = [0, 0]
    if anchor == 'center':
        if data.get('pattern') in ('wood', 'brick', 'tile', 'strip', 'herringbone', 'chevron'):
            half = [(s.get('length_m') or 0) / 2, (s.get('width_m') or 0) / 2]
        else:
            half = [(s.get('side_m') or 0) / 2, (s.get('side_m') or 0) / 2]
    shift = rot([off[0] - half[0], off[1] - half[1]])
    t = [origin[0] + shift[0], origin[1] + shift[1]]
    place.rotated = c != 1 or sn != 0
    place.rot = rot
    place.t = t
    place.to_pattern = lambda p: inv([p[0] - t[0], p[1] - t[1]])

    def to_face(p):
        r = rot(p)
        return [r[0] + t[0], r[1] + t[1]]

    place.to_face = to_face
    return place


def place_piece(piece, place):
    """Rectangular pieces map their texture with an axis-aligned box. Once the
    pattern turns, the same mapping becomes a frame whose cross axis keeps v
    exactly where the box put it (no mirrored boards)."""
    result = dict(piece)
    result['polygons_m'] = [[place.to_face(p) for p in poly] for poly in piece['polygons_m']]
    result['polygon_m'] = result['polygons_m'][0]
    if piece.get('grain_axis'):
        result['grain_axis'] = place.rot(piece['grain_axis'])
    frame = piece.get('texture_frame_m')
    if piece.get('texture_box_m'):
        x, y, w, h = piece['texture_box_m']
        if not place.rotated:
            result['texture_box_m'] = [x + place.t[0], y + place.t[1], w, h]
        else:
            along = piece['grain_axis'][0] == 1
            a = [1, 0] if along else [0, 1]
            cr = [0, 1] if along else [1, 0]
            frame = {'axis': a, 'cross_axis': cr, 'origin_uv_m': [x * a[0] + y * a[1], x * cr[0] + y * cr[1]],
                     'length_m': w if along else h}
            del result['texture_box_m']
    if frame:
        a = place.rot(frame['axis'])
        cr = place.rot(frame['cross_axis']) if frame.get('cross_axis') else [-a[1], a[0]]
        t = place.t
        placed = dict(frame)
        placed['axis'] = a
        placed['origin_uv_m'] = [frame['origin_uv_m'][0] + t[0] * a[0] + t[1] * a[1],
                                 frame['origin_uv_m'][1] + t[0] * cr[0] + t[1] * cr[1]]
        if frame.get('cross_axis'):
            placed['cross_axis'] = cr
        result['texture_frame_m'] = placed
    return result


def continuous_texture(output, data, place):
    """Continuous texture (ALFA36): every piece maps the image from the same
    floor frame (pattern origin and axes), so the drawing runs across joints."""
    s = data.get('settings') or {}
    if s.get('texture_mode') != 'continuous':
        return output
    width = _get(s, 'texture_width_m', 0.5)
    if not _is_num(width) or width <= 0:
        raise PavingError('Invalid texture width')
    a = [1, 0] if place.identity else place.rot([1, 0])
    c = [0, 1] if place.identity else place.rot([0, 1])
    t = [0, 0] if place.identity else place.t
    frame = {'axis': a, 'cross_axis': c, 'origin_uv_m': [t[0] * a[0] + t[1] * a[1], t[0] * c[0] + t[1] * c[1]],
             'length_m': width}
    pieces = []
    for piece in output['pieces']:
        result = dict(piece)
        result['texture_frame_m'] = dict(frame)
        result.pop('texture_box_m', None)
        pieces.append(result)
    return dict(output, pieces=pieces)


def lift(output, data):
    """Height variation (ALFA38): each piece rises a seeded amount between 0
    and lift_max_m. Grass cells keep their own height."""
    s = data.get('settings') or {}
    top = _get(s, 'lift_max_m', 0)
    if not _is_num(top) or top < 0 or top > 0.01:
        raise PavingError('Invalid lift')
    if not top:
        return output
    seed = _get(s, 'layout_seed', 1)
    grass = output['pattern'] in ('adopasto', 'adopasto_reja')
    pieces = [piece if grass and piece['role'] == 'insert' else
              dict(piece, lift_m=top * hash01('lift:' + _jstr(seed) + ':' + piece['id']))
              for piece in output['pieces']]
    return dict(output, pieces=pieces)


def generate(data):
    if not data or data.get('schema') != SCHEMA:
        raise PavingError('Unsupported schema')
    place = placement(data)
    if place.identity:
        return lift(continuous_texture(generate_local(data), data, place), data)
    local_input = dict(data)
    local_input['boundary'] = [place.to_pattern(p) for p in data['boundary']]
    if data.get('domain_triangles_m'):
        local_input['domain_triangles_m'] = [[place.to_pattern(p) for p in cell] for cell in data['domain_triangles_m']]
    local = generate_local(local_input)
    placed = dict(local, pieces=[place_piece(piece, place) for piece in local['pieces']])
    return lift(continuous_texture(placed, data, place), data)


def hash01(text):
    h = 0x811c9dc5
    for ch in text:
        # charCodeAt works on UTF-16 code units.
        for unit in _utf16_units(ch):
            h ^= unit
            h = _imul(h, 0x01000193)
    # Final avalanche (murmur3 fmix32): FNV alone barely separates similar keys.
    h ^= h >> 16
    h = _imul(h, 0x85ebca6b)
    h ^= h >> 13
    h = _imul(h, 0xc2b2ae35)
    h ^= h >> 16
    return (h & _MASK) / 4294967296


def _utf16_units(ch):
    code = ord(ch)
    if code < 0x10000:
        return (code,)
    code -= 0x10000
    return (0xd800 + (code >> 10), 0xdc00 + (code & 0x3ff))


def _segment_distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    k = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length)) if length else 0
    return hypot(p[0] - a[0] - k * dx, p[1] - a[1] - k * dy)


def _polygons_distance(p, q):
    best = math.inf
    for one, two in ((p, q), (q, p)):
        for poly in two:
            for i in range(len(poly)):
                a, b = poly[i], poly[(i + 1) % len(poly)]
                for other in one:
                    for point in other:
                        best = min(best, _segment_distance(point, a, b))
    return best


def assign_materials(pieces, settings):
    """Material slots (ALFA36). Returns None for the classic draw (100 %
    random, neighbours ignored) so the adapter keeps its per-piece hash."""
    s = settings or {}
    pct = _get(s, 'material_randomness_pct', 100)
    avoid = bool(s.get('material_avoid_repeat'))
    if not _is_num(pct) or pct < 0 or pct > 100:
        raise PavingError('Invalid material randomness')
    assignment = _get(s, 'material_assignment', 'random')
    if assignment not in ('random', 'sequence'):
        raise PavingError('Invalid material assignment')
    count = max(1, len(s.get('main_materials') or []))
    seed = _jstr(_get(s, 'material_seed', 1))
    # In sequence (2026.1) the materials repeat in order, piece after piece.
    if assignment == 'sequence':
        return [i % count for i in range(len(pieces))]
    if pct == 100 and not avoid:
        return None
    random = [hash01('rand:' + seed + ':' + p['id']) * 100 < pct for p in pieces]
    slots = [math.floor(hash01('pick:' + seed + ':' + p['id']) * count) if random[i] else 0 for i, p in enumerate(pieces)]
    if not avoid or count < 2:
        return slots
    reach = max(s.get('joint_m') or 0, s.get('joint_end_m') or 0) + 0.001
    boxes = []
    for p in pieces:
        pts = [q for poly in p['polygons_m'] for q in poly]
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        boxes.append([min(xs) - reach, min(ys) - reach, max(xs) + reach, max(ys) + reach])
    size = sum(max(b[2] - b[0], b[3] - b[1]) for b in boxes) / max(1, len(boxes)) or 1
    grid = {}

    def cells(b):
        out = []
        for x in range(math.floor(b[0] / size), math.floor(b[2] / size) + 1):
            for y in range(math.floor(b[1] / size), math.floor(b[3] / size) + 1):
                out.append((x, y))
        return out

    for i, b in enumerate(boxes):
        for key in cells(b):
            grid.setdefault(key, []).append(i)

    # Pieces using their own insert material never compete with the main list.
    def pool(p):
        return 'insert' if p['role'] == 'insert' and s.get('insert_enabled') else 'main'

    for i, piece in enumerate(pieces):
        if not random[i] or pool(piece) != 'main':
            continue
        taken, seen = set(), set()
        for key in cells(boxes[i]):
            for j in grid[key]:
                # Earlier pieces are settled; later ones only if they keep the first material.
                if j == i or (j > i and random[j]) or j in seen or pool(pieces[j]) != 'main':
                    continue
                seen.add(j)
                b, a = boxes[j], boxes[i]
                if b[0] > a[2] or b[2] < a[0] or b[1] > a[3] or b[3] < a[1]:
                    continue
                if _polygons_distance(piece['polygons_m'], pieces[j]['polygons_m']) <= reach:
                    taken.add(slots[j])
        k = 0
        while k < count and slots[i] in taken:
            slots[i] = (slots[i] + 1) % count
            k += 1
    return slots


def _bounds(shape):
    xs, ys = [p[0] for p in shape], [p[1] for p in shape]
    return min(xs), min(ys), max(xs), max(ys)


def _nearby_index(domain):
    """Bucket the domain cells on a grid so each candidate only clips nearby
    cells. Candidates return in domain order, so fragment order is unchanged."""
    if len(domain) <= 8:
        return lambda *_: domain
    g = min(256, math.ceil(math.sqrt(len(domain))))
    boxes = [_bounds(cell) for cell in domain]
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    sx = (x1 - x0) / g or 1
    sy = (y1 - y0) / g or 1

    def col(x):
        return max(0, min(g - 1, math.floor((x - x0) / sx)))

    def row(y):
        return max(0, min(g - 1, math.floor((y - y0) / sy)))

    buckets = [[] for _ in range(g * g)]
    for i, box in enumerate(boxes):
        for r in range(row(box[1]), row(box[3]) + 1):
            for c in range(col(box[0]), col(box[2]) + 1):
                buckets[r * g + c].append(i)

    def nearby(qx0, qy0, qx1, qy1):
        found = set()
        for r in range(row(qy0), row(qy1) + 1):
            for c in range(col(qx0), col(qx1) + 1):
                found.update(buckets[r * g + c])
        return [domain[i] for i in sorted(found)]

    return nearby


def generate_local(data):
    if not data or data.get('schema') != SCHEMA:
        raise PavingError('Unsupported schema')
    if data.get('pattern') not in PATTERNS:
        raise PavingError('Unsupported pattern')
    if data.get('unit') != 'm':
        raise PavingError('Core requires metres')
    boundary = polygon(data.get('boundary'))
    # A host tessellator can supply non-overlapping triangles for a concave
    # surface with holes. The host must check their total area against its face.
    cells = data.get('domain_triangles_m')
    if cells is not None and (not isinstance(cells, (list, tuple)) or not cells or len(cells) > 10000):
        raise PavingError('Invalid domain triangulation')
    if cells is not None:
        domain = []
        for cell in cells:
            if not isinstance(cell, (list, tuple)) or len(cell) != 3:
                raise PavingError('Domain cell must be a triangle')
            domain.append(polygon(cell))
    else:
        domain = [boundary]
        if data.get('holes'):
            raise PavingError('Holes require a domain triangulation')
        clip_convex(boundary, boundary)
    nearby = _nearby_index(domain)
    work = {'clip': 0, 'visits': 0}

    def clip_tick():
        work['clip'] += 1
        if work['clip'] > 2000000:
            raise PavingError('Clipping work limit exceeded')

    min_x, min_y, max_x, max_y = _bounds(boundary)
    settings = data.get('settings') or {}
    gap = number(_get(settings, 'joint_m', 0.003), 'joint', False)
    limit = data.get('piece_limit', 25000)
    if not _is_int(limit) or limit < 1 or limit > 200000:
        raise PavingError('Invalid limit')
    limit = int(limit)
    pieces = []

    def visit():
        work['visits'] += 1
        if work['visits'] > limit * 20:
            raise PavingError('Candidate limit exceeded')

    def fragments_of(shapes):
        fragments = []
        for shape in shapes:
            for cell in nearby(*_bounds(shape)):
                clip_tick()
                clipped = clip_convex(shape, cell)
                if clipped:
                    fragments.append(clipped)
        return fragments

    def fragments_box(shape, x, y, right, top):
        fragments = []
        for cell in nearby(x, y, right, top):
            clip_tick()
            if (all(p[0] < x for p in cell) or all(p[0] > right for p in cell) or
                    all(p[1] < y for p in cell) or all(p[1] > top for p in cell)):
                continue
            clipped = clip_convex(shape, cell)
            if clipped:
                fragments.append(clipped)
        return fragments

    def push(piece):
        if len(pieces) >= limit:
            raise PavingError('Piece limit exceeded')
        pieces.append(piece)

    def emit(id_, x, y, w, h, role, inset, box=None, nominal=None):
        visit()
        if inset:
            x += gap / 2
            y += gap / 2
            w -= gap
            h -= gap
        if w <= EPS or h <= EPS:
            raise PavingError('Joint eliminates a piece')
        if x >= max_x or y >= max_y or x + w <= min_x or y + h <= min_y:
            return
        fragments = fragments_box(rectangle(x, y, w, h), x, y, x + w, y + h)
        if not fragments:
            return
        # texture_box_m keeps the uncut rectangle so a cut piece shows a crop of
        # the image instead of squeezing the whole image into its remainder.
        along = box[2] >= box[3] if box else w >= h
        push({'id': id_, 'role': role, 'polygon_m': fragments[0], 'polygons_m': fragments,
              'grain_axis': [1, 0] if along else [0, 1], 'texture_box_m': box or [x, y, w, h],
              'nominal_area_m2': w * h if nominal is None else nominal})

    def emit_shape(id_, raw, axis, nominal_length, role='main', inset_distance=None):
        visit()
        shape = inset_convex(raw, gap / 2 if inset_distance is None else inset_distance)
        x, y, right, top = _bounds(shape)
        if x >= max_x or y >= max_y or right <= min_x or top <= min_y:
            return
        fragments = fragments_box(shape, x, y, right, top)
        if not fragments:
            return
        projected = [[p[0] * axis[0] + p[1] * axis[1], -p[0] * axis[1] + p[1] * axis[0]] for p in shape]
        push({'id': id_, 'role': role, 'polygon_m': fragments[0], 'polygons_m': fragments, 'grain_axis': axis,
              'texture_frame_m': {'axis': axis, 'origin_uv_m': [min(p[0] for p in projected), min(p[1] for p in projected)],
                                  'length_m': nominal_length},
              'nominal_area_m2': abs(area(shape))})

    def composite(id_, shapes, role, origin, length, depth=None):
        visit()
        fragments = fragments_of(shapes)
        if not fragments:
            return
        piece = {'id': id_, 'role': role, 'polygon_m': fragments[0], 'polygons_m': fragments, 'grain_axis': [1, 0],
                 'texture_frame_m': {'axis': [1, 0], 'origin_uv_m': origin, 'length_m': length},
                 'nominal_area_m2': sum(abs(area(q)) for q in shapes)}
        if depth is not None:
            piece['depth_m'] = depth
        push(piece)

    pattern = data['pattern']
    if pattern == 'irregular':
        _irregular(settings, gap, limit, (min_x, min_y, max_x, max_y), emit_shape, clip_tick)
    elif pattern == 'adopasto_reja':
        # Visual approximation: five-cell cross, repeated on a pentomino lattice.
        # side_m is the actual overall concrete dimension; joint adds to lattice.
        side = number(_get(settings, 'side_m', .465), 'reja side', True)
        hole = number(_get(settings, 'reja_opening_m', .085), 'reja opening', True)
        chamfer = number(_get(settings, 'reja_chamfer_m', .015), 'reja corner cut', False)
        depth = number(_get(settings, 'depth_m', .08), 'depth', True)
        recess = number(_get(settings, 'grass_recess_m', .01), 'grass recess', False)
        cell = (side + gap) / 3
        w = cell - gap
        a = w / 2
        if w - hole < .002 or hole < .001 or depth - recess < .001 or chamfer > (w - hole) / 2 - .001:
            raise PavingError('Reja requiere celdas y altura de pasto de 1 mm, nervios de 1 mm y recorte menor que el marco.')
        corners = [[(2 * x + y) / (5 * cell), (-x + 2 * y) / (5 * cell)]
                   for x, y in rectangle(min_x - side, min_y - side, max_x - min_x + 2 * side, max_y - min_y + 2 * side)]
        i0, i1 = math.floor(min(p[0] for p in corners)), math.ceil(max(p[0] for p in corners))
        j0, j1 = math.floor(min(p[1] for p in corners)), math.ceil(max(p[1] for p in corners))
        if (i1 - i0 + 1) * (j1 - j0 + 1) * 6 > limit * 20:
            raise PavingError('Candidate limit exceeded')
        crosses = [[0, 0], [-1, 0], [1, 0], [0, -1], [0, 1]]
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                cx, cy = (2 * i - j) * cell, (i + 2 * j) * cell
                if cx + side / 2 <= min_x or cx - side / 2 >= max_x or cy + side / 2 <= min_y or cy - side / 2 >= max_y:
                    continue
                concrete, grass = [], []
                for k, (dx, dy) in enumerate(crosses):
                    hx, hy = cx + dx * cell, cy + dy * cell
                    x0, x1, y0, y1 = hx - a, hx + a, hy - a, hy + a
                    # Shared edges meet the centre; only the outer cross boundary has a joint.
                    if dx == 1:
                        x0 = cx + a
                    if dx == -1:
                        x1 = cx - a
                    if dy == 1:
                        y0 = cy + a
                    if dy == -1:
                        y1 = cy - a
                    outline = rectangle(x0, y0, x1 - x0, y1 - y0)
                    if chamfer and k:
                        c = chamfer
                        if dx == 1:
                            outline = [[x0, y0], [x1 - c, y0], [x1, y0 + c], [x1, y1 - c], [x1 - c, y1], [x0, y1]]
                        if dx == -1:
                            outline = [[x0 + c, y0], [x1, y0], [x1, y1], [x0 + c, y1], [x0, y1 - c], [x0, y0 + c]]
                        if dy == 1:
                            outline = [[x0, y0], [x1, y0], [x1, y1 - c], [x1 - c, y1], [x0 + c, y1], [x0, y1 - c]]
                        if dy == -1:
                            outline = [[x0 + c, y0], [x1 - c, y0], [x1, y0 + c], [x1, y1], [x0, y1], [x0, y0 + c]]
                    l, r, b, t = hx - hole / 2, hx + hole / 2, hy - hole / 2, hy + hole / 2
                    for rect in (rectangle(x0, y0, x1 - x0, b - y0), rectangle(x0, t, x1 - x0, y1 - t),
                                 rectangle(x0, b, l - x0, hole), rectangle(r, b, x1 - r, hole)):
                        clipped = clip_convex(rect, outline)
                        if clipped:
                            concrete.append(clipped)
                    grass.append(rectangle(l, b, hole, hole))
                base = _jstr(i) + ':' + _jstr(j)
                composite(base + ':frame', concrete, 'main', [cx - side / 2, cy - side / 2], side)
                for k, shape in enumerate(grass):
                    gx, gy = cx + crosses[k][0] * cell, cy + crosses[k][1] * cell
                    composite(base + ':grass:' + str(k), [shape], 'insert', [gx - hole / 2, gy - hole / 2], hole, depth - recess)
    elif pattern == 'adopasto':
        side = number(_get(settings, 'side_m', .20), 'module', True)
        band = number(_get(settings, 'grass_frame_m', .03), 'concrete frame', True)
        depth = number(_get(settings, 'depth_m', .08), 'depth', True)
        recess = number(_get(settings, 'grass_recess_m', .01), 'grass recess', False)
        outer = side - gap
        opening = outer - 2 * band
        if band < .001 or opening < .001 or depth - recess < .001:
            raise PavingError('Adopasto requiere marco, celda y altura de pasto de al menos 1 mm.')
        lo_i, hi_i = math.floor(min_x / side), math.ceil(max_x / side)
        lo_j, hi_j = math.floor(min_y / side), math.ceil(max_y / side)
        if (hi_i - lo_i + 1) * (hi_j - lo_j + 1) * 2 > limit * 20:
            raise PavingError('Candidate limit exceeded')
        for j in range(lo_j, hi_j + 1):
            for i in range(lo_i, hi_i + 1):
                x, y = i * side + gap / 2, j * side + gap / 2
                if x >= max_x or y >= max_y or x + outer <= min_x or y + outer <= min_y:
                    continue
                base = _jstr(i) + ':' + _jstr(j)
                composite(base + ':frame', [
                    rectangle(x, y, outer, band), rectangle(x, y + outer - band, outer, band),
                    rectangle(x, y + band, band, opening), rectangle(x + outer - band, y + band, band, opening)
                ], 'main', [x, y], outer)
                composite(base + ':grass', [rectangle(x + band, y + band, opening, opening)], 'insert',
                          [x + band, y + band], opening, depth - recess)
    elif pattern == 'octagon':
        side = number(_get(settings, 'side_m', .12), 'octagon side', True)
        raw_side = side + gap * math.tan(math.pi / 8)
        pitch = (1 + math.sqrt(2)) * raw_side
        cut = raw_side / math.sqrt(2)
        insert_side = raw_side - gap
        if insert_side <= EPS:
            raise PavingError('La junta elimina los insertos de Octágono.')
        lo_i, hi_i = math.floor(min_x / pitch) - 1, math.ceil(max_x / pitch) + 1
        lo_j, hi_j = math.floor(min_y / pitch) - 1, math.ceil(max_y / pitch) + 1
        if (hi_i - lo_i + 1) * (hi_j - lo_j + 1) * 2 > limit * 20:
            raise PavingError('Candidate limit exceeded')
        diagonal = [math.sqrt(0.5), math.sqrt(0.5)]
        for j in range(lo_j, hi_j + 1):
            for i in range(lo_i, hi_i + 1):
                x, y = i * pitch, j * pitch
                base = _jstr(i) + ':' + _jstr(j)
                emit_shape(base + ':main', [[x + cut, y], [x + pitch - cut, y], [x + pitch, y + cut], [x + pitch, y + pitch - cut],
                                            [x + pitch - cut, y + pitch], [x + cut, y + pitch], [x, y + pitch - cut], [x, y + cut]],
                           [1, 0], pitch - gap)
                emit_shape(base + ':insert', [[x - cut, y], [x, y - cut], [x + cut, y], [x, y + cut]],
                           diagonal, insert_side, 'insert')
    elif pattern == 'hexagon':
        # Regular flat-top hexagons. Expand the lattice before the half-joint
        # inset so side_m remains the actual finished side length.
        side = number(_get(settings, 'side_m', .15), 'hexagon side', True)
        radius = side + gap / math.sqrt(3)
        pitch_y = math.sqrt(3) * radius
        lo_i, hi_i = math.floor(min_x / (1.5 * radius)) - 2, math.ceil(max_x / (1.5 * radius)) + 2
        rows = math.ceil((max_y - min_y) / pitch_y) + 6
        if not math.isfinite(radius) or (hi_i - lo_i + 1) * rows > limit * 20:
            raise PavingError('Candidate limit exceeded')
        for i in range(lo_i, hi_i + 1):
            lo_j, hi_j = math.floor(min_y / pitch_y - i / 2) - 2, math.ceil(max_y / pitch_y - i / 2) + 2
            for j in range(lo_j, hi_j + 1):
                x, y = 1.5 * radius * i, pitch_y * (j + i / 2)
                shape = [[x + radius * math.cos(k * math.pi / 3), y + radius * math.sin(k * math.pi / 3)] for k in range(6)]
                emit_shape(_jstr(i) + ':' + _jstr(j), shape, [1, 0], 2 * side)
    elif pattern == 'basketweave':
        # Square pitch includes the surrounding joint; three equal slats fill each block.
        side = number(_get(settings, 'side_m', .30), 'side', True)
        if side / 3 <= gap:
            raise PavingError('La junta elimina las tablas de Cestería.')
        lo_i, hi_i = math.floor(min_x / side), math.ceil(max_x / side)
        lo_j, hi_j = math.floor(min_y / side), math.ceil(max_y / side)
        if (hi_i - lo_i + 1) * (hi_j - lo_j + 1) * 3 > limit * 20:
            raise PavingError('Candidate limit exceeded')
        for j in range(lo_j, hi_j + 1):
            for i in range(lo_i, hi_i + 1):
                horizontal = (i + j) % 2 == 0
                for k in range(3):
                    emit_shape(_jstr(i) + ':' + _jstr(j) + ':' + str(k),
                               rectangle(i * side + (0 if horizontal else k * side / 3), j * side + (k * side / 3 if horizontal else 0),
                                         side if horizontal else side / 3, side / 3 if horizontal else side),
                               [1, 0] if horizontal else [0, 1], side - gap)
    elif pattern in ('herringbone', 'chevron'):
        length = number(_get(settings, 'length_m', .60), 'length', True)
        width = number(_get(settings, 'width_m', .10), 'width', True)
        if length <= width:
            raise PavingError('El largo debe ser mayor que el ancho en Espiga y Chevron.')
        if pattern == 'herringbone':
            pitch_length, pitch_width = length + gap, width + gap
            padding = pitch_length + pitch_width
            det = 2 * pitch_length * pitch_width
            indices = [[(p[0] + p[1]) / (2 * pitch_length), (p[1] - p[0]) / (2 * pitch_width)]
                       for p in rectangle(min_x - padding, min_y - padding, max_x - min_x + 2 * padding, max_y - min_y + 2 * padding)]
            lo_i, hi_i = math.floor(min(p[0] for p in indices)), math.ceil(max(p[0] for p in indices))
            lo_j, hi_j = math.floor(min(p[1] for p in indices)), math.ceil(max(p[1] for p in indices))
            if not math.isfinite(det) or (hi_i - lo_i + 1) * (hi_j - lo_j + 1) * 2 > limit * 20:
                raise PavingError('Candidate limit exceeded')
            for j in range(lo_j, hi_j + 1):
                for i in range(lo_i, hi_i + 1):
                    x, y = pitch_length * i - pitch_width * j, pitch_length * i + pitch_width * j
                    base = _jstr(i) + ':' + _jstr(j)
                    emit_shape(base + ':h', rectangle(x, y, pitch_length, pitch_width), [1, 0], length)
                    emit_shape(base + ':v', rectangle(x + pitch_length, y, pitch_width, pitch_length), [0, 1], length)
        else:
            angle = _get(settings, 'chevron_angle_deg', 45)
            if not _is_num(angle) or angle < 15 or angle > 75:
                raise PavingError('El ángulo de Chevron debe estar entre 15 y 75 grados.')
            theta = angle * math.pi / 180
            c, s = math.cos(theta), math.sin(theta)
            a = length * c + gap
            rise = a * s / c
            h = (width + gap) / c
            lo_i, hi_i = math.floor(min_x / (2 * a)) - 1, math.ceil(max_x / (2 * a)) + 1
            lo_j, hi_j = math.floor((min_y - rise) / h) - 1, math.ceil(max_y / h) + 1
            if (hi_i - lo_i + 1) * (hi_j - lo_j + 1) * 2 > limit * 20:
                raise PavingError('Candidate limit exceeded')
            for j in range(lo_j, hi_j + 1):
                for i in range(lo_i, hi_i + 1):
                    x, y = i * 2 * a, j * h
                    base = _jstr(i) + ':' + _jstr(j)
                    emit_shape(base + ':left', [[x, y], [x + a, y + rise], [x + a, y + rise + h], [x, y + h]], [c, s], length)
                    emit_shape(base + ':right', [[x + a, y + rise], [x + 2 * a, y], [x + 2 * a, y + h], [x + a, y + rise + h]], [c, -s], length)
    elif pattern == 'wedge':
        # Cuña (ALFA40): rows of trapezoids, wide base down, alternating with
        # inverted pieces whose narrow base is wedge_inverse_m (0 = triangle).
        big = number(_get(settings, 'wedge_long_m', .20), 'wedge long base', True)
        small = number(_get(settings, 'wedge_short_m', .10), 'wedge short base', False)
        h = number(_get(settings, 'wedge_height_m', .15), 'wedge height', True)
        q = number(_get(settings, 'wedge_inverse_m', 0), 'wedge inverse base', False)
        if small > big + 1e-12 or (big - small < 1e-12 and q <= 0):
            raise PavingError('Cuña: la base menor no puede superar la mayor, y con bases iguales la pieza invertida necesita base.')
        s = (big - small) / 2
        shift = gap * hypot(s, h) / h
        pitch_x, pitch_y = big + q + 2 * shift, h + gap
        i0, i1 = math.floor((min_x - pitch_x) / pitch_x) - 1, math.ceil(max_x / pitch_x) + 1
        j0, j1 = math.floor(min_y / pitch_y) - 1, math.ceil(max_y / pitch_y) + 1
        if (i1 - i0 + 1) * (j1 - j0 + 1) * 2 > limit * 20:
            raise PavingError('Candidate limit exceeded')
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                x, y = i * pitch_x, j * pitch_y
                xq = x + big + shift
                base = _jstr(j) + ':' + _jstr(i)
                emit_shape(base + ':a', [[x, y], [x + big, y], [x + big - s, y + h], [x + s, y + h]] if small > 0 else
                           [[x, y], [x + big, y], [x + s, y + h]], [1, 0], big, 'main', 0)
                emit_shape(base + ':b', [[xq, y], [xq + q, y], [xq + q + s, y + h], [xq - s, y + h]] if q > 0 else
                           [[xq, y], [xq + s, y + h], [xq - s, y + h]], [1, 0], big, 'insert', 0)
    elif pattern == 'i_block':
        # Bloque I (ALFA40): interlocking I pavers. Alternate columns drop half
        # a module so each flange fills the neighbour's recess.
        big_h = number(_get(settings, 'iblock_length_m', .20), 'I length', True)
        big_w = number(_get(settings, 'iblock_width_m', .165), 'I width', True)
        web = number(_get(settings, 'iblock_web_m', .11), 'I web', True)
        f = (big_h - 3 * gap) / 4
        r = (big_w - web) / 2
        if r <= 1e-9 or f < .001:
            raise PavingError('Bloque I: el alma debe ser más angosta que las alas y el largo debe dejar alas de al menos 1 mm con la junta.')
        pitch_x, pitch_y = (big_w + web) / 2 + gap, big_h + gap
        c0, c1 = math.floor((min_x - big_w) / pitch_x) - 1, math.ceil(max_x / pitch_x) + 1
        k0, k1 = math.floor((min_y - big_h) / pitch_y) - 2, math.ceil(max_y / pitch_y) + 1
        if (c1 - c0 + 1) * (k1 - k0 + 1) > limit * 20:
            raise PavingError('Candidate limit exceeded')
        for c in range(c0, c1 + 1):
            for k in range(k0, k1 + 1):
                x, y = c * pitch_x, k * pitch_y + (c % 2) * pitch_y / 2
                if x >= max_x or y >= max_y or x + big_w <= min_x or y + big_h <= min_y:
                    continue
                visit()
                # Two flanges and the web; the adapter merges them into one top face.
                parts = [rectangle(x, y, big_w, f), rectangle(x + r, y + f, web, big_h - 2 * f), rectangle(x, y + big_h - f, big_w, f)]
                fragments = fragments_of(parts)
                if not fragments:
                    continue
                push({'id': _jstr(c) + ':' + _jstr(k), 'role': 'main', 'polygon_m': fragments[0], 'polygons_m': fragments,
                      'grain_axis': [1, 0], 'texture_frame_m': {'axis': [1, 0], 'origin_uv_m': [x, y], 'length_m': big_h},
                      'nominal_area_m2': sum(abs(area(p)) for p in parts)})
    elif pattern == 'diamonds':
        # Diamantes (ALFA40): rhombi in two alternating roles (checkerboard).
        side = number(_get(settings, 'side_m', .20), 'diamond side', True)
        angle = _get(settings, 'diamond_angle_deg', 90)
        if not _is_num(angle) or angle < 30 or angle > 90:
            raise PavingError('El ángulo del rombo debe estar entre 30 y 90 grados.')
        t = angle * math.pi / 180
        a, b = side * math.cos(t / 2), side * math.sin(t / 2)
        raw = side + gap / math.sin(t)
        pa, pb = raw * math.cos(t / 2), raw * math.sin(t / 2)
        i0, i1 = math.floor((min_x - a) / (2 * pa)) - 1, math.ceil((max_x + a) / (2 * pa)) + 1
        j0, j1 = math.floor((min_y - b) / (2 * pb)) - 1, math.ceil((max_y + b) / (2 * pb)) + 1
        if (i1 - i0 + 1) * (j1 - j0 + 1) * 2 > limit * 20:
            raise PavingError('Candidate limit exceeded')
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                for k, role in ((0, 'main'), (1, 'insert')):
                    cx, cy = 2 * pa * i + k * pa, 2 * pb * j + k * pb
                    emit_shape(_jstr(j) + ':' + _jstr(i) + ':' + str(k), [[cx, cy - b], [cx + a, cy], [cx, cy + b], [cx - a, cy]],
                               [1, 0], 2 * a, role, 0)
    elif pattern in ('wood', 'brick', 'tile', 'strip'):
        _rows(pattern, settings, gap, limit, (min_x, min_y, max_x, max_y), nearby, emit, clip_tick)
    else:
        side = number(_get(settings, 'side_m', 0.30), 'side', True)
        if pattern == 'pinwheel':
            unit = side / 3
            template = [[0, 0, 2, 1], [2, 0, 1, 2], [1, 2, 2, 1], [0, 1, 1, 2], [1, 1, 1, 1]]
            first_x, last_x = math.floor(min_x / side), math.ceil(max_x / side)
            first_y, last_y = math.floor(min_y / side), math.ceil(max_y / side)
            if (last_x - first_x + 1) * (last_y - first_y + 1) * 5 > limit * 20:
                raise PavingError('Candidate limit exceeded')
            for j in range(first_y, last_y + 1):
                for i in range(first_x, last_x + 1):
                    for k, r in enumerate(template):
                        emit(_jstr(i) + ':' + _jstr(j) + ':' + str(k), i * side + r[0] * unit, j * side + r[1] * unit,
                             r[2] * unit, r[3] * unit, 'insert' if k == 4 else 'main', True)
        else:
            a = side
            b = side / (3 if pattern == 'hopscotch_2' else 2)
            det = a * a + b * b
            indices = [[(a * p[0] + b * p[1]) / det, (-b * p[0] + a * p[1]) / det]
                       for p in rectangle(min_x - a * 2, min_y - a * 2, max_x - min_x + a * 4, max_y - min_y + a * 4)]
            lo_i = math.floor(min(p[0] for p in indices)) - 1
            hi_i = math.ceil(max(p[0] for p in indices)) + 1
            lo_j = math.floor(min(p[1] for p in indices)) - 1
            hi_j = math.ceil(max(p[1] for p in indices)) + 1
            multiplier = 5 if pattern == 'hopscotch_3' else 3 if pattern == 'hopscotch_4' else 2
            if (hi_i - lo_i + 1) * (hi_j - lo_j + 1) * multiplier > limit * 20:
                raise PavingError('Candidate limit exceeded')
            count = 2 if pattern == 'hopscotch_3' else 1
            for j in range(lo_j, hi_j + 1):
                for i in range(lo_i, hi_i + 1):
                    x, y = a * i - b * j, b * i + a * j
                    id_ = _jstr(i) + ':' + _jstr(j)
                    if pattern == 'hopscotch_4':
                        horizontal = (i + j) % 2 == 0
                        for k in range(2):
                            emit(id_ + ':main:' + str(k), x + (0 if horizontal else k * a / 2), y + (k * a / 2 if horizontal else 0),
                                 a if horizontal else a / 2, a / 2 if horizontal else a, 'main', True)
                    else:
                        emit(id_ + ':main', x, y, a, a, 'main', True)
                    for n in range(count):
                        for m in range(count):
                            emit(id_ + ':insert:' + str(n) + ':' + str(m), x + a + m * b / count,
                                 y + n * b / count, b / count, b / count, 'insert', True)
    return {'schema': SCHEMA, 'unit': 'm', 'pattern': pattern, 'pieces': pieces}


def _irregular(settings, gap, limit, box, emit_shape, clip_tick):
    """Shared perturbed grid vertices form convex quadrilaterals ('grid'), or
    nearest-site cells split into unequal stones ('stone')."""
    min_x, min_y, max_x, max_y = box
    size = number(_get(settings, 'side_m', .30), 'irregular size', True)
    amount = _get(settings, 'irregularity_pct', 70)
    seed = _get(settings, 'layout_seed', 1)
    if not _is_num(amount) or amount < 0 or amount > 100:
        raise PavingError('La irregularidad debe estar entre 0 y 100%.')
    if not _is_int(seed) or abs(seed) > 2147483647:
        raise PavingError('Semilla de composición inválida.')
    seed = int(seed)
    style = _get(settings, 'irregular_style', 'grid')
    if style not in ('grid', 'stone'):
        raise PavingError('Tipo de irregular inválido.')
    jitter = (.45 if style == 'stone' else .22) * size * amount / 100
    i0, i1 = math.floor((min_x - jitter) / size) - 1, math.ceil((max_x + jitter) / size)
    j0, j1 = math.floor((min_y - jitter) / size) - 1, math.ceil((max_y + jitter) / size)
    if (i1 - i0 + 1) * (j1 - j0 + 1) > limit * 20:
        raise PavingError('Candidate limit exceeded')

    def random(i, j, axis):
        h = _imul(i, 0x1f123bb5) ^ _imul(j, 0x5f356495) ^ _imul(seed, 0x6c8e9cf5) ^ _imul(axis + 1, 0x27d4eb2d)
        h = _imul(h ^ (h >> 16), 0x7feb352d)
        h = _imul(h ^ (h >> 15), 0x846ca68b)
        h ^= h >> 16
        return h / 4294967295

    def vertex(i, j):
        return [i * size + (2 * random(i, j, 0) - 1) * jitter, j * size + (2 * random(i, j, 1) - 1) * jitter]

    if style == 'grid':
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                emit_shape(_jstr(i) + ':' + _jstr(j), [vertex(i, j), vertex(i + 1, j), vertex(i + 1, j + 1), vertex(i, j + 1)], [1, 0], size)
        return
    # Nearest-site cells are clipped by exact perpendicular bisectors. Each
    # stratified site stays inside its own grid cell. A 7x7 neighbour window
    # exceeds twice the covering radius, including maximum jitter.
    cache = {}

    def site(i, j):
        if (i, j) not in cache:
            cache[(i, j)] = vertex(i, j)
        return cache[(i, j)]

    def half_plane(poly, origin, normal):
        out = []
        previous = poly[-1]
        d0 = (previous[0] - origin[0]) * normal[0] + (previous[1] - origin[1]) * normal[1]
        for p in poly:
            d = (p[0] - origin[0]) * normal[0] + (p[1] - origin[1]) * normal[1]
            if (d <= 0) != (d0 <= 0):
                t = d0 / (d0 - d)
                out.append([previous[0] + t * (p[0] - previous[0]), previous[1] + t * (p[1] - previous[1])])
            if d <= 0:
                out.append([p[0], p[1]])
            previous, d0 = p, d
        return out

    def tidy(poly):
        n = len(poly)
        out = [p for k, p in enumerate(poly)
               if hypot(p[0] - poly[(k + n - 1) % n][0], p[1] - poly[(k + n - 1) % n][1]) > size * 1e-9]
        changed = True
        while changed and len(out) > 3:
            changed = False
            for k in range(len(out)):
                a, b, c = out[(k + len(out) - 1) % len(out)], out[k], out[(k + 1) % len(out)]
                if abs(cross(a, b, c)) < size * size * 1e-10:
                    del out[k]
                    changed = True
                    break
        return out

    def inset_stone(poly):
        result = poly
        k = 0
        while k < len(poly) and result:
            a, b = poly[k], poly[(k + 1) % len(poly)]
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = hypot(dx, dy)
            normal = [dy / length, -dx / length]
            result = half_plane(result, [a[0] - normal[0] * gap / 2, a[1] - normal[1] * gap / 2], normal)
            k += 1
        return tidy(result) if len(result) >= 3 else []

    def emit_stone(id_, poly):
        inset = inset_stone(poly)
        if len(inset) < 3 or abs(area(inset)) <= EPS:
            raise PavingError('La junta elimina una piedra: reduce la junta o aumenta el tamaño.')
        emit_shape(id_, inset, [1, 0], size, 'main', 0)

    for j in range(j0, j1 + 1):
        for i in range(i0, i1 + 1):
            p = site(i, j)
            poly = rectangle(p[0] - 2 * size, p[1] - 2 * size, 4 * size, 4 * size)
            for dy in range(-3, 4):
                for dx in range(-3, 4):
                    if dx or dy:
                        clip_tick()
                        q = site(i + dx, j + dy)
                        poly = half_plane(poly, [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2], [q[0] - p[0], q[1] - p[1]])
            poly = tidy(poly)
            base = _jstr(i) + ':' + _jstr(j)
            # Divide a seeded subset into unequal convex stones, including
            # triangles. Shared split boundaries also receive half-joints.
            if len(poly) >= 4 and random(i, j, 2) < .5 * amount / 100:
                start = math.floor(random(i, j, 3) * len(poly))
                v = poly[start:] + poly[:start]
                first, second = v[:3], [v[0]] + v[2:]
                ratio = abs(area(first)) / abs(area(poly))
                if .18 <= ratio <= .75 and len(inset_stone(first)) >= 3 and len(inset_stone(second)) >= 3:
                    emit_stone(base + ':a', first)
                    emit_stone(base + ':b', second)
                    continue
            emit_stone(base, poly)


def _rows(pattern, settings, gap, limit, box, nearby, emit, clip_tick):
    """Wood, brick, tile and strip: rows of boards, fixed or variable lengths,
    with the minimum cut against walls and holes."""
    min_x, min_y, max_x, max_y = box
    length = number(_get(settings, 'length_m', 0.30 if pattern == 'strip' else 1.20), 'length', True)
    width = number(_get(settings, 'width_m', 0.05 if pattern == 'strip' else 0.18), 'width', True)
    offset = 0 if pattern == 'tile' else _get(settings, 'offset', 0.5)
    if not _is_num(offset) or offset < 0 or offset > 1:
        raise PavingError('Invalid offset')
    # End joint (between board ends) may differ from the joint between rows.
    end_gap = gap if settings.get('joint_end_m') is None else number(settings['joint_end_m'], 'end joint', False)
    pitch_x, pitch_y = length + end_gap, width + gap
    rows = math.ceil(max_y / pitch_y) - math.floor(min_y / pitch_y) + 2
    # Minimum cut (ALFA39): a board cut by a wall or hole keeps at least
    # min_cut_m visible; its inner neighbour is cut instead, as on site.
    min_cut = 0 if pattern == 'tile' or settings.get('min_cut_m', _MISSING) is _MISSING else number(settings['min_cut_m'], 'minimum cut', False)

    def check_cut(shortest):
        if min_cut > shortest / 2 + 1e-12:
            raise PavingError('El recorte mínimo no puede superar la mitad de la tabla más corta.')

    def row_spans(y0, y1):
        """Stretches of the row band covered by the face (walls, holes, L shapes)."""
        spans = []
        for cell in nearby(min_x, y0, max_x, y1):
            clip_tick()
            if all(p[1] <= y0 for p in cell) or all(p[1] >= y1 for p in cell):
                continue
            part = clip_convex(rectangle(min_x - 1, y0, max_x - min_x + 2, y1 - y0), cell)
            if part:
                spans.append([min(p[0] for p in part), max(p[0] for p in part)])
        spans.sort(key=lambda span: span[0])
        merged = []
        for span in spans:
            if merged and span[0] <= merged[-1][1] + 1e-9:
                merged[-1][1] = max(merged[-1][1], span[1])
            else:
                merged.append(span)
        return merged

    def trim_row(boards, spans):
        """Moves one joint per short cut. A board that meets two span ends is left as is."""
        ordered = sorted(boards, key=lambda board: board['x'])

        def ends(lo, hi):
            return sum((lo < a < hi) + (lo < b < hi) for a, b in spans)

        def adjacent(p, q):
            return abs(q['x'] - (p['x'] + p['size'] + end_gap)) < 1e-7

        for a, b in spans:
            i = next((k for k, p in enumerate(ordered) if p['x'] < a < p['x'] + p['size']), -1)
            if 0 <= i < len(ordered) - 1:
                p, q = ordered[i], ordered[i + 1]
                d = min_cut - (p['x'] + p['size'] - a)
                if (d > 0 and p['x'] + p['size'] < b and p['x'] + d <= a and q['size'] - d >= min_cut and adjacent(p, q)
                        and ends(p['x'], q['x'] + q['size']) == 1):
                    p['x'] += d
                    q['x'] += d
                    q['size'] -= d
                    q['crop'] += d
            j = next((k for k, p in enumerate(ordered) if p['x'] < b < p['x'] + p['size']), -1)
            if j > 0:
                p, q = ordered[j - 1], ordered[j]
                d = min_cut - (b - q['x'])
                if (d > 0 and q['x'] >= a and q['size'] >= min_cut and p['x'] + p['size'] - d - max(p['x'], a) >= min_cut
                        and adjacent(p, q) and ends(p['x'], q['x'] + q['size']) == 1):
                    p['size'] -= d
                    q['x'] -= d

    def lay_row(y, boards, span):
        """The texture box spans `span` from x - crop, so a shortened board keeps its part of the image."""
        if min_cut > 0:
            trim_row(boards, row_spans(y, y + width))
        for b in boards:
            if b['x'] < max_x and b['x'] + b['size'] > min_x:
                emit(b['id'], b['x'], y, b['size'], width, 'main', False, [b['x'] - b['crop'], y, span, width], b['nominal'] * width)

    if pattern != 'tile' and settings.get('length_variable') is True:
        # Variable lengths (ALFA38): boards take one of a few lengths, minimum
        # to maximum in equal steps. Each row is laid both ways from a seeded
        # start; an end joint skips lengths that would fall within the stagger
        # of a joint in the previous row.
        lo = number(_get(settings, 'length_min_m', 0.6), 'minimum length', True)
        hi = number(_get(settings, 'length_max_m', 1.8), 'maximum length', True)
        steps = _get(settings, 'length_steps', 5)
        if not _is_int(steps) or steps < 2 or steps > 10 or hi < lo + 0.001:
            raise PavingError('Invalid variable lengths')
        steps = int(steps)
        seed = _get(settings, 'layout_seed', 1)
        if not _is_int(seed) or abs(seed) > 2147483647:
            raise PavingError('Semilla de composición inválida.')
        seed = _jstr(seed)
        sizes = [lo + (hi - lo) * k / (steps - 1) for k in range(steps)]
        check_cut(lo)
        stagger = min(0.15, lo / 3)
        if rows * (math.ceil((max_x - min_x) / (lo + end_gap)) + 4) > limit * 20:
            raise PavingError('Candidate limit exceeded')
        previous = []
        walk = [0]

        def near(x):
            a, b = 0, len(previous)
            while a < b:
                m = (a + b) >> 1
                if previous[m] < x:
                    a = m + 1
                else:
                    b = m
            return (a < len(previous) and previous[a] - x < stagger) or (a > 0 and x - previous[a - 1] < stagger)

        for row in range(math.floor(min_y / pitch_y) - 1, math.ceil(max_y / pitch_y) + 1):
            y = row * pitch_y
            boards = []
            start = None
            t = 0
            while t < 8 and start is None:
                candidate = -hash01('start:' + seed + ':' + str(row) + ':' + str(t)) * (hi + end_gap)
                if not near(candidate - end_gap / 2):
                    start = candidate
                t += 1
            # Rare: every seeded start sits on a joint; take the first clear spot.
            x = 0.0
            while start is None and x > -(hi + end_gap):
                if not near(x - end_gap / 2):
                    start = x
                x -= 0.005
            if start is None:
                start = 0

            def choose(k, end):
                first = math.floor(hash01('length:' + seed + ':' + str(row) + ':' + str(k)) * steps)
                for t in range(steps):
                    if not near(end(sizes[(first + t) % steps])):
                        return sizes[(first + t) % steps]
                return sizes[first]

            def board(k, x, size):
                # The texture box is as long as the longest board; a shorter one
                # shows a seeded part of it (start, middle or end), never a squeeze.
                walk[0] += 1
                if walk[0] > limit * 40:
                    raise PavingError('Candidate limit exceeded')
                crop = (hi - size) * math.floor(hash01('crop:' + seed + ':' + str(row) + ':' + str(k)) * 3) / 2
                boards.append({'id': str(row) + ':' + str(k), 'x': x, 'size': size, 'crop': crop, 'nominal': size})

            x, k = start, 0
            while x < max_x:
                size = choose(k, lambda s, x=x: x + s + end_gap / 2)
                board(k, x, size)
                x += size + end_gap
                k += 1
            x, k = start - end_gap, -1
            while x > min_x:
                size = choose(k, lambda s, x=x: x - s - end_gap / 2)
                board(k, x - size, size)
                x -= size + end_gap
                k -= 1
            lay_row(y, boards, hi)
            # The next row staggers against the joints as finally laid.
            joints = [j for b in boards for j in (b['x'] - end_gap / 2, b['x'] + b['size'] + end_gap / 2)]
            previous = sorted(j for j in joints if min_x - hi - stagger < j < max_x + hi + stagger)
    else:
        cols = math.ceil((max_x - min_x) / pitch_x) + 4
        if rows * cols > limit * 20:
            raise PavingError('Candidate limit exceeded')
        check_cut(length)
        for row in range(math.floor(min_y / pitch_y) - 1, math.ceil(max_y / pitch_y) + 1):
            shift = (row % 2) * offset * pitch_x
            boards = [{'id': str(row) + ':' + str(col), 'x': col * pitch_x + shift, 'size': length, 'crop': 0, 'nominal': length}
                      for col in range(math.floor((min_x - shift) / pitch_x) - 1, math.ceil((max_x - shift) / pitch_x) + 1)]
            lay_row(row * pitch_y, boards, length)
