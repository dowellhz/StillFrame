import fs from 'node:fs';import {PNG} from '../../server/node_modules/pngjs/lib/png.js';import {decode,resize,sixColor} from '../../server/src/image.mjs';
const source=decode(fs.readFileSync('firmware/assets/setup.png')),r=sixColor(source);const preview=PNG.sync.read(r.preview);
// Help text and QR must remain crisp black and white, without color dithering.
for(let y=1020;y<1600;y++)for(let x=0;x<1200;x++){const p=y*1200+x,i=p*4,code=(source.data[i]*.3+source.data[i+1]*.59+source.data[i+2]*.11)<150?0:1;r.bin[p>>1]=p%2?(r.bin[p>>1]&240)|code:(r.bin[p>>1]&15)|(code<<4);preview.data[i]=preview.data[i+1]=preview.data[i+2]=code?255:0;preview.data[i+3]=255;}
fs.writeFileSync('firmware/assets/setup.bin',r.bin);fs.writeFileSync('firmware/assets/setup-preview.png',PNG.sync.write(preview));
const art=sixColor(resize(decode(fs.readFileSync('painting/v2-ae36dd9cc63c5c071cd9611976aff2e9_r.jpg'))));fs.writeFileSync('firmware/assets/welcome.bin',art.bin);
