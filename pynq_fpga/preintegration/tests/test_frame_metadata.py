from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from frame_metadata import encode,decode,stamp_bgr0,WORDS


def association():
    raw={'US_DATA':1000,'US_META':0x80000001,'QEI0_VEL':0xffff0000,
         'QEI1_VEL':0xffff0000,'QEI0_META':0x80000001,'QEI1_META':0x80000001,
         'RISK_STATE':0x02010002,'RISK_META':0x80000001,'QEI0_INFO':0,'QEI1_INFO':0}
    for channel in range(2):
        raw.update({f'ODOM{channel}_{key}':value for key,value in
                    [('DISP_LO',0xfffe0000),('DISP_HI',0xffffffff),('PATH_LO',0x30000),
                     ('PATH_HI',0),('META',0x80000001)]})
    return {'valid':True,'frame_id':0x12345678,'epoch':0xabcd,
            'estimated_frame_pl_ticks64':0x123456789abcdef0,'registers':raw,
            'sample_age_ms':{'us':10,'qei0':20,'qei1':20,'risk':10}}


class MetadataTests(unittest.TestCase):
    def test_quality_fault_hides_speed_even_if_velocity_valid_and_fresh(self):
        for updates in ({'QEI1_INFO':16}, {'QEI1_INFO':255<<4},
                        {'ODOM1_META':0xc0000001}, {'QEI1_VEL':0x7fffffff}):
            item=association();item['registers'].update(updates)
            result=decode(encode(item))
            self.assertFalse(result['speed_valid'])
            self.assertTrue(result['distance_valid'])

    def test_exact_wire_layout_ordinary_motor_and_64bit_time(self):
        words=encode(association())
        self.assertEqual(words[:17],[0xd3a95c,0x030018,0x345678,0xabcd12,0x0493e8,
                                    0,0,0,0,0,0,0,0,0x000201,0xbcdef0,0x56789a,0x001234])
        decoded=decode(words)
        self.assertEqual(decoded['speed_q16'],0)
        self.assertEqual(decoded['displacement_q16'],0)
        self.assertEqual(decoded['path_q16'],0)
        self.assertEqual(decoded['frame_id'],0x12345678)
        self.assertEqual(decoded['estimated_frame_pl_ticks64'],0x123456789abcdef0)
        self.assertFalse(decoded['odometry_valid'])
        self.assertFalse(decoded['filter_valid'])
        self.assertEqual(len(words),24)

    def test_explicit_host_mileage_estimate_is_labelled_and_not_qei(self):
        item=association()
        item['clock_anchor']={'display_estimate':{'available':True,'estimated':True,'travelled_mm':3}}
        result=decode(encode(item))
        self.assertTrue(result['mileage_estimated'])
        self.assertTrue(result['odometry_valid'])
        self.assertFalse(result['speed_valid'])
        self.assertEqual(result['path_q16'],196608)

    def test_corrupted_word_version_reserved_bits_and_range_rejected(self):
        words=encode(association())
        for index in range(WORDS):
            changed=words[:];changed[index]^=1
            with self.assertRaises(ValueError):decode(changed)
        # Even recomputing the checksum cannot legitimise reserved bits.
        changed=words[:];changed[6]|=1<<8;changed[-1]^=1<<8
        with self.assertRaisesRegex(ValueError,'reserved'):decode(changed)
        invalid=association();invalid['frame_id']=1<<32
        with self.assertRaisesRegex(ValueError,'uint32'):encode(invalid)

    def test_stale_sensor_and_faulted_odometry_keep_independent_invalid_flags(self):
        item=association();item['sample_age_ms']['us']=200
        item['registers']['ODOM1_META']|=0x40000000
        item['sample_age_ms']['risk']=200
        decoded=decode(encode(item))
        self.assertFalse(decoded['distance_valid']);self.assertFalse(decoded['odometry_valid'])
        self.assertEqual(decoded['risk_level'],3);self.assertTrue(decoded['risk_stop'])
        self.assertFalse(decoded['speed_valid'])

    def test_stamping_preserves_source_and_every_nonreserved_pixel(self):
        source=bytes(range(256))*4
        stamped=stamp_bgr0(source,association(),width=64,height=4)
        self.assertEqual(stamped[96:],source[96:])
        self.assertEqual(source,bytes(range(256))*4)
        words=[int.from_bytes(stamped[i:i+4],'little') for i in range(0,96,4)]
        self.assertEqual(decode(words)['epoch'],0xabcd)
        self.assertTrue(all(stamped[index*4+3]==0 for index in range(WORDS)))
        with self.assertRaises(ValueError):stamp_bgr0(source,association(),width=8,height=32)
        item=association();item['valid']=False
        with self.assertRaises(ValueError):stamp_bgr0(source,item,width=64,height=4)
