import sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from aiohttp.test_utils import TestClient,TestServer
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pynq_fpga/preintegration/host'))
from wireless_server import WirelessServer


class DisplayApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.runner=SimpleNamespace(tactical_enabled=True)
        self.mailbox=Mock()
        self.server=WirelessServer(self.runner,Mock(),self.mailbox)
        self.client=TestClient(TestServer(self.server.application()))
        await self.client.start_server()
        self.headers={'Authorization':'Bearer '+self.server.token}

    async def asyncTearDown(self):
        await self.client.close()
        self.assertEqual(self.mailbox.mock_calls,[],'display settings must not send actuator intents')

    async def test_toggle_and_readback(self):
        for enabled in (False,True):
            response=await self.client.post('/api/display/settings',json={'tactical_enabled':enabled},headers=self.headers)
            self.assertEqual(response.status,200)
            self.assertEqual(await response.json(),{'tactical_enabled':enabled})
            response=await self.client.get('/api/display/settings',headers=self.headers)
            self.assertEqual((await response.json())['tactical_enabled'],enabled)

    async def test_authentication_and_origin(self):
        response=await self.client.post('/api/display/settings',json={'tactical_enabled':False})
        self.assertEqual(response.status,401)
        response=await self.client.post('/api/display/settings',json={'tactical_enabled':False},headers={**self.headers,'Origin':'http://unrelated.invalid'})
        self.assertEqual(response.status,403)
        self.assertTrue(self.runner.tactical_enabled)

    async def test_bad_payload_does_not_change_state(self):
        for payload in ({'tactical_enabled':1},{'tactical_enabled':'true'},{},{'tactical_enabled':False,'extra':0},[],None):
            response=await self.client.post('/api/display/settings',json=payload,headers=self.headers)
            self.assertEqual(response.status,400)
            self.assertTrue(self.runner.tactical_enabled)


if __name__=='__main__':unittest.main()
