"""Execute the shipped renderer, including estimated values and stale status."""
import json,re,shutil,subprocess,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from status_server import PAGE

class DisplayPageTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'),'Node is unavailable')
    def test_wired_renderer_uses_estimated_field_without_changing_raw_validity(self):
        script=re.search(r'function number\(.*?\nconst displayModes=.*?\nfunction motionCards\(.*?\n',PAGE,re.S).group()
        payload={'speed_valid':False,'speed_mm_s':None,'odometry_valid':False,
                 'motion_display':{'available':True,'speed_mm_s':0,'travelled_mm':0,'displacement_mm':0,'mode':'stationary_assumption'}}
        js=script+'\nconst s='+json.dumps(payload)+';console.log(JSON.stringify(motionCards(s)));'
        r=subprocess.run(['node','-e',js],capture_output=True,text=True,encoding='utf8',timeout=10)
        self.assertEqual(r.returncode,0,r.stderr)
        values=json.loads(r.stdout)
        self.assertEqual(values[0],['轮速','0.00 mm/s'])
        self.assertEqual(values[-1],['显示状态','静止展示'])

    @unittest.skipUnless(shutil.which('node'),'Node is unavailable')
    def test_wireless_renderer_removes_numbers_when_telemetry_stalls(self):
        page=Path(__file__).resolve().parents[1]/'host/wireless_page.html'
        text=page.read_text('utf8')
        script=re.search(r'const displayModes=.*?\nfunction renderMotion\(.*?\n',text,re.S).group()
        js="const elements={motionNumbers:{},motionMode:{}};const el=id=>elements[id];\n"+script
        js+="renderMotion({motion_display:{available:true,speed_mm_s:0,travelled_mm:0,displacement_mm:0,mode:'stationary_assumption'}},true);const good=elements.motionNumbers.textContent;renderMotion({},false);console.log(JSON.stringify({good,stale:elements.motionNumbers.textContent}));"
        r=subprocess.run(['node','-e',js],capture_output=True,text=True,encoding='utf8',timeout=10)
        self.assertEqual(r.returncode,0,r.stderr)
        result=json.loads(r.stdout)
        self.assertIn('轮速 0.00',result['good'])
        self.assertEqual(result['stale'],'显示暂不可用')

if __name__=='__main__':unittest.main()
