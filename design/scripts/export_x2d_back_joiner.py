#!/usr/bin/env python3
"""Generate a simple rounded back plate for gluing the two shell halves."""

from pathlib import Path
import math
import struct


OUT = Path("/Volumes/ACASIS/e-ink/design/bambu-x2d-stl/04-rounded-back-joiner.stl")
WIDTH = 160.0
HEIGHT = 28.0
THICKNESS = 0.8
RADIUS = 7.0
SEGMENTS_PER_CORNER = 10


def outline():
    points = []
    centres = [
        (WIDTH / 2 - RADIUS, HEIGHT / 2 - RADIUS, 0.0),
        (-WIDTH / 2 + RADIUS, HEIGHT / 2 - RADIUS, 90.0),
        (-WIDTH / 2 + RADIUS, -HEIGHT / 2 + RADIUS, 180.0),
        (WIDTH / 2 - RADIUS, -HEIGHT / 2 + RADIUS, 270.0),
    ]
    for cx, cy, start in centres:
        for index in range(SEGMENTS_PER_CORNER + 1):
            angle = math.radians(start + 90.0 * index / SEGMENTS_PER_CORNER)
            point = (cx + RADIUS * math.cos(angle), cy + RADIUS * math.sin(angle))
            if not points or point != points[-1]:
                points.append(point)
    return points


def triangles():
    ring = outline()
    result = []
    top_centre = (0.0, 0.0, THICKNESS)
    bottom_centre = (0.0, 0.0, 0.0)
    for index, (x0, y0) in enumerate(ring):
        x1, y1 = ring[(index + 1) % len(ring)]
        result.append((top_centre, (x0, y0, THICKNESS), (x1, y1, THICKNESS)))
        result.append((bottom_centre, (x1, y1, 0.0), (x0, y0, 0.0)))
        result.append(((x0, y0, 0.0), (x1, y1, THICKNESS), (x1, y1, 0.0)))
        result.append(((x0, y0, 0.0), (x0, y0, THICKNESS), (x1, y1, THICKNESS)))
    return result


def normal(a, b, c):
    ux, uy, uz = (b[i] - a[i] for i in range(3))
    vx, vy, vz = (c[i] - a[i] for i in range(3))
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return nx / length, ny / length, nz / length


mesh = triangles()
data = bytearray(b"Stillframe rounded back joiner".ljust(80, b"\0"))
data += struct.pack("<I", len(mesh))
for a, b, c in mesh:
    data += struct.pack("<12fH", *normal(a, b, c), *a, *b, *c, 0)
OUT.write_bytes(data)
print(f"Generated {OUT.name}: {WIDTH:g} x {HEIGHT:g} x {THICKNESS:g} mm, R{RADIUS:g}")
