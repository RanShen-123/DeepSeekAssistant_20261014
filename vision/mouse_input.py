"""Windows 物理像素单击；导入模块不会操作桌面。"""
import ctypes
from ctypes import wintypes
import sys


def escape_pressed():
    return sys.platform == "win32" and bool(ctypes.windll.user32.GetAsyncKeyState(0x1B) & 0x8000)


def click_physical(x, y, cancelled):
    if sys.platform != "win32":
        raise RuntimeError("鼠标测试仅支持 Windows。")
    if type(x) is not int or type(y) is not int:
        raise ValueError("屏幕点击坐标必须为整数。")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    pointer_uint = ctypes.c_size_t

    class MouseInput(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", pointer_uint)]

    class KeyInput(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", pointer_uint)]

    class HardwareInput(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

    class InputUnion(ctypes.Union):
        _fields_ = [("mi", MouseInput), ("ki", KeyInput), ("hi", HardwareInput)]

    class Input(ctypes.Structure):
        _anonymous_ = ("data",)
        _fields_ = [("type", wintypes.DWORD), ("data", InputUnion)]

    user32.SetPhysicalCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    user32.SetPhysicalCursorPos.restype = wintypes.BOOL
    user32.GetPhysicalCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.GetPhysicalCursorPos.restype = wintypes.BOOL
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    if cancelled():
        raise RuntimeError("已停止，未点击。")
    if not user32.SetPhysicalCursorPos(x, y):
        raise OSError("无法将鼠标定位到控件。")
    point = wintypes.POINT()
    if not user32.GetPhysicalCursorPos(ctypes.byref(point)) or (point.x, point.y) != (x, y):
        raise RuntimeError("鼠标位置与目标坐标不一致，未点击。")
    if cancelled():
        raise RuntimeError("已停止，未点击。")
    events = (Input * 2)()
    events[0].mi.dwFlags = 0x0002  # 左键按下
    events[1].mi.dwFlags = 0x0004  # 左键释放
    sent = user32.SendInput(2, events, ctypes.sizeof(Input))
    if sent != 2:
        if sent == 1:
            release = (Input * 1)()
            release[0].mi.dwFlags = 0x0004
            user32.SendInput(1, release, ctypes.sizeof(Input))
        raise OSError("鼠标输入未完整发送，已停止且不重试。")
