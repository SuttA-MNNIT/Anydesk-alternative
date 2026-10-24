"""Small, fixed Windows input interface. No shell or arbitrary command execution."""
import ctypes
from ctypes import wintypes
import math
import threading

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [("type", wintypes.DWORD), ("value", INPUTUNION)]


KEYS = {f"Key{chr(c)}": c for c in range(65, 91)}
KEYS.update({f"Digit{n}": 48 + n for n in range(10)})
KEYS.update({f"F{n}": 111 + n for n in range(1, 13)})
KEYS.update({"Backspace": 8, "Tab": 9, "Enter": 13, "ShiftLeft": 0xA0, "ShiftRight": 0xA1, "ControlLeft": 0xA2, "ControlRight": 0xA3, "AltLeft": 0xA4, "AltRight": 0xA5, "Space": 32, "PageUp": 33, "PageDown": 34, "End": 35, "Home": 36, "ArrowLeft": 37, "ArrowUp": 38, "ArrowRight": 39, "ArrowDown": 40, "Insert": 45, "Delete": 46, "MetaLeft": 0x5B, "MetaRight": 0x5C, "CapsLock": 0x14, "NumLock": 0x90, "ScrollLock": 0x91, "Semicolon": 0xBA, "Equal": 0xBB, "Comma": 0xBC, "Minus": 0xBD, "Period": 0xBE, "Slash": 0xBF, "Backquote": 0xC0, "BracketLeft": 0xDB, "Backslash": 0xDC, "BracketRight": 0xDD, "Quote": 0xDE})
KEYS.update({f"Numpad{n}": 0x60 + n for n in range(10)})
KEYS.update({"NumpadMultiply": 0x6A, "NumpadAdd": 0x6B, "NumpadSubtract": 0x6D, "NumpadDecimal": 0x6E, "NumpadDivide": 0x6F, "NumpadEnter": 13})
EXTENDED = {"ControlRight", "AltRight", "MetaLeft", "MetaRight", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", "Insert", "Delete", "NumpadDivide", "NumpadEnter", "NumLock"}


class Controller:
    def __init__(self):
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        self.user32.SendInput.restype = wintypes.UINT
        self.user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
        self.user32.SetCursorPos.restype = wintypes.BOOL
        self.keys = set()
        self.buttons = set()
        self.lock = threading.RLock()

    def _send(self, item):
        if self.user32.SendInput(1, ctypes.byref(item), ctypes.sizeof(INPUT)) != 1:
            raise OSError("Windows blocked remote input. Elevated windows and the secure desktop are not supported.")

    def _key(self, code, down):
        if code not in KEYS:
            return
        flags = (0 if down else 2) | (1 if code in EXTENDED else 0)
        self._send(INPUT(type=1, ki=KEYBDINPUT(wVk=KEYS[code], dwFlags=flags)))
        if down:
            self.keys.add(code)
        else:
            self.keys.discard(code)

    def _button(self, button, down):
        flags = {(0, True): 2, (0, False): 4, (1, True): 0x20, (1, False): 0x40, (2, True): 8, (2, False): 16}
        if (button, down) not in flags:
            return
        self._send(INPUT(type=0, mi=MOUSEINPUT(dwFlags=flags[(button, down)])))
        if down:
            self.buttons.add(button)
        else:
            self.buttons.discard(button)

    def _move(self, msg):
        x, y = msg.get("x"), msg.get("y")
        if isinstance(x, bool) or isinstance(y, bool) or not isinstance(x, (int, float)) or not isinstance(y, (int, float)) or not math.isfinite(x) or not math.isfinite(y) or not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError("Invalid pointer coordinates")
        width, height = self.user32.GetSystemMetrics(0), self.user32.GetSystemMetrics(1)
        if not self.user32.SetCursorPos(round(x * (width - 1)), round(y * (height - 1))):
            raise OSError("Windows blocked pointer input")

    def handle(self, msg):
        with self.lock:
            kind = msg.get("type")
            if kind == "move":
                self._move(msg)
            elif kind == "button":
                if type(msg.get("button")) is not int or type(msg.get("down")) is not bool:
                    raise ValueError("Invalid button event")
                self._move(msg)
                self._button(msg["button"], msg["down"])
            elif kind == "key":
                if type(msg.get("down")) is not bool or not isinstance(msg.get("code"), str):
                    raise ValueError("Invalid key event")
                self._key(msg["code"], msg["down"])
            elif kind == "wheel":
                delta = msg.get("delta")
                if type(delta) is not int or abs(delta) > 1200:
                    raise ValueError("Invalid scroll event")
                self._send(INPUT(type=0, mi=MOUSEINPUT(mouseData=delta & 0xFFFFFFFF, dwFlags=0x800)))
            elif kind == "release":
                self.release()

    def release(self):
        with self.lock:
            for code in list(self.keys):
                try:
                    self._key(code, False)
                except OSError:
                    pass
            for button in list(self.buttons):
                try:
                    self._button(button, False)
                except OSError:
                    pass
            self.keys.clear()
            self.buttons.clear()
