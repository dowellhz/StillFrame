// The standalone build preserves the API contract in browser storage.
// The Node edition uses real HTTP requests and filesystem persistence instead.
(() => {
  const key='stillframe-offline-server-v1';
  const seed=globalThis.__STILLFRAME_SEED__;
  let state;
  try{state=JSON.parse(localStorage.getItem(key))||structuredClone(seed);}catch{state=structuredClone(seed);}
  const clone=x=>structuredClone(x);
  const ids=id=>{const set=new Set([id]);let old;do{old=set.size;for(const c of state.categories)if(set.has(c.parent))set.add(c.id);}while(old!==set.size);return set;};
  const validate=c=>{if(!Number.isFinite(c.interval)||c.interval<180||c.interval>86400)throw new Error('刷新间隔需在 3 分钟至 24 小时之间');if(c.category!=='all'&&!state.categories.some(x=>x.id===c.category))throw new Error('分类不存在');if(!['sequence','random'].includes(c.order))throw new Error('播放顺序无效');return {interval:c.interval,category:c.category,order:c.order};};
  globalThis.fetch=async(url,options={})=>{
    let status=200,value;
    try{
      const method=options.method||'GET',b=JSON.parse(options.body||'{}');
      if(url==='/api/state')value=state;
      else if(url==='/api/default'&&method==='PUT'){state.defaultConfig=validate(b);value=state;}
      else if(url.startsWith('/api/devices/')&&method==='PUT'){const d=state.devices.find(x=>x.id===decodeURIComponent(url.slice(13)));if(!d)throw new Error('设备尚未注册');d.config=b.config===null?null:validate(b.config);d.name=String(b.name||d.name).slice(0,60);value=state;}
      else if(url==='/api/sync'&&method==='POST'){
        if(typeof b.id!=='string'||!/^[\w-]{1,80}$/.test(b.id))throw new Error('设备标识无效');
        let d=state.devices.find(x=>x.id===b.id);const registered=!d;
        if(!d){d={id:b.id,name:'Stillframe '+b.id.slice(-4),config:null,lastSeen:null,currentPhoto:null};state.devices.push(d);}
        d.lastSeen=new Date().toISOString();const c=d.config||state.defaultConfig;
        const pool=state.photos.filter(x=>x.storage==='server'&&(c.category==='all'||ids(c.category).has(x.category)));let photo=null;
        if(pool.length){const previous=pool.findIndex(x=>x.id===b.currentPhoto),others=pool.filter(x=>x.id!==b.currentPhoto);photo=c.order==='random'?(others.length?others[Math.floor(Math.random()*others.length)]:pool[0]):pool[(previous+1)%pool.length];}
        d.currentPhoto=photo?.id||b.currentPhoto||null;value={registered,source:d.config?'device':'default',config:c,photo};
      }
      else if(url==='/api/categories'&&method==='POST'){const name=String(b.name||'').trim().slice(0,60);if(!name)throw new Error('请填写分类名称');if(b.parent&&!state.categories.some(c=>c.id===b.parent))throw new Error('上级分类不存在');state.categories.push({id:crypto.randomUUID(),name,parent:b.parent||null});value=state;}
      else if(url.startsWith('/api/categories/')&&method==='PUT'){const c=state.categories.find(x=>x.id===url.split('/').at(-1));if(!c)throw new Error('分类不存在');if(!String(b.name||'').trim())throw new Error('请填写名称');c.name=String(b.name).trim().slice(0,60);value=state;}
      else if(url.startsWith('/api/categories/')&&method==='DELETE'){const id=url.split('/').at(-1);if(state.categories.some(x=>x.parent===id)||state.photos.some(x=>x.category===id))throw new Error('请先移出照片并删除下级分类');state.categories=state.categories.filter(x=>x.id!==id);for(const c of [state.defaultConfig,...state.devices.map(x=>x.config).filter(Boolean)])if(c.category===id)c.category='all';value=state;}
      else if(url==='/api/photos'&&method==='POST'){if(!state.categories.some(c=>c.id===b.category))throw new Error('请选择分类');if(!/^data:image\/(jpeg|png|webp);base64,[A-Za-z0-9+/=]+$/.test(b.data||''))throw new Error('图片格式无效');if(b.data.length>14*1024*1024)throw new Error('图片不能超过 10 MB');state.photos.push({id:crypto.randomUUID(),name:String(b.name||'未命名').slice(0,100),category:b.category,storage:b.storage==='sd'?'sd':'server',url:b.data});value=state;status=201;}
      else if(url.startsWith('/api/photos/')&&method==='DELETE'){state.photos=state.photos.filter(x=>x.id!==url.split('/').at(-1));value=state;}
      else if(url==='/api/sd/seed'&&method==='POST'){for(const item of state.photos.filter(x=>x.storage==='server').slice(0,4))if(!state.photos.some(x=>x.id==='sd-'+item.id))state.photos.push({...item,id:'sd-'+item.id,storage:'sd'});value=state;}
      else throw new Error('接口不存在');
      if(method!=='GET')localStorage.setItem(key,JSON.stringify(state));
    }catch(e){status=400;value={error:e.name==='QuotaExceededError'?'离线存储空间不足，请删除部分上传照片，或使用 Node 服务版':e.message};
      try{state=JSON.parse(localStorage.getItem(key))||clone(seed);}catch{state=clone(seed);}
    }
    const snapshot=clone(value);return {ok:status>=200&&status<300,status,json:async()=>snapshot};
  };
})();
