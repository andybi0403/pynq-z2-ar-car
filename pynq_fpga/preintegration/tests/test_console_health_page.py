"""Actual page renderer must redact stale/missing physical feedback."""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

@unittest.skipUnless(shutil.which('node'), 'Node unavailable')
class ConsoleHealthTests(unittest.TestCase):
    def test_feedback_expiry_and_capture_error_are_distinct(self):
        text=(Path(__file__).resolve().parents[1]/'host/wireless_page.html').read_text('utf8')
        renderer=next(line for line in text.splitlines() if line.startswith('function renderHealth('))
        script="const assert=require('node:assert/strict');const elements={};const el=id=>elements[id]??={};\n"+renderer+r'''
const live={running:true,telemetry_fresh:true,latest:{status:{distance_valid:true,distance_mm:321,car_valid:true,car:{lock:1,left:0,right:0},speed_valid:false}},video:{fps_since_start:{captured:12}}};
renderHealth(live);assert.equal(el('distanceCard').textContent,'321 mm');assert.equal(el('lockCard').textContent,'已锁车');assert.equal(el('leftPwmCard').textContent,'0');assert.match(el('cameraHealth').textContent,/实际采集/);
renderHealth({...live,telemetry_fresh:false});assert.equal(el('distanceCard').textContent,'—');assert.equal(el('leftPwmCard').textContent,'—');assert.equal(el('lockCard').textContent,'未收到');
renderHealth({...live,video:{error:'device busy'}});assert.match(el('cameraHealth').textContent,/device busy/);assert.doesNotMatch(el('cameraHealth').textContent,/未连接/);
renderHealth({...live,latest:{status:{distance_valid:true,car_valid:true}}});assert.equal(el('distanceCard').textContent,'—');assert.equal(el('lockCard').textContent,'未收到');
renderHealth({...live,control_available:false,latest:{status:{}}});assert.match(el('uartHealth').textContent,/未采集 STM32/);assert.equal(el('leftPwmCard').textContent,'—');
renderHealth({});assert.equal(el('distanceCard').textContent,'—');assert.equal(el('lockCard').textContent,'未收到');
console.log('PASS');
'''
        result=subprocess.run(['node','-e',script],capture_output=True,text=True,encoding='utf8',timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
