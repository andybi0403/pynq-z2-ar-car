# -*- coding: utf-8 -*-
"""夜间A：跨层停止时限闭环测试。

链路：Python(pynq_link, 可控时钟) -> FakeTransport(9600bps 字节级延迟模型)
      -> 真实 C safe_control.dll(生产源码编译) -> 安全状态/电机输出。

被测组件全部为生产代码：
  - pynq_link.CarLink（注入时钟函数，不做算法复制）
  - safe_control.c（stm32_pynq对接版 生产策略层，SHA256 记录于 c_build/build.log）
  - 传输模型：9600bps 8N1 = 每字节 10 bit -> 1.0417 ms/字节，发送端 write()
    到接收端可读之间按帧长折算延迟（阻塞读取场景的下限模型）。

分项预算（采样失效 T_s 到 STM32 电机输出为 0）：
  P1 Python 检测：样本年龄 >= SAMPLE_MAX_AGE(200ms) 后的下一个 decide 周期
     -> 最坏 +PERIOD(100ms)
  P2 传输：撤销帧 $P,0,0,0,0000,0,N,XX# = 21 字节 -> 21.9ms
  P3 C 响应：V=0 到达当拍锁车（tick 内，不计）
  断言上限：200 + 100 + 22 = 322ms；场景断言取 330ms 裕量。
  UART 完全中断场景走 C 侧兜底：250ms 租约（V 停发后 200ms 数据年龄先触发，
  两者取小 -> 断言 <=260ms，从最后有效帧到达算起）。

运行：python test_night_a_loop.py
"""
import ctypes
import sys
import unittest
from pathlib import Path

HOST = Path(__file__).resolve().parent
sys.path.insert(0, str(HOST))
sys.path.insert(0, str(HOST.parent.parent.parent / "stm32预备程序" / "pc"))

from pynq_link import CarLink, MockSerial, build_p, parse_car  # noqa: E402

# ── 生产 C DLL 加载 ──
DLL = HOST.parent / "c_build" / "safe_control.dll"
if not DLL.exists():
    raise RuntimeError("safe_control.dll missing - run c_build/build_car_c_dll.ps1 first")
lib = ctypes.CDLL(str(DLL))


class CSafe(ctypes.Structure):
    _fields_ = [("sample_ms", ctypes.c_uint32), ("command_ms", ctypes.c_uint32),
                ("clear_ms", ctypes.c_uint32), ("distance_mm", ctypes.c_uint16),
                ("ir", ctypes.c_uint8), ("valid", ctypes.c_uint8),
                ("clear_tracking", ctypes.c_uint8), ("latched", ctypes.c_uint8),
                ("distance_blocked", ctypes.c_uint8), ("command", ctypes.c_uint8),
                ("reason", ctypes.c_uint8), ("speed", ctypes.c_int),
                ("left_req", ctypes.c_int), ("right_req", ctypes.c_int),
                ("drop_count", ctypes.c_uint16)]


lib.safe_init.argtypes = [ctypes.POINTER(CSafe)]
lib.safe_tick.argtypes = [ctypes.POINTER(CSafe), ctypes.c_uint32]
lib.safe_source_handover.argtypes = [ctypes.POINTER(CSafe)]
lib.safe_pframe.restype = ctypes.c_int
lib.safe_pframe.argtypes = [ctypes.POINTER(CSafe), ctypes.c_char_p,
                            ctypes.c_size_t, ctypes.c_uint32]
lib.safe_frame.restype = ctypes.c_int
lib.safe_frame.argtypes = [ctypes.POINTER(CSafe), ctypes.c_char_p,
                           ctypes.c_size_t, ctypes.c_uint32]
lib.safe_outputs.argtypes = [ctypes.POINTER(CSafe), ctypes.POINTER(ctypes.c_int),
                             ctypes.POINTER(ctypes.c_int)]

BPS = 9600
BYTE_MS = 10 * 1000.0 / BPS          # 1.0417 ms per byte (8N1)
PERIOD_MS = 100.0                     # pynq_link 发送周期
SAMPLE_AGE_MS = 200.0                 # Python 侧样本年龄上限
CMD_AGE_MS = 500.0                    # Python 侧驾驶请求年龄上限
CMD_LEASE_MS = 250.0                  # STM32 运动租约
DATA_AGE_MS = 200.0                   # STM32 数据年龄

STOP_BUDGET_MS = 330.0                # 采样失效->撤销帧完整到达 C（200+100+22+裕量）
UART_DEAD_BUDGET_MS = 260.0           # UART 中断时 C 侧兜底（250 租约+裕量）
FAULT_IR = 2                           # safe_control.h: enum FAULT_IR


class FakeTransport:
    """9600bps 字节级单向延迟模型。

    write(data): 记录帧及"发送完成时刻"（按字节折算）；接收端在
    tx_done_at 之后 read() 才能取到整帧（阻塞读取的下限模型：
    忽略字节间间隙，按帧末对齐）。
    """

    def __init__(self, clock):
        self.clock = clock
        self.sent = []            # (tx_done_ms, bytes)
        self.delivered = []       # 已到达接收缓冲的帧（按 tx_done 排序）
        self.tx_busy_until = 0.0  # 同一根9600bps线路必须串行发送

    def write(self, data: bytes):
        n = len(data)
        start = max(self.clock(), self.tx_busy_until)
        done = start + n * BYTE_MS
        self.tx_busy_until = done
        self.sent.append((done, bytes(data)))

    def pump(self):
        """把到达时刻已到的帧移交接收缓冲。"""
        now = self.clock()
        ready = [f for (t, f) in self.sent if t <= now]
        self.sent = [(t, f) for (t, f) in self.sent if t > now]
        self.delivered.extend(ready)

    def stats(self):
        return {"n": len(self.sent) + len(self.delivered)}


class SimClock:
    """毫秒可控时钟（float ms）。"""

    def __init__(self, t0=0.0):
        self.now = t0

    def __call__(self):
        return self.now

    def advance(self, ms):
        self.now += ms
        return self.now


class CLoop:
    """真实 C safe_control 的接收与执行侧（模拟 STM32 主循环节奏）。"""

    def __init__(self):
        self.s = CSafe()
        lib.safe_init(ctypes.byref(self.s))
        self.log = []             # (c_ms, event)

    def feed_frame(self, frame: bytes, c_ms: int):
        """按 C 主循环节奏处理一帧。

        帧路由复刻生产固件 receive() 的分发逻辑（$PREL#/$PSTOP#→safe_frame
        停止帧路径，$P...→safe_pframe，其余→safe_frame）——安全判定本身全部
        仍在生产 safe_control.c 内，这里只做与固件相同的帧头分派。"""
        if frame.startswith(b"$P,"):
            ok = lib.safe_pframe(ctypes.byref(self.s), frame, len(frame), c_ms)
            ev = "pframe" if ok else "bad"
        elif frame == b"$PSTOP#":
            lib.safe_fault(ctypes.byref(self.s), 1)   # FAULT_START：高风险锁存
            ok = True
            ev = "pstop"
        elif frame == b"$PREL#":
            # 与固件一致：$PREL# 走停止帧同一条安全路径（300ms 连续条件在 C 内判定）
            ok = lib.safe_frame(ctypes.byref(self.s),
                                b"$0,0,0,0,0,0,0,0,0,0#", 21, c_ms)
            ev = "prel"
        else:
            ok = lib.safe_frame(ctypes.byref(self.s), frame, len(frame), c_ms)
            ev = "sframe" if ok else "bad"
        l = ctypes.c_int()
        r = ctypes.c_int()
        lib.safe_outputs(ctypes.byref(self.s), ctypes.byref(l), ctypes.byref(r))
        moving = (l.value != 0 or r.value != 0)
        self.log.append((c_ms, ev, moving, l.value, r.value,
                         self.s.latched, self.s.reason))
        return moving

    def tick(self, c_ms: int):
        lib.safe_tick(ctypes.byref(self.s), c_ms)
        l = ctypes.c_int()
        r = ctypes.c_int()
        lib.safe_outputs(ctypes.byref(self.s), ctypes.byref(l), ctypes.byref(r))
        moving = (l.value != 0 or r.value != 0)
        self.log.append((c_ms, "tick", moving, l.value, r.value,
                         self.s.latched, self.s.reason))
        return moving

    def last_moving(self):
        for (t, ev, moving, *_rest) in reversed(self.log):
            if ev in ("pframe", "tick"):
                return t, moving
        return None, False


class Harness:
    """可控时钟下的完整闭环：pynq_link 线程步进 + 传输 + C 主循环。"""

    def __init__(self):
        self.clock = SimClock()
        self.tx = FakeTransport(self.clock)
        self.ser = MockSerial()
        self.ser.write = self.tx.write           # 注入传输模型
        self.link = CarLink("/dev/null", ser=self.ser, clock_fn=self.clock)
        self.link.PERIOD = PERIOD_MS
        self.link.SAMPLE_MAX_AGE = SAMPLE_AGE_MS
        self.link.CMD_MAX_AGE = CMD_AGE_MS
        self.c = CLoop()
        self.c_ms = 0.0                          # C 主循环时钟（ms，uint32 语义）
        self.rx_buf = b""                        # C 侧接收缓冲
        # 采集轮询模拟：默认持续产新样本（60ms 节奏，生产采集核预算内）；
        # 冻结场景显式 self.sampling=False 停止更新。
        self.sampling = True
        self.sample_valid = True
        self.sample_mm = 1000
        self.sample_ir = 0
        self._last_sample_ms = -60.0
        self._next_tx_ms = 0.0
        self.last_moving_c_ms = None

    def pump_rx(self):
        """C 侧按当前时刻收取已到达帧并逐帧处理（每帧间隔 1ms 处理时间）。"""
        self.tx.pump()
        now32 = int(self.c_ms) & 0xFFFFFFFF  # 同拍到达的帧共享同一 C 时刻（按序处理）
        for frame in self.tx.delivered:
            self.c.feed_frame(frame, now32)
        self.tx.delivered = []

    def step(self, ms):
        """推进 ms 毫秒：pynq_link 决定发送、C 侧收帧与 tick 交错推进。"""
        target = self.clock.now + ms
        while self.clock.now < target - 1e-9:
            dt = min(10.0, target - self.clock.now)
            self.clock.advance(dt)
            self.c_ms += dt              # 同频毫秒时基；允许单独把C移到uint32回绕点
            # 采集轮询（60ms 节拍）：持续提交真实采样时刻
            if self.sampling and self.clock.now - self._last_sample_ms >= 60.0:
                self._last_sample_ms = self.clock.now
                self.link.update_sample(self.sample_valid, self.sample_mm,
                                        self.sample_ir, self.clock.now)
            # 与生产_loop一致：100ms发送一次，不能按10ms C tick灌满9600bps链路。
            now = self.clock()
            if now >= self._next_tx_ms:
                kind, payload = self.link._decide(now)
                if kind == 'stop':
                    self.ser.write(b"$PSTOP#")
                elif kind == 'rel':
                    self.ser.write(b"$PREL#")
                else:
                    self.link._seq = (self.link._seq + 1) % 10
                    if kind in ('drive', 'idle_ok'):
                        L, R, V, MM, IR = payload
                        self.ser.write(build_p(L, R, V, MM, self.link._seq, IR,
                                               self.link.proto))
                    else:
                        self.ser.write(build_p(0, 0, False, 0, self.link._seq, 0,
                                               self.link.proto))
                self._next_tx_ms = now + PERIOD_MS
            self.pump_rx()
            moving = self.c.tick(int(self.c_ms) & 0xFFFFFFFF)
            if moving:
                self.last_moving_c_ms = self.c_ms

    # ── 便捷操作 ──
    def update_sample(self, valid, mm, ir=0):
        self.link.update_sample(valid, mm, ir, self.clock())

    def update_command(self, left, right):
        self.link.update_command(left, right)

    def release(self):
        self.link.release_request()

    def stop(self):
        self.link.stop_request()

    def last_stop_c_ms(self):
        """C 侧从运动到停止的最近时刻。"""
        best = None
        prev_moving = False
        for (t, ev, moving, *_r) in self.c.log:
            if prev_moving and not moving:
                best = t
            prev_moving = moving
        return best


class TestNightACrossLayerStop(unittest.TestCase):
    """跨层停止时限：每个场景断言"采样/链路失效到 C 电机停"的时间预算。"""

    def setUp(self):
        self.h = Harness()
        # 上电预热：好样本 + 解锁 + 正转，建立运动基线
        self.h.update_sample(True, 1000, 0)
        self.h.update_command(800, 800)
        self.h.step(PERIOD_MS * 4)          # 4 周期好数据
        self.h.release()                    # $PREL# -> C 300ms 条件满足
        self.h.step(PERIOD_MS * 5)
        self.h.update_command(800, 800)     # 解锁后的新驾驶请求
        self.h.step(PERIOD_MS * 2)
        st = self.h.c.s
        self.assertFalse(st.latched, f"setup: C should be running, reason={st.reason}")
        self.assertTrue(self.h.c.log[-1][2], "setup: motors should be moving")
        self.h.c.log.clear()

    def _assert_stop_within(self, budget_ms, label):
        t = self.h.last_stop_c_ms()
        self.assertIsNotNone(t, f"{label}: C never stopped")
        since = t - (self.h.c_ms - 0)      # 相对本次 step 起点不可靠，改为场景内自查
        return t

    def test_01_sample_freeze_stop_budget(self):
        """只有采集冻结：最后一次有效样本到 C 停机 <= 330ms 预算。"""
        h = self.h
        # 记录最后一个有效样本帧到达 C 的时刻（从 log 找最后一个 V=1 帧）
        last_good_arrival = None
        for (t, ev, moving, *_r) in h.c.log:
            last_good_arrival = t        # 每 tick 都在跑；用帧到达更精确——重建：
        # 简化：停止采样更新后推进，记录 C 停止时刻与"当前时钟-撤销窗"关系
        freeze_clock = h.clock.now       # 采集冻结从此刻起
        h.sampling = False               # 停止采集更新（模拟采集核死）
        h.step(SAMPLE_AGE_MS + PERIOD_MS + 60)   # 预算窗：200 检测+100 周期+帧传输+裕量
        t_stop = h.last_stop_c_ms()
        self.assertIsNotNone(t_stop, "C did not stop after sample freeze")
        # 停止时刻相对冻结时刻
        elapsed = t_stop - freeze_clock
        self.assertLessEqual(elapsed, STOP_BUDGET_MS,
                             f"sample-freeze stop took {elapsed:.1f}ms > {STOP_BUDGET_MS}ms")
        self.assertGreater(elapsed, SAMPLE_AGE_MS - 1,
                           "stopped before sample age limit - timeline is wrong")

    def test_02_command_freeze_stop_budget(self):
        """只有上游网页控制冻结：cmd 超 500ms 后 C 停机 <= 500+100+22+裕量。"""
        h = self.h
        h.update_command(800, 800)       # 从本场景起点定义最后一次驾驶续租
        freeze_clock = h.clock.now
        # 采集继续（sampling=True），只停驾驶意图更新（网页端断开）
        h.step(CMD_AGE_MS + PERIOD_MS + 60)
        t_stop = h.last_stop_c_ms()
        self.assertIsNotNone(t_stop, "C did not stop after command freeze")
        elapsed = t_stop - freeze_clock
        self.assertLessEqual(elapsed, CMD_AGE_MS + PERIOD_MS + 22 + 10,
                             f"cmd-freeze stop took {elapsed:.1f}ms")

    def test_03_uart_dead_c_side_backstop(self):
        """只有 UART 中断（Python 发但 C 收不到）：C 侧 250ms 租约兜底。"""
        h = self.h
        # 断开传输：tx 帧不再到达（模拟无线/线路断）
        h.tx.pump = lambda: None
        h.tx.write = lambda data: None
        dead_clock = h.clock.now
        h.step(DATA_AGE_MS + 60)
        t_stop = h.last_stop_c_ms()
        self.assertIsNotNone(t_stop, "C did not stop after UART death")
        elapsed = t_stop - dead_clock
        self.assertLessEqual(elapsed, UART_DEAD_BUDGET_MS,
                             f"UART-dead stop took {elapsed:.1f}ms > {UART_DEAD_BUDGET_MS}ms")

    def test_04_python_killed_c_backstop(self):
        """Python 全死（不再 step 也不发帧）：只推进 C 时钟。"""
        h = self.h
        dead_clock = h.c_ms
        for _ in range(30):
            h.c_ms += 10
            h.c.tick(int(h.c_ms) & 0xFFFFFFFF)
        t_stop = h.last_stop_c_ms()
        self.assertIsNotNone(t_stop)
        elapsed = t_stop - dead_clock
        self.assertLessEqual(elapsed, CMD_LEASE_MS + 10,
                             f"C backstop took {elapsed:.1f}ms > {CMD_LEASE_MS}ms")

    def test_05_ir_obstacle_immediate(self):
        """IR 触发：采集态 IR=3 -> P 帧 IR 位=3 -> C 立即锁存停车。"""
        h = self.h
        h.sample_ir = 3                     # 采集核状态：左右均见障碍
        h.update_command(800, 800)          # 遥控持续发包（租约内）
        h.step(PERIOD_MS + 40)
        t_stop = h.last_stop_c_ms()
        self.assertIsNotNone(t_stop, "IR did not stop the car")
        self.assertTrue(h.c.s.latched and bool(h.c.s.reason & FAULT_IR),
                        f"IR fault reason missing: {h.c.s.reason}")

    def test_06_distance_hysteresis_180_240_260(self):
        """距离 180→只禁正转；240→保持；260→恢复（回差）。"""
        h = self.h
        h.sample_mm = 180
        h.update_command(800, 800)
        h.step(PERIOD_MS + 40)
        l = ctypes.c_int(); r = ctypes.c_int()
        lib.safe_outputs(ctypes.byref(h.c.s), ctypes.byref(l), ctypes.byref(r))
        self.assertEqual(l.value, 0, "forward must be blocked at 180mm")
        h.sample_mm = 240
        h.update_command(800, 800)
        h.step(PERIOD_MS + 40)
        lib.safe_outputs(ctypes.byref(h.c.s), ctypes.byref(l), ctypes.byref(r))
        self.assertEqual(l.value, 0, "forward still blocked at 240mm (hysteresis)")
        h.sample_mm = 260
        h.update_command(800, 800)
        h.step(PERIOD_MS + 40)
        lib.safe_outputs(ctypes.byref(h.c.s), ctypes.byref(l), ctypes.byref(r))
        self.assertEqual(l.value, 800, "forward restored at 260mm")

    def test_07_bad_frame_checksum(self):
        """坏校验和帧：C 拒绝+drop 计数+不产生运动。"""
        h = self.h
        before = h.c.s.drop_count
        h.tx.write(b"$P,999,999,1,0999,0,00#")   # 坏校验和
        h.step(PERIOD_MS + 40)
        self.assertGreater(h.c.s.drop_count, before, "checksum error not counted")
        self.assertTrue(h.c.s.latched, "bad frame must latch")

    def test_08_inserted_field_frame_rejected(self):
        """插字段反例（审查 A-02）：X 不参与校验和，必须整帧拒绝。"""
        h = self.h
        before = h.c.s.drop_count
        h.tx.write(b"$P,0,0,1,1000,0,0,X,2E#")   # 22 字节反例
        h.step(PERIOD_MS + 40)
        self.assertEqual(h.c.s.drop_count, before + 1, "inserted-field frame accepted!")
        self.assertTrue(h.c.s.latched)

    def test_09_fragmented_and_glued_frames(self):
        """生产CarLink接收器能从分片和粘连的$CAR字节流恢复两帧。"""
        ser = MockSerial([
            b"noise$CAR,1,2,0,0,1000,0,0",
            b"#$CAR,3,4,1,2,900,1,7#",
        ])
        link = CarLink('/dev/null', ser=ser, clock_fn=lambda: 0.0)
        link._process_rx(0.0)
        self.assertIsNone(link.state)
        link._process_rx(1.0)
        self.assertEqual(link.state,
                         {'left': 3, 'right': 4, 'lock': 1, 'fault': 2,
                          'mm': 900, 'ir': 1, 'drop': 7})

    def test_10_recovery_requires_explicit_release(self):
        """安全条件恢复但无显式解锁：保持锁车。"""
        h = self.h
        # 制造故障锁存
        h.sample_ir = 3
        h.update_command(800, 800)
        h.step(PERIOD_MS + 40)
        self.assertTrue(h.c.s.latched)
        # 故障解除（IR 清除、距离正常）+ 零速心跳，但不发 release
        h.sample_ir = 0
        h.update_command(0, 0)              # 上游停止运动请求（零速续租）
        h.step(PERIOD_MS * 4)
        self.assertTrue(h.c.s.latched,
                        "C unlocked without explicit release!")
        # 显式解锁（$PREL# 语义：满足 300ms 连续安全条件后由 C 判定）
        h.release()
        h.step(PERIOD_MS * 4)
        self.assertFalse(h.c.s.latched, "explicit release did not unlock")

    def test_11_unlock_requires_new_command(self):
        """显式解锁后没有新驾驶请求：不得恢复运动。"""
        h = self.h
        h.sample_ir = 3
        h.update_command(800, 800)
        h.step(PERIOD_MS + 40)
        self.assertTrue(h.c.s.latched)
        h.sample_ir = 0
        h.update_command(0, 0)
        h.step(PERIOD_MS * 4)       # 先用有效停止帧满足C端连续安全300ms
        h.release()
        h.step(PERIOD_MS * 4)
        self.assertFalse(h.c.s.latched)
        # 解锁后 drive() 没有新请求（_cmd 保持 0,0）——C 输出必须为 0
        l = ctypes.c_int(); r = ctypes.c_int()
        lib.safe_outputs(ctypes.byref(h.c.s), ctypes.byref(l), ctypes.byref(r))
        self.assertEqual((l.value, r.value), (0, 0),
                         "motion resumed without new driving intent")

    def test_12_unlock_cancelled_by_stop(self):
        """STOP 取消待决 release（R11 语义）：STOP 后 release 不生效。"""
        h = self.h
        h.sample_ir = 3
        h.update_command(800, 800)
        h.step(PERIOD_MS + 40)
        self.assertTrue(h.c.s.latched)
        h.sample_ir = 0
        h.update_command(0, 0)
        h.release()
        h.stop()                                  # STOP 在 release 后立即到来
        h.step(PERIOD_MS * 4)
        self.assertTrue(h.c.s.latched, "STOP must cancel pending release")

    def test_13_time_wrap_in_c(self):
        """C 侧 uint32 时间回绕：0xFFFFFFF0 附近收帧+租约正常。"""
        c = CLoop()
        start = 0xFFFFFF00
        # 有效零速帧每100ms刷新，连续安全300ms跨越0xffffffff->0。
        for offset in (0, 100, 200, 300, 400):
            frame = build_p(0, 0, True, 1000, (offset // 100) % 10, 0, 'pynq')
            c.feed_frame(frame, (start + offset) & 0xFFFFFFFF)
        c.feed_frame(b'$PREL#', (start + 410) & 0xFFFFFFFF)
        self.assertFalse(c.s.latched, "uint32 wrap broke 300ms clear interval")
        drive = build_p(800, 800, True, 1000, 6, 0, 'pynq')
        self.assertTrue(c.feed_frame(drive, (start + 420) & 0xFFFFFFFF))
        # 200ms数据年龄边界同样跨回绕生效。
        c.tick((start + 620) & 0xFFFFFFFF)
        self.assertTrue(c.s.latched, "uint32 wrap broke sensor-age backstop")

    def test_14_age_boundary_exact(self):
        """样本年龄等于阈值即失效（>= 语义）：199ms 新鲜、201ms 过期。"""
        clock = SimClock()
        link = CarLink('/dev/null', ser=MockSerial(), clock_fn=clock)
        link.SAMPLE_MAX_AGE = SAMPLE_AGE_MS
        link.CMD_MAX_AGE = CMD_AGE_MS
        link.update_sample(True, 1234, 0, clock())
        link.update_command(1, 1)
        clock.advance(SAMPLE_AGE_MS - 1)
        self.assertEqual(link._decide(clock())[0], 'drive')
        clock.advance(1)
        self.assertEqual(link._decide(clock())[0], 'idle')

    def test_15_source_handover_discards_unlock_snapshot(self):
        """控制源切换后，旧源的安全快照不能供兼容 STOP 帧解锁。"""
        c = CLoop()
        for offset in (0, 100, 200, 300):
            frame = build_p(0, 0, True, 1000, (offset // 100) % 10, 0, 'pynq')
            c.feed_frame(frame, 1000 + offset)
        self.assertTrue(c.s.valid and c.s.clear_tracking)
        nonzero = build_p(1200, -800, True, 1000, 4, 0, 'pynq')
        c.feed_frame(nonzero, 1400)
        self.assertEqual((c.s.left_req, c.s.right_req), (1200, -800))
        lib.safe_source_handover(ctypes.byref(c.s))
        self.assertTrue(c.s.latched)
        self.assertFalse(c.s.valid)
        self.assertFalse(c.s.clear_tracking)
        c.feed_frame(b'$0,0,0,0,0,0,0,0,0,0#', 1499)
        self.assertTrue(c.s.latched, "old snapshot unlocked after source handover")
        self.assertEqual((c.s.left_req, c.s.right_req), (0, 0))


class TestFrameTransportModel(unittest.TestCase):
    """传输模型自检：帧长字节按 9600bps 折算。"""

    def test_frame_length_budget(self):
        f = build_p(-2400, -2400, True, 9999, 9, 3, 'pynq')
        self.assertEqual(len(f), 29, "longest $P frame must be 29 bytes")
        t = len(f) * BYTE_MS
        self.assertAlmostEqual(t, 30.2, delta=0.1,
                               msg="9600bps byte budget drifted")
        f_short = build_p(0, 0, False, 0, 0, 0, 'pynq')
        self.assertEqual(len(f_short), 21, "idle revoke frame must be 21 bytes")
        self.assertLess(len(f_short) * BYTE_MS, 22.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
