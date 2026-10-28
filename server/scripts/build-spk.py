#!/usr/bin/env python3
"""Build a DSM 7 package using an explicit application allowlist."""
from pathlib import Path
import base64
import hashlib
import io
import tarfile
import tempfile
import shutil
import math
import json
ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / 'dist'
version = '0.1.29-0030'

def add(tar, source, name):
    def normalize(info):
        info.uid=info.gid=0
        info.uname=info.gname='root'
        return info
    tar.add(source, arcname=name, filter=normalize)

def build():
    DIST.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='stillframe-spk-') as temporary:
        stage=Path(temporary)
        payload=stage/'payload'
        app=payload/'app'
        app.mkdir(parents=True)
        for name in ['src','public']:
            shutil.copytree(ROOT/name,app/name)
        for name in ['package.json','package-lock.json']:
            shutil.copy2(ROOT/name,app/name)
        for name in ['jpeg-js','pngjs']:
            if not (ROOT/'node_modules'/name/'package.json').is_file():
                raise RuntimeError('请先在 server 目录执行 npm ci')
            shutil.copytree(ROOT/'node_modules'/name,app/'node_modules'/name)
        shutil.copytree(ROOT/'synology/ui',payload/'ui')
        for forbidden in ['state.json','server.lock','.env','credentials.json']:
            if list(payload.rglob(forbidden)):
                raise RuntimeError('拒绝把运行数据打入安装包')
        tgz=stage/'package.tgz'
        with tarfile.open(tgz,'w:gz',format=tarfile.USTAR_FORMAT) as tar:
            for item in sorted(payload.iterdir()):add(tar,item,item.name)
        info=(ROOT/'synology/INFO').read_text()
        info+='extractsize="'+str(math.ceil(sum(p.stat().st_size for p in payload.rglob('*') if p.is_file())/1024))+'"\n'
        info+='checksum="'+hashlib.md5(tgz.read_bytes()).hexdigest()+'"\n'
        for key,file in [('package_icon','PACKAGE_ICON.PNG'),('package_icon_256','PACKAGE_ICON_256.PNG')]:
            info+=key+'="'+base64.b64encode((ROOT/'synology'/file).read_bytes()).decode()+'"\n'
        (stage/'INFO').write_text(info)
        for name in ['scripts','conf']:
            shutil.copytree(ROOT/'synology'/name,stage/name)
        for name in ['PACKAGE_ICON.PNG','PACKAGE_ICON_256.PNG']:
            shutil.copy2(ROOT/'synology'/name,stage/name)
        output=DIST/f'Stillframe-{version}.spk'
        with tarfile.open(output,'w',format=tarfile.USTAR_FORMAT) as tar:
            for name in ['INFO','package.tgz','scripts','conf','PACKAGE_ICON.PNG','PACKAGE_ICON_256.PNG']:add(tar,stage/name,name)
        digest=hashlib.sha256(output.read_bytes()).hexdigest()
        (DIST/(output.name+'.sha256')).write_text(digest+'  '+output.name+'\n')
        # Verify both package layers and that all required lifecycle files exist.
        with tarfile.open(output) as tar:
            for name in ['preinst','postinst','preuninst','postuninst','preupgrade','postupgrade','start-stop-status']:
                member=tar.getmember('scripts/'+name)
                assert member.mode & 0o111
            packed=tar.extractfile('package.tgz').read()
            assert hashlib.md5(packed).hexdigest() in tar.extractfile('INFO').read().decode()
        with tarfile.open(fileobj=io.BytesIO(packed),mode='r:gz') as tar:
            assert tar.getmember('app/src/main.mjs')
            assert tar.getmember('app/node_modules/jpeg-js/package.json')
            assert tar.getmember('app/node_modules/pngjs/package.json')
            ui=json.load(tar.extractfile('ui/config'))
            assert ui['.url']['com.stillframe.server']['port']=='8484'
        print(output)
        print('SHA256',digest)
        print('包结构、生命周期脚本、应用入口、依赖、图标与端口检查通过；尚未在 DSM 安装验收。')
if __name__=='__main__':build()
