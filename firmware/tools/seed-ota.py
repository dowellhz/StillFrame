"""Seed a disposable emulator image's OTA metadata, never a connected device."""
import pathlib,sys,struct,binascii
source=pathlib.Path(sys.argv[1]);dest=pathlib.Path(sys.argv[2]);seq=int(sys.argv[3]) if len(sys.argv)>3 else 1;state=int(sys.argv[4]) if len(sys.argv)>4 else 2
image=bytearray(source.read_bytes());offset=0xf000
entry=struct.pack('<I20sII',seq,b'\xff'*20,state,binascii.crc32(struct.pack('<I',seq),0xffffffff)&0xffffffff)
image[offset:offset+0x2000]=b'\xff'*0x2000;image[offset:offset+32]=entry;dest.write_bytes(image)
