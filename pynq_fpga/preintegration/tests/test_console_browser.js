'use strict';
// Browser interaction regression. All telemetry is an OFFLINE FIXTURE, never hardware evidence.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const host=path.resolve(__dirname,'../host');
const output=path.resolve(__dirname,'../../../work/console_connection_20261025_r6');
const base='http://127.0.0.1:18765',token='offline-wasd-token';
(async()=>{
  await fs.mkdir(output,{recursive:true});
  const browser=await chromium.launch({channel:'chrome',headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  await context.route('**/*',route=>route.request().url().startsWith('file:')?route.continue():route.abort()); // No external or vehicle requests.
  const page=await context.newPage(),errors=[],checks=[];
  page.on('pageerror',e=>errors.push(e.message));
  const state={authorized:false,hang:false,offline:false,loginCount:0,wsCount:0,stopCount:0};
  function status(){return {hardware:false,running:true,control_available:true,telemetry_fresh:true,
    identity:{offline_fixture:true},latest:{status:{distance_valid:true,distance_mm:321,
      car_valid:true,car:{lock:1,left:0,right:0,fault:0},
      infrared:{valid:true,mask:1,sequence:21},encoder:{left:{valid:true,sequence:50},right:{valid:true,sequence:60}},
      stm32_link:{link_fresh:true,state_sequence:32,sensor_errors:0,last_reply_age_ms:10,last_reply_latency_ms:2}}},
    video:{fps_since_start:{captured:12}}};}
  await page.route(base+'/**',async route=>{
    const request=route.request(),url=new URL(request.url()),p=url.pathname;
    const json=(value,status=200,headers={})=>route.fulfill({status,contentType:'application/json',headers,body:JSON.stringify(value)});
    if(p==='/')return route.fulfill({contentType:'text/html',body:await fs.readFile(path.join(host,'wireless_page.html'),'utf8')});
    if(p==='/assets/wireless_player.js')return route.fulfill({contentType:'application/javascript',body:await fs.readFile(path.join(host,'wireless_player.js'),'utf8')});
    if(p==='/assets/console_ui.js')return route.fulfill({contentType:'application/javascript',body:await fs.readFile(path.join(host,'console_ui.js'),'utf8')});
    if(state.offline)return route.abort('connectionfailed');
    if(p==='/api/session'){
      state.loginCount++;
      if(state.hang){await new Promise(r=>setTimeout(r,5000));return route.abort().catch(()=>{});}
      if(request.headers()['authorization']!=='Bearer '+token)return json({error:'unauthorized'},401);
      state.authorized=true;return json({authenticated:true},200,{'Set-Cookie':'car_session=fixture; Path=/; HttpOnly; SameSite=Strict'});
    }
    if(!state.authorized)return json({error:'unauthorized'},401);
    if(p==='/api/session/logout'){state.authorized=false;return json({authenticated:false},200,{'Set-Cookie':'car_session=; Max-Age=0; Path=/'});}
    if(p==='/api/status')return json(status());
    if(p==='/api/video/settings')return json({mode:'auto',max_fps:30,max_quality:85});
    if(p==='/api/stop'){state.stopCount++;return json({queued:true});}
    if(p==='/api/video')return route.abort();
    return json({});
  });
  await page.routeWebSocket(base.replace('http','ws')+'/api/control',ws=>{
    state.wsCount++;ws.send(JSON.stringify({type:'sync',nonce:'fixture'}));
    ws.onMessage(raw=>{const m=JSON.parse(String(raw));if(m.type==='sync')ws.send(JSON.stringify({type:'synced'}));});
  });
  const text=id=>page.locator('#'+id).textContent();
  const gate=()=>page.waitForFunction(()=>!document.getElementById('connectView').hidden);
  const consoleVisible=()=>page.waitForFunction(()=>typeof connected!=='undefined'&&connected&&!document.getElementById('consoleView').hidden);
  async function login(){await page.locator('#sessionToken').fill(token);await page.locator('#connectButton').click();await consoleVisible();await page.waitForFunction(()=>document.getElementById('qeiLeftCard').textContent==='seq 50');}
  try{
    await page.goto(base);await gate();
    await page.locator('#sessionToken').pressSequentially('wasd space');
    assert.equal(await page.locator('#sessionToken').inputValue(),'wasd space');checks.push('login keyboard accepts WASD and spaces');
    await page.locator('#sessionToken').fill('http://[');await page.locator('#connectButton').click();
    await page.waitForFunction(()=>document.getElementById('connectStatus').textContent.includes('连接失败'));
    assert.equal(errors.length,0);checks.push('malformed link is caught');
    await page.locator('#sessionToken').fill('wrong');await page.locator('#connectButton').click();
    await page.waitForFunction(()=>document.getElementById('connectStatus').textContent.includes('令牌无效'));
    checks.push('wrong token remains at connection page');
    state.hang=true;await page.locator('#sessionToken').fill(token);await page.locator('#connectButton').click();
    await page.waitForFunction(()=>document.getElementById('connectStatus').textContent.includes('连接超时'),{},{timeout:6500});
    state.hang=false;checks.push('stalled authentication times out and unlocks button');
    await login();checks.push('manual login enters console');
    await page.screenshot({path:path.join(output,'console-desktop.png'),fullPage:true});
    await page.reload();await consoleVisible();checks.push('existing session reload enters console');
    await page.waitForFunction(()=>document.getElementById('qeiLeftCard').textContent==='seq 50');
    state.offline=true;
    await page.waitForFunction(()=>document.getElementById('qeiLeftCard').textContent==='—');
    assert.equal(await text('distanceCard'),'—');assert.equal(await text('lockCard'),'未收到');
    checks.push('network loss clears encoder, distance and actuator data');
    state.offline=false;await page.waitForFunction(()=>document.getElementById('qeiLeftCard').textContent==='seq 50');
    checks.push('network restoration refreshes data without restoring ownership');
    state.authorized=false;await gate();checks.push('service token change returns to connection gate');
    await login();await page.locator('#disconnect').click();await gate();
    await page.waitForFunction(()=>document.getElementById('connectStatus').textContent==='已断开连接。');
    const sockets=state.wsCount;await page.waitForTimeout(1300);assert.equal(state.wsCount,sockets);
    assert.equal(state.authorized,false);checks.push('disconnect clears session and prevents delayed socket reconnect');
    await page.goto(base+'/#token='+token);await consoleVisible();assert.equal(new URL(page.url()).hash,'');
    checks.push('full startup link auto-login removes token from address bar');
    await page.locator('#disconnect').click();await gate();
    await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(output,'connection-mobile.png'),fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);checks.push('390px connection layout fits');
    await login();await page.screenshot({path:path.join(output,'console-mobile.png'),fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);checks.push('390px console layout fits');
    state.authorized=false;await page.goto(pathToFileURL(path.join(host,'console_launcher.html')).href);
    await page.locator('#sessionToken').fill(base+'/#token='+token);await page.locator('button[type=submit]').click();await consoleVisible();
    checks.push('offline local HTML launcher navigates to authenticated board page');
    assert.deepEqual(errors,[]);
    await fs.writeFile(path.join(output,'browser-results.json'),JSON.stringify({hardware:false,scope:'offline browser fixture',checks,page_errors:errors},null,2));
    console.log('BROWSER_PASS '+checks.length+' scenarios; no page errors');
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
