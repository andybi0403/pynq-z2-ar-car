'use strict';
const assert=require('node:assert/strict');
const {ByteReader,LatestSlot,WirelessPlayer}=require('../host/wireless_player.js');
const jpeg=Buffer.from([255,216,42,255,217]);
function multipart(id=7,body=jpeg){return Buffer.concat([Buffer.from(`--carframe\r\nContent-Length: ${body.length}\r\nX-Frame-Id: ${id}\r\nX-JPEG-Quality: 75\r\n\r\n`),body,Buffer.from('\r\n')]);}
function reader(bytes,width){let offset=0;return new ByteReader({read:async()=>offset>=bytes.length?{done:true}:{done:false,value:bytes.subarray(offset,(offset+=width))}});}
(async()=>{
  for(const width of [1,2,7,64,4096]){const r=reader(Buffer.concat([multipart(7),multipart(8)]),width);
    assert.equal((await r.frame()).id,7);assert.equal((await r.frame()).id,8);}
  await assert.rejects(()=>reader(multipart('9007199254740992'),2).frame(),/上限/);
  await assert.rejects(()=>reader(multipart(1,Buffer.from('wrong')),2).frame(),/JPEG/);
  await assert.rejects(()=>reader(Buffer.from('--carframe\r\nContent-Length: 99999999\r\nX-Frame-Id: 1\r\n\r\n'),3).frame(),/上限/);
  await assert.rejects(()=>reader(Buffer.from('x'.repeat(1100)),9).frame(),/过长/);
  const slot=new LatestSlot();for(let n=0;n<10000;n++)slot.put({id:n});assert.equal(slot.replaced,9999);assert.equal(slot.take().id,9999);assert.equal(slot.take(),null);
  // Actual pump: block one JPEG decode, push many new frames, verify only newest survives.
  let decodingResolve,decodes=0,closed=0,draws=0,dimensionWrites=0;
  global.createImageBitmap=async()=>{decodes++;if(decodes===1)await new Promise(r=>decodingResolve=r);return {width:1280,height:720,close:()=>closed++};};
  global.requestAnimationFrame=fn=>fn();global.document={hidden:false};
  const canvas={getContext:()=>({drawImage:()=>draws++}),get width(){return 1280;},set width(v){dimensionWrites++;},get height(){return 720;},set height(v){dimensionWrites++;}};
  const p=new WirelessPlayer(canvas);p.slot.put({id:1,jpeg,generation:0,videoSession:null,received:performance.now()});const running=p.pump();
  for(let id=2;id<=100;id++)p.slot.put({id,jpeg,generation:0,videoSession:null,received:performance.now()});
  decodingResolve();await running;assert.equal(decodes,2);assert.equal(draws,2);assert.equal(closed,2);assert.equal(dimensionWrites,0);
  p.slot.put({id:101,jpeg,generation:0,videoSession:null,received:performance.now()-1000});await p.pump();assert.equal(draws,2);assert.equal(closed,3);
  p.slot.put({id:102,jpeg,generation:-1,videoSession:null,received:performance.now()});await p.pump();assert.equal(draws,2);assert.equal(closed,4);
  // Session can change while JPEG decoding/RAF is already pending.
  let raf;
  global.requestAnimationFrame=fn=>{raf=fn;};
  p.videoSession='old';
  p.slot.put({id:103,jpeg,generation:0,videoSession:'old',received:performance.now()});
  const oldPaint=p.pump();await new Promise(r=>setImmediate(r));
  p.videoSession='new';raf();await oldPaint;assert.equal(draws,2);assert.equal(closed,5);
  const delayed={id:104,jpeg,generation:0,videoSession:'new',received:performance.now()};
  p.slot.put(delayed);const latePaint=p.pump();await new Promise(r=>setImmediate(r));
  delayed.received-=1000;raf();await latePaint;assert.equal(draws,2);assert.equal(closed,6);
  // Real read-loop restart: high old ID -> low new ID; still reject a
  // duplicate within the new HTTP stream, and cancel both abandoned bodies.
  global.requestAnimationFrame=fn=>fn();
  const originalTimeout=global.setTimeout;const retries=[];let calls=0,canceled=0;
  const messages=[];const restarted=new WirelessPlayer(canvas,text=>messages.push(text));
  global.setTimeout=fn=>retries.push(fn);
  global.fetch=async()=>{
    calls++;const payload=calls===1?multipart(900):Buffer.concat([multipart(1),multipart(1)]);
    let consumed=false;
    return {ok:true,headers:{get:()=>calls===1?'first-stream':'second-stream'},body:{getReader:()=>({
      read:async()=>{if(!consumed){consumed=true;return {done:false,value:payload};}
        await new Promise(r=>setImmediate(r));return {done:true};},
      cancel:async()=>{canceled++;}
    })}};
  };
  try{
    await restarted.readLoop(0,'processed');assert.equal(restarted.last,900);
    assert.equal(restarted.drawn,1);assert.equal(retries.length,1);
    await retries.shift()();assert.equal(restarted.last,1);assert.equal(restarted.drawn,2);
    assert.ok(messages.includes('重复或倒序视频帧'));assert.equal(canceled,2);
    assert.ok(restarted.info.client_receive_to_draw_ms>=0);
  }finally{global.setTimeout=originalTimeout;delete global.fetch;}
  // Delayed browser painting must not block decoding a newer JPEG. Keep
  // one bitmap and one pending paint, releasing superseded/stopped images.
  let queueDecodes=0,queueClosed=0,queueDraws=0,queuedPaint;
  global.requestAnimationFrame=fn=>{assert.equal(queuedPaint,undefined);queuedPaint=fn;};
  global.createImageBitmap=async()=>{queueDecodes++;let released=false;return {
    width:1280,height:720,close:()=>{assert.equal(released,false);released=true;queueClosed++;}};};
  const queued=new WirelessPlayer({width:1280,height:720,getContext:()=>({drawImage:()=>queueDraws++})});
  const fresh=id=>({id,jpeg,generation:0,videoSession:null,received:performance.now(),quality:85});
  const old=fresh(300);queued.slot.put(old);await queued.pump();
  assert.equal(queueDecodes,1);assert.ok(queuedPaint);
  old.received-=1000;queued.slot.put(fresh(301));await queued.pump();
  assert.equal(queueDecodes,2,'delayed paint must not block the latest JPEG decode');
  assert.equal(queueClosed,1,'superseded bitmap must be released');
  const paint=queuedPaint;queuedPaint=undefined;paint();
  assert.equal(queueDraws,1);assert.equal(queued.info.frame_id,301);assert.equal(queueClosed,2);
  queued.slot.put(fresh(302));await queued.pump();queued.stop();
  const stopped=queuedPaint;queuedPaint=undefined;stopped();
  assert.equal(queueDraws,1);assert.equal(queueClosed,3);
  global.document.hidden=true;queued.slot.put(fresh(303));await queued.pump();
  assert.equal(queueDecodes,3,'hidden tabs must not decode discarded frames');
  global.document.hidden=false;
  console.log('PLAYER_PASS: fragmented MJPEG, malformed bounds, latest-only decode, stale switch, bitmap ownership, canvas reuse');
})().catch(e=>{console.error(e);process.exitCode=1;});
