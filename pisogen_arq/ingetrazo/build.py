# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alfonso Rodríguez
"""PisoGen ARQ floors in an IngeTrazo document.

A floor is ONE container group (tagged as a PisoGen ARQ floor) whose parts
are the pieces: component instances, so equal pieces share one prototype
mesh and only carry their own matrix, like the SketchUp version. The
parameters live on the container (``group.ext[KEY]``) so Edit can rebuild
it where it stands.

Coordinates: the core works in metres in the face plane (pattern space).
``face_frame`` gives the matrix from that plane to the world; IngeTrazo
documents are in metres too.
"""
import math

from PySide6.QtGui import QMatrix4x4, QVector3D

from ..core import bevel, paving
from . import geometry, store, texture

KEY = 'pisogen_arq'
VERSION = '2026.1.0'
NAMES = {
    'wood': 'Madera', 'brick': 'Ladrillo', 'tile': 'Loseta', 'strip': 'Cintilla', 'pinwheel': 'Tweed',
    'hopscotch_1': 'Hopscotch 1', 'hopscotch_2': 'Hopscotch 2', 'hopscotch_3': 'Hopscotch 3', 'hopscotch_4': 'Hopscotch 4',
    'herringbone': 'Espiga', 'chevron': 'Chevron', 'basketweave': 'Cestería', 'hexagon': 'Hexágono', 'octagon': 'Octágono',
    'adopasto': 'Adopasto', 'adopasto_reja': 'Adopasto Reja', 'irregular': 'Irregular', 'wedge': 'Cuña',
    'i_block': 'Bloque I', 'diamonds': 'Diamantes',
}
MAIN_MAT = 'PisoGen ARQ piezas'
INSERT_MAT = 'PisoGen ARQ insertos'
GROUT_MAT = 'PisoGen ARQ junta'
DEFAULT_COLORS = {MAIN_MAT: (0.72, 0.56, 0.40), INSERT_MAT: (0.36, 0.30, 0.26), GROUT_MAT: (0.78, 0.77, 0.74)}
ROUND = 1e-7
# «Al nivel de la cara» leaves the top this far above it: coplanar faces flicker.
FLUSH_PROUD_M = 0.0005


class FloorError(ValueError):
    pass


class FaceCopy:
    """What a floor reads from a face, kept after its group is closed: an open
    group's faces are in world coordinates, but they may not outlive it."""

    def __init__(self, face):
        self.vertices = [QVector3D(p) for p in face.vertices]
        self._normal = QVector3D(face.normal())
        self._triangles = [[QVector3D(p) for p in tri] for tri in face.triangulate()]
        self.attrs = dict(getattr(face, 'attrs', None) or {})

    def normal(self):
        return self._normal

    def triangulate(self):
        return self._triangles


def _xyz(v):
    return (v.x(), v.y(), v.z())


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a):
    length = math.sqrt(_dot(a, a))
    if length < 1e-12:
        raise FloorError('La cara está degenerada.')
    return (a[0] / length, a[1] / length, a[2] / length)


def face_frame(face):
    """The face plane as pattern space: origin at the first corner, X along
    the first edge, Z along the face normal. Returns (matrix, to_plane)."""
    loop = [_xyz(p) for p in face.vertices]
    if len(loop) < 3:
        raise FloorError('La cara tiene menos de 3 esquinas.')
    origin = loop[0]
    z = _unit(_xyz(face.normal()))
    # Give horizontal floors an upward extrusion even if their face is reversed.
    if z[2] < -0.5:
        z = (-z[0], -z[1], -z[2])
    x = None
    for p in loop[1:]:
        d = _sub(p, origin)
        d = _sub(d, tuple(c * _dot(d, z) for c in z))
        if _dot(d, d) > 1e-12:
            x = _unit(d)
            break
    if x is None:
        raise FloorError('La cara está degenerada.')
    y = _cross(z, x)
    matrix = QMatrix4x4(x[0], y[0], z[0], origin[0],
                        x[1], y[1], z[1], origin[1],
                        x[2], y[2], z[2], origin[2],
                        0, 0, 0, 1)

    def to_plane(p):
        d = _sub(_xyz(p) if isinstance(p, QVector3D) else p, origin)
        return [_dot(d, x), _dot(d, y)]

    return matrix, to_plane


def face_domain(face):
    """Boundary and host triangles of a face in its own plane, metres."""
    matrix, to_plane = face_frame(face)
    boundary = [to_plane(p) for p in face.vertices]
    triangles = [[to_plane(p) for p in tri] for tri in face.triangulate()]
    triangles = [t for t in triangles if abs(paving.area(t)) > 1e-12]
    if not triangles:
        raise FloorError('La cara no tiene área.')
    if len(triangles) > 10000:
        raise FloorError('La cara es demasiado compleja (más de 10 000 triángulos).')
    return matrix, boundary, triangles


def generate(boundary, triangles, pattern, settings, piece_limit=100000):
    """Core output for a face domain in pattern space, bevels applied."""
    data = {'schema': paving.SCHEMA, 'unit': 'm', 'pattern': pattern, 'boundary': boundary,
            'domain_triangles_m': triangles, 'settings': settings, 'piece_limit': piece_limit}
    return bevel.apply(paving.generate(data), settings)


# ---------------------------------------------------------------------------
# Piece geometry, in the piece's own local frame (min corner at the origin)
# ---------------------------------------------------------------------------

def _rings(loops):
    """Outer loops (counter-clockwise) with the holes (clockwise) they contain."""
    outers = [l for l in loops if bevel.area(l) > 0]
    holes = [l for l in loops if bevel.area(l) < 0]
    rings = [[o, []] for o in outers]
    for h in holes:
        probe = h[0]
        owner = next((r for r in rings if bevel._inside(probe, r[0])), rings[0] if rings else None)
        if owner is not None:
            owner[1].append(h)
    return rings


def piece_faces(piece, depth):
    """Faces of a closed piece in pattern space: [(outer, holes, coords)],
    every normal outward. ``coords`` gives each outer vertex its texture
    coordinate (metres): the XY of the top and base, a wall unfolded outwards
    from its top edge, or the bevel chart. Uses the bevel mesh when the core
    made one; otherwise a straight prism from 0 to depth."""
    mesh = piece.get('bevel_mesh')
    if mesh and not mesh.get('skipped'):
        faces = []
        for outer, holes in _rings([[[p[0], p[1]] for p in loop] for loop in mesh['base_loops_m']]):
            outer = [[p[0], p[1], 0] for p in reversed(outer)]
            faces.append((outer, [[[p[0], p[1], 0] for p in reversed(h)] for h in holes], [p[:2] for p in outer]))
        for quad, chart in zip(mesh['sides_m'], mesh['side_uv_m']):
            faces.append((quad, [], chart))
        top_z = mesh['top_loops_m'][0][0][2]
        for outer, holes in _rings([[[p[0], p[1]] for p in loop] for loop in mesh['top_loops_m']]):
            faces.append(([[p[0], p[1], top_z] for p in outer], [[[p[0], p[1], top_z] for p in h] for h in holes],
                          [p[:2] for p in outer]))
        return faces
    return _prism_faces(bevel.perimeters(piece['polygons_m']), depth)


def _prism_faces(loops, depth):
    """Base, top and walls of counter-clockwise outlines with their clockwise
    holes, from 0 to depth, every normal outward."""
    faces = []
    for outer, holes in _rings(loops):
        faces.append(([[p[0], p[1], 0] for p in reversed(outer)], [[[p[0], p[1], 0] for p in reversed(h)] for h in holes],
                      [p[:2] for p in reversed(outer)]))
        faces.append(([[p[0], p[1], depth] for p in outer], [[[p[0], p[1], depth] for p in h] for h in holes],
                      [p[:2] for p in outer]))
    for loop in loops:
        n = len(loop)
        for i in range(n):
            a, b = loop[i], loop[(i + 1) % n]
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            nx, ny = (b[1] - a[1]) / length, -(b[0] - a[0]) / length
            # Unfold the wall outward from its top edge: at the shared edge the
            # coordinates equal the top map exactly.
            faces.append(([[a[0], a[1], 0], [b[0], b[1], 0], [b[0], b[1], depth], [a[0], a[1], depth]], [],
                          [[a[0] + nx * depth, a[1] + ny * depth], [b[0] + nx * depth, b[1] + ny * depth],
                           [b[0], b[1]], [a[0], a[1]]]))
    return faces


def _anchor(piece):
    pts = [p for poly in piece['polygons_m'] for p in poly]
    return min(p[0] for p in pts), min(p[1] for p in pts)


def _signature(faces, anchor, maps):
    """Equal pieces (same shape and texture placement after moving to their
    anchor) share a prototype."""
    ax, ay = anchor

    def loop(points):
        return tuple((round((p[0] - ax) / ROUND), round((p[1] - ay) / ROUND), round(p[2] / ROUND)) for p in points)

    shape = tuple((loop(outer), tuple(loop(h) for h in holes)) for outer, holes, _coords in faces)
    return shape, tuple(None if m is None else tuple(round(v / ROUND) for v in m) for m in maps)


SOFT_COS = math.cos(math.radians(50))


def soften(mesh):
    """Bevel facets read as one rounded edge: an edge between two faces that
    turn less than 50° is soft, as the SketchUp version smooths them."""
    for edge in mesh.edges:
        faces = edge.faces
        if len(faces) == 2:
            a, b = _xyz(faces[0].normal()), _xyz(faces[1].normal())
            if _dot(a, b) > SOFT_COS:
                edge.soft = True


def ensure_materials(scene, colors=None):
    from core.materials import Material
    for name, color in (colors or DEFAULT_COLORS).items():
        if name not in scene.materials:
            scene.materials[name] = Material(name, color=color)


def _material(scene, name, fallback):
    return scene.materials.get(name) or scene.materials[fallback]


def _ratio(material):
    """Image height / width, from the material's real tile size."""
    tex = material.texture or {}
    sw, sh = tex.get('sw') or 1.0, tex.get('sh') or 1.0
    return sh / sw if sw > 0 and sh > 0 else 1.0


def _face_maps(faces, anchor, uv):
    """Local→UV affine map per face, or None where it is degenerate."""
    from core.texture import fit_uv_affine
    maps = []
    for outer, _holes, coords in faces:
        points = [(p[0] - anchor[0], p[1] - anchor[1], p[2]) for p in outer]
        maps.append(fit_uv_affine(points, [uv(c) for c in coords]))
    return maps


def _material_slots(pieces, settings):
    """Which main material each piece takes: the core's draw (sequence,
    randomness, no repeated neighbours) or one seeded pick per piece."""
    count = len(settings.get('main_materials') or []) or 1
    slots = paving.assign_materials(pieces, settings)
    if slots is not None:
        return slots
    seed = paving._jstr(settings.get('material_seed', 1))
    return [math.floor(paving.hash01('mat:' + seed + ':' + p['id']) * count) for p in pieces]


def level_pose(matrix, settings, lowered=False):
    """Where the floor's base goes: on the face, or sunk so its top meets it.
    Sunk over a slab that went down, the top meets the face exactly; over a
    face that stayed, it stands 0.5 mm proud so the two do not flicker."""
    if settings.get('base_level') != 'flush':
        return matrix
    place = QMatrix4x4(matrix)
    place.translate(0, 0, (0 if lowered else FLUSH_PROUD_M) - settings.get('depth_m', 0.02))
    return place


def build_parts(scene, matrix, boundary, triangles, pattern, settings, lowered=False):
    """The pieces of a floor as component instances placed by ``matrix``,
    plus the joint fill when asked. Raises before touching the document when
    the core refuses the input."""
    from core.group import Group
    from core.mesh import Mesh
    depth = settings.get('depth_m', 0.02)
    matrix = level_pose(matrix, settings, lowered)
    out = generate(boundary, triangles, pattern, settings, piece_limit(pattern, settings))
    if not out['pieces']:
        raise FloorError('El patrón no deja piezas sobre la cara.')
    ensure_materials(scene)
    mains = [_material(scene, name, MAIN_MAT) for name in (settings.get('main_materials') or [MAIN_MAT])]
    insert_material = _material(scene, settings.get('insert_material') or INSERT_MAT, INSERT_MAT)
    inserts = settings.get('insert_enabled') or pattern in ('adopasto', 'adopasto_reja')
    slots = _material_slots(out['pieces'], settings)
    paint_settings = dict(settings, pattern=pattern)
    stone = texture.stone_extent(out['pieces'], paint_settings) if pattern == 'irregular' else None
    prototypes = {}
    children = []
    for piece, slot in zip(out['pieces'], slots):
        piece_depth = piece.get('depth_m', depth)
        faces = piece_faces(piece, piece_depth)
        anchor = _anchor(piece)
        insert = piece['role'] == 'insert' and inserts
        material = insert_material if insert else mains[slot % len(mains)]
        maps = [None] * len(faces)
        if material.texture:
            uv = texture.uv_mapper(piece, dict(paint_settings, depth_m=piece_depth), _ratio(material),
                                   texture.texture_id(piece, paint_settings), stone)
            maps = _face_maps(faces, anchor, uv)
        key = (material.name, _signature(faces, anchor, maps))
        proto = prototypes.get(key)
        if proto is None:
            paint = material.face_attrs()
            proto = Mesh()
            for (outer, holes, _coords), uvw in zip(faces, maps):
                f = proto.add_face([QVector3D(p[0] - anchor[0], p[1] - anchor[1], p[2]) for p in outer],
                                   [[QVector3D(p[0] - anchor[0], p[1] - anchor[1], p[2]) for p in h] for h in holes] or None)
                attrs = dict(paint)
                if uvw is not None and 'texture' in attrs:
                    attrs['texture'] = dict(attrs['texture'], uvw=list(uvw))
                f.attrs = attrs
            soften(proto)
            prototypes[key] = proto
        place = QMatrix4x4(matrix)
        place.translate(anchor[0], anchor[1], piece.get('lift_m', 0))
        child = Group(proto, name=piece['id'])
        child.xform = place
        child.component = True
        children.append(child)
    if settings.get('grout_enabled'):
        children.append(grout_bed(scene, matrix, triangles, settings))
    net_area = sum(abs(paving.area(t)) for t in triangles)
    return children, {'pieces': len(out['pieces']), 'prototypes': len(prototypes),
                      'area_m2': sum(abs(paving.area(poly)) for p in out['pieces'] for poly in p['polygons_m']),
                      'quantities': store.quantities(out['pieces'], settings, net_area)}


def piece_limit(pattern, settings):
    """main.rb limits: unique pieces (irregular stones, continuous texture)
    15 000; grass blocks 200 000; the rest 100 000."""
    if pattern == 'irregular' or settings.get('texture_mode') == 'continuous':
        return 15000
    return 200000 if pattern in ('adopasto', 'adopasto_reja') else 100000


def count_pieces(boundary, triangles, pattern, settings):
    """Pieces the floor will have, or 0 when the core refuses the input (the
    build itself then reports why)."""
    try:
        data = {'schema': paving.SCHEMA, 'unit': 'm', 'pattern': pattern, 'boundary': boundary,
                'domain_triangles_m': triangles, 'settings': settings, 'piece_limit': piece_limit(pattern, settings)}
        return len(paving.generate(data)['pieces'])
    except Exception:  # noqa: BLE001
        return 0


GROUT_CLEARANCE_M = 0.0002


def grout_bed(scene, matrix, triangles, settings):
    """A separate bed under the pieces fills the visible joints without
    changing them: the whole face, from 0.2 mm up to the recess below the top."""
    from core.group import Group
    from core.mesh import Mesh
    loops = geometry.grout_loops(triangles, GROUT_CLEARANCE_M)
    if not any(geometry.area(loop) > 0 for loop in loops):
        raise FloorError('La cara base es demasiado estrecha para el relleno de juntas.')
    height = settings.get('depth_m', 0.02) - settings.get('grout_recess_m', 0.002) - GROUT_CLEARANCE_M
    if height <= 0.0001:
        raise FloorError('El rebaje de la junta debe ser menor que el espesor.')
    material = _material(scene, settings.get('grout_material') or GROUT_MAT, GROUT_MAT)
    bed = Mesh()
    for outer, holes, _coords in _prism_faces(loops, height):
        f = bed.add_face([QVector3D(p[0], p[1], p[2]) for p in outer],
                         [[QVector3D(p[0], p[1], p[2]) for p in h] for h in holes] or None)
        f.attrs = material.face_attrs()
    group = Group(bed, name='Relleno de juntas')
    place = QMatrix4x4(matrix)
    place.translate(0, 0, GROUT_CLEARANCE_M)
    group.xform = place
    group.component = False
    return group


def _matrix(values):
    """QMatrix4x4 from its data() list (column-major)."""
    return QMatrix4x4(*values).transposed()


def floor_data(group):
    data = (getattr(group, 'ext', None) or {}).get(KEY)
    return data if isinstance(data, dict) and 'boundary' in data else None


def make_floor(scene, face, pattern, settings, name=None, host=None):
    """Face → floor container (not yet added to the scene). ``host`` is the
    record of the face it stands on (see place_host)."""
    from core.group import Group
    matrix, boundary, triangles = face_domain(face)
    children, stats = build_parts(scene, matrix, boundary, triangles, pattern, settings, bool(host and host.get('push')))
    floor = Group(name=name or 'PisoGen ARQ · ' + NAMES.get(pattern, pattern))
    floor.adopt(children)
    floor.component = False
    layer = (getattr(face, 'attrs', None) or {}).get('layer')
    if layer is not None:
        floor.layer = layer
    floor.ext = {KEY: {'version': VERSION, 'pattern': pattern, 'settings': dict(settings), 'pose': list(matrix.data()),
                       'boundary': boundary, 'triangles': triangles, 'stats': stats,
                       'first_xform': list(children[0].xform.data()), 'host': host}}
    return floor


def rebuild_floor(scene, floor, pattern, settings, found=None):
    """New parameters, same place: the pieces are laid again on the face
    the floor was made on, wherever the floor has been moved since.
    ``found`` is (mesh, face) of its host from find_host: the slab first
    goes back to where it was, then the new level applies."""
    data = floor_data(floor)
    if data is None:
        raise FloorError('«%s» no es un piso de PisoGen ARQ.' % floor.name)
    host = data.get('host')
    if found is not None:
        mesh, face = found
        if host.get('push'):
            move_face(mesh, face, [-c for c in host['push']])
        host = place_host(mesh, face, host_record(face), settings)
    # Where the floor stands now: the move since it was made is what turned
    # its first piece; the new pieces get the same move.
    pose = _matrix(data['pose'])
    if floor.children and data.get('first_xform'):
        moved = floor.children[0].xform * _matrix(data['first_xform']).inverted()[0]
        pose = moved * pose
    lowered = found is not None and bool(host.get('push'))
    children, stats = build_parts(scene, pose, data['boundary'], data['triangles'], pattern, settings, lowered)
    floor.children = children
    old_name = 'PisoGen ARQ · ' + NAMES.get(data['pattern'], data['pattern'])
    if floor.name == old_name:
        floor.name = 'PisoGen ARQ · ' + NAMES.get(pattern, pattern)
    ext = dict(floor.ext or {})
    ext[KEY] = dict(data, version=VERSION, pattern=pattern, settings=dict(settings), stats=stats,
                    pose=list(pose.data()), first_xform=list(children[0].xform.data()), host=host)
    floor.ext = ext


# ---------------------------------------------------------------------------
# The host face: level with it, a slab top goes down by the floor's depth so
# the finish sits on the slab instead of inside it (SketchUp r11 does the
# same). IngeTrazo faces cannot be hidden, so a face that cannot go down
# stays where it is and the floor stands 0.5 mm above it.
# ---------------------------------------------------------------------------

def _loops(face):
    return [list(face.loop)] + [list(h) for h in face.hole_loops]


def _up(face):
    z = _unit(_xyz(face.normal()))
    return (-z[0], -z[1], -z[2]) if z[2] < -0.5 else z


def _outline_key(points):
    return tuple(sorted(tuple(round(c * 1e5) for c in p) for p in points))


def host_record(face):
    """What a floor keeps to find its face again: the outline, and how far it
    was pushed (None while it is in its original place)."""
    return {'loop': [list(_xyz(v.position)) for v in face.loop], 'push': None}


def slab_push(mesh, face, depth):
    """The move (world metres) that lowers the face by depth, or None. It
    goes down when every edge meets only walls square to it, below it and at
    least depth plus 1 mm tall, or nothing at all (a loose face)."""
    up = _up(face)
    origin = _xyz(face.loop[0].position)
    below = above = 0.0
    for loop in _loops(face):
        for i in range(len(loop)):
            edge = mesh.find_edge(loop[i], loop[(i + 1) % len(loop)])
            if edge is None:
                return None
            others = [f for f in edge.faces if f is not face]
            if len(others) > 1:
                return None
            for other in others:
                if abs(_dot(up, _unit(_xyz(other.normal())))) > 1e-3:
                    return None
                for p in other.vertices:
                    offset = _dot(_sub(_xyz(p), origin), up)
                    below, above = max(below, -offset), max(above, offset)
    if above > 1e-6 or (below > 0 and below < depth + 0.001):
        return None
    return [-c * depth for c in up]


def move_face(mesh, face, delta):
    step = QVector3D(*delta)
    seen = set()
    for loop in _loops(face):
        for vertex in loop:
            if id(vertex) not in seen:
                seen.add(id(vertex))
                mesh.move_vertex(vertex, step)


def place_host(mesh, face, record, settings):
    """Lowers the face when the floor goes level with it and it can go down;
    returns the record to keep."""
    if record is None or settings.get('base_level') != 'flush':
        return record
    push = slab_push(mesh, face, settings.get('depth_m', 0.02))
    if push is None:
        return record
    move_face(mesh, face, push)
    return dict(host_record(face), push=push)


def _all_groups(scene):
    stack, out = list(scene.groups), []
    while stack:
        group = stack.pop()
        out.append(group)
        stack.extend(getattr(group, 'children', None) or ())
    return out


def mesh_shared(scene, mesh):
    """Whether more than one group draws this mesh."""
    return sum(1 for group in _all_groups(scene) if getattr(group, 'mesh', None) is mesh) > 1


def host_meshes(scene):
    """The loose mesh and the meshes of plain groups, nested ones too;
    component instances are left alone, because changing one changes all."""
    out = [scene.mesh]
    stack = list(scene.groups)
    while stack:
        group = stack.pop()
        if floor_data(group) is not None or getattr(group, 'xform', None) is not None:
            continue
        mesh = getattr(group, 'mesh', None)
        if mesh is not None:
            out.append(mesh)
        stack.extend(getattr(group, 'children', None) or ())
    return out


def find_host(scene, record):
    """(mesh, face) of a floor's host face where it is now, or None."""
    if not record:
        return None
    wanted = _outline_key(record['loop'])
    for mesh in host_meshes(scene):
        for face in mesh.faces:
            if len(face.loop) == len(wanted) and _outline_key([_xyz(v.position) for v in face.loop]) == wanted:
                return mesh, face
    return None
