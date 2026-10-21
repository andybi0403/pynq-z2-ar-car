/* Real JPEG receipt/decode/canvas draw counts. One decoding job + newest JPEG. */
(function(global){
'use strict';
class ByteReader {
  constructor(reader){this.reader=reader;this.chunk=new Uint8Array(0);this.offset=0;}
  async fill(){
    while(this.offset===this.chunk.length){
      const part=await this.reader.read();if(part.done)throw Error('视频流已结束');
      if(!(part.value instanceof Uint8Array))throw Error('无效视频数据');
      this.chunk=part.value;this.offset=0;
    }
  }
  async line(max=1024){
    const bytes=[];
    while(bytes.length<=max){await this.fill();const b=this.chunk[this.offset++];
      bytes.push(b);if(b===10)return String.fromCharCode(...bytes).replace(/\r?\n$/,'');
    }
    throw Error('MJPEG头过长');
  }
  async exact(length){
    const result=new Uint8Array(length);let written=0;
    while(written<length){await this.fill();const n=Math.min(length-written,this.chunk.length-this.offset);
      result.set(this.chunk.subarray(this.offset,this.offset+n),written);this.offset+=n;written+=n;
    }
    return result;
  }
  async frame(){
    let boundary=await this.line();if(boundary==='')boundary=await this.line();
    if(boundary!=='--carframe')throw Error('MJPEG边界错误');
    const headers={};let total=0;
    for(;;){const line=await this.line();if(!line)break;total+=line.length;
      if(total>2048)throw Error('MJPEG头过长');const split=line.indexOf(':');
      if(split<=0)throw Error('无效MJPEG头');headers[line.slice(0,split).toLowerCase()]=line.slice(split+1).trim();
    }
    if(!/^\d+$/.test(headers['content-length']||'')||!/^\d+$/.test(headers['x-frame-id']||''))throw Error('无效帧长度/身份');
    const length=Number(headers['content-length']),id=Number(headers['x-frame-id']);
    if(length<4||length>4*1024*1024||!Number.isSafeInteger(id))throw Error('帧超出上限');
    const jpeg=await this.exact(length);
    if(jpeg[0]!==255||jpeg[1]!==216||jpeg[length-2]!==255||jpeg[length-1]!==217)throw Error('JPEG不完整');
    return {id,jpeg,quality:headers['x-jpeg-quality']||'unknown',captured:headers['x-captured-monotonic-ns']};
  }
}
class LatestSlot {
  constructor(){this.latest=null;this.replaced=0;}
  put(frame){if(this.latest)this.replaced++;this.latest=frame;}
  take(){const frame=this.latest;this.latest=null;return frame;}
  clear(){this.latest=null;}
}
class WirelessPlayer {
  constructor(canvas,onStatus=()=>{}){
    this.canvas=canvas;this.context=canvas.getContext('2d',{alpha:false});this.onStatus=onStatus;
    this.slot=new LatestSlot();this.generation=0;this.abort=null;this.decoding=false;
    this.received=0;this.drawn=0;this.decodeDropped=0;this.last=-1;this.view='processed';this.videoSession=null;
    this.ready=null;this.paintScheduled=false;
    this.rateAt=performance.now();this.rateReceived=0;this.rateDrawn=0;this.info={received_fps:0,drawn_fps:0};
  }
  stop(){this.generation++;if(this.abort)this.abort.abort();this.slot.clear();this.discardReady();this.videoSession=null;}
  start(view){this.stop();this.view=view;this.last=-1;this.rateAt=performance.now();this.rateReceived=this.received;this.rateDrawn=this.drawn;
    this.readLoop(this.generation,view);}
  async readLoop(generation,view){
    if(generation!==this.generation)return;const abort=new AbortController();this.abort=abort;
    let streamReader;
    try{
      const response=await fetch('/api/video?view='+view,{signal:abort.signal});
      if(!response.ok)throw Error(await response.text());
      if(generation!==this.generation)return;
      const session=response.headers.get('X-Video-Session');
      if(!session)throw Error('视频流缺少会话身份');
      // Frame IDs are ordered inside a connection. A restarted board may
      // begin again at one; clear old decode work at the new stream boundary.
      this.slot.clear();this.discardReady();this.last=-1;this.videoSession=session;
      streamReader=response.body.getReader();const reader=new ByteReader(streamReader);
      while(generation===this.generation){const frame=await reader.frame();if(generation!==this.generation)return;
        if(frame.id<=this.last)throw Error('重复或倒序视频帧');this.last=frame.id;frame.generation=generation;
        frame.videoSession=session;frame.received=performance.now();this.received++;this.info.quality=frame.quality;this.info.frame_bytes=frame.jpeg.length;
        this.slot.put(frame);this.pump();
      }
    }catch(error){
      if(generation!==this.generation)return;this.slot.clear();this.discardReady();this.videoSession=null;this.onStatus(error.message);
      setTimeout(()=>this.readLoop(generation,view),500);
    }finally{
      abort.abort();
      // Do not retain abandoned HTTP bodies across Wi-Fi/service reconnects.
      if(streamReader){try{streamReader.cancel().catch(()=>{});}catch(error){}}
    }
  }
  discardReady(){
    if(this.ready){this.ready.bitmap.close();this.ready=null;this.decodeDropped++;}
  }
  schedulePaint(){
    if(this.paintScheduled)return;this.paintScheduled=true;
    requestAnimationFrame(()=>{
      this.paintScheduled=false;const ready=this.ready;this.ready=null;
      if(!ready)return;const {frame,bitmap}=ready;
      try{
        if(frame.generation!==this.generation||frame.videoSession!==this.videoSession||
            document.hidden||performance.now()-frame.received>500){this.decodeDropped++;return;}
        if(this.canvas.width!==1280)this.canvas.width=1280;
        if(this.canvas.height!==720)this.canvas.height=720;
        this.context.drawImage(bitmap,0,0);this.drawn++;
        this.info.client_receive_to_draw_ms=performance.now()-frame.received;
        this.info.frame_id=frame.id;this.info.view=this.view;
        this.onStatus(`帧 #${frame.id} · 1280×720 · ${frame.quality==='camera-native'?'摄像头原生画质':'JPEG质量 '+frame.quality}`);
      }catch(error){this.decodeDropped++;this.onStatus(error.message);}
      finally{bitmap.close();}
    });
  }
  async pump(){
    if(this.decoding)return;this.decoding=true;
    try{
      for(let frame; (frame=this.slot.take());){
        let bitmap;
        try{
          if(document.hidden){this.decodeDropped++;continue;}
          bitmap=await createImageBitmap(new Blob([frame.jpeg],{type:'image/jpeg'}));
          if(frame.generation!==this.generation||frame.videoSession!==this.videoSession||
              document.hidden||performance.now()-frame.received>500){this.decodeDropped++;continue;}
          if(bitmap.width!==1280||bitmap.height!==720)throw Error('实际JPEG不是1280×720');
          // Keep decoding independently of the browser's paint scheduling.
          // One ready bitmap is replaced by the latest, and one RAF is pending.
          this.discardReady();this.ready={frame,bitmap};bitmap=null;this.schedulePaint();
        }catch(error){this.decodeDropped++;this.onStatus(error.message);}
        finally{if(bitmap)bitmap.close();}
      }
    }finally{this.decoding=false;}
  }
  rates(){
    const now=performance.now(),seconds=Math.max(.001,(now-this.rateAt)/1000);
    if(seconds<.5)return {...this.info,received_fps:0,drawn_fps:0,warming_up:true,video_session:null,visible:!document.hidden,client_dropped:this.slot.replaced+this.decodeDropped};
    const result={...this.info,received_fps:(this.received-this.rateReceived)/seconds,drawn_fps:(this.drawn-this.rateDrawn)/seconds,
      client_dropped:this.slot.replaced+this.decodeDropped,video_session:this.videoSession,visible:!document.hidden};
    this.rateAt=now;this.rateReceived=this.received;this.rateDrawn=this.drawn;this.info=result;return result;
  }
}
const exported={ByteReader,LatestSlot,WirelessPlayer};
if(typeof module!=='undefined'&&module.exports)module.exports=exported;
else global.CarVideo=exported;
})(typeof window!=='undefined'?window:globalThis);
