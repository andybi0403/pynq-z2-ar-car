"""Age/atomic-write/contract failures in the real host register writer."""
import unittest
from types import SimpleNamespace
from test_perception_client import FakeIO
from perception_client import PerceptionClient, ContractError
import car_regs as reg


class BridgeIO(FakeIO):
    def write32(self, offset, value):
        super().write32(offset,value)
        if offset==reg.EXT_SENSOR_COMMIT:
            self.mem[reg.EXT_SENSOR_SEQUENCE]=value
        if offset==reg.EXT_SENSOR_MODE:
            self.mem[reg.EXT_SENSOR_STATUS]=value & 1


class ExternalBridgeTests(unittest.TestCase):
    def setUp(self):
        self.io=BridgeIO();self.client=PerceptionClient(self.io)
        self.link=SimpleNamespace(sensor_snapshot=lambda:None)
        self.client.attach_sensor_link(self.link)
    def report(self, **changes):
        data=dict(us_seq=7,ir_seq=8,us_valid=True,ir_valid=True,
                  us_sample_s=.97,ir_sample_s=.999,mm=900,ir=0)
        data.update(changes);return data
    def test_age_is_preserved_and_eight_stages_precede_commit(self):
        self.client.commit_external_sensors(self.report(),1.0)
        self.assertGreaterEqual(self.io.mem[reg.EXT_US_AGE],3_000_000)
        self.assertEqual(self.io.mem[reg.EXT_US_DATA],900)
        self.assertEqual(self.io.mem[reg.EXT_IR_STATUS],4)
        self.assertEqual(self.io.mem[reg.EXT_US_META],0x80000007)
        self.assertEqual(self.io.mem[reg.EXT_SENSOR_ANCHOR_LO],0xfffffffe)
        self.assertEqual(self.io.mem[reg.EXT_SENSOR_ANCHOR_HI],1)
        self.assertEqual([off for off,_ in self.io.writes[-9:]],
                         [reg.EXT_SENSOR_ANCHOR_LO,reg.EXT_SENSOR_ANCHOR_HI,
                          reg.EXT_US_DATA,reg.EXT_US_AGE,reg.EXT_US_META,
                          reg.EXT_IR_STATUS,reg.EXT_IR_AGE,reg.EXT_IR_META,reg.EXT_SENSOR_COMMIT])
    def test_pause_before_staging_is_included_in_age(self):
        self.link._clock=lambda:1.3
        self.client.commit_external_sensors(self.report(),1.0)
        self.assertFalse(self.io.mem[reg.EXT_US_META]&0x80000000)
        self.assertFalse(self.io.mem[reg.EXT_IR_META]&0x80000000)
        self.assertGreaterEqual(self.io.mem[reg.EXT_US_AGE],33_000_000)
    def test_no_reply_and_expired_ir_revoke_validity(self):
        self.client.commit_external_sensors(None,1.0)
        self.assertEqual(self.io.mem[reg.EXT_US_META],0)
        self.assertEqual(self.io.mem[reg.EXT_IR_META],0)
        self.client.commit_external_sensors(self.report(ir_sample_s=.8),1.0)
        self.assertEqual(self.io.mem[reg.EXT_IR_META],8)
        self.assertEqual(self.io.mem[reg.EXT_US_META],0x80000007)
    def test_no_reply_does_not_seed_a_zero_sample_before_upper_half_sequence(self):
        self.client.commit_external_sensors(self.report(),1.0)
        previous=self.io.mem[reg.EXT_SENSOR_SEQUENCE]
        self.io.mem[reg.EXT_SENSOR_STATUS]=7
        self.io.writes.clear()
        self.client.commit_external_sensors(None,1.0)
        self.assertNotIn(reg.EXT_SENSOR_COMMIT,[o for o,_ in self.io.writes])
        self.assertEqual(self.io.mem[reg.EXT_SENSOR_SEQUENCE],previous)
        self.assertEqual(self.io.mem[reg.EXT_SENSOR_STATUS],1)
        self.client.commit_external_sensors(self.report(us_seq=0xf123,ir_seq=0x9011),1.0)
        self.assertEqual(self.io.mem[reg.EXT_US_META],0x8000f123)
        self.assertEqual(self.io.mem[reg.EXT_IR_META],0x80009011)
        self.assertEqual(self.io.mem[reg.EXT_SENSOR_SEQUENCE],previous+1)
    def test_future_or_old_sample_is_never_made_fresh(self):
        for stamp in (1.001,.5):
            self.client.commit_external_sensors(self.report(us_sample_s=stamp),1.0)
            self.assertFalse(self.io.mem[reg.EXT_US_META]&0x80000000)
    def test_reset_mode_and_rejected_commit_fail_closed(self):
        self.io.mem[reg.EXT_SENSOR_MODE]=0
        with self.assertRaises(ContractError):self.client.commit_external_sensors(self.report(),1.0)
        self.io.mem[reg.EXT_SENSOR_MODE]=1
        self.io.write32=lambda off,value:None
        with self.assertRaises(ContractError):self.client.commit_external_sensors(self.report(),1.0)
    def test_old_contract_cannot_enable_injection(self):
        self.io.mem[reg.ID_VERSION]=0xC4251009
        with self.assertRaises(ContractError):self.client.attach_sensor_link(self.link)


if __name__=='__main__':unittest.main()
