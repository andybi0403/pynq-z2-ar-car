"""Read service exit evidence before starting another diagnostic session."""
import json,re,shlex,time
from car_network_probe import wifi,cmd,join_car,connect_board,OUT,clean
from car_deploy_console import run,PYTHON,REMOTE

def main():
    original=re.search(r'^\s*Profile\s*:\s*(.+)$',wifi(),re.M).group(1).strip()
    facts={};client=None
    try:
        facts['profile']=join_car();client=connect_board('192.168.8.139')
        facts['service']=run(client,'systemctl show pynq-car-console.service -p ActiveState -p SubState -p Result -p ExecMainStatus -p NRestarts -p InvocationID')
        facts['journal']=run(client,'journalctl -u pynq-car-console.service -n 100 --no-pager -o cat',root=True)
        source=f'''from pathlib import Path
import json
root=Path({REMOTE!r})/'evidence'
dirs=sorted(root.glob('sensor_console_*'),key=lambda p:p.stat().st_mtime)
out={{}}
for d in dirs[-3:]:
 out[d.name]={{p.name:json.loads(p.read_text()) for p in d.glob('*summary.json')}}
print(json.dumps(out))
'''
        facts['summaries']=run(client,shlex.quote(PYTHON)+' -c '+shlex.quote(source),root=True)
    except Exception as exc:facts['error']=clean(str(exc))
    finally:
        if client:client.close()
        facts={k:({a:clean(b) if isinstance(b,str) else b for a,b in v.items()} if isinstance(v,dict) else v) for k,v in facts.items()}
        cmd(['netsh','wlan','connect','name='+original,'interface=WLAN 2']);time.sleep(4)
        (OUT/'service-failure.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2),'utf8')
        print('SERVICE_EVIDENCE_SAVED',facts.get('error'),facts.get('service'))

if __name__=='__main__':main()
