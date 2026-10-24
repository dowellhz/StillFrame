import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {Readable,Writable} from 'node:stream';
import {createSimulator} from '../server.mjs';

// Exercise the real HTTP handler in memory: no network port or socket is needed.
function request(server,url,method='GET',body){return new Promise((resolve,reject)=>{
 const req=Readable.from(body===undefined?[]:[Buffer.from(JSON.stringify(body))]);req.url=url;req.method=method;req.headers={'content-type':'application/json'};
 let status,headers,chunks=[];const res=new Writable({write(chunk,encoding,cb){chunks.push(Buffer.from(chunk));cb();}});
 res.writeHead=(s,h)=>{status=s;headers=h;return res;};res.on('finish',()=>{const data=Buffer.concat(chunks);resolve({status,headers,data,json:()=>JSON.parse(data)});});res.on('error',reject);server.emit('request',req,res);
});}
const config={interval:180,category:'vangogh',order:'sequence'};
test('first request registers once; default and dedicated config synchronize on next request',async()=>{
 const dir=await mkdtemp(path.join(os.tmpdir(),'stillframe-test-'));try{
 const server=await createSimulator({dataDir:dir});let r=await request(server,'/api/sync','POST',{id:'test-frame'});assert.equal(r.status,200);assert.equal(r.json().registered,true);assert.equal(r.json().source,'default');assert.ok(r.json().photo);
 const first=r.json().photo.id;r=await request(server,'/api/default','PUT',config);assert.equal(r.status,200);
 r=await request(server,'/api/sync','POST',{id:'test-frame',currentPhoto:first});assert.equal(r.json().registered,false);assert.deepEqual(r.json().config,config);assert.notEqual(r.json().photo.id,first);
 r=await request(server,'/api/devices/test-frame','PUT',{name:'卧室',config:{...config,interval:900,category:'people'}});assert.equal(r.status,200);
 r=await request(server,'/api/sync','POST',{id:'test-frame'});assert.equal(r.json().source,'device');assert.equal(r.json().config.interval,900);assert.equal(r.json().photo,null);
 const restarted=await createSimulator({dataDir:dir});r=await request(restarted,'/api/state');assert.equal(r.json().devices.length,1);assert.equal(r.json().devices[0].name,'卧室');assert.equal(r.json().devices[0].config.interval,900);
 await request(restarted,'/api/devices/test-frame','PUT',{config:null});r=await request(restarted,'/api/sync','POST',{id:'test-frame'});assert.equal(r.json().source,'default');assert.deepEqual(r.json().config,config);
 }finally{await rm(dir,{recursive:true,force:true});}
});
test('nested categories include descendants; server and SD photos stay separate',async()=>{
 const dir=await mkdtemp(path.join(os.tmpdir(),'stillframe-test-'));try{
 const s=await createSimulator({dataDir:dir});await request(s,'/api/default','PUT',{...config,category:'art'});let r=await request(s,'/api/sync','POST',{id:'nested-test'});assert.equal(r.json().photo.category,'vangogh');assert.equal(r.json().photo.storage,'server');
 r=await request(s,'/api/categories','POST',{name:'莫奈',parent:'art'});const c=r.json().categories.find(x=>x.name==='莫奈');assert.equal(c.parent,'art');
 r=await request(s,'/api/categories/'+c.id,'PUT',{name:'Claude Monet'});assert.ok(r.json().categories.some(x=>x.name==='Claude Monet'));
 assert.equal((await request(s,'/api/categories/art','DELETE')).status,409);
 r=await request(s,'/api/sd/seed','POST',{});assert.equal(r.json().photos.filter(x=>x.storage==='sd').length,4);
 r=await request(s,'/api/sd/seed','POST',{});assert.equal(r.json().photos.filter(x=>x.storage==='sd').length,4);
 await request(s,'/api/default','PUT',{...config,category:c.id});r=await request(s,'/api/sync','POST',{id:'nested-test'});assert.equal(r.json().photo,null);
 assert.equal((await request(s,'/api/categories/'+c.id,'DELETE')).status,200);
 }finally{await rm(dir,{recursive:true,force:true});}
});
test('upload, persistence, deletion, invalid config and private file protection',async()=>{
 const dir=await mkdtemp(path.join(os.tmpdir(),'stillframe-test-'));try{
 const s=await createSimulator({dataDir:dir});assert.equal((await request(s,'/api/default','PUT',{...config,interval:1})).status,400);assert.equal((await request(s,'/api/default','PUT',{...config,category:'missing'})).status,400);assert.equal((await request(s,'/api/sync','POST',{id:'../../bad'})).status,400);
 const data='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jB4kAAAAASUVORK5CYII=';
 let r=await request(s,'/api/photos','POST',{name:'测试照片',category:'people',storage:'sd',data});assert.equal(r.status,201);const photo=r.json().photos.find(x=>x.name==='测试照片');assert.equal(photo.storage,'sd');assert.equal((await request(s,photo.url)).status,200);
 r=await request(s,'/api/photos/'+photo.id,'DELETE');assert.equal(r.status,200);assert.equal((await request(s,photo.url)).status,404);
 assert.equal((await request(s,'/server.mjs')).status,404);assert.equal((await request(s,'/painting/%2e%2e%2fdoc/GDEP133C02.pdf')).status,403);assert.equal((await request(s,'/')).status,200);assert.equal((await request(s,'/app.js')).status,200);
 const q=await request(s,'/assets/setup-qr.png');assert.equal(q.status,200);assert.equal(q.data.subarray(1,4).toString(),'PNG');
 }finally{await rm(dir,{recursive:true,force:true});}
});
