/* Complete console interactions. Recorded/display data never enter control. */
(()=>{
 'use strict';
 const $=id=>document.getElementById(id);
 let state=null,updated=0,held=null,press=null,tab='overview',recording=false,rows=[],bytes=0;
 let events=[],eventKey='',history=[],replay=null,replayIndex=0,replayTimer=null;
 let calibration=null,calStart=null,calFinish=null,demoIndex=0,presenting=false;
 const reasons={qei0_invalid:'左前轮编码器无效',qei1_invalid:'右前轮编码器无效',ir_invalid:'红外样本无效或过期',us_invalid:'超声波样本无效或过期',command_invalid:'尚未接管有效驾驶意图',risk_stop:'风险核当前要求停车',intent_expired_or_missing:'等待新的驾驶意图',STM32_latched:'STM32 已锁车',PL_perception_denied:'感知条件不允许驾驶'};
 const steps=[
  ['系统介绍','介绍 PYNQ 的实时感知和 AR 处理、PS 的管理与传输、STM32 的底盘执行。','展示同一页面中的视频、仪表与实际锁车反馈。'],
  ['实时感知','观察距离、左右红外、双轮编码器、速度与里程。','遮挡再移开左右红外；手转测量轮时观察真实计数。'],
  ['AR 画面对比','切换摄像头原图和真实 PL 处理图，再冻结同一帧进行比较。','说明历史画面中的数据不用于当前车辆控制。'],
  ['手动操控','完成标定与安全条件检查后，接管、手动解锁，再按住方向键。','松手停车；实际 PWM 和 LOCK 以 STM32 回包为准。'],
  ['安全响应','分别演示红外遮挡告警、超声波前方障碍停车，以及失焦停车。','红外只提示；流程按钮不会自动驱动车辆，需要操作者现场执行。'],
  ['结果展示','结束记录并导出会话数据、联调报告与演示摘要。','软件演示完成和整车实物验收分别记录。']
 ];
 function info(text,bad=false){$('driveReadiness').textContent=text;$('driveReadiness').className=bad?'notice bad':'muted';}
 function download(name,value,type='application/json'){const blob=new Blob([typeof value==='string'?value:JSON.stringify(value,null,2)],{type});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 function event(name,detail){events.unshift({time:new Date().toLocaleTimeString('zh-CN',{hour12:false}),name,detail:String(detail)});events=events.slice(0,200);$('eventRows').replaceChildren(...events.map(e=>{const tr=document.createElement('tr');for(const v of [e.time,e.name,e.detail]){const td=document.createElement('td');td.textContent=v;tr.append(td);}return tr;}));}
 function fresh(){return !replay&&state?.running===true&&state?.telemetry_fresh===true&&performance.now()-updated<750&&connected&&lastSnapshot!==null;}
 function clearDrive(){held=null;press=null;document.querySelectorAll('[data-drive]').forEach(b=>b.classList.remove('active'));}
 function drive(direction,identity){if(!fresh()||!claimed||!synced||!state.console?.motion_ready||held)return;held=direction;press=identity;document.querySelector(`[data-drive=${direction}]`)?.classList.add('active');}
 function intent(){if(!held)return [0,0];if(!fresh()||!claimed||!state.console?.motion_ready){stop();return [0,0];}const limit=Math.min(400,state.console?.pwm_limit||0),p=Math.max(0,Math.min(limit,Number($('drivePwm').value)||0));return ({w:[p,p],s:[-p,-p],a:[0,p],d:[p,0]})[held]||[0,0];}
 function controls(){const live=fresh(),c=state?.console;
  for(const id of ['raw','processed','freeze','mode','fps','quality','apply'])$(id).disabled=!connected||!!replay;
  $('claim').disabled=!live||!synced||claimed||state?.control_available===false;
  $('release').disabled=!(live&&claimed&&synced&&c?.release_ready);
  $('setDriveMode').disabled=!live||!c?.motion_supported;
  $('driveMode').disabled=!live||!c?.motion_supported;
  $('calStart').disabled=!live;$('calEnd').disabled=!live||!calStart;
  $('calApply').disabled=!live||!calibration||state?.motor_disconnected!==true||c?.mode!=='observe';
  $('motorApply').disabled=!live||!c;
  $('recordStart').disabled=!live||recording;$('recordStop').disabled=!recording;
  $('recordJson').disabled=$('recordCsv').disabled=!rows.length;
  document.querySelectorAll('[data-drive]').forEach(b=>b.disabled=!(live&&claimed&&synced&&c?.motion_ready));
  if(!live||!c?.motion_ready){if(held)stop();clearDrive();}
 }
 function render(s,{historical=false}={}){state=s;updated=performance.now();const a=s.latest?.status||{},c=s.latest?.control||{},conf=s.console||{},live=s.running===true&&s.telemetry_fresh===true;
  const ir=a.infrared,irKnown=live&&ir?.valid===true,mask=irKnown?ir.mask:0;
  $('infraredNotice').className='notice'+(!irKnown||mask?' warn':'');
  $('infraredNotice').textContent=(historical?'历史记录 · ':'')+(irKnown?(mask?'红外障碍告警：'+(mask===3?'左右两侧':mask===1?'左侧':'右侧'):'红外未检测到障碍'):'红外数据未知或已失效')+' · 仅提示，不参与停车和解锁判断';
  $('sourceLabel').textContent=historical?'历史回放 · 控制已撤销':live?(s.hardware===false?'本地验证数据 · 非实车':'实车数据 · 当前会话'):'连接中断 · 等待新鲜回传';
  $('offlineBar').className='notice '+(historical||!live?'warn':'');
  $('speedMain').textContent=live&&a.speed_valid&&Number.isFinite(a.speed_mm_s)?a.speed_mm_s.toFixed(1)+' mm/s':'— mm/s';
  $('travelMain').textContent=live&&a.odometry_valid&&Number.isFinite(a.travelled_mm)?a.travelled_mm.toFixed(1)+' mm':'— mm';
  $('displacementMain').textContent=live&&a.odometry_valid&&Number.isFinite(a.displacement_mm)?a.displacement_mm.toFixed(1)+' mm':'— mm';
  const risk=live&&Number.isInteger(a.risk_level)?a.risk_level:null;
  $('riskMain').textContent=risk===null?'未知':['安全','注意','紧急','数据无效'][risk]||'未知';$('riskMain').className=risk===0?'risk-good':risk===1?'risk-warn':risk===null?'':'risk-bad';
  const r=[...(conf.blockers||[]),...(c.decision_reasons||[]).map(x=>reasons[x]||x)];
  $('riskExplain').textContent=live?(r.length?[...new Set(r)].join(' · '):'当前感知数据有效，实际执行状态以 STM32 为准'):'等待本次会话的有效测量';
  $('motionBadge').textContent=historical?'历史回放':conf.mode==='manual'?'手动驾驶':s.control_available===false?'仅视频':'仅观察';
  $('scopeBadge').textContent=historical?'记录回放':live?'实时会话':'未连接';
  $('driveMode').value=conf.mode||'observe';
  const phase=c.phase==='ARMED'?'已解锁，可按住方向键':c.phase==='WAIT_UNLOCK'?'等待 STM32 实际解锁反馈':'已锁车';
  info(historical?'历史回放不开放控制':conf.operator_error||conf.fault||(!conf.motion_supported?'当前板端服务未开放驾驶；完整操控需部署配套控制服务':phase+(r.length?' · '+[...new Set(r)].join(' · '):'')),Boolean(conf.fault));
  $('keys').textContent=conf.mode==='manual'?'WASD 或按住方向按钮；松手／失焦／断链即停车。首轮限速由板端执行，单次最长 '+(conf.max_burst_s||1)+' 秒。':'仅观察模式可以查看视频和传感器。驾驶需有效实测标定、实际锁车反馈及手动解锁。';
  $('calState').textContent=`动力${s.motor_disconnected===true?'已断开':s.motor_disconnected===false?'已连接':'状态未知'} · SCALE ${conf.scales?.join(' / ')||'未回读'} · ${conf.calibration_measured?'已加载实测标定':'等待实测标定'}`;
  if(document.activeElement!==$('motorPhysical'))$('motorPhysical').value=s.motor_disconnected?'disconnected':'connected';
  const action=conf.action||s.action;if(action)$('calResult').textContent=action.applied===false?'操作未完成：'+(action.error||'请查看诊断'):action.applied?'操作已应用并记录':'';
  const key=JSON.stringify([c.phase,a.car?.lock,a.car?.fault,a.risk_level,conf.mode,conf.fault,s.telemetry_fresh]);
  if(!historical&&key!==eventKey){eventKey=key;event('状态变化',`${phase} · ${$('riskMain').textContent} · ${conf.mode==='manual'?'手动驾驶':'仅观察'}`);}
  if(!historical){history.push({at:Date.now(),distance:live&&a.distance_valid?a.distance_mm:null,speed:live&&a.speed_valid?a.speed_mm_s:null});history=history.filter(v=>v.at>Date.now()-60000).slice(-150);
   if(recording){const row={observed_at:new Date().toISOString(),state:s},size=JSON.stringify(row).length;if(rows.length>=4000||bytes+size>24*1024*1024){recording=false;event('记录结束','已达到本地容量上限，请导出保存');}else{rows.push(row);bytes+=size;}recordLabel();}
  }
  drawCharts();controls();renderDemo();
 }
 function disconnected(message='尚未连接小车'){state=null;updated=0;clearDrive();$('infraredNotice').textContent='红外数据未知 · 仅提示，不参与停车和解锁判断';$('infraredNotice').className='notice';$('sourceLabel').textContent='未连接小车 · 当前没有实测数据';$('connection').textContent='离线查看 · 尚未连接小车';$('keys').textContent='连接后可查看视频与传感器；具备实测标定和驾驶条件后手动接管。';$('calState').textContent='未连接 · 等待板端标定信息';$('offlineBar').className='notice';for(const id of ['speedMain','travelMain','displacementMain'])$(id).textContent='—';$('riskMain').textContent='未知';$('riskExplain').textContent=message;$('motionBadge').textContent='未连接';$('scopeBadge').textContent='离线查看';info('连接后核对实际传感器、标定和执行器状态');if(recording){recording=false;event('记录暂停','连接已中断，已保留已采集的数据');recordLabel();}controls();drawCharts();}
 function draw(canvas,key,label){const ctx=canvas.getContext('2d'),w=canvas.width,h=canvas.height;ctx.clearRect(0,0,w,h);ctx.fillStyle='#f7fafc';ctx.fillRect(0,0,w,h);ctx.font='13px Microsoft YaHei';ctx.strokeStyle='#dce5ed';ctx.fillStyle='#607083';const valid=history.map(v=>v[key]).filter(Number.isFinite),lo=Math.min(0,...valid),hi=Math.max(1,...valid),span=hi-lo;for(let n=0;n<4;n++){const y=18+n*(h-46)/3;ctx.beginPath();ctx.moveTo(50,y);ctx.lineTo(w-12,y);ctx.stroke();ctx.fillText((hi-n*span/3).toFixed(0),5,y+4);}ctx.fillText(valid.length?'60 秒前                                        现在':'等待有效实测数据',50,h-8);ctx.strokeStyle=key==='distance'?'#087e8b':'#1559a6';ctx.lineWidth=2;ctx.beginPath();let pen=false;const end=Date.now();for(const point of history){const value=point[key];if(!Number.isFinite(value)){pen=false;continue;}const x=50+(w-62)*(point.at-(end-60000))/60000,y=18+(hi-value)/span*(h-46);if(pen)ctx.lineTo(x,y);else ctx.moveTo(x,y);pen=true;}ctx.stroke();}
 function drawCharts(){draw($('distanceTrend'),'distance');draw($('speedTrend'),'speed');}
 function recordLabel(){$('recordState').replaceChildren();const dot=document.createElement('i');dot.className='record-dot'+(recording?' on':'');$('recordState').append(dot,document.createTextNode(recording?'正在记录':'未记录'));$('recordInfo').textContent=`本地保留 ${rows.length} 条观察 · ${(bytes/1024/1024).toFixed(2)} MB · 不包含连接令牌`;controls();}
 function recordingPayload(){return {schema:'car-console-recording/v1',exported_at:new Date().toISOString(),source:'actual-session-observations',scope:'观察记录，不等同于整车验收',rows};}
 function startRecord(){if(!fresh()||recording)return;if(rows.length)download('小车上一段记录-'+Date.now()+'.json',recordingPayload());rows=[];bytes=0;recording=true;event('开始记录','本次实际会话');recordLabel();}
 function setTab(next){if(claimed)stop();tab=next;document.body.dataset.tab=tab;document.querySelectorAll('.console-nav [data-tab]').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));const show=(node,tabs)=>node?.classList.toggle('hidden-panel',!tabs.includes(tab));
  show($('driveSummary'),['overview','demo']);show($('trends'),['overview']);
  for(const name of ['calibrationPanel'])show($(name),['sensors']);
  for(const name of ['recordPanel','eventPanel'])show($(name),['records']);show($('demoPanel'),['demo']);
  document.querySelectorAll('[data-console-panel]').forEach(p=>show(p,p.dataset.consolePanel.split(' ')));drawCharts();
 }
 function tagPanels(){const find=title=>[...document.querySelectorAll('#consoleView section')].find(s=>s.querySelector('h2')?.textContent===title);const tags={'实时状态':'overview demo','摄像头与 PL 处理画面':'overview demo','传感器通道':'sensors','完整传感器联调':'sensors','STM32 串口链路':'sensors','手动操控':'overview demo','运动显示':'sensors'};for(const [name,tabs] of Object.entries(tags)){const p=find(name);if(p)p.dataset.consolePanel=tabs;}const diagnostics=$('status').closest('section');diagnostics.dataset.consolePanel='records';diagnostics.classList.add('advanced');}
 function renderDemo(){const [title,desc,note]=steps[demoIndex];$('demoCard').replaceChildren();const h=document.createElement('h3'),p=document.createElement('p'),small=document.createElement('p');h.textContent=`${demoIndex+1} / ${steps.length} · ${title}`;p.textContent=desc;small.textContent=note;small.className='muted';$('demoCard').append(h,p,small);$('demoPrev').disabled=demoIndex===0;$('demoNext').disabled=demoIndex===steps.length-1;[...$('demoSteps').children].forEach((b,i)=>b.classList.toggle('active',i===demoIndex));}
 function getCounts(){const a=state?.latest?.status,e=a?.encoder,cfg=state?.console?.qei_configuration;if(!fresh()||!e||!Number.isInteger(e.left?.position)||!Number.isInteger(e.right?.position))throw Error('需要新鲜的双轮实际计数');for(const wheel of [e.left,e.right])if((wheel.faults||[]).some(v=>/illegal|overflow|saturat|odometry/i.test(v)))throw Error('编码器有非法跳变或溢出，请先排除输入异常');if(!cfg||cfg.length!==2)throw Error('需要板端当前编码器方向与滤波配置');return {counts:[e.left.position,e.right.position],at:new Date().toISOString(),epoch:state.latest?.control?.epoch,configuration:structuredClone(cfg),session:a.stm32_link?.session_hex};}
 function calibrationFile(item){if(item?.schema!=='car-wheel-calibration/v1'||item.measured!==true||typeof item.provenance!=='string'||!item.provenance.trim())throw Error('需要带实测来源的有效双轮标定文件');if(item.contract_version!==11||item.channel_map?.left!=='QEI0_left_front'||item.channel_map?.right!=='QEI1_right_front')throw Error('标定协议版本或左右轮映射不匹配');for(const name of ['left','right']){const w=item[name];if(!Number.isInteger(w?.scale)||w.scale<1||w.scale>0xffffffff||![0,1].includes(w.direction)||!Number.isInteger(w.filter_ticks)||w.filter_ticks<0||w.filter_ticks>1000000||!Number.isInteger(w.zero_ticks)||w.zero_ticks<66||w.zero_ticks>19000000)throw Error('轮尺度、方向或滤波参数无效');}calibration=item;$('calDownload').disabled=false;controls();$('calResult').textContent='标定文件已就绪，尚未写入板卡';}
 async function action(path,value,target='calResult'){if(!fresh()){$(target).textContent='请先连接小车并取得新鲜反馈';return;}try{stop();const answer=await(await api(path,value)).json();$(target).textContent=answer.queued?'已提交，等待板端处理':'操作完成';}catch(e){$(target).textContent=e.message;}}
 function replayRender(){if(!replay)return;const row=replay.rows[replayIndex],s=row.state;renderHealth(s);renderSensors(s);renderLink(s);renderMotion(s.latest?.status||{},s.telemetry_fresh===true);renderInterconnect(s.interconnect_test);render(s,{historical:true});$('replayPosition').value=replayIndex;$('replayTime').textContent=`${replayIndex+1} / ${replay.rows.length} · ${row.observed_at}`;}
 function replayStop(){clearInterval(replayTimer);replayTimer=null;$('replayPlay').textContent='播放';}
 async function enterReplay(file){if(file.size>32*1024*1024)throw Error('回放文件上限为 32MB');const item=JSON.parse(await file.text());if(item.schema!=='car-console-recording/v1'||!Array.isArray(item.rows)||!item.rows.length||item.rows.length>4000||item.rows.some(r=>!r||typeof r.observed_at!=='string'||!r.state||typeof r.state!=='object'||!r.state.latest||typeof r.state.latest!=='object'))throw Error('不是有效的控制台记录文件');stop();closeSocket();allowWebSocket=false;connected=false;sessionGeneration++;player?.stop();clearVideo('历史数据回放 · 视频暂停');replay=item;replayIndex=0;replayStop();$('replayTools').hidden=false;$('replayPosition').max=item.rows.length-1;recording=false;setTab('records');replayRender();event('进入回放','已撤销控制，历史数据不可解锁或运动');}
 window.ConsoleApp={render,disconnected,clearDrive,intent,get isPlayback(){return replay!==null;}};
 document.querySelectorAll('[data-drive]').forEach(b=>{b.addEventListener('pointerdown',e=>{e.preventDefault();if(b.disabled)return;b.setPointerCapture(e.pointerId);drive(b.dataset.drive,e.pointerId);});for(const kind of ['pointerup','pointercancel','lostpointercapture'])b.addEventListener(kind,e=>{if(press===e.pointerId)stop();});});
 window.addEventListener('keydown',e=>{if(e.target?.closest('input,textarea,select,[contenteditable]'))return;const key=e.key.toLowerCase();if(key.length===1&&'wasd'.includes(key)){e.preventDefault();if(!e.repeat)drive(key,e.code);}});
 window.addEventListener('keyup',e=>{if(press===e.code)stop();});
 for(const id of ['globalStop','padStop'])$(id).onclick=()=>stop();
 $('release').onclick=()=>{if(fresh()&&claimed&&state.console?.release_ready)send({type:'release',seq:++seq,client_ms:performance.now()});};
 $('drivePwm').oninput=()=>{$('drivePwmValue').textContent=$('drivePwm').value;};
 $('setDriveMode').onclick=()=>action('/api/console/mode',{mode:$('driveMode').value},'driveReadiness');
 $('motorApply').onclick=()=>{if(!$('motorConfirmed').checked){$('calResult').textContent='请先核对并勾选物理连接状态';return;}action('/api/console/motor-state',{disconnected:$('motorPhysical').value==='disconnected',confirmed:true});$('motorConfirmed').checked=false;};
 $('connectionSettings').onclick=()=>{$('connectView').hidden=false;$('connectView').scrollIntoView({block:'start'});};
 $('present').onclick=()=>{presenting=!presenting;document.body.classList.toggle('presenting',presenting);$('present').textContent=presenting?'退出演示视图':'演示视图';setTab('demo');};
 document.querySelectorAll('.console-nav [data-tab]').forEach(b=>b.onclick=()=>setTab(b.dataset.tab));
 $('recordStart').onclick=startRecord;$('recordStop').onclick=()=>{recording=false;event('结束记录',`${rows.length} 条观察`);recordLabel();};
 $('recordJson').onclick=()=>download('小车会话-'+Date.now()+'.json',recordingPayload());
 $('recordCsv').onclick=()=>{const table=[['observed_at','epoch','distance_mm','distance_valid','speed_mm_s','speed_valid','travelled_mm','risk_level','actual_lock','actual_left_pwm','actual_right_pwm','car_valid']];for(const row of rows){const a=row.state.latest?.status||{},c=a.car_valid?a.car:null;table.push([row.observed_at,a.epoch,a.distance_valid?a.distance_mm:'',a.distance_valid,a.speed_valid?a.speed_mm_s:'',a.speed_valid,a.odometry_valid?a.travelled_mm:'',a.risk_level,c?.lock??'',c?.left??'',c?.right??'',a.car_valid]);}download('小车数据-'+Date.now()+'.csv','\ufeff'+table.map(r=>r.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\r\n'),'text/csv;charset=utf-8');};
 $('replayFile').onchange=async e=>{try{if(e.target.files[0])await enterReplay(e.target.files[0]);}catch(err){$('recordInfo').textContent=err.message;}e.target.value='';};
 $('replayPosition').oninput=()=>{replayStop();replayIndex=Number($('replayPosition').value);replayRender();};
 $('replayPlay').onclick=()=>{if(replayTimer){replayStop();return;}if(!replay)return;$('replayPlay').textContent='暂停';replayTimer=setInterval(()=>{if(replayIndex>=replay.rows.length-1){replayStop();return;}replayIndex++;replayRender();},500);};
 $('replayExit').onclick=async()=>{replayStop();replay=null;$('replayTools').hidden=true;disconnected('已退出回放');try{await enterConsole();}catch(e){showConnection('请重新连接实时会话：'+e.message);}};
 $('calStart').onclick=()=>{try{calStart=getCounts();calFinish=null;$('calCounts').textContent='起点 '+calStart.counts.join(' / ')+' count';controls();}catch(e){$('calResult').textContent=e.message;}};
 $('calEnd').onclick=()=>{try{calFinish=getCounts();if(calStart.epoch>calFinish.epoch||calStart.session!==calFinish.session||JSON.stringify(calStart.configuration)!==JSON.stringify(calFinish.configuration))throw Error('采样会话或配置发生变化，请重新测量');$('calCounts').textContent='计数变化 '+calFinish.counts.map((v,i)=>v-calStart.counts[i]).join(' / ')+' count';}catch(e){calFinish=null;$('calResult').textContent=e.message;}};
 $('calCompute').onclick=()=>{try{if(!calStart||!calFinish||!$('calMeasured').checked)throw Error('请完成起终点记录并确认实测来源');const distance=Number($('calDistance').value),delta=calFinish.counts.map((v,i)=>v-calStart.counts[i]);if(!Number.isFinite(distance)||distance<=0||delta.some(v=>!v||Math.abs(v)>1e9))throw Error('需要正的实测距离以及双轮非零有效计数');const wheels=delta.map((v,i)=>({scale:Math.round(distance/Math.abs(v)*65536),direction:calStart.configuration[i].dir^(v<0?1:0),filter_ticks:calStart.configuration[i].filter,zero_ticks:calStart.configuration[i].zero}));const contract=state?.identity?.calibration?.contract_version??11;calibrationFile({schema:'car-wheel-calibration/v1',contract_version:contract,channel_map:{left:'QEI0_left_front',right:'QEI1_right_front'},left:wheels[0],right:wheels[1],measured:true,provenance:`人工尺量向前推动 ${distance} mm；起点 ${calStart.counts}；终点 ${calFinish.counts}；${calStart.at} 至 ${calFinish.at}`});}catch(e){$('calResult').textContent=e.message;}};
 $('calFile').onchange=async e=>{try{const file=e.target.files[0];if(!file)return;if(file.size>16384)throw Error('标定文件过大');calibrationFile(JSON.parse(await file.text()));}catch(err){calibration=null;$('calResult').textContent=err.message;controls();}e.target.value='';};
 $('calDownload').onclick=()=>{if(calibration)download('双轮实测标定-'+Date.now()+'.json',calibration);};
 $('calApply').onclick=()=>{if(calibration)action('/api/calibration',calibration);};
 steps.forEach(([title],i)=>{const b=document.createElement('button');b.textContent=(i+1)+' '+title;b.onclick=()=>{demoIndex=i;renderDemo();};$('demoSteps').append(b);});
 $('demoPrev').onclick=()=>{demoIndex=Math.max(0,demoIndex-1);renderDemo();};$('demoNext').onclick=()=>{demoIndex=Math.min(steps.length-1,demoIndex+1);renderDemo();};
 $('demoRecord').onclick=()=>{startRecord();$('demoRecord').textContent=recording?'演示记录中':'需要先连接实际会话';};
 $('demoExport').onclick=()=>download('小车演示摘要-'+Date.now()+'.json',{schema:'car-demo-observation/v1',exported_at:new Date().toISOString(),step:demoIndex+1,steps:steps.map(s=>s[0]),events,observation_count:rows.length,latest:state,scope:'演示观察记录，不是整车验收证明'});
 $('demoFullscreen').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch(e){event('全屏不可用',e.message);}};
 if(location.hostname==='127.0.0.1'){$('desktopConnect').hidden=false;$('desktopConnect').onclick=async()=>{try{const r=await fetch('/api/desktop/connect',{method:'POST'});if(!r.ok)throw Error('无法启动连接助手');$('sourceLabel').textContent='已打开连接助手；由你选择连接，当前页面保留离线查看';}catch(e){$('sourceLabel').textContent=e.message;}};setInterval(()=>fetch('/api/desktop/ping',{method:'POST'}).catch(()=>{}),10000);}
 window.addEventListener('DOMContentLoaded',async()=>{tagPanels();setTab('overview');renderDemo();drawCharts();controls();setInterval(controls,250);if(location.hostname==='127.0.0.1'){try{const r=await fetch('/api/desktop/info');if(r.ok&&(await r.json()).kind==='car-console-desktop/v1'){$('serverAddress').value='http://192.168.8.139:8080';$('connectView').hidden=true;}}catch{}}});
})();
