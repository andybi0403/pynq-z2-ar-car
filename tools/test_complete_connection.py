"""Verify actual connector routing with all network/process operations mocked."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import ExitStack
from unittest.mock import Mock,patch
import connect_car_console as connector


class CompleteConnectionTests(unittest.TestCase):
    def attempt(self,state,error=None):
        with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
            stack.enter_context(patch.object(connector,'OUT',Path(folder)))
            stack.enter_context(patch.object(connector,'wifi',return_value='State : connected'))
            stack.enter_context(patch.object(connector,'join_car',return_value='mock-car-profile'))
            client=Mock();stack.enter_context(patch.object(connector,'connect_board',return_value=client))
            stack.enter_context(patch.object(connector,'run',side_effect=[
                {'code':0,'stderr':'','stdout':''},
                {'code':0,'stdout':'a'*32},
                {'code':0,'stdout':'http://192.168.8.139:8080/#token=fixture-only'}]))
            opener=Mock();opener.open.return_value=io.BytesIO(json.dumps(state).encode())
            stack.enter_context(patch.object(connector.urllib.request,'build_opener',return_value=opener))
            spawn=stack.enter_context(patch.object(connector.subprocess,'Popen'))
            if error:
                with self.assertRaisesRegex(RuntimeError,error):connector.connect(lambda _:None)
                spawn.assert_not_called()
            else:
                result=connector.connect(lambda _:None)
                self.assertTrue(result['connected_verified']);spawn.assert_called_once()
            client.close.assert_called_once()

    def test_old_trial_never_opens_as_complete_console(self):
        self.attempt({'running':True,'hardware':True,'mode':'controlled-trial'},'旧的“受限试跑”')

    def test_unknown_service_is_explicit_mismatch(self):
        self.attempt({'running':True,'hardware':True},'服务与新版完整控制台不匹配')

    def test_prior_complete_console_requires_new_policy(self):
        self.attempt({'running':True,'hardware':True,'classification':'CONTROLLED_CONSOLE_NOT_RELEASE',
                      'console':{'motion_supported':True}},'服务与新版完整控制台不匹配')

    def test_matching_service_opens_even_when_driving_is_not_ready(self):
        self.attempt({'running':True,'hardware':True,'classification':'CONTROLLED_CONSOLE_NOT_RELEASE',
                      'console':{'motion_supported':True,'infrared_policy':'warning_only','motion_ready':False}})


if __name__=='__main__':unittest.main()
