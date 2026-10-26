'use strict';
const {chromium}=require('playwright');
const fs=require('node:fs/promises');
(async()=>{
 const out='work/ground_trial_20261026';
 const {url}=JSON.parse(await fs.readFile(out+'/active-session.json','utf8'));
 const browser=await chromium.launch({channel:'msedge',headless:true,args:['--no-proxy-server']});
 const errors=[];
 try{
  const page=await browser.newPage({viewport:{width:1200,height:1100}});
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url,{waitUntil:'domcontentloaded',timeout:12000});
  await page.waitForFunction(()=>last?.telemetry_fresh&&last.latest?.stm32_link?.link_fresh&&synced,{},{timeout:15000});
  const result=await page.evaluate(()=>({state:last,claimed,release_disabled:document.getElementById('release').disabled,drive_disabled:document.querySelector('[data-drive=w]').disabled,title:document.title}));
  result.page_errors=errors;result.release_sent=false;result.motion_sent=false;
  await page.screenshot({path:out+'/live-trial-console.png',fullPage:true});
  await fs.writeFile(out+'/live-browser.json',JSON.stringify(result,null,2));
  const car=result.state.latest.control.car;
  if(errors.length||result.claimed||!result.release_disabled||!result.drive_disabled||result.state.mode!=='controlled-trial'||!car||car.lock!==1||car.left||car.right)throw Error('read-only trial UI check failed');
  console.log(JSON.stringify({live_trial_ui:true,actual_locked_zero:true,unclaimed:true,blockers:result.state.latest.blockers,page_errors:errors.length}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.message.replace(/#token=[\w-]+/g,'#token=<redacted>'));process.exitCode=1;});
