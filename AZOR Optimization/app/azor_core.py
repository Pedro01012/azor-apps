from __future__ import annotations

import copy
import itertools
import struct
import ctypes
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from azor_modules.power_policy import POWER_SETTINGS, POWER_EXPECTED
from azor_benchmark import system_sample, compare as compare_system_samples

try:
    import winreg  # type: ignore
except ImportError:
    winreg = None

APP_ROOT = Path(__file__).resolve().parent


def _resolve_data_dir() -> Path:
    """Store mutable state in LocalAppData on Windows.

    The clean portable build never self-installs or replaces its own executable.
    Settings, logs and restore data stay outside the extracted application folder.
    """
    override = os.environ.get("AZOR_DATA_DIR")
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and local:
        return Path(local) / "AzorOptimization" / "user" / "data"
    return APP_ROOT / "data"


DATA_DIR = _resolve_data_dir()
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = DATA_DIR / "restore_state.json"
# O baseline e escrito UMA vez, na primeira captura, e nunca mais e sobrescrito.
# Ele e o unico registro de como este PC era antes do AZOR existir: sem ele,
# rodar a otimizacao duas vezes gravava o estado ja otimizado como "original"
# e "restaurar padroes do Windows" passava a restaurar o proprio AZOR.
BASELINE_FILE = DATA_DIR / "baseline_state.json"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
JOURNAL_FILE = DATA_DIR / "journal.jsonl"
SETTINGS_FILE = DATA_DIR / "settings.json"
LOG_FILE = DATA_DIR / "azor.log"

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


# Niveis de log. A assinatura antiga - log("texto") - continua valendo e cai em
# INFO, entao nenhuma das centenas de chamadas existentes precisou mudar.
#
# DEBUG so vai para o arquivo com o modo desenvolvedor ligado. O cliente comum
# nao precisa ver rastreio de excecao para saber que o app esta funcionando, e um
# log cheio de linha vermelha assusta quem nao e tecnico.
LOG_LEVELS = ("DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR")


def _dev_mode() -> bool:
    try:
        return bool(load_settings().get("dev_mode"))
    except Exception:
        return False


def log(message: str, level: str = "INFO") -> None:
    lvl = str(level).upper()
    if lvl not in LOG_LEVELS:
        lvl = "INFO"
    if lvl == "DEBUG" and not _dev_mode():
        return
    line = f"[{_ts()}] [{lvl:<7}] {message}"
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass






def log_error(message: str) -> None:
    log(message, "ERROR")


def log_debug(message: str) -> None:
    log(message, "DEBUG")


_JOURNAL_LOCK = threading.Lock()
_JOURNAL_MAX_BYTES = 4 * 1024 * 1024


def journal(event: str, **fields: Any) -> None:
    """Structured append-only log (JSONL), one object per line.

    The human log stays as it is for reading on screen. This one exists so a
    support ticket can be answered with data instead of prose: every apply,
    verify, revert and measurement lands here with its own fields.
    """
    row: Dict[str, Any] = {"ts": _ts(), "event": str(event)}
    for key, value in fields.items():
        try:
            json.dumps(value)
            row[key] = value
        except Exception:
            row[key] = str(value)
    try:
        with _JOURNAL_LOCK:
            if JOURNAL_FILE.exists() and JOURNAL_FILE.stat().st_size > _JOURNAL_MAX_BYTES:
                JOURNAL_FILE.replace(JOURNAL_FILE.with_suffix(".jsonl.1"))
            with JOURNAL_FILE.open("a", encoding="utf-8", newline="\n") as f:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass




def read_log(limit: int = 250) -> str:
    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-limit:])
    except Exception:
        return ""


def run_hidden(args: List[str], timeout: int = 20) -> subprocess.CompletedProcess:
    kwargs: Dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "timeout": timeout,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.run(args, **kwargs)


# ---------------------------------------------------------------------------
# Short-lived cache for readings that cost a process spawn.
#
# The dashboard polls /api/summary every 12 s. Re-running powercfg, tasklist and
# the optimization analysis on every poll cost ~1,3 s of CPU per poll to answer
# a question whose answer only changes when the user clicks something. Anything
# the user can change from inside the app calls invalidate_cache() right after
# the action, so the screen never shows a stale result of its own click.
# ---------------------------------------------------------------------------
_TTL_CACHE: Dict[str, Tuple[float, Any]] = {}
_TTL_LOCK = threading.Lock()


def cached_reading(key: str, ttl: float, producer: Callable[[], Any], force: bool = False) -> Any:
    now = time.monotonic()
    if not force:
        with _TTL_LOCK:
            hit = _TTL_CACHE.get(key)
        if hit is not None and (now - hit[0]) < ttl:
            return copy.deepcopy(hit[1])
    value = producer()
    with _TTL_LOCK:
        _TTL_CACHE[key] = (now, value)
    return copy.deepcopy(value)


def invalidate_cache(*keys: str) -> None:
    """Drops cached readings after something was actually changed on the system."""
    global _DEVICE_CACHE
    with _TTL_LOCK:
        if keys:
            for key in keys:
                _TTL_CACHE.pop(key, None)
        else:
            _TTL_CACHE.clear()
    if not keys:
        _DEVICE_CACHE = {"ts": 0.0, "data": None}


def powershell(script: str, timeout: int = 25) -> str:
    if os.name != "nt":
        return ""
    utf8_prefix = "[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false); $OutputEncoding = [Console]::OutputEncoding; "
    p = run_hidden([
        "powershell.exe", "-NoProfile", "-NonInteractive", "-Command", utf8_prefix + script
    ], timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "PowerShell failed").strip())
    return (p.stdout or "").strip()


def powershell_json(script: str, timeout: int = 30) -> Any:
    # Windows PowerShell 5 does not accept a pipeline beginning on the line
    # after an arbitrary multi-line script. Capture the script block result
    # first, then serialize it in a separate, syntactically stable statement.
    wrapped = "$ErrorActionPreference='Stop'; $azorResult = & {\n" + str(script).strip() + "\n}; $azorResult | ConvertTo-Json -Depth 6 -Compress"
    out = powershell(wrapped, timeout)
    if not out:
        return None
    return json.loads(out)


def is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False




def _root_const(name: str):
    if winreg is None:
        return None
    return {
        "HKCU": winreg.HKEY_CURRENT_USER,
        "HKLM": winreg.HKEY_LOCAL_MACHINE,
    }[name]


def reg_read(root: str, path: str, name: str) -> Dict[str, Any]:
    if winreg is None:
        return {"exists": False, "value": None, "type": None}
    try:
        with winreg.OpenKey(_root_const(root), path, 0, winreg.KEY_READ) as k:
            value, typ = winreg.QueryValueEx(k, name)
            return {"exists": True, "value": value, "type": int(typ)}
    except FileNotFoundError:
        return {"exists": False, "value": None, "type": None}


def reg_write(root: str, path: str, name: str, value: Any, typ: Optional[int] = None) -> None:
    if winreg is None:
        raise RuntimeError("Windows registry is unavailable on this system.")
    if typ is None:
        typ = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
    access = winreg.KEY_SET_VALUE
    with winreg.CreateKeyEx(_root_const(root), path, 0, access) as k:
        winreg.SetValueEx(k, name, 0, typ, value)


def reg_delete_value(root: str, path: str, name: str) -> None:
    if winreg is None:
        return
    try:
        with winreg.OpenKey(_root_const(root), path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, name)
    except FileNotFoundError:
        pass


TRACKED_REGISTRY = [
    ("HKCU", r"Software\Microsoft\GameBar", "AllowAutoGameMode"),
    ("HKCU", r"Software\Microsoft\GameBar", "AutoGameModeEnabled"),
    ("HKCU", r"System\GameConfigStore", "GameDVR_Enabled"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications", "GlobalUserDisabled"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects", "VisualFXSetting"),
    ("HKCU", r"Control Panel\Mouse", "MouseSpeed"),
    ("HKCU", r"Control Panel\Mouse", "MouseThreshold1"),
    ("HKCU", r"Control Panel\Mouse", "MouseThreshold2"),
    ("HKCU", r"Control Panel\Keyboard", "KeyboardDelay"),
    ("HKCU", r"Control Panel\Keyboard", "KeyboardSpeed"),
]


def get_active_power_scheme() -> Optional[str]:
    if os.name != "nt":
        return None
    try:
        out = run_hidden(["powercfg", "/getactivescheme"]).stdout
        m = re.search(r"([0-9a-fA-F-]{36})", out or "")
        return m.group(1) if m else None
    except Exception:
        return None


def has_battery() -> bool:
    if os.name != "nt":
        return False
    try:
        class _SYSTEM_POWER_STATUS(ctypes.Structure):
            _fields_=[("ACLineStatus",ctypes.c_ubyte),("BatteryFlag",ctypes.c_ubyte),("BatteryLifePercent",ctypes.c_ubyte),("SystemStatusFlag",ctypes.c_ubyte),("BatteryLifeTime",ctypes.c_ulong),("BatteryFullLifeTime",ctypes.c_ulong)]
        status=_SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
            # 128 means that Windows reports no system battery.
            return int(status.BatteryFlag) != 128
    except Exception:
        pass
    try:
        data = powershell_json("@(Get-CimInstance Win32_Battery | Select-Object -First 1 Name)")
        return bool(data)
    except Exception:
        return False


# Suspensao seletiva USB pelos GUIDs. Os apelidos SUB_USB e USBSELECTSUSPEND nao existem
# na lista de apelidos do powercfg (powercfg /aliases): com eles o powercfg
# devolvia "Parametros invalidos", a leitura voltava None em todo PC e o ajuste
# "USB sem suspensao" nunca rodava.
USB_SUBGROUP_GUID = "2a737441-1930-4402-8d77-b2bebba308a3"
USB_SELECTIVE_SUSPEND_GUID = "48e6b7a6-50f5-4782-a5d4-53bb8f07e226"


def get_usb_selective_suspend_state() -> Optional[Dict[str, int]]:
    """Read current USB selective-suspend AC/DC indexes from the active scheme.

    powercfg emits the two current values as 8-digit hex indexes even on localized
    Windows builds; use only the final two current indexes and never guess.
    /QH, and not /Q, so a plan that hides the setting still answers.
    """
    if os.name != "nt":
        return None
    try:
        p = run_hidden(["powercfg", "/QH", "SCHEME_CURRENT", USB_SUBGROUP_GUID, USB_SELECTIVE_SUSPEND_GUID], timeout=8)
        if p.returncode != 0:
            return None
        vals = re.findall(r"0x([0-9a-fA-F]{8})", (p.stdout or "") + "\n" + (p.stderr or ""))
        if len(vals) < 2:
            return None
        return {"ac": int(vals[-2], 16), "dc": int(vals[-1], 16)}
    except Exception as e:
        log(f"USB selective suspend query failed: {e}")
        return None


def _set_usb_selective_suspend_indexes(ac: int, dc: int) -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Disponível só no Windows."
    commands = [
        ["powercfg", "/SETACVALUEINDEX", "SCHEME_CURRENT", USB_SUBGROUP_GUID, USB_SELECTIVE_SUSPEND_GUID, str(int(ac))],
        ["powercfg", "/SETDCVALUEINDEX", "SCHEME_CURRENT", USB_SUBGROUP_GUID, USB_SELECTIVE_SUSPEND_GUID, str(int(dc))],
        ["powercfg", "/SETACTIVE", "SCHEME_CURRENT"],
    ]
    for cmd in commands:
        p = run_hidden(cmd, timeout=8)
        if p.returncode != 0:
            return False, (p.stderr or p.stdout or "powercfg failed").strip()
    now = get_usb_selective_suspend_state()
    ok = bool(now and now.get("ac") == int(ac) and now.get("dc") == int(dc))
    return ok, ("USB selective-suspend AC/DC state restored and verified." if ok else f"USB power verification mismatch: {now}")


def _broadcast_setting(section: str) -> None:
    if os.name != "nt":
        return
    try:
        result = ctypes.c_ulong(0)
        ctypes.windll.user32.SendMessageTimeoutW(0xFFFF, 0x001A, 0, str(section), 0x0002, 1000, ctypes.byref(result))
    except Exception as e:
        log(f"WM_SETTINGCHANGE broadcast failed for {section}: {e}")


def get_automatic_pagefile() -> Optional[bool]:
    """Return Windows automatic pagefile state when it can be queried."""
    if os.name != "nt":
        return None
    try:
        out = powershell("[bool](Get-CimInstance Win32_ComputerSystem).AutomaticManagedPagefile")
        low = str(out).strip().lower()
        if low in ("true", "1"): return True
        if low in ("false", "0"): return False
    except Exception as e:
        log(f"Automatic pagefile query failed: {e}")
    return None


def set_automatic_pagefile_verified(enabled: bool=True) -> Tuple[bool,str]:
    if os.name != "nt": return False,"Disponível só no Windows."
    capture_restore_point()
    flag = "$true" if enabled else "$false"
    try:
        powershell(f"$cs=Get-CimInstance Win32_ComputerSystem; Set-CimInstance -InputObject $cs -Property @{{AutomaticManagedPagefile={flag}}} | Out-Null")
        now=get_automatic_pagefile()
        ok=(now is enabled)
        log(f"Automatic pagefile requested={enabled} verified={ok}")
        return ok,("Paginação automática habilitada e verificada." if enabled and ok else "Configuração de paginação restaurada e verificada." if ok else "O Windows não confirmou a configuração solicitada de paginação.")
    except Exception as e:
        log(f"Automatic pagefile change failed: {e}")
        return False,str(e)


def _snapshot_payload() -> Dict[str, Any]:
    """Reads the current value of everything AZOR is allowed to change."""
    state: Dict[str, Any] = {
        "created_at": _ts(),
        "registry": [],
        "power_scheme": get_active_power_scheme(),
        "automatic_pagefile": get_automatic_pagefile(),
        "usb_selective_suspend": get_usb_selective_suspend_state(),
        "fortnite_gpu_pref": None,
    }
    for root, path, name in tracked_registry():
        state["registry"].append({
            "root": root, "path": path, "name": name, **reg_read(root, path, name)
        })
    fortnite = detect_fortnite()
    exe = fortnite.get("exe")
    if exe and winreg is not None:
        state["fortnite_gpu_pref"] = {
            "exe": exe,
            **reg_read("HKCU", r"Software\Microsoft\DirectX\UserGpuPreferences", exe)
        }
    return state


def _write_baseline_once(state: Dict[str, Any], derived: str = "") -> bool:
    """Writes the pre-AZOR baseline exactly once. Never overwrites it.

    Anything else in this file may be rewritten. This file may not: it is the only
    copy of what the machine looked like before the app ran for the first time.
    """
    if BASELINE_FILE.exists():
        return False
    payload = dict(state)
    payload["kind"] = "baseline"
    payload["captured_at"] = payload.get("created_at") or _ts()
    if derived:
        payload["derived_from"] = derived
    try:
        BASELINE_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        log(f"Baseline could not be written: {exc}")
        return False
    log("Immutable pre-AZOR baseline captured.")
    journal("baseline_captured", registry_keys=len(payload.get("registry") or []), derived_from=derived or None)
    return True


def _archive_snapshot(state: Dict[str, Any], keep: int = 20) -> Optional[str]:
    """Versioned copy per batch, so a second run cannot erase the first one's record."""
    try:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        name = time.strftime("%Y%m%d-%H%M%S") + ".json"
        target = SNAPSHOT_DIR / name
        target.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        old = sorted(SNAPSHOT_DIR.glob("*.json"))
        for extra in old[:-keep]:
            try:
                extra.unlink()
            except Exception:
                pass
        return str(target)
    except Exception as exc:
        log(f"Snapshot archive failed: {exc}")
        return None


def capture_restore_point(force: bool = False) -> Dict[str, Any]:
    """AZOR snapshot of the tracked state. This is NOT a Windows restore point.

    A Windows restore point is a separate, heavier operation and lives in
    ``create_windows_restore_point()``; the UI must not confuse the two.
    """
    if STATE_FILE.exists() and not force:
        try:
            existing = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            # An install from an older build has a restore_state but no baseline.
            # Its snapshot is the oldest record that exists, so it becomes the
            # baseline - flagged as derived, because it may already be post-tweak.
            _write_baseline_once(existing, derived="restore_state.json de uma versão anterior")
            return existing
        except Exception:
            pass
    state = _snapshot_payload()
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    _write_baseline_once(state)
    archived = _archive_snapshot(state)
    log("Restore snapshot captured.")
    journal("snapshot_captured", forced=bool(force), archive=archived)
    return state


def baseline_state() -> Dict[str, Any]:
    """The pre-AZOR state, or an empty dict when it was never captured."""
    try:
        if BASELINE_FILE.exists():
            data = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as exc:
        log(f"Baseline could not be read: {exc}")
    return {}


def baseline_registry_entry(root: str, path: str, name: str) -> Optional[Dict[str, Any]]:
    for item in (baseline_state().get("registry") or []):
        if (str(item.get("root")) == root and str(item.get("path")).casefold() == str(path).casefold()
                and str(item.get("name")).casefold() == str(name).casefold()):
            return item
    return None


def _same_registry_value(a: Any, b: Any) -> bool:
    if isinstance(a, (int, bool)) or isinstance(b, (int, bool)):
        try:
            return int(a) == int(b)
        except Exception:
            pass
    return str(a) == str(b)


def revert_registry_from_baseline(entries: List[Tuple[str, str, str]], label: str = "") -> Tuple[bool, str]:
    """Puts the listed values back to what they were before AZOR, and re-reads them.

    A value that had no baseline entry is not guessed: it is reported as unknown
    instead of being deleted, because deleting a key AZOR never recorded would be
    the app inventing a "default" it does not know.
    """
    if winreg is None or os.name != "nt":
        return False, "Disponível só no Windows."
    if not BASELINE_FILE.exists():
        return False, "Nenhum baseline foi capturado neste PC; a reversao individual precisa dele."
    done, unknown, failed = [], [], []
    for root, path, name in entries:
        item = baseline_registry_entry(root, path, name)
        if item is None:
            unknown.append(name)
            continue
        try:
            if item.get("exists"):
                reg_write(root, path, name, item.get("value"), item.get("type"))
            else:
                reg_delete_value(root, path, name)
            check = reg_read(root, path, name)
            ok = (bool(check.get("exists")) and _same_registry_value(check.get("value"), item.get("value"))) \
                if item.get("exists") else (not bool(check.get("exists")))
            (done if ok else failed).append(name)
        except Exception as exc:
            failed.append(f"{name} ({exc})")
    _broadcast_setting("Control Panel\\Mouse")
    ok = bool(done) and not failed and not unknown
    parts = []
    if done:
        parts.append(f"{len(done)} valor(es) revertido(s) e relido(s).")
    if unknown:
        parts.append("Sem baseline para: " + ", ".join(unknown) + ". Nada foi apagado por suposicao.")
    if failed:
        parts.append("Não confirmado: " + ", ".join(failed) + ".")
    detail = " ".join(parts) or "Nada a reverter."
    journal("revert_registry", label=label or None, reverted=done, unknown=unknown, failed=failed, ok=ok)
    log(f"Revert {label or entries}: ok={ok} {detail}")
    return ok, detail




def system_protection_status() -> Dict[str, Any]:
    """Is Windows System Protection on for the system drive?"""
    if os.name != "nt":
        return {"supported": False, "enabled": None, "detail": "Disponível só no Windows."}
    try:
        raw = powershell(
            "$d=$env:SystemDrive; "
            "$rp=@(Get-ComputerRestorePoint -ErrorAction SilentlyContinue); "
            "$freq=(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\SystemRestore' "
            "-Name SystemRestorePointCreationFrequency -ErrorAction SilentlyContinue).SystemRestorePointCreationFrequency; "
            "[pscustomobject]@{Drive=$d;Points=$rp.Count;Last=($rp | Select-Object -Last 1).CreationTime;Freq=$freq} | ConvertTo-Json -Compress",
            timeout=30)
        data = json.loads(raw) if raw and raw.strip().startswith("{") else {}
    except Exception as exc:
        return {"supported": True, "enabled": None, "detail": f"Estado não confirmado: {exc}"}
    points = data.get("Points")
    return {
        "supported": True,
        "enabled": None if points is None else bool(points) or None,
        "restore_points": points,
        "last_point": data.get("Last"),
        "creation_frequency_min": data.get("Freq"),
        "detail": ("Proteção do Sistema respondeu com "
                   f"{points if points is not None else 'nenhum'} ponto(s) existente(s)."),
    }


def create_windows_restore_point(description: str = "AZOR Optimization") -> Tuple[bool, str]:
    """Real Windows restore point via Checkpoint-Computer, reported honestly.

    Windows silently refuses a second restore point within 24 h unless
    SystemRestorePointCreationFrequency says otherwise, and it refuses entirely
    when System Protection is off. Both cases are reported as what they are
    instead of being painted as success.
    """
    if os.name != "nt":
        return False, "Disponível só no Windows."
    if not is_admin():
        return False, "Um ponto de restauração do Windows exige o AZOR aberto como administrador."
    before = None
    try:
        raw = powershell("@(Get-ComputerRestorePoint -ErrorAction SilentlyContinue).Count", timeout=40)
        before = int(str(raw).strip() or "0")
    except Exception:
        before = None
    try:
        out = powershell(
            "try { Checkpoint-Computer -Description " + json.dumps(str(description)[:60]) +
            " -RestorePointType 'MODIFY_SETTINGS' -ErrorAction Stop; 'OK' } catch { 'ERR:' + $_.Exception.Message }",
            timeout=180)
    except Exception as exc:
        journal("windows_restore_point", ok=False, detail=str(exc))
        return False, f"O Windows não criou o ponto de restauração: {exc}"
    after = None
    try:
        raw = powershell("@(Get-ComputerRestorePoint -ErrorAction SilentlyContinue).Count", timeout=40)
        after = int(str(raw).strip() or "0")
    except Exception:
        after = None
    created = (isinstance(before, int) and isinstance(after, int) and after > before)
    if created:
        journal("windows_restore_point", ok=True, points_before=before, points_after=after)
        return True, f"Ponto de restauração do Windows criado e confirmado ({before} -> {after})."
    if "ERR:" in str(out):
        msg = str(out).split("ERR:", 1)[1].strip()
        journal("windows_restore_point", ok=False, detail=msg)
        return False, ("O Windows recusou o ponto de restauração: " + msg +
                       " Verifique se a Proteção do Sistema esta ligada no disco do Windows.")
    journal("windows_restore_point", ok=False, points_before=before, points_after=after, raw=str(out)[:200])
    return False, ("O comando retornou sem erro, mas a contagem de pontos não aumentou. "
                   "O Windows costuma ignorar um segundo ponto criado no mesmo dia; "
                   "o snapshot próprio do AZOR foi gravado de qualquer forma.")


def _repair_guarded_registry() -> Dict[Tuple[str, str, str], Tuple[Any, ...]]:
    """Valores do baseline que são o próprio defeito que um conserto do AZOR desfez.

    Consertos não entram no Desfazer (a tela diz isso). Das chaves que os
    consertos mexem, so o pre-carregamento esta no snapshot rastreado - pelos
    itens de teste do SysMain e do Prefetcher. Num PC que chegou sabotado, o
    baseline guarda EnablePrefetcher = 0 e SysMain desabilitado; sem esta guarda,
    "Desfazer tudo" gravaria o defeito de volta. So vale quando o AZOR aplicou o
    conserto: quem desligou por conta própria e nunca consertou recupera o que tinha.
    """
    if "app_launch_cache_repair" not in set(desired_task_ids()):
        return {}
    return {
        ("hklm", PREFETCH_PARAMS.casefold(), "enableprefetcher"): (0,),
        ("hklm", r"system\currentcontrolset\services\sysmain", "start"): (4,),
    }


def restore_all(progress: Optional[Callable[[str, str], None]] = None, target: str = "baseline") -> List[Dict[str, str]]:
    """Restore Azor-tracked state and verify every mandatory write before reporting success.

    ``target`` decides WHICH record to go back to. "baseline" is how this PC looked
    before AZOR ever ran, and is the only honest meaning of "restore Windows
    defaults"; "last" is merely the snapshot taken before the most recent batch.
    """
    results: List[Dict[str, str]] = []
    state: Optional[Dict[str, Any]] = None
    origin = ""
    if str(target).lower() != "last":
        base = baseline_state()
        if base:
            state = base
            origin = "baseline (estado anterior ao AZOR)"
            if base.get("derived_from"):
                origin += f", derivado de {base.get('derived_from')}"
    if state is None:
        if not STATE_FILE.exists():
            return [{"name": "Restore", "status": "not_applicable", "detail": "Nenhum snapshot de restauração existe neste PC."}]
        try:
            state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            origin = "snapshot do último lote"
        except Exception as e:
            return [{"name":"Restore","status":"failed","detail":f"Restore snapshot could not be read: {e}"}]
    results.append({"name": "Origem da restauração", "status": "completed",
                    "detail": f"Restaurando a partir do {origin}, capturado em {state.get('captured_at') or state.get('created_at') or 'data desconhecida'}."})

    def report(name: str, status: str, detail: str = ""):
        results.append({"name": name, "status": status, "detail": detail})
        if progress:
            progress(name, status)

    def same_value(a: Any, b: Any) -> bool:
        if isinstance(a, (int, bool)) or isinstance(b, (int, bool)):
            try: return int(a) == int(b)
            except Exception: pass
        return str(a) == str(b)

    guarded = _repair_guarded_registry()
    for item in state.get("registry", []):
        label = item.get("name", "Registry")
        broken = guarded.get((str(item.get("root") or "").casefold(), str(item.get("path") or "").casefold(),
                              str(item.get("name") or "").casefold()))
        if broken and item.get("exists") and item.get("value") in broken:
            report(label, "not_applicable",
                   "Preservado: o valor anterior e o defeito que o AZOR consertou. Consertos não entram no Desfazer.")
            continue
        try:
            if item.get("exists"):
                reg_write(item["root"], item["path"], item["name"], item.get("value"), item.get("type"))
            else:
                reg_delete_value(item["root"], item["path"], item["name"])
            verify = reg_read(item["root"], item["path"], item["name"])
            ok = bool(verify.get("exists")) and same_value(verify.get("value"), item.get("value")) if item.get("exists") else not bool(verify.get("exists"))
            report(label, "completed" if ok else "failed", "Original registry state restored and verified." if ok else "Registry restore write could not be verified.")
        except Exception as e:
            report(label, "failed", str(e))

    fgp = state.get("fortnite_gpu_pref")
    if fgp and fgp.get("exe"):
        try:
            if fgp.get("exists"):
                reg_write("HKCU", r"Software\Microsoft\DirectX\UserGpuPreferences", fgp["exe"], fgp.get("value"), fgp.get("type"))
            else:
                reg_delete_value("HKCU", r"Software\Microsoft\DirectX\UserGpuPreferences", fgp["exe"])
            verify=reg_read("HKCU",r"Software\Microsoft\DirectX\UserGpuPreferences",fgp["exe"])
            ok=bool(verify.get("exists")) and same_value(verify.get("value"),fgp.get("value")) if fgp.get("exists") else not bool(verify.get("exists"))
            report("Fortnite GPU preference", "completed" if ok else "failed", "Original GPU preference restored and verified." if ok else "GPU preference restore was not verified.")
        except Exception as e:
            report("Fortnite GPU preference", "failed", str(e))

    scheme = state.get("power_scheme")
    if scheme and os.name == "nt":
        try:
            p = run_hidden(["powercfg", "/setactive", str(scheme)])
            time.sleep(0.25)
            active=(get_active_power_scheme() or "").lower()
            ok=p.returncode==0 and active==str(scheme).lower()
            report("Power plan", "completed" if ok else "failed", "Original power scheme restored and verified." if ok else f"Power restore was not verified; active={active or 'unknown'}.")
        except Exception as e:
            report("Power plan", "failed", str(e))

    original_pagefile=state.get("automatic_pagefile", None)
    if isinstance(original_pagefile, bool):
        try:
            ok,detail=set_automatic_pagefile_verified(original_pagefile)
            report("Pagefile", "completed" if ok else "failed", detail)
        except Exception as e:
            report("Pagefile", "failed", str(e))

    usb_state = state.get("usb_selective_suspend")
    if isinstance(usb_state, dict) and isinstance(usb_state.get("ac"), int) and isinstance(usb_state.get("dc"), int):
        try:
            ok, detail = _set_usb_selective_suspend_indexes(usb_state["ac"], usb_state["dc"])
            report("USB selective suspend", "completed" if ok else "failed", detail)
        except Exception as e:
            report("USB selective suspend", "failed", str(e))

    _broadcast_setting("Control Panel\\Mouse")
    _broadcast_setting("Control Panel\\Keyboard")
    log("Verified restore operation finished.")
    journal("restore_all", origin=origin,
            failed=[r["name"] for r in results if r.get("status") == "failed"],
            completed=sum(1 for r in results if r.get("status") == "completed"))
    return results


def restore_all_report(target: str = "baseline") -> Dict[str, Any]:
    """restore_all com o resumo que a tela mostra. Roda no processo elevado."""
    res = restore_all(target=target)
    failed = sum(1 for x in res if x.get("status") == "failed")
    completed = sum(1 for x in res if x.get("status") == "completed")
    ok = failed == 0 and completed > 0
    detail = (f"Restauração verificada: {completed} concluída(s), {failed} falha(s)." if completed
              else (res[0].get("detail") if res else "Nenhuma etapa de restauração foi executada."))
    return {"ok": ok, "detail": detail, "results": res, "target": target}


def set_game_mode(enabled: bool = True) -> None:
    capture_restore_point()
    val = 1 if enabled else 0
    reg_write("HKCU", r"Software\Microsoft\GameBar", "AllowAutoGameMode", val)
    reg_write("HKCU", r"Software\Microsoft\GameBar", "AutoGameModeEnabled", val)
    log(f"Game Mode set to {enabled}.")


def set_game_dvr(enabled: bool = False) -> None:
    capture_restore_point()
    val = 1 if enabled else 0
    reg_write("HKCU", r"System\GameConfigStore", "GameDVR_Enabled", val)
    reg_write("HKCU", r"Software\Microsoft\Windows\CurrentVersion\GameDVR", "AppCaptureEnabled", val)
    log(f"Game DVR/App Capture set to {enabled}.")


def set_background_apps_disabled(disabled: bool = True) -> None:
    capture_restore_point()
    reg_write("HKCU", r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications", "GlobalUserDisabled", 1 if disabled else 0)
    log(f"Background app global switch disabled={disabled}.")








def flush_dns() -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Disponível só no Windows."
    p = run_hidden(["ipconfig", "/flushdns"])
    ok = p.returncode == 0
    detail = (p.stdout or p.stderr or "").strip()
    log("DNS cache flushed." if ok else f"DNS flush failed: {detail}")
    return ok, detail


LAST_DEVICE_DETECTION_META: Dict[str, Any] = {"methods": [], "errors": [], "updated_at": None}


def _device_rows(script: str, method: str, errors: List[str]) -> List[Dict[str, Any]]:
    try:
        data = powershell_json(script, timeout=22)
        if data is None:
            return []
        if isinstance(data, dict):
            data = [data]
        return [x for x in data if isinstance(x, dict)]
    except Exception as e:
        errors.append(f"{method}: {e}")
        log(f"Device detection {method} failed: {e}")
        return []



def _looks_like_game_controller(name: Any, cls: Any = "", ident: Any = "") -> bool:
    low = " ".join([str(name or ""), str(cls or ""), str(ident or "")]).casefold()
    # Storage/chipset/host controllers are NOT game controllers.
    blocked = [
        "ahci", "sata", "storage controller", "controlador de armazenamento",
        "controlador de armazen", "raid", "nvme", "ide ata", "pci express root",
        "host controller", "controlador host", "usb root hub", "storahci", "standard sata ahci",
        # A "system controller" HID collection is the power/media block that
        # keyboards and mice expose. It is not a gamepad, and counting it as one
        # was reporting phantom controllers on machines with none connected.
        "system controller", "controlador de sistema", "consumer control",
        "controle do consumidor", "vendor-defined", "definido pelo fornecedor",
    ]
    if any(x in low for x in blocked):
        return False
    strong = [
        "xbox", "gamepad", "game controller", "controlador de jogo", "controle de jogo",
        "xinput", "dualsense", "dualshock", "wireless controller", "gaming input", "joystick"
    ]
    if any(x in low for x in strong):
        return True
    # Generic 'controller' alone is too broad. Require a HID/game-input identity.
    return "controller" in low and any(x in low for x in ["hid", "xinput", "ig_", "game"] )

def _device_physical_key(entry: Dict[str, str]) -> str:
    """One physical device = one key, even when Windows exposes it several times.

    A single keyboard shows up as Win32_Keyboard, as one or more HID collections
    under Get-PnpDevice and again in the PnP registry. They are the same object
    on the desk, so they are folded together by USB vendor/product id.
    """
    ids = _extract_vid_pid(entry.get("id"))
    if ids.get("vid") and ids.get("pid"):
        return f"vidpid:{ids['vid']}:{ids['pid']}"
    return "name:" + str(entry.get("name") or "").strip().casefold()


def _device_entry_rank(entry: Dict[str, str]) -> Tuple[int, int, int]:
    """Lower is better: the entry that best names the hardware wins the group."""
    low = str(entry.get("name") or "").casefold()
    generic = any(x in low for x in [
        "hid keyboard", "dispositivo de teclado hid", "hid-compliant mouse",
        "mouse compat", "teclado hid", "mouse hid", "standard ps/2",
        "dispositivo de entrada usb", "usb input device", "unknown",
    ])
    source_rank = {"Get-PnpDevice": 0, "Win32_PnPEntity": 1, "Win32_Keyboard": 2, "Win32_PointingDevice": 2}
    virtual = 1 if "IG_" in str(entry.get("id") or "").upper() else 0
    return (virtual, 1 if generic else 0, source_rank.get(str(entry.get("source")), 3))


def _collapse_duplicate_devices(result: Dict[str, List[Dict[str, str]]]) -> None:
    """Collapses the multi-provider view into the hardware actually connected.

    Fixes two counts the UI was reporting wrong: the same keyboard/mouse listed
    once per HID collection, and a gamepad counted twice because Windows also
    publishes its virtual XInput device.
    """
    for kind, entries in result.items():
        groups: Dict[str, Dict[str, str]] = {}
        interfaces: Dict[str, int] = {}
        for entry in entries:
            key = _device_physical_key(entry)
            interfaces[key] = interfaces.get(key, 0) + 1
            best = groups.get(key)
            if best is None or _device_entry_rank(entry) < _device_entry_rank(best):
                groups[key] = entry
        merged = []
        for key, entry in groups.items():
            item = dict(entry)
            item["interfaces"] = interfaces.get(key, 1)
            merged.append(item)
        result[kind] = merged

    # A gamepad is published twice: as the physical USB device and as the
    # virtual XInput (IG_) device. Keep the virtual one only when it is alone.
    pads = result.get("controller") or []
    physical = [x for x in pads if "IG_" not in str(x.get("id") or "").upper()]
    if physical and len(physical) != len(pads):
        result["controller"] = physical

    # Gamepads, keyboards and mice all expose extra HID collections. Whatever is
    # already identified as a controller must not be counted again as a mouse or
    # a keyboard.
    pad_keys = {_device_physical_key(x) for x in result.get("controller") or []}
    for kind in ("keyboard", "mouse"):
        result[kind] = [x for x in result.get(kind) or [] if _device_physical_key(x) not in pad_keys]


_DEVICE_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
DEVICE_CACHE_TTL = 90.0


def detect_devices(force: bool = False) -> Dict[str, List[Dict[str, str]]]:
    """Cached device detection.

    Enumerating devices costs a powershell.exe round trip. The dashboard used to
    pay it every 12 s inside the summary poll; peripherals do not change that
    often, and the "detect again" button still forces a fresh read.
    """
    global _DEVICE_CACHE
    now = time.time()
    cached = _DEVICE_CACHE.get("data")
    if not force and cached is not None and (now - float(_DEVICE_CACHE.get("ts", 0))) < DEVICE_CACHE_TTL:
        return copy.deepcopy(cached)
    data = _detect_devices_uncached()
    _DEVICE_CACHE = {"ts": now, "data": copy.deepcopy(data)}
    return data


def _detect_devices_uncached() -> Dict[str, List[Dict[str, str]]]:
    '''Detect input devices using multiple Windows data sources.

    V5.3 depended almost entirely on Get-PnpDevice. On some Windows installs the
    PnpDevice module/present-only query returns nothing even while HID devices work.
    V5.4 merges PnP + CIM keyboard/mouse + PnP entity controller fallbacks and
    deduplicates the result instead of treating one failed provider as "0 devices".
    '''
    global LAST_DEVICE_DETECTION_META
    result: Dict[str, List[Dict[str, str]]] = {"keyboard": [], "mouse": [], "controller": []}
    errors: List[str] = []
    methods: List[str] = []
    if os.name != "nt":
        LAST_DEVICE_DETECTION_META = {"methods": ["non-windows"], "errors": [], "updated_at": _ts()}
        return result

    seen: Dict[str, set] = {"keyboard": set(), "mouse": set(), "controller": set()}

    def add(kind: str, name: Any, status: Any = "Unknown", ident: Any = "", cls: Any = "", source: str = "Windows") -> None:
        n = str(name or "").strip()
        if not n:
            return
        ident_s = str(ident or "").strip()
        key = (ident_s.lower() if ident_s else n.lower())
        if key in seen[kind]:
            return
        seen[kind].add(key)
        result[kind].append({
            "name": n,
            "class": str(cls or kind.title()),
            "status": str(status or "Unknown"),
            "id": ident_s,
            "source": source,
        })


    # Providers 1-4 share ONE powershell.exe. Each cold powershell start costs
    # ~0.8 s, so asking four times for four answers was paying that price four
    # times per detection.
    combined = _device_rows(r'''
$pnp=@(); $kb=@(); $mice=@(); $ctl=@()
try{ $pnp=@(Get-PnpDevice -PresentOnly -ErrorAction Stop |
      Where-Object { $_.Class -in @('Keyboard','Mouse','HIDClass','XnaComposite') } |
      Select-Object FriendlyName,Class,Status,InstanceId) }catch{}
try{ $kb=@(Get-CimInstance Win32_Keyboard -ErrorAction Stop |
      Select-Object Name,Status,DeviceID,PNPDeviceID) }catch{}
try{ $mice=@(Get-CimInstance Win32_PointingDevice -ErrorAction Stop |
      Select-Object Name,Status,DeviceID,PNPDeviceID) }catch{}
try{ $ctl=@(Get-CimInstance Win32_PnPEntity -ErrorAction Stop |
      Where-Object {
        $_.ConfigManagerErrorCode -eq 0 -and
        ($_.Name -match '(?i)xbox|gamepad|game controller|controlador de jogo|controle de jogo|xinput|dualsense|dualshock|wireless controller|gaming input|joystick')
      } |
      Select-Object Name,Status,DeviceID,PNPClass,ConfigManagerErrorCode) }catch{}
[pscustomobject]@{ pnp=$pnp; keyboards=$kb; mice=$mice; controllers=$ctl }
''', "WindowsDeviceProviders", errors)

    bundle = combined[0] if combined else {}

    def rows(key: str) -> List[Dict[str, Any]]:
        value = bundle.get(key)
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list):
            return [x for x in value if isinstance(x, dict)]
        return []

    pnp = rows("pnp")
    if pnp:
        methods.append("Get-PnpDevice")
    for d in pnp:
        name = str(d.get("FriendlyName") or "Unknown device")
        cls = str(d.get("Class") or "")
        low = name.casefold()
        if cls.casefold() == "keyboard" or any(k in low for k in ["keyboard", "teclado"]):
            add("keyboard", name, d.get("Status"), d.get("InstanceId"), cls, "Get-PnpDevice")
        elif cls.casefold() == "mouse" or any(k in low for k in ["mouse", "pointing device", "dispositivo apontador"]):
            add("mouse", name, d.get("Status"), d.get("InstanceId"), cls, "Get-PnpDevice")
        elif _looks_like_game_controller(name, cls, d.get("InstanceId")):
            add("controller", name, d.get("Status"), d.get("InstanceId"), cls, "Get-PnpDevice")

    keyboards = rows("keyboards")
    if keyboards:
        methods.append("Win32_Keyboard")
    for d in keyboards:
        add("keyboard", d.get("Name") or "Teclado HID", d.get("Status") or "OK", d.get("PNPDeviceID") or d.get("DeviceID"), "Keyboard", "Win32_Keyboard")

    mice = rows("mice")
    if mice:
        methods.append("Win32_PointingDevice")
    for d in mice:
        add("mouse", d.get("Name") or "Mouse HID", d.get("Status") or "OK", d.get("PNPDeviceID") or d.get("DeviceID"), "Mouse", "Win32_PointingDevice")

    controllers = rows("controllers")
    if controllers:
        methods.append("Win32_PnPEntity")
    for d in controllers:
        if _looks_like_game_controller(d.get("Name"), d.get("PNPClass"), d.get("DeviceID")):
            add("controller", d.get("Name") or "Game Controller", d.get("Status") or "OK", d.get("DeviceID"), d.get("PNPClass") or "HIDClass", "Win32_PnPEntity")

    # Provider 5: direct read-only PnP registry fallback. This remains useful
    # when WMI/CIM is disabled by policy but HID devices are working normally.
    # The registry walk exists for machines where WMI/CIM is blocked by policy.
    # Running it when CIM already answered only produced a second, differently
    # named copy of hardware that was already on the list.
    registry_rows=0
    if winreg is not None and not methods:
        try:
            for enum_branch in [r"SYSTEM\CurrentControlSet\Enum\HID",r"SYSTEM\CurrentControlSet\Enum\USB"]:
                try: root_key=winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,enum_branch,0,winreg.KEY_READ)
                except OSError: continue
                with root_key:
                    for i in range(min(512,winreg.QueryInfoKey(root_key)[0])):
                        hardware=winreg.EnumKey(root_key,i)
                        try: hardware_key=winreg.OpenKey(root_key,hardware,0,winreg.KEY_READ)
                        except OSError: continue
                        with hardware_key:
                            for j in range(min(64,winreg.QueryInfoKey(hardware_key)[0])):
                                instance=winreg.EnumKey(hardware_key,j)
                                try: key=winreg.OpenKey(hardware_key,instance,0,winreg.KEY_READ)
                                except OSError: continue
                                with key:
                                    values={}
                                    for value_name in ["FriendlyName","DeviceDesc","Class","Service","HardwareID","CompatibleIDs"]:
                                        try: values[value_name]=winreg.QueryValueEx(key,value_name)[0]
                                        except OSError: pass
                                raw_name=str(values.get("FriendlyName") or values.get("DeviceDesc") or "").split(";")[-1].strip()
                                joined=" ".join([hardware,instance]+[str(x) for x in values.values()]).casefold()
                                ident=f"{enum_branch.split(chr(92))[-1]}\\{hardware}\\{instance}"
                                if any(x in joined for x in ["keyboard","teclado","kbdhid"]):
                                    add("keyboard",raw_name or "Teclado HID","OK",ident,values.get("Class") or "Keyboard","Registry PnP");registry_rows+=1
                                elif any(x in joined for x in ["mouse","pointing","mouhid"]):
                                    add("mouse",raw_name or "Mouse HID","OK",ident,values.get("Class") or "Mouse","Registry PnP");registry_rows+=1
                                elif _looks_like_game_controller(raw_name or joined, values.get("Class") or "HIDClass", ident + " " + joined):
                                    add("controller",raw_name or "Controle HID","OK",ident,values.get("Class") or "HIDClass","Registry PnP");registry_rows+=1
            if registry_rows: methods.append("Registry PnP")
        except Exception as e:
            errors.append(f"Registry PnP: {e}")
            log(f"Device detection Registry PnP failed: {e}")

    _collapse_duplicate_devices(result)

    # O nome acima e o do DRIVER: um GameSir em modo XInput chega como
    # "Controlador XBOX 360 para Windows". A identidade pelo VID vai junto, e a
    # tela mostra o fabricante em vez do controle que ele emula.
    from azor_modules import usb_ids
    for kind, entries in result.items():
        for entry in entries:
            entry.update(usb_ids.identify(kind, entry))

    # Sort real branded/friendly names above generic HID names, without inventing identity.
    def score(item: Dict[str, str]) -> Tuple[int, str]:
        low = item.get("name", "").casefold()
        generic = any(x in low for x in ["hid keyboard", "dispositivo de teclado hid", "hid-compliant mouse", "mouse compatível com hid", "standard ps/2", "unknown"])
        return (1 if generic else 0, low)
    for kind in result:
        result[kind].sort(key=score)

    LAST_DEVICE_DETECTION_META = {
        "methods": list(dict.fromkeys(methods)),
        "errors": errors[-6:],
        "updated_at": _ts(),
        "counts": {k: len(v) for k, v in result.items()},
    }
    log("Device detection V5.4: " + json.dumps(LAST_DEVICE_DETECTION_META, ensure_ascii=False))
    return result



def _epic_manifest_locations() -> List[Path]:
    base = Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    return list(base.glob("*.item")) if base.exists() else []


def detect_fortnite() -> Dict[str, Any]:
    info: Dict[str, Any] = {"installed": False, "root": None, "exe": None, "config": None}
    candidates: List[Path] = []
    for mf in _epic_manifest_locations():
        try:
            data = json.loads(mf.read_text(encoding="utf-8", errors="replace"))
            dn = str(data.get("DisplayName") or "")
            an = str(data.get("AppName") or "")
            if "fortnite" in (dn + " " + an).lower():
                loc = data.get("InstallLocation")
                if loc:
                    candidates.append(Path(loc))
        except Exception:
            continue
    for raw in [r"C:\Program Files\Epic Games\Fortnite", r"D:\Epic Games\Fortnite", r"E:\Epic Games\Fortnite"]:
        candidates.append(Path(raw))

    seen = set()
    for root in candidates:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        exe = root / "FortniteGame" / "Binaries" / "Win64" / "FortniteClient-Win64-Shipping.exe"
        if exe.exists():
            info.update({"installed": True, "root": str(root), "exe": str(exe)})
            break
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    cfg = local / "FortniteGame" / "Saved" / "Config" / "WindowsClient" / "GameUserSettings.ini"
    if cfg.exists():
        info["config"] = str(cfg)
    return info


# ---------------------------------------------------------------------------
# Tela cheia exclusiva: por executavel, nao para o Windows inteiro
# ---------------------------------------------------------------------------
#
# Desligar as "otimizacoes de tela cheia" tira o compositor do caminho entre o
# frame pronto e o monitor. O ganho e real, mas o AZOR fazia isso pela chave do
# GameConfigStore, que vale para TODOS os aplicativos - e ai o overlay do
# Discord, do OBS e dos capturadores para de aparecer no PC inteiro, nao so no
# jogo.
#
# O Windows guarda a mesma opcao POR EXECUTAVEL, que e o que a caixinha
# "Desabilitar otimizacoes de tela cheia" nas Propriedades do arquivo grava:
#
#   HKCU\Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers
#   <caminho completo do exe> = "~ DISABLEDXMAXIMIZEDWINDOWEDMODE"
#
# Mesmo beneficio dentro do Fortnite, zero dano colateral fora dele. E como e o
# mesmo mecanismo da interface do Windows, o cliente consegue conferir e desfazer
# pela propria janela de Propriedades do executavel.

APPCOMPAT_LAYERS = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
FSO_OFF_FLAG = "DISABLEDXMAXIMIZEDWINDOWEDMODE"


def _layers_value_for(exe: str) -> str:
    """Preserva as flags que já existiam para esse exe e soma a nossa."""
    current = str(reg_read("HKCU", APPCOMPAT_LAYERS, exe).get("value") or "")
    parts = [p for p in current.split() if p and p != "~"]
    if FSO_OFF_FLAG not in parts:
        parts.append(FSO_OFF_FLAG)
    return "~ " + " ".join(parts)


def set_fortnite_fullscreen_exclusive(enabled: bool = True) -> Tuple[bool, str]:
    """Desliga as otimizacoes de tela cheia SO para o executavel do Fortnite."""
    if os.name != "nt":
        return False, "Disponível só no Windows."
    exe = (detect_fortnite() or {}).get("exe")
    if not exe:
        return False, "O executável do Fortnite não foi localizado neste PC."
    baseline_backfill("fortnite_fso", {"exe": exe,
                                       **reg_read("HKCU", APPCOMPAT_LAYERS, exe)})
    try:
        if enabled:
            reg_write("HKCU", APPCOMPAT_LAYERS, exe, _layers_value_for(exe))
        else:
            reg_delete_value("HKCU", APPCOMPAT_LAYERS, exe)
        back = str(reg_read("HKCU", APPCOMPAT_LAYERS, exe).get("value") or "")
        ok = (FSO_OFF_FLAG in back) if enabled else (FSO_OFF_FLAG not in back)
        journal("fortnite_fso", exe=exe, enabled=enabled, ok=ok, value=back)
        log(f"Fortnite FSO {'off' if enabled else 'restaurado'}: {back!r}",
            "SUCCESS" if ok else "ERROR")
        return ok, (f"Tela cheia exclusiva ativada apenas para o Fortnite (relido: {back})."
                    if ok else f"A gravação não foi confirmada na releitura (valor atual: {back!r}).")
    except Exception as exc:
        log_error(f"set_fortnite_fullscreen_exclusive: {exc}")
        return False, str(exc)


def set_fortnite_high_performance_gpu() -> Tuple[bool, str]:
    fort = detect_fortnite()
    exe = fort.get("exe")
    if not exe:
        return False, "O Fortnite não foi encontrado neste PC."
    ok, detail = set_game_high_performance_gpu(str(exe), capture=True)
    log(f"Fortnite high-performance GPU preference verified={ok} executable={exe!r}.")
    return ok, ("Fortnite foi definido como Alto desempenho no Windows e a configuração foi relida e confirmada." if ok else detail)




def _normalize_game_exe_path(exe_path: str) -> Optional[Path]:
    """Return a validated, absolute Windows executable path without guessing."""
    raw = str(exe_path or "").strip().strip('"')
    if not raw:
        return None
    try:
        p = Path(os.path.expandvars(raw)).expanduser()
        if not p.is_absolute():
            return None
        p = p.resolve(strict=False)
    except Exception:
        return None
    if p.suffix.lower() != ".exe" or not p.exists() or not p.is_file():
        return None
    return p


def set_game_high_performance_gpu(exe_path: str, capture: bool = True) -> Tuple[bool, str]:
    """Set Windows per-app Graphics preference to High performance and verify it.

    Windows stores per-application GPU preference under HKCU\\Software\\Microsoft\\DirectX\\UserGpuPreferences.
    The executable path itself is the registry value name. We only report success after
    reading that exact value name back and confirming GpuPreference=2.
    """
    p = _normalize_game_exe_path(exe_path)
    if p is None:
        return False, "Selecione um arquivo .exe de jogo válido."
    exe = str(p)
    if capture:
        try:
            capture_restore_point()
        except Exception as e:
            log(f"Snapshot before game GPU preference failed: {e}")
    before = reg_read("HKCU", r"Software\Microsoft\DirectX\UserGpuPreferences", exe)
    reg_write("HKCU", r"Software\Microsoft\DirectX\UserGpuPreferences", exe, "GpuPreference=2;")
    verify = reg_read("HKCU", r"Software\Microsoft\DirectX\UserGpuPreferences", exe)
    observed = str(verify.get("value") or "")
    ok = bool(verify.get("exists")) and "GpuPreference=2" in observed
    if ok:
        remember_game_gpu_preference(exe, before)
    log(f"Game high-performance GPU preference exe={exe!r} verified={ok} observed={observed!r}")
    return ok, (f"{p.name} foi definido como Alto desempenho no Windows e a preferência foi relida e confirmada." if ok else f"A preferência de GPU de {p.name} foi gravada, mas não pôde ser confirmada na releitura.")


def _game_gpu_state_file() -> Path:
    return DATA_DIR / "game_gpu_preferences.json"


def remember_game_gpu_preference(exe: str, before: Dict[str, Any]) -> None:
    """Persist a small AZOR-owned list so the UI can show configured games.

    The original registry value is stored only for values configured through this generic
    games panel; it lets AZOR restore individual entries without touching unrelated apps.
    """
    path = _game_gpu_state_file()
    data = {"games": []}
    try:
        if path.exists():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict): data = loaded
    except Exception:
        data = {"games": []}
    games = data.get("games") if isinstance(data.get("games"), list) else []
    low = exe.lower()
    existing = next((x for x in games if str(x.get("exe") or "").lower() == low), None)
    item = {
        "exe": exe,
        "name": Path(exe).stem,
        "configured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "original_exists": bool(before.get("exists")),
        "original_value": before.get("value"),
        "original_type": before.get("type"),
    }
    if existing:
        # Preserve the first original value so repeated applies do not overwrite restore data.
        item["original_exists"] = existing.get("original_exists", item["original_exists"])
        item["original_value"] = existing.get("original_value", item["original_value"])
        item["original_type"] = existing.get("original_type", item["original_type"])
        games[games.index(existing)] = item
    else:
        games.append(item)
    data["games"] = games[-40:]
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


def list_game_gpu_preferences() -> Dict[str, Any]:
    data={"games":[]}
    path=_game_gpu_state_file()
    try:
        if path.exists():
            loaded=json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded,dict): data=loaded
    except Exception as e:
        log(f"Game GPU preferences read failed: {e}")
    out=[]
    for item in data.get("games",[]):
        exe=str(item.get("exe") or "")
        pref=reg_read("HKCU",r"Software\Microsoft\DirectX\UserGpuPreferences",exe) if exe else {"exists":False}
        value=str(pref.get("value") or "")
        out.append({**item,"exists":bool(exe and Path(exe).exists()),"high_performance":bool(pref.get("exists") and "GpuPreference=2" in value),"observed":value})
    return {"ok":True,"games":out}


def restore_game_gpu_preference(exe_path: str) -> Tuple[bool, str]:
    p_raw=str(exe_path or "").strip().strip('"')
    if not p_raw:
        return False,"Executável não informado."
    data=list_game_gpu_preferences(); item=next((x for x in data.get("games",[]) if str(x.get("exe") or "").lower()==p_raw.lower()),None)
    if not item:
        return False,"Esse jogo não possui estado original salvo pelo AZOR."
    if item.get("original_exists"):
        typ=item.get("original_type")
        try: typ=int(typ) if typ is not None else None
        except Exception: typ=None
        reg_write("HKCU",r"Software\Microsoft\DirectX\UserGpuPreferences",p_raw,item.get("original_value") or "",typ)
        verify=reg_read("HKCU",r"Software\Microsoft\DirectX\UserGpuPreferences",p_raw)
        ok=bool(verify.get("exists")) and str(verify.get("value") or "")==str(item.get("original_value") or "")
    else:
        reg_delete_value("HKCU",r"Software\Microsoft\DirectX\UserGpuPreferences",p_raw)
        verify=reg_read("HKCU",r"Software\Microsoft\DirectX\UserGpuPreferences",p_raw)
        ok=not bool(verify.get("exists"))
    log(f"Game GPU preference restore exe={p_raw!r} verified={ok}")
    return ok,("Preferência gráfica original restaurada e verificada." if ok else "A restauração foi executada, mas não passou na verificação.")


def pick_game_executable() -> Tuple[bool, str, Optional[str]]:
    """Open the native Windows file picker. Manual path entry remains available in the UI."""
    if os.name != "nt":
        return False,"O seletor de executável está disponível no Windows.",None
    script = r"Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Title='Selecione o executavel do jogo'; $d.Filter='Executaveis (*.exe)|*.exe'; $d.CheckFileExists=$true; $d.Multiselect=$false; if($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK){[Console]::OutputEncoding=[Text.Encoding]::UTF8; Write-Output $d.FileName}"
    try:
        p=run_hidden(["powershell.exe","-NoProfile","-STA","-ExecutionPolicy","Bypass","-Command",script],timeout=120)
        selected=(p.stdout or "").strip().splitlines()
        selected=selected[-1].strip() if selected else ""
        valid=_normalize_game_exe_path(selected)
        if valid is None:
            return False,"Nenhum executável foi selecionado.",None
        return True,"Executável selecionado.",str(valid)
    except Exception as e:
        log(f"Game executable picker failed: {e}")
        return False,f"Não foi possível abrir o seletor: {e}",None

def backup_fortnite_config() -> Tuple[bool, str]:
    fort = detect_fortnite()
    cfg = fort.get("config")
    if not cfg:
        return False, "O arquivo de configuração do Fortnite ainda não existe. Abra o jogo uma vez e feche."
    src = Path(cfg)
    dst = DATA_DIR / f"GameUserSettings.backup.{time.strftime('%Y%m%d-%H%M%S')}.ini"
    shutil.copy2(src, dst)
    same = hashlib.sha256(src.read_bytes()).digest() == hashlib.sha256(dst.read_bytes()).digest()
    if not same:
        try: dst.unlink(missing_ok=True)
        except Exception: pass
        return False, "A cópia de segurança da configuração do Fortnite não bateu com o original. Nada foi alterado."
    log(f"Fortnite config backup created and verified: {dst.name}")
    return True, str(dst)




def ping_test(host: str = "1.1.1.1") -> Dict[str, Any]:
    if os.name == "nt":
        p = run_hidden(["ping", "-n", "4", host], timeout=12)
    else:
        p = run_hidden(["ping", "-c", "4", host], timeout=12)
    text = (p.stdout or "") + "\n" + (p.stderr or "")
    times = [int(x) for x in re.findall(r"(?:time[=<]|tempo[=<])\s*(\d+)\s*ms", text, flags=re.I)]
    if not times:
        times = [int(x) for x in re.findall(r"(\d+)ms", text, flags=re.I)]
    return {
        "ok": p.returncode == 0,
        "host": host,
        "avg_ms": round(sum(times) / len(times), 1) if times else None,
        "min_ms": min(times) if times else None,
        "max_ms": max(times) if times else None,
        "raw": text.strip(),
    }


class TimerResolutionSession:
    """Verified Windows timer-resolution session with a native 0.5 ms target when supported."""
    def __init__(self):
        self.active=False; self.requested_ms=0.5; self.actual_ms=None; self.mode="off"; self._desired_100ns=0; self._winmm_period=0
    @staticmethod
    def _to_native(ms: float) -> int: return max(1,int(round(float(ms)*10000.0)))
    @staticmethod
    def _to_ms(v: int) -> float: return round(float(v)/10000.0,4)
    def query(self) -> Dict[str,Any]:
        if os.name!="nt": return {"supported":False,"active":self.active,"requested_ms":self.requested_ms,"actual_ms":None,"mode":self.mode}
        try:
            ntdll=ctypes.WinDLL("ntdll"); fn=ntdll.NtQueryTimerResolution
            fn.argtypes=[ctypes.POINTER(ctypes.c_ulong),ctypes.POINTER(ctypes.c_ulong),ctypes.POINTER(ctypes.c_ulong)]; fn.restype=ctypes.c_long
            mn=ctypes.c_ulong(0); mx=ctypes.c_ulong(0); cur=ctypes.c_ulong(0)
            status=int(fn(ctypes.byref(mn),ctypes.byref(mx),ctypes.byref(cur)))
            if status!=0: raise OSError(f"NtQueryTimerResolution status 0x{status & 0xffffffff:08X}")
            return {"supported":True,"active":self.active,"requested_ms":self.requested_ms,"actual_ms":self._to_ms(cur.value),"minimum_ms":self._to_ms(mn.value),"maximum_ms":self._to_ms(mx.value),"mode":self.mode}
        except Exception as e:
            return {"supported":False,"active":self.active,"requested_ms":self.requested_ms,"actual_ms":self.actual_ms,"mode":self.mode,"error":str(e)}
    def enable(self,period_ms: float=0.5) -> Tuple[bool,str]:
        if os.name!="nt": return False,"Disponível só no Windows."
        requested=max(0.5,min(15.625,float(period_ms)))
        if self.active: self.disable()
        desired=self._to_native(requested)
        try:
            ntdll=ctypes.WinDLL("ntdll"); fn=ntdll.NtSetTimerResolution
            fn.argtypes=[ctypes.c_ulong,ctypes.c_ubyte,ctypes.POINTER(ctypes.c_ulong)]; fn.restype=ctypes.c_long
            cur=ctypes.c_ulong(0); status=int(fn(desired,1,ctypes.byref(cur)))
            if status==0:
                self.active=True; self.requested_ms=requested; self._desired_100ns=desired; self.mode="NtSetTimerResolution"
                q=self.query(); self.actual_ms=q.get("actual_ms") or self._to_ms(cur.value)
                log(f"Timer requested={requested:.3f}ms actual={self.actual_ms}ms via NtSetTimerResolution")
                return True,f"Timer solicitado em {requested:.3f} ms; resolução atual verificada em {self.actual_ms:.3f} ms."
        except Exception as e: log(f"NtSetTimerResolution unavailable: {e}")
        rc=ctypes.windll.winmm.timeBeginPeriod(1)
        if rc==0:
            self.active=True; self.requested_ms=requested; self._winmm_period=1; self.mode="timeBeginPeriod"; self.actual_ms=self.query().get("actual_ms")
            return True,f"0,5 ms não foi aceito pela API nativa; fallback verificado de 1 ms ativado. Atual: {self.actual_ms if self.actual_ms is not None else 'indisponível'} ms."
        return False,f"Não foi possível ativar a resolução solicitada (timeBeginPeriod={rc})."
    def disable(self) -> Tuple[bool,str]:
        if os.name!="nt": return False,"Disponível só no Windows."
        if not self.active: return True,"O timer de 0,5 ms já estava desligado."
        ok=True
        try:
            if self.mode=="NtSetTimerResolution" and self._desired_100ns:
                ntdll=ctypes.WinDLL("ntdll"); fn=ntdll.NtSetTimerResolution
                fn.argtypes=[ctypes.c_ulong,ctypes.c_ubyte,ctypes.POINTER(ctypes.c_ulong)]; fn.restype=ctypes.c_long
                cur=ctypes.c_ulong(0); ok=int(fn(self._desired_100ns,0,ctypes.byref(cur)))==0
            elif self.mode=="timeBeginPeriod" and self._winmm_period:
                ok=ctypes.windll.winmm.timeEndPeriod(self._winmm_period)==0
        finally:
            self.active=False; self.actual_ms=None; self.mode="off"; self._desired_100ns=0; self._winmm_period=0
        log("Timer resolution session disabled.")
        return ok,"Timer session disabled and released." if ok else "Timer release returned an error."


TIMER_SESSION = TimerResolutionSession()


class AzorMemoryEngine:
    """Internal standby-memory manager; no external ISLC executable is required.

    It acts only under memory pressure or on explicit manual cleanup. The engine avoids
    continuous purge loops because Windows' standby cache is normally useful. Each cleanup
    is verified through available-memory readings and the native NT status code.
    """
    def __init__(self):
        self.active=False; self.cycles=0; self.last_cleanup=None; self.last_status=None
        self.last_error=None; self._thread=None; self._stop=threading.Event(); self.cooldown_sec=20.0
    def memory(self)->Dict[str,Any]:
        if os.name!='nt': return {'supported':False,'total_mb':None,'available_mb':None,'used_pct':None}
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_=[('dwLength',ctypes.c_ulong),('dwMemoryLoad',ctypes.c_ulong),('ullTotalPhys',ctypes.c_ulonglong),('ullAvailPhys',ctypes.c_ulonglong),('ullTotalPageFile',ctypes.c_ulonglong),('ullAvailPageFile',ctypes.c_ulonglong),('ullTotalVirtual',ctypes.c_ulonglong),('ullAvailVirtual',ctypes.c_ulonglong),('ullAvailExtendedVirtual',ctypes.c_ulonglong)]
        st=MEMORYSTATUSEX(); st.dwLength=ctypes.sizeof(st)
        try:
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                raise ctypes.WinError()
            return {'supported':True,'total_mb':round(st.ullTotalPhys/1048576,1),'available_mb':round(st.ullAvailPhys/1048576,1),'used_pct':int(st.dwMemoryLoad)}
        except Exception as e:
            return {'supported':False,'total_mb':None,'available_mb':None,'used_pct':None,'error':str(e)}
    def threshold_mb(self)->int:
        m=self.memory(); total=float(m.get('total_mb') or 0)
        if total<=0:return 1024
        # Keep a conservative reserve; don't purge normal healthy cache.
        return int(max(768,min(3072,total*0.09)))
    def _enable_privilege(self)->None:
        try:
            ntdll=ctypes.WinDLL('ntdll'); old=ctypes.c_ubyte(0)
            fn=ntdll.RtlAdjustPrivilege; fn.argtypes=[ctypes.c_ulong,ctypes.c_ubyte,ctypes.c_ubyte,ctypes.POINTER(ctypes.c_ubyte)]; fn.restype=ctypes.c_long
            fn(13,1,0,ctypes.byref(old))  # SeProfileSingleProcessPrivilege
        except Exception: pass
    def purge(self,reason='manual')->Tuple[bool,str]:
        if os.name!='nt': return False,'Windows only'
        before=self.memory(); self._enable_privilege()
        try:
            ntdll=ctypes.WinDLL('ntdll'); fn=ntdll.NtSetSystemInformation
            fn.argtypes=[ctypes.c_int,ctypes.c_void_p,ctypes.c_ulong]; fn.restype=ctypes.c_long
            command=ctypes.c_int(4) # MemoryPurgeStandbyList
            status=int(fn(80,ctypes.byref(command),ctypes.sizeof(command))) # SystemMemoryListInformation
            self.last_status=f'0x{status & 0xffffffff:08X}'
            if status!=0:
                self.last_error=f'NtSetSystemInformation {self.last_status}'
                log(f'AZOR Memory Engine purge failed reason={reason} status={self.last_status}')
                return False,f'Limpeza de standby não foi aceita pelo Windows ({self.last_status}). Execute o AZOR como administrador.'
            time.sleep(0.12); after=self.memory(); self.cycles+=1; self.last_cleanup=_ts(); self.last_error=None
            delta=None
            if before.get('available_mb') is not None and after.get('available_mb') is not None:
                delta=round(float(after['available_mb'])-float(before['available_mb']),1)
            log(f'AZOR Memory Engine purge verified reason={reason} before={before.get("available_mb")} after={after.get("available_mb")} delta={delta}')
            return True,(f'AZOR Memory Engine executou a limpeza interna. Memória disponível: {after.get("available_mb")} MB' + (f' ({delta:+.1f} MB).' if delta is not None else '.'))
        except Exception as e:
            self.last_error=str(e);log(f'AZOR Memory Engine purge exception: {e}');return False,f'Falha no Memory Engine: {e}'
    def _loop(self):
        last=0.0
        while not self._stop.wait(2.0):
            try:
                m=self.memory(); avail=m.get('available_mb'); threshold=self.threshold_mb(); now=time.time()
                if avail is not None and float(avail)<threshold and now-last>=self.cooldown_sec:
                    ok,_=self.purge('memory-pressure')
                    if ok:last=now
            except Exception as e:
                self.last_error=str(e);log(f'AZOR Memory Engine loop: {e}')
    def start(self)->Tuple[bool,str]:
        if os.name!='nt':return False,'Windows only'
        if self.active and self._thread and self._thread.is_alive():return True,'AZOR Memory Engine já está ativo.'
        self._stop.clear();self.active=True;self._thread=threading.Thread(target=self._loop,name='AzorMemoryEngine',daemon=True);self._thread.start()
        log('AZOR Memory Engine started (internal, adaptive).');return True,'AZOR Memory Engine interno ativado. Ele limpa standby apenas quando há pressão de memória.'
    def stop(self)->Tuple[bool,str]:
        self.active=False;self._stop.set();log('AZOR Memory Engine stopped.');return True,'AZOR Memory Engine desativado.'
    def status(self)->Dict[str,Any]:
        m=self.memory();running=bool(self.active and self._thread and self._thread.is_alive())
        return {'found':True,'internal':True,'name':'AZOR Memory Engine','path':'Interno ao AZOR • nenhum ISLC.exe necessário','running':running,'active':running,'cycles':self.cycles,'last_cleanup':self.last_cleanup,'threshold_mb':self.threshold_mb(),'cooldown_sec':self.cooldown_sec,'last_status':self.last_status,'last_error':self.last_error,**m}


MEMORY_ENGINE=AzorMemoryEngine()









# -------------------- App integration helpers --------------------

# Iniciar junto com o Windows.
#
# A build anterior recusava ligar isso ("versao limpa") - o que fazia sentido
# quando o app se copiava sozinho e criava VBS e tarefa agendada. Nada disso
# existe mais: aqui e UMA entrada em HKCU\...\Run, no perfil do proprio usuario,
# apontando para o launcher que ja esta na pasta. Nao exige administrador, nao
# se esconde, e o cliente remove pelo Gerenciador de Tarefas se quiser.
#
# Continua DESLIGADO por padrao. Ligar e decisao do usuario no interruptor das
# Configuracoes - o app nunca liga sozinho.
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "AzorOptimization"


def _startup_command() -> Optional[str]:
    """Comando que sobe o AZOR no login: direto no pythonw, sem janela de console
    e sem pedir permissão do Windows a cada inicialização (o .bat pediria)."""
    pyw = _runtime_pythonw()
    launcher = APP_ROOT / "azor_launcher.py"
    if pyw.exists() and launcher.exists():
        return f'"{pyw}" "{launcher}" --autostart'
    return None


def set_start_with_windows(enabled: bool) -> Tuple[bool, str]:
    """Liga/desliga a entrada de inicialização e CONFIRMA relendo o registro."""
    if winreg is None or os.name != "nt":
        return False, "Disponível só no Windows."
    try:
        if not enabled:
            reg_delete_value("HKCU", _RUN_KEY, _RUN_NAME)
            reg_delete_value("HKCU", _RUN_KEY, "AzorGuardian")
            still = reg_read("HKCU", _RUN_KEY, _RUN_NAME).get("exists")
            ok = not still
            log("Inicialização automática desligada." if ok else
                "Inicialização automática NÃO pode ser removida.",
                "SUCCESS" if ok else "ERROR")
            return ok, ("O AZOR não vai mais abrir junto com o Windows."
                        if ok else "A entrada de inicialização não pôde ser removida.")
        command = _startup_command()
        if not command:
            return False, ("O launcher do AZOR não foi encontrado nesta pasta, "
                           "então não dá para configurar a inicialização automática.")
        # reg_write nao devolve nada e escolhe REG_SZ sozinho para texto; quem diz
        # se deu certo e a releitura, que e a regra da casa para toda gravacao.
        reg_write("HKCU", _RUN_KEY, _RUN_NAME, command)
        back = reg_read("HKCU", _RUN_KEY, _RUN_NAME)
        ok = str(back.get("value") or "") == command
        log(f"Inicialização automática ligada: {command}" if ok else
            f"Inicialização automática falhou ao gravar: {back}",
            "SUCCESS" if ok else "ERROR")
        journal("start_with_windows", enabled=True, ok=ok)
        return ok, ("O AZOR vai abrir junto com o Windows, direto na bandeja."
                    if ok else "A entrada não foi confirmada na releitura do registro.")
    except Exception as e:
        log_error(f"set_start_with_windows: {e}")
        return False, str(e)


def get_start_with_windows() -> bool:
    """Le do registro, nunca de um JSON: quem manda aqui e o Windows."""
    if winreg is None or os.name != "nt":
        return False
    try:
        return bool(reg_read("HKCU", _RUN_KEY, _RUN_NAME).get("exists"))
    except Exception:
        return False

def _latest_fortnite_backup() -> Optional[Path]:
    backups = sorted(DATA_DIR.glob("GameUserSettings.backup.*.ini"), key=lambda p: p.stat().st_mtime, reverse=True)
    return backups[0] if backups else None


def apply_fortnite_competitive_preset() -> Tuple[bool, str]:
    """Edits only known keys that already exist in GameUserSettings.ini.

    This deliberately avoids forcing renderer-specific or undocumented keys.
    """
    fort = detect_fortnite()
    cfg = fort.get("config")
    if not cfg:
        return False, "O arquivo de configuração do Fortnite ainda não existe. Abra o jogo uma vez e feche."
    ok, backup_detail = backup_fortnite_config()
    if not ok:
        return False, backup_detail
    path = Path(cfg)
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = raw.splitlines()
    targets = {
        "bUseVSync": "False",
        "sg.ViewDistanceQuality": "0",
        "sg.AntiAliasingQuality": "0",
        "sg.ShadowQuality": "0",
        "sg.GlobalIlluminationQuality": "0",
        "sg.ReflectionQuality": "0",
        "sg.PostProcessQuality": "0",
        "sg.TextureQuality": "0",
        "sg.EffectsQuality": "0",
        "sg.FoliageQuality": "0",
        "sg.ShadingQuality": "0",
    }
    changed = []
    out_lines = []
    for line in lines:
        stripped = line.strip()
        replaced = False
        for key, value in targets.items():
            if stripped.startswith(key + "="):
                prefix = line[:len(line) - len(line.lstrip())]
                current = stripped.split("=", 1)[1]
                if current != value:
                    out_lines.append(f"{prefix}{key}={value}")
                    changed.append(key)
                else:
                    out_lines.append(line)
                replaced = True
                break
        if not replaced:
            out_lines.append(line)
    if not changed:
        return True, "O Fortnite já estava no preset competitivo. Nada precisou mudar."
    path.write_text("\n".join(out_lines) + ("\n" if raw.endswith(("\n", "\r")) else ""), encoding="utf-8")
    reread = path.read_text(encoding="utf-8", errors="replace").splitlines()
    observed = {}
    for line in reread:
        stripped = line.strip()
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key in targets:
            observed[key] = value
    mismatches = [key for key in changed if observed.get(key) != targets[key]]
    if mismatches:
        log("Fortnite preset verification failed for: " + ", ".join(mismatches))
        return False, f"A configuração foi gravada, mas {len(mismatches)} item(ns) não conferiram: {', '.join(mismatches)}. Use \"Voltar o meu\" se precisar."
    log(f"Fortnite competitive preset applied and verified for {len(changed)} existing keys: {', '.join(changed)}")
    return True, f"Preset competitivo aplicado e conferido ({len(changed)} ajuste(s)). Cópia do seu arquivo guardada: {Path(backup_detail).name}"



def set_fortnite_resolution_quality(percent: int) -> Tuple[bool, str]:
    """Set the existing sg.ResolutionQuality value and verify it after writing.

    The game must be closed so Fortnite cannot overwrite the file while Azor edits it.
    """
    fort=detect_fortnite(); cfg=fort.get("config")
    if not cfg: return False,"GameUserSettings.ini não foi encontrado. Abra o Fortnite pelo menos uma vez."
    # Avoid racing the game process and reporting a value that Fortnite immediately overwrites.
    try:
        if any("fortniteclient-win64-shipping" in x.lower() for x in _process_names()):
            return False,"Feche o Fortnite antes de alterar a Resolução 3D. O Azor não edita o arquivo enquanto o jogo está aberto."
    except Exception: pass
    pct=max(50,min(100,int(percent)))
    ok,detail=backup_fortnite_config()
    if not ok: return False,detail
    path=Path(cfg)
    raw=path.read_text(encoding="utf-8",errors="replace")
    pat=re.compile(r"^(\s*sg\.ResolutionQuality\s*=\s*)([0-9.]+)(\s*)$",re.I|re.M)
    if not pat.search(raw):
        return False,"A chave sg.ResolutionQuality não existe neste GameUserSettings.ini; o Azor não vai inventar uma chave que não encontrou."
    replacement=f"{pct:.6f}"
    updated=pat.sub(lambda m:m.group(1)+replacement+m.group(3),raw,count=1)
    try:
        path.write_text(updated,encoding="utf-8")
    except PermissionError:
        return False,"GameUserSettings.ini está somente leitura ou sem permissão. Remova Somente leitura e tente novamente."
    reread=path.read_text(encoding="utf-8",errors="replace")
    m=pat.search(reread)
    try: observed=float(m.group(2)) if m else None
    except Exception: observed=None
    verified=observed is not None and abs(observed-float(pct))<0.01
    log(f"Fortnite 3D resolution requested={pct} observed={observed} verified={verified}")
    return verified,(f"Resolução 3D gravada em {pct}% e relida com sucesso." if verified else f"O arquivo foi gravado, mas a releitura encontrou {observed if observed is not None else 'valor ausente'} em vez de {pct}%.")

def restore_latest_fortnite_config() -> Tuple[bool, str]:
    fort = detect_fortnite()
    cfg = fort.get("config")
    backup = _latest_fortnite_backup()
    if not cfg:
        return False, "O arquivo de configuração do Fortnite não foi encontrado."
    if not backup:
        return False, "No Azor Fortnite config backup exists."
    target = Path(cfg)
    shutil.copy2(backup, target)
    ok = hashlib.sha256(backup.read_bytes()).digest() == hashlib.sha256(target.read_bytes()).digest()
    log(f"Fortnite config restore from {backup.name} verified={ok}")
    return ok, (f"Fortnite config restored and verified from {backup.name}." if ok else "Fortnite restore copy finished, but byte-for-byte verification failed.")

# ==================== V3: Monitoring / Measure Sleep / external ISLC integration ====================
import csv
import math
import statistics
from collections import deque

_MON_LAST_NET = None
_MON_LAST_NET_TS = None
_MON_HW_CACHE = {"ts": 0.0, "data": {}}
_MON_HW_TTL_MIN = 8.0
_MON_HW_TTL_MAX = 600.0
_MON_HW_TTL = _MON_HW_TTL_MIN


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_uint32), ("dwHighDateTime", ctypes.c_uint32)]


def _filetime_int(ft: _FILETIME) -> int:
    return (int(ft.dwHighDateTime) << 32) | int(ft.dwLowDateTime)


from azor_sampling import CpuCounter, DemandSampler
_CPU_COUNTER = CpuCounter()

def _cpu_usage_windows() -> Optional[float]:
    if os.name != "nt": return None
    def read():
        idle = _FILETIME(); kernel = _FILETIME(); user = _FILETIME()
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        return (_filetime_int(idle), _filetime_int(kernel), _filetime_int(user))
    try:return _CPU_COUNTER.sample(read)
    except Exception as exc:
        log("CPU counter unavailable: " + str(exc))
        return None


class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _memory_windows() -> Dict[str, Any]:
    if os.name != "nt":
        return {"percent": None, "used_gb": None, "total_gb": None, "free_gb": None}
    try:
        st = _MEMORYSTATUSEX(); st.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            raise RuntimeError("GlobalMemoryStatusEx failed")
        total = st.ullTotalPhys / (1024 ** 3)
        free = st.ullAvailPhys / (1024 ** 3)
        return {
            "percent": round(float(st.dwMemoryLoad), 1),
            "used_gb": round(total - free, 2),
            "total_gb": round(total, 2),
            "free_gb": round(free, 2),
        }
    except Exception:
        return {"percent": None, "used_gb": None, "total_gb": None, "free_gb": None}


MAX_INTERFACE_NAME_LEN = 256
MAXLEN_PHYSADDR = 8
MAXLEN_IFDESCR = 256
IF_TYPE_SOFTWARE_LOOPBACK = 24


class _MIB_IFROW(ctypes.Structure):
    """Layout de MIB_IFROW (iphlpapi). Só os contadores de octeto interessam."""
    _fields_ = [
        ("wszName", ctypes.c_wchar * MAX_INTERFACE_NAME_LEN),
        ("dwIndex", ctypes.c_uint32),
        ("dwType", ctypes.c_uint32),
        ("dwMtu", ctypes.c_uint32),
        ("dwSpeed", ctypes.c_uint32),
        ("dwPhysAddrLen", ctypes.c_uint32),
        ("bPhysAddr", ctypes.c_ubyte * MAXLEN_PHYSADDR),
        ("dwAdminStatus", ctypes.c_uint32),
        ("dwOperStatus", ctypes.c_uint32),
        ("dwLastChange", ctypes.c_uint32),
        ("dwInOctets", ctypes.c_uint32),
        ("dwInUcastPkts", ctypes.c_uint32),
        ("dwInNUcastPkts", ctypes.c_uint32),
        ("dwInDiscards", ctypes.c_uint32),
        ("dwInErrors", ctypes.c_uint32),
        ("dwInUnknownProtos", ctypes.c_uint32),
        ("dwOutOctets", ctypes.c_uint32),
        ("dwOutUcastPkts", ctypes.c_uint32),
        ("dwOutNUcastPkts", ctypes.c_uint32),
        ("dwOutDiscards", ctypes.c_uint32),
        ("dwOutErrors", ctypes.c_uint32),
        ("dwOutQLen", ctypes.c_uint32),
        ("dwDescrLen", ctypes.c_uint32),
        ("bDescr", ctypes.c_ubyte * MAXLEN_IFDESCR),
    ]


_NET_API_OK: Optional[bool] = None


def _network_totals_api() -> Optional[Tuple[int, int]]:
    """Bytes recebidos/enviados lidos direto do Windows, sem abrir processo.

    GetIfTable devolve os contadores por interface. A loopback fica de fora
    porque tráfego local não é rede do usuário.
    """
    if os.name != "nt":
        return None
    try:
        iphlpapi = ctypes.windll.iphlpapi
        size = ctypes.c_ulong(0)
        # Primeira chamada só para descobrir o tamanho do buffer.
        iphlpapi.GetIfTable(None, ctypes.byref(size), False)
        if not size.value:
            return None
        buf = ctypes.create_string_buffer(size.value)
        if iphlpapi.GetIfTable(buf, ctypes.byref(size), False) != 0:
            return None
        count = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint32)).contents.value
        if count <= 0 or count > 4096:
            return None
        rows = ctypes.cast(ctypes.byref(buf, 4), ctypes.POINTER(_MIB_IFROW))
        rx = tx = 0
        for i in range(count):
            row = rows[i]
            if row.dwType == IF_TYPE_SOFTWARE_LOOPBACK:
                continue
            rx += int(row.dwInOctets)
            tx += int(row.dwOutOctets)
        return rx, tx
    except Exception as e:
        log(f"GetIfTable failed: {e}")
        return None


def _network_totals_netstat() -> Optional[Tuple[int, int]]:
    if os.name != "nt":
        return None
    try:
        p = run_hidden(["netstat", "-e"], timeout=5)
        text = p.stdout or ""
        candidates = []
        for line in text.splitlines():
            vals = [int(x.replace(',', '').replace('.', '')) for x in re.findall(r"\b\d[\d,.]*\b", line)]
            if len(vals) >= 2:
                candidates.append((vals[0], vals[1]))
        if not candidates:
            return None
        # The bytes received/sent row is normally the largest pair in netstat -e.
        return max(candidates, key=lambda x: x[0] + x[1])
    except Exception:
        return None


def _network_totals_windows() -> Optional[Tuple[int, int]]:
    """Totais de rede, preferindo a API e caindo para netstat se ela discordar.

    Antes isso abria um netstat.exe por amostra - 38 processos por minuto só
    para ler dois números que o Windows entrega por chamada de API. A primeira
    leitura confere os dois caminhos: se a API não bater com o netstat na mesma
    ordem de grandeza, ela é descartada de vez nesta sessão e o comportamento
    volta a ser exatamente o de antes.
    """
    global _NET_API_OK
    if os.name != "nt":
        return None
    if _NET_API_OK is None:
        api = _network_totals_api()
        shell = _network_totals_netstat()
        if api and shell and shell[0] > 0:
            ratio = api[0] / float(shell[0])
            _NET_API_OK = 0.5 <= ratio <= 1.5
            log(f"network counters: api={api} netstat={shell} api_trusted={_NET_API_OK}")
        else:
            _NET_API_OK = bool(api) and not shell
        return api if _NET_API_OK else shell
    if _NET_API_OK:
        return _network_totals_api()
    return _network_totals_netstat()


def _network_rate_windows() -> Dict[str, Optional[float]]:
    global _MON_LAST_NET, _MON_LAST_NET_TS
    cur = _network_totals_windows(); now = time.perf_counter()
    if cur is None:
        return {"down_mbps": None, "up_mbps": None}
    if _MON_LAST_NET is None or _MON_LAST_NET_TS is None:
        _MON_LAST_NET, _MON_LAST_NET_TS = cur, now
        return {"down_mbps": 0.0, "up_mbps": 0.0}
    dt = max(0.05, now - _MON_LAST_NET_TS)
    rx = max(0, cur[0] - _MON_LAST_NET[0])
    tx = max(0, cur[1] - _MON_LAST_NET[1])
    _MON_LAST_NET, _MON_LAST_NET_TS = cur, now
    return {"down_mbps": round(rx * 8 / dt / 1_000_000, 2), "up_mbps": round(tx * 8 / dt / 1_000_000, 2)}


NVIDIA_QUERY = ("name,utilization.gpu,temperature.gpu,memory.used,"
                "memory.total,clocks.current.graphics")
_NVIDIA_EXE_CACHED = False
_NVIDIA_EXE: Optional[str] = None


def _nvidia_exe() -> Optional[str]:
    """shutil.which walks the whole PATH; the answer does not change at runtime."""
    global _NVIDIA_EXE_CACHED, _NVIDIA_EXE
    if not _NVIDIA_EXE_CACHED:
        _NVIDIA_EXE = shutil.which("nvidia-smi")
        _NVIDIA_EXE_CACHED = True
    return _NVIDIA_EXE


def _parse_nvidia_row(line: str) -> Optional[Dict[str, Any]]:
    line = (line or "").strip()
    if not line:
        return None
    try:
        vals = [x.strip() for x in next(csv.reader([line]))]
        if len(vals) < 6:
            return None

        def num(v: str) -> Optional[float]:
            return None if v in ("N/A", "[Not Supported]", "") else float(v)

        return {
            "available": True, "vendor": "NVIDIA", "name": vals[0],
            "usage": num(vals[1]), "temp_c": num(vals[2]),
            "vram_used_mb": num(vals[3]), "vram_total_mb": num(vals[4]),
            "clock_mhz": num(vals[5]),
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Job object: filho que morre junto com o AZOR
#
# O feed do nvidia-smi e um processo de longa duracao. Encerrar o servidor pelo
# caminho normal o termina no finally do main() - mas o launcher do AZOR mata os
# backends antigos com Stop-Process -Force, e ai o finally nunca roda. Cada
# abertura do app deixava um nvidia-smi orfao rodando para sempre (verificado:
# quatro deles, todos com o pai morto). Um job object com KILL_ON_JOB_CLOSE
# resolve isso no nivel do Windows: quando o processo do AZOR morre, de qualquer
# jeito, o handle do job fecha e o Windows encerra quem estiver dentro dele.
# ---------------------------------------------------------------------------
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JobObjectExtendedLimitInformation = 9


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [("ReadOperationCount", ctypes.c_uint64), ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64), ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64), ("OtherTransferCount", ctypes.c_uint64)]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


_CHILD_JOB = None
_CHILD_JOB_TRIED = False


def _child_job_handle():
    """Job que mata os filhos quando o processo do AZOR morre, do jeito que for."""
    global _CHILD_JOB, _CHILD_JOB_TRIED
    if _CHILD_JOB_TRIED:
        return _CHILD_JOB
    _CHILD_JOB_TRIED = True
    if os.name != "nt":
        return None
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        handle = kernel32.CreateJobObjectW(None, None)
        if not handle:
            return None
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = kernel32.SetInformationJobObject(
            ctypes.c_void_p(handle), JobObjectExtendedLimitInformation,
            ctypes.byref(info), ctypes.sizeof(info))
        if not ok:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
            return None
        _CHILD_JOB = handle
    except Exception as e:
        log(f"job object unavailable: {e}")
        _CHILD_JOB = None
    return _CHILD_JOB


def _adopt_child(proc: subprocess.Popen) -> bool:
    """Coloca o filho no job. False quando o Windows não deixou."""
    handle = _child_job_handle()
    if not handle or os.name != "nt":
        return False
    try:
        child = int(proc._handle)  # type: ignore[attr-defined]
        return bool(ctypes.windll.kernel32.AssignProcessToJobObject(
            ctypes.c_void_p(handle), ctypes.c_void_p(child)))
    except Exception as e:
        log(f"could not adopt child into job: {e}")
        return False


class _NvidiaFeed:
    """Keeps a single `nvidia-smi -lms` alive and reads its lines.

    Spawning nvidia-smi once per sample cost ~50 ms of CPU every 1,5 s - about
    3,4 % of one core, permanently, on a machine the app is supposed to be
    freeing up. One process that emits a line per interval pays that once.
    Any failure falls back to the original one-shot call.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None
        self._latest: Optional[Dict[str, Any]] = None
        self._latest_at = 0.0
        self._failed_at = 0.0

    def _spawn(self, interval_ms: int) -> None:
        """Starts the feed at most once.

        The whole check-and-create runs under the lock: two threads asking for a
        GPU reading at the same instant used to start two nvidia-smi processes,
        and only the last one was ever terminated - the other stayed alive for
        the rest of the session.
        """
        exe = _nvidia_exe()
        if not exe:
            return
        proc = None
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return
            if time.monotonic() - self._failed_at < 60:
                return
            try:
                kwargs: Dict[str, Any] = {
                    "stdout": subprocess.PIPE, "stderr": subprocess.DEVNULL,
                    "stdin": subprocess.DEVNULL, "text": True,
                    "encoding": "utf-8", "errors": "replace", "bufsize": 1,
                }
                if os.name == "nt":
                    kwargs["creationflags"] = CREATE_NO_WINDOW
                proc = subprocess.Popen([
                    exe, "--query-gpu=" + NVIDIA_QUERY, "--format=csv,noheader,nounits",
                    "-lms", str(max(400, int(interval_ms))),
                ], **kwargs)
                if not _adopt_child(proc):
                    # Sem a garantia de que ele morre junto, um processo de longa
                    # duracao nao vale o risco de virar orfao: encerra e volta
                    # para a chamada avulsa desta sessao.
                    try:
                        proc.terminate()
                    except Exception:
                        pass
                    self._failed_at = time.monotonic()
                    self._proc = None
                    log("nvidia-smi feed disabled: job object unavailable")
                    return
                self._proc = proc
            except Exception as e:
                self._failed_at = time.monotonic()
                self._proc = None
                log("nvidia-smi feed failed to start: " + str(e))
                return
        self._reader = threading.Thread(target=self._pump, args=(proc,), name="azor-nvidia-feed", daemon=True)
        self._reader.start()

    def _pump(self, proc: subprocess.Popen) -> None:
        if not proc.stdout:
            return
        try:
            for line in proc.stdout:
                row = _parse_nvidia_row(line)
                if row:
                    with self._lock:
                        self._latest = row
                        self._latest_at = time.monotonic()
        except Exception:
            pass
        finally:
            with self._lock:
                if self._proc is proc:
                    self._proc = None

    def read(self, interval_ms: int = 1500) -> Dict[str, Any]:
        if not _nvidia_exe():
            return {"available": False, "vendor": None}
        with self._lock:
            alive = self._proc is not None and self._proc.poll() is None
            latest = self._latest
            age = time.monotonic() - self._latest_at if latest else 999.0
        if not alive:
            self._spawn(interval_ms)  # idempotent: re-checks under the lock
        if latest is not None and age < max(6.0, interval_ms / 250.0):
            return dict(latest)
        return _nvidia_snapshot_once()

    def stop(self) -> None:
        with self._lock:
            proc, self._proc = self._proc, None
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass


def sweep_orphan_gpu_feeds() -> int:
    """Encerra feeds de GPU deixados por execucoes anteriores que morreram a forca.

    So mata o que casa com a linha de comando exata do AZOR e cujo processo pai
    já não existe. Um nvidia-smi aberto pelo próprio usuário não e tocado.
    """
    if os.name != "nt":
        return 0
    script = (
        "$mine = Get-CimInstance Win32_Process -Filter \"Name='nvidia-smi.exe'\" | "
        "  Where-Object { $_.CommandLine -like '*" + NVIDIA_QUERY + "*' -and $_.CommandLine -like '*-lms*' }; "
        "$killed = 0; "
        "foreach($p in $mine){ "
        "  if(-not (Get-Process -Id $p.ParentProcessId -ErrorAction SilentlyContinue)){ "
        "    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue; $killed++ } } "
        "$killed"
    )
    try:
        out = powershell(script, timeout=15)
        count = int(str(out).strip() or 0)
        if count:
            log(f"swept {count} orphan nvidia-smi feed(s) from earlier runs")
        return count
    except Exception as e:
        log(f"orphan sweep failed: {e}")
        return 0


NVIDIA_FEED = _NvidiaFeed()


def _nvidia_snapshot_once() -> Dict[str, Any]:
    exe = _nvidia_exe()
    if not exe:
        return {"available": False, "vendor": None}
    try:
        p = run_hidden([exe, "--query-gpu=" + NVIDIA_QUERY, "--format=csv,noheader,nounits"], timeout=5)
        if p.returncode != 0 or not (p.stdout or "").strip():
            return {"available": False, "vendor": "NVIDIA"}
        row = _parse_nvidia_row((p.stdout or "").splitlines()[0])
        return row or {"available": False, "vendor": "NVIDIA"}
    except Exception as e:
        log("nvidia-smi monitor failed: " + str(e))
        return {"available": False, "vendor": "NVIDIA"}


def _nvidia_snapshot() -> Dict[str, Any]:
    return NVIDIA_FEED.read()


def _hardware_monitor_snapshot() -> Dict[str, Any]:
    """Reads optional LibreHardwareMonitor/OpenHardwareMonitor WMI providers if already available.
    No fake fallback temperatures are emitted.

    Both providers are probed inside a SINGLE powershell.exe, and when neither is
    installed the probe backs off instead of paying ~1.8 s of CPU every 8 s
    forever. On a PC without LHM/OHM the old loop spent roughly 13 s of CPU per
    minute discovering the same absence over and over.
    """
    global _MON_HW_CACHE, _MON_HW_TTL
    now = time.time()
    if now - float(_MON_HW_CACHE.get("ts", 0)) < _MON_HW_TTL:
        return dict(_MON_HW_CACHE.get("data") or {})
    result: Dict[str, Any] = {"cpu_temp_c": None, "fans": [], "cpu_clock_mhz": None, "source": None}
    if os.name != "nt":
        _MON_HW_CACHE = {"ts": now, "data": result}
        _MON_HW_TTL = _MON_HW_TTL_MAX
        return result
    script = (
        "$out=$null; "
        "foreach($ns in @('root/LibreHardwareMonitor','root/OpenHardwareMonitor')){ "
        "  try{ $rows = Get-CimInstance -Namespace $ns -ClassName Sensor -ErrorAction Stop | "
        "        Select-Object Name,SensorType,Value; "
        "       if($rows){ $out=[pscustomobject]@{source=$ns;sensors=@($rows)}; break } }catch{} } "
        "$out"
    )
    data = None
    try:
        data = powershell_json(script, timeout=10)
    except Exception:
        data = None
    sensors = (data or {}).get("sensors") if isinstance(data, dict) else None
    if sensors:
        if isinstance(sensors, dict):
            sensors = [sensors]
        temps = []; fans = []; clocks = []
        for sensor in sensors:
            if not isinstance(sensor, dict):
                continue
            typ = str(sensor.get("SensorType") or "").lower()
            name = str(sensor.get("Name") or "")
            try:
                val = float(sensor.get("Value"))
            except Exception:
                continue
            low = name.lower()
            if typ == "temperature" and any(k in low for k in ["cpu package", "cpu", "core max", "package"]):
                temps.append(val)
            elif typ == "fan" and val >= 0:
                fans.append({"name": name, "rpm": round(val)})
            elif typ == "clock" and "cpu" in low:
                clocks.append(val)
        result["cpu_temp_c"] = round(max(temps), 1) if temps else None
        result["fans"] = fans[:6]
        result["cpu_clock_mhz"] = round(max(clocks), 0) if clocks else None
        source = str((data or {}).get("source") or "")
        result["source"] = "LibreHardwareMonitor" if "Libre" in source else ("OpenHardwareMonitor" if source else None)

    if result["source"]:
        _MON_HW_TTL = _MON_HW_TTL_MIN
    else:
        # Nothing installed: keep answering "no sensor" from cache and retry rarely.
        _MON_HW_TTL = min(_MON_HW_TTL_MAX, max(_MON_HW_TTL, _MON_HW_TTL_MIN) * 4)
    _MON_HW_CACHE = {"ts": now, "data": result}
    return result


def _top_processes_memory() -> List[Dict[str, Any]]:
    rows = []
    for row in _tasklist_rows():
        if len(row) < 5:
            continue
        digits = re.sub(r"\D", "", row[4])
        if not digits:
            continue
        rows.append({"name": row[0], "pid": row[1], "memory_mb": round(int(digits) / 1024, 1)})
    rows.sort(key=lambda x: x["memory_mb"], reverse=True)
    return rows[:8]


def _collect_monitor_sample() -> Dict[str, Any]:
    """One reading of the live gauges. Runs on the sampler thread only."""
    mem=_memory_windows()
    net=_network_rate_windows()
    gpu=_nvidia_snapshot()
    hw=_hardware_monitor_snapshot()
    try:
        drive=os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/"
        du=shutil.disk_usage(drive)
        disk={"percent":round(du.used*100/du.total,1),"used_gb":round(du.used/(1024**3),1),"total_gb":round(du.total/(1024**3),1)}
    except Exception:
        disk={"percent":None,"used_gb":None,"total_gb":None}
    return {
        "ts": time.time(),
        "cpu": {"usage": _cpu_usage_windows(), "temp_c": hw.get("cpu_temp_c"), "clock_mhz": hw.get("cpu_clock_mhz")},
        "gpu": gpu,
        "ram": mem,
        "disk": disk,
        "network": net,
        "fans": hw.get("fans") or [],
        "sensor_source": hw.get("source"),
        "processes": _top_processes_memory(),
    }


class _MonitorSampler(DemandSampler):
    def __init__(self):
        super().__init__(_collect_monitor_sample, NVIDIA_FEED.stop,
                         lambda message: log("monitor sampler error: " + message))
    def request(self, interval=None):
        result=super().request(interval)
        for key in ("cpu","gpu","ram","disk","network"):
            result.setdefault(key,{})
        result.setdefault("fans",[]);result.setdefault("processes",[])
        return result


MONITOR_SAMPLER = _MonitorSampler()


def monitor_snapshot(interval: Optional[float] = None) -> Dict[str, Any]:
    """Latest live-gauge sample. Never blocks on a process spawn after the first.

    Com o jogo em primeiro plano o amostrador para inteiro. Ele mantem um
    `nvidia-smi -lms` vivo e le contadores de CPU e memória em intervalo curto;
    e trabalho util com o cliente olhando os medidores, e puro desperdicio com a
    janela escondida atrás da partida. A tela recebe a última amostra marcada
    como pausada, e volta a atualizar sozinha quando o jogo sai da frente.
    """
    if game_focused().get("focused"):
        MONITOR_SAMPLER.stop()
        last = dict(getattr(MONITOR_SAMPLER, "_sample", None) or {})
        last.update({"paused": True, "paused_reason": "jogo em primeiro plano"})
        return last
    return MONITOR_SAMPLER.request(interval)







# ==================== V4 ULTIMATE: verified optimization + guardian + maintenance + BIOS guide ====================
import hashlib
import threading

AZOR_POWER_NAME = "AZOR DESEMPENHO"
AZOR_POWER_DESCRIPTION = "Plano gamer baseado no Alto desempenho, com CPU máxima, boost agressivo e preferência de desempenho; permite repouso sem carga."

# Extend restore coverage with V4 user-level Windows settings.
for _item in [
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SubscribedContent-338388Enabled"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SubscribedContent-353694Enabled"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager", "SystemPaneSuggestionsEnabled"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize", "EnableTransparency"),
    ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced", "TaskbarDa"),
]:
    if _item not in TRACKED_REGISTRY:
        TRACKED_REGISTRY.append(_item)


def _safe_json_read(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"Could not read {path.name}: {e}")
    return default


# ---------------------------------------------------------------------------
# Gravacao de JSON: por que o nome do arquivo temporario precisa ser unico
# ---------------------------------------------------------------------------
#
# A versao anterior escrevia sempre em "<arquivo>.tmp" - um nome FIXO. Quem
# grava esses arquivos nao e um so:
#
#   - o servidor e um ThreadingHTTPServer, entao duas requisicoes /api/summary
#     que se cruzam rodam em threads diferentes e chamam hardware_profile() ao
#     mesmo tempo;
#   - o agente Guardian e um PROCESSO separado e chama as mesmas funcoes.
#
# Dois escritores no mesmo .tmp, no Windows, e falha garantida: um abre o
# arquivo, o outro recebe WinError 32 ("ja esta sendo usado por outro
# processo"), ou o replace de um roda enquanto o outro ainda tem o handle aberto
# e vira WinError 5. No log do cliente isso apareceu como
# "GET /api/summary error: [WinError 32] ... hardware_profile.json.tmp" - ou
# seja, a tela inicial inteira caia por causa de um arquivo de cache.
#
# Windows tambem nao tem o rename-sobre-arquivo-aberto do POSIX: mesmo com o
# temporario unico, o replace final pode esbarrar em alguem LENDO o destino.
# Por isso ele e tentado algumas vezes antes de desistir.

_JSON_WRITE_SEQ = itertools.count()
_JSON_WRITE_LOCK = threading.Lock()


def _safe_json_write(path: Path, value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2, default=str)
    # Unico por processo, por thread e por chamada: dois escritores nunca
    # disputam o mesmo temporario.
    tmp = path.with_name(
        f"{path.name}.{os.getpid()}.{threading.get_ident()}."
        f"{next(_JSON_WRITE_SEQ)}.tmp")
    try:
        tmp.write_text(payload, encoding="utf-8")
        last: Optional[Exception] = None
        # O temporario unico resolve escritor-contra-escritor. Sobra
        # escritor-contra-LEITOR: no Windows, um replace precisa de acesso DELETE
        # ao destino, e quem esta lendo o arquivo nesse instante segura isso.
        # A janela e de milissegundos, entao repetir resolve - com orcamento
        # suficiente (~1,1 s no pior caso) para nao desistir cedo demais.
        for attempt in range(10):
            try:
                # Serializa os escritores DESTE processo; o de fora ainda pode
                # cruzar, e para esse caso existe a repeticao.
                with _JSON_WRITE_LOCK:
                    tmp.replace(path)
                return
            except (PermissionError, OSError) as exc:
                last = exc
                time.sleep(0.02 * (attempt + 1))
        raise last if last else OSError(f"replace falhou: {path}")
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass


def _cache_json_write(path: Path, value: Any) -> bool:
    """Grava um arquivo de CACHE. Falhar aqui nunca derruba a requisicao.

    A diferença entre este e o `_safe_json_write` não e técnica, e de contrato.
    Perder settings.json ou desired_state.json quebra a promessa de "aplicou =
    fica", então esses tem de estourar e ser tratados. Já o hardware_profile.json
    e so um valor derivado que pode ser recalculado a qualquer momento - e mesmo
    assim ele foi capaz de derrubar a tela inicial inteira, porque a excecao
    subia até o handler do /api/summary. Cache que não grava e um cache frio,
    não um erro de aplicação.
    """
    try:
        _safe_json_write(path, value)
        return True
    except Exception as exc:
        log(f"Cache não pode ser gravado ({path.name}): {exc}. Seguindo com o valor em memória.")
        return False


def _sweep_stale_tmp(older_than_s: float = 300.0) -> int:
    """Remove temporarios orfaos de gravacoes que morreram no meio."""
    removed = 0
    try:
        cutoff = time.time() - older_than_s
        for leftover in DATA_DIR.glob("*.tmp"):
            try:
                if leftover.stat().st_mtime < cutoff:
                    leftover.unlink()
                    removed += 1
            except Exception:
                continue
    except Exception:
        pass
    return removed


def load_settings() -> Dict[str, Any]:
    defaults = {
        # Modo do BOOST e da reaplicação no login: "maximo" (Recomendado) ou "agressivo" (Extremo).
        "performance_mode": "maximo",
        # Modo Turbo: timer 0,5 ms + prioridade do jogo + motor de memória, vivos com o AZOR na bandeja.
        "turbo": False,
        # Quem faz live: preserva overlay (sem tela cheia exclusiva) e a reserva de CPU do encoder.
        "streamer": False,
        "start_with_windows": False,
        "start_minimized": False,
        # Mostra fonte, métrica e custo técnico de cada tweak (para o técnico).
        "technician": False,
        "reduce_motion": False,
        "customer_name": "",
        # Jogos que o AZOR reconhece em primeiro plano (pausa o monitor de periféricos).
        "configured_games": ["FortniteClient-Win64-Shipping.exe", "VALORANT-Win64-Shipping.exe", "cs2.exe",
                             "r5apex.exe", "r5apex_dx12.exe", "RobloxPlayerBeta.exe", "League of Legends.exe"],
    }
    data = _safe_json_read(SETTINGS_FILE, {})
    if isinstance(data, dict):
        defaults.update(data)
    if defaults.get("performance_mode") not in ("maximo", "agressivo"):
        defaults["performance_mode"] = "maximo"
    return defaults


def save_settings(settings: Dict[str, Any]) -> None:
    _safe_json_write(SETTINGS_FILE, settings)
    log("Settings saved and normalized.")








def _extract_vid_pid(dev_id: Any) -> Dict[str, Optional[str]]:
    txt = str(dev_id or "")
    m = re.search(r"VID_([0-9A-F]{4}).*PID_([0-9A-F]{4})", txt, re.I)
    if not m:
        return {"vid": None, "pid": None}
    return {"vid": m.group(1).upper(), "pid": m.group(2).upper()}


def _infer_connection(dev: Dict[str, Any]) -> str:
    joined = (str(dev.get("id") or "") + " " + str(dev.get("name") or "")).lower()
    if "bth" in joined or "bluetooth" in joined:
        return "Bluetooth"
    if "wireless" in joined or "2.4" in joined or "dongle" in joined:
        return "Dongle / Wireless"
    if "usb" in joined or "vid_" in joined:
        return "USB"
    return "Windows HID"




def set_enhanced_pointer_precision(enabled: bool) -> Tuple[bool, str]:
    if os.name != "nt" or winreg is None:
        return False, "Disponível só no Windows."
    capture_restore_point()
    try:
        wanted = ("1", "6", "10") if enabled else ("0", "0", "0")
        reg_write("HKCU", r"Control Panel\Mouse", "MouseSpeed", wanted[0], winreg.REG_SZ)
        reg_write("HKCU", r"Control Panel\Mouse", "MouseThreshold1", wanted[1], winreg.REG_SZ)
        reg_write("HKCU", r"Control Panel\Mouse", "MouseThreshold2", wanted[2], winreg.REG_SZ)
        _broadcast_setting("Control Panel\\Mouse")
        got = tuple(str(reg_read("HKCU", r"Control Panel\Mouse", n).get("value")) for n in ("MouseSpeed", "MouseThreshold1", "MouseThreshold2"))
        ok = got == wanted
        return ok, (f"Enhanced Pointer Precision {'enabled' if enabled else 'disabled'}; all three Windows mouse values were re-read and verified." if ok else f"Mouse acceleration verification mismatch: expected={wanted}, got={got}.")
    except Exception as e:
        return False, str(e)




def set_usb_selective_suspend_disabled(disabled: bool = True) -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Disponível só no Windows."
    capture_restore_point()
    before = get_usb_selective_suspend_state()
    wanted = 0 if disabled else 1
    battery = has_battery()
    commands = [["powercfg", "/SETACVALUEINDEX", "SCHEME_CURRENT", USB_SUBGROUP_GUID, USB_SELECTIVE_SUSPEND_GUID, str(wanted)]]
    if not battery:
        commands.append(["powercfg", "/SETDCVALUEINDEX", "SCHEME_CURRENT", USB_SUBGROUP_GUID, USB_SELECTIVE_SUSPEND_GUID, str(wanted)])
    commands.append(["powercfg", "/SETACTIVE", "SCHEME_CURRENT"])
    try:
        for cmd in commands:
            p = run_hidden(cmd, timeout=8)
            if p.returncode != 0:
                return False, (p.stderr or p.stdout or "powercfg failed").strip()
        after = get_usb_selective_suspend_state()
        if not after:
            return False, "O pedido de energia USB foi feito, mas o Windows não mostrou o estado para conferir."
        expected_dc = before.get("dc") if battery and before else wanted
        ok = after.get("ac") == wanted and (expected_dc is None or after.get("dc") == expected_dc)
        if ok:
            scope = "AC only; battery/DC preserved" if battery else "AC and DC"
            return True, f"USB selective suspend {'disabled' if disabled else 'enabled'} and verified ({scope})."
        return False, f"USB selective suspend verification mismatch: before={before}, after={after}, requested={wanted}."
    except Exception as e:
        return False, str(e)

def set_keyboard_repeat_verified(delay: int, speed: int) -> Tuple[bool, str]:
    if os.name != "nt" or winreg is None:
        return False, "Disponível só no Windows."
    capture_restore_point()
    try:
        d = str(max(0, min(3, int(delay))))
        s = str(max(0, min(31, int(speed))))
        reg_write("HKCU", r"Control Panel\Keyboard", "KeyboardDelay", d, winreg.REG_SZ)
        reg_write("HKCU", r"Control Panel\Keyboard", "KeyboardSpeed", s, winreg.REG_SZ)
        _broadcast_setting("Control Panel\\Keyboard")
        got_d = str(reg_read("HKCU", r"Control Panel\Keyboard", "KeyboardDelay").get("value"))
        got_s = str(reg_read("HKCU", r"Control Panel\Keyboard", "KeyboardSpeed").get("value"))
        ok = got_d == d and got_s == s
        return ok, (f"Keyboard repeat updated and re-read (delay={d}, speed={s})." if ok else f"Keyboard repeat verification mismatch: wanted=({d},{s}) got=({got_d},{got_s}).")
    except Exception as e:
        return False, str(e)






def list_power_schemes() -> List[Dict[str, Any]]:
    if os.name != "nt": return []
    try:
        p = run_hidden(["powercfg", "/list"], timeout=8)
        text = (p.stdout or "") + "\n" + (p.stderr or "")
        rows=[]
        for line in text.splitlines():
            m=re.search(r"([0-9a-fA-F-]{36})\s*\((.*?)\)\s*(\*)?", line)
            if m:
                rows.append({"guid":m.group(1).lower(),"name":m.group(2).strip(),"active":bool(m.group(3))})
        return rows
    except Exception as e:
        log(f"Power scheme list failed: {e}")
        return []


def _scheme_by_profile(profile: str) -> Optional[Dict[str, Any]]:
    rows=list_power_schemes(); low=str(profile or '').lower().strip()
    if low in ("azor","azor_fps_boost","azor fps boost","fps_boost","fps boost"):
        for x in rows:
            if str(x.get("name") or "").strip().casefold() == AZOR_POWER_NAME.casefold():
                return x
    if low in ("high","high_performance","performance"):
        for x in rows:
            if x["guid"] == "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c": return x
        for x in rows:
            if "high performance" in x["name"].lower() or "alto desempenho" in x["name"].lower(): return x
    if low in ("ultimate","ultimate_performance","max","maximum","max_performance"):
        for x in rows:
            if "ultimate" in x["name"].lower() or "desempenho máximo" in x["name"].lower() or "desempenho maximo" in x["name"].lower(): return x
    if re.fullmatch(r"[0-9a-fA-F-]{36}", low):
        for x in rows:
            if x["guid"] == low: return x
    return None




def ensure_azor_fps_boost_scheme() -> Tuple[bool, Optional[str], str]:
    """Create the explicitly requested performance scheme without changing its source."""
    if os.name != "nt": return False,None,"Disponível só no Windows."
    found=_scheme_by_profile("azor_fps_boost")
    if found:
        return True,str(found["guid"]).lower(),f"{AZOR_POWER_NAME} already exists."
    source="8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
    if not any(str(row.get("guid","")).lower()==source for row in list_power_schemes()):
        return False,None,"Plano Alto desempenho indisponível. Selecione um plano existente em Energia; não será usado Equilibrado como substituto."
    p=run_hidden(["powercfg","/duplicatescheme",source],timeout=10)
    text=(p.stdout or "")+"\n"+(p.stderr or "")
    m=re.search(r"([0-9a-fA-F-]{36})",text)
    if p.returncode != 0 or not m:
        return False,None,(text.strip() or f"Não foi possível criar {AZOR_POWER_NAME} a partir de Alto desempenho.")
    guid=m.group(1).lower()
    rn=run_hidden(["powercfg","/changename",guid,AZOR_POWER_NAME,AZOR_POWER_DESCRIPTION],timeout=8)
    if rn.returncode != 0:
        return False,None,(rn.stderr or rn.stdout or f"Could not rename the AZOR power plan.").strip()
    found=_scheme_by_profile("azor_fps_boost")
    if not found or str(found.get("guid") or "").lower()!=guid:
        return False,None,f"{AZOR_POWER_NAME} was created but its name/GUID could not be verified."
    log(f"{AZOR_POWER_NAME} scheme created: {guid}")
    return True,guid,f"{AZOR_POWER_NAME} criado a partir de Alto desempenho e verificado."






def _powercfg_index_for_scheme(scheme: str, subgroup: str, setting: str, which: str="ac") -> Optional[int]:
    if os.name != "nt": return None
    try:
        # /QH, nao /Q: EPP, modo de boost, politica de resfriamento e parking
        # vem ocultos no Windows, e com /Q o powercfg so imprime o cabecalho do
        # plano. A escrita funcionava; era a releitura que voltava vazia.
        p=run_hidden(["powercfg","/QH",str(scheme),subgroup,setting],timeout=8)
        if p.returncode != 0: return None
        vals=re.findall(r"0x([0-9a-fA-F]{8})",(p.stdout or "")+"\n"+(p.stderr or ""))
        if len(vals)<2: return None
        return int(vals[-2 if str(which).lower()=="ac" else -1],16)
    except Exception as e:
        log(f"Power index query failed {subgroup}/{setting}: {e}")
        return None




def _set_powercfg_value_verified(scheme: str, subgroup: str, setting: str, value: int, label: str, which: str="ac") -> Tuple[bool,str]:
    if os.name != "nt": return False,"Disponível só no Windows."
    flag="/SETACVALUEINDEX" if str(which).lower()=="ac" else "/SETDCVALUEINDEX"
    p=run_hidden(["powercfg",flag,str(scheme),subgroup,setting,str(int(value))],timeout=8)
    if p.returncode != 0:
        return False,(p.stderr or p.stdout or f"{label}: powercfg failed").strip()
    observed=_powercfg_index_for_scheme(scheme,subgroup,setting,which)
    ok=observed==int(value)
    suffix="AC" if str(which).lower()=="ac" else "DC"
    return ok,(f"{label} {suffix}: {observed} verified." if ok else f"{label} {suffix}: requested {value}, observed {observed}.")




def azor_fps_boost_power_status() -> Dict[str,Any]:
    found=_scheme_by_profile("azor_fps_boost")
    guid=str(found.get("guid") or "").lower() if found else ""
    active=(get_active_power_scheme() or "").lower()
    scheme=guid or "SCHEME_CURRENT"
    return {
        "name": AZOR_POWER_NAME,
        "guid": guid or None,
        "active_guid": active or None,
        "active": bool(guid and active==guid),
        "cpu_min_ac": _powercfg_index_for_scheme(scheme,"SUB_PROCESSOR","PROCTHROTTLEMIN","ac") if guid else None,
        "cpu_max_ac": _powercfg_index_for_scheme(scheme,"SUB_PROCESSOR","PROCTHROTTLEMAX","ac") if guid else None,
        "epp_ac": _powercfg_index_for_scheme(scheme,"SUB_PROCESSOR","PERFEPP","ac") if guid else None,
        "boost_mode_ac": _powercfg_index_for_scheme(scheme,"SUB_PROCESSOR","PERFBOOSTMODE","ac") if guid else None,
        "boost_policy_ac": _powercfg_index_for_scheme(scheme,"SUB_PROCESSOR","PERFBOOSTPOL","ac") if guid else None,
        "cooling_policy_ac": _powercfg_index_for_scheme(scheme,"SUB_PROCESSOR","SYSCOOLPOL","ac") if guid else None,
        "core_parking_min_ac": _powercfg_index_for_scheme(scheme,"SUB_PROCESSOR","CPMINCORES","ac") if guid else None,
        "pcie_aspm_ac": _powercfg_index_for_scheme(scheme,"SUB_PCIEXPRESS","ASPM","ac") if guid else None,
        "usb_suspend_ac": _powercfg_index_for_scheme(scheme,USB_SUBGROUP_GUID,USB_SELECTIVE_SUSPEND_GUID,"ac") if guid else None,
        "disk_idle_ac": _powercfg_index_for_scheme(scheme,"SUB_DISK","DISKIDLE","ac") if guid else None,
    }




def set_azor_fps_boost_power() -> Tuple[bool,str]:
    """Apply supported AC processor settings to the owned performance plan.

    Parking, EPP, USB, PCIe and disk-idle policies remain those of the source plan.
    No claim of FPS or input-latency gain is made by a configuration readback.
    """
    if os.name != "nt": return False,"Disponível só no Windows."
    capture_restore_point()
    ok,guid,detail=ensure_azor_fps_boost_scheme()
    if not ok or not guid: return False,detail
    steps=[]
    desired=[(subgroup,setting,value,label) for key,subgroup,setting,value,label in POWER_SETTINGS]
    for subgroup,setting,value,label in desired:
        current=_powercfg_index_for_scheme(guid,subgroup,setting,"ac")
        if current is None:
            steps.append((True,f"{label}: setting not exposed on this PC; preserved."))
            continue
        vok,vdetail=_set_powercfg_value_verified(guid,subgroup,setting,value,label,"ac")
        steps.append((vok,vdetail))
    p=run_hidden(["powercfg","/setactive",guid],timeout=8)
    if p.returncode != 0:
        return False,(p.stderr or p.stdout or f"Could not activate {AZOR_POWER_NAME}.").strip()
    active=(get_active_power_scheme() or "").lower()
    active_ok=active==guid.lower()
    status=azor_fps_boost_power_status()
    expected=POWER_EXPECTED
    checks=[]
    for key,val in expected.items():
        observed=status.get(key)
        checks.append(observed is None or observed==val)
    all_ok=active_ok and all(x[0] for x in steps) and all(checks)
    details=" ".join(x[1] for x in steps)
    log(f"{AZOR_POWER_NAME} apply result ok={all_ok} status={status}")
    prefix=f"{AZOR_POWER_NAME} {'activated and verified' if active_ok else 'activation NOT verified'}; GUID {guid}."
    return all_ok,(prefix+" "+details).strip()



def verify_game_mode() -> bool:
    a=reg_read("HKCU",r"Software\Microsoft\GameBar","AllowAutoGameMode")
    b=reg_read("HKCU",r"Software\Microsoft\GameBar","AutoGameModeEnabled")
    return a.get("value")==1 and b.get("value")==1


def verify_game_dvr_off() -> bool:
    a=reg_read("HKCU",r"System\GameConfigStore","GameDVR_Enabled")
    b=reg_read("HKCU",r"Software\Microsoft\Windows\CurrentVersion\GameDVR","AppCaptureEnabled")
    return a.get("value")==0 and b.get("value")==0


def set_game_mode_verified(enabled: bool=True) -> Tuple[bool,str]:
    set_game_mode(enabled)
    wanted=1 if enabled else 0
    a=reg_read("HKCU",r"Software\Microsoft\GameBar","AllowAutoGameMode").get("value")
    b=reg_read("HKCU",r"Software\Microsoft\GameBar","AutoGameModeEnabled").get("value")
    ok=(a==wanted and b==wanted)
    return ok,(f"Game Mode verified {'enabled' if enabled else 'disabled'}." if ok else f"Game Mode verification mismatch: AllowAutoGameMode={a}, AutoGameModeEnabled={b}, wanted={wanted}.")


def set_game_dvr_verified(enabled: bool=False) -> Tuple[bool,str]:
    set_game_dvr(enabled)
    wanted=1 if enabled else 0
    a=reg_read("HKCU",r"System\GameConfigStore","GameDVR_Enabled").get("value")
    b=reg_read("HKCU",r"Software\Microsoft\Windows\CurrentVersion\GameDVR","AppCaptureEnabled").get("value")
    ok=(a==wanted and b==wanted)
    return ok,(f"Game DVR/background capture verified {'enabled' if enabled else 'disabled'}." if ok else f"Game DVR verification mismatch: GameDVR_Enabled={a}, AppCaptureEnabled={b}, wanted={wanted}.")


def set_windows_suggestions_off() -> Tuple[bool,str]:
    capture_restore_point()
    p=r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
    names=["SubscribedContent-338388Enabled","SubscribedContent-353694Enabled","SystemPaneSuggestionsEnabled"]
    for n in names: reg_write("HKCU",p,n,0)
    ok=all(reg_read("HKCU",p,n).get("value")==0 for n in names)
    log(f"Windows suggestions disabled verified={ok}")
    return ok,"Windows promotional suggestions disabled and verified for the current user." if ok else "Some suggestion settings could not be verified."


def set_transparency_off() -> Tuple[bool,str]:
    capture_restore_point(); p=r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    reg_write("HKCU",p,"EnableTransparency",0)
    ok=reg_read("HKCU",p,"EnableTransparency").get("value")==0
    return ok,"Transparency effects disabled and verified." if ok else "Transparency setting could not be verified."


# Politica "Permitir widgets" (Modelos Administrativos > Componentes do Windows >
# Widgets). 0 esconde o botao e desliga o recurso para todos os usuarios.
WIDGETS_POLICY = ("HKLM", r"SOFTWARE\Policies\Microsoft\Dsh", "AllowNewsAndInterests")


def set_widgets_taskbar_hidden() -> Tuple[bool,str]:
    capture_restore_point(); p=r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
    try:
        reg_write("HKCU",p,"TaskbarDa",0)
    except PermissionError:
        # O Windows 11 atual protege TaskbarDa contra escrita de programas: "Acesso
        # negado" mesmo como administrador, e o item falhava em todo login. O caminho
        # que o Windows aceita e a politica, que alem de esconder desliga o recurso.
        if not is_admin():
            return False, "O Windows bloqueia esta chave para programas; a politica de Widgets exige administrador."
        baseline_backfill_registry([WIDGETS_POLICY])
        reg_write(*WIDGETS_POLICY, 0)
        ok = verify_widgets_hidden()
        return ok, ("Widgets desligados pela politica do Windows (Permitir widgets: desativado) e relidos."
                    if ok else "A politica de Widgets foi gravada, mas não foi confirmada.")
    ok=reg_read("HKCU",p,"TaskbarDa").get("value")==0
    return ok,"Widgets taskbar button hidden for current user." if ok else "Widgets taskbar setting could not be verified."


def verify_windows_suggestions_off() -> bool:
    p=r"Software\Microsoft\Windows\CurrentVersion\ContentDeliveryManager"
    names=["SubscribedContent-338388Enabled","SubscribedContent-353694Enabled","SystemPaneSuggestionsEnabled"]
    return all(reg_read("HKCU",p,n).get("value")==0 for n in names)

def verify_transparency_off() -> bool:
    return reg_read("HKCU",r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize","EnableTransparency").get("value")==0

def verify_widgets_hidden() -> bool:
    if reg_read("HKCU",r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced","TaskbarDa").get("value")==0:
        return True
    policy = reg_read(*WIDGETS_POLICY)
    return policy.get("exists") is True and policy.get("value") == 0

def set_background_apps_verified(disabled: bool=True) -> Tuple[bool,str]:
    set_background_apps_disabled(disabled)
    wanted=1 if disabled else 0
    ok=reg_read("HKCU",r"Software\Microsoft\Windows\CurrentVersion\BackgroundAccessApplications","GlobalUserDisabled").get("value")==wanted
    return ok,("Background-app preference written and verified in the current-user registry." if ok else "Background-app registry state did not verify. Windows may manage this differently on this build.")





# ---------------------------------------------------------------------------
# Lista de processos: por que isto deixou de ser o tasklist.exe
# ---------------------------------------------------------------------------
#
# O cliente reclamou de MAIS delay depois de instalar o AZOR, e a medicao deu
# razao a ele. O agente Guardian acorda a cada 5 s enquanto o jogo roda, e o
# retrato de processos custava um `tasklist.exe`: 100 ms de CreateProcess,
# ~10 vezes por minuto, DENTRO da partida. Criar processo e uma operacao de
# kernel que enumera a maquina inteira - e exatamente o formato de um engasgo
# periodico de frametime.
#
# O mesmo dado sai do Toolhelp32 dentro do proprio processo, sem spawn:
#
#     tasklist.exe    100,5 ms   (medido, 122 processos)
#     Toolhelp32        1,5 ms   (medido, 120 processos)
#
# Diferenca de conteudo: nenhuma que importe. O tasklist chama o PID 0 de
# "System Idle Process" e o Toolhelp de "[System Process]", e o tasklist se ve
# na propria lista. Nenhum jogo se chama assim.
#
# O tasklist continua existindo para as DUAS telas que precisam da coluna de
# memoria (monitoramento e hardware) - elas so rodam com a pagina aberta, nunca
# no meio de uma partida.

_TH32CS_SNAPPROCESS = 0x00000002


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_ulong),
        ("cntUsage", ctypes.c_ulong),
        ("th32ProcessID", ctypes.c_ulong),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", ctypes.c_ulong),
        ("cntThreads", ctypes.c_ulong),
        ("th32ParentProcessID", ctypes.c_ulong),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", ctypes.c_ulong),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


_PROCLIST_CACHE: Dict[str, Any] = {"ts": 0.0, "rows": []}
PROCLIST_TTL = 2.0


def _process_list(force: bool = False) -> List[Tuple[str, int]]:
    """(nome, pid) de todo processo visivel, sem abrir processo externo."""
    global _PROCLIST_CACHE
    now = time.time()
    if not force and (now - float(_PROCLIST_CACHE.get("ts", 0))) < PROCLIST_TTL:
        return list(_PROCLIST_CACHE.get("rows") or [])
    rows: List[Tuple[str, int]] = []
    if os.name == "nt":
        try:
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
            k32.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PROCESSENTRY32W)]
            k32.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_PROCESSENTRY32W)]
            k32.CloseHandle.argtypes = [ctypes.c_void_p]
            snap = k32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
            if snap and snap != ctypes.c_void_p(-1).value:
                try:
                    entry = _PROCESSENTRY32W()
                    entry.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
                    ok = k32.Process32FirstW(snap, ctypes.byref(entry))
                    while ok:
                        rows.append((entry.szExeFile, int(entry.th32ProcessID)))
                        ok = k32.Process32NextW(snap, ctypes.byref(entry))
                finally:
                    k32.CloseHandle(snap)
        except Exception as e:
            log(f"Toolhelp32 falhou, caindo para tasklist: {e}")
            rows = [(str(r[0]), int(str(r[1]).strip('"') or 0))
                    for r in _tasklist_rows() if len(r) > 1 and str(r[1]).strip('"').isdigit()]
    _PROCLIST_CACHE = {"ts": now, "rows": rows}
    return list(rows)


# ---------------------------------------------------------------------------
# "Esta jogando AGORA?" - a pergunta mais barata do app
# ---------------------------------------------------------------------------
#
# Detectar pela lista de processos responde "o jogo esta ABERTO". Para decidir
# se o AZOR deve ficar quieto, a pergunta certa e outra: "o jogo esta NA FRENTE
# agora?". Se o cliente deu alt-tab para olhar o AZOR, a interface tem que estar
# viva; se ele voltou para a partida, o AZOR tem que sumir.
#
# A janela em primeiro plano custa duas chamadas de user32 (~50 us) e nao
# enumera nada. E o sinal certo pelo preco certo.

_FOREGROUND_CACHE: Dict[str, Any] = {"ts": 0.0, "value": ("", 0)}


def foreground_process(force: bool = False) -> Tuple[str, int]:
    """(nome minusculo, pid) do dono da janela em primeiro plano."""
    global _FOREGROUND_CACHE
    now = time.time()
    if not force and (now - float(_FOREGROUND_CACHE.get("ts", 0))) < 0.5:
        return tuple(_FOREGROUND_CACHE.get("value") or ("", 0))  # type: ignore[return-value]
    name, pid = "", 0
    if os.name == "nt":
        try:
            u32 = ctypes.windll.user32
            hwnd = u32.GetForegroundWindow()
            if hwnd:
                out = ctypes.c_ulong(0)
                u32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(out))
                pid = int(out.value)
                if pid:
                    name = _process_name_of_pid(pid)
        except Exception:
            name, pid = "", 0
    _FOREGROUND_CACHE = {"ts": now, "value": (name, pid)}
    return name, pid


def _process_name_of_pid(pid: int) -> str:
    """Nome da imagem de um PID único, sem varrer a máquina inteira."""
    if os.name != "nt" or not pid:
        return ""
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = ctypes.c_void_p
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(260)
            size = ctypes.c_ulong(260)
            k32.QueryFullProcessImageNameW.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
            if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value).lower()
        finally:
            ctypes.WinDLL("kernel32").CloseHandle(ctypes.c_void_p(h))
    except Exception:
        pass
    return ""


_GAME_FOCUS_CACHE: Dict[str, Any] = {"ts": 0.0, "value": None}


def game_focused(force: bool = False) -> Dict[str, Any]:
    """O jogo configurado esta em primeiro plano NESTE instante?

    O resultado INTEIRO fica em cache por 0,5 s, e não so a janela em primeiro
    plano. A primeira versão desta função relia `load_settings()` a cada chamada
    - 0,172 ms de disco - e quem a chama e o laço do stream, até 125 vezes por
    segundo: 21,5 ms/s, ou 2% de um núcleo gastos relendo um JSON que não mudou.
    Sai mais caro que o problema que ela veio resolver.
    """
    global _GAME_FOCUS_CACHE
    now = time.time()
    cached = _GAME_FOCUS_CACHE.get("value")
    if not force and cached is not None and (now - float(_GAME_FOCUS_CACHE.get("ts", 0))) < 0.5:
        return dict(cached)
    name, pid = foreground_process(force=force)
    if not name:
        out = {"focused": False, "name": "", "pid": 0}
    else:
        configured = {str(x).lower() for x in (load_settings().get("configured_games") or [])}
        out = {"focused": name in configured, "name": name, "pid": pid}
    _GAME_FOCUS_CACHE = {"ts": now, "value": out}
    return dict(out)


_TASKLIST_CACHE: Dict[str, Any] = {"ts": 0.0, "rows": []}
TASKLIST_TTL = 6.0


def _tasklist_rows(force: bool = False) -> List[List[str]]:
    """Uma única leitura da lista de processos, compartilhada por todo mundo.

    Tres funcoes diferentes abriam seu próprio tasklist.exe: nomes de processo
    (monitor de jogo), top por memória (tela de monitoramento) e memória por
    imagem (hardware). Em regime isso dava ~14 tasklist por minuto, o processo
    mais caro da lista (~130 ms cada). Agora e uma leitura so, valida por 6 s.
    """
    global _TASKLIST_CACHE
    now = time.time()
    if not force and (now - float(_TASKLIST_CACHE.get("ts", 0))) < TASKLIST_TTL:
        return list(_TASKLIST_CACHE.get("rows") or [])
    rows: List[List[str]] = []
    if os.name == "nt":
        try:
            p = run_hidden(["tasklist", "/FO", "CSV", "/NH"], timeout=12)
            rows = [row for row in csv.reader((p.stdout or "").splitlines()) if row]
        except Exception as e:
            log(f"tasklist failed: {e}")
            rows = []
    _TASKLIST_CACHE = {"ts": now, "rows": rows}
    return list(rows)


def _process_names() -> List[str]:
    # Caminho quente: usado pelo monitor de jogo a cada volta do Guardian.
    return [name.lower() for name, _pid in _process_list()]








def detect_external_islc_process() -> Dict[str,Any]:
    # Compatibility name used by existing modules. There is no external ISLC process anymore.
    return MEMORY_ENGINE.status()


def ensure_external_islc_running() -> Tuple[bool,str]:
    # Compatibility name: starts AZOR's internal memory engine.
    return MEMORY_ENGINE.start()











def bios_snapshot() -> Dict[str,Any]:
    if os.name != "nt": return {"supported":False,"reason":"Disponível só no Windows."}
    script=r'''
$bb=Get-CimInstance Win32_BaseBoard | Select-Object -First 1 Manufacturer,Product,Version
$bios=Get-CimInstance Win32_BIOS | Select-Object -First 1 Manufacturer,SMBIOSBIOSVersion,ReleaseDate
$cpu=Get-CimInstance Win32_Processor | Select-Object -First 1 Name,Manufacturer,MaxClockSpeed,NumberOfCores,NumberOfLogicalProcessors
$ram=@(Get-CimInstance Win32_PhysicalMemory | Select-Object Manufacturer,PartNumber,Capacity,Speed,ConfiguredClockSpeed)
$gpu=@(Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion)
[PSCustomObject]@{BaseBoard=$bb;BIOS=$bios;CPU=$cpu;RAM=$ram;GPU=$gpu}
'''
    try:
        data=powershell_json(script,timeout=15) or {}
    except Exception as e:
        # Read-only Win32/registry fallback for systems where WMI is disabled.
        fallback={"BaseBoard":{},"BIOS":{},"CPU":{},"RAM":[],"GPU":[],"partial":True,"reason":str(e)}
        try:
            if winreg is not None:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r"HARDWARE\DESCRIPTION\System\BIOS",0,winreg.KEY_READ) as key:
                    def rv(name,default=""):
                        try:return winreg.QueryValueEx(key,name)[0]
                        except OSError:return default
                    fallback["BaseBoard"]={"Manufacturer":rv("BaseBoardManufacturer"),"Product":rv("BaseBoardProduct"),"Version":rv("BaseBoardVersion")}
                    fallback["BIOS"]={"Manufacturer":rv("BIOSVendor"),"SMBIOSBIOSVersion":rv("BIOSVersion"),"ReleaseDate":rv("BIOSReleaseDate")}
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",0,winreg.KEY_READ) as key:
                    def cv(name,default=""):
                        try:return winreg.QueryValueEx(key,name)[0]
                        except OSError:return default
                    fallback["CPU"]={"Name":str(cv("ProcessorNameString")).strip(),"Manufacturer":cv("VendorIdentifier"),"MaxClockSpeed":cv("~MHz",0),"NumberOfCores":os.cpu_count() or 0,"NumberOfLogicalProcessors":os.cpu_count() or 0}
            mem=_memory_windows();total=float(mem.get("total_gb") or 0)
            if total>0:fallback["RAM"]=[{"Manufacturer":"Windows","PartNumber":"Memória física total","Capacity":int(total*(1024**3)),"Speed":0,"ConfiguredClockSpeed":0}]
            class _DISPLAY_DEVICEW(ctypes.Structure):
                _fields_=[("cb",ctypes.c_ulong),("DeviceName",ctypes.c_wchar*32),("DeviceString",ctypes.c_wchar*128),("StateFlags",ctypes.c_ulong),("DeviceID",ctypes.c_wchar*128),("DeviceKey",ctypes.c_wchar*128)]
            for idx in range(16):
                dd=_DISPLAY_DEVICEW();dd.cb=ctypes.sizeof(dd)
                if not ctypes.windll.user32.EnumDisplayDevicesW(None,idx,ctypes.byref(dd),0):break
                name=str(dd.DeviceString or "").strip()
                if name and name not in [x.get("Name") for x in fallback["GPU"]]:fallback["GPU"].append({"Name":name,"AdapterRAM":None,"DriverVersion":None})
            fallback["ResizableBAR"]=None;fallback["supported"]=bool(fallback["CPU"].get("Name") or fallback["RAM"] or fallback["BaseBoard"].get("Product"))
            return fallback
        except Exception as fallback_error:
            return {"supported":False,"reason":f"{e}; fallback: {fallback_error}"}
    rebar=None
    exe=shutil.which("nvidia-smi")
    if exe:
        try:
            q=run_hidden([exe,"-q"],timeout=10).stdout or ""
            m=re.search(r"Resizable BAR\s*:\s*(Enabled|Disabled|Yes|No)",q,re.I)
            if m: rebar=m.group(1)
        except Exception: pass
    data["ResizableBAR"] = rebar
    data["supported"] = True
    return data


HARDWARE_PROFILE_FILE = DATA_DIR / "hardware_profile.json"


# ---------------------------------------------------------------------------
# CPU hibrida: P-cores e E-cores
# ---------------------------------------------------------------------------
#
# A partir da 12a geracao a Intel mistura nucleos de desempenho (P) com nucleos
# de eficiencia (E) no mesmo processador, e o total de nucleos deixou de dizer o
# que a maquina aguenta: um 12400 com 6 nucleos iguais nao e um 12600K com 6P+4E.
#
# A leitura sai de GetLogicalProcessorInformationEx, que e a API oficial - nao de
# uma tabela de modelos, que envelheceria a cada lancamento. Cada nucleo carrega
# uma EfficiencyClass; quando todos tem a mesma, o processador NAO e hibrido, e
# a funcao diz isso em vez de fingir uma divisao.
#
# AMD tambem devolve classe unica aqui (os X3D nao se declaram hibridos por esta
# API), entao o resultado e honesto nos dois casos: quando nao da para separar,
# o campo volta como nao identificado.

_RELATION_PROCESSOR_CORE = 0


def is_windows_11() -> bool:
    """True no Windows 11. A separação correta e pela build, não pelo nome.

    O `platform.release()` devolve "10" nos dois sistemas; quem separa e a build
    22000, primeira do Windows 11. Checar o nome faz um 11 ser tratado como 10.
    """
    if os.name != "nt":
        return False
    try:
        return int(str(platform.version() or "0.0.0").split(".")[-1]) >= 22000
    except Exception:
        return False


def cpu_topology(force: bool = False) -> Dict[str, Any]:
    """P-cores / E-cores lidos do Windows, ou 'não identificado'."""
    def probe() -> Dict[str, Any]:
        out = {"hybrid": None, "performance_cores": None, "efficiency_cores": None,
               "physical_cores": None, "smt": None,
               "detail": "Topologia de núcleos não identificada neste sistema."}
        if os.name != "nt":
            return out
        try:
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            size = ctypes.c_ulong(0)
            k32.GetLogicalProcessorInformationEx(
                _RELATION_PROCESSOR_CORE, None, ctypes.byref(size))
            if not size.value:
                return out
            buf = ctypes.create_string_buffer(size.value)
            if not k32.GetLogicalProcessorInformationEx(
                    _RELATION_PROCESSOR_CORE, buf, ctypes.byref(size)):
                return out
            raw = buf.raw[:size.value]
            classes: List[int] = []
            smt = False
            off = 0
            while off + 8 <= len(raw):
                rel, entry_size = struct.unpack_from("<II", raw, off)
                if entry_size <= 0 or off + entry_size > len(raw):
                    break
                if rel == _RELATION_PROCESSOR_CORE:
                    flags, eff = struct.unpack_from("<BB", raw, off + 8)
                    classes.append(int(eff))
                    if flags & 1:
                        smt = True
                off += entry_size
            if not classes:
                return out
            top = max(classes)
            perf = sum(1 for c in classes if c == top)
            eff_n = len(classes) - perf
            hybrid = len(set(classes)) > 1
            out.update({
                "hybrid": hybrid,
                "physical_cores": len(classes),
                "smt": smt,
                "performance_cores": perf if hybrid else None,
                "efficiency_cores": eff_n if hybrid else None,
                "detail": (f"{perf} núcleo(s) de desempenho (P) e {eff_n} de eficiência (E)."
                           if hybrid else
                           f"{len(classes)} núcleo(s) físico(s), todos da mesma classe "
                           f"(processador não híbrido)."),
            })
            return out
        except Exception as exc:
            log_debug(f"cpu_topology falhou: {exc}")
            return out
    return cached_reading("cpu_topology", 3600.0, probe, force=force) or {}


def hardware_profile(force: bool=False) -> Dict[str,Any]:
    """Build a conservative one-click profile from detected hardware.

    This classifies capabilities; it does not infer FPS or write firmware.
    Cached data keeps the frequently refreshed UI lightweight.
    """
    cached=_safe_json_read(HARDWARE_PROFILE_FILE,{})
    if not force and isinstance(cached,dict):
        try:
            if time.time()-float(cached.get("cached_at_epoch") or 0)<600:
                return cached
        except Exception:
            pass
    hw=bios_snapshot()
    cpu=hw.get("CPU") or {}
    ram=hw.get("RAM") or []
    gpu=hw.get("GPU") or []
    if isinstance(ram,dict):ram=[ram]
    if isinstance(gpu,dict):gpu=[gpu]
    ram_gb=round(sum(float(x.get("Capacity") or 0) for x in ram if isinstance(x,dict))/(1024**3),1)
    cores=int(cpu.get("NumberOfCores") or 0) if isinstance(cpu,dict) else 0
    logical=int(cpu.get("NumberOfLogicalProcessors") or 0) if isinstance(cpu,dict) else 0
    topo=cpu_topology()
    gpu_names=[str(x.get("Name") or "").strip() for x in gpu if isinstance(x,dict) and str(x.get("Name") or "").strip()]
    discrete=any(not any(k in name.lower() for k in ["microsoft basic","intel(r) uhd","intel(r) iris","radeon(tm) graphics"]) for name in gpu_names)
    battery=has_battery()
    reasons=[]
    if not hw.get("supported"):
        tier="unknown";label="Hardware não confirmado";recommended="safe"
        reasons.append("A leitura completa de hardware não ficou disponível; AUTO usa o modo SAFE.")
    elif battery:
        tier="mobile";label="Notebook / perfil térmico móvel";recommended="safe"
        reasons.append("Bateria detectada: AUTO preserva o plano de energia e evita política agressiva contínua.")
    elif ram_gb>=16 and logical>=8 and discrete:
        tier="performance";label="Desktop competitivo";recommended="competitive"
        reasons.append(f"{ram_gb:g} GB de RAM, {logical} threads lógicas e GPU dedicada detectada(s).")
    elif ram_gb>=12 and logical>=6:
        tier="balanced";label="PC balanceado";recommended="competitive"
        reasons.append(f"{ram_gb:g} GB de RAM e {logical} threads lógicas suportam o perfil competitivo conservador.")
    else:
        tier="entry";label="PC de entrada / preservação";recommended="safe"
        reasons.append("AUTO preserva recursos em hardware com RAM/CPU limitados ou parcialmente detectados.")
    stream_ready=bool(not battery and ram_gb>=24 and logical>=12)
    if stream_ready:
        reasons.append("O hardware também atende ao critério local do modo JOGO + LIVE (24 GB de RAM e 12 threads ou mais).")
    result={
        "ok":bool(hw.get("supported")),"tier":tier,"label":label,"recommended":recommended,
        "stream_ready":stream_ready,"battery":battery,"ram_gb":ram_gb,"cpu":str(cpu.get("Name") or "") if isinstance(cpu,dict) else "",
        "cores":cores,"logical_processors":logical,"gpus":gpu_names,"discrete_gpu":discrete,
        # P-cores / E-cores lidos da API do Windows. Vem tudo None quando o
        # processador nao e hibrido ou quando a leitura nao esta disponivel -
        # a tela mostra "nao identificado" em vez de inventar uma divisao.
        "topology":topo,
        "reasons":reasons,"detected_at":_ts(),"cached_at_epoch":time.time(),
    }
    # Cache derivado: se nao der para gravar, o valor ja esta calculado em
    # memoria e a proxima chamada recalcula. Isto NAO pode derrubar /api/summary.
    _cache_json_write(HARDWARE_PROFILE_FILE,result)
    return result



# ==================== HARDWARE COMMAND CENTER ====================
# Every value below is read from Windows and reported as-is. Where Windows does
# not expose a reliable answer the field stays None and the UI says so, instead
# of the app inventing a health score.

STORAGE_HEALTH_CACHE: Dict[str, Any] = {"ts": 0.0, "data": {}}


def trim_state() -> Dict[str, Any]:
    """Read the global TRIM/DeleteNotify policy.

    fsutil reports it per filesystem; 0 means TRIM notifications are enabled.
    """
    if os.name != "nt":
        return {"supported": False, "ntfs": None, "refs": None, "detail": "Disponível só no Windows."}
    try:
        out = (run_hidden(["fsutil", "behavior", "query", "DisableDeleteNotify"], timeout=12).stdout or "")
    except Exception as e:
        return {"supported": False, "ntfs": None, "refs": None, "detail": str(e)}
    result: Dict[str, Any] = {"supported": True, "ntfs": None, "refs": None, "raw": out.strip()[:400]}
    for line in out.splitlines():
        m = re.search(r"(NTFS|ReFS)\s+DisableDeleteNotify\s*=\s*(\d)", line, re.I)
        if m:
            key = "ntfs" if m.group(1).upper() == "NTFS" else "refs"
            result[key] = (m.group(2) == "0")  # 0 = TRIM notifications enabled
    if result["ntfs"] is None:
        m = re.search(r"DisableDeleteNotify\s*=\s*(\d)", out)
        if m:
            result["ntfs"] = (m.group(1) == "0")
    result["detail"] = ("TRIM habilitado para NTFS." if result["ntfs"] else
                        "TRIM aparece desabilitado para NTFS." if result["ntfs"] is False else
                        "O Windows não retornou o estado de TRIM.")
    return result


# Mesma numeracao do STORAGE_BUS_TYPE e do BusType do Get-PhysicalDisk.
_STORAGE_BUS_NAMES = {1: "SCSI", 2: "ATAPI", 3: "ATA", 4: "1394", 5: "SSA", 6: "Fibre Channel", 7: "USB",
                      8: "RAID", 9: "iSCSI", 10: "SAS", 11: "SATA", 12: "SD", 13: "MMC", 14: "Virtual",
                      15: "File Backed Virtual", 16: "Storage Spaces", 17: "NVMe", 18: "SCM", 19: "UFS"}


def _disks_from_driver(max_disks: int = 32) -> List[Dict[str, Any]]:
    """Tipo de midia, barramento e tamanho direto do driver de cada disco.

    Get-PhysicalDisk e Get-Volume dependem do servico smphost (Storage Spaces
    SMP), que otimizadores e Windows "debloated" costumam desativar; sem ele as
    listas voltam vazias ate como administrador, e os itens "so com SSD" ficavam
    sem saber o tipo do disco. O driver responde sem o servico e sem
    administrador: o disco e aberto com acesso zero, so para consulta.
    """
    if os.name != "nt":
        return []
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = ctypes.c_void_p
    k32.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p,
                                ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p]
    k32.DeviceIoControl.restype = ctypes.c_int
    k32.DeviceIoControl.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32,
                                    ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    invalid = ctypes.c_void_p(-1).value

    def ioctl(handle, code: int, query: Optional[bytes], size: int) -> Optional[bytes]:
        out = ctypes.create_string_buffer(size)
        got = ctypes.c_uint32(0)
        ok = k32.DeviceIoControl(handle, code, query, len(query) if query else 0, out, size, ctypes.byref(got), None)
        return out.raw[:got.value] if ok else None

    disks: List[Dict[str, Any]] = []
    for number in range(max_disks):
        handle = k32.CreateFileW(f"\\\\.\\PhysicalDrive{number}", 0, 3, None, 3, 0, None)
        if not handle or handle == invalid:
            continue
        try:
            # IOCTL_STORAGE_QUERY_PROPERTY: 7 = StorageDeviceSeekPenaltyProperty, 0 = StorageDeviceProperty.
            seek = ioctl(handle, 0x002D1400, struct.pack("<iii", 7, 0, 0), 12)
            desc = ioctl(handle, 0x002D1400, struct.pack("<iii", 0, 0, 0), 1024)
            geometry = ioctl(handle, 0x000700A0, None, 256)  # IOCTL_DISK_GET_DRIVE_GEOMETRY_EX
        finally:
            k32.CloseHandle(handle)
        media = "Unspecified"
        if seek and len(seek) >= 9:
            media = "HDD" if seek[8] else "SSD"  # IncursSeekPenalty
        bus, name = "", f"Disco {number}"
        if desc and len(desc) >= 32:
            bus = _STORAGE_BUS_NAMES.get(struct.unpack_from("<i", desc, 28)[0], "")
            offset = struct.unpack_from("<I", desc, 16)[0]  # ProductIdOffset
            if 0 < offset < len(desc):
                end = desc.find(b"\0", offset)
                name = desc[offset:end if end >= 0 else len(desc)].decode("ascii", "replace").strip() or name
        size_gb = round(struct.unpack_from("<q", geometry, 24)[0] / 1024 ** 3, 1) if geometry and len(geometry) >= 32 else None
        disks.append({"Number": number, "Name": name, "Media": media, "Bus": bus, "Health": "",
                      "Operational": "Tipo e barramento lidos direto do driver do disco", "SizeGB": size_gb,
                      "Wear": None, "TempC": None, "PowerOnHours": None, "ReadErrors": None, "WriteErrors": None})
    return disks


def _fixed_volumes() -> List[Dict[str, Any]]:
    """Volumes fixos com letra, sem depender do serviço de armazenamento."""
    if os.name != "nt":
        return []
    k32 = ctypes.WinDLL("kernel32")
    mask = k32.GetLogicalDrives()
    volumes: List[Dict[str, Any]] = []
    for i in range(26):
        if not mask >> i & 1:
            continue
        root = f"{chr(65 + i)}:\\"
        if k32.GetDriveTypeW(ctypes.c_wchar_p(root)) != 3:  # DRIVE_FIXED
            continue
        try:
            usage = shutil.disk_usage(root)
        except OSError:
            continue
        label, fs = ctypes.create_unicode_buffer(261), ctypes.create_unicode_buffer(261)
        k32.GetVolumeInformationW(ctypes.c_wchar_p(root), label, 261, None, None, None, fs, 261)
        volumes.append({"Letter": chr(65 + i), "Label": label.value, "FS": fs.value,
                        "SizeGB": round(usage.total / 1024 ** 3, 1), "FreeGB": round(usage.free / 1024 ** 3, 1),
                        "Health": ""})
    return volumes


def storage_health(force: bool = False) -> Dict[str, Any]:
    """Physical disk health, media type and reliability counters when exposed.

    SMART detail comes from Get-StorageReliabilityCounter, which many SATA
    bridges and USB enclosures simply do not implement. A missing counter is
    reported as unavailable; it is never replaced with an estimate.
    """
    global STORAGE_HEALTH_CACHE
    now = time.time()
    if not force and now - float(STORAGE_HEALTH_CACHE.get("ts") or 0) < 45:
        return dict(STORAGE_HEALTH_CACHE.get("data") or {})
    if os.name != "nt":
        return {"ok": False, "supported": False, "reason": "Disponível só no Windows.", "disks": [], "volumes": []}
    script = r"""
$disks=@(Get-PhysicalDisk -ErrorAction SilentlyContinue | ForEach-Object{
  $rc=$null
  try{$rc=$_|Get-StorageReliabilityCounter -ErrorAction Stop}catch{}
  [PSCustomObject]@{
    Number=$_.DeviceId; Name=$_.FriendlyName; Media=[string]$_.MediaType; Bus=[string]$_.BusType
    Health=[string]$_.HealthStatus; Operational=([string[]]$_.OperationalStatus -join ', ')
    SizeGB=[math]::Round($_.Size/1GB,1)
    Wear=$(if($rc){$rc.Wear}else{$null}); TempC=$(if($rc){$rc.Temperature}else{$null})
    PowerOnHours=$(if($rc){$rc.PowerOnHours}else{$null})
    ReadErrors=$(if($rc){$rc.ReadErrorsTotal}else{$null}); WriteErrors=$(if($rc){$rc.WriteErrorsTotal}else{$null})
  }})
$vols=@(Get-Volume -ErrorAction SilentlyContinue | Where-Object{$_.DriveLetter} | ForEach-Object{
  [PSCustomObject]@{Letter=[string]$_.DriveLetter; Label=[string]$_.FileSystemLabel; FS=[string]$_.FileSystem
    SizeGB=[math]::Round($_.Size/1GB,1); FreeGB=[math]::Round($_.SizeRemaining/1GB,1)
    Health=[string]$_.HealthStatus}})
[PSCustomObject]@{Disks=$disks;Volumes=$vols}
"""
    try:
        data = powershell_json(script, timeout=40) or {}
    except Exception as e:
        result = {"ok": False, "supported": False, "reason": str(e), "disks": [], "volumes": [], "trim": trim_state()}
        STORAGE_HEALTH_CACHE = {"ts": now, "data": result}
        return result
    disks = data.get("Disks") or []
    vols = data.get("Volumes") or []
    if isinstance(disks, dict): disks = [disks]
    if isinstance(vols, dict): vols = [vols]
    media_source = "windows"
    if not disks:
        try:
            disks = _disks_from_driver()
        except Exception as exc:
            log_debug(f"_disks_from_driver falhou: {exc}")
            disks = []
        if disks:
            media_source = "driver"
    if not vols:
        try:
            vols = _fixed_volumes()
        except Exception as exc:
            log_debug(f"_fixed_volumes falhou: {exc}")

    findings: List[Dict[str, str]] = []
    for d in disks:
        if not isinstance(d, dict): continue
        name = str(d.get("Name") or "Disco")
        health = str(d.get("Health") or "")
        if health and health.lower() not in ("healthy", "saudavel"):
            findings.append({"level": "bad", "text": f"{name}: o Windows reporta HealthStatus = {health}. Faca backup antes de continuar otimizando."})
        try:
            wear = d.get("Wear")
            if wear is not None and float(wear) >= 80:
                findings.append({"level": "warn", "text": f"{name}: desgaste reportado em {float(wear):.0f}%. O valor vem do contador do próprio SSD."})
        except Exception:
            pass
        try:
            temp = d.get("TempC")
            if temp is not None and float(temp) >= 70:
                findings.append({"level": "warn", "text": f"{name}: {float(temp):.0f} C reportados pelo disco. Acima de 70 C o NVMe costuma reduzir desempenho para se proteger."})
        except Exception:
            pass
    for v in vols:
        if not isinstance(v, dict): continue
        try:
            size, free = float(v.get("SizeGB") or 0), float(v.get("FreeGB") or 0)
            if size > 0 and (free / size) < 0.10:
                findings.append({"level": "warn", "text": f"Volume {v.get('Letter')}: apenas {free:.0f} GB livres de {size:.0f} GB. Abaixo de 10% livres o Windows e os jogos passam a sofrer com paginacao e shader cache."})
        except Exception:
            pass

    trim = trim_state()
    if trim.get("ntfs") is False and any(str(d.get("Media") or "").upper() == "SSD" for d in disks if isinstance(d, dict)):
        findings.append({"level": "warn", "text": "TRIM aparece desabilitado e ha SSD no sistema. Sem TRIM o SSD perde desempenho de escrita ao longo do tempo."})

    smart_note = ("Desgaste, temperatura e horas ligadas vem do contador de confiabilidade do próprio disco. Muitos SSDs SATA e gabinetes USB não implementam esse contador; nesse caso o AZOR mostra indisponível em vez de estimar."
                  if media_source == "windows" else
                  "O serviço de armazenamento do Windows (Storage Spaces SMP) esta desligado neste PC, então tipo, barramento e tamanho foram lidos direto do driver de cada disco. Saúde, desgaste e temperatura so chegam por esse serviço e ficam como não reportados.")
    result = {
        "ok": True, "supported": True, "disks": disks, "volumes": vols, "media_source": media_source,
        "trim": trim, "findings": findings, "checked_at": _ts(), "smart_note": smart_note,
    }
    STORAGE_HEALTH_CACHE = {"ts": now, "data": result}
    return result


DRIVER_CLASSES = ("DISPLAY", "NET", "SCSIADAPTER", "HDC", "SYSTEM", "MEDIA", "USB", "HIDCLASS", "MOUSE", "KEYBOARD")


def _parse_wmi_date(value: Any) -> Optional[str]:
    """WMI dates arrive either as /Date(ms)/ or as a CIM_DATETIME string."""
    text = str(value or "")
    m = re.search(r"/Date\((-?\d+)", text)
    if m:
        try:
            return time.strftime("%Y-%m-%d", time.localtime(int(m.group(1)) / 1000.0))
        except Exception:
            return None
    m = re.match(r"(\d{4})(\d{2})(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    return m.group(0) if m else None


VIRTUAL_DEVICE_PATTERNS = (
    "wan miniport", "microsoft kernel", "ras async", "microsoft isatap", "teredo",
    "microsoft 6to4", "microsoft ip-http", "wi-fi direct", "microsoft wi-fi",
    "microsoft hyper-v", "bluetooth device (personal area network)", "npcap", "vmware",
    "virtualbox", "tap-windows", "microsoft loopback", "wintun", "wireguard",
)


def _is_vendor_driver(driver: Dict[str, Any]) -> bool:
    """True when the driver is one the user could replace from a vendor site."""
    name = str(driver.get("name") or "").lower()
    vendor = str(driver.get("vendor") or "").lower()
    if any(p in name for p in VIRTUAL_DEVICE_PATTERNS):
        return False
    if vendor.startswith("microsoft"):
        return False
    return True


def driver_inventory(force: bool = False) -> Dict[str, Any]:
    """Age and version of the drivers that actually affect gaming.

    Driver *age* is a fact Windows reports. Whether a newer driver exists is not
    something this app can know offline, so it never claims a driver is outdated
    against a catalogue it cannot see - only how old the installed one is.
    """
    if os.name != "nt":
        return {"ok": False, "supported": False, "reason": "Disponível só no Windows.", "drivers": []}
    classes = ",".join(f"'{c}'" for c in DRIVER_CLASSES)
    script = (
        "@(Get-CimInstance Win32_PnPSignedDriver -ErrorAction SilentlyContinue | "
        f"Where-Object {{ $_.DeviceClass -in @({classes}) -and $_.DeviceName }} | "
        "Select-Object DeviceName,DeviceClass,DriverVersion,DriverDate,Manufacturer,DriverProviderName)"
    )
    try:
        rows = powershell_json(script, timeout=45) or []
    except Exception as e:
        return {"ok": False, "supported": False, "reason": str(e), "drivers": []}
    if isinstance(rows, dict): rows = [rows]
    today = time.time()
    out: List[Dict[str, Any]] = []
    seen = set()
    for r in rows:
        if not isinstance(r, dict): continue
        name = str(r.get("DeviceName") or "").strip()
        if not name or name in seen: continue
        seen.add(name)
        date = _parse_wmi_date(r.get("DriverDate"))
        age_days = None
        if date:
            try:
                age_days = int((today - time.mktime(time.strptime(date, "%Y-%m-%d"))) / 86400)
            except Exception:
                age_days = None
        out.append({
            "name": name,
            "cls": str(r.get("DeviceClass") or "").upper(),
            "version": str(r.get("DriverVersion") or ""),
            "date": date,
            "age_days": age_days,
            "vendor": str(r.get("DriverProviderName") or r.get("Manufacturer") or ""),
        })
    for d in out:
        d["vendor_driver"] = _is_vendor_driver(d)
    priority = {"DISPLAY": 0, "NET": 1, "SCSIADAPTER": 2, "HDC": 3}
    out.sort(key=lambda x: (priority.get(x["cls"], 9), -(x["age_days"] or 0)))
    key_drivers = [d for d in out if d["cls"] in ("DISPLAY", "NET", "SCSIADAPTER", "HDC") and d["vendor_driver"]]
    # Age is only actionable for a driver the user can actually replace from a
    # vendor site. Microsoft's inbox and virtual-adapter drivers carry ancient
    # placeholder dates by design and are serviced by Windows Update, so calling
    # them "outdated" would be a number the user cannot act on.
    stale = [d for d in key_drivers if (d.get("age_days") or 0) > 540]
    return {
        "ok": True, "supported": True, "drivers": out[:120], "key_drivers": key_drivers[:12],
        "total": len(out), "vendor_count": sum(1 for d in out if d["vendor_driver"]),
        "stale": stale[:8], "stale_count": len(stale), "checked_at": _ts(),
        "note": "O AZOR mostra a data e a versão que o Windows reporta para o driver instalado. Ele não baixa nem instala driver, e não afirma que existe versão mais nova: isso so o site oficial do fabricante pode confirmar.",
        "scope_note": "A idade so e avaliada em drivers de fabricante (GPU, rede, armazenamento). Drivers nativos da Microsoft e adaptadores virtuais como WAN Miniport tem data simbólica de 2006 e são atualizados pelo Windows Update, então contar a idade deles seria um alarme falso.",
    }


# --- Startup / background impact -----------------------------------------
# Enable/disable uses the same StartupApproved mechanism the Task Manager uses:
# the Run entry is never deleted, only flagged, so every change is reversible.
STARTUP_APPROVED = {
    "HKCU_RUN": ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
    "HKLM_RUN": ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"),
    # Programas 32 bits de "todos os usuários" (Adobe, atualizadores, vários launchers) moram
    # no WOW6432Node; o Gerenciador de Tarefas guarda a aprovação deles em "Run32".
    "HKLM_RUN32": ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run32"),
}
STARTUP_RUN_KEYS = {
    "HKCU_RUN": ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Run"),
    "HKLM_RUN": ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Run"),
    "HKLM_RUN32": ("HKLM", r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"),
}


def _all_process_memory() -> Dict[str, Dict[str, Any]]:
    """Working set per image name, summed across instances.

    Chromium-style apps run many processes under one name; the number the user
    cares about is the total that image is holding right now.
    """
    rows: Dict[str, Dict[str, Any]] = {}
    if os.name != "nt":
        return rows
    try:
        for row in _tasklist_rows():
            if len(row) < 5:
                continue
            digits = re.sub(r"\D", "", row[4])
            if not digits:
                continue
            name = str(row[0]).lower()
            entry = rows.setdefault(name, {"name": row[0], "memory_mb": 0.0, "instances": 0})
            entry["memory_mb"] = round(entry["memory_mb"] + int(digits) / 1024.0, 1)
            entry["instances"] += 1
    except Exception as e:
        log(f"process memory enumeration failed: {e}")
    return rows


def _startup_enabled_flag(scope: str, name: str) -> Optional[bool]:
    if winreg is None:
        return None
    root, path = STARTUP_APPROVED[scope]
    try:
        with winreg.OpenKey(_root_const(root), path, 0, winreg.KEY_READ) as k:
            raw, _typ = winreg.QueryValueEx(k, name)
            if not raw:
                return True
            # Gerenciador de Tarefas: byte 0 par (2, 6) = ligado; ímpar (3, 7) = desligado.
            return int(raw[0]) % 2 == 0
    except FileNotFoundError:
        return True  # no approval record at all means Windows still runs it
    except OSError:
        return True
    except Exception:
        return None


def startup_items() -> Dict[str, Any]:
    """List startup entries with their real, currently measured footprint.

    Windows does not expose Task Manager's "startup impact" rating through any
    documented API, so the app does not reproduce that label. What it shows
    instead is measurable: whether the program is running right now and how much
    memory it is using at this moment.
    """
    if os.name != "nt" or winreg is None:
        return {"ok": False, "supported": False, "reason": "Disponível só no Windows.", "items": []}
    # The top-8 process list is not enough here: a startup app can be running and
    # still not be one of the heaviest processes, which would show an empty
    # footprint for something that is measurably resident. Read every process.
    running = _all_process_memory()
    procs = set(running.keys())
    items: List[Dict[str, Any]] = []
    for scope, (root, path) in STARTUP_RUN_KEYS.items():
        try:
            with winreg.OpenKey(_root_const(root), path, 0, winreg.KEY_READ) as k:
                idx = 0
                while True:
                    try:
                        name, value, _typ = winreg.EnumValue(k, idx)
                    except OSError:
                        break
                    idx += 1
                    command = str(value or "")
                    exe = ""
                    m = re.search(r'"([^"]+\.exe)"|([A-Za-z]:\\[^",]+?\.exe)', command, re.I)
                    if m:
                        exe = os.path.basename(m.group(1) or m.group(2) or "")
                    low = exe.lower()
                    proc = running.get(low)
                    if proc is None and low.endswith(".exe"):
                        # Some Run entries point at an updater stub while the real
                        # resident process uses the product name (Discord/Update.exe).
                        stem = low[:-4]
                        proc = running.get(stem + "64.exe") or running.get(stem)
                    items.append({
                        "scope": scope,
                        "scope_label": "Este usuário" if scope == "HKCU_RUN" else "Todos os usuários",
                        "name": name,
                        "command": command[:300],
                        "exe": exe,
                        "enabled": _startup_enabled_flag(scope, name),
                        "running": bool(proc) or (low in procs),
                        "memory_mb": (proc or {}).get("memory_mb"),
                        "admin_required": scope.startswith("HKLM"),
                    })
        except FileNotFoundError:
            continue
        except Exception as e:
            log(f"startup enumeration failed for {scope}: {e}")
    items.sort(key=lambda x: (-(x.get("memory_mb") or 0), x["name"].lower()))
    measured = [x for x in items if x.get("memory_mb")]
    return {
        "ok": True, "supported": True, "items": items,
        "total": len(items),
        "enabled_count": sum(1 for x in items if x.get("enabled")),
        "measured_mb": round(sum(float(x.get("memory_mb") or 0) for x in measured), 1),
        "checked_at": _ts(),
        "policy": "O AZOR nunca desativa itens de inicialização em massa. Cada item so muda com um clique seu, e a alteração usa o mesmo registro de aprovação do Gerenciador de Tarefas, que e reversível.",
        "impact_note": "O Windows não publica a nota de impacto do Gerenciador de Tarefas por API. Em vez de inventar uma, o AZOR mostra o que da para medir agora: se o programa esta em execução e quanta memória ele esta usando neste momento.",
    }


def set_startup_item_enabled(scope: str, name: str, enabled: bool) -> Tuple[bool, str]:
    """Flag one startup entry, then re-read it before reporting success."""
    if os.name != "nt" or winreg is None:
        return False, "Disponivel somente no Windows."
    if scope not in STARTUP_APPROVED:
        return False, "Origem de inicialização desconhecida."
    name = str(name or "").strip()
    if not name:
        return False, "Item de inicialização não informado."
    if scope.startswith("HKLM") and not is_admin():
        return False, "Itens de 'Todos os usuários' exigem executar o AZOR como administrador."
    capture_restore_point()
    root, path = STARTUP_APPROVED[scope]
    blob = bytes([2 if enabled else 3] + [0] * 11)
    try:
        with winreg.CreateKeyEx(_root_const(root), path, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_BINARY, blob)
    except Exception as e:
        return False, f"Não foi possível alterar '{name}': {e}"
    got = _startup_enabled_flag(scope, name)
    ok = (got is True) if enabled else (got is False)
    verb = "reativado" if enabled else "desativado"
    return ok, (f"'{name}' {verb} na inicialização e confirmado por releitura."
                if ok else f"A alteração de '{name}' foi gravada, mas a releitura não confirmou o novo estado.")






# ==================== BIOS COPILOT (GUIADO, NUNCA AUTOMATICO) ====================
# The app still refuses to write firmware. What it adds here is the best guided
# experience it can honestly offer: it names the vendor's own menu path, keeps a
# checklist the user ticks off, and then re-reads Windows to confirm - or fail to
# confirm - what actually changed after the reboot.

BIOS_CHECKLIST_FILE = DATA_DIR / "bios_checklist.json"

# Menu paths as the vendors label them in their mainstream UEFI builds. Exact
# wording moves between BIOS revisions, which is why every entry ships with the
# alternative names the same option is known by.
BIOS_VENDOR_GUIDE = {
    "asus": {
        "label": "ASUS / ROG / TUF",
        "enter": "Ligue o PC e pressione DEL (ou F2) repetidamente. Dentro do utilitario, pressione F7 para sair do EZ Mode e entrar no Advanced Mode.",
        "memory": "Ai Tweaker > Ai Overclock Tuner > selecione XMP I / XMP II (Intel) ou D.O.C.P. / EXPO (AMD).",
        "rebar": "Advanced > PCI Subsystem Settings > ative Above 4G Decoding e depois Re-Size BAR Support.",
        "save": "Pressione F10 para salvar e reiniciar.",
    },
    "msi": {
        "label": "MSI",
        "enter": "Ligue o PC e pressione DEL repetidamente. Pressione F7 para alternar para o modo Advanced do Click BIOS.",
        "memory": "OC > Extreme Memory Profile (XMP) (Intel) ou A-XMP / EXPO (AMD) > selecione o Profile 1.",
        "rebar": "Settings > Advanced > PCI Subsystem Settings > ative Above 4G Memory e Re-Size BAR Support.",
        "save": "Pressione F10 para salvar e reiniciar.",
    },
    "gigabyte": {
        "label": "Gigabyte / AORUS",
        "enter": "Ligue o PC e pressione DEL repetidamente. Se abrir no Easy Mode, pressione F2 para ir ao Advanced Mode.",
        "memory": "Tweaker > Extreme Memory Profile (X.M.P.) (Intel) ou EXPO (AMD) > Profile1.",
        "rebar": "Settings > IO Ports > ative Above 4G Decoding e depois Re-Size BAR Support.",
        "save": "Pressione F10 para salvar e reiniciar.",
    },
    "asrock": {
        "label": "ASRock",
        "enter": "Ligue o PC e pressione F2 (ou DEL) repetidamente.",
        "memory": "OC Tweaker > DRAM Configuration > Load XMP Setting (Intel) ou EXPO (AMD).",
        "rebar": "Advanced > PCI Configuration > ative Above 4G Decoding e Re-Size BAR Support.",
        "save": "Pressione F10 para salvar e reiniciar.",
    },
    "generic": {
        "label": "Outro fabricante",
        "enter": "No POST, pressione a tecla de setup indicada na tela (normalmente DEL, F2 ou F10) e procure o modo Advanced.",
        "memory": "Procure por XMP, DOCP, EXPO ou 'Memory Profile' na secao de overclock/tweaker e selecione o perfil 1.",
        "rebar": "Procure Above 4G Decoding e Resizable BAR na secao de PCI/PCIe. Above 4G Decoding precisa vir primeiro.",
        "save": "Salve as alterações e reinicie (normalmente F10).",
    },
}


def _bios_vendor_key(manufacturer: Any) -> str:
    text = str(manufacturer or "").lower()
    for key in ("asus", "msi", "gigabyte", "asrock"):
        if key in text:
            return key
    if "micro-star" in text:
        return "msi"
    if "asustek" in text:
        return "asus"
    return "generic"


def load_bios_checklist() -> Dict[str, Any]:
    data = _safe_json_read(BIOS_CHECKLIST_FILE, {})
    return data if isinstance(data, dict) else {}


def set_bios_checklist(key: str, done: bool) -> Dict[str, Any]:
    """Record that the user says they changed a firmware option.

    The mark itself proves nothing, so the reading Windows gives right now is
    stored alongside it. After the reboot the UI can compare the two and show
    whether the change actually took effect.
    """
    key = str(key or "").strip()
    if key not in ("memory_profile", "resizable_bar", "above_4g"):
        return {"ok": False, "detail": "Item de BIOS desconhecido."}
    data = load_bios_checklist()
    if done:
        data[key] = {
            "marked": True,
            "marked_at": _ts(),
            "reading_when_marked": _bios_live_readings().get(key),
        }
    else:
        data.pop(key, None)
    _safe_json_write(BIOS_CHECKLIST_FILE, data)
    return {"ok": True, "detail": "Checklist da BIOS atualizado.", "checklist": data}


def _bios_live_readings() -> Dict[str, Any]:
    """What Windows can actually prove about firmware settings, right now."""
    hw = bios_snapshot()
    ram = hw.get("RAM") or []
    if isinstance(ram, dict):
        ram = [ram]
    configured = [int(x.get("ConfiguredClockSpeed") or 0) for x in ram if isinstance(x, dict)]
    rated = [int(x.get("Speed") or 0) for x in ram if isinstance(x, dict)]
    memory: Dict[str, Any] = {
        "configured_mts": max(configured) if configured else None,
        "rated_mts": max(rated) if rated else None,
        "at_rated_speed": None,
    }
    if memory["configured_mts"] and memory["rated_mts"]:
        memory["at_rated_speed"] = memory["configured_mts"] >= memory["rated_mts"]
    return {
        "memory_profile": memory,
        "resizable_bar": {"reported": hw.get("ResizableBAR")},
        "above_4g": {"reported": None},
    }


def bios_copilot() -> Dict[str, Any]:
    """Guided, vendor-aware BIOS assistant. Reads and explains; never writes."""
    hw = bios_snapshot()
    if not hw.get("supported"):
        return {"ok": False, "supported": False, "reason": str(hw.get("reason") or "Hardware não pode ser lido."), "steps": []}
    board = hw.get("BaseBoard") or {}
    cpu = hw.get("CPU") or {}
    if isinstance(cpu, list):
        cpu = cpu[0] if cpu else {}
    vendor_key = _bios_vendor_key(board.get("Manufacturer"))
    guide = BIOS_VENDOR_GUIDE[vendor_key]
    cpu_vendor = str(cpu.get("Manufacturer") or cpu.get("Name") or "").lower()
    amd = "amd" in cpu_vendor
    memory_feature = "EXPO / D.O.C.P." if amd else "XMP"

    readings = _bios_live_readings()
    checklist = load_bios_checklist()
    mem = readings["memory_profile"]

    if mem["at_rated_speed"] is True:
        # Running above the SPD/JEDEC base speed is exactly what an active
        # XMP/EXPO profile looks like from Windows, so say that, not "equal to".
        if mem["configured_mts"] > mem["rated_mts"]:
            mem_status, mem_detail = "confirmed", f"A memória roda a {mem['configured_mts']} MT/s, acima dos {mem['rated_mts']} MT/s da tabela base dos módulos. Rodar acima da base e exatamente como um perfil {memory_feature} ativo aparece para o Windows."
        else:
            mem_status, mem_detail = "confirmed", f"A memória já roda a {mem['configured_mts']} MT/s, o mesmo valor nominal lido dos módulos."
    elif mem["at_rated_speed"] is False:
        mem_status, mem_detail = "action", f"Os módulos anunciam até {mem['rated_mts']} MT/s, mas o Windows le {mem['configured_mts']} MT/s. O perfil de memória provavelmente esta desligado."
    else:
        mem_status, mem_detail = "unknown", "O Windows não retornou a velocidade nominal e a configurada desta memória, então o AZOR não afirma nada sobre o perfil."

    rebar_reported = readings["resizable_bar"]["reported"]
    if str(rebar_reported).lower() in ("enabled", "yes"):
        rebar_status, rebar_detail = "confirmed", "O driver da GPU reporta Resizable BAR como ativo."
    elif str(rebar_reported).lower() in ("disabled", "no"):
        rebar_status, rebar_detail = "action", "O driver da GPU reporta Resizable BAR como desativado."
    else:
        rebar_status, rebar_detail = "unknown", "Nenhuma GPU deste PC expos um estado confiável de Resizable BAR, então o AZOR não adivinha o valor."

    def step(key, name, status, detail, path, why, risk):
        mark = checklist.get(key) or {}
        return {
            "key": key, "name": name, "status": status, "detail": detail,
            "path": path, "why": why, "risk": risk,
            "automatic": False,
            "marked": bool(mark.get("marked")),
            "marked_at": mark.get("marked_at"),
            "verified_after_mark": (status == "confirmed") if mark.get("marked") else None,
        }

    steps = [
        step("memory_profile", f"Perfil de memória ({memory_feature})", mem_status, mem_detail,
             guide["memory"],
             "Sem o perfil ativo a memória roda na velocidade JEDEC de segurança, bem abaixo do que você comprou. E o ajuste de BIOS com maior efeito real em 1% low.",
             "medium"),
        step("above_4g", "Above 4G Decoding", "prereq", "Pré-requisito do Resizable BAR. O Windows não expõe esse valor, então ele so pode ser confirmado na própria BIOS.",
             guide["rebar"],
             "O Resizable BAR não aparece ou não funciona enquanto o Above 4G Decoding estiver desligado.",
             "low"),
        step("resizable_bar", "Resizable BAR", rebar_status, rebar_detail,
             guide["rebar"],
             "Permite que a CPU enxergue toda a VRAM de uma vez. O ganho varia por jogo e por GPU: em alguns títulos ajuda, em outros não muda nada.",
             "low"),
    ]

    return {
        "ok": True, "supported": True,
        "vendor": vendor_key, "vendor_label": guide["label"],
        "board": {"manufacturer": str(board.get("Manufacturer") or ""), "product": str(board.get("Product") or "")},
        "bios": hw.get("BIOS") or {},
        "cpu": {"name": str(cpu.get("Name") or ""), "amd": amd},
        "memory_feature": memory_feature,
        "enter": guide["enter"], "save": guide["save"],
        "steps": steps,
        "readings": readings,
        "checklist": checklist,
        "policy": "O AZOR não escreve firmware por métodos genéricos. Um valor de BIOS gravado errado pode impedir o PC de ligar, e nenhum ganho de FPS justifica esse risco no PC de um cliente. Por isso aqui ele mostra o caminho exato do seu fabricante, guarda o que você já fez e confirma depois do reboot o que o Windows conseguir reler.",
        "accuracy_note": "Os nomes dos menus mudam entre versoes de BIOS. Se um item estiver com outro nome na sua placa, procure o termo equivalente indicado acima ou consulte o manual do modelo.",
        "generated_at": _ts(),
    }












def revert_optimization(task_id: str) -> Dict[str,Any]:
    """Desfaz um único tweak aplicado, a partir do baseline anterior ao AZOR."""
    try:
        from azor_modules.engine import revert_task
        result = revert_task(str(task_id or ""))
    except Exception as e:
        log(f"Individual revert failed: {e}")
        return {"ok":False,"id":str(task_id or ""),"detail":str(e)}
    invalidate_cache()
    return result










# ---------------------------------------------------------------------------
# A distancia entre "otimizado" e "100% otimizado" tem um nome: administrador
# ---------------------------------------------------------------------------
#
# Medido nesta maquina, sem elevacao, no perfil competitivo:
#
#     27 tweaks  bloqueados por falta de administrador   (39% do catalogo)
#     17 tweaks  ja estavam corretos                     (sucesso, nao falha)
#      3 tweaks  preservados por decisao tecnica
#
# Os 27 nao sao sobras: sao MMCSS, resolucao global de timer, separacao de
# prioridade do Win32, throttling de rede, HAGS, MSI da GPU e do disco, NTFS,
# servicos, TDR, MPO e Nagle - boa parte do que de fato move FPS e latencia.
#
# O app sabia disso e escondia bem: cada um virava um "nao aplicavel" discreto no
# meio de uma lista longa, e o BOOST terminava anunciando "39 aplicadas" com cara
# de sucesso. O cliente ficava com 61% do produto achando que tinha 100%.
#
# Esta funcao existe para que o numero apareca inteiro, na tela inicial, com o
# botao de resolver do lado. Ela conta o catalogo de verdade - nao ha numero
# fixo aqui que possa envelhecer quando o catalogo crescer.












# ===========================================================================
# Detector de gargalo
#
# Duas leituras aqui nao existiam no AZOR e sao das que mais valem FPS por
# minuto de trabalho do usuario, justamente porque quase ninguem olha:
#   1. o monitor rodando abaixo da propria taxa maxima - FPS de graca, sem
#      tocar em nada do sistema;
#   2. a RAM abaixo da frequencia gravada nos pentes (XMP/EXPO desligado) ou
#      em canal unico.
# As duas saem de leitura, nunca de suposicao: quando o Windows nao responde,
# o campo volta como "nao reportado" em vez de um numero inventado.
# ===========================================================================
ENUM_CURRENT_SETTINGS = -1
CCHDEVICENAME = 32
CCHFORMNAME = 32


class _POINTL(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _DEVMODEW(ctypes.Structure):
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * CCHDEVICENAME),
        ("dmSpecVersion", ctypes.c_uint16),
        ("dmDriverVersion", ctypes.c_uint16),
        ("dmSize", ctypes.c_uint16),
        ("dmDriverExtra", ctypes.c_uint16),
        ("dmFields", ctypes.c_uint32),
        ("dmPosition", _POINTL),
        ("dmDisplayOrientation", ctypes.c_uint32),
        ("dmDisplayFixedOutput", ctypes.c_uint32),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * CCHFORMNAME),
        ("dmLogPixels", ctypes.c_uint16),
        ("dmBitsPerPel", ctypes.c_uint32),
        ("dmPelsWidth", ctypes.c_uint32),
        ("dmPelsHeight", ctypes.c_uint32),
        ("dmDisplayFlags", ctypes.c_uint32),
        ("dmDisplayFrequency", ctypes.c_uint32),
        ("dmICMMethod", ctypes.c_uint32),
        ("dmICMIntent", ctypes.c_uint32),
        ("dmMediaType", ctypes.c_uint32),
        ("dmDitherType", ctypes.c_uint32),
        ("dmReserved1", ctypes.c_uint32),
        ("dmReserved2", ctypes.c_uint32),
        ("dmPanningWidth", ctypes.c_uint32),
        ("dmPanningHeight", ctypes.c_uint32),
    ]


def display_refresh_state() -> Dict[str, Any]:
    """Taxa de atualização atual contra a maxima que o modo atual suporta.

    Um monitor de 144 Hz ligado a 60 Hz e a otimizacao mais barata que existe:
    não mexe em nada do Windows e devolve mais que a maioria dos tweaks juntos.
    Não abre processo nenhum - EnumDisplaySettings já responde tudo.
    """
    out: Dict[str, Any] = {"ok": False, "current_hz": None, "max_hz": None,
                           "width": None, "height": None, "below_max": False, "detail": "não reportado"}
    if os.name != "nt":
        return out
    try:
        user32 = ctypes.windll.user32
        current = _DEVMODEW()
        current.dmSize = ctypes.sizeof(_DEVMODEW)
        if not user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(current)):
            return out
        width, height = int(current.dmPelsWidth), int(current.dmPelsHeight)
        current_hz = int(current.dmDisplayFrequency)
        best = current_hz
        index = 0
        while index < 4096:
            mode = _DEVMODEW()
            mode.dmSize = ctypes.sizeof(_DEVMODEW)
            if not user32.EnumDisplaySettingsW(None, index, ctypes.byref(mode)):
                break
            index += 1
            if int(mode.dmPelsWidth) == width and int(mode.dmPelsHeight) == height:
                best = max(best, int(mode.dmDisplayFrequency))
        out.update({
            "ok": True, "current_hz": current_hz, "max_hz": best,
            "width": width, "height": height,
            "below_max": bool(best > current_hz + 1),
            "modes_checked": index,
        })
        if out["below_max"]:
            out["detail"] = (f"O monitor esta em {current_hz} Hz, mas aceita {best} Hz "
                             f"em {width}x{height}. Windows: Configurações > Sistema > Video > "
                             f"Video avançado > Taxa de atualização.")
        else:
            out["detail"] = f"{current_hz} Hz em {width}x{height} - já e a maior taxa deste modo."
        return out
    except Exception as e:
        log(f"display refresh read failed: {e}")
        out["detail"] = f"não reportado ({e})"
        return out


def memory_channels_state(force: bool = False) -> Dict[str, Any]:
    """Frequencia configurada contra a gravada no pente, e quantos pentes.

    ConfiguredClockSpeed abaixo de Speed e a assinatura de XMP/EXPO desligado
    no BIOS. Em jogo limitado por CPU isso costuma ser o maior item isolado da
    lista - e o AZOR não pode corrigir sozinho, porque não escreve firmware.
    """
    def read() -> Dict[str, Any]:
        out: Dict[str, Any] = {"ok": False, "sticks": 0, "rated_mhz": None, "configured_mhz": None,
                               "xmp_off": False, "single_channel": None, "total_gb": None,
                               "detail": "não reportado"}
        if os.name != "nt":
            return out
        try:
            data = powershell_json(
                "Get-CimInstance Win32_PhysicalMemory -ErrorAction Stop | "
                "Select-Object Capacity,Speed,ConfiguredClockSpeed,DeviceLocator,BankLabel")
        except Exception as e:
            out["detail"] = f"não reportado ({e})"
            return out
        if isinstance(data, dict):
            data = [data]
        rows = [x for x in (data or []) if isinstance(x, dict)]
        if not rows:
            return out
        def as_int(v):
            try:
                return int(v)
            except Exception:
                return None
        rated = [as_int(r.get("Speed")) for r in rows]
        configured = [as_int(r.get("ConfiguredClockSpeed")) for r in rows]
        rated = [x for x in rated if x]
        configured = [x for x in configured if x]
        total = sum((as_int(r.get("Capacity")) or 0) for r in rows)
        banks = {str(r.get("BankLabel") or r.get("DeviceLocator") or "") for r in rows}
        out.update({
            "ok": True,
            "sticks": len(rows),
            "rated_mhz": max(rated) if rated else None,
            "configured_mhz": max(configured) if configured else None,
            "total_gb": round(total / (1024 ** 3), 1) if total else None,
            "slots": sorted(banks),
        })
        if out["rated_mhz"] and out["configured_mhz"]:
            out["xmp_off"] = out["configured_mhz"] < out["rated_mhz"] - 20
        out["single_channel"] = len(rows) < 2
        parts = []
        if out["configured_mhz"]:
            parts.append(f"rodando a {out['configured_mhz']} MHz")
        if out["xmp_off"]:
            parts.append(f"mas os pentes são de {out['rated_mhz']} MHz - XMP/EXPO parece desligado no BIOS")
        if out["single_channel"]:
            parts.append("um único pente instalado (canal único)")
        out["detail"] = "; ".join(parts) if parts else "memória na frequência esperada"
        return out

    return cached_reading("memory_channels", 900.0, read, force=force)


def bottleneck_report(force: bool = False) -> Dict[str, Any]:
    """Onde esta o limite deste PC, com o cuidado de não chutar.

    Em repouso da para afirmar com honestidade so os limites ESTRUTURAIS - os
    que existem independentemente de carga. Dizer "seu gargalo e a CPU" olhando
    para uma máquina parada seria adivinhação; esse veredito depende de medição
    com o jogo aberto, e o relatório diz isso em vez de inventar.
    """
    findings: List[Dict[str, Any]] = []
    profile = hardware_profile()
    monitor = MONITOR_SAMPLER.request()
    display = display_refresh_state()
    memory = memory_channels_state(force=force)

    def add(severity: str, area: str, title: str, detail: str, action: str = "", gain: str = "") -> None:
        findings.append({"severity": severity, "area": area, "title": title,
                         "detail": detail, "action": action, "gain": gain})

    if display.get("below_max"):
        add("high", "Monitor", f"Monitor em {display['current_hz']} Hz de {display['max_hz']} Hz possiveis",
            display.get("detail", ""),
            "Windows: Configurações > Sistema > Video > Video avançado > Taxa de atualização.",
            f"+{display['max_hz'] - display['current_hz']} Hz de teto, sem tocar em mais nada")

    if memory.get("xmp_off"):
        add("high", "Memoria", f"RAM a {memory['configured_mhz']} MHz com pentes de {memory['rated_mhz']} MHz",
            "XMP/EXPO parece desligado no BIOS. Em jogo limitado por CPU esse costuma ser o maior item "
            "isolado da lista.",
            "Ative o perfil XMP/EXPO no BIOS. O AZOR não escreve firmware: o BIOS Copiloto mostra o "
            "caminho exato do seu fabricante e confirma depois do reboot.",
            "tipicamente de 5% a 15% em jogo limitado por CPU")

    if memory.get("single_channel"):
        add("high" if not profile.get("discrete_gpu") else "medium", "Memoria",
            "Um único pente de RAM (canal único)",
            "Com um pente so, a banda de memória cai pela metade. Em vídeo integrado o impacto e grande, "
            "porque a GPU usa a mesma memória.",
            "Instalar um segundo pente igual, no slot que o manual manda para dual channel.",
            "20% a 40% em vídeo integrado; menos com GPU dedicada")

    ram_gb = profile.get("ram_gb")
    if isinstance(ram_gb, (int, float)) and ram_gb and ram_gb < 12:
        add("high", "Memoria", f"{ram_gb} GB de RAM",
            "Abaixo de 12 GB, jogo moderno com navegador aberto passa a usar arquivo de paginacao, e "
            "isso aparece como travadinha, não como FPS baixo.",
            "Fechar apps pesados antes de jogar; a solucao real e mais memória.",
            "")

    if not profile.get("discrete_gpu"):
        add("medium", "GPU", "Nenhuma GPU dedicada detectada",
            "O vídeo integrado divide memória e energia com a CPU. Aqui, RAM em dual channel e resolução "
            "valem mais que qualquer ajuste de registro.", "", "")

    ram_now = (monitor.get("ram") or {}).get("percent")
    if isinstance(ram_now, (int, float)) and ram_now >= 85:
        add("medium", "Memoria", f"RAM em {ram_now}% agora, com o jogo fechado",
            "Comecar a partida já perto do limite e receita de stutter.",
            "Veja os maiores consumidores no Monitoramento e no Hardware.", "")

    disk = monitor.get("disk") or {}
    if isinstance(disk.get("percent"), (int, float)) and disk["percent"] >= 92:
        add("high", "Disco", f"Disco do sistema em {disk['percent']}% de uso",
            "Disco quase cheio derruba desempenho de escrita e atrapalha shader cache e paginacao.",
            "Liberar espaco no disco do Windows.", "")

    # "O PC ficou lento para abrir programa" tem quase sempre a mesma causa
    #
    # SysMain e Prefetcher sao as duas pecas que fazem o Windows pre-carregar o
    # que voce usa todo dia. Desligar os dois e o conselho mais repetido dos
    # scripts de otimizacao - e o motivo numero um de o cliente dizer que o PC
    # piorou depois de "otimizar".
    #
    # Este achado vem ANTES dos outros de propostito: nenhum tweak de FPS
    # compensa esperar a janela do navegador abrir.
    _launch = app_launch_cache_state()
    if _launch.get("broken"):
        add("high", "Windows",
            "O Windows parou de pré-carregar os programas que você usa",
            "SysMain (Superfetch) e o Prefetcher estão desligados. São eles que deixam o "
            "aplicativo do dia a dia abrir rápido a partir da segunda vez. Desligados, TODO "
            "programa abre do zero — e é isso que dá a sensação de PC lento, mesmo com um "
            "SSD rápido. Não devolve FPS: o SysMain nem roda durante a partida, porque cede "
            "prioridade sob carga.",
            "Aplicar o reparo 'Religar o pré-carregamento de programas' (precisa do AZOR "
            "aberto como administrador).", "Tempo até a janela do programa aparecer")

    # CPU hibrida: onde o Windows 10 custa 1% low de verdade
    #
    # A partir da 12a geracao a Intel mistura nucleos P (rapidos) e E
    # (eficientes). Quem decide qual thread vai para qual nucleo e o Thread
    # Director, e ele SO existe no Windows 11 - o Windows 10 nao tem essa camada
    # e distribui as threads do jogo sem saber que metade dos nucleos e lenta.
    #
    # O resultado nao aparece no FPS medio, aparece exatamente no 1% low: o
    # quadro que caiu num E-core chega tarde. Nenhum tweak de registro conserta
    # isso, entao ele entra como achado ESTRUTURAL, na mesma prateleira do
    # monitor a 60 Hz: o AZOR diz o que e, e nao finge resolver.
    topo = cpu_topology()
    if topo.get("hybrid"):
        pe = f"{topo.get('performance_cores')}P + {topo.get('efficiency_cores')}E"
        if not is_windows_11():
            add("high", "CPU",
                f"Processador híbrido ({pe}) rodando no Windows 10",
                "O Thread Director, que decide se a thread do jogo vai para um núcleo rápido (P) "
                "ou lento (E), só existe no Windows 11. No Windows 10 parte das threads da partida "
                "cai nos núcleos de eficiência, e isso aparece no 1% low, não na média de FPS.",
                "Atualizar para o Windows 11 é o único caminho real aqui. Nenhum ajuste de "
                "registro substitui o agendador.", "1% low")
        else:
            add("low", "CPU",
                f"Processador híbrido detectado ({pe})",
                "O Windows 11 distribui as threads da partida com o Thread Director. O AZOR evita "
                "de propósito qualquer ajuste antigo de afinidade ou de quantum que atrapalhe "
                "esse agendamento.",
                "", "")

    gpu = monitor.get("gpu") or {}
    if isinstance(gpu.get("temp_c"), (int, float)) and gpu["temp_c"] >= 80:
        add("medium", "Termico", f"GPU a {gpu['temp_c']} °C sem jogo aberto",
            "Temperatura alta em repouso indica fluxo de ar ou limpeza, não configuração. "
            "Software nenhum resolve isso.", "", "")

    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda x: order.get(x["severity"], 3))

    structural = [f for f in findings if f["severity"] == "high"]
    if structural:
        verdict = structural[0]["area"]
        headline = structural[0]["title"]
    elif findings:
        verdict = findings[0]["area"]
        headline = findings[0]["title"]
    else:
        verdict = "Configuracao"
        headline = "Nenhum limite estrutural encontrado"

    return {
        "ok": True,
        "verdict_area": verdict,
        "headline": headline,
        "findings": findings,
        "display": display,
        "memory": memory,
        "profile": {"label": profile.get("label"), "tier": profile.get("tier"),
                    "cpu": profile.get("cpu"), "gpus": profile.get("gpus"),
                    "ram_gb": ram_gb, "discrete_gpu": profile.get("discrete_gpu")},
        "live_note": ("Este veredito cobre os limites estruturais, que valem com o PC parado. "
                      "Dizer qual peca esta segurando o FPS durante a partida exige medir com o jogo "
                      "aberto: use o Monitor de Jogo para coletar antes e depois com frametime real."),
    }




# ==================== V5 CLIENT / LATENCY HELPERS ====================

# ---------------------------------------------------------------------------
# Timer de 0,5 ms: ativo nao e a mesma coisa que ALCANCANDO O JOGO
# ---------------------------------------------------------------------------
#
# Ate o Windows 10 1909, um processo que pedia timer de 0,5 ms mudava o timer do
# sistema INTEIRO. A partir do 2004 a Microsoft tornou o pedido valido apenas
# para o processo que pediu - o resto da maquina continua no timer grosso.
#
# Consequencia direta, e e um placebo classico: o AZOR pede 0,5 ms, a API
# confirma 0,5 ms, a tela mostra "Timer ativo - 0,5 ms" ... e o Fortnite continua
# agendado no timer padrao. O ganho fica todo dentro do proprio otimizador.
#
# Quem devolve o comportamento antigo e a chave GlobalTimerResolutionRequests,
# que existe no catalogo (tweak `global_timer_resolution`) e EXIGE REINICIAR
# para valer. O catalogo ja explicava essa dependencia; o que faltava era o
# status olhar para ela antes de dizer que o timer esta valendo.
#
# Agora o status carrega o ALCANCE, e a tela pode dizer a verdade inteira:
#   system  - a chave esta ligada: o pedido vale para a maquina toda
#   pending - a chave foi gravada mas o PC ainda nao reiniciou
#   process - a chave esta desligada: vale so dentro do AZOR (nao ajuda o jogo)

TIMER_GLOBAL_KEY = (r"SYSTEM\CurrentControlSet\Control\Session Manager\Kernel",
                    "GlobalTimerResolutionRequests")


def timer_global_scope() -> Dict[str, Any]:
    """O pedido de timer alcanca o sistema, ou morre dentro do próprio app?"""
    out = {"scope": "process", "key_set": False, "needs_restart": False,
           "reaches_the_game": False,
           "detail": ("O pedido de 0,5 ms vale apenas dentro do AZOR. Desde o Windows 10 "
                      "2004 o timer é por processo, então isso NÃO alcança o jogo.")}
    if os.name != "nt":
        return out
    try:
        entry = reg_read("HKLM", TIMER_GLOBAL_KEY[0], TIMER_GLOBAL_KEY[1])
        out["key_set"] = bool(entry.get("exists")) and int(entry.get("value") or 0) == 1
        if not out["key_set"]:
            return out
        # A chave e lida pelo Session Manager no boot. Gravada agora, so vale no
        # proximo inicio - e ate la o timer continua sendo por processo.
        applied_boot = _timer_key_active_since_boot()
        if applied_boot:
            out.update({"scope": "system", "reaches_the_game": True,
                        "detail": "O timer do AZOR vale para o sistema inteiro, incluindo o jogo."})
        else:
            out.update({"scope": "pending", "needs_restart": True,
                        "detail": ("A chave global já está gravada, mas só passa a valer no "
                                   "próximo reinício. Até lá o timer vale só dentro do AZOR.")})
    except Exception as exc:
        log_debug(f"timer_global_scope: {exc}")
    return out


def _timer_key_active_since_boot() -> bool:
    """A chave global já estava ligada quando esta sessão do Windows subiu?

    Guardamos o boot_id no momento em que a chave foi vista ligada pela primeira
    vez. Se o boot mudou desde então, o Windows já leu a chave no arranque.
    """
    try:
        state = _safe_json_read(DATA_DIR / "timer_scope.json", {}) or {}
        now_boot = boot_id()
        seen_boot = state.get("seen_boot")
        if seen_boot and seen_boot != now_boot:
            return True
        if not seen_boot:
            _cache_json_write(DATA_DIR / "timer_scope.json", {"seen_boot": now_boot})
        return False
    except Exception:
        return False


def latency_engine_status() -> Dict[str,Any]:
    q=TIMER_SESSION.query()
    # Sem isto a tela dizia "0,5 ms ativo" mesmo quando o pedido nao saia do
    # proprio processo. Ativo e alcance sao duas perguntas diferentes.
    try:
        q["global"]=timer_global_scope()
    except Exception: pass
    return q

def set_latency_target(ms: float) -> Tuple[bool,str]:
    target=0.5 if float(ms)<=0.75 else 1.0
    st=load_settings(); st["latency_engine_autostart"]=True; st["latency_target_ms"]=target; save_settings(st)
    return TIMER_SESSION.enable(target)


def disable_latency_engine() -> Tuple[bool,str]:
    st=load_settings(); st["latency_engine_autostart"]=False; save_settings(st)
    ok,detail=TIMER_SESSION.disable()
    return ok,"Timer liberado."

def _runtime_pythonw() -> Path:
    bundled = APP_ROOT.parent / "runtime" / "pythonw.exe"
    if bundled.exists():
        return bundled
    private = Path(os.environ.get("LOCALAPPDATA",str(APP_ROOT))) / "AzorOptimization" / "runtime" / "pythonw.exe"
    if private.exists():
        return private
    current = Path(sys.executable)
    sibling = current.with_name("pythonw.exe")
    return sibling if sibling.exists() else current









def gpu_throttle_reasons() -> Dict[str, Any]:
    """Ask the NVIDIA driver why it is holding clocks down, if it will say.

    nvidia-smi exposes the real throttle flags. AMD and Intel have no equivalent
    offline query here, so for those the answer is "unavailable", never a guess.
    """
    exe = shutil.which("nvidia-smi")
    if not exe:
        return {"available": False, "vendor": None, "reasons": []}
    fields = [
        "clocks_throttle_reasons.hw_thermal_slowdown",
        "clocks_throttle_reasons.sw_thermal_slowdown",
        "clocks_throttle_reasons.hw_power_brake_slowdown",
        "clocks_throttle_reasons.sw_power_cap",
    ]
    labels = {
        fields[0]: "Redução térmica por hardware (a GPU atingiu o limite de temperatura)",
        fields[1]: "Redução térmica por software (driver reduzindo clock por calor)",
        fields[2]: "Freio de energia por hardware (limite elétrico da fonte/conector)",
        fields[3]: "Limite de potência do driver (power cap atingido)",
    }
    try:
        p = run_hidden([exe, "--query-gpu=" + ",".join(fields), "--format=csv,noheader"], timeout=6)
        if p.returncode != 0 or not (p.stdout or "").strip():
            return {"available": False, "vendor": "NVIDIA", "reasons": []}
        row = next(csv.reader([(p.stdout or "").splitlines()[0]]))
        active = []
        for field, value in zip(fields, [x.strip().lower() for x in row]):
            if value in ("active", "yes", "1"):
                active.append(labels[field])
        return {"available": True, "vendor": "NVIDIA", "reasons": active}
    except Exception as e:
        log(f"nvidia throttle query failed: {e}")
        return {"available": False, "vendor": "NVIDIA", "reasons": []}


def thermal_snapshot() -> Dict[str, Any]:
    """Temperatures and sustained-clock ratio, from whatever Windows exposes.

    Consumer CPU temperature is not readable through a documented Windows API
    without a kernel driver. The app therefore uses LibreHardwareMonitor or
    OpenHardwareMonitor if the user already has one running, then ACPI thermal
    zones, and otherwise reports that no sensor is available - it never fills the
    gap with an invented number.
    """
    result: Dict[str, Any] = {
        "cpu_temp_c": None, "cpu_temp_source": None,
        "gpu_temp_c": None, "gpu_name": None,
        "cpu_clock_mhz": None, "cpu_max_clock_mhz": None, "cpu_clock_ratio": None,
        "acpi_zones_c": [], "throttle": {"available": False, "reasons": []},
        "supported": os.name == "nt",
    }
    if os.name != "nt":
        return result

    hw = _hardware_monitor_snapshot()
    if hw.get("cpu_temp_c") is not None:
        result["cpu_temp_c"] = hw.get("cpu_temp_c")
        result["cpu_temp_source"] = hw.get("source")
    result["cpu_clock_mhz"] = hw.get("cpu_clock_mhz")

    gpu = _nvidia_snapshot()
    if gpu.get("available"):
        result["gpu_temp_c"] = gpu.get("temp_c")
        result["gpu_name"] = gpu.get("name")
    result["throttle"] = gpu_throttle_reasons()

    try:
        data = powershell_json(
            "$z=@(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature -ErrorAction SilentlyContinue|"
            "ForEach-Object{[math]::Round(($_.CurrentTemperature/10)-273.15,1)});"
            "$p=Get-CimInstance Win32_Processor|Select-Object -First 1 CurrentClockSpeed,MaxClockSpeed;"
            "[pscustomobject]@{Zones=$z;Current=$p.CurrentClockSpeed;Max=$p.MaxClockSpeed}",
            timeout=15,
        ) or {}
    except Exception:
        data = {}
    zones = data.get("Zones") or []
    if isinstance(zones, (int, float)):
        zones = [zones]
    result["acpi_zones_c"] = [z for z in zones if isinstance(z, (int, float)) and -20 < float(z) < 130]
    if result["cpu_temp_c"] is None and result["acpi_zones_c"]:
        result["cpu_temp_c"] = round(max(result["acpi_zones_c"]), 1)
        result["cpu_temp_source"] = "ACPI thermal zone"
    try:
        cur, mx = float(data.get("Current") or 0), float(data.get("Max") or 0)
        if result["cpu_clock_mhz"] is None and cur > 0:
            result["cpu_clock_mhz"] = cur
        result["cpu_max_clock_mhz"] = mx or None
        if cur > 0 and mx > 0:
            result["cpu_clock_ratio"] = round(cur / mx, 2)
    except Exception:
        pass
    result["sensor_note"] = (
        "Temperatura de CPU não tem API oficial do Windows sem driver de kernel. "
        "O AZOR usa LibreHardwareMonitor/OpenHardwareMonitor se você já tiver um aberto, "
        "depois as zonas termicas ACPI da placa, e se nenhum dos dois responder ele diz "
        "que não ha sensor em vez de estimar um valor."
    )
    return result





















# ==================== ARSENAL: BASELINE DERIVADO E ALVOS NOVOS ====================
#
# Tudo abaixo existe para uma frase: "reversivel" so pode ser dito quando o valor
# anterior esta guardado. Ate aqui, a lista do que era capturado (TRACKED_REGISTRY)
# era escrita a mao num lugar e as chaves gravadas pelos tweaks em outro. As duas
# ja divergiram uma vez. Com trinta tweaks novos, divergir de novo era questao de
# tempo -- entao a lista passou a ser DERIVADA do proprio catalogo: a uniao das
# chaves declaradas por todos os modulos E a captura.


def _module_declared_registry_keys() -> List[Tuple[str, str, str]]:
    """Toda chave que algum tweak declara escrever, lida do próprio catalogo.

    Importa tarde de proposito: azor_modules pede azor_core de volta, e um import
    no topo fecharia o ciclo.
    """
    out: List[Tuple[str, str, str]] = []
    try:
        from azor_modules import engine as _engine
        for module in _engine.MODULES:
            for entries in (getattr(module, "KEYS", {}) or {}).values():
                for item in entries:
                    if len(item) >= 3:
                        out.append((str(item[0]), str(item[1]), str(item[2])))
    except Exception as exc:
        log(f"Declared registry keys could not be read from the catalog: {exc}")
    return out


TCPIP_INTERFACES_PATH = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"
# Nagle: tres valores, por adaptador. O caminho depende do GUID da interface, que
# so existe nesta maquina - por isso estas chaves nao cabem numa lista estatica.
NAGLE_VALUES = ("TcpAckFrequency", "TCPNoDelay", "TcpDelAckTicks")


def tcpip_interface_guids() -> List[str]:
    """GUIDs das interfaces TCP/IP registradas neste PC."""
    if winreg is None or os.name != "nt":
        return []
    out: List[str] = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, TCPIP_INTERFACES_PATH, 0, winreg.KEY_READ) as k:
            index = 0
            while True:
                try:
                    out.append(winreg.EnumKey(k, index))
                except OSError:
                    break
                index += 1
    except Exception:
        return []
    return out


def _dynamic_registry_keys() -> List[Tuple[str, str, str]]:
    """Chaves cujo caminho so pode ser descoberto nesta máquina."""
    out: List[Tuple[str, str, str]] = []
    for guid in tcpip_interface_guids():
        path = TCPIP_INTERFACES_PATH + "\\" + guid
        for name in NAGLE_VALUES:
            out.append(("HKLM", path, name))
    # A flag de tela cheia do Fortnite mora numa chave cujo NOME e o caminho do
    # executavel - ou seja, so existe nesta maquina. Sem entrar aqui, o baseline
    # nao captura o estado anterior e a reversao falha com "sem baseline para:"
    # (foi exatamente o que aconteceu no primeiro teste desta tarefa).
    try:
        fort_exe = (detect_fortnite() or {}).get("exe")
        if fort_exe:
            out.append(("HKCU", APPCOMPAT_LAYERS, str(fort_exe)))
    except Exception:
        pass
    return out


def tracked_registry() -> List[Tuple[str, str, str]]:
    """A captura = lista base + tudo que o catalogo declara + chaves por máquina.

    Enquanto um tweak declarar as chaves que grava, ele e reversível por
    construcao. Não existe segunda lista para esquecer de atualizar.
    """
    seen = set()
    out: List[Tuple[str, str, str]] = []
    for root, path, name in list(TRACKED_REGISTRY) + _module_declared_registry_keys() + _dynamic_registry_keys():
        key = (str(root), str(path).casefold(), str(name).casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append((str(root), str(path), str(name)))
    return out


def baseline_backfill(section: str, value: Any) -> bool:
    """Grava uma secao que faltava no baseline, sem NUNCA sobrescrever o que já existe.

    Por que isto e honesto: um PC que capturou o baseline antes deste build não tem
    entrada para, digamos, o serviço DiagTrack. Mas nenhuma versão do AZOR jamais
    escreveu nesse serviço -- então o valor que esta la agora ainda e o valor
    anterior ao AZOR. Registrar isso agora captura o baseline verdadeiro daquele
    item. Sobrescrever um que já existe, não: aquele pode já ser pos-AZOR.
    """
    if not BASELINE_FILE.exists():
        return False
    try:
        data = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False
        if section in data and data.get(section) not in (None, {}, []):
            return False
        data[section] = value
        backfilled = data.setdefault("backfilled", {})
        if isinstance(backfilled, dict):
            backfilled[section] = _ts()
        BASELINE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        journal("baseline_backfill", section=section)
        return True
    except Exception as exc:
        log(f"Baseline backfill for {section} failed: {exc}")
        return False


def baseline_backfill_registry(entries: List[Tuple[str, str, str]]) -> int:
    """Mesma ideia, uma chave por vez: acrescenta ao baseline so o que falta nele."""
    if not BASELINE_FILE.exists():
        return 0
    try:
        data = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return 0
        rows = data.get("registry")
        if not isinstance(rows, list):
            return 0
        have = {(str(r.get("root")), str(r.get("path")).casefold(), str(r.get("name")).casefold()) for r in rows}
        added = 0
        for root, path, name in entries:
            key = (str(root), str(path).casefold(), str(name).casefold())
            if key in have:
                continue
            rows.append({"root": root, "path": path, "name": name, **reg_read(root, path, name)})
            have.add(key)
            added += 1
        if added:
            data["registry"] = rows
            backfilled = data.setdefault("backfilled", {})
            if isinstance(backfilled, dict):
                backfilled["registry_keys"] = _ts()
            BASELINE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            journal("baseline_backfill_registry", added=added)
        return added
    except Exception as exc:
        log(f"Registry baseline backfill failed: {exc}")
        return 0


def write_registry_values_verified(values: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """Grava um conjunto de valores e RELE cada um antes de dizer que deu certo.

    O contrato do app inteiro: nenhum tweak retorna sucesso sem releitura.
    """
    if winreg is None or os.name != "nt":
        return False, "Disponível só no Windows."
    baseline_backfill_registry([(v["root"], v["path"], v["name"]) for v in values])
    written, failed = [], []
    for item in values:
        root, path, name, value = item["root"], item["path"], item["name"], item["value"]
        typ = winreg.REG_SZ if isinstance(value, str) else winreg.REG_DWORD
        try:
            reg_write(root, path, name, value, typ)
            check = reg_read(root, path, name)
            if check.get("exists") and _same_registry_value(check.get("value"), value):
                written.append(name)
            else:
                failed.append(f"{name} (leu {check.get('value')!r})")
        except PermissionError:
            failed.append(f"{name} (acesso negado; o AZOR precisa ser aberto como administrador)")
        except Exception as exc:
            failed.append(f"{name} ({exc})")
    ok = bool(written) and not failed
    if ok:
        detail = f"{len(written)} valor(es) gravado(s) e relido(s): " + ", ".join(written) + "."
    else:
        detail = "Não confirmado: " + "; ".join(failed) + "."
        if written:
            detail = f"{len(written)} confirmado(s); " + detail
    return ok, detail


def verify_registry_values(values: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """Confere se os valores estão como o tweak pediu, sem gravar nada."""
    if winreg is None or os.name != "nt":
        return False, "Disponível só no Windows."
    wrong = []
    for item in values:
        check = reg_read(item["root"], item["path"], item["name"])
        if not (check.get("exists") and _same_registry_value(check.get("value"), item["value"])):
            wrong.append(f"{item['name']}={check.get('value')!r}")
    if wrong:
        return False, "Fora do esperado: " + ", ".join(wrong) + "."
    return True, f"{len(values)} valor(es) relido(s) e confirmado(s)."


# ---------------------------------------------------------------------------
# Servicos do Windows
#
# O app nao desliga servico em lote. Cada um que entra na lista tem de responder
# tres perguntas: o que ele faz, o que para de funcionar sem ele, e como voltar.
# ---------------------------------------------------------------------------

SERVICE_START_TYPES = {"Boot": 0, "System": 1, "Automatic": 2, "Manual": 3, "Disabled": 4}
SERVICE_START_NAMES = {v: k for k, v in SERVICE_START_TYPES.items()}


def service_state(name: str) -> Dict[str, Any]:
    """Tipo de inicialização e estado atual, lidos do registro (sem abrir processo)."""
    if os.name != "nt" or winreg is None:
        return {"exists": False, "name": name}
    entry = reg_read("HKLM", rf"SYSTEM\CurrentControlSet\Services\{name}", "Start")
    if not entry.get("exists"):
        return {"exists": False, "name": name}
    start = int(entry.get("value") or 0)
    return {
        "exists": True, "name": name, "start": start,
        "start_label": SERVICE_START_NAMES.get(start, str(start)),
        "disabled": start == 4,
    }


def set_service_start_verified(name: str, start_type: str) -> Tuple[bool, str]:
    """Muda o tipo de inicialização e confirma relendo. Não para o serviço a forca."""
    if os.name != "nt":
        return False, "Disponível só no Windows."
    target = SERVICE_START_TYPES.get(str(start_type))
    if target is None:
        return False, f"Tipo de inicialização inválido: {start_type}"
    if target == 4:
        from azor_managers import ServiceManager
        allowed,reason=ServiceManager(core=sys.modules[__name__]).can_disable(name)
        if not allowed:return False,reason
    before = service_state(name)
    if not before.get("exists"):
        return False, f"O serviço {name} não existe neste Windows; nada foi alterado."
    baseline_backfill_registry([("HKLM", rf"SYSTEM\CurrentControlSet\Services\{name}", "Start")])
    verb = {0: "boot", 1: "system", 2: "auto", 3: "demand", 4: "disabled"}[target]
    # `start=` e o valor vao em argumentos SEPARADOS - e a forma documentada do
    # sc.exe, e a mesma que o resto do app usa. Colado (`start=auto`) funciona em
    # algumas versoes e falha em outras, e nao da para distinguir num PC sem
    # elevacao porque o "Acesso negado" acontece no OpenService, antes de o
    # sc.exe chegar a interpretar as opcoes. Na duvida, a forma documentada.
    p = run_hidden(["sc", "config", name, "start=", verb], timeout=15)
    if p.returncode != 0:
        return False, (p.stdout or p.stderr or "").strip()[:400] or "O Windows recusou a mudanca."
    after = service_state(name)
    ok = after.get("start") == target
    if ok and target == 4:
        # Parar agora evita esperar o proximo boot; se ele recusar, o tipo ja mudou
        # e o servico nao volta - entao a falha aqui nao invalida o tweak.
        run_hidden(["sc", "stop", name], timeout=20)
        state=powershell_json("$s=Get-Service -Name '"+name+"' -ErrorAction Stop; $s.WaitForStatus([System.ServiceProcess.ServiceControllerStatus]::Stopped,[TimeSpan]::FromSeconds(10)); $s.Refresh(); [int]$s.Status",timeout=15)
        if state != 1:return False,"SERVICE_STOP_UNCONFIRMED: tipo alterado, mas a parada não foi confirmada; restaurar estado anterior."
    journal("service_start", service=name, requested=start_type, before=before.get("start_label"),
            after=after.get("start_label"), ok=ok)
    return ok, (f"{name}: inicialização {before.get('start_label')} -> {after.get('start_label')}, confirmada por releitura."
                if ok else f"{name}: a mudanca foi solicitada, mas o Windows continua em {after.get('start_label')}.")


def printer_count() -> Optional[int]:
    """Quantas impressoras reais estão instaladas (as virtuais do Windows não contam)."""
    if os.name != "nt":
        return None
    return cached_reading("printer_count", 300.0, _printer_count_probe)


def _printer_count_probe() -> Optional[int]:
    try:
        data = powershell_json(
            "@(Get-Printer -ErrorAction SilentlyContinue | Where-Object {"
            "$_.Name -notmatch 'Microsoft Print to PDF|Microsoft XPS|OneNote|Fax'}).Count",
            timeout=20)
        return int(data) if isinstance(data, (int, float)) else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Rede: adaptador ativo, propriedades avancadas e TCP global
# ---------------------------------------------------------------------------

def active_network_adapter(force: bool = False) -> Dict[str, Any]:
    """O adaptador que carrega a rota padrão - o único que importa para o jogo."""
    def probe() -> Dict[str, Any]:
        if os.name != "nt":
            return {}
        try:
            data = powershell_json(
                "$r=Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue|"
                "Sort-Object RouteMetric,ifMetric|Select-Object -First 1;"
                "if(-not $r){return};"
                "$a=Get-NetAdapter -InterfaceIndex $r.ifIndex -ErrorAction SilentlyContinue;"
                "if(-not $a){return};"
                "[pscustomobject]@{Name=$a.Name;Guid=$a.InterfaceGuid;Description=$a.InterfaceDescription;"
                "Index=$a.ifIndex;Speed=$a.LinkSpeed;Media=$a.MediaType;Status=$a.Status}",
                timeout=25) or {}
            if isinstance(data, list):
                data = data[0] if data else {}
            if not isinstance(data, dict) or not data.get("Name"):
                return {}
            return {
                "alias": str(data.get("Name") or ""),
                "guid": str(data.get("Guid") or "").strip("{}"),
                "guid_braced": str(data.get("Guid") or ""),
                "description": str(data.get("Description") or ""),
                "index": data.get("Index"),
                "speed": str(data.get("Speed") or ""),
                "media": str(data.get("Media") or ""),
                "status": str(data.get("Status") or ""),
                "wireless": "802.11" in str(data.get("Media") or "") or "wi-fi" in str(data.get("Name") or "").lower(),
            }
        except Exception as exc:
            log(f"Active adapter probe failed: {exc}")
            return {}
    return cached_reading("active_adapter", 90.0, probe, force=force) or {}


def nagle_registry_values(guid_braced: str) -> List[Dict[str, Any]]:
    path = TCPIP_INTERFACES_PATH + "\\" + str(guid_braced)
    return [
        {"root": "HKLM", "path": path, "name": "TcpAckFrequency", "value": 1},
        {"root": "HKLM", "path": path, "name": "TCPNoDelay", "value": 1},
        {"root": "HKLM", "path": path, "name": "TcpDelAckTicks", "value": 0},
    ]


def nic_advanced_properties(alias: str, force: bool = False) -> List[Dict[str, Any]]:
    """Propriedades avançadas expostas pelo driver do adaptador, como estão agora."""
    if os.name != "nt" or not alias:
        return []
    def probe() -> List[Dict[str, Any]]:
        try:
            data = powershell_json(
                "@(Get-NetAdapterAdvancedProperty -Name '" + alias.replace("'", "''") + "' -ErrorAction SilentlyContinue|"
                "Select-Object RegistryKeyword,DisplayName,DisplayValue,RegistryValue)",
                timeout=30) or []
            if isinstance(data, dict):
                data = [data]
            out = []
            for row in data:
                if not isinstance(row, dict):
                    continue
                raw = row.get("RegistryValue")
                if isinstance(raw, list):
                    raw = raw[0] if raw else None
                out.append({
                    "keyword": str(row.get("RegistryKeyword") or ""),
                    "display_name": str(row.get("DisplayName") or ""),
                    "display_value": str(row.get("DisplayValue") or ""),
                    "value": None if raw is None else str(raw),
                })
            return out
        except Exception as exc:
            log(f"NIC advanced properties failed: {exc}")
            return []
    return cached_reading(f"nic_adv:{alias}", 90.0, probe, force=force) or []


def nic_property_value(alias: str, keyword: str) -> Optional[str]:
    for row in nic_advanced_properties(alias):
        if row.get("keyword", "").casefold() == str(keyword).casefold():
            return row.get("value")
    return None


def set_nic_property_verified(alias: str, keyword: str, value: str) -> Tuple[bool, str]:
    """Grava uma propriedade avançada do driver e confirma relendo o driver."""
    if os.name != "nt":
        return False, "Disponível só no Windows."
    current = nic_property_value(alias, keyword)
    if current is None:
        return False, f"O driver de '{alias}' não expõe {keyword}; nada foi alterado."
    if str(current) == str(value):
        return True, f"{keyword} já estava em {value} neste adaptador."
    a, k, v = alias.replace("'", "''"), keyword.replace("'", "''"), str(value).replace("'", "''")
    try:
        out = powershell(
            f"Set-NetAdapterAdvancedProperty -Name '{a}' -RegistryKeyword '{k}' -RegistryValue '{v}' "
            f"-NoRestart -ErrorAction Stop; 'OK'", timeout=45)
    except Exception as exc:
        return False, f"O Windows recusou a mudanca de {keyword}: {exc}"
    if "OK" not in str(out):
        return False, f"{keyword} não pode ser alterado: {str(out).strip()[:300]}"
    invalidate_cache(f"nic_adv:{alias}")
    after = nic_property_value(alias, keyword)
    ok = str(after) == str(value)
    journal("nic_property", alias=alias, keyword=keyword, before=current, after=after, ok=ok)
    return ok, (f"{keyword}: {current} -> {after}, relido do driver."
                if ok else f"{keyword} foi solicitado como {value}, mas o driver reporta {after}.")


def nic_power_management(alias: str) -> Optional[bool]:
    """True quando o Windows tem permissao de desligar a placa de rede para economizar.

    Cacheado porque a resposta mais comum e um erro: varios drivers não publicam
    MSFT_NetAdapterPowerManagementSettingData, e sem cache cada tela do Arsenal
    pagava um PowerShell por tweak so para receber a mesma negativa.
    """
    if os.name != "nt" or not alias:
        return None
    return cached_reading(f"nic_pm:{alias}", 120.0, lambda: _nic_power_management_probe(alias))


def _nic_power_management_probe(alias: str) -> Optional[bool]:
    try:
        data = powershell_json(
            "$p=Get-NetAdapterPowerManagement -Name '" + alias.replace("'", "''") + "' -ErrorAction SilentlyContinue;"
            "if($p){[pscustomobject]@{Allow=[string]$p.AllowComputerToTurnOffDevice}}",
            timeout=25) or {}
        if isinstance(data, list):
            data = data[0] if data else {}
        raw = str((data or {}).get("Allow") or "").strip().lower()
        if raw in ("enabled", "true", "1"):
            return True
        if raw in ("disabled", "false", "0"):
            return False
        return None
    except Exception:
        return None


NET_CLASS_GUID = "{4d36e972-e325-11ce-bfc1-08002be10318}"
# PnPCapabilities = 24 (0x18) e o valor que o Windows grava quando voce desmarca
# "O computador pode desligar este dispositivo para economizar energia" na aba
# Gerenciamento de Energia do Gerenciador de Dispositivos.
PNP_NO_POWER_MANAGEMENT = 24


def nic_driver_key(alias: str) -> Optional[str]:
    r"""Caminho da chave de driver do adaptador, onde vive PnPCapabilities.

    Formato: SYSTEM\CurrentControlSet\Control\Class\<GUID da classe Net>\NNNN

    A primeira tentativa foi pedir o indice ao Get-NetAdapter; ele nao devolve
    isso. O caminho confiavel e o inverso: percorrer as subchaves da classe de
    rede e achar a que tem NetCfgInstanceId igual ao GUID da interface. E winreg
    puro, funciona offline e nao depende de idioma.
    """
    if os.name != "nt" or winreg is None or not alias:
        return None

    def probe() -> Optional[str]:
        guid = ""
        adapter = active_network_adapter()
        if str(adapter.get("alias") or "").casefold() == str(alias).casefold():
            guid = str(adapter.get("guid_braced") or "")
        if not guid:
            try:
                data = powershell_json(
                    "$a=Get-NetAdapter -Name '" + str(alias).replace("'", "''") + "' "
                    "-ErrorAction SilentlyContinue|Select-Object -First 1;"
                    "if($a){[pscustomobject]@{Guid=[string]$a.InterfaceGuid}}", timeout=25) or {}
                if isinstance(data, list):
                    data = data[0] if data else {}
                guid = str((data or {}).get("Guid") or "")
            except Exception:
                guid = ""
        if not guid:
            return None
        base = r"SYSTEM\CurrentControlSet\Control\Class" + "\\" + NET_CLASS_GUID
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base, 0, winreg.KEY_READ) as root:
                index = 0
                while True:
                    try:
                        sub = winreg.EnumKey(root, index)
                    except OSError:
                        break
                    index += 1
                    if not re.fullmatch(r"\d{4}", sub):
                        continue
                    entry = reg_read("HKLM", base + "\\" + sub, "NetCfgInstanceId")
                    if str(entry.get("value") or "").casefold() == guid.casefold():
                        return base + "\\" + sub
        except Exception as exc:
            log(f"NIC driver key scan failed: {exc}")
        return None

    return cached_reading(f"nic_key:{alias}", 600.0, probe)


def nic_pnp_power_managed(alias: str) -> Optional[bool]:
    """True = o Windows pode desligar a placa. None = a chave nem existe."""
    key = nic_driver_key(alias)
    if not key:
        return None
    entry = reg_read("HKLM", key, "PnPCapabilities")
    if not entry.get("exists"):
        # Ausente significa "comportamento padrao do driver", que e permitir.
        return True
    try:
        return not bool(int(entry.get("value") or 0) & PNP_NO_POWER_MANAGEMENT)
    except Exception:
        return None


def set_nic_power_management_verified(alias: str, allow: bool) -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Disponível só no Windows."
    before = nic_power_management(alias)
    if before is None:
        # Nem todo driver publica MSFT_NetAdapterPowerManagementSettingData. O
        # interruptor real do Gerenciador de Dispositivos e PnPCapabilities, e ele
        # existe para qualquer placa - entao o AZOR cai para ele em vez de desistir.
        key = nic_driver_key(alias)
        if not key:
            return False, f"O adaptador '{alias}' não expõe gerenciamento de energia; nada foi alterado."
        if not is_admin():
            return False, "Alterar a energia da placa de rede exige o AZOR aberto como administrador."
        if allow:
            ok, detail = revert_registry_from_baseline([("HKLM", key, "PnPCapabilities")], "nic_power")
            return ok, detail
        ok, detail = write_registry_values_verified(
            [{"root": "HKLM", "path": key, "name": "PnPCapabilities", "value": PNP_NO_POWER_MANAGEMENT}])
        journal("nic_power_pnp", alias=alias, key=key, ok=ok)
        return ok, (detail + " O Windows perde a permissao de desligar a placa; vale a partir do próximo "
                             "reinício do adaptador ou do PC." if ok else detail)
    if before == allow:
        return True, "O adaptador já estava nesse estado de economia de energia."
    a = alias.replace("'", "''")
    state = "Enabled" if allow else "Disabled"
    try:
        out = powershell(
            f"Set-NetAdapterPowerManagement -Name '{a}' -AllowComputerToTurnOffDevice {state} "
            f"-NoRestart -ErrorAction Stop; 'OK'", timeout=45)
    except Exception as exc:
        return False, f"O Windows recusou a mudanca: {exc}"
    if "OK" not in str(out):
        return False, str(out).strip()[:300] or "Mudanca não confirmada."
    after = nic_power_management(alias)
    ok = after == allow
    journal("nic_power", alias=alias, before=before, after=after, ok=ok)
    return ok, ("O Windows não pode mais desligar a placa de rede para economizar energia; relido e confirmado."
                if ok and not allow else
                "Permissao de economia devolvida ao Windows e confirmada." if ok else
                "A mudanca foi solicitada, mas o Windows não confirmou.")




# ATENCAO ao mexer aqui: a primeira versao lia `netsh int tcp show global` e
# procurava a linha pelo nome em ingles. Num Windows em portugues a linha se chama
# "Nivel de Ajuste Automatico da Janela de Recebimento", a busca nao achava nada,
# e o tweak se declarava "nao suportado" num PC onde era perfeitamente suportado.
# Get-NetTCPSetting devolve nomes de propriedade invariantes: TCP e lido por
# cmdlet, nunca por texto de saida traduzida.
def tcp_global_state(force: bool = False) -> Dict[str, str]:
    """Configuração TCP do perfil Internet, por nomes de propriedade invariantes."""
    def probe() -> Dict[str, str]:
        if os.name != "nt":
            return {}
        try:
            data = powershell_json(
                "$s=Get-NetTCPSetting -SettingName Internet -ErrorAction SilentlyContinue|Select-Object -First 1;"
                "if(-not $s){return};"
                "[pscustomobject]@{AutoTuningLevelLocal=[string]$s.AutoTuningLevelLocal;"
                "EcnCapability=[string]$s.EcnCapability;Timestamps=[string]$s.Timestamps;"
                "InitialRto=[string]$s.InitialRto;ScalingHeuristics=[string]$s.ScalingHeuristics;"
                "MinRto=[string]$s.MinRto}", timeout=30) or {}
            if isinstance(data, list):
                data = data[0] if data else {}
            return {str(k): str(v) for k, v in (data or {}).items() if v not in (None, "")}
        except Exception as exc:
            log(f"TCP setting probe failed: {exc}")
            return {}
    return cached_reading("tcp_global", 60.0, probe, force=force) or {}


_TCP_ALIASES = {
    "autotuninglevel": "AutoTuningLevelLocal",
    "autotuninglevellocal": "AutoTuningLevelLocal",
    "ecncapability": "EcnCapability",
    "timestamps": "Timestamps",
    "initialrto": "InitialRto",
}


def _tcp_global_lookup(state: Dict[str, str], setting: str) -> Optional[str]:
    key = _TCP_ALIASES.get(re.sub(r"[^a-z]", "", str(setting).lower()), str(setting))
    if key in state:
        return state[key]
    for name, value in state.items():
        if name.casefold() == key.casefold():
            return value
    return None


def set_tcp_global_verified(setting: str, value: str) -> Tuple[bool, str]:
    """Set-NetTCPSetting no perfil Internet, confirmado por releitura da propriedade."""
    if os.name != "nt":
        return False, "Disponível só no Windows."
    prop = _TCP_ALIASES.get(re.sub(r"[^a-z]", "", str(setting).lower()), str(setting))
    before = _tcp_global_lookup(tcp_global_state(), prop)
    baseline_backfill("tcp_global", dict(tcp_global_state()))
    safe = re.sub(r"[^A-Za-z0-9]", "", str(value))
    if not safe:
        return False, f"Valor inválido para {prop}."
    try:
        out = powershell(f"Set-NetTCPSetting -SettingName Internet -{prop} {safe} -ErrorAction Stop; 'OK'",
                         timeout=45)
    except Exception as exc:
        return False, f"O Windows recusou a mudanca de {prop}: {exc}"
    if "OK" not in str(out):
        return False, str(out).strip()[:300] or f"{prop} não foi alterado."
    invalidate_cache("tcp_global")
    after = _tcp_global_lookup(tcp_global_state(force=True), prop)
    ok = str(after or "").strip().casefold() == safe.casefold()
    journal("tcp_setting", setting=prop, requested=safe, before=before, after=after, ok=ok)
    return ok, (f"{prop}: {before} -> {after}, relido pelo Get-NetTCPSetting."
                if ok else f"{prop} foi pedido como {safe}, mas o Windows reporta {after}.")


# ---------------------------------------------------------------------------
# NTFS / disco
# ---------------------------------------------------------------------------

def _fsutil_scalar(text: str) -> Optional[int]:
    """Extrai o valor numerico de um `fsutil behavior query`, em qualquer idioma.

    O separador muda com a localizacao do Windows: "= 2" em ingles, "e: 2" em
    portugues. E o rotulo também muda. O que não muda e a forma "<digito> (" do
    valor seguido da explicacao entre parenteses, e o separador ser ':' ou '='.
    """
    for pattern in (r"[:=]\s*([0-9])\b", r"\b([0-9])\s*\("):
        m = re.search(pattern, str(text or ""))
        if m:
            return int(m.group(1))
    return None


def ntfs_last_access_state(force: bool = False) -> Dict[str, Any]:
    """0/2 = atualização de último acesso ligada; 1/3 = desligada. 2 e 3 são 'gerenciado pelo sistema'."""
    def probe() -> Dict[str, Any]:
        if os.name != "nt":
            return {}
        try:
            p = run_hidden(["fsutil", "behavior", "query", "disablelastaccess"], timeout=15)
            value = _fsutil_scalar(p.stdout)
            return {"value": value, "disabled": value in (1, 3), "managed": value in (2, 3),
                    "raw": (p.stdout or "").strip()[:200]}
        except Exception:
            return {}
    return cached_reading("ntfs_last_access", 300.0, probe, force=force) or {}


def set_ntfs_last_access_verified(value: int) -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Disponível só no Windows."
    before = ntfs_last_access_state()
    baseline_backfill("ntfs_last_access", before)
    p = run_hidden(["fsutil", "behavior", "set", "disablelastaccess", str(int(value))], timeout=20)
    if p.returncode != 0:
        return False, (p.stdout or p.stderr or "").strip()[:300] or "fsutil recusou o comando."
    after = ntfs_last_access_state(force=True)
    ok = after.get("value") == int(value)
    journal("ntfs_last_access", requested=value, before=before.get("value"), after=after.get("value"), ok=ok)
    return ok, (f"Atualizacao de último acesso do NTFS: {before.get('value')} -> {after.get('value')}, relido pelo fsutil."
                if ok else f"Foi pedido {value}, mas o fsutil reporta {after.get('value')}.")


def ntfs_8dot3_state(force: bool = False) -> Dict[str, Any]:
    """Criacao de nome curto 8.3. 0 = em todos os volumes, 1 = em nenhum,
    2 = por volume (padrão do Windows), 3 = todos menos o do sistema."""
    def probe() -> Dict[str, Any]:
        if os.name != "nt":
            return {}
        try:
            p = run_hidden(["fsutil", "behavior", "query", "disable8dot3"], timeout=15)
            value = _fsutil_scalar(p.stdout)
            return {"value": value, "disabled_everywhere": value == 1,
                    "raw": (p.stdout or "").strip()[:200]}
        except Exception:
            return {}
    return cached_reading("ntfs_8dot3", 300.0, probe, force=force) or {}


def set_ntfs_8dot3_verified(value: int) -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Disponível só no Windows."
    before = ntfs_8dot3_state()
    baseline_backfill("ntfs_8dot3", before)
    p = run_hidden(["fsutil", "behavior", "set", "disable8dot3", str(int(value))], timeout=20)
    if p.returncode != 0:
        return False, (p.stdout or p.stderr or "").strip()[:300] or "fsutil recusou o comando."
    after = ntfs_8dot3_state(force=True)
    ok = after.get("value") == int(value)
    journal("ntfs_8dot3", requested=value, before=before.get("value"), after=after.get("value"), ok=ok)
    return ok, (f"Criacao de nome curto 8.3: {before.get('value')} -> {after.get('value')}, "
                "relido pelo fsutil." if ok
                else f"Foi pedido {value}, mas o fsutil reporta {after.get('value')}.")


def delete_notify_state(force: bool = False) -> Dict[str, Any]:
    """TRIM. DisableDeleteNotify=0 significa TRIM LIGADO (o nome da chave e invertido)."""
    def probe() -> Dict[str, Any]:
        if os.name != "nt":
            return {}
        try:
            p = run_hidden(["fsutil", "behavior", "query", "disabledeletenotify"], timeout=15)
            text = p.stdout or ""
            values = [int(x) for x in re.findall(r"[:=]\s*([0-9])\b", text)]
            return {"values": values, "trim_on": bool(values) and all(v == 0 for v in values),
                    "raw": text.strip()[:300]}
        except Exception:
            return {}
    return cached_reading("delete_notify", 300.0, probe, force=force) or {}


PREFETCH_PARAMS = (r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management"
                   r"\PrefetchParameters")


def app_launch_cache_state(force: bool = False) -> Dict[str, Any]:
    """O Windows ainda pre-carrega os programas que você mais usa?

    Duas pecas fazem isso, e as duas costumam ser desligadas juntas por scripts
    de "otimizacao": o serviço SysMain (antigo Superfetch) e o Prefetcher.
    """
    def probe() -> Dict[str, Any]:
        out = {"supported": os.name == "nt", "sysmain_running": None,
               "sysmain_start": None, "prefetcher": None, "broken": False,
               "detail": ""}
        if os.name != "nt":
            return out
        try:
            q = run_hidden(["sc", "query", "SysMain"], timeout=10)
            txt = (q.stdout or "")
            if "RUNNING" in txt:
                out["sysmain_running"] = True
            elif "STOPPED" in txt:
                out["sysmain_running"] = False
            c = run_hidden(["sc", "qc", "SysMain"], timeout=10)
            ctxt = (c.stdout or "")
            if "DISABLED" in ctxt.upper():
                out["sysmain_start"] = "disabled"
            elif "AUTO_START" in ctxt.upper():
                out["sysmain_start"] = "auto"
            elif "DEMAND_START" in ctxt.upper():
                out["sysmain_start"] = "manual"
            entry = reg_read("HKLM", PREFETCH_PARAMS, "EnablePrefetcher")
            out["prefetcher"] = entry.get("value") if entry.get("exists") else None
        except Exception as exc:
            log_debug(f"app_launch_cache_state: {exc}")
            return out
        desligado = (out["sysmain_running"] is False
                     or out["sysmain_start"] == "disabled"
                     or out["prefetcher"] in (0, "0"))
        out["broken"] = bool(desligado)
        out["detail"] = (
            "O Windows deixou de pre-carregar os programas que você mais usa. "
            "E a causa mais comum de 'o PC ficou lento para abrir aplicativo' "
            "depois de passar um otimizador."
            if desligado else
            "SysMain e Prefetcher ativos: o Windows pre-carrega normalmente.")
        return out
    return cached_reading("app_launch_cache", 60.0, probe, force=force) or {}


def repair_app_launch_cache() -> Tuple[bool, str]:
    """Religa SysMain e o Prefetcher, e confirma relendo os dois.

    Por que isto e REPARO e não tweak:
    -----------------------------------
    "Desative o Superfetch, você tem SSD" e conselho de 2012. Ele nasceu quando
    o SysMain vivia paginando em HD mecanico e quando SSD tinha pouca resistencia
    a escrita. Em Windows 10/11 com SSD, a Microsoft mantem o serviço ligado de
    proposito: ele cacheia em RAM, o trafego de disco e pequeno, e e ELE quem faz
    o programa que você usa todo dia abrir rápido.

    Desligar não devolve FPS: o SysMain nem roda durante a partida, porque ele
    cede prioridade sob carga. Devolve tela de espera cada vez que o cliente abre
    o navegador. E o motivo número um de "otimizei e meu PC ficou lento".
    """
    if os.name != "nt":
        return False, "Disponível só no Windows."
    if not is_admin():
        return False, ("Religar o SysMain exige o AZOR aberto como administrador.")
    antes = app_launch_cache_state(force=True)
    baseline_backfill("app_launch_cache", antes)
    passos = []
    try:
        run_hidden(["sc", "config", "SysMain", "start=", "auto"], timeout=15)
        run_hidden(["sc", "start", "SysMain"], timeout=25)
        passos.append("SysMain: inicio automático e serviço iniciado")
    except Exception as exc:
        passos.append(f"SysMain falhou: {exc}")
    try:
        # 3 = pre-carrega aplicativos e boot. E o padrao do Windows.
        reg_write("HKLM", PREFETCH_PARAMS, "EnablePrefetcher", 3)
        passos.append("EnablePrefetcher = 3")
    except Exception as exc:
        passos.append(f"Prefetcher falhou: {exc}")
    depois = app_launch_cache_state(force=True)
    ok = not depois.get("broken")
    journal("app_launch_cache_repair", before=antes, after=depois, ok=ok)
    log(f"Reparo do cache de abertura: ok={ok} {passos}",
        "SUCCESS" if ok else "ERROR")
    return ok, (
        "SysMain e Prefetcher religados e confirmados por releitura. "
        "A primeira abertura de cada programa ainda leva o tempo de sempre; "
        "a partir da segunda o Windows volta a pre-carregar."
        if ok else
        f"Não foi confirmado na releitura. {'; '.join(passos)}")


def enable_trim_verified() -> Tuple[bool, str]:
    """Religa o TRIM quando algum 'otimizador' o desligou. Reparo, não tweak novo."""
    if os.name != "nt":
        return False, "Disponível só no Windows."
    before = delete_notify_state()
    baseline_backfill("delete_notify", before)
    p = run_hidden(["fsutil", "behavior", "set", "disabledeletenotify", "0"], timeout=20)
    if p.returncode != 0:
        return False, (p.stdout or p.stderr or "").strip()[:300] or "fsutil recusou o comando."
    after = delete_notify_state(force=True)
    ok = bool(after.get("trim_on"))
    journal("trim_repair", before=before.get("values"), after=after.get("values"), ok=ok)
    return ok, ("TRIM confirmado como ativo pelo fsutil em todos os sistemas de arquivo."
                if ok else f"TRIM não foi confirmado: {after.get('raw')}")


# ---------------------------------------------------------------------------
# GPU: agendamento por hardware, MSI e preferencia por jogo
# ---------------------------------------------------------------------------

GRAPHICS_DRIVERS_PATH = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"


def hags_state() -> Dict[str, Any]:
    """HwSchMode: 1 = desligado, 2 = ligado. A chave so existe quando o driver
    suporta agendamento por hardware - ausencia significa 'não suportado', não 'zero'."""
    entry = reg_read("HKLM", GRAPHICS_DRIVERS_PATH, "HwSchMode")
    return {
        "supported": bool(entry.get("exists")),
        "value": entry.get("value"),
        "enabled": entry.get("value") == 2,
    }


def gpu_pci_instances() -> List[Dict[str, Any]]:
    """Os controladores de vídeo no barramento PCI, com o caminho de instância real."""
    if os.name != "nt":
        return []
    def probe() -> List[Dict[str, Any]]:
        try:
            data = powershell_json(
                "@(Get-PnpDevice -Class Display -Status OK -ErrorAction SilentlyContinue|"
                "Where-Object {$_.InstanceId -like 'PCI*'}|"
                "Select-Object FriendlyName,InstanceId)", timeout=30) or []
            if isinstance(data, dict):
                data = [data]
            return [{"name": str(x.get("FriendlyName") or ""), "instance": str(x.get("InstanceId") or "")}
                    for x in data if isinstance(x, dict) and x.get("InstanceId")]
        except Exception as exc:
            log(f"GPU PCI probe failed: {exc}")
            return []
    return cached_reading("gpu_pci", 600.0, probe) or []


def _msi_path(instance: str) -> str:
    return (r"SYSTEM\CurrentControlSet\Enum" + "\\" + str(instance).strip("\\")
            + r"\Device Parameters\Interrupt Management\MessageSignaledInterruptProperties")


def gpu_msi_state() -> Dict[str, Any]:
    """MSI (Message Signaled Interrupts) por GPU, lido do Enum do dispositivo."""
    rows = []
    for gpu in gpu_pci_instances():
        entry = reg_read("HKLM", _msi_path(gpu["instance"]), "MSISupported")
        rows.append({
            "name": gpu["name"], "instance": gpu["instance"],
            "key_exists": bool(entry.get("exists")),
            "msi": None if not entry.get("exists") else entry.get("value") == 1,
            "value": entry.get("value"),
        })
    return {"gpus": rows, "any_off": any(r["msi"] is False for r in rows),
            "all_on": bool(rows) and all(r["msi"] is True for r in rows)}


def set_gpu_msi_verified(enabled: bool = True) -> Tuple[bool, str]:
    """Liga MSI nas GPUs PCI. Exige reinício para valer, e o app diz isso."""
    if os.name != "nt":
        return False, "Disponível só no Windows."
    gpus = gpu_pci_instances()
    if not gpus:
        return False, "Nenhuma GPU no barramento PCI foi encontrada; nada foi alterado."
    values = [{"root": "HKLM", "path": _msi_path(g["instance"]), "name": "MSISupported",
               "value": 1 if enabled else 0} for g in gpus]
    ok, detail = write_registry_values_verified(values)
    journal("gpu_msi", enabled=enabled, gpus=[g["name"] for g in gpus], ok=ok)
    if not ok:
        return ok, detail
    names = ", ".join(g["name"] for g in gpus)
    return True, (f"MSI gravado e relido em: {names}. So passa a valer depois de reiniciar o Windows.")




def detect_installed_games(force: bool = False) -> List[Dict[str, Any]]:
    """Executaveis de jogo que o Windows já conhece, para a preferencia de GPU.

    Fonte: as pastas de instalacao dos lancadores presentes + o que já tem
    preferencia gravada. Não varre o disco inteiro.
    """
    def probe() -> List[Dict[str, Any]]:
        if os.name != "nt":
            return []
        found: Dict[str, Dict[str, Any]] = {}
        fort = detect_fortnite()
        if fort.get("exe"):
            found[str(fort["exe"]).lower()] = {"exe": fort["exe"], "name": "Fortnite", "source": "Epic Games"}
        roots: List[Path] = []
        for env in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
            base = os.environ.get(env)
            if base:
                roots += [Path(base) / "Steam" / "steamapps" / "common",
                          Path(base) / "Epic Games", Path(base) / "Riot Games"]
        for letter in "CDEFG":
            roots += [Path(f"{letter}:/SteamLibrary/steamapps/common"),
                      Path(f"{letter}:/Steam/steamapps/common"),
                      Path(f"{letter}:/Games")]
        for root in roots:
            try:
                if not root.is_dir():
                    continue
                for game_dir in list(root.iterdir())[:60]:
                    if not game_dir.is_dir():
                        continue
                    for exe in list(game_dir.rglob("*.exe"))[:400]:
                        low = exe.name.lower()
                        if any(bad in low for bad in ("unins", "setup", "crash", "launcher", "redist",
                                                      "vcredist", "dxsetup", "helper", "service")):
                            continue
                        try:
                            if exe.stat().st_size < 8 * 1024 * 1024:
                                continue
                        except Exception:
                            continue
                        key = str(exe).lower()
                        if key not in found:
                            found[key] = {"exe": str(exe), "name": game_dir.name, "source": root.name}
                        break
            except Exception:
                continue
        for exe in (list_game_gpu_preferences().get("games") or []):
            path = str(exe.get("exe") or "")
            if path and path.lower() not in found:
                found[path.lower()] = {"exe": path, "name": Path(path).stem, "source": "Preferencia já gravada"}
        return list(found.values())[:40]
    return cached_reading("installed_games", 900.0, probe, force=force) or []


def set_all_games_high_performance_gpu() -> Tuple[bool, str]:
    """Grava GpuPreference=2 para cada jogo encontrado e rele cada um."""
    games = detect_installed_games()
    if not games:
        return False, "Nenhum executavel de jogo foi localizado nas pastas conhecidas; nada foi gravado."
    done, failed = [], []
    for game in games:
        try:
            ok, _ = set_game_high_performance_gpu(str(game["exe"]), capture=True)
            (done if ok else failed).append(game["name"])
        except Exception:
            failed.append(game["name"])
    ok = bool(done) and not failed
    journal("all_games_gpu", applied=done, failed=failed)
    detail = f"{len(done)} jogo(s) definidos para a GPU de alto desempenho e relidos: " + ", ".join(done[:8])
    if len(done) > 8:
        detail += f" e mais {len(done) - 8}"
    if failed:
        detail += f". Não confirmado: {', '.join(failed[:5])}."
    return ok, detail + "."


# ==================== MEDICAO FINA E INDICE AZOR ====================
#
# A parte que o cliente ve precisa de numeros grandes. A regra desta build e que
# eles sejam grandes porque o trabalho e grande, nao porque a tela inflou o valor.
# Sao duas fontes:
#   1. medicao de verdade, com resolucao maior (microssegundos, p99, stalls);
#   2. contagem do que o motor realmente tocou (chaves gravadas e relidas).
# Nenhum dos dois e estimado.




# O arsenal em numeros: quantos pontos do Windows o motor sabe mexer, contados a
# partir do proprio catalogo. Se um tweak for adicionado ou removido, este numero
# muda sozinho - ele nao e uma constante escrita na tela.






# ==================== REPARO: DESFAZER O ESTRAGO DE OUTROS OTIMIZADORES ====================
#
# Quase todo PC que chega "ja otimizado" chega tambem com alguma coisa quebrada
# por um script de internet: HPET forcado no boot, servico de audio desabilitado,
# firewall desligado, Protecao do Sistema off. Nada disso aparece como erro - o
# Windows so fica pior em silencio.
#
# Estas leituras existem para achar esses casos. Duas regras:
#   1. So e reportado o que pode ser CONFIRMADO por releitura. Sem confirmacao, o
#      AZOR diz que nao sabe em vez de acusar.
#   2. Reparo nao tem "desfazer". O app nao oferece um botao para desligar o
#      firewall de novo ou forcar o HPET de volta; ele diz isso e mostra o comando
#      para quem realmente quiser.


# Opcoes de boot que scripts de "otimizacao" costumam gravar. A presenca de
# qualquer uma no {current} JA e o problema: nenhuma existe num Windows de
# fabrica, entao presenca == alguem sobrescreveu o padrao.
BCD_TIMER_OVERRIDES = ("useplatformclock", "disabledynamictick", "tscsyncpolicy",
                       "useplatformtick", "x2apicpolicy")


def bcd_overrides(force: bool = False) -> Dict[str, Any]:
    r"""Le `bcdedit /enum {current}` e devolve quais overrides de tempo existem.

    Detecta pela PRESENCA do nome da opcao, nunca pelo valor: o valor sai
    traduzido ("Sim"/"Nao") num Windows em portugues, e o nome da opcao nao. Como
    nenhuma dessas opcoes existe por padrao, estar la ja significa que alguem
    gravou.
    """
    def probe() -> Dict[str, Any]:
        if os.name != "nt":
            return {"supported": False, "readable": False, "present": []}
        try:
            p = run_hidden(["bcdedit", "/enum", "{current}"], timeout=15)
        except Exception as exc:
            return {"supported": True, "readable": False, "present": [], "detail": str(exc)}
        if p.returncode != 0:
            return {"supported": True, "readable": False, "present": [],
                    "detail": ("O bcdedit recusou a leitura. Ele exige administrador."
                               if not is_admin() else "O bcdedit recusou a leitura.")}
        text = (p.stdout or "")
        present = [name for name in BCD_TIMER_OVERRIDES
                   if re.search(rf"(?mi)^{name}\s", text)]
        return {"supported": True, "readable": True, "present": present,
                "detail": ("Nenhum override de temporizador no boot."
                           if not present else "Overrides encontrados: " + ", ".join(present))}
    return cached_reading("bcd_overrides", 300.0, probe, force=force) or {}


def remove_bcd_override(name: str) -> Tuple[bool, str]:
    """Apaga um override de boot e confirma relendo o {current}."""
    if os.name != "nt":
        return False, "Disponível só no Windows."
    if name not in BCD_TIMER_OVERRIDES:
        return False, f"Override não reconhecido: {name}"
    if not is_admin():
        return False, "Alterar o boot exige o AZOR aberto como administrador."
    p = run_hidden(["bcdedit", "/deletevalue", "{current}", name], timeout=20)
    invalidate_cache("bcd_overrides")
    after = bcd_overrides(force=True)
    ok = after.get("readable") and name not in (after.get("present") or [])
    journal("bcd_override_removed", name=name, rc=p.returncode, ok=bool(ok))
    return bool(ok), (f"{name} removido do boot e confirmado por releitura." if ok
                      else f"O bcdedit respondeu código {p.returncode} e {name} ainda aparece no boot.")


def firewall_state(force: bool = False) -> Dict[str, Any]:
    """Perfis do Firewall do Windows, por nome de propriedade invariante."""
    def probe() -> Dict[str, Any]:
        if os.name != "nt":
            return {"supported": False, "profiles": []}
        try:
            data = powershell_json(
                "@(Get-NetFirewallProfile -ErrorAction SilentlyContinue|"
                "ForEach-Object{[pscustomobject]@{Name=[string]$_.Name;Enabled=[string]$_.Enabled}})",
                timeout=30) or []
            if isinstance(data, dict):
                data = [data]
            rows = [{"name": str(x.get("Name") or ""),
                     "enabled": str(x.get("Enabled") or "").strip().lower() in ("true", "1")}
                    for x in data if isinstance(x, dict)]
            return {"supported": True, "profiles": rows,
                    "disabled": [r["name"] for r in rows if not r["enabled"]],
                    "readable": bool(rows)}
        except Exception as exc:
            return {"supported": True, "readable": False, "profiles": [], "detail": str(exc)}
    return cached_reading("firewall_state", 180.0, probe, force=force) or {}


def enable_firewall_verified() -> Tuple[bool, str]:
    """Religa os perfis do Firewall que estiverem desligados, e confirma."""
    if os.name != "nt":
        return False, "Disponível só no Windows."
    if not is_admin():
        return False, "Religar o firewall exige o AZOR aberto como administrador."
    before = firewall_state()
    off = before.get("disabled") or []
    if not off:
        return True, "Todos os perfis do firewall já estavam ligados."
    try:
        powershell("Set-NetFirewallProfile -Profile " + ",".join(off) +
                   " -Enabled True -ErrorAction Stop; 'OK'", timeout=45)
    except Exception as exc:
        return False, f"O Windows recusou religar o firewall: {exc}"
    after = firewall_state(force=True)
    ok = not (after.get("disabled") or [])
    journal("firewall_repair", before=off, after=after.get("disabled"), ok=ok)
    return ok, (f"Perfis religados e confirmados: {', '.join(off)}." if ok
                else f"Ainda desligado(s): {', '.join(after.get('disabled') or [])}.")


SYSTEM_RESTORE_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\SystemRestore"


def system_restore_config() -> Dict[str, Any]:
    """Proteção do Sistema ligada? Lido de duas chaves, sem chutar a terceira.

    `system_protection_status()` responde "quantos pontos existem", que e outra
    pergunta: um PC recem-formatado tem zero pontos com a proteção ligada.
    """
    interval = reg_read("HKLM", SYSTEM_RESTORE_KEY, "RPSessionInterval")
    disabled = reg_read("HKLM", SYSTEM_RESTORE_KEY, "DisableSR")
    if not interval.get("exists"):
        return {"readable": False, "enabled": None,
                "detail": "O Windows não expos RPSessionInterval; o estado não pode ser confirmado."}
    off_by_policy = bool(disabled.get("exists")) and int(disabled.get("value") or 0) == 1
    enabled = int(interval.get("value") or 0) == 1 and not off_by_policy
    return {"readable": True, "enabled": enabled, "session_interval": interval.get("value"),
            "disabled_by_policy": off_by_policy,
            "detail": ("Proteção do Sistema ligada no disco do Windows." if enabled
                       else "Proteção do Sistema desligada: o Windows não esta criando pontos de restauração.")}


def enable_system_restore_verified() -> Tuple[bool, str]:
    """Religa a Proteção do Sistema no disco do Windows e confirma por releitura."""
    if os.name != "nt":
        return False, "Disponível só no Windows."
    if not is_admin():
        return False, "Religar a Proteção do Sistema exige o AZOR aberto como administrador."
    before = system_restore_config()
    try:
        powershell("Enable-ComputerRestore -Drive \"$env:SystemDrive\\\" -ErrorAction Stop; 'OK'", timeout=90)
    except Exception as exc:
        return False, f"O Windows recusou religar a Proteção do Sistema: {exc}"
    after = system_restore_config()
    ok = bool(after.get("enabled"))
    journal("system_restore_repair", before=before.get("enabled"), after=after.get("enabled"), ok=ok)
    return ok, ("Proteção do Sistema religada e confirmada; o Windows volta a criar pontos de "
                "restauração - inclusive o que o AZOR pede antes de otimizar."
                if ok else f"A mudanca foi solicitada, mas a releitura diz: {after.get('detail')}")


# Servicos que nenhum "otimizador" deveria desligar, e o que quebra quando desliga.
# WSearch e Windows Defender ficam FORA: a primeira e preferencia legitima de
# quem nao usa busca, e a segunda quebra em PC com antivirus de terceiro.
ESSENTIAL_SERVICES = {
    "Audiosrv": "áudio do Windows",
    "AudioEndpointBuilder": "detecção de saídas de áudio",
    "Themes": "temas e estilos visuais (a interface fica com aparencia de Windows classico)",
    "Dhcp": "obtencao automática de IP",
    "Dnscache": "cache de resolução de nomes",
    "EventLog": "log de eventos - sem ele o próprio diagnóstico do AZOR fica cego",
    "nsi": "informacoes de rede (conexoes param de funcionar)",
    "Schedule": "Agendador de Tarefas, usado pelo Windows Update e por drivers",
    "BFE": "motor de filtragem base (firewall e VPN dependem dele)",
    "mpssvc": "Firewall do Windows",
    "wuauserv": "Windows Update - sem ele o PC para de receber correcao de segurança",
    "BITS": "transferencia em segundo plano usada pelo Windows Update",
}


def disabled_essential_services() -> List[Dict[str, str]]:
    """Quais serviços essenciais estão com inicialização Desabilitada agora."""
    out: List[Dict[str, str]] = []
    for name, what in ESSENTIAL_SERVICES.items():
        state = service_state(name)
        if state.get("exists") and state.get("disabled"):
            out.append({"name": name, "breaks": what})
    return out


def restore_essential_services() -> Tuple[bool, str]:
    """Devolve os serviços essenciais desabilitados ao tipo de inicialização padrão.

    O padrão usado e o do próprio Windows para cada serviço, escrito aqui porque
    o baseline do AZOR não serve: se o serviço já chegou desabilitado, o "valor
    anterior ao AZOR" também e "desabilitado", e restaurar isso não repara nada.
    """
    defaults = {
        "Audiosrv": "Automatic", "AudioEndpointBuilder": "Automatic", "Themes": "Automatic",
        "Dhcp": "Automatic", "Dnscache": "Automatic", "EventLog": "Automatic",
        "nsi": "Automatic", "Schedule": "Automatic", "BFE": "Automatic",
        "mpssvc": "Automatic", "wuauserv": "Manual", "BITS": "Manual",
    }
    broken = disabled_essential_services()
    if not broken:
        return True, "Nenhum serviço essencial estava desabilitado."
    done, failed = [], []
    for item in broken:
        name = item["name"]
        ok, detail = set_service_start_verified(name, defaults.get(name, "Manual"))
        (done if ok else failed).append(f"{name}" if ok else f"{name} ({detail})")
    ok = bool(done) and not failed
    journal("essential_services_repair", restored=done, failed=failed)
    parts = []
    if done:
        parts.append(f"{len(done)} serviço(s) devolvido(s) ao padrão do Windows e confirmado(s): "
                     + ", ".join(done) + ".")
    if failed:
        parts.append("Não confirmado: " + ", ".join(failed) + ".")
    return ok, " ".join(parts)


# ==================== ESTADO DESEJADO: "APLICOU = FICA" ====================
#
# O bug que isto conserta, medido num PC real: as configuracoes diziam
# `persistent_game_mode: True` e `latency_engine_autostart: True`, e depois de um
# reinicio o Game Mode estava DESLIGADO e o timer em `mode: off`. O app registrava
# a intencao do usuario e nunca voltava para conferir.
#
# Do ponto de vista do cliente isso e simplesmente "reiniciei e perdi tudo" - e
# ele esta certo. O Windows, a Game Bar e o software do fabricante reescrevem
# essas chaves por conta propria; um otimizador que aplica uma vez e nunca mais
# olha esta apostando que ninguem vai mexer.
#
# A solucao NAO e criar tarefa agendada nem inicializacao automatica (a build
# limpa proibe isso, e com razao: era a origem dos popups de VBS). E um livro de
# registro: todo apply bem-sucedido grava o id do tweak aqui, e toda abertura do
# AZOR reconfere a lista e reaplica o que saiu do lugar. Reverter apaga a
# entrada, entao desfazer continua sendo desfazer para sempre.

DESIRED_FILE = DATA_DIR / "desired_state.json"


def desired_state() -> Dict[str, Any]:
    data = _safe_json_read(DESIRED_FILE, {})
    if not isinstance(data, dict):
        return {"tasks": {}}
    data.setdefault("tasks", {})
    if not isinstance(data["tasks"], dict):
        data["tasks"] = {}
    return data


def mark_task_applied(task_id: str, name: str = "", profile: str = "") -> None:
    """Registra que o usuário QUER este tweak aplicado, daqui para frente."""
    task_id = str(task_id or "").strip()
    if not task_id:
        return
    data = desired_state()
    entry = data["tasks"].get(task_id) or {}
    entry.update({
        "name": name or entry.get("name") or task_id,
        "profile": profile or entry.get("profile") or "",
        "applied_at": _ts(),
        "first_applied_at": entry.get("first_applied_at") or _ts(),
    })
    data["tasks"][task_id] = entry
    data["updated_at"] = _ts()
    _safe_json_write(DESIRED_FILE, data)


def unmark_task_applied(task_id: str) -> None:
    """Desfazer e para sempre: a reconciliacao não pode ressuscitar o tweak."""
    task_id = str(task_id or "").strip()
    data = desired_state()
    if task_id in data["tasks"]:
        data["tasks"].pop(task_id, None)
        data["updated_at"] = _ts()
        _safe_json_write(DESIRED_FILE, data)
        journal("desired_state_removed", id=task_id)


def desired_task_ids() -> List[str]:
    return sorted(desired_state().get("tasks", {}).keys())


def reconcile_desired_state(dry_run: bool = False) -> Dict[str, Any]:
    """Reconfere tudo que já foi aplicado e reaplica o que saiu do lugar.

    Roda na abertura do AZOR. Tres resultados possiveis por item:
      mantido    - o verify confirmou; nada a fazer
      restaurado - tinha saido do lugar e voltou (o caso do Game Mode após reboot)
      falhou     - saiu do lugar e não foi possível devolver; aparece na tela

    `dry_run` responde "o que você faria" sem escrever nada, para a tela poder
    mostrar o diagnóstico antes de agir.
    """
    result: Dict[str, Any] = {"ok": True, "checked": 0, "kept": [], "restored": [],
                              "failed": [], "unknown": [], "dry_run": bool(dry_run),
                              "time": _ts()}
    wanted = desired_state().get("tasks", {})
    if not wanted:
        result["detail"] = "Nenhum ajuste registrado ainda. O primeiro BOOST cria a lista."
        return result
    try:
        from azor_modules.engine import _all_tasks, _context
        tasks = {t.id: t for t in _all_tasks()}
    except Exception as exc:
        log(f"Reconcile could not load the catalog: {exc}")
        return {**result, "ok": False, "detail": str(exc)}

    ctx = None
    for task_id, entry in wanted.items():
        task = tasks.get(task_id)
        if task is None:
            result["unknown"].append(task_id)
            continue
        result["checked"] += 1
        label = task.name
        if task.verify is None:
            # Sem releitura nao da para saber se saiu do lugar; nao reaplicamos no
            # escuro. A limpeza de temporarios e o caso tipico.
            result["kept"].append({"id": task_id, "name": label, "detail": "sem releitura disponível"})
            continue
        try:
            if ctx is None:
                ctx = _context(_core_self(), str(entry.get("profile") or "auto"))
            ok, detail = _normalize(task.verify(_core_self(), ctx))
        except Exception as exc:
            result["failed"].append({"id": task_id, "name": label, "detail": f"releitura falhou: {exc}"})
            continue
        if ok:
            result["kept"].append({"id": task_id, "name": label, "detail": detail})
            continue
        if dry_run:
            result["restored"].append({"id": task_id, "name": label, "detail": "saiu do lugar (simulacao)"})
            continue
        if task.apply is None:
            result["failed"].append({"id": task_id, "name": label, "detail": "sem aplicação automática"})
            continue
        try:
            aok, adetail = _normalize(task.apply(_core_self(), ctx))
            if aok and task.verify:
                vok, vdetail = _normalize(task.verify(_core_self(), ctx))
                aok = vok
                adetail = vdetail or adetail
        except Exception as exc:
            aok, adetail = False, str(exc)
        if aok:
            # O que o Windows desfaz com frequencia e a informacao mais util que
            # este ciclo produz - mais util, inclusive, que o proprio conserto.
            record_drift(task_id, label)
        (result["restored"] if aok else result["failed"]).append(
            {"id": task_id, "name": label, "detail": adetail})

    result["ok"] = not result["failed"]
    parts = []
    if result["restored"]:
        parts.append(f"{len(result['restored'])} ajuste(s) tinham saido do lugar e foram restaurados")
    if result["kept"]:
        parts.append(f"{len(result['kept'])} continuavam corretos")
    if result["failed"]:
        parts.append(f"{len(result['failed'])} não puderam ser restaurados")
    result["detail"] = ("; ".join(parts) + "." if parts else "Nada a reconciliar.")
    if not dry_run:
        journal("reconcile", checked=result["checked"],
                restored=[x["id"] for x in result["restored"]],
                failed=[x["id"] for x in result["failed"]])
        log(f"Reconcile: {result['detail']}")
    return result


def _core_self():
    """O próprio módulo, para as funcoes do catalogo que esperam receber `core`.

    Descobrir que `sys` não estava importado neste arquivo veio daqui: a
    reconciliacao inteira falhava com um NameError que aparecia na tela apenas
    como "3 não puderam ser restaurados". O mesmo faltava em _runtime_pythonw().
    """
    return sys.modules[__name__]


def _normalize(value: Any) -> Tuple[bool, str]:
    from azor_modules.base import normalize_result
    return normalize_result(value)




STARTUP_REPORT: Dict[str, Any] = {"done": False}


def run_startup_reconcile() -> Dict[str, Any]:
    """Chamado uma vez, numa thread, quando o backend sobe."""
    global STARTUP_REPORT
    report: Dict[str, Any] = {"done": True, "time": _ts()}
    try:
        report["session"] = []  # Opening is read-only; session engines require explicit activation.
    except Exception as exc:
        report["session"] = []
        log(f"Session engine restore failed: {exc}")
    try:
        report["reboot"] = confirm_after_reboot()
    except Exception as exc:
        report["reboot"] = {"pending": 0, "confirmed": [], "failed": [], "waiting": []}
        log(f"Post-reboot confirmation failed: {exc}")
    try:
        report["reconcile"] = reconcile_desired_state(dry_run=True)
    except Exception as exc:
        report["reconcile"] = {"ok": False, "detail": str(exc)}
        log(f"Startup reconcile failed: {exc}")
    STARTUP_REPORT = report
    return report




# ==================== REINICIAR DIRETO PARA A BIOS/UEFI ====================
#
# O BIOS Copiloto ja dizia o caminho do menu de cada fabricante ("aperte DEL na
# hora do boot"). Isso falha na pratica: em PC com boot rapido a janela para
# apertar a tecla e de fracao de segundo, e o cliente tenta cinco vezes.
#
# O Windows tem uma forma oficial de pedir isso: reiniciar direto para a
# configuracao do firmware. So funciona em UEFI, entao o app confere ANTES em vez
# de mandar um comando que falha em silencio numa maquina legada.

FIRMWARE_TYPE_UNKNOWN, FIRMWARE_TYPE_BIOS, FIRMWARE_TYPE_UEFI = 0, 1, 2


def _affinity_policy_path(instance: str) -> str:
    return ("SYSTEM\\CurrentControlSet\\Enum\\" + str(instance).strip("\\")
            + "\\Device Parameters\\Interrupt Management\\Affinity Policy")


# DevicePriority: 0 = indefinido, 1 = baixa, 2 = normal, 3 = alta. E a mesma
# opcao que a Interrupt Affinity Policy Tool da Microsoft grava, e ela decide
# quem e atendido primeiro quando duas interrupcoes chegam juntas.
DEVICE_PRIORITY_HIGH = 3


def gpu_interrupt_priority_state() -> Dict[str, Any]:
    rows = []
    for gpu in gpu_pci_instances():
        entry = reg_read("HKLM", _affinity_policy_path(gpu["instance"]), "DevicePriority")
        rows.append({"name": gpu["name"], "instance": gpu["instance"],
                     "value": entry.get("value"),
                     "high": entry.get("exists") and entry.get("value") == DEVICE_PRIORITY_HIGH})
    return {"gpus": rows, "all_high": bool(rows) and all(r["high"] for r in rows)}


def set_gpu_interrupt_priority_verified(high: bool = True) -> Tuple[bool, str]:
    gpus = gpu_pci_instances()
    if not gpus:
        return False, "Nenhuma GPU no barramento PCI foi encontrada."
    values = [{"root": "HKLM", "path": _affinity_policy_path(g["instance"]),
               "name": "DevicePriority", "value": DEVICE_PRIORITY_HIGH if high else 0}
              for g in gpus]
    ok, detail = write_registry_values_verified(values)
    journal("gpu_interrupt_priority", high=high, gpus=[g["name"] for g in gpus], ok=ok)
    if not ok:
        return ok, detail
    return True, (f"Prioridade de interrupção alta gravada e relida em: "
                  f"{', '.join(g['name'] for g in gpus)}. So passa a valer depois de reiniciar.")


# ==================== INTERRUPCOES DO USB NOS NUCLEOS E ====================
#
# Controle ou mouse em 4K/8K manda de 4 a 8 mil relatorios por segundo. Cada um
# vira interrupcao e DPC na controladora USB, e o Windows entrega tudo num nucleo
# so. Medido num i5-13400F com um GameSir em 8K e o Fortnite aberto: o nucleo 0
# recebia 10 mil interrupcoes e 10 mil DPCs por segundo (14% do tempo dele),
# contra ~100 DPCs/s nos outros. O nucleo 0 e P - onde roda a thread principal
# do jogo, que ja estava em 93%. Em CPU hibrida os nucleos E existem para esse
# trabalho. A politica de afinidade (a mesma da Interrupt Affinity Policy Tool da
# Microsoft) manda para eles as interrupcoes da controladora onde o controle esta
# conectado. So vale depois de reiniciar.

IRQ_POLICY_SPECIFIED_PROCESSORS = 4
USB_IRQ_FILE = DATA_DIR / "usb_irq_hosts.json"
_PCI_INSTANCE_RE = re.compile(r"PCI\\[A-Za-z0-9&_\\]+")


def _core_efficiency_classes(raw: bytes) -> List[Tuple[int, int, int]]:
    """(EfficiencyClass, grupo, mascara) de cada núcleo, lidos de um buffer de
    GetLogicalProcessorInformationEx(RelationProcessorCore).

    PROCESSOR_RELATIONSHIP: Flags no byte 8, EfficiencyClass no 9, GroupCount no
    30 e o primeiro GROUP_AFFINITY no 32 (Mask de 8 bytes + Group de 2).
    """
    cores: List[Tuple[int, int, int]] = []
    off = 0
    while off + 8 <= len(raw):
        rel, entry_size = struct.unpack_from("<II", raw, off)
        if entry_size <= 0 or off + entry_size > len(raw):
            break
        if rel == _RELATION_PROCESSOR_CORE and entry_size >= 42:
            if struct.unpack_from("<H", raw, off + 30)[0] >= 1:
                mask, group = struct.unpack_from("<QH", raw, off + 32)
                cores.append((int(raw[off + 9]), int(group), int(mask)))
        off += entry_size
    return cores


def _efficiency_mask_from_cores(cores: List[Tuple[int, int, int]]) -> int:
    """Nucleos com EfficiencyClass abaixo da maior, no grupo 0. 0 se todos iguais."""
    classes = {c[0] for c in cores}
    if len(classes) < 2:
        return 0
    top = max(classes)
    out = 0
    for eff, group, mask in cores:
        if eff < top and group == 0:
            out |= mask
    return out


def efficiency_core_mask(force: bool = False) -> int:
    """Mascara, no grupo 0, dos processadores logicos dos núcleos E; 0 se não hibrido."""
    def probe() -> int:
        if os.name != "nt":
            return 0
        try:
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            size = ctypes.c_ulong(0)
            k32.GetLogicalProcessorInformationEx(_RELATION_PROCESSOR_CORE, None, ctypes.byref(size))
            if not size.value:
                return 0
            buf = ctypes.create_string_buffer(size.value)
            if not k32.GetLogicalProcessorInformationEx(_RELATION_PROCESSOR_CORE, buf, ctypes.byref(size)):
                return 0
            cores = _core_efficiency_classes(buf.raw[:size.value])
        except Exception as exc:
            log_debug(f"efficiency_core_mask falhou: {exc}")
            return 0
        return _efficiency_mask_from_cores(cores)
    return int(cached_reading("efficiency_core_mask", 3600.0, probe, force=force) or 0)


def usb_hosts_with_game_controller(force: bool = False) -> List[Dict[str, Any]]:
    """Controladoras USB (instância PCI) onde ha controle de jogo conectado agora."""
    def probe() -> List[Dict[str, Any]]:
        if os.name != "nt":
            return []
        script = r"""
$ErrorActionPreference='SilentlyContinue'
function P($id){ (Get-PnpDeviceProperty -InstanceId $id -KeyName DEVPKEY_Device_Parent).Data }
$pads = @(Get-PnpDevice -PresentOnly | Where-Object {
  $_.Class -in @('XnaComposite','XboxComposite') -or
  ($_.Class -eq 'HIDClass' -and [string]$_.FriendlyName -match 'jogo|game controller|gamepad|joystick') })
$rows = @()
foreach ($d in $pads) {
  $c = $d.InstanceId; $pci = $null
  for ($i = 0; $i -lt 12 -and $c; $i++) { if ($c -like 'PCI\*') { $pci = $c; break }; $c = P $c }
  if ($pci) {
    $h = Get-PnpDevice -InstanceId $pci
    $rows += [pscustomobject]@{pad=[string]$d.FriendlyName; host=[string]$pci; host_name=[string]$h.FriendlyName}
  }
}
$rows
"""
        try:
            data = powershell_json(script, timeout=40)
        except Exception as exc:
            log_debug(f"usb_hosts_with_game_controller falhou: {exc}")
            return []
        rows = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
        hosts: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            inst = str((r or {}).get("host") or "")
            if not _PCI_INSTANCE_RE.fullmatch(inst):
                continue
            h = hosts.setdefault(inst.upper(), {"instance": inst, "name": str(r.get("host_name") or inst),
                                                "controllers": []})
            pad = str(r.get("pad") or "")
            if pad and pad not in h["controllers"]:
                h["controllers"].append(pad)
        return list(hosts.values())
    return cached_reading("usb_hosts_with_game_controller", 30.0, probe, force=force) or []


def _usb_irq_known_hosts() -> List[str]:
    """Controladoras em que o AZOR já gravou a afinidade (para o desfazer achar)."""
    try:
        data = json.loads(USB_IRQ_FILE.read_text(encoding="utf-8")) if USB_IRQ_FILE.exists() else {}
        return [str(h) for h in (data.get("hosts") or []) if _PCI_INSTANCE_RE.fullmatch(str(h))]
    except Exception:
        return []


def usb_interrupt_affinity_state(force: bool = False) -> Dict[str, Any]:
    """Para onde vao hoje as interrupções da controladora do controle, pelo registro."""
    mask = efficiency_core_mask()
    rows = []
    for h in usb_hosts_with_game_controller(force=force):
        path = _affinity_policy_path(h["instance"])
        policy = reg_read("HKLM", path, "DevicePolicy")
        override = reg_read("HKLM", path, "AssignmentSetOverride")
        value = override.get("value")
        current = int.from_bytes(bytes(value), "little") if isinstance(value, (bytes, bytearray)) else None
        rows.append({**h, "policy": policy.get("value"), "mask": current,
                     "on_ecores": bool(mask) and policy.get("value") == IRQ_POLICY_SPECIFIED_PROCESSORS
                                  and current == mask})
    return {"hosts": rows, "ecore_mask": mask, "hybrid": bool(mask),
            "ecore_cpus": [i for i in range(64) if mask >> i & 1],
            "all_on_ecores": bool(rows) and all(r["on_ecores"] for r in rows)}


def set_usb_interrupts_on_ecores_verified() -> Tuple[bool, str]:
    """Grava DevicePolicy = 4 e AssignmentSetOverride = núcleos E, e rele."""
    if os.name != "nt" or winreg is None:
        return False, "Disponível só no Windows."
    if not is_admin():
        return False, "Gravar a afinidade de interrupção exige administrador."
    state = usb_interrupt_affinity_state(force=True)
    mask = state["ecore_mask"]
    if not mask:
        return False, "Este processador não tem núcleos E; nada foi alterado."
    hosts = state["hosts"]
    if not hosts:
        return False, "Nenhum controle de jogo conectado por USB foi encontrado; nada foi alterado."
    entries = [("HKLM", _affinity_policy_path(h["instance"]), name)
               for h in hosts for name in ("DevicePolicy", "AssignmentSetOverride")]
    baseline_backfill_registry(entries)
    known = sorted(set(_usb_irq_known_hosts()) | {h["instance"] for h in hosts})
    _safe_json_write(USB_IRQ_FILE, {"hosts": known, "mask": mask, "updated_at": _ts()})
    failed = []
    for h in hosts:
        path = _affinity_policy_path(h["instance"])
        try:
            reg_write("HKLM", path, "DevicePolicy", IRQ_POLICY_SPECIFIED_PROCESSORS, winreg.REG_DWORD)
            reg_write("HKLM", path, "AssignmentSetOverride", int(mask).to_bytes(8, "little"), winreg.REG_BINARY)
        except Exception as exc:
            failed.append(f"{h['name']} ({exc})")
    after = usb_interrupt_affinity_state()
    ok = not failed and after["all_on_ecores"]
    journal("usb_interrupts_ecores", hosts=[h["name"] for h in hosts], mask=mask, ok=ok, failed=failed)
    if not ok:
        return False, "Não confirmado: " + ("; ".join(failed) if failed else "a releitura não bateu.")
    cpus = ", ".join(str(c) for c in after["ecore_cpus"])
    return True, (f"Interrupcoes de {', '.join(h['name'] for h in hosts)} direcionadas aos núcleos E "
                  f"(processadores {cpus}), gravadas e relidas. So passa a valer depois de reiniciar.")


def usb_interrupt_affinity_revert() -> Tuple[bool, str]:
    """Volta ao que estava antes do AZOR nas controladoras que ele tocou."""
    instances = _usb_irq_known_hosts() or [h["instance"] for h in usb_hosts_with_game_controller(force=True)]
    entries = [("HKLM", _affinity_policy_path(i), name) for i in sorted(set(instances))
               for name in ("DevicePolicy", "AssignmentSetOverride")]
    if not entries:
        return False, "Nenhuma controladora USB registrada para reverter."
    ok, detail = revert_registry_from_baseline(entries, "usb_interrupts_ecores")
    return ok, (detail + " So passa a valer depois de reiniciar.") if ok else detail


class _PdhItem(ctypes.Structure):
    _fields_ = [("name", ctypes.c_wchar_p), ("status", ctypes.c_ulong), ("value", ctypes.c_double)]


def interrupt_load_by_cpu(seconds: float = 2.0) -> Dict[str, Any]:
    """Interrupcoes e DPCs por processador logico agora, pelo PDH com nomes em ingles.

    A classe do WMI para esses contadores não existe em todo Windows (no PC onde
    isto foi medido, "Classe invalida"); o PdhAddEnglishCounter funciona em
    qualquer idioma.
    """
    if os.name != "nt":
        return {"ok": False, "rows": [], "detail": "Disponível só no Windows."}
    seconds = min(max(float(seconds or 2.0), 0.5), 5.0)
    try:
        pdh = ctypes.WinDLL("pdh.dll")
    except Exception as exc:
        return {"ok": False, "rows": [], "detail": str(exc)}
    query = ctypes.c_void_p()
    if pdh.PdhOpenQueryW(None, None, ctypes.byref(query)) != 0:
        return {"ok": False, "rows": [], "detail": "O Windows não abriu a consulta de desempenho."}
    paths = {"interrupts": r"\Processor Information(*)\Interrupts/sec",
             "dpcs": r"\Processor Information(*)\DPCs Queued/sec",
             "interrupt_pct": r"\Processor Information(*)\% Interrupt Time",
             "dpc_pct": r"\Processor Information(*)\% DPC Time"}
    rows: Dict[int, Dict[str, Any]] = {}
    try:
        counters = {}
        for key, path in paths.items():
            handle = ctypes.c_void_p()
            if pdh.PdhAddEnglishCounterW(query, ctypes.c_wchar_p(path), None, ctypes.byref(handle)) == 0:
                counters[key] = handle
        if not counters:
            return {"ok": False, "rows": [], "detail": "Contadores de processador indisponiveis."}
        pdh.PdhCollectQueryData(query)
        time.sleep(seconds)
        pdh.PdhCollectQueryData(query)
        for key, handle in counters.items():
            size, count = ctypes.c_ulong(0), ctypes.c_ulong(0)
            pdh.PdhGetFormattedCounterArrayW(handle, 0x200, ctypes.byref(size), ctypes.byref(count), None)
            if not size.value:
                continue
            buf = ctypes.create_string_buffer(size.value)
            if pdh.PdhGetFormattedCounterArrayW(handle, 0x200, ctypes.byref(size), ctypes.byref(count), buf) != 0:
                continue
            items = ctypes.cast(buf, ctypes.POINTER(_PdhItem))
            for i in range(count.value):
                m = re.fullmatch(r"0,(\d+)", str(items[i].name or ""))
                if m:
                    rows.setdefault(int(m.group(1)), {"cpu": int(m.group(1))})[key] = round(float(items[i].value), 2)
    finally:
        pdh.PdhCloseQuery(query)
    ecores = efficiency_core_mask()
    ordered = [rows[k] for k in sorted(rows)]
    for r in ordered:
        r["efficiency"] = bool(ecores >> r["cpu"] & 1)
        r["busy_pct"] = round(float(r.get("interrupt_pct") or 0) + float(r.get("dpc_pct") or 0), 2)
    busiest = max(ordered, key=lambda r: float(r.get("dpcs") or 0), default=None)
    others = sorted(float(r.get("dpcs") or 0) for r in ordered if r is not busiest)
    return {"ok": bool(ordered), "seconds": seconds, "rows": ordered, "busiest": busiest,
            "others_median_dpcs": others[len(others) // 2] if others else None, "measured_at": _ts()}


SUB_DISK_GUID = "0012ee47-9041-4b5d-9b77-535fba8b1442"
NVME_IDLE_TIMEOUT_GUID = "d639518a-e56d-4345-8af2-b9f32fb26109"


def nvme_idle_state() -> Dict[str, Any]:
    """Tempo até o NVMe entrar em estado de baixa energia. 0 = nunca."""
    if os.name != "nt":
        return {"readable": False}
    try:
        p = run_hidden(["powercfg", "/Q", "SCHEME_CURRENT", SUB_DISK_GUID,
                        NVME_IDLE_TIMEOUT_GUID], timeout=12)
        if p.returncode != 0:
            return {"readable": False, "hidden": True,
                    "detail": ("O tempo de inatividade do NVMe vem oculto nas opcoes de energia. "
                               "O AZOR revela ao aplicar e volta a oculta-lo ao reverter.")}
        vals = re.findall(r"0x([0-9a-fA-F]{8})", (p.stdout or ""))
        if len(vals) < 2:
            return {"readable": False, "hidden": True,
                    "detail": "Este PC não expõe o tempo de inatividade do NVMe."}
        return {"readable": True, "ac": int(vals[-2], 16), "dc": int(vals[-1], 16),
                "never": int(vals[-2], 16) == 0}
    except Exception as exc:
        return {"readable": False, "detail": str(exc)}


def set_nvme_idle_never_verified(never: bool = True) -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Disponível só no Windows."
    if not is_admin():
        return False, "Alterar a energia do NVMe exige o AZOR aberto como administrador."
    before = nvme_idle_state()
    if not before.get("readable"):
        run_hidden(["powercfg", "-attributes", SUB_DISK_GUID, NVME_IDLE_TIMEOUT_GUID,
                    "-ATTRIB_HIDE"], timeout=12)
        before = nvme_idle_state()
        if not before.get("readable"):
            return False, before.get("detail") or "O ajuste não esta exposto neste PC."
    baseline_backfill("nvme_idle", before)
    want = 0 if never else int(before.get("ac") or 200)
    for cmd in (["powercfg", "/SETACVALUEINDEX", "SCHEME_CURRENT", SUB_DISK_GUID,
                 NVME_IDLE_TIMEOUT_GUID, str(want)],
                ["powercfg", "/SETACTIVE", "SCHEME_CURRENT"]):
        p = run_hidden(cmd, timeout=12)
        if p.returncode != 0:
            return False, (p.stderr or p.stdout or "powercfg recusou o comando.").strip()[:300]
    after = nvme_idle_state()
    ok = after.get("ac") == want
    journal("nvme_idle", never=never, after=after.get("ac"), ok=ok)
    return ok, (("O NVMe deixa de entrar em estado de baixa energia no plano ativo, confirmado por "
                 "releitura. O primeiro acesso depois de um periodo parado para de custar o tempo de "
                 "acordar o controlador.") if ok and never else
                ("Tempo de inatividade do NVMe devolvido ao Windows e confirmado." if ok else
                 f"Foi pedido {want}, mas o powercfg reporta {after.get('ac')}."))


def hibernate_state(force: bool = False) -> Dict[str, Any]:
    """A hibernacao esta disponível? Lido pelo próprio powercfg.

    A detecção e pela PRESENCA do arquivo de hibernacao e pelo que o
    `powercfg /a` lista como disponível; o texto e traduzido, então a leitura
    olha o hiberfil.sys, que não e.
    """
    def probe() -> Dict[str, Any]:
        if os.name != "nt":
            return {}
        system_drive = os.environ.get("SystemDrive", "C:")
        hiberfil = Path(system_drive + "\\hiberfil.sys")
        size_gb = None
        try:
            if hiberfil.exists():
                size_gb = round(hiberfil.stat().st_size / (1024 ** 3), 1)
        except Exception:
            pass
        entry = reg_read("HKLM", r"SYSTEM\CurrentControlSet\Control\Power", "HibernateEnabled")
        enabled = bool(entry.get("value")) if entry.get("exists") else (size_gb is not None)
        return {"readable": True, "enabled": enabled, "file_gb": size_gb}
    return cached_reading("hibernate", 300.0, probe, force=force) or {}


def set_hibernate_verified(enabled: bool) -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Disponível só no Windows."
    if not is_admin():
        return False, "Alterar a hibernação exige o AZOR aberto como administrador."
    before = hibernate_state()
    baseline_backfill("hibernate", before)
    p = run_hidden(["powercfg", "/hibernate", "on" if enabled else "off"], timeout=30)
    if p.returncode != 0:
        return False, (p.stdout or p.stderr or "").strip()[:300] or "O powercfg recusou o comando."
    after = hibernate_state(force=True)
    ok = bool(after.get("enabled")) is bool(enabled)
    journal("hibernate", enabled=enabled, after=after.get("enabled"), ok=ok)
    freed = before.get("file_gb")
    return ok, (("Hibernação desligada e confirmada" + (f"; {freed} GB liberados do disco do sistema." if freed else ".")
                 + " A Inicialização Rápida depende dela, então ela também deixa de existir.")
                if ok and not enabled else
                ("Hibernação religada e confirmada." if ok else
                 f"Foi pedido {enabled}, mas o Windows reporta {after.get('enabled')}."))


def disk_write_cache_state() -> Dict[str, Any]:
    """Cache de escrita por disco. 0 explicito = alguém desligou.

    Ausente significa o padrão do Windows, que e LIGADO - e por isso ausencia
    não e tratada como problema.
    """
    if os.name != "nt":
        return {"readable": False}
    def probe() -> Dict[str, Any]:
        try:
            data = powershell_json(
                "@(Get-PnpDevice -Class DiskDrive -Status OK -ErrorAction SilentlyContinue|"
                "Select-Object FriendlyName,InstanceId)", timeout=30) or []
            if isinstance(data, dict):
                data = [data]
        except Exception as exc:
            return {"readable": False, "detail": str(exc)}
        rows = []
        for dev in data:
            if not isinstance(dev, dict) or not dev.get("InstanceId"):
                continue
            path = ("SYSTEM\\CurrentControlSet\\Enum\\" + str(dev["InstanceId"]).strip("\\")
                    + "\\Device Parameters\\Disk")
            entry = reg_read("HKLM", path, "UserWriteCacheSetting")
            rows.append({"name": str(dev.get("FriendlyName") or ""), "path": path,
                         "value": entry.get("value"),
                         "disabled": bool(entry.get("exists")) and entry.get("value") == 0})
        return {"readable": True, "disks": rows,
                "off": [r for r in rows if r["disabled"]]}
    return cached_reading("write_cache", 300.0, probe) or {}


def enable_write_cache_verified() -> Tuple[bool, str]:
    state = disk_write_cache_state()
    off = state.get("off") or []
    if not off:
        return True, "O cache de escrita já está habilitado em todos os discos."
    values = [{"root": "HKLM", "path": d["path"], "name": "UserWriteCacheSetting", "value": 1}
              for d in off]
    ok, detail = write_registry_values_verified(values)
    journal("write_cache_repair", disks=[d["name"] for d in off], ok=ok)
    return ok, ((f"Cache de escrita religado e confirmado em: {', '.join(d['name'] for d in off)}. "
                 "Só passa a valer depois de reiniciar.") if ok else detail)


def defender_status(force: bool = False) -> Dict[str, Any]:
    """O Defender e o antivirus ATIVO deste PC, e o que ele já exclui.

    A pergunta importa: com antivirus de terceiro no comando, o Defender fica em
    modo passivo e excluir pasta nele não muda nada - seria um tweak que finge.
    """
    def probe() -> Dict[str, Any]:
        if os.name != "nt":
            return {"readable": False}
        try:
            data = powershell_json(
                "$s=Get-MpComputerStatus -ErrorAction SilentlyContinue;"
                "$p=Get-MpPreference -ErrorAction SilentlyContinue;"
                "if(-not $s){return};"
                "[pscustomobject]@{Mode=[string]$s.AMRunningMode;RT=[bool]$s.RealTimeProtectionEnabled;"
                "Excl=@($p.ExclusionPath)}", timeout=40) or {}
            if isinstance(data, list):
                data = data[0] if data else {}
            excl = (data or {}).get("Excl") or []
            if isinstance(excl, str):
                excl = [excl]
            mode = str((data or {}).get("Mode") or "")
            return {"readable": True, "mode": mode,
                    "active": "normal" in mode.lower(),
                    "realtime": bool((data or {}).get("RT")),
                    "exclusions": [str(x) for x in excl if x]}
        except Exception as exc:
            return {"readable": False, "detail": str(exc)}
    return cached_reading("defender", 180.0, probe, force=force) or {}


def game_folders() -> List[str]:
    """Pastas de instalacao dos jogos encontrados, sem repetir subpasta."""
    roots = set()
    for game in detect_installed_games():
        try:
            path = Path(str(game.get("exe") or "")).resolve()
            for parent in list(path.parents)[:4]:
                name = parent.name.lower()
                if name in ("common", "steamapps", "epic games", "riot games", "games"):
                    break
                candidate = parent
            roots.add(str(candidate))
        except Exception:
            continue
    # Remove pastas contidas em outra ja listada.
    out = []
    for r in sorted(roots, key=len):
        if not any(r.lower().startswith(o.lower() + "\\") for o in out):
            out.append(r)
    return out[:12]


def set_defender_exclusions_verified(paths: List[str], add: bool = True) -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Disponível só no Windows."
    if not is_admin():
        return False, "Alterar exclusoes do Defender exige o AZOR aberto como administrador."
    if not paths:
        return False, "Nenhuma pasta de jogo foi localizada; nada foi alterado."
    before = defender_status()
    baseline_backfill("defender_exclusions", before.get("exclusions") or [])
    verb = "Add-MpPreference" if add else "Remove-MpPreference"
    quoted = ",".join("'" + p.replace("'", "''") + "'" for p in paths)
    try:
        powershell(f"{verb} -ExclusionPath @({quoted}) -ErrorAction Stop; 'OK'", timeout=60)
    except Exception as exc:
        return False, f"O Defender recusou a mudanca: {exc}"
    after = defender_status(force=True)
    have = {str(x).lower() for x in (after.get("exclusions") or [])}
    missing = [p for p in paths if p.lower() not in have] if add else [p for p in paths if p.lower() in have]
    ok = not missing
    journal("defender_exclusions", add=add, paths=paths, ok=ok)
    return ok, ((f"{len(paths)} pasta(s) de jogo {'excluida(s)' if add else 'devolvida(s)'} e "
                 "confirmada(s) pelo Get-MpPreference: " + ", ".join(paths[:3])
                 + (f" e mais {len(paths)-3}." if len(paths) > 3 else "."))
                if ok else "Não confirmado para: " + ", ".join(missing[:3]))


def nic_rss_state(alias: str) -> Optional[bool]:
    """Receive Side Scaling: distribui as interrupções da rede entre núcleos."""
    if os.name != "nt" or not alias:
        return None
    def probe() -> Optional[bool]:
        try:
            data = powershell_json(
                "$r=Get-NetAdapterRss -Name '" + alias.replace("'", "''") + "' -ErrorAction SilentlyContinue;"
                "if($r){[pscustomobject]@{On=[string]$r.Enabled}}", timeout=25) or {}
            if isinstance(data, list):
                data = data[0] if data else {}
            raw = str((data or {}).get("On") or "").strip().lower()
            return True if raw in ("true", "1") else (False if raw in ("false", "0") else None)
        except Exception:
            return None
    return cached_reading(f"nic_rss:{alias}", 180.0, probe)


def set_nic_rss_verified(alias: str, enabled: bool = True) -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Disponível só no Windows."
    if not is_admin():
        return False, "Alterar o RSS do adaptador exige o AZOR aberto como administrador."
    before = nic_rss_state(alias)
    if before is None:
        return False, f"O driver de '{alias}' não expõe RSS; nada foi alterado."
    baseline_backfill(f"nic_rss:{alias}", before)
    verb = "Enable-NetAdapterRss" if enabled else "Disable-NetAdapterRss"
    try:
        powershell(f"{verb} -Name '" + alias.replace("'", "''") + "' -ErrorAction Stop; 'OK'", timeout=45)
    except Exception as exc:
        return False, f"O Windows recusou a mudanca de RSS: {exc}"
    invalidate_cache(f"nic_rss:{alias}")
    after = nic_rss_state(alias)
    ok = after is bool(enabled)
    journal("nic_rss", alias=alias, enabled=enabled, after=after, ok=ok)
    return ok, (f"RSS {'ligado' if enabled else 'desligado'} em {alias} e relido do driver."
                if ok else f"Foi pedido {enabled}, mas o driver reporta {after}.")


def firmware_type() -> Dict[str, Any]:
    """BIOS legado ou UEFI, pela API do Windows (sem abrir processo)."""
    if os.name != "nt":
        return {"supported": False, "uefi": None, "label": "Disponível só no Windows."}
    try:
        value = ctypes.c_uint(0)
        ok = ctypes.windll.kernel32.GetFirmwareType(ctypes.byref(value))
        if not ok:
            return {"supported": False, "uefi": None, "label": "O Windows não respondeu o tipo de firmware."}
        kind = int(value.value)
        return {
            "supported": True, "type": kind,
            "uefi": kind == FIRMWARE_TYPE_UEFI,
            "label": {FIRMWARE_TYPE_UEFI: "UEFI", FIRMWARE_TYPE_BIOS: "BIOS legado"}.get(kind, "desconhecido"),
        }
    except Exception as exc:
        return {"supported": False, "uefi": None, "label": f"não foi possível ler: {exc}"}


def firmware_boot_status() -> Dict[str, Any]:
    """Da para reiniciar direto na BIOS deste PC? E o que falta, se não der."""
    fw = firmware_type()
    admin = is_admin()
    ready = bool(fw.get("uefi")) and admin
    if not fw.get("supported"):
        reason = fw.get("label") or "Tipo de firmware não confirmado."
    elif not fw.get("uefi"):
        reason = ("Este PC inicia em BIOS legado, e o Windows so sabe reiniciar direto para a "
                  "configuração em máquinas UEFI. Aqui o caminho continua sendo a tecla no boot.")
    elif not admin:
        reason = "Reiniciar para a UEFI exige o AZOR aberto como administrador."
    else:
        reason = "Pronto: o Windows reinicia direto na configuração da UEFI."
    return {"ready": ready, "uefi": fw.get("uefi"), "firmware": fw.get("label"),
            "admin": admin, "detail": reason}


def reboot_to_firmware(delay_seconds: int = 15) -> Dict[str, Any]:
    """Agenda o reinício para a UEFI, com folga para o usuário salvar o que estava fazendo."""
    status = firmware_boot_status()
    if not status.get("ready"):
        return {"ok": False, **status}
    delay = max(5, min(120, int(delay_seconds)))
    p = run_hidden(["shutdown", "/r", "/fw", "/t", str(delay),
                    "/c", "O AZOR vai reiniciar este PC direto na configuração da UEFI."], timeout=20)
    ok = p.returncode == 0
    journal("reboot_to_firmware", delay=delay, ok=ok, rc=p.returncode)
    if not ok:
        return {"ok": False, "detail": ((p.stdout or p.stderr or "").strip()[:300]
                                        or "O Windows recusou o reinício para o firmware.")}
    return {"ok": True, "delay": delay, "abortable": True,
            "detail": f"Reinício para a UEFI agendado em {delay} segundos. "
                      "Salve o que estiver aberto - ainda da para cancelar."}


def abort_reboot() -> Dict[str, Any]:
    """Cancela o reinício agendado. Existe porque agendar sem poder cancelar
    seria um botão que sequestra o PC do cliente."""
    if os.name != "nt":
        return {"ok": False, "detail": "Disponível só no Windows."}
    p = run_hidden(["shutdown", "/a"], timeout=15)
    ok = p.returncode == 0
    journal("abort_reboot", ok=ok, rc=p.returncode)
    return {"ok": ok, "detail": ("Reinício cancelado." if ok else
                                 "Não havia reinício agendado para cancelar.")}


# ==================== ALVOS POR COMPONENTE: RAM, CPU, GPU, PLACA E SSD ====================
#
# Tudo aqui segue a mesma regra do resto do catalogo: caminho de registro que so
# existe nesta maquina e descoberto em tempo de execucao e entra no baseline pelo
# backfill; nada retorna sucesso sem releitura.


def pci_instances(pnp_class: str, cache_key: str = "") -> List[Dict[str, Any]]:
    """Dispositivos PCI de uma classe, com o caminho de instância real.

    Generaliza o que so existia para vídeo. O caminho de instância e por máquina,
    então ele nunca poderia estar numa lista estatica de chaves.
    """
    if os.name != "nt":
        return []
    key = cache_key or f"pci:{pnp_class}"

    def probe() -> List[Dict[str, Any]]:
        try:
            data = powershell_json(
                "@(Get-PnpDevice -Class " + pnp_class + " -Status OK -ErrorAction SilentlyContinue|"
                "Where-Object {$_.InstanceId -like 'PCI*'}|"
                "Select-Object FriendlyName,InstanceId)", timeout=30) or []
            if isinstance(data, dict):
                data = [data]
            return [{"name": str(x.get("FriendlyName") or ""), "instance": str(x.get("InstanceId") or "")}
                    for x in data if isinstance(x, dict) and x.get("InstanceId")]
        except Exception as exc:
            log(f"PCI probe for {pnp_class} failed: {exc}")
            return []
    return cached_reading(key, 600.0, probe) or []


def device_msi_state(instances: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = []
    for dev in instances:
        entry = reg_read("HKLM", _msi_path(dev["instance"]), "MSISupported")
        rows.append({"name": dev["name"], "instance": dev["instance"],
                     "msi": None if not entry.get("exists") else entry.get("value") == 1,
                     "value": entry.get("value")})
    return {"devices": rows, "all_on": bool(rows) and all(r["msi"] is True for r in rows)}


def set_device_msi_verified(instances: List[Dict[str, Any]], enabled: bool = True) -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Disponível só no Windows."
    if not instances:
        return False, "Nenhum dispositivo correspondente foi encontrado; nada foi alterado."
    values = [{"root": "HKLM", "path": _msi_path(d["instance"]), "name": "MSISupported",
               "value": 1 if enabled else 0} for d in instances]
    ok, detail = write_registry_values_verified(values)
    journal("device_msi", devices=[d["name"] for d in instances], enabled=enabled, ok=ok)
    if not ok:
        return ok, detail
    return True, (f"MSI gravado e relido em: {', '.join(d['name'] for d in instances)}. "
                  "So passa a valer depois de reiniciar o Windows.")


# ---------------------------------------------------------------------------
# USB: energia dos hubs raiz
# ---------------------------------------------------------------------------

def usb_hub_instances() -> List[Dict[str, Any]]:
    """Hubs USB e controladores, onde vive a permissao de desligar por energia."""
    if os.name != "nt":
        return []

    def probe() -> List[Dict[str, Any]]:
        try:
            data = powershell_json(
                "@(Get-PnpDevice -Class USB -Status OK -ErrorAction SilentlyContinue|"
                "Where-Object {$_.FriendlyName -match 'Hub|Controlador|Controller'}|"
                "Select-Object FriendlyName,InstanceId)", timeout=30) or []
            if isinstance(data, dict):
                data = [data]
            return [{"name": str(x.get("FriendlyName") or ""), "instance": str(x.get("InstanceId") or "")}
                    for x in data if isinstance(x, dict) and x.get("InstanceId")][:24]
        except Exception as exc:
            log(f"USB hub probe failed: {exc}")
            return []
    return cached_reading("usb_hubs", 600.0, probe) or []


def _usb_power_path(instance: str) -> str:
    return (r"SYSTEM\CurrentControlSet\Enum" + "\\" + str(instance).strip("\\")
            + r"\Device Parameters")


def usb_hub_power_state() -> Dict[str, Any]:
    """True em `managed` = o Windows ainda pode desligar aquele hub."""
    rows = []
    for hub in usb_hub_instances():
        entry = reg_read("HKLM", _usb_power_path(hub["instance"]), "EnhancedPowerManagementEnabled")
        # Ausente significa comportamento padrao do driver, que e permitir.
        managed = True if not entry.get("exists") else entry.get("value") == 1
        rows.append({"name": hub["name"], "instance": hub["instance"], "managed": managed})
    return {"hubs": rows, "managed": [r for r in rows if r["managed"]],
            "all_off": bool(rows) and not any(r["managed"] for r in rows)}


def set_usb_hub_power_verified(managed: bool = False) -> Tuple[bool, str]:
    state = usb_hub_power_state()
    hubs = state.get("hubs") or []
    if not hubs:
        return False, "Nenhum hub USB foi encontrado; nada foi alterado."
    values = [{"root": "HKLM", "path": _usb_power_path(h["instance"]),
               "name": "EnhancedPowerManagementEnabled", "value": 1 if managed else 0}
              for h in hubs]
    ok, detail = write_registry_values_verified(values)
    journal("usb_hub_power", hubs=len(hubs), managed=managed, ok=ok)
    if not ok:
        return ok, detail
    return True, (f"{len(hubs)} hub(s) USB fora da economia de energia, gravados e relidos. "
                  "Vale a partir do próximo reinício do controlador ou do PC.")


# ---------------------------------------------------------------------------
# RAM: compressao de memoria
# ---------------------------------------------------------------------------

def memory_compression_state(force: bool = False) -> Dict[str, Any]:
    def probe() -> Dict[str, Any]:
        if os.name != "nt":
            return {}
        try:
            data = powershell_json(
                "$m=Get-MMAgent -ErrorAction SilentlyContinue;"
                "if($m){[pscustomobject]@{MC=[string]$m.MemoryCompression;"
                "PF=[string]$m.PageCombining}}", timeout=25) or {}
            if isinstance(data, list):
                data = data[0] if data else {}
            raw = str((data or {}).get("MC") or "").strip().lower()
            if raw in ("true", "1"):
                return {"readable": True, "enabled": True}
            if raw in ("false", "0"):
                return {"readable": True, "enabled": False}
            return {"readable": False, "enabled": None}
        except Exception as exc:
            return {"readable": False, "enabled": None, "detail": str(exc)}
    return cached_reading("memory_compression", 180.0, probe, force=force) or {}


def set_memory_compression_verified(enabled: bool) -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Disponível só no Windows."
    if not is_admin():
        return False, "Alterar a compressao de memória exige o AZOR aberto como administrador."
    before = memory_compression_state()
    baseline_backfill("memory_compression", before)
    verb = "Enable-MMAgent -mc" if enabled else "Disable-MMAgent -mc"
    try:
        powershell(f"{verb} -ErrorAction Stop; 'OK'", timeout=45)
    except Exception as exc:
        return False, f"O Windows recusou a mudanca: {exc}"
    after = memory_compression_state(force=True)
    ok = after.get("enabled") is bool(enabled)
    journal("memory_compression", enabled=enabled, after=after.get("enabled"), ok=ok)
    return ok, (f"Compressao de memoria {'ligada' if enabled else 'desligada'} e relida pelo Get-MMAgent."
                if ok else f"Foi pedido {enabled}, mas o Windows reporta {after.get('enabled')}.")


# ---------------------------------------------------------------------------
# CPU: estados ociosos
# ---------------------------------------------------------------------------

# GUIDs do subgrupo de processador e do ajuste IDLEDISABLE, documentados nas
# opcoes de linha de comando do powercfg. O Windows entrega os dois OCULTOS: sem
# revelar o atributo, `powercfg /Q` nao mostra o indice e o ajuste seria codigo
# morto na maioria das maquinas.
SUB_PROCESSOR_GUID = "54533251-82be-4824-96c1-47b60b740d00"
IDLEDISABLE_GUID = "5d76a2ca-e8c0-402f-a133-2158492d58ad"


def unhide_processor_idle_attribute() -> bool:
    """Revela IDLEDISABLE nas opcoes de energia. Reversivel por +ATTRIB_HIDE."""
    if os.name != "nt":
        return False
    try:
        p = run_hidden(["powercfg", "-attributes", SUB_PROCESSOR_GUID, IDLEDISABLE_GUID,
                        "-ATTRIB_HIDE"], timeout=12)
        invalidate_cache("processor_idle")
        return p.returncode == 0
    except Exception as exc:
        log(f"Unhide IDLEDISABLE failed: {exc}")
        return False


def hide_processor_idle_attribute() -> bool:
    if os.name != "nt":
        return False
    try:
        p = run_hidden(["powercfg", "-attributes", SUB_PROCESSOR_GUID, IDLEDISABLE_GUID,
                        "+ATTRIB_HIDE"], timeout=12)
        return p.returncode == 0
    except Exception:
        return False


def processor_idle_state(allow_unhide: bool = False) -> Dict[str, Any]:
    """IDLEDISABLE no esquema ativo: 1 = a CPU não entra em estado ocioso.

    `allow_unhide` so e usado no caminho de escrita: a leitura da tela não pode
    ter efeito colateral nas opcoes de energia do usuário.
    """
    if os.name != "nt":
        return {"readable": False}
    try:
        p = run_hidden(["powercfg", "/Q", "SCHEME_CURRENT", "SUB_PROCESSOR", "IDLEDISABLE"], timeout=10)
        if p.returncode != 0:
            return {"readable": False, "detail": "O powercfg não expos IDLEDISABLE neste PC."}
        vals = re.findall(r"0x([0-9a-fA-F]{8})", (p.stdout or ""))
        if len(vals) < 2:
            if allow_unhide and is_admin() and unhide_processor_idle_attribute():
                return processor_idle_state(allow_unhide=False)
            return {"readable": False, "hidden": True,
                    "detail": ("IDLEDISABLE vem oculto nas opcoes de energia do Windows. O AZOR revela "
                               "o atributo ao aplicar, e volta a oculta-lo ao reverter.")}
        return {"readable": True, "ac": int(vals[-2], 16), "dc": int(vals[-1], 16),
                "disabled": int(vals[-2], 16) == 1}
    except Exception as exc:
        return {"readable": False, "detail": str(exc)}


def set_processor_idle_disabled(disabled: bool = True) -> Tuple[bool, str]:
    if os.name != "nt":
        return False, "Disponível só no Windows."
    if not is_admin():
        return False, "Alterar os estados ociosos da CPU exige o AZOR aberto como administrador."
    before = processor_idle_state(allow_unhide=True)
    if not before.get("readable"):
        return False, before.get("detail") or "IDLEDISABLE não esta exposto neste PC."
    baseline_backfill("processor_idle", before)
    want = 1 if disabled else 0
    for cmd in (["powercfg", "/SETACVALUEINDEX", "SCHEME_CURRENT", "SUB_PROCESSOR", "IDLEDISABLE", str(want)],
                ["powercfg", "/SETACTIVE", "SCHEME_CURRENT"]):
        p = run_hidden(cmd, timeout=10)
        if p.returncode != 0:
            return False, (p.stderr or p.stdout or "powercfg recusou o comando.").strip()[:300]
    after = processor_idle_state()
    ok = after.get("ac") == want
    if ok and not disabled:
        # Reverter devolve tambem a opcao ao estado oculto em que o Windows a entrega.
        hide_processor_idle_attribute()
    journal("processor_idle", disabled=disabled, after=after.get("ac"), ok=ok)
    return ok, (("Estados ociosos da CPU desligados no plano ativo e confirmados por releitura."
                 if disabled else "Estados ociosos devolvidos ao Windows e confirmados.")
                if ok else f"Foi pedido {want}, mas o powercfg reporta {after.get('ac')}.")


# ==================== FECHANDO O CICLO: REINICIO, DERIVA E PROVA ====================
#
# Ate aqui o motor sabia aplicar e reconferir. Faltavam tres coisas que separam
# "aplica tweak" de "otimizacao verificavel":
#
#   1. Onze tweaks dizem "so vale depois de reiniciar" e ninguem NUNCA voltava
#      para conferir depois do boot. O cliente reiniciava e ficava sem saber.
#   2. A reconciliacao devolvia o ajuste ao lugar em silencio. Saber QUAL ajuste
#      o Windows desfaz toda semana vale mais que o conserto em si.
#   3. Todo tweak declara a metrica que deveria mover, e nenhum media. Metrica
#      declarada e promessa; metrica medida e prova.


def boot_id() -> str:
    """Identificador estável da sessão de boot atual.

    Calculado do instante do boot (agora menos o tempo ligado), arredondado para
    o minuto: um valor que muda a cada reinício e não muda dentro da mesma sessão.
    Não usa WMI de proposito - isto e consultado em toda abertura.
    """
    if os.name != "nt":
        return "posix"
    try:
        uptime_s = ctypes.windll.kernel32.GetTickCount64() / 1000.0
        return time.strftime("%Y%m%d-%H%M", time.localtime(time.time() - uptime_s))
    except Exception:
        return "desconhecido"


def mark_pending_reboot(task_id: str, name: str = "") -> None:
    """Anota que este tweak so passa a valer no próximo boot."""
    data = desired_state()
    pending = data.setdefault("pending_reboot", {})
    if not isinstance(pending, dict):
        pending = data["pending_reboot"] = {}
    pending[str(task_id)] = {"name": name or task_id, "applied_at": _ts(), "boot": boot_id()}
    data["updated_at"] = _ts()
    _safe_json_write(DESIRED_FILE, data)


def record_drift(task_id: str, name: str = "") -> None:
    """Registra que o Windows desfez este ajuste e o AZOR devolveu.

    Guarda so a contagem e as ultimas datas: um log que cresce sem limite viraria
    outro arquivo para ninguem ler.
    """
    data = desired_state()
    drift = data.setdefault("drift", {})
    if not isinstance(drift, dict):
        drift = data["drift"] = {}
    entry = drift.setdefault(str(task_id), {"name": name or task_id, "count": 0, "dates": []})
    entry["name"] = name or entry.get("name") or task_id
    entry["count"] = int(entry.get("count") or 0) + 1
    dates = entry.setdefault("dates", [])
    dates.append(_ts())
    entry["dates"] = dates[-8:]
    data["updated_at"] = _ts()
    _safe_json_write(DESIRED_FILE, data)




def confirm_after_reboot() -> Dict[str, Any]:
    """Confere, depois do boot, os tweaks que so valiam após reiniciar.

    Roda junto da reconciliacao de abertura. Um item so e avaliado quando o
    identificador de boot mudou desde a aplicação - antes disso, "não confirmado"
    seria injusto, porque o usuário ainda nem reiniciou.
    """
    data = desired_state()
    pending = data.get("pending_reboot") or {}
    if not isinstance(pending, dict) or not pending:
        return {"pending": 0, "confirmed": [], "failed": [], "waiting": []}
    now_boot = boot_id()
    try:
        from azor_modules.engine import _all_tasks, _context
        tasks = {t.id: t for t in _all_tasks()}
        ctx = _context(_core_self(), "auto")
    except Exception as exc:
        log(f"Post-reboot confirmation could not load the catalog: {exc}")
        return {"pending": len(pending), "confirmed": [], "failed": [], "waiting": [], "error": str(exc)}

    confirmed, failed, waiting = [], [], []
    keep: Dict[str, Any] = {}
    for task_id, entry in pending.items():
        label = entry.get("name") or task_id
        if entry.get("boot") == now_boot:
            waiting.append({"id": task_id, "name": label})
            keep[task_id] = entry
            continue
        task = tasks.get(task_id)
        if task is None or task.verify is None:
            confirmed.append({"id": task_id, "name": label, "detail": "sem releitura disponível"})
            continue
        try:
            ok, detail = _normalize(task.verify(_core_self(), ctx))
        except Exception as exc:
            ok, detail = False, str(exc)
        (confirmed if ok else failed).append({"id": task_id, "name": label, "detail": detail})
        if not ok:
            # Continua pendente: pode ser que o usuario reinicie de novo e resolva.
            keep[task_id] = entry
    data["pending_reboot"] = keep
    data["updated_at"] = _ts()
    _safe_json_write(DESIRED_FILE, data)
    if confirmed or failed:
        journal("post_reboot_confirm", confirmed=[x["id"] for x in confirmed],
                failed=[x["id"] for x in failed])
    return {"pending": len(pending), "confirmed": confirmed, "failed": failed, "waiting": waiting}


# ---------------------------------------------------------------------------
# Prova medida por tweak
# ---------------------------------------------------------------------------

# Tweaks cuja metrica declarada e medivel pelo proprio AZOR agora. Um tweak que
# move "FPS medio" nao entra: FPS so se mede com o jogo aberto, e o Monitor de
# Jogo ja faz isso. Prometer medir aqui o que so da para medir la seria teatro.






# ==================== OTIMIZACAO TOTAL: TODAS AS PAGINAS NUM CLIQUE ====================
#
# Ate aqui o BOOST rodava so o catalogo de tweaks. As outras paginas - Input Lab,
# Fortnite, preferencia de GPU por jogo - ficavam esperando o usuario ir la e
# clicar. Na pratica, quase ninguem ia: o cliente apertava BOOST, via "concluido"
# e achava que estava tudo feito.
#
# `full_optimize` faz o clique unico valer o nome. A ordem importa e nao e
# arbitraria: reparo e tweaks primeiro (eles mudam como o Windows agenda tudo),
# input depois (depende do timer que o lote acabou de ligar), e as coisas por
# jogo por ultimo, porque sao as unicas que dependem de detectar arquivo em disco.

# O que cada perfil considera "melhor" no Input Lab. Fica aqui e nao na interface
# porque o BOOST precisa funcionar sem ninguem ter aberto a tela de input.






# ==================== O CUSTO DO PROPRIO AZOR ====================
#
# O cliente disse que sentiu MAIS delay depois de instalar o app. Ele estava
# certo, e a medicao mostrou onde:
#
#   1. O agente Guardian acordava a cada 5 s DURANTE a partida e tirava um
#      retrato dos processos com `tasklist.exe`. Medido nesta maquina: 100,5 ms
#      por chamada, ~10 chamadas por minuto dentro do jogo. Criar processo e uma
#      operacao de kernel que enumera a maquina inteira - o formato exato de um
#      engasgo periodico de frametime. O mesmo dado sai do Toolhelp32 dentro do
#      proprio processo em 1,5 ms.
#
#   2. O monitor de perifericos registra RIDEV_INPUTSINK, que entrega ao AZOR
#      uma copia de TODO relatorio bruto do mouse e do teclado, inclusive sem
#      foco. Num mouse de 1000 Hz sao mil mensagens por segundo atravessando um
#      callback Python enquanto o cliente mira. O watchdog de 8 s nao salvava:
#      quem o alimentava era o proprio servidor, nao a pagina, entao minimizar
#      para a bandeja mantinha tudo vivo.
#
#   3. O amostrador mantinha um `nvidia-smi` de longa duracao e lia contadores
#      em intervalo curto, com a janela escondida atras do jogo.
#
# Nada disso serve para nada com o cliente dentro da partida: ninguem esta
# olhando os medidores nem o desenho do teclado acender. Agora o AZOR sai da
# frente sozinho, e volta sozinho quando o jogo perde o foco.
#
# O que continua ligado durante o jogo e so o que EXISTE para o jogo: o motor de
# prioridade e a sessao de timer. Esses sao o produto.






# ==================== FPS DE VERDADE: HZ DO MONITOR E PRIORIDADE DO JOGO ====================
#
# Duas coisas que valem mais que boa parte do catalogo somado, e que o app ate
# aqui so sabia DIAGNOSTICAR:
#
#   1. Monitor de 144 Hz rodando a 60 Hz. O relatorio de gargalo detectava e
#      mandava o usuario ir nas Configuracoes do Windows. Detectar e nao
#      consertar e a pior combinacao possivel: o cliente le que tem problema e
#      continua com ele.
#   2. O jogo disputando CPU em prioridade Normal com trinta processos de
#      segundo plano. O Game Mode do Windows ajuda, mas nao sobe a prioridade do
#      processo - e prioridade e o que decide quem roda quando falta nucleo.

CDS_UPDATEREGISTRY = 0x00000001
CDS_TEST = 0x00000002
DISP_CHANGE_SUCCESSFUL = 0
DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000


# O que o AZOR NAO escreve, e por que.
#
# As opcoes de baixa latencia do driver de video sao das que mais devolvem delay
# em jogo - e ficam atras de APIs que a NVIDIA e a AMD nao publicam para
# terceiros. Escrever direto no registro do driver e o tipo de coisa que quebra
# na proxima atualizacao e some sem avisar. Entao o AZOR faz o que faz no BIOS
# Copiloto: mostra o caminho exato e deixa o clique com o usuario.
DRIVER_GUIDES = {
    "nvidia": {
        "label": "NVIDIA",
        "panel": "Painel de Controle NVIDIA > Gerenciar configurações 3D > Configurações de programa > escolher o jogo",
        "items": [
            ("Baixa latência", "Reflex no jogo; Ultra como teste quando não houver Reflex",
             "Reflex tem precedência sobre o modo do driver. Ultra não é universal; o efeito depende da API e da carga. Compare latência e estabilidade no mesmo cenário."),
            ("Modo de gerenciamento de energia", "Preferir desempenho máximo",
             "Aplicar ao perfil do jogo, não a todos os programas. Pode manter clocks elevados em carga limitada pela CPU, com mais consumo e calor."),
            ("Sincronização vertical", "Desativada",
             "Com G-SYNC ligado, deixe ATIVADA e limite o FPS alguns quadros abaixo da "
             "taxa do monitor — é assim que o G-SYNC entrega baixa latência sem rasgo."),
            ("Filtragem de textura — Qualidade", "Desempenho como opção de teste",
             "Pode reduzir qualidade e aumentar cintilação de textura. Não comprova ganho; preserve Qualidade quando a diferença não for medida."),
            ("Cache de shaders", "Preservar cache e limite adequado ao espaço disponível",
             "Não limpar repetidamente. Tamanho ilimitado não elimina toda compilação nem garante ausência de travadas."),
        ],
    },
    "amd": {
        "label": "AMD",
        "panel": "AMD Software: Adrenalin Edition > Jogos > escolher o jogo > Gráficos",
        "items": [
            ("Radeon Anti-Lag", "Testar no perfil compatível; Anti-Lag 2 quando integrado ao jogo",
             "Depende da GPU, API e jogo. Anti-Lag e Radeon Chill não funcionam juntos; não ativar recursos ausentes nem usar integração externa ao anti-cheat."),
            ("Aguardar atualização vertical", "Sempre desativado",
             "Com FreeSync, prefira limitar o FPS abaixo da taxa do monitor."),
            ("Qualidade de filtragem de textura", "Desempenho",
             "Mesmo raciocínio da NVIDIA: detalhe imperceptível em movimento."),
            ("Cache de shader", "AMD otimizado",
             "Evita recompilação de shader durante a partida."),
            ("Otimização de formato de superfície", "Ativado",
             "Reduz banda de memória usada pela GPU."),
        ],
    },
    "intel": {
        "label": "Intel",
        "panel": "Intel Arc Control / Gráfico Intel > Configurações de jogo",
        "items": [
            ("Modo de baixa latência", "Ativado",
             "Disponível nas placas Arc e nos gráficos integrados recentes."),
            ("Sincronização vertical", "Desativada",
             "Com Adaptive Sync, limite o FPS abaixo da taxa do monitor."),
        ],
    },
}


def driver_guide() -> Dict[str, Any]:
    """O guia do fabricante da GPU que este PC realmente tem."""
    profile = hardware_profile()
    gpus = [str(g) for g in (profile.get("gpus") or [])]
    joined = " ".join(gpus).lower()
    vendor = ("nvidia" if "nvidia" in joined or "geforce" in joined or "rtx" in joined or "gtx" in joined
              else "amd" if "radeon" in joined or "amd" in joined
              else "intel" if "intel" in joined or "arc" in joined
              else "")
    guide = DRIVER_GUIDES.get(vendor)
    return {
        "ok": bool(guide), "vendor": vendor, "gpus": gpus,
        "guide": guide,
        "applied": False,
        "sources": [
            "https://www.nvidia.com/en-us/geforce/guides/system-latency-optimization-guide/",
            "https://www.amd.com/en/products/software/adrenalin/radeon-software-anti-lag.html"],
        "note": ("Guia por jogo, não confirmação de configuração aplicada. Esta versão ainda não integra "
                 "gravação e restauração dos perfis do driver. Reflex e Anti-Lag 2 precisam do suporte do jogo. "
                 "Não são gravadas chaves de driver não documentadas."),
    }


def available_refresh_rates() -> List[int]:
    """Taxas oferecidas pelo monitor na resolução atual, da maior para a menor."""
    if os.name != "nt":
        return []
    try:
        user32 = ctypes.windll.user32
        current = _DEVMODEW()
        current.dmSize = ctypes.sizeof(_DEVMODEW)
        if not user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(current)):
            return []
        width, height = int(current.dmPelsWidth), int(current.dmPelsHeight)
        rates = set()
        index = 0
        while index < 4096:
            mode = _DEVMODEW()
            mode.dmSize = ctypes.sizeof(_DEVMODEW)
            if not user32.EnumDisplaySettingsW(None, index, ctypes.byref(mode)):
                break
            index += 1
            if int(mode.dmPelsWidth) == width and int(mode.dmPelsHeight) == height:
                hz = int(mode.dmDisplayFrequency)
                if hz > 1:
                    rates.add(hz)
        return sorted(rates, reverse=True)
    except Exception as exc:
        log(f"available refresh rates failed: {exc}")
        return []


def set_display_refresh_verified(hz: int) -> Tuple[bool, str]:
    """Muda a taxa de atualização e confirma relendo o modo ativo.

    Testa com CDS_TEST antes de aplicar: pedir um modo que o monitor recusa
    poderia deixar a tela preta até o Windows reverter sozinho, e esperar
    quinze segundos por isso e uma experiencia ruim de se entregar a um cliente.
    """
    if os.name != "nt":
        return False, "Disponível só no Windows."
    target = int(hz)
    before = display_refresh_state()
    if not before.get("ok"):
        return False, "O Windows não respondeu o modo de vídeo atual."
    if target not in available_refresh_rates():
        return False, (f"{target} Hz não está na lista que o monitor oferece em "
                       f"{before.get('width')}x{before.get('height')}.")
    baseline_backfill("display_refresh", {"hz": before.get("current_hz"),
                                          "width": before.get("width"),
                                          "height": before.get("height")})
    try:
        user32 = ctypes.windll.user32
        mode = _DEVMODEW()
        mode.dmSize = ctypes.sizeof(_DEVMODEW)
        if not user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(mode)):
            return False, "Não foi possível ler o modo de vídeo atual."
        mode.dmDisplayFrequency = target
        mode.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY
        test = user32.ChangeDisplaySettingsExW(None, ctypes.byref(mode), None, CDS_TEST, None)
        if test != DISP_CHANGE_SUCCESSFUL:
            return False, (f"O Windows recusou {target} Hz neste modo (código {test}). "
                           "Nada foi alterado.")
        applied = user32.ChangeDisplaySettingsExW(None, ctypes.byref(mode), None,
                                                  CDS_UPDATEREGISTRY, None)
        if applied != DISP_CHANGE_SUCCESSFUL:
            return False, f"A troca para {target} Hz falhou (código {applied})."
    except Exception as exc:
        return False, f"Falha ao trocar a taxa de atualização: {exc}"
    after = display_refresh_state()
    ok = int(after.get("current_hz") or 0) == target
    journal("display_refresh", requested=target, before=before.get("current_hz"),
            after=after.get("current_hz"), ok=ok)
    return ok, (f"Monitor de {before.get('current_hz')} Hz para {after.get('current_hz')} Hz em "
                f"{after.get('width')}x{after.get('height')}, confirmado por releitura. "
                f"O jogo passa a poder mostrar {after.get('current_hz')} quadros por segundo em vez de "
                f"{before.get('current_hz')}." if ok else
                f"A troca foi solicitada, mas o Windows continua reportando {after.get('current_hz')} Hz.")


# ---------------------------------------------------------------------------
# Prioridade do processo do jogo
# ---------------------------------------------------------------------------

HIGH_PRIORITY_CLASS = 0x00000080
ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
NORMAL_PRIORITY_CLASS = 0x00000020
PROCESS_SET_INFORMATION = 0x0200
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000




def _process_kernel():
    from ctypes import wintypes
    k32=ctypes.WinDLL("kernel32",use_last_error=True)
    k32.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    k32.OpenProcess.restype=wintypes.HANDLE
    k32.CloseHandle.argtypes=[wintypes.HANDLE]
    k32.GetPriorityClass.argtypes=[wintypes.HANDLE]
    k32.GetPriorityClass.restype=wintypes.DWORD
    k32.SetPriorityClass.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    k32.SetPriorityClass.restype=wintypes.BOOL
    k32.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    k32.GetProcessTimes.restype=wintypes.BOOL
    k32.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
    k32.QueryFullProcessImageNameW.restype=wintypes.BOOL
    return k32


def _process_creation(k32,handle):
    from ctypes import wintypes
    times=[wintypes.FILETIME() for _ in range(4)]
    if not k32.GetProcessTimes(handle,*(ctypes.byref(t) for t in times)):return None
    return (times[0].dwHighDateTime<<32)|times[0].dwLowDateTime


def process_snapshot(pid: int) -> Optional[Dict[str,Any]]:
    if os.name!="nt":return None
    from ctypes import wintypes
    k32=_process_kernel()
    handle=k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,False,int(pid))
    if not handle:return None
    try:
        created=_process_creation(k32,handle)
        size=wintypes.DWORD(32768);buf=ctypes.create_unicode_buffer(size.value)
        if created is None or not k32.QueryFullProcessImageNameW(handle,0,buf,ctypes.byref(size)):return None
        priority=int(k32.GetPriorityClass(handle))
        if not priority:return None
        return {"pid":int(pid),"created":created,"path":buf.value,"name":Path(buf.value).name,"priority":priority}
    finally:k32.CloseHandle(handle)




def set_process_priority(pid: int, priority: int, expected_creation: Optional[int]=None) -> bool:
    if os.name!="nt":return False
    # Never expose REALTIME, including through advanced profiles.
    if priority not in (0x40,0x4000,NORMAL_PRIORITY_CLASS,ABOVE_NORMAL_PRIORITY_CLASS,HIGH_PRIORITY_CLASS):return False
    k32=_process_kernel()
    handle=k32.OpenProcess(PROCESS_SET_INFORMATION|PROCESS_QUERY_LIMITED_INFORMATION,False,int(pid))
    if not handle:return False
    try:
        if expected_creation is not None and _process_creation(k32,handle)!=expected_creation:return False
        return bool(k32.SetPriorityClass(handle,priority)) and k32.GetPriorityClass(handle)==priority
    finally:k32.CloseHandle(handle)


from azor_game_mode import GameProcessManager

class GamePriorityEngine(GameProcessManager):
    """Compatibility entry point for the reversible AZOR session manager."""
    def __init__(self):super().__init__(sys.modules[__name__])


GAME_PRIORITY = GamePriorityEngine()


# ==================== PLANO DE ACAO: A ORDEM DO MAIOR RETORNO ====================
#
# O app chegou a 68 tweaks, um indice, um relatorio de gargalo e uma prova
# medida - e nenhuma resposta para a unica pergunta que o cliente faz: "o que eu
# faco primeiro?". Uma lista de 68 itens nao e um plano; e um catalogo.
#
# Este modulo nao mede nada novo. Ele ORDENA o que ja foi medido, e a ordem sai
# de tres fatos ja conhecidos:
#   1. Limite estrutural vence tweak. Monitor a 60 Hz num painel de 144 devolve
#      mais que os 68 ajustes somados, e nenhum deles compensa XMP desligado.
#   2. Entre tweaks, o que a metrica declarada move manda: quem mexe em FPS e
#      1% low vem antes de quem mexe em "processos em repouso".
#   3. O que exige clique explicito (risco alto, experimental) vai para o fim,
#      porque nao e recomendacao - e escolha informada.
#
# Nenhum passo promete numero. Cada um diz de onde veio a posicao dele.

# Peso derivado da METRICA que o proprio tweak declara. Nao e opiniao sobre o
# tweak: e sobre o que ele diz que move. Metrica vazia = preferencia, e vai por
# ultimo porque o proprio catalogo diz que ali nao ha desempenho.






# ==================== PERIFERICOS: O QUE E REALMENTE LEGIVEL ====================
#
# Esta secao existe para uma regra: a tela de perifericos nao mostra numero que o
# AZOR nao consegue ler do dispositivo.
#
# O que da para saber, e de onde:
#   polling rate  MEDIDO. O azor_input_monitor cronometra o intervalo entre
#                 relatorios reais de Raw Input e devolve a mediana, com nivel de
#                 confianca. So vale enquanto o usuario move o mouse.
#   DPI           NAO DA. O Windows nao expoe DPI de mouse por API nenhuma - o
#                 valor vive no firmware do mouse e so o software do fabricante
#                 le. Qualquer numero de DPI numa tela dessas ou veio do usuario
#                 ou foi inventado.
#   VID/PID       DA, pelo Enum do dispositivo.
#   conexao       INFERIDA do caminho do dispositivo (USB, Bluetooth, dongle).
#
# A versao anterior tinha `_supported_hz()`, que adivinhava a taxa maxima pelo
# NOME do dispositivo ("8K" no nome => suporta 8000 Hz). Isso e chute apresentado
# como capacidade, e saiu.

DPI_UNAVAILABLE_REASON = (
    "O Windows não expõe o DPI do mouse por nenhuma API: esse valor vive no "
    "firmware do dispositivo e so o software do fabricante consegue ler. O AZOR "
    "prefere dizer que não sabe a mostrar um número que não veio do seu mouse."
)

POLLING_UNAVAILABLE_REASON = (
    "A taxa de envio e medida cronometrando os relatorios reais do dispositivo. "
    "Mova o mouse por alguns segundos com esta tela aberta para o AZOR medir."
)


def input_capabilities() -> Dict[str, Any]:
    """O que o AZOR consegue LER de cada periférico neste PC, sem chute."""
    devices = detect_devices()
    import azor_gamepad
    xinput = azor_gamepad.available()
    out: Dict[str, Any] = {}
    for kind in ("controller", "mouse", "keyboard"):
        rows = devices.get(kind, [])
        dev = rows[0] if rows else {}
        ids = _extract_vid_pid(dev.get("id"))
        # Controle em modo XInput: o AZOR conta os pacotes que ele manda e le a
        # bateria pelo proprio XInput. Controle so-HID continua sem essas leituras.
        pad_readable = kind == "controller" and xinput and bool(dev.get("xinput"))
        out[kind] = {
            "connected": bool(rows),
            "count": len(rows),
            "name": dev.get("name") or "",
            "display_name": dev.get("display_name") or dev.get("name") or "",
            "vendor": dev.get("vendor"),
            "vendor_kind": dev.get("vendor_kind"),
            "note": dev.get("note") or "",
            "xinput": bool(dev.get("xinput")),
            "emulated": bool(dev.get("emulated")),
            "layout": dev.get("layout") or "asymmetric",
            "devices": [{"display_name": r.get("display_name") or r.get("name"), "vid": r.get("vid"),
                         "pid": r.get("pid"), "vendor": r.get("vendor"), "xinput": bool(r.get("xinput"))}
                        for r in rows],
            "status": dev.get("status") or "",
            "vid": ids.get("vid"),
            "pid": ids.get("pid"),
            "connection": _infer_connection(dev),
            # Declarado explicitamente para a tela nao precisar adivinhar o que
            # pode mostrar. Nenhum destes vira numero sem leitura real.
            "readable": {
                "dpi": False,
                "polling": kind in ("mouse", "keyboard") or pad_readable,
                "battery": pad_readable,
                "firmware": False,
            },
            "dpi_reason": DPI_UNAVAILABLE_REASON,
            "polling_reason": (POLLING_UNAVAILABLE_REASON if kind != "controller" else
                               "A taxa do controle é medida pelo XInput, e este controle não está em modo XInput."),
        }
    return out


# ---------------------------------------------------------------------------
# Remapeamento de controle
# ---------------------------------------------------------------------------
#
# ATENCAO - LEIA ANTES DE MEXER AQUI.
#
# O AZOR NAO remapeia o controle de verdade, e a tela diz isso com todas as
# letras. Guardar o mapa aqui e util (o perfil sobrevive a reinicio e vai junto
# com o resto das configuracoes), mas o Windows nao oferece nenhum caminho para
# um aplicativo comum reescrever os botoes de um gamepad:
#
#   - XInput e API de LEITURA. Nao existe "SetState" de botoes.
#   - A Gamepad API do navegador tambem so le.
#   - Trocar botao de verdade exige um driver no meio do caminho: um gamepad
#     VIRTUAL (ViGEmBus) recebendo o estado traduzido, mais o fisico ESCONDIDO
#     do jogo (HidHide). Sem esconder o original, o jogo enxerga os dois e conta
#     entrada dobrada.
#
# PONTO DE INTEGRACAO, se um dia isso for implementado:
#   1. Detectar ViGEmBus instalado (servico "ViGEmBus" / driver vigembus.sys).
#   2. Criar um controle virtual X360/DS4 e alimentar com o estado traduzido.
#   3. Esconder o fisico com HidHide, apenas para os executaveis de jogo.
#   4. Trocar `applied` para True SOMENTE depois de confirmar 1, 2 e 3.
# Ate la, `applied` e False e a tela mostra "salvo como perfil, nao aplicado".





