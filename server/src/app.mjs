import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import crypto from 'node:crypto';
import {promisify} from 'node:util';
import {Store,id,stamp,validateConfig,categorySet,defaults} from './store.mjs';
import {inspectRom,compatible,firmwareOffer,MAX_ROM} from './firmware.mjs';
import {renderImage,queuedJobs} from './jobs.mjs';
import {colorLevels,toneLimits,RENDERER} from './image.mjs';
const scrypt=promisify(crypto.scrypt),ROOT=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const fail=(message,status=400)=>Object.assign(new Error(message),{status});
const hash=b=>crypto.createHash('sha256').update(b).digest('hex');
const equal=(a,b)=>typeof a==='string'&&typeof b==='string'&&Buffer.byteLength(a)===Buffer.byteLength(b)&&crypto.timingSafeEqual(Buffer.from(a),Buffer.from(b));
const text=(v,max=100)=>typeof v==='string'?v.trim().slice(0,max):'';
export async function createApp({dataDir=process.env.STILLFRAME_DATA_DIR||path.join(ROOT,'data')}={}){
 const store=new Store(dataDir),sessions=new Map(),attempts=new Map();await fs.mkdir(path.join(dataDir,'photos'),{recursive:true,mode:0o700});
 function response(res,status,body,headers={}){res.writeHead(status,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff',...headers});res.end(JSON.stringify(body));}
 async function readBody(req,max=30*1024*1024){let bytes=0,chunks=[];for await(const c of req){bytes+=c.length;if(bytes>max)throw fail('请求过大，单张图片最多 20 MB',413);chunks.push(c);}try{return JSON.parse(Buffer.concat(chunks).toString('utf8')||'{}');}catch{throw fail('请求内容不是有效 JSON');}}
 function cookie(req){return /(?:^|;\s*)stillframe_session=([A-Za-z0-9_-]+)/.exec(req.headers.cookie||'')?.[1];}
 function isAdmin(req){const token=cookie(req),s=sessions.get(token);if(!s)return false;if(s.expires<Date.now()){sessions.delete(token);return false;}return true;}
 function session(req,res){const token=crypto.randomBytes(32).toString('base64url');if(sessions.size>=100)sessions.delete(sessions.keys().next().value);sessions.set(token,{expires:Date.now()+86400000});return {'Set-Cookie':`stillframe_session=${token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400${req.socket?.encrypted?'; Secure':''}`};}
 function admin(req){if(!isAdmin(req))throw fail('请先登录管理员',401);}
 function deviceAuth(req){const token=/^Bearer (.+)$/.exec(req.headers.authorization||'')?.[1];if(!equal(token,store.data.enrollmentKey))throw fail('设备接入凭证无效',401);if(!store.data.admin)throw fail('服务器尚未初始化',503);}
 function limited(req){const ip=req.socket?.remoteAddress||'local';const time=Date.now();if(attempts.size>2000)for(const[k,v]of attempts)if(v.until<time)attempts.delete(k);const a=attempts.get(ip);if(a&&a.until>time&&a.count>=10)throw fail('尝试次数过多，请 10 分钟后再试',429);if(!a||a.until<time)attempts.set(ip,{count:1,until:time+600000});else a.count++;}
 function state(){const s=store.data;return {schemaVersion:1,defaultConfig:s.defaultConfig,categories:s.categories,photos:s.photos,devices:s.devices.map(d=>({...d,lastRequestId:undefined,lastResponse:undefined})),events:s.events,firmwares:s.firmwares||[],defaultColor:s.defaultColor||'natural',colorLevels,toneLimits,rerender:rerendering,statistics:{photos:s.photos.length,devices:s.devices.length,categories:s.categories.length,originalBytes:s.photos.reduce((n,p)=>n+p.originalBytes,0),displayBytes:s.photos.length*960000,queuedJobs:queuedJobs()},serverTime:stamp()};}
 // Choosing another preset without explicit tone values applies that preset's values.
 function edited(photo,b){return {...photo,...(b.color!==undefined&&b.color!==photo.color?{chroma:undefined,brightness:undefined,contrast:undefined}:{}),...b};}
 function photoSettings(b){const fit=b.fit??'cover',rotation=b.rotation??0,dither=b.dither??true,color=b.color??store.data.defaultColor??'natural',cropX=b.cropX??0,cropY=b.cropY??0,cropW=b.cropW??1,cropH=b.cropH??1,crop=[cropX,cropY,cropW,cropH];if(!['contain','cover'].includes(fit)||![0,90,180,270].includes(rotation)||typeof dither!=='boolean'||!Object.hasOwn(colorLevels,color)||!crop.every(v=>typeof v==='number'&&Number.isFinite(v))||cropX<0||cropY<0||cropW<.05||cropH<.05||cropX+cropW>1.0001||cropY+cropH>1.0001)throw fail('图片排版参数无效');const tone={};for(const [k,[lo,hi]] of Object.entries(toneLimits)){const v=b[k]??colorLevels[color][k];if(typeof v!=='number'||!Number.isFinite(v)||v<lo||v>hi)throw fail('色彩微调参数超出范围');tone[k]=Math.round(v*100)/100;}return {fit,rotation,dither,color,cropX,cropY,cropW,cropH,...tone};}
 function photoCollections(s,b){const raw=Array.isArray(b.collectionIds)?b.collectionIds:(b.categoryId?[b.categoryId]:[]);if(!raw.length||raw.length>100||raw.some(x=>typeof x!=='string'||!s.categories.some(c=>c.id===x)))throw fail('请至少选择一个有效收藏集');return [...new Set(raw)];}
 async function files(res,file,type,req,onSent,expectedSha){let bytes;try{bytes=await fs.readFile(file);}catch(e){if(e.code==='ENOENT')throw fail('文件不存在',404);throw e;}if(expectedSha&&hash(bytes)!==expectedSha)throw fail('保存的 ROM 校验失败，请重新上传',409);if(req.method==='GET'&&onSent)res.once('finish',()=>{try{onSent(bytes.length);}catch(e){console.error('Stillframe download record failed:',e.code||e.name);}});res.writeHead(200,{'Content-Type':type,'Content-Length':bytes.length,'Cache-Control':'private, no-cache','X-Content-Type-Options':'nosniff'});res.end(req.method==='HEAD'?undefined:bytes);}
 const server=http.createServer(async(req,res)=>{
  const started=Date.now();
  try{
   const u=new URL(req.url,'http://localhost'),p=u.pathname,m=req.method;
   if(['POST','PUT','PATCH','DELETE'].includes(m)&&req.headers.origin){let origin;try{origin=new URL(req.headers.origin);}catch{throw fail('来源无效',403);}if(origin.host!==req.headers.host)throw fail('禁止跨站修改请求',403);}
   if(p==='/api/health'&&m==='GET')return response(res,200,{ok:true,name:'Stillframe',version:'0.1.29',ready:!!store.data.admin});
   if(p==='/api/auth/status'&&m==='GET')return response(res,200,{initialized:!!store.data.admin,authenticated:isAdmin(req)});
   if(p==='/api/auth/setup'&&m==='POST'){
    limited(req);if(store.data.admin)throw fail('管理员已创建',409);const b=await readBody(req,8192),username=text(b.username,60);if(!username||typeof b.password!=='string'||b.password.length<10||b.password.length>128)throw fail('用户名不能为空，密码需为 10～128 位');const salt=crypto.randomBytes(16).toString('hex'),passwordHash=(await scrypt(b.password,salt,64)).toString('hex');store.write(s=>{if(s.admin)throw fail('管理员已创建',409);s.admin={username,salt,passwordHash};store.event(s,'setup','管理员已创建');});return response(res,201,{ok:true},session(req,res));
   }
   if(p==='/api/auth/login'&&m==='POST'){limited(req);const b=await readBody(req,8192),a=store.data.admin;if(!a||typeof b.password!=='string'||b.password.length>128)throw fail('用户名或密码错误',401);const key=(await scrypt(b.password,a.salt,64)).toString('hex');if(b.username!==a.username||!equal(key,a.passwordHash))throw fail('用户名或密码错误',401);return response(res,200,{ok:true},session(req,res));}
   if(p==='/api/auth/logout'&&m==='POST'){sessions.delete(cookie(req));return response(res,200,{ok:true},{'Set-Cookie':'stillframe_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'});}
   if(p==='/api/v1/device/sync'&&m==='POST'){
    deviceAuth(req);const b=await readBody(req,16384);if(typeof b.deviceId!=='string'||!/^[A-Za-z0-9:_-]{4,100}$/.test(b.deviceId))throw fail('deviceId 需为 4～100 位字母、数字或 : _ -');if(b.requestId!==undefined&&(typeof b.requestId!=='string'||b.requestId.length>100))throw fail('requestId 无效');
    let output;store.write(s=>{let d=s.devices.find(x=>x.id===b.deviceId);const registered=!d;if(!d){d={id:b.deviceId,name:'Stillframe '+b.deviceId.slice(-4),config:null,disabled:false,createdAt:stamp(),lastSeen:null,currentPhotoId:null,lastDeliveredId:null};s.devices.push(d);store.event(s,'register',`新设备 ${d.name} 自动建档`,d.id);}if(d.disabled)throw fail('设备已停用',403);d.lastSeen=stamp();d.address=(req.socket?.remoteAddress||'').replace(/^::ffff:/,'')||null;if(b.firmwareVersion!==undefined)d.firmwareVersion=text(b.firmwareVersion,60);if(b.batteryPercent!==undefined&&Number.isFinite(b.batteryPercent)&&b.batteryPercent>=0&&b.batteryPercent<=100)d.batteryPercent=b.batteryPercent;
     // Hardware identity is reported by firmware compiled for this board; an
     // unreported/legacy board can never receive a remote upgrade.
     for(const k of ['boardModel','panelModel','chipModel'])if(typeof b[k]==='string')d[k]=text(b[k],60);
     if(Number.isInteger(b.otaProtocol))d.otaProtocol=b.otaProtocol;
     if(Number.isInteger(b.otaSlotBytes))d.otaSlotBytes=b.otaSlotBytes;
     if(typeof b.firmwareSha256==='string'&&/^[a-f0-9]{64}$/.test(b.firmwareSha256))d.firmwareSha256=b.firmwareSha256;
     if(d.firmwareTask&&['queued','offered','cancelled'].includes(d.firmwareTask.status)&&d.firmwareSha256){
      const installed=(s.firmwares||[]).find(f=>f.id===d.firmwareTask.firmwareId);
      if(installed&&compatible(d,installed)&&b.firmwareSha256===installed.sha256){d.firmwareTask.status='succeeded';d.firmwareTask.message=d.firmwareTask.cancelledAt?'设备在取消任务后仍完成了升级，已确认实际版本':'新固件已通过启动确认';d.firmwareTask.completedAt=stamp();store.event(s,'firmware',`${d.name}：升级成功，版本 ${installed.version}`,d.id);}
     }
     if(b.requestId&&d.lastRequestId===b.requestId&&d.lastResponse){
      output={...d.lastResponse,firmware:firmwareOffer(s,d)};
      d.nextRefreshAt=new Date(Date.now()+output.nextRequestAfterSeconds*1000).toISOString();
      // Old cached responses keep their image/version but gain download attribution.
      if(output.photo){const download=new URL(output.photo.url,'http://localhost');download.searchParams.set('deviceId',d.id);output.photo.url=download.pathname+download.search;}
      return;
     }
     const c={...defaults,...(d.config||s.defaultConfig)},categories=categorySet(s,c.categoryIds,c.includeChildren),pool=s.photos.filter(x=>x.enabled&&(c.categoryIds.length===0||(x.collectionIds||[x.categoryId]).some(id=>categories.has(id)))&&(c.contentTypes.length===0||c.contentTypes.includes(x.contentType||'painting'))&&(c.subjects.length===0||c.subjects.some(value=>(x.subjects||[]).includes(value)))&&(c.creators.length===0||c.creators.includes(x.creator||x.author||''))&&(c.movements.length===0||c.movements.some(value=>(x.tags||[]).includes(value)))&&(c.tags.length===0||c.tags.some(value=>(x.tags||[]).includes(value)))).sort((a,b)=>a.createdAt.localeCompare(b.createdAt)||a.id.localeCompare(b.id));
     if(b.currentPhotoVersion!==undefined&&b.currentPhotoVersion!==null&&!/^[a-f0-9-]{36}$/.test(b.currentPhotoVersion))throw fail('显示照片版本无效');
     if(typeof b.currentPhotoId==='string'){
      if(d.currentPhotoId!==b.currentPhotoId)d.currentPhotoVersion=null;
      d.currentPhotoId=b.currentPhotoId||null;
      if(b.currentPhotoVersion!==undefined)d.currentPhotoVersion=b.currentPhotoVersion;
      d.currentPhotoReportedAt=d.currentPhotoId?stamp():null;
     }
     const pushed=d.pushPhotoId&&s.photos.find(x=>x.id===d.pushPhotoId&&x.enabled);if(!pushed||b.currentPhotoId===d.pushPhotoId)d.pushPhotoId=null;
     let photo=d.pushPhotoId?pushed:pool.find(x=>x.id===d.lastDeliveredId&&x.id!==b.currentPhotoId);
     if(!photo&&pool.length){const current=pool.findIndex(x=>x.id===b.currentPhotoId);const others=pool.filter(x=>x.id!==b.currentPhotoId);photo=c.order==='random'?(others.length?others[crypto.randomInt(others.length)]:pool[0]):pool[(current+1)%pool.length];}
     d.lastDeliveredId=photo?.id||null;d.lastDeliveredVersion=photo?.renderVersion||null;const revision=hash(JSON.stringify(c)).slice(0,16);
     output={schemaVersion:1,firmware:firmwareOffer(s,d),registered,deviceId:d.id,serverTime:stamp(),config:{...c,revision,source:d.config?'device':'default'},photo:photo?{id:photo.id,title:photo.title,width:1200,height:1600,format:'spectra6-4bpp-row-major',bytes:960000,sha256:photo.displaySha256,url:`/api/v1/device/photos/${photo.id}/display.bin?v=${photo.renderVersion}&deviceId=${encodeURIComponent(d.id)}`} : null,nextRequestAfterSeconds:c.intervalSeconds};
     d.nextRefreshAt=new Date(Date.now()+c.intervalSeconds*1000).toISOString();
     d.lastRequestId=b.requestId||null;d.lastResponse=output;
    });return response(res,200,output);
   }
   const deviceFirmware=/^\/api\/v1\/device\/firmware\/([a-f0-9-]+)$/.exec(p);
   if(deviceFirmware&&m==='GET'){
    deviceAuth(req);const d=store.data.devices.find(x=>x.id===u.searchParams.get('deviceId')),f=(store.data.firmwares||[]).find(x=>x.id===deviceFirmware[1]);
    if(!d||!f||!compatible(d,f)||d.firmwareTask?.firmwareId!==f.id||d.firmwareTask?.id!==u.searchParams.get('taskId')||!['queued','offered'].includes(d.firmwareTask.status))throw fail('升级任务不存在、已取消或型号不匹配',409);
    return await files(res,path.join(dataDir,'firmware',f.id+'.bin'),'application/octet-stream',req,undefined,f.sha256);
   }
   // Immediate display confirmation after a refresh. It records what the panel shows without
   // selecting a new photo, so the dashboard no longer lags one sync interval behind.
   if(p==='/api/v1/device/displayed'&&m==='POST'){
    deviceAuth(req);const b=await readBody(req,8192);if(typeof b.photoId!=='string'||!b.photoId||b.photoId.length>80)throw fail('照片 ID 无效');if(b.photoVersion!==undefined&&b.photoVersion!==null&&!/^[a-f0-9-]{36}$/.test(b.photoVersion))throw fail('显示照片版本无效');
    store.write(s=>{const d=s.devices.find(x=>x.id===b.deviceId);if(!d)throw fail('设备不存在',404);if(d.disabled)throw fail('设备已停用',403);if(d.currentPhotoId!==b.photoId)d.currentPhotoVersion=null;d.currentPhotoId=b.photoId;if(d.pushPhotoId===b.photoId)d.pushPhotoId=null;if(b.photoVersion!==undefined)d.currentPhotoVersion=b.photoVersion;d.currentPhotoReportedAt=d.lastSeen=stamp();});return response(res,200,{ok:true});
   }
   if(p==='/api/v1/device/firmware-result'&&m==='POST'){
    deviceAuth(req);const b=await readBody(req,8192);store.write(s=>{const d=s.devices.find(x=>x.id===b.deviceId);if(!d||d.disabled||!d.firmwareTask||d.firmwareTask.id!==b.taskId)throw fail('升级任务不存在',404);if(!['failed','installed'].includes(b.status))throw fail('升级结果无效');if(d.firmwareTask.status==='succeeded')return;if(d.firmwareTask.status==='cancelled'&&b.status!=='installed')throw fail('升级任务已取消',409);d.firmwareTask.status=b.status==='installed'?'offered':'failed';d.firmwareTask.message=text(b.message,160);d.firmwareTask.updatedAt=stamp();store.event(s,'firmware',`${d.name}：${b.status==='installed'?'已写入，等待重启确认':'升级失败'} ${d.firmwareTask.message}`,d.id);});return response(res,200,{ok:true});
   }
   const devicePhoto=/^\/api\/v1\/device\/photos\/([a-f0-9-]+)\/display\.bin$/.exec(p);
   if(devicePhoto&&['GET','HEAD'].includes(m)){
    deviceAuth(req);const photo=store.data.photos.find(x=>x.id===devicePhoto[1]&&x.enabled);if(!photo)throw fail('照片不存在或已停用',404);
    const version=u.searchParams.get('v')||photo.renderVersion;if(!/^[a-f0-9-]{36}$/.test(version))throw fail('图片版本无效');
    const deviceId=u.searchParams.get('deviceId');
    if(deviceId){const device=store.data.devices.find(d=>d.id===deviceId);if(!device)throw fail('设备不存在',404);if(device.disabled)throw fail('设备已停用',403);}
    return await files(res,path.join(dataDir,'photos',photo.id,version+'.bin'),'application/octet-stream',req,deviceId?bytes=>{
     store.write(s=>{const d=s.devices.find(d=>d.id===deviceId);if(!d)return;
      const at=stamp();d.lastDownloadedPhotoId=photo.id;d.lastDownloadedVersion=version;d.lastDownloadedAt=at;
      const entry={id:id(),photoId:photo.id,title:photo.title,version,at,bytes};
      d.downloadHistory=[entry,...(d.downloadHistory||[])].slice(0,20);
      store.event(s,'download',`${d.name}：已发送照片「${photo.title}」`,d.id);
     });
    }:undefined);
   }
   if(p.startsWith('/api/admin/')){
    admin(req);
    if(p==='/api/admin/firmwares'&&m==='POST'){
     const b=await readBody(req,Math.ceil(MAX_ROM*4/3)+8192);if(typeof b.data!=='string'||!/^data:application\/octet-stream;base64,[A-Za-z0-9+/]+={0,2}$/.test(b.data))throw fail('请上传应用 bin 文件');
     const bytes=Buffer.from(b.data.split(',')[1],'base64'),info=inspectRom(bytes);if((store.data.firmwares||[]).some(f=>f.sha256===info.sha256))throw fail('此 ROM 已上传',409);
     const rom={id:id(),...info,createdAt:stamp(),filename:text(b.filename,120)||'Stillframe.bin'};await fs.mkdir(path.join(dataDir,'firmware'),{recursive:true,mode:0o700});const file=path.join(dataDir,'firmware',rom.id+'.bin');await fs.writeFile(file,bytes,{mode:0o600,flag:'wx'});
     try{store.write(s=>{s.firmwares||=[];if(s.firmwares.some(f=>f.sha256===rom.sha256))throw fail('此 ROM 已上传',409);s.firmwares.push(rom);store.event(s,'firmware',`上传 ROM ${rom.version} · ${rom.boardModel}`);});}catch(e){await fs.rm(file,{force:true});throw e;}return response(res,201,state());
    }
    const deploy=/^\/api\/admin\/devices\/([A-Za-z0-9:_-]+)\/firmware$/.exec(p);
    if(deploy&&m==='POST'){
     const b=await readBody(req,8192),uploaded=(store.data.firmwares||[]).find(x=>x.id===b.firmwareId);if(!uploaded)throw fail('ROM 不存在',404);const checked=inspectRom(await fs.readFile(path.join(dataDir,'firmware',uploaded.id+'.bin')));if(checked.sha256!==uploaded.sha256)throw fail('已保存 ROM 的 SHA-256 不匹配，请重新上传');store.write(s=>{const d=s.devices.find(x=>x.id===deploy[1]),f=(s.firmwares||[]).find(x=>x.id===b.firmwareId);if(!d||!f)throw fail('设备或 ROM 不存在',404);if(!compatible(d,f))throw fail('主板型号、屏幕、芯片、升级协议或分区容量不匹配；旧设备请先通过设备网页或有线方式更新');if(d.firmwareSha256===f.sha256)throw fail('设备已安装这个 ROM',409);if(d.firmwareTask&&['queued','offered'].includes(d.firmwareTask.status))throw fail('已有升级任务，请先取消',409);d.firmwareTask={id:id(),firmwareId:f.id,version:f.version,status:'queued',createdAt:stamp()};d.lastRequestId=null;d.lastResponse=null;store.event(s,'firmware',`${d.name}：等待下发 ROM ${f.version}`,d.id);});return response(res,200,state());
    }
    if(deploy&&m==='DELETE'){store.write(s=>{const d=s.devices.find(x=>x.id===deploy[1]);if(!d?.firmwareTask||!['queued','offered'].includes(d.firmwareTask.status))throw fail('没有可取消的升级任务',409);d.firmwareTask.status='cancelled';d.firmwareTask.cancelledAt=stamp();d.lastRequestId=null;d.lastResponse=null;store.event(s,'firmware',`${d.name}：已取消升级任务`,d.id);});return response(res,200,state());}
    if(p==='/api/admin/state'&&m==='GET')return response(res,200,state());
    if(p==='/api/admin/password'&&m==='PUT'){
     limited(req);const b=await readBody(req,8192),a=store.data.admin;
     if(typeof b.currentPassword!=='string'||b.currentPassword.length>128||typeof b.newPassword!=='string'||b.newPassword.length<10||b.newPassword.length>128)throw fail('新密码需为 10～128 位，请填写当前密码');
     if(b.confirmPassword!==b.newPassword)throw fail('两次新密码不一致');
     const currentHash=(await scrypt(b.currentPassword,a.salt,64)).toString('hex');if(!equal(currentHash,a.passwordHash))throw fail('当前密码不正确');
     if(b.currentPassword===b.newPassword)throw fail('新密码不能与当前密码相同');
     const salt=crypto.randomBytes(16).toString('hex'),passwordHash=(await scrypt(b.newPassword,salt,64)).toString('hex');
     admin(req);store.write(s=>{if(s.admin.passwordHash!==a.passwordHash)throw fail('密码已在另一会话中修改，请重新登录',409);s.admin={...s.admin,salt,passwordHash};store.event(s,'account','管理员密码已修改，旧登录会话已失效');});
     sessions.clear();return response(res,200,{ok:true},session(req,res));
    }
    if(p==='/api/admin/photo-defaults'&&m==='PUT'){const b=await readBody(req,8192);if(!Object.hasOwn(colorLevels,b.color))throw fail('色彩档位无效');store.write(s=>{s.defaultColor=b.color;store.event(s,'photo','照片默认色彩已更新');});return response(res,200,state());}
    if(p==='/api/admin/photos/rerender'&&m==='POST'){if(rerendering)throw fail('正在重新生成照片，请等待完成',409);const color=store.data.defaultColor||'natural';rerenderAll(store.data.photos,()=>true,()=>({color,chroma:undefined,brightness:undefined,contrast:undefined}),n=>`已按默认色彩重新生成 ${n} 张照片的显示数据`);return response(res,202,state());}
    if(p==='/api/admin/default-config'&&m==='PUT'){const b=await readBody(req,16384);store.write(s=>{s.defaultConfig=validateConfig(s,b);store.event(s,'config','默认播放配置已更新');});return response(res,200,state());}
    if(p==='/api/admin/enrollment-key'&&m==='GET')return response(res,200,{key:store.data.enrollmentKey});
    if(p==='/api/admin/enrollment-key'&&m==='POST'){store.write(s=>{s.enrollmentKey=crypto.randomBytes(24).toString('base64url');store.event(s,'credential','设备接入凭证已更换，旧凭证失效');});return response(res,200,{key:store.data.enrollmentKey});}
    if(p==='/api/admin/categories'&&m==='POST'){const b=await readBody(req,8192);store.write(s=>{const name=text(b.name,60);if(!name)throw fail('请填写收藏集名称');if(b.parentId&&!s.categories.some(x=>x.id===b.parentId))throw fail('上级收藏集不存在');if(s.categories.some(x=>x.name===name&&x.parentId===(b.parentId||null)))throw fail('同级收藏集名称已存在',409);s.categories.push({id:id(),name,parentId:b.parentId||null});});return response(res,201,state());}
    const cat=/^\/api\/admin\/categories\/([\w-]+)$/.exec(p);
    if(cat&&m==='PUT'){const b=await readBody(req,8192);store.write(s=>{const c=s.categories.find(x=>x.id===cat[1]);if(!c)throw fail('收藏集不存在',404);const name=text(b.name,60),parent=b.parentId||null;if(!name)throw fail('名称不能为空');if(parent&&(!s.categories.some(x=>x.id===parent)||categorySet(s,[c.id]).has(parent)))throw fail('上级收藏集无效，收藏集不能循环嵌套');if(s.categories.some(x=>x.id!==c.id&&x.name===name&&x.parentId===parent))throw fail('同级收藏集名称已存在',409);Object.assign(c,{name,parentId:parent});});return response(res,200,state());}
    if(cat&&m==='DELETE'){store.write(s=>{if(!s.categories.some(x=>x.id===cat[1]))throw fail('收藏集不存在',404);if(s.categories.some(x=>x.parentId===cat[1])||s.photos.some(x=>(x.collectionIds||[x.categoryId]).includes(cat[1])))throw fail('请先移出作品并删除下级收藏集',409);s.categories=s.categories.filter(x=>x.id!==cat[1]);for(const c of [s.defaultConfig,...s.devices.map(d=>d.config).filter(Boolean)])c.categoryIds=c.categoryIds.filter(x=>x!==cat[1]);});return response(res,200,state());}
    const show=/^\/api\/admin\/devices\/([A-Za-z0-9:_-]+)\/show$/.exec(p);
    if(show&&m==='POST'){const b=await readBody(req,8192);let address=null;store.write(s=>{const d=s.devices.find(x=>x.id===show[1]);if(!d)throw fail('设备不存在',404);if(d.disabled)throw fail('设备已停用',403);const photo=s.photos.find(x=>x.id===b.photoId);if(!photo)throw fail('照片不存在',404);if(!photo.enabled)throw fail('这张照片已停止播放，请先允许在相框中播放',409);d.pushPhotoId=photo.id;d.lastRequestId=null;d.lastResponse=null;address=d.address;store.event(s,'photo',`发送《${photo.title}》到 ${d.name}`,d.id);});let woke=false;if(address)try{woke=(await fetch(`http://${address.includes(':')?'['+address+']':address}/api/wake`,{method:'POST',headers:{authorization:'Bearer '+store.data.enrollmentKey},signal:AbortSignal.timeout(4000)})).status===202;}catch{}return response(res,200,{...state(),woke});}
    const dev=/^\/api\/admin\/devices\/([A-Za-z0-9:_-]+)$/.exec(p);
    if(dev&&m==='PUT'){const b=await readBody(req,16384);store.write(s=>{const d=s.devices.find(x=>x.id===dev[1]);if(!d)throw fail('设备不存在',404);if(b.name!==undefined){const name=text(b.name,60);if(!name)throw fail('设备名称不能为空');d.name=name;}if(b.config!==undefined)d.config=b.config===null?null:validateConfig(s,b.config);if(b.disabled!==undefined){if(typeof b.disabled!=='boolean')throw fail('停用状态无效');d.disabled=b.disabled;}d.lastRequestId=null;d.lastResponse=null;store.event(s,'config',`${d.name} 的配置已更新`,d.id);});return response(res,200,state());}
    if(dev&&m==='DELETE'){store.write(s=>{const i=s.devices.findIndex(x=>x.id===dev[1]);if(i<0)throw fail('设备不存在',404);const d=s.devices[i];s.devices.splice(i,1);store.event(s,'device',`已删除相框 ${d.name}（${d.id}）；若它仍在使用，下次联网会重新出现`);});return response(res,200,state());}
    if(p==='/api/admin/photos'&&m==='POST'){
     const b=await readBody(req),initialCollections=photoCollections(store.data,b),data=/^data:image\/(?:jpeg|png);base64,([A-Za-z0-9+/=]+)$/.exec(b.data||'');if(!data)throw fail('请上传 JPG 或 PNG 图片');const bytes=Buffer.from(data[1],'base64');if(bytes.length>20*1024*1024)throw fail('单张图片最多 20 MB',413);const sha=hash(bytes);if(store.data.photos.some(x=>x.sha256===sha))throw fail('这张照片已在相册中',409);const settings=photoSettings(b),result=await renderImage(bytes,settings),photoId=id(),version=id(),folder=path.join(dataDir,'photos',photoId);await fs.mkdir(folder,{mode:0o700});
     try{await Promise.all([fs.writeFile(path.join(folder,'original.'+result.ext),bytes),fs.writeFile(path.join(folder,version+'.bin'),result.bin),fs.writeFile(path.join(folder,version+'.png'),result.preview),fs.writeFile(path.join(folder,version+'.jpg'),result.thumbnail)]);store.write(s=>{const collectionIds=photoCollections(s,{collectionIds:initialCollections});if(s.photos.some(x=>x.sha256===sha))throw fail('这张照片已在相册中',409);const contentType=['painting','photo','illustration'].includes(b.contentType)?b.contentType:'painting',subjects=Array.isArray(b.subjects)?b.subjects.slice(0,12).map(x=>text(x,30)).filter(Boolean):[],tags=Array.isArray(b.tags)?b.tags.slice(0,30).map(x=>text(x,30)).filter(Boolean):[],people=Array.isArray(b.people)?b.people.slice(0,20).map(x=>text(x,60)).filter(Boolean):[];s.photos.push({id:photoId,title:text(b.title,120)||'未命名照片',author:text(b.author,60)||null,creator:text(b.creator,60)||text(b.author,60)||null,people,subjects,tags,contentType,location:text(b.location,80)||null,capturedAt:text(b.capturedAt,20)||null,facetsVersion:1,categoryId:collectionIds[0],collectionIds,enabled:true,createdAt:stamp(),originalBytes:bytes.length,width:result.width,height:result.height,ext:result.ext,sha256:sha,displaySha256:hash(result.bin),renderVersion:version,...settings,renderer:RENDERER});store.event(s,'photo','新增照片：'+(text(b.title,120)||'未命名照片'));});}catch(e){await fs.rm(folder,{recursive:true,force:true});throw e;}return response(res,201,state());
    }
    const photoRoute=/^\/api\/admin\/photos\/([a-f0-9-]+)(?:\/(original|preview|thumbnail|display|simulate))?$/.exec(p);
    if(photoRoute){const photo=store.data.photos.find(x=>x.id===photoRoute[1]);if(!photo)throw fail('照片不存在',404);const folder=path.join(dataDir,'photos',photo.id),variant=photoRoute[2];
     if(variant==='simulate'&&m==='POST'){const b=await readBody(req,16384),r=await renderImage(await fs.readFile(path.join(folder,'original.'+photo.ext)),photoSettings(edited(photo,b)),undefined,'simulate');res.writeHead(200,{'Content-Type':'image/png','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(Buffer.from(r.preview));return;}
     if(variant&&['GET','HEAD'].includes(m)){const version=u.searchParams.get('v')||photo.renderVersion;if(variant!=='original'&&!/^[a-f0-9-]{36}$/.test(version))throw fail('图片版本无效');const entry={original:['original.'+photo.ext,photo.ext==='png'?'image/png':'image/jpeg'],preview:[version+'.png','image/png'],thumbnail:[version+'.jpg','image/jpeg'],display:[version+'.bin','application/octet-stream']}[variant];return await files(res,path.join(folder,entry[0]),entry[1],req);}
     if(!variant&&m==='PUT'){const b=await readBody(req,16384);const settings=photoSettings(edited(photo,b)),changed=photo.renderer!==RENDERER||['fit','rotation','dither','color','chroma','brightness','contrast','cropX','cropY','cropW','cropH'].some(k=>settings[k]!==photo[k]);let result,version;if(changed){result=await renderImage(await fs.readFile(path.join(folder,'original.'+photo.ext)),settings);version=id();await Promise.all([fs.writeFile(path.join(folder,version+'.bin'),result.bin),fs.writeFile(path.join(folder,version+'.png'),result.preview),fs.writeFile(path.join(folder,version+'.jpg'),result.thumbnail)]);}
      store.write(s=>{const current=s.photos.find(x=>x.id===photo.id);if(!current)throw fail('照片已删除',409);if(b.title!==undefined){const title=text(b.title,120);if(!title)throw fail('标题不能为空');current.title=title;}if(b.author!==undefined){if(b.author!==null&&typeof b.author!=='string')throw fail('作者无效');current.author=text(b.author,60)||null;current.creator=current.author;}if(b.contentType!==undefined&&['painting','photo','illustration'].includes(b.contentType))current.contentType=b.contentType;if(Array.isArray(b.subjects))current.subjects=b.subjects.slice(0,12).map(x=>text(x,30)).filter(Boolean);if(Array.isArray(b.tags))current.tags=b.tags.slice(0,30).map(x=>text(x,30)).filter(Boolean);if(Array.isArray(b.people))current.people=b.people.slice(0,20).map(x=>text(x,60)).filter(Boolean);if(b.location!==undefined)current.location=text(b.location,80)||null;if(b.capturedAt!==undefined)current.capturedAt=text(b.capturedAt,20)||null;if(b.collectionIds!==undefined||b.categoryId!==undefined){const collectionIds=photoCollections(s,b);current.categoryId=collectionIds[0];current.collectionIds=collectionIds;}if(b.enabled!==undefined){if(typeof b.enabled!=='boolean')throw fail('启用状态无效');current.enabled=b.enabled;}if(changed){Object.assign(current,settings,{renderVersion:version,displaySha256:hash(result.bin),renderer:RENDERER});}store.event(s,'photo','更新照片：'+current.title);});return response(res,200,state());
     }
     if(!variant&&m==='DELETE'){store.write(s=>{s.photos=s.photos.filter(x=>x.id!==photo.id);store.event(s,'photo','删除照片：'+photo.title);});await fs.rm(folder,{recursive:true,force:true});return response(res,200,state());}
    }
    throw fail('管理接口不存在',404);
   }
   if(p.startsWith('/api/'))throw fail('接口不存在',404);
   if(!['GET','HEAD'].includes(m))throw fail('不支持此方法',405);const publicRoot=path.join(ROOT,'public'),dest=path.resolve(publicRoot,p==='/'?'index.html':decodeURIComponent(p.slice(1)));if(!dest.startsWith(publicRoot+path.sep))throw fail('禁止访问',403);const type={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.png':'image/png'}[path.extname(dest)]||'application/octet-stream';return await files(res,dest,type,req);
  }catch(e){if(!res.headersSent)response(res,e.status||(e.code?503:400),{error:e.status?e.message:(e.code?'服务暂时不可用':e.message)});else res.destroy();if(!e.status&&e.code)console.error('Stillframe request error:',e.code);}
 });
 // One background re-render at a time, reporting progress through state().
 let rerendering=null;
 async function rerenderAll(photos,needed,overrides,message){rerendering={total:photos.length,done:0};let changed=0;try{for(const old of photos){try{if(!needed(store.data.photos.find(x=>x.id===old.id)||{renderer:RENDERER}))continue;const folder=path.join(dataDir,'photos',old.id),settings=photoSettings({...old,...overrides(old)}),result=await renderImage(await fs.readFile(path.join(folder,'original.'+old.ext)),settings),version=id();await Promise.all([fs.writeFile(path.join(folder,version+'.bin'),result.bin),fs.writeFile(path.join(folder,version+'.png'),result.preview),fs.writeFile(path.join(folder,version+'.jpg'),result.thumbnail)]);store.write(s=>{const current=s.photos.find(x=>x.id===old.id);if(!current||!needed(current))return;Object.assign(current,settings,{renderVersion:version,displaySha256:hash(result.bin),renderer:RENDERER});changed++;});}catch(e){console.error('Stillframe re-render failed:',old.id,e.message);}finally{rerendering.done++;}}if(changed)store.write(s=>store.event(s,'photo',message(changed)));}finally{rerendering=null;}return changed;}
 // Photos rendered by an earlier algorithm are re-rendered once. The old "vivid" level was
 // an automatic default of the previous renderer, so it maps to natural.
 const pending=store.data.photos.filter(x=>x.renderer!==RENDERER);
 const colorMigration=pending.length?rerenderAll(pending,x=>x.renderer!==RENDERER,old=>({color:old.color==='standard'?'standard':'natural',chroma:undefined,brightness:undefined,contrast:undefined}),n=>`已用墨水校准算法重新生成 ${n} 张照片的显示数据`):Promise.resolve(0);
 server.requestTimeout=90000;server.headersTimeout=15000;return {server,store,colorMigration,close:()=>store.close()};
}
