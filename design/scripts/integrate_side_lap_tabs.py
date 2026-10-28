#!/usr/bin/env python3
"""Move the two outer seam tabs under the thick side rails.

The upper-shell tabs become 10.4 x 15 x 1.1 mm tongues. Matching lower-shell
base sockets become 10.8 x 15.3 mm blind slots covered by the 1.4 mm side
rails. This adds two horizontal glue faces without separate connector parts.
"""

from collections import defaultdict
from pathlib import Path
import math
import struct


ROOT = Path("/Volumes/ACASIS/e-ink/design/bambu-x2d-stl")
SEAM_Y = 84.8125
OLD_TAB_CENTRES = (-90.0, 90.0)
NEW_TAB_CENTRES = (-110.8, 110.8)
OLD_TAB_W = 18.0
NEW_TAB_W = 10.4
OLD_SOCKET_W = 18.5
NEW_SOCKET_W = 10.8
OLD_DEPTH = 8.0
NEW_DEPTH = 15.0
OLD_SOCKET_DEPTH = 8.3
NEW_SOCKET_DEPTH = 15.3
TAB_T = 1.1


def read(path):
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    triangles = []
    for index in range(count):
        raw = struct.unpack_from("<9f", data, 84 + index * 50 + 12)
        triangles.append([[raw[start], raw[start + 1], raw[start + 2]] for start in range(0, 9, 3)])
    return data[:80], triangles


def components(triangles):
    edges = defaultdict(list)
    for triangle_index, triangle in enumerate(triangles):
        rounded = [tuple(round(value, 5) for value in vertex) for vertex in triangle]
        for a, b in ((rounded[0], rounded[1]), (rounded[1], rounded[2]), (rounded[2], rounded[0])):
            edges[tuple(sorted((a, b)))].append(triangle_index)
    adjacency = [set() for _ in triangles]
    for owners in edges.values():
        if len(owners) == 2:
            a, b = owners
            adjacency[a].add(b)
            adjacency[b].add(a)
    result, seen = [], set()
    for start in range(len(triangles)):
        if start in seen:
            continue
        stack, component = [start], []
        seen.add(start)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbour in adjacency[current]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    stack.append(neighbour)
        result.append(component)
    return result


def normal(a, b, c):
    ux, uy, uz = (b[i] - a[i] for i in range(3))
    vx, vy, vz = (c[i] - a[i] for i in range(3))
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (nx / length, ny / length, nz / length)


def write(path, header, triangles):
    output = bytearray(header + struct.pack("<I", len(triangles)))
    for triangle in triangles:
        output += struct.pack("<12fH", *normal(*triangle), *triangle[0], *triangle[1], *triangle[2], 0)
    path.write_bytes(output)


def move_upper_tabs(path):
    header, triangles = read(path)
    moved = 0
    for component in components(triangles):
        vertices = [vertex for index in component for vertex in triangles[index]]
        xmin, xmax = min(v[0] for v in vertices), max(v[0] for v in vertices)
        ymin, ymax = min(v[1] for v in vertices), max(v[1] for v in vertices)
        for old_centre, new_centre in zip(OLD_TAB_CENTRES, NEW_TAB_CENTRES):
            if abs((xmin + xmax) / 2 - old_centre) > 0.01 or abs(ymax + SEAM_Y) > 0.01:
                continue
            for index in component:
                for vertex in triangles[index]:
                    vertex[0] = new_centre + (vertex[0] - old_centre) * NEW_TAB_W / OLD_TAB_W
                    vertex[1] = -SEAM_Y - (-(vertex[1] + SEAM_Y)) * NEW_DEPTH / OLD_DEPTH
                    if vertex[2] > TAB_T:
                        vertex[2] = TAB_T
            moved += 1
    if moved != 2:
        raise ValueError(f"expected two outer tabs, moved {moved}")
    write(path, header, triangles)


def move_lower_sockets(path):
    header, triangles = read(path)
    changed = [0, 0]
    for triangle in triangles:
        for vertex in triangle:
            for index, (old_centre, new_centre) in enumerate(zip(OLD_TAB_CENTRES, NEW_TAB_CENTRES)):
                if not (old_centre - OLD_SOCKET_W / 2 - 0.01 <= vertex[0] <= old_centre + OLD_SOCKET_W / 2 + 0.01):
                    continue
                if vertex[1] < SEAM_Y - OLD_SOCKET_DEPTH - 0.01:
                    continue
                vertex[0] = new_centre + (vertex[0] - old_centre) * NEW_SOCKET_W / OLD_SOCKET_W
                vertex[1] = SEAM_Y - (SEAM_Y - vertex[1]) * NEW_SOCKET_DEPTH / OLD_SOCKET_DEPTH
                changed[index] += 1
                break
    if not all(changed):
        raise ValueError(f"socket vertices not found: {changed}")
    write(path, header, triangles)


move_upper_tabs(ROOT / "01-shell-top.stl")
move_lower_sockets(ROOT / "02-shell-bottom-fpc-slots.stl")
print("Integrated two side-rail lap tabs into the upper/lower shells")
