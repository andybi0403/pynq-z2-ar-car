"""Offline desktop entry: join the car LAN, verify PYNQ, start and open its console."""
import argparse
import concurrent.futures
from datetime import datetime
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import threading
import time
import urllib.request

from car_network_probe import ROOT, OUT, clean, cmd, wifi, join_car, ssh_banner, connect_board
from car_deploy_console import run
from car_connection_control import (ConnectionCancelled, check_cancel, pause,
    hidden_process_options, LauncherOwnership, foreground_launcher)


def connect(progress, *, verify_only=False, restore=False, diagnose=False, browser_check=False, cancel_event=None):
    initial=wifi()
    match=re.search(r'^\s*Profile\s*:\s*(.+)$',initial,re.M)
    original=match.group(1).strip() if match else None
    facts={'started_local':datetime.now().isoformat(),'motion_commands_sent':False,'wifi_before':initial,'original_profile':original}
    client=None
    try:
        check_cancel(cancel_event)
        progress('正在连接小车 Wi-Fi（此网络没有互联网）…')
        facts['stage']='wifi'
        facts['profile']=join_car(cancel_event=cancel_event,progress=progress)
        check_cancel(cancel_event)
        progress('正在确认 PYNQ 板卡身份…')
        facts['stage']='board_identity'
        hosts=['192.168.8.139','192.168.8.10']
        candidates=hosts
        identity_errors=[]
        for host in candidates:
            check_cancel(cancel_event)
            try:
                client=connect_board(host)
                facts.update(host=host,verified_host_key=True)
                break
            except Exception as exc:
                identity_errors.append({'host':host,'error':clean(str(exc))})
        if client is None:
            check_cancel(cancel_event)
            progress('已连小车网络，正在查找 PYNQ 的实际 IP…')
            addresses=['192.168.8.'+str(i) for i in range(2,255)]
            pool=concurrent.futures.ThreadPoolExecutor(max_workers=24)
            pending={pool.submit(ssh_banner,host):host for host in addresses}
            candidates=[]
            try:
                for future in concurrent.futures.as_completed(pending):
                    check_cancel(cancel_event)
                    if future.result():candidates.append(pending[future])
            finally:
                for future in pending:future.cancel()
                pool.shutdown(wait=True,cancel_futures=True)
            for host in candidates[:3]:
                check_cancel(cancel_event)
                try:
                    client=connect_board(host)
                    facts.update(host=host,verified_host_key=True)
                    break
                except Exception as exc:
                    identity_errors.append({'host':host,'error':clean(str(exc))})
        facts['identity_attempt_errors']=identity_errors
        if client is None:
            raise RuntimeError('已连接小车 Wi-Fi，但没有找到已验证的 PYNQ。请检查板卡电源和路由器网线。')
        check_cancel(cancel_event)
        progress('正在启动板上控制台…')
        facts['stage']='board_service'
        start=run(client,'systemctl start pynq-car-console.service',root=True,timeout=35)
        if start['code']:
            raise RuntimeError('板上控制台启动失败：'+clean(start['stderr'])[-700:])
        token=None
        # A cold service loads the Overlay and checks acquisition before it
        # publishes a link. Allow its measured startup time without giving up
        # early and leaving the PC on a LAN without Internet.
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            check_cancel(cancel_event)
            invocation=run(client,'systemctl show pynq-car-console.service -p InvocationID --value')['stdout'].strip()
            if re.fullmatch('[0-9a-f]{32}',invocation):
                journal=run(client,'journalctl _SYSTEMD_INVOCATION_ID='+invocation+' -n 80 --no-pager -o cat',root=True)
                matches=re.findall(r'http://[^\s]+/#token=([\w-]+)',journal['stdout'])
                if matches:
                    token=matches[-1]
                    break
            if cancel_event is None:time.sleep(1)
            else:pause(1,cancel_event)
        if not token:
            raise RuntimeError('板上服务没有生成连接入口。请查看板上 pynq-car-console.service 日志。')
        url='http://'+host+':8080/'
        check_cancel(cancel_event)
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        request=urllib.request.Request(url+'api/status',headers={'Authorization':'Bearer '+token})
        with opener.open(request,timeout=8) as response:
            state=json.load(response)
        if not state.get('running') or state.get('hardware') is not True:
            raise RuntimeError('服务尚未进入实板运行状态。')
        check_cancel(cancel_event)
        facts['connected_verified']=True
        facts['status']=state
        if diagnose:
            facts['uart_diagnostic']=run(client,'cat /proc/tty/driver/xuartps; cat /proc/tty/driver/serial; fuser -v /dev/ttyPS1; stty -F /dev/ttyPS1 -a; ls -l /sys/class/tty/ttyPS1/device/of_node',root=True)
        if verify_only:
            (OUT/'active-session.json').write_text(json.dumps({'url':url+'#token='+token}),'utf8')
            if browser_check:
                progress('正在用浏览器验证实板画面和状态…')
                checked=subprocess.run(['node',str(ROOT/'tools/verify_live_car_console.js')],cwd=ROOT,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=50,**hidden_process_options())
                facts['browser_check']={'code':checked.returncode,'stdout':clean(checked.stdout),'stderr':clean(checked.stderr)}
                if checked.returncode:raise RuntimeError('实板浏览器检查未通过：'+clean(checked.stderr)[-500:])
            progress('实板连接已验证。')
        else:
            progress('正在打开小车控制台…')
            edge=Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe'
            if not edge.exists():
                edge=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Microsoft/Edge/Application/msedge.exe'
            if not edge.exists():
                raise RuntimeError('未找到 Microsoft Edge。')
            check_cancel(cancel_event)
            subprocess.Popen([str(edge),'--user-data-dir='+str(OUT/'edge-profile'),'--no-proxy-server','--app='+url+'#token='+token],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            progress('已连接。控制台正在显示实板数据。')
        facts['stage']='connected'
        return facts
    except ConnectionCancelled:
        facts['cancelled']=True
        facts['error']='连接已取消'
        raise
    except Exception as exc:
        facts['error']=clean(str(exc))
        raise
    finally:
        if client:client.close()
        if cancel_event is not None and cancel_event.is_set():
            facts.update(cancelled=True,error='连接已取消')
        if original and (restore or 'error' in facts):
            progress('正在恢复原来的 Wi-Fi…')
            facts['restore_request']=cmd(['netsh','wlan','connect','name='+original,'interface=WLAN 2'])
            for _ in range(8):
                time.sleep(1)
                facts['restored_wifi']=wifi()
                if re.search(r'^\s*Profile\s*:\s*'+re.escape(original)+r'\s*$',facts['restored_wifi'],re.M):
                    facts['original_wifi_restored']=True
                    break
            else:
                facts['original_wifi_restored']=False
                progress('原来的 Wi-Fi 暂未恢复，请在系统网络列表中连接 '+original+'。')
        payload=json.dumps(facts,ensure_ascii=False,indent=2)
        (OUT/'last-connect.json').write_text(payload,'utf8')
        stamp=datetime.now().strftime('%Y%m%dT%H%M%S_%f')
        (OUT/('connect-attempt_'+stamp+'.json')).write_text(payload,'utf8')
        if facts.get('connected_verified') and 'error' not in facts:
            (OUT/'last-successful-connect.json').write_text(payload,'utf8')


def launch_gui(args):
    import tkinter as tk
    window=tk.Tk()
    window.title('PYNQ 小车连接')
    window.geometry('560x250')
    window.resizable(False,False)
    tk.Label(window,text='PYNQ 小车控制台',font=('Microsoft YaHei UI',15,'bold')).pack(pady=(20,12))
    label=tk.Label(window,text='准备连接…',font=('Microsoft YaHei UI',10),wraplength=520)
    label.pack(padx=15,fill='x')
    tk.Label(window,text='关闭或取消会停止连接，并在后台恢复原 Wi-Fi。',font=('Microsoft YaHei UI',9),fg='#666666').pack(pady=10)
    events=queue.Queue()
    cancel_event=threading.Event()
    worker=None
    closed=False
    def work():
        try:
            connect(lambda s:events.put(('progress',s)),restore=args.restore,cancel_event=cancel_event)
            events.put(('done',''))
        except ConnectionCancelled:events.put(('cancelled',''))
        except Exception as exc:events.put(('error',clean(str(exc))))
    def close():
        nonlocal closed
        if closed:return
        closed=True
        cancel_event.set()
        window.destroy()
    buttons=tk.Frame(window);buttons.pack(side='bottom',pady=18)
    retry=tk.Button(buttons,text='重新连接',font=('Microsoft YaHei UI',10),width=12,state='disabled')
    retry.pack(side='left',padx=8)
    tk.Button(buttons,text='取消 / 关闭',font=('Microsoft YaHei UI',10),width=12,command=close).pack(side='left',padx=8)
    def start():
        nonlocal worker
        if worker is not None and worker.is_alive():return
        cancel_event.clear();retry.configure(state='disabled');label.configure(text='准备连接…',fg='#222222')
        worker=threading.Thread(target=work,name='car-connection')
        worker.start()
    retry.configure(command=start)
    def poll():
        try:
            while True:
                kind,value=events.get_nowait()
                if kind=='error':
                    label.configure(text=value,fg='#a00000')
                    retry.configure(state='normal')
                if kind=='done':
                    window.after(1200,window.destroy)
                    return
                if kind=='progress':label.configure(text=value)
        except queue.Empty:pass
        window.after(100,poll)
    window.protocol('WM_DELETE_WINDOW',close)
    start()
    poll()
    window.mainloop()
    # The window closes immediately; keep ownership until network restoration ends.
    if worker is not None:worker.join()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only',action='store_true')
    parser.add_argument('--restore',action='store_true')
    parser.add_argument('--diagnose',action='store_true')
    parser.add_argument('--browser-check',action='store_true')
    args=parser.parse_args()
    with LauncherOwnership() as ownership:
        if not ownership.acquired:
            foreground_launcher()
            if args.verify_only:raise RuntimeError('已有小车连接任务正在运行，请等待或关闭现有连接窗口。')
            return
        if args.verify_only:
            facts=connect(lambda s:print(s,flush=True),verify_only=True,restore=args.restore,diagnose=args.diagnose,browser_check=args.browser_check)
            print(json.dumps({k:facts.get(k) for k in ('host','profile','connected_verified','error')},ensure_ascii=True))
        else:launch_gui(args)

if __name__=='__main__':main()
