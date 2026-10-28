#!/usr/bin/env python3
"""Shorten the left support to a 10 mm stub attached to the left rail."""

from collections import defaultdict
from pathlib import Path
import math
import struct


PATH = Path("/Volumes/ACASIS/e-ink/design/bambu-x2d-stl/02-shell-bottom-fpc-slots.stl")
OLD_MIN_X = -104.85
OLD_MAX_X = -70.16
NEW_MAX_X = -94.85
SUPPORT_MIN_Y = -47.0625
SUPPORT_MAX_Y = -43.0625


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

changed = 0
for triangle in triangles:
    for vertex in triangle:
        if (abs(vertex[0] - OLD_MAX_X) < 0.01 and
                SUPPORT_MIN_Y - 0.01 <= vertex[1] <= SUPPORT_MAX_Y + 0.01 and
                vertex[2] >= 1.14):
            vertex[0] = NEW_MAX_X
            changed += 1

if changed == 0:
    raise ValueError("left support edge not found")

output = bytearray(data[:80] + struct.pack("<I", len(triangles)))
for triangle in triangles:
    output += struct.pack("<12fH", *normal(*triangle), *triangle[0], *triangle[1], *triangle[2], 0)
PATH.write_bytes(output)
print(f"Shortened left support to {NEW_MAX_X - OLD_MIN_X:.2f} mm")
