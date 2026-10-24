from pathlib import Path
import struct,binascii,subprocess,sys
r=Path(__file__).resolve().parents[2];p=r/'firmware/test-assets';cfg=bytearray(800);struct.pack_into('<I',cfg,0,1);cfg[552:560]=b'12345678';cfg[616:629]=b'sf-boot-stall';struct.pack_into('<I',cfg,728,3600)
assert len(cfg)==800
(p/'startup-config.bin').write_bytes(cfg);(p/'startup-nvs.csv').write_text('key,type,encoding,value\nstillframe,namespace,,\nconfig,file,binary,'+str(p/'startup-config.bin')+'\n')
subprocess.run([str(r/'.tools/idf-python/bin/python'),str(r/'.tools/esp-idf/components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py'),'generate',str(p/'startup-nvs.csv'),str(p/'startup-nvs.bin'),'0x6000'],check=True)
b=bytearray((p/'runtime-flash.bin').read_bytes());b+=b'\xff'*(16*1024*1024-len(b));app=b[0x20000:0x520000];b[0x520000:0xa20000]=app;b[0x9000:0xf000]=(p/'startup-nvs.bin').read_bytes();b[0xf000:0x11000]=b'\xff'*0x2000
for off,seq,state in [(0xf000,1,2),(0x10000,2,0)]:b[off:off+32]=struct.pack('<I20sII',seq,b'\xff'*20,state,binascii.crc32(struct.pack('<I',seq),0xffffffff)&0xffffffff)
(p/'startup-stall-flash.bin').write_bytes(b)

# A separate unconfigured pending image spends 40 seconds drawing its setup
# screen. OTA health must be confirmed from initialized services, not display
# completion, so the new slot remains valid.
slow=bytearray(cfg);slow[616:648]=b'\0'*32;slow[616:629]=b'sf-slow-setup'
(p/'slow-setup-config.bin').write_bytes(slow)
(p/'slow-setup-nvs.csv').write_text('key,type,encoding,value\nstillframe,namespace,,\nconfig,file,binary,'+str(p/'slow-setup-config.bin')+'\n')
subprocess.run([str(r/'.tools/idf-python/bin/python'),str(r/'.tools/esp-idf/components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py'),'generate',str(p/'slow-setup-nvs.csv'),str(p/'slow-setup-nvs.bin'),'0x6000'],check=True)
slow_flash=bytearray((p/'runtime-flash.bin').read_bytes());slow_flash+=b'\xff'*(16*1024*1024-len(slow_flash));app=slow_flash[0x20000:0x520000];slow_flash[0x520000:0xa20000]=app;slow_flash[0x9000:0xf000]=(p/'slow-setup-nvs.bin').read_bytes();slow_flash[0xf000:0x11000]=b'\xff'*0x2000
for off,seq,state in [(0xf000,1,2),(0x10000,2,0)]:slow_flash[off:off+32]=struct.pack('<I20sII',seq,b'\xff'*20,state,binascii.crc32(struct.pack('<I',seq),0xffffffff)&0xffffffff)
(p/'slow-setup-flash.bin').write_bytes(slow_flash)

# Three early worker crashes must stop automatic playback and leave the setup
# hotspot alive instead of rebooting forever.
early=bytearray(cfg);early[4:37]=b'\0'*33;early[37:102]=b'\0'*65;early[616:648]=b'\0'*32
early[4:10]=b'myssid';early[37:47]=b'mypassword';early[616:630]=b'sf-early-crash';early[732]=1
(p/'early-crash-config.bin').write_bytes(early)
(p/'early-crash-nvs.csv').write_text('key,type,encoding,value\nstillframe,namespace,,\nconfig,file,binary,'+str(p/'early-crash-config.bin')+'\n')
subprocess.run([str(r/'.tools/idf-python/bin/python'),str(r/'.tools/esp-idf/components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py'),'generate',str(p/'early-crash-nvs.csv'),str(p/'early-crash-nvs.bin'),'0x6000'],check=True)
early_flash=bytearray((p/'runtime-flash.bin').read_bytes());early_flash+=b'\xff'*(16*1024*1024-len(early_flash));early_flash[0x9000:0xf000]=(p/'early-crash-nvs.bin').read_bytes()
(p/'early-crash-flash.bin').write_bytes(early_flash)

# A configured device first reaches managed safe mode, then performs a
# deliberate OTA boot into the duplicate image in ota_1. The new image must not
# inherit the old early-reset count or it would immediately roll back.
safe_ota=bytearray(early);safe_ota[616:648]=b'\0'*32;safe_ota[616:627]=b'sf-safe-ota'
(p/'safe-ota-config.bin').write_bytes(safe_ota)
(p/'safe-ota-nvs.csv').write_text('key,type,encoding,value\nstillframe,namespace,,\nconfig,file,binary,'+str(p/'safe-ota-config.bin')+'\n')
subprocess.run([str(r/'.tools/idf-python/bin/python'),str(r/'.tools/esp-idf/components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py'),'generate',str(p/'safe-ota-nvs.csv'),str(p/'safe-ota-nvs.bin'),'0x6000'],check=True)
safe_flash=bytearray((p/'runtime-flash.bin').read_bytes());safe_flash+=b'\xff'*(16*1024*1024-len(safe_flash));app=safe_flash[0x20000:0x520000];safe_flash[0x520000:0xa20000]=app;safe_flash[0x9000:0xf000]=(p/'safe-ota-nvs.bin').read_bytes()
(p/'safe-ota-flash.bin').write_bytes(safe_flash)

# A pending configured image that actually tries the real panel driver must
# roll back when that attempt fails. This catches display-driver regressions;
# the emulator intentionally has no GDEP133C02 peripheral model.
panel=bytearray(early);panel[616:648]=b'\0'*32;panel[616:633]=b'sf-panel-rollback'
(p/'panel-rollback-config.bin').write_bytes(panel)
(p/'panel-rollback-nvs.csv').write_text('key,type,encoding,value\nstillframe,namespace,,\nconfig,file,binary,'+str(p/'panel-rollback-config.bin')+'\n')
subprocess.run([str(r/'.tools/idf-python/bin/python'),str(r/'.tools/esp-idf/components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py'),'generate',str(p/'panel-rollback-nvs.csv'),str(p/'panel-rollback-nvs.bin'),'0x6000'],check=True)
panel_flash=bytearray((p/'runtime-flash.bin').read_bytes());panel_flash+=b'\xff'*(16*1024*1024-len(panel_flash));app=panel_flash[0x20000:0x520000];panel_flash[0x520000:0xa20000]=app;panel_flash[0x9000:0xf000]=(p/'panel-rollback-nvs.bin').read_bytes();panel_flash[0xf000:0x11000]=b'\xff'*0x2000
for off,seq,state in [(0xf000,1,2),(0x10000,2,0)]:panel_flash[off:off+32]=struct.pack('<I20sII',seq,b'\xff'*20,state,binascii.crc32(struct.pack('<I',seq),0xffffffff)&0xffffffff)
(p/'panel-rollback-flash.bin').write_bytes(panel_flash)

# If the panel was not known-good before an upgrade, the same first-cycle
# failure must not roll back the new image: it may contain the panel repair.
prebroken=bytearray(early);prebroken[616:648]=b'\0'*32;prebroken[616:634]=b'sf-panel-prebroken'
(p/'panel-prebroken-config.bin').write_bytes(prebroken)
(p/'panel-prebroken-nvs.csv').write_text('key,type,encoding,value\nstillframe,namespace,,\nconfig,file,binary,'+str(p/'panel-prebroken-config.bin')+'\n')
subprocess.run([str(r/'.tools/idf-python/bin/python'),str(r/'.tools/esp-idf/components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py'),'generate',str(p/'panel-prebroken-nvs.csv'),str(p/'panel-prebroken-nvs.bin'),'0x6000'],check=True)
prebroken_flash=bytearray((p/'runtime-flash.bin').read_bytes());prebroken_flash+=b'\xff'*(16*1024*1024-len(prebroken_flash));app=prebroken_flash[0x20000:0x520000];prebroken_flash[0x520000:0xa20000]=app;prebroken_flash[0x9000:0xf000]=(p/'panel-prebroken-nvs.bin').read_bytes();prebroken_flash[0xf000:0x11000]=b'\xff'*0x2000
for off,seq,state in [(0xf000,1,2),(0x10000,2,0)]:prebroken_flash[off:off+32]=struct.pack('<I20sII',seq,b'\xff'*20,state,binascii.crc32(struct.pack('<I',seq),0xffffffff)&0xffffffff)
(p/'panel-prebroken-flash.bin').write_bytes(prebroken_flash)

# Repeated resets while the display high-voltage sequence is active must stop
# after three attempts instead of retrying forever every three minutes.
power=bytearray(early);power[616:648]=b'\0'*32;power[616:630]=b'sf-power-reset'
(p/'power-reset-config.bin').write_bytes(power)
(p/'power-reset-nvs.csv').write_text('key,type,encoding,value\nstillframe,namespace,,\nconfig,file,binary,'+str(p/'power-reset-config.bin')+'\n')
subprocess.run([str(r/'.tools/idf-python/bin/python'),str(r/'.tools/esp-idf/components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py'),'generate',str(p/'power-reset-nvs.csv'),str(p/'power-reset-nvs.bin'),'0x6000'],check=True)
power_flash=bytearray((p/'runtime-flash.bin').read_bytes());power_flash+=b'\xff'*(16*1024*1024-len(power_flash));power_flash[0x9000:0xf000]=(p/'power-reset-nvs.bin').read_bytes()
(p/'power-reset-flash.bin').write_bytes(power_flash)

# Safe mode waits 30 minutes in release builds, then clears the old counter and
# attempts one normal boot. Runtime tests shorten only this fixture's delay.
safe_retry=bytearray(early);safe_retry[616:648]=b'\0'*32;safe_retry[616:629]=b'sf-safe-retry'
(p/'safe-retry-config.bin').write_bytes(safe_retry)
(p/'safe-retry-nvs.csv').write_text('key,type,encoding,value\nstillframe,namespace,,\nconfig,file,binary,'+str(p/'safe-retry-config.bin')+'\n')
subprocess.run([str(r/'.tools/idf-python/bin/python'),str(r/'.tools/esp-idf/components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py'),'generate',str(p/'safe-retry-nvs.csv'),str(p/'safe-retry-nvs.bin'),'0x6000'],check=True)
safe_retry_flash=bytearray((p/'runtime-flash.bin').read_bytes());safe_retry_flash+=b'\xff'*(16*1024*1024-len(safe_retry_flash));safe_retry_flash[0x9000:0xf000]=(p/'safe-retry-nvs.bin').read_bytes()
(p/'safe-retry-flash.bin').write_bytes(safe_retry_flash)
