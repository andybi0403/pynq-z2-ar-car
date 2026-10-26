"""Actual page renderer must redact stale/missing physical feedback."""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

@unittest.skipUnless(shutil.which('node'), 'Node unavailable')
class ConsoleHealthTests(unittest.TestCase):
    def test_connection_gate_precedes_console(self):
        text=(Path(__file__).resolve().parents[1]/'host/wireless_page.html').read_text('utf8')
        self.assertLess(text.index('id="connectView"'),text.index('id="consoleView"'))
        self.assertIn('id="consoleView" hidden',text)
        self.assertIn('id="connectForm"',text)
        self.assertIn('id="serverAddress"',text)
        self.assertIn('id="sessionToken"',text)
        self.assertIn("request('/api/session'",text)
        self.assertIn('/api/session/logout',text)

    def test_feedback_expiry_and_capture_error_are_distinct(self):
        text=(Path(__file__).resolve().parents[1]/'host/wireless_page.html').read_text('utf8')
        start=text.index('function renderHealth(')
        end=text.index('function renderSensors(',start)
        renderer=text[start:end]
        script="const assert=require('node:assert/strict');const elements={};const el=id=>elements[id]??={};const setPill=(node,text,kind='')=>{node.textContent=text;node.className='pill '+kind;};const finite=v=>Number.isFinite(v)?v:null;\n"+renderer+r'''
const live={running:true,telemetry_fresh:true,control_available:true,latest:{status:{distance_valid:true,distance_mm:321,car_valid:true,car:{lock:1,left:0,right:0,fault:1},stm32_link:{link_fresh:true,sensor:{us_age_ms:12}}}},video:{fps_since_start:{captured:12}}};
renderHealth(live);assert.equal(el('distanceCard').textContent,'321 mm');assert.equal(el('lockCard').textContent,'已锁车');assert.equal(el('leftPwmCard').textContent,'0');assert.match(el('cameraHealth').textContent,/实际采集/);assert.match(el('uartHealth').textContent,/回包新鲜/);
renderHealth({...live,telemetry_fresh:false});assert.equal(el('distanceCard').textContent,'—');assert.equal(el('leftPwmCard').textContent,'—');assert.equal(el('lockCard').textContent,'未收到');
renderHealth({...live,video:{error:'device busy'}});assert.match(el('cameraHealth').textContent,/device busy/);assert.doesNotMatch(el('cameraHealth').textContent,/未连接/);
renderHealth({...live,latest:{status:{distance_valid:true,car_valid:true}}});assert.equal(el('distanceCard').textContent,'—');assert.equal(el('lockCard').textContent,'未收到');
renderHealth({...live,control_available:false,latest:{status:{}}});assert.match(el('uartHealth').textContent,/未采集 STM32/);assert.equal(el('leftPwmCard').textContent,'—');
renderHealth({...live,latest:{status:{stm32_link:{resync_pending:true,query_tx_count:30}}}});assert.equal(el('uartRecoveryHint').hidden,false);assert.equal(el('uartWiringHint').hidden,true);assert.equal(el('lockCard').textContent,'未收到');
renderHealth({...live,latest:{status:{...live.latest.status,stm32_link:{link_fresh:true,locked_resync_count:1}}}});assert.match(el('uartRecoveryHint').textContent,/不通过稳定验收/);assert.equal(el('lockCard').textContent,'已锁车');
renderHealth({});assert.equal(el('distanceCard').textContent,'—');assert.equal(el('lockCard').textContent,'未收到');
assert.equal(el('uartRecoveryHint').hidden,true);
console.log('PASS');
'''
        result=subprocess.run(['node','-e',script],capture_output=True,text=True,encoding='utf8',timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
