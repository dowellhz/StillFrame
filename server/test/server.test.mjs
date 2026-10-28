import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm,readFile,writeFile,mkdir} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {Readable,Writable} from 'node:stream';
import crypto from 'node:crypto';
import {PNG} from 'pngjs';
import jpeg from 'jpeg-js';
import {createApp} from '../src/app.mjs';
import {sixColor,decode,resize} from '../src/image.mjs';
function call(app,url,method='GET',data,headers={},options={}){return new Promise((resolve,reject)=>{const req=Readable.from(data===undefined?[]:[Buffer.from(JSON.stringify(data))]);Object.assign(req,{url,method,headers:{host:'localhost',...headers},socket:{remoteAddress:'127.0.0.1'}});let status,outHeaders,chunks=[];const res=new Writable({write(c,e,cb){if(options.abortResponse){cb(new Error('test response interrupted'));return;}chunks.push(Buffer.from(c));cb();}});res.writeHead=(s,h)=>{status=s;outHeaders=h;res.headersSent=true;return res;};res.on('finish',()=>{const bytes=Buffer.concat(chunks);resolve({status,headers:outHeaders,bytes,json:()=>JSON.parse(bytes)});});res.on('error',reject);app.server.emit('request',req,res);});}
async function fixture(t){const dir=await mkdtemp(path.join(os.tmpdir(),'stillframe-server-'));const app=await createApp({dataDir:dir});t.after(async()=>{app.close();await rm(dir,{recursive:true,force:true});});return {app,dir};}
async function initialize(app){const r=await call(app,'/api/auth/setup','POST',{username:'owner',password:'correct-test-password'});assert.equal(r.status,201,r.bytes.toString());return {cookie:r.headers['Set-Cookie'].split(';')[0]};}
const cfg={intervalSeconds:180,categoryIds:['art'],includeChildren:true,order:'sequence'};
function pngData(color=255){const data=Buffer.alloc(16*16*4,255);for(let i=0;i<data.length;i+=4)data[i]=data[i+1]=data[i+2]=color;return 'data:image/png;base64,'+PNG.sync.write({width:16,height:16,data}).toString('base64');}
test('authentication, exclusive first setup, session logout and cross-site protection',async t=>{
 const {app}=await fixture(t);assert.equal((await call(app,'/api/admin/state')).status,401);const auth=await initialize(app);
 assert.equal((await call(app,'/api/auth/setup','POST',{username:'other',password:'another-password'})).status,409);
 assert.equal((await call(app,'/api/auth/login','POST',{username:'owner',password:'wrong'})).status,401);
 assert.equal((await call(app,'/api/auth/login','POST',{username:'owner',password:'correct-test-password'})).status,200);
 assert.equal((await call(app,'/api/admin/default-config','PUT',cfg,{...auth,origin:'https://attacker.example'})).status,403);
 assert.equal((await call(app,'/api/v1/device/sync','POST',{deviceId:'test-frame'})).status,401);
 assert.equal((await call(app,'/api/admin/state','GET',undefined,auth)).status,200);
 await call(app,'/api/auth/logout','POST',{},auth);assert.equal((await call(app,'/api/admin/state','GET',undefined,auth)).status,401);
});
test('hierarchical categories reject cycles, duplicate names and nonempty deletions; configs validate bounds',async t=>{
 const {app}=await fixture(t),auth=await initialize(app);
 assert.equal((await call(app,'/api/admin/categories/art','PUT',{name:'绘画',parentId:'vangogh'},auth)).status,400);
 assert.equal((await call(app,'/api/admin/categories/art','DELETE',undefined,auth)).status,409);
 assert.equal((await call(app,'/api/admin/categories','POST',{name:'梵高',parentId:'art'},auth)).status,409);
 let r=await call(app,'/api/admin/categories','POST',{name:'莫奈',parentId:'art'},auth);assert.equal(r.status,201);const c=r.json().categories.find(c=>c.name==='莫奈');
 assert.equal((await call(app,'/api/admin/categories/'+c.id,'PUT',{name:'Claude Monet',parentId:null},auth)).status,200);
 assert.equal((await call(app,'/api/admin/default-config','PUT',{...cfg,intervalSeconds:1},auth)).status,400);
 assert.equal((await call(app,'/api/admin/default-config','PUT',{...cfg,categoryIds:['missing']},auth)).status,400);
 assert.equal((await call(app,'/api/admin/categories/'+c.id,'DELETE',undefined,auth)).status,200);
});
test('playback config combines type, subject, artist, movement and collection facets',async t=>{
 const {app}=await fixture(t),auth=await initialize(app),key=(await call(app,'/api/admin/enrollment-key','GET',undefined,auth)).json().key,deviceAuth={authorization:'Bearer '+key};
 let r=await call(app,'/api/admin/photos','POST',{title:'莫奈风景',author:'克劳德·莫奈',contentType:'painting',subjects:['landscape'],tags:['印象派','鲜亮'],collectionIds:['vangogh','people'],data:pngData(120),dither:false},auth);assert.equal(r.status,201);const painting=r.json().photos[0];assert.deepEqual(painting.collectionIds,['vangogh','people']);assert.equal(painting.categoryId,'vangogh');
 r=await call(app,'/api/admin/photos','POST',{title:'人物照片',author:'摄影者',contentType:'photo',subjects:['portrait'],tags:['旅行'],categoryId:'people',data:pngData(80),dither:false},auth);assert.equal(r.status,201);
 const filters={...cfg,categoryIds:['art'],contentTypes:['painting'],subjects:['landscape'],creators:['克劳德·莫奈'],movements:['印象派'],tags:['鲜亮']};
 r=await call(app,'/api/admin/default-config','PUT',filters,auth);assert.equal(r.status,200);assert.deepEqual(r.json().defaultConfig.contentTypes,['painting']);assert.deepEqual(r.json().defaultConfig.movements,['印象派']);assert.deepEqual(r.json().defaultConfig.tags,['鲜亮']);
 r=await call(app,'/api/v1/device/sync','POST',{deviceId:'facet-frame',requestId:'facets'},deviceAuth);assert.equal(r.status,200);assert.equal(r.json().photo.id,painting.id);
 r=await call(app,'/api/admin/default-config','PUT',{...filters,categoryIds:['people']},auth);assert.equal(r.status,200);r=await call(app,'/api/v1/device/sync','POST',{deviceId:'facet-frame',requestId:'secondary-collection'},deviceAuth);assert.equal(r.json().photo.id,painting.id,'a secondary collection participates in playback filtering');
 assert.equal((await call(app,'/api/admin/photos/'+painting.id,'PUT',{collectionIds:[]},auth)).status,400);
 assert.equal((await call(app,'/api/admin/default-config','PUT',{...filters,contentTypes:['video']},auth)).status,400);
 assert.equal((await call(app,'/api/admin/default-config','PUT',{...filters,creators:'克劳德·莫奈'},auth)).status,400);
});
test('legacy playback tags migrate into separate movement and user-tag facets',async t=>{
 const {app,dir}=await fixture(t);app.close();
 const file=path.join(dir,'state.json'),saved=JSON.parse(await readFile(file,'utf8'));
 delete saved.defaultConfig.movements;saved.defaultConfig.tags=['印象派','鲜亮'];
 await writeFile(file,JSON.stringify(saved));
 const restarted=await createApp({dataDir:dir});t.after(()=>restarted.close());
 assert.deepEqual(restarted.store.data.defaultConfig.movements,['印象派']);
 assert.deepEqual(restarted.store.data.defaultConfig.tags,['鲜亮']);
});
test('real image pipeline, binary hash, device retry/ack selection, overrides, credentials and restart persistence',async t=>{
 const {app,dir}=await fixture(t),auth=await initialize(app);const key=(await call(app,'/api/admin/enrollment-key','GET',undefined,auth)).json().key,deviceAuth={authorization:'Bearer '+key};
 let r=await call(app,'/api/admin/photos','POST',{title:'白色测试图',categoryId:'vangogh',data:pngData(),dither:false},auth);assert.equal(r.status,201,r.bytes.toString());const first=r.json().photos[0];assert.equal(first.fit,'cover','uploads without fit must default to center crop');
 r=await call(app,'/api/admin/photos','POST',{title:'黑色测试图',categoryId:'vangogh',data:pngData(0),dither:false},auth);assert.equal(r.status,201,r.bytes.toString());
 assert.equal((await call(app,'/api/admin/photos','POST',{title:'重复',categoryId:'vangogh',data:pngData()},auth)).status,409);
 assert.equal((await call(app,'/api/admin/photos','POST',{title:'坏图片',categoryId:'vangogh',data:'data:image/png;base64,YmFk'},auth)).status,400);
 await call(app,'/api/admin/default-config','PUT',cfg,auth);const sync=b=>call(app,'/api/v1/device/sync','POST',{deviceId:'frame-bedroom',...b},deviceAuth);
 const initial=(await sync({requestId:'first'})).json();assert.equal(initial.registered,true);assert.equal(initial.config.source,'default');assert.equal(initial.photo.bytes,960000);assert.ok(Math.abs(Date.parse(app.store.data.devices[0].nextRefreshAt)-Date.now()-cfg.intervalSeconds*1000)<2000,'server records the device next refresh time');
 const download=await call(app,initial.photo.url,'GET',undefined,deviceAuth);assert.equal(download.status,200);assert.equal(download.bytes.length,960000);assert.equal(crypto.createHash('sha256').update(download.bytes).digest('hex'),initial.photo.sha256);
 assert.deepEqual((await sync({requestId:'first'})).json(),initial);assert.equal((await sync({requestId:'retry'})).json().photo.id,initial.photo.id);
 assert.notEqual((await sync({requestId:'next',currentPhotoId:initial.photo.id})).json().photo.id,initial.photo.id);assert.equal(app.store.data.devices.length,1);
 await call(app,'/api/admin/devices/frame-bedroom','PUT',{name:'卧室相框',config:{...cfg,intervalSeconds:900,categoryIds:['people']}},auth);
 r=await sync({requestId:'dedicated'});assert.equal(r.json().config.source,'device');assert.equal(r.json().config.intervalSeconds,900);assert.equal(r.json().photo,null);
 await call(app,'/api/admin/devices/frame-bedroom','PUT',{config:null},auth);assert.equal((await sync({requestId:'inherit'})).json().config.source,'default');
 await call(app,'/api/admin/devices/frame-bedroom','PUT',{disabled:true},auth);assert.equal((await sync({requestId:'disabled'})).status,403);
 await call(app,'/api/admin/enrollment-key','POST',{},auth);assert.equal((await sync({requestId:'rotated'})).status,401);
 app.close();const restarted=await createApp({dataDir:dir});t.after(()=>restarted.close());assert.equal(restarted.store.data.devices.length,1);assert.equal(restarted.store.data.devices[0].name,'卧室相框');assert.equal(restarted.store.data.photos.length,2);assert.equal((await readFile(path.join(dir,'photos',first.id,first.renderVersion+'.bin'))).length,960000);
 assert.equal((await call(restarted,'/api/auth/login','POST',{username:'owner',password:'correct-test-password'})).status,200);
});
test('six-color screen codes, alpha compositing, aspect ratio and oversized image rejection',()=>{
 const jpg=jpeg.encode({width:2,height:3,data:Buffer.alloc(2*3*4,255)},80).data;const decoded=decode(jpg);assert.equal(decoded.ext,'jpg');assert.equal(decoded.width,2);assert.equal(decoded.height,3);
 const colors=[[0,0,0],[255,255,255],[255,255,0],[255,0,0],[0,0,255],[0,128,0]],input={width:6,height:1,data:Buffer.from(colors.flatMap(c=>[...c,255]))};assert.deepEqual([...sixColor(input,false).bin],[0x01,0x23,0x56]);
 const r=resize({width:2,height:1,data:Buffer.from([255,0,0,255,255,0,0,255])},4,4,'contain');assert.deepEqual([...r.data.subarray(0,4)],[255,255,255,255]);assert.equal(r.data[(1*4+1)*4+1],0);
 const strip={width:4,height:1,data:Buffer.from([[255,0,0],[0,255,0],[0,0,255],[255,255,0]].flatMap(c=>[...c,255]))},cropped=resize(strip,2,1,'cover',0,.5,0,.5,1);assert.deepEqual([...cropped.data],[0,0,255,255,255,255,0,255]);
 assert.ok(resize({width:1,height:1,data:Buffer.from([0,0,0,0])},2,2).data.every(x=>x===255));const huge=Buffer.alloc(24);Buffer.from([137,80,78,71,13,10,26,10]).copy(huge);huge.writeUInt32BE(100000,16);huge.writeUInt32BE(100000,20);assert.throws(()=>decode(huge),/2400/);
});
test('private files, missing paths and public health routes',async t=>{const {app}=await fixture(t);assert.equal((await call(app,'/api/health')).status,200);assert.equal((await call(app,'/')).status,200);assert.equal((await call(app,'/src/app.mjs')).status,404);assert.equal((await call(app,'/%2e%2e%2fsrc/app.mjs')).status,403);assert.equal((await call(app,'/app.js')).status,200);});
test('photo edits preserve in-flight binary versions; disabling and deleting stops new delivery',async t=>{
 const {app}=await fixture(t),auth=await initialize(app),key=(await call(app,'/api/admin/enrollment-key','GET',undefined,auth)).json().key,deviceAuth={authorization:'Bearer '+key};
 const uploaded=await call(app,'/api/admin/photos','POST',{title:'可编辑照片',categoryId:'vangogh',data:pngData(140),dither:true},auth);assert.equal(uploaded.status,201);const photo=uploaded.json().photos[0];
 const delivered=(await call(app,'/api/v1/device/sync','POST',{deviceId:'photo-edit-frame',requestId:'before'},deviceAuth)).json().photo;
 let r=await call(app,'/api/admin/photos/'+photo.id,'PUT',{title:'编辑完成',categoryId:'landscape',fit:'cover',rotation:90,dither:false,enabled:true},auth);assert.equal(r.status,200,r.bytes.toString());const changed=r.json().photos[0];assert.notEqual(changed.renderVersion,photo.renderVersion);assert.equal(changed.categoryId,'landscape');
 const old=await call(app,delivered.url,'GET',undefined,deviceAuth);assert.equal(old.status,200);assert.equal(crypto.createHash('sha256').update(old.bytes).digest('hex'),delivered.sha256);
 const newer=(await call(app,'/api/v1/device/sync','POST',{deviceId:'photo-edit-frame',requestId:'after',currentPhotoId:photo.id},deviceAuth)).json().photo;assert.equal(newer.sha256,changed.displaySha256);
 assert.equal((await call(app,'/api/admin/photos/'+photo.id+'/preview','GET',undefined,auth)).headers['Content-Type'],'image/png');
 await call(app,'/api/admin/photos/'+photo.id,'PUT',{enabled:false},auth);assert.equal((await call(app,'/api/v1/device/sync','POST',{deviceId:'photo-edit-frame',requestId:'off'},deviceAuth)).json().photo,null);
 assert.equal((await call(app,delivered.url,'GET',undefined,deviceAuth)).status,404);
 await call(app,'/api/admin/photos/'+photo.id,'DELETE',undefined,auth);assert.equal(app.store.data.photos.length,0);assert.equal((await call(app,'/api/admin/photos/'+photo.id+'/original','GET',undefined,auth)).status,404);
});
test('a second process instance cannot acquire the same data directory; corrupt state never silently resets',async t=>{
 const {app,dir}=await fixture(t);await assert.rejects(()=>createApp({dataDir:dir}),/另一服务/);app.close();const fs=await import('node:fs/promises');await fs.writeFile(path.join(dir,'state.json'),'{broken');await assert.rejects(()=>createApp({dataDir:dir}));assert.equal(await fs.readFile(path.join(dir,'state.json'),'utf8'),'{broken');
});
test('password changes verify current and confirmation, invalidate old sessions, persist and preserve device key',async t=>{
 const {app,dir}=await fixture(t),auth=await initialize(app),oldKey=app.store.data.enrollmentKey;
 const second=await call(app,'/api/auth/login','POST',{username:'owner',password:'correct-test-password'});const otherAuth={cookie:second.headers['Set-Cookie'].split(';')[0]};
 const body={currentPassword:'correct-test-password',newPassword:'updated-test-password',confirmPassword:'updated-test-password'};
 assert.equal((await call(app,'/api/admin/password','PUT',{...body,currentPassword:'wrong'},auth)).status,400);
 assert.equal((await call(app,'/api/admin/password','PUT',{...body,confirmPassword:'different'},auth)).status,400);
 assert.equal((await call(app,'/api/admin/password','PUT',{...body,newPassword:'short',confirmPassword:'short'},auth)).status,400);
 assert.equal((await call(app,'/api/admin/state','GET',undefined,auth)).status,200);
 const r=await call(app,'/api/admin/password','PUT',body,auth);assert.equal(r.status,200,r.bytes.toString());const current={cookie:r.headers['Set-Cookie'].split(';')[0]};
 assert.equal((await call(app,'/api/admin/state','GET',undefined,auth)).status,401);assert.equal((await call(app,'/api/admin/state','GET',undefined,otherAuth)).status,401);assert.equal((await call(app,'/api/admin/state','GET',undefined,current)).status,200);
 assert.equal(app.store.data.enrollmentKey,oldKey);const disk=await readFile(path.join(dir,'state.json'),'utf8');assert.ok(!disk.includes(body.newPassword));assert.ok(!disk.includes(body.currentPassword));
 app.close();const restarted=await createApp({dataDir:dir});t.after(()=>restarted.close());assert.equal((await call(restarted,'/api/auth/login','POST',{username:'owner',password:body.newPassword})).status,200);assert.equal((await call(restarted,'/api/auth/login','POST',{username:'owner',password:body.currentPassword})).status,401);
});

test('device downloads are attributed only after a complete GET, retain versions and history, and never confirm display',async t=>{
 const {app,dir}=await fixture(t),auth=await initialize(app),deviceAuth={authorization:'Bearer '+app.store.data.enrollmentKey};
 const upload=await call(app,'/api/admin/photos','POST',{title:'下载记录测试',categoryId:'vangogh',data:pngData(120),dither:false},auth);
 const photo=upload.json().photos[0],sync=b=>call(app,'/api/v1/device/sync','POST',{deviceId:'download-frame',...b},deviceAuth);
 const first=(await sync({requestId:'first'})).json();assert.equal(new URL(first.photo.url,'http://localhost').searchParams.get('deviceId'),'download-frame');
 app.store.write(s=>{s.devices[0].lastResponse.photo.url=first.photo.url.replace('&deviceId=download-frame','');});
 const legacyRetry=(await sync({requestId:'first'})).json();assert.equal(legacyRetry.photo.url,first.photo.url,'legacy cached responses gain attribution without advancing the photo');
 const device=()=>app.store.data.devices.find(d=>d.id==='download-frame');assert.equal(device().downloadHistory,undefined);assert.equal(device().currentPhotoId,null);
 assert.equal((await call(app,first.photo.url.replace('&deviceId=download-frame',''),'GET',undefined,deviceAuth)).status,200);assert.equal(device().downloadHistory,undefined,'old links remain usable but are not attributed by guessing');
 assert.equal((await call(app,first.photo.url,'HEAD',undefined,deviceAuth)).status,200);assert.equal(device().downloadHistory,undefined,'HEAD is not a download');
 assert.equal((await call(app,first.photo.url)).status,401);assert.equal(device().downloadHistory,undefined);
 await assert.rejects(call(app,first.photo.url,'GET',undefined,deviceAuth,{abortResponse:true}),/interrupted/);assert.equal(device().downloadHistory,undefined,'a failed response is not recorded');
 const downloaded=await call(app,first.photo.url,'GET',undefined,deviceAuth);assert.equal(downloaded.status,200);assert.equal(device().currentPhotoId,null,'download does not claim display');
 assert.equal(device().lastDownloadedPhotoId,photo.id);assert.equal(device().lastDownloadedVersion,photo.renderVersion);assert.equal(device().downloadHistory.length,1);assert.equal(device().downloadHistory[0].bytes,960000);assert.equal(device().downloadHistory[0].title,photo.title);assert.ok(device().lastDownloadedAt);
 assert.equal((await call(app,first.photo.url.replace('deviceId=download-frame','deviceId=unknown-frame'),'GET',undefined,deviceAuth)).status,404);
 const oldPreview=await call(app,`/api/admin/photos/${photo.id}/preview?v=${photo.renderVersion}`,'GET',undefined,auth);assert.equal(oldPreview.status,200);
 const edited=(await call(app,`/api/admin/photos/${photo.id}`,'PUT',{rotation:90,dither:true},auth)).json().photos[0];assert.notEqual(edited.renderVersion,photo.renderVersion);
 const historical=await call(app,`/api/admin/photos/${photo.id}/preview?v=${photo.renderVersion}`,'GET',undefined,auth);assert.deepEqual(historical.bytes,oldPreview.bytes,'device preview uses the downloaded version');
 assert.equal((await call(app,`/api/admin/photos/${photo.id}/preview?v=../../other`,'GET',undefined,auth)).status,400);
 const missing=first.photo.url.replace(photo.renderVersion,'00000000-0000-0000-0000-000000000000');assert.equal((await call(app,missing,'GET',undefined,deviceAuth)).status,404);assert.equal(device().downloadHistory.length,1);
 await sync({requestId:'ack',currentPhotoId:photo.id,currentPhotoVersion:photo.renderVersion});assert.equal(device().currentPhotoId,photo.id);assert.equal(device().currentPhotoVersion,photo.renderVersion);assert.ok(device().currentPhotoReportedAt);
 for(let i=0;i<22;i++)assert.equal((await call(app,first.photo.url,'GET',undefined,deviceAuth)).status,200);
 assert.equal(device().downloadHistory.length,20);assert.equal(new Set(device().downloadHistory.map(h=>h.id)).size,20);
 const before=device().downloadHistory.length;await call(app,'/api/admin/devices/download-frame','PUT',{disabled:true},auth);assert.equal((await call(app,first.photo.url,'GET',undefined,deviceAuth)).status,403);assert.equal(device().downloadHistory.length,before);
 app.close();const restarted=await createApp({dataDir:dir});t.after(()=>restarted.close());const saved=restarted.store.data.devices[0];assert.equal(saved.downloadHistory.length,20);assert.equal(saved.currentPhotoVersion,photo.renderVersion);
});
function testRom(){const data=Buffer.alloc(400);data.writeUInt32LE(0xabcd5432);data.write('0.1.9',16);data.write('Stillframe',48);data.write('STILLFRAME-HW1',256);data.write('ESP32-133C02-IL',272);data.write('GDEP133C02',304);data.writeUInt32LE(1,328);data.writeUInt16LE(1200,332);data.writeUInt16LE(1600,334);const header=Buffer.alloc(32);header[0]=0xe9;header[1]=1;header.writeUInt16LE(9,12);header[23]=1;header.writeUInt32LE(data.length,28);const raw=Buffer.concat([header,data,Buffer.alloc(16)]);let checksum=0xef;for(const x of data)checksum^=x;raw[raw.length-1]=checksum;return Buffer.concat([raw,crypto.createHash('sha256').update(raw).digest()]);}
test('ROM validation rejects wrong board, chip, merged images, truncation and modified data',async()=>{const {inspectRom}=await import('../src/firmware.mjs');const rom=testRom();assert.equal(inspectRom(rom).boardModel,'ESP32-133C02-IL');for(const mutate of [b=>b[12]=0,b=>b[304]=88,b=>b[336]=88,b=>b[288]=0,b=>b[368]=1,b=>b[80]=88,b=>b[390]^=1,b=>b[b.length-1]^=1]){const wrong=Buffer.from(rom);mutate(wrong);assert.throws(()=>inspectRom(wrong));}assert.throws(()=>inspectRom(rom.subarray(0,-1)));assert.throws(()=>inspectRom(Buffer.concat([rom,rom])));});
test('ROM tasks require known matching hardware, persist, remain per-device and verify running SHA',async t=>{
 const {app,dir}=await fixture(t),auth=await initialize(app),deviceAuth={authorization:'Bearer '+app.store.data.enrollmentKey};const rom=testRom();
 const body={filename:'Stillframe.bin',data:'data:application/octet-stream;base64,'+rom.toString('base64')};
 assert.equal((await call(app,'/api/admin/firmwares','POST',body)).status,401);
 let r=await call(app,'/api/admin/firmwares','POST',body,auth);assert.equal(r.status,201,r.bytes.toString());const f=r.json().firmwares[0];assert.equal((await readFile(path.join(dir,'firmware',f.id+'.bin'))).length,rom.length);
 assert.equal((await call(app,'/api/admin/firmwares','POST',body,auth)).status,409);
 const sync=(deviceId,b={})=>call(app,'/api/v1/device/sync','POST',{deviceId,requestId:crypto.randomUUID(),...b},deviceAuth);
 await sync('legacy-frame');await sync('other-frame');const route='/api/admin/devices/legacy-frame/firmware';
 assert.equal((await call(app,route,'POST',{firmwareId:f.id},auth)).status,400);
 const hw={boardModel:f.boardModel,panelModel:f.panelModel,chipModel:f.chipModel,otaProtocol:1,otaSlotBytes:5242880};
 await sync('legacy-frame',{...hw,boardModel:'WRONG'});assert.equal((await call(app,route,'POST',{firmwareId:f.id},auth)).status,400);
 await sync('legacy-frame',hw);assert.equal((await call(app,route,'POST',{firmwareId:f.id},auth)).status,200);
 assert.equal((await call(app,route,'POST',{firmwareId:f.id},auth)).status,409);
 const offer=(await sync('legacy-frame')).json().firmware;assert.equal(offer.id,f.id);assert.equal((await sync('other-frame',hw)).json().firmware,null);
 assert.equal((await call(app,offer.url,'GET',undefined,deviceAuth)).status,200);
 assert.equal((await call(app,offer.url.replace('legacy-frame','other-frame'),'GET',undefined,deviceAuth)).status,409);
 assert.equal((await call(app,offer.url)).status,401);
 await sync('legacy-frame',{firmwareVersion:f.version,firmwareSha256:'0'.repeat(64)});assert.equal(app.store.data.devices[0].firmwareTask.status,'offered');
 await sync('legacy-frame',{firmwareVersion:f.version,firmwareSha256:f.sha256});assert.equal(app.store.data.devices[0].firmwareTask.status,'succeeded');assert.equal((await call(app,offer.url,'GET',undefined,deviceAuth)).status,409);
 assert.equal((await call(app,route,'POST',{firmwareId:f.id},auth)).status,409);
 await sync('other-frame',hw);const route2='/api/admin/devices/other-frame/firmware';await call(app,route2,'POST',{firmwareId:f.id},auth);const pending=(await sync('other-frame')).json().firmware;await call(app,route2,'DELETE',undefined,auth);assert.equal((await call(app,pending.url,'GET',undefined,deviceAuth)).status,409);assert.equal((await sync('other-frame')).json().firmware,null);
 const romPath=path.join(dir,'firmware',f.id+'.bin');await writeFile(romPath,rom.subarray(0,-1));assert.equal((await call(app,route2,'POST',{firmwareId:f.id},auth)).status,400);await writeFile(romPath,rom);
 await call(app,route2,'POST',{firmwareId:f.id},auth);const task=(await sync('other-frame')).json().firmware;assert.equal((await call(app,'/api/v1/device/firmware-result','POST',{deviceId:'other-frame',taskId:task.taskId,status:'failed',message:'校验失败'},deviceAuth)).status,200);assert.equal((await sync('other-frame')).json().firmware,null);
 app.close();const reopened=await createApp({dataDir:dir});assert.equal(reopened.store.data.firmwares[0].sha256,f.sha256);assert.equal(reopened.store.data.devices[1].firmwareTask.status,'failed');reopened.close();
});
test('audit: missing primary state must not silently replace an existing library',async t=>{
 const {app,dir}=await fixture(t);await initialize(app);app.close();const before=await readFile(path.join(dir,'state.json.previous'));await rm(path.join(dir,'state.json'));await assert.rejects(()=>createApp({dataDir:dir}),/索引缺失|备份/);assert.deepEqual(await readFile(path.join(dir,'state.json.previous')),before);
});
test('audit: corrupted saved ROM is refused at download and cancelled in-flight install is reconciled',async t=>{
 const {app,dir}=await fixture(t),auth=await initialize(app),deviceAuth={authorization:'Bearer '+app.store.data.enrollmentKey},rom=testRom();const uploaded=await call(app,'/api/admin/firmwares','POST',{filename:'test.bin',data:'data:application/octet-stream;base64,'+rom.toString('base64')},auth),f=uploaded.json().firmwares[0];
 const sync=b=>call(app,'/api/v1/device/sync','POST',{deviceId:'audit-ota-frame',requestId:crypto.randomUUID(),...b},deviceAuth);
 await sync({boardModel:f.boardModel,panelModel:f.panelModel,chipModel:f.chipModel,otaProtocol:1,otaSlotBytes:5242880});const route='/api/admin/devices/audit-ota-frame/firmware';await call(app,route,'POST',{firmwareId:f.id},auth);const offer=(await sync({})).json().firmware;
 const file=path.join(dir,'firmware',f.id+'.bin');await writeFile(file,Buffer.alloc(rom.length));assert.equal((await call(app,offer.url,'GET',undefined,deviceAuth)).status,409);await writeFile(file,rom);
 await call(app,route,'DELETE',undefined,auth);
 assert.equal((await call(app,'/api/v1/device/firmware-result','POST',{deviceId:'audit-ota-frame',taskId:offer.taskId,status:'installed'},deviceAuth)).status,200);
 await sync({firmwareSha256:f.sha256});assert.equal(app.store.data.devices[0].firmwareTask.status,'succeeded');assert.ok(app.store.data.devices[0].firmwareTask.cancelledAt);
});

test('audit: renderer exiting without a message cannot stall the next queued photo',async()=>{
 const {renderImage,queuedJobs}=await import('../src/jobs.mjs');const noResult=new URL('data:text/javascript,process.exit(0)');await assert.rejects(()=>renderImage(Buffer.from('x'),{},noResult),/未返回结果/);assert.equal(queuedJobs(),0);
 const image=Buffer.from(pngData(100).split(',')[1],'base64');const result=await renderImage(image,{fit:'cover',rotation:0,dither:false});assert.equal(result.bin.length,960000);assert.equal(queuedJobs(),0);
});

test('audit: a failed disk commit preserves memory and disk state and can be retried',async t=>{
 const {app,dir}=await fixture(t),auth=await initialize(app),before=await readFile(path.join(dir,'state.json'));await mkdir(path.join(dir,'state.json.tmp'));
 const changed={...app.store.data.defaultConfig,intervalSeconds:900};assert.equal((await call(app,'/api/admin/default-config','PUT',changed,auth)).status,503);assert.equal(app.store.data.defaultConfig.intervalSeconds,3600);assert.deepEqual(await readFile(path.join(dir,'state.json')),before);
 await rm(path.join(dir,'state.json.tmp'),{recursive:true});assert.equal((await call(app,'/api/admin/default-config','PUT',changed,auth)).status,200);assert.equal(app.store.data.defaultConfig.intervalSeconds,900);
});
test('deleting a frame removes it from the list; an active frame re-registers on its next sync',async t=>{
 const {app}=await fixture(t),auth=await initialize(app);const key=(await call(app,'/api/admin/enrollment-key','GET',undefined,auth)).json().key,deviceAuth={authorization:'Bearer '+key};
 const sync=id=>call(app,'/api/v1/device/sync','POST',{deviceId:id,requestId:id+'-'+Date.now()},deviceAuth);
 assert.equal((await sync('old-frame')).status,200);assert.equal((await sync('live-frame')).status,200);
 assert.equal((await call(app,'/api/admin/devices/missing-frame','DELETE',undefined,auth)).status,404);
 assert.equal((await call(app,'/api/admin/devices/old-frame','DELETE')).status,401,'deletion requires an admin session');
 const r=await call(app,'/api/admin/devices/old-frame','DELETE',undefined,auth);assert.equal(r.status,200);
 assert.deepEqual(r.json().devices.map(d=>d.id),['live-frame']);assert.equal(r.json().statistics.devices,1);
 assert.equal((await sync('old-frame')).json().registered,true,'a deleted frame that is still in use reappears as new');
});
test('calibrated renderer defaults to natural, re-renders on colour change and migrates earlier renders once',async t=>{
 const {app,dir}=await fixture(t),auth=await initialize(app);
 const colorful=()=>{const data=Buffer.alloc(16*16*4,255);for(let i=0;i<data.length;i+=4){data[i]=180;data[i+1]=120;data[i+2]=90;}return 'data:image/png;base64,'+PNG.sync.write({width:16,height:16,data}).toString('base64');};
 assert.equal((await call(app,'/api/admin/photos','POST',{title:'坏色彩',categoryId:'vangogh',data:pngData(),color:'neon'},auth)).status,400);
 let r=await call(app,'/api/admin/photos','POST',{title:'暖色',categoryId:'vangogh',data:colorful()},auth);assert.equal(r.status,201,r.bytes.toString());
 const photo=r.json().photos[0];assert.equal(photo.color,'natural');assert.equal(photo.renderer,'lab-1');
 r=await call(app,'/api/admin/photos/'+photo.id,'PUT',{color:'vivid'},auth);assert.equal(r.status,200,r.bytes.toString());
 const vivid=r.json().photos[0];assert.notEqual(vivid.renderVersion,photo.renderVersion);assert.notEqual(vivid.displaySha256,photo.displaySha256,'chroma must change the panel data');
 app.store.write(s=>{delete s.photos[0].renderer;});app.close();
 const again=await createApp({dataDir:dir});t.after(()=>again.close());assert.equal(await again.colorMigration,1);
 const migrated=again.store.data.photos[0];assert.equal(migrated.color,'natural','old vivid default maps to natural');assert.equal(migrated.renderer,'lab-1');assert.equal(migrated.displaySha256,photo.displaySha256,'migration renders exactly like a fresh natural upload');
 assert.ok(again.store.data.events.some(e=>/墨水校准算法重新生成 1 张/.test(e.message)));
 again.close();const third=await createApp({dataDir:dir});t.after(()=>third.close());assert.equal(await third.colorMigration,0,'migration runs only once');
});
test('display confirmation updates the reported photo immediately without advancing the playlist',async t=>{
 const {app}=await fixture(t),auth=await initialize(app);const key=(await call(app,'/api/admin/enrollment-key','GET',undefined,auth)).json().key,deviceAuth={authorization:'Bearer '+key};
 for(const [title,color] of [['甲',0],['乙',255]])assert.equal((await call(app,'/api/admin/photos','POST',{title,categoryId:'vangogh',data:pngData(color)},auth)).status,201);
 await call(app,'/api/admin/default-config','PUT',{...cfg,categoryIds:['vangogh']},auth);
 const sync=b=>call(app,'/api/v1/device/sync','POST',{deviceId:'ack-frame',...b},deviceAuth),displayed=b=>call(app,'/api/v1/device/displayed','POST',{deviceId:'ack-frame',...b},deviceAuth);
 const first=(await sync({requestId:'a'})).json().photo,version=new URL(first.url,'http://x').searchParams.get('v');
 assert.equal((await call(app,'/api/v1/device/displayed','POST',{deviceId:'ack-frame',photoId:first.id})).status,401);
 assert.equal((await displayed({photoId:''})).status,400);assert.equal((await displayed({photoId:first.id,photoVersion:'bad'})).status,400);
 assert.equal((await call(app,'/api/v1/device/displayed','POST',{deviceId:'unknown',photoId:first.id},deviceAuth)).status,404);
 assert.equal((await displayed({photoId:first.id,photoVersion:version})).status,200);
 const device=()=>app.store.data.devices.find(d=>d.id==='ack-frame');assert.equal(device().currentPhotoId,first.id);assert.equal(device().currentPhotoVersion,version);assert.equal(device().lastDeliveredId,first.id,'confirmation must not select another photo');
 assert.notEqual((await sync({requestId:'b',currentPhotoId:first.id})).json().photo.id,first.id,'the next scheduled sync still advances');
 await call(app,'/api/admin/devices/ack-frame','PUT',{disabled:true},auth);assert.equal((await displayed({photoId:first.id})).status,403);
});
test('offline hotspot delay is configurable, validated, and defaults for configs saved before it existed',async t=>{
 const {app}=await fixture(t),auth=await initialize(app);const key=(await call(app,'/api/admin/enrollment-key','GET',undefined,auth)).json().key,deviceAuth={authorization:'Bearer '+key};
 const sync=r=>call(app,'/api/v1/device/sync','POST',{deviceId:'hotspot-frame',requestId:r},deviceAuth);
 assert.equal((await sync('a')).json().config.offlineHotspotSeconds,600);
 app.store.write(s=>{delete s.defaultConfig.offlineHotspotSeconds;});assert.equal((await sync('b')).json().config.offlineHotspotSeconds,600,'legacy default config');
 assert.equal((await call(app,'/api/admin/default-config','PUT',{...cfg,offlineHotspotSeconds:30},auth)).status,400);
 assert.equal((await call(app,'/api/admin/devices/hotspot-frame','PUT',{config:{...cfg,offlineHotspotSeconds:1800}},auth)).status,200);
 assert.equal((await sync('c')).json().config.offlineHotspotSeconds,1800);
 app.store.write(s=>{delete s.devices[0].config.offlineHotspotSeconds;});assert.equal((await sync('d')).json().config.offlineHotspotSeconds,600,'legacy device config');
});
test('tone overrides, live simulation, default colour and bulk re-render',async t=>{
 const {app}=await fixture(t),auth=await initialize(app);
 let r=await call(app,'/api/admin/photos','POST',{title:'调色',categoryId:'vangogh',data:pngData(120)},auth);assert.equal(r.status,201,r.bytes.toString());
 const photo=r.json().photos[0];assert.deepEqual([photo.chroma,photo.brightness,photo.contrast],[1,0,1]);
 const sim=await call(app,`/api/admin/photos/${photo.id}/simulate`,'POST',{chroma:1.4,brightness:10,contrast:1.2},auth);assert.equal(sim.status,200);assert.equal(sim.headers['Content-Type'],'image/png');
 const png=PNG.sync.read(sim.bytes);assert.deepEqual([png.width,png.height],[600,800]);
 assert.equal((await call(app,`/api/admin/photos/${photo.id}/simulate`,'POST',{chroma:3})).status,401);
 assert.equal((await call(app,`/api/admin/photos/${photo.id}/simulate`,'POST',{chroma:3},auth)).status,400);
 assert.equal((await call(app,`/api/admin/photos/${photo.id}/simulate`,'POST',{cropX:.8,cropY:0,cropW:.4,cropH:1},auth)).status,400);
 assert.equal(app.store.data.photos[0].renderVersion,photo.renderVersion,'simulation never stores a render');
 r=await call(app,'/api/admin/photos/'+photo.id,'PUT',{brightness:12,contrast:1.2},auth);const tuned=r.json().photos[0];assert.equal(tuned.brightness,12);assert.notEqual(tuned.displaySha256,photo.displaySha256);
 assert.equal((await call(app,'/api/admin/photo-defaults','PUT',{color:'neon'},auth)).status,400);
 r=await call(app,'/api/admin/photo-defaults','PUT',{color:'standard'},auth);assert.equal(r.json().defaultColor,'standard');
 r=await call(app,'/api/admin/photos','POST',{title:'默认',categoryId:'vangogh',data:pngData(60)},auth);assert.equal(r.json().photos.find(p=>p.title==='默认').chroma,1.15);
 r=await call(app,'/api/admin/photos/rerender','POST',{},auth);assert.equal(r.status,202);assert.ok(r.json().rerender);
 assert.equal((await call(app,'/api/admin/photos/rerender','POST',{},auth)).status,409);
 for(let i=0;i<200&&(await call(app,'/api/admin/state','GET',undefined,auth)).json().rerender;i++)await new Promise(res=>setTimeout(res,50));
 const after=app.store.data.photos.find(p=>p.id===photo.id);assert.equal(after.color,'standard');assert.equal(after.brightness,0,'bulk re-render resets per-photo tweaks');
 assert.ok(app.store.data.events.some(e=>/按默认色彩重新生成 2 张/.test(e.message)));
});
test('sending a photo to a frame overrides the playlist until the frame reports showing it',async t=>{
 const {app}=await fixture(t),auth=await initialize(app);const key=(await call(app,'/api/admin/enrollment-key','GET',undefined,auth)).json().key,deviceAuth={authorization:'Bearer '+key};
 for(const [title,color] of [['甲',0],['乙',255],['丙',128]])assert.equal((await call(app,'/api/admin/photos','POST',{title,categoryId:'vangogh',data:pngData(color)},auth)).status,201);
 await call(app,'/api/admin/default-config','PUT',{...cfg,categoryIds:['vangogh']},auth);
 const sync=b=>call(app,'/api/v1/device/sync','POST',{deviceId:'push-frame',...b},deviceAuth);
 const first=(await sync({requestId:'a'})).json().photo;const device=()=>app.store.data.devices.find(d=>d.id==='push-frame');assert.equal(device().address,'127.0.0.1');
 const target=app.store.data.photos.find(p=>p.id!==first.id&&p.title==='丙')||app.store.data.photos.find(p=>p.id!==first.id);
 assert.equal((await call(app,'/api/admin/devices/push-frame/show','POST',{photoId:target.id})).status,401);
 assert.equal((await call(app,'/api/admin/devices/missing/show','POST',{photoId:target.id},auth)).status,404);
 const r=await call(app,'/api/admin/devices/push-frame/show','POST',{photoId:target.id},auth);assert.equal(r.status,200);assert.equal(r.json().woke,false,'nothing listens on the test address');
 assert.equal(device().pushPhotoId,target.id);
 assert.equal((await sync({requestId:'b',currentPhotoId:first.id})).json().photo.id,target.id,'pushed photo comes first');
 assert.equal((await sync({requestId:'c',currentPhotoId:first.id})).json().photo.id,target.id,'and is resent until shown');
 assert.equal((await call(app,'/api/v1/device/displayed','POST',{deviceId:'push-frame',photoId:target.id},deviceAuth)).status,200);assert.equal(device().pushPhotoId,null);
 assert.notEqual((await sync({requestId:'d',currentPhotoId:target.id})).json().photo.id,target.id,'playlist resumes after it');
 await call(app,'/api/admin/photos/'+first.id,'PUT',{enabled:false},auth);
 assert.equal((await call(app,'/api/admin/devices/push-frame/show','POST',{photoId:first.id},auth)).status,409);
});
test('photos carry an optional author that can be set on upload, edited and cleared',async t=>{
 const {app}=await fixture(t),auth=await initialize(app);
 let r=await call(app,'/api/admin/photos','POST',{title:'星月夜',author:'  文森特·梵高  ',categoryId:'vangogh',data:pngData(90)},auth);assert.equal(r.status,201);
 const photo=r.json().photos[0];assert.equal(photo.author,'文森特·梵高');
 r=await call(app,'/api/admin/photos/'+photo.id,'PUT',{author:'梵高'},auth);assert.equal(r.json().photos[0].author,'梵高');assert.equal(r.json().photos[0].renderVersion,photo.renderVersion,'metadata edits do not re-render');
 assert.equal((await call(app,'/api/admin/photos/'+photo.id,'PUT',{author:42},auth)).status,400);
 r=await call(app,'/api/admin/photos/'+photo.id,'PUT',{author:''},auth);assert.equal(r.json().photos[0].author,null);
 r=await call(app,'/api/admin/photos','POST',{title:'无作者',categoryId:'vangogh',data:pngData(30)},auth);assert.equal(r.json().photos.find(p=>p.title==='无作者').author,null);
});
