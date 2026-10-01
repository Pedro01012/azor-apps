"""Consertos de um clique (vindos do WinUtil) e o DNS.

Cada conserto diz antes o que faz e quanto demora, e depois o que achou. Nada
aqui é "otimização": é o que o técnico roda quando o Windows está com defeito.
"""
from __future__ import annotations

import json
import os
import random
import re
import socket
import statistics
import struct
import subprocess
import threading
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


# ---------------------------------------------------------------------------
# Medir qual DNS responde mais rápido neste PC e nesta internet.
#
# É o mesmo teste que um técnico faz à mão com nslookup, só que feito por UDP
# direto: cada servidor recebe os mesmos nomes (lojas e launchers de jogo) e
# vale a mediana. Não precisa de administrador e não muda nada no Windows.
# ---------------------------------------------------------------------------
BENCH_NAMES = ("steamcommunity.com", "epicgames.com", "riotgames.com", "discord.com",
               "battle.net", "google.com")
BENCH_EXTRA = {"opendns": {"label": "OpenDNS", "v4": ["208.67.222.222", "208.67.220.220"]}}


def _dns_query(server: str, name: str, timeout: float = 1.2, port: int = 53) -> Optional[float]:
    """Pergunta o endereço de `name` a `server` e devolve o tempo em ms (None se não respondeu)."""
    qid = random.randrange(65536)
    packet = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    packet += b"".join(bytes([len(part)]) + part.encode("ascii") for part in name.split(".")) + b"\x00"
    packet += struct.pack(">HH", 1, 1)
    sock = socket.socket(socket.AF_INET6 if ":" in server else socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        start = time.perf_counter()
        sock.sendto(packet, (server, port))
        data, _ = sock.recvfrom(2048)
        elapsed = (time.perf_counter() - start) * 1000
    except (OSError, socket.timeout):
        return None
    finally:
        sock.close()
    if len(data) < 12:
        return None
    reply_id, flags = struct.unpack(">HH", data[:4])
    # Resposta de verdade (QR=1) com o mesmo número; "não existe" (3) também vale como resposta.
    if reply_id != qid or not flags & 0x8000 or (flags & 0xF) not in (0, 3):
        return None
    return elapsed


def _bench_one(server: str, names, port: int, out: Dict[str, Any]) -> None:
    samples, failed = [], 0
    for name in names:
        _dns_query(server, name, port=port)           # a 1ª pergunta aquece o cache do servidor
        ms = _dns_query(server, name, port=port)      # a 2ª é o dia a dia de quem usa o PC
        if ms is None:
            failed += 1
        else:
            samples.append(ms)
    out["failed"] = failed
    out["total"] = len(names)
    out["ms"] = round(statistics.median(samples), 1) if samples else None


def dns_bench(core, resolvers: Optional[Dict[str, Dict[str, Any]]] = None, port: int = 53) -> Dict[str, Any]:
    """Mede todos os provedores (e o DNS atual do provedor de internet) em paralelo."""
    candidates: Dict[str, Dict[str, Any]] = {}
    if resolvers is None:
        for key, prov in list(DNS_PROVIDERS.items()) + list(BENCH_EXTRA.items()):
            if prov["v4"]:
                candidates[key] = {"label": prov["label"], "server": prov["v4"][0]}
        try:
            state = dns_state(core)
        except Exception:
            state = {}
        if state.get("ok") and state.get("current") == "auto":
            servers = [s for a in state.get("adapters", []) for s in a.get("servers", []) if ":" not in s]
            if servers:
                candidates["atual"] = {"label": "Atual (do provedor de internet)", "server": servers[0]}
    else:
        candidates = {k: dict(v) for k, v in resolvers.items()}
    rows = {key: {"id": key, "label": c["label"], "server": c["server"]} for key, c in candidates.items()}
    threads = [threading.Thread(target=_bench_one, args=(c["server"], BENCH_NAMES, port, rows[key]), daemon=True)
               for key, c in candidates.items()]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    result = []
    for row in rows.values():
        row.setdefault("ms", None)
        row.setdefault("failed", len(BENCH_NAMES))
        row.setdefault("total", len(BENCH_NAMES))
        row["usable"] = row["ms"] is not None and row["failed"] * 3 <= row["total"]
        result.append(row)
    result.sort(key=lambda r: (not r["usable"], r["ms"] if r["ms"] is not None else 9e9))
    usable = [r for r in result if r["usable"]]
    if not usable:
        return {"ok": False, "rows": result, "best": None,
                "detail": "Nenhum DNS respondeu. Confira se a internet está funcionando e se o firewall não bloqueia a porta 53."}
    best = usable[0]
    current = next((r for r in usable if r["id"] == "atual"), None)
    # Só recomenda trocar se o vencedor for claramente melhor (10 ms ou 25%); senão trocar não vale o incômodo.
    worth = bool(current is None or best["id"] == "atual"
                 or (current["ms"] - best["ms"] >= 10 and best["ms"] <= current["ms"] * 0.75))
    if best["id"] == "atual" or (current is not None and not worth):
        detail = "O DNS que você já usa é rápido; não precisa trocar."
        pick = None
    else:
        detail = f"O mais rápido aqui é {best['label']}: {best['ms']} ms."
        pick = best["id"] if best["id"] in DNS_PROVIDERS else None
        if pick is None:
            detail += " Ele não está na lista para aplicar; escolha o próximo da lista."
            pick = next((r["id"] for r in usable if r["id"] in DNS_PROVIDERS), None)
    return {"ok": True, "rows": result, "best": best["id"], "pick": pick, "detail": detail}

