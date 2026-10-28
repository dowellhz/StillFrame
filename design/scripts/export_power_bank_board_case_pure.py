#!/usr/bin/env python3
"""Generate the printable power-bank/controller housing used by the Blender design."""

from pathlib import Path
import math
import struct


OUT = Path("/Volumes/ACASIS/e-ink/design/bambu-x2d-stl/06-power-bank-board-case.stl")

POWER_W, POWER_H, POWER_T = 105.0, 70.0, 15.9
BOARD_W, BOARD_H, BOARD_T = 90.1, 61.2, 4.25
OUTER_W, OUTER_H = 146.0, 170.0
BASE_T, SIDE_T, OVERLAP = 1.6, 3.0, 0.08
POWER_CAVITY_W, POWER_CAVITY_H, POWER_CAVITY_T = 106.0, 71.0, 17.0
POWER_Y0, POWER_Y1 = 12.0, 83.0
POWER_CENTRE_Y = 47.5
BOARD_CENTRE_Y = -51.4
DEVICE_X = 17.0
BOARD_Y0 = BOARD_CENTRE_Y - BOARD_H / 2
BOARD_Y1 = BOARD_CENTRE_Y + BOARD_H / 2
FULL_WALL_H = BASE_T + POWER_CAVITY_T + 1.5
LOW_WALL_H = BASE_T + 4.0
FPC_NOTCH_X0 = DEVICE_X + BOARD_W / 2 - 10.0
FPC_NOTCH_Y0 = BOARD_CENTRE_Y - 25.0
FPC_NOTCH_Y1 = BOARD_CENTRE_Y + 25.0


def rounded_outline(width, height, radius, cx=0.0, cy=0.0, segments=8):
    points = []
    for ox, oy, start in (
        (width/2-radius, height/2-radius, 0),
        (-width/2+radius, height/2-radius, 90),
        (-width/2+radius, -height/2+radius, 180),
        (width/2-radius, -height/2+radius, 270),
    ):
        for i in range(segments + 1):
            angle = math.radians(start + 90 * i / segments)
            p = (cx + ox + radius*math.cos(angle), cy + oy + radius*math.sin(angle))
            if not points or p != points[-1]: points.append(p)
    return points


def prism(width, height, z0, z1, radius, cx=0.0, cy=0.0):
    ring = rounded_outline(width, height, min(radius, width/2, height/2), cx, cy)
    top_centre, bottom_centre = (cx,cy,z1), (cx,cy,z0)
    result=[]
    for i,(x0,y0) in enumerate(ring):
        x1,y1=ring[(i+1)%len(ring)]
        result += [
            (top_centre,(x0,y0,z1),(x1,y1,z1)),
            (bottom_centre,(x1,y1,z0),(x0,y0,z0)),
            ((x0,y0,z0),(x1,y1,z1),(x1,y1,z0)),
            ((x0,y0,z0),(x0,y0,z1),(x1,y1,z1)),
        ]
    return result


def annular_boss(x,y,z0,z1,outer_r=4.5,inner_r=1.5,segments=48):
    v=[]
    for z in (z0,z1):
        for r in (outer_r,inner_r):
            for i in range(segments):
                a=2*math.pi*i/segments; v.append((x+r*math.cos(a),y+r*math.sin(a),z))
    ob,ib,ot,it=0,segments,2*segments,3*segments
    faces=[]
    for i in range(segments):
        j=(i+1)%segments
        faces += [(ob+i,ob+j,ot+j),(ob+i,ot+j,ot+i),
                  (ib+j,ib+i,it+i),(ib+j,it+i,it+j),
                  (ot+i,ot+j,it+j),(ot+i,it+j,it+i),
                  (ob+j,ob+i,ib+i),(ob+j,ib+i,ib+j)]
    return [(v[a],v[b],v[c]) for a,b,c in faces]


def normal(a,b,c):
    ux,uy,uz=(b[i]-a[i] for i in range(3)); vx,vy,vz=(c[i]-a[i] for i in range(3))
    nx,ny,nz=uy*vz-uz*vy,uz*vx-ux*vz,ux*vy-uy*vx
    length=math.sqrt(nx*nx+ny*ny+nz*nz) or 1
    return nx/length,ny/length,nz/length


t=[]
# Rounded base with a right-edge notch for the reverse-folded display FPC.
outer_x1=OUTER_W/2
main_x1=FPC_NOTCH_X0+1.0
t += prism(main_x1+OUTER_W/2,OUTER_H,0,BASE_T,3.0,(main_x1-OUTER_W/2)/2,0)
for y0,y1 in ((-OUTER_H/2,FPC_NOTCH_Y0),(FPC_NOTCH_Y1,OUTER_H/2)):
    t += prism(outer_x1-FPC_NOTCH_X0+1.0,y1-y0,0,BASE_T,2.0,
               (outer_x1+FPC_NOTCH_X0-1.0)/2,(y0+y1)/2)
# Power-bank cradle. The cable side uses a low guide so the built-in lead can
# enter the left return bay; the right and top walls locate the bank.
side_x=POWER_CAVITY_W/2+SIDE_T/2
t += prism(SIDE_T,POWER_CAVITY_H+2,BASE_T-OVERLAP,FULL_WALL_H,1.25,
           DEVICE_X+side_x,POWER_CENTRE_Y+1)
t += prism(SIDE_T,POWER_CAVITY_H+2,BASE_T-OVERLAP,LOW_WALL_H,1.25,
           DEVICE_X-side_x,POWER_CENTRE_Y+1)
t += prism(POWER_CAVITY_W+2*SIDE_T,SIDE_T,BASE_T-OVERLAP,FULL_WALL_H,1.25,
           DEVICE_X,POWER_Y1+SIDE_T/2)
stop_w=(POWER_CAVITY_W-58)/2
for x in (DEVICE_X-(58+stop_w)/2,DEVICE_X+(58+stop_w)/2):
    t += prism(stop_w,4,BASE_T-OVERLAP,LOW_WALL_H,1.2,x,POWER_Y0)
# Low controller cradle. The right guide is omitted so the FPC connector and
# folded tail remain completely unobstructed.
board_clear_w=BOARD_W+1
board_side_x=board_clear_w/2+SIDE_T/2
t += prism(SIDE_T,BOARD_H+1,BASE_T-OVERLAP,LOW_WALL_H,1.0,
           DEVICE_X-board_side_x,BOARD_CENTRE_Y)
t += prism(board_clear_w+2*SIDE_T,SIDE_T,BASE_T-OVERLAP,LOW_WALL_H,1.0,
           DEVICE_X,BOARD_Y0-SIDE_T/2)
# Diagonal mounting bosses estimated from the photographed board.
for dx,dy in ((-40.75,-26.10),(40.75,26.10)):
    t += annular_boss(DEVICE_X+dx,BOARD_CENTRE_Y+dy,BASE_T-OVERLAP,BASE_T+2.2)

data=bytearray(b"Stillframe power bank and controller housing".ljust(80,b"\0"))
data += struct.pack("<I",len(t))
for a,b,c in t:
    data += struct.pack("<12fH",*normal(a,b,c),*a,*b,*c,0)
OUT.write_bytes(data)
print(f"Generated {OUT.name}: {OUTER_W:g} x {OUTER_H:g} x {FULL_WALL_H:g} mm")
print(f"Cable bay: {POWER_Y0-BOARD_Y1:.1f} mm")
print(f"Power cable return bay: {DEVICE_X-POWER_CAVITY_W/2+OUTER_W/2:.1f} mm")
print(f"FPC edge notch: {outer_x1-FPC_NOTCH_X0:.1f} x {FPC_NOTCH_Y1-FPC_NOTCH_Y0:.1f} mm")
