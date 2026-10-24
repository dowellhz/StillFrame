import {PNG} from 'pngjs';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
for(const size of [64,72,256]){const data=Buffer.alloc(size*size*4);for(let y=0;y<size;y++)for(let x=0;x<size;x++){const X=x/size*256,Y=y/size*256;let color=[53,91,73];if(X>=57&&X<=199&&Y>=33&&Y<=223&&(X<69||X>187||Y<45||Y>211))color=[234,220,197];if((X-102)**2+(Y-82)**2<14**2)color=[212,185,107];if(Y>=108&&Y<=166&&X>=80&&X<=176&&(Y>=166-(X-82)*1.4||Y>=166-(176-X)*1.6))color=[234,220,197];const i=(y*size+x)*4;data[i]=color[0];data[i+1]=color[1];data[i+2]=color[2];data[i+3]=255;}const png=PNG.sync.write({width:size,height:size,data});const name=size===72?'PACKAGE_ICON.PNG':size===256?'PACKAGE_ICON_256.PNG':null;if(name)fs.writeFileSync(path.join(root,'synology',name),png);fs.writeFileSync(path.join(root,'synology/ui/images',`stillframe_${size}.png`),png);}
