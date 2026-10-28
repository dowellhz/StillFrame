#!/usr/bin/env python3
"""Shift all three FPC slots 16 mm left to match the physical assembly photo."""

from collections import defaultdict
from pathlib import Path
import math
import struct


PATH = Path("/Volumes/ACASIS/e-ink/design/bambu-x2d-stl/02-shell-bottom-fpc-slots.stl")
SHIFT_X = -16.0
OLD_SLOT_MIN_X = -81.16
OLD_SLOT_MAX_X = -47.16
SLOT_REGION_MIN_Y = -70.70
SLOT_REGION_MAX_Y = -51.67
OLD_SUPPORT_MAX_X = -81.91
NEW_SUPPORT_MAX_X = -97.91


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

slot_vertices = 0
support_vertices = 0
for triangle in triangles:
    for vertex in triangle:
        if (OLD_SLOT_MIN_X - 0.01 <= vertex[0] <= OLD_SLOT_MAX_X + 0.01 and
                SLOT_REGION_MIN_Y <= vertex[1] <= SLOT_REGION_MAX_Y and
                vertex[2] <= 1.21):
            vertex[0] += SHIFT_X
            slot_vertices += 1
        elif (abs(vertex[0] - OLD_SUPPORT_MAX_X) < 0.01 and
              -47.1 <= vertex[1] <= -43.0 and vertex[2] >= 1.14):
            vertex[0] = NEW_SUPPORT_MAX_X
            support_vertices += 1

if slot_vertices == 0 or support_vertices == 0:
    raise ValueError(f"expected slot/support vertices, got {slot_vertices}/{support_vertices}")

output = bytearray(data[:80] + struct.pack("<I", len(triangles)))
for triangle in triangles:
    output += struct.pack("<12fH", *normal(*triangle), *triangle[0], *triangle[1], *triangle[2], 0)
PATH.write_bytes(output)
print(f"Shifted FPC slot vertices: {slot_vertices}; adjusted support vertices: {support_vertices}")
