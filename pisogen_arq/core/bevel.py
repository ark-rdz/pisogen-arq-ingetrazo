# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alfonso Rodríguez
"""PisoGen ARQ perimeter bevel construction, Python port of core/bevel.js.

Coordinates and profiles are metres. No host dependency and no modification
of the input piece polygons.
"""
import math

from .paving import PavingError, hypot

TOL = 1e-8


def _js_round(v):
    # Math.round rounds halves towards +infinity.
    return math.floor(v + 0.5)


def key(p):
    return ':'.join(str(_js_round(v / TOL)) for v in p)


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _sub(a, b):
    return [a[0] - b[0], a[1] - b[1]]


def area(p):
    n = len(p)
    return sum(_cross(a, p[(i + 1) % n]) for i, a in enumerate(p)) / 2


def _distance(a, b):
    return hypot(a[0] - b[0], a[1] - b[1])


def _finite(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _is_int(v):
    return _finite(v) and float(v).is_integer()


def _clean(loop):
    n = len(loop)
    points = [p for i, p in enumerate(loop) if _distance(p, loop[(i + n - 1) % n]) > TOL]
    changed = True
    while changed and len(points) > 3:
        changed = False
        for i in range(len(points)):
            before, here, after = points[(i + len(points) - 1) % len(points)], points[i], points[(i + 1) % len(points)]
            u, v = _sub(here, before), _sub(after, here)
            if abs(_cross(u, v)) <= TOL * max(hypot(*u), hypot(*v)) and u[0] * v[0] + u[1] * v[1] > 0:
                del points[i]
                changed = True
                break
    return points


def perimeters(polygons):
    normalized = [poly if area(poly) > 0 else list(reversed(poly)) for poly in polygons]
    vertices = {}
    for poly in normalized:
        for p in poly:
            vertices[key(p)] = p
    edges = {}
    work = 0
    for poly in normalized:
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            v = _sub(b, a)
            length = hypot(*v)
            cuts = []
            if length <= TOL:
                continue
            for p in vertices.values():
                work += 1
                if work > 2000000:
                    raise PavingError('Perimeter work limit exceeded')
                t = ((p[0] - a[0]) * v[0] + (p[1] - a[1]) * v[1]) / (length * length)
                if -TOL / length <= t <= 1 + TOL / length and abs(_cross(v, _sub(p, a))) <= TOL * length:
                    cuts.append((max(0, min(1, t)), p))
            cuts.sort(key=lambda cut: cut[0])
            for j in range(len(cuts) - 1):
                p, q = cuts[j][1], cuts[j + 1][1]
                kp, kq = key(p), key(q)
                if kp == kq:
                    continue
                order = kp < kq
                edge_key = kp + '|' + kq if order else kq + '|' + kp
                entry = edges.get(edge_key) or {'count': 0, 'a': p if order else q, 'b': q if order else p}
                entry['count'] += 1 if order else -1
                edges[edge_key] = entry
    following = {}
    edge_count = 0
    for e in edges.values():
        if e['count'] == 0:
            continue
        if abs(e['count']) != 1:
            raise PavingError('Overlapping piece fragments')
        a, b = (e['a'], e['b']) if e['count'] > 0 else (e['b'], e['a'])
        k = key(a)
        if k in following:
            raise PavingError('Touching perimeter branches')
        following[k] = (a, b)
        edge_count += 1
    loops = []
    while following:
        start = next(iter(following))
        at, loop = start, []
        while True:
            edge = following.get(at)
            if not edge:
                raise PavingError('Open piece perimeter')
            loop.append(edge[0])
            del following[at]
            at = key(edge[1])
            if len(loop) > edge_count:
                raise PavingError('Invalid perimeter cycle')
            if at == start:
                break
        loop = _clean(loop)
        if len(loop) < 3 or abs(area(loop)) < TOL * TOL:
            raise PavingError('Degenerate perimeter')
        loops.append(loop)
    if not loops:
        raise PavingError('Empty perimeter')
    return loops


def _on_segment(p, a, b):
    v, w = _sub(b, a), _sub(p, a)
    length = hypot(*v)
    dot = w[0] * v[0] + w[1] * v[1]
    return abs(_cross(v, w)) <= TOL * length and dot >= -TOL and dot <= length * length + TOL


def _inside(p, poly):
    result = False
    j = len(poly) - 1
    for i in range(len(poly)):
        a, b = poly[j], poly[i]
        if _on_segment(p, a, b):
            return True
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]:
            result = not result
        j = i
    return result


def _intersect(a, b, c, d):
    ab, cd = _sub(b, a), _sub(d, c)
    det = _cross(ab, cd)
    if abs(det) < TOL * TOL:
        return _on_segment(a, c, d) or _on_segment(b, c, d) or _on_segment(c, a, b) or _on_segment(d, a, b)
    t = _cross(_sub(c, a), cd) / det
    u = _cross(_sub(c, a), ab) / det
    return -1e-9 <= t <= 1 + 1e-9 and -1e-9 <= u <= 1 + 1e-9


def offset(loop, inset):
    result = []
    n = len(loop)
    for i, p in enumerate(loop):
        before, after = loop[(i + n - 1) % n], loop[(i + 1) % n]
        u, v = _sub(p, before), _sub(after, p)
        lu, lv = hypot(*u), hypot(*v)
        u = [c / lu for c in u]
        v = [c / lv for c in v]
        a = [p[0] - u[1] * inset, p[1] + u[0] * inset]
        b = [p[0] - v[1] * inset, p[1] + v[0] * inset]
        det = _cross(u, v)
        if abs(det) < 1e-10:
            result.append(a)
            continue
        t = _cross(_sub(b, a), v) / det
        q = [a[0] + t * u[0], a[1] + t * u[1]]
        if _distance(p, q) > inset * 12 + TOL:
            raise PavingError('Miter too long')
        result.append(q)
    return result


def _material_contains(loops, p):
    return sum((1 if area(loop) > 0 else -1) for loop in loops if _inside(p, loop)) > 0


def valid_offset(original, shifted):
    for k, loop in enumerate(shifted):
        source = original[k]
        if area(loop) * area(source) <= 0:
            return False
        if area(source) > 0 and abs(area(loop)) >= abs(area(source)):
            return False
        if area(source) < 0 and abs(area(loop)) <= abs(area(source)):
            return False
        for i in range(len(loop)):
            a, b = loop[i], loop[(i + 1) % len(loop)]
            # Every shifted edge must retain its original direction; a rectangle
            # collapsed past its centre otherwise appears valid again.
            old, now = _sub(source[(i + 1) % len(source)], source[i]), _sub(b, a)
            if now[0] * old[0] + now[1] * old[1] <= TOL * TOL:
                return False
            if not _material_contains(original, a) or not _material_contains(original, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]):
                return False
            for l in range(k, len(shifted)):
                other = shifted[l]
                for j in range(len(other)):
                    if l == k and (j == i or j == (i + 1) % len(loop) or i == (j + 1) % len(loop)):
                        continue
                    if _intersect(a, b, other[j], other[(j + 1) % len(other)]):
                        return False
    return True


def profile(width, height, segments, curved):
    levels = [{'inset': 0, 'z': 0}]
    for i in range(1, segments + 1):
        t = i / segments
        levels.append({'inset': width * (1 - math.cos(t * math.pi / 2)) if curved else width * t,
                       'z': height * math.sin(t * math.pi / 2) if curved else height * t})
    remaining = 0.0
    levels[-1]['remaining'] = 0
    for i in range(len(levels) - 2, -1, -1):
        remaining += hypot(levels[i + 1]['inset'] - levels[i]['inset'], levels[i + 1]['z'] - levels[i]['z'])
        levels[i]['remaining'] = remaining
    return levels


def vertical_contour(loops, settings):
    size = settings.get('vertical_bevel_size_m')
    curved = settings.get('vertical_bevel_profile') == 'curved'
    segments = settings.get('vertical_bevel_segments') if curved else 1
    if (settings.get('vertical_bevel_profile') not in ('straight', 'curved') or not _finite(size) or size < .0001 or
            not _is_int(segments) or segments < 1 or segments > 6 or (curved and segments < 2)):
        raise PavingError('Medidas o segmentos del bisel vertical inválidos.')
    segments = int(segments)
    for attempt in range(24):
        multiplier = .75 ** attempt
        state = {'reduced': False, 'skipped': False, 'changed': False}

        def corners(loop):
            # A clockwise hole is kept intact. Only convex material corners are
            # removed, never material added into a hole or a re-entrant corner.
            if area(loop) < 0:
                return loop
            result = []
            n = len(loop)
            for i, p in enumerate(loop):
                before, after = loop[(i + n - 1) % n], loop[(i + 1) % n]
                u, v = _sub(p, before), _sub(after, p)
                lu, lv = hypot(*u), hypot(*v)
                u = [c / lu for c in u]
                v = [c / lv for c in v]
                turn = math.atan2(_cross(u, v), u[0] * v[0] + u[1] * v[1])
                if turn <= .01:
                    result.append(p)
                    continue
                tan = math.tan(turn / 2)
                requested = size * multiplier * tan if curved else size * multiplier
                retreat = min(requested, lu * .24, lv * .24)
                radius = retreat / tan
                if retreat < requested - 1e-10 or attempt > 0:
                    state['reduced'] = True
                min_edge = 2 * radius * math.sin(turn / (2 * segments)) if curved else 2 * retreat * math.cos(turn / 2)
                if retreat < .0001 or min_edge < .00004:
                    result.append(p)
                    state['skipped'] = True
                    continue
                a = [p[0] - u[0] * retreat, p[1] - u[1] * retreat]
                b = [p[0] + v[0] * retreat, p[1] + v[1] * retreat]
                if curved:
                    center = [a[0] - u[1] * radius, a[1] + u[0] * radius]
                    start = math.atan2(a[1] - center[1], a[0] - center[0])
                    for m in range(segments + 1):
                        angle = start + turn * m / segments
                        result.append(a if m == 0 else b if m == segments else
                                      [center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle)])
                else:
                    result.extend([a, b])
                state['changed'] = True
            return result

        candidate = [corners(loop) for loop in loops]
        valid, work = True, 0
        for k, loop in enumerate(candidate):
            if not valid:
                break
            if len(loop) > 1000:
                raise PavingError('El bisel vertical supera el límite de vértices del contorno.')
            if area(loop) * area(loops[k]) <= 0:
                valid = False
                break
            for i in range(len(loop)):
                if not valid:
                    break
                a, b = loop[i], loop[(i + 1) % len(loop)]
                if area(loop) > 0 and (not _material_contains(loops, a) or not _material_contains(loops, [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2])):
                    valid = False
                    break
                for l in range(k, len(candidate)):
                    if not valid:
                        break
                    other = candidate[l]
                    for j in range(len(other)):
                        work += 1
                        if work > 2000000:
                            raise PavingError('El bisel vertical supera el límite de comprobaciones.')
                        if k == l and (j == i or j == (i + 1) % len(loop) or i == (j + 1) % len(loop)):
                            continue
                        if _intersect(a, b, other[j], other[(j + 1) % len(other)]):
                            valid = False
                            break
        if valid:
            return dict(state, loops=candidate)
    return {'loops': loops, 'reduced': False, 'skipped': True, 'changed': False}


def mesh(piece, settings, contours=None):
    loops = contours or perimeters(piece['polygons_m'])
    upper = settings.get('bevel_enabled') is not False
    height = settings.get('bevel_height_m') if upper else 0
    width = (height if settings.get('bevel_lock') else settings.get('bevel_width_m')) if upper else 0
    depth = settings.get('depth_m')
    if not all(_finite(v) for v in (height, width, depth)) or depth <= 0 or (upper and (height <= 0 or width <= 0 or height >= depth)):
        raise PavingError('El bisel requiere altura y ancho positivos; la altura debe ser menor que el espesor.')
    curved = upper and settings.get('bevel_profile') == 'curved'
    segments = settings.get('bevel_segments') if curved else 1 if upper else 0
    if not _is_int(segments) or segments < 0 or segments > 6:
        raise PavingError('Segmentos de bisel inválidos.')
    segments = int(segments)
    scale, rings = 1.0, None
    for _attempt in range(24):
        levels = profile(width * scale, height * scale, segments, curved)
        try:
            rings = [[offset(loop, level['inset']) for loop in loops] if level['inset'] else loops for level in levels]
            native_edges = not contours or all(_distance(p, loop[(i + 1) % len(loop)]) >= .00004
                                               for ring in rings for loop in ring for i, p in enumerate(loop))
            if native_edges and all(valid_offset(loops, ring) for ring in rings[1:]):
                break
        except (PavingError, ArithmeticError):
            # The JavaScript core catches every failed attempt the same way.
            pass
        rings = None
        scale *= 0.75
    if not rings or (upper and (width * scale < 0.0001 or height * scale < 0.0001)):
        return {'skipped': True, 'reason': 'Geometría del recorte incompatible con un bisel de al menos 0.1 mm.'}
    levels = profile(width * scale, height * scale, segments, curved)
    lower = depth - height * scale
    sides, side_uv, uv = [], [], {}

    def vertex(point, z):
        result = [point[0], point[1], z]
        uv[key(result)] = {'point_m': result, 'uv_xy_m': [point[0], point[1]]}
        return result

    bases = [[vertex(p, 0) for p in loop] for loop in loops]
    layers = [[[vertex(p, lower + levels[n]['z']) for p in loop] for loop in ring] for n, ring in enumerate(rings)]
    for k, loop in enumerate(loops):
        bottom, first = bases[k], layers[0][k]
        for i, p in enumerate(loop):
            j = (i + 1) % len(loop)
            edge = _sub(loop[j], p)
            length = hypot(*edge)
            normal = [-edge[1] / length, edge[0] / length]

            # Unfold each edge in its own plane. Keep its tangential coordinate
            # unchanged; adjacent perpendicular edges have a vertical UV seam.
            def unfold(point, inset, remaining, normal=normal):
                shift = width * scale - inset - remaining
                return [point[0] + normal[0] * shift, point[1] + normal[1] * shift]

            r0 = levels[0]['remaining']
            sides.append([bottom[i], bottom[j], first[j], first[i]])
            side_uv.append([unfold(bottom[i], 0, r0 + lower), unfold(bottom[j], 0, r0 + lower),
                            unfold(first[j], 0, r0), unfold(first[i], 0, r0)])
            for n in range(len(layers) - 1):
                sides.append([layers[n][k][i], layers[n][k][j], layers[n + 1][k][j], layers[n + 1][k][i]])
                lb, la = levels[n], levels[n + 1]
                side_uv.append([unfold(layers[n][k][i], lb['inset'], lb['remaining']), unfold(layers[n][k][j], lb['inset'], lb['remaining']),
                                unfold(layers[n + 1][k][j], la['inset'], la['remaining']), unfold(layers[n + 1][k][i], la['inset'], la['remaining'])])
    if settings.get('surface_texture_continuity'):
        # One chart per geometric vertex, anchored to the unchanged top XY map.
        # Extend outward by developed profile distance.
        index = 0
        for k, loop in enumerate(loops):
            n_loop = len(loop)
            normals = []
            for i, p in enumerate(loop):
                d = _sub(loop[(i + 1) % n_loop], p)
                l = hypot(*d)
                normals.append([-d[1] / l, d[0] / l])
            directions = []
            for i, nrm in enumerate(normals):
                before = normals[(i + n_loop - 1) % n_loop]
                den = 1 + before[0] * nrm[0] + before[1] * nrm[1]
                if den < 1e-6:
                    raise PavingError('Esquina incompatible con continuidad de superficie.')
                directions.append([(before[0] + nrm[0]) / den, (before[1] + nrm[1]) / den])

            def chart(point, i, inset, remaining, directions=directions):
                shift = width * scale - inset - remaining
                nrm = directions[i]
                return [point[0] + nrm[0] * shift, point[1] + nrm[1] * shift]

            r0 = levels[0]['remaining']
            for i in range(n_loop):
                j = (i + 1) % n_loop
                side_uv[index] = [chart(bases[k][i], i, 0, r0 + lower), chart(bases[k][j], j, 0, r0 + lower),
                                  chart(layers[0][k][j], j, 0, r0), chart(layers[0][k][i], i, 0, r0)]
                index += 1
                for n in range(len(layers) - 1):
                    lb, la = levels[n], levels[n + 1]
                    side_uv[index] = [chart(layers[n][k][i], i, lb['inset'], lb['remaining']), chart(layers[n][k][j], j, lb['inset'], lb['remaining']),
                                      chart(layers[n + 1][k][j], j, la['inset'], la['remaining']), chart(layers[n + 1][k][i], i, la['inset'], la['remaining'])]
                    index += 1
    elif settings.get('perimeter_texture_strip'):
        # A rounded vertical corner is one developable wall strip. Keep its UV
        # continuous across every facet; duplicate U only at one closure.
        minimum = [math.inf, math.inf]
        for poly in piece['polygons_m']:
            for p in poly:
                minimum = [min(minimum[0], p[0]), min(minimum[1], p[1])]
        along_x = not piece.get('grain_axis') or piece['grain_axis'][0] == 1
        frame = piece.get('texture_frame_m')

        def encode(u, v):
            if frame:
                a = frame['axis']
                c = frame.get('cross_axis') or [-a[1], a[0]]
                x, y = frame['origin_uv_m'][0] + u, frame['origin_uv_m'][1] + v
                return [a[0] * x + c[0] * y, a[1] * x + c[1] * y]
            return [minimum[0] + u, minimum[1] + v] if along_x else [minimum[0] + v, minimum[1] + u]

        index = 0
        for loop in loops:
            n_loop = len(loop)
            lengths = [_distance(p, loop[(i + 1) % n_loop]) for i, p in enumerate(loop)]
            seam = 0
            for i in range(1, n_loop):
                y = (loop[i][1] + loop[(i + 1) % n_loop][1]) / 2
                previous_y = (loop[seam][1] + loop[(seam + 1) % n_loop][1]) / 2
                if lengths[i] > lengths[seam] + TOL or (abs(lengths[i] - lengths[seam]) <= TOL and y > previous_y):
                    seam = i
            starts = [0.0] * n_loop
            total = 0.0
            for step in range(n_loop):
                i = (seam + step) % n_loop
                starts[i] = total
                total += lengths[i]
            r0 = levels[0]['remaining']
            for i in range(n_loop):
                u = starts[i]
                end = u + lengths[i]
                side_uv[index] = [encode(u, r0 + lower), encode(end, r0 + lower), encode(end, r0), encode(u, r0)]
                index += 1
                for n in range(len(layers) - 1):
                    side_uv[index] = [encode(u, levels[n]['remaining']), encode(end, levels[n]['remaining']),
                                      encode(end, levels[n + 1]['remaining']), encode(u, levels[n + 1]['remaining'])]
                    index += 1
    return {'sides_m': sides, 'side_uv_m': side_uv, 'top_loops_m': layers[-1], 'base_loops_m': bases,
            'uv_vertices': list(uv.values()), 'scale': scale, 'width_m': width * scale, 'height_m': height * scale, 'curved': curved}


def corner_smooth_edges(bevel_mesh):
    if not bevel_mesh.get('vertical_curved'):
        return []
    edges = {}
    direction_tolerance = 1e-7 * .0254
    for face in bevel_mesh['sides_m']:
        a, b, c = face[0], face[1], face[2]
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - a[i] for i in range(3)]
        normal = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        length = hypot(*normal)
        if length < 1e-16:
            continue
        normal = [n / length for n in normal]
        for i, p in enumerate(face):
            q = face[(i + 1) % len(face)]
            ka, kb = key(p), key(q)
            edge_key = ka + '|' + kb if ka < kb else kb + '|' + ka
            edge = edges.get(edge_key) or {'p': p, 'q': q, 'normals': []}
            edge['normals'].append(normal)
            edges[edge_key] = edge
    result = []
    for edge in edges.values():
        if len(edge['normals']) != 2:
            continue
        vector = [edge['q'][i] - edge['p'][i] for i in range(3)]
        if abs(vector[2]) <= direction_tolerance or hypot(vector[0], vector[1]) <= direction_tolerance:
            continue
        dot = sum(n * m for n, m in zip(edge['normals'][0], edge['normals'][1]))
        if math.acos(max(-1, min(1, dot))) < .9:
            result.append([edge['p'], edge['q']])
    return result


def apply(output, settings):
    if not settings.get('bevel_enabled') and not settings.get('vertical_bevel_enabled'):
        return output
    count = {'reduced': 0, 'skipped': 0, 'vreduced': 0, 'vskipped': 0}

    def one(piece):
        # Adopasto grass is a recessed flat fill, not a second concrete paver.
        if output.get('pattern') in ('adopasto', 'adopasto_reja') and piece['role'] == 'insert':
            return dict(piece)
        corners = None
        if settings.get('vertical_bevel_enabled'):
            corners = vertical_contour(perimeters(piece['polygons_m']), settings)
            if corners['reduced']:
                count['vreduced'] += 1
            if corners['skipped']:
                count['vskipped'] += 1
        frame = piece.get('texture_frame_m')
        angled_frame = bool(frame) and abs(frame['axis'][0]) > TOL and abs(frame['axis'][1]) > TOL
        # Cestería keeps each edge anchored to the board's top frame. A single
        # perimeter strip turns every end into longitudinal grain.
        changed = bool(corners and corners['changed'])
        perimeter_strip = ((output.get('pattern') == 'octagon' and changed) or
                           (output.get('pattern') not in ('basketweave', 'hexagon', 'octagon') and
                            (changed or (bool(settings.get('bevel_enabled')) and angled_frame))))
        surface_continuity = output.get('pattern') == 'octagon' and settings.get('texture_surface_continuity') is True
        mesh_settings = dict(settings, perimeter_texture_strip=bool(perimeter_strip), surface_texture_continuity=surface_continuity)
        bevel = mesh(piece, mesh_settings, corners and corners['loops'])
        if bevel.get('skipped'):
            if settings.get('bevel_enabled'):
                count['skipped'] += 1
            if not changed:
                return dict(piece)
            bevel = mesh(piece, dict(mesh_settings, bevel_enabled=False), corners['loops'])
            if bevel.get('skipped'):
                if not corners['skipped']:
                    count['vskipped'] += 1
                return dict(piece)
        elif settings.get('bevel_enabled') and bevel['scale'] < 0.999999:
            count['reduced'] += 1
        if corners:
            bevel['vertical_curved'] = settings.get('vertical_bevel_profile') == 'curved' and corners['changed']
            bevel['smooth_corner_edges_m'] = corner_smooth_edges(bevel)
        return dict(piece, bevel_mesh=bevel)

    pieces = [one(piece) for piece in output['pieces']]
    result = dict(output, pieces=pieces, bevel_summary={'reduced': count['reduced'], 'skipped': count['skipped']})
    if settings.get('vertical_bevel_enabled'):
        result['vertical_bevel_summary'] = {'reduced': count['vreduced'], 'skipped': count['vskipped']}
    return result
