# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Alfonso Rodríguez
"""Plane geometry for the joint fill, without Qt or the document, so it can
be tested on its own. Same rules as main.rb (SketchUp r10)."""
import math

# Points closer than this merge, as SketchUp merges them (main.rb MERGE_M).
MERGE_M = 0.0001


def area(points):
    return sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(points, points[1:] + points[:1])) / 2.0


def clean(points):
    """Drops repeated and collinear points; None when nothing is left."""
    kept = []
    for p in points:
        if not kept or math.hypot(p[0] - kept[-1][0], p[1] - kept[-1][1]) >= MERGE_M:
            kept.append(list(p))
    while len(kept) > 1 and math.hypot(kept[0][0] - kept[-1][0], kept[0][1] - kept[-1][1]) < MERGE_M:
        kept.pop()
    while len(kept) > 3:
        for i in range(len(kept)):
            a, b, c = kept[i - 1], kept[i], kept[(i + 1) % len(kept)]
            span = math.hypot(c[0] - a[0], c[1] - a[1])
            if abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) < MERGE_M * max(span, MERGE_M):
                del kept[i]
                break
        else:
            break
    return kept if len(kept) >= 3 and abs(area(kept)) > MERGE_M * MERGE_M else None


def _left_normal(a, b):
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    return (a[1] - b[1]) / length, (b[0] - a[0]) / length


def inset_loop(points, distance):
    """Moves every edge of a counter-clockwise outline (clockwise for a hole)
    to its left, toward the inside, by distance; corners are mitred."""
    out = []
    for i, p in enumerate(points):
        before = _left_normal(points[i - 1], p)
        after = _left_normal(p, points[(i + 1) % len(points)])
        scale = distance / max(1 + before[0] * after[0] + before[1] * after[1], 0.1)
        out.append([p[0] + (before[0] + after[0]) * scale, p[1] + (before[1] + after[1]) * scale])
    return out


def grout_loops(triangles, clearance):
    """The bed is one surface per outline: the edges owned by a single
    triangle are chained into loops (counter-clockwise outlines, clockwise
    holes) and pulled back by the clearance. Building it triangle by triangle
    left slits where long thin fan triangles vanished, and their edges showed
    through the stones as diagonal lines."""
    def key(p):
        return (round(p[0] * 1e8), round(p[1] * 1e8))

    counter = [list(reversed(t)) if area(t) < 0 else list(t) for t in triangles]
    owners = {}
    for t in counter:
        for i in range(3):
            edge = tuple(sorted((key(t[i]), key(t[(i + 1) % 3]))))
            owners[edge] = owners.get(edge, 0) + 1
    points = {}
    following = {}
    for t in counter:
        for i in range(3):
            a, b = t[i], t[(i + 1) % 3]
            if owners[tuple(sorted((key(a), key(b))))] != 1:
                continue
            points[key(a)], points[key(b)] = a, b
            following.setdefault(key(a), []).append(key(b))
    loops = []
    while following:
        start = next(iter(following))
        ring, current = [start], start
        while following.get(current):
            step = following[current].pop(0)
            if not following[current]:
                del following[current]
            if step == start:
                break
            ring.append(step)
            current = step
        if current in following and not following[current]:
            del following[current]
        outline = clean([points[k] for k in ring])
        if outline:
            outline = clean(inset_loop(outline, clearance))
        if outline:
            loops.append(outline)
    return loops
