"""Generate the fixed onboarding URL as QR version 2-L, byte mode, mask 0.
No runtime or third-party dependencies. Output includes a four-module quiet zone.
"""
import struct
import zlib
from pathlib import Path

text = b'http://192.168.4.1/'
size = 25
bits = [0, 1, 0, 0]
def put(value, count):
    bits.extend((value >> i) & 1 for i in range(count - 1, -1, -1))
put(len(text), 8)
for value in text:
    put(value, 8)
bits.extend([0] * min(4, 272 - len(bits)))
bits.extend([0] * ((-len(bits)) % 8))
data = [sum(bits[i + j] << (7 - j) for j in range(8)) for i in range(0, len(bits), 8)]
pad = 0
while len(data) < 34:
    data.append((0xEC, 0x11)[pad % 2])
    pad += 1

def mul(a, b):
    out = 0
    while b:
        if b & 1:
            out ^= a
        a <<= 1
        if a & 256:
            a ^= 0x11D
        b >>= 1
    return out

gen = [1]
alpha = 1
for _ in range(10):
    nxt = [0] * (len(gen) + 1)
    for j, v in enumerate(gen):
        nxt[j] ^= v
        nxt[j + 1] ^= mul(v, alpha)
    gen = nxt
    alpha = mul(alpha, 2)
parity = [0] * 10
for v in data:
    factor = v ^ parity[0]
    parity = parity[1:] + [0]
    parity = [p ^ mul(g, factor) for p, g in zip(parity, gen[1:])]
stream = [((v >> i) & 1) for v in data + parity for i in range(7, -1, -1)]
m = [[False] * size for _ in range(size)]
reserved = [[False] * size for _ in range(size)]
def setcell(x, y, value):
    if 0 <= x < size and 0 <= y < size:
        m[y][x] = bool(value)
        reserved[y][x] = True
for i in range(size):
    setcell(6, i, i % 2 == 0)
    setcell(i, 6, i % 2 == 0)
for cx, cy in [(3, 3), (size - 4, 3), (3, size - 4)]:
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            setcell(cx + dx, cy + dy, max(abs(dx), abs(dy)) not in (2, 4))
for dy in range(-2, 3):
    for dx in range(-2, 3):
        setcell(18 + dx, 18 + dy, max(abs(dx), abs(dy)) != 1)
fmt = 0x77C4  # L, mask 0, including BCH and XOR mask.
bit = lambda i: (fmt >> i) & 1
for i in range(6):
    setcell(8, i, bit(i))
setcell(8, 7, bit(6))
setcell(8, 8, bit(7))
setcell(7, 8, bit(8))
for i in range(9, 15):
    setcell(14 - i, 8, bit(i))
for i in range(8):
    setcell(size - 1 - i, 8, bit(i))
for i in range(8, 15):
    setcell(8, size - 15 + i, bit(i))
setcell(8, size - 8, True)
index = 0
right = size - 1
while right >= 1:
    if right == 6:
        right = 5
    for vert in range(size):
        y = size - 1 - vert if ((right + 1) & 2) == 0 else vert
        for x in (right, right - 1):
            if not reserved[y][x]:
                value = stream[index] if index < len(stream) else 0
                m[y][x] = bool(value ^ ((x + y) % 2 == 0))
                index += 1
    right -= 2
assert index == 359 and len(stream) == 352
scale, quiet = 12, 4
width = (size + quiet * 2) * scale
raw = bytearray()
for y in range(width):
    raw.append(0)
    for x in range(width):
        mx, my = x // scale - quiet, y // scale - quiet
        raw.append(0 if 0 <= mx < size and 0 <= my < size and m[my][mx] else 255)
def chunk(kind, value):
    return struct.pack('>I', len(value)) + kind + value + struct.pack('>I', zlib.crc32(kind + value) & 0xffffffff)
png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, width, 8, 0, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')
Path(__file__).resolve().parents[1].joinpath('public/assets/setup-qr.png').write_bytes(png)
print('QR generated:', text.decode(), width, 'px')
