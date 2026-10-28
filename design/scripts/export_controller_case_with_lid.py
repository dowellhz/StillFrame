#!/usr/bin/env python3
"""Generate a board-only ESP32-133C02-IL case and friction-fit lid."""

from pathlib import Path
import math
import struct


OUT = Path("/Volumes/ACASIS/e-ink/design/bambu-x2d-stl")

# Confirmed board envelope; mounting holes and port centres remain photo-derived.
BOARD_W, BOARD_H, BOARD_T = 61.2, 90.1, 4.25  # rotated installation
CLEARANCE = 0.6
EXTRA_ROOM = 4.0  # total increase: 2 mm more clearance on every side
CAVITY_W = BOARD_W + 2*CLEARANCE + EXTRA_ROOM
CAVITY_H = BOARD_H + 2*CLEARANCE + EXTRA_ROOM
WALL_T, BASE_T = 1.8, 1.4
OUTER_W, OUTER_H = CAVITY_W + 2*WALL_T, CAVITY_H + 2*WALL_T
STANDOFF_H = 2.2
CASE_H = BASE_T + STANDOFF_H + BOARD_T + 1.5

# Photo-scaled positions in the rotated installation direction.
HOLES = ((-27.05, 40.90), (18.05, -40.95))
USB_CENTRE_Y = 13.0
SD_CENTRE_Y = -3.0
SERVICE_OPENING_CENTRE_Y = 5.0
SERVICE_OPENING = 36.0
FPC_OPENING = 42.0
FPC_CENTRE_X = 2.0

LID_T, LIP_H, LIP_T, LIP_CLEARANCE = 1.2, 1.2, 1.0, 0.25
OVERLAP = 0.06
SNAP_Y = -24.0              # clear of the left-side USB opening
SNAP_W = 16.0
SNAP_LEDGE_D = 0.7
SNAP_LEDGE_H = 0.8
SNAP_CLIP_T = 1.6
SNAP_CLIP_DROP = 4.2
SNAP_SIDE_CLEARANCE = 0.30
SNAP_HOOK = 0.75


def outline(width,height,radius,cx=0,cy=0,segments=8):
    pts=[]
    for ox,oy,start in ((width/2-radius,height/2-radius,0),(-width/2+radius,height/2-radius,90),
                        (-width/2+radius,-height/2+radius,180),(width/2-radius,-height/2+radius,270)):
        for i in range(segments+1):
            a=math.radians(start+90*i/segments)
            p=(cx+ox+radius*math.cos(a),cy+oy+radius*math.sin(a))
            if not pts or p!=pts[-1]: pts.append(p)
    return pts


def prism(width,height,z0,z1,radius=0,cx=0,cy=0):
    ring=outline(width,height,min(radius,width/2,height/2),cx,cy)
    result=[]; top=(cx,cy,z1); bottom=(cx,cy,z0)
    for i,(x0,y0) in enumerate(ring):
        x1,y1=ring[(i+1)%len(ring)]
        result += [(top,(x0,y0,z1),(x1,y1,z1)),(bottom,(x1,y1,z0),(x0,y0,z0)),
                   ((x0,y0,z0),(x1,y1,z1),(x1,y1,z0)),
                   ((x0,y0,z0),(x0,y0,z1),(x1,y1,z1))]
    return result


def boss(x,y,z0,z1,outer=4.5,inner=1.45,segments=48):
    v=[]
    for z in (z0,z1):
        for r in (outer,inner):
            for i in range(segments):
                a=2*math.pi*i/segments; v.append((x+r*math.cos(a),y+r*math.sin(a),z))
    ob,ib,ot,it=0,segments,2*segments,3*segments; faces=[]
    for i in range(segments):
        j=(i+1)%segments
        faces += [(ob+i,ob+j,ot+j),(ob+i,ot+j,ot+i),(ib+j,ib+i,it+i),(ib+j,it+i,it+j),
                  (ot+i,ot+j,it+j),(ot+i,it+j,it+i),(ob+j,ob+i,ib+i),(ob+j,ib+i,ib+j)]
    return [(v[a],v[b],v[c]) for a,b,c in faces]


def polygon_area(points):
    return sum(points[i][0]*points[(i+1)%len(points)][1] -
               points[(i+1)%len(points)][0]*points[i][1] for i in range(len(points))) / 2


def triangulate(points):
    """Ear-clip a small simple X/Z polygon."""
    order=list(range(len(points)))
    if polygon_area(points) < 0: order.reverse()
    result=[]
    while len(order) > 3:
        clipped=False
        for k,i in enumerate(order):
            a,b,c=order[k-1],i,order[(k+1)%len(order)]
            ax,az=points[a]; bx,bz=points[b]; cx,cz=points[c]
            cross=(bx-ax)*(cz-bz)-(bz-az)*(cx-bx)
            if cross <= 1e-9: continue
            def inside(p):
                px,pz=points[p]
                s1=(bx-ax)*(pz-az)-(bz-az)*(px-ax)
                s2=(cx-bx)*(pz-bz)-(cz-bz)*(px-bx)
                s3=(ax-cx)*(pz-cz)-(az-cz)*(px-cx)
                return s1>=-1e-9 and s2>=-1e-9 and s3>=-1e-9
            if any(inside(p) for p in order if p not in (a,b,c)): continue
            result.append((a,b,c)); order.pop(k); clipped=True; break
        if not clipped: raise RuntimeError("snap polygon triangulation failed")
    result.append(tuple(order))
    return result


def extrude_y(points,y0,y1):
    """Extrude one continuous X/Z profile along Y."""
    verts=[(x,y0,z) for x,z in points]+[(x,y1,z) for x,z in points]
    n=len(points); faces=[]
    for a,b,c in triangulate(points):
        faces += [(a,c,b),(n+a,n+b,n+c)]
    for i in range(n):
        j=(i+1)%n
        faces += [(i,j,n+j),(i,n+j,n+i)]
    return [(verts[a],verts[b],verts[c]) for a,b,c in faces]


def case_bottom():
    t=prism(OUTER_W,OUTER_H,0,BASE_T,3.0)
    x0,x1=-OUTER_W/2,OUTER_W/2; y0,y1=-OUTER_H/2,OUTER_H/2
    z0=0.0  # every shell starts on the print bed; no slicer "floating region"
    snap0,snap1=SNAP_Y-SNAP_W/2,SNAP_Y+SNAP_W/2
    # Right wall is split around a continuous wall/ledge snap profile.
    for a,b in ((y0,snap0+OVERLAP),(snap1-OVERLAP,y1)):
        t += prism(WALL_T,b-a,z0,CASE_H,0.7,x1-WALL_T/2,(a+b)/2)
    right_profile=[(x1-WALL_T,0),(x1,0),(x1,CASE_H-3.4),
                   (x1+SNAP_LEDGE_D-OVERLAP,CASE_H-3.4),
                   (x1+SNAP_LEDGE_D-OVERLAP,CASE_H-3.4+SNAP_LEDGE_H),
                   (x1,CASE_H-3.4+SNAP_LEDGE_H),(x1,CASE_H),(x1-WALL_T,CASE_H)]
    t += extrude_y(right_profile,snap0,snap1)
    # Top wall is split around the photographed FPC connector. Its centre is
    # about 8 mm right of the board centre.
    top_x0=x0+WALL_T-OVERLAP; top_x1=x1-WALL_T+OVERLAP
    fpc0,fpc1=FPC_CENTRE_X-FPC_OPENING/2,FPC_CENTRE_X+FPC_OPENING/2
    for a,b in ((top_x0,fpc0),(fpc1,top_x1)):
        t += prism(b-a,WALL_T,z0,CASE_H,0.7,(a+b)/2,y1-WALL_T/2)
    # One robust service opening covers both the SD socket and USB-C. Separate
    # holes would leave a thin, fragile strip between the adjacent connectors.
    service0=SERVICE_OPENING_CENTRE_Y-SERVICE_OPENING/2
    service1=SERVICE_OPENING_CENTRE_Y+SERVICE_OPENING/2
    for a,b in ((y0,snap0+OVERLAP),(snap1-OVERLAP,service0),(service1,y1)):
        t += prism(WALL_T,b-a,z0,CASE_H,0.7,x0+WALL_T/2,(a+b)/2)
    left_profile=[(x0,0),(x0+WALL_T,0),(x0+WALL_T,CASE_H),(x0,CASE_H),
                  (x0,CASE_H-3.4+SNAP_LEDGE_H),
                  (x0-SNAP_LEDGE_D+OVERLAP,CASE_H-3.4+SNAP_LEDGE_H),
                  (x0-SNAP_LEDGE_D+OVERLAP,CASE_H-3.4),(x0,CASE_H-3.4)]
    t += extrude_y(left_profile,snap0,snap1)
    # Bottom wall is continuous in the actual board orientation.
    bottom_x0=x0+WALL_T-OVERLAP; bottom_x1=x1-WALL_T+OVERLAP
    t += prism(bottom_x1-bottom_x0,WALL_T,z0,CASE_H,0.7,
               (bottom_x0+bottom_x1)/2,y0+WALL_T/2)
    for x,y in HOLES:
        t += boss(x,y,0,BASE_T+STANDOFF_H)
    return t


def lid():
    # Print outside face down; locating rim points upward and is flipped for use.
    t=prism(OUTER_W,OUTER_H,0,LID_T,3.0)
    lip_w=CAVITY_W-2*LIP_CLEARANCE; lip_h=CAVITY_H-2*LIP_CLEARANCE
    x0,x1=-lip_w/2,lip_w/2; y0,y1=-lip_h/2,lip_h/2
    z0,z1=0.0,LID_T+LIP_H
    t += prism(LIP_T,lip_h,z0,z1,0.45,x1-LIP_T/2,0)
    top_x0=x0+LIP_T-OVERLAP; top_x1=x1-LIP_T+OVERLAP
    fpc0,fpc1=FPC_CENTRE_X-FPC_OPENING/2,FPC_CENTRE_X+FPC_OPENING/2
    for a,b in ((top_x0,fpc0),(fpc1,top_x1)):
        t += prism(b-a,LIP_T,z0,z1,0.45,(a+b)/2,y1-LIP_T/2)
    service0=SERVICE_OPENING_CENTRE_Y-SERVICE_OPENING/2
    service1=SERVICE_OPENING_CENTRE_Y+SERVICE_OPENING/2
    for a,b in ((y0,service0),(service1,y1)):
        t += prism(LIP_T,b-a,z0,z1,0.45,x0+LIP_T/2,(a+b)/2)
    bottom_x0=x0+LIP_T-OVERLAP; bottom_x1=x1-LIP_T+OVERLAP
    t += prism(bottom_x1-bottom_x0,LIP_T,z0,z1,0.45,
               (bottom_x0+bottom_x1)/2,y0+LIP_T/2)
    # Two cantilever clips flex outward over the case ledges. In print
    # orientation they point upward; the lid is flipped when installed.
    clip_z1=LID_T+SNAP_CLIP_DROP
    outer=OUTER_W/2+SNAP_SIDE_CLEARANCE+SNAP_CLIP_T
    inner=OUTER_W/2+SNAP_SIDE_CLEARANCE
    hook_inner=inner-SNAP_HOOK+OVERLAP
    # The root bridge reaches into the lid by OVERLAP. Only the lower skirt has
    # side clearance, so the clip is one printable part rather than a loose bar.
    lid_edge=OUTER_W/2
    root_inner=lid_edge-OVERLAP
    root_top=LID_T+OVERLAP
    right_clip=[(root_inner,0),(outer,0),(outer,clip_z1),(hook_inner,clip_z1),
                (hook_inner,clip_z1-SNAP_LEDGE_H),(inner,clip_z1-SNAP_LEDGE_H),
                (inner,root_top),(root_inner,root_top)]
    left_clip=[(-x,z) for x,z in reversed(right_clip)]
    t += extrude_y(right_clip,SNAP_Y-SNAP_W/2,SNAP_Y+SNAP_W/2)
    t += extrude_y(left_clip,SNAP_Y-SNAP_W/2,SNAP_Y+SNAP_W/2)
    return t


def normal(a,b,c):
    ux,uy,uz=(b[i]-a[i] for i in range(3)); vx,vy,vz=(c[i]-a[i] for i in range(3))
    nx,ny,nz=uy*vz-uz*vy,uz*vx-ux*vz,ux*vy-uy*vx
    q=math.sqrt(nx*nx+ny*ny+nz*nz) or 1
    return nx/q,ny/q,nz/q


def write(name,triangles,label):
    data=bytearray(label.encode()[:80].ljust(80,b"\0"))+struct.pack("<I",len(triangles))
    for a,b,c in triangles: data += struct.pack("<12fH",*normal(a,b,c),*a,*b,*c,0)
    (OUT/name).write_bytes(data)


write("06-controller-case-bottom.stl",case_bottom(),"Stillframe controller case bottom")
write("07-controller-case-lid.stl",lid(),"Stillframe controller case lid")
print(f"Case outer: {OUTER_W:.1f} x {OUTER_H:.1f} x {CASE_H:.2f} mm")
print(f"Cavity: {CAVITY_W:.1f} x {CAVITY_H:.1f} mm; USB/SD service={SERVICE_OPENING:.1f}; FPC={FPC_OPENING:.1f}")
print(f"Photo-corrected: holes left-top/right-bottom; USB y={USB_CENTRE_Y:.1f}; SD y={SD_CENTRE_Y:.1f}; FPC top x={FPC_CENTRE_X:.1f}")
print("Lid: two flexible side snap clips; no glue required")
