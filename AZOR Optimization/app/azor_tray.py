"""Icone do AZOR na bandeja do Windows, ao lado do relogio.

Por que isto existe: a interface do AZOR e uma janela do Edge em modo aplicativo.
Minimizar mandava ela para a barra de tarefas, junto de tudo o mais, e fechar
matava a janela mas deixava o backend rodando invisivel -- o usuário não tinha
como trazer o app de volta a não ser reabrindo pelo atalho, o que reinicia tudo.

Aqui a janela minimizada e ESCONDIDA e o AZOR passa a viver no icone da bandeja:
um clique traz de volta, o menu do botão direito abre ou encerra de verdade.

Sem dependencia externa: Shell_NotifyIcon e uma janela oculta com laço de
mensagens, por ctypes. Um pacote a mais no runtime embutido seria alguns MB para
um icone.
"""
from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Callable, Optional

user32 = ctypes.windll.user32 if os.name == "nt" else None
shell32 = ctypes.windll.shell32 if os.name == "nt" else None
kernel32 = ctypes.windll.kernel32 if os.name == "nt" else None

# --- constantes do Win32 usadas aqui -----------------------------------------
WM_DESTROY, WM_CLOSE, WM_COMMAND = 0x0002, 0x0010, 0x0111
WM_APP = 0x8000
WM_TRAY = WM_APP + 17          # mensagem de retorno do icone da bandeja
WM_LBUTTONUP, WM_RBUTTONUP, WM_LBUTTONDBLCLK = 0x0202, 0x0205, 0x0203
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0x0, 0x1, 0x2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x0010, 0x0040
SW_HIDE, SW_SHOW, SW_RESTORE = 0, 5, 9
MF_STRING, MF_SEPARATOR = 0x0, 0x800
TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x0002, 0x0100
IDI_APPLICATION = 32512
CMD_OPEN, CMD_EXIT = 1001, 1002


class NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON), ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
    ]


class WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT), ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
    ]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)
ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def find_ui_window(title_prefix: str = "AZOR") -> Optional[int]:
    """A janela do Edge em modo aplicativo que serve a interface do AZOR.

    Filtra por classe do Chromium E titulo, porque o titulo sozinho pegaria uma
    aba qualquer do navegador com "AZOR" no nome de um site aberto.
    """
    if user32 is None:
        return None
    found = []

    def cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            # Janela ja escondida por nos continua sendo a nossa: nao filtra aqui.
            pass
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value or ""
        if not title.upper().startswith(title_prefix.upper()):
            return True
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if "Chrome_WidgetWin" in (cls.value or ""):
            found.append(hwnd)
            return False
        return True

    try:
        user32.EnumWindows(ENUMPROC(cb), 0)
    except Exception:
        return None
    return found[0] if found else None


class AzorTray:
    """Icone da bandeja + vigia da janela.

    `on_open` e chamado quando não existe janela para restaurar (o usuário fechou
    no X): quem sabe reabrir a interface e o servidor, não este módulo.
    """

    def __init__(self, icon_path: Optional[Path], tooltip: str,
                 on_open: Callable[[], None], on_exit: Callable[[], None],
                 log: Optional[Callable[[str], None]] = None):
        self.icon_path = Path(icon_path) if icon_path else None
        self.tooltip = tooltip[:127]
        self.on_open = on_open
        self.on_exit = on_exit
        self.log = log or (lambda _m: None)
        self.hwnd = None
        self._nid = None
        self._proc = None          # a referencia precisa sobreviver ao registro
        self._thread = None
        self._watch = None
        self._stop = threading.Event()
        self._hidden_by_us = False
        self.available = os.name == "nt" and user32 is not None

    # ------------------------------------------------------------------ ciclo
    def start(self) -> bool:
        if not self.available or self._thread:
            return False
        self._thread = threading.Thread(target=self._run, name="azor-tray", daemon=True)
        self._thread.start()
        self._watch = threading.Thread(target=self._watch_window, name="azor-tray-watch", daemon=True)
        self._watch.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        try:
            if self.hwnd:
                user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        except Exception:
            pass

    # ------------------------------------------------------------------ janela
    def _run(self) -> None:
        try:
            self._proc = WNDPROC(self._wndproc)
            hinst = kernel32.GetModuleHandleW(None)
            cls = WNDCLASS()
            cls.lpfnWndProc = ctypes.cast(self._proc, ctypes.c_void_p)
            cls.hInstance = hinst
            cls.lpszClassName = "AzorTrayWindow"
            if not user32.RegisterClassW(ctypes.byref(cls)):
                # 1410 = classe ja registrada (segunda abertura no mesmo processo)
                if kernel32.GetLastError() not in (1410,):
                    self.log("Tray: RegisterClassW falhou")
                    return
            self.hwnd = user32.CreateWindowExW(0, "AzorTrayWindow", "AZOR", 0,
                                               0, 0, 0, 0, None, None, hinst, None)
            if not self.hwnd:
                self.log("Tray: CreateWindowExW falhou")
                return
            self._add_icon()
            msg = wintypes.MSG()
            while not self._stop.is_set():
                got = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if got in (0, -1):
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        except Exception as exc:
            self.log(f"Tray falhou: {exc}")
        finally:
            self._remove_icon()

    def _load_icon(self):
        if self.icon_path and self.icon_path.exists():
            handle = user32.LoadImageW(None, str(self.icon_path), IMAGE_ICON, 0, 0,
                                       LR_LOADFROMFILE | LR_DEFAULTSIZE)
            if handle:
                return handle
        return user32.LoadIconW(None, ctypes.c_wchar_p(IDI_APPLICATION))

    def _add_icon(self) -> None:
        nid = NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATA)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self._load_icon()
        nid.szTip = self.tooltip
        self._nid = nid
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

    def _remove_icon(self) -> None:
        try:
            if self._nid is not None:
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._nid))
                self._nid = None
        except Exception:
            pass

    def notify(self, title: str, text: str) -> None:
        """Balao da bandeja. Usado com parcimonia: notificacao repetida vira ruido."""
        if self._nid is None:
            return
        try:
            self._nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_INFO
            self._nid.szInfoTitle = title[:63]
            self._nid.szInfo = text[:255]
            self._nid.dwInfoFlags = 0
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._nid))
            self._nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        except Exception:
            pass

    # ------------------------------------------------------------------ eventos
    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg == WM_TRAY:
            event = lparam & 0xFFFF
            if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self.show_ui()
            elif event == WM_RBUTTONUP:
                self._menu()
            return 0
        if msg == WM_COMMAND:
            cmd = wparam & 0xFFFF
            if cmd == CMD_OPEN:
                self.show_ui()
            elif cmd == CMD_EXIT:
                self._quit()
            return 0
        if msg in (WM_CLOSE, WM_DESTROY):
            self._remove_icon()
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _menu(self) -> None:
        try:
            menu = user32.CreatePopupMenu()
            user32.AppendMenuW(menu, MF_STRING, CMD_OPEN, "Abrir o AZOR")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, CMD_EXIT, "Sair do AZOR")
            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            # Sem isto o menu nao fecha ao clicar fora - comportamento documentado
            # do TrackPopupMenu para janelas sem foco.
            user32.SetForegroundWindow(self.hwnd)
            cmd = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD,
                                        pt.x, pt.y, 0, self.hwnd, None)
            user32.PostMessageW(self.hwnd, 0, 0, 0)
            user32.DestroyMenu(menu)
            if cmd == CMD_OPEN:
                self.show_ui()
            elif cmd == CMD_EXIT:
                self._quit()
        except Exception as exc:
            self.log(f"Tray menu falhou: {exc}")

    def show_ui(self) -> None:
        """Traz a janela de volta; se ela não existe mais, pede uma nova."""
        hwnd = find_ui_window()
        if hwnd:
            try:
                user32.ShowWindow(hwnd, SW_SHOW)
                user32.ShowWindow(hwnd, SW_RESTORE)
                user32.SetForegroundWindow(hwnd)
                self._hidden_by_us = False
                return
            except Exception:
                pass
        try:
            self.on_open()
        except Exception as exc:
            self.log(f"Tray: reabrir a interface falhou: {exc}")

    def _quit(self) -> None:
        try:
            self.on_exit()
        except Exception as exc:
            self.log(f"Tray: encerramento falhou: {exc}")
        self.stop()

    # ------------------------------------------------------------------ vigia
    def _watch_window(self) -> None:
        """Minimizou, some da barra e vai para a bandeja.

        Poll de 500 ms em vez de hook global: um hook exigiria injecao em outro
        processo (o Edge não e nosso) e e exatamente o tipo de coisa que faz
        antivirus e anticheat reclamarem de um otimizador.
        """
        while not self._stop.is_set():
            try:
                hwnd = find_ui_window()
                if hwnd and user32.IsIconic(hwnd) and user32.IsWindowVisible(hwnd):
                    user32.ShowWindow(hwnd, SW_HIDE)
                    self._hidden_by_us = True
                    self.log("Tray: janela minimizada foi recolhida para a bandeja")
            except Exception:
                pass
            time.sleep(0.5)
