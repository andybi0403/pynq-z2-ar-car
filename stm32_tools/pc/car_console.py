"""USB 有线上位机：Tkinter 界面 + 非阻塞串口，100 ms 控制周期。"""
import re
import time
import tkinter as tk
from tkinter import ttk, messagebox
import serial
from serial.tools import list_ports


def motion(command):
    return f'${command},0,0,0,0,0,0,0,0,0#'.encode('ascii')


KEY_COMMANDS = {'Up': 1, 'Down': 2, 'Left': 3, 'Right': 4}


def parse_status(line):
    match = re.fullmatch(rb'\$SAFE,MS(\d+),IR(\d+),MM(\d+),VALID([01]),LOCK([01]),FAULT(\d+),CMD(\d+),PWM(\d+),USB([01])#', line.strip())
    if not match:
        return None
    return dict(zip(('MS','IR','MM','VALID','LOCK','FAULT','CMD','PWM','USB'), map(int, match.groups())))


class Console:
    def __init__(self, root):
        self.root = root
        self.link = None
        self.buffer = b''
        self.command = 0
        self.status = None
        self.last_rx = 0
        self.last_ms = None
        self.last_tx = 0
        self.releasing_bluetooth = False
        self.release_job = None
        # 记录实际按下的方向键。使用列表而不是单个布尔量，便于处理
        # 用户在松开一个键前又按下另一个键的情况。
        self.pressed_keys = []
        self.active_key = None
        root.title('STM32 小车 · USB 有线控制')
        root.geometry('680x510')
        root.option_add('*Font', ('Microsoft YaHei UI', 11))
        box = ttk.Frame(root, padding=20)
        box.pack(fill='both', expand=True)
        ttk.Label(box, text='BST-4WD 小车控制台', font=('Microsoft YaHei UI', 20, 'bold')).pack(anchor='w')
        ttk.Label(box, text='电脑 USB → 扩展板 Micro-USB（CH340） · 115200 / 8N1').pack(anchor='w', pady=8)
        row = ttk.Frame(box); row.pack(fill='x', pady=8)
        self.port = ttk.Combobox(row, width=15, state='readonly'); self.port.pack(side='left')
        ttk.Button(row, text='刷新串口', command=self.refresh).pack(side='left', padx=6)
        ttk.Button(row, text='连接', command=self.connect).pack(side='left')
        ttk.Button(row, text='断开', command=self.disconnect).pack(side='left', padx=6)
        self.info = tk.StringVar(value='未连接；请先把车轮悬空，再进行首次测试。')
        ttk.Label(box, textvariable=self.info, wraplength=620).pack(anchor='w', pady=12)
        self.readout = tk.StringVar(value='等待带 USB 标记的新固件状态…')
        ttk.Label(box, textvariable=self.readout, wraplength=620).pack(anchor='w', pady=8)
        pad = ttk.Frame(box); pad.pack(pady=12)
        self.buttons = []
        for title, cmd, r, c in [('按住前进',1,0,1),('按住左转',3,1,0),('按住后退',2,1,1),('按住右转',4,1,2)]:
            b = ttk.Button(pad, text=title, width=14, state='disabled')
            b.grid(row=r,column=c,padx=5,pady=5)
            b.bind('<ButtonPress-1>', lambda e, v=cmd: self.drive(v))
            b.bind('<ButtonRelease-1>', lambda e: self.stop())
            b.bind('<Leave>', lambda e: self.stop())
            self.buttons.append(b)
        row = ttk.Frame(box); row.pack(pady=10)
        ttk.Button(row, text='人工解锁（安全条件满足后）', command=self.arm).pack(side='left', padx=6)
        ttk.Button(row, text='紧急停车 / 锁定', command=self.halt).pack(side='left', padx=6)
        self.bluetooth_button = ttk.Button(row, text='切回蓝牙（锁车）', command=self.switch_to_bluetooth,
                                           state='disabled')
        self.bluetooth_button.pack(side='left', padx=6)
        ttk.Label(box, text='松开方向按钮或键盘方向键即停止；窗口失焦会锁车。\n红外、超声波故障优先于驾驶。PWM 是输出量，不是真实速度。').pack(anchor='w', pady=8)
        root.bind('<FocusOut>', lambda e: root.after_idle(self.focus_check))
        root.bind('<space>', lambda e: self.halt())
        # 方向键采用“按住才运动”的方式：按下后由 tick() 每 100 ms
        # 续发，松开立即发送 IDLE。bind_all 使焦点在按钮或窗口其他区域
        # 时也能收到方向键事件。
        for key in KEY_COMMANDS:
            root.bind_all(f'<KeyPress-{key}>', lambda e, k=key: self.key_press(k), add='+')
            root.bind_all(f'<KeyRelease-{key}>', lambda e, k=key: self.key_release(k), add='+')
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh()
        root.after(25, self.tick)

    def refresh(self):
        ports = list(list_ports.comports())
        self.port['values'] = [p.device for p in ports]
        best = next((p.device for p in ports if 'CH340' in p.description), ports[0].device if ports else '')
        self.port.set(best)

    def connect(self):
        self.disconnect()
        try:
            link = serial.Serial(port=None, baudrate=115200, timeout=0, write_timeout=0.05)
            link.dtr = False; link.rts = False
            link.port = self.port.get(); link.open()
            self.link = link
            self.buffer = b''; self.status = None; self.last_ms = None; self.last_rx = 0
            self.send(b'$HALT#')
            self.info.set('已打开串口，等待新固件回应。连接本身不会解锁。')
        except (serial.SerialException, ValueError, OSError) as exc:
            self.disconnect(); messagebox.showerror('连接失败', str(exc))

    def send(self, data):
        if self.link:
            try:
                if self.link.write(data) != len(data):
                    raise serial.SerialException('发送不完整')
            except (serial.SerialException, OSError) as exc:
                self.link.close(); self.link = None; self.command = 0; self.status = None
                self.info.set('串口中断：' + str(exc))

    def ready(self):
        return bool(self.link and self.status and self.status['USB'] and not self.status['LOCK']
                    and not self.releasing_bluetooth and time.monotonic()-self.last_rx < 0.8)

    def drive(self, cmd):
        if self.ready():
            self.command = cmd; self.send(motion(cmd))

    def key_press(self, key):
        """处理一个方向键按下事件；返回 break 防止控件重复处理。"""
        if key not in KEY_COMMANDS:
            return
        if key in self.pressed_keys:
            # Windows 的按键自动重复只需要保持当前方向，不必重复追加。
            return 'break'
        self.pressed_keys.append(key)
        self.active_key = key
        self.drive(KEY_COMMANDS[key])
        return 'break'

    def key_release(self, key):
        """处理方向键松开；没有其他方向键时立即停车。"""
        if key not in KEY_COMMANDS:
            return
        if key in self.pressed_keys:
            self.pressed_keys.remove(key)
        if self.active_key == key:
            if self.pressed_keys:
                self.active_key = self.pressed_keys[-1]
                self.drive(KEY_COMMANDS[self.active_key])
            else:
                self.active_key = None
                self.stop()
        return 'break'

    def stop(self):
        self.command = 0
        if not self.releasing_bluetooth:
            self.send(b'$IDLE#')

    def halt(self):
        self.command = 0
        self.pressed_keys.clear()
        self.active_key = None
        if self.status:
            self.status['LOCK'] = 1
        if not self.releasing_bluetooth:
            self.send(b'$HALT#')

    def arm(self):
        self.command = 0
        if self.link and self.status and self.status['USB'] and time.monotonic()-self.last_rx < 0.8:
            self.send(b'$ARM#')
            self.info.set('已请求解锁；由板端检查距离、红外及数据有效性。')

    def switch_to_bluetooth(self):
        if not (self.link and self.status and self.status['USB']):
            return
        self.command = 0
        self.pressed_keys.clear()
        self.active_key = None
        self.releasing_bluetooth = True
        self.send(b'$BT#')
        self.info.set('正在锁车并切回蓝牙；控制台将自动断开。')
        self.release_job = self.root.after(150, self.finish_bluetooth_release)

    def finish_bluetooth_release(self):
        self.release_job = None
        if self.link:
            self.link.close()
        self.link = None; self.status = None; self.command = 0
        self.releasing_bluetooth = False
        self.info.set('已切回蓝牙并锁车；请在手机端重新发送停止指令后解锁。')

    def focus_check(self):
        if self.root.focus_displayof() is None:
            self.halt()

    def disconnect(self):
        releasing = self.releasing_bluetooth
        if self.release_job:
            self.root.after_cancel(self.release_job)
            self.release_job = None
        self.releasing_bluetooth = False
        if not releasing:
            self.halt()
        if self.link:
            self.link.close()
        self.link = None; self.status = None; self.command = 0
        self.info.set('未连接')

    def close(self):
        self.disconnect(); self.root.destroy()

    def tick(self):
        now = time.monotonic()
        try:
            if self.link:
                self.buffer += self.link.read(min(self.link.in_waiting, 4096))
                if len(self.buffer)>8192:
                    self.buffer=b''; self.halt()
                while b'\n' in self.buffer:
                    line, self.buffer = self.buffer.split(b'\n',1)
                    state = parse_status(line)
                    if state and state['MS'] != self.last_ms:
                        self.last_rx=now; self.last_ms=state['MS']; self.status=state
                        if state['LOCK']:
                            self.command=0
                        distance = str(state['MM'])+' mm' if state['VALID'] else '无效'
                        faults = [name for bit,name in [(1,'上电/人工锁定'),(2,'红外障碍'),(4,'距离过近'),(8,'测距无效/过期'),(16,'通信超时'),(32,'报文错误'),(64,'模式请求')] if state['FAULT'] & bit]
                        left_ir = '检测到障碍' if state['IR'] & 1 else '无遮挡'
                        right_ir = '检测到障碍' if state['IR'] & 2 else '无遮挡'
                        self.readout.set(
                            f"前方距离：{distance}    PWM：{state['PWM']}\n"
                            f"左红外：{left_ir}    右红外：{right_ir}\n"
                            f"停车原因：{'、'.join(faults) or '无'}")
                        self.info.set('USB 控制 · '+('已锁定，请人工解锁' if state['LOCK'] else '已解锁，可按住方向按钮'))
                if not self.releasing_bluetooth and now-self.last_rx>=0.8:
                    self.command=0
                    self.send(b'$HALT#')
                    self.info.set('状态未更新：已禁止驾驶。请确认新固件已烧录并运行。')
                if not self.releasing_bluetooth and now-self.last_tx>=0.1:
                    self.send(motion(self.command) if self.command and self.ready() else b'$IDLE#')
                    self.last_tx=now
        except (serial.SerialException, OSError) as exc:
            self.disconnect(); self.info.set('读取失败：'+str(exc))
        for b in self.buttons:
            b.configure(state='normal' if self.ready() else 'disabled')
        self.bluetooth_button.configure(
            state='normal' if self.link and self.status and self.status['USB'] and not self.releasing_bluetooth else 'disabled')
        self.root.after(25,self.tick)


if __name__ == '__main__':
    root=tk.Tk(); Console(root); root.mainloop()
