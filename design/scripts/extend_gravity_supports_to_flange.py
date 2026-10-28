#!/usr/bin/env python3
"""Extend both portrait gravity rails down to the bottom bonding flange."""

from collections import defaultdict
from pathlib import Path
import math
import struct


PATH = Path("/Volumes/ACASIS/e-ink/design/bambu-x2d-stl/02-shell-bottom-fpc-slots.stl")
OLD_BOTTOM_Y = -47.0625
NEW_BOTTOM_Y = -72.8625  # 0.05 mm overlap into the bottom flange
TOP_Y = -43.0625


def normal(a, b, c):
    ux, uy, uz = (b[i] - a[i] for i in range(3))
    vx, vy, vz = (c[i] - a[i] for i in range(3))
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (nx / length, ny / length, nz / length)


data = PATH.read_bytes()
count = struct.unpack_from("<I", data, 80)[0]
triangles = []
for index in range(count):
    raw = struct.unpack_from("<9f", data, 84 + index * 50 + 12)
    triangles.append([[raw[start], raw[start + 1], raw[start + 2]] for start in range(0, 9, 3)])

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

seen, extended = set(), 0
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
    vertices = [vertex for index in component for vertex in triangles[index]]
    xmin, xmax = min(v[0] for v in vertices), max(v[0] for v in vertices)
    ymin, ymax = min(v[1] for v in vertices), max(v[1] for v in vertices)
    zmin, zmax = min(v[2] for v in vertices), max(v[2] for v in vertices)
    if (xmax - xmin < 45 and abs(ymin - OLD_BOTTOM_Y) < 0.01 and
            abs(ymax - TOP_Y) < 0.01 and zmin > 1.1 and zmax > 2.5):
        for index in component:
            for vertex in triangles[index]:
                if abs(vertex[1] - OLD_BOTTOM_Y) < 0.01:
                    vertex[1] = NEW_BOTTOM_Y
        extended += 1

if extended != 2:
    raise ValueError(f"expected two gravity rails, extended {extended}")

output = bytearray(data[:80] + struct.pack("<I", len(triangles)))
for triangle in triangles:
    output += struct.pack("<12fH", *normal(*triangle), *triangle[0], *triangle[1], *triangle[2], 0)
PATH.write_bytes(output)
print("Extended both gravity rails to overlap the bottom flange by 0.05 mm")
