"""Open the complete console locally. Network connection is an explicit action."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
HOST=ROOT/'pynq_fpga/preintegration/host'
OUT=ROOT/'work/desktop_console'
FILES={'/':('wireless_page.html','text/html; charset=utf-8'),
       '/assets/console_ui.js':('console_ui.js','application/javascript; charset=utf-8'),
       '/assets/wireless_player.js':('wireless_player.js','application/javascript; charset=utf-8')}


def hidden():
    return {'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}


def open_edge(url):
    candidates=[Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe',
                Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Microsoft/Edge/Application/msedge.exe']
    edge=next((p for p in candidates if p.is_file()),None)
    if edge is None:raise FileNotFoundError('Microsoft Edge not found')
    subprocess.Popen([str(edge),'--user-data-dir='+str(OUT/'edge-profile'),'--no-proxy-server','--app='+url],
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**hidden())


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*_):pass

    def reply(self,status,value,kind='application/json; charset=utf-8'):
        data=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode('utf8')
        self.send_response(status)
        self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        try:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):pass

    def allowed(self,mutating=False):
        host='127.0.0.1:'+str(self.server.server_port)
        if self.headers.get('Host')!=host or (mutating and self.headers.get('Origin')!='http://'+host):
            self.reply(403,{'error':'local origin required'});return False
        return True

    def do_GET(self):
        if not self.allowed():return
        path=self.path.split('?',1)[0]
        if path in FILES:
            name,kind=FILES[path]
            self.server.last_seen=time.monotonic()
            return self.reply(200,(HOST/name).read_bytes(),kind)
        if path=='/api/desktop/info':
            return self.reply(200,{'kind':'car-console-desktop/v1','pid':os.getpid(),'network_auto_connect':False})
        if path.startswith('/api/'):
            return self.reply(401,{'error':'小车尚未连接；当前可离线查看完整控制台'})
        return self.reply(404,{'error':'not found'})

    def do_POST(self):
        if not self.allowed(mutating=True):return
        if self.path=='/api/desktop/ping':
            self.server.last_seen=time.monotonic()
            return self.reply(200,{'alive':True})
        if self.path=='/api/desktop/connect':
            python=Path(sys.executable).with_name('pythonw.exe') if os.name=='nt' else Path(sys.executable)
            subprocess.Popen([str(python),'-X','utf8',str(ROOT/'tools/connect_car_console.py')],cwd=ROOT,
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,**hidden())
            return self.reply(202,{'opened':True,'network_action':'explicit user click'})
        return self.reply(401,{'error':'小车尚未连接'})


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--no-open',action='store_true')
    p.add_argument('--port',type=int,default=0)
    args=p.parse_args(argv)
    OUT.mkdir(parents=True,exist_ok=True)
    instance=OUT/'instance.json'
    if not args.no_open and instance.exists():
        try:
            old=json.loads(instance.read_text('utf8'));url='http://127.0.0.1:'+str(int(old['port']))+'/'
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(url+'api/desktop/info',timeout=.5) as r:info=json.load(r)
            if info.get('kind')=='car-console-desktop/v1' and info.get('pid')==old['pid']:
                open_edge(url);return 0
        except (OSError,ValueError,KeyError):pass
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.daemon_threads=True
    server.last_seen=time.monotonic()
    url='http://127.0.0.1:'+str(server.server_port)+'/'
    instance.write_text(json.dumps({'pid':os.getpid(),'port':server.server_port,'url':url}), 'utf8')
    if sys.stdout:print(url,flush=True)
    def expiry():
        while time.monotonic()-server.last_seen<90:time.sleep(5)
        server.shutdown()
    threading.Thread(target=expiry,daemon=True).start()
    try:
        if not args.no_open:open_edge(url)
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:pass
    finally:
        server.server_close()
        try:
            if json.loads(instance.read_text('utf8')).get('pid')==os.getpid():instance.unlink()
        except (OSError,ValueError):pass
    return 0


if __name__=='__main__':raise SystemExit(main())
