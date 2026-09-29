"""Consertos de um clique (vindos do WinUtil) e o DNS.

Cada conserto diz antes o que faz e quanto demora, e depois o que achou. Nada
aqui é "otimização": é o que o técnico roda quando o Windows está com defeito.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from typing import Any, Callable, Dict, List, Optional


def _run_text(core, args: List[str], timeout: int) -> Dict[str, Any]:
    """Roda e devolve o texto. sfc e chkdsk escrevem UTF-16; o resto, a página de código do console."""
    kwargs: Dict[str, Any] = {"capture_output": True, "timeout": timeout}
    if os.name == "nt":
        kwargs["creationflags"] = core.CREATE_NO_WINDOW
    try:
        p = subprocess.run(args, **kwargs)
    except subprocess.TimeoutExpired:
        return {"code": None, "text": "Tempo esgotado."}
    except Exception as exc:
        return {"code": None, "text": str(exc)}
    raw = (p.stdout or b"") + b"\n" + (p.stderr or b"")
    if raw.count(b"\x00") > len(raw) // 4:
        text = raw.decode("utf-16-le", errors="replace")
    else:
        text = ""
        for enc in ("utf-8", "cp850", "cp1252"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    text = text.replace("\x00", "").replace("\r", "")
    return {"code": p.returncode, "text": text}


def _last_lines(text: str, n: int = 3) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not re.fullmatch(r"[\[\]=.\s\d%-]+", ln.strip())]
    return " ".join(lines[-n:])[:400]


def system_repair(core, progress: Optional[Callable] = None) -> Dict[str, Any]:
    """CHKDSK (só leitura), SFC e DISM: arquivos corrompidos do Windows."""
    if not core.is_admin():
        return {"ok": False, "detail": "Precisa do AZOR como administrador."}
    steps = [
        ("Verificar o disco (CHKDSK)", ["chkdsk", os.environ.get("SystemDrive", "C:"), "/scan"], 3600),
        ("Reparar a imagem do Windows (DISM)", ["dism", "/Online", "/Cleanup-Image", "/RestoreHealth"], 5400),
        ("Reparar arquivos do sistema (SFC)", ["sfc", "/scannow"], 3600),
    ]
    rows = []
    for label, args, timeout in steps:
        if progress:
            progress(label, "applying", "Pode levar de 5 a 30 minutos. Não desligue o PC.")
        res = _run_text(core, args, timeout)
        ok = res["code"] == 0
        detail = _last_lines(res["text"]) or ("Concluído." if ok else "Terminou com aviso.")
        rows.append({"name": label, "ok": ok, "detail": detail})
        if progress:
            progress(label, "completed" if ok else "failed", detail)
    ok = all(r["ok"] for r in rows)
    core.journal("system_repair", results=rows)
    return {"ok": ok, "results": rows,
            "detail": "Windows verificado e reparado. Reinicie o PC." if ok else
                      "O reparo terminou com avisos; veja os detalhes e reinicie o PC."}


def network_reset(core, progress: Optional[Callable] = None) -> Dict[str, Any]:
    if not core.is_admin():
        return {"ok": False, "detail": "Precisa do AZOR como administrador."}
    cmds = [
        ("Limpar cache de DNS", ["ipconfig", "/flushdns"]),
        ("Renovar endereço", ["ipconfig", "/renew"]),
        ("Redefinir Winsock", ["netsh", "winsock", "reset"]),
        ("Redefinir TCP/IP", ["netsh", "int", "ip", "reset"]),
        ("Auto-ajuste TCP normal", ["netsh", "int", "tcp", "set", "global", "autotuninglevel=normal"]),
    ]
    rows = []
    for label, args in cmds:
        res = _run_text(core, args, 120)
        low = res["text"].lower()
        # "netsh int ip reset" costuma sair com código 1 só porque uma chave protegida
        # recusou a escrita, mesmo tendo redefinido o resto e pedido reinício.
        ok = res["code"] == 0 or (res["code"] == 1 and ("reinici" in low or "restart" in low))
        rows.append({"name": label, "ok": ok, "detail": _last_lines(res["text"], 1)})
        if progress:
            progress(label, "completed" if ok else "failed", rows[-1]["detail"])
    ok = all(r["ok"] for r in rows if r["name"] != "Renovar endereço")
    return {"ok": ok, "results": rows, "restart": True,
            "detail": "Rede redefinida. Reinicie o PC para terminar." if ok else "Parte da redefinição falhou."}


def update_reset(core, progress: Optional[Callable] = None) -> Dict[str, Any]:
    """Conserto padrão do Windows Update: para os serviços, renomeia os caches e religa."""
    if not core.is_admin():
        return {"ok": False, "detail": "Precisa do AZOR como administrador."}
    stamp = time.strftime("%Y%m%d%H%M%S")
    script = (
        "$ErrorActionPreference='SilentlyContinue'; $svc='wuauserv','bits','cryptsvc','appidsvc','msiserver'; "
        "foreach($s in $svc){ Stop-Service -Name $s -Force }; "
        "Remove-Item \"$env:ALLUSERSPROFILE\\Microsoft\\Network\\Downloader\\qmgr*.dat\" -Force; "
        f"Rename-Item \"$env:SystemRoot\\SoftwareDistribution\" \"SoftwareDistribution.old-{stamp}\"; "
        f"Rename-Item \"$env:SystemRoot\\System32\\catroot2\" \"catroot2.old-{stamp}\"; "
        "Get-BitsTransfer -AllUsers | Remove-BitsTransfer; "
        "Remove-ItemProperty -Path 'HKLM:\\SOFTWARE\\Policies\\Microsoft\\Windows\\WindowsUpdate' -Name WUServer,WUStatusServer -Force; "
        "foreach($s in $svc){ Start-Service -Name $s }; "
        "Start-Process -FilePath \"$env:SystemRoot\\System32\\UsoClient.exe\" -ArgumentList 'StartScan' -WindowStyle Hidden; "
        "[pscustomobject]@{Renamed=(Test-Path \"$env:SystemRoot\\SoftwareDistribution.old-" + stamp + "\");"
        "Running=((Get-Service wuauserv).Status -eq 'Running' -or (Get-Service wuauserv).StartType -ne 'Disabled')}"
    )
    if progress:
        progress("Windows Update", "applying", "Parando serviços e recriando os caches do Windows Update…")
    try:
        data = core.powershell_json(script, timeout=600) or {}
    except Exception as exc:
        return {"ok": False, "detail": f"O conserto não terminou: {exc}"}
    ok = bool(data.get("Running"))
    detail = ("Windows Update redefinido. Abra Configurações > Windows Update e procure atualizações."
              if ok else "Os serviços do Windows Update não voltaram; reinicie o PC.")
    if progress:
        progress("Windows Update", "completed" if ok else "failed", detail)
    return {"ok": ok, "detail": detail, "restart": True}


LEGACY_FEATURES = (("NetFx3", ".NET Framework 3.5"), ("LegacyComponents", "Componentes legados"),
                   ("DirectPlay", "DirectPlay"))


def legacy_games(core, progress: Optional[Callable] = None) -> Dict[str, Any]:
    """Liga .NET 3.5 e DirectPlay, que jogos de 2002 a 2012 pedem."""
    if not core.is_admin():
        return {"ok": False, "detail": "Precisa do AZOR como administrador."}
    rows = []
    for feature, label in LEGACY_FEATURES:
        if progress:
            progress(label, "applying", "Baixando pelo Windows Update se preciso…")
        try:
            state = str(core.powershell(
                f"Enable-WindowsOptionalFeature -Online -FeatureName {feature} -All -NoRestart -ErrorAction Stop | Out-Null; "
                f"(Get-WindowsOptionalFeature -Online -FeatureName {feature}).State", timeout=1800)).strip()
            ok = state.lower().startswith("enabled") or state.lower() == "enablepending"
            detail = "Ativado." if ok else f"Estado: {state}"
        except Exception as exc:
            ok, detail = False, str(exc)[:200]
        rows.append({"name": label, "ok": ok, "detail": detail})
        if progress:
            progress(label, "completed" if ok else "failed", detail)
    ok = all(r["ok"] for r in rows)
    return {"ok": ok, "results": rows,
            "detail": "Recursos para jogos antigos ativados." if ok else "Parte dos recursos não foi ativada."}


# ---------------------------------------------------------------------------
# DNS
#
# Honesto: DNS não diminui o ping da partida (ele só resolve o nome do servidor
# uma vez). Ajuda quando o DNS do provedor é lento ou cai: sites e logins dos
# jogos abrem mais rápido e param de dar "sem conexão" com a internet ok.
# ---------------------------------------------------------------------------
DNS_PROVIDERS = {
    "auto": {"label": "Automático (do provedor)", "v4": [], "v6": []},
    "cloudflare": {"label": "Cloudflare", "v4": ["1.1.1.1", "1.0.0.1"], "v6": ["2606:4700:4700::1111", "2606:4700:4700::1001"]},
    "google": {"label": "Google", "v4": ["8.8.8.8", "8.8.4.4"], "v6": ["2001:4860:4860::8888", "2001:4860:4860::8844"]},
    "quad9": {"label": "Quad9 (bloqueia sites maliciosos)", "v4": ["9.9.9.9", "149.112.112.112"], "v6": ["2620:fe::fe", "2620:fe::9"]},
    "adguard": {"label": "AdGuard (bloqueia anúncios)", "v4": ["94.140.14.14", "94.140.15.15"], "v6": ["2a10:50c0::ad1:ff", "2a10:50c0::ad2:ff"]},
}


def dns_state(core) -> Dict[str, Any]:
    try:
        data = core.powershell_json(
            "Get-NetAdapter -Physical -ErrorAction SilentlyContinue | Where-Object Status -eq 'Up' | ForEach-Object { "
            "$d=Get-DnsClientServerAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue; "
            "[pscustomobject]@{Name=$_.Name;Index=$_.ifIndex;Servers=@($d.ServerAddresses)} }", timeout=30)
    except Exception as exc:
        return {"ok": False, "adapters": [], "current": None, "detail": str(exc)}
    if isinstance(data, dict):
        data = [data]
    adapters = [{"name": d.get("Name"), "index": d.get("Index"), "servers": d.get("Servers") or []}
                for d in (data or []) if isinstance(d, dict)]
    current = "auto"
    servers = set(adapters[0]["servers"]) if adapters else set()
    for key, prov in DNS_PROVIDERS.items():
        if prov["v4"] and servers and servers <= set(prov["v4"]):
            current = key
    return {"ok": True, "adapters": adapters, "current": current,
            "providers": [{"id": k, "label": v["label"]} for k, v in DNS_PROVIDERS.items()]}


def dns_set(core, provider: str) -> Dict[str, Any]:
    if provider not in DNS_PROVIDERS:
        return {"ok": False, "detail": "Provedor de DNS inválido."}
    if not core.is_admin():
        return {"ok": False, "detail": "Precisa do AZOR como administrador."}
    prov = DNS_PROVIDERS[provider]
    if provider == "auto":
        action = "Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ResetServerAddresses"
    else:
        servers = ",".join(json.dumps(s) for s in prov["v4"] + prov["v6"])
        action = f"Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ServerAddresses @({servers})"
    try:
        core.powershell("Get-NetAdapter -Physical | Where-Object Status -eq 'Up' | ForEach-Object { " + action +
                        " }; Clear-DnsClientCache; 'OK'", timeout=60)
    except Exception as exc:
        return {"ok": False, "detail": f"O Windows recusou trocar o DNS: {exc}"}
    state = dns_state(core)
    ok = state.get("current") == provider
    core.journal("dns_set", provider=provider, ok=ok)
    return {"ok": ok, "detail": f"DNS: {prov['label']}." if ok else "A troca não foi confirmada.", "state": state}
