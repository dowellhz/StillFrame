import crypto from 'node:crypto';
export const BOARD='ESP32-133C02-IL',PANEL='GDEP133C02',MAX_ROM=5*1024*1024;
const bad=message=>{throw Object.assign(new Error(message),{status:400});};
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const fixed=(b,start,len)=>{const v=b.subarray(start,start+len),end=v.indexOf(0);if(end<1||v.subarray(end).some(x=>x!==0))bad('ROM 型号或版本字段无效');return v.subarray(0,end).toString('utf8');};
// ESP-IDF application image: 24-byte header, segment table/data, XOR checksum,
// 16-byte padding and mandatory appended SHA-256. Full-flash images are rejected.
export function inspectRom(b){
 if(!Buffer.isBuffer(b)||b.length<372||b.length>MAX_ROM)bad('请上传不超过 5 MiB 的应用 ROM（Stillframe.bin）');
 if(b[0]!==0xe9||b[1]<1||b[1]>16||b.readUInt16LE(12)!==9||b[23]!==1)bad('需要 ESP32-S3 应用 ROM，不能上传整包刷机文件');
 if(b.readUInt32LE(32)!==0xabcd5432)bad('未找到应用信息，请上传 Stillframe.bin');
 if(fixed(b,80,32)!=='Stillframe')bad('ROM 不属于 Stillframe');
 const version=fixed(b,48,32);if(!/^\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?$/.test(version))bad('ROM 版本无效');
 if(!b.subarray(288,304).equals(Buffer.from('STILLFRAME-HW1\0\0')))bad('旧 ROM 缺少主板信息，禁止远程下发');
 const boardModel=fixed(b,304,32),panelModel=fixed(b,336,24),otaProtocol=b.readUInt32LE(360),width=b.readUInt16LE(364),height=b.readUInt16LE(366);
 if(b.readUInt32LE(368)!==0)bad('测试 ROM 禁止远程下发');
 if(boardModel!==BOARD||panelModel!==PANEL||otaProtocol!==1||width!==1200||height!==1600)bad('ROM 主板、屏幕型号或升级协议不匹配');
 let off=24,checksum=0xef;
 for(let i=0;i<b[1];i++){if(off+8>b.length)bad('ROM 分段损坏');const len=b.readUInt32LE(off+4);off+=8;if(!len||off+len>b.length||(i===0&&len<340))bad('ROM 分段不完整');for(const v of b.subarray(off,off+len))checksum^=v;off+=len;}
 const checksumAt=Math.ceil((off+1)/16)*16-1;
 if(checksumAt+33!==b.length||b[checksumAt]!==checksum||b.subarray(off,checksumAt).some(x=>x!==0))bad('ROM 长度或校验码不正确');
 if(!b.subarray(checksumAt+1).equals(crypto.createHash('sha256').update(b.subarray(0,checksumAt+1)).digest()))bad('ROM 内置 SHA-256 校验失败');
 return {version,boardModel,panelModel,chipModel:'esp32s3',otaProtocol,width,height,bytes:b.length,sha256:sha(b)};
}
export function compatible(d,f){return !d.disabled&&d.boardModel===f.boardModel&&d.panelModel===f.panelModel&&d.chipModel===f.chipModel&&d.otaProtocol===f.otaProtocol&&Number.isInteger(d.otaSlotBytes)&&d.otaSlotBytes>=f.bytes;}
export function firmwareOffer(s,d){const task=d.firmwareTask;if(!task||!['queued','offered'].includes(task.status))return null;const f=(s.firmwares||[]).find(f=>f.id===task.firmwareId);if(!f||!compatible(d,f)){task.status='failed';task.message='设备硬件信息已改变或 ROM 不可用，拒绝下发';return null;}task.status='offered';return {...f,taskId:task.id,url:`/api/v1/device/firmware/${f.id}?deviceId=${encodeURIComponent(d.id)}&taskId=${task.id}`};}
