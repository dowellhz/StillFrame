#!/usr/bin/env python3
"""Place the controller tray and rounded joiner together on one X2D plate."""

from pathlib import Path
import math
import struct


ROOT = Path("/Volumes/ACASIS/e-ink/design/bambu-x2d-stl")
OUTPUT = ROOT / "05-controller-tray-and-rounded-joiner.stl"

# Both parts lie flat on one X2D plate with generous separation.
PLACEMENTS = (
    (ROOT / "06-power-bank-board-case.stl", 0.0, 34.0, 0.0),
    (ROOT / "04-rounded-back-joiner.stl", 0.0, -90.0, 0.0),
)


def read(path, offset):
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    triangles = []
    ox, oy, oz = offset
    for index in range(count):
        values = struct.unpack_from("<9f", data, 96 + index * 50)
        triangles.append(tuple(
            (values[start] + ox, values[start + 1] + oy, values[start + 2] + oz)
            for start in (0, 3, 6)
        ))
    return triangles


def normal(a, b, c):
    ux, uy, uz = (b[i] - a[i] for i in range(3))
    vx, vy, vz = (c[i] - a[i] for i in range(3))
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return nx / length, ny / length, nz / length


triangles = []
for path, x, y, z in PLACEMENTS:
    triangles.extend(read(path, (x, y, z)))

data = bytearray(b"Stillframe X2D combined accessories".ljust(80, b"\0"))
data += struct.pack("<I", len(triangles))
for a, b, c in triangles:
    data += struct.pack("<12fH", *normal(a, b, c), *a, *b, *c, 0)
OUTPUT.write_bytes(data)
print(f"Generated {OUTPUT.name} with power/board housing and rounded joiner: {len(triangles)} triangles")
