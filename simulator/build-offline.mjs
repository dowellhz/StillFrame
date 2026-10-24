import {promises as fs} from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {fileURLToPath} from 'node:url';
import {Readable,Writable} from 'node:stream';
import {createSimulator} from './server.mjs';
const root=path.dirname(fileURLToPath(import.meta.url));
const tmp=await fs.mkdtemp(path.join(os.tmpdir(),'stillframe-build-'));
try{
 const server=await createSimulator({dataDir:tmp});
 const seed=await new Promise(resolve=>{const req=Readable.from([]);req.url='/api/state';req.method='GET';let chunks=[];const res=new Writable({write(c,e,cb){chunks.push(c);cb();}});res.writeHead=()=>res;res.on('finish',()=>resolve(JSON.parse(Buffer.concat(chunks))));server.emit('request',req,res);});
 const assets={};
 for(const url of [...seed.photos.map(p=>p.url),'/assets/setup-qr.png']){
  const dest=url.startsWith('/painting/')?path.join(root,'..',decodeURIComponent(url.slice(1))):path.join(root,'public',url.slice(1));
  const buf=await fs.readFile(dest);assets[url]=`data:image/${url.endsWith('.png')?'png':'jpeg'};base64,${buf.toString('base64')}`;
 }
 const [html,css,js,adapter]=await Promise.all(['public/index.html','public/style.css','public/app.js','offline-adapter.js'].map(x=>fs.readFile(path.join(root,x),'utf8')));
 const safe=o=>JSON.stringify(o).replaceAll('<','\\u003c');
 const output=html.replace('<link rel="stylesheet" href="/style.css">',`<style>${css}</style>`).replace('<script type="module" src="/app.js"></script>',()=>`<script>globalThis.__STILLFRAME_ASSETS__=${safe(assets)};globalThis.__STILLFRAME_SEED__=${safe(seed)};\n${adapter}</script><script type="module">${js}</script>`).replace('本地服务</span>','离线演示</span>');
 await fs.writeFile(path.join(root,'Stillframe模拟器.html'),output);console.log('离线入口已生成：Stillframe模拟器.html');
}finally{await fs.rm(tmp,{recursive:true,force:true});}
