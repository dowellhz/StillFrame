#!/usr/bin/env python3
"""Remove exact shared-edge contacts while preserving functional dimensions.

The Blender source joins touching closed primitives without a boolean union.
Slicers then see a few edges used by four triangles. A 0.05 mm controlled
overlap removes those ambiguous coincident edges and is far below FDM tolerance.
"""

from collections import defaultdict
from pathlib import Path
import math
import struct


ROOT = Path("/Volumes/ACASIS/e-ink/design/bambu-x2d-stl")
OVERLAP = 0.05


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


def bounds(triangles, component):
    vertices = [vertex for index in component for vertex in triangles[index]]
    return [(min(v[axis] for v in vertices), max(v[axis] for v in vertices)) for axis in range(3)]


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


def repair_shell(path):
    header, triangles = read(path)
    for component in components(triangles):
        (xmin, xmax), (_, _), (zmin, zmax) = bounds(triangles, component)
        if abs(zmin - 1.2) > 0.001 or abs(zmax - 2.6) > 0.001:
            continue
        horizontal_flange = xmax - xmin > 200
        for index in component:
            for vertex in triangles[index]:
                if abs(vertex[2] - 1.2) < 0.001:
                    vertex[2] = 1.2 - OVERLAP
                if horizontal_flange:
                    if abs(vertex[0] - xmin) < 0.001:
                        vertex[0] = -104.8 - OVERLAP
                    elif abs(vertex[0] - xmax) < 0.001:
                        vertex[0] = 104.8 + OVERLAP
    write(path, header, triangles)


def repair_tray(path):
    header, triangles = read(path)
    for component in components(triangles):
        (xmin, xmax), (ymin, ymax), (zmin, zmax) = bounds(triangles, component)
        if zmax < 7.8:
            continue
        x_narrow = xmax - xmin < 2.0
        y_narrow = ymax - ymin < 2.0
        for index in component:
            for vertex in triangles[index]:
                if x_narrow:
                    if abs(vertex[0] + 33.6) < 0.001: vertex[0] = -33.55
                    if abs(vertex[0] + 31.9) < 0.001: vertex[0] = -31.85
                    if abs(vertex[0] - 31.9) < 0.001: vertex[0] = 31.85
                    if abs(vertex[0] - 33.6) < 0.001: vertex[0] = 33.55
                    if abs(vertex[1] + 48.05) < 0.001: vertex[1] = -48.0
                    if abs(vertex[1] - 48.05) < 0.001: vertex[1] = 48.0
                elif y_narrow:
                    if abs(vertex[0] + 33.6) < 0.001: vertex[0] = -31.95
                    if abs(vertex[0] - 33.6) < 0.001: vertex[0] = 31.95
                    if abs(vertex[1] - 46.35) < 0.001: vertex[1] = 46.30
                    if abs(vertex[1] - 48.05) < 0.001: vertex[1] = 48.0
    write(path, header, triangles)


repair_shell(ROOT / "01-shell-top.stl")
repair_shell(ROOT / "02-shell-bottom-fpc-slots.stl")
repair_tray(ROOT / "03-controller-board-tray.stl")
print("Repaired exact shared-edge contacts in shell and tray STLs")
