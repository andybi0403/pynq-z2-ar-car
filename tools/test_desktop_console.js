'use strict';
// Real localhost HTTP server + production assets; never connect to the car.
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs/promises');
const python=process.env.CAR_CONSOLE_PYTHON||path.join(process.env.LOCALAPPDATA,'Programs/Python/Python314/python.exe');
(async()=>{
 const server=spawn(python,['-X','utf8','tools/open_car_console.py','--no-open'],{windowsHide:true});
 let browser;
 try{
  const origin=await new Promise((resolve,reject)=>{let output='';const timeout=setTimeout(()=>reject(Error('local server startup timeout')),10000);server.stdout.on('data',data=>{output+=data;const match=output.match(/http:\/\/127\.0\.0\.1:\d+/);if(match){clearTimeout(timeout);resolve(match[0]);}});server.once('error',reject);server.once('exit',code=>{if(code)reject(Error('local server exited '+code));});});
  browser=await chromium.launch({channel:'msedge',headless:true});
  const page=await browser.newPage({viewport:{width:1512,height:1080}}),errors=[],external=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',route=>{if(new URL(route.request().url()).origin!==origin){external.push(route.request().url());return route.abort();}return route.continue();});
  await page.goto(origin);await page.waitForFunction(()=>window.ConsoleApp&&document.getElementById('sourceLabel').textContent.includes('未连接'));
  await page.waitForTimeout(250);
  assert.equal(await page.locator('#consoleView').isVisible(),true);
  assert.equal(await page.locator('#claim').isDisabled(),true);
  assert.equal(await page.locator('[data-drive=w]').isDisabled(),true);
  assert.equal(await page.locator('#speedMain').textContent(),'—');
  for(const tab of ['sensors','records','demo','overview']){await page.locator('.console-nav [data-tab='+tab+']').click();assert.equal(await page.locator('body').getAttribute('data-tab'),tab);}
  const out=path.resolve('work/complete_console_20261026');await fs.mkdir(out,{recursive:true});
  await page.screenshot({path:path.join(out,'desktop-offline.png'),fullPage:true});
  await page.locator('#connectionSettings').click();assert.equal(await page.locator('#connectView').isVisible(),true);
  assert.equal(await page.locator('#serverAddress').inputValue(),'http://192.168.8.139:8080');
  assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
  await fs.writeFile(path.join(out,'desktop-results.json'),JSON.stringify({hardware:false,server:'production localhost HTTP',network_auto_connect:false,external_requests:external,page_errors:errors,checks:['production desktop page opens offline','all four navigation tabs work offline','unknown measurements and driving disabled','connection settings remain available','no external requests']},null,2));
  console.log('DESKTOP_CONSOLE_PASS 5 checks; no external requests');
 }finally{if(browser)await browser.close();server.kill();}
})().catch(error=>{console.error(error);process.exitCode=1;});
