# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alfonso Rodríguez
"""Texture placement per piece, as the SketchUp version paints it.

``uv_mapper`` is the port of ``paint_piece`` in main.rb: the image follows
the board (its texture box or frame), is fitted along its length, across its
width or at the image's real size, turned 0/90/180/270° plus a seeded random
turn, mirrored, shifted, and every irregular stone gets its own window of
the image. It returns a function from a piece's texture coordinate (metres,
pattern space: the top face's XY, a wall unfolded outwards, or the bevel
chart) to image UV (1 = one image).

Seeds use SHA-256 like main.rb, so a floor shows the same variation in both
programs.
"""
import hashlib

from ..core.paving import _jstr

TEXTURE_VARIANTS = 8
STONE_UV_MARGIN_M = 0.005


def _digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _word(digest, start):
    return int(digest[start:start + 8], 16)


def randomized(settings):
    """True when pieces need their own texture variant."""
    return bool(settings.get('texture_random') or settings.get('texture_flip') or settings.get('texture_flip_u') or
                settings.get('texture_flip_v') or settings.get('texture_random_v') or
                (settings.get('texture_random_rotation') or 'none') != 'none')


def texture_id(piece, settings):
    """Which seed paints the piece: one of TEXTURE_VARIANTS when randomized
    (equal pieces still share a few component variants)."""
    if randomized(settings):
        variant = _word(_digest(f"texture:{_jstr(settings.get('material_seed', 1))}:{piece['id']}"), 0) % TEXTURE_VARIANTS
        return f'variant:{variant}'
    return piece['id']


def frame_extent(piece):
    frame = piece['texture_frame_m']
    axis, origin = frame['axis'], frame['origin_uv_m']
    points = [p for poly in piece['polygons_m'] for p in poly]
    return (max(x * axis[0] + y * axis[1] - origin[0] for x, y in points),
            max(-x * axis[1] + y * axis[0] - origin[1] for x, y in points))


def stone_extent(pieces, settings):
    """Floor-wide texture window for irregular stones: largest stone plus
    the walls unfolded on both sides."""
    if settings.get('texture_mode') == 'continuous':
        return None
    extents = [frame_extent(p) for p in pieces if p.get('texture_frame_m')]
    if not extents:
        return None
    margin = settings.get('depth_m', 0.02) + STONE_UV_MARGIN_M
    return (max(e[0] for e in extents) + 2 * margin, max(e[1] for e in extents) + 2 * margin)


def _fit_width(piece, settings, along_x, box, xs, ys):
    pattern = settings.get('pattern')
    joint = settings.get('joint_m', 0.003)
    side = settings.get('side_m', 0.3)
    if pattern == 'basketweave':
        return side / 3.0 - joint
    if pattern in ('adopasto', 'adopasto_reja'):
        size = side - joint
        if pattern == 'adopasto_reja':
            return settings.get('reja_opening_m', 0.085) if piece['role'] == 'insert' else side
        return size - 2 * settings.get('grass_frame_m', 0.03) if piece['role'] == 'insert' else size
    if pattern == 'octagon':
        import math
        raw_side = side + joint * math.tan(math.pi / 8)
        return raw_side - joint if piece['role'] == 'insert' else (1 + math.sqrt(2)) * raw_side - joint
    if pattern == 'irregular':
        return side
    if pattern == 'hexagon':
        return 3 ** 0.5 * side
    if pattern in ('wood', 'brick', 'tile', 'strip', 'herringbone', 'chevron'):
        return settings.get('width_m', 0.18)
    if box:
        return box[3] if along_x else box[2]
    return (max(ys) - min(ys)) if along_x else (max(xs) - min(xs))


def uv_mapper(piece, settings, ratio, tex_id, stone=None):
    """Function texture coordinate (x, y metres) → image (u, v) for one piece.
    ``ratio`` is the image height / width."""
    points = [p for poly in piece['polygons_m'] for p in poly]
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    along_x = list(piece.get('grain_axis') or [1, 0]) == [1, 0]
    min_x, min_y = min(xs), min(ys)
    span = (max(xs) - min_x) if along_x else (max(ys) - min_y)
    # A cut rectangle maps like its uncut piece: the image is cropped,
    # never squeezed into a remainder a few millimetres wide.
    box = piece.get('texture_box_m')
    if box:
        min_x, min_y = box[0], box[1]
        span = box[2] if along_x else box[3]
    frame = piece.get('texture_frame_m')
    if frame:
        span = frame['length_m']
        axis, origin = frame['axis'], frame['origin_uv_m']
        # A rotated rectangular piece names its cross axis; others use +90°.
        cross = frame.get('cross_axis') or [-axis[1], axis[0]]

        def project(c):
            return (c[0] * axis[0] + c[1] * axis[1] - origin[0], c[0] * cross[0] + c[1] * cross[1] - origin[1])
    else:
        project = None
    piece_length = span
    rotation = settings.get('texture_rotation_deg', 0)
    quarter = rotation in (90, 270)
    half_turn = rotation in (180, 270)
    seed = _jstr(settings.get('material_seed', 1))
    continuous = settings.get('texture_mode') == 'continuous'
    extra_turns = 0
    random_rotation = settings.get('texture_random_rotation') or 'none'
    if random_rotation != 'none' and not continuous:
        turns = _word(_digest(f'rotation:{seed}:{tex_id}'), 0)
        extra_turns = turns % 4 if random_rotation == 'quarter' else 2 * (turns % 2)
    fit = settings.get('texture_fit', 'length')
    if fit == 'manual' or continuous:
        # Real width of the image in metres; its height keeps the proportion.
        width = settings.get('texture_width_m', 0.5)
        span = width * ratio if quarter else width
    elif fit == 'width':
        width = _fit_width(piece, settings, along_x, box, xs, ys)
        span = width * ratio if quarter else width / ratio
    shift = shift_v = 0.0
    reverse = False
    if settings.get('texture_random') and not continuous:
        digest = _digest(f'texture:{seed}:{tex_id}')
        shift = max(span - piece_length, 0.0) * _word(digest, 0) / 4294967295.0
        reverse = _word(digest, 8) % 2 == 1
    flip_v = False
    flip_u_on = settings.get('texture_flip') or settings.get('texture_flip_u')
    flip_v_on = settings.get('texture_flip') or settings.get('texture_flip_v')
    if (flip_u_on or flip_v_on) and not continuous:
        # Seeded mirror per piece, along (U) and across (V) the grain.
        digest = _digest(f'flip:{seed}:{tex_id}')
        if flip_u_on and _word(digest, 0) % 2 == 1:
            reverse = not reverse
        flip_v = bool(flip_v_on and _word(digest, 8) % 2 == 1)

    def across():
        if frame:
            return max(project(p)[1] for p in points)
        return (max(ys) - min_y) if along_x else (max(xs) - min_x)

    if settings.get('texture_random_v') and not continuous:
        # Seeded shift across the grain within the image left over beside the piece.
        cover = span / ratio if quarter else span * ratio
        shift_v = max(cover - across(), 0.0) * _word(_digest(f'texture_v:{seed}:{tex_id}'), 0) / 4294967295.0
    if frame and stone:
        # Irregular stones: one floor-wide scale covering the largest stone
        # plus its unfolded walls; each stone its own seeded window.
        margin = settings.get('depth_m', 0.02) + STONE_UV_MARGIN_M
        own_u, own_v = frame_extent(piece)
        span = max(stone[0], stone[1] * ratio if quarter else stone[1] / ratio)
        cover_v = span / ratio if quarter else span * ratio
        piece_length = own_u
        digest = _digest(f'stone:{seed}:{tex_id}')
        shift = margin + max(span - (own_u + 2 * margin), 0.0) * _word(digest, 0) / 4294967295.0
        shift_v = margin + max(cover_v - (own_v + 2 * margin), 0.0) * _word(digest, 16) / 4294967295.0
    # Mirror across the grain about the piece's own width.
    cross_extent = across() if flip_v else 0.0
    offset_u = settings.get('texture_offset_u_m') or 0.0
    offset_v = settings.get('texture_offset_v_m') or 0.0
    image_w, image_h = (span / ratio, span) if quarter else (span, span * ratio)
    if span <= 1e-9:
        raise ValueError('No se pudo definir el mapeo de textura.')

    def uv(coordinate):
        if project:
            u, v = project(coordinate)
        else:
            u = coordinate[0] - min_x if along_x else coordinate[1] - min_y
            v = coordinate[1] - min_y if along_x else coordinate[0] - min_x
        if reverse:
            u = piece_length - u
        if flip_v:
            v = cross_extent - v
        u += shift + offset_u
        v += shift_v + offset_v
        # Rotate in the physical image frame, keeping its aspect ratio.
        px, py = (-v, u) if quarter else (u, v)
        if half_turn:
            px, py = -px, -py
        for _ in range(extra_turns):
            px, py = -py, px
        return (px / image_w, py / image_h)

    return uv
