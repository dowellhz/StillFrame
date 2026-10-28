import {createApp} from './app.mjs';
const {server,close}=await createApp();
const host=process.env.STILLFRAME_HOST||'127.0.0.1',port=Number(process.env.STILLFRAME_PORT||8484);
server.on('error',e=>{console.error('Stillframe 启动失败：',e.message);close();process.exitCode=1;});
server.listen(port,host,()=>console.log(`Stillframe 0.1.30 已启动：http://${host}:${port}`));
let stopping=false;function stop(){if(stopping)return;stopping=true;server.close(()=>{close();process.exit(0);});server.closeIdleConnections?.();setTimeout(()=>{close();process.exit(1);},10000).unref();}
process.on('SIGTERM',stop);process.on('SIGINT',stop);
