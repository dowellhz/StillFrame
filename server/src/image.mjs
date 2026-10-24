import jpeg from 'jpeg-js';
import {PNG} from 'pngjs';
export const WIDTH=1200,HEIGHT=1600;
export const palette=[{code:0,rgb:[0,0,0]},{code:1,rgb:[255,255,255]},{code:2,rgb:[255,255,0]},{code:3,rgb:[255,0,0]},{code:5,rgb:[0,0,255]},{code:6,rgb:[0,128,0]}];
export function decode(bytes){
 let image,ext;
 if(bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))){if(bytes.length<24)throw new Error('PNG 文件不完整');const w=bytes.readUInt32BE(16),h=bytes.readUInt32BE(20);if(w<1||h<1||w*h>24000000)throw new Error('图片最多支持 2400 万像素');image=PNG.sync.read(bytes,{checkCRC:true});ext='png';}
 else if(bytes[0]===255&&bytes[1]===216){image=jpeg.decode(bytes,{useTArray:true,maxResolutionInMP:24,maxMemoryUsageInMB:256});ext='jpg';}
 else throw new Error('仅支持有效的 JPG 和 PNG 图片');
 if(!image.width||!image.height||image.width*image.height>24000000)throw new Error('图片尺寸无效');return {...image,ext};
}
export function resize(image,w=WIDTH,h=HEIGHT,fit='cover',rotation=0){
 const out=Buffer.alloc(w*h*4,255),swap=rotation===90||rotation===270,sw=swap?image.height:image.width,sh=swap?image.width:image.height;
 const scale=fit==='cover'?Math.max(w/sw,h/sh):Math.min(w/sw,h/sh);const dw=sw*scale,dh=sh*scale,dx=(w-dw)/2,dy=(h-dh)/2;
 for(let y=0;y<h;y++)for(let x=0;x<w;x++){const rx=(x+.5-dx)/scale-.5,ry=(y+.5-dy)/scale-.5;if(rx<-.5||ry<-.5||rx>=sw-.5||ry>=sh-.5)continue;
  let sx,sy;if(rotation===90){sx=ry;sy=image.height-1-rx;}else if(rotation===180){sx=image.width-1-rx;sy=image.height-1-ry;}else if(rotation===270){sx=image.width-1-ry;sy=rx;}else{sx=rx;sy=ry;}
  sx=Math.max(0,Math.min(image.width-1,sx));sy=Math.max(0,Math.min(image.height-1,sy));const x0=Math.floor(sx),y0=Math.floor(sy),x1=Math.min(x0+1,image.width-1),y1=Math.min(y0+1,image.height-1),fx=sx-x0,fy=sy-y0,base=(y*w+x)*4;
  for(let c=0;c<3;c++){const sample=(xx,yy)=>{const i=(yy*image.width+xx)*4,a=image.data[i+3]/255;return image.data[i+c]*a+255*(1-a);};out[base+c]=Math.round((sample(x0,y0)*(1-fx)+sample(x1,y0)*fx)*(1-fy)+(sample(x0,y1)*(1-fx)+sample(x1,y1)*fx)*fy);}
 }return {data:out,width:w,height:h};
}
// Spectra 6 inks are far duller than the ideal palette used for matching, so
// boost saturation and contrast before dithering. Levels were picked from
// simulated ink previews; vivid is the default.
export const colorLevels={natural:{saturation:1,contrast:1},standard:{saturation:1.35,contrast:1.1},vivid:{saturation:1.7,contrast:1.2}};
export function enhance(image,level='vivid'){
 const {saturation,contrast}=colorLevels[level]||colorLevels.vivid;if(saturation===1&&contrast===1)return image;const data=Buffer.from(image.data);
 for(let i=0;i<data.length;i+=4){const l=.299*data[i]+.587*data[i+1]+.114*data[i+2];for(let c=0;c<3;c++)data[i+c]=Math.max(0,Math.min(255,Math.round((l+(data[i+c]-l)*saturation-128)*contrast+128)));}
 return {...image,data};
}
export function sixColor(image,dither=true){
 const {width:w,height:h}=image,bin=Buffer.alloc(Math.ceil(w*h/2)),preview=Buffer.alloc(w*h*4,255);let current=new Float32Array((w+2)*3),next=new Float32Array((w+2)*3);
 for(let y=0;y<h;y++){const reverse=y%2===1,dir=reverse?-1:1;for(let n=0;n<w;n++){const x=reverse?w-1-n:n,i=(y*w+x)*4,e=(x+1)*3;const rgb=[0,1,2].map(c=>Math.max(0,Math.min(255,image.data[i+c]+current[e+c])));let best=palette[0],distance=Infinity;
   for(const p of palette){const d=.3*(rgb[0]-p.rgb[0])**2+.59*(rgb[1]-p.rgb[1])**2+.11*(rgb[2]-p.rgb[2])**2;if(d<distance){distance=d;best=p;}}
   const pixel=y*w+x;if(pixel%2===0)bin[pixel>>1]|=best.code<<4;else bin[pixel>>1]|=best.code;for(let c=0;c<3;c++){preview[i+c]=best.rgb[c];if(dither){const err=rgb[c]-best.rgb[c];current[e+dir*3+c]+=err*7/16;next[e-dir*3+c]+=err*3/16;next[e+c]+=err*5/16;next[e+dir*3+c]+=err/16;}}
  }current=next;next=new Float32Array((w+2)*3);
 }return {bin,preview:PNG.sync.write({width:w,height:h,data:preview})};
}
export function processImage(bytes,settings={}){const source=decode(bytes);const fitted=resize(source,WIDTH,HEIGHT,settings.fit??'cover',settings.rotation||0);const result=sixColor(enhance(fitted,settings.color),settings.dither!==false);const thumb=resize(source,300,360,'cover',settings.rotation||0);return {...result,thumbnail:jpeg.encode(thumb,80).data,width:source.width,height:source.height,ext:source.ext};}
