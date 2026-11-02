'use strict';
// All data/video below are local fixtures. No hardware/network evidence.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const host=path.resolve(__dirname,'../pynq_fpga/preintegration/host'),out=path.resolve(__dirname,'../validation/browser');
const origin='http://127.0.0.1:18845',token='local-fixture-only';
(async()=>{
 await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const page=await browser.newPage({viewport:{width:1512,height:1100},acceptDownloads:true});
 const errors=[],checks=[],messages=[],actions=[];
 const lastCommand=()=>messages.findLast(m=>['intent','stop','release'].includes(m.type));
 let offline=false,statusOnlyFailure=false,authorized=false,frame=0,recorded,controlSocket;
 const c={phase:'LOCKED',permit:false,safe_hold:false,decision_reasons:[],output_pwm:[0,0],epoch:20};
 const a={mileage_estimate:{available:true,estimated:true,travelled_mm:1234.5,source:'stm32_actual_pwm_elapsed_time'},epoch:20,distance_valid:true,distance_mm:850,speed_valid:false,speed_mm_s:null,odometry_valid:false,travelled_mm:0,displacement_mm:0,risk_level:3,car_valid:true,car:{lock:1,left:0,right:0,mm:850,ir:0,fault:1,drop:0},infrared:{valid:true,mask:0,sequence:15},encoder:{left:{valid:false,position:0,sequence:2,faults:[]},right:{valid:false,position:0,sequence:2,faults:[]}},stm32_link:{session_hex:'FIXTURE',link_fresh:true,query_tx_count:80,report_rx_count:80,sensor_errors:0,last_reply_latency_ms:6,sensor:{us_age_ms:15,ir_age_ms:10}}};
 const conf={profile:'plain_motor_demo',control_mode:'direct_manual',control_fresh:true,control_flow:'claim_release',operation_mode_required:false,motion_supported:true,motion_ready:false,release_ready:false,pwm_limit:2400,max_burst_s:0,scales:[0,0],calibration_measured:false,blockers:[],qei_configuration:[{dir:0,filter:1000,zero:10000000},{dir:1,filter:1000,zero:10000000}]};
 const state={hardware:false,running:true,telemetry_fresh:true,control_available:true,motor_disconnected:false,console:conf,identity:{offline_fixture:true,calibration:{contract_version:12,measured:false}},latest:{status:a,control:c},video:{fps_since_start:{captured:15}},failures:[]};
 a.ultrasonic_processing={filter_valid:true,filtered_mm:840,sample_count:3,sample_sequence:16,trend:'stable',trend_valid:true};
 state.display_settings={tactical_enabled:true};
 page.on('pageerror',e=>errors.push(e.message));
 const jpeg=Buffer.from(await page.evaluate(()=>{const canvas=document.createElement('canvas');canvas.width=1280;canvas.height=720;const ctx=canvas.getContext('2d');ctx.fillStyle='#214b60';ctx.fillRect(0,0,1280,720);ctx.fillStyle='#fff';ctx.font='36px sans-serif';ctx.fillText('OFFLINE UI FIXTURE - NOT LIVE VIDEO',160,340);return canvas.toDataURL('image/jpeg').split(',')[1];}),'base64');
 await page.addInitScript(base64=>{const fetchReal=window.fetch.bind(window);let id=0,session=0;const jpeg=Uint8Array.from(atob(base64),c=>c.charCodeAt(0)),encoder=new TextEncoder();window.fetch=async(input,options={})=>{const url=new URL(String(input),location.origin);if(url.pathname!=='/api/video')return fetchReal(input,options);let timer;const stream=new ReadableStream({start(controller){const stop=()=>{clearInterval(timer);try{controller.close();}catch{}};options.signal?.addEventListener('abort',stop,{once:true});timer=setInterval(()=>{const head=encoder.encode(`--carframe\r\nContent-Length: ${jpeg.length}\r\nX-Frame-Id: ${++id}\r\nX-JPEG-Quality: 75\r\n\r\n`),tail=encoder.encode('\r\n'),data=new Uint8Array(head.length+jpeg.length+tail.length);data.set(head);data.set(jpeg,head.length);data.set(tail,head.length+jpeg.length);try{controller.enqueue(data);}catch{clearInterval(timer);}},100);},cancel(){clearInterval(timer);}});return new Response(stream,{headers:{'Content-Type':'multipart/x-mixed-replace; boundary=carframe','X-Video-Session':'fixture-'+(++session)}});};},jpeg.toString('base64'));
 await page.route('**/*',async route=>{
  const request=route.request(),url=new URL(request.url());if(url.origin!==origin)return route.abort();
  const p=url.pathname,json=(v,code=200)=>route.fulfill({status:code,contentType:'application/json',body:JSON.stringify(v)});
  if(p==='/')return route.fulfill({contentType:'text/html',body:await fs.readFile(path.join(host,'wireless_page.html'),'utf8')});
  if(p.startsWith('/assets/'))return route.fulfill({contentType:'application/javascript',body:await fs.readFile(path.join(host,path.basename(p)),'utf8')});
  if(offline)return route.abort('connectionfailed');
  if(p==='/api/session'){authorized=request.headers().authorization==='Bearer '+token;return json({authenticated:authorized},authorized?200:401);}
  if(!authorized)return json({error:'not connected'},401);
  if(p==='/api/status'){if(statusOnlyFailure)return route.abort('connectionfailed');return json(state);}
  if(p==='/api/video/settings')return json({mode:'auto',max_fps:30,max_quality:85});
  if(p==='/api/display/settings'){
   if(request.method()==='POST'){const body=request.postDataJSON();assert.equal(typeof body.tactical_enabled,'boolean');state.display_settings.tactical_enabled=body.tactical_enabled;actions.push({type:'display',...body});}
   return json(state.display_settings);
  }
  if(p==='/api/video'){const id=++frame;return route.fulfill({contentType:'multipart/x-mixed-replace; boundary=carframe',headers:{'X-Video-Session':'fixture'},body:Buffer.concat([Buffer.from(`--carframe\r\nContent-Length: ${jpeg.length}\r\nX-Frame-Id: ${id}\r\nX-JPEG-Quality: 75\r\n\r\n`),jpeg,Buffer.from('\r\n')])});}
  if(p==='/api/snapshot')return json({frame_id:77,historical:{offline_fixture:true},raw_jpeg_base64:jpeg.toString('base64'),processed_jpeg_base64:jpeg.toString('base64')});
  if(p==='/api/stop'){actions.push({type:'stop'});return json({queued:true});}
  if(p==='/api/console/mode'){actions.push({type:'retired_mode_request'});return json({error:'operation modes removed'},410);}
  if(p==='/api/console/motor-state'){const body=request.postDataJSON();state.motor_disconnected=body.disconnected;conf.action={applied:true};actions.push({type:'motor-state',...body});return json({queued:true});}
  if(p==='/api/calibration'){const body=request.postDataJSON();assert.equal(state.motor_disconnected,true);assert.equal(body.measured,true);conf.scales=[body.left.scale,body.right.scale];conf.calibration_measured=true;conf.blockers=[];state.action={kind:'calibration',applied:true};actions.push({type:'calibration',body});return json({queued:true});}
  return json({queued:true});
 });
 await page.routeWebSocket(origin.replace('http','ws')+'/api/control',ws=>{
  controlSocket=ws;ws.send(JSON.stringify({type:'sync',nonce:'fixture'}));
  ws.onMessage(raw=>{const m=JSON.parse(String(raw));messages.push(m);if(m.type==='sync')ws.send(JSON.stringify({type:'synced'}));if(m.type==='claim')ws.send(JSON.stringify({type:'claimed'}));if(m.type==='intent'&&!offline)ws.send(JSON.stringify({type:'ack',seq:m.seq}));});
 });
 const clickTab=async name=>page.locator(`[data-tab=${name}]`).click();
 const wait=fn=>page.waitForFunction(fn,{}, {timeout:7000});
 try{
  await page.goto(origin);await wait(()=>!document.getElementById('consoleView').hidden);
  assert.equal(await page.locator('[data-drive=w]').isDisabled(),true);checks.push('offline shows whole console with unknown data and disabled drive');
  await page.locator('#sessionToken').fill(token);await page.locator('#connectButton').click();await wait(()=>connected&&lastSnapshot?.console);
  await wait(()=>player.drawn>0);checks.push('real player decodes 720p fixture');
  await wait(()=>document.getElementById('distanceCard').textContent==='84.0 cm');
  assert.match(await page.locator('#distanceSub').textContent(),/85.0 cm.*稳定/);
  a.ultrasonic_processing.filter_valid=false;await wait(()=>document.getElementById('distanceCard').textContent==='—');
  assert.match(await page.locator('#distanceSub').textContent(),/采样中/);
  delete a.ultrasonic_processing;await wait(()=>document.getElementById('distanceSub').textContent==='该记录无滤波数据');
  a.ultrasonic_processing={filter_valid:true,filtered_mm:840,sample_count:3,sample_sequence:16,trend:'approaching',trend_valid:true};
  await wait(()=>document.getElementById('distanceCard').textContent==='84.0 cm');
  checks.push('distance uses PL filter, preserves raw comparison, rejects missing and warming data');
  const displayBefore=messages.filter(m=>['intent','stop','release'].includes(m.type)).length;
  await page.locator('#tacticalEnabled').uncheck();await wait(()=>lastSnapshot.display_settings.tactical_enabled===false);
  await page.locator('#tacticalEnabled').check();await wait(()=>lastSnapshot.display_settings.tactical_enabled===true);
  assert.equal(messages.filter(m=>['intent','stop','release'].includes(m.type)).length,displayBefore);
  checks.push('tactical toggle changes display settings without actuator messages');
  a.distance_valid=false;a.risk_level=1;await wait(()=>document.getElementById('riskExplain').textContent.includes('距离未知'));assert.equal(await page.locator('#riskMain').textContent(),'注意');
  a.car.fault=4;await wait(()=>document.getElementById('riskMain').textContent==='紧急');a.car.fault=1;a.distance_valid=true;a.risk_level=3;checks.push('unknown range warns and retained near obstacle stays emergency');
  a.infrared.mask=3;await wait(()=>document.getElementById('infraredNotice').textContent.includes('左右两侧'));
  a.infrared.valid=false;await wait(()=>document.getElementById('infraredNotice').textContent.includes('已失效'));
  assert.match(await page.locator('#infraredNotice').textContent(),/不参与停车和解锁/);
  a.infrared.valid=true;a.infrared.mask=0;checks.push('IR obstacle and missing data are explicitly advisory');
  await page.locator('#raw').click();await wait(()=>view==='raw');await page.locator('#processed').click();await wait(()=>view==='processed');
  await page.locator('#freeze').click();await wait(()=>frozen&&!document.getElementById('pair').hidden);
  assert.equal(await page.locator('#rawFrozen').getAttribute('src'),'data:image/jpeg;base64,'+jpeg.toString('base64'));checks.push('raw/processed switch and same-frame freeze');
  await page.locator('#processed').click();
  assert.equal(await page.locator('#speedMain').isVisible(),false);
  assert.equal(await page.locator('#speedTrend').isVisible(),false);
  assert.match(await page.locator('#travelMain').textContent(),/1234.5/);
  assert.equal((await page.locator('body').innerText()).includes('未配备编码器'),false);
  checks.push('estimated mileage shown, speed and unwanted encoder label absent');
  await clickTab('sensors');
  assert.equal(await page.locator('#calStart').isVisible(),false);
  assert.equal(await page.locator('#qeiLeftCard').isVisible(),false);
  assert.equal(await page.locator('#qeiRightCard').isVisible(),false);
  checks.push('calibration workflow and unused encoder cards removed');
  await page.locator('#motorPhysical').selectOption('disconnected');await page.locator('#motorConfirmed').check();await page.locator('#motorApply').click();await wait(()=>lastSnapshot.motor_disconnected===true);
  await page.locator('#motorPhysical').selectOption('connected');await page.locator('#motorConfirmed').check();await page.locator('#motorApply').click();await wait(()=>lastSnapshot.motor_disconnected===false);
  checks.push('actual motor connection state retained independently of calibration');
  await clickTab('records');await page.locator('#recordStart').click();await page.waitForTimeout(1100);await page.locator('#recordStop').click();
  let download=page.waitForEvent('download');await page.locator('#recordJson').click();recorded=await download;const recording=JSON.parse(await fs.readFile(await recorded.path(),'utf8'));
  assert.equal(recording.schema,'car-console-recording/v1');assert.ok(recording.rows.length>=2);assert.equal(JSON.stringify(recording).includes(token),false);
  assert.equal(recording.rows.at(-1).state.latest.status.ultrasonic_processing.filtered_mm,840);
  download=page.waitForEvent('download');await page.locator('#recordCsv').click();const csv=await download;const csvText=await fs.readFile(await csv.path(),'utf8');assert.match(csvText,/actual_left_pwm/);assert.match(csvText,/estimated_travelled_mm/);assert.doesNotMatch(csvText,/speed_mm_s/);checks.push('record/stop and JSON/CSV exports omit auth token');
  await clickTab('overview');
  assert.equal(await page.locator('#driveMode,#setDriveMode').count(),0);await page.waitForTimeout(1200);
  assert.equal(actions.some(m=>m.type==='mode'||m.type==='retired_mode_request'),false);
  assert.equal(messages.some(m=>m.type==='release'),false);checks.push('operation mode removed; polling never changes workflow or automatically releases');
  conf.release_ready=true;c.decision_reasons=[];
  await wait(()=>!document.getElementById('claim').disabled);await page.locator('#claim').click();await wait(()=>claimed&&!document.getElementById('release').disabled);
  state.telemetry_fresh=false;conf.schedule_jitter_events=9;
  controlSocket.send(JSON.stringify({type:'synced'}));
  await page.waitForTimeout(1200);
  assert.equal(await page.locator('#claim').isDisabled(),true);
  assert.equal(await page.locator('#claim').textContent(),'已接管');
  assert.equal(await page.locator('#release').isDisabled(),false);
  assert.equal(await page.locator('#release').textContent(),'直接驾驶解锁');
  assert.equal(await page.evaluate(()=>claimed),true);
  state.telemetry_fresh=true;
  checks.push('direct control stays available across stale telemetry and sync; claimed button has one state owner');
  await page.locator('#release').click();await wait(()=>document.getElementById('controlStatus').textContent.includes('接管'));
  assert.equal(await page.locator('[data-drive=w]').isDisabled(),true);
  conf.motion_ready=true;c.phase='ARMED';a.car.lock=0;await wait(()=>!document.querySelector('[data-drive=w]').disabled);
  await page.keyboard.down('w');await wait(()=>window.ConsoleApp.intent()[0]===1800);
  statusOnlyFailure=true;await page.waitForTimeout(2300);
  assert.equal(await page.evaluate(()=>claimed),true);assert.equal(lastCommand().left,1800);
  assert.equal(await page.locator('#distanceCard').textContent(),'—');
  statusOnlyFailure=false;await page.waitForTimeout(650);
  checks.push('HTTP status failure keeps acknowledged control active and marks measurements unknown');
  await page.keyboard.up('w');await clickTab('demo');assert.equal(await page.evaluate(()=>claimed),true);
  assert.equal(lastCommand().left,0);await clickTab('overview');
  checks.push('internal tabs zero output without revoking ownership');
  await page.keyboard.down('w');await wait(()=>window.ConsoleApp.intent()[0]===1800);await page.waitForTimeout(100);await page.keyboard.up('w');await page.waitForTimeout(80);
  assert.equal(messages.some(m=>m.type==='intent'&&m.left===1800&&m.right===1800),true);assert.equal(lastCommand().type,'intent');assert.equal(lastCommand().left,0);assert.equal(lastCommand().right,0);assert.equal(await page.evaluate(()=>claimed),true);checks.push('keyboard release sends zero PWM and retains explicit ownership');
  for(const [key,expected] of [['s',[-1800,-1800]],['d',[1800,0]]]){await page.keyboard.down(key);await page.waitForTimeout(90);await page.keyboard.up(key);await page.waitForTimeout(80);assert.equal(messages.some(m=>m.type==='intent'&&m.left===expected[0]&&m.right===expected[1]),true);}checks.push('reverse S and right D reach WebSocket at starting PWM');
  await page.keyboard.down('w');await page.waitForTimeout(80);await page.evaluate(()=>window.dispatchEvent(new Event('blur')));await page.waitForTimeout(80);assert.equal(await page.evaluate(()=>claimed),true);assert.equal(lastCommand().left,0);await page.keyboard.up('w');checks.push('brief blur zeros drive without hard lock or ownership loss');
  await wait(()=>claimed&&!document.querySelector('[data-drive=w]').disabled);const button=page.locator('[data-drive=w]');await button.scrollIntoViewIfNeeded();const box=await button.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();await page.waitForTimeout(120);await page.mouse.up();await page.waitForTimeout(80);assert.equal(lastCommand().type,'intent');assert.equal(lastCommand().left,0);assert.equal(lastCommand().right,0);checks.push('pointer release zeros PWM; emergency STOP still revokes');await page.locator('#stop').click();assert.equal(lastCommand().type,'stop');
  await clickTab('records');const before=messages.length;await page.locator('#replayFile').setInputFiles({name:'recording.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(recording))});await wait(()=>window.ConsoleApp.isPlayback);
  assert.equal(await page.locator('#claim').isDisabled(),true);assert.equal(await page.locator('#tacticalEnabled').isDisabled(),true);await page.keyboard.down('w');await page.waitForTimeout(120);await page.keyboard.up('w');assert.equal(messages.slice(before).some(m=>m.type==='release'||(m.type==='intent'&&(m.left||m.right))),false);checks.push('replay revokes ownership, disables display changes and never drives from historical data');
  a.ultrasonic_processing.filtered_mm=1500;
  await page.waitForTimeout(1100);
  assert.equal(await page.locator('#distanceCard').textContent(),'84.0 cm');
  checks.push('replay filter and chart history stay isolated from changing live values');
  await page.locator('#replayPlay').click();await page.waitForTimeout(600);await page.locator('#replayExit').click();await wait(()=>!window.ConsoleApp.isPlayback&&connected);checks.push('play/pause/exit replay restores viewing without ownership');
  const legacyRecording=structuredClone(recording);
  for(const row of legacyRecording.rows)delete row.state.latest.status.ultrasonic_processing;
  await page.locator('#replayFile').setInputFiles({name:'legacy-recording.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(legacyRecording))});
  await wait(()=>window.ConsoleApp.isPlayback);
  assert.equal(await page.locator('#distanceCard').textContent(),'—');
  assert.equal(await page.locator('#distanceSub').textContent(),'该记录无滤波数据');
  await page.locator('#replayExit').click();await wait(()=>!window.ConsoleApp.isPlayback&&connected);
  checks.push('legacy recordings do not invent filtered measurements');
  await clickTab('demo');await page.locator('#demoNext').click();await page.locator('#demoNext').click();assert.match(await page.locator('#demoCard').textContent(),/AR 画面对比/);download=page.waitForEvent('download');await page.locator('#demoExport').click();const summary=await download;assert.equal(JSON.parse(await fs.readFile(await summary.path(),'utf8')).schema,'car-demo-observation/v1');checks.push('demonstration stages and export send no automatic motion');
  await page.locator('#present').click();assert.equal(await page.locator('body').getAttribute('class'),'presenting');await page.screenshot({path:path.join(out,'demo-fixture.png'),fullPage:true});await page.locator('#present').click();
  await clickTab('overview');await page.screenshot({path:path.join(out,'overview-fixture.png'),fullPage:true});
  conf.profile='encoder_legacy';await wait(()=>document.getElementById('claim').disabled);checks.push('legacy encoder service cannot grant control in demo UI');conf.profile='plain_motor_demo';
  offline=true;controlSocket.close();await wait(()=>document.getElementById('distanceCard').textContent==='—');assert.equal(await page.locator('[data-drive=w]').isDisabled(),true);checks.push('connection loss clears measurements and control');
  offline=false;await wait(()=>lastSnapshot?.telemetry_fresh);
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'mobile-fixture.png'),fullPage:true});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);checks.push('390px layout stays within viewport');
  assert.deepEqual(errors,[]);await fs.writeFile(path.join(out,'browser-results.json'),JSON.stringify({hardware:false,scope:'local simulated API/video fixture; no car network',checks,page_errors:errors},null,2));
  console.log('PLAIN_MOTOR_BROWSER_PASS '+checks.length+' scenarios');
 }catch(e){await page.screenshot({path:path.join(out,'failure.png'),fullPage:true});console.error(JSON.stringify({errors,checks,debug:await page.evaluate(()=>({connected,frames:player?.drawn,info:player?.info,video:document.getElementById('videoStatus').textContent,connection:document.getElementById('connectStatus').textContent}))}));throw e;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
