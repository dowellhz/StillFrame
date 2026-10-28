#!/usr/bin/env python3
"""Keep one 38 x 3 mm FPC opening at X=-48.16 mm.

Input is the current three-slot shell with centres at X=-80.16 mm. The middle
slot boundary is moved and widened; the other two slots are closed by slightly
overlapping watertight inserts so slicers produce a solid base.
"""

from pathlib import Path
import math
import struct


PATH = Path("/Volumes/ACASIS/e-ink/design/bambu-x2d-stl/02-shell-bottom-fpc-slots.stl")
CURRENT_X = -80.16
FINAL_X = -48.16
CURRENT_W = 34.0
FINAL_W = 38.0
MIDDLE_Y = -61.1875
CLOSED_SLOT_YS = (-53.1875, -69.1875)
OLD_SUPPORT_MAX_X = -97.91
NEW_SUPPORT_MAX_X = -65.91


def normal(a, b, c):
    ux, uy, uz = (b[i] - a[i] for i in range(3))
    vx, vy, vz = (c[i] - a[i] for i in range(3))
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (nx / length, ny / length, nz / length)


def add_box(triangles, cx, cy, sx, sy, z0, z1):
    first = [
        [cx - sx / 2, cy - sy / 2, z0], [cx + sx / 2, cy - sy / 2, z0],
        [cx + sx / 2, cy + sy / 2, z0], [cx - sx / 2, cy + sy / 2, z0],
        [cx - sx / 2, cy - sy / 2, z1], [cx + sx / 2, cy - sy / 2, z1],
        [cx + sx / 2, cy + sy / 2, z1], [cx - sx / 2, cy + sy / 2, z1],
    ]
    faces = [
        (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
        (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
    ]
    triangles.extend([[first[a], first[b], first[c]] for a, b, c in faces])


data = PATH.read_bytes()
count = struct.unpack_from("<I", data, 80)[0]
triangles = []
for index in range(count):
    raw = struct.unpack_from("<9f", data, 84 + index * 50 + 12)
    triangles.append([[raw[start], raw[start + 1], raw[start + 2]] for start in range(0, 9, 3)])

moved = 0
support = 0
for triangle in triangles:
    for vertex in triangle:
        if (abs(vertex[1] - MIDDLE_Y) <= 1.51 and
                CURRENT_X - CURRENT_W / 2 - 0.01 <= vertex[0] <= CURRENT_X + CURRENT_W / 2 + 0.01 and
                vertex[2] <= 1.21):
            vertex[0] = FINAL_X + (vertex[0] - CURRENT_X) * FINAL_W / CURRENT_W
            moved += 1
        elif (abs(vertex[0] - OLD_SUPPORT_MAX_X) < 0.01 and
              -47.1 <= vertex[1] <= -43.0 and vertex[2] >= 1.14):
            vertex[0] = NEW_SUPPORT_MAX_X
            support += 1

if moved == 0 or support == 0:
    raise ValueError(f"expected opening/support vertices, got {moved}/{support}")

for y in CLOSED_SLOT_YS:
    add_box(triangles, CURRENT_X, y, 34.4, 3.4, -0.01, 1.21)

output = bytearray(data[:80] + struct.pack("<I", len(triangles)))
for triangle in triangles:
    output += struct.pack("<12fH", *normal(*triangle), *triangle[0], *triangle[1], *triangle[2], 0)
PATH.write_bytes(output)
print(f"Final FPC opening: 38 x 3 mm at X={FINAL_X}; closed two unused slots")
