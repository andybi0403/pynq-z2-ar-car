"""Cancellation and single-instance ownership for the desktop connector."""
import ctypes
import os
import subprocess
import time


class ConnectionCancelled(RuntimeError):
    pass


def check_cancel(event):
    if event is not None and event.is_set():
        raise ConnectionCancelled('连接已取消')


def pause(seconds, event=None):
    if event is None:
        time.sleep(seconds)
    elif event.wait(seconds):
        check_cancel(event)


def hidden_process_options():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


class LauncherOwnership:
    """Keep ownership through cancellation cleanup, so two launchers cannot race Wi-Fi."""
    def __enter__(self):
        self.handle = None
        self.acquired = True
        if os.name == 'nt':
            from ctypes import wintypes as w
            self.api = ctypes.WinDLL('kernel32', use_last_error=True)
            self.api.CreateMutexW.argtypes = [ctypes.c_void_p, w.BOOL, w.LPCWSTR]
            self.api.CreateMutexW.restype = w.HANDLE
            self.api.CloseHandle.argtypes = [w.HANDLE]
            self.handle = self.api.CreateMutexW(None, False, 'Local\\PynqCarConsoleLauncher')
            if not self.handle:
                raise ctypes.WinError(ctypes.get_last_error())
            self.acquired = ctypes.get_last_error() != 183
        return self

    def __exit__(self, *args):
        if self.handle:
            self.api.CloseHandle(self.handle)


def foreground_launcher():
    if os.name == 'nt':
        from ctypes import wintypes as w
        api = ctypes.WinDLL('user32')
        api.FindWindowW.argtypes = [w.LPCWSTR, w.LPCWSTR]
        api.FindWindowW.restype = w.HWND
        api.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
        api.SetForegroundWindow.argtypes = [w.HWND]
        handle = api.FindWindowW(None, 'PYNQ 小车连接')
        if handle:
            api.ShowWindow(handle, 9)
            api.SetForegroundWindow(handle)
