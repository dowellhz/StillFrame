#!/usr/bin/env python3
"""Resize only the outer X2D bonding flange from 15 mm to 12 mm.

The source STLs were generated with a 15 mm flange. Screen, FPC, supports and
joint coordinates are preserved in assembled/global coordinates; only the four
outer flange regions are compressed. Binary STL normals are recomputed.
"""

from pathlib import Path
import math
import struct


ROOT = Path("/Volumes/ACASIS/e-ink/design/bambu-x2d-stl")
OLD_FLANGE = 15.0
NEW_FLANGE = 12.0
CAVITY_HALF_W = (208.8 + 0.8) / 2
CAVITY_HALF_H = (284.7 + 29.75 + 0.8) / 2
OLD_SHELL_H = 2 * CAVITY_HALF_H + 2 * OLD_FLANGE
NEW_SHELL_H = 2 * CAVITY_HALF_H + 2 * NEW_FLANGE
OLD_PANEL_H = OLD_SHELL_H / 2
NEW_PANEL_H = NEW_SHELL_H / 2


def read_binary_stl(path):
    data = path.read_bytes()
    count = struct.unpack_from("<I", data, 80)[0]
    expected = 84 + count * 50
    if len(data) != expected:
        raise ValueError(f"{path} is not the expected binary STL format")
    triangles = []
    offset = 84
    for _ in range(count):
        values = struct.unpack_from("<12fH", data, offset)
        triangles.append([list(values[3:6]), list(values[6:9]), list(values[9:12])])
        offset += 50
    return data[:80], triangles


def normal(a, b, c):
    ux, uy, uz = (b[i] - a[i] for i in range(3))
    vx, vy, vz = (c[i] - a[i] for i in range(3))
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length == 0:
        return (0.0, 0.0, 0.0)
    return (nx / length, ny / length, nz / length)


def compress_outer_x(x):
    if x > CAVITY_HALF_W:
        return CAVITY_HALF_W + (x - CAVITY_HALF_W) * NEW_FLANGE / OLD_FLANGE
    if x < -CAVITY_HALF_W:
        return -CAVITY_HALF_W + (x + CAVITY_HALF_W) * NEW_FLANGE / OLD_FLANGE
    return x


def transform_vertex(vertex, top_panel):
    x, local_y, z = vertex
    old_centre_y = OLD_PANEL_H / 2 if top_panel else -OLD_PANEL_H / 2
    new_centre_y = NEW_PANEL_H / 2 if top_panel else -NEW_PANEL_H / 2
    global_y = local_y + old_centre_y
    if top_panel and global_y > CAVITY_HALF_H:
        global_y = CAVITY_HALF_H + (global_y - CAVITY_HALF_H) * NEW_FLANGE / OLD_FLANGE
    elif not top_panel and global_y < -CAVITY_HALF_H:
        global_y = -CAVITY_HALF_H + (global_y + CAVITY_HALF_H) * NEW_FLANGE / OLD_FLANGE
    return [compress_outer_x(x), global_y - new_centre_y, z]


def rewrite(path, top_panel):
    header, triangles = read_binary_stl(path)
    vertices = [vertex for triangle in triangles for vertex in triangle]
    actual_width = max(v[0] for v in vertices) - min(v[0] for v in vertices)
    expected_width = 2 * CAVITY_HALF_W + 2 * OLD_FLANGE
    if abs(actual_width - expected_width) > 0.01:
        raise ValueError(
            f"{path.name} width is {actual_width:.3f} mm; expected "
            f"{expected_width:.3f} mm source. Refusing a repeated resize."
        )
    transformed = [[transform_vertex(vertex, top_panel) for vertex in triangle] for triangle in triangles]
    output = bytearray(header)
    output += struct.pack("<I", len(transformed))
    for triangle in transformed:
        n = normal(*triangle)
        output += struct.pack("<12fH", *n, *triangle[0], *triangle[1], *triangle[2], 0)
    path.write_bytes(output)


rewrite(ROOT / "01-shell-top.stl", top_panel=True)
rewrite(ROOT / "02-shell-bottom-fpc-slots.stl", top_panel=False)
print("Resized X2D flange to 12 mm")
