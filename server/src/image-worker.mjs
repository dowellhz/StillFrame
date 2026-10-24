import {parentPort,workerData} from 'node:worker_threads';
import {processImage} from './image.mjs';
try{const r=processImage(Buffer.from(workerData.bytes),workerData.settings);parentPort.postMessage({ok:true,...r});}catch(e){parentPort.postMessage({ok:false,error:e.message});}
