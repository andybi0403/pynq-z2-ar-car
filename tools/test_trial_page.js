'use strict';
// Browser test with simulated telemetry only; never connects to the car.
const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
 const html=fs.readFileSync('pynq_fpga/preintegration/host/trial_page.html','utf8');
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const errors=[];
 let state={mode:'controlled-trial',running:true,hardware:true,telemetry_fresh:true,
   motion_ready:false,release_ready:false,latest:{control:{phase:'LOCKED',car:{lock:1,left:0,right:0,mm:560,ir:3}},scales:[0,0],blockers:['双轮编码器尚未实测标定（SCALE=0）','STM32 红外仍报告障碍：IR=3']}};
 try{
  const page=await browser.newPage({viewport:{width:1100,height:1000}});
  page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(()=>{
   window.__sent=[];
   class Socket{
    static OPEN=1;
    constructor(){this.readyState=1;queueMicrotask(()=>this.onmessage?.({data:JSON.stringify({type:'sync',nonce:'test'})}));}
    send(raw){const m=JSON.parse(raw);window.__sent.push(m);if(m.type==='sync'||m.type==='claim')queueMicrotask(()=>this.onmessage?.({data:JSON.stringify({type:m.type==='sync'?'synced':'claimed'})}));}
    close(){this.readyState=3;this.onclose?.();}
   }
   window.WebSocket=Socket;
  });
  await page.route('http://trial.test/**',route=>route.fulfill({status:200,contentType:route.request().url().endsWith('/api/status')?'application/json':'text/html',body:route.request().url().endsWith('/api/status')?JSON.stringify(state):html}));
  await page.goto('http://trial.test/');
  await page.waitForFunction(()=>document.getElementById('claim').disabled===false);
  assert.equal(await page.locator('#release').isDisabled(),true);
  assert.equal(await page.locator('[data-drive=w]').isDisabled(),true);
  assert.equal(await page.evaluate(()=>__sent.some(m=>m.type==='release'||m.left||m.right)),false);
  await page.locator('#claim').click();
  await page.waitForFunction(()=>claimed);
  assert.equal(await page.locator('#release').isDisabled(),true);
  state.release_ready=true;state.latest.blockers=[];
  await page.waitForFunction(()=>!document.getElementById('release').disabled);
  await page.locator('#release').click();
  await page.waitForFunction(()=>__sent.some(m=>m.type==='release'));
  assert.equal(await page.locator('[data-drive=w]').isDisabled(),true); // Real unlock ACK still required.
  state.motion_ready=true;state.latest.control.phase='ARMED';state.latest.control.car.lock=0;
  await page.waitForFunction(()=>!document.querySelector('[data-drive=w]').disabled);
  await page.keyboard.down('w');
  await page.waitForFunction(()=>__sent.some(m=>m.left===400&&m.right===400));
  await page.keyboard.up('w');
  await page.waitForFunction(()=>__sent.at(-1).type==='stop');
  const stoppedAt=await page.evaluate(()=>__sent.length);
  await page.waitForTimeout(180);
  assert.equal(await page.evaluate(n=>__sent.slice(n).some(m=>m.left||m.right),stoppedAt),false);
  await page.locator('#claim').click();
  await page.waitForFunction(()=>claimed);
  await page.keyboard.down('w');
  await page.waitForFunction(()=>held==='w');
  await page.evaluate(()=>window.dispatchEvent(new Event('blur')));
  assert.equal(await page.evaluate(()=>claimed),false);
  assert.equal(await page.evaluate(()=>__sent.at(-1).type),'stop');
  await page.keyboard.up('w');
  await page.reload();
  await page.waitForFunction(()=>synced&&last);
  assert.equal(await page.evaluate(()=>claimed),false);
  assert.equal(await page.evaluate(()=>__sent.some(m=>m.type==='release'||m.type==='claim'||m.left||m.right)),false);
  assert.deepEqual(errors,[]);
  fs.mkdirSync('work/ground_trial_20261026',{recursive:true});
  await page.screenshot({path:'work/ground_trial_20261026/simulated-ui.png',fullPage:true});
  console.log(JSON.stringify({simulated_browser:true,checks:['initial lock','sensor blockers','explicit release','real unlock ACK required','PWM cap','key-up STOP','blur STOP','no reconnect replay'],page_errors:errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
