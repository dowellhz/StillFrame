const $=s=>document.querySelector(s), $$=s=>[...document.querySelectorAll(s)];
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const KEY='stillframe-device-v1';
const asset=url=>globalThis.__STILLFRAME_ASSETS__?.[url]||url;
function fresh(){return {id:'sf-'+crypto.randomUUID(),configured:false,mode:'server',ssid:'',wifiPassword:'',server:'',credential:'',apPassword:'12345678',sd:false,network:true,power:true,config:{interval:3600,category:'all',order:'sequence'},source:'—',photo:null,nextAt:null,firmware:'1.0',slot:'A'};}
let device;try{device=JSON.parse(localStorage.getItem(KEY))||fresh();}catch{device=fresh();}
let model,storage='server',view='device',busy=false,timeOffset=0,toastTimer,drawRevision=0;
const canvas=$('#screen'),ctx=canvas.getContext('2d'),baseCanvas=document.createElement('canvas');baseCanvas.width=1200;baseCanvas.height=1600;const bctx=baseCanvas.getContext('2d');
const images=new Map();
const now=()=>Date.now()+timeOffset;
const save=()=>localStorage.setItem(KEY,JSON.stringify(device));
async function api(url,method='GET',data){const res=await fetch(url,{method,headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});const b=await res.json();if(!res.ok)throw new Error(b.error||'请求失败');return b;}
function toast(t){$('#toast').textContent=t;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,4200);}
function log(t,error=false){const row=document.createElement('div');row.className='log-row'+(error?' error':'');row.innerHTML=`<time>${new Date(now()).toLocaleTimeString('zh-CN',{hour12:false})}</time><span>${esc(t)}</span>`;$('#logs').prepend(row);while($('#logs').children.length>80)$('#logs').lastChild.remove();}
function fail(e){toast(e.message);log(e.message,true);}
function catName(id){return id==='all'?'全部分类':model.categories.find(c=>c.id===id)?.name||'未分类';}
function descendants(id){const set=new Set([id]);let size;do{size=set.size;for(const c of model.categories)if(set.has(c.parent))set.add(c.id);}while(set.size!==size);return set;}
function catOptions(all=true){let out=all?'<option value="all">全部分类</option>':'';function branch(parent,level){for(const c of model.categories.filter(c=>c.parent===parent)){out+=`<option value="${esc(c.id)}">${'　'.repeat(level)}${esc(c.name)}</option>`;branch(c.id,level+1);}}branch(null,0);return out;}
function intervalOptions(){return [[180,'3 分钟'],[300,'5 分钟'],[900,'15 分钟'],[1800,'30 分钟'],[3600,'1 小时'],[10800,'3 小时'],[21600,'6 小时'],[43200,'12 小时'],[86400,'24 小时']].map(([v,t])=>`<option value="${v}">${t}</option>`).join('');}
function intervalText(v){return v>=3600?`${v/3600} 小时`:`${v/60} 分钟`;}
function remaining(){if(!device.power)return '电源已关闭';if(!device.configured)return '等待配网';if(device.mode==='local'&&!device.sd)return '等待插入 SD 卡';const s=Math.max(0,Math.ceil((device.nextAt-now())/1000));return s>=3600?`${Math.floor(s/3600)} 小时 ${Math.floor(s%3600/60)} 分钟`:`${Math.floor(s/60)} 分 ${s%60} 秒`;}
function renderDevice(){
 $('#device-short').textContent=device.id.slice(-4);$('#device-id').textContent=device.id;$('#mode-badge').textContent=device.configured?(device.mode==='local'?'本地 SD 卡':'群晖服务器'):'未配置';
 $('#wifi-status').textContent=!device.power?'已断电':!device.configured?'热点：Stillframe':device.mode==='local'?(device.network?'本地管理热点':'本地播放 · 网络关闭'):device.network?device.ssid:'网络已断开';
 $('#config-source').textContent=device.source;$('#interval-value').textContent=device.configured?intervalText(device.config.interval):'—';$('#next-update').textContent=remaining();$('#current-name').textContent=device.photo?.name||'开机引导';
 $('#sd').checked=device.sd;$('#network').checked=device.network;$('#power').checked=device.power;$('#power-tag').hidden=device.power;
 $('#sd-detail').textContent=device.sd?'已插入 · 可以选择本地模式':'未插入 · 仅支持服务器模式';
 $('#configure').textContent=device.configured?'设备设置':'配置设备';$('#refresh').disabled=busy||!device.configured||!device.power;$('#advance').disabled=busy||!device.configured||!device.power;$('#configure').disabled=!device.power||busy;$('#reset').disabled=busy||!device.power;$('#upgrade').disabled=busy||!device.power||!device.configured||!device.network;
 $('#screen-status').textContent=!device.power?'画面保留':busy?'正在更新':!device.configured?'等待配网':device.mode==='local'&&!device.sd?'SD 卡已移除':device.mode==='server'&&!device.network?'离线保留画面':'正常显示';
 $('#firmware').textContent=`运行版本 v${device.firmware} · 分区 ${device.slot}`;
}
function renderLibrary(){
 const previous=$('#library-category').value;$('#library-category').innerHTML=catOptions();$('#library-category').value=model.categories.some(x=>x.id===previous)?previous:'all';
 const selected=$('#library-category').value;const photos=model.photos.filter(p=>p.storage===storage&&(selected==='all'||descendants(selected).has(p.category)));
 const unavailable=storage==='sd'&&!device.sd;$('#sd-library-note').hidden=!unavailable;$('#upload').disabled=unavailable;$('#seed-sd').hidden=storage!=='sd';$('#seed-sd').disabled=unavailable;
 $('#category-chips').innerHTML=model.categories.map(c=>`<span class="category-chip">${esc(c.parent?catName(c.parent)+' / ':'')}${esc(c.name)} <button data-rename="${esc(c.id)}" title="重命名">✎</button><button data-delete-category="${esc(c.id)}" title="删除分类">×</button></span>`).join('');
 $('#photo-grid').innerHTML=unavailable?'<div class="empty">插入模拟 MicroSD 卡后<br>即可管理本地相册</div>':photos.length?photos.map(p=>`<article class="photo-card"><img src="${esc(asset(p.url))}" alt="${esc(p.name)}" loading="lazy"><div class="photo-info"><strong>${esc(p.name)}</strong><div class="photo-meta"><span>${esc(catName(p.category))}</span><button data-delete-photo="${esc(p.id)}">删除</button></div></div></article>`).join(''):'<div class="empty">这里还没有照片<br>上传一张照片，或切换分类查看</div>';
 $('#library-footer').textContent=`${photos.length} 张照片 · ${storage==='sd'?'模拟 SD 卡':'服务器相册'} · 约 ${(photos.length*960000/1024/1024).toFixed(1)} MiB 显示数据（估算，非磁盘实占）`;
}
function renderServer(){
 const f=$('#default-form');f.elements.category.innerHTML=catOptions();f.elements.interval.innerHTML=intervalOptions();for(const [k,v]of Object.entries(model.defaultConfig))f.elements[k].value=v;
 $('#device-list').innerHTML=model.devices.length?model.devices.map(d=>{const c=d.config||model.defaultConfig;return `<div class="server-device"><h4>${esc(d.name)} ${d.id===device.id?'<span class="tag">当前设备</span>':''}</h4><div class="mono muted">${esc(d.id)}</div><p class="help">上次请求：${new Date(d.lastSeen).toLocaleString('zh-CN')} · ${d.config?'专属配置':'default 配置'}</p><form data-device="${esc(d.id)}"><label class="inherit"><input name="inherit" type="checkbox" ${d.config?'':'checked'}>使用 default 配置</label><label>显示分类<select name="category">${catOptions()}</select></label><label>刷新间隔<select name="interval">${intervalOptions()}</select></label><label>播放顺序<select name="order"><option value="sequence">顺序播放</option><option value="random">随机播放</option></select></label><button class="button primary">保存设备配置</button></form></div>`;}).join(''):'<div class="empty">设备完成首次配网并请求服务器后<br>自动出现在这里</div>';
 $$('#device-list form').forEach(f=>{const d=model.devices.find(d=>d.id===f.dataset.device);const c=d.config||model.defaultConfig;for(const[k,v]of Object.entries(c))f.elements[k].value=v;const toggle=()=>['category','interval','order'].forEach(k=>f.elements[k].disabled=f.elements.inherit.checked);toggle();f.elements.inherit.onchange=toggle;f.onsubmit=async e=>{e.preventDefault();try{model=await api('/api/devices/'+encodeURIComponent(d.id),'PUT',{name:d.name,config:f.elements.inherit.checked?null:{category:f.elements.category.value,interval:Number(f.elements.interval.value),order:f.elements.order.value}});renderServer();toast('已保存，下次设备请求时生效');log('服务器已更新设备专属配置；等待下次同步');}catch(e){fail(e);}};});
}
function render(){renderDevice();if(view==='library')renderLibrary();if(view==='server')renderServer();}
async function loadImage(url){if(images.has(url))return images.get(url);const promise=new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(new Error('照片加载失败'));i.src=asset(url);});images.set(url,promise);try{return await promise;}catch(e){images.delete(url);throw e;}}
function cover(c,img,x,y,w,h){const scale=Math.max(w/img.width,h/img.height),sw=w/scale,sh=h/scale;c.drawImage(img,(img.width-sw)/2,(img.height-sh)/2,sw,sh,x,y,w,h);}
async function paint(){const revision=++drawRevision;const welcome=!device.configured||!device.photo;const img=await loadImage(welcome?'/painting/v2-ae36dd9cc63c5c071cd9611976aff2e9_r.jpg':device.photo.url);if(revision!==drawRevision)return;bctx.fillStyle='#fff';bctx.fillRect(0,0,1200,1600);
 if(welcome){
  cover(bctx,img,0,0,1200,1010);
  bctx.fillStyle='#111';bctx.textBaseline='alphabetic';bctx.font='48px Georgia';bctx.fillText('Stillframe',66,1075);bctx.strokeStyle='#555';bctx.lineWidth=1;bctx.beginPath();bctx.moveTo(66,1100);bctx.lineTo(1134,1100);bctx.stroke();
  bctx.font='50px "Songti SC",serif';bctx.fillText('让喜欢的画，留在眼前',66,1170);
  bctx.font='30px "PingFang SC",sans-serif';bctx.fillText(device.configured?'等待第一张照片':'首次使用 · 两步完成设置',66,1230);
  bctx.font='31px "PingFang SC",sans-serif';
  if(!device.configured){bctx.fillText('1  打开手机 Wi-Fi，连接 Stillframe',66,1282);bctx.fillText('    密码：'+device.apPassword,66,1328);bctx.fillText('2  连接后，扫描右侧二维码',66,1381);bctx.font='29px "PingFang SC",sans-serif';bctx.fillText('    配置网络、相册或本地模式',66,1427);}
  else{bctx.fillText('配置已保存，等待相册中的照片。',66,1300);bctx.fillText('请检查分类、网络或 SD 卡。',66,1350);}
  bctx.font='27px "PingFang SC",sans-serif';bctx.fillText('也可访问 http://192.168.4.1',66,1480);
  bctx.font='26px "PingFang SC",sans-serif';bctx.fillText('如提示无互联网，请选择保持连接。',66,1530);
  try{const qr=await loadImage('/assets/setup-qr.png');if(revision!==drawRevision)return;bctx.imageSmoothingEnabled=false;bctx.drawImage(qr,914,1255,220,220);bctx.imageSmoothingEnabled=true;}catch{}
 }else cover(bctx,img,0,0,1200,1600);
 applyPreview();
}
function applyPreview(){ctx.drawImage(baseCanvas,0,0);if(!$('#six-color').checked)return;const image=ctx.getImageData(0,0,1200,1600),a=image.data;const palette=[[20,20,20],[240,240,225],[236,205,30],[180,42,34],[37,64,139],[50,111,61]];const bayer=[0,8,2,10,12,4,14,6,3,11,1,9,15,7,13,5];for(let y=0;y<1600;y++)for(let x=0;x<1200;x++){const i=(y*1200+x)*4;if(a[i]>245&&a[i+1]>245&&a[i+2]>245)continue;const d=(bayer[(y%4)*4+x%4]-7.5)*4;let best=0,dist=Infinity;for(let j=0;j<palette.length;j++){const p=palette[j],v=(a[i]+d-p[0])**2+(a[i+1]+d-p[1])**2+(a[i+2]+d-p[2])**2;if(v<dist){dist=v;best=j;}}a[i]=palette[best][0];a[i+1]=palette[best][1];a[i+2]=palette[best][2];}ctx.putImageData(image,0,0);}
async function refresh(){if(busy||!device.power||!device.configured)return;if(device.mode==='local'&&!device.sd){log('SD 卡已移除，保留当前照片，等待重新插入',true);toast('请插入 MicroSD 卡');renderDevice();return;}busy=true;renderDevice();
 try{
  let result;
  if(device.mode==='server'){
   if(!device.network)throw new Error('Wi-Fi 已断开：保留当前画面，1 分钟后重试');
   result=await api('/api/sync','POST',{id:device.id,currentPhoto:device.photo?.id});
   if(result.registered)log('首次请求：服务器自动建档，返回 default 配置');
   log(`收到${result.source==='default'?' default':'设备专属'}配置：${catName(result.config.category)}，每 ${intervalText(result.config.interval)}更新`);
   model=await api('/api/state');
  }else{
   const pool=model.photos.filter(p=>p.storage==='sd'&&(device.config.category==='all'||descendants(device.config.category).has(p.category)));const prev=pool.findIndex(p=>p.id===device.photo?.id);const others=pool.filter(p=>p.id!==device.photo?.id);
   const photo=device.config.order==='random'?(others.length?others[Math.floor(Math.random()*others.length)]:pool[0]):pool[(prev+1)%pool.length];result={config:device.config,source:'local',photo};log('从模拟 SD 卡读取照片和本地播放配置');
  }
  if(!device.power)return;
  device.config=result.config;device.source=result.source==='default'?'default 配置':result.source==='local'?'设备本地配置':'设备专属配置';
  if(result.photo){await loadImage(result.photo.url);if(!device.power)return;device.photo=result.photo;$('#frame').classList.add('refreshing');await paint();await new Promise(r=>setTimeout(r,1000));$('#frame').classList.remove('refreshing');log(`显示「${device.photo.name}」；模拟驱动关电，画面保留`);}
  else{log('所选分类没有照片，保留当前画面');await paint();}
  device.nextAt=now()+device.config.interval*1000;save();
 }catch(e){device.nextAt=now()+60000;save();fail(e);}finally{busy=false;render();}
}
function openSetup(){const f=$('#setup-form');f.elements.mode.value=device.mode;for(const k of ['ssid','wifiPassword','server','credential','apPassword'])f.elements[k].value=device[k]||'';f.elements.localCategory.innerHTML=catOptions();f.elements.localInterval.innerHTML=intervalOptions();f.elements.localCategory.value=model.categories.some(x=>x.id===device.config.category)?device.config.category:'all';f.elements.localInterval.value=device.config.interval;f.elements.localOrder.value=device.config.order;$('option[value="local"]').disabled=!device.sd;$('#setup-error').textContent='';toggleSetup();$('#setup-dialog').showModal();}
function toggleSetup(){const local=$('#setup-mode').value==='local';$('#server-fields').hidden=local;$('#local-settings').hidden=!local;}
function setView(name){view=['device','library','server'].includes(name)?name:'device';$$('.view').forEach(el=>el.hidden=el.id!==view+'-view');$$('nav button').forEach(el=>el.classList.toggle('active',el.dataset.view===view));$('#page-title').textContent={device:'设备模拟器',library:'相册管理',server:'服务器配置'}[view];render();}
$$('nav button').forEach(el=>el.onclick=()=>{location.hash=el.dataset.view;});window.onhashchange=()=>{if(location.hash==='#setup'){setView('device');openSetup();}else setView(location.hash.slice(1));};
canvas.onclick=()=>{if(!device.configured&&device.power)openSetup();};
$('#configure').onclick=openSetup;$('#close-setup').onclick=()=>$('#setup-dialog').close();$('#setup-mode').onchange=toggleSetup;
$('#setup-form').onsubmit=async e=>{e.preventDefault();const f=e.target;const v=Object.fromEntries(new FormData(f));try{
 if(!/^[\x20-\x7e]{8,63}$/.test(v.apPassword))throw new Error('热点密码需为 8～63 位 ASCII 字符');
 if(v.mode==='local'&&!device.sd)throw new Error('请先插入模拟 SD 卡');
 if(v.mode==='server'){if(!v.ssid.trim())throw new Error('请填写 Wi-Fi 名称');const url=new URL(v.server);if(!['http:','https:'].includes(url.protocol))throw new Error('服务器地址需以 http:// 或 https:// 开头');if(!v.credential.trim())throw new Error('请填写设备接入凭证');if(!device.network)throw new Error('模拟网络已关闭，请先恢复网络');}
 Object.assign(device,{mode:v.mode,ssid:v.ssid,wifiPassword:v.wifiPassword,server:v.server,credential:v.credential,apPassword:v.apPassword,configured:true});
 if(v.mode==='local')device.config={category:v.localCategory,interval:Number(v.localInterval),order:v.localOrder};
 device.photo=null;device.nextAt=now();save();$('#setup-dialog').close();log(`配置已保存：${v.mode==='local'?'本地 SD 卡模式':'服务器模式'}；密码不再出现在屏幕引导中`);toast('配置已保存');await paint();await refresh();
 }catch(e){$('#setup-error').textContent=e.message==='Invalid URL'?'请输入完整服务器地址，例如 http://192.168.1.100:8080':e.message;}};
$('#refresh').onclick=refresh;$('#advance').onclick=()=>{if(!device.power||!device.configured)return;timeOffset+=Math.max(0,device.nextAt-now())+1000;log('模拟时钟快进至下一次更新时间');refresh();};
$('#sd').onchange=e=>{device.sd=e.target.checked;save();log(device.sd?'MicroSD 卡已插入，可在设备设置中选择本地模式':'MicroSD 卡已移除；不会自动切换运行模式');render();};
$('#network').onchange=e=>{device.network=e.target.checked;save();log(device.network?'模拟网络已恢复':'模拟网络已断开');renderDevice();};
$('#power').onchange=async e=>{device.power=e.target.checked;save();log(device.power?'设备重新通电，恢复本地配置与固定身份':'设备断电，屏幕保留上一画面');renderDevice();if(device.power){if(device.configured)await refresh();else await paint();}};
$('#reset').onclick=async()=>{if(!confirm('清除本机连接配置并重新配网？服务器照片和设备档案会保留，设备身份不变。'))return;const {id,sd,power,network}=device;device={...fresh(),id,sd,power,network};save();await paint();render();log('已清除本机配置，保留设备身份，进入首次配网');};
$('#six-color').onchange=applyPreview;$('#mat').onchange=e=>$('#occlusion').hidden=!e.target.checked;
$('#export').onclick=()=>{const a=document.createElement('a');a.download='Stillframe-screen-1200x1600.png';a.href=canvas.toDataURL('image/png');a.click();toast('已导出原生分辨率屏幕，不含画框和遮边层');};$('#clear-log').onclick=()=>$('#logs').replaceChildren();
$$('[data-storage]').forEach(b=>b.onclick=()=>{storage=b.dataset.storage;$$('[data-storage]').forEach(x=>x.classList.toggle('active',x===b));renderLibrary();});$('#library-category').onchange=renderLibrary;
$('#default-form').onsubmit=async e=>{e.preventDefault();const f=e.target;try{model=await api('/api/default','PUT',{category:f.elements.category.value,interval:Number(f.elements.interval.value),order:f.elements.order.value});renderServer();toast('默认配置已保存，下次请求时生效');log('服务器 default 配置已更新');}catch(e){fail(e);}};
$('#add-category').onclick=()=>{const f=$('#category-form');f.reset();f.elements.parent.innerHTML='<option value="">无，作为一级分类</option>'+catOptions(false);$('#category-dialog').showModal();};$('#cancel-category').onclick=()=>$('#category-dialog').close();
$('#category-form').onsubmit=async e=>{e.preventDefault();try{model=await api('/api/categories','POST',Object.fromEntries(new FormData(e.target)));$('#category-dialog').close();renderLibrary();toast('分类已创建');}catch(e){fail(e);}};
$('#category-chips').onclick=async e=>{const b=e.target.closest('button');if(!b)return;try{if(b.dataset.rename){const c=model.categories.find(c=>c.id===b.dataset.rename);const name=prompt('分类新名称',c.name);if(name===null)return;model=await api('/api/categories/'+c.id,'PUT',{name});}else if(b.dataset.deleteCategory){if(!confirm('删除这个分类？有下级分类或照片时不能删除。'))return;model=await api('/api/categories/'+b.dataset.deleteCategory,'DELETE');}renderLibrary();}catch(e){fail(e);}};
$('#photo-grid').onclick=async e=>{const b=e.target.closest('[data-delete-photo]');if(!b)return;if(!confirm('删除这张照片？'))return;try{model=await api('/api/photos/'+b.dataset.deletePhoto,'DELETE');renderLibrary();toast('照片已删除，当前屏幕保留至下次更新');}catch(e){fail(e);}};
$('#seed-sd').onclick=async()=>{try{model=await api('/api/sd/seed','POST',{});renderLibrary();toast('已复制示例作品到模拟 SD 卡');}catch(e){fail(e);}};
$('#upload').onchange=async e=>{const input=e.target;try{const category=$('#library-category').value;if(category==='all')throw new Error('请先选择一个上传目标分类');for(const file of input.files){if(file.size>10*1024*1024)throw new Error('每张图片不能超过 10 MB');if(!['image/jpeg','image/png','image/webp'].includes(file.type))throw new Error('支持 JPG、PNG、WebP');const data=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsDataURL(file);});await loadImage(data);model=await api('/api/photos','POST',{name:file.name,category,storage,data});}renderLibrary();toast('照片上传完成');}catch(e){fail(e);}finally{input.value='';}};
$('#upgrade').onclick=async()=>{if(busy||!device.power||!device.network||!device.configured)return;busy=true;renderDevice();const kind=$('#upgrade-case').value,old=device.slot;log(`OTA 演示：向备用分区 ${old==='A'?'B':'A'} 下载新固件`);await new Promise(r=>setTimeout(r,700));if(!device.power||!device.network||kind==='interrupted'){log('下载中断：保持旧版本及启动分区',true);}else{log('文件校验通过，尝试启动新分区');await new Promise(r=>setTimeout(r,700));if(!device.power||kind==='bad'){log('新版本未通过自检：模拟看门狗重启，回滚旧分区 '+old,true);}else{device.slot=old==='A'?'B':'A';device.firmware=(Number(device.firmware)+0.1).toFixed(1);log('新版本自检通过，标记有效；保留旧固件');}}save();busy=false;renderDevice();};
async function boot(){model=await api('/api/state');setView(location.hash.slice(1));save();await paint();log(device.configured?'读取已保存配置，设备身份保持不变':'首次启动：开启 Stillframe 配网热点（模拟）');if(location.hash==='#setup')openSetup();if(device.configured&&device.power)await refresh();setInterval(()=>{renderDevice();if(!busy&&device.power&&device.configured&&device.nextAt&&now()>=device.nextAt&&(device.mode!=='local'||device.sd))refresh();},1000);}
boot().catch(e=>{fail(e);$('#screen-status').textContent='服务连接失败';});
