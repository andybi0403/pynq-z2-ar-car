"""Exercise the real local desktop server without touching car networking."""
from http.client import HTTPConnection
import json
import threading
import time
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from open_car_console import Handler


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.last_seen=0
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.origin='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,path='/',method='GET',headers=None):
        conn=HTTPConnection('127.0.0.1',self.server.server_port,timeout=2)
        conn.request(method,path,headers=headers or {})
        response=conn.getresponse();data=response.read();status=response.status
        conn.close();return status,data

    @patch('open_car_console.subprocess.Popen')
    def test_offline_page_and_info_never_launch_network_helper(self,spawn):
        status,page=self.request();self.assertEqual(status,200)
        self.assertIn('PYNQ AR 小车控制台',page.decode())
        self.assertGreater(self.server.last_seen,0)
        self.assertEqual(self.request('/assets/console_ui.js')[0],200)
        status,data=self.request('/api/desktop/info')
        self.assertEqual(status,200)
        self.assertFalse(json.loads(data)['network_auto_connect'])
        self.assertEqual(self.request('/api/status')[0],401)
        spawn.assert_not_called()

    @patch('open_car_console.subprocess.Popen')
    def test_foreign_host_and_origin_cannot_start_helper(self,spawn):
        self.assertEqual(self.request(headers={'Host':'foreign.invalid'})[0],403)
        for headers in ({},{'Origin':'http://foreign.invalid'}):
            self.assertEqual(self.request('/api/desktop/connect','POST',headers)[0],403)
        spawn.assert_not_called()

    @patch('open_car_console.subprocess.Popen')
    def test_only_explicit_same_origin_connect_launches_fixed_hidden_helper(self,spawn):
        status,_=self.request('/api/desktop/connect','POST',{'Origin':self.origin})
        self.assertEqual(status,202);spawn.assert_called_once()
        args,kwargs=spawn.call_args
        self.assertTrue(args[0][-1].endswith('tools\\connect_car_console.py') or args[0][-1].endswith('tools/connect_car_console.py'))
        self.assertNotIn('shell',kwargs)
        self.assertIn('creationflags',kwargs)

    def test_ping_and_path_allowlist(self):
        self.assertEqual(self.request('/api/desktop/ping','POST',{'Origin':self.origin})[0],200)
        self.assertLess(time.monotonic()-self.server.last_seen,1)
        self.assertEqual(self.request('/../tools/car_network_probe.py')[0],404)


if __name__=='__main__':unittest.main()
