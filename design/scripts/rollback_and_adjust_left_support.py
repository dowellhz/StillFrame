#!/usr/bin/env python3
"""Restore short gravity supports and connect only the left one to the side rail."""

from collections import defaultdict
from pathlib import Path
import math
import struct


PATH = Path("/Volumes/ACASIS/e-ink/design/bambu-x2d-stl/02-shell-bottom-fpc-slots.stl")
CURRENT_BOTTOM_Y = -72.8625
RESTORED_BOTTOM_Y = -47.0625
TOP_Y = -43.0625
LEFT_MIN_X = -104.85
LEFT_MAX_X = -70.16


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

seen, restored = set(), 0
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
    if (abs(ymin - CURRENT_BOTTOM_Y) > 0.01 or abs(ymax - TOP_Y) > 0.01 or
            zmin < 1.1 or zmax < 2.5):
        continue
    for index in component:
        for vertex in triangles[index]:
            if abs(vertex[1] - CURRENT_BOTTOM_Y) < 0.01:
                vertex[1] = RESTORED_BOTTOM_Y
            if xmax < 0:
                if abs(vertex[0] - xmin) < 0.01:
                    vertex[0] = LEFT_MIN_X
                elif abs(vertex[0] - xmax) < 0.01:
                    vertex[0] = LEFT_MAX_X
    restored += 1

if restored != 2:
    raise ValueError(f"expected two extended rails, restored {restored}")

output = bytearray(data[:80] + struct.pack("<I", len(triangles)))
for triangle in triangles:
    output += struct.pack("<12fH", *normal(*triangle), *triangle[0], *triangle[1], *triangle[2], 0)
PATH.write_bytes(output)
print("Restored short supports; connected shortened left support to the left rail")
