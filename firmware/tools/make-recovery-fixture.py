"""Create disposable corrupt-config flash for the real-driver recovery test."""
import pathlib,subprocess,sys,csv
root=pathlib.Path(__file__).resolve().parents[2]
out=root/'firmware/test-assets';out.mkdir(exist_ok=True)
blob=out/'unsupported-config.bin';blob.write_bytes((99).to_bytes(4,'little')+b'\0'*796)
with (out/'recovery.csv').open('w') as f:
 w=csv.writer(f);w.writerow(['key','type','encoding','value']);w.writerow(['stillframe','namespace','','']);w.writerow(['config','file','binary',str(blob)])
subprocess.run([str(root/'.tools/idf-python/bin/python'),str(root/'.tools/esp-idf/components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py'),'generate',str(out/'recovery.csv'),str(out/'recovery-nvs.bin'),'0x6000'],check=True)
data=bytearray((out/'runtime-flash.bin').read_bytes());data[0x9000:0xf000]=(out/'recovery-nvs.bin').read_bytes();(out/'recovery-flash.bin').write_bytes(data)
