#!/usr/bin/env python3
"""Place only the controller case bottom and snap lid on X2D plate 3."""

from pathlib import Path
import math
import struct

ROOT=Path("/Volumes/ACASIS/e-ink/design/bambu-x2d-stl")
OUT=ROOT/"08-controller-case-and-lid.stl"
PLACEMENTS=((ROOT/"06-controller-case-bottom.stl",-40.0,20.0,0.0),
            (ROOT/"07-controller-case-lid.stl",40.0,20.0,0.0))

def read(path,offset):
    d=path.read_bytes(); n=struct.unpack_from('<I',d,80)[0]; ox,oy,oz=offset; out=[]
    for i in range(n):
        a=struct.unpack_from('<9f',d,96+i*50)
        out.append(tuple((a[j]+ox,a[j+1]+oy,a[j+2]+oz) for j in (0,3,6)))
    return out

def normal(a,b,c):
    ux,uy,uz=(b[i]-a[i] for i in range(3)); vx,vy,vz=(c[i]-a[i] for i in range(3))
    nx,ny,nz=uy*vz-uz*vy,uz*vx-ux*vz,ux*vy-uy*vx; q=math.sqrt(nx*nx+ny*ny+nz*nz) or 1
    return nx/q,ny/q,nz/q

t=[]
for p,x,y,z in PLACEMENTS: t.extend(read(p,(x,y,z)))
d=bytearray(b"Stillframe controller case kit plate".ljust(80,b"\0"))+struct.pack('<I',len(t))
for a,b,c in t: d += struct.pack('<12fH',*normal(a,b,c),*a,*b,*c,0)
OUT.write_bytes(d)
print(f"Generated {OUT.name}: {len(t)} triangles")
