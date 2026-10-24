"""Apply only reviewed official SDK fixes, checking exact input/output hashes."""
from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).resolve().parents[2];tools=root/'firmware/tools';sdk=root/'.tools/esp-idf';lock=json.loads((tools/'sdk-lock.json').read_text())
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=sdk,text=True).strip()
if head!=lock['esp_idf']['commit']:raise SystemExit('SDK commit differs from sdk-lock.json; refusing an unreviewed SDK')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for fix in lock.get('security_patches',[]):
 patch=tools/fix['patch'];source=sdk/fix['file']
 if sha(patch)!=fix['patch_sha256']:raise SystemExit('SDK security patch checksum mismatch')
 actual=sha(source)
 if actual==fix['patched_sha256']:continue
 if actual!=fix['original_sha256']:raise SystemExit('SDK source differs from both reviewed base and patched file: '+fix['file'])
 subprocess.run(['git','apply','--check',str(patch)],cwd=sdk,check=True)
 subprocess.run(['git','apply',str(patch)],cwd=sdk,check=True)
 if sha(source)!=fix['patched_sha256']:raise SystemExit('SDK patch output checksum mismatch')
 print('Applied official SDK security fix:',fix['advisory'])
