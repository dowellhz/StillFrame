import jpeg from 'jpeg-js';
import {PNG} from 'pngjs';
export const WIDTH=1200,HEIGHT=1600;
export function decode(bytes){
 let image,ext;
 if(bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))){if(bytes.length<24)throw new Error('PNG 文件不完整');const w=bytes.readUInt32BE(16),h=bytes.readUInt32BE(20);if(w<1||h<1||w*h>24000000)throw new Error('图片最多支持 2400 万像素');image=PNG.sync.read(bytes,{checkCRC:true});ext='png';}
 else if(bytes[0]===255&&bytes[1]===216){image=jpeg.decode(bytes,{useTArray:true,maxResolutionInMP:24,maxMemoryUsageInMB:256});ext='jpg';}
 else throw new Error('仅支持有效的 JPG 和 PNG 图片');
 if(!image.width||!image.height||image.width*image.height>24000000)throw new Error('图片尺寸无效');return {...image,ext};
}
export function resize(image,w=WIDTH,h=HEIGHT,fit='cover',rotation=0,cropX=0,cropY=0,cropW=1,cropH=1){
 const out=Buffer.alloc(w*h*4,255),swap=rotation===90||rotation===270,sw=swap?image.height:image.width,sh=swap?image.width:image.height;
 const useCrop=fit==='cover',left=useCrop?cropX*sw:0,top=useCrop?cropY*sh:0,cw=useCrop?cropW*sw:sw,ch=useCrop?cropH*sh:sh,scale=fit==='cover'?Math.max(w/cw,h/ch):Math.min(w/cw,h/ch),dw=cw*scale,dh=ch*scale,dx=(w-dw)/2,dy=(h-dh)/2;
 for(let y=0;y<h;y++)for(let x=0;x<w;x++){const rx=left+(x+.5-dx)/scale-.5,ry=top+(y+.5-dy)/scale-.5;if(rx<left-.5||ry<top-.5||rx>=left+cw-.5||ry>=top+ch-.5)continue;
  let sx,sy;if(rotation===90){sx=ry;sy=image.height-1-rx;}else if(rotation===180){sx=image.width-1-rx;sy=image.height-1-ry;}else if(rotation===270){sx=image.width-1-ry;sy=rx;}else{sx=rx;sy=ry;}
  sx=Math.max(0,Math.min(image.width-1,sx));sy=Math.max(0,Math.min(image.height-1,sy));const x0=Math.floor(sx),y0=Math.floor(sy),x1=Math.min(x0+1,image.width-1),y1=Math.min(y0+1,image.height-1),fx=sx-x0,fy=sy-y0,base=(y*w+x)*4;
  for(let c=0;c<3;c++){const sample=(xx,yy)=>{const i=(yy*image.width+xx)*4,a=image.data[i+3]/255;return image.data[i+c]*a+255*(1-a);};out[base+c]=Math.round((sample(x0,y0)*(1-fx)+sample(x1,y0)*fx)*(1-fy)+(sample(x0,y1)*(1-fx)+sample(x1,y1)*fx)*fy);}
 }return {data:out,width:w,height:h};
}
// GDEP133C02 datasheet section 8.1: typical CIELAB of each ink (spectrophotometer).
// White is only L* 66.5 and yellow nearly as bright, so matching against ideal
// RGB primaries turned pale greens into yellow blotches. Match and diffuse error
// in CIELAB against the measured inks instead, after compressing the source
// lightness into the range the panel can reflect.
const inks=[[0,[12,7,-11]],[1,[66.5,-4,0]],[2,[62,-11,65]],[3,[26.5,41,30]],[5,[34,3.5,-37]],[6,[35,-22,15]]];
export const RENDERER='lab-1';
// Tone presets; natural reproduces the source most faithfully. Photos may override
// any value: chroma scales a*/b*, brightness shifts L*, contrast stretches L* about 50.
export const colorLevels={natural:{chroma:1,brightness:0,contrast:1},standard:{chroma:1.15,brightness:0,contrast:1},vivid:{chroma:1.3,brightness:0,contrast:1.05}};
export const toneLimits={chroma:[.6,1.8],brightness:[-20,20],contrast:[.7,1.5]};
export function toneOf(settings={}){const preset=colorLevels[settings.color]||colorLevels.natural;return {chroma:settings.chroma??preset.chroma,brightness:settings.brightness??preset.brightness,contrast:settings.contrast??preset.contrast};}
const linear=v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4,encode=v=>v<=.0031308?12.92*v:1.055*v**(1/2.4)-.055;
const f=t=>t>216/24389?Math.cbrt(t):(24389/27*t+16)/116,fi=t=>t**3>216/24389?t**3:(116*t-16)/(24389/27);
function lab(r,g,b){const R=linear(r/255),G=linear(g/255),B=linear(b/255),fx=f((.4124*R+.3576*G+.1805*B)/.95047),fy=f(.2126*R+.7152*G+.0722*B),fz=f((.0193*R+.1192*G+.9505*B)/1.08883);return [116*fy-16,500*(fx-fy),200*(fy-fz)];}
function rgb([L,a,b]){const fy=(L+16)/116,X=fi(fy+a/500)*.95047,Y=fi(fy),Z=fi(fy-b/200)*1.08883;return [3.2406*X-1.5372*Y-.4986*Z,-.9689*X+1.8758*Y+.0415*Z,.0557*X-.204*Y+1.057*Z].map(v=>Math.round(255*encode(Math.max(0,Math.min(1,v)))));}
// What each ink looks like, used for the admin preview so it matches the panel.
export const inkRgb=Object.fromEntries(inks.map(([code,value])=>[code,rgb(value)]));
export function sixColor(image,dither=true,{chroma=1,brightness=0,contrast=1}={}){
 const {width:w,height:h}=image,bin=Buffer.alloc(Math.ceil(w*h/2)),preview=Buffer.alloc(w*h*4,255),dark=12,light=66.5;let current=new Float32Array((w+2)*3),next=new Float32Array((w+2)*3);
 for(let y=0;y<h;y++){const reverse=y%2===1,dir=reverse?-1:1;for(let n=0;n<w;n++){const x=reverse?w-1-n:n,i=(y*w+x)*4,e=(x+1)*3,[L,a,b]=lab(image.data[i],image.data[i+1],image.data[i+2]);
   const toned=Math.max(0,Math.min(100,(L-50)*contrast+50+brightness)),want=[dark+toned/100*(light-dark)+current[e],a*chroma+current[e+1],b*chroma+current[e+2]];let best=inks[0],distance=Infinity;
   for(const ink of inks){const p=ink[1],d=2*(want[0]-p[0])**2+(want[1]-p[1])**2+(want[2]-p[2])**2;if(d<distance){distance=d;best=ink;}}
   const pixel=y*w+x;if(pixel%2===0)bin[pixel>>1]|=best[0]<<4;else bin[pixel>>1]|=best[0];preview.set(inkRgb[best[0]],i);preview[i+3]=255;
   // Attenuated, clamped diffusion keeps soft paintings from breaking into colour noise.
   if(dither)for(let c=0;c<3;c++){const err=Math.max(-40,Math.min(40,(want[c]-best[1][c])*.85));current[e+dir*3+c]+=err*7/16;next[e-dir*3+c]+=err*3/16;next[e+c]+=err*5/16;next[e+dir*3+c]+=err/16;}
  }current=next;next=new Float32Array((w+2)*3);
 }return {bin,preview:PNG.sync.write({width:w,height:h,data:preview})};
}
export function processImage(bytes,settings={}){const source=decode(bytes),crop=[settings.cropX??0,settings.cropY??0,settings.cropW??1,settings.cropH??1];const fitted=resize(source,WIDTH,HEIGHT,settings.fit??'cover',settings.rotation||0,...crop);const result=sixColor(fitted,settings.dither!==false,toneOf(settings));const thumb=resize(source,300,360,'cover',settings.rotation||0,...crop);return {...result,thumbnail:jpeg.encode(thumb,80).data,width:source.width,height:source.height,ext:source.ext};}
// Fast half-resolution render for live previews while adjusting tone; never stored.
export function simulateImage(bytes,settings={}){const source=decode(bytes),crop=[settings.cropX??0,settings.cropY??0,settings.cropW??1,settings.cropH??1];const fitted=resize(source,WIDTH/2,HEIGHT/2,settings.fit??'cover',settings.rotation||0,...crop);return {preview:sixColor(fitted,settings.dither!==false,toneOf(settings)).preview};}
