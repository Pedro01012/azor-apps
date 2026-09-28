"""Programas que abrem junto com o Windows, classificados para quem joga.

Cada item cai numa de quatro caixas:
  essencial  - driver de som/vídeo/touchpad, antivírus, anti-cheat, software
               do mouse e teclado. Nunca é desligado pelo AZOR.
  inutil     - atualizadores, Edge, Teams, Copilot, OneDrive, Adobe... O
               BOOST desliga (continuam instalados e abrem quando você quiser).
  lancador   - Steam, Epic, Discord, Battle.net... Só o modo EXTREMO desliga:
               eles abrem na hora que você for jogar, sem ficar na memória antes.
  outro      - não reconhecido. Fica como está; o usuário decide.

Desligar usa o mesmo registro do Gerenciador de Tarefas (StartupApproved),
então o próprio Windows mostra o item como Desabilitado e ele volta com um clique.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ESSENTIAL = (
    "securityhealth", "windowsdefender", "msmpeng", "rtkaud", "realtek", "rthdvcpl", "waves", "maxxaudio",
    "nahimic", "dolby", "synaptics", "syntp", "elan", "etdctrl", "igfx", "intel", "nvidia", "nvbackend",
    "nvcontainer", "amd", "radeon", "ati ", "logi", "lghub", "razer", "synapse", "steelseries", "corsair",
    "icue", "hyperx", "ngenuity", "wooting", "glorious", "armoury", "asus", "msi center", "dragon center",
    "bluetooth", "btmshell", "vanguard", "vgtray", "easyanticheat", "battleye", "faceit", "avast", "avg",
    "kaspersky", "norton", "bitdefender", "eset", "malwarebytes", "mcafee", "sophos", "ctfmon",
)
USELESS = (
    "microsoftedgeautolaunch", "msedge", "edgeupdate", "teams", "msteams", "skype", "onedrive", "cortana",
    "copilot", "adobe", "acrobat", "ccxprocess", "adobegc", "googleupdate", "google update", "googledrivefs",
    "chrome", "opera browser assistant", "browser_assistant", "brave", "ituneshelper", "itunes", "jusched",
    "java update", "ccleaner", "utorrent", "bittorrent", "zoom", "slack", "whatsapp", "telegram", "spotify",
    "dropbox", "grammarly", "phoneexperiencehost", "yourphone", "cyberlink", "wondershare", "update",
    "updater", "helper",
)
LAUNCHERS = (
    "steam", "epicgameslauncher", "epic games", "battle.net", "battlenet", "eadesktop", "ea app", "origin",
    "ubisoft", "upc", "uplay", "goggalaxy", "galaxyclient", "riotclient", "riot client", "rockstar",
    "playnite", "overwolf", "curseforge", "medal", "discord", "teamspeak", "vesktop", "parsec", "xbox",
)

APPROVED_FOLDER = {
    "HKCU_FOLDER": ("HKCU", r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder"),
    "HKLM_FOLDER": ("HKLM", r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder"),
}
DISABLED_BY_AZOR = "startup_disabled_by_azor.json"

WHY = {
    "essencial": "Driver, antivírus, anti-cheat ou software do seu periférico. Deixe ligado.",
    "inutil": "Não precisa abrir com o Windows. Continua instalado e abre quando você quiser.",
    "lancador": "Lançador ou chat. Desligado, abre na hora que você for jogar, sem ocupar memória antes.",
    "outro": "Programa não reconhecido. Desligue só se você souber o que é.",
}


def classify(name: str, command: str = "") -> str:
    text = f" {name} {command} ".lower()
    if any(k in text for k in ESSENTIAL):
        return "essencial"
    if any(k in text for k in LAUNCHERS):
        return "lancador"
    if any(k in text for k in USELESS):
        return "inutil"
    return "outro"


def _folder_flag(core, scope: str, name: str) -> Optional[bool]:
    winreg = core.winreg
    if winreg is None:
        return None
    root, path = APPROVED_FOLDER[scope]
    try:
        with winreg.OpenKey(core._root_const(root), path, 0, winreg.KEY_READ) as k:
            raw, _ = winreg.QueryValueEx(k, name)
            return not raw or int(raw[0]) not in (3,)
    except OSError:
        return True


def _folder_items(core) -> List[Dict[str, Any]]:
    out = []
    folders = []
    appdata, programdata = os.environ.get("APPDATA"), os.environ.get("ProgramData")
    if appdata:
        folders.append(("HKCU_FOLDER", Path(appdata) / r"Microsoft\Windows\Start Menu\Programs\Startup"))
    if programdata:
        folders.append(("HKLM_FOLDER", Path(programdata) / r"Microsoft\Windows\Start Menu\Programs\StartUp"))
    for scope, folder in folders:
        try:
            entries = sorted(folder.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.name.lower() == "desktop.ini" or not entry.is_file():
                continue
            out.append({"scope": scope, "scope_label": "Pasta Inicializar", "name": entry.name,
                        "command": str(entry), "exe": entry.stem, "enabled": _folder_flag(core, scope, entry.name),
                        "running": None, "memory_mb": None, "admin_required": scope == "HKLM_FOLDER"})
    return out


def items(core) -> Dict[str, Any]:
    base = core.startup_items() if os.name == "nt" else {"ok": False, "items": []}
    rows = list(base.get("items") or []) + (_folder_items(core) if os.name == "nt" else [])
    for row in rows:
        kind = classify(str(row.get("name") or ""), str(row.get("command") or ""))
        row["kind"] = kind
        row["why"] = WHY[kind]
    order = {"inutil": 0, "lancador": 1, "outro": 2, "essencial": 3}
    rows.sort(key=lambda r: (order[r["kind"]], -(r.get("memory_mb") or 0), str(r.get("name")).lower()))
    return {"ok": bool(base.get("ok", os.name == "nt")), "items": rows,
            "enabled_count": sum(1 for r in rows if r.get("enabled")),
            "useless_on": sum(1 for r in rows if r.get("enabled") and r["kind"] == "inutil"),
            "launchers_on": sum(1 for r in rows if r.get("enabled") and r["kind"] == "lancador")}


def set_enabled(core, scope: str, name: str, enabled: bool) -> Tuple[bool, str]:
    if scope in APPROVED_FOLDER:
        winreg = core.winreg
        if winreg is None:
            return False, "Disponível somente no Windows."
        if scope == "HKLM_FOLDER" and not core.is_admin():
            return False, "Este item vale para todos os usuários e exige administrador."
        root, path = APPROVED_FOLDER[scope]
        blob = bytes([2 if enabled else 3] + [0] * 11)
        try:
            with winreg.CreateKeyEx(core._root_const(root), path, 0, winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, name, 0, winreg.REG_BINARY, blob)
        except OSError as exc:
            return False, f"Não foi possível alterar '{name}': {exc}"
        got = _folder_flag(core, scope, name)
        ok = (got is True) if enabled else (got is False)
        return ok, (f"'{name}' {'reativado' if enabled else 'desativado'} na inicialização."
                    if ok else "A releitura não confirmou.")
    return core.set_startup_item_enabled(scope, name, enabled)


def _ledger_path(core) -> Path:
    return Path(core.DATA_DIR) / DISABLED_BY_AZOR


def _ledger(core) -> List[Dict[str, str]]:
    try:
        data = json.loads(_ledger_path(core).read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def boost_disable(core, extreme: bool, progress: Optional[Callable] = None) -> Dict[str, Any]:
    """Desliga o inútil (e os lançadores no Extremo). Anota o que o AZOR desligou."""
    kinds = {"inutil", "lancador"} if extreme else {"inutil"}
    state = items(core)
    targets = [r for r in state["items"] if r.get("enabled") and r["kind"] in kinds
               and not (r.get("admin_required") and not core.is_admin())]
    ledger = _ledger(core)
    done, failed = [], []
    for row in targets:
        ok, detail = set_enabled(core, row["scope"], row["name"], False)
        (done if ok else failed).append(row["name"])
        if ok and not any(x["scope"] == row["scope"] and x["name"] == row["name"] for x in ledger):
            ledger.append({"scope": row["scope"], "name": row["name"]})
    if done:
        _ledger_path(core).write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    if progress:
        progress("Inicialização", "completed" if not failed else "failed",
                 f"{len(done)} programa(s) tirado(s) do boot." if done else "Nada inútil abrindo com o Windows.")
    return {"ok": not failed, "disabled": done, "failed": failed}


def restore_disabled(core) -> Dict[str, Any]:
    """Religa tudo que o BOOST tirou do boot (usado pelo Desfazer tudo)."""
    ledger = _ledger(core)
    back, failed = [], []
    for row in ledger:
        ok, _ = set_enabled(core, row["scope"], row["name"], True)
        (back if ok else failed).append(row["name"])
    remaining = [r for r in ledger if r["name"] in failed]
    _ledger_path(core).write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": not failed, "restored": back, "failed": failed}
