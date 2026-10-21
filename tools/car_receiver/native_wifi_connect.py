"""Request the existing profile with Windows Native Wi-Fi; no profile edits."""
import ctypes
from ctypes import wintypes as w
import time
import uuid

class GUID(ctypes.Structure):
    _fields_=[('a',w.DWORD),('b',w.WORD),('c',w.WORD),('d',ctypes.c_ubyte*8)]
class Parameters(ctypes.Structure):
    _fields_=[('mode',w.DWORD),('profile',w.LPCWSTR),('ssid',ctypes.c_void_p),
              ('bssids',ctypes.c_void_p),('bss_type',w.DWORD),('flags',w.DWORD)]

def request(profile):
    api=ctypes.WinDLL('wlanapi.dll')
    api.WlanOpenHandle.argtypes=[w.DWORD,ctypes.c_void_p,ctypes.POINTER(w.DWORD),ctypes.POINTER(w.HANDLE)]
    api.WlanOpenHandle.restype=w.DWORD
    api.WlanScan.argtypes=[w.HANDLE,ctypes.POINTER(GUID),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p]
    api.WlanConnect.argtypes=[w.HANDLE,ctypes.POINTER(GUID),ctypes.POINTER(Parameters),ctypes.c_void_p]
    api.WlanConnect.restype=w.DWORD
    api.WlanCloseHandle.argtypes=[w.HANDLE,ctypes.c_void_p]
    handle=w.HANDLE();version=w.DWORD()
    opened=api.WlanOpenHandle(2,None,ctypes.byref(version),ctypes.byref(handle))
    record={'method':'Windows Native Wi-Fi','open_code':opened,'profile_changed':False}
    if opened:return record,lambda:None
    guid=GUID.from_buffer_copy(uuid.UUID('d9371623-0cd9-40f1-990a-ee99d29a8960').bytes_le)
    record['scan_code']=api.WlanScan(handle,ctypes.byref(guid),None,None,None)
    if record['scan_code']==0:time.sleep(4)
    params=Parameters(0,profile,None,None,1,0)
    record['connect_code']=api.WlanConnect(handle,ctypes.byref(guid),ctypes.byref(params),None)
    return record,lambda:api.WlanCloseHandle(handle,None)
