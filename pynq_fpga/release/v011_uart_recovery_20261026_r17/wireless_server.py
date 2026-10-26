"""LAN HTTP MJPEG + WebSocket; all hardware requests go through the mailbox."""
import asyncio
import base64
import json
from pathlib import Path
import secrets
import threading
import time
from aiohttp import web,WSMsgType
from wireless_core import ControlGate


class WirelessServer:
    def __init__(self,runner,hub,mailbox,host='0.0.0.0',port=8080):
        self.runner=runner;self.hub=hub;self.mailbox=mailbox;self.host=host;self.port=port
        self.token=secrets.token_urlsafe(32);self.cookie=secrets.token_urlsafe(32)
        self.gate=ControlGate(mailbox,motion_allowed=False)
        self.loop=None;self.thread=None;self.ready=threading.Event();self.failure=None
        self.video_task=None;self.sockets=set()
        self.snapshot_busy=False
        self.video_session=None
        self.page_text=Path(__file__).with_name('wireless_page.html').read_text(encoding='utf-8')
    def authorized(self,request):
        bearer=request.headers.get('Authorization','')
        cookie=request.cookies.get('car_session','')
        return secrets.compare_digest(bearer,'Bearer '+self.token) or secrets.compare_digest(cookie,self.cookie)
    def check(self,request,mutating=False):
        if not self.authorized(request):raise web.HTTPUnauthorized(text='需要本次启动链接中的会话令牌')
        origin=request.headers.get('Origin')
        if origin is not None and origin!=f'{request.scheme}://{request.host}':raise web.HTTPForbidden(text='Origin不匹配')
        if mutating and origin is None and not secrets.compare_digest(request.headers.get('Authorization',''),'Bearer '+self.token):
            raise web.HTTPForbidden(text='修改请求需要同源Origin')
    async def page(self,request):
        return web.Response(text=self.page_text,content_type='text/html',headers={'Cache-Control':'no-store'})
    async def session(self,request):
        self.check(request,True)
        response=web.json_response({'authenticated':True,'motion_allowed':False})
        response.set_cookie('car_session',self.cookie,httponly=True,samesite='Strict',path='/')
        return response
    async def logout(self,request):
        self.check(request,True)
        self.gate.revoke('operator_logout')
        if self.sockets:
            await asyncio.gather(*(ws.close(code=1000,message=b'logged out') for ws in list(self.sockets)),return_exceptions=True)
        response=web.json_response({'authenticated':False})
        response.del_cookie('car_session',path='/')
        return response
    async def status(self,request):
        self.check(request)
        state=self.runner.status_snapshot();state['video']=self.hub.stats()
        state['remote_control']=self.gate.status()
        return web.json_response(state,headers={'Cache-Control':'no-store'})
    async def player_script(self,request):
        return web.FileResponse(Path(__file__).with_name('wireless_player.js'))
    async def console_script(self,request):
        return web.FileResponse(Path(__file__).with_name('console_ui.js'))
    async def video_settings(self,request):
        self.check(request,request.method=='POST')
        if request.method=='GET':return web.json_response(self.hub.policy.settings())
        try:settings=self.hub.policy.configure(await request.json())
        except (ValueError,TypeError) as exc:raise web.HTTPBadRequest(text=str(exc))
        return web.json_response(settings)
    async def video_feedback(self,request):
        self.check(request,True)
        try:
            payload=await request.json()
            if not self.video_session or not isinstance(payload,dict) or payload.get('video_session')!=self.video_session:
                raise ValueError('feedback must match the active video session')
            if type(payload.get('visible')) is not bool:raise ValueError('visible must be boolean')
            self.hub.policy.observe(receiver=payload)
        except (ValueError,TypeError) as exc:raise web.HTTPBadRequest(text=str(exc))
        return web.json_response({'recorded':True})
    async def snapshot(self,request):
        self.check(request,True)
        if self.snapshot_busy:raise web.HTTPTooManyRequests(text='冻结请求正在处理中')
        self.snapshot_busy=True
        try:frame=await asyncio.to_thread(self.hub.snapshot)
        except (TimeoutError,RuntimeError) as exc:raise web.HTTPServiceUnavailable(text=str(exc))
        finally:self.snapshot_busy=False
        return web.json_response({'frame_id':frame.frame_id,'captured_monotonic_ns':frame.captured_ns,
             'raw_jpeg_base64':base64.b64encode(frame.raw).decode(),
             'processed_jpeg_base64':base64.b64encode(frame.processed).decode(),
             'historical_snapshot':frame.historical},headers={'Cache-Control':'no-store'})
    async def video(self,request):
        self.check(request);view=request.query.get('view','processed')
        if view not in ('raw','processed'):raise web.HTTPBadRequest(text='invalid view')
        task=asyncio.current_task();old=self.video_task
        if old and old is not task:old.cancel()
        self.video_task=task;self.hub.set_view(view)
        stream_identity=secrets.token_hex(12);self.video_session=stream_identity
        response=web.StreamResponse(headers={'Content-Type':'multipart/x-mixed-replace; boundary=carframe',
                                               'Cache-Control':'no-store','X-Accel-Buffering':'no',
                                               'X-Video-Session':stream_identity})
        try:
            await response.prepare(request);last=-1
            while not self.hub.closed:
                frame=await asyncio.to_thread(self.hub.next,view,last,.5)
                if frame is None:continue
                if time.monotonic_ns()-frame.captured_ns>500_000_000:
                    last=frame.frame_id;continue
                jpeg=frame.raw if view=='raw' else frame.processed
                header=(f'--carframe\r\nContent-Type: image/jpeg\r\nContent-Length: {len(jpeg)}\r\n'
                        f'X-Frame-Id: {frame.frame_id}\r\nX-Captured-Monotonic-Ns: {frame.captured_ns}\r\n'
                        f'X-JPEG-Quality: {"camera-native" if view=="raw" else frame.historical.get("jpeg_quality",75)}\r\n\r\n').encode()
                # Separate writes avoid joining/copying the entire compressed frame.
                started=time.monotonic_ns()
                for chunk in (header,jpeg,b'\r\n'):
                    await asyncio.wait_for(response.write(chunk),timeout=.25)
                send_ms=(time.monotonic_ns()-started)/1e6
                self.hub.observe('network_write',send_ms,amount=0);self.hub.policy.observe(cost_ms=send_ms)
                last=frame.frame_id;self.hub.observe('sent')
                with self.hub.condition:self.hub.bytes_sent+=len(jpeg)
        except asyncio.TimeoutError:self.hub.policy.observe(backlogged=True,source='network')
        except (ConnectionError,asyncio.CancelledError):pass
        finally:
            if self.video_task is task:self.video_task=None;self.video_session=None
        return response
    async def control(self,request):
        self.check(request,True)
        ws=web.WebSocketResponse(max_msg_size=4096,autoping=True,timeout=1)
        await ws.prepare(request);key=secrets.token_hex(16)
        try:self.gate.connect(key)
        except ValueError:
            await ws.close(code=1013,message=b'too many connections');return ws
        self.sockets.add(ws);next_sync=0;window=time.monotonic();messages=0
        try:
            while not ws.closed:
                now=time.monotonic()
                self.gate.maintain()
                if now>=next_sync:
                    await ws.send_json(self.gate.challenge(key));next_sync=now+1
                try:message=await ws.receive(timeout=.05)
                except asyncio.TimeoutError:continue
                if message.type in (WSMsgType.CLOSE,WSMsgType.CLOSED,WSMsgType.ERROR):break
                if message.type!=WSMsgType.TEXT:continue
                if now-window>=1:window=now;messages=0
                messages+=1
                if messages>60:raise ValueError('control rate exceeds 60 messages/s')
                payload=json.loads(message.data)
                if (isinstance(payload,dict) and payload.get('type') in ('claim','intent','release')
                        and not getattr(self.runner,'control_available',True)):
                    self.gate.revoke('video_only_control_disabled')
                    await ws.send_json({'type':'error','error':'当前为视频测试会话，未连接执行器控制'})
                    continue
                if isinstance(payload,dict) and payload.get('type') in ('claim','intent','release') and self.hub.error:
                    self.gate.revoke('video_unavailable: '+self.hub.error)
                    await ws.send_json({'type':'error','error':'视频不可用，已撤销控制：'+self.hub.error})
                    continue
                if isinstance(payload,dict) and payload.get('type')=='ack_timing':
                    rtt=ControlGate.number(payload.get('rtt_ms'))
                    if not 0<=rtt<=10000:raise ValueError('invalid browser RTT')
                    self.hub.observe('browser_control_rtt',rtt)
                    continue  # Observability must NEVER renew a driving lease.
                try:reply=self.gate.message(key,payload)
                except (ValueError,TypeError) as exc:
                    reply={'type':'error','error':str(exc)}
                await ws.send_json(reply)
        except (ValueError,json.JSONDecodeError):
            await ws.close(code=1008,message=b'invalid control request')
        finally:
            self.gate.disconnect(key);self.sockets.discard(ws)
        return ws
    async def action(self,request):
        self.check(request,True)
        if request.match_info['kind']=='stop':
            self.gate.revoke('operator_stop')
            return web.json_response({'queued':True})
        try:
            result=self.runner.enqueue_action('calibration',await request.json())
            return web.json_response(result,status=202)
        except (ValueError,RuntimeError,TypeError) as exc:raise web.HTTPBadRequest(text=str(exc))
    async def sensor_test_reset(self,request):
        self.check(request,True)
        try:result=self.runner.reset_interconnect_test()
        except (AttributeError,RuntimeError) as exc:raise web.HTTPBadRequest(text=str(exc))
        return web.json_response(result)
    async def log(self,request):
        self.check(request)
        name=request.match_info['name']
        if name not in ('joint.jsonl','joint_summary.json','video.jsonl','video_summary.json'):raise web.HTTPNotFound()
        path=self.runner.output_dir/name
        if not path.is_file():raise web.HTTPNotFound()
        return web.FileResponse(path)
    def application(self):
        app=web.Application(client_max_size=16384)
        app.router.add_get('/',self.page);app.router.add_post('/api/session',self.session)
        app.router.add_post('/api/session/logout',self.logout)
        app.router.add_get('/assets/wireless_player.js',self.player_script)
        app.router.add_get('/assets/console_ui.js',self.console_script)
        app.router.add_get('/api/video/settings',self.video_settings);app.router.add_post('/api/video/settings',self.video_settings)
        app.router.add_post('/api/video/feedback',self.video_feedback)
        app.router.add_get('/api/status',self.status);app.router.add_get('/api/video',self.video)
        app.router.add_post('/api/snapshot',self.snapshot);app.router.add_get('/api/control',self.control)
        app.router.add_post('/api/sensor-test/reset',self.sensor_test_reset)
        app.router.add_post('/api/{kind:stop|calibration}',self.action)
        app.router.add_get('/api/log/{name}',self.log)
        return app
    async def start_async(self):
        self.app_runner=web.AppRunner(self.application(),access_log=None,shutdown_timeout=1)
        await self.app_runner.setup();self.site=web.TCPSite(self.app_runner,self.host,self.port)
        await self.site.start();self.port=self.site._server.sockets[0].getsockname()[1]
        async def watchdog():
            while True:
                if self.hub.error and self.gate.owner is not None:
                    self.gate.revoke('video_unavailable: '+self.hub.error)
                self.gate.maintain();await asyncio.sleep(.05)
        self.watchdog_task=asyncio.create_task(watchdog())
    async def stop_async(self):
        self.mailbox.stop()
        self.watchdog_task.cancel()
        await asyncio.gather(self.watchdog_task,return_exceptions=True)
        if self.video_task:self.video_task.cancel()
        if self.sockets:
            try:await asyncio.wait_for(asyncio.gather(*(ws.close() for ws in list(self.sockets))),timeout=1)
            except asyncio.TimeoutError:pass
        await self.app_runner.cleanup()
    def __enter__(self):
        def run():
            self.loop=asyncio.new_event_loop();asyncio.set_event_loop(self.loop)
            try:self.loop.run_until_complete(self.start_async())
            except Exception as exc:self.failure=exc
            finally:self.ready.set()
            if self.failure:self.loop.close();return
            try:self.loop.run_forever()
            finally:
                pending=asyncio.all_tasks(self.loop)
                for task in pending:task.cancel()
                if pending:self.loop.run_until_complete(asyncio.gather(*pending,return_exceptions=True))
                self.loop.run_until_complete(self.loop.shutdown_asyncgens())
                self.loop.run_until_complete(self.loop.shutdown_default_executor())
                self.loop.close()
        self.thread=threading.Thread(target=run,daemon=True,name='wireless-http');self.thread.start()
        if not self.ready.wait(5):raise TimeoutError('web server startup timed out')
        if self.failure:raise self.failure
        return self
    def __exit__(self,*args):
        try:asyncio.run_coroutine_threadsafe(self.stop_async(),self.loop).result(timeout=3)
        finally:self.loop.call_soon_threadsafe(self.loop.stop);self.thread.join(timeout=3)
        if self.thread.is_alive():raise RuntimeError('web server shutdown unconfirmed')
