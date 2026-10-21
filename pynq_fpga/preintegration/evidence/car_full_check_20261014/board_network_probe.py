"""Read-only router reachability and PHY check from the already connected board."""
from pathlib import Path
import json
import subprocess
import urllib.request

facts={'kind':'BOARD_ROUTER_REACHABILITY','hardware':True}
for name in ('carrier','operstate','address'):
    path=Path('/sys/class/net/eth0')/name
    facts[name]=path.read_text().strip() if path.exists() else None
facts['commands']=[]
for args in (['ip','route'],['ip','neigh'],['ping','-c','2','-W','1','192.168.8.1'],['ethtool','eth0']):
    try:
        run=subprocess.run(args,capture_output=True,text=True,timeout=5)
        facts['commands'].append({'argv':args,'code':run.returncode,'stdout':run.stdout,'stderr':run.stderr})
    except Exception as exc:facts['commands'].append({'argv':args,'error':repr(exc)})
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
for path in ('/','/cgi-bin/api/router/hello'):
    try:
        with opener.open('http://192.168.8.1'+path,timeout=3) as response:
            facts[path]={'code':response.status,'body':response.read(18000).decode('utf8','replace')}
    except Exception as exc:facts[path]={'error':repr(exc)}
print(json.dumps(facts))
