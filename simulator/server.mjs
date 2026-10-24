import http from 'node:http';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const project = path.dirname(root);
const types = { '.html':'text/html; charset=utf-8', '.js':'text/javascript; charset=utf-8', '.css':'text/css; charset=utf-8', '.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.webp':'image/webp', '.svg':'image/svg+xml' };
export async function createSimulator({dataDir = path.join(root,'.data')} = {}) {
  await fs.mkdir(path.join(dataDir,'uploads'),{recursive:true});
  const filename=path.join(dataDir,'state.json');
  let state;
  try { state=JSON.parse(await fs.readFile(filename,'utf8')); }
  catch(e) {
    if(e.code!=='ENOENT') throw e;
    const names=(await fs.readdir(path.join(project,'painting','vango'))).filter(n=>/\.jpe?g$/i.test(n));
    state={ defaultConfig:{interval:3600,category:'all',order:'sequence'}, categories:[{id:'art',name:'绘画',parent:null},{id:'vangogh',name:'梵高',parent:'art'},{id:'people',name:'人物照片',parent:null},{id:'landscape',name:'风景',parent:null}], devices:[], photos:[{id:'sunflowers',name:'向日葵',category:'vangogh',storage:'server',url:'/painting/v2-ae36dd9cc63c5c071cd9611976aff2e9_r.jpg'},...names.map((n,i)=>({id:'sample-'+i,name:'绘画作品 '+(i+1),category:'vangogh',storage:'server',url:'/painting/vango/'+encodeURIComponent(n)}))]};
  }
  let queue=Promise.resolve();
  function persist(){ const snapshot=JSON.stringify(state,null,2); const job=queue.then(async()=>{await fs.writeFile(filename+'.tmp',snapshot);await fs.rename(filename+'.tmp',filename);}); queue=job.catch(()=>{});return job; }
  await persist();
  const send=(res,code,data)=>{res.writeHead(code,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(data));};
  async function body(req){let size=0,chunks=[];for await(const c of req){size+=c.length;if(size>16*1024*1024)throw Object.assign(new Error('上传文件过大，请选择小于 10 MB 的图片'),{status:413});chunks.push(c);}try{return JSON.parse(Buffer.concat(chunks).toString()||'{}');}catch{throw Object.assign(new Error('无效 JSON'),{status:400});}}
  function config(c){if(!Number.isFinite(c.interval)||c.interval<180||c.interval>86400)throw Object.assign(new Error('刷新间隔需在 3 分钟至 24 小时之间'),{status:400});if(c.category!=='all'&&!state.categories.some(x=>x.id===c.category))throw Object.assign(new Error('分类不存在'),{status:400});if(!['sequence','random'].includes(c.order))throw Object.assign(new Error('播放顺序无效'),{status:400});return {interval:c.interval,category:c.category,order:c.order};}
  function categoryIds(id){const ids=new Set([id]);let old;do{old=ids.size;for(const c of state.categories)if(ids.has(c.parent))ids.add(c.id);}while(old!==ids.size);return ids;}
  const server=http.createServer(async(req,res)=>{
    try {
      const u=new URL(req.url,'http://localhost');const p=u.pathname;
      if(p==='/api/state'&&req.method==='GET')return send(res,200,state);
      if(p==='/api/default'&&req.method==='PUT'){state.defaultConfig=config(await body(req));await persist();return send(res,200,state);}
      if(p.startsWith('/api/devices/')&&req.method==='PUT'){
        const d=state.devices.find(d=>d.id===decodeURIComponent(p.slice(13)));if(!d)return send(res,404,{error:'设备尚未注册'});
        const b=await body(req);d.config=b.config===null?null:config(b.config);d.name=String(b.name||d.name).slice(0,60);await persist();return send(res,200,state);
      }
      if(p==='/api/sync'&&req.method==='POST'){
        const b=await body(req);if(typeof b.id!=='string'||!/^[\w-]{1,80}$/.test(b.id))return send(res,400,{error:'设备标识无效'});
        let d=state.devices.find(x=>x.id===b.id);const registered=!d;
        if(!d){d={id:b.id,name:'Stillframe '+b.id.slice(-4),config:null,lastSeen:null,currentPhoto:null};state.devices.push(d);}
        d.lastSeen=new Date().toISOString();const c=d.config||state.defaultConfig;
        const pool=state.photos.filter(x=>x.storage==='server'&&(c.category==='all'||categoryIds(c.category).has(x.category)));
        let photo=null;
        if(pool.length){const previous=pool.findIndex(x=>x.id===b.currentPhoto);const candidates=pool.filter(x=>x.id!==b.currentPhoto);photo=c.order==='random'?(candidates.length?candidates[Math.floor(Math.random()*candidates.length)]:pool[0]):pool[(previous+1)%pool.length];}
        d.currentPhoto=photo?.id||b.currentPhoto||null;await persist();return send(res,200,{registered,source:d.config?'device':'default',config:c,photo});
      }
      if(p==='/api/categories'&&req.method==='POST'){
        const b=await body(req);const name=String(b.name||'').trim().slice(0,60);if(!name)return send(res,400,{error:'请填写分类名称'});
        if(b.parent&&!state.categories.some(x=>x.id===b.parent))return send(res,400,{error:'上级分类不存在'});
        state.categories.push({id:crypto.randomUUID(),name,parent:b.parent||null});await persist();return send(res,200,state);
      }
      if(p.startsWith('/api/categories/')&&req.method==='PUT'){
        const c=state.categories.find(x=>x.id===p.split('/').at(-1));if(!c)return send(res,404,{error:'分类不存在'});const b=await body(req);if(!String(b.name||'').trim())return send(res,400,{error:'请填写名称'});c.name=String(b.name).trim().slice(0,60);await persist();return send(res,200,state);
      }
      if(p.startsWith('/api/categories/')&&req.method==='DELETE'){
        const id=p.split('/').at(-1);if(state.categories.some(x=>x.parent===id)||state.photos.some(x=>x.category===id))return send(res,409,{error:'请先移出照片并删除下级分类'});
        state.categories=state.categories.filter(x=>x.id!==id);for(const c of [state.defaultConfig,...state.devices.map(d=>d.config).filter(Boolean)])if(c.category===id)c.category='all';await persist();return send(res,200,state);
      }
      if(p==='/api/photos'&&req.method==='POST'){
        const b=await body(req);if(!state.categories.some(x=>x.id===b.category))return send(res,400,{error:'请选择分类'});
        const m=/^data:image\/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)$/.exec(b.data||'');if(!m)return send(res,400,{error:'支持 JPG、PNG、WebP 图片'});
        const bytes=Buffer.from(m[2],'base64');if(bytes.length>10*1024*1024)return send(res,413,{error:'图片不能超过 10 MB'});
        const id=crypto.randomUUID(),ext=m[1]==='jpeg'?'jpg':m[1];await fs.writeFile(path.join(dataDir,'uploads',id+'.'+ext),bytes);
        state.photos.push({id,name:String(b.name||'未命名').slice(0,100),category:b.category,storage:b.storage==='sd'?'sd':'server',url:'/uploads/'+id+'.'+ext});await persist();return send(res,201,state);
      }
      if(p.startsWith('/api/photos/')&&req.method==='DELETE'){const id=p.split('/').at(-1);const item=state.photos.find(x=>x.id===id);state.photos=state.photos.filter(x=>x.id!==id);await persist();if(item?.url.startsWith('/uploads/'))await fs.rm(path.join(dataDir,'uploads',path.basename(item.url)),{force:true});return send(res,200,state);}
      if(p==='/api/sd/seed'&&req.method==='POST'){for(const item of state.photos.filter(x=>x.storage==='server').slice(0,4))if(!state.photos.some(x=>x.id==='sd-'+item.id))state.photos.push({...item,id:'sd-'+item.id,storage:'sd'});await persist();return send(res,200,state);}
      if(p.startsWith('/api/'))return send(res,404,{error:'接口不存在'});
      if(!['GET','HEAD'].includes(req.method))return send(res,405,{error:'不支持此方法'});
      let base,rel;
      if(p.startsWith('/painting/')){base=path.join(project,'painting');rel=decodeURIComponent(p.slice(10));}
      else if(p.startsWith('/uploads/')){base=path.join(dataDir,'uploads');rel=decodeURIComponent(p.slice(9));}
      else{base=path.join(root,'public');rel=p==='/'?'index.html':decodeURIComponent(p.slice(1));}
      const dest=path.resolve(base,rel);if(!dest.startsWith(base+path.sep))return send(res,403,{error:'禁止访问'});
      try{const data=await fs.readFile(dest);res.writeHead(200,{'Content-Type':types[path.extname(dest)]||'application/octet-stream','Cache-Control':'no-cache'});res.end(req.method==='HEAD'?undefined:data);}catch(e){if(e.code==='ENOENT')return send(res,404,{error:'文件不存在'});throw e;}
    }catch(e){send(res,e.status||500,{error:e.status?e.message:'本地服务错误'});console.error(e.message);}
  });
  return server;
}
if(process.argv[1]===fileURLToPath(import.meta.url)){const server=await createSimulator();const port=Number(process.env.PORT||4173);server.listen(port,'127.0.0.1',()=>console.log(`Stillframe 模拟器已启动：http://127.0.0.1:${port}`));}
