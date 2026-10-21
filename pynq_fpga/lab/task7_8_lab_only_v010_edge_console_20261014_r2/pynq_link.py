# -*- coding: utf-8 -*-
"""
PYNQ-Z2 与 STM32 底盘的 UART 链路模块（协议 V2.1，安全修订版）。

支持两个固件版本的帧格式：
  - PYNQ 完整对接版（stm32_pynq对接版/，超声波+红外全部在 PYNQ 上）：
      $P,<L>,<R>,<V>,<MMM>,<IR>,<N>,<C>#   ← 默认格式
  - 演示版（stm32预备程序/，超声波仍在 STM32 上）：
      $P,<L>,<R>,<V>,<MMM>,<N>,<C>#
构造函数用 proto='pynq' 或 'demo' 选择，默认对接版。

安全语义（与 STM32 侧 200ms 数据年龄 / 250ms 运动租约对齐）：
  - drive() 的 left/right 是上游驾驶请求，valid/mm/ir 是 PL 真实传感器样本；
    两者分别记录更新时间。任一超龄，后台线程不再重发旧值，而是发送
    "零速 + V=0" 撤销帧——STM32 依 V=0 立即按传感器无效锁存停车。
  - 进入抑制态后，即使上游恢复 drive()，也只更新缓存值；必须显式调用
    release_request()。释放请求只发送停止状态，随后还必须收到一条新的驾驶
    请求才恢复驱动量，禁止重放释放前缓存的运动值。
  - 接收侧维护跨调用字节缓存：按 '$'/'#' 提取完整 $CAR 帧，容忍分片到达、
    前导垃圾与帧粘连；残帧超时或超长即丢弃重同步。$CAR 的 L/R 字段是
    STM32 实际应用到电机的执行 PWM（真实轮速来自编码器）。

本模块不做风险判断；风险等级与动态安全距离由 PL 状态机决定，PS 只读结果。
"""
import threading
import time
import math
import re
import secrets

try:
    import serial
except ImportError:  # 允许在 PC 上仅运行单元测试（注入 mock 串口）
    serial = None

SAFE_MAX_PWM = 2400


def checksum(body: str) -> str:
    """'$' 到 N 字段所有字符 ASCII 和的低 8 位，两位大写十六进制。"""
    return f"{sum(body.encode()) & 0xFF:02X}"


def build_p(left: int, right: int, valid: bool, mm: int, seq: int,
            ir: int = 0, proto: str = 'pynq') -> bytes:
    """构造 $P 驱动帧。left/right：左右轮 PWM，正=前进；mm：PL 测距值；
    ir：红外位图 bit0 左 bit1 右（仅对接版固件使用）。"""
    if proto not in ('pynq', 'demo'):
        raise ValueError('unknown protocol')
    for v in (left, right):
        if not -SAFE_MAX_PWM <= v <= SAFE_MAX_PWM:
            raise ValueError(f"PWM 超出 ±{SAFE_MAX_PWM}: {v}")
    if proto == 'pynq':
        body = (f"$P,{left},{right},{1 if valid else 0},"
                f"{max(0, min(mm, 9999)):04d},{ir & 3},{seq % 10}")
    else:
        body = (f"$P,{left},{right},{1 if valid else 0},"
                f"{max(0, min(mm, 9999)):04d},{seq % 10}")
    return (body + f",{checksum(body)}#").encode()


def parse_car(line: bytes):
    """解析 $CAR 帧为 dict，格式错误返回 None。"""
    try:
        text = line.decode("ascii").strip()
    except UnicodeDecodeError:
        return None
    if not re.fullmatch(r'\$CAR,-?\d+,-?\d+,\d+,\d+,\d+,\d+,\d+#', text):
        return None
    if not (text.startswith("$CAR,") and text.endswith("#")):
        return None
    fields = text[5:-1].split(",")
    if len(fields) != 7:
        return None
    try:
        left, right, lock, fault, mm, ir, drop = fields
        values = tuple(map(int, fields))
        limits = ((-2400, 2400), (-2400, 2400), (0, 1), (0, 65535),
                  (0, 9999), (0, 3), (0, 0xffffffff))
        if any(not lo <= value <= hi for value, (lo, hi) in zip(values, limits)):
            return None
        return dict(zip(("left", "right", "lock", "fault", "mm", "ir", "drop"), values))
    except ValueError:
        return None


class CarLink:
    """100ms 周期发送 $P 帧；真实样本过期或上游请求过期时自动撤销运动许可。

    用法（PYNQ 上，对接版固件）：
        link = CarLink('/dev/ttyPS1')       # 或注入已有串口对象 ser=...
        link.start()
        link.drive(600, 600, valid=True, mm=900, ir=0,
                   sample_ts=pl_sample_monotonic)   # sample_ts 用 PL 采样时刻
        link.state                          # 最近一次完整 $CAR 的解析结果
        link.stop_request()                 # $PSTOP#
        link.release_request()              # 抑制恢复后请求重新解锁
    """

    PERIOD = 0.10           # 发送周期 100ms；STM32 租约 250ms、数据年龄 200ms
    SAMPLE_MAX_AGE = 0.20   # 真实传感器样本最大年龄（秒），超龄即撤销运动许可
    CMD_MAX_AGE = 0.50      # 上游驾驶请求最大年龄（秒），超龄同上（STM32 租约兜底）
    RX_MAX = 160            # 接收缓存上限（最长合法 $CAR 约 40 字节，留足余量）
    RX_STALE = 0.50         # 残帧最大等待时间（秒）

    def __init__(self, port: str, baud: int = 9600, proto: str = 'pynq', ser=None,
                 clock_fn=None):
        # clock_fn：可控时钟注入（测试用），默认 time.monotonic（秒）。
        # 所有内部时间（_cmd_ms/_sample_ms/loop tick/rx 时间戳）统一使用该时钟，
        # 单位由调用方约定（生产=秒；测试可传毫秒时钟，PERIOD 等常量同步覆盖）。
        self._clock = clock_fn if clock_fn is not None else time.monotonic
        self.ser = ser if ser is not None else serial.Serial(port, baud, timeout=0.05, write_timeout=0.1)
        self.proto = proto
        self.state = None            # 最近一次完整 $CAR 解析结果
        self.state_seq = 0           # 每收到一个新的合法 $CAR 单调递增
        self.state_rx_time = None    # 最近合法 $CAR 的本地单调时刻
        self.suppressed = False      # True=已撤销运动许可，等待PREL及其后的新请求
        self._lock = threading.Lock()
        self._cmd = (0, 0, False, 0, 0)   # L,R,V,MM,IR（上游请求缓存）
        self._cmd_ms = None               # 上游 drive() 最近更新时刻
        self._sample_ms = None            # PL 真实传感器样本时刻
        self._rxbuf = bytearray()         # 接收字节缓存（跨 read 调用）
        self._rx_ms = None                # 缓存非空时的最近字节时刻
        self._stop_flag = False
        self._rel_flag = False
        self._await_new_intent = False  # 已发送PREL，等待释放后的新驾驶请求
        self._new_intent = False        # 仅记录上述等待阶段内到达的新请求
        self._running = False
        self._seq = 0
        self._thread = None
        self.dropped_tx = 0               # STM32 回报的 $P 校验失败计数
        self.transport_error = None
        self._closed = False

    # ── 上游接口 ──
    def drive(self, left: int, right: int, valid: bool, mm: int,
              ir: int = 0, sample_ts: float = None):
        """更新驾驶请求与传感器快照。

        sample_ts：PL 产生该样本的时刻（time.monotonic 基准）。调用方应传
        真实采样时刻而不是“现在”——否则采集冻结会被 UART 心跳掩盖。
        传 None 时以当前时刻近似（仅适用于 PL 与 PS 同步采样的场景）。
        """
        now = self._clock()
        with self._lock:
            self._cmd = (left, right, bool(valid), mm, ir & 3)
            self._cmd_ms = now
            self._sample_ms = now if sample_ts is None else sample_ts
            if self._await_new_intent:
                self._new_intent = True

    def stop_request(self):
        with self._lock:
            self._stop_flag = True
            self._rel_flag = False

    def release_request(self):
        """请求 STM32 重新解锁；本端仍保持零速，等待之后的新驾驶请求。"""
        with self._lock:
            self._rel_flag = True

    def update_sample(self, valid, mm, ir, sample_ts):
        """仅提交真实采样时刻；采集轮询不得续租旧驾驶请求。"""
        with self._lock:
            left, right, _, _, _ = self._cmd
            self._cmd = (left, right, bool(valid), mm, ir & 3)
            self._sample_ms = sample_ts

    def update_command(self, left, right):
        """仅在收到新的驾驶意图时调用；不会刷新传感器年龄。"""
        if not all(-SAFE_MAX_PWM <= v <= SAFE_MAX_PWM for v in (left, right)):
            raise ValueError('PWM out of range')
        with self._lock:
            _, _, valid, mm, ir = self._cmd
            self._cmd = (left, right, valid, mm, ir)
            self._cmd_ms = self._clock()
            if self._await_new_intent:
                self._new_intent = True

    def close(self):
        if self._closed:
            return
        self._running = False
        if self._thread:
            self._thread.join(timeout=self.PERIOD * 4)
        alive = self._thread is not None and self._thread.is_alive()
        if alive:
            for name in ('cancel_read', 'cancel_write'):
                cancel = getattr(self.ser, name, None)
                if cancel:
                    try: cancel()
                    except OSError: pass
            self.ser.close()
            self._thread.join(timeout=self.PERIOD * 4)
            self._closed = True
            if self._thread.is_alive():
                raise RuntimeError('UART worker did not terminate after cancellation')
            raise OSError('UART shutdown needed cancellation; final STOP unconfirmed')
        error = None
        try:
            # No worker can race this final STOP with an old drive frame.
            written = self.ser.write(b'$PSTOP#')
            if written is not None and written != 7:
                raise OSError('short UART STOP write during shutdown')
        except (OSError, ValueError) as exc:
            error = exc
            self.transport_error = str(exc)
        finally:
            self.ser.close()
            self._closed = True
        if error is not None:
            raise OSError('final UART STOP could not be submitted') from error

    def status_snapshot(self):
        """Return state, sequence and receive timestamp from one RX commit."""
        with self._lock:
            return (dict(self.state) if self.state is not None else None,
                    self.state_seq, self.state_rx_time)

    def limit_command(self, left, right):
        """Retract/limit cached PWM without renewing age or creating intent.

        Each component can only keep its sign and reduce magnitude. A
        supervisor must receive a fresh upstream request before increasing it.
        """
        with self._lock:
            old_left, old_right, valid, mm, ir = self._cmd
            for old, new in ((old_left, left), (old_right, right)):
                if (isinstance(new, bool) or not isinstance(new, int)
                        or abs(new) > abs(old) or (old * new < 0)):
                    raise ValueError('limit_command may only reduce cached PWM')
            self._cmd = (left, right, valid, mm, ir)

    # ── 后台线程 ──
    def start(self):
        if self._closed or self._thread is not None:
            raise RuntimeError('CarLink requires a new instance after stop or failure')
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _decide(self, now):
        """在锁内取快照并判定本拍应发送的内容。
        返回 (frame_kind, payload)：kind ∈ {'stop','rel','idle','idle_ok','drive'}。"""
        with self._lock:
            cmd = self._cmd
            cmd_age = (now - self._cmd_ms) if self._cmd_ms is not None else float('inf')
            sample_age = (now - self._sample_ms) if self._sample_ms is not None else float('inf')
            if self._stop_flag:
                self._stop_flag = False
                self.suppressed = True
                self._rel_flag = False
                self._await_new_intent = False
                self._new_intent = False   # STOP 取消待决解锁与旧意图
                return 'stop', None
            stale = (not math.isfinite(sample_age) or not math.isfinite(cmd_age)
                     or not 0 <= sample_age < self.SAMPLE_MAX_AGE
                     or not 0 <= cmd_age < self.CMD_MAX_AGE)
            if stale:
                # 撤销运动许可：零速 + V=0（STM32 按传感器无效锁存停车）。
                # 旧值不得继续充当新鲜样本重发；恢复需重新提交采样/零速请求，
                # 满足安全保持后PREL，最后再提交一条新的驾驶请求。
                self.suppressed = True
                self._cmd_ms = None      # 冻结请求时间，防止旧值恢复发送
                self._sample_ms = None
                self._rel_flag = False
                self._await_new_intent = False
                self._new_intent = False
                return 'idle', None
            if not cmd[2]:
                self.suppressed = True
                self._rel_flag = False
                self._await_new_intent = False
                self._new_intent = False
                return 'idle', None
            if cmd[4]:
                # 保留真实有效的IR位和距离，让STM32记录FAULT_IR；速度强制为0。
                # 用V=0会把故障来源错误地降格成FAULT_SENSOR并丢失IR诊断。
                self.suppressed = True
                self._rel_flag = False
                self._await_new_intent = False
                self._new_intent = False
                return 'idle_ok', (0, 0, True, cmd[3], cmd[4])
            if self._rel_flag:
                self._rel_flag = False
                if cmd[3] >= 250:
                    # Release authorizes the stopped state, never cached motion.
                    # 心跳维持 V=1 零速并续租（样本与命令都保持新鲜：STM32 不因
                    # 数据超龄/租约反复锁存——DEF-A-01/A-02）。
                    self._cmd = (0, 0, cmd[2], cmd[3], cmd[4])
                    self._cmd_ms = self._clock()
                    self.suppressed = True
                    self._await_new_intent = True
                    self._new_intent = False
                    return 'rel', None
            if self.suppressed:
                # 抑制态：维持零速有效帧。只有显式新驾驶意图（解锁后）
                # 才恢复请求的驱动量；恢复前提是当前已不在 STM32 锁存
                # （由 $PREL#/$CAR 流程外部保证）。
                if self._await_new_intent and self._new_intent:
                    self.suppressed = False
                    self._await_new_intent = False
                    self._new_intent = False
                    return 'drive', cmd
                return 'idle_ok', (0, 0, cmd[2], cmd[3], cmd[4])
            return 'drive', cmd

    def _loop(self):
        next_tick = self._clock()
        while self._running:
            try:
                now = self._clock()
                if now >= next_tick:
                    self._send_once(now)
                    next_tick = now + self.PERIOD
                self._process_rx(self._clock())
            except (OSError, ValueError) as exc:
                self.transport_error = str(exc)
                self.stop_request()
                self._running = False

    def _send_once(self, now):
        """One production TX transaction, also used by deterministic C tests."""
        kind, payload = self._decide(now)
        if kind == 'stop':
            frame = b"$PSTOP#"
        elif kind == 'rel':
            frame = b"$PREL#"
        else:
            self._seq = (self._seq + 1) % 10
            if kind in ('drive', 'idle_ok'):
                L, R, V, MM, IR = payload
                frame = build_p(L, R, V, MM, self._seq, IR, self.proto)
            else:
                frame = build_p(0, 0, False, 0, self._seq, 0, self.proto)
        written = self.ser.write(frame)
        if written is not None and written != len(frame):
            raise OSError('short UART write')
        return kind

    # ── 接收：跨调用缓存，按 $/# 提取完整帧 ──
    def _process_rx(self, now):
        data = self.ser.read(256)
        if data:
            self._rxbuf += data
            self._rx_ms = now
        while True:
            i = self._rxbuf.find(b'$')
            if i < 0:
                self._rxbuf.clear()
                return
            if i:
                del self._rxbuf[:i]          # 丢弃前导垃圾
            j = self._rxbuf.find(b'#')
            next_start = self._rxbuf.find(b'$', 1)
            if next_start >= 0 and (j < 0 or next_start < j):
                del self._rxbuf[:next_start]
                continue
            if j < 0:
                # 残帧：超长或超时未完成即丢弃重同步
                if len(self._rxbuf) > self.RX_MAX or (
                        self._rx_ms is not None and now - self._rx_ms > self.RX_STALE):
                    self._rxbuf.clear()
                    self._rx_ms = None
                return
            frame = bytes(self._rxbuf[:j + 1])
            del self._rxbuf[:j + 1]
            if len(frame) > self.RX_MAX:
                continue
            st = parse_car(frame)
            if st is not None:
                with self._lock:
                    self.state = st
                    self.state_seq += 1
                    self.state_rx_time = now
                    if st["drop"]:
                        self.dropped_tx = st["drop"]


def crc16(body):
    """CRC-16/CCITT-FALSE, ASCII bytes, initial 0xffff, polynomial 0x1021."""
    crc = 0xffff
    for byte in body.encode('ascii') if isinstance(body, str) else body:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xffff
    return crc


def hybrid_frame(kind, session, sequence, *values):
    if kind not in ('Q1', 'D1', 'R1'):
        raise ValueError('unknown hybrid command')
    if type(session) is not int or not 1 <= session <= 0xffffffff:
        raise ValueError('invalid session')
    if type(sequence) is not int or not 0 <= sequence <= 0xffffffff:
        raise ValueError('invalid sequence')
    if len(values) != (2 if kind == 'D1' else 0):
        raise ValueError('invalid command field count')
    if any(type(v) is not int or not -2400 <= v <= 2400 for v in values):
        raise ValueError('invalid PWM')
    body = '$' + ','.join(map(str, (kind, session, sequence, *values)))
    return f'{body},{crc16(body):04X}#'.encode('ascii')


def parse_sensor_report(frame):
    """S1 carries actual local sensors AND actual executor state; no CAR echo."""
    try:
        text = frame.decode('ascii')
        if len(text) > 180 or not re.fullmatch(r'\$S1,\d+,\d+,\d+,\d+,\d+,\d+,\d+,\d+,\d+,\d+,-?\d+,-?\d+,\d+,\d+,\d+,[0-9A-F]{4}#', text):
            return None
        body, check = text[:-1].rsplit(',', 1)
        if crc16(body) != int(check, 16):
            return None
        values = list(map(int, body[4:].split(',')))
        limits = [(1, 0xffffffff), (0, 0xffffffff), (0, 0xffffffff),
                  (0, 65535), (0, 1), (0, 4095), (0, 0xffffffff),
                  (0, 65535), (0, 1), (0, 3), (-2400, 2400),
                  (-2400, 2400), (0, 1), (0, 65535), (0, 65535)]
        if len(values) != len(limits) or any(not lo <= v <= hi for v, (lo, hi) in zip(values, limits)):
            return None
        return dict(zip(('session', 'request', 'us_seq', 'us_age_ms', 'us_valid',
                         'mm', 'ir_seq', 'ir_age_ms', 'ir_valid', 'ir',
                         'left', 'right', 'lock', 'fault', 'drop'), values))
    except (UnicodeError, ValueError):
        return None


class HybridCarLink(CarLink):
    """v3, 115200 8N1: fresh request/reply ages bound untrusted RX buffering.

    An S1 reply must match a single outstanding Q1 of this random session,
    arrive within 150 ms, and advance sample sequences. Duplicate samples
    retain their earliest timestamp; queries cannot rejuvenate old sensors.
    Legacy CAR replies cannot update either sensors or actual motor status.
    """
    PERIOD = .05
    REQUEST_MAX_AGE = .150
    IR_MAX_AGE = .100
    RX_MAX = 192

    def __init__(self, port, baud=115200, *, ser=None, clock_fn=None, session=None):
        if baud != 115200:
            raise ValueError('hybrid v3 requires 115200 8N1')
        super().__init__(port, baud=baud, proto='pynq', ser=ser, clock_fn=clock_fn)
        self.proto = 'hybrid'
        self.session = session if session is not None else secrets.randbelow(0xffffffff) + 1
        hybrid_frame('Q1', self.session, 0)  # Validate before any transmission.
        self._query_seq = 0
        self._control_seq = 0
        self._pending = {}
        self._sensors = None
        self.sensor_errors = 0

    def sensor_snapshot(self, now=None):
        now = self._clock() if now is None else now
        with self._lock:
            if self._sensors is None:
                return None
            result = dict(self._sensors)
        result['us_valid'] = bool(result['us_valid'] and
                                 0 <= now - result['us_sample_s'] < self.SAMPLE_MAX_AGE)
        result['ir_valid'] = bool(result['ir_valid'] and
                                 0 <= now - result['ir_sample_s'] < self.IR_MAX_AGE)
        return result

    def start(self):
        if self._running and self._thread is not None and self._thread.is_alive():
            return  # Readiness and the session share the same single owner.
        return super().start()

    def _send_once(self, now):
        self._query_seq = (self._query_seq + 1) & 0xffffffff
        request = self._query_seq
        with self._lock:
            self._pending = {seq: stamp for seq, stamp in self._pending.items()
                             if 0 <= now - stamp < self.REQUEST_MAX_AGE}
            self._pending[request] = now
        packet = hybrid_frame('Q1', self.session, request)
        written = self.ser.write(packet)
        if written is not None and written != len(packet):
            raise OSError('short sensor query write')
        kind, payload = self._decide(now)
        self._control_seq = (self._control_seq + 1) & 0xffffffff
        if kind == 'rel':
            packet = hybrid_frame('R1', self.session, self._control_seq)
        elif kind in ('drive', 'idle_ok'):
            packet = hybrid_frame('D1', self.session, self._control_seq, *payload[:2])
        else:
            packet = b'$PSTOP#'
        written = self.ser.write(packet)
        if written is not None and written != len(packet):
            raise OSError('short hybrid command write')
        return kind

    def _process_rx(self, now):
        data = self.ser.read(256)
        now = self._clock()  # read() can block; timestamp the completed RX.
        if data:
            self._rxbuf += data
        while True:
            start = self._rxbuf.find(b'$')
            if start < 0:
                self._rxbuf.clear(); self._rx_ms = None
                return
            if start:
                del self._rxbuf[:start]
                self._rx_ms = None
            if self._rx_ms is None:
                self._rx_ms = now
            end = self._rxbuf.find(b'#')
            next_start = self._rxbuf.find(b'$', 1)
            if next_start >= 0 and (end < 0 or next_start < end):
                del self._rxbuf[:next_start]; self._rx_ms = now
                continue
            if end < 0:
                if len(self._rxbuf) > self.RX_MAX or now - self._rx_ms >= self.REQUEST_MAX_AGE:
                    self._rxbuf.clear(); self._rx_ms = None
                return
            frame = bytes(self._rxbuf[:end + 1])
            del self._rxbuf[:end + 1]; self._rx_ms = None
            report = parse_sensor_report(frame)
            if report is None or report['session'] != self.session:
                self.sensor_errors += 1
                continue
            with self._lock:
                sent = self._pending.pop(report['request'], None)
                if sent is None or not 0 <= now - sent < self.REQUEST_MAX_AGE:
                    self.sensor_errors += 1
                    continue
                old = self._sensors
                if old is not None:
                    # Replies may arrive out of order; reject both batch replay
                    # and sequence rollback (including STM32 reset).
                    d = (report['request'] - old['request']) & 0xffffffff
                    if not 0 < d < 0x80000000:
                        self.sensor_errors += 1; continue
                    if any((report[k] - old[k]) & 0xffffffff >= 0x80000000
                           for k in ('us_seq', 'ir_seq')):
                        self.sensor_errors += 1; continue
                for channel in ('us', 'ir'):
                    # Request send preceded the MCU snapshot, so this is a
                    # conservative lower bound without mixing clock origins.
                    stamp = sent - report[channel + '_age_ms'] / 1000 - .002
                    if old is not None and report[channel + '_seq'] == old[channel + '_seq']:
                        stamp = min(stamp, old[channel + '_sample_s'])
                        if any(report[k] != old[k] for k in
                               ((channel + '_valid', 'mm') if channel == 'us' else (channel + '_valid', 'ir'))):
                            report[channel + '_valid'] = 0
                    report[channel + '_sample_s'] = stamp
                self._sensors = report
                self.state = {k: report[k] for k in ('left', 'right', 'lock', 'fault', 'mm', 'ir', 'drop')}
                self.state_seq += 1
                self.state_rx_time = sent  # Conservatively includes reply transit.


class MockSerial:
    """单元测试用串口替身：记录写入、按脚本回放读取。"""

    def __init__(self, rx_script=None):
        self.written = []
        self._rx = list(rx_script or [])
        self.closed = False

    def write(self, data):
        self.written.append(bytes(data))

    def read(self, n=1):
        if self._rx:
            return self._rx.pop(0)
        return b""

    def close(self):
        self.closed = True


if __name__ == "__main__":
    # 板上台架自检：不发驱动，只维持零速心跳并打印 $CAR
    link = CarLink("/dev/ttyPS1")
    link.start()
    try:
        while True:
            st = link.state
            if st:
                print(st)
            time.sleep(0.3)
    except KeyboardInterrupt:
        link.close()
