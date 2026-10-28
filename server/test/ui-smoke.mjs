// Optional DOM integration harness. Pass a happy-dom module path; never packaged.
import assert from 'node:assert/strict';
import {readFile,mkdtemp,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {Readable,Writable} from 'node:stream';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createApp} from '../src/app.mjs';
import {PNG} from 'pngjs';
const {Window}=await import(pathToFileURL(path.resolve(process.argv[2])).href);
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url))),dir=await mkdtemp(path.join(os.tmpdir(),'stillframe-ui-')),app=await createApp({dataDir:dir});
let cookie='';
function request(url,options={}){return new Promise(resolve=>{const req=Readable.from(options.body?[Buffer.from(options.body)]:[]);Object.assign(req,{url,method:options.method||'GET',headers:{host:'localhost:8484',cookie,...options.headers},socket:{remoteAddress:'127.0.0.1'}});let status,headers,chunks=[];const res=new Writable({write(c,e,cb){chunks.push(Buffer.from(c));cb();}});res.writeHead=(s,h)=>{status=s;headers=h;res.headersSent=true;return res;};res.on('finish',()=>{if(headers['Set-Cookie'])cookie=headers['Set-Cookie'].split(';')[0];const body=Buffer.concat(chunks).toString();resolve({ok:status<400,status,json:async()=>JSON.parse(body)});});app.server.emit('request',req,res);});}
const w=new Window({url:'http://localhost:8484',settings:{disableCSSFileLoading:true,disableJavaScriptFileLoading:true}});w.fetch=request;w.confirm=()=>true;w.document.write(await readFile(path.join(root,'public/index.html'),'utf8'));for(const d of w.document.querySelectorAll('dialog')){d.showModal=()=>d.setAttribute('open','');d.close=()=>{d.removeAttribute('open');d.dispatchEvent(new w.Event('close'));};}
// The optional happy-dom harness lacks the native RadioNodeList value setter.
const radioValue=Object.getOwnPropertyDescriptor(w.RadioNodeList.prototype,'value');
if(!radioValue?.set)Object.defineProperty(w.RadioNodeList.prototype,'value',{...radioValue,set(value){for(const node of this)node.checked=node.value===String(value);}});
const q=s=>w.document.querySelector(s),wait=()=>new Promise(r=>setTimeout(r,40)),go=async name=>{w.location.hash=name;w.onhashchange();await wait();};
try{
 w.eval(await readFile(path.join(root,'public/app.js'),'utf8'));await wait();assert.match(q('#auth-title').textContent,/有个家/);
 const f=q('#auth-form');f.elements.username.value='owner';f.elements.password.value='ui-test-password';await f.onsubmit({target:f,preventDefault(){}});assert.equal(q('#workspace').hidden,false);assert.equal(q('#auth').hidden,true);assert.equal(q('#auth-error').textContent,'');assert.match(q('#album-count').textContent,/0 件作品/);
 q('#upload-top').click();assert.equal(q('#upload-form').elements.fit.value,'cover');assert.ok(q('#upload-form').querySelectorAll('[name="photoCollections"]').length);assert.ok(q('#upload-form').querySelectorAll('[name="photoMovements"]').length);q('#upload-form').elements.fit.value='contain';q('#upload-dialog').close();q('#upload-top').click();assert.equal(q('#upload-form').elements.fit.value,'cover');q('#upload-dialog').close();await go('photos');assert.equal(q('#page-title').textContent,'图库');q('#new-category').click();const cat=q('#category-form');cat.elements.name.value='UI 测试收藏集';cat.elements.parentId.value='art';await cat.onsubmit({target:cat,preventDefault(){}});assert.ok(app.store.data.categories.some(c=>c.name==='UI 测试收藏集'));
 await go('settings');const defaults=q('#default-form');defaults.elements.intervalSeconds.value='180';await defaults.onsubmit({target:defaults,preventDefault(){}});assert.equal(app.store.data.defaultConfig.intervalSeconds,180);
 await request('/api/v1/device/sync',{method:'POST',headers:{authorization:'Bearer '+app.store.data.enrollmentKey},body:JSON.stringify({deviceId:'ui-test-device',requestId:'first'})});await q('#refresh').onclick();q('nav button[data-view="devices"]').click();await wait();assert.equal(q('#device-grid .device-card')!==null,true);assert.match(q('#device-grid [data-next-refresh]').textContent,/\d{2}:\d{2}/);q('[data-device="ui-test-device"]').click();const device=q('#device-form');device.elements.name.value='书房相框';device.elements.inherit.checked=false;device.elements.inherit.onchange();device.elements.intervalSeconds.value='900';await device.onsubmit({target:device,preventDefault(){}});assert.equal(app.store.data.devices[0].config.intervalSeconds,900);assert.equal(app.store.data.devices[0].name,'书房相框');
 await q('#connect-device').onclick();assert.equal(q('#enrollment-key').value,app.store.data.enrollmentKey);assert.equal(q('#enrollment-key').type,'password');q('#toggle-key').click();assert.equal(q('#enrollment-key').type,'text');
 assert.ok(q('#photo-preview').closest('.real-frame'));assert.match(q('.frame-dimensions').textContent,/30 × 45/);
 const account=q('#password-form');account.elements.currentPassword.value='ui-test-password';account.elements.newPassword.value='ui-updated-password';account.elements.confirmPassword.value='ui-updated-password';await account.onsubmit({target:account,preventDefault(){}});assert.equal(q('#password-message').textContent,'');assert.equal(account.elements.currentPassword.value,'');const oldLogin=await request('/api/auth/login',{method:'POST',body:JSON.stringify({username:'owner',password:'ui-test-password'})});assert.equal(oldLogin.status,401);
 await request('/api/admin/default-config',{method:'PUT',body:JSON.stringify({intervalSeconds:240,categoryIds:[],includeChildren:true,order:'sequence'})});await q('#refresh').onclick();q('nav button[data-view="settings"]').click();await wait();assert.equal(q('#default-form').elements.intervalSeconds.value,'240','a custom API interval must not silently turn into 180 seconds');
 for(const [value,title] of [[255,'翻页白图'],[0,'翻页黑图']]){const data=Buffer.alloc(4*4*4,255);for(let i=0;i<data.length;i+=4)data[i]=data[i+1]=data[i+2]=value;const png=PNG.sync.write({width:4,height:4,data});const result=await request('/api/admin/photos',{method:'POST',body:JSON.stringify({title,categoryId:'vangogh',dither:false,data:'data:image/png;base64,'+png.toString('base64')})});assert.equal(result.status,201);}
 for(const d of w.document.querySelectorAll('dialog[open]'))d.close();await q('#refresh').onclick();q('nav button[data-view="photos"]').click();await wait();
 const cards=[...w.document.querySelectorAll('#photo-grid [data-photo]')];assert.equal(cards.length,2);cards[0].click();const initial=q('#photo-form').elements.id.value;assert.equal(q('#photo-position').textContent,'1 / 2');assert.equal(q('#photo-prev').disabled,true);assert.equal(q('#photo-next').disabled,false);
 q('#preview-original').click();q('#photo-next').click();assert.notEqual(q('#photo-form').elements.id.value,initial);assert.equal(q('#photo-position').textContent,'2 / 2');assert.equal(q('#photo-next').disabled,true);assert.ok(q('#preview-original').classList.contains('active'));q('#photo-prev').click();assert.equal(q('#photo-form').elements.id.value,initial);
 const titleInput=q('#photo-form').elements.title;titleInput.value='尚未保存';titleInput.dispatchEvent(new w.Event('input',{bubbles:true}));w.confirm=()=>false;q('#photo-next').click();assert.equal(q('#photo-form').elements.id.value,initial);assert.equal(titleInput.value,'尚未保存');w.confirm=()=>true;q('#photo-next').click();assert.notEqual(q('#photo-form').elements.id.value,initial);
 q('#photo-dialog').dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true}));assert.equal(q('#photo-form').elements.id.value,initial);q('#photo-form').elements.title.dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true}));assert.equal(q('#photo-form').elements.id.value,initial,'editing text must not trigger navigation');q('#photo-dialog').close();
 q('#search').value='翻页白图';q('#search').dispatchEvent(new w.Event('input',{bubbles:true}));q('#photo-grid [data-photo]').click();assert.equal(q('#photo-position').textContent,'1 / 1');assert.equal(q('#photo-prev').disabled,true);assert.equal(q('#photo-next').disabled,true);const drawer=q('#photo-dialog'),outside={bubbles:true,clientX:-1,clientY:-1};drawer.dispatchEvent(new w.MouseEvent('pointerdown',outside));drawer.dispatchEvent(new w.MouseEvent('click',outside));await new Promise(r=>setTimeout(r,220));assert.equal(drawer.open,false,'clicking outside the photo drawer returns to the list');

 // Complete-image mode must remain unchanged until a real crop gesture, then
 // save the selected region through the same backend used by the photo editor.
 for(const [width,height] of [[8,8],[6,8]]){
  const pixels=Buffer.alloc(width*height*4),colors=[[255,0,0],[0,255,0],[0,0,255],[255,255,0],[0,0,0],[255,255,255]];
  for(let y=0;y<height;y++)for(let x=0;x<width;x++)pixels.set([...colors[(x+y)%colors.length],255],(y*width+x)*4);
  const title=`裁切回归 ${width}×${height}`,png=PNG.sync.write({width,height,data:pixels});
  const uploaded=await request('/api/admin/photos',{method:'POST',body:JSON.stringify({title,categoryId:'vangogh',fit:'contain',cropX:.1,cropY:0,cropW:.8,cropH:1,dither:false,data:'data:image/png;base64,'+png.toString('base64')})});
  assert.equal(uploaded.status,201);const original=(await uploaded.json()).photos.find(p=>p.title===title);
  q('#search').value='';q('#search').dispatchEvent(new w.Event('input',{bubbles:true}));await q('#refresh').onclick();q(`#photo-grid [data-photo="${original.id}"]`).click();
  const form=q('#photo-form'),box=q('#crop-box'),stage=q('#crop-stage'),values=()=>['cropX','cropY','cropW','cropH'].map(k=>Number(form.elements[k].value));
  stage.getBoundingClientRect=()=>({width:400,height:400*height/width});box.setPointerCapture=()=>{};
  const pointer=(target,type,x,y)=>target.dispatchEvent(new w.PointerEvent(type,{bubbles:true,button:0,pointerId:1,clientX:x,clientY:y}));
  assert.equal(form.elements.fit.value,'contain');assert.deepEqual(values(),[0,0,1,1]);assert.equal(q('.crop-disabled'),null);assert.ok(!stage.classList.contains('disabled'));
  pointer(box,'pointerdown',150,150);pointer(box,'pointerup',150,150);assert.equal(form.elements.fit.value,'contain');assert.deepEqual(values(),[0,0,1,1]);
  pointer(box,'pointerdown',150,150);pointer(box,'pointermove',170,150);pointer(box,'pointerup',170,150);assert.equal(form.elements.fit.value,'cover','moving a complete image activates cropping');
  form.elements.fit.value='contain';form.elements.fit.dispatchEvent(new w.Event('change',{bubbles:true}));
  pointer(q('.crop-handle'),'pointerdown',300,300);pointer(box,'pointermove',180,120);pointer(box,'pointerup',180,120);
  assert.equal(form.elements.fit.value,'cover');let [x,y,cw,ch]=values();assert.ok(cw<1&&ch<1);assert.ok(Math.abs(cw*width/(ch*height)-.75)<.001,'crop keeps screen ratio');
  pointer(box,'pointerdown',150,150);pointer(box,'pointermove',170,170);pointer(box,'pointerup',170,170);assert.ok(Number(form.elements.cropX.value)>x);assert.ok(Number(form.elements.cropY.value)>y);
  const selected=values();await form.onsubmit({target:form,preventDefault(){}});const saved=app.store.data.photos.find(p=>p.id===original.id);
  assert.equal(saved.fit,'cover');assert.deepEqual([saved.cropX,saved.cropY,saved.cropW,saved.cropH],selected);assert.notEqual(saved.displaySha256,original.displaySha256,'crop changes actual display bytes');
  q(`#photo-grid [data-photo="${original.id}"]`).click();assert.deepEqual(values(),selected,'saved region reopens correctly');
  form.elements.fit.value='contain';form.elements.fit.dispatchEvent(new w.Event('change',{bubbles:true}));assert.deepEqual(values(),[0,0,1,1]);
  form.elements.rotation.value='90';form.elements.rotation.dispatchEvent(new w.Event('change',{bubbles:true}));assert.deepEqual(values(),[0,0,1,1]);
  form.elements.rotation.value='0';form.elements.rotation.dispatchEvent(new w.Event('change',{bubbles:true}));await form.onsubmit({target:form,preventDefault(){}});
  const restored=app.store.data.photos.find(p=>p.id===original.id);assert.equal(restored.fit,'contain');assert.equal(restored.displaySha256,original.displaySha256,'complete-image mode restores original display');
 }
 console.log('Crop UI PASS: square and screen-ratio contain images, click without changes, resize/move, save/reopen, rendered bytes, rotation and restore.');

 const deviceAuth={authorization:'Bearer '+app.store.data.enrollmentKey};
 const offered=await request('/api/v1/device/sync',{method:'POST',headers:deviceAuth,body:JSON.stringify({deviceId:'ui-test-device',requestId:'preview-download'})});
 const offeredPhoto=(await offered.json()).photo;assert.ok(offeredPhoto);
 await request(offeredPhoto.url,{headers:deviceAuth});await q('#refresh').onclick();q('nav button[data-view="devices"]').click();await wait();
 assert.match(q('#device-grid .device-photo-status').textContent,/待确认/);assert.ok(q('#device-grid .frame-opening img').src.includes(offeredPhoto.id));
 assert.ok(q('#device-grid .frame-opening img').src.includes(new URL(offeredPhoto.url,'http://localhost').searchParams.get('v')));
 q('#device-grid [data-device-preview]').click();assert.equal(q('#device-preview-dialog').open,true);assert.equal(q('#device-photo-title').textContent,offeredPhoto.title);assert.match(q('#device-photo-note').textContent,/尚未确认/);q('#device-preview-dialog').close();
 await request('/api/v1/device/sync',{method:'POST',headers:deviceAuth,body:JSON.stringify({deviceId:'ui-test-device',requestId:'preview-display',currentPhotoId:offeredPhoto.id,currentPhotoVersion:new URL(offeredPhoto.url,'http://localhost').searchParams.get('v')})});await q('#refresh').onclick();
 assert.equal(q('#device-grid .device-photo-status').textContent,'设备报告显示');q('#device-grid [data-download-index]').click();assert.match(q('#device-photo-note').textContent,/下载记录/);q('#device-preview-dialog').close();
 await request('/api/admin/photos/'+offeredPhoto.id,{method:'DELETE'});await q('#refresh').onclick();assert.match(q('#device-grid').textContent,/照片已删除/);assert.ok(q('#device-grid .device-download-history'));assert.equal(q('#device-grid [data-download-index]').disabled,true);
 if(process.argv[3]){
  const rom=await readFile(process.argv[3]);q('nav button[data-view="settings"]').click();await wait();
  Object.defineProperty(q('#rom-file'),'files',{configurable:true,value:[{name:'Stillframe.bin',size:rom.length,arrayBuffer:async()=>rom}]});
  await q('#rom-upload-form').onsubmit({target:q('#rom-upload-form'),preventDefault(){}});assert.equal(app.store.data.firmwares.length,1);assert.match(q('#rom-list').textContent,/ESP32-133C02-IL/);
  if(process.argv[4]){const newer=await readFile(process.argv[4]);Object.defineProperty(q('#rom-file'),'files',{configurable:true,value:[{name:'newer.bin',size:newer.length,arrayBuffer:async()=>newer}]});await q('#rom-upload-form').onsubmit({target:q('#rom-upload-form'),preventDefault(){}});assert.equal(app.store.data.firmwares.length,2);}
  q('nav button[data-view="devices"]').click();await wait();q('[data-rom-device]').click();assert.equal(q('#rom-deploy-form button').disabled,true);q('#rom-dialog').close();
  await request('/api/v1/device/sync',{method:'POST',headers:deviceAuth,body:JSON.stringify({deviceId:'ui-test-device',requestId:'hardware',boardModel:'ESP32-133C02-IL',panelModel:'GDEP133C02',chipModel:'esp32s3',otaProtocol:1,otaSlotBytes:5242880})});await q('#refresh').onclick();q('[data-rom-device]').click();assert.equal(q('#rom-deploy-form button').disabled,false);if(process.argv[4])assert.equal(q('#rom-deploy-form').elements.firmwareId.value,app.store.data.firmwares.at(-1).id,'default ROM selection must be the newest compatible upload');
  await q('#rom-deploy-form').onsubmit({target:q('#rom-deploy-form'),preventDefault(){}});assert.equal(app.store.data.devices[0].firmwareTask.status,'queued');assert.match(q('#device-grid').textContent,/待下发/);
  q('[data-rom-cancel]').click();await wait();assert.equal(app.store.data.devices[0].firmwareTask.status,'cancelled');console.log('ROM UI PASS: real application upload, unknown board blocked, matching target selection, manual dispatch and cancellation.');
 }
 await q('#logout').onclick();assert.equal(q('#workspace').hidden,true);assert.equal(q('#auth').hidden,false);console.log('DOM + real backend PASS: first setup, login state, navigation, categories, default config, device settings, connection credentials, frame markup, password change, photo previous/next/keyboard/filter/unsaved handling, device download preview/pending/display confirmation/history/deletion, logout.');
}finally{await w.happyDOM.close();app.close();await rm(dir,{recursive:true,force:true});}
