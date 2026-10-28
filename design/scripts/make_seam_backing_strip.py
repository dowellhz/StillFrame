#!/usr/bin/env python3
"""Create two flat side-rail seam plates as a binary STL."""

from pathlib import Path
import math
import struct


OUTPUT = Path("/Volumes/ACASIS/e-ink/design/bambu-x2d-stl/04-side-seam-plates.stl")
WIDTH = 12.0
DEPTH = 30.0
THICKNESS = 0.8
CENTRES = (-10.0, 10.0)


vertices, faces = [], []
for centre in CENTRES:
    first = len(vertices)
    vertices.extend([
        (centre - WIDTH / 2, -DEPTH / 2, 0.0),
        (centre + WIDTH / 2, -DEPTH / 2, 0.0),
        (centre + WIDTH / 2,  DEPTH / 2, 0.0),
        (centre - WIDTH / 2,  DEPTH / 2, 0.0),
        (centre - WIDTH / 2, -DEPTH / 2, THICKNESS),
        (centre + WIDTH / 2, -DEPTH / 2, THICKNESS),
        (centre + WIDTH / 2,  DEPTH / 2, THICKNESS),
        (centre - WIDTH / 2,  DEPTH / 2, THICKNESS),
    ])
    faces.extend([tuple(first + i for i in face) for face in [
        (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
        (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
    ]])


def normal(a, b, c):
    ux, uy, uz = (b[i] - a[i] for i in range(3))
    vx, vy, vz = (c[i] - a[i] for i in range(3))
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    return (nx / length, ny / length, nz / length)


header = b"Stillframe two side-rail seam plates".ljust(80, b"\0")
data = bytearray(header + struct.pack("<I", len(faces)))
for face in faces:
    triangle = [vertices[index] for index in face]
    data += struct.pack("<12fH", *normal(*triangle), *triangle[0], *triangle[1], *triangle[2], 0)

OUTPUT.write_bytes(data)
print(f"Wrote {OUTPUT}: two {WIDTH} x {DEPTH} x {THICKNESS} mm plates")
