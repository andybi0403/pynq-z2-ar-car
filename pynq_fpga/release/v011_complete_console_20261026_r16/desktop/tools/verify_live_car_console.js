'use strict';
const {chromium}=require('playwright');
const fs=require('node:fs/promises');
const path=require('node:path');
(async()=>{
  const directory=path.resolve('work/connection_live_20261025');
  const launch=JSON.parse(await fs.readFile(path.join(directory,'active-session.json'),'utf8'));
  const browser=await chromium.launch({channel:'msedge',headless:true,args:['--no-proxy-server']});
  const errors=[];
  try{
    const page=await browser.newPage({viewport:{width:1440,height:1000}});
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(launch.url,{waitUntil:'domcontentloaded',timeout:12000});
    await page.waitForFunction(()=>!document.getElementById('consoleView').hidden,{},{timeout:12000});
    await page.waitForFunction(()=>typeof player!=='undefined'&&player.drawn>=3&&lastSnapshot?.hardware===true,{},{timeout:20000});
    await page.waitForFunction(()=>{
      const s=lastSnapshot?.latest?.status,c=s?.car;
      return s?.stm32_link?.link_fresh&&c?.lock===1&&c.left===0&&c.right===0;
    },{},{timeout:8000});
    const result=await page.evaluate(()=>({console_visible:!document.getElementById('consoleView').hidden,
      frames_drawn:player.drawn,video:player.rates(),state:lastSnapshot,
      distance:document.getElementById('distanceCard').textContent,
      lock:document.getElementById('lockCard').textContent,
      left:document.getElementById('qeiLeftCard').textContent,right:document.getElementById('qeiRightCard').textContent}));
    await page.screenshot({path:path.join(directory,'live-console-edge.png'),fullPage:true});
    result.hardware=result.state.hardware;result.motion_commands_sent=false;result.page_errors=errors;
    await fs.writeFile(path.join(directory,'live-browser-result.json'),JSON.stringify(result,null,2));
    const physical=result.state.latest?.status,car=physical?.car;
    if(errors.length||!result.console_visible||result.frames_drawn<3||result.hardware!==true||result.state.motion_allowed!==false||result.state.motor_disconnected!==false||!physical?.stm32_link?.link_fresh||car?.lock!==1||car.left!==0||car.right!==0)throw Error('live UI verification failed');
    console.log(JSON.stringify({live_console:true,frames_drawn:result.frames_drawn,page_errors:errors.length,lock:result.lock}));
  }finally{await browser.close();}
})().catch(e=>{console.error(e.message.replace(/#token=[\w-]+/g,'#token=<redacted>'));process.exitCode=1;});
