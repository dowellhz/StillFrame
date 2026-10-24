"""Download SDK build wheels using curl, then install with pip offline."""
import json, subprocess, pathlib, re, sys
from pip._vendor.packaging.requirements import Requirement
from pip._vendor.packaging.version import Version
from pip._vendor.packaging.tags import sys_tags
from pip._vendor.packaging.utils import parse_wheel_filename, canonicalize_name
root=pathlib.Path(__file__).resolve().parents[2]
wheels=root/'.tools/wheels'; wheels.mkdir(exist_ok=True)
tags=set(sys_tags()); constraints={}
for line in (root/'.tools/idf-tools/espidf.constraints.v5.5.txt').read_text().splitlines():
 try:
  r=Requirement(line)
  if not r.marker or r.marker.evaluate(): constraints[canonicalize_name(r.name)]=r.specifier
 except Exception: pass
queue=[]
for line in (root/'.tools/esp-idf/tools/requirements/requirements.core.txt').read_text().splitlines():
 try:
  r=Requirement(line)
  if not r.marker or r.marker.evaluate(): queue.append(r)
 except Exception: pass
selected={}
missing=[]
cache=root/'.tools/pypi'; cache.mkdir(exist_ok=True)
def metadata(name, version=None):
 key=name+('-'+str(version) if version else '')
 path=cache/(key+'.json')
 if not path.exists():
  missing.append({'url':f'https://pypi.org/pypi/{name}/'+(str(version)+'/' if version else '')+'json','path':str(path)})
  return None
 return json.loads(path.read_text())
while queue:
 r=queue.pop(0); name=canonicalize_name(r.name)
 if name in selected:
  if selected[name] not in r.specifier: raise RuntimeError(f'conflict {r}: {selected[name]}')
  continue
 meta=metadata(name)
 if meta is None: continue
 versions=sorted([Version(v) for v in meta['releases'] if not Version(v).is_prerelease],reverse=True)
 chosen=None
 for v in versions:
  if v not in r.specifier or (name in constraints and v not in constraints[name]): continue
  for f in meta['releases'][str(v)]:
   if f['yanked'] or f['packagetype']!='bdist_wheel': continue
   if f.get('requires_python'):
    from pip._vendor.packaging.specifiers import SpecifierSet
    if Version('.'.join(map(str,sys.version_info[:3]))) not in SpecifierSet(f['requires_python']): continue
   if parse_wheel_filename(f['filename'])[3]&tags: chosen=(v,f); break
  if chosen: break
 if not chosen:
  for v in versions:
   if v not in r.specifier or (name in constraints and v not in constraints[name]): continue
   fs=[f for f in meta['releases'][str(v)] if f['packagetype']=='sdist' and not f['yanked']]
   if fs: chosen=(v,fs[0]); break
 if not chosen: raise RuntimeError(f'No compatible distribution: {r}')
 v,f=chosen; selected[name]=v; dest=wheels/f['filename']
 if not dest.exists(): missing.append({'url':f['url'],'path':str(dest)})
 # silent planning
 versionmeta=metadata(name,v)
 if versionmeta is None: continue
 info=versionmeta['info']
 for dep in info.get('requires_dist') or []:
  d=Requirement(dep)
  if not d.marker or d.marker.evaluate({'extra':''}): queue.append(d)
if missing:
 print(json.dumps(missing)); sys.exit(0)
subprocess.run([sys.executable,'-m','pip','install','--no-index','--no-build-isolation','--find-links',str(wheels),*[f'{n}=={v}' for n,v in selected.items()]],check=True)
