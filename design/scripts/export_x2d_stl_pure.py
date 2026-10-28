#!/usr/bin/env python3
"""Generate the two X2D shell halves without a GUI or mesh booleans.

The model intentionally contains only the back sheet, bonding flanges, three
joining fingers/sockets, one FPC opening, and two short gravity supports.
Every primitive is a closed solid and touching parts overlap by 0.05 mm.
"""

from pathlib import Path
import math
import struct


OUT = Path("/Volumes/ACASIS/e-ink/design/bambu-x2d-stl")
OUT.mkdir(parents=True, exist_ok=True)

SCREEN_W, SCREEN_H = 208.8, 284.7
FPC_EXTENSION, CLEARANCE, FLANGE = 29.75, 0.8, 12.0
PANEL_W = SCREEN_W + CLEARANCE + 2 * FLANGE
SHELL_H = SCREEN_H + FPC_EXTENSION + CLEARANCE + 2 * FLANGE
PANEL_H = SHELL_H / 2
BACK_T, TOP_Z, OVERLAP = 1.2, 2.6, 0.05

TAB_CENTRES = (-45.0, 0.0, 45.0)
TAB_W, TAB_D = 18.0, 8.0
SOCKET_W, SOCKET_D = 18.5, 8.3

FPC_X, FPC_GLOBAL_Y = -48.16, -146.0
FPC_W, FPC_H = 38.0, 3.0

SCREEN_BOTTOM_Y = SHELL_H / 2 - FLANGE - CLEARANCE / 2 - SCREEN_H
SUPPORT_Y_GLOBAL = SCREEN_BOTTOM_Y - 0.4 - 2.0
LEFT_SUPPORT = (-(SCREEN_W + CLEARANCE) / 2 - OVERLAP,
                -SCREEN_W / 2 + 27.0)
RIGHT_SUPPORT = (SCREEN_W / 2 - 27.0,
                 (SCREEN_W + CLEARANCE) / 2 + OVERLAP)


def tri(a, b, c):
    return (a, b, c)


def box(x0, x1, y0, y1, z0, z1):
    v = [(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
         (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
    faces = [(0,2,1),(0,3,2),(4,5,6),(4,6,7),
             (0,1,5),(0,5,4),(1,2,6),(1,6,5),
             (2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    return [tri(v[a], v[b], v[c]) for a,b,c in faces]


def capsule_stations(cx, width, height, segments=12):
    r = height / 2
    straight = width / 2 - r
    values = []
    left = cx - straight
    right = cx + straight
    for i in range(segments + 1):
        dx = -r + r * i / segments
        values.append((left + dx, math.sqrt(max(0.0, r*r - dx*dx))))
    values.append((right, r))
    for i in range(1, segments + 1):
        dx = r * i / segments
        values.append((right + dx, math.sqrt(max(0.0, r*r - dx*dx))))
    return values


def rectangle_with_capsule_hole(x0, x1, y0, y1, z0, z1, cx, cy, width, height):
    """Closed rectangular prism with one horizontal capsule through-hole."""
    ts = []
    stations = capsule_stations(cx, width, height)
    left, right = stations[0][0], stations[-1][0]

    # Flat faces to the left and right. Split the inner edge at the capsule tip
    # so there are no T-junctions or coincident internal faces.
    for z, reverse in ((z1, False), (z0, True)):
        faces = [
            ((x0,y0,z),(left,y0,z),(left,cy,z)),
            ((x0,y0,z),(left,cy,z),(x0,y1,z)),
            ((x0,y1,z),(left,cy,z),(left,y1,z)),
            ((right,y0,z),(x1,y0,z),(x1,y1,z)),
            ((right,y0,z),(x1,y1,z),(right,cy,z)),
            ((right,cy,z),(x1,y1,z),(right,y1,z)),
        ]
        for a,b,c in faces:
            ts.append(tri(a,c,b) if reverse else tri(a,b,c))

    # Top and bottom sheets around the opening, split at capsule stations.
    for (xa, ea), (xb, eb) in zip(stations, stations[1:]):
        at, bt = cy + ea, cy + eb
        ab, bb = cy - ea, cy - eb
        ts += [tri((xa,at,z1),(xb,bt,z1),(xb,y1,z1)),
               tri((xa,at,z1),(xb,y1,z1),(xa,y1,z1)),
               tri((xa,y0,z1),(xb,y0,z1),(xb,bb,z1)),
               tri((xa,y0,z1),(xb,bb,z1),(xa,ab,z1))]
        ts += [tri((xa,at,z0),(xb,y1,z0),(xb,bt,z0)),
               tri((xa,at,z0),(xa,y1,z0),(xb,y1,z0)),
               tri((xa,y0,z0),(xb,bb,z0),(xb,y0,z0)),
               tri((xa,y0,z0),(xa,ab,z0),(xb,bb,z0))]

    # Outer walls. Split the long horizontal walls at the same X stations used
    # by the flat faces, preventing T-junctions in strict mesh validators.
    x_breaks = [x0] + [x for x,_ in stations] + [x1]
    for xa,xb in zip(x_breaks,x_breaks[1:]):
        ts += [tri((xa,y0,z0),(xb,y0,z1),(xb,y0,z0)),
               tri((xa,y0,z0),(xa,y0,z1),(xb,y0,z1)),
               tri((xb,y1,z0),(xa,y1,z1),(xa,y1,z0)),
               tri((xb,y1,z0),(xb,y1,z1),(xa,y1,z1))]
    ts += [tri((x1,y0,z0),(x1,y1,z1),(x1,y1,z0)),
           tri((x1,y0,z0),(x1,y0,z1),(x1,y1,z1)),
           tri((x0,y1,z0),(x0,y0,z1),(x0,y0,z0)),
           tri((x0,y1,z0),(x0,y1,z1),(x0,y0,z1))]

    # Capsule wall: top side left-to-right and bottom side right-to-left. The
    # curves meet at a single vertex at each tip, so no artificial end wall is
    # needed.
    for (xa, ea), (xb, eb) in zip(stations, stations[1:]):
        a, b = (xa, cy+ea), (xb, cy+eb)
        ts += [tri((a[0],a[1],z0),(b[0],b[1],z1),(b[0],b[1],z0)),
               tri((a[0],a[1],z0),(a[0],a[1],z1),(b[0],b[1],z1))]
        a, b = (xb, cy-eb), (xa, cy-ea)
        ts += [tri((a[0],a[1],z0),(b[0],b[1],z1),(b[0],b[1],z0)),
               tri((a[0],a[1],z0),(a[0],a[1],z1),(b[0],b[1],z1))]
    return ts


def write_stl(path, triangles, label):
    header = label.encode("ascii")[:80].ljust(80, b"\0")
    data = bytearray(header + struct.pack("<I", len(triangles)))
    for a,b,c in triangles:
        ux,uy,uz = (b[i]-a[i] for i in range(3))
        vx,vy,vz = (c[i]-a[i] for i in range(3))
        nx,ny,nz = uy*vz-uz*vy, uz*vx-ux*vz, ux*vy-uy*vx
        length = math.sqrt(nx*nx+ny*ny+nz*nz) or 1.0
        data += struct.pack("<12fH", nx/length,ny/length,nz/length, *a,*b,*c, 0)
    path.write_bytes(data)


def top_panel():
    x0,x1 = -PANEL_W/2, PANEL_W/2
    y0,y1 = -PANEL_H/2, PANEL_H/2
    t = box(x0,x1,y0,y1,0,BACK_T)
    for cx in TAB_CENTRES:
        t += box(cx-TAB_W/2,cx+TAB_W/2,y0-TAB_D,y0+OVERLAP,0,BACK_T)
    t += box(x0,x0+FLANGE,y0,y1,BACK_T-OVERLAP,TOP_Z)
    t += box(x1-FLANGE,x1,y0,y1,BACK_T-OVERLAP,TOP_Z)
    t += box(x0+FLANGE-OVERLAP,x1-FLANGE+OVERLAP,
             y1-FLANGE,y1,BACK_T-OVERLAP,TOP_Z)
    return t


def bottom_panel():
    x0,x1 = -PANEL_W/2, PANEL_W/2
    y0,y1 = -PANEL_H/2, PANEL_H/2
    panel_centre_global_y = -PANEL_H/2
    slot_y = FPC_GLOBAL_Y - panel_centre_global_y
    split_y = y1 - SOCKET_D
    # Main body includes the FPC hole. The seam strip is broken only by sockets.
    t = rectangle_with_capsule_hole(x0,x1,y0,split_y+OVERLAP,0,BACK_T,
                                    FPC_X,slot_y,FPC_W,FPC_H)
    cuts = sorted((cx-SOCKET_W/2,cx+SOCKET_W/2) for cx in TAB_CENTRES)
    cursor = x0
    for a,b in cuts:
        if a > cursor:
            t += box(max(cursor,x0+OVERLAP),min(a,x1-OVERLAP),split_y,y1,0,BACK_T)
        cursor = b
    if cursor < x1:
        t += box(max(cursor,x0+OVERLAP),x1-OVERLAP,split_y,y1,0,BACK_T)
    t += box(x0,x0+FLANGE,y0,y1,BACK_T-OVERLAP,TOP_Z)
    t += box(x1-FLANGE,x1,y0,y1,BACK_T-OVERLAP,TOP_Z)
    t += box(x0+FLANGE-OVERLAP,x1-FLANGE+OVERLAP,
             y0,y0+FLANGE,BACK_T-OVERLAP,TOP_Z)
    support_y = SUPPORT_Y_GLOBAL - panel_centre_global_y
    for sx0,sx1 in (LEFT_SUPPORT, RIGHT_SUPPORT):
        t += box(sx0,sx1,support_y-2.0,support_y+2.0,BACK_T-OVERLAP,TOP_Z)
    return t


write_stl(OUT / "01-shell-top.stl", top_panel(), "Stillframe clean X2D top")
write_stl(OUT / "02-shell-bottom-fpc-slots.stl", bottom_panel(), "Stillframe clean X2D bottom")
print("Generated clean X2D shell STL files")
