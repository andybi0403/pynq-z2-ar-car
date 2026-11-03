# -*- coding: utf-8 -*-
"""pynq_link.py 安全行为单元测试（PC 可运行，无需板卡与真实串口）。

覆盖审查报告 A-01（旧数据保鲜）与 A-05（半帧丢失）的修复验证：
  1. 正常更新：drive() 后发送请求值驱动帧；
  2. 采集冻结但线程存活：样本超龄后发"零速+V=0"撤销帧，旧值不得继续充当新鲜样本；
  3. 上游（网页控制）断开但线程存活：请求超龄后同样撤销；
  4. 恢复后仍需重新解锁：恢复 drive() 只更新缓存；release_request() 后仍为
     零速，只有释放之后到达的新驾驶请求才能恢复驱动帧；
  5. 接收缓存：分片、粘连、前导垃圾、超长残帧、非法 UTF-8。

运行：python test_pynq_link.py
"""
import sys
import time
import unittest

sys.path.insert(0, ".")
from pynq_link import CarLink, MockSerial, build_p, parse_car, checksum


def wait_until(pred, timeout=2.0, step=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return True
        time.sleep(step)
    return False


def make_link(**kw):
    params = dict(SAMPLE_MAX_AGE=0.05, CMD_MAX_AGE=0.10, PERIOD=0.02,
                  RX_MAX=64, RX_STALE=0.10)
    params.update(kw)
    ser = MockSerial()
    link = CarLink("/dev/null", ser=ser)
    for k, v in params.items():
        setattr(link, k, v)
    return link, ser


def frames_of(ser, prefix=b"$P"):
    return [w for w in ser.written if w.startswith(prefix)]


class TestStaleness(unittest.TestCase):
    def tearDown(self):
        if self.link._running:
            self.link._running = False
            time.sleep(0.05)

    def test_1_normal_drive_sends_requested_frame(self):
        """正常更新：drive() 后发送携带请求值与 V=1 的驱动帧。"""
        self.link, self.ser = make_link()
        self.link.drive(600, -300, True, 900, ir=0)   # 先有请求再启动线程
        self.link.start()
        self.assertTrue(wait_until(lambda: frames_of(self.ser)))
        f = frames_of(self.ser)[-1]
        # 序号由线程维护（先自增再用），因此只锚定前缀并动态验证校验和。
        prefix = b"$P,600,-300,1,0900,0,"
        self.assertTrue(f.startswith(prefix) and f.endswith(b"#"), f)
        body = f[:-4]  # 去掉 ,XX#（两个校验字符、一个逗号、一个井号）
        self.assertEqual(f, body + b"," + checksum(body.decode()).encode() + b"#")

    def test_2_frozen_sample_revokes_motion(self):
        """采集冻结但线程存活：样本超龄后必须发零速 V=0 撤销帧，不得重发旧值。"""
        self.link, self.ser = make_link()
        self.link.start()
        self.link.drive(1200, 1200, True, 800)
        self.assertTrue(wait_until(lambda: frames_of(self.ser)))
        n_before = len(frames_of(self.ser))
        # 不再调用 drive()（模拟 PL 采集任务/上游主循环冻结），线程仍运行。
        self.assertTrue(wait_until(
            lambda: any(b",0,0,0,0000,0," in w for w in frames_of(self.ser)[n_before:])))
        # 撤销帧之后不得再出现携带请求值的帧。
        idx = max(i for i, w in enumerate(self.ser.written) if b",0,0,0,0000,0," in w)
        self.assertFalse(any(b"$P,1200,1200,1," in w for w in self.ser.written[idx:]),
                         "撤销后不得重发旧驱动值")

    def test_3_upstream_disconnect_revokes_motion(self):
        """上游断开但线程存活：请求超龄同样触发撤销（与采集冻结独立的第二条路径）。"""
        self.link, self.ser = make_link(SAMPLE_MAX_AGE=5.0)  # 样本不超龄，只让请求超龄
        self.link.start()
        self.link.drive(500, 500, True, 1000)
        self.assertTrue(wait_until(lambda: frames_of(self.ser)))
        self.assertTrue(wait_until(
            lambda: any(b",0,0,0,0000,0," in w for w in frames_of(self.ser))))

    def test_4_recovery_requires_release(self):
        """抑制态下恢复 drive() 只发零速；PREL 后仍需新的 drive()。"""
        self.link, self.ser = make_link()
        self.link.drive(800, 800, True, 1000)   # 先有请求再启动线程
        self.link.start()
        self.assertTrue(wait_until(lambda: frames_of(self.ser)))
        # 等待进入抑制态
        self.assertTrue(wait_until(lambda: self.link.suppressed))
        n_before = len(self.ser.written)
        # 上游恢复 drive()：只更新缓存，不允许立即恢复驱动量
        self.link.drive(900, 900, True, 1000)
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            recent = self.ser.written[n_before:]
            if any(b"$P,900,900,1," in w for w in recent):
                self.fail("抑制态下恢复 drive() 后不得直接恢复驱动帧")
            if any(b",0,0,1,1000,0," in w for w in recent):
                break  # 零速但 V=1 的有效帧（idle_ok）——允许
            time.sleep(0.01)
        # 请求重新解锁：发送 $PREL#，但不重放释放前缓存的900/900
        self.link.drive(900, 900, True, 1000)
        self.link.release_request()
        self.assertTrue(wait_until(lambda: b"$PREL#" in self.ser.written))
        # 释放后的新驾驶请求才允许恢复
        self.link.drive(900, 900, True, 1000)
        self.assertTrue(wait_until(lambda: any(b"$P,900,900,1," in w for w in self.ser.written)))
        self.assertFalse(self.link.suppressed)


class TestRxBuffer(unittest.TestCase):
    def setUp(self):
        self.link, self.ser = make_link()
        self.link.start()

    def tearDown(self):
        self.link._running = False
        time.sleep(0.05)

    def rx_state(self, chunks):
        """把分片注入 mock 串口读队列，等待解析完成。"""
        self.ser._rx.extend(chunks)
        self.assertTrue(wait_until(lambda: self.link.state is not None, timeout=1.5))
        return self.link.state

    def test_5_fragmented_frame(self):
        """分片到达：$CAR 帧拆成多片仍能拼出完整帧。"""
        f = b"$CAR,-2400,2400,0,6,0,3,0#\r\n"
        st = self.rx_state([f[:5], f[5:12], f[12:]])
        self.assertEqual((st["left"], st["right"], st["lock"]), (-2400, 2400, 0))
        self.assertEqual(self.link.state_seq, 1)
        self.assertIsNotNone(self.link.state_rx_time)

    def test_6_garbage_then_frames_glued(self):
        """前导垃圾 + 两帧粘连：只取合法 $CAR 帧。"""
        glued = b"XX\xff\xfe$CAR,1,2,0,0,0,0,0#\r\n$CAR,3,4,0,0,0,0,1#\r\n"
        self.ser._rx.extend([glued])
        self.assertTrue(wait_until(lambda: self.link.state is not None, timeout=1.5))
        self.assertEqual(self.link.state["left"], 3)  # 最后一帧生效

    def test_7_oversize_partial_then_valid(self):
        """超长残帧丢弃重同步后，后续合法帧仍能接收。"""
        self.ser._rx.extend([b"$CAR," + b"9" * 100])   # 无 # 的超长残帧
        time.sleep(0.3)                                  # 超过 RX_STALE，缓存应被清
        f = b"$CAR,7,8,0,0,0,0,0#\r\n"
        self.ser._rx.extend([f])
        self.assertTrue(wait_until(lambda: self.link.state is not None, timeout=1.5))
        self.assertEqual(self.link.state["left"], 7)

    def test_8_invalid_utf8_not_crash(self):
        """非法 UTF-8/坏字段帧：parse_car 返回 None，缓存继续前进不卡死。"""
        self.ser._rx.extend([b"$CAR,\xff\xfe,2,0,0,0,0,0#\r\n"])  # 坏字段帧
        self.assertTrue(wait_until(lambda: not self.link._rxbuf, timeout=1.5))
        self.assertIsNone(self.link.state)          # 坏帧不产生状态
        self.assertTrue(self.link._running)         # 线程仍存活
        f = b"$CAR,7,8,0,0,0,0,0#\r\n"              # 随后合法帧仍可接收
        self.ser._rx.extend([f])
        self.assertTrue(wait_until(lambda: self.link.state is not None, timeout=1.5))
        self.assertEqual(self.link.state["left"], 7)


class TestAcceptanceRegressions(unittest.TestCase):
    def test_fresh_idle_carries_real_sensor(self):
        link, _ = make_link()
        now = time.monotonic()
        link.drive(900, 900, True, 1000, sample_ts=now)
        link.suppressed = True
        # use actual command timestamp to avoid a negative synthetic age
        kind, payload = link._decide(time.monotonic())
        self.assertEqual((kind, payload), ('idle_ok', (0, 0, True, 1000, 0)))

    def test_nonfinite_future_and_exact_expiry(self):
        for stamp in (float('nan'), float('inf'), 11.0, 9.75):
            link, _ = make_link(SAMPLE_MAX_AGE=0.25)
            link.drive(500, 500, True, 1000, sample_ts=stamp)
            link._cmd_ms = 10.0
            self.assertEqual(link._decide(10.0)[0], 'idle')

    def test_sample_update_cannot_refresh_command(self):
        link, _ = make_link()
        link.drive(500, 500, True, 1000, sample_ts=1.0)
        link._cmd_ms = 1.0
        link.update_sample(True, 1000, 0, 2.0)
        self.assertEqual(link._decide(2.0)[0], 'idle')

    def test_stop_cancels_pending_release(self):
        link, _ = make_link()
        link.drive(500, 500, True, 1000)
        link.release_request()
        link.stop_request()
        self.assertEqual(link._decide(time.monotonic())[0], 'stop')
        self.assertEqual(link._decide(time.monotonic())[0], 'idle_ok')

    def test_nested_start_recovers_valid_frame(self):
        link, ser = make_link()
        ser._rx.append(b'$CAR,broken$CAR,7,8,0,0,1000,0,0#')
        link._process_rx(time.monotonic())
        self.assertEqual(link.state['left'], 7)

    def test_release_does_not_replay_cached_motion(self):
        link, _ = make_link()
        link.drive(900, 900, True, 1000)
        link.release_request()
        self.assertEqual(link._decide(time.monotonic())[0], 'rel')
        kind, payload = link._decide(time.monotonic())
        self.assertEqual((kind, payload), ('idle_ok', (0, 0, True, 1000, 0)))
        link.drive(700, 700, True, 1000)
        self.assertEqual(link._decide(time.monotonic()),
                         ('drive', (700, 700, True, 1000, 0)))

    def test_command_before_release_does_not_bypass_release(self):
        link, _ = make_link()
        now = time.monotonic()
        link.drive(800, 800, True, 1000, sample_ts=now)
        link.suppressed = True
        link.drive(900, 900, True, 1000, sample_ts=time.monotonic())
        kind, payload = link._decide(time.monotonic())
        self.assertEqual((kind, payload), ('idle_ok', (0, 0, True, 1000, 0)))

    def test_drive_uses_injected_clock(self):
        now = [123.0]
        link = CarLink('/dev/null', ser=MockSerial(), clock_fn=lambda: now[0])
        link.drive(10, 20, True, 900)
        self.assertEqual(link._cmd_ms, 123.0)
        self.assertEqual(link._sample_ms, 123.0)


class TestChecksumAgreement(unittest.TestCase):
    def test_9_python_matches_reference(self):
        """与固件单元测试相同的参考帧：Python 校验和必须一致。"""
        cases = {
            "$P,1200,1200,1,0888,0,0": "6B",   # 对接版常规
            "$P,0,0,1,1000,0,0": "2E",         # 对接版反例基准
            "$P,-2400,-2400,1,9999,3,9": "E3", # 对接版最长
            "$P,1200,1200,1,0888,0": "0F",     # 演示版常规
            "$P,-2400,-2400,1,9999,9": "84",   # 演示版最长
        }
        for body, want in cases.items():
            self.assertEqual(checksum(body), want, body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
