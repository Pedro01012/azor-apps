"""Leitura do controle pelo XInput: identidade, bateria, estado e taxa de envio medida.

Por que existe
--------------
A tela de Periféricos desenha o controle pela Gamepad API do navegador. Ela só
entrega o nome do DRIVER ("Xbox 360 Controller (XInput STANDARD GAMEPAD)") e
nenhuma medida, e por isso a tela dizia "taxa não disponível" e chamava de Xbox
qualquer controle em modo XInput.

O XInput diz mais:
  * qual slot (1 a 4) está ligado e, por XInputGetCapabilitiesEx, o VID/PID
    real por trás dele - daí sai o fabricante;
  * o tipo e o nível da bateria (com fio, pilha, recarregável);
  * um número de pacote que o driver incrementa a cada estado novo que o
    controle manda. Contar quanto esse número anda por segundo, enquanto o
    analógico se mexe, é a taxa de envio medida. Como é o próprio driver que
    conta, o resultado não depende de este leitor ser mais rápido que o controle.

Custo e ciclo de vida
---------------------
Nada vai para disco nem para rede. A coleta só roda enquanto a aba Controle
está aberta: a página pede leitura algumas vezes por segundo, e sem pedido por
IDLE_TIMEOUT segundos o laço termina sozinho. Slot vazio é caro de consultar no
XInput, então os vazios só são reprocurados uma vez por segundo.
"""
from __future__ import annotations

import ctypes
import threading
import time
from collections import deque
from ctypes import wintypes
from typing import Any, Dict, List, Optional

from azor_modules import usb_ids

IS_WINDOWS = hasattr(ctypes, "windll")
ERROR_SUCCESS = 0
MAX_SLOTS = 4
IDLE_TIMEOUT = 3.0
RESCAN_EVERY = 1.0
INFO_EVERY = 5.0
SAMPLE_SLEEP = 0.0005
# Entre dois estados novos, mais do que isto é pausa do jogador, não ritmo do
# controle: fecha a rajada de movimento em vez de contar a pausa como intervalo.
BURST_GAP = 0.05
MIN_BURST = 0.15
MEASURE_WINDOW = 8.0
NOMINAL_HZ = (125, 250, 500, 1000, 2000, 4000, 8000)

BUTTON_NAMES = (
    (0x0001, "UP"), (0x0002, "DOWN"), (0x0004, "LEFT"), (0x0008, "RIGHT"),
    (0x0010, "START"), (0x0020, "BACK"), (0x0040, "L3"), (0x0080, "R3"),
    (0x0100, "LB"), (0x0200, "RB"), (0x0400, "GUIDE"),
    (0x1000, "A"), (0x2000, "B"), (0x4000, "X"), (0x8000, "Y"),
)
SUBTYPES = {
    0x00: "desconhecido", 0x01: "controle", 0x02: "volante", 0x03: "arcade stick",
    0x04: "manche", 0x05: "tapete de dança", 0x06: "guitarra", 0x07: "guitarra",
    0x08: "bateria", 0x0B: "baixo", 0x13: "arcade pad",
}
BATTERY_TYPES = {0x00: "desconectado", 0x01: "com fio", 0x02: "pilha alcalina", 0x03: "recarregável (NiMH)",
                 0xFF: "não informado"}
BATTERY_LEVELS = {0: "vazia", 1: "baixa", 2: "média", 3: "cheia"}
XINPUT_CAPS_WIRELESS = 0x0002


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [("wButtons", wintypes.WORD), ("bLeftTrigger", wintypes.BYTE), ("bRightTrigger", wintypes.BYTE),
                ("sThumbLX", wintypes.SHORT), ("sThumbLY", wintypes.SHORT),
                ("sThumbRX", wintypes.SHORT), ("sThumbRY", wintypes.SHORT)]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", XINPUT_GAMEPAD)]


class XINPUT_VIBRATION(ctypes.Structure):
    _fields_ = [("wLeftMotorSpeed", wintypes.WORD), ("wRightMotorSpeed", wintypes.WORD)]


class XINPUT_CAPABILITIES(ctypes.Structure):
    _fields_ = [("Type", wintypes.BYTE), ("SubType", wintypes.BYTE), ("Flags", wintypes.WORD),
                ("Gamepad", XINPUT_GAMEPAD), ("Vibration", XINPUT_VIBRATION)]


class XINPUT_CAPABILITIES_EX(ctypes.Structure):
    # Não documentada, mas estável desde o Windows 8 (ordinal 108 do xinput1_4);
    # é o que o SDL usa para achar o VID/PID de um controle XInput.
    _fields_ = [("Capabilities", XINPUT_CAPABILITIES), ("VendorId", wintypes.WORD),
                ("ProductId", wintypes.WORD), ("ProductVersion", wintypes.WORD),
                ("unk1", wintypes.WORD), ("unk2", wintypes.DWORD)]


class XINPUT_BATTERY_INFORMATION(ctypes.Structure):
    _fields_ = [("BatteryType", wintypes.BYTE), ("BatteryLevel", wintypes.BYTE)]


def _load_xinput():
    """(nome, GetState, GetCapabilities, GetCapabilitiesEx, GetBatteryInformation) ou None."""
    if not IS_WINDOWS:
        return None
    for name in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
        try:
            dll = ctypes.WinDLL(name)
        except OSError:
            continue
        get_state = None
        if name != "xinput9_1_0":
            try:
                get_state = dll[100]  # XInputGetStateEx: igual ao GetState, mas inclui o botão guia
            except (AttributeError, OSError):
                get_state = None
        if get_state is None:
            get_state = dll.XInputGetState
        get_state.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
        get_state.restype = wintypes.DWORD
        get_caps = dll.XInputGetCapabilities
        get_caps.argtypes = [wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(XINPUT_CAPABILITIES)]
        get_caps.restype = wintypes.DWORD
        get_caps_ex = None
        if name == "xinput1_4":
            try:
                get_caps_ex = dll[108]
                get_caps_ex.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                        ctypes.POINTER(XINPUT_CAPABILITIES_EX)]
                get_caps_ex.restype = wintypes.DWORD
            except (AttributeError, OSError):
                get_caps_ex = None
        get_battery = None
        try:
            get_battery = dll.XInputGetBatteryInformation
            get_battery.argtypes = [wintypes.DWORD, wintypes.BYTE, ctypes.POINTER(XINPUT_BATTERY_INFORMATION)]
            get_battery.restype = wintypes.DWORD
        except AttributeError:
            get_battery = None
        return name, get_state, get_caps, get_caps_ex, get_battery
    return None


def rate_from_bursts(bursts: List[tuple]) -> Dict[str, Any]:
    """Taxa de envio a partir de rajadas (duração, pacotes). Função pura, testável.

    Só entra rajada de movimento contínuo: parado, o controle não manda estado
    novo e o número de pacote não anda - isso não é taxa baixa, é silêncio.
    """
    duration = sum(d for d, _ in bursts)
    packets = sum(p for _, p in bursts)
    if duration < 1.0 or packets < 100:
        return {"hz": None, "nominal_hz": None, "packets": packets, "seconds": round(duration, 2),
                "confidence": "insufficient",
                "detail": "Gire um analógico em círculos por alguns segundos, sem parar, para o AZOR medir."}
    hz = packets / duration
    nominal = min(NOMINAL_HZ, key=lambda n: abs(n - hz))
    close = abs(hz - nominal) / nominal < 0.18
    measured = duration >= 3.0
    return {
        "hz": round(hz, 1),
        "nominal_hz": nominal if close else None,
        "packets": packets,
        "seconds": round(duration, 2),
        "confidence": "measured" if measured else "partial",
        "detail": (f"Contados {packets} pacotes novos do XInput em {duration:.1f} s de movimento."
                   + ("" if measured else " Continue girando o analógico para fechar a medição.")),
    }


class _Slot:
    def __init__(self, index: int) -> None:
        self.index = index
        self.connected = False
        self.checked_at = 0.0
        self.info_at = 0.0
        self.info: Dict[str, Any] = {}
        self.packet: Optional[int] = None
        self.burst_start: Optional[tuple] = None  # (tempo, pacote) do início da rajada
        self.burst_last: Optional[tuple] = None
        self.bursts: deque = deque()  # (fim, duração, pacotes)
        self.raw: Optional[tuple] = None

    def reset(self) -> None:
        self.connected = False
        self.info = {}
        self.info_at = 0.0
        self.packet = None
        self.burst_start = self.burst_last = None
        self.bursts.clear()
        self.raw = None

    def close_burst(self) -> None:
        if self.burst_start and self.burst_last:
            duration = self.burst_last[0] - self.burst_start[0]
            packets = (self.burst_last[1] - self.burst_start[1]) & 0xFFFFFFFF
            if duration >= MIN_BURST and packets > 0:
                self.bursts.append((self.burst_last[0], duration, packets))
        self.burst_start = self.burst_last = None


class PadMonitor:
    def __init__(self) -> None:
        self._api = _load_xinput()
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._running = False
        self._last_request = 0.0
        self._slots = [_Slot(i) for i in range(MAX_SLOTS)]
        self._loop_hz: Optional[float] = None

    # -- ciclo de vida ------------------------------------------------------
    def available(self) -> bool:
        return self._api is not None

    def touch(self) -> None:
        self._last_request = time.monotonic()

    def ensure_running(self) -> None:
        if not self._api:
            return
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="azor-gamepad", daemon=True)
            self._running = True
            self._thread.start()

    def stop(self) -> Dict[str, Any]:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2.0)
        with self._lock:
            for slot in self._slots:
                slot.reset()
            self._running = False
        return {"ok": True, "detail": "Leitura do controle encerrada.", "running": False}

    # -- leitura --------------------------------------------------------------
    def _refresh_info(self, slot: _Slot, now: float) -> None:
        _, _, get_caps, get_caps_ex, get_battery = self._api
        info: Dict[str, Any] = {}
        caps_ex = XINPUT_CAPABILITIES_EX()
        caps = None
        if get_caps_ex is not None and get_caps_ex(1, slot.index, 0, ctypes.byref(caps_ex)) == ERROR_SUCCESS:
            caps = caps_ex.Capabilities
            if caps_ex.VendorId:
                info["vid"] = f"{caps_ex.VendorId:04X}"
                info["pid"] = f"{caps_ex.ProductId:04X}"
        if caps is None:
            plain = XINPUT_CAPABILITIES()
            if get_caps(slot.index, 0, ctypes.byref(plain)) == ERROR_SUCCESS:
                caps = plain
        if caps is not None:
            info["subtype"] = SUBTYPES.get(int(caps.SubType), f"tipo {int(caps.SubType)}")
            info["wireless"] = bool(int(caps.Flags) & XINPUT_CAPS_WIRELESS)
        if get_battery is not None:
            battery = XINPUT_BATTERY_INFORMATION()
            if get_battery(slot.index, 0, ctypes.byref(battery)) == ERROR_SUCCESS:
                kind = int(battery.BatteryType) & 0xFF
                level = int(battery.BatteryLevel) & 0xFF
                info["battery"] = {
                    "type": BATTERY_TYPES.get(kind, "não informado"),
                    "wired": kind == 0x01,
                    # Com fio o nível não significa nada; o XInput devolve "cheia".
                    "level": None if kind in (0x00, 0x01, 0xFF) else BATTERY_LEVELS.get(level),
                }
        maker = usb_ids.vendor(info.get("vid"))
        if maker:
            info["vendor"] = maker["name"]
            info["vendor_kind"] = maker["kind"]
        slot.info = info
        slot.info_at = now

    def _run(self) -> None:
        name, get_state, *_ = self._api
        state = XINPUT_STATE()
        loops, loop_t0 = 0, time.perf_counter()
        try:
            while not self._stop.is_set():
                if time.monotonic() - self._last_request > IDLE_TIMEOUT:
                    break
                now = time.perf_counter()
                with self._lock:
                    for slot in self._slots:
                        if not slot.connected and now - slot.checked_at < RESCAN_EVERY:
                            continue
                        slot.checked_at = now
                        if get_state(slot.index, ctypes.byref(state)) != ERROR_SUCCESS:
                            if slot.connected:
                                slot.reset()
                            continue
                        pad = state.Gamepad
                        packet = int(state.dwPacketNumber)
                        slot.raw = (int(pad.wButtons), int(pad.bLeftTrigger) & 0xFF, int(pad.bRightTrigger) & 0xFF,
                                    int(pad.sThumbLX), int(pad.sThumbLY), int(pad.sThumbRX), int(pad.sThumbRY))
                        if not slot.connected:
                            slot.connected = True
                            slot.packet = packet
                            self._refresh_info(slot, now)
                            continue
                        if now - slot.info_at > INFO_EVERY:
                            self._refresh_info(slot, now)
                        if packet != slot.packet:
                            slot.packet = packet
                            if slot.burst_last and now - slot.burst_last[0] > BURST_GAP:
                                slot.close_burst()
                            if slot.burst_start is None:
                                slot.burst_start = (now, packet)
                            slot.burst_last = (now, packet)
                        elif slot.burst_last and now - slot.burst_last[0] > BURST_GAP:
                            slot.close_burst()
                        while slot.bursts and now - slot.bursts[0][0] > MEASURE_WINDOW:
                            slot.bursts.popleft()
                    any_connected = any(slot.connected for slot in self._slots)
                loops += 1
                elapsed = now - loop_t0
                if elapsed >= 1.0:
                    self._loop_hz = loops / elapsed
                    loops, loop_t0 = 0, now
                # Sem controle ligado não há pacote para contar: dorme até a próxima
                # busca em vez de acordar mil vezes por segundo à toa.
                time.sleep(SAMPLE_SLEEP if any_connected else 0.1)
        finally:
            self._running = False

    def snapshot(self) -> Dict[str, Any]:
        self.touch()
        self.ensure_running()
        slots: List[Dict[str, Any]] = []
        with self._lock:
            for slot in self._slots:
                if not slot.connected:
                    continue
                bursts = [(d, p) for _, d, p in slot.bursts]
                if slot.burst_start and slot.burst_last:
                    live = slot.burst_last[0] - slot.burst_start[0]
                    if live >= MIN_BURST:
                        bursts.append((live, (slot.burst_last[1] - slot.burst_start[1]) & 0xFFFFFFFF))
                raw = slot.raw
                entry = {"index": slot.index, "number": slot.index + 1, **slot.info,
                         "polling": rate_from_bursts(bursts)}
                if raw:
                    entry["state"] = {
                        "buttons": [label for mask, label in BUTTON_NAMES if raw[0] & mask],
                        "lt": raw[1], "rt": raw[2], "lx": raw[3], "ly": raw[4], "rx": raw[5], "ry": raw[6],
                    }
                slots.append(entry)
        return {
            "ok": True,
            "available": self.available(),
            "api": self._api[0] if self._api else None,
            "running": bool(self._running),
            "sampler_hz": round(self._loop_hz, 1) if self._loop_hz else None,
            "slots": slots,
            "detail": ("" if self._api else
                       "O XInput não está disponível neste Windows; o controle é lido só pela janela."),
        }


MONITOR = PadMonitor()


def available() -> bool:
    return MONITOR.available()


def snapshot() -> Dict[str, Any]:
    return MONITOR.snapshot()


def stop() -> Dict[str, Any]:
    return MONITOR.stop()
