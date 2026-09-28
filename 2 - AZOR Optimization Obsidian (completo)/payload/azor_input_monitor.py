"""AZOR Input Monitor - live peripheral state and real polling-rate measurement.

Why this exists
---------------
The Input Lab could only light up a key while the browser window happened to be
focused, and the polling rate was always reported as "not measured". Windows
Raw Input delivers one message per HID report, so reading it directly gives the
visualiser real device events and gives the polling rate an actually measured
number instead of the value printed on the box.

Privacy - non negotiable
------------------------
This module is deliberately built so that it *cannot* work as a keylogger:

* There is exactly one slot for keyboard identity (`_keys_down`, the set of keys
  physically held right now) plus a counter. No sequence, ordering or history of
  keystrokes is ever assembled, so the typed text does not exist in memory.
* Nothing here writes to disk, and nothing here opens a socket.
* It only runs while the Input Lab page is open: the page sends a heartbeat and
  a watchdog shuts the listener down a few seconds after the heartbeat stops.
* Text input is not distinguishable from any other key here - the module stores
  a display label such as "A" or "SHIFT" for the currently-held key and drops it
  the moment the key is released.

Everything stays in this process, on this machine, in memory.
"""
from __future__ import annotations

import ctypes
import threading
import time
from collections import deque
from ctypes import wintypes
from typing import Any, Dict, List, Optional

IS_WINDOWS = hasattr(ctypes, "windll")

# --- Win32 constants ------------------------------------------------------
WM_INPUT = 0x00FF
WM_TIMER = 0x0113
WATCHDOG_TIMER_ID = 1
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
HWND_MESSAGE = -3
RIDEV_INPUTSINK = 0x00000100
RIDEV_REMOVE = 0x00000001
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
RIM_TYPEKEYBOARD = 1

RI_MOUSE_LEFT_BUTTON_DOWN = 0x0001
RI_MOUSE_LEFT_BUTTON_UP = 0x0002
RI_MOUSE_RIGHT_BUTTON_DOWN = 0x0004
RI_MOUSE_RIGHT_BUTTON_UP = 0x0008
RI_MOUSE_MIDDLE_BUTTON_DOWN = 0x0010
RI_MOUSE_MIDDLE_BUTTON_UP = 0x0020
RI_MOUSE_BUTTON_4_DOWN = 0x0040
RI_MOUSE_BUTTON_4_UP = 0x0080
RI_MOUSE_BUTTON_5_DOWN = 0x0100
RI_MOUSE_BUTTON_5_UP = 0x0200
RI_MOUSE_WHEEL = 0x0400

RI_KEY_BREAK = 0x01  # set on key release
RI_KEY_E0 = 0x02
RI_KEY_E1 = 0x04

MOUSE_BUTTON_EVENTS = (
    (RI_MOUSE_LEFT_BUTTON_DOWN, "left-click", True),
    (RI_MOUSE_LEFT_BUTTON_UP, "left-click", False),
    (RI_MOUSE_RIGHT_BUTTON_DOWN, "right-click", True),
    (RI_MOUSE_RIGHT_BUTTON_UP, "right-click", False),
    (RI_MOUSE_MIDDLE_BUTTON_DOWN, "wheel", True),
    (RI_MOUSE_MIDDLE_BUTTON_UP, "wheel", False),
    (RI_MOUSE_BUTTON_4_DOWN, "side-1", True),
    (RI_MOUSE_BUTTON_4_UP, "side-1", False),
    (RI_MOUSE_BUTTON_5_DOWN, "side-2", True),
    (RI_MOUSE_BUTTON_5_UP, "side-2", False),
)

# Virtual-key -> the label the SVG uses as data-pressable.
VK_LABELS = {
    0x08: "⌫", 0x09: "TAB", 0x0D: "ENTER", 0x10: "SHIFT", 0x11: "CTRL", 0x12: "ALT",
    0x14: "CAPS", 0x1B: "ESC", 0x20: "SPACE", 0x5B: "WIN", 0x5C: "WIN", 0x5D: "MENU",
    0xA0: "SHIFT", 0xA1: "SHIFT", 0xA2: "CTRL", 0xA3: "CTRL", 0xA4: "ALT", 0xA5: "ALT",
    0xBD: "-", 0xBB: "=", 0xDB: "[", 0xDD: "]", 0xDC: "\\", 0xBA: ";", 0xDE: "'",
    0xBC: ",", 0xBE: ".", 0xBF: "/", 0xC0: "`",
    # Setas e bloco de navegacao: o teclado TKL da tela desenha todas, entao elas
    # precisam acender tambem.
    0x25: "\u2190", 0x26: "\u2191", 0x27: "\u2192", 0x28: "\u2193",
    0x2D: "Ins", 0x2E: "Del", 0x24: "Home", 0x23: "End", 0x21: "PgUp", 0x22: "PgDn",
    0x2C: "PrtSc", 0x91: "ScrLk", 0x13: "Pause",
    # Teclas que so existem no ABNT2/ISO: a barra ao lado do Z e a do lado do ponto.
    0xE2: "ISO", 0xC1: "RO",
}

# Posicao FISICA da tecla (scan code), e nao o caractere do layout. O desenho tem
# de acender a tecla que foi apertada: no ABNT2 o VK da tecla do "Ç" e o do ";"
# americano, e a do "/" nem existe no VK_LABELS. O VK fica so de reserva (Pause,
# que chega com prefixo E1).
SCAN_LABELS = {
    0x01: "ESC", 0x0E: "⌫", 0x0F: "TAB", 0x1C: "ENTER", 0x1D: "CTRL", 0x2A: "SHIFT", 0x36: "SHIFT",
    0x38: "ALT", 0x39: "SPACE", 0x3A: "CAPS", 0x46: "ScrLk",
    0x0C: "-", 0x0D: "=", 0x1A: "[", 0x1B: "]", 0x27: ";", 0x28: "'", 0x29: "`", 0x2B: "\\",
    0x33: ",", 0x34: ".", 0x35: "/", 0x56: "ISO", 0x73: "RO", 0x57: "F11", 0x58: "F12",
}
SCAN_LABELS.update({0x02 + i: "1234567890"[i] for i in range(10)})
SCAN_LABELS.update({0x10 + i: c for i, c in enumerate("QWERTYUIOP")})
SCAN_LABELS.update({0x1E + i: c for i, c in enumerate("ASDFGHJKL")})
SCAN_LABELS.update({0x2C + i: c for i, c in enumerate("ZXCVBNM")})
SCAN_LABELS.update({0x3B + i: f"F{i + 1}" for i in range(10)})
SCAN_LABELS_E0 = {
    0x1D: "CTRL", 0x38: "ALT", 0x37: "PrtSc", 0x5B: "WIN", 0x5C: "WIN", 0x5D: "MENU",
    0x47: "Home", 0x48: "↑", 0x49: "PgUp", 0x4B: "←", 0x4D: "→", 0x4F: "End",
    0x50: "↓", 0x51: "PgDn", 0x52: "Ins", 0x53: "Del",
}


def _key_label(make: int, flags: int, vkey: int) -> str:
    if flags & RI_KEY_E1:
        return _vk_label(vkey)
    if flags & RI_KEY_E0:
        # E0 fora da tabela e tecla que o desenho nao tem (Enter e "/" do
        # numerico, o SHIFT falso que acompanha o PrtSc, teclas de midia).
        return SCAN_LABELS_E0.get(make, "")
    if make in SCAN_LABELS:
        return SCAN_LABELS[make]
    if 0x47 <= make <= 0x53:
        return ""  # teclado numerico: com NumLock desligado ele manda VK de seta
    return _vk_label(vkey)


def _vk_label(vkey: int) -> str:
    if vkey in VK_LABELS:
        return VK_LABELS[vkey]
    if 0x30 <= vkey <= 0x39:  # 0-9
        return chr(vkey)
    if 0x41 <= vkey <= 0x5A:  # A-Z
        return chr(vkey)
    if 0x70 <= vkey <= 0x7B:
        return f"F{vkey - 0x6F}"
    return ""


# --- Raw Input structures -------------------------------------------------
class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]


class _RAWMOUSE_BUTTONS(ctypes.Structure):
    _fields_ = [("usButtonFlags", wintypes.USHORT), ("usButtonData", wintypes.SHORT)]


class _RAWMOUSE_UNION(ctypes.Union):
    _fields_ = [("ulButtons", wintypes.ULONG), ("bt", _RAWMOUSE_BUTTONS)]


class RAWMOUSE(ctypes.Structure):
    _fields_ = [("usFlags", wintypes.USHORT), ("u", _RAWMOUSE_UNION),
                ("ulRawButtons", wintypes.ULONG), ("lLastX", wintypes.LONG),
                ("lLastY", wintypes.LONG), ("ulExtraInformation", wintypes.ULONG)]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [("MakeCode", wintypes.USHORT), ("Flags", wintypes.USHORT),
                ("Reserved", wintypes.USHORT), ("VKey", wintypes.USHORT),
                ("Message", wintypes.UINT), ("ExtraInformation", wintypes.ULONG)]


class RAWHID(ctypes.Structure):
    _fields_ = [("dwSizeHid", wintypes.DWORD), ("dwCount", wintypes.DWORD),
                ("bRawData", ctypes.c_ubyte * 1)]


class _RAWINPUT_UNION(ctypes.Union):
    _fields_ = [("mouse", RAWMOUSE), ("keyboard", RAWKEYBOARD), ("hid", RAWHID)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("data", _RAWINPUT_UNION)]


LRESULT = ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]



def _bind_win32() -> None:
    """Declare prototypes explicitly.

    Without argtypes/restype ctypes assumes a 32-bit int return, which silently
    truncates the HWND that CreateWindowExW hands back and makes every later call
    fail. On 64-bit Windows this is the difference between working and not.
    """
    if not IS_WINDOWS:
        return
    u = ctypes.windll.user32
    k = ctypes.windll.kernel32
    u.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    u.RegisterClassExW.restype = wintypes.ATOM
    u.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                  wintypes.DWORD, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                  wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    u.CreateWindowExW.restype = wintypes.HWND
    u.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u.DefWindowProcW.restype = LRESULT
    u.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    u.GetMessageW.restype = ctypes.c_int
    u.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
    u.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
    u.DispatchMessageW.restype = LRESULT
    u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u.PostMessageW.restype = wintypes.BOOL
    u.DestroyWindow.argtypes = [wintypes.HWND]
    u.DestroyWindow.restype = wintypes.BOOL
    u.PostQuitMessage.argtypes = [ctypes.c_int]
    u.SetTimer.argtypes = [wintypes.HWND, ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p]
    u.SetTimer.restype = ctypes.c_void_p
    u.KillTimer.argtypes = [wintypes.HWND, ctypes.c_void_p]
    u.KillTimer.restype = wintypes.BOOL
    u.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
    u.RegisterRawInputDevices.restype = wintypes.BOOL
    u.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID,
                                  ctypes.POINTER(wintypes.UINT), wintypes.UINT]
    u.GetRawInputData.restype = wintypes.UINT
    k.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    k.GetModuleHandleW.restype = wintypes.HMODULE


_bind_win32()


# Windows keeps a raw pointer to every window procedure it has been handed. If
# Python frees one while a window can still receive a message, the next message
# is an access violation - a hard process kill with no traceback. These are
# therefore never released; a handful of tiny callbacks is a fair price.
_LIVE_CALLBACKS: List[Any] = []

HEARTBEAT_TIMEOUT = 8.0   # seconds without a page heartbeat before shutting down
RATE_WINDOW = 1.0         # rolling window used to compute reports/second
# Soltar e apertar de novo o mesmo botao em menos que isto nao e dedo humano (o
# clique duplo mais rapido de gente fica acima de ~50 ms): e o switch do mouse
# "quicando", o defeito classico que vira clique duplo sozinho.
CHATTER_GAP = 0.030
POLLING_CACHE_S = 0.1     # the estimate sorts ~2k intervals; recompute at most 10x/s


class InputMonitor:
    """Owns the message-only window and the raw-input state."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._start_lock = threading.RLock()
        self._generation = 0
        self._thread: Optional[threading.Thread] = None
        self._hwnd = None
        self._running = False
        self._error: Optional[str] = None
        self._last_heartbeat = 0.0
        self._started_at = 0.0

        # --- state the UI renders -------------------------------------
        self._buttons_down: Dict[str, bool] = {}
        # Set of currently-held keys only. Never a sequence: see module docstring.
        self._keys_down: Dict[str, float] = {}
        # Virtual-key code per held label, used only to ask Windows whether the
        # key is still physically down. Cleared with the label.
        self._keys_vk: Dict[str, int] = {}
        self._key_press_count = 0
        # Bumped on every observed change so a reader can send only on change
        # instead of re-sending the same state 60 times a second.
        self._revision = 0
        # O leitor (o stream SSE) dormia 2 ms num laco eterno para descobrir se
        # este contador tinha mexido: 500 despertares por segundo de um processo
        # que, na maior parte do tempo, nao tinha nada a dizer - e que continuava
        # girando com o cliente dentro da partida. Agora o contador acorda quem
        # espera, e ninguem mais gira a toa.
        self._changed = threading.Event()
        self._wheel_at = 0.0
        self._wheel_dir = 0
        self._move_dx = 0
        self._move_dy = 0
        self._last_move_at = 0.0
        # Teste de clique do mouse: contagem por botao e cliques colados no
        # anterior. As chaves sao nomes de botao do mouse, nunca teclas.
        self._clicks: Dict[str, int] = {}
        self._chatter: Dict[str, int] = {}
        self._released_at: Dict[str, float] = {}
        self._move_counts: deque = deque(maxlen=4096)  # (instante, |dx|+|dy|)
        self._polling_cache = (0.0, None)

        # --- timing rings: timestamps only, no identities --------------
        self._mouse_report_ts: deque = deque(maxlen=4096)
        self._kbd_report_ts: deque = deque(maxlen=1024)
        self._mouse_intervals: deque = deque(maxlen=2048)
        self._mouse_total = 0
        self._peak_hz = 0.0

    # -- lifecycle -----------------------------------------------------
    def start(self) -> Dict[str, Any]:
        if not IS_WINDOWS:
            return {"ok": False, "detail": "Disponivel somente no Windows."}
        with self._start_lock:
            self.touch()
            if self._running:
                return {"ok": True, "detail": "Monitor de input ja estava ativo.", "running": True}
            # A previous listener may still be unwinding. Let it finish before a
            # new one exists, so the two can never own state at the same time.
            previous = self._thread
            if previous and previous.is_alive():
                previous.join(timeout=3.0)
                if previous.is_alive():
                    return {"ok": False, "detail": "O monitor anterior ainda esta encerrando. Tente de novo em instantes.", "running": False}
            self._error = None
            self._thread = threading.Thread(target=self._run, name="azor-input-monitor", daemon=True)
            self._thread.start()
        for _ in range(40):
            time.sleep(0.05)
            if self._running or self._error:
                break
        if self._error:
            return {"ok": False, "detail": self._error, "running": False}
        return {"ok": bool(self._running),
                "detail": "Monitor de input ativo. Nenhuma tecla e gravada." if self._running
                          else "O monitor de input nao pode ser iniciado.",
                "running": bool(self._running)}

    def stop(self) -> Dict[str, Any]:
        with self._start_lock:
            with self._lock:
                hwnd = self._hwnd
                thread = self._thread
            if hwnd and IS_WINDOWS:
                try:
                    ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                except Exception:
                    pass
            # Join rather than poll a flag: start() must never overlap a thread
            # that is still inside its teardown.
            if thread and thread.is_alive():
                thread.join(timeout=3.0)
            self._reset_state()
            return {"ok": True, "detail": "Monitor de input encerrado.", "running": bool(self._running)}

    def touch(self) -> None:
        """Heartbeat from the open page."""
        self._last_heartbeat = time.time()

    def _reset_state(self) -> None:
        with self._lock:
            self._buttons_down.clear()
            self._keys_down.clear()
            self._keys_vk.clear()
            self._bump()
            self._mouse_report_ts.clear()
            self._kbd_report_ts.clear()
            self._mouse_intervals.clear()
            self._clicks.clear()
            self._chatter.clear()
            self._released_at.clear()
            self._move_counts.clear()
            self._polling_cache = (0.0, None)

    # -- window / message loop ----------------------------------------
    def _run(self) -> None:
        user32 = ctypes.windll.user32
        hwnd = None
        with self._lock:
            self._generation += 1
            generation = self._generation
        try:
            wndproc = WNDPROC(self._on_message)
            _LIVE_CALLBACKS.append(wndproc)  # never released; see _LIVE_CALLBACKS
            cls = WNDCLASSEXW()
            cls.cbSize = ctypes.sizeof(WNDCLASSEXW)
            cls.lpfnWndProc = wndproc
            cls.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
            # A fresh class per generation: re-registering a class whose window is
            # still being torn down is exactly the case that used to race.
            cls.lpszClassName = f"AzorInputMonitor_{ctypes.windll.kernel32.GetCurrentProcessId()}_{generation}"
            if not user32.RegisterClassExW(ctypes.byref(cls)):
                err = ctypes.GetLastError()
                if err not in (0, 1410):
                    raise OSError(f"RegisterClassExW failed ({err})")
            hwnd = user32.CreateWindowExW(0, cls.lpszClassName, "AZOR Input Monitor",
                                          0, 0, 0, 0, 0, wintypes.HWND(HWND_MESSAGE), None, cls.hInstance, None)
            if not hwnd:
                raise OSError(f"CreateWindowExW failed ({ctypes.GetLastError()})")
            with self._lock:
                self._hwnd = hwnd

            devices = (RAWINPUTDEVICE * 2)()
            # Generic Desktop page: 0x02 mouse, 0x06 keyboard.
            devices[0].usUsagePage, devices[0].usUsage = 0x01, 0x02
            devices[1].usUsagePage, devices[1].usUsage = 0x01, 0x06
            for d in devices:
                d.dwFlags = RIDEV_INPUTSINK  # deliver even when we are not focused
                d.hwndTarget = hwnd
            if not user32.RegisterRawInputDevices(devices, 2, ctypes.sizeof(RAWINPUTDEVICE)):
                raise OSError(f"RegisterRawInputDevices failed ({ctypes.GetLastError()})")

            # Without this the loop can park in GetMessageW forever on an idle
            # machine and the heartbeat check below would never be reached.
            user32.SetTimer(hwnd, ctypes.c_void_p(WATCHDOG_TIMER_ID), 1000, None)

            self._running = True
            self._started_at = time.time()
            msg = wintypes.MSG()
            while True:
                got = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
                if got == 0 or got == -1:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
                # Watchdog: the listener must not outlive the page that asked
                # for it. The 1s WM_TIMER guarantees this runs even with no input.
                if time.time() - self._last_heartbeat > HEARTBEAT_TIMEOUT:
                    break
        except Exception as e:  # pragma: no cover - depends on the host session
            self._error = f"Monitor de input indisponivel: {e}"
        finally:
            self._running = False
            try:
                if hwnd:
                    ctypes.windll.user32.KillTimer(hwnd, ctypes.c_void_p(WATCHDOG_TIMER_ID))
            except Exception:
                pass
            try:
                if hwnd:
                    devices = (RAWINPUTDEVICE * 2)()
                    devices[0].usUsagePage, devices[0].usUsage = 0x01, 0x02
                    devices[1].usUsagePage, devices[1].usUsage = 0x01, 0x06
                    for d in devices:
                        d.dwFlags = RIDEV_REMOVE
                        d.hwndTarget = None
                    ctypes.windll.user32.RegisterRawInputDevices(devices, 2, ctypes.sizeof(RAWINPUTDEVICE))
                    ctypes.windll.user32.DestroyWindow(hwnd)
            except Exception:
                pass
            with self._lock:
                # Only clear the shared handle if it is still this run's window.
                if self._hwnd == hwnd:
                    self._hwnd = None

    def _on_message(self, hwnd, msg, wparam, lparam):
        user32 = ctypes.windll.user32
        if msg == WM_INPUT:
            try:
                size = wintypes.UINT(0)
                user32.GetRawInputData(wintypes.HANDLE(lparam), RID_INPUT, None,
                                       ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER))
                if size.value:
                    buf = ctypes.create_string_buffer(size.value)
                    if user32.GetRawInputData(wintypes.HANDLE(lparam), RID_INPUT, buf,
                                              ctypes.byref(size), ctypes.sizeof(RAWINPUTHEADER)):
                        self._handle_raw(ctypes.cast(buf, ctypes.POINTER(RAWINPUT)).contents)
            except Exception:
                pass
        elif msg in (WM_CLOSE, WM_DESTROY):
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _handle_raw(self, raw: RAWINPUT) -> None:
        now = time.perf_counter()
        wall = time.time()
        if raw.header.dwType == RIM_TYPEMOUSE:
            m = raw.data.mouse
            with self._lock:
                if self._mouse_report_ts:
                    delta = now - self._mouse_report_ts[-1]
                    if 0 < delta < 0.5:
                        self._mouse_intervals.append(delta)
                self._mouse_report_ts.append(now)
                self._mouse_total += 1
                if m.lLastX or m.lLastY:
                    self._move_dx, self._move_dy = int(m.lLastX), int(m.lLastY)
                    self._last_move_at = wall
                    self._move_counts.append((now, abs(int(m.lLastX)) + abs(int(m.lLastY))))
                    self._bump()
                flags = int(m.u.bt.usButtonFlags)
                for mask, label, down in MOUSE_BUTTON_EVENTS:
                    if flags & mask:
                        if down and not self._buttons_down.get(label):
                            self._clicks[label] = self._clicks.get(label, 0) + 1
                            released = self._released_at.get(label)
                            if released is not None and now - released < CHATTER_GAP:
                                self._chatter[label] = self._chatter.get(label, 0) + 1
                        elif not down:
                            self._released_at[label] = now
                        self._buttons_down[label] = down
                        self._bump()
                if flags & RI_MOUSE_WHEEL:
                    self._wheel_at = wall
                    delta = int(m.u.bt.usButtonData)
                    self._wheel_dir = 1 if delta > 0 else -1 if delta < 0 else 0
                    self._bump()
        elif raw.header.dwType == RIM_TYPEKEYBOARD:
            k = raw.data.keyboard
            label = _key_label(int(k.MakeCode), int(k.Flags), int(k.VKey))
            released = bool(int(k.Flags) & RI_KEY_BREAK)
            with self._lock:
                self._kbd_report_ts.append(now)
                if not label:
                    return
                if released:
                    # Identity is dropped the instant the key comes back up.
                    self._keys_down.pop(label, None)
                    self._keys_vk.pop(label, None)
                    self._bump()
                else:
                    if label not in self._keys_down:
                        self._key_press_count += 1
                        self._bump()
                    self._keys_down[label] = wall
                    self._keys_vk[label] = int(k.VKey)

    # -- measurement ---------------------------------------------------
    def _rate_hz(self, ring: deque, window: float = RATE_WINDOW) -> Optional[float]:
        """Reports per second over the rolling window. None when idle."""
        if not ring:
            return None
        now = time.perf_counter()
        recent = [t for t in ring if now - t <= window]
        if len(recent) < 4:
            return None
        span = recent[-1] - recent[0]
        if span <= 0:
            return None
        return round((len(recent) - 1) / span, 1)

    def _polling_estimate(self) -> Dict[str, Any]:
        """Turn measured inter-report gaps into a polling-rate reading.

        The device only reports while it is being moved, so this is honest only
        as "measured while you moved the mouse". The median gap is used because a
        single scheduling hiccup should not move the number.
        """
        with self._lock:
            intervals = sorted(self._mouse_intervals)
            samples = len(intervals)
            peak = self._peak_hz
        if samples < 24:
            return {"hz": None, "samples": samples, "confidence": "insufficient",
                    "detail": "Mova o mouse por alguns segundos para o AZOR medir a taxa real de envio."}
        mid = intervals[samples // 2]
        if mid <= 0:
            return {"hz": None, "samples": samples, "confidence": "insufficient", "detail": "Intervalos invalidos."}
        hz = 1.0 / mid
        p95 = intervals[max(0, int(samples * 0.95) - 1)]
        jitter_ms = round((p95 - mid) * 1000, 3)
        nominal = min((125, 250, 500, 1000, 2000, 4000, 8000), key=lambda n: abs(n - hz))
        close = abs(hz - nominal) / nominal < 0.18
        # Quantos intervalos cairam no ritmo do proprio mouse (a mediana). Fora do
        # ritmo nao e so defeito: movimento lento tambem abre intervalo, porque o
        # mouse so manda relatorio quando anda.
        early = sum(1 for x in intervals if x < 0.75 * mid)
        on_beat = sum(1 for x in intervals if 0.75 * mid <= x <= 1.25 * mid)
        late = sum(1 for x in intervals if 1.25 * mid < x <= 2.5 * mid)
        pct = lambda n: round(100.0 * n / samples, 1)
        return {
            "hz": round(hz, 1),
            "nominal_hz": nominal if close else None,
            "samples": samples,
            "jitter_ms": jitter_ms,
            "stability": {"on_beat": pct(on_beat), "early": pct(early), "late": pct(late),
                          "gaps": pct(samples - on_beat - early - late)},
            "peak_hz": round(peak, 1) if peak else None,
            "confidence": "measured" if samples >= 200 else "partial",
            "detail": (f"Medido a partir de {samples} relatorios reais do dispositivo."
                       if samples >= 200 else
                       f"Medicao parcial com {samples} relatorios. Continue movendo o mouse para refinar."),
        }

    def _polling_cached(self) -> Dict[str, Any]:
        """O stream pode pedir snapshot 144x/s; a estimativa nao precisa mudar tanto."""
        now = time.perf_counter()
        at, value = self._polling_cache
        if value is None or now - at > POLLING_CACHE_S:
            value = self._polling_estimate()
            self._polling_cache = (now, value)
        return value

    def _counts_per_second(self) -> Optional[int]:
        """Soma de |dx|+|dy| no ultimo segundo: velocidade crua do sensor, em contagens."""
        now = time.perf_counter()
        with self._lock:
            recent = [c for t, c in self._move_counts if now - t <= 1.0]
        return sum(recent) if recent else None

    def _drop_stuck_keys(self, now: float) -> None:
        """Removes keys Windows says are no longer physically down.

        A raw-input BREAK can be missed - the classic case is a key held while
        focus moves or while the listener restarts - and the label then stayed
        lit forever. GetAsyncKeyState is the authority on what is held right now,
        so anything held for more than 400 ms is confirmed against it. The delay
        keeps a key that was just pressed from being second-guessed.
        """
        if not IS_WINDOWS or not self._keys_down:
            return
        try:
            get_state = ctypes.windll.user32.GetAsyncKeyState
        except Exception:
            return
        for label, since in list(self._keys_down.items()):
            if now - since < 0.4:
                continue
            vk = self._keys_vk.get(label)
            if not vk:
                continue
            try:
                if not (get_state(int(vk)) & 0x8000):
                    self._keys_down.pop(label, None)
                    self._keys_vk.pop(label, None)
                    self._bump()
            except Exception:
                return

    def _bump(self) -> None:
        """Conta a mudanca e acorda quem estiver esperando por ela."""
        self._revision += 1
        self._changed.set()

    def wait_for_change(self, timeout: float) -> bool:
        """Bloqueia ate o estado mudar. Sem giro, sem acordar a toa."""
        got = self._changed.wait(timeout)
        if got:
            self._changed.clear()
        return got

    def revision(self) -> int:
        with self._lock:
            return self._revision

    def snapshot(self) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            self._drop_stuck_keys(now)
            running = bool(self._running)
            buttons = [k for k, v in self._buttons_down.items() if v]
            keys = list(self._keys_down.keys())
            revision = self._revision
            key_count = self._key_press_count
            wheel_recent = (now - self._wheel_at) < 0.18 if self._wheel_at else False
            wheel_dir = self._wheel_dir if wheel_recent else 0
            moving = (now - self._last_move_at) < 0.15 if self._last_move_at else False
            dx, dy = self._move_dx, self._move_dy
            mouse_total = self._mouse_total
            clicks, chatter = dict(self._clicks), dict(self._chatter)
            uptime = now - self._started_at if self._started_at else 0.0
        mouse_hz = self._rate_hz(self._mouse_report_ts)
        if mouse_hz:
            with self._lock:
                self._peak_hz = max(self._peak_hz, mouse_hz)
        return {
            "ok": True,
            "running": running,
            "rev": revision,
            "error": self._error,
            "mouse": {
                "buttons": buttons, "moving": moving, "dx": dx, "dy": dy,
                "wheel": wheel_recent, "wheel_dir": wheel_dir, "live_hz": mouse_hz, "reports": mouse_total,
                "clicks": clicks, "chatter": chatter, "counts_per_s": self._counts_per_second(),
            },
            "keyboard": {
                # Only what is held down right now, plus a count. No sequence exists.
                "down": keys, "press_count": key_count,
            },
            "polling": self._polling_cached(),
            "uptime_s": round(uptime, 1),
            "privacy": ("Esta tela mostra apenas qual tecla ou botao esta pressionado agora, "
                        "para desenhar o periferico e medir a taxa de envio. O AZOR nao guarda "
                        "sequencia de teclas, nao grava o que voce digita, nao salva nada em disco "
                        "e o monitor para sozinho quando voce sai desta tela."),
        }


MONITOR = InputMonitor()


def start() -> Dict[str, Any]:
    return MONITOR.start()


def stop() -> Dict[str, Any]:
    return MONITOR.stop()


def revision() -> int:
    """Change counter, so a stream can send only when something happened."""
    return MONITOR.revision()


def wait_for_change(timeout: float) -> bool:
    """Espera ate haver o que enviar, ou ate o timeout."""
    return MONITOR.wait_for_change(timeout)


def snapshot() -> Dict[str, Any]:
    MONITOR.touch()
    return MONITOR.snapshot()


def status() -> Dict[str, Any]:
    return {"running": bool(MONITOR._running), "error": MONITOR._error, "supported": IS_WINDOWS}
